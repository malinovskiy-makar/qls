"""
Обзор кабинета 13.08.2026, фаза 12 — минуты на сайте на ЖИВЫХ данных
и пустая карточка «Средняя сложность работ» у индивидуального ученика.

⚠️ Синтетика проверялась в сессии 10 (`test_minutes_on_site`). Здесь другое:
события ставятся так, как их пишет `seed_platform_demo` — сотнями, из
четырёх источников, по всему месяцу, — и проверяется, что число собирается
из объяснимых частей, а не берётся ниоткуда.
"""
import re
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from problems import stats
from problems.models import LearningEvent, StudentGroup
from problems.tests.factories import make_user


def pieces(user, period='month', now=None):
    """Разбор числа на части: промежутки, сессии, хвост.

    Считаем НЕЗАВИСИМО от `minutes_on_site` — иначе проверка сверяла бы
    функцию сама с собой.
    """
    start, end = stats.period_bounds(period, now)
    events = LearningEvent.objects.filter(user=user)
    if start is not None:
        events = events.filter(created_at__gte=start, created_at__lt=end)
    stamps = list(events.order_by('created_at')
                  .values_list('created_at', flat=True))
    if not stamps:
        return {'gaps': 0.0, 'sessions': 0, 'total': 0}
    gap = timedelta(minutes=stats.SESSION_GAP_MINUTES)
    sessions, inside = 1, timedelta()
    for before, after in zip(stamps, stamps[1:]):
        step = after - before
        if step <= gap:
            inside += step
        else:
            sessions += 1
    total = inside + sessions * timedelta(minutes=stats.SESSION_TAIL_MINUTES)
    return {'gaps': inside.total_seconds() / 60, 'sessions': sessions,
            'total': int(round(total.total_seconds() / 60))}


class LiveShapedTests(TestCase):
    """Событий как в демо: много, из четырёх источников, за месяц."""

    def setUp(self):
        self.now = timezone.now()
        self.student = make_user('lm_student', role='student')
        # Двадцать заходов по шесть действий: между действиями 4 минуты,
        # между заходами — сутки. Ровно та форма, что у демо-ученика.
        stamps = []
        for day in range(20):
            base = self.now - timedelta(days=day + 1)
            for step in range(6):
                stamps.append(base + timedelta(minutes=4 * step))
        sources = ('homework', 'exam', 'catalog', 'game')
        for index, when in enumerate(stamps):
            event = LearningEvent.objects.create(
                user=self.student, source=sources[index % 4],
                event_type='solved')
            LearningEvent.objects.filter(pk=event.pk).update(created_at=when)

    def test_the_number_is_made_of_explainable_parts(self):
        part = pieces(self.student, 'month', self.now)
        self.assertEqual(stats.minutes_on_site(self.student, 'month',
                                               self.now), part['total'])

    def test_sessions_are_the_visits(self):
        self.assertEqual(pieces(self.student, 'month', self.now)['sessions'], 20)

    def test_the_number_is_plausible(self):
        """Двадцать заходов по 20 минут — примерно 20×(20+хвост)."""
        minutes = stats.minutes_on_site(self.student, 'month', self.now)
        self.assertEqual(minutes, 20 * (4 * 5 + stats.SESSION_TAIL_MINUTES))

    def test_game_counts_as_time_on_site(self):
        """Решение владельца: это время НА САЙТЕ, а не «учебное время»."""
        without = LearningEvent.objects.filter(
            user=self.student).exclude(source='game').count()
        self.assertLess(without,
                        LearningEvent.objects.filter(user=self.student).count())
        before = stats.minutes_on_site(self.student, 'month', self.now)
        LearningEvent.objects.filter(user=self.student, source='game').delete()
        self.assertLess(stats.minutes_on_site(self.student, 'month', self.now),
                        before)


