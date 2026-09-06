u"""Сюжет 7 — «Монополия: объём, цена, прибыль» (сложность 3).

Контрольный пример: спрос P = 100 − Q, MC = 20 (постоянные), FC = 400.
MR = 100 − 2Q, MR = MC ⇒ Q* = 40, P* = 60 (цена берётся С КРИВОЙ СПРОСА).
ATC(40) = 20 + 400/40 = 30. Прибыль = (60 − 30) · 40 = 1200.

⚠️ Постоянные издержки ОБЯЗАТЕЛЬНЫ. Без них ATC = MC, прибыль совпадает с
наценкой, и ошибка «прямоугольник отложен от MC вместо ATC» исчезает вовсе.
Это уже проходили на архетипе монополии.

⚠️ На оси P обязательны засечки P*, ATC и MC — иначе ошибку не проверить
глазом: игрок обязан видеть, на какой высоте проходит каждая из трёх линий.

ATC = MC + FC/Q — гипербола, и рисуется она ломаной по точкам (единственный
честный способ: рисователь не умеет и не должен уметь формулы).
"""
from fractions import Fraction

from game.generators._figure import (area, axis_max, broken_line, callout,
                                     clip_linear, figure, line, mark, point)
from .._fmt import fmt, linear
from ..base import (MAX_SAMPLE_ATTEMPTS, Injector, SampleError, Scenario,
                    verdict)

STORIES = [
    {'key': 'water',
     'lead': u'Единственный в городе водоканал «Аквалайн» продаёт питьевую '
             u'воду: сети чужим не сдают, конкурентов нет.',
     'good': u'питьевую воду', 'qunit': u'тыс. кубометров в месяц',
     'punit': u'руб. за кубометр', 'fixed': u'содержание сетей'},
    {'key': 'railway',
     'lead': u'Единственная железнодорожная ветка к посёлку принадлежит одной '
             u'компании, и возить грузы больше нечем.',
     'good': u'перевозки', 'qunit': u'тыс. тонн в месяц',
     'punit': u'руб. за тонну', 'fixed': u'содержание путей'},
    {'key': 'patent',
     'lead': u'Фармацевтическая компания держит патент на препарат: аналогов '
             u'на рынке нет и до конца патента не будет.',
     'good': u'препарат', 'qunit': u'тыс. упаковок в месяц',
     'punit': u'руб. за упаковку', 'fixed': u'исследования и патент'},
    {'key': 'cable',
     'lead': u'В горный посёлок протянут один-единственный кабель связи, и '
             u'принадлежит он одному оператору.',
     'good': u'интернет', 'qunit': u'тыс. подключений',
     'punit': u'руб. в месяц', 'fixed': u'обслуживание кабеля'},
    {'key': 'quarry',
     'lead': u'Карьер с редкой глиной в области один, и лицензия на него '
             u'выдана единственной компании.',
     'good': u'глину', 'qunit': u'тыс. тонн в месяц',
     'punit': u'руб. за тонну', 'fixed': u'лицензия и техника'},
    {'key': 'port',
     'lead': u'Порт на реке один, и перевалку грузов делает только его '
             u'владелец.',
     'good': u'перевалку грузов', 'qunit': u'тыс. тонн в месяц',
     'punit': u'руб. за тонну', 'fixed': u'краны и причалы'},
]

SLOPES = [Fraction(1, 2), Fraction(1), Fraction(2)]
QSTARS = [20, 25, 30, 40, 50, 60]
MCS = [10, 15, 20, 25, 30, 40]
# FC = k · Q*, k чётное: тогда и ATC(Q*), и ATC(2Q*) целые (второе нужно
# инжектору «объём взят там, где спрос равен MC»).
KS = [4, 6, 8, 10, 12, 16, 20]


