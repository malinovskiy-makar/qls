# -*- coding: utf-8 -*-
"""Откуда взялось 0,852 вчера и 0,623 сегодня. Разложение 2×2.

Вчерашняя считалка (`reports/formula_choice/score.py`) и сегодняшняя
(`metrics.py`) считают nDCG@10 по РАЗНЫМ определениям и по РАЗНЫМ наборам
кандидатов. Пока обе цифры называются одним словом «nDCG@10», сравнивать
их нельзя. Скрипт меняет по одному знаку за раз и печатает вклад каждого.

Две оси:
  набор кандидатов — вчерашний пул (весь банк 41 307, без дедупа) против
      сегодняшнего S0 (видимые поиску, дедуп схлопнут);
  определение метрики — вчерашнее (прирост линейный, идеал по меткам
      пула) против сегодняшнего (прирост 2^метка − 1, идеал по всем
      меткам запроса).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SCALE = {'good': 2, 'unsure': 1, 'bad': 0}
FORMULA = 'vec_v2_focus_repeat'


def ndcg_yesterday(ranked, labels, pool_ids, k=10):
    """Определение score.py: прирост = метка, идеал по меткам ПУЛА."""
    graded = [labels.get(pid, 0) for pid in ranked[:k]]
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(graded))
    ideal = sorted((labels[pid] for pid in pool_ids if pid in labels),
                   reverse=True)[:k]
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def ndcg_today(ranked, labels, k=10):
    """Определение metrics.py: прирост = 2^метка − 1, идеал по всем меткам."""
    graded = [2 ** labels.get(pid, 0) - 1 for pid in ranked[:k]]
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(graded))
    ideal = sorted((2 ** rel - 1 for rel in labels.values()), reverse=True)[:k]
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main():
    with open('reports/formula_choice/razmetka_336.json', encoding='utf-8') as f:
        raw = json.load(f)
    labels = {}
    for row in raw:
        labels.setdefault(row['query_id'], {})[row['problem_id']] = \
            SCALE[row['verdict']]

    with open('reports/formula_choice/pool.json', encoding='utf-8') as f:
        old = json.load(f)
    old_top10, old_pool = {}, {}
    for qid, members in old['pool_per_query'].items():
        ranked = [(int(pid), info[FORMULA]['rank'])
                  for pid, info in members.items() if FORMULA in info]
        ranked.sort(key=lambda pair: pair[1])
        old_top10[qid] = [pid for pid, _ in ranked]
        old_pool[qid] = [int(pid) for pid in members]

    new = [json.loads(line) for line in
           open(os.path.join(HERE, 'pool.jsonl'), encoding='utf-8')]
    new_top10 = {r['manual_id']: r['runs']['S0_dense'][:10]
                 for r in new if r['manual_id']}

    cells, coverage = {}, {}
    for set_name, tops in (('вчерашний пул', old_top10),
                           ('сегодняшний S0', new_top10)):
        for rule_name, rule in (('вчерашняя метрика', 'old'),
                                ('сегодняшняя метрика', 'new')):
            values = []
            for qid, ranked in tops.items():
                if rule == 'old':
                    values.append(ndcg_yesterday(ranked, labels[qid],
                                                 old_pool[qid]))
                else:
                    values.append(ndcg_today(ranked, labels[qid]))
            cells[(set_name, rule_name)] = sum(values) / len(values)
        covered = []
        for qid, ranked in tops.items():
            known = sum(1 for pid in ranked[:10] if pid in labels[qid])
            covered.append(known / max(len(ranked[:10]), 1))
        coverage[set_name] = sum(covered) / len(covered)

    print('nDCG@10 на десяти запросах с ручной разметкой, формула '
          'v2_focus_repeat\n')
    head = f"{'набор кандидатов':<20}{'вчерашняя метрика':>20}{'сегодняшняя':>16}{'размечено':>12}"
    print(head)
    print('-' * len(head))
    for set_name in ('вчерашний пул', 'сегодняшний S0'):
        print(f'{set_name:<20}'
              f'{cells[(set_name, "вчерашняя метрика")]:>20.3f}'
              f'{cells[(set_name, "сегодняшняя метрика")]:>16.3f}'
              f'{coverage[set_name]:>12.0%}')

    a = cells[('вчерашний пул', 'вчерашняя метрика')]
    b = cells[('вчерашний пул', 'сегодняшняя метрика')]
    c = cells[('сегодняшний S0', 'вчерашняя метрика')]
    d = cells[('сегодняшний S0', 'сегодняшняя метрика')]
    print('\nВклад слагаемых:')
    print('  смена определения метрики при том же наборе: %+.3f' % (b - a))
    print('  смена набора кандидатов при той же метрике:  %+.3f' % (c - a))
    print('  обе разом:                                   %+.3f' % (d - a))

    json.dump({'cells': {'%s / %s' % k: round(v, 4) for k, v in cells.items()},
               'coverage': {k: round(v, 4) for k, v in coverage.items()}},
              open(os.path.join(HERE, 'gap_explained.json'), 'w',
                   encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
