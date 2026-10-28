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
    raise ValueError(action)
