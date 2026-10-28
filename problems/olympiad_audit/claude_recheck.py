# -*- coding: utf-8 -*-
u"""Второй проход по очереди «на утро» аудита Claude: v7 → v7.1, v3 → v3.1.

Каждая позиция `morning_vN.jsonl` (правка не принята, дефект без правки,
«на странице есть, в эталоне нет», рисунок не вырезан) уходит в Claude Opus 5.5
вместе с картинками своих страниц и соседних (предыдущей и следующей, в
уменьшенном виде). Позиции одной единицы аудита идут одним запросом.

Модель по каждой позиции решает:

* `fix` — дать ПОЛНЫЙ исправленный текст поля;
* `keep` — менять нечего (текст верен, тревога ложная, рисунок не нужен);
* `figure` — рамка рисунка на странице;
* `human` — по страницам не решить, нужен человек.

Решение принимается только при уверенности ≥ 0,9 и с дословной цитатой со
страницы (если у страницы есть текстовый слой — цитата обязана в нём
найтись). Правка `fix` вдобавок проходит те же проверки, что и в первом проходе
(`claude_eyes.check_unit`: числа со страницы, KaTeX, «Ответ:», урезание).
Остальное остаётся в очереди.

Позиции, которые решаются без модели (закрываются с причиной):

* «такой рисунок уже есть в эталоне» — рисунок на месте;
* находка Haiku «на странице есть, в эталоне нет» на единице, которую Sonnet
  проверил и этого не подтвердил (мнение Sonnet сильнее, как в `resolve`).

Выход — рядом с v7 / v3, они не перезаписываются: `<vN.1>/reference_problems_<vN.1>.jsonl`,
слой `claude_recheck_<vN.1>.json`, `<vN>_to_<vN.1>_keys.csv`, `changes_<vN.1>.md`,
`review_<vN.1>.html` и `morning_<vN.1>.jsonl` — только то, что осталось в очереди.
"""
from __future__ import annotations

import base64
import collections
import io
import json
import os
import re

from . import claude_eyes as ce

MODEL = 'claude-opus-5-5'
MIN_CONFIDENCE = 0.9
#: Доля слов цитаты, которые обязаны найтись в текстовом слое страниц.
EVIDENCE_SHARE = 0.7
MAX_IMAGES = 6
NEIGHBOR_SIDE = 1000
VERSIONS = {'v7': 'v7.1', 'v3': 'v3.1'}

KIND_FIX = 'правка не принята'
KIND_DEFECT = 'дефект без правки'
KIND_UNLISTED = 'на странице есть, в эталоне нет'
KIND_FIGURE = 'рисунок не вырезан'

