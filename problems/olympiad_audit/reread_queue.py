# -*- coding: utf-8 -*-
"""Очередь перечитывания страниц по находкам автопроверок и сверки глазами.

Перенесено из `weconomics-data\\olympiads\\v4_work\\build_queue.py` (13.10.2026)
без изменения правил. Приоритеты:

* 1 — находка сверки глазами с приоритетом 1; класс 1 (смесь алфавитов) не
  в формуле;
* 2 — классы 4, 5, 7, 8; класс 9, кроме «блока коротких строк»; класс 6
  только «нет в слое»;
* 3 — классы 2, 3; формулы класса 1; блок коротких строк класса 9;
  излишек сверх бюджета.

Бюджет приоритетов 1+2 — `cap_usd` / `per_page` страниц (по умолчанию
$5 / $0,006); излишек приоритета 2 уходит в 3. Файл — UTF-8 с BOM, «;»,
колонки `set;page;priority;n_reasons;reasons`, причины через « || ».
"""
from __future__ import annotations

import collections
import csv
import json
import re

COLUMNS = ['set', 'page', 'priority', 'n_reasons', 'reasons']


def read_eye(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return [(x['set'], x['page'], x['reason'], int(x['priority'])) for x in data['pages']]


def _pages_for(ctx, x):
    if x['field'] == 'page':
        return x['pages'].split()
    pgs = sorted(ctx.tp[x['idx']])
    w = re.search(r'[А-Яа-яЁёA-Za-z]{4,}', x['snippet'])
    out = []
    for pg in pgs:
        pj = ctx.pjson(pg)
        txt = ' '.join((b.get('text') or '') for b in (pj or {}).get('blocks', []))
        if w and w.group(0) in txt:
            out.append(pg)
    return out or pgs[:1]


def _priority(x):
    c = x['cls']
    if c.startswith('1_'):
        return 1 if not x['snippet'].startswith('формула') else 3
    if c.startswith(('4_', '5_', '7_', '8_')):
        return 2
    if c.startswith('9_'):
        return 2 if not x['snippet'].lstrip().startswith('[блок') else 3
    if c.startswith('6_'):
        return 2 if 'нет в слое' in x['snippet'] else None
    if c.startswith(('2_', '3_')):
        return 3
    return None


def build(eye, findings, cap_usd=5.0, per_page=0.006):
    """`eye` — [(set, page, причина, приоритет)]; `findings` — {set: (ctx,
    находки автопроверок)} → строки очереди по порядку (приоритет, −число
    причин, (set, page))."""
    eye = [e for e in eye if e[3] != 9]
    q = collections.defaultdict(lambda: {'reasons': [], 'prio': 9})

    def add(s, pg, reason, prio):
        d = q[(s, pg)]
        if reason not in d['reasons']:
            d['reasons'].append(reason)
        d['prio'] = min(d['prio'], prio)

    sets = set(findings)
    for s, pg, r, p in eye:
        if s in sets:
            add(s, pg, 'глаза: ' + r, p)
    for st, (ctx, res) in findings.items():
        for x in res:
            pr = _priority(x)
            if pr is None:
                continue
            for pg in _pages_for(ctx, x):
                add(st, pg, 'авто %s: %s' % (x['cls'][:1], x['snippet'][:90]), pr)
    cap = int(cap_usd / per_page)
    rows = sorted(q.items(), key=lambda kv: (kv[1]['prio'], -len(kv[1]['reasons']), kv[0]))
    n12 = 0
    for _key, v in rows:
        if v['prio'] <= 2:
            n12 += 1
            if n12 > cap:
                v['prio'] = 3
                v['reasons'].append('(за пределом бюджета $5 — вниз)')
    rows = sorted(q.items(), key=lambda kv: (kv[1]['prio'], -len(kv[1]['reasons']), kv[0]))
    return [{'set': s, 'page': pg, 'priority': v['prio'], 'n_reasons': len(v['reasons']),
             'reasons': ' || '.join(v['reasons'][:6]).replace('\x00', '').replace('\r', ' ')}
            for (s, pg), v in rows]


def write(path, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in COLUMNS])


def read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))
