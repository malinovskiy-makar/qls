# -*- coding: utf-8 -*-
"""
Хвост первой сессии: три числа, которые считали не то (ревью 17.08, фаза 0).

Первая сессия свела счёт «ждут проверки» к паре (ученик, работа), и три
места на экране сошлись. Но сошлись они НА ОДНОМ И ТОМ ЖЕ ВРАНЬЕ: у
`Submission` в `Meta.ordering` стоит `-submitted_at`, а Django добавляет
поле сортировки прямо в `SELECT DISTINCT`. Строки различались ещё и
моментом сдачи, и один ученик, сдавший работу из четырёх задач, давал
четыре «работы»:

  0.2 «сдали 1 из 3» и рядом кнопка «Проверить 4 работы»;
  0.3 «Сдано работ 21» при двенадцати заданиях в группе.

Прежние проверки этого не видели, потому что в их данных `submitted_at`
у всех сдач пуст — при одинаковом значении `DISTINCT` схлопывает строки
и без `order_by()`. Здесь моменты сдачи РАЗНЫЕ, как в живой базе.

  0.1 Заголовок блока «Требуют проверки 3» стоял в тридцати пикселях от
      пилюли «6 работ ждут проверки»: два числа про одно и то же, и
      считают они разное.

⚠️ Проверки сравнивают числа МЕЖДУ СОБОЙ, а не с константой: константа
устареет при первой правке демо-данных, а равенство «кнопка = пилюля =
колонка» обязано держаться всегда.
"""
import datetime
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission, User,
)
from teacher import views_groups


