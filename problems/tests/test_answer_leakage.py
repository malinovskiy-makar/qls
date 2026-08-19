# -*- coding: utf-8 -*-
"""Фаза 3 сессии 3А: правильный ответ не уходит в браузер раньше времени.

⚠️ ПРОВЕРЯЕТСЯ СЫРОЕ ТЕЛО ОТВЕТА, А НЕ ЭКРАН. Кнопка, спрятанная стилями или
скриптом, защитой не является: данные уже в браузере, и достаточно открыть
исходник страницы. Поэтому все проверки здесь ищут строку в
`response.content` целиком — вместе с `data`-атрибутами, встроенным
JavaScript и начальным состоянием виджетов.

Маркеры намеренно сделаны редкими и непохожими на обычный текст: если такая
строка встретилась в теле ответа, она попала туда из поля, а не совпала
случайно с разметкой.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup,
)
from problems.models_platform import SolutionVisibility, TutorNote

User = get_user_model()

PASSWORD = 'proverka12345'

# Маркеры. Каждый обязан быть уникальным и не встречаться в разметке.
SECRET_ANSWER = 'ОТВЕТМАРКЕРЖЖЖ42'
SECRET_SOLUTION = 'РЕШЕНИЕМАРКЕРЩЩЩ99'
SECRET_NOTE = 'ЗАМЕТКАМАРКЕРЫЫЫ77'
SECRET_OVERRIDE = 'ЭТАЛОНМАРКЕРЪЪЪ55'


class AnswerLeakageTestCase(TestCase):
    """Общая заготовка: контрольная, которую ученик ещё не сдал."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('leak_tutor', password=PASSWORD,
                                             role='teacher')
        cls.student = User.objects.create_user('leak_pupil', password=PASSWORD,
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)

        cls.problem = Problem.objects.create(
            statement='Найдите равновесие: $P = 10 - Q$.',
            answer=SECRET_ANSWER,
            solution=SECRET_SOLUTION,
            status=Problem.Status.PUBLISHED,
        )

        cls.exam = Assignment.objects.create(
            name='Контрольная', author=cls.tutor, group=cls.group,
            kind=Assignment.Kind.EXAM)
        cls.exam.students.add(cls.student)
        cls.exam.problems.add(cls.problem)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.exam, catalog_problem=cls.problem, order=0,
            # Решение открывается только после сдачи — самый строгий из
            # режимов, которые ученик может встретить на контрольной.
            solution_visible_after=SolutionVisibility.SUBMIT,
        )
        # Утверждённый эталон ответа: именно его машина сверяет с ответом
        # ученика, и он тоже не должен доехать до браузера.
        cls.item.answer_override = {'': SECRET_OVERRIDE}
        cls.item.save(update_fields=['answer_override'])

        TutorNote.objects.create(tutor=cls.tutor, student=cls.student,
                                 text=SECRET_NOTE)

    def setUp(self):
        self.client = Client()
        self.assertTrue(
            self.client.login(username='leak_pupil', password=PASSWORD))

    # -- помощники --------------------------------------------------------
    def assert_no_secrets(self, response, where):
        """Ни одного маркера в СЫРОМ теле ответа."""
        body = response.content.decode('utf-8', errors='replace')
        for name, marker in (('ответ', SECRET_ANSWER),
                             ('решение', SECRET_SOLUTION),
                             ('заметка репетитора', SECRET_NOTE),
                             ('утверждённый эталон', SECRET_OVERRIDE)):
            self.assertNotIn(
                marker, body,
                '%s: в теле ответа найден %s — он уехал в браузер ученика'
                % (where, name))

    def start_attempt(self):
        """Начать попытку — как это делает ученик кнопкой «Начать»."""
        return self.client.post(
            reverse('student:exam_start', args=[self.exam.pk]))


