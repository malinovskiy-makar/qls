# -*- coding: utf-8 -*-
"""ВсОШ: таблица покрытия «этап × сезон × регион» — где задания, где решения."""
from __future__ import annotations

from collections import defaultdict

from problems.olympiad_audit.vsosh_prepare import role_of

STAGE_RU = {'final': 'ЗЭ', 'regional': 'РЭ', 'municipal': 'МЭ', 'school': 'ШЭ',
            'invitational': 'Пригл.'}
STAGE_ORDER = ('final', 'regional', 'municipal', 'school', 'invitational')


def cells(rows):
    """{(stage, season, region_code): {'region_name', 'tasks', 'solutions', 'grades'}}
    по скачанным файлам (дубли считаются: важно, ЕСТЬ ли файл)."""
    out = defaultdict(lambda: {'region_name': '', 'tasks': 0, 'solutions': 0,
                               'grades': set(), 'sources': set()})
    for r in rows:
        if r.get('status') != 'ok' or (r.get('subject') or 'econ') != 'econ':
            continue
        role = role_of(r.get('kind'))
        if not role:
            continue
        stage = r.get('stage')
        if stage not in STAGE_RU:
            continue
        c = out[(stage, r.get('season') or '?', r.get('region_code') or 'ru')]
        c['region_name'] = c['region_name'] or r.get('region_name') or ''
        if role == 'tasks':
            c['tasks'] += 1
            if r.get('kind') == 'tasks+solutions' or r.get('with_solutions'):
                c['solutions'] += 1
        else:
            c['solutions'] += 1
        if r.get('grades'):
            c['grades'].add(r['grades'])
        c['sources'].add((r.get('source') or '').split(':')[0])
    return out


def _seasons(start=1995, end=2026):
    return [f'{y}/{(y + 1) % 100:02d}' for y in range(start, end + 1)]


def markdown(rows, title='Покрытие ВсОШ по экономике'):
    cs = cells(rows)
    lines = [f'# {title}', '',
             'Клетка: `З` — есть задания, `Р` — есть решения/ответы/критерии, `—` — нет ничего. '
             'Считаются скачанные файлы экономики (дубли тоже: важно, есть ли файл).', '']
    # 1. ЗЭ и РЭ по сезонам.
    lines += ['## ЗЭ и РЭ по сезонам', '', '| сезон | ЗЭ | РЭ |', '|---|---|---|']
    for s in _seasons():
        row = []
        for st in ('final', 'regional'):
            c = cs.get((st, s, 'ru'))
            row.append(_mark(c))
        if any(x != '—' for x in row):
            lines.append(f'| {s} | ' + ' | '.join(row) + ' |')
    missing = []
    for s in _seasons(1995, 2025):
        for st in ('final', 'regional'):
            c = cs.get((st, s, 'ru'))
            if not c or not c['tasks']:
                missing.append(f'{STAGE_RU[st]} {s}: нет заданий')
            elif not c['solutions']:
                missing.append(f'{STAGE_RU[st]} {s}: нет решений')
    lines += ['', '**Чего не хватает (ЗЭ/РЭ, 1995/96–2025/26):** ' +
              ('; '.join(missing) if missing else 'всё на месте'), '']
    # 2. МЭ / ШЭ / пригласительный по регионам.
    for st in ('municipal', 'school', 'invitational'):
        regions = sorted({k[2] for k in cs if k[0] == st},
                         key=lambda x: (x != '77', int(x) if x.isdigit() else 999))
        if not regions:
            continue
        seasons = sorted({k[1] for k in cs if k[0] == st})
        lines += [f'## {STAGE_RU[st]} по регионам', '',
                  '| регион | ' + ' | '.join(s[2:] for s in seasons) + ' | сезонов З | без Р |',
                  '|---|' + '---|' * (len(seasons) + 2)]
        for reg in regions:
            name = next((cs[k]['region_name'] for k in cs if k[0] == st and k[2] == reg
                         and cs[k]['region_name']), '')
            marks = [_mark(cs.get((st, s, reg)), short=True) for s in seasons]
            n_t = sum(1 for s in seasons if (cs.get((st, s, reg)) or {}).get('tasks'))
            n_ns = sum(1 for s in seasons if (cs.get((st, s, reg)) or {}).get('tasks')
                       and not cs[(st, s, reg)]['solutions'])
            lines.append(f'| {reg} {name} | ' + ' | '.join(marks) + f' | {n_t} | {n_ns} |')
        lines.append('')
    return '\n'.join(lines) + '\n'


def _mark(c, short=False):
    if not c or (not c['tasks'] and not c['solutions']):
        return '—' if not short else '·'
    s = ('З' if c['tasks'] else '') + ('Р' if c['solutions'] else '')
    return s


def summary(rows):
    """Короткие числа для Notion: пар «этап-сезон-регион» с заданиями / с решениями."""
    cs = cells(rows)
    out = {}
    for st in STAGE_ORDER:
        keys = [k for k in cs if k[0] == st]
        out[st] = {'cells_with_tasks': sum(1 for k in keys if cs[k]['tasks']),
                   'cells_with_solutions': sum(1 for k in keys if cs[k]['tasks'] and cs[k]['solutions']),
                   'regions': len({k[2] for k in keys}),
                   'seasons': len({k[1] for k in keys})}
    return out
