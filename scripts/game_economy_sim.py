# -*- coding: utf-8 -*-
u"""Симуляция экономики Wecon Rush: выгодно ли играть нечестно.

⚠️ ЗАЧЕМ ЭТО ВООБЩЕ. Экономика игры — это набор чисел, и «на глаз» в ней
не видно главного: не выгоднее ли отфильтровать пул до одних лёгких
вопросов, чем честно играть. У версии 1 это было именно так — «только 1★»
давало в 2–4 раза больше честного забега. Здесь такие перекосы ищутся
перебором, а не рассуждением.

⚠️ ФОРМУЛЫ ИМПОРТИРУЮТСЯ ИЗ game/scoring.py, а не переписаны здесь. Копия
разъехалась бы с боевым расчётом при первой же правке, и симуляция начала
бы одобрять то, чего в игре нет.

Что перебирается:
  четыре типа игроков × четыре стратегии фильтра × четыре режима,
  по умолчанию 1 500 забегов на ячейку.

Что смотрим: среднее и «лучший из 20» (по нему живёт лидерборд — туда
попадает не средний забег, а удачный).

Запуск:
    venv313/Scripts/python.exe scripts/game_economy_sim.py
    venv313/Scripts/python.exe scripts/game_economy_sim.py --runs 300 --seed 7
"""
import argparse
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import config, scoring          # noqa: E402  (после sys.path)

# ── Игроки. `acc` — вероятность верного ответа на вопрос 3★; на других
#    сложностях она сдвигается (см. `answer_prob`). `speed` — доля опорного
#    времени, за которую игрок отвечает.
PLAYERS = [
    ('угадывающий',   {'acc': 0.30, 'speed': 0.15}),
    ('неаккуратный',  {'acc': 0.75, 'speed': 0.55}),
    ('внимательный',  {'acc': 0.90, 'speed': 0.80}),
    ('эксперт',       {'acc': 0.95, 'speed': 0.55}),
]

# ── Стратегии игрока: что он пускает в свой пул и попадает ли такой забег
#    в таблицу. Третье поле — ЗАЧЁТНОСТЬ (см. фазу 5): фильтр ПО СЛОЖНОСТИ
#    делает забег тренировочным, фильтр по темам и источникам — нет.
#    Это и есть главный предохранитель: подобрать себе сложность можно,
#    но такой забег на доску не поедет.
STRATEGIES = [
    # имя,            какие сложности, ×1,3 за отсутствие фильтров, зачётный
    ('без фильтров',  None,   True,  True),
    ('фильтр темы',   None,   False, True),
    ('только 1★',     [1],    False, False),
    ('2–3★',          [2, 3], False, False),
    ('только 5★',     [5],    False, False),
]

MODES = ['bullet', 'blitz', 'rapid', 'classic']

# Распределение сложностей в пуле. Снято грубо: середина тяжелее краёв.
POOL_MIX = {1: 0.12, 2: 0.24, 3: 0.34, 4: 0.20, 5: 0.10}

# Длина текста вопроса, знаков. Влияет на опорное время через T_read.
TEXT_LEN = 110


def answer_prob(base_acc, difficulty):
    u"""Вероятность верного ответа: сложнее вопрос — ниже шанс.

    3★ — «своя» сложность игрока. Каждая ступень вверх отнимает 8 пунктов,
    вниз — добавляет. Числа грубые: важна не их точность, а то, что
    зависимость есть, — без неё «только 5★» выглядело бы бесплатно.
    """
    p = base_acc - 0.08 * (difficulty - 3)
    return max(0.05, min(0.99, p))


def pick_difficulty(rng, allowed):
    u"""Сложность очередного вопроса под фильтром игрока."""
    pool = {d: w for d, w in POOL_MIX.items()
            if allowed is None or d in allowed}
    if not pool:
        return 3
    return rng.choices(list(pool), weights=list(pool.values()))[0]


def simulate_run(rng, mode, player, allowed, unfiltered):
    u"""Один забег. Возвращает итоговый счёт.

    Забег кончается по жизням или по времени. Время идёт по опорному
    (сколько игрок реально сидит над вопросом) и пополняется прибавкой за
    верные ответы — с потолком, как в игре.
    """
    cfg = config.MODES[mode]
    time_left = float(cfg['duration'])
    lives = cfg['lives']
    streak = 0
    raw = 0
    correct = wrong = 0
    bonus_total = 0
    text = 'ф' * TEXT_LEN
    # Предохранитель от бесконечного цикла, если потолок вдруг снимут.
    for _ in range(2000):
        if lives <= 0 or time_left <= 0:
            break
        d = pick_difficulty(rng, allowed)
        t_ref = scoring.reference_time(mode, d, text)
        spent = max(0.3, t_ref * player['speed'] * rng.uniform(0.75, 1.25))
        time_left -= spent
        if time_left <= 0:
            break
        if rng.random() < answer_prob(player['acc'], d):
            streak += 1
            correct += 1
            lives_before = lives
            raw += scoring.question_points(mode, d, text, spent, streak,
                                           lives_before, unfiltered)
            gain = scoring.time_bonus(mode, d, bonus_total)
            bonus_total += gain
            time_left += gain
        else:
            streak = 0
            wrong += 1
            lives -= 1
    return scoring.final_score(raw, correct, wrong)


