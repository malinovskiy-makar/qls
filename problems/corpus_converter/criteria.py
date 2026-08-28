# -*- coding: utf-8 -*-
"""Школково: criteria_tex (проза, структурированная по \\textbf{(метка)} +
\\begin{itemize}) -> кандидат Rubric/RubricCriterion.

Единственный источник банка со структурными критериями (CORPUS-FORMAT.md
§3: "маппинг в Rubric берётся даром" у 836 задач Школково) — но баллы
внутри каждого \\item всё равно нужно вытащить из русской прозы
("3 балла за ...", "1 балл за ..."), это и есть менее тривиальная часть,
явно выделенная спекой в отдельный файл."""
from __future__ import annotations

import re

from problems.corpus_converter.core import convert_text_field

_PART_BLOCK_RE = re.compile(
    r'\\textbf\{(\([^)]*\))\}\s*\\begin\{itemize\}(.*?)\\end\{itemize\}',
    re.DOTALL,
)
_ITEM_RE = re.compile(r'\\item\s*(.*?)(?=\\item|\Z)', re.DOTALL)
#: "3 балла за ..." / "1 балл за ..." / "5 баллов за ..." — число в начале
#: пункта, за которым следует слово "балл"/"балла"/"баллов".
_POINTS_RE = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*балл(?:а|ов)?\b')


def parse_shkolkovo_criteria(criteria_tex):
    """criteria_tex -> {'rubric_name', 'criteria': [...], 'warnings': [...]}."""
    if not criteria_tex:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    criteria = []
    warnings = []
    order = 0

    for block_match in _PART_BLOCK_RE.finditer(criteria_tex):
        label = block_match.group(1)
        body = block_match.group(2)
        for item_match in _ITEM_RE.finditer(body):
            raw_item = item_match.group(1).strip()
            if not raw_item:
                continue
            points_match = _POINTS_RE.match(raw_item)
            if points_match:
                max_points = float(points_match.group(1).replace(',', '.'))
            else:
                max_points = None
                warnings.append(f'критерий без баллов в прозе: {label} — {raw_item[:60]}')
            description = convert_text_field(raw_item)['text_md']
            criteria.append({
                'name': f'{label} {description}'.strip(),
                'max_points': max_points,
                'description': description,
                'order': order,
            })
            order += 1

    if not criteria:
        warnings.append(
            f'criteria_tex непустой ({len(criteria_tex)} симв.), но не распознано ни одного '
            f'критерия — формат не соответствует ожидаемому \\textbf{{(метка)}}\\begin{{itemize}}'
        )

    return {'rubric_name': 'Критерии оценивания', 'criteria': criteria, 'warnings': warnings}


#: SolveHub (атлас: критерии вклеены в answer_md прозой, слово «критери*» у
#: 26 задач, схема «+N баллов» у 41). Заголовок — устойчиво слово «Критерии»
#: в именительном падеже (например «***Критерии****:*») ИЛИ «Критерии
#: проверки»/«Критерии оценивания...» — но НЕ любая словоформа: живой пример
#: #3609 использует «критериям» (дательный падеж, обычная экономическая
#: лексика про ранжирование вузов, не про баллы) — точное слово исключает
#: этот класс ложных срабатываний. Остаточный риск задокументирован ниже.
_SOLVEHUB_CRITERIA_HEADER_RE = re.compile(r'(?i)\bкритерии\b')
#: Пункт — либо "N)", либо "-" в начале строки, перед которыми может стоять
#: markdown-звёздочка (разметка в источнике хаотична: "*1)  Дан ответ...",
#: "*-Если нет..." — живые примеры #6371/#6347).
_SOLVEHUB_ITEM_RE = re.compile(
    r'(?:^|\n)\s*\*?\s*(?:(\d+)\)|-)\s*(.*?)(?=\n\s*\*?\s*(?:\d+\)|-)|\Z)',
    re.DOTALL,
)
#: Баллы — знаковое число внутри $...$, за которым (возможно, через
#: markdown-звёздочку) следует «балл»/«балла»/«баллов». Скобки вокруг НЕ
#: обязательны — у #6347 баллы идут без скобок ("$-15$ баллов").
_SOLVEHUB_POINTS_RE = re.compile(r'\$\s*([+-]?\d+(?:[.,]\d+)?)\s*\$\s*\*?\s*балл')


