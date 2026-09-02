u"""Сюжет 5 — «Потолок цены» (сложность 4).

Контрольный пример: спрос P = 100 − Q, предложение P = 20 + Q, потолок 40.
Равновесие Q* = 40, P* = 60. Объём спроса при потолке 60, объём предложения 20.
ПРОДАНО 20 — торгуется КОРОТКАЯ СТОРОНА рынка. Дефицит 40.
Потери общества = ½ · (80 − 40) · (40 − 20) = 400.

Ключевая ловушка темы — именно короткая сторона: при потолке продаётся не
столько, сколько хотят купить, а столько, сколько согласны продать.

Треугольник потерь строится ОБЩИМ правилом: при объёме q ≠ Q* он заключён
между спросом сверху и предложением снизу на отрезке от q до Q*. Правило
одно и то же и для верного объёма, и для ошибочного — поэтому при подмене
объёма треугольник честно уезжает на другую сторону от равновесия, а не
вырождается в отрезок.
"""
from fractions import Fraction

from game.generators._figure import (area, axis_max, callout, clip_linear,
                                     figure, line, mark, point)
from .._fmt import fmt, linear
from ..base import (MAX_SAMPLE_ATTEMPTS, Injector, SampleError, Scenario,
                    verdict)

# Потолок вводят там, где товар считают жизненно необходимым, — вид
# вмешательства обязан идти ИЗ сюжета.
STORIES = [
    {'key': 'bread',
     'lead': u'Регион заморозил цену на социальный хлеб, чтобы он остался '
             u'доступным.',
     'good': u'социальный хлеб', 'qunit': u'тыс. буханок в день',
     'punit': u'руб. за буханку', 'cap': u'предельная цена'},
    {'key': 'rent',
     'lead': u'Город ограничил арендную плату за студии в старом фонде.',
     'good': u'аренду студий', 'qunit': u'тыс. квартир',
     'punit': u'тыс. руб. в месяц', 'cap': u'потолок арендной платы'},
    {'key': 'meds',
     'lead': u'Государство установило предельную цену на жизненно необходимое '
             u'лекарство.',
     'good': u'лекарство', 'qunit': u'тыс. упаковок в месяц',
     'punit': u'руб. за упаковку', 'cap': u'предельная отпускная цена'},
    {'key': 'tickets',
     'lead': u'Перед праздником власти ограничили цену билетов на пригородные '
             u'электрички.',
     'good': u'билеты', 'qunit': u'тыс. билетов в день',
     'punit': u'руб. за билет', 'cap': u'предельная цена билета'},
    {'key': 'water',
     'lead': u'Тариф на питьевую воду в посёлке ограничен решением района.',
     'good': u'питьевую воду', 'qunit': u'тыс. кубометров в месяц',
     'punit': u'руб. за кубометр', 'cap': u'предельный тариф'},
    {'key': 'fuel_cap',
     'lead': u'В отдалённом районе введена предельная цена на дизельное '
             u'топливо для сельхозработ.',
     'good': u'дизельное топливо', 'qunit': u'тыс. литров в неделю',
     'punit': u'руб. за литр', 'cap': u'предельная цена'},
]

SLOPES = [Fraction(1, 2), Fraction(1), Fraction(2), Fraction(3)]
QSTARS = [20, 24, 30, 36, 40, 50, 60]
PSTARS = [40, 50, 60, 70, 80, 90]
GAPS = [4, 6, 8, 10, 12, 15, 20]        # на сколько потолок сжал предложение


