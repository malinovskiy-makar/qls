# -*- coding: utf-8 -*-
u"""Экономика очков v2 — контрольные числа (фаза 3).

⚠️ ЧИСЛА ЗДЕСЬ — ИЗ ЗАДАНИЯ ВЛАДЕЛЬЦА, а не срисованы с работающего кода.
В этом весь смысл: тест, посчитанный тем же кодом, который проверяет,
зелёный при любой формуле. Каждое число ниже посчитано на бумаге и
сходится с решением о переходе на v2.

Опорные величины Блица для 100-значного текста:
    T_read  = 100 / 20 = 5 с
    T_think = 12 × (0,6 + 0,2·d)
    T_ref   = T_read + T_think
        3★: T_think = 14,4 → T_ref = 19,4
        5★: T_think = 19,2 → T_ref = 24,2
        1★: T_think =  9,6 → T_ref = 14,6
"""
from django.test import SimpleTestCase

from game import config, scoring

TEXT100 = 'ф' * 100          # ровно 100 знаков → T_read = 5 с
TEXT40 = 'ф' * 40            # 40 знаков → T_read = 2 с (пол не задевается)


class ReferenceTimeTests(SimpleTestCase):
    u"""Опорное время: прочитать плюс подумать."""

    def test_read_time(self):
        self.assertAlmostEqual(scoring.read_time(TEXT100), 5.0)
        self.assertAlmostEqual(scoring.read_time(TEXT40), 2.0)

    def test_read_time_has_a_floor(self):
        u"""Без пола короткая данетка давала бы нулевое опорное время и
        максимальный бонус любому, кто просто быстро жмёт."""
        self.assertAlmostEqual(scoring.read_time('Верно?'), 2.0)
        self.assertAlmostEqual(scoring.read_time(''), 2.0)
        self.assertAlmostEqual(scoring.read_time(None), 2.0)

    def test_think_time_scales_with_difficulty(self):
        self.assertAlmostEqual(scoring.think_time('blitz', 3), 14.4)
        self.assertAlmostEqual(scoring.think_time('blitz', 5), 19.2)
        self.assertAlmostEqual(scoring.think_time('blitz', 1), 9.6)
        self.assertAlmostEqual(scoring.think_time('bullet', 2), 6.0)

    def test_reference_time(self):
        self.assertAlmostEqual(scoring.reference_time('blitz', 3, TEXT100), 19.4)
        self.assertAlmostEqual(scoring.reference_time('blitz', 5, TEXT100), 24.2)
        self.assertAlmostEqual(scoring.reference_time('bullet', 2, TEXT40), 8.0)


class QuestionPointsTests(SimpleTestCase):
    u"""Контрольные числа за один верный ответ."""

    def pts(self, **kw):
        base = dict(mode='blitz', difficulty=3, text=TEXT100, elapsed_s=19.4,
                    streak=1, lives_before=3, unfiltered=True)
        base.update(kw)
        return scoring.question_points(
            base['mode'], base['difficulty'], base['text'],
            base['elapsed_s'], base['streak'], base['lives_before'],
            base['unfiltered'])

    def test_3star_at_reference_time(self):
        u"""3★, ровно опорное время, серия 1, три жизни, без фильтров."""
        self.assertEqual(self.pts(), 130)

    def test_3star_instant_answer_hits_the_read_floor(self):
        u"""t = 1 с, но пол по прочтению — 5 с: быстрее не считается."""
        self.assertEqual(self.pts(elapsed_s=1), 178)

    def test_5star_instant(self):
        self.assertEqual(self.pts(difficulty=5, elapsed_s=1), 454)

    def test_5star_instant_with_filters(self):
        u"""Тот же ответ, но игрок подобрал себе пул: ×1,3 не начисляется."""
        self.assertEqual(self.pts(difficulty=5, elapsed_s=1, unfiltered=False),
                         349)

    def test_1star_slow(self):
        self.assertEqual(self.pts(difficulty=1, elapsed_s=100), 26)

    def test_combo_steps(self):
        u"""Серия 3 / 6 / 9 / 12 на опорном времени."""
        self.assertEqual(self.pts(streak=3), 163)
        self.assertEqual(self.pts(streak=6), 195)
        self.assertEqual(self.pts(streak=9), 228)
        self.assertEqual(self.pts(streak=12), 260)

    def test_last_life(self):
        u"""×1,25, а не ×2: двукратный множитель награждал угадывание."""
        self.assertEqual(self.pts(lives_before=1), 163)

    def test_bullet_short_question(self):
        u"""Пуля, 2★, текст 40 знаков (T_ref = 8), ответ за 3 с."""
        self.assertEqual(
            self.pts(mode='bullet', difficulty=2, text=TEXT40, elapsed_s=3),
            85)

    def test_missing_server_time_gives_no_speed_bonus(self):
        u"""Нет метки выдачи — трактуем как «долго», а не как «мгновенно»."""
        self.assertEqual(self.pts(elapsed_s=None), 130)
        self.assertEqual(self.pts(elapsed_s=-5), 130)


