# -*- coding: utf-8 -*-
"""Зубастость сверки 0.3: портим по одному значению в данных Анича и ждём, что сверка увидит."""
import json, sqlite3, collections
BASE='/Users/makarmalinovskiy/Downloads/qls_handover_20260820'
con=sqlite3.connect('db.sqlite3'); con.row_factory=sqlite3.Row
d=json.load(open(f'{BASE}/aa.json',encoding='utf-8'))
probs=d['problems'][:400]
ids=[p['id'] for p in probs]
ph=','.join('?'*len(ids))
ours={r['id']:dict(r) for r in con.execute(f"select id,title,statement,answer,solution,problem_type,difficulty_native,status,needs_quality_review,duplicate_of_id from problems_problem where id in ({ph})",ids)}
oparts=collections.defaultdict(dict)
for r in con.execute(f'select problem_id,"order",label,statement,answer,solution from problems_problempart where problem_id in ({ph})',ids):
    oparts[r['problem_id']][(r['order'],r['label'])]=dict(r)

def count_diffs(probs):
    n=0
    for p in probs:
        o=ours[p['id']]
        for f in ['title','statement','answer','solution','problem_type','difficulty_native']:
            a=p.get(f) or ''; b=o.get(f) or ''
            if str(a)!=str(b): n+=1
        ap={(x['order'],x['label']):x for x in p.get('parts') or []}
        bp=oparts.get(p['id'],{})
        if set(ap)!=set(bp): n+=1
        for k in set(ap)&set(bp):
            for f in ['statement','answer','solution']:
                if (ap[k].get(f) or '')!=(bp[k].get(f) or ''): n+=1
        v=p['visibility']
        if v['status']!=o['status']: n+=1
        if bool(v['needs_quality_review'])!=bool(o['needs_quality_review']): n+=1
        if p.get('duplicate_of')!=o['duplicate_of_id']: n+=1
    return n

print("контроль без порчи (ожидаем 0):", count_diffs(probs))

cases=[]
# 1. один символ в statement
m=json.loads(json.dumps(probs)); m[0]['statement']=m[0]['statement'][:-1]+'Ж'
cases.append(('один символ в statement', m))
# 2. пробел в конце title
m=json.loads(json.dumps(probs)); m[1]['title']=(m[1]['title'] or '')+' '
cases.append(('лишний пробел в title', m))
# 3. смена статуса
m=json.loads(json.dumps(probs)); m[2]['visibility']['status']='hidden' if m[2]['visibility']['status']!='hidden' else 'draft'
cases.append(('смена status', m))
# 4. подпункт: правка текста
m=json.loads(json.dumps(probs))
for x in m:
    if x.get('parts'):
        x['parts'][0]['statement']=(x['parts'][0]['statement'] or '')+'X'; break
cases.append(('символ в подпункте', m))
# 5. пропавший подпункт
m=json.loads(json.dumps(probs))
for x in m:
    if x.get('parts'):
        x['parts'].pop(0); break
cases.append(('удалён подпункт', m))
# 6. флаг качества
m=json.loads(json.dumps(probs)); m[3]['visibility']['needs_quality_review']=not m[3]['visibility']['needs_quality_review']
cases.append(('смена needs_quality_review', m))
# 7. duplicate_of
m=json.loads(json.dumps(probs)); m[4]['duplicate_of']= 999999 if m[4].get('duplicate_of') is None else None
cases.append(('смена duplicate_of', m))

ok=True
for name,mut in cases:
    n=count_diffs(mut)
    good = n>0
    ok = ok and good
    print(f"  {'ВИДИТ ' if good else 'СЛЕПА!'} {name}: расхождений {n}")
print("\nВЕРДИКТ:", "сверка зубастая" if ok else "СВЕРКА СЛЕПА — чинить")
