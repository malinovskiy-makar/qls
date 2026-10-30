import random
from problems.models import Problem
from olympiads.bank_fix import editable_ids
from olympiads.management.commands.dedupe_problem_parts import load_parts
from olympiads import parts_fix as pf
ed=editable_ids(); bp=load_parts(ed)
st=dict(Problem.objects.filter(id__in=list(bp)).values_list('id','statement'))
random.seed(3)
ids=[pid for pid in bp if pf.squeeze(bp[pid][0]['statement'])[:40] in pf.squeeze(st[pid])]
print(len(ids))
for pid in random.sample(ids, 8):
    s=st[pid]; first=bp[pid][0]
    k=s.find(first['statement'][:25])
    print('=====', pid, [p['label'] for p in bp[pid]], [str(p['points']) for p in bp[pid]])
    print('TAIL:', repr(s[max(0,k-40):k+300]))
    print('PART0:', repr(first['statement'][:120]))
    print('LASTPART:', repr(bp[pid][-1]['statement'][-80:]), '| STMT END:', repr(s[-80:]))
