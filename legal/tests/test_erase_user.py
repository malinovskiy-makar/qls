# -*- coding: utf-8 -*-
"""Часть Б, фаза 3: `manage.py erase_user` – удаление аккаунта одной командой.

Что держат эти тесты.

* Сухой прогон ничего не меняет, печатает числа и строку «Останется без автора».
* `--apply` удаляет строки «без указания человека», пользователя с каскадом, файлы
  каждого вида (чат и картинки страниц, загрузки, сдачи, снимок экрана, аватар),
  сессии (из базы и из кэша) и пишет одну строку в журнал без логина.
* Инвариант: по списку моделей со связью на пользователя из `scripts/legal/pd_inventory.py`
  строк удалённого пользователя не осталось нигде; «без автора» остаются только
  авторские материалы; файлов из его списка на диске нет; чужие данные не тронуты.
* Сотрудника удалить нельзя.
"""
import importlib.util
import io
import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from PIL import Image

from game.models import GameResult, GameSet
from legal import consent
from problems import erasure
from problems.models import (
    Assignment, CatalogAttempt, Collection, FileAsset, StudentGroup, Submission,
)
from problems.models_legal import ConsentRecord, ErasureLog
from problems.models_platform import (
    AiUsageLog, ChatAttachment, ChatTurn, CustomProblem, Event, Feedback, LearningEvent,
    ProblemProgress, ProblemReport, SavedProblem, SearchLog, UserProfile,
)
from problems.tests.factories import make_problem, make_user
from vp.models import VPAttempt, VPVariant

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='qls_erase_media_')


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (10, 20, 30)).save(buf, 'PNG')
    return buf.getvalue()


