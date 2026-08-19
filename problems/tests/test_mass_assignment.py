# -*- coding: utf-8 -*-
"""Фаза 4 сессии 3А: клиент не назначает то, что назначает сервер.

⚠️ В ПРОЕКТЕ НЕТ НИ ОДНОЙ `ModelForm`. Это проверено обходом всех файлов:
ни `forms.py`, ни `fields = "__all__"`, ни `django import forms` не
встречаются нигде. Все обработчики читают `request.POST` руками и
складывают явный словарь полей.

Для безопасности это скорее хорошо — «взяли форму и сохранили всё, что
пришло» невозможно по устройству. Но означает, что защита держится на
дисциплине каждого обработчика, а не на одном общем механизме. Тесты ниже
и есть замена этому механизму: они фиксируют, какие поля клиент назначать
НЕ может, и краснеют, если однажды сможет.

Проверяется не код ответа, а ЗНАЧЕНИЕ В БАЗЕ после запроса.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission,
)
from problems.models_platform import CustomProblem, UserProfile

User = get_user_model()

PASSWORD = 'proverka12345'


class MassAssignmentFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('ma_tutor', password=PASSWORD,
                                             role='teacher')
        cls.other_tutor = User.objects.create_user('ma_other',
                                                   password=PASSWORD,
                                                   role='teacher')
        cls.student = User.objects.create_user('ma_student',
                                               password=PASSWORD,
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.problem = Problem.objects.create(
            statement='Условие.', status=Problem.Status.PUBLISHED)
        cls.work = Assignment.objects.create(
            name='Работа', author=cls.tutor, group=cls.group)
        cls.work.students.add(cls.student)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.work, catalog_problem=cls.problem, order=0)

    def client_for(self, user):
        client = Client()
        self.assertTrue(client.login(username=user.username,
                                     password=PASSWORD))
        return client


class ProfileFieldsTests(MassAssignmentFixture):
    """Свой профиль не даёт повысить себе права."""

    def test_role_and_staff_flags_are_not_accepted(self):
        client = self.client_for(self.student)
        response = client.post(reverse('profile'), {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            # Всё ниже клиент назначать не вправе.
            'role': 'teacher',
            'is_staff': 'on',
            'is_superuser': 'on',
            'email': 'podmena@example.org',
        })
        self.assertIn(response.status_code, (200, 302))

        self.student.refresh_from_db()
        self.assertEqual(self.student.role, 'student',
                         'роль изменена полем формы')
        self.assertFalse(self.student.is_staff, 'выдан признак персонала')
        self.assertFalse(self.student.is_superuser,
                         'выдан признак суперпользователя')
        self.assertNotEqual(self.student.email, 'podmena@example.org',
                            'почта (она же логин связи) изменена из формы')

    def test_profile_role_is_not_accepted_either(self):
        """Роль в профиле — тоже не поле формы."""
        client = self.client_for(self.student)
        client.post(reverse('profile'), {
            'first_name': 'Имя', 'last_name': 'Фамилия',
            'role': UserProfile.Role.TUTOR,
        })
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.role, UserProfile.Role.STUDENT,
                         'роль профиля изменена полем формы')


class CustomProblemOwnerTests(MassAssignmentFixture):
    """Владелец своей задачи берётся из request.user, а не из формы."""

    def test_owner_field_from_client_is_ignored(self):
        client = self.client_for(self.tutor)
        response = client.post(reverse('teacher:problem_new'), {
            'kind': CustomProblem.Kind.OPEN,
            'statement': 'Моя задача',
            'correct_answer': '42',
            # Подделка: пробуем записать задачу на чужого.
            'owner': self.other_tutor.pk,
            'owner_id': self.other_tutor.pk,
        })
        self.assertIn(response.status_code, (200, 302))

        created = CustomProblem.objects.filter(
            statement='Моя задача').first()
        self.assertIsNotNone(created, 'задача не создалась — проверять нечего')
        self.assertEqual(created.owner_id, self.tutor.pk,
                         'владелец взят из формы, а не из request.user')

    def test_editing_someone_elses_problem_is_refused(self):
        alien = CustomProblem.objects.create(
            owner=self.other_tutor, statement='Чужая задача',
            kind=CustomProblem.Kind.OPEN)
        client = self.client_for(self.tutor)
        response = client.post(
            reverse('teacher:problem_edit', args=[alien.pk]), {
                'kind': CustomProblem.Kind.OPEN,
                'statement': 'ПЕРЕПИСАНО',
                'correct_answer': '0',
            })
        self.assertIn(response.status_code, (403, 404))
        alien.refresh_from_db()
        self.assertEqual(alien.statement, 'Чужая задача',
                         'чужая задача переписана')


class SubmissionStateTests(MassAssignmentFixture):
    """Переходы состояний: назад ходить нельзя."""

    def setUp(self):
        self.submission = Submission.objects.create(
            student=self.student, assignment=self.work, problem=self.problem,
            problem_item=self.item, submitted_answer='первый ответ',
            status='reviewed')

    def test_reviewed_cannot_be_resubmitted(self):
        """Проверенную работу нельзя пере-сдать и затереть ответ.

        Иначе ученик, увидев оценку, переписывал бы ответ и отправлял
        заново — а вместе с ответом слетал бы и вердикт репетитора.
        """
        client = self.client_for(self.student)
        client.post(reverse('student:submit_assignment', args=[self.work.pk]), {
            'answer_item_%d' % self.item.pk: 'подменённый ответ',
            # Прямая подмена состояния, на случай если его когда-нибудь
            # начнут читать из формы.
            'status': 'draft',
        })

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, 'reviewed',
                         'состояние откатилось назад')
        self.assertEqual(self.submission.submitted_answer, 'первый ответ',
                         'ответ переписан после проверки')

    def test_student_cannot_set_own_score(self):
        """Балл ученик себе не ставит ни полем, ни эндпоинтом."""
        client = self.client_for(self.student)
        response = client.post(
            reverse('teacher:api_grade_submission'),
            data='{"submission_id": %d, "score": 100}' % self.submission.pk,
            content_type='application/json')
        self.assertIn(response.status_code, (302, 403, 404))
        self.submission.refresh_from_db()
        self.assertFalse(
            hasattr(self.submission, 'feedback')
            and self.submission.feedback.score == 100,
            'ученик выставил себе балл')


class AssignmentTargetingTests(MassAssignmentFixture):
    """Ученик не выдаёт работу сам себе и не подписывается на чужую."""

    def test_student_cannot_add_himself_to_someone_elses_work(self):
        alien_group = StudentGroup.objects.create(name='Чужое занятие',
                                                  teacher=self.other_tutor)
        alien_work = Assignment.objects.create(
            name='Чужая работа', author=self.other_tutor, group=alien_group)

        client = self.client_for(self.student)
        # Единственная точка создания работы в проекте — этот адрес.
        # ⚠️ Ученик обязан получить отказ ещё на роли.
        response = client.post(reverse('teacher:assignment_create'), {
            'name': 'Подделка',
            'students': self.student.pk,
            'group': alien_group.pk,
        })
        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            alien_work.students.filter(pk=self.student.pk).exists(),
            'ученик подписался на чужую работу')
        self.assertFalse(
            Assignment.objects.filter(name='Подделка').exists(),
            'ученик создал работу')

    def test_tutor_cannot_target_a_foreign_group(self):
        """Репетитор не выдаёт работу в чужое занятие через `?group=`."""
        alien_group = StudentGroup.objects.create(name='Чужое занятие 2',
                                                  teacher=self.other_tutor)
        client = self.client_for(self.tutor)
        response = client.get(
            reverse('teacher:work_pick') + '?group=%d' % alien_group.pk)
        # Отказ приходит сразу и уводит на «Ученики», а не показывает экран
        # с чужим занятием в крошке.
        self.assertIn(response.status_code, (302, 403, 404))
        if response.status_code == 302:
            self.assertIn(reverse('teacher:groups'), response['Location'])


class ItemPointsTests(MassAssignmentFixture):
    """Максимальный балл позиции — не произвольное число от клиента."""

    def test_negative_points_are_refused(self):
        client = self.client_for(self.tutor)
        before = self.item.points
        response = client.post(
            reverse('teacher:api_item_points'),
            data='{"item_id": %d, "points": -5}' % self.item.pk,
            content_type='application/json')
        self.assertIn(response.status_code, (400, 403))
        self.item.refresh_from_db()
        self.assertEqual(self.item.points, before,
                         'принят отрицательный максимальный балл')

    def test_owner_can_set_points(self):
        """Контроль: своему репетитору балл править по-прежнему можно."""
        client = self.client_for(self.tutor)
        response = client.post(
            reverse('teacher:api_item_points'),
            data='{"item_id": %d, "points": 7}' % self.item.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(float(self.item.points), 7.0)
