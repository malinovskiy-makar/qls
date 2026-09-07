# -*- coding: utf-8 -*-
"""Пилот обогащения v2 (Б2): выборка, смета, гейт --apply/--max-cost.

Зубастость по списку Б5: шорт-лист сюда не входит (свой файл), но
стратификация обязана быть детерминированной сидом, `--max-cost` обязан
считать по ФАКТИЧЕСКОМУ usage (а не по смете), без `--apply` не должно
уходить ни одного обращения к API, а верхние границы массивов (1–5 тегов,
ровно 8 запросов...) проверяются в Python, а не схемой.
"""
import ast
import io
import json
import re
import shutil
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from problems.ai import providers
from problems.enrich import prompts_v2, taxonomy, text as enrich_text, title_rules
from problems.enrich.shortlist import load_df_cache, shortlist_for
from problems.management.commands import pilot_enrich_v2 as cmd
from problems.models import Problem, ProblemFigure, Topic

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
            'given': 'Дано', 'find': 'Найти',
            'econ_concepts': ['альфа', 'бета', 'гамма'],
            'concepts_offlist': [], 'task_nature': 'расчётная',
            'features_1': [], 'topic_confidence': 'высокая',
        }
        data.update(overrides)
        return data

    def test_валидный_ответ_проходит(self):
        ok, violations = cmd.validate_call1(self._base())
        self.assertTrue(ok, violations)

    def test_восемь_тегов_проходит(self):
        # Граница расширена 03.09.2026: теги выписываются по КАЖДОЙ
        # названной теме, а не только по главной, — 1–8 вместо 1–5.
        ok, violations = cmd.validate_call1(self._base(tags=['a'] * 8))
        self.assertTrue(ok, violations)

    def test_слишком_много_тегов(self):
        ok, violations = cmd.validate_call1(self._base(tags=['a'] * 9))
        self.assertFalse(ok)
        self.assertTrue(any('tags' in v for v in violations))

    def test_ноль_тегов_не_проходит(self):
        ok, violations = cmd.validate_call1(self._base(tags=[]))
        self.assertFalse(ok)

    def test_мало_понятий_теперь_не_жёсткое(self):
        # Фаза 1 задания сессии 02.09 (вторая пересъёмка): econ_concepts
        # < 3 больше не портит банк — прямое следствие починки шорт-листа
        # (стал честнее и уже), повтор за это больше не платим.
        ok, violations = cmd.validate_call1(self._base(econ_concepts=['альфа']))
        self.assertTrue(ok, violations)
        soft = cmd.soft_violations_call1(self._base(econ_concepts=['альфа']))
        self.assertTrue(any('econ_concepts' in v for v in soft))

    def test_четыре_дополнительные_темы_проходят(self):
        # Граница расширена 03.09.2026: многотемье в олимпиадной экономике —
        # норма, поэтому 0–4 вместо 0–2.
        ok, violations = cmd.validate_call1(
            self._base(topics_secondary=['A', 'B', 'C', 'D']))
        self.assertTrue(ok, violations)

    def test_много_дополнительных_тем(self):
        ok, violations = cmd.validate_call1(
            self._base(topics_secondary=['A', 'B', 'C', 'D', 'E']))
        self.assertFalse(ok)
        self.assertTrue(any('topics_secondary' in v for v in violations))

    def test_семь_понятий_всё_ещё_жёсткое(self):
        ok, violations = cmd.validate_call1(
            self._base(econ_concepts=['a1', 'b1', 'c1', 'd1', 'e1', 'f1', 'g1']))
        self.assertFalse(ok)
        self.assertTrue(any('econ_concepts' in v for v in violations))

    def test_однобуквенное_обозначение_econ_concepts_жёсткое(self):
        # §12 правило 5 / §4.6 API_RUN_MASTER: «P», «π» и подобные
        # неоднозначны без контекста — запрещены даже если модель взяла их
        # дословно из шорт-листа.
        ok, violations = cmd.validate_call1(
            self._base(econ_concepts=['альфа', 'P', 'гамма']))
        self.assertFalse(ok)
        self.assertTrue(any('однобуквенное' in v for v in violations))

    def test_понятие_вне_шорт_листа_жёсткое(self):
        ok, violations = cmd.validate_call1(
            self._base(econ_concepts=['альфа', 'бета', 'не_из_списка']),
            shortlist_terms=['альфа', 'бета', 'гамма'])
        self.assertFalse(ok)
        self.assertTrue(any('вне шорт-листа' in v for v in violations))

    def test_понятие_из_шорт_листа_проходит(self):
        ok, violations = cmd.validate_call1(
            self._base(econ_concepts=['альфа', 'бета', 'гамма']),
            shortlist_terms=['альфа', 'бета', 'гамма', 'дельта'])
        self.assertTrue(ok, violations)

    def test_пустой_шорт_лист_не_проверяется(self):
        # `shortlist_for()` в бою никогда не отдаёт [] (добор ядром до
        # MIN_SHORTLIST) — [] в вызове читается как «не задан», не как
        # «ничего не разрешено».
        ok, violations = cmd.validate_call1(self._base(), shortlist_terms=[])
        self.assertTrue(ok, violations)

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
        self.assertEqual(
            cmd.soft_violations_call1(
                self._base(task_nature='не_задача', econ_concepts=[],
                           concepts_offlist=[])),
            ['topics_secondary пусто'])

    def test_пустые_econ_concepts_теперь_только_мягкое_для_обычной_задачи(self):
        ok, violations = cmd.validate_call1(
            self._base(task_nature='расчётная', econ_concepts=[]))
        self.assertTrue(ok, violations)
        soft = cmd.soft_violations_call1(
            self._base(task_nature='расчётная', econ_concepts=[]))
        self.assertTrue(any('econ_concepts' in v for v in soft))

    def test_topics_secondary_пусто_мягкое(self):
        soft = cmd.soft_violations_call1(self._base(topics_secondary=[]))
        self.assertIn('topics_secondary пусто', soft)

    def test_topics_secondary_непусто_без_мягкого(self):
        soft = cmd.soft_violations_call1(self._base(topics_secondary=['5']))
        self.assertNotIn('topics_secondary пусто', soft)

    def test_шесть_признаков_это_максимум(self):
        ok, _ = cmd.validate_call1(self._base(features_1=list(prompts_v2.FEATURES_1)))
        self.assertTrue(ok)
        ok, violations = cmd.validate_call1(
            self._base(features_1=list(prompts_v2.FEATURES_1) + ['лишний']))
        self.assertFalse(ok)

    # -----------------------------------------------------------------
    # §12 правило 3 API_RUN_MASTER: «Ни одной цифры в given, find,
    # econ_concepts... — проверка регуляркой, а не просьбой в промпте.»
    # Зубастость задания сессии называет «цифра в given» прямым текстом.
    # -----------------------------------------------------------------

    def test_цифра_в_given_нарушение(self):
        ok, violations = cmd.validate_call1(self._base(given='Цена P=10'))
        self.assertFalse(ok)
        self.assertTrue(any('given' in v for v in violations))

    def test_цифра_в_find_нарушение(self):
        ok, violations = cmd.validate_call1(self._base(find='Найти Q при P=5'))
        self.assertFalse(ok)
        self.assertTrue(any('find' in v for v in violations))

    def test_цифра_в_econ_concepts_нарушение(self):
        ok, violations = cmd.validate_call1(
            self._base(econ_concepts=['эластичность', 'налог 2 рода', 'спрос']))
        self.assertFalse(ok)
        self.assertTrue(any('econ_concepts' in v for v in violations))

    def test_given_и_find_без_цифр_проходят(self):
        ok, violations = cmd.validate_call1(
            self._base(given='Линейная функция спроса', find='Точку равновесия'))
        self.assertTrue(ok, violations)


class ValidateCall2Tests(TestCase):

    def _base(self, **overrides):
        data = {
            'search_queries': ['q'] * 8, 'text_quality': 'чистая',
            'text_quality_note': '', 'problem_type': 'тест: короткий ответ',
            'difficulty': 3, 'difficulty_note': '',
            'answer_consistency': 'согласован', 'plot': None, 'hints': None,
            'title_candidate': 'Рынок кофе',
        }
        data.update(overrides)
        return data

    def test_валидный_ответ_проходит(self):
        ok, violations = cmd.validate_call2(self._base())
        self.assertTrue(ok, violations)

    def test_запросов_меньше_пяти_теперь_мягкое(self):
        # Фаза 1 задания сессии 02.09 (вторая пересъёмка): пять точных
        # запросов лучше восьми с натяжкой — за это больше не повторяем.
        ok, violations = cmd.validate_call2(self._base(search_queries=['q'] * 4))
        self.assertTrue(ok, violations)
        soft = cmd.soft_violations_call2(self._base(search_queries=['q'] * 4))
        self.assertTrue(any('search_queries' in v for v in soft))

    def test_запросов_больше_восьми_нарушение(self):
        ok, violations = cmd.validate_call2(self._base(search_queries=['q'] * 9))
        self.assertFalse(ok)

    def test_пять_запросов_законно(self):
        """Фаза B.3: нижняя граница снижена с 8 до 5 — лучше пять точных,
        чем восемь с натяжкой (боевой прогон 02.09: восьмой запрос у #32
        был откровенным добиванием до счёта, к задаче не относился)."""
        ok, violations = cmd.validate_call2(self._base(search_queries=['q'] * 5))
        self.assertTrue(ok, violations)

    def test_семь_запросов_законно(self):
        ok, violations = cmd.validate_call2(self._base(search_queries=['q'] * 7))
        self.assertTrue(ok, violations)

    def test_восемь_запросов_всё_ещё_законно(self):
        ok, violations = cmd.validate_call2(self._base(search_queries=['q'] * 8))
        self.assertTrue(ok, violations)

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

    def test_title_candidate_длиннее_40_теперь_мягкое(self):
        long_title = 'Очень ' * 10 + 'длинное имя'
        ok, violations = cmd.validate_call2(self._base(title_candidate=long_title))
        self.assertTrue(ok, violations)
        soft = cmd.soft_violations_call2(self._base(title_candidate=long_title))
        self.assertTrue(any('40' in v for v in soft))

    def test_title_candidate_больше_4_слов_теперь_мягкое(self):
        title = 'Раз два три четыре пять'
        ok, violations = cmd.validate_call2(self._base(title_candidate=title))
        self.assertTrue(ok, violations)
        soft = cmd.soft_violations_call2(self._base(title_candidate=title))
        self.assertTrue(any('1..4 слова' in v for v in soft))

    def test_soft_violations_call2_пустой_title_без_мягкого(self):
        # Пустой заголовок остаётся ЖЁСТКИМ нарушением (title_candidate
        # пуст) — мягкая проверка длины/числа слов не должна дублировать
        # его отдельной записью про несуществующий текст.
        soft = cmd.soft_violations_call2(self._base(title_candidate=''))
        self.assertEqual(soft, [])

    def test_soft_violations_call2_валидный_без_мягких(self):
        self.assertEqual(cmd.soft_violations_call2(self._base()), [])

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

    # -----------------------------------------------------------------
    # §12 правило 3: та же проверка цифр — для `plot` и восьми запросов.
    # -----------------------------------------------------------------

    def test_цифра_в_plot_нарушение(self):
        ok, violations = cmd.validate_call2(
            self._base(plot='Монополист продаёт 2 товара двум группам'))
        self.assertFalse(ok)
        self.assertTrue(any('plot' in v for v in violations))

    def test_цифра_в_одном_из_search_queries_нарушение(self):
        queries = ['a'] * 7 + ['запрос с числом 5']
        ok, violations = cmd.validate_call2(self._base(search_queries=queries))
        self.assertFalse(ok)
        self.assertTrue(any('search_queries' in v for v in violations))

    def test_plot_без_цифр_проходит(self):
        ok, violations = cmd.validate_call2(
            self._base(plot='Монополист продаёт товар нескольким группам'))
        self.assertTrue(ok, violations)