def _inventory():
    """Скрипт инвентаризации как модуль: ему можно верить как списку моделей."""
    path = Path(settings.BASE_DIR) / 'scripts' / 'legal' / 'pd_inventory.py'
    spec = importlib.util.spec_from_file_location('pd_inventory_for_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def populate(user, tag):
    """Данные человека во всех моделях, которые затрагивает удаление, и файлы каждого вида."""
    problem = make_problem('Условие %s.' % tag)
    paths = {}

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.avatar.save('%s.jpg' % tag, ContentFile(_png()))
    paths['аватар'] = [profile.avatar.name]

    # Явно удаляемые строки «без указания человека».
    Event.objects.create(user=user, visitor='v-' + tag, page_key='p', path='/', name='click')
    SearchLog.objects.create(user=user, query='запрос ' + tag)
    shot = Feedback(user=user, kind='bug', page_key='p')
    shot.screenshot.save('%s.png' % tag, ContentFile(_png()), save=False)
    shot.save()
    paths['снимок'] = [shot.screenshot.name]
    ProblemReport.objects.create(user=user, source='catalog', kind='other')
    GameResult.objects.create(user=user, mode='daily')
    variant = VPVariant.objects.create(slug='v-' + tag, title='Вариант', grade_band='9-11',
                                       year=2026, source_kind='official')
    VPAttempt.objects.create(user=user, variant=variant, public_code='c' + tag)
    asset = FileAsset(uploaded_by=user)
    asset.file.save('%s.png' % tag, ContentFile(_png()), save=False)
    asset.save()
    paths['загрузка'] = [asset.file.name]

    # Чат: файл, картинки страниц (отдельные файлы) и реплика.
    chat_file = ChatAttachment(user=user, problem=problem, mime='application/pdf', size=10)
    chat_file.file.save('%s.pdf' % tag, ContentFile(b'%PDF-1.4 test'), save=False)
    chat_file.save()
    pages = []
    for number in (1, 2):
        from django.core.files.storage import default_storage
        pages.append(default_storage.save('chat/%s_p%d.png' % (tag, number), ContentFile(_png())))
    chat_file.pages_json = pages
    chat_file.save(update_fields=['pages_json'])
    ChatTurn.objects.create(user=user, problem=problem)
    paths['чат'] = [chat_file.file.name] + pages

    # Работа: сдача с файлом.
    homework = Assignment.objects.create(name='Работа ' + tag)
    submission = Submission(student=user, assignment=homework)
    submission.solution_file.save('%s.pdf' % tag, ContentFile(b'%PDF-1.4 work'), save=False)
    submission.save()
    paths['сдача'] = [submission.solution_file.name]

    # Прочее, что уходит каскадом.
    AiUsageLog.objects.create(user=user, model_name='m')
    LearningEvent.objects.create(user=user, source='catalog', event_type='open')
    CatalogAttempt.objects.create(user=user, problem=problem)
    SavedProblem.objects.create(owner=user, catalog_problem=problem)
    ProblemProgress.objects.create(user=user, problem=problem)
    consent.grant(user, ConsentRecord.Kind.PD, ConsentRecord.Source.REGISTER)
    CustomProblem.objects.create(owner=user, statement='своя ' + tag)
    StudentGroup.objects.create(teacher=user, name='Группа ' + tag, invite_code='G' + tag.upper())

    # Авторские материалы: после удаления остаются без автора.
    Assignment.objects.create(name='Моя работа ' + tag, author=user)
    Collection.objects.create(name='Моя подборка ' + tag, author=user)
    GameSet.objects.create(mode='daily', author=user)
    return paths


def all_paths(paths):
    return [p for group in paths.values() for p in group]


def exists(name):
    return os.path.exists(os.path.join(MEDIA, name))


@override_settings(MEDIA_ROOT=MEDIA)
class EraseUserTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.user = make_user('erase_target', role='teacher')
        self.other = make_user('erase_bystander')
        self.paths = populate(self.user, 'aaa')
        self.other_paths = populate(self.other, 'bbb')
        self.user_sessions = []
        for _ in range(2):
            client = Client()
            client.force_login(self.user)
            self.user_sessions.append(client.session.session_key)
        other_client = Client()
        other_client.force_login(self.other)
        self.other_session = other_client.session.session_key

    def _run(self, *args):
        out = StringIO()
        call_command('erase_user', *args, stdout=out)
        return out.getvalue()

    # -- сухой прогон ---------------------------------------------------------

    def test_dry_run_changes_nothing_and_prints_the_numbers(self):
        pk = self.user.pk
        before = {'users': User.objects.count(), 'events': Event.objects.count(),
                  'chat': ChatTurn.objects.count(), 'sessions': Session.objects.count()}
        text = self._run('erase_target')
        self.assertIn('Сухой прогон: ничего не удалено', text)
        self.assertIn('problems.Event', text)
        self.assertIn('problems.ChatAttachment', text)
        self.assertIn('Останется без автора'.lower(), text.lower())
        self.assertIn('problems.Assignment.author', text)
        self.assertIn('Сессии: 2', text)
        # Логин в вывод не попадает; номер – да.
        self.assertNotIn('erase_target', text)
        self.assertIn('№%d' % pk, text)
        self.assertEqual(before, {'users': User.objects.count(), 'events': Event.objects.count(),
                                  'chat': ChatTurn.objects.count(), 'sessions': Session.objects.count()})
        self.assertTrue(all(exists(p) for p in all_paths(self.paths)))
        self.assertEqual(ErasureLog.objects.count(), 0)

    # -- удаление и инвариант ------------------------------------------------------

    def test_apply_leaves_no_rows_no_files_no_sessions(self):
        pk = self.user.pk
        other_counts = self._counts_of(self.other)
        plan = erasure.plan_user(self.user)
        expected_rows = sum(plan['explicit'].values()) + sum(plan['cascade'].values())
        text = self._run('erase_target', '--apply')
        self.assertIn('Удалено: строк', text)

        # Пользователя нет, его сессий нет (ни в базе, ни в кэше), чужая сессия цела.
        self.assertFalse(User.objects.filter(pk=pk).exists())
        for key in self.user_sessions:
            self.assertFalse(Session.objects.filter(session_key=key).exists())
        self.assertTrue(Session.objects.filter(session_key=self.other_session).exists())

        # Файлы: все из его списка исчезли, чужие на месте.
        self.assertEqual([p for p in all_paths(self.paths) if exists(p)], [])
        self.assertTrue(all(exists(p) for p in all_paths(self.other_paths)))

        # Инвариант по списку моделей инвентаризации.
        checked = self._assert_nothing_left(pk)
        self.assertGreaterEqual(checked, 49)   # 48 моделей с прямым ключом на пользователя + он сам

        # Авторские материалы остались, но без автора.
        self.assertEqual(Assignment.objects.filter(name__startswith='Моя работа aaa', author=None).count(), 1)
        self.assertEqual(Collection.objects.filter(name='Моя подборка aaa', author=None).count(), 1)
        self.assertEqual(GameSet.objects.filter(author=None).count(), 1)

        # Чужие данные не тронуты.
        self.assertEqual(self._counts_of(self.other), other_counts)

        # Журнал: одна строка, без логина и содержимого.
        entry = ErasureLog.objects.get()
        self.assertEqual(entry.user_pk, pk)
        # Сухой прогон не врёт: он обещал ровно столько строк, сколько удалено.
        self.assertEqual(entry.rows_deleted, expected_rows)
        self.assertEqual(entry.files_deleted, len(set(all_paths(self.paths))))
        field_names = {f.name for f in ErasureLog._meta.get_fields()}
        self.assertEqual(field_names, {'id', 'created_at', 'user_pk', 'rows_deleted', 'files_deleted'})

    def test_explicit_rows_are_deleted_before_the_link_disappears(self):
        """Без явного удаления эти строки остались бы с текстами, но без человека."""
        self._run('erase_target', '--apply')
        self.assertEqual(Event.objects.filter(visitor='v-aaa').count(), 0)
        self.assertEqual(SearchLog.objects.filter(query='запрос aaa').count(), 0)
        self.assertEqual(Feedback.objects.filter(user=None).count(), 0)
        self.assertEqual(ProblemReport.objects.filter(user=None).count(), 0)
        self.assertEqual(GameResult.objects.filter(user=None).count(), 0)
        self.assertEqual(VPAttempt.objects.filter(user=None).count(), 0)
        self.assertEqual(FileAsset.objects.filter(uploaded_by=None).count(), 0)

    def test_a_failure_in_the_transaction_deletes_nothing(self):
        from unittest import mock
        with mock.patch.object(User, 'delete', side_effect=RuntimeError('сбой')):
            with self.assertRaises(RuntimeError):
                erasure.erase_user(self.user)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(Event.objects.filter(visitor='v-aaa').count(), 1)
        self.assertTrue(all(exists(p) for p in all_paths(self.paths)))
        self.assertEqual(ErasureLog.objects.count(), 0)

    def test_a_missing_file_does_not_stop_the_deletion(self):
        os.remove(os.path.join(MEDIA, self.paths['чат'][1]))
        text = self._run('erase_target', '--apply')
        self.assertIn('не найдено на диске 1', text)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    # -- отказы ----------------------------------------------------------------

    def test_staff_cannot_be_erased(self):
        make_user('erase_staff', is_staff=True)
        for args in (('erase_staff',), ('erase_staff', '--apply')):
            with self.assertRaises(CommandError) as ctx:
                self._run(*args)
            self.assertIn('Сотрудника командой удалить нельзя', str(ctx.exception))
        self.assertTrue(User.objects.filter(username='erase_staff').exists())

    def test_superuser_cannot_be_erased(self):
        User.objects.create_superuser('erase_root', password='x12345678')
        with self.assertRaises(CommandError):
            self._run('erase_root', '--apply')

    def test_unknown_login_is_a_clear_error(self):
        with self.assertRaises(CommandError) as ctx:
            self._run('nobody_here')
        self.assertIn('не найден', str(ctx.exception))

    # -- помощники --------------------------------------------------------------

    def _counts_of(self, user):
        return {
            'events': Event.objects.filter(user=user).count(),
            'search': SearchLog.objects.filter(user=user).count(),
            'chat_turns': ChatTurn.objects.filter(user=user).count(),
            'chat_files': ChatAttachment.objects.filter(user=user).count(),
            'submissions': Submission.objects.filter(student=user).count(),
            'authored': Assignment.objects.filter(author=user).count(),
        }

    def _assert_nothing_left(self, pk):
        """Для каждой модели со связью на пользователя из инвентаризации – ни одной строки."""
        inventory = _inventory()
        _models, rows, user_model = inventory.collect_models()
        checked = 0
        for model, info in rows.items():
            if model is user_model:
                self.assertFalse(model.objects.filter(pk=pk).exists())
                checked += 1
                continue
            if info['group'] != 'прямой ключ на User':
                continue
            for field in inventory._relation_fields(model):
                if field.related_model is user_model and not field.many_to_many:
                    self.assertEqual(
                        model.objects.filter(**{field.attname: pk}).count(), 0,
                        '%s.%s: строки удалённого пользователя остались' % (model._meta.label, field.name))
            checked += 1
        return checked
