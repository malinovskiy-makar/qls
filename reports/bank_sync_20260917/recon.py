"""Разведка Фазы 1 — ТОЛЬКО ЧТЕНИЕ. Таксономия, заголовки, подпункты,
источники, токены в условиях; ключи справочников для синхронизации.

Один запуск — одна база, итог в recon_<label>.json. `--render` сводит оба
файла (и заметки по коду из recon_notes.md, если есть) в RECON.md.

    venv313/Scripts/python.exe reports/bank_sync_20260917/recon.py --label home
    DATABASE_URL=postgres://qls:qls_dev_password@127.0.0.1:55432/weco_prod_copy \
      venv313/Scripts/python.exe reports/bank_sync_20260917/recon.py --label prod \
      --settings config.settings_test_pg
    venv313/Scripts/python.exe reports/bank_sync_20260917/recon.py --render
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 17

# ── Эвристика «обрубок» (формулировка владельца) ─────────────────────────
RX_TASK_N = re.compile(r'(?i)\b(задача|задание|вопрос|question|problem|task|'
                       r'упражнение|exercise)\s*№?\s*\d+[а-яa-z]?\s*\.?$')
RX_ABBR_YEAR = re.compile(r'^[A-ZА-ЯЁ]{2,6}\b.*\b(19|20)\d{2}\b')
RX_ABBR_STAGE = re.compile(r'^[A-ZА-ЯЁ]{2,6}\s+(?i:отбор|финал|регион\w*|'
                           r'муниципал\w*|заключ\w*|олимп\w*)')
RX_ONLY_DIGITS = re.compile(r'^[\d\W_]+$')

# Ссылки на цифровые пункты в ответе/решении.
RX_REF_PAREN = re.compile(r'(?<![\w.,])[1-9]\)')
RX_REF_DOT = re.compile(r'(?m)^\s*[1-9]\.\s')
RX_REF_WORD = re.compile(r'(?i)\bпункт\w*\s*[1-9]\b')

RX_TOKEN = re.compile(r'\[\[([A-Z_]+):')


def norm(s):
    return re.sub(r'\s+', ' ', s or '').strip().lower()


def title_flags(title, statement):
    """Категории «обрубка» для одного заголовка; пустой заголовок — вне счёта."""
    raw = (title or '').strip()
    t = norm(raw).rstrip('.… ')
    s = norm(statement)
    k = min(40, len(t))
    flags = []
    if k and s[:k] == t[:k]:
        flags.append('start')
    if len(raw.split()) <= 2:
        flags.append('short')
    if raw.endswith('…') or raw.endswith('...'):
        flags.append('ellipsis')
    if RX_TASK_N.search(raw) or RX_ABBR_YEAR.search(raw) or RX_ABBR_STAGE.search(raw):
        flags.append('code')
    if RX_ONLY_DIGITS.match(raw):
        flags.append('digits')
    return flags


def label_class(label):
    x = (label or '').strip().strip('().').lower()
    if re.fullmatch(r'\d+', x):
        return 'digit'
    if re.fullmatch(r'[а-яё]', x):
        return 'cyr'
    if re.fullmatch(r'[a-z]', x):
        return 'lat'
    return 'other'


def collect(label):
    from django.db import connection
    from problems import problem_types
    from problems.models import (EconConcept, Feature, Problem, ProblemPart,
                                 Source, SourceReference, Tag, Topic)
    from catalog.filters import base_queryset
    from catalog.preview import looks_like_statement_cut
    from catalog.topic_blocks import is_known

    out = {'label': label, 'vendor': connection.vendor}
    visible = set(base_queryset('catalog').values_list('id', flat=True))
    all_ids = set(Problem.objects.values_list('id', flat=True))
    out['problems'] = {'all': len(all_ids), 'visible': len(visible)}

    # ── 1. Таксономия ────────────────────────────────────────────────────
    topics = {t.id: t for t in Topic.objects.all()}
    p_topics = defaultdict(set)
    for pid, tid in Problem.topics.through.objects.values_list('problem_id', 'topic_id'):
        p_topics[pid].add(tid)

    def topic_share(ids):
        canon = sum(1 for p in ids if any(topics[t].is_canonical for t in p_topics.get(p, ())))
        noncanon = sum(1 for p in ids if any(not topics[t].is_canonical for t in p_topics.get(p, ())))
        only_non = sum(1 for p in ids if p_topics.get(p) and
                       not any(topics[t].is_canonical for t in p_topics[p]))
        none = sum(1 for p in ids if not p_topics.get(p))
        return {'with_canonical': canon, 'with_noncanonical': noncanon,
                'only_noncanonical': only_non, 'no_topic': none}

    vis_topic_n = Counter(t for p in visible for t in p_topics.get(p, ()))
    filter_topics = sorted(
        ({'id': t, 'name': topics[t].name, 'is_canonical': topics[t].is_canonical,
          'visible': n} for t, n in vis_topic_n.items() if is_known(topics[t].name)),
        key=lambda r: (not r['is_canonical'], r['name']))
    out['topics'] = {
        'total': len(topics),
        'canonical': sum(1 for t in topics.values() if t.is_canonical),
        'canonical_names': sorted(t.name for t in topics.values() if t.is_canonical),
        'all': topic_share(all_ids), 'visible': topic_share(visible),
        'filter_known': filter_topics,
        'visible_linked_distinct': len(vis_topic_n),
    }

    tags = {t.id: t for t in Tag.objects.all()}
    p_tags = defaultdict(set)
    for pid, tid in Problem.tags.through.objects.values_list('problem_id', 'tag_id'):
        p_tags[pid].add(tid)
    tag_links = Counter(t for ts in p_tags.values() for t in ts)
    tag_links_vis = Counter(t for p in visible for t in p_tags.get(p, ()))

    def tag_share(ids):
        with_tags = [p for p in ids if p_tags.get(p)]
        only_legacy = sum(1 for p in with_tags if all(tags[t].kind == 'legacy' for t in p_tags[p]))
        no_canon = sum(1 for p in with_tags if not any(tags[t].kind == 'canonical' for t in p_tags[p]))
        return {'with_tags': len(with_tags), 'only_legacy': only_legacy,
                'without_canonical': no_canon}

    canon_by_norm = {norm(t.name).replace('ё', 'е'): t for t in tags.values() if t.kind == 'canonical'}
    equal, nested = [], []
    for t in tags.values():
        if t.kind != 'legacy':
            continue
        key = norm(t.name).replace('ё', 'е')
        if not key:
            continue
        if key in canon_by_norm:
            equal.append((t, canon_by_norm[key]))
            continue
        inside = [c for k, c in canon_by_norm.items() if len(key) >= 4 and (key in k or k in key)]
        if inside:
            nested.append((t, inside))

    def pack(pairs, many=False):
        return {
            'legacy_tags': len(pairs),
            'links_all': sum(tag_links[t.id] for t, _ in pairs),
            'links_visible': sum(tag_links_vis[t.id] for t, _ in pairs),
            'examples': [
                {'legacy': t.name, 'links': tag_links[t.id],
                 'canonical': ([c.name for c in cs][:3] if many else cs.name)}
                for t, cs in sorted(pairs, key=lambda x: -tag_links[x[0].id])[:25]],
        }

    out['tags'] = {
        'by_kind': dict(Counter(t.kind for t in tags.values())),
        'by_kind_linked_visible': dict(Counter(tags[t].kind for t in tag_links_vis)),
        'canonical_without_links_all': sum(1 for t in tags.values()
                                           if t.kind == 'canonical' and not tag_links[t.id]),
        'all': tag_share(all_ids), 'visible': tag_share(visible),
        'legacy_equal_canonical': pack(equal),
        'legacy_nested_canonical': pack(nested, many=True),
    }

    # ── 2. Заголовки ─────────────────────────────────────────────────────
    rows = Problem.objects.values_list('id', 'title', 'title_candidate', 'title_source', 'statement')
    cat = Counter()
    cat_vis = Counter()
    combos = Counter()
    stub, keep = [], []
    stats = Counter()
    for pid, title, cand, tsource, statement in rows.iterator(chunk_size=2000):
        stats['title'] += bool((title or '').strip())
        stats['candidate'] += bool((cand or '').strip())
        stats['source:' + (tsource or '-')] += 1
        if pid in visible and (title or '').strip() and looks_like_statement_cut(title, statement):
            stats['visible_hidden_by_catalog_cut'] += 1
        if not (title or '').strip():
            continue
        flags = title_flags(title, statement)
        has_cand = bool((cand or '').strip())
        differs = has_cand and cand.strip() != title.strip()
        for f in flags:
            cat[f] += 1
            cat[f + '+cand'] += has_cand
            if pid in visible:
                cat_vis[f] += 1
                cat_vis[f + '+cand'] += has_cand
        combos['+'.join(flags) or '(нет)'] += 1
        row = {'id': pid, 'title': title, 'candidate': cand, 'source': tsource,
               'visible': pid in visible, 'flags': flags}
        if flags:
            stats['stub'] += 1
            stats['stub+cand'] += has_cand
            stats['stub+cand_differs'] += differs
            stats['stub_visible'] += pid in visible
            stats['stub_visible+cand_differs'] += differs and pid in visible
            if differs:
                stub.append(row)
        elif differs:
            keep.append(row)
    rnd = random.Random(SEED)
    out['titles'] = {
        'stats': dict(stats), 'categories_all': dict(cat), 'categories_visible': dict(cat_vis),
        'combos': dict(combos.most_common(20)),
        'sample_stub': rnd.sample(stub, min(60, len(stub))),
        'sample_keep': rnd.sample(keep, min(20, len(keep))),
    }

    # ── 3. Подпункты ─────────────────────────────────────────────────────
    ptype = dict(Problem.objects.values_list('id', 'problem_type'))
    labels = defaultdict(set)
    for pid, lab in ProblemPart.objects.values_list('problem_id', 'label').iterator(chunk_size=5000):
        labels[pid].add(label_class(lab))
    parts_out = {'parts_total': ProblemPart.objects.count(), 'problems_with_parts': len(labels)}
    for scope, ids in (('all', all_ids), ('visible', visible)):
        c = Counter()
        digit_open = []
        for pid in ids:
            if pid not in labels:
                continue
            kind = 'test' if problem_types.is_test(ptype.get(pid)) else 'open'
            cls = labels[pid]
            key = next(iter(cls)) if len(cls) == 1 else 'mixed'
            c[f'{kind}:{key}'] += 1
            if kind == 'open' and key == 'digit':
                digit_open.append(pid)
        refs = Counter()
        texts = defaultdict(str)
        for pid, a, s in Problem.objects.filter(id__in=digit_open).values_list('id', 'answer', 'solution'):
            texts[pid] += (a or '') + '\n' + (s or '')
        for pid, a, s in ProblemPart.objects.filter(problem_id__in=digit_open).values_list(
                'problem_id', 'answer', 'solution'):
            texts[pid] += '\n' + (a or '') + '\n' + (s or '')
        for pid in digit_open:
            txt = texts.get(pid, '')
            hits = [n for n, rx in (('paren', RX_REF_PAREN), ('dot', RX_REF_DOT), ('word', RX_REF_WORD))
                    if rx.search(txt)]
            refs['any'] += bool(hits)
            for h in hits:
                refs[h] += 1
        parts_out[scope] = {'classes': dict(c), 'open_digit': len(digit_open),
                            'open_digit_refs': dict(refs),
                            'open_digit_sample_ids': sorted(digit_open)[:15]}
    out['parts'] = parts_out

    # ── 4. Источники ─────────────────────────────────────────────────────
    ref_rows = list(SourceReference.objects.values_list('problem_id', 'source_id', 'url'))
    by_src = defaultdict(set)
    by_src_url = defaultdict(set)
    for pid, sid, url in ref_rows:
        by_src[sid].add(pid)
        if (url or '').strip():
            by_src_url[sid].add(pid)
    sources = []
    for s in Source.objects.all().order_by('id'):
        ids = by_src.get(s.id, set())
        sources.append({'id': s.id, 'name': s.name, 'kind': s.kind, 'note': s.note[:80],
                        'problems': len(ids), 'visible': len(ids & visible),
                        'with_url': len(by_src_url.get(s.id, set())),
                        'visible_with_url': len(by_src_url.get(s.id, set()) & visible)})
    lesh = {}
    for s in Source.objects.filter(name__icontains='ЛЭШ'):
        refs = SourceReference.objects.filter(source=s)
        pids = set(refs.values_list('problem_id', flat=True))
        lesh[s.name] = {
            'refs': refs.count(), 'problems': len(pids), 'visible': len(pids & visible),
            'stage': dict(Counter(refs.values_list('stage', flat=True)).most_common(8)),
            'year': dict(Counter(refs.values_list('year', flat=True)).most_common(8)),
            'grade': dict(Counter(refs.values_list('grade', flat=True)).most_common(8)),
            'problem_number_sample': list(refs.values_list('problem_number', flat=True)[:12]),
            'url_nonempty': refs.exclude(url='').count(),
            'url_sample': list(refs.exclude(url='').values_list('url', flat=True)[:3]),
            'note': dict(Counter(refs.values_list('note', flat=True)).most_common(5)),
            'other_sources_on_same_problems': dict(Counter(
                SourceReference.objects.filter(problem_id__in=pids).exclude(source=s)
                .values_list('source__name', flat=True))),
            'olympiad_refs': Problem.objects.filter(id__in=pids, olympiad_refs__isnull=False)
                                            .distinct().count(),
        }
    out['sources'] = {'list': sources, 'lesh': lesh}

    # ── 5. Токены в тексте ───────────────────────────────────────────────
    tok = Counter()
    tok_vis = Counter()
    fig_vis_format = Counter()
    pct_vis = dollar_vis = 0
    for pid, st, sol, fmt in Problem.objects.values_list('id', 'statement', 'solution',
                                                         'content_format').iterator(chunk_size=2000):
        kinds = set(RX_TOKEN.findall(st or '')) | {k + '(решение)' for k in RX_TOKEN.findall(sol or '')}
        for k in kinds:
            tok[k] += 1
            if pid in visible:
                tok_vis[k] += 1
        if pid in visible:
            if '[[FIGURE:' in (st or ''):
                fig_vis_format[fmt or '-'] += 1
            pct_vis += '\\%' in (st or '')
            dollar_vis += '$' in (st or '')
    part_tok = Counter()
    for pid, st in ProblemPart.objects.values_list('problem_id', 'statement').iterator(chunk_size=5000):
        for k in set(RX_TOKEN.findall(st or '')):
            part_tok[k + (' (видимые)' if pid in visible else '')] += 1
    out['tokens'] = {
        'problems_all': dict(tok), 'problems_visible': dict(tok_vis), 'parts': dict(part_tok),
        'visible_figure_statement_by_content_format': dict(fig_vis_format),
        'visible_content_format': dict(Counter(base_queryset('catalog').values_list(
            'content_format', flat=True))),
        'visible_statement_with_backslash_percent': pct_vis,
        'visible_statement_with_dollar': dollar_vis,
    }

    # ── Ключи для синхронизации (сверка id дома и на бою) ────────────────
    out['keys'] = {
        'topic': {t.id: [t.name, t.slug, t.is_canonical] for t in topics.values()},
        'tag': {t.id: [t.name, t.kind] for t in tags.values()},
        'source': {s['id']: s['name'] for s in sources},
        'feature': dict(Feature.objects.values_list('id', 'key')),
        'econ_concept': dict(EconConcept.objects.values_list('id', 'canonical')),
        'problem_statement_sha1': {
            pid: hashlib.sha1((st or '').encode('utf-8')).hexdigest()[:12]
            for pid, st in Problem.objects.values_list('id', 'statement').iterator(chunk_size=2000)},
    }
    return out


# ── Сводка в RECON.md ─────────────────────────────────────────────────────
def md_table(head, rows):
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    lines += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(lines)


def cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def render():
    h = json.loads((HERE / 'recon_home.json').read_text(encoding='utf-8'))
    p = json.loads((HERE / 'recon_prod.json').read_text(encoding='utf-8'))
    o = ['# RECON — Фаза 1, разведка (только чтение)', '',
         f"Дом: `db.sqlite3` ({h['vendor']}). Бой: копия `weco_prod_copy` ({p['vendor']}).", '']

    def pair(title, keys, get):
        return md_table([title, 'дома', 'на копии боя'],
                        [(k, get(h, k), get(p, k)) for k in keys])

    o += ['## 0. Задачи', '', pair('', ['all', 'visible'], lambda d, k: d['problems'][k]), '']

    o += ['## 1. Таксономия', '', '### Темы', '',
          pair('показатель', ['total', 'canonical', 'visible_linked_distinct'],
               lambda d, k: d['topics'][k]), '',
          pair('задачи (весь банк)', list(h['topics']['all']),
               lambda d, k: d['topics']['all'][k]), '',
          pair('задачи (видимый каталог)', list(h['topics']['visible']),
               lambda d, k: d['topics']['visible'][k]), '']
    for d, name in ((h, 'дома'), (p, 'на копии боя')):
        rows = d['topics']['filter_known']
        o += [f"**Темы, которые фильтр показывает {name}: {len(rows)}** "
              f"(канонических {sum(r['is_canonical'] for r in rows)}, "
              f"неканонических {sum(not r['is_canonical'] for r in rows)})", '',
              md_table(['id', 'тема', 'is_canonical', 'видимых задач'],
                       [(r['id'], cell(r['name']), r['is_canonical'], r['visible']) for r in rows]), '']
    o += ['### Теги', '',
          md_table(['вид', 'дома (всего)', 'бой (всего)', 'дома (на видимых)', 'бой (на видимых)'],
                   [(k, h['tags']['by_kind'].get(k, 0), p['tags']['by_kind'].get(k, 0),
                     h['tags']['by_kind_linked_visible'].get(k, 0),
                     p['tags']['by_kind_linked_visible'].get(k, 0))
                    for k in ('canonical', 'legacy', 'author', 'junk')]), '',
          pair('задачи с тегами (весь банк)', list(h['tags']['all']), lambda d, k: d['tags']['all'][k]), '',
          pair('задачи с тегами (видимые)', list(h['tags']['visible']),
               lambda d, k: d['tags']['visible'][k]), '',
          pair('канонические теги без связей', ['canonical_without_links_all'],
               lambda d, k: d['tags'][k]), '']
    for key, title in (('legacy_equal_canonical', 'legacy = канонический (без учёта регистра и ё)'),
                       ('legacy_nested_canonical', 'legacy вложен в канонический или наоборот')):
        o += [f'#### {title}', '',
              pair('', ['legacy_tags', 'links_all', 'links_visible'], lambda d, k: d['tags'][key][k]), '',
              'Примеры (дома, по числу связей):', '',
              md_table(['legacy', 'связей', 'канонический'],
                       [(cell(e['legacy']), e['links'], cell(e['canonical']))
                        for e in h['tags'][key]['examples']]), '']

    t_h, t_p = h['titles'], p['titles']
    o += ['## 2. Заголовки', '',
          pair('показатель', ['title', 'candidate', 'stub', 'stub+cand', 'stub+cand_differs',
                              'stub_visible', 'stub_visible+cand_differs',
                              'visible_hidden_by_catalog_cut'],
               lambda d, k: d['titles']['stats'].get(k, 0)), '',
          md_table(['категория', 'дома', 'дома, есть кандидат', 'дома видимых',
                    'бой', 'бой, есть кандидат', 'бой видимых'],
                   [(c, t_h['categories_all'].get(c, 0), t_h['categories_all'].get(c + '+cand', 0),
                     t_h['categories_visible'].get(c, 0), t_p['categories_all'].get(c, 0),
                     t_p['categories_all'].get(c + '+cand', 0), t_p['categories_visible'].get(c, 0))
                    for c in ('start', 'short', 'ellipsis', 'code', 'digits')]), '',
          'Категории: `start` — совпадает с началом условия (первые 40 знаков после '
          'нормализации); `short` — не больше двух слов; `ellipsis` — «…»/«...» в конце; '
          '`code` — код источника («Задача 21», «Question 189», аббревиатура + год, '
          '«ВП отбор»); `digits` — только цифры и знаки.', '',
          'Пересечения (дома, топ-20):', '',
          md_table(['категории', 'заголовков'], list(t_h['combos'].items())), '',
          'Источник кандидата `title_source` (дома):', '',
          md_table(['title_source', 'задач'],
                   [(k.split(':', 1)[1], v) for k, v in t_h['stats'].items() if k.startswith('source:')]), '',
          '### 60 случайных обрубков «старый → кандидат» (дома)', '',
          md_table(['id', 'виден', 'категории', 'старый', 'кандидат'],
                   [(r['id'], '✓' if r['visible'] else '', ','.join(r['flags']), cell(r['title']),
                     cell(r['candidate'])) for r in t_h['sample_stub']]), '',
          '### 20 случайных НЕ обрубков, у которых кандидат другой (их не тронем)', '',
          md_table(['id', 'виден', 'старый', 'кандидат'],
                   [(r['id'], '✓' if r['visible'] else '', cell(r['title']), cell(r['candidate']))
                    for r in t_h['sample_keep']]), '']

    o += ['## 3. Подпункты', '',
          pair('показатель', ['parts_total', 'problems_with_parts'], lambda d, k: d['parts'][k]), '']
    for scope in ('all', 'visible'):
        keys = sorted(set(h['parts'][scope]['classes']) | set(p['parts'][scope]['classes']))
        o += [f'Классы меток ({scope}): `open` — не тест, `test` — тест; метки `digit` 1,2,3 / '
              '`cyr` а,б,в / `lat` a,b,c / `other` / `mixed`', '',
              pair('класс', keys, lambda d, k, s=scope: d['parts'][s]['classes'].get(k, 0)), '',
              pair(f'открытые с цифрами ({scope}): ссылки в answer/solution',
                   ['any', 'paren', 'dot', 'word'],
                   lambda d, k, s=scope: d['parts'][s]['open_digit_refs'].get(k, 0)), '']

    o += ['## 4. Источники', '',
          md_table(['id дома', 'источник', 'дома задач', 'дома видимых', 'дома со ссылкой',
                    'id боя', 'бой задач', 'бой видимых', 'бой со ссылкой'],
                   [(s['id'], cell(s['name']), s['problems'], s['visible'], s['with_url'],
                     *next(((q['id'], q['problems'], q['visible'], q['with_url'])
                            for q in p['sources']['list'] if q['name'] == s['name']), ('—',) * 4))
                    for s in h['sources']['list']]), '',
          '«Со ссылкой» — непустой `SourceReference.url` (у `Problem` поля `url` нет).', '']
    for d, name in ((h, 'дома'), (p, 'на копии боя')):
        o += [f'ЛЭШ {name}:', '', '```json',
              json.dumps(d['sources']['lesh'], ensure_ascii=False, indent=1), '```', '']

    o += ['## 5. Токены в тексте', '']
    for d, name in ((h, 'дома'), (p, 'на копии боя')):
        o += [f'{name}:', '', '```json', json.dumps(d['tokens'], ensure_ascii=False, indent=1), '```', '']

    o += ['## Ключи справочников: совпадают ли id дома и на бою', '']
    rows = []
    for key in ('topic', 'tag', 'source', 'feature', 'econ_concept'):
        hk, pk = h['keys'][key], p['keys'][key]
        same = sum(1 for i, v in pk.items() if hk.get(i) == v)
        rows.append((key, len(hk), len(pk), same, sum(1 for i in pk if i not in hk)))
    o += [md_table(['справочник', 'дома', 'бой', 'бой: тот же id и то же значение', 'бой: id нет дома'],
                   rows), '']
    hs, ps = h['keys']['problem_statement_sha1'], p['keys']['problem_statement_sha1']
    o += [md_table(['задачи', 'число'], [
        ('на бою', len(ps)), ('из них id есть дома', sum(1 for i in ps if i in hs)),
        ('условие побайтно то же', sum(1 for i, v in ps.items() if hs.get(i) == v))]), '']
    notes = HERE / 'recon_notes.md'
    if notes.exists():
        o += [notes.read_text(encoding='utf-8')]
    (HERE / 'RECON.md').write_text('\n'.join(o) + '\n', encoding='utf-8')
    print('RECON.md записан')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label')
    ap.add_argument('--settings', default='config.settings')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()
    if args.render:
        return render()
    sys.path.insert(0, str(ROOT))
    os.environ['DJANGO_SETTINGS_MODULE'] = args.settings
    import django
    django.setup()
    data = collect(args.label)
    path = HERE / f'recon_{args.label}.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    print('записано', path, 'задач', data['problems'])


if __name__ == '__main__':
    main()
