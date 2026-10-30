import re, random
from collections import Counter
from problems.models import Problem
from olympiads.bank_fix import editable_ids
from olympiads.management.commands.dedupe_problem_parts import load_parts
from olympiads import parts_fix as pf
ed=editable_ids(); bp=load_parts(ed)
st=dict(Problem.objects.filter(id__in=list(bp)).values_list('id','statement'))
c=Counter(); samples={}
for pid, parts in bp.items():
    after, reason = pf.split_plan(st[pid], parts)
    if reason != pf.REASON_SPLIT_MISMATCH: continue
    s=st[pid]; pats=[pf._label_pattern(p['label']) for p in parts]
    starts=list(re.finditer(r'(?m)^'+pats[0], s)) if pats[0] else []
    if not starts: kind='no label start'
    else:
        # how far do we get
        pos=starts[-1].start(); kind=None
        for i,(p,pat) in enumerate(zip(parts,pats)):
            m=re.compile(r'\s*'+pat).match(s,pos)
            if not m: kind='label %s missing'%('first' if i==0 else 'next'); break
            pos=m.end()
            t=re.compile(r'\s*'+pf._loose(p['statement'])).match(s,pos)
            if not t:
                nxt=pf.squeeze(s[pos:pos+300]); ps=pf.squeeze(p['statement'])
                k=0
                while k<min(len(nxt),len(ps)) and nxt[k]==ps[k]: k+=1
                if k==len(ps): kind='?'
                elif k>=len(ps)-3: kind='part text shorter by tail chars: '+repr(nxt[k:k+3])
                elif 'отмечено' in nxt[k:k+15] or 'отмечено' in ps[k:k+15]: kind='отмечено differs'
                else: kind='text differs'
                break
            pos=t.end()
        else:
            kind='extra after last part'
    key=kind if not kind.startswith('part text shorter') else 'part text shorter: '+kind.split(': ')[1]
    c[key]+=1; samples.setdefault(key,[]).append(pid)
for k,v in c.most_common(25): print(v, k, samples[k][:4])
