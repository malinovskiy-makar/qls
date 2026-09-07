# -*- coding: utf-8 -*-
"""`publish_ready_sources`: в published уходят только чистые черновики."""
import io
import shutil
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import Problem
from problems.tests.factories import link_source, make_problem, make_source


class PublishReadyTests(TestCase):

    def setUp(self):
        self.src = make_source('Новый источник')
        self.other = make_source('Чужой источник')
        # ⚠️ Свой --report-dir ОБЯЗАТЕЛЕН. Без него прогон набора пишет
        # журнал отката тестовыми данными прямо в боевую папку отчётов и
        # затирает настоящий: путь отката после этого ведёт в никуда.
        # Та же беда уже чинилась у команд импорта (коммит 2da55ee) и в
        # revert_gate_v2_blocked_markdown.
        self.reports = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.reports, ignore_errors=True)

    def draft(self, text='Черновик.', source=None, **kwargs):
        kwargs.setdefault('content_format', Problem.ContentFormat.MARKDOWN)
        p = make_problem(text, status=Problem.Status.DRAFT, **kwargs)
        link_source(p, source or self.src)
        return p

    def run_cmd(self, **kwargs):
        out = io.StringIO()
        kwargs.setdefault('sources', str(self.src.id))
        kwargs.setdefault('report_dir', self.reports)
        call_command('publish_ready_sources', stdout=out, **kwargs)
        return out.getvalue()

    # ------------------------------------------------------------------
    def test_clean_draft_is_published(self):
        p = self.draft()
        self.run_cmd(apply=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.PUBLISHED)

    def test_flagged_draft_stays_draft(self):
        p = self.draft(flagged=True)
        self.run_cmd(apply=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.DRAFT)

    def test_plain_format_draft_stays_draft(self):
        """`plain` и означает «шлюз рендера не пропустил»."""
        p = self.draft(content_format='plain')
        self.run_cmd(apply=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.DRAFT)

    def test_hidden_is_not_touched(self):
        """`hidden` поставлен осознанно — это не «руки не дошли»."""
        p = make_problem('Убрана руками.', status=Problem.Status.HIDDEN,
                         content_format=Problem.ContentFormat.MARKDOWN)
        link_source(p, self.src)
        self.run_cmd(apply=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.HIDDEN)

    def test_foreign_source_is_not_touched(self):
        p = self.draft(source=self.other)
        self.run_cmd(apply=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.DRAFT)

    def test_hidden_pending_review_is_left_alone(self):
        """Шлюз ручного ревью не снимается: человек их НЕ смотрел."""
        p = self.draft(hidden_pending_review=True)
        self.run_cmd(apply=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.PUBLISHED)
        self.assertTrue(p.hidden_pending_review)

    def test_dry_run_changes_nothing(self):
        p = self.draft()
        out = self.run_cmd()
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.DRAFT)
        self.assertIn('СУХОЙ ПРОГОН', out)

    def test_revert_restores_draft(self):
        p = self.draft()
        self.run_cmd(apply=True)
        self.run_cmd(revert=True)
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.DRAFT)

    def test_second_apply_is_a_noop(self):
        self.draft()
        self.run_cmd(apply=True)
        out = self.run_cmd()
        self.assertIn('из них к публикации          0', out)

    def test_journal_goes_to_the_given_report_dir(self):
        """Журнал отката обязан лечь в --report-dir, а не в боевую папку.

        Без этого прогон набора затирает настоящий журнал тестовыми
        данными, и путь отката ведёт в никуда. Именно так и случилось
        30.08: боевой журнал на 9 418 строк был затёрт одной строкой из
        теста и восстанавливался из снимка gate_backup.json."""
        import os
        self.draft()
        self.run_cmd(apply=True)
        self.assertTrue(os.path.isfile(
            os.path.join(self.reports, 'publish_ready_backup.json')))

    def test_unknown_source_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_cmd(apply=True, sources='999999')
