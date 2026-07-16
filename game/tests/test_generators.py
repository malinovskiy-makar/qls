"""
Тесты параметрических генераторов Econ Rush (game/generators/).

Два слоя:
1. Контрольные числа из ТЗ — подача параметров в solve() напрямую, минуя
   рандом (класс ControlNumbers*).
2. Свойства на массе: по 500 сэмплов на архетип — ответ «красивый»,
   независимый пересчёт solve() сходится с correct_value через Fraction,
   дистракторы уникальны и ≠ ответу, длины в лимитах, parse_exact_number
   принимает каждый correct_value (класс ArchetypeProperties).
"""
import json
import random
import re
from fractions import Fraction

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from game.generators import base as gbase
from game.generators.base import fmt_num, is_nice, LIMIT_FULL, LIMIT_SHORT
from game.generators.registry import ARCHETYPES
from game.models import GameQuestion
from game.views import parse_exact_number

N_SAMPLES = 500          # сэмплов на архетип (распределяются по трём типам)
MIN_INT_SHARE = 0.6      # доля целых ответов среди numeric (правило ≥80%
                         # держим по построению сеток; в тесте — консервативный
                         # порог против случайного перекоса выборки)


class ArchetypePropertyMixin(object):
    """Общий прогон свойств для одного архетипа."""

    def run_archetype(self, key, validator=None):
        arch = ARCHETYPES[key]
        rng = random.Random(20260714)
        per_type = N_SAMPLES // 3
        int_answers = 0
        numeric_total = 0

        for qtype in ('numeric', 'single', 'boolean'):
            for _ in range(per_type):
                q = gbase.generate_question(arch, rng, qtype)
                params = q['params']
                asked_key = params['_asked']
                solved = arch.solve(params)

                # длины условий в лимитах типа
                limit = LIMIT_FULL if qtype == 'numeric' else LIMIT_SHORT
                self.assertLessEqual(len(q['statement']), limit, q['statement'])
                self.assertGreaterEqual(len(q['statement']), 15)

                # сложность и темы заполнены
                self.assertIn(q['difficulty'], (1, 2, 3, 4, 5))
                self.assertTrue(q['topics'])
                self.assertTrue(q['solution_text'].startswith('1. '))

                # валидность экономики архетипа
                if validator is not None:
                    validator(self, params, solved)

                value = solved[asked_key]
                if isinstance(value, str):
                    # class-вопрос: правильная метка — в вариантах
                    if qtype == 'single':
                        self.assertEqual(
                            q['options'][q['correct_index']], value)
                    else:
                        claim = params['_claim']
                        truth = (claim == value)
                        self.assertEqual(q['correct_index'], 0 if truth else 1)
                    continue

                value = Fraction(value)
                self.assertTrue(is_nice(value), value)

                if qtype == 'numeric':
                    numeric_total += 1
                    if value.denominator == 1:
                        int_answers += 1
                    parsed = parse_exact_number(q['correct_value'])
                    self.assertIsNotNone(parsed, q['correct_value'])
                    # независимый пересчёт сходится с correct_value
                    self.assertEqual(parsed, value)
                    self.assertEqual(q['options'], [])
                elif qtype == 'single':
                    self.assertEqual(len(q['options']), 4)
                    # варианты уникальны, правильный = ответ
                    self.assertEqual(len(set(q['options'])), 4)
                    self.assertEqual(
                        q['options'][q['correct_index']], fmt_num(value))
                    for i, o in enumerate(q['options']):
                        if i != q['correct_index']:
                            self.assertNotEqual(
                                parse_exact_number(o), value)
                            # дистракторы правдоподобны: неотрицательны
                            self.assertGreaterEqual(parse_exact_number(o), 0)
                else:  # boolean
                    self.assertEqual(q['options'], [u'Верно', u'Неверно'])
                    claim = Fraction(str(params['_claim']).replace(',', '.')
                                     if '/' not in str(params['_claim'])
                                     else params['_claim'])
                    truth = (claim == value)
                    self.assertEqual(q['correct_index'], 0 if truth else 1)

        # правило красивого ответа: целые преобладают
        self.assertGreater(numeric_total, 0)
        self.assertGreaterEqual(int_answers / float(numeric_total),
                                MIN_INT_SHARE)


def market_validator(test, params, solved):
    """Экономическая валидность рынка: равновесие в первой четверти."""
    test.assertGreater(solved['p_star'], 0)
    test.assertGreater(solved['q_star'], 0)
    test.assertGreater(params['a'], 0)
    test.assertGreater(params['b'], 0)
    test.assertGreater(params['d'], 0)


