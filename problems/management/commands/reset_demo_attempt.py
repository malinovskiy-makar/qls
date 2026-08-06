"""
Сброс попытки ученика по контрольной — чтобы пройти сценарий заново.

Нужна ровно для ручных и браузерных проверок: контрольную можно писать
ОДИН раз, и после первой сдачи страница прохождения больше не открывается.
Без этой команды каждый повторный прогон приходится чистить SQL-ом руками.

    ./venv/bin/python manage.py reset_demo_attempt --exam 7 --student student3@test.local
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Сбрасывает попытку ученика по контрольной (только для демо).'

    def add_arguments(self, parser):
        parser.add_argument('--exam', type=int, required=True,
                            help='id контрольной')
        parser.add_argument('--student', required=True,
                            help='логин ученика')

    @transaction.atomic
    def handle(self, *args, **options):
        from problems.models import (
            AnswerDraft, Assignment, ExamAttempt, PartAnswer, Submission,
            TeacherFeedback, User,
        )

        student = User.objects.filter(username=options['student']).first()
        if student is None:
            self.stderr.write('Нет такого ученика: %s' % options['student'])
            return
        exam = Assignment.objects.filter(pk=options['exam']).first()
        if exam is None:
            self.stderr.write('Нет такой работы: %s' % options['exam'])
            return

        attempts = ExamAttempt.objects.filter(assignment=exam, student=student)
        AnswerDraft.objects.filter(attempt__in=attempts).delete()
        attempts_count = attempts.count()
        attempts.delete()

        submissions = Submission.objects.filter(assignment=exam,
                                                student=student)
        PartAnswer.objects.filter(submission__in=submissions).delete()
        TeacherFeedback.objects.filter(submission__in=submissions).delete()
        submissions_count = submissions.count()
        submissions.delete()

        self.stdout.write(self.style.SUCCESS(
            'Сброшено: попыток %d, решений %d. Работу «%s» можно писать '
            'заново.' % (attempts_count, submissions_count, exam.name)))