class DropDigitSearchQueriesTests(TestCase):
    """Фаза 1.2 (решение владельца 02.09.2026, четвёртая пересъёмка):
    запрос с цифрой ВЫБРАСЫВАЕТСЯ из массива, а не роняет весь вызов.

    Правило §12.3 «без цифр» при этом не ослаблено: цифра в поисковом
    запросе по-прежнему недопустима — меняется реакция, не правило."""

    def _call2(self, queries):
        return {
            'search_queries': list(queries), 'text_quality': 'чистая',
            'text_quality_note': '', 'problem_type': 'тест: короткий ответ',
            'difficulty': 3, 'difficulty_note': '',
            'answer_consistency': 'согласован', 'plot': None, 'hints': None,
            'title_candidate': 'Рынок кофе',
        }

    def test_восемь_запросов_два_с_цифрами_остаётся_шесть_и_вызов_проходит(self):
        """Зубастость задания дословно: массив из восьми, где два с
        цифрами — на выходе шесть и вызов прошёл."""
        data = self._call2(['чистый запрос %d' % i for i in range(6)])
        data['search_queries'] = ['спрос и предложение', 'эластичность спроса',
                                  'налог на производителя', 'потолок цены',
                                  'излишек потребителя', 'равновесие рынка',
                                  'цена 100 рублей', 'спрос при Q = 20']
        dropped = cmd.drop_digit_search_queries(data)
        self.assertEqual(len(dropped), 2)
        self.assertEqual(len(data['search_queries']), 6)
        ok, violations = cmd.validate_call2_full(data)
        self.assertTrue(ok, violations)
        self.assertEqual(cmd.soft_violations_call2(data), [])

    def test_шесть_запросов_четыре_с_цифрами_остаётся_два_мягкое_без_повтора(self):
        """Зубастость задания дословно: массив из шести, где четыре с
        цифрами — на выходе два, мягкое нарушение, повтора нет."""
        data = self._call2(['спрос и предложение', 'эластичность спроса',
                            'цена 100 рублей', 'выпуск 20 единиц',
                            'налог 5 процентов', 'доход 1000 рублей'])
        dropped = cmd.drop_digit_search_queries(data)
        self.assertEqual(len(dropped), 4)
        self.assertEqual(len(data['search_queries']), 2)
        # мягкое: повтора не будет — validate_call2_full молчит.
        ok, violations = cmd.validate_call2_full(data)
        self.assertTrue(ok, violations)
        soft = cmd.soft_violations_call2(data)
        self.assertTrue(any('search_queries' in v for v in soft), soft)

    def test_выброшенные_запросы_возвращаются_текстом(self):
        data = self._call2(['спрос', 'предложение', 'цена 100 рублей'])
        dropped = cmd.drop_digit_search_queries(data)
        self.assertEqual(dropped, ['цена 100 рублей'])

    def test_массив_без_цифр_не_трогается(self):
        queries = ['спрос', 'предложение', 'равновесие', 'налог', 'субсидия']
        data = self._call2(queries)
        self.assertEqual(cmd.drop_digit_search_queries(data), [])
        self.assertEqual(data['search_queries'], queries)

    def test_не_словарь_и_не_список_не_ломают(self):
        self.assertEqual(cmd.drop_digit_search_queries(None), [])
        self.assertEqual(cmd.drop_digit_search_queries('строка'), [])
        self.assertEqual(cmd.drop_digit_search_queries({'search_queries': None}), [])

    def test_не_строки_остаются_и_ловятся_схемой(self):
        """Число вместо запроса — это НЕ «запрос с цифрой», а нарушение
        типа: его обязана поймать схема жёстко, а не проглотить выброс."""
        data = self._call2(['спрос', 'предложение', 'равновесие', 'налог', 42])
        self.assertEqual(cmd.drop_digit_search_queries(data), [])
        ok, violations = cmd.validate_call2_full(data)
        self.assertFalse(ok)
        self.assertTrue(any('search_queries[4]' in v for v in violations), violations)

    def test_санитайзер_помнит_последнюю_попытку_а_не_копит(self):
        sanitize, state = cmd.make_query_sanitizer()
        sanitize(self._call2(['спрос', 'цена 100 рублей']))
        self.assertEqual(len(state['dropped']), 1)
        sanitize(self._call2(['спрос', 'предложение']))
        self.assertEqual(state['dropped'], [])


class DigitFragmentMessageTests(TestCase):
    """Фаза 1.3: сообщение повтора по `given`/`find` цитирует нарушивший
    кусок и говорит, чем его заменить. Правило остаётся жёстким."""

    def _base(self, **overrides):
        theme_id = taxonomy.theme_ids()[0]
        tag_id = taxonomy.tag_ids()[0]
        data = {
            'topic_primary': theme_id, 'topics_secondary': [], 'tags': [tag_id],
            'given': 'Линейная функция спроса', 'find': 'Точку равновесия',
            'econ_concepts': ['спрос', 'предложение', 'равновесие'],
            'concepts_offlist': [], 'task_nature': 'расчётная',
            'features_1': [], 'topic_confidence': 'высокая',
        }
        data.update(overrides)
        return data

    def test_кусок_вокруг_цифры_а_не_вся_строка(self):
        fragment = cmd.digit_fragment(
            'Дана линейная функция спроса P = 100 − 2Q, найдите равновесие')
        self.assertIn('100', fragment)
        self.assertNotIn('найдите равновесие', fragment)

    def test_длинный_кусок_обрезается_окном_вокруг_цифры(self):
        text = 'слово ' * 40 + 'P = 100' + ' слово' * 40
        fragment = cmd.digit_fragment(text)
        self.assertLessEqual(len(fragment), 60)
        self.assertIn('100', fragment)

    def test_без_цифр_куска_нет(self):
        self.assertEqual(cmd.digit_fragment('линейная функция спроса'), '')

    def test_сообщение_повтора_цитирует_фрагмент_и_говорит_что_делать(self):
        ok, violations = cmd.validate_call1(
            self._base(given='Дана функция спроса P = 100 − 2Q'))
        self.assertFalse(ok)
        message = ' | '.join(violations)
        self.assertIn('В поле given встречается', message)
        self.assertIn('100', message)
        self.assertIn('Числовые значения запрещены', message)
        self.assertIn('линейная функция спроса', message)
        self.assertIn('Перепиши только given и find', message)

    def test_правило_осталось_жёстким(self):
        """Формулировка сообщения смягчилась, само правило — нет:
        `ok` по-прежнему False, значит будет повтор."""
        ok, _ = cmd.validate_call1(self._base(find='Найти Q при P = 5'))
        self.assertFalse(ok)


