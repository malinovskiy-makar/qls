# -*- coding: utf-8 -*-
"""Смета пар по косинусу ДО записи в базу. Только чтение.

Считает, сколько пар даст порог 0,90 и как они лягут по бакетам. Нужна,
чтобы не запустить вслепую `find_duplicates`, который пишет пары по одной
через get_or_create: на SQLite сотни тысяч строк — это часы и распухшая база.
"""
import os
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from problems.models import Problem  # noqa: E402

OUT = pathlib.Path('reports/dedup_recon_20260911')
OUT.mkdir(parents=True, exist_ok=True)

BUCKETS = [(0.90, 0.93), (0.93, 0.95), (0.95, 0.97), (0.97, 1.01)]
CHUNK = 2000


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


def main():
    t0 = time.time()
    ids, mat = load()
    n = len(ids)
    print('векторов: %d, размерность %d (загрузка %.0f с)' % (n, mat.shape[1], time.time() - t0))

    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    mat = (mat / norms).astype(np.float32)

    counts = {b: 0 for b in BUCKETS}
    # Сколько задач имеет хотя бы одного соседа >= 0,90 — это верхняя оценка
    # размера «зоны схлопывания».
    has_neighbor = np.zeros(n, dtype=bool)
    t1 = time.time()
    for start in range(0, n, CHUNK):
        end = min(start + CHUNK, n)
        sims = mat[start:end] @ mat.T                      # (m, n)
        # Убираем диагональ и нижний треугольник: считаем каждую пару один раз.
        rows = np.arange(start, end)[:, None]
        cols = np.arange(n)[None, :]
        upper = cols > rows
        sims_u = np.where(upper, sims, -2.0)
        for lo, hi in BUCKETS:
            counts[(lo, hi)] += int(np.count_nonzero((sims_u >= lo) & (sims_u < hi)))
        # соседи в обе стороны (для охвата)
        near = (sims >= 0.90) & (cols != rows)
        has_neighbor[start:end] |= near.any(axis=1)
        has_neighbor |= near.any(axis=0)
        print('  %d/%d (%.0f с)' % (end, n, time.time() - t1), flush=True)

    total = sum(counts.values())
    lines = ['# Смета пар по косинусу на векторах v2_focus_repeat v95', '',
             'Считано numpy без единой записи в базу.', '',
             'векторов: %d' % n, '']
    lines.append('%-14s %12s' % ('бакет', 'пар'))
    for (lo, hi), c in counts.items():
        lines.append('%-14s %12d' % ('%.2f-%.2f' % (lo, hi), c))
    lines.append('%-14s %12d' % ('ИТОГО >=0.90', total))
    lines.append('')
    lines.append('задач хотя бы с одним соседом >=0.90: %d (%.1f %% банка)'
                 % (int(has_neighbor.sum()), 100.0 * has_neighbor.sum() / n))
    text = '\n'.join(lines)
    (OUT / 'phase3_estimate.md').write_text(text, encoding='utf-8')
    print()
    print(text)


if __name__ == '__main__':
    main()
