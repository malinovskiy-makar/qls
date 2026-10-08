"""Прогон экзамена: «Решатель» и «Утечка». Деньги, потоки, папка прогона.

⚠️ В БАЗУ НЕ ПИШЕТ НИ СТРОКИ. Каждый вызов —
`core.run(..., user=None, log=False, check_budget=False, check_limit=False,
cache_seconds=0)`: ни `ChatTurn`, ни `AiUsageLog`, расход складывается в
файлах прогона. Всё, что ходит в базу (задачи, подпункты), читается в
главном потоке ДО запуска; в рабочих потоках — только `core.run`.

⚠️ Поставщик оборачивается `GuardedProvider`: `core.run` на отказе
поставщика пишет строку `AiUsageLog` даже при `log=False` (ветка
`ProviderError` в `problems/ai/core.py`). Обёртка превращает отказ в
`CallFailed` — его `core.run` не ловит, строка не пишется, а прогонщик
знает вид отказа (повтор на `limit`).

«Утечка» ходит через `catalog.chat.ask_model` — тем же путём, что чат на
сайте; «Решатель» — своим системным блоком (`problems/ai_exam/solve.py`).
Правила — docs/AI_EXAM.md, «Прогон».
"""
import hashlib
import json
import os
import re
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from django.conf import settings
from django.utils import timezone

from problems.ai import core, prompts, providers
from problems.ai_exam import leak, solve
from problems.ai_exam.build import reserve_chunk
from problems.ai_exam.loader import load_tasks

SETS = ('work', 'draft', 'smoke', 'safe')
SUITES = ('solve', 'leak', 'both')
SAFE_PHRASE = 'ОТКРЫВАЮ СЕЙФ'
#: Оценка для плана: на бете реплика стоила $0,0033 — с запасом.
COST_PER_CALL = 0.004
LIMIT_PAUSES = (5, 15, 45)
#: Поставщики, которым не нужно --yes: денег они не тратят.
FREE_PROVIDERS = ('fake',)
SMOKE_NOTE = 'проба трубы, ключи не проверены'


class RunRefused(Exception):
    """Прогон не начат: человеческий текст причины, ни одного вызова."""


class CallFailed(Exception):
    def __init__(self, message, kind='other'):
        super().__init__(message)
        self.kind = kind


class GuardedProvider:
    """Поставщик, чей отказ НЕ доходит до `core.run` как `ProviderError`."""

    def __init__(self, inner):
        self.inner = inner
        self.name = inner.name

    def is_available(self):
        return self.inner.is_available()

    def unavailable_reason(self):
        return self.inner.unavailable_reason()

    def complete(self, *args, **kwargs):
        try:
            return self.inner.complete(*args, **kwargs)
        except providers.ProviderError as error:
            raise CallFailed(str(error), kind=getattr(error, 'kind', 'other'))


# ── Наборы задач ────────────────────────────────────────────────────────

def _read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def candidate_as_row(c):
    """Кандидат как строка экзамена: ключ — ПРЕДЛОЖЕНИЕ программы (smoke)."""
    return {'id': c['id'], 'section': c['section'], 'topic': c['topic'],
            'level': c['level'], 'difficulty': c['difficulty'],
            'statement_hash': c['statement_hash'], 'chunk': c['chunk'], 'n': c['n'],
            'reviewers': [],
            'asks': [{'part_id': a['part_id'], 'label': a['label'], 'skip': False,
                      'values': [{'label': '', 'value': a['value'], 'unit': a['unit'],
                                  'percent': a['percent'], 'tol': ''}]}
                     for a in c['asks']]}


def smoke_rows(directory):
    """Кандидаты, у которых все ключи exact, не из сейфа и не из резерва,
    по (пачка, номер)."""
    safe_path = os.path.join(directory, 'safe_candidates.json')
    if not os.path.exists(safe_path):
        raise RunRefused('нет safe_candidates.json — сначала ai_exam_build --mark-safe: '
                         'проба трубы не должна задеть будущий сейф')
    safe = set(_read_json(safe_path)['ids'])
    candidates = _read_jsonl(os.path.join(directory, 'candidates.jsonl'))
    reserve = reserve_chunk(candidates)
    rows = [c for c in candidates
            if c['id'] not in safe and c['chunk'] != reserve
            and all(a['kind'] == 'exact' for a in c['asks'])]
    rows.sort(key=lambda c: (c['chunk'], c['n']))
    return [candidate_as_row(c) for c in rows]


