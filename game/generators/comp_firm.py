"""
Архетип 9 (Блок Б): совершенно конкурентная фирма — дана цена P,
из P = MC найти оптимальный выпуск, затем выручку/прибыль.

TC = F + gQ + hQ²; P = MC = g + 2hQ → Q* = (P − g)/(2h);
π = P·Q* − TC(Q*) = h·Q*² − F. Обратный ход: сэмплируются Q* и прибыль,
цена и F вычисляются.

Контроль (TC = 100 + 20Q + 4Q², P = 100): Q* = 10, прибыль = 300.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market
from .costs_tc import tc_formula


class CompFirmArchetype(Archetype):
    key = 'comp_firm'
    title = u'Оптимум конкурентной фирмы'
    block = u'Б. Фирма и издержки'
    topics = [u'Совершенная конкуренция']

    def sample(self, rng):
        for _ in range(100):
            q_star = rng.choice([3, 4, 5, 6, 8, 10, 12, 15])
            h = rng.choice([1, 1, 2, 2, 3, 4, 5])
            g = rng.choice(range(4, 41, 2))
            price = g + 2 * h * q_star
            max_profit = h * q_star * q_star  # прибыль при F = 0
            profit_cands = [pi for pi in range(50, 1001, 50)
                            if pi < max_profit]
            if not profit_cands:
                continue
            profit = rng.choice(profit_cands)
            return {'F': max_profit - profit, 'g': g, 'h': h, 'p': price,
                    'good': rng.randrange(len(_market.GOODS))}
        raise RuntimeError('comp_firm: не сэмплировалась красивая фирма')

    def solve(self, params):
        f_cost, g, h = F(params['F']), F(params['g']), F(params['h'])
        price = F(params['p'])
        q_star = (price - g) / (2 * h)
        tc = f_cost + g * q_star + h * q_star * q_star
        revenue = price * q_star
        return {'q_star': q_star, 'revenue': revenue, 'tc': tc,
                'profit': revenue - tc}

    def asked_values(self, params):
        return [
            Asked('q_star', nom=u'оптимальный объём выпуска фирмы',
                  acc=u'оптимальный объём выпуска фирмы', gender='m',
                  unit=u'шт.'),
            Asked('revenue', nom=u'выручка фирмы в оптимуме',
                  acc=u'выручку фирмы в оптимуме', gender='f',
                  unit=u'ден. ед.'),
            Asked('profit', nom=u'максимальная прибыль фирмы',
                  acc=u'максимальную прибыль фирмы', gender='f',
                  unit=u'ден. ед.'),
        ]

    def error_variants(self, params, solved, asked):
        f_cost, g, h = F(params['F']), F(params['g']), F(params['h'])
        price = F(params['p'])
        q = solved['q_star']
        if asked.key == 'q_star':
            return [(price - g) / h,     # забыта двойка в MC
                    price / (2 * h),     # потеряно g
                    2 * q,
                    solved['profit']]    # перепутаны величины
        if asked.key == 'revenue':
            return [solved['profit'],    # прибыль вместо выручки
                    solved['tc'],
                    price * (price - g) / h,  # выручка при ошибочном Q
                    price * q / 2]
        # profit
        return [solved['revenue'],       # выручка вместо прибыли
                h * q * q,               # забыт F
                solved['revenue'] - f_cost,   # забыты переменные издержки
                2 * h * q * q - f_cost,       # использован MC·Q вместо TC
                solved['tc']]

    def wrappers(self):
        def full(p, s):
            good = _market.GOODS[p['good']]
            return (u'Совершенно конкурентная фирма продаёт {} по рыночной '
                    u'цене {} ден. ед. за штуку. Её общие издержки: {} '
                    u'($Q$ — выпуск в шт.).').format(
                        good[1], p['p'], tc_formula(p))

        def full_workshop(p, s):
            good = _market.GOODS[p['good']]
            return (u'Мастерская выпускает {} и работает на совершенно '
                    u'конкурентном рынке: сложившаяся цена равна {} ден. ед. '
                    u'Функция общих издержек мастерской: {} '
                    u'($Q$ — выпуск в шт.).').format(
                        good[1], p['p'], tc_formula(p))

        def short(p, s):
            return (u'Конкурентная фирма: цена {} ден. ед., издержки {} '
                    u'($Q$ — шт.).').format(p['p'], tc_formula(p))

        return [Wrapper('firm', full, short),
                Wrapper('workshop', full_workshop, short)]

    def solution(self, params, solved, asked):
        g, h, price = params['g'], params['h'], params['p']
        steps = [
            u'Оптимум конкурентной фирмы: $P = MC$, где $MC(Q) = {} + {}Q$.'.format(
                fmt_num(g, latex=True), fmt_num(2 * F(h), latex=True)),
            u'${} = {} + {}Q \\Rightarrow Q^* = {}$ шт.'.format(
                price, fmt_num(g, latex=True), fmt_num(2 * F(h), latex=True),
                fmt_num(solved['q_star'], latex=True)),
        ]
        if asked.key == 'revenue':
            steps.append(u'Выручка: $TR = P \\cdot Q^* = {} \\cdot {} = {}$ '
                         u'ден. ед.'.format(
                             price, fmt_num(solved['q_star'], latex=True),
                             fmt_num(solved['revenue'], latex=True)))
        elif asked.key == 'profit':
            steps.append(u'Издержки в оптимуме: $TC(Q^*) = {}$ ден. ед.'.format(
                fmt_num(solved['tc'], latex=True)))
            steps.append(u'Прибыль: $\\pi = TR - TC = {} - {} = {}$ ден. ед.'.format(
                fmt_num(solved['revenue'], latex=True),
                fmt_num(solved['tc'], latex=True),
                fmt_num(solved['profit'], latex=True)))
        return steps


ARCHETYPE = CompFirmArchetype()
