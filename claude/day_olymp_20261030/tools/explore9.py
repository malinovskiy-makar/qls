import re
from collections import Counter
from problems.models import ProblemPart
from olympiads.package_clean import s4_problem_ids
ws = lambda s: re.sub(r'\s+', '', s or '')
ed = {i for i in s4_problem_ids() if i >= 53709}
parts = list(ProblemPart.objects.filter(problem_id__in=ed).order_by('problem_id','order','id').values())
by={}
for p in parts: by.setdefault(p['problem_id'],[]).append(p)
c=Counter(); ex=[]
for pid, ps in by.items():
    groups={}
    for p in ps: groups.setdefault(p['label'],[]).append(p)
    for lab, g in groups.items():
        if len(g)<2: continue
        texts={ws(x['statement']) for x in g}; pts={x['points'] for x in g}
        if len(texts)>1: c['text']+=1
        elif len(pts)>1: c['points only']+=1; ex.append((pid, lab, [x['points'] for x in g]))
        else: c['same']+=1
print(c); print(ex[:10])
