# -*- coding: utf-8 -*-
"""Пилот обогащения v2 (Б2): выборка, смета, гейт --apply/--max-cost.

Зубастость по списку Б5: шорт-лист сюда не входит (свой файл), но
стратификация обязана быть детерминированной сидом, `--max-cost` обязан
считать по ФАКТИЧЕСКОМУ usage (а не по смете), без `--apply` не должно
уходить ни одного обращения к API, а верхние границы массивов (1–5 тегов,
ровно 8 запросов...) проверяются в Python, а не схемой.
"""
import io
import re
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, text as enrich_text
from problems.enrich.shortlist import load_df_cache, shortlist_for
from problems.management.commands import pilot_enrich_v2 as cmd
from problems.models import Problem, Topic

PRICES = {
    cmd.TERRA: (2.00, 0.20, 12.00),
    cmd.LUNA: (0.20, 0.02, 1.20),
}


def _make_topic(name):
    topic, _ = Topic.objects.get_or_create(name=name, defaults={'slug': name[:50]})
    return topic


def _make_problem(statement='Условие задачи про рынок.', topics=(),
                  human_review='', solution='', answer=''):
    problem = Problem.objects.create(
        statement=statement, human_review=human_review,
        solution=solution, answer=answer)
    for name in topics:
        problem.topics.add(_make_topic(name))
    return problem


@override_settings(AI_PRICES=PRICES)
class SamplingTests(TestCase):

    def setUp(self):
        for i in range(30):
            _make_problem('Микро задача %d про монополию.' % i,
                          topics=[cmd.MICRO_TOPICS[0]])
        for i in range(10):
            _make_problem('Макро задача %d про ВВП.' % i,
                          topics=[cmd.MACRO_TOPICS[0]])
        for i in range(5):
            _make_problem('An English-language problem number %d about supply and demand.' % i)
        for i in range(5):
            _make_problem('Сломанная задача %d.' % i,
                          human_review=Problem.HumanReview.DEFECT)

    def test_детерминирован_один_и_тот_же_seed(self):
        first, _ = cmd.build_sample(20, seed=111)
        second, _ = cmd.build_sample(20, seed=111)
        self.assertEqual(first, second)

    def test_разные_seed_обычно_дают_разную_выборку(self):
        first, _ = cmd.build_sample(15, seed=1)
        second, _ = cmd.build_sample(15, seed=2)
        self.assertNotEqual(first, second)

    def test_ни_одна_задача_не_попадает_в_две_страты(self):
        sample_ids, _ = cmd.build_sample(cmd.STRATA_TOTAL, seed=cmd.SEED_DEFAULT)
        self.assertEqual(len(sample_ids), len(set(sample_ids)))

    def test_дефект_страта_берёт_только_human_review_defect(self):
        sample_ids, _ = cmd.build_sample(cmd.STRATA_TOTAL, seed=1)
        defect_ids = set(Problem.objects.filter(
            human_review=Problem.HumanReview.DEFECT).values_list('id', flat=True))
        # Все задачи со статусом DEFECT в этом фикстур-наборе малочисленны
        # (5), их страта просит 20 — значит все 5 должны попасть в выборку.
        self.assertTrue(defect_ids.issubset(set(sample_ids)))

    def test_недостаточно_кандидатов_не_падает_а_берёт_сколько_есть(self):
        # В фикстуре только 5 сломанных задач при страте на 20 — не ошибка.
        sample_ids, report = cmd.build_sample(cmd.STRATA_TOTAL, seed=1)
        self.assertTrue(any('заведомо сломанные: нужно 20' in line
                            for line in report))
        self.assertTrue(any('взято 5' in line for line in report
                            if 'сломанные' in line))