SYSTEM_PROMPT = """Ты — второй, строгий проверяющий оцифровки олимпиадных заданий (экономика, финансовая грамотность, бизнес). Первый проход (другая модель) сверил оцифровку с картинками страниц PDF, но часть случаев не смог решить уверенно — они в очереди к человеку. Твоя задача — разобрать каждую позицию очереди по картинкам страниц и решить её, если это можно сделать по странице надёжно.

Тебе даны картинки страниц: «проверяемые» — в полном размере, «соседние» (предыдущая и следующая) — уменьшенные, для контекста (задание может начинаться или продолжаться на соседней странице). Для каждой позиции дано: вид позиции, текущий текст полей фрагмента в эталоне (current), заметка первого прохода (first_pass_note) и, если была, его отклонённая правка (first_pass_proposal).

Виды позиций:
- «правка не принята» — первый проход предложил правку, но она не прошла проверку (низкая уверенность, число не нашлось на странице и т. п.). Проверь по странице, нужна ли правка и какая именно.
- «дефект без правки» — первый проход увидел дефект, но правку не дал. Если дефект настоящий и его можно исправить по странице — дай правку.
- «на странице есть, в эталоне нет» — на странице вроде бы есть задание или пункт, которого нет среди фрагментов. Сверь со списком заданий комплекта: если оно есть в эталоне под другим номером или это не задание (инструкция, бланк, колонтитул) — это ложная тревога.
- «рисунок не вырезан» — нужна рамка рисунка (графика, схемы, диаграммы) на странице.

Решения (поле decision):
- "fix" — исправить: в fixes дай ПОЛНЫЙ исправленный текст каждого исправляемого поля (statement_md, title, answer, solution_md, criteria_md — строкой; parts — полным списком [{"label": …, "text": …}]). Только поля этого фрагмента.
- "keep" — менять ничего не надо: текущий текст верен, тревога ложная, рисунок не нужен или уже есть.
- "figure" — дать рамку рисунка в figure_bboxes: page — номер картинки в этом запросе (1, 2, …), bbox — [x0, y0, x1, y1] в долях ширины и высоты (0…1, от левого верхнего угла), рисунок с подписями осей, без соседнего текста. Таблицы и формулы — не рисунки, их переписывают текстом (это "fix").
- "human" — по этим страницам надёжно не решить (нужен текст, которого на страницах нет; надо добавить целое новое задание; страница нечитаема) — оставить человеку.

ПРАВИЛА:
1. Переписывай ДОСЛОВНО, как на картинке. Опечатки авторов — как в оригинале. Ничего не решай, не досочиняй, не добавляй ответов, которых нет на странице.
2. Исправляй только то, что ВИДНО на страницах. Если фрагмент помечен "editable": false (не все его страницы показаны), "fix" не давай.
3. Колонтитулы, номера страниц, водяные знаки в текст не идут.
4. Разметка: Markdown; формулы — TeX внутри $…$ (KaTeX); таблицы — markdown-таблицами; варианты ответа — списком, по строке на вариант, с исходными буквами/цифрами.
5. Принятая разметка эталона — НЕ дефект: пункты стоят и в statement_md, и в parts; вступление своего раздела в начале условия теста; «(отмечено)» у варианта в решении теста; повтор вопроса пункта в решении.
6. evidence — ОБЯЗАТЕЛЬНО: дословная цитата со страницы (несколько слов подряд, как напечатано), которая доказывает решение. Для "keep" — цитата, которая показывает, что текущий текст верен или что тревога ложная.
7. confidence — от 0 до 1. Ставь 0.9 и выше только если уверен полностью; сомневаешься — "human".

Ответ — ТОЛЬКО JSON, без пояснений вокруг:
{"tasks": [{"id": "i1", "decision": "fix"|"keep"|"figure"|"human", "classes": ["missing_text"], "fixes": {…}, "figure_bboxes": [{"page": 1, "bbox": [0.1, 0.2, 0.9, 0.5], "caption": "…"}], "evidence": "…", "why": "коротко, почему так", "confidence": 0.95}]}
Классы (classes) — из списка: missing_text, missing_table, table_wrong, missing_options, missing_part, part_split_wrong, figure_as_text, figure_missing, formula_wrong, number_wrong, solution_misattached, criteria_missing, service_block_in_task, title_wrong, other."""


# ── Очередь ──────────────────────────────────────────────────────────────

def load_version(name, data_root, audit_dirs):
    """Набор с текущей версией (v7 / v3) вместо входной и очередь «на утро»."""
    base = ce.load_set(name, data_root, audit_dirs)
    version = base.out_version
    path = os.path.join(base.digitized, version, 'reference_problems_%s.jsonl' % version)
    ds = ce.DataSet(name, base.digitized, ce.read_jsonl(path), base.manifest, version, VERSIONS[version])
    items = ce.read_jsonl(os.path.join(base.digitized, version, 'morning_%s.jsonl' % version))
    return ds, items


def auto_close(items, sonnet_units):
    """Позиции, которые решаются без модели → (к модели, закрытые с причиной)."""
    todo, closed = [], []
    for item in items:
        note = ''
        if item['kind'] == KIND_FIGURE and item.get('why') == 'такой рисунок уже есть в эталоне':
            note = 'рисунок уже есть в эталоне'
        elif (item['kind'] == KIND_UNLISTED and item.get('model') == 'claude-haiku-5-5'
              and item.get('unit') in sonnet_units):
            note = 'находка Haiku, Sonnet по той же странице её не подтвердил'
        if note:
            closed.append(dict(item, resolution='closed', note=note, by='auto'))
        else:
            todo.append(item)
    return todo, closed


