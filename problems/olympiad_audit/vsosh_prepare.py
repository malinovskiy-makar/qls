# -*- coding: utf-8 -*-
"""ВсОШ: подготовка к оцифровке — цели, конвертация, отрисовка, пары, план.

Из манифеста берутся ГЛАВНЫЕ копии (без `dup_of`) файлов заданий, решений,
ответов и критериев; методички, видео и предпринимательство в оцифровку не
идут (предпринимательство — своя группа «позже»). Протоколы и списки
победителей — персональные данные — не идут никогда (`digitize.personal_data_hit`).

Пары «задания ↔ решения» — по метаданным источника: (этап, сезон, регион,
классы, тур). Решение без тура ложится ко всем турам своих классов
(флаг `solutions_shared_across_tours`), решение на диапазон классов
(«9-11») — ко всем комплектам, чьи классы внутри диапазона.

Комплект — `event_id` вида
`vseros-{stage}-{2024-25}-{region|ru}-{grades}-{tour}` (тур пустой — `all`).
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict

from problems.olympiad_audit import digitize

TASK_KINDS = ('tasks', 'test', 'essay', 'tasks+solutions')
SOLUTION_KINDS = ('solutions', 'answers')
CRITERIA_KINDS = ('criteria',)
DOC_FORMATS = ('doc', 'docx', 'rtf', 'odt')

#: Группы плана оцифровки (приоритет и модель — по ним).
GROUPS = {
    1: 'ЗЭ все годы',
    2: 'РЭ все годы',
    3: 'Москва: МЭ, ШЭ, пригласительный',
    4: 'МЭ регионов',
    5: 'ШЭ регионов',
    6: 'предпринимательство (позже)',
}

#: Крупные регионы — порядок внутри группы 4 (население, грубо).
BIG_REGIONS = ('50', '78', '23', '66', '2', '16', '61', '52', '74', '63', '24', '54',
               '59', '34', '36', '42', '55', '26', '64', '3', '1')


def group_of(row):
    if (row.get('subject') or 'econ') != 'econ':
        return 6
    stage, reg = row.get('stage'), row.get('region_code')
    if stage == 'final':
        return 1
    if stage == 'regional':
        return 2
    if reg == '77':
        return 3
    if stage == 'municipal':
        return 4
    return 5


def role_of(kind):
    if kind in TASK_KINDS:
        return 'tasks'
    if kind in SOLUTION_KINDS:
        return 'solutions'
    if kind in CRITERIA_KINDS:
        return 'criteria'
    return ''


def season_slug(season):
    return str(season or 'unknown').replace('/', '-')


def grade_list(grades):
    """«9-11» → [9, 10, 11]; «» → []."""
    m = re.fullmatch(r'(\d{1,2})(?:-(\d{1,2}))?', str(grades or ''))
    if not m:
        return []
    lo = int(m.group(1))
    hi = int(m.group(2) or lo)
    return list(range(lo, hi + 1))


def event_id_for(stage, season, region_code, grades, tour):
    return '-'.join(['vseros', stage or 'unknown', season_slug(season), region_code or 'ru',
                     grades or 'all', tour or 'all'])


def digitize_targets(manifest):
    """(цели, исключённые с причиной) из манифеста."""
    targets, excluded = [], []
    for r in manifest:
        if r.get('status') != 'ok':
            continue
        if r.get('dup_of'):
            continue
        fmt = r.get('format')
        reason = ''
        if fmt not in ('pdf',) + DOC_FORMATS:
            reason = f'формат {fmt}'
        elif not role_of(r.get('kind')):
            reason = f'не задания ({r.get("kind")})'
        elif r.get('stage') not in ('final', 'regional', 'municipal', 'school', 'invitational'):
            reason = 'этап не определён'
        if reason:
            excluded.append(dict(r, exclude_reason=reason))
            continue
        targets.append(r)
    return targets, excluded


def pdf_path_for(data_root, row):
    """Путь к PDF цели: оригинал или сконвертированный Word'ом."""
    if row.get('format') == 'pdf':
        return os.path.join(data_root, row['path'])
    return os.path.join(data_root, 'digitized', 'v1', 'converted', row['sha256'][:16] + '.pdf')


def conversion_list(data_root, targets):
    """[(src, dst)] для Word: только doc/docx/rtf."""
    out = []
    for r in targets:
        if r.get('format') in DOC_FORMATS:
            out.append((os.path.normpath(os.path.join(data_root, r['path'])),
                        os.path.normpath(pdf_path_for(data_root, r))))
    return out


def first_page_text(png_dir):
    path = os.path.join(png_dir, 'p1.txt')
    return open(path, encoding='utf-8').read() if os.path.isfile(path) else ''


