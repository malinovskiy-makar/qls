u"""Сюжет 4 — «Налог: бремя и потери общества» (сложность 3).

Контрольный пример: спрос P = 120 − 2Q, предложение P = 30 + Q, налог t = 30.
Без налога: Q₀ = 30, P₀ = 60.
С налогом: Q₁ = 20, цена покупателя 80, цена продавца 50, разница 30 ✓.
Бремя покупателя 20, продавца 10 — РАЗЛИЧАЮТСЯ, это принципиально.
Потери общества = ½ · 30 · 10 = 150.

⚠️ ОБЯЗАТЕЛЬНОЕ ограничение сэмплирования: наклоны спроса и предложения
различаются. При равных наклонах бремя делится пополам, и ошибка «бремя
разделено наоборот» становится численно НЕОТЛИЧИМОЙ от верного ответа.
Закрыто тестом.

Бремя делится обратно пропорционально наклонам: чем круче кривая, тем
больше бремени на её стороне. Здесь бремя покупателя = b·ΔQ, продавца =
d·ΔQ, где b и d — модули наклонов спроса и предложения.
"""
from fractions import Fraction

from game.generators._figure import (area, axis_max, callout, clip_linear,
                                     figure, line, mark, point)
from .._fmt import fmt, linear
from ..base import (MAX_SAMPLE_ATTEMPTS, Injector, SampleError, Scenario,
                    verdict)

# Вид вмешательства берётся ИЗ сюжета: акциз на сладкую газировку осмыслен,
# «налог ради борьбы с ожирением» на дрова — нет.
STORIES = [
    {'key': 'soda',
     'lead': u'Город ввёл акциз на сладкую газировку, чтобы сократить '
             u'потребление сахара.',
     'good': u'газировку', 'qunit': u'тыс. бутылок в месяц',
     'punit': u'руб. за бутылку', 'tax': u'акциз'},
    {'key': 'tobacco',
     'lead': u'Государство подняло акциз на табак ради здоровья населения.',
     'good': u'сигареты', 'qunit': u'тыс. пачек в месяц',
     'punit': u'руб. за пачку', 'tax': u'акциз'},
    {'key': 'parking',
     'lead': u'Мэрия обложила сбором платные парковки в центре, чтобы '
             u'разгрузить улицы.',
     'good': u'парковочные места', 'qunit': u'тыс. мест в день',
     'punit': u'руб. за место', 'tax': u'сбор'},
    {'key': 'plastic',
     'lead': u'Регион ввёл экологический сбор на одноразовую пластиковую '
             u'посуду.',
     'good': u'пластиковую посуду', 'qunit': u'тыс. наборов в месяц',
     'punit': u'руб. за набор', 'tax': u'экологический сбор'},
    {'key': 'fuel',
     'lead': u'Страна повысила топливный акциз, чтобы наполнить дорожный фонд.',
     'good': u'бензин', 'qunit': u'тыс. литров в день',
     'punit': u'руб. за литр', 'tax': u'акциз'},
    {'key': 'timber',
     'lead': u'Введена вывозная пошлина на необработанную древесину.',
     'good': u'древесину', 'qunit': u'тыс. кубометров в месяц',
     'punit': u'руб. за кубометр', 'tax': u'пошлина'},
]

SLOPES = [Fraction(1, 2), Fraction(1), Fraction(2), Fraction(3)]
DROPS = [4, 6, 8, 10, 12, 15, 20]        # ΔQ — насколько налог сжал рынок
Q0S = [20, 24, 30, 36, 40, 50, 60]
P0S = [40, 50, 60, 70, 80, 90]


