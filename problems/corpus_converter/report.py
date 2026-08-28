# -*- coding: utf-8 -*-
"""Общий сборщик отчёта «было -> стало» для команд corpus_pilot_ile и
corpus_pilot_shkolkovo — чтобы формат записи не разъезжался между двумя
командами."""
from __future__ import annotations


def _render_fields(fields):
    """Один ряд полей dict-а: каждое поле — одна строка `key: value`,
    кроме списков: непустой список рисуется заголовком и построчно, каждый
    элемент — своей строкой с отступом (не сырой repr)."""
    out = []
    for key, value in fields.items():
        if isinstance(value, list) and value:
            out.append(f'{key}:')
            for item in value:
                out.append(f'  - {item}')
        else:
            out.append(f'{key}: {value}')
    return out


def render_entry(problem_id, source_label, before, after, extra_note=''):
    """Один блок отчёта: заголовок с id/источником, «было» (сырые поля из
    before), «стало» (converted-поля из after)."""
    lines = [f'### #{problem_id} — {source_label}', '']
    if extra_note:
        lines.append(f'_{extra_note}_')
        lines.append('')
    lines.append('**Было:**')
    lines.append('```')
    lines.extend(_render_fields(before))
    lines.append('```')
    lines.append('')
    lines.append('**Стало:**')
    lines.append('```')
    lines.extend(_render_fields(after))
    lines.append('```')
    lines.append('')
    return '\n'.join(lines)


def render_report(title, entries, warnings_summary):
    """Собрать полный report.md: заголовок, все записи, сводка warnings."""
    parts = [f'# {title}', '']
    parts.extend(entries)
    parts.append('## Warnings и сложные случаи')
    parts.append('')
    parts.append(warnings_summary)
    return '\n'.join(parts)
