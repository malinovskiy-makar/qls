"""Правила подсчёта баллов «Высшей пробы» — ЕДИНСТВЕННАЯ точка правды.

⚠️ Никакой арифметики баллов больше нигде в приложении `vp` быть не должно.
Экраны, админка и импорт зовут эти функции и ничего не досчитывают сами.

Почему мы не зовём `student.views.grade_submission`, хотя CLAUDE.md требует
единственной точки проверки: там балл за пункт — это `points` из `ProblemPart`,
без долей и штрафов, а множественный выбор в банке — «всё или ничего»
(`problems.answer_check`). Подсчёт ВП в это не ложится: у него доли верных
отметок, пропорциональный штраф за лишние и клэмп в ноль. Мы переиспользуем
нормализацию из `problems.answer_check`, а правила ВП держим здесь, в одном
модуле. Решение записано в ADR 0124.

Считаем ТОЧНЫМИ ДРОБЯМИ (`fractions.Fraction`), округляем один раз, только
результат: до сотых, `ROUND_HALF_UP`. Промежуточных float нет.
"""
from decimal import Decimal
from fractions import Fraction
from math import floor

from problems.answer_check import normalize_text

# Балл за ОДНО задание с долевым подсчётом (multi) не бывает отрицательным.
# Итог попытки в любом случае не ниже нуля — это `score_attempt`.
CLAMP_MULTI_AT_ZERO = True

_CENT = Decimal('0.01')
_ZERO = Decimal('0.00')


def normalize_short(text):
    """Нормализация короткого ответа: пробелы, регистр, «ё» → «е», точка в конце.

    Пробелы, регистр и завершающую точку делает `problems.answer_check.
    normalize_text`; сверху добавлено только «ё» → «е». Дефисы НЕ трогаем:
    «пятилетка» и «пяти-летка» — разные ответы.

    ⚠️ `normalize_text` заодно превращает запятую в точку. Для сравнения это
    безвредно — обе стороны нормализуются одинаково.
    """
    if text is None:
        return ''
    return normalize_text(text).replace('ё', 'е').strip()


def _round(value):
    """Дробь → Decimal с двумя знаками, ROUND_HALF_UP (половина — от нуля)."""
    cents = abs(value) * 100
    whole = floor(cents + Fraction(1, 2))
    result = (Decimal(whole) / 100).quantize(_CENT)
    return -result if value < 0 and whole else result


def _is_blank(raw):
    """Пустой ответ — «не отвечено»: нет значения, пустая строка или набор."""
    if raw is None:
        return True
    if isinstance(raw, str):
        return not raw.strip()
    if isinstance(raw, (list, tuple, set, dict)):
        return not raw
    return False


def _to_int(value):
    """Номер варианта из ответа: число или строка-число, иначе None."""
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _marked(raw):
    """Множество отмеченных номеров из ответа-списка (мусор отбрасываем)."""
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    return {n for n in map(_to_int, raw) if n is not None}


def _score_short(item, raw):
    given = normalize_short(raw)
    truth = {normalize_short(item.answer)}
    truth.update(normalize_short(a) for a in (item.accepted or []))
    truth.discard('')
    points = Fraction(item.points)
    if given and given in truth:
        return points, True
    return -Fraction(item.wrong_penalty), False


def _score_single(item, raw):
    correct = _marked(item.correct)
    if isinstance(raw, (list, tuple, set)) and len(raw) == 1:
        raw = next(iter(raw))
    chosen = _to_int(raw)
    if chosen is not None and chosen in correct:
        return Fraction(item.points), True
    return -Fraction(item.wrong_penalty), False


def _score_multi(item, raw):
    points = Fraction(item.points)
    correct = _marked(item.correct)
    numbers = {n for n in (_to_int(o.get('n')) for o in (item.options or []))
               if n is not None}
    wrong_all = numbers - correct
    marked = _marked(raw) & numbers
    if not correct:
        return Fraction(0), False
    right = len(marked & correct)
    wrong = len(marked - correct)
    value = points * Fraction(right, len(correct))
    if item.penalty and wrong_all:
        value -= points * Fraction(wrong, len(wrong_all))
    if CLAMP_MULTI_AT_ZERO and value < 0:
        value = Fraction(0)
    return value, value == points


def _score_match(item, raw):
    points = Fraction(item.points)
    correct = item.correct if isinstance(item.correct, dict) else {}
    if not isinstance(raw, dict) or not correct:
        return Fraction(0), False
    right = sum(1 for key, truth in correct.items()
                if key in raw and _to_int(raw[key]) == _to_int(truth))
    value = points * Fraction(right, len(correct))  # штрафа нет никогда
    return value, value == points


_SCORERS = {
    'short_text': _score_short,
    'single': _score_single,
    'multi': _score_multi,
    'match': _score_match,
}


def score_item(item, raw) -> tuple[Decimal, bool | None]:
    """Балл за одно задание: `(балл, верно_ли)`.

    Пустой или отсутствующий ответ — «не отвечено»: `(0.00, None)`. Это НЕ
    «неверно» (`False`): в разборе и статистике «не успел» и «ошибся» — разные
    вещи. Штраф `wrong_penalty` к пустому ответу не применяется никогда — только
    к реально неверному.

    Для непустого ответа что именно начисляется, зависит от `item.kind` (см.
    `_score_*`); `True` — получен полный балл задания, `False` — нет.
    """
    try:
        scorer = _SCORERS[item.kind]
    except KeyError:
        raise ValueError(f'Неизвестный вид задания: {item.kind!r}') from None
    if _is_blank(raw):
        return _ZERO, None
    value, is_correct = scorer(item, raw)
    return _round(value), is_correct


def score_attempt(attempt):
    """Балл попытки: сумма по всем её ответам, не ниже нуля.

    Ничего не пишет в базу: считает по `raw` каждого `VPAnswer`. Задание без
    ответа в сумму не входит — оно даёт 0 и штрафа не несёт.
    """
    total = _ZERO
    for answer in attempt.answers.select_related('item'):
        score, _ = score_item(answer.item, answer.raw)
        total += score
    return max(total, _ZERO).quantize(_CENT)
