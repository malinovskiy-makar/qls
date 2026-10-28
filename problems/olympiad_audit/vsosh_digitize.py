# -*- coding: utf-8 -*-
"""ВсОШ: оцифровка страниц, пакеты Claude, сборка эталона v1, проверки.

Подкоманды `olympiad_vsosh`:
  transcribe — GLM-5.3-Flash по страницам групп плана (библиотека
               `transcribe.Transcriber`, без правок чужого модуля). Деньги:
               без `--yes` только план; `--max-usd` — потолок ВСЕГО журнала
               `transcribe_cost.jsonl` (не одного прогона);
  assemble   — `assemble.assemble(profile='econ')` поверх страниц
               (+ заплатки Claude из `pages_claude\\`, если есть) →
               `reference_problems_v1.jsonl` в схеме эталона ВП/МОШ v6 +
               поля `stage`, `region_code`, `region_name`, `tour`, `variant`;
  check      — проверки качества (KaTeX — отдельно node-скриптом);
  review     — `review_v1.html`: только нерешённое, картинка и текст рядом;
  bank       — сверка с банком (только чтение).

Пакеты Claude (`claude_batch.py` в этом же модуле — функции `batch_*`)
готовятся всегда; отправка — только когда ключ отвечает (ночью 28.10 ключ
требовал `anthropic-workspace-id`, которого нет).
"""
from __future__ import annotations

import base64
import json
import os
import re
from collections import Counter, defaultdict

from problems.olympiad_audit import assemble, digitize, transcribe

#: Цена страницы в Batches (−50 %), $: калибровка 28.10 на 30 страницах ×1,1
#: (Sonnet low $0,0089, Haiku low $0,00068; вход ≈ 3 400 ток., из них ≈ 1 900
#: из кэша). Цены 06.10.2026: Sonnet 5.5 $2/$10, Haiku 5.5 $0,10/$0,50 за 1 млн.
CLAUDE_PAGE_USD = {'claude-sonnet-5-5': 0.0098, 'claude-haiku-5-5': 0.00075}
CLAUDE_PRICES = {'claude-sonnet-5-5': (2.0, 10.0), 'claude-haiku-5-5': (0.10, 0.50)}

STAGE_NAME = {'final': 'заключительный этап', 'regional': 'региональный этап',
              'municipal': 'муниципальный этап', 'school': 'школьный этап',
              'invitational': 'пригласительный этап'}

#: Подсказка модели: текстовый слой PDF (обрезанный) — не источник, мерило.
LAYER_HINT_CHARS = 6000

FLASH_MODEL = transcribe.MODEL


def _read(path):
    return digitize.read_jsonl(path) if os.path.isfile(path) else []


def load_events(digitized):
    files = {e['event_id']: e for e in _read(os.path.join(digitized, 'events_files.jsonl'))}
    meta = {m['event_id']: m for m in _read(os.path.join(digitized, 'events_meta.jsonl'))}
    return files, meta


def page_jobs(digitized, groups=None):
    """Страницы к оцифровке по порядку групп → [(группа, PageJob)].

    Файл, общий для нескольких комплектов, — один раз (по первой группе)."""
    files, meta = load_events(digitized)
    seen = set()
    order = sorted(meta.values(), key=lambda m: (m['group'], m['academic_year'] or '',
                                                 m['event_id']))
    out = []
    for m in order:
        if groups and m['group'] not in groups:
            continue
        ev = files[m['event_id']]
        name = (f'Всероссийская олимпиада школьников по экономике, '
                f'{STAGE_NAME.get(m["stage"], m["stage"])} {m["academic_year"]}'
                + (f', {m["region_name"]}' if m.get('region_name') else ''))
        for key in ('task_files', 'solution_files', 'criteria_files'):
            for f in ev[key]:
                if f['sha256'] in seen:
                    continue
                seen.add(f['sha256'])
                row = {'file': f['file'], 'page_dir': f['page_dir'], 'pages': f['pages'],
                       'digitize': True, 'duplicate_of': None, 'ext': 'pdf',
                       'kind': f['kind']}
                for job in transcribe.build_jobs([row], digitized, name):
                    out.append((m['group'], job))
    return out


# ── GLM-5.3-Flash ───────────────────────────────────────────────────────

