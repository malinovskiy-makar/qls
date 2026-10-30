"""Механические починки задач пакета олимпиад (день 30.10, этапы Д1–Д5).

Задачи S4 собираются в тестовой базе с явными номерами не меньше
`bank_fix.S4_FIRST` — команды правят только их; прежняя задача банка —
номером ниже. Тексты задачи 59997 — как лежат в базе площадки.
"""
import tempfile
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from olympiads import bank_fix as bf
from olympiads.models import OlympiadStage, OlympiadVariant, OlympiadVariantItem
from problems.models import Hint, Problem, ProblemPart

from .test_models import make_olympiad

# Задача 59997 «Торговля с ограничениями» (ВсОШ 2025/26, 11 кл., 2 тур, № 6).
LEAD_59997 = (
    'В мире существуют две страны — Альфа и Бета. Они производят и потребляют '
    'два товара: $X$ и $Y$. Технологии стран различаются, кривые '
    'производственных возможностей задаются следующими уравнениями: для страны '
    'Альфа $X_A^2 + 2000Y_A = 1\\,200\\,000$, для страны Бета '
    '$X_B^2 + 400Y_B = 480\\,000$.\n\nПредпочтения потребителей в обеих странах '
    'одинаковые. Они потребляют товары строго комплектами в пропорции 1:1, то '
    'есть функция полезности имеет вид $U = \\min(X, Y)$.\n\nСчитайте, что во '
    'всех обменах цена товара $Y$ равна 1, а цена товара $X$ обозначается как '
    '$p$. При решении этой задачи численные значения цен и объемов можно '
    'округлять до первого знака после запятой.')
PARTS_59997 = [
    ('а', '(4 балла) Представим, что страны открывают границы и торгуют без '
          'ограничений, при этом цена устанавливается на уровне равновесия '
          'совершенной конкуренции. Найдите мировую цену $p^\\star$, объемы '
          'производства, потребления и экспорта (импорта) товара $X$ для каждой '
          'страны.'),
    ('б', '(4 балла) Правительство страны, ставшей импортером товара $X$, решает '
          'начать «торговую войну» с целью увеличить собственное производство '
          'этого товара. Для этого оно вводит потолок цены $\\overline{p}$ на '
          'импорт на уровне $0{,}9p^\\star$. Выиграют ли потребители в этой '
          'стране по сравнению со свободной торговлей?'),
    ('в', '(4 балла) Правительство решает опустить потолок цены еще ниже, до '
          'уровня $\\hat{p} = 2p^\\star/3$. Выиграют ли потребители '
          'страны-импортера товара $X$ по сравнению со свободной торговлей и с '
          'потолком $\\overline{p}$ теперь?'),
]
STATEMENT_59997 = LEAD_59997 + ''.join(
    '\n\n{}) {}'.format(label, text) for label, text in PARTS_59997)


class DayMixin:
    """Комплект, прежняя задача банка и конструктор задач S4."""

    command = ''

    def setUp(self):
        super().setUp()
        olympiad = make_olympiad('dd')
        stage = OlympiadStage.objects.create(olympiad=olympiad, code='final',
                                             name='Заключительный')
        self.variant = OlympiadVariant.objects.create(
            olympiad=olympiad, stage=stage, kit_key='dd-1', season='2025/26')
        self.next_id = bf.S4_FIRST + 100
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.legacy = self.add(STATEMENT_59997,
                               [(label, text, 4) for label, text in PARTS_59997] * 2,
                               pk=bf.S4_FIRST - 1, legacy=True)

    def add(self, statement, parts=(), *, pk=None, legacy=False, human='',
            **fields):
        if pk is None:
            pk = self.next_id
            self.next_id += 1
        problem = Problem.objects.create(
            pk=pk, title='з', statement=statement, status='draft',
            hidden_pending_review=True, human_review=human,
            content_format='plain' if legacy else 'markdown', **fields)
        for order, (label, text, points) in enumerate(parts):
            ProblemPart.objects.create(problem=problem, label=label, statement=text,
                                       points=points, order=order)
        OlympiadVariantItem.objects.create(
            variant=self.variant, problem=problem, order=pk,
            ref_key='dd-1:{}'.format(pk))
        return problem

    def run_cmd(self, *args, command=''):
        out = StringIO()
        call_command(command or self.command, '--report-dir', self.tmp.name,
                     '--no-snapshot', *args, stdout=out)
        return out.getvalue()

    def parts(self, problem):
        return list(problem.parts.order_by('order', 'id')
                    .values_list('label', 'statement', 'points'))

    def legacy_state(self):
        self.legacy.refresh_from_db()
        return (self.legacy.statement, self.legacy.updated_at, self.parts(self.legacy))


