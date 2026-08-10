"""
Слой агрегации и экраны статистики: доступ, разделение ролей, число запросов.

Главное, что стерегут эти тесты:
* чужой репетитор и чужой родитель НЕ видят ученика (404, а не 403);
* у репетитора и родителя на экране НЕТ геймификации;
* родитель не видит НИЧЕГО о работе репетитора;
* страница статистики укладывается в бюджет запросов.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import (
    DailySummary, LearningEvent, ParentLink, StudentGroup,
    StudentProgressProfile,
)
from problems.tests.factories import (
    make_assignment, make_problem, make_topic, make_user,
)


def solve(student, problem, when=None, correct=True, source='catalog',
          seconds=120):
    """Событие в журнале с нужной датой (created_at — auto_now_add)."""
    event = LearningEvent.objects.create(
        user=student, source=source,
        event_type='solved' if correct else 'failed',
        catalog_problem=problem, topic=problem.topics.first(),
        difficulty=problem.difficulty, time_spent_seconds=seconds)
    if when is not None:
        LearningEvent.objects.filter(pk=event.pk).update(created_at=when)
        event.refresh_from_db()
    return event


class AggregationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = make_user('agg_student', role='student')
        cls.topic_a = make_topic('Спрос и предложение')
        cls.topic_b = make_topic('Инфляция')
        cls.p_a = make_problem('A', difficulty=3, topic=cls.topic_a)
        cls.p_b = make_problem('B', difficulty=4, topic=cls.topic_b)
        now = timezone.now()
        for _ in range(6):
            solve(cls.student, cls.p_a, now - timedelta(days=2))
        for _ in range(4):
            solve(cls.student, cls.p_b, now - timedelta(days=2), correct=False)

    def test_overview_counts_attempts_not_openings(self):
        row = stats.overview(self.student, 'month')
        self.assertEqual(row['solved'], 6)
        self.assertEqual(row['attempted'], 10)
        self.assertEqual(row['accuracy'], 60.0)

    def test_accuracy_ignores_skipped(self):
        """Пропуск — не ответ, точность он портить не должен."""
        LearningEvent.objects.create(
            user=self.student, source='catalog', event_type='skipped',
            catalog_problem=self.p_a, topic=self.topic_a)
        self.assertEqual(stats.overview(self.student, 'month')['accuracy'],
                         60.0)

    def test_topic_breakdown(self):
        rows = {r['name']: r for r in
                stats.topic_breakdown(self.student, 'month')}
        self.assertEqual(rows['Спрос и предложение']['accuracy'], 100)
        self.assertEqual(rows['Инфляция']['accuracy'], 0)

    def test_ranking_needs_minimum_attempts(self):
        """Тема с 3 попытками в рейтинг не идёт — это не статистика."""
        topic = make_topic('Редкая тема')
        problem = make_problem('R', difficulty=2, topic=topic)
        for _ in range(3):
            solve(self.student, problem)
        names = [r['name'] for r in
                 stats.strongest_weakest(self.student, 'all')['strong']]
        self.assertNotIn('Редкая тема', names)

    def test_game_is_separate_from_learning(self):
        """Партии игры не попадают в учебную статистику."""
        before = stats.overview(self.student, 'all')['attempted']
        for _ in range(5):
            LearningEvent.objects.create(user=self.student, source='game',
                                         event_type='solved',
                                         payload={'mode': 'blitz'})
        self.assertEqual(stats.overview(self.student, 'all')['attempted'],
                         before)
        self.assertEqual(stats.game_stats(self.student)['attempted'], 5)

    def test_calendar_uses_daily_summaries(self):
        DailySummary.objects.create(user=self.student,
                                    date=timezone.localdate(),
                                    problems_solved=7, xp_earned=40)
        calendar = stats.activity_calendar(self.student, 30)
        today = [c for c in calendar['cells']
                 if c['date'] == timezone.localdate()][0]
        self.assertEqual(today['solved'], 7)
        self.assertEqual(today['level'], 4)
        # Координаты клеток считает питон — шаблон только рисует.
        self.assertIn('x', today)
        self.assertIn('y', today)

    def test_hint_is_neutral(self):
        by_hour = stats.activity_by_hour(self.student, 'all')
        hint = stats.best_time_hint(by_hour)
        for word in ('плохо', 'хуже', 'не получается'):
            self.assertNotIn(word, hint.lower())


class QueryBudgetTests(TestCase):
    """Страница статистики не должна разъезжаться по числу запросов.

    ⚠️ Проверяем ПОТОЛОК, а не точное число: `assertNumQueries` требует
    ровного совпадения и краснеет от любой безобидной правки. Смысл теста —
    «не больше тридцати», а не «ровно девятнадцать».

    Кэш чистим руками: он живёт в процессе и переезжает между тестами, а
    тогда замер показал бы семь запросов вместо настоящих.
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.student = make_user('budget_student', role='student')
        topic = make_topic('Издержки')
        problems = [make_problem('P%d' % i, difficulty=i % 5 + 1, topic=topic)
                    for i in range(10)]
        now = timezone.now()
        for day in range(90):
            for problem in problems[:3]:
                solve(self.student, problem, now - timedelta(days=day))

    BUDGET = 30

    def _count(self, action):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            result = action()
        return len(captured), result

    def test_full_stats_under_budget(self):
        count, _ = self._count(
            lambda: stats.full_stats(self.student, 'month', use_cache=False))
        self.assertLessEqual(count, self.BUDGET,
                             'full_stats: %d запросов' % count)

    def test_page_under_budget(self):
        self.client.force_login(self.student)
        count, response = self._count(
            lambda: self.client.get(reverse('student_stats')))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(count, self.BUDGET,
                             'страница статистики: %d запросов' % count)


