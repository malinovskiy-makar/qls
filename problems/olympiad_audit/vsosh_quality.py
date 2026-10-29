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
#: Вариант ответа теста: пункт Markdown-списка («- хлеб», «- a. …», «- 1) …»)
#: или строка с меткой «а)», «A.», «1)». Простой список без букв — тоже
#: варианты: так Claude переписывает тесты из веб-форм (28.10).
_OPTION = re.compile(r'(?m)^\s*(?:[-*+]\s+|\(?[а-еa-eА-ЕA-E][.)]\s+|[1-9][.)]\s+)\S')

#: Флаги-факты о источнике, не дефекты оцифровки: в счёт «с флагами» и в
#: review_v1.html не идут.
INFO_FLAGS = {'ключа_нет_в_источнике'}


_NUM = re.compile(r'(?<![\w.,])\d{2,}(?:[.,]\d+)?')


_THOUSANDS = re.compile('(?<=[0-9])[   ](?=[0-9]{3}(?![0-9]))')


def _nums(text):
    """Числа от двух знаков; «2 040» = «2040», «0,5» = «0.5»."""
    return {m.replace(',', '.') for m in _NUM.findall(_THOUSANDS.sub('', text or ''))}


def numbers_not_on_page(statement, layers, extra=()):
    """Числа (от двух знаков) из нашего условия, которых нет в текстовом слое
    его страниц и в `extra` (остальные файлы комплекта). Пустой слой своих
    страниц (скан) — проверка не делается (None)."""
    layer = '\n'.join(layers)
    if len(layer.strip()) < 80:
        return None
    return sorted(_nums(statement) - _nums(layer) - _nums('\n'.join(extra)))


def task_flags(r, event_has_solutions, layers=None, extra_layers=()):
    flags = list(r.get('flags') or [])
    st = r.get('statement_md') or ''
    if not st.strip():
        flags.append('пустое_условие')
    if r.get('layer_ratio') is not None and r['layer_ratio'] < 0.9:
        flags.append('расходится_со_слоем')
    if len(_LIST_MARK.findall(st)) >= 2 and not r.get('parts'):
        flags.append('пункты_не_разобраны')
    is_test = str(r.get('number', '')).startswith('тест')
    if is_test:
        if len(_OPTION.findall(st)) < 2:
            flags.append('тест_без_вариантов')
        if not (r.get('answer') or '').strip() and not (r.get('solution_md') or '').strip():
            # Нет файла ответов в источнике — факт покрытия, не брак расшифровки.
            flags.append('тест_без_ключа' if event_has_solutions else 'ключа_нет_в_источнике')
    elif event_has_solutions and not (r.get('solution_md') or '').strip() \
            and not (r.get('criteria_md') or '').strip():
        flags.append('нет_решения')
    for f in (r.get('figures') or []) + (r.get('solution_figures') or []):
        if f.get('flag'):
            flags.append('рисунок_' + f['flag'])
    if layers is not None:
        missing = numbers_not_on_page(st, layers, extra_layers)
        if missing:
            flags.append('числа_не_со_страницы')
            r['numbers_not_on_page'] = missing[:20]
        elif missing is None and r.get('needs_eyes'):
            flags.append('скан_на_глаза')
    return sorted(set(flags))


def page_layers(dz, index, refs):
    r"""Текстовый слой страниц «файл#pN» из `pages\<sha16>\pN.txt`."""
    out = []
    for ref in refs or []:
        pdf, _, page = ref.rpartition('#p')
        pd = index.get(pdf)
        path = os.path.join(dz, pd, f'p{page}.txt') if pd else ''
        if path and os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                out.append(fh.read())
    return out


def figure_eyes(path):
    """Решения глаз по контактным листам вырезок: путь рисунка → флаг
    (`плохая_вырезка`, `лишний_текст`). Файл переживает пересборку."""
    if not os.path.isfile(path):
        return {}
    out = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            cells = line.rstrip('\n').split('\t')
            if len(cells) >= 2 and not line.startswith('#'):
                out[cells[0]] = cells[1]
    return out


