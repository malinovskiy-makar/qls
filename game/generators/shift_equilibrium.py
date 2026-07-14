"""
Архетип 2 (Блок А): сдвиг спроса ИЛИ предложения на константу —
новое равновесие или его изменение.

Обратный ход: сдвиг Δ выбирается кратным (b+d), чтобы новая цена
сдвинулась на целое k = Δ/(b+d); тогда и объём меняется на целое.

Контроль: Qd = 130 − P (после сдвига +30 от 100 − P), Qs = P → P* = 65.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_eq
from . import _market

# Сюжетные причины сдвига: (side, направление) → варианты текста.
REASONS = {
    ('demand', 1): [u'После роста доходов покупателей',
                    u'После удачной рекламной кампании'],
    ('demand', -1): [u'После снижения доходов покупателей',
                     u'После смены потребительской моды'],
    ('supply', 1): [u'После удешевления сырья',
                    u'После внедрения новой технологии'],
    ('supply', -1): [u'После подорожания сырья',
                     u'После роста издержек производителей'],
}


class ShiftEquilibriumArchetype(Archetype):
    key = 'shift_equilibrium'
    title = u'Сдвиг спроса или предложения'
    block = u'А. Рынок'
    topics = [u'Спрос и предложение']

    def sample(self, rng):
        for _ in range(60):
            p = _market.sample_market(rng)
            side = rng.choice(['demand', 'supply'])
            k = rng.choice([5, 10, 15, 20]) * rng.choice([1, -1])
            delta = k * (p['b'] + p['d'])  # сдвиг кривой по количеству
            p['side'] = side
            p['delta'] = delta
            p['reason'] = rng.randrange(2)
            s = self.solve(p)
            # валидность: новое равновесие в первой четверти, спрос не вырожден
            new_a = p['a'] + (delta if side == 'demand' else 0)
            if s['p_new'] > 0 and s['q_new'] > 0 and new_a > 0:
                return p
        raise RuntimeError('shift_equilibrium: не сэмплировался валидный рынок')

    def solve(self, params):
        p0, q0 = _market.solve_market(params)
        shifted = dict(params)
        if params['side'] == 'demand':
            shifted['a'] = params['a'] + params['delta']
        else:
            shifted['c'] = params['c'] + params['delta']
        p1, q1 = _market.solve_market(shifted)
        return {
            'p0': p0, 'q0': q0, 'p_new': p1, 'q_new': q1,
            'dp_abs': abs(p1 - p0), 'dq_abs': abs(q1 - q0),
        }

    def _directions(self, params):
        """(глагол для цены, глагол для объёма) по знакам изменений."""
        delta_pos = params['delta'] > 0
        if params['side'] == 'demand':
            p_up = delta_pos
        else:
            p_up = not delta_pos
        q_up = delta_pos  # рост любой из кривых увеличивает Q*
        return (u'вырастет' if p_up else u'снизится',
                u'вырастет' if q_up else u'снизится')

    def asked_values(self, params):
        p_verb, q_verb = self._directions(params)
        return [
            Asked('p_new', nom=u'новая равновесная цена',
                  acc=u'новую равновесную цену', gender='f', unit=u'ден. ед.'),
            Asked('q_new', nom=u'новый равновесный объём продаж',
                  acc=u'новый равновесный объём продаж', gender='m',
                  unit=u'шт.'),
            Asked('dp_abs', unit=u'ден. ед.',
                  question=u'На сколько ден. ед. {} равновесная цена?'.format(p_verb),
                  claim_tpl=u'равновесная цена {} на {{V}} ден. ед.'.format(p_verb),
                  nom=u'изменение равновесной цены', gender='n'),
            Asked('dq_abs', unit=u'шт.',
                  question=u'На сколько штук {} равновесный объём продаж?'.format(q_verb),
                  claim_tpl=u'равновесный объём продаж {} на {{V}} шт.'.format(q_verb),
                  nom=u'изменение равновесного объёма', gender='n'),
        ]

    def error_variants(self, params, solved, asked):
        b, d = F(params['b']), F(params['d'])
        delta = abs(F(params['delta']))
        p0, q0 = solved['p0'], solved['q0']
        p1, q1 = solved['p_new'], solved['q_new']
        if asked.key == 'p_new':
            return [p0,                    # сдвиг проигнорирован
                    2 * p0 - p1,           # сдвиг не в ту сторону
                    p0 + delta,            # весь Δ приписан цене
                    q1]                    # перепутаны P и Q
        if asked.key == 'q_new':
            return [q0,                    # сдвиг проигнорирован
                    2 * q0 - q1,           # сдвиг не в ту сторону
                    q0 + delta,            # весь Δ приписан объёму
                    q0 - delta,
                    p1]                    # перепутаны P и Q
        if asked.key == 'dp_abs':
            return [delta,                 # цена сдвинулась на весь Δ
                    solved['dq_abs'],      # перепутаны ΔP и ΔQ
                    delta / b,
                    delta / d,
                    2 * solved['dp_abs']]
        return [delta,                     # объём изменился на весь Δ
                solved['dp_abs'],          # перепутаны ΔP и ΔQ
                delta / 2,
                solved['dq_abs'] * 2,
                solved['dp_abs'] * b]

    def _shift_sentence(self, params, short=False):
        reason = REASONS[(params['side'],
                          1 if params['delta'] > 0 else -1)][params['reason']]
        curve = u'спрос' if params['side'] == 'demand' else u'предложение'
        verb = u'вырос' if params['delta'] > 0 else u'сократился'
        if params['side'] == 'supply':
            verb = u'выросло' if params['delta'] > 0 else u'сократилось'
        return u'{} {} при каждой цене {} на {} шт.'.format(
            reason, curve, verb, abs(params['delta']))

    def wrappers(self):
        def full(setup):
            return lambda p, s: setup(p) + ' ' + self._shift_sentence(p)

        def short(setup):
            return lambda p, s: setup(p) + ' ' + self._shift_sentence(p, True)

        return [
            Wrapper('city', full(_market.setup_full),
                    short(_market.setup_short)),
            Wrapper('country', full(_market.setup_full_country),
                    short(_market.setup_short_bare)),
        ]

    def solution(self, params, solved, asked):
        side_demand = params['side'] == 'demand'
        new_a = params['a'] + (params['delta'] if side_demand else 0)
        new_c = params['c'] + (0 if side_demand else params['delta'])
        new_eq = linear_eq('Q_d', new_a, -F(params['b'])) if side_demand \
            else linear_eq('Q_s', new_c, F(params['d']))
        steps = [
            u'Исходное равновесие: $P_0^* = {}$ ден. ед., $Q_0^* = {}$ шт.'.format(
                fmt_num(solved['p0'], latex=True), fmt_num(solved['q0'], latex=True)),
            u'Новая кривая {}: {}.'.format(
                u'спроса' if side_demand else u'предложения', new_eq),
            u'Новое равновесие: $P_1^* = {}$ ден. ед., $Q_1^* = {}$ шт.'.format(
                fmt_num(solved['p_new'], latex=True),
                fmt_num(solved['q_new'], latex=True)),
        ]
        if asked.key == 'dp_abs':
            steps.append(u'Изменение цены: $|{} - {}| = {}$ ден. ед.'.format(
                fmt_num(solved['p_new'], latex=True),
                fmt_num(solved['p0'], latex=True),
                fmt_num(solved['dp_abs'], latex=True)))
        elif asked.key == 'dq_abs':
            steps.append(u'Изменение объёма: $|{} - {}| = {}$ шт.'.format(
                fmt_num(solved['q_new'], latex=True),
                fmt_num(solved['q0'], latex=True),
                fmt_num(solved['dq_abs'], latex=True)))
        return steps


ARCHETYPE = ShiftEquilibriumArchetype()
