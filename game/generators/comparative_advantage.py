"""
Архетип 13 (Блок В): сравнительное преимущество и диапазон взаимовыгодной
цены обмена для двух стран с линейными КПВ.

Преимущество по X — у страны с меньшей альтернативной стоимостью X;
взаимовыгодная цена 1 ед. X лежит строго между двумя альтернативными
стоимостями.

Контроль (A: 60X/30Y, B: 20X/40Y): преимущество по X у A;
цена 1X между 0,5Y и 2Y.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _ppf

COUNTRIES = [u'страна Альфа', u'страна Бета']


class ComparativeAdvantageArchetype(Archetype):
    key = 'comparative_advantage'
    title = u'Сравнительное преимущество и цена обмена'
    block = u'В. КПВ и торговля'
    topics = [u'Международная торговля']

    def sample(self, rng):
        # Правило красивого ответа: границы цены — отношения My/Mx, сами по
        # себе часто дробные; в ~70 % случаев требуем обе границы целыми.
        want_int = rng.random() < 0.7
        for _ in range(300):
            mxa, mya = rng.choice(_ppf.M_GRID), rng.choice(_ppf.M_GRID)
            mxb, myb = rng.choice(_ppf.M_GRID), rng.choice(_ppf.M_GRID)
            oca, ocb = _ppf.oc_x(mxa, mya), _ppf.oc_x(mxb, myb)
            if oca == ocb:
                continue  # преимущества нет — обмен не взаимовыгоден
            if want_int and (oca.denominator != 1 or ocb.denominator != 1):
                continue
            ix, iy = _ppf.pick_goods_pair(rng)
            return {'mxa': mxa, 'mya': mya, 'mxb': mxb, 'myb': myb,
                    'gx': ix, 'gy': iy}
        raise RuntimeError('comparative_advantage: не сэмплировались страны')

    def solve(self, params):
        oca = _ppf.oc_x(params['mxa'], params['mya'])
        ocb = _ppf.oc_x(params['mxb'], params['myb'])
        adv_x = COUNTRIES[0] if oca < ocb else COUNTRIES[1]
        adv_y = COUNTRIES[1] if oca < ocb else COUNTRIES[0]
        return {'oca': oca, 'ocb': ocb,
                'adv_x': adv_x, 'adv_y': adv_y,
                'price_low': min(oca, ocb), 'price_high': max(oca, ocb)}

    def asked_values(self, params):
        gx = _ppf.PPF_GOODS[params['gx']]
        gy = _ppf.PPF_GOODS[params['gy']]
        return [
            Asked('adv_x', kind='class', class_options=list(COUNTRIES),
                  question=(u'У какой страны сравнительное преимущество '
                            u'в производстве {}?').format(gx[1]),
                  claim_tpl=(u'сравнительное преимущество в производстве {} '
                             u'имеет {{V}}').format(gx[1])),
            Asked('adv_y', kind='class', class_options=list(COUNTRIES),
                  question=(u'У какой страны сравнительное преимущество '
                            u'в производстве {}?').format(gy[1]),
                  claim_tpl=(u'сравнительное преимущество в производстве {} '
                             u'имеет {{V}}').format(gy[1])),
            Asked('price_low', unit='',
                  question=(u'Укажите нижнюю границу диапазона цен '
                            u'(в единицах {} за 1 ед. {}), при которых обмен '
                            u'взаимовыгоден.').format(gy[1], gx[1]),
                  claim_tpl=(u'нижняя граница взаимовыгодной цены 1 ед. {} '
                             u'равна {{V}} ед. {}').format(gx[1], gy[1]),
                  nom=u'нижняя граница цены', gender='f'),
            Asked('price_high', unit='',
                  question=(u'Укажите верхнюю границу диапазона цен '
                            u'(в единицах {} за 1 ед. {}), при которых обмен '
                            u'взаимовыгоден.').format(gy[1], gx[1]),
                  claim_tpl=(u'верхняя граница взаимовыгодной цены 1 ед. {} '
                             u'равна {{V}} ед. {}').format(gx[1], gy[1]),
                  nom=u'верхняя граница цены', gender='f'),
        ]

    def error_variants(self, params, solved, asked):
        oca, ocb = solved['oca'], solved['ocb']
        other = solved['price_high'] if asked.key == 'price_low' \
            else solved['price_low']
        return [other,                    # другая граница диапазона
                1 / oca,                  # перевёрнутые отношения
                1 / ocb,
                (oca + ocb) / 2,
                F(params['mya']) / F(params['myb'])]

    def wrappers(self):
        def full(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'Страны Альфа и Бета производят {} и {}; КПВ обеих '
                    u'линейны. За год Альфа может выпустить максимум {} ед. '
                    u'{} либо {} ед. {}, а Бета выпустит {} ед. {} либо '
                    u'{} ед. {}. Страны рассматривают специализацию '
                    u'и обмен.').format(
                        gx[0], gy[0], p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        def short(p, s):
            gx, gy = _ppf.PPF_GOODS[p['gx']], _ppf.PPF_GOODS[p['gy']]
            return (u'КПВ линейны. Альфа: {} ед. {} либо {} ед. {}; '
                    u'Бета: {} ед. {} либо {} ед. {}.').format(
                        p['mxa'], gx[1], p['mya'], gy[1],
                        p['mxb'], gx[1], p['myb'], gy[1])

        return [Wrapper('countries', full, short)]

    def solution(self, params, solved, asked):
        gx = _ppf.PPF_GOODS[params['gx']]
        gy = _ppf.PPF_GOODS[params['gy']]
        steps = [
            (u'Альтернативная стоимость 1 ед. {}: у Альфы ${}$, у Беты ${}$ '
             u'(в ед. {}).').format(
                gx[1], fmt_num(solved['oca'], latex=True),
                fmt_num(solved['ocb'], latex=True), gy[1]),
        ]
        if asked.key in ('adv_x', 'adv_y'):
            steps.append(
                (u'Сравнительное преимущество принадлежит тому, чья '
                 u'альтернативная стоимость ниже: в производстве {} '
                 u'это {}, в производстве {} это {}.').format(
                    gx[1], solved['adv_x'], gy[1], solved['adv_y']))
        else:
            steps.append(
                (u'Обмен взаимовыгоден, когда цена 1 ед. {} лежит между '
                 u'альтернативными стоимостями: от ${}$ до ${}$ ед. {}.').format(
                    gx[1], fmt_num(solved['price_low'], latex=True),
                    fmt_num(solved['price_high'], latex=True), gy[1]))
        return steps


ARCHETYPE = ComparativeAdvantageArchetype()
