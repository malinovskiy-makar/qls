# -*- coding: utf-8 -*-
"""
Состав однородной работы на печати и в `.tex` (ревью 17.08, фаза 14).

Разбор pdf владельцем: у контрольной из одних тестов «Вопрос 1 / Ответ:»
шли подряд — без единой подписи состава и без пометки о решении. Границы
частей у такой работы действительно нет, но состав у неё есть.
"""
from decimal import Decimal

from django.test import TestCase

from problems import assignment_export as export
from problems.assignment_rows import section_marks, whole_caption
from problems.models import Assignment, AssignmentItem, Problem, User


class WholeCaptionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('wc-tutor', password='x',
                                             role='teacher')
        cls.test_one = Problem.objects.create(
            title='Верно ли?', statement='Утверждение.',
            status=Problem.Status.PUBLISHED, problem_type='тест: один ответ',
            answer='Неверно')
        cls.test_two = Problem.objects.create(
            title='Что произойдёт?', statement='Спрос вырос.',
            status=Problem.Status.PUBLISHED, problem_type='тест: один ответ',
            answer='Сдвинется вправо')
        cls.task = Problem.objects.create(
            title='Издержки', statement='Фирма произвела 100 единиц.',
            status=Problem.Status.PUBLISHED, problem_type='задача',
            answer='5000', solution='TC = FC + VC.')

    def work(self, *problems):
        work = Assignment.objects.create(name='Работа', author=self.tutor)
        for order, problem in enumerate(problems):
            AssignmentItem.objects.create(assignment=work, order=order,
                                          catalog_problem=problem,
                                          points=Decimal('3'))
        return work

    def items(self, work):
        return list(work.items.order_by('order'))

    def test_homogeneous_work_gets_one_caption(self):
        work = self.work(self.test_one, self.test_two)
        items = self.items(work)
        self.assertEqual(section_marks(items), {})
        caption = whole_caption(items)
        self.assertEqual(caption['count'], 2)
        self.assertEqual(caption['caption'],
                         'Тестовая часть · 2 вопроса · 6 баллов')

    def test_mixed_work_is_left_to_section_marks(self):
        """⚠️ Две подписи об одном — хуже, чем ни одной: у смешанной работы
        границы частей уже размечены, и общая строка спорила бы с ними."""
        work = self.work(self.test_one, self.task)
        items = self.items(work)
        self.assertTrue(section_marks(items))
        self.assertIsNone(whole_caption(items))

    def test_empty_work_has_nothing_to_say(self):
        self.assertIsNone(whole_caption([]))

    def test_tex_prints_the_caption(self):
        work = self.work(self.test_one, self.test_two)
        tex, _ = export.build_tex(work, for_teacher=True)
        self.assertIn('Тестовая часть · 2 вопроса · 6 баллов', tex)

    def test_tex_of_mixed_work_keeps_two_captions(self):
        work = self.work(self.test_one, self.task)
        tex, _ = export.build_tex(work, for_teacher=True)
        self.assertIn('Тестовая часть', tex)
        self.assertIn('Задачи', tex)

    def test_print_sheet_puts_the_caption_on_the_first_row(self):
        work = self.work(self.test_one, self.test_two)
        rows, _ = export.print_rows(work, for_teacher=True)
        self.assertIsNotNone(rows[0]['section_head'])
        self.assertIsNone(rows[1]['section_head'])
        self.assertIn('2 вопроса', rows[0]['section_head']['caption'])


class MissingSolutionIsSaidAloudTests(TestCase):
    """⚠️ Лист «с ответами», где стоит только «Ответ:», читается как потеря
    при выгрузке. Это состояние банка, и оно называется вслух."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('ms-tutor', password='x',
                                             role='teacher')

    def build(self, **fields):
        problem = Problem.objects.create(
            title='Задача', statement='Условие.',
            status=Problem.Status.PUBLISHED, **fields)
        work = Assignment.objects.create(name='Работа', author=self.tutor)
        AssignmentItem.objects.create(assignment=work, order=0,
                                      catalog_problem=problem,
                                      points=Decimal('2'))
        return export.build_tex(work, for_teacher=True)[0]

    def test_answer_without_solution_is_explained(self):
        tex = self.build(answer='5000')
        self.assertIn(r'\textbf{Ответ:}', tex)
        self.assertIn('Эталонного решения в банке нет', tex)

    def test_solution_replaces_the_note(self):
        tex = self.build(answer='5000', solution='TC = FC + VC.')
        self.assertIn(r'\textbf{Решение:}', tex)
        self.assertNotIn('Эталонного решения в банке нет', tex)

    def test_no_answer_no_note(self):
        """Без ответа лист вообще ничего не обещает — и молчит о решении."""
        tex = self.build()
        self.assertNotIn('Эталонного решения в банке нет', tex)

    def test_student_variant_is_untouched(self):
        problem = Problem.objects.create(
            title='Задача', statement='Условие.', answer='5000',
            status=Problem.Status.PUBLISHED)
        work = Assignment.objects.create(name='Работа', author=self.tutor)
        AssignmentItem.objects.create(assignment=work, order=0,
                                      catalog_problem=problem,
                                      points=Decimal('2'))
        tex, _ = export.build_tex(work, for_teacher=False)
        self.assertNotIn('Эталонного решения', tex)
        self.assertNotIn('Ответ:} 5000', tex)


class BothEnginesTests(TestCase):
    """`.tex` собирается любым движком: ветвление преамбулы на месте."""

    def test_preamble_branches(self):
        work = Assignment.objects.create(
            name='Работа',
            author=User.objects.create_user('be-t', password='x',
                                            role='teacher'))
        tex, _ = export.build_tex(work)
        self.assertIn(r'\usepackage{iftex}', tex)
        self.assertIn(r'\ifPDFTeX', tex)
        self.assertIn('[T2A]{fontenc}', tex)
        self.assertIn(r'\usepackage{fontspec}', tex)
        self.assertIn('Latin Modern Roman', tex)
