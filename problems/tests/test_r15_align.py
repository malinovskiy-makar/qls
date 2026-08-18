"""
Объединённое ревью 15.08, фаза 3 — выравнивание столбцов и карточек.

Пункты владельца 2, 3 и маршрут 9 (четыре карточки на карточке ученика).

⚠️ ЧТО ЗАМЕРЕНО. У заголовка и ячейки один левый край, но заголовок широкий
(«Решено»), значение узкое («3»), а процент лежит в чипе со своим отступом —
центр цифры уезжал от центра подписи на 20–31 пиксель (замер
`scripts/r15_align_probe.js`). После правки у всех числовых столбцов
расхождение центров 0 px; у текстовых и дат оно осталось и должно остаться —
их читают слева.
"""
import os
import re

from django.test import TestCase

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def markup_files():
    for folder in ('templates', 'teacher', 'student', 'problems/templates'):
        for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            if 'node_modules' in base:
                continue
            for name in files:
                if name.endswith('.html'):
                    path = os.path.join(base, name)
                    with open(path, encoding='utf-8') as handle:
                        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
                        yield rel, handle.read()


class RuleIsCommonTests(TestCase):
    """Правило одно, в наборе, а не подкрутка каждой таблицы."""

    # ⚠️ ПЕРЕСЧИТАНЫ 16.08: правило переехало из набора в общий партиал
    # `templates/_table_align.html` — набор подключают только экраны
    # кабинета, а владелец просил подравнять и таблицы каталога, который
    # видит ученик. Смысл проверок прежний, читаем РЕНДЕР набора: он
    # включает партиал, и правило по-прежнему приезжает на экраны кабинета
    # ровно оттуда, откуда приезжало.
    def kit_css(self):
        from django.template.loader import render_to_string

        return render_to_string('_kit.html')

    def test_kit_owns_column_alignment(self):
        kit = self.kit_css()
        self.assertIn('table th[data-type="num"], table td[data-type="num"]',
                      kit)
        self.assertIn('text-align: center', kit.split(
            'table th[data-type="num"], table td[data-type="num"]')[1][:80])

    def test_numbers_are_tabular(self):
        """⚠️ Ищем ПРАВИЛО, а не первое вхождение селектора.

        Прежняя проверка резала файл по строке селектора и смотрела на
        первые 200 символов после неё. С 16.08 такой селектор встречается
        дважды (центрирование и табличные цифры), и разрез попадал в
        соседнее правило — тест краснел на верной таблице стилей.
        """
        kit = self.kit_css()
        rules = [piece for piece in kit.split('}')
                 if 'tabular-nums' in piece and 'data-type="num"' in piece]
        self.assertTrue(rules, 'правила табличных цифр нет вовсе')

    def test_header_sits_on_one_line(self):
        kit = self.kit_css()
        self.assertIn('table thead th[data-type] { vertical-align: bottom; }',
                      kit)

    def test_per_table_rule_does_not_outweigh_the_kit(self):
        """⚠️ `table.stats-table th` весил столько же и, стоя ниже, побеждал."""
        style = read('problems', 'templates', 'platform', '_stats_style.html')
        self.assertNotIn('table.stats-table th, table.stats-table td', style)
        self.assertIn('.stats-table th, .stats-table td', style)

    def test_no_inline_text_align_left_in_cabinet_tables(self):
        """Выравнивание живёт в правилах, а не в атрибуте `style`."""
        bad = []
        for path, text in markup_files():
            for match in re.finditer(r'<t[hd][^>]*style="[^"]*text-align',
                                     text):
                bad.append('%s: %s' % (path, match.group(0)[:60]))
        self.assertEqual(bad, [], bad)


class MarkedCellsTests(TestCase):
    """Ячейки объявляют тип столбца — тем же словом, что и заголовок."""

    TABLES = [
        ('teacher/templates/teacher/groups/_overview.html', 3),
        ('teacher/templates/teacher/_work_history.html', 4),
        ('teacher/templates/teacher/groups/exam_results.html', 2),
    ]

    def test_numeric_cells_are_marked(self):
        for path, at_least in self.TABLES:
            text = read(*path.split('/'))
            found = len(re.findall(r'<td[^>]*data-type="num"', text))
            self.assertGreaterEqual(found, at_least, path)

    def test_every_marked_table_has_marked_headers(self):
        """Ячейка с типом без заголовка с типом — столбец без оси."""
        for path, _ in self.TABLES:
            text = read(*path.split('/'))
            self.assertIn('data-type="num"', text.split('<tbody')[0], path)


class LiveAlignmentTests(TestCase):
    """Проверка на живой странице: у числовых столбцов один класс."""

    def setUp(self):
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission, TeacherFeedback)
        from problems.tests.factories import make_problem, make_user

        now = timezone.now()
        self.tutor = make_user('al_tutor', role='teacher')
        self.student = make_user('al_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=now - timedelta(days=1))
        self.work.students.set([self.student])
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('4'))
        sub = Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=item,
            status='reviewed', submitted_at=now)
        TeacherFeedback.objects.create(submission=sub, score=Decimal('2'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def _cells(self, html, table_id):
        table = html.split('id="%s"' % table_id)[1].split('</table>')[0]
        head = table.split('<tbody')[0]
        body = table.split('<tbody')[1]
        return head, body

    def test_students_table_marks_its_numbers(self):
        html = self.client.get('/teacher/groups/%d/' % self.group.pk
                               ).content.decode()
        head, body = self._cells(html, 'students-table')
        self.assertEqual(head.count('data-type="num"'), 3)
        self.assertEqual(body.count('data-type="num"'), 3)

    def test_work_history_marks_its_numbers(self):
        html = self.client.get('/teacher/groups/%d/' % self.group.pk
                               ).content.decode()
        head, body = self._cells(html, 'group-works-table')
        self.assertGreaterEqual(head.count('data-type="num"'), 3)
        self.assertGreaterEqual(body.count('data-type="num"'), 3)

    def test_text_columns_are_left_alone(self):
        """Имя ученика и название работы остаются текстом слева."""
        html = self.client.get('/teacher/groups/%d/' % self.group.pk
                               ).content.decode()
        head, _ = self._cells(html, 'students-table')
        # ⚠️ Режем по `<th ` С ПРОБЕЛОМ: подстрока `<th` есть и в `<thead>`.
        first = head.split('<th ')[1]
        self.assertIn('data-type="text"', first)
        self.assertNotIn('data-type="num"', first)


class CardValuesOnOneLineTests(TestCase):
    """3.2 — четыре карточки-показателя: значение прижато к одной линии."""

    def test_card_is_a_column_with_the_value_at_the_bottom(self):
        style = read('problems', 'templates', 'platform', '_stats_style.html')
        card = style.split('.card3 {')[1].split('}')[0]
        self.assertIn('flex-direction: column', card)
        value = style.split('.card3-value {')[1].split('}')[0]
        self.assertIn('margin-top: auto', value)

    def test_narrow_screen_grid_is_not_touched(self):
        """На 380 карточки идут столбцом — прижимать там нечего."""
        style = read('problems', 'templates', 'platform', '_stats_style.html')
        grid = style.split('.cards3 {')[1].split('}')[0]
        self.assertIn('auto-fit', grid)
        self.assertIn('minmax(210px, 1fr)', grid)


class CatalogDifficultyTests(TestCase):
    """Столбец сложности каталога — тоже по центру."""

    def test_difficulty_column_is_centred(self):
        page = read('catalog', 'templates', 'catalog', 'problem_list.html')
        rule = page.split('.ptable .col-diff')[1].split('}')[0]
        self.assertIn('text-align: center', rule)
