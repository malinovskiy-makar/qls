# -*- coding: utf-8 -*-
"""ФАЗА B.3 — честное сравнение формул на ОБЩЕМ пуле пар.

Каждая формула сама выбирает свои пары, и сравнивать их «свои против своих»
нечестно: у кого пул меньше, у того и доля мусора меньше. Здесь пул один —
объединение пар всех сравниваемых формул, — и на нём для каждой формулы
считается, насколько её косинус предсказывает РЕАЛЬНОЕ дублирование текста
(символьная близость полных условий вместе с подпунктами).

«Настоящий дубль» определяется НЕ моделью и не косинусом, а порогом по
символьной близости — метрикой, ничего не знающей ни об одной формуле.

Только чтение.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import fetch_attrs, connect, full_text  # noqa: E402
from dedup_phase_b_textsim import trigrams, jaccard  # noqa: E402

VEC_DIR = os.path.join('reports', 'formula_v2')


def load_vectors(spec):
    meta = json.load(open(os.path.join(
        VEC_DIR, 'vec_%s.meta.json' % spec), encoding='utf-8'))
    ids = np.asarray(meta['ids'], dtype=np.int64)
    mat = np.fromfile(os.path.join(VEC_DIR, 'vec_%s.f32' % spec),
                      dtype=np.float32).reshape(len(ids), int(meta['dim']))
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    строка = {int(i): k for k, i in enumerate(ids)}
    return строка, (mat / norms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--specs', default='v1,v2_lean,v2_nolimit,v2_focus_repeat')
    ap.add_argument('--pool', nargs='+', required=True,
                    help='.npz файлы пар, их объединение и есть общий пул')
    ap.add_argument('--dup-jaccard', type=float, default=0.80)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    specs = args.specs.split(',')

    пул = set()
    for path in args.pool:
        z = np.load(path)
        пул.update(zip((int(x) for x in z['id_a']), (int(x) for x in z['id_b'])))
    пары = sorted(пул)
    ia = np.array([p[0] for p in пары], dtype=np.int64)
    ib = np.array([p[1] for p in пары], dtype=np.int64)
    print('общий пул пар: %d' % len(пары), flush=True)

    con = connect()
    ids = np.union1d(ia, ib)
    attrs = fetch_attrs(con, ids)
    con.close()
    граммы = {int(i): trigrams(full_text(attrs[int(i)])) for i in ids}
    jac = np.array([jaccard(граммы[int(a)], граммы[int(b)])
                    for a, b in zip(ia, ib)])
    дубль = jac >= args.dup_jaccard
    print('«настоящих дублей» в пуле (Жаккар >= %.2f): %d (%.1f %%)'
          % (args.dup_jaccard, int(дубль.sum()),
             100.0 * дубль.mean()), flush=True)

    отчёт = {'пул': len(пары), 'порог дубля': args.dup_jaccard,
             'дублей в пуле': int(дубль.sum()), 'формулы': {}}

    for spec in specs:
        строка, mat = load_vectors(spec)
        ra = np.array([строка[int(x)] for x in ia])
        rb = np.array([строка[int(x)] for x in ib])
        cos = np.einsum('ij,ij->i', mat[ra], mat[rb])

        # Спирмен: ранговая связь косинуса с реальной близостью текста.
        r_cos = np.argsort(np.argsort(cos))
        r_jac = np.argsort(np.argsort(jac))
        spearman = float(np.corrcoef(r_cos, r_jac)[0, 1])

        # Точность при СОВПАДАЮЩЕЙ полноте: берём у каждой формулы столько
        # верхних пар, сколько в пуле настоящих дублей, — тогда сравнение
        # не зависит от того, какой у формулы масштаб косинуса.
        k = int(дубль.sum())
        верх = np.argsort(-cos)[:k]
        precision_at_k = float(дубль[верх].mean())

        по_порогам = {}
        for t in (0.95, 0.97, 0.98, 0.99):
            m = cos >= t
            n = int(m.sum())
            по_порогам['%.2f' % t] = {
                'пар': n,
                'точность': round(float(дубль[m].mean()), 4) if n else None,
                'полнота': round(float((m & дубль).sum() / max(int(дубль.sum()), 1)), 4),
            }
        отчёт['формулы'][spec] = {
            'спирмен косинус~текст': round(spearman, 4),
            'точность на топ-%d' % k: round(precision_at_k, 4),
            'по порогам': по_порогам,
        }
        print('%-18s спирмен %.4f  точность@%d %.4f  '
              '0,97: пар %5d точн %.3f полн %.3f'
              % (spec, spearman, k, precision_at_k,
                 по_порогам['0.97']['пар'], по_порогам['0.97']['точность'],
                 по_порогам['0.97']['полнота']), flush=True)

    json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('записано: %s' % args.out)


if __name__ == '__main__':
    main()