def run_transcribe(cmd, opts):
    digitized = cmd.digitized
    groups = {int(g) for g in str(opts['groups']).split(',') if g.strip()}
    jobs = [j for _g, j in page_jobs(digitized, groups)]
    if opts.get('pages_file'):
        wanted = {line.strip() for line in open(opts['pages_file'], encoding='utf-8') if line.strip()}
        jobs = [j for j in jobs if j.key in wanted or j.key.replace('pages/', '') in wanted]
    pending = transcribe.todo(jobs, digitized)
    if opts.get('limit'):
        pending = pending[:opts['limit']]
    cost_log = transcribe.CostLog(os.path.join(digitized, 'transcribe_cost.jsonl'))
    spent, calls = cost_log.total()
    avg = cost_log.average() or 0.00116
    cap = opts.get('max_usd')
    cmd._say(f'страниц в группах {sorted(groups)}: {len(jobs)}; к расшифровке {len(pending)}; '
             f'оценка ${len(pending) * avg * 1.15:.2f}; журнал: ${spent:.4f} за {calls} вызовов')
    if not opts.get('yes'):
        cmd._say('Без --yes вызовов нет (только план).')
        return
    if cap is None:
        from django.core.management.base import CommandError
        raise CommandError('--max-usd обязателен для платного прогона.')
    budget = transcribe.Budget(max(0.0, cap - spent), avg * 2)
    tr = transcribe.Transcriber(root=digitized, provider=transcribe.make_provider(),
                                budget=budget, cost_log=cost_log, workers=opts['workers'],
                                stdout=cmd.stdout)
    tr.progress_name = 'transcribe_progress_vsosh.json'
    stats = tr.run(pending)
    cmd._say(f'итог: {dict(stats)}; потрачено в прогоне ${budget.spent:.4f}; '
             f'стоп: {tr.stopped or "нет"}')


# ── Claude: пакеты Message Batches ──────────────────────────────────────

CLAUDE_SYSTEM = (transcribe.SYSTEM_PROMPT + transcribe.STRICT_SUFFIX +
                 '\n\nК картинке приложен текстовый слой PDF этой страницы — как подсказку '
                 'для точных чисел и слов. Источник правды — КАРТИНКА: если слой расходится '
                 'с картинкой или в нём пропали формулы (Equation Editor), переписывай по '
                 'картинке. Формулы — LaTeX внутри $…$, таблицы — Markdown-таблицами, '
                 'варианты ответа тестов — списком, рисунок — блок `figure` с рамкой.'
                 '\n\nОТВЕЧАЙ РОВНО ОДНИМ JSON-ОБЪЕКТОМ по этой схеме, без текста вокруг:\n'
                 + json.dumps(transcribe.SCHEMA, ensure_ascii=False))


#: Длинная сторона картинки для Claude: больше API всё равно ужмёт сам.
CLAUDE_MAX_SIDE = 1568
#: PNG страницы до этого размера уходит как есть (API ужмёт сам); крупнее —
#: уменьшается и идёт JPEG: уменьшенный PNG со сглаженными краями букв
#: весит БОЛЬШЕ исходного (замер 28.10: 250 стр. — 200–226 МБ при лимите
#: пакета 256 МБ).
PNG_AS_IS_BYTES = 600_000


def page_image_b64(path, max_side=CLAUDE_MAX_SIDE):
    """Картинка страницы для Claude → (media_type, base64)."""
    if os.path.getsize(path) <= PNG_AS_IS_BYTES:
        with open(path, 'rb') as fh:
            return 'image/png', base64.b64encode(fh.read()).decode('ascii')
    import io

    from PIL import Image
    with Image.open(path) as im:
        im = im.convert('L' if im.mode in ('L', '1', 'LA') else 'RGB')
        if max(im.size) > max_side:
            k = max_side / max(im.size)
            im = im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=90)
    return 'image/jpeg', base64.b64encode(buf.getvalue()).decode('ascii')


