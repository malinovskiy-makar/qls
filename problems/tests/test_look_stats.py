# -*- coding: utf-8 -*-
"""
Визуальная сессия 17.08, фаза 4 — статистика ученика по мокапу
`reports/mockups/mockup-stats-cabinet.html`, разделы «Первое» — «Пятое».

Контраст СЧИТАЕТСЯ, а не оценивается на глаз: у метки темы четыре цвета,
и каждая пара «чернила на подложке» обязана держать AA в обеих темах.
Считаем ПОВЕРХ поверхности — в тёмной теме подложки заданы через `rgba`,
и сравнивать текст с прозрачностью значит мерить не то.
"""
import re

from django.test import TestCase

from problems.tests.test_readable import (
    contrast, hex_rgb, over, themes, token,
)

STATS = 'problems/templates/platform/stats.html'
STYLE = 'problems/templates/platform/_stats_style.html'
JS = 'problems/static/platform/stats.js'


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def colour(value, surface):
    """Токен в rgb: hex как есть, rgba — поверх поверхности."""
    value = value.strip()
    if value.startswith('#'):
        return hex_rgb(value)
    parts = [p.strip() for p in
             re.match(r'rgba?\(([^)]+)\)', value).group(1).split(',')]
    top = tuple(float(p) for p in parts[:3])
    alpha = float(parts[3]) if len(parts) > 3 else 1.0
    return over(top, surface, alpha)


class TopicLabelContrastTests(TestCase):
    """4.5 — четыре метки карты тем читаются в обеих темах."""

    AA = 4.5
    # (класс метки, токен чернил, токен подложки) — ровно то, что стоит в CSS.
    PAIRS = (
        ('mastery-master', 'green', 'green-tint'),
        ('mastery-good', 'amber-ink', 'amber-tint'),
        ('mastery-weak', 'error', 'error-tint'),
        ('mastery-thin', 'chip-text', 'chip-bg'),
    )

    def measure(self, theme_css):
        surface = colour(token(theme_css, 'surface'), (255, 255, 255))
        return {name: contrast(colour(token(theme_css, ink), surface),
                               colour(token(theme_css, tint), surface))
                for name, ink, tint in self.PAIRS}

    def test_light_theme_passes_aa(self):
        light, _ = themes()
        for name, value in self.measure(light).items():
            self.assertGreaterEqual(
                value, self.AA, 'светлая тема, %s: контраст %s' % (name, value))

    def test_dark_theme_passes_aa(self):
        _, dark = themes()
        for name, value in self.measure(dark).items():
            self.assertGreaterEqual(
                value, self.AA, 'тёмная тема, %s: контраст %s' % (name, value))

    def test_css_uses_exactly_these_tokens(self):
        """Замер бесполезен, если CSS красит метку другими токенами."""
        css = read(STYLE)
        for name, ink, tint in self.PAIRS:
            rule = re.search(r'\.%s\s*\{([^}]*)\}' % name, css)
            self.assertIsNotNone(rule, 'нет правила .%s' % name)
            body = rule.group(1)
            self.assertIn('var(--%s)' % ink, body, name)
            self.assertIn('var(--%s)' % tint, body, name)


class TopicBarColourTests(TestCase):
    """4.5 — полоса под карточкой красится по метке, а не одним акцентом."""

    def test_bar_has_a_colour_per_label(self):
        css = read(STYLE)
        for kind, expected in (('weak', 'error'), ('good', 'amber'),
                               ('master', 'green')):
            rule = re.search(
                r'\.topic-bar--%s\s+i\s*\{([^}]*)\}' % kind, css)
            self.assertIsNotNone(rule, 'нет правила для метки %s' % kind)
            self.assertIn('var(--%s)' % expected, rule.group(1))

    def test_default_bar_is_not_the_accent(self):
        """«Мало данных» — нейтральная полоса: это не оценка."""
        css = read(STYLE)
        rule = re.search(r'\.topic-bar i\s*\{([^}]*)\}', css)
        self.assertIsNotNone(rule)
        self.assertNotIn('--accent', rule.group(1))

    def test_markup_passes_the_label_kind_to_the_bar(self):
        page = read(STATS)
        self.assertIn('topic-bar topic-bar--{{ topic.label_kind }}', page)