class TaxBurden(Scenario):
    key = 'tax_dwl'
    title = u'Налог: бремя и потери общества'
    # Сложность 3: два равновесия, две цены, треугольник между ними.
    difficulty = 3
    topics = (u'Вмешательство государства',)

    def sample(self, rng):
        for _ in range(MAX_SAMPLE_ATTEMPTS):
            story = STORIES[rng.randrange(len(STORIES))]
            b = SLOPES[rng.randrange(len(SLOPES))]     # |наклон| спроса
            d = SLOPES[rng.randrange(len(SLOPES))]     # наклон предложения
            if b == d:
                continue        # ⚠️ равные наклоны ⇒ бремя пополам, см. шапку
            dq = DROPS[rng.randrange(len(DROPS))]
            burden_b, burden_s = b * dq, d * dq
            if burden_b.denominator != 1 or burden_s.denominator != 1:
                continue
            q0 = Q0S[rng.randrange(len(Q0S))]
            if dq >= q0:
                continue                     # налог не может убить весь рынок
            p0 = P0S[rng.randrange(len(P0S))]
            a = p0 + b * q0                  # спрос при Q = 0
            c = p0 - d * q0                  # предложение при Q = 0
            if c < 0 or a.denominator != 1 or c.denominator != 1:
                continue
            t = burden_b + burden_s          # ставка налога
            dwl = t * dq / 2
            if dwl.denominator != 1:
                continue
            if p0 - burden_s <= 0:
                continue                     # цена продавца обязана быть > 0
            # ⚠️ Требования к КАРТИНКЕ, а не к математике. Ставка 9 руб. при
            # цене 90 математически корректна, но на чертеже треугольник
            # потерь превращается в волосок, а кривые — в две почти
            # горизонтальные черты: проверять глазом нечего. Поэтому ставка
            # обязана быть заметной долей цены, а предложение — начинаться
            # достаточно низко, чтобы кривая реально шла вверх.
            if t * 4 < p0 or c * 3 > p0 * 2:
                continue
            return {'story': story['key'], 'b': b, 'd': d, 'dq': dq,
                    'q0': q0, 'p0': p0, 'a': int(a), 'c': int(c),
                    't': int(t), 'q1': q0 - dq,
                    'pb': int(p0 + burden_b), 'ps': int(p0 - burden_s)}
        raise SampleError(u'tax_dwl: не собрался красивый набор')

    def story(self, params):
        for s in STORIES:
            if s['key'] == params['story']:
                return s
        return STORIES[0]

    # ---------------- три шага ----------------
    def points(self, params):
        u"""Шаг 1: старое равновесие и две новые цены при объёме Q₁."""
        return {
            'E_0': (Fraction(params['q0']), Fraction(params['p0'])),
            'B': (Fraction(params['q1']), Fraction(params['pb'])),
            'C': (Fraction(params['q1']), Fraction(params['ps'])),
        }

    def region(self, params, points):
        u"""Шаг 2: треугольник потерь между двумя ценами и старым равновесием."""
        return [points['B'], points['C'], points['E_0']]

    # value — площадь области (shoelace в движке).

    # ---------------- ошибки ----------------
    def injectors(self):
        return [
            Injector(
                'points', 'burden_swapped',
                u'бремя разделено наоборот: цена покупателя ниже цены продавца',
                self._swap_burden,
                hint=u'бремя больше на той стороне, чья кривая КРУЧЕ: она хуже '
                     u'реагирует на цену и потому не может увернуться'),
            Injector(
                'points', 'gap_not_tax',
                u'разница цен покупателя и продавца не равна ставке налога',
                self._gap_off,
                hint=u'налог это ровно вертикальный разрыв между ценой, '
                     u'которую платит покупатель, и ценой, которую получает '
                     u'продавец'),
            Injector(
                'region', 'revenue_rect',
                u'заштрихован прямоугольник сбора государства вместо '
                u'треугольника потерь',
                self._revenue_rect,
                hint=u'сбор государства никуда не пропадает, он достаётся '
                     u'бюджету; общество теряет только сделки, которые больше '
                     u'не состоялись'),
            Injector(
                'value', 'no_half',
                u'забыта половина в площади треугольника', self._forgot_half,
                hint=u'потери общества это ПОЛОВИНА произведения ставки налога '
                     u'на изменение объёма'),
        ]

    def _swap_burden(self, params, points, rng):
        out = dict(points)
        out['B'] = (Fraction(params['q1']), Fraction(params['ps']))
        out['C'] = (Fraction(params['q1']), Fraction(params['pb']))
        return out

    def _gap_off(self, params, points, rng):
        u"""Цену покупателя сдвигаем так, чтобы разрыв перестал равняться t.

        Сдвиг ЦЕЛЫЙ: цена попадает засечкой на ось, «81,333» там нечитаемо.
        """
        step = self._gap_step(params)
        out = dict(points)
        qb, pb = points['B']
        out['B'] = (qb, pb + step)
        return out

    def _revenue_rect(self, params, points, region, rng):
        qb, pb = points['B']
        _qc, pc = points['C']
        return [(Fraction(0), pc), (qb, pc), (qb, pb), (Fraction(0), pb)]

    def _forgot_half(self, params, points, region, value, rng):
        return value * 2

    # ---------------- чертёж ----------------
    @staticmethod
    def _gap_step(params):
        u"""Насколько инжектор поднимает цену покупателя (нужно и рамке)."""
        return max(2, params['t'] // 4)

    def frame(self, params):
        u"""Рамка ТОЛЬКО из params — и по ЦЕНАМ, а не по свободному члену.

        ⚠️ `axis_max(a)` тянул верх оси к цене спроса при нулевом объёме
        (160 при ценах 78–88), и весь сюжет сплющивался в узкую полосу:
        кривые почти горизонтальны, треугольник потерь — волосок, подписи
        цен налезают друг на друга. Кривые за рамку не выйдут — их обрежет
        clip_linear, для того он и есть. Видно это только глазами на
        скриншоте, ни один тест такого не заметит.
        """
        top = params['pb'] + self._gap_step(params)
        return axis_max(params['q0']), axis_max(top)

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
        # предложение с налогом — пунктиром, как «было/стало»
        seg = clip_linear(params['d'], params['c'] + params['t'], xmax, ymax)
        if seg:
            lines.append(line('tax', u'S + %s' % st['tax'], seg[0], seg[1],
                              dash=True))

        pts, marks = [], []
        role = {'E_0': 'd', 'B': 'd', 'C': 's'}
        for name, (x, y) in solution.points.items():
            pts.append(point(x, y, name, role.get(name, 'd'), coords=True))
        seen_y = set()
        for name, label in (('B', 'P_b'), ('C', 'P_s'), ('E_0', 'P_0')):
            _x, y = solution.points[name]
            if y > 0 and y not in seen_y:
                marks.append(mark('y', y, label))
                seen_y.add(y)
        seen_x = set()
        for name, label in (('B', 'Q_1'), ('E_0', 'Q_0')):
            x, _y = solution.points[name]
            if x > 0 and x not in seen_x:
                marks.append(mark('x', x, label))
                seen_x.add(x)

        return figure(
            'tax', xmax, ymax,
            u'Q, %s' % st['qunit'], u'P, %s' % st['punit'],
            lines=lines,
            areas=[area('dwl', solution.region, outline=True)],
            points=pts, marks=marks,
            callouts=[callout(u'потери общества = %s' % fmt(solution.value),
                              solution.region, role='dwl')])

    # ---------------- тексты ----------------
    def statement(self, params):
        st = self.story(params)
        return (
            u'%s Спрос на %s задан уравнением %s, а предложение %s '
            u'(Q в %s, P в %s). Ставка составила %s руб. с единицы. Ученик '
            u'нашёл новые цены и заштриховал потери общества.' % (
                st['lead'], st['good'],
                linear(params['a'], -params['b']),
                linear(params['c'], params['d']),
                st['qunit'], st['punit'], fmt(params['t'])))

    def explain(self, params, reference, injector):
        head = (
            u'Как надо. Без налога %s и %s дают Q₀ = %s, P₀ = %s. С налогом '
            u'%s руб. объём падает до Q₁ = %s: покупатель платит %s, продавец '
            u'получает %s, разница равна ставке. Бремя покупателя %s, '
            u'продавца %s, и они разные, потому что наклоны кривых разные. '
            u'Потери общества дают треугольник: ½ · %s · %s = %s.' % (
                linear(params['a'], -params['b']),
                linear(params['c'], params['d']),
                fmt(params['q0']), fmt(params['p0']), fmt(params['t']),
                fmt(params['q1']), fmt(params['pb']), fmt(params['ps']),
                fmt(params['pb'] - params['p0']),
                fmt(params['p0'] - params['ps']),
                fmt(params['t']), fmt(params['dq']), fmt(reference.value)))
        return head + u' ' + verdict(injector)
