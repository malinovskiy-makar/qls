"""
Обзор кабинета 13.08.2026, фаза 5 — карточка ученика.

Пункты владельца 30, 32, 34:
  • «562 минуты» под подписью «Минут на сайте» — единица звучит дважды;
  • ссылка «карточка ученика» налезала на строку с данными;
  • голый прочерк в «% верных тестов», когда тестов в работе не было.
"""
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class MinutesLabelTests(TestCase):
    """5.1 — единица только в подписи."""

    def setUp(self):
        from problems.models import LearningEvent

        self.tutor = make_user('mc_tutor', role='teacher')
        self.student = make_user('mc_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.lesson = StudentGroup.objects.create(
            name='Мария Ким', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.student])
        now = timezone.now()
        for shift in (0, 4, 9):
            LearningEvent.objects.create(user=self.student, source='catalog',
                                         event_type='solved')
        LearningEvent.objects.filter(user=self.student).update(
            created_at=now - timedelta(minutes=3))
        self.client.force_login(self.tutor)

    def _card_value(self, html):
        part = html.split('Минут на сайте')[1]
        value = re.search(r'class="card3-value">(.*?)</div>', part, re.S)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>|\{.*?\}', '',
                                          value.group(1))).strip()

    def test_student_card_says_the_unit_once(self):
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        value = self._card_value(html)
        self.assertNotIn('минут', value)
        self.assertTrue(value.isdigit() or value == 'нет данных', value)

    def test_lesson_screen_says_the_unit_once(self):
        html = self.client.get(
            reverse('teacher:group_detail',
                    args=[self.lesson.pk])).content.decode()
        value = self._card_value(html)
        self.assertNotIn('минут', value)

    def test_caption_still_names_the_unit(self):
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        self.assertIn('Минут на сайте', html)


class HeaderLinkTests(TestCase):
    """5.2 — ссылка «Карточка ученика» стоит на своём месте."""

    def setUp(self):
        self.tutor = make_user('hl_tutor', role='teacher')
        self.student = make_user('hl_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.student.profile.grade = 11
        self.student.profile.city = 'Санкт-Петербург'
        self.student.profile.goal = 'заключительный этап ВсОШ'
        self.student.profile.save()
        self.lesson = StudentGroup.objects.create(
            name='Мария Ким', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.student])
        self.client.force_login(self.tutor)

    def _html(self):
        return self.client.get(
            reverse('teacher:group_detail',
                    args=[self.lesson.pk])).content.decode()

    def test_link_is_not_deleted(self):
        """⚠️ Ссылка ведёт на ДРУГОЙ экран — удалять её было нельзя."""
        self.assertIn(reverse('teacher:student_progress',
                              args=[self.student.pk]), self._html())

    def test_link_left_the_subtitle(self):
        """Она стояла ВНУТРИ подписи, вплотную под строкой с данными."""
        page = read('teacher', 'templates', 'teacher', 'groups',
                    'detail.html')
        header = page.split('<div class="page-header">')[1].split(
            '</div>\n\n{% comment %}')[0]
        subtitle = header.split('page-sub')
        for chunk in subtitle[1:]:
            self.assertNotIn('student_progress', chunk[:200])

    def test_link_is_a_kit_button_now(self):
        html = self._html()
        block = html.split('<div class="gd-side">')[1][:400]
        self.assertIn('k-btn k-btn--plain k-btn--sm', block)
        self.assertIn('Карточка ученика', block)

    def test_kind_chip_is_still_there(self):
        block = self._html().split('<div class="gd-side">')[1][:500]
        self.assertIn('индивидуально', block)

    def test_group_screen_has_no_such_button(self):
        """У группы карточки ученика нет — и кнопки быть не должно."""
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.set([self.student, make_user('hl_2', role='student')])
        html = self.client.get(
            reverse('teacher:group_detail', args=[group.pk])).content.decode()
        block = html.split('<div class="gd-side">')[1][:400]
        self.assertNotIn('Карточка ученика', block)


class WorkHistoryEmptyTests(TestCase):
    """5.3 — «нет тестов» вместо голого прочерка."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem,
                                     Submission, TeacherFeedback)

        self.now = timezone.now()
        self.tutor = make_user('wh_tutor', role='teacher')
        self.student = make_user('wh_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])

        # Работа ТОЛЬКО из открытых задач: тестов в ней не было вовсе.
        self.work = Assignment.objects.create(
            name='Только задачи', author=self.tutor, group=self.group,
            deadline=self.now - timedelta(days=1))
        self.work.students.set([self.student])
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('10'))
        sub = Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=item,
            status='reviewed', submitted_at=self.now)
        TeacherFeedback.objects.create(submission=sub, score=Decimal('8'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def test_kinds_are_read_from_the_composition(self):
        kinds = stats.work_kinds(self.work)
        self.assertEqual(kinds, {'has_open': True, 'has_test': False})

    def test_history_says_no_tests(self):
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        self.assertIn('нет тестов', html)

    def test_the_open_column_still_shows_the_percent(self):
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        self.assertIn('80 %', html)

    def test_dash_survives_where_data_is_simply_missing(self):
        """Тест в работе ЕСТЬ, но не проверен — это «пока не знаем»."""
        from problems.models import AssignmentItem

        test_problem = make_problem('Тестовое условие')
        test_problem.problem_type = 'тест: один ответ'
        test_problem.save()
        AssignmentItem.objects.create(
            assignment=self.work, order=1, catalog_problem=test_problem,
            points=Decimal('3'))
        kinds = stats.work_kinds(self.work)
        self.assertTrue(kinds['has_test'])
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        self.assertNotIn('нет тестов', html)

    def test_group_history_gets_the_same_wording(self):
        html = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=overview').content.decode()
        self.assertIn('нет тестов', html)

    def test_nothing_wording_is_quiet_grey(self):
        css = read('problems', 'templates', 'platform', '_stats_style.html')
        block = css.split('.wk-nothing {')[1].split('}')[0]
        self.assertIn('var(--text3)', block)
        self.assertNotIn('background', block)