class CheckAgainstSchemaTests(TestCase):
    """§12 правило 4 / зубастость «несуществующий номер тега»: у Z.AI нет
    строгого `enum` на стороне поставщика — эту проверку обязан сделать
    наш код, тем же способом, каким её уже делает `glm_eval.py`."""

    def _valid_call1(self):
        theme_id = taxonomy.theme_ids()[0]
        tag_id = taxonomy.tag_ids()[0]
        return {
            'topic_primary': theme_id, 'topics_secondary': [],
            'tags': [tag_id], 'given': 'Дано', 'find': 'Найти',
            'econ_concepts': ['спрос', 'предложение', 'равновесие'],
            'concepts_offlist': [], 'task_nature': 'расчётная',
            'features_1': [], 'topic_confidence': 'высокая',
        }

    def test_валидный_ответ_проходит_схему(self):
        violations = cmd.check_against_schema(
            self._valid_call1(), prompts_v2.call1_schema(with_concepts=True))
        self.assertEqual(violations, [])

    def test_несуществующий_номер_темы(self):
        data = self._valid_call1()
        data['topic_primary'] = '999'  # заведомо не существующая тема
        violations = cmd.check_against_schema(
            data, prompts_v2.call1_schema(with_concepts=True))
        self.assertTrue(any('topic_primary' in v for v in violations))

    def test_несуществующий_номер_тега(self):
        data = self._valid_call1()
        data['tags'] = ['999.99']  # заведомо не существующий тег
        violations = cmd.check_against_schema(
            data, prompts_v2.call1_schema(with_concepts=True))
        self.assertTrue(any('tags' in v for v in violations))

    def test_отсутствует_обязательное_поле(self):
        data = self._valid_call1()
        del data['find']
        violations = cmd.check_against_schema(
            data, prompts_v2.call1_schema(with_concepts=True))
        self.assertTrue(any('find' in v for v in violations))

    def test_лишнее_поле_вне_схемы(self):
        data = self._valid_call1()
        data['совсем_левое_поле'] = 'x'
        violations = cmd.check_against_schema(
            data, prompts_v2.call1_schema(with_concepts=True))
        self.assertTrue(any('лишние поля' in v for v in violations))

    def test_не_json_объект(self):
        violations = cmd.check_against_schema(
            None, prompts_v2.call1_schema(with_concepts=True))
        self.assertTrue(violations)

    def _valid_call2(self):
        return {
            'search_queries': ['a', 'b', 'c', 'd', 'e'],
            'text_quality': 'чистая', 'text_quality_note': '',
            'problem_type': 'тест: короткий ответ', 'difficulty': 3,
            'difficulty_note': '', 'answer_consistency': 'согласован',
            'plot': None, 'hints': None, 'title_candidate': 'Рынок кофе',
        }

    def test_difficulty_в_границах_1_5_проходит(self):
        violations = cmd.check_against_schema(self._valid_call2(), prompts_v2.CALL2_SCHEMA)
        self.assertEqual(violations, [])

    def test_difficulty_ноль_вне_границ(self):
        # Фаза 1 задания сессии 02.09 (вторая пересъёмка): schema уже
        # объявляла minimum/maximum, но `_check_schema_value` их не
        # проверял — тип integer/null пропускал 0 и 6 молча.
        data = self._valid_call2()
        data['difficulty'] = 0
        violations = cmd.check_against_schema(data, prompts_v2.CALL2_SCHEMA)
        self.assertTrue(any('difficulty' in v and 'минимума' in v for v in violations))

    def test_difficulty_шесть_вне_границ(self):
        data = self._valid_call2()
        data['difficulty'] = 6
        violations = cmd.check_against_schema(data, prompts_v2.CALL2_SCHEMA)
        self.assertTrue(any('difficulty' in v and 'максимума' in v for v in violations))

    def test_difficulty_null_допустим_для_не_задачи(self):
        data = self._valid_call2()
        data['difficulty'] = None
        violations = cmd.check_against_schema(data, prompts_v2.CALL2_SCHEMA)
        self.assertEqual(violations, [])


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
             'call2': {'problem_type': 'тест: короткий ответ'}},
            {'call1': {'task_nature': 'не_задача'},
             'call2': {'problem_type': 'не_задача'}},
        ]
        divergent, total, pct = cmd.task_nature_divergence(rows)
        self.assertEqual((divergent, total), (0, 2))
        self.assertEqual(pct, 0.0)

    def test_расхождение_считается(self):
        rows = [
            {'call1': {'task_nature': 'не_задача'},
             'call2': {'problem_type': 'тест: короткий ответ'}},
            {'call1': {'task_nature': 'расчётная'},
             'call2': {'problem_type': 'не_задача'}},
            {'call1': {'task_nature': 'расчётная'},
             'call2': {'problem_type': 'тест: короткий ответ'}},
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
    # topic_primary/tags — НАСТОЯЩИЕ id из data/taxonomy.json (не "X"/"a"):
    # с тех пор как `_process_one_problem` проверяет ответ и `check_against_
    # schema` (боевой путь GLM, §12 правило 4), фиктивные id читались бы
    # как нарушение enum и запускали лишний повтор — здесь это сбило бы с
    # толку тесты, которые проверяют СОВСЕМ ДРУГОЕ (параллельность, дедуп,
    # учёт расхода), а не содержимое ответа.
    '{"topic_primary": "1", "topics_secondary": [], "tags": ["1.1"], '
    '"given": "Дано", "find": "Найти", '
    '"econ_concepts": ["альфа","бета","гамма"], '
    '"concepts_offlist": [], "task_nature": "расчётная", "features_1": [], '
    '"topic_confidence": "высокая"}'
)
CALL2_OK_JSON = (
    '{"search_queries": ["a","b","c","d","e","f","g","h"], '
    '"text_quality": "чистая", "text_quality_note": "", '
    '"problem_type": "тест: короткий ответ", "difficulty": 2, '
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

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
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


class StripGivenFindPrefixTests(TestCase):
    """Фаза B.2 (боевой прогон 02.09): поле уже называется given/find —
    приставка «Дано:»/«Найти:» это мусор, который иначе уходит в эмбеддинг.
    Срезается КОДОМ, БЕЗ повтора — это не нарушение схемы."""

    def test_срезает_дано(self):
        data = {'given': 'Дано: линейная функция спроса'}
        cmd.strip_given_find_prefixes(data)
        self.assertEqual(data['given'], 'линейная функция спроса')

    def test_срезает_найти(self):
        data = {'find': 'Найти: точку равновесия'}
        cmd.strip_given_find_prefixes(data)
        self.assertEqual(data['find'], 'точку равновесия')

    def test_регистронезависимо_и_с_пробелами(self):
        data = {'given': '  дано:   структура рынка'}
        cmd.strip_given_find_prefixes(data)
        self.assertEqual(data['given'], 'структура рынка')

    def test_без_приставки_не_трогает(self):
        data = {'given': 'линейная функция спроса', 'find': 'точку равновесия'}
        cmd.strip_given_find_prefixes(data)
        self.assertEqual(data['given'], 'линейная функция спроса')
        self.assertEqual(data['find'], 'точку равновесия')

    def test_пустое_значение_и_отсутствующий_ключ_не_падают(self):
        cmd.strip_given_find_prefixes({'given': None, 'find': ''})
        cmd.strip_given_find_prefixes({})
        cmd.strip_given_find_prefixes(None)  # не должно бросить исключение

    def test_другие_поля_не_трогает(self):
        data = {'given': 'Дано: X', 'topic_primary': '1'}
        cmd.strip_given_find_prefixes(data)
        self.assertEqual(data['topic_primary'], '1')


class CallWithRetryTests(TestCase):
    """Фаза 2 задания сессии: у Z.AI нет строгой схемы — весь контроль
    держит наш код. «Механика при нарушении: один повтор с коротким
    сообщением, что именно не так. Не помогло — задача в очередь брака.»"""

    def test_валидный_ответ_с_первого_раза_без_повтора(self):
        calls = []

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            calls.append(user_text)
            return _FakeReply(CALL1_OK_JSON)

        reply, data, ok, violations, retried, attempts = cmd.call_with_retry(
            complete_fn, 'm', ['ядро'], 'текст', {}, None, None,
            lambda d: cmd.validate_call1(d, True))

        self.assertTrue(ok)
        self.assertEqual(violations, [])
        self.assertFalse(retried)
        self.assertEqual(len(calls), 1)

    def test_нарушение_даёт_один_повтор_с_объяснением(self):
        bad_json = CALL1_OK_JSON.replace('"tags": ["1.1"]', '"tags": []')
        calls = []

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            calls.append(user_text)
            if len(calls) == 1:
                return _FakeReply(bad_json)
            return _FakeReply(CALL1_OK_JSON)

        reply, data, ok, violations, retried, attempts = cmd.call_with_retry(
            complete_fn, 'm', ['ядро'], 'текст', {}, None, None,
            lambda d: cmd.validate_call1(d, True))

        self.assertTrue(ok)
        self.assertTrue(retried)
        self.assertEqual(len(calls), 2)
        # повторный промпт содержит явное объяснение, что не так — не
        # молчаливая перепосылка того же текста.
        self.assertIn('tags', calls[1])
        self.assertIn('текст', calls[1])  # исходный текст задачи никуда не делся

    def test_если_и_повтор_не_помог_идёт_в_брак(self):
        bad_json = CALL1_OK_JSON.replace('"tags": ["1.1"]', '"tags": []')
        calls = []

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            calls.append(user_text)
            return _FakeReply(bad_json)

        reply, data, ok, violations, retried, attempts = cmd.call_with_retry(
            complete_fn, 'm', ['ядро'], 'текст', {}, None, None,
            lambda d: cmd.validate_call1(d, True))

        self.assertFalse(ok)
        self.assertTrue(retried)
        self.assertEqual(len(calls), 2)  # ровно один повтор, не бесконечный цикл
        self.assertTrue(violations)

    def test_битый_json_тоже_считается_нарушением_а_не_падением(self):
        calls = []

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            calls.append(user_text)
            if len(calls) == 1:
                return _FakeReply('это не json')
            return _FakeReply(CALL1_OK_JSON)

        reply, data, ok, violations, retried, attempts = cmd.call_with_retry(
            complete_fn, 'm', ['ядро'], 'текст', {}, None, None,
            lambda d: cmd.validate_call1(d, True))

        self.assertTrue(ok)
        self.assertTrue(retried)
        self.assertEqual(len(calls), 2)


class RunVariantConcurrentTests(TestCase):
    """Фаза 1 задания сессии: пул воркеров для боевого прогона на GLM.
    Зубастость — реально проверяем ОДНОВРЕМЕННОСТЬ (счётчик в локе, а не
    просто «правильное число строк на выходе»), потому что баг вида
    «ThreadPoolExecutor создан, но семафора нет» дал бы точно такой же
    результат на маленькой тестовой выборке, просто без реального
    параллелизма — и остался бы незамеченным без явного счётчика пиков."""

    def setUp(self):
        self.problems = [_make_problem('Задача %d.' % i) for i in range(8)]
        self.shortlists = {p.id: [] for p in self.problems}

    def _tracking_complete_fn(self, sleep_seconds=0.03):
        import threading
        import time as _time
        lock = threading.Lock()
        state = {'inflight': 0, 'peak': 0, 'calls': 0}

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            with lock:
                state['inflight'] += 1
                state['peak'] = max(state['peak'], state['inflight'])
                state['calls'] += 1
            _time.sleep(sleep_seconds)
            with lock:
                state['inflight'] -= 1
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return _FakeReply(text)

        return complete_fn, state

    def test_не_превышает_потолок_одновременных_вызовов(self):
        complete_fn, state = self._tracking_complete_fn()
        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped, errors = cmd.run_variant_concurrent(
            self.problems, variant, complete_fn, self.shortlists, workers=3)

        self.assertEqual(errors, [])
        self.assertLessEqual(state['peak'], 3)
        # хотя бы раз пул реально заполнился до потолка — иначе тест не
        # доказывает параллельность, а просто не противоречит ей.
        self.assertEqual(state['peak'], 3)
        self.assertEqual(len(rows), 8)
        self.assertFalse(stopped)

    def test_обрабатывает_всю_выборку(self):
        complete_fn, state = self._tracking_complete_fn(sleep_seconds=0.01)
        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped, errors = cmd.run_variant_concurrent(
            self.problems, variant, complete_fn, self.shortlists, workers=4)

        got_ids = sorted(r['problem_id'] for r in rows)
        want_ids = sorted(p.id for p in self.problems)
        self.assertEqual(got_ids, want_ids)
        self.assertEqual(state['calls'], 16)  # 8 задач × 2 вызова

    def test_max_cost_реально_останавливает_новые_вызовы(self):
        import threading
        calls = []
        calls_lock = threading.Lock()

        def expensive_complete_fn(model, blocks, user_text, schema, effort, images=None):
            with calls_lock:
                calls.append(model)
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            price_in = PRICES[model][0]
            # каждый вызов сам по себе дороже потолка — после первой же
            # задачи расход обязан перевалить $0.5 и остановить пул.
            input_tokens = int(Decimal('0.6') / Decimal(str(price_in)) * Decimal(10 ** 6))
            return _FakeReply(text, input_tokens=input_tokens)

        variant = cmd.VARIANTS['base']
        rows, spent, stopped, errors = cmd.run_variant_concurrent(
            self.problems, variant, expensive_complete_fn, self.shortlists,
            workers=2, max_cost=0.5)

        self.assertEqual(errors, [])
        self.assertTrue(stopped)
        self.assertGreaterEqual(spent, Decimal('0.5'))
        self.assertLess(len(rows), len(self.problems))

    def test_on_progress_и_on_row_вызываются_на_каждую_строку(self):
        complete_fn, state = self._tracking_complete_fn(sleep_seconds=0.01)
        variant = cmd.VARIANTS['luna-luna']
        seen_rows = []
        seen_progress = []
        cmd.run_variant_concurrent(
            self.problems, variant, complete_fn, self.shortlists, workers=3,
            on_row=lambda row: seen_rows.append(row['problem_id']),
            on_progress=lambda pid, spent: seen_progress.append(pid))

        self.assertEqual(sorted(seen_rows), sorted(p.id for p in self.problems))
        self.assertEqual(sorted(seen_progress), sorted(p.id for p in self.problems))

    def test_единственный_воркер_ведёт_себя_как_последовательный_прогон(self):
        """workers=1 — не особый случай в коде, но полезно знать, что
        итог совпадает с `run_variant` по набору id и числу строк."""
        complete_fn, state = self._tracking_complete_fn(sleep_seconds=0.0)
        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped, errors = cmd.run_variant_concurrent(
            self.problems, variant, complete_fn, self.shortlists, workers=1)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 8)
        self.assertEqual(state['peak'], 1)

    def test_одна_упавшая_задача_не_роняет_остальные(self):
        """Ключевая устойчивость Фазы 1/4: обрыв на ОДНОЙ задаче из 300
        не имеет права стоить прогону остальных 299 уже оплаченных.
        Битый JSON сюда не годится — `call_with_retry` теперь обрабатывает
        его как нарушение схемы (повтор, потом брак), а не как исключение;
        нужен настоящий сбой, который переживает и повтор complete_fn."""
        bad_problem = _make_problem('СЛОМАННАЯ_МЕТКА задача.')
        problems = self.problems + [bad_problem]
        shortlists = {p.id: [] for p in problems}

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            if 'СЛОМАННАЯ_МЕТКА' in user_text:
                raise RuntimeError('внутренняя ошибка, не связанная с форматом ответа')
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return _FakeReply(text)

        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped, errors = cmd.run_variant_concurrent(
            problems, variant, complete_fn, shortlists, workers=3)

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], bad_problem.id)
        self.assertEqual(len(rows), len(problems) - 1)
        self.assertEqual(sorted(r['problem_id'] for r in rows),
                         sorted(p.id for p in self.problems))


