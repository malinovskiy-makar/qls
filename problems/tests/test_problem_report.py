# -*- coding: utf-8 -*-
"""«Плохая задача?» — приём жалобы, границы доступа и экраны (15.09.2026).

Таблица «ресурс × роль × действие» — каждая клетка закрыта тестом ниже:
- создать жалобу (POST /api/problem-report/): гость, ученик — можно, с CSRF и
  лимитом частоты; без CSRF — 403; GET — 405;
- автор жалобы — только из сессии: поле «кто» из запроса не принимается;
- читать и разбирать жалобы: только staff через админку; гость и ученик — нет;
- наружу в ответе — только номер жалобы: задача игрового вопроса не уходит
  (анти-чит: до ответа клиент игры `problem_id` не знает).
"""
import io
import json

from django.core.cache import cache
from django.test import Client, TestCase

from problems.models import User
from problems.models_platform import Feedback, ProblemReport
from problems.tests.factories import make_problem

PASSWORD = 'problem-report-probe-2026'
URL = '/api/problem-report/'
BASE_TEMPLATES = (
    'calendar_stub/templates/calendar_stub/calendar.html',
    'catalog/templates/catalog/base.html',
    'calc2/templates/calc2/calc2.html',
    'game/templates/game/game.html',
    'problems/templates/platform/base.html',
    'teacher/templates/teacher/base.html',
    'student/templates/student/base.html',
)


def make_game_question(problem):
    from game.models import GameQuestion
    return GameQuestion.objects.create(
        problem=problem, question_type='single',
        question='Что изучает микроэкономика?', options=['Фирмы', 'Страны'],
        correct_index=0, difficulty=2, topics=[], lang='ru')


class ReportMixin:

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Условие для жалобы.')

    def _post(self, client=None, **over):
        data = {'source': 'catalog', 'kind': 'figure', 'problem_id': self.problem.pk}
        data.update(over)
        return (client or self.client).post(URL, data)


class AcceptTests(ReportMixin, TestCase):
    """Что принимается."""

    def test_guest_can_report_a_catalog_problem(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        report = ProblemReport.objects.get()
        self.assertIsNone(report.user)
        self.assertEqual(report.problem, self.problem)
        self.assertEqual(report.source, 'catalog')
        self.assertEqual(response.json(), {'ok': True, 'id': report.pk})

    def test_author_comes_from_the_session_not_from_the_request(self):
        me = User.objects.create_user(username='rp_me', password=PASSWORD, role='student')
        other = User.objects.create_user(username='rp_other', password=PASSWORD,
                                         role='student')
        self.client.force_login(me)
        self._post(user=other.pk, user_id=other.pk)
        self.assertEqual(ProblemReport.objects.get().user, me)

    def test_game_question_is_resolved_to_its_problem_on_the_server(self):
        question = make_game_question(self.problem)
        response = self._post(source='game', problem_id='', game_question_id=question.pk)
        self.assertEqual(response.status_code, 200)
        report = ProblemReport.objects.get()
        self.assertEqual(report.problem, self.problem)
        self.assertEqual(report.game_question_id, question.pk)
        # ⚠️ Анти-чит: задача игрового вопроса в ответ не уходит.
        self.assertEqual(set(response.json()), {'ok', 'id'})

    def test_generated_question_leaves_problem_empty(self):
        question = make_game_question(None)
        self._post(source='game', problem_id='', game_question_id=question.pk)
        self.assertIsNone(ProblemReport.objects.get().problem)

    def test_other_with_text_is_accepted(self):
        response = self._post(kind='other', text='Ответ не сходится с условием')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProblemReport.objects.get().text, 'Ответ не сходится с условием')


