# -*- coding: utf-8 -*-
"""Замер Б4: sync против Batch API, кэш префикса GPT-5.6 (Notion, «Надо»).

Единственный вопрос: сохраняется ли кэш промпта (`cached_tokens`) внутри
Batch API, где OpenAI сам решает, когда обработать каждую строку в течение
24-часового окна. Документация OpenAI об этом молчит, а от ответа втрое
меняется смета всего прогона обогащения на 41 307 задач — гадать нельзя.

100 задач (сид 20260831, та же стратификация, что в pilot_enrich_v2.py),
ТОЛЬКО вызов 1 (классификация), reasoning=none, модель gpt-5.6-terra.

⚠️ ПОЧЕМУ ШАГИ РАЗДЕЛЕНЫ. Batch API может выполняться до 24 часов — нельзя
держать один процесс, который блокирующе ждёт. Каждый шаг читает и
дописывает файлы-чекпоинты в reports/pilot_b4/, поэтому его можно повторять
и продолжать в любой момент.

Запуск (из корня проекта):
    venv313\\Scripts\\python.exe scripts\\pilot_b4_measurement.py sample
    venv313\\Scripts\\python.exe scripts\\pilot_b4_measurement.py sync --max-cost 5.0
    venv313\\Scripts\\python.exe scripts\\pilot_b4_measurement.py batch-submit
    venv313\\Scripts\\python.exe scripts\\pilot_b4_measurement.py batch-poll
    venv313\\Scripts\\python.exe scripts\\pilot_b4_measurement.py batch-download
    venv313\\Scripts\\python.exe scripts\\pilot_b4_measurement.py report
"""
import argparse
import hashlib
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402
django.setup()  # noqa: E402

from django.conf import settings  # noqa: E402
from django.test import override_settings  # noqa: E402

from problems.ai import providers  # noqa: E402
from problems.ai import batch as batch_mod  # noqa: E402
from problems.enrich import prompts_v2  # noqa: E402
from problems.enrich.text import problem_full_text  # noqa: E402
from problems.enrich.shortlist import shortlist_for  # noqa: E402
from problems.management.commands.pilot_enrich_v2 import (  # noqa: E402
    build_sample, real_call_cost, _model_prices)
from problems.models import Problem  # noqa: E402

SEED = 20260831
LIMIT = 100
TERRA = 'gpt-5.6-terra'
CACHE_HIT_THRESHOLD = 9000

OUT_DIR = Path('reports/pilot_b4')
OUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_PATH = OUT_DIR / 'sample.json'
SYNC_LOG_PATH = OUT_DIR / 'sync_log.jsonl'
BATCH_DIR = OUT_DIR / 'batch_files'
BATCH_MANIFEST_PATH = OUT_DIR / 'batch_manifest.json'
BATCH_RESULTS_DIR = OUT_DIR / 'batch_results'
BATCH_LOG_PATH = OUT_DIR / 'batch_log.jsonl'


# ---------------------------------------------------------------------------
# Общее
# ---------------------------------------------------------------------------

def core_and_schema():
    core = prompts_v2.call1_core(with_concepts=True)
    schema = prompts_v2.call1_schema(with_concepts=True)
    return core, schema


def core_md5(core_text):
    return hashlib.md5(core_text.encode('utf-8')).hexdigest()


def _read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


# ---------------------------------------------------------------------------
# sample — выборка + md5 ядра, без обращений к API
# ---------------------------------------------------------------------------

def _ordered_sample_and_shortlists(ids):
    problems = list(
        Problem.objects.filter(id__in=ids).prefetch_related('parts'))
    by_id = {p.id: p for p in problems}
    ordered = [by_id[pid] for pid in ids if pid in by_id]
    shortlists = {
        p.id: shortlist_for(problem_full_text(p.statement, p.parts.all()))
        for p in ordered
    }
    return ordered, shortlists