class StopEventTests(TestCase):
    """Фаза 2: автостоп при доле брака выше 3% дёргает `stop_event`, а не
    падает исключением — новые задачи перестают стартовать, уже летящие
    доигрывают."""

    def test_stop_event_останавливает_новые_задачи(self):
        import threading
        problems = [_make_problem('Задача %d.' % i) for i in range(10)]
        shortlists = {p.id: [] for p in problems}
        stop_event = threading.Event()
        stop_event.set()  # уже взведён ДО прогона — ни одна задача не должна уйти

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return _FakeReply(text)

        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped, errors = cmd.run_variant_concurrent(
            problems, variant, complete_fn, shortlists, workers=3,
            stop_event=stop_event)

        self.assertEqual(rows, [])
        self.assertTrue(stopped)


class ResumableRunConcurrentTests(TestCase):
    """Фаза 3/4 задания сессии: `resumable_run_variant_concurrent` пишет
    журнал ПОД ЛОКОМ — без него параллельные `append_raw_log` из разных
    потоков могут перемешать строки JSONL (каждая строка сама по себе
    валидна, но запись не атомарна на уровне ОС при одновременном append
    из нескольких потоков одного процесса без синхронизации на стороне
    Python)."""

    def setUp(self):
        self.problems = [_make_problem('Задача %d.' % i) for i in range(12)]
        self.shortlists = {p.id: [] for p in self.problems}
        self.log_path = Path(tempfile.mkdtemp()) / 'raw.jsonl'

    def _complete_fn(self):
        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return _FakeReply(text)
        return complete_fn

    def test_журнал_остаётся_валидным_jsonl_под_нагрузкой(self):
        variant = cmd.VARIANTS['luna-luna']
        rows, spent, stopped, skipped, errors = cmd.resumable_run_variant_concurrent(
            self.problems, variant, self._complete_fn(), self.shortlists,
            str(self.log_path), 'run-1', 'promptver', workers=6)

        self.assertEqual(errors, [])
        self.assertEqual(skipped, 0)
        entries = cmd.read_raw_log(str(self.log_path))
        # 12 задач × 2 вызова = 24 строки, каждая — валидный JSON (иначе
        # read_raw_log сам бы упал на json.loads одной из перемешанных строк).
        self.assertEqual(len(entries), 24)

    def test_повторный_запуск_не_платит_за_готовые_задачи(self):
        variant = cmd.VARIANTS['luna-luna']
        cmd.resumable_run_variant_concurrent(
            self.problems, variant, self._complete_fn(), self.shortlists,
            str(self.log_path), 'run-1', 'promptver', workers=4)

        calls = []

        def counting_complete_fn(model, blocks, user_text, schema, effort, images=None):
            calls.append(model)
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return _FakeReply(text)

        rows, spent, stopped, skipped, errors = cmd.resumable_run_variant_concurrent(
            self.problems, variant, counting_complete_fn, self.shortlists,
            str(self.log_path), 'run-1', 'promptver', workers=4)

        self.assertEqual(len(calls), 0)
        self.assertEqual(skipped, len(self.problems))

    def test_extra_on_row_зовётся_на_каждую_обработанную_задачу(self):
        """Боевая команда вешает сюда счётчик доли брака (Фаза 2) — без
        вызова автостоп никогда не сработает."""
        variant = cmd.VARIANTS['luna-luna']
        seen = []
        cmd.resumable_run_variant_concurrent(
            self.problems, variant, self._complete_fn(), self.shortlists,
            str(self.log_path), 'run-1', 'promptver', workers=4,
            extra_on_row=lambda row: seen.append(row['problem_id']))
        self.assertEqual(sorted(seen), sorted(p.id for p in self.problems))


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

    def test_with_figure_note_добавляет_маркер_когда_фигура_есть_а_маркера_нет(self):
        problem = _make_problem('Обычное условие про рынок, без маркера.')
        ProblemFigure.objects.create(problem=problem, tikz_hash='abc123',
                                     tikz_source='x')
        text = enrich_text.problem_full_text(problem.statement,
                                             problem.parts.all())
        payload = enrich_text.with_figure_note(text, problem.figures.count())
        self.assertIn('[[FIGURE:', payload)
        self.assertIn('приложено 1 изображение', payload)
        self.assertTrue(payload.startswith(text))

    def test_with_figure_note_склонение_по_числу(self):
        problem = _make_problem('Условие с несколькими картинками.')
        for i in range(3):
            ProblemFigure.objects.create(
                problem=problem, tikz_hash='hash%d' % i, tikz_source='x')
        payload = enrich_text.with_figure_note('текст', problem.figures.count())
        self.assertIn('приложено 3 изображения', payload)

    def test_with_figure_note_не_дублирует_уже_существующий_маркер(self):
        text = 'На рисунке [[FIGURE:deadbeef]] показан спрос.'
        payload = enrich_text.with_figure_note(text, figure_count=1)
        self.assertEqual(payload, text)
        self.assertEqual(payload.count('[[FIGURE:'), 1)

    def test_with_figure_note_без_фигур_текст_не_меняется(self):
        text = 'Обычное условие без картинок вовсе.'
        payload = enrich_text.with_figure_note(text, figure_count=0)
        self.assertEqual(payload, text)
        self.assertNotIn('[[FIGURE:', payload)


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


# Решение владельца 01.09.2026 (Notion «Решения»): модель больше не
# определяет «Реальные данные» и «Нестандартный поворот» — двух особенностей
# из FEATURES_1 не существует нигде под этими файлами/схемой, точка.
# «Нестандартный поворот» как ФРАЗА в тексте якорей сложности (уровень 4/5,
# DIFFICULTY_ANCHORS) — легитимна и не про эту особенность, поэтому в
# проверку взяты только реальные представления убранной особенности:
# код-слаг с подчёркиванием и капитализированная витринная форма, а не
# любое упоминание слов «нестандартный»/«реальные» по отдельности.
_REMOVED_FEATURE_NEEDLES = (
    'реальные_данные', 'нестандартный_поворот',
    'Реальные данные', 'Нестандартный поворот',
)

_REMOVED_FEATURE_SCAN_ROOTS = (
    Path(__file__).resolve().parent.parent / 'enrich',
    Path(__file__).resolve().parent.parent / 'ai',
    Path(__file__).resolve().parent.parent / 'management' / 'commands' /
    'pilot_enrich_v2.py',
)


# ⚠️ СКАНИРУЕМ КОД, А НЕ ТЕКСТ ФАЙЛА, И ЭТО ПРИНЦИПИАЛЬНО.
# Прежняя версия искала подстроку во всём файле целиком и ловила сама себя:
# `problems/enrich/features.py` в первом же абзаце ОБЪЯСНЯЕТ, что «Реальные
# данные» и «Нестандартный поворот» убраны, — и сторож краснел на фразе,
# которая как раз подтверждает, что особенностей нет. Сторож при этом не
# ослаблен: убранная особенность может жить в коде только как строковый
# литерал (элемент FEATURES_1, значение enum, ключ словаря) или как имя
# (переменная, поле, функция), и проверяются именно они. Пояснительная проза —
# комментарии и docstring — кодом не является и в проверку не входит.


def _identifiers(tree):
    """Все имена, объявленные или использованные в модуле."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg


def _code_strings(tree):
    """Строковые литералы модуля, КРОМЕ docstring'ов."""
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        first = node.body[0] if node.body else None
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings):
            yield node.value


def _removed_feature_hits_in_source(source):
    """Следы убранных особенностей в ЗНАЧЕНИЯХ и ИМЕНАХ исходника."""
    tree = ast.parse(source)
    haystack = list(_code_strings(tree)) + list(_identifiers(tree))
    return sorted({needle for needle in _REMOVED_FEATURE_NEEDLES
                   for chunk in haystack if needle in chunk})


