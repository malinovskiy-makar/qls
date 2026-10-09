# -*- coding: utf-8 -*-
"""Пакет «просмотр глазами»: остаток очереди «на глаза» после судьи и
перечитывания (`human`, а также `judge_error` и не дошедшие до
перечитывания `needs_fix`).

`human_review\\index.html` — таблица (страница, комплект, номер задания, что
смущает судью) и ниже по странице: PNG слева, расшифровка справа. Страниц
больше `SPLIT_OVER` — два пакета: `urgent\\` (попадёт в импорт) и `other\\`;
`human_review\\index.html` тогда только ссылки. Рядом — `human_review.csv`.

Файл самодостаточный: без внешних библиотек и адресов, открывается двойным
щелчком. Пишет только в папку пакета.
"""
from __future__ import annotations

import csv
import html
import os
import random
import shutil

from problems.olympiad_audit import triage
from problems.olympiad_audit.judge import judge_transcript

SPLIT_OVER = 150
HUMAN_STATUSES = ('human', 'judge_error', 'needs_fix')
STATUS_LABELS = {'human': 'перечитана, судья всё ещё видит расхождения',
                 'judge_error': 'судья не ответил валидным JSON',
                 'needs_fix': 'не перечитана'}
CSV_COLUMNS = ['пакет', 'страница', 'файл', 'комплекты', 'задания', 'срочность',
               'ярус', 'статус', 'замечания судьи', 'числа не найдены',
               'расшифровка', 'png']

CSS = """body{font:15px/1.45 system-ui,sans-serif;margin:16px;color:#1a1a1a}
table{border-collapse:collapse;width:100%;margin-bottom:28px}
th,td{border:1px solid #ccc;padding:4px 8px;vertical-align:top;text-align:left}
th{background:#f0f0f0;position:sticky;top:0}
section{border-top:3px solid #444;margin-top:28px;padding-top:8px}
.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
.grid img{max-width:100%;border:1px solid #ccc}
pre{white-space:pre-wrap;word-wrap:break-word;background:#fafafa;border:1px solid #ddd;padding:8px}
.issue{color:#8a1c1c}.meta{color:#555}
@media(max-width:900px){.grid{grid-template-columns:1fr}}"""


def urgency_rank(label):
    return {triage.URGENT_NEW: 0, triage.URGENT_UPDATE: 1}.get(label, 2)


def judge_summary(patch):
    """Что смущает судью, коротко: последнее заключение (после перечитывания,
    если оно было и расшифровка из него выбрана), иначе первое."""
    verdict = (patch.get('judge') if patch.get('chosen') == 'v3' else None) \
        or patch.get('judge_before') or patch.get('judge') or {}
    parts = [f'{i.get("kind", "")}: {i.get("detail", "")}' for i in verdict.get('issues') or []]
    if verdict.get('real_missing'):
        parts.append('числа не найдены в расшифровке: ' + ', '.join(verdict['real_missing']))
    return parts


def build_items(plan_rows, patches, v2_records):
    """Остаток для просмотра: список словарей по страницам, срочные первыми."""
    plan = {r['страница']: r for r in plan_rows}
    items = []
    for key, patch in patches.items():
        if patch.get('status') not in HUMAN_STATUSES:
            continue
        row = plan.get(key, {})
        record = v2_records.get(key) or {}
        items.append({
            'key': key, 'patch': patch, 'record': record,
            'file': row.get('файл') or record.get('file', ''),
            'events': row.get('комплекты', ''), 'tasks': row.get('задания', ''),
            'urgency': row.get('срочность', triage.NOT_URGENT),
            'tier': row.get('ярус', patch.get('tier', '')),
            'status': patch['status'], 'remarks': judge_summary(patch),
            'missing': (patch.get('judge') or patch.get('judge_before') or {}
                        ).get('real_missing') or [],
        })
    items.sort(key=lambda it: (urgency_rank(it['urgency']), it['key']))
    return items


def split_items(items, limit=SPLIT_OVER):
    """Один пакет или два: `urgent` (срочные) и `other`, если страниц больше
    `limit`."""
    if len(items) <= limit:
        return {'': items}
    return {'urgent': [i for i in items if urgency_rank(i['urgency']) < 2],
            'other': [i for i in items if urgency_rank(i['urgency']) == 2]}


def _blocks_of(item):
    """(выбранная расшифровка, вторая версия или None, подписи)."""
    old = item['record'].get('blocks') or []
    new = ((item['patch'].get('reread') or {}).get('blocks')) or None
    if item['patch'].get('chosen') == 'v3' and new is not None:
        return new, old, ('перечитанная (показана)', 'прежняя')
    return old, new, ('прежняя (показана)', 'перечитанная')


