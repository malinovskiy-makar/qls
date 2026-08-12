"""
Тесты панели учителя: доступ, список решений, проверка работы,
обновление прогресса ученика.

⚠️ Вкладка «Проверка» (дашборд входящих) удалена в сессии 9. Адрес
`teacher:dashboard` остался редиректом на список учеников — после входа
преподаватель попадает ровно на него. Проверки доступа переехали на живой
экран, а проверка содержимого дашборда снята: содержимого больше нет.
"""

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentTopicProgress, Submission, TeacherFeedback
from problems.tests.factories import (
    make_assignment, make_problem, make_submission, make_topic, make_user,
)


class TeacherAccessTests(TestCase):
    def test_cabinet_requires_login(self):
        resp = self.client.get(reverse('teacher:groups'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_student_gets_403(self):
        student = make_user('s1', role='student')
        self.client.force_login(student)
        resp = self.client.get(reverse('teacher:groups'))
        self.assertEqual(resp.status_code, 403)

    def test_cabinet_root_leads_to_students(self):
        """Корень кабинета — вход преподавателя, своего экрана у него нет."""
        teacher = make_user('t_root', role='teacher')
        self.client.force_login(teacher)
        resp = self.client.get(reverse('teacher:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('teacher:groups'))


class TeacherPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = make_user('teacher', role='teacher')
        cls.student = make_user('student', role='student')
        cls.topic = make_topic('Монополия и ценовая дискриминация')
        cls.problem = make_problem('Задача про монополию.', topic=cls.topic)
        cls.assignment = make_assignment(cls.teacher, students=[cls.student],
                                         problems=[cls.problem])
        cls.submission = make_submission(
            cls.student, cls.assignment, cls.problem,
            status='submitted', solution_text='Решение ученика.')

    def setUp(self):
        self.client.force_login(self.teacher)

    def test_students_screen_shows_pending_count(self):
        """Сколько работ ждёт проверки — теперь на экране «Ученики».

        Раньше это проверялось на дашборде входящих; вкладка удалена, а
        счётчик остался — он же и стал единым для всего кабинета (фаза 4).
        """
        from problems.models import StudentGroup

        group = StudentGroup.objects.create(name='Группа',
                                            teacher=self.teacher)
        group.students.add(self.student)
        self.assignment.group = group
        self.assignment.save()

        resp = self.client.get(reverse('teacher:groups'))
        self.assertEqual(resp.status_code, 200)
        card = next(c for c in resp.context['cards']
                    if c['group'].pk == group.pk)
        self.assertEqual(card['pending'], 1)

    def test_assignment_detail_lists_submissions(self):
        resp = self.client.get(
            reverse('teacher:assignment_detail', args=[self.assignment.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_foreign_assignment_404(self):
        other = make_user('other_teacher', role='teacher')
        self.client.force_login(other)
        resp = self.client.get(
            reverse('teacher:assignment_detail', args=[self.assignment.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_review_form_opens(self):
        resp = self.client.get(
            reverse('teacher:review_submission', args=[self.submission.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_review_creates_feedback_and_updates_progress(self):
        resp = self.client.post(
            reverse('teacher:review_submission', args=[self.submission.pk]),
            {'score': '4.5', 'comment': 'Хорошо, но есть неточность.'})
        self.assertRedirects(
            resp,
            reverse('teacher:assignment_detail', args=[self.assignment.pk]))

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, 'reviewed')

        feedback = TeacherFeedback.objects.get(submission=self.submission)
        self.assertEqual(float(feedback.score), 4.5)
        self.assertEqual(feedback.reviewed_by, self.teacher)

        progress = StudentTopicProgress.objects.get(
            student=self.student, topic=self.topic)
        self.assertEqual(progress.level, 90)   # 4.5 из 5.0 → 90%

    def test_foreign_teacher_cannot_review(self):
        other = make_user('other_teacher2', role='teacher')
        self.client.force_login(other)
        resp = self.client.post(
            reverse('teacher:review_submission', args=[self.submission.pk]),
            {'score': '1', 'comment': ''})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(
            TeacherFeedback.objects.filter(submission=self.submission).exists())
