"""Заголовки-обрубки → заголовок-кандидат (правило владельца 17.09.2026).

`title` заменяется на `title_candidate` только там, где старый заголовок —
обрубок (`problems.enrich.title_rules.stub_flags`), кандидат есть и
отличается. Нормальные заголовки не трогаются, даже если кандидат другой.
Старый заголовок остаётся в снимке: отдельного поля «прежний заголовок» в
модели нет. Отпечаток вектора берёт `title_candidate`, поэтому векторы
замена не сдвигает.

    manage.py titles_from_candidates            # сухой прогон (по умолчанию)
    manage.py titles_from_candidates --apply
    manage.py titles_from_candidates --revert reports/bank_edits/titles_from_candidates/snapshot_<время>.json
"""
import random
from collections import Counter

from problems import bank_sync
from problems.enrich.title_rules import stub_flags
from problems.models import Problem

from ._bank_edit import BankEditCommand

SAMPLE = 100
SEED = 17


class Command(BankEditCommand):
    help = 'Заменить заголовки-обрубки кандидатами (сухой прогон по умолчанию).'

    def build(self, options):
        from catalog.filters import base_queryset
        visible = set(base_queryset('catalog').values_list('id', flat=True))
        result = bank_sync.empty_plan()
        by_flag, rows = Counter(), []
        for pid, title, cand, statement in Problem.objects.values_list(
                'id', 'title', 'title_candidate', 'statement').iterator(chunk_size=2000):
            cand = (cand or '').strip()
            if not cand or cand == (title or '').strip():
                continue
            flags = stub_flags(title, statement)
            if not flags:
                continue
            by_flag.update(flags)
            result['problems'].append({'id': pid, 'old': {'title': title}, 'new': {'title': cand}})
            rows.append((pid, pid in visible, ','.join(flags), title, cand))
        header = ['- Обрубков с другим кандидатом: %d (видимых в каталоге: %d)'
                  % (len(rows), sum(1 for r in rows if r[1])),
                  '- По признакам (задача может нести несколько): %s'
                  % ', '.join('%s %d' % kv for kv in sorted(by_flag.items()))]
        sample = random.Random(SEED).sample(rows, min(SAMPLE, len(rows)))
        extra = ['## %d случайных пар «старый → новый»' % len(sample), '',
                 '| id | виден | признаки | старый | новый |', '|---|---|---|---|---|']
        extra += ['| %d | %s | %s | %s | %s |' % (pid, '✓' if vis else '', flags,
                                                   bank_sync.short(old, 80), bank_sync.short(new, 80))
                  for pid, vis, flags, old, new in sorted(sample)]
        return result, header, extra
