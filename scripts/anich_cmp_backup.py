# -*- coding: utf-8 -*-
"""Сверка живой базы с бэкапом.

⚠️ ПРО ЗУБАСТОСТЬ. Канарейка «сколько задач сменили темы» работает ТОЛЬКО против
базы, в которой такое изменение заведомо есть (бэкап 13.08 — там 133 задачи от
merge_topics). Против свежего бэкапа тем никто не менял, и ноль там — ПРАВИЛЬНЫЙ
ответ, а не слепота прибора. Поэтому ожидание канарейки задаётся аргументом
--canary N, а сама зубастость доказывается встроенной самопроверкой: сверке
подсовывается порча, и она обязана её увидеть. Самопроверка не зависит от того,
какой бэкап взят.
"""
import sqlite3, sys, collections, json
LIVE='db.sqlite3'
BASE=sys.argv[1]
ONLY_REST = '--rest' in sys.argv
CANARY_EXPECT = None
for i, a in enumerate(sys.argv):
    if a == '--canary' and i + 1 < len(sys.argv):
        CANARY_EXPECT = int(sys.argv[i + 1])

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

print("\n=== САМОПРОВЕРКА: сверка обязана видеть порчу ===")
# Берём первую задачу, портим значение на стороне бэкапа и смотрим, поймано ли.
probe_id = min(set(L) & set(O) & scope)
seen = 0
for idx, fname in ((1, 'statement'), (7, 'status')):
    spoiled = list(O[probe_id]); spoiled[idx] = (str(spoiled[idx]) or '') + 'ПОРЧА'
    if tuple(spoiled) != L[probe_id]:
        seen += 1
    print(f"  порча поля {fname:<12}: {'видит' if tuple(spoiled) != L[probe_id] else 'СЛЕПА'}")
print("вердикт самопроверки:", "сверка зубастая" if seen == 2 else "!!! СВЕРКА СЛЕПА — чинить !!!")

print("\n=== КАНАРЕЙКА: задачи со сменой набора тем ===")
print(f"найдено: {len(changed_topics)}")
if CANARY_EXPECT is None:
    print("  ожидание не задано (--canary N). Против свежего бэкапа ноль — это")
    print("  ПРАВИЛЬНЫЙ ответ: тем никто не менял. Канарейка осмысленна только")
    print("  против базы, где известное изменение заведомо есть.")
else:
    print(f"  ожидалось около {CANARY_EXPECT}")
    print("  вердикт:", "канарейка сработала" if changed_topics else "!!! КАНАРЕЙКА МОЛЧИТ — сверка под подозрением !!!")

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
