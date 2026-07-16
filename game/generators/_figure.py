u"""
Схема чертежа к сгенерированной задаче.

Чертёж — ДЕКЛАРАТИВНАЯ геометрия в JSON: питон считает числа, браузер рисует
SVG (game.html::drawFigure). Схема одна на все архетипы — поэтому рисователь
один и не знает ни про монополию, ни про КПВ. Добавить график новому
архетипу = вернуть отсюда собранный dict, рисователь трогать не нужно.

Формат (всё в координатах ЗАДАЧИ, не в пикселях — пересчёт делает клиент):

{
  'kind':   'monopoly',              # для подписи и отладки
  'xmax':   60,   'ymax': 130,       # границы осей (только первая четверть)
  'xlabel': 'Q, тыс. шт.', 'ylabel': 'P, руб.',
  'lines':  [{'role': 'd', 'label': 'D', 'from': [x, y], 'to': [x, y],
              'dash': False}],
  'areas':  [{'role': 'dwl', 'label': 'DWL', 'points': [[x, y], ...]}],
  'points': [{'x': .., 'y': .., 'label': 'M', 'role': 'd'}],
  'marks':  [{'axis': 'x', 'at': 25, 'label': 'Q_m'}],   # засечка на оси
}

⚠️ role — СМЫСЛОВОЙ слой, а не цвет. Цвет назначает клиент из палитры calc2
(--curve-d, --curve-s, --curve-mr, --curve-mc, --curve-tax, --curve-dwl,
--curve-reg, --curve-ghost). Поэтому график перекрашивается переключателем
темы сайта сам, а числа в базе от палитры не зависят и переживут редизайн.
"""
from fractions import Fraction

# Смысловые слои, которые понимает рисователь (game.html::FIG_ROLES).
ROLES = ('d', 's', 'mr', 'mc', 'tax', 'dwl', 'reg', 'ghost', 'cs', 'ps')


def num(v):
    """Fraction/int → JSON-совместимое число.

    Целые остаются int (в JSON «25», а не «25.0»), дробные — float с
    округлением: чертёж — картинка, шестого знака глазу не видно. Точная
    арифметика живёт в solve(), сюда приходят уже готовые величины."""
    f = Fraction(v)
    if f.denominator == 1:
        return int(f)
    return round(float(f), 6)


def pt(x, y):
    return [num(x), num(y)]


def line(role, label, p_from, p_to, dash=False):
    """Отрезок «от» → «до». dash=True — вспомогательная (пунктир)."""
    assert role in ROLES, role
    return {'role': role, 'label': label,
            'from': pt(p_from[0], p_from[1]), 'to': pt(p_to[0], p_to[1]),
            'dash': bool(dash)}


def area(role, points, label=''):
    """Заливка по вершинам многоугольника (излишки, потери, налог)."""
    assert role in ROLES, role
    return {'role': role, 'label': label,
            'points': [pt(p[0], p[1]) for p in points]}


def point(x, y, label='', role='d'):
    """Ключевая точка (равновесие, оптимум монополиста)."""
    assert role in ROLES, role
    return {'x': num(x), 'y': num(y), 'label': label, 'role': role}


def mark(axis, at, label):
    """Засечка с подписью на оси: axis — 'x' или 'y'."""
    assert axis in ('x', 'y'), axis
    return {'axis': axis, 'at': num(at), 'label': label}


def figure(kind, xmax, ymax, xlabel, ylabel,
           lines=None, areas=None, points=None, marks=None):
    """Собирает чертёж. Пустые слои не кладём — JSON в базе меньше и чище."""
    fig = {'kind': kind,
           'xmax': num(xmax), 'ymax': num(ymax),
           'xlabel': xlabel, 'ylabel': ylabel}
    if lines:
        fig['lines'] = lines
    if areas:
        fig['areas'] = areas
    if points:
        fig['points'] = points
    if marks:
        fig['marks'] = marks
    return fig


def clip_linear(slope, intercept, xmax, ymax):
    u"""Отрезок прямой P = slope·Q + intercept внутри рамки [0,xmax]×[0,ymax].

    Кривые задаются экономикой, а рамка — удобством чтения, и сами по себе
    они не совпадают: спрос $Q_d = 280 - P$ уходит к P = 280, хотя всё
    интересное происходит около равновесной цены 100. Обрезаем прямую по
    рамке здесь, в питоне, — иначе клиент рисовал бы линию за краем осей
    или пришлось бы растягивать рамку под пустое место.

    Возвращает ((x1, y1), (x2, y2)) или None, если прямая в рамку не попала.
    """
    m, k = Fraction(slope), Fraction(intercept)
    xmax, ymax = Fraction(xmax), Fraction(ymax)
    if m == 0:
        if not (0 <= k <= ymax):
            return None
        return (0, k), (xmax, k)
    # Q, при которых P = 0 и P = ymax
    q_at_0 = -k / m
    q_at_top = (ymax - k) / m
    lo, hi = sorted([q_at_0, q_at_top])
    lo, hi = max(lo, Fraction(0)), min(hi, xmax)
    if hi <= lo:
        return None
    return (lo, m * lo + k), (hi, m * hi + k)


def axis_max(value, pad=Fraction(115, 100)):
    """Верх оси: величина с запасом ~15 %, округлённая вверх до круглого.

    Оси с «некруглым» верхом (137,8) выглядят как ошибка вёрстки, а не как
    чертёж из учебника."""
    v = Fraction(value) * pad
    if v <= 0:
        return 1
    # шаг округления: 1 / 5 / 10 / 50 / 100 — по порядку величины
    for step in (1, 5, 10, 20, 50, 100, 200, 500, 1000):
        if v <= step * 10:
            return int(-(-v // step) * step)   # деление вверх
    return int(v)
