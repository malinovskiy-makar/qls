# -*- coding: utf-8 -*-
"""Сколько видимых задач получат кнопку «Построить в «Графиках»» (ТОЛЬКО ЧТЕНИЕ).

    manage.py calc2_link_coverage

Обязательный шаг выкатки кнопки (решение владельца 10.10.2026, ADR 0145):
запустить на dev.weconomics.ai; кнопку выкатываем при покрытии от 10 %.
Считает по тем же правилам, что и страница задачи (`catalog/calc2_link.py`),
по видимым задачам каталога (`filters.base_queryset('catalog')`). В базу не
пишет ничего.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from catalog import calc2_link, filters
from problems.models import Problem, Tag

# Порог выкатки из решения владельца: меньше, и кнопку не выкатываем.
ROLLOUT_MIN_PCT = 10


class Command(BaseCommand):
    help = 'Покрытие кнопки «Построить в «Графиках»» по видимым задачам (только чтение).'

    def handle(self, *args, **options):
        ids = list(filters.base_queryset('catalog').values_list('id', flat=True))
        tags = defaultdict(list)
        for pid, name in (Problem.tags.through.objects
                          .filter(problem_id__in=ids, tag__kind='canonical')
                          .values_list('problem_id', 'tag__name')):
            tags[pid].append(name)
        topics = defaultdict(list)
        for pid, name in (Problem.topics.through.objects
                          .filter(problem_id__in=ids, topic__is_canonical=True)
                          .values_list('problem_id', 'topic__name')):
            topics[pid].append(name)
        c = calc2_link.coverage(ids, tags, topics)
        canonical = set(Tag.objects.filter(kind='canonical').values_list('name', flat=True))
        missing = [name for name in calc2_link.TAG_TO_MODEL if name not in canonical]

        pct = 100.0 * c['with_button'] / c['visible'] if c['visible'] else 0.0
        w = self.stdout.write
        w('Видимых задач: %d' % c['visible'])
        w('С каноническим тегом: %d' % c['with_tag'])
        w('С сопоставленным тегом: %d' % c['mapped_tag'])
        w('Кнопка по запасному пути темы: %d' % c['by_topic'])
        w('Теги есть, модели нет (кнопки нет): %d' % c['tagged_no_button'])
        w('С кнопкой: %d (%.1f %%)' % (c['with_button'], pct))
        w('С двумя моделями: %d' % c['two_models'])
        w('Модель первой кнопки:')
        for key, n in c['first'].most_common():
            w('  %-14s %6d  %s' % (key, n, calc2_link.MODEL_NAMES[key]))
        w('Все показанные модели (первая и «Или:»):')
        for key, n in c['shown'].most_common():
            w('  %-14s %6d' % (key, n))
        w('Строк таблицы тегов нет среди канонических тегов базы: %d' % len(missing))
        for name in missing:
            w('  %s' % name)
        verdict = 'выкатываем' if pct >= ROLLOUT_MIN_PCT else 'НЕ выкатываем'
        w('Порог выкатки %d %%: %s.' % (ROLLOUT_MIN_PCT, verdict))
