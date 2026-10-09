# -*- coding: utf-8 -*-
"""Разбор очереди «на глаза»: ярусы, срочность, выборка контроля, страницы v3.

Очередь — страницы оцифровки со статусом `needs_eyes` (`digitized\\pages\\
<sha16>\\p<N>.json`). Здесь она делится на ярусы по РЕАЛЬНОМУ риску:

* A — текст расходится со слоем, не хватает чисел, судья-скан уже нашёл
  расхождения, сбой формата ответа;
* B — только лишние числа (подписи графиков и т. п.): норма по умолчанию,
  в проверке — только выборка контроля;
* C — плановая выборка сканов (каждая 5-я): так же, только выборка.

Результаты разбора лежат рядом со старыми страницами, не поверх них:
`pages_v3\\<sha16>\\p<N>.json` — «заплатка» страницы (статус судьи или
перечитывания). `PageOverlay` накладывает заплатки на старую запись при
сборке v3; старые `pages\\…\\p<N>.json` не меняются никогда.

Ни одного вызова модели и ни одной записи в базу этот модуль не делает.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
from collections import Counter, defaultdict

from problems.olympiad_audit.assemble import norm_number
from problems.olympiad_audit.transcribe import LAYER_THRESHOLD

TIER_A, TIER_B, TIER_C = 'A', 'B', 'C'

REASON_LAYER = 'расходится со слоем PDF'
REASON_JUDGE = 'судья нашёл расхождения'
REASON_FORMAT = 'сбой формата ответа'

#: Выборка контроля яруса: 5 % страниц, но не меньше 20 (или весь ярус).
CONTROL_SHARE = 0.05
CONTROL_MIN = 20
CONTROL_SEED = 20261009
#: Порог сходства «лучшего совпадения где-либо» в таблице проверки банка.
BANK_FUZZY = 0.85

URGENT_NEW = 'срочная: в банке нет'
URGENT_UPDATE = 'срочная: в банке есть похожая'
NOT_URGENT = 'не срочная'

PLAN_COLUMNS = ['страница', 'файл', 'комплекты', 'ярус', 'причина', 'срочность',
                'задания', 'контроль']


# ── Страницы и заплатки v3 ───────────────────────────────────────────────

def page_key(record):
    return f'{record["page_dir"]}/p{record["page"]}'


def v3_path(digitized, page_dir, page):
    """`pages/<sha16>` → `pages_v3/<sha16>/p<N>.json` (рядом, не поверх)."""
    head, _, tail = page_dir.partition('/')
    return os.path.join(digitized, 'pages_v3' if head == 'pages' else head + '_v3',
                        tail, f'p{page}.json')


def read_json(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def write_json_atomic(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def iter_page_records(digitized):
    """Все записи страниц `pages\\*\\p<N>.json` (только v2, не заплатки)."""
    pages = os.path.join(digitized, 'pages')
    for folder in sorted(os.listdir(pages)):
        full = os.path.join(pages, folder)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            if name.startswith('p') and name.endswith('.json'):
                record = read_json(os.path.join(full, name))
                if isinstance(record, dict) and 'page_dir' in record:
                    yield record


#: Статусы заплатки, при которых страница считается разобранной.
PATCH_OK = ('ok_judge', 'fixed')


class PageOverlay:
    """Заплатки v3 поверх записей страниц v2 при сборке.

    * `ok_judge` — судья без замечаний: страница больше не «на глаза»;
    * `fixed` — перечитана, судья без замечаний: берётся новая расшифровка;
    * `human` — остаток: если перечитывание дало меньше замечаний, берётся
      оно (в заплатке есть `blocks`), страница остаётся «на глаза»;
    * `needs_fix`, `judge_error` — запись v2 как была;
    * страница из `norm` (ярусы B/C вне выборки контроля) — норма.
    """

    def __init__(self, digitized, norm=()):
        self.digitized, self.norm = digitized, set(norm)

    def apply(self, page_dir, page, base):
        if base is None:
            return None
        patch = read_json(v3_path(self.digitized, page_dir, page))
        status = (patch or {}).get('status')
        out = dict(base)
        if status in PATCH_OK:
            if status == 'fixed' or 'blocks' in patch:
                for key in PATCH_FIELDS:
                    if key in patch:
                        out[key] = patch[key]
            out.update(needs_eyes=False, needs_eyes_reasons=[], status=status)
        elif status == 'human':
            if 'blocks' in patch:
                for key in PATCH_FIELDS:
                    if key in patch:
                        out[key] = patch[key]
            out.update(needs_eyes=True, status='human')
        elif patch is None and f'{page_dir}/p{page}' in self.norm:
            out.update(needs_eyes=False, needs_eyes_reasons=[], status='ok_norm')
        return out


#: Поля записи страницы, которые заплатка заменяет целиком.
PATCH_FIELDS = ('blocks', 'flags', 'layer_ratio', 'layer_fuzz', 'numbers_ok',
                'numbers_missing', 'numbers_extra')


# ── Ярусы ────────────────────────────────────────────────────────────────

def classify(record):
    """Запись страницы v2 → (ярус, причина) или None, если не «на глаза»."""
    if not record.get('needs_eyes'):
        return None
    reasons = record.get('needs_eyes_reasons') or []
    if REASON_FORMAT in reasons or record.get('status') == 'error':
        return TIER_A, 'сбой формата ответа'
    if REASON_JUDGE in reasons:
        return TIER_A, 'скан: судья уже нашёл расхождения'
    if record.get('has_layer'):
        ratio = record.get('layer_ratio')
        # ratio None: в слое нет слов от трёх букв, мерило не посчитано, а страница
        # из-за расхождения со слоем всё же в очереди — считаем риском.
        if ratio is None or ratio < LAYER_THRESHOLD:
            return TIER_A, 'текст расходится со слоем'
        if record.get('numbers_missing'):
            return TIER_A, 'не хватает чисел'
        if record.get('numbers_extra'):
            return TIER_B, 'только лишние числа'
        return TIER_B, 'прочее со слоем'
    return TIER_C, 'плановая выборка скана'


def control_sample(keys, tier, seed=CONTROL_SEED, share=CONTROL_SHARE, minimum=CONTROL_MIN):
    """Случайная (воспроизводимая) выборка контроля яруса: `share` страниц,
    но не меньше `minimum` (или весь ярус, если он меньше)."""
    keys = sorted(keys)
    size = min(len(keys), max(minimum, math.ceil(share * len(keys))))
    return set(random.Random(f'{seed}-{tier}').sample(keys, size))


# ── Срочность ────────────────────────────────────────────────────────────

def page_tasks(v2_rows, file_to_dir):
    """Страница → задания, в сборку которых она вошла: {ключ: [(комплект,
    номер, вариант, роль)]}. Ключ — `pages/<sha16>/p<N>`."""
    out = defaultdict(set)
    for row in v2_rows:
        for role, field in (('условие', 'source_pages'), ('решение', 'solution_pages'),
                            ('критерии', 'criteria_pages')):
            for ref in row.get(field) or []:
                file, _, page = ref.rpartition('#p')
                page_dir = file_to_dir.get(file)
                if page_dir and page.isdigit():
                    out[f'{page_dir}/p{page}'].add(
                        (row['event_id'], norm_number(row['number']),
                         row.get('task_variant') or '', role))
    return {key: sorted(tasks) for key, tasks in out.items()}


def bank_keys(check_rows, official_record_ids=()):
    """Задания эталона, у которых в банке есть похожая: {(комплект, номер)}.

    Источники: таблица проверки банка (`existing_refs_text_check.csv`:
    сопоставленное задание, либо лучшее совпадение где-либо с сходством от
    0,85) и привязки `official:<комплект>:<номер>` в базе."""
    keys = set()
    for row in check_rows:
        event, number = row.get('ref_event_matched'), row.get('ref_number_matched')
        if event and number:
            keys.add((event, norm_number(number)))
        event, number = row.get('best_any_event'), row.get('best_any_number')
        try:
            fuzzy = float(row.get('best_any_fuzzy') or 0)
        except ValueError:
            fuzzy = 0.0
        if event and number and fuzzy >= BANK_FUZZY:
            keys.add((event, norm_number(number)))
    for record_id in official_record_ids:
        parts = str(record_id).split(':')
        if len(parts) == 3 and parts[0] == 'official':
            keys.add((parts[1], norm_number(parts[2])))
    return keys


def urgency(tasks, bank):
    """(срочность, ранг) страницы по заданиям, которые она питает.
    Ранг для сортировки: 0 — в банке нет (будет импорт), 1 — есть похожая,
    2 — страница не питает ни одного задания."""
    if not tasks:
        return NOT_URGENT, 2
    if any((event, number) not in bank for event, number, _v, _r in tasks):
        return URGENT_NEW, 0
    return URGENT_UPDATE, 1


# ── План ─────────────────────────────────────────────────────────────────

def build_plan(records, v2_rows, file_to_dir, bank, events_by_file=None):
    """Строки `triage_plan.csv` по записям страниц «на глаза»."""
    tasks_by_page = page_tasks(v2_rows, file_to_dir)
    queue = {}
    for record in records:
        verdict = classify(record)
        if verdict:
            queue[page_key(record)] = (record, *verdict)
    by_tier = defaultdict(list)
    for key, (_r, tier, _reason) in queue.items():
        by_tier[tier].append(key)
    control = set()
    for tier in (TIER_B, TIER_C):
        control |= control_sample(by_tier[tier], tier)
    rows = []
    for key in sorted(queue):
        record, tier, reason = queue[key]
        tasks = tasks_by_page.get(key, [])
        label, rank = urgency(tasks, bank)
        rows.append({
            'страница': key, 'файл': record.get('file', ''),
            'комплекты': ' '.join(sorted({t[0] for t in tasks}
                                         or (events_by_file or {}).get(record.get('file'), []))),
            'ярус': tier, 'причина': reason, 'срочность': label,
            'задания': ' '.join(sorted({f'{t[0]}#{t[1]}' for t in tasks})),
            'контроль': 'да' if key in control else '',
            '_rank': rank,
        })
    return rows


def write_plan(path, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def read_plan(path):
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def summarize_plan(rows):
    """Сводка плана: ярус × срочность, причины, выборки контроля."""
    summary = {'страниц': len(rows), 'по ярусам': dict(Counter(r['ярус'] for r in rows)),
               'ярус × срочность': {},
               'причины': dict(Counter(f'{r["ярус"]}: {r["причина"]}' for r in rows)),
               'контроль': dict(Counter(r['ярус'] for r in rows if r['контроль']))}
    for r in rows:
        key = f'{r["ярус"]} / {r["срочность"]}'
        summary['ярус × срочность'][key] = summary['ярус × срочность'].get(key, 0) + 1
    return summary


def pages_to_judge(plan_rows):
    """Что идёт к судье: весь ярус A + выборка контроля ярусов B и C."""
    return [r['страница'] for r in plan_rows
            if r['ярус'] == TIER_A or (r['ярус'] in (TIER_B, TIER_C) and r['контроль'])]


def norm_pages(plan_rows):
    """Страницы ярусов B/C вне выборки контроля: норма по умолчанию."""
    return {r['страница'] for r in plan_rows
            if r['ярус'] in (TIER_B, TIER_C) and not r['контроль']}


# ── Сверка сборок v2 и v3 ────────────────────────────────────────────────

def _task_key(row):
    return (row['event_id'], row['number'], row.get('task_variant') or '')


def compare_versions(old_rows, new_rows, v1_counts=None):
    """Числовые инварианты сборки v3 против v2.

    * заданий по комплектам: где в v3 меньше, чем в v2 (должно быть пусто);
    * заданий с пустым `statement_md` — не больше, чем в v2;
    * задания, у которых изменился текст условия, решения или критериев;
    * комплекты, совпадающие с v1 по числу заданий (`v1_counts`)."""
    old = {_task_key(r): r for r in old_rows}
    new = {_task_key(r): r for r in new_rows}
    count_old, count_new = Counter(r['event_id'] for r in old_rows), \
        Counter(r['event_id'] for r in new_rows)
    fewer = {e: (count_old[e], count_new.get(e, 0)) for e in count_old
             if count_new.get(e, 0) < count_old[e]}
    more = {e: (count_old.get(e, 0), count_new[e]) for e in count_new
            if count_new[e] > count_old.get(e, 0)}
    changed = [k for k in old if k in new and any(
        (old[k].get(f) or '') != (new[k].get(f) or '')
        for f in ('statement_md', 'solution_md', 'criteria_md'))]
    out = {
        'заданий v2': len(old_rows), 'заданий v3': len(new_rows),
        'комплектов, где v3 меньше v2': fewer, 'комплектов, где v3 больше v2': more,
        'пустых statement_md v2': sum(not r['statement_md'] for r in old_rows),
        'пустых statement_md v3': sum(not r['statement_md'] for r in new_rows),
        'заданий пропало': sorted(set(old) - set(new)),
        'заданий появилось': sorted(set(new) - set(old)),
        'заданий с изменённым текстом': changed,
        'needs_eyes v2': sum(bool(r.get('needs_eyes')) for r in old_rows),
        'needs_eyes v3': sum(bool(r.get('needs_eyes')) for r in new_rows),
    }
    if v1_counts is not None:
        out['комплектов, совпадающих с v1 по числу заданий'] = \
            f'{sum(count_new.get(e, 0) == n for e, n in v1_counts.items())} из {len(v1_counts)}'
    return out
