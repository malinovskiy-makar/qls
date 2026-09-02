"""
Архетип 14 (Блок Г): мультипликатор госзакупок в кейнсианском кресте.

k = 1/(1 − MPC); ΔВВП = k·ΔG. Два варианта сюжета: дан ΔG (найти
мультипликатор или ΔВВП) и обратный — дана цель по ΔВВП (найти нужный ΔG).

Контроль: MPC = 0,8 → k = 5; ΔG = 20 → ΔВВП = 100.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num

# MPC из ТЗ; мультипликаторы: 2, 2,5, 4, 5, 10.
MPC_GRID = ['0,5', '0,6', '0,75', '0,8', '0,9']


class MpcMultiplierArchetype(Archetype):
    key = 'mpc_multiplier'
    title = u'Мультипликатор госзакупок'
    block = u'Г. Макро-лайт'
    topics = [u'Фискальная политика']

    def sample(self, rng):
        mpc = rng.choice(MPC_GRID)
        mult = 1 / (1 - F(mpc))
        variant = rng.choice(['given_dg', 'need_dy'])
        for _ in range(60):
            dg = rng.choice(range(10, 101, 10))
            if (mult * dg).denominator != 1:
                continue
            if variant == 'given_dg':
                return {'mpc': mpc, 'dg': dg, 'variant': variant}
            return {'mpc': mpc, 'dy': int(mult * dg), 'variant': variant}
        raise RuntimeError('mpc_multiplier: не сэмплировался красивый ΔG')

    def solve(self, params):
        mpc = F(params['mpc'])
        mult = 1 / (1 - mpc)
        out = {'mult': mult}
        if params['variant'] == 'given_dg':
            out['dgdp'] = mult * F(params['dg'])
        else:
            out['dg_needed'] = F(params['dy']) / mult
        return out

    def asked_values(self, params):
        asked = [
            Asked('mult', nom=u'мультипликатор государственных закупок',
                  acc=u'мультипликатор государственных закупок',
                  gender='m', unit=''),
        ]
        if params['variant'] == 'given_dg':
            asked.append(Asked(
                'dgdp', unit=u'ден. ед.',
                question=u'На сколько ден. ед. вырастет равновесный ВВП?',
                claim_tpl=u'равновесный ВВП вырастет на {V} ден. ед.',
                nom=u'прирост равновесного ВВП', gender='m'))
        else:
            asked.append(Asked(
                'dg_needed', unit=u'ден. ед.',
                question=(u'На сколько ден. ед. следует увеличить '
                          u'государственные закупки?'),
                claim_tpl=(u'для этого достаточно увеличить госзакупки '
                           u'на {V} ден. ед.'),
                nom=u'необходимый прирост госзакупок', gender='m'))
        return asked

    def error_variants(self, params, solved, asked):
        mpc = F(params['mpc'])
        mult = solved['mult']
        if asked.key == 'mult':
            return [1 / mpc,             # перевёрнута формула
                    mpc,                 # взята сама MPC
                    1 - mpc,             # взята MPS
                    mult - 1,            # мультипликатор налогов
                    mult + 1]
        if asked.key == 'dgdp':
            dg = F(params['dg'])
            return [dg,                  # мультипликатор забыт
                    mpc * dg,            # умножили на MPC
                    (mult - 1) * dg,     # налоговый мультипликатор
                    dg * (1 + mpc),      # только первые два раунда расходов
                    dg / (1 - mpc) / 2]
        dy = F(params['dy'])
        return [dy,                      # деление забыто
                dy * mpc,                # умножили вместо деления
                dy / (mult - 1) if mult != 1 else dy,
                dy * 2 / mult]

    def wrappers(self):
        def policy(p):
            if p['variant'] == 'given_dg':
                return (u'Правительство увеличивает государственные закупки '
                        u'товаров и услуг на {} ден. ед.; налоги '
                        u'не меняются.').format(p['dg'])
            return (u'Правительство хочет, чтобы равновесный ВВП вырос '
                    u'на {} ден. ед. за счёт государственных закупок; '
                    u'налоги не меняются.').format(p['dy'])

        def full(p, s):
            return (u'В закрытой экономике страны Икс потребление домохозяйств '
                    u'линейно зависит от располагаемого дохода: предельная '
                    u'склонность к потреблению равна {}. Инвестиции и налоги '
                    u'автономны. {}').format(p['mpc'], policy(p))

        def full_crisis(p, s):
            return (u'После спада экономика страны Икс работает не на полную '
                    u'мощность, поэтому выпуск определяется спросом. '
                    u'Предельная склонность к потреблению равна {}, '
                    u'инвестиции и налоги автономны. {}').format(
                        p['mpc'], policy(p))

        def full_region(p, s):
            return (u'Область считает, что даст её экономике оживление '
                    u'бюджетных расходов. Модель кейнсианская: предельная '
                    u'склонность к потреблению {}, инвестиции и налоги '
                    u'автономны. {}').format(p['mpc'], policy(p))

        def full_memo(p, s):
            return (u'Министерство экономики готовит записку о влиянии '
                    u'бюджета на выпуск. Экономика закрытая, предельная '
                    u'склонность к потреблению {}, инвестиции и налоги '
                    u'автономны. {}').format(p['mpc'], policy(p))

        def full_class(p, s):
            return (u'На занятии разбирают кейнсианский крест. Экономика '
                    u'закрытая, предельная склонность к потреблению равна {}, '
                    u'инвестиции и налоги автономны. {}').format(
                        p['mpc'], policy(p))

        def short(p, s):
            return (u'Кейнсианский крест: MPC = {}. {}').format(
                p['mpc'], policy(p))

        def short_crisis(p, s):
            return (u'После спада, выпуск по спросу. MPC = {}. {}').format(
                p['mpc'], policy(p))

        def short_region(p, s):
            return (u'Область, кейнсианская модель: MPC = {}. {}').format(
                p['mpc'], policy(p))

        def short_memo(p, s):
            return (u'Записка министерства: MPC = {}. {}').format(
                p['mpc'], policy(p))

        def short_class(p, s):
            return (u'Разбор на занятии: MPC = {}. {}').format(
                p['mpc'], policy(p))

        return [Wrapper('country', full, short),
                Wrapper('crisis', full_crisis, short_crisis),
                Wrapper('region', full_region, short_region),
                Wrapper('memo', full_memo, short_memo),
                Wrapper('class', full_class, short_class)]

    def solution(self, params, solved, asked):
        mpc = params['mpc']
        mult = solved['mult']
        steps = [
            (u'Мультипликатор госзакупок: $k = \\frac{{1}}{{1 - MPC}} '
             u'= \\frac{{1}}{{1 - {}}} = {}$.').format(
                fmt_num(F(mpc), latex=True), fmt_num(mult, latex=True)),
        ]
        if asked.key == 'dgdp':
            steps.append(
                u'$\\Delta ВВП = k \\cdot \\Delta G = {} \\cdot {} = {}$ '
                u'ден. ед.'.format(
                    fmt_num(mult, latex=True), params['dg'],
                    fmt_num(solved['dgdp'], latex=True)))
        elif asked.key == 'dg_needed':
            steps.append(
                u'$\\Delta G = \\Delta ВВП / k = {} / {} = {}$ ден. ед.'.format(
                    params['dy'], fmt_num(mult, latex=True),
                    fmt_num(solved['dg_needed'], latex=True)))
        return steps


ARCHETYPE = MpcMultiplierArchetype()
