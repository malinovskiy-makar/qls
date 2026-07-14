"""
Архетип 3 (Блок А): потоварный налог t или субсидия s на линейном рынке.

Обратный ход: ставка кратна (b+d) → цены покупателя/продавца сдвигаются
на целые k·d и k·b; ΔQ = k·b·d целое; чётность DWL = t·ΔQ/2 проверяется
при сэмплировании.

Контроль (Qd = 100 − P, Qs = P, t = 20): Pb = 60, Ps = 40, Q = 40,
бюджет = 800, DWL = 100, доля покупателей = 50 %.
Субсидия s = 20 на той же базе: Q = 60, расходы бюджета = 1200, DWL = 100.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_eq
from . import _market


class TaxSubsidyArchetype(Archetype):
    key = 'tax_subsidy'
    title = u'Потоварный налог и субсидия'
    block = u'А. Рынок'
    topics = [u'Вмешательство государства']

    def sample(self, rng):
        for _ in range(120):
            p = _market.sample_market(
                rng, p_grid=list(range(40, 101, 5)),
                q_grid=list(range(60, 241, 10)))
            kind = rng.choice(['tax', 'subsidy'])
            k = rng.choice([2, 3, 4, 5, 6, 8, 10])
            rate = k * (p['b'] + p['d'])
            p['kind'] = kind
            p['rate'] = rate
            b, d, q0 = p['b'], p['d'], None
            s = self.solve(dict(p))
            # валидность: рынок не убит, цены положительны, DWL целое
            if s['q1'] <= 0 or s['pb'] <= 0 or s['ps'] <= 0:
                continue
            if Fraction(s['dwl']).denominator != 1:
                continue
            return p
        raise RuntimeError('tax_subsidy: не сэмплировался валидный рынок')

    def solve(self, params):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        rate = F(params['rate'])
        p0, q0 = _market.solve_market(params)
        if params['kind'] == 'tax':
            pb = p0 + rate * d / (b + d)   # цена покупателей растёт
            ps = pb - rate
        else:
            pb = p0 - rate * d / (b + d)   # субсидия: покупатели платят меньше
            ps = pb + rate
        q1 = a - b * pb
        dq = abs(q0 - q1)
        return {
            'p0': p0, 'q0': q0, 'pb': pb, 'ps': ps, 'q1': q1, 'dq': dq,
            'budget': rate * q1,           # сборы (налог) или расходы (субсидия)
            'dwl': rate * dq / 2,
            'share_buyers': 100 * d / (b + d),
        }

    def asked_values(self, params):
        tax = params['kind'] == 'tax'
        word = u'налога' if tax else u'субсидии'
        asked = [
            Asked('pb', nom=u'цена покупателей после введения ' + word,
                  acc=u'цену покупателей после введения ' + word,
                  gender='f', unit=u'ден. ед.'),
            Asked('ps', nom=u'цена, остающаяся продавцам после введения ' + word,
                  acc=u'цену, остающуюся продавцам после введения ' + word,
                  gender='f', unit=u'ден. ед.'),
            Asked('q1', nom=u'новый равновесный объём продаж',
                  acc=u'новый равновесный объём продаж', gender='m', unit=u'шт.'),
            Asked('budget',
                  nom=(u'сумма налоговых поступлений в бюджет' if tax
                       else u'сумма расходов бюджета на субсидию'),
                  acc=(u'сумму налоговых поступлений в бюджет' if tax
                       else u'сумму расходов бюджета на субсидию'),
                  gender='f', unit=u'ден. ед.'),
            Asked('dwl', nom=u'величина чистых потерь общества',
                  acc=u'величину чистых потерь общества', gender='f',
                  unit=u'ден. ед.'),
        ]
        if tax:
            asked.append(Asked(
                'share_buyers', unit='%', max_value=100,
                question=u'Какая доля налогового бремени ложится на покупателей (в %)?',
                claim_tpl=u'на покупателей ложится {V} % налогового бремени',
                nom=u'доля налогового бремени покупателей', gender='f'))
        return asked

    def error_variants(self, params, solved, asked):
        b, d = F(params['b']), F(params['d'])
        rate = F(params['rate'])
        tax = params['kind'] == 'tax'
        p0, q0, pb, ps = solved['p0'], solved['q0'], solved['pb'], solved['ps']
        q1, dq = solved['q1'], solved['dq']
        if asked.key == 'pb':
            full = p0 + rate if tax else p0 - rate     # вся ставка на покупателях
            wrong_side = p0 + (p0 - ps) if tax else p0 - (ps - p0)
            return [full, p0, ps, wrong_side, q1]
        if asked.key == 'ps':
            full = p0 - rate if tax else p0 + rate
            wrong_side = 2 * p0 - ps
            return [full, p0, pb, wrong_side, q1]
        if asked.key == 'q1':
            return [q0, q0 - rate if tax else q0 + rate,   # ставка вычтена из Q
                    2 * q0 - q1,                            # сдвиг не в ту сторону
                    dq, pb]
        if asked.key == 'budget':
            return [rate * q0,          # умножили на старый объём
                    solved['dwl'],
                    rate * dq,
                    rate * (q0 + q1) / 2]
        if asked.key == 'dwl':
            return [rate * dq,          # забыли 1/2
                    solved['budget'],
                    rate * q1 / 2,
                    rate * q0 / 2,
                    dq]
        # share_buyers
        return [100 * b / (b + d),      # доля продавцов
                50,
                100 * d / b if b != 0 else 0,
                100 - 100 * b / (b + d)]

    def _policy_sentence(self, params):
        if params['kind'] == 'tax':
            return (u'Государство ввело потоварный налог {} ден. ед. '
                    u'с каждой проданной единицы, уплачиваемый '
                    u'продавцами.').format(params['rate'])
        return (u'Государство ввело потоварную субсидию {} ден. ед. '
                u'за каждую проданную единицу, выплачиваемую '
                u'продавцам.').format(params['rate'])

    def wrappers(self):
        def full(setup):
            return lambda p, s: setup(p) + ' ' + self._policy_sentence(p)

        def short(setup):
            short_pol = (lambda p: (u'Введён потоварный налог {} ден. ед. '
                                    u'с продавцов.'.format(p['rate'])
                                    if p['kind'] == 'tax' else
                                    u'Введена потоварная субсидия {} ден. ед. '
                                    u'продавцам.'.format(p['rate'])))
            return lambda p, s: setup(p) + ' ' + short_pol(p)

        return [
            Wrapper('city', full(_market.setup_full),
                    short(_market.setup_short)),
            Wrapper('analysts', full(_market.setup_full_analysts),
                    short(_market.setup_short_bare)),
        ]

    def solution(self, params, solved, asked):
        tax = params['kind'] == 'tax'
        rate = fmt_num(params['rate'], latex=True)
        sign = '-' if tax else '+'
        steps = [
            u'Исходное равновесие: $P_0^* = {}$ ден. ед., $Q_0^* = {}$ шт.'.format(
                fmt_num(solved['p0'], latex=True),
                fmt_num(solved['q0'], latex=True)),
            (u'{} {} ден. ед. вбивает клин между ценой покупателей $P_b$ и '
             u'ценой продавцов $P_s = P_b {} {}$; предложение теперь зависит '
             u'от $P_s$.').format(
                 u'Налог' if tax else u'Субсидия', rate,
                 '-' if tax else '+', rate),
            (u'Решая систему, получаем $P_b = {}$, $P_s = {}$ ден. ед., '
             u'$Q_1 = {}$ шт.').format(
                 fmt_num(solved['pb'], latex=True),
                 fmt_num(solved['ps'], latex=True),
                 fmt_num(solved['q1'], latex=True)),
        ]
        if asked.key == 'budget':
            verb = u'Сборы бюджета' if tax else u'Расходы бюджета'
            steps.append(u'{}: ${} \\cdot {} = {}$ ден. ед.'.format(
                verb, rate, fmt_num(solved['q1'], latex=True),
                fmt_num(solved['budget'], latex=True)))
        elif asked.key == 'dwl':
            steps.append(
                u'Чистые потери: $DWL = \\frac{{1}}{{2}} \\cdot {} \\cdot {} '
                u'= {}$ ден. ед.'.format(
                    rate, fmt_num(solved['dq'], latex=True),
                    fmt_num(solved['dwl'], latex=True)))
        elif asked.key == 'share_buyers':
            steps.append(
                u'Бремя делится пропорционально наклонам: доля покупателей '
                u'$= \\frac{{d}}{{b + d}} = {}\\,\\%$.'.format(
                    fmt_num(solved['share_buyers'], latex=True)))
        return steps


ARCHETYPE = TaxSubsidyArchetype()
