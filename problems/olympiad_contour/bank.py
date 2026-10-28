# -*- coding: utf-8 -*-
"""Карточки стандарта из банка (уровень «а»): Problem, части, рисунки, привязки.

Охват (`scope_ids`): все ВИДИМЫЕ в каталоге задачи с привязкой к ВП, МОШ или
ВсОШ (слаги `OLYMPIAD_SLUGS`, любой источник привязки) плюс список
`next_api_run_ids.txt` ночи 28→29.10 — эти берутся и скрытые.

Связь с эталоном — по официальной привязке: `event_id|number|вариант`
(`raw_meta.official_task_variant`). Через неё карточка банка получает слой
PDF (S3), «есть файл решений» (S8) и пометку P4 «критерии не от этой задачи».
Задачи только SolveHub/ILE без официальной привязки слоя не имеют — S3 для
них пропускается с причиной.
"""
from __future__ import annotations

import io
import os
import re
from urllib.parse import urlsplit

from problems.olympiad_audit.registry import REGISTRY

OLYMPIAD_SLUGS = ('vp', 'vp-fingram', 'vp-ob', 'mosh', 'mosh-fingram', 'vseros')
#: Порядок, в котором выбирается «своя» олимпиада задачи с несколькими привязками.
PRIORITY = ('vp', 'vp-fingram', 'vp-ob', 'mosh', 'mosh-fingram', 'mosh-entrepreneurship', 'vseros')
NEXT_API_IDS = r'C:\Users\shipu\weconomics-data\night_20261028\next_api_run_ids.txt'

_MARKER = re.compile(r'\[\[FIGURE:([0-9a-f]+)\]\]')


def read_ids(path=NEXT_API_IDS):
    with open(path, encoding='utf-8') as handle:
        return [int(x) for x in handle.read().split() if x.strip().isdigit()]


def scope_ids(next_ids=()):
    """(все id, видимые id, {id: откуда взят}) — охват проверки банка."""
    from catalog.filters import base_queryset
    from problems.models import OlympiadRef

    visible = set(base_queryset('catalog').values_list('pk', flat=True))
    olymp = set(OlympiadRef.objects.filter(olympiad_slug__in=OLYMPIAD_SLUGS)
                .values_list('problem_id', flat=True))
    by_scope = {}
    for pk in olymp & visible:
        by_scope.setdefault(pk, set()).add('visible')
    for pk in next_ids:
        by_scope.setdefault(pk, set()).add('next_api')
    return sorted(by_scope), visible, by_scope


def olympiad_of(ref):
    original = (ref.raw_meta or {}).get('original_olympiad')
    if isinstance(original, dict) and original.get('slug'):
        return original['slug']
    return ref.olympiad_slug


def primary_ref(refs):
    """Своя привязка задачи: официальная раньше агрегатора, затем порядок PRIORITY."""
    def rank(ref):
        slug = olympiad_of(ref)
        return (ref.source_site != 'official',
                PRIORITY.index(slug) if slug in PRIORITY else 99, ref.event_id, ref.pk)
    refs = [r for r in refs if olympiad_of(r) in PRIORITY]
    return min(refs, key=rank) if refs else None


def ref_key_of(ref):
    variant = (ref.raw_meta or {}).get('official_task_variant') or ''
    return '%s|%s|%s' % (ref.event_id, ref.number, variant)


def image_opens_bytes(data):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        return True
    except Exception:  # noqa: BLE001 — любой отказ PIL = картинка не открывается
        return False


def _host_official(url, slug):
    entry = REGISTRY.get(slug) or REGISTRY.get('mosh-fingram' if slug == 'mosh-entrepreneurship' else slug)
    hosts = entry.official_hosts if entry else ()
    host = urlsplit(url).netloc.lower()
    return any(host == h or host.endswith('.' + h) for h in hosts)


def _test_of(problem, parts):
    from catalog import testplay
    from problems import problem_types
    if not testplay.is_test(problem):
        return None
    kind = problem_types.test_kind(problem.problem_type)
    key = (problem.answer or '').strip()
    if kind == problem_types.NUMERIC:
        return {'kind': 'short', 'options': [], 'key': key, 'why': ''}
    options = [{'label': p.label, 'text': p.statement,
                'correct': (p.answer or '').strip().lower() == 'верно'} for p in parts]
    game = testplay.game_of(problem, parts)
    name = {problem_types.MULTI: 'multi', problem_types.BOOLEAN: 'boolean'}.get(kind, 'single')
    if game is None:
        why = 'не собирается в игру'
        from problems import answer_check
        correct = answer_check.catalog_test_correct_labels(problem)
        labels = {answer_check.normalize_label(p.label) for p in parts}
        if not parts:
            why = 'нет вариантов'
        elif len(labels) != len(parts):
            why = 'метки вариантов повторяются'
        elif not correct:
            why = 'ключа нет'
        elif not correct <= labels:
            why = 'верные метки вне вариантов: %s' % ', '.join(sorted(correct - labels))
        elif name == 'single' and len(correct) != 1:
            why = 'один выбор, верных %d' % len(correct)
        return {'kind': 'broken', 'options': options, 'key': key, 'why': why}
    return {'kind': name, 'options': options, 'key': key, 'why': ''}


