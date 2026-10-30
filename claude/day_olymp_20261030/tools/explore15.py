import re
from collections import Counter
from problems.models import Problem
from problems.answer_check import normalize_label
from olympiads.bank_fix import editable_ids
from olympiads.management.commands.dedupe_problem_parts import load_parts
M=re.compile(r'\(\s*отмечено\s*\)', re.I)
ed=editable_ids()
probs={p['id']:p for p in Problem.objects.filter(id__in=ed).values('id','statement','answer','problem_type')}
bp=load_parts(ed)
c=Counter(); ex={}
for pid,p in probs.items():
    parts=bp.get(pid,[])
    sm=len(M.findall(p['statement'])); pm=[x for x in parts if M.search(x['statement'])]
    if not sm and not pm: continue
    c['total']+=1
    labels=[normalize_label(x['label']) for x in parts]
    opts = len(parts)>=2 and len(set(labels))==len(labels) and all(labels)
    k=('stmt' if sm else '')+('+parts' if pm else '')+(' opts' if opts else ' noopts')
    c[k]+=1; ex.setdefault(k,[]).append(pid)
    if pm and any(len(M.findall(x['statement']))>1 for x in pm): c['part with 2 marks']+=1
    if any(re.match(r'\s*\+', x['statement']) for x in parts): c['plus-start part']+=1
for k,v in sorted(c.items()): print(v,k, ex.get(k,[])[:5])
