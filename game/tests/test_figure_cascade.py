u"""ШЛЮЗ КАСКАДА — самый ценный тест режима «График».

Каждый сюжет × каждый его инжектор × 200 сэмплов. Проверяется ровно то, без
чего вопрос теряет смысл:

1. испорчен ровно ОДИН шаг, а нижние ПЕРЕСЧИТАНЫ от него;
2. верхние шаги совпадают с эталоном байт в байт;
3. верный ответ определяется однозначно;
4. картинка ОТЛИЧАЕТСЯ от эталонной (инжектор, не меняющий чертёж, —
   это невидимая ошибка, то есть вопрос без решения);
5. «ошибки нет» совпадает с эталоном полностью.

Плюс инвариант рамки: у эталона и у испорченного решения ОДНИ И ТЕ ЖЕ оси.
Прошлая сессия наступила ровно на это: архетип строил рамку от решения, и
на испорченном варианте оси разъезжались — вариант отличался поломанным
рисунком, а не экономикой.

Зубастость шлюза проверяется отдельным классом: каскад ломают нарочно
(инжектор лезет в `params`, то есть в общий вход всех трёх шагов) и
убеждаются, что тест краснеет.
"""
import copy
import json
import random

from django.test import SimpleTestCase

from game import config
from game.figures import base as fbase
from game.figures.registry import SCENARIOS
from game.figures.scenarios.consumer_surplus import ConsumerSurplus
from game.figures.scenarios.tax_burden import TaxBurden

SAMPLES = 200


def fig_key(fig):
    return json.dumps(fig, sort_keys=True, ensure_ascii=False)


def assert_cascade(test, sc, inj, clean_params, ref, got, where=''):
    u"""Проверка каскада на ОДНОМ экземпляре.

    ⚠️ `clean_params` — снимок параметров, снятый ДО инъекции. Пересчитывать
    нижние шаги теми же параметрами, которые инжектор мог подменить, нельзя:
    подмена «сошлась бы сама с собой», и шлюз пропустил бы ровно ту диверсию,
    ради которой он написан. На этом он один раз и попался — теперь снимок.
    """
    if inj.step == fbase.STEP_POINTS:
        test.assertNotEqual(ref.step_key('points'), got.step_key('points'),
                            u'%s: точки не изменились' % where)
        test.assertEqual(
            got.region, sc.region(clean_params, got.points),
            u'%s: область не пересчитана от испорченных точек' % where)
        test.assertEqual(
            got.value, sc.value(clean_params, got.points, got.region),
            u'%s: число не пересчитано от испорченной области' % where)
    elif inj.step == fbase.STEP_REGION:
        test.assertEqual(ref.step_key('points'), got.step_key('points'),
                         u'%s: точки тронуты, а не должны' % where)
        test.assertNotEqual(ref.step_key('region'), got.step_key('region'),
                            u'%s: область не изменилась' % where)
        test.assertEqual(
            got.value, sc.value(clean_params, got.points, got.region),
            u'%s: число не пересчитано от испорченной области' % where)
    else:
        test.assertEqual(ref.step_key('points'), got.step_key('points'),
                         u'%s: точки тронуты, а не должны' % where)
        test.assertEqual(ref.step_key('region'), got.step_key('region'),
                         u'%s: область тронута, а не должна' % where)
        test.assertNotEqual(ref.value, got.value,
                            u'%s: число не изменилось' % where)


