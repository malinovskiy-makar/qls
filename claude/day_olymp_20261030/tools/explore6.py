import os, re
from collections import defaultdict, Counter
from olympiads import navigator as nav
vs = nav.base_variants().filter(olympiad__slug='vseros').select_related('stage')
groups = defaultdict(list)
for v in vs:
    g = tuple(sorted(v.grades.values_list('grade', flat=True)))
    groups[(v.stage_id, v.season, g)].append(v)
t = lambda s: re.sub(r'\W+', '', (s or '').lower())
base = lambda p: os.path.basename(p).split('_',1)[0]
c = Counter()
for key, kits in sorted(groups.items(), key=lambda kv: kv[0][1]):
    tours = {v.tour: v for v in kits}
    if not {'1','2'} <= set(tours): continue
    a, b = tours['1'], tours['2']
    ia = {i.number: i for i in a.items.select_related('problem')}; ib = {i.number: i for i in b.items.select_related('problem')}
    fa = Counter(base(f) for i in ia.values() for f in i.pages.get('source_file', []))
    fb = Counter(base(f) for i in ib.values() for f in i.pages.get('source_file', []))
    sharedf = set(fa) & set(fb)
    out=[]
    for n in ia:
        if n not in ib: continue
        x, y = ia[n], ib[n]
        if t(x.problem.title) != t(y.problem.title) or not t(x.problem.title):
            if t(x.problem.title)[:15]==t(y.problem.title)[:15]: out.append(('TITLE~', n, x.problem.title[:30], y.problem.title[:30]))
            continue
        xs = {base(f) for f in x.pages.get('source_file', [])}; ys = {base(f) for f in y.pages.get('source_file', [])}
        xo, yo = xs <= sharedf, ys <= sharedf
        sa, sb = x.max_score, y.max_score
        if (sa is None) != (sb is None):
            c['primary']+=1; verdict = 'excl-1' if sa is None else 'excl-2'
            if (sa is None) != xo or (sb is None) != yo: c['primary-disagrees-with-files']+=1; verdict+='!'
        elif xo != yo:
            c['secondary']+=1; verdict = 'excl-1(f)' if xo else 'excl-2(f)'
        else:
            c['question']+=1; verdict='?'
        out.append((n, verdict, sa, sb, x.problem.title[:25]))
    if out: print(key[1], key[2], a.pk, b.pk, len(ia), len(ib), out)
print(c)
