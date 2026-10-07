"""Чтение банка для отбора экзамена. ТОЛЬКО ЧТЕНИЕ, в базу ни строки.

Основа — `catalog.filters.base_queryset('catalog')`: свой «признак
видимости» не заводим (в проекте их и так четыре, см. CLAUDE.md).

Каждая задача превращается в простой словарь («запись») — дальше отбор
работает на чистых функциях `problems/ai_exam/sampling.py`, и тесты
проверяют его без хитростей.

⚠️ Картинки (`ProblemFigure`) не читаются вовсе: их байты — сотни мегабайт
на корпус. Задача с картинкой отсекается по маркеру `[[FIGURE:` в тексте.
⚠️ Связанные таблицы читаются подзапросом `problem__in=<queryset>`, а не
списком id: `id__in` с тысячами значений роняет SQLite.
"""
from django.db.models import Max

from catalog.filters import base_queryset
from problems.models import (
    AnswerSecondOpinion, Problem, ProblemPart, SourceReference, Topic,
)

_FIELDS = (
    'id', 'title', 'statement', 'answer', 'solution', 'problem_type',
    'difficulty', 'task_nature', 'answer_consistency', 'text_quality',
    'solution_needs_review', 'multiple_problems', 'dup_group', 'dup_is_best',
)


def load_topics():
    """id → {'id', 'name', 'order'} канонических тем."""
    return {t['id']: t for t in Topic.objects.filter(is_canonical=True)
            .values('id', 'name', 'order')}


def load_records():
    """Записи всех видимых в каталоге задач, по возрастанию id."""
    qs = base_queryset('catalog')
    records = {}
    for row in qs.values(*_FIELDS).order_by('id'):
        row.update(parts=[], topics=[], source='', source_id=None, opinion=None)
        records[row['id']] = row

    parts = (ProblemPart.objects.filter(problem__in=qs)
             .order_by('problem_id', 'order', 'label', 'id')
             .values('id', 'problem_id', 'label', 'statement', 'answer'))
    for part in parts:
        records[part.pop('problem_id')]['parts'].append(part)

    links = (Problem.topics.through.objects
             .filter(problem__in=qs, topic__is_canonical=True)
             .order_by('problem_id', 'topic_id')
             .values_list('problem_id', 'topic_id'))
    for problem_id, topic_id in links:
        records[problem_id]['topics'].append(topic_id)

    # Источник — первая по id привязка: у задачи их бывает несколько.
    refs = (SourceReference.objects.filter(problem__in=qs)
            .order_by('problem_id', 'id')
            .values_list('problem_id', 'source_id', 'source__name'))
    for problem_id, source_id, name in refs:
        record = records[problem_id]
        if record['source_id'] is None:
            record['source_id'] = source_id
            record['source'] = name or ''

    # Второе мнение — последнее по времени.
    opinions = (AnswerSecondOpinion.objects.filter(problem__in=qs)
                .order_by('problem_id', 'created_at', 'id')
                .values('problem_id', 'agrees', 'resolved', 'resolution'))
    for opinion in opinions:
        records[opinion.pop('problem_id')]['opinion'] = opinion

    return [records[pk] for pk in sorted(records)]


def bank_fingerprint():
    """(строк Problem, максимум updated_at) — до и после отбора они обязаны
    совпасть: сессия в базу не пишет."""
    return (Problem.objects.count(),
            Problem.objects.aggregate(m=Max('updated_at'))['m'])
