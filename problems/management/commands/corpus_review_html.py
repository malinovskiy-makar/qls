# -*- coding: utf-8 -*-
"""Собрать сэмплы «было -> стало» по всем 6 источникам corpus_converter и
сохранить как один самодостаточный HTML-файл для визуального ревью
владельцем (reports/corpus_converter_scaleup/review_samples.html).

READ-ONLY, как corpus_scaleup_*.py. Ничего не создаётся и не изменяется в
базе, ``content_format`` нигде не читается и не пишется — конвертер сам по
себе его не касается.

Сэмплы собираются ТЕМ ЖЕ кодом и с тем же random.seed(20260826), что и
report.md (corpus_scaleup_legacy/solvehub/lesh) — переиспользована точная
логика выборки, а не написана заново, чтобы сэмплы двух артефактов
совпадали."""
import base64
import glob
import hashlib
import html
import json
import os
import random
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.criteria import parse_solvehub_criteria
from problems.corpus_converter.lesh import parse_z_blocks, interpret_z_args
from problems.models import Problem, ProblemPart, Rubric, FileAsset
from problems.rendering import render_markdown

SAMPLE_SIZE = 40
MIN_APPROVED = 20
MIN_WITH_STRUCTURE = 14
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'

LEGACY_SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}
SOURCE_ORDER = ['archive3', 'matek', 'lsh2025', 'reshalki', 'solvehub', 'lesh']
SOURCE_LABELS = {
    **{slug: name for slug, (_, name) in LEGACY_SOURCES.items()},
    'solvehub': 'SolveHub (кандидат, НЕ в базе)',
    'lesh': 'ЛЭШ_2026_Гамма (кандидат, НЕ в базе)',
}

SOLVEHUB_DIR = os.path.join(os.path.dirname(settings.BASE_DIR), 'weconomics-data', 'solvehub')
LESH_DIR = os.path.join(
    settings.BASE_DIR, 'materials', 'corpus_sources', 'lesh_2026_gamma', 'ЛЭШ_2026__Гамма',
)
EXCLUDED_DIR_PARTS = ('misc',)
EXCLUDED_PATH_SUBSTRINGS = ('Пример и шаблон', 'качи.tex')

OUT_PATH = os.path.join(
    settings.BASE_DIR, 'reports', 'corpus_converter_scaleup', 'review_samples.html',
)


# ---------------------------------------------------------------------------
# Сбор сэмплов — легаси-семейство (Archive3/МатЭк/ЛШ2025/Решалки)
# ---------------------------------------------------------------------------

def _build_legacy_sample(problem, result, existing_parts):
    raw_sections = [('Условие', problem.statement)]
    if existing_parts:
        raw_sections.append((
            'Части (было)',
            '\n'.join(f'{label}) {text}' for label, text in existing_parts),
        ))
    if problem.answer:
        raw_sections.append(('Ответ', problem.answer))
    if problem.solution:
        raw_sections.append(('Решение', problem.solution))

    converted_sections = [('Условие', result['statement_md'])]
    for part in result['parts']:
        converted_sections.append((f"Часть {part['label']}", part['statement_md']))
    if result['answer_md']:
        converted_sections.append(('Ответ', result['answer_md']))
    if result['solution_md']:
        converted_sections.append(('Решение', result['solution_md']))

    return {
        'source_id': str(problem.id),
        'label': f'human_review={problem.human_review or "не смотрели"}',
        'raw_sections': raw_sections,
        'converted_sections': converted_sections,
        'images': result['images'],
        'warnings': list(result['warnings']),
        'complex_table': result['complex_table'],
    }


