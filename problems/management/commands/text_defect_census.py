"""
Перепись признаков порчи в текстах каталога. ТОЛЬКО ЧТЕНИЕ.

Команда ничего не правит и ничего не пишет в базу: её итог — отчёт, по
которому чистка базы становится отдельной задачей со своим стоп-гейтом.
Часть признаков лечится на лету при показе и экспорте
(`problems/text_clean.py`), часть чинить нечем — и ровно это разделение
здесь и меряется.

    ./venv/bin/python manage.py text_defect_census
    ./venv/bin/python manage.py text_defect_census --out reports/text_defects
"""
import os
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from problems.text_clean import (
    DEFECT_NAMES, FIXED_AUTOMATICALLY, REPORTED_ONLY, clean, defects,
    same_numbers_and_signs,
)

FIELDS = ('statement', 'solution', 'answer')


class Command(BaseCommand):
    help = 'Перепись признаков порчи в текстах задач (только чтение)'

    def add_arguments(self, parser):
        parser.add_argument('--out', default='reports/text_defects',
                            help='Куда положить отчёт')
        parser.add_argument('--all', action='store_true',
                            help='Считать по всей базе, а не только по '
                                 'видимым в каталоге задачам')
        parser.add_argument('--examples', type=int, default=8,
                            help='Сколько примеров id хранить на признак')

    def handle(self, *args, **options):
        from problems.models import Problem, ProblemPart

        queryset = Problem.objects.all()
        scope = 'вся база'
        if not options['all']:
            queryset = queryset.filter(
                status=Problem.Status.PUBLISHED, needs_quality_review=False)
            scope = 'видимые в каталоге (published, без флага качества)'

        by_defect = Counter()          # задач с признаком
        by_field = Counter()           # полей с признаком
        examples = defaultdict(list)
        dirty_problems = set()
        total = 0
        changed_by_cleaner = 0
        numbers_broken = 0

        self.stdout.write('Считаю по условиям, решениям и ответам…')
        for pid, *values in queryset.values_list('id', *FIELDS).iterator(
                chunk_size=2000):
            total += 1
            found = set()
            for name, text in zip(FIELDS, values):
                marks = defects(text)
                if marks:
                    by_field[name] += 1
                found |= marks
                fixed = clean(text or '')
                if fixed != (text or ''):
                    changed_by_cleaner += 1
                    # ⚠️ Контроль главного правила прямо на живых данных, а
                    # не только в тестах: если санитайзер хоть где-то тронул
                    # число, это надо знать до, а не после разговора о
                    # чистке базы.
                    if not same_numbers_and_signs(text or '', fixed):
                        numbers_broken += 1
            if found:
                dirty_problems.add(pid)
                for mark in found:
                    by_defect[mark] += 1
                    if len(examples[mark]) < options['examples']:
                        examples[mark].append(pid)

        parts_dirty = 0
        part_defects = Counter()
        parts_queryset = ProblemPart.objects.all()
        if not options['all']:
            parts_queryset = parts_queryset.filter(
                problem__status=Problem.Status.PUBLISHED,
                problem__needs_quality_review=False)
        for statement, in parts_queryset.values_list('statement').iterator(
                chunk_size=5000):
            marks = defects(statement)
            if marks:
                parts_dirty += 1
                for mark in marks:
                    part_defects[mark] += 1

        os.makedirs(options['out'], exist_ok=True)
        path = os.path.join(options['out'], 'census.md')
        with open(path, 'w', encoding='utf-8') as report:
            self._write(report, scope, total, dirty_problems, by_defect,
                        by_field, examples, parts_dirty, part_defects,
                        changed_by_cleaner, numbers_broken)

        self.stdout.write('')
        self.stdout.write('Задач осмотрено: %d' % total)
        self.stdout.write('Задач с признаками порчи: %d (%.1f%%)'
                          % (len(dirty_problems),
                             100.0 * len(dirty_problems) / max(total, 1)))
        for mark, count in by_defect.most_common():
            self.stdout.write('  %-58s %6d' % (DEFECT_NAMES[mark], count))
        self.stdout.write('Подпунктов с признаками: %d' % parts_dirty)
        self.stdout.write('Полей, которые санитайзер меняет на лету: %d'
                          % changed_by_cleaner)
        if numbers_broken:
            self.stdout.write(self.style.ERROR(
                'ВНИМАНИЕ: санитайзер изменил числа в %d полях — это запрет'
                % numbers_broken))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Санитайзер не изменил ни одного числа и ни одного знака'))
        self.stdout.write('Отчёт: %s' % path)

    def _write(self, out, scope, total, dirty, by_defect, by_field, examples,
               parts_dirty, part_defects, changed, numbers_broken):
        out.write('# Перепись признаков порчи в текстах задач\n\n')
        out.write('Только чтение: команда ничего не правит.\n\n')
        out.write('* Охват: %s\n' % scope)
        out.write('* Задач осмотрено: **%d**\n' % total)
        out.write('* Задач хотя бы с одним признаком: **%d** (%.1f%%)\n'
                  % (len(dirty), 100.0 * len(dirty) / max(total, 1)))
        out.write('* Подпунктов с признаками: **%d**\n' % parts_dirty)
        out.write('* Полей, которые санитайзер правит при показе: **%d**\n'
                  % changed)
        out.write('* Полей, где санитайзер изменил число или знак: **%d** '
                  '(обязано быть 0)\n\n' % numbers_broken)

        out.write('## Чинится на лету при показе и экспорте\n\n')
        out.write('| Признак | Задач | Подпунктов | Примеры id |\n')
        out.write('|---|---:|---:|---|\n')
        for mark in FIXED_AUTOMATICALLY:
            out.write('| %s | %d | %d | %s |\n'
                      % (DEFECT_NAMES[mark], by_defect.get(mark, 0),
                         part_defects.get(mark, 0),
                         ', '.join(str(x) for x in examples.get(mark, []))))

        out.write('\n## Только считается — чинить нечем\n\n')
        out.write('Это и есть содержание будущей задачи «чистка текстов '
                  'каталога в базе»: правки здесь неоднозначны, поэтому '
                  'делать их надо отдельным этапом со стоп-гейтом, а не '
                  'на лету.\n\n')
        out.write('| Признак | Задач | Подпунктов | Примеры id |\n')
        out.write('|---|---:|---:|---|\n')
        for mark in REPORTED_ONLY:
            out.write('| %s | %d | %d | %s |\n'
                      % (DEFECT_NAMES[mark], by_defect.get(mark, 0),
                         part_defects.get(mark, 0),
                         ', '.join(str(x) for x in examples.get(mark, []))))

        out.write('\n## По полям\n\n')
        for name in FIELDS:
            out.write('* `%s`: %d\n' % (name, by_field.get(name, 0)))