class ControlNumbersBlockA(SimpleTestCase):
    """Контрольные числа Задачи 3 — прямые вызовы solve()."""

    def test_equilibrium(self):
        s = ARCHETYPES['equilibrium'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0})
        self.assertEqual(s['p_star'], 50)
        self.assertEqual(s['q_star'], 50)

    def test_shift_equilibrium(self):
        # Qd: 100−P → 130−P (сдвиг спроса +30), Qs = P → P* = 65
        s = ARCHETYPES['shift_equilibrium'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0,
             'side': 'demand', 'delta': 30, 'reason': 0})
        self.assertEqual(s['p_new'], 65)
        self.assertEqual(s['q_new'], 65)
        self.assertEqual(s['dp_abs'], 15)
        self.assertEqual(s['dq_abs'], 15)

    def test_tax(self):
        s = ARCHETYPES['tax_subsidy'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0,
             'kind': 'tax', 'rate': 20})
        self.assertEqual(s['pb'], 60)
        self.assertEqual(s['ps'], 40)
        self.assertEqual(s['q1'], 40)
        self.assertEqual(s['budget'], 800)
        self.assertEqual(s['dwl'], 100)
        self.assertEqual(s['share_buyers'], 50)

    def test_subsidy(self):
        s = ARCHETYPES['tax_subsidy'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0,
             'kind': 'subsidy', 'rate': 20})
        self.assertEqual(s['q1'], 60)
        self.assertEqual(s['budget'], 1200)
        self.assertEqual(s['dwl'], 100)
        self.assertEqual(s['pb'], 40)
        self.assertEqual(s['ps'], 60)

    def test_price_control(self):
        # потолок P = 30 при равновесии 50 → дефицит 40
        s = ARCHETYPES['price_control'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0,
             'kind': 'ceiling', 'limit': 30})
        self.assertEqual(s['gap'], 40)
        self.assertEqual(s['q_sold'], 30)
        self.assertEqual(s['q_d'], 70)

    def test_elasticity_point(self):
        s = ARCHETYPES['elasticity_point'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0, 'curve': 'demand'})
        self.assertEqual(s['e_abs'], 1)
        self.assertIn(u'единичная', s['e_class'])

    def test_elasticity_arc(self):
        # (P=40, Q=60) → (P=60, Q=40): |E| = 1, выручка не меняется
        s = ARCHETYPES['elasticity_arc'].solve(
            {'p1': 40, 'p2': 60, 'q1': 60, 'q2': 40, 'good': 0})
        self.assertEqual(s['e_arc'], 1)
        self.assertEqual(s['rev_class'], u'не изменится')
        self.assertEqual(s['dr_abs'], 0)

    def test_surplus(self):
        s = ARCHETYPES['surplus'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0})
        self.assertEqual(s['cs'], 1250)
        self.assertEqual(s['ps'], 1250)
        self.assertEqual(s['total'], 2500)


class ControlNumbersBlockB(SimpleTestCase):
    """Контрольные числа Задачи 4 (TC = 100 + 20Q + 4Q²)."""

    def test_costs_tc(self):
        s = ARCHETYPES['costs_tc'].solve(
            {'F': 100, 'g': 20, 'h': 4, 'q0': 5, 'good': 0})
        self.assertEqual(s['fc'], 100)
        self.assertEqual(s['q_min'], 5)
        self.assertEqual(s['atc_min'], 60)
        self.assertEqual(s['mc0'], 60)
        self.assertEqual(s['avc0'], 40)

    def test_comp_firm(self):
        s = ARCHETYPES['comp_firm'].solve(
            {'F': 100, 'g': 20, 'h': 4, 'p': 100, 'good': 0})
        self.assertEqual(s['q_star'], 10)
        self.assertEqual(s['profit'], 300)
        self.assertEqual(s['revenue'], 1000)

    def test_monopoly_etalon_aqualine(self):
        """Эталон «Аквалайн», утверждённый преподавателем 2026-07-16.

        Спрос Q = (120 − P)/2 ⇒ a = 120, b = 2; MC = 20, FC = 100.
        MR = 120 − 4Q = 20 ⇒ Q_m = 25; P_m = 70;
        π = 70·25 − (20·25 + 100) = 1750 − 600 = 1150 тыс. руб.
        Эти числа — договорённость с владельцем, а не деталь реализации:
        поедут они — поедет и планка качества."""
        s = ARCHETYPES['monopoly'].solve(
            {'a': 120, 'b': 2, 'mc': 20, 'fc': 100, 'story': 0})
        self.assertEqual(s['q_m'], 25)
        self.assertEqual(s['p_m'], 70)
        self.assertEqual(s['revenue'], 1750)
        self.assertEqual(s['total_cost'], 600)
        self.assertEqual(s['profit'], 1150)
        self.assertEqual(s['q_c'], 50)
        self.assertEqual(s['dwl'], 625)

    def test_monopoly_fixed_costs_do_not_move_the_optimum(self):
        """Постоянные издержки не влияют на выпуск и цену — только на прибыль.

        Это главная мысль решения архетипа; если она сломается, разбор будет
        объяснять то, чего в числах нет."""
        arch = ARCHETYPES['monopoly']
        a = arch.solve({'a': 120, 'b': 2, 'mc': 20, 'fc': 100, 'story': 0})
        b = arch.solve({'a': 120, 'b': 2, 'mc': 20, 'fc': 500, 'story': 0})
        self.assertEqual(a['q_m'], b['q_m'])
        self.assertEqual(a['p_m'], b['p_m'])
        self.assertEqual(a['dwl'], b['dwl'])
        self.assertEqual(a['profit'] - b['profit'], 400)   # ровно разница FC


