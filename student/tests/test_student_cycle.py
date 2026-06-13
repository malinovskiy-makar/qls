"""
Тесты цикла ученика: доступ, выдача домашки, отправка ответа,
автопроверка тестовых задач.
"""

from django.test import TestCase
from django.urls import reverse

from problems.models import ProblemPart, Submission
from problems.tests.factories import (
    make_assignment, make_problem, make_user,
)


class StudentAccessTests(TestCase):
    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('student:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_teacher_gets_403(self):
        teacher = make_user('t1', role='teacher')
        self.client.force_login(teacher)
        resp = self.client.get(reverse('student:dashboard'))
        self.assertEqual(resp.status_code, 403)


class StudentCycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = make_user('teacher', role='teacher')
        cls.student = make_user('student', role='student')
        cls.test_problem = make_problem(
            'Тестовый вопрос: выберите вариант.', answer='Б',
            problem_type='тест: один ответ')
        cls.open_problem = make_problem('Открытая задача: найдите Q*.')
        cls.assignment = make_assignment(
            cls.teacher, students=[cls.student],
            problems=[cls.test_problem, cls.open_problem])

    def setUp(self):
        self.client.force_login(self.student)

    def test_dashboard_shows_assignment(self):
        resp = self.client.get(reverse('student:dashboard'))
        self.assertEqual(resp.status_code, 200)
        names = [item['assignment'].name for item in resp.context['active']]
        self.assertIn(self.assignment.name, names)

    def test_assignment_detail_creates_submissions(self):
        resp = self.client.get(
            reverse('student:assignment_detail', args=[self.assignment.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            Submission.objects.filter(student=self.student,
                                      assignment=self.assignment).count(), 2)

    def test_foreign_assignment_404(self):
        other = make_user('other', role='student')
        self.client.force_login(other)
        resp = self.client.get(
            reverse('student:assignment_detail', args=[self.assignment.pk]))
        self.assertEqual(resp.status_code, 404)

    def _open_assignment(self):
        """GET страницы домашки — создаёт Submission со статусом not_started."""
        self.client.get(
            reverse('student:assignment_detail', args=[self.assignment.pk]))

    def test_submit_correct_test_answer_auto_reviewed(self):
        self._open_assignment()
        resp = self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            {f'answer_{self.test_problem.pk}': 'б'})   # регистр не важен
        self.assertRedirects(resp, reverse('student:dashboard'))
        sub = Submission.objects.get(student=self.student,
                                     problem=self.test_problem)
        self.assertEqual(sub.status, 'reviewed')
        self.assertEqual(float(sub.feedback.score), 1.0)

    def test_submit_wrong_test_answer_scored_zero(self):
        self._open_assignment()
        self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            {f'answer_{self.test_problem.pk}': 'А'})
        sub = Submission.objects.get(student=self.student,
                                     problem=self.test_problem)
        self.assertEqual(sub.status, 'reviewed')
        self.assertEqual(float(sub.feedback.score), 0.0)

    def test_submit_open_problem_stays_submitted(self):
        """Открытая задача не автопроверяется — ждёт учителя."""
        self._open_assignment()
        self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            {f'text_{self.open_problem.pk}': 'Моё развёрнутое решение.'})
        sub = Submission.objects.get(student=self.student,
                                     problem=self.open_problem)
        self.assertEqual(sub.status, 'submitted')
        self.assertFalse(hasattr(sub, 'feedback'))


class AutoCheckMultiAnswerTests(TestCase):
    """Автопроверка типа «тест: все верные» — сравнение множеств меток."""

    @classmethod
    def setUpTestData(cls):
        cls.teacher = make_user('teacher2', role='teacher')
        cls.student = make_user('student2', role='student')
        cls.problem = make_problem(
            'Выберите все верные утверждения.', answer='а, в',
            problem_type='тест: все верные')
        ProblemPart.objects.create(problem=cls.problem, label='а',
                                   answer='верно', order=1)
        ProblemPart.objects.create(problem=cls.problem, label='б',
                                   answer='неверно', order=2)
        ProblemPart.objects.create(problem=cls.problem, label='в',
                                   answer='верно', order=3)
        cls.assignment = make_assignment(cls.teacher, students=[cls.student],
                                         problems=[cls.problem])

    def test_set_comparison(self):
        self.client.force_login(self.student)
        self.client.get(
            reverse('student:assignment_detail', args=[self.assignment.pk]))
        self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            {f'answer_{self.problem.pk}': 'в, а'})    # порядок не важен
        sub = Submission.objects.get(student=self.student,
                                     problem=self.problem)
        self.assertEqual(float(sub.feedback.score), 1.0)
