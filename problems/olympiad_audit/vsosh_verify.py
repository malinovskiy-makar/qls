# -*- coding: utf-8 -*-
"""ВсОШ v2 (сессия Q2): расшифровка регионов моделями не от Anthropic,
второе мнение, сведение и арбитр Claude.

Своя обёртка над форматом P3: промпт и схема ответа — `vsosh_digitize.CLAUDE_SYSTEM`
(тот же JSON блоков, что у GLM и Claude ночи 28.10), запись страницы — формат
`transcribe` (`blocks`, `status`, `model`, `cost_usd`), поэтому сборка
`assemble` читает её без переделки. Модули `claude_eyes.py`/`claude_recheck.py`
ветки `feat/olympiad-v7` — образец метода, здесь не импортируются.

Пишет ТОЛЬКО файлы в `digitized\\v2\\` папки ВсОШ, в базу — ничего; v1 не трогает.

⚠️ ДЕНЬГИ. Каждый вызов — строкой в `ledger_q2.jsonl` сразу после ответа
(поставщик, модель, фаза, $). Потолки сессии — `CAPS`; на 90 % потолка
новые вызовы и пакеты не отправляются (`Ledger.allow`).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

from problems.olympiad_audit import transcribe

#: $ за 1 млн токенов (вход, выход), сверено 28–29.10.2026. OpenRouter
#: присылает цену вызова сам (`usage.cost`), его модели здесь для сметы.
PRICES = {
    'gpt-6.1-sol': (2.00, 10.00),
    'gpt-6.1-terra': (1.00, 5.00),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-opus-5-5': (4.00, 20.00),
    'claude-haiku-5-5': (0.10, 0.50),
    'glm-5.3-flash': (0.15, 0.50),
    'google/gemini-4-argon': (2.00, 10.00),
    'qwen/qwen3.8-max-prime': (4.00, 12.00),
}
#: Пакетные API (OpenAI Batch, Anthropic Message Batches, `:batch` у OpenRouter) — вдвое дешевле.
BATCH_DISCOUNT = 0.5

#: Потолки сессии Q2 по поставщикам, $ (задание Q2, 29.10).
CAPS = {'anthropic': 35.0, 'openai': 25.0, 'openrouter': 35.0, 'glm': 3.0}
#: Доля потолка, после которой новые вызовы не отправляются.
CAP_SHARE = 0.9


def provider_of(model):
    if model.startswith('gpt-'):
        return 'openai'
    if model.startswith('claude-'):
        return 'anthropic'
    if model.startswith('glm-'):
        return 'glm'
    if '/' in model:
        return 'openrouter'
    raise ValueError(model)


def load_env(path=r'C:\Users\shipu\qls\.env'):
    """Ключи из .env владельца (не печатаются)."""
    out = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ── Журнал денег ───────────────────────────────────────────────────────

class Ledger:
    """Расход сессии: строка на вызов или пакет. Потолок — на поставщика."""

    def __init__(self, path, caps=None):
        self.path, self.caps = path, dict(caps or CAPS)
        self.lock = threading.Lock()

    def rows(self):
        if not os.path.isfile(self.path):
            return []
        with open(self.path, encoding='utf-8') as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def spent(self, provider=None, phase=None):
        return sum(float(r.get('usd') or 0) for r in self.rows()
                   if (provider is None or r.get('provider') == provider)
                   and (phase is None or r.get('phase') == phase))

    def allow(self, provider, extra=0.0):
        """Можно ли отправить ещё на `extra` $: не дальше 90 % потолка."""
        return self.spent(provider) + extra <= CAP_SHARE * self.caps[provider]

    def add(self, **rec):
        rec.setdefault('provider', provider_of(rec['model']))
        rec['ts'] = round(time.time())
        with self.lock, open(self.path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')


def call_usd(model, tin, tout, batch=False):
    pin, pout = PRICES[model]
    return (tin * pin + tout * pout) / 1e6 * (BATCH_DISCOUNT if batch else 1.0)


# ── Страницы ───────────────────────────────────────────────────────────

class Job:
    """Лёгкая страница к расшифровке (из кэша `jobs_cache.jsonl`): слой
    читается с диска по требованию — 18 967 слоёв в памяти не держим."""

    def __init__(self, root, row):
        self.root, self.row = root, row
        for k in ('key', 'group', 'file', 'page_dir', 'page', 'pages', 'kind',
                  'olympiad_name', 'has_layer'):
            setattr(self, k, row.get(k))
        self.footers = set(row.get('footers') or [])
        self.png = os.path.join(root, self.page_dir, f'p{self.page}.png')

    @property
    def layer(self):
        path = os.path.join(self.root, self.page_dir, f'p{self.page}.txt')
        if not os.path.isfile(path):
            return ''
        with open(path, encoding='utf-8') as fh:
            return fh.read()

    def user_text(self):
        return transcribe.PageJob.user_text(self)


def write_job_cache(root, path, groups=None):
    """Все страницы плана → `jobs_cache.jsonl` (группа, колонтитулы, есть ли слой)."""
    from problems.olympiad_audit import vsosh_digitize
    rows = []
    for g, job in vsosh_digitize.page_jobs(root, groups):
        rows.append({'key': job.key, 'group': g, 'file': job.file, 'page_dir': job.page_dir,
                     'page': job.page, 'pages': job.pages, 'kind': job.kind,
                     'olympiad_name': job.olympiad_name, 'has_layer': job.has_layer,
                     'footers': sorted(job.footers)})
    with open(path, 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    return len(rows)


def load_jobs(root, path):
    with open(path, encoding='utf-8') as fh:
        return {j.key: j for j in (Job(root, json.loads(x)) for x in fh if x.strip())}


# ── Запрос ─────────────────────────────────────────────────────────────

#: Длинная сторона картинки: как у пакетов Claude P3 (1568) — модели всё
#: равно ужимают; GPT при `detail: high` режет на плитки 512 px.
MAX_SIDE = 1568


def image_b64(path, max_side=MAX_SIDE):
    """PNG/JPEG страницы → (media_type, base64); как `vsosh_digitize.page_image_b64`."""
    from problems.olympiad_audit.vsosh_digitize import page_image_b64
    return page_image_b64(path, max_side)


def system_prompt():
    from problems.olympiad_audit.vsosh_digitize import CLAUDE_SYSTEM
    return CLAUDE_SYSTEM


def user_text(job):
    """Текст запроса — как у пакетов Claude P3: страница + слой-подсказка."""
    from problems.olympiad_audit.vsosh_digitize import LAYER_HINT_CHARS
    layer = transcribe.layer_body(job.layer, job.footers)[:LAYER_HINT_CHARS]
    return job.user_text() + ('\n\nТекстовый слой PDF (подсказка):\n<<<\n' + layer + '\n>>>'
                              if layer.strip() else '\n\nТекстового слоя нет (скан).')


def openai_body(model, job, effort='low', max_tokens=12000):
    mt, data = image_b64(job.png)
    return {'model': model, 'max_completion_tokens': max_tokens, 'reasoning_effort': effort,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system_prompt()},
                         {'role': 'user', 'content': [
                             {'type': 'image_url', 'image_url': {
                                 'url': f'data:{mt};base64,{data}', 'detail': 'high'}},
                             {'type': 'text', 'text': user_text(job)}]}]}


def openrouter_body(model, job, effort='low', max_tokens=12000):
    mt, data = image_b64(job.png)
    return {'model': model, 'max_tokens': max_tokens, 'usage': {'include': True},
            'reasoning': {'effort': effort},
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system_prompt()},
                         {'role': 'user', 'content': [
                             {'type': 'image_url', 'image_url': {'url': f'data:{mt};base64,{data}'}},
                             {'type': 'text', 'text': user_text(job)}]}]}


def anthropic_params(model, job, effort='low', max_tokens=12000):
    mt, data = image_b64(job.png)
    return {'model': model, 'max_tokens': max_tokens,
            'system': [{'type': 'text', 'text': system_prompt(),
                        'cache_control': {'type': 'ephemeral'}}],
            'output_config': {'effort': effort},
            'messages': [{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': data}},
                {'type': 'text', 'text': user_text(job)}]}]}


def _post(url, headers, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=dict(headers, **{'content-type': 'application/json'}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def call(model, body, env, timeout=300):
    """Синхронный вызов → (текст, вход, выход, $). Тело — из `*_body`."""
    prov = provider_of(model)
    if prov == 'openai':
        d = _post('https://api.openai.com/v1/chat/completions',
                  {'authorization': 'Bearer ' + env['OPENAI_API_KEY']}, body, timeout)
        u = d.get('usage') or {}
        tin, tout = u.get('prompt_tokens', 0), u.get('completion_tokens', 0)
        return (d['choices'][0]['message'].get('content') or '', tin, tout,
                call_usd(model, tin, tout))
    if prov == 'openrouter':
        d = _post('https://openrouter.ai/api/v1/chat/completions',
                  {'authorization': 'Bearer ' + env['OPENROUTER_API_KEY']}, body, timeout)
        if 'choices' not in d:
            raise RuntimeError(str(d.get('error') or d)[:300])
        u = d.get('usage') or {}
        return (d['choices'][0]['message'].get('content') or '', u.get('prompt_tokens', 0),
                u.get('completion_tokens', 0), float(u.get('cost') or 0))
    if prov == 'glm':
        d = _post('https://api.z.ai/api/paas/v4/chat/completions',
                  {'authorization': 'Bearer ' + env['GLM_API_KEY']}, body, timeout)
        u = d.get('usage') or {}
        tin, tout = u.get('prompt_tokens', 0), u.get('completion_tokens', 0)
        return (d['choices'][0]['message'].get('content') or '', tin, tout,
                call_usd(model, tin, tout))
    if prov == 'anthropic':
        headers = {'x-api-key': env['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'}
        if env.get('ANTHROPIC_WORKSPACE_ID'):
            headers['anthropic-workspace-id'] = env['ANTHROPIC_WORKSPACE_ID']
        d = _post('https://api.anthropic.com/v1/messages', headers, body, timeout)
        u = d.get('usage') or {}
        tin = (u.get('input_tokens') or 0) + 1.25 * (u.get('cache_creation_input_tokens') or 0) \
            + 0.1 * (u.get('cache_read_input_tokens') or 0)
        text = ''.join(b.get('text', '') for b in d.get('content', []) if b.get('type') == 'text')
        return text, tin, u.get('output_tokens', 0), call_usd(model, tin, u.get('output_tokens', 0))
    raise ValueError(model)


def glm_body(model, job, max_tokens=12000):
    """GLM-5.3-Flash (Z.AI): как у P4 `ocr.py` — рассуждение low."""
    mt, data = image_b64(job.png)
    return {'model': model, 'max_tokens': max_tokens, 'thinking': {'type': 'enabled'},
            'reasoning_effort': 'low',
            'messages': [{'role': 'system', 'content': system_prompt()},
                         {'role': 'user', 'content': [
                             {'type': 'image_url', 'image_url': {'url': f'data:{mt};base64,{data}'}},
                             {'type': 'text', 'text': user_text(job)}]}]}


def body_for(model, job, effort='low'):
    prov = provider_of(model)
    if prov == 'glm':
        return glm_body(model, job)
    if prov == 'openai':
        return openai_body(model, job, effort)
    if prov == 'openrouter':
        return openrouter_body(model, job, effort)
    return anthropic_params(model, job, effort)


def call_with_retry(model, body, env, tries=4):
    """Повтор на 429/5xx/обрыв: 10/30/90 с. 4xx (кроме 429) — сразу ошибка."""
    for attempt in range(tries):
        try:
            return call(model, body, env)
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 409, 429, 500, 502, 503, 504, 529) or attempt == tries - 1:
                raise RuntimeError(f'HTTP {exc.code}: {exc.read()[:300]!r}') from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError):
            if attempt == tries - 1:
                raise
        time.sleep((10, 30, 90, 180)[attempt])


def make_record(key, text, model, usd, extra=None):
    """Ответ модели → запись страницы в формате `transcribe` (как `claude_record`)."""
    data = transcribe.tolerant_parse(text)
    blocks = transcribe.clean_blocks(data.get('blocks'))
    page_dir, _, page = key.rpartition('/p')
    rec = {'page_dir': page_dir, 'page': int(page), 'blocks': blocks,
           'status': 'ok' if blocks or (not data.get('_parse_error') and 'blocks' in data) else 'error',
           'parse_error': data.get('_parse_error', ''), 'model': model,
           'cost_usd': round(usd, 6),
           'flags': {k: bool(data.get(k)) for k in ('has_formulas', 'has_table', 'has_figure')}}
    rec.update(extra or {})
    return rec


def write_record(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_record(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


# ── Метрики страницы ───────────────────────────────────────────────────

_NUM_RE = re.compile(r'(?<![\w.])[-−]?\d+(?:[.,]\d+)?')


def _norm_num(s):
    s = s.replace('−', '-').replace(',', '.').lstrip('-')
    try:
        v = float(s)
    except ValueError:
        return None
    return ('%.4f' % v).rstrip('0').rstrip('.')


def numbers(text):
    """Числа текста мультимножеством (разбор P4 `ocr_compare`, исправленный):
    TeX-запятая «49{,}9» и «1\\,000» — одно число; «1 000 000» — одно;
    метка варианта не склеивается с числом («2) 500» — два числа)."""
    t = (text or '').replace('{,}', ',').replace('{.}', '.')
    t = re.sub(r'(?<=\d)(?:\\[,;:! ]|~|\\thinspace\s?)(?=\d{3}(?!\d))', '', t)
    t = re.sub(r'(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))', '', t)
    return Counter(n for n in (_norm_num(x) for x in _NUM_RE.findall(t)) if n is not None)


#: Вариант ответа — строка с меткой («а)», «(b)», «1.», «- 2)»); голый пункт
#: списка не считается: модели по-разному режут решения на пункты.
_OPTION_LINE = re.compile(r'(?m)^\s*(?:[-*+]\s+)?(?:\*\*)?\(?(?:[а-еa-eА-ЕA-E]|[1-9])[.)]')
_TABLE_ROW = re.compile(r'(?m)^\s*\|(?![\s|:-]*$).*\|\s*$')
_WORD3 = re.compile(r'[а-яёa-z]{3,}')


def structure(blocks):
    """Структура страницы: номера условий заданий по порядку (без повторов
    подряд — продолжение задания), варианты, строки таблиц, рисунки. Номера
    блоков решений и критериев не сравниваются: модели по-разному режут
    файл «вопрос — решение» на блоки, а текст при этом одинаков."""
    tasks = []
    for b in blocks:
        num = re.sub(r'(?i)^(?:задача|задание|вопрос)\s*№?\s*', '', str(b.get('number') or '')).strip(' .')
        if b['type'] == 'task' and num and (not tasks or tasks[-1] != num):
            tasks.append(num)
    text = content_text(blocks)
    return {'numbers': tasks, 'options': len(_OPTION_LINE.findall(text)),
            'table_rows': len(_TABLE_ROW.findall(text)),
            'figures': sum(1 for b in blocks if b['type'] == 'figure')}


def body_text(blocks):
    return transcribe.transcript_text(blocks)


_LIST_LABEL = re.compile(r'(?m)^\s*(?:[-*+]\s+)?(?:\*\*)?\(?\d{1,2}[.)](?=\s|\*)')


def compare_numbers(blocks):
    """Числа для сведения двух версий: МНОЖЕСТВО чисел текста, ответа и
    подписей, без меток списков («3)», «5. Задачи»). Множество, а не
    мультимножество: число из текста модели по-разному повторяют в `answer`."""
    text = '\n'.join(str(b.get(k) or '') for b in blocks
                     if b['type'] not in ('footer', 'noise', 'header')
                     for k in ('text', 'answer', 'caption'))
    return set(numbers(_LIST_LABEL.sub(' ', text)))


def content_text(blocks):
    """Только текст страницы (text, caption) — без полей-меток
    `number`/`points`/`title` и без `answer`: одна модель пишет «Задача 3
    (20 баллов)» в текст, другая — в поля; в `answer` одна кладёт номер
    варианта, другая — его полный текст (калибровка арбитра 29.10: 15 из 16
    «расхождений» были такими, текст страницы совпадал)."""
    return '\n'.join(str(b.get(k) or '') for b in blocks
                     if b['type'] not in ('footer', 'noise', 'header')
                     for k in ('text', 'caption'))


def page_metrics(rec, job):
    """Метрики расшифровки без людей. Слой — мерило, не источник:
    `num_recall` — доля чисел слоя (без колонтитулов), найденных у модели;
    `num_precision` — доля чисел модели, которые есть в слое страницы
    (иначе выдумка или ошибка чтения); `word_f1` — `layer_ratio` P3;
    `fabricated_words` — доля слов модели, которых нет во всём слое."""
    blocks = transcribe.clean_blocks((rec or {}).get('blocks'))
    text = body_text(blocks)
    out = {'status': (rec or {}).get('status'), 'usd': (rec or {}).get('cost_usd'),
           'structure': structure(blocks), 'chars': len(text)}
    if not job.has_layer:
        return out
    body = transcribe.layer_body(job.layer, job.footers, job.page)
    want, got, full = numbers(body), numbers(text), numbers(job.layer)
    head = numbers(transcribe.transcript_text(blocks, header=True))
    inter = sum((got & want).values())
    out['num_recall'] = inter / sum(want.values()) if want else None
    good = sum((got & (full + head)).values())
    out['num_precision'] = good / sum(got.values()) if got else None
    ratio, ok, missing, extra, _f = transcribe.layer_metrics(blocks, job.layer, job.footers, job.page)
    out.update(word_f1=ratio, numbers_ok=ok, missing=missing[:10], extra=extra[:10])
    from problems.olympiad_official import markup_free_key
    mw = Counter(_WORD3.findall(markup_free_key(text)))
    lw = Counter(_WORD3.findall(markup_free_key(job.layer, pdf=True)))
    out['fabricated_words'] = (sum((mw - lw).values()) / sum(mw.values())) if mw else None
    return out


# ── Сведение двух мнений ───────────────────────────────────────────────

def agree(rec_a, rec_b, kind='tasks'):
    """Совпали ли две расшифровки «по числам и структуре» (правило Q2, как P2):
    одинаковое мультимножество чисел текста, одинаковые номера заданий по
    порядку, число вариантов и строк таблиц. → (bool, причины расхождения)."""
    ba = transcribe.clean_blocks((rec_a or {}).get('blocks'))
    bb = transcribe.clean_blocks((rec_b or {}).get('blocks'))
    why = []
    if (rec_a or {}).get('status') != 'ok' or (rec_b or {}).get('status') != 'ok':
        return False, ['нет_ответа']
    if compare_numbers(ba) != compare_numbers(bb):
        why.append('числа')
    sa, sb = structure(ba), structure(bb)
    # Номера условий сравниваются только на странице условий: в файле
    # решений «задание или критерий» — выбор разметки, а не текста.
    fields = ('numbers', 'options', 'table_rows', 'figures') if kind not in (
        'solutions', 'criteria') else ('options', 'table_rows', 'figures')
    for k in fields:
        if sa[k] != sb[k]:
            why.append({'numbers': 'номера', 'options': 'варианты', 'table_rows': 'таблицы',
                        'figures': 'рисунки'}[k])
    return not why, why


# ── Калибровка (фаза 1) ────────────────────────────────────────────────

_FORMULA_HINT = re.compile(r'[=<>≤≥^]|\bln\b|√')
_OPTION_HINT = re.compile(r'(?m)^\s*(?:[а-еa-e]\)|[1-5]\))\s+\S')
_FIGURE_HINT = re.compile(r'(?i)рис\w*|график\w*|диаграмм\w*|изображ\w*')


def page_features(job, pdf_path=''):
    """Признаки формата страницы для стратифицированной выборки."""
    layer = job.layer or ''
    lines = [ln for ln in layer.splitlines() if ln.strip()]
    short_num = sum(1 for ln in lines if len(ln) < 14 and re.search(r'\d', ln))
    return {'scan': not job.has_layer, 'word': 'converted/' in pdf_path.replace(chr(92), '/'),
            'formula': len(_FORMULA_HINT.findall(layer)) >= 4,
            'options': len(_OPTION_HINT.findall(layer)) >= 3,
            'figure': bool(_FIGURE_HINT.search(layer)),
            'table': short_num >= 12, 'solution': job.kind in ('solutions', 'criteria')}


def page_events(root):
    """page_dir → (этап, сезон, регион) по файлам комплектов."""
    files = [json.loads(x) for x in open(os.path.join(root, 'events_files.jsonl'), encoding='utf-8')]
    meta = {m['event_id']: m for m in (json.loads(x) for x in
                                       open(os.path.join(root, 'events_meta.jsonl'), encoding='utf-8'))}
    out = {}
    for ev in files:
        m = meta.get(ev['event_id'], {})
        for key in ('task_files', 'solution_files', 'criteria_files'):
            for f in ev.get(key) or []:
                out.setdefault(f['page_dir'], (m.get('stage'), m.get('academic_year'),
                                               m.get('region_name') or ''))
    return out


def calib_sample(jobs, root, todo_keys, control_keys, n=40, n_control=10, seed=20261029):
    """40 нечитанных страниц МЭ/ШЭ регионов: сначала по 4 на каждый признак
    формата (скан, Word, формулы, варианты, рисунок, таблица, решение), затем
    добор — разные регионы и сезоны. Плюс `n_control` страниц ЗЭ/РЭ,
    прочитанных Sonnet в P3, — контроль. Порядок детерминирован (`seed`)."""
    import random
    rnd = random.Random(seed)
    evs = page_events(root)
    pdfs = {x['page_dir']: x['pdf'] for x in (json.loads(y) for y in open(
        os.path.join(root, 'render_index.jsonl'), encoding='utf-8'))}
    cand = [jobs[k] for k in sorted(todo_keys) if k in jobs]
    rnd.shuffle(cand)
    feats = {j.key: page_features(j, pdfs.get(j.page_dir, '')) for j in cand}
    picked, regions, files = [], Counter(), set()

    def take(j):
        picked.append(j.key)
        regions[evs.get(j.page_dir, ('', '', ''))[2]] += 1
        files.add(j.page_dir)

    for feat in ('scan', 'word', 'formula', 'options', 'figure', 'table', 'solution'):
        got = 0
        for j in cand:
            if got >= 4 or len(picked) >= n:
                break
            if j.key in picked or j.page_dir in files or not feats[j.key][feat]:
                continue
            if regions[evs.get(j.page_dir, ('', '', ''))[2]] >= 2:
                continue
            take(j)
            got += 1
    seasons = Counter(evs.get(jobs[k].page_dir, ('', '', ''))[1] for k in picked)
    for per_region, per_season in ((2, 4), (3, 6), (4, 9)):   # добор, ослабляя разброс
        for j in cand:
            if len(picked) >= n:
                break
            ev = evs.get(j.page_dir, ('', '', ''))
            if (j.key in picked or j.page_dir in files or regions[ev[2]] >= per_region
                    or seasons[ev[1]] >= per_season):
                continue
            take(j)
            seasons[ev[1]] += 1
    ctrl = sorted(control_keys)
    rnd.shuffle(ctrl)
    out = [{'key': k, 'set': 'region', **dict(zip(('stage', 'season', 'region'),
                                                   evs.get(jobs[k].page_dir, ('', '', '')))),
            'features': feats[k]} for k in picked]
    seen_dirs = set()
    for k in ctrl:
        if len([x for x in out if x['set'] == 'control']) >= n_control:
            break
        if k not in jobs or jobs[k].page_dir in seen_dirs:
            continue
        seen_dirs.add(jobs[k].page_dir)
        out.append({'key': k, 'set': 'control', **dict(zip(('stage', 'season', 'region'),
                                                            evs.get(jobs[k].page_dir, ('', '', '')))),
                    'features': page_features(jobs[k], pdfs.get(jobs[k].page_dir, ''))})
    return out


def rec_path(folder, model, key):
    page_dir, _, page = key.rpartition('/p')
    return os.path.join(folder, model.replace('/', '__').replace(':', '_'),
                        page_dir.split('/')[-1], f'p{page}.json')


def run_pages(model, keys, jobs, folder, env, ledger, phase, workers=6, effort='low',
              log=print):
    """Синхронная расшифровка страниц моделью (калибровка, малые объёмы):
    готовые записи — мимо; потолок поставщика проверяется перед каждым вызовом."""
    from concurrent.futures import ThreadPoolExecutor
    prov = provider_of(model.split(':')[0]) if ':' in model else provider_of(model)
    todo = [k for k in keys if not (read_record(rec_path(folder, model, k)) or {}).get('status') == 'ok']
    stats = Counter()

    def one(key):
        if not ledger.allow(prov, 0.05):
            stats['стоп_потолок'] += 1
            return
        t0 = time.time()
        try:
            text, tin, tout, usd = call_with_retry(model, body_for(model, jobs[key], effort), env)
        except Exception as exc:  # noqa: BLE001 — сбой одной страницы не роняет прогон
            stats['ошибка'] += 1
            log(f'  {model} {key}: {str(exc)[:200]}')
            return
        ledger.add(model=model, provider=prov, phase=phase, key=key, usd=round(usd, 6),
                   tin=tin, tout=tout, seconds=round(time.time() - t0, 1))
        rec = make_record(key, text, model, usd, {'tin': tin, 'tout': tout})
        write_record(rec_path(folder, model, key), rec)
        stats[rec['status']] += 1

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    return dict(stats)


def layer_check(rec, job):
    """Числа версии против текстового слоя страницы → (недостающие, лишние):
    числа слоя (без колонтитулов) — должны быть у версии; числа версии —
    должны быть во всём слое страницы или в шапке."""
    blocks = transcribe.clean_blocks((rec or {}).get('blocks'))
    got = set(numbers(content_text(blocks)))
    want = set(numbers(transcribe.layer_body(job.layer, job.footers, job.page)))
    full = set(numbers(job.layer)) | set(numbers(transcribe.transcript_text(blocks, header=True)))
    return sorted(want - got), sorted(got - full)


def layer_tiebreak(rec_a, rec_b, job, why):
    """Расхождение ТОЛЬКО в числах, у страницы есть текстовый слой: если одна
    версия со слоем сходится полностью (ни одного недостающего и лишнего
    числа), а другая — нет, слой рассудил: → 'A' / 'B'. Иначе None (арбитру).
    Слой здесь мерило, не источник: текст берётся из версии модели целиком."""
    if why != ['числа'] or not job.has_layer:
        return None
    ba = transcribe.clean_blocks((rec_a or {}).get('blocks'))
    bb = transcribe.clean_blocks((rec_b or {}).get('blocks'))
    na, nb = compare_numbers(ba), compare_numbers(bb)
    body = set(numbers(transcribe.layer_body(job.layer, job.footers, job.page)))
    full = set(numbers(job.layer))
    only_a, only_b = na - nb, nb - na

    def wins(mine, theirs):
        # Каждое число победителя, которого нет у соперника, есть в теле
        # слоя (соперник его потерял); каждое число соперника, которого нет
        # у победителя, отсутствует во всём слое (выдумка или ошибка чтения).
        return mine <= body and not (theirs & full) and bool(mine or theirs)
    a_wins = wins(only_a, only_b)
    b_wins = wins(only_b, only_a)
    if a_wins != b_wins:
        return 'A' if a_wins else 'B'
    return None


# ── Арбитр расхождений (Claude Sonnet) ─────────────────────────────────

ARBITER_MODEL = 'claude-sonnet-5-5'
#: Правило приёма решения арбитра — как у P2 (`claude_recheck`): уверенность
#: не ниже 0,9 и дословная цитата со страницы, найденная в текстовом слое.
MIN_CONFIDENCE = 0.9
#: 0,75–0,9 — повтор с effort `high` (если хватает денег).
RETRY_CONFIDENCE = (0.75, MIN_CONFIDENCE)
EVIDENCE_SHARE = 0.7
MIN_LAYER = 200
ARBITER_DECISIONS = ('A', 'B', 'fix', 'human')

ARBITER_SYSTEM = """Ты — арбитр расшифровки страницы олимпиадных заданий по экономике. Две независимые модели переписали одну страницу в JSON блоков (схема ниже), и их версии РАСХОДЯТСЯ — по числам, номерам заданий, вариантам ответа, строкам таблиц или рисункам. Тебе дана картинка страницы (источник правды), текстовый слой PDF (подсказка: числа и слова обычно верны, формулы в нём рассыпаны) и обе версии.

