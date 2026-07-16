u"""
Архетип 11 (Блок В): линейная КПВ одного хозяйства.

КПВ задана парой максимумов (Mx, My): Y = My·(1 − X/Mx). Альтернативная
стоимость 1 ед. X = My/Mx (в ед. Y) — постоянна, потому что КПВ линейна.

Вопросы: альтернативная стоимость 1 ед. X (или Y), максимум Y при заданном
X, положение точки относительно границы (класс — только для Блица/Пули).

⚠️ Товары теперь берутся ИЗ СЮЖЕТА, а не из общего списка _ppf.PPF_GOODS
(переработка под эталон 2026-07-16). Раньше пара товаров выбиралась
случайно, и «ферма, производящая сталь и кофе» была законным исходом:
пара обязана быть частью истории, а не приезжать к ней случайно.
_ppf.PPF_GOODS оставлен непеределанным архетипам Блока В.

Единица альтернативной стоимости («ед. ткани») уехала из текста вопроса в
поле unit: тогда она же показывается игроку у поля ввода Классики.

Контроль (Mx = 60, My = 30): альт. стоимость 1X = 0,5Y; точка (40; 10) —
на границе.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _figure, _ppf

POINT_LABELS = [
    u'лежит ровно на границе КПВ (производство эффективно)',
    u'достижима, но неэффективна (лежит внутри КПВ)',
    u'недостижима при имеющихся ресурсах',
]

# Доли использования ресурса под X: дают красивые точки на КПВ.
X_FRACTIONS = [Fraction(1, 2), Fraction(1, 3), Fraction(2, 3),
               Fraction(1, 4), Fraction(3, 4), Fraction(1, 5),
               Fraction(2, 5), Fraction(3, 5)]


class Story(object):
    u"""Сюжет КПВ: своё хозяйство, СВОЯ пара товаров и общий ресурс.

    Пара товаров неотделима от истории: пекарня печёт булки и пирожные, а
    не сталь и кофе (раньше пара бралась из общего списка случайно).

    Формы слова заданы явно, потому что склеить их из одной основы нельзя,
    а «альтернативная стоимость одной единицы сайтов» выдаёт генератор
    вернее любой формулы:
      actor  — кто хозяйничает («пекарня», «команда») для текста решения;
      x_one  — «одного сайта», «одного центнера пшеницы» (в вопросе об
               альтернативной стоимости);
      x_count— «сайтов», «центнеров пшеницы» (в счётных оборотах);
      x_good — «сайтов», «пшеницы» (в единице ответа «ед. …»);
      x_axis — подпись оси графика.
    """

    def __init__(self, key, actor, x_one, x_count, x_good, x_axis,
                 y_one, y_count, y_good, y_axis, full):
        self.key = key
        self.actor = actor
        self.x_one, self.x_count, self.x_good, self.x_axis = (
            x_one, x_count, x_good, x_axis)
        self.y_one, self.y_count, self.y_good, self.y_axis = (
            y_one, y_count, y_good, y_axis)
        self.full = full


def _bakery(p, st):
    return (u'В пекарне «Тёплый угол» одна печь и один рабочий день, и '
            u'делить их приходится между двумя противнями: на булки или на '
            u'пирожные. Если печь весь день занята только булками, выходит '
            u'{} штук; если только пирожными — {} штук. Пекарь может '
            u'разделить день в любой пропорции, и тогда выпуск падает '
            u'ровно пропорционально отданному времени.').format(
                p['mx'], p['my'])


def _field(p, st):
    return (u'У фермера в деревне N одно поле, и засеять его надо целиком: '
            u'земля простаивать не должна. Всё поле под пшеницу даёт {} '
            u'центнеров за сезон, всё поле под картофель — {} центнеров. '
            u'Землю можно поделить в любой пропорции, урожай меняется '
            u'пропорционально отведённой площади.').format(p['mx'], p['my'])


def _workshop(p, st):
    return (u'Столярная мастерская «Рубанок» работает одной бригадой: '
            u'сколько часов ушло на столы, столько не досталось стульям. '
            u'За месяц бригада делает либо {} столов, либо {} стульев, '
            u'либо любую промежуточную комбинацию — время делится '
            u'пропорционально.').format(p['mx'], p['my'])


def _studio(p, st):
    return (u'В студии «Пиксель» одна команда и один спринт: взяли задачу '
            u'по сайтам — не взяли по мобильным приложениям. За спринт '
            u'команда успевает либо {} сайтов, либо {} приложений, либо '
            u'поделить силы в любой пропорции.').format(p['mx'], p['my'])


def _country(p, st):
    return (u'Экономика страны Альфа выпускает два товара — станки и '
            u'холодильники, — и ресурсы (труд, металл, энергия) у неё '
            u'ограничены и используются полностью. Бросив все ресурсы на '
            u'станки, страна выпустит за год {} штук; бросив все на '
            u'холодильники — {} штук. КПВ линейна: ресурсы одинаково '
            u'годятся для обоих производств.').format(p['mx'], p['my'])


STORIES = [
    Story('bakery', u'пекарня',
          u'одной булки', u'булок', u'булок', u'Булки, шт.',
          u'одного пирожного', u'пирожных', u'пирожных', u'Пирожные, шт.',
          _bakery),
    Story('field', u'фермер',
          u'одного центнера пшеницы', u'центнеров пшеницы', u'пшеницы',
          u'Пшеница, ц.',
          u'одного центнера картофеля', u'центнеров картофеля', u'картофеля',
          u'Картофель, ц.', _field),
    Story('workshop', u'бригада',
          u'одного стола', u'столов', u'столов', u'Столы, шт.',
          u'одного стула', u'стульев', u'стульев', u'Стулья, шт.', _workshop),
    Story('studio', u'команда',
          u'одного сайта', u'сайтов', u'сайтов', u'Сайты, шт.',
          u'одного приложения', u'приложений', u'приложений',
          u'Приложения, шт.', _studio),
    Story('country', u'страна',
          u'одного станка', u'станков', u'станков', u'Станки, шт.',
          u'одного холодильника', u'холодильников', u'холодильников',
          u'Холодильники, шт.', _country),
]


class PpfSingleArchetype(Archetype):
    key = 'ppf_single'
    title = u'Линейная КПВ'
    block = u'В. КПВ и торговля'
    topics = [u'Альтернативные издержки и КПВ']

    def sample(self, rng):
        u"""Пара максимумов + точка для вопроса-классификации.

        ⚠️ Альтернативная стоимость — это ОТНОШЕНИЕ My/Mx, и на произвольной
        паре из сетки оно чаще дробное (100/40 = 2,5). Правило «красивого
        ответа» просит целое в большинстве случаев, поэтому в 4 случаях из 5
        берём пару, где один максимум кратен другому: тогда стоимость целая
        в одну сторону и вида 1/k — в другую (обе красивы). Оставшаяся пятая часть
        — произвольная пара, ради разнообразия чисел."""
        for _ in range(200):
            if rng.random() < Fraction(4, 5):
                base = rng.choice([20, 30, 40, 50, 60])
                mult = rng.choice([2, 3, 4])
                if rng.random() < 0.5:
                    mx, my = base, base * mult
                else:
                    mx, my = base * mult, base
            else:
                mx = rng.choice(_ppf.M_GRID)
                my = rng.choice(_ppf.M_GRID)
            frac = rng.choice(X_FRACTIONS)
            x0 = frac * mx
            y_border = _ppf.y_on_ppf(mx, my, x0)
            if x0.denominator != 1 or y_border.denominator != 1:
                continue
            if y_border <= 0:
                continue
            # Точка для вопроса-классификации: на границе / внутри / выше.
            kind = rng.choice(['on', 'inside', 'outside'])
            delta = rng.choice([5, 10])
            if kind == 'on':
                y0 = y_border
            elif kind == 'inside':
                y0 = y_border - delta
                if y0 <= 0:
                    continue
            else:
                y0 = y_border + delta
            return {'mx': mx, 'my': my, 'x0': int(x0), 'y0': int(y0),
                    'story': rng.randrange(len(STORIES))}
        raise RuntimeError('ppf_single: не сэмплировалась красивая КПВ')

    def solve(self, params):
        mx, my = params['mx'], params['my']
        y_border = _ppf.y_on_ppf(mx, my, params['x0'])
        y0 = F(params['y0'])
        if y0 == y_border:
            point_class = POINT_LABELS[0]
        elif y0 < y_border:
            point_class = POINT_LABELS[1]
        else:
            point_class = POINT_LABELS[2]
        return {
            'oc_x': _ppf.oc_x(mx, my),
            'oc_y': _ppf.oc_x(my, mx),
            'y_at_x': y_border,
            'point_class': point_class,
        }

    def asked_values(self, params):
        st = STORIES[params['story']]
        return [
            Asked('oc_x',
                  nom=u'альтернативная стоимость производства {}'.format(st.x_one),
                  acc=u'альтернативную стоимость производства {}'.format(st.x_one),
                  gender='f', unit=u'ед. {}'.format(st.y_good), difficulty=2),
            Asked('oc_y',
                  nom=u'альтернативная стоимость производства {}'.format(st.y_one),
                  acc=u'альтернативную стоимость производства {}'.format(st.y_one),
                  gender='f', unit=u'ед. {}'.format(st.x_good), difficulty=2),
            Asked('y_at_x', unit=u'ед. {}'.format(st.y_good), difficulty=3,
                  question=(u'Какое наибольшее количество {} можно получить, '
                            u'если выпустить {} {}?'
                            ).format(st.y_count, params['x0'], st.x_count),
                  claim_tpl=(u'при выпуске {} {} можно получить максимум '
                             u'{{V}} {}').format(
                                 params['x0'], st.x_count, st.y_count),
                  nom=u'максимальный выпуск второго товара', gender='m'),
            Asked('point_class', kind='class', class_options=list(POINT_LABELS),
                  difficulty=3,
                  question=(u'Как расположена точка ({}; {}) — {} и {} '
                            u'соответственно — относительно КПВ?').format(
                                params['x0'], params['y0'],
                                st.x_count, st.y_count),
                  claim_tpl=(u'точка ({}; {}) {{V}}').format(
                      params['x0'], params['y0'])),
        ]

    def error_variants(self, params, solved, asked):
        mx, my = F(params['mx']), F(params['my'])
        x0 = F(params['x0'])
        if asked.key == 'oc_x':
            return [solved['oc_y'],      # перевёрнутое отношение
                    my, mx,              # взят максимум вместо отношения
                    abs(mx - my),
                    solved['oc_x'] * 2]
        if asked.key == 'oc_y':
            return [solved['oc_x'], mx, my, abs(mx - my),
                    solved['oc_y'] * 2]
        # y_at_x
        return [my - x0,                 # вычли X напрямую из максимума Y
                my * x0 / mx,            # доля произведённого, а не остатка
                my,                      # ограничение проигнорировано
                x0,
                mx - x0]

    def wrappers(self):
        u"""Один Wrapper: сюжет (а с ним и пара товаров) выбран в sample()."""
        def full(p, s):
            st = STORIES[p['story']]
            return st.full(p, st)

        def short(p, s):
            st = STORIES[p['story']]
            return (u'КПВ линейна: максимум {} {} либо {} {}.').format(
                p['mx'], st.x_count, p['my'], st.y_count)

        return [Wrapper('story', full, short)]

    def solution(self, params, solved, asked):
        mx, my = params['mx'], params['my']
        st = STORIES[params['story']]
        oc = _ppf.oc_x(mx, my)
        eq_step = (u'Ресурс общий, поэтому потраченное на один товар '
                   u'недоступно для другого. КПВ линейна, её уравнение: '
                   u'$Y = {} \\cdot (1 - X/{})$, где $X$ — выпуск {}, '
                   u'$Y$ — выпуск {}.').format(
                       fmt_num(my, latex=True), fmt_num(mx, latex=True),
                       st.x_count, st.y_count)
        if asked.key in ('oc_x', 'oc_y'):
            num, den = (my, mx) if asked.key == 'oc_x' else (mx, my)
            one = st.x_one if asked.key == 'oc_x' else st.y_one
            count = st.x_count if asked.key == 'oc_x' else st.y_count
            in_what = st.y_good if asked.key == 'oc_x' else st.x_good
            return [
                u'Альтернативная стоимость — это то, ЧЕМ ЖЕРТВУЮТ ради '
                u'товара, а не сколько за него платят деньгами.',
                u'Отказавшись от всех {} {}, {} получает {} ед. {}. КПВ '
                u'линейна, значит курс обмена одинаков на всём протяжении '
                u'границы.'.format(
                    fmt_num(den, latex=True), count, st.actor,
                    fmt_num(num, latex=True), in_what),
                u'Делим на количество: ради {} приходится жертвовать '
                u'${} / {} = {}$ ед. {}.'.format(
                    one, fmt_num(num, latex=True), fmt_num(den, latex=True),
                    fmt_num(solved[asked.key], latex=True), in_what),
            ]
        if asked.key == 'y_at_x':
            return [
                eq_step,
                u'На {} {} уходит доля ${}/{}$ всего ресурса — значит на '
                u'второй товар остаётся остальное.'.format(
                    params['x0'], st.x_count, params['x0'],
                    fmt_num(mx, latex=True)),
                u'Подставим $X = {}$: $Y = {} \\cdot (1 - {}/{}) = {}$ ед. '
                u'{}'.format(
                    params['x0'], fmt_num(my, latex=True), params['x0'],
                    fmt_num(mx, latex=True),
                    fmt_num(solved['y_at_x'], latex=True), st.y_good),
                u'Проверка через альтернативную стоимость: {} {} стоят '
                u'${} \\cdot {} = {}$ ед. {} — ровно на столько выпуск '
                u'меньше максимума {}.'.format(
                    params['x0'], st.x_count, params['x0'],
                    fmt_num(oc, latex=True),
                    fmt_num(F(params['x0']) * oc, latex=True), st.y_good,
                    fmt_num(my, latex=True)),
            ]
        # point_class
        y0 = params['y0']
        border = solved['y_at_x']
        if F(y0) == border:
            why = (u'Столько и получается — точка лежит НА границе: ресурсы '
                   u'заняты полностью и без потерь.')
        elif F(y0) < border:
            why = (u'Это меньше границы — значит часть ресурса простаивает '
                   u'или тратится впустую. Точка достижима, но неэффективна: '
                   u'можно выпустить больше, ничего не отнимая.')
        else:
            why = (u'Это больше границы — таких ресурсов у хозяйства просто '
                   u'нет. Точка недостижима.')
        return [
            eq_step,
            u'Найдём границу при $X = {}$: $Y = {} \\cdot (1 - {}/{}) = {}$ '
            u'ед. {}'.format(
                params['x0'], fmt_num(my, latex=True), params['x0'],
                fmt_num(mx, latex=True), fmt_num(border, latex=True),
                st.y_good),
            u'У точки $Y = {}$. {}'.format(y0, why),
            u'Вывод: точка {}.'.format(solved['point_class']),
        ]

    def figure(self, params, solved, asked):
        u"""КПВ: граница, достижимое множество и точка из вопроса."""
        mx, my = F(params['mx']), F(params['my'])
        st = STORIES[params['story']]
        x0, y0 = F(params['x0']), F(params['y0'])
        xmax = _figure.axis_max(mx)
        ymax = _figure.axis_max(max(my, y0))
        points = [_figure.point(x0, y0, 'A', 'reg')]
        # Точку-вопрос показываем всегда; на КПВ-границе — ещё и ориентир
        if asked.key == 'y_at_x':
            points = [_figure.point(x0, solved['y_at_x'], 'A', 'ppf')]
        return _figure.figure(
            'ppf', xmax, ymax,
            st.x_axis, st.y_axis,
            lines=[
                _figure.line('ppf', u'КПВ', (0, my), (mx, 0)),
                _figure.line('ghost', '', (0, points[0]['y']),
                             (points[0]['x'], points[0]['y']), dash=True),
                _figure.line('ghost', '', (points[0]['x'], 0),
                             (points[0]['x'], points[0]['y']), dash=True),
            ],
            areas=[_figure.area('feasible', [(0, 0), (mx, 0), (0, my)],
                                u'Достижимо')],
            points=points,
            marks=[_figure.mark('x', mx, 'M_x'), _figure.mark('y', my, 'M_y')])


ARCHETYPE = PpfSingleArchetype()