class ControlNumbersBlockV(SimpleTestCase):
    """Контрольные числа Задачи 5 (КПВ и торговля)."""

    def test_ppf_single(self):
        # 60X/30Y: альт. стоимость 1X = 0,5Y; точка (40; 10) — на границе
        s = ARCHETYPES['ppf_single'].solve(
            {'mx': 60, 'my': 30, 'x0': 40, 'y0': 10, 'gx': 0, 'gy': 1})
        self.assertEqual(s['oc_x'], Fraction(1, 2))
        self.assertEqual(s['y_at_x'], 10)
        self.assertIn(u'на границе', s['point_class'])

    def test_ppf_joint(self):
        # A(60X/30Y) + B(20X/40Y) → излом (60; 40); при X = 70 → Y = 20
        base = {'mxa': 60, 'mya': 30, 'mxb': 20, 'myb': 40,
                'gx': 0, 'gy': 1}
        s = ARCHETYPES['ppf_joint'].solve(dict(base, x0=70))
        self.assertEqual(s['kink_x'], 60)
        self.assertEqual(s['kink_y'], 40)
        self.assertEqual(s['y_at_x'], 20)
        self.assertEqual(s['total_max_x'], 80)
        self.assertEqual(s['total_max_y'], 70)

    def test_comparative_advantage(self):
        # преимущество по X у Альфы; цена 1X между 0,5Y и 2Y
        s = ARCHETYPES['comparative_advantage'].solve(
            {'mxa': 60, 'mya': 30, 'mxb': 20, 'myb': 40, 'gx': 0, 'gy': 1})
        self.assertEqual(s['adv_x'], u'страна Альфа')
        self.assertEqual(s['adv_y'], u'страна Бета')
        self.assertEqual(s['price_low'], Fraction(1, 2))
        self.assertEqual(s['price_high'], 2)


class ControlNumbersBlockG(SimpleTestCase):
    """Контрольные числа Задачи 6 (макро-лайт)."""

    def test_mpc_multiplier(self):
        # MPC = 0,8 → мультипликатор 5; ΔG = 20 → ΔВВП = 100
        s = ARCHETYPES['mpc_multiplier'].solve(
            {'mpc': '0,8', 'dg': 20, 'variant': 'given_dg'})
        self.assertEqual(s['mult'], 5)
        self.assertEqual(s['dgdp'], 100)
        s2 = ARCHETYPES['mpc_multiplier'].solve(
            {'mpc': '0,8', 'dy': 100, 'variant': 'need_dy'})
        self.assertEqual(s2['dg_needed'], 20)

    def test_labor_minwage(self):
        # Ld = 100 − 2W, Ls = −20 + 4W → W* = 20, L* = 60; МРОТ 25 → 30
        s = ARCHETYPES['labor_minwage'].solve(
            {'a': 100, 'b': 2, 'c': -20, 'd': 4, 'wm': 25})
        self.assertEqual(s['w_star'], 20)
        self.assertEqual(s['l_star'], 60)
        self.assertEqual(s['unemployment'], 30)
        self.assertEqual(s['employment'], 50)


class ControlNumbersBonus(SimpleTestCase):
    """Контрольные числа бонус-архетипов 16–17."""

    def test_price_index(self):
        # (10 шт: 4→6) + (5 шт: 8→8) → индекс 125 %, инфляция 25 %
        s = ARCHETYPES['price_index'].solve(
            {'n1': 10, 'n2': 5, 'p1_0': 4, 'p1_1': 6,
             'p2_0': 8, 'p2_1': 8, 'g1': 0, 'g2': 1})
        self.assertEqual(s['cost0'], 80)
        self.assertEqual(s['cost1'], 100)
        self.assertEqual(s['index'], 125)
        self.assertEqual(s['inflation'], 25)

    def test_perfect_price_discrimination(self):
        # P = 100 − Q, MC = 20 → выпуск 80, прибыль 3200 (без FC)
        s = ARCHETYPES['perfect_price_discrimination'].solve(
            {'a': 100, 'b': 1, 'mc': 20, 'good': 0})
        self.assertEqual(s['q_pd'], 80)
        self.assertEqual(s['profit_pd'], 3200)
        self.assertEqual(s['q_m'], 40)
        self.assertEqual(s['profit_m'], 1600)
        self.assertEqual(s['extra'], 1600)


