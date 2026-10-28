# -*- coding: utf-8 -*-
"""Общее для проверки людьми: форматы, пути, порядок олимпиад, отпечатки полей."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

#: Решения рецензента. `skip` — вернуть в очередь.
DECISIONS = ('ok', 'accept_proposed', 'edit', 'hide', 'not_a_task', 'skip')

#: Поля задачи, которые видит и правит человек (уровень банка, а не эталона).
TEXT_FIELDS = ('title', 'statement', 'solution', 'answer')
FIELDS = TEXT_FIELDS + ('parts',)

#: Ключи позиции общего формата (Q1, Q2 и Q3 пишут и читают одинаково).
ITEM_KEYS = ('item_id', 'source', 'olympiad', 'ref_key', 'problem_id', 'check', 'details',
             'page_images', 'current', 'proposed', 'confidence')

#: Порядок олимпиад в очереди: ВП → МОШ (экономика) → ВсОШ ЗЭ/РЭ → остальное.
OLYMPIAD_RANK = {'vp': 0, 'mosh': 1, 'vseros': 2}
OTHER_RANK = 3

#: Дефекты выборочной приёмки (галочки пакета приёмки).
ACCEPTANCE_DEFECTS = {
    'text_lost': 'потерян текст',
    'table': 'таблица',
    'formula': 'формула',
    'figure': 'рисунок',
    'parts': 'пункты',
    'foreign_solution': 'решение не от этой задачи',
    'options_key': 'варианты / ключ',
    'display': 'отображение',
    'other': 'другое',
}
ACCEPTANCE_SLUGS = ('vp', 'mosh', 'vp-fingram', 'vp-ob', 'mosh-fingram',
                    'mosh-entrepreneurship', 'vseros')
#: Порог приёмки: задач с дефектом меньше 3 на 100.
ACCEPTANCE_THRESHOLD = 0.03

#: Последняя версия эталона олимпиады (относительно `digitized\\` папки аудита).
LATEST_REFERENCE = {
    'vp': 'v7.1/reference_problems_v7.1.jsonl',
    'mosh': 'v7.1/reference_problems_v7.1.jsonl',
    'vp-fingram': 'v3.1/reference_problems_v3.1.jsonl',
    'vp-ob': 'v3.1/reference_problems_v3.1.jsonl',
    'mosh-fingram': 'v3.1/reference_problems_v3.1.jsonl',
    'mosh-entrepreneurship': 'v3.1/reference_problems_v3.1.jsonl',
}

#: Набор P2 (`set` в morning_vN.1.jsonl) → слаг олимпиады.
P2_SETS = {'vp': 'vp', 'mosh': 'mosh', 'vp_fingram': 'vp-fingram', 'vp_business': 'vp-ob',
           'mosh_fingram': 'mosh-fingram', 'mosh_entrepreneurship': 'mosh-entrepreneurship'}

OVERRIDES_NAME = 'reference_overrides.jsonl'


def data_root():
    from django.conf import settings

    from problems.olympiad_audit.digitize import default_data_root
    return Path(default_data_root(settings.BASE_DIR))


def quality_dir(value=None):
    """Папка волны качества (`queues\\`, `packs\\`, `decisions\\`)."""
    if value:
        return Path(value)
    env = os.environ.get('OLYMPIAD_QUALITY_DIR')
    if env:
        return Path(env)
    return data_root().parent / 'quality_20261029'


def audit_dir(slug):
    from problems.olympiad_audit import registry
    return data_root() / registry.get(slug).audit_dir


def overrides_path(slug):
    return audit_dir(slug) / OVERRIDES_NAME


def olympiad_rank(slug, stage=''):
    if slug == 'vseros' and stage not in ('', 'final', 'regional'):
        return OTHER_RANK
    return OLYMPIAD_RANK.get(slug, OTHER_RANK)


def field_sha(value):
    """Отпечаток значения поля (строка или подпункты) — для «задача не менялась с пакета»."""
    return hashlib.sha1(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
                        ).hexdigest()[:12]


def norm_parts(parts):
    """Подпункты к виду карточки: [{label, statement, answer}]."""
    out = []
    for p in parts or []:
        out.append({'label': str(p.get('label') or ''),
                    'statement': p.get('statement') if 'statement' in p else p.get('statement_md', ''),
                    'answer': p.get('answer') or ''})
    return out


def norm_fields(fields):
    """Поля карточки: только известные, подпункты — к общему виду."""
    if fields is None:
        return None
    out = {}
    for name in TEXT_FIELDS:
        if name in fields and fields[name] is not None:
            out[name] = str(fields[name])
    if 'parts' in fields and fields['parts'] is not None:
        out['parts'] = norm_parts(fields['parts'])
    return out


def read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
