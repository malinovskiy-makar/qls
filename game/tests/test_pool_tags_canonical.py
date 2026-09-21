"""Окно фильтров игры показывает только канонические теги (18.09.2026).

Как в каталоге (решение 17.09): legacy-теги из окна ушли. Данные пула не
трогаются — вопрос с legacy-тегом по-прежнему считается по своей теме:
`pool_counts_for` этой правкой не задет.
"""
from django.test import TestCase

from game import views
from game.tests.test_filter_window import make_q
from problems.models import Tag


class PoolTagsCanonicalTests(TestCase):

    def setUp(self):
        self.canon = Tag.objects.create(name='Курно', slug='kurno', kind='canonical')
        self.legacy = Tag.objects.create(name='старый тег', slug='old', kind='legacy')
        make_q(tag_ids=[self.canon.id, self.legacy.id], topics=['Эластичность'])

    def test_legacy_tag_is_not_listed(self):
        names = {r['name'] for r in views.pool_tags()}
        self.assertIn('Курно', names)
        self.assertNotIn('старый тег', names)

    def test_question_with_legacy_tag_still_counts_for_its_topic(self):
        f = dict(views.empty_filter(), topics=['Эластичность'])
        self.assertEqual(views.pool_counts_for(f)['blitz'], 1)

    def test_tag_carries_the_topics_of_its_questions(self):
        row = next(r for r in views.pool_tags() if r['name'] == 'Курно')
        self.assertEqual(row['topics'], ['Эластичность'])
