# -*- coding: utf-8 -*-
"""Дословная сверка наших текстов с выгрузками Анича. Только чтение."""
import json, sqlite3, sys, collections

DB = 'db.sqlite3'
BASE = '/Users/makarmalinovskiy/Downloads/qls_handover_20260820'
FILES = [('ile.json', 2, 'ILE'), ('aa.json', 6, 'АА'), ('matek.json', 13, 'МатЭк')]

P_FIELDS = ['title', 'statement', 'answer', 'solution', 'problem_type', 'difficulty_native']
PART_FIELDS = ['statement', 'answer', 'solution']
VIS = ['status', 'needs_quality_review', 'solution_needs_review', 'duplicate_of']

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row

diffs = collections.defaultdict(list)
summary = []

for fname, sid, label in FILES:
    d = json.load(open(f'{BASE}/{fname}', encoding='utf-8'))
    probs = d['problems']
    ids = [p['id'] for p in probs]
    # наши задачи
    ours = {}
    CH = 900
    for i in range(0, len(ids), CH):
        chunk = ids[i:i+CH]
        ph = ','.join('?'*len(chunk))
        for r in con.execute(f"select id,title,statement,answer,solution,problem_type,difficulty,difficulty_native,status,needs_quality_review,solution_needs_review,duplicate_of_id from problems_problem where id in ({ph})", chunk):
            ours[r['id']] = dict(r)
    # наши подпункты
    oparts = collections.defaultdict(dict)
    for i in range(0, len(ids), CH):
        chunk = ids[i:i+CH]
        ph = ','.join('?'*len(chunk))
        for r in con.execute(f'select problem_id,"order",label,statement,answer,solution from problems_problempart where problem_id in ({ph})', chunk):
            oparts[r['problem_id']][(r['order'], r['label'])] = dict(r)

    n_missing = n_text = n_part = n_vis = 0
    hidden_n = 0
    for p in probs:
        pid = p['id']
        o = ours.get(pid)
        if o is None:
            n_missing += 1; diffs[label].append((pid, 'НЕТ_У_НАС', '', '')); continue
        if p['visibility']['status'] == 'hidden':
            hidden_n += 1
        for f in P_FIELDS:
            a = p.get(f); b = o.get(f)
            a = '' if a is None else a
            b = '' if b is None else b
            if str(a) != str(b):
                n_text += 1; diffs[label].append((pid, 'ТЕКСТ:'+f, repr(a)[:120], repr(b)[:120]))
        # difficulty отдельно (число)
        if p.get('difficulty') != o.get('difficulty'):
            n_text += 1; diffs[label].append((pid, 'ТЕКСТ:difficulty', p.get('difficulty'), o.get('difficulty')))
        # подпункты
        ap = {(x['order'], x['label']): x for x in p.get('parts') or []}
        bp = oparts.get(pid, {})
        if set(ap) != set(bp):
            n_part += 1
            diffs[label].append((pid, 'НАБОР_ПОДПУНКТОВ', sorted(ap), sorted(bp)))
        for k in set(ap) & set(bp):
            for f in PART_FIELDS:
                a = ap[k].get(f) or ''; b = bp[k].get(f) or ''
                if a != b:
                    n_part += 1; diffs[label].append((pid, f'ПОДПУНКТ{k}:{f}', repr(a)[:120], repr(b)[:120]))
        # видимость
        v = p['visibility']
        pairs = [('status', v['status'], o['status']),
                 ('needs_quality_review', bool(v['needs_quality_review']), bool(o['needs_quality_review'])),
                 ('solution_needs_review', bool(v['solution_needs_review']), bool(o['solution_needs_review'])),
                 ('duplicate_of', p.get('duplicate_of'), o['duplicate_of_id'])]
        for name, a, b in pairs:
            if a != b:
                n_vis += 1; diffs[label].append((pid, 'ВИДИМОСТЬ:'+name, a, b))
    summary.append((label, sid, len(probs), n_missing, n_text, n_part, n_vis, hidden_n))

print(f"{'источник':<8}{'id':>4}{'задач':>8}{'нет у нас':>11}{'текст≠':>9}{'подпункт≠':>11}{'видимость≠':>12}{'hidden':>8}")
tot = [0]*5
for label, sid, n, nm, nt, np_, nv, hid in summary:
    print(f"{label:<8}{sid:>4}{n:>8}{nm:>11}{nt:>9}{np_:>11}{nv:>12}{hid:>8}")
    tot[0]+=n; tot[1]+=nm; tot[2]+=nt; tot[3]+=np_; tot[4]+=nv
print(f"{'ИТОГО':<8}{'':>4}{tot[0]:>8}{tot[1]:>11}{tot[2]:>9}{tot[3]:>11}{tot[4]:>12}")

print("\n=== ПРИМЕРЫ РАСХОЖДЕНИЙ (до 25) ===")
shown = 0
for label, rows in diffs.items():
    for r in rows[:25]:
        print(f"  [{label}] id={r[0]} {r[1]}\n     Анич: {r[2]}\n     Мак : {r[3]}")
        shown += 1
        if shown >= 25: break
    if shown >= 25: break
if not shown:
    print("  нет ни одного")

allbad = sum(len(v) for v in diffs.values())
print(f"\nВСЕГО РАСХОЖДЕНИЙ: {allbad}")
