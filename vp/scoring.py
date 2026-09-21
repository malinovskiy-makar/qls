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
from collections import namedtuple
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


#: Публичное имя: «пусто ли» — правило подсчёта, экраны спрашивают его здесь.
is_blank = _is_blank


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


_MultiParts = namedtuple(
    '_MultiParts', 'points right wrong correct_total wrong_total gain loss')


def _multi_parts(item, raw):
    """Составные части долевого балла: и подсчёт, и разбор берут их ОТСЮДА.

    `gain` — доля за найденные верные, `loss` — штраф за лишние (только у заданий со
    штрафом). Дроби точные, округляет тот, кто показывает или записывает.
    """
    points = Fraction(item.points)
    correct = _marked(item.correct)
    numbers = {n for n in (_to_int(o.get('n')) for o in (item.options or []))
               if n is not None}
    wrong_all = numbers - correct
    marked = _marked(raw) & numbers
    right = len(marked & correct)
    wrong = len(marked - correct)
    gain = points * Fraction(right, len(correct)) if correct else Fraction(0)
    loss = points * Fraction(wrong, len(wrong_all)) if item.penalty and wrong_all else Fraction(0)
    return _MultiParts(points, right, wrong, len(correct), len(wrong_all), gain, loss)


def _score_multi(item, raw):
    parts = _multi_parts(item, raw)
    if not parts.correct_total:
        return Fraction(0), False
    value = parts.gain - parts.loss
    if CLAMP_MULTI_AT_ZERO and value < 0:
        value = Fraction(0)
    return value, value == parts.points


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


def explain_item(item, raw) -> dict:
    """Как получился балл за задание — СТРУКТУРА для экрана разбора, не готовая строка.

    Ничего не считает сама: балл берёт у `score_item`, доли — у `_multi_parts`, ту же
    арифметику, что и подсчёт. Текст «3 × 2/2 − 3 × 1/3 = 3,00 − 1,00 = 2,00» собирает
    шаблон. Виды:

    * `blank` — не отвечено (`is_correct` — `None`);
    * `share` — долевой подсчёт (`multi`): найдено `correct_hit` из `correct_total`
      верных, лишних отмечено `wrong_hit` из `wrong_total` неверных, `gain`/`loss` —
      прибавка и штраф, `clamped` — итог ушёл бы ниже нуля и поднят до нуля
      (`before_clamp` — каким он был бы: «−0,50 → 0,00»). `penalty` — есть ли у
      задания штраф вообще;
    * `binary` — короткий ответ и «один верный»: `score` и `is_correct`.

    ⚠️ `gain` и `loss` округлены каждый сам, а `score` — один раз из точных дробей,
    поэтому у заданий с «некруглым» баллом разность может отличаться от `score` на
    копейку. У формата 1 тура (3 балла, до пяти вариантов) они совпадают.
    """
    score, is_correct = score_item(item, raw)
    if is_correct is None:
        return {'kind': 'blank', 'score': score, 'is_correct': None}
    if item.kind == 'multi':
        parts = _multi_parts(item, raw)
        return {
            'kind': 'share',
            'points': _round(parts.points),
            'correct_total': parts.correct_total, 'correct_hit': parts.right,
            'wrong_total': parts.wrong_total, 'wrong_hit': parts.wrong,
            'penalty': bool(item.penalty and parts.wrong_total),
            'gain': _round(parts.gain), 'loss': _round(parts.loss),
            'before_clamp': _round(parts.gain - parts.loss),
            'clamped': parts.gain - parts.loss < 0,
            'score': score, 'is_correct': is_correct,
        }
    return {'kind': 'binary', 'score': score, 'is_correct': is_correct}


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


def penalty_example(points):
    """Числа для примера в правилах на входе: в задании 2 верных и 3 неверных варианта.

    Верный вариант приносит долю `points / 2`, лишний отнимает `points / 3`
    (доля верных отметок и доля лишних — те же, что в `_score_multi`). Возвращает
    `(за верный, за лишний)`, округлено до сотых. Живёт здесь, а не в шаблоне и не
    во view: арифметику баллов держим в одном модуле.
    """
    points = Fraction(points)
    return _round(points / 2), _round(points / 3)


def block_totals(attempt):
    """Баллы сданной попытки по блокам: `{блок: (набрано, максимум)}`.

    Читает баллы, записанные при сдаче в `VPAnswer`, и складывает их по блокам;
    порядок блоков — по номеру первого задания. Своей проверки ответов не делает.
    """
    totals = {}
    answers = attempt.answers.select_related('item').order_by('item__number')
    for answer in answers:
        got, top = totals.get(answer.item.block, (_ZERO, _ZERO))
        totals[answer.item.block] = (got + (answer.score or _ZERO), top + answer.item.points)
    return totals
