"""
Бонус-архетип 17: совершенная ценовая дискриминация монополиста.

Спрос P = a − bQ, MC = const. Совершенный дискриминатор продаёт каждую
единицу по цене спроса, пока она выше MC: выпуск конкурентный
Q_pd = (a − MC)/b, прибыль (без FC) — весь треугольник между спросом и MC:
π = ½·(a − MC)·Q_pd, ровно вдвое больше прибыли обычной монополии.

Контроль (P = 100 − Q, MC = 20): выпуск = 80, прибыль = 3200.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_eq
from . import _market


class PerfectPDArchetype(Archetype):
    key = 'perfect_price_discrimination'
    title = u'Совершенная ценовая дискриминация'
    block = u'Б. Фирма и издержки'
    topics = [u'Монополия и ценовая дискриминация']

    def sample(self, rng):
        for _ in range(100):
            q_m = rng.choice([10, 15, 20, 25, 30, 40, 50])
            b = rng.choice([1, 1, 1, 2, 2, 3])
            mc = rng.choice(range(4, 41, 2))
            # прибыль дискриминатора 2b·Q_m² всегда целая; следим лишь,
            # чтобы обычная монопольная прибыль (для дистракторов) была целой
            if (b * q_m * q_m) % 2:
                continue
            return {'a': mc + 2 * b * q_m, 'b': b, 'mc': mc,
                    'good': rng.randrange(len(_market.GOODS))}
        raise RuntimeError('perfect_pd: не сэмплировалась красивая монополия')

    def solve(self, params):
        a, b, mc = F(params['a']), F(params['b']), F(params['mc'])
        q_pd = (a - mc) / b               # выпуск = конкурентному
        profit_pd = (a - mc) * q_pd / 2   # весь треугольник над MC
        q_m = q_pd / 2
        profit_m = b * q_m * q_m
        return {'q_pd': q_pd, 'profit_pd': profit_pd,
                'q_m': q_m, 'profit_m': profit_m,
                'extra': profit_pd - profit_m}

    def asked_values(self, params):
        return [
            Asked('q_pd', nom=u'выпуск монополиста-дискриминатора',
                  acc=u'выпуск монополиста-дискриминатора', gender='m',
                  unit=u'шт.'),
            Asked('profit_pd',
                  nom=u'прибыль монополиста при совершенной дискриминации',
                  acc=u'прибыль монополиста при совершенной дискриминации',
                  gender='f', unit=u'ден. ед.'),
            Asked('extra',
                  nom=(u'прирост прибыли по сравнению с единой '
                       u'монопольной ценой'),
                  acc=(u'прирост прибыли по сравнению с единой '
                       u'монопольной ценой'),
                  gender='m', unit=u'ден. ед.'),
        ]

    def error_variants(self, params, solved, asked):
        a, b, mc = F(params['a']), F(params['b']), F(params['mc'])
        if asked.key == 'q_pd':
            return [solved['q_m'],           # выпуск обычной монополии
                    a / b,                   # спрос при P = 0
                    a / (2 * b),
                    (a + mc) / (2 * b)]
        if asked.key == 'profit_pd':
            return [solved['profit_m'],      # прибыль обычной монополии
                    (a - mc) * solved['q_pd'],   # забыта 1/2
                    solved['extra'],
                    mc * solved['q_pd'],
                    a * solved['q_pd'] / 2]
        # extra
        return [solved['profit_pd'],
                solved['profit_m'],
                2 * solved['extra'],
                solved['extra'] / 2]

    def wrappers(self):
        def demand(p):
            return linear_eq('P', p['a'], -F(p['b']), 'Q')

        def full(p, s):
            good = _market.GOODS[p['good']]
            return (u'Монополист на рынке {} знает готовность платить каждого '
                    u'покупателя и назначает каждому индивидуальную цену '
                    u'(совершенная ценовая дискриминация). Спрос: {} '
                    u'($P$ в ден. ед., $Q$ в шт.); предельные издержки '
                    u'постоянны и равны {} ден. ед., постоянных издержек '
                    u'нет.').format(good[0], demand(p), p['mc'])

        def short(p, s):
            return (u'Монополист-совершенный дискриминатор: спрос {}, '
                    u'$MC = {}$ (пост. изд. нет).').format(demand(p), p['mc'])

        return [Wrapper('pd', full, short)]

    def solution(self, params, solved, asked):
        a, b, mc = params['a'], params['b'], params['mc']
        steps = [
            (u'Дискриминатор продаёт каждую единицу по цене спроса, пока она '
             u'не ниже $MC$: выпуск из $P(Q) = MC$: $Q = {}$ шт.').format(
                fmt_num(solved['q_pd'], latex=True)),
            (u'Прибыль составляет весь треугольник между спросом и $MC$: '
             u'$\\pi = \\frac{{1}}{{2}} ({} - {}) \\cdot {} = {}$ '
             u'ден. ед.').format(
                fmt_num(a, latex=True), fmt_num(mc, latex=True),
                fmt_num(solved['q_pd'], latex=True),
                fmt_num(solved['profit_pd'], latex=True)),
        ]
        if asked.key == 'extra':
            steps.append(
                (u'Обычная монополия: $Q_m = {}$, $\\pi_m = {}$; прирост: '
                 u'${} - {} = {}$ ден. ед.').format(
                    fmt_num(solved['q_m'], latex=True),
                    fmt_num(solved['profit_m'], latex=True),
                    fmt_num(solved['profit_pd'], latex=True),
                    fmt_num(solved['profit_m'], latex=True),
                    fmt_num(solved['extra'], latex=True)))
        return steps


ARCHETYPE = PerfectPDArchetype()