def group_items(items):
    """Позиции → {единица: [позиции с id i1, i2, …]} в порядке появления."""
    out = collections.OrderedDict()
    for item in items:
        bucket = out.setdefault(item['unit'], [])
        bucket.append(dict(item, iid='i%d' % (len(bucket) + 1)))
    return out


def _shift(ref, manifest, step):
    head, page = ref.rsplit('#p', 1)
    other = '%s#p%d' % (head, int(page) + step)
    return other if other in manifest else None


def group_refs(row, group):
    return ce._uniq(row.get(ce.GROUPS[group][0]) or [])


def request_pages(unit, items, rows_by_key, manifest, max_images=MAX_IMAGES):
    """Картинки запроса: [(ref, 'проверяемая'|'соседняя')]. Сначала страницы
    единицы, затем недостающие страницы фрагментов позиций, затем соседние
    (предыдущая к первой и следующая к последней) — пока влезает."""
    main = list(unit['pages'])
    for item in items:
        if item.get('fid'):
            key, group = item['fid'].split('#')
            for ref in group_refs(rows_by_key.get(key, {}), group):
                if ref in manifest and ref not in main and len(main) < max_images:
                    main.append(ref)
    pages = [(ref, 'проверяемая') for ref in main]
    for ref in (_shift(main[0], manifest, -1), _shift(main[-1], manifest, 1)):
        if ref and ref not in main and len(pages) < max_images:
            pages.append((ref, 'соседняя'))
    order = {ref: i for i, ref in enumerate(sorted({r for r, _ in pages},
                                                  key=lambda r: (r.rsplit('#p', 1)[0], int(r.rsplit('#p', 1)[1]))))}
    return sorted(pages, key=lambda p: order[p[0]])


def scaled_image_block(path, max_side=NEIGHBOR_SIDE):
    from PIL import Image
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        image.save(buf, 'JPEG', quality=80)
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                        'data': base64.b64encode(buf.getvalue()).decode('ascii')}}


def item_payload(item, frag, pages):
    refs = [r for r, _ in pages]
    out = {'id': item['iid'], 'kind': item['kind'], 'fid': item.get('fid') or '',
           'field': item.get('field') or '', 'first_pass_note': item.get('why') or ''}
    if item['kind'] == KIND_FIX and item.get('text'):
        out['first_pass_proposal'] = item['text']
    if item['kind'] == KIND_UNLISTED and item.get('text'):
        out['seen_on_page'] = item['text']
    if frag is not None:
        out['group'] = frag['group']
        out['editable'] = frag['editable']
        out['current'] = frag['fields']
        out['own_pages'] = [refs.index(r) + 1 for r in frag['refs'] if r in refs]
    return out


def fragments_for(items, units_by_fid, rows_by_key, pages):
    """fid → фрагмент с полями ТЕКУЩЕЙ версии; editable — все страницы группы в запросе."""
    refs = {r for r, _ in pages}
    out = {}
    for item in items:
        fid = item.get('fid')
        if not fid or fid in out or fid not in units_by_fid:
            continue
        key, group = fid.split('#')
        row = rows_by_key[key]
        own = group_refs(row, group)
        out[fid] = {'fid': fid, 'group': group, 'refs': own, 'editable': bool(own) and set(own) <= refs,
                    'fields': ce.fragment_fields(row, group)}
    return out


def unit_text(unit, pages, items, frags):
    lines = ['Картинки в этом запросе:']
    for i, (ref, role) in enumerate(pages, 1):
        lines.append('Страница %d (%s): %s, стр. %s' % (i, role, ref.split('#')[0].split('/')[-1],
                                                        ref.rsplit('#p', 1)[-1]))
    if unit.get('event_tasks'):
        lines += ['', 'Задания комплекта в эталоне (номер: начало условия):']
        lines += ['%s: %s' % (ev, '; '.join(t)) for ev, t in sorted(unit['event_tasks'].items())]
    payload = [item_payload(item, frags.get(item.get('fid')), pages) for item in items]
    lines += ['', 'Позиции очереди:', json.dumps(payload, ensure_ascii=False, indent=1), '',
              'Разбери каждую позицию и верни JSON по правилам.']
    return '\n'.join(lines)


