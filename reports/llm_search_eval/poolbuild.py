# -*- coding: utf-8 -*-
"""Чистая часть сборки пула: слияние ног, дедуп, тип запроса, инварианты.

Отделено от кода, ходящего в базу, намеренно: правила сборки пула — это
то, что легко испортить незаметно, и они должны проверяться без базы, без
модели и без сети.
"""

#: k слияния RRF. 60 — значение из статьи Cormack и то же, что стоит в
#: `catalog/hybrid.py`: две реализации RRF в одном проекте с разными k
#: давали бы несравнимые числа.
RRF_K = 60

#: Границы пула. Меньше 30 — сравнивать системы не на чем; больше 200 —
#: разметка пула перестаёт помещаться в бюджет.
POOL_MIN, POOL_MAX = 30, 200

#: Запрос короче этого числа слов и без глагола считается «коротким».
SHORT_WORDS = 4

_VERB_TAGS = ('VERB', 'INFN')

_MORPH = None


class PoolInvariantError(AssertionError):
    """Пул нарушил инвариант. Это остановка, а не предупреждение."""


def rrf_weight(rank):
    """Вес места в выдаче: 1/(k + позиция), позиция с нуля."""
    return 1.0 / (RRF_K + rank + 1)


def rrf_merge(runs):
    """Слить несколько ранжированных списков id по РАНГАМ.

    По рангам, а не по весам: косинус лежит в [0, 1], BM25 — в произвольных
    единицах, зависящих от длины корпуса. Любая попытка сложить их напрямую
    была бы подгонкой коэффициента на глаз — ровно то, чего решение от
    19.08 велело избегать до появления золотого набора.
    """
    score = {}
    for ranked in runs.values():
        for rank, pid in enumerate(ranked):
            score[pid] = score.get(pid, 0.0) + rrf_weight(rank)
    return sorted(score, key=lambda pid: (-score[pid], pid))


def collapse_dedup(ids, groups):
    """Оставить по одному представителю дедуп-группы.

    `groups`: {id: (группа, фаворит ли)}. Представитель — фаворит, а если
    фаворит в пул не попал (он может быть невидим поиску), то первый по
    порядку исходного списка, то есть лучший по рангу.

    Возвращает `(оставленные, убранные)`; у каждого убранного записано,
    из какой он группы и кто остался вместо него — иначе «в пуле нет пары
    из одной группы» превращается в необъяснимое исчезновение кандидата.
    """
    best = {}
    for pid in ids:
        group = groups.get(pid, (None, False))[0]
        if group is None:
            continue
        is_best = groups.get(pid, (None, False))[1]
        current = best.get(group)
        if current is None or (is_best and not groups[current][1]):
            best[group] = pid

    kept, dropped = [], []
    for pid in ids:
        group = groups.get(pid, (None, False))[0]
        if group is None or best[group] == pid:
            kept.append(pid)
        else:
            dropped.append({'id': pid, 'group': group, 'kept': best[group]})
    return kept, dropped


def _morph():
    global _MORPH
    if _MORPH is None:
        import pymorphy3
        _MORPH = pymorphy3.MorphAnalyzer()
    return _MORPH


def query_type(text):
    """«короткий» (≤4 слов и без глагола) либо «описательный».

    Эвристика владельца из задания. Глагол ищется разбором, а не по
    окончанию: «нахождение» и «найти» иначе попадали бы в одну корзину, а
    это разные запросы — первый называет тему, второй ставит задачу.
    Итог правится руками в `query_types.csv`, эвристика лишь заполняет.
    """
    words = [w for w in text.replace(' ', ' ').split() if any(c.isalpha() for c in w)]
    if len(words) > SHORT_WORDS:
        return 'описательный'
    for word in words:
        parsed = _morph().parse(word.strip('.,!?:;()«»"'))
        if parsed and any(tag in parsed[0].tag for tag in _VERB_TAGS):
            return 'описательный'
    return 'короткий'


def check_pool(query_id, pool, visible_ids, groups):
    """Инварианты пула одного запроса. Нарушение — исключение."""
    if len(pool) != len(set(pool)):
        raise PoolInvariantError(
            '%s: в пуле повторяются id (%d строк, %d различных)'
            % (query_id, len(pool), len(set(pool))))
    if not POOL_MIN <= len(pool) <= POOL_MAX:
        raise PoolInvariantError(
            '%s: пул размером %d вне границ %d…%d'
            % (query_id, len(pool), POOL_MIN, POOL_MAX))
    outside = [pid for pid in pool if pid not in visible_ids]
    if outside:
        raise PoolInvariantError(
            '%s: в пуле %d задач вне множества видимых поиску: %s'
            % (query_id, len(outside), outside[:5]))
    seen = {}
    for pid in pool:
        group = groups.get(pid, (None, False))[0]
        if group is None:
            continue
        if group in seen:
            raise PoolInvariantError(
                '%s: в пуле две задачи из дедуп-группы %s: %s и %s'
                % (query_id, group, seen[group], pid))
        seen[group] = pid
