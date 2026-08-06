"""
Утверждение ответов репетитором — что именно проверяет машина.

⚠️ ЗАКРЫВАЕМЫЙ РИСК. Автопроверка каталожной задачи шла по признаку «в поле
ответа лежит нечто похожее на число». В банке этим «числом» регулярно
оказывается промежуточный результат из решения или год из условия — и
ученик получает ноль за верный ответ. Теперь машина проверяет ТОЛЬКО то,
что подтвердил живой человек, а неутверждённая задача честно уходит ему же.

Три случая из задания: ответ в каталоге есть (утвердить или заменить);
ответа нет (вписать свой — задача становится автопроверяемой); репетитор
ничего не сделал (ручная проверка).
"""
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, Problem, ProblemPart, StudentGroup, Submission,
)
from problems.tests.factories import make_problem, make_user


def numeric_problem(answer='42'):
    return make_problem('Сколько будет?', answer=answer, difficulty=2)


def parts_problem():
    problem = make_problem('Фирма выпускает 100 единиц.', difficulty=2)
    ProblemPart.objects.create(problem=problem, label='а', order=0,
                               statement='Найдите TC.', answer='5000')
    ProblemPart.objects.create(problem=problem, label='б', order=1,
                               statement='Найдите ATC.', answer='50')
    return problem


class ApprovalGateTests(TestCase):
    """Без утверждения — ручная проверка. С утверждением — машина."""

    def setUp(self):
        self.tutor = make_user('ap_tutor', role='teacher')
        self.student = make_user('ap_student', role='student')
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.work.students.add(self.student)
        self.client.force_login(self.student)

    def _item(self, problem, **kwargs):
        kwargs.setdefault('points', Decimal('2'))
        return AssignmentItem.objects.create(
            assignment=self.work, catalog_problem=problem,
            order=self.work.items.count(), **kwargs)

    def _submit(self, item, answer):
        from problems.assignment_rows import answer_input_name, answer_parts

        data = {}
        for part in answer_parts(item):
            data[answer_input_name(item, part)] = answer
        self.client.post(reverse('student:submit_assignment',
                                 args=[self.work.pk]), data)
        return Submission.objects.get(student=self.student, problem_item=item)

    def test_case_three_no_approval_goes_to_the_human(self):
        """Репетитор ничего не сделал — балл машина НЕ ставит."""
        item = self._item(numeric_problem('42'))
        sub = self._submit(item, '42')
        self.assertEqual(sub.status, 'submitted')
        self.assertIsNone(getattr(sub, 'feedback', None))

    def test_case_one_approved_catalog_answer_is_checked(self):
        item = self._item(numeric_problem('42'), answer_override={'': '42'})
        sub = self._submit(item, '42')
        self.assertEqual(sub.status, 'reviewed')
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('2'))

    def test_case_one_replaced_answer_wins_over_catalog(self):
        """Заменённый ответ главнее каталожного, каталог не тронут."""
        problem = numeric_problem('42')
        item = self._item(problem, answer_override={'': '7'})
        self.assertEqual(Decimal(str(self._submit(item, '7').feedback.score)),
                         Decimal('2'))
        problem.refresh_from_db()
        self.assertEqual(problem.answer, '42', 'каталог изменён — так нельзя')

    def test_case_two_problem_without_answer_becomes_checkable(self):
        """Прямая просьба человека: вписать ответ задаче, у которой его нет."""
        item = self._item(numeric_problem(''))
        self.assertFalse(item.answers_approved)
        item.answer_override = {'': '15'}
        item.save()
        sub = self._submit(item, '15')
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('2'))

    def test_word_answer_is_allowed_after_approval(self):
        """Словесный эталон разрешён — за него отвечает утвердивший."""
        item = self._item(numeric_problem('вырастет'),
                          answer_override={'': 'вырастет'})
        sub = self._submit(item, 'Вырастет')
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('2'))

    def test_word_answer_without_approval_is_not_auto_checked(self):
        item = self._item(numeric_problem('вырастет'))
        sub = self._submit(item, 'вырастет')
        self.assertIsNone(getattr(sub, 'feedback', None))

    def test_parts_are_approved_separately(self):
        problem = parts_problem()
        part_a, part_b = list(problem.parts.order_by('order'))
        item = self._item(problem,
                          answer_override={str(part_a.pk): '5000',
                                           str(part_b.pk): '50'})
        from problems.assignment_rows import answer_input_name

        self.client.post(reverse('student:submit_assignment',
                                 args=[self.work.pk]),
                         {answer_input_name(item, part_a): '5000',
                          answer_input_name(item, part_b): '999'})
        sub = Submission.objects.get(student=self.student, problem_item=item)
        # «а» верно, «б» нет — половина балла, задача проверена машиной.
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('1'))

    def test_partial_approval_leaves_the_task_to_the_human(self):
        """Утверждён один пункт из двух — задача целиком ждёт человека."""
        problem = parts_problem()
        part_a, _ = list(problem.parts.order_by('order'))
        item = self._item(problem, answer_override={str(part_a.pk): '5000'})
        sub = self._submit(item, '5000')
        self.assertIsNone(getattr(sub, 'feedback', None))

    # -- утверждение не требуется там, где эталон и так надёжен -----------

    def test_test_needs_no_approval(self):
        problem = Problem.objects.create(
            statement='Что будет со спросом?', answer='б',
            problem_type='тест: один ответ',
            status=Problem.Status.PUBLISHED)
        ProblemPart.objects.create(problem=problem, label='а', order=0,
                                   statement='Влево')
        ProblemPart.objects.create(problem=problem, label='б', order=1,
                                   statement='Вправо')
        item = self._item(problem)
        self.assertTrue(item.answers_approved)
        sub = self._submit(item, 'б')
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('2'))

    def test_custom_problem_needs_no_approval(self):
        from problems.models import CustomProblem

        problem = CustomProblem.objects.create(
            owner=self.tutor, statement='Своя задача', correct_answer='12',
            kind=CustomProblem.Kind.OPEN)
        item = AssignmentItem.objects.create(
            assignment=self.work, custom_problem=problem, order=0,
            points=Decimal('2'))
        self.assertTrue(item.answers_approved)