class RefuseTests(ReportMixin, TestCase):
    """Что не принимается — и запись при этом не появляется."""

    def assertRefused(self, response, status=400):
        self.assertEqual(response.status_code, status)
        self.assertEqual(ProblemReport.objects.count(), 0)

    def test_other_without_text_is_400(self):
        response = self._post(kind='other', text='   ')
        self.assertRefused(response)
        self.assertEqual(response.json()['error'], 'Напишите, что не так')

    def test_unknown_kind_is_400(self):
        self.assertRefused(self._post(kind='всё плохо'))

    def test_unknown_source_is_400(self):
        self.assertRefused(self._post(source='admin'))

    def test_without_any_id_is_400(self):
        self.assertRefused(self._post(problem_id=''))

    def test_non_integer_ids_are_400(self):
        self.assertRefused(self._post(problem_id='12abc'))
        self.assertRefused(self._post(problem_id='-3'))
        self.assertRefused(self._post(problem_id='', game_question_id='99999999999'))

    def test_missing_problem_is_400(self):
        self.assertRefused(self._post(problem_id=self.problem.pk + 10_000))

    def test_missing_game_question_is_400(self):
        self.assertRefused(self._post(source='game', problem_id='', game_question_id=987654))

    def test_too_long_text_is_400(self):
        self.assertRefused(self._post(kind='other', text='x' * 2001))

    def test_get_is_405(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_csrf_is_required(self):
        self.assertRefused(self._post(client=Client(enforce_csrf_checks=True)), status=403)

    def test_eleventh_report_in_a_row_is_throttled(self):
        for index in range(10):
            self.assertEqual(self._post().status_code, 200, index)
        self.assertEqual(self._post().status_code, 429)
        self.assertEqual(ProblemReport.objects.count(), 10)


class AdminAccessTests(TestCase):
    """⚠️ ОТРИЦАТЕЛЬНЫЕ: жалобы читает только staff."""

    LIST = '/admin/problems/problemreport/'

    def test_staff_sees_the_list(self):
        staff = User.objects.create_user(username='rp_staff', password=PASSWORD,
                                         is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        ProblemReport.objects.create(source='game', kind='figure',
                                     problem=make_problem('Задача из жалобы.'))
        self.assertEqual(self.client.get(self.LIST).status_code, 200)

    def test_guest_and_student_are_refused(self):
        self.assertIn(self.client.get(self.LIST).status_code, (302, 403))
        student = User.objects.create_user(username='rp_plain', password=PASSWORD,
                                           role='student')
        self.client.force_login(student)
        self.assertIn(self.client.get(self.LIST).status_code, (302, 403))

    def test_feedback_admin_list_still_renders(self):
        """Регрессия: `Feedback.short` однажды уехал в тело `ProblemReport`
        при вставке модели — список обратной связи падал бы на первой записи."""
        staff = User.objects.create_user(username='rp_staff2', password=PASSWORD,
                                         is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        Feedback.objects.create(kind='problem', page_key='game', other_text='Зависло')
        self.assertEqual(self.client.get('/admin/problems/feedback/').status_code, 200)


class ScreenTests(TestCase):
    """Кнопка на странице задачи и в игре, окно — во всех базовых шаблонах."""

    def test_problem_page_has_the_button_with_the_problem_id(self):
        problem = make_problem('Условие с кнопкой жалобы.')
        html = self.client.get('/catalog/problem/%d/' % problem.pk).content.decode('utf-8')
        self.assertTrue('btn-report' in html)
        self.assertTrue('data-problem-id="%d"' % problem.pk in html)

    def test_problem_page_button_is_called_error_in_problem(self):
        """Переименование 17.09.2026; заголовок окна прежний."""
        problem = make_problem('Условие с кнопкой жалобы.')
        html = self.client.get('/catalog/problem/%d/' % problem.pk).content.decode('utf-8')
        self.assertTrue('Ошибка в задаче?' in html, 'нет новой подписи кнопки')
        self.assertFalse('Плохая задача?' in html, 'осталась старая подпись')
        self.assertTrue('Что не так с этой задачей?' in html, 'заголовок окна пропал')

    def test_game_page_has_the_button(self):
        html = self.client.get('/game/').content.decode('utf-8')
        self.assertTrue('id="btn-report"' in html)
        self.assertTrue('data-source="game"' in html)

    def test_partial_is_included_in_every_base_template(self):
        for path in BASE_TEMPLATES:
            src = io.open(path, encoding='utf-8').read()
            self.assertTrue("{% include '_problem_report.html' %}" in src, path)

    def test_kinds_come_from_the_model(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        block = html.split('id="rp-kinds"', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
        self.assertEqual(json.loads(block), [list(pair) for pair in ProblemReport.Kind.choices])