def batch_request(job, model, max_tokens=12000, thinking=None, custom_id=None):
    """Запрос Batches для страницы: system кэшируется (одинаков у всех).
    `thinking` — {'type': 'between_tools'} у Sonnet 5.5 выключает рассуждение."""
    layer = transcribe.layer_body(job.layer, job.footers)[:LAYER_HINT_CHARS]
    text = job.user_text() + ('\n\nТекстовый слой PDF (подсказка):\n<<<\n' + layer + '\n>>>'
                              if layer.strip() else '\n\nТекстового слоя нет (скан).')
    media_type, data = page_image_b64(job.png)
    params = {
        'model': model, 'max_tokens': max_tokens,
        'system': [{'type': 'text', 'text': CLAUDE_SYSTEM,
                    'cache_control': {'type': 'ephemeral'}}],
        'output_config': {'effort': 'low'},
        'messages': [{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type,
                                         'data': data}},
            {'type': 'text', 'text': text}]}],
    }
    if thinking:
        params['thinking'] = thinking
    return {'custom_id': custom_id or job.key.replace('/', '__'), 'params': params}


#: Рассуждение выключается по-разному: Sonnet 5.5 не принимает `disabled`.
THINKING_OFF = {'claude-sonnet-5-5': {'type': 'between_tools'},
                'claude-haiku-5-5': {'type': 'disabled'}}


def write_batches(digitized, groups, model, out_dir, chunk=250, thinking=None, pages=None,
                  max_bytes=150_000_000):
    """Пакеты Batches: batch_<model>_g<группы>_<N>.jsonl по `chunk` страниц
    в порядке плана (группа, сезон). `pages` — только эти ключи страниц."""
    os.makedirs(out_dir, exist_ok=True)
    jobs = [(g, j) for g, j in page_jobs(digitized, groups) if not pages or j.key in pages]
    paths, n, part, fh, in_file, size = [], 0, 0, None, 0, 0

    def close():
        # Готовый файл — под своим именем: отправка не подхватит недописанный.
        fh.close()
        os.replace(paths[-1] + '.tmp', paths[-1])

    for _g, job in jobs:
        if fh is None or in_file >= chunk or size >= max_bytes:
            if fh:
                close()
            part += 1
            paths.append(os.path.join(
                out_dir, f'batch_{model}_g{"".join(map(str, sorted(groups)))}_{part:03d}.jsonl'))
            fh, in_file, size = open(paths[-1] + '.tmp', 'w', encoding='utf-8'), 0, 0
        line = json.dumps(batch_request(job, model, thinking=thinking), ensure_ascii=False) + '\n'
        fh.write(line)
        size += len(line)
        in_file += 1
        n += 1
    if fh:
        close()
    return paths, n


def claude_client():
    """Клиент Anthropic с заголовком пространства, если он задан в окружении."""
    import anthropic
    headers = {}
    ws = os.environ.get('ANTHROPIC_WORKSPACE_ID')
    if ws:
        headers['anthropic-workspace-id'] = ws
    return anthropic.Anthropic(default_headers=headers, max_retries=5)


def batch_cost(usage, model):
    """$ за ответ Batches (−50 %); кэш-чтение — 0,1 входа, запись — 1,25."""
    pin, pout = CLAUDE_PRICES[model]
    u = usage or {}
    inp = (u.get('input_tokens') or 0) + 1.25 * (u.get('cache_creation_input_tokens') or 0) \
        + 0.1 * (u.get('cache_read_input_tokens') or 0)
    return 0.5 * (inp * pin + (u.get('output_tokens') or 0) * pout) / 1e6


def claude_record(job_key, message_text, usage, model):
    """Ответ Claude → запись страницы в формате `transcribe` (для overlay)."""
    data = transcribe.tolerant_parse(message_text)
    blocks = transcribe.clean_blocks(data.get('blocks'))
    return {'page_dir': job_key.rsplit('/p', 1)[0], 'page': int(job_key.rsplit('/p', 1)[1]),
            'blocks': blocks, 'status': 'ok' if blocks else 'error',
            'parse_error': data.get('_parse_error', ''), 'model': model,
            'cost_usd': round(batch_cost(usage, model), 6),
            'flags': {k: bool(data.get(k)) for k in ('has_formulas', 'has_table', 'has_figure')}}


# ── Сборка ──────────────────────────────────────────────────────────────

