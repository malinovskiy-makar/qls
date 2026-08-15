# -*- coding: utf-8 -*-
"""Фаза 8 объединённого ревью 15.08: карточка ученика и личная статистика.

8.1 Блок «Сильные и слабые темы» больше НЕ ИСЧЕЗАЕТ. Проверено вживую:
    при периоде «Месяц» его не было вообще, при `?period=all` появлялся, —
    владелец решил, что фича пропала. Блок стоит при всех четырёх
    периодах; когда сравнивать нечего, внутри объяснение словами.
8.2 Значения личных фактов (класс, город, цель) заметнее меток.
8.3 Карточка «Лучший день» — ПРОВЕРКА, не переделка: показывается дата и
    работает подсказка-вопросик.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.utils import timezone

from problems.models import LearningEvent, StudentGroup, Topic
from problems.models_gamification import DailySummary, PersonalRecord
from problems.models_platform import UserProfile
from problems.stats import MIN_ATTEMPTS_FOR_RANKING, PERIODS, strongest_weakest

User = get_user_model()


class RankingAlwaysThereTests(TestCase):
    """8.1 — блок есть при любом периоде и при любом количестве данных."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t8', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('s8', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Г8', teacher=cls.tutor)
        cls.group.students.add(cls.student)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def card(self, period):
        response = self.client.get('/teacher/student/%d/progress/?period=%s'
                                   % (self.student.pk, period))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_block_is_present_for_every_period(self):
        for key, _label in PERIODS:
            self.assertIn('Сильные и слабые темы', self.card(key),
                          'блок пропал на периоде «%s»' % key)

    def test_short_data_is_explained_in_words(self):
        html = self.card('month')
        self.assertIn('не набрала %d попыток' % MIN_ATTEMPTS_FOR_RANKING, html)

    def test_narrow_period_suggests_a_wider_one(self):
        self.assertIn('период шире', self.card('month'))

    def test_all_time_does_not_suggest_a_wider_period(self):
        """⚠️ Шире «Всё время» ничего нет — совет был бы издевательством."""
        self.assertNotIn('период шире', self.card('all'))

    def test_one_ranked_topic_is_not_enough(self):
        """Делить на сильные и слабые можно начиная с двух тем."""
        topic = Topic.objects.create(name='Спрос')
        result = strongest_weakest(self.student, 'all', rows=[
            {'name': topic.name, 'attempted': MIN_ATTEMPTS_FOR_RANKING,
             'solved': 3, 'accuracy': 60},
        ])
        self.assertFalse(result['enough_data'])
        self.assertIn('одна тема', result['note'])

    def test_two_ranked_topics_fill_the_halves(self):
        rows = [
            {'name': 'Спрос', 'attempted': 10, 'solved': 9, 'accuracy': 90},
            {'name': 'Издержки', 'attempted': 8, 'solved': 2, 'accuracy': 25},
        ]
        result = strongest_weakest(self.student, 'all', rows=rows)
        self.assertTrue(result['enough_data'])
        self.assertEqual(result['note'], '')
        self.assertEqual([r['name'] for r in result['strong']], ['Спрос'])
        self.assertEqual([r['name'] for r in result['weak']], ['Издержки'])

    def test_halves_never_overlap(self):
        rows = [{'name': 'Т%d' % i, 'attempted': 10, 'solved': i,
                 'accuracy': i * 10} for i in range(1, 9)]
        result = strongest_weakest(self.student, 'all', rows=rows)
        names = {r['name'] for r in result['strong']}
        self.assertFalse(names & {r['name'] for r in result['weak']})

    def test_markup_lives_in_one_partial(self):
        """Три экрана рисуют блок ОДНИМ партиалом, а не тремя копиями."""
        for path in ('teacher/student_progress.html',
                     'teacher/groups/student_stats.html',
                     'platform/stats.html'):
            with open('/'.join(['.', _find(path)]), encoding='utf-8') as fh:
                body = fh.read()
            self.assertIn('_ranking.html', body, path)


