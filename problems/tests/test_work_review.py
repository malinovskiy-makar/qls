"""
Разбор сданной работы: один экран, балл главным элементом, ошибки заметны.

Проверка цели Части B: ученик открывает сданную работу и видит, сколько
получил, что сказал преподаватель и что именно было не так.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.assignment_rows import answer_input_name, answer_parts
from problems.models import (
    Assignment, AssignmentItem, MistakeTag, ProblemPart, StudentGroup,
    Submission, WorkFeedback,
)
from problems.tests.factories import make_problem, make_user


def costs_problem():
    problem = make_problem('Фирма выпускает 100 единиц.', difficulty=2)
    ProblemPart.objects.create(problem=problem, label='а', order=0,
                               statement='Найдите TC.', answer='5000',
                               points=Decimal('1'))
    ProblemPart.objects.create(problem=problem, label='б', order=1,
                               statement='Найдите ATC.', answer='50',
                               points=Decimal('1'))
    return problem


class WorkReviewTests(TestCase):

    def setUp(self):
        self.tutor = make_user('wr_tutor', role='teacher')
        self.student = make_user('wr_student', role='student')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.group.students.add(self.student)
        self.homework = Assignment.objects.create(
            name='Домашка №9', author=self.tutor, group=self.group,
            deadline=timezone.now() + timedelta(days=1))
        self.homework.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, order=0, catalog_problem=costs_problem(),
            points=Decimal('2'))
        self.open_item = AssignmentItem.objects.create(
            assignment=self.homework, order=1,
            catalog_problem=make_problem('Открытая'), points=Decimal('8'))
        self.parts = answer_parts(self.item)
        self.client.force_login(self.student)

    def _submit(self, first='5000', second='60'):
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(self.item, self.parts[0]): first,
             answer_input_name(self.item, self.parts[1]): second,
             answer_input_name(self.open_item): 'мой ответ',
             'text_item_%d' % self.open_item.pk: 'ход решения'})

    def _url(self):
        return reverse('student:work_review', args=[self.homework.pk])

    def test_unsubmitted_work_redirects_back_to_solving(self):
        response = self.client.get(self._url())
        self.assertRedirects(
            response,
            reverse('student:assignment_detail', args=[self.homework.pk]))

    def test_score_is_the_biggest_thing_on_the_screen(self):
        self._submit()
        body = self.client.get(self._url()).content.decode()
        # Балл и его подпись есть, причём в шапке.
        self.assertIn('class="wr-score"', body)
        self.assertIn('по проверенным задачам', body)
        self.assertIn('предварительный результат', body)

    def test_partial_task_shows_per_part_verdicts(self):
        self._submit(first='5000', second='60')
        body = self.client.get(self._url()).content.decode()
        self.assertIn('частично', body)
        self.assertIn('5000', body)
        self.assertIn('верный:', body)

    def test_teacher_comment_and_mistakes_are_visible(self):
        self._submit()
        mistake = MistakeTag.objects.create(name='Не проверена размерность')
        submission = Submission.objects.get(problem_item=self.open_item)
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, submission.pk]),
            {'score': '6', 'comment': 'Ход верный, вывод скомкан',
             'mistakes': [mistake.pk],
             'work_comment': 'В целом хорошо, следи за единицами.'})
        self.client.force_login(self.student)

        body = self.client.get(self._url()).content.decode()
        self.assertIn('Ход верный, вывод скомкан', body)
        self.assertIn('Не проверена размерность', body)
        self.assertIn('В целом хорошо, следи за единицами.', body)
        self.assertIn('Комментарий преподавателя к работе', body)

    def test_final_score_after_everything_is_checked(self):
        self._submit()
        submission = Submission.objects.get(problem_item=self.open_item)
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, submission.pk]),
            {'score': '8', 'comment': 'Отлично'})
        self.client.force_login(self.student)

        body = self.client.get(self._url()).content.decode()
        self.assertIn('итоговый балл за работу', body)
        self.assertNotIn('предварительный результат', body)
        # 1 балл за верный пункт «а» + 8 за открытую = 9 из 10.
        self.assertIn('9', body)

    def test_wrong_tasks_are_opened_by_default(self):
        """Разбор начинается с того, что не получилось."""
        self._submit(first='1', second='2')
        body = self.client.get(self._url()).content.decode()
        self.assertIn('data-attention="1"', body)
        self.assertIn('сначала с ошибками', body)

    def test_old_per_problem_screen_redirects_here(self):
        """Двух похожих экранов результата не осталось."""
        self._submit()
        submission = Submission.objects.get(problem_item=self.item)
        response = self.client.get(
            reverse('student:submission_detail', args=[submission.pk]))
        self.assertRedirects(response, self._url())

    def test_dashboard_links_to_the_review(self):
        self._submit()
        body = self.client.get(reverse('student:dashboard')).content.decode()
        self.assertIn(self._url(), body)

    def test_foreign_student_cannot_open(self):
        outsider = make_user('wr_outsider', role='student')
        self._submit()
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self._url()).status_code, 404)


class TutorSeesTheSameScreenTests(TestCase):

    def setUp(self):
        self.tutor = make_user('wt_tutor', role='teacher')
        self.other = make_user('wt_other', role='teacher')
        self.student = make_user('wt_student', role='student')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.group.students.add(self.student)
        self.homework = Assignment.objects.create(
            name='ДЗ', author=self.tutor, group=self.group)
        self.homework.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, order=0,
            catalog_problem=make_problem('Задача'), points=Decimal('5'))
        self.client.force_login(self.student)
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(self.item): 'ответ'})

    def _url(self):
        return reverse('teacher:student_work_review',
                       args=[self.group.pk, self.homework.pk, self.student.pk])

    def test_tutor_opens_the_students_own_screen(self):
        self.client.force_login(self.tutor)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('class="wr-score"', body)
        self.assertIn(self.student.username, body)

    def test_foreign_tutor_gets_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self._url()).status_code, 404)

    def test_student_cannot_open_the_tutor_url(self):
        self.client.force_login(self.student)
        self.assertIn(self.client.get(self._url()).status_code, (403, 404, 302))


class ExamReviewTests(TestCase):
    """Контрольная открывается на ТОТ ЖЕ экран."""

    def setUp(self):
        now = timezone.now()
        self.tutor = make_user('we_tutor', role='teacher')
        self.student = make_user('we_student', role='student')
        self.exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.WINDOW,
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=1),
            deadline=now + timedelta(hours=1))
        self.exam.students.add(self.student)
        AssignmentItem.objects.create(
            assignment=self.exam, order=0,
            catalog_problem=make_problem('Задача', answer='7'), points=3)
        self.client.force_login(self.student)

    def test_exam_result_redirects_to_the_single_screen(self):
        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]))
        response = self.client.get(
            reverse('student:exam_result', args=[self.exam.pk]))
        self.assertRedirects(
            response, reverse('student:work_review', args=[self.exam.pk]))

    def test_hidden_results_still_show_the_teachers_work(self):
        self.exam.show_results_immediately = False
        self.exam.save(update_fields=['show_results_immediately'])
        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]))
        url = reverse('student:work_review', args=[self.exam.pk])
        body = self.client.get(url).content.decode()
        self.assertIn('преподаватель откроет результат', body)

        submission = Submission.objects.filter(assignment=self.exam).first()
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('teacher:review_submission', args=[submission.pk]),
            {'score': '3', 'comment': 'Виден всегда'})
        self.client.force_login(self.student)
        body = self.client.get(url).content.decode()
        self.assertIn('Виден всегда', body)


class QueryCountTests(TestCase):
    """Экран разбора не должен делать больше 30 запросов."""

    def test_review_screen_query_budget(self):
        tutor = make_user('qc_tutor', role='teacher')
        student = make_user('qc_student', role='student')
        homework = Assignment.objects.create(name='ДЗ', author=tutor)
        homework.students.add(student)
        payload = {}
        for index in range(8):
            item = AssignmentItem.objects.create(
                assignment=homework, order=index,
                catalog_problem=make_problem('Задача %d' % index, answer='1'),
                points=Decimal('2'))
            payload[answer_input_name(item)] = '1'
        self.client.force_login(student)
        self.client.post(
            reverse('student:submit_assignment', args=[homework.pk]), payload)

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = reverse('student:work_review', args=[homework.pk])
        with CaptureQueriesContext(connection) as captured:
            self.client.get(url)
        self.assertLessEqual(len(captured), 30,
                             'экран разбора стал дороже 30 запросов: %d'
                             % len(captured))
