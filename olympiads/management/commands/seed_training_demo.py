"""Демо-привязка задач банка к комплектам олимпиад — чтобы тренировку было
на чём посмотреть глазами.

⚠️ ЭТА КОМАНДА ПИШЕТ В `problems`, и это единственное место раздела, которое
себе такое позволяет. Обычный код олимпиад в банк не пишет вовсе
([ADR 0063]); здесь исключение осознанное и узкое: настоящие привязки
`OlympiadRef` строятся сопоставлением по ссылкам с внешним индексом, и до
того, как этот прогон сделан, тренировать не на чем.

Защита от порчи настоящих данных:
* комплект, у которого привязки УЖЕ есть, не трогается вовсе;
* у демо-записей `record_id` начинается с `demo:` — по нему же и удаляются;
* без `--yes` печатается план и не пишется ничего.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from olympiads.models import OlympiadVariant

DEMO_PREFIX = 'demo:'


class Command(BaseCommand):
    help = ('Демонстрационные привязки задач банка к комплектам олимпиад '
            '(problems.OlympiadRef). Без --yes только печатает план.')

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true',
                            help='Действительно записать привязки.')
        parser.add_argument('--wipe', action='store_true',
                            help='Сначала удалить прежние демо-привязки.')

    def handle(self, *args, **options):
        from problems.models import OlympiadRef, Problem

        variants = list(OlympiadVariant.objects
                        .exclude(ref_event_id='')
                        .select_related('olympiad', 'stage')
                        .order_by('pk'))
        if not variants:
            self.stdout.write('Комплектов с ref_event_id нет — нечего связывать.')
            return

        # Берём задачи с непустым условием, детерминированно по номеру:
        # повторный запуск обязан дать тот же набор, иначе «тот же комплект»
        # каждый раз оказывался бы другим.
        pool = list(Problem.objects.exclude(statement='')
                    .order_by('id').values_list('id', flat=True)[:600])
        if not pool:
            self.stdout.write(self.style.WARNING(
                'В банке нет задач — привязывать нечего.'))
            return

        plan = []
        cursor = 0
        for variant in variants:
            event_id = variant.ref_event_id
            existing = OlympiadRef.objects.filter(event_id=event_id)
            if existing.exclude(record_id__startswith=DEMO_PREFIX).exists():
                plan.append((variant, event_id, 0, 'есть настоящие привязки'))
                continue
            count = variant.problem_count or 5
            chosen = pool[cursor:cursor + count]
            cursor = (cursor + count) % max(1, len(pool) - count)
            plan.append((variant, event_id, len(chosen), chosen))

        if not options['yes']:
            self.stdout.write('ПЛАН (ничего не записано, нужен --yes):')
            for variant, event_id, count, tail in plan:
                note = tail if isinstance(tail, str) else '{} задач'.format(count)
                self.stdout.write('  {:<26} {}'.format(event_id, note))
            return

        created = 0
        with transaction.atomic():
            if options['wipe']:
                gone, _ = OlympiadRef.objects.filter(
                    record_id__startswith=DEMO_PREFIX).delete()
                self.stdout.write('Удалено демо-привязок: {}'.format(gone))
            for variant, event_id, count, tail in plan:
                if isinstance(tail, str):
                    continue
                for number, problem_id in enumerate(tail, start=1):
                    _, made = OlympiadRef.objects.get_or_create(
                        problem_id=problem_id, event_id=event_id,
                        defaults=dict(
                            source_site='solvehub',
                            olympiad_slug=variant.olympiad.slug,
                            olympiad_name=variant.olympiad.name_short,
                            year=variant.year,
                            stage=variant.stage.code if variant.stage else '',
                            grade=str(variant.grade or ''),
                            number=str(number),
                            record_id='{}{}:{}'.format(DEMO_PREFIX, event_id,
                                                       number),
                            match_score=0.0,
                            reviewed_by_human=False,
                        ))
                    created += int(made)

        self.stdout.write(self.style.SUCCESS(
            'Демо-привязок создано: {}. Комплектов затронуто: {}.'.format(
                created, sum(1 for _, _, c, t in plan if not isinstance(t, str)))))
        self.stdout.write(
            'Это ДЕМО-данные: задачи выбраны по порядку номеров, к реальным '
            'турам отношения не имеют.')
