u"""
Архетип 1 (Блок А): равновесие на линейном рынке — найти P* или Q*.

Экономика: Q_d = a − bP, Q_s = c + dP; в равновесии Q_d = Q_s ⇒
P* = (a − c)/(b + d), Q* = a − bP*. Свободный член предложения c может быть
отрицательным — это нормально (при низкой цене везти товар невыгодно, и
предложение начинается не с нуля), лишь бы равновесие было в первой четверти;
за этим следит _market.sample_market.

⚠️ Сюжеты у архетипа СВОИ (переработка под эталон 2026-07-16), а не общие
из _market: там короткие декорации на весь Блок А, и их всё ещё используют
непеределанные архетипы. Трогать их — значит менять пять архетипов разом,
не переработав ни одного как следует.

Единицы: P — руб. за штуку, Q — штуки (за период сюжета).

Контроль: Qd = 100 − P, Qs = P → P* = 50, Q* = 50.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_rhs
from . import _figure, _market


def demand_eq(p):
    return u'$Q_d = {}$'.format(linear_rhs(p['a'], -F(p['b'])))


def supply_eq(p):
    return u'$Q_s = {}$'.format(linear_rhs(p['c'], F(p['d'])))


class Story(object):
    u"""Сюжет рынка: кто покупает, кто продаёт и почему кривые такие.

    У каждого сюжета свой текст: подстановка слов в один шаблон читается
    как подстановка слов в один шаблон.

    unit_q — единица количества ИМЕННО этого сюжета. Кофе меряют в
    килограммах, и «равновесный объём 190 шт.» под рассказом про кофе в
    зёрнах — та самая небрежность, из-за которой задаче не место на сайте.
    Форма выбрана так, чтобы вставать в оборот «(в …)»: «в шт.», «в кг».

    good_gen — товар в родительном падеже для СЖАТОЙ формы («на рынке
    мёда»). Раньше сжатую форму собирал _market.setup_short, и товар он брал
    из params['good'] — независимо от сюжета. Выходило «На рынке зонтов
    ($Q$ — в шт.)» там, где спрашивали про кофе в кг."""

    def __init__(self, key, good_gen, unit_q, full):
        self.key = key
        self.good_gen = good_gen
        self.unit_q = unit_q
        self.full = full


def _honey(p):
    return (u'Каждую субботу в городе N работает фермерский рынок мёда. '
            u'Пасечники из окрестных сёл везут мёд тем охотнее, чем выше '
            u'цена: при цене $P$ руб. за банку они выставят на прилавки '
            u'{} банок. Покупатели ведут себя наоборот, ведь чем дороже, '
            u'тем меньше берут: {}. К вечеру рынок нащупывает цену, при которой '
            u'мёд не остаётся на прилавках, но и очереди не '
            u'выстраиваются.').format(supply_eq(p), demand_eq(p))


def _bikes(p):
    return (u'В городе N открылся сезон проката велосипедов, и несколько '
            u'фирм выставили их на продажу. Чем выше цена, тем больше фирмы '
            u'готовы привезти: {} велосипедов при цене $P$ руб. за штуку. '
            u'Горожане, напротив, при высокой цене чаще выбирают автобус: '
            u'{}. Пока цена не та, кто-то остаётся без велосипеда, '
            u'а кто-то с непроданным складом.').format(
                supply_eq(p), demand_eq(p))


def _tulips(p):
    return (u'Перед 8 Марта на цветочном рынке города N торгуют тюльпанами. '
            u'Оптовики завозят их из теплиц: при цене $P$ руб. за букет '
            u'предложение составит {} букетов. Спрос горожан к празднику '
            u'известен по прошлым годам: {}. Цветы быстро портятся, '
            u'поэтому продавцы быстро сходятся на цене, при которой к концу '
            u'дня не остаётся ни лишних букетов, ни '
            u'неудовлетворённых покупателей.').format(
                supply_eq(p), demand_eq(p))


def _mugs(p):
    return (u'На ярмарке в городе N продают керамические кружки ручной '
            u'работы. Мастерские берутся за них тем охотнее, чем выше цена: '
            u'{} кружек при цене $P$ руб. за штуку. Посетители ярмарки '
            u'реагируют на цену обратным образом: {}. Организаторы хотят '
            u'заранее понять, на какой цене рынок успокоится, то есть при '
            u'какой цене желающих купить будет ровно столько же, сколько '
            u'кружек привезут.').format(supply_eq(p), demand_eq(p))


def _coffee(p):
    return (u'Аналитики изучают городской рынок кофе в зёрнах. Обжарщики '
            u'наращивают поставки вслед за ценой: при цене $P$ руб. за '
            u'килограмм рынку предложат {} кг. Кофейни и жители при росте '
            u'цены закупают меньше: {}. Аналитиков интересует состояние, в '
            u'котором рынок не имеет причин двигаться: ни излишка, ни '
            u'дефицита.').format(supply_eq(p), demand_eq(p))


STORIES = [
    Story('honey', u'мёда', u'шт.', _honey),
    Story('bikes', u'велосипедов', u'шт.', _bikes),
    Story('tulips', u'тюльпанов', u'шт.', _tulips),
    Story('mugs', u'керамических кружек', u'шт.', _mugs),
    Story('coffee', u'кофе в зёрнах', u'кг', _coffee),
]


def setup_short(p, solved=None):
    u"""Сжатая декорация ЭТОГО архетипа: сюжетный товар и его единицы.

    ⚠️ Не _market.setup_short. Тот пишет «$P$ — в ден. ед., $Q$ — в шт.», а
    здесь цену спрашивают «(в руб.)» (Asked.unit) и количество — в единице
    сюжета. Замер по базе нашёл 45 вопросов, где условие говорило «ден. ед.»,
    а вопрос — «в руб.»; общий помощник остальным архетипам Блока А подходит,
    им и остаётся."""
    return (u'На рынке {}: спрос {}, предложение {} '
            u'($P$ в руб., $Q$ в {}).').format(
                STORIES[p['story']].good_gen, demand_eq(p), supply_eq(p),
                STORIES[p['story']].unit_q)


class EquilibriumArchetype(Archetype):
    key = 'equilibrium'
    title = u'Равновесие на рынке'
    block = u'А. Рынок'
    topics = [u'Спрос и предложение']

    def sample(self, rng):
        params = _market.sample_market(rng)
        params['story'] = rng.randrange(len(STORIES))
        return params

    def solve(self, params):
        p_star, q_star = _market.solve_market(params)
        return {'p_star': p_star, 'q_star': q_star}

    def asked_values(self, params):
        # Единица количества — из сюжета (кофе в кг, кружки в шт.).
        unit_q = STORIES[params['story']].unit_q
        return [
            Asked('p_star', nom=u'равновесная цена', acc=u'равновесную цену',
                  gender='f', unit=u'руб.', difficulty=2),
            Asked('q_star', nom=u'равновесный объём продаж',
                  acc=u'равновесный объём продаж', gender='m',
                  unit=unit_q, difficulty=3),
        ]

    def error_variants(self, params, solved, asked):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        p_star, q_star = solved['p_star'], solved['q_star']
        p_sign_err = (a + c) / (b + d)          # знак c потерян
        if asked.key == 'p_star':
            errs = [
                p_sign_err,
                q_star,                          # перепутаны P и Q
                (a - c) / b,                     # наклон предложения потерян
                (a - c) / d,                     # наклон спроса потерян
                a / b,                           # цена спроса при Q = 0
            ]
            if b != d:
                errs.append((a - c) / (b - d))   # наклоны вычтены, а не сложены
            return errs
        return [
            p_star,                              # перепутаны P и Q
            a - b * p_sign_err,                  # спрос в ошибочной цене
            c + d * p_sign_err,                  # предложение в ошибочной цене
            a,                                   # спрос при P = 0
            (a + c) / 2,                         # среднее свободных членов
        ]

    def wrappers(self):
        u"""Один Wrapper, разворачивающий сюжет из params['story'] —
        сюжет выбран в sample(), поэтому условие и вопрос об одном и том же
        (см. подробнее в monopoly.py)."""
        def full(p, s):
            return STORIES[p['story']].full(p)

        return [Wrapper('story', full, setup_short)]

    def solution(self, params, solved, asked):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        p_star, q_star = solved['p_star'], solved['q_star']
        unit_q = STORIES[params['story']].unit_q
        steps = [
            u'Равновесной называют цену, при которой рынку не с чего двигаться: '
            u'все, кто готов купить по этой цене, находят продавца, и '
            u'наоборот. Значит, $Q_d = Q_s$: ${} = {}$.'.format(
                linear_rhs(params['a'], -b), linear_rhs(params['c'], d)),
            u'Соберём $P$ в одной части: ${} = {}P \\Rightarrow P^* = {}$ '
            u'руб.'.format(fmt_num(a - c, latex=True),
                           fmt_num(b + d, latex=True),
                           fmt_num(p_star, latex=True)),
        ]
        if asked.key == 'q_star':
            b_part = fmt_num(p_star, latex=True) if b == 1 else \
                u'{} \\cdot {}'.format(fmt_num(b, latex=True),
                                       fmt_num(p_star, latex=True))
            d_part = fmt_num(p_star, latex=True) if d == 1 else \
                u'{} \\cdot {}'.format(fmt_num(d, latex=True),
                                       fmt_num(p_star, latex=True))
            steps.append(
                u'Подставим равновесную цену в спрос: $Q^* = {} - {} = {}$ '
                u'{}'.format(fmt_num(a, latex=True), b_part,
                             fmt_num(q_star, latex=True), unit_q))
            steps.append(
                u'Проверим по предложению: в равновесии обе функции обязаны '
                u'дать одно и то же, ${} + {} = {}$ {} Сходится.'.format(
                    fmt_num(c, latex=True), d_part,
                    fmt_num(q_star, latex=True), unit_q))
        else:
            steps.append(
                u'При этой цене рынок расчищается: и спрос, и предложение '
                u'дают $Q^* = {}$ {}, так что нет ни дефицита, ни излишка.'.format(
                    fmt_num(q_star, latex=True), unit_q))
        return steps

    def figure(self, params, solved, asked):
        u"""Крест Маршалла: спрос, предложение, точка равновесия.

        Рамку строим вокруг равновесия (вдвое шире), а не по всей длине
        кривых: спрос может уходить к $P = 280$, но интересно то, что рядом
        с P*. Кривые обрезаем по рамке (_figure.clip_linear)."""
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        p_star, q_star = solved['p_star'], solved['q_star']
        xmax = _figure.axis_max(q_star * 2)
        ymax = _figure.axis_max(p_star * 2)
        # В осях (Q, P): спрос P = (a − Q)/b, предложение P = (Q − c)/d
        d_seg = _figure.clip_linear(-Fraction(1, 1) / b, a / b, xmax, ymax)
        s_seg = _figure.clip_linear(Fraction(1, 1) / d, -c / d, xmax, ymax)
        lines = []
        if d_seg:
            lines.append(_figure.line('d', 'D', d_seg[0], d_seg[1]))
        if s_seg:
            lines.append(_figure.line('s', 'S', s_seg[0], s_seg[1]))
        lines.append(_figure.line('ghost', '', (0, p_star), (q_star, p_star),
                                  dash=True))
        lines.append(_figure.line('ghost', '', (q_star, 0), (q_star, p_star),
                                  dash=True))
        return _figure.figure(
            'equilibrium', xmax, ymax,
            u'Q, {}'.format(STORIES[params['story']].unit_q), u'P, руб.',
            lines=lines,
            points=[_figure.point(q_star, p_star, 'E', 'd')],
            marks=[_figure.mark('x', q_star, 'Q^*'),
                   _figure.mark('y', p_star, 'P^*')])


ARCHETYPE = EquilibriumArchetype()
