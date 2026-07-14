"""
Архетип 1 (Блок А): равновесие на линейном рынке — найти P* или Q*.

Контроль: Qd = 100 − P, Qs = P → P* = 50, Q* = 50.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market


class EquilibriumArchetype(Archetype):
    key = 'equilibrium'
    title = u'Равновесие на рынке'
    block = u'А. Рынок'
    topics = [u'Спрос и предложение']

    def sample(self, rng):
        return _market.sample_market(rng)

    def solve(self, params):
        p_star, q_star = _market.solve_market(params)
        return {'p_star': p_star, 'q_star': q_star}

    def asked_values(self, params):
        return [
            Asked('p_star', nom=u'равновесная цена', acc=u'равновесную цену',
                  gender='f', unit=u'ден. ед.'),
            Asked('q_star', nom=u'равновесный объём продаж',
                  acc=u'равновесный объём продаж', gender='m', unit=u'шт.'),
        ]

    def error_variants(self, params, solved, asked):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        p_star, q_star = solved['p_star'], solved['q_star']
        p_sign_err = (a + c) / (b + d)          # знак c потерян
        if asked.key == 'p_star':
            errs = [
                p_sign_err,
                q_star,                          # перепутаны P и Q
                (a - c) / b,                     # наклон предложения потерян
                (a - c) / d,                     # наклон спроса потерян
                a / b,                           # цена спроса при Q = 0
            ]
            if b != d:
                errs.append((a - c) / (b - d))   # наклоны вычтены, а не сложены
            return errs
        return [
            p_star,                              # перепутаны P и Q
            a - b * p_sign_err,                  # спрос в ошибочной цене
            c + d * p_sign_err,                  # предложение в ошибочной цене
            a,                                   # спрос при P = 0
            (a + c) / 2,                         # среднее свободных членов
        ]

    def wrappers(self):
        return [
            Wrapper('city', _market.setup_full, _market.setup_short),
            Wrapper('country', _market.setup_full_country, _market.setup_short_bare),
            Wrapper('analysts', _market.setup_full_analysts, _market.setup_short),
        ]

    def solution(self, params, solved, asked):
        return _market.eq_solution_steps(
            params, solved['p_star'], solved['q_star'],
            with_q=(asked.key == 'q_star'))


ARCHETYPE = EquilibriumArchetype()
