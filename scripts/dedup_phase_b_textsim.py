# -*- coding: utf-8 -*-
"""ФАЗА B.3 — проверка гипотезы «косинус лучше совпадает с дублированием ТЕКСТА».

Косинус считается по ОТПЕЧАТКУ (формула), а дубль — это совпадение
ПОЛНОГО текста задачи. Здесь меряется, насколько одно предсказывает другое:
для каждой пары считается символьная близость полных текстов (Жаккар по
3-граммам нормализованного условия вместе с подпунктами) — метрика, ничего
не знающая ни про одну формулу.

Заодно ловится главный риск короткой формулы `v1`: она кодирует лишь первые
500 символов условия, и две РАЗНЫЕ длинные задачи с общей шапкой могут
получить высокий косинус. Признак `общая шапка` показывает такие пары прямо.

Только чтение.
"""
import argparse
import json
import os
import re
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import fetch_attrs, connect, full_text  # noqa: E402

_WS_RE = re.compile(r'\s+')
#: Бюджет условия у формулы v1 — ровно столько символов она и видит.
V1_STATEMENT_BUDGET = 500


def normalize(text):
    return _WS_RE.sub(' ', (text or '').lower()).strip()


def trigrams(text):
    t = normalize(text)
    return {t[i:i + 3] for i in range(max(len(t) - 2, 0))} or {t}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--enriched', nargs='+', required=True)
    ap.add_argument('--min-sim', type=float, default=0.97)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    отчёт = {}
    con = connect()
    for path in args.enriched:
        имя = path.split('enriched_')[-1].replace('.npz', '')
        z = np.load(path)
        m = z['sim'] >= args.min_sim
        ia, ib, sim = z['id_a'][m], z['id_b'][m], z['sim'][m]
        ids = np.union1d(ia, ib)
        attrs = fetch_attrs(con, ids)
        тексты = {int(i): full_text(attrs[int(i)]) for i in ids}
        граммы = {i: trigrams(t) for i, t in тексты.items()}

        близость = np.array([jaccard(граммы[int(a)], граммы[int(b)])
                             for a, b in zip(ia, ib)])
        # Общая шапка: первые 500 символов совпадают, а полные тексты — нет.
        шапка = np.array([
            normalize(тексты[int(a)])[:V1_STATEMENT_BUDGET]
            == normalize(тексты[int(b)])[:V1_STATEMENT_BUDGET]
            and normalize(тексты[int(a)]) != normalize(тексты[int(b)])
            for a, b in zip(ia, ib)])
        длинные = np.array([
            len(тексты[int(a)]) > V1_STATEMENT_BUDGET
            and len(тексты[int(b)]) > V1_STATEMENT_BUDGET
            for a, b in zip(ia, ib)])

        n = len(sim) or 1
        отчёт[имя] = {
            'порог': args.min_sim, 'пар': int(len(sim)),
            'текст Жаккар медиана': round(float(np.median(близость)), 4),
            'текст Жаккар среднее': round(float(близость.mean()), 4),
            'доля пар Жаккар >= 0,80': round(float((близость >= 0.80).mean()), 4),
            'доля пар Жаккар >= 0,50': round(float((близость >= 0.50).mean()), 4),
            'доля пар Жаккар < 0,30': round(float((близость < 0.30).mean()), 4),
            'пар Жаккар < 0,30': int((близость < 0.30).sum()),
            'общая шапка 500 символов': int(шапка.sum()),
            'общая шапка %': round(100.0 * шапка.sum() / n, 2),
            'обе длиннее 500': int(длинные.sum()),
        }
        print('%-20s пар %6d  Жаккар медиана %.3f  >=0,80 %5.1f%%  '
              '<0,30 %5.1f%% (%d)  общая шапка %d'
              % (имя, len(sim), np.median(близость),
                 100 * (близость >= 0.80).mean(),
                 100 * (близость < 0.30).mean(), int((близость < 0.30).sum()),
                 int(шапка.sum())), flush=True)
    con.close()
    json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('записано: %s' % args.out)


if __name__ == '__main__':
    main()
