"""
Архетип 5 (Блок А): точечная эластичность спроса или предложения в равновесии.

|E_d| = b·P*/Q*, |E_s| = d·P*/Q*. Обратный ход: сначала выбирается красивое
значение |E| и объём Q*, из них вычисляется цена P* = |E|·Q*/наклон
(принимается, только если P* целая) — эластичность красива по построению.

Контроль: Qd = 100 − P, Qs = P → |E_d| = 1.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market

# Сетка целевых |E|: целые преобладают (правило «красивого ответа»).
E_GRID = [1, 1, 2, 2, 3, 3, 4, 5,
          Fraction(1, 2), Fraction(3, 2), Fraction(5, 2), Fraction(1, 4)]

CLASS_LABELS_D = [u'спрос в равновесии эластичен',
                  u'спрос в равновесии неэластичен',
                  u'эластичность спроса в равновесии единичная']
CLASS_LABELS_S = [u'предложение в равновесии эластично',
                  u'предложение в равновесии неэластично',
                  u'эластичность предложения в равновесии единичная']


class ElasticityPointArchetype(Archetype):
    key = 'elasticity_point'
    title = u'Точечная эластичность в равновесии'
    block = u'А. Рынок'
    topics = [u'Эластичность']

    def sample(self, rng):
        for _ in range(200):
            e = rng.choice(E_GRID)
            curve = rng.choice(['demand', 'supply'])
            slope = rng.choice([1, 2, 3])
            # Q* подбирается под выбранную |E| (иначе крупные целые |E|
            # выбраковывались бы по потолку цены и перекашивали распределение).
            q_cands = [q for q in _market.Q_GRID
                       if (Fraction(e) * q / slope).denominator == 1
                       and 5 <= Fraction(e) * q / slope <= 120]
            if not q_cands:
                continue
            q_star = rng.choice(q_cands)
            p_star = Fraction(e) * q_star / slope
            other = rng.choice(_market.SLOPES)
            b = slope if curve == 'demand' else other
            d = slope if curve == 'supply' else other
            p = {
                'a': int(q_star + b * p_star), 'b': b,
                'c': int(q_star - d * p_star), 'd': d,
                'good': rng.randrange(len(_market.GOODS)),
                'curve': curve,
            }
            return p
        raise RuntimeError('elasticity_point: не сэмплировалась красивая эластичность')

    def solve(self, params):
        p_star, q_star = _market.solve_market(params)
        e_d = F(params['b']) * p_star / q_star
        e_s = F(params['d']) * p_star / q_star
        e_abs = e_d if params['curve'] == 'demand' else e_s
        labels = CLASS_LABELS_D if params['curve'] == 'demand' else CLASS_LABELS_S
        if e_abs > 1:
            e_class = labels[0]
        elif e_abs < 1:
            e_class = labels[1]
        else:
            e_class = labels[2]
        return {'p_star': p_star, 'q_star': q_star, 'e_d': e_d, 'e_s': e_s,
                'e_abs': e_abs, 'e_class': e_class}

    def asked_values(self, params):
        demand = params['curve'] == 'demand'
        word = u'спроса' if demand else u'предложения'
        labels = CLASS_LABELS_D if demand else CLASS_LABELS_S
        return [
            Asked('e_abs',
                  nom=u'модуль точечной эластичности {} в точке равновесия'.format(word),
                  acc=u'модуль точечной эластичности {} в точке равновесия'.format(word),
                  gender='m', unit=''),
            Asked('e_class', kind='class', class_options=list(labels),
                  question=u'Как характеризуется {} по эластичности в точке '
                           u'равновесия?'.format(
                               u'спрос' if demand else u'предложение'),
                  claim_tpl=u'{V}'),
        ]

    def error_variants(self, params, solved, asked):
        b, d = F(params['b']), F(params['d'])
        p, q = solved['p_star'], solved['q_star']
        e = solved['e_abs']
        errs = [
            d * p / q if params['curve'] == 'demand' else b * p / q,  # не та кривая
            (b if params['curve'] == 'demand' else d) * q / p,        # P/Q перевёрнуто
            p / q,                                                    # забыт наклон
        ]
        if e != 0:
            errs.append(1 / e)                                        # обратная величина
        errs.append(e * 2)
        errs.append(F(params['b']) if params['curve'] == 'demand' else F(params['d']))
        return errs

    def wrappers(self):
        return [
            Wrapper('city', _market.setup_full, _market.setup_short),
            Wrapper('analysts', _market.setup_full_analysts,
                    _market.setup_short_bare),
        ]

    def solution(self, params, solved, asked):
        demand = params['curve'] == 'demand'
        slope = params['b'] if demand else params['d']
        steps = [
            u'Равновесие: $P^* = {}$ ден. ед., $Q^* = {}$ шт.'.format(
                fmt_num(solved['p_star'], latex=True),
                fmt_num(solved['q_star'], latex=True)),
            (u'Точечная эластичность {}: $|E| = {} \\cdot \\frac{{P^*}}{{Q^*}} '
             u'= {} \\cdot \\frac{{{}}}{{{}}} = {}$.').format(
                u'спроса' if demand else u'предложения',
                fmt_num(slope, latex=True), fmt_num(slope, latex=True),
                fmt_num(solved['p_star'], latex=True),
                fmt_num(solved['q_star'], latex=True),
                fmt_num(solved['e_abs'], latex=True)),
        ]
        if asked.key == 'e_class':
            e = solved['e_abs']
            cmp_word = u'больше' if e > 1 else (u'меньше' if e < 1 else u'равен')
            steps.append(u'Модуль эластичности {} 1 — {}.'.format(
                cmp_word, solved['e_class']))
        return steps


ARCHETYPE = ElasticityPointArchetype()
