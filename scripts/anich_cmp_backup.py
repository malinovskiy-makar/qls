# -*- coding: utf-8 -*-
"""Сверка живой базы с бэкапом до 18.08. Канарейка — 132 задачи со сменой тем (merge_topics 13.08)."""
import sqlite3, sys, collections, json
LIVE='db.sqlite3'
BASE=sys.argv[1]
ONLY_REST = '--rest' in sys.argv

live=sqlite3.connect(LIVE); live.row_factory=sqlite3.Row
old =sqlite3.connect(BASE); old.row_factory=sqlite3.Row

# id трёх источников — их уже сверили с Аничем
three=set(r[0] for r in live.execute("select distinct problem_id from problems_sourcereference where source_id in (2,6,13)"))
print(f"задач трёх источников: {len(three)}")

PF=['title','statement','answer','solution','problem_type','difficulty','difficulty_native',
    'status','needs_quality_review','solution_needs_review','duplicate_of_id']
sel="select id,"+",".join(f'"{f}"' for f in PF)+" from problems_problem"

def load(con):
    return {r['id']: tuple(r[f] for f in PF) for r in con.execute(sel)}

L=load(live); O=load(old)
scope = (set(L)|set(O)) - three if ONLY_REST else (set(L)|set(O))
print(f"в сверке задач: {len(scope)}")

only_live = sorted((set(L)-set(O)) & scope)
only_old  = sorted((set(O)-set(L)) & scope)
field_diff=collections.Counter(); examples=[]
for pid in sorted(set(L)&set(O)&scope):
    a,b=O[pid],L[pid]
    if a!=b:
        for i,f in enumerate(PF):
            if a[i]!=b[i]:
                field_diff[f]+=1
                if len(examples)<15: examples.append((pid,f,repr(a[i])[:90],repr(b[i])[:90]))

# подпункты
def loadp(con):
    d=collections.defaultdict(dict)
    for r in con.execute('select problem_id,"order",label,statement,answer,solution from problems_problempart'):
        d[r['problem_id']][(r['order'],r['label'])]=(r['statement'],r['answer'],r['solution'])
    return d
LP=loadp(live); OP=loadp(old)
part_set=0; part_field=collections.Counter(); pex=[]
for pid in sorted(set(LP)|set(OP)):
    if pid not in scope: continue
    a=OP.get(pid,{}); b=LP.get(pid,{})
    if set(a)!=set(b):
        part_set+=1
        if len(pex)<8: pex.append((pid,'НАБОР',sorted(a),sorted(b)))
    for k in set(a)&set(b):
        for i,f in enumerate(['statement','answer','solution']):
            if (a[k][i] or '')!=(b[k][i] or ''):
                part_field[f]+=1
                if len(pex)<8: pex.append((pid,f'подпункт{k}:{f}',repr(a[k][i])[:90],repr(b[k][i])[:90]))

# КАНАРЕЙКА: темы
def topics(con):
    d=collections.defaultdict(set)
    for pid,tid in con.execute("select problem_id, topic_id from problems_problem_topics"):
        d[pid].add(tid)
    return d
LT=topics(live); OT=topics(old)
changed_topics=[pid for pid in (set(LT)|set(OT)) if LT.get(pid,set())!=OT.get(pid,set())]

print("\n=== КАНАРЕЙКА (проверка на зубастость) ===")
print(f"задач со сменой набора тем: {len(changed_topics)}   (ожидается 132 от merge_topics 13.08)")
print("вердикт канарейки:", "СВЕРКА ВИДИТ ИЗМЕНЕНИЯ" if changed_topics else "!!! СВЕРКА СЛЕПА !!!")

print("\n=== РАСХОЖДЕНИЯ В ЗАДАЧАХ ===")
print(f"есть только в живой базе: {len(only_live)}   {only_live[:10]}")
print(f"есть только в бэкапе    : {len(only_old)}   {only_old[:10]}")
if field_diff:
    for f,n in field_diff.most_common(): print(f"  {f:<24} {n}")
else:
    print("  по всем 11 полям: 0")
print("\n=== РАСХОЖДЕНИЯ В ПОДПУНКТАХ ===")
print(f"задач с иным набором подпунктов: {part_set}")
if part_field:
    for f,n in part_field.most_common(): print(f"  {f:<12} {n}")
else:
    print("  по трём полям: 0")
if examples:
    print("\n=== ПРИМЕРЫ (задачи) ===")
    for e in examples: print(f"  id={e[0]} {e[1]}\n     бэкап: {e[2]}\n     живая: {e[3]}")
if pex:
    print("\n=== ПРИМЕРЫ (подпункты) ===")
    for e in pex: print(f"  id={e[0]} {e[1]}\n     бэкап: {e[2]}\n     живая: {e[3]}")
total=len(only_live)+len(only_old)+sum(field_diff.values())+part_set+sum(part_field.values())
print(f"\nВСЕГО РАСХОЖДЕНИЙ (тексты+видимость+подпункты): {total}")
