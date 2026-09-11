# -*- coding: utf-8 -*-
"""ФАЗА C — группы `content_hash` и гейт по подпунктам.

`content_hash` — MD5 одного поля `statement`. Подпунктов он не видит, и
самая большая «группа точного совпадения» в банке — 30 РАЗНЫХ тестовых
заданий с общей шапкой, у которых различаются варианты ответа в
`ProblemPart`. Здесь считается, сколько групп переживёт гейт, который
подпункты учитывает.

Гейт: совпал хеш И совпало ЧИСЛО подпунктов И (если подпунктов больше нуля)
совпал набор «условие+ответ» по подпунктам.

Только чтение.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import connect  # noqa: E402

_WS_RE = re.compile(r'\s+')


def norm(text):
    return _WS_RE.sub(' ', (text or '')).strip()


def parts_fingerprint(parts):
    """Отпечаток подпунктов: условие и ответ каждого, по порядку.

    ⚠️ Метка пункта («а», «б») в отпечаток НЕ входит: метки не уникальны и
    у разных источников расставлены по-разному, а различать задачи должно
    содержимое.
    """
    куски = ['%s|%s' % (norm(st), norm(ans)) for st, ans in parts]
    return hashlib.md5(' '.join(куски).encode('utf-8')).hexdigest()


PART_SQL = ('SELECT problem_id, statement, answer FROM problems_problempart '
            'ORDER BY problem_id, "order", label, id')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    con = connect()
    хеши = defaultdict(list)
    for pid, h in con.execute(
            "SELECT id, content_hash FROM problems_problem "
            "WHERE content_hash IS NOT NULL AND content_hash <> ''"):
        хеши[h].append(pid)
    пусто = con.execute(
        "SELECT COUNT(*) FROM problems_problem "
        "WHERE content_hash IS NULL OR content_hash = ''").fetchone()[0]

    группы = {h: ids for h, ids in хеши.items() if len(ids) > 1}
    задач_в_группах = sum(len(v) for v in группы.values())

    нужны = {i for ids in группы.values() for i in ids}
    подпункты = defaultdict(list)
    for pid, st, ans in con.execute(PART_SQL):
        if pid in нужны:
            подпункты[pid].append((st, ans))
    con.close()

    размеры = defaultdict(int)
    for ids in группы.values():
        размеры[len(ids)] += 1

    # Дробим каждую группу хеша на подгруппы по отпечатку подпунктов.
    подгрупп_всего = 0
    выжило_групп = 0
    выжило_задач = 0
    лишних_после = 0
    лишних_до = задач_в_группах - len(группы)
    развалились = []
    без_подпунктов_групп = 0
    for h, ids in группы.items():
        по_отпечатку = defaultdict(list)
        for pid in ids:
            ч = подпункты.get(pid, [])
            по_отпечатку[(len(ч), parts_fingerprint(ч))].append(pid)
        подгрупп_всего += len(по_отпечатку)
        if all(not подпункты.get(pid) for pid in ids):
            без_подпунктов_групп += 1
        for ключ, члены in по_отпечатку.items():
            if len(члены) > 1:
                выжило_групп += 1
                выжило_задач += len(члены)
                лишних_после += len(члены) - 1
        if len(по_отпечатку) > 1:
            развалились.append({
                'hash': h, 'было': len(ids),
                'стало подгрупп': len(по_отпечатку),
                'размеры подгрупп': sorted(
                    (len(v) for v in по_отпечатку.values()), reverse=True),
                'пример id': sorted(ids)[:6],
            })

    отчёт = {
        'задач с непустым content_hash': sum(len(v) for v in хеши.values()),
        'задач с пустым content_hash': пусто,
        'групп точного совпадения ДО гейта': len(группы),
        'задач в них ДО': задач_в_группах,
        'лишних сверх одной ДО': лишних_до,
        'размеры групп ДО': dict(sorted(размеры.items())),
        'подгрупп после дробления': подгрупп_всего,
        'групп ПОСЛЕ гейта по подпунктам': выжило_групп,
        'задач в них ПОСЛЕ': выжило_задач,
        'лишних сверх одной ПОСЛЕ': лишних_после,
        'групп, развалившихся на части': len(развалились),
        'групп целиком без подпунктов': без_подпунктов_групп,
        'самые пострадавшие': sorted(
            развалились, key=lambda r: -r['было'])[:10],
    }
    json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    краткий = {k: v for k, v in отчёт.items() if k != 'самые пострадавшие'}
    print(json.dumps(краткий, ensure_ascii=False, indent=1))
    print('\nсамые пострадавшие группы:')
    for r in отчёт['самые пострадавшие']:
        print('  было %2d -> подгрупп %2d, размеры %s, id %s'
              % (r['было'], r['стало подгрупп'], r['размеры подгрупп'],
                 r['пример id']))


if __name__ == '__main__':
    main()