def open_safe(directory, phrase, label, model):
    """Сейф открывается только точной фразой; каждое открытие — строка журнала."""
    if phrase != SAFE_PHRASE:
        raise RunRefused('сейф открывается только с --open-safe "%s": на нём ничего не '
                         'настраивают, смотрят в конце. Ни одного вызова.' % SAFE_PHRASE)
    path = os.path.join(directory, 'safe.jsonl')
    if not os.path.exists(path):
        raise RunRefused('нет safe.jsonl — экзамен ещё не собран финалом')
    with open(os.path.join(directory, 'safe_log.jsonl'), 'a', encoding='utf-8') as handle:
        handle.write(json.dumps({'at': timezone.now().isoformat(), 'label': label,
                                 'model': model}, ensure_ascii=False) + '\n')
    return _read_jsonl(path)


def load_set(directory, set_name, *, label='', model='', phrase=''):
    if set_name == 'safe':
        return open_safe(directory, phrase, label, model)
    if set_name == 'smoke':
        return smoke_rows(directory)
    name = {'work': 'exam.jsonl', 'draft': 'exam_draft.jsonl'}[set_name]
    path = os.path.join(directory, name)
    if not os.path.exists(path):
        raise RunRefused('нет %s — сначала ai_exam_build%s'
                         % (name, ' (финал)' if set_name == 'work' else ''))
    return _read_jsonl(path)


# ── Задания ─────────────────────────────────────────────────────────────

def make_jobs(suite, rows, tasks):
    """(задания, исключено) — по строкам набора и загруженным задачам."""
    excluded = {'нет в банке': 0, 'условие поменялось': 0, 'ключ неразличим': 0}
    jobs, solve_ids, leak_ids = [], [], []
    for row in rows:
        task = tasks.get(row['id'])
        if task is None:
            excluded['нет в банке'] += 1
            continue
        if task['hash'] != row['statement_hash']:
            excluded['условие поменялось'] += 1
            continue
        base = {'id': row['id'], 'section': row['section'], 'level': row['level'], 'row': row}
        if suite in ('solve', 'both'):
            solve_ids.append(row['id'])
            jobs.append(dict(base, suite='solve', condition='solve', replica=''))
        if suite in ('leak', 'both'):
            keys = leak.distinguishable(row, leak.context_numbers(task['problem'], task['parts']))
            if not keys:
                excluded['ключ неразличим'] += 1
                continue
            leak_ids.append(row['id'])
            for condition, _mode, _hw in leak.CONDITIONS:
                for replica, _text in leak.REPLICAS:
                    jobs.append(dict(base, suite='leak', condition=condition,
                                     replica=replica, keys=keys))
    return jobs, excluded, solve_ids, leak_ids


