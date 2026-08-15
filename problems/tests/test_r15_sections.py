# -*- coding: utf-8 -*-
"""Фаза 7 объединённого ревью 15.08: части работы видны с первого взгляда.

Владелец на приёмке: «сейчас изначально не видно, что у нас вообще
существует такое разделение». Проверяем три вещи, из которых оно состоит:

1. заголовок части несёт СОСТАВ («Тестовая часть · 3 вопроса · 6 баллов»)
   и склонения в нём правильные;
2. у карточки задачи есть полоса типа — там, где левый край свободен;
3. чип типа стоит у КАЖДОЙ карточки на всех экранах, где перечисляются
   задачи работы, включая те, где край занят состоянием проверки.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from problems.assignment_rows import (
    section_caption, section_detail, section_marks, ordered_items,
)
from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission,
)

User = get_user_model()


def a_test(title):
    return Problem.objects.create(title=title, statement='Условие теста',
                                  problem_type='тест: один ответ',
                                  status=Problem.Status.PUBLISHED)


def a_task(title):
    return Problem.objects.create(title=title, statement='Условие задачи',
                                  problem_type='задача',
                                  status=Problem.Status.PUBLISHED)


class SectionCaptionTests(TestCase):
    """Состав части словами. Чистые функции — базы не требуют."""

    def test_units_differ_by_kind(self):
        """У теста считаются ВОПРОСЫ, у открытой части — ЗАДАЧИ."""
        self.assertTrue(section_detail('test', 3, 6).startswith('3 вопроса'))
        self.assertTrue(section_detail('task', 3, 6).startswith('3 задачи'))

    def test_declension_of_units(self):
        for count, word in ((1, '1 вопрос'), (2, '2 вопроса'),
                            (5, '5 вопросов'), (11, '11 вопросов'),
                            (21, '21 вопрос'), (22, '22 вопроса')):
            self.assertTrue(section_detail('test', count, 0).startswith(word),
                            '%d → %s' % (count, section_detail('test', count, 0)))

    def test_declension_of_points(self):
        self.assertTrue(section_detail('task', 1, 1).endswith('1 балл'))
        self.assertTrue(section_detail('task', 1, 3).endswith('3 балла'))
        self.assertTrue(section_detail('task', 1, 12).endswith('12 баллов'))
        self.assertTrue(section_detail('task', 1, 21).endswith('21 балл'))

    def test_fractional_points_take_the_genitive(self):
        """⚠️ «1,5 балла», а не «1,5 балл»: дробное число целым не склоняют."""
        self.assertTrue(
            section_detail('task', 1, Decimal('1.5')).endswith('1,5 балла'))

    def test_points_are_written_like_everywhere(self):
        """Балл печатает `scorefmt.ball`: без хвостовых нулей, с запятой."""
        detail = section_detail('task', 2, Decimal('6.00'))
        self.assertIn('6 баллов', detail)
        self.assertNotIn('6,00', detail)

    def test_zero_points_are_a_number_not_a_dash(self):
        self.assertIn('0 баллов', section_detail('task', 1, Decimal('0')))

    def test_caption_glues_the_title(self):
        self.assertEqual(section_caption('test', 3, 6),
                         'Тестовая часть · 3 вопроса · 6 баллов')


class SectionMarksTests(TestCase):
    """Состав считается по позициям, а не берётся с потолка."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t7', password='x', role='teacher')
        cls.student = User.objects.create_user('s7', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Г7', teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.work = Assignment.objects.create(name='Р7', author=cls.tutor,
                                             group=cls.group)
        cls.work.students.add(cls.student)
        for order, problem in enumerate([a_test('Т1'), a_test('Т2'),
                                         a_task('З1')]):
            AssignmentItem.objects.create(assignment=cls.work, order=order,
                                          catalog_problem=problem,
                                          points=Decimal('3')
                                          if problem.title.startswith('Т')
                                          else Decimal('10'))

    def test_counts_and_points_are_summed_per_part(self):
        marks = section_marks(ordered_items(self.work))
        self.assertEqual(marks[0]['count'], 2)
        self.assertEqual(marks[0]['points'], Decimal('6'))
        self.assertEqual(marks[2]['count'], 1)
        self.assertEqual(marks[2]['points'], Decimal('10'))

    def test_caption_is_ready_for_the_screen(self):
        marks = section_marks(ordered_items(self.work))
        self.assertEqual(marks[0]['caption'],
                         'Тестовая часть · 2 вопроса · 6 баллов')
        self.assertEqual(marks[2]['caption'], 'Задачи · 1 задача · 10 баллов')