class ArchetypeProperties(SimpleTestCase, ArchetypePropertyMixin):
    """500 сэмплов на каждый архетип."""

    def test_equilibrium(self):
        self.run_archetype('equilibrium', market_validator)

    def test_shift_equilibrium(self):
        def v(test, params, solved):
            test.assertGreater(solved['p_new'], 0)
            test.assertGreater(solved['q_new'], 0)
            test.assertGreater(solved['p0'], 0)
            test.assertGreater(solved['q0'], 0)
        self.run_archetype('shift_equilibrium', v)

    def test_tax_subsidy(self):
        def v(test, params, solved):
            # вмешательство не убивает рынок, цены в первой четверти
            test.assertGreater(solved['q1'], 0)
            test.assertGreater(solved['pb'], 0)
            test.assertGreater(solved['ps'], 0)
            test.assertEqual(Fraction(solved['dwl']).denominator, 1)
        self.run_archetype('tax_subsidy', v)

    def test_price_control(self):
        def v(test, params, solved):
            # ограничение связывает: потолок ниже P*, пол выше
            if params['kind'] == 'ceiling':
                test.assertLess(params['limit'], solved['p0'])
            else:
                test.assertGreater(params['limit'], solved['p0'])
            test.assertGreater(solved['q_d'], 0)
            test.assertGreater(solved['q_s'], 0)
        self.run_archetype('price_control', v)

    def test_elasticity_point(self):
        def v(test, params, solved):
            test.assertGreater(solved['p_star'], 0)
            test.assertGreater(solved['q_star'], 0)
            test.assertGreater(solved['e_abs'], 0)
        self.run_archetype('elasticity_point', v)

    def test_elasticity_arc(self):
        def v(test, params, solved):
            test.assertGreater(params['p2'], params['p1'])
            test.assertGreater(params['q1'], params['q2'])
            test.assertGreater(params['q2'], 0)
            test.assertGreater(solved['e_arc'], 0)
            # тождество: |E| > 1 ⟺ выручка при росте цены падает
            if solved['e_arc'] > 1:
                test.assertEqual(solved['rev_class'], u'снизится')
            elif solved['e_arc'] < 1:
                test.assertEqual(solved['rev_class'], u'вырастет')
            else:
                test.assertEqual(solved['rev_class'], u'не изменится')
        self.run_archetype('elasticity_arc', v)

    def test_surplus(self):
        def v(test, params, solved):
            market_validator(test, params, solved)
            # валидный треугольник PS: цена предложения при Q=0 неотрицательна
            test.assertLessEqual(params['c'], 0)
            test.assertGreater(solved['cs'], 0)
            test.assertGreater(solved['ps'], 0)
        self.run_archetype('surplus', v)

    def test_costs_tc(self):
        def v(test, params, solved):
            test.assertGreater(params['F'], 0)
            test.assertGreater(params['h'], 0)
            test.assertGreater(params['q0'], 0)
            test.assertGreater(solved['q_min'], 0)
            # тождество: в минимуме ATC = MC
            test.assertEqual(solved['atc_min'],
                             params['g'] + 2 * params['h'] * solved['q_min'])
        self.run_archetype('costs_tc', v)

    def test_comp_firm(self):
        def v(test, params, solved):
            test.assertGreater(solved['q_star'], 0)
            test.assertGreater(solved['profit'], 0)
            test.assertGreater(params['F'], 0)
            # P = MC в оптимуме
            test.assertEqual(
                params['p'],
                params['g'] + 2 * params['h'] * solved['q_star'])
        self.run_archetype('comp_firm', v)

    def test_monopoly(self):
        def v(test, params, solved):
            test.assertGreater(solved['q_m'], 0)
            test.assertGreater(solved['p_m'], params['mc'])  # наценка положительна
            test.assertEqual(solved['q_c'], 2 * solved['q_m'])
            # Прибыль ДО постоянных издержек = b·Q_m² = 2·DWL. С появлением FC
            # (переработка под эталон) прибыль на них меньше — инвариант
            # теперь связывает DWL с прибылью ПЛЮС постоянные издержки.
            test.assertEqual(solved['dwl'] * 2,
                             solved['profit'] + Fraction(params['fc']))
            test.assertEqual(Fraction(solved['dwl']).denominator, 1)
            # Прибыль положительна — иначе сюжет «директор максимизирует
            # прибыль» описывает фирму, которой выгодно закрыться.
            test.assertGreater(solved['profit'], 0)
            test.assertEqual(solved['revenue'], solved['p_m'] * solved['q_m'])
        self.run_archetype('monopoly', v)

    def test_ppf_single(self):
        def v(test, params, solved):
            test.assertGreater(params['mx'], 0)
            test.assertGreater(params['my'], 0)
            test.assertGreater(params['x0'], 0)
            test.assertGreater(solved['y_at_x'], 0)
            # взаимно обратные альтернативные стоимости
            test.assertEqual(solved['oc_x'] * solved['oc_y'], 1)
        self.run_archetype('ppf_single', v)

    def test_ppf_joint(self):
        def v(test, params, solved):
            test.assertGreater(solved['y_at_x'], 0)
            test.assertGreater(solved['kink_x'], 0)
            test.assertGreater(solved['kink_y'], 0)
            test.assertLess(solved['kink_y'], solved['total_max_y'])
        self.run_archetype('ppf_joint', v)

    def test_comparative_advantage(self):
        def v(test, params, solved):
            # преимущества противоположны, диапазон невырожден
            test.assertNotEqual(solved['adv_x'], solved['adv_y'])
            test.assertLess(solved['price_low'], solved['price_high'])
        self.run_archetype('comparative_advantage', v)

    def test_mpc_multiplier(self):
        def v(test, params, solved):
            test.assertGreater(solved['mult'], 1)
            mpc = Fraction(str(params['mpc']).replace(',', '.'))
            test.assertEqual(solved['mult'] * (1 - mpc), 1)
        self.run_archetype('mpc_multiplier', v)

    def test_price_index(self):
        def v(test, params, solved):
            test.assertGreater(params['p1_1'], 0)
            test.assertGreater(params['p2_1'], 0)
            test.assertGreater(solved['cost0'], 0)
            # по построению инфляция положительна
            test.assertGreater(solved['index'], 100)
        self.run_archetype('price_index', v)

    def test_perfect_price_discrimination(self):
        def v(test, params, solved):
            test.assertGreater(params['a'], params['mc'])
            test.assertGreater(solved['q_pd'], 0)
            test.assertGreater(solved['profit_pd'], 0)
            # дискриминация ровно удваивает прибыль линейной монополии
            test.assertEqual(solved['profit_pd'], 2 * solved['profit_m'])
        self.run_archetype('perfect_price_discrimination', v)

    def test_labor_minwage(self):
        def v(test, params, solved):
            test.assertGreater(solved['w_star'], 0)
            test.assertGreater(solved['l_star'], 0)
            # МРОТ связывает: выше равновесной ставки, занятость жива
            test.assertGreater(params['wm'], solved['w_star'])
            test.assertGreater(solved['employment'], 0)
            test.assertGreater(solved['unemployment'], 0)
        self.run_archetype('labor_minwage', v)


