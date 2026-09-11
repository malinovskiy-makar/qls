# -*- coding: utf-8 -*-
"""Закрытый словарь понятий: сопоставление и счёт пересечения.

⚠️ НЕЧЁТКОГО ПОИСКА ЗДЕСЬ НЕТ И БЫТЬ НЕ ДОЛЖНО. Словарь закрыт: 1 886
понятий, размеченных прогоном обогащения. «Похоже на понятие из словаря»
— это уже новое понятие, и заводить его решает владелец. Стоит завести
здесь сопоставление по расстоянию, и в пул начнут попадать задачи по
понятию, которого никто не утверждал, причём молча.
"""
import re

_SPACES = re.compile(r'\s+')

#: Понятие весит вдвое против тега: понятий 1 886 на 344 тега, и попадание
#: в понятие говорит о задаче заметно больше. Число из задания сессии.
CONCEPT_WEIGHT = 2
TAG_WEIGHT = 1


def normalize(name):
    """Регистр и «ё» — не различие. Всё остальное различие."""
    return _SPACES.sub(' ', (name or '').lower().replace('ё', 'е')).strip()


def build_dictionary(canonical_names):
    """{нормализованное имя: каноническое} — точка входа сопоставления."""
    return {normalize(name): name for name in canonical_names if name}


def match(free_names, dictionary):
    """Список от модели → (найденные канонические, несловарные).

    Порядок сохраняется, повторы схлопываются: одно понятие, названное
    дважды, не должно удваивать вес задачи в счёте пересечения.
    """
    found, offlist, seen = [], [], set()
    for raw in free_names or []:
        key = normalize(raw)
        if not key:
            continue
        canonical = dictionary.get(key)
        if canonical is None:
            if raw not in offlist:
                offlist.append(raw)
            continue
        if canonical not in seen:
            seen.add(canonical)
            found.append(canonical)
    return found, offlist


def overlap_score(query_concepts, query_tags, problem_concepts, problem_tags):
    """Счёт кандидата: совпавшие понятия × 2 + совпавшие теги."""
    concepts_hit = len(set(query_concepts) & set(problem_concepts))
    tags_hit = len(set(query_tags) & set(problem_tags))
    return concepts_hit * CONCEPT_WEIGHT + tags_hit * TAG_WEIGHT
