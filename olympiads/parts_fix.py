"""Пункты задач пакета олимпиад: что починить механически (день 30.10, Д1–Д3).

Модуль только РЕШАЕТ; пишут команды `dedupe_problem_parts`,
`split_statement_parts`, `strip_part_points`. Функции чистые: принимают
строки пунктов (словари `values()` модели `ProblemPart`) и тексты, базу не
трогают.

⚠️ ПРИНЦИП тот же, что у чистки S6 (ADR 0172): чинить только механическое и
однозначное. Числа, знаки и смысл не меняются; всё сомнительное — причина
«под вопросом», текст остаётся как был.
"""
import re

_WS = re.compile(r'\s+')


def squeeze(text):
    """Текст без пробелов и переводов строк — так сравниваются пункты."""
    return _WS.sub('', text or '')


# ── Д1: пункты записаны дважды ───────────────────────────────────────────

REASON_PART_CONFLICT = 'пункт с одной меткой записан дважды с разным текстом или баллами'
REASON_PART_SAME_TEXT = 'один текст пункта под разными метками'


def dedupe_plan(parts):
    """Какие пункты задачи — копии. `parts` — по порядку (`order`, `id`).

    Возвращает (`remove`, `reasons`): `remove` — {id копии: id оставленного};
    оставляется первый по порядку. Копия — та же метка, тот же текст, те же
    баллы, ответ и решение: удалить её значит ничего не потерять. Метка одна,
    а текст или баллы различаются — такие пункты не трогаем, причина в
    `reasons` («а) X, а) Y, а) X»: второй X уходит, Y остаётся под вопросом).
    """
    first = {}
    remove, reasons = {}, []
    for part in parts:
        key = (part['label'], squeeze(part['statement']), part['points'],
               squeeze(part['answer']), squeeze(part['solution']))
        if key in first:
            remove[part['id']] = first[key]
        else:
            first[key] = part['id']
    left = [p for p in parts if p['id'] not in remove]
    labels = [p['label'] for p in left]
    if len(set(labels)) < len(labels):
        reasons.append(REASON_PART_CONFLICT)
    left = [p for p in left if squeeze(p['statement'])]
    if len({squeeze(p['statement']) for p in left}) < len(left):
        reasons.append(REASON_PART_SAME_TEXT)
    return remove, reasons


def has_repeated_text(parts):
    """Мерка карточки Notion: один и тот же текст пункта встречается дважды."""
    texts = [squeeze(p['statement']) for p in parts if squeeze(p['statement'])]
    return len(set(texts)) < len(texts)


# ── Д2: текст пунктов ещё раз внутри условия ─────────────────────────────

REASON_SPLIT_MISMATCH = 'пункты в условии не совпали с пунктами задачи'
REASON_SPLIT_EMPTY = 'после пунктов в условии не осталось общей части'

# «(4 балла)», в том числе жирным, — пометка балла пункта.
BALLS = re.compile(r'[*_]*\(\s*(\d+(?:[.,]\d+)?)\s*балл\w*\s*\)[*_]*', re.IGNORECASE)
# Буквы-двойники по начертанию: метка «a)» латиницей в условии — та же «а)».
_TWINS = {'а': 'аa', 'a': 'аa', 'с': 'сc', 'c': 'сc', 'е': 'еe', 'e': 'еe',
          'о': 'оo', 'o': 'оo'}
_MARKUP = r'(?:\*\*|__|\*|_)?'
# Хоть немного общей части: буква или цифра.
_MEANINGFUL = re.compile(r'[0-9A-Za-zА-Яа-яЁё]')


def _label_pattern(label):
    """Метка пункта в начале строки: «а)», «(а)», «**а)**», «- а.», «1)», «1.»."""
    label = (label or '').strip().rstrip(').').lstrip('(')
    if not label:
        return None
    # Регистр метки не важен: пункт «b», в условии «B.».
    first = _TWINS.get(label[0].lower())
    head = '[{}]'.format(first) if first else re.escape(label[0])
    body = '(?i:' + head + re.escape(label[1:]) + ')'
    return (r'[ \t]*(?:[-*•+][ \t]+)?' + _MARKUP + r'\(?' + _MARKUP + body
            + r'\s*[).]' + _MARKUP)


def _loose(text):
    """Регулярное выражение текста без учёта пробелов между знаками."""
    return r'\s*'.join(re.escape(ch) for ch in squeeze(text))


