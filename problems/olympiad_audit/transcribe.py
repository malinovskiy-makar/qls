# -*- coding: utf-8 -*-
"""Расшифровка страниц олимпиадных PDF зрячей моделью (GLM-5.3-Flash).

Страница PDF → картинка PNG → `core.run(images=…)` → JSON со списком
блоков (шапка, задание, продолжение, рисунок, решение, критерии). Пишет
ТОЛЬКО файлы в `digitized\\` папки аудита, в базу — ничего.

Качество проверяется по текстовому слою PDF, где он есть: слой — не
источник, а мерило (`layer_ratio`, `numbers_ok`). Не дотянула — один повтор
с усиленной инструкцией, не помогло — `needs_eyes`. Страницы без слоя
(сканы) — каждая 5-я на глаза и «модель-судья» для страниц с формулами,
таблицами и рисунками.

⚠️ ДЕНЬГИ. Ни одного вызова без `--yes`; `--max-usd` обязателен и
обрывает прогон (с запасом на вызовы в полёте). Расход каждого вызова —
строкой в `transcribe_cost.jsonl` СРАЗУ после ответа, до разбора: сбой
формата не теряет расход (терпимый разбор не бросает исключений).

⚠️ `core.run` ПИШЕТ AiUsageLog ПРИ ОТКАЗЕ ПОСТАВЩИКА ДАЖЕ С `log=False`
(карточка Notion «Надо», 08.10). Оцифровка в базу не пишет ничего,
поэтому на время прогона `core._log` подменяется подсчётом без записи
(`no_db_usage_log`). Файлы `problems/ai/` не меняются.

⚠️ Клиент openai внутри GLMProvider по умолчанию сам повторяет запрос до
двух раз (таймаут, 5xx) — такой повтор может быть оплачен. Поэтому
таймаут вызова щедрый (240 с), а наш повтор на `limit` — 5/15/45 с.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

from rapidfuzz import fuzz

from problems.olympiad_official import markup_free_key
from problems.text_dedup import extract_numeric_tokens

MODEL = 'glm-5.3-flash'
PROFILE = 'olympiad_digitize'
JUDGE_PROFILE = 'olympiad_digitize_judge'
MAX_TOKENS = 12000
TIMEOUT = 240
#: Повторы на отказ «лимит» (429 Z.AI): пауза перед попыткой, секунды.
LIMIT_BACKOFF = (5, 15, 45)
#: Порог сходства расшифровки с текстовым слоем.
LAYER_THRESHOLD = 0.90
#: Каждая N-я страница-скан — на глаза человеку.
SCAN_EYES_EVERY = 5
#: Оценка цены страницы до пилота, $ (замер фазы −1 — вырез таблицы
#: $0,00027; полная страница с длинным выходом заметно дороже).
DEFAULT_PAGE_USD = 0.005
CHECKPOINT_EVERY = 50

BLOCK_TYPES = ('header', 'task', 'task_continuation', 'figure', 'solution',
               'criteria', 'footer', 'noise')

SYSTEM_PROMPT = """Ты переписываешь страницу олимпиадных заданий по экономике. Верни JSON со списком блоков в порядке чтения.

Типы блоков:
- `header` — шапка: олимпиада, год, этап, класс, вариант (поля `olympiad`, `year`, `stage`, `grade`, `variant`; что не указано — пустая строка);
- `task` — задание: `number` (номер как в тексте: «1», «2.3», для теста — номер вопроса), `task_variant` (если на странице «Вариант K» одного задания), `title` (название, если есть), `points` (баллы, число или null), `text` — условие в Markdown;
- `task_continuation` — продолжение задания с предыдущей страницы (`number`, если виден, и `text`);
- `figure` — рисунок или график: `bbox` — рамка [x0, y0, x1, y1] в долях ширины/высоты страницы от 0 до 1000 (0,0 — левый верхний угол), `caption` — подпись, `number` — к какому заданию относится;
- `solution` — решение: `number` (номер задания), `text` — решение в Markdown, `answer` — ответ отдельно, если он выделен в тексте;
- `criteria` — критерии оценивания: `number`, `text` (критерии и баллы в Markdown), `points` — максимум за задание, если указан;
- `footer` / `noise` — колонтитулы, номера страниц, служебные надписи: только тип, текст НЕ переписывать.

