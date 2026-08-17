# -*- coding: utf-8 -*-
"""
Логика блоков и таблиц (ревью 17.08, фаза 5).

5.1 Работы, которых никто не сдал, лежали в блоке «Проверены».
5.2 Метки «Карты тем» противоречили числам рядом: «уверенно — 40%» против
    «разобрался — 95%», а одинаковые данные давали разные слова.
5.3 «Сильные и слабые темы» показывали по четыре темы вместо пяти.
5.4 По какому столбцу отсортировано — не видно.
5.6 Подсказка на повёрнутом заголовке темы не появлялась вовсе.
5.7 Работу можно было выдать занятию без учеников.
"""
import datetime
import os
import re
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission, User,
)
from teacher import views_groups

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class ClosedWorksTests(TestCase):
    """5.1 — «Завершены»: срок прошёл, не сдал никто."""

    def row(self, **over):
        base = {'pending': 0, 'deadline': None, 'nobody_submitted': False}
        base.update(over)
        return base

    def test_nobody_submitted_and_overdue_is_closed(self):
        past = timezone.now() - datetime.timedelta(days=2)
        state = views_groups.assignment_state(
            self.row(deadline=past, nobody_submitted=True))
        self.assertEqual(state, 'closed')

    def test_checked_work_stays_in_done(self):
        past = timezone.now() - datetime.timedelta(days=2)
        state = views_groups.assignment_state(
            self.row(deadline=past, nobody_submitted=False))
        self.assertEqual(state, 'done')

    def test_waiting_wins_over_the_deadline(self):
        past = timezone.now() - datetime.timedelta(days=2)
        state = views_groups.assignment_state(
            self.row(deadline=past, pending=1, nobody_submitted=True))
        self.assertEqual(state, 'needs_you')

    def test_the_block_order_is_fixed(self):
        keys = [key for key, _ in views_groups.ASSIGNMENT_STATES]
        self.assertEqual(keys, ['needs_you', 'running', 'done', 'closed'])

    def test_closed_block_has_its_own_more_button(self):
        past = timezone.now() - datetime.timedelta(days=3)
        rows = [self.row(deadline=past, nobody_submitted=True)
                for _ in range(views_groups.DONE_SHOWN + 3)]
        groups = views_groups.group_assignments_by_state(rows)
        closed = [g for g in groups if g['key'] == 'closed'][0]
        self.assertEqual(closed['title'], 'Завершены')
        self.assertEqual(closed['hidden_count'], 3)

    def test_closed_work_is_not_painted_green(self):
        past = timezone.now() - datetime.timedelta(days=3)
        groups = views_groups.group_assignments_by_state(
            [self.row(deadline=past, nobody_submitted=True)])
        self.assertNotEqual(groups[0]['items'][0]['mark'], 'correct')


class TopicLabelTests(TestCase):
    """5.2 — метка темы считается по числам этой же карточки."""

    def test_thin_data_says_so(self):
        self.assertEqual(stats.topic_label(4, 100), ('thin', 'мало данных'))
        self.assertEqual(stats.topic_label(0, 0)[1], 'мало данных')

    def test_rule_is_explicit(self):
        self.assertEqual(stats.topic_label(10, 95)[1], 'мастер')
        self.assertEqual(stats.topic_label(10, 85)[1], 'мастер')
        self.assertEqual(stats.topic_label(10, 84)[1], 'разобрался')
        self.assertEqual(stats.topic_label(10, 60)[1], 'разобрался')
        self.assertEqual(stats.topic_label(10, 59)[1], 'стоит подтянуть')
        self.assertEqual(stats.topic_label(10, 0)[1], 'стоит подтянуть')

    def test_same_data_gives_the_same_label(self):
        """⚠️ ЭТО И ЕСТЬ РЕГРЕССИЯ: «100% · 2/2» получало то «уверенно»,
        то «разобрался» — метка бралась из другого счётчика."""
        first = stats.topic_label(2, 100)
        second = stats.topic_label(2, 100)
        self.assertEqual(first, second)
        # И две темы с одинаковыми числами — тоже.
        self.assertEqual(stats.topic_label(21, 95), stats.topic_label(21, 95))

    def test_label_never_contradicts_the_number(self):
        """Сорок процентов не могут называться лучше, чем девяносто пять."""
        order = ['стоит подтянуть', 'разобрался', 'мастер']
        previous = -1
        for accuracy in range(0, 101, 5):
            word = stats.topic_label(10, accuracy)[1]
            place = order.index(word)
            self.assertGreaterEqual(place, previous, accuracy)
            previous = place

    def test_threshold_is_shared_with_the_ranking_block(self):
        self.assertEqual(stats.MIN_ATTEMPTS_FOR_RANKING, 5)
        self.assertEqual(stats.topic_label(
            stats.MIN_ATTEMPTS_FOR_RANKING - 1, 100)[0], 'thin')
        self.assertNotEqual(stats.topic_label(
            stats.MIN_ATTEMPTS_FOR_RANKING, 100)[0], 'thin')


