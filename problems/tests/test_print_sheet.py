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


def option_lines(html):
    """Строки <li> с вариантами ответа — только они, без CSS и условий.

    ⚠️ Искать пометку верного варианта по ВСЕМУ исходнику страницы нельзя:
    там же лежит CSS-правило `.options li.is-right`, и проверка «пометки
    нет» краснела бы всегда, даже на ученическом листке.
    """
    return [line for line in html.splitlines() if '<li' in line]


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
        """Страница не наследует базовый шаблон: меню на бумаге не нужно.

        Название сайта на листке ЕСТЬ — в собственном подвале (фаза 5.4), и
        это не навигация. Раньше проверка искала само слово «Weconomics» и
        поэтому запрещала подвал заодно с меню.
        """
        body = self.client.get(self._url()).content.decode()
        self.assertNotIn('nav-link', body)
        self.assertNotIn('header-nav', body)
        self.assertNotIn('site-header', body)
        # Название сайта встречается ровно один раз — в подвале.
        self.assertEqual(body.count('Weconomics'), 1)
        self.assertIn('<span><b>Weconomics</b>', body)

    def test_katex_pipeline_matches_the_site(self):
        """Тот же конвейер, что в `catalog/base.html`, — иначе на бумаге
        напечатается не то, что видно на экране.

        ⚠️ Версия НЕ пишется здесь строкой. Раньше стояло `katex@0.16.9` —
        кусок адреса CDN, и после переезда библиотек в репозиторий
        (ADR 0070) тест покраснел, хотя конвейер как раз остался общим.
        Теперь путь спрашивается у самого `catalog/base.html`: тест
        сравнивает печать с сайтом, как и обещает его название, и переживёт
        следующую смену версии.
        """
        import os
        import re

        from django.conf import settings

        base = os.path.join(str(settings.BASE_DIR), 'catalog', 'templates',
                            'catalog', 'base.html')
        with open(base, encoding='utf-8') as handle:
            site = handle.read()
        katex_path = re.search(r"vendor/katex-[\d.]+/katex\.min\.js", site)
        self.assertIsNotNone(
            katex_path, 'в catalog/base.html не нашёлся путь к KaTeX')

        body = self.client.get(self._url()).content.decode()
        # В отрисованной странице путь уже с хешем ManifestStaticFiles,
        # поэтому сверяем каталог версии, а не имя файла целиком.
        version = katex_path.group(0).split('/')[1]      # katex-0.16.9
        self.assertIn(version, body)
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
        # Верный вариант помечается галочкой в своей колонке (фаза 5.6), а
        # не словом в строке варианта: смотрим на пометку, а не на текст.
        self.assertFalse([l for l in option_lines(student) if 'is-right' in l])
        self.assertTrue([l for l in option_lines(teacher) if 'is-right' in l])

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


