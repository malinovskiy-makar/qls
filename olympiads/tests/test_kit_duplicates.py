"""Повторы комплектов пакета (`mark_olympiad_kit_duplicates`, ADR 0171).

Комплекты собираются в тестовой базе вручную: правило читает только
комплекты, их классы, позиции и тексты задач банка.
"""
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from olympiads.models import (
    OlympiadStage, OlympiadVariant, OlympiadVariantFile, OlympiadVariantGrade,
    OlympiadVariantItem, TrainingAttempt,
)
from problems.models import Problem

from .test_models import make_olympiad


def text(n):
    """Условие задачи № n. Разные n различаются числами — это другой вариант."""
    return ('На рынке товара спрос задан функцией Qd = {} - P, а предложение '
            'Qs = {} + 2P. Найдите равновесную цену и объём продаж, излишки '
            'потребителей и производителей.'.format(100 + n, 10 + n))


class DuplicatesMixin:

    def setUp(self):
        super().setUp()
        self.olympiad = make_olympiad('vs')
        self.final = OlympiadStage.objects.create(
            olympiad=self.olympiad, code='final', name='Заключительный')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.counter = 0

    def kit(self, key, texts, tour='', grades=(9,), season='2021/22',
            merit=0, official=True):
        """Комплект: каждое задание — СВОЯ задача банка (как после S4)."""
        variant = OlympiadVariant.objects.create(
            olympiad=self.olympiad, stage=self.final, kit_key=key,
            season=season, tour=tour)
        for grade in grades:
            OlympiadVariantGrade.objects.create(variant=variant, grade=grade)
        for order, n in enumerate(texts):
            self.counter += 1
            statement = n if isinstance(n, str) else text(n)
            problem = Problem.objects.create(title='з', statement=statement)
            OlympiadVariantItem.objects.create(
                variant=variant, problem=problem, order=order,
                ref_key='{}:{}'.format(key, order),
                has_solution=order < merit, has_answer=order < merit,
                has_criteria=order < merit)
        OlympiadVariantFile.objects.create(
            variant=variant, kind='условия', official=official,
            sha256='{:064d}'.format(variant.pk))
        return variant

    def run_cmd(self, *extra):
        out = StringIO()
        call_command('mark_olympiad_kit_duplicates', '--report-dir',
                     self.tmp.name, *extra, stdout=out)
        return out.getvalue()

    def state(self, variant):
        variant.refresh_from_db()
        target = variant.duplicate_of.kit_key if variant.duplicate_of else None
        return target, variant.duplicate_kind