class WeeklyGoalTests(TestCase):
    """4.2 и 4.3 — кольцо ушло, цель считается верными задачами."""

    def test_ring_is_gone_from_markup_and_styles(self):
        self.assertNotIn('goal-ring', read(STATS))
        self.assertNotIn('goal-ring', read(STYLE))

    def test_goal_is_a_thin_bar_like_the_level(self):
        page = read(STATS)
        self.assertIn('hero-bar hero-bar--thin', page)
        rule = re.search(r'\.hero-bar\s*\{([^}]*)\}', read(STYLE))
        self.assertIn('height: 5px', rule.group(1))

    def test_freezes_counter_is_gone(self):
        self.assertNotIn('заморозок', read(STATS))

    def test_caption_says_what_is_counted(self):
        self.assertIn('верных за неделю', read(STATS))

    def test_game_does_not_count_towards_the_goal(self):
        """Правило цели живёт в одной выборке, и игра из неё исключена."""
        from problems import stats

        source = read('problems/stats.py')
        body = source[source.index('def _goal_events('):]
        body = body[:body.index('def solved_by_day(')]
        self.assertIn("exclude(source='game')", body)
        self.assertIn("event_type='solved'", body)
        self.assertTrue(hasattr(stats, 'solved_between'))

    def test_achievement_uses_the_same_rule(self):
        """Цель на экране и цель в достижении — одно число, не два."""
        source = read('problems/gamification.py')
        body = source[source.index('def weekly_goal_streak('):]
        body = body[:body.index('def check_achievements(')]
        self.assertIn('solved_by_day', body)
        self.assertNotIn('problems_solved', body)


class EmptyAccuracyCardTests(TestCase):
    """4.4 — пустота называется словами, а не прочерком."""

    def test_template_prints_words(self):
        page = read(STATS)
        self.assertIn('нет ответов', page)
        self.assertIn('за выбранный период', page)

    def test_period_switch_says_the_same(self):
        """Разметку рисует шаблон, переключатель периода — скрипт."""
        source = read(JS)
        self.assertIn('нет ответов', source)
        self.assertIn('за выбранный период', source)

    def test_empty_value_is_quieter_than_a_number(self):
        rule = re.search(r'\.metric \.big\.is-empty\s*\{([^}]*)\}', read(STYLE))
        self.assertIsNotNone(rule)
        self.assertIn('var(--text3)', rule.group(1))


class GroupSpacingTests(TestCase):
    """4.6 — иерархия расстоянием: 24 внутри группы, 56 между группами."""

    def test_two_gaps_and_no_headings(self):
        css = read(STYLE)
        between = re.search(r'\.st-group \+ \.st-group\s*\{([^}]*)\}', css)
        self.assertIsNotNone(between)
        self.assertIn('56px', between.group(1))
        inside = re.search(r'\.st-group > \*\s*\{([^}]*)\}', css)
        self.assertIn('24px', inside.group(1))

    def test_page_is_split_into_five_groups(self):
        page = read(STATS)
        self.assertEqual(page.count('<div class="st-group">'), 5)

    def test_charts_are_split_by_meaning(self):
        """«Разделы экономики» — к знаниям, «Динамика уровня» — к занятиям."""
        page = read(STATS)
        knowledge = page.index('Карта тем')
        activity = page.index('_activity_panel.html')
        self.assertLess(page.index('Разделы экономики'), activity)
        self.assertGreater(page.index('Разделы экономики'), knowledge)
        self.assertGreater(page.index('Динамика уровня'), activity)
        self.assertGreater(page.index('Где решаешь'), activity)


class GameMissTopicsTests(TestCase):
    """4.7 — воронка «поиграл → пошёл разбираться»."""

    def test_block_lives_inside_the_game_panel(self):
        page = read(STATS)
        panel = page[page.index('game-panel'):]
        self.assertIn('Чаще всего промахиваешься в игре', panel)
        self.assertIn("{% url 'catalog:problem_list' %}?topic=", panel)
        self.assertIn("{% url 'game:page' %}", panel)

    def test_branding_of_the_game_block_is_untouched(self):
        """Знак и пометка «игра» остаются — блок отгорожен намеренно."""
        page = read(STATS)
        self.assertIn('_rush_logo.html', page)
        self.assertIn('game-badge', page)

    def test_only_topics_with_misses_and_at_most_three(self):
        from problems.stats import GAME_MISS_TOPICS, game_miss_topics
        from problems.models import LearningEvent, Topic, User

        user = User.objects.create_user('miss_student', password='x')
        topics = [Topic.objects.create(name='Т%d' % i, slug='miss-t%d' % i)
                  for i in range(5)]
        for index, topic in enumerate(topics):
            for _ in range(index):          # 0, 1, 2, 3, 4 промаха
                LearningEvent.objects.create(user=user, source='game',
                                             event_type='failed', topic=topic)
            LearningEvent.objects.create(user=user, source='game',
                                         event_type='solved', topic=topic)
        rows = game_miss_topics(
            LearningEvent.objects.filter(user=user, source='game'))
        self.assertEqual(len(rows), GAME_MISS_TOPICS)
        self.assertEqual([r['failed'] for r in rows], [4, 3, 2])
        # Тема без промахов в список не попадает: разбирать в ней нечего.
        self.assertNotIn('Т0', [r['name'] for r in rows])

    def test_events_without_a_topic_are_skipped(self):
        """Целиться в «Без темы» нечем — такие промахи не показываем."""
        from problems.stats import game_miss_topics
        from problems.models import LearningEvent, User

        user = User.objects.create_user('miss_blank', password='x')
        for _ in range(5):
            LearningEvent.objects.create(user=user, source='game',
                                         event_type='failed')
        rows = game_miss_topics(
            LearningEvent.objects.filter(user=user, source='game'))
        self.assertEqual(rows, [])
