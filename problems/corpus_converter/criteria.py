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

    Известное ограничение (проверено на реальной выборке из 6 задач диска):
    парсер распознаёт только один устойчивый формат — заголовок «Критерии»
    плюс пункты «N)»/«-» с баллами в $...$. Остальные форматы (сплошная
    проза без пунктов, схема «- $N$ **балл**» без $-обёртки числа) дают 0
    критериев с явным предупреждением — как и parse_shkolkovo_criteria,
    молчания на непонятном формате нет. Слово «Критерии» изредка встречается
    не как заголовок баллов, а как обычный термин (пример #5578: «Критерии
    оптимума для функций полезности...») — такой случай тоже даст пустой
    список с предупреждением, ложного извлечения баллов из математики он
    не совершит (проверено: #5578 и #3609 дают 0 пунктов, не мусор)."""
    if not answer_md:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    header = _SOLVEHUB_CRITERIA_HEADER_RE.search(answer_md)
    if not header:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    criteria = []
    warnings = []
    tail = answer_md[header.end():]

    for order, item_match in enumerate(_SOLVEHUB_ITEM_RE.finditer(tail)):
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

    if not criteria:
        warnings.append(
            f'найдено слово «Критерии» в answer_md ({len(answer_md)} симв.), но не распознано '
            f'ни одного пункта вида «N)» или «-» с баллами в $...$ — формат не подходит под '
            f'единственный поддерживаемый парсером шаблон'
        )

    return {'rubric_name': 'Критерии оценивания', 'criteria': criteria, 'warnings': warnings}
