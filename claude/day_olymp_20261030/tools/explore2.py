import re
from problems.models import ProblemPart
ws = lambda s: re.sub(r'\s+', '', s or '')
parts = list(ProblemPart.objects.filter(problem__id__range=(53709,61361)).order_by('problem_id','order','id').values('id','problem_id','label','statement','points','order'))
by = {}
for p in parts: by.setdefault(p['problem_id'], []).append(p)
n=0; kinds={}
for pid, ps in by.items():
    labels=[p['label'] for p in ps]
    if len(set(labels))==len(labels): continue
    keys=[(p['label'],ws(p['statement'])) for p in ps]
    if len(set(keys))<len(keys): continue
    n+=1
    if n<=6:
        print('==', pid, labels)
        seen={}
        for p in ps:
            if p['label'] in seen:
                a=seen[p['label']]; print('  ', p['label'], repr(a['statement'][:90]), a['points'], '|', repr(p['statement'][:90]), p['points'])
            else: seen[p['label']]=p
print('label dup, text differs', n)
# pattern: sequences
from collections import Counter
c=Counter()
for pid, ps in by.items():
    keys=[(p['label'],ws(p['statement'])) for p in ps]
    if len(set(keys))<len(keys):
        half=len(ps)//2
        c['abcabc' if len(ps)%2==0 and keys[:half]==keys[half:] else 'other']+=1
        pts=[(p['label'],ws(p['statement']),p['points']) for p in ps]
        if len(set(pts))!=len(set(keys)): c['points differ']+=1
print(c)
