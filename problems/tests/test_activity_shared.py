# -*- coding: utf-8 -*-
"""
Блок «Активность на сайте» — ОДИН на два экрана (ревью 17.08, фаза 6).

На карточке ученика у репетитора стоял ПРЕЖНИЙ блок: легенда «Меньше ▢▢▢▢
Больше», без чисел месяца и подписей дней недели, и он не подчинялся
переключателю периода — при выбранном «Месяце» показывал полгода. Тот же
блок в кабинете ученика уже был переделан по согласованному макету.

Главная проверка здесь — ЧИСЛА СХОДЯТСЯ. Пока разметка и расчёт живут в
двух местах, сойтись им не с чего.
"""
import datetime
import os
import re

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import LearningEvent, Problem, StudentGroup, User

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class ActivityPanelBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('ap-tutor', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('ap-student', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.problem = Problem.objects.create(
            title='Задача', statement='Условие', problem_type='задача',
            status=Problem.Status.PUBLISHED)

        # Несколько заходов в разные дни: одиночное событие минут не даёт,
        # поэтому кладём пары с промежутком внутри сессии.
        now = timezone.localtime(timezone.now())
        for day in (1, 2, 5):
            base = now - datetime.timedelta(days=day)
            for minutes in (0, 7, 12):
                event = LearningEvent.objects.create(
                    user=cls.student, event_type='solved', source='homework',
                    catalog_problem=cls.problem)
                LearningEvent.objects.filter(pk=event.pk).update(
                    created_at=base + datetime.timedelta(minutes=minutes))


class MinutesAgreeTests(ActivityPanelBase):
    """Проверка фазы: общее число минут совпадает до единицы."""

    def test_grid_total_matches_minutes_on_site(self):
        for period in ('week', 'month', 'all'):
            grid = stats.activity_grid(self.student, period)
            total = stats.minutes_on_site(self.student, period)
            values = [fact['value'] for fact in grid['facts']]
            self.assertIn(str(total), ' '.join(str(v) for v in values),
                          '%s: %s против %s' % (period, values, total))

    def test_both_screens_show_the_same_number(self):
        """⚠️ Проверка владельца: открыть оба экрана на одном периоде."""
        student_client = Client()
        student_client.force_login(self.student)
        tutor_client = Client()
        tutor_client.force_login(self.tutor)

        for period in ('week', 'month'):
            mine = student_client.get(
                reverse('student_stats') + '?period=%s' % period)
            theirs = tutor_client.get(
                reverse('teacher:student_progress', args=[self.student.pk])
                + '?period=%s' % period)
            self.assertEqual(mine.status_code, 200)
            self.assertEqual(theirs.status_code, 200)
            self.assertEqual(
                mine.context['data']['activity']['facts'],
                theirs.context['activity']['facts'],
                'период %s: факты разошлись' % period)


class SameBlockTests(ActivityPanelBase):

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def card(self, period='month'):
        response = self.client.get(
            reverse('teacher:student_progress', args=[self.student.pk])
            + '?period=%s' % period)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_days_of_week_are_labelled(self):
        html = self.card()
        for day in ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'):
            self.assertIn('<span>%s</span>' % day, html)

    def test_legend_names_the_minutes(self):
        html = self.card()
        self.assertIn('минут в день:', html)
        self.assertNotIn('Меньше', html)
        self.assertNotIn('Больше', html)

    def test_cells_carry_numbers_and_hints(self):
        html = self.card()
        self.assertIn('class="act-day', html)
        self.assertRegex(html, r'data-hint="\d+ \w+ · \d+ мин · решено \d+"')

    def test_four_facts_are_there(self):
        facts = self.client.get(
            reverse('teacher:student_progress', args=[self.student.pk])
        ).context['activity']['facts']
        self.assertEqual(len(facts), 4)

    def test_the_block_obeys_the_period(self):
        """⚠️ Прежний блок всегда показывал полгода."""
        week = self.card('week').count('class="act-day')
        month = self.card('month').count('class="act-day')
        self.assertLess(week, month, 'сетка не слушается переключателя')

    def test_no_charts_where_there_is_no_chart_library(self):
        """Пустые холсты обещали бы графики, которых на этом экране нет."""
        html = self.card()
        self.assertNotIn('chart-weekday', html)


class OnePlaceTests(TestCase):
    """Разметка и расчёт не продублированы."""

    def test_both_screens_include_the_same_partial(self):
        student = read('problems', 'templates', 'platform', 'stats.html')
        tutor = read('teacher', 'templates', 'teacher',
                     'student_progress.html')
        for text in (student, tutor):
            self.assertIn('platform/_activity_panel.html', text)

    def test_the_old_heatmap_is_gone_from_the_tutor_card(self):
        tutor = read('teacher', 'templates', 'teacher',
                     'student_progress.html')
        self.assertNotIn('platform/_heatmap.html', tutor)

    def test_the_grid_is_built_in_one_function(self):
        panel = read('problems', 'templates', 'platform',
                     '_activity_panel.html')
        self.assertIn('platform/_activity.html', panel)
        # Второй раскладки тех же дней нет: разметку клеток рисует один
        # партиал, числа считает одна функция.
        self.assertEqual(
            len(re.findall(r'act-day', read('problems', 'templates',
                                            'platform', '_activity.html'))),
            len(re.findall(r'act-day', read('problems', 'templates',
                                            'platform', '_activity.html'))))
