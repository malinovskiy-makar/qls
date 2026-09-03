u"""Сюжет 1 — «Излишек потребителя» (сложность 2).

Контрольный пример: спрос P = 100 − Q, предложение P = 40 + 2Q.
Равновесие Q* = 20, P* = 80. CS = ½ · (100 − 80) · 20 = 200,
PS = ½ · (80 − 40) · 20 = 400.

⚠️ ОБЯЗАТЕЛЬНОЕ ограничение сэмплирования: наклоны спроса и предложения
ДОЛЖНЫ различаться. При равных наклонах CS = PS, и ошибка «заштриховали
излишек продавца вместо излишка покупателя» становится численно
НЕОТЛИЧИМОЙ от верного ответа — вопрос остаётся без решения. Закрыто
тестом.
"""
from fractions import Fraction

from game.generators._figure import (area, axis_max, callout, clip_linear,
                                     figure, line, mark, point)
from .._fmt import fmt, linear
from ..base import (MAX_SAMPLE_ATTEMPTS, Injector, SampleError, Scenario,
                    verdict)

# Библиотека сюжетов: у каждого свой рынок, товар и единицы. Единицы берутся
# ИЗ сюжета, а не подставляются потом — иначе кофе начинают мерить в поездках.
STORIES = [
    {'key': 'coffee',
     'lead': u'Кофейня у вокзала продаёт зерновой кофе на развес.',
     'good': u'зерновой кофе', 'qunit': u'кг в день', 'punit': u'руб. за кг',
     'buyer': u'покупателей кофе'},
    {'key': 'ferry',
     'lead': u'Паромная переправа через залив возит пассажиров летом.',
     'good': u'поездки на пароме', 'qunit': u'поездок в день',
     'punit': u'руб. за поездку', 'buyer': u'пассажиров'},
    {'key': 'tutor',
     'lead': u'Городской центр подготовки продаёт занятия с репетитором.',
     'good': u'занятия', 'qunit': u'занятий в неделю',
     'punit': u'руб. за занятие', 'buyer': u'учеников'},
    {'key': 'firewood',
     'lead': u'Дачный посёлок закупает колотые дрова на зиму.',
     'good': u'дрова', 'qunit': u'кубометров в месяц',
     'punit': u'руб. за кубометр', 'buyer': u'дачников'},
    {'key': 'bike',
     'lead': u'Городской прокат выдаёт велосипеды на час.',
     'good': u'прокат велосипеда', 'qunit': u'часов проката в день',
     'punit': u'руб. за час', 'buyer': u'горожан'},
    {'key': 'honey',
     'lead': u'Ярмарка выходного дня торгует мёдом с местной пасеки.',
     'good': u'мёд', 'qunit': u'банок за выходные', 'punit': u'руб. за банку',
     'buyer': u'покупателей мёда'},
]

SLOPES = [Fraction(1, 2), Fraction(1), Fraction(2), Fraction(3)]
QSTARS = [10, 12, 16, 20, 24, 30, 40]
PSTARS = [40, 50, 60, 70, 80, 90]


