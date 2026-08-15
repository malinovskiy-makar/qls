# -*- coding: utf-8 -*-
"""Фаза 14 объединённого ревью 15.08: печать и `.tex`.

14.1 В варианте преподавателя «Ответ:» и «Решение:» — явно разные части,
     одинаково оформленные у всех задач; пустого места под решение в этом
     варианте нет (это лист для отправки, а не бланк).
14.2 Дефекты вёрстки `.tex`, разобранные владельцем по собранному pdf:
     своё слово и своя нумерация у тестовой части, балл не отрывается от
     числа, линия «Фамилия, имя» идёт до правого поля, место под решение
     зависит от типа и веса, заголовок раздела не отрывается от первой
     задачи, у тестовой части есть место для отметки ответа.

⚠️ PDF СОБРАТЬ НЕЧЕМ: TeX Live на машине нет (`pdflatex` не найден). Всё
проверяемое здесь — сам `.tex`; сборку и вид pdf смотрит человек.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from problems import assignment_export as export
from problems.models import (
    Assignment, AssignmentItem, Problem, ProblemPart, StudentGroup,
)

User = get_user_model()


class TeacherSheetTests(TestCase):
    """14.1 — ответ и решение разведены, пустого места нет."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t14', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Г14', teacher=cls.tutor)
        cls.work = Assignment.objects.create(name='Р14', author=cls.tutor,
                                             group=cls.group)
        problem = Problem.objects.create(
            title='Равновесие', statement='Спрос 100-Q, предложение Q.',
            answer='P = 50', solution='Приравниваем и решаем.',
            problem_type='задача', status=Problem.Status.PUBLISHED)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.work, order=0, catalog_problem=problem,
            points=Decimal('10'))

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def sheet(self, for_teacher=True):
        url = ('/teacher/groups/%d/assignments/%d/print/'
               % (self.group.pk, self.work.pk))
        response = self.client.get(url,
                                   {'for': 'teacher'} if for_teacher else {})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_answer_and_solution_are_labelled_apart(self):
        html = self.sheet()
        self.assertIn('<b>Ответ:</b>', html)
        self.assertIn('sol-cap">Решение:', html)

    def test_no_blank_space_in_the_teacher_variant(self):
        """Компактный лист для отправки, а не бланк для письма."""
        self.assertNotIn('class="space"', self.sheet())

    def test_student_variant_still_has_room(self):
        self.assertIn('class="space"', self.sheet(for_teacher=False))

    def test_tex_labels_both_parts_the_same_way(self):
        tex, _ = export.build_tex(self.work, for_teacher=True)
        self.assertIn(r'\textbf{Ответ:}', tex)
        self.assertIn(r'\textbf{Решение:}', tex)


class TexLayoutTests(TestCase):
    """14.2 — разобранные владельцем дефекты собранного pdf."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t14t', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Г14т', teacher=cls.tutor)
        cls.work = Assignment.objects.create(name='Р14т', author=cls.tutor,
                                             group=cls.group)
        for number in range(3):
            test = Problem.objects.create(
                title='Тест %d' % number, statement='Утверждение %d.' % number,
                problem_type='тест: верно/неверно',
                status=Problem.Status.PUBLISHED)
            AssignmentItem.objects.create(assignment=cls.work, order=number,
                                          catalog_problem=test,
                                          points=Decimal('2'))
        for number in range(2):
            task = Problem.objects.create(
                title='Задача %d' % number, statement='Условие %d.' % number,
                problem_type='задача', status=Problem.Status.PUBLISHED)
            ProblemPart.objects.create(problem=task, label='а',
                                       statement='Пункт а.')
            AssignmentItem.objects.create(assignment=cls.work, order=10 + number,
                                          catalog_problem=task,
                                          points=Decimal('10'))

    def tex(self, for_teacher=False):
        text, _ = export.build_tex(self.work, for_teacher=for_teacher)
        return text

    def test_test_part_has_its_own_word(self):
        """⚠️ Вопросы тестовой части подписывались «Задача 1, 2, 3»."""
        tex = self.tex()
        self.assertIn(r'\textbf{Вопрос 1.}', tex)
        self.assertIn(r'\textbf{Вопрос 3.}', tex)

    def test_numbering_restarts_inside_each_part(self):
        """Сквозная нумерация означала «задача 4» в разных смыслах."""
        tex = self.tex()
        self.assertIn(r'\textbf{Задача 1.}', tex)
        self.assertNotIn(r'\textbf{Задача 4.}', tex)

    def test_points_never_break_away_from_the_number(self):
        """⚠️ «2» осталось справа, а «б.» уехало на следующую строку."""
        tex = self.tex()
        self.assertIn('2~б.', tex)
        self.assertNotIn('2 б.', tex)

    def test_name_line_runs_to_the_right_margin(self):
        tex = self.tex()
        self.assertIn(r'Фамилия, имя: \hrulefill', tex)
        self.assertNotIn(r'\underline{\hspace{7cm}}', tex)

    def test_tests_get_a_place_to_mark_the_answer(self):
        """У тестовой части не было места для отметки ответа вовсе."""
        tex = self.tex()
        self.assertIn(r'\textit{Ответ:} \underline{\hspace{3cm}}', tex)

    def test_room_depends_on_the_kind_and_the_weight(self):
        """Пустота раздавалась поровну: после теста столько же, сколько
        после расчётной задачи на полстраницы."""
        import re

        spaces = re.findall(r'\\vspace\{(\d+\.\d+)cm\}', self.tex())
        self.assertTrue(spaces, 'место под решение пропало вовсе')
        # У теста своего `\vspace` нет — только строка ответа.
        self.assertEqual(len(spaces), 2)
        self.assertGreater(float(spaces[0]), 3.0)

    def test_section_head_stays_with_the_first_task(self):
        """⚠️ «Задачи» повисли внизу страницы, задача уехала на вторую."""
        tex = self.tex()
        self.assertIn(r'\begingroup\samepage', tex)
        self.assertEqual(tex.count(r'\begingroup\samepage'),
                         tex.count(r'\endgroup'))

    def test_numbers_are_never_cut_by_the_helper(self):
        """⚠️ Помощник срезал нули с конца строки: балл 10 печатался как 1."""
        self.assertEqual(export._clean_number(Decimal('10')), '10')
        self.assertEqual(export._clean_number(Decimal('100')), '100')
        self.assertEqual(export._clean_number(Decimal('2.50')), '2,5')
        self.assertEqual(export._clean_number(Decimal('0')), '0')

    def test_screen_and_tex_agree_on_the_order(self):
        from problems.assignment_rows import ordered_items

        rows, _ = export.print_rows(self.work)
        screen = [item.problem_title for item in ordered_items(self.work)]
        self.assertEqual([row['title'] for row in rows], screen)
