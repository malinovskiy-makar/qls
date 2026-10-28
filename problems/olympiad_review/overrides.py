# -*- coding: utf-8 -*-
"""`reference_overrides.jsonl` — решения людей по строкам эталона, которых в банке ещё нет.

Файл лежит в папке аудита олимпиады (`weconomics-data\\olympiads\\<audit_dir>\\`),
дописывается командой `olympiad_review apply`, читается импортом
(`import_olympiad_reference`) и обновлением (`update_olympiad_reference`).
Строка:

    {"ref_key", "action", "fields": {...}, "bank_id", "item_id", "reviewer",
     "comment", "decided_at"}

`action`:

* `edit` — поля задачи (уровень банка: title, statement, parts, solution,
  answer) заменяют собранные из строки эталона;
* `ok` — человек сверил задание с PDF, править нечего;
* `hide` — завести задачу скрытой (текст надо доработать);
* `not_a_task` — не задание, не заводить;
* `link` / `new` — пара «та же задача?»: привязать к `bank_id` / завести новой.

Решение человека сильнее двигателя и судьи-модели; `edit`, `ok`, `link`,
`new` снимают пропуск `needs_eyes` (страницу посмотрел человек). По одному
ключу действует последняя строка файла; поля нескольких `edit` складываются.
"""
from __future__ import annotations

import os

from problems.olympiad_review import common

ACTIONS = ('edit', 'ok', 'hide', 'not_a_task', 'link', 'new')
REVIEWED = ('edit', 'ok', 'link', 'new', 'hide')


def load(path):
    """{ref_key: решение} — последняя строка по ключу; поля `edit` копятся."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    for row in common.read_jsonl(path):
        if row.get('action') not in ACTIONS or not row.get('ref_key'):
            continue
        prev = out.get(row['ref_key'])
        merged = dict(row)
        fields = dict((prev or {}).get('fields') or {})
        fields.update(row.get('fields') or {})
        merged['fields'] = fields
        out[row['ref_key']] = merged
    return out


def apply_fields(built, override):
    """Поля `build_fields` ← правка человека (тот же словарь, изменён на месте)."""
    if not override:
        return built
    fields = override.get('fields') or {}
    for name in common.TEXT_FIELDS:
        if name in fields:
            built[name] = fields[name]
    if 'parts' in fields:
        built['parts'] = [{'label': p['label'], 'statement_md': p.get('statement') or '',
                           'answer': p.get('answer') or '', 'points': None}
                          for p in fields['parts']]
    built.setdefault('notes', []).append(f'правка человека ({override.get("reviewer") or "?"}): '
                                         f'{override.get("action")}')
    return built


def as_import_decision(override):
    """Решение для `import_olympiad_reference --decisions`: link / new / skip или None."""
    if not override:
        return None
    who = f'люди: {override.get("reviewer") or "?"}'
    action = override.get('action')
    if action == 'link' and override.get('bank_id'):
        return {'key': override['ref_key'], 'decision': 'link', 'bank_id': int(override['bank_id']),
                'decided_by': who}
    if action == 'new':
        return {'key': override['ref_key'], 'decision': 'new', 'decided_by': who}
    if action == 'not_a_task':
        return {'key': override['ref_key'], 'decision': 'skip', 'decided_by': who + ' (не задача)'}
    return None


def reviewed(override):
    return bool(override) and override.get('action') in REVIEWED
