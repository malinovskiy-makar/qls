u"""Сюжет 10 — «Единичная эластичность и максимум выручки» (сложность 4).

Контрольный пример: спрос P = 100 − 2Q. Единичная эластичность — ровно в
середине отрезка спроса: Q = 25, P = 50. Выручка TR = 50 · 25 = 1250, и она
здесь максимальна.

Сюжет специально устроен так, чтобы у него БЫЛА область: иначе игрок за
десяток забегов выучит, что «на эластичности область не спрашивают», и
перестанет её проверять.

⚠️ ОТСТУПЛЕНИЕ ОТ ТЗ, осознанное. В ТЗ у этого сюжета две ошибки вычисления
были про ПОДПИСЬ эластичности («|E| = 2» вместо 1, «E = +1»). Подпись
эластичности — свойство ТОЧКИ (она считается из её координат), а не третьего
шага: сделать её ошибкой вычисления значило бы завести на чертеже второе
независимое «записанное число», и «испорчен ровно один шаг» перестало бы
выполняться. Поэтому подпись у точки считается честно из её координат (в
верном решении там и выходит «|E| = 1»), а ошибками вычисления взяты две
настоящие арифметические: выручку посчитали как треугольник и умножили цену
на цену вместо цены на количество. Пункт занесён в хвосты.
"""
from fractions import Fraction

from game.generators._figure import (area, axis_max, callout, clip_linear,
                                     figure, line, mark, point)
from .._fmt import fmt, linear
from ..base import (MAX_SAMPLE_ATTEMPTS, Injector, SampleError, Scenario,
                    verdict)

STORIES = [
    {'key': 'museum',
     'lead': u'Музей подбирает цену билета так, чтобы выручка была наибольшей.',
     'good': u'билеты в музей', 'qunit': u'тыс. билетов в месяц',
     'punit': u'руб. за билет'},
    {'key': 'app',
     'lead': u'Разработчик приложения ищет подписку, при которой выручка '
             u'максимальна.',
     'good': u'подписки', 'qunit': u'тыс. подписок',
     'punit': u'руб. в месяц'},
    {'key': 'parking2',
     'lead': u'Оператор парковки подбирает тариф ради наибольшей выручки: '
             u'мест хватает, издержки почти не растут.',
     'good': u'парковочные часы', 'qunit': u'тыс. часов в день',
     'punit': u'руб. за час'},
    {'key': 'concert',
     'lead': u'Организатор концерта в парке выбирает цену входа, чтобы '
             u'собрать как можно больше.',
     'good': u'входные билеты', 'qunit': u'тыс. билетов',
     'punit': u'руб. за билет'},
    {'key': 'ferry2',
     'lead': u'Речной трамвайчик ищет цену прогулки, при которой сборы '
             u'наибольшие.',
     'good': u'прогулки', 'qunit': u'тыс. поездок за сезон',
     'punit': u'руб. за поездку'},
    {'key': 'cloud',
     'lead': u'Облачный сервис подбирает цену тарифа ради максимальной '
             u'выручки.',
     'good': u'тарифы', 'qunit': u'тыс. аккаунтов', 'punit': u'руб. в месяц'},
]

SLOPES = [Fraction(1, 2), Fraction(1), Fraction(2), Fraction(4)]
# Спрос упирается в ось Q в точке a/b; её делим на 5 для ошибочной точки,
# поэтому a/b обязано делиться на 10 (и на 2 — ради середины).
QMAXES = [20, 30, 40, 50, 60, 80, 100]


