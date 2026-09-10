# -*- coding: utf-8 -*-
"""Фаза 3: метрики всех систем по итоговым меткам. Базу не трогает.

Один способ счёта на всю сессию (зафиксирован 10.09.2026):
  прирост nDCG — 2^метка − 1, идеал по ВСЕМ меткам запроса;
  неразмеченный кандидат считается негодным;
  precision делится на число ПОКАЗАННЫХ, а не на k.

Разрезы: все запросы, описательные, короткие, отдельно 10 запросов с
ручной разметкой владельца. Плюс строки чувствительности по трём
правилам слияния меток судей.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_metrics.py
"""
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.getcwd())

import judging  # noqa: E402
import metrics as M  # noqa: E402

POOL = os.path.join(HERE, 'pool.jsonl')
SCALE = {'good': 2, 'unsure': 1, 'bad': 0}

#: система → как получить её порядок для запроса
SYSTEMS = ['S0_dense', 'S1_bm25', 'S2_rrf', 'S_concept',
           'S3_glm-flash', 'S3_glm', 'S3_haiku', 'S4_sonnet']


def read_rerank(name):
    path = os.path.join(HERE, 'rerank_%s.jsonl' % name)
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            out[row['query_id']] = row['ranked']
    return out


def load_labels(rule):
    """Итоговые метки по правилу: ручная разметка владельца сильнее."""
    labels = {}
    path = os.path.join(HERE, 'labels_final.jsonl')
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            value = (row['label'] if row['source'] == 'владелец'
                     else row['labels'][rule])
            labels.setdefault(row['query_id'], {})[row['problem_id']] = value
    return labels


def project(ranked, pool_ids, replacement):
    """Выдачу — на пул: дубль заменяется фаворитом своей группы.

    ⚠️ БЕЗ ЭТОГО СРАВНЕНИЕ НЕЧЕСТНОЕ. Ноги ищут по всему множеству и
    находят в том числе задачи, которые из пула убраны как дубли: в пуле
    остался ровно один представитель группы. Оставить дубль в выдаче
    значит поставить системе ноль за то, что она нашла ту же задачу
    другой копией, — а копию никто не размечал. Поэтому дубль
    подменяется представителем, порядок сохраняется, повтор снимается.

    Кандидат, которого нет ни в пуле, ни среди убранных дублей, из
    выдачи исчезает: он вне размеченного множества, и судить о нём
    нечем.
    """
    out, seen = [], set()
    for pid in ranked:
        target = pid if pid in pool_ids else replacement.get(pid)
        if target is None or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def runs_for(pool):
    runs = {name: {} for name in SYSTEMS}
    pools = {r['query_id']: set(r['pool']) for r in pool}
    replacement = {r['query_id']: {d['id']: d['kept'] for d in r['dropped_dups']}
                   for r in pool}
    for row in pool:
        qid = row['query_id']
        for name in ('S0_dense', 'S1_bm25', 'S2_rrf', 'S_concept'):
            runs[name][qid] = project(row['runs'].get(name, []), pools[qid],
                                      replacement[qid])
    for short, name in (('glm-flash', 'S3_glm-flash'), ('glm', 'S3_glm'),
                        ('haiku', 'S3_haiku'), ('sonnet', 'S4_sonnet')):
        raw = read_rerank(short)
        runs[name] = {qid: project(ranked, pools[qid], replacement[qid])
                      for qid, ranked in raw.items()}
    return runs


def measure(runs, labels, pool, subset):
    """Метрики одной системы на подмножестве запросов."""
    rows = [r for r in pool if r['query_id'] in subset]
    out = {'запросов': 0, 'p5': [], 'p10': [], 'ndcg10': [], 'three': [],
           'anchor5': [], 'нет выдачи': []}
    for row in rows:
        qid = row['query_id']
        ranked = runs.get(qid)
        if not ranked:
            out['нет выдачи'].append(qid)
            continue
        marks = labels.get(qid, {})
        out['запросов'] += 1
        out['p5'].append(M.precision_at_k(ranked, marks, 5))
        out['p10'].append(M.precision_at_k(ranked, marks, 10))
        out['ndcg10'].append(M.ndcg_at_k(ranked, marks, 10))
        out['three'].append(M.has_n_good(ranked, marks, 3, 5))
        if row['anchor'] is not None:
            out['anchor5'].append(1.0 if row['anchor'] in ranked[:5] else 0.0)
    return out


def mean(values):
    return round(sum(values) / len(values), 3) if values else None


def check_invariants(runs, pool):
    """Топ-10 каждой системы обязан лежать внутри пула запроса."""
    problems = []
    pools = {r['query_id']: set(r['pool']) for r in pool}
    for name, by_query in runs.items():
        for qid, ranked in by_query.items():
            outside = [pid for pid in ranked[:10] if pid not in pools[qid]]
            if outside:
                problems.append('%s/%s: вне пула %s' % (name, qid, outside[:3]))
    return problems


def local_latency(pool):
    """Задержка бесплатных ног, замеряется честно и заново."""
    from catalog import lexical_bm25 as lex
    index = lex.load_index(os.path.join(HERE, 'bm25_index'))
    times = []
    for row in pool:
        started = time.perf_counter()
        lex.search(index, row['text'], 50)
        times.append((time.perf_counter() - started) * 1000)
    return times


