"""
Архетип 6 (Блок А): дуговая эластичность (формула средней точки) между двумя
точками кривой спроса; производный вопрос — как изменится выручка.

|E| = (ΔQ/ΔP)·((P1+P2)/(Q1+Q2)). Полезное тождество: |E| = 1 в средней точке
⟺ P1·Q1 = P2·Q2, |E| > 1 ⟺ выручка при росте цены падает — классификация
выручки строго согласована с эластичностью.

Обратный ход: сначала |E| из красивой сетки и пара цен, затем подбирается
сумма объёмов, при которой ΔQ целое и той же чётности.

Контроль: (P=40, Q=60) → (P=60, Q=40): |E| = 1, выручка не меняется.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market

E_GRID = [1, 1, 2, 2, 3, 3, 4, 5,
          Fraction(1, 2), Fraction(3, 2), Fraction(5, 2), Fraction(1, 4)]

REV_LABELS = [u'вырастет', u'снизится', u'не изменится']


class ElasticityArcArchetype(Archetype):
    key = 'elasticity_arc'
    title = u'Дуговая эластичность и выручка'
    block = u'А. Рынок'
    topics = [u'Эластичность']

    def sample(self, rng):
        for _ in range(300):
            e = Fraction(rng.choice(E_GRID))
            p1 = rng.choice(range(10, 91, 5))
            p2 = p1 + rng.choice([10, 20, 30, 40])
            sp, dp = p1 + p2, p2 - p1
            sq = rng.choice(range(40, 301, 10))
            dq = e * dp * sq / sp
            if dq.denominator != 1:
                continue
            dq = int(dq)
            if not (0 < dq < sq) or (sq - dq) % 2:
                continue
            q1, q2 = (sq + dq) // 2, (sq - dq) // 2
            if q2 <= 0:
                continue
            return {'p1': p1, 'p2': p2, 'q1': q1, 'q2': q2,
                    'good': rng.randrange(len(_market.GOODS))}
        raise RuntimeError('elasticity_arc: не сэмплировались красивые точки')

    def solve(self, params):
        p1, p2 = F(params['p1']), F(params['p2'])
        q1, q2 = F(params['q1']), F(params['q2'])
        e_arc = (q1 - q2) * (p1 + p2) / ((p2 - p1) * (q1 + q2))
        r1, r2 = p1 * q1, p2 * q2
        if r2 > r1:
            rev_class = REV_LABELS[0]
        elif r2 < r1:
            rev_class = REV_LABELS[1]
        else:
            rev_class = REV_LABELS[2]
        return {'e_arc': e_arc, 'r1': r1, 'r2': r2,
                'rev_class': rev_class, 'dr_abs': abs(r2 - r1)}

    def asked_values(self, params):
        solved = self.solve(params)
        asked = [
            Asked('e_arc',
                  nom=u'модуль дуговой эластичности спроса (по формуле средней точки)',
                  acc=u'модуль дуговой эластичности спроса (по формуле средней точки)',
                  gender='m', unit=''),
            Asked('rev_class', kind='class', class_options=list(REV_LABELS),
                  question=u'Как при таком подорожании изменится выручка продавцов?',
                  claim_tpl=u'выручка продавцов при этом {V}'),
        ]
        if solved['dr_abs'] != 0:
            verb = solved['rev_class']  # «вырастет» / «снизится»
            asked.append(Asked(
                'dr_abs', unit=u'ден. ед.',
                question=u'На сколько ден. ед. {} выручка продавцов?'.format(verb),
                claim_tpl=u'выручка продавцов {} на {{V}} ден. ед.'.format(verb),
                nom=u'изменение выручки', gender='n'))
        return asked

    def error_variants(self, params, solved, asked):
        p1, p2 = F(params['p1']), F(params['p2'])
        q1, q2 = F(params['q1']), F(params['q2'])
        dp, dq = p2 - p1, q1 - q2
        e = solved['e_arc']
        if asked.key == 'e_arc':
            errs = [
                dq * p1 / (dp * q1),        # эластичность по начальной точке
                dq * p2 / (dp * q2),        # по конечной точке
                dp * (q1 + q2) / (dq * (p1 + p2)),  # перевёрнутая формула
                dq / dp,                    # забыты средние точки
            ]
            if e != 0:
                errs.append(1 / e)
            errs.append(2 * e)
            return errs
        # dr_abs
        return [solved['r1'],               # взяли старую выручку целиком
                solved['r2'],
                dp * (q1 + q2) / 2,         # ΔP на средний объём
                dq * (p1 + p2) / 2,
                solved['dr_abs'] * 2]

    def wrappers(self):
        def full(p, s):
            good = _market.GOODS[p['good']]
            return (u'На рынке {} цена выросла с {} до {} ден. ед., '
                    u'а объём покупок снизился с {} до {} шт.').format(
                        good[0], p['p1'], p['p2'], p['q1'], p['q2'])

        def full_analysts(p, s):
            good = _market.GOODS[p['good']]
            return (u'Аналитики наблюдают за рынком {}. После подорожания '
                    u'единицы товара с {} до {} ден. ед. объём продаж '
                    u'сократился с {} до {} шт.').format(
                        good[0], p['p1'], p['p2'], p['q1'], p['q2'])

        def short(p, s):
            return (u'Цена {} выросла с {} до {} ден. ед., спрос снизился '
                    u'с {} до {} шт.').format(
                        _market.GOODS[p['good']][0],
                        p['p1'], p['p2'], p['q1'], p['q2'])

        return [Wrapper('observed', full, short),
                Wrapper('analysts', full_analysts, short)]

    def solution(self, params, solved, asked):
        p1, p2 = params['p1'], params['p2']
        q1, q2 = params['q1'], params['q2']
        steps = [
            u'$\\Delta P = {}$, $\\Delta Q = {}$; суммы: $P_1 + P_2 = {}$, '
            u'$Q_1 + Q_2 = {}$.'.format(p2 - p1, q1 - q2, p1 + p2, q1 + q2),
            (u'Дуговая эластичность: $|E| = \\frac{{\\Delta Q}}{{\\Delta P}} '
             u'\\cdot \\frac{{P_1 + P_2}}{{Q_1 + Q_2}} = '
             u'\\frac{{{}}}{{{}}} \\cdot \\frac{{{}}}{{{}}} = {}$.').format(
                 q1 - q2, p2 - p1, p1 + p2, q1 + q2,
                 fmt_num(solved['e_arc'], latex=True)),
        ]
        if asked.key != 'e_arc':
            steps.append(
                u'Выручка: $R_1 = {} \\cdot {} = {}$, $R_2 = {} \\cdot {} = {}$ '
                u'ден. ед. — выручка {}.'.format(
                    p1, q1, fmt_num(solved['r1'], latex=True),
                    p2, q2, fmt_num(solved['r2'], latex=True),
                    solved['rev_class']))
        if asked.key == 'dr_abs':
            steps.append(u'Изменение выручки: $|{} - {}| = {}$ ден. ед.'.format(
                fmt_num(solved['r2'], latex=True),
                fmt_num(solved['r1'], latex=True),
                fmt_num(solved['dr_abs'], latex=True)))
        return steps


ARCHETYPE = ElasticityArcArchetype()