@override_settings(AI_PRICES=PRICES)
class VisualStrataTests(TestCase):
    """Фаза 6.1: страты «с фигурой/маркером» и «с таблицей»."""

    def setUp(self):
        _make_problem('Обычная задача про рынок труда без визуала.')
        self.marker_problem = _make_problem(
            'На рисунке ниже [[FIGURE:abc]] показан спрос на товар.')
        self.tikz_problem = _make_problem(
            r'Постройте график: \begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}')
        self.table_problem = _make_problem(
            r'Дана таблица издержек: \begin{tabular}{cc}1 & 2\end{tabular}')
        self.md_table_problem = _make_problem(
            'Цены по годам:\n| Год | Цена |\n| 2020 | 10 |')

    def test_маркер_и_tikz_попадают_в_страту_figure(self):
        sample_ids, _ = cmd.build_sample(cmd.STRATA_TOTAL, seed=1)
        self.assertIn(self.marker_problem.id, sample_ids)
        self.assertIn(self.tikz_problem.id, sample_ids)

    def test_tabular_и_markdown_попадают_в_страту_table(self):
        sample_ids, _ = cmd.build_sample(cmd.STRATA_TOTAL, seed=1)
        self.assertIn(self.table_problem.id, sample_ids)
        self.assertIn(self.md_table_problem.id, sample_ids)

    def test_problem_figure_попадает_в_страту_figure_без_маркера(self):
        problem = _make_problem('Условие без единого маркера визуала.')
        problem.figures.create(tikz_hash='a' * 64, tikz_source='src')
        sample_ids, _ = cmd.build_sample(cmd.STRATA_TOTAL, seed=1)
        self.assertIn(problem.id, sample_ids)

    def test_страты_видны_в_отчёте(self):
        _, report = cmd.build_sample(cmd.STRATA_TOTAL, seed=1)
        self.assertTrue(any('с фигурой/маркером' in line for line in report))
        self.assertTrue(any('с таблицей' in line for line in report))


class ScaleStrataTests(TestCase):

    def test_сумма_страт_совпадает_с_limit(self):
        for limit in (30, 150, 300, 600, 900):
            scaled = cmd.scale_strata(limit)
            self.assertEqual(sum(t for _, t, _ in scaled), limit)

    def test_дефолтный_limit_даёт_исходные_страты(self):
        scaled = cmd.scale_strata(cmd.STRATA_TOTAL)
        self.assertEqual(scaled, cmd.STRATA)

    def test_малый_limit_не_обнуляет_страты(self):
        # Регресс: раньше round() и вычитание остатка из «самой большой»
        # страты могли обнулить страту (limit=9 обнулял «микро» — 9 страт
        # ровно по 1 требуют суммы 9, а старый код давал микро=0).
        for limit in (9, 10, 15, 20, 25):
            scaled = cmd.scale_strata(limit)
            self.assertEqual(sum(t for _, t, _ in scaled), limit)
            self.assertTrue(all(t >= 1 for _, t, _ in scaled),
                            (limit, scaled))

    def test_limit_меньше_числа_страт_даёт_по_одной_на_крупнейшие(self):
        scaled = cmd.scale_strata(5)
        self.assertEqual(sum(t for _, t, _ in scaled), 5)
        self.assertEqual(sorted(t for _, t, _ in scaled),
                         [0] * (len(cmd.STRATA) - 5) + [1] * 5)

    def test_limit_ноль(self):
        scaled = cmd.scale_strata(0)
        self.assertEqual(sum(t for _, t, _ in scaled), 0)


