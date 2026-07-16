u"""
Архетип 3 (Блок А): потоварный налог t или субсидия s на линейном рынке.

Экономика. Налог платят продавцы, поэтому цена покупателя и цена продавца
расходятся: P_s = P_b − t. Предложение зависит от того, сколько ОСТАЁТСЯ
продавцу: Q_s = c + d(P_b − t), спрос по-прежнему от P_b. Отсюда
  P_b = (a − c + d·t)/(b + d),  P_s = P_b − t,  Q_1 = a − b·P_b.
Субсидия — тот же ход с обратным знаком: P_s = P_b + s, P_b = (a − c − d·s)/(b + d).
Бремя делится по наклонам: доля покупателей = d/(b + d) — кто менее чуток
к цене, тот и платит.

Обратный ход: ставка кратна (b + d) → цены сдвигаются на целые k·d и k·b,
ΔQ = k·b·d целое; чётность DWL = t·ΔQ/2 проверяется при сэмплировании.

⚠️ Сюжет задаёт ВИД вмешательства (params['kind'] берётся из сюжета, а не
сэмплируется отдельно): налог на сладкую газировку и субсидия фермерам —
разные истории, и «субсидия на газировку ради борьбы с ожирением» была бы
бессмыслицей. Раньше kind сэмплировался независимо от декорации.

Единицы: P — руб. за штуку, Q — тыс. штук, деньги — тыс. руб.
(тогда ставка × объём сразу в тыс. руб.).

Контроль (Qd = 100 − P, Qs = P, t = 20): Pb = 60, Ps = 40, Q = 40,
бюджет = 800, DWL = 100, доля покупателей = 50 %.
Субсидия s = 20 на той же базе: Q = 60, расходы бюджета = 1200, DWL = 100.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_rhs
from . import _figure, _market


def demand_eq(p):
    return u'$Q_d = {}$'.format(linear_rhs(p['a'], -F(p['b'])))


def supply_eq(p):
    return u'$Q_s = {}$'.format(linear_rhs(p['c'], F(p['d'])))


class Story(object):
    u"""Сюжет вмешательства: рынок, повод государства и единицы.

    kind — 'tax' или 'subsidy': вид вмешательства неотделим от истории.
    unit_q — единица количества этого сюжета (тыс. бутылок, тыс. литров).
    У каждого сюжета свой текст абзаца, а не общий шаблон."""

    def __init__(self, key, kind, unit_q, full, short_setup):
        self.key = key
        self.kind = kind
        self.unit_q = unit_q
        self.full = full
        self.short_setup = short_setup


# --- налоги -----------------------------------------------------------------

def _soda(p):
    return (u'В стране Альфа обсуждают, как сократить потребление сладкой '
            u'газировки: врачи связывают его с ростом детского ожирения. До '
            u'реформы рынок жил обычной жизнью — спрос {} и предложение {} '
            u'(в тыс. бутылок, $P$ — цена в руб. за бутылку). С нового года '
            u'ввели потоварный налог {} руб. с каждой проданной бутылки, '
            u'платят его производители.').format(
                demand_eq(p), supply_eq(p), p['rate'])


def _bags(p):
    return (u'Городские власти N борются с пластиковым мусором: пакеты '
            u'разлагаются веками, а свалка у города переполнена. Спрос '
            u'магазинов на пакеты {} и предложение заводов {} (в тыс. штук, '
            u'$P$ — цена в руб. за пакет). Совет города ввёл экологический '
            u'сбор {} руб. с каждого проданного пакета — платят его '
            u'производители.').format(demand_eq(p), supply_eq(p), p['rate'])


def _energy(p):
    return (u'Депутаты решили ограничить продажу энергетических напитков '
            u'подросткам и заодно пополнить бюджет: спрос на них рос '
            u'быстрее, чем успевали спорить о вреде. Рынок описывался '
            u'функциями {} и {} (в тыс. банок, $P$ — цена в руб. за банку). '
            u'С июля введён акциз {} руб. с каждой проданной банки, который '
            u'перечисляют производители.').format(
                demand_eq(p), supply_eq(p), p['rate'])


# --- субсидии ---------------------------------------------------------------

def _milk(p):
    return (u'В регионе N фермеры жалуются: молоко продаётся дешевле, чем '
            u'обходится содержание стада, и хозяйства закрываются. Спрос '
            u'переработчиков {} и предложение ферм {} (в тыс. литров, $P$ — '
            u'цена в руб. за литр). Чтобы удержать хозяйства, область ввела '
            u'субсидию {} руб. за каждый проданный литр — её получают '
            u'фермеры.').format(demand_eq(p), supply_eq(p), p['rate'])


def _trains(p):
    return (u'Пригородные электрички в области N возят дачников себе в '
            u'убыток, и перевозчик грозит отменить часть рейсов. Спрос '
            u'пассажиров на билеты {} и предложение перевозчика {} (в тыс. '
            u'поездок, $P$ — цена билета в руб.). Область назначила '
            u'перевозчику субсидию {} руб. за каждую проданную поездку.').format(
                demand_eq(p), supply_eq(p), p['rate'])


def _saplings(p):
    return (u'Город N задумал озеленение: деревьев нужно много, а питомники '
            u'выращивать саженцы не спешат — слишком долго ждать выручки. '
            u'Спрос на саженцы {} и предложение питомников {} (в тыс. штук, '
            u'$P$ — цена в руб. за саженец). Мэрия ввела субсидию {} руб. за '
            u'каждый проданный саженец — её получают питомники.').format(
                demand_eq(p), supply_eq(p), p['rate'])


def _short_tax(p):
    return (u'Рынок: спрос {}, предложение {} (тыс. шт.). Введён потоварный '
            u'налог {} руб. с продавцов.').format(
                demand_eq(p), supply_eq(p), p['rate'])


def _short_sub(p):
    return (u'Рынок: спрос {}, предложение {} (тыс. шт.). Введена потоварная '
            u'субсидия {} руб. продавцам.').format(
                demand_eq(p), supply_eq(p), p['rate'])


STORIES = [
    Story('soda', 'tax', u'тыс. бутылок', _soda, _short_tax),
    Story('bags', 'tax', u'тыс. шт.', _bags, _short_tax),
    Story('energy', 'tax', u'тыс. банок', _energy, _short_tax),
    Story('milk', 'subsidy', u'тыс. литров', _milk, _short_sub),
    Story('trains', 'subsidy', u'тыс. поездок', _trains, _short_sub),
    Story('saplings', 'subsidy', u'тыс. шт.', _saplings, _short_sub),
]

MONEY = u'тыс. руб.'


class TaxSubsidyArchetype(Archetype):
    key = 'tax_subsidy'
    title = u'Потоварный налог и субсидия'
    block = u'А. Рынок'
    topics = [u'Вмешательство государства']

    def sample(self, rng):
        for _ in range(120):
            p = _market.sample_market(
                rng, p_grid=list(range(40, 101, 5)),
                q_grid=list(range(60, 241, 10)))
            story = rng.randrange(len(STORIES))
            p['story'] = story
            p['kind'] = STORIES[story].kind    # вид вмешательства — из сюжета
            k = rng.choice([2, 3, 4, 5, 6, 8, 10])
            p['rate'] = k * (p['b'] + p['d'])
            s = self.solve(dict(p))
            # валидность: рынок не убит, цены положительны, DWL целое
            if s['q1'] <= 0 or s['pb'] <= 0 or s['ps'] <= 0:
                continue
            if Fraction(s['dwl']).denominator != 1:
                continue
            return p
        raise RuntimeError('tax_subsidy: не сэмплировался валидный рынок')

    def solve(self, params):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        rate = F(params['rate'])
        p0, q0 = _market.solve_market(params)
        if params['kind'] == 'tax':
            pb = p0 + rate * d / (b + d)   # цена покупателей растёт
            ps = pb - rate
        else:
            pb = p0 - rate * d / (b + d)   # субсидия: покупатели платят меньше
            ps = pb + rate
        q1 = a - b * pb
        dq = abs(q0 - q1)
        return {
            'p0': p0, 'q0': q0, 'pb': pb, 'ps': ps, 'q1': q1, 'dq': dq,
            'budget': rate * q1,           # сборы (налог) или расходы (субсидия)
            'dwl': rate * dq / 2,
            'share_buyers': 100 * d / (b + d),
        }

    def asked_values(self, params):
        tax = params['kind'] == 'tax'
        word = u'налога' if tax else u'субсидии'
        unit_q = STORIES[params['story']].unit_q
        asked = [
            Asked('pb', nom=u'цена покупателей после введения ' + word,
                  acc=u'цену покупателей после введения ' + word,
                  gender='f', unit=u'руб.', difficulty=4),
            Asked('ps', nom=u'цена, остающаяся продавцам после введения ' + word,
                  acc=u'цену, остающуюся продавцам после введения ' + word,
                  gender='f', unit=u'руб.', difficulty=4),
            Asked('q1', nom=u'новый равновесный объём продаж',
                  acc=u'новый равновесный объём продаж', gender='m',
                  unit=unit_q, difficulty=4),
            Asked('budget',
                  nom=(u'сумма налоговых поступлений в бюджет' if tax
                       else u'сумма расходов бюджета на субсидию'),
                  acc=(u'сумму налоговых поступлений в бюджет' if tax
                       else u'сумму расходов бюджета на субсидию'),
                  gender='f', unit=MONEY, difficulty=5),
            Asked('dwl', nom=u'величина чистых потерь общества',
                  acc=u'величину чистых потерь общества', gender='f',
                  unit=MONEY, difficulty=5),
        ]
        if tax:
            asked.append(Asked(
                'share_buyers', unit='%', max_value=100, difficulty=5,
                question=u'Какая доля налогового бремени ложится на покупателей (в %)?',
                claim_tpl=u'на покупателей ложится {V} % налогового бремени',
                nom=u'доля налогового бремени покупателей', gender='f'))
        return asked

    def error_variants(self, params, solved, asked):
        b, d = F(params['b']), F(params['d'])
        rate = F(params['rate'])
        tax = params['kind'] == 'tax'
        p0, q0, pb, ps = solved['p0'], solved['q0'], solved['pb'], solved['ps']
        q1, dq = solved['q1'], solved['dq']
        if asked.key == 'pb':
            full = p0 + rate if tax else p0 - rate     # вся ставка на покупателях
            wrong_side = p0 + (p0 - ps) if tax else p0 - (ps - p0)
            return [full, p0, ps, wrong_side, q1]
        if asked.key == 'ps':
            full = p0 - rate if tax else p0 + rate
            wrong_side = 2 * p0 - ps
            return [full, p0, pb, wrong_side, q1]
        if asked.key == 'q1':
            return [q0, q0 - rate if tax else q0 + rate,   # ставка вычтена из Q
                    2 * q0 - q1,                            # сдвиг не в ту сторону
                    dq, pb]
        if asked.key == 'budget':
            return [rate * q0,          # умножили на старый объём
                    solved['dwl'],
                    rate * dq,
                    rate * (q0 + q1) / 2]
        if asked.key == 'dwl':
            return [rate * dq,          # забыли 1/2
                    solved['budget'],
                    rate * q1 / 2,
                    rate * q0 / 2,
                    dq]
        # share_buyers
        return [100 * b / (b + d),      # доля продавцов
                50,
                100 * d / b if b != 0 else 0,
                100 - 100 * b / (b + d)]

    def wrappers(self):
        u"""Один Wrapper: сюжет (а с ним и вид вмешательства) выбран в
        sample(), иначе к налогу могла бы приехать декорация субсидии."""
        def full(p, s):
            return STORIES[p['story']].full(p)

        def short(p, s):
            return STORIES[p['story']].short_setup(p)

        return [Wrapper('story', full, short)]

    def solution(self, params, solved, asked):
        u"""Полный вывод, а не «решая систему, получаем».

        Раньше третий шаг прятал всю работу за словами «решая систему» —
        именно это и значило «решение в три строчки»."""
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        tax = params['kind'] == 'tax'
        rate_f = F(params['rate'])
        rate = fmt_num(params['rate'], latex=True)
        unit_q = STORIES[params['story']].unit_q
        # ⚠️ Налог продавцы ПЛАТЯТ, а субсидию — ПОЛУЧАЮТ. Одним глаголом
        # на оба случая тут не обойтись: «субсидию платят продавцы» — прямая
        # экономическая ошибка в тексте, который читает ученик.
        policy = (u'налог {} руб. с каждой единицы платят продавцы'.format(rate)
                  if tax else
                  u'субсидию {} руб. за каждую единицу продавцы '
                  u'получают'.format(rate))
        # Предложение от цены продавца: Q_s = c + d·(P_b ∓ ставка)
        d_head = u'' if F(d) == 1 else fmt_num(d, latex=True)
        supply_of_pb = u'{} + {}(P_b {} {})'.format(
            fmt_num(c, latex=True), d_head, '-' if tax else '+', rate)
        # Собранное уравнение: (b+d)·P_b = a − c ± d·ставка
        pb_rhs = (a - c + d * rate_f) if tax else (a - c - d * rate_f)
        steps = [
            u'Сначала — что было до вмешательства. $Q_d = Q_s$: ${} = {} '
            u'\\Rightarrow P_0 = {}$ руб., $Q_0 = {}$ {}'.format(
                linear_rhs(params['a'], -b), linear_rhs(params['c'], d),
                fmt_num(solved['p0'], latex=True),
                fmt_num(solved['q0'], latex=True), unit_q),
            (u'Теперь {}, поэтому цена покупателя $P_b$ и цена продавца '
             u'$P_s$ расходятся: $P_s = P_b {} {}$. Продавец смотрит на то, '
             u'сколько остаётся ЕМУ, значит предложение считается от $P_s$: '
             u'$Q_s = {}$.').format(
                 policy, '-' if tax else '+', rate, supply_of_pb),
            (u'Спрос по-прежнему зависит от того, сколько платит покупатель. '
             u'Приравняем: ${} = {}$. Соберём $P_b$: ${}P_b = {} '
             u'\\Rightarrow P_b = {}$ руб.').format(
                 linear_rhs(params['a'], -b, 'P_b'), supply_of_pb,
                 fmt_num(b + d, latex=True), fmt_num(pb_rhs, latex=True),
                 fmt_num(solved['pb'], latex=True)),
            u'Тогда $P_s = {} {} {} = {}$ руб., а объём — из спроса: '
            u'$Q_1 = {}$ {} (было {}).'.format(
                fmt_num(solved['pb'], latex=True), '-' if tax else '+', rate,
                fmt_num(solved['ps'], latex=True),
                fmt_num(solved['q1'], latex=True), unit_q,
                fmt_num(solved['q0'], latex=True)),
        ]
        if asked.key == 'budget':
            verb = u'Сборы бюджета' if tax else u'Расходы бюджета'
            steps.append(
                u'{}: ставка умножается на НОВЫЙ объём (по старому торговать '
                u'уже никто не будет): ${} \\cdot {} = {}$ {}'.format(
                    verb, rate, fmt_num(solved['q1'], latex=True),
                    fmt_num(solved['budget'], latex=True), MONEY))
        elif asked.key == 'dwl':
            steps.append(
                u'Чистые потери — треугольник на сделках, которые были '
                u'выгодны обеим сторонам, но после вмешательства не '
                u'состоялись (объём упал с {} до {}): '
                u'$DWL = \\frac{{1}}{{2}} \\cdot {} \\cdot {} = {}$ {}'.format(
                    fmt_num(solved['q0'], latex=True),
                    fmt_num(solved['q1'], latex=True), rate,
                    fmt_num(solved['dq'], latex=True),
                    fmt_num(solved['dwl'], latex=True), MONEY)
                if tax else
                u'Даже субсидия даёт чистые потери: она вытягивает сделки, '
                u'в которых издержки продавца выше ценности для покупателя '
                u'(объём вырос с {} до {}). '
                u'$DWL = \\frac{{1}}{{2}} \\cdot {} \\cdot {} = {}$ {}'.format(
                    fmt_num(solved['q0'], latex=True),
                    fmt_num(solved['q1'], latex=True), rate,
                    fmt_num(solved['dq'], latex=True),
                    fmt_num(solved['dwl'], latex=True), MONEY))
        elif asked.key == 'share_buyers':
            steps.append(
                u'Бремя делится по наклонам — платит больше тот, кто меньше '
                u'готов отказаться от сделки. Доля покупателей '
                u'$= \\frac{{d}}{{b + d}} = \\frac{{{}}}{{{} + {}}} = '
                u'{}\\,\\%$: цена для них выросла на {} руб. из {} руб. '
                u'ставки.'.format(
                    fmt_num(d, latex=True), fmt_num(b, latex=True),
                    fmt_num(d, latex=True),
                    fmt_num(solved['share_buyers'], latex=True),
                    fmt_num(abs(solved['pb'] - solved['p0']), latex=True),
                    rate))
        return steps

    def figure(self, params, solved, asked):
        u"""Налог: спрос, старое и новое предложение, клин между P_b и P_s,
        прямоугольник сборов и треугольник потерь."""
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        rate = F(params['rate'])
        tax = params['kind'] == 'tax'
        p0, q0 = solved['p0'], solved['q0']
        pb, ps, q1 = solved['pb'], solved['ps'], solved['q1']
        xmax = _figure.axis_max(max(q0, q1) * Fraction(7, 5))
        ymax = _figure.axis_max(max(pb, p0) * Fraction(8, 5))
        # В осях (Q, P): спрос P = (a − Q)/b; предложение P = (Q − c)/d.
        # Со ставкой предложение сдвигается на rate вверх (налог) / вниз
        # (субсидия) — продавцу нужна прежняя выручка на руки.
        shift = rate if tax else -rate
        d_seg = _figure.clip_linear(-Fraction(1, 1) / b, a / b, xmax, ymax)
        s_seg = _figure.clip_linear(Fraction(1, 1) / d, -c / d, xmax, ymax)
        s2_seg = _figure.clip_linear(Fraction(1, 1) / d, -c / d + shift,
                                     xmax, ymax)
        lines = []
        if d_seg:
            lines.append(_figure.line('d', 'D', d_seg[0], d_seg[1]))
        if s_seg:
            lines.append(_figure.line('ghost', 'S', s_seg[0], s_seg[1]))
        if s2_seg:
            lines.append(_figure.line('s', "S'", s2_seg[0], s2_seg[1]))
        return _figure.figure(
            'tax' if tax else 'subsidy', xmax, ymax,
            u'Q, {}'.format(STORIES[params['story']].unit_q), u'P, руб.',
            lines=lines,
            areas=[
                # клин ставки на новом объёме = деньги бюджета
                _figure.area('tax', [(0, ps), (0, pb), (q1, pb), (q1, ps)],
                             u'Бюджет'),
                _figure.area('dwl', [(q1, pb), (q1, ps), (q0, p0)], 'DWL'),
            ],
            points=[
                _figure.point(q0, p0, 'E_0', 'ghost'),
                _figure.point(q1, pb, 'B', 'd'),
                _figure.point(q1, ps, 'S', 's'),
            ],
            marks=[_figure.mark('y', pb, 'P_b'),
                   _figure.mark('y', ps, 'P_s'),
                   _figure.mark('x', q1, 'Q_1'),
                   _figure.mark('x', q0, 'Q_0')])


ARCHETYPE = TaxSubsidyArchetype()