def _scan_removed_feature_hits():
    hits = []
    for root in _REMOVED_FEATURE_SCAN_ROOTS:
        paths = [root] if root.is_file() else sorted(
            p for p in root.rglob('*.py') if '__pycache__' not in p.parts)
        for path in paths:
            source = path.read_text(encoding='utf-8')
            for needle in _removed_feature_hits_in_source(source):
                hits.append((str(path), needle))
    return hits


class RemovedFeaturesTests(TestCase):
    """Зубастость сторожа проверяется здесь же, а не «вручную»:
    `test_сторож_краснеет_на_возвращённой_особенности` подсовывает сканеру
    исходник с вернувшейся особенностью и требует, чтобы он её нашёл."""

    def test_сторож_краснеет_на_возвращённой_особенности(self):
        """Убранная особенность в КОДЕ обязана находиться — во всех видах,
        какими она может вернуться."""
        для_каждого = [
            "FEATURES_1 = ('реальные_данные', 'параметры')",
            "SCHEMA = {'enum': ['нестандартный_поворот']}",
            "LABELS = {'реальные_данные': 'Реальные данные'}",
            "реальные_данные = True",
            "def нестандартный_поворот(x):\n    return x",
        ]
        for source in для_каждого:
            with self.subTest(source=source):
                self.assertNotEqual(
                    [], _removed_feature_hits_in_source(source),
                    'сторож проспал возвращённую особенность')

    def test_сторож_не_краснеет_на_пояснительной_прозе(self):
        """Комментарий и docstring, объясняющие, что особенности убраны, —
        это не возвращение особенности. Именно на них сторож ловил сам себя."""
        source = (
            '"""«Реальные данные» и «Нестандартный поворот» убраны '
            'владельцем 01.09.2026."""\n'
            '# реальные_данные и нестандартный_поворот больше не считаются\n'
            "FEATURES_1 = ('параметры',)\n"
        )
        self.assertEqual([], _removed_feature_hits_in_source(source))

    def test_убранные_особенности_нигде_не_встречаются_в_коде(self):
        hits = _scan_removed_feature_hits()
        self.assertEqual(
            hits, [],
            'Найдены следы убранных особенностей «Реальные данные» / '
            '«Нестандартный поворот»: %r' % (hits,))

    def test_features_1_ровно_шесть_без_убранных_особенностей(self):
        self.assertEqual(
            prompts_v2.FEATURES_1,
            (
                'графическое_решение',
                'нужен_график_в_ответе',
                'на_доказательство',
                'целочисленность_или_дискретный_выбор',
                'параметры',
                'бизнесовое',
            ),
            prompts_v2.FEATURES_1)

    def test_схема_вызова_1_не_содержит_убранные_особенности(self):
        schema = prompts_v2.call1_schema()
        enum = schema['properties']['features_1']['items']['enum']
        self.assertNotIn('реальные_данные', enum)
        self.assertNotIn('нестандартный_поворот', enum)
        self.assertEqual(len(enum), 6, enum)


# ---------------------------------------------------------------------------
# Фаза 2Б.1 (2026-09-01): сырой ответ модели целиком — JSONL рядом с
# манифестом, восстановление без обращения к API.
# ---------------------------------------------------------------------------

class RawResponseLogTests(TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.log_path = Path(self.tmp_dir) / 'raw_log.jsonl'

    def test_запись_и_чтение_восстанавливают_поля_без_api(self):
        reply = _FakeReply('{}', input_tokens=100, output_tokens=50,
                           cache_write_tokens=10, cache_read_tokens=20)
        data = {'topic_primary': 'X', 'title_candidate': 'Рынок кофе'}
        cmd.append_raw_log(self.log_path, run_id='r1', prompt_version='pv1',
                           model=cmd.TERRA, problem_id=42, call_name='call1',
                           effort='none', reply=reply, data=data)

        entries = cmd.read_raw_log(self.log_path)

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry['run_id'], 'r1')
        self.assertEqual(entry['prompt_version'], 'pv1')
        self.assertEqual(entry['model'], cmd.TERRA)
        self.assertEqual(entry['problem_id'], 42)
        self.assertEqual(entry['call'], 'call1')
        self.assertEqual(entry['raw_response'], data)
        self.assertEqual(entry['usage']['input_tokens'], 100)
        self.assertEqual(entry['usage']['output_tokens'], 50)
        self.assertEqual(entry['usage']['cache_write_tokens'], 10)
        self.assertEqual(entry['usage']['cache_read_tokens'], 20)

    def test_несколько_вызовов_пишутся_по_одной_строке_каждый(self):
        reply = _FakeReply('{}')
        for i in range(3):
            cmd.append_raw_log(self.log_path, run_id='r1', prompt_version='pv1',
                               model=cmd.TERRA, problem_id=i, call_name='call1',
                               effort=None, reply=reply, data={})
        entries = cmd.read_raw_log(self.log_path)
        self.assertEqual([e['problem_id'] for e in entries], [0, 1, 2])

    def test_чтение_несуществующего_файла_даёт_пустой_список(self):
        missing = Path(self.tmp_dir) / 'нет-такого.jsonl'
        self.assertEqual(cmd.read_raw_log(missing), [])


# ---------------------------------------------------------------------------
# Фаза 2Б.2 (2026-09-01): резюмирование прогона без повторной оплаты —
# повторный запуск на готовых результатах не должен звать API вовсе.
# ---------------------------------------------------------------------------

@override_settings(AI_PRICES=PRICES)
class ResumableRunTests(TestCase):

    def setUp(self):
        self.problems = [_make_problem('Задача %d про равновесие.' % i)
                         for i in range(3)]
        self.shortlists = {p.id: [] for p in self.problems}
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.log_path = Path(self.tmp_dir) / 'raw_log.jsonl'

    def _counting_complete_fn(self):
        calls = []

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            calls.append((model, effort))
            is_call1 = 'topic_primary' in _schema_names(schema)
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return _FakeReply(text)

        return complete_fn, calls

    def test_повторный_прогон_на_готовых_результатах_не_зовёт_api(self):
        variant = cmd.VARIANTS['base']
        complete_fn1, calls1 = self._counting_complete_fn()
        rows1, spent1, stop1, skipped1 = cmd.resumable_run_variant(
            self.problems, variant, complete_fn1, self.shortlists,
            self.log_path, run_id='r1', prompt_version='pv-test')
        self.assertEqual(len(calls1), len(self.problems) * 2)
        self.assertEqual(skipped1, 0)
        self.assertEqual(len(rows1), len(self.problems))

        complete_fn2, calls2 = self._counting_complete_fn()
        rows2, spent2, stop2, skipped2 = cmd.resumable_run_variant(
            self.problems, variant, complete_fn2, self.shortlists,
            self.log_path, run_id='r2', prompt_version='pv-test')
        self.assertEqual(
            len(calls2), 0,
            'повторный прогон на тех же задачах обязан пропустить всё — '
            'ноль обращений к API')
        self.assertEqual(skipped2, len(self.problems))
        self.assertEqual(len(rows2), 0)

    def test_разный_reasoning_effort_не_считается_готовым_на_тех_же_моделях(self):
        """Баг Фазы 5 (боевой пилот, 01.09.2026): `base` и `terra-low`
        зовут ОДНИ И ТЕ ЖЕ модели (Terra/Luna), отличаются только
        `call1_effort` ('none' vs 'low') — старая проверка сравнивала
        только модель и приняла результаты `base` за готовые для
        `terra-low`, тихо пропустив всю ветку (0 обращений к API вместо
        ожидаемых 600 на боевом прогоне)."""
        base = cmd.VARIANTS['base']
        terra_low = cmd.VARIANTS['terra-low']
        self.assertEqual(base['call1_model'], terra_low['call1_model'])
        self.assertEqual(base['call2_model'], terra_low['call2_model'])
        self.assertNotEqual(base['call1_effort'], terra_low['call1_effort'])

        complete_fn1, calls1 = self._counting_complete_fn()
        cmd.resumable_run_variant(
            self.problems, base, complete_fn1, self.shortlists,
            self.log_path, run_id='r-base', prompt_version='pv-shared')

        complete_fn2, calls2 = self._counting_complete_fn()
        rows2, spent2, stop2, skipped2 = cmd.resumable_run_variant(
            self.problems, terra_low, complete_fn2, self.shortlists,
            self.log_path, run_id='r-terra-low', prompt_version='pv-shared')

        self.assertEqual(
            len(calls2), len(self.problems) * 2,
            'ветка с другим effort обязана прогнаться заново, а не '
            'быть принята за уже готовую по чужим результатам')
        self.assertEqual(skipped2, 0)
        self.assertEqual(len(rows2), len(self.problems))

    def test_другая_версия_промпта_не_считается_готовой(self):
        """Резюме матчит по prompt_version — иначе после правки промпта
        резюме молча пропустило бы задачи, разобранные СТАРЫМ текстом."""
        variant = cmd.VARIANTS['base']
        complete_fn1, calls1 = self._counting_complete_fn()
        cmd.resumable_run_variant(
            self.problems, variant, complete_fn1, self.shortlists,
            self.log_path, run_id='r1', prompt_version='pv-old')

        complete_fn2, calls2 = self._counting_complete_fn()
        rows2, spent2, stop2, skipped2 = cmd.resumable_run_variant(
            self.problems, variant, complete_fn2, self.shortlists,
            self.log_path, run_id='r2', prompt_version='pv-new')
        self.assertEqual(len(calls2), len(self.problems) * 2)
        self.assertEqual(skipped2, 0)

    # -----------------------------------------------------------------
    # Мина перегона корпуса (задание сессии 03.09.2026, фаза −1). Журнал
    # резюмирования ключуется версией промпта. Если версию не поднять при
    # изменённом ядре, перегон решит, что корпус уже обработан, и не
    # сделает НИ ОДНОГО вызова — молча, без ошибки, с кодом возврата 0.
    #
    # Версия — не ручной номер (его легко забыть увеличить), а sha256-
    # отпечаток ТЕКСТА обоих ядер: она поднимается сама. Два теста ниже
    # закрывают обе половины: отпечаток реагирует на правку ядра, и на
    # новом отпечатке старый журнал не считается сделанным.
    # -----------------------------------------------------------------

    def test_отпечаток_промпта_меняется_при_правке_ядра(self):
        before = cmd.prompt_fingerprint(True)
        with mock.patch.object(prompts_v2, 'call1_core',
                               return_value='другое ядро вызова 1'):
            after = cmd.prompt_fingerprint(True)
        self.assertNotEqual(
            before, after,
            'отпечаток обязан меняться при изменении текста ядра — иначе '
            'перегон корпуса примет старый журнал за готовый результат')

    def test_новая_версия_промпта_не_видит_старый_журнал_готовым(self):
        """`done_problem_ids_from_log` на журнале, записанном СТАРОЙ версией
        промпта, при новой версии обязан вернуть пустое множество."""
        variant = cmd.VARIANTS['base']
        complete_fn, _calls = self._counting_complete_fn()
        cmd.resumable_run_variant(
            self.problems, variant, complete_fn, self.shortlists,
            self.log_path, run_id='r1', prompt_version='pv-old')

        done_old = cmd.done_problem_ids_from_log(
            self.log_path, 'pv-old', variant)
        self.assertEqual(done_old, {p.id for p in self.problems},
                         'на своей же версии журнал обязан читаться готовым '
                         '— иначе тест ниже ничего не доказывает')

        done_new = cmd.done_problem_ids_from_log(
            self.log_path, 'pv-new', variant)
        self.assertEqual(done_new, set())


