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
from problems.tests.factories import make_problem, make_user
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
    """Два верных варианта из трёх — второй случай с ручной проверки.

    Тип именно «все верные»: галочки в проекте рисует ТОЛЬКО он. Тип
    «верно/неверно» — это одно утверждение с двумя вариантами (454 из 455
    таких задач банка), и выбор там одиночный.
    """
    return catalog_test(
        'тест: все верные',
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
        """Старая позиция без балла по-прежнему стоит единицу.

        Новым позициям балл проставляет `AssignmentItem.save()` (10 задаче,
        3 тесту), поэтому пустой балл приходится вернуть через `update()` —
        он идёт мимо save() и точно повторяет строку, лежавшую в базе до
        миграции 0032. Правило «пусто = единица» стережём именно ради таких
        строк: они могут приехать из старой фикстуры.
        """
        item = AssignmentItem.objects.create(
            assignment=self.homework, catalog_problem=multi_problem(),
            order=99)
        AssignmentItem.objects.filter(pk=item.pk).update(points=None)
        item.refresh_from_db()
        self.assertEqual(item_max_score(item), Decimal('1'))
        sub = self._submit(item, ['а', 'б', 'г'])
        self.assertEqual(Decimal(str(sub.feedback.score)), Decimal('1'))

    def test_new_item_gets_default_points(self):
        """Значения по умолчанию: 10 открытой задаче, 3 тесту."""
        test_item = AssignmentItem.objects.create(
            assignment=self.homework, catalog_problem=multi_problem(),
            order=101)
        open_item = AssignmentItem.objects.create(
            assignment=self.homework, order=102,
            catalog_problem=make_problem('Открытая задача'))
        self.assertEqual(item_max_score(test_item), Decimal('3'))
        self.assertEqual(item_max_score(open_item), Decimal('10'))

    def test_explicit_points_are_not_overwritten(self):
        """Балл, выставленный репетитором, значение по умолчанию не трогает."""
        item = AssignmentItem.objects.create(
            assignment=self.homework, catalog_problem=multi_problem(),
            order=103, points=7)
        self.assertEqual(item_max_score(item), Decimal('7'))
        item.points = 4
        item.save()
        item.refresh_from_db()
        self.assertEqual(item_max_score(item), Decimal('4'))


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


class OptionReviewTests(TestCase):
    """Разбор показывает ВАРИАНТЫ с двумя отметками, а не две строки текста."""

    def setUp(self):
        self.tutor = make_user('or_tutor', role='teacher')
        self.student = make_user('or_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.homework.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, catalog_problem=multi_problem(),
            order=0, points=Decimal('3'))
        self.client.force_login(self.student)

    def _review_rows(self, values):
        from problems.assignment_rows import answer_input_name, option_review

        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(self.item): values})
        sub = Submission.objects.get(student=self.student,
                                     problem_item=self.item)
        return option_review(self.item, sub)

    def test_four_states_are_distinguished(self):
        """Верные «а, б, г»; ученик отметил «а, в» — все четыре исхода разом."""
        rows = {r['label']: r['state'] for r in self._review_rows(['а', 'в'])}
        self.assertEqual(rows['а'], 'hit')      # выбрал, верно
        self.assertEqual(rows['в'], 'wrong')    # выбрал, неверно
        self.assertEqual(rows['б'], 'missed')   # не выбрал, а надо было
        self.assertEqual(rows['г'], 'missed')

    def test_correctly_skipped_option(self):
        """«Не выбрал и правильно» — четвёртое состояние, отдельный исход."""
        clean = {r['label']: r['state']
                 for r in self._review_rows(['а', 'б', 'г'])}
        self.assertEqual(clean['в'], 'skip')
        self.assertEqual(clean['а'], 'hit')

    def test_option_text_is_shown_not_only_the_letter(self):
        rows = self._review_rows(['а'])
        self.assertIn('Технология производства',
                      [r['text'] for r in rows])

    def test_screen_renders_options(self):
        from problems.assignment_rows import answer_input_name

        self.client.post(
            reverse('student:submit_assignment', args=[self.homework.pk]),
            {answer_input_name(self.item): ['а', 'в']})
        body = self.client.get(
            reverse('student:work_review',
                    args=[self.homework.pk])).content.decode()
        self.assertIn('Технология производства', body)
        self.assertIn('надо было выбрать', body)
        self.assertIn('opt-missed', body)
        self.assertIn('opt-wrong', body)

    def test_options_are_not_leaked_before_submission(self):
        """До сдачи разбор вариантов не собирается — это были бы ответы."""
        from problems.assignment_rows import build_rows

        row = build_rows(self.homework, self.student)[0]
        self.assertEqual(row['option_review'], [])


class TutorStudentViewTests(TestCase):
    """«Глазами ученика»: ведёт на разбор ЭТОГО ученика и говорит об этом."""

    def setUp(self):
        from problems.models import StudentGroup

        self.tutor = make_user('tsv_tutor', role='teacher')
        self.student = make_user('tsv_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.client.force_login(self.tutor)

    def _work(self, group=None):
        work = Assignment.objects.create(name='Работа', author=self.tutor,
                                         group=group)
        work.students.add(self.student)
        item = AssignmentItem.objects.create(
            assignment=work, catalog_problem=single_problem(), order=0,
            points=Decimal('1'))
        Submission.objects.create(student=self.student, assignment=work,
                                  problem_item=item, status='submitted',
                                  submitted_answer='б')
        return work

    def test_group_route_shows_banner_with_student_name(self):
        work = self._work(group=self.group)
        body = self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, work.pk,
                          self.student.pk])).content.decode()
        self.assertIn('глазами ученика', body)
        self.assertIn(self.student.username, body)

    def test_work_without_group_still_has_the_screen(self):
        """У работы без группы кнопка раньше просто исчезала со страницы."""
        work = self._work(group=None)
        response = self.client.get(
            reverse('teacher:student_work_review_plain',
                    args=[work.pk, self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('глазами ученика', response.content.decode())

    def test_review_page_always_offers_the_link(self):
        """Кнопка на месте. Надпись сокращена в фазе 7.2 до «Глазами
        ученика»: длинная строка вылезала за границы кнопки."""
        work = self._work(group=None)
        sub = Submission.objects.get(assignment=work)
        body = self.client.get(
            reverse('teacher:review_submission',
                    args=[sub.pk])).content.decode()
        self.assertIn('Глазами ученика', body)
        # Класс .btn-back тут стоять не должен: у него white-space:nowrap.
        self.assertNotIn('class="btn-back"\n             style', body)

    def test_stranger_tutor_gets_404(self):
        work = self._work(group=None)
        other = make_user('tsv_other', role='teacher')
        self.client.force_login(other)
        response = self.client.get(
            reverse('teacher:student_work_review_plain',
                    args=[work.pk, self.student.pk]))
        self.assertEqual(response.status_code, 404)
