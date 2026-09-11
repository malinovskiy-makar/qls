"""Фаза 3: считалка — из ручной разметки в таблицу по 16 формулам.

Вход: pool.json (Фаза 1, кто на каком месте у какой формулы) + JSON разметки
владельца (список {query_id, problem_id, verdict}, verdict ∈
{good, unsure, bad}).

РАБОТАЕТ НА НЕПОЛНОЙ РАЗМЕТКЕ: запрос попадает в счёт, только если размечены
ВСЕ задачи его пула (иначе precision@10 отдельной формулы мог бы опираться на
непомеченную карточку). Не полностью размеченные запросы перечисляются и
пропускаются, а не тянут метрику вниз нулями.

Метрики (годится=2, спорно=1, не годится=0):
  precision@10  — доля «годится» среди первых 10 у формулы (то, что владелец
                  видит на экране за раз).
  precision@5   — то же по первым 5.
  nDCG@10       — по градуированной шкале; идеальный порядок (IDCG@10) берёт
                  топ-10 ПО ВСЕМУ размеченному пулу запроса (не только из
                  выдачи формулы) — так nDCG не занижен нехваткой разметки.
  mean_rank_first_good — средний ранг первой «годится» в топ-10; если такой
                  нет вовсе — используется censoring-конвенция «11»
                  (условно «сразу за пределами показанных десяти»).

Плюс бутстрап по запросам (10 000 итераций) — 95% доверительный интервал
разницы «формула минус v2_meta_first» (то, что стоит в банке сейчас) для
каждой метрики.

Запуск:
    venv313/Scripts/python.exe reports/formula_choice/score.py razmetka.json
"""
import json
import math
import random
import sys
from pathlib import Path

BASELINE = 'vec_v2_meta_first'
VERDICT_SCORE = {'good': 2, 'unsure': 1, 'bad': 0}


def load_markup(path):
    with open(path, encoding='utf-8') as fh:
        rows = json.load(fh)
    verdicts = {}  # (query_id, problem_id) -> verdict
    for r in rows:
        verdicts[(r['query_id'], int(r['problem_id']))] = r['verdict']
    return verdicts


def complete_queries(pool, verdicts):
    """query_id -> True, если ВСЕ задачи пула этого запроса размечены."""
    complete = {}
    for qid, merged in pool['pool_per_query'].items():
        pool_ids = [int(pid) for pid in merged.keys()]
        complete[qid] = all((qid, pid) in verdicts for pid in pool_ids)
    return complete


#: Что считается «годной» для precision@k и ранга первой годной. nDCG@10
#: НЕ зависит от режима — она и так градуирована (годится=2, спорно=1,
#: не годится=0), это ровно тот компромисс, ради которого шкала градуирована.
GOOD_SETS = {
    'strict': {'good'},             # годной считается только «годится»
    'soft': {'good', 'unsure'},     # годной считается «годится» и «спорно»
}


def query_metrics(pool, qid, verdicts, formulas, mode='strict'):
    """{formula: {precision10, precision5, ndcg10, rank_first_good}} для
    ОДНОГО (полностью размеченного) запроса.

    `mode` ('strict'|'soft') решает, что считать «годной» для precision@k и
    ранга первой годной — nDCG@10 от режима не зависит (см. GOOD_SETS)."""
    merged = pool['pool_per_query'][qid]  # {pid: {formula: {rank, score}}}
    good_set = GOOD_SETS[mode]

    all_graded = [VERDICT_SCORE[verdicts[(qid, int(pid))]] for pid in merged.keys()]
    ideal_top10 = sorted(all_graded, reverse=True)[:10]
    idcg10 = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_top10))

    out = {}
    for name in formulas:
        # top10 этой формулы для запроса, в её собственном порядке ранга.
        ranked = [
            (int(pid), info[name]['rank'])
            for pid, info in merged.items() if name in info
        ]
        ranked.sort(key=lambda t: t[1])  # по рангу 1..10
        top10 = [pid for pid, _ in ranked]
        assert len(top10) == 10, f'{qid}/{name}: в пуле {len(top10)} мест топ-10, а не 10'

        graded = [VERDICT_SCORE[verdicts[(qid, pid)]] for pid in top10]
        is_good = [verdicts[(qid, pid)] in good_set for pid in top10]

        precision10 = sum(is_good) / 10.0
        precision5 = sum(is_good[:5]) / 5.0
        dcg10 = sum(rel / math.log2(i + 2) for i, rel in enumerate(graded))
        ndcg10 = (dcg10 / idcg10) if idcg10 > 0 else 0.0

        rank_first_good = next((i + 1 for i, g in enumerate(is_good) if g), 11)

        out[name] = {
            'precision10': precision10,
            'precision5': precision5,
            'ndcg10': ndcg10,
            'rank_first_good': rank_first_good,
        }
    return out