class RoleSeparationTests(TestCase):
    """Геймификация — только ученику."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('sep_tutor', role='teacher')
        cls.student = make_user('sep_student', role='student')
        cls.parent = make_user('sep_parent', role='viewer')
        cls.group = StudentGroup.objects.create(name='Г', teacher=cls.tutor)
        cls.group.students.set([cls.student])
        ParentLink.objects.create(parent=cls.parent, student=cls.student)
        StudentProgressProfile.objects.create(
            user=cls.student, xp_total=500, level=4, current_streak=9)

    # Ищем РАЗМЕТКУ, а не слова: общий файл стилей у трёх экранов один, и
    # слово «Достижения» стоит в нём комментарием к правилам — по тексту
    # проверка краснела бы на пустом месте.
    GAMIFICATION_MARKUP = ('class="hero"', 'id="achv-grid"', 'всего опыта',
                           'дней подряд', 'заморозок:')

    def _body(self, url):
        return self.client.get(url).content.decode()

    def test_student_sees_gamification(self):
        self.client.force_login(self.student)
        body = self._body(reverse('student_stats'))
        for marker in self.GAMIFICATION_MARKUP:
            self.assertIn(marker, body, marker)

    def test_tutor_page_has_no_gamification(self):
        self.client.force_login(self.tutor)
        body = self._body(reverse('teacher:student_stats',
                                  args=[self.student.pk]))
        for marker in self.GAMIFICATION_MARKUP:
            self.assertNotIn(marker, body, marker)

    def test_parent_page_has_no_gamification(self):
        self.client.force_login(self.parent)
        body = self._body(reverse('parent_student', args=[self.student.pk]))
        for marker in self.GAMIFICATION_MARKUP:
            self.assertNotIn(marker, body, marker)

    def test_parent_sees_nothing_about_tutor_work(self):
        """Ни скорости проверки, ни времени ответа, ни числа занятий."""
        self.client.force_login(self.parent)
        body = self.client.get(
            reverse('parent_student', args=[self.student.pk])).content.decode()
        for word in ('скорость проверки', 'время ответа', 'занятий проведено',
                     'проверил за', 'ждёт проверки уже'):
            self.assertNotIn(word, body, word)


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('acc_tutor', role='teacher')
        cls.other_tutor = make_user('acc_other_tutor', role='teacher')
        cls.student = make_user('acc_student', role='student')
        cls.parent = make_user('acc_parent', role='viewer')
        cls.other_parent = make_user('acc_other_parent', role='viewer')
        cls.group = StudentGroup.objects.create(name='Г', teacher=cls.tutor)
        cls.group.students.set([cls.student])
        ParentLink.objects.create(parent=cls.parent, student=cls.student)

    def test_foreign_tutor_gets_404_on_student(self):
        self.client.force_login(self.other_tutor)
        response = self.client.get(
            reverse('teacher:student_stats', args=[self.student.pk]))
        self.assertEqual(response.status_code, 404)

    def test_foreign_tutor_gets_404_on_group(self):
        self.client.force_login(self.other_tutor)
        response = self.client.get(
            reverse('teacher:group_stats', args=[self.group.pk]))
        self.assertEqual(response.status_code, 404)

    def test_own_tutor_ok(self):
        """Свой репетитор доходит до карточки ученика.

        ⚠️ С сессии 7 `student_stats` — РЕДИРЕКТ на неё: экранов об одном
        ученике было два, остался один (решение стоп-гейта 10.1). Проверка
        та же по смыслу — «свой репетитор проходит», — поэтому идём по
        редиректу до конца, а не сверяем код 200 у промежуточного адреса.
        Отказ чужому проверяется соседним тестом и остался 404: доступ
        режется на уровне queryset ДО редиректа.
        """
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.get(
            reverse('teacher:student_stats', args=[self.student.pk]),
            follow=True).status_code, 200)

    def test_foreign_parent_gets_404(self):
        self.client.force_login(self.other_parent)
        response = self.client.get(
            reverse('parent_student', args=[self.student.pk]))
        self.assertEqual(response.status_code, 404)

    def test_own_parent_ok(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(
            reverse('parent_student', args=[self.student.pk])).status_code,
            200)

    def test_parent_home_lists_only_own_children(self):
        self.client.force_login(self.other_parent)
        response = self.client.get(reverse('parent_home'))
        self.assertEqual(list(response.context['rows']), [])

    def test_stats_require_login(self):
        for name in ('student_stats', 'parent_home'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)


class ProgressPageAbsorbedTests(TestCase):
    """Старая страница «Прогресс» поглощена — двух разделов нет."""

    def test_old_progress_redirects_to_stats(self):
        student = make_user('abs_student', role='student')
        self.client.force_login(student)
        response = self.client.get(reverse('student:progress'))
        self.assertRedirects(response, reverse('student_stats'))


class GroupStatsContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tutor = make_user('gs_tutor', role='teacher')
        cls.first = make_user('gs_one', role='student')
        cls.second = make_user('gs_two', role='student')
        cls.group = StudentGroup.objects.create(name='Г', teacher=cls.tutor)
        cls.group.students.set([cls.first, cls.second])
        topic = make_topic('Монополия')
        problem = make_problem('M', difficulty=3, topic=topic)
        now = timezone.now()
        for _ in range(4):
            solve(cls.first, problem, now - timedelta(days=1))
        for _ in range(4):
            solve(cls.second, problem, now - timedelta(days=1), correct=False)

    def test_matrix_shows_both_students(self):
        matrix = stats.group_topic_matrix(self.group, 'all')
        self.assertEqual(len(matrix['matrix']), 2)
        self.assertEqual(matrix['columns'][0]['name'], 'Монополия')
        accuracies = sorted(row['cells'][0]['accuracy']
                            for row in matrix['matrix'])
        self.assertEqual(accuracies, [0, 100])

    def test_group_table_has_no_xp_column(self):
        rows = stats.group_table(self.group, 'all')
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertNotIn('xp', row)
            self.assertNotIn('level', row)

    def test_attention_ignores_work_with_open_deadline(self):
        """Работа, срок которой ещё не прошёл, не повод бить тревогу."""
        make_assignment(self.tutor, students=[self.first, self.second],
                        problems=[make_problem('Z')], group=self.group,
                        deadline=timezone.now() + timedelta(days=5))
        reasons = [r for row in stats.needs_attention(self.group)
                   for r in row['reasons']]
        self.assertFalse([r for r in reasons if 'не сдал' in r], reasons)
