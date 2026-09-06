"""
Мелочи приёмки (фаза 7 сессии фиксов).

7.1 номер позиции переехал к названию задачи;
7.2 «баллов» и «тест» больше не склеиваются в одну фразу;
7.3 фокус поля — нейтральный, не малиновый;
7.4 контраст кнопок в тёмной теме;
7.5 «Смотреть работу» ведёт на проверку, а не на разбор глазами ученика;
7.6 номера задач совпадают у ученика, у репетитора, в проверке и в листке.
"""
import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.assignment_export import print_rows
from problems.assignment_rows import ordered_items
from problems.models import (
    Assignment, AssignmentItem, ProblemPart, StudentGroup, Submission,
)
from problems.tests.color_utils import ratio, split_themes, token
from problems.tests.factories import make_problem, make_user
from problems.work_review import work_summary

TOKENS = 'templates/_tokens.html'
KIT = 'templates/_kit.html'
CARD = 'teacher/templates/teacher/groups/assignment_detail.html'


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


# ⚠️ Формула контраста — из `problems/tests/color_utils.py`, ОДНОЙ копией на
# весь набор. Здесь лежала своя, ещё одна из восьми одинаковых.
contrast = ratio


class RailTests(TestCase):
    """7.1 и 7.2 — левая рейка карточки позиции."""

    def setUp(self):
        self.tutor = make_user('t-rail', role='teacher')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=make_problem('Задача.', title='Про эластичность',
                                         difficulty=2),
            points=Decimal('2'))
        self.client.force_login(self.tutor)

    def _markup(self):
        html = self.client.get(reverse(
            'teacher:group_assignment',
            args=[self.group.pk, self.assignment.pk])).content.decode()
        return re.sub(r'<(script|style).*?</\1>', '', html, flags=re.S)

    def test_number_sits_next_to_the_title(self):
        """⚠️ В рейке номер стоял НАД крупной цифрой балла, и два числа
        друг под другом читались как одно."""
        markup = self._markup()
        self.assertIn('<span class="item-num">1.</span>', markup)
        rail = re.search(r'class="item-rail">(.*?)</div>\s*<div class="item-body"',
                         markup, re.S)
        self.assertIsNotNone(rail)
        self.assertNotIn('item-num', rail.group(1),
                         'номер снова в рейке над баллом')

    def test_source_label_is_a_separate_object(self):
        """«баллов» и «тест» читались одной фразой «2 баллов тест».

        ⚠️ ПЕРЕСЧИТАН, А НЕ ОТКЛЮЧЁН (ревью 15.08, фаза 7). Метка уехала
        из рейки в тело карточки и встала рядом с чипом типа: в рейке она
        стояла прямо под словом «баллов» и склеивалась с ним в фразу — то
        самое, из-за чего эта проверка и заводилась. Требование прежнее:
        метка остаётся ОТДЕЛЬНЫМ объектом со своим фоном, а не третьей
        строкой того же текста.
        """
        style = read(CARD)
        match = re.search(r'\.item-from \{(.*?)\}', style, re.S)
        self.assertIsNotNone(match, 'метка источника перестала быть объектом')
        self.assertIn('var(--chip-bg)', match.group(1))
        markup = self._markup()
        rail = re.search(r'class="item-rail">(.*?)</div>\s*<div class="item-body"',
                         markup, re.S)
        self.assertIsNotNone(rail)
        self.assertNotIn('item-from', rail.group(1),
                         'метка источника снова стоит под словом «баллов»')


