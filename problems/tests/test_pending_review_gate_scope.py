# -*- coding: utf-8 -*-
"""`pending_review_gate --revert`: частичная раскатка шлюза ручного ревью.

Откат без ограничений снимает признак у ВСЕХ задач банка — это законное
«шлюз выключили целиком». Но для «разобрали три источника, открываем
только их» он слишком широк: заодно открылись бы все прочие, которых
человек не смотрел. Тесты держат обе границы.
"""
import io
import os
import shutil
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import Problem
from problems.tests.factories import link_source, make_problem, make_source


class RevertScopeTests(TestCase):

    def setUp(self):
        self.our = make_source('Наш источник')
        self.other = make_source('Чужой источник')
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def card(self, source=None, **kwargs):
        kwargs.setdefault('status', Problem.Status.PUBLISHED)
        kwargs.setdefault('hidden_pending_review', True)
        p = make_problem('Задача про спрос.', **kwargs)
        link_source(p, source or self.our)
        return p

    def run_cmd(self, **kw):
        out = io.StringIO()
        call_command('pending_review_gate', stdout=out, **kw)
        return out.getvalue()

    def exclude_file(self, ids):
        path = os.path.join(self.tmp, 'hold.txt')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('# держим\n')
            for pid in ids:
                fh.write('%d\tрешение не принято\n' % pid)
        return path

    # ------------------------------------------------------------------
    def test_scoped_revert_opens_only_its_sources(self):
        ours, foreign = self.card(), self.card(source=self.other)
        self.run_cmd(revert=True, apply=True, sources=str(self.our.id))
        ours.refresh_from_db(); foreign.refresh_from_db()
        self.assertFalse(ours.hidden_pending_review)
        self.assertTrue(foreign.hidden_pending_review,
                        'чужой источник трогать нельзя')

    def test_unscoped_revert_still_opens_everything(self):
        """Поведение без --sources прежнее — иначе это регрессия."""
        ours, foreign = self.card(), self.card(source=self.other)
        self.run_cmd(revert=True, apply=True)
        ours.refresh_from_db(); foreign.refresh_from_db()
        self.assertFalse(ours.hidden_pending_review)
        self.assertFalse(foreign.hidden_pending_review)

    def test_excluded_ids_stay_hidden(self):
        keep, open_ = self.card(), self.card()
        self.run_cmd(revert=True, apply=True, sources=str(self.our.id),
                     exclude_ids_file=self.exclude_file([keep.id]))
        keep.refresh_from_db(); open_.refresh_from_db()
        self.assertTrue(keep.hidden_pending_review)
        self.assertFalse(open_.hidden_pending_review)

    def test_only_publishable_keeps_draft_flagged(self):
        """ГЛАВНОЕ: черновику признак не снимаем.

        Иначе публикация этого черновика потом вернула бы его в каталог
        непроверенным — ровно та дыра, о которой предупреждает докстринг
        самой команды."""
        draft = self.card(status=Problem.Status.DRAFT)
        published = self.card()
        self.run_cmd(revert=True, apply=True, sources=str(self.our.id),
                     only_publishable=True)
        draft.refresh_from_db(); published.refresh_from_db()
        self.assertTrue(draft.hidden_pending_review)
        self.assertFalse(published.hidden_pending_review)

    def test_only_publishable_keeps_flagged_defect(self):
        bad = self.card(flagged=True)
        good = self.card()
        self.run_cmd(revert=True, apply=True, sources=str(self.our.id),
                     only_publishable=True)
        bad.refresh_from_db(); good.refresh_from_db()
        self.assertTrue(bad.hidden_pending_review)
        self.assertFalse(good.hidden_pending_review)

    def test_dry_run_changes_nothing(self):
        p = self.card()
        out = self.run_cmd(revert=True, sources=str(self.our.id))
        p.refresh_from_db()
        self.assertTrue(p.hidden_pending_review)
        self.assertIn('проба', out)

    def test_other_hiding_mechanisms_are_untouched(self):
        """Снимаем ТОЛЬКО свой признак: статус и флаг брака не трогаем."""
        p = self.card(status=Problem.Status.HIDDEN, flagged=True)
        self.run_cmd(revert=True, apply=True, sources=str(self.our.id))
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.HIDDEN)
        self.assertTrue(p.needs_quality_review)

    def test_unknown_source_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_cmd(revert=True, apply=True, sources='999999')

    def test_missing_exclude_file_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_cmd(revert=True, apply=True, sources=str(self.our.id),
                         exclude_ids_file=os.path.join(self.tmp, 'нет.txt'))
