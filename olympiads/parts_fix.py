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
