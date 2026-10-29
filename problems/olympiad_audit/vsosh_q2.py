# -*- coding: utf-8 -*-
"""ВсОШ v2, сессия Q2: шаги по фазам поверх `vsosh_verify`.

Подкоманды `olympiad_vsosh q2 --action …` (папка работы — `digitized\\v2\\q2\\`):
  jobs        — кэш страниц плана `jobs_cache.jsonl` (слой читается по требованию);
  calib       — фаза 1: выборка 40 + 10 страниц, расшифровка всеми кандидатами
                (без `--yes` только план), метрики без людей → `calib\\CALIB.md`.
Деньги — `ledger_q2.jsonl`, потолки — `vsosh_verify.CAPS`.
"""
from __future__ import annotations

import json
import re
import os
import statistics
import subprocess
import time
from collections import Counter

from problems.olympiad_audit import transcribe
from problems.olympiad_audit import vsosh_verify as vv

CALIB_MODELS = ('gpt-6.1-sol', 'gpt-6.1-terra', 'google/gemini-4-argon',
                'qwen/qwen3.8-max-prime', 'claude-sonnet-5-5')
#: Эталонная планка: Sonnet 5.5 (на контрольных ЗЭ/РЭ — его запись P3).
BAR = 'claude-sonnet-5-5'


class Q2:
    def __init__(self, v1_root):
        self.v1 = v1_root
        self.work = os.path.join(os.path.dirname(v1_root), 'v2', 'q2')
        os.makedirs(self.work, exist_ok=True)
        self.ledger = vv.Ledger(os.path.join(self.work, 'ledger_q2.jsonl'))
        self._jobs = None

    @property
    def jobs(self):
        if self._jobs is None:
            self._jobs = vv.load_jobs(self.v1, os.path.join(self.work, 'jobs_cache.jsonl'))
        return self._jobs

    def todo_keys(self, groups=(4, 5)):
        out = []
        for g in groups:
            path = os.path.join(self.v1, 'claude_batches', f'todo_g{g}.txt')
            with open(path, encoding='utf-8') as fh:
                out += [x.strip() for x in fh if x.strip()]
        return out

    def sonnet_keys(self, groups=(1, 2)):
        """Страницы ЗЭ/РЭ с удачной записью Sonnet P3 — контроль."""
        out = []
        for k, j in self.jobs.items():
            if j.group in groups:
                rec = vv.read_record(self.p3_claude_path(k))
                if rec and rec.get('status') == 'ok' and rec.get('model') == BAR and j.has_layer:
                    out.append(k)
        return out

    def p3_claude_path(self, key):
        page_dir, _, page = key.rpartition('/p')
        return os.path.join(self.v1, 'pages_claude', page_dir.split('/')[-1], f'p{page}.json')


# ── Фаза 1 ─────────────────────────────────────────────────────────────

def calib_sample(q, log):
    path = os.path.join(q.work, 'calib', 'sample.json')
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sample = vv.calib_sample(q.jobs, q.v1, q.todo_keys(), q.sonnet_keys())
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(sample, fh, ensure_ascii=False, indent=1)
    log(f'выборка: {Counter(s["set"] for s in sample)} → {path}')
    return sample


def calib_run(q, opts, log):
    sample = calib_sample(q, log)
    folder = os.path.join(q.work, 'calib')
    region = [s['key'] for s in sample if s['set'] == 'region']
    control = [s['key'] for s in sample if s['set'] == 'control']
    plan = {m: (region if m == BAR else region + control) for m in CALIB_MODELS}
    for m, keys in plan.items():
        log(f'{m}: страниц {len(keys)}')
    if not opts.get('yes'):
        log('Без --yes вызовов нет (только план).')
        return
    env = vv.load_env()
    for m in (opts.get('models') or ','.join(CALIB_MODELS)).split(','):
        stats = vv.run_pages(m, plan.get(m, region + control), q.jobs, folder, env, q.ledger,
                             phase='calib', workers=opts.get('workers') or 6, log=log)
        log(f'{m}: {stats}; потрачено фазой ${q.ledger.spent(vv.provider_of(m.split(":")[0]), "calib"):.3f}')


def katex_errors(records, work, name):
    """KaTeX текстов записей → {ключ: число ошибок}. node `scripts/vsosh_katex.js`."""
    src = os.path.join(work, f'{name}_katex_in.jsonl')
    dst = os.path.join(work, f'{name}_katex_out.json')
    with open(src, 'w', encoding='utf-8') as fh:
        for key, rec in records.items():
            blocks = transcribe.clean_blocks((rec or {}).get('blocks'))
            text = '\n\n'.join(str(b.get(k) or '') for b in blocks for k in ('text', 'answer')
                               if b['type'] not in ('footer', 'noise'))
            fh.write(json.dumps({'event_id': key, 'number': '', 'statement_md': text},
                                ensure_ascii=False) + '\n')
    script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'vsosh_katex.js')
    subprocess.run(['node', os.path.abspath(script), src, dst], check=True,  # noqa: S603,S607
                   capture_output=True)
    with open(dst, encoding='utf-8') as fh:
        data = json.load(fh)
    return {k.split('|')[0]: len(v) for k, v in (data.get('by_key') or {}).items()}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 4) if xs else None


