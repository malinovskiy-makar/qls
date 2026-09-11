# -*- coding: utf-8 -*-
"""ФАЗА B.2 и далее — признаки пар поверх посчитанного косинуса.

Берёт `.npz` из `dedup_phase_b_pairs.py` и навешивает на каждую пару:
числовой вердикт (эвристика прошлой сессии, НЕ переписана), `human_review`,
источник, наличие картинки, `content_hash`, число подпунктов, статус.

Только SELECT: соединение открыто в режиме `file:...?mode=ro`.
"""
import argparse
import json
import os
import sqlite3
import sys

import numpy as np

# Рядом лежащий модуль прошлой сессии: эвристику НЕ переписываем, зовём ту же.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dedup_recon_numbers import compare_numbers  # noqa: E402

DB = os.path.abspath('db.sqlite3')
#: Типы файлов, которые считаются «к задаче приложена картинка».
#:
#: ⚠️ 11.09.2026 ЗАМЕРЕНО: таблица `problems_fileasset` ПУСТА (0 строк), и
#: связь `problems_problem_files` тоже пуста. То есть признак «картинка
#: через FileAsset» в этой базе даёт ноль для КАЖДОЙ задачи и решения не
#: несёт. Настоящий носитель картинок — `ProblemFigure` (2 498 фигур у
#: 1 706 задач), он и считается ниже в поле `figures`.
IMAGE_KINDS = ('image', 'graph')

#: Поля-источники фигуры. Фигура из `solution` иллюстрирует РЕШЕНИЕ, а не
#: условие, и на вопрос «есть ли у задачи картинка в условии» не отвечает.
FIGURE_STATEMENT_FIELDS = ('statement', 'import')


def connect():
    путь = DB.replace(os.sep, '/')
    return sqlite3.connect('file:%s?mode=ro' % путь, uri=True)


def fetch_attrs(con, ids):
    """Признаки задач одним проходом. Возвращает dict id -> словарь."""
    con.execute('DROP TABLE IF EXISTS temp.wanted')
    con.execute('CREATE TEMP TABLE wanted (id INTEGER PRIMARY KEY)')
    con.executemany('INSERT OR IGNORE INTO temp.wanted VALUES (?)',
                    ((int(i),) for i in ids))

    attrs = {}
    q = """
        SELECT p.id, p.statement, p.human_review, p.status, p.content_hash,
               p.hidden_pending_review, p.content_status, p.answer,
               p.solution, p.duplicate_of_id
        FROM problems_problem p JOIN temp.wanted w ON w.id = p.id
    """
    for row in con.execute(q):
        attrs[row[0]] = {
            'statement': row[1] or '', 'human_review': row[2] or '',
            'status': row[3] or '', 'content_hash': row[4] or '',
            'hidden_pending': bool(row[5]), 'content_status': row[6] or '',
            'answer': (row[7] or '').strip(),
            'solution': (row[8] or '').strip(),
            'duplicate_of': row[9],
            'parts': 0, 'parts_text': '', 'images': 0, 'source': '',
            'figures': 0, 'figures_statement': 0,
        }

    # Подпункты: число и склейка условий (нужна числовому гейту — часть
    # чисел задачи живёт именно там, а content_hash их не видит).
    q = """
        SELECT sp.problem_id, COUNT(*), GROUP_CONCAT(COALESCE(sp.statement,''), ' ')
        FROM problems_problempart sp JOIN temp.wanted w ON w.id = sp.problem_id
        GROUP BY sp.problem_id
    """
    for pid, cnt, txt in con.execute(q):
        if pid in attrs:
            attrs[pid]['parts'] = cnt
            attrs[pid]['parts_text'] = txt or ''

    # Картинки — чисто структурно: связь files → FileAsset(kind in image/graph).
    q = """
        SELECT pf.problem_id, COUNT(*)
        FROM problems_problem_files pf
        JOIN problems_fileasset f ON f.id = pf.fileasset_id
        JOIN temp.wanted w ON w.id = pf.problem_id
        WHERE f.kind IN (%s)
        GROUP BY pf.problem_id
    """ % ','.join('?' * len(IMAGE_KINDS))
    for pid, cnt in con.execute(q, IMAGE_KINDS):
        if pid in attrs:
            attrs[pid]['images'] = cnt

    # Фигуры: настоящий носитель картинок в этой базе (см. IMAGE_KINDS).
    q = """
        SELECT f.problem_id, COUNT(*),
               SUM(CASE WHEN f.source_field IN (%s) THEN 1 ELSE 0 END)
        FROM problems_problemfigure f JOIN temp.wanted w ON w.id = f.problem_id
        GROUP BY f.problem_id
    """ % ','.join('?' * len(FIGURE_STATEMENT_FIELDS))
    for pid, всего, в_условии in con.execute(q, FIGURE_STATEMENT_FIELDS):
        if pid in attrs:
            attrs[pid]['figures'] = всего
            attrs[pid]['figures_statement'] = в_условии or 0

    # Источник — ПЕРВАЯ привязка, как в прошлой сессии.
    q = """
        SELECT sr.problem_id, s.name
        FROM problems_sourcereference sr
        JOIN problems_source s ON s.id = sr.source_id
        JOIN temp.wanted w ON w.id = sr.problem_id
        ORDER BY sr.problem_id, sr.id
    """
    for pid, name in con.execute(q):
        if pid in attrs and not attrs[pid]['source']:
            attrs[pid]['source'] = name or ''
    return attrs


