# -*- coding: utf-8 -*-
"""Точечные правки текста эталона по сверке глазами: vA + правки → vB.

Перенесено из инструментов ночной сессии v4 (13.10.2026,
`weconomics-data\\olympiads\\v4_work\\engine.py`, `apply.py`, `autofix.py`)
без изменения поведения: тот же v3 + те же 90 правок дают побайтно тот же
v4 (инвариант сессии v5, 14.10.2026).

Правки — ДАННЫЕ, не код: файл `fixes_vN.json` лежит рядом с данными
(`weconomics-data\\olympiads\\v5_work\\`). Правка — словарь
`{set, page, op, find, rep, min, note}`:

* `page` — `<sha16>/p<N>` (правка ищется в заданиях, которые питает эта
  страница; не нашлась — во всём комплекте этих заданий, потом во всех
  заданиях того же файла) или `ev:<event_id>` (весь комплект);
* `op`: `lit` — точная строка; `re` — регулярное выражение; `fn` — выражение,
  совпадение переводится по таблице `rep.translate` (кириллица → латиница);
  `del_line` — удалить строки, совпавшие целиком; `foot` — дописать сноску
  `rep` в поле, где стоит маркер `find`, а текста сноски нет;
* `min` — сколько замен ожидается не меньше.

Статусы журнала: `applied` (замен ≥ min), `partial` (меньше), `already_fixed`
(замены нет, а заменяющий текст уже стоит), `absent_in_<vA>` (искомого нет
нигде в эталоне), `not_found`, `ambiguous(N tasks)` (сноска подходит к
нескольким заданиям — не вставляется).

В базу ничего не пишет.
"""
from __future__ import annotations

import collections
import copy
import csv
import difflib
import json
import os
import re

STATUS_OK = ('applied', 'already_fixed')


# ── Данные ───────────────────────────────────────────────────────────────