def _collect_legacy(slug):
    source_id, _ = LEGACY_SOURCES[slug]
    qs = (
        Problem.objects.filter(source_references__source_id=source_id)
        .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
        .distinct()
        .prefetch_related('parts')
    )
    processed = []
    for problem in qs.iterator(chunk_size=500):
        existing_parts = [(part.label, part.statement) for part in problem.parts.all()]
        result = convert_problem(
            statement=problem.statement,
            answer=problem.answer,
            solution=problem.solution,
            existing_parts=existing_parts,
        )
        processed.append((problem, result, existing_parts))

    approved = [item for item in processed if item[0].human_review == Problem.HumanReview.APPROVED]
    with_structure = [
        item for item in processed
        if item[1]['parts'] or item[1]['images'] or item[1]['complex_table']
    ]

    random.seed(20260826)
    sample = {}
    for item in (random.sample(approved, min(MIN_APPROVED, len(approved))) if approved else []):
        sample[item[0].id] = item
    remaining_structure = [item for item in with_structure if item[0].id not in sample]
    for item in (
        random.sample(remaining_structure, min(MIN_WITH_STRUCTURE, len(remaining_structure)))
        if remaining_structure else []
    ):
        sample[item[0].id] = item
    remaining_pool = [item for item in processed if item[0].id not in sample]
    if len(sample) < SAMPLE_SIZE and remaining_pool:
        for item in random.sample(remaining_pool, min(SAMPLE_SIZE - len(sample), len(remaining_pool))):
            sample[item[0].id] = item

    ordered = sorted(sample.values(), key=lambda item: item[0].id)[:SAMPLE_SIZE]
    built = [_build_legacy_sample(problem, result, parts) for problem, result, parts in ordered]
    return built, len(processed), processed


# ---------------------------------------------------------------------------
# Сбор сэмплов — SolveHub (INSERT, с диска)
# ---------------------------------------------------------------------------

def _load_solvehub_problems():
    problems_dir = os.path.join(SOLVEHUB_DIR, 'problems')
    for path in sorted(glob.glob(os.path.join(problems_dir, '*.json'))):
        with open(path, encoding='utf-8') as f:
            yield json.load(f)


def _classify_solvehub_images(images, image_map, local_files):
    classified = []
    for img in images:
        ref = img['original_ref']
        if img['kind'] != 'markdown':
            classified.append({**img, 'status': 'не-markdown (includegraphics/url)'})
            continue
        local_name = image_map.get(ref)
        if local_name is None:
            classified.append({**img, 'status': 'битая ссылка — URL не в image_map'})
        elif local_name not in local_files:
            classified.append({**img, 'status': 'в image_map, но файла нет на диске'})
        else:
            classified.append({**img, 'status': f'resolved -> images/{local_name}'})
    return classified


def _build_solvehub_sample(raw, result, criteria_result, images, is_dup):
    raw_sections = [
        ('Название', raw.get('title', '')),
        ('Условие (md)', raw.get('md', '')),
        ('answer_md (сырой)', raw.get('answer_md', '')),
    ]
    converted_sections = [('Условие', result['statement_md'])]
    for part in result['parts']:
        converted_sections.append((f"Часть {part['label']}", part['statement_md']))
    if result['solution_md']:
        converted_sections.append(('Решение (answer_md конвертированный)', result['solution_md']))
    for criterion in criteria_result['criteria']:
        points = criterion['max_points']
        points_label = f'{points} балл(ов)' if points is not None else 'баллы не распознаны'
        converted_sections.append((f'Критерий ({points_label})', criterion['description']))

    warnings = list(result['warnings']) + list(criteria_result['warnings'])
    if is_dup:
        warnings.append('ТОЧНОЕ совпадение content_hash с банком — вероятный дубль')

    return {
        'source_id': str(raw['id']),
        'label': 'кандидат, НЕ в базе' + (' · вероятный дубль' if is_dup else ''),
        'raw_sections': raw_sections,
        'converted_sections': converted_sections,
        'images': images,
        'warnings': warnings,
        'complex_table': result['complex_table'],
    }


def _collect_solvehub():
    with open(os.path.join(SOLVEHUB_DIR, 'image_map.json'), encoding='utf-8') as f:
        image_map = json.load(f)
    local_files = set(os.listdir(os.path.join(SOLVEHUB_DIR, 'images')))

    existing_hashes = set(
        Problem.objects
        .exclude(content_hash='')
        .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
        .values_list('content_hash', flat=True)
    )

    candidates = []
    by_id = {}
    for raw in _load_solvehub_problems():
        statement_md = raw.get('md') or ''
        if not statement_md:
            continue
        answer_md_raw = raw.get('answer_md') or ''
        result = convert_problem(statement=statement_md, answer='', solution=answer_md_raw, existing_parts=None)
        criteria_result = parse_solvehub_criteria(answer_md_raw)
        images = _classify_solvehub_images(result['images'], image_map, local_files)
        content_hash = hashlib.md5(statement_md.encode('utf-8'), usedforsecurity=False).hexdigest()
        is_dup = content_hash in existing_hashes
        item = (raw, result, criteria_result, images, is_dup)
        candidates.append(item)
        by_id[raw['id']] = item

    with_criteria = [c for c in candidates if c[2]['criteria']]
    with_broken_images = [c for c in candidates if any('битая ссылка' in i['status'] for i in c[3])]
    with_tables = [c for c in candidates if c[1]['complex_table']]

    random.seed(20260826)
    sample = []
    for bucket, n in ((with_criteria, 10), (with_broken_images, 10), (with_tables, 8)):
        picks = random.sample(bucket, min(n, len(bucket))) if bucket else []
        for pick in picks:
            if pick not in sample:
                sample.append(pick)
    remaining = [c for c in candidates if c not in sample]
    if len(sample) < SAMPLE_SIZE and remaining:
        sample.extend(random.sample(remaining, min(SAMPLE_SIZE - len(sample), len(remaining))))

    built = [_build_solvehub_sample(*item) for item in sample[:SAMPLE_SIZE]]
    return built, len(candidates), by_id


