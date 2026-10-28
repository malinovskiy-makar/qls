# -*- coding: utf-8 -*-
"""Карточки стандарта из строк эталонных файлов (уровень «б»).

Наборы — последние версии ночи 28→29.10: ВП и МОШ v7.1, четыре набора
финграмотности и бизнеса v3.1, ВсОШ v1. Папки берутся из реестра
(`registry.REGISTRY[слаг].audit_dir`), файлы только читаются.
"""
from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field

from problems.olympiad_audit.claude_eyes import task_key
from problems.olympiad_audit.reference_import import (
    TYPE_BOOLEAN, TYPE_MULTI_CHOICE, TYPE_SHORT, TYPE_SINGLE, is_test_row,
    load_url_map, test_fields,
)
from problems.olympiad_audit.registry import REGISTRY
from problems.olympiad_contour.standard import SCAN_LAYER_BELOW, text_points

DATA_ROOT = r'C:\Users\shipu\weconomics-data\olympiads'
CRITERIA_SUSPECT = r'C:\Users\shipu\weconomics-data\ai_exam\v1\criteria_mismatch_keys.json'

#: слаг → (путь к jsonl от папки digitized, версия)
SETS = {
    'vp': ('v7.1/reference_problems_v7.1.jsonl', 'v7.1'),
    'mosh': ('v7.1/reference_problems_v7.1.jsonl', 'v7.1'),
    'vp-fingram': ('v3.1/reference_problems_v3.1.jsonl', 'v3.1'),
    'vp-ob': ('v3.1/reference_problems_v3.1.jsonl', 'v3.1'),
    'mosh-fingram': ('v3.1/reference_problems_v3.1.jsonl', 'v3.1'),
    'mosh-entrepreneurship': ('v3.1/reference_problems_v3.1.jsonl', 'v3.1'),
    'vseros': ('reference_problems_v1.jsonl', 'v1'),
}

#: флаги вырезки, которые означают «перевырезано Claude» — это не дефект
FIGURE_FLAGS_OK = {'', 'claude', 'claude_recheck'}
_OPTION_KEY = re.compile(r'^\s*[(]?[а-еa-e1-6][).]?(?:\s*[,;и]\s*[(]?[а-еa-e1-6][).]?)*\s*\.?\s*$', re.IGNORECASE)


@dataclass
class RefSet:
    slug: str
    digitized: str          # папка, от которой идут page_dir и пути рисунков
    root: str               # папка, от которой идут source_file / source_pages
    path: str
    version: str
    rows: list
    pages: dict             # «файл#pN» → page_dir/pN (без расширения), абсолютный
    urls: object            # basename файла → (адрес, official)
    rejected: dict = field(default_factory=dict)   # basename рисунка → причина


def digitized_dir(slug, data_root=DATA_ROOT):
    audit = REGISTRY[slug].audit_dir
    if slug == 'vseros':
        return os.path.join(data_root, audit, 'digitized', 'v1')
    return os.path.join(data_root, audit, 'digitized')


def _read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _pages_p2(digitized):
    out = {}
    for item in _read_jsonl(os.path.join(digitized, 'pages_manifest.jsonl')):
        out['%s#p%d' % (item['file'], item['page'])] = os.path.join(
            digitized, item['page_dir'], 'p%d' % item['page'])
    return out


class _VsoshPages(dict):
    """«файл#pN» → page_dir/pN; файл — путь в raw или converted (render_index)."""

    def __init__(self, digitized):
        super().__init__()
        self.dirs = {}
        self.urls = {}
        for item in _read_jsonl(os.path.join(digitized, 'render_index.jsonl')):
            for key in (item.get('path'), item.get('pdf')):
                if key:
                    self.dirs[key] = os.path.join(digitized, item['page_dir'])
                    self.urls[os.path.basename(key)] = item.get('url') or ''

    def get(self, ref, default=None):
        name, _, page = ref.rpartition('#p')
        base = self.dirs.get(name)
        if not base or not page.isdigit():
            return default
        return os.path.join(base, 'p%s' % page)


class _VsoshUrls(dict):
    def __init__(self, pages, hosts):
        super().__init__()
        from problems.olympiad_audit.reference_import import _host_official
        for name, url in pages.urls.items():
            self[name] = (url, _host_official(url, hosts) if url else False)


