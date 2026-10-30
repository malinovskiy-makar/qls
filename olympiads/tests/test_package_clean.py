"""Чистка задач пакета олимпиад (`clean_olympiad_package_tasks`, ADR 0172).

Задачи собираются в тестовой базе вручную: правило читает условие и решение
задачи, пункты и позиции комплектов. Прежняя задача банка — раньше по номеру
и 'plain'; задача S4 — draft, скрыта, ревью пустое, 'markdown'.
"""
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from olympiads import package_clean as pc
from olympiads.models import OlympiadStage, OlympiadVariant, OlympiadVariantItem
from problems.models import Problem

from .package_clean_fixtures import (STATEMENT_58804, STATEMENT_59676,
                                     STATEMENT_59745, STATEMENT_60655)
from .test_models import make_olympiad

# Условие достаточной длины: короткие тексты правила не применяют.
BASE = ('Фирма на монопольном рынке производит {q} единиц продукции, при этом '
        'ценовая эластичность спроса при текущем объёме производства равна {e}. '
        'Известно, что функция спроса линейна, а цена падает на {d} денежные '
        'единицы при увеличении величины спроса на одну единицу. Чему равна '
        'цена на рынке?')
STATEMENT = BASE.format(q=200, e=-3, d=2)
STATEMENT_2 = ('Фирма на монопольном рынке выпускает {q} единиц продукции, при '
               'этом ценовая эластичность спроса при текущем объёме производства '
               'равна {e}. Известно, что функция спроса линейна, а цена падает '
               'на {d} денежные единицы при увеличении величины спроса на одну '
               'единицу. Чему равна цена на рынке?').format(q=200, e=-3, d=2)
CRITERIA = '## Критерии оценивания\n\nВерная цена — 3 балла.'
REAL_SOLUTION = ('Воспользуемся формулой точечной эластичности спроса по цене, '
                 'подставим известные значения и получим цену 1200.')


class CleanMixin:

    def setUp(self):
        super().setUp()
        olympiad = make_olympiad('cl')
        stage = OlympiadStage.objects.create(olympiad=olympiad, code='final',
                                             name='Заключительный')
        self.variant = OlympiadVariant.objects.create(
            olympiad=olympiad, stage=stage, kit_key='cl-1', season='2021/22')
        self.counter = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Прежняя задача банка (номер ниже всех S4): отпечаток сверяет её.
        self.legacy = self.add(STATEMENT + '\n\n' + STATEMENT_2, '', legacy=True)[0]

    def add(self, statement, solution='', *, legacy=False, human='',
            has_solution=False, has_criteria=False):
        self.counter += 1
        problem = Problem.objects.create(
            title='з', statement=statement, solution=solution,
            status='draft', hidden_pending_review=True, human_review=human,
            content_format='plain' if legacy else 'markdown')
        item = OlympiadVariantItem.objects.create(
            variant=self.variant, problem=problem, order=self.counter,
            ref_key='cl-1:{}'.format(self.counter),
            has_solution=has_solution, has_criteria=has_criteria)
        return problem, item

    def run_cmd(self, *args):
        out = StringIO()
        call_command('clean_olympiad_package_tasks', '--report-dir', self.tmp.name,
                     '--no-snapshot', *args, stdout=out)
        return out.getvalue()

    def reload(self, problem):
        problem.refresh_from_db()
        return problem


class DoubledStatementTests(CleanMixin, TestCase):

    def test_doubling_with_same_numbers_keeps_first_half(self):
        problem, item = self.add(STATEMENT + '\n\n' + STATEMENT_2)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, STATEMENT)
        item.refresh_from_db()
        self.assertEqual(item.quality, 'clean')

    def test_doubling_with_different_numbers_is_flagged_not_changed(self):
        text = STATEMENT + '\n\n' + BASE.format(q=250, e=-3, d=2)
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        item.refresh_from_db()
        self.assertEqual(item.quality, 'flagged')
        self.assertIn(pc.REASON_DOUBLED, item.quality_reasons)

    def test_doubling_with_different_sign_is_flagged(self):
        text = STATEMENT + '\n\n' + BASE.format(q=200, e='+3', d=2)
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        self.assertIn(pc.REASON_DOUBLED, OlympiadVariantItem.objects.get(pk=item.pk)
                      .quality_reasons)