def best_of(values, k):
    u"""«Лучший из k»: чего игрок добьётся, если попробует k раз."""
    if len(values) < k:
        return max(values) if values else 0
    out = []
    for i in range(0, len(values) - k + 1, k):
        out.append(max(values[i:i + k]))
    return statistics.mean(out) if out else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=1500,
                    help='забегов на ячейку (по умолчанию 1500)')
    ap.add_argument('--seed', type=int, default=20260902)
    ap.add_argument('--best-of', type=int, default=20)
    args = ap.parse_args()

    print(f'Экономика версии {config.ECONOMY_VERSION}. '
          f'Забегов на ячейку: {args.runs}. Зерно: {args.seed}.')
    print()

    problems = []
    notes = []
    for mode in MODES:
        print(f'══ Режим «{config.MODES[mode]["title"]}» '
              f'({config.MODES[mode]["duration"]} с, '
              f'{config.MODES[mode]["lives"]} жизни) ══')
        head = f'{"игрок":<16}' + ''.join(
            f'{name + ("" if ranked else " ✗"):>17}'
            for name, _a, _u, ranked in STRATEGIES)
        print(head)
        for pname, player in PLAYERS:
            rng = random.Random(f'{args.seed}|{mode}|{pname}')
            means, bests = [], []
            for _sname, allowed, unf, _rk in STRATEGIES:
                runs = [simulate_run(rng, mode, player, allowed, unf)
                        for _ in range(args.runs)]
                means.append(statistics.mean(runs))
                bests.append(best_of(runs, args.best_of))
            row = f'{pname:<16}' + ''.join(
                f'{m:>9.0f}/{b:<7.0f}' for m, b in zip(means, bests))
            print(row)
            # Угадывающего не проверяем: ему выгодно всё лёгкое по
            # устройству, и лечится это точностью, а не охватом.
            if pname == 'угадывающий':
                continue
            for (sname, _a, _u, ranked), m, b in zip(
                    STRATEGIES[1:], means[1:], bests[1:]):
                # ⚠️ ГЛАВНАЯ ПРОВЕРКА — ПО ЗАЧЁТНЫМ СТРАТЕГИЯМ. В таблицу
                # попадает не средний забег, а удачный, поэтому смотрим и
                # среднее, и «лучший из N». Забег с фильтром ПО СЛОЖНОСТИ
                # на доску не поедет вовсе, и обгонять там нечего.
                if ranked and (m > means[0] or b > bests[0]):
                    problems.append(
                        f'{mode}/{pname}: ЗАЧЁТНАЯ «{sname}» выгоднее «без '
                        f'фильтров» (среднее {m:.0f} против {means[0]:.0f}, '
                        f'лучший из {args.best_of} {b:.0f} против {bests[0]:.0f})')
                # У незачётных следим за СРЕДНИМ: если подбор сложности
                # окупается и в обычной игре, люди будут играть так всегда,
                # даже без таблицы.
                if not ranked and m > means[0]:
                    problems.append(
                        f'{mode}/{pname}: тренировочная «{sname}» выгоднее в '
                        f'среднем ({m:.0f} против {means[0]:.0f})')
                if not ranked and b > bests[0]:
                    notes.append(
                        f'{mode}/{pname}: «{sname}» даёт более высокий удачный '
                        f'забег ({b:.0f} против {bests[0]:.0f}), но такой забег '
                        f'ТРЕНИРОВОЧНЫЙ и в таблицу не идёт')
        print('  (в клетке: среднее / лучший из %d; ✗ — забег '
              'тренировочный, в таблицу не идёт)' % args.best_of)
        print()

    if notes:
        print('Замечено (не перекос, но знать надо):')
        for n in notes:
            print('   ' + n)
        print()
    if problems:
        print('⚠️ ПЕРЕКОСЫ, которые надо лечить числами, а не молча:')
        for p in problems:
            print('   ' + p)
        return 1
    print('Перекосов нет: у трёх честных типов «без фильтров» не хуже любой '
          'ЗАЧЁТНОЙ стратегии во всех режимах, и не хуже любой стратегии '
          'по среднему.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
