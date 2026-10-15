# -*- coding: utf-8 -*-
"""Удаление данных человека: аккаунт целиком и диалоги с помощником (часть Б, 09.10.2026).

Исполняет сроки и права из Политики обработки персональных данных (разделы 7, 8)
и пункт 8 Согласия на помощника. Два входа, общая внутренность:

* `erase_user(user, apply=...)` – команда `manage.py erase_user`: строки «без указания
  человека», файлы, пользователь (каскад), сессии, запись в журнал удалений;
* `erase_chat(user)` – отзыв согласия на помощника в профиле: реплики и вложения чата
  вместе с файлами и картинками страниц.

Порядок аккаунта (раздел 4.2 отчёта инвентаризации ПДн 08.10.2026):

1. пути файлов выписываются ДО удаления строк (после него негде их взять);
2. в ОДНОЙ транзакции: строки, которые при удалении пользователя остались бы
   «без указания человека» (SET_NULL с его текстами), потом сам пользователь с
   каскадом. Сбой – ничего не удалено;
3. после фиксации транзакции: файлы с диска. Файл удаляется ТОЛЬКО после того, как
   строка ушла: иначе сбой оставил бы строку без файла;
4. сессии: номер пользователя лежит внутри данных сессии, поэтому перебираем их;
5. строка в журнал удалений – без логина и без содержимого.

⚠️ ЧТО КОМАНДА НЕ ДЕЛАЕТ: бэкапы (живут до 30 дней, Политика, раздел 7), журналы
контейнеров, данные у получателей (Z.ai, Яндекс Метрика) и события `Event`,
записанные по куке посетителя ДО входа: они не связаны с аккаунтом ничем, кроме
случайного номера браузера.
"""
import logging

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models.deletion import Collector
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Строки, которые при удалении пользователя остались бы с его содержимым, но «без
#: указания человека» (`on_delete=SET_NULL`): тексты кликов, запросы поиска,
#: обращения со снимком экрана, жалобы, результаты забегов, попытки тренажёра,
#: загруженные файлы. Их удаляем явно, пока связь с человеком ещё видна.
#: (метка модели, поле со ссылкой на пользователя)
EXPLICIT = (
    ('problems.Event', 'user'),
    ('problems.SearchLog', 'user'),
    ('problems.Feedback', 'user'),
    ('problems.ProblemReport', 'user'),
    ('game.GameResult', 'user'),
    ('vp.VPAttempt', 'user'),
    ('problems.FileAsset', 'uploaded_by'),
)


class Refused(Exception):
    """Удалять нельзя; текст – для оператора."""


# ── Что будет удалено ───────────────────────────────────────────────────────

def explicit_querysets(user):
    out = []
    for label, field in EXPLICIT:
        model = apps.get_model(label)
        out.append((label, model.objects.filter(**{field: user})))
    return out


def _add(paths, name):
    if name:
        paths.add(str(name))


def chat_file_paths(user):
    """Файлы чата: оригинал и картинки страниц для модели (без повторов)."""
    from problems.models_platform import ChatAttachment

    paths = set()
    for attachment in ChatAttachment.objects.filter(user=user):
        _add(paths, attachment.file.name)
        for page in attachment.pages_json or []:
            _add(paths, page)
    return paths


def file_paths(user):
    """Все файлы человека по видам: {вид: {путь в хранилище}}. Ничего не удаляет."""
    from problems.models import FileAsset, Submission
    from problems.models_platform import Feedback, UserProfile

    kinds = {'чат': chat_file_paths(user)}
    uploads, work, shots, avatar = set(), set(), set(), set()
    for asset in FileAsset.objects.filter(uploaded_by=user):
        _add(uploads, asset.file.name)
    for submission in Submission.objects.filter(student=user).exclude(solution_file=''):
        _add(work, submission.solution_file.name)
    for feedback in Feedback.objects.filter(user=user).exclude(screenshot=''):
        _add(shots, feedback.screenshot.name)
    for profile in UserProfile.objects.filter(user=user).exclude(avatar=''):
        _add(avatar, profile.avatar.name)
    kinds.update({'загрузки к попыткам': uploads, 'файлы сдач': work,
                  'снимки экрана': shots, 'аватар': avatar})
    return kinds


def cascade_counts(user):
    """{метка модели: число строк}, которые уйдут вместе с пользователем (каскад).

    Считает сборщик самого Django – тот же, что работает при `user.delete()`, поэтому
    список не разойдётся с настоящим удалением, как разошёлся бы написанный руками.
    Явные модели (`EXPLICIT`) сюда не входят: у них связь SET_NULL.
    """
    collector = Collector(using='default')
    collector.collect([user])
    counts = {}
    for model, instances in collector.data.items():
        counts[model._meta.label] = counts.get(model._meta.label, 0) + len(instances)
    for queryset in collector.fast_deletes:
        counts[queryset.model._meta.label] = (
            counts.get(queryset.model._meta.label, 0) + queryset.count())
    return {label: n for label, n in counts.items() if n}