# ---------------------------------------------------------------------------
# Сбор сэмплов — ЛЭШ Гамма (INSERT, с диска)
# ---------------------------------------------------------------------------

def _iter_lesh_tex_files():
    for path in glob.glob(os.path.join(LESH_DIR, '**', '*.tex'), recursive=True):
        rel = os.path.relpath(path, LESH_DIR)
        parts = rel.split(os.sep)
        if any(p in EXCLUDED_DIR_PARTS for p in parts):
            continue
        if any(sub in rel for sub in EXCLUDED_PATH_SUBSTRINGS):
            continue
        yield path, rel


def _is_lesh_reshalka_file(rel_path):
    return 'решалк' in rel_path.lower()


def _build_lesh_sample(rel, parsed, result, solution_text, is_dup):
    raw_sections = [
        ('Название (\\z)', parsed['name'] or ''),
        ('Условие (сырое)', parsed['statement']),
    ]
    if parsed['subpoints']:
        raw_sections.append((
            'Пункты (сырые)',
            '\n'.join(f'{i + 1}) {sp}' for i, sp in enumerate(parsed['subpoints'])),
        ))
    if solution_text:
        raw_sections.append(('Решение (найдено в Решалках, сырое)', solution_text))

    converted_sections = [('Условие', result['statement_md'])]
    for part in result['parts']:
        converted_sections.append((f"Часть {part['label']}", part['statement_md']))
    if result['solution_md']:
        converted_sections.append(('Решение', result['solution_md']))

    warnings = list(result['warnings'])
    if not solution_text:
        warnings.append('решение не найдено по названию в Решалках')
    if is_dup:
        warnings.append('ТОЧНОЕ совпадение content_hash с банком — вероятный дубль')

    return {
        'source_id': f'{rel} :: {parsed["name"] or "(без названия)"}',
        'label': 'кандидат, НЕ в базе',
        'raw_sections': raw_sections,
        'converted_sections': converted_sections,
        'images': result['images'],
        'warnings': warnings,
        'complex_table': result['complex_table'],
    }


def _collect_lesh():
    existing_hashes = set(
        Problem.objects
        .exclude(content_hash='')
        .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
        .values_list('content_hash', flat=True)
    )

    condition_blocks = []
    solutions_by_name = {}
    for path, rel in _iter_lesh_tex_files():
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
        blocks, _warnings = parse_z_blocks(text)
        is_reshalka = _is_lesh_reshalka_file(rel)
        for block in blocks:
            parsed = interpret_z_args(block)
            if is_reshalka:
                if parsed['name']:
                    solutions_by_name.setdefault(parsed['name'], (rel, parsed))
            else:
                condition_blocks.append((rel, parsed))

    seen_prefixes = set()
    unique_conditions = []
    for rel, parsed in condition_blocks:
        prefix = parsed['statement'][:200]
        if not prefix or prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        unique_conditions.append((rel, parsed))

    candidates = []
    by_name = {}
    for rel, parsed in unique_conditions:
        statement = parsed['statement']
        if not statement:
            continue
        solution_text = ''
        if parsed['name'] and parsed['name'] in solutions_by_name:
            _sol_rel, sol_parsed = solutions_by_name[parsed['name']]
            solution_text = sol_parsed['statement']

        existing_parts = [(str(i + 1), subpoint) for i, subpoint in enumerate(parsed['subpoints'])]
        result = convert_problem(
            statement=statement, answer='', solution=solution_text,
            existing_parts=existing_parts or [],
        )
        content_hash = hashlib.md5(statement.encode('utf-8'), usedforsecurity=False).hexdigest()
        is_dup = content_hash in existing_hashes

        item = (rel, parsed, result, solution_text, is_dup)
        candidates.append(item)
        if parsed['name']:
            by_name[(rel, parsed['name'])] = item

    with_images = [c for c in candidates if c[2]['images']]
    with_solution = [c for c in candidates if c[3]]

    random.seed(20260826)
    sample = []
    for bucket, n in ((with_images, 10), (with_solution, 15)):
        picks = random.sample(bucket, min(n, len(bucket))) if bucket else []
        for pick in picks:
            if pick not in sample:
                sample.append(pick)
    remaining = [c for c in candidates if c not in sample]
    if len(sample) < SAMPLE_SIZE and remaining:
        sample.extend(random.sample(remaining, min(SAMPLE_SIZE - len(sample), len(remaining))))

    built = [_build_lesh_sample(*item) for item in sample[:SAMPLE_SIZE]]
    return built, len(candidates), by_name