def make_generated_question(**kw):
    """Минимальный сгенерированный вопрос для тестов хранения/выдачи."""
    defaults = dict(
        problem=None, part=None,
        question_type='numeric',
        question=u'Тестовый сгенерированный вопрос: чему равно 2 + 2?',
        options=[],
        correct_value='4',
        difficulty=2,
        topics=[u'Спрос и предложение'],
        lang='ru',
        unit=u'ден. ед.',
        is_generated=True,
        generator_key='equilibrium',
        gen_params={'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0,
                    '_asked': 'p_star', '_wrapper': 'city'},
        gen_solution=u'1. Шаг решения.',
    )
    defaults.update(kw)
    return GameQuestion.objects.create(**defaults)


class StorageTests(TestCase):
    """Хранение: build_game_pool не трогает сгенерированные,
    generate_game_questions пишет и переписывает, purge_generated
    возвращает пул ровно к исходному состоянию."""

    def test_build_game_pool_preserves_generated(self):
        from problems.models import Problem
        p = Problem.objects.create(
            statement=u'Тестовая задача-источник', status='draft',
            problem_type=u'тест: один ответ')
        GameQuestion.objects.create(
            problem=p, question_type='single',
            question=u'Старый вопрос из теста', options=['1', '2'],
            correct_index=0, lang='ru')
        gen = make_generated_question()

        call_command('build_game_pool', verbosity=0)

        # сгенерированный жив, вопрос из теста пересобран (кандидатов нет → 0)
        self.assertTrue(
            GameQuestion.objects.filter(pk=gen.pk, is_generated=True).exists())
        self.assertEqual(
            GameQuestion.objects.filter(is_generated=False).count(), 0)

    def test_generate_and_purge_roundtrip(self):
        baseline = make_generated_question(
            generator_key='__manual__').pk  # чужой ключ не должен удаляться
        call_command('generate_game_questions', '--per-archetype', '2',
                     '--confirm', '--only', 'equilibrium', verbosity=0)
        n_eq = GameQuestion.objects.filter(
            is_generated=True, generator_key='equilibrium').count()
        self.assertEqual(n_eq, 6)  # 2 вопроса × 3 типа
        self.assertTrue(GameQuestion.objects.filter(pk=baseline).exists())

        # повторный запуск того же ключа не плодит дубли
        call_command('generate_game_questions', '--per-archetype', '2',
                     '--confirm', '--only', 'equilibrium', verbosity=0)
        self.assertEqual(GameQuestion.objects.filter(
            is_generated=True, generator_key='equilibrium').count(), 6)

        call_command('purge_generated', verbosity=0)
        self.assertEqual(
            GameQuestion.objects.filter(is_generated=True).count(), 0)


