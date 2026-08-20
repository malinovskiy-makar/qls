# -*- coding: utf-8 -*-
"""Фаза 4: сверка нашей базы с паспортом Анича (state.json). Только чтение.

Разошлось хоть одно число — это НЕ повод подгонять. Прибор печатает, что именно
разошлось, и возвращает код 1.
"""
import json, sqlite3, sys

DB = 'db.sqlite3'
STATE = sys.argv[1] if len(sys.argv) > 1 else '/Users/makarmalinovskiy/Downloads/state.json'

s = json.load(open(STATE, encoding='utf-8'))
con = sqlite3.connect(DB)
one = lambda q, *a: con.execute(q, a).fetchone()[0]

rows = []          # (раздел, показатель, у Анича, у нас)
def chk(section, name, expect, got):
    rows.append((section, name, expect, got))

# --- объёмы ---
chk('Объёмы', 'Problem',     s['db']['problem_total'],     one("select count(*) from problems_problem"))
chk('Объёмы', 'ProblemPart', s['db']['problempart_total'], one("select count(*) from problems_problempart"))

# --- human_review ---
hr = {k: 0 for k in ('approved', 'defect', 'empty')}
for v, n in con.execute("select human_review, count(*) from problems_problem group by 1"):
    hr['empty' if v == '' else v] = n
for k, label in (('approved', 'human_review approved'), ('defect', 'human_review defect'), ('empty', 'human_review пусто')):
    chk('Разметка', label, s['human_review'][k], hr.get(k, 0))

# --- признаки ---
f = s['flags']
chk('Признаки', 'hidden_pending_review',  f['hidden_pending_review_true'],  one("select count(*) from problems_problem where hidden_pending_review=1"))
chk('Признаки', 'needs_quality_review',   f['needs_quality_review_true'],   one("select count(*) from problems_problem where needs_quality_review=1"))
chk('Признаки', 'solution_needs_review',  f['solution_needs_review_true'],  one("select count(*) from problems_problem where solution_needs_review=1"))
chk('Признаки', 'duplicate_of непусто',   f['duplicate_of_not_null'],       one("select count(*) from problems_problem where duplicate_of_id is not null"))
chk('Признаки', 'задач с embedding',      f['embedding_not_empty'],         one("select count(*) from problems_problem where embedding is not null and length(embedding)>0"))

# --- длина эмбеддинга ---
lens = con.execute("select distinct length(embedding) from problems_problem where embedding is not null").fetchall()
chk('Признаки', 'длина embedding, байт', 4096, lens[0][0] if len(lens) == 1 else f'РАЗНЫЕ: {[x[0] for x in lens]}')

# --- статусы ---
st = dict(con.execute("select status, count(*) from problems_problem group by 1"))
for k, v in s['status'].items():
    chk('Статусы', f'status={k}', v, st.get(k, 0))

# --- вердикты ---
chk('Вердикты', 'ReviewVerdict всего', s['review_verdict_total'], one("select count(*) from problems_reviewverdict"))
by_b = {b: (r, p) for b, r, p in con.execute(
    "select bundle, count(*), count(distinct problem_id) from problems_reviewverdict group by 1")}
for e in s['review_verdict_by_bundle']:
    b = e['bundle']
    chk('Вердикты', f'{b}: строк',  e['rows'],     by_b.get(b, (0, 0))[0])
    chk('Вердикты', f'{b}: задач',  e['problems'], by_b.get(b, (0, 0))[1])

# --- 23/24 пары (пакет × категория) ---
by_bc = {(b, c): n for b, c, n in con.execute(
    "select bundle, category, count(*) from problems_reviewverdict group by 1,2")}
seen = set()
for e in s['review_verdict_by_bundle_category']:
    k = (e['bundle'], e['category']); seen.add(k)
    chk('Пары пакет×категория', f"{e['bundle']} / {e['category']}", e['count'], by_bc.get(k, 0))
for k in sorted(set(by_bc) - seen):
    chk('Пары пакет×категория', f'{k[0]} / {k[1]}', 'нет в паспорте', by_bc[k])

# --- по источникам ---
for e in s['sources']:
    sid = e['source_id_actual']; key = e['key']
    ids = f"(select problem_id from problems_sourcereference where source_id={sid})"
    chk('Источники', f'{key}: всего',        e['total'],        one(f"select count(distinct problem_id) from problems_sourcereference where source_id={sid}"))
    chk('Источники', f'{key}: approved',     e['approved'],     one(f"select count(*) from problems_problem where id in {ids} and human_review='approved'"))
    chk('Источники', f'{key}: defect',       e['defect'],       one(f"select count(*) from problems_problem where id in {ids} and human_review='defect'"))
    chk('Источники', f'{key}: без вердикта', e['no_verdict'],
        one(f"select count(*) from problems_problem where id in {ids} and human_review=''"))
    chk('Источники', f'{key}: видно в каталоге', e['visible_in_catalog'],
        one(f"""select count(*) from problems_problem where id in {ids}
                and status='published' and needs_quality_review=0 and hidden_pending_review=0"""))
    chk('Источники', f'{key}: hidden_pending_review', e['hidden_pending_review'],
        one(f"select count(*) from problems_problem where id in {ids} and hidden_pending_review=1"))
    chk('Источники', f'{key}: id источника', e['source_id_expected'], e['source_id_actual'])

# --- печать ---
bad = [r for r in rows if str(r[2]) != str(r[3])]
sec = None
print(f"{'показатель':<44}{'у Анича':>16}{'у нас':>16}  сошлось")
print('-' * 88)
for section, name, exp, got in rows:
    if section != sec:
        sec = section; print(f'\n[{sec}]')
    mark = 'да' if str(exp) == str(got) else '*** НЕТ ***'
    print(f"  {name:<42}{str(exp):>16}{str(got):>16}  {mark}")
print('-' * 88)
print(f"\nвсего сверено показателей: {len(rows)}, разошлось: {len(bad)}")
if bad:
    print('\n!!! РАЗОШЛОСЬ !!!')
    for section, name, exp, got in bad:
        print(f'  [{section}] {name}: у Анича {exp}, у нас {got}')
    sys.exit(1)
print('\nВЕРДИКТ: состояние воспроизведено точно — все числа паспорта совпали.')