def parse_solvehub_criteria(answer_md):
    """answer_md -> {'rubric_name', 'criteria': [...], 'warnings': [...]}.

    Известное ограничение: парсер уверенно распознаёт только пункты вида
    «N)»/«-» с баллами в $...$. Остальные форматы (сплошная проза без
    пунктов, схема «- $N$ **балл**» без $-обёртки числа) дают 0 критериев
    для своего раздела с явным предупреждением — молчания на непонятном
    формате нет. Слово «Критерии» изредка встречается не как заголовок
    баллов, а как обычный термин (пример #5578: «Критерии оптимума для
    функций полезности...») — такой случай тоже даёт пустой список с
    предупреждением, ложного извлечения баллов из математики он не
    совершает.

    Дефект, найденный ревью 2026-08-26 (задача #3498 — three-part answer,
    "1) ... 2) ... 3) ..." с ТРЕМЯ отдельными разделами «Критерии», по
    одному на часть): раньше искали только ПЕРВЫЙ заголовок «Критерии» и
    сканировали пункты до КОНЦА всего answer_md — regex «N)» цеплял
    границы следующих частей ответа ("2)", "3)") как будто это пункты
    критериев, а настоящие (неномерованные, прозой) критерии части 1
    терялись без единого warning. Починка в две части:
    1. Обрабатываются ВСЕ заголовки «Критерии» (через finditer), каждый —
       в границах до СЛЕДУЮЩЕГО заголовка (не до конца строки).
    2. Если первый найденный номер последовательности "N)" внутри раздела
       — не "1" (значит распознали границу ЧАСТИ ответа, а не пункт
       критерия — настоящие критерии всегда начинаются с "1)"), раздел
       НЕ разбирается вовсе — лучше честный warning, чем чужой текст в
       описании критерия.
    Плюс отдельная страховка после всех разделов: любое "N баллов" в
    прозе, не попавшее в текст ни одного извлечённого критерия, поднимает
    предупреждение — так неномерованные критерии части 1 задачи #3498
    (раньше терялись молча) теперь как минимум видны в отчёте."""
    if not answer_md:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    headers = list(_SOLVEHUB_CRITERIA_HEADER_RE.finditer(answer_md))
    if not headers:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    criteria = []
    warnings = []
    order = 0
    claimed_spans = []

    for i, header in enumerate(headers):
        region_end = headers[i + 1].start() if i + 1 < len(headers) else len(answer_md)
        tail = answer_md[header.end():region_end]

        items = list(_SOLVEHUB_ITEM_RE.finditer(tail))
        numbered = [m for m in items if m.group(1)]
        if numbered and numbered[0].group(1) != '1':
            warnings.append(
                f'заголовок «Критерии» найден, но следующие "N)" похожи на границы частей '
                f'ответа, а не на пункты критериев (первая метка "{numbered[0].group(1)})", '
                f'не "1)") — раздел пропущен, нужен ручной разбор'
            )
            continue

        found_any = False
        for item_match in items:
            raw_item = item_match.group(2).strip()
            if not raw_item:
                continue
            points_match = _SOLVEHUB_POINTS_RE.search(raw_item)
            if points_match:
                max_points = float(points_match.group(1).replace(',', '.'))
            else:
                max_points = None
                warnings.append(f'критерий без баллов в прозе: {raw_item[:60]}')
            description = convert_text_field(raw_item)['text_md']
            criteria.append({
                'name': description[:80],
                'max_points': max_points,
                'description': description,
                'order': order,
            })
            order += 1
            found_any = True
            claimed_spans.append((header.end() + item_match.start(), header.end() + item_match.end()))

        if not found_any:
            warnings.append(
                f'заголовок «Критерии» найден ({len(tail)} симв. до следующего раздела/конца), '
                f'но не распознано ни одного пункта вида «N)» или «-» с баллами в $...$'
            )

    for points_match in _SOLVEHUB_POINTS_RE.finditer(answer_md):
        if any(start <= points_match.start() < end for start, end in claimed_spans):
            continue
        snippet = answer_md[max(0, points_match.start() - 20):points_match.end() + 60]
        warnings.append(
            f'баллы в прозе вне извлечённых критериев (возможна частичная потеря): '
            f'"...{snippet}..."'
        )

    return {'rubric_name': 'Критерии оценивания', 'criteria': criteria, 'warnings': warnings}
