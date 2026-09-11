# -*- coding: utf-8 -*-
"""Фаза 4 — риски по ВСЕМУ корпусу, а не по выборке. Только чтение.

Три вопроса, на которые нужен ответ числом до выбора порога:
  1. Сколько пар высокой близости пересекают границу эталона (одна сторона
     approved, другая нет) — то есть где автоправило «оставить A» может
     убить именно отсмотренную версию.
  2. Сколько пар, где approved-версия БЕДНЕЕ своего двойника (нет ответа
     или нет решения, а у двойника есть) — тут «эталон всегда лучший»
     неверно как правило.
  3. Что за группы точного совпадения content_hash и нет ли среди них
     мусорных.
"""
import os
import pathlib
import sys
import time
from collections import Counter

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from django.db.models import Count  # noqa: E402
from problems.models import Problem  # noqa: E402
from scripts.dedup_recon_numbers import compare_numbers  # noqa: E402

OUT = pathlib.Path('reports/dedup_recon_20260911')
LEVELS = [0.95, 0.97, 0.99]
CHUNK = 2000
lines = []


def p(s=''):
    lines.append(str(s))


def main():
    meta = {}
    for r in Problem.objects.values('id', 'human_review', 'status', 'answer',
                                    'solution', 'statement', 'content_status',
                                    'dup_group').iterator(chunk_size=5000):
        meta[r['id']] = r
    first_src = {}
    for pid, sname in (Problem.objects.filter(source_references__isnull=False)
                       .values_list('id', 'source_references__source__name')
                       .order_by('id', 'source_references__id')):
        first_src.setdefault(pid, sname)

    ids, vecs = [], []
    for pid, raw in (Problem.objects.filter(embedding__isnull=False)
                     .values_list('id', 'embedding').iterator(chunk_size=1000)):
        raw = bytes(raw)
        if raw:
            ids.append(pid)
            vecs.append(np.frombuffer(raw, dtype=np.float32))
    ids = np.array(ids)
    mat = np.stack(vecs)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    mat = (mat / norms).astype(np.float32)
    n = len(ids)

    counters = {lv: Counter() for lv in LEVELS}
    losers = {lv: [] for lv in LEVELS}   # approved беднее двойника
    t0 = time.time()
    for start in range(0, n, CHUNK):
        end = min(start + CHUNK, n)
        sims = mat[start:end] @ mat.T
        rows = np.arange(start, end)[:, None]
        cols = np.arange(n)[None, :]
        sims = np.where(cols > rows, sims, -2.0)
        for lv in LEVELS:
            ri, ci = np.nonzero(sims >= lv)
            c = counters[lv]
            for r, ccol in zip(ri, ci):
                a = meta[int(ids[start + r])]
                b = meta[int(ids[ccol])]
                c['пар всего'] += 1
                ra, rb = a['human_review'], b['human_review']
                if ra == 'approved' and rb == 'approved':
                    c['обе approved'] += 1
                elif 'approved' in (ra, rb):
                    c['ровно одна approved'] += 1
                    ap, other = (a, b) if ra == 'approved' else (b, a)
                    poorer = []
                    if not (ap['answer'] or '').strip() and (other['answer'] or '').strip():
                        poorer.append('нет ответа')
                    if not (ap['solution'] or '').strip() and (other['solution'] or '').strip():
                        poorer.append('нет решения')
                    if poorer:
                        c['approved БЕДНЕЕ двойника'] += 1
                        if len(losers[lv]) < 40:
                            losers[lv].append((ap['id'], other['id'],
                                               float(sims[r, ccol]), '+'.join(poorer)))
                else:
                    c['ни одной approved'] += 1
                sa = first_src.get(int(ids[start + r]), '(нет)')
                sb = first_src.get(int(ids[ccol]), '(нет)')
                c['разные источники' if sa != sb else 'один источник'] += 1
                c['числа: ' + compare_numbers(a['statement'], b['statement'])] += 1
                if a['dup_group'] and a['dup_group'] == b['dup_group']:
                    c['уже в одной dup_group'] += 1
                if a['status'] in ('duplicate', 'hidden') and b['status'] in ('duplicate', 'hidden'):
                    c['ОБЕ уже скрыты/дубль'] += 1
        print('  %d/%d (%.0f с)' % (end, n, time.time() - t0), flush=True)

    p('# Фаза 4 — риски по всему корпусу на векторах v95')
    p()
    for lv in LEVELS:
        c = counters[lv]
        total = c['пар всего']
        p('## Порог >= %.2f — пар: %d' % (lv, total))
        p()
        for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
            if k == 'пар всего':
                continue
            p('  %-32s %8d  %5.1f %%' % (k, v, 100.0 * v / total if total else 0))
        p()

    p('## Пары, где approved-версия БЕДНЕЕ своего двойника (примеры)')
    p()
    p('Это прямой контрпример правилу «approved всегда лучший». Перечислены')
    p('первые найденные; полное число — в счётчиках выше.')
    p()
    for lv in LEVELS:
        if not losers[lv]:
            continue
        p('порог >= %.2f:' % lv)
        p('  %-10s %-10s %-9s %s' % ('approved', 'двойник', 'близость', 'чего не хватает эталону'))
        for ap_id, other_id, sim, why in losers[lv][:25]:
            p('  %-10d %-10d %-9.4f %s' % (ap_id, other_id, sim, why))
        p()

    p('## Фаза 4.1 — группы точного совпадения content_hash')
    p()
    dups = (Problem.objects.exclude(content_hash='')
            .values('content_hash').annotate(n=Count('id')).filter(n__gt=1)
            .order_by('-n'))
    p('%-10s %-40s %s' % ('размер', 'первые id', 'начало условия'))
    for r in list(dups)[:12]:
        members = list(Problem.objects.filter(content_hash=r['content_hash'])
                       .values_list('id', 'statement')[:40])
        head = ' '.join((members[0][1] or '').split())[:90]
        p('%-10d %-40s %s' % (r['n'], ', '.join(str(m[0]) for m in members[:5]), head))

    path = OUT / 'phase4_risks.md'
    path.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[:80]))
    print('written: %s' % path)


if __name__ == '__main__':
    main()
