# -*- coding: utf-8 -*-
"""`publish_ready_sources`: в published уходят только чистые черновики."""
import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import Problem
from problems.tests.factories import link_source, make_problem, make_source


class PublishReadyTests(TestCase):

    def setUp(self):
        self.src = make_source('Новый источник')
        self.other = make_source('Чужой источник')

    def draft(self, text='Черновик.', source=None, **kwargs):
        kwargs.setdefault('content_format', Problem.ContentFormat.MARKDOWN)
        p = make_problem(text, status=Problem.Status.DRAFT, **kwargs)
        link_source(p, source or self.src)
        return p

    def run_cmd(self, **kwargs):
        out = io.StringIO()
        kwargs.setdefault('sources', str(self.src.id))
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

    def test_unknown_source_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_cmd(apply=True, sources='999999')