class UpperBoundTests(TestCase):
    """Верхняя граница: чем число МОЖЕТ быть раздуто, а чем не может."""

    def setUp(self):
        self.now = timezone.now()
        self.student = make_user('ub_student', role='student')

    def _put(self, offsets_minutes):
        # ⚠️ Сдвиг на минуту: у периода «месяц» правая граница — РОВНО
        # `now`, и фильтр берёт события строго ДО неё. Событие с нулевым
        # смещением в выборку не попадает вовсе.
        offsets_minutes = [offset + 1 for offset in offsets_minutes]
        for offset in offsets_minutes:
            event = LearningEvent.objects.create(
                user=self.student, source='catalog', event_type='solved')
            LearningEvent.objects.filter(pk=event.pk).update(
                created_at=self.now - timedelta(minutes=offset))

    def test_a_burst_of_close_events_does_not_inflate(self):
        """Пачка событий с близкими метками даёт КРОШЕЧНЫЕ промежутки."""
        self._put([100 - index * 0.01 for index in range(200)])
        minutes = stats.minutes_on_site(self.student, 'month', self.now)
        self.assertLessEqual(minutes, stats.SESSION_TAIL_MINUTES + 2)

    def test_identical_stamps_add_nothing(self):
        self._put([50] * 30)
        self.assertEqual(stats.minutes_on_site(self.student, 'month', self.now),
                         stats.SESSION_TAIL_MINUTES)

    def test_one_gap_can_add_at_most_the_session_gap(self):
        """Забытая вкладка событий НЕ ПИШЕТ, но и пауза ограничена сверху."""
        self._put([0, stats.SESSION_GAP_MINUTES])
        self.assertEqual(
            stats.minutes_on_site(self.student, 'month', self.now),
            stats.SESSION_GAP_MINUTES + stats.SESSION_TAIL_MINUTES)

    def test_a_longer_pause_is_a_new_visit_not_time(self):
        self._put([0, stats.SESSION_GAP_MINUTES + 1])
        self.assertEqual(stats.minutes_on_site(self.student, 'month', self.now),
                         2 * stats.SESSION_TAIL_MINUTES)

    def test_minutes_never_exceed_the_span_of_the_events(self):
        """Число не может быть больше времени между первым и последним."""
        self._put([0, 10, 25, 40, 55, 70])
        span = 70 + stats.SESSION_TAIL_MINUTES * 3
        self.assertLessEqual(
            stats.minutes_on_site(self.student, 'month', self.now), span)

    def test_events_outside_the_period_are_not_counted(self):
        self._put([5, 10, 60 * 24 * 40])
        month = stats.minutes_on_site(self.student, 'month', self.now)
        self.assertLess(month, stats.minutes_on_site(self.student, 'all',
                                                     self.now))


class DemoDifficultyTests(TestCase):
    """12.2 — карточка «Средняя сложность работ» у одного на один."""

    def test_seed_gives_the_solo_student_a_rating(self):
        """⚠️ Тест ГОНЯЕТ НАСТОЯЩУЮ КОМАНДУ демо-данных.

        Проверять это на выдуманных объектах бессмысленно: дефект был
        именно в том, КОГО команда передаёт в простановку оценок.
        """
        from django.core.management import call_command

        from problems.models_platform import WorkDifficulty, difficulty_for_student

        call_command('seed_platform_demo', verbosity=0)
        solo = StudentGroup.objects.filter(
            kind=StudentGroup.Kind.INDIVIDUAL).first()
        self.assertIsNotNone(solo, 'в демо нет индивидуального занятия')
        student = solo.students.first()
        self.assertIsNotNone(student)
        self.assertTrue(
            WorkDifficulty.objects.filter(student=student).exists(),
            'у индивидуального ученика нет ни одной оценки сложности')
        self.assertIsNotNone(difficulty_for_student(student))

    def test_the_average_is_formatted_in_one_place(self):
        """⚠️ «7.0» превращалось в «70» по шкале от 1 до 10.

        В шаблоне обзора стояло `stringformat:"s"|cut:"."` — попытка убрать
        точку из числа. Она убирала её вместе со смыслом, и увидеть это было
        нельзя, пока у индивидуального ученика не появилось ни одной оценки.
        """
        from problems.models_platform import difficulty_label

        self.assertEqual(difficulty_label(7.0), '7,0 из 10')
        self.assertEqual(difficulty_label(4.35), '4,3 из 10')
        self.assertIsNone(difficulty_label(None))

    def test_no_screen_formats_it_by_itself(self):
        import os

        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        page = open(os.path.join(root, 'teacher', 'templates', 'teacher',
                                 'groups', '_overview.html'),
                    encoding='utf-8').read()
        self.assertNotIn('stringformat:"s"|cut:"."', page)

    def test_the_card_shows_the_scale(self):
        from django.core.management import call_command
        from django.urls import reverse

        from problems.models import StudentGroup, User

        call_command('seed_platform_demo', verbosity=0)
        tutor = User.objects.get(username='tutor@test.local')
        solo = StudentGroup.objects.filter(
            kind=StudentGroup.Kind.INDIVIDUAL).first()
        self.client.force_login(tutor)
        html = self.client.get(
            reverse('teacher:group_detail', args=[solo.pk])).content.decode()
        part = html.split('Средняя сложность работ')[1]
        value = re.search(r'class="card3-value">(.*?)</div>', part, re.S).group(1)
        shown = re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', value)).strip()
        self.assertIn('из 10', shown)
        self.assertNotEqual(shown, 'нет оценок')

    def test_the_question_is_asked_to_the_student(self):
        """Оценку ставит ученик на разборе работы — механизм на месте."""
        import os

        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        page = open(os.path.join(root, 'student', 'templates', 'student',
                                 'work_review.html'), encoding='utf-8').read()
        self.assertIn('Насколько сложной была работа?', page)
        self.assertIn("student:rate_difficulty", page)
        # ⚠️ Спрашивают ТОЛЬКО ученика: репетитору этот блок не показывают.
        self.assertIn('{% if not for_tutor %}', page)
