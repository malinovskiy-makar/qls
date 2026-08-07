"""
Применить правило «пустая работа = ноль автоматом» к УЖЕ сданным работам.

Само правило работает при сдаче (`part_grading.save_part_answers`), но в
базе остались работы, сданные до его появления: они висят в очереди ручной
проверки, хотя читать в них нечего. Команда доводит их до того же состояния,
в котором оказалась бы работа, сданная сегодня.

Трогает ТОЛЬКО работы, где пусто всё сразу: ответ, решение и файл. Работа,
где ответа нет, а решение написано, остаётся в очереди — её читает человек.
Уже проверенные работы не трогаются никогда.

Без --confirm только показывает, что сделал бы.

    ./venv/bin/python manage.py apply_auto_zero
    ./venv/bin/python manage.py apply_auto_zero --confirm
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from problems import part_grading
from problems.models import Submission


class Command(BaseCommand):
    help = 'Проставить автоматический ноль сданным пустым работам.'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='записать изменения (без него — только показ)')

    def handle(self, *args, **options):
        confirm = options['confirm']
        queue = Submission.objects.filter(status='submitted').select_related(
            'problem_item', 'problem_item__catalog_problem',
            'problem_item__custom_problem', 'student', 'assignment')

        blank = []
        for submission in queue:
            if (submission.submitted_answer or '').strip():
                continue
            if part_grading.wrote_anything(submission):
                continue
            item = submission.problem_item
            if item is None or not part_grading.applies(item):
                # Тесты и работы без позиции идут своим путём: тест машина
                # и так закрывает сразу, а позицию без адреса пересчитать
                # нечем — выдумывать за неё правило нельзя.
                continue
            blank.append(submission)

        self.stdout.write('в очереди проверки: %d' % queue.count())
        self.stdout.write('из них пустых целиком: %d' % len(blank))
        for submission in blank:
            self.stdout.write('  #%d  %s  «%s»' % (
                submission.pk, submission.student.username,
                str(submission.assignment)[:40]))

        if not blank:
            return
        if not confirm:
            self.stdout.write(self.style.WARNING(
                '\nэто показ. Записать: --confirm'))
            return

        with transaction.atomic():
            for submission in blank:
                item = submission.problem_item
                values = {(p.pk if p is not None else None): ''
                          for p in part_grading.answer_parts(item)}
                part_grading.apply_to_submission(submission, item, values)
                submission.save()

        self.stdout.write(self.style.SUCCESS(
            '\nпроставлен автоматический ноль: %d' % len(blank)))