def _image_name(key):
    page_dir, _, page = key.rpartition('/p')
    return f'{page_dir.rsplit("/", 1)[-1]}_p{page}.png'


def render_html(title, items, note=''):
    e = html.escape
    out = [f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
           f'<title>{e(title)}</title><style>{CSS}</style></head><body>',
           f'<h1>{e(title)}</h1><p class="meta">Страниц: {len(items)}. {e(note)}</p>',
           '<table><tr><th>#</th><th>страница</th><th>комплект</th><th>номер задания</th>'
           '<th>срочность</th><th>что смущает судью</th></tr>']
    for n, item in enumerate(items, 1):
        tasks = [t.rpartition('#') for t in item['tasks'].split()]
        events = ', '.join(sorted({t[0] for t in tasks})) or item['events'] or '—'
        numbers = ', '.join(t[2] for t in tasks) or '—'
        short = '; '.join(item['remarks'])[:300] or STATUS_LABELS.get(item['status'], '')
        out.append(f'<tr><td>{n}</td><td><a href="#p{n}">{e(item["key"])}</a></td>'
                   f'<td>{e(events)}</td><td>{e(numbers)}</td><td>{e(item["urgency"])}</td>'
                   f'<td>{e(short)}</td></tr>')
    out.append('</table>')
    for n, item in enumerate(items, 1):
        shown, other, labels = _blocks_of(item)
        out.append(f'<section id="p{n}"><h2>{n}. {e(item["key"])}</h2>'
                   f'<p class="meta">{e(item["file"])} · ярус {e(item["tier"])} · '
                   f'{e(item["urgency"])} · {e(STATUS_LABELS.get(item["status"], ""))}</p>')
        if item['remarks']:
            out.append('<ul>' + ''.join(f'<li class="issue">{e(r)}</li>' for r in item['remarks'])
                       + '</ul>')
        out.append(f'<div class="grid"><div><img src="img/{e(_image_name(item["key"]))}" '
                   f'alt="{e(item["key"])}"></div><div><b>{e(labels[0])}</b>'
                   f'<pre>{e(judge_transcript(shown))}</pre>')
        if other:
            out.append(f'<details><summary>{e(labels[1])} расшифровка</summary>'
                       f'<pre>{e(judge_transcript(other))}</pre></details>')
        out.append('</div></div></section>')
    out.append('</body></html>')
    return '\n'.join(out)


def csv_row(pack, item):
    return {'пакет': pack or 'общий', 'страница': item['key'], 'файл': item['file'],
            'комплекты': item['events'], 'задания': item['tasks'],
            'срочность': item['urgency'], 'ярус': item['tier'], 'статус': item['status'],
            'замечания судьи': ' | '.join(item['remarks']),
            'числа не найдены': ' '.join(item['missing']),
            'расшифровка': 'перечитанная' if item['patch'].get('chosen') == 'v3'
            else 'прежняя', 'png': _image_name(item['key'])}


def build_pack(digitized, items, out_root=None):
    """Пакет(ы) на диск. Возвращает {пакет: число страниц} и пути."""
    out_root = out_root or os.path.join(digitized, 'human_review')
    packs = split_items(items)
    os.makedirs(out_root, exist_ok=True)
    rows, written = [], {}
    for pack, pack_items in packs.items():
        folder = os.path.join(out_root, pack) if pack else out_root
        os.makedirs(os.path.join(folder, 'img'), exist_ok=True)
        for item in pack_items:
            page_dir, _, page = item['key'].rpartition('/p')
            source = os.path.join(digitized, page_dir, f'p{page}.png')
            if os.path.isfile(source):
                shutil.copy2(source, os.path.join(folder, 'img', _image_name(item['key'])))
            rows.append(csv_row(pack, item))
        title = 'Просмотр глазами: ' + {'urgent': 'срочные (попадут в импорт)',
                                         'other': 'остальные', '': 'остаток очереди'}[pack]
        with open(os.path.join(folder, 'index.html'), 'w', encoding='utf-8') as handle:
            handle.write(render_html(title, pack_items))
        written[pack or 'общий'] = len(pack_items)
    if len(packs) > 1:
        links = ''.join(f'<li><a href="{p}/index.html">{html.escape(p)}</a> — {n} страниц</li>'
                        for p, n in written.items())
        with open(os.path.join(out_root, 'index.html'), 'w', encoding='utf-8') as handle:
            handle.write('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                         f'<title>Просмотр глазами</title></head><body><h1>Просмотр глазами'
                         f'</h1><ul>{links}</ul></body></html>')
    csv_path = os.path.join(digitized, 'human_review.csv')
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return {'packs': written, 'csv': csv_path, 'index': os.path.join(out_root, 'index.html')}


