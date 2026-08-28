# -*- coding: utf-8 -*-
"""Проверка после применения фикс-пака МатЭк: взять случайные N задач из
745 и сверить, что состояние в базе ДОСЛОВНО совпадает с тем, что просил
человек в matek_fixed.json.

Только чтение. Сверяются:
* поля задачи, которые пакет менял — с `after` соответствующей правки;
* структура подпунктов (ярлыки и условия) — с финальным `parts` пакета.

Поля, которых пакет не касался, намеренно НЕ сверяются: пакет по ним не
источник правды (у задач без правки ответа там лежит пустая строка, а не
«ответ должен стать пустым»)."""
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem

DEFAULT_PACK = os.path.join(
    os.path.dirname(settings.BASE_DIR), 'weconomics-data',
    'matek_fixed_20260826', 'matek_fixed.json',
)
PROBLEM_FIELDS = {
    'Условие': 'statement',
    'Ответ': 'answer',
    'Решение': 'solution',
    'Тип задачи': 'problem_type',
    'title': 'title',
}


class Command(BaseCommand):
    help = 'Сверить случайные N задач из фикс-пака МатЭк с состоянием в базе (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--pack', default=DEFAULT_PACK)
        parser.add_argument('--sample', type=int, default=15)
        parser.add_argument('--seed', type=int, default=20260827)

    def handle(self, *args, **options):
        with open(options['pack'], encoding='utf-8') as f:
            entries = json.load(f)['problems']
        random.seed(options['seed'])
        sample = random.sample(entries, min(options['sample'], len(entries)))

        checks = mismatches = 0
        problems_ok = 0
        for entry in sample:
            problem = (
                Problem.objects.filter(id=entry['problem_id'])
                .prefetch_related('parts').first()
            )
            if problem is None:
                self.stdout.write(self.style.ERROR(
                    f'#{entry["problem_id"]}: задачи нет в базе'))
                mismatches += 1
                continue

            problem_bad = []
            # 1. поля задачи, которые пакет менял
            for change in entry['changed']:
                attr = PROBLEM_FIELDS.get(change['field'])
                if attr is None:
                    continue
                checks += 1
                actual = getattr(problem, attr) or ''
                if actual != change['after']:
                    mismatches += 1
                    problem_bad.append(
                        f'поле {attr}: в базе {actual[:70]!r}, '
                        f'в пакете {change["after"][:70]!r}')

            # 2. структура подпунктов целиком
            checks += 1
            actual_parts = [
                (part.label, part.statement)
                for part in problem.parts.all().order_by('order', 'label')
            ]
            wanted_parts = [(p['label'], p['statement']) for p in entry['parts']]
            if sorted(actual_parts) != sorted(wanted_parts):
                mismatches += 1
                problem_bad.append(
                    f'подпункты: в базе {[l for l, _ in actual_parts]}, '
                    f'в пакете {[l for l, _ in wanted_parts]}')
                for (al, ast), (wl, wst) in zip(sorted(actual_parts), sorted(wanted_parts)):
                    if (al, ast) != (wl, wst):
                        problem_bad.append(
                            f'  «{al}» в базе {ast[:60]!r} vs «{wl}» в пакете {wst[:60]!r}')

            if problem_bad:
                self.stdout.write(self.style.ERROR(f'#{problem.id} — РАСХОЖДЕНИЕ:'))
                for line in problem_bad:
                    self.stdout.write(f'    {line}')
            else:
                problems_ok += 1
                self.stdout.write(
                    f'#{problem.id} — сошлось дословно '
                    f'(подпунктов {len(actual_parts)}, content_format={problem.content_format})'
                )

        self.stdout.write('')
        if mismatches:
            raise CommandError(
                f'Сверено задач: {len(sample)}, сошлось {problems_ok}. '
                f'Проверок {checks}, расхождений {mismatches}.'
            )
        self.stdout.write(self.style.SUCCESS(
            f'Все {len(sample)} задач сошлись дословно ({checks} проверок, 0 расхождений).'
        ))
