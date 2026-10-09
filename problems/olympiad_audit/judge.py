# -*- coding: utf-8 -*-
"""Судья «картинка против расшифровки» и целевое перечитывание страниц.

Фаза 2: судья получает картинку страницы и расшифровку и возвращает
СТРОГИЙ JSON — список конкретных расхождений. Невалидный ответ — один
повтор; не помогло — страница остаётся «на глаза» (`judge_error`).

Страница с нулём замечаний и без РЕАЛЬНОГО пропуска чисел — `ok_judge`,
остальные — `needs_fix`. «Реальный пропуск» — число из текстового слоя PDF,
которого нет в расшифровке (`numbers_missing`) и которое судья подтвердил
на картинке (`on_image`) при отсутствии в расшифровке (`in_transcript`);
число, которого на картинке нет (артефакт слоя), или которое в расшифровке
всё-таки есть (мерило не узнало запись), не считается. Число, про которое
судья промолчал, считается реальным пропуском — в сомнении страница не
проходит.

Фаза 3: `needs_fix` перечитывается ОДИН раз тем же `glm-5.3-flash` с
картинкой и подсказкой (замечания судьи + недостающие числа слоя), затем
пересчёт мерила и повторный судья: без замечаний — `fixed`, иначе `human`.

Результат — только в `pages_v3\\`; старые `pages\\…\\p<N>.json` не
перезаписываются. В базу — ничего.
"""
from __future__ import annotations

import os
import random
from collections import Counter
from datetime import datetime

from problems.olympiad_audit import triage
from problems.olympiad_audit.transcribe import (JUDGE_PROFILE, PROFILE, SCHEMA,
                                                SYSTEM_PROMPT, Transcriber)

JUDGE_ATTEMPTS = 2                  # вызов + один повтор на невалидный ответ
MAX_TRANSCRIPT_CHARS = 30000
MAX_HINT_ISSUES = 20

JUDGE_PROMPT = """Ты проверяешь расшифровку страницы олимпиадных заданий по экономике. Тебе дана картинка страницы и расшифровка (блоки: тип, номер, вариант, баллы, текст в Markdown, формулы в LaTeX). Сравни расшифровку с картинкой и перечисли КОНКРЕТНЫЕ расхождения. Виды (поле `kind`):
- «пропуск» — строка, абзац, подпункт, число или ячейка таблицы есть на картинке, а в расшифровке нет;
- «лишнее» — в расшифровке есть текст, которого на картинке нет;
- «формула» — формула записана неверно (другие знаки, индексы, степени, дроби);
- «номер» — неверный номер задания, вариант или баллы;
- «искажение» — другие слова, числа или знаки в обычном тексте и таблицах.
Не считаются расхождениями: колонтитулы и номера страниц, оформление Markdown/LaTeX, пробелы, «е» вместо «ё». Не придумывай: не уверен — не пиши. В `detail` процитируй фрагмент (что на картинке и что в расшифровке).

Если в запросе дан список «Числа для проверки», то про КАЖДОЕ число из него заполни запись в `numbers`: `on_image` — есть ли это число на картинке (отдельно или внутри записи), `in_transcript` — есть ли оно в расшифровке. Если списка нет — `numbers` пустой.

Ответ — ОДИН JSON-объект: {"ok": true/false, "issues": [{"kind": "пропуск|лишнее|формула|номер|искажение", "where": "где на странице", "detail": "что именно"}], "numbers": [{"number": "…", "on_image": true/false, "in_transcript": true/false}]}. Расхождений нет — {"ok": true, "issues": [], "numbers": […]}."""

JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'ok': {'type': 'boolean'},
        'issues': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'kind': {'type': 'string'}, 'where': {'type': 'string'},
                           'detail': {'type': 'string'}},
            'required': ['kind', 'detail']}},
        'numbers': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'number': {'type': 'string'}, 'on_image': {'type': 'boolean'},
                           'in_transcript': {'type': 'boolean'}},
            'required': ['number', 'on_image', 'in_transcript']}},
    },
    'required': ['ok', 'issues'],
}

REREAD_HINT = """

ПЕРЕЧИТЫВАНИЕ. Проверяющий сравнил прошлую расшифровку этой страницы с картинкой и нашёл расхождения. Перепиши страницу ДОСЛОВНО и целиком, исправив их.{issues}{numbers}"""


class BadVerdict(ValueError):
    """Ответ судьи не соответствует схеме."""


# ── Что видит судья ──────────────────────────────────────────────────────