class StrongWeakTests(TestCase):
    """5.3 — по пять тем, без пересечения, устойчивым порядком."""

    def rows(self, count):
        return [{'topic_id': n, 'name': 'Тема %d' % n, 'attempted': 10,
                 'solved': n, 'accuracy': 100 - n * 5, 'mastery': 'none'}
                for n in range(count)]

    def split(self, count):
        user = User.objects.create_user('sw%d' % count, password='x',
                                        role='student')
        return stats.strongest_weakest(user, rows=self.rows(count))

    def test_ten_topics_give_five_and_five(self):
        result = self.split(10)
        self.assertEqual(len(result['strong']), 5)
        self.assertEqual(len(result['weak']), 5)

    def test_nine_topics_fill_the_first_column(self):
        """⚠️ Было 4 и 4, девятая тема не показывалась нигде."""
        result = self.split(9)
        self.assertEqual(len(result['strong']), 5)
        self.assertEqual(len(result['weak']), 4)

    def test_columns_never_overlap(self):
        for count in range(0, 14):
            result = self.split(count)
            names = [row['name'] for row in result['strong']]
            for row in result['weak']:
                self.assertNotIn(row['name'], names,
                                 'при %d темах тема в обоих списках' % count)

    def test_few_topics_show_what_there_is(self):
        result = self.split(3)
        self.assertEqual(len(result['strong']) + len(result['weak']), 3)

    def test_ties_keep_a_stable_order(self):
        """При равном проценте порядок задаёт число попыток — не случай."""
        user = User.objects.create_user('sw-tie', password='x', role='student')
        rows = [{'topic_id': 1, 'name': 'Реже', 'attempted': 6, 'solved': 3,
                 'accuracy': 50, 'mastery': 'none'},
                {'topic_id': 2, 'name': 'Чаще', 'attempted': 40, 'solved': 20,
                 'accuracy': 50, 'mastery': 'none'}]
        first = stats.strongest_weakest(user, rows=list(rows))
        second = stats.strongest_weakest(user, rows=list(reversed(rows)))
        self.assertEqual([r['name'] for r in first['strong']],
                         [r['name'] for r in second['strong']])
        self.assertEqual(first['strong'][0]['name'], 'Чаще')


class SortIndicatorTests(TestCase):
    """5.4 — видно, по какому столбцу отсортировано."""

    def test_arrow_only_on_the_active_header(self):
        kit = read('templates', '_kit.html')
        self.assertIn('thead th.is-sorted::after', kit)
        self.assertIn('thead th.is-sorted.is-desc::after', kit)

    def test_width_does_not_jump(self):
        """Место под стрелку занято всегда — иначе таблица дёргается."""
        kit = read('templates', '_kit.html')
        rule = re.search(r'thead th\[aria-sort\]::after\s*\{([^}]*)\}', kit)
        self.assertIsNotNone(rule, 'нет резерва места под стрелку')
        self.assertIn('width', rule.group(1))

    def test_aria_sort_is_set(self):
        script = read('templates', '_table_sort.html')
        self.assertIn("setAttribute('aria-sort'", script)
        self.assertIn("'ascending'", script)
        self.assertIn("'descending'", script)

    def test_empty_values_sink_in_both_directions(self):
        script = read('templates', '_table_sort.html')
        self.assertIn('xEmpty !== yEmpty', script)


class StudentCardSortingTests(TestCase):
    """5.5 — оба блока «История работ» ведут себя одинаково."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('sc-tutor', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('sc-student', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Группа',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def test_student_card_has_the_same_caption(self):
        html = self.client.get(reverse('teacher:student_progress',
                                       args=[self.student.pk])).content.decode()
        self.assertIn('Нажмите на заголовок столбца, чтобы отсортировать', html)

    def test_student_card_loads_the_sorter(self):
        html = self.client.get(reverse('teacher:student_progress',
                                       args=[self.student.pk])).content.decode()
        self.assertIn('data-sortable', html)
        self.assertIn("table[data-sortable]", html)


class MatrixHintTests(TestCase):
    """5.6 — подсказка висит на самой надписи, а не на ячейке."""

    def test_hint_is_on_the_rotated_label(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        block = page.split('{% for column in matrix.columns %}')[1]
        block = block.split('{% endfor %}')[0]
        self.assertIn('class="matrix-head"', block)
        head = block[block.index('<span class="matrix-head"'):]
        self.assertIn('data-hint', head,
                      'подсказка осталась на ячейке, а не на надписи')

    def test_cells_keep_theirs(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        self.assertIn('matrix-cell', page)
        self.assertIn('нет попыток', page)


class EmptyLessonTests(TestCase):
    """5.7 — занятию без учеников работу выдать нельзя."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('el-tutor', password='x',
                                             role='teacher')
        cls.empty = StudentGroup.objects.create(name='Пустое занятие',
                                                teacher=cls.tutor)
        cls.full = StudentGroup.objects.create(name='Живое занятие',
                                               teacher=cls.tutor)
        cls.full.students.add(User.objects.create_user('el-s', password='x',
                                                       role='student'))

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def give(self):
        return self.client.get(reverse('teacher:work_give')).content.decode()

    def test_empty_lesson_cannot_be_chosen(self):
        html = self.give()
        box = re.search(
            r'<input[^>]*name="groups"[^>]*value="%d"[^>]*>' % self.empty.pk,
            html)
        self.assertIsNotNone(box)
        self.assertIn('disabled', box.group(0))

    def test_live_lesson_stays_available(self):
        html = self.give()
        box = re.search(
            r'<input[^>]*name="groups"[^>]*value="%d"[^>]*>' % self.full.pk,
            html)
        self.assertIsNotNone(box)
        self.assertNotIn('disabled', box.group(0))

    def test_the_reason_is_written_next_to_it(self):
        self.assertIn('выдавать некому', self.give())

    def test_empty_lesson_is_never_prechecked(self):
        html = self.client.get(reverse('teacher:work_give')
                               + '?group=%d' % self.empty.pk).content.decode()
        box = re.search(
            r'<input[^>]*name="groups"[^>]*value="%d"[^>]*>' % self.empty.pk,
            html)
        self.assertNotIn('checked', box.group(0))

    def test_the_gate_lives_with_the_other_gates(self):
        give = read('teacher', 'templates', 'teacher', 'work', 'give.html')
        self.assertIn('ни в одном занятии нет учеников', give)
        self.assertIn('window.QLS_WORK.block(missing)', give)
