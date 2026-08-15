# -*- coding: utf-8 -*-
"""Фаза 9 объединённого ревью 15.08: «Когда занимаешься» считает минуты.

Владелец: «должны показываться не эфемерные кол-ва попыток, а минуты,
проведённые на сайте». Плюс отдельный дефект — правый график (по часам)
был пуст при непустом левом.

⚠️ ПРИЧИНА ПУСТОГО ГРАФИКА НАЙДЕНА, А НЕ ОБОЙДЕНА. Графики читали РАЗНЫЕ
источники по РАЗНЫМ правилам: левый — счётчик `DailySummary
.problems_attempted`, правый — события вида «решено / неверно». У человека,
который только ОТКРЫВАЛ задачи каталога (ровно так выглядит история
репетитора в демо-базе), сводка дня насчитывает попытки, а событий
«решено / неверно» нет ни одного — левый показывает 10, правый ноль, и оба
«правы» по своему правилу. Теперь источник один: те же отметки времени,
по которым считается карточка «Минут на сайте».
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from problems import stats
from problems.models import LearningEvent, Problem
from problems.models_gamification import DailySummary

User = get_user_model()


def at(user, moment, problem=None, event_type='opened'):
    event = LearningEvent.objects.create(user=user, event_type=event_type,
                                         source='catalog',
                                         catalog_problem=problem)
    LearningEvent.objects.filter(pk=event.pk).update(created_at=moment)
    return event


class MinuteSlicesTests(TestCase):
    """Правило разложения минут — то же, что у карточки «Минут на сайте»."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('m9', password='x', role='student')

    def test_sum_of_slices_equals_the_card(self):
        base = timezone.now() - timedelta(days=2)
        for offset in (0, 5, 12, 20):
            at(self.user, base + timedelta(minutes=offset))
        card = stats.minutes_on_site(self.user, 'all')
        by_week = sum(r['value'] for r in stats.minutes_by_weekday(self.user,
                                                                   'all'))
        by_hour = sum(r['value'] for r in stats.minutes_by_hour(self.user,
                                                                'all'))
        self.assertEqual(card, 20 + stats.SESSION_TAIL_MINUTES)
        self.assertEqual(by_week, card)
        self.assertEqual(by_hour, card)

    def test_two_sessions_get_two_tails(self):
        base = timezone.now() - timedelta(days=3)
        at(self.user, base)
        at(self.user, base + timedelta(minutes=10))
        # Разрыв длиннее паузы — это уже другой заход.
        at(self.user, base + timedelta(minutes=10,
                                       seconds=60 * (stats.SESSION_GAP_MINUTES
                                                     + 5)))
        self.assertEqual(stats.minutes_on_site(self.user, 'all'),
                         10 + 2 * stats.SESSION_TAIL_MINUTES)

    def test_slice_never_crosses_the_hour(self):
        """25 минут с 20:50 — это 10 минут одного часа и 15 другого."""
        local = timezone.localtime(timezone.now()).replace(
            hour=20, minute=50, second=0, microsecond=0) - timedelta(days=1)
        at(self.user, local)
        at(self.user, local + timedelta(minutes=25))
        rows = {r['hour']: r['value']
                for r in stats.minutes_by_hour(self.user, 'all')}
        self.assertEqual(rows[20], 10)
        self.assertEqual(rows[21], 15 + stats.SESSION_TAIL_MINUTES)

    def test_no_events_is_an_honest_zero(self):
        empty = User.objects.create_user('m9e', password='x', role='student')
        self.assertEqual(stats.minutes_on_site(empty, 'all'), 0)
        self.assertEqual(sum(r['value']
                             for r in stats.minutes_by_hour(empty, 'all')), 0)


class EmptyHourChartTests(TestCase):
    """Тот самый случай: левый график полон, правый пуст."""

    def test_opened_only_history_used_to_break_the_pair(self):
        """⚠️ Воспроизводим историю репетитора из демо-базы.

        Десять событий «открыл задачу» и сводка дня с десятью попытками.
        Прежние функции давали 10 и 0; новые дают одно и то же число.
        """
        user = User.objects.create_user('m9t', password='x', role='teacher')
        problem = Problem.objects.create(title='З', statement='у',
                                         status=Problem.Status.PUBLISHED)
        base = timezone.now() - timedelta(days=1)
        for index in range(10):
            at(user, base + timedelta(minutes=index), problem=problem)
        DailySummary.objects.create(user=user,
                                    date=timezone.localtime(base).date(),
                                    problems_attempted=10, problems_solved=7)

        # Как было: попытки по дням берутся из сводки, часы — из событий
        # «решено / неверно», которых у этого человека нет вовсе.
        old_week = sum(r['value'] for r in stats.activity_by_weekday(user,
                                                                     'all'))
        old_hour = sum(r['value'] for r in stats.activity_by_hour(user, 'all'))
        self.assertEqual(old_week, 10)
        self.assertEqual(old_hour, 0, 'дефект перестал воспроизводиться')

        # Как стало: один источник, одно правило, числа сходятся.
        new_week = sum(r['value'] for r in stats.minutes_by_weekday(user,
                                                                    'all'))
        new_hour = sum(r['value'] for r in stats.minutes_by_hour(user, 'all'))
        self.assertTrue(new_hour > 0)
        self.assertEqual(new_week, new_hour)
        self.assertEqual(new_week, stats.minutes_on_site(user, 'all'))


class MinuteWordingTests(TestCase):
    """Подписи говорят «мин» и склоняются правильно."""

    def test_declension(self):
        self.assertEqual(stats.minutes_text(1), '1 минута')
        self.assertEqual(stats.minutes_text(3), '3 минуты')
        self.assertEqual(stats.minutes_text(15), '15 минут')
        self.assertEqual(stats.minutes_text(21), '21 минута')
        self.assertEqual(stats.minutes_text(0), '0 минут')

    def test_rows_carry_ready_text(self):
        user = User.objects.create_user('m9w', password='x', role='student')
        at(user, timezone.now() - timedelta(hours=2))
        rows = stats.minutes_by_weekday(user, 'all')
        self.assertTrue(all('text' in row for row in rows))

    def test_chart_script_asks_for_minutes(self):
        """⚠️ Склонение живёт в питоне: на клиенте его копии быть не должно."""
        with open('problems/static/platform/stats.js', encoding='utf-8') as fh:
            script = fh.read()
        self.assertIn("' мин'", script)
        self.assertIn('Минуты на сайте', script)
        self.assertNotIn("'Попыток'", script)
        self.assertNotIn('минуты\', \'минут', script)

    def test_payload_feeds_minutes_to_the_charts(self):
        user = User.objects.create_user('m9p', password='x', role='student')
        at(user, timezone.now() - timedelta(hours=1))
        data = stats.full_stats(user, 'all', use_cache=False)
        self.assertIn('text', data['by_weekday'][0])
        self.assertIn('text', data['by_hour'][0])

    def test_hint_below_the_charts_still_counts_attempts(self):
        """Подсказка отвечает на ДРУГОЙ вопрос — «когда лучше получается»."""
        user = User.objects.create_user('m9h', password='x', role='student')
        problem = Problem.objects.create(title='З2', statement='у',
                                         status=Problem.Status.PUBLISHED)
        local = timezone.localtime(timezone.now()).replace(
            hour=19, minute=0, second=0, microsecond=0) - timedelta(days=1)
        for index in range(6):
            at(user, local + timedelta(minutes=index), problem=problem,
               event_type='solved')
        self.assertIn('Лучше всего',
                      stats.best_time_hint(stats.activity_by_hour(user, 'all')))
