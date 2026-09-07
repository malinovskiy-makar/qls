# -*- coding: utf-8 -*-
"""rebuild_feature_view — пересобрать витрину каталога `Problem.features`
из связи `ProblemFeature`.

⚠️ ВИТРИНА СВОЕГО ФАКТА НЕ ХРАНИТ. Три ключа `graph`/`table`/`proof`, которые
читают фильтры каталога, — это производное от двенадцати настоящих
особенностей по правилу `problems/enrich/features.py::CATALOG_VIEW_MAP`.
Команда нужна на два случая: правило показа поменяли (тогда витрину надо
пересобрать всю) и витрина разошлась со связью (тогда это чинится здесь, а
не правкой JSON руками).

Идемпотентна: повторный запуск обязан дать ноль изменений — это же
проверяет `problems/tests/test_enrich_features.py`.

    manage.py rebuild_feature_view            # сухой прогон
    manage.py rebuild_feature_view --apply    # запись
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.enrich import features as feat
from problems.models import Problem, ProblemFeature

BATCH = 1000


class Command(BaseCommand):
    help = 'Пересобрать Problem.features из связи ProblemFeature.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Записать. Без флага — только числа.')

    def handle(self, *args, **options):
        keys_by_problem = defaultdict(set)
        for pid, key in ProblemFeature.objects.values_list(
                'problem_id', 'feature__key'):
            keys_by_problem[pid].add(key)

        changed, checked = [], 0
        for problem in Problem.objects.only('id', 'features').iterator(
                chunk_size=BATCH):
            checked += 1
            want = sorted(feat.catalog_view(keys_by_problem.get(problem.id, ())))
            if sorted(problem.features or []) != want:
                problem.features = want
                changed.append(problem)

        self.stdout.write('задач просмотрено: %d' % checked)
        self.stdout.write('витрина расходится со связью у: %d' % len(changed))
        if not options['apply']:
            self.stdout.write('--dry-run: ничего не записано.')
            return

        with transaction.atomic():
            for start in range(0, len(changed), BATCH):
                Problem.objects.bulk_update(
                    changed[start:start + BATCH], ['features'])
        self.stdout.write('витрина обновлена у %d задач' % len(changed))