Реши по картинке:
- "A" — версия A верна (расхождения — ошибки B);
- "B" — версия B верна;
- "fix" — обе ошибаются; верни в `blocks` ПОЛНЫЙ исправленный список блоков страницы в той же схеме (за основу — лучшую версию, исправь только то, что расходится с картинкой);
- "human" — по картинке не разобрать (мелко, размыто, неоднозначно) или сомневаешься.

Правила: переписывай ДОСЛОВНО, ничего не решай и не исправляй ошибки оригинала. Различия в оформлении Markdown, пробелах, переносах и выборе разметки формулы, не меняющие смысла, — НЕ ошибки: выбирай по существу (числа, слова, знаки, пункты, варианты, ячейки таблиц, рамки рисунков).

`evidence` — ОБЯЗАТЕЛЬНО: дословная цитата со страницы (несколько слов подряд, как напечатано), которая доказывает решение — то место, где версии расходятся. `confidence` — от 0 до 1; 0.9 и выше — только если уверен полностью, иначе "human".

Ответ — ОДИН JSON-объект без текста вокруг: {"decision": "A"|"B"|"fix"|"human", "differences": ["коротко: что где расходится и кто прав"], "evidence": "…", "confidence": 0.95, "blocks": [...только для fix...]}

Схема блоков:
"""


def compact_blocks(rec):
    """Блоки версии для арбитра: без служебных полей и пустых значений."""
    out = []
    for b in transcribe.clean_blocks((rec or {}).get('blocks')):
        if b['type'] in ('footer', 'noise'):
            out.append({'type': b['type']})
            continue
        out.append({k: v for k, v in b.items()
                    if k in transcribe.SCHEMA['properties']['blocks']['items']['properties']
                    and v not in (None, '', [])})
    return out


def arbiter_params(job, rec_a, rec_b, why, model=ARBITER_MODEL, effort='medium',
                   max_tokens=16000):
    mt, data = image_b64(job.png)
    layer = transcribe.layer_body(job.layer, job.footers)[:6000]
    text = (f'Страница: {job.key} ({job.olympiad_name}; '
            f'{transcribe.KIND_LABELS.get(job.kind, job.kind)}, стр. {job.page} из {job.pages}).\n'
            f'Найденные расхождения: {", ".join(why)}.\n\n'
            + ('Текстовый слой PDF:\n<<<\n' + layer + '\n>>>\n\n' if layer.strip()
               else 'Текстового слоя нет (скан).\n\n')
            + 'Версия A:\n' + json.dumps(compact_blocks(rec_a), ensure_ascii=False)
            + '\n\nВерсия B:\n' + json.dumps(compact_blocks(rec_b), ensure_ascii=False))
    return {'model': model, 'max_tokens': max_tokens,
            'system': [{'type': 'text', 'text': ARBITER_SYSTEM + json.dumps(
                transcribe.SCHEMA, ensure_ascii=False), 'cache_control': {'type': 'ephemeral'}}],
            'output_config': {'effort': effort},
            'messages': [{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': data}},
                {'type': 'text', 'text': text}]}]}


_WORD_EV = re.compile(r'[^\W\d_]{3,}')


def evidence_on_page(evidence, layer, share=EVIDENCE_SHARE):
    """Цитата со страницы (правило P2): у скана без слоя — непустая; со слоем —
    ≥ `share` слов цитаты есть в слое и все числа цитаты тоже. Перенос слова
    в слое склеивается."""
    evidence = (evidence or '').strip()
    if len(evidence) < 8:
        return False
    layer = re.sub(r'-\s*\n\s*', '', layer or '')
    if len(layer.strip()) < MIN_LAYER:
        return True
    if numbers(evidence) - numbers(layer):
        return False
    words = [w.lower() for w in _WORD_EV.findall(evidence)]
    have = {w.lower() for w in _WORD_EV.findall(layer)}
    if not words:
        return True
    return sum(1 for w in words if w in have) >= share * len(words)


def judge_arbiter(reply_text, job, rec_a, rec_b):
    """Ответ арбитра → (итог, запись страницы или None, причины).

    Итог: `accept_A`/`accept_B`/`accept_fix` — принято по правилу;
    `retry` — уверенность 0,75–0,9 (спросить ещё раз с effort high);
    `human` — в очередь людям. Правка (`fix`) принимается, только если в ней
    нет чисел, которых нет в слое страницы (у скана — без этой проверки)."""
    data = transcribe.tolerant_parse(reply_text)
    dec = str(data.get('decision') or '').strip()
    try:
        conf = float(data.get('confidence') or 0)
    except (TypeError, ValueError):
        conf = 0.0
    why = []
    if dec not in ARBITER_DECISIONS:
        return 'human', None, ['ответ_не_разобран'], data
    if dec == 'human':
        return 'human', None, ['арбитр: человеку'], data
    if not evidence_on_page(data.get('evidence'), job.layer):
        why.append('нет_цитаты_со_страницы')
    if conf < MIN_CONFIDENCE:
        why.append(f'уверенность_{conf:.2f}')
    rec = {'A': rec_a, 'B': rec_b}.get(dec)
    if dec == 'fix':
        blocks = transcribe.clean_blocks(data.get('blocks'))
        if not blocks:
            why.append('правка_пустая')
        elif job.has_layer:
            extra = numbers(body_text(blocks)) - numbers(job.layer) \
                - numbers(transcribe.transcript_text(blocks, header=True))
            if extra:
                why.append('правка_с_числами_не_со_страницы')
        rec = dict(rec_a or {}, blocks=blocks, status='ok' if blocks else 'error')
    if why:
        if why == [f'уверенность_{conf:.2f}'] and RETRY_CONFIDENCE[0] <= conf < RETRY_CONFIDENCE[1]:
            return 'retry', None, why, data
        return 'human', None, why, data
    return f'accept_{dec}', rec, [], data