class FocusRingTests(TestCase):
    """7.3 — кольцо фокуса нейтральное, акцент остался навигации."""

    def test_neutral_focus_tokens_exist(self):
        tokens = read(TOKENS)
        self.assertIn('--focus:', tokens)
        self.assertIn('--focus-ring:', tokens)
        # В обеих темах, иначе в тёмной кольца просто не будет.
        self.assertEqual(tokens.count('--focus:'), 2)

    def test_kit_fields_use_the_neutral_ring(self):
        kit = read(KIT)
        for block in re.findall(r'[^\n]*:focus[^\n{]*\{[^}]*\}', kit):
            self.assertNotIn('var(--accent-ring)', block,
                             'поле снова обводится акцентом: %s' % block[:60])

    def test_no_accent_focus_left_in_teacher_and_student_screens(self):
        """Правило одно на весь кабинет, а не «в наборе поправили»."""
        import glob

        offenders = []
        for path in (glob.glob('teacher/templates/**/*.html', recursive=True)
                     + glob.glob('student/templates/**/*.html', recursive=True)):
            for block in re.findall(r'[^\n]*:focus[^\n{]*\{[^}]*\}',
                                    read(path)):
                if 'var(--accent' in block:
                    offenders.append('%s — %s' % (path, block[:50]))
        self.assertEqual(offenders, [])


class DarkButtonContrastTests(TestCase):
    """7.4 — главная кнопка в тёмной теме читалась блёклой.

    ⚠️ ЗАМЕР ПОПРАВИЛ ОБЪЯСНЕНИЕ. Первое подозрение — «плохо читается белый
    текст» — не подтвердилось: на прежнем #334155 он давал 10,35:1. Не
    хватало другого: САМА КНОПКА не отличалась от панели (1,52:1), заливка
    не читалась как заливка. Держим оба числа сразу, иначе починка одного
    развалит другое.
    """

    AAA = 7.0          # порог контраста текста на кнопке
    STANDS_OUT = 2.11  # перепад кнопки к поверхности, которую требует канон

    def _token(self, theme, name):
        light, dark = split_themes(read(TOKENS))
        value = token(dark if theme == 'dark' else light, name)
        self.assertIsNotNone(value, '%s: токен --%s не найден' % (theme, name))
        return value

    def _dark_token(self, name):
        return self._token('dark', name)

    def test_main_button_text_stays_readable(self):
        """Осветляя заливку, легко потерять текст. Порог AAA — 7:1.

        ⚠️ ЧЕРНИЛА БЕРУТСЯ ИЗ `--on-btn` СВОЕЙ ТЕМЫ, А НЕ СЧИТАЮТСЯ БЕЛЫМИ.
        В тёмной теме кнопка стала светлой, и текст на ней тёмный; проверка,
        зашившая белый, мерила бы не то, что на экране.
        """
        value = contrast(self._dark_token('btn-bg'), self._dark_token('on-btn'))
        self.assertGreater(value, self.AAA,
                           'текст на кнопке даёт всего %.2f:1' % value)

    def test_main_button_stands_out_from_the_panel(self):
        """Кнопка обязана отличаться от панели, на которой лежит."""
        ratio = contrast(self._dark_token('btn-bg'),
                         self._dark_token('surface-2'))
        self.assertGreater(ratio, 1.9,
                           'кнопка сливается с панелью: %.2f:1' % ratio)

    def test_button_holds_its_properties_in_both_themes(self):
        """Проверяется СВОЙСТВО кнопки, а не конкретный её цвет.

        ⚠️ Раньше здесь стояло `assertIn('--btn-bg: #1e293b;', light)` — тест
        держал наизусть один старый серо-синий. Смена палитры делает такую
        проверку красной, ничего не сообщая о читаемости: цвет поменялся —
        и что? Свойств у кнопки три, и они не зависят от палитры: кнопка
        объявлена в обеих темах, текст на ней держит порог AAA, и сама
        кнопка отличается от поверхности не меньше, чем требует канон.
        """
        for theme in ('light', 'dark'):
            btn = self._token(theme, 'btn-bg')
            ink = self._token(theme, 'on-btn')
            surface = self._token(theme, 'surface')
            self.assertGreaterEqual(
                contrast(btn, ink), self.AAA,
                '%s: текст на кнопке %.2f:1' % (theme, contrast(btn, ink)))
            self.assertGreaterEqual(
                contrast(btn, surface), self.STANDS_OUT,
                '%s: кнопка не отличается от поверхности (%.2f:1)'
                % (theme, contrast(btn, surface)))