def cmd_sample(args):
    sample_ids, strata_report = build_sample(LIMIT, SEED)
    ordered, shortlists = _ordered_sample_and_shortlists(sample_ids)
    core, _schema = core_and_schema()

    payload = {
        'seed': SEED,
        'limit': LIMIT,
        'strata_report': strata_report,
        'ids_in_order': [p.id for p in ordered],
        'core_md5': core_md5(core),
        'core_len_chars': len(core),
    }
    with open(SAMPLE_PATH, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print('=== ВЫБОРКА Б4 (seed=%d, limit=%d) ===' % (SEED, LIMIT))
    for line in strata_report:
        print('  ' + line)
    print('Итого задач: %d' % len(ordered))
    print('md5(ядро вызова 1) = %s (длина %d символов)' % (
        payload['core_md5'], payload['core_len_chars']))
    print('Сохранено: %s' % SAMPLE_PATH)


def load_sample():
    with open(SAMPLE_PATH, encoding='utf-8') as fh:
        payload = json.load(fh)
    ordered, shortlists = _ordered_sample_and_shortlists(payload['ids_in_order'])
    return ordered, shortlists, payload


def _assert_core_matches(payload):
    core, schema = core_and_schema()
    now = core_md5(core)
    if now != payload['core_md5']:
        raise SystemExit(
            'ЯДРО РАСХОДИТСЯ С СОХРАНЁННОЙ ВЫБОРКОЙ: было %s, сейчас %s — '
            'замер недействителен, остановка.' % (payload['core_md5'], now))
    return core, schema


# ---------------------------------------------------------------------------
# sync — строго последовательный прогон
# ---------------------------------------------------------------------------

def cmd_sync(args):
    ordered, shortlists, payload = load_sample()
    core, schema = _assert_core_matches(payload)
    print('md5(ядро) = %s — совпадает с выборкой' % payload['core_md5'])

    provider = providers.OpenAIProvider()
    max_tokens = getattr(settings, 'AI_MAX_TOKENS', 4000)
    spent = Decimal('0')
    rows = []

    with override_settings(AI_REASONING_EFFORT='none'):
        for i, problem in enumerate(ordered, start=1):
            if args.max_cost is not None and spent >= Decimal(str(args.max_cost)):
                print('СТОП по --max-cost=$%.2f на запросе %d из %d' % (
                    args.max_cost, i, len(ordered)))
                break

            text = problem_full_text(problem.statement, problem.parts.all())
            user1 = prompts_v2.call1_user_text(text, shortlists.get(problem.id))

            t0 = time.perf_counter()
            error = None
            reply = None
            try:
                reply = provider.complete([core], user1, schema, TERRA, max_tokens)
            except providers.ProviderError as exc:
                error = str(exc)
            elapsed = time.perf_counter() - t0

            row = {'index': i, 'problem_id': problem.id, 'elapsed_sec': elapsed}
            if reply is not None:
                cost = real_call_cost(TERRA, reply)
                spent += cost
                schema_ok = True
                try:
                    json.loads(reply.text)
                except ValueError:
                    schema_ok = False
                row.update({
                    'input_tokens': reply.input_tokens,
                    'cached_tokens': reply.cache_read_tokens,
                    'output_tokens': reply.output_tokens,
                    'reasoning_tokens': reply.reasoning_tokens,
                    'schema_ok': schema_ok,
                    'cost_usd': str(cost),
                    'error': None,
                })
            else:
                row.update({
                    'input_tokens': None, 'cached_tokens': None,
                    'output_tokens': None, 'reasoning_tokens': None,
                    'schema_ok': False, 'cost_usd': '0', 'error': error,
                })
            rows.append(row)
            print('  #%3d id=%-6d cached=%-6s out=%-4s t=%5.2fs потрачено=$%.4f%s' % (
                i, problem.id, row['cached_tokens'], row['output_tokens'],
                elapsed, spent,
                '' if row['error'] is None else ' ОШИБКА: %s' % row['error']))

    with open(SYNC_LOG_PATH, 'w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    print('Готово: %d запросов из %d, потрачено $%.4f. Журнал: %s' % (
        len(rows), len(ordered), spent, SYNC_LOG_PATH))


