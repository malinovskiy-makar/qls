import re, difflib
from collections import defaultdict
from olympiads import navigator as nav
from olympiads import bank_match as bm
vs = nav.base_variants().filter(olympiad__slug='vseros').select_related('stage')
groups = defaultdict(list)
for v in vs:
    groups[(v.stage_id, v.season, tuple(sorted(v.grades.values_list('grade', flat=True))))].append(v)
for key, kits in sorted(groups.items(), key=lambda kv: kv[0][1]):
    tours = {v.tour: v for v in kits}
    if not {'1','2'} <= set(tours): continue
    ia = {i.number: i for i in tours['1'].items.select_related('problem')}; ib = {i.number: i for i in tours['2'].items.select_related('problem')}
    rs=[]
    for n in ia:
        if n in ib:
            a=bm.norm(ia[n].problem.statement)[:600]; b=bm.norm(ib[n].problem.statement)[:600]
            r=difflib.SequenceMatcher(None,a,b,autojunk=False).ratio()
            rs.append((n, round(r,2)))
    print(key[1], key[2], rs)
