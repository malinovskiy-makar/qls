"""
Движок начисления: опыт, уровни, серия дней, владение темами, достижения.

Отдельный класс тестов — про АНТИФАРМ: правило «решать лёгкое ради очков
невыгодно» проверяется арифметикой, а не на глаз.
"""
from datetime import date, timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from problems import gamification as g
from problems.models import (
    Achievement, Assignment, DailySummary, EarnedAchievement, LearningEvent,
    PersonalRecord, StudentProgressProfile, StudentTopicProgress,
)
from problems.tests.factories import make_problem, make_topic, make_user


class AntiFarmArithmeticTests(TestCase):
    """Час лёгких задач обязан давать МЕНЬШЕ опыта, чем час трудных."""

    # Оценка времени решения (минуты), та же, что в докстринге движка.
    MINUTES = {1: 1.5, 2: 3, 3: 8, 4: 20, 5: 35}

    def test_xp_per_hour_grows_with_difficulty(self):
        rates = []
        for difficulty in (1, 2, 3, 4, 5):
            rate = g.base_xp(difficulty) / self.MINUTES[difficulty] * 60
            rates.append(rate)
        self.assertEqual(rates, sorted(rates),
                         'опыт в час должен расти со сложностью: %s' % rates)

    def test_hour_of_easy_farming_loses_to_hour_of_hard(self):
        """Считаем ЧЕСТНЫЙ час фарма — с затуханием, как в бою."""
        minutes, easy_done, easy_xp = 0.0, 0, 0
        while minutes + self.MINUTES[1] <= 60:
            easy_xp += g.xp_for_solved(1, easy_solved_today=easy_done)
            easy_done += 1
            minutes += self.MINUTES[1]

        hard_xp = int(60 / self.MINUTES[4]) * g.xp_for_solved(4)
        self.assertLess(easy_xp, hard_xp,
                        'фарм лёгкого (%d) не должен обгонять '
                        'сложное (%d)' % (easy_xp, hard_xp))

    def test_decay_never_touches_serious_problems(self):
        """Задачам сложности 3+ затухание не грозит никогда."""
        for difficulty in (3, 4, 5):
            self.assertEqual(g.xp_for_solved(difficulty, easy_solved_today=0),
                             g.xp_for_solved(difficulty,
                                             easy_solved_today=99))

    def test_unknown_difficulty_is_treated_as_easy(self):
        """Иначе «сложность не проставлена» стала бы дырой для фарма."""
        self.assertTrue(g.is_easy(None))
        self.assertLess(g.xp_for_solved(None, easy_solved_today=30),
                        g.xp_for_solved(None, easy_solved_today=0))


class XpRulesTests(TestCase):
    def test_exam_multiplier(self):
        self.assertEqual(g.xp_for_solved(4, source='exam'),
                         int(round(g.xp_for_solved(4) * g.EXAM_MULTIPLIER)))

    def test_decay_steps(self):
        self.assertEqual(g.easy_decay(0), 1.0)
        self.assertEqual(g.easy_decay(g.EASY_FULL_PER_DAY - 1), 1.0)
        self.assertEqual(g.easy_decay(g.EASY_FULL_PER_DAY),
                         g.EASY_HALF_FACTOR)
        self.assertEqual(g.easy_decay(g.EASY_HALF_UNTIL), g.EASY_TAIL_FACTOR)


class LevelTests(TestCase):
    def test_starts_at_first_level(self):
        self.assertEqual(g.level_for_xp(0), 1)
        self.assertEqual(g.level_for_xp(-5), 1)

    def test_thresholds(self):
        self.assertEqual(g.xp_for_level(1), 0)
        self.assertEqual(g.xp_for_level(2), 100)
        self.assertEqual(g.xp_for_level(3), int(100 * 2 ** 1.5))

    def test_boundaries_exact(self):
        for level in range(2, 12):
            need = g.xp_for_level(level)
            self.assertEqual(g.level_for_xp(need - 1), level - 1, level)
            self.assertEqual(g.level_for_xp(need), level, level)

    def test_xp_to_next(self):
        remaining, need = g.xp_to_next_level(99)
        self.assertEqual(need, 100)
        self.assertEqual(remaining, 1)

    def test_progress_percent_within_range(self):
        for xp in (0, 50, 99, 100, 500, 5000):
            self.assertGreaterEqual(g.level_progress_percent(xp), 0)
            self.assertLessEqual(g.level_progress_percent(xp), 100)


class MasteryTests(TestCase):
    def test_thresholds(self):
        self.assertEqual(g.mastery_for(0, 0, 0), 'none')
        self.assertEqual(g.mastery_for(3, 4, 0), 'familiar')
        self.assertEqual(g.mastery_for(8, 12, 0), 'confident')
        self.assertEqual(g.mastery_for(15, 18, 3), 'mastered')

    def test_mastered_requires_hard_problems(self):
        """15 решённых с долей 83%, но ни одной трудной — не «разобрался»."""
        self.assertEqual(g.mastery_for(15, 18, 0), 'confident')

    def test_confident_requires_ratio(self):
        self.assertEqual(g.mastery_for(8, 20, 0), 'familiar')


