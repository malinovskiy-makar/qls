# -*- coding: utf-8 -*-
"""Предварительные метрики трёх ног на ручной разметке владельца.

Считает то, что уже можно посчитать без единого вызова модели: S0 dense,
S1 bm25 и S2 rrf на десяти запросах, размеченных владельцем вручную.
Ни одного обращения к базе и к сети.

⚠️ Числа неполные и такими называются. Ручная разметка снята с ДРУГОГО
пула (топ-10 шестнадцати формул отпечатка, срез «весь банк»), поэтому
часть кандидатов наших ног в ней просто отсутствует. Доля размеченных
печатается рядом с каждой метрикой — без неё эти числа читать нельзя.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import metrics  # noqa: E402

SCALE = {'good': 2, 'unsure': 1, 'bad': 0}


def load():
    pool = [json.loads(line) for line in
            open(os.path.join(HERE, 'pool.jsonl'), encoding='utf-8')]
    with open('reports/formula_choice/razmetka_336.json', encoding='utf-8') as f:
        raw = json.load(f)
    labels = {}
    for row in raw:
        labels.setdefault(row['query_id'], {})[row['problem_id']] = \
            SCALE[row['verdict']]
    return pool, labels


def main():
    pool, manual = load()
    rows = [r for r in pool if r['manual_id']]
    systems = ('S0_dense', 'S1_bm25', 'S2_rrf')
    out = {s: {'p5': [], 'p10': [], 'ndcg10': [], 'three_good': [],
               'cov5': [], 'cov10': [], 'p10_labelled': []} for s in systems}

    per_query = []
    for row in rows:
        labels = manual[row['manual_id']]
        line = {'query_id': row['query_id'], 'manual_id': row['manual_id'],
                'text': row['text'], 'labelled_total': len(labels)}
        for system in systems:
            ranked = row['runs'][system]
            out[system]['p5'].append(metrics.precision_at_k(ranked, labels, 5))
            out[system]['p10'].append(metrics.precision_at_k(ranked, labels, 10))
            out[system]['ndcg10'].append(metrics.ndcg_at_k(ranked, labels, 10))
            out[system]['three_good'].append(
                metrics.has_n_good(ranked, labels, 3, 5))
            out[system]['cov5'].append(metrics.labelled_share(ranked, labels, 5))
            out[system]['cov10'].append(
                metrics.labelled_share(ranked, labels, 10))
            upper = metrics.precision_among_labelled(ranked, labels, 10)
            if upper is not None:
                out[system]['p10_labelled'].append(upper)
            line[system] = {
                'p5': round(out[system]['p5'][-1], 3),
                'ndcg10': round(out[system]['ndcg10'][-1], 3),
                'cov10': round(out[system]['cov10'][-1], 2),
            }
        per_query.append(line)

    def mean(values):
        return round(sum(values) / len(values), 3) if values else 0.0

    summary = {s: {k: mean(v) for k, v in d.items()} for s, d in out.items()}
    for s in systems:
        summary[s]['three_good'] = round(
            sum(out[s]['three_good']) / len(out[s]['three_good']), 3)

    report = {'queries': len(rows), 'summary': summary, 'per_query': per_query}
    with open(os.path.join(HERE, 'metrics_pre.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    head = (f"{'система':<10}{'P@5':>8}{'P@10':>8}{'P@10 верх':>11}"
            f"{'nDCG@10':>10}{'≥3 годных':>12}{'разметка@10':>13}")
    print(f'Десять запросов с ручной разметкой владельца ({len(rows)} шт.)\n')
    print(head)
    print('-' * len(head))
    for s in systems:
        d = summary[s]
        print(f"{s:<10}{d['p5']:>8.3f}{d['p10']:>8.3f}"
              f"{d['p10_labelled']:>11.3f}{d['ndcg10']:>10.3f}"
              f"{d['three_good']:>12.1%}{d['cov10']:>13.0%}")


if __name__ == '__main__':
    main()