# ---------------------------------------------------------------------------
# batch — один файл, submit / poll / download
# ---------------------------------------------------------------------------

def cmd_batch_submit(args):
    ordered, shortlists, payload = load_sample()
    core, schema = _assert_core_matches(payload)
    print('md5(ядро) = %s — совпадает с выборкой' % payload['core_md5'])
    max_tokens = getattr(settings, 'AI_MAX_TOKENS', 4000)

    requests_iter = []
    for problem in ordered:
        text = problem_full_text(problem.statement, problem.parts.all())
        user1 = prompts_v2.call1_user_text(text, shortlists.get(problem.id))
        requests_iter.append(batch_mod.build_request(
            custom_id=str(problem.id), model=TERRA, system_blocks=[core],
            user_text=user1, schema=schema, max_tokens=max_tokens,
            reasoning_effort='none'))

    manifest = batch_mod.split_into_files(requests_iter, BATCH_DIR, prefix='b4')
    if len(manifest) != 1:
        raise SystemExit(
            'Ожидался ОДИН файл (100 строк), получили %d — прогон не '
            'соответствует условию замера, остановка.' % len(manifest))
    print('Файл: %s, строк: %d, байт: %d' % (
        manifest[0]['path'], manifest[0]['line_count'], manifest[0]['byte_count']))
    batch_mod.save_manifest(manifest, BATCH_MANIFEST_PATH)

    import openai
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    try:
        manifest = batch_mod.submit_pending(client, manifest, BATCH_MANIFEST_PATH)
    except Exception as exc:
        print('ОШИБКА ПРИ ОТПРАВКЕ БАТЧА (текст дословно):')
        print('  %r' % exc)
        body = getattr(exc, 'body', None)
        if body is not None:
            print('  тело ответа: %s' % body)
        raise
    for entry in manifest:
        print('Отправлено: batch_id=%s статус=%s' % (
            entry.get('batch_id'), entry.get('status')))


def cmd_batch_poll(args):
    import openai
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    manifest = batch_mod.load_manifest(BATCH_MANIFEST_PATH)
    if not manifest:
        raise SystemExit('Манифест пуст — сначала batch-submit.')
    manifest = batch_mod.refresh_statuses(client, manifest, BATCH_MANIFEST_PATH)
    for entry in manifest:
        print('batch_id=%s статус=%s request_counts=%s' % (
            entry.get('batch_id'), entry.get('status'),
            entry.get('request_counts')))
    print('Все терминальны: %s' % batch_mod.all_terminal(manifest))