class AnswerInsideStatementTests(CleanMixin, TestCase):
    BODY = STATEMENT

    def test_answer_label_at_line_start_is_cut(self):
        problem, _item = self.add(self.BODY + '\n\nОтвет: 1200.')
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, self.BODY)

    def test_word_decision_inside_phrase_is_not_a_label(self):
        text = self.BODY + '\n\nРешение фирмы о выпуске зависит от предельных издержек.'
        problem, _item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)

    def test_cut_becomes_solution_when_there_was_none(self):
        problem, item = self.add(self.BODY + '\n\nОтвет: 1200.\nПодставим числа в формулу.',
                                 CRITERIA, has_criteria=True)
        self.run_cmd('--apply')
        problem = self.reload(problem)
        self.assertEqual(problem.statement, self.BODY)
        self.assertTrue(problem.solution.startswith('Ответ: 1200.'))
        self.assertTrue(problem.solution.endswith(CRITERIA))
        item.refresh_from_db()
        self.assertTrue(item.has_solution)
        self.assertTrue(item.has_criteria)

    def test_cut_does_not_overwrite_real_solution(self):
        problem, _item = self.add(self.BODY + '\n\nОтвет: 1200.', REAL_SOLUTION)
        out = self.run_cmd('--apply')
        problem = self.reload(problem)
        self.assertEqual(problem.statement, self.BODY)
        self.assertEqual(problem.solution, REAL_SOLUTION)
        self.assertIn('отрезанное только в отчёт 1', out)

    def test_new_part_after_label_is_flagged_not_cut(self):
        text = (self.BODY + '\n\nа) Найдите цену.\n\nОтвет: 1200.\n\n'
                'в) Найдите излишек потребителя при этой цене.')
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        item.refresh_from_db()
        self.assertIn(pc.REASON_ANSWER, item.quality_reasons)


class SolutionCopyTests(CleanMixin, TestCase):

    def test_copy_of_statement_removed_criteria_kept(self):
        problem, _item = self.add(STATEMENT, STATEMENT + '\n\n' + CRITERIA,
                                  has_solution=True, has_criteria=True)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).solution, CRITERIA)

    def test_has_solution_flag_dropped_where_solution_was_a_copy(self):
        problem, item = self.add(STATEMENT, STATEMENT + '\n\n' + CRITERIA,
                                 has_solution=True, has_criteria=True)
        self.run_cmd('--apply')
        item.refresh_from_db()
        self.assertFalse(item.has_solution)
        self.assertTrue(item.has_criteria)

    def test_copy_without_criteria_leaves_empty_solution(self):
        problem, item = self.add(STATEMENT, STATEMENT, has_solution=True)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).solution, '')
        item.refresh_from_db()
        self.assertFalse(item.has_solution)


class AnswerMarkTests(CleanMixin, TestCase):
    """«(отмечено)» у варианта теста — это ответ: терять его нельзя."""
    TEST = ('Выберите верные утверждения о монополии на рынке товара с высокими '
            'барьерами входа.\n\n1) монополист назначает цену выше предельных издержек\n'
            '2) монополист всегда получает положительную прибыль\n'
            '3) спрос на продукцию монополиста убывает по цене')

    def test_copy_with_marked_options_is_flagged_not_removed(self):
        marked = self.TEST.replace('3) спрос', '3) (отмечено) спрос')
        problem, item = self.add(self.TEST, marked, has_solution=True)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).solution, marked)
        item.refresh_from_db()
        self.assertTrue(item.has_solution)
        self.assertIn(pc.REASON_COPY_EXTRA, item.quality_reasons)

    def test_doubling_keeps_the_edition_with_marks_even_if_second(self):
        marked = self.TEST.replace('3) спрос', '3) (отмечено) спрос')
        problem, _item = self.add(self.TEST + '\n\n' + marked)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, marked)


    def test_doubling_where_first_half_keeps_the_marks_is_fixed(self):
        marked = self.TEST.replace('3) спрос', '3) (отмечено) спрос')
        problem, _item = self.add(marked + '\n\n' + self.TEST)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, marked)


