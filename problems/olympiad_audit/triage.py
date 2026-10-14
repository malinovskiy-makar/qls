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
import re
from collections import Counter, defaultdict

from problems.olympiad_audit.assemble import _plain, is_service_text, norm_number
from problems.olympiad_audit.transcribe import (LAYER_THRESHOLD, clean_blocks, layer_metrics,
                                                passes)

TIER_A, TIER_B, TIER_C = 'A', 'B', 'C'
#: Ярус D (сессия 2, финграмотность и бизнес): страница НЕ в очереди «на глаза»,
#: но питает задание к импорту и не дотягивает до автопубликации (слой < 0,95,
#: числа не сошлись, скан без слоя) — к судье, чтобы задание не ушло человеку
#: только из-за мерила. Решение 13.10: публикуем без ручной проверки, если
#: строгая автопроверка уверена.
TIER_D = 'D'
AUTO_LAYER = 0.95

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


#: Папка заплаток по умолчанию (ВП/МОШ по экономике: эталон v2 → заплатки v3).
#: Финграмотность и бизнес (сессия 2, 13.10.2026): эталон v1 → `pages_v2`
#: (`--base v1` у команд разбора).
DEFAULT_PATCHES = 'pages_v3'


def patches_for(base):
    """`v1` → `pages_v2`, `v2` → `pages_v3`: заплатки — следующая версия."""
    return f'pages_v{int(str(base).lstrip("v")) + 1}'


