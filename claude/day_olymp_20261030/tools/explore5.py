from collections import defaultdict, Counter
from olympiads import navigator as nav
from olympiads.package_clean import same_text
from olympiads.models import OlympiadVariantItem as I
vs = nav.base_variants().filter(olympiad__slug='vseros').select_related('stage')
groups = defaultdict(list)
for v in vs:
    g = tuple(sorted(v.grades.values_list('grade', flat=True)))
    groups[(v.stage_id, v.season, g)].append(v)
c = Counter(); rows=[]
for key, kits in sorted(groups.items(), key=lambda kv: kv[0][1]):
    tours = {v.tour: v for v in kits}
    if len(kits) < 2: continue
    if not {'1','2'} <= set(tours): c['pairs-not-1-2']+=1; continue
    a, b = tours['1'], tours['2']
    c['pairs'] += 1
    ia = {i.number: i for i in a.items.select_related('problem')}; ib = {i.number: i for i in b.items.select_related('problem')}
    shared = [n for n in ia if n in ib]
    same = [n for n in shared if same_text(ia[n].problem.statement, ib[n].problem.statement)]
    if same: c['pairs-with-shared'] += 1
    for n in same:
        sa, sb = ia[n].max_score, ib[n].max_score
        if (sa is None) != (sb is None): c['foreign'] += 1
        else: c['question'] += 1; rows.append((key[1], key[2], n, sa, sb, a.pk, b.pk))
    if len(shared) != len(same): c['shared-number-diff-text'] += len(shared)-len(same); rows.append(('difftext', key[1], key[2], [n for n in shared if n not in same]))
print(c)
for r in rows: print(r)