def orphan_counts(user):
    """{«модель.поле»: число строк}, которые останутся БЕЗ АВТОРА (SET_NULL вне EXPLICIT).

    Авторские материалы: работы, подборки, наборы игры, уроки, правки задач. Связь с
    человеком обнулится, содержимое останется: оно принадлежит курсу, а не личности.
    """
    explicit = {(apps.get_model(label), field) for label, field in EXPLICIT}
    counts = {}
    for rel in user._meta.related_objects:
        if rel.on_delete is not models.SET_NULL or rel.many_to_many:
            continue
        if (rel.related_model, rel.field.name) in explicit:
            continue
        n = rel.related_model.objects.filter(**{rel.field.name: user}).count()
        if n:
            counts['%s.%s' % (rel.related_model._meta.label, rel.field.name)] = n
    return counts


def user_session_keys(user):
    """Ключи сессий, в данных которых лежит этот пользователь."""
    wanted = str(user.pk)
    keys = []
    for session in Session.objects.iterator():
        try:
            data = session.get_decoded()
        except Exception:        # битая строка: чужую сессию не трогаем
            continue
        if str(data.get('_auth_user_id', '')) == wanted:
            keys.append(session.session_key)
    return keys


def plan_user(user):
    """Сухой прогон: что будет удалено. Базу и диск не меняет."""
    explicit = {label: qs.count() for label, qs in explicit_querysets(user)}
    explicit = {label: n for label, n in explicit.items() if n}
    files = file_paths(user)
    on_disk = {kind: sum(1 for p in paths if _exists(p)) for kind, paths in files.items()}
    return {
        'explicit': explicit,
        'cascade': cascade_counts(user),
        'orphans': orphan_counts(user),
        'files': {kind: len(paths) for kind, paths in files.items()},
        'files_on_disk': on_disk,
        'sessions': len(user_session_keys(user)),
    }


# ── Удаление ────────────────────────────────────────────────────────────────

def _exists(name):
    try:
        return default_storage.exists(name)
    except SuspiciousFileOperation:
        return False


def delete_files(paths):
    """Удаляет файлы из хранилища. Возвращает (удалено, не найдено, ошибок)."""
    deleted = missing = failed = 0
    for name in sorted(set(paths)):
        try:
            if default_storage.exists(name):
                default_storage.delete(name)
                deleted += 1
            else:
                missing += 1
        except SuspiciousFileOperation:
            failed += 1
            logger.warning('Путь вне хранилища, файл не тронут: %r', name)
        except OSError:
            failed += 1
            logger.exception('Файл не удалён: %r', name)
    return deleted, missing, failed


def delete_sessions(keys):
    """Удаляет сессии из базы И из кэша (движок `cached_db`)."""
    from django.contrib.sessions.backends.cached_db import SessionStore

    for key in keys:
        SessionStore(key).delete()
    return len(keys)


def erase_chat(user):
    """Диалоги с помощником: реплики и вложения чата вместе с файлами.

    Общая внутренность для отзыва согласия на помощника (профиль) и для
    `erase_user`. Строки удаляются в транзакции, файлы – после неё.
    Возвращает {'rows': число строк, 'files': число файлов}.
    """
    from problems.models_platform import ChatAttachment, ChatTurn

    paths = chat_file_paths(user)
    with transaction.atomic():
        rows = ChatTurn.objects.filter(user=user).delete()[0]
        rows += ChatAttachment.objects.filter(user=user).delete()[0]
    deleted, _missing, _failed = delete_files(paths)
    return {'rows': rows, 'files': deleted}


def erase_user(user):
    """Выполняет удаление. Вызывать после `check_allowed`. Возвращает итог."""
    from problems.models_legal import ErasureLog

    check_allowed(user)
    user_pk = user.pk
    paths = set()
    for group in file_paths(user).values():
        paths |= group
    sessions = user_session_keys(user)

    rows = 0
    with transaction.atomic():
        for _label, queryset in explicit_querysets(user):
            rows += queryset.delete()[0]
        rows += user.delete()[0]

    files, missing, failed = delete_files(paths)
    delete_sessions(sessions)

    ErasureLog.objects.create(created_at=timezone.now(), user_pk=user_pk,
                              rows_deleted=rows, files_deleted=files)
    return {'rows': rows, 'files': files, 'files_missing': missing,
            'files_failed': failed, 'sessions': len(sessions)}


def check_allowed(user):
    if user.is_staff or user.is_superuser:
        raise Refused('Сотрудника командой удалить нельзя: это учётная запись с правами '
                      'администратора. Снимите права в админке и повторите.')


def find_user(username):
    User = get_user_model()
    try:
        return User.objects.get(**{User.USERNAME_FIELD: username})
    except User.DoesNotExist:
        raise Refused('Пользователь с таким логином не найден.')