def v3_path(digitized, page_dir, page, patches=DEFAULT_PATCHES):
    """`pages/<sha16>` → `<patches>/<sha16>/p<N>.json` (рядом, не поверх)."""
    head, _, tail = page_dir.partition('/')
    suffix = patches.rpartition('_')[2]
    return os.path.join(digitized, patches if head == 'pages' else f'{head}_{suffix}',
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
#: Мерило слоя пересчитано без модели (сессия 2: точность против всего слоя) —
#: страница прошла порог; поля мерила в заплатке.
RESCORE_OK = 'ok_rescore'
METRIC_FIELDS = ('layer_ratio', 'layer_fuzz', 'numbers_ok', 'numbers_missing', 'numbers_extra')


class PageOverlay:
    """Заплатки v3 поверх записей страниц v2 при сборке.

    * `ok_judge` — судья без замечаний: страница больше не «на глаза»;
    * `fixed` — перечитана, судья без замечаний: берётся новая расшифровка;
    * `human` — остаток: если перечитывание дало меньше замечаний, берётся
      оно (в заплатке есть `blocks`), страница остаётся «на глаза»;
    * `needs_fix`, `judge_error` — запись v2 как была;
    * страница из `norm` (ярусы B/C вне выборки контроля) — норма.
    """

    def __init__(self, digitized, norm=(), patches=DEFAULT_PATCHES, keep_points=False,
                 check_numbers=True):
        self.digitized, self.norm, self.patches = digitized, set(norm), patches
        #: Защита «перечитывание потеряло номера» (13.10). Слой pages_v3 в сборке
        #: v5 — без неё: так собран v3 (09.10), и сборка v5 с пустым pages_v5
        #: даёт v3 ровно.
        self.check_numbers = check_numbers
        #: v5: у перечитанного блока без баллов баллы берутся у того же блока
        #: прежней расшифровки (МОШ 2011, 10 кл., «Тест II»: перечитывание
        #: вернуло шапку теста, но потеряло «2 балла» у вопросов 16–21).
        self.keep_points = keep_points

    def _take(self, out, patch, base):
        for key in PATCH_FIELDS:
            if key in patch:
                out[key] = patch[key]
        if self.keep_points and 'blocks' in patch:
            # Слой v5: баллы — из прежней расшифровки; блоки помечаются `_v5`
            # (сборка не даёт перечитыванию заводить новые задания из файла ответов).
            out['blocks'] = [dict(b, _v5=True)
                             for b in keep_points(base.get('blocks') or [], out['blocks'])]

    def apply(self, page_dir, page, base):
        if base is None:
            return None
        patch = read_json(v3_path(self.digitized, page_dir, page, self.patches))
        status = (patch or {}).get('status')
        out = dict(base)
        if patch and patch.get('rescore'):
            # Мерило пересчитано без модели: поля мерила — из заплатки (до блоков).
            for key in METRIC_FIELDS:
                if key in patch['rescore']:
                    out[key] = patch['rescore'][key]
        if status == RESCORE_OK:
            out.update(needs_eyes=False, needs_eyes_reasons=[], status=status)
        elif status in PATCH_OK:
            if (self.check_numbers and (status == 'fixed' or 'blocks' in patch)
                    and 'blocks' in patch
                    and not numbers_kept(base.get('blocks'), patch['blocks'])):
                # Перечитывание поправило текст, но потеряло номера блоков
                # (МОШ-предпринимательство 2009/10: 15 ответов → один блок без
                # номера): старая разметка, страница — человеку.
                out.update(needs_eyes=True, status=SKELETON_LOST,
                           needs_eyes_reasons=['перечитывание потеряло номера'])
                return out
            if status == 'fixed' or 'blocks' in patch:
                self._take(out, patch, base)
            out.update(needs_eyes=False, needs_eyes_reasons=[], status=status)
        elif status == 'human':
            # Расшифровка human-страницы судьёй не подтверждена: берём её, только
            # если «скелет» (тип+номер блоков заданий/решений/критериев) тот же —
            # иначе задание могло бы тихо исчезнуть из сборки (mosh-2019-final-6).
            if 'blocks' in patch and skeleton(patch['blocks']) == skeleton(base.get('blocks')):
                self._take(out, patch, base)
            out.update(needs_eyes=True, status='human')
        elif patch is None and f'{page_dir}/p{page}' in self.norm:
            out.update(needs_eyes=False, needs_eyes_reasons=[], status='ok_norm')
        return out


class LayeredOverlay:
    """Несколько слоёв заплаток по порядку (v5: `pages_v3`, затем `pages_v5`):
    каждый следующий накладывается на результат предыдущего, так что поздний
    слой перекрывает ранний, а его защиты (скелет, номера) сверяются с уже
    поправленной страницей."""

    def __init__(self, layers):
        self.layers = list(layers)

    def apply(self, page_dir, page, base):
        for layer in self.layers:
            base = layer.apply(page_dir, page, base)
        return base


def keep_points(base_blocks, new_blocks):
    """Баллы блока (тип, номер, вариант), потерянные перечитыванием, — из
    прежней расшифровки; блоки без номера и с баллами не трогаются."""
    points = {}
    for b in base_blocks or []:
        key = (b.get('type'), str(b.get('number') or ''), str(b.get('task_variant') or ''))
        if key[1] and b.get('points') not in (None, ''):
            points.setdefault(key, b['points'])
    out = []
    for b in new_blocks or []:
        key = (b.get('type'), str(b.get('number') or ''), str(b.get('task_variant') or ''))
        if key[1] and b.get('points') in (None, '') and key in points:
            b = dict(b, points=points[key])
        out.append(b)
    return out


STRUCTURE_TYPES = ('task', 'task_continuation', 'solution', 'criteria')
SKELETON_LOST = 'human_skeleton'


def numbers_kept(base_blocks, new_blocks):
    """Все номера блоков заданий/решений/критериев исходной расшифровки есть и в
    новой (номера, а не порядок: перечитывание вправе поменять тип блока)."""
    def numbers(blocks):
        return {str(b.get('number') or '').strip() for b in blocks or []
                if b.get('type') in STRUCTURE_TYPES and str(b.get('number') or '').strip()}
    return numbers(base_blocks) <= numbers(new_blocks)


def skeleton(blocks):
    """Структура страницы для сборки: порядок (тип, номер) блоков заданий,
    решений и критериев; текст в неё не входит."""
    return [(b.get('type'), str(b.get('number') or '')) for b in blocks or []
            if b.get('type') in STRUCTURE_TYPES]


#: Поля записи страницы, которые заплатка заменяет целиком.
PATCH_FIELDS = ('blocks', 'flags', 'layer_ratio', 'layer_fuzz', 'numbers_ok',
                'numbers_missing', 'numbers_extra')


# ── Ярусы ────────────────────────────────────────────────────────────────

def rescore_record(record, job):
    """Пересчитать мерило слоя по блокам записи (без модели, без записи на
    диск): (новая запись, поля мерила | None, если не изменились). Страница
    «на глаза» только из-за расхождения со слоем, прошедшая порог по новому
    мерилу, больше не «на глаза»."""
    if job is None or not job.has_layer or record.get('status') not in ('ok', 'needs_eyes'):
        return record, None
    m = layer_metrics(clean_blocks(record.get('blocks')), job.layer, job.footers, job.page)
    fields = {'layer_ratio': m[0], 'numbers_ok': m[1], 'numbers_missing': m[2][:50],
              'numbers_extra': m[3][:50], 'layer_fuzz': m[4]}
    if all(record.get(k) == v for k, v in fields.items()):
        return record, None
    out = dict(record, **fields)
    reasons = record.get('needs_eyes_reasons') or []
    if record.get('needs_eyes') and set(reasons) <= {REASON_LAYER} and passes(m):
        out.update(needs_eyes=False, needs_eyes_reasons=[])
    return out, fields


_HEADING = re.compile(r'(?m)^\W*(?:задача|задание)\s*№?\s*(\d+)\b', re.IGNORECASE)
SHORT_STATEMENT = 30


def task_risks(rows, events_with_answers, file_to_dir):
    """Задачные причины яруса A по эталону: {ключ страницы условия: [причины]}.

    Пустое или слишком короткое условие (разрыв), нет ответа/решения/критериев
    при файле решений у комплекта, внутри условия заголовок ДРУГОГО задания
    (склейка), условие — служебный блок."""
    out = defaultdict(list)
    # Пропуск номеров внутри комплекта (1 → 9): задание перед пропуском —
    # подозрение на склейку, если сборка не смогла его разрезать.
    tails = defaultdict(set)
    for row in rows:
        match = re.match(r'^(.*?)(\d+)$', str(row.get('number') or ''))
        if match:
            tails[(row['event_id'], row.get('task_variant') or '', match.group(1))].add(
                int(match.group(2)))
    for row in rows:
        statement = row.get('statement_md') or ''
        reasons = []
        match = re.match(r'^(.*?)(\d+)$', str(row.get('number') or ''))
        if match:
            ints = tails[(row['event_id'], row.get('task_variant') or '', match.group(1))]
            n = int(match.group(2))
            later = [m for m in ints if m > n]
            if later and min(later) > n + 1:
                reasons.append(f'после задания пропуск номеров до {min(later)} (склейка?)')
        if not statement.strip():
            reasons.append('пустое условие')
        elif len(_plain(statement)) < SHORT_STATEMENT:
            reasons.append('короткое условие (разрыв?)')
        if row['event_id'] in events_with_answers and not (
                row.get('solution_md') or row.get('answer') or row.get('criteria_md')):
            reasons.append('нет ответа/решения при файле решений')
        own = re.match(r'\d+', str(row.get('number') or ''))
        others = {n for n in _HEADING.findall(statement) if own and n != own.group()}
        if others:
            reasons.append(f'внутри условия заголовок задания {", ".join(sorted(others))} (склейка?)')
        if statement.strip() and is_service_text(statement):
            reasons.append('служебный блок как задание')
        if not reasons:
            continue
        for ref in row.get('source_pages') or []:
            file, _, page = ref.rpartition('#p')
            page_dir = file_to_dir.get(file)
            if page_dir and page.isdigit():
                for reason in reasons:
                    tag = f'{row["event_id"]}#{row["number"]}: {reason}'
                    if tag not in out[f'{page_dir}/p{page}']:
                        out[f'{page_dir}/p{page}'].append(tag)
    return dict(out)


def auto_publish_page_ok(record):
    """Страница проходит автопроверку без судьи: слой ≥ 0,95 и числа сошлись."""
    return bool(record.get('has_layer') and (record.get('layer_ratio') or 0) >= AUTO_LAYER
                and record.get('numbers_ok') and not record.get('needs_eyes'))


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

def build_plan(records, v2_rows, file_to_dir, bank, events_by_file=None, risks=None,
               auto_publish=False):
    """Строки `triage_plan.csv` по записям страниц «на глаза».

    `risks` — задачные причины яруса A (`task_risks`): страница поднимается в A
    или добавляется. `auto_publish` — ярус D: страницы заданий «в банке нет»,
    не прошедшие автопроверку (`auto_publish_page_ok`), к судье."""
    tasks_by_page = page_tasks(v2_rows, file_to_dir)
    queue = {}
    by_key = {}
    for record in records:
        by_key[page_key(record)] = record
        verdict = classify(record)
        if verdict:
            queue[page_key(record)] = (record, *verdict)
    for key, reasons in (risks or {}).items():
        if key not in by_key:
            continue
        text = 'задание: ' + '; '.join(reasons)
        if key in queue:
            record, _tier, reason = queue[key]
            queue[key] = (record, TIER_A, f'{reason}; {text}')
        else:
            queue[key] = (by_key[key], TIER_A, text)
    if auto_publish:
        for key, tasks in tasks_by_page.items():
            record = by_key.get(key)
            if key in queue or record is None or urgency(tasks, bank)[0] != URGENT_NEW:
                continue
            if not auto_publish_page_ok(record):
                why = ('скан без слоя' if not record.get('has_layer') else
                       f'слой {record.get("layer_ratio")} < {AUTO_LAYER}'
                       if (record.get('layer_ratio') or 0) < AUTO_LAYER else 'числа не сошлись')
                queue[key] = (record, TIER_D, f'для автопубликации: {why}')
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


def pages_to_judge(plan_rows, only=None):
    """Что идёт к судье: ярусы A и D + выборка контроля ярусов B и C.
    `only='control'` — только выборка контроля (её смотрят первой: доля
    «дефектов» > 30 % — судья ненадёжен, остальное не судится)."""
    if only == 'control':
        return [r['страница'] for r in plan_rows if r['ярус'] in (TIER_B, TIER_C) and r['контроль']]
    if only == 'auto':
        # Для автопубликации: B/C вне выборки контроля у заданий к импорту —
        # «норма» для сборки, но не уверенность для публикации без человека.
        return [r['страница'] for r in plan_rows if r['ярус'] in (TIER_B, TIER_C)
                and not r['контроль'] and r['срочность'] == URGENT_NEW]
    return [r['страница'] for r in plan_rows
            if r['ярус'] in (TIER_A, TIER_D) or (r['ярус'] in (TIER_B, TIER_C) and r['контроль'])]


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
