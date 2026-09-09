"""Отчёт по ручной разметке пула (336/336): все пункты сессии 09.09.2026 —
полная таблица, строгая/мягкая трактовка «спорно», подмножество без
q02/q07/q10, разбивка победителя и baseline по запросам.

ТОЛЬКО ЧИТАЕТ pool.json и razmetka_336.json. Формулу и ACTIVE_SPEC_NAME не
трогает — это замер, решение за владельцем.

Запуск:
    venv313/Scripts/python.exe reports/formula_choice/phase3_report.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402

HERE = Path(__file__).resolve().parent
EXCLUDE_FLAT_QUERIES = {'q02', 'q07', 'q10'}


def load():
    with open(HERE / 'pool.json', encoding='utf-8') as fh:
        pool = json.load(fh)
    verdicts = score.load_markup(HERE / 'razmetka_336.json')
    return pool, verdicts


def ranking_by_precision10(agg, formulas):
    return sorted(formulas, key=lambda f: -agg[f]['precision10'])


def print_ranking_table(agg, formulas, title):
    print(f'--- {title} ---')
    header = f'{"#":>2s} {"формула":28s} {"prec@10":>8s} {"prec@5":>8s} {"nDCG@10":>8s} {"ранг1й":>7s}'
    print(header)
    print('-' * len(header))
    ranking = ranking_by_precision10(agg, formulas)
    for i, name in enumerate(ranking, start=1):
        a = agg[name]
        marker = ' *baseline*' if name == score.BASELINE else ''
        print(f'{i:2d} {name:28s} {a["precision10"]:8.3f} {a["precision5"]:8.3f} '
              f'{a["ndcg10"]:8.3f} {a["rank_first_good"]:7.2f}{marker}')
    print()
    return ranking


def section1_full_table(pool, verdicts):
    print('=' * 70)
    print('1. Полная таблица, все 10 запросов, строгая трактовка (по умолчанию)')
    print('=' * 70)
    result = score.run(pool, verdicts, verbose=False, mode='strict')
    formulas = pool['formulas']
    ranking = print_ranking_table(result['aggregate'], formulas, 'строго (10 запросов)')

    ci = result['ci']
    print(f'95% ДИ разницы (формула − {score.BASELINE}) по precision@10, бутстрап 10000, запросов={len(result["complete_queries"])}:')
    for name in formulas:
        if name == score.BASELINE:
            continue
        lo, hi = ci[name]['precision10']
        sign = '' if lo <= 0 <= hi else ('значимо ЛУЧШЕ' if lo > 0 else 'значимо ХУЖЕ')
        print(f'  {name:28s} [{lo:+.3f}, {hi:+.3f}]  {sign}')
    print()
    return result, ranking


def section2_strict_vs_soft(pool, verdicts):
    print('=' * 70)
    print('2. Строго vs мягко (спорно = годится) — держится ли порядок')
    print('=' * 70)
    strict = score.run(pool, verdicts, verbose=False, mode='strict')
    soft = score.run(pool, verdicts, verbose=False, mode='soft')
    formulas = pool['formulas']

    ranking_strict = print_ranking_table(strict['aggregate'], formulas, 'строго')
    ranking_soft = print_ranking_table(soft['aggregate'], formulas, 'мягко')

    same = ranking_strict == ranking_soft
    same_top1 = ranking_strict[0] == ranking_soft[0]
    print(f'Порядок формул совпадает полностью: {same}')
    print(f'Лидер совпадает: {same_top1} '
          f'(строго: {ranking_strict[0]}, мягко: {ranking_soft[0]})')
    if not same:
        print('!!! Порядок разный — вывод держится на трактовке "спорно", а не только на данных.')
        print('    Строгий порядок:', ' > '.join(ranking_strict))
        print('    Мягкий порядок: ', ' > '.join(ranking_soft))
    print()
    return strict, soft, ranking_strict, ranking_soft


def section3_exclude_easy_queries(pool, verdicts, main_ranking):
    print('=' * 70)
    print('3. Без q02/q07/q10 (не различают формулы: q07=100% good, q10=82%, q02=80%)')
    print('=' * 70)
    all_qids = [q['query_id'] for q in pool['queries']]
    subset = [q for q in all_qids if q not in EXCLUDE_FLAT_QUERIES]
    print('Оставлено запросов:', ', '.join(subset))
    result = score.run(pool, verdicts, verbose=False, mode='strict', query_filter=subset)
    formulas = pool['formulas']
    ranking_subset = print_ranking_table(result['aggregate'], formulas, f'строго, {len(subset)} запросов')
    print(f'Победитель на 10 запросах: {main_ranking[0]}')
    print(f'Победитель на {len(subset)} запросах: {ranking_subset[0]}')
    print(f'Победитель меняется: {main_ranking[0] != ranking_subset[0]}')
    print()
    return result, ranking_subset


def section4_per_query_breakdown(pool, strict_result, winner, baseline):
    print('=' * 70)
    print(f'4. Разбивка по запросам: precision@10 для {winner!r} и {baseline!r}')
    print('=' * 70)
    per_query = strict_result['per_query']
    header = f'{"запрос":8s} {winner:>28s} {baseline:>28s} {"разница":>10s}'
    print(header)
    print('-' * len(header))
    diffs = []
    for qid in sorted(per_query.keys()):
        w = per_query[qid][winner]['precision10']
        b = per_query[qid][baseline]['precision10']
        diffs.append(w - b)
        print(f'{qid:8s} {w:28.3f} {b:28.3f} {w - b:+10.3f}')
    n_better = sum(1 for d in diffs if d > 0)
    n_worse = sum(1 for d in diffs if d < 0)
    n_equal = sum(1 for d in diffs if d == 0)
    print()
    print(f'{winner} лучше на {n_better} запросах, хуже на {n_worse}, равно на {n_equal} из {len(diffs)}.')
    if n_better <= 2 and n_better > 0:
        print('!!! Преимущество держится на 1-2 запросах — не обобщённый эффект.')
    print()


def main():
    pool, verdicts = load()
    formulas = pool['formulas']

    strict_main, ranking_main = section1_full_table(pool, verdicts)
    strict_again, soft_main, ranking_strict, ranking_soft = section2_strict_vs_soft(pool, verdicts)
    _, ranking_subset = section3_exclude_easy_queries(pool, verdicts, ranking_main)
    section4_per_query_breakdown(pool, strict_main, ranking_main[0], score.BASELINE)

    print('=' * 70)
    print('ИТОГ')
    print('=' * 70)
    print(f'Победитель (строго, 10 запросов): {ranking_main[0]}')
    print(f'Победитель (мягко, 10 запросов):  {ranking_soft[0]}')
    print(f'Победитель (строго, 7 запросов):  {ranking_subset[0]}')
    print(f'Baseline (в банке сейчас): {score.BASELINE}')

    # Сохраняем всё для последующей записи в Notion / отправки файлом.
    out = {
        'n_marked': len(verdicts),
        'ranking_10_strict': ranking_main,
        'ranking_10_soft': ranking_soft,
        'ranking_7_strict': ranking_subset,
        'agg_10_strict': strict_main['aggregate'],
        'agg_10_soft': soft_main['aggregate'],
        'ci_10_strict': {k: v for k, v in strict_main['ci'].items()},
    }
    out_path = HERE / 'phase3_result.json'
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print()
    print('Записано:', out_path)


if __name__ == '__main__':
    main()