class BoundaryTests(CleanMixin, TestCase):

    def test_legacy_problem_is_never_changed(self):
        before = (self.legacy.statement, self.legacy.solution,
                  self.legacy.updated_at)
        out = self.run_cmd('--apply')
        self.legacy.refresh_from_db()
        self.assertEqual((self.legacy.statement, self.legacy.solution,
                          self.legacy.updated_at), before)
        self.assertIn('прежних задач с находкой (не тронуты): 1', out)

    def test_problem_with_human_review_is_never_changed(self):
        text = STATEMENT + '\n\nОтвет: 1200.'
        problem, _item = self.add(text, human='approved')
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)

    def test_dry_run_changes_nothing(self):
        text = STATEMENT + '\n\n' + STATEMENT_2
        problem, _item = self.add(text)
        self.run_cmd()
        self.assertEqual(self.reload(problem).statement, text)

    def test_second_run_changes_nothing(self):
        self.add(STATEMENT + '\n\n' + STATEMENT_2)
        self.add(STATEMENT + '\n\nОтвет: 1200.', REAL_SOLUTION)
        self.add(STATEMENT, STATEMENT + '\n\n' + CRITERIA)
        self.add(STATEMENT + '\n\n' + BASE.format(q=250, e=-3, d=2))
        self.run_cmd('--apply')
        state = list(Problem.objects.order_by('id').values_list('statement', 'solution'))
        flags = list(OlympiadVariantItem.objects.order_by('pk').values_list(
            'quality', 'quality_reasons', 'has_solution', 'has_criteria'))
        out = self.run_cmd('--apply')
        self.assertIn('задач с правкой текста: 0; позиций с правкой: 0', out)
        self.assertEqual(state, list(Problem.objects.order_by('id')
                                     .values_list('statement', 'solution')))
        self.assertEqual(flags, list(OlympiadVariantItem.objects.order_by('pk')
                                     .values_list('quality', 'quality_reasons',
                                                  'has_solution', 'has_criteria')))


class FigureMarkerTests(CleanMixin, TestCase):

    def test_marker_of_removed_half_survives(self):
        marker = '[[FIGURE:' + 'ab' * 8 + ']]'
        problem, _item = self.add(STATEMENT + '\n\n' + STATEMENT_2 + '\n\n' + marker)
        self.run_cmd('--apply')
        self.assertIn(marker, self.reload(problem).statement)

    def test_marker_after_answer_label_survives(self):
        marker = '[[FIGURE:' + 'cd' * 8 + ']]'
        problem, _item = self.add(STATEMENT + '\n\nОтвет: 1200.\n\n' + marker)
        self.run_cmd('--apply')
        statement = self.reload(problem).statement
        self.assertIn(marker, statement)
        self.assertNotIn('Ответ', statement)


TASK = ('Фирма производит {q} единиц продукции на конкурентном рынке. Функция '
        'общих издержек фирмы TC = Q^2 + 20Q + 100, рыночная цена равна 140. '
        'Найдите оптимальный объём выпуска и прибыль фирмы, объясните, почему '
        'именно такой выпуск максимизирует прибыль.')
REASONING = ('Так как фирма действует на конкурентном рынке, она выбирает объём из '
             'условия P = MC.\nСледовательно, 140 = 2Q + 20, откуда Q = 60. (2 балла)\n'
             'Итак, прибыль равна 140 * 60 - TC(60) = 8400 - 4900 = 3500. (1 балл)\n'
             'Подставим числа и проверим: 3500 > 0, фирма получает прибыль.\n'
             'Выразим то же через средние издержки: AC(60) = 60 + 20 + 100/60, '
             'то есть примерно 81,7, а цена 140 выше, поэтому прибыль положительна.')