def build_events(targets):
    """Комплекты из целей: {event_id: {meta…, task_files, solution_files,
    criteria_files, flags}} и список решений без пары."""
    tasks_by_key = defaultdict(list)
    sols = []
    for r in targets:
        role = role_of(r.get('kind'))
        if role == 'tasks':
            key = (r['stage'], r['season'], r['region_code'], r.get('grades') or '',
                   r.get('tour') or '')
            tasks_by_key[key].append(r)
        else:
            sols.append((role, r))
    events = {}
    for key, files in tasks_by_key.items():
        stage, season, reg, grades, tour = key
        eid = event_id_for(stage, season, reg, grades, tour)
        f0 = files[0]
        events[eid] = {
            'event_id': eid, 'olympiad_slug': 'vseros', 'stage': stage,
            'academic_year': season, 'year': _end_year(season), 'grade': grades,
            'region_code': reg, 'region_name': f0.get('region_name', ''),
            'tour': tour, 'variant': '', 'official': True,
            'source': 'official', 'task_files': files, 'solution_files': [],
            'criteria_files': [], 'flags': [],
            'source_urls': [f['url'] for f in files],
        }
    orphans = []
    for role, s in sols:
        matches = match_solution(events, s)
        if not matches:
            orphans.append(s)
            continue
        tours = {events[e]['tour'] for e in matches}
        for e in matches:
            events[e]['solution_files' if role == 'solutions' else 'criteria_files'].append(s)
            if len(tours) > 1 and not s.get('tour'):
                if 'solutions_shared_across_tours' not in events[e]['flags']:
                    events[e]['flags'].append('solutions_shared_across_tours')
    for ev in events.values():
        if not ev['solution_files'] and not ev['criteria_files'] and not any(
                f.get('kind') == 'tasks+solutions' or f.get('with_solutions')
                for f in ev['task_files']):
            ev['flags'].append('нет_решений')
    return events, orphans


def _end_year(season):
    m = re.match(r'(\d{4})/(\d{2})', str(season or ''))
    return int(m.group(1)) + 1 if m else None


def match_solution(events, s):
    """Комплекты, к которым ложится файл решений/критериев `s`."""
    same = [e for e in events.values()
            if (e['stage'], e['academic_year'], e['region_code']) ==
            (s['stage'], s['season'], s['region_code'])]
    if not same:
        return []
    sg, st = s.get('grades') or '', s.get('tour') or ''
    if st:
        tour_ok = [e for e in same if e['tour'] in (st, '')]
        same = tour_ok or same
    exact = [e['event_id'] for e in same if e['grade'] == sg]
    if exact:
        return exact
    if sg:
        span = set(grade_list(sg))
        inside = [e['event_id'] for e in same if grade_list(e['grade']) and
                  set(grade_list(e['grade'])) <= span]
        if inside:
            return inside
        overlap = [e['event_id'] for e in same if set(grade_list(e['grade'])) & span]
        return overlap
    # Классы решения неизвестны: единственная группа классов — её.
    grades = {e['grade'] for e in same}
    if len(grades) == 1:
        return [e['event_id'] for e in same]
    return []


def plan(events, page_counts, flash_usd=0.00116, sonnet_usd=None, haiku_usd=None):
    """Страницы и деньги по группам: {группа: {...}}. page_counts — {sha: pages}."""
    out = defaultdict(lambda: Counter())
    seen = set()
    for ev in events.values():
        g = group_of({'subject': ev['task_files'][0].get('subject', 'econ'),
                      'stage': ev['stage'], 'region_code': ev['region_code']})
        out[g]['events'] += 1
        for key in ('task_files', 'solution_files', 'criteria_files'):
            for f in ev[key]:
                if f['sha256'] in seen:
                    continue
                seen.add(f['sha256'])
                out[g]['files'] += 1
                out[g]['pages'] += int(page_counts.get(f['sha256']) or 0)
    res = {}
    for g, c in sorted(out.items()):
        row = dict(c)
        row['name'] = GROUPS[g]
        row['flash_usd'] = round(c['pages'] * flash_usd * 1.15, 2)   # +15 % на повторы
        if sonnet_usd:
            row['sonnet_batch_usd'] = round(c['pages'] * sonnet_usd, 2)
        if haiku_usd:
            row['haiku_batch_usd'] = round(c['pages'] * haiku_usd, 2)
        res[g] = row
    return res


def _render_one(args):
    pdf, out_dir = args
    try:
        pages, _drawn = digitize.render_pdf(pdf, out_dir)
        return len(pages), ''
    except Exception as exc:  # битый PDF — 0 страниц и причина
        return 0, f'{type(exc).__name__}: {exc}'[:200]


def render_all(data_root, targets, digitized, log=print, workers=8):
    """PDF целей → pages\<sha16>\p<N>.png/.txt (готовое не перерисовывается).

    Процессами (fitz не потокобезопасен). Возвращает {sha256: страниц};
    не открывшиеся PDF — со значением 0."""
    from concurrent.futures import ProcessPoolExecutor
    counts, tasks = {}, []
    for r in targets:
        pdf = pdf_path_for(data_root, r)
        if not os.path.isfile(pdf):
            counts[r['sha256']] = 0
            continue
        tasks.append((r, (pdf, os.path.join(digitized, digitize.page_dir_for(r['sha256'])))))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, ((r, _a), (n, err)) in enumerate(
                zip(tasks, pool.map(_render_one, [a for _r, a in tasks], chunksize=4)), 1):
            counts[r['sha256']] = n
            if err:
                log(f'  не отрисован {r["path"]}: {err}')
            if i % 100 == 0:
                log(f'  … {i}/{len(tasks)} файлов')
    return counts