def calib_report(q, log):
    sample = calib_sample(q, log)
    folder = os.path.join(q.work, 'calib')
    sets = {s['key']: s['set'] for s in sample}
    recs = {}
    for m in CALIB_MODELS:
        for s in sample:
            k = s['key']
            if m == BAR and s['set'] == 'control':
                rec = vv.read_record(q.p3_claude_path(k))
            else:
                rec = vv.read_record(vv.rec_path(folder, m, k))
            if rec:
                recs[(m, k)] = rec
    kx = katex_errors({f'{m}#{k}': r for (m, k), r in recs.items()}, folder, 'calib')
    per = {}
    for (m, k), rec in recs.items():
        met = vv.page_metrics(rec, q.jobs[k])
        met['katex'] = kx.get(f'{m}#{k}', 0)
        per[(m, k)] = met
    # Структура — против большинства ДРУГИХ моделей страницы (как консенсус P4).
    for (m, k), met in per.items():
        others = [per[(o, k)]['structure'] for o in CALIB_MODELS if o != m and (o, k) in per]
        agree_n = {}
        for field in ('numbers', 'options', 'table_rows', 'figures'):
            vals = Counter(json.dumps(o[field]) for o in others)
            top = vals.most_common(1)
            agree_n[field] = bool(top) and top[0][1] >= 2 and json.dumps(met['structure'][field]) == top[0][0]
        met['struct_agree'] = all(agree_n.values())
        met['struct_fields'] = agree_n
    out = {}
    for m in CALIB_MODELS:
        for part in ('region', 'control', 'all'):
            rows = [per[(m, k)] for k in sets if (m, k) in per and (part == 'all' or sets[k] == part)]
            if not rows:
                continue
            spent = [r['usd'] for r in rows if r.get('usd')]
            out[f'{m}|{part}'] = {
                'pages': len(rows), 'ok': sum(r['status'] == 'ok' for r in rows),
                'num_recall': _mean(r.get('num_recall') for r in rows),
                'num_precision': _mean(r.get('num_precision') for r in rows),
                'numbers_ok': _mean([float(r['numbers_ok']) for r in rows if r.get('numbers_ok') is not None]),
                'word_f1': _mean(r.get('word_f1') for r in rows),
                'fabricated_words': _mean(r.get('fabricated_words') for r in rows),
                'katex_pages_bad': sum(1 for r in rows if r['katex']),
                'struct_agree': _mean([float(r['struct_agree']) for r in rows]),
                'usd_per_page': round(statistics.mean(spent), 5) if spent else None}
    with open(os.path.join(folder, 'metrics.json'), 'w', encoding='utf-8') as fh:
        json.dump({'summary': out, 'pages': {f'{m}#{k}': v for (m, k), v in per.items()}},
                  fh, ensure_ascii=False, indent=1)
    lines = ['# Калибровка расшифровщиков ВсОШ-регионов (Q2, фаза 1)', '',
             'Метрики без людей: числа и слова — против текстового слоя PDF; структура — '
             'совпадение номеров заданий, числа вариантов, строк таблиц и рисунков с большинством '
             'других моделей; KaTeX — node `vsosh_katex.js`; цена — по ответу API (синхронно, без скидки пакета).', '',
             '| модель | набор | стр. | ok | числа: полнота | числа: точность | numbers_ok | слова F1 | '
             'выдумки слов | KaTeX стр. | структура | $/стр. |', '|' + '---|' * 12]
    for key, v in out.items():
        m, part = key.split('|')
        lines.append(f'| {m} | {part} | {v["pages"]} | {v["ok"]} | {v["num_recall"]} | '
                     f'{v["num_precision"]} | {v["numbers_ok"]} | {v["word_f1"]} | '
                     f'{v["fabricated_words"]} | {v["katex_pages_bad"]} | {v["struct_agree"]} | '
                     f'{v["usd_per_page"]} |')
    with open(os.path.join(folder, 'CALIB.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    log('\n'.join(lines))
    return out


# ── Пакеты: OpenAI Batch и Anthropic Message Batches ───────────────────

PRIMARY, SECOND = 'gpt-6.1-terra', 'claude-haiku-5-5'
#: Оценка $ за запрос пакетом (калибровка ×0,5 скидки ×1,1 запаса) — для
#: потолка до отправки; в журнал денег идёт настоящая цена по `usage`.
BATCH_ITEM_USD = {'gpt-6.1-terra': 0.0047, 'claude-haiku-5-5': 0.00095,
                  'claude-sonnet-5-5': 0.011, 'claude-opus-5-5': 0.045}
#: Запросов в пакете: у OpenAI файл ≤ 200 МБ, у Anthropic пакет ≤ 256 МБ
#: (страница с картинкой — до ~0,8 МБ base64).
CHUNK = {'openai': 200, 'anthropic': 200}
#: Объём пакета в байтах JSON (base64 картинок внутри): с запасом до 200/256 МБ.
MAX_BATCH_BYTES = 120_000_000


def custom_id(key):
    return key.replace('/', '__')


def key_of(cid):
    return cid.replace('__', '/')


class BatchLog:
    """Журнал пакетов `batches\\ledger.jsonl`: что отправлено, что забрано."""

    def __init__(self, q):
        self.q = q
        self.dir = os.path.join(q.work, 'batches')
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, 'ledger.jsonl')

    def rows(self):
        if not os.path.isfile(self.path):
            return []
        with open(self.path, encoding='utf-8') as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def add(self, **rec):
        with open(self.path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def open_batches(self):
        done = {r['batch_id'] for r in self.rows() if r.get('kind') == 'collected'}
        return [r for r in self.rows() if r.get('kind') == 'submitted' and r['batch_id'] not in done]

    def pending_usd(self, provider):
        return sum(r['estimate_usd'] for r in self.open_batches() if r['provider'] == provider)

    def pending_ids(self, phase, model):
        return {cid for r in self.open_batches() if r['phase'] == phase and r['model'] == model
                for cid in r['ids']}


def _openai_client(env):
    import openai
    return openai.OpenAI(api_key=env['OPENAI_API_KEY'], max_retries=5)


def submit(q, phase, model, items, log, limit=None):
    """Отправить пакеты: items — [(custom_id, тело запроса)] (тело — как для
    синхронного вызова). Перед каждым пакетом — потолок поставщика с учётом
    ещё не забранных пакетов. → число отправленных запросов."""
    from problems.olympiad_audit import vsosh_digitize
    bl, env = BatchLog(q), vv.load_env()
    prov = vv.provider_of(model)
    sent, chunks = 0, 0
    # Пакет режется и по числу запросов, и по объёму: 200 позиций Opus по
    # 5 картинок — больше 256 МБ, сервер рвёт соединение (29.10). `items` —
    # генератор: тела с картинками 7 140 страниц в памяти — это ~3 ГБ.
    def parts_of(it):
        cur, cur_bytes = [], 0
        for item in it:
            size = len(json.dumps(item[1], ensure_ascii=False))
            if cur and (len(cur) >= CHUNK[prov] or cur_bytes + size > MAX_BATCH_BYTES):
                yield cur
                cur, cur_bytes = [], 0
            cur.append(item)
            cur_bytes += size
        if cur:
            yield cur
    for i, part in enumerate(parts_of(items)):
        est = round(len(part) * BATCH_ITEM_USD[model], 3)
        if not q.ledger.allow(prov, est + bl.pending_usd(prov)):
            log(f'стоп {model}: пакет поднял бы расход {prov} выше 90 % потолка')
            break
        if prov == 'openai':
            tmp = os.path.join(bl.dir, f'tmp_{phase}_{i}.jsonl')
            with open(tmp, 'w', encoding='utf-8') as fh:
                for cid, body in part:
                    fh.write(json.dumps({'custom_id': cid, 'method': 'POST',
                                         'url': '/v1/chat/completions', 'body': body},
                                        ensure_ascii=False) + '\n')
            client = _openai_client(env)
            with open(tmp, 'rb') as fh:
                f = client.files.create(file=fh, purpose='batch')
            batch = client.batches.create(input_file_id=f.id, endpoint='/v1/chat/completions',
                                          completion_window='24h')
            os.remove(tmp)
        else:
            client = vsosh_digitize.claude_client()
            for attempt in range(3):
                try:
                    batch = client.messages.batches.create(
                        requests=[{'custom_id': cid, 'params': body} for cid, body in part])
                    break
                except Exception as exc:  # noqa: BLE001 — обрыв связи: подождать и повторить
                    if attempt == 2:
                        raise
                    log(f'  повтор отправки {phase}/{model}: {str(exc)[:120]}')
                    time.sleep(30 * (attempt + 1))
        bl.add(kind='submitted', phase=phase, model=model, provider=prov, batch_id=batch.id,
               n=len(part), estimate_usd=est, ids=[cid for cid, _b in part], ts=round(time.time()))
        log(f'  отправлен {phase}/{model}: {batch.id}, {len(part)} запросов, оценка ${est}')
        sent += len(part)
        chunks += 1
        if limit and chunks >= limit:
            break
    return sent


def _openai_results(client, b):
    """Строки результата OpenAI Batch → (custom_id, ok, текст, вход, выход)."""
    for fid in (b.output_file_id, b.error_file_id):
        if not fid:
            continue
        for line in client.files.content(fid).text.splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            resp = r.get('response') or {}
            body = resp.get('body') or {}
            if resp.get('status_code') == 200 and body.get('choices'):
                u = body.get('usage') or {}
                yield (r['custom_id'], True, body['choices'][0]['message'].get('content') or '',
                       u.get('prompt_tokens', 0), u.get('completion_tokens', 0))
            else:
                yield r['custom_id'], False, json.dumps(r.get('error') or body)[:300], 0, 0


def _anthropic_results(client, batch_id):
    for res in client.messages.batches.results(batch_id):
        if res.result.type != 'succeeded':
            yield res.custom_id, False, res.result.type, 0, 0
            continue
        msg = res.result.message
        u = msg.usage
        tin = (u.input_tokens or 0) + 1.25 * (u.cache_creation_input_tokens or 0) \
            + 0.1 * (u.cache_read_input_tokens or 0)
        yield (res.custom_id, True, ''.join(getattr(x, 'text', '') for x in msg.content
                                            if x.type == 'text'), tin, u.output_tokens or 0)


def collect(q, handlers, log):
    """Забрать готовые пакеты: результат запроса → `handlers[phase](model,
    custom_id, текст, $)`; расход пакета — одной строкой в журнал денег."""
    from problems.olympiad_audit import vsosh_digitize
    bl, env = BatchLog(q), vv.load_env()
    status = Counter()
    for row in bl.open_batches():
        if row['provider'] == 'openai':
            client = _openai_client(env)
            b = client.batches.retrieve(row['batch_id'])
            if b.status not in ('completed', 'expired', 'failed', 'cancelled'):
                status[f'{row["model"]}:{b.status}'] += 1
                continue
            results = _openai_results(client, b) if b.status != 'failed' else iter(())
            if b.status == 'failed':
                log(f'  пакет {row["batch_id"]} failed: {str(b.errors)[:300]}')
        else:
            client = vsosh_digitize.claude_client()
            b = client.messages.batches.retrieve(row['batch_id'])
            if b.processing_status != 'ended':
                status[f'{row["model"]}:{b.processing_status}'] += 1
                continue
            results = _anthropic_results(client, row['batch_id'])
        usd, ok, bad = 0.0, 0, 0
        for cid, good, text, tin, tout in results:
            if not good:
                bad += 1
                continue
            cost = vv.call_usd(row['model'], tin, tout, batch=True)
            usd += cost
            ok += 1
            handlers[row['phase']](row['model'], cid, text, cost)
        q.ledger.add(model=row['model'], phase=row['phase'], batch=row['batch_id'],
                     usd=round(usd, 4), ok=ok, failed=bad)
        bl.add(kind='collected', batch_id=row['batch_id'], ok=ok, failed=bad, usd=round(usd, 4))
        status[f'{row["model"]}:забран'] += 1
        log(f'  забран {row["phase"]}/{row["model"]} {row["batch_id"]}: ok {ok}, сбоев {bad}, ${usd:.3f}')
    return dict(status)


# ── Фаза 2: регионы ────────────────────────────────────────────────────

def pages_dir(q):
    return os.path.join(q.work, 'pages')


def p2_keys(q, opts):
    keys = q.todo_keys()
    if opts.get('pages_file'):
        with open(opts['pages_file'], encoding='utf-8') as fh:
            wanted = {x.strip() for x in fh if x.strip()}
        keys = [k for k in keys if k in wanted]
    return keys


def p2_submit(q, opts, log):
    models = (opts.get('models') or f'{PRIMARY},{SECOND}').split(',')
    keys = p2_keys(q, opts)
    for model in models:
        pending = BatchLog(q).pending_ids('p2', model)
        todo = [k for k in keys if custom_id(k) not in pending and (vv.read_record(
            vv.rec_path(pages_dir(q), model, k)) or {}).get('status') != 'ok']
        log(f'{model}: страниц {len(keys)}, к отправке {len(todo)}, '
            f'оценка ${len(todo) * BATCH_ITEM_USD[model]:.2f}')
        if not opts.get('yes') or not todo:
            continue
        items = ((custom_id(k), vv.body_for(model, q.jobs[k])) for k in todo)
        submit(q, 'p2', model, items, log, limit=opts.get('limit'))
    if not opts.get('yes'):
        log('Без --yes пакеты не отправляются (только план).')


#: OpenAI держит в очереди Batch не больше 1,35 млн токенов на модель
#: (29.10: остальные пакеты — failed «token_limit_exceeded», без оплаты).
#: Пакет terra в 200 стр. ≈ 1 млн токенов, проходит за 2–4 мин — поэтому по одному.
OPENAI_INFLIGHT = 1


def p2_pump(q, opts, log):
    """Насос фазы 2: Haiku — все пакеты сразу; terra — по одному, следующий
    после того, как предыдущий забран. Каждый круг — `collect`. Выход —
    когда всё прочитано или упёрлись в потолок денег."""
    if (opts.get('models') or '') != PRIMARY:   # `--models gpt-6.1-terra` — Haiku шлёт другой процесс
        p2_submit(q, dict(opts, models=SECOND), log)
    while True:
        collect(q, handlers(q), log)
        inflight = [r for r in BatchLog(q).open_batches()
                    if r['provider'] == 'openai' and r['phase'] == 'p2']
        if len(inflight) < OPENAI_INFLIGHT:
            before = len(BatchLog(q).rows())
            p2_submit(q, dict(opts, models=PRIMARY, limit=1), log)
            if len(BatchLog(q).rows()) == before and not BatchLog(q).open_batches():
                log('насос: отправлять больше нечего или упёрлись в потолок — стоп')
                break
        time.sleep(opts.get('sleep') or 60)


def _page_handler(q):
    def handle(model, cid, text, usd):
        key = key_of(cid)
        rec = vv.make_record(key, text, model, usd)
        vv.write_record(vv.rec_path(pages_dir(q), model, key), rec)
    return handle


def handlers(q):
    return {'p2': _page_handler(q), 'arb': _arb_handler(q), 'p4': _p4_handler(q)}


def pages_v2_dir(q):
    return os.path.join(os.path.dirname(q.work), 'pages_v2')


def write_v2(q, key, rec, read_by):
    page_dir, _, page = key.rpartition('/p')
    path = os.path.join(pages_v2_dir(q), page_dir.split('/')[-1], f'p{page}.json')
    vv.write_record(path, dict(rec, read_by=read_by))


def arb_reply(q, key, rnd):
    return vv.read_record(os.path.join(q.work, 'arbiter', vv.ARBITER_MODEL,
                                       f'{custom_id(key)}-r{rnd}.json'))


def p2_merge(q, opts, log):
    """Сведение: согласие → основная версия; рассудил слой → его выбор;
    иначе — арбитр (ответ уже есть → правило приёма P2; нет — в список
    `arbiter_todo.json`). Итог страницы — `pages_v2\\<sha16>\\pN.json` с полем
    `read_by` (кто прочитал и как решено). Сводка — `merge_p2.json`."""
    stats, todo_arb, human = Counter(), [], []
    for k in p2_keys(q, opts):
        job = q.jobs[k]
        a = vv.read_record(vv.rec_path(pages_dir(q), PRIMARY, k))
        b = vv.read_record(vv.rec_path(pages_dir(q), SECOND, k))
        if not a or not b or a.get('status') != 'ok' and b.get('status') != 'ok':
            stats['ждёт_чтения'] += 1
            continue
        base = {'primary': PRIMARY, 'second': SECOND}
        ok, why = vv.agree(a, b, job.kind)
        if ok:
            write_v2(q, k, a, dict(base, decision='согласие'))
            stats['согласие'] += 1
            continue
        tb = vv.layer_tiebreak(a, b, job, why)
        if tb:
            write_v2(q, k, a if tb == 'A' else b, dict(base, decision=f'слой_{tb}', why=why))
            stats[f'слой_{tb}'] += 1
            continue
        verdict, rec = None, None
        for rnd in ('2', '1'):
            reply = arb_reply(q, k, rnd)
            if reply:
                verdict, rec, reasons, data = vv.judge_arbiter(reply['text'], job, a, b)
                break
        if verdict is None:
            todo_arb.append({'key': k, 'why': why, 'round': '1'})
            stats['к_арбитру'] += 1
            write_v2(q, k, a, dict(base, decision='ждёт_арбитра', why=why))
            continue
        if verdict == 'retry' and rnd == '1':
            todo_arb.append({'key': k, 'why': why, 'round': '2'})
            stats['арбитр_повтор'] += 1
            write_v2(q, k, a, dict(base, decision='ждёт_арбитра', why=why))
            continue
        if verdict.startswith('accept_'):
            write_v2(q, k, rec, dict(base, decision='арбитр_' + verdict[7:], why=why,
                                     arbiter=vv.ARBITER_MODEL, evidence=data.get('evidence'),
                                     confidence=data.get('confidence')))
            stats['арбитр_' + verdict[7:]] += 1
            continue
        # Человеку: в эталон идёт основная версия с пометкой, страница — в очередь.
        write_v2(q, k, a if a.get('status') == 'ok' else b,
                 dict(base, decision='человеку', why=why, arbiter=vv.ARBITER_MODEL,
                      reasons=reasons, differences=data.get('differences'),
                      confidence=data.get('confidence'), needs_human=True))
        human.append({'key': k, 'why': why, 'reasons': reasons,
                      'differences': data.get('differences'), 'confidence': data.get('confidence')})
        stats['человеку'] += 1
    for name, data in (('arbiter_todo.json', todo_arb), ('human_pages.json', human)):
        with open(os.path.join(q.work, name), 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(q.work, 'merge_p2.json'), 'w', encoding='utf-8') as fh:
        json.dump(dict(stats), fh, ensure_ascii=False, indent=1)
    log(f'сведение: {dict(stats)}')
    return stats


def arb_submit(q, opts, log):
    """Расхождения → пакеты Sonnet (раунд 1 — effort medium, раунд 2 — high)."""
    with open(os.path.join(q.work, 'arbiter_todo.json'), encoding='utf-8') as fh:
        todo = json.load(fh)
    pending = BatchLog(q).pending_ids('arb', vv.ARBITER_MODEL)
    items = []
    # Деньги Sonnet кончатся раньше очереди: сначала расхождения в числах,
    # потом номера/рисунки, разметка (варианты, таблицы) — в конце.
    rank = {'числа': 0, 'нет_ответа': 0, 'номера': 1, 'рисунки': 1, 'таблицы': 2, 'варианты': 2}
    todo.sort(key=lambda t: (min(rank.get(w, 2) for w in t['why']), t['key']))
    for t in todo:
        cid = f'{custom_id(t["key"])}-r{t["round"]}'
        if cid in pending or arb_reply(q, t['key'], t['round']):
            continue
        a = vv.read_record(vv.rec_path(pages_dir(q), PRIMARY, t['key']))
        b = vv.read_record(vv.rec_path(pages_dir(q), SECOND, t['key']))
        items.append((cid, vv.arbiter_params(q.jobs[t['key']], a, b, t['why'],
                                             effort='high' if t['round'] == '2' else 'medium')))
    log(f'к арбитру: {len(items)}, оценка ${len(items) * BATCH_ITEM_USD[vv.ARBITER_MODEL]:.2f}')
    if opts.get('yes') and items:
        submit(q, 'arb', vv.ARBITER_MODEL, items, log, limit=opts.get('limit'))


def _arb_handler(q):
    def handle(model, cid, text, usd):
        base, _, rnd = cid.rpartition('-r')
        path = os.path.join(q.work, 'arbiter', model, cid + '.json')
        vv.write_record(path, {'key': key_of(base), 'round': rnd, 'model': model,
                               'text': text, 'usd': usd})
    return handle


# ── Фаза 4: второй проход Opus по флагам ЗЭ/РЭ ─────────────────────────

def _row_id(r):
    import hashlib
    raw = f"{r['event_id']}|{r['number']}|{r.get('task_variant', '')}"
    return hashlib.sha1(raw.encode('utf-8'), usedforsecurity=False).hexdigest()[:20]


def p4_items(q):
    from problems.olympiad_audit import vsosh_recheck as rc
    rows = [json.loads(x) for x in open(os.path.join(q.v1, 'reference_problems_v1.jsonl'),
                                         encoding='utf-8')]
    files = {e['event_id']: e for e in (json.loads(x) for x in open(
        os.path.join(q.v1, 'events_files.jsonl'), encoding='utf-8'))}
    index = {x['pdf']: x['page_dir'] for x in (json.loads(y) for y in open(
        os.path.join(q.v1, 'render_index.jsonl'), encoding='utf-8'))}
    # Порядок: сначала флаги текста и формул, «нет_решения» — в конце (дороже и чаще ложный).
    prio = {'числа_не_со_страницы': 0, 'расходится_со_слоем': 0, 'пустое_условие': 0, 'katex': 0,
            'тест_без_вариантов': 1, 'пункты_не_разобраны': 1, 'скан_на_глаза': 1,
            'расхождение_с_ILE': 1, 'рисунок_плохая_вырезка': 2, 'рисунок_лишний_текст': 2,
            'нет_решения': 3}
    out = []
    for r in rows:
        if not rc.needs_recheck(r):
            continue
        full, near = rc.item_pages(r, files.get(r['event_id'], {}), index, q.jobs)
        out.append({'id': _row_id(r), 'row': _key_row_id(r), 'stage': r['stage'],
                    'flags': rc.item_flags(r), 'full': full, 'near': near,
                    'prio': min(prio.get(f, 2) for f in rc.item_flags(r) if f not in rc.SKIP_ONLY)})
    out.sort(key=lambda x: (x['prio'], x['row']))
    return out, {_key_row_id(r): r for r in rows}


def p4_reply(q, item_id, rnd):
    return vv.read_record(os.path.join(q.work, 'recheck', f'{item_id}-r{rnd}.json'))


def p4_submit(q, opts, log):
    from problems.olympiad_audit import vsosh_recheck as rc
    items, rows = p4_items(q)
    retry = set()
    path = os.path.join(q.work, 'recheck_retry.json')
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as fh:
            retry = set(json.load(fh))
    pending = BatchLog(q).pending_ids('p4', rc.MODEL)
    reqs = []
    for it in items:
        rnd = '2' if it['id'] in retry else '1'
        cid = f'{it["id"]}-r{rnd}'
        if cid in pending or p4_reply(q, it['id'], rnd):
            continue
        reqs.append((cid, rc.request_params(rows[it['row']], it['full'], it['near'], q.v1,
                                            effort='high' if rnd == '2' else 'medium')))
    # Сначала первые проходы, повторы (effort high) — на остаток потолка.
    reqs.sort(key=lambda x: x[0].endswith('-r2'))
    log(f'Opus: позиций {len(items)} ({Counter(i["stage"] for i in items)}), к отправке {len(reqs)}, '
        f'оценка ${len(reqs) * BATCH_ITEM_USD[rc.MODEL]:.2f}')
    if opts.get('yes') and reqs:
        # Потолок Opus внутри Claude — свой: $20 (задание Q2); в счёт — только пакеты Opus.
        spent = q.ledger.spent('anthropic', 'p4') + q.ledger.spent('anthropic', 'p4-probe') + sum(
            r['estimate_usd'] for r in BatchLog(q).open_batches() if r['phase'] == 'p4')
        room = 0.9 * P4_CAP - spent
        n = max(0, int(room / BATCH_ITEM_USD[rc.MODEL]))
        if n < len(reqs):
            log(f'по потолку Opus ${P4_CAP} отправляю {n} из {len(reqs)}')
        submit(q, 'p4', rc.MODEL, reqs[:n], log, limit=opts.get('limit'))


#: Потолок второго прохода Opus, $ (задание Q2).
P4_CAP = 20.0


def _p4_handler(q):
    def handle(model, cid, text, usd):
        vv.write_record(os.path.join(q.work, 'recheck', cid + '.json'),
                        {'id': cid.rpartition('-r')[0], 'round': cid.rpartition('-r')[2],
                         'model': model, 'text': text, 'usd': usd})
    return handle


def p4_decide(q, opts, log):
    """Ответы Opus → `recheck\\decisions.jsonl` (keep / fix / human / retry)."""
    from problems.olympiad_audit import vsosh_recheck as rc
    items, rows = p4_items(q)
    out, retry, stats = [], [], Counter()
    for it in items:
        r = rows[it['row']]
        layers = [q.jobs[f'{pd}/p{p}'].layer for pd, p in it['full'] + it['near']
                  if f'{pd}/p{p}' in q.jobs]
        rep2, rep1 = p4_reply(q, it['id'], '2'), p4_reply(q, it['id'], '1')
        rep = rep2 or rep1
        if not rep:
            stats['нет_ответа'] += 1
            continue
        verdict, fixes, why, data = rc.judge(rep['text'], r, layers)
        if verdict == 'retry' and not rep2:
            retry.append(it['id'])
            stats['повтор'] += 1
            # Повтор с effort high — только пока есть деньги Opus; итог до
            # повтора — человеку с пометкой (`--yes` у p4-submit дошлёт повтор).
            why = why + ['повтор_не_отправлен']
        if verdict == 'retry':
            verdict = 'human'
        stats[verdict] += 1
        out.append({'id': it['id'], 'row': it['row'], 'stage': it['stage'], 'flags': it['flags'],
                    'verdict': verdict, 'fixes': fixes, 'reasons': why,
                    'evidence': data.get('evidence'), 'why': data.get('why'),
                    'confidence': data.get('confidence'),
                    'pages': [os.path.join(q.v1, pd, f'p{p}.png') for pd, p in it['full']]})
    folder = os.path.join(q.work, 'recheck')
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'decisions.jsonl'), 'w', encoding='utf-8') as fh:
        for x in out:
            fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    with open(os.path.join(q.work, 'recheck_retry.json'), 'w', encoding='utf-8') as fh:
        json.dump(retry, fh)
    log(f'Opus: {dict(stats)}')
    return stats


