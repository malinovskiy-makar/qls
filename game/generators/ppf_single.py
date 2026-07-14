"""
Архетип 11 (Блок В): линейная КПВ одной страны/фермы.

Вопросы: альтернативная стоимость 1 ед. X (или Y), максимум Y при заданном
X, положение точки относительно границы (класс: на границе / внутри /
недостижима).

Контроль (60X/30Y): альт. стоимость 1X = 0,5Y; точка (40; 10) — на границе.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _ppf

POINT_LABELS = [
    u'лежит ровно на границе КПВ (производство эффективно)',
    u'достижима, но неэффективна (лежит внутри КПВ)',
    u'недостижима при имеющихся ресурсах',
]

# Доли использования ресурса под X: дают красивые точки на КПВ.
X_FRACTIONS = [Fraction(1, 2), Fraction(1, 3), Fraction(2, 3),
               Fraction(1, 4), Fraction(3, 4), Fraction(1, 5),
               Fraction(2, 5), Fraction(3, 5)]


class PpfSingleArchetype(Archetype):
    key = 'ppf_single'
    title = u'Линейная КПВ'
    block = u'В. КПВ и торговля'
    topics = [u'Альтернативные издержки и КПВ']

    def sample(self, rng):
        for _ in range(200):
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
            ix, iy = _ppf.pick_goods_pair(rng)
            return {'mx': mx, 'my': my, 'x0': int(x0), 'y0': int(y0),
                    'gx': ix, 'gy': iy}
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
        gx = _ppf.PPF_GOODS[params['gx']]
        gy = _ppf.PPF_GOODS[params['gy']]
        oc_nom_x = (u'альтернативная стоимость производства одной '
                    u'единицы {} (в единицах {})'.format(gx[1], gy[1]))
        oc_acc_x = (u'альтернативную стоимость производства одной '
                    u'единицы {} (в единицах {})'.format(gx[1], gy[1]))
        oc_nom_y = (u'альтернативная стоимость производства одной '
                    u'единицы {} (в единицах {})'.format(gy[1], gx[1]))
        oc_acc_y = (u'альтернативную стоимость производства одной '
                    u'единицы {} (в единицах {})'.format(gy[1], gx[1]))
        return [
            Asked('oc_x', nom=oc_nom_x, acc=oc_acc_x, gender='f', unit=''),
            Asked('oc_y', nom=oc_nom_y, acc=oc_acc_y, gender='f', unit=''),
            Asked('y_at_x', unit=u'ед.',
                  question=(u'Какое наибольшее количество единиц {} можно '
                            u'произвести, если выпускается {} единиц {}?'
                            ).format(gy[1], params['x0'], gx[1]),
                  claim_tpl=(u'при выпуске {} единиц {} можно произвести '
                             u'максимум {{V}} единиц {}').format(
                                 params['x0'], gx[1], gy[1]),
                  nom=u'максимальный выпуск второго товара', gender='m'),
            Asked('point_class', kind='class', class_options=list(POINT_LABELS),
                  question=(u'Как расположена точка ({}; {}) — {} и {} '
                            u'соответственно — относительно КПВ?').format(
                                params['x0'], params['y0'], gx[0], gy[0]),
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
        def full(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Ферма в стране Альфа производит {} и {}; её КПВ линейна. '
                    u'За сезон можно произвести максимум {} единиц {} '
                    u'(если выпускать только его) либо {} единиц {}.').format(
                        gx[0], gy[0], p['mx'], gx[1], p['my'], gy[1])

        def full_country(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Экономика страны Альфа выпускает два блага — {} и {}. '
                    u'КПВ линейна: максимум {} единиц {} либо {} единиц {}. '
                    u'Ресурсы используются полностью.').format(
                        gx[0], gy[0], p['mx'], gx[1], p['my'], gy[1])

        def short(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'КПВ линейна: максимум {} ед. {} либо {} ед. {}.').format(
                p['mx'], gx[1], p['my'], gy[1])

        return [Wrapper('farm', full, short),
                Wrapper('country', full_country, short)]

    def solution(self, params, solved, asked):
        mx, my = params['mx'], params['my']
        gx, gy = _ppf.PPF_GOODS[params['gx']], _ppf.PPF_GOODS[params['gy']]
        eq_step = (u'КПВ линейна: $Y = {} - {}X$, где $X$ — выпуск {}, '
                   u'$Y$ — выпуск {}.').format(
                       fmt_num(my, latex=True),
                       fmt_num(_ppf.oc_x(mx, my), latex=True) if _ppf.oc_x(mx, my) != 1 else '',
                       gx[1], gy[1])
        if asked.key in ('oc_x', 'oc_y'):
            num, den = (my, mx) if asked.key == 'oc_x' else (mx, my)
            what, in_what = (gx[1], gy[1]) if asked.key == 'oc_x' else (gy[1], gx[1])
            return [
                u'Наклон линейной КПВ постоянен: отказ от {} ед. {} даёт {} ед. {}.'.format(
                    den, what, num, in_what),
                u'Альтернативная стоимость 1 ед. {}: ${} / {} = {}$ ед. {}.'.format(
                    what, fmt_num(num, latex=True), fmt_num(den, latex=True),
                    fmt_num(solved[asked.key], latex=True), in_what),
            ]
        if asked.key == 'y_at_x':
            return [
                eq_step,
                u'При $X = {}$: $Y = {} \\cdot (1 - {}/{}) = {}$ ед.'.format(
                    params['x0'], fmt_num(my, latex=True), params['x0'], mx,
                    fmt_num(solved['y_at_x'], latex=True)),
            ]
        # point_class
        return [
            eq_step,
            u'Граница при $X = {}$: $Y = {}$; у точки $Y = {}$.'.format(
                params['x0'], fmt_num(solved['y_at_x'], latex=True),
                params['y0']),
            u'Вывод: точка {}.'.format(solved['point_class']),
        ]


ARCHETYPE = PpfSingleArchetype()