class DifferentMomentsBase(TestCase):
    """Группа из трёх учеников; у каждой задачи свой момент сдачи."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('ln-tutor', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.students = []
        for index in range(3):
            student = User.objects.create_user('ln-s%d' % index, password='x',
                                               role='student')
            cls.group.students.add(student)
            cls.students.append(student)

        cls.problems = [
            Problem.objects.create(title='Задача %d' % n, statement='Условие',
                                   status=Problem.Status.PUBLISHED,
                                   problem_type='задача', difficulty=3)
            for n in range(4)]

        # Четыре задачи в работе — ровно тот случай, на котором кнопка
        # писала «Проверить 4 работы» при одном сдавшем.
        cls.work = Assignment.objects.create(name='Сквозная домашка',
                                             author=cls.tutor,
                                             group=cls.group)
        for order, problem in enumerate(cls.problems):
            AssignmentItem.objects.create(assignment=cls.work, order=order,
                                          catalog_problem=problem,
                                          points=Decimal('2'))
        cls.work.students.set(cls.group.students.all())

        # ⚠️ РАЗНЫЕ МОМЕНТЫ СДАЧИ. Ученик отвечает на задачи по очереди, и
        # в живой базе `submitted_at` у них разный — именно это и ломало
        # `distinct()`.
        base = timezone.now() - datetime.timedelta(days=1)
        for number, item in enumerate(cls.work.items.all()):
            Submission.objects.create(
                assignment=cls.work, student=cls.students[0],
                problem=item.catalog_problem, problem_item=item,
                status='submitted',
                submitted_at=base + datetime.timedelta(minutes=number))

    def _rows(self):
        return [views_groups.assignment_stats(self.work)]


class OneStudentIsOneWorkTests(DifferentMomentsBase):
    """0.2 — кнопка считает сдачи, а не задачи внутри них."""

    def test_button_counts_one_work_per_student(self):
        row = views_groups.assignment_stats(self.work)
        self.assertEqual(row['submitted'], 1)
        self.assertEqual(row['pending'], 1,
                         'кнопка снова считает задачи, а не работы')

    def test_button_never_exceeds_the_number_of_students(self):
        """Работ на проверке не может быть больше, чем учеников работы."""
        row = views_groups.assignment_stats(self.work)
        self.assertLessEqual(row['pending'], self.work.students.count())

    def test_four_rows_of_one_work_stay_one(self):
        self.assertEqual(Submission.objects.filter(assignment=self.work,
                                                   status='submitted').count(),
                         4)
        self.assertEqual(stats.works_waiting([self.work]), 1)

    def test_second_student_adds_exactly_one(self):
        base = timezone.now()
        for number, item in enumerate(self.work.items.all()):
            Submission.objects.create(
                assignment=self.work, student=self.students[1],
                problem=item.catalog_problem, problem_item=item,
                status='submitted',
                submitted_at=base + datetime.timedelta(minutes=number))
        self.assertEqual(stats.works_waiting([self.work]), 2)


class ColumnNeverExceedsAssignmentsTests(DifferentMomentsBase):
    """0.3 — «Сдано работ» не бывает больше числа заданий занятия."""

    def test_column_is_bounded_by_the_number_of_works(self):
        works = Assignment.objects.filter(group=self.group).count()
        for row in stats.group_table(self.group, period='all'):
            self.assertLessEqual(
                row['submitted'], works,
                'у %s работ больше, чем заданий в занятии'
                % row['student'].username)

    def test_column_counts_this_group_only(self):
        """Работа другого занятия в колонку не попадает."""
        other = StudentGroup.objects.create(name='Другое', teacher=self.tutor)
        other.students.add(self.students[0])
        work = Assignment.objects.create(name='Чужая', author=self.tutor,
                                         group=other)
        item = AssignmentItem.objects.create(assignment=work, order=0,
                                             catalog_problem=self.problems[0],
                                             points=Decimal('1'))
        Submission.objects.create(assignment=work, student=self.students[0],
                                  problem=self.problems[0], problem_item=item,
                                  status='submitted',
                                  submitted_at=timezone.now())
        rows = {row['student'].username: row
                for row in stats.group_table(self.group, period='all')}
        self.assertEqual(rows['ln-s0']['submitted'], 1)


class AllThreeNumbersAgreeTests(DifferentMomentsBase):
    """Пилюля, кнопки и колонка — одно число, посчитанное один раз."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def test_pill_equals_sum_of_buttons(self):
        assignments = list(Assignment.objects.filter(group=self.group))
        buttons = sum(views_groups.assignment_stats(work)['pending']
                      for work in assignments)
        self.assertEqual(buttons, stats.works_waiting(assignments))

    def test_pill_equals_sum_of_column(self):
        rows = stats.group_table(self.group, period='all')
        self.assertEqual(
            sum(row['pending'] for row in rows),
            stats.works_waiting(list(Assignment.objects.filter(
                group=self.group))))

    def test_screen_shows_the_same_number_everywhere(self):
        page = self.client.get(reverse('teacher:group_detail',
                                       args=[self.group.pk])
                               + '?tab=assignments')
        self.assertEqual(page.status_code, 200)
        buttons = sum(row['pending']
                      for row in page.context['assignment_rows'])
        self.assertEqual(buttons, page.context['waiting_total'])


class HeaderHasNoSecondNumberTests(DifferentMomentsBase):
    """0.1 — у блока «Требуют проверки» числа в заголовке нет."""

    def test_needs_you_block_has_no_caption(self):
        blocks = {block['key']: block for block in
                  views_groups.group_assignments_by_state(self._rows())}
        self.assertIn('needs_you', blocks)
        self.assertEqual(blocks['needs_you']['caption'], '')

    def test_other_blocks_keep_their_caption(self):
        """У остальных блоков число ничему не противоречит и остаётся."""
        work = Assignment.objects.create(
            name='Идёт', author=self.tutor, group=self.group,
            deadline=timezone.now() + datetime.timedelta(days=3))
        rows = self._rows() + [views_groups.assignment_stats(work)]
        blocks = {block['key']: block for block in
                  views_groups.group_assignments_by_state(rows)}
        self.assertEqual(blocks['running']['caption'], '1')

    def test_screen_prints_the_title_without_a_number(self):
        page = self.client.get(reverse('teacher:group_detail',
                                       args=[self.group.pk])
                               + '?tab=assignments')
        blocks = {block['key']: block
                  for block in page.context['assignment_groups']}
        self.assertEqual(blocks['needs_you']['caption'], '')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)
