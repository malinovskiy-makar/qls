# -*- coding: utf-8 -*-
"""ФАЗА D — правило картинки для пар «эталон против двойника».

Явный уровень = объединение двух источников пар:
  * косинусный гейт фазы B (формула, порог, числовой вердикт, близость текста);
  * группы `content_hash`, пережившие гейт по подпунктам (фаза C).

Наличие картинки определяется ЧИСТО СТРУКТУРНО, без единой догадки о том,
нужна ли задаче картинка по смыслу условия.

⚠️ Промпт называл признаком связь `files` → `FileAsset(kind in image/graph)`.
Замерено 11.09.2026: таблица `FileAsset` ПУСТА (0 строк), связь `files`
тоже (0 строк), то есть этот признак даёт ноль у всех 41 307 задач и решения
не несёт. Настоящий носитель картинок — `ProblemFigure`: 2 498 фигур у
1 706 задач. Считается он, в двух видах: любая фигура и фигура, пришедшая
из условия (`source_field` = `statement` или `import`), — фигура из
`solution` иллюстрирует решение, а не условие.

Правило: у двойника картинка есть, у approved нет → пара в ручную очередь,
автофаворит не назначается. Во всех остальных случаях approved побеждает.

Только чтение, ничего не применяется.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import connect, fetch_attrs  # noqa: E402
from dedup_phase_c_hash import PART_SQL, parts_fingerprint  # noqa: E402

#: Источники, названные в промпте фазы D. Сверяется вхождением подстроки:
#: в банке имена длинные («SolveHub — банк задач по экономике»).
TWIN_SOURCES = ('SolveHub', 'Школково')


def hash_pairs(con):
    """Пары из групп `content_hash`, переживших гейт фазы C."""
    хеши = defaultdict(list)
    for pid, h in con.execute(
            "SELECT id, content_hash FROM problems_problem "
            "WHERE content_hash IS NOT NULL AND content_hash <> ''"):
        хеши[h].append(pid)
    группы = {h: v for h, v in хеши.items() if len(v) > 1}
    нужны = {p for v in группы.values() for p in v}
    части = defaultdict(list)
    for pid, st, ans in con.execute(PART_SQL):
        if pid in нужны:
            части[pid].append((st, ans))
    пары = set()
    for ids in группы.values():
        по = defaultdict(list)
        for pid in ids:
            ч = части.get(pid, [])
            по[(len(ч), parts_fingerprint(ч))].append(pid)
        for члены in по.values():
            члены = sorted(члены)
            for i in range(len(члены)):
                for j in range(i + 1, len(члены)):
                    пары.add((члены[i], члены[j]))
    return пары


def twin_source(name):
    return any(s in (name or '') for s in TWIN_SOURCES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--explicit', required=True,
                    help='.npz явного уровня из dedup_phase_b_gate.py')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    z = np.load(args.explicit)
    из_косинуса = set(zip((int(x) for x in z['id_a']),
                          (int(x) for x in z['id_b'])))

    con = connect()
    из_хеша = hash_pairs(con)
    # Пара — неупорядоченная: нормализуем до (меньший, больший).
    def норм(пары):
        return {(min(a, b), max(a, b)) for a, b in пары}
    из_косинуса, из_хеша = норм(из_косинуса), норм(из_хеша)
    явные = sorted(из_косинуса | из_хеша)

    ids = sorted({x for p in явные for x in p})
    attrs = fetch_attrs(con, ids)
    con.close()

    итог = {
        'пар из косинусного гейта': len(из_косинуса),
        'пар из групп content_hash': len(из_хеша),
        'пересечение': len(из_косинуса & из_хеша),
        'ЯВНЫЙ УРОВЕНЬ всего пар': len(явные),
    }

    одна_approved = 0
    обе_approved = 0
    ни_одной = 0
    двойник_из_списка = 0
    в_очередь = 0
    approved_побеждает = 0
    очередь_примеры = []
    # Контроль: то же правило, но без ограничения на источник двойника.
    в_очередь_любой_источник = 0

    for a, b in явные:
        aa, ab = attrs[a], attrs[b]
        флаги = (aa['human_review'] == 'approved', ab['human_review'] == 'approved')
        if all(флаги):
            обе_approved += 1
            continue
        if not any(флаги):
            ни_одной += 1
            continue
        одна_approved += 1
        эталон, двойник = (a, b) if флаги[0] else (b, a)
        ае, ад = attrs[эталон], attrs[двойник]
        картинка_у_двойника = ад['figures_statement'] > 0
        картинка_у_эталона = ае['figures_statement'] > 0
        if картинка_у_двойника and not картинка_у_эталона:
            в_очередь_любой_источник += 1
        if not twin_source(ад['source']):
            approved_побеждает += 1
            continue
        двойник_из_списка += 1
        if картинка_у_двойника and not картинка_у_эталона:
            в_очередь += 1
            if len(очередь_примеры) < 25:
                очередь_примеры.append({
                    'approved': эталон, 'двойник': двойник,
                    'источник двойника': ад['source'],
                    'фигур у двойника': ад['figures'],
                    'из них в условии': ад['figures_statement'],
                    'ответ у approved': bool(ае['answer']),
                    'ответ у двойника': bool(ад['answer']),
                })
        else:
            approved_побеждает += 1

    итог.update({
        'пар без единой approved': ни_одной,
        'пар с обеими approved': обе_approved,
        'ПАР С РОВНО ОДНОЙ approved': одна_approved,
        'из них двойник из SolveHub/Школково': двойник_из_списка,
        'В РУЧНУЮ ОЧЕРЕДЬ по правилу картинки': в_очередь,
        'approved побеждает без ревью': approved_побеждает,
        'доля очереди от approved-пар': round(
            в_очередь / max(одна_approved, 1), 4),
        'справочно: очередь без ограничения по источнику': в_очередь_любой_источник,
        'примеры очереди': очередь_примеры,
    })
    json.dump(итог, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    краткий = {k: v for k, v in итог.items() if k != 'примеры очереди'}
    print(json.dumps(краткий, ensure_ascii=False, indent=1))
    print('\nпримеры очереди (до 25):')
    for e in очередь_примеры:
        print('  approved %6d  vs  двойник %6d (%s, фигур в условии %d)'
              % (e['approved'], e['двойник'], e['источник двойника'],
                 e['из них в условии']))


if __name__ == '__main__':
    main()
