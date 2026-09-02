"""
Общий помощник Блока А: линейный рынок Qd = a − bP, Qs = c + dP.

Обратный ход: сэмплируются красивые P*, Q* и наклоны, свободные члены
вычисляются (a = Q* + b·P*, c = Q* − d·P*; c может быть < 0 — это валидно,
пока равновесие в первой четверти). Всё целые → равновесие красиво
по построению.

Здесь же — сюжетный словарь (товары в нужных падежах) и сборщики текста
базовой декорации, которые переиспользуют все архетипы Блока А.
"""
from fractions import Fraction

from .base import F, fmt_num, linear_eq

# Сетки красивых опорных величин.
P_GRID = list(range(10, 101, 5))          # P* — равновесная цена
Q_GRID = list(range(20, 201, 10))         # Q* — равновесный объём
# Наклоны: маленькие чаще (реалистичнее выглядят в тексте).
SLOPES = [1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5]

# Товары: [0] родительный («на рынке …»), [1] винительный («спрос на …»).
GOODS = [
    (u'яблок', u'яблоки'),
    (u'велосипедов', u'велосипеды'),
    (u'керамических кружек', u'керамические кружки'),
    (u'сыра', u'сыр'),
    (u'мёда', u'мёд'),
    (u'тюльпанов', u'тюльпаны'),
    (u'зонтов', u'зонты'),
    (u'настольных ламп', u'настольные лампы'),
    (u'футболок', u'футболки'),
    (u'кофе в зёрнах', u'кофе в зёрнах'),
]

WHERE_PQ = u'где цена $P$ задана в ден. ед., а количество $Q$ в шт.'


def sample_market(rng, p_grid=None, q_grid=None, slopes=None):
    """Рынок с красивым равновесием. Возвращает params-словарь (все int)."""
    p_star = rng.choice(p_grid or P_GRID)
    q_star = rng.choice(q_grid or Q_GRID)
    b = rng.choice(slopes or SLOPES)
    d = rng.choice(slopes or SLOPES)
    return {
        'a': q_star + b * p_star,
        'b': b,
        'c': q_star - d * p_star,
        'd': d,
        'good': rng.randrange(len(GOODS)),
    }


def solve_market(params):
    """Равновесие: P* = (a−c)/(b+d), Q* = a − b·P*. Всегда Fraction."""
    a, b, c, d = F(params['a']), F(params['b']), F(params['c']), F(params['d'])
    p_star = (a - c) / (b + d)
    q_star = a - b * p_star
    return p_star, q_star


def demand_eq(params, head='Q_d'):
    return linear_eq(head, params['a'], -F(params['b']))


def supply_eq(params, head='Q_s'):
    return linear_eq(head, params['c'], F(params['d']))


def setup_full(params, solved=None):
    """Развёрнутая декорация рынка (для numeric): сюжет + функции + расшифровка."""
    good = GOODS[params['good']]
    return (u'На рынке {} в городе N спрос и предложение заданы функциями '
            u'{} и {}, {}.').format(
                good[0], demand_eq(params), supply_eq(params), WHERE_PQ)


def setup_full_country(params, solved=None):
    good = GOODS[params['good']]
    return (u'В стране Альфа спрос на {} описывается уравнением {}, '
            u'а предложение уравнением {} (цена $P$ в ден. ед., '
            u'количество $Q$ в шт.).').format(
                good[1], demand_eq(params), supply_eq(params))


def setup_full_analysts(params, solved=None):
    good = GOODS[params['good']]
    return (u'Аналитики изучают рынок {}. По их оценкам, спрос и предложение '
            u'имеют вид {} и {}, {}.').format(
                good[0], demand_eq(params), supply_eq(params), WHERE_PQ)


def setup_short(params, solved=None):
    """Сжатая декорация (для single/boolean): только функции."""
    return (u'На рынке {}: спрос {}, предложение {} ($P$ в ден. ед., '
            u'$Q$ в шт.).').format(
                GOODS[params['good']][0], demand_eq(params), supply_eq(params))


def setup_short_bare(params, solved=None):
    return u'Спрос: {}, предложение: {} ($P$ в ден. ед., $Q$ в шт.).'.format(
        demand_eq(params), supply_eq(params))


def eq_solution_steps(params, p_star, q_star, with_q=True):
    """Общие шаги «найти равновесие» для решений архетипов Блока А."""
    from .base import linear_rhs
    steps = [
        u'В равновесии $Q_d = Q_s$: ${} = {}$.'.format(
            linear_rhs(params['a'], -F(params['b'])),
            linear_rhs(params['c'], F(params['d']))),
        u'Отсюда $P^* = {}$ ден. ед.'.format(fmt_num(p_star, latex=True)),
    ]
    if with_q:
        b = F(params['b'])
        b_part = fmt_num(p_star, latex=True) if b == 1 else \
            u'{} \\cdot {}'.format(fmt_num(b, latex=True),
                                   fmt_num(p_star, latex=True))
        steps.append(u'Подставим в спрос: $Q^* = {} - {} = {}$ шт.'.format(
            fmt_num(params['a'], latex=True), b_part,
            fmt_num(q_star, latex=True)))
    return steps
