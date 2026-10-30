import re
from problems.models import ProblemPart
from olympiads import bank_match as bm
from olympiads.package_clean import strip_balls
ws = lambda s: re.sub(r'\s+', '', s or '')
parts = list(ProblemPart.objects.filter(problem__id__range=(53709,61361)).order_by('problem_id','order','id').values('id','problem_id','label','statement','points','order'))
by = {}
for p in parts: by.setdefault(p['problem_id'], []).append(p)
for name, f in [('ws', ws), ('ws-balls', lambda s: ws(strip_balls(s))), ('norm', bm.norm), ('norm-balls', lambda s: bm.norm(strip_balls(s))), ('textonly', lambda s: ws(s)), ]:
    n=sum(1 for ps in by.values() if len({(p['label'],f(p['statement'])) for p in ps})<len(ps))
    print(name, n)
print('text only (no label)', sum(1 for ps in by.values() if len({ws(p['statement']) for p in ps if ws(p['statement'])})<len([p for p in ps if ws(p['statement'])])))
print('label strip lower', sum(1 for ps in by.values() if len({(p['label'].strip().lower().strip(').'),ws(p['statement'])) for p in ps})<len(ps)))