class ClaudeOverlay:
    r"""Заплатка страниц расшифровкой Claude (`pages_claude\<sha16>\p<N>.json`):
    есть удачная запись Claude — её блоки вместо блоков Flash."""

    def __init__(self, folder):
        self.folder = folder
        self.applied = 0

    def path(self, page_dir, page):
        return os.path.join(self.folder, page_dir.split('/')[-1], f'p{page}.json')

    def apply(self, page_dir, page, record):
        path = self.path(page_dir, page)
        if not os.path.isfile(path):
            return record
        with open(path, encoding='utf-8') as fh:
            claude = json.load(fh)
        if claude.get('status') != 'ok' or not claude.get('blocks'):
            return record
        self.applied += 1
        return dict(record, blocks=claude['blocks'], model=claude.get('model'),
                    needs_eyes=False, flash_needs_eyes=record.get('needs_eyes'))


def ensure_stub(digitized, page_dir, page):
    """Страница есть только у Claude — пустая запись Flash, чтобы сборка её
    прочла (блоки придут заплаткой)."""
    path = os.path.join(digitized, page_dir, f'p{page}.json')
    if not os.path.isfile(path):
        transcribe.Transcriber._write(path, {'page_dir': page_dir, 'page': page, 'blocks': [],
                                             'status': 'claude_only', 'needs_eyes': False})

EXTRA_KEYS = ('stage', 'region_code', 'region_name', 'tour', 'variant')


def drop_repeated_paragraphs(text):
    """Дословный повтор абзаца в условии — прочь (первое вхождение остаётся).
    Правило сборки v5 приклеивает к каждому вопросу теста инструкцию раздела
    со всех страниц, где она стоит, — «Тест №2. Выберите…» выходил трижды.
    Правится форма, не смысл (ADR 0005). Возвращает (текст, число удалённых)."""
    if not text:
        return text, 0
    seen, out, dropped = set(), [], 0
    for para in re.split(r'\n\s*\n', text):
        key = ' '.join(para.split())
        if key and key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(para)
    return '\n\n'.join(out), dropped


#: Ответ-«ключ» теста: «Да», «неверно», «1)», «а, в», «2; 4», «Б».
_KEY_TOKEN = re.compile(r'^(?:да|нет|верно|неверно|[а-еa-e]|\d{1,2})$', re.I)


def answer_like(text):
    """Короткая строка ключа теста (не решение и не критерий)."""
    t = re.sub(r'[*_`]', '', str(text or '')).strip()
    if not t or len(t) > 25 or '\n' in t:
        return False
    tokens = [x for x in re.split(r'[\s,;.)(]+|\bи\b', t) if x]
    return bool(tokens) and all(_KEY_TOKEN.match(x) for x in tokens)


def key_blocks(digitized, ev):
    """Блоки ключа из файлов ответов комплекта по порядку страниц:
    [(номер, ответ)] — `criteria`/`solution` с номером-числом и коротким
    ответом. Страница — заплатка Claude, если удачна, иначе GLM."""
    out = []
    for key in ('solution_files', 'criteria_files'):
        for f in ev.get(key) or []:
            sha16 = f['page_dir'].split('/')[-1]
            for p in range(1, int(f.get('pages') or 0) + 1):
                rec = None
                for path in (os.path.join(digitized, 'pages_claude', sha16, f'p{p}.json'),
                             os.path.join(digitized, f['page_dir'], f'p{p}.json')):
                    if os.path.isfile(path):
                        with open(path, encoding='utf-8') as fh:
                            rec = json.load(fh)
                        if rec.get('status') == 'ok' and rec.get('blocks'):
                            break
                for b in (rec or {}).get('blocks') or []:
                    num = str(b.get('number') or '').strip().rstrip('.')
                    text = b.get('answer') or b.get('text') or ''
                    if b.get('type') in ('criteria', 'solution') and num.isdigit() \
                            and answer_like(text):
                        out.append((num, re.sub(r'[*_`]', '', text).strip()))
    return out


