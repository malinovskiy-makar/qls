# -*- coding: utf-8 -*-
"""Фаза 4: 91 запрос замера через ТОТ ЖЕ КОД, что и вью (catalog/rerank.py),
не через скрипты замера. Запросы последовательно, пачки внутри запроса —
параллельно (это уже делает _score_pool сам).

⚠️ На этой машине Docker не поднят (search_service недоступен) — плотная
нога графически пуста (_dense_leg ловит исключение и возвращает []), пул
собирается только из bm25. Это конфигурация «прод без плотного поиска»,
она же — честный нижний предел задержки/стоимости.

Запуск:
    venv313\\Scripts\\python.exe reports/smart_search_rerank/run_phase4.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from catalog import rerank  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES_PATH = os.path.join(HERE, '..', 'llm_search_eval', 'queries.json')
OUT_PATH = os.path.join(HERE, 'phase4_results.jsonl')


def percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def main():
    with open(QUERIES_PATH, encoding='utf-8') as handle:
        queries = json.load(handle)

    rerank.clear_cache()

    rows = []
    with open(OUT_PATH, 'w', encoding='utf-8') as out:
        for i, q in enumerate(queries, 1):
            started = time.perf_counter()
            result = rerank.rerank(q['text'])
            wall = time.perf_counter() - started
            row = {
                'query_id': q['query_id'],
                'type': q['type'],
                'status': result.status,
                'reason': result.reason,
                'leg_sizes': result.leg_sizes,
                'batches': result.batches,
                'model_seconds': result.model_seconds,
                'total_seconds': result.total_seconds,
                'wall_seconds': round(wall, 3),
                'cost_usd': result.cost_usd,
            }
            rows.append(row)
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            out.flush()
            print('%d/%d %s %s %.2fs $%.5f' % (
                i, len(queries), q['query_id'], result.status,
                result.total_seconds, result.cost_usd))

    totals = [r['total_seconds'] for r in rows]
    models = [r['model_seconds'] for r in rows if r['status'] == 'rerank']
    costs = [r['cost_usd'] for r in rows]
    fallbacks = [r for r in rows if r['status'] != 'rerank']
    timeouts = [r for r in fallbacks if 'Timeout' in (r['reason'] or '')]

    summary = {
        'n': len(rows),
        'rerank_ok': len(rows) - len(fallbacks),
        'fallback': len(fallbacks),
        'timeout_fallback': len(timeouts),
        'fallback_reasons': sorted({r['reason'] for r in fallbacks}),
        'total_seconds_p50': round(percentile(totals, 0.50), 3),
        'total_seconds_p95': round(percentile(totals, 0.95), 3),
        'model_seconds_p50': round(percentile(models, 0.50), 3) if models else None,
        'model_seconds_p95': round(percentile(models, 0.95), 3) if models else None,
        'cost_usd_total': round(sum(costs), 5),
        'cost_usd_mean': round(sum(costs) / len(costs), 5) if costs else 0.0,
    }
    with open(os.path.join(HERE, 'phase4_summary.json'), 'w',
             encoding='utf-8') as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