class FullerEditionTests(CleanMixin, TestCase):

    def test_points_are_not_numbers_and_edition_with_points_is_kept(self):
        plain = TASK.format(q=60)
        with_points = plain + ' (4 балла)'
        problem, item = self.add(plain + '\n\n' + with_points)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, with_points)
        item.refresh_from_db()
        self.assertEqual(item.quality, 'clean')

    def test_removed_edition_must_match_the_start(self):
        intro = 'Рассмотрим рынок одного товара в краткосрочном периоде.'
        text = intro + '\n\n' + TASK.format(q=60) + '\n\n' + TASK.format(q=60)
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        item.refresh_from_db()
        self.assertIn(pc.REASON_SEVERAL, item.quality_reasons)

    def test_duplicated_list_only_is_removed(self):
        head = 'Фирма выбирает форму организации бизнеса, варианты таковы:'
        items = ('- **Малое предприятие**: выпуск не превышает 10 единиц, фирма не '
                 'несёт налоговой нагрузки, но ограничена в найме работников.\n'
                 '- **Крупное предприятие**: выпуск превышает 10 единиц, фирма платит '
                 'налог на прибыль и может нанимать любое число работников.')
        problem, _item = self.add(head + '\n' + items + '\n\n' + items)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, head + '\n' + items)

    def test_footnote_stays_with_kept_edition(self):
        base = TASK.format(q=60).replace('конкурентном', 'конкурентном$^1$')
        note = '$^1$ Конкурентный рынок — рынок, где фирма не влияет на цену.'
        other = (TASK.format(q=60).replace('конкурентном', 'конкурентном$^1$')
                 + '\n\n¹ Конкурентный рынок — рынок, где фирма не влияет на цену.')
        problem, _item = self.add(base + '\n\n' + note + '\n\n' + other)
        self.run_cmd('--apply')
        statement = self.reload(problem).statement
        self.assertIn(note, statement)
        self.assertEqual(statement.count('конкурентном$^1$'), 1)


class ResidualSolutionTests(CleanMixin, TestCase):

    def test_solution_before_the_label_is_flagged_and_nothing_is_cut(self):
        text = TASK.format(q=60) + '\n\n' + REASONING + '\nОтвет: Q = 60, прибыль 3500.'
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        item.refresh_from_db()
        self.assertIn(pc.REASON_RESIDUAL, item.quality_reasons)

    def test_solution_without_label_is_flagged_too(self):
        text = TASK.format(q=60) + '\n\n' + REASONING
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        self.assertIn(pc.REASON_RESIDUAL, OlympiadVariantItem.objects.get(
            pk=item.pk).quality_reasons)

    def test_plain_statement_with_points_per_part_is_not_flagged(self):
        text = (TASK.format(q=60) + '\n\nа) Найдите выпуск. (2 балла)\n'
                'б) Найдите прибыль фирмы при этом выпуске. (3 балла)')
        problem, item = self.add(text)
        self.run_cmd('--apply')
        item.refresh_from_db()
        self.assertNotIn(pc.REASON_RESIDUAL, item.quality_reasons)


class BlankFormTests(CleanMixin, TestCase):

    def test_blank_answer_goes_to_report_not_to_solution(self):
        text = TASK.format(q=60) + '\n\nОтвет: ____________ (комментарий)'
        problem, _item = self.add(text)
        self.run_cmd('--apply')
        problem = self.reload(problem)
        self.assertEqual(problem.statement, TASK.format(q=60))
        self.assertEqual(problem.solution, '')

    def test_blank_with_doubled_variants_is_flagged_as_a_whole(self):
        variants = ('- А) первое\n- В) второе\n- С) третье\n- D) четвёртое')
        text = (TASK.format(q=60) + '\n\n' + variants + '\n\n' + variants
                + '\n\nОтвет: ____________ (комментарий)')
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        self.assertIn(pc.REASON_MESS, OlympiadVariantItem.objects.get(
            pk=item.pk).quality_reasons)