class ValidateCall1Tests(TestCase):

    def _base(self, **overrides):
        data = {
            'topic_primary': 'X', 'topics_secondary': [], 'tags': ['a'],
            'given': 'Дано', 'find': 'Найти', 'econ_concepts': ['a', 'b', 'c'],
            'concepts_offlist': [], 'task_nature': 'расчётная',
            'features_1': [], 'topic_confidence': 'высокая',
        }
        data.update(overrides)
        return data

    def test_валидный_ответ_проходит(self):
        ok, violations = cmd.validate_call1(self._base())
        self.assertTrue(ok, violations)

    def test_слишком_много_тегов(self):
        ok, violations = cmd.validate_call1(self._base(tags=['a'] * 6))
        self.assertFalse(ok)
        self.assertTrue(any('tags' in v for v in violations))

    def test_ноль_тегов_не_проходит(self):
        ok, violations = cmd.validate_call1(self._base(tags=[]))
        self.assertFalse(ok)

    def test_мало_понятий(self):
        ok, violations = cmd.validate_call1(self._base(econ_concepts=['a']))
        self.assertFalse(ok)
        self.assertTrue(any('econ_concepts' in v for v in violations))

    def test_много_дополнительных_тем(self):
        ok, violations = cmd.validate_call1(
            self._base(topics_secondary=['A', 'B', 'C']))
        self.assertFalse(ok)

    def test_без_понятий_econ_concepts_не_проверяется(self):
        data = self._base()
        del data['econ_concepts']
        del data['concepts_offlist']
        ok, violations = cmd.validate_call1(data, with_concepts=False)
        self.assertTrue(ok, violations)

    def test_пустые_econ_concepts_законны_для_не_задачи(self):
        # Регресс со смок-теста Фазы 6.4 (id 47409): промпт (Фаза 4.5)
        # разрешает пустой econ_concepts при task_nature='не_задача',
        # счётчик диапазона 3..6 не должен на это ругаться.
        ok, violations = cmd.validate_call1(
            self._base(task_nature='не_задача', econ_concepts=[],
                       concepts_offlist=[]))
        self.assertTrue(ok, violations)

    def test_пустые_econ_concepts_всё_ещё_нарушение_для_обычной_задачи(self):
        ok, violations = cmd.validate_call1(
            self._base(task_nature='расчётная', econ_concepts=[]))
        self.assertFalse(ok)
        self.assertTrue(any('econ_concepts' in v for v in violations))

    def test_восемь_признаков_это_максимум(self):
        ok, _ = cmd.validate_call1(self._base(features_1=list(prompts_v2.FEATURES_1)))
        self.assertTrue(ok)
        ok, violations = cmd.validate_call1(
            self._base(features_1=list(prompts_v2.FEATURES_1) + ['лишний']))
        self.assertFalse(ok)


class ValidateCall2Tests(TestCase):

    def _base(self, **overrides):
        data = {
            'search_queries': ['q'] * 8, 'text_quality': 'чистая',
            'text_quality_note': '', 'problem_type': 'открытый_ответ',
            'difficulty': 3, 'difficulty_note': '',
            'answer_consistency': 'согласован', 'plot': None, 'hints': None,
            'title_candidate': 'Рынок кофе',
        }
        data.update(overrides)
        return data

    def test_валидный_ответ_проходит(self):
        ok, violations = cmd.validate_call2(self._base())
        self.assertTrue(ok, violations)

    def test_не_восемь_запросов(self):
        ok, violations = cmd.validate_call2(self._base(search_queries=['q'] * 7))
        self.assertFalse(ok)

    def test_hints_null_допустим(self):
        ok, _ = cmd.validate_call2(self._base(hints=None))
        self.assertTrue(ok)

    def test_hints_вне_диапазона(self):
        ok, violations = cmd.validate_call2(self._base(hints=['a', 'b']))
        self.assertFalse(ok)
        self.assertTrue(any('hints' in v for v in violations))

    def test_пять_подсказок_ок(self):
        ok, _ = cmd.validate_call2(self._base(hints=['a'] * 5))
        self.assertTrue(ok)

    def test_title_candidate_пустой(self):
        ok, violations = cmd.validate_call2(self._base(title_candidate=''))
        self.assertFalse(ok)
        self.assertTrue(any('пуст' in v for v in violations))

    def test_title_candidate_длиннее_40(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate='Очень ' * 10 + 'длинное имя'))
        self.assertFalse(ok)
        self.assertTrue(any('40' in v for v in violations))

    def test_title_candidate_больше_4_слов(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate='Раз два три четыре пять'))
        self.assertFalse(ok)
        self.assertTrue(any('1..4 слова' in v for v in violations))

    def test_title_candidate_со_строчной_буквы(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate='рынок кофе'))
        self.assertFalse(ok)
        self.assertTrue(any('заглавной' in v for v in violations))

    def test_title_candidate_с_точкой(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate='Рынок кофе.'))
        self.assertFalse(ok)
        self.assertTrue(any('точкой' in v for v in violations))

    def test_title_candidate_с_цифрой(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate='Налог 10 процентов'))
        self.assertFalse(ok)
        self.assertTrue(any('цифру' in v for v in violations))

    def test_title_candidate_с_latex(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate=r'Рынок $P$'))
        self.assertFalse(ok)
        self.assertTrue(any('$' in v for v in violations))

    def test_title_candidate_валидный(self):
        ok, violations = cmd.validate_call2(
            self._base(title_candidate='Дуополия Курно'))
        self.assertTrue(ok, violations)