class DedupePartsTests(DayMixin, TestCase):
    """Д1: «а б в а б в» → «а б в»."""

    command = 'dedupe_problem_parts'

    def test_59997_keeps_three_parts_four_points_each(self):
        problem = self.add(STATEMENT_59997,
                           [(label, text, 4) for label, text in PARTS_59997] * 2)
        self.run_cmd('--apply')
        parts = self.parts(problem)
        self.assertEqual([p[0] for p in parts], ['а', 'б', 'в'])
        self.assertEqual({p[2] for p in parts}, {Decimal('4.00')})

    def test_same_label_with_other_text_is_flagged_not_removed(self):
        problem = self.add('Условие', [('а', 'первый вопрос', 4),
                                       ('а', 'другой вопрос', 4)])
        self.run_cmd('--apply')
        self.assertEqual(len(self.parts(problem)), 2)
        item = problem.olympiad_items.get()
        self.assertEqual(item.quality, 'flagged')
        self.assertTrue(item.quality_reasons)

    def test_same_text_with_other_points_is_not_a_copy(self):
        problem = self.add('Условие', [('а', 'вопрос', 4), ('а', 'вопрос', 2)])
        self.run_cmd('--apply')
        self.assertEqual(len(self.parts(problem)), 2)

    def test_link_to_removed_copy_moves_to_kept_part(self):
        problem = self.add('Условие', [('а', 'вопрос', 4), ('а', 'вопрос', 4)])
        kept, copy = problem.parts.order_by('order', 'id')
        hint = Hint.objects.create(problem=problem, part=copy, text='подсказка')
        self.run_cmd('--apply')
        hint.refresh_from_db()
        self.assertEqual(hint.part_id, kept.pk)

    def test_parts_shrink_exactly_by_copies(self):
        self.add(STATEMENT_59997, [(label, text, 4) for label, text in PARTS_59997] * 2)
        before = ProblemPart.objects.count()
        out = self.run_cmd('--apply')
        self.assertEqual(ProblemPart.objects.count(), before - 3)
        self.assertIn('копий удалено: 3', out)

    def test_legacy_and_reviewed_problems_are_never_changed(self):
        reviewed = self.add('Условие', [('а', 'вопрос', 4), ('а', 'вопрос', 4)],
                            human='approved')
        before = self.legacy_state()
        self.run_cmd('--apply')
        self.assertEqual(self.legacy_state(), before)
        self.assertEqual(len(self.parts(reviewed)), 2)

    def test_dry_run_and_second_run_change_nothing(self):
        problem = self.add(STATEMENT_59997,
                           [(label, text, 4) for label, text in PARTS_59997] * 2)
        self.add('Условие', [('а', 'первый вопрос', 4), ('а', 'другой вопрос', 4)])
        self.run_cmd()
        self.assertEqual(len(self.parts(problem)), 6)
        self.run_cmd('--apply')
        flags = list(OlympiadVariantItem.objects.order_by('pk')
                     .values_list('quality', 'quality_reasons', 'updated_at'))
        out = self.run_cmd('--apply')
        self.assertIn('копий удалено: 0', out)
        self.assertIn('Позиций с новой пометкой: 0', out)
        self.assertEqual(flags, list(OlympiadVariantItem.objects.order_by('pk')
                                     .values_list('quality', 'quality_reasons',
                                                  'updated_at')))


