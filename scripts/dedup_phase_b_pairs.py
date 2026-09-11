# -*- coding: utf-8 -*-
"""ФАЗА B.1 — косинус и бакеты на векторах ВЫБРАННОГО варианта формулы.

Читает векторы из `reports/formula_v2/vec_<spec>.f32` и соответствие
«строка → id задачи» из одноимённого `.meta.json`. Базу не открывает вовсе.

Складывает пары выше порога в `.npz`, чтобы фаза B.2 (числовой гейт) и
фазы C-E работали по уже посчитанному, не гоняя матрицу заново.
"""
import argparse
import json
import os
import time

import numpy as np

VEC_DIR = os.path.join('reports', 'formula_v2')
BUCKETS = ((0.90, 0.93), (0.93, 0.95), (0.95, 0.97), (0.97, 1.01))
CHUNK = 2048


def load(spec):
    meta_path = os.path.join(VEC_DIR, 'vec_%s.meta.json' % spec)
    meta = json.load(open(meta_path, encoding='utf-8'))
    ids = np.asarray(meta['ids'], dtype=np.int64)
    raw = np.fromfile(os.path.join(VEC_DIR, 'vec_%s.f32' % spec),
                      dtype=np.float32)
    dim = int(meta['dim'])
    mat = raw.reshape(-1, dim)
    assert mat.shape[0] == len(ids), (
        'строк в .f32 %d, а id в мета %d' % (mat.shape[0], len(ids)))
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    return meta, ids, (mat / norms).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', required=True)
    ap.add_argument('--keep-from', type=float, default=0.95,
                    help='пары с косинусом не ниже этого сохраняются в .npz')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    t0 = time.time()
    meta, ids, mat = load(args.spec)
    n = len(ids)
    print('%s v%s: %d векторов, dim %d (%.0f с)'
          % (args.spec, meta.get('version'), n, mat.shape[1], time.time() - t0),
          flush=True)

    counts = {b: 0 for b in BUCKETS}
    has_neighbor = np.zeros(n, dtype=bool)
    kept_i, kept_j, kept_s = [], [], []

    t1 = time.time()
    for start in range(0, n, CHUNK):
        end = min(start + CHUNK, n)
        sims = mat[start:end] @ mat.T
        rows = np.arange(start, end)[:, None]
        cols = np.arange(n)[None, :]
        # Верхний треугольник: каждая пара ровно один раз, диагональ вон.
        sims_u = np.where(cols > rows, sims, -2.0)
        for lo, hi in BUCKETS:
            counts[(lo, hi)] += int(np.count_nonzero(
                (sims_u >= lo) & (sims_u < hi)))
        near = (sims >= 0.90) & (cols != rows)
        has_neighbor[start:end] |= near.any(axis=1)
        has_neighbor |= near.any(axis=0)
        ii, jj = np.nonzero(sims_u >= args.keep_from)
        if len(ii):
            kept_i.append((ii + start).astype(np.int32))
            kept_j.append(jj.astype(np.int32))
            kept_s.append(sims_u[ii, jj].astype(np.float32))
        if (start // CHUNK) % 5 == 0:
            print('  %d/%d (%.0f с)' % (end, n, time.time() - t1), flush=True)

    rows_i = np.concatenate(kept_i) if kept_i else np.zeros(0, np.int32)
    rows_j = np.concatenate(kept_j) if kept_j else np.zeros(0, np.int32)
    sims_k = np.concatenate(kept_s) if kept_s else np.zeros(0, np.float32)
    np.savez_compressed(args.out, id_a=ids[rows_i], id_b=ids[rows_j],
                        sim=sims_k, spec=np.array([args.spec]),
                        keep_from=np.array([args.keep_from]))

    сводка = {
        'spec': args.spec, 'version': meta.get('version'), 'n': int(n),
        'buckets': {'%.2f-%.2f' % b: c for b, c in counts.items()},
        'total_ge_090': int(sum(counts.values())),
        'problems_with_neighbor_090': int(has_neighbor.sum()),
        'share_with_neighbor_090': round(float(has_neighbor.sum()) / n, 4),
        'pairs_kept': int(len(sims_k)), 'keep_from': args.keep_from,
        'seconds': round(time.time() - t0, 1),
    }
    print(json.dumps(сводка, ensure_ascii=False, indent=1))
    json.dump(сводка, open(args.out + '.summary.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