class Call2UserTextContextTests(TestCase):
    """Фаза 5: вызов 2 получает тему/характер задачи из вызова 1."""

    def test_тема_и_характер_попадают_в_текст(self):
        text = prompts_v2.call2_user_text(
            'условие', 'дано', 'найти', 'решение', 'ответ',
            topic_primary_name='Монополия и ценовая дискриминация',
            task_nature='расчётная')
        self.assertIn('ГЛАВНАЯ ТЕМА (из первого разбора): '
                      'Монополия и ценовая дискриминация', text)
        self.assertIn('ХАРАКТЕР ЗАДАЧИ (из первого разбора): расчётная', text)

    def test_без_контекста_прочерк(self):
        text = prompts_v2.call2_user_text('условие', '', '', '', '')
        self.assertIn('ГЛАВНАЯ ТЕМА (из первого разбора): —', text)
        self.assertIn('ХАРАКТЕР ЗАДАЧИ (из первого разбора): —', text)


@override_settings(AI_PRICES=PRICES)
class VisualInvariantsTests(TestCase):
    """Фаза 6.2: инварианты «не потеряли визуальное»."""

    def setUp(self):
        self.marker_problem = _make_problem(
            'Смотри [[FIGURE:abc]] на графике.')
        self.table_problem = _make_problem(
            r'\begin{tabular}{cc}1 & 2\end{tabular}')
        self.plain_problem = _make_problem('Обычная задача без визуала.')
        self.pf_problem = _make_problem('Задача с картинкой без маркера.')
        self.pf_problem.figures.create(tikz_hash='a' * 64, tikz_source='src')
        self.ids = [self.marker_problem.id, self.table_problem.id,
                   self.plain_problem.id, self.pf_problem.id]

    def test_снимок_до_и_после_без_изменений_совпадает(self):
        before = cmd.visual_snapshot(self.ids)
        after = cmd.visual_snapshot(self.ids)
        lines = cmd.diff_visual_snapshots(before, after)
        self.assertTrue(all('РАСХОЖДЕНИЕ' not in line for line in lines))
        self.assertTrue(any('расхождений 0' in line for line in lines))

    def test_снимок_считает_маркеры_и_table_и_problemfigure(self):
        snap = cmd.visual_snapshot(self.ids)
        self.assertEqual(snap['figure_markers'], 1)
        self.assertEqual(snap['table_envs'], 1)
        self.assertEqual(snap['problem_figure_rows'], 1)

    def test_свип_детектор_ловит_изменение_текста(self):
        before = cmd.visual_snapshot(self.ids)
        Problem.objects.filter(id=self.plain_problem.id).update(
            statement='Текст подменили.')
        after = cmd.visual_snapshot(self.ids)
        lines = cmd.diff_visual_snapshots(before, after)
        self.assertTrue(any('РАСХОЖДЕНИЕ' in line or 'расхождений 1' in line
                            for line in lines))

    def test_is_visual_problem(self):
        self.assertTrue(cmd.is_visual_problem(self.marker_problem))
        self.assertTrue(cmd.is_visual_problem(self.table_problem))
        self.assertTrue(cmd.is_visual_problem(self.pf_problem))
        self.assertFalse(cmd.is_visual_problem(self.plain_problem))

    def test_visual_flag_lists_ловит_утраченный_визуал(self):
        rows = [
            {'problem_id': self.pf_problem.id,
             'call1': {'task_nature': 'расчётная'},
             'call2': {'text_quality_note':
                      'содержание в утраченном визуальном элементе'}},
            {'problem_id': self.marker_problem.id,
             'call1': {'task_nature': 'не_задача'},
             'call2': {'text_quality_note': ''}},
            {'problem_id': self.plain_problem.id,
             'call1': {'task_nature': 'не_задача'},
             'call2': {'text_quality_note': ''}},
        ]
        lost_visual, not_task_visual = cmd.visual_flag_lists(rows)
        self.assertEqual(lost_visual, [self.pf_problem.id])
        self.assertEqual(not_task_visual, [self.marker_problem.id])


