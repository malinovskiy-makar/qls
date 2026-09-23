"""Пересчёт баллов сданных попыток после правки эталона: `manage.py rescore_vp`.

Сценарии владельца (23.09.2026): эталон поправили на месте — балл старой
попытки пересчитывается строго по новому эталону, в обе стороны; несданные
попытки, время сдачи и зачётность не трогаются; сухой прогон ничего не пишет;
повторный запуск ничего не меняет.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from vp import views
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import answer_all, make_full_variant


def run(*args):
    out = StringIO()
    call_command('rescore_vp', *args, stdout=out)
    return out.getvalue()


class RescoreTests(TestCase):
    def setUp(self):
        self.variant = make_full_variant('vp-rs')
        # A: всё верно по СТАРЫМ эталонам, сдана.
        self.a = answer_all(self.variant, right=True)
        views._finalize(self.a, auto=False)
        # B: всё верно, но в №5 ответ, который верен только по НОВОМУ эталону.
        self.b = VPAttempt.objects.create(variant=self.variant, public_code='rs-b')
        for item in self.variant.items.all():
            raw = item.answer if item.kind == 'short_text' else (
                item.correct[0] if item.kind == 'single' else item.correct)
            if item.number == 5:
                raw = 'термин пять'
            VPAnswer.objects.create(attempt=self.b, item=item, raw=raw)
        views._finalize(self.b, auto=False)
        self.a.refresh_from_db()
        self.b.refresh_from_db()

    def fix_key(self, number=5, answer='термин пять'):
        """Как `import_vp`: эталон правится на месте, задание то же."""
        item = self.variant.items.get(number=number)
        item.answer = answer
        item.save(update_fields=['answer'])

    def answer(self, attempt, number):
        return attempt.answers.get(item__number=number)

    # ---------------------------------------------------------------- сценарии

    def test_01_scores_before_fix(self):
        self.assertEqual(self.a.score, Decimal('100.00'))
        self.assertEqual(self.b.score, Decimal('98.00'))

    def test_02_fixed_key_raises_score(self):
        self.fix_key()
        run('--variant', 'vp-rs')
        self.b.refresh_from_db()
        self.assertEqual(self.b.score, Decimal('100.00'))
        answer = self.answer(self.b, 5)
        self.assertEqual((answer.score, answer.is_correct), (Decimal('2.00'), True))

    def test_03_strict_both_ways_lowers_old_key(self):
        self.fix_key()
        run('--variant', 'vp-rs')
        self.a.refresh_from_db()
        self.assertEqual(self.a.score, Decimal('98.00'))
        answer = self.answer(self.a, 5)
        self.assertEqual((answer.score, answer.is_correct), (Decimal('0.00'), False))

    def test_04_accepted_synonym_counts(self):
        item = self.variant.items.get(number=7)
        item.accepted = ['седьмой термин']
        item.save(update_fields=['accepted'])
        answer = self.answer(self.b, 7)
        answer.raw = 'седьмой термин'
        answer.save(update_fields=['raw'])
        run('--variant', 'vp-rs')
        answer.refresh_from_db()
        self.assertEqual((answer.score, answer.is_correct), (Decimal('2.00'), True))

    def test_05_open_attempt_untouched(self):
        open_attempt = VPAttempt.objects.create(variant=self.variant, public_code='rs-open')
        VPAnswer.objects.create(attempt=open_attempt,
                                item=self.variant.items.get(number=5), raw='термин пять')
        self.fix_key()
        run('--all')
        open_attempt.refresh_from_db()
        self.assertIsNone(open_attempt.score)
        self.assertIsNone(open_attempt.submitted_at)
        self.assertIsNone(self.answer(open_attempt, 5).score)

    def test_06_only_scores_change(self):
        before = VPAttempt.objects.values(
            'pk', 'submitted_at', 'is_auto_submitted', 'is_ranked', 'max_score',
            'public_code', 'started_at').order_by('pk')
        before = list(before)
        raws = list(VPAnswer.objects.order_by('pk').values_list('raw', flat=True))
        self.fix_key()
        run('--all')
        after = list(VPAttempt.objects.values(
            'pk', 'submitted_at', 'is_auto_submitted', 'is_ranked', 'max_score',
            'public_code', 'started_at').order_by('pk'))
        self.assertEqual(before, after)
        self.assertEqual(raws, list(VPAnswer.objects.order_by('pk').values_list('raw', flat=True)))

    def test_07_dry_run_writes_nothing(self):
        self.fix_key()
        out = run('--variant', 'vp-rs', '--dry-run')
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual((self.a.score, self.b.score), (Decimal('100.00'), Decimal('98.00')))
        self.assertEqual(self.answer(self.b, 5).score, Decimal('0.00'))
        self.assertIn('[dry-run', out)
        self.assertIn('Попыток изменено: 2 (балл вырос: 1, упал: 1)', out)
        self.assertIn('vp-rs №5: стало верно 1, стало неверно 1', out)

    def test_08_second_run_changes_nothing(self):
        self.fix_key()
        run('--all')
        out = run('--all')
        self.assertIn('Изменений нет', out)

    def test_09_variant_filter(self):
        other = make_full_variant('vp-rs-other')
        stale = answer_all(other, right=True)
        views._finalize(stale, auto=False)
        VPAttempt.objects.filter(pk=stale.pk).update(score=Decimal('1.00'))
        run('--variant', 'vp-rs')
        stale.refresh_from_db()
        self.assertEqual(stale.score, Decimal('1.00'))
        run('--all')
        stale.refresh_from_db()
        self.assertEqual(stale.score, Decimal('100.00'))

    def test_10_needs_explicit_scope(self):
        with self.assertRaises(CommandError):
            run()
        with self.assertRaises(CommandError):
            run('--all', '--variant', 'vp-rs')
        with self.assertRaises(CommandError):
            run('--variant', 'no-such-variant')