class StreakEngineTests(TestCase):
    """Серия дней: продление, заморозка, обнуление, новый месяц."""

    def setUp(self):
        self.student = make_user('streaker', role='student')
        self.profile = StudentProgressProfile.objects.create(user=self.student)

    def _count_day(self, day):
        """Отмечает день как зачтённый и прогоняет обновление серии."""
        summary, _ = DailySummary.objects.get_or_create(
            user=self.student, date=day,
            defaults={'problems_attempted': g.STREAK_MIN_ATTEMPTS})
        summary.problems_attempted = g.STREAK_MIN_ATTEMPTS
        summary.save()
        g._update_streak(self.profile, summary, day)
        self.profile.save()

    def test_one_trivial_problem_does_not_count_the_day(self):
        """Одна задача поздно вечером день НЕ засчитывает — намеренно."""
        self.assertFalse(g.day_counts_for_streak(1, False))
        self.assertTrue(g.day_counts_for_streak(g.STREAK_MIN_ATTEMPTS, False))
        # Сдал работу — засчитан даже при одной попытке.
        self.assertTrue(g.day_counts_for_streak(1, True))

    def test_consecutive_days_extend(self):
        start = date(2026, 3, 2)
        for shift in range(3):
            self._count_day(start + timedelta(days=shift))
        self.assertEqual(self.profile.current_streak, 3)
        self.assertEqual(self.profile.longest_streak, 3)

    def test_gap_uses_freeze(self):
        start = date(2026, 3, 2)
        self._count_day(start)
        self._count_day(start + timedelta(days=2))    # пропущен один день
        self.assertEqual(self.profile.current_streak, 2)
        self.assertEqual(self.profile.freezes_available,
                         g.FREEZES_PER_MONTH - 1)
        self.assertEqual(self.profile.freezes_used_this_month, 1)

    def test_gap_without_freezes_resets(self):
        start = date(2026, 3, 2)
        self._count_day(start)
        self.profile.freezes_available = 0
        self.profile.save()
        self._count_day(start + timedelta(days=3))
        self.assertEqual(self.profile.current_streak, 1)
        self.assertEqual(self.profile.longest_streak, 1)

    def test_longest_survives_reset(self):
        start = date(2026, 3, 2)
        for shift in range(4):
            self._count_day(start + timedelta(days=shift))
        self.profile.freezes_available = 0
        self.profile.save()
        self._count_day(start + timedelta(days=10))
        self.assertEqual(self.profile.current_streak, 1)
        self.assertEqual(self.profile.longest_streak, 4)

    def test_freezes_reset_on_first_of_month(self):
        self._count_day(date(2026, 3, 20))
        self.profile.freezes_available = 0
        self.profile.freezes_used_this_month = 2
        self.profile.save()
        self._count_day(date(2026, 4, 1))
        self.assertEqual(self.profile.freezes_available, g.FREEZES_PER_MONTH)
        self.assertEqual(self.profile.freezes_used_this_month, 0)

    def test_same_day_twice_does_not_extend(self):
        day = date(2026, 3, 5)
        self._count_day(day)
        self._count_day(day)
        self.assertEqual(self.profile.current_streak, 1)


class AwardingTests(TestCase):
    """Начисление по факту события — через настоящий журнал."""

    def setUp(self):
        self.student = make_user('earner', role='student')
        self.topic = make_topic('Эластичность')

    def _solve(self, difficulty=3, problem=None, source='catalog'):
        from problems.event_log import log_problem_event

        problem = problem or make_problem('З', difficulty=difficulty,
                                          topic=self.topic)
        return log_problem_event(source, 'solved', self.student, problem)

    def test_solving_gives_xp(self):
        self._solve(difficulty=4)
        profile = StudentProgressProfile.objects.get(user=self.student)
        self.assertEqual(profile.xp_total, g.xp_for_solved(4))

    def test_wrong_attempt_gives_nothing_and_takes_nothing(self):
        from problems.event_log import log_problem_event

        problem = make_problem('З', difficulty=4, topic=self.topic)
        log_problem_event('catalog', 'solved', self.student, problem)
        before = StudentProgressProfile.objects.get(user=self.student).xp_total
        other = make_problem('Д', difficulty=4, topic=self.topic)
        log_problem_event('catalog', 'failed', self.student, other)
        after = StudentProgressProfile.objects.get(user=self.student).xp_total
        self.assertEqual(before, after)

    def test_solving_same_problem_twice_gives_xp_once(self):
        problem = make_problem('Повтор', difficulty=4, topic=self.topic)
        self._solve(problem=problem)
        first = StudentProgressProfile.objects.get(user=self.student).xp_total
        self._solve(problem=problem)
        second = StudentProgressProfile.objects.get(user=self.student).xp_total
        self.assertEqual(first, second)

    def test_topic_mastery_counters_grow(self):
        for _ in range(3):
            self._solve(difficulty=2)
        row = StudentTopicProgress.objects.get(student=self.student,
                                               topic=self.topic)
        self.assertEqual(row.solved, 3)
        self.assertEqual(row.attempted, 3)
        self.assertEqual(row.mastery_level, 'familiar')

    def test_daily_summary_written(self):
        self._solve(difficulty=3)
        summary = DailySummary.objects.get(user=self.student,
                                           date=timezone.localdate())
        self.assertEqual(summary.problems_solved, 1)
        self.assertEqual(summary.xp_earned, g.xp_for_solved(3))

    def test_record_of_correct_row(self):
        for _ in range(4):
            self._solve(difficulty=2)
        record = PersonalRecord.objects.get(
            user=self.student, kind=PersonalRecord.Kind.BEST_CORRECT_STREAK)
        self.assertEqual(record.value, 4)