def fill_test_keys(rows, keys):
    """Ключ теста из файла ответов → `answer` вопросов «тест-N» комплекта.

    Номера ключа уникальны — раздаются по номеру; нумерация начиналась
    заново по разделам, но ключей ровно столько, сколько вопросов, — по
    порядку. Иначе не трогаем. Ключ, который сборка приняла за критерии
    задачи с тем же номером (первый абзац `criteria_md` равен ключу), с
    задачи снимается. Возвращает число заполненных ответов."""
    tests = sorted((r for r in rows if str(r.get('number', '')).startswith('тест-')),
                   key=lambda r: int(str(r['number'])[5:] or 0)
                   if str(r['number'])[5:].isdigit() else 0)
    if not tests or not keys:
        return 0
    nums = [n for n, _ in keys]
    if len(set(nums)) == len(nums):
        by_num = dict(keys)
        pairs = [(r, by_num.get(str(r['number'])[5:])) for r in tests]
    elif len(keys) == len(tests):
        pairs = list(zip(tests, [a for _, a in keys]))
    else:
        return 0
    filled = 0
    for r, ans in pairs:
        if ans and not (r.get('answer') or '').strip():
            r['answer'] = ans
            r['answer_from_key_table'] = True
            filled += 1
    if filled and len(set(nums)) == len(nums):
        by_num = dict(keys)
        for r in rows:
            num = str(r.get('number', ''))
            crit = r.get('criteria_md') or ''
            first, _, rest = crit.partition('\n\n')
            if num in by_num and first.strip() == by_num[num]:
                r['criteria_md'] = rest.strip()
                r['key_removed_from_criteria'] = True
    return filled


def page_models(digitized, pdf_dirs, refs):
    """Какой моделью расшифрованы страницы задания («файл#pN»): заплатка Claude
    или GLM. Порядок — по убыванию числа страниц."""
    c = Counter()
    for ref in refs or []:
        pdf, _, page = ref.rpartition('#p')
        pd = pdf_dirs.get(pdf)
        if not pd:
            continue
        path = os.path.join(digitized, 'pages_claude', pd.split('/')[-1], f'p{page}.json')
        model = FLASH_MODEL
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                rec = json.load(fh)
            if rec.get('status') == 'ok':
                model = rec.get('model') or model
        c[model] += 1
    return '+'.join(m for m, _ in c.most_common()) or FLASH_MODEL


def reference_events(meta):
    out = []
    for m in meta.values():
        out.append({'event_id': m['event_id'], 'olympiad_slug': 'vseros',
                    'year': m.get('year'), 'academic_year': m.get('academic_year'),
                    'stage': m.get('stage'), 'grade': m.get('grade'), 'variant': m.get('tour') or 'all',
                    'official': True, 'source': 'official',
                    'source_urls': m.get('source_urls', [])})
    return out