class SectionOnScreenTests(TestCase):
    """Заголовок, полоса и чип — на живых страницах кабинета."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t7s', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('s7s', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Г7с', teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.work = Assignment.objects.create(name='Р7с', author=cls.tutor,
                                             group=cls.group)
        cls.work.students.add(cls.student)
        cls.items = [
            AssignmentItem.objects.create(assignment=cls.work, order=0,
                                          catalog_problem=a_test('Т1'),
                                          points=Decimal('3')),
            AssignmentItem.objects.create(assignment=cls.work, order=1,
                                          catalog_problem=a_task('З1'),
                                          points=Decimal('10')),
        ]

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def page(self):
        response = self.client.get('/teacher/groups/%d/assignments/%d/'
                                   % (self.group.pk, self.work.pk))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_assignment_page_shows_the_composition(self):
        html = self.page()
        self.assertIn('Тестовая часть', html)
        self.assertIn('1 вопрос · 3 балла', html)
        self.assertIn('1 задача · 10 баллов', html)

    def test_assignment_page_paints_the_type_stripe(self):
        html = self.page()
        self.assertIn('k-type k-type--test', html)
        self.assertIn('k-type k-type--task', html)

    def test_every_card_carries_a_kind_chip(self):
        html = self.page()
        self.assertEqual(html.count('class="k-kind k-kind--'), 2)

    def test_source_label_no_longer_answers_two_questions(self):
        """⚠️ «тест» было ОТКУДА задача; теперь это отдельный чип типа."""
        from teacher.views_groups import _source_label

        self.assertEqual(_source_label(self.items[0]), 'каталог')
        self.assertEqual(_source_label(self.items[1]), 'каталог')

    def test_work_review_divides_into_parts_too(self):
        """Разбор работы — такой же список задач работы."""
        for item in self.items:
            Submission.objects.create(student=self.student,
                                      assignment=self.work,
                                      problem_item=item, status='submitted')
        response = self.client.get(
            '/teacher/groups/%d/assignments/%d/students/%d/'
            % (self.group.pk, self.work.pk, self.student.pk))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Тестовая часть', html)
        self.assertIn('1 вопрос · 3 балла', html)
        self.assertEqual(html.count('class="k-kind k-kind--'), 2)

    def test_review_screen_keeps_state_on_the_left_edge(self):
        """⚠️ Полосы типа там, где край занят состоянием, быть не должно.

        Две полосы разного смысла на одном крае читаются как одна
        двухцветная, и цвет состояния перестаёт что-либо значить.
        """
        for item in self.items:
            Submission.objects.create(student=self.student,
                                      assignment=self.work,
                                      problem_item=item, status='submitted')
        html = self.client.get(
            '/teacher/groups/%d/assignments/%d/students/%d/'
            % (self.group.pk, self.work.pk, self.student.pk)).content.decode()
        # Разметка строк задачи: класс состояния есть, класса типа нет.
        self.assertIn('wr-item k-mark k-mark--', html)
        self.assertNotIn('wr-item k-mark k-mark--pending k-type', html)


class KitRulesTests(TestCase):
    """Правила общих классов живут в наборе, а не в шаблоне одного экрана."""

    def kit(self):
        from django.template.loader import render_to_string

        return render_to_string('_kit.html')

    def test_type_stripe_lives_in_the_kit(self):
        kit = self.kit()
        self.assertIn('.k-type.k-type--task', kit)
        self.assertIn('.k-type.k-type--test', kit)

    def test_modifier_is_written_with_two_classes(self):
        """⚠️ Карточка задачи задаёт рамку сокращённой записью.

        При равной силе селекторов побеждает та, что ниже, а набор
        подключается ВЫШЕ страничных стилей — полоса пропала бы молча.
        """
        kit = self.kit()
        self.assertIn('.k-type.k-type--task { border-left: 3px solid', kit)

    def test_kind_chip_lives_in_the_kit(self):
        self.assertIn('.k-kind {', self.kit())

    def test_student_style_no_longer_duplicates_the_separator(self):
        """Дубль правил `.k-sep` удалён: набор подключён и у ученика."""
        from django.template.loader import render_to_string

        style = render_to_string('student/_work_style.html')
        self.assertNotIn('.k-sep__line {', style)

    def test_picker_style_no_longer_duplicates_the_stripe(self):
        from django.template.loader import render_to_string

        style = render_to_string('teacher/_picker_style.html')
        self.assertNotIn('.problem-card[data-kind="test"]', style)
