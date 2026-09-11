# -*- coding: utf-8 -*-
"""ФАЗА E — короткая структурная перепроверка автосхлопа 08.06.2026.

Не текстовый аудит: только пересчёт чисел прошлой сессии и один новый
вопрос — сколько среди выведенных из каталога задач имеют картинку,
которой у победившего дубликата нет.

Картинка — `ProblemFigure` из условия (`source_field` = `statement` или
`import`), а не `FileAsset`: та таблица в базе пуста (см. фазу D).

Только чтение.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import connect  # noqa: E402

FIGURE_FIELDS = ('statement', 'import')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    con = connect()

    # 1. Пересчёт чисел прошлой сессии.
    пары = list(con.execute(
        "SELECT problem_a_id, problem_b_id, similarity "
        "FROM problems_duplicatecandidate"))
    b_high = {b for _, b, s in пары if s >= 0.97}
    b_mid = {b for _, b, s in пары if 0.95 <= s < 0.97}
    все_b = {b for _, b, _ in пары}

    статус = dict(con.execute("SELECT id, status FROM problems_problem"))
    dup_of = dict(con.execute(
        "SELECT id, duplicate_of_id FROM problems_problem"))
    review = dict(con.execute(
        "SELECT id, COALESCE(human_review, '') FROM problems_problem"))

    как_duplicate = {i for i, s in статус.items() if s == 'duplicate'}
    с_duplicate_of = {i for i, v in dup_of.items() if v}

    # 2. Картинки: фигуры в условии.
    фигуры = defaultdict(int)
    q = ("SELECT problem_id, COUNT(*) FROM problems_problemfigure "
         "WHERE source_field IN (%s) GROUP BY problem_id"
         % ','.join('?' * len(FIGURE_FIELDS)))
    for pid, c in con.execute(q, FIGURE_FIELDS):
        фигуры[pid] = c
    фигуры_любые = defaultdict(int)
    for pid, c in con.execute(
            "SELECT problem_id, COUNT(*) FROM problems_problemfigure "
            "GROUP BY problem_id"):
        фигуры_любые[pid] = c
    con.close()

    выведены = все_b & (как_duplicate | с_duplicate_of)

    # Для каждой выведенной задачи — победители, оставшиеся видимыми.
    победители = defaultdict(set)
    for a, b, _ in пары:
        победители[b].add(a)

    потеря = []
    потеря_любая = []
    for b in sorted(выведены):
        if not фигуры.get(b) and not фигуры_любые.get(b):
            continue
        соперники = победители[b]
        живые = [a for a in соперники
                 if статус.get(a) not in ('duplicate', 'hidden')]
        опора = живые or list(соперники)
        if фигуры.get(b) and not any(фигуры.get(a) for a in опора):
            потеря.append({'скрыта': b, 'фигур в условии': фигуры[b],
                           'победители': sorted(опора)[:5],
                           'живых победителей': len(живые)})
        if фигуры_любые.get(b) and not any(фигуры_любые.get(a) for a in опора):
            потеря_любая.append(b)

    с_фигурой = sum(1 for b in выведены if фигуры_любые.get(b))
    с_фигурой_условия = sum(1 for b in выведены if фигуры.get(b))

    итог = {
        'строк DuplicateCandidate': len(пары),
        'уникальных problem_b': len(все_b),
        'problem_b при similarity >= 0,97': len(b_high),
        'problem_b при 0,95 <= similarity < 0,97': len(b_mid),
        'в обеих группах': len(b_high & b_mid),
        'status=duplicate всего в банке': len(как_duplicate),
        'duplicate_of не пуст всего в банке': len(с_duplicate_of),
        'ВЫВЕДЕНО ИЗ КАТАЛОГА прогоном 08.06': len(выведены),
        'из них approved': sum(1 for b in выведены if review.get(b) == 'approved'),
        'из них с фигурой (любой)': с_фигурой,
        'из них с фигурой в условии': с_фигурой_условия,
        'ПОТЕРЯ КАРТИНКИ (фигура в условии есть у скрытой, нет у победителя)':
            len(потеря),
        'доля потери от выведенных': round(len(потеря) / max(len(выведены), 1), 4),
        'то же по любой фигуре': len(потеря_любая),
        'примеры потери': потеря[:25],
    }
    json.dump(итог, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    краткий = {k: v for k, v in итог.items() if k != 'примеры потери'}
    print(json.dumps(краткий, ensure_ascii=False, indent=1))
    print('\nпримеры (до 25):')
    for e in потеря[:25]:
        print('  скрыта %6d (фигур %d) -> победители %s, живых %d'
              % (e['скрыта'], e['фигур в условии'], e['победители'],
                 e['живых победителей']))


if __name__ == '__main__':
    main()
