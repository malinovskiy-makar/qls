# -*- coding: utf-8 -*-
"""Фаза 1: пул кандидатов на все запросы эталона. ТОЛЬКО ЧТЕНИЕ базы.

Три ноги без модели-посредника:
  S0 dense  — плотный поиск по активной формуле отпечатка (v2_focus_repeat);
  S1 bm25   — лексика: pymorphy3 + bm25s (catalog/lexical_bm25.py);
  S2 rrf    — слияние S0 и S1 по рангам, k = 60.

Нога S_concept (разбор запроса моделью) добавляется отдельно, когда
появится ключ OpenRouter, — см. `run_concept.py`.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_pool.py

Промежуточные файлы кэшируются: повторный запуск не пересобирает индекс и
не перекодирует запросы.
"""
import csv
import json
import os
import re
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

import numpy as np  # noqa: E402

import poolbuild  # noqa: E402
from catalog import lexical_bm25 as lex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, 'corpus.jsonl')
INDEX_DIR = os.path.join(HERE, 'bm25_index')
QUERIES = os.path.join(HERE, 'queries.json')
QTYPES = os.path.join(HERE, 'query_types.csv')
POOL = os.path.join(HERE, 'pool.jsonl')
TIMING = os.path.join(HERE, 'timing.json')

TOP_K = 30


def norm_text(text):
    text = text.lower().replace('ё', 'е')
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text)).strip()


# ─── Запросы ──────────────────────────────────────────────────────────────

def build_queries():
    """61 различная формулировка: C58 — подмножество C65, объединение = C65.

    Проверено в фазе −1 сверкой по нормализованному тексту. Считать их за
    119 значило бы дать 58 формулировкам двойной вес во всех метриках.
    """
    with open('problems/data/eval_set_c_v3.json', encoding='utf-8') as f:
        c65 = json.load(f)['cases']
    with open('problems/data/eval_set_c.json', encoding='utf-8') as f:
        c58 = {norm_text(c['query']) for c in json.load(f)['cases']}
    with open('reports/formula_choice/pool.json', encoding='utf-8') as f:
        manual = {norm_text(q['text']): q['query_id'] for q in json.load(f)['queries']}

    queries = []
    for i, case in enumerate(c65, 1):
        key = norm_text(case['query'])
        queries.append({
            'query_id': 'q%02d' % i,
            'text': case['query'],
            'anchor': (case.get('relevant_ids') or [None])[0],
            'in_c58': key in c58,
            'manual_id': manual.get(key),
            'type': poolbuild.query_type(case['query']),
        })
    with open(QUERIES, 'w', encoding='utf-8') as f:
        json.dump(queries, f, ensure_ascii=False, indent=1)
    with open(QTYPES, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['query_id', 'тип', 'ручная разметка', 'запрос'])
        for q in queries:
            writer.writerow([q['query_id'], q['type'], q['manual_id'] or '',
                             q['text']])
    return queries


# ─── Корпус ───────────────────────────────────────────────────────────────

