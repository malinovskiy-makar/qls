"""Фаза 0-1 линейки выбора формулы: десять запросов → пул для ручной разметки.

ТОЛЬКО ЧИТАЕТ. Банк не трогает, эмбеддинги не пересчитывает, ACTIVE_SPEC_NAME
не меняет. Срез индекса — 'all' (см. catalog.semantic.index_queryset):
banк целиком, а не то, что видно на сайте — иначе формулы мерились бы по
обрезанному 14-тысячами hidden_pending_review банку.

Запуск:
    venv313/Scripts/python.exe reports/formula_choice/build_pool.py
Пишет reports/formula_choice/pool.json.
"""
import json
import os
import sys
from collections import defaultdict

import django
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from problems.management.commands.search_eval import (  # noqa: E402
    построить_индекс, загрузить_файл_векторов,
)

FORMULAS = [
    'vec_v1', 'vec_v2', 'vec_v2_3000', 'vec_v2_nolimit', 'vec_v2_lean',
    'vec_v2_focus', 'vec_v2_focus_repeat', 'vec_v2_meta_first',
    'vec_v2_masked_numbers', 'vec_v2_no_solution', 'vec_v2_no_hints',
    'vec_v2_no_queries', 'vec_v2_no_offlist', 'vec_v2_no_code_features',
    'vec_v2_no_tail_meta', 'vec_v2_no_blurb',
]
PREFIX = 'reports/formula_v2/'
TOP_K = 10
SCOPE = 'all'

# Владелец отклонил июньскую пятёрку (сравнение с июнем не нужно) и попросил
# все десять запросов взять из наборов C58/C65 (владелец, живые формулировки),
# отбирая по разнообразию ТИПОВ (расчётные, верно-неверно, графические,
# табличные, доказательные) и ТЕМ (разные разделы — микро, макро, финансы,
# математический аппарат/прочее), не повторяя ни то ни другое между собой.
QUERIES = [
    {'query_id': 'q01', 'source': 'eval_set_c_v3#44', 'topic': 'сравнительное преимущество (верно/неверно)',
     'kind': 'верно_неверно, теоретическая', 'anchor': 5718,
     'text': 'простенькая данетка  на сравнительные преимущества'},
    {'query_id': 'q02', 'source': 'eval_set_c_v3#53', 'topic': 'межвременной выбор потребителя (график)',
     'kind': 'несколько_подвопросов, расчётная, feature=graph', 'anchor': 26652,
     'text': 'Стандартная задача на межвременной выбор потребителя, какие-то пункты с возможностью брать кредит и класть депозиты'},
    {'query_id': 'q03', 'source': 'eval_set_c_v3#42', 'topic': 'предложение фирмы на СК (таблица издержек)',
     'kind': 'несколько_подвопросов, расчётная, feature=table', 'anchor': 374,
     'text': 'простая задача на нахождение предложение в ск'},
    {'query_id': 'q04', 'source': 'eval_set_c_v3#61', 'topic': 'матчинг «один ко многим» (доказательство)',
     'kind': 'задача с развёрнутым ответом, теоретическая, feature=proof', 'anchor': 29649,
     'text': 'Задача на one-to-many мэтчинг'},
    {'query_id': 'q05', 'source': 'eval_set_c_v3#2', 'topic': 'неравенство доходов: Лоренц/Джини',
     'kind': 'несколько_подвопросов, расчётная', 'anchor': 29497,
     'text': 'нахождение и дальнейшее изменение кривой лоренца и коэффициента джинни'},
    {'query_id': 'q06', 'source': 'eval_set_c_v3#7', 'topic': 'рынок труда: фрикционная безработица',
     'kind': 'единственный_выбор, расчётная', 'anchor': 6981,
     'text': 'нахождение уровня занятости при изменении численности рабочей силы и безработных'},
    {'query_id': 'q07', 'source': 'eval_set_c_v3#46', 'topic': 'монетарная политика: депозитный мультипликатор',
     'kind': 'тест: короткий ответ, расчётная', 'anchor': 28052,
     'text': 'Стандартная задачка на монетарную политику: депозиты, норма резервирования, кредиты и тд'},
    {'query_id': 'q08', 'source': 'eval_set_c_v3#22', 'topic': 'фискальная политика: изменение ВВП',
     'kind': 'задача с развёрнутым ответом, расчётная', 'anchor': 28062,
     'text': 'задача по фискальной политике на изменение ввп'},
    {'query_id': 'q09', 'source': 'eval_set_c_v3#62', 'topic': 'переход СК → монополия (индекс Лернера)',
     'kind': 'задача с развёрнутым ответом, расчётная', 'anchor': 1928,
     'text': 'Продвинутая задача на переход от СК к монополии, возможно красиво через индекс Лернера'},
    {'query_id': 'q10', 'source': 'eval_set_c_v3#55', 'topic': 'финансы: цена бессрочной облигации',
     'kind': 'единственный_выбор, расчётная', 'anchor': 6640,
     'text': 'Расчет цены бессрочной облигации'},
]


