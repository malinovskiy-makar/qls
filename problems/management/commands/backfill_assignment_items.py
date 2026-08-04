"""
Бэкфилл позиций задач в домашках: старый M2M → `AssignmentItem`.

Зачем. Историческая домашка хранила задачи простым M2M `Assignment.problems`
без порядка и без обвязки. Платформа работает через ПОЗИЦИЮ (`AssignmentItem`):
на ней висят порядок, балл, комментарии, решалка, график. Пока позиций нет,
ученик и репетитор смотрят на разные списки — ровно тот баг, ради которого
команда и написана.

Идемпотентность. Позиция создаётся только для тех задач M2M, у которых её ещё
нет. Повторный запуск ничего не меняет и печатает нули. Существующие позиции
НЕ трогаются: у них может быть выставлен балл и написано решение.

Порядок. M2M порядка не хранит вовсе, поэтому берём единственный
воспроизводимый — по `Problem.id` (как и старая страница ученика, где стояло
`order_by('id')`). Новые позиции дописываются ПОСЛЕ уже существующих: если
репетитор успел собрать часть домашки в новом конструкторе, его порядок
главнее выдуманного нами.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = ('Создаёт AssignmentItem для задач, оставшихся только в старом '
            'M2M Assignment.problems. Идемпотентна.')

    def add_arguments(self, parser):
        parser.add_argument('--assignment-id', type=int, default=None,
                            help='Только одна домашка (для отладки).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только посчитать, ничего не писать.')

    def handle(self, *args, **options):
        from problems.models import Assignment, AssignmentItem

        queryset = Assignment.objects.all().prefetch_related('problems', 'items')
        if options['assignment_id']:
            queryset = queryset.filter(pk=options['assignment_id'])

        dry = options['dry_run']
        touched_assignments = 0
        created_total = 0

        with transaction.atomic():
            for assignment in queryset:
                existing = list(assignment.items.all())
                have = {i.catalog_problem_id for i in existing
                        if i.catalog_problem_id}
                # Следующий свободный порядок — после всех существующих.
                next_order = max([i.order for i in existing], default=-1) + 1

                missing = [p for p in assignment.problems.all().order_by('id')
                           if p.pk not in have]
                if not missing:
                    continue

                touched_assignments += 1
                created_total += len(missing)
                self.stdout.write(
                    f'  #{assignment.pk} «{assignment.name}»: '
                    f'+{len(missing)} позиц. (было {len(existing)})')

                if dry:
                    continue

                AssignmentItem.objects.bulk_create([
                    AssignmentItem(assignment=assignment, catalog_problem=p,
                                   order=next_order + n)
                    for n, p in enumerate(missing)
                ])

            if dry:
                transaction.set_rollback(True)

        prefix = '[dry-run] ' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Домашек затронуто: {touched_assignments}, '
            f'позиций создано: {created_total}.'))