class AchievementTests(TestCase):
    def setUp(self):
        call_command('seed_achievements', verbosity=0)
        self.student = make_user('achiever', role='student')
        self.topic = make_topic('Издержки')

    def test_seed_is_idempotent(self):
        first = Achievement.objects.count()
        call_command('seed_achievements', verbosity=0)
        self.assertEqual(Achievement.objects.count(), first)
        self.assertGreaterEqual(first, 25)

    def test_first_solved_awarded(self):
        from problems.event_log import log_problem_event

        log_problem_event('catalog', 'solved', self.student,
                          make_problem('З', difficulty=3, topic=self.topic))
        codes = set(EarnedAchievement.objects.filter(user=self.student)
                    .values_list('achievement__code', flat=True))
        self.assertIn('first_solved', codes)

    def test_unknown_condition_never_awards(self):
        self.assertFalse(g.condition_met({'type': 'опечатка', 'value': 1},
                                         {'problems_solved': 999}))

    def test_rarity_percent_is_a_share(self):
        achievement = Achievement.objects.get(code='first_solved')
        StudentProgressProfile.objects.create(user=self.student, xp_total=50)
        EarnedAchievement.objects.create(user=self.student,
                                         achievement=achievement)
        from django.core.cache import cache
        cache.clear()
        self.assertEqual(achievement.rarity_percent(), 100.0)


class RecalculateTests(TestCase):
    """Пересчёт даёт то же, что накопление по одному, и идемпотентен."""

    def setUp(self):
        self.student = make_user('recalc', role='student')
        self.topic = make_topic('Спрос')

    def _history(self):
        from problems.event_log import log_problem_event

        for difficulty in (1, 1, 2, 3, 4, 5):
            log_problem_event('catalog', 'solved', self.student,
                              make_problem('З%d' % difficulty,
                                           difficulty=difficulty,
                                           topic=self.topic))

    def test_recalculation_matches_incremental(self):
        self._history()
        before = StudentProgressProfile.objects.get(user=self.student)
        xp_before, level_before = before.xp_total, before.level

        call_command('recalculate_gamification', verbosity=0)
        after = StudentProgressProfile.objects.get(user=self.student)
        self.assertEqual(after.xp_total, xp_before)
        self.assertEqual(after.level, level_before)

    def test_recalculation_is_idempotent(self):
        self._history()
        call_command('recalculate_gamification', verbosity=0)
        first = StudentProgressProfile.objects.get(user=self.student).xp_total
        days_first = DailySummary.objects.filter(user=self.student).count()
        call_command('recalculate_gamification', verbosity=0)
        second = StudentProgressProfile.objects.get(user=self.student).xp_total
        self.assertEqual(first, second)
        self.assertEqual(days_first,
                         DailySummary.objects.filter(user=self.student).count())

    def test_dry_run_writes_nothing(self):
        self._history()
        before = StudentProgressProfile.objects.get(user=self.student).xp_total
        LearningEvent.objects.filter(user=self.student).update(difficulty=5)
        call_command('recalculate_gamification', dry_run=True, verbosity=0)
        self.assertEqual(
            StudentProgressProfile.objects.get(user=self.student).xp_total,
            before)


class ParentLinkTests(TestCase):
    def test_children_and_parents(self):
        from problems.models import ParentLink, UserProfile

        parent = make_user('mama', role='viewer')
        first = make_user('kid1', role='student')
        second = make_user('kid2', role='student')
        ParentLink.objects.create(parent=parent, student=first)
        ParentLink.objects.create(parent=parent, student=second)

        profile, _ = UserProfile.objects.get_or_create(
            user=parent, defaults={'role': 'parent'})
        self.assertEqual(set(profile.children()), {first, second})

        child_profile, _ = UserProfile.objects.get_or_create(user=first)
        self.assertEqual(list(child_profile.parents()), [parent])

    def test_pair_is_unique(self):
        from django.db import IntegrityError

        from problems.models import ParentLink
        parent = make_user('papa', role='viewer')
        child = make_user('kid3', role='student')
        ParentLink.objects.create(parent=parent, student=child)
        with self.assertRaises(IntegrityError):
            ParentLink.objects.create(parent=parent, student=child)