class SubmissionsButtonTests(TestCase):
    """7.5 — «Смотреть работу» ведёт на проверку."""

    def setUp(self):
        self.tutor = make_user('t-btn', role='teacher')
        self.student = make_user('s-btn', role='student')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        problem = make_problem('Задача.', difficulty=2)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        self.assignment.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0, catalog_problem=problem,
            points=Decimal('2'))
        self.submission = Submission.objects.create(
            student=self.student, assignment=self.assignment,
            problem=problem, problem_item=self.item,
            submitted_answer='42', status='reviewed')
        self.client.force_login(self.tutor)

    def _card(self):
        from teacher.views_groups import student_cards

        return student_cards(self.assignment, self.group)[0]

    def test_main_button_opens_the_review_screen(self):
        """⚠️ Раньше кнопка открывала экран ученика, где сверху написано
        «оценки ставятся на странице проверки»."""
        card = self._card()
        self.assertEqual(card['button']['label'], 'Смотреть работу')
        self.assertEqual(
            card['button']['url'],
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.submission.pk]))

    def test_student_view_stays_as_a_quiet_second_link(self):
        card = self._card()
        self.assertEqual(
            card['student_view'],
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.assignment.pk,
                          self.student.pk]))

    def test_pending_work_also_offers_the_student_view(self):
        self.submission.status = 'submitted'
        self.submission.save(update_fields=['status'])
        self.assertIsNotNone(self._card()['student_view'])

    def test_nothing_submitted_has_no_student_view(self):
        """Разбирать нечего — и ссылки быть не должно."""
        self.submission.status = 'not_started'
        self.submission.save(update_fields=['status'])
        self.assertIsNone(self._card()['student_view'])


class NumberingAgreesEverywhereTests(TestCase):
    """7.6 — один и тот же номер у одной и той же задачи на всех экранах.

    ⚠️ Иначе разговор на занятии ломается: ученик называет «четвёртую», а у
    репетитора под четвёртой другая задача.
    """

    def setUp(self):
        self.tutor = make_user('t-num', role='teacher')
        self.student = make_user('s-num', role='student')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        self.assignment.students.add(self.student)
        # Нарочно вперемешку: задача, тест, задача, тест.
        self.items = []
        for order, is_test in enumerate([False, True, False, True]):
            problem = make_problem(
                'Условие %d.' % order, difficulty=2,
                problem_type='тест: один ответ' if is_test else 'расчётная',
                answer='а' if is_test else '42')
            if is_test:
                ProblemPart.objects.create(problem=problem, label='а', order=0,
                                           statement='Первый', answer='верно')
                ProblemPart.objects.create(problem=problem, label='б', order=1,
                                           statement='Второй', answer='неверно')
            self.items.append(AssignmentItem.objects.create(
                assignment=self.assignment, order=order,
                catalog_problem=problem, points=Decimal('2')))
        for item in self.items:
            Submission.objects.create(
                student=self.student, assignment=self.assignment,
                problem=item.catalog_problem, problem_item=item,
                submitted_answer='42', status='submitted')

    def test_teacher_student_and_print_agree(self):
        teacher = [(index, item.pk) for index, item
                   in enumerate(ordered_items(self.assignment), start=1)]

        student = [(row['number'], row['item'].pk) for row
                   in work_summary(self.assignment, self.student)['rows']]
        self.assertEqual(teacher, student,
                         'номера у ученика и у репетитора разошлись')

        rows, _ = print_rows(self.assignment)
        printed = [row['number'] for row in rows]
        self.assertEqual(printed, [index for index, _ in teacher],
                         'номера в листке разошлись с экраном')

    def test_review_flow_uses_the_same_numbers(self):
        from teacher.views import review_position

        order = {item.pk: index for index, item
                 in enumerate(ordered_items(self.assignment), start=1)}
        for submission in Submission.objects.filter(
                assignment=self.assignment, student=self.student):
            number, total, _, _, _ = review_position(
                self.assignment, self.student, submission)
            self.assertEqual(number, order[submission.problem_item_id])
            self.assertEqual(total, len(order))
