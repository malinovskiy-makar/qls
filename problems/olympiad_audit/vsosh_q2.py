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


def keys_run(q, opts, log):
    """Ключи двумя моделями (синхронно: ~200 комплектов). `--limit` — первые N."""
    from concurrent.futures import ThreadPoolExecutor
    folder = os.path.join(q.work, 'keys')
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
    models = (opts.get('models') or KEY_MODELS).split(',')
    rows = {_key_row_id(r): r for r in (json.loads(x) for x in open(
        os.path.join(q.v1, 'reference_problems_v1.jsonl'), encoding='utf-8'))}
    acc, queue, why = [], [], Counter()
    for ev in events:
        replies = []
        for m in models:
            rec = vv.read_record(os.path.join(folder, m.replace('/', '__'), ev['event_id'] + '.json'))
            replies.append(vsosh_keys.parse_reply(rec['text']) if rec else {})
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
    if action == 'keys-prepare':
        return keys_prepare(q, log)
    if action == 'keys':
        return keys_run(q, opts, log)
    if action == 'keys-decide':
        return keys_decide(q, opts, log)
    raise ValueError(action)
