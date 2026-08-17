# -*- coding: utf-8 -*-
"""
Визуальная сессия 17.08, фаза 5 — карточки экрана «Ученики» и ширина
колонки тем. Мокап `reports/mockups/mockup-stats-cabinet.html`, разделы
«Шестое» и «Седьмое».

Высоты карточек остаются РАЗНЫМИ — так задумано владельцем. Проверяем не
высоту, а то, что низ прижат ко дну и отделён линией: именно это делает из
разновысоких карточек сетку.
"""
import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import Assignment, StudentGroup, Submission, User

LIST = 'teacher/templates/teacher/groups/list.html'
STYLE = 'problems/templates/platform/_stats_style.html'


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def styles(page):
    """Только блок правил: разметку от них надо отличать."""
    return page[page.index('{% block extra_style %}'):
                page.index('{% block content %}')]


class CardStripeTests(TestCase):
    """5.1 — полоса слева есть у ВСЕХ карточек, а не через раз."""

    def test_every_card_has_a_stripe(self):
        rules = styles(read(LIST))
        base = re.search(r'\.gc-card \{([^}]*)\}', rules)
        self.assertIsNotNone(base)
        self.assertIn('border-left: 3px solid var(--border)', base.group(1))

    def test_waiting_card_turns_amber(self):
        rules = styles(read(LIST))
        calls = re.search(r'\.gc-card\.is-calls \{([^}]*)\}', rules)
        self.assertIsNotNone(calls)
        self.assertIn('var(--amber)', calls.group(1))

    def test_stripe_is_on_when_something_waits_for_the_tutor(self):
        """«Ждёт вас» — это и предупреждения, и очередь проверки."""
        page = read(LIST)
        self.assertIn('{% if card.warnings or card.pending %} is-calls', page)


class CardFootTests(TestCase):
    """5.1 — низ прижат ко дну, отделён линией и отвечает на два вопроса."""

    def test_foot_is_pinned_and_separated(self):
        rules = styles(read(LIST))
        foot = re.search(r'\.gc-foot \{([^}]*)\}', rules)
        self.assertIsNotNone(foot)
        self.assertIn('margin-top: auto', foot.group(1))
        self.assertIn('border-top: 1px solid var(--border-soft)',
                      foot.group(1))

    def test_quiet_state_is_named(self):
        page = read(LIST)
        self.assertIn('Работ на проверке нет', page)

    def test_quiet_state_is_not_a_second_pill(self):
        """Плашка рядом с янтарной читалась бы как второй сигнал."""
        rules = styles(read(LIST))
        quiet = re.search(r'\.gc-quiet \{([^}]*)\}', rules)
        self.assertIsNotNone(quiet)
        self.assertNotIn('background', quiet.group(1))


class DeadlineWindowTests(TestCase):
    """5.1 — срок показывается только в пределах семи дней."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('lc_tutor', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('lc_student', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)

    def _card(self):
        self.client.force_login(self.tutor)
        body = self.client.get(reverse('teacher:groups')).content.decode()
        return body

    def _work(self, days):
        work = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group,
            deadline=timezone.now() + timedelta(days=days))
        work.students.add(self.student)
        return work

    def test_near_deadline_is_shown(self):
        self._work(3)
        self.assertIn('class="gc-when', self._card())

    def test_far_deadline_is_hidden(self):
        self._work(30)
        self.assertNotIn('class="gc-when', self._card())

    def test_view_decides_not_the_template(self):
        """Границу окна считает питон: в шаблоне её не сравнить с «сейчас»."""
        source = read('teacher/views_groups.py')
        self.assertIn("'deadline_soon'", source)
        self.assertIn('timedelta(days=7)', source)


class WarningLevelTests(TestCase):
    """5.1 — цвет чёрточки предупреждения показывает срочность."""

    def test_three_levels_exist_in_styles(self):
        rules = styles(read(LIST))
        base = re.search(r'\.gc-warn div \{([^}]*)\}', rules)
        self.assertIn('var(--border)', base.group(1))
        high = re.search(r'\.gc-warn div\.is-high \{([^}]*)\}', rules)
        self.assertIn('var(--error)', high.group(1))
        warn = re.search(r'\.gc-warn div\.is-warn \{([^}]*)\}', rules)
        self.assertIn('var(--amber)', warn.group(1))

    def test_level_is_computed_by_stats_not_by_the_template(self):
        page = read(LIST)
        self.assertIn('class="is-{{ warning.level }}"', page)

    def test_worst_level_wins_for_a_student_with_many_reasons(self):
        from problems.stats import worst_level

        self.assertEqual(worst_level(['info', 'high', 'warn']), 'high')
        self.assertEqual(worst_level(['info', 'warn']), 'warn')
        self.assertEqual(worst_level(['info']), 'info')
        self.assertEqual(worst_level([]), 'info')

    def test_overdue_work_is_the_top_level(self):
        from problems.stats import needs_attention

        tutor = User.objects.create_user('wl_tutor', password='x',
                                         role='teacher')
        student = User.objects.create_user('wl_student', password='x',
                                           role='student')
        group = StudentGroup.objects.create(name='Г', teacher=tutor)
        group.students.add(student)
        work = Assignment.objects.create(
            name='Просроченная', author=tutor, group=group,
            deadline=timezone.now() - timedelta(days=2))
        work.students.add(student)
        rows = needs_attention(group)
        self.assertTrue(rows)
        self.assertEqual(rows[0]['level'], 'high')

    def test_review_waiting_over_a_week_is_the_top_level(self):
        """Ждёт вас дольше недели — это уже не «стоит посмотреть»."""
        from problems.stats import needs_attention

        tutor = User.objects.create_user('wl2_tutor', password='x',
                                         role='teacher')
        student = User.objects.create_user('wl2_student', password='x',
                                           role='student')
        group = StudentGroup.objects.create(name='Г2', teacher=tutor)
        group.students.add(student)
        work = Assignment.objects.create(name='Сданная', author=tutor,
                                         group=group)
        work.students.add(student)
        Submission.objects.create(
            assignment=work, student=student, status='submitted',
            submitted_at=timezone.now() - timedelta(days=9))
        levels = {row['level'] for row in needs_attention(group)}
        self.assertIn('high', levels)


class TopicColumnWidthTests(TestCase):
    """5.2 — колонка названий тем 300 px вместо 200."""

    def test_column_is_wide_enough_for_the_long_names(self):
        rule = re.search(r'\.tp-row \{([^}]*)\}', read(STYLE))
        self.assertIsNotNone(rule)
        self.assertIn('300px', rule.group(1))

    def test_header_row_shares_the_same_grid(self):
        """Шапка колонок — тот же класс: две ширины разъехались бы."""
        css = read(STYLE)
        self.assertNotIn('.tp-head { display: grid', css)
        for path in ('teacher/templates/teacher/student_progress.html',
                     'teacher/templates/teacher/groups/_overview.html'):
            self.assertIn('tp-row tp-head', read(path))
