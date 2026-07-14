"""
Архетип 8 (Блок Б): издержки фирмы с квадратичной TC(Q) = F + gQ + hQ².

FC = F, VC = gQ + hQ², AVC = g + hQ, MC = g + 2hQ, ATC = TC/Q.
Минимум ATC: Q_min = √(F/h) (точка, где hQ = F/Q), ATC_min = g + 2h·Q_min.

Обратный ход: Q_min сэмплируется красивым, F = h·Q_min² вычисляется;
точка запроса Q₀ выбирается так, чтобы ATC(Q₀) был целым (Q₀ | F).

Контроль (TC = 100 + 20Q + 4Q²): FC = 100; Q_min = 5; ATC_min = 60;
MC(5) = 60; AVC(5) = 40.
"""
import math
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, fmt_coef
from . import _market


def tc_formula(params):
    """'$TC(Q) = 100 + 20Q + 4Q^2$' с чисткой единичных коэффициентов."""
    g, h = params['g'], params['h']
    parts = [fmt_num(params['F'], latex=True)]
    if g:
        parts.append('{}Q'.format(fmt_coef(g)))
    parts.append('{}Q^2'.format(fmt_coef(h)))
    return '$TC(Q) = {}$'.format(' + '.join(parts))


class CostsTCArchetype(Archetype):
    key = 'costs_tc'
    title = u'Издержки фирмы (квадратичная TC)'
    block = u'Б. Фирма и издержки'
    topics = [u'Теория фирмы: производство и издержки']

    def sample(self, rng):
        for _ in range(100):
            q_min = rng.choice([2, 3, 4, 5, 6, 8, 10])
            h = rng.choice([1, 1, 2, 2, 3, 4, 5])
            g = rng.choice(range(4, 41, 2))
            f_cost = h * q_min * q_min
            # точка запроса: ATC(Q0) целый ⟺ Q0 делит F
            q_cands = [q for q in range(2, 16)
                       if q != q_min and f_cost % q == 0]
            if not q_cands:
                continue
            q0 = rng.choice(q_cands + [q_min])
            return {'F': f_cost, 'g': g, 'h': h, 'q0': q0,
                    'good': rng.randrange(len(_market.GOODS))}
        raise RuntimeError('costs_tc: не сэмплировались красивые издержки')

    def solve(self, params):
        f_cost, g, h = F(params['F']), F(params['g']), F(params['h'])
        q0 = F(params['q0'])
        q_min_sq = f_cost / h
        # Q_min красив по построению (F = h·Q_min²) — целочисленный корень
        assert q_min_sq.denominator == 1
        q_min = Fraction(math.isqrt(q_min_sq.numerator))
        assert q_min * q_min == q_min_sq
        return {
            'fc': f_cost,
            'vc0': g * q0 + h * q0 * q0,
            'tc0': f_cost + g * q0 + h * q0 * q0,
            'atc0': (f_cost + g * q0 + h * q0 * q0) / q0,
            'avc0': g + h * q0,
            'mc0': g + 2 * h * q0,
            'q_min': q_min,
            'atc_min': g + 2 * h * q_min,
        }

    def asked_values(self, params):
        q0 = params['q0']
        at_q = u'при выпуске $Q = {}$'.format(q0)
        return [
            Asked('fc', nom=u'величина постоянных издержек фирмы',
                  acc=u'величину постоянных издержек фирмы', gender='f',
                  unit=u'ден. ед.', trivial=True),
            Asked('vc0', nom=u'переменные издержки ' + at_q,
                  acc=u'переменные издержки ' + at_q, gender='p',
                  unit=u'ден. ед.'),
            Asked('atc0', nom=u'средние общие издержки ' + at_q,
                  acc=u'средние общие издержки ' + at_q, gender='p',
                  unit=u'ден. ед.'),
            Asked('avc0', nom=u'средние переменные издержки ' + at_q,
                  acc=u'средние переменные издержки ' + at_q, gender='p',
                  unit=u'ден. ед.'),
            Asked('mc0', nom=u'предельные издержки ' + at_q,
                  acc=u'предельные издержки ' + at_q, gender='p',
                  unit=u'ден. ед.'),
            Asked('q_min', nom=u'выпуск, при котором средние общие издержки минимальны',
                  acc=u'выпуск, при котором средние общие издержки минимальны',
                  gender='m', unit=u'шт.'),
            Asked('atc_min', nom=u'минимальное значение средних общих издержек',
                  acc=u'минимальное значение средних общих издержек',
                  gender='n', unit=u'ден. ед.'),
        ]

    def error_variants(self, params, solved, asked):
        f_cost, g, h = F(params['F']), F(params['g']), F(params['h'])
        q0 = F(params['q0'])
        if asked.key == 'fc':
            return [g, h, f_cost + g, solved['vc0'], f_cost / q0]
        if asked.key == 'vc0':
            return [solved['tc0'],       # забыли вычесть FC
                    g * q0,              # потеряно квадратичное слагаемое
                    h * q0 * q0,         # потеряно линейное
                    solved['avc0'],      # средние вместо суммарных
                    f_cost]
        if asked.key == 'atc0':
            return [solved['avc0'],      # забыт FC-компонент
                    solved['mc0'],
                    solved['vc0'] / q0,  # то же, что AVC — дубль отфильтруется
                    solved['tc0'],       # не поделили
                    g + h * q0 + f_cost]
        if asked.key == 'avc0':
            return [solved['atc0'],      # прихвачен FC
                    solved['mc0'],       # спутано с предельными
                    g,                   # потеряно hQ
                    h * q0,
                    solved['vc0']]
        if asked.key == 'mc0':
            return [solved['avc0'],      # спутано со средними переменными
                    solved['atc0'],
                    g + h * q0,          # производная без двойки
                    2 * h * q0,          # потеряно g
                    solved['tc0'] / q0]
        if asked.key == 'q_min':
            return [f_cost / h,          # забыт корень (Q²)
                    solved['atc_min'],   # перепутаны Q и ATC
                    2 * solved['q_min'],
                    g / (2 * h),
                    f_cost / g]
        # atc_min
        return [g + h * solved['q_min'],       # AVC в точке минимума
                2 * h * solved['q_min'],       # потеряно g
                solved['q_min'],               # перепутаны Q и ATC
                2 * solved['atc_min'],
                g]

    def wrappers(self):
        def full(p, s):
            good = _market.GOODS[p['good']]
            return (u'Фирма производит {}. Её общие издержки описываются '
                    u'функцией {}, где $Q$ — выпуск (в шт.), издержки — '
                    u'в ден. ед.').format(good[1], tc_formula(p))

        def full_plant(p, s):
            good = _market.GOODS[p['good']]
            return (u'Технологи завода, выпускающего {}, оценили функцию '
                    u'общих издержек: {} ($Q$ — выпуск в шт., '
                    u'издержки — в ден. ед.).').format(good[1], tc_formula(p))

        def short(p, s):
            return u'Издержки фирмы: {} ($Q$ — шт., издержки — ден. ед.).'.format(
                tc_formula(p))

        return [Wrapper('firm', full, short),
                Wrapper('plant', full_plant, short)]

    def solution(self, params, solved, asked):
        f_cost, g, h = params['F'], params['g'], params['h']
        q0 = params['q0']
        if asked.key == 'fc':
            return [u'Постоянные издержки — слагаемое TC, не зависящее от $Q$: '
                    u'$FC = {}$ ден. ед.'.format(fmt_num(f_cost, latex=True))]
        if asked.key == 'vc0':
            return [
                u'Переменные издержки: $VC(Q) = TC(Q) - FC = {}Q + {}Q^2$.'.format(
                    fmt_coef(g), fmt_coef(h)),
                u'При $Q = {}$: $VC = {}$ ден. ед.'.format(
                    q0, fmt_num(solved['vc0'], latex=True)),
            ]
        if asked.key == 'atc0':
            return [
                u'Общие издержки при $Q = {}$: $TC = {}$ ден. ед.'.format(
                    q0, fmt_num(solved['tc0'], latex=True)),
                u'Средние общие: $ATC = TC / Q = {} / {} = {}$ ден. ед.'.format(
                    fmt_num(solved['tc0'], latex=True), q0,
                    fmt_num(solved['atc0'], latex=True)),
            ]
        if asked.key == 'avc0':
            return [
                u'Средние переменные издержки: $AVC(Q) = VC/Q = {} + {}Q$.'.format(
                    fmt_num(g, latex=True), fmt_coef(h)),
                u'При $Q = {}$: $AVC = {}$ ден. ед.'.format(
                    q0, fmt_num(solved['avc0'], latex=True)),
            ]
        if asked.key == 'mc0':
            return [
                u'Предельные издержки квадратичной TC: $MC(Q) = {} + {}Q$.'.format(
                    fmt_num(g, latex=True), fmt_coef(2 * F(h))),
                u'При $Q = {}$: $MC = {}$ ден. ед.'.format(
                    q0, fmt_num(solved['mc0'], latex=True)),
            ]
        if asked.key == 'q_min':
            return [
                u'ATC минимальны там, где $\\frac{{F}}{{Q}} = {}Q$ '
                u'(средние постоянные равны переменной части): '
                u'$Q^2 = F/h = {}$.'.format(
                    fmt_coef(h), fmt_num(F(f_cost) / F(h), latex=True)),
                u'Отсюда $Q_{{min}} = {}$ шт.'.format(
                    fmt_num(solved['q_min'], latex=True)),
            ]
        # atc_min
        return [
            u'Минимум ATC достигается при $Q^2 = F/h$: $Q_{{min}} = {}$ шт.'.format(
                fmt_num(solved['q_min'], latex=True)),
            u'В точке минимума $ATC = MC$: $ATC_{{min}} = {} + 2 \\cdot {} '
            u'\\cdot {} = {}$ ден. ед.'.format(
                fmt_num(g, latex=True), fmt_num(h, latex=True),
                fmt_num(solved['q_min'], latex=True),
                fmt_num(solved['atc_min'], latex=True)),
        ]


ARCHETYPE = CostsTCArchetype()
