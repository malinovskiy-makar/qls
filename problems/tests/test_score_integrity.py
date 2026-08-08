"""
Балл обязан соответствовать сравнению ответа с эталоном (фаза 1 сессии фиксов).

⚠️ ЗАЧЕМ ЭТОТ ФАЙЛ. На приёмке владелец увидел «ВЕРНО, 2 из 2» за ответ `30`
на задачу, эталон которой — «E ≈ −1,22 (по модулю больше 1) — спрос
эластичен». Расследование показало, что балл поставлен РУКОЙ (нашим же
браузерным сценарием прошлой сессии), а не машиной, и что машина в этом
случае честно отказывается проверять. Но проверить это утверждение было
нечем: тестов, сверяющих ИМЕННО «ответ против эталона», не было.

Здесь они и лежат: четыре случая сравнения из задания плюс защита балла от
чисел вне диапазона «от нуля до максимума задачи».
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.answer_check import check_open_answer
from problems.assignment_rows import item_max_score
from problems.models import (
    Assignment, AssignmentItem, StudentGroup, Submission, TeacherFeedback,
)
from problems.part_grading import grade_part
from problems.tests.factories import make_problem, make_user

# Тот самый эталон из каталога, на котором всё и вскрылось.
CATALOG_ANSWER = 'E ≈ −1,22 (по модулю больше 1) — спрос эластичен.'


class AnswerAgainstReferenceTests(TestCase):
    """Четыре случая сравнения: совпало, не совпало, пробелы/регистр,
    число против фразы."""

    def test_exact_match_is_correct(self):
        self.assertTrue(check_open_answer('-1,22', '-1,22'))
        self.assertTrue(check_open_answer(CATALOG_ANSWER, CATALOG_ANSWER))

    def test_different_value_is_wrong(self):
        self.assertFalse(check_open_answer('-1,22', '30'))
        self.assertFalse(check_open_answer('-1,22', '-1,23'))

    def test_spaces_and_case_do_not_matter(self):
        """«Спрос ЭЛАСТИЧЕН» и «спрос эластичен» — один и тот же ответ."""
        self.assertTrue(check_open_answer('Спрос эластичен',
                                          '  спрос   ЭЛАСТИЧЕН  '))
        self.assertTrue(check_open_answer(CATALOG_ANSWER,
                                          '  ' + CATALOG_ANSWER.upper() + ' '))

    def test_number_against_phrase_is_wrong(self):
        """ГЛАВНЫЙ СЛУЧАЙ ПРИЁМКИ: ответ `30` против фразы-эталона.

        Не совпадает ни одним знаком, и сравнение обязано сказать «неверно».
        Раньше это утверждение держалось на честном слове.
        """
        self.assertFalse(check_open_answer(CATALOG_ANSWER, '30'))
        self.assertFalse(check_open_answer(CATALOG_ANSWER, ''))
        # И наоборот: число в эталоне против фразы в ответе.
        self.assertFalse(check_open_answer('30', CATALOG_ANSWER))

    def test_minus_sign_variants_are_the_same_number(self):
        """В каталоге минус набран типографским «−», ученик набирает «-»."""
        self.assertTrue(check_open_answer('−1,22', '-1,22'))


class GradeAgainstReferenceTests(TestCase):
    """То же на уровне позиции задания: балл за ответ `30`."""

    def setUp(self):
        self.tutor = make_user('t-score', role='teacher')
        self.problem = make_problem('Эластичность спроса по цене.',
                                    answer=CATALOG_ANSWER, difficulty=2)
        self.assignment = Assignment.objects.create(
            name='Домашка про эластичность', author=self.tutor)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=self.problem, points=Decimal('2'))

    def test_unapproved_catalog_answer_is_not_checked_by_machine(self):
        """Пока эталон не утверждён, машина НЕ ставит балл вовсе."""
        ok, score, maximum = grade_part(self.item, None, '30', 1)
        self.assertIsNone(ok, 'машина не имеет права судить по каталогу')
        self.assertIsNone(score)
        self.assertEqual(maximum, Decimal('2'))

    def test_approved_reference_gives_zero_for_wrong_answer(self):
        """Утвердили эталон как есть → `30` получает НОЛЬ, а не максимум."""
        self.item.answer_override = {'': CATALOG_ANSWER}
        self.item.save(update_fields=['answer_override'])
        ok, score, maximum = grade_part(self.item, None, '30', 1)
        self.assertFalse(ok)
        self.assertEqual(score, Decimal('0'))
        self.assertEqual(maximum, Decimal('2'))

    def test_approved_reference_gives_full_score_for_right_answer(self):
        self.item.answer_override = {'': '-1,22'}
        self.item.save(update_fields=['answer_override'])
        ok, score, _ = grade_part(self.item, None, '−1,22', 1)
        self.assertTrue(ok)
        self.assertEqual(score, Decimal('2'))


class ManualScoreIsClampedTests(TestCase):
    """Балл, введённый руками, обрезается по максимуму — НА СЕРВЕРЕ.

    ⚠️ В боевой базе нашлась оценка «9 из 5»: поле «своё» принимало любое
    число. Разметке (`max=` у поля) верить нельзя — форму можно отправить в
    обход браузера, и балл выше максимума ломает и сумму работы, и проценты.
    """

    def setUp(self):
        self.tutor = make_user('t-clamp', role='teacher')
        self.student = make_user('s-clamp', role='student')
        group = StudentGroup.objects.create(name='Группа', teacher=self.tutor)
        group.students.add(self.student)
        self.group = group
        problem = make_problem('Задача на 5 баллов.', difficulty=2)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=group)
        self.assignment.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0, catalog_problem=problem,
            points=Decimal('5'))
        self.submission = Submission.objects.create(
            student=self.student, assignment=self.assignment,
            problem=problem, problem_item=self.item,
            submitted_answer='123', status='submitted')
        self.client.force_login(self.tutor)

    def _post(self, score):
        return self.client.post(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.submission.pk]),
            {'score': score, 'comment': ''})

    def test_score_above_maximum_is_cut_to_maximum(self):
        self._post('9')
        feedback = TeacherFeedback.objects.get(submission=self.submission)
        self.assertEqual(feedback.score, Decimal('5'),
                         'балл выше максимума задачи попал в базу')

    def test_negative_score_becomes_zero(self):
        self._post('-3')
        feedback = TeacherFeedback.objects.get(submission=self.submission)
        self.assertEqual(feedback.score, Decimal('0'))

    def test_normal_score_passes_through(self):
        self._post('3')
        feedback = TeacherFeedback.objects.get(submission=self.submission)
        self.assertEqual(feedback.score, Decimal('3'))

    def test_maximum_matches_item_points(self):
        self.assertEqual(item_max_score(self.item), Decimal('5'))
