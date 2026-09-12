# -*- coding: utf-8 -*-
"""import_dup_human_choices — приёмщик разметки из dedup_human_review_html.

Читает JSON, который страница отдаёт кнопкой «Скачать разметку», и кладёт
его в `DupHumanChoice`. Без `--apply` только считает и печатает план — как
у остальных команд проекта, пишущих в базу.

Откат полный: `--revert` снимает строки ровно тех групп, что перечислены в
файле, и ничего больше. В `Problem` и в `DupMark` команда не пишет вовсе —
разметка человека живёт рядом с алгоритмической, а не поверх неё.
"""
import io
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.dedup import REASON_TAG_KEYS
from problems.models import DupHumanChoice, DupMark, Problem

VERDICTS = {v for v, _label in DupHumanChoice.Verdict.choices}


def validate(rows):
    """Разбор строк файла. Возвращает `(годные, жалобы)`.

    Строка с непонятным вердиктом или с фаворитом не из своей группы —
    это ошибка данных, а не повод упасть целиком: остальная разметка
    честно заработана человеком и теряться не должна.
    """
    good, complaints = [], []
    groups = {}
    for group, pid in DupMark.objects.values_list('group', 'problem_id'):
        groups.setdefault(group, set()).add(pid)

    for index, row in enumerate(rows, 1):
        group = row.get('group')
        verdict = row.get('verdict')
        chosen = row.get('chosen_problem_id')
        where = 'строка %s (группа %s)' % (index, group)

        if group not in groups:
            complaints.append('%s: такой группы нет в DupMark' % where)
            continue
        if verdict not in VERDICTS:
            complaints.append('%s: неизвестный вердикт %r' % (where, verdict))
            continue
        if verdict == DupHumanChoice.Verdict.CHOSEN:
            if chosen not in groups[group]:
                complaints.append('%s: фаворит #%s не входит в эту группу'
                                  % (where, chosen))
                continue
        else:
            chosen = None

        tags = [t for t in (row.get('reason_tags') or []) if t in REASON_TAG_KEYS]
        unknown = set(row.get('reason_tags') or []) - REASON_TAG_KEYS
        if unknown:
            complaints.append('%s: причины вне списка отброшены: %s'
                              % (where, ', '.join(sorted(unknown))))

        good.append({'group': group, 'verdict': verdict, 'chosen': chosen,
                     'reason_tags': ','.join(tags),
                     'note': (row.get('note') or '').strip()})
    return good, complaints


class Command(BaseCommand):
    help = 'Принять разметку групп копий из JSON страницы разметки.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='JSON, скачанный со страницы разметки')
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу (без флага — только план)')
        parser.add_argument('--revert', action='store_true',
                            help='снять строки групп, перечисленных в файле')

    def handle(self, *args, **options):
        if options['apply'] and options['revert']:
            raise CommandError('--apply и --revert вместе не имеют смысла')

        try:
            with io.open(options['path'], encoding='utf-8') as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as error:
            raise CommandError('не читается файл разметки: %s' % error)

        rows = payload.get('rows') if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CommandError('в файле нет списка rows')

        good, complaints = validate(rows)
        for complaint in complaints:
            self.stdout.write(self.style.WARNING('  ' + complaint))

        if options['revert']:
            names = [row['group'] for row in good]
            existing = DupHumanChoice.objects.filter(group__in=names)
            self.stdout.write('Снять строк: %s' % existing.count())
            existing.delete()
            self.stdout.write(self.style.SUCCESS('Разметка снята'))
            return

        by_verdict = {}
        for row in good:
            by_verdict[row['verdict']] = by_verdict.get(row['verdict'], 0) + 1
        self.stdout.write('Годных строк: %s из %s' % (len(good), len(rows)))
        for verdict, number in sorted(by_verdict.items()):
            self.stdout.write('  %-16s %4d' % (verdict, number))

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                'Это план. Запись — тот же вызов с --apply.'))
            return

        now = timezone.now()
        with transaction.atomic():
            for row in good:
                DupHumanChoice.objects.update_or_create(
                    group=row['group'],
                    defaults={
                        'verdict': row['verdict'],
                        'chosen_problem': (Problem.objects.filter(pk=row['chosen']).first()
                                           if row['chosen'] else None),
                        'reason_tags': row['reason_tags'],
                        'note': row['note'],
                        'labeled_at': now,
                    })
        self.stdout.write(self.style.SUCCESS(
            'Записано строк: %s' % len(good)))