class AccuracyTests(SimpleTestCase):
    u"""Точность забега снижает ИТОГ. Пропуски не считаются."""

    def test_accuracy_multiplier_points(self):
        for correct, wrong, want in [(9, 1, 1.0), (8, 2, 0.9), (7, 3, 0.7),
                                     (6, 4, 0.5), (3, 3, 0.3), (5, 0, 1.0)]:
            self.assertAlmostEqual(
                scoring.accuracy_multiplier(correct, wrong), want, places=6,
                msg='%d/%d' % (correct, wrong))

    def test_below_the_floor_stays_at_the_floor(self):
        self.assertAlmostEqual(scoring.accuracy_multiplier(1, 9), 0.3)
        self.assertAlmostEqual(scoring.accuracy_multiplier(0, 5), 0.3)

    def test_empty_run_is_not_punished(self):
        u"""Забег без единого ответа: делить не на что, множитель 1."""
        self.assertAlmostEqual(scoring.accuracy_multiplier(0, 0), 1.0)

    def test_final_score(self):
        self.assertEqual(scoring.final_score(1000, 6, 4), 500)
        self.assertEqual(scoring.final_score(1000, 9, 1), 1000)
        self.assertEqual(scoring.final_score(0, 0, 0), 0)


class TimeBonusTests(SimpleTestCase):
    u"""Прибавка времени: со скидкой за лёгкость и с потолком на забег."""

    def test_classic_scale_by_difficulty(self):
        self.assertEqual(scoring.time_bonus('classic', 1, 0), 6)
        self.assertEqual(scoring.time_bonus('classic', 2, 0), 15)
        self.assertEqual(scoring.time_bonus('classic', 3, 0), 30)
        self.assertEqual(scoring.time_bonus('classic', 5, 0), 30)

    def test_cap_stops_the_endless_run(self):
        u"""В Классике запас 600 с; после 600 с прибавки верный даёт +0.
        Без потолка хороший игрок набирал время быстрее, чем тратил."""
        cap = int(config.MODES['classic']['duration']
                  * config.TIME_BONUS_CAP_FACTOR)
        self.assertEqual(cap, 600)
        self.assertEqual(scoring.time_bonus('classic', 3, 600), 0)
        self.assertEqual(scoring.time_bonus('classic', 3, 599), 1)
        self.assertEqual(scoring.time_bonus('classic', 3, 580), 20)


class EconomyShapeTests(SimpleTestCase):
    u"""Свойства экономики, которые обязаны держаться, а не числа."""

    def test_harder_questions_are_worth_more(self):
        vals = [scoring.question_points('blitz', d, TEXT100, 19.4, 1, 3, True)
                for d in (1, 2, 3, 4, 5)]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual(len(set(vals)), 5)

    def test_unfiltered_always_beats_filtered_all_else_equal(self):
        for d in (1, 2, 3, 4, 5):
            a = scoring.question_points('blitz', d, TEXT100, 10, 4, 3, True)
            b = scoring.question_points('blitz', d, TEXT100, 10, 4, 3, False)
            self.assertGreater(a, b, 'сложность %d' % d)

    def test_rounding_is_half_up_not_bankers(self):
        u"""У банковского округления 162,5 → 162, и контрольные числа
        переставали бы сходиться."""
        self.assertEqual(scoring.question_points(
            'blitz', 3, TEXT100, 19.4, 3, 3, True), 163)     # ровно 162,5

    def test_difficulty_outside_the_range_does_not_crash(self):
        u"""Порча данных — не повод ронять забег игроку."""
        for bad in (0, 9, None, 'три'):
            self.assertGreater(
                scoring.question_points('blitz', bad, TEXT100, 19.4, 1, 3, True),
                0)

    def test_economy_version_is_two(self):
        self.assertEqual(config.ECONOMY_VERSION, 2)
        self.assertEqual(scoring.ECONOMY_VERSION, 2)


class SimulationWiringTests(SimpleTestCase):
    u"""Симуляция обязана считать ТЕМИ ЖЕ формулами, что и игра.

    ⚠️ Смысл проверки. Симуляцией решают, не выгодно ли играть нечестно.
    Заведись у неё своя копия формул — она начала бы одобрять экономику,
    которой в игре нет, и перекос жил бы незамеченным. Сам прогон здесь не
    запускается (он долгий); проверяется, что копии нет.
    """

    def test_simulation_imports_the_production_formulas(self):
        import io
        src = io.open('scripts/game_economy_sim.py', encoding='utf-8').read()
        self.assertIn('from game import config, scoring', src)
        for call in ('scoring.question_points(', 'scoring.time_bonus(',
                     'scoring.final_score(', 'scoring.reference_time('):
            self.assertIn(call, src, call)

    def test_simulation_has_no_copy_of_the_numbers(self):
        import io
        src = io.open('scripts/game_economy_sim.py', encoding='utf-8').read()
        # Ни одной константы экономики своими значениями.
        for forbidden in ('BASE_BY_DIFFICULTY =', 'COMBO_STEPS =',
                          'SCOPE_MULTIPLIER =', 'SPEED_BONUS_MAX =',
                          'ACCURACY_FULL_AT ='):
            self.assertNotIn(forbidden, src, forbidden)

    def test_simulation_knows_which_runs_reach_the_board(self):
        u"""Фильтр по сложности делает забег тренировочным. Не знай об этом
        симуляция — она объявляла бы перекосом то, что на доску не идёт."""
        import io
        src = io.open('scripts/game_economy_sim.py', encoding='utf-8').read()
        self.assertIn('ЗАЧЁТНОСТЬ', src)
        self.assertIn('тренировочный', src)