# ---------------------------------------------------------------------------
# HTML-рендер
# ---------------------------------------------------------------------------

#: KaTeX кладётся В САМ ФАЙЛ, а не тянется с jsDelivr. Аудит 29.08:
#: при офлайне, CSP или сетевом сбое все 11 808 формул страницы
#: превратились бы в сырой TeX, и проверка показала бы не то, что есть.
#: Плюс версия: вендорный каталог — это ровно 0.16.9, та же, что на
#: боевом показе, а CDN однажды отдаст другую.
#:
#: Шрифты вшиваются как data:-адреса, и только woff2: без них KaTeX
#: считает ширины системным шрифтом, а ширина формулы — это код `OVER`,
#: который мы же и меряем. woff/ttf выбрасываются — их понимает только
#: браузер, которого здесь нет.
_KATEX_DIR = os.path.join(settings.BASE_DIR, 'problems',
                          'review_bundle_assets', 'vendor', 'katex')
_FONT_URL_RE = re.compile(r'url\(fonts/([^)]+)\)')


def _katex_assets():
    """`<style>` и `<script>` вендорного KaTeX 0.16.9 одним куском."""
    with open(os.path.join(_KATEX_DIR, 'katex.min.css'), encoding='utf-8') as fh:
        css = fh.read()

    cache = {}

    def inline(match):
        name = match.group(1)
        if not name.endswith('.woff2'):
            # Ветку woff/ttf убираем целиком вместе с адресом: пусть
            # останется единственный формат, который точно вшит.
            return "url('')"
        if name not in cache:
            with open(os.path.join(_KATEX_DIR, 'fonts', name), 'rb') as fh:
                cache[name] = base64.b64encode(fh.read()).decode('ascii')
        return "url(data:font/woff2;base64,%s)" % cache[name]

    css = _FONT_URL_RE.sub(inline, css)
    parts = ['<style>%s</style>' % css]
    for name in ('katex.min.js', os.path.join('contrib', 'auto-render.min.js')):
        with open(os.path.join(_KATEX_DIR, name), encoding='utf-8') as fh:
            parts.append('<script>%s</script>' % fh.read())
    return '\n'.join(parts)


def html_head():
    """Шапка страницы проверки с вшитым KaTeX."""
    return _HTML_HEAD.replace('__KATEX_ASSETS__', _katex_assets())