# ---------------------------------------------------------------------------
# Фаза 2Б.3 (2026-09-01): репетиция записи `title_candidate`/`title_source`
# на КОПИИ db.sqlite3 — канон не трогается никогда.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Фаза 5 (боевой пилот, 01.09.2026): устойчивость к обрыву сети — у
# владельца постоянно включён VPN, luna-luna упала на 86-й задаче именно
# из-за таймаута. Повтор с нарастающей паузой на transient-отказы
# провайдера (kind='other'/'limit'), без повтора на постоянные (no_key).
# ---------------------------------------------------------------------------

class RetryOnNetworkErrorTests(TestCase):

    def test_повторяет_и_получается_после_двух_transient_отказов(self):
        good_reply = _FakeReply(CALL1_OK_JSON)
        with mock.patch.object(
                providers.OpenAIProvider, 'complete',
                side_effect=[
                    providers.ProviderError('таймаут 1', kind='other'),
                    providers.ProviderError('таймаут 2', kind='other'),
                    good_reply,
                ]) as fake_complete, \
                mock.patch('problems.management.commands.pilot_enrich_v2.time.sleep') as fake_sleep:
            complete_fn = cmd.make_openai_complete_fn()
            reply = complete_fn(cmd.TERRA, ['ядро'], 'текст',
                                {'type': 'object'}, 'none')
        self.assertIs(reply, good_reply)
        self.assertEqual(fake_complete.call_count, 3)
        self.assertEqual(fake_sleep.call_count, 2)
        # нарастающая пауза — вторая ждёт дольше первой.
        waits = [c.args[0] for c in fake_sleep.call_args_list]
        self.assertLess(waits[0], waits[1])

    def test_не_повторяет_на_отсутствии_ключа(self):
        with mock.patch.object(
                providers.OpenAIProvider, 'complete',
                side_effect=providers.ProviderError(
                    'ключ не настроен', kind='no_key')) as fake_complete, \
                mock.patch('problems.management.commands.pilot_enrich_v2.time.sleep') as fake_sleep:
            complete_fn = cmd.make_openai_complete_fn()
            with self.assertRaises(providers.ProviderError):
                complete_fn(cmd.TERRA, ['ядро'], 'текст',
                           {'type': 'object'}, 'none')
        self.assertEqual(fake_complete.call_count, 1)
        fake_sleep.assert_not_called()

    def test_сдаётся_и_кидает_ошибку_после_исчерпания_попыток(self):
        with mock.patch.object(
                providers.OpenAIProvider, 'complete',
                side_effect=providers.ProviderError(
                    'сеть недоступна', kind='other')) as fake_complete, \
                mock.patch('problems.management.commands.pilot_enrich_v2.time.sleep'):
            complete_fn = cmd.make_openai_complete_fn()
            with self.assertRaises(providers.ProviderError):
                complete_fn(cmd.TERRA, ['ядро'], 'текст',
                           {'type': 'object'}, 'none')
        self.assertEqual(fake_complete.call_count, cmd.NETWORK_RETRIES)


class TitleCandidateUpdatesTests(TestCase):

    def test_категория_keep_не_попадает_в_список_на_запись(self):
        keep_problem = _make_problem(
            'Два производителя минеральной воды выбирают объёмы выпуска '
            'одновременно, функции издержек заданы.')
        keep_problem.title = 'Известная задача про олигополию'
        keep_problem.save()
        self.assertEqual(
            title_rules.classify_current_title(
                keep_problem.title, keep_problem.statement),
            title_rules.CATEGORY_KEEP)

        empty_problem = _make_problem('Условие про рынок кофе и налог.')

        rows = [
            {'problem_id': keep_problem.id,
            'call2': {'title_candidate': 'что-то от модели'}},
            {'problem_id': empty_problem.id,
            'call2': {'title_candidate': 'Рынок кофе'}},
        ]
        problems_by_id = {keep_problem.id: keep_problem,
                          empty_problem.id: empty_problem}

        updates = cmd.title_candidate_updates(rows, problems_by_id)
        ids_written = {pid for pid, _, _ in updates}

        self.assertNotIn(keep_problem.id, ids_written)
        self.assertIn(empty_problem.id, ids_written)
        candidate, source = next(
            (c, s) for pid, c, s in updates if pid == empty_problem.id)
        self.assertEqual(candidate, 'Рынок кофе')
        self.assertEqual(source, Problem.TitleSource.MODEL_EMPTY)


class RehearseDbWriteTests(TestCase):

    def _make_sqlite_copy_source(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        db_path = str(Path(tmp_dir) / 'rehearsal_source.sqlite3')
        conn = sqlite3.connect(db_path)
        conn.execute(
            'CREATE TABLE problems_problem (id INTEGER PRIMARY KEY, '
            'title TEXT, statement TEXT, title_candidate TEXT, '
            'title_source TEXT)')
        conn.execute(
            "INSERT INTO problems_problem VALUES "
            "(1, '', 'Условие про рынок кофе.', '', '')")
        conn.execute(
            "INSERT INTO problems_problem VALUES "
            "(2, 'Дуополия Курно', 'Дуополия Курно, два случая.', '', '')")
        conn.commit()
        conn.close()
        return db_path

    def test_репетиция_пишет_в_копию_и_не_трогает_канон(self):
        db_path = self._make_sqlite_copy_source()
        original_bytes = Path(db_path).read_bytes()
        updates = [(1, 'Рынок кофе', Problem.TitleSource.MODEL_EMPTY)]

        tmp_copy_path, invariants = cmd.rehearse_db_write(db_path, updates)

        self.assertEqual(Path(db_path).read_bytes(), original_bytes,
                         'канон db.sqlite3 не должен измениться НИ БАЙТОМ')
        conn = sqlite3.connect(tmp_copy_path)
        row = conn.execute(
            'SELECT title_candidate, title_source FROM problems_problem '
            'WHERE id=1').fetchone()
        untouched = conn.execute(
            'SELECT title_candidate, title_source FROM problems_problem '
            'WHERE id=2').fetchone()
        conn.close()
        self.assertEqual(row, ('Рынок кофе', Problem.TitleSource.MODEL_EMPTY))
        self.assertEqual(untouched, ('', ''))
        self.assertTrue(any('1' in line for line in invariants))


class TikzSourceInPayloadTests(TestCase):
    """§3.5 API_RUN_MASTER: исходник чертежа уходит в вызов 1 текстом.

    Зубастость по каждому правилу отдельно — подстановка, потолок,
    отсутствие дублирования, и главное: НЕ подставлять ссылку на растровый
    файл (в банке она лежит в том же поле `tikz_source`, 2 491 запись из
    2 498 на 02.09.2026).
    """

    TIKZ = (r'\begin{tikzpicture}\draw[->] (0,0) -- (5,0) node {$Q$};'
            r'\draw[->] (0,0) -- (0,5) node {$P$};'
            r'\draw (0,4) -- (4,0) node[right] {$D$};\end{tikzpicture}')

    def test_маркер_заменяется_исходником_чертежа(self):
        problem = _make_problem('На рисунке [[FIGURE:deadbeef]] показан спрос.')
        problem.figures.create(tikz_hash='deadbeef', tikz_source=self.TIKZ)

        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())

        self.assertEqual(stats['replaced'], 1)
        self.assertNotIn('[[FIGURE:deadbeef]]', out)
        self.assertIn(r'\draw (0,4) -- (4,0)', out)
        self.assertIn('ЧЕРТЁЖ К ЗАДАЧЕ', out)
        self.assertIn('КОНЕЦ ЧЕРТЕЖА', out)
        self.assertIn('описание графика', out.lower())

    def test_ссылка_на_растровый_файл_НЕ_подставляется(self):
        """Главный капкан: у 2 491 записи из 2 498 в `tikz_source` лежит
        ссылка на картинку, а не чертёж. Подставить её под заголовком
        «читай как описание графика» — соврать модели."""
        problem = _make_problem('На рисунке [[FIGURE:cafe01]] показан спрос.')
        problem.figures.create(
            tikz_hash='cafe01',
            tikz_source='https://api.solvehub.app/uploads/images/f-2024.png')

        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())

        self.assertEqual(stats['replaced'], 0)
        self.assertEqual(out, problem.statement)
        self.assertNotIn('ЧЕРТЁЖ К ЗАДАЧЕ', out)
        self.assertIn('[[FIGURE:cafe01]]', out)

    def test_потолок_обрезает_и_говорит_об_этом(self):
        long_tikz = (r'\begin{tikzpicture}'
                     + r'\draw (0,0) -- (1,1) node {точка};' * 400
                     + r'\end{tikzpicture}')
        self.assertGreater(enrich_text.count_tokens(long_tikz), 800)
        problem = _make_problem('Смотри [[FIGURE:long01]].')
        problem.figures.create(tikz_hash='long01', tikz_source=long_tikz)

        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())

        self.assertEqual(stats['truncated'], 1)
        self.assertIn('ЧЕРТЁЖ ОБРЕЗАН', out)
        self.assertLess(len(out), len(long_tikz))

        # обрезано РОВНО по потолку, а не «примерно»: сам резак меряется
        # отдельно, чтобы токены обёртки не смазывали проверку
        body, was_cut = enrich_text.truncate_to_tokens(
            long_tikz, enrich_text.TIKZ_MAX_TOKENS)
        self.assertTrue(was_cut)
        self.assertEqual(enrich_text.count_tokens(body),
                         enrich_text.TIKZ_MAX_TOKENS)
        self.assertTrue(long_tikz.startswith(body[:200]),
                        'обрезок обязан быть НАЧАЛОМ исходника, не серединой')

    def test_короткий_чертёж_не_обрезается(self):
        problem = _make_problem('Смотри [[FIGURE:short1]].')
        problem.figures.create(tikz_hash='short1', tikz_source=self.TIKZ)
        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())
        self.assertEqual(stats['truncated'], 0)
        self.assertNotIn('ЧЕРТЁЖ ОБРЕЗАН', out)
        self.assertIn(r'\end{tikzpicture}', out)

    def test_один_чертёж_подставляется_один_раз(self):
        """Тот же маркер дважды в тексте — исходник встаёт один раз, за
        второй копией никто не платит."""
        problem = _make_problem(
            'Сначала [[FIGURE:twice1]], потом снова [[FIGURE:twice1]].')
        problem.figures.create(tikz_hash='twice1', tikz_source=self.TIKZ)

        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())

        self.assertEqual(stats['replaced'], 1)
        self.assertEqual(out.count('ЧЕРТЁЖ К ЗАДАЧЕ'), 1)
        self.assertEqual(out.count('[[FIGURE:twice1]]'), 1)

    def test_два_разных_чертежа_подставляются_оба(self):
        problem = _make_problem('Раз [[FIGURE:aa11]] и два [[FIGURE:bb22]].')
        problem.figures.create(tikz_hash='aa11', tikz_source=self.TIKZ)
        problem.figures.create(tikz_hash='bb22',
                               tikz_source=self.TIKZ.replace('$Q$', '$Y$'))

        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())

        self.assertEqual(stats['replaced'], 2)
        self.assertEqual(out.count('ЧЕРТЁЖ К ЗАДАЧЕ'), 2)
        self.assertIn('$Y$', out)

    def test_чертёж_без_маркера_в_тексте_не_дописывается(self):
        """Нет маркера — за такую задачу отвечает `with_figure_note`,
        дописывать сюда ещё и исходник значило бы платить дважды."""
        problem = _make_problem('Условие вообще без маркера.')
        problem.figures.create(tikz_hash='nomark', tikz_source=self.TIKZ)
        out, stats = enrich_text.with_tikz_sources(
            problem.statement, problem.figures.all())
        self.assertEqual(stats['replaced'], 0)
        self.assertEqual(out, problem.statement)

    def test_база_не_меняется(self):
        problem = _make_problem('Смотри [[FIGURE:keep01]].')
        figure = problem.figures.create(tikz_hash='keep01',
                                        tikz_source=self.TIKZ)
        before_stmt = problem.statement
        before_src = figure.tikz_source

        enrich_text.with_tikz_sources(problem.statement, problem.figures.all())

        problem.refresh_from_db()
        figure.refresh_from_db()
        self.assertEqual(problem.statement, before_stmt)
        self.assertEqual(figure.tikz_source, before_src)

    def test_looks_like_tikz_отличает_код_от_ссылки(self):
        self.assertTrue(enrich_text.looks_like_tikz(self.TIKZ))
        self.assertTrue(enrich_text.looks_like_tikz(r'\begin{axis}\addplot{x};'))
        self.assertFalse(enrich_text.looks_like_tikz(
            'https://iloveeconomics.ru/system/files/images/u1/graph.png'))
        self.assertFalse(enrich_text.looks_like_tikz('234414|ela.png'))
        self.assertFalse(enrich_text.looks_like_tikz(''))