def aggregate(per_query, formulas, query_ids):
    """Среднее по запросам query_ids для каждой формулы/метрики."""
    metrics = ['precision10', 'precision5', 'ndcg10', 'rank_first_good']
    agg = {name: {m: 0.0 for m in metrics} for name in formulas}
    n = len(query_ids)
    if n == 0:
        return agg
    for qid in query_ids:
        for name in formulas:
            for m in metrics:
                agg[name][m] += per_query[qid][name][m]
    for name in formulas:
        for m in metrics:
            agg[name][m] /= n
    return agg


def bootstrap_ci(per_query, formulas, query_ids, iters=10000, seed=20260909):
    """95% ДИ разницы (формула − BASELINE) по каждой метрике, ресэмплинг
    запросов с возвращением."""
    metrics = ['precision10', 'precision5', 'ndcg10', 'rank_first_good']
    rnd = random.Random(seed)
    n = len(query_ids)
    diffs = {name: {m: [] for m in metrics} for name in formulas if name != BASELINE}

    for _ in range(iters):
        sample = [query_ids[rnd.randrange(n)] for _ in range(n)]
        base_means = {m: sum(per_query[q][BASELINE][m] for q in sample) / n for m in metrics}
        for name in diffs:
            for m in metrics:
                formula_mean = sum(per_query[q][name][m] for q in sample) / n
                diffs[name][m].append(formula_mean - base_means[m])

    ci = {name: {} for name in diffs}
    for name in diffs:
        for m in metrics:
            vals = sorted(diffs[name][m])
            lo = vals[int(0.025 * iters)]
            hi = vals[int(0.975 * iters) - 1]
            ci[name][m] = (lo, hi)
    return ci


def run(pool, verdicts, verbose=True, mode='strict', query_filter=None):
    """query_filter: необязательный список/множество query_id — если задан,
    используются только они (должны быть полностью размечены); остальные
    полностью размеченные запросы в счёт не идут. Нужно для замера на
    подмножестве запросов (Фаза «без q02/q07/q10»)."""
    formulas = pool['formulas']
    complete = complete_queries(pool, verdicts)
    complete_ids = [qid for qid, ok in complete.items() if ok]
    incomplete_ids = [qid for qid, ok in complete.items() if not ok]

    if query_filter is not None:
        missing = set(query_filter) - set(complete_ids)
        if missing:
            raise ValueError(f'query_filter просит запросы, которых нет среди '
                              f'полностью размеченных: {sorted(missing)}')
        complete_ids = [qid for qid in complete_ids if qid in set(query_filter)]

    if verbose:
        print(f'Запросов размечено полностью: {len(complete)} из {len(pool["queries"])}'
              + (f', в счёт взято {len(complete_ids)}' if query_filter is not None else ''))
        if incomplete_ids:
            print('Пропущены (разметка неполная):', ', '.join(sorted(incomplete_ids)))
        if not complete_ids:
            print('Ни одного полностью размеченного запроса — считать нечего.')
            return None

    per_query = {
        qid: query_metrics(pool, qid, verdicts, formulas, mode=mode)
        for qid in complete_ids
    }
    agg = aggregate(per_query, formulas, complete_ids)
    ci = bootstrap_ci(per_query, formulas, complete_ids) if len(complete_ids) >= 2 else None

    if verbose:
        _print_table(agg, ci, formulas)
    return {'aggregate': agg, 'ci': ci, 'complete_queries': complete_ids,
            'incomplete_queries': incomplete_ids, 'per_query': per_query, 'mode': mode}


def _print_table(agg, ci, formulas):
    print()
    header = f'{"формула":28s} {"prec@10":>8s} {"prec@5":>8s} {"nDCG@10":>8s} {"ранг1й":>7s}'
    print(header)
    print('-' * len(header))
    for name in formulas:
        a = agg[name]
        marker = ' *baseline*' if name == BASELINE else ''
        print(f'{name:28s} {a["precision10"]:8.3f} {a["precision5"]:8.3f} '
              f'{a["ndcg10"]:8.3f} {a["rank_first_good"]:7.2f}{marker}')
    if ci:
        print()
        print(f'95% ДИ разницы (формула − {BASELINE}), бутстрап по запросам, 10000 итераций:')
        for name in formulas:
            if name == BASELINE:
                continue
            lo, hi = ci[name]['precision10']
            sign = '' if lo <= 0 <= hi else ('значимо ЛУЧШЕ' if lo > 0 else 'значимо ХУЖЕ')
            print(f'  {name:28s} prec@10: [{lo:+.3f}, {hi:+.3f}]  {sign}')


def main():
    if len(sys.argv) < 2:
        print('Использование: score.py <разметка.json> [pool.json]')
        sys.exit(1)
    markup_path = sys.argv[1]
    pool_path = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).resolve().parent / 'pool.json')

    with open(pool_path, encoding='utf-8') as fh:
        pool = json.load(fh)
    verdicts = load_markup(markup_path)
    run(pool, verdicts)


if __name__ == '__main__':
    main()
