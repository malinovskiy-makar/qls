# -*- coding: utf-8 -*-
"""Сроки хранения данных: что старше срока и как это удалить (часть Б, 09.10.2026).

Политика обработки ПДн, раздел 7. Срок – ОДНА настройка `DATA_RETENTION_MONTHS`
(по умолчанию 12), отсчёт от создания записи.

Что удаляется целиком (строка и её файлы):
  реплики и вложения чата, загруженные файлы (`FileAsset`), события аналитики
  (`Event`), журнал поиска (`SearchLog`), обращения (`Feedback`, вместе со снимком
  экрана) и жалобы на задачи (`ProblemReport`).
Что теряет только файл (строка остаётся): файл сдачи `Submission.solution_file`.
Что только перечисляется числом: аккаунты, в которые не входили 3 года.

⚠️ `FileAsset`, привязанные к задаче банка (`Problem.files`), НЕ удаляются: это материал
каталога, а не файл человека; без этой оговорки команда стёрла бы рисунки задач.

⚠️ Файл удаляется ТОЛЬКО после того, как строка ушла из базы (транзакция уже
зафиксирована): сбой посреди работы оставляет лишний файл, а не строку без файла.
"""
import calendar
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from . import erasure

logger = logging.getLogger(__name__)

#: Аккаунт без входа дольше этого срока (лет) только перечисляется.
INACTIVE_ACCOUNT_YEARS = 3


def months_ago(now, months):
    """Момент на `months` календарных месяцев раньше `now` (день сжимается до конца месяца)."""
    index = now.year * 12 + (now.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


def cutoff(now=None, months=None):
    return months_ago(now or timezone.now(),
                      settings.DATA_RETENTION_MONTHS if months is None else months)


def _querysets(edge):
    """{метка: queryset} строк, которые удаляются целиком."""
    from problems.models import FileAsset
    from problems.models_platform import (
        ChatAttachment, ChatTurn, Event, Feedback, ProblemReport, SearchLog,
    )
    return {
        'problems.ChatTurn': ChatTurn.objects.filter(created_at__lt=edge),
        'problems.ChatAttachment': ChatAttachment.objects.filter(created_at__lt=edge),
        # Файлы задач банка – не файлы людей (см. докстринг модуля).
        'problems.FileAsset': FileAsset.objects.filter(
            created_at__lt=edge, problems__isnull=True),
        'problems.Event': Event.objects.filter(ts__lt=edge),
        'problems.SearchLog': SearchLog.objects.filter(ts__lt=edge),
        'problems.Feedback': Feedback.objects.filter(created_at__lt=edge),
        'problems.ProblemReport': ProblemReport.objects.filter(created_at__lt=edge),
    }


def _old_submissions(edge):
    from problems.models import Submission
    return Submission.objects.filter(submitted_at__lt=edge).exclude(solution_file='')


def _file_names(edge):
    """Пути файлов старых записей по видам. Собираются ДО удаления строк."""
    q = _querysets(edge)
    chat = set()
    for attachment in q['problems.ChatAttachment']:
        if attachment.file.name:
            chat.add(attachment.file.name)
        chat.update(p for p in (attachment.pages_json or []) if p)
    return {
        'чат': chat,
        'загрузки к попыткам': {a.file.name for a in q['problems.FileAsset'] if a.file.name},
        'снимки экрана': {f.screenshot.name for f in q['problems.Feedback'].exclude(screenshot='')},
        'файлы сдач': {s.solution_file.name for s in _old_submissions(edge)},
    }


def inactive_accounts(now=None):
    """Число аккаунтов, в которые не входили INACTIVE_ACCOUNT_YEARS лет (не удаляются)."""
    now = now or timezone.now()
    edge = months_ago(now, INACTIVE_ACCOUNT_YEARS * 12)
    from django.db.models import Q
    User = get_user_model()
    return (User.objects.filter(is_staff=False, is_superuser=False)
            .filter(Q(last_login__lt=edge) | Q(last_login__isnull=True, date_joined__lt=edge))
            .count())


def plan(now=None):
    """Сухой прогон: числа по всем пунктам. Базу и диск не меняет."""
    edge = cutoff(now)
    rows = {label: qs.count() for label, qs in _querysets(edge).items()}
    rows['problems.Submission (только файл)'] = _old_submissions(edge).count()
    files = {kind: len(paths) for kind, paths in _file_names(edge).items()}
    return {
        'cutoff': edge,
        'rows': rows,
        'files': files,
        'expired_sessions': Session.objects.filter(expire_date__lt=timezone.now()).count(),
        'inactive_accounts': inactive_accounts(now),
    }


def purge(now=None):
    """Удаляет всё старше срока. Возвращает итоговые числа."""
    edge = cutoff(now)
    names = _file_names(edge)
    all_names = set().union(*names.values())
    rows = {}
    with transaction.atomic():
        for label, queryset in _querysets(edge).items():
            rows[label] = queryset.delete()[0]
        old = _old_submissions(edge)
        rows['problems.Submission (только файл)'] = old.update(solution_file='')
    deleted, missing, failed = erasure.delete_files(all_names)
    return {'cutoff': edge, 'rows': rows, 'files_deleted': deleted,
            'files_missing': missing, 'files_failed': failed}