# ── Контроль судьи ───────────────────────────────────────────────────────

#: Seed выборки контроля судьи (записан в отчёт); 30 страниц яруса A,
#: которые судья пропустил (`ok_judge`). Человек не видит пометки судьи и
#: считает, сколько ошибок расшифровки судья пропустил.
CONTROL_PACK_SEED = 20261009
CONTROL_PACK_SIZE = 30
CONTROL_MARK_COLUMNS = ['страница', 'олимпиада', 'ошибок найдено', 'какие']


def control_candidates(plan_rows, patches):
    """Ключи страниц яруса A со статусом `ok_judge` (решение судьи фазы 2)."""
    plan = {r['страница']: r for r in plan_rows}
    return sorted(key for key, patch in patches.items()
                  if patch.get('status') == 'ok_judge' and patch.get('phase') == 'judge'
                  and plan.get(key, {}).get('ярус') == triage.TIER_A)


def pick_control(candidates, seed=CONTROL_PACK_SEED, size=CONTROL_PACK_SIZE):
    """Воспроизводимая выборка: кандидаты — пары (олимпиада, ключ страницы)."""
    candidates = sorted(candidates)
    return sorted(random.Random(f'control-{seed}').sample(candidates,
                                                          min(size, len(candidates))))


def render_control_html(items):
    """Раздел «контроль»: то же, что пакет, но без статуса, срочности, яруса и
    замечаний судьи."""
    e = html.escape
    out = ['<!doctype html><html lang="ru"><head><meta charset="utf-8">'
           f'<title>Контроль</title><style>{CSS}</style></head><body><h1>Контроль</h1>',
           f'<p class="meta">Страниц: {len(items)}. Для каждой посчитайте ошибки расшифровки '
           '(пропуск, лишнее, искажение чисел/формул/слов) и впишите в '
           '<b>control_marks.csv</b>.</p>',
           '<table><tr><th>#</th><th>страница</th><th>олимпиада</th><th>комплект</th>'
           '<th>номер задания</th></tr>']
    for n, item in enumerate(items, 1):
        tasks = [t.rpartition('#') for t in item['tasks'].split()]
        events = ', '.join(sorted({t[0] for t in tasks})) or item['events'] or '—'
        out.append(f'<tr><td>{n}</td><td><a href="#p{n}">{e(item["key"])}</a></td>'
                   f'<td>{e(item["olympiad"])}</td><td>{e(events)}</td>'
                   f'<td>{e(", ".join(t[2] for t in tasks) or "—")}</td></tr>')
    out.append('</table>')
    for n, item in enumerate(items, 1):
        out.append(f'<section id="p{n}"><h2>{n}. {e(item["olympiad"])} · {e(item["key"])}</h2>'
                   f'<div class="grid"><div><img src="img/{e(item["image"])}" alt=""></div>'
                   f'<div><pre>{e(judge_transcript(item["blocks"]))}</pre></div></div></section>')
    out.append('</body></html>')
    return '\n'.join(out)


def build_control_pack(entries, out_root):
    """entries: словари {olympiad, digitized, key, blocks, tasks, events}.
    Пишет `out_root\index.html`, `img\`, `control_marks.csv` (пустой бланк) и
    `control_pages.csv` (какие страницы вошли — для сверки с судьёй)."""
    os.makedirs(os.path.join(out_root, 'img'), exist_ok=True)
    items = []
    for entry in entries:
        page_dir, _, page = entry['key'].rpartition('/p')
        image = f'{entry["olympiad"]}_{_image_name(entry["key"])}'
        source = os.path.join(entry['digitized'], page_dir, f'p{page}.png')
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(out_root, 'img', image))
        items.append({**entry, 'image': image})
    with open(os.path.join(out_root, 'index.html'), 'w', encoding='utf-8') as handle:
        handle.write(render_control_html(items))
    for name, rows in (('control_marks.csv', [{'страница': i['key'], 'олимпиада': i['olympiad']}
                                              for i in items]),
                       ('control_pages.csv', [{'страница': i['key'], 'олимпиада': i['olympiad'],
                                               'seed': CONTROL_PACK_SEED} for i in items])):
        with open(os.path.join(out_root, name), 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CONTROL_MARK_COLUMNS if
                                                            name == 'control_marks.csv'
                                                            else rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return {'pages': len(items), 'index': os.path.join(out_root, 'index.html')}
