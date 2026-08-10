"""
Оценка ПРЯМО В РАЗБОРЕ РАБОТЫ глазами ученика (п. 14.4).

Раньше режим был только для чтения, и репетитор, увидевший там ошибку
оценки, уходил на другой экран, искал ту же задачу и возвращался.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission,
    TeacherFeedback, User,
)
from problems.work_review import score_presets


def make_user(username, role='teacher'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = role
    user.save()
    return user


class InlineGradeTests(TestCase):

    def setUp(self):
        self.tutor = make_user('eg_tutor')
        self.student = make_user('eg_student', 'student')
        self.group = StudentGroup.objects.create(name='Группа оценки',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='Работа', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.problem = Problem.objects.create(
            title='Задача', statement='Условие',
            status=Problem.Status.PUBLISHED)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0, catalog_problem=self.problem,
            points=Decimal('5'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work, problem=self.problem,
            problem_item=self.item, submitted_answer='ответ',
            status='submitted')
        self.client.force_login(self.tutor)

    def url(self):
        return reverse('teacher:student_work_review',
                       args=[self.group.pk, self.work.pk, self.student.pk])

    def test_tutor_sees_the_grading_block(self):
        body = self.client.get(self.url()).content.decode()
        self.assertIn('class="gi-block"', body)
        self.assertIn('Сохранить оценку', body)

    def test_student_does_not_see_it(self):
        """Ученику блок оценивания не показываем — он не ставит себе балл."""
        self.client.force_login(self.student)
        body = self.client.get(
            reverse('student:work_review', args=[self.work.pk])).content.decode()
        # ⚠️ Ищем РАЗМЕТКУ, а не имя класса: правила стилей на странице есть
        # у всех, и проверка «нет слова gi-block» покраснела бы на CSS.
        self.assertNotIn('class="gi-block"', body)
        self.assertNotIn('Сохранить оценку', body)

    def test_everything_is_collapsed_for_the_tutor(self):
        """⚠️ У репетитора при открытии всё свёрнуто (п. 14.4)."""
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('1'),
                                       reviewed_by=None)
        body = self.client.get(self.url()).content.decode()
        # Раскрытая задача несёт атрибут `open` у <details>.
        self.assertIn('class="wr-item', body)
        self.assertNotIn('0}"\n         open>', body)
        self.assertNotIn('data-attention="1"\n         open>', body)

    def test_student_still_sees_errors_expanded(self):
        """У ученика прежнее поведение: задачи с ошибкой раскрыты."""
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('0'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.student)
        body = self.client.get(
            reverse('student:work_review', args=[self.work.pk])).content.decode()
        self.assertIn('open>', body)

    def test_grade_is_saved(self):
        response = self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': '3', 'comment': 'почти',
        })
        self.assertEqual(response.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(float(self.sub.feedback.score), 3.0)
        self.assertEqual(self.sub.feedback.comment, 'почти')
        self.assertEqual(self.sub.feedback.reviewed_by_id, self.tutor.pk)
        self.assertEqual(self.sub.status, 'reviewed')

    def test_score_is_clamped_by_the_server(self):
        """⚠️ Балл обрезает СЕРВЕР: в базе однажды нашлась оценка «9 из 5»."""
        response = self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': '99', 'comment': '',
        })
        self.assertEqual(response.json()['score'], 5.0)
        self.sub.refresh_from_db()
        self.assertEqual(float(self.sub.feedback.score), 5.0)

    def test_negative_score_becomes_zero(self):
        self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': '-3', 'comment': '',
        })
        self.sub.refresh_from_db()
        self.assertEqual(float(self.sub.feedback.score), 0.0)

    def test_comma_is_accepted(self):
        """Репетитор пишет «1,5» — русская запятая не должна давать ноль."""
        self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': '1,5', 'comment': '',
        })
        self.sub.refresh_from_db()
        self.assertEqual(float(self.sub.feedback.score), 1.5)

    def test_junk_is_rejected_without_writing(self):
        response = self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': 'абв', 'comment': '',
        })
        self.assertEqual(response.status_code, 400)
        self.sub.refresh_from_db()
        self.assertIsNone(getattr(self.sub, 'feedback', None))

    def test_someone_elses_work_is_not_gradable(self):
        stranger = make_user('eg_stranger')
        self.client.force_login(stranger)
        response = self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': '5', 'comment': '',
        })
        self.assertEqual(response.status_code, 404)

    def test_locked_points_do_not_block_grading(self):
        """⚠️ `points_locked` — про МАКСИМУМ позиции, а не про оценку.

        Проверять работы после первой сдачи это и есть обычный ход дела.
        """
        self.assertTrue(self.work.points_locked)
        response = self.client.post(reverse('teacher:api_grade_submission'), {
            'submission': self.sub.pk, 'score': '4', 'comment': '',
        })
        self.assertEqual(response.status_code, 200)


class PresetsSinglePointTests(TestCase):
    """Пресеты балла считает ОДНА функция на оба экрана."""

    def test_review_screen_delegates(self):
        from teacher.views import _score_presets

        self.assertEqual(_score_presets(5), score_presets(5))

    def test_half_is_not_rounded(self):
        values = [p['value'] for p in score_presets(3)]
        self.assertEqual(values, ['0', '1.5', '3'])

    def test_label_uses_a_comma_and_value_uses_a_dot(self):
        """⚠️ Значение уезжает в `input[type=number]` — запятая дала бы ноль."""
        half = score_presets(3)[1]
        self.assertEqual(half['label'], '1,5')
        self.assertEqual(half['value'], '1.5')

    def test_zero_max_gives_a_single_button(self):
        self.assertEqual([p['value'] for p in score_presets(0)], ['0'])