def _rejected(digitized):
    out = {}
    for path in glob.glob(os.path.join(digitized, '**', 'figures_rejected*.txt'), recursive=True):
        with open(path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                name, _, why = line.strip().partition('#')
                name = name.strip()
                if name:
                    out[os.path.basename(name)] = why.strip() or os.path.basename(path)
    return out


def load_set(slug, data_root=DATA_ROOT):
    rel, version = SETS[slug]
    digitized = digitized_dir(slug, data_root)
    path = os.path.join(digitized, rel)
    rows = _read_jsonl(path)
    hosts = REGISTRY[slug].official_hosts
    if slug == 'vseros':
        pages = _VsoshPages(digitized)
        urls = _VsoshUrls(pages, hosts)
        root = os.path.dirname(os.path.dirname(digitized))
    else:
        pages = _pages_p2(digitized)
        urls = load_url_map(os.path.dirname(digitized), hosts)
        root = os.path.dirname(digitized)
    return RefSet(slug, digitized, root, path, version, rows, pages, urls, _rejected(digitized))


def load_suspect(path=CRITERIA_SUSPECT):
    """Ключи «event:number:variant» с критериями от другой задачи (P4)."""
    if not os.path.isfile(path):
        return set()
    with open(path, encoding='utf-8') as handle:
        return set(json.load(handle))


# ── Слой PDF и картинки страниц ──────────────────────────────────────────

def page_layer(refset, refs):
    """{text, scan, pngs} по страницам: скан — каждая страница со слоем < 200."""
    texts, pngs, scans = [], [], 0
    for ref in refs or []:
        base = refset.pages.get(ref)
        if not base:
            continue
        if os.path.isfile(base + '.png'):
            pngs.append(base + '.png')
        text = ''
        if os.path.isfile(base + '.txt'):
            with open(base + '.txt', encoding='utf-8', errors='replace') as handle:
                text = handle.read()
        if len(text.strip()) < SCAN_LAYER_BELOW:
            scans += 1
        else:
            texts.append(text)
    if not pngs and not texts:
        return None
    return {'text': '\n'.join(texts), 'scan': not texts, 'pngs': pngs, 'scan_pages': scans}


def figure_fact(path, name, field_name, flag='', caption='', rejected=''):
    fact = {'name': name, 'path': path, 'field': field_name, 'exists': os.path.isfile(path),
            'size': 0, 'opens': False, 'rejected': rejected,
            'flag': '' if flag in FIGURE_FLAGS_OK else flag,
            'table_ok': 'намеренно' in (caption or '').lower()}
    if fact['exists']:
        fact['size'] = os.path.getsize(path)
        fact['opens'] = image_opens_path(path) if fact['size'] else False
    return fact


def image_opens_path(path):
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:  # noqa: BLE001 — любой отказ PIL = картинка не открывается
        return False


# ── Строка → карточка ────────────────────────────────────────────────────

def test_of(row):
    statement, kind, parts, note = test_fields(row.get('statement_md') or '', row.get('answer') or '')
    key = (row.get('answer') or '').strip()
    options = [{'label': p['label'], 'text': p['statement_md'], 'correct': p['answer'] == 'верно'}
               for p in parts]
    name = {TYPE_SINGLE: 'single', TYPE_MULTI_CHOICE: 'multi', TYPE_BOOLEAN: 'boolean',
            TYPE_SHORT: 'short'}.get(kind, 'single')
    if name == 'short' and key and _OPTION_KEY.match(key):
        name, note = 'broken', 'ключ — метка варианта («%s»), а варианты не разобраны: %s' % (key[:20], note)
    if name == 'short' and not key and len(row.get('parts') or []) >= 2:
        name, note = 'broken', 'пункты есть, варианты не разобраны: %s' % note
    return {'kind': name, 'options': options, 'key': key, 'why': note, 'stem': statement}


def card_of(refset, row, suspect=frozenset()):
    key = task_key(row)
    is_test = is_test_row(row)
    parts = [] if is_test else [
        {'label': p.get('label') or '', 'text': p.get('text') or '',
         'points': text_points(p.get('text')), 'answer': ''}
        for p in row.get('parts') or []]
    figures = []
    for field_name, rows_key in (('statement', 'figures'), ('solution', 'solution_figures')):
        for fig in row.get(rows_key) or []:
            path = os.path.join(refset.digitized, fig.get('path') or '')
            name = os.path.basename(fig.get('path') or '')
            figures.append(figure_fact(path, name, field_name, fig.get('flag') or '',
                                       fig.get('caption') or '', refset.rejected.get(name, '')))
    src = (row.get('source_file') or [''])[0]
    url, official = refset.urls.get(os.path.basename(src), ('', False)) or ('', False)
    grade = str(row.get('grade') or '')
    if not grade and '-all-' in str(row.get('event_id')):
        grade = 'все'
    suspect_key = '%s:%s:%s' % (row['event_id'], row['number'], row.get('task_variant') or '')
    layer = page_layer(refset, row.get('source_pages'))
    return {
        'level': 'ref',
        'olympiad': row.get('olympiad_slug') or refset.slug,
        'ref_key': key,
        'problem_id': None,
        'event_id': row['event_id'],
        'number': row['number'],
        'title': row.get('title') or '',
        'statement': row.get('statement_md') or '',
        'solution': row.get('solution_md') or '',
        'answer': row.get('answer') or '',
        'criteria': row.get('criteria_md') or '',
        'parts': parts,
        'test': test_of(row) if is_test else None,
        'max_score': row.get('max_score'),
        'figures': figures,
        'figure_markers_missing': [],
        'figure_orphans': [],
        'tables_expected': row.get('tables') or 0,
        'layer': layer,
        'numbers_ok': row.get('numbers_ok'),
        'meta': {'season': row.get('academic_year') or row.get('year') or '',
                 'stage': row.get('stage') or '', 'grade': grade, 'number': row.get('number') or '',
                 'pdf_url': url, 'pdf_official': bool(official) if url else None},
        'reference_suspect': suspect_key in suspect,
        'solution_expected': bool(row.get('solution_pages')),
        'section': row.get('section_md') or '',
        'visible': None,
        'page_images': (layer or {}).get('pngs', []) + [
            p for p in ((page_layer(refset, row.get('solution_pages')) or {}).get('pngs') or [])],
        'set_version': refset.version,
    }


def load_all(data_root=DATA_ROOT, slugs=None):
    """{слаг: RefSet} и [карточки] по всем наборам."""
    suspect = load_suspect()
    sets, cards = {}, []
    for slug in slugs or SETS:
        refset = load_set(slug, data_root)
        sets[slug] = refset
        cards.extend(card_of(refset, row, suspect) for row in refset.rows)
    return sets, cards