class KitDuplicatesTests(DuplicatesMixin, TestCase):

    def test_source_copy_is_marked_source(self):
        a = self.kit('vs-2021-9-a', [1, 2, 3], merit=3)
        b = self.kit('vs-2021-9-b', [1, 2, 3])
        self.run_cmd('--apply')
        self.assertEqual(self.state(a), (None, ''))
        self.assertEqual(self.state(b), ('vs-2021-9-a', 'source'))

    def test_dry_run_writes_nothing(self):
        self.kit('vs-2021-9-a', [1, 2, 3], merit=3)
        b = self.kit('vs-2021-9-b', [1, 2, 3])
        out = self.run_cmd()
        self.assertIn('изменений: 1 (сухой прогон)', out)
        self.assertEqual(self.state(b), (None, ''))

    def test_combined_file_points_to_first_tour(self):
        t1 = self.kit('vs-2021-9-1', [1, 2], tour='1')
        t2 = self.kit('vs-2021-9-2', [3, 4], tour='2')
        c = self.kit('vs-2021-9-all', [1, 2, 3, 4])
        self.run_cmd('--apply')
        self.assertEqual(self.state(c), ('vs-2021-9-1', 'combined'))
        self.assertEqual(self.state(t1), (None, ''))
        self.assertEqual(self.state(t2), (None, ''))

    def test_different_grades_are_not_linked(self):
        nine = self.kit('vs-2021-9', [1, 2, 3], grades=(9,))
        eleven = self.kit('vs-2021-11', [1, 2, 3], grades=(11,))
        self.run_cmd('--apply')
        self.assertEqual(self.state(nine), (None, ''))
        self.assertEqual(self.state(eleven), (None, ''))

    def test_all_grades_kit_does_not_bridge_9_and_11(self):
        # «все классы» совместим и с 9, и с 11 — но 9 и 11 между собой нет.
        self.kit('vs-2021-all', [1, 2, 3], grades=(), merit=3)
        nine = self.kit('vs-2021-9', [1, 2, 3], grades=(9,), merit=2)
        eleven = self.kit('vs-2021-11', [1, 2, 3], grades=(11,))
        self.run_cmd('--apply')
        self.assertEqual(self.state(nine), ('vs-2021-all', 'source'))
        self.assertEqual(self.state(eleven), ('vs-2021-all', 'source'))
        self.assertNotEqual(self.state(eleven)[0], 'vs-2021-9')

    def test_different_seasons_are_not_linked(self):
        a = self.kit('vs-2021-9', [1, 2, 3], season='2021/22')
        b = self.kit('vs-2022-9', [1, 2, 3], season='2022/23')
        self.run_cmd('--apply')
        self.assertEqual(self.state(a), (None, ''))
        self.assertEqual(self.state(b), (None, ''))

    def test_sixty_percent_is_not_marked(self):
        a = self.kit('vs-2021-9-a', [1, 2, 3, 4, 5])
        b = self.kit('vs-2021-9-b', [1, 2, 3, 6, 7])
        self.run_cmd('--apply')
        self.assertEqual(self.state(a), (None, ''))
        self.assertEqual(self.state(b), (None, ''))

    def test_tour_kit_is_main_over_combined(self):
        # Сводный богаче разборами, но основным остаётся тур.
        t1 = self.kit('vs-2021-9-1', [1, 2], tour='1')
        self.kit('vs-2021-9-2', [3, 4], tour='2')
        c = self.kit('vs-2021-9-all', [1, 2, 3, 4], merit=4)
        self.run_cmd('--apply')
        self.assertEqual(self.state(t1), (None, ''))
        self.assertEqual(self.state(c), ('vs-2021-9-1', 'combined'))

    def test_chain_resolves_to_root(self):
        # Сводный указывает на первый тур, а тот сам — повтор тура из
        # другого источника. Ссылка обязана идти прямо на корень.
        t1a = self.kit('vs-2021-9-1a', [1, 2], tour='1')
        t1b = self.kit('vs-2021-9-1b', [1, 2], tour='1', merit=2)
        self.kit('vs-2021-9-2', [3, 4], tour='2')
        c = self.kit('vs-2021-9-all', [1, 2, 3, 4])
        self.run_cmd('--apply')
        self.assertEqual(self.state(t1a), ('vs-2021-9-1b', 'source'))
        self.assertEqual(self.state(t1b), (None, ''))
        self.assertEqual(self.state(c), ('vs-2021-9-1b', 'combined'))

    def test_second_run_changes_nothing(self):
        self.kit('vs-2021-9-1', [1, 2], tour='1')
        self.kit('vs-2021-9-2', [3, 4], tour='2')
        self.kit('vs-2021-9-all', [1, 2, 3, 4])
        self.kit('vs-2021-9-copy', [1, 2, 3, 4])
        first = self.run_cmd('--apply')
        self.assertNotIn('изменений: 0', first)
        second = self.run_cmd('--apply')
        self.assertIn('изменений: 0', second)

    def test_nothing_is_deleted_or_hidden(self):
        self.kit('vs-2021-9-1', [1, 2], tour='1')
        self.kit('vs-2021-9-2', [3, 4], tour='2')
        self.kit('vs-2021-9-all', [1, 2, 3, 4])
        self.kit('vs-2021-9-a', [5, 6, 7])
        self.kit('vs-2021-9-b', [5, 6, 7])

        def snapshot():
            return (OlympiadVariant.objects.count(),
                    OlympiadVariantItem.objects.count(),
                    OlympiadVariantFile.objects.count(),
                    Problem.objects.count(),
                    sorted(OlympiadVariant.objects.values_list('kit_key', 'visibility')))
        before = snapshot()
        out = self.run_cmd('--apply')
        self.assertIn('изменений: 2', out)
        self.assertEqual(snapshot(), before)

    def test_kit_with_attempts_is_not_touched(self):
        self.kit('vs-2021-9-a', [1, 2, 3], merit=3)
        b = self.kit('vs-2021-9-b', [1, 2, 3])
        TrainingAttempt.objects.create(variant=b, session_key='s')
        out = self.run_cmd('--apply')
        self.assertEqual(self.state(b), (None, ''))
        self.assertIn('Не тронуты (есть попытки): vs-2021-9-b', out)

    def hide(self, variant):
        OlympiadVariant.objects.filter(pk=variant.pk).update(
            visibility=OlympiadVariant.Visibility.HIDDEN)

    def test_hidden_kit_is_duplicate_never_main(self):
        # Скрытый богаче разборами, но основным становится видимый.
        a = self.kit('vs-2021-9-a', [1, 2, 3], merit=3)
        b = self.kit('vs-2021-9-b', [1, 2, 3])
        self.hide(a)
        self.run_cmd('--apply')
        self.assertEqual(self.state(a), ('vs-2021-9-b', 'source'))
        self.assertEqual(self.state(b), (None, ''))
        a.refresh_from_db()
        self.assertEqual(a.visibility, OlympiadVariant.Visibility.HIDDEN)

    def test_two_hidden_kits_are_not_linked(self):
        a = self.kit('vs-2021-9-a', [1, 2, 3])
        b = self.kit('vs-2021-9-b', [1, 2, 3])
        self.hide(a)
        self.hide(b)
        self.run_cmd('--apply')
        self.assertEqual(self.state(a), (None, ''))
        self.assertEqual(self.state(b), (None, ''))

    def test_main_has_wider_grades(self):
        # Узкий богаче разборами, но основным становится широкий: иначе у
        # 9 класса пропала бы клетка.
        wide = self.kit('vs-2021-9-11', [1, 2, 3], grades=(9, 10, 11))
        narrow = self.kit('vs-2021-10-11', [1, 2, 3], grades=(10, 11), merit=3)
        self.run_cmd('--apply')
        self.assertEqual(self.state(wide), (None, ''))
        self.assertEqual(self.state(narrow), ('vs-2021-9-11', 'source'))

    def test_overlapping_grades_are_not_linked(self):
        a = self.kit('vs-2021-9-10', [1, 2, 3], grades=(9, 10))
        b = self.kit('vs-2021-10-11', [1, 2, 3], grades=(10, 11))
        self.run_cmd('--apply')
        self.assertEqual(self.state(a), (None, ''))
        self.assertEqual(self.state(b), (None, ''))


