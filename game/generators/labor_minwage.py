"""
Архетип 15 (Блок Г): рынок труда с МРОТ выше равновесной ставки.

Ld = A − B·W, Ls = C + D·W; при МРОТ Wm > W*: безработица =
Ls(Wm) − Ld(Wm) = (B + D)·(Wm − W*), занятость = Ld(Wm).

Обратный ход: сэмплируются красивые W*, L* и отступ МРОТ.

Контроль: Ld = 100 − 2W, Ls = −20 + 4W → W* = 20, L* = 60;
МРОТ = 25 → безработица = 30.
"""
from fractions import Fraction

from .base import Archetype, Asked, Wrapper, F, fmt_num, linear_eq
from . import _market

W_GRID = list(range(10, 61, 5))       # W* — равновесная ставка
L_GRID = list(range(40, 201, 10))     # L* — равновесная занятость


class LaborMinwageArchetype(Archetype):
    key = 'labor_minwage'
    title = u'Рынок труда и МРОТ'
    block = u'Г. Макро-лайт'
    topics = [u'Рынок труда']

    def sample(self, rng):
        for _ in range(120):
            w_star = rng.choice(W_GRID)
            l_star = rng.choice(L_GRID)
            b = rng.choice([1, 1, 2, 2, 3, 4])
            d = rng.choice([1, 2, 2, 3, 4, 4, 5])
            m = rng.choice([5, 10, 15])
            p = {
                'a': l_star + b * w_star, 'b': b,
                'c': l_star - d * w_star, 'd': d,
                'wm': w_star + m,
            }
            s = self.solve(p)
            if s['ld_m'] > 0:   # МРОТ не убивает занятость
                return p
        raise RuntimeError('labor_minwage: не сэмплировался валидный рынок труда')

    def solve(self, params):
        a, b = F(params['a']), F(params['b'])
        c, d = F(params['c']), F(params['d'])
        wm = F(params['wm'])
        w_star = (a - c) / (b + d)
        l_star = a - b * w_star
        ld_m = a - b * wm
        ls_m = c + d * wm
        return {
            'w_star': w_star, 'l_star': l_star,
            'ld_m': ld_m, 'ls_m': ls_m,
            'employment': ld_m,
            'unemployment': ls_m - ld_m,
        }

    def asked_values(self, params):
        return [
            Asked('w_star', nom=u'равновесная ставка заработной платы',
                  acc=u'равновесную ставку заработной платы', gender='f',
                  unit=u'ден. ед.'),
            Asked('l_star', nom=u'равновесная занятость',
                  acc=u'равновесную занятость', gender='f', unit=u'чел.'),
            Asked('unemployment',
                  nom=u'число безработных после введения МРОТ',
                  acc=u'число безработных (превышение предложения труда '
                      u'над спросом) после введения МРОТ',
                  gender='n', unit=u'чел.'),
            Asked('employment', nom=u'занятость после введения МРОТ',
                  acc=u'занятость после введения МРОТ', gender='f',
                  unit=u'чел.'),
        ]

    def error_variants(self, params, solved, asked):
        b, d = F(params['b']), F(params['d'])
        m = F(params['wm']) - solved['w_star']
        if asked.key == 'w_star':
            a, c = F(params['a']), F(params['c'])
            return [(a + c) / (b + d),    # потерян знак c
                    solved['l_star'],     # перепутаны W и L
                    (a - c) / b,
                    (a - c) / d,
                    F(params['wm'])]
        if asked.key == 'l_star':
            return [solved['w_star'],     # перепутаны W и L
                    solved['ld_m'],       # взято при МРОТ
                    solved['ls_m'],
                    F(params['a'])]
        if asked.key == 'unemployment':
            return [solved['ls_m'],       # только предложение
                    solved['ld_m'],       # только спрос
                    b * m,                # один наклон
                    d * m,
                    solved['l_star'] - solved['ld_m']]  # падение занятости
        # employment
        return [solved['ls_m'],           # длинная сторона рынка
                solved['l_star'],         # МРОТ проигнорирован
                solved['unemployment'],
                solved['l_star'] - solved['unemployment']]

    def _setup(self, params, full=True):
        dem = linear_eq('L_d', params['a'], -F(params['b']), 'W')
        sup = linear_eq('L_s', params['c'], F(params['d']), 'W')
        if full:
            return (u'На рынке труда города N спрос и предложение задаются '
                    u'функциями {} и {}, где часовая ставка оплаты $W$ '
                    u'задана в ден. ед., а число работников $L$ в чел. '
                    u'Государство ввело минимальную ставку оплаты труда '
                    u'(МРОТ) {} ден. ед. в час.').format(
                        dem, sup, params['wm'])
        return (u'Рынок труда: {} и {} (ставка $W$ в ден. ед., $L$ в чел.). '
                u'Введён МРОТ {} ден. ед.').format(dem, sup, params['wm'])

    def wrappers(self):
        def full_town(p, s):
            return self._setup(p, full=True)

        def full_industry(p, s):
            dem = linear_eq('L_d', p['a'], -F(p['b']), 'W')
            sup = linear_eq('L_s', p['c'], F(p['d']), 'W')
            return (u'В отрасли лёгкой промышленности страны Икс спрос '
                    u'фирм на труд равен {}, предложение труда равно {} '
                    u'(часовая ставка $W$ в ден. ед., число '
                    u'работников $L$ в чел.). Правительство установило '
                    u'минимальную часовую ставку {} ден. ед.').format(
                        dem, sup, p['wm'])

        def short(p, s):
            return self._setup(p, full=False)

        return [Wrapper('town', full_town, short),
                Wrapper('industry', full_industry, short)]

    def solution(self, params, solved, asked):
        steps = [
            u'Равновесие: $W^* = {}$ ден. ед., $L^* = {}$ чел.'.format(
                fmt_num(solved['w_star'], latex=True),
                fmt_num(solved['l_star'], latex=True)),
        ]
        if asked.key in ('unemployment', 'employment'):
            steps.append(
                (u'МРОТ ${}$ выше равновесной ставки, поэтому рынок не '
                 u'приходит в равновесие. При $W = {}$: $L_d = {}$, '
                 u'$L_s = {}$ чел.').format(
                    params['wm'], params['wm'],
                    fmt_num(solved['ld_m'], latex=True),
                    fmt_num(solved['ls_m'], latex=True)))
        if asked.key == 'unemployment':
            steps.append(
                u'Безработица: $L_s - L_d = {} - {} = {}$ чел.'.format(
                    fmt_num(solved['ls_m'], latex=True),
                    fmt_num(solved['ld_m'], latex=True),
                    fmt_num(solved['unemployment'], latex=True)))
        elif asked.key == 'employment':
            steps.append(
                u'Занятость определяет короткая сторона рынка, то есть спрос: '
                u'$L = {}$ чел.'.format(fmt_num(solved['ld_m'], latex=True)))
        return steps


ARCHETYPE = LaborMinwageArchetype()