# ── Фаза 3: ключи-сетки ────────────────────────────────────────────────

def _key_row_id(r):
    return f"{r['event_id']}|{r['number']}|{r.get('task_variant', '')}"


_KEY_HINT = re.compile(r'ответ\w* на тест|ключ|бланк ответ|ответы|ответ:|правильный ответ|верный ответ')
_TEST_HINT = re.compile(r'тест|вопрос')


def key_pages(q, ev, limit=8):
    """Страницы файлов ответов комплекта, где стоит ключ теста: по расшифровке
    P3 (таблица, «ответы/ключ», «тест/вопрос»); не нашлось — первые страницы
    файлов ответов. → [путь png]."""
    scored = []
    for key in ('solution_files', 'criteria_files', 'task_files'):
        for f in ev.get(key) or []:
            if key == 'task_files' and f.get('source_kind') != 'tasks+solutions':
                continue
            for p in range(1, int(f.get('pages') or 0) + 1):
                k = f"{f['page_dir']}/p{p}"
                rec = vv.read_record(q.p3_claude_path(k)) or vv.read_record(
                    os.path.join(q.v1, f['page_dir'], f'p{p}.json')) or {}
                text = json.dumps(rec.get('blocks') or [], ensure_ascii=False).lower()
                src = text + (q.jobs[k].layer.lower() if k in q.jobs else '')
                score = (('|' in text) + 2 * bool(_KEY_HINT.search(src))
                         + bool(_TEST_HINT.search(src)) - (p > 3))
                scored.append((score, key != 'task_files', -p,
                               os.path.join(q.v1, f['page_dir'], f'p{p}.png')))
    scored.sort(reverse=True)
    best = [x for x in scored if x[0] >= 2][:limit] or scored[:2]
    # Порядок страниц файла: ключ «вопрос — решение — ответ» идёт подряд.
    order = {x[3]: i for i, x in enumerate(sorted(scored, key=lambda x: (not x[1], x[3])))}
    return sorted((x[3] for x in best), key=order.get)


