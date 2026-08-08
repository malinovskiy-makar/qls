"""
Применить правило «пустая работа = ноль автоматом» к УЖЕ сданным работам.

Само правило работает при сдаче (`part_grading.save_part_answers` и
`part_grading.close_blank_position`), но в базе остались работы, сданные до
его появления: они висят в очереди ручной проверки или вовсе показывают
прочерк вместо балла. Команда доводит их до того же состояния, в котором
оказалась бы работа, сданная сегодня.

ДВА КЛАССА, и оба про одно и то же — «ученик не написал ничего»:

1. Позиция В ОЧЕРЕДИ (`submitted`), где пусто всё: ответ, решение, файл.
   Читать репетитору нечего — ставим ноль, из очереди убираем.
2. Позиция НЕ НАЧАТА (`not_started`) в работе, которую ученик ОТПРАВИЛ.
   Раньше приём работы такие позиции молча пропускал, и на экране стоял
   прочерк: балла нет, и увидеть позицию тоже нельзя. Ставим ноль.

Работа, где ответа нет, а решение написано, не трогается никогда — её
читает человек. Уже проверенные оценки не трогаются никогда.

Идемпотентна: повторный запуск ничего не находит.

Без --confirm только показывает, что сделал бы.

    ./venv/bin/python manage.py apply_auto_zero
    ./venv/bin/python manage.py apply_auto_zero --confirm
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from problems import part_grading
from problems.models import Submission


class Command(BaseCommand):
    help = 'Проставить автоматический ноль пустым позициям сданных работ.'

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

        untouched = self._untouched_of_submitted_works()
        self.stdout.write('')
        self.stdout.write('не начатых позиций в ОТПРАВЛЕННЫХ работах: %d'
                          % len(untouched))
        for submission in untouched:
            self.stdout.write('  #%d  %s  «%s»' % (
                submission.pk, submission.student.username,
                str(submission.assignment)[:40]))

        if not blank and not untouched:
            self.stdout.write(self.style.SUCCESS('\nнечего исправлять'))
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
            closed = 0
            for submission in untouched:
                if part_grading.close_blank_position(submission,
                                                     submission.problem_item):
                    closed += 1

        self.stdout.write(self.style.SUCCESS(
            '\nпроставлен автоматический ноль: %d в очереди + %d не начатых'
            % (len(blank), closed)))

    def _untouched_of_submitted_works(self):
        """Позиции «не начата» в работах, которые ученик отправил.

        Работа считается отправленной, если хоть по одной её позиции этот
        ученик что-то сдал. Пока не отправил ни одной — работа просто идёт,
        и раздавать нули за незаполненное было бы наказанием за то, что
        человек ещё не закончил.
        """
        submitted_pairs = set(
            Submission.objects
            .filter(status__in=('submitted', 'reviewed'))
            .values_list('assignment_id', 'student_id'))

        rows = []
        query = (Submission.objects
                 .exclude(status__in=('submitted', 'reviewed'))
                 .select_related('problem_item',
                                 'problem_item__catalog_problem',
                                 'problem_item__custom_problem',
                                 'student', 'assignment'))
        for submission in query:
            if (submission.assignment_id,
                    submission.student_id) not in submitted_pairs:
                continue
            if submission.problem_item is None:
                continue
            if (submission.submitted_answer or '').strip():
                continue
            if part_grading.wrote_anything(submission):
                continue
            rows.append(submission)
        return rows
