"""
Архетип 4 (Блок А): потолок цены ниже P* / пол выше P* — дефицит или излишек.

Обратный ход: отступ m от равновесной цены целый → разрыв (b+d)·m целый.
Контроль: Qd = 100 − P, Qs = P, потолок P = 30 → дефицит 40.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market


class PriceControlArchetype(Archetype):
    key = 'price_control'
    title = u'Потолок и пол цены'
    block = u'А. Рынок'
    topics = [u'Вмешательство государства']

    def sample(self, rng):
        for _ in range(120):
            p = _market.sample_market(
                rng, p_grid=list(range(30, 101, 5)),
                q_grid=list(range(40, 201, 10)))
            p['kind'] = rng.choice(['ceiling', 'floor'])
            m = rng.choice([5, 10, 15, 20, 25])
            p0, q0 = _market.solve_market(p)
            if p['kind'] == 'ceiling':
                p['limit'] = int(p0) - m
            else:
                p['limit'] = int(p0) + m
            if p['limit'] <= 0:
                continue
            s = self.solve(p)
            # обе стороны рынка живы при регулируемой цене
            if s['q_d'] > 0 and s['q_s'] > 0:
                return p
        raise RuntimeError('price_control: не сэмплировался валидный рынок')

    def solve(self, params):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        limit = F(params['limit'])
        p0, q0 = _market.solve_market(params)
        q_d = a - b * limit
        q_s = c + d * limit
        return {
            'p0': p0, 'q0': q0, 'q_d': q_d, 'q_s': q_s,
            'gap': abs(q_d - q_s),           # дефицит (потолок) или излишек (пол)
            'q_sold': min(q_d, q_s),         # реально продаётся короткая сторона
        }

    def asked_values(self, params):
        ceiling = params['kind'] == 'ceiling'
        gap_word = u'дефицита' if ceiling else u'излишка предложения'
        return [
            Asked('gap', nom=u'величина возникшего ' + gap_word,
                  acc=u'величину возникшего ' + gap_word,
                  gender='f', unit=u'шт.'),
            Asked('q_sold', nom=u'объём продаж при регулируемой цене',
                  acc=u'объём продаж при регулируемой цене',
                  gender='m', unit=u'шт.'),
        ]

    def error_variants(self, params, solved, asked):
        b, d = F(params['b']), F(params['d'])
        m = abs(F(params['limit']) - solved['p0'])
        q_d, q_s, q0 = solved['q_d'], solved['q_s'], solved['q0']
        if asked.key == 'gap':
            return [q_d,            # взяли только спрос
                    q_s,            # взяли только предложение
                    b * m,          # учли лишь наклон спроса
                    d * m,          # учли лишь наклон предложения
                    q0]
        return [q_d if solved['q_sold'] == q_s else q_s,  # длинная сторона рынка
                q0,                 # проигнорировали регулирование
                solved['gap'],
                (q_d + q_s) / 2]

    def _control_sentence(self, params):
        if params['kind'] == 'ceiling':
            return (u'Власти установили потолок цены — не выше {} ден. ед. '
                    u'за единицу.').format(params['limit'])
        return (u'Власти установили минимальную цену (ценовой пол) {} ден. ед. '
                u'за единицу.').format(params['limit'])

    def wrappers(self):
        def with_control(setup):
            return lambda p, s: setup(p) + ' ' + self._control_sentence(p)

        return [
            Wrapper('city', with_control(_market.setup_full),
                    with_control(_market.setup_short)),
            Wrapper('country', with_control(_market.setup_full_country),
                    with_control(_market.setup_short_bare)),
        ]

    def solution(self, params, solved, asked):
        ceiling = params['kind'] == 'ceiling'
        limit = fmt_num(params['limit'], latex=True)
        steps = [
            (u'Равновесная цена ${}$ ден. ед. — ограничение {} её, '
             u'поэтому оно связывает рынок.').format(
                fmt_num(solved['p0'], latex=True),
                u'ниже' if ceiling else u'выше'),
            u'При цене ${}$: $Q_d = {}$ шт., $Q_s = {}$ шт.'.format(
                limit, fmt_num(solved['q_d'], latex=True),
                fmt_num(solved['q_s'], latex=True)),
        ]
        if asked.key == 'gap':
            word = u'Дефицит' if ceiling else u'Излишек'
            hi = solved['q_d'] if ceiling else solved['q_s']
            lo = solved['q_s'] if ceiling else solved['q_d']
            steps.append(u'{}: ${} - {} = {}$ шт.'.format(
                word, fmt_num(hi, latex=True), fmt_num(lo, latex=True),
                fmt_num(solved['gap'], latex=True)))
        else:
            steps.append(
                u'Продаётся короткая сторона рынка: $\\min(Q_d, Q_s) = {}$ шт.'.format(
                    fmt_num(solved['q_sold'], latex=True)))
        return steps


ARCHETYPE = PriceControlArchetype()
