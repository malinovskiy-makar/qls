# -*- coding: utf-8 -*-
"""Криминалистика прошлого автосхлопывания 08.06.2026. Только чтение."""
import os
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from django.db.models import Count  # noqa: E402
from problems.models import DuplicateCandidate, Problem  # noqa: E402

OUT = pathlib.Path('reports/dedup_recon_20260911')
lines = []


def p(s=''):
    lines.append(str(s))


def src(pr):
    ref = pr.source_references.select_related('source').first()
    return ref.source.name if ref else '(без источника)'


p('# Фаза 0.2/0.3 — криминалистика прогона process_duplicates 08.06.2026')
p()
pairs = DuplicateCandidate.objects.all()
a_ids = set(pairs.values_list('problem_a_id', flat=True))
b_ids = set(pairs.values_list('problem_b_id', flat=True))
p('пар всего: %d' % pairs.count())
p('различных problem_a: %d' % len(a_ids))
p('различных problem_b: %d' % len(b_ids))
p('задач, побывавших и A, и B: %d' % len(a_ids & b_ids))
p()

# Группы А и Б по порогам самой команды
ga = set(pairs.filter(similarity__gte=0.97).values_list('problem_b_id', flat=True))
gb = set(pairs.filter(similarity__gte=0.95, similarity__lt=0.97)
         .values_list('problem_b_id', flat=True))
p('problem_b в парах >=0.97 (группа А, ставит status=duplicate): %d' % len(ga))
p('problem_b в парах 0.95-0.97 (группа Б, ставит hidden+duplicate_of): %d' % len(gb))
p('пересечение А и Б: %d' % len(ga & gb))
p()

dup_status = set(Problem.objects.filter(status='duplicate').values_list('id', flat=True))
dup_of = set(Problem.objects.exclude(duplicate_of=None).values_list('id', flat=True))
p("status='duplicate': %d" % len(dup_status))
p('duplicate_of не пуст: %d' % len(dup_of))
p()
p('РАСХОЖДЕНИЯ:')
p("  status='duplicate', но НЕ является problem_b ни в одной паре: %d"
  % len(dup_status - b_ids))
p("  problem_b группы А, но status НЕ 'duplicate': %d" % len(ga - dup_status))
p('  duplicate_of не пуст, но НЕ problem_b ни в одной паре: %d' % len(dup_of - b_ids))
p('  problem_b группы Б, но duplicate_of пуст: %d' % len(gb - dup_of))
p("  задачи с duplicate_of И status='duplicate' одновременно: %d"
  % len(dup_of & dup_status))
p()

p('## Задело ли прошлое схлопывание эталон (human_review=approved)')
p()
for label, ids in (("status='duplicate'", dup_status),
                   ('duplicate_of не пуст', dup_of),
                   ('problem_b любой пары', b_ids)):
    qs = Problem.objects.filter(id__in=ids)
    ap = qs.filter(human_review='approved').count()
    de = qs.filter(human_review='defect').count()
    p('%-26s всего %6d | approved %5d | defect %5d' % (label, qs.count(), ap, de))
p()
p('Статусы задач, побывавших problem_b:')
for r in (Problem.objects.filter(id__in=b_ids).values('status')
          .annotate(n=Count('id')).order_by('-n')):
    p('  %-12s %d' % (r['status'], r['n']))
p()
p('Источники задач со status=duplicate (топ-15):')
for r in (Problem.objects.filter(status='duplicate')
          .values('source_references__source__name')
          .annotate(n=Count('id', distinct=True)).order_by('-n')[:15]):
    p('  %-45s %d' % (r['source_references__source__name'] or '(нет)', r['n']))

# ─── Выборки по 30 ──────────────────────────────────────────────────────
random.seed(20260911)
p()
p('## 30 случайных confirmed-пар: источник и human_review обеих сторон')
p()
all_pair_ids = list(pairs.values_list('id', flat=True))
sample_pairs = random.sample(all_pair_ids, min(30, len(all_pair_ids)))
p('%-7s %-6s %-6s %-8s %-30s %-10s | %-30s %-10s' %
  ('pair', 'A', 'B', 'sim', 'источник A', 'review A', 'источник B', 'review B'))
for dc in (DuplicateCandidate.objects.filter(id__in=sample_pairs)
           .select_related('problem_a', 'problem_b')):
    a, b = dc.problem_a, dc.problem_b
    p('%-7d %-6d %-6d %-8.4f %-30.30s %-10s | %-30.30s %-10s' % (
        dc.id, a.id, b.id, dc.similarity, src(a), a.human_review or '-',
        src(b), b.human_review or '-'))

p()
p("## 30 случайных задач со status='duplicate'")
p()
ids = random.sample(sorted(dup_status), min(30, len(dup_status)))
p('%-7s %-40s %-10s %-8s %s' % ('id', 'источник', 'review', 'dup_of', 'dup_group'))
for pr in Problem.objects.filter(id__in=ids):
    p('%-7d %-40.40s %-10s %-8s %s' % (
        pr.id, src(pr), pr.human_review or '-', pr.duplicate_of_id or '-',
        pr.dup_group or '-'))

path = OUT / 'phase0_forensics.md'
path.write_text('\n'.join(lines), encoding='utf-8')
print('written: %s' % path)