class OrphanTests(CleanMixin, TestCase):

    def test_cut_text_absent_from_solution_is_flagged(self):
        extra = ' '.join('Вариант объяснения номер {} опирается на другие допущения '
                         'о поведении потребителей и издержках.'.format(i)
                         for i in range(1, 6))
        problem, item = self.add(TASK.format(q=60) + '\n\nОтвет: 60.\n' + extra, '60')
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, TASK.format(q=60))
        self.assertIn(pc.REASON_ORPHAN, OlympiadVariantItem.objects.get(
            pk=item.pk).quality_reasons)


class FinalChecksTests(CleanMixin, TestCase):
    """Четыре проверки итогового условия после правки A или B (ADR 0172, п. 4)."""

    def flagged_unchanged(self, statement, reason):
        problem, item = self.add(statement)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, statement)
        item.refresh_from_db()
        self.assertEqual(item.quality, 'flagged')
        self.assertIn(reason, item.quality_reasons)

    def test_start_repeated_below_is_flagged_not_changed(self):
        self.flagged_unchanged(STATEMENT_59676, pc.REASON_TWICE)

    def test_grading_text_in_statement_is_flagged_not_changed(self):
        self.flagged_unchanged(STATEMENT_58804, pc.REASON_CRITERIA)

    def test_voice_of_solution_in_last_600_chars_is_flagged_not_cut(self):
        self.flagged_unchanged(STATEMENT_59745, pc.REASON_RESIDUAL)

    def test_grading_comment_after_cut_is_flagged_not_cut(self):
        self.flagged_unchanged(STATEMENT_60655, pc.REASON_CRITERIA)

    def test_alien_tail_of_kept_edition_is_flagged(self):
        plain = TASK.format(q=60)
        alien = 'Отдельно проанализируйте рынок автомобилей в стране Бета подробно.'
        self.assertEqual(pc.final_checks(plain + '\n\n' + alien, plain), [pc.REASON_ALIEN])

    def test_no_alien_tail_when_it_is_in_the_removed_edition(self):
        plain = TASK.format(q=60)
        note = 'Отдельно проанализируйте рынок автомобилей в стране Бета подробно.'
        self.assertEqual(pc.final_checks(plain + '\n\n' + note, plain + '\n\n' + note), [])

    def test_alien_check_is_only_for_edition_choice(self):
        plain = TASK.format(q=60)
        alien = 'Отдельно проанализируйте рынок автомобилей в стране Бета подробно.'
        self.assertEqual(pc.final_checks(plain + '\n\n' + alien), [])

    def test_result_tail_with_equals_and_no_question_is_flagged(self):
        text = TASK.format(q=60) + '\n\nU = 10\n\nОтвет: 60.'
        problem, item = self.add(text)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, text)
        self.assertIn(pc.REASON_RESIDUAL, OlympiadVariantItem.objects.get(
            pk=item.pk).quality_reasons)

    def test_footnote_is_restored_from_removed_edition(self):
        kept = TASK.format(q=60).replace('конкурентном', 'конкурентном$^1$')
        removed = kept + '\n\n$^1$ Конкурентный рынок — рынок, где фирма не влияет на цену.'
        self.assertIn('$^1$ Конкурентный', pc.restore_footnotes(kept, removed))


class BallsAndBrokenWordsTests(CleanMixin, TestCase):

    def test_edition_with_points_wins_when_text_otherwise_equal(self):
        plain = TASK.format(q=60) + '\n\nа) Найдите выпуск.\nб) Найдите прибыль.'
        points = TASK.format(q=60) + '\n\nа) Найдите выпуск. (2 балла)\nб) Найдите прибыль. (3 балла)'
        problem, _item = self.add(plain + '\n\n' + points)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, points)

    def test_broken_words_in_kept_edition_are_flagged(self):
        good = TASK.format(q=60)
        broken = good.replace('Объясните', 'Объяс ните').replace('максимизирует', 'максими зирует')
        problem, item = self.add(broken + ' (4 балла)\n\n' + good)
        self.run_cmd('--apply')
        self.assertEqual(self.reload(problem).statement, broken + ' (4 балла)\n\n' + good)
        item.refresh_from_db()
        self.assertIn(pc.REASON_BROKEN, item.quality_reasons)