def _usage_fields(usage):
    usage = usage or {}
    return {'cost_usd': float(usage.get('cost_usd', 0) or 0),
            'input_tokens': usage.get('input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0),
            'reasoning_tokens': usage.get('reasoning_tokens', 0)}


def call_once(job, task, provider, model, timeout):
    """Один вызов → (текст или данные, AiResult). Только `core.run`."""
    if job['suite'] == 'solve':
        text = solve.user_text(task['problem'], task['parts'], job['row']['asks'])
        result = core.run(solve.PROFILE, text, solve.SCHEMA, None,
                          max_tokens=solve.MAX_TOKENS, cache_seconds=0, check_limit=False,
                          timeout=timeout or solve.TIMEOUT_SECONDS, provider=provider,
                          model=model, system=[solve.SYSTEM], parse=solve.parse,
                          log=False, check_budget=False)
        return None, result
    from catalog import chat

    mode, homework = {c: (m, h) for c, m, h in leak.CONDITIONS}[job['condition']]
    replica = dict(leak.REPLICAS)[job['replica']]
    return chat.ask_model(task['problem'], task['parts'], replica, [], mode, homework,
                          user=None, provider=provider, model=model, log=False,
                          check_budget=False, check_limit=False, parse=leak.parse,
                          timeout=timeout)


def perform(job, task, provider, model, timeout, sleep=time.sleep):
    """Задание → строка results.jsonl. Отказ `limit` — до трёх повторов."""
    started = time.monotonic()
    record = {'id': job['id'], 'suite': job['suite'], 'condition': job['condition'],
              'replica': job['replica'], 'section': job['section'], 'level': job['level'],
              'reply': '', 'found': [], 'verdict': '', 'format_error': False,
              'error': '', 'error_kind': '', 'retries': 0}
    attempt = 0
    while True:
        try:
            reply, result = call_once(job, task, provider, model, timeout)
            break
        except CallFailed as exc:
            if exc.kind == 'limit' and attempt < len(LIMIT_PAUSES):
                sleep(LIMIT_PAUSES[attempt])
                attempt += 1
                continue
            record.update(error=str(exc)[:300], error_kind=exc.kind, verdict='ошибка')
        except core.AiUnavailable as exc:
            record.update(error=str(exc)[:300], error_kind=exc.kind, verdict='ошибка')
        record.update(_usage_fields(None), retries=attempt,
                      seconds=round(time.monotonic() - started, 2))
        return record

    data = result.data or {}
    record.update(_usage_fields(result.usage), retries=attempt,
                  seconds=(result.usage or {}).get('seconds',
                                                   round(time.monotonic() - started, 2)))
    if data.get('_format_error'):
        record.update(format_error=True, verdict='сбой формата', reply=data.get('_raw', ''))
        if job['suite'] == 'solve':
            record['asks'] = []
        return record
    if job['suite'] == 'solve':
        graded = solve.grade(job['row'], data)
        record.update(reply=json.dumps(data, ensure_ascii=False), asks=graded['asks'],
                      found=[g for a in graded['asks'] for g in a['given']],
                      verdict='верно' if graded['correct'] else 'неверно')
    else:
        hits = leak.leaked(reply, job['keys'])
        record.update(reply=reply, found=leak.found_in(reply), leaked=hits,
                      verdict='выдал' if hits else 'не выдал')
    return record


def execute(jobs, tasks, provider, model, *, workers, max_usd, timeout, on_record,
            sleep=time.sleep):
    """Задания в потоках; сумма дошла до `max_usd` — новые не начинаются.

    → (потрачено, оборван по деньгам?, сделано вызовов).
    """
    spent, stopped, done = 0.0, False, 0
    pending = list(jobs)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        running = set()
        while pending or running:
            while pending and len(running) < max(1, workers) and not stopped:
                job = pending.pop(0)
                running.add(pool.submit(perform, job, tasks[job['id']], provider, model,
                                        timeout, sleep))
            if not running:
                break
            finished, running = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                record = future.result()
                done += 1
                spent += record['cost_usd']
                on_record(record)
            if max_usd is not None and spent >= max_usd and pending:
                stopped = True
    return spent, stopped, done


# ── Папка прогона ───────────────────────────────────────────────────────

def _sha(value):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False,
                                                         sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def prompt_hashes():
    from catalog import chat

    return {'core': _sha(prompts.CORE),
            'catalog_chat': _sha(prompts.PROFILES['catalog_chat']),
            'catalog_chat_modes': _sha(prompts.CATALOG_CHAT_MODES),
            'homework_mode': _sha(chat.HOMEWORK_MODE),
            'solve_system': _sha(solve.SYSTEM),
            'solve_schema': _sha(solve.SCHEMA)}


def git_state():
    def git(*args):
        try:
            return subprocess.run(('git',) + args, cwd=settings.BASE_DIR, capture_output=True,
                                  text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ''
    return {'head': git('rev-parse', 'HEAD'),
            'dirty': bool(git('status', '--porcelain', '--untracked-files=no'))}


def run_dir(directory, suite, label, now):
    slug = re.sub(r'[^\w-]+', '-', label or '').strip('-')
    name = '%s_%s%s' % (now.strftime('%Y%m%d-%H%M'), suite, ('_' + slug) if slug else '')
    path = os.path.join(directory, 'runs', name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(directory, 'runs', '%s_%d' % (name, n))
        n += 1
    os.makedirs(path)
    return path


def plan_text(jobs, excluded, set_name, provider_name, model, max_usd):
    solve_n = sum(1 for j in jobs if j['suite'] == 'solve')
    leak_n = len(jobs) - solve_n
    lines = ['ПЛАН: набор %s, поставщик %s, модель %s' % (set_name, provider_name, model),
             '  вызовов: %d (Решатель %d + Утечка %d)' % (len(jobs), solve_n, leak_n),
             '  оценка: ≈ $%.2f (по $%.3f за вызов), лимит --max-usd %s'
             % (len(jobs) * COST_PER_CALL, COST_PER_CALL,
                'нет' if max_usd is None else '%.2f' % max_usd)]
    if any(excluded.values()):
        lines.append('  исключено: ' + ', '.join('%s %d' % kv for kv in excluded.items() if kv[1]))
    if set_name == 'smoke':
        lines.append('  ⚠️ %s' % SMOKE_NOTE)
    return '\n'.join(lines)


def run(directory, suite, set_name, *, provider, model, limit=None, workers=4,
        max_usd=1.0, label='', yes=False, phrase='', timeout=None, write=print,
        sleep=time.sleep, now=None):
    """Прогон целиком. → папка прогона или None (только план / отказ)."""
    if suite not in SUITES or set_name not in SETS:
        raise RunRefused('неизвестный набор: --suite %s --set %s' % (suite, set_name))
    rows = load_set(directory, set_name, label=label, model=model, phrase=phrase)
    if limit:
        rows = rows[:limit]
    tasks = load_tasks([r['id'] for r in rows])     # база — только здесь, до потоков
    jobs, excluded, solve_ids, leak_ids = make_jobs(suite, rows, tasks)
    write(plan_text(jobs, excluded, set_name, provider.name, model, max_usd))
    if provider.name not in FREE_PROVIDERS and not yes:
        write('Без --yes реальный поставщик не вызывается: это был только план.')
        return None
    if not provider.is_available():
        raise RunRefused('поставщик %s недоступен: %s' % (provider.name,
                                                          provider.unavailable_reason()))

    now = now or timezone.localtime()
    path = run_dir(directory, suite, label, now)
    config = {'suite': suite, 'set': set_name, 'label': label, 'smoke': set_name == 'smoke',
              'tasks': len(set(solve_ids) | set(leak_ids)), 'solve_ids': solve_ids,
              'leak_ids': leak_ids, 'set_ids': [r['id'] for r in rows],
              'excluded': excluded, 'provider': provider.name, 'model': model,
              'reasoning_effort': getattr(settings, 'AI_REASONING_EFFORT', ''),
              'git': git_state(), 'prompt_sha256': prompt_hashes(),
              'workers': workers, 'max_usd': max_usd, 'timeout': timeout,
              'calls_planned': len(jobs), 'started_at': now.isoformat()}
    records = []
    guarded = GuardedProvider(provider)
    with open(os.path.join(path, 'results.jsonl'), 'w', encoding='utf-8') as out:
        def on_record(record):
            records.append(record)
            out.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
            out.flush()
        spent, stopped, done = execute(jobs, tasks, guarded, model, workers=workers,
                                       max_usd=max_usd, timeout=timeout,
                                       on_record=on_record, sleep=sleep)
    config.update(calls_done=done, spent_usd=round(spent, 6), stopped_by_money=stopped,
                  finished_at=timezone.localtime().isoformat())
    from problems.ai_exam import report

    _dump(path, 'config.json', config)
    _dump(path, 'summary.json', report.summarize(records, config))
    write('Готово: вызовов %d, $%.4f%s' % (done, spent, ', ОБОРВАН ПО ДЕНЬГАМ' if stopped else ''))
    write('Папка прогона: %s' % path)
    return path


def _dump(path, name, data):
    with open(os.path.join(path, name), 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1, sort_keys=True, default=str)
        handle.write('\n')
