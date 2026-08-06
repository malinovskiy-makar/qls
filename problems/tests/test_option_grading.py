"""
Начисление баллов за тесты с вариантами — самый дорогой класс ошибок.

⚠️ ЧТО ЗДЕСЬ ЗАКРЫВАЕТСЯ. Ученик отметил ровно верный набор вариантов и
получил «ЧАСТИЧНО», балл «1 / 3 б.» — при том что в той же карточке стояло
«Верно ✓». Причина: `auto_check_submission` ставила жёстко зашитую единицу,
а максимум читался из `AssignmentItem.points`. Несправедливая оценка убивает
доверие быстрее падения страницы, поэтому проверяются ВСЕ четыре исхода
(полный набор / неполный / с лишним / пустой) на КАЖДОМ из трёх видов теста.

Правило начисления — «всё или ничего», объяснено в `problems/answer_check.py`.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.answer_check import check_catalog_test
from problems.assignment_rows import (
    ANSWER_CHECKBOX, ANSWER_RADIO, item_answer_form, item_max_score,
)
from problems.models import (
    Assignment, AssignmentItem, CustomProblem, CustomProblemOption, Problem,
    ProblemPart, Submission,
)
from problems.tests.factories import make_user
from problems.work_review import work_summary


def catalog_test(ptype, statement, answer, options):
    """Каталожный тест: подпункты играют роль вариантов ответа."""
    problem = Problem.objects.create(
        statement=statement, answer=answer, problem_type=ptype,
        status=Problem.Status.PUBLISHED, difficulty=2)
    for order, (label, text, part_answer) in enumerate(options):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement=text, answer=part_answer,
                                   order=order)
    return problem


def multi_problem():
    """«Все верные»: три верных варианта из четырёх, задача ценой 3 балла."""
    return catalog_test(
        'тест: все верные', 'Какие факторы сдвигают кривую предложения?',
        'а, б, г',
        [('а', 'Технология производства', 'верно'),
         ('б', 'Цены на ресурсы', 'верно'),
         ('в', 'Мода на товар', 'неверно'),
         ('г', 'Налог на производителя', 'верно')])


def statements_problem():
    """«Несколько утверждений»: два верных из трёх, задача ценой 2 балла."""
    return catalog_test(
        'тест: несколько утверждений',
        'Отметьте верные утверждения о совершенной конкуренции.', 'а, в',
        [('а', 'Фирма принимает цену как данность.', 'верно'),
         ('б', 'Фирма может назначить любую цену.', 'неверно'),
         ('в', 'В долгосрочном периоде прибыль стремится к нулю.', 'верно')])


def single_problem():
    """«Один ответ»: ровно один верный вариант."""
    return catalog_test(
        'тест: один ответ', 'Доходы выросли. Что будет со спросом?', 'б',
        [('а', 'Сдвинется влево', ''),
         ('б', 'Сдвинется вправо', ''),
         ('в', 'Станет вертикальной', '')])


class OptionScoringTests(TestCase):
    """Балл за тест = ПОЛНЫЙ балл задачи, а не единица."""

    def setUp(self):
        self.tutor = make_user('og_tutor', role='teacher')
        self.student = make_user('og_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ с тестами',
                                                  author=self.tutor)
        self.homework.students.add(self.student)
        self.client.force_login(self.student)

    def _item(self, problem, points):
        return AssignmentItem.objects.create(
            assignment=self.homework, catalog_problem=problem,
            order=self.homework.items.count(), points=Decimal(str(points)))

    def _submit(self, item, values):
        """Сдать один ответ через боевой приём домашки и вернуть решение."""
        from problems.assignment_rows import answer_input_name

        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(item): values})
        return Submission.objects.get(student=self.student, problem_item=item)

    def _grade_empty(self, item):
        """Пустой ответ приходит не с домашки, а с контрольной.

        Домашка пустое поле просто не принимает («нет новых ответов»), а
        контрольная сдаёт ВСЕ позиции разом, в том числе нетронутые — и вот
        там пустой ответ обязан дать ноль, а не «ждёт проверки».
        """
        from problems.assignment_rows import get_or_create_submission
        from student.views import grade_submission

        sub = get_or_create_submission(self.student, self.homework, item)
        sub.submitted_answer = ''
        sub.status = 'submitted'
        sub.save()
        grade_submission(sub, item, values={})
        sub.refresh_from_db()
        return sub

    # -- главный случай: полный верный набор даёт полный балл --------------

    def test_full_correct_set_gives_full_score(self):
        item = self._item(multi_problem(), 3)
        sub = self._submit(item, ['а', 'б', 'г'])
        self.assertEqual(sub.status, 'reviewed')
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('3'))
        self.assertIn('Верно', sub.feedback.comment)

    def test_verdict_and_score_do_not_contradict(self):
        """Карточка «Верно ✓» и состояние «ЧАСТИЧНО» одновременно — запрещено."""
        item = self._item(multi_problem(), 3)
        self._submit(item, ['а', 'б', 'г'])
        summary = work_summary(self.homework, self.student)
        row = summary['rows'][0]
        self.assertEqual(row['state'], 'correct')
        self.assertEqual(row['score'], row['max_points'])

    def test_two_correct_of_three_statements(self):
        """Второй случай с ручной проверки: «а, в» из трёх утверждений."""
        item = self._item(statements_problem(), 2)
        sub = self._submit(item, ['а', 'в'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('2'))

    # -- остальные три исхода ---------------------------------------------

    def test_incomplete_set_scores_zero(self):
        item = self._item(multi_problem(), 3)
        sub = self._submit(item, ['а', 'б'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('0'))
        self.assertIn('Неверно', sub.feedback.comment)

    def test_extra_option_scores_zero(self):
        item = self._item(multi_problem(), 3)
        sub = self._submit(item, ['а', 'б', 'в', 'г'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('0'))

    def test_empty_answer_scores_zero(self):
        item = self._item(multi_problem(), 3)
        sub = self._grade_empty(item)
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('0'))

    # -- одиночный выбор ---------------------------------------------------

    def test_single_choice_full_and_wrong(self):
        item = self._item(single_problem(), 4)
        sub = self._submit(item, ['б'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('4'))
        wrong_item = self._item(single_problem(), 4)
        wrong = self._submit(wrong_item, ['а'])
        self.assertEqual(Decimal(str(wrong.feedback.score)), Decimal('0'))

    # -- порядок отметок не влияет ----------------------------------------

    def test_order_of_marks_does_not_matter(self):
        """«г, а, б» — тот же набор, что «а, б, г»."""
        item = self._item(multi_problem(), 3)
        sub = self._submit(item, ['г', 'а', 'б'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('3'))

    # -- балл не задан -----------------------------------------------------

    def test_missing_points_means_one(self):
        item = AssignmentItem.objects.create(
            assignment=self.homework, catalog_problem=multi_problem(),
            order=99, points=None)
        self.assertEqual(item_max_score(item), Decimal('1'))
        sub = self._submit(item, ['а', 'б', 'г'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('1'))


class CustomOptionScoringTests(TestCase):
    """Своя задача репетитора — те же четыре исхода."""

    def setUp(self):
        self.tutor = make_user('og_tutor2', role='teacher')
        self.student = make_user('og_student2', role='student')
        self.homework = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.homework.students.add(self.student)
        self.client.force_login(self.student)
        self.problem = CustomProblem.objects.create(
            owner=self.tutor, statement='Отметьте верные утверждения.',
            kind=CustomProblem.Kind.MULTIPLE)
        self.options = [
            CustomProblemOption.objects.create(problem=self.problem, order=i,
                                               text=text, is_correct=ok)
            for i, (text, ok) in enumerate(
                [('Первое', True), ('Второе', False), ('Третье', True)])]
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, custom_problem=self.problem, order=0,
            points=Decimal('5'))

    def _submit(self, values):
        from problems.assignment_rows import answer_input_name

        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(self.item): values})
        return Submission.objects.get(student=self.student,
                                      problem_item=self.item)

    def test_full_set(self):
        sub = self._submit([str(self.options[0].pk), str(self.options[2].pk)])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('5'))

    def test_incomplete_set(self):
        sub = self._submit([str(self.options[0].pk)])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('0'))

    def test_extra_option(self):
        sub = self._submit([str(o.pk) for o in self.options])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('0'))

    def test_empty(self):
        from problems.assignment_rows import get_or_create_submission
        from student.views import grade_submission

        sub = get_or_create_submission(self.student, self.homework, self.item)
        sub.submitted_answer = ''
        sub.status = 'submitted'
        sub.save()
        grade_submission(sub, self.item, values={})
        sub.refresh_from_db()
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('0'))


class CheckerContractTests(TestCase):
    """Чистая проверка `check_catalog_test` без экранов и HTTP."""

    def test_multiple_is_all_or_nothing(self):
        problem = multi_problem()
        self.assertEqual(check_catalog_test(problem, 'а, б, г'), (True, True))
        self.assertEqual(check_catalog_test(problem, 'а, б'), (True, False))
        self.assertEqual(check_catalog_test(problem, 'а, б, в, г'),
                         (True, False))
        self.assertEqual(check_catalog_test(problem, ''), (True, False))

    def test_labels_are_case_and_bracket_insensitive(self):
        problem = single_problem()
        for given in ('б', 'Б', 'б)', 'Б.'):
            self.assertEqual(check_catalog_test(problem, given), (True, True),
                             given)

    def test_numeric_test_without_options(self):
        problem = Problem.objects.create(
            statement='Сколько?', answer='0,5',
            problem_type='тест: числовой ответ',
            status=Problem.Status.PUBLISHED)
        self.assertEqual(check_catalog_test(problem, '0.5'), (True, True))
        self.assertEqual(check_catalog_test(problem, '1/2'), (True, True))
        self.assertEqual(check_catalog_test(problem, '0,6'), (True, False))

    def test_not_a_test_is_not_auto_checked(self):
        problem = Problem.objects.create(
            statement='Открытая задача', answer='42', problem_type='расчётная',
            status=Problem.Status.PUBLISHED)
        self.assertEqual(check_catalog_test(problem, '42'), (False, False))

    def test_kind_comes_from_the_form_the_student_saw(self):
        """Вид проверки берётся у той же функции, что рисовала форму."""
        homework = Assignment.objects.create(
            name='ДЗ', author=make_user('og_tutor3', role='teacher'))
        multi = AssignmentItem.objects.create(
            assignment=homework, catalog_problem=multi_problem(), order=0)
        single = AssignmentItem.objects.create(
            assignment=homework, catalog_problem=single_problem(), order=1)
        self.assertEqual(item_answer_form(multi)[0], ANSWER_CHECKBOX)
        self.assertEqual(item_answer_form(single)[0], ANSWER_RADIO)
