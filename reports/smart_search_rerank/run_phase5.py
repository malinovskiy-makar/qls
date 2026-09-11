# -*- coding: utf-8 -*-
"""Фаза 5: метрики сортировщика для трёх составов пула — только dense,
только bm25, оба. На тех же 91 запросах и готовых метках из
reports/llm_search_eval/, метод счёта — reports/llm_search_eval/metrics.py
(зафиксирован 10.09.2026), без единого нового вызова модели.

Как это устроено без новых денег: `rerank_glm-flash.jsonl` — уже готовый
ответ сортировщика на ПОЛНЫЙ (dense+bm25, дедуп) пул каждого запроса
(reports/llm_search_eval/, замер 10.09.2026). `pool.jsonl` хранит, откуда
взят каждый кандидат пула — сырые списки dense (`S0_dense`) и bm25
(`S1_bm25`) ДО объединения. «Только dense» — это порядок сортировщика,
отфильтрованный до кандидатов dense-ноги; «только bm25» — то же для
bm25-ноги; «оба» — полный порядок как есть. Сортировщик не перезывается:
это подмножество уже посчитанных оценок, а не гипотетический новый вызов.

⚠️ ОГОВОРКА МЕТОДА: сортировщик при замере 10.09 видел ПОЛНЫЙ пул (обе
ноги сразу) и оценивал кандидата в этом контексте. «Только dense»/«только
bm25» здесь — это ЕГО ЖЕ оценки, но подмножество, а не гипотетический
рескоринг в изоляции: если бы сортировщик видел только 50 кандидатов
одной ноги, баллы могли бы немного отличаться. Это стандартный и честный
способ прикинуть состав без нового прогона, но не то же самое, что живой
замер с изолированным пулом.

Запуск:
    venv313\\Scripts\\python.exe reports/smart_search_rerank/run_phase5.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.join(HERE, '..', 'llm_search_eval')
sys.path.insert(0, EVAL_DIR)
sys.path.insert(0, os.getcwd())

import judging  # noqa: E402
import metrics as M  # noqa: E402

POOL_PATH = os.path.join(EVAL_DIR, 'pool.jsonl')


def project(ranked, pool_ids, replacement):
    out, seen = [], set()
    for pid in ranked:
        target = pid if pid in pool_ids else replacement.get(pid)
        if target is None or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def read_rerank(name):
    path = os.path.join(EVAL_DIR, 'rerank_%s.jsonl' % name)
    out = {}
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            out[row['query_id']] = row['ranked']
    return out


def load_labels(rule):
    labels = {}
    path = os.path.join(EVAL_DIR, 'labels_final.jsonl')
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            value = (row['label'] if row['source'] == 'владелец'
                     else row['labels'][rule])
            labels.setdefault(row['query_id'], {})[row['problem_id']] = value
    return labels


def mean(values):
    return round(sum(values) / len(values), 3) if values else None


def measure(rows_ranked, labels, pool):
    """rows_ranked: {query_id: ranked_ids}."""
    out = {'запросов': 0, 'p5': [], 'ndcg10': [], 'three': [], 'labelled10': []}
    for row in pool:
        qid = row['query_id']
        ranked = rows_ranked.get(qid)
        if not ranked:
            continue
        marks = labels.get(qid, {})
        out['запросов'] += 1
        out['p5'].append(M.precision_at_k(ranked, marks, 5))
        out['ndcg10'].append(M.ndcg_at_k(ranked, marks, 10))
        out['three'].append(M.has_n_good(ranked, marks, 3, 5))
        out['labelled10'].append(M.labelled_share(ranked, marks, 10))
    return out


def main():
    pool = [json.loads(line) for line in open(POOL_PATH, encoding='utf-8')]
    agreement = json.load(open(os.path.join(EVAL_DIR, 'agreement.json'),
                               encoding='utf-8'))
    primary = agreement['primary']
    labels = load_labels(primary)
    raw_rerank = read_rerank('glm-flash')

    dense_only, bm25_only, both = {}, {}, {}
    pool_sizes = {'dense': [], 'bm25': [], 'both': []}
    for row in pool:
        qid = row['query_id']
        pool_ids = set(row['pool'])
        replacement = {d['id']: d['kept'] for d in row['dropped_dups']}
        dense_ids = set(project(row['runs'].get('S0_dense', []), pool_ids,
                                replacement))
        bm25_ids = set(project(row['runs'].get('S1_bm25', []), pool_ids,
                               replacement))
        full_ranked = project(raw_rerank.get(qid, []), pool_ids, replacement)
        if not full_ranked:
            continue
        dense_only[qid] = [pid for pid in full_ranked if pid in dense_ids]
        bm25_only[qid] = [pid for pid in full_ranked if pid in bm25_ids]
        both[qid] = full_ranked
        pool_sizes['dense'].append(len(dense_ids))
        pool_sizes['bm25'].append(len(bm25_ids))
        pool_sizes['both'].append(len(pool_ids))

    # Задержка «только bm25» — реальный прогон Фазы 4 (тот же код сайта).
    phase4_summary_path = os.path.join(HERE, 'phase4_summary.json')
    bm25_latency = None
    if os.path.exists(phase4_summary_path):
        with open(phase4_summary_path, encoding='utf-8') as handle:
            p4 = json.load(handle)
        bm25_latency = 'p50 %.1fс / p95 %.1fс (живой прогон Фазы 4)' % (
            p4['total_seconds_p50'], p4['total_seconds_p95'])

    latency_path = os.path.join(EVAL_DIR, 'latency.json')
    both_latency = None
    if os.path.exists(latency_path):
        with open(latency_path, encoding='utf-8') as handle:
            lat = json.load(handle)
        row = lat.get('S3_glm-flash')
        if row:
            both_latency = 'p50 %.0fмс / p95 %.0fмс (замер 10.09, dense+bm25)' % (
                row['p50'], row['p95'])

    results = {}
    for label, rows_ranked, sizes, latency in (
            ('только dense', dense_only, pool_sizes['dense'], None),
            ('только bm25', bm25_only, pool_sizes['bm25'], bm25_latency),
            ('оба', both, pool_sizes['both'], both_latency)):
        got = measure(rows_ranked, labels, pool)
        results[label] = {
            'запросов': got['запросов'],
            'размер_пула_среднее': round(sum(sizes) / len(sizes), 1) if sizes else 0,
            'P@5': mean(got['p5']),
            'nDCG@10': mean(got['ndcg10']),
            '>=3 годных в топ-5': ('%.0f%%' % (100 * mean(got['three']))
                                   if got['three'] else '—'),
            'доля размеченных в топ-10': ('%.0f%%' % (100 * mean(got['labelled10']))
                                          if got['labelled10'] else '—'),
            'задержка': latency or 'нет живого замера (нужен Docker/search_service)',
        }

    with open(os.path.join(HERE, 'phase5_results.json'), 'w',
             encoding='utf-8') as handle:
        json.dump(results, handle, ensure_ascii=False, indent=1)
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
