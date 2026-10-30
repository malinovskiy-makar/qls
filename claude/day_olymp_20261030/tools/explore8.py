import re
from collections import Counter
from problems.models import ProblemPart
from olympiads.package_clean import s4_problem_ids
ws = lambda s: re.sub(r'\s+', '', s or '')
ed = {i for i in s4_problem_ids() if i >= 53709}
print('editable', len(ed))
parts = list(ProblemPart.objects.filter(problem_id__in=ed).order_by('problem_id','order','id').values())
by={}
for p in parts: by.setdefault(p['problem_id'],[]).append(p)
c=Counter(); dup_ids=[]
for pid, ps in by.items():
    groups={}
    for p in ps: groups.setdefault(p['label'],[]).append(p)
    conflict=False; dups=[]
    for lab, g in groups.items():
        if len(g)<2: continue
        keys={(ws(x['statement']), x['points']) for x in g}
        if len(keys)>1: conflict=True
        else:
            k=g[0]
            for x in g[1:]:
                dups.append(x['id'])
                if ws(x['answer'])!=ws(k['answer']): c['answer differs']+=1
                if ws(x['solution'])!=ws(k['solution']): c['solution differs']+=1
                if x['order']==k['order']: c['same order']+=1
    if dups and conflict: c['dups+conflict']+=1
    elif dups: c['dups only']+=1; dup_ids+=dups
    elif conflict: c['conflict only']+=1
print(c, len(dup_ids))
for rel in ProblemPart._meta.related_objects:
    m=rel.related_model; f=rel.field.name
    print(m.__name__, f, m.objects.filter(**{f+'__in':dup_ids}).count(), m.objects.filter(**{f+'__problem_id__in':ed}).count())
