"""
Архетип 10 (Блок Б): монополия со спросом P = a − bQ и MC = const.

MR = a − 2bQ = MC → Q_m = (a − MC)/(2b), P_m = a − b·Q_m;
прибыль (без FC) = (P_m − MC)·Q_m = b·Q_m²; конкурентный выпуск
Q_c = 2·Q_m; DWL = ½·(P_m − MC)·(Q_c − Q_m) = b·Q_m²/2.

Обратный ход: сэмплируется Q_m, a вычисляется; чётность b·Q_m²
гарантирует целый DWL.

Контроль (P = 100 − Q, MC = 20): Q_m = 40, P_m = 60, прибыль = 1600,
Q_c = 80, DWL = 800.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_eq
from . import _market


class MonopolyArchetype(Archetype):
    key = 'monopoly'
    title = u'Монополия (MR = MC)'
    block = u'Б. Фирма и издержки'
    topics = [u'Монополия и ценовая дискриминация']

    def sample(self, rng):
        for _ in range(100):
            q_m = rng.choice([10, 15, 20, 25, 30, 40, 50])
            b = rng.choice([1, 1, 1, 2, 2, 3])
            mc = rng.choice(range(4, 41, 2))
            if (b * q_m * q_m) % 2:      # DWL = b·Q_m²/2 должен быть целым
                continue
            return {'a': mc + 2 * b * q_m, 'b': b, 'mc': mc,
                    'good': rng.randrange(len(_market.GOODS))}
        raise RuntimeError('monopoly: не сэмплировалась красивая монополия')

    def solve(self, params):
        a, b, mc = F(params['a']), F(params['b']), F(params['mc'])
        q_m = (a - mc) / (2 * b)
        p_m = a - b * q_m
        profit = (p_m - mc) * q_m
        q_c = (a - mc) / b
        dwl = (p_m - mc) * (q_c - q_m) / 2
        return {'q_m': q_m, 'p_m': p_m, 'profit': profit,
                'q_c': q_c, 'dwl': dwl}

    def asked_values(self, params):
        return [
            Asked('q_m', nom=u'оптимальный выпуск монополиста',
                  acc=u'оптимальный выпуск монополиста', gender='m',
                  unit=u'шт.'),
            Asked('p_m', nom=u'цена, которую назначит монополист',
                  acc=u'цену, которую назначит монополист', gender='f',
                  unit=u'ден. ед.'),
            Asked('profit', nom=u'максимальная прибыль монополиста',
                  acc=u'максимальную прибыль монополиста', gender='f',
                  unit=u'ден. ед.'),
            Asked('q_c', nom=(u'объём продаж, который сложился бы при '
                              u'конкурентном ценообразовании ($P = MC$)'),
                  acc=(u'объём продаж, который сложился бы при конкурентном '
                       u'ценообразовании ($P = MC$)'), gender='m', unit=u'шт.'),
            Asked('dwl', nom=u'величина чистых потерь общества от монополии',
                  acc=u'величину чистых потерь общества от монополии',
                  gender='f', unit=u'ден. ед.'),
        ]

    def error_variants(self, params, solved, asked):
        a, b, mc = F(params['a']), F(params['b']), F(params['mc'])
        q_m, p_m = solved['q_m'], solved['p_m']
        if asked.key == 'q_m':
            return [solved['q_c'],       # забыто удвоение наклона MR
                    a / (2 * b),         # потеряна MC
                    (a - mc) / 2,        # потерян наклон
                    a / b,
                    q_m / 2]
        if asked.key == 'p_m':
            return [mc,                  # цена = MC (конкурентная логика)
                    a,                   # цена спроса при Q = 0
                    q_m,                 # перепутаны P и Q
                    b * q_m,             # наценка вместо цены
                    a - mc]
        if asked.key == 'profit':
            return [p_m * q_m,           # выручка вместо прибыли
                    solved['dwl'],
                    (a - mc) * q_m,      # взята вся высота спроса
                    mc * q_m,
                    solved['profit'] / 2]
        if asked.key == 'q_c':
            return [q_m,                 # монопольный вместо конкурентного
                    a / b,               # спрос при P = 0
                    (a + mc) / (2 * b),
                    3 * q_m]
        # dwl
        return [solved['profit'],        # прибыль вместо DWL
                2 * solved['dwl'],       # забыта 1/2
                p_m * q_m / 2,
                (a - mc) * q_m / 2,
                solved['q_c']]

    def wrappers(self):
        def demand(p):
            return linear_eq('P', p['a'], -F(p['b']), 'Q')

        def full(p, s):
            good = _market.GOODS[p['good']]
            return (u'Единственный производитель {} в городе N — монополист. '
                    u'Спрос на его продукцию: {}, где $P$ — цена (в ден. ед.), '
                    u'$Q$ — количество (в шт.). Предельные издержки постоянны '
                    u'и равны {} ден. ед., постоянных издержек нет.').format(
                        good[0], demand(p), p['mc'])

        def full_patent(p, s):
            good = _market.GOODS[p['good']]
            return (u'Фирма получила патент и стала монополистом на рынке {}. '
                    u'Спрос описывается уравнением {} ($P$ — в ден. ед., '
                    u'$Q$ — в шт.); каждая дополнительная единица обходится '
                    u'фирме в {} ден. ед., постоянных издержек нет.').format(
                        good[0], demand(p), p['mc'])

        def short(p, s):
            return (u'Монополия: спрос {}, $MC = {}$ ден. ед. '
                    u'(постоянных издержек нет).').format(demand(p), p['mc'])

        return [Wrapper('city', full, short),
                Wrapper('patent', full_patent, short)]

    def solution(self, params, solved, asked):
        a, b, mc = params['a'], params['b'], params['mc']
        steps = [
            u'Предельная выручка при спросе $P = {} - {}Q$: $MR = {} - {}Q$.'.format(
                fmt_num(a, latex=True),
                fmt_num(b, latex=True) if b != 1 else '',
                fmt_num(a, latex=True), fmt_num(2 * F(b), latex=True)),
            u'$MR = MC$: ${} - {}Q = {} \\Rightarrow Q_m = {}$ шт.'.format(
                fmt_num(a, latex=True), fmt_num(2 * F(b), latex=True), mc,
                fmt_num(solved['q_m'], latex=True)),
        ]
        if asked.key in ('p_m', 'profit', 'dwl'):
            steps.append(u'Цена монополиста: $P_m = {} - {} = {}$ ден. ед.'.format(
                fmt_num(a, latex=True),
                fmt_num(F(b) * solved['q_m'], latex=True),
                fmt_num(solved['p_m'], latex=True)))
        if asked.key == 'profit':
            steps.append(
                u'Прибыль: $\\pi = (P_m - MC) \\cdot Q_m = ({} - {}) \\cdot {} '
                u'= {}$ ден. ед.'.format(
                    fmt_num(solved['p_m'], latex=True), mc,
                    fmt_num(solved['q_m'], latex=True),
                    fmt_num(solved['profit'], latex=True)))
        if asked.key in ('q_c', 'dwl'):
            steps.append(
                u'При конкурентном ценообразовании $P = MC$: $Q_c = {}$ шт.'.format(
                    fmt_num(solved['q_c'], latex=True)))
        if asked.key == 'dwl':
            steps.append(
                u'Чистые потери: $DWL = \\frac{{1}}{{2}} (P_m - MC)(Q_c - Q_m) '
                u'= \\frac{{1}}{{2}} \\cdot {} \\cdot {} = {}$ ден. ед.'.format(
                    fmt_num(solved['p_m'] - mc, latex=True),
                    fmt_num(solved['q_c'] - solved['q_m'], latex=True),
                    fmt_num(solved['dwl'], latex=True)))
        return steps


ARCHETYPE = MonopolyArchetype()
