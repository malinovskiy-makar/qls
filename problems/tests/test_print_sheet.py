"""
Версия для печати: листок в один клик, без установки чего-либо.

⚠️ ЗАЧЕМ ЭТА СТРАНИЦА ВООБЩЕ. Человек собрал выданный `.tex` и получил PDF,
где нет ни одного русского слова: файл был написан под pdflatex, а собран
XeTeX. Функция, результат которой зависит от того, угадал ли пользователь
компилятор, сломана. Сайт при этом УЖЕ рисует эти формулы верно — значит
листок можно просто напечатать из браузера.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from problems import assignment_export as export
from problems.models import (
    Assignment, AssignmentItem, CustomProblem, CustomProblemOption,
    ProblemPart, StudentGroup,
)
from problems.tests.factories import make_problem, make_user


class PrintSheetTests(TestCase):

    def setUp(self):
        self.tutor = make_user('pr_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='9А', teacher=self.tutor)
        self.work = Assignment.objects.create(name='Домашка про издержки',
                                              author=self.tutor,
                                              group=self.group)
        problem = make_problem(
            'Фирма выпускает $Q$единиц. Постоянные издержки 2000.',
            title='Издержки фирмы', answer='5000', difficulty=3)
        problem.solution = 'TC = FC + VC = 2000 + 3000 = 5000.'
        problem.save()
        ProblemPart.objects.create(problem=problem, label='а', order=0,
                                   statement='Найдите TC.', answer='5000')
        self.item = AssignmentItem.objects.create(
            assignment=self.work, catalog_problem=problem, order=0,
            points=Decimal('3'))
        self.client.force_login(self.tutor)

    def _url(self, for_teacher=False):
        url = reverse('teacher:assignment_print',
                      args=[self.group.pk, self.work.pk])
        return url + ('?for=teacher' if for_teacher else '')

    def test_student_sheet_has_no_answers(self):
        body = self.client.get(self._url()).content.decode()
        self.assertIn('Издержки фирмы', body)
        self.assertIn('Фамилия, имя', body)
        self.assertNotIn('TC = FC + VC', body)

    def test_teacher_sheet_has_answers_and_solutions(self):
        body = self.client.get(self._url(for_teacher=True)).content.decode()
        self.assertIn('TC = FC + VC', body)
        self.assertIn('Ответ:', body)
        self.assertNotIn('Фамилия, имя', body)

    def test_no_navigation_on_the_sheet(self):
        """Страница не наследует базовый шаблон: меню на бумаге не нужно."""
        body = self.client.get(self._url()).content.decode()
        self.assertNotIn('ЭкЗадачи', body)
        self.assertNotIn('nav-link', body)

    def test_katex_pipeline_matches_the_site(self):
        """Тот же конвейер, что в `catalog/base.html`, — иначе на бумаге
        напечатается не то, что видно на экране."""
        body = self.client.get(self._url()).content.decode()
        self.assertIn('katex@0.16.9', body)
        self.assertIn('throwOnError: false', body)
        # $$ строго раньше $ — иначе auto-render режет $$…$$ на два пустых.
        self.assertLess(body.index("left: '$$'"), body.index("left: '$',"))

    def test_task_does_not_break_across_pages(self):
        body = self.client.get(self._url()).content.decode()
        self.assertIn('break-inside: avoid', body)
        self.assertIn('@media print', body)

    def test_text_is_cleaned_before_printing(self):
        """Склейка «$Q$единиц» на бумаге видна особенно хорошо."""
        body = self.client.get(self._url()).content.decode()
        self.assertIn('$Q$ единиц', body)

    def test_options_of_a_custom_test_are_printed(self):
        problem = CustomProblem.objects.create(
            owner=self.tutor, statement='Что будет со спросом?',
            kind=CustomProblem.Kind.SINGLE)
        CustomProblemOption.objects.create(problem=problem, text='Вырастет',
                                           is_correct=True, order=0)
        CustomProblemOption.objects.create(problem=problem, text='Упадёт',
                                           order=1)
        AssignmentItem.objects.create(assignment=self.work,
                                      custom_problem=problem, order=1)
        student = self.client.get(self._url()).content.decode()
        teacher = self.client.get(self._url(for_teacher=True)).content.decode()
        self.assertIn('Вырастет', student)
        self.assertNotIn('— верно', student)
        self.assertIn('— верно', teacher)

    def test_rows_match_the_tex_export(self):
        """Один и тот же листок: номера и пропуски обязаны совпадать."""
        rows, skipped = export.print_rows(self.work)
        tex, tex_skipped = export.build_tex(self.work)
        self.assertEqual(len(skipped), len(tex_skipped))
        self.assertEqual(len(rows), tex.count(r'\textbf{Задача '))

    def test_stranger_tutor_cannot_open(self):
        self.client.force_login(make_user('pr_other', role='teacher'))
        self.assertEqual(self.client.get(self._url()).status_code, 404)


class PdfButtonTests(TestCase):
    """Кнопка «Скачать PDF» ПОДГОТОВЛЕНА, но выключена."""

    def setUp(self):
        self.tutor = make_user('pdf_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.work = Assignment.objects.create(name='Работа', author=self.tutor,
                                              group=self.group)
        AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие.', difficulty=2))
        self.client.force_login(self.tutor)

    def test_flag_is_off_by_default(self):
        self.assertFalse(export.pdf_button_enabled())

    def test_no_pdf_button_on_the_page_while_the_flag_is_off(self):
        body = self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])).content.decode()
        self.assertNotIn('Скачать PDF', body)
        self.assertIn('Распечатать', body)

    def test_request_while_off_explains_and_redirects(self):
        """Отказ — человеческим текстом и переводом на версию для печати."""
        response = self.client.get(
            reverse('teacher:assignment_export',
                    args=[self.group.pk, self.work.pk]) + '?fmt=browser-pdf')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/print/', response['Location'])
        pdf, error = export.browser_pdf('<p>тест</p>')
        self.assertIsNone(pdf)
        self.assertIn('Версия для печати', error)

    @override_settings(ASSIGNMENT_PDF_ENABLED=True)
    def test_flag_turns_the_function_on(self):
        """Включается настройкой, а не правкой кода."""
        self.assertTrue(export.pdf_button_enabled())


class DoctypeTests(TestCase):
    """⚠️ Тест, родившийся из настоящей поломки, найденной браузером."""

    def setUp(self):
        self.tutor = make_user('dt_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.work = Assignment.objects.create(name='Работа', author=self.tutor,
                                              group=self.group)
        AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Решите $2x = 4$.', difficulty=2))
        self.client.force_login(self.tutor)

    def test_doctype_is_first(self):
        """Без `<!doctype html>` браузер уходит в quirks mode, а KaTeX в
        quirks mode ОТКАЗЫВАЕТСЯ рисовать вообще — на листке остаётся сырой
        текст «$2x = 4$» вместо формулы. Страница при этом отдаёт 200, и ни
        один питон-тест поломки не видит: она живёт только в браузере.
        """
        body = self.client.get(
            reverse('teacher:assignment_print',
                    args=[self.group.pk, self.work.pk])).content.decode()
        self.assertTrue(body.lstrip().lower().startswith('<!doctype html>'),
                        'страница не начинается с doctype — KaTeX не '
                        'нарисует ни одной формулы')