class SolutionHintForCall1Tests(TestCase):
    """Фаза 1 (2026-09-04, реверс §3.4 API_RUN_MASTER): решение подаётся в
    вызов 1 как подсказка об аппарате — только для задач, у которых оно
    есть, с потолком и обязательной защитной формулировкой рядом."""

    def test_нет_решения_блок_не_строится(self):
        block, stats = enrich_text.solution_hint_for_call1('')
        self.assertIsNone(block)
        self.assertEqual(stats, {'sent': False, 'tokens': 0, 'truncated': False})

    def test_короткое_решение_подаётся_целиком_с_защитной_формулировкой(self):
        block, stats = enrich_text.solution_hint_for_call1(
            'Из условия равновесия P=MC находим оптимальный объём выпуска.')
        self.assertTrue(stats['sent'])
        self.assertFalse(stats['truncated'])
        self.assertGreater(stats['tokens'], 0)
        self.assertIn('оптимальный объём выпуска', block)
        # защитная формулировка (Фаза 1.2) обязана стоять РЯДОМ с решением,
        # а не только в ядре — модель читает их вместе.
        self.assertIn('только как подсказка', block.lower())
        self.assertIn('given', block)
        self.assertIn('find', block)
        self.assertIn('РЕШЕНИЕ', block)

    def test_длинное_решение_обрезается_по_потолку_800(self):
        long_solution = 'Шаг решения номер такой-то. ' * 400
        self.assertGreater(enrich_text.count_tokens(long_solution), 800)

        block, stats = enrich_text.solution_hint_for_call1(long_solution)

        self.assertTrue(stats['truncated'])
        self.assertIn('ОБРЕЗАНО', block)

    def test_короткое_решение_не_обрезается(self):
        block, stats = enrich_text.solution_hint_for_call1('Ответ: Q=10.')
        self.assertFalse(stats['truncated'])
        self.assertNotIn('ОБРЕЗАНО', block)


class Call1UserTextSolutionBlockTests(TestCase):
    """`call1_user_text` дописывает блок решения в конец, не трогая старый
    формат (регулярка `_SHORTLIST_RE` теста `test_glm_enrich_run` завязана
    на то, что сразу после шорт-листа идёт `\n\nЗАДАЧА`)."""

    def test_без_решения_текст_не_меняется(self):
        with_block = prompts_v2.call1_user_text('Текст задачи.', ['спрос'])
        without_block = prompts_v2.call1_user_text(
            'Текст задачи.', ['спрос'], solution_block=None)
        self.assertEqual(with_block, without_block)

    def test_блок_решения_дописывается_в_конец(self):
        block = 'РЕШЕНИЕ КАК ПОДСКАЗКА (только как подсказка)'
        out = prompts_v2.call1_user_text(
            'Текст задачи.', ['спрос', 'предложение'], solution_block=block)
        self.assertTrue(out.endswith(block))
        self.assertIn('\n\nЗАДАЧА (условие с подпунктами, без сокращений):'
                      '\nТекст задачи.\n\n' + block, out)

    def test_шорт_лист_остаётся_вычленяемым_регуляркой(self):
        shortlist_re = re.compile(
            r'ШОРТ-ЛИСТ ПОНЯТИЙ ДЛЯ econ_concepts.*?:\n(.*?)\n\nЗАДАЧА', re.DOTALL)
        out = prompts_v2.call1_user_text(
            'Текст задачи.', ['спрос', 'предложение'],
            solution_block='РЕШЕНИЕ-блок')
        m = shortlist_re.search(out)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), 'спрос; предложение')


class SolutionLeakGuardTests(TestCase):
    """Фаза 1.2: величина, выведенная в решении, не имеет права попасть в
    `given`/`find` — общий запрет цифр в этих полях (§12.3) уже ловит это
    структурно, тест закрепляет именно этот сценарий, а не запрет вообще."""

    def _base(self, given='Обобщённое дано без цифр', find='Обобщённая цель'):
        return {
            'topic_primary': taxonomy.theme_ids()[0], 'topics_secondary': [],
            'tags': [taxonomy.tag_ids()[0]], 'given': given, 'find': find,
            'econ_concepts': ['спрос', 'предложение', 'равновесие'],
            'concepts_offlist': [],
            'task_nature': 'расчётная', 'features_1': [],
            'topic_confidence': 'высокая',
        }

    def test_число_из_решения_утёкшее_в_given_ловится(self):
        # Решение содержит Q=19,3 — в условии этого числа нет вовсе.
        data = self._base(given='Равновесный объём Q=19,3 при линейном спросе')
        ok, violations = cmd.validate_call1(data)
        self.assertFalse(ok)
        self.assertTrue(any('given' in v for v in violations))

    def test_число_из_решения_утёкшее_в_find_ловится(self):
        data = self._base(find='Найти, что цена равна 81,3')
        ok, violations = cmd.validate_call1(data)
        self.assertFalse(ok)
        self.assertTrue(any('find' in v for v in violations))

    def test_given_find_без_цифр_проходят(self):
        data = self._base()
        ok, violations = cmd.validate_call1(data)
        self.assertTrue(ok)
        self.assertEqual(violations, [])


class TikzInCall1OnlyTests(TestCase):
    """§3.5: чертёж уходит ТОЛЬКО в вызов 1. В вызове 2 смысл чертежа уже
    несут `given`/`find`, платить за LaTeX второй раз незачем."""

    TIKZ = (r'\begin{tikzpicture}\draw (0,4) -- (4,0) node {$D$};'
            r'\end{tikzpicture}')

    def _run(self, with_tikz):
        problem = _make_problem('Смотри [[FIGURE:c1only]] и найди равновесие.',
                                solution='Решение.', answer='42')
        problem.figures.create(tikz_hash='c1only', tikz_source=self.TIKZ)
        seen = []

        def fake_complete(model, core_blocks, user_text, schema, effort, images=None):
            seen.append(user_text)
            payload = ({'topic_primary': 'MIC-01', 'topics_secondary': [],
                        'tags': ['t'], 'econ_concepts': ['a', 'b', 'c'],
                        'given': 'дано', 'find': 'найти',
                        'task_nature': 'задача'} if len(seen) == 1 else
                       {'search_queries': ['q'] * 8,
                        'problem_type': 'расчётная', 'difficulty': 3})
            return providers.Reply(
                text=json.dumps(payload, ensure_ascii=False),
                input_tokens=10, output_tokens=10, cache_write_tokens=0,
                cache_read_tokens=0, reasoning_tokens=0)

        with override_settings(AI_PRICES=PRICES):
            cmd.run_variant([problem], cmd.VARIANTS['base'], fake_complete,
                            {problem.id: None}, with_tikz=with_tikz)
        return seen

    def test_чертёж_есть_в_вызове_1_и_нет_в_вызове_2(self):
        call1, call2 = self._run(with_tikz=True)
        self.assertIn('ЧЕРТЁЖ К ЗАДАЧЕ', call1)
        self.assertIn(r'\begin{tikzpicture}', call1)
        self.assertNotIn('ЧЕРТЁЖ К ЗАДАЧЕ', call2)
        self.assertNotIn(r'\begin{tikzpicture}', call2)

    def test_без_подстановки_вызов_1_видит_голый_маркер(self):
        call1, _ = self._run(with_tikz=False)
        self.assertIn('[[FIGURE:c1only]]', call1)
        self.assertNotIn('ЧЕРТЁЖ К ЗАДАЧЕ', call1)


