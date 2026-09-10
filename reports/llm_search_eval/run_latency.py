# -*- coding: utf-8 -*-
"""Задержка систем на ОДИНОЧНОМ запросе, без параллельности.

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ЗАМЕР. Боевые прогоны шли в 8 потоков, и «общее время
делить на число запросов» дало бы задержку в восемь раз меньше настоящей.
Человек на сайте ждёт ОДИН свой запрос, а не средний по пачке. Поэтому
здесь запросы идут строго по одному.

Плотная и лексическая ноги меряются целиком и бесплатно. Реранкер — на
небольшой выборке: каждый вызов стоит денег, а разброс задержки виден и
на десяти.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_latency.py [--sample 10]
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

import numpy as np  # noqa: E402

import envbridge  # noqa: E402
import orclient  # noqa: E402
import poolbuild  # noqa: E402
import reranking  # noqa: E402
import run_batch_judge  # noqa: E402
from catalog import lexical_bm25 as lex  # noqa: E402
from problems.ai.providers import get_provider  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'latency.json')


def stats(times):
    if not times:
        return None
    ordered = sorted(times)
    return {'p50': round(statistics.median(ordered), 1),
            'p95': round(ordered[min(int(len(ordered) * 0.95),
                                     len(ordered) - 1)], 1),
            'n': len(ordered)}


def main():
    sample = int(sys.argv[sys.argv.index('--sample') + 1]
                 if '--sample' in sys.argv else 10)
    envbridge.apply_to_process()
    pool, corpus = run_batch_judge.load()
    result = {}

    # ── S1: лексика ────────────────────────────────────────────────────
    index = lex.load_index(os.path.join(HERE, 'bm25_index'))
    times = []
    for row in pool:
        started = time.perf_counter()
        lex.search(index, row['text'], 50)
        times.append((time.perf_counter() - started) * 1000)
    result['S1_bm25'] = stats(times)

    # ── S0: плотный поиск, включая кодирование запроса ─────────────────
    from problems.management.commands.search_eval import _кодировщик_модели
    import run_pool
    ids, vecs = [], []
    for pid, raw in run_pool.visible_queryset().values_list(
            'id', 'embedding').iterator(chunk_size=1000):
        raw = bytes(raw)
        if len(raw) == 1024 * 4:
            ids.append(pid)
            vecs.append(np.frombuffer(raw, dtype=np.float32))
    matrix = np.stack(vecs)
    matrix /= np.where(np.linalg.norm(matrix, axis=1, keepdims=True) == 0,
                       1e-9, np.linalg.norm(matrix, axis=1, keepdims=True))
    encode = _кодировщик_модели()
    times = []
    for row in pool:
        started = time.perf_counter()
        vector = encode([row['text']])[0]
        vector = vector / (np.linalg.norm(vector) or 1e-9)
        np.argsort(-(matrix @ vector))[:50]
        times.append((time.perf_counter() - started) * 1000)
    result['S0_dense'] = stats(times)
    result['S2_rrf'] = {
        'p50': round(result['S0_dense']['p50'] + result['S1_bm25']['p50'], 1),
        'p95': round(result['S0_dense']['p95'] + result['S1_bm25']['p95'], 1),
        'n': len(pool),
        'note': 'сумма двух ног: слияние по рангам считается за микросекунды'}

    # ── S3: реранкер, по одному запросу за раз ─────────────────────────
    client = orclient.Client(
        providers={'zai': get_provider('glm')},
        costs_path=os.path.join(HERE, 'costs.json'),
        failures_path=os.path.join(HERE, 'failures.jsonl'),
        budgets=orclient.BUDGETS)
    times = []
    for row in pool[:sample]:
        started = time.perf_counter()
        for chunk in [row['pool'][i:i + reranking.BATCH]
                      for i in range(0, len(row['pool']), reranking.BATCH)]:
            client.call(stage='замер задержки', query_id=row['query_id'],
                        provider='zai', model='glm-5.3-flash',
                        system_blocks=[reranking.INSTRUCTION],
                        user_text=reranking.user_text(
                            row['text'], [corpus[pid] for pid in chunk]),
                        schema=reranking.SCHEMA, max_tokens=3000, timeout=300,
                        estimated_usd=0.02)
        times.append((time.perf_counter() - started) * 1000)
    result['S3_glm-flash'] = stats(times)
    result['S3_glm-flash']['note'] = (
        'весь пул запроса, %d пачек в среднем, строго последовательно'
        % round(sum(len(row['pool']) for row in pool[:sample])
                / max(sample, 1) / reranking.BATCH, 1))

    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print('Задержка на одиночном запросе, мс:')
    for name, row in result.items():
        print('   %-14s p50 %8.1f  p95 %8.1f  (n=%d) %s'
              % (name, row['p50'], row['p95'], row['n'], row.get('note', '')))
    print('Потрачено на замер: $%.4f' % (
        client.costs['by_stage'].get('замер задержки', {})
        .get('glm-5.3-flash', {}).get('usd', 0.0)))


if __name__ == '__main__':
    main()
