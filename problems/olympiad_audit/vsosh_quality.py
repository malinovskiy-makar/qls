# -*- coding: utf-8 -*-
"""ВсОШ v1: проверки качества, страница для владельца, сверка с банком.

check  — по каждой строке `reference_problems_v1.jsonl` флаги:
         пустое условие, расхождение со слоем, числа слоя не найдены,
         пункты потеряны («а)…б)» в тексте, `parts` пуст), тест без вариантов
         или без ключа, у комплекта есть файл решений, а у задачи решения нет,
         рисунок с флагом вырезки; KaTeX — node-скриптом `vsosh_katex.js`
         (результат `katex_v1.json` подхватывается, если есть).
review — `review_v1.html`: ТОЛЬКО строки с флагами — картинка страницы и текст рядом.
bank   — только чтение базы: привязки `vseros` по этапам и сезонам, оценка
         «создать / привязать / сомнительные» для импорта следующей ночи.
"""
from __future__ import annotations

import html
import json
import os
import re
from collections import Counter, defaultdict

from problems.olympiad_audit import digitize

_LIST_MARK = re.compile(r'(?m)^\s*(?:[-*]\s*)?(?:\(?[а-еa-e]\)|\d{1,2}[.)])\s+\S')
_OPTION = re.compile(r'(?m)^\s*(?:[-*]\s*)?(?:\(?[а-еa-eА-ЕA-E]\)|[1-6][.)]|[А-ЕA-E][.)])\s+\S')


def task_flags(r, event_has_solutions):
    flags = list(r.get('flags') or [])
    st = r.get('statement_md') or ''
    if not st.strip():
        flags.append('пустое_условие')
    if r.get('layer_ratio') is not None and r['layer_ratio'] < 0.9:
        flags.append('расходится_со_слоем')
    if r.get('numbers_ok') is False:
        flags.append('числа_слоя_не_найдены')
    if len(_LIST_MARK.findall(st)) >= 2 and not r.get('parts'):
        flags.append('пункты_не_разобраны')
    is_test = str(r.get('number', '')).startswith('тест')
    if is_test:
        if len(_OPTION.findall(st)) < 2:
            flags.append('тест_без_вариантов')
        if not (r.get('answer') or '').strip() and not (r.get('solution_md') or '').strip():
            flags.append('тест_без_ключа')
    elif event_has_solutions and not (r.get('solution_md') or '').strip() \
            and not (r.get('criteria_md') or '').strip():
        flags.append('нет_решения')
    for f in (r.get('figures') or []) + (r.get('solution_figures') or []):
        if f.get('flag'):
            flags.append('рисунок_' + f['flag'])
    if r.get('needs_eyes'):
        flags.append('страница_на_глаза')
    return sorted(set(flags))


def run_check(cmd, opts):
    dz = cmd.digitized
    rows = digitize.read_jsonl(os.path.join(dz, 'reference_problems_v1.jsonl'))
    files = {e['event_id']: e for e in digitize.read_jsonl(os.path.join(dz, 'events_files.jsonl'))}
    katex_path = os.path.join(dz, 'katex_v1.json')
    katex = json.load(open(katex_path, encoding='utf-8')) if os.path.isfile(katex_path) else {}
    bad_katex = {k for k, v in (katex.get('by_key') or {}).items() if v}
    out, counts = [], Counter()
    for r in rows:
        ev = files.get(r['event_id'], {})
        has_sol = bool(ev.get('solution_files') or ev.get('criteria_files')) or any(
            f.get('source_kind') == 'tasks+solutions' for f in ev.get('task_files') or [])
        flags = task_flags(r, has_sol)
        key = f"{r['event_id']}|{r['number']}|{r.get('task_variant', '')}"
        if key in bad_katex:
            flags.append('katex')
        r['check_flags'] = flags
        counts.update(flags)
        out.append(r)
    keys = Counter((r['event_id'], r['number'], r.get('task_variant', '')) for r in out)
    digitize.write_jsonl(os.path.join(dz, 'reference_problems_v1.jsonl'), out)
    res = {'tasks': len(out), 'with_flags': sum(1 for r in out if r['check_flags']),
           'flags': dict(counts), 'keys_unique': all(v == 1 for v in keys.values()),
           'katex_errors': katex.get('errors'), 'katex_fields': katex.get('fields'),
           'by_stage_season': _by_stage_season(out)}
    with open(os.path.join(dz, 'check_v1.json'), 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    cmd._say(json.dumps({k: v for k, v in res.items() if k != 'by_stage_season'},
                        ensure_ascii=False))


def _by_stage_season(rows):
    c = defaultdict(Counter)
    for r in rows:
        c[r.get('stage')][r.get('academic_year')] += 1
    return {k: dict(sorted(v.items())) for k, v in c.items()}


# ── review_v1.html ──────────────────────────────────────────────────────

def _page_png(dz, ref):
    """«путь#pN» → относительный путь к PNG страницы по индексу рендера."""
    return ref


def run_review(cmd, opts):
    dz = cmd.digitized
    rows = [r for r in digitize.read_jsonl(os.path.join(dz, 'reference_problems_v1.jsonl'))
            if r.get('check_flags')]
    index = {r['pdf']: r['page_dir'] for r in digitize.read_jsonl(
        os.path.join(dz, 'render_index.jsonl'))}
    parts = ['<!doctype html><meta charset="utf-8"><title>ВсОШ v1 — на проверку</title>',
             '<style>body{font:14px/1.45 system-ui;margin:16px;background:#f6f5f2}'
             '.t{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;'
             'background:#fff;border:1px solid #ddd;margin:0 0 18px;padding:10px}'
             '.t img{max-width:100%;border:1px solid #ccc;margin-bottom:6px}'
             'pre{white-space:pre-wrap;font:13px/1.4 ui-monospace,Consolas}'
             '.f{color:#a40;font-weight:600}h2{font-size:15px;margin:0 0 6px}</style>',
             f'<h1>ВсОШ v1 — только нерешённое: {len(rows)} заданий</h1>',
             '<p>Слева — страницы PDF, справа — расшифровка. Флаги — что насторожило проверку.</p>']
    for r in rows[:3000]:
        imgs = []
        for ref in (r.get('source_pages') or [])[:3] + (r.get('solution_pages') or [])[:2]:
            pdf, _, page = ref.rpartition('#p')
            pd = index.get(pdf)
            if pd:
                imgs.append(f'<img loading="lazy" src="{html.escape(pd)}/p{page}.png">')
        figs = ''.join(f'<img loading="lazy" src="{html.escape(f["path"])}">'
                       for f in (r.get('figures') or []))
        parts.append(
            '<div class="t"><div>' + ''.join(dict.fromkeys(imgs)) + '</div><div>'
            f'<h2>{html.escape(r["event_id"])} · № {html.escape(str(r["number"]))}</h2>'
            f'<div class="f">{html.escape(", ".join(r["check_flags"]))}</div>'
            f'<pre>{html.escape(r.get("statement_md") or "")}</pre>'
            + (f'<b>Решение</b><pre>{html.escape(r.get("solution_md") or "")}</pre>'
               if r.get('solution_md') else '')
            + (f'<b>Ответ</b><pre>{html.escape(r.get("answer") or "")}</pre>'
               if r.get('answer') else '')
            + figs + '</div></div>')
    path = os.path.join(dz, 'review_v1.html')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(parts))
    cmd._say(f'review_v1.html: {len(rows)} заданий с флагами → {path}')


