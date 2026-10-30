import re
from collections import Counter
from problems.models import Problem, ProblemPart
S4 = (53709, 61361)
ws = lambda s: re.sub(r'\s+', '', s or '')
print('problems', Problem.objects.count())
parts = list(ProblemPart.objects.filter(problem__id__range=S4).values('id','problem_id','label','statement','points','order','answer','solution'))
print('S4 parts', len(parts))
by = {}
for p in parts: by.setdefault(p['problem_id'], []).append(p)
print('S4 problems with parts', len(by))
dup_label = sum(1 for ps in by.values() if len({p['label'] for p in ps}) < len(ps))
dup_key = sum(1 for ps in by.values() if len({(p['label'], ws(p['statement'])) for p in ps}) < len(ps))
print('dup label', dup_label, 'dup label+text', dup_key)
st = dict(Problem.objects.filter(id__in=by).values_list('id','statement'))
def inside(pid):
    s = ws(st[pid])
    return [ws(p['statement'])[:60] in s for p in by[pid] if ws(p['statement'])]
allin = sum(1 for pid in by if (r:=inside(pid)) and all(r))
anyin = sum(1 for pid in by if (r:=inside(pid)) and any(r))
print('parts text inside statement all', allin, 'any', anyin)
old = list(ProblemPart.objects.filter(problem_id__lt=53709).values('problem_id','statement'))
ob={}
for p in old: ob.setdefault(p['problem_id'],[]).append(p)
ost = dict(Problem.objects.filter(id__in=ob).values_list('id','statement'))
oin = sum(1 for pid,ps in ob.items() if any(ws(p['statement'])[:60] in ws(ost[pid]) for p in ps if ws(p['statement'])))
oall = sum(1 for pid,ps in ob.items() if (r:=[ws(p['statement'])[:60] in ws(ost[pid]) for p in ps if ws(p['statement'])]) and all(r))
print('old problems with parts', len(ob), 'any inside', oin, 'all inside', oall)
