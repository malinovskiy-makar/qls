# -*- coding: utf-8 -*-
"""Диагностика корпуса (С13, Уровень 0 из docs/EMBEDDINGS.md).

Здесь живёт только то, что нельзя посчитать одним ORM-запросом: ретроспективное
устаревание векторов. Остальные диагностические числа считает команда
`corpus_diagnostics`.

⚠️ **Устаревание считается по ОТПЕЧАТКУ, а не по «текст поменялся».** Что
входит в `problem_to_text`, решает АКТИВНАЯ формула (`ACTIVE_SPEC`, с 09.09.2026
— `v2_focus_repeat`): условие и решение в пределах своих бюджетов, подпункты,
темы, теги, метаданные. Ответ НЕ входит. Поэтому фикс-пак, поправивший только
ответ, вектор не старит, правка решения старит, а правка условия за границей
обрезки не старит: до неё обрезка не доходит.

Наивное «правился текст → пересчитать» дало бы по фикс-паку МатЭк 719 задач
вместо реальных — то есть выписало бы счёт за работу, которой нет.
"""
import copy

from problems.management.commands.build_embeddings import (
    embedding_source_hash, problem_to_text,
)

# Ключ, под которым Django держит предвыбранные подпункты. Совпадает с
# related_name связи ProblemPart.problem.
_PARTS_CACHE_KEY = 'parts'


def _shadow(problem, overrides):
    """Копия задачи с подставленными СТАРЫМИ значениями — в память, не в базу.

    pk сохраняется: темы, навыки и теги остаются настоящими (фикс-паки их не
    трогали), а подменяются только те поля, что реально правили.

    Подпункты подставляются через `_prefetched_objects_cache` — тот же
    механизм, которым пользуется `prefetch_related`. Так `problem_to_text`
    вызывается НАСТОЯЩИЙ, а не переписанный здесь: копия формулы разошлась бы
    с оригиналом при первой же правке отпечатка.
    """
    shadow = copy.copy(problem)
    for field, value in overrides.items():
        if field != 'parts':
            setattr(shadow, field, value)

    part_overrides = overrides.get('parts') or {}
    parts = []
    for part in problem.parts.all():
        part = copy.copy(part)
        if part.pk in part_overrides:
            part.statement = part_overrides[part.pk]
        parts.append(part)
    shadow._prefetched_objects_cache = {_PARTS_CACHE_KEY: parts}
    return shadow


def fingerprint_changed(problem, overrides):
    """Изменился ли отпечаток задачи относительно варианта со старыми значениями.

    `overrides` — старые значения: {'statement': ..., 'title': ...,
    'parts': {part_pk: старый statement}}. Пустой словарь означает «правок не
    было» и всегда даёт False.
    """
    if not overrides:
        return False
    current = embedding_source_hash(problem_to_text(problem))
    previous = embedding_source_hash(problem_to_text(_shadow(problem, overrides)))
    return current != previous