# ── сверка с банком (только чтение) ─────────────────────────────────────

def run_bank(cmd, opts):
    from rapidfuzz import fuzz

    from problems.models import OlympiadRef
    from problems.olympiad_official import markup_free_key
    dz = cmd.digitized
    refs = list(OlympiadRef.objects.filter(olympiad_slug='vseros').values(
        'problem_id', 'source_site', 'academic_year', 'year', 'stage', 'grade', 'number',
        'event_id', 'problem__statement'))
    by = defaultdict(Counter)
    for r in refs:
        by[(r['stage'] or '?', r['academic_year'] or str(r['year'] or '?'))][r['source_site']] += 1
    rows = digitize.read_jsonl(os.path.join(dz, 'reference_problems_v1.jsonl'))
    # Сопоставление по тексту внутри (этап, сезон): ключ без разметки.
    bank_by = defaultdict(list)
    for r in refs:
        bank_by[(_stage_bank(r['stage']), _season(r))].append(
            (r['problem_id'], markup_free_key(r['problem__statement'] or '')))
    plan = Counter()
    detail = []
    for t in rows:
        cands = bank_by.get((t['stage'], t['academic_year']), [])
        key = markup_free_key(t.get('statement_md') or '')
        best, pid = 0, None
        for p, k in cands:
            if not k or not key:
                continue
            s = fuzz.token_set_ratio(key[:3000], k[:3000]) / 100
            if s > best:
                best, pid = s, p
        verdict = 'привязать' if best >= 0.9 else 'сомнительно' if best >= 0.7 else 'создать'
        plan[(t['stage'], verdict)] += 1
        detail.append({'event_id': t['event_id'], 'number': t['number'], 'best': round(best, 3),
                       'problem_id': pid, 'verdict': verdict})
    digitize.write_jsonl(os.path.join(dz, 'bank_match_v1.jsonl'), detail)
    lines = ['# ВсОШ: сверка с банком (только чтение)', '',
             f'Привязок `vseros` в банке: {len(refs)} '
             f'({dict(Counter(r["source_site"] for r in refs))}).', '',
             '| этап | сезон | solvehub | ile | official |', '|---|---|---|---|---|']
    for (st, season), c in sorted(by.items()):
        lines.append(f'| {st} | {season} | {c.get("solvehub", 0)} | {c.get("ile", 0)} | '
                     f'{c.get("official", 0)} |')
    lines += ['', '## Сухой план следующей ночи (по тексту, rapidfuzz token_set ≥ 0,90 / 0,70)', '',
              '| этап | создать | привязать | сомнительно |', '|---|---|---|---|']
    for st in ('final', 'regional', 'municipal', 'school', 'invitational'):
        lines.append(f'| {st} | {plan[(st, "создать")]} | {plan[(st, "привязать")]} | '
                     f'{plan[(st, "сомнительно")]} |')
    with open(os.path.join(dz, 'BANK_v1.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    cmd._say('\n'.join(lines))


_BANK_STAGE = {'final': 'final', 'заключительный': 'final', 'regional': 'regional',
               'региональный': 'regional', 'municipal': 'municipal', 'муниципальный': 'municipal',
               'school': 'school', 'школьный': 'school'}


def _stage_bank(stage):
    s = str(stage or '').lower()
    for k, v in _BANK_STAGE.items():
        if k in s:
            return v
    return s


def _season(r):
    ay = str(r.get('academic_year') or '')
    m = re.match(r'(\d{4})\D+(\d{2,4})', ay)
    if m:
        return f'{m.group(1)}/{m.group(2)[-2:]}'
    if r.get('year'):
        y = int(r['year'])
        return f'{y - 1}/{y % 100:02d}'
    return ''


def run_step(cmd, step, opts):
    return {'check': run_check, 'review': run_review, 'bank': run_bank}[step](cmd, opts)