class ApprovalApiTests(TestCase):
    """Эндпоинт утверждения: права, чужие ключи, снятие."""

    def setUp(self):
        self.tutor = make_user('apa_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, catalog_problem=numeric_problem('42'),
            order=0, points=Decimal('1'))
        self.url = reverse('teacher:api_item_answers')
        self.client.force_login(self.tutor)

    def _post(self, payload):
        return self.client.post(self.url, json.dumps(payload),
                                content_type='application/json')

    def test_approve_and_clear(self):
        response = self._post({'item_id': self.item.pk,
                               'answers': {'': '42'}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['approved'])
        self.item.refresh_from_db()
        self.assertEqual(self.item.answer_override, {'': '42'})

        self._post({'item_id': self.item.pk, 'clear': True})
        self.item.refresh_from_db()
        self.assertIsNone(self.item.answer_override)
        self.assertFalse(self.item.answers_approved)

    def test_empty_answer_is_not_an_approval(self):
        """Пустая строка — не утверждение, а «ничего не вписал»."""
        self._post({'item_id': self.item.pk, 'answers': {'': '   '}})
        self.item.refresh_from_db()
        self.assertIsNone(self.item.answer_override)

    def test_foreign_keys_are_dropped(self):
        """Ключ чужого пункта не должен оседать невидимой записью."""
        self._post({'item_id': self.item.pk,
                    'answers': {'': '42', '999999': 'мусор'}})
        self.item.refresh_from_db()
        self.assertEqual(self.item.answer_override, {'': '42'})

    def test_stranger_tutor_is_refused(self):
        self.client.force_login(make_user('apa_other', role='teacher'))
        response = self._post({'item_id': self.item.pk,
                               'answers': {'': 'взлом'}})
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.answer_override)


class ApprovalScreenTests(TestCase):
    """Задача без утверждения ЗАМЕТНА на странице задания."""

    def setUp(self):
        self.tutor = make_user('aps_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, catalog_problem=numeric_problem('42'),
            order=0, points=Decimal('1'))
        self.client.force_login(self.tutor)

    def _body(self):
        return self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])).content.decode()

    def test_unapproved_item_is_marked(self):
        body = self._body()
        self.assertIn('уйдёт на ручную проверку', body)
        self.assertIn('ap-off', body)

    def test_catalog_answer_is_offered_as_a_hint(self):
        self.assertIn('из каталога: 42', self._body())

    def test_approved_item_says_so(self):
        self.item.answer_override = {'': '42'}
        self.item.save()
        body = self._body()
        self.assertIn('проверяется автоматически', body)
        self.assertIn('ap-badge ap-on', body)
        self.assertNotIn('ap-badge ap-off', body)
