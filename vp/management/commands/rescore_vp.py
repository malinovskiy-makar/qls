"""Пересчёт баллов СДАННЫХ попыток ВП по текущим эталонам.

Зачем. `import_vp` правит эталон на месте (тот же `VPItem`), а баллы сданной
попытки записаны один раз, при сдаче (`views._finalize`), и сами не меняются.
После правки эталона старые попытки пересчитываются этой командой.

Правило владельца (23.09.2026): пересчёт СТРОГО по текущим эталонам в обе
стороны — балл может и вырасти, и упасть. Ученику ничего отдельно не
показываем: экран результата, «Мои попытки» и таблица лучших читают
`VPAttempt.score`; процентиль обновится сам, его кэш живёт 5 минут
(`review.COHORT_TTL`).

Арифметики здесь нет: балл задания — `scoring.score_item`, итог попытки —
`scoring.score_attempt`, ровно те же вызовы, что при сдаче. Меняются только
`VPAnswer.score`, `VPAnswer.is_correct`, `VPAnswer.max_score` и `VPAttempt.score`.
Время сдачи, зачётность, код попытки и сами ответы не трогаются. Несданные
попытки не трогаются: их посчитает сдача.

`--dry-run` выполняет всё и откатывает транзакцию (как `import_vp`), поэтому
числа сухого прогона — те же, что у настоящего.

    manage.py rescore_vp --all --dry-run
    manage.py rescore_vp --variant vp-1tur-2026-olmat-11-v3 --variant … [--dry-run]
    manage.py rescore_vp --all -v 2      # ещё и список изменённых попыток
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vp import scoring
from vp.models import VPAnswer, VPAttempt, VPVariant


class Command(BaseCommand):
    help = 'Пересчитать баллы сданных попыток ВП по текущим эталонам.'

    def add_arguments(self, parser):
        parser.add_argument('--variant', action='append', default=[], metavar='SLUG',
                            help='Слаг варианта; ключ можно повторять.')
        parser.add_argument('--all', action='store_true',
                            help='Все варианты.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Посчитать и показать, в базу не писать.')

    def handle(self, *args, **options):
        slugs, everything = options['variant'], options['all']
        if bool(slugs) == bool(everything):
            raise CommandError('Укажите либо --all, либо один или несколько --variant.')
        variants = (VPVariant.objects.all() if everything
                    else VPVariant.objects.filter(slug__in=slugs))
        missing = sorted(set(slugs) - set(variants.values_list('slug', flat=True)))
        if missing:
            raise CommandError(f'Нет таких вариантов: {", ".join(missing)}')

        dry_run = options['dry_run']
        prefix = '[dry-run, в базу не писали] ' if dry_run else ''
        checked, answers_changed, went_up, went_down = 0, 0, 0, 0
        per_item = defaultdict(Counter)  # (слаг, №) -> {'верно': n, 'неверно': n, …}
        lines = []

        with transaction.atomic():
            # Блокировки не нужны: сданную попытку сдача больше не трогает
            # (`views._finalize` идемпотентна), а несданные сюда не попадают.
            attempts = (VPAttempt.objects
                        .filter(variant__in=variants, submitted_at__isnull=False)
                        .select_related('variant').order_by('pk'))
            for attempt in attempts:
                checked += 1
                fixed = []
                for answer in attempt.answers.select_related('item'):
                    score, is_correct = scoring.score_item(answer.item, answer.raw)
                    top = answer.item.points
                    if (score, is_correct, top) == (answer.score, answer.is_correct,
                                                    answer.max_score):
                        continue
                    key = (attempt.variant.slug, answer.item.number)
                    if answer.is_correct is not True and is_correct is True:
                        per_item[key]['стало верно'] += 1
                    elif answer.is_correct is True and is_correct is not True:
                        per_item[key]['стало неверно'] += 1
                    else:
                        per_item[key]['изменился балл'] += 1
                    answer.score, answer.is_correct, answer.max_score = score, is_correct, top
                    fixed.append(answer)
                total = scoring.score_attempt(attempt)
                if not fixed and total == attempt.score:
                    continue
                answers_changed += len(fixed)
                if attempt.score is None or total > attempt.score:
                    went_up += 1
                elif total < attempt.score:
                    went_down += 1
                numbers = ', '.join(f'№{a.item.number}' for a in
                                    sorted(fixed, key=lambda a: a.item.number)) or 'только итог'
                lines.append(f'  {attempt.variant.slug} · {attempt.public_code}: '
                             f'{attempt.score} → {total} ({numbers})')
                VPAnswer.objects.bulk_update(fixed, ['score', 'is_correct', 'max_score'])
                attempt.score = total
                attempt.save(update_fields=['score'])
            if dry_run:
                transaction.set_rollback(True)

        changed = len(lines)
        self.stdout.write(f'Вариантов: {variants.count()}, сданных попыток проверено: {checked}')
        if not changed:
            self.stdout.write(self.style.SUCCESS(
                'Изменений нет: все сданные попытки совпадают с текущими эталонами.'))
            return
        self.stdout.write(f'{prefix}Попыток изменено: {changed} (балл вырос: {went_up}, '
                          f'упал: {went_down}); ответов изменено: {answers_changed}')
        self.stdout.write('По заданиям:')
        for (slug, number), counts in sorted(per_item.items()):
            parts = ', '.join(f'{name} {count}' for name, count in sorted(counts.items()))
            self.stdout.write(f'  {slug} №{number}: {parts}')
        if options['verbosity'] >= 2:
            self.stdout.write('Попытки:')
            for line in lines:
                self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS(f'{prefix}Готово.'))