class CascadeGateTests(SimpleTestCase):
    u"""★ Каскад: один испорченный шаг, нижние — от него, верхние — эталон."""

    def _walk(self, check):
        for key in sorted(SCENARIOS):
            sc = SCENARIOS[key]
            for inj in sc.injectors():
                rng = random.Random('%s:%s' % (key, inj.key))
                for i in range(SAMPLES):
                    params = sc.sample(rng)
                    snapshot = copy.deepcopy(params)
                    ref = sc.solve(params)
                    got = sc.inject(params, inj, rng)
                    check(sc, inj, snapshot, ref, got, i)

    def test_upper_steps_are_identical_and_lower_are_recomputed(self):
        def check(sc, inj, params, ref, got, i):
            assert_cascade(self, sc, inj, params, ref, got,
                           u'%s/%s #%d' % (sc.key, inj.key, i))
        self._walk(check)

    def test_the_picture_always_differs_from_the_reference(self):
        u"""Невидимая ошибка = вопрос без решения. Такой инжектор обязан краснеть."""
        def check(sc, inj, params, ref, got, i):
            self.assertNotEqual(
                fig_key(sc.draw(params, ref)), fig_key(sc.draw(params, got)),
                u'%s/%s #%d: чертёж не отличается от эталонного'
                % (sc.key, inj.key, i))
        self._walk(check)

    def test_axes_never_move_between_reference_and_spoiled(self):
        u"""★ Рамка считается ТОЛЬКО из params — иначе оси поедут."""
        def check(sc, inj, params, ref, got, i):
            a, b = sc.draw(params, ref), sc.draw(params, got)
            self.assertEqual((a['xmax'], a['ymax']), (b['xmax'], b['ymax']),
                             u'%s/%s #%d: рамка чертежа поехала'
                             % (sc.key, inj.key, i))
        self._walk(check)

    def test_clean_solution_equals_the_reference_completely(self):
        for key in sorted(SCENARIOS):
            sc = SCENARIOS[key]
            rng = random.Random('clean:' + key)
            for i in range(SAMPLES):
                params = sc.sample(rng)
                ref = sc.solve(params)
                clean = sc.inject(params, None, rng)
                self.assertEqual(ref.snapshot(), clean.snapshot(),
                                 u'%s #%d: «ошибки нет» разошлось с эталоном'
                                 % (key, i))
                self.assertEqual(fig_key(sc.draw(params, ref)),
                                 fig_key(sc.draw(params, clean)))

    def test_correct_answer_is_unambiguous(self):
        u"""Верный ответ = номер испорченного шага, и он ровно один."""
        for key in sorted(SCENARIOS):
            sc = SCENARIOS[key]
            rng = random.Random('answer:' + key)
            for _ in range(SAMPLES):
                q = fbase.build_question(sc, rng, config.FIGURE_CLEAN_SHARE)
                self.assertIn(q['correct_index'], (0, 1, 2, 3))
                self.assertEqual(
                    q['correct_index'],
                    fbase.ANSWER_INDEX[q['params']['_step']])
                self.assertEqual(q['options'], fbase.ANSWER_OPTIONS)


class ScenarioContractTests(SimpleTestCase):
    def test_every_scenario_has_all_three_kinds_of_error(self):
        u"""Иначе обещанное распределение 28/28/29/15 — неправда."""
        for key, sc in sorted(SCENARIOS.items()):
            by_step = sc.injectors_by_step()
            for step in fbase.STEPS:
                self.assertTrue(by_step[step],
                                u'%s: нет ошибок вида «%s»' % (key, step))

    def test_answer_options_order_is_fixed(self):
        u"""Порядок вариантов и есть правильный порядок проверки решения."""
        self.assertEqual(fbase.ANSWER_OPTIONS[0], u'Координаты точек')
        self.assertEqual(fbase.ANSWER_OPTIONS[1], u'Заштрихованная область')
        self.assertEqual(fbase.ANSWER_OPTIONS[2], u'Вычисление')
        self.assertEqual(fbase.ANSWER_OPTIONS[3], u'Ошибки нет')

    def test_difficulty_is_explicit_and_in_range(self):
        for key, sc in sorted(SCENARIOS.items()):
            self.assertIn(sc.difficulty, (1, 2, 3, 4, 5), key)
            self.assertTrue(sc.topics, u'%s: сюжет без тем' % key)

    def test_scenario_keys_are_unique_and_stable(self):
        keys = [sc.key for sc in SCENARIOS.values()]
        self.assertEqual(len(keys), len(set(keys)))
        for k in keys:
            self.assertTrue(k and k.replace('_', '').isalnum(), k)


class NiceNumbersTests(SimpleTestCase):
    u"""Не меньше 90 % сэмплов — целые числа и целые координаты. На четырёх сидах."""

    def test_integers_on_four_seeds(self):
        for key in sorted(SCENARIOS):
            sc = SCENARIOS[key]
            for seed in (1, 2, 3, 4):
                rng = random.Random('%s:%d' % (key, seed))
                nice = 0
                for _ in range(SAMPLES):
                    params = sc.sample(rng)
                    sol = sc.solve(params)
                    ok = sol.value.denominator == 1
                    for _n, (x, y) in sol.points.items():
                        ok = ok and x.denominator == 1 and y.denominator == 1
                    nice += 1 if ok else 0
                share = nice / float(SAMPLES)
                self.assertGreaterEqual(
                    share, 0.90,
                    u'%s (сид %d): целых только %.0f %%'
                    % (key, seed, 100 * share))