def request_params(unit, items, frags, pages, ds, model=MODEL, effort='medium', max_tokens=16000):
    content = []
    for i, (ref, role) in enumerate(pages, 1):
        content.append({'type': 'text', 'text': 'Страница %d (%s):' % (i, role)})
        content.append(ce.image_block(ds.png(ref)) if role == 'проверяемая'
                       else scaled_image_block(ds.png(ref)))
    content.append({'type': 'text', 'text': unit_text(unit, pages, items, frags)})
    return {'model': model, 'max_tokens': max_tokens, 'output_config': {'effort': effort},
            'system': [{'type': 'text', 'text': SYSTEM_PROMPT, 'cache_control': {'type': 'ephemeral'}}],
            'messages': [{'role': 'user', 'content': content}]}


class Plan:
    """Всё, что нужно для запросов и проверки: единицы текущей версии, очередь по единицам."""

    def __init__(self, ds, items, sonnet_units):
        self.ds = ds
        self.units, _ = ce.build_units(ds)
        self.rows_by_key = {ce.task_key(r): r for r in ds.rows}
        self.unit_of_fid = {f['fid']: uid for uid, u in self.units.items() for f in u['fragments']}
        self.todo, self.closed = auto_close(items, sonnet_units)
        self.by_unit = group_items(self.todo)

    def pages(self, uid):
        unit = self.units.get(uid) or {'pages': [], 'fragments': []}
        if not unit['pages']:
            return []
        return request_pages(unit, self.by_unit[uid], self.rows_by_key, self.ds.manifest)

    def frags(self, uid, pages):
        return fragments_for(self.by_unit[uid], self.unit_of_fid, self.rows_by_key, pages)

    def params(self, uid, effort='medium'):
        pages = self.pages(uid)
        return request_params(self.units[uid], self.by_unit[uid], self.frags(uid, pages), pages,
                              self.ds, effort=effort)


# ── Проверка ответа ──────────────────────────────────────────────────────

_WORD = re.compile(r'\w{3,}')


def evidence_on_page(evidence, layer, share=EVIDENCE_SHARE):
    """Цитата со страницы: у скана без слоя — непустая; со слоем — ≥ `share`
    слов цитаты есть в слое и все числа цитаты тоже."""
    evidence = (evidence or '').strip()
    if len(evidence) < 8:
        return False
    if not layer.strip():
        return True
    words = [w.lower() for w in _WORD.findall(evidence)]
    have = {w.lower() for w in _WORD.findall(layer)}
    if ce.numbers(evidence) - ce.numbers(layer):
        return False
    if not words:
        return True
    return sum(1 for w in words if w in have) >= share * len(words)


