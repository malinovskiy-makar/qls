# -*- coding: utf-8 -*-
"""ФАЗА B.4 — предложенный гейт «явного» уровня, посчитанный, но НЕ применённый.

Гейт — связка, а не один порог: косинус отбирает кандидатов, числовой
вердикт и символьная близость полных текстов запрещают схлопывание там,
где тексты на самом деле разные.

Пишет список пар явного уровня в `.npz` — его читают фазы C, D и E.
Базу не меняет.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import fetch_attrs, connect, full_text  # noqa: E402
from dedup_phase_b_textsim import trigrams, jaccard, normalize  # noqa: E402

V1_STATEMENT_BUDGET = 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--enriched', required=True)
    ap.add_argument('--cos', type=float, default=0.98)
    ap.add_argument('--jaccard', type=float, default=0.80)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    z = np.load(args.enriched)
    m = z['sim'] >= args.cos
    поля = {k: z[k][m] for k in z.files if z[k].shape and z[k].shape[0] == len(z['sim'])}
    ia, ib, sim = поля['id_a'], поля['id_b'], поля['sim']

    con = connect()
    ids = np.union1d(ia, ib)
    attrs = fetch_attrs(con, ids)
    con.close()
    тексты = {int(i): full_text(attrs[int(i)]) for i in ids}
    граммы = {i: trigrams(t) for i, t in тексты.items()}

    jac = np.array([jaccard(граммы[int(a)], граммы[int(b)])
                    for a, b in zip(ia, ib)])
    шапка = np.array([
        normalize(тексты[int(a)])[:V1_STATEMENT_BUDGET]
        == normalize(тексты[int(b)])[:V1_STATEMENT_BUDGET]
        and normalize(тексты[int(a)]) != normalize(тексты[int(b)])
        for a, b in zip(ia, ib)])

    числа_ок = поля['verdict'] == 'совпадают'
    текст_ок = jac >= args.jaccard
    явный = числа_ок & текст_ок

    n = len(sim) or 1
    сводка = {
        'косинус >=': args.cos, 'жаккар >=': args.jaccard,
        'пар выше косинуса': int(len(sim)),
        'из них числа совпадают': int(числа_ок.sum()),
        'из них текст близок': int(текст_ок.sum()),
        'ЯВНЫЙ уровень (обе проверки)': int(явный.sum()),
        'доля явных от пула': round(float(явный.sum()) / n, 4),
        'отсеяно числовым гейтом': int((~числа_ок).sum()),
        'отсеяно текстовым гейтом': int((числа_ок & ~текст_ок).sum()),
        'общая шапка среди пула': int(шапка.sum()),
        'общая шапка среди явных': int((шапка & явный).sum()),
        'жаккар явных: медиана': round(float(np.median(jac[явный])), 4) if явный.any() else None,
        'жаккар явных: минимум': round(float(jac[явный].min()), 4) if явный.any() else None,
    }
    print(json.dumps(сводка, ensure_ascii=False, indent=1))

    сохранить = {k: v[явный] for k, v in поля.items()}
    сохранить['jaccard'] = jac[явный]
    сохранить['header_clash'] = шапка[явный]
    np.savez_compressed(args.out, **сохранить)
    json.dump(сводка, open(args.out + '.summary.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('записано: %s (%d пар)' % (args.out, int(явный.sum())))


if __name__ == '__main__':
    main()