Правила:
- Переписывай ДОСЛОВНО, весь текст страницы, ничего не пропуская и не сокращая. Не решай задания и не исправляй ошибки оригинала.
- Формулы — в LaTeX внутри `$…$` (выносные — `$$…$$`); дроби `\\frac{}{}`, индексы `Q_d`, степени `x^2`.
- Подпункты (а), б), 1), 2)…) — списком Markdown, каждый с новой строки.
- Варианты ответов в тесте — списком, как на странице.
- Таблицы — Markdown-таблицами (`| … | … |`), все строки и столбцы; объединённые ячейки повтори.
- Что не читается — `[нечитаемо]`.
- Не додумывай текст: если на странице нет задания — верни пустой список блоков.

Также верни флаги страницы: `has_formulas`, `has_table`, `has_figure` (true/false).

Ответ — ОДИН JSON-объект: {"blocks": [...], "has_formulas": …, "has_table": …, "has_figure": …}."""

RETRY_SUFFIX = """

ВНИМАНИЕ: прошлая расшифровка этой страницы разошлась с текстом PDF. Перепиши страницу ДОСЛОВНО, ничего не пропускай: каждый абзац, каждый подпункт, каждую строку и ячейку таблицы, все числа. Колонтитулы и номера страниц — по-прежнему не переписывай."""

JUDGE_PROMPT = """Ты проверяешь расшифровку страницы олимпиадных заданий по экономике. Тебе дана картинка страницы и расшифровка (Markdown, формулы в LaTeX). Сравни их и перечисли ПРОПУСКИ (текст есть на картинке, нет в расшифровке), ИСКАЖЕНИЯ (другие числа, слова, знаки, формулы, ячейки таблицы) и ЛИШНЕЕ (в расшифровке есть, на картинке нет). Колонтитулы и номера страниц не считаются. Не придирайся к оформлению Markdown и пробелам.

