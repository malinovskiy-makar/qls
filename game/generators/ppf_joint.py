"""
Архетип 12 (Блок В): суммарная КПВ двух стран с изломом.

Наращивание X начинает страна с меньшей альтернативной стоимостью X;
излом — когда она целиком уходит в X: (Mx_дешёвой, My_другой).

Контроль: A(60X/30Y) + B(20X/40Y) → излом (60; 40); при X = 70 → Y = 20.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _ppf


def _countries(params):
    """((mx, my) Альфы, (mx, my) Беты)."""
    return (params['mxa'], params['mya']), (params['mxb'], params['myb'])


def _low_high(params):
    """Страны в порядке возрастания альт. стоимости X:
    ((mx, my, имя) дешёвой по X, (mx, my, имя) дорогой)."""
    (mxa, mya), (mxb, myb) = _countries(params)
    a = (mxa, mya, u'Альфа')
    b = (mxb, myb, u'Бета')
    if _ppf.oc_x(mxa, mya) <= _ppf.oc_x(mxb, myb):
        return a, b
    return b, a


class PpfJointArchetype(Archetype):
    key = 'ppf_joint'
    title = u'Суммарная КПВ двух стран'
    block = u'В. КПВ и торговля'
    topics = [u'Альтернативные издержки и КПВ']

    def sample(self, rng):
        for _ in range(300):
            mxa, mya = rng.choice(_ppf.M_GRID), rng.choice(_ppf.M_GRID)
            mxb, myb = rng.choice(_ppf.M_GRID), rng.choice(_ppf.M_GRID)
            if _ppf.oc_x(mxa, mya) == _ppf.oc_x(mxb, myb):
                continue  # без разницы в альт. стоимости излома нет
            total_x = mxa + mxb
            x_cands = [x for x in range(10, total_x, 10)]
            if not x_cands:
                continue
            x0 = rng.choice(x_cands)
            p = {'mxa': mxa, 'mya': mya, 'mxb': mxb, 'myb': myb, 'x0': x0}
            s = self.solve(p)
            if s['y_at_x'] <= 0:
                continue
            ix, iy = _ppf.pick_goods_pair(rng)
            p['gx'], p['gy'] = ix, iy
            return p
        raise RuntimeError('ppf_joint: не сэмплировались красивые страны')

    def solve(self, params):
        low, high = _low_high(params)
        kink_x, kink_y = F(low[0]), F(high[1])
        total_y = F(params['mya']) + F(params['myb'])
        oc_low = _ppf.oc_x(low[0], low[1])
        oc_high = _ppf.oc_x(high[0], high[1])
        x0 = F(params['x0'])
        if x0 <= kink_x:
            y_at_x = total_y - oc_low * x0
        else:
            y_at_x = kink_y - oc_high * (x0 - kink_x)
        return {
            'kink_x': kink_x, 'kink_y': kink_y,
            'total_max_x': F(params['mxa']) + F(params['mxb']),
            'total_max_y': total_y,
            'y_at_x': y_at_x,
        }

    def asked_values(self, params):
        gx = _ppf.PPF_GOODS[params['gx']]
        gy = _ppf.PPF_GOODS[params['gy']]
        return [
            Asked('kink_x', unit=u'ед.',
                  question=(u'При каком суммарном выпуске {} на суммарной КПВ '
                            u'находится точка излома?').format(gx[1]),
                  claim_tpl=(u'излом суммарной КПВ находится при выпуске '
                             u'{{V}} ед. {}').format(gx[1]),
                  nom=u'абсцисса точки излома', gender='f'),
            Asked('kink_y', unit=u'ед.',
                  question=(u'Какому суммарному выпуску {} соответствует '
                            u'точка излома суммарной КПВ?').format(gy[1]),
                  claim_tpl=(u'в точке излома суммарной КПВ выпускается '
                             u'{{V}} ед. {}').format(gy[1]),
                  nom=u'ордината точки излома', gender='f'),
            Asked('total_max_y', trivial=True, unit=u'ед.',
                  nom=u'наибольший суммарный выпуск {}'.format(gy[1]),
                  acc=u'наибольший суммарный выпуск {}'.format(gy[1]),
                  gender='m'),
            Asked('y_at_x', unit=u'ед.',
                  question=(u'Какое наибольшее суммарное количество единиц {} '
                            u'можно произвести, если вместе страны выпускают '
                            u'{} единиц {}?').format(
                                gy[1], params['x0'], gx[1]),
                  claim_tpl=(u'при суммарном выпуске {} ед. {} страны могут '
                             u'произвести максимум {{V}} ед. {}').format(
                                 params['x0'], gx[1], gy[1]),
                  nom=u'максимальный суммарный выпуск второго товара',
                  gender='m'),
        ]

    def error_variants(self, params, solved, asked):
        low, high = _low_high(params)
        oc_low = _ppf.oc_x(low[0], low[1])
        oc_high = _ppf.oc_x(high[0], high[1])
        total_y = solved['total_max_y']
        x0 = F(params['x0'])
        if asked.key == 'kink_x':
            return [F(high[0]),                    # специализация перепутана
                    solved['total_max_x'],
                    solved['kink_y'],              # координаты перепутаны
                    F(low[0]) / 2]
        if asked.key == 'kink_y':
            return [F(low[1]),                     # взяли Y дешёвой страны
                    total_y,
                    solved['kink_x'],              # координаты перепутаны
                    F(high[1]) / 2]
        if asked.key == 'total_max_y':
            return [F(params['mya']), F(params['myb']),
                    solved['total_max_x'],
                    total_y / 2]
        # y_at_x: посчитали не тем сегментом / не той альт. стоимостью
        return [total_y - oc_low * x0,
                total_y - oc_high * x0,
                solved['kink_y'],
                solved['kink_y'] - oc_low * (x0 - solved['kink_x']),
                total_y]

    def wrappers(self):
        def full(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Страны Альфа и Бета производят {} и {}; КПВ каждой '
                    u'линейна. Альфа может выпустить максимум {} ед. {} либо '
                    u'{} ед. {}, а Бета {} ед. {} либо {} ед. {}. Страны '
                    u'объединяют производство и распределяют его '
                    u'эффективно.').format(
                        gx[0], gy[0], p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def short(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'КПВ линейны. Альфа: {} ед. {} либо {} ед. {}; '
                    u'Бета: {} ед. {} либо {} ед. {}. Производят сообща.').format(
                        p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def full_neighbours(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'У соседних стран Альфа и Бета общая граница и разное '
                    u'хозяйство. Обе производят {} и {}, КПВ каждой линейна. '
                    u'Альфа может выпустить максимум {} ед. {} либо {} ед. '
                    u'{}, а Бета {} ед. {} либо {} ед. {}. Соседи решили '
                    u'производить сообща.').format(
                        gx[0], gy[0], p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def full_islands(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Островные государства Альфа и Бета живут своим '
                    u'хозяйством и производят {} и {}; КПВ каждой линейна. '
                    u'Альфа выпускает максимум {} ед. {} либо {} ед. {}, '
                    u'а Бета {} ед. {} либо {} ед. {}. Они наладили паром и '
                    u'считают, что смогут произвести вместе.').format(
                        gx[0], gy[0], p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def full_union(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Страны Альфа и Бета обсуждают союз без пошлин. Обе '
                    u'производят {} и {}, КПВ каждой линейна: Альфа может '
                    u'выпустить максимум {} ед. {} либо {} ед. {}, а Бета '
                    u'{} ед. {} либо {} ед. {}. Переговорщики считают '
                    u'совместные возможности.').format(
                        gx[0], gy[0], p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def full_class(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'На олимпиадном разборе строят суммарную КПВ двух стран. '
                    u'Альфа и Бета производят {} и {}, КПВ каждой линейна: '
                    u'Альфа даёт максимум {} ед. {} либо {} ед. {}, Бета '
                    u'{} ед. {} либо {} ед. {}. Производство объединяют и '
                    u'распределяют эффективно.').format(
                        gx[0], gy[0], p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def short_neighbours(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Соседи, КПВ линейны. Альфа: {} ед. {} либо {} ед. {}; '
                    u'Бета: {} ед. {} либо {} ед. {}. Производят сообща.'
                    ).format(p['mxa'], gx[1], p['mya'], gy[1],
                             p['mxb'], gx[1], p['myb'], gy[1])

        def short_islands(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Два острова, КПВ линейны. Альфа: {} ед. {} либо {} ед. '
                    u'{}; Бета: {} ед. {} либо {} ед. {}. Производят сообща.'
                    ).format(p['mxa'], gx[1], p['mya'], gy[1],
                             p['mxb'], gx[1], p['myb'], gy[1])

        def short_union(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Союз без пошлин, КПВ линейны. Альфа: {} ед. {} либо '
                    u'{} ед. {}; Бета: {} ед. {} либо {} ед. {}.').format(
                        p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def short_class(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Разбор: КПВ линейны. Альфа: {} ед. {} либо {} ед. {}; '
                    u'Бета: {} ед. {} либо {} ед. {}. Сообща.').format(
                        p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        return [Wrapper('countries', full, short),
                Wrapper('neighbours', full_neighbours, short_neighbours),
                Wrapper('islands', full_islands, short_islands),
                Wrapper('union', full_union, short_union),
                Wrapper('class', full_class, short_class)]

    def solution(self, params, solved, asked):
        low, high = _low_high(params)
        oc_low = _ppf.oc_x(low[0], low[1])
        oc_high = _ppf.oc_x(high[0], high[1])
        gx = _ppf.PPF_GOODS[params['gx']]
        gy = _ppf.PPF_GOODS[params['gy']]
        if asked.key == 'total_max_y':
            return [u'Обе страны выпускают только {}: ${} + {} = {}$ ед.'.format(
                gy[0], params['mya'], params['myb'],
                fmt_num(solved['total_max_y'], latex=True))]
        steps = [
            (u'Альтернативная стоимость 1 ед. {}: у страны {} она равна '
             u'${}$, у страны {} равна ${}$ (ед. {}); первой {} '
             u'наращивает {}.').format(
                gx[1], low[2], fmt_num(oc_low, latex=True),
                high[2], fmt_num(oc_high, latex=True), gy[1],
                gx[0], low[2]),
            (u'Излом суммарной КПВ наступает, когда {} целиком в {}: '
             u'$({};\\ {})$.').format(
                low[2], gx[0],
                fmt_num(solved['kink_x'], latex=True),
                fmt_num(solved['kink_y'], latex=True)),
        ]
        if asked.key == 'y_at_x':
            x0 = F(params['x0'])
            if x0 <= solved['kink_x']:
                steps.append(
                    u'$X = {}$ до излома: $Y = {} - {} \\cdot {} = {}$ ед.'.format(
                        params['x0'],
                        fmt_num(solved['total_max_y'], latex=True),
                        fmt_num(oc_low, latex=True), params['x0'],
                        fmt_num(solved['y_at_x'], latex=True)))
            else:
                steps.append(
                    (u'$X = {}$ за изломом: страна {} выпускает {} ед. {}, '
                     u'поэтому $Y = {} - {} \\cdot {} = {}$ ед.').format(
                        params['x0'], high[2],
                        fmt_num(x0 - solved['kink_x'], latex=True), gx[1],
                        fmt_num(solved['kink_y'], latex=True),
                        fmt_num(oc_high, latex=True),
                        fmt_num(x0 - solved['kink_x'], latex=True),
                        fmt_num(solved['y_at_x'], latex=True)))
        return steps


ARCHETYPE = PpfJointArchetype()
