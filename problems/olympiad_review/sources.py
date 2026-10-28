# -*- coding: utf-8 -*-
"""Загрузчики очередей → позиции общего формата (`common.ITEM_KEYS`).

Источники волны 29.10.2026:

* **P1** — пары «судья не уверен» (`link_review.csv` импорта: задание эталона ↔
  задача банка) и две задачи из `claude_check_14.csv` (#63331 «похожа на не-задачу»,
  #63409 «Claude не проверил»);
* **P2** — второй проход аудита эталона (`morning_vN.1.jsonl` шести наборов);
  «на странице есть, в эталоне нет» — не проверка людьми, а недостающие
  задания: отдельным списком (`missing`), в пакеты не идут;
* **Q1 / Q2 / приёмка** — уже в общем формате (`load_common`).

`current` и `proposed` — на уровне БАНКА (title, statement, parts, solution,
answer): так их показывает сайт и так их правит человек. Строка эталона
переводится в поля банка тем же `reference_import.build_fields`, что и при
импорте; правка поля эталона (`statement_md`, `criteria_md`…) — через ту же
сборку из исправленной строки, в предложение идут только изменившиеся поля.
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from problems.olympiad_review import common

#: Поле правки P2 → поле строки эталона.
P2_ROW_FIELDS = {'statement_md': 'statement_md', 'solution_md': 'solution_md',
                 'criteria_md': 'criteria_md', 'answer': 'answer', 'title': 'title',
                 'parts': 'parts'}
#: `field_text` P2 режет текст правки на 3000 знаков — такая правка не предложение.
P2_TEXT_LIMIT = 3000
P2_MISSING = 'на странице есть, в эталоне нет'
P2_KIND_CODES = {'дефект без правки': 'defect', 'правка не принята': 'fix_rejected',
                 'рисунок не вырезан': 'figure', P2_MISSING: 'missing'}
_CONF = re.compile(r'уверенность\s+(\d(?:[.,]\d+)?)')


class Reference:
    """Последняя версия эталона одной олимпиады: строки, поля банка, страницы PDF."""

    def __init__(self, slug, path=None):
        from problems.olympiad_audit import bank_match, registry
        self.slug = slug
        self.digitized = common.audit_dir(slug) / 'digitized'
        self.path = Path(path) if path else self.digitized / common.LATEST_REFERENCE[slug]
        self.rows = {bank_match.row_key(r): r for r in common.read_jsonl(self.path)}
        self.short = registry.short_name(slug)
        self._pages = None

    def fields(self, row):
        """Строка эталона → (поля карточки, рисунки {hash: путь})."""
        from problems.olympiad_audit import reference_import as ri
        built = ri.build_fields(row, digitized_dir=str(self.digitized), url_map=ri.UrlMap(),
                                olympiad_short=self.short)
        return common.norm_fields(built), {f['hash']: f['path'] for f in built['figures']}

    def page_dirs(self):
        if self._pages is None:
            self._pages = {}
            inv = self.digitized / 'inventory.jsonl'
            if inv.is_file():
                for item in common.read_jsonl(inv):
                    if item.get('page_dir'):
                        self._pages[item['file']] = item['page_dir']
        return self._pages

    def page_images(self, row):
        """PNG страниц задания: условие, решение, критерии — по порядку, без повторов."""
        out = []
        for ref in (row.get('source_pages') or []) + (row.get('solution_pages') or []) \
                + (row.get('criteria_pages') or []):
            file, _sep, page = str(ref).partition('#p')
            page_dir = self.page_dirs().get(file)
            if not page_dir or not page.isdigit():
                continue
            png = str(self.digitized / page_dir / f'p{page}.png')
            if os.path.isfile(png) and png not in out:
                out.append(png)
        return out


class Bank:
    """Чтение банка: ключ эталона → задача, поля задачи как в карточке, видимость."""

    def __init__(self):
        self._visible = None

    @staticmethod
    def problem_for_key(key):
        from problems.models import OlympiadRef, SourceReference
        ref = OlympiadRef.objects.filter(source_site='official', record_id=f'official:{key}') \
            .values_list('problem_id', flat=True).first()
        if ref:
            return ref
        return SourceReference.objects.filter(problem_number=key[:50]) \
            .values_list('problem_id', flat=True).order_by('id').first()

    @staticmethod
    def created_from(problem, key):
        """Задача заведена импортом из этой строки эталона (а не привязана к чужому тексту).

        `create_problem` пишет первую `SourceReference` задачи с номером = ключ
        эталона; у привязанной задачи первая ссылка — из её родного источника."""
        first = problem.source_references.order_by('id').values_list('problem_number', flat=True).first()
        return (first or '') == key[:50]

    def is_visible(self, pid):
        if self._visible is None:
            from catalog.filters import base_queryset
            self._visible = set(base_queryset('catalog').values_list('id', flat=True))
        return pid in self._visible

    @staticmethod
    def fields(problem):
        """Поля задачи банка в виде карточки + рисунки {hash: 'db:<id>'}."""
        parts = [{'label': p.label, 'statement': p.statement, 'answer': p.answer}
                 for p in problem.parts.order_by('order', 'id')]
        fields = {'title': problem.title or '', 'statement': problem.statement or '',
                  'solution': problem.solution or '', 'answer': problem.answer or '',
                  'parts': parts}
        figures = {f.tikz_hash: f'db:{f.id}' for f in problem.figures.all()}
        return fields, figures


def _item(**kw):
    item = {k: None for k in common.ITEM_KEYS}
    item.update(kw)
    return item


def _pages(first, rest):
    """Страницы позиции (на которых модель нашла дефект) + остальные страницы задания."""
    out = []
    for png in list(first or []) + list(rest or []):
        if png not in out:
            out.append(png)
    return out


def _confidence(text):
    values = [float(v.replace(',', '.')) for v in _CONF.findall(text or '')]
    return values[-1] if values else None


def p2_ref_key(fid):
    """`событие|номер|вариант#группа` → ключ эталона `событие:номер[:вариант]`."""
    key = fid.split('#')[0]
    event, number, variant = (key.split('|') + ['', ''])[:3]
    return f'{event}:{number}' + (f':{variant}' if variant else '')


def parse_parts_text(text, labels):
    """Плоский текст правки пунктов («1 текст\\n2 текст») → подпункты по известным меткам.

    Только если строки идут ровно по меткам текущих пунктов; иначе None."""
    lines = [ln for ln in (text or '').split('\n') if ln.strip()]
    if not labels or not lines:
        return None
    out, current = [], None
    pending = list(labels)
    for line in lines:
        head = line.strip()
        if pending:
            lab = pending[0]
            m = re.match(r'\(?' + re.escape(lab.rstrip(').')) + r'[).:]?\s+(.*)$', head)
            if m:
                current = {'label': lab, 'text': m.group(1)}
                out.append(current)
                pending.pop(0)
                continue
        if current is None:
            return None
        current['text'] += '\n' + line
    return out if not pending else None


def p2_proposal(ref, row, field, text):
    """Правка поля строки эталона → (поля банка, изменённые правкой) или (None, причина)."""
    target = P2_ROW_FIELDS.get(field)
    if not target or not (text or '').strip() and field != 'answer':
        return None, 'правки нет'
    if len(text or '') >= P2_TEXT_LIMIT:
        return None, 'текст правки обрезан на 3000 знаков'
    new_row = dict(row)
    if target == 'parts':
        labels = [str(p.get('label', '')) for p in row.get('parts') or []]
        parsed = parse_parts_text(text, labels)
        if parsed is None:
            return None, 'пункты правки не разобрать по меткам'
        new_row['parts'] = parsed
    else:
        new_row[target] = text
    old, _f = ref.fields(row)
    new, _f = ref.fields(new_row)
    changed = {k: v for k, v in new.items() if old.get(k) != v}
    return (changed or None), ('' if changed else 'правка не меняет задачу на сайте')


def load_p2(paths, bank=None, refs=None):
    """morning_vN.1.jsonl → (позиции, недостающие задания)."""
    from problems.models import Problem
    bank = bank or Bank()
    refs = refs if refs is not None else {}
    items, missing = [], []
    for path in paths:
        for n, raw in enumerate(common.read_jsonl(path)):
            slug = common.P2_SETS[raw['set']]
            kind = raw['kind']
            code = P2_KIND_CODES.get(kind, 'other')
            if kind == P2_MISSING:
                missing.append(dict(raw, olympiad=slug, source='p2_recheck',
                                    item_id=f'p2_recheck:{slug}:{raw["unit"]}:{raw.get("iid") or n}'))
                continue
            key = p2_ref_key(raw['fid'])
            group = raw['fid'].split('#')[-1] if '#' in raw['fid'] else ''
            if slug not in refs:
                refs[slug] = Reference(slug)
            ref = refs[slug]
            row = ref.rows.get(key)
            details = f'{kind}: {raw.get("why") or ""}'.strip()
            pid = bank.problem_for_key(key)
            current, figures, proposed, note = None, {}, None, ''
            current_from = 'bank'
            if pid:
                problem = Problem.objects.get(pk=pid)
                if row is not None and bank.created_from(problem, key):
                    # Задача заведена из эталона: показываем её так, как она станет
                    # после обновления до последней версии (ВП ещё на v6 — фаза 5).
                    current, figures = ref.fields(row)
                    current_from = 'reference'
                    if raw.get('field') and code == 'fix_rejected':
                        proposed, note = p2_proposal(ref, row, raw['field'], raw.get('text'))
                else:
                    current, figures = bank.fields(problem)
                    note = 'задача банка привязана к заданию, текст у неё свой — правку эталона переносить руками'
            elif row is not None:
                current, figures = ref.fields(row)
                current_from = 'reference'
                if raw.get('field') and code == 'fix_rejected':
                    proposed, note = p2_proposal(ref, row, raw['field'], raw.get('text'))
            else:
                note = 'строки эталона с таким ключом нет'
            if raw.get('text') and proposed is None and code != 'defect':
                details += f'\nМодель предлагала ({raw.get("field") or "поле"}): {raw["text"][:1500]}'
            if note:
                details += f'\n[{note}]'
            items.append(_item(
                item_id=f'p2_recheck:{slug}:{key}:{code}:{group}:{raw.get("unit")}:{raw.get("iid") or n}',
                source='p2_recheck', olympiad=slug, ref_key=key, problem_id=pid,
                check=f'P2 {kind}' + (f' ({group})' if group else ''), details=details,
                page_images=_pages(raw.get('pngs'), ref.page_images(row) if row else []),
                current=current, proposed=proposed, confidence=_confidence(raw.get('why')),
                figures=figures, stage=(row or {}).get('stage', ''), current_from=current_from))
    return items, missing


#: link_review.csv импорта P1 → олимпиада строки эталона.
P1_LINK_REVIEW = (
    ('vp', 'audit_vp_20261008/import_v6_judge/real/link_review.csv'),
    ('mosh', 'audit_mosh_20261009/import_v71/real/link_review.csv'),
    ('mosh-entrepreneurship',
     'audit_finbiz_20261013/mosh_entrepreneurship/import_journal_v31/real/link_review.csv'),
)
P1_CHECK14 = 'audit_finbiz_20261013/claude_check_14.csv'
P1_EXTRA = {'63331': 'похожа на не-задачу', '63409': 'Claude не проверил'}


def load_p1(root=None, bank=None, refs=None):
    """Пары «судья не уверен» + две задачи из claude_check_14 → позиции."""
    from problems.models import Problem
    root = Path(root) if root else common.data_root()
    bank = bank or Bank()
    refs = refs if refs is not None else {}
    items = []
    for slug, rel in P1_LINK_REVIEW:
        with open(root / rel, encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        if slug not in refs:
            refs[slug] = Reference(slug)
        ref = refs[slug]
        for r in rows:
            key = r['key']
            row = ref.rows.get(key)
            bank_id = int(r['задача банка'])
            current, figures = ref.fields(row) if row else (None, {})
            bank_fields, bank_figures = bank.fields(Problem.objects.get(pk=bank_id))
            figures.update(bank_figures)
            items.append(_item(
                item_id=f'p1_link:{slug}:{key}', source='p1_link', olympiad=slug, ref_key=key,
                problem_id=None, check='P1 пара: та же задача?',
                details=(f'Судья не уверен: {r["причина"]}. Кандидат — задача банка #{bank_id} '
                         f'({r["источник задачи банка"]}), сходство {r["сходство"]}, '
                         f'вхождение {r["вхождение"]}. «Принять» = это та же задача '
                         '(привязать), «Верно» = разные задачи (завести новую).'),
                page_images=ref.page_images(row) if row else [], current=current,
                proposed={'link_to': bank_id}, confidence=None, figures=figures,
                pair_bank={'id': bank_id, 'fields': bank_fields,
                           'source': r['источник задачи банка']},
                stage=(row or {}).get('stage', ''), current_from='reference'))
    with open(root / P1_CHECK14, encoding='utf-8-sig', newline='') as handle:
        check14 = {r['id']: r for r in csv.DictReader(handle)}
    for pid, label in P1_EXTRA.items():
        r = check14[pid]
        problem = Problem.objects.get(pk=int(pid))
        current, figures = bank.fields(problem)
        pages = [str(root / 'audit_finbiz_20261013' / p) for p in r['страницы'].split()]
        details = f'P1, проверка 14 задач: {label}. Жалоба обогащения: {r["жалоба"]}'
        if r.get('проблемы'):
            details += f'\nClaude ({r["вердикт Claude"]}, {r["confidence"]}): {r["проблемы"]}'
        items.append(_item(
            item_id=f'p1_check14:{pid}', source='p1_check14',
            olympiad=r['key'].split('-20')[0], ref_key=r['key'], problem_id=int(pid),
            check=f'P1 {label}', details=details, page_images=pages, current=current,
            proposed=None, confidence=float(r['confidence']) if r.get('confidence') else None,
            figures=figures))
    return items


def load_common(path, bank=None):
    """Очередь в общем формате (Q1, Q2, дефекты приёмки). Поля — к виду карточки.

    Q1 кладёт тесты как `options` + `key`; у банка варианты — это подпункты
    (метка, текст, «верно» у верных), поэтому они переводятся в `parts`."""
    bank = bank or Bank()
    items = []
    for raw in common.read_jsonl(path):
        item = _item(**{k: raw.get(k) for k in common.ITEM_KEYS})
        for extra in ('auto', 'stage'):
            if extra in raw:
                item[extra] = raw[extra]
        item['current'] = _from_common_fields(raw.get('current'))
        item['proposed'] = _from_common_fields(raw.get('proposed'))
        item['figures'] = {}
        if item['problem_id']:
            from problems.models import Problem
            problem = Problem.objects.filter(pk=item['problem_id']).first()
            if problem is not None:
                bank_fields, item['figures'] = bank.fields(problem)
                if not item['current']:
                    item['current'] = bank_fields
        items.append(item)
    return items


def _from_common_fields(fields):
    if not fields:
        return None
    fields = dict(fields)
    options = fields.pop('options', None)
    key = fields.pop('key', None)
    out = common.norm_fields(fields)
    if options and 'parts' not in out:
        keys = {str(k) for k in (key if isinstance(key, list) else [key]) if k not in (None, '')}
        out['parts'] = [{'label': str(o.get('label', i + 1)) if isinstance(o, dict) else str(i + 1),
                         'statement': (o.get('text') or o.get('statement') or '') if isinstance(o, dict)
                         else str(o),
                         'answer': ''} for i, o in enumerate(options)]
        for p in out['parts']:
            if p['label'] in keys:
                p['answer'] = 'верно'
    return out or None


def write_missing(path, missing):
    common.write_jsonl(path, missing)
    return len(missing)


def dump(obj):
    return json.dumps(obj, ensure_ascii=False)