def judge_transcript(blocks):
    """Блоки расшифровки → читаемый текст для судьи (не сырой JSON)."""
    parts = []
    for block in blocks:
        kind = block.get('type')
        if kind in ('footer', 'noise'):
            parts.append(f'[{kind}: колонтитул/служебное — не проверять]')
            continue
        head = [kind]
        if block.get('number'):
            head.append(f'№ {block["number"]}')
        if block.get('task_variant'):
            head.append(f'вариант задания {block["task_variant"]}')
        if block.get('points') not in (None, ''):
            head.append(f'{block["points"]} баллов')
        if block.get('title'):
            head.append(f'«{block["title"]}»')
        lines = ['### ' + ', '.join(str(h) for h in head)]
        for key in ('olympiad', 'year', 'stage', 'grade', 'variant'):
            if kind == 'header' and block.get(key):
                lines.append(f'{key}: {block[key]}')
        if block.get('text'):
            lines.append(block['text'])
        if block.get('answer'):
            lines.append(f'Ответ: {block["answer"]}')
        if block.get('caption'):
            lines.append(f'Подпись рисунка: {block["caption"]}')
        parts.append('\n'.join(lines))
    return '\n\n'.join(parts)[:MAX_TRANSCRIPT_CHARS]


def judge_user_text(key, blocks, expected_numbers):
    text = f'Страница {key}. Расшифровка:\n\n{judge_transcript(blocks)}'
    if expected_numbers:
        text += ('\n\nЧисла для проверки (по текстовому слою PDF их не хватает в '
                 'расшифровке): ' + ', '.join(str(n) for n in expected_numbers))
    return text


def reread_user_text(job, issues, missing_numbers):
    listing = ''
    if issues:
        listing = '\nЗамечания:\n' + '\n'.join(
            f'- {i.get("kind", "")} ({i.get("where", "")}): {str(i.get("detail", ""))[:300]}'
            for i in issues[:MAX_HINT_ISSUES])
    numbers = ''
    if missing_numbers:
        numbers = ('\nВ текстовом слое PDF есть числа, которых нет в прошлой расшифровке: '
                   + ', '.join(str(n) for n in missing_numbers)
                   + '. Убедись, что эти фрагменты есть на картинке; если есть — включи их '
                     'в расшифровку; если нет — не добавляй.')
    return job.user_text() + REREAD_HINT.format(issues=listing, numbers=numbers)


# ── Разбор ответа судьи ──────────────────────────────────────────────────

def _number_key(value):
    return str(value).strip().lstrip('-−').replace('.', ',').replace(' ', '')


def parse_verdict(data, expected_numbers=()):
    """Ответ модели → вердикт или `BadVerdict`. Строго: нужны `ok` (bool) и
    `issues` (список замечаний с непустым `detail`); при списке чисел для
    проверки — ещё и `numbers` (список записей с bool-полями)."""
    if not isinstance(data, dict) or data.get('_parse_error'):
        raise BadVerdict('ответ не JSON')
    if not isinstance(data.get('ok'), bool):
        raise BadVerdict('нет поля ok (true/false)')
    if not isinstance(data.get('issues'), list):
        raise BadVerdict('нет списка issues')
    issues = []
    for item in data['issues']:
        detail = item.get('detail') if isinstance(item, dict) else None
        if not isinstance(detail, str) or not detail.strip():
            raise BadVerdict('замечание без detail')
        issues.append({'kind': str(item.get('kind') or 'искажение').strip().lower(),
                       'where': str(item.get('where') or '').strip(),
                       'detail': detail.strip()})
    if not data['ok'] and not issues:
        issues.append({'kind': 'прочее', 'where': '',
                       'detail': 'судья ответил ok=false, не уточнив расхождение'})
    entries = []
    if expected_numbers:
        raw = data.get('numbers')
        if not isinstance(raw, list):
            raise BadVerdict('нет списка numbers')
        for item in raw:
            if (not isinstance(item, dict) or item.get('number') in (None, '')
                    or not isinstance(item.get('on_image'), bool)
                    or not isinstance(item.get('in_transcript'), bool)):
                raise BadVerdict('запись numbers без number/on_image/in_transcript')
            entries.append({'number': str(item['number']).strip(),
                            'on_image': item['on_image'],
                            'in_transcript': item['in_transcript']})
    missing = real_missing(entries, expected_numbers)
    return {'ok': not issues and not missing, 'issues': issues, 'numbers': entries,
            'expected_numbers': [str(n) for n in expected_numbers],
            'real_missing': missing}


def real_missing(entries, expected_numbers):
    """Числа слоя, реально пропущенные в расшифровке (см. шапку модуля)."""
    seen = {_number_key(e['number']): e for e in entries}
    out = []
    for number in expected_numbers:
        entry = seen.get(_number_key(number))
        if entry is None or (entry['on_image'] and not entry['in_transcript']):
            out.append(str(number))
    return out