def _test_order(r):
    tail = str(r['number'])[5:]
    return int(tail) if tail.isdigit() else 0


def keys_prepare(q, log):
    from problems.olympiad_audit import vsosh_keys
    rows = [json.loads(x) for x in open(os.path.join(q.v1, 'reference_problems_v1.jsonl'),
                                         encoding='utf-8')]
    files = {e['event_id']: e for e in (json.loads(x) for x in open(
        os.path.join(q.v1, 'events_files.jsonl'), encoding='utf-8'))}
    by_ev = {}
    for r in rows:
        if str(r.get('number', '')).startswith('тест'):
            by_ev.setdefault(r['event_id'], []).append(r)
    need = sorted({r['event_id'] for r in rows if 'тест_без_ключа' in (r.get('check_flags') or [])})
    out = []
    for eid in need:
        tests = sorted(by_ev[eid], key=_test_order)
        out.append({'event_id': eid, 'pages': key_pages(q, files[eid]),
                    'rows': [_key_row_id(r) for r in tests],
                    'need': [_key_row_id(r) for r in tests
                             if 'тест_без_ключа' in (r.get('check_flags') or [])],
                    'questions': vsosh_keys.question_list(tests)})
    folder = os.path.join(q.work, 'keys')
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'events.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    log(f'комплектов {len(out)}, вопросов без ключа {sum(len(e["need"]) for e in out)}, '
        f'страниц ключа {sum(len(e["pages"]) for e in out)}')
    return out


