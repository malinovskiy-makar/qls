"""
Экспорт задания на бумагу: два варианта, граничные случаи, деградация.
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from problems import assignment_export as export
from problems.models import (
    Assignment, AssignmentItem, CustomProblem, ProblemPart, StudentGroup,
)
from problems.tests.factories import make_problem, make_user


class BuildTexTests(TestCase):

    def setUp(self):
        self.tutor = make_user('ex_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Экономика 11',
                                                 teacher=self.tutor)
        self.homework = Assignment.objects.create(
            name='Домашка №5', author=self.tutor, group=self.group)
        problem = make_problem('Найдите равновесие на рынке кофе.',
                               answer='P = 30')
        ProblemPart.objects.create(problem=problem, label='а', order=0,
                                   statement='Найдите цену.', answer='30')
        ProblemPart.objects.create(problem=problem, label='б', order=1,
                                   statement='Найдите количество.',
                                   answer='60')
        problem.solution = 'Приравниваем спрос и предложение.'
        problem.save()
        self.item = AssignmentItem.objects.create(
            assignment=self.homework, order=0, catalog_problem=problem,
            points=Decimal('4'))

    def test_student_sheet_has_no_answers(self):
        tex, skipped = export.build_tex(self.homework, for_teacher=False)
        self.assertIn('Домашка №5', tex)
        self.assertIn('Экономика 11', tex)
        self.assertIn('Задача 1', tex)
        self.assertIn('Найдите цену.', tex)
        self.assertNotIn('P = 30', tex)
        self.assertNotIn('Приравниваем спрос', tex)
        self.assertEqual(skipped, [])
        # ⚠️ ПЕРЕСЧИТАН (ревью 15.08, п. 14.2). Место под решение было
        # ОДИНАКОВЫМ у всех задач — 3,2 см и после теста с готовыми
        # вариантами, и после расчётной задачи на полстраницы. Теперь его
        # считает та же `solution_lines`, что и страница печати. Требование
        # проверки прежнее: место под решение в ученическом варианте есть.
        self.assertRegex(tex, r'\\vspace\{\d+\.\d+cm\}')

    def test_teacher_sheet_has_answers_and_solutions(self):
        tex, _ = export.build_tex(self.homework, for_teacher=True)
        self.assertIn('Ответ:', tex)
        self.assertIn('Приравниваем спрос', tex)
        self.assertIn('Вариант преподавателя', tex)

    def test_parts_are_separate_lines(self):
        tex, _ = export.build_tex(self.homework)
        self.assertIn(r'\begin{enumerate}', tex)
        self.assertIn(r'\item[а)]', tex)
        self.assertIn(r'\item[б)]', tex)

    def test_points_are_printed(self):
        tex, _ = export.build_tex(self.homework)
        # ⚠️ Неразрывный пробел: «4» и «б.» разъезжались по строкам.
        self.assertIn('4~б.', tex)

    def test_file_compiles_with_any_engine(self):
        """⚠️ ИЗМЕНЕНИЕ КОНТРАКТА (Фаза C.4). Раньше здесь стояло «fontspec
        быть не должно»: файл писался строго под pdflatex. Ручная проверка
        показала худший исход — человек собрал его XeTeX-ом и получил PDF
        БЕЗ ЕДИНОГО русского слова: настройки pdflatex XeTeX молча
        игнорирует, и кириллица исчезает без ошибки. Репетитор не обязан
        знать слов «pdflatex» и «XeTeX», поэтому преамбула теперь ветвится
        сама.
        """
        tex, _ = export.build_tex(self.homework)
        self.assertIn('% !TeX program = pdflatex', tex)
        self.assertIn(r'\usepackage{iftex}', tex)
        # Ветка pdflatex — кодировки; ветка XeTeX/LuaTeX — юникодный шрифт.
        self.assertIn(r'\ifPDFTeX', tex)
        self.assertIn(r'\usepackage[T2A]{fontenc}', tex)
        self.assertIn(r'\usepackage{fontspec}', tex)
        self.assertIn('Latin Modern Roman', tex)
        self.assertIn(r'\fi', tex)
        # Русский язык подключается ОДИН раз, после ветвления.
        self.assertEqual(tex.count(r'\usepackage[russian]{babel}'), 1)
        self.assertLess(tex.index(r'\ifPDFTeX'),
                        tex.index(r'\usepackage[russian]{babel}'))

    def test_custom_problem_exports_too(self):
        own = CustomProblem.objects.create(
            owner=self.tutor, title='Своя', statement='Условие своей задачи.',
            correct_answer='7')
        AssignmentItem.objects.create(assignment=self.homework, order=1,
                                      custom_problem=own, points=3)
        tex, _ = export.build_tex(self.homework, for_teacher=True)
        self.assertIn('Условие своей задачи.', tex)
        self.assertIn('Ответ:', tex)

    def test_graph_plate_becomes_a_visible_box(self):
        problem = make_problem('Смотрите чертёж. [[График: Равновесие]]')
        AssignmentItem.objects.create(assignment=self.homework, order=2,
                                      catalog_problem=problem)
        tex, _ = export.build_tex(self.homework)
        self.assertIn(r'\fbox', tex)
        self.assertIn('Равновесие', tex)

    def test_broken_problem_is_skipped_not_fatal(self):
        """Битая задача пропускается с пометкой, остальные собираются."""
        broken = make_problem('Условие с непарным $ долларом и {скобкой')
        AssignmentItem.objects.create(assignment=self.homework, order=3,
                                      catalog_problem=broken)
        tex, skipped = export.build_tex(self.homework)
        self.assertEqual(len(skipped), 1)
        self.assertIn('Пропущено задач при сборке: 1', tex)
        self.assertIn('Найдите равновесие', tex)   # хорошая задача осталась

    def test_broken_detector(self):
        self.assertTrue(export.looks_broken('одна $ формула'))
        self.assertTrue(export.looks_broken('{незакрытая'))
        self.assertFalse(export.looks_broken('нормально: $x=1$ и \\{ \\}'))
        self.assertFalse(export.looks_broken('$$P^*=30$$'))


class ExportViewTests(TestCase):

    def setUp(self):
        self.tutor = make_user('ev_tutor', role='teacher')
        self.other = make_user('ev_other', role='teacher')
        self.group = StudentGroup.objects.create(name='Г', teacher=self.tutor)
        self.exam = Assignment.objects.create(
            name='Контрольная №2', author=self.tutor, group=self.group,
            kind=Assignment.Kind.EXAM)
        AssignmentItem.objects.create(
            assignment=self.exam, order=0,
            catalog_problem=make_problem('Задача', answer='5'), points=5)
        self.client.force_login(self.tutor)

    def _url(self, **params):
        url = reverse('teacher:assignment_export',
                      args=[self.group.pk, self.exam.pk])
        if params:
            url += '?' + '&'.join('%s=%s' % kv for kv in params.items())
        return url

    def test_tex_downloads(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('x-tex', response['Content-Type'])
        self.assertIn('.tex', response['Content-Disposition'])
        self.assertIn('Контрольная работа', response.content.decode())

    def test_pdf_falls_back_to_tex_without_tex_live(self):
        """Прод без TeX Live: понятное сообщение и .tex, а не 500."""
        with mock.patch.object(export, 'pdflatex_available',
                               return_value=False):
            response = self.client.get(self._url(fmt='pdf'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('x-tex', response['Content-Type'])

    def test_foreign_tutor_gets_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self._url()).status_code, 404)

    def test_buttons_are_on_the_assignment_page(self):
        body = self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.exam.pk])).content.decode()
        # Кнопка называется понятно: «Распечатать», а не «Экспорт в TeX».
        self.assertIn('Распечатать', body)
        self.assertIn('assignments/%d/print/' % self.exam.pk, body)
        self.assertIn('.tex ученикам', body)
