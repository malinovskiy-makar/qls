"""
История работ в обзоре группы (п. 11.5).

Столбцов семь, и от истории в карточке ученика отличается ровно один —
«Невовремя / не сдано». Сборка и разметка ОБЩИЕ; здесь проверяем именно
подсчёт опоздавших и несдавших и согласие чисел с карточкой ученика.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission,
    TeacherFeedback, User,
)


def make_user(username, role='student'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = role
    user.save()
    return user


class GroupWorkHistoryTests(TestCase):

    def setUp(self):
        self.tutor = make_user('gh_tutor', 'teacher')
        self.group = StudentGroup.objects.create(name='Группа истории',
                                                 teacher=self.tutor)
        self.a = make_user('gh_a')
        self.b = make_user('gh_b')
        self.c = make_user('gh_c')
        for student in (self.a, self.b, self.c):
            self.group.students.add(student)

        self.problem = Problem.objects.create(
            title='Задача истории', statement='Условие',
            status=Problem.Status.PUBLISHED)
        self.now = timezone.now()

    def make_work(self, name, deadline):
        work = Assignment.objects.create(name=name, author=self.tutor,
                                         group=self.group, deadline=deadline)
        work.students.set([self.a, self.b, self.c])
        item = AssignmentItem.objects.create(assignment=work, order=0,
                                             catalog_problem=self.problem,
                                             points=Decimal('10'))
        return work, item

    def submit(self, work, item, student, when, score=None):
        sub = Submission.objects.create(
            student=student, assignment=work, problem=self.problem,
            problem_item=item, submitted_answer='ответ', status='submitted')
        Submission.objects.filter(pk=sub.pk).update(submitted_at=when)
        if score is not None:
            TeacherFeedback.objects.create(submission=sub, score=score,
                                           reviewed_by=self.tutor)
        return sub

    def row_for(self, name):
        rows = stats.group_work_history(self.group)
        return next(row for row in rows if row['work'].name == name)

    def test_late_and_missing_are_counted_apart(self):
        deadline = self.now - timedelta(days=1)
        work, item = self.make_work('Домашка со сроком', deadline)
        # вовремя, с опозданием, не сдал
        self.submit(work, item, self.a, deadline - timedelta(hours=2))
        self.submit(work, item, self.b, deadline + timedelta(hours=2))
        row = self.row_for('Домашка со сроком')
        self.assertEqual(row['late'], 1)
        self.assertEqual(row['missing'], 1)

    def test_work_without_deadline_has_no_late_column(self):
        """⚠️ Без срока опоздать нельзя — прочерк, а не ноль."""
        work, item = self.make_work('Домашка без срока', None)
        self.submit(work, item, self.a, self.now)
        row = self.row_for('Домашка без срока')
        self.assertIsNone(row['late'])
        self.assertEqual(row['missing'], 2)

    def test_nobody_submitted_is_marked_idle(self):
        self.make_work('Никто не сдал', self.now + timedelta(days=1))
        row = self.row_for('Никто не сдал')
        self.assertTrue(row['not_submitted'])
        self.assertEqual(row['missing'], 3)

    def test_percent_is_weighted_by_points_not_by_students(self):
        """Оценка группы = набрано ÷ максимум, а не среднее из процентов."""
        deadline = self.now + timedelta(days=1)
        work, item = self.make_work('Оценка группы', deadline)
        self.submit(work, item, self.a, self.now, score=Decimal('10'))
        self.submit(work, item, self.b, self.now, score=Decimal('0'))
        row = self.row_for('Оценка группы')
        # 10 из 20 возможных по двум оценённым работам
        self.assertEqual(row['mark'], 50)
        self.assertEqual(row['open_percent'], 50)
        self.assertIsNone(row['test_percent'])

    def test_group_numbers_agree_with_student_card(self):
        """Числа группы сходятся с числами карточек отдельных учеников."""
        deadline = self.now + timedelta(days=1)
        work, item = self.make_work('Сверка', deadline)
        self.submit(work, item, self.a, self.now, score=Decimal('8'))
        self.submit(work, item, self.b, self.now, score=Decimal('2'))
        group_row = self.row_for('Сверка')
        marks = []
        for student in (self.a, self.b):
            row = next(r for r in stats.work_history(student, self.tutor)
                       if r['work'].pk == work.pk)
            marks.append(row['mark'])
        self.assertEqual(marks, [80, 20])
        # Средневзвешенное: (8 + 2) из 20 = 50 %
        self.assertEqual(group_row['mark'], 50)

    def test_overview_shows_the_block(self):
        self.client.force_login(self.tutor)
        self.make_work('Работа на экране', self.now + timedelta(days=1))
        body = self.client.get(
            reverse('teacher:group_detail',
                    args=[self.group.pk])).content.decode()
        self.assertIn('История работ', body)
        self.assertIn('Невовремя / не сдано', body)
        self.assertIn('Работа на экране', body)

    def test_student_card_has_no_group_column(self):
        """У карточки ученика столбец прежний — дата сдачи."""
        self.client.force_login(self.tutor)
        self.make_work('Работа ученика', self.now + timedelta(days=1))
        body = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.a.pk])).content.decode()
        self.assertIn('Дата сдачи', body)
        self.assertNotIn('Невовремя / не сдано', body)


class WorkHistoryStylesTests(TestCase):
    """⚠️ Класс есть, а стиля нет — знакомый класс дефекта (баг 7.6).

    Таблица истории стоит на ДВУХ страницах, и правила обязаны лежать в
    файле, который подключают обе.
    """

    def test_table_styles_live_in_the_shared_file(self):
        import os

        from django.conf import settings

        shared = os.path.join(settings.BASE_DIR, 'problems', 'templates',
                              'platform', '_stats_style.html')
        with open(shared, encoding='utf-8') as fh:
            self.assertIn('.wk-table', fh.read())

    def test_both_pages_include_that_file(self):
        import os

        from django.conf import settings

        for rel in (('teacher', 'templates', 'teacher', 'student_progress.html'),
                    ('teacher', 'templates', 'teacher', 'groups', 'detail.html')):
            path = os.path.join(settings.BASE_DIR, *rel)
            with open(path, encoding='utf-8') as fh:
                self.assertIn('platform/_stats_style.html', fh.read(), rel)