KEY_MODELS = 'google/gemini-4-argon,gpt-6.1-terra'


def key_body(model, ev):
    from problems.olympiad_audit import vsosh_keys
    imgs = [vv.image_b64(path) for path in ev['pages']]
    text = ('Комплект: ' + ev['event_id'] + '.\nВопросы теста:\n'
            + json.dumps(ev['questions'], ensure_ascii=False))
    prov = vv.provider_of(model)
    if prov == 'anthropic':
        return {'model': model, 'max_tokens': 8000, 'output_config': {'effort': 'medium'},
                'system': vsosh_keys.KEY_SYSTEM,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': d}}
                    for mt, d in imgs] + [{'type': 'text', 'text': text}]}]}
    extra = {'detail': 'high'} if prov == 'openai' else {}
    parts = [{'type': 'image_url', 'image_url': dict({'url': f'data:{mt};base64,{d}'}, **extra)}
             for mt, d in imgs] + [{'type': 'text', 'text': text}]
    body = {'model': model, 'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': vsosh_keys.KEY_SYSTEM},
                         {'role': 'user', 'content': parts}]}
    if prov == 'openai':
        body.update(max_completion_tokens=12000, reasoning_effort='medium')
    else:
        body.update(max_tokens=12000, usage={'include': True}, reasoning={'effort': 'medium'})
    return body