def run_assemble(cmd, opts):
    digitized = cmd.digitized
    files, meta = load_events(digitized)
    # Комплекты без единой расшифрованной страницы условий — мимо (не пустые строки).
    ready = {}
    for eid, ev in files.items():
        done = sum(1 for f in ev['task_files'] for p in range(1, int(f['pages'] or 0) + 1)
                   if transcribe.page_done(os.path.join(digitized, f['page_dir'], f'p{p}.json'))
                   or os.path.isfile(os.path.join(digitized, 'pages_claude',
                                                  f['page_dir'].split('/')[-1], f'p{p}.json')))
        total = sum(int(f['pages'] or 0) for f in ev['task_files'])
        if done:
            ready[eid] = (done, total)
    folder = os.path.join(digitized, 'pages_claude')
    overlay = ClaudeOverlay(folder) if os.path.isdir(folder) else None
    if overlay:
        for eid in ready:
            for key in ('task_files', 'solution_files', 'criteria_files'):
                for f in files[eid][key]:
                    for p in range(1, int(f['pages'] or 0) + 1):
                        if os.path.isfile(overlay.path(f['page_dir'], p)):
                            ensure_stub(digitized, f['page_dir'], p)
    summary = assemble.assemble(digitized, reference_events(meta), [], FLASH_MODEL,
                                only_events=set(ready), crop=True, overlay=overlay,
                                out_dir=digitized, suffix='v1asm', profile=assemble.ECON)
    rows = _read(os.path.join(digitized, 'reference_problems_v1asm.jsonl'))
    pdf_dirs = {x['pdf']: x['page_dir'] for x in _read(os.path.join(digitized, 'render_index.jsonl'))}
    out, keys, dup = [], Counter(), 0
    for r in rows:
        m = meta.get(r['event_id'], {})
        for k in EXTRA_KEYS:
            r[k] = m.get(k, '') if k != 'stage' else (m.get('stage') or r.get('stage'))
        r['olympiad_slug'] = 'vseros'
        r['statement_md'], dropped = drop_repeated_paragraphs(r.get('statement_md') or '')
        if dropped:
            r['repeated_paragraphs_dropped'] = dropped
        r['digitized_by'] = dict(r.get('digitized_by') or {},
                                 model=page_models(digitized, pdf_dirs, r.get('source_pages')))
        r['pages_ready'] = list(ready.get(r['event_id'], (0, 0)))
        r['event_partial'] = ready.get(r['event_id'], (0, 0))[0] < ready.get(r['event_id'], (0, 1))[1]
        r['title'] = official_title(r.get('title'))
        fixed = 0
        for field in ('statement_md', 'solution_md', 'criteria_md', 'answer'):
            r[field], k = fix_currency_dollars(r.get(field) or '')
            fixed += k
        for part in r.get('parts') or []:
            part['text'], k = fix_currency_dollars(part.get('text') or '')
            fixed += k
        if fixed:
            r['currency_dollars_escaped'] = fixed
        key = (r['event_id'], r['number'], r.get('task_variant', ''))
        keys[key] += 1
        if keys[key] > 1:
            dup += 1
            r['task_variant'] = (r.get('task_variant') or '') + f'#dup{keys[key]}'
            r.setdefault('flags', []).append('повтор_ключа')
        out.append(r)
    by_event = defaultdict(list)
    for r in out:
        by_event[r['event_id']].append(r)
    keys_filled = sum(fill_test_keys(rs, key_blocks(digitized, files.get(eid, {})))
                      for eid, rs in by_event.items())
    digitize.write_jsonl(os.path.join(digitized, 'reference_problems_v1.jsonl'), out)
    cmd._say(f'ключ теста из таблицы ответов: {keys_filled} ответов')
    cmd._say(f'сборка: {dict(summary)}')
    cmd._say(f'заданий v1: {len(out)}; комплектов с заданиями: '
             f'{len({r["event_id"] for r in out})}; повторов ключа (переименованы): {dup}')


_CYR_WORD = re.compile(r'[А-Яа-яЁё]{3,}')
_TEXT_CMD = re.compile(r'\\(?:text|mathrm|textit|textbf|operatorname)\{[^{}]*\}')
#: Обратная косая — именем: правки этого файла уже дважды съедали её в литералах.
_BSL = chr(92)


def fix_currency_dollars(text):
    r"""Валютный «$700» → «\$700»: модель пишет доллары как в оригинале, а на
    сайте `$` открывает формулу, и KaTeX склеивает текст до следующего `$`.

    Правило (детерминированное, ADR 0005 — правится форма, не смысл): `$` без
    обратной косой перед ним, сразу за ним цифра; если «формула» до
    следующего `$` содержит русское слово (вне `\text{}`) или закрывающего
    `$` нет — это деньги, `$` экранируется. `$$` не трогается.
    Возвращает (текст, число правок)."""
    if not text or '$' not in text:
        return text, 0
    out, i, n = [], 0, 0
    while i < len(text):
        ch = text[i]
        if ch == '$' and (i == 0 or text[i - 1] != _BSL):
            if text.startswith('$$', i):
                j = text.find('$$', i + 2)
                j = len(text) - 2 if j < 0 else j
                out.append(text[i:j + 2])
                i = j + 2
                continue
            j = i + 1
            while j < len(text) and not (text[j] == '$' and text[j - 1] != _BSL):
                j += 1
            seg = text[i + 1:j]
            if text[i + 1:i + 2].isdigit() and (
                    j >= len(text) or _CYR_WORD.search(_TEXT_CMD.sub('', seg))):
                out.append(_BSL + '$')
                n += 1
                i += 1
                continue
            out.append(text[i:j + 1])
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out), n


#: Слова служебного заголовка: «Задачи - 1-ый тур», «Задание № 2», «Тест (10 вопросов)».
_SERVICE_WORDS = re.compile(
    r'задач\w*|задани\w*|вопрос\w*|тест\w*|тур\w*|класс\w*|часть|раздел\w*|эссе|блиц|'
    r'справк\w*|решени\w*|ответ\w*|критери\w*|баллов|балл\w*|ый|ой|ий|й|го|я|кл|'
    r'первый|второй|третий|i{1,3}|iv|v|vi{0,3}|\d+', re.I)


