u"""Сюжет 12 — «КПВ двух хозяйств» (сложность 5).

Контрольный пример: хозяйство А — 60 X или 30 Y (1X стоит 0,5Y);
хозяйство Б — 40 X или 40 Y (1X стоит 1Y).
Совместная КПВ: (0; 70) → излом (60; 40) → (100; 0).
Излом там, где заканчивается специализация хозяйства с МЕНЬШЕЙ
альтернативной стоимостью X, то есть А.

⚠️ Ловушка сэмплирования, на которую уже наступали: альтернативная стоимость
— это ОТНОШЕНИЕ, и на произвольной паре максимумов она чаще всего дробная и
некрасивая. Поэтому пары подбираются так, чтобы обе стоимости были целыми
или простыми половинами, и обязательно РАЗНЫМИ (при равных стоимостях излома
нет вовсе — КПВ становится прямой, и вопрос про излом теряет смысл).

⚠️ Отступление от ТЗ: в ТЗ отдельными ошибками шли «излом поставлен не там»
и «альтернативная стоимость перевёрнута». Это ОДНА и та же ошибка: перевернув
стоимость, ученик решает, что первым специализируется другое хозяйство, и
ставит излом ровно туда, куда ведёт перевёрнутое сравнение. Двумя инжекторами
это дало бы два одинаковых чертежа с разными «правильными ответами».
Записано в разбор словами.
"""
from fractions import Fraction

from game.generators._figure import (area, axis_max, broken_line, callout,
                                     figure, mark, point)
from .._fmt import fmt
from ..base import (MAX_SAMPLE_ATTEMPTS, Injector, SampleError, Scenario,
                    verdict)

# ⚠️ Хозяйства зовутся А и Б, а не «пекарня у парка». Причина не в лени:
# русские падежи. «Для пекарня на площади одна единица…» — именно это и
# получилось в первом заходе, потому что подставлять название в разные
# падежи шаблоном нельзя, а склонятель ради шести сюжетов — перебор.
# Буквы А и Б не склоняются, живое название живёт в первой фразе, и текст
# остаётся грамотным при любой подстановке.
# 'xgen'/'ygen' — товар в родительном падеже («80 буханок хлеба»).
STORIES = [
    {'key': 'farm',
     'lead': u'Два фермерских хозяйства в районе выращивают картофель и '
             u'капусту и решают, кому чем заняться.',
     'x': u'картофель', 'y': u'капуста',
     'xgen': u'картофеля', 'ygen': u'капусты',
     'xunit': u'тонн', 'yunit': u'тонн'},
    {'key': 'workshop',
     'lead': u'Две мастерские при колледже делают табуреты и полки из одного '
             u'и того же запаса досок.',
     'x': u'табуреты', 'y': u'полки',
     'xgen': u'табуретов', 'ygen': u'полок',
     'xunit': u'штук', 'yunit': u'штук'},
    {'key': 'bakery',
     'lead': u'Две пекарни одной сети пекут хлеб и булочки и делят между '
             u'собой заказ.',
     'x': u'хлеб', 'y': u'булочки',
     'xgen': u'хлеба', 'ygen': u'булочек',
     'xunit': u'буханок', 'yunit': u'штук'},
    {'key': 'island',
     'lead': u'Два соседних острова ловят рыбу и собирают кокосы и думают о '
             u'разделении труда.',
     'x': u'рыба', 'y': u'кокосы',
     'xgen': u'рыбы', 'ygen': u'кокосов',
     'xunit': u'корзин', 'yunit': u'корзин'},
    {'key': 'studio',
     'lead': u'Две студии одной компании рисуют иллюстрации и монтируют '
             u'ролики.',
     'x': u'иллюстрации', 'y': u'ролики',
     'xgen': u'иллюстраций', 'ygen': u'роликов',
     'xunit': u'штук', 'yunit': u'штук'},
    {'key': 'greenhouse',
     'lead': u'Два тепличных комплекса растят огурцы и томаты на одинаковых '
             u'площадях.',
     'x': u'огурцы', 'y': u'томаты',
     'xgen': u'огурцов', 'ygen': u'томатов',
     'xunit': u'тонн', 'yunit': u'тонн'},
]

# Альтернативная стоимость X в единицах Y — только красивые значения.
COSTS = [Fraction(1, 2), Fraction(1), Fraction(3, 2), Fraction(2),
         Fraction(3)]
XMAXES = [20, 30, 40, 50, 60, 80]


