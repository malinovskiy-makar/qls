# -*- coding: utf-8 -*-
"""Максимальный балл задания там, где он выводится однозначно (сессия v5, 14.10.2026).

Без модели, по тексту задания эталона. Источники по старшинству:

1. **шапка задания** — «Задача 1. «Подарок от бабушки» (45 баллов)» в начале
   условия, в названии или в повторе задачи в файле решений/критериев;
2. **сумма баллов пунктов** — «А) (5 баллов)», «1) (2 балла)», «(а) (6 баллов)»,
   «Пункт №1 (8 баллов)», «1. (12 баллов за пункт 1)» в начале строк (не меньше
   двух пунктов; сначала в условии, иначе в решении; баллы — в скобках, строки
   критериев «(1) 1 балл за…» пунктами не считаются);
3. **итог таблицы критериев** — «Итого за задачу: 20 баллов» (подытоги
   «Итого: 3 балла» без «за задачу/задание» не берутся).

Заполняется только пустой `max_score` и только если все найденные источники
дают одно число. Расхождение источников (или источника с уже стоящим
`max_score`) — в список, без правки: под «100 за комплект» ничего не
подгоняется (у ВП с 2022/23 пять задач по 25).
"""
from __future__ import annotations

import re

_HEADER = re.compile(r'(?:задач\w*|задани\w*)\b[^\n]{0,160}?\((\d{1,3})\s*балл\w*\)', re.IGNORECASE)
_TITLE = re.compile(r'\((\d{1,3})\s*балл\w*\)')
_ITEM = re.compile(
    r'(?m)^[\s*#>\-]*(?:(?:\(?([А-Еа-еA-Ea-e])\))|(\d{1,2})[.)]|пункт\s*№?\s*(\d{1,2}))'
    r'[\s*:.]*\((?:\*\*)?\s*(\d{1,3})\s*балл\w*(?:\s+за\s+пункт\s*\d+)?(?:\*\*)?\)',
    re.IGNORECASE)
_TOTAL = re.compile(r'(?m)^[\s*#>\-]*(?:итого|всего|максимальн\w*\s+(?:сумма|количество|балл)\w*)'
                    r'[^\n]{0,40}?за\s+(?:задач|задани)\w*\s*[:—–=-]?\s*(\d{1,3})\s*балл', re.IGNORECASE)


def _lines(text, n=2):
    return '\n'.join([x for x in (text or '').splitlines() if x.strip()][:n])


def header_points(row):
    """Баллы из шапки задания (условие, название, повтор задачи в решении/критериях)."""
    for text in (row.get('title') or '',):
        m = _TITLE.search(text)
        if m:
            return int(m.group(1))
    for field in ('statement_md', 'solution_md', 'criteria_md'):
        head = _lines(row.get(field))
        m = _HEADER.search(head)
        if m and 'за пункт' not in head[m.start():m.end() + 12].lower():
            return int(m.group(1))
    return None


def item_points(text):
    """Сумма баллов пунктов в начале строк (≥ 2 разных пункта) или None."""
    items = {}
    for m in _ITEM.finditer(text or ''):
        label = (m.group(1) or m.group(2) or m.group(3) or '').lower()
        if label and label not in items:
            items[label] = int(m.group(4))
    return sum(items.values()) if len(items) >= 2 else None


def total_points(text):
    found = _TOTAL.findall(text or '')
    return int(found[-1]) if found else None


def infer(row):
    """{'sources': {источник: число}, 'value': число | None, 'status': …}.

    status: `filled` (пустой max_score заполнен), `kept` (уже стоит и источники
    согласны или их нет), `conflict` (источники расходятся между собой),
    `differs` (источник расходится с уже стоящим max_score), `none` (нечего брать)."""
    sources = {}
    head = header_points(row)
    if head is not None:
        sources['шапка'] = head
    for field, name in (('statement_md', 'пункты условия'), ('solution_md', 'пункты решения')):
        value = item_points(row.get(field))
        if value is not None:
            sources[name] = value
            break
    total = total_points(row.get('criteria_md'))
    if total is not None:
        sources['итог критериев'] = total
    values = set(sources.values())
    current = row.get('max_score')
    has = current not in (None, '')
    if len(values) > 1:
        return {'sources': sources, 'value': None, 'status': 'conflict'}
    if not values:
        return {'sources': sources, 'value': None, 'status': 'kept' if has else 'none'}
    value = values.pop()
    if has:
        try:
            same = float(current) == float(value)
        except (TypeError, ValueError):
            same = False
        return {'sources': sources, 'value': None, 'status': 'kept' if same else 'differs'}
    return {'sources': sources, 'value': value, 'status': 'filled'}


def fill(rows):
    """Заполнить пустые max_score на месте; журнал [(ключ, статус, источники, было, стало)]."""
    log = []
    for r in rows:
        res = infer(r)
        key = (r['event_id'], r['number'], r.get('task_variant') or '')
        before = r.get('max_score')
        if res['status'] == 'filled':
            r['max_score'] = res['value']
            r['max_score_source'] = ', '.join(res['sources'])
        log.append((key, res['status'], res['sources'], before, r.get('max_score')))
    return log