class ConsumerSurplus(Scenario):
    key = 'cs_triangle'
    title = u'Излишек потребителя'
    # Сложность 2: одна пара прямых, одно равновесие, один треугольник.
    difficulty = 2
    topics = (u'Спрос и предложение',)

    # ---------------- параметры ----------------
    def sample(self, rng):
        for _ in range(MAX_SAMPLE_ATTEMPTS):
            story = STORIES[rng.randrange(len(STORIES))]
            q = QSTARS[rng.randrange(len(QSTARS))]        # чётный объём
            b = SLOPES[rng.randrange(len(SLOPES))]        # наклон спроса
            d = SLOPES[rng.randrange(len(SLOPES))]        # наклон предложения
            if b == d:
                continue          # ⚠️ равные наклоны ⇒ CS = PS, см. шапку
            if (b * q).denominator != 1 or (d * q).denominator != 1:
                continue
            p = PSTARS[rng.randrange(len(PSTARS))]
            a = p + b * q                                  # спрос при Q = 0
            c = p - d * q                                  # предложение при Q = 0
            if c < 0 or a % 2 != 0:
                continue           # чётный «потолок» спроса ⇒ все площади целые
            # Требование к картинке: предложение, стартующее у самой
            # равновесной цены, даёт почти горизонтальную кривую.
            if c * 3 > p * 2:
                continue
            q_at_zero = a / b      # где спрос упирается в ось Q
            if q_at_zero.denominator != 1:
                continue           # эта точка нужна инжектору координат
            # Рамка строится по этой точке, иначе испорченное равновесие
            # уехало бы за край. Но и растягивать ось втрое дальше
            # равновесия нельзя: всё интересное сожмётся в левую треть.
            if q_at_zero > 3 * q:
                continue
            return {'story': story['key'], 'q': q, 'p': p,
                    'a': int(a), 'b': b, 'c': int(c), 'd': d,
                    'q_axis': int(q_at_zero)}
        raise SampleError(u'cs_triangle: не собрался красивый набор')

    def story(self, params):
        for s in STORIES:
            if s['key'] == params['story']:
                return s
        return STORIES[0]

    # ---------------- три шага ----------------
    def points(self, params):
        u"""Шаг 1: равновесие."""
        return {'E': (Fraction(params['q']), Fraction(params['p']))}

    def region(self, params, points):
        u"""Шаг 2: излишек потребителя — треугольник над ценой под спросом."""
        qe, pe = points['E']
        return [(Fraction(0), Fraction(params['a'])), (Fraction(0), pe),
                (qe, pe)]

    # value — площадь области (движок, shoelace): испорченная область
    # автоматически даёт другое число.

    # ---------------- ошибки ----------------
    def injectors(self):
        return [
            Injector(
                'points', 'demand_axis',
                u'равновесие снято на пересечении спроса с осью Q',
                self._wrong_equilibrium,
                hint=u'равновесие находится там, где спрос ПЕРЕСЕКАЕТСЯ с предложением, '
                     u'а не там, где спрос упирается в ось'),
            Injector(
                'region', 'willingness',
                u'заштрихована вся площадь под спросом (готовность платить)',
                self._area_under_demand,
                hint=u'излишек потребителя равен тому, что покупатели готовы '
                     u'были заплатить, МИНУС то, что заплатили; площадь под '
                     u'спросом целиком это только первое'),
            Injector(
                'region', 'producer_side',
                u'заштрихован излишек продавца вместо излишка покупателя',
                self._mirror_producer,
                hint=u'излишек покупателя лежит НАД ценой и ПОД спросом, '
                     u'излишек продавца лежит под ценой и над предложением'),
            Injector(
                'region', 'height_from_zero',
                u'высота треугольника отложена от нуля, а не от цены',
                self._height_from_zero,
                hint=u'высота треугольника равна разнице между ценой спроса '
                     u'при Q = 0 и равновесной ценой, а не сама цена спроса'),
            Injector(
                'value', 'no_half', u'забыта половина в площади треугольника',
                self._forgot_half,
                hint=u'площадь треугольника это ПОЛОВИНА произведения основания '
                     u'на высоту'),
        ]

    def _wrong_equilibrium(self, params, points, rng):
        return {'E': (Fraction(params['q_axis']), Fraction(0))}

    def _area_under_demand(self, params, points, region, rng):
        qe, pe = points['E']
        return [(Fraction(0), Fraction(0)), (Fraction(0), Fraction(params['a'])),
                (qe, pe), (qe, Fraction(0))]

    def _mirror_producer(self, params, points, region, rng):
        qe, pe = points['E']
        return [(Fraction(0), Fraction(params['c'])), (Fraction(0), pe), (qe, pe)]

    def _height_from_zero(self, params, points, region, rng):
        qe, _pe = points['E']
        return [(Fraction(0), Fraction(params['a'])), (Fraction(0), Fraction(0)),
                (qe, Fraction(0))]

    def _forgot_half(self, params, points, region, value, rng):
        return value * 2

    # ---------------- чертёж ----------------
    def frame(self, params):
        # ⚠️ ТОЛЬКО из params: и эталон, и испорченное решение обязаны жить
        # в одной рамке, иначе вариант отличается поехавшими осями.
        return axis_max(params['q_axis']), axis_max(params['a'])

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

        qe, pe = solution.points['E']
        marks = []
        if qe > 0:
            marks.append(mark('x', qe, 'Q^*'))
        if pe > 0:
            marks.append(mark('y', pe, 'P^*'))
        return figure(
            'cs', xmax, ymax,
            u'Q, %s' % st['qunit'], u'P, %s' % st['punit'],
            lines=lines,
            areas=[area('cs', solution.region, outline=True)],
            points=[point(qe, pe, 'E', 'd', coords=True)],
            marks=marks,
            callouts=[callout(u'CS = %s' % fmt(solution.value),
                              solution.region, role='cs')])

    # ---------------- тексты ----------------
    def statement(self, params):
        st = self.story(params)
        return (
            u'%s Спрос на %s задан уравнением %s, а предложение %s '
            u'(Q в %s, P в %s). Ученик нашёл равновесие и заштриховал '
            u'излишек %s.' % (
                st['lead'], st['good'],
                linear(params['a'], -params['b']),
                linear(params['c'], params['d']),
                st['qunit'], st['punit'], st['buyer']))

    def explain(self, params, reference, injector):
        qe, pe = reference.points['E']
        head = (
            u'Как надо. Приравниваем спрос и предложение: %s и %s дают '
            u'Q* = %s, P* = %s. Излишек потребителя это треугольник между '
            u'линией спроса и ценой %s: ½ · (%s − %s) · %s = %s.' % (
                linear(params['a'], -params['b']),
                linear(params['c'], params['d']),
                fmt(qe), fmt(pe), fmt(pe),
                fmt(params['a']), fmt(pe), fmt(qe), fmt(reference.value)))
        return head + u' ' + verdict(injector)