class TaskNatureDivergenceTests(TestCase):
    """Фаза 5: числовой инвариант расхождения вызов1/вызов2 по «это задача»."""

    def test_нет_строк_с_call2_ноль_пар(self):
        divergent, total, pct = cmd.task_nature_divergence(
            [{'call1': {'task_nature': 'расчётная'}}])
        self.assertEqual((divergent, total, pct), (0, 0, 0.0))

    def test_совпадение_не_расхождение(self):
        rows = [
            {'call1': {'task_nature': 'расчётная'},
             'call2': {'problem_type': 'открытый_ответ'}},
            {'call1': {'task_nature': 'не_задача'},
             'call2': {'problem_type': 'не_задача'}},
        ]
        divergent, total, pct = cmd.task_nature_divergence(rows)
        self.assertEqual((divergent, total), (0, 2))
        self.assertEqual(pct, 0.0)

    def test_расхождение_считается(self):
        rows = [
            {'call1': {'task_nature': 'не_задача'},
             'call2': {'problem_type': 'открытый_ответ'}},
            {'call1': {'task_nature': 'расчётная'},
             'call2': {'problem_type': 'не_задача'}},
            {'call1': {'task_nature': 'расчётная'},
             'call2': {'problem_type': 'открытый_ответ'}},
        ]
        divergent, total, pct = cmd.task_nature_divergence(rows)
        self.assertEqual((divergent, total), (2, 3))
        self.assertAlmostEqual(pct, 200 / 3, places=4)


class VariantResolutionTests(TestCase):

    def test_all_возвращает_все_ветки(self):
        result = cmd.Command()._resolve_variants('all')
        self.assertEqual(list(result), list(cmd.ALL_VARIANTS))

    def test_список_через_запятую(self):
        result = cmd.Command()._resolve_variants('base, luna-luna')
        self.assertEqual(result, ['base', 'luna-luna'])

    def test_неизвестная_ветка_кидает_ошибку(self):
        with self.assertRaises(CommandError):
            cmd.Command()._resolve_variants('base,не-существует')

    def test_no_concepts_не_требует_econ_concepts_в_схеме(self):
        schema = prompts_v2.call1_schema(
            with_concepts=cmd.VARIANTS['no-concepts']['concepts'])
        self.assertNotIn('econ_concepts', schema['properties'])


class _FakeReply(object):
    def __init__(self, text, input_tokens=0, output_tokens=0,
                cache_write_tokens=0, cache_read_tokens=0):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_write_tokens = cache_write_tokens
        self.cache_read_tokens = cache_read_tokens
        self.reasoning_tokens = 0


CALL1_OK_JSON = (
    '{"topic_primary": "X", "topics_secondary": [], "tags": ["a"], '
    '"given": "Дано", "find": "Найти", "econ_concepts": ["a","b","c"], '
    '"concepts_offlist": [], "task_nature": "расчётная", "features_1": [], '
    '"topic_confidence": "высокая"}'
)
CALL2_OK_JSON = (
    '{"search_queries": ["a","b","c","d","e","f","g","h"], '
    '"text_quality": "чистая", "text_quality_note": "", '
    '"problem_type": "открытый_ответ", "difficulty": 2, '
    '"difficulty_note": "", "answer_consistency": "согласован", '
    '"plot": null, "hints": null, "title_candidate": "Рынок кофе"}'
)