def event_layers(dz, ev):
    """Текстовый слой всех страниц файлов комплекта: инструкция раздела
    приходит в условие со страниц других файлов (файл ответов), её числа —
    не выдумка модели."""
    out = []
    for key in ('task_files', 'solution_files', 'criteria_files'):
        for f in ev.get(key) or []:
            for p in range(1, int(f.get('pages') or 0) + 1):
                path = os.path.join(dz, f['page_dir'], f'p{p}.txt')
                if os.path.isfile(path):
                    with open(path, encoding='utf-8') as fh:
                        out.append(fh.read())
    return out


def run_check(cmd, opts):
    dz = cmd.digitized
    rows = digitize.read_jsonl(os.path.join(dz, 'reference_problems_v1.jsonl'))
    files = {e['event_id']: e for e in digitize.read_jsonl(os.path.join(dz, 'events_files.jsonl'))}
    katex_path = os.path.join(dz, 'katex_v1.json')
    katex = json.load(open(katex_path, encoding='utf-8')) if os.path.isfile(katex_path) else {}
    bad_katex = {k for k, v in (katex.get('by_key') or {}).items() if v}
    index = {x['pdf']: x['page_dir'] for x in digitize.read_jsonl(
        os.path.join(dz, 'render_index.jsonl'))}
    eyes = figure_eyes(os.path.join(dz, 'figure_flags_eyes.tsv'))
    out, counts = [], Counter()
    for r in rows:
        for f in (r.get('figures') or []) + (r.get('solution_figures') or []):
            if f.get('path') in eyes:
                f['flag'] = eyes[f['path']]
        ev = files.get(r['event_id'], {})
        has_sol = bool(ev.get('solution_files') or ev.get('criteria_files')) or any(
            f.get('source_kind') == 'tasks+solutions' for f in ev.get('task_files') or [])
        flags = task_flags(r, has_sol, page_layers(dz, index, r.get('source_pages')),
                           event_layers(dz, ev))
        key = f"{r['event_id']}|{r['number']}|{r.get('task_variant', '')}"
        if key in bad_katex:
            flags.append('katex')
        r['check_flags'] = flags
        counts.update(flags)
        out.append(r)
    keys = Counter((r['event_id'], r['number'], r.get('task_variant', '')) for r in out)
    digitize.write_jsonl(os.path.join(dz, 'reference_problems_v1.jsonl'), out)
    res = {'tasks': len(out),
           'with_flags': sum(1 for r in out if set(r['check_flags']) - INFO_FLAGS),
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
            if set(r.get('check_flags') or []) - INFO_FLAGS]
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
    # v2 (сессия Q2): свой файл эталона и свои имена отчёта — v1 не перезаписывается.
    ref_file = opts.get('ref_file') or os.path.join(dz, 'reference_problems_v1.jsonl')
    out_dir, tag = opts.get('out_dir') or dz, opts.get('tag') or 'v1'
    refs = list(OlympiadRef.objects.filter(olympiad_slug='vseros').values(
        'problem_id', 'source_site', 'academic_year', 'year', 'stage', 'grade', 'number',
        'event_id', 'problem__statement'))
    by = defaultdict(Counter)
    for r in refs:
        by[(r['stage'] or '?', r['academic_year'] or str(r['year'] or '?'))][r['source_site']] += 1
    rows = digitize.read_jsonl(ref_file)
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
    digitize.write_jsonl(os.path.join(out_dir, f'bank_match_{tag}.jsonl'), detail)
    lines = [f'# ВсОШ {tag}: сверка с банком (только чтение)', '',
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
    with open(os.path.join(out_dir, f'BANK_{tag}.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    cmd._say('\n'.join(lines))
    return plan


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
    if step == 'ile':
        from problems.olympiad_audit import vsosh_ile
        return vsosh_ile.run_ile(cmd, opts)
    return {'check': run_check, 'review': run_review, 'bank': run_bank}[step](cmd, opts)
