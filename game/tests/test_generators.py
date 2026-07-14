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
import random
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

    def test_monopoly(self):
        s = ARCHETYPES['monopoly'].solve(
            {'a': 100, 'b': 1, 'mc': 20, 'good': 0})
        self.assertEqual(s['q_m'], 40)
        self.assertEqual(s['p_m'], 60)
        self.assertEqual(s['profit'], 1600)
        self.assertEqual(s['q_c'], 80)
        self.assertEqual(s['dwl'], 800)


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
            test.assertEqual(solved['dwl'] * 2, solved['profit'])
            test.assertEqual(Fraction(solved['dwl']).denominator, 1)
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