class PriceCeiling(Scenario):
    key = 'ceiling_dwl'
    title = u'Потолок цены'
    # Сложность 4: нужно понять, что торгуется короткая сторона, и только
    # потом строить треугольник — да ещё и от неё, а не от равновесия.
    difficulty = 4
    topics = (u'Вмешательство государства',)

    def sample(self, rng):
        for _ in range(MAX_SAMPLE_ATTEMPTS):
            story = STORIES[rng.randrange(len(STORIES))]
            b = SLOPES[rng.randrange(len(SLOPES))]     # |наклон| спроса
            d = SLOPES[rng.randrange(len(SLOPES))]     # наклон предложения
            gap = GAPS[rng.randrange(len(GAPS))]       # Q* − объём предложения
            q = QSTARS[rng.randrange(len(QSTARS))]
            if gap >= q:
                continue
            p = PSTARS[rng.randrange(len(PSTARS))]
            a = p + b * q
            c = p - d * q
            cap = p - d * gap                          # потолок
            if c < 0 or cap <= 0 or cap <= c:
                continue      # ниже точки выхода предложения продавать некому
            # ⚠️ Требование к КАРТИНКЕ (см. тот же комментарий у налога):
            # потолок обязан заметно кусать, а предложение — начинаться
            # низко, иначе треугольник потерь вырождается в волосок.
            if (p - cap) * 4 < p or c * 3 > p * 2:
                continue
            q_sold = q - gap                           # короткая сторона
            q_demanded = q + (d * gap) / b             # длинная сторона
            if q_demanded.denominator != 1:
                continue
            # рамка строится по длинной стороне: не даём ей уехать втрое
            if q_demanded > Fraction(5, 2) * q:
                continue
            dwl = (b + d) * gap * gap / 2
            p_demand = p + b * gap                     # цена спроса при q_sold
            if (a.denominator != 1 or c.denominator != 1
                    or cap.denominator != 1 or dwl.denominator != 1
                    or p_demand.denominator != 1):
                continue
            return {'story': story['key'], 'b': b, 'd': d, 'gap': gap,
                    'q': q, 'p': p, 'a': int(a), 'c': int(c),
                    'cap': int(cap), 'q_sold': int(q_sold),
                    'q_demanded': int(q_demanded)}
        raise SampleError(u'ceiling_dwl: не собрался красивый набор')

    def story(self, params):
        for s in STORIES:
            if s['key'] == params['story']:
                return s
        return STORIES[0]

    # ---------------- три шага ----------------
    def _p_demand(self, params, q):
        return Fraction(params['a']) - params['b'] * q

    def _p_supply(self, params, q):
        return Fraction(params['c']) + params['d'] * q

    def points(self, params):
        u"""Шаг 1: сколько на самом деле продано и что происходит при этом объёме.

        'V' лежит на спросе, 'W' — на предложении; при верном объёме W как раз
        и стоит на потолке (потому что продавцы выходят ровно до него).
        """
        q_sold = Fraction(params['q_sold'])
        return {
            'E': (Fraction(params['q']), Fraction(params['p'])),
            'V': (q_sold, self._p_demand(params, q_sold)),
            'W': (q_sold, self._p_supply(params, q_sold)),
        }

    def region(self, params, points):
        u"""Шаг 2: треугольник потерь между спросом и предложением до Q*."""
        return [points['V'], points['W'], points['E']]

    # ---------------- ошибки ----------------
    def injectors(self):
        return [
            Injector(
                'points', 'long_side',
                u'проданным отмечен объём спроса, а не объём предложения',
                self._long_side,
                hint=u'при потолке торгуется КОРОТКАЯ сторона рынка: купить '
                     u'хотят больше, но продавать по такой цене согласны '
                     u'немногие, и сделок ровно столько, сколько предложено'),
            Injector(
                'region', 'deficit_rect',
                u'заштрихован прямоугольник дефицита вместо треугольника потерь',
                self._deficit_rect,
                hint=u'дефицит это разрыв по количеству, а потери общества это '
                     u'непроведённые сделки, и они всегда треугольник между '
                     u'спросом и предложением'),
            Injector(
                'value', 'no_half',
                u'забыта половина в площади треугольника', self._forgot_half,
                hint=u'потери общества это ПОЛОВИНА произведения разрыва цен на '
                     u'изменение объёма'),
        ]

    def _long_side(self, params, points, rng):
        q = Fraction(params['q_demanded'])
        out = dict(points)
        out['V'] = (q, self._p_demand(params, q))
        out['W'] = (q, self._p_supply(params, q))
        return out

    def _deficit_rect(self, params, points, region, rng):
        lo = Fraction(params['q_sold'])
        hi = Fraction(params['q_demanded'])
        cap = Fraction(params['cap'])
        return [(lo, Fraction(0)), (hi, Fraction(0)), (hi, cap), (lo, cap)]

    def _forgot_half(self, params, points, region, value, rng):
        return value * 2

    # ---------------- чертёж ----------------
    def frame(self, params):
        u"""Рамка ТОЛЬКО из params — и по ЦЕНАМ, а не по свободному члену.

        Та же беда, что у налога: `axis_max(a)` тянул верх оси к цене
        спроса при нулевом объёме, и треугольник потерь превращался в
        волосок. Верх берём по самой высокой ЗНАЧИМОЙ цене — цене спроса
        при проданном объёме и цене предложения при объёме спроса (вторая
        нужна инжектору «продано по стороне спроса»). Кривые выше рамки
        обрежет clip_linear.
        """
        p_demand = Fraction(params['p']) + params['b'] * params['gap']
        p_supply_long = (Fraction(params['c'])
                         + params['d'] * params['q_demanded'])
        return (axis_max(params['q_demanded']),
                axis_max(max(p_demand, p_supply_long)))

    def draw(self, params, solution):
        xmax, ymax = self.frame(params)
        st = self.story(params)
        lines = []
        seg = clip_linear(-params['b'], params['a'], xmax, ymax)
        if seg:
            lines.append(line('d', 'D', seg[0], seg[1]))
        seg = clip_linear(params['d'], params['c'], xmax, ymax)
        if seg:
            lines.append(line('s', 'S', seg[0], seg[1]))
        lines.append(line('reg', st['cap'], (0, params['cap']),
                          (xmax, params['cap'])))

        # ⚠️ «продано» берётся ИЗ РЕШЕНИЯ (его и проверяет игрок), а Q* и
        # потолок — из params: это условие задачи, оно неоспоримо.
        q_sold = solution.points['V'][0]
        marks = [mark('y', params['cap'], u'потолок'),
                 mark('x', q_sold, u'продано'),
                 mark('x', params['q'], 'Q^*')]
        return figure(
            'ceiling', xmax, ymax,
            u'Q, %s' % st['qunit'], u'P, %s' % st['punit'],
            lines=lines,
            areas=[area('dwl', solution.region, outline=True)],
            points=[point(solution.points['V'][0], solution.points['V'][1],
                          'A', 'd', coords=True),
                    point(solution.points['W'][0], solution.points['W'][1],
                          'B', 's', coords=True),
                    point(params['q'], params['p'], 'E', 'mr', coords=True)],
            marks=marks,
            callouts=[callout(u'потери общества = %s' % fmt(solution.value),
                              solution.region, role='dwl')])

    # ---------------- тексты ----------------
    def statement(self, params):
        st = self.story(params)
        return (
            # ⚠️ «%s установлен на уровне» не годится: «предельная цена
            # установлен». Двоеточие снимает согласование в роде вовсе.
            u'%s Спрос на %s задан уравнением %s, а предложение %s '
            u'(Q в %s, P в %s). Введено ограничение цены: %s на уровне %s. Ученик '
            u'определил, сколько в итоге продано, и заштриховал потери '
            u'общества.' % (
                st['lead'], st['good'],
                linear(params['a'], -params['b']),
                linear(params['c'], params['d']),
                st['qunit'], st['punit'], st['cap'], fmt(params['cap'])))

    def explain(self, params, reference, injector):
        vq, vp = reference.points['V']
        head = (
            u'Как надо. Без потолка %s и %s дают Q* = %s, P* = %s. При потолке '
            u'%s купить хотят %s, а продать согласны только %s, поэтому торгуется '
            u'короткая сторона, значит продано %s. Дефицит %s. За проданный '
            u'объём покупатели готовы платить %s, а продавцы получают %s, и '
            u'потери общества дают треугольник: ½ · (%s − %s) · (%s − %s) = %s.'
            % (linear(params['a'], -params['b']),
               linear(params['c'], params['d']),
               fmt(params['q']), fmt(params['p']), fmt(params['cap']),
               fmt(params['q_demanded']), fmt(params['q_sold']),
               fmt(params['q_sold']),
               fmt(params['q_demanded'] - params['q_sold']),
               fmt(vp), fmt(params['cap']),
               fmt(vp), fmt(params['cap']),
               fmt(params['q']), fmt(params['q_sold']),
               fmt(reference.value)))
        return head + u' ' + verdict(injector)