class JointPPF(Scenario):
    key = 'ppf_joint_kink'
    title = u'КПВ двух хозяйств'
    # Сложность 5: сравнить альтернативные стоимости, решить, кто
    # специализируется первым, и только потом построить излом.
    difficulty = 5
    topics = (u'Альтернативные издержки и КПВ',)

    def sample(self, rng):
        for _ in range(MAX_SAMPLE_ATTEMPTS):
            story = STORIES[rng.randrange(len(STORIES))]
            ca = COSTS[rng.randrange(len(COSTS))]
            cb = COSTS[rng.randrange(len(COSTS))]
            if ca == cb:
                continue        # равные стоимости ⇒ излома нет вовсе
            xa = XMAXES[rng.randrange(len(XMAXES))]
            xb = XMAXES[rng.randrange(len(XMAXES))]
            ya, yb = ca * xa, cb * xb
            if ya.denominator != 1 or yb.denominator != 1:
                continue
            if ya < 10 or yb < 10:
                continue
            # первым специализируется в X тот, у кого стоимость X МЕНЬШЕ
            if ca < cb:
                low, high = 'a', 'b'
                x_kink, y_kink = xa, yb
            else:
                low, high = 'b', 'a'
                x_kink, y_kink = xb, ya
            x_total, y_total = xa + xb, ya + yb
            if x_kink >= x_total or y_kink >= y_total:
                continue
            # площадь под ломаной и «площадь как у треугольника» — обе целые
            if (y_total * x_kink + y_kink * x_total) % 2 or \
                    (x_total * y_total) % 2:
                continue
            return {'story': story['key'],
                    'xa': xa, 'ya': int(ya), 'xb': xb, 'yb': int(yb),
                    'ca': ca, 'cb': cb, 'first': low, 'second': high,
                    'x_kink': int(x_kink), 'y_kink': int(y_kink),
                    'x_total': int(x_total), 'y_total': int(y_total),
                    # излом, который получится, если сравнить стоимости
                    # наоборот (специализируется тот, у кого дороже)
                    'x_kink_wrong': int(xb if ca < cb else xa),
                    'y_kink_wrong': int(ya if ca < cb else yb)}
        raise SampleError(u'ppf_joint_kink: не собрался красивый набор')

    def story(self, params):
        for s in STORIES:
            if s['key'] == params['story']:
                return s
        return STORIES[0]

    # ---------------- три шага ----------------
    def points(self, params):
        u"""Шаг 1: концы совместной КПВ и её излом."""
        return {
            'A': (Fraction(0), Fraction(params['y_total'])),
            'K': (Fraction(params['x_kink']), Fraction(params['y_kink'])),
            'B': (Fraction(params['x_total']), Fraction(0)),
        }

    def region(self, params, points):
        u"""Шаг 2: допустимое множество — под ломаной."""
        return [(Fraction(0), Fraction(0)), points['A'], points['K'],
                points['B']]

    # ---------------- ошибки ----------------
    def injectors(self):
        return [
            Injector(
                'points', 'kink_swapped',
                u'излом поставлен там, где специализируется хозяйство с '
                u'БОЛЬШЕЙ альтернативной стоимостью',
                self._kink_swapped,
                hint=u'сначала весь товар X делает тот, кому он обходится '
                     u'ДЕШЕВЛЕ в упущенном Y; ровно этот выбор и даёт излом'),
            Injector(
                'region', 'above_the_line',
                u'допустимое множество заштриховано НАД границей',
                self._above,
                hint=u'КПВ это граница возможного: под ней всё достижимо, '
                     u'а над ней недостижимо ни при каком разделении труда'),
            Injector(
                'value', 'as_triangle',
                u'площадь посчитана как у треугольника, излом не учтён',
                self._as_triangle,
                hint=u'из-за излома фигура не треугольник: у совместной КПВ '
                     u'две грани с разным наклоном, и площадь под ней больше'),
        ]

    def _kink_swapped(self, params, points, rng):
        out = dict(points)
        out['K'] = (Fraction(params['x_kink_wrong']),
                    Fraction(params['y_kink_wrong']))
        return out

    def _above(self, params, points, region, rng):
        xmax, ymax = self.frame(params)
        return [points['A'], points['K'], points['B'],
                (Fraction(xmax), Fraction(ymax)), (Fraction(0), Fraction(ymax))]

    def _as_triangle(self, params, points, region, value, rng):
        _x, y_top = points['A']
        x_right, _y = points['B']
        return x_right * y_top / 2

    # ---------------- чертёж ----------------
    def frame(self, params):
        return axis_max(params['x_total']), axis_max(params['y_total'])

    def draw(self, params, solution):
        xmax, ymax = self.frame(params)
        st = self.story(params)
        chain = [solution.points['A'], solution.points['K'],
                 solution.points['B']]
        kx, ky = solution.points['K']
        return figure(
            'ppf', xmax, ymax,
            u'%s, %s' % (st['x'].capitalize(), st['xunit']),
            u'%s, %s' % (st['y'].capitalize(), st['yunit']),
            polylines=[broken_line('ppf', u'КПВ', chain)],
            areas=[area('feasible', solution.region, outline=True)],
            points=[point(kx, ky, u'излом', 'mr', coords=True)],
            marks=[mark('x', solution.points['B'][0], u'весь X'),
                   mark('y', solution.points['A'][1], u'весь Y')],
            callouts=[callout(u'площадь = %s' % fmt(solution.value),
                              solution.region, role='feasible')])

    # ---------------- тексты ----------------
    def statement(self, params):
        st = self.story(params)
        return (
            u'%s Обозначим их А и Б. За сезон А может произвести либо %s %s '
            u'%s, либо %s %s %s; Б может произвести либо %s %s %s, '
            u'либо %s %s %s. Ученик '
            u'построил совместную КПВ, заштриховал допустимое множество и '
            u'посчитал его площадь.'
            % (st['lead'],
               fmt(params['xa']), st['xunit'], st['xgen'],
               fmt(params['ya']), st['yunit'], st['ygen'],
               fmt(params['xb']), st['xunit'], st['xgen'],
               fmt(params['yb']), st['yunit'], st['ygen']))

    def explain(self, params, reference, injector):
        st = self.story(params)
        first = u'А' if params['first'] == 'a' else u'Б'
        head = (
            u'Как надо. Альтернативная стоимость одной единицы «%s»: у А она '
            u'равна %s «%s», у Б равна %s «%s». Дешевле «%s» обходится '
            u'хозяйству %s, поэтому сначала весь этот товар делает оно, и '
            u'излом приходится на (%s; %s). Концы совместной КПВ: (0; %s) '
            u'и (%s; 0). Площадь '
            u'допустимого множества под ломаной равна %s.' % (
                st['x'], fmt(params['ca']), st['y'],
                fmt(params['cb']), st['y'], st['x'], first,
                fmt(params['x_kink']), fmt(params['y_kink']),
                fmt(params['y_total']), fmt(params['x_total']),
                fmt(reference.value)))
        return head + u' ' + verdict(injector)