#: Копия конфигурации из catalog/templates/catalog/base.html + partial
#: templates/_katex_dollars.html — ТОТ ЖЕ рендерер, что видит ученик на
#: странице задачи. Версия KaTeX и порядок разделителей ($$ раньше $)
#: обязаны совпадать с прод-шаблоном (problems/rendering.py, docstring).
_HTML_HEAD = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ревью конвертера корпуса — 6 источников</title>
__KATEX_ASSETS__
<style>
:root {
  --bg: #f7f7f5; --surface: #ffffff; --border: #ddd; --text: #1a1a1a;
  --muted: #888; --accent: #b5651d; --warn-bg: #fff4e5; --warn-border: #e8a33d;
  --ok-bg: #f0f4f0; --reviewed-bg: #eaf3ff; --reviewed-border: #3b78c2;
}
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
h1 { font-size: 1.4rem; margin-bottom: 4px; }
.subtitle { color: var(--muted); margin-bottom: 16px; font-size: 0.9rem; }
table.summary { border-collapse: collapse; margin-bottom: 16px; background: var(--surface); }
table.summary th, table.summary td { border: 1px solid var(--border); padding: 6px 12px; text-align: right; font-size: 0.9rem; }
table.summary th:first-child, table.summary td:first-child { text-align: left; }
table.summary tr.total { font-weight: bold; background: #f0f0ee; }
#filters { margin-bottom: 20px; }
#filters button { padding: 6px 14px; margin-right: 8px; border: 1px solid var(--border); background: var(--surface); border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
#filters button.active { background: var(--accent); color: white; border-color: var(--accent); }
details.source-section { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 14px; padding: 10px 14px; }
details.reviewed-section { background: var(--reviewed-bg); border: 2px solid var(--reviewed-border); border-radius: 6px; margin-bottom: 20px; padding: 10px 14px; }
summary { cursor: pointer; font-weight: 600; font-size: 1.05rem; padding: 4px 0; }
.sample-card { border: 1px solid var(--border); border-radius: 6px; margin: 12px 0; padding: 10px 12px; background: var(--ok-bg); }
.sample-card.has-warnings { background: var(--warn-bg); border-color: var(--warn-border); border-left: 5px solid var(--warn-border); }
/* opacity НЕ ставим: аудит 29.08 отдельно отметил, что серые
   карточки мешают смотреть корпус глазами. Чистая карточка
   отличается фоном, а не читаемостью. */
.sample-card.no-warnings { background: var(--ok-bg); }
.sample-card.is-reviewed { border-left: 5px solid var(--reviewed-border); }
.sample-header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; }
.sample-id { font-weight: 700; font-family: monospace; }
.sample-label { color: var(--muted); font-size: 0.85rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.78rem; background: #eee; border: 1px solid #ccc; }
.badge.warn { background: #fde2b5; border-color: var(--warn-border); }
.badge.complex-table { background: #ffd6d6; border-color: #d33; }
.badge.reviewed { background: var(--reviewed-border); color: white; border-color: var(--reviewed-border); }
.sample-body { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .sample-body { grid-template-columns: 1fr; } }
.col h4 { margin: 0 0 4px; font-size: 0.8rem; text-transform: uppercase; color: var(--muted); }
.col pre { white-space: pre-wrap; word-break: break-word; font-size: 0.82rem; background: #fafafa; border: 1px solid #eee; border-radius: 4px; padding: 8px; margin: 0 0 8px; }
/* Без max-height: обрезанное до прокрутки условие нельзя
   проверить глазами — а ровно для этого страница и делается. */
.col .converted-block { border: 1px solid #eee; border-radius: 4px; padding: 8px; margin: 0 0 8px; background: #fff; }
/* Те же правила, что на боевой странице задачи
   (catalog/problem_detail.html): широкое прокручивается
   внутри себя, картинка не шире колонки. */
.math-content .katex-display { overflow-x: auto; overflow-y: hidden; }
.math-content table { display: block; width: fit-content; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
.math-content th, .math-content td { padding: 6px 12px; text-align: left; border-bottom: 1px solid #e3e3e3; }
.math-content .problem-figure, .math-content svg { display: block; max-width: 100%; height: auto; }
.col .converted-block p { margin: 0 0 0.6em; }
.images-note, .warnings-note { font-size: 0.82rem; margin-top: 6px; }
.warnings-note ul { margin: 2px 0; padding-left: 18px; }
.hidden { display: none !important; }
</style>
</head>
<body>
"""

_HTML_FOOT_TEMPLATE = """
<script>
// --- _katex_dollars.html, буквально: маскировка \\$ вне формул -------------
var DOLLAR_SENTINEL = '\\uE000';
function findClose(s, from, close) {
  var i = from;
  while (i < s.length) {
    if (s.charAt(i) === '\\\\' && s.charAt(i + 1) === '$') { i += 2; continue; }
    if (s.substr(i, close.length) === close) return i;
    i++;
  }
  return -1;
}
function mathSpanEnd(s, i) {
  var pairs = [['$$', '$$'], ['\\\\[', '\\\\]'], ['\\\\(', '\\\\)'], ['$', '$']];
  for (var k = 0; k < pairs.length; k++) {
    var open = pairs[k][0], close = pairs[k][1];
    if (s.substr(i, open.length) !== open) continue;
    var end = findClose(s, i + open.length, close);
    if (end === -1) continue;
    return end + close.length;
  }
  return i;
}
function maskOutsideMath(s) {
  if (s.indexOf('\\\\$') === -1) return s;
  var out = '', i = 0, n = s.length;
  while (i < n) {
    if (s.charAt(i) === '\\\\' && s.charAt(i + 1) === '$') { out += DOLLAR_SENTINEL; i += 2; continue; }
    var end = mathSpanEnd(s, i);
    if (end > i) { out += s.slice(i, end); i = end; continue; }
    out += s.charAt(i); i++;
  }
  return out;
}
function maskEscapedDollars(root) {
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    if (node.nodeValue.indexOf('\\\\$') !== -1) node.nodeValue = maskOutsideMath(node.nodeValue);
  }
}
function fixCurrencyDollars(root) {
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    var v = node.nodeValue;
    if (v.indexOf(DOLLAR_SENTINEL) !== -1 || v.indexOf('\\\\$') !== -1 ||
        v.indexOf('\\\\_') !== -1 || v.indexOf('\\\\&') !== -1 || v.indexOf('\\\\#') !== -1) {
      node.nodeValue = v.split(DOLLAR_SENTINEL).join('$').split('\\\\$').join('$')
                        .split('\\\\_').join('_').split('\\\\&').join('&')
                        .split('\\\\#').join('#');
    }
  }
}
function initKaTeX() {
  maskEscapedDollars(document.body);
  renderMathInElement(document.body, {
    delimiters: [
      { left: '$$',   right: '$$',   display: true  },
      { left: '$',    right: '$',    display: false },
      { left: '\\\\[',  right: '\\\\]',  display: true  },
      { left: '\\\\(',  right: '\\\\)',  display: false }
    ],
    // В ИНСТРУМЕНТЕ ПРОВЕРКИ ошибка обязана быть видна: с false
    // сломанная формула молча превращается в сырой TeX, и
    // страница выглядит исправной. На боевом показе остаётся
    // false — там ученику незачем видеть красный текст ошибки.
    throwOnError: true,
    errorColor: "#c0392b",
    trust: false
  });
  fixCurrencyDollars(document.body);
}
document.addEventListener('DOMContentLoaded', function () {
  initKaTeX();
});

// --- фильтр «все / только warnings / только проверено ревью» ---------------
(function () {
  var buttons = document.querySelectorAll('#filters button');
  function applyFilter(mode) {
    var cards = document.querySelectorAll('.sample-card');
    cards.forEach(function (card) {
      var show = true;
      if (mode === 'warnings') show = card.dataset.hasWarnings === 'true';
      else if (mode === 'reviewed') show = card.dataset.reviewed === 'true';
      card.classList.toggle('hidden', !show);
    });
    buttons.forEach(function (b) { b.classList.toggle('active', b.dataset.filter === mode); });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () { applyFilter(b.dataset.filter); });
  });
  applyFilter('all');
})();
</script>
</body>
</html>
"""


def _esc(text):
    return html.escape(text or '', quote=False)


def _render_converted_sections(sections):
    parts = []
    for title, text in sections:
        rendered = render_markdown(text)
        parts.append(f'<div class="converted-block"><h4>{_esc(title)}</h4>{rendered}</div>')
    return ''.join(parts)


def _render_raw_sections(sections):
    parts = []
    for title, text in sections:
        parts.append(f'<h4>{_esc(title)}</h4><pre>{_esc(text)}</pre>')
    return ''.join(parts)


def _render_images_note(images):
    if not images:
        return ''
    items = []
    for img in images:
        status = img.get('status', '')
        items.append(f'{_esc(img["kind"])}: {_esc(img["original_ref"])}' + (f' — {_esc(status)}' if status else ''))
    return '<div class="images-note"><strong>Картинки:</strong> ' + '; '.join(items) + '</div>'


def _render_warnings_note(warnings):
    if not warnings:
        return ''
    items = ''.join(f'<li>{_esc(w)}</li>' for w in warnings)
    return f'<div class="warnings-note"><strong>Warnings ({len(warnings)}):</strong><ul>{items}</ul></div>'


def _render_badges(sample):
    badges = []
    if sample['complex_table']:
        badges.append('<span class="badge complex-table">complex_table</span>')
    for w in sample['warnings'][:6]:
        short = w if len(w) <= 70 else w[:67] + '…'
        badges.append(f'<span class="badge warn" title="{_esc(w)}">{_esc(short)}</span>')
    if len(sample['warnings']) > 6:
        badges.append(f'<span class="badge warn">+{len(sample["warnings"]) - 6} ещё</span>')
    return ''.join(badges)


def _render_sample_card(sample, reviewed=False):
    has_warnings = bool(sample['warnings']) or sample['complex_table']
    classes = ['sample-card']
    classes.append('has-warnings' if has_warnings else 'no-warnings')
    if reviewed:
        classes.append('is-reviewed')
    reviewed_badge = '<span class="badge reviewed">проверено ревью</span>' if reviewed else ''
    return f"""
<div class="{' '.join(classes)}" data-has-warnings="{'true' if has_warnings else 'false'}" data-reviewed="{'true' if reviewed else 'false'}">
  <div class="sample-header">
    <span class="sample-id">#{_esc(sample['source_id'])}</span>
    <span class="sample-label">{_esc(sample['label'])}</span>
    {reviewed_badge}
    {_render_badges(sample)}
  </div>
  <div class="sample-body">
    <div class="col raw"><h4 style="text-transform:none;color:inherit;font-weight:700;">Исходник</h4>{_render_raw_sections(sample['raw_sections'])}</div>
    <div class="col converted math-content"><h4 style="text-transform:none;color:inherit;font-weight:700;">Результат конвертера</h4>{_render_converted_sections(sample['converted_sections'])}{_render_images_note(sample['images'])}{_render_warnings_note(sample['warnings'])}</div>
  </div>
</div>
"""


class Command(BaseCommand):
    help = (
        'Read-only: собрать сэмплы по 6 источникам corpus_converter и сохранить '
        'reports/corpus_converter_scaleup/review_samples.html для визуального ревью.'
    )

    def handle(self, *args, **options):
        counts_before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }

        self.stdout.write('Archive3...')
        archive3_samples, archive3_total, archive3_all = _collect_legacy('archive3')
        self.stdout.write('МатЭк...')
        matek_samples, matek_total, _matek_all = _collect_legacy('matek')
        self.stdout.write('ЛШ Олмат 2025...')
        lsh2025_samples, lsh2025_total, _lsh2025_all = _collect_legacy('lsh2025')
        self.stdout.write('Решалки Олмат...')
        reshalki_samples, reshalki_total, _reshalki_all = _collect_legacy('reshalki')
        self.stdout.write('SolveHub...')
        solvehub_samples, solvehub_total, solvehub_by_id = _collect_solvehub()
        self.stdout.write('ЛЭШ Гамма...')
        lesh_samples, lesh_total, lesh_by_name = _collect_lesh()

        samples_by_source = {
            'archive3': archive3_samples,
            'matek': matek_samples,
            'lsh2025': lsh2025_samples,
            'reshalki': reshalki_samples,
            'solvehub': solvehub_samples,
            'lesh': lesh_samples,
        }
        totals_by_source = {
            'archive3': archive3_total, 'matek': matek_total, 'lsh2025': lsh2025_total,
            'reshalki': reshalki_total, 'solvehub': solvehub_total, 'lesh': lesh_total,
        }

        # --- Блок "Проверено ревью" — 3 дефекта, 4 конкретных случая -------
        reviewed_samples = []

        archive3_33817 = next((item for item in archive3_all if item[0].id == 33817), None)
        if archive3_33817 is None:
            raise CommandError('Задача Archive3 #33817 не найдена в базе — проверь source_id/фильтры.')
        problem, result, parts = archive3_33817
        s = _build_legacy_sample(problem, result, parts)
        s['label'] = 'Дефект 1 — голые &-строки без \\begin{tabular} (' + s['label'] + ')'
        reviewed_samples.append(s)

        kurno_key = ('Подборки\\Микроэкономика\\Курно и Штакельберг.tex', 'Вмешательство в модель Курно')
        kurno_key_posix = ('Подборки/Микроэкономика/Курно и Штакельберг.tex', 'Вмешательство в модель Курно')
        kurno_item = lesh_by_name.get(kurno_key) or lesh_by_name.get(kurno_key_posix)
        if kurno_item is None:
            raise CommandError('ЛЭШ «Курно и Штакельберг.tex» / «Вмешательство в модель Курно» не найден.')
        s = _build_lesh_sample(*kurno_item)
        s['label'] = 'Дефект 2 — сырые \\item в subpoints (' + s['label'] + ')'
        reviewed_samples.append(s)

        hotelling_key = ('Подборки\\Микроэкономика\\Хотеллинг.tex', 'Это сложнее, чем вы думаете')
        hotelling_key_posix = ('Подборки/Микроэкономика/Хотеллинг.tex', 'Это сложнее, чем вы думаете')
        hotelling_item = lesh_by_name.get(hotelling_key) or lesh_by_name.get(hotelling_key_posix)
        if hotelling_item is None:
            raise CommandError('ЛЭШ «Хотеллинг.tex» / «Это сложнее, чем вы думаете» не найден.')
        s = _build_lesh_sample(*hotelling_item)
        s['label'] = 'Дефект 2 — сырые \\item в subpoints (' + s['label'] + ')'
        reviewed_samples.append(s)

        solvehub_3498 = solvehub_by_id.get(3498)
        if solvehub_3498 is None:
            raise CommandError('SolveHub #3498 не найден на диске.')
        s = _build_solvehub_sample(*solvehub_3498)
        s['label'] = 'Дефект 3 — парсер критериев терял часть баллов (' + s['label'] + ')'
        reviewed_samples.append(s)

        # --- Сборка HTML -----------------------------------------------------
        html_parts = [html_head()]
        html_parts.append('<h1>Ревью конвертера корпуса — 6 источников</h1>')
        html_parts.append(
            '<div class="subtitle">problems/corpus_converter/, read-only, '
            'reports/corpus_converter_scaleup/report.md — тот же прогон. '
            'Рендер справа — problems.rendering.render_markdown + KaTeX 0.16.9, '
            'как на проде.</div>'
        )

        summary_rows = []
        total_shown = 0
        total_warn = 0
        for slug in SOURCE_ORDER:
            shown = len(samples_by_source[slug])
            warn = sum(1 for s in samples_by_source[slug] if s['warnings'] or s['complex_table'])
            total_shown += shown
            total_warn += warn
            summary_rows.append(
                f'<tr><td>{_esc(SOURCE_LABELS[slug])}</td>'
                f'<td>{totals_by_source[slug]}</td><td>{shown}</td><td>{warn}</td></tr>'
            )
        summary_html = (
            '<table class="summary"><tr><th>Источник</th><th>Всего в источнике</th>'
            '<th>Сэмплов показано</th><th>Из них с warnings</th></tr>'
            + ''.join(summary_rows)
            + f'<tr class="total"><td>Итого</td><td>—</td><td>{total_shown}</td><td>{total_warn}</td></tr>'
            + '</table>'
        )
        html_parts.append(summary_html)

        html_parts.append(
            '<div id="filters">'
            '<button data-filter="all" class="active">Показать все</button>'
            '<button data-filter="warnings">Только с warnings</button>'
            '<button data-filter="reviewed">Только «Проверено ревью»</button>'
            '</div>'
        )

        html_parts.append(
            '<details class="reviewed-section" open><summary>✅ Проверено ревью — '
            f'{len(reviewed_samples)} случая, 3 дефекта (2026-08-26)</summary>'
        )
        for s in reviewed_samples:
            html_parts.append(_render_sample_card(s, reviewed=True))
        html_parts.append('</details>')

        for slug in SOURCE_ORDER:
            samples = samples_by_source[slug]
            warn_count = sum(1 for s in samples if s['warnings'] or s['complex_table'])
            html_parts.append(
                f'<details class="source-section" open data-source="{slug}"><summary>'
                f'{_esc(SOURCE_LABELS[slug])} — {len(samples)} сэмплов, {warn_count} с warnings</summary>'
            )
            for s in samples:
                html_parts.append(_render_sample_card(s, reviewed=False))
            html_parts.append('</details>')

        html_parts.append(_HTML_FOOT_TEMPLATE)

        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            f.write(''.join(html_parts))

        counts_after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }
        if counts_before != counts_after:
            raise CommandError(f'ИНВАРИАНТ НАРУШЕН: было {counts_before}, стало {counts_after}')

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Сэмплов показано: {total_shown} (из них с warnings: {total_warn}), '
            f'плюс {len(reviewed_samples)} в блоке «Проверено ревью». '
            f'Инвариант счётчиков сошёлся. Файл: {OUT_PATH}'
        ))
