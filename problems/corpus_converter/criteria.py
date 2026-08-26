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
