"""Пометить комплекты пакета олимпиад, повторяющие другой комплект.

    manage.py mark_olympiad_kit_duplicates                 # сухой прогон
    manage.py mark_olympiad_kit_duplicates --only vseros
    manage.py mark_olympiad_kit_duplicates --apply         # запись

⚠️ ПО УМОЛЧАНИЮ — СУХОЙ ПРОГОН. Запись — только `duplicate_of` и
`duplicate_kind` комплектов, одной транзакцией. Команда НИКОГДА не удаляет
комплекты, позиции, файлы и задачи, не трогает `visibility` и не меняет
комплекты, на которых есть попытки (`TrainingAttempt`); счётчики до и после
сверяются, расхождение откатывает транзакцию целиком. Повторный прогон на
тех же данных — 0 изменений. Правило — `olympiads/kit_duplicates.py`,
ADR 0171.
"""
import collections
import datetime
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from olympiads import kit_duplicates as kd


def counters():
    """То, что команда менять не смеет."""
    from olympiads.models import (OlympiadVariant, OlympiadVariantFile,
                                  OlympiadVariantItem)
    from problems.models import Problem
    return {
        'variants': OlympiadVariant.objects.count(),
        'published': OlympiadVariant.objects.filter(
            visibility=OlympiadVariant.Visibility.PUBLISHED).count(),
        'items': OlympiadVariantItem.objects.count(),
        'files': OlympiadVariantFile.objects.count(),
        'problems': Problem.objects.count(),
    }


class Command(BaseCommand):
    help = ('Пометить повторы комплектов пакета олимпиад (duplicate_of). '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--only', default='',
                            help='Только одна олимпиада по слагу, например vseros.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Сухой прогон (по умолчанию и так он).')
        parser.add_argument('--apply', action='store_true',
                            help='Записать в базу.')
        parser.add_argument('--report-dir', default='',
                            help='Куда класть отчёт (по умолчанию reports/).')

    def handle(self, *args, **options):
        from olympiads.models import OlympiadVariant

        if options['dry_run'] and options['apply']:
            raise CommandError('--dry-run и --apply вместе нельзя.')
        apply = options['apply']

        kits, matcher = kd.load(options['only'])
        desired, details = kd.decide(kits, matcher)
        by_pk = {kit.pk: kit for kit in kits}
        changes = [(kit, desired[kit.pk]) for kit in kits
                   if not kit.locked and desired[kit.pk] != kit.current]

        before = counters()
        if apply and changes:
            with transaction.atomic():
                for kit, (parent, kind) in changes:
                    OlympiadVariant.objects.filter(pk=kit.pk).update(
                        duplicate_of_id=parent, duplicate_kind=kind)
                after = counters()
                if after != before:
                    raise CommandError('Счётчики сдвинулись: {} → {}. Откат.'
                                       .format(before, after))
        else:
            after = before

        slugs = dict(OlympiadVariant.objects.filter(pk__in=by_pk)
                     .values_list('pk', 'olympiad__slug'))
        table = collections.defaultdict(collections.Counter)
        for kit in kits:
            parent, kind = desired[kit.pk]
            table[slugs[kit.pk]]['kits'] += 1
            table[slugs[kit.pk]]['hidden'] += kit.hidden
            if kind:
                table[slugs[kit.pk]][kind] += 1

        self.stdout.write('Комплектов-кандидатов: {}, изменений: {}{}'.format(
            len(kits), len(changes), ' (записано)' if apply else ' (сухой прогон)'))
        for slug in sorted(table):
            row = table[slug]
            self.stdout.write('  {:24} комплектов {:4} (скрытых {:2})  source {:4}  '
                              'combined {:4}'.format(slug, row['kits'], row['hidden'],
                                                     row['source'], row['combined']))
        if details['skipped'].get('locked'):
            self.stdout.write('Не тронуты (есть попытки): {}'.format(
                ', '.join(details['skipped']['locked'])))
        if details['skipped'].get('grades_or_hidden'):
            self.stdout.write('Сводные не помечены (классы не покрыты или '
                              'основной скрыт): {}'.format(
                                  ', '.join(details['skipped']['grades_or_hidden'])))
        self.stdout.write('Счётчики до: {}'.format(before))
        self.stdout.write('Счётчики после: {}'.format(after))

        marks = [{'kit': kit.kit_key, 'kind': desired[kit.pk][1],
                  'duplicate_of': by_pk[desired[kit.pk][0]].kit_key}
                 for kit in kits if desired[kit.pk][0]]
        directory = options['report_dir'] or os.path.join(settings.BASE_DIR, 'reports')
        os.makedirs(directory, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(directory, 'olympiads_dups_{}.json'.format(stamp))
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'only': options['only'], 'apply': apply,
                       'changes': len(changes), 'counters_before': before,
                       'counters_after': after, 'marks': marks, **details},
                      fh, ensure_ascii=False, indent=1)
        self.stdout.write('Отчёт: {}'.format(path))
