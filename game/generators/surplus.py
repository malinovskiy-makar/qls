"""
Архетип 7 (Блок А): излишек потребителей (CS) и производителей (PS)
в равновесии линейного рынка.

Для Qd = a − bP, Qs = c + dP: высота треугольника CS равна Q*/b, а PS — Q*/d,
поэтому CS = Q*²/(2b), PS = Q*²/(2d). Валидный треугольник PS требует
неотрицательной цены предложения при Q = 0, то есть c ≤ 0 — это ограничение
сэмплера. Обратный ход: Q* подбирается так, чтобы оба излишка были целыми.

Контроль: Qd = 100 − P, Qs = P → CS = PS = 1250.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market


class SurplusArchetype(Archetype):
    key = 'surplus'
    title = u'Излишки потребителей и производителей'
    block = u'А. Рынок'
    topics = [u'Спрос и предложение']

    def sample(self, rng):
        for _ in range(300):
            p_star = rng.choice(_market.P_GRID)
            b = rng.choice([1, 1, 2, 2, 5])
            d = rng.choice([1, 1, 2, 2, 5])
            q_cands = [q for q in _market.Q_GRID
                       if q <= d * p_star            # c ≤ 0: валидный треугольник PS
                       and (q * q) % (2 * b) == 0    # CS целый
                       and (q * q) % (2 * d) == 0]   # PS целый
            if not q_cands:
                continue
            q_star = rng.choice(q_cands)
            return {
                'a': q_star + b * p_star, 'b': b,
                'c': q_star - d * p_star, 'd': d,
                'good': rng.randrange(len(_market.GOODS)),
            }
        raise RuntimeError('surplus: не сэмплировался валидный рынок')

    def solve(self, params):
        b, d = F(params['b']), F(params['d'])
        p_star, q_star = _market.solve_market(params)
        cs = q_star * q_star / (2 * b)
        ps = q_star * q_star / (2 * d)
        return {'p_star': p_star, 'q_star': q_star,
                'cs': cs, 'ps': ps, 'total': cs + ps}

    def asked_values(self, params):
        return [
            Asked('cs', nom=u'величина излишка потребителей',
                  acc=u'величину излишка потребителей', gender='f',
                  unit=u'ден. ед.'),
            Asked('ps', nom=u'величина излишка производителей',
                  acc=u'величину излишка производителей', gender='f',
                  unit=u'ден. ед.'),
            Asked('total', nom=u'суммарный общественный излишек',
                  acc=u'суммарный общественный излишек', gender='m',
                  unit=u'ден. ед.'),
        ]

    def error_variants(self, params, solved, asked):
        p, q = solved['p_star'], solved['q_star']
        cs, ps, total = solved['cs'], solved['ps'], solved['total']
        if asked.key == 'cs':
            return [2 * cs,          # забыта 1/2
                    ps,              # не тот излишек
                    p * q / 2,       # высота до нуля, а не до цены спроса
                    total,
                    p * q]           # вся выручка
        if asked.key == 'ps':
            return [2 * ps, cs, p * q / 2, total, p * q]
        return [cs, ps, 2 * total, p * q,
                total / 2]

    def wrappers(self):
        return [
            Wrapper('city', _market.setup_full, _market.setup_short),
            Wrapper('country', _market.setup_full_country,
                    _market.setup_short_bare),
            Wrapper('analysts', _market.setup_full_analysts,
                    _market.setup_short),
        ]

    def solution(self, params, solved, asked):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        p, q = solved['p_star'], solved['q_star']
        steps = [
            u'Равновесие: $P^* = {}$ ден. ед., $Q^* = {}$ шт.'.format(
                fmt_num(p, latex=True), fmt_num(q, latex=True)),
        ]
        if asked.key in ('cs', 'total'):
            steps.append(
                (u'Цена спроса при $Q = 0$: ${}$; излишек потребителей '
                 u'образует треугольник: $CS = \\frac{{1}}{{2}}({} - {}) \\cdot {} '
                 u'= {}$ ден. ед.').format(
                     fmt_num(a / b, latex=True), fmt_num(a / b, latex=True),
                     fmt_num(p, latex=True), fmt_num(q, latex=True),
                     fmt_num(solved['cs'], latex=True)))
        if asked.key in ('ps', 'total'):
            steps.append(
                (u'Цена предложения при $Q = 0$: ${}$; излишек производителей: '
                 u'$PS = \\frac{{1}}{{2}}({} - {}) \\cdot {} = {}$ '
                 u'ден. ед.').format(
                     fmt_num(-c / d, latex=True), fmt_num(p, latex=True),
                     fmt_num(-c / d, latex=True), fmt_num(q, latex=True),
                     fmt_num(solved['ps'], latex=True)))
        if asked.key == 'total':
            steps.append(u'Суммарный излишек: ${} + {} = {}$ ден. ед.'.format(
                fmt_num(solved['cs'], latex=True),
                fmt_num(solved['ps'], latex=True),
                fmt_num(solved['total'], latex=True)))
        return steps


ARCHETYPE = SurplusArchetype()
