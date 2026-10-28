# -*- coding: utf-8 -*-
"""Строка «олимпиада · год · этап · класс · задание» под заголовком задачи.

Решение 15.10.2026 «Заголовок олимпиадной задачи…»: олимпиада, год, этап,
класс и номер не пишутся в заголовок, а показываются отдельной строкой из
`OlympiadRef`. Ответ владельца на гейте 1 И3 (28.10): показываются привязки
`official` и `ile` (зеркало официального архива ЦПМК); SolveHub — нет, его
номера — позиции в списке, а не официальные.

Одинаковые строки склеиваются, показываются первые три, дальше «и ещё N».
Название — из `OlympiadRef.olympiad_name` без «Олимпиада школьников» в
начале; новых словарей названий здесь нет.
"""
from __future__ import annotations

import re

SHOWN_SITES = ('official', 'ile')
MAX_LINES = 3

STAGES = {
    'final': 'заключительный этап',
    'qualifying': 'отборочный этап',
    'regional': 'региональный этап',
    'municipal': 'муниципальный этап',
}

_NAME_PREFIX = re.compile(r'^Олимпиада школьников\s+', re.IGNORECASE)
#: Вариант, который ничего не говорит ученику: служебный `v1`, номер таблицы
#: агрегатора, повтор класса («11 класс»).
_NOISE_VARIANT = re.compile(r'^(v1|table-\d+)$|класс', re.IGNORECASE)


def _year(academic_year, year):
    text = (academic_year or '').strip()
    m = re.fullmatch(r'(\d{4})\s*/\s*(\d{2,4})', text)
    if m:
        return f'{m.group(1)}/{m.group(2)[-2:]}'
    return text or (str(year) if year else '')


def _grade(grade):
    g = (grade or '').strip().replace('-', '–')
    if not g:
        return ''
    return f'{g} {"классы" if "–" in g else "класс"}'


def _variant(variant):
    v = (variant or '').strip()
    if not v or _NOISE_VARIANT.search(v):
        return ''
    m = re.fullmatch(r'v(\d+)', v)
    return f'вариант {m.group(1)}' if m else v


def _number(number):
    n = (number or '').strip()
    if not n:
        return ''
    if n.startswith('тест-'):
        return f'тест, вопрос {n[len("тест-"):]}'
    return f'задание {n}'


def ref_line(ref):
    """Одна строка привязки: «Высшая проба» по экономике · 2018/19 · …»."""
    pieces = [
        _NAME_PREFIX.sub('', (ref.olympiad_name or ref.olympiad_slug or '').strip()),
        _year(ref.academic_year, ref.year),
        STAGES.get(ref.stage or '', ''),
        _grade(ref.grade),
        _variant(ref.variant),
        _number(ref.number),
    ]
    return ' · '.join(p for p in pieces if p)


def olympiad_lines(refs):
    """{'lines': [до трёх строк], 'more': сколько ещё} по привязкам задачи."""
    lines = []
    for ref in sorted(refs, key=lambda r: (r.source_site != 'official', -(r.year or 0), r.id or 0)):
        if ref.source_site not in SHOWN_SITES:
            continue
        line = ref_line(ref)
        if line and line not in lines:
            lines.append(line)
    return {'lines': lines[:MAX_LINES], 'more': max(0, len(lines) - MAX_LINES)}