def official_title(title):
    """Решение Notion 15.10: настоящее название — берём; «Задача 3», «Задание N»,
    «СПРАВКА» — не название (пусто: название даст ИИ при импорте)."""
    t = str(title or '').strip()
    rest = re.sub(r'[\W_]+', ' ', _SERVICE_WORDS.sub(' ', t)).strip()
    if not t or not rest:
        return ''
    return t


def run_batches(cmd, opts):
    """Пакеты Claude к утру: группы 1–3 — Sonnet, 4–5 — Haiku (по `--groups`)."""
    out_dir = os.path.join(cmd.digitized, 'claude_batches')
    groups = {int(g) for g in str(opts['groups']).split(',') if g.strip()}
    total = {}
    for model, gs in (('claude-sonnet-5-5', groups & {1, 2, 3}),
                      ('claude-haiku-5-5', groups & {4, 5})):
        if not gs:
            continue
        pages = None
        if opts.get('pages_file'):
            pages = {x.strip() for x in open(opts['pages_file'], encoding='utf-8') if x.strip()}
        paths, n = write_batches(cmd.digitized, gs, model, out_dir, pages=pages,
                                 thinking=THINKING_OFF[model] if opts.get('thinking_off') else None)
        total[model] = {'pages': n, 'files': len(paths),
                        'estimate_usd': round(n * CLAUDE_PAGE_USD[model], 2)}
    with open(os.path.join(out_dir, 'batches_plan.json'), 'w', encoding='utf-8') as fh:
        json.dump(total, fh, ensure_ascii=False, indent=1)
    cmd._say(json.dumps(total, ensure_ascii=False))


def _ledger(digitized):
    path = os.path.join(digitized, 'claude_batches', 'ledger.jsonl')
    return path, _read(path)


def page_usd(ledger):
    """Цена страницы по модели: средняя по уже забранным пакетам (×1,1 запас),
    пока их нет — оценка `CLAUDE_PAGE_USD`."""
    out = dict(CLAUDE_PAGE_USD)
    for model in out:
        rs = [x for x in ledger if x.get('kind') == 'result' and x.get('model') == model]
        n = sum((x.get('ok') or 0) + (x.get('failed') or 0) for x in rs)
        if n >= 50:
            out[model] = 1.1 * sum(float(x['cost_usd']) for x in rs) / n
    return out


#: Старшинство моделей при заплатке: пакеты забираются в порядке готовности,
#: и поздний Haiku не должен затирать удачный Sonnet той же страницы.
MODEL_RANK = {'claude-haiku-5-5': 1, 'claude-sonnet-5-5': 2}


def keeps_existing(path, rec):
    """Уже лежащая удачная запись старшей модели остаётся (новая — мимо)."""
    if not os.path.isfile(path):
        return False
    with open(path, encoding='utf-8') as fh:
        old = json.load(fh)
    return (old.get('status') == 'ok'
            and MODEL_RANK.get(old.get('model'), 0) > MODEL_RANK.get(rec.get('model'), 0))


def pending_usd(ledger):
    """Оценка отправленных, но ещё не забранных пакетов. Забранный пакет
    уже сидит в `spent` настоящей ценой — второй раз его не считать
    (28.10: двойной счёт остановил отправку на $28 вместо $47)."""
    collected = {x['batch_id'] for x in ledger if x.get('kind') == 'collected'}
    return sum(float(x.get('estimate_usd') or 0) for x in ledger
               if x.get('kind') == 'submitted' and x['batch_id'] not in collected)


