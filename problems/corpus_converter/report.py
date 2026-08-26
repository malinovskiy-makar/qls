# -*- coding: utf-8 -*-
"""Общий сборщик отчёта «было -> стало» для команд corpus_pilot_ile и
corpus_pilot_shkolkovo — чтобы формат записи не разъезжался между двумя
командами."""
from __future__ import annotations


def render_entry(problem_id, source_label, before, after, extra_note=''):
    """Один блок отчёта: заголовок с id/источником, «было» (сырые поля из
    before), «стало» (converted-поля из after)."""
    lines = [f'### #{problem_id} — {source_label}', '']
    if extra_note:
        lines.append(f'_{extra_note}_')
        lines.append('')
    lines.append('**Было:**')
    lines.append('```')
    for key, value in before.items():
        lines.append(f'{key}: {value}')
    lines.append('```')
    lines.append('')
    lines.append('**Стало:**')
    lines.append('```')
    for key, value in after.items():
        lines.append(f'{key}: {value}')
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
