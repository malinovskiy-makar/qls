"""
Бонус-архетип 16: индекс цен фиксированной корзины из двух товаров.

Индекс = 100·(стоимость корзины в новых ценах)/(в старых), инфляция =
индекс − 100. Обратный ход: сначала тянется красивая инфляция и стоимость
старой корзины, цены подбираются под неё.

Контроль: (10 шт: 4→6) + (5 шт: 8→8) → индекс 125 %, инфляция 25 %.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _market


class PriceIndexArchetype(Archetype):
    key = 'price_index'
    title = u'Индекс цен корзины'
    block = u'Г. Макро-лайт'
    topics = [u'Инфляция и безработица']

    def sample(self, rng):
        for _ in range(400):
            n1 = rng.choice([2, 4, 5, 10, 20])
            n2 = rng.choice([2, 4, 5, 10])
            p1_0 = rng.choice([2, 4, 5, 6, 8, 10, 12])
            p2_0 = rng.choice([2, 4, 5, 6, 8, 10, 12])
            cost0 = n1 * p1_0 + n2 * p2_0
            infl = rng.choice([5, 10, 20, 25, 40, 50, 75, 100])
            cost1 = Fraction(cost0 * (100 + infl), 100)
            if cost1.denominator != 1:
                continue
            # цена второго товара меняется на небольшой шаг (или замирает),
            # первый товар добирает остаток стоимости корзины
            d2 = rng.choice([-2, -1, 0, 0, 1, 2, 3, 4])
            p2_1 = p2_0 + d2
            if p2_1 <= 0:
                continue
            p1_1 = Fraction(int(cost1) - n2 * p2_1, n1)
            if p1_1.denominator != 1 or p1_1 <= 0 or p1_1 == p1_0:
                continue
            g1 = rng.randrange(len(_market.GOODS))
            i2 = rng.randrange(len(_market.GOODS) - 1)
            return {'n1': n1, 'n2': n2,
                    'p1_0': p1_0, 'p1_1': int(p1_1),
                    'p2_0': p2_0, 'p2_1': p2_1,
                    'g1': g1,
                    'g2': i2 if i2 < g1 else i2 + 1}
        raise RuntimeError('price_index: не сэмплировалась красивая корзина')

    def solve(self, params):
        n1, n2 = F(params['n1']), F(params['n2'])
        cost0 = n1 * F(params['p1_0']) + n2 * F(params['p2_0'])
        cost1 = n1 * F(params['p1_1']) + n2 * F(params['p2_1'])
        index = 100 * cost1 / cost0
        return {'cost0': cost0, 'cost1': cost1,
                'index': index, 'inflation': index - 100}

    def asked_values(self, params):
        return [
            Asked('index', nom=u'значение индекса цен корзины (в %)',
                  acc=u'значение индекса цен корзины (в %)', gender='n',
                  unit='%'),
            Asked('inflation',
                  nom=u'темп инфляции по этой корзине (в %)',
                  acc=u'темп инфляции по этой корзине (в %)', gender='m',
                  unit='%'),
            Asked('cost1', nom=u'стоимость корзины в новых ценах',
                  acc=u'стоимость корзины в новых ценах', gender='f',
                  unit=u'ден. ед.'),
        ]

    def error_variants(self, params, solved, asked):
        p1_0, p1_1 = F(params['p1_0']), F(params['p1_1'])
        p2_0, p2_1 = F(params['p2_0']), F(params['p2_1'])
        # классика ошибок: невзвешенное среднее относительных цен
        unweighted = 100 * (p1_1 / p1_0 + p2_1 / p2_0) / 2
        if asked.key == 'index':
            return [solved['inflation'],       # индекс спутан с инфляцией
                    unweighted,                # веса корзины потеряны
                    100 * solved['cost0'] / solved['cost1'],  # перевёрнуто
                    100 * p1_1 / p1_0,         # только первый товар
                    100 * p2_1 / p2_0]
        if asked.key == 'inflation':
            return [solved['index'],           # инфляция спутана с индексом
                    unweighted - 100,
                    100 * (p1_1 - p1_0) / p1_0,
                    100 * (p2_1 - p2_0) / p2_0,
                    solved['cost1'] - solved['cost0']]  # прирост в ден. ед.
        # cost1
        return [solved['cost0'],
                solved['cost1'] - solved['cost0'],
                F(params['n1']) * p1_1,
                F(params['n2']) * p2_1,
                p1_1 + p2_1]

    def wrappers(self):
        def basket(p):
            g1 = _market.GOODS[p['g1']][0]
            g2 = _market.GOODS[p['g2']][0]
            return (u'{} ед. {} и {} ед. {}. Цена единицы {} выросла с {} до '
                    u'{} ден. ед., а цена единицы {} изменилась с {} до {} '
                    u'ден. ед.').format(
                        p['n1'], g1, p['n2'], g2, g1, p['p1_0'], p['p1_1'],
                        g2, p['p2_0'], p['p2_1'])

        def full(p, s):
            return (u'Статистики города N считают индекс цен по фиксированной '
                    u'потребительской корзине: {}').format(basket(p))

        def full_family(p, s):
            return (u'Семья ведёт домашнюю бухгалтерию и каждый месяц '
                    u'покупает один и тот же набор: {} Набор не меняется '
                    u'намеренно: иначе непонятно, подорожала жизнь или '
                    u'просто стали покупать другое.').format(basket(p))

        def full_canteen(p, s):
            return (u'Школьная столовая закупает продукты по неизменной '
                    u'раскладке: {} Директор считает, на сколько подорожал '
                    u'обед, чтобы объяснить это родителям.').format(basket(p))

        def full_pension(p, s):
            return (u'Пенсионный фонд считает, на сколько поднять выплаты. '
                    u'В расчёт берут неизменную корзину: {} Индексация '
                    u'привязана к её подорожанию.').format(basket(p))

        def full_plant(p, s):
            return (u'Снабженец завода закупает материалы одним и тем же '
                    u'списком: {} Ему нужно понять, насколько выросла '
                    u'стоимость закупки.').format(basket(p))

        def short(p, s):
            return u'Корзина: {}'.format(basket(p))

        def short_family(p, s):
            return u'Домашняя корзина: {}'.format(basket(p))

        def short_canteen(p, s):
            return u'Закупка столовой: {}'.format(basket(p))

        def short_pension(p, s):
            return u'Корзина для индексации: {}'.format(basket(p))

        def short_plant(p, s):
            return u'Список снабженца: {}'.format(basket(p))

        return [Wrapper('basket', full, short),
                Wrapper('family', full_family, short_family),
                Wrapper('canteen', full_canteen, short_canteen),
                Wrapper('pension', full_pension, short_pension),
                Wrapper('plant', full_plant, short_plant)]

    def solution(self, params, solved, asked):
        steps = [
            u'Корзина в старых ценах: ${} \\cdot {} + {} \\cdot {} = {}$ ден. ед.'.format(
                params['n1'], params['p1_0'], params['n2'], params['p2_0'],
                fmt_num(solved['cost0'], latex=True)),
            u'Корзина в новых ценах: ${} \\cdot {} + {} \\cdot {} = {}$ ден. ед.'.format(
                params['n1'], params['p1_1'], params['n2'], params['p2_1'],
                fmt_num(solved['cost1'], latex=True)),
        ]
        if asked.key != 'cost1':
            steps.append(
                u'Индекс цен: $100 \\cdot {} / {} = {}\\,\\%$; '
                u'инфляция: ${} - 100 = {}\\,\\%$.'.format(
                    fmt_num(solved['cost1'], latex=True),
                    fmt_num(solved['cost0'], latex=True),
                    fmt_num(solved['index'], latex=True),
                    fmt_num(solved['index'], latex=True),
                    fmt_num(solved['inflation'], latex=True)))
        return steps


ARCHETYPE = PriceIndexArchetype()