def decide_status(verdict):
    """`ok_judge` — ни одного замечания и ни одного реального пропуска числа."""
    clean = not verdict.get('issues') and not verdict.get('real_missing')
    return 'ok_judge' if clean else 'needs_fix'


def defect_count(verdict):
    return len(verdict.get('issues') or []) + len(verdict.get('real_missing') or [])


# ── Прогоны ──────────────────────────────────────────────────────────────

def _now():
    return datetime.now().isoformat(timespec='seconds')


class JudgeBase(Transcriber):
    """Общее: вызов судьи с одним повтором на невалидный ответ."""

    def __init__(self, *, plan=None, **kwargs):
        super().__init__(**kwargs)
        self.plan = plan or {}
        self.digitized = self.root

    def v3(self, job):
        return triage.v3_path(self.digitized, job.page_dir, job.page)

    def judge_blocks(self, job, blocks, expected_numbers, kind):
        """(вердикт | None, ошибка, расход). Невалидный ответ — один повтор."""
        from problems.ai import core
        cost, error = 0.0, ''
        for _attempt in range(JUDGE_ATTEMPTS):
            self.stats['судья вызовов'] += 1
            try:
                data, usage = self._call(
                    job, JUDGE_PROMPT, judge_user_text(job.key, blocks, expected_numbers),
                    JUDGE_SCHEMA, kind, JUDGE_PROFILE)
            except core.AiUnavailable as exc:
                error = f'сбой вызова: {exc}'[:300]
                continue
            cost += float((usage or {}).get('cost_usd') or 0)
            try:
                return parse_verdict(data, expected_numbers), '', cost
            except BadVerdict as exc:
                error = str(exc)
                self.stats['судья: невалидный ответ'] += 1
        return None, error, cost


class JudgeRunner(JudgeBase):
    """Фаза 2: судья на страницах плана → заплатка v3 со статусом
    `ok_judge` / `needs_fix` / `judge_error`."""

    def transcribe_page(self, job):
        record = triage.read_json(job.out_path(self.root))
        row = self.plan.get(job.key, {})
        expected = list(record.get('numbers_missing') or []) if job.has_layer else []
        verdict, error, cost = self.judge_blocks(job, record.get('blocks') or [],
                                                 expected, 'judge2')
        patch = {'file': job.file, 'page_dir': job.page_dir, 'page': job.page,
                 'phase': 'judge', 'tier': row.get('ярус', ''),
                 'control': row.get('контроль') == 'да', 'judge': verdict,
                 'error': error, 'cost_usd': round(cost, 6), 'at': _now()}
        patch['status'] = decide_status(verdict) if verdict else 'judge_error'
        triage.write_json_atomic(self.v3(job), patch)
        return patch['status']


class RereadRunner(JudgeBase):
    """Фаза 3: перечитывание `needs_fix` (одна попытка) → пересчёт мерила →
    повторный судья → `fixed` / `human`."""

    def transcribe_page(self, job):
        old = triage.read_json(job.out_path(self.root))
        patch = triage.read_json(self.v3(job))
        before = patch['judge']
        missing_layer = list(old.get('numbers_missing') or []) if job.has_layer else []
        data, usage = self._call(
            job, SYSTEM_PROMPT, reread_user_text(job, before['issues'], missing_layer),
            SCHEMA, 'reread', PROFILE)
        cost = float((usage or {}).get('cost_usd') or 0)
        attempt = self._attempt(job, data, usage, retry=True)
        new = {'blocks': attempt['blocks'], 'flags': attempt['flags'],
               'layer_ratio': attempt['metrics'][0], 'numbers_ok': attempt['metrics'][1],
               'numbers_missing': attempt['metrics'][2][:50],
               'numbers_extra': attempt['metrics'][3][:50], 'layer_fuzz': attempt['metrics'][4],
               'parse_error': attempt.get('parse_error', '')}
        after, error = None, ''
        if new['parse_error'] and not new['blocks']:
            error = 'сбой формата перечитывания'
        else:
            expected = list(new['numbers_missing']) if job.has_layer else []
            after, error, judge_cost = self.judge_blocks(job, new['blocks'], expected,
                                                         'rejudge')
            cost += judge_cost
        result = {'file': job.file, 'page_dir': job.page_dir, 'page': job.page,
                  'phase': 'reread', 'tier': patch.get('tier', ''),
                  'control': patch.get('control', False), 'judge_before': before,
                  'judge': after, 'error': error, 'reread': new, 'at': _now(),
                  'cost_usd': round(float(patch.get('cost_usd') or 0) + cost, 6)}
        fixed = after is not None and decide_status(after) == 'ok_judge'
        result['status'] = 'fixed' if fixed else 'human'
        better = after is not None and defect_count(after) < defect_count(before)
        result['chosen'] = 'v3' if (fixed or better) else 'v2'
        if result['chosen'] == 'v3':
            for key in triage.PATCH_FIELDS:
                result[key] = new[key]
        triage.write_json_atomic(self.v3(job), result)
        return result['status']


