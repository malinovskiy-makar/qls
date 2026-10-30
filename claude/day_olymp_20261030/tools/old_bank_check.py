"""Прежний банк не тронут: сравнение таблиц с снимком до дня.

    ./venv313/bin/python claude/day_olymp_20261030/tools/old_bank_check.py [база] [снимок]

Для каждой таблицы, где есть `problem_id`, и для самой `problems_problem`
сравнивает строки задач с id < 53709 в базе и в снимке (EXCEPT в обе
стороны). Печатает «таблица → строк различается» и код возврата 1, если
различий больше нуля. Базы открываются только на чтение.
"""
import sqlite3
import sys

S4_FIRST = 53709
db = sys.argv[1] if len(sys.argv) > 1 else 'db_screens.sqlite3'
snap = sys.argv[2] if len(sys.argv) > 2 else 'db_screens.before_day_20261030.sqlite3'
con = sqlite3.connect('file:{}?mode=ro'.format(db), uri=True)
con.execute("ATTACH DATABASE 'file:{}?mode=ro' AS snap".format(snap))
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
checked, bad = 0, 0
for t in tables:
    cols = [r[1] for r in con.execute('PRAGMA table_info("{}")'.format(t))]
    snap_cols = [r[1] for r in con.execute('PRAGMA snap.table_info("{}")'.format(t))]
    if t == 'problems_problem':
        where = 'id < {}'.format(S4_FIRST)
    elif 'problem_id' in cols:
        where = 'problem_id < {}'.format(S4_FIRST)
    else:
        continue
    if not snap_cols:
        print('{:<45} нет в снимке'.format(t)); continue
    common = ', '.join('"{}"'.format(c) for c in cols if c in snap_cols)
    q = ('SELECT COUNT(*) FROM (SELECT {c} FROM main."{t}" WHERE {w} EXCEPT SELECT {c} FROM snap."{t}" WHERE {w})'
         .format(c=common, t=t, w=where))
    q2 = q.replace('main."', 'X."').replace('snap."', 'main."').replace('X."', 'snap."')
    n = con.execute(q).fetchone()[0] + con.execute(q2).fetchone()[0]
    checked += 1
    bad += n
    if n:
        print('{:<45} РАЗЛИЧАЕТСЯ строк: {}'.format(t, n))
print('таблиц сверено: {}; различающихся строк прежних задач: {}'.format(checked, bad))
sys.exit(1 if bad else 0)
