import re
from problems.models import Problem
from olympiads.bank_fix import editable_ids
from olympiads.management.commands.dedupe_problem_parts import load_parts
from olympiads import parts_fix as pf
ed=editable_ids(); bp=load_parts(ed)
st=dict(Problem.objects.filter(id__in=list(bp)).values_list('id','statement'))
orig=pf._loose
pf._loose=lambda t: orig(t)+r'[;.,]?'
n=sum(1 for pid,parts in bp.items() if pf.split_plan(st[pid],parts)[0] is not None)
pf._loose=orig
m=sum(1 for pid,parts in bp.items() if pf.split_plan(st[pid],parts)[0] is not None)
print('strict', m, 'with trailing ;., tolerated', n)
