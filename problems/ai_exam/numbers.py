"""Числа и ключи экзамена: разбор записи ответа, поиск чисел, сравнение.

Чистые функции, к базе не обращаются. Последний шаг разбора отдан
`problems.answer_check.parse_number`, чтобы «число» в экзамене и в
автопроверке домашки значило одно и то же: десятичная запятая, простые
дроби a/b, Fraction вместо float.

Чего v0 сознательно НЕ понимает: степени и запись «2·10^3». Такой ответ —
не число (None), его ключ впишет человек на странице проверки.
"""
import re
from fractions import Fraction

from problems.answer_check import parse_number

#: Пробелы, которыми в банке разделяют разряды: обычный, неразрывный,
#: тонкий и узкий неразрывный.
_SPACES = ' \u00a0\u2009\u202f'

#: Разрядный пробел: между цифрами и ПЕРЕД группой ровно из трёх цифр
#: («1 250» → 1250). «12 5» под правило не подпадает — это не число.
_THOUSANDS_RE = re.compile(r'(?<=\d)[%s]+(?=\d{3}(?!\d))' % _SPACES)
_TEXT_CMD_RE = re.compile(r'\\(?:text|mathrm|textrm|mbox)\s*\{([^{}]*)\}')
_TEX_SPACE_RE = re.compile(r'\\[,;! ]|~')
_FRAC_RE = re.compile(
    r'\\[dt]?frac\s*\{\s*([-+]?\d+)\s*\}\s*\{\s*([-+]?\d+)\s*\}')

#: Вся строка — одно число: целое, десятичное, простая дробь.
_NUMBER_RE = re.compile(r'^[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:/[-+]?\d+)?$')
#: Короткий хвост единиц: начинается с буквы, без цифр, до 12 знаков.
_UNIT_TAIL_RE = re.compile(
    r'^(?P<num>.*?\d)\s*(?P<unit>[^\W\d_](?:[^\W\d_]|[.\s/])*)$')
_UNIT_MAX = 12

# Что числом НЕ считается при поиске в тексте.
_POWER10_RE = re.compile(
    r'[-+]?\d+(?:[.,]\d+)?\s*[·*×]\s*10\s*\^\s*(?:\{[^{}]*\}|[-+]?\d+)')
_EXP_RE = re.compile(
    r'(?:\d+(?:[.,]\d+)?)?\s*\^\s*(?:\{[^{}]*\}|[-+]?\d+(?:[.,]\d+)?)')
_SUB_RE = re.compile(r'_\s*(?:\{[^{}]*\}|\d+|[^\W\d_])')
#: Число в тексте. Знак минус — только если перед ним не буква и не
#: скобка («Q-1» — это не «минус один»). Цифра, приклеенная к букве
#: («P1»), — индекс, а не число.
_FIND_RE = re.compile(
    r'(?:(?<![\w)\]])(-))?(?<![^\W\d_])(?<![\d.,/])'
    r'(\d+(?:[.,]\d+)?(?:/\d+)?)(?!\d)(\s*%)?')

#: Заведомо не ключ: знак неравенства («A>25», «P ≥ 5», \le, \geq …).
_INEQUALITY_RE = re.compile(
    r'[<>≤≥]|\\(?:leqslant|geqslant|leq|geq|le|ge|lt|gt)(?![A-Za-z])')
#: Заведомо не ключ: число — коэффициент формулы, то есть стоит вплотную
#: к латинской букве или умножается на неё («240Q», «2x», «240·Q»).
#: Кириллический хвост вплотную («5кг») — это единицы, сюда не попадает.
_COEFFICIENT_RE = re.compile(r'\d\s*[·*×]\s*[A-Za-z]|\d[A-Za-z]')

#: Нижняя граница допуска по умолчанию — полсотой.
_MIN_TOL = Fraction(5, 1000)


def _normalize(text):
    """Общая чистка записи: TeX-обрамление, пробелы, минусы, \\frac."""
    s = str(text or '')
    s = s.replace('$', '')
    s = _TEXT_CMD_RE.sub(r'\1', s)
    s = s.replace('{,}', ',').replace('{.}', '.')
    s = _TEX_SPACE_RE.sub(' ', s)
    s = s.replace('−', '-').replace('–', '-')
    s = s.replace('\\%', '%').replace('\\approx', '≈')
    s = s.replace('\\cdot', '·').replace('\\times', '×')
    s = _THOUSANDS_RE.sub('', s)
    return _FRAC_RE.sub(r'\1/\2', s)


