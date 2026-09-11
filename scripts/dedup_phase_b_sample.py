# -*- coding: utf-8 -*-
"""ФАЗА B.3 — выборка пар глазами и точечная сверка конкретных пар.

Печатает пары с косинусом по НЕСКОЛЬКИМ формулам сразу: так видно, двигает
ли смена формулы конкретный случай, а не только сводные доли.

Только чтение.
"""
import argparse
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import fetch_attrs, connect, full_text  # noqa: E402
from dedup_phase_b_textsim import trigrams, jaccard, normalize  # noqa: E402
from dedup_recon_numbers import extract_numbers, compare_numbers  # noqa: E402

VEC_DIR = os.path.join('reports', 'formula_v2')


def load_vectors(spec):
    meta = json.load(open(os.path.join(
        VEC_DIR, 'vec_%s.meta.json' % spec), encoding='utf-8'))
    ids = np.asarray(meta['ids'], dtype=np.int64)
    mat = np.fromfile(os.path.join(VEC_DIR, 'vec_%s.f32' % spec),
                      dtype=np.float32).reshape(len(ids), int(meta['dim']))
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    return {int(i): v for i, v in zip(ids, mat / norms)}


def cos(vecs, a, b):
    if a not in vecs or b not in vecs:
        return None
    return round(float(np.dot(vecs[a], vecs[b])), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--enriched', default=None)
    ap.add_argument('--pairs', default=None,
                    help='явные пары через запятую: 51615-51609,35661-34026')
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--seed', type=int, default=20260911)
    ap.add_argument('--min-sim', type=float, default=0.97)
    ap.add_argument('--max-sim', type=float, default=1.01)
    ap.add_argument('--only-header-clash', action='store_true')
    ap.add_argument('--specs', default='v1,v2_focus_repeat')
    ap.add_argument('--chars', type=int, default=700)
    args = ap.parse_args()

    specs = args.specs.split(',')
    vecs = {s: load_vectors(s) for s in specs}

    if args.pairs:
        пары = [tuple(int(x) for x in p.split('-'))
                for p in args.pairs.split(',')]
    else:
        z = np.load(args.enriched)
        m = (z['sim'] >= args.min_sim) & (z['sim'] < args.max_sim)
        ia, ib = z['id_a'][m], z['id_b'][m]
        индексы = list(range(len(ia)))
        random.Random(args.seed).shuffle(индексы)
        пары = [(int(ia[i]), int(ib[i])) for i in индексы[:args.n * 4]]

    con = connect()
    ids = sorted({x for p in пары for x in p})
    attrs = fetch_attrs(con, ids)
    con.close()
    тексты = {i: full_text(attrs[i]) for i in ids}

    показано = 0
    for a, b in пары:
        ta, tb = тексты[a], тексты[b]
        шапка = (normalize(ta)[:500] == normalize(tb)[:500]
                 and normalize(ta) != normalize(tb))
        if args.only_header_clash and not шапка:
            continue
        показано += 1
        print('=' * 78)
        print('ПАРА %d — %d' % (a, b))
        for s in specs:
            print('  косинус %-18s %s' % (s, cos(vecs[s], a, b)))
        print('  Жаккар полного текста: %.4f' % jaccard(trigrams(ta),
                                                        trigrams(tb)))
        print('  числа: %s' % compare_numbers(ta, tb))
        print('  общая шапка 500 символов: %s' % ('ДА' if шапка else 'нет'))
        for имя, pid in (('A', a), ('B', b)):
            at = attrs[pid]
            print('  --- %s id=%d review=%r статус=%r источник=%r '
                  'подпунктов=%d картинок=%d ответ=%s решение=%s длина=%d'
                  % (имя, pid, at['human_review'], at['status'],
                     at['source'], at['parts'], at['images'],
                     'да' if at['answer'] else 'нет',
                     'да' if at['solution'] else 'нет', len(тексты[pid])))
            print('      %s' % тексты[pid][:args.chars].replace('\n', ' '))
        if показано >= args.n:
            break
    print('\nпоказано пар: %d' % показано)


if __name__ == '__main__':
    main()