@override_settings(AI_PRICES=PRICES)
class RunVariantMaxCostTests(TestCase):
    """⚠️ ГЛАВНАЯ зубастость Б2: --max-cost считает по фактическому usage."""

    def setUp(self):
        self.problems = [_make_problem('Задача %d.' % i) for i in range(5)]
        self.shortlists = {p.id: [] for p in self.problems}

    def _complete_fn_factory(self, cost_per_call):
        # `cost_per_call` — Decimal, дороговизна одного вызова через
        # input_tokens при цене 2.00/млн для TERRA (см. PRICES) —
        # достаточно грубо подобрать input_tokens под нужную цену.
        calls = []

        def complete_fn(model, blocks, user_text, schema, effort):
            calls.append((model, effort))
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            price_in = PRICES[model][0]
            input_tokens = int(cost_per_call / Decimal(str(price_in)) * Decimal(10 ** 6))
            return _FakeReply(text, input_tokens=input_tokens)

        return complete_fn, calls

    def test_останавливается_когда_реальный_расход_достиг_потолка(self):
        # Один вызов стоит ~$0.40 (input_tokens посчитаны так, чтобы дать
        # ровно эту цену при цене TERRA 2.00/млн). Два вызова на задачу
        # (call1 Terra + call2 Luna) — значит после ~1 задачи расход уже
        # у потолка $0.5, и цикл обязан остановиться, не дойдя до 5 задач.
        complete_fn, calls = self._complete_fn_factory(Decimal('0.40'))
        variant = cmd.VARIANTS['base']
        rows, spent, stopped_early = cmd.run_variant(
            self.problems, variant, complete_fn, self.shortlists,
            max_cost=0.5)
        self.assertTrue(stopped_early)
        self.assertLess(len(rows), len(self.problems))
        self.assertGreaterEqual(spent, Decimal('0.5'))

    def test_без_потолка_обрабатывает_всю_выборку(self):
        complete_fn, calls = self._complete_fn_factory(Decimal('0.0001'))
        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped_early = cmd.run_variant(
            self.problems, variant, complete_fn, self.shortlists,
            max_cost=None)
        self.assertFalse(stopped_early)
        self.assertEqual(len(rows), len(self.problems))
        self.assertEqual(len(calls), len(self.problems) * 2)

    def test_потолок_не_срабатывает_на_прикидке_а_только_на_реальном_usage(self):
        """Регрессия на баг build_eval_set_b: смета не должна решать за
        --max-cost — только фактический usage каждого ответа."""
        # Ставим потолок заведомо выше сметы, но при этом реальный usage
        # каждого вызова огромный — цикл обязан остановиться по нему, а не
        # проскочить все 5 задач, ориентируясь на маленькую оценку.
        complete_fn, calls = self._complete_fn_factory(Decimal('10'))
        variant = cmd.VARIANTS['base']
        rows, spent, stopped_early = cmd.run_variant(
            self.problems, variant, complete_fn, self.shortlists,
            max_cost=5.0)
        self.assertTrue(stopped_early)
        self.assertEqual(len(rows), 1)  # первый call1 уже перевалил потолок


def _schema_names(schema):
    return set(schema.get('properties', {}))


@override_settings(AI_PRICES=PRICES)
class RealCallCostTests(TestCase):

    def test_совпадает_с_ручным_расчётом(self):
        reply = _FakeReply('', input_tokens=1000, output_tokens=500,
                           cache_write_tokens=200, cache_read_tokens=300)
        cost = cmd.real_call_cost(cmd.TERRA, reply)
        price_in, price_cache, price_out = (Decimal('2.00'), Decimal('0.20'),
                                            Decimal('12.00'))
        expected = (
            Decimal(1000) * price_in + Decimal(500) * price_out
            + Decimal(200) * price_in * Decimal('1.25')
            + Decimal(300) * price_cache
        ) / Decimal(10 ** 6)
        self.assertEqual(cost, expected)


class NoApplyDoesNotCallApiTests(TestCase):
    """⚠️ Без --apply — ни одного обращения к API."""

    def setUp(self):
        for i in range(3):
            _make_problem('Задача %d про равновесие спроса и предложения.' % i,
                          topics=[cmd.MICRO_TOPICS[0]])

    def test_сухой_прогон_не_зовёт_provider_complete(self):
        with mock.patch.object(
                providers.OpenAIProvider, 'complete',
                side_effect=AssertionError(
                    'API вызван без --apply — это баг')) as fake_complete:
            out = io.StringIO()
            call_command('pilot_enrich_v2', '--limit', '3',
                        stdout=out, stderr=out)
            fake_complete.assert_not_called()
        self.assertIn('ФАЗА ПОКАЗА', out.getvalue())

    def test_apply_без_max_cost_кидает_ошибку(self):
        with self.assertRaises(CommandError):
            call_command('pilot_enrich_v2', '--limit', '3', '--apply')