def main():
    pool = [json.loads(line) for line in open(POOL, encoding='utf-8')]
    runs = runs_for(pool)
    labels_by_rule = {rule: load_labels(rule) for rule in judging.MERGE_RULES}
    agreement = json.load(open(os.path.join(HERE, 'agreement.json'),
                               encoding='utf-8'))
    primary = agreement['primary']

    subsets = {
        'все': {r['query_id'] for r in pool},
        'описательные': {r['query_id'] for r in pool
                         if r['type'] == 'описательный'},
        'короткие': {r['query_id'] for r in pool if r['type'] == 'короткий'},
        'только 10 ручных': {r['query_id'] for r in pool if r['manual_id']},
    }

    costs = json.load(open(os.path.join(HERE, 'costs.json'), encoding='utf-8'))
    stage_cost = {}
    for stage, models in costs['by_stage'].items():
        for model, data in models.items():
            stage_cost[stage] = stage_cost.get(stage, 0.0) + data['usd']

    lines = ['# Метрики офлайн-замера LLM-слоя над поиском', '',
             'Запросов %d, пар в пулах %d, множество поиска 26 914 задач, '
             'формула отпечатка `v2_focus_repeat` версии 95.'
             % (len(pool), sum(len(r['pool']) for r in pool)), '',
             'Правило слияния меток судей — **%s** (согласие с владельцем '
             'по границе годности %s).' % (
                 primary,
                 '%.0f %%' % (100 * agreement['report'][
                     'правило «%s»' % primary]['годится / не годится'])), '']

    labels = labels_by_rule[primary]
    problems = check_invariants(runs, pool)
    lines.append('Инвариант «топ-10 внутри пула»: %s'
                 % ('нарушений нет' if not problems
                    else 'НАРУШЕН, %d случаев' % len(problems)))
    lines.append('')

    for subset_name, subset in subsets.items():
        lines += ['## %s (%d запросов)' % (subset_name, len(subset)), '',
                  '| система | P@5 | P@10 | nDCG@10 | ≥3 годных в топ-5 | '
                  'recall@5 по якорю | запросов |', '|---|---|---|---|---|---|---|']
        for name in SYSTEMS:
            if not runs.get(name):
                continue
            got = measure(runs[name], labels, pool, subset)
            if not got['запросов']:
                continue
            lines.append('| %s | %s | %s | %s | %s | %s | %d |' % (
                name, mean(got['p5']), mean(got['p10']), mean(got['ndcg10']),
                ('%.0f %%' % (100 * mean(got['three']))
                 if got['three'] else '—'),
                mean(got['anchor5']) if got['anchor5'] else '—',
                got['запросов']))
        lines.append('')

    # ── контроль: только метки владельца, без машинных ────────────────
    owner = {}
    with open(os.path.join(HERE, 'labels_final.jsonl'), encoding='utf-8') as h:
        for line in h:
            if not line.strip():
                continue
            row = json.loads(line)
            if row['source'] == 'владелец':
                owner.setdefault(row['query_id'], {})[row['problem_id']] =                     row['label']
    lines += ['## Контроль: только пары, размеченные владельцем', '',
              'Из выдачи каждой системы убрано всё, чего владелец не видел. '
              'Машинных меток здесь нет вовсе: это проверка на то, что выигрыш '
              'реранкера не создан судьями, которые сами модели.', '',
              '| система | P@5 | nDCG@10 | пар в счёте |',
              '|---|---|---|---|']
    for name in SYSTEMS:
        if not runs.get(name):
            continue
        p5, nd, pairs = [], [], 0
        for row in pool:
            qid = row['query_id']
            marks = owner.get(qid)
            if not marks or qid not in runs[name]:
                continue
            ranked = [pid for pid in runs[name][qid] if pid in marks]
            if not ranked:
                continue
            p5.append(M.precision_at_k(ranked, marks, 5))
            nd.append(M.ndcg_at_k(ranked, marks, 10))
            pairs += len(ranked)
        if p5:
            lines.append('| %s | %s | %s | %d |'
                         % (name, mean(p5), mean(nd), pairs))
    lines.append('')

    # ── чувствительность к правилу слияния ─────────────────────────────
    lines += ['## Чувствительность: те же системы при других правилах', '',
              '| система | %s |' % ' | '.join(
                  'nDCG@10 «%s»' % r for r in judging.MERGE_RULES),
              '|---|%s' % ('---|' * len(judging.MERGE_RULES))]
    for name in SYSTEMS:
        if not runs.get(name):
            continue
        cells = []
        for rule in judging.MERGE_RULES:
            got = measure(runs[name], labels_by_rule[rule], pool, subsets['все'])
            cells.append(str(mean(got['ndcg10'])))
        lines.append('| %s | %s |' % (name, ' | '.join(cells)))
    lines.append('')

    # ── деньги и задержка ──────────────────────────────────────────────
    bm25_times = local_latency(pool)
    lines += ['## Задержка и деньги', '',
              '| этап | стоимость, $ | на запрос, $ |', '|---|---|---|']
    for stage, usd in sorted(stage_cost.items()):
        lines.append('| %s | %.4f | %.5f |' % (stage, usd, usd / len(pool)))
    lines.append('| **итого** | **%.4f** | **%.5f** |'
                 % (costs['total_usd'], costs['total_usd'] / len(pool)))
    lines += ['', 'Лексическая нога, замер на 91 запросе: p50 %.1f мс, '
                  'p95 %.1f мс.' % (statistics.median(bm25_times),
                                    sorted(bm25_times)[int(len(bm25_times) * .95)]),
              '']

    # ── доля пар с одним судьёй ────────────────────────────────────────
    stats = agreement['stats']
    single = stats.get('single_judge', 0)
    total = stats.get('меток в итоге', 1)
    lines += ['## Полнота разметки', '',
              '- пар с двумя судьями: %d' % stats.get('две метки', 0),
              '- пар с одним судьёй (`single_judge`): %d (%.1f %%)'
              % (single, 100.0 * single / total),
              '- пар без единой метки: %d' % stats.get('без единой метки', 0),
              '- разногласий судей: %d' % stats.get('разногласий', 0), '']

    with open(os.path.join(HERE, 'metrics.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