def check_item(item, ans, frag, pages, page_texts, katex=ce.katex_errors):
    """Позиция + ответ модели → {'resolution': fixed|closed|figure|queue, …}."""
    if ans is None:
        return {'resolution': 'queue', 'reasons': ['нет ответа по позиции']}
    decision = str(ans.get('decision') or '')
    evidence = str(ans.get('evidence') or '')
    why = str(ans.get('why') or '')[:500]
    conf = ce._confidence(ans)
    base = {'decision': decision, 'evidence': evidence[:500], 'note': why, 'confidence': conf}
    reasons = []
    if conf < MIN_CONFIDENCE:
        reasons.append('уверенность %.2f < %.2f' % (conf, MIN_CONFIDENCE))
    if not evidence_on_page(evidence, '\n'.join(page_texts)):
        reasons.append('нет цитаты со страницы')
    if decision == 'human' or decision not in ('fix', 'keep', 'figure'):
        reasons.append('модель оставила человеку' if decision == 'human' else 'неизвестное решение %r' % decision)
    if decision == 'fix':
        fixes = ans.get('fixes') or {}
        if frag is None:
            reasons.append('у позиции нет фрагмента — править нечего')
        elif not isinstance(fixes, dict) or not fixes:
            reasons.append('решение fix без fixes')
        else:
            classes = [c for c in (ans.get('classes') or []) if isinstance(c, str)] or ['other']
            unit = {'fragments': [frag]}
            reply = {'tasks': [{'fid': frag['fid'], 'fixes': fixes, 'confidence': conf,
                                'defects': [{'class': c, 'evidence': evidence} for c in classes]}]}
            accepted, rejected, _ = ce.check_unit(unit, reply, page_texts, katex=katex,
                                                  min_confidence=MIN_CONFIDENCE)
            for chk in rejected:
                reasons += ['%s: %s' % (chk.field, r) for r in chk.reasons] if isinstance(chk, ce.FixCheck) \
                    else [str(chk[1])]
            if not reasons:
                return dict(base, resolution='fixed', fixes=accepted, classes=classes)
    if decision == 'figure':
        figs = []
        for fig in ans.get('figure_bboxes') or []:
            if not isinstance(fig, dict):
                continue
            try:
                page = int(fig.get('page', 0))
            except (TypeError, ValueError):
                page = 0
            if not 1 <= page <= len(pages) or ce.valid_bbox(fig.get('bbox')) is None:
                reasons.append('негодная рамка')
                continue
            figs.append({'page_ref': pages[page - 1][0], 'bbox': [float(v) for v in fig['bbox']],
                         'caption': str(fig.get('caption') or '')})
        if frag is None or frag['group'] not in ('statement', 'solution'):
            reasons.append('рисунок не к условию и не к решению')
        elif not frag['editable']:
            reasons.append('группа видна не целиком')
        if not figs:
            reasons.append('нет рамки')
        if not reasons:
            return dict(base, resolution='figure', figures=figs)
    if decision == 'keep' and not reasons:
        return dict(base, resolution='closed')
    return dict(base, resolution='queue', reasons=reasons)


def check_unit_reply(plan, uid, raw_text, katex=ce.katex_errors):
    """Сырой ответ единицы → [(позиция, итог)]."""
    reply = ce.parse_reply(raw_text)
    answers = {str(t.get('id')): t for t in reply.get('tasks') or [] if isinstance(t, dict)}
    pages = plan.pages(uid)
    frags = plan.frags(uid, pages)
    texts = [plan.ds.layer(ref) for ref, _ in pages]
    out = []
    for item in plan.by_unit[uid]:
        if reply.get('_parse_error'):
            res = {'resolution': 'queue', 'reasons': ['ответ не разобран']}
        else:
            res = check_item(item, answers.get(item['iid']), frags.get(item.get('fid')), pages, texts,
                             katex=katex)
        out.append((item, res))
    return out


# ── Сборка vN.1 ──────────────────────────────────────────────────────────

def _same_as_existing(existing, item, bbox):
    """Рисунок той же страницы с заметным пересечением: прежние рамки — `bbox_model`
    (тысячные доли) или `bbox_norm` (доли, вырезки Claude)."""
    for old in existing:
        if not isinstance(old, dict):
            continue
        if old.get('bbox_norm') and old.get('page') == item['page'] and old.get('page_dir') == item['page_dir']:
            norm = dict(old, bbox_model=[float(v) * 1000 for v in old['bbox_norm']])
            if ce._same_figure(norm, item, bbox):
                return True
        elif ce._same_figure(old, item, bbox):
            return True
    return False