def run_claude(cmd, opts):
    r"""submit — отправить пакеты по порядку, пока расход < 90 % потолка;
    collect — забрать готовые результаты в pages_claude\ и учесть расход."""
    import time
    digitized = cmd.digitized
    out_dir = os.path.join(digitized, 'claude_batches')
    ledger_path, ledger = _ledger(digitized)
    spent = sum(float(x.get('cost_usd') or 0) for x in ledger if x.get('kind') == 'result')
    cap = opts.get('max_usd') or 0
    action = opts.get('action') or 'collect'
    per_page = page_usd(ledger)
    client = claude_client()
    if action == 'submit':
        if not opts.get('yes') or not cap:
            cmd._say('Без --yes и --max-usd пакеты не отправляются.')
            return
        sent = {x['file'] for x in ledger if x.get('kind') == 'submitted'}
        for name in sorted(os.listdir(out_dir)):
            # Только дописанные файлы: `.jsonl.tmp` ещё пишется (28.10 — 400 «пустой список»).
            if not (name.startswith('batch_') and name.endswith('.jsonl')) or name in sent:
                continue
            model = 'claude-sonnet-5-5' if 'sonnet' in name else 'claude-haiku-5-5'
            reqs = _read(os.path.join(out_dir, name))
            if opts.get('thinking_off'):     # решение калибровки — при отправке
                for req in reqs:
                    req['params']['thinking'] = THINKING_OFF[model]
            projected = spent + len(reqs) * per_page[model] + pending_usd(ledger)
            if projected > 0.9 * cap:
                cmd._say(f'стоп: {name} поднял бы расход до ${projected:.2f} (> 90 % от ${cap})')
                break
            for attempt in range(6):
                try:
                    batch = client.messages.batches.create(requests=reqs)
                    break
                except Exception as exc:   # 429/5xx — подождать и повторить
                    if attempt == 5:
                        raise
                    cmd._say(f'  повтор отправки {name}: {exc}')
                    time.sleep(30 * (attempt + 1))
            rec = {'kind': 'submitted', 'file': name, 'batch_id': batch.id, 'model': model,
                   'requests': len(reqs), 'estimate_usd': round(len(reqs) * per_page[model], 3)}
            with open(ledger_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
            ledger.append(rec)
            cmd._say(f'отправлен {name}: {batch.id}')
        return
    done = {x['batch_id'] for x in ledger if x.get('kind') == 'collected'}
    for sub in [x for x in ledger if x.get('kind') == 'submitted' and x['batch_id'] not in done]:
        b = client.messages.batches.retrieve(sub['batch_id'])
        if b.processing_status != 'ended':
            cmd._say(f'{sub["file"]}: {b.processing_status} {b.request_counts}')
            continue
        cost, ok, bad = 0.0, 0, 0
        for res in client.messages.batches.results(sub['batch_id']):
            key = res.custom_id.replace('__', '/')
            if res.result.type != 'succeeded':
                bad += 1
                continue
            msg = res.result.message
            text = ''.join(getattr(b_, 'text', '') for b_ in msg.content if b_.type == 'text')
            usage = msg.usage.model_dump() if hasattr(msg.usage, 'model_dump') else dict(msg.usage)
            rec = claude_record(key, text, usage, sub['model'])
            cost += rec['cost_usd']
            ok += rec['status'] == 'ok'
            sha16 = key.split('/')[1]
            path = os.path.join(digitized, 'pages_claude', sha16, f'p{rec["page"]}.json')
            if not keeps_existing(path, rec):
                transcribe.Transcriber._write(path, rec)
        with open(ledger_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'kind': 'result', 'batch_id': sub['batch_id'], 'cost_usd': round(cost, 4),
                                 'model': sub['model'], 'ok': ok, 'failed': bad},
                                ensure_ascii=False) + '\n')
            fh.write(json.dumps({'kind': 'collected', 'batch_id': sub['batch_id']}) + '\n')
        cmd._say(f'{sub["file"]}: ok {ok}, сбоев {bad}, ${cost:.3f}')


def run_step(cmd, step, opts):
    if step == 'batches':
        return run_batches(cmd, opts)
    if step == 'claude':
        return run_claude(cmd, opts)
    if step == 'transcribe':
        return run_transcribe(cmd, opts)
    if step == 'assemble':
        return run_assemble(cmd, opts)
    from problems.olympiad_audit import vsosh_quality
    return vsosh_quality.run_step(cmd, step, opts)


def group_pages(digitized):
    """{группа: (страниц, готово)} — для отчёта и Notion."""
    out = defaultdict(lambda: [0, 0])
    for g, job in page_jobs(digitized):
        out[g][0] += 1
        if transcribe.page_done(job.out_path(digitized)):
            out[g][1] += 1
    return dict(out)
