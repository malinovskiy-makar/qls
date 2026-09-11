# -*- coding: utf-8 -*-
"""ФАЗА B.3 — решающая проверка: что формулы дают на ОДИНАКОВЫХ текстах.

Если два условия совпали символ в символ после нормализации, честный
отпечаток обязан дать косинус 1,0. Всё, что ниже, — шум, который формула
принесла извне текста задачи (рубрикация и поля, дописанные моделью
каждой копии по отдельности).

Метрика ни от одной формулы не зависит: пары отбираются по тексту.
Только чтение.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import fetch_attrs, connect, full_text  # noqa: E402
from dedup_phase_b_textsim import normalize  # noqa: E402
from dedup_phase_b_compare import load_vectors  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--specs', default='v1,v2_lean,v2_nolimit,v2_focus_repeat')
    ap.add_argument('--pool', nargs='+', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    пул = set()
    for path in args.pool:
        z = np.load(path)
        пул.update(zip((int(x) for x in z['id_a']), (int(x) for x in z['id_b'])))
    пары = sorted(пул)

    con = connect()
    ids = sorted({x for p in пары for x in p})
    attrs = fetch_attrs(con, ids)
    con.close()
    норм = {i: normalize(full_text(attrs[i])) for i in ids}

    одинаковые = [(a, b) for a, b in пары
                  if норм[a] and норм[a] == норм[b]]
    print('пар с ПОБУКВЕННО одинаковым условием: %d из %d'
          % (len(одинаковые), len(пары)), flush=True)

    ia = np.array([p[0] for p in одинаковые])
    ib = np.array([p[1] for p in одинаковые])
    отчёт = {'пар одинаковых': len(одинаковые), 'пул': len(пары),
             'формулы': {}}
    for spec in args.specs.split(','):
        строка, mat = load_vectors(spec)
        cos = np.einsum('ij,ij->i',
                        mat[[строка[int(x)] for x in ia]],
                        mat[[строка[int(x)] for x in ib]])
        отчёт['формулы'][spec] = {
            'медиана': round(float(np.median(cos)), 4),
            'среднее': round(float(cos.mean()), 4),
            '5-й процентиль': round(float(np.percentile(cos, 5)), 4),
            'минимум': round(float(cos.min()), 4),
            'доля >= 0,98': round(float((cos >= 0.98).mean()), 4),
            'доля >= 0,97': round(float((cos >= 0.97).mean()), 4),
            'доля >= 0,95': round(float((cos >= 0.95).mean()), 4),
            'доля < 0,95 (потеряны)': int((cos < 0.95).sum()),
        }
        print('%-18s медиана %.4f  5-й проц. %.4f  мин %.4f  '
              '>=0,97 %5.1f%%  ниже 0,95: %d'
              % (spec, np.median(cos), np.percentile(cos, 5), cos.min(),
                 100 * (cos >= 0.97).mean(), int((cos < 0.95).sum())),
              flush=True)
    json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('записано: %s' % args.out)


if __name__ == '__main__':
    main()
