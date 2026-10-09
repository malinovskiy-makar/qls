# -*- coding: utf-8 -*-
"""Часть Б, фаза 5: `manage.py purge_expired` – сроки хранения данных.

Политика, раздел 7: файлы решений, диалоги с помощником, события, поиск, обращения и
снимки экрана – 12 месяцев с создания. По каждой модели: запись 13 месяцев удалена,
11 месяцев осталась; файл старой записи исчез с диска, файл свежей остался.
"""
import datetime
import io
import os
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from problems import retention
from problems.models import Assignment, FileAsset, Submission
from problems.models_platform import (
    ChatAttachment, ChatTurn, Event, Feedback, ProblemReport, SearchLog,
)
from problems.tests.factories import make_problem, make_user

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='qls_purge_media_')


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (5, 5, 5)).save(buf, 'PNG')
    return buf.getvalue()


def _exists(name):
    return os.path.exists(os.path.join(MEDIA, name))


def _age(model, pk, months, field='created_at'):
    """Состарить запись на `months` месяцев (авто-поля времени иначе не задать)."""
    moment = retention.months_ago(timezone.now(), months)
    model.objects.filter(pk=pk).update(**{field: moment})


class MonthsAgoTests(SimpleTestCase):
    def test_plain_month(self):
        now = datetime.datetime(2026, 10, 9, 12, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(retention.months_ago(now, 12), now.replace(year=2025))
        self.assertEqual(retention.months_ago(now, 1), now.replace(month=9))

    def test_day_is_clamped_to_the_end_of_a_shorter_month(self):
        now = datetime.datetime(2026, 3, 31, tzinfo=datetime.timezone.utc)
        self.assertEqual(retention.months_ago(now, 1).day, 28)

    def test_crossing_the_new_year(self):
        now = datetime.datetime(2026, 2, 15, tzinfo=datetime.timezone.utc)
        self.assertEqual((retention.months_ago(now, 3).year, retention.months_ago(now, 3).month), (2025, 11))

    def test_one_setting_one_default(self):
        self.assertEqual(settings.DATA_RETENTION_MONTHS, 12)


@override_settings(MEDIA_ROOT=MEDIA)
class PurgeExpiredTests(TestCase):
    OLD, FRESH = 13, 11

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = make_user('purge_user')
        self.problem = make_problem('Условие.')
        self.rows = {}      # {метка: (старая, свежая)}
        self.files = {}     # {вид: (старый, свежий)}

        def pair(model, label, build, field='created_at'):
            old, fresh = build('old'), build('fresh')
            _age(model, old.pk, self.OLD, field)
            _age(model, fresh.pk, self.FRESH, field)
            self.rows[label] = (model, old.pk, fresh.pk)
            return old, fresh

        # Чат: вложение с файлом и двумя картинками страниц + реплика.
        def chat_attachment(tag):
            a = ChatAttachment(user=self.user, problem=self.problem, mime='application/pdf', size=4)
            a.file.save('%s.pdf' % tag, ContentFile(b'%PDF'), save=False)
            a.save()
            pages = [default_storage.save('chat/%s_p%d.png' % (tag, n), ContentFile(_png())) for n in (1, 2)]
            a.pages_json = pages
            a.save(update_fields=['pages_json'])
            return a
        old_a, fresh_a = pair(ChatAttachment, 'problems.ChatAttachment', chat_attachment)
        self.files['чат'] = ([old_a.file.name] + old_a.pages_json, [fresh_a.file.name] + fresh_a.pages_json)
        pair(ChatTurn, 'problems.ChatTurn',
             lambda tag: ChatTurn.objects.create(user=self.user, problem=self.problem, user_text=tag))

        def asset(tag):
            a = FileAsset(uploaded_by=self.user)
            a.file.save('%s.png' % tag, ContentFile(_png()), save=False)
            a.save()
            return a
        old_f, fresh_f = pair(FileAsset, 'problems.FileAsset', asset)
        self.files['загрузки'] = ([old_f.file.name], [fresh_f.file.name])

        pair(Event, 'problems.Event', lambda tag: Event.objects.create(
            user=self.user, visitor='v-' + tag, page_key='p', path='/', name='click'), field='ts')
        pair(SearchLog, 'problems.SearchLog',
             lambda tag: SearchLog.objects.create(user=self.user, query='q ' + tag), field='ts')

        def feedback(tag):
            f = Feedback(user=self.user, kind='bug', page_key='p')
            f.screenshot.save('%s.png' % tag, ContentFile(_png()), save=False)
            f.save()
            return f
        old_s, fresh_s = pair(Feedback, 'problems.Feedback', feedback)
        self.files['снимки'] = ([old_s.screenshot.name], [fresh_s.screenshot.name])
        pair(ProblemReport, 'problems.ProblemReport',
             lambda tag: ProblemReport.objects.create(user=self.user, source='catalog', kind='other'))

        # Сдача: строка остаётся в любом случае, у старой стирается файл.
        homework = Assignment.objects.create(name='Работа')

        def submission(tag):
            s = Submission(student=self.user, assignment=homework)
            s.solution_file.save('%s.pdf' % tag, ContentFile(b'%PDF'), save=False)
            s.save()
            return s
        old_w, fresh_w = submission('old'), submission('fresh')
        _age(Submission, old_w.pk, self.OLD, 'submitted_at')
        _age(Submission, fresh_w.pk, self.FRESH, 'submitted_at')
        self.old_work, self.fresh_work = old_w.pk, fresh_w.pk
        self.files['сдачи'] = ([old_w.solution_file.name], [fresh_w.solution_file.name])

    def _run(self, *args):
        out = StringIO()
        call_command('purge_expired', *args, stdout=out)
        return out.getvalue()

    # -- сухой прогон ---------------------------------------------------------

    def test_dry_run_changes_nothing_and_prints_the_numbers(self):
        counts = {label: model.objects.count() for label, (model, _o, _f) in self.rows.items()}
        text = self._run()
        self.assertIn('Сухой прогон: ничего не удалено', text)
        for label in self.rows:
            self.assertIn(label, text)
        self.assertIn('Аккаунтов без входа больше 3 лет', text)
        self.assertEqual(counts, {label: model.objects.count() for label, (model, _o, _f) in self.rows.items()})
        for old, fresh in self.files.values():
            self.assertTrue(all(_exists(p) for p in old + fresh))
        self.assertTrue(Submission.objects.filter(pk=self.old_work).exclude(solution_file='').exists())

    def test_the_plan_promises_exactly_what_is_deleted(self):
        plan = retention.plan()
        self.assertEqual(plan['rows']['problems.ChatTurn'], 1)
        self.assertEqual(plan['rows']['problems.Submission (только файл)'], 1)
        self.assertEqual(plan['files']['чат'], 3)
        self.assertEqual(plan['files']['файлы сдач'], 1)

    # -- удаление ---------------------------------------------------------------

    def test_a_thirteen_month_row_goes_and_an_eleven_month_row_stays_for_every_model(self):
        self._run('--apply')
        for label, (model, old_pk, fresh_pk) in self.rows.items():
            with self.subTest(model=label):
                self.assertFalse(model.objects.filter(pk=old_pk).exists(), 'старая осталась')
                self.assertTrue(model.objects.filter(pk=fresh_pk).exists(), 'свежая удалена')

    def test_files_of_old_rows_vanish_and_files_of_fresh_rows_stay(self):
        self._run('--apply')
        for kind, (old, fresh) in self.files.items():
            with self.subTest(kind=kind):
                self.assertEqual([p for p in old if _exists(p)], [], 'файл старой записи остался')
                self.assertTrue(all(_exists(p) for p in fresh), 'файл свежей записи удалён')

    def test_submission_row_stays_and_only_its_file_is_cleared(self):
        self._run('--apply')
        old = Submission.objects.get(pk=self.old_work)
        self.assertFalse(old.solution_file)
        self.assertTrue(Submission.objects.get(pk=self.fresh_work).solution_file)

    def test_a_file_asset_of_a_catalog_problem_is_never_purged(self):
        asset = FileAsset(uploaded_by=None)
        asset.file.save('figure.png', ContentFile(_png()), save=False)
        asset.save()
        self.problem.files.add(asset)
        _age(FileAsset, asset.pk, 40)
        self._run('--apply')
        self.assertTrue(FileAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(_exists(asset.file.name))

    def test_apply_runs_clearsessions_and_the_training_cleanup(self):
        Session.objects.create(session_key='dead' * 8, session_data='x',
                               expire_date=timezone.now() - datetime.timedelta(days=1))
        live = Session.objects.create(session_key='live' * 8, session_data='x',
                                      expire_date=timezone.now() + datetime.timedelta(days=1))
        calls = []
        real = call_command

        def spy(name, *args, **kwargs):
            calls.append(name)
            return real(name, *args, **kwargs)

        with mock.patch('problems.management.commands.purge_expired.call_command', spy):
            self._run('--apply')
        self.assertIn('clearsessions', calls)
        self.assertIn('cleanup_training_attempts', calls)
        self.assertFalse(Session.objects.filter(session_key='dead' * 8).exists())
        self.assertTrue(Session.objects.filter(pk=live.pk).exists())

    def test_inactive_accounts_are_counted_but_never_deleted(self):
        old_login = retention.months_ago(timezone.now(), 40)
        ghost = make_user('purge_ghost')
        User.objects.filter(pk=ghost.pk).update(last_login=old_login, date_joined=old_login)
        staff = make_user('purge_staff_old', is_staff=True)
        User.objects.filter(pk=staff.pk).update(last_login=old_login, date_joined=old_login)
        self.assertEqual(retention.inactive_accounts(), 1)
        text = self._run('--apply')
        self.assertIn('Аккаунтов без входа больше 3 лет (не удаляются): 1', text)
        self.assertTrue(User.objects.filter(pk=ghost.pk).exists())
        self.assertTrue(User.objects.filter(pk=staff.pk).exists())

    @override_settings(DATA_RETENTION_MONTHS=6)
    def test_the_term_is_one_setting(self):
        self._run('--apply')
        for label, (model, _old, fresh_pk) in self.rows.items():
            self.assertFalse(model.objects.filter(pk=fresh_pk).exists(), label)

    def test_a_second_run_finds_nothing(self):
        self._run('--apply')
        plan = retention.plan()
        self.assertEqual({k: v for k, v in plan['rows'].items() if v}, {})
        self.assertEqual({k: v for k, v in plan['files'].items() if v}, {})