class ServingTests(TestCase):
    """Выдача: флаг GAME_GENERATED_ENABLED, анти-чит, решение в разборе."""

    def _start_session(self, mode='classic'):
        return self.client.get('/game/api/session/start/?mode=' + mode)

    def test_flag_off_excludes_generated(self):
        make_generated_question()
        with self.settings(GAME_GENERATED_ENABLED=False):
            resp = self._start_session()
            # других numeric в пуле нет → пул пуст
            self.assertEqual(resp.status_code, 503)

    def test_flag_on_serves_generated_with_anticheat(self):
        gq = make_generated_question()
        with self.settings(GAME_GENERATED_ENABLED=True):
            resp = self._start_session()
            self.assertEqual(resp.status_code, 200)
            q = resp.json()['question']
            self.assertEqual(q['id'], gq.pk)
            self.assertTrue(q['generated'])
            self.assertIsNone(q['problem_id'])
            self.assertEqual(q.get('unit'), u'ден. ед.')
            # анти-чит: ни ответа, ни решения в payload вопроса
            payload_text = str(q)
            self.assertNotIn('correct', payload_text)
            self.assertNotIn(u'Шаг решения', payload_text)

            # неверный ответ → решение приходит в разборе
            resp = self.client.post(
                '/game/api/answer/',
                data='{"question_id": %d, "value": "5"}' % gq.pk,
                content_type='application/json')
            data = resp.json()
            self.assertEqual(data['result'], 'wrong')
            self.assertEqual(data['correct_value'], '4')
            self.assertEqual(data['solution'], u'1. Шаг решения.')

    def test_game_page_counts_respect_flag(self):
        import json as _json
        import re as _re
        make_generated_question()

        def classic_count():
            resp = self.client.get('/game/')
            m = _re.search(r'"pool_counts": ({[^}]+})',
                           resp.content.decode('utf-8'))
            return _json.loads(m.group(1))['classic']

        with self.settings(GAME_GENERATED_ENABLED=False):
            self.assertEqual(classic_count(), 0)
        with self.settings(GAME_GENERATED_ENABLED=True):
            self.assertEqual(classic_count(), 1)


class FlagHoldsEverywhereTests(TestCase):
    """Флаг GAME_GENERATED_ENABLED=False — герметичен на ВСЕХ поверхностях.

    Тесты выше проверяют флаг на пустом пуле (нет базовых вопросов → 503).
    Здесь ситуация как на проде: пул СМЕШАННЫЙ — базовые вопросы из тестов
    и сгенерированные лежат рядом. Вопрос теста один: может ли игрок при
    выключенном флаге хоть как-нибудь получить сгенерированный вопрос.

    Поверхностей четыре (все ходят через views._pool_qs): счётчики и чипы
    тем стартовой страницы, выбор вопроса в забеге, очередь работы над
    ошибками, ответ на вопрос по id.
    """
    TOPIC = u'Спрос и предложение'

    def setUp(self):
        from problems.models import Problem
        self.source = Problem.objects.create(
            statement=u'Задача-источник для игровых тестов', status='draft',
            problem_type=u'тест: один ответ')

    def make_base(self, n, topic=None):
        """n базовых (не сгенерированных) вопросов режима Блиц."""
        out = []
        for i in range(n):
            out.append(GameQuestion.objects.create(
                problem=self.source if i == 0 else None,
                question_type='single',
                question=u'Базовый вопрос №{}'.format(i),
                options=['а', 'б', 'в'], correct_index=0,
                topics=[topic or self.TOPIC], lang='ru', is_generated=False))
        return out

    def make_gen(self, n, topic=None):
        return [make_generated_question(
            question_type='single', question=u'Сгенерированный №{}'.format(i),
            options=['а', 'б', 'в'], correct_index=0, correct_value='',
            topics=[topic or self.TOPIC])
            for i in range(n)]

    def test_flag_off_never_serves_generated_in_a_whole_run(self):
        """Забег до исчерпания пула: ни одного сгенерированного вопроса.

        Базовых мало, сгенерированных много — если бы флаг протекал,
        случайная выдача почти наверняка выдала бы сгенерированный."""
        base_ids = {g.pk for g in self.make_base(3)}
        self.make_gen(40)
        with self.settings(GAME_GENERATED_ENABLED=False):
            r = self.client.get('/game/api/session/start/?mode=blitz').json()
            served = [r['question']['id']]
            while True:
                nxt = self.client.get('/game/api/question/').json()
                if 'question' not in nxt:
                    break
                served.append(nxt['question']['id'])
        self.assertEqual(len(served), 3)          # пул кончился на базовых
        self.assertEqual(set(served), base_ids)   # сгенерированных не было
        self.assertEqual(
            GameQuestion.objects.filter(id__in=served, is_generated=True).count(), 0)

    def test_flag_off_hides_topic_chip_of_generated_only_topic(self):
        """Тема, которая держится только на сгенерированных, чипом не встаёт.

        Иначе игрок ткнул бы в чип и получил пустой забег (503)."""
        # MIN_TOPIC_POOL=30 — берём с запасом, тема канонична
        self.make_gen(35, topic=self.TOPIC)

        def has_chip():
            html = self.client.get('/game/').content.decode('utf-8')
            return 'data-topic="{}"'.format(self.TOPIC) in html

        with self.settings(GAME_GENERATED_ENABLED=False):
            self.assertFalse(has_chip())
        with self.settings(GAME_GENERATED_ENABLED=True):
            self.assertTrue(has_chip())

    def test_flag_off_mistakes_run_pulls_no_generated(self):
        """Работа над ошибками — курированная очередь, отдельная поверхность.

        Ошибаемся в теме, где сгенерированных вопросов больше, чем базовых:
        при выключенном флаге в целевой забег не должен попасть ни один."""
        self.make_base(4)
        self.make_gen(40)
        with self.settings(GAME_GENERATED_ENABLED=False):
            r = self.client.get('/game/api/session/start/?mode=blitz').json()
            qid = r['question']['id']
            self.client.post(              # неверный ответ → ошибка в теме
                '/game/api/answer/',
                json.dumps({'question_id': qid, 'choice': 1}),
                content_type='application/json')
            self.client.post('/game/api/session/finish/',
                             json.dumps({'reason': 'time'}),
                             content_type='application/json')
            d = self.client.get('/game/api/session/start_mistakes/').json()
            served = [d['question']['id']]
            while True:
                nxt = self.client.get('/game/api/question/').json()
                if 'question' not in nxt:
                    break
                served.append(nxt['question']['id'])
        self.assertEqual(
            GameQuestion.objects.filter(id__in=served, is_generated=True).count(), 0)

    def test_flag_off_rejects_answer_to_generated_question_by_id(self):
        """Прямой POST по id сгенерированного вопроса — не лазейка.

        Вопрос не выдавался (его нет в state['seen']) → 404, ответ и
        решение наружу не уходят."""
        self.make_base(2)
        gen = self.make_gen(1)[0]
        with self.settings(GAME_GENERATED_ENABLED=False):
            self.client.get('/game/api/session/start/?mode=blitz')
            r = self.client.post(
                '/game/api/answer/',
                json.dumps({'question_id': gen.pk, 'choice': 0}),
                content_type='application/json')
        self.assertEqual(r.status_code, 404)
        self.assertNotIn('solution', r.json())


