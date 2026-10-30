from collections import Counter
from olympiads.management.commands.dedupe_problem_parts import load_parts
from olympiads import parts_fix as pf
from olympiads.bank_fix import editable_ids
bp = load_parts(editable_ids()); c=Counter(); shown=0
for pid, parts in bp.items():
    remove, reasons = pf.dedupe_plan(parts)
    left=[p for p in parts if p['id'] not in remove]
    if not pf.has_repeated_text(left): continue
    groups={}
    for p in parts: groups.setdefault(p['label'],[]).append(p)
    kinds=set()
    for lab,g in groups.items():
        if len(g)<2: continue
        ss=[pf.squeeze(p['statement']) for p in g]
        if len(set(ss))==1:
            kinds.add('same-text-diff-'+('points' if len({p['points'] for p in g})>1 else 'ans/sol'))
        elif len(set(ss))<len(ss): kinds.add('mixed')
    c[tuple(sorted(kinds))]+=1
    if shown<4 and kinds:
        shown+=1; print(pid, [(p['label'], p['statement'][:30], p['points'], p['answer'][:20], p['solution'][:20]) for p in parts][:8])
print(c)
