# -*- coding: utf-8 -*-
"""Фаза 5: итоговый вид базы — что видит ученик и как разложены 31 694 задачи."""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db.models import Count, Q
from problems.models import Problem, Source

tot = Problem.objects.count()
visible = Problem.objects.filter(status='published', needs_quality_review=False,
                                 hidden_pending_review=False)
print("=== ЧТО ВИДИТ УЧЕНИК ===")
print(f"  всего задач в базе                     {tot}")
print(f"  ДОСТУПНО В КАТАЛОГЕ                    {visible.count()}")
print(f"  скрыто «человек не смотрел»            {Problem.objects.filter(hidden_pending_review=True).count()}")
print(f"  скрыто иначе (статус/шлюз качества)    "
      f"{Problem.objects.filter(hidden_pending_review=False).exclude(status='published', needs_quality_review=False).count()}")
print()
print("  расклад скрытого, по причинам (причины пересекаются):")
print(f"    status != published                  {Problem.objects.exclude(status='published').count()}")
print(f"    needs_quality_review                 {Problem.objects.filter(needs_quality_review=True).count()}")
print(f"    hidden_pending_review                {Problem.objects.filter(hidden_pending_review=True).count()}")
print()
print("  из видимых, по вердикту человека:")
for v, label in (('approved', 'одобрено'), ('defect', 'брак'), ('', 'не смотрели')):
    print(f"    {label:<36} {visible.filter(human_review=v).count()}")

print("\n=== ВСЕ 31 694 ПО СОСТОЯНИЯМ ===")
for v, label in (('approved', 'одобрено человеком'), ('defect', 'человек нашёл брак'), ('', 'не смотрел никто')):
    n = Problem.objects.filter(human_review=v).count()
    print(f"  {label:<24} {n:>7}   ({100*n/tot:.1f} %)")

print("\n=== ПО ИСТОЧНИКАМ ===")
print(f"  {'источник':<44}{'всего':>7}{'одобр':>7}{'брак':>7}{'не смотр':>9}{'в кат.':>8}")
rows = []
for s in Source.objects.all().order_by('id'):
    ids = Problem.objects.filter(source_references__source=s).values_list('id', flat=True).distinct()
    n = ids.count()
    if not n:
        continue
    base = Problem.objects.filter(id__in=list(ids))
    rows.append((s.id, s.name, n,
                 base.filter(human_review='approved').count(),
                 base.filter(human_review='defect').count(),
                 base.filter(human_review='').count(),
                 base.filter(status='published', needs_quality_review=False,
                             hidden_pending_review=False).count()))
rows.sort(key=lambda r: -r[2])
for sid, name, n, a, d, e, vis in rows:
    print(f"  {(name[:40] + f' [{sid}]'):<44}{n:>7}{a:>7}{d:>7}{e:>9}{vis:>8}")
noref = Problem.objects.filter(source_references__isnull=True).count()
print(f"  {'(без ссылки на источник)':<44}{noref:>7}")
print(f"\n  сумма по источникам: {sum(r[2] for r in rows)} (задача может быть в нескольких источниках)")
print(f"  одобренных суммарно: {sum(r[3] for r in rows)}, видно в каталоге суммарно: {sum(r[6] for r in rows)}")