def build(ds, results, closed, out_dir=None, katex=ce.katex_errors):
    """Текущая версия + принятые решения второго прохода → vN.1 рядом с vN.

    `results` — [(позиция, итог)] по всем отправленным позициям; `closed` — закрытые
    без модели. Возвращает сводку и инварианты."""
    version = ds.out_version
    out_dir = out_dir or os.path.join(ds.digitized, version)
    rows_by_key = {ce.task_key(r): r for r in ds.rows}
    texts, figs, queue, done = {}, [], [], list(closed)
    fig_count = collections.Counter()
    for item, res in results:
        if res['resolution'] == 'fixed':
            for chk in res['fixes']:
                key, group = chk.fid.split('#')
                texts[(key, chk.field)] = {'key': key, 'group': group, 'field': chk.field, 'value': chk.new,
                                           'old_sha1': ce._sha(chk.old), 'unit': item['unit'], 'model': MODEL,
                                           'kind': item['kind'], 'classes': res.get('classes', [])}
            done.append(dict(item, resolution='fixed', note=res.get('note', '')))
        elif res['resolution'] == 'figure':
            key, group = item['fid'].split('#')
            row = rows_by_key[key]
            existing = (row.get('figures') or []) + (row.get('solution_figures') or [])
            added = 0
            for fig in res['figures']:
                page_item = ds.manifest[fig['page_ref']]
                if _same_as_existing(existing, page_item, fig['bbox']):
                    continue
                fig_count[key] += 1
                ev, num, var = key.split('|')
                name = '%s_%s%s_r%d%s.png' % (ev, re.sub(r'[^\w-]', '_', num), ('_' + var) if var else '',
                                              fig_count[key], 's' if group == 'solution' else '')
                rel = '%s/figures_%s/%s' % (version, version, name)
                size = ce.crop_figure(ds.png(fig['page_ref']), fig['bbox'], os.path.join(ds.digitized, rel))
                if size is None:
                    continue
                figs.append({'key': key, 'field': 'figure',
                             'target': 'figures' if group == 'statement' else 'solution_figures',
                             'value': {'path': rel, 'caption': fig['caption'], 'flag': 'claude_recheck',
                                       'page': page_item['page'], 'page_dir': page_item['page_dir'],
                                       'bbox_norm': fig['bbox'], 'size': list(size), 'model': MODEL},
                             'unit': item['unit'], 'model': MODEL})
                added += 1
            note = res.get('note', '') if added else 'рисунок уже есть в эталоне'
            done.append(dict(item, resolution='figure' if added else 'closed', note=note))
        elif res['resolution'] == 'closed':
            done.append(dict(item, resolution='closed', note=res.get('note', '')))
        else:
            why = '; '.join(res.get('reasons') or [])
            queue.append(dict(item, why=('%s · второй проход: %s%s' % (
                item.get('why', ''), why, (' — ' + res['note']) if res.get('note') else ''))[:900]))
    layer = list(texts.values()) + figs
    new_rows, log = ce.apply_layer(ds.rows, layer)
    for row in new_rows:
        changed = sorted({f for k, f, s in log if k == ce.task_key(row) and s == 'applied'})
        if changed:
            row['claude_recheck'] = {'version': version, 'fields': changed}
    path = os.path.join(out_dir, 'reference_problems_%s.jsonl' % version)
    if os.path.abspath(path) == os.path.abspath(os.path.join(ds.digitized, ds.in_version,
                                                             'reference_problems_%s.jsonl' % ds.in_version)):
        raise ValueError('выход совпал со входом — отказ')
    ce.write_jsonl(path, new_rows)
    with open(os.path.join(out_dir, 'claude_recheck_%s.json' % version), 'w', encoding='utf-8', newline='\n') as h:
        json.dump({'set': ds.name, 'base': ds.in_version, 'version': version, 'model': MODEL,
                   'fixes': list(texts.values()), 'figures': figs,
                   'resolved': [{k: v for k, v in d.items() if k != 'pngs'} for d in done]},
                  h, ensure_ascii=False, indent=1)
    keys = [ce.task_key(r) for r in new_rows]
    new_keys = set(keys)
    ce.write_csv(os.path.join(out_dir, '%s_to_%s_keys.csv' % (ds.in_version, version)),
                 ['%s_key' % ds.in_version, '%s_key' % version, 'судьба'],
                 [[k, k if k in new_keys else '', 'тот же' if k in new_keys else 'НЕТ ПРИЧИНЫ']
                  for k in rows_by_key])

    def segs(rows):
        out = [s for r in rows for f in ('statement_md', 'solution_md', 'answer', 'criteria_md', 'title')
               for s in ce.math_segments(r.get(f) or '')]
        return out + [s for r in rows for p in (r.get('parts') or []) if isinstance(p, dict)
                      for s in ce.math_segments(p.get('text') or '')]
    new_err = sum(1 for e in katex(segs(new_rows)) if e)
    base_err = sum(1 for e in katex(segs(ds.rows)) if e)
    inv = {'tasks_in': len(ds.rows), 'tasks_out': len(new_rows),
           'lost_without_reason': len(rows_by_key) - len(new_keys & set(rows_by_key)),
           'duplicate_keys': len(keys) - len(new_keys),
           'katex_errors_in': base_err, 'katex_errors_out': new_err,
           'katex_errors_new': max(0, new_err - base_err),
           'layer_entries': len(layer), 'layer_applied': sum(1 for x in log if x[2] == 'applied'),
           'layer_not_applied': [x for x in log if x[2] != 'applied'],
           'queue_in': len(results) + len(closed), 'queue_out': len(queue)}
    inv['ok'] = (inv['tasks_in'] == inv['tasks_out'] and inv['lost_without_reason'] == 0
                 and inv['duplicate_keys'] == 0 and inv['katex_errors_new'] == 0
                 and not inv['layer_not_applied'])
    with open(os.path.join(out_dir, 'invariants_%s.json' % version), 'w', encoding='utf-8', newline='\n') as h:
        json.dump(inv, h, ensure_ascii=False, indent=1)
    ce.write_jsonl(os.path.join(out_dir, 'morning_%s.jsonl' % version), queue)
    ce.review_html(queue, os.path.join(out_dir, 'review_%s.html' % version),
                   '%s %s: на утро после второго прохода (Opus)' % (ds.name, version))
    _changes_md(ds, out_dir, texts, figs, done, queue, inv)
    return {'rows': new_rows, 'texts': list(texts.values()), 'figures': figs, 'done': done,
            'queue': queue, 'invariants': inv, 'path': path, 'log': log}