class ProblemTextHelpersTests(TestCase):

    def test_problem_full_text_склеивает_условие_и_подпункты(self):
        problem = _make_problem('Общее условие.')
        problem.parts.create(label='а', statement='Первый подпункт', answer='')
        problem.parts.create(label='б', statement='Второй подпункт', answer='')
        full = enrich_text.problem_full_text(problem.statement, problem.parts.all())
        self.assertIn('Общее условие.', full)
        self.assertIn('(а) Первый подпункт', full)
        self.assertIn('(б) Второй подпункт', full)

    def test_is_english_text_ловит_латиницу_без_кириллицы(self):
        english = 'A monopolist faces demand Q equals one hundred minus price.' * 2
        self.assertTrue(enrich_text.is_english_text(english))

    def test_is_english_text_не_ловит_русский(self):
        russian = 'Монополист сталкивается со спросом сто минус цена.'
        self.assertFalse(enrich_text.is_english_text(russian))

    def test_is_english_text_короткий_текст_не_считается(self):
        self.assertFalse(enrich_text.is_english_text('OK'))

    def test_has_graph_in_statement_по_problem_figure(self):
        self.assertTrue(enrich_text.has_graph_in_statement(
            'Обычный текст без маркера.', has_problem_figure=True))

    def test_has_graph_in_statement_по_маркеру(self):
        self.assertTrue(enrich_text.has_graph_in_statement(
            'На рисунке ниже [[FIGURE:abc123]] показан спрос.'))

    def test_has_graph_in_statement_по_tikzpicture(self):
        self.assertTrue(enrich_text.has_graph_in_statement(
            r'\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}'))

    def test_has_graph_in_statement_ничего_нет(self):
        self.assertFalse(enrich_text.has_graph_in_statement(
            'Обычное условие без визуальных элементов.'))

    def test_has_table_in_statement_tabular(self):
        self.assertTrue(enrich_text.has_table_in_statement(
            r'\begin{tabular}{cc}1 & 2\end{tabular}'))

    def test_has_table_in_statement_html(self):
        self.assertTrue(enrich_text.has_table_in_statement(
            '<table><tr><td>1</td></tr></table>'))

    def test_has_table_in_statement_markdown(self):
        self.assertTrue(enrich_text.has_table_in_statement(
            '| Цена | Количество |\n| 10 | 5 |'))

    def test_has_table_in_statement_ничего_нет(self):
        self.assertFalse(enrich_text.has_table_in_statement(
            'Обычное условие без таблиц.'))


# ---------------------------------------------------------------------------
# Фаза 3 (2026-09-01): три примера разбора в WORKED_EXAMPLES построены на
# реальных задачах банка (id 28917, 1045, 47409) — тексты ниже переписаны
# дословно из БД на момент выбора примеров, чтобы тест не зависел от
# состояния живой базы. Механическая проверка ловит прошлый дефект: пример
# выдавал понятия мимо шорт-листа при пустом concepts_offlist.
# ---------------------------------------------------------------------------

_EXAMPLE_A_TEXT = (
    'Новая и единственная кофейня «Аромат» открывается в центре города и '
    'ее издержки заданы функцией $TC = Q^2 + 4Q + 20$. В первые дни работы '
    'кофейня смогла выяснить дневной спрос посетителей: $P = 120 - 2Q$; '
    'цены измеряются в д.е., а количество - в чашках кофе.\n'
    '(а) Найдите равновесие\n\n Однако через неделю, по мере завоевания '
    'популярности, мэр города узнал о кофейне и, будучи глубоко '
    'убежденным во вреде потребления кофе, хочет ввести налог, но не '
    'может выбрать какой, помогите ему рассмотреть разные случаи и '
    'выбрать подходящий:\n'
    '(б) налог на потребителя в размере 10 д.е.\n'
    '(в) налог на производителя в размере 10 д.е.\n'
    '(г) налог на потребителя в размере 10% от их цены'
)

_EXAMPLE_B_TEXT = (
    'На рынке некоторого товара функция спроса строго убывает, а функция '
    'предложения строго возрастает. Государство вводит потоварный налог '
    'на каждую единицу товара. Может ли случиться так, что при любой '
    'положительной ставке налога налоговые сборы государства оказываются '
    'одинаковыми (не зависят от ставки)? Если да, приведите пример таких '
    'функций спроса и предложения и докажите, что они удовлетворяют '
    'условию задачи. Если нет, строго докажите, что это невозможно.'
)

_EXAMPLE_C_TEXT = (
    'ности равны, и каждый бедный зарабатывает в 4 раза меньше, чем '
    'каждый богатый.\nИз страны уходит ровно половина ее населения. '
    'Найдите матожидание коэффициента\nДжинни после их ухода.'
)

