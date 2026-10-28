# -*- coding: utf-8 -*-
"""Выборочная приёмка олимпиады: выборка, пакеты, отчёт (решение 28.10.2026).

Выборка — `n` видимых на сайте задач олимпиады, равномерно по (году, этапу):
задачи раскладываются по слоям, внутри слоя перемешиваются генератором с
`seed`, затем берутся по кругу — по одной из каждого слоя, пока не наберётся
`n`. Тот же `seed` — та же выборка. Рецензенты получают чередующиеся задачи
выборки (1-я, 3-я, … — первому; 2-я, 4-я, … — второму): у каждого все слои.

Отчёт — доля задач с дефектом на 100 с 95 % интервалом Уилсона; вердикт
«можно открывать», если просмотрено не меньше `n` задач и задач с дефектом
меньше порога (3 на 100). Задачи с дефектами уходят людям в очередь
(`queues\\acceptance_defects.jsonl`, общий формат).
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from problems.olympiad_review import common


def wilson(k, n, z=1.96):
    """95 % интервал Уилсона для доли k/n → (низ, верх); n = 0 → (0, 1)."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def verdict(k, n, need=100, threshold=common.ACCEPTANCE_THRESHOLD):
    if n < need:
        return f'мало данных ({n} из {need})'
    return 'можно открывать' if k / n < threshold else 'нельзя открывать'


def stratified_sample(strata, n, seed):
    """{слой: [id]} → n id: перемешать внутри слоя (seed), брать по кругу по слоям."""
    rng = random.Random(seed)
    pools = []
    for key in sorted(strata, key=str):
        ids = sorted(set(strata[key]))
        rng.shuffle(ids)
        pools.append(ids)
    out = []
    while len(out) < n and any(pools):
        for pool in pools:
            if pool and len(out) < n:
                out.append(pool.pop(0))
    return out


def olympiad_refs(slug):
    """Строки OlympiadRef олимпиады. Предпринимательство МОШ пишется под mosh-fingram
    (решение 14.10) — различаем по event_id."""
    from problems.models import OlympiadRef
    entr = registry_prefix('mosh-entrepreneurship')
    if slug == 'mosh-entrepreneurship':
        return OlympiadRef.objects.filter(olympiad_slug__in=('mosh-fingram', slug),
                                          event_id__startswith=entr)
    qs = OlympiadRef.objects.filter(olympiad_slug=slug)
    if slug == 'mosh-fingram':
        qs = qs.exclude(event_id__startswith=entr)
    return qs


def registry_prefix(slug):
    from problems.olympiad_audit import registry
    return registry.get(slug).event_prefix


def strata_for(slug, visible):
    """{(год, этап): [id видимых задач]}; у задачи с несколькими строками — первая official."""
    first = {}
    for ref in olympiad_refs(slug).order_by('id').values('problem_id', 'year', 'stage', 'source_site',
                                                         'record_id'):
        pid = ref['problem_id']
        if pid not in visible:
            continue
        if pid not in first or (ref['source_site'] == 'official'
                                and first[pid]['source_site'] != 'official'):
            first[pid] = ref
    strata = defaultdict(list)
    for pid, ref in first.items():
        strata[(ref['year'] or 0, ref['stage'] or '')].append(pid)
    return strata, first


def cards_for(slug, pids, refs, bank, references):
    """Карточки приёмки: задача банка как на сайте + страницы PDF её задания."""
    from problems.models import Problem
    from problems.olympiad_review.sources import Reference
    cards = []
    for pid in pids:
        problem = Problem.objects.get(pk=pid)
        fields, figures = bank.fields(problem)
        ref = refs[pid]
        key = ref['record_id'][len('official:'):] if ref['record_id'].startswith('official:') else None
        pages = []
        if key and slug in common.LATEST_REFERENCE:
            if slug not in references:
                references[slug] = Reference(slug)
            row = references[slug].rows.get(key)
            if row is not None:
                pages = references[slug].page_images(row)
        cards.append({
            'item_id': f'acc:{slug}:{pid}', 'olympiad': slug, 'ref_key': key, 'problem_id': pid,
            'kind': 'acceptance', 'visible': True, 'sources': ['acceptance'],
            'checks': [f'приёмка {slug}: {ref["year"]} {ref["stage"]}'],
            'details': [] if pages else ['Страниц PDF у задачи нет — сверяйте по смыслу.'],
            'items': [f'acc:{slug}:{pid}'], 'page_images': pages, 'current': fields,
            'current_from': 'bank', 'proposed': None,
            'base': {k: common.field_sha(v) for k, v in fields.items()}, 'figures': figures,
            'stratum': [ref['year'], ref['stage']],
        })
    return cards


def report(rows):
    """[(карточка, решение приёмки)] → {олимпиада: сводка} и список задач с дефектами."""
    per = defaultdict(lambda: {'n': 0, 'defective': 0, 'defects': defaultdict(int), 'by': defaultdict(int)})
    bad = []
    seen = set()
    for card, dec in rows:
        key = (card['olympiad'], card['problem_id'])
        if key in seen:
            continue     # одну задачу смотрел один человек; повтор — не новая задача выборки
        seen.add(key)
        s = per[card['olympiad']]
        s['n'] += 1
        s['by'][dec['reviewer']] += 1
        if dec.get('defects'):
            s['defective'] += 1
            for d in dec['defects']:
                s['defects'][d] += 1
            bad.append((card, dec))
    out = {}
    for slug, s in per.items():
        lo, hi = wilson(s['defective'], s['n'])
        out[slug] = {'просмотрено': s['n'], 'с дефектом': s['defective'],
                     'на 100': round(100 * s['defective'] / s['n'], 1) if s['n'] else None,
                     'интервал 95% (Уилсон), на 100': [round(100 * lo, 1), round(100 * hi, 1)],
                     'вердикт': verdict(s['defective'], s['n']),
                     'дефекты': dict(s['defects']), 'рецензенты': dict(s['by'])}
    return out, bad


def defect_items(bad):
    """Задачи с дефектами приёмки → позиции очереди людям (общий формат)."""
    items = []
    for card, dec in bad:
        names = ', '.join(common.ACCEPTANCE_DEFECTS[d] for d in dec['defects'])
        items.append({'item_id': f'acceptance:{card["olympiad"]}:{card["problem_id"]}:{dec["reviewer"]}',
                      'source': 'acceptance', 'olympiad': card['olympiad'], 'ref_key': card.get('ref_key'),
                      'problem_id': card['problem_id'], 'check': f'приёмка: {names}',
                      'details': f'{dec["reviewer"]}: {names}. {dec.get("comment") or ""}'.strip(),
                      'page_images': card.get('page_images') or [], 'current': card.get('current'),
                      'proposed': None, 'confidence': None})
    return items