Ответ — ОДИН JSON-объект: {"ok": true/false, "issues": [{"kind": "пропуск|искажение|лишнее", "where": "где на странице", "detail": "что именно"}]}. Если расхождений нет — {"ok": true, "issues": []}."""

SCHEMA = {
    'type': 'object',
    'properties': {
        'blocks': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'type': {'type': 'string', 'enum': list(BLOCK_TYPES)},
                    'number': {'type': 'string'},
                    'task_variant': {'type': 'string'},
                    'title': {'type': 'string'},
                    'points': {'type': ['number', 'null']},
                    'text': {'type': 'string'},
                    'answer': {'type': 'string'},
                    'bbox': {'type': 'array', 'items': {'type': 'number'}},
                    'caption': {'type': 'string'},
                    'olympiad': {'type': 'string'},
                    'year': {'type': 'string'},
                    'stage': {'type': 'string'},
                    'grade': {'type': 'string'},
                    'variant': {'type': 'string'},
                },
                'required': ['type'],
            },
        },
        'has_formulas': {'type': 'boolean'},
        'has_table': {'type': 'boolean'},
        'has_figure': {'type': 'boolean'},
    },
    'required': ['blocks'],
}

JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'ok': {'type': 'boolean'},
        'issues': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'kind': {'type': 'string'}, 'where': {'type': 'string'},
                           'detail': {'type': 'string'}}}},
    },
    'required': ['ok', 'issues'],
}

KIND_LABELS = {'tasks': 'условия заданий', 'solutions': 'решения',
               'criteria': 'критерии оценивания', 'mixed': 'условия и решения/критерии',
               'other': 'материалы олимпиады'}


# ── Разбор ответа ────────────────────────────────────────────────────────

_FENCE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')


def tolerant_parse(text):
    """Ответ модели → dict, НИКОГДА не бросает исключение (иначе `core.run`
    потеряет расход вызова). Срезает обрамление ```, вырезает объект от
    первой `{` до последней `}`, массив оборачивает в `{"blocks": …}`.
    Не разобралось — `{'blocks': [], '_parse_error': …, '_raw': …}`."""
    raw = text or ''
    body = _FENCE.sub('', raw.strip())
    candidates = [body]
    start, end = body.find('{'), body.rfind('}')
    if 0 <= start < end:
        candidates.append(body[start:end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, list):
            data = {'blocks': data}
        if isinstance(data, dict):
            if not isinstance(data.get('blocks', []), list):
                data['blocks'] = []
            data.setdefault('blocks', [])
            return data
    return {'blocks': [], '_parse_error': 'не JSON', '_raw': raw[:20000]}


def clean_blocks(blocks):
    """Блоки как пришли → только словари с известным типом; поля-строки
    приведены к строкам. Неизвестный тип — `noise` с пометкой."""
    out = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        block = dict(block)
        kind = str(block.get('type') or '').strip()
        if kind not in BLOCK_TYPES:
            block['_type_was'] = kind
            kind = 'noise'
        block['type'] = kind
        for key in ('number', 'task_variant', 'title', 'text', 'answer', 'caption'):
            if key in block and block[key] is not None and not isinstance(block[key], str):
                block[key] = str(block[key])
        out.append(block)
    return out


# ── Сверка со слоем ──────────────────────────────────────────────────────

_PAGE_NUM = re.compile(r'^\s*(?:стр\.?|страница|page)?\s*\d{1,3}\s*(?:из\s*\d{1,3})?\s*$',
                       re.IGNORECASE)


def repeated_lines(page_layers):
    """Колонтитулы файла: строки, стоящие на половине страниц и больше
    (файл от 3 страниц). Модель их не переписывает, а в слое они есть."""
    if len(page_layers) < 3:
        return set()
    counts = Counter()
    for layer in page_layers:
        counts.update({' '.join(line.split()) for line in (layer or '').splitlines()
                       if line.strip()})
    return {line for line, n in counts.items() if n >= len(page_layers) / 2}


def layer_body(layer, footers=()):
    """Текстовый слой страницы без колонтитулов и номеров страниц."""
    lines = []
    for line in (layer or '').splitlines():
        norm = ' '.join(line.split())
        if not norm or norm in footers or _PAGE_NUM.match(norm):
            continue
        lines.append(norm)
    return '\n'.join(lines)


def transcript_text(blocks):
    """Всё, что модель переписала (без колонтитулов): для сверки со слоем."""
    parts = []
    for block in blocks:
        if block['type'] in ('footer', 'noise'):
            continue
        if block['type'] == 'header':
            parts.extend(str(block.get(k) or '') for k in
                         ('olympiad', 'year', 'stage', 'grade', 'variant', 'text'))
            continue
        for key in ('title', 'text', 'answer', 'caption'):
            if block.get(key):
                parts.append(block[key])
    return '\n'.join(p for p in parts if p)


_DECIMAL = re.compile(r'(\d)[.,](\d)')


def _numbers(text):
    return set(extract_numeric_tokens(_DECIMAL.sub(r'\1,\2', text or '')))


def layer_metrics(blocks, layer, footers=()):
    """(layer_ratio, numbers_ok, недостающие числа, лишние числа).

    `layer_ratio` — сходство ключей без разметки (LaTeX, пунктуация,
    регистр), НЕ зависящее от порядка слов (`token_sort_ratio`): таблица в
    слое PDF часто идёт по столбцам, а в Markdown — по строкам. Пропущенный
    абзац всё равно роняет его: недостающие слова — недостающие токены.
    Числа — множества после единой записи десятичной запятой."""
    body = layer_body(layer, footers)
    model_key = markup_free_key(transcript_text(blocks))
    layer_key = markup_free_key(body, pdf=True)
    if not layer_key:
        return None, None, [], []
    ratio = fuzz.token_sort_ratio(model_key, layer_key) / 100.0
    got, want = _numbers(transcript_text(blocks)), _numbers(body)
    missing, extra = sorted(want - got), sorted(got - want)
    return round(ratio, 4), not missing and not extra, missing, extra


def passes(metrics):
    ratio, numbers_ok = metrics[0], metrics[1]
    return ratio is not None and ratio >= LAYER_THRESHOLD and bool(numbers_ok)


def better(a, b):
    """Какая из двух попыток лучше: проходящая проверку, затем больший
    layer_ratio. a/b — словари попыток с ключом `metrics`."""
    def key(att):
        ratio, numbers_ok = att['metrics'][0], att['metrics'][1]
        return (passes(att['metrics']), bool(numbers_ok), ratio or 0.0)
    return a if key(a) >= key(b) else b


# ── Задание страницы ─────────────────────────────────────────────────────

class PageJob:
    """Одна страница к расшифровке."""

    def __init__(self, *, file, page_dir, page, pages, png, layer, has_layer,
                 kind, olympiad_name, footers=(), eyes_sample=False):
        self.file, self.page_dir, self.page, self.pages = file, page_dir, page, pages
        self.png, self.layer, self.has_layer = png, layer, has_layer
        self.kind, self.olympiad_name = kind, olympiad_name
        self.footers, self.eyes_sample = footers, eyes_sample

    @property
    def key(self):
        return f'{self.page_dir}/p{self.page}'

    def out_path(self, root):
        return os.path.join(root, self.page_dir, f'p{self.page}.json')

    def user_text(self, retry=False):
        text = (f'Олимпиада: {self.olympiad_name}. Файл: '
                f'{KIND_LABELS.get(self.kind, self.kind)}. Страница {self.page} '
                f'из {self.pages} (ключ {self.key}). Перепиши страницу на картинке.')
        return text + (RETRY_SUFFIX if retry else '')


#: Слой страницы короче этого ключа (без разметки) — считай, слоя нет:
#: подпись к рисунку или номер страницы мерилом не служат.
LAYER_MIN_KEY = 80


def build_jobs(inventory_rows, digitized, olympiad_name):
    """Страницы к расшифровке из инвентаря: PDF с `digitize=true`, не
    дубли, только отрисованные. Колонтитулы — по слою всего файла; каждая
    5-я страница-скан (по порядку файла и страницы) — выборка на глаза."""
    jobs, scans = [], 0
    for row in sorted(inventory_rows, key=lambda r: r['file']):
        if (not row.get('digitize') or row.get('duplicate_of')
                or row.get('ext', 'pdf') != 'pdf'):
            continue
        folder = os.path.join(digitized, row['page_dir'])
        pages = int(row.get('pages') or 0)
        layers = []
        for page in range(1, pages + 1):
            path = os.path.join(folder, f'p{page}.txt')
            layers.append(open(path, encoding='utf-8').read() if os.path.isfile(path) else '')
        footers = repeated_lines(layers)
        for page in range(1, pages + 1):
            png = os.path.join(folder, f'p{page}.png')
            if not os.path.isfile(png):
                continue
            body = layer_body(layers[page - 1], footers)
            has_layer = len(markup_free_key(body, pdf=True)) >= LAYER_MIN_KEY
            eyes = False
            if not has_layer:
                eyes = scans % SCAN_EYES_EVERY == 0
                scans += 1
            jobs.append(PageJob(file=row['file'], page_dir=row['page_dir'], page=page,
                                pages=pages, png=png, layer=layers[page - 1],
                                has_layer=has_layer, kind=row.get('kind', 'other'),
                                olympiad_name=olympiad_name, footers=footers,
                                eyes_sample=eyes))
    return jobs


def make_provider():
    """Боевой поставщик: GLM (Z.AI), ключ GLM_API_KEY из окружения."""
    from problems.ai import providers
    return providers.get_provider('glm')


def todo(jobs, root):
    """Страницы, которые ещё надо расшифровать (докачка: готовые — мимо)."""
    return [job for job in jobs if not page_done(job.out_path(root))]


def page_done(path):
    """Готова ли страница: есть json со статусом `ok` или `needs_eyes`
    (ошибка вызова и сбой формата — не готово, докачка повторит)."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle).get('status') in ('ok', 'needs_eyes')
    except (OSError, ValueError):
        return False


# ── Деньги и журнал ─────────────────────────────────────────────────────

def _no_db_usage_log(user, profile, provider_name, model, reply, seconds, ok=True,
                     note=''):
    """Замена `core._log` на время прогона: тот же расход словарём, но без
    строки AiUsageLog (см. шапку модуля)."""
    from problems.ai import core, providers
    if reply is None:
        reply = providers.Reply('')
    usage = core._usage_of(profile, provider_name, model, reply, seconds, ok=ok)
    usage['note'] = note
    return usage


@contextlib.contextmanager
def no_db_usage_log():
    from problems.ai import core
    original = core._log
    core._log = _no_db_usage_log
    try:
        yield
    finally:
        core._log = original


class Budget:
    """Потолок расхода прогона с запасом на вызовы в полёте."""

    def __init__(self, max_usd, per_call_estimate):
        self.max_usd = float(max_usd)
        self.estimate = float(per_call_estimate)
        self.spent = 0.0
        self.calls = 0
        self.lock = threading.Lock()

    def add(self, usd):
        with self.lock:
            self.spent += float(usd or 0)
            self.calls += 1

    def can_start(self, in_flight):
        with self.lock:
            return self.spent + (in_flight + 1) * self.estimate <= self.max_usd


class CostLog:
    """`transcribe_cost.jsonl` — строка на вызов, пишется сразу после ответа."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def write(self, record):
        record = dict(record, at=datetime.now().isoformat(timespec='seconds'))
        with self.lock, open(self.path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')

    def total(self):
        if not os.path.isfile(self.path):
            return 0.0, 0
        usd, calls = 0.0, 0
        with open(self.path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    usd += float(json.loads(line).get('cost_usd') or 0)
                    calls += 1
                except ValueError:
                    continue
        return usd, calls

    def average(self, kind='page'):
        """Средняя цена вызова этого вида по журналу; None — замеров нет."""
        if not os.path.isfile(self.path):
            return None
        values = []
        with open(self.path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get('call') == kind and rec.get('cost_usd') is not None:
                    values.append(float(rec['cost_usd']))
        return sum(values) / len(values) if values else None


# ── Прогон ───────────────────────────────────────────────────────────────

class Transcriber:
    """Расшифровка списка страниц: потоки, потолок денег, повторы, судья.

    `provider` — готовый поставщик (тест подставляет заглушку, боевой
    запуск — GLMProvider), `stdout` — куда печатать ход."""

    def __init__(self, *, root, provider, budget, cost_log, workers=20,
                 stdout=None, sleep=time.sleep):
        self.root, self.provider, self.budget = root, provider, budget
        self.cost_log, self.workers = cost_log, max(1, min(int(workers), 20))
        self.stdout = stdout
        self.sleep = sleep
        self.stats = Counter()
        self.stopped = ''

    def _say(self, text):
        if self.stdout is not None:
            self.stdout.write(text)

    # Один вызов модели с повторами на «лимит».
    def _call(self, job, system, user_text, schema, call_kind, profile):
        from problems.ai import core
        with open(job.png, 'rb') as handle:
            png = handle.read()
        last_error = None
        for attempt, pause in enumerate((0,) + LIMIT_BACKOFF):
            if pause:
                self.sleep(pause)
            try:
                result = core.run(
                    profile, user_text, schema, None, max_tokens=MAX_TOKENS,
                    cache_seconds=0, check_limit=False, timeout=TIMEOUT,
                    images=[('image/png', png)], provider=self.provider,
                    model=MODEL, system=[system], parse=tolerant_parse,
                    log=False, check_budget=False)
            except core.AiUnavailable as error:
                last_error = error
                self.cost_log.write({'page': job.key, 'call': call_kind, 'ok': False,
                                     'error': str(error)[:300], 'kind': error.kind,
                                     'cost_usd': 0.0, 'attempt': attempt + 1})
                if error.kind != 'limit':
                    break
                self.stats['повтор на лимит'] += 1
                continue
            usage = result.usage or {}
            cost = float(usage.get('cost_usd') or 0)
            self.budget.add(cost)
            self.cost_log.write({
                'page': job.key, 'call': call_kind, 'ok': True, 'cost_usd': cost,
                'input_tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens'),
                'reasoning_tokens': usage.get('reasoning_tokens'),
                'seconds': usage.get('seconds'),
                'parse_error': bool(result.data.get('_parse_error'))})
            return result.data, usage
        raise last_error

    def transcribe_page(self, job):
        """Страница → запись p<N>.json. Возвращает итоговый статус."""
        attempts = []
        data, usage = self._call(job, SYSTEM_PROMPT, job.user_text(), SCHEMA,
                                 'page', PROFILE)
        attempts.append(self._attempt(job, data, usage, retry=False))
        if job.has_layer and not passes(attempts[0]['metrics']):
            self.stats['повтор по слою'] += 1
            data, usage = self._call(job, SYSTEM_PROMPT, job.user_text(retry=True),
                                     SCHEMA, 'page_retry', PROFILE)
            attempts.append(self._attempt(job, data, usage, retry=True))
        best = attempts[0] if len(attempts) == 1 else better(*attempts)
        record = {
            'file': job.file, 'page_dir': job.page_dir, 'page': job.page,
            'pages': job.pages, 'kind': job.kind, 'png': os.path.basename(job.png),
            'has_layer': job.has_layer, 'blocks': best['blocks'],
            'flags': best['flags'], 'layer_ratio': best['metrics'][0],
            'numbers_ok': best['metrics'][1], 'numbers_missing': best['metrics'][2][:50],
            'numbers_extra': best['metrics'][3][:50], 'retries': len(attempts) - 1,
            'parse_error': best.get('parse_error', ''),
            'cost_usd': round(sum(a['cost_usd'] for a in attempts), 6),
            'model': MODEL, 'digitized_at': datetime.now().isoformat(timespec='seconds'),
        }
        reasons = []
        if best.get('parse_error'):
            reasons.append('сбой формата ответа')
        if job.has_layer and not passes(best['metrics']):
            reasons.append('расходится со слоем PDF')
        if not job.has_layer:
            if job.eyes_sample:
                reasons.append(f'скан: выборка каждой {SCAN_EYES_EVERY}-й страницы')
            flags = best['flags']
            if flags.get('has_formulas') or flags.get('has_table') or flags.get('has_figure'):
                verdict = self._judge(job, best['blocks'])
                record['judge'] = verdict
                if not verdict.get('ok', False) or verdict.get('issues'):
                    reasons.append('судья нашёл расхождения')
        record['needs_eyes'] = bool(reasons)
        record['needs_eyes_reasons'] = reasons
        record['status'] = ('error' if best.get('parse_error') and not best['blocks']
                            else 'needs_eyes' if reasons else 'ok')
        self._write(job.out_path(self.root), record)
        return record['status']

    def _attempt(self, job, data, usage, retry):
        blocks = clean_blocks(data.get('blocks'))
        flags = {k: bool(data.get(k)) for k in ('has_formulas', 'has_table', 'has_figure')}
        metrics = (layer_metrics(blocks, job.layer, job.footers) if job.has_layer
                   else (None, None, [], []))
        return {'blocks': blocks, 'flags': flags, 'metrics': metrics, 'retry': retry,
                'parse_error': data.get('_parse_error', ''),
                'raw': data.get('_raw', ''),
                'cost_usd': float((usage or {}).get('cost_usd') or 0)}

    def _judge(self, job, blocks):
        self.stats['судья'] += 1
        transcript = json.dumps(blocks, ensure_ascii=False)[:30000]
        user_text = (f'Страница {job.key}. Расшифровка (JSON-блоки):\n{transcript}')
        try:
            data, _usage = self._call(job, JUDGE_PROMPT, user_text, JUDGE_SCHEMA,
                                      'judge', JUDGE_PROFILE)
        except Exception as error:      # судья — не повод терять страницу
            return {'ok': False, 'issues': [], 'error': str(error)[:300]}
        if data.get('_parse_error'):
            return {'ok': False, 'issues': [], 'error': 'сбой формата судьи'}
        issues = data.get('issues') if isinstance(data.get('issues'), list) else []
        return {'ok': bool(data.get('ok')) and not issues, 'issues': issues[:30]}

    @staticmethod
    def _write(path, record):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def run(self, jobs):
        """Все страницы `jobs` (готовые уже отфильтрованы вызывающим)."""
        started = time.monotonic()
        done = 0
        pending = list(jobs)
        in_flight = {}
        with no_db_usage_log(), ThreadPoolExecutor(max_workers=self.workers) as pool:
            while pending or in_flight:
                while pending and len(in_flight) < self.workers:
                    if not self.budget.can_start(len(in_flight)):
                        self.stopped = (f'потолок ${self.budget.max_usd:.2f}: потрачено '
                                        f'${self.budget.spent:.4f}, ещё одна страница '
                                        'могла бы его превысить')
                        pending = []
                        break
                    job = pending.pop(0)
                    in_flight[pool.submit(self._safe_page, job)] = job
                if not in_flight:
                    break
                finished, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
                for future in finished:
                    in_flight.pop(future)
                    self.stats[future.result()] += 1
                    done += 1
                    if done % CHECKPOINT_EVERY == 0:
                        self._checkpoint(done, started)
        self._checkpoint(done, started, final=True)
        return self.stats

    def _safe_page(self, job):
        try:
            return self.transcribe_page(job)
        except Exception as error:      # страница с ошибкой — докачка повторит
            self.cost_log.write({'page': job.key, 'call': 'page', 'ok': False,
                                 'error': repr(error)[:300], 'cost_usd': 0.0})
            return 'error'

    def _checkpoint(self, done, started, final=False):
        state = {'done': done, 'stats': dict(self.stats),
                 'spent_usd_run': round(self.budget.spent, 6),
                 'calls_run': self.budget.calls,
                 'minutes': round((time.monotonic() - started) / 60, 1),
                 'stopped': self.stopped, 'final': final,
                 'at': datetime.now().isoformat(timespec='seconds')}
        self._write(os.path.join(self.root, 'transcribe_progress.json'), state)
        self._say(f'  [{state["at"]}] страниц {done}: {dict(self.stats)}; '
                  f'${state["spent_usd_run"]:.4f} за {state["minutes"]} мин')