_EXAMPLE_TEXTS = {'A': _EXAMPLE_A_TEXT, 'B': _EXAMPLE_B_TEXT, 'C': _EXAMPLE_C_TEXT}


def _parse_worked_examples(source=None):
    """Разбирает `WORKED_EXAMPLES` на блоки по букве примера (A/B/C) и
    вытаскивает поля регуляркой — тест читает РЕАЛЬНЫЙ текст промпта, а не
    ручную копию, иначе правка примера тихо перестанет проверяться.
    """
    source = source if source is not None else prompts_v2.WORKED_EXAMPLES
    blocks = {}
    matches = list(re.finditer(r'ПРИМЕР ([ABC]) ', source))
    for i, m in enumerate(matches):
        letter = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        blocks[letter] = source[start:end]

    parsed = {}
    for letter, block in blocks.items():
        def field_list(name, block=block):
            m = re.search(r'%s:\s*\[(.*?)\]' % re.escape(name), block)
            if not m:
                return None
            items = re.findall(r'"([^"]*)"', m.group(1))
            return items

        def field_str(name, block=block):
            m = re.search(r'%s:\s*"(.*?)"' % re.escape(name), block, re.DOTALL)
            return m.group(1) if m else None

        parsed[letter] = {
            'econ_concepts': field_list('econ_concepts'),
            'concepts_offlist': field_list('concepts_offlist'),
            'given': field_str('given'),
            'find': field_str('find'),
            'topic_confidence': field_str('topic_confidence'),
        }
    return parsed


class WorkedExamplesShortlistTests(TestCase):
    """Механическая проверка трёх примеров ядра вызова 1 (Фаза 3)."""

    def setUp(self):
        self.parsed = _parse_worked_examples()
        self.df = load_df_cache()

    def test_все_три_примера_разобрались(self):
        self.assertEqual(set(self.parsed), {'A', 'B', 'C'})

    def test_econ_concepts_и_concepts_offlist_покрывают_шорт_лист(self):
        for letter, text in _EXAMPLE_TEXTS.items():
            example = self.parsed[letter]
            shortlist = set(shortlist_for(text, df=self.df))
            for concept in example['econ_concepts'] or []:
                self.assertIn(
                    concept, shortlist,
                    'Пример %s: понятие %r из econ_concepts отсутствует в '
                    'шорт-листе и не объявлено в concepts_offlist' %
                    (letter, concept))
            for concept in example['concepts_offlist'] or []:
                self.assertNotIn(
                    concept, shortlist,
                    'Пример %s: понятие %r лежит в concepts_offlist, но '
                    'оно и так есть в шорт-листе — это не offlist-случай' %
                    (letter, concept))

    def test_topic_confidence_три_разных_значения(self):
        values = [self.parsed[letter]['topic_confidence'] for letter in 'ABC']
        self.assertEqual(len(set(values)), 3, values)

    def test_given_find_без_цифр(self):
        digit_re = re.compile(r'\d')
        for letter in 'ABC':
            example = self.parsed[letter]
            for field in ('given', 'find'):
                value = example[field] or ''
                self.assertIsNone(
                    digit_re.search(value),
                    'Пример %s: поле %s содержит цифру: %r' %
                    (letter, field, value))

    def test_зубастость_ловит_понятие_мимо_шорт_листа(self):
        """Портим Пример A понятием мимо шорт-листа при пустом offlist —
        тест обязан покраснеть. Не меняет исходный файл, работает на копии
        текста промпта."""
        broken_source = prompts_v2.WORKED_EXAMPLES.replace(
            'econ_concepts: ["равновесие", "налог", "спрос", "издержки"]',
            'econ_concepts: ["равновесие", "налог", "спрос", "издержки", '
            '"монополия"]',
            1,
        )
        self.assertNotEqual(broken_source, prompts_v2.WORKED_EXAMPLES,
                            'Замена не сработала — строка econ_concepts '
                            'примера A изменилась в исходнике, обнови тест')
        broken_parsed = _parse_worked_examples(broken_source)
        shortlist = set(shortlist_for(_EXAMPLE_A_TEXT, df=self.df))
        self.assertNotIn('монополия', shortlist)  # причина поломки
        with self.assertRaises(AssertionError):
            for concept in broken_parsed['A']['econ_concepts']:
                self.assertIn(concept, shortlist)
