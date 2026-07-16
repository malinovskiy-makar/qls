u"""
Архетип 10 (Блок Б): монополия со спросом P = a − bQ, MC = const и
постоянными издержками FC.

Экономика:
  MR = a − 2bQ = MC  →  Q_m = (a − MC)/(2b),  P_m = a − b·Q_m;
  наценка P_m − MC = b·Q_m  →  прибыль до постоянных издержек = b·Q_m²,
  прибыль π = b·Q_m² − FC;
  конкурентный выпуск Q_c = 2·Q_m;  DWL = ½·(P_m − MC)·(Q_c − Q_m) = b·Q_m²/2.

⚠️ FC появились при переработке под эталон (2026-07-16). Без них задача
вырождалась: «прибыль» совпадала с наценкой, а сюжету нечего было
объяснять. С FC в решении появляется настоящая мысль — постоянные
издержки НЕ влияют на выбор объёма (они не зависят от Q), но уменьшают
прибыль. Ради неё FC и добавлены.

Обратный ход: сэмплируется Q_m, a вычисляется; чётность b·Q_m²
гарантирует целый DWL; FC берётся заметно меньше b·Q_m², чтобы прибыль
осталась положительной и осмысленной.

Единицы во ВСЕХ сюжетах одни: P — руб. за штуку, Q — тыс. штук,
деньги — тыс. руб. Тогда P·Q сразу в тыс. руб. и переводить ничего не надо.

Контроль (эталон «Аквалайн», утверждён преподавателем 2026-07-16):
  Q = (120 − P)/2, MC = 20, FC = 100  ⇒  a = 120, b = 2;
  MR = 120 − 4Q = 20 ⇒ Q_m = 25 тыс. шт.; P_m = 70 руб.;
  π = 70·25 − (20·25 + 100) = 1750 − 600 = 1150 тыс. руб.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num
from . import _figure


def demand_q_form(a, b):
    u"""Спрос в «покупательской» записи Q = (a − P)/b.

    Так его и формулируют в условии («при цене P покупатели купят …»):
    человек выбирает количество, глядя на цену. Обратный спрос P = a − bQ
    появляется уже в решении — как первый шаг."""
    if F(b) == 1:
        return u'$Q = {} - P$'.format(fmt_num(a, latex=True))
    return u'$Q = ({} - P)/{}$'.format(fmt_num(a, latex=True),
                                       fmt_num(b, latex=True))


class Story(object):
    u"""Сюжет монополии: своя история, свой товар, своя причина монополии.

    У каждого сюжета СВОЙ текст абзаца (метод full), а не общий шаблон с
    подставленными словами: подстановка слов в один шаблон читается как
    подстановка слов в один шаблон. Общими остаются только числа."""

    def __init__(self, key, unit_q, full):
        self.key = key
        self.unit_q = unit_q      # «тыс. картриджей» — для текста условия
        self.full = full


def _aqualine(p):
    return (u'Фирма «Аквалайн» — единственный в городе N производитель '
            u'сменных картриджей для фильтров воды: патент на мембрану ещё '
            u'действует, конкурентов нет. Маркетологи оценили месячный '
            u'спрос: при цене $P$ руб. за штуку покупатели купят {} тыс. '
            u'картриджей в месяц. Картридж обходится в {} руб., содержание '
            u'цеха — ещё {} тыс. руб. в месяц. Директор максимизирует '
            u'прибыль.').format(demand_q_form(p['a'], p['b']), p['mc'], p['fc'])


def _pharma(p):
    return (u'Лаборатория «Ревиталь» — единственный в стране держатель '
            u'регистрационного удостоверения на редкий препарат, так что '
            u'больше его никто продавать не вправе. Отдел продаж выяснил: '
            u'при цене $P$ руб. за упаковку аптеки заберут {} тыс. упаковок '
            u'в месяц. Сырьё и розлив одной упаковки стоят {} руб., а '
            u'содержание стерильного цеха обходится в {} тыс. руб. в месяц '
            u'независимо от объёма выпуска.').format(
                demand_q_form(p['a'], p['b']), p['mc'], p['fc'])


def _monotown(p):
    return (u'Кирпичный завод «Гранит» — единственное производство '
            u'облицовочного кирпича в районе: ближайший конкурент за триста '
            u'километров, и везти оттуда дороже, чем купить у «Гранита». '
            u'Спрос застройщиков на его кирпич: при цене $P$ руб. за штуку '
            u'они купят {} тыс. штук за сезон. Каждый кирпич стоит заводу '
            u'{} руб., а печь надо топить и обслуживать круглый сезон — это '
            u'ещё {} тыс. руб.').format(
                demand_q_form(p['a'], p['b']), p['mc'], p['fc'])


def _airport(p):
    return (u'Кофейня «Гринвуд» выиграла конкурс и стала единственным '
            u'обладателем франшизы в аэропорту: других точек с кофе за '
            u'стойкой досмотра нет и по договору не будет. Замеры показали: '
            u'при цене $P$ руб. за стакан пассажиры возьмут {} тыс. стаканов '
            u'в месяц. Зерно, молоко и стакан обходятся в {} руб., аренда '
            u'места в терминале — {} тыс. руб. в месяц.').format(
                demand_q_form(p['a'], p['b']), p['mc'], p['fc'])


def _ferry(p):
    return (u'Паромная переправа «Затон» — единственный способ попасть на '
            u'остров: моста нет, и лицензию на перевозку выдали только ей. '
            u'Спрос дачников на билеты: при цене $P$ руб. за поездку они '
            u'купят {} тыс. поездок за лето. Топливо и работа команды на '
            u'одну поездку стоят {} руб., а содержание причала и парома — '
            u'{} тыс. руб. за сезон, сколько бы рейсов ни сделали.').format(
                demand_q_form(p['a'], p['b']), p['mc'], p['fc'])


STORIES = [
    Story('aqualine', u'тыс. картриджей', _aqualine),
    Story('pharma', u'тыс. упаковок', _pharma),
    Story('monotown', u'тыс. штук', _monotown),
    Story('airport', u'тыс. стаканов', _airport),
    Story('ferry', u'тыс. поездок', _ferry),
]

# Сетки. FC берём кратными 50 — «содержание цеха 137 тыс. руб.» выглядит
# как опечатка, а не как условие задачи.
Q_GRID = [10, 15, 20, 25, 30, 40, 50]
B_GRID = [1, 1, 2, 2, 2, 3, 4]
MC_GRID = list(range(10, 61, 5))
FC_GRID = [50, 100, 150, 200, 250, 300, 400, 500, 600, 800]


class MonopolyArchetype(Archetype):
    key = 'monopoly'
    title = u'Монополия (MR = MC)'
    block = u'Б. Фирма и издержки'
    topics = [u'Монополия и ценовая дискриминация']

    def sample(self, rng):
        for _ in range(200):
            q_m = rng.choice(Q_GRID)
            b = rng.choice(B_GRID)
            mc = rng.choice(MC_GRID)
            gross = b * q_m * q_m          # прибыль до постоянных издержек
            if gross % 2:                  # DWL = gross/2 должен быть целым
                continue
            # FC не больше 60 % «валовой» прибыли: иначе прибыль вырождается
            # в копейки и вопрос «максимальная прибыль» теряет смысл.
            fc_choices = [f for f in FC_GRID if f <= gross * Fraction(3, 5)]
            if not fc_choices:
                continue
            return {'a': mc + 2 * b * q_m, 'b': b, 'mc': mc,
                    'fc': rng.choice(fc_choices),
                    'story': rng.randrange(len(STORIES))}
        raise RuntimeError('monopoly: не сэмплировалась красивая монополия')

    def solve(self, params):
        a, b = F(params['a']), F(params['b'])
        mc, fc = F(params['mc']), F(params['fc'])
        q_m = (a - mc) / (2 * b)
        p_m = a - b * q_m
        revenue = p_m * q_m
        total_cost = mc * q_m + fc
        profit = revenue - total_cost
        q_c = (a - mc) / b
        dwl = (p_m - mc) * (q_c - q_m) / 2
        return {'q_m': q_m, 'p_m': p_m, 'revenue': revenue,
                'total_cost': total_cost, 'profit': profit,
                'q_c': q_c, 'dwl': dwl}

    def asked_values(self, params):
        u"""Спрашиваем РОВНО ОДНУ величину — какую, решает движок.

        Сложность проставлена явно, по экономической глубине: найти выпуск —
        один шаг MR = MC; прибыль — ещё и издержки с FC; потери общества —
        сравнение с конкурентным исходом."""
        return [
            Asked('q_m', nom=u'оптимальный месячный выпуск монополиста',
                  acc=u'оптимальный выпуск монополиста', gender='m',
                  unit=u'тыс. шт.', difficulty=3),
            Asked('p_m', nom=u'цена, которую назначит монополист',
                  acc=u'цену, которую назначит монополист', gender='f',
                  unit=u'руб.', difficulty=3),
            Asked('profit', nom=u'максимальная прибыль фирмы',
                  acc=u'максимальную прибыль фирмы', gender='f',
                  unit=u'тыс. руб.', difficulty=4),
            Asked('q_c', nom=(u'объём, который сложился бы при конкурентном '
                              u'ценообразовании ($P = MC$)'),
                  acc=(u'объём, который сложился бы при конкурентном '
                       u'ценообразовании ($P = MC$)'), gender='m',
                  unit=u'тыс. шт.', difficulty=4),
            Asked('dwl', nom=u'величина чистых потерь общества от монополии',
                  acc=u'величину чистых потерь общества от монополии',
                  gender='f', unit=u'тыс. руб.', difficulty=5),
        ]

    def error_variants(self, params, solved, asked):
        u"""Дистракторы — ВЫЧИСЛЕННЫЕ типовые ошибки, а не случайные числа."""
        a, b = F(params['a']), F(params['b'])
        mc, fc = F(params['mc']), F(params['fc'])
        q_m, p_m = solved['q_m'], solved['p_m']
        if asked.key == 'q_m':
            return [solved['q_c'],           # забыто удвоение наклона MR
                    a / (2 * b),             # потеряна MC
                    (a - mc) / 2,            # потерян наклон
                    a / b,
                    q_m / 2]
        if asked.key == 'p_m':
            return [mc,                      # цена = MC (конкурентная логика)
                    a,                       # цена спроса при Q = 0
                    q_m,                     # перепутаны P и Q
                    b * q_m,                 # наценка вместо цены
                    a - mc]
        if asked.key == 'profit':
            return [solved['profit'] + fc,   # ЗАБЫТЫ постоянные издержки
                    solved['revenue'],       # выручка вместо прибыли
                    solved['revenue'] - fc,  # забыты переменные издержки
                    solved['dwl'],
                    (a - mc) * q_m - fc]     # взята вся высота спроса
        if asked.key == 'q_c':
            return [q_m,                     # монопольный вместо конкурентного
                    a / b,                   # спрос при P = 0
                    (a + mc) / (2 * b),
                    3 * q_m]
        # dwl
        return [solved['profit'],            # прибыль вместо DWL
                2 * solved['dwl'],           # забыта 1/2
                solved['revenue'] / 2,
                (a - mc) * q_m / 2,
                solved['q_c']]

    def wrappers(self):
        u"""Один Wrapper, который разворачивает сюжет из params['story'].

        ⚠️ Почему не список из пяти Wrapper'ов: движок выбирает обёртку
        ПОСЛЕ того, как выбрал спрашиваемую величину и её единицы. Если бы
        сюжет выбирался там же, единица в вопросе («тыс. упаковок») могла
        бы приехать из одного сюжета, а текст — из другого. Сюжет выбран
        в sample() — значит, условие и вопрос заведомо об одном и том же."""
        def full(p, s):
            return STORIES[p['story']].full(p)

        def short(p, s):
            return (u'Монополист: спрос {} (тыс. шт.), предельные издержки '
                    u'{} руб., постоянные — {} тыс. руб.').format(
                        demand_q_form(p['a'], p['b']), p['mc'], p['fc'])

        return [Wrapper('story', full, short)]

    def solution(self, params, solved, asked):
        u"""Полное решение: с рассуждением «почему так», шагами и смыслом."""
        a, b = params['a'], params['b']
        mc, fc = params['mc'], params['fc']
        q_m, p_m = solved['q_m'], solved['p_m']
        # Коэффициент 1 не пишем: «$80Q - 1Q^2$» и «$80 - 1 \cdot 20$» —
        # мелочь, которая сразу выдаёт машинную подстановку.
        bq = u'' if F(b) == 1 else fmt_num(b, latex=True)
        b_dot_q = fmt_num(q_m, latex=True) if F(b) == 1 else \
            u'{} \\cdot {}'.format(fmt_num(b, latex=True),
                                   fmt_num(q_m, latex=True))
        steps = [
            u'Перейдём от спроса к обратному спросу — выразим цену через '
            u'количество: {} $\\Rightarrow P = {} - {}Q$. Так видно, на '
            u'сколько падает цена от каждой лишней проданной единицы.'.format(
                demand_q_form(a, b), fmt_num(a, latex=True), bq),
            u'Выручка: $TR = P \\cdot Q = ({} - {}Q)Q = {}Q - {}Q^2$, '
            u'отсюда предельная выручка $MR = {} - {}Q$. У линейного спроса '
            u'$MR$ падает вдвое круче спроса: продав лишнюю единицу, '
            u'монополист вынужден снизить цену и на всех прежних.'.format(
                fmt_num(a, latex=True), bq, fmt_num(a, latex=True),
                bq, fmt_num(a, latex=True),
                fmt_num(2 * F(b), latex=True)),
            u'Монополист наращивает выпуск, пока лишняя единица приносит '
            u'выручки больше, чем стоит, и останавливается при $MR = MC$: '
            u'${} - {}Q = {} \\Rightarrow Q_m = {}$ тыс. шт.'.format(
                fmt_num(a, latex=True), fmt_num(2 * F(b), latex=True), mc,
                fmt_num(q_m, latex=True)),
        ]
        if asked.key in ('p_m', 'profit', 'dwl'):
            steps.append(
                u'Цену берём с кривой спроса — это максимум, который '
                u'покупатели готовы платить за такой объём: '
                u'$P_m = {} - {} = {}$ руб.'.format(
                    fmt_num(a, latex=True), b_dot_q, fmt_num(p_m, latex=True)))
        if asked.key == 'profit':
            steps.append(
                u'Прибыль: $\\pi = TR - TC = {} \\cdot {} - ({} \\cdot {} + '
                u'{}) = {} - {} = {}$ тыс. руб.'.format(
                    fmt_num(p_m, latex=True), fmt_num(q_m, latex=True),
                    mc, fmt_num(q_m, latex=True), fc,
                    fmt_num(solved['revenue'], latex=True),
                    fmt_num(solved['total_cost'], latex=True),
                    fmt_num(solved['profit'], latex=True)))
            steps.append(
                u'Обратите внимание: постоянные издержки ({} тыс. руб.) на '
                u'выбор объёма НЕ влияли — они не зависят от $Q$, и в '
                u'условии $MR = MC$ их нет. Но прибыль они уменьшают: '
                u'фирма зарабатывает {} тыс. руб. в месяц.'.format(
                    fc, fmt_num(solved['profit'], latex=True)))
        if asked.key in ('q_c', 'dwl'):
            steps.append(
                u'При конкуренции цена опустилась бы до предельных издержек '
                u'($P = MC$): ${} - {}Q = {} \\Rightarrow Q_c = {}$ тыс. шт. '
                u'— вдвое больше монопольного выпуска.'.format(
                    fmt_num(a, latex=True), bq, mc,
                    fmt_num(solved['q_c'], latex=True)))
        if asked.key == 'dwl':
            steps.append(
                u'Чистые потери — треугольник между спросом и $MC$ на '
                u'непроизведённых единицах от $Q_m$ до $Q_c$: эти сделки '
                u'были выгодны обеим сторонам, но не состоялись. '
                u'$DWL = \\frac{{1}}{{2}}(P_m - MC)(Q_c - Q_m) = '
                u'\\frac{{1}}{{2}} \\cdot {} \\cdot {} = {}$ тыс. руб.'.format(
                    fmt_num(p_m - F(mc), latex=True),
                    fmt_num(solved['q_c'] - q_m, latex=True),
                    fmt_num(solved['dwl'], latex=True)))
        return steps

    def figure(self, params, solved, asked):
        u"""Чертёж монополии: спрос, MR, MC, обе точки, излишек и потери."""
        a, b = F(params['a']), F(params['b'])
        mc = F(params['mc'])
        q_m, p_m, q_c = solved['q_m'], solved['p_m'], solved['q_c']
        xmax = _figure.axis_max(a / b)        # спрос упирается в ось Q
        ymax = _figure.axis_max(a)
        return _figure.figure(
            'monopoly', xmax, ymax, u'Q, тыс. шт.', u'P, руб.',
            lines=[
                _figure.line('d', 'D', (0, a), (a / b, 0)),
                _figure.line('mr', 'MR', (0, a), (a / (2 * b), 0)),
                _figure.line('mc', 'MC', (0, mc), (xmax, mc)),
                # вспомогательные — «читаем» оптимум с осей
                _figure.line('ghost', '', (0, p_m), (q_m, p_m), dash=True),
                _figure.line('ghost', '', (q_m, 0), (q_m, p_m), dash=True),
            ],
            areas=[
                _figure.area('cs', [(0, a), (0, p_m), (q_m, p_m)],
                             u'Излишек потребителей'),
                _figure.area('dwl', [(q_m, p_m), (q_c, mc), (q_m, mc)],
                             'DWL'),
            ],
            points=[
                _figure.point(q_m, p_m, 'M', 'd'),
                _figure.point(q_c, mc, 'C', 'mc'),
            ],
            marks=[
                _figure.mark('x', q_m, 'Q_m'),
                _figure.mark('x', q_c, 'Q_c'),
                _figure.mark('y', p_m, 'P_m'),
                _figure.mark('y', mc, 'MC'),
            ])


ARCHETYPE = MonopolyArchetype()