class MonopolyProfit(Scenario):
    key = 'monopoly_profit'
    title = u'Монополия: объём, цена, прибыль'
    # Сложность 3: MR = MC, цена со спроса, прямоугольник от ATC.
    difficulty = 3
    topics = (u'Монополия и ценовая дискриминация',)

    def sample(self, rng):
        for _ in range(MAX_SAMPLE_ATTEMPTS):
            story = STORIES[rng.randrange(len(STORIES))]
            q = QSTARS[rng.randrange(len(QSTARS))]
            b = SLOPES[rng.randrange(len(SLOPES))]
            mc = MCS[rng.randrange(len(MCS))]
            k = KS[rng.randrange(len(KS))]
            # MR = a − 2bQ = MC при Q = q ⇒ a = MC + 2b·q
            a = mc + 2 * b * q
            if a.denominator != 1:
                continue
            p = a - b * q                      # цена берётся СО СПРОСА
            if p.denominator != 1:
                continue      # ⚠️ иначе int() ниже МОЛЧА обрежет 27,5 до 27,
                              # и точка перестанет лежать на кривой спроса
            atc = mc + k                       # FC/Q* = k
            # Прибыль обязана быть не просто положительной, а ЗАМЕТНОЙ:
            # при наценке в пару рублей прямоугольник прибыли вырождается
            # в полоску, и ошибку «отложили от MC» на нём не разглядеть.
            if (p - atc) * 5 < p:
                continue
            fc = k * q
            atc_double = mc + Fraction(fc, 2 * q)   # ATC при Q = 2q
            if atc_double.denominator != 1:
                continue
            if (p - atc) * q > 100000:
                continue                       # числа не должны быть монстрами
            # ⚠️ При P* = Q* ошибка «умножили на цену вместо количества»
            # даёт ТО ЖЕ число и становится невидимой — вопрос без решения.
            # Поймано тестом-шлюзом, а не глазами.
            if p == q:
                continue
            return {'story': story['key'], 'q': q, 'b': b, 'mc': mc,
                    'a': int(a), 'p': int(p), 'fc': int(fc),
                    'atc': int(atc), 'q_dmc': int(2 * q),
                    'atc_dmc': int(atc_double)}
        raise SampleError(u'monopoly_profit: не собрался красивый набор')

    def story(self, params):
        for s in STORIES:
            if s['key'] == params['story']:
                return s
        return STORIES[0]

    def _atc(self, params, q):
        return Fraction(params['mc']) + Fraction(params['fc'], 1) / q

    def _demand(self, params, q):
        return Fraction(params['a']) - params['b'] * q

    # ---------------- три шага ----------------
    def points(self, params):
        u"""Шаг 1: выбор монополиста — объём и цена."""
        return {'M': (Fraction(params['q']), Fraction(params['p']))}

    def region(self, params, points):
        u"""Шаг 2: прямоугольник прибыли — от ATC при этом объёме до цены."""
        q, p = points['M']
        atc = self._atc(params, q)
        return [(Fraction(0), atc), (q, atc), (q, p), (Fraction(0), p)]

    # ---------------- ошибки ----------------
    def injectors(self):
        return [
            Injector(
                'points', 'price_off_mr',
                u'цена снята с кривой MR, а не с кривой спроса',
                self._price_from_mr,
                hint=u'MR = MC определяет только ОБЪЁМ; цену за этот объём '
                     u'платят покупатели, значит её берут с кривой СПРОСА'),
            Injector(
                'points', 'q_where_d_equals_mc',
                u'объём взят там, где спрос равен MC (как у конкурентной фирмы)',
                self._q_at_mc,
                hint=u'равенство цены и предельных издержек это правило '
                     u'конкурентной фирмы; монополист приравнивает к MC свой '
                     u'предельный ДОХОД, а он падает вдвое круче спроса'),
            Injector(
                'region', 'from_mc',
                u'прямоугольник прибыли отложен от MC, а не от ATC',
                self._rect_from_mc,
                hint=u'разница между ценой и MC это наценка на последнюю '
                     u'единицу; прибыль же считается от СРЕДНИХ издержек, в '
                     u'которые входят и постоянные'),
            Injector(
                'value', 'times_price',
                u'прибыль умножена на цену вместо объёма', self._times_price,
                hint=u'(P − ATC) это прибыль с ОДНОЙ единицы, поэтому '
                     u'умножать её надо на количество единиц'),
        ]

    def _price_from_mr(self, params, points, rng):
        q, _p = points['M']
        mr = Fraction(params['a']) - 2 * params['b'] * q
        return {'M': (q, mr)}

    def _q_at_mc(self, params, points, rng):
        q = Fraction(params['q_dmc'])
        return {'M': (q, self._demand(params, q))}

    def _rect_from_mc(self, params, points, region, rng):
        q, p = points['M']
        mc = Fraction(params['mc'])
        return [(Fraction(0), mc), (q, mc), (q, p), (Fraction(0), p)]

    def _times_price(self, params, points, region, value, rng):
        q, p = points['M']
        atc = self._atc(params, q)
        return abs(p - atc) * p

    # ---------------- чертёж ----------------
    def frame(self, params):
        return axis_max(params['q_dmc']), axis_max(params['a'])

    def _atc_curve(self, params, xmax, ymax):
        u"""ATC = MC + FC/Q ломаной по точкам: формул рисователь не знает."""
        pts, steps = [], 40
        for i in range(steps + 1):
            q = Fraction(xmax) * Fraction(i, steps)
            if q <= 0:
                continue
            y = self._atc(params, q)
            if y <= ymax:
                pts.append((q, y))
        return pts

    def draw(self, params, solution):
        xmax, ymax = self.frame(params)
        st = self.story(params)
        lines = []
        seg = clip_linear(-params['b'], params['a'], xmax, ymax)
        if seg:
            lines.append(line('d', 'D', seg[0], seg[1]))
        seg = clip_linear(-2 * params['b'], params['a'], xmax, ymax)
        if seg:
            lines.append(line('mr', 'MR', seg[0], seg[1]))
        lines.append(line('mc', 'MC', (0, params['mc']), (xmax, params['mc'])))

        q, p = solution.points['M']
        atc_here = self._atc(params, q)
        # ⚠️ засечки P*, ATC и MC обязательны: без них ошибку «отложили от MC»
        # глазами не поймать
        marks = [mark('x', q, 'Q^*'), mark('y', p, 'P^*'),
                 mark('y', params['mc'], 'MC')]
        if atc_here != p and atc_here != params['mc']:
            marks.append(mark('y', atc_here, 'ATC'))

        curve = self._atc_curve(params, xmax, ymax)
        return figure(
            'monopoly', xmax, ymax,
            u'Q, %s' % st['qunit'], u'P, %s' % st['punit'],
            lines=lines,
            polylines=[broken_line('atc', 'ATC', curve)] if curve else None,
            areas=[area('zone', solution.region, outline=True)],
            points=[point(q, p, 'M', 'd', coords=True)],
            marks=marks,
            callouts=[callout(u'прибыль = %s' % fmt(solution.value),
                              solution.region, role='zone')])

    # ---------------- тексты ----------------
    def statement(self, params):
        st = self.story(params)
        return (
            # ⚠️ «а краны и причалы обходится в 160» — согласование в числе.
            # «Постоянные издержки … составляют» согласуется всегда.
            u'%s Спрос на %s задан уравнением %s (Q в %s, P в %s). Предельные '
            u'издержки постоянны и равны %s, а постоянные издержки (%s) '
            u'составляют %s независимо от объёма. Ученик нашёл объём и цену '
            u'монополиста и заштриховал прибыль.' % (
                st['lead'], st['good'], linear(params['a'], -params['b']),
                st['qunit'], st['punit'], fmt(params['mc']),
                st['fixed'], fmt(params['fc'])))

    def explain(self, params, reference, injector):
        q, p = reference.points['M']
        head = (
            u'Как надо. При спросе %s предельный доход падает вдвое круче: '
            u'MR = %s. Из MR = MC = %s получаем Q* = %s, а цену за этот объём '
            u'берём СО СПРОСА: P* = %s. Средние издержки при таком объёме '
            u'ATC = %s + %s / %s = %s. Прибыль это прямоугольник между ценой и '
            u'ATC: (%s − %s) · %s = %s.' % (
                linear(params['a'], -params['b']),
                linear(params['a'], -2 * params['b']),
                fmt(params['mc']), fmt(q), fmt(p), fmt(params['mc']),
                fmt(params['fc']), fmt(q), fmt(params['atc']),
                fmt(p), fmt(params['atc']), fmt(q), fmt(reference.value)))
        return head + u' ' + verdict(injector)