def build_corpus():
    """Видимые поиску задачи с полями отпечатка. База только читается."""
    if os.path.exists(CORPUS):
        with open(CORPUS, encoding='utf-8') as f:
            return [json.loads(line) for line in f]

    from catalog.semantic import index_queryset
    from problems.models import Problem, ProblemPart

    ids = list(index_queryset('prod').values_list('id', flat=True))
    id_set = set(ids)

    parts = {}
    for pid, statement in ProblemPart.objects.filter(
            problem_id__in=id_set).order_by('problem_id', 'order').values_list(
            'problem_id', 'statement').iterator(chunk_size=5000):
        if statement:
            parts.setdefault(pid, []).append(statement)

    rows = []
    qs = (Problem.objects.filter(id__in=id_set)
          .prefetch_related('topics', 'tags', 'econ_concepts')
          .only('id', 'title', 'title_candidate', 'statement', 'find', 'given',
                'problem_type', 'difficulty', 'dup_group', 'dup_is_best'))
    for p in qs.iterator(chunk_size=500):
        rows.append({
            'id': p.id,
            'title': p.title_candidate or p.title or '',
            'statement': p.statement or '',
            'parts': parts.get(p.id, []),
            'find': p.find or '',
            'given': p.given or '',
            'problem_type': p.problem_type or '',
            'difficulty': p.difficulty,
            'topics': [t.name for t in p.topics.all() if t.is_canonical],
            'tags': [t.name for t in p.tags.all() if t.kind == 'canonical'],
            'concepts': [c.canonical for c in p.econ_concepts.all()],
            'dup_group': p.dup_group or None,
            'dup_is_best': bool(p.dup_is_best),
        })
    with open(CORPUS, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    return rows


# ─── Ноги ─────────────────────────────────────────────────────────────────

def bm25_index(rows, timing):
    if os.path.exists(os.path.join(INDEX_DIR, 'ids.json')):
        started = time.perf_counter()
        index = lex.load_index(INDEX_DIR)
        timing['bm25_load_s'] = round(time.perf_counter() - started, 2)
        return index
    started = time.perf_counter()
    index = lex.build_index([r['id'] for r in rows],
                            [lex.index_text(r) for r in rows])
    timing['bm25_build_s'] = round(time.perf_counter() - started, 2)
    lex.save_index(index, INDEX_DIR)
    return index


def dense_runs(queries, timing):
    """Топ-30 плотного поиска. Матрица — из банка, запросы кодируются локально."""
    cache = os.path.join(HERE, 'dense.json')
    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            return json.load(f)

    from problems.management.commands.search_eval import (
        построить_индекс, _кодировщик_модели)
    from problems.embedding_config import EMBEDDING_MAX_SEQ_LENGTH

    started = time.perf_counter()
    matrix, ids = построить_индекс('prod')
    timing['dense_index_s'] = round(time.perf_counter() - started, 2)
    timing['dense_index_rows'] = len(ids)

    from search_service.app import get_model
    get_model().max_seq_length = EMBEDDING_MAX_SEQ_LENGTH
    encode = _кодировщик_модели()

    started = time.perf_counter()
    vectors = encode([q['text'] for q in queries])
    timing['encode_queries_s'] = round(time.perf_counter() - started, 2)
    vectors = vectors / np.where(
        np.linalg.norm(vectors, axis=1, keepdims=True) == 0, 1e-9,
        np.linalg.norm(vectors, axis=1, keepdims=True))

    runs = {}
    started = time.perf_counter()
    for q, vec in zip(queries, vectors):
        scores = matrix @ vec
        top = np.argsort(-scores)[:TOP_K]
        runs[q['query_id']] = [[int(ids[i]), float(scores[i])] for i in top]
    timing['dense_search_total_s'] = round(time.perf_counter() - started, 3)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(runs, f, ensure_ascii=False)
    return runs


def main():
    timing = {}
    queries = build_queries()
    print('Запросов: %d (короткие %d, описательные %d, с ручной разметкой %d)'
          % (len(queries),
             sum(1 for q in queries if q['type'] == 'короткий'),
             sum(1 for q in queries if q['type'] == 'описательный'),
             sum(1 for q in queries if q['manual_id'])))

    rows = build_corpus()
    print('Корпус (видимо поиску): %d задач' % len(rows))
    groups = {r['id']: (r['dup_group'], r['dup_is_best']) for r in rows}
    visible = {r['id'] for r in rows}

    index = bm25_index(rows, timing)
    started = time.perf_counter()
    bm25 = {q['query_id']: lex.search(index, q['text'], TOP_K) for q in queries}
    timing['bm25_search_total_s'] = round(time.perf_counter() - started, 3)
    timing['bm25_search_per_query_ms'] = round(
        timing['bm25_search_total_s'] * 1000 / max(len(queries), 1), 2)

    dense = dense_runs(queries, timing)

    pool_rows, stats = [], {'anchor_in_pool': 0, 'sizes': [], 'dropped': 0}
    for q in queries:
        qid = q['query_id']
        s0 = [int(pid) for pid, _ in dense[qid]]
        s1 = [int(pid) for pid, _ in bm25[qid]]
        s2 = poolbuild.rrf_merge({'dense': s0, 'bm25': s1})[:TOP_K]

        order, seen = [], set()
        for pid in s0 + s1 + s2:
            if pid not in seen:
                seen.add(pid)
                order.append(pid)
        kept, dropped = poolbuild.collapse_dedup(order, groups)
        poolbuild.check_pool(qid, kept, visible, groups)

        provenance = {}
        for name, ranked in (('S0_dense', s0), ('S1_bm25', s1), ('S2_rrf', s2)):
            for rank, pid in enumerate(ranked):
                provenance.setdefault(pid, {})[name] = rank + 1

        stats['sizes'].append(len(kept))
        stats['dropped'] += len(dropped)
        if q['anchor'] in kept:
            stats['anchor_in_pool'] += 1
        pool_rows.append({
            'query_id': qid, 'text': q['text'], 'type': q['type'],
            'anchor': q['anchor'], 'anchor_in_pool': q['anchor'] in kept,
            'manual_id': q['manual_id'],
            'pool': kept,
            'sources': {str(pid): provenance.get(pid, {}) for pid in kept},
            'runs': {'S0_dense': s0, 'S1_bm25': s1, 'S2_rrf': s2},
            'dropped_dups': dropped,
        })

    with open(POOL, 'w', encoding='utf-8') as f:
        for row in pool_rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    sizes = stats['sizes']
    timing['pool'] = {
        'queries': len(queries),
        'size_min': min(sizes), 'size_max': max(sizes),
        'size_mean': round(sum(sizes) / len(sizes), 1),
        'anchor_in_pool': stats['anchor_in_pool'],
        'anchor_in_pool_share': round(stats['anchor_in_pool'] / len(sizes), 3),
        'dropped_dups': stats['dropped'],
    }
    with open(TIMING, 'w', encoding='utf-8') as f:
        json.dump(timing, f, ensure_ascii=False, indent=1)
    print(json.dumps(timing, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