def cmd_batch_download(args):
    import openai
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    manifest = batch_mod.load_manifest(BATCH_MANIFEST_PATH)
    if not manifest:
        raise SystemExit('Манифест пуст — сначала batch-submit.')
    manifest = batch_mod.refresh_statuses(client, manifest, BATCH_MANIFEST_PATH)
    if not batch_mod.all_terminal(manifest):
        print('Батч ещё выполняется, статус: %s' % manifest[0].get('status'))
        return

    downloaded = batch_mod.download_results(client, manifest, BATCH_RESULTS_DIR)
    print('Скачано: %s' % downloaded)

    rows = []
    for result_path in downloaded:
        with open(result_path, encoding='utf-8') as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                line = json.loads(raw_line)
                custom_id = line.get('custom_id')
                response = line.get('response') or {}
                body = response.get('body') or {}
                usage = body.get('usage') or {}
                in_details = usage.get('input_tokens_details') or {}
                out_details = usage.get('output_tokens_details') or {}
                total_input = usage.get('input_tokens') or 0
                cached = in_details.get('cached_tokens') or 0
                text = batch_mod._output_text_from_batch_body(body)
                schema_ok = True
                if line.get('error'):
                    schema_ok = False
                else:
                    try:
                        json.loads(text) if text else None
                    except ValueError:
                        schema_ok = False
                cache_write = in_details.get('cache_write_tokens') or 0
                fresh_input = max(total_input - cached, 0)
                output_tokens = usage.get('output_tokens') or 0
                price_in, price_cache, price_out = _model_prices(TERRA)
                cost = (Decimal(fresh_input) * price_in
                       + Decimal(output_tokens) * price_out
                       + Decimal(cache_write) * price_in * Decimal('1.25')
                       + Decimal(cached) * price_cache) / Decimal(10 ** 6)
                rows.append({
                    'problem_id': int(custom_id) if custom_id and custom_id.isdigit() else custom_id,
                    'input_tokens': fresh_input,
                    'cached_tokens': cached,
                    'cache_write_tokens': cache_write,
                    'output_tokens': output_tokens,
                    'reasoning_tokens': out_details.get('reasoning_tokens') or 0,
                    'created_at': body.get('created_at'),
                    'schema_ok': schema_ok,
                    'cost_usd': str(cost),
                    'error': line.get('error'),
                    'status_code': response.get('status_code'),
                })

    with open(BATCH_LOG_PATH, 'w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    print('Разобрано строк: %d. Журнал: %s' % (len(rows), BATCH_LOG_PATH))


# ---------------------------------------------------------------------------
# report — свод чисел из фазы 1 промпта
# ---------------------------------------------------------------------------

def cmd_report(args):
    with open(SAMPLE_PATH, encoding='utf-8') as fh:
        sample_payload = json.load(fh)
    sync_rows = _read_jsonl(SYNC_LOG_PATH)
    batch_rows = _read_jsonl(BATCH_LOG_PATH)

    def stored_cost(r):
        # ⚠️ Берём УЖЕ посчитанную стоимость строки (со всеми 4 счётчиками,
        # включая cache_write_tokens), а не пересчитываем заново по трём —
        # первая версия отчёта тут теряла надбавку ×1.25 на кэш-запись и
        # занижала факт на ~6% ($1.2735 вместо реальных $1.3540).
        return Decimal(r['cost_usd'])

    print('=== Б4: sync против batch, замер кэша (100 задач, seed=%d) ===' %
         sample_payload['seed'])
    print('md5(ядро вызова 1) = %s' % sample_payload['core_md5'])
    print('')

    ok_sync = [r for r in sync_rows if r.get('error') is None]
    print('--- SYNC ---')
    print('успешных запросов: %d из %d' % (len(ok_sync), len(sync_rows)))
    if ok_sync:
        print('запрос №1: cached_tokens = %s (ожидание ~0)' % ok_sync[0]['cached_tokens'])
        rest = ok_sync[1:]
        hit = sum(1 for r in rest if (r['cached_tokens'] or 0) >= CACHE_HIT_THRESHOLD)
        print('запросы №2..%d: доля с cached_tokens >= %d — %d из %d (ожидание >= 95 из 99)' % (
            len(ok_sync), CACHE_HIT_THRESHOLD, hit, len(rest)))
        sync_cost = sum((stored_cost(r) for r in ok_sync), Decimal('0'))
        print('фактическая стоимость прогона по usage: $%.4f' % sync_cost)
        cached_nonzero = sorted(r['cached_tokens'] for r in rest if (r['cached_tokens'] or 0) > 0)
        if cached_nonzero:
            core_size = _percentile(cached_nonzero, 50)
            print('фактический размер ядра по данным API '
                 '(медиана cached_tokens закэшированных запросов) = %.0f токенов' % core_size)

    print('')
    print('--- BATCH ---')
    ok_batch = [r for r in batch_rows
               if r.get('error') is None and r.get('status_code') in (200, None)]
    print('успешных строк: %d из %d' % (len(ok_batch), len(batch_rows)))
    if ok_batch:
        hit_b = sum(1 for r in ok_batch if (r['cached_tokens'] or 0) >= CACHE_HIT_THRESHOLD)
        print('доля строк с cached_tokens >= %d: %d из %d (%.1f%%) — измеряем, ожидания нет' % (
            CACHE_HIT_THRESHOLD, hit_b, len(ok_batch), 100.0 * hit_b / len(ok_batch)))
        cached_vals = sorted(r['cached_tokens'] or 0 for r in ok_batch)
        print('распределение cached_tokens по строкам (не сумма):')
        print('  мин=%d  25%%=%.0f  медиана=%.0f  75%%=%.0f  макс=%d' % (
            cached_vals[0], _percentile(cached_vals, 25), _percentile(cached_vals, 50),
            _percentile(cached_vals, 75), cached_vals[-1]))
        created = sorted(r['created_at'] for r in ok_batch if r.get('created_at'))
        if created:
            spread = created[-1] - created[0]
            print('разброс времени ответа между первой и последней строкой: '
                 '%d сек (%.1f мин)' % (spread, spread / 60))
        else:
            print('разброс времени ответа: нет поля created_at в теле ответа — не измерено')
        batch_cost_full = sum((stored_cost(r) for r in ok_batch), Decimal('0'))
        print('фактическая стоимость по usage (тариф без скидки Batch): $%.4f' % batch_cost_full)
        print('то же со скидкой Batch API 50%%: $%.4f' % (batch_cost_full * Decimal('0.5')))
    else:
        print('нет данных — batch-download ещё не запускался или батч не завершён')

    print('')
    print('--- ДЛИНА ВЫХОДА И СХЕМА (все успешные ответы вызова 1) ---')
    all_ok = ok_sync + ok_batch
    out_lens = sorted(r['output_tokens'] for r in all_ok if r.get('output_tokens') is not None)
    if out_lens:
        median = _percentile(out_lens, 50)
        p90 = _percentile(out_lens, 90)
        print('фактическая длина выхода вызова 1: медиана=%.0f p90=%.0f токенов '
             '(в смете заложено 260)' % (median, p90))
        price_out_terra = _model_prices(TERRA)[2]
        n_corpus = 41307
        only_output_cost = lambda tok: (Decimal(n_corpus) * Decimal(tok)
                                        * price_out_terra) / Decimal(10 ** 6)
        print('  только выходные токены вызова 1 на весь корпус (41 307 задач, '
             'без входа/кэша): по смете (260) $%.2f, по факту p90 (%.0f) $%.2f, '
             'по факту медианы (%.0f) $%.2f' % (
                 only_output_cost(260), p90, only_output_cost(p90),
                 median, only_output_cost(median)))

    schema_fail = sum(1 for r in (sync_rows + batch_rows) if r.get('schema_ok') is False)
    print('ответов, не прошедших схему strict с первого раза: %d из %d' % (
        schema_fail, len(sync_rows) + len(batch_rows)))

    print('')
    print('--- ПОДТВЕРЖДЕНИЕ УЧЁТА КЭША ---')
    print('cached_tokens НЕ прибавляется к input_tokens при подсчёте цены: '
         'providers.py::OpenAIProvider._reply_from вычитает cache_read из '
         'полного входа (`input_tokens=max(total_input - cache_read, 0)`), '
         'и `real_call_cost` складывает input_tokens и cache_read_tokens как '
         'непересекающиеся величины по разным ценам.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('sample')

    p_sync = sub.add_parser('sync')
    p_sync.add_argument('--max-cost', type=float, default=None)

    sub.add_parser('batch-submit')
    sub.add_parser('batch-poll')
    sub.add_parser('batch-download')
    sub.add_parser('report')

    args = parser.parse_args()
    {
        'sample': cmd_sample,
        'sync': cmd_sync,
        'batch-submit': cmd_batch_submit,
        'batch-poll': cmd_batch_poll,
        'batch-download': cmd_batch_download,
        'report': cmd_report,
    }[args.cmd](args)


if __name__ == '__main__':
    main()