def merge_pool_for_query(top10_by_formula, formulas):
    """ОБЪЕДИНЕНИЕ (не пересечение!) топ-10 всех формул для одного запроса.

    top10_by_formula: {formula_name: [(problem_id, score), ...10 штук...]}
    Возвращает {problem_id: {formula_name: {'rank': 1..10, 'score': ...}}} —
    задача попадает в пул, если её нашла ХОТЬ ОДНА формула. Тест
    test_pool_is_union_not_intersection (Фаза 4) ловит замену на `&`: тогда
    размер пула упал бы до общих для ВСЕХ 16 формул находок, обычно 0-1.
    """
    merged = defaultdict(dict)
    for name in formulas:
        for rank, (pid, score) in enumerate(top10_by_formula[name], start=1):
            merged[pid][name] = {'rank': rank, 'score': score}
    return dict(merged)


def main():
    from search_service.app import get_model
    model = get_model()

    query_texts = [q['text'] for q in QUERIES]
    print('Кодируем 10 запросов локально (CPU)...')
    raw = np.asarray(model.encode(query_texts, show_progress_bar=False), dtype=np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    query_vecs = raw / np.where(norms == 0, 1e-9, norms)

    # top10[query_id][formula] = [(problem_id, score), ...]  (10 штук, по убыванию)
    top10 = defaultdict(dict)
    index_sizes = {}

    for name in FORMULAS:
        print(f'Формула {name}...')
        матрица, место_в_файле, мета = загрузить_файл_векторов(PREFIX + name)
        matrix, ids = построить_индекс(SCOPE, (матрица, место_в_файле))
        index_sizes[name] = len(ids)
        ids_arr = np.array(ids)
        scores_all = matrix @ query_vecs.T  # (N_index, 10)
        for qi, q in enumerate(QUERIES):
            scores = scores_all[:, qi]
            top_idx = np.argpartition(scores, -TOP_K)[-TOP_K:]
            top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
            top10[q['query_id']][name] = [
                (int(ids_arr[i]), float(scores[i])) for i in top_idx
            ]

    print()
    print('Размер индекса "all" по каждому файлу (должно быть одинаково, 41307):')
    for name, n in index_sizes.items():
        print(f'  {name}: {n}')

    # ── Пул: объединение уникальных пар «запрос — задача» ──────────────
    pool_per_query = {
        q['query_id']: merge_pool_for_query(top10[q['query_id']], FORMULAS)
        for q in QUERIES
    }

    # ── Стоп-гейт: числа ────────────────────────────────────────────────
    sizes = {qid: len(merged) for qid, merged in pool_per_query.items()}
    all_pairs = sum(sizes.values())
    unique_problem_ids = set()
    for merged in pool_per_query.values():
        unique_problem_ids.update(merged.keys())

    overlap_buckets = {'1': 0, '2-5': 0, '6+': 0}
    for merged in pool_per_query.values():
        for pid, per_formula in merged.items():
            n_found = len(per_formula)
            if n_found == 1:
                overlap_buckets['1'] += 1
            elif n_found <= 5:
                overlap_buckets['2-5'] += 1
            else:
                overlap_buckets['6+'] += 1

    print()
    print('=== СТОП-ГЕЙТ ===')
    print('Уникальных задач в пуле (по всем 10 запросам, пары запрос-задача):', all_pairs)
    print('Уникальных ЗАДАЧ (id) во всём пуле, если задача встречается в нескольких запросах:',
          len(unique_problem_ids))
    print('По запросу (сколько уникальных задач нашли 16 формул вместе):')
    for qid, n in sizes.items():
        topic = next(q['topic'] for q in QUERIES if q['query_id'] == qid)
        print(f'  {qid} ({topic}): {n}')
    vals = sorted(sizes.values())
    n = len(vals)
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    print(f'  минимум={min(vals)} медиана={median} максимум={max(vals)}')
    print()
    print('Пересечение формул (доля пар запрос-задача, найденных N формулами):')
    for k, v in overlap_buckets.items():
        print(f'  {k} формул(а): {v} ({100 * v / all_pairs:.1f}%)')

    out = {
        'scope': SCOPE,
        'top_k': TOP_K,
        'formulas': FORMULAS,
        'queries': QUERIES,
        'index_sizes': index_sizes,
        'pool_per_query': {
            qid: {str(pid): per_formula for pid, per_formula in merged.items()}
            for qid, merged in pool_per_query.items()
        },
        'stopgate': {
            'pairs_total': all_pairs,
            'unique_problem_ids_total': len(unique_problem_ids),
            'per_query_sizes': sizes,
            'overlap_buckets': overlap_buckets,
        },
    }
    out_path = 'reports/formula_choice/pool.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print()
    print('Записано:', out_path)


if __name__ == '__main__':
    main()