SOLUTION = ('\n\n**Решение.** Приравняем спрос и предложение: 101 - P = 11 + 2P, '
            'откуда P = 30 и Q = 71. Излишек потребителей равен половине '
            'произведения 71 на 71, излишек производителей считается так же. '
            '**Ответ:** P = 30, Q = 71.')


class PrefixRuleTests(DuplicatesMixin, TestCase):
    """Поправка «короткий текст ≈ начало длинного» и её защита."""

    def pair(self, longer):
        self.kit('vs-2021-9-a', [1], merit=1)
        return self.kit('vs-2021-9-b', [longer])

    def test_doubled_statement_matches(self):
        b = self.pair(text(1) + '\n\n' + text(1).replace('товара', 'некоторого товара'))
        self.run_cmd('--apply')
        self.assertEqual(self.state(b), ('vs-2021-9-a', 'source'))

    def test_solution_inside_statement_matches(self):
        b = self.pair(text(1) + SOLUTION)
        self.run_cmd('--apply')
        self.assertEqual(self.state(b), ('vs-2021-9-a', 'source'))

    def test_replaced_number_in_head_does_not_match(self):
        b = self.pair(text(1).replace('Qs = 11', 'Qs = 15') + SOLUTION)
        self.run_cmd('--apply')
        self.assertEqual(self.state(b), (None, ''))

    def test_other_sign_in_head_does_not_match(self):
        b = self.pair(text(1).replace('101 - P', '101 + P') + SOLUTION)
        self.run_cmd('--apply')
        self.assertEqual(self.state(b), (None, ''))

    def test_short_text_gets_no_prefix_rule(self):
        short = 'Спрос задан функцией Qd = 50 - P, предложение Qs = 2P. Найдите цену.'
        self.kit('vs-2021-9-a', [short], merit=1)
        b = self.kit('vs-2021-9-b', [short + '\n\n' + short])
        self.run_cmd('--apply')
        self.assertEqual(self.state(b), (None, ''))