class ExamInProgressTests(AnswerLeakageTestCase):
    """Незавершённая контрольная не отдаёт ни ответа, ни решения."""

    def test_intro_page_is_clean(self):
        response = self.client.get(
            reverse('student:exam_intro', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_no_secrets(response, 'страница до старта')

    def test_take_page_is_clean(self):
        """Главная проверка фазы: страница прохождения контрольной."""
        self.start_attempt()
        response = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        # Условие на месте — значит страница настоящая, а не редирект.
        self.assertContains(response, 'Найдите равновесие')
        self.assert_no_secrets(response, 'страница прохождения')

    def test_autosave_response_is_clean(self):
        """JSON автосохранения не возвращает ответов.

        Автосохранение уходит по ходу набора и возвращает JSON — самое
        незаметное место, где эталон мог бы просочиться.
        """
        self.start_attempt()
        response = self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data='{"item_id": %d, "answer": "черновик"}' % self.item.pk,
            content_type='application/json')
        self.assertIn(response.status_code, (200, 409))
        self.assert_no_secrets(response, 'JSON автосохранения')

    def test_time_endpoint_is_clean(self):
        self.start_attempt()
        response = self.client.get(
            reverse('student:exam_time', args=[self.exam.pk]))
        self.assert_no_secrets(response, 'JSON таймера')


class HomeworkBeforeSubmitTests(AnswerLeakageTestCase):
    """Обычная домашка до сдачи — то же правило."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.homework = Assignment.objects.create(
            name='Домашка', author=cls.tutor, group=cls.group)
        cls.homework.students.add(cls.student)
        cls.homework.problems.add(cls.problem)
        cls.hw_item = AssignmentItem.objects.create(
            assignment=cls.homework, catalog_problem=cls.problem, order=0,
            solution_visible_after=SolutionVisibility.SUBMIT)
        cls.hw_item.answer_override = {'': SECRET_OVERRIDE}
        cls.hw_item.save(update_fields=['answer_override'])

    def test_assignment_page_is_clean(self):
        response = self.client.get(
            reverse('student:assignment_detail', args=[self.homework.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Найдите равновесие')
        self.assert_no_secrets(response, 'страница домашки до сдачи')

    def test_dashboard_is_clean(self):
        response = self.client.get(reverse('student:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assert_no_secrets(response, 'кабинет ученика')


class SolutionNeverVisibleTests(AnswerLeakageTestCase):
    """Режим «решение не показывается» держится и ПОСЛЕ сдачи."""

    def test_solution_stays_hidden_after_submit(self):
        self.item.solution_visible_after = SolutionVisibility.NEVER
        self.item.save(update_fields=['solution_visible_after'])

        self.start_attempt()
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]))

        response = self.client.get(
            reverse('student:work_review', args=[self.exam.pk]))
        body = response.content.decode('utf-8', errors='replace')
        self.assertNotIn(
            SECRET_SOLUTION, body,
            'режим «никогда» не сработал: решение показано после сдачи')
        self.assertNotIn(
            SECRET_NOTE, body,
            'заметка репетитора доехала до ученика')


class TutorNoteNeverReachesStudentTests(AnswerLeakageTestCase):
    """Заметка репетитора не доходит до ученика ни одним путём."""

    def test_note_absent_on_every_student_screen(self):
        self.start_attempt()
        urls = [
            reverse('student:dashboard'),
            reverse('student:exam_intro', args=[self.exam.pk]),
            reverse('student:exam_take', args=[self.exam.pk]),
            reverse('student:progress'),
            reverse('student_stats'),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url, follow=True)
                body = response.content.decode('utf-8', errors='replace')
                self.assertNotIn(SECRET_NOTE, body,
                                 'заметка репетитора видна на %s' % url)


class AfterSubmitTests(AnswerLeakageTestCase):
    """Контроль: после сдачи разбор ПОКАЗЫВАЕТ то, что должен.

    Без этой проверки фазу можно было бы «закрыть», спрятав всё навсегда, —
    и тесты остались бы зелёными, а продукт сломанным.
    """

    def test_solution_appears_after_submit(self):
        self.start_attempt()
        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]))

        response = self.client.get(
            reverse('student:work_review', args=[self.exam.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8', errors='replace')
        self.assertIn(
            SECRET_SOLUTION, body,
            'после сдачи решение обязано открыться — режим SUBMIT')


class TutorStillSeesEverythingTests(TestCase):
    """Контроль: репетитору решение видно всегда, ограничение не на него."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('leak_tutor2', password=PASSWORD,
                                             role='teacher')
        cls.student = User.objects.create_user('leak_pupil2',
                                               password=PASSWORD,
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Занятие 2',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.problem = Problem.objects.create(
            statement='Условие для репетитора.', answer=SECRET_ANSWER,
            solution=SECRET_SOLUTION, status=Problem.Status.PUBLISHED)
        cls.work = Assignment.objects.create(
            name='Работа', author=cls.tutor, group=cls.group)
        cls.work.students.add(cls.student)
        cls.work.problems.add(cls.problem)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.work, catalog_problem=cls.problem, order=0,
            solution_visible_after=SolutionVisibility.NEVER)

    def test_tutor_sees_solution_even_in_never_mode(self):
        client = Client()
        self.assertTrue(client.login(username='leak_tutor2',
                                     password=PASSWORD))
        response = client.get(
            reverse('teacher:student_work_review_plain',
                    args=[self.work.pk, self.student.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8', errors='replace')
        self.assertIn(SECRET_SOLUTION, body,
                      'репетитор перестал видеть решение — правка зашла '
                      'слишком далеко')