def _parse(text):
    """Строка → (Fraction или None, запись числа, единицы, проценты?)."""
    s = _normalize(text).strip(_SPACES + '\t\n')
    s = s.lstrip('≈=~' + _SPACES + '\t')
    percent = False
    if s.endswith('%'):
        percent = True
        s = s[:-1].rstrip(_SPACES + '\t')
    unit = ''
    match = _UNIT_TAIL_RE.match(s)
    if match and len(match.group('unit').strip()) <= _UNIT_MAX:
        s = match.group('num')
        unit = match.group('unit').strip()
    core = s.strip(_SPACES + '\t').rstrip('.')
    if not _NUMBER_RE.match(core):
        return None, core, unit, percent
    return parse_number(core), core, unit, percent


def _canon(core):
    """Запись числа для ключа: точка вместо запятой, без плюса."""
    return core.replace(',', '.').lstrip('+')


def _decimals(core):
    """Сколько знаков после запятой в записи ключа; у дроби — ноль."""
    if '/' in core:
        return 0
    match = re.search(r'[.,](\d+)$', core)
    return len(match.group(1)) if match else 0


def to_number(text):
    """Запись ответа → Fraction или None, если вся запись — не одно число.

    Допускается обрамление $…$, разрядные пробелы, {,}, \\frac{a}{b}, знак
    процента и короткий хвост единиц («руб.», «тыс. руб.»).
    """
    return _parse(text)[0]


def _find(text):
    """[(Fraction, запись, проценты?)] — все числа в тексте по порядку."""
    s = _normalize(text)
    s = _POWER10_RE.sub(' ', s)
    s = _EXP_RE.sub(' ', s)
    s = _SUB_RE.sub(' ', s)
    found = []
    for match in _FIND_RE.finditer(s):
        core = (match.group(1) or '') + match.group(2)
        value = parse_number(core)
        if value is not None:
            found.append((value, core, bool(match.group(3))))
    return found


def find_numbers(text):
    """Все числа в тексте с TeX. Индексы (Q_1, Q_{1}, P1) и степени
    (x^2, 10^3) числами не считаются."""
    return [value for value, _core, _pct in _find(text)]


def propose_key(raw_answer):
    """Предложение ключа по ответу банка.

    exact — вся строка после чистки это одно число (хвост единиц допустим);
    extracted — в тексте ровно одно число; none — иначе (ключ впишет человек).

    none и для заведомого мусора — неравенства и коэффициенты формул: такой
    «ключ» не ответ, а ловушка для проверяющего, который поверит подсказке.
    """
    if (_INEQUALITY_RE.search(str(raw_answer or ''))
            or _COEFFICIENT_RE.search(_normalize(raw_answer))):
        return {'value': '', 'unit': '', 'percent': False, 'kind': 'none'}
    value, core, unit, percent = _parse(raw_answer)
    if value is not None:
        return {'value': _canon(core), 'unit': unit, 'percent': percent,
                'kind': 'exact'}
    found = _find(raw_answer)
    if len(found) == 1:
        _value, core, percent = found[0]
        return {'value': _canon(core), 'unit': '', 'percent': percent,
                'kind': 'extracted'}
    return {'value': '', 'unit': '', 'percent': False, 'kind': 'none'}


def parse_tol(tol):
    """Допуск из ключа: None — по умолчанию; иначе положительная Fraction.

    Не число или не больше нуля — ValueError: молча подменить допуск
    значило бы мерить модель не той линейкой.
    """
    if tol is None or str(tol).strip() == '':
        return None
    value = to_number(str(tol))
    if value is None or value <= 0:
        raise ValueError('допуск должен быть положительным числом: %r' % tol)
    return value


def default_tol(value):
    """Допуск по умолчанию для ключа `value`:
    max(0,005; 1 % от |ключа|; половина последнего знака записи)."""
    key, core = _parse(value)[:2]
    if key is None:
        raise ValueError('ключ не число: %r' % value)
    tol = max(_MIN_TOL, abs(key) / 100)
    digits = _decimals(core)
    if digits >= 1:
        tol = max(tol, Fraction(1, 2) / 10 ** digits)
    return tol


def matches(given, value, percent=False, tol=None):
    """Совпадает ли выданный ответ `given` с ключом `value`.

    Верно, если |g − k| ≤ допуск. Ключ в процентах (`percent=True`)
    засчитывает и долю: 0,25 при ключе 25. Если в ответе стоит знак %,
    а ключ — доля, засчитывается и g/100.
    """
    key = to_number(value)
    if key is None:
        return False
    got, _core, _unit, given_percent = _parse(given)
    if got is None:
        return False
    limit = parse_tol(tol)
    if limit is None:
        limit = default_tol(value)
    candidates = [got]
    if percent:
        candidates.append(got * 100)
    elif given_percent:
        candidates.append(got / 100)
    return any(abs(c - key) <= limit for c in candidates)
