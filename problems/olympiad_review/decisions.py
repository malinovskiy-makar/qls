# -*- coding: utf-8 -*-
"""Файлы решений рецензентов: чтение, проверка формата, сведение двух людей.

Файл (кнопка «Скачать решения» пакета):

    {"pack_id", "reviewer", "mode": "review"|"acceptance", "saved", "cards",
     "decisions": [{"item_id", "decision", "edited", "reviewer", "comment", "ts"}, …]}

У приёмки вместо `decision`/`edited` — `defects` (коды `common.ACCEPTANCE_DEFECTS`)
и `no_defects`. Один рецензент мог скачать файл несколько раз — по карточке
действует его последнее решение (`ts`). Два рецензента решили одну карточку
по-разному — спор: позиция остаётся в очереди, обе версии идут в отчёт.
"""
from __future__ import annotations

import json
from collections import defaultdict

from problems.olympiad_review import common


class DecisionError(ValueError):
    pass


def validate(row, mode='review'):
    """Ошибки строки решения (пустой список — строка в порядке)."""
    errors = []
    if not isinstance(row, dict):
        return ['строка решения — не объект']
    if not row.get('item_id'):
        errors.append('нет item_id')
    if not row.get('reviewer'):
        errors.append('нет reviewer')
    if mode == 'acceptance':
        defects = row.get('defects')
        if not isinstance(defects, list) or any(d not in common.ACCEPTANCE_DEFECTS for d in defects):
            errors.append(f'defects: неизвестные коды {defects!r}')
        elif not defects and not row.get('no_defects'):
            errors.append('ни дефектов, ни «дефектов нет»')
        elif defects and row.get('no_defects'):
            errors.append('и дефекты, и «дефектов нет»')
        return errors
    if row.get('decision') not in common.DECISIONS:
        errors.append(f'неизвестное решение {row.get("decision")!r}')
    edited = row.get('edited') or {}
    if not isinstance(edited, dict):
        errors.append('edited — не объект')
    else:
        unknown = set(edited) - set(common.FIELDS)
        if unknown:
            errors.append(f'edited: неизвестные поля {sorted(unknown)}')
        if row.get('decision') == 'edit' and not edited:
            errors.append('решение edit без правки')
        for p in edited.get('parts') or []:
            if not isinstance(p, dict) or 'label' not in p:
                errors.append('edited.parts: пункт без метки')
                break
    return errors


def load_files(paths):
    """[(путь, данные файла)] с проверкой формата; ошибка формата — исключение со списком."""
    out, problems = [], []
    for path in paths:
        with open(path, encoding='utf-8-sig') as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or 'decisions' not in data or not data.get('pack_id'):
            problems.append(f'{path}: не файл решений пакета (нет pack_id / decisions)')
            continue
        mode = data.get('mode') or 'review'
        for n, row in enumerate(data['decisions']):
            for err in validate(row, mode):
                problems.append(f'{path} #{n} {row.get("item_id") if isinstance(row, dict) else ""}: {err}')
        out.append((str(path), data))
    if problems:
        raise DecisionError('\n'.join(problems[:30]))
    return out


def _same(a, b):
    return (a['decision'], json.dumps(a.get('edited') or {}, sort_keys=True, ensure_ascii=False)) == \
        (b['decision'], json.dumps(b.get('edited') or {}, sort_keys=True, ensure_ascii=False))


def merge(files):
    """{(pack_id, item_id): решение} и список споров.

    Внутри рецензента — последнее по `ts`; `skip` одного при решении другого не
    спор (решение другого в силе); разные решения двух людей — спор."""
    per = defaultdict(dict)          # (pack, item) → {reviewer: row}
    for _path, data in files:
        for row in data['decisions']:
            row = dict(row, pack_id=data['pack_id'], mode=data.get('mode') or 'review')
            key = (data['pack_id'], row['item_id'])
            prev = per[key].get(row['reviewer'])
            if prev is None or (row.get('ts') or '') >= (prev.get('ts') or ''):
                per[key][row['reviewer']] = row
    # Одна карточка могла уйти в два пакета (после «пропустить») — сводим по item_id.
    by_item = defaultdict(list)
    for (pack_id, item_id), rows in per.items():
        by_item[item_id].extend(rows.values())
    chosen, disputes = {}, []
    for item_id, rows in by_item.items():
        if rows[0]['mode'] == 'acceptance':
            for row in rows:
                chosen[(row['pack_id'], item_id, row['reviewer'])] = row
            continue
        real = [r for r in rows if r['decision'] != 'skip']
        if not real:
            last = max(rows, key=lambda r: r.get('ts') or '')
            chosen[(last['pack_id'], item_id)] = last
            continue
        if all(_same(real[0], r) for r in real[1:]):
            chosen[(real[0]['pack_id'], item_id)] = real[0]
            continue
        disputes.append({'item_id': item_id, 'versions': real})
    return chosen, disputes