class PrintSheetPhase5Tests(TestCase):
    """Шесть исправлений листка (фаза 5 ночной сессии)."""

    def setUp(self):
        self.tutor = make_user('p5_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='10Б',
                                                 teacher=self.tutor)
        self.work = Assignment.objects.create(name='Листок',
                                              author=self.tutor,
                                              group=self.group)
        self.client.force_login(self.tutor)

    def _url(self, for_teacher=False):
        url = reverse('teacher:assignment_print',
                      args=[self.group.pk, self.work.pk])
        return url + ('?for=teacher' if for_teacher else '')

    def _task(self, points, title='Задача'):
        problem = make_problem('Найдите равновесие.', title=title)
        return AssignmentItem.objects.create(
            assignment=self.work, catalog_problem=problem,
            order=self.work.items.count(), points=Decimal(str(points)))

    def _test_item(self, points=3):
        problem = make_problem('Верно ли?', title='Тест', answer='а',
                               problem_type='тест: один ответ')
        for order, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='вариант', order=order)
        return AssignmentItem.objects.create(
            assignment=self.work, catalog_problem=problem,
            order=self.work.items.count(), points=Decimal(str(points)))

    # -- 5.1 подпункты буквами --------------------------------------------

    def test_parts_are_lettered_not_numbered(self):
        problem = make_problem('Задача с пунктами.', title='С пунктами')
        for order, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=problem, label=label, order=order,
                                       statement='Найдите что-нибудь.')
        AssignmentItem.objects.create(assignment=self.work, order=0,
                                      catalog_problem=problem)
        rows, _ = export.print_rows(self.work)
        self.assertEqual([p['label'] for p in rows[0]['parts']], ['а', 'б'])
        html = self.client.get(self._url()).content.decode()
        self.assertIn('<b class="part-label">а)</b>', html)
        # Нумерованного списка быть не должно — он рисовал бы «1.» и «2.».
        self.assertNotIn('<ol class="parts"', html)

    # -- 5.2 место для решения по весу ------------------------------------

    def test_test_gets_no_ruled_lines(self):
        item = self._test_item()
        self.assertEqual(export.solution_lines(item), 0)

    def test_heavier_task_gets_more_space(self):
        light = self._task(2)
        heavy = self._task(10)
        self.assertEqual(export.solution_lines(light), 3)
        self.assertEqual(export.solution_lines(heavy), 11)
        self.assertGreater(export.solution_lines(heavy),
                           export.solution_lines(light))

    def test_space_stays_between_three_and_twelve(self):
        self.assertEqual(export.solution_lines(self._task(0)), 3)
        self.assertEqual(export.solution_lines(self._task(1)), 3)
        self.assertEqual(export.solution_lines(self._task(100)), 12)

    # -- 5.3 шапка ученического листка ------------------------------------

    def test_student_header_is_one_row_without_a_rule(self):
        self._task(3)
        html = self.client.get(self._url()).content.decode()
        self.assertIn('who-f', html)
        # Ряд подчёркиваний «____» больше не рисуется — линию даёт CSS.
        self.assertNotIn('________', html)
        self.assertIn('Фамилия, имя', html)
        self.assertIn('Класс', html)
        self.assertIn('Дата', html)

    def test_teacher_sheet_has_no_name_row(self):
        self._task(3)
        html = self.client.get(self._url(for_teacher=True)).content.decode()
        self.assertNotIn('Фамилия, имя', html)

    # -- 5.4 подвал --------------------------------------------------------

    def test_footer_points_at_the_site_home(self):
        self._task(3)
        html = self.client.get(self._url()).content.decode()
        self.assertIn('class="foot"', html)
        self.assertIn('Weconomics', html)
        # Адрес ГЛАВНОЙ, а не этого раздела.
        self.assertIn('http://testserver/', html)
        self.assertNotIn('http://testserver/teacher/', html)

    def test_print_dialog_hint_mentions_headers(self):
        self._task(3)
        html = self.client.get(self._url()).content.decode()
        self.assertIn('Колонтитулы', html)

    # -- 5.5 плашка графика ------------------------------------------------

    def test_graph_plate_only_for_students(self):
        from problems.models import SavedGraph

        item = self._task(3)
        item.graph = SavedGraph.objects.create(owner=self.tutor,
                                               name='Равновесие', scene={})
        item.save(update_fields=['graph'])

        student_html = self.client.get(self._url()).content.decode()
        self.assertIn('вклейте или начертите здесь', student_html)

        teacher_html = self.client.get(
            self._url(for_teacher=True)).content.decode()
        self.assertNotIn('вклейте или начертите здесь', teacher_html)
        # Название графика преподаватель всё же видит — просто без рамки.
        self.assertIn('Равновесие', teacher_html)

    # -- 5.6 пометка верного варианта --------------------------------------

    def test_correct_option_marked_by_a_tick_not_by_a_word(self):
        """На тесте «верно/неверно» слово «верно» — это сам вариант."""
        problem = make_problem('При росте ставки цены облигаций вырастут.',
                               title='Данетка', answer='б',
                               problem_type='тест: верно/неверно')
        for order, (label, text) in enumerate(
                (('а', 'Верно'), ('б', 'Неверно'))):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement=text, order=order)
        AssignmentItem.objects.create(assignment=self.work, order=0,
                                      catalog_problem=problem)
        html = self.client.get(self._url(for_teacher=True)).content.decode()
        self.assertIn('class="is-right"', html)
        # Каша «б) Неверно — верно» должна исчезнуть. Смотрим ИМЕННО строки
        # вариантов: слова «верно» полно и в условии, и в пояснении в CSS.
        options = option_lines(html)
        self.assertTrue(options)
        for line in options:
            self.assertNotIn('— верно', line)
        right = [line for line in options if 'is-right' in line]
        self.assertEqual(len(right), 1)
        self.assertIn('Неверно', right[0])