class DistributionTests(SimpleTestCase):
    u"""Распределение верных ответов: 28,3 / 28,3 / 28,3 / 15 (±4 п.п.)."""

    def test_two_thousand_samples(self):
        rng = random.Random('distribution')
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        total = 2000
        keys = sorted(SCENARIOS)
        for i in range(total):
            sc = SCENARIOS[keys[i % len(keys)]]
            q = fbase.build_question(sc, rng, config.FIGURE_CLEAN_SHARE)
            counts[q['correct_index']] += 1
        share = {k: 100.0 * v / total for k, v in counts.items()}
        want_err = 100.0 * (1 - config.FIGURE_CLEAN_SHARE) / 3
        want_clean = 100.0 * config.FIGURE_CLEAN_SHARE
        for idx in (0, 1, 2):
            self.assertAlmostEqual(
                share[idx], want_err, delta=4.0,
                msg=u'вариант %d: %.1f %% вместо %.1f %%'
                    % (idx, share[idx], want_err))
        self.assertAlmostEqual(
            share[3], want_clean, delta=4.0,
            msg=u'«ошибки нет»: %.1f %% вместо %.1f %%' % (share[3], want_clean))


class ControlNumbersTests(SimpleTestCase):
    u"""Контрольные примеры из ТЗ — прямой подачей параметров в шаги."""

    def test_consumer_surplus_control(self):
        # спрос P = 100 − Q, предложение P = 40 + 2Q
        sc = ConsumerSurplus()
        params = {'story': 'coffee', 'q': 20, 'p': 80, 'a': 100, 'b': 1,
                  'c': 40, 'd': 2, 'q_axis': 100}
        sol = sc.solve(params)
        self.assertEqual(sol.points['E'], (20, 80))
        self.assertEqual(sol.value, 200)                      # CS
        by_key = {i.key: i for i in sc.injectors()}
        rng = random.Random(0)
        # излишек продавца вместо покупателя → 400
        self.assertEqual(sc.inject(params, by_key['producer_side'], rng).value,
                         400)
        # готовность платить (трапеция под спросом) → ½·(100+80)·20 = 1800
        self.assertEqual(sc.inject(params, by_key['willingness'], rng).value,
                         1800)
        # высота от нуля → ½·100·20 = 1000
        self.assertEqual(sc.inject(params, by_key['height_from_zero'],
                                   rng).value, 1000)
        # забыта половина → 400 при верной области
        spoiled = sc.inject(params, by_key['no_half'], rng)
        self.assertEqual(spoiled.value, 400)
        self.assertEqual(spoiled.region, sol.region)
        # равновесие снято на оси Q
        coord = sc.inject(params, by_key['demand_axis'], rng)
        self.assertEqual(coord.points['E'], (100, 0))

    def test_tax_control(self):
        # спрос P = 120 − 2Q, предложение P = 30 + Q, налог 30
        sc = TaxBurden()
        params = {'story': 'soda', 'b': 2, 'd': 1, 'dq': 10, 'q0': 30,
                  'p0': 60, 'a': 120, 'c': 30, 't': 30, 'q1': 20,
                  'pb': 80, 'ps': 50}
        sol = sc.solve(params)
        self.assertEqual(sol.points['E_0'], (30, 60))
        self.assertEqual(sol.points['B'], (20, 80))    # цена покупателя
        self.assertEqual(sol.points['C'], (20, 50))    # цена продавца
        self.assertEqual(params['pb'] - params['ps'], params['t'])
        self.assertEqual(params['pb'] - params['p0'], 20)   # бремя покупателя
        self.assertEqual(params['p0'] - params['ps'], 10)   # бремя продавца
        self.assertEqual(sol.value, 150)                    # потери общества
        by_key = {i.key: i for i in sc.injectors()}
        rng = random.Random(0)
        # бремя наоборот: покупатель 50, продавец 80
        swapped = sc.inject(params, by_key['burden_swapped'], rng)
        self.assertEqual(swapped.points['B'], (20, 50))
        self.assertEqual(swapped.points['C'], (20, 80))
        # прямоугольник сбора вместо треугольника → 30 · 20 = 600
        self.assertEqual(sc.inject(params, by_key['revenue_rect'], rng).value,
                         600)
        # забыта половина → 300
        self.assertEqual(sc.inject(params, by_key['no_half'], rng).value, 300)

    def test_slopes_always_differ(self):
        u"""★ Равные наклоны сделали бы ошибку численно неотличимой."""
        for key in ('cs_triangle', 'tax_dwl'):
            sc = SCENARIOS[key]
            rng = random.Random('slopes:' + key)
            for _ in range(SAMPLES * 2):
                params = sc.sample(rng)
                self.assertNotEqual(params['b'], params['d'],
                                    u'%s: наклоны совпали' % key)

    def test_consumer_surplus_never_equals_producer_surplus(self):
        sc = SCENARIOS['cs_triangle']
        by_key = {i.key: i for i in sc.injectors()}
        rng = random.Random('cs-vs-ps')
        for _ in range(SAMPLES):
            params = sc.sample(rng)
            cs = sc.solve(params).value
            ps = sc.inject(params, by_key['producer_side'], rng).value
            self.assertNotEqual(cs, ps,
                                u'CS = PS: ошибка «зеркальный излишек» '
                                u'неотличима от верного ответа')

    def test_tax_burden_never_splits_evenly(self):
        sc = SCENARIOS['tax_dwl']
        rng = random.Random('burden')
        for _ in range(SAMPLES):
            params = sc.sample(rng)
            self.assertNotEqual(params['pb'] - params['p0'],
                                params['p0'] - params['ps'],
                                u'бремя разделилось поровну: ошибка «наоборот» '
                                u'неотличима от верного ответа')


