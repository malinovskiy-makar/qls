# -*- coding: utf-8 -*-
"""Фаза 3.3 и 4.2 — стратифицированная выборка пар по бакетам близости.

Только чтение. Пары берутся прямо из numpy, минуя DuplicateCandidate: для
отчёта запись в базу не нужна, а выборка от неё не зависит.

Для каждой пары печатается то, что нужно ГЛАЗАМ человека: источник, статус
ревью, начало условия обеих задач, ответы, вердикт числовой эвристики и
пересечение тем и тегов.
"""
import os
import pathlib
import random
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from problems.models import Problem  # noqa: E402
from scripts.dedup_recon_numbers import compare_numbers, extract_numbers  # noqa: E402

OUT = pathlib.Path('reports/dedup_recon_20260911')
OUT.mkdir(parents=True, exist_ok=True)

BUCKETS = [(0.90, 0.93), (0.93, 0.95), (0.95, 0.97), (0.97, 1.01)]
PER_BUCKET = 20
CHUNK = 2000
SEED = 20260911
EXCERPT = 400


def load():
    ids, vecs = [], []
    for pid, raw in (Problem.objects.filter(embedding__isnull=False)
                     .values_list('id', 'embedding').iterator(chunk_size=1000)):
        raw = bytes(raw)
        if not raw:
            continue
        ids.append(pid)
        vecs.append(np.frombuffer(raw, dtype=np.float32))
    return np.array(ids), np.stack(vecs)


def collect_sample():
    """Резервуарная выборка PER_BUCKET пар на бакет за один проход."""
    rng = random.Random(SEED)
    ids, mat = load()
    n = len(ids)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    mat = (mat / norms).astype(np.float32)

    reservoir = {b: [] for b in BUCKETS}
    seen = {b: 0 for b in BUCKETS}
    t0 = time.time()
    for start in range(0, n, CHUNK):
        end = min(start + CHUNK, n)
        sims = mat[start:end] @ mat.T
        rows = np.arange(start, end)[:, None]
        cols = np.arange(n)[None, :]
        sims = np.where(cols > rows, sims, -2.0)
        for lo, hi in BUCKETS:
            ri, ci = np.nonzero((sims >= lo) & (sims < hi))
            for r, c in zip(ri, ci):
                seen[(lo, hi)] += 1
                item = (int(ids[start + r]), int(ids[c]), float(sims[r, c]))
                res = reservoir[(lo, hi)]
                if len(res) < PER_BUCKET:
                    res.append(item)
                else:
                    j = rng.randrange(seen[(lo, hi)])
                    if j < PER_BUCKET:
                        res[j] = item
        print('  %d/%d (%.0f с)' % (end, n, time.time() - t0), flush=True)
    return reservoir, seen


def excerpt(text):
    text = ' '.join((text or '').split())
    return (text[:EXCERPT] + '…') if len(text) > EXCERPT else (text or '(пусто)')


def overlap(a, b):
    if not a and not b:
        return 'у обеих пусто'
    if not a or not b:
        return 'только у одной'
    if set(a) == set(b):
        return 'совпадают'
    if set(a) & set(b):
        return 'частично'
    return 'не совпадают'


def main():
    reservoir, seen = collect_sample()

    wanted = {pid for pairs in reservoir.values() for pair in pairs for pid in pair[:2]}
    objs = {p.id: p for p in Problem.objects.filter(id__in=wanted)
            .prefetch_related('topics', 'tags', 'source_references__source')}

    def src(p):
        ref = next(iter(p.source_references.all()), None)
        return ref.source.name if ref else '(без источника)'

    lines = []
    stats = {}
    lines.append('# Фаза 3.3 / 4.2 — стратифицированная выборка пар')
    lines.append('')
    lines.append('По %d пары из каждого бакета близости, seed=%d.' % (PER_BUCKET, SEED))
    lines.append('Пары взяты из numpy напрямую, DuplicateCandidate не трогался.')
    lines.append('')

    for lo, hi in BUCKETS:
        key = (lo, hi)
        pairs = sorted(reservoir[key], key=lambda t: -t[2])
        num_verdicts = {}
        topic_verdicts = {}
        lines.append('')
        lines.append('=' * 78)
        lines.append('## Бакет %.2f–%.2f — всего пар в банке: %d, показано %d'
                     % (lo, hi, seen[key], len(pairs)))
        lines.append('=' * 78)
        for a_id, b_id, sim in pairs:
            a, b = objs.get(a_id), objs.get(b_id)
            if a is None or b is None:
                continue
            nv = compare_numbers(a.statement, b.statement)
            tv = overlap([t.name for t in a.topics.all()], [t.name for t in b.topics.all()])
            gv = overlap([t.name for t in a.tags.all()], [t.name for t in b.tags.all()])
            num_verdicts[nv] = num_verdicts.get(nv, 0) + 1
            topic_verdicts[tv] = topic_verdicts.get(tv, 0) + 1
            lines.append('')
            lines.append('-' * 78)
            lines.append('близость %.4f | числа: %s | темы: %s | теги: %s'
                         % (sim, nv, tv, gv))
            for tag, pr in (('A', a), ('B', b)):
                lines.append('')
                lines.append('[%s] id=%d  источник: %s' % (tag, pr.id, src(pr)))
                lines.append('    статус=%s  ревью=%s  content_status=%s  dup_group=%s'
                             % (pr.status, pr.human_review or '-', pr.content_status,
                                pr.dup_group or '-'))
                lines.append('    условие: %s' % excerpt(pr.statement))
                lines.append('    ответ:   %s' % excerpt(pr.answer)[:200])
                lines.append('    числа:   %s'
                             % (', '.join(sorted(extract_numbers(pr.statement))[:25]) or '(нет)'))
        stats[key] = (num_verdicts, topic_verdicts)

    head = ['# Сводка выборки по бакетам', '']
    head.append('%-14s %10s | %s' % ('бакет', 'пар всего', 'вердикт по числам (из 20)'))
    head.append('-' * 78)
    for lo, hi in BUCKETS:
        nv = stats[(lo, hi)][0]
        head.append('%-14s %10d | %s' % (
            '%.2f-%.2f' % (lo, hi), seen[(lo, hi)],
            ', '.join('%s:%d' % kv for kv in sorted(nv.items(), key=lambda kv: -kv[1]))))
    head.append('')
    head.append('%-14s %s' % ('бакет', 'вердикт по темам (из 20)'))
    head.append('-' * 78)
    for lo, hi in BUCKETS:
        tv = stats[(lo, hi)][1]
        head.append('%-14s %s' % (
            '%.2f-%.2f' % (lo, hi),
            ', '.join('%s:%d' % kv for kv in sorted(tv.items(), key=lambda kv: -kv[1]))))
    head.append('')

    path = OUT / 'phase3_sample.md'
    path.write_text('\n'.join(head + lines), encoding='utf-8')
    print('\n'.join(head))
    print('written: %s' % path)


if __name__ == '__main__':
    main()
