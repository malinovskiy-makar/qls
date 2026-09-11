# -*- coding: utf-8 -*-
"""Разведка перед дедупом корпуса: схема, дедуп-инфраструктура, векторы, источники.

Только чтение. В базу не пишет ничего.
"""
import os
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from django.db.models import Avg, Count, Max, Min, Q  # noqa: E402
from problems.embedding_config import (  # noqa: E402
    ACTIVE_SPEC, ACTIVE_SPEC_NAME, EMBEDDING_MODEL_BUILD,
)
from problems.models import DuplicateCandidate, Problem  # noqa: E402

OUT = pathlib.Path('reports/dedup_recon_20260911')
OUT.mkdir(parents=True, exist_ok=True)
lines = []


def p(s=''):
    lines.append(str(s))


# ─── Фаза -1.5 — поля модели ────────────────────────────────────────────
p('# Фаза -1.5 — поля модели Problem')
p()
names = sorted(f.name for f in Problem._meta.get_fields())
p('Всего полей и связей: %d' % len(names))
p()
for name in names:
    f = Problem._meta.get_field(name)
    rel = ' -> %s' % f.related_model.__name__ if getattr(f, 'related_model', None) else ''
    p('  %-28s %-26s%s' % (name, f.__class__.__name__, rel))

# ─── Фаза -1.6 — объём и источники ──────────────────────────────────────
p()
p('# Фаза -1.6 — объём банка')
p()
total = Problem.objects.count()
p('Problem.objects.count() = %d' % total)
p('без единой привязки к источнику: %d'
  % Problem.objects.filter(source_references__isnull=True).count())
p('привязок SourceReference всего: %d'
  % Problem.objects.filter(source_references__isnull=False).count())

# ─── Фаза 0.1 — DuplicateCandidate ──────────────────────────────────────
p()
p('# Фаза 0.1 — DuplicateCandidate')
p()
p('поля: %s' % ', '.join(sorted(f.name for f in DuplicateCandidate._meta.get_fields())))
dq = DuplicateCandidate.objects.all()
p('всего строк: %d' % dq.count())
for r in dq.values('status').annotate(n=Count('id')).order_by('-n'):
    p('  status=%-12s %d' % (r['status'], r['n']))
agg = dq.aggregate(smin=Min('similarity'), smax=Max('similarity'), savg=Avg('similarity'),
                   cmin=Min('created_at'), cmax=Max('created_at'))
p('similarity: min=%s max=%s avg=%s' % (agg['smin'], agg['smax'], agg['savg']))
p('created_at: min=%s max=%s' % (agg['cmin'], agg['cmax']))

# ─── Фаза 0.2 — следы схлопываний ───────────────────────────────────────
p()
p('# Фаза 0.2 — следы прошлых схлопываний')
p()
p("Problem.status='duplicate':      %d" % Problem.objects.filter(status='duplicate').count())
p('Problem.duplicate_of не пуст:    %d' % Problem.objects.exclude(duplicate_of=None).count())
p('Problem.dup_group не пуст:       %d' % Problem.objects.exclude(dup_group='').count())
p('Problem.dup_is_best=True:        %d' % Problem.objects.filter(dup_is_best=True).count())
p('различных dup_group:             %d'
  % Problem.objects.exclude(dup_group='').values('dup_group').distinct().count())
p()
p('dup_best_rule (каким признаком выиграл фаворит):')
for r in (Problem.objects.filter(dup_is_best=True).values('dup_best_rule')
          .annotate(n=Count('id')).order_by('dup_best_rule')):
    p('  правило %-6s %d' % (r['dup_best_rule'], r['n']))
p()
p('Разбивка Problem.status:')
for r in Problem.objects.values('status').annotate(n=Count('id')).order_by('-n'):
    p('  %-14s %d' % (r['status'], r['n']))
p()
p('human_review:')
for r in Problem.objects.values('human_review').annotate(n=Count('id')).order_by('-n'):
    p('  %-14s %d' % (r['human_review'] or '(пусто)', r['n']))
p()
p('hidden_pending_review:')
for r in Problem.objects.values('hidden_pending_review').annotate(n=Count('id')).order_by('-n'):
    p('  %-14s %d' % (r['hidden_pending_review'], r['n']))
p()
p('content_status:')
for r in Problem.objects.values('content_status').annotate(n=Count('id')).order_by('-n'):
    p('  %-14s %d' % (r['content_status'] or '(пусто)', r['n']))

# ─── Фаза 1 — эмбеддинги ────────────────────────────────────────────────
p()
p('# Фаза 1 — эмбеддинги: покрытие и актуальность')
p()
p('ACTIVE_SPEC_NAME      = %s' % ACTIVE_SPEC_NAME)
p('ACTIVE_SPEC.version   = %s' % ACTIVE_SPEC.version)
p('EMBEDDING_MODEL_BUILD = %s' % EMBEDDING_MODEL_BUILD)
p()
null_emb = Problem.objects.filter(embedding__isnull=True).count()
p('embedding IS NULL:     %d' % null_emb)
has_emb = Problem.objects.filter(embedding__isnull=False)
p('embedding не пуст:     %d' % has_emb.count())
p()
p('embedding_version среди тех, у кого вектор есть:')
for r in has_emb.values('embedding_version').annotate(n=Count('id')).order_by('embedding_version'):
    p('  version=%-8s %d' % (r['embedding_version'], r['n']))
p()
p('embedding_model_build:')
for r in has_emb.values('embedding_model_build').annotate(n=Count('id')).order_by('-n'):
    p('  %-20s %d' % (r['embedding_model_build'] or '(пусто)', r['n']))
p()
match = has_emb.filter(embedding_version=ACTIVE_SPEC.version,
                       embedding_model_build=EMBEDDING_MODEL_BUILD).count()
p('СОВПАДАЮТ с активным спеком (version+build): %d (%.1f %% банка)'
  % (match, 100.0 * match / total))
p('НЕ совпадают (включая пустые поля и NULL-вектор): %d (%.1f %% банка)'
  % (total - match, 100.0 * (total - match) / total))
p()
p('embedding_source_hash пуст среди имеющих вектор: %d'
  % has_emb.filter(Q(embedding_source_hash='') | Q(embedding_source_hash=None)).count())

# ─── Фаза 4.1 — точные content_hash ─────────────────────────────────────
p()
p('# Фаза 4.1 — точные совпадения content_hash')
p()
dups = (Problem.objects.exclude(content_hash='')
        .values('content_hash').annotate(n=Count('id')).filter(n__gt=1))
sizes = Counter()
groups = 0
in_groups = 0
for r in dups:
    groups += 1
    in_groups += r['n']
    sizes[r['n']] += 1
p('задач с непустым content_hash: %d' % Problem.objects.exclude(content_hash='').count())
p('задач с ПУСТЫМ content_hash:   %d' % Problem.objects.filter(content_hash='').count())
p('групп точного совпадения:      %d' % groups)
p('задач в этих группах:          %d' % in_groups)
p('лишних сверх одной на группу:  %d' % (in_groups - groups))
p('распределение размеров групп:  %s' % dict(sorted(sizes.items())))

path = OUT / 'phase0_raw.md'
path.write_text('\n'.join(lines), encoding='utf-8')
print('written: %s (%d строк)' % (path, len(lines)))