def _real_png(size=(20, 20)):
    """Настоящий декодируемый PNG — `prepare_raster_image` открывает байты
    через Pillow, суррогатный заголовок (как в `test_ai_providers.py`,
    там `complete()` картинку не декодирует) здесь не подходит."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, color=(200, 50, 50)).save(buf, format='PNG')
    return buf.getvalue()


class RasterImageForCall1Tests(TestCase):
    """Фаза 0.4 подготовки боевого прогона (02.09.2026): растровая картинка
    условия уходит В КАРТИНКУ вызова 1 — GLM-5.3-Flash подтверждённо её
    читает (реальный вызов, токены изображения в usage). Зубастость по
    четырём случаям: подстановка растра, задача без визуального содержимого
    не получает лишнего, картинка решения не идёт в вызов 1, битые байты не
    роняют сборку."""

    def test_растровая_картинка_условия_идёт_в_список(self):
        problem = _make_problem('На рисунке [[FIGURE:img001]] показан спрос.')
        problem.figures.create(tikz_hash='img001', source_field='statement',
                               content_type='image/png', image_data=_real_png())

        images = enrich_text.images_for_call1(problem.figures.all())

        self.assertEqual(len(images), 1)
        content_type, data = images[0]
        self.assertEqual(content_type, 'image/png')
        self.assertTrue(data)

    def test_задача_без_визуального_содержимого_ничего_не_получает(self):
        problem = _make_problem('Обычная задача без картинок и чертежей.')
        self.assertEqual(enrich_text.images_for_call1(problem.figures.all()), [])

    def test_картинка_только_у_решения_в_вызов_1_не_идёт(self):
        """§3.4/§3.5: решение в вызов 1 не подаётся вовсе — картинка,
        которая иллюстрирует только решение, для понимания УСЛОВИЯ
        бесполезна."""
        problem = _make_problem('Задача без картинки в условии.',
                                solution='Решение с рисунком.')
        problem.figures.create(tikz_hash='sol001', source_field='solution',
                               content_type='image/png', image_data=_real_png())
        self.assertEqual(enrich_text.images_for_call1(problem.figures.all()), [])

    def test_настоящий_tikz_не_дублируется_картинкой(self):
        """Чертёж с реальным TikZ уже уходит текстом (with_tikz_sources) —
        отправить его ЕЩЁ и картинкой значило бы заплатить дважды за одно
        и то же."""
        problem = _make_problem('Смотри [[FIGURE:tikz01]].')
        problem.figures.create(
            tikz_hash='tikz01', source_field='statement',
            tikz_source=r'\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}',
            content_type='image/png', image_data=_real_png())
        self.assertEqual(enrich_text.images_for_call1(problem.figures.all()), [])

    def test_битые_байты_не_роняют_сборку(self):
        """Пустые/повреждённые байты — не крах, а просто отсутствие
        картинки в списке. `ProblemFigure` без реального импорта файла —
        такая же битая ссылка, как и в тексте, только на уровне байтов."""
        problem = _make_problem('Задача с неудавшимся импортом картинки.')
        problem.figures.create(tikz_hash='empty1', source_field='import',
                               content_type='image/png', image_data=b'')
        problem.figures.create(tikz_hash='broken1', source_field='import',
                               content_type='image/png',
                               image_data=b'\x89PNG\r\n\x1a\nnot-a-real-png')

        # не должно бросить исключение
        images = enrich_text.images_for_call1(problem.figures.all())
        self.assertEqual(images, [])

    def test_run_variant_передаёт_картинки_в_complete_fn(self):
        """Сквозная проверка: `run_variant` реально прокидывает картинки в
        `complete_fn`, а не только собирает список сам по себе."""
        problem = _make_problem('На рисунке [[FIGURE:end2end]] показан спрос.')
        problem.figures.create(tikz_hash='end2end', source_field='statement',
                               content_type='image/png', image_data=_real_png())
        seen_images = []

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in _schema_names(schema)
            seen_images.append((is_call1, images))
            text = CALL1_OK_JSON if is_call1 else CALL2_OK_JSON
            return providers.Reply(text=text, input_tokens=10, output_tokens=10)

        with override_settings(AI_PRICES=PRICES):
            cmd.run_variant([problem], cmd.VARIANTS['base'], fake_complete,
                            {problem.id: None})

        call1_images = [images for is_call1, images in seen_images if is_call1][0]
        call2_images = [images for is_call1, images in seen_images if not is_call1][0]
        self.assertEqual(len(call1_images), 1)
        self.assertIn(call2_images, (None, []))


class PrepareRasterImageTests(TestCase):
    """`prepare_raster_image` — конверсия форматов и сжатие по длинной
    стороне (§0.4 задания сессии: PNG/JPEG форматы, остальное —
    сконвертировать; слишком большие — ужать)."""

    def test_маленький_png_не_трогается(self):
        original = _real_png((20, 20))
        content_type, data, stats = enrich_text.prepare_raster_image(
            'image/png', original)
        self.assertEqual(content_type, 'image/png')
        self.assertFalse(stats['converted'])
        self.assertFalse(stats['resized'])

    def test_gif_конвертируется_в_png(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (10, 10), color=(0, 100, 200)).save(buf, format='GIF')

        content_type, data, stats = enrich_text.prepare_raster_image(
            'image/gif', buf.getvalue())

        self.assertEqual(content_type, 'image/png')
        self.assertTrue(stats['converted'])
        self.assertTrue(data.startswith(b'\x89PNG'))

    def test_крупная_картинка_ужимается_по_длинной_стороне(self):
        big = _real_png((3000, 100))
        content_type, data, stats = enrich_text.prepare_raster_image(
            'image/png', big, max_long_side=1000)

        self.assertTrue(stats['resized'])
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            self.assertLessEqual(max(img.size), 1000)

    def test_битые_байты_не_бросают_исключение(self):
        content_type, data, stats = enrich_text.prepare_raster_image(
            'image/png', b'not a real image at all, just garbage bytes')
        self.assertEqual(data, b'')


class GraphicalSolutionMergeTests(TestCase):
    """0-бис.3 (02.09.2026): особенность «Графическое решение» определена
    через РЕШЕНИЕ (§6.1 API_RUN_MASTER), а спрашивается в вызове 1, где
    решения нет вовсе (§3.4) — прямое доказательство (картинка, привязанная
    к solution) физически не может попасть модели в промпт. Объединение по
    ИЛИ с кодовым признаком «есть ProblemFigure у решения» чинит это без
    единого лишнего запроса к модели."""

    def test_есть_у_решения_код_даёт_сигнал(self):
        problem = _make_problem('Задача без картинки в условии.',
                                solution='Решение с рисунком.')
        problem.figures.create(tikz_hash='s1', source_field='solution',
                               content_type='image/png', image_data=b'\x89PNG...')
        self.assertTrue(enrich_text.graphical_solution_signal(problem))

    def test_картинка_только_у_условия_не_считается_сигналом_кода(self):
        """Картинка к УСЛОВИЮ ничего не говорит о том, что РЕШЕНИЕ
        опирается на график — это разные вещи, и код не имеет права их
        путать."""
        problem = _make_problem('Задача с картинкой в условии.')
        problem.figures.create(tikz_hash='s2', source_field='statement',
                               content_type='image/png', image_data=b'\x89PNG...')
        self.assertFalse(enrich_text.graphical_solution_signal(problem))

    def test_нет_фигур_вовсе_сигнала_нет(self):
        problem = _make_problem('Обычная задача без картинок.')
        self.assertFalse(enrich_text.graphical_solution_signal(problem))

    def test_объединение_модель_да_код_нет(self):
        problem = _make_problem('Задача.')
        merged, source = enrich_text.merge_graphical_solution(
            ['графическое_решение'], problem)
        self.assertTrue(merged)
        self.assertEqual(source, 'model')

    def test_объединение_модель_нет_код_да_зубастость(self):
        """ГЛАВНЫЙ случай задания: модель НЕ поставила особенность (текст
        решения без чисел на график не намекает), но у задачи физически
        есть картинка, привязанная к решению — код обязан её всё равно
        засчитать."""
        problem = _make_problem('Задача.', solution='Решение с графиком.')
        problem.figures.create(tikz_hash='s3', source_field='solution',
                               content_type='image/png', image_data=b'\x89PNG...')
        merged, source = enrich_text.merge_graphical_solution([], problem)
        self.assertTrue(merged)
        self.assertEqual(source, 'code')

    def test_объединение_оба_согласны(self):
        problem = _make_problem('Задача.', solution='Решение с графиком.')
        problem.figures.create(tikz_hash='s4', source_field='solution',
                               content_type='image/png', image_data=b'\x89PNG...')
        merged, source = enrich_text.merge_graphical_solution(
            ['графическое_решение'], problem)
        self.assertTrue(merged)
        self.assertEqual(source, 'both')

    def test_объединение_ни_то_ни_другое(self):
        problem = _make_problem('Задача без графиков вовсе.')
        merged, source = enrich_text.merge_graphical_solution([], problem)
        self.assertFalse(merged)
        self.assertEqual(source, 'none')

    def test_пустой_features_1_не_роняет(self):
        problem = _make_problem('Задача.')
        merged, source = enrich_text.merge_graphical_solution(None, problem)
        self.assertFalse(merged)
        self.assertEqual(source, 'none')


class GraphicalSolutionInvariantTests(TestCase):
    """Инвариант §5 задания сессии: число задач с «Графическим решением»
    после объединения печатается вместе с разбивкой модель/код/совпало."""

    def test_счётчик_разбивки_по_рядам(self):
        p_model = _make_problem('Задача A.')
        p_code = _make_problem('Задача B.', solution='Решение.')
        p_code.figures.create(tikz_hash='b1', source_field='solution',
                              content_type='image/png', image_data=b'\x89PNG...')
        p_both = _make_problem('Задача C.', solution='Решение.')
        p_both.figures.create(tikz_hash='c1', source_field='solution',
                              content_type='image/png', image_data=b'\x89PNG...')
        p_none = _make_problem('Задача D.')

        rows = [
            {'problem_id': p_model.id, 'call1': {'features_1': ['графическое_решение']}},
            {'problem_id': p_code.id, 'call1': {'features_1': []}},
            {'problem_id': p_both.id, 'call1': {'features_1': ['графическое_решение']}},
            {'problem_id': p_none.id, 'call1': {'features_1': []}},
        ]
        problems_by_id = {p.id: p for p in (p_model, p_code, p_both, p_none)}

        breakdown = cmd.graphical_solution_breakdown(rows, problems_by_id)

        self.assertEqual(breakdown['model'], 1)
        self.assertEqual(breakdown['code'], 1)
        self.assertEqual(breakdown['both'], 1)
        self.assertEqual(breakdown['none'], 1)
        self.assertEqual(breakdown['total_graphical'], 3)
