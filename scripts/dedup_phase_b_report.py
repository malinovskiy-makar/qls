# -*- coding: utf-8 -*-
"""ФАЗА B.3-B.4 — сводка по обогащённым парам: пороги против вердиктов чисел.

Только чтение `.npz`. Печатает таблицу, по которой выбирается порог.
"""
import argparse
import json
import sys

import numpy as np

VERDICTS = ('совпадают', 'частично', 'не совпадают', 'числа только у одной',
            'оба без чисел')
THRESHOLDS = (0.95, 0.96, 0.97, 0.975, 0.98, 0.99)


def block(z, lo):
    m = z['sim'] >= lo
    n = int(m.sum())
    if not n:
        return None
    v = z['verdict'][m]
    appr = z['approved_a'][m].astype(int) + z['approved_b'][m].astype(int)
    имг_a, имг_b = z['images_a'][m], z['images_b'][m]
    строка = {'порог': lo, 'пар': n}
    for имя in VERDICTS:
        c = int((v == имя).sum())
        строка[имя] = c
        строка[имя + ' %'] = round(100.0 * c / n, 2)
    строка['ни одной approved'] = int((appr == 0).sum())
    строка['ровно одна approved'] = int((appr == 1).sum())
    строка['обе approved'] = int((appr == 2).sum())
    строка['разные content_hash'] = int((z['hash_a'][m] != z['hash_b'][m]).sum())
    строка['картинка у обеих'] = int(((имг_a > 0) & (имг_b > 0)).sum())
    строка['картинка у одной'] = int(((имг_a > 0) ^ (имг_b > 0)).sum())
    return строка


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--enriched', nargs='+', required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    отчёт = {}
    for path in args.enriched:
        z = np.load(path)
        имя = path.split('enriched_')[-1].replace('.npz', '')
        строки = [s for s in (block(z, t) for t in THRESHOLDS) if s]
        отчёт[имя] = строки
        print('\n=== %s ===' % имя)
        print('%-7s %7s %9s %9s %13s %9s' %
              ('порог', 'пар', 'совпад.', 'частич.', 'НЕ совпад.', 'одна'))
        for s in строки:
            print('%-7.3f %7d %6d %2.0f%% %6d %2.0f%% %7d %4.1f%% %5d %2.0f%%'
                  % (s['порог'], s['пар'],
                     s['совпадают'], s['совпадают %'],
                     s['частично'], s['частично %'],
                     s['не совпадают'], s['не совпадают %'],
                     s['числа только у одной'], s['числа только у одной %']))
    if args.out:
        json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('\nзаписано: %s' % args.out)


if __name__ == '__main__':
    main()