class UnitElasticity(Scenario):
    key = 'unit_elasticity'
    title = u'Единичная эластичность и максимум выручки'
    # Сложность 4: надо знать, что |E| = 1 ровно в середине отрезка спроса,
    # и что именно там выручка максимальна.
    difficulty = 4
    topics = (u'Эластичность',)

    def sample(self, rng):
        for _ in range(MAX_SAMPLE_ATTEMPTS):
            story = STORIES[rng.randrange(len(STORIES))]
            qmax = QMAXES[rng.randrange(len(QMAXES))]      # спрос при P = 0
            b = SLOPES[rng.randrange(len(SLOPES))]
            a = b * qmax
            if a.denominator != 1 or a % 2 != 0:
                continue
            q = Fraction(qmax, 2)                          # середина отрезка
            p = a / 2
            if q.denominator != 1 or p.denominator != 1:
                continue
            q_wrong = Fraction(qmax, 5)                    # где |E| = 4
            if q_wrong.denominator != 1:
                continue
            p_wrong = a - b * q_wrong
            if p_wrong.denominator != 1:
                continue
            # ⚠️ При P = Q ошибка «цену умножили на цену» даёт ТО ЖЕ число
            # и становится невидимой (для P = a/2 и Q = a/2b это ровно
            # случай b = 1). Поймано тестом-шлюзом.
            if p == q:
                continue
            tr = p * q
            if tr.denominator != 1 or tr < 100:
                continue
            return {'story': story['key'], 'b': b, 'a': int(a),
                    'qmax': int(qmax), 'q': int(q), 'p': int(p),
                    'q_wrong': int(q_wrong), 'p_wrong': int(p_wrong)}
        raise SampleError(u'unit_elasticity: не собрался красивый набор')

    def story(self, params):
        for s in STORIES:
            if s['key'] == params['story']:
                return s
        return STORIES[0]

    def _elasticity(self, params, q, p):
        u"""|E| = P / (b · Q) для линейного спроса P = a − bQ."""
        if q == 0:
            return None
        return abs(p / (params['b'] * q))

    # ---------------- три шага ----------------
    def points(self, params):
        u"""Шаг 1: точка, в которой ученик увидел единичную эластичность."""
        return {'U': (Fraction(params['q']), Fraction(params['p']))}

    def region(self, params, points):
        u"""Шаг 2: прямоугольник выручки под этой точкой."""
        q, p = points['U']
        return [(Fraction(0), Fraction(0)), (q, Fraction(0)), (q, p),
                (Fraction(0), p)]

    # ---------------- ошибки ----------------
    def injectors(self):
        return [
            Injector(
                'points', 'not_the_middle',
                u'точка единичной эластичности поставлена не в середине спроса',
                self._off_middle,
                hint=u'у линейного спроса |E| = 1 ровно на СЕРЕДИНЕ отрезка: '
                     u'выше середины спрос эластичен, ниже неэластичен, и '
                     u'выручка максимальна именно в середине'),
            Injector(
                'region', 'wrong_height',
                u'прямоугольник выручки отложен от неверной высоты',
                self._wrong_height,
                hint=u'выручка это цена, по которой РЕАЛЬНО продают, '
                     u'умноженная на количество; максимальная цена спроса '
                     u'здесь ни при чём'),
            Injector(
                'value', 'as_triangle',
                u'выручка посчитана как площадь треугольника', self._as_triangle,
                hint=u'выручка это ПРЯМОУГОЛЬНИК «цена × количество», '
                     u'половины в нём нет'),
            Injector(
                'value', 'price_squared',
                u'цена умножена на цену вместо цены на количество',
                self._price_squared,
                hint=u'в произведении P · Q второй множитель это количество; '
                     u'цену дважды не берут'),
        ]

    def _off_middle(self, params, points, rng):
        return {'U': (Fraction(params['q_wrong']), Fraction(params['p_wrong']))}

    def _wrong_height(self, params, points, region, rng):
        q, _p = points['U']
        top = Fraction(params['a'])           # максимальная цена спроса
        return [(Fraction(0), Fraction(0)), (q, Fraction(0)), (q, top),
                (Fraction(0), top)]

    def _as_triangle(self, params, points, region, value, rng):
        return value / 2

    def _price_squared(self, params, points, region, value, rng):
        _q, p = points['U']
        return p * p

    # ---------------- чертёж ----------------
    def frame(self, params):
        return axis_max(params['qmax']), axis_max(params['a'])

    def draw(self, params, solution):
        xmax, ymax = self.frame(params)
        st = self.story(params)
        lines = []
        seg = clip_linear(-params['b'], params['a'], xmax, ymax)
        if seg:
            lines.append(line('d', 'D', seg[0], seg[1]))

        q, p = solution.points['U']
        e = self._elasticity(params, q, p)
        # Подпись эластичности считается ИЗ КООРДИНАТ точки — она честная
        # часть первого шага, а не отдельное записанное число.
        label = u'|E| = %s' % fmt(e) if e is not None else u'|E|'
        marks = []
        if q > 0:
            marks.append(mark('x', q, 'Q'))
        if p > 0:
            marks.append(mark('y', p, 'P'))
        return figure(
            'elasticity', xmax, ymax,
            u'Q, %s' % st['qunit'], u'P, %s' % st['punit'],
            lines=lines,
            areas=[area('zone', solution.region, outline=True)],
            points=[point(q, p, label, 'd', coords=True)],
            marks=marks,
            callouts=[callout(u'TR = %s' % fmt(solution.value),
                              solution.region, role='zone')])

    # ---------------- тексты ----------------
    def statement(self, params):
        st = self.story(params)
        return (
            u'%s Спрос на %s задан уравнением %s (Q в %s, P в %s). Ученик '
            u'отметил точку, где спрос единично эластичен, и заштриховал '
            u'выручку в ней.' % (
                st['lead'], st['good'], linear(params['a'], -params['b']),
                st['qunit'], st['punit']))

    def explain(self, params, reference, injector):
        q, p = reference.points['U']
        head = (
            u'Как надо. У линейного спроса %s единичная эластичность ровно на '
            u'середине отрезка: спрос упирается в ось Q при Q = %s, значит '
            u'Q = %s и P = %s. Там же выручка максимальна: TR = %s · %s = %s.'
            % (linear(params['a'], -params['b']), fmt(params['qmax']),
               fmt(q), fmt(p), fmt(p), fmt(q), fmt(reference.value)))
        return head + u' ' + verdict(injector)