def card_of(problem, refs, *, visible, ref_cards, rejected, suspect):
    """Задача банка → карточка. `ref_cards` — {ref_key: карточка эталона}."""
    parts = list(problem.parts.all())
    test = _test_of(problem, parts)
    ref = primary_ref(refs)
    slug = olympiad_of(ref) if ref else ''
    official = [r for r in refs if r.source_site == 'official']
    linked = None
    for r in ([ref] if ref and ref.source_site == 'official' else []) + official:
        linked = ref_cards.get(ref_key_of(r))
        if linked:
            break
    texts = [problem.statement or '', problem.solution or '', problem.answer or '']
    for p in parts:
        texts += [p.statement or '', p.answer or '', p.solution or '']
    markers = set(_MARKER.findall('\n'.join(texts)))
    figures, have = [], set()
    for fig in problem.figures.all():
        have.add(fig.tikz_hash)
        name = os.path.basename((fig.tikz_source or '').split(':')[-1]) if fig.tikz_source.startswith(
            'official-pdf:') else 'figure#%d' % fig.pk
        data = bytes(fig.image_data) if fig.image_data else b''
        if data:
            opens = image_opens_bytes(data)
        else:
            opens = (fig.svg or '').lstrip().startswith('<svg')
        figures.append({'name': name, 'pk': fig.pk, 'hash': fig.tikz_hash,
                        'field': 'solution' if fig.source_field == 'solution' else 'statement',
                        'exists': bool(data or fig.svg), 'size': len(data) or len(fig.svg or ''),
                        'opens': opens, 'rejected': rejected.get(name, ''), 'flag': '',
                        'table_ok': False})
    orphans = [f['name'] for f in figures if f['hash'] not in markers]
    max_score = None
    for r in official:
        value = (r.raw_meta or {}).get('max_score')
        if value not in (None, ''):
            try:
                max_score = float(value)
            except (TypeError, ValueError):
                pass
            break
    pdf_url, pdf_official = '', None
    if ref and ref.source_site == 'official' and ref.official_url:
        pdf_url = ref.official_url
    else:
        for sr in problem.source_references.all():
            if sr.url:
                pdf_url = sr.url
                break
        if not pdf_url and ref:
            pdf_url = ref.official_url
    if pdf_url:
        pdf_official = _host_official(pdf_url, slug)
    is_test = bool(test)
    card_parts = [] if is_test else [
        {'label': p.label, 'text': p.statement or '',
         'points': p.points, 'answer': p.answer or ''} for p in parts]
    return {
        'level': 'bank',
        'olympiad': slug,
        'ref_key': ref_key_of(ref) if ref and ref.source_site == 'official' else (
            linked['ref_key'] if linked else None),
        'linked_ref_key': linked['ref_key'] if linked else None,
        'problem_id': problem.pk,
        'event_id': ref.event_id if ref else '',
        'number': ref.number if ref else '',
        'title': problem.title or '',
        'statement': problem.statement or '',
        'solution': problem.solution or '',
        'answer': problem.answer or '',
        'criteria': '',
        'parts': card_parts,
        'test': test,
        'max_score': max_score,
        'figures': figures,
        'figure_markers_missing': sorted(markers - have),
        'figure_orphans': orphans,
        'tables_expected': 0,
        'layer': linked['layer'] if linked else None,
        'numbers_ok': None,
        'meta': {'season': (ref.academic_year or ref.year or '') if ref else '',
                 'stage': ref.stage if ref else '', 'grade': (ref.grade if ref else '') or (
                     'все' if ref and '-all-' in ref.event_id else ''),
                 'number': ref.number if ref else '',
                 'pdf_url': pdf_url, 'pdf_official': pdf_official},
        'reference_suspect': bool(linked and linked.get('reference_suspect')),
        'solution_expected': bool(linked and linked.get('solution_expected')),
        'section': linked.get('section', '') if linked else '',
        'visible': problem.pk in visible,
        'status': problem.status,
        'page_images': linked['page_images'] if linked else [],
        'source_site': ref.source_site if ref else '',
    }


def load_cards(ids, visible, ref_cards, rejected, suspect, chunk=500):
    from problems.models import OlympiadRef, Problem
    cards = []
    for start in range(0, len(ids), chunk):
        part = ids[start:start + chunk]
        refs = {}
        for r in OlympiadRef.objects.filter(problem_id__in=part):
            refs.setdefault(r.problem_id, []).append(r)
        qs = (Problem.objects.filter(pk__in=part)
              .prefetch_related('parts', 'figures', 'source_references'))
        for problem in qs:
            cards.append(card_of(problem, refs.get(problem.pk, []), visible=visible,
                                 ref_cards=ref_cards, rejected=rejected, suspect=suspect))
    cards.sort(key=lambda c: c['problem_id'])
    return cards