class SplitStatementTests(DayMixin, TestCase):
    """Д2: условие = общая часть до первого пункта, если хвост — ровно пункты."""

    command = 'split_statement_parts'

    def parts_59997(self):
        return [(label, text, 4) for label, text in PARTS_59997]

    def test_59997_statement_ends_before_first_part(self):
        problem = self.add(STATEMENT_59997, self.parts_59997())
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, LEAD_59997)
        self.assertTrue(problem.statement.endswith('до первого знака после запятой.'))

    def test_cut_tail_is_exactly_the_parts(self):
        from olympiads import parts_fix as pf
        problem = self.add(STATEMENT_59997, self.parts_59997())
        self.run_cmd('--apply')
        problem.refresh_from_db()
        tail = STATEMENT_59997[len(problem.statement):]
        rows = list(problem.parts.order_by('order', 'id').values(
            'label', 'statement', 'points'))
        self.assertTrue(pf.tail_is_parts(tail, rows))

    def test_bold_labels_and_points_mark_only_in_statement(self):
        statement = (LEAD_59997 + '\n\n**а)** (4 балла) первый вопрос задачи'
                     '\n\n**б)** (4 балла) второй вопрос задачи')
        problem = self.add(statement, [('а', 'первый вопрос задачи', 4),
                                       ('б', 'второй вопрос задачи', 4)])
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, LEAD_59997)

    def test_points_mark_with_other_points_is_not_dropped(self):
        statement = LEAD_59997 + '\n\nа) (5 баллов) первый вопрос задачи'
        problem = self.add(statement, [('а', 'первый вопрос задачи', 4)])
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, statement)

    def test_extra_paragraph_in_tail_is_flagged_not_cut(self):
        statement = STATEMENT_59997 + '\n\nОтвет: 12.'
        problem = self.add(statement, self.parts_59997())
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, statement)
        self.assertIn('пункты в условии не совпали с пунктами задачи',
                      problem.olympiad_items.get().quality_reasons)

    def test_parts_in_other_order_are_flagged_not_cut(self):
        parts = self.parts_59997()
        problem = self.add(STATEMENT_59997, [parts[1], parts[0], parts[2]])
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, STATEMENT_59997)
        self.assertEqual(problem.olympiad_items.get().quality, 'flagged')

    def test_trailing_semicolon_of_option_is_not_lost(self):
        statement = 'Что такое ипотека?\n\nA. Залог недвижимости;\nB. Ценная бумага.'
        problem = self.add(statement, [('a', 'Залог недвижимости', None),
                                       ('b', 'Ценная бумага', None)])
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, statement)

    def test_latin_capital_labels_match(self):
        statement = 'Что такое ипотека?\n\nA. Залог недвижимости\nB. Ценная бумага'
        problem = self.add(statement, [('a', 'Залог недвижимости', None),
                                       ('b', 'Ценная бумага', None)])
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, 'Что такое ипотека?')

    def test_legacy_untouched_and_second_run_changes_nothing(self):
        before = self.legacy_state()
        self.add(STATEMENT_59997, self.parts_59997())
        self.add(STATEMENT_59997 + '\n\nОтвет: 12.', self.parts_59997())
        self.run_cmd('--apply')
        self.assertEqual(self.legacy_state(), before)
        state = list(Problem.objects.order_by('pk').values_list('statement', 'updated_at'))
        out = self.run_cmd('--apply')
        self.assertIn('Условий укорочено: 0', out)
        self.assertIn('Позиций с новой пометкой: 0', out)
        self.assertEqual(state, list(Problem.objects.order_by('pk')
                                     .values_list('statement', 'updated_at')))

    def test_parts_twice_in_statement_are_cut_in_one_run(self):
        statement = STATEMENT_59997 + ''.join(
            '\n\n{}) {}'.format(label, text) for label, text in PARTS_59997)
        problem = self.add(statement, self.parts_59997())
        self.run_cmd('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, LEAD_59997)
        out = self.run_cmd('--apply')
        self.assertIn('Условий укорочено: 0', out)


class StripPointsTests(DayMixin, TestCase):
    """Д3: «(4 балла)» в начале текста пункта."""

    command = 'strip_part_points'

    def test_59997_parts_start_with_words(self):
        problem = self.add(LEAD_59997, [(label, text, 4) for label, text in PARTS_59997])
        self.run_cmd('--apply')
        texts = [p[1] for p in self.parts(problem)]
        self.assertTrue(texts[0].startswith('Представим'))
        self.assertTrue(texts[1].startswith('Правительство'))
        self.assertEqual({p[2] for p in self.parts(problem)}, {Decimal('4.00')})

    def test_empty_points_are_filled_from_mark(self):
        problem = self.add('Условие', [('а', '(3 балла) Найдите цену.', None)])
        out = self.run_cmd('--apply')
        self.assertEqual(self.parts(problem), [('а', 'Найдите цену.', Decimal('3.00'))])
        self.assertIn('баллы заполнены из пометки: 1', out)

    def test_other_points_are_flagged_not_changed(self):
        problem = self.add('Условие', [('а', '(3 балла) Найдите цену.', 4)])
        self.run_cmd('--apply')
        self.assertEqual(self.parts(problem), [('а', '(3 балла) Найдите цену.', Decimal('4.00'))])
        self.assertEqual(problem.olympiad_items.get().quality, 'flagged')

    def test_mark_inside_bold_is_flagged_not_changed(self):
        text = '**(4 балла) Найдите цену.**'
        problem = self.add('Условие', [('а', text, 4)])
        self.run_cmd('--apply')
        self.assertEqual(self.parts(problem)[0][1], text)

    def test_legacy_untouched_and_second_run_changes_nothing(self):
        before = self.legacy_state()
        self.add(LEAD_59997, [(label, text, 4) for label, text in PARTS_59997])
        self.run_cmd('--apply')
        self.assertEqual(self.legacy_state(), before)
        out = self.run_cmd('--apply')
        self.assertIn('Пометок убрано: 0', out)