def _points_of(match):
    return float(match.group(1).replace(',', '.'))


def split_plan(statement, parts):
    """Где в условии начинаются пункты, если хвост условия — ровно они.

    Возвращает (новое условие или None, причина или None). Хвост условия от
    метки первого пункта обязан состоять из меток и текстов пунктов по
    порядку — без учёта пробелов, разметки меток и пометки «(N балла)» у
    пункта с баллом N. Лишний абзац, другой порядок, рисунок или знак
    препинания, которого нет в пункте, — не совпало: условие не трогаем.
    Пунктов внутри условия нет вовсе — (None, None).
    """
    statement = statement or ''
    if not parts or not any(squeeze(p['statement'])[:60] in squeeze(statement)
                            for p in parts if squeeze(p['statement'])):
        return None, None
    patterns = [_label_pattern(p['label']) for p in parts]
    if None in patterns or not all(squeeze(p['statement']) for p in parts):
        return None, REASON_SPLIT_MISMATCH
    for start in re.finditer(r'(?m)^' + patterns[0], statement):
        pos = start.start()
        tail = _match_tail(statement, pos, parts, patterns)
        if tail is None:
            continue
        head = statement[:pos].rstrip()
        if not _MEANINGFUL.search(head):
            return None, REASON_SPLIT_EMPTY
        return head, None
    return None, REASON_SPLIT_MISMATCH


def _match_tail(statement, pos, parts, patterns):
    """Хвост `statement[pos:]` — ровно пункты по порядку? Конец совпадения или None."""
    for part, pattern in zip(parts, patterns):
        label = re.compile(r'\s*' + pattern).match(statement, pos)
        if not label:
            return None
        pos = label.end()
        text = re.compile(r'\s*' + _loose(part['statement'])).match(statement, pos)
        if not text:
            balls = re.compile(r'\s*' + BALLS.pattern, re.IGNORECASE).match(statement, pos)
            if (not balls or part['points'] is None
                    or _points_of(balls) != float(part['points'])):
                return None
            text = re.compile(r'\s*' + _loose(part['statement'])).match(statement, balls.end())
            if not text:
                return None
        pos = text.end()
    if statement[pos:].strip():
        return None
    return pos


def tail_is_parts(tail, parts):
    """Независимая сверка «ни одного знака не потеряно».

    Из вырезанного хвоста убираются метки пунктов (в начале строк) и пометки
    «(N балла)»; что осталось, без пробелов, обязано совпасть со склеенными
    текстами пунктов (тоже без пометок баллов).
    """
    rest = tail
    for part in parts:
        pattern = _label_pattern(part['label'])
        rest = re.sub(r'(?m)^' + pattern, '', rest, count=1)
    rest = BALLS.sub('', rest)
    glued = ''.join(BALLS.sub('', p['statement']) for p in parts)
    return squeeze(rest) == squeeze(glued)


# ── Д3: «(4 балла)» в начале текста пункта ───────────────────────────────

REASON_POINTS_DIFFER = 'пометка баллов в тексте пункта расходится с баллами пункта'
REASON_POINTS_MARKUP = 'пометка баллов пункта внутри разметки'

_LEAD_POINTS = re.compile(
    r'\s*(?P<pre>[*_]*)\(\s*(?P<n>\d+(?:[.,]\d+)?)\s*балл\w*\s*\)(?P<post>[*_]*)\s*',
    re.IGNORECASE)


def points_plan(part):
    """(новый текст или None, баллы для пустого поля или None, причина или None).

    Пометка «(N балл…)» в начале текста при `points = N` убирается — баллы
    экран показывает отдельно. `points` пусто — ставится N. N ≠ `points` —
    причина, текст не трогаем. Пометка, разрывающая разметку («**(4 балла)
    Найдите**»), — тоже причина: убрать её значит сломать жирный шрифт.
    """
    match = _LEAD_POINTS.match(part['statement'] or '')
    if not match:
        return None, None, None
    rest = part['statement'][match.end():]
    if match.group('pre') != match.group('post'):
        return None, None, REASON_POINTS_MARKUP
    if not _MEANINGFUL.search(rest):
        return None, None, REASON_POINTS_DIFFER
    number = float(match.group('n').replace(',', '.'))
    if part['points'] is None:
        return rest, match.group('n').replace(',', '.'), None
    if float(part['points']) != number:
        return None, None, REASON_POINTS_DIFFER
    return rest, None, None
