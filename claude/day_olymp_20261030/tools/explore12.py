import re
from collections import Counter
from problems.models import Problem, ProblemPart
from olympiads.bank_fix import editable_ids
M=re.compile(r'\(\s*отмечено\s*\)', re.I)
ed=editable_ids()
ps=list(Problem.objects.filter(id__in=ed).values('id','statement','answer','problem_type','solution'))
inst=[p for p in ps if M.search(p['statement'])]
print('S4 with mark in statement', len(inst), 'all S4 incl reviewed', Problem.objects.filter(id__gte=53709, statement__icontains='(отмечено)').count())
parts={}
for x in ProblemPart.objects.filter(problem_id__in=[p['id'] for p in inst]).order_by('order','id').values('problem_id','label','statement','answer'):
    parts.setdefault(x['problem_id'],[]).append(x)
c=Counter()
for p in inst:
    pp=parts.get(p['id'],[])
    c['type='+p['problem_type']]+=1
    c['has parts' if pp else 'no parts']+=1
    if pp: c['mark in parts' if any(M.search(x['statement']) for x in pp) else 'no mark in parts']+=1
    c['answer filled' if p['answer'].strip() else 'answer empty']+=1
    c['marks=%d'%min(len(M.findall(p['statement'])),3)]+=1
    if any(x['answer'].strip() for x in pp): c['part answers filled']+=1
    if M.search(p['solution'] or ''): c['mark in solution']+=1
for k,v in sorted(c.items()): print(k,v)
print('parts-with-mark problems total (S4)', ProblemPart.objects.filter(problem_id__in=ed, statement__icontains='(отмечено)').values('problem_id').distinct().count())
