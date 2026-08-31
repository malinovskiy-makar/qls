# -*- coding: utf-8 -*-
"""Пилот обогащения v2 (Б2): выборка, смета, гейт --apply/--max-cost.

Зубастость по списку Б5: шорт-лист сюда не входит (свой файл), но
стратификация обязана быть детерминированной сидом, `--max-cost` обязан
считать по ФАКТИЧЕСКОМУ usage (а не по смете), без `--apply` не должно
уходить ни одного обращения к API, а верхние границы массивов (1–5 тегов,
ровно 8 запросов...) проверяются в Python, а не схемой.
"""
import io
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, text as enrich_text
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


class ScaleStrataTests(TestCase):

    def test_сумма_страт_совпадает_с_limit(self):
        for limit in (30, 150, 300, 600, 900):
            scaled = cmd.scale_strata(limit)
            self.assertEqual(sum(t for _, t, _ in scaled), limit)

    def test_дефолтный_limit_даёт_исходные_страты(self):
        scaled = cmd.scale_strata(cmd.STRATA_TOTAL)
        self.assertEqual(scaled, cmd.STRATA)


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
    '"plot": null, "hints": null}'
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