def _find(template):
    """Путь к шаблону на диске — по тем же каталогам, что у Django."""
    from django.template.loader import get_template

    return get_template(template).origin.name.split('qls_platform/')[-1]


class StudentFactsTests(TestCase):
    """8.2 — класс, город и цель читаются, а не прячутся в подпись."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t8f', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('s8f', password='x',
                                               role='student',
                                               first_name='Пётр')
        cls.group = StudentGroup.objects.create(name='Г8ф', teacher=cls.tutor)
        cls.group.students.add(cls.student)
        profile, _ = UserProfile.objects.get_or_create(user=cls.student)
        profile.grade = 9
        profile.city = 'Москва'
        profile.goal = 'призёр регионального этапа'
        profile.save()

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def test_values_are_marked_up_separately_from_labels(self):
        html = self.client.get('/teacher/student/%d/progress/'
                               % self.student.pk).content.decode()
        self.assertIn('<b class="fact">Москва</b>', html)
        self.assertIn('<span class="cap">город</span>', html)

    def test_value_is_bigger_and_denser_than_the_label(self):
        style = render_to_string('platform/_stats_style.html')
        self.assertIn('.student-facts { display: flex', style)
        self.assertIn('font-size: 14px', style.split('.student-facts')[1][:200])
        self.assertIn('.student-facts .fact { font-weight: 600', style)
        # Метка осталась мелкой: заметнее — не значит «всё крупное».
        self.assertIn('.student-facts .cap { font-size: 11px', style)

    def test_separator_is_drawn_by_css(self):
        """Литеральной точки в разметке нет — иначе она висела бы у
        единственного факта."""
        markup = render_to_string('_student_facts.html', {'profile': None})
        self.assertNotIn('·', markup)
        style = render_to_string('platform/_stats_style.html')
        self.assertIn(".student-facts > span + span::before", style)

    def test_empty_profile_draws_nothing(self):
        markup = render_to_string('_student_facts.html', {'profile': None})
        self.assertNotIn('student-facts', markup)

    def test_long_goal_does_not_break_the_header(self):
        profile = self.student.profile
        profile.goal = 'п' * 200
        profile.save(update_fields=['goal'])
        html = self.client.get('/teacher/student/%d/progress/'
                               % self.student.pk).content.decode()
        self.assertIn('п' * 200, html)
        style = render_to_string('platform/_stats_style.html')
        self.assertIn('overflow-wrap: anywhere',
                      style.split('.student-facts .fact')[1][:120])

    def test_both_screens_use_one_partial(self):
        for template in ('teacher/student_progress.html',
                         'teacher/groups/detail.html'):
            with open(_find(template), encoding='utf-8') as fh:
                self.assertIn('_student_facts.html', fh.read(), template)


class BestDayTests(TestCase):
    """8.3 — проверка: дата на месте, подсказка работает."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('s8d', password='x',
                                               role='student')
        cls.day = timezone.localdate() - timedelta(days=3)
        DailySummary.objects.create(user=cls.student, date=cls.day,
                                    problems_solved=7)
        PersonalRecord.objects.create(
            user=cls.student,
            kind=PersonalRecord.Kind.MOST_PRODUCTIVE_DAY,
            value=7, payload={'date': str(cls.day)})

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.student)

    def page(self):
        response = self.client.get('/profile/stats/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_card_shows_the_date_not_only_the_number(self):
        html = self.page()
        self.assertIn('Лучший день', html)
        # Дата человеческая: день, месяц словом, год.
        self.assertIn(str(self.day.year), html)
        self.assertIn('class="when"', html)

    def test_hint_explains_why_the_day_is_the_best(self):
        html = self.page()
        self.assertIn('Лучшим считается день', html)
        # Подсказка живёт на `data-hint`, а не на браузерном `title`.
        self.assertIn('data-hint', html)

    def test_raw_iso_date_never_reaches_the_screen(self):
        """«2026-08-04» посреди русского экрана читается как код."""
        self.assertNotIn(str(self.day), self.page())