def full_text(a, statement_only=False):
    """Текст для числового гейта.

    ⚠️ По умолчанию сюда входят И подпункты: часть чисел задачи живёт именно
    там, а `content_hash` их не видит (находка фазы 4 прошлой сессии).
    Флаг `--statement-only` оставлен ради сверки с числами прошлой сессии,
    которая читала одно поле `statement`.
    """
    if statement_only:
        return a['statement']
    return (a['statement'] + ' ' + a['parts_text']).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pairs', required=True)
    ap.add_argument('--min-sim', type=float, default=0.95)
    ap.add_argument('--statement-only', action='store_true')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    z = np.load(args.pairs)
    ia, ib, sim = z['id_a'], z['id_b'], z['sim']
    keep = sim >= args.min_sim
    ia, ib, sim = ia[keep], ib[keep], sim[keep]
    print('пар: %d (порог %.2f)' % (len(sim), args.min_sim), flush=True)

    con = connect()
    ids = np.union1d(ia, ib)
    attrs = fetch_attrs(con, ids)
    con.close()
    print('задач в парах: %d' % len(attrs), flush=True)

    verdicts = []
    cache = {}
    for pid in ids:
        cache[int(pid)] = full_text(attrs[int(pid)], args.statement_only)
    for a, b in zip(ia, ib):
        verdicts.append(compare_numbers(cache[int(a)], cache[int(b)]))

    np.savez_compressed(
        args.out, id_a=ia, id_b=ib, sim=sim,
        verdict=np.array(verdicts),
        approved_a=np.array([attrs[int(x)]['human_review'] == 'approved'
                             for x in ia]),
        approved_b=np.array([attrs[int(x)]['human_review'] == 'approved'
                             for x in ib]),
        images_a=np.array([attrs[int(x)]['images'] for x in ia]),
        images_b=np.array([attrs[int(x)]['images'] for x in ib]),
        parts_a=np.array([attrs[int(x)]['parts'] for x in ia]),
        parts_b=np.array([attrs[int(x)]['parts'] for x in ib]),
        source_a=np.array([attrs[int(x)]['source'] for x in ia]),
        source_b=np.array([attrs[int(x)]['source'] for x in ib]),
        hash_a=np.array([attrs[int(x)]['content_hash'] for x in ia]),
        hash_b=np.array([attrs[int(x)]['content_hash'] for x in ib]),
        answer_a=np.array([bool(attrs[int(x)]['answer']) for x in ia]),
        answer_b=np.array([bool(attrs[int(x)]['answer']) for x in ib]),
        solution_a=np.array([bool(attrs[int(x)]['solution']) for x in ia]),
        solution_b=np.array([bool(attrs[int(x)]['solution']) for x in ib]),
        status_a=np.array([attrs[int(x)]['status'] for x in ia]),
        status_b=np.array([attrs[int(x)]['status'] for x in ib]),
    )

    from collections import Counter
    print(json.dumps({'вердикты': Counter(verdicts)}, ensure_ascii=False,
                     indent=1, default=dict))


if __name__ == '__main__':
    main()