# ── Отбор страниц ────────────────────────────────────────────────────────

JUDGE_DONE = ('ok_judge', 'needs_fix', 'fixed', 'human')


def judge_todo(keys, digitized):
    """Страницы, у которых судья ещё не отработал (`judge_error` — повторить)."""
    return [key for key in keys if (triage.read_json(_patch_path(digitized, key)) or {})
            .get('status') not in JUDGE_DONE]


def select_for_reread(keys, digitized):
    """Страницы на перечитывание: судья дал `needs_fix`, перечитывания ещё не
    было. `ok_judge`, `judge_error`, `fixed`, `human` — мимо (одна попытка)."""
    return [key for key in keys if (triage.read_json(_patch_path(digitized, key)) or {})
            .get('status') == 'needs_fix']


def _patch_path(digitized, key):
    page_dir, _, page = key.rpartition('/p')
    return triage.v3_path(digitized, page_dir, page)


def v3_statuses(digitized):
    """Статусы всех заплаток v3: {ключ страницы: запись}."""
    root = os.path.join(digitized, 'pages_v3')
    out = {}
    if not os.path.isdir(root):
        return out
    for folder in sorted(os.listdir(root)):
        for name in sorted(os.listdir(os.path.join(root, folder))):
            if name.endswith('.json'):
                patch = triage.read_json(os.path.join(root, folder, name))
                if patch:
                    out[f'pages/{folder}/p{name[1:-5]}'] = patch
    return out


# ── Сводка для стоп-гейта ────────────────────────────────────────────────

#: Судья, нашедший «дефекты» в большей доле контрольных страниц, ненадёжен.
FALSE_POSITIVE_LIMIT = 0.30


def _first_verdict(patch):
    """Заключение судьи по ПРЕЖНЕЙ расшифровке страницы (фаза 2)."""
    return patch.get('judge_before') or patch.get('judge') or {}


def judge_report(plan_rows, patches, examples=10, seed=7):
    """Сводка фазы 2: статусы по ярусам, ложные срабатывания на контроле
    (ярусы B и C — страницы, которые считаются нормой), примеры замечаний."""
    plan = {r['страница']: r for r in plan_rows}
    judged = {k: p for k, p in patches.items()
              if k in plan and p.get('phase') in ('judge', 'reread')}
    by_tier = {}
    for key, patch in judged.items():
        by_tier.setdefault(plan[key]['ярус'], Counter())[patch['status']] += 1
    control = {}
    for tier in ('B', 'C'):
        pages = [p for k, p in judged.items() if plan[k]['ярус'] == tier and plan[k]['контроль']]
        answered = [p for p in pages if _first_verdict(p)]
        found = [p for p in answered if defect_count(_first_verdict(p))]
        control[tier] = {'страниц': len(pages), 'судья ответил': len(answered),
                         'нашёл дефекты': len(found),
                         'доля': round(len(found) / len(answered), 3) if answered else None}
    answered = sum(c['судья ответил'] for c in control.values())
    found = sum(c['нашёл дефекты'] for c in control.values())
    control['всего'] = {'судья ответил': answered, 'нашёл дефекты': found,
                        'доля': round(found / answered, 3) if answered else None}
    dismissed = sum(1 for p in judged.values()
                    if _first_verdict(p).get('expected_numbers')
                    and not _first_verdict(p).get('real_missing'))
    pool = [(k, i['kind'], i['detail']) for k, p in sorted(judged.items())
            for i in _first_verdict(p).get('issues') or []]
    sample = random.Random(seed).sample(pool, min(examples, len(pool)))
    return {'страниц с заключением судьи': len(judged),
            'по статусам': dict(Counter(p['status'] for p in judged.values())),
            'по ярусам': {t: dict(c) for t, c in sorted(by_tier.items())},
            'контроль (ложные срабатывания)': control,
            'судья ненадёжен (доля > 30 %)': bool(
                answered and found / answered > FALSE_POSITIVE_LIMIT),
            'страниц, где «не хватает чисел» не подтвердилось картинкой': dismissed,
            'расход, $': round(sum(float(p.get('cost_usd') or 0) for p in judged.values()), 4),
            'примеры замечаний': [{'страница': k, 'вид': kind, 'что': detail[:300]}
                                  for k, kind, detail in sample]}

