# -*- coding: utf-8 -*-
u"""Экономика очков Wecon Rush, версия 2 — ЧИСТЫЕ ФУНКЦИИ.

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Очки считает только сервер, но считает он их в
двух местах: в живом забеге (`views.api_answer`) и в симуляции
(`scripts/game_economy_sim.py`), которой проверяют, не выгодно ли играть
нечестно. Разъедься эти два расчёта — симуляция начала бы одобрять то, чего
в игре нет. Поэтому формулы живут здесь, а оба места их импортируют.

Здесь НЕТ Django: ни моделей, ни запросов, ни времени. На вход приходят
числа, на выходе числа. Это и делает экономику проверяемой арифметикой.

⚠️ ЧТО ЛЕЧИТ ВЕРСИЯ 2. В версии 1 очки были «100 × комбо» — сложность
вопроса не влияла ни на что. Симуляция показала два перекоса:
  • стратегия «только 1★» давала в 2–4 раза больше честного забега:
    лёгкие вопросы отвечаются быстрее, серия рвётся реже, а очки те же;
  • в Классике +30 с за верный ответ делали забег бесконечным.
Версия 2 привязывает очки к сложности, к скорости относительно ЧЕСТНОГО
времени на прочтение и размышление, и снижает итог за низкую точность.

Округление везде «половина вверх» (`int(x + 0.5)`), а не банковское:
у банковского 162,5 → 162, и контрольные числа переставали бы сходиться.
"""
from . import config

# Версия экономики. Пишется в GameResult: забеги разных версий нельзя
# складывать в один рекорд — они на разных шкалах.
ECONOMY_VERSION = config.ECONOMY_VERSION


def read_time(text):
    u"""Сколько честно читать условие, секунды.

    Пол в 2 секунды нужен коротким данеткам: без него «Верно?» из пяти
    букв давал бы нулевое опорное время и максимальный бонус за скорость
    любому, кто просто быстро жмёт.
    """
    n = len(text or '')
    return max(config.READ_MIN_S, n / config.READ_CHARS_PER_SEC)


def think_time(mode, difficulty):
    u"""Сколько честно думать над вопросом этой сложности, секунды.

    Базу даёт режим (в Пуле думают 6 с, в Классике 60), множитель —
    сложность: 1★ → 0,8 базы, 5★ → 1,6.
    """
    d = _clamp_difficulty(difficulty)
    return config.THINK_S[mode] * (0.6 + 0.2 * d)


def reference_time(mode, difficulty, text):
    u"""Опорное время ответа: прочитать плюс подумать."""
    return read_time(text) + think_time(mode, difficulty)


def speed_bonus(mode, difficulty, text, elapsed_s):
    u"""Множитель за скорость: 1,0 (не быстрее опорного) … 1,5 (мгновенно).

    ⚠️ ПОЛ ПО ВРЕМЕНИ ПРОЧТЕНИЯ. Ответ быстрее, чем текст физически можно
    прочитать, не считается более быстрым: иначе максимум бонуса получал бы
    угадывающий, который вообще не читает. Отрицательное или отсутствующее
    время — это сбой измерения, и трактуется как «долго», без бонуса.
    """
    if elapsed_s is None or elapsed_s < 0:
        return 1.0
    t_ref = reference_time(mode, difficulty, text)
    if t_ref <= 0:
        return 1.0
    t_eff = max(elapsed_s, read_time(text))
    return 1.0 + config.SPEED_BONUS_MAX * max(0.0, 1.0 - t_eff / t_ref)


def combo_multiplier(streak):
    u"""Множитель за серию верных подряд.

    Ступени в версии 2 положе (×1,25 … ×2 вместо ×2 … ×4): при ×4 одна
    удачная серия перевешивала весь остальной забег, и выгоднее было
    набирать её на лёгких вопросах, чем честно играть.
    """
    for threshold, mult in config.COMBO_STEPS:
        if streak >= threshold:
            return float(mult)
    return 1.0


def question_points(mode, difficulty, text, elapsed_s, streak,
                    lives_before, unfiltered):
    u"""Очки за ОДИН верный ответ.

    difficulty — ЭФФЕКТИВНАЯ сложность (измеренная, если попыток набралось,
    иначе хранимая): см. `game/stats.py::effective_difficulty`.
    elapsed_s — СЕРВЕРНОЕ время ответа. Клиентское в очки не входит.
    """
    d = _clamp_difficulty(difficulty)
    pts = config.BASE_BY_DIFFICULTY[d]
    pts *= speed_bonus(mode, d, text, elapsed_s)
    pts *= combo_multiplier(streak)
    if unfiltered:
        pts *= config.SCOPE_MULTIPLIER
    if lives_before == 1:
        pts *= config.LAST_LIFE_MULTIPLIER
    return int(pts + 0.5)


def accuracy_multiplier(correct, wrong):
    u"""Множитель итога за точность забега.

    ⚠️ ПРОПУСКИ НЕ СЧИТАЮТСЯ. Пропуск — честное «не знаю», и наказывать за
    него нечем: он и так не приносит очков. Считается доля верных среди
    ОТВЕЧЕННЫХ.

    Точность ≥ 85 % → ×1; ≤ 50 % → ×0,3; между ними линейно. Это и есть
    главный тормоз угадывания: угадывающий набирает очки, но теряет их на
    итоге.
    """
    answered = correct + wrong
    if answered <= 0:
        return 1.0
    acc = correct / answered
    if acc >= config.ACCURACY_FULL_AT:
        return 1.0
    if acc <= config.ACCURACY_FLOOR_AT:
        return config.ACCURACY_MIN_MULT
    span = config.ACCURACY_FULL_AT - config.ACCURACY_FLOOR_AT
    k = (acc - config.ACCURACY_FLOOR_AT) / span
    return config.ACCURACY_MIN_MULT + (1.0 - config.ACCURACY_MIN_MULT) * k


def time_bonus(mode, difficulty, bonus_already):
    u"""Сколько секунд добавить за верный ответ, с учётом потолка забега.

    ⚠️ ПОТОЛОК ОБЯЗАТЕЛЕН. В Классике +30 с за верный ответ при запасе
    600 с делали забег бесконечным: хороший игрок набирал время быстрее,
    чем тратил. Суммарная прибавка за забег ограничена запасом режима.

    Лёгкие вопросы дают меньше: 1★ — пятую часть прибавки, 2★ — половину.
    Иначе выгодно было бы фильтровать пул до одних лёгких.
    """
    d = _clamp_difficulty(difficulty)
    cfg = config.MODES[mode]
    step = int(cfg['time_correct']
               * config.TIME_BONUS_SCALE_BY_DIFFICULTY[d] + 0.5)
    cap = int(cfg['duration'] * config.TIME_BONUS_CAP_FACTOR)
    room = max(0, cap - int(bonus_already or 0))
    return max(0, min(step, room))


def final_score(raw, correct, wrong):
    u"""Итог забега: сырые очки, помноженные на точность."""
    return int(max(0, raw) * accuracy_multiplier(correct, wrong) + 0.5)


def _clamp_difficulty(d):
    u"""Сложность вне 1–5 — это порча данных, а не повод падать."""
    try:
        d = int(d)
    except (TypeError, ValueError):
        return 3
    return max(config.DIFFICULTY_MIN, min(config.DIFFICULTY_MAX, d))