# Архетипы, переработанные под ЭТАЛОН качества (решение в Notion, 2026-07-16:
# сюжет-библиотека, полное решение, целочисленные параметры, график у
# графических). Список растёт по мере переработки — планка проверяется
# только для них; остальные ждут очереди и держатся выключенным флагом.
ETALON_ARCHETYPES = ['monopoly', 'equilibrium', 'tax_subsidy', 'ppf_single']
# Графические из них — обязаны отдавать чертёж к развёрнутому вопросу.
ETALON_WITH_FIGURE = ['monopoly', 'equilibrium', 'tax_subsidy', 'ppf_single']

MIN_STATEMENT_LEN = 250     # солидный абзац с мотивацией, а не две строки
MIN_SOLUTION_STEPS = 3      # решение с рассуждением, а не «MR=MC ⇒ Q=25»
MIN_STORIES = 3             # библиотека сюжетов, а не один шаблон


class EtalonQualityTests(TestCase):
    """Планка качества сгенерированных задач (эталон «Аквалайн»).

    Проверяем не «работает ли генератор», а «достойна ли задача сайта»:
    длину сюжета, ровно один числовой вопрос с единицами, глубину решения,
    точность ответа и наличие чертежа. Эти проверки — машинная часть
    договорённости с преподавателем; вкус («интересно ли читать») по-прежнему
    смотрит он сам по HTML-предпросмотру.
    """
    SAMPLES = 60

    def each(self, key):
        rng = random.Random(20260716)
        arch = ARCHETYPES[key]
        for _ in range(self.SAMPLES):
            yield arch, gbase.generate_question(arch, rng, 'numeric')

    def test_statement_is_a_real_story(self):
        """Условие — абзац с сюжетом, а не две строки с формулой."""
        for key in ETALON_ARCHETYPES:
            for _, q in self.each(key):
                self.assertGreaterEqual(
                    len(q['statement']), MIN_STATEMENT_LEN,
                    u'{}: сюжет короче эталона: {}'.format(key, q['statement']))
                self.assertLessEqual(len(q['statement']), gbase.LIMIT_FULL)

    def test_exactly_one_numeric_question_with_units(self):
        """В Классике — РОВНО ОДИН числовой вопрос, и у него есть единицы.

        Два вопроса в карточке забега = игрок не знает, что вводить."""
        for key in ETALON_ARCHETYPES:
            for _, q in self.each(key):
                asks = q['statement'].count('?') + len(re.findall(
                    u'(Найдите|Определите)', q['statement']))
                self.assertEqual(asks, 1,
                                 u'{}: вопросов не один: {}'.format(
                                     key, q['statement']))
                self.assertTrue(q['unit'], u'{}: у ответа нет единиц'.format(key))

    def test_solution_has_steps_and_reasoning(self):
        """Решение — пронумерованные шаги с рассуждением, не одна строка."""
        for key in ETALON_ARCHETYPES:
            for _, q in self.each(key):
                steps = [l for l in q['solution_text'].split('\n') if l.strip()]
                self.assertGreaterEqual(
                    len(steps), MIN_SOLUTION_STEPS,
                    u'{}: решение из {} шагов'.format(key, len(steps)))
                self.assertRegex(q['solution_text'], r'^1\. ')

    def test_answer_is_exact_and_recomputable(self):
        """correct_value — точное число, сходится с независимым solve()."""
        for key in ETALON_ARCHETYPES:
            for arch, q in self.each(key):
                parsed = parse_exact_number(q['correct_value'])
                self.assertIsNotNone(parsed, q['correct_value'])
                solved = arch.solve(q['params'])
                self.assertEqual(parsed, Fraction(solved[q['params']['_asked']]))
                self.assertTrue(is_nice(parsed))

    def test_story_library_is_not_one_template(self):
        """Сюжетов несколько и они реально разные (по тексту, не по числам)."""
        for key in ETALON_ARCHETYPES:
            keys, openings = set(), set()
            for _, q in self.each(key):
                keys.add(q['params'].get('story'))
                openings.add(q['statement'][:40])   # завязка, до чисел
            self.assertGreaterEqual(
                len(keys), MIN_STORIES,
                u'{}: сюжетов всего {}'.format(key, len(keys)))
            self.assertGreaterEqual(len(openings), MIN_STORIES)

    def test_difficulty_is_not_glued_to_prose_length(self):
        """Сложность — про экономику, а не про длину решения.

        Развёрнутые решения длинные у всех вопросов архетипа; если бы
        сложность считалась по числу строк, она была бы у всех одна."""
        for key in ETALON_ARCHETYPES:
            diffs = {q['difficulty'] for _, q in self.each(key)}
            self.assertGreater(
                len(diffs), 1, u'{}: сложность у всех одна: {}'.format(key, diffs))
            for d in diffs:
                self.assertIn(d, (1, 2, 3, 4, 5))

    def test_graphical_archetypes_return_a_valid_figure(self):
        """Чертёж есть, и он по схеме _figure (роли известны рисователю)."""
        from game.generators import _figure
        for key in ETALON_WITH_FIGURE:
            for _, q in self.each(key):
                fig = q['figure']
                self.assertIsNotNone(fig, u'{}: нет чертежа'.format(key))
                self.assertGreater(fig['xmax'], 0)
                self.assertGreater(fig['ymax'], 0)
                self.assertTrue(fig['xlabel'] and fig['ylabel'])
                for ln in fig.get('lines', []):
                    self.assertIn(ln['role'], _figure.ROLES)
                for ar in fig.get('areas', []):
                    self.assertIn(ar['role'], _figure.ROLES)
                    self.assertGreaterEqual(len(ar['points']), 3)
                for pnt in fig.get('points', []):
                    # ключевые точки — внутри осей, иначе уедут за рамку
                    self.assertLessEqual(pnt['x'], fig['xmax'])
                    self.assertLessEqual(pnt['y'], fig['ymax'])
                json.dumps(fig)   # чертёж обязан лечь в JSONField

    def test_figure_only_on_the_detailed_question(self):
        """График — к numeric (его смотрят в разборе). В Блице/Пуле карточка
        короткая, чертёж там был бы лишним."""
        rng = random.Random(1)
        arch = ARCHETYPES['monopoly']
        for qtype in ('single', 'boolean'):
            q = gbase.generate_question(arch, rng, qtype)
            self.assertIsNone(q['figure'])

    # величины-количества: их единица обязана прийти из сюжета
    QUANTITY_KEYS = ('q_star', 'q_m', 'q_c', 'q1')

    def test_units_match_the_story(self):
        """Единица количества — из сюжета, а не общая на архетип.

        «Равновесный объём 190 шт.» под рассказом про кофе в зёрнах (его
        меряют в килограммах) — ровно та небрежность, из-за которой задаче
        не место на сайте."""
        from game.generators import (equilibrium, monopoly, ppf_single,
                                      tax_subsidy)
        mods = {'monopoly': monopoly, 'equilibrium': equilibrium,
                'tax_subsidy': tax_subsidy, 'ppf_single': ppf_single}
        for key in ETALON_ARCHETYPES:
            mod = mods[key]
            for _, q in self.each(key):
                if q['params']['_asked'] not in self.QUANTITY_KEYS:
                    continue
                story = mod.STORIES[q['params']['story']]
                self.assertEqual(
                    q['unit'], story.unit_q,
                    u'{}/{}: единица «{}» не из сюжета'.format(
                        key, story.key, q['unit']))
                self.assertIn(story.unit_q, q['solution_text'])