class GateHasTeethTests(SimpleTestCase):
    u"""Проверка шлюза на зубастость: ломаем каскад нарочно.

    Единственный способ сломать каскад в этом движке — залезть из инжектора
    в `params`, то есть в общий вход всех трёх шагов. Тогда «испорченными»
    окажутся сразу два независимых шага, и шлюз обязан покраснеть. Если он
    этого не увидит — он ничего не стережёт.
    """

    def _run_gate(self, sc, inj):
        u"""Ровно та проверка, что стоит в шлюзе, на одном экземпляре."""
        rng = random.Random(7)
        params = sc.sample(rng)
        snapshot = copy.deepcopy(params)
        ref = sc.solve(params)
        got = sc.inject(params, inj, rng)
        assert_cascade(self, sc, inj, snapshot, ref, got, u'диверсия')

    def test_a_saboteur_injector_is_caught(self):
        sc = ConsumerSurplus()

        def saboteur(params, points, rng):
            # портим точку И подменяем параметр, от которого зависят нижние
            # шаги: тогда независимо сломаны сразу два шага, и «первый
            # неверный» перестаёт быть определённым
            params['a'] = params['a'] + 10
            return {'E': (points['E'][0] + 2, points['E'][1])}

        bad = fbase.Injector('points', 'saboteur', u'диверсант', saboteur)
        with self.assertRaises(AssertionError):
            self._run_gate(sc, bad)

    def test_an_injector_that_touches_a_neighbouring_step_is_caught(self):
        u"""Инжектор области, попутно сдвинувший точку, тоже обязан краснеть."""
        sc = ConsumerSurplus()

        def sneaky(params, points, region, rng):
            points['E'] = (points['E'][0] + 1, points['E'][1])
            return list(region)[::-1] + [(0, 0)]

        bad = fbase.Injector('region', 'sneaky', u'тихушник', sneaky)
        with self.assertRaises(AssertionError):
            self._run_gate(sc, bad)

    def test_an_invisible_injector_is_caught(self):
        u"""Инжектор, ничего не меняющий, — это вопрос без решения."""
        sc = ConsumerSurplus()
        bad = fbase.Injector('value', 'nothing', u'ничего не меняет',
                             lambda params, pts, reg, val, rng: val)
        with self.assertRaises(AssertionError):
            self._run_gate(sc, bad)

    def test_the_gate_passes_a_correct_injector(self):
        u"""И наоборот: настоящий инжектор шлюз пропускает (иначе он просто
        красит всё подряд и ничего не доказывает)."""
        sc = ConsumerSurplus()
        good = {i.key: i for i in sc.injectors()}['producer_side']
        self._run_gate(sc, good)   # не должно бросить