def read_rows(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_rows(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # newline='\n': на Windows иначе CRLF, а эталоны записаны с LF.
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def page_map(digitized):
    """«файл#pN» → «<sha16>/pN» и «<sha16>» → файл (по `pages_manifest.jsonl`)."""
    by_ref, by_hash = {}, {}
    with open(os.path.join(digitized, 'pages_manifest.jsonl'), encoding='utf-8') as handle:
        for line in handle:
            item = json.loads(line)
            sha = item['page_dir'].split('/')[-1]
            by_ref[item['file'] + '#p%d' % item['page']] = sha + '/p%d' % item['page']
            by_hash[sha] = item['file']
    return by_ref, by_hash


def task_pages(row, by_ref):
    """Страницы условия, решения и критериев задания: {«<sha16>/pN»}."""
    out = set()
    for key in ('source_pages', 'solution_pages', 'criteria_pages'):
        for ref in row.get(key) or []:
            if ref in by_ref:
                out.add(by_ref[ref])
    return out


def text_fields(row):
    """(путь, текст) текстовых полей задания: условие, решение, ответ,
    критерии, название, тексты подпунктов."""
    for key in ('statement_md', 'solution_md', 'answer', 'criteria_md', 'title'):
        if isinstance(row.get(key), str):
            yield key, row[key]
    for i, part in enumerate(row.get('parts') or []):
        if isinstance(part, dict) and isinstance(part.get('text'), str):
            yield ('parts', i, 'text'), part['text']


def get_field(row, path):
    return row[path] if isinstance(path, str) else row[path[0]][path[1]][path[2]]


def put_field(row, path, value):
    if isinstance(path, str):
        row[path] = value
    else:
        row[path[0]][path[1]][path[2]] = value


def field_name(path):
    return path if isinstance(path, str) else 'parts[%d]' % path[1]


def load_fixes(path):
    """`fixes_vN.json` → список кортежей (set, page, op, find, rep, min, note)."""
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    items = data['fixes'] if isinstance(data, dict) else data
    out = []
    for item in items:
        rep = item.get('rep', '')
        if item['op'] == 'fn':
            table = str.maketrans(rep['translate'])
            rep = (lambda table: lambda m: m.group(0).translate(table))(table)
        out.append((item['set'], item['page'], item['op'], item['find'], rep,
                    int(item.get('min', 1)), item.get('note', '')))
    return out


# ── Движок ───────────────────────────────────────────────────────────────

class Dataset:
    """Эталон одной олимпиады для правок: строки, страницы заданий, файлы."""

    def __init__(self, rows, by_ref, by_hash):
        self.rows = rows
        self.tp = [task_pages(r, by_ref) for r in rows]
        self.h2f = by_hash

    @classmethod
    def load(cls, digitized, rows):
        by_ref, by_hash = page_map(digitized)
        return cls(rows, by_ref, by_hash)


def _try_apply(rows, cand, op, find, rep):
    nrep, touched, present_rep = 0, [], False
    for k in cand:
        r = rows[k]
        for path, t in list(text_fields(r)):
            if op == 'lit':
                n = t.count(find)
                if n:
                    put_field(r, path, t.replace(find, rep))
                    nrep += n
                    touched.append((k, path))
                elif isinstance(rep, str) and rep and rep in t:
                    present_rep = True
            elif op in ('re', 'fn'):
                t2, n = re.subn(find, rep, t)
                if n:
                    put_field(r, path, t2)
                    nrep += n
                    touched.append((k, path))
                elif isinstance(rep, str) and rep and rep in t:
                    present_rep = True
            elif op == 'del_line':
                lines = t.split('\n')
                keep = [line for line in lines
                        if not re.fullmatch(r'\s*' + find + r'\s*', line.strip())
                        and not re.match(find, line.strip())]
                if len(keep) != len(lines):
                    nrep += len(lines) - len(keep)
                    put_field(r, path, '\n'.join(keep).strip())
                    touched.append((k, path))
            elif op == 'foot':
                if rep[:30] in t:
                    present_rep = True
                elif re.search(find, t) and not re.search(r'(^|\n)\s*(?:' + find + r')\s', t):
                    nrep += 1
                    touched.append((k, path))
    return nrep, touched, present_rep


def run(fixes, datasets):
    """Применить правки по порядку. `datasets` — {set: Dataset}; строки
    меняются на месте. Возвращает (исходные строки {set: [...]}, журнал)."""
    orig = {s: copy.deepcopy(d.rows) for s, d in datasets.items()}
    log = []
    for i, (s, page, op, find, rep, mn, note) in enumerate(fixes):
        if s not in datasets:
            continue
        data = datasets[s]
        rows, tp, h2f = data.rows, data.tp, data.h2f
        if page.startswith('ev:'):
            cand = [k for k, r in enumerate(rows) if r['event_id'] == page[3:]]
            scope = 'event'
        else:
            cand = [k for k, p in enumerate(tp) if page in p]
            scope = 'page'
        if op == 'foot':
            nrep, touched, pr = _try_apply(rows, cand, op, find, rep)
            if pr:
                status = 'already_fixed'
            elif nrep == 0:
                status = 'not_found'
            else:
                ks = sorted(set(k for k, _ in touched))
                if len(ks) > 1:
                    status = 'ambiguous(%d tasks)' % len(ks)
                else:
                    for k, path in touched:
                        t = get_field(rows[k], path)
                        put_field(rows[k], path, t.rstrip() + '\n\n' + rep)
                    status = 'applied'
                    nrep = len(touched)
            log.append(dict(i=i, set=s, page=page, op=op, find=find[:50], status=status, n=nrep,
                            mn=mn, scope=scope, tasks=sorted(set(k for k, _ in touched)),
                            note=note))
            continue
        nrep, touched, pr = _try_apply(rows, cand, op, find, rep)
        if nrep == 0 and not pr:
            # Не нашлось у заданий страницы: весь комплект этих заданий, затем
            # все задания того же файла (страницы ↔ задания в v3 бывают сдвинуты).
            evs = {rows[k]['event_id'] for k in cand}
            if evs and not page.startswith('ev:'):
                cand1 = [k for k, r in enumerate(rows) if r['event_id'] in evs]
                nrep, touched, pr = _try_apply(rows, cand1, op, find, rep)
                scope = 'event'
            f = h2f.get(page.split('/')[0])
            if nrep > 0 or pr:
                f = None
            cand2 = [k for k, r in enumerate(rows)
                     if r.get('source_file') == f or (f and f in json.dumps(r.get('source_pages')))]
            if f and cand2:
                nrep, touched, pr = _try_apply(rows, cand2, op, find, rep)
                scope = 'file'
        if nrep >= mn:
            status = 'applied'
        elif nrep > 0:
            status = 'partial'
        elif pr:
            status = 'already_fixed'
        else:
            status = 'not_found'
        log.append(dict(i=i, set=s, page=page, op=op, find=find[:50], status=status, n=nrep, mn=mn,
                        scope=scope, tasks=sorted(set(k for k, _ in touched)), note=note))
    return orig, log


# ── После правок: маркеры сносок, «нет нигде», автоисправления ───────────

SUPM = {'1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}


def supmarks(t):
    """Маркер сноски `^1` → `¹` вне формул."""
    parts = re.split(r'(\$\$.*?\$\$|\$[^$\n]*\$)', t, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'(?<=[А-Яа-яЁёA-Za-z.,;:»”)!?])\^\{?([1-9])\}?(?!\d)',
                          lambda m: SUPM[m.group(1)], parts[i])
    return ''.join(parts)


def postprocess(fixes, datasets, log, base_label):
    """Маркеры сносок в заданиях, куда вставлена сноска; `not_found`, чьего
    искомого нет нигде в эталоне, → `absent_in_<base_label>`."""
    for item in log:
        if item['op'] == 'foot' and item['status'] == 'applied':
            rows = datasets[item['set']].rows
            for k in item['tasks']:
                for path, t in list(text_fields(rows[k])):
                    t2 = supmarks(t)
                    if t2 != t:
                        put_field(rows[k], path, t2)
    for item in log:
        if item['status'] == 'not_found' and item['op'] in ('lit', 're', 'del_line', 'fn'):
            find = fixes[item['i']][3]
            rows = datasets[item['set']].rows
            pat = find if item['op'] != 'lit' else re.escape(find)
            hit = any(re.search(pat, t) for r in rows for _, t in text_fields(r))
            if not hit:
                item['status'] = 'absent_in_' + base_label
    return log


def status_ok(status):
    return status in STATUS_OK or status.startswith('absent_in_')


_ANSWER_LINE = re.compile(r'\s*(\*\*)?Ответ(ы)?\s*:')


def autofix(rows, set_name):
    """Безопасные автоисправления на месте: мягкий перенос U+00AD и точный
    повтор строки «Ответ: …» не дальше двух строк от первой. Журнал —
    [(set, idx, event, number, поле, действие)]."""
    log = []
    for k, r in enumerate(rows):
        for p, t in list(text_fields(r)):
            t0 = t
            if '­' in t:
                t = t.replace('­', '')
                log.append((set_name, k, r['event_id'], r['number'], field_name(p), 'U+00AD удалён'))
            if p != 'title':
                lines = t.split('\n')
                out, lastans, lastidx = [], None, -9
                for i, line in enumerate(lines):
                    if _ANSWER_LINE.match(line):
                        if lastans is not None and line.strip() == lastans and i - lastidx <= 2:
                            log.append((set_name, k, r['event_id'], r['number'], field_name(p),
                                        'удалён точный повтор: ' + line.strip()[:60]))
                            lastidx = i
                            continue
                        lastans, lastidx = line.strip(), i
                    out.append(line)
                t = '\n'.join(out)
            if t != t0:
                put_field(r, p, t)
    return log


# ── Отчёты ───────────────────────────────────────────────────────────────

def write_logs(out_dir, log, autofix_log=()):
    """fixes_log.csv, fixes_unapplied.csv, autofix_log.csv (UTF-8 с BOM, «;»)."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'fixes_log.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['set', 'page', 'op', 'find', 'status', 'n_applied', 'expected_min', 'scope',
                    'tasks_idx', 'note'])
        for x in log:
            w.writerow([x['set'], x['page'], x['op'], x['find'], x['status'], x['n'], x['mn'],
                        x['scope'], ' '.join(map(str, x['tasks'])), x['note']])
    with open(os.path.join(out_dir, 'fixes_unapplied.csv'), 'w', newline='',
              encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['set', 'page', 'op', 'find', 'status', 'note'])
        for x in log:
            if not status_ok(x['status']):
                w.writerow([x['set'], x['page'], x['op'], x['find'], x['status'], x['note']])
    with open(os.path.join(out_dir, 'autofix_log.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['set', 'idx', 'event', 'number', 'field', 'action'])
        w.writerows(autofix_log)


def changes_md(orig, rows, title):
    """«Было → стало» по каждому изменённому заданию (Markdown) и их число."""
    out, changed = [f'# {title}\n'], 0
    for k, (a, b) in enumerate(zip(orig, rows)):
        if a == b:
            continue
        changed += 1
        out.append('\n### %s №%s вар.%s (idx %d)' % (a['event_id'], a['number'],
                                                    a['task_variant'], k))
        for (p, t), (_p2, t2) in zip(text_fields(a), text_fields(b)):
            if t == t2:
                continue
            sm = difflib.SequenceMatcher(None, t, t2, autojunk=False)
            n = 0
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == 'equal':
                    continue
                n += 1
                if n > 6:
                    out.append('- … ещё правки в поле')
                    break
                out.append('- `%s`: «%s» → «%s»' % (
                    field_name(p), t[max(0, i1 - 25):i2 + 25].replace('\n', '⏎'),
                    t2[max(0, j1 - 25):j2 + 25].replace('\n', '⏎')))
    return '\n'.join(out), changed


def apply_version(digitized, src_rows, fixes, set_name, base_label, with_autofix=True):
    """vA (строки) + правки → (строки vB, журнал правок, журнал автоисправлений,
    исходные строки). Строки на входе не меняются."""
    rows = copy.deepcopy(src_rows)
    datasets = {set_name: Dataset.load(digitized, rows)}
    orig, log = run(fixes, datasets)
    postprocess(fixes, datasets, log, base_label)
    auto = autofix(rows, set_name) if with_autofix else []
    return rows, log, auto, orig[set_name]


def counts(log):
    return dict(collections.Counter(x['status'] for x in log))