def _changes_md(ds, out_dir, texts, figs, done, queue, inv):
    version = ds.out_version
    lines = ['# %s: %s → %s, второй проход очереди (Claude Opus 5.5)' % (ds.name, ds.in_version, version), '',
             'Очередь на входе: %d позиций; на выходе: %d.' % (inv['queue_in'], inv['queue_out']), '',
             '| вид позиции | исправлено | рисунок | закрыто без правки | осталось |', '|---|---|---|---|---|']
    kinds = collections.OrderedDict((k, collections.Counter()) for k in (KIND_FIX, KIND_DEFECT,
                                                                         KIND_UNLISTED, KIND_FIGURE))
    for d in done:
        kinds.setdefault(d['kind'], collections.Counter())[d['resolution']] += 1
    for q in queue:
        kinds.setdefault(q['kind'], collections.Counter())['queue'] += 1
    for kind, c in kinds.items():
        lines.append('| %s | %d | %d | %d | %d |' % (kind, c['fixed'], c['figure'], c['closed'], c['queue']))
    lines += ['', 'Правок полей: %d; новых рисунков: %d.' % (len(texts), len(figs)), '',
              '## Инварианты', '', '```',
              json.dumps({k: v for k, v in inv.items() if k != 'layer_not_applied'}, ensure_ascii=False, indent=1),
              '```', '', '## Примеры правок', '']
    base = {ce.task_key(r): r for r in ds.rows}
    for entry in list(texts.values())[:15]:
        lines += ['### `%s` · %s (%s)' % (entry['key'], entry['field'], entry['kind']), '',
                  'Было:', '', '```', ce.field_text(base[entry['key']].get(entry['field']))[:800], '```', '',
                  'Стало:', '', '```', ce.field_text(entry['value'])[:800], '```', '']
    with open(os.path.join(out_dir, 'changes_%s.md' % version), 'w', encoding='utf-8', newline='\n') as h:
        h.write('\n'.join(lines))
