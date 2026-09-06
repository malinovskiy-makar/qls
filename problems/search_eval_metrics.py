# -*- coding: utf-8 -*-
"""С14, Уровень 0 — метрики измерителя поиска.

Здесь нет ни Django, ни модели, ни базы: на вход приходит готовый список id
в порядке выдачи, на выходе — числа. Оторванность намеренная. Ядро замера
обязано проверяться на игрушечных наборах, где правильный ответ виден глазом;
если бы для этого требовалось поднять базу и загрузить 2 ГБ модели, проверки
писались бы «потом» и не написались бы никогда.

Релевантность бинарная: id либо правильный, либо нет. Градаций
relevant/acceptable/irrelevant пока нет — их даст разметка владельца по
топ-20 (команда `search_eval_markup`), и вот тогда nDCG станет считаться по
градациям. До тех пор честнее считать по факту «единственный известный
правильный ответ», чем изображать разметку, которой не делали.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """Один запрос эталонного набора.

    query        — текст, который вводит человек;
    relevant_ids — id задач, считающихся правильным ответом. Для наборов B и C
                   это ровно один id; для набора A — все дубли исходной задачи.
    meta         — что угодно для отчёта (источник строки, тема), в метрики
                   не входит.
    """

    query: str
    relevant_ids: frozenset[int]
    meta: dict = field(default_factory=dict, compare=False)

    def __init__(self, query, relevant_ids, meta=None):
        object.__setattr__(self, 'query', query)
        object.__setattr__(self, 'relevant_ids', frozenset(relevant_ids))
        object.__setattr__(self, 'meta', meta or {})


def recall_at_k(ranked_ids, relevant_ids, k) -> float:
    """Доля правильных ответов, попавших в первые k позиций выдачи.

    ⚠️ ПУСТОЙ ЭТАЛОН — ОШИБКА, А НЕ НОЛЬ. Вернуть 0.0 значило бы записать
    такой запрос в промахи поиска, хотя искать было нечего: средний recall
    поехал бы вниз по вине набора, а чинили бы поиск.
    """
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError('Пустой набор правильных ответов: recall не определён.')
    if not ranked_ids:
        return 0.0
    найдено = relevant & set(ranked_ids[:k])
    return len(найдено) / len(relevant)


def mrr_at_k(ranked_ids, relevant_ids, k) -> float:
    """Обратный ранг ПЕРВОГО правильного ответа: 1/позиция, 0 — если его нет.

    Осмысленна там, где правильный ответ ровно один (наборы B и C). Для
    набора A, где дублей может быть несколько, число считается, но читать
    его надо как «как быстро нашёлся хоть один дубль».
    """
    relevant = set(relevant_ids)
    for позиция, pid in enumerate(ranked_ids[:k], start=1):
        if pid in relevant:
            return 1.0 / позиция
    return 0.0


def ndcg_at_k(ranked_ids, relevant_ids, k) -> float:
    """nDCG@k при бинарной релевантности: DCG выдачи, делённый на идеальный.

    Идеальный порядок — все правильные ответы подряд с первой позиции, но не
    больше k штук: если правильных 80, а k=10, потолок всё равно десять.
    """
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError('Пустой набор правильных ответов: nDCG не определён.')
    dcg = sum(
        1.0 / math.log2(позиция + 1)
        for позиция, pid in enumerate(ranked_ids[:k], start=1)
        if pid in relevant
    )
    idcg = sum(
        1.0 / math.log2(позиция + 1)
        for позиция in range(1, min(len(relevant), k) + 1)
    )
    return dcg / idcg if idcg else 0.0


def evaluate_case(case: EvalCase, ranked_ids, index_ids, ks) -> dict:
    """Все метрики по одному запросу плюс признак физической недостижимости.

    ⚠️ «НЕТ В ИНДЕКСЕ ВОВСЕ» — ОТДЕЛЬНАЯ КАТЕГОРИЯ, А НЕ НУЛЕВОЙ RECALL.
    Если правильной задачи нет в индексе (у неё нет эмбеддинга, она скрыта
    или забракована), поиск не мог её вернуть никаким улучшением формулы.
    Смешав это с промахом, мы стали бы улучшать ранжирование там, где чинить
    надо корпус. Запрос считается недостижимым, только когда НИ ОДИН из его
    правильных ответов не лежит в индексе.
    """
    достижимые = case.relevant_ids & set(index_ids)
    return {
        'query': case.query,
        'relevant_ids': sorted(case.relevant_ids),
        'unreachable': not достижимые,
        'recall': {k: recall_at_k(ranked_ids, case.relevant_ids, k) for k in ks},
        'mrr_10': mrr_at_k(ranked_ids, case.relevant_ids, 10),
        'ndcg_10': ndcg_at_k(ranked_ids, case.relevant_ids, 10),
        'first_hit_rank': _first_hit_rank(ranked_ids, case.relevant_ids),
        'meta': case.meta,
    }


def _first_hit_rank(ranked_ids, relevant_ids):
    """Позиция первого правильного ответа во всей выдаче, None — если нет."""
    relevant = set(relevant_ids)
    for позиция, pid in enumerate(ranked_ids, start=1):
        if pid in relevant:
            return позиция
    return None


def aggregate(results, ks) -> dict:
    """Свод по набору: средние метрики и главное число программы.

    Главное число — разрыв `recall@50 − recall@5`. Оно и есть точный потолок
    того, что способен дать реранкер: разрыв мал — реранкер не окупит
    задержку; разрыв велик — нужное поиск находит, но плохо расставляет.
    """
    n = len(results)
    if not n:
        return {
            'queries': 0,
            'recall': {k: 0.0 for k in ks},
            'mrr_10': 0.0,
            'ndcg_10': 0.0,
            'gap_50_5': 0.0,
            'unreachable_share': 0.0,
            'unreachable_count': 0,
        }
    recall = {k: sum(r['recall'][k] for r in results) / n for k in ks}
    недостижимых = sum(1 for r in results if r['unreachable'])
    return {
        'queries': n,
        'recall': recall,
        'mrr_10': sum(r['mrr_10'] for r in results) / n,
        'ndcg_10': sum(r['ndcg_10'] for r in results) / n,
        'gap_50_5': (recall.get(50, 0.0) - recall.get(5, 0.0)),
        'unreachable_share': недостижимых / n,
        'unreachable_count': недостижимых,
    }