def keys_folder(q, rnd='1'):
    return os.path.join(q.work, 'keys') if str(rnd) == '1' else os.path.join(q.work, 'keys', 'r2')


def keys2_prepare(q, log):
    """Второй проход ключей: комплекты, где обе модели не нашли ключ хотя бы
    к одному вопросу, — со ВСЕМИ страницами файлов ответов (до 20): в файлах
    «вопрос — решение» ответы разбросаны по 17–18 страницам, а первый проход
    видел до 8."""
    folder = keys_folder(q)
    with open(os.path.join(folder, 'events.json'), encoding='utf-8') as fh:
        events = {e['event_id']: e for e in json.load(fh)}
    files = {e['event_id']: e for e in (json.loads(x) for x in open(
        os.path.join(q.v1, 'events_files.jsonl'), encoding='utf-8'))}
    need = set()
    for x in (json.loads(y) for y in open(os.path.join(folder, 'queue.jsonl'), encoding='utf-8')):
        reps = [v for v in x['replies'].values()]
        if x['why'] == 'нет_ответа_модели' and all(v is None or v[0] is None for v in reps):
            need.add(x['row'].split('|')[0])
    out = []
    for eid in sorted(need):
        ev = files[eid]
        pages = []
        for key in ('solution_files', 'criteria_files', 'task_files'):
            for f in ev.get(key) or []:
                if key == 'task_files' and f.get('source_kind') != 'tasks+solutions':
                    continue
                pages += [os.path.join(q.v1, f['page_dir'], f'p{p}.png')
                          for p in range(1, int(f.get('pages') or 0) + 1)]
        if len(pages) > len(events[eid]['pages']):
            out.append(dict(events[eid], pages=pages[:20]))
    os.makedirs(keys_folder(q, 2), exist_ok=True)
    with open(os.path.join(keys_folder(q, 2), 'events.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    log(f'второй проход ключей: комплектов {len(out)} (из {len(need)} без ключа у обеих моделей), '
        f'страниц {sum(len(e["pages"]) for e in out)}')


def keys_run(q, opts, log):
    """Ключи двумя моделями (синхронно: ~200 комплектов). `--limit` — первые N."""
    from concurrent.futures import ThreadPoolExecutor
    folder = keys_folder(q, opts.get('round') or '1')
    with open(os.path.join(folder, 'events.json'), encoding='utf-8') as fh:
        events = json.load(fh)
    if opts.get('pages_file'):   # калибровка: только комплекты из файла
        with open(opts['pages_file'], encoding='utf-8') as fh:
            wanted = {x.strip() for x in fh if x.strip()}
        events = [e for e in events if e['event_id'] in wanted]
    if opts.get('limit'):
        events = events[:opts['limit']]
    models = (opts.get('models') or KEY_MODELS).split(',')
    log(f'комплектов {len(events)}, модели {models}')
    if not opts.get('yes'):
        return log('Без --yes вызовов нет (только план).')
    env = vv.load_env()

    def one(arg):
        model, ev = arg
        path = os.path.join(folder, model.replace('/', '__'), ev['event_id'] + '.json')
        if os.path.isfile(path):
            return
        prov = vv.provider_of(model)
        if not q.ledger.allow(prov, 0.1):
            return log(f'стоп: потолок {prov}')
        try:
            text, tin, tout, usd = vv.call_with_retry(model, key_body(model, ev), env)
        except Exception as exc:  # noqa: BLE001 — сбой комплекта не роняет прогон
            return log(f'  {model} {ev["event_id"]}: {str(exc)[:200]}')
        q.ledger.add(model=model, phase='keys', key=ev['event_id'], usd=round(usd, 6),
                     tin=tin, tout=tout)
        vv.write_record(path, {'event_id': ev['event_id'], 'model': model, 'text': text, 'usd': usd})

    with ThreadPoolExecutor(opts.get('workers') or 6) as ex:
        list(ex.map(one, [(m, e) for e in events for m in models]))
    log(f'потрачено фазой ключей: ${q.ledger.spent(phase="keys"):.3f}')


def keys_decide(q, opts, log):
    """Сведение двух моделей → keys/accepted.jsonl и очередь keys/queue.jsonl."""
    from problems.olympiad_audit import vsosh_keys
    folder = os.path.join(q.work, 'keys')
    with open(os.path.join(folder, 'events.json'), encoding='utf-8') as fh:
        events = json.load(fh)
    rows = {_key_row_id(r): r for r in (json.loads(x) for x in open(
        os.path.join(q.v1, 'reference_problems_v1.jsonl'), encoding='utf-8'))}
    acc, queue, why = [], [], Counter()
    for ev in events:
        # Второе мнение — Gemini; где OpenRouter упёрся в лимит ключа (29.10,
        # 18 комплектов) — Claude Sonnet: тоже другое семейство, чем GPT.
        models, replies = [], []
        for group in (('gpt-6.1-terra',), ('google/gemini-4-argon', 'claude-sonnet-5-5')):
            for m in group:
                # Второй проход (все страницы файлов ответов) старше первого.
                rec = None
                for fold in (keys_folder(q, 2), folder):
                    rec = rec or vv.read_record(os.path.join(fold, m.replace('/', '__'),
                                                             ev['event_id'] + '.json'))
                if rec:
                    models.append(m)
                    replies.append(vsosh_keys.parse_reply(rec['text']))
                    break
            else:
                models.append(group[0])
                replies.append({})
        tests = [rows[k] for k in ev['rows']]
        for i, (r, ans, reason) in enumerate(vsosh_keys.decide(tests, replies[0], replies[1]), 1):
            k = _key_row_id(r)
            if k not in ev['need']:
                continue
            if ans:
                acc.append({'row': k, 'labels': list(ans), 'models': models,
                            'answer': vsosh_keys.answer_text(
                                ans, vsosh_keys.options(r.get('statement_md') or ''))})
            else:
                queue.append({'row': k, 'why': reason, 'pages': ev['pages'],
                              'replies': {m: rep.get(f'q{i}') for m, rep in zip(models, replies)}})
            why[reason or 'принят'] += 1
    for name, data in (('accepted.jsonl', acc), ('queue.jsonl', queue)):
        with open(os.path.join(folder, name), 'w', encoding='utf-8') as fh:
            for x in data:
                fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    log(f'ключи: принято {len(acc)}, в очередь {len(queue)}; {dict(why)}')
    return acc, queue


# ── Фаза 5: сборка v2 ──────────────────────────────────────────────────

QUEUE_PATH = r'C:\Users\shipu\weconomics-data\quality_20261029\queues\q2_vsosh_v2.jsonl'


def build_v2(q, cmd, opts, log):
    """Сборка эталона v2 и все проверки фазы 5 → `digitized\\v2\\`."""
    from problems.olympiad_audit import digitize
    from problems.olympiad_audit import vsosh_v2 as V
    v2_root = os.path.dirname(q.work)
    rows = V.assemble_v2(q.v1, v2_root, log)
    v1_rows = digitize.read_jsonl(os.path.join(q.v1, 'reference_problems_v1.jsonl'))
    ile = V.ile_2008_rows(os.path.join(os.path.dirname(os.path.dirname(q.v1)), 'raw', 'ile', 'print',
                                       'iloveeconomics.ru__print-all-tasks__3950.html'),
                          os.path.join(v2_root, 'figures_v2', 'ile_2008_09'))
    rows += ile
    log(f'ЗЭ 2008/09 со страницы ILE: {len(ile)} заданий')
    st4 = V.apply_recheck(rows, os.path.join(q.work, 'recheck', 'decisions.jsonl'))
    st3 = V.apply_keys(rows, os.path.join(q.work, 'keys', 'accepted.jsonl'), v1_rows)
    human_path = os.path.join(q.work, 'human_pages.json')
    human = json.load(open(human_path, encoding='utf-8')) if os.path.isfile(human_path) else []
    V.check_rows(rows, q.v1, v2_root, [h['key'] for h in human])
    out = os.path.join(v2_root, 'reference_problems_v2.jsonl')
    digitize.write_jsonl(out, rows)
    kx = V.katex_check(out, os.path.join(v2_root, 'katex_v2.json'))
    bad = {k for k, v in (kx.get('by_key') or {}).items() if v}
    for r in rows:
        if V.row_key(r) in bad:
            r['check_flags'] = sorted(set(r['check_flags']) | {'katex'})
    digitize.write_jsonl(out, rows)
    keys = Counter(V.row_key(r) for r in rows)
    key_queue = digitize.read_jsonl(os.path.join(q.work, 'keys', 'queue.jsonl')) \
        if os.path.isfile(os.path.join(q.work, 'keys', 'queue.jsonl')) else []
    queue = V.build_queue(rows, q.v1, key_queue, human, QUEUE_PATH)
    res = {'tasks': len(rows), 'events': len({r['event_id'] for r in rows}),
           'by_stage': dict(Counter(r['stage'] for r in rows)),
           'v1_by_stage': dict(Counter(r['stage'] for r in v1_rows)),
           'flags_v1': V.flag_share(v1_rows), 'flags_v2': V.flag_share(rows),
           'flag_counts_v2': dict(Counter(f for r in rows for f in set(r['check_flags']) - V.INFO)),
           'keys_unique': all(v == 1 for v in keys.values()),
           'katex_errors': kx.get('errors'), 'katex_red': kx.get('red'), 'katex_fields': kx.get('fields'),
           'test_keys_outside_options': V.test_keys_in_options(rows),
           'figures_bad': V.figures_ok(rows, v2_root), 'recheck_applied': dict(st4), 'keys_applied': dict(st3),
           'changed': V.changed_keys(v1_rows, rows, os.path.join(v2_root, 'changed_keys_v1_v2.csv')),
           'queue_items': len(queue), 'queue_by_check': dict(Counter(x['check'] for x in queue)),
           'queue_tasks': len({x['ref_key'] for x in queue})}
    if not opts.get('no_bank'):
        res['bank_plan'] = {f'{s}|{v}': n for (s, v), n in V.bank_plan(rows, v2_root).items()}
    with open(os.path.join(v2_root, 'check_v2.json'), 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    log(json.dumps({k: v for k, v in res.items() if k not in ('figures_bad',)}, ensure_ascii=False)[:4000])
    return res


def run(cmd, opts):
    q = Q2(cmd.digitized)
    action = opts.get('action')
    log = cmd._say
    if action == 'jobs':
        n = vv.write_job_cache(q.v1, os.path.join(q.work, 'jobs_cache.jsonl'))
        return log(f'страниц в кэше: {n}')
    if action == 'calib':
        return calib_run(q, opts, log)
    if action == 'calib-report':
        return calib_report(q, log)
    if action == 'p2-submit':
        return p2_submit(q, opts, log)
    if action == 'build':
        return build_v2(q, cmd, opts, log)
    if action == 'p2-pump':
        return p2_pump(q, opts, log)
    if action == 'p2-merge':
        return p2_merge(q, opts, log)
    if action == 'arb-submit':
        return arb_submit(q, opts, log)
    if action == 'p4-submit':
        return p4_submit(q, opts, log)
    if action == 'p4-decide':
        return p4_decide(q, opts, log)
    if action == 'collect':
        return log(str(collect(q, handlers(q), log)))
    if action == 'keys-prepare':
        return keys_prepare(q, log)
    if action == 'keys':
        return keys_run(q, opts, log)
    if action == 'keys2-prepare':
        return keys2_prepare(q, log)
    if action == 'keys-decide':
        return keys_decide(q, opts, log)
    raise ValueError(action)
