"""
Ответы по пунктам: отдельное поле, отдельная проверка, отдельный вердикт.

Проверка цели Части A: задача «а) найдите TC, б) найдите ATC» даёт ученику
ДВА поля, система сама проверяет 5000 и 50, и результат показывается по
пунктам, а не одним вердиктом на всю задачу.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems import part_grading
from problems.assignment_rows import answer_input_name, answer_parts
from problems.models import (
    Assignment, AssignmentItem, CustomProblem, PartAnswer, ProblemPart,
    Submission,
)
from problems.tests.factories import make_problem, make_user


def costs_problem():
    """Та самая задача про издержки, на которой споткнулась ручная проверка."""
    problem = make_problem(
        'Фирма выпускает 100 единиц. Постоянные издержки 2000, переменные 3000.',
        difficulty=2)
    ProblemPart.objects.create(problem=problem, label='а', order=0,
                               statement='Найдите общие издержки (TC).',
                               answer='5000', points=Decimal('1'))
    ProblemPart.objects.create(problem=problem, label='б', order=1,
                               statement='Найдите средние издержки (ATC).',
                               answer='50', points=Decimal('1'))
    return problem


class PartFieldsTests(TestCase):
    """Поля ввода: своё на каждый пункт, одно у задачи без пунктов."""

    def setUp(self):
        self.tutor = make_user('pa_tutor', role='teacher')
        self.student = make_user('pa_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.homework.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, order=0,
            catalog_problem=costs_problem(), points=Decimal('2'))
        self.client.force_login(self.student)

    def test_two_fields_for_two_parts(self):
        parts = answer_parts(self.item)
        self.assertEqual(len(parts), 2)
        body = self.client.get(reverse('student:assignment_detail',
                                       args=[self.homework.pk])).content.decode()
        for part in parts:
            self.assertIn(answer_input_name(self.item, part), body)

    def test_problem_without_parts_is_one_pseudo_part(self):
        """Задача без пунктов — частный случай «один пункт», не вторая ветка."""
        plain = AssignmentItem.objects.create(
            assignment=self.homework, order=1,
            catalog_problem=make_problem('Без пунктов', answer='7'))
        parts = answer_parts(plain)
        self.assertEqual(parts, [None])
        self.assertFalse(part_grading.has_parts(plain))
        body = self.client.get(reverse('student:assignment_detail',
                                       args=[self.homework.pk])).content.decode()
        self.assertIn(answer_input_name(plain), body)

    def test_empty_parts_are_not_asked_about(self):
        """Повисший служебный подпункт («Ответ:» без содержания) — не вопрос."""
        problem = make_problem('С мусорным подпунктом', answer='1')
        ProblemPart.objects.create(problem=problem, label='а', order=0,
                                   statement='', answer='Ответ:')
        item = AssignmentItem.objects.create(
            assignment=self.homework, order=2, catalog_problem=problem)
        self.assertEqual(answer_parts(item), [None])


class PartGradingTests(TestCase):
    """ГЛАВНАЯ ПРОВЕРКА ЦЕЛИ: каждый пункт проверяется сам."""

    def setUp(self):
        self.tutor = make_user('pg_tutor', role='teacher')
        self.student = make_user('pg_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.homework.students.add(self.student)
        self.problem = costs_problem()
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, order=0, catalog_problem=self.problem,
            points=Decimal('2'))
        self.client.force_login(self.student)
        self.parts = answer_parts(self.item)

    def _submit(self, first, second):
        return self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(self.item, self.parts[0]): first,
             answer_input_name(self.item, self.parts[1]): second})

    def test_both_parts_correct(self):
        self._submit('5000', '50')
        submission = Submission.objects.get(student=self.student,
                                            problem_item=self.item)
        self.assertEqual(submission.status, 'reviewed')
        self.assertEqual(float(submission.feedback.score), 2.0)
        answers = {a.part.label: a for a in submission.part_answers.all()}
        self.assertTrue(answers['а'].is_correct)
        self.assertTrue(answers['б'].is_correct)

    def test_partially_correct_gets_partial_score(self):
        """«а) верно, б) неверно» — а не один вердикт на задачу."""
        self._submit('5000', '60')
        submission = Submission.objects.get(student=self.student,
                                            problem_item=self.item)
        self.assertEqual(float(submission.feedback.score), 1.0)
        answers = {a.part.label: a for a in submission.part_answers.all()}
        self.assertTrue(answers['а'].is_correct)
        self.assertFalse(answers['б'].is_correct)
        self.assertIn('а) верно', submission.feedback.comment)
        self.assertIn('б) неверно', submission.feedback.comment)

    def test_numbers_compared_as_fractions_not_floats(self):
        """Проверка через Fraction: «0,1» и «1/10» — одно и то же число."""
        problem = make_problem('Дробный ответ')
        ProblemPart.objects.create(problem=problem, label='а', order=0,
                                   statement='Найдите долю.', answer='1/10')
        item = AssignmentItem.objects.create(assignment=self.homework,
                                             order=5, catalog_problem=problem)
        part = answer_parts(item)[0]
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(item, part): '0,1'})
        answer = PartAnswer.objects.get(submission__problem_item=item)
        self.assertTrue(answer.is_correct)

    def test_wordy_catalog_answer_goes_to_the_teacher(self):
        """Эталон-фраза не сравнивается со строкой ученика.

        В банке «ответ» сплошь и рядом это целая фраза («E ≈ −1,22 (по
        модулю больше 1) — спрос эластичен»). Сравнить её со строкой
        ученика — значит поставить ноль за верный ответ.
        """
        problem = make_problem(
            'Словесный ответ',
            answer='E ≈ −1,22 (по модулю больше 1) — спрос эластичен')
        item = AssignmentItem.objects.create(assignment=self.homework,
                                             order=6, catalog_problem=problem)
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(item): '-1,22'})
        submission = Submission.objects.get(problem_item=item)
        self.assertEqual(submission.status, 'submitted')
        self.assertIsNone(getattr(submission, 'feedback', None))

    def test_unanswered_part_is_zero_not_pending(self):
        self._submit('5000', '')
        submission = Submission.objects.get(student=self.student,
                                            problem_item=self.item)
        self.assertEqual(submission.status, 'reviewed')
        self.assertEqual(float(submission.feedback.score), 1.0)

    def test_points_split_evenly_when_parts_have_none(self):
        problem = make_problem('Без баллов у пунктов')
        for label, answer in (('а', '2'), ('б', '4')):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='Найдите %s.' % label,
                                       answer=answer)
        item = AssignmentItem.objects.create(
            assignment=self.homework, order=7, catalog_problem=problem,
            points=Decimal('10'))
        parts = answer_parts(item)
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(item, parts[0]): '2',
             answer_input_name(item, parts[1]): '9'})
        submission = Submission.objects.get(problem_item=item)
        self.assertEqual(float(submission.feedback.score), 5.0)

    def test_answer_string_is_assembled_from_parts(self):
        """Старые экраны читают `submitted_answer` — строка собирается."""
        self._submit('5000', '50')
        submission = Submission.objects.get(problem_item=self.item)
        self.assertEqual(submission.submitted_answer, 'а) 5000; б) 50')


class PartsDoNotBreakTestsTests(TestCase):
    """Задача БЕЗ пунктов и тесты не сломались."""

    def setUp(self):
        self.tutor = make_user('pn_tutor', role='teacher')
        self.student = make_user('pn_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.homework.students.add(self.student)
        self.client.force_login(self.student)

    def test_catalog_test_still_checked_by_labels(self):
        problem = make_problem('Тест', answer='б',
                               problem_type='тест: один ответ')
        for order, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='вариант', order=order)
        item = AssignmentItem.objects.create(assignment=self.homework,
                                             order=0, catalog_problem=problem)
        self.assertFalse(part_grading.applies(item))
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(item): 'б'})
        submission = Submission.objects.get(problem_item=item)
        self.assertEqual(submission.status, 'reviewed')
        self.assertEqual(float(submission.feedback.score), 1.0)

    def test_custom_open_problem_with_word_answer_still_checked(self):
        """У СВОЕЙ задачи словесный эталон разрешён: его писал человек."""
        problem = CustomProblem.objects.create(
            owner=self.tutor, title='Своя', statement='Вырастет ли выручка?',
            kind=CustomProblem.Kind.OPEN, correct_answer='вырастет')
        item = AssignmentItem.objects.create(assignment=self.homework,
                                             order=1, custom_problem=problem)
        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(item): 'Вырастет'})
        submission = Submission.objects.get(problem_item=item)
        self.assertEqual(submission.status, 'reviewed')
        self.assertGreater(float(submission.feedback.score), 0)


class PartsInExamTests(TestCase):
    """Контрольная: черновик по пунктам, проверка по пунктам."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.tutor = make_user('pe_tutor', role='teacher')
        self.student = make_user('pe_student', role='student')
        now = timezone.now()
        self.exam = Assignment.objects.create(
            name='КР', author=self.tutor, kind=Assignment.Kind.EXAM,
            exam_mode=Assignment.ExamMode.WINDOW,
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=1), deadline=now + timedelta(hours=1))
        self.exam.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.exam, order=0, catalog_problem=costs_problem(),
            points=Decimal('2'))
        self.parts = answer_parts(self.item)
        self.client.force_login(self.student)

    def test_drafts_are_saved_per_part_and_graded_per_part(self):
        import json

        from problems.models import AnswerDraft

        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        for part, value in zip(self.parts, ('5000', '60')):
            response = self.client.post(
                reverse('student:exam_autosave', args=[self.exam.pk]),
                data=json.dumps({'item_id': self.item.pk,
                                 'part_id': part.pk, 'answer': value}),
                content_type='application/json')
            self.assertEqual(response.status_code, 200)
        self.assertEqual(AnswerDraft.objects.filter(
            problem_item=self.item, part__isnull=False).count(), 2)

        # Возврат на страницу показывает оба черновика на своих местах.
        body = self.client.get(
            reverse('student:exam_take', args=[self.exam.pk])).content.decode()
        self.assertIn('value="5000"', body)
        self.assertIn('value="60"', body)

        self.client.post(reverse('student:exam_finish', args=[self.exam.pk]))
        submission = Submission.objects.get(problem_item=self.item)
        answers = {a.part.label: a for a in submission.part_answers.all()}
        self.assertTrue(answers['а'].is_correct)
        self.assertFalse(answers['б'].is_correct)
        self.assertEqual(float(submission.feedback.score), 1.0)

    def test_solution_is_not_wiped_by_saving_an_answer(self):
        """Ответ и решение уезжают разными запросами и не затирают друг друга."""
        import json

        from problems.models import AnswerDraft

        self.client.post(reverse('student:exam_start', args=[self.exam.pk]))
        self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': self.item.pk,
                             'solution': 'ход решения'}),
            content_type='application/json')
        self.client.post(
            reverse('student:exam_autosave', args=[self.exam.pk]),
            data=json.dumps({'item_id': self.item.pk,
                             'part_id': self.parts[0].pk, 'answer': '5000'}),
            content_type='application/json')
        whole = AnswerDraft.objects.get(problem_item=self.item,
                                        part__isnull=True)
        self.assertEqual(whole.solution_draft, 'ход решения')
