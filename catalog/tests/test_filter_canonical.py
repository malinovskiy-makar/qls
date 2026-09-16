"""Фильтр каталога показывает только канонические темы и теги (решение 17.09.2026).

На бою видимые задачи ещё висели на старых темах (с названием из 23
«живых») и на legacy-тегах — фильтр показывал 36 тем вместо 29. Старые связи
снимает синхронизация банка; этот тест держит предохранитель в коде.
"""
import json

from django.test import TestCase
from django.urls import reverse

from problems.models import Tag
from problems.tests.factories import make_problem, make_topic


class CanonicalOnlyFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.new = make_topic('Эластичность', is_canonical=True)
        # Старое имя из 23 «живых» — `is_known` его узнаёт, но флага нет.
        cls.old = make_topic('Спрос и предложение')
        cls.canon_tag = Tag.objects.create(name='Эластичность спроса', slug='el-demand', kind='canonical')
        cls.legacy_tag = Tag.objects.create(name='эластичность', slug='el-legacy', kind='legacy')
        for text in ('Эластичность раз.', 'Эластичность два.'):
            p = make_problem(text, topic=cls.new)
            p.topics.add(cls.old)
            p.tags.add(cls.canon_tag, cls.legacy_tag)

    def test_old_topic_is_not_offered(self):
        resp = self.client.get(reverse('catalog:api_filter_state'))
        self.assertEqual(resp.status_code, 200)
        topics = json.loads(resp.content)['counts']['topic']
        self.assertTrue(str(self.new.pk) in topics, 'нет канонической темы')
        self.assertFalse(str(self.old.pk) in topics, 'старая тема в фильтре')

    def test_legacy_tag_is_not_listed_under_topic(self):
        resp = self.client.get(reverse('catalog:api_filter_state'), {'topic': self.new.pk})
        tags = json.loads(resp.content)['counts']['tag']
        self.assertTrue(str(self.canon_tag.pk) in tags, 'нет канонического тега')
        self.assertFalse(str(self.legacy_tag.pk) in tags, 'legacy-тег в списке')

    def test_tag_suggestions_are_canonical_only(self):
        by_topic = json.loads(self.client.get(reverse('catalog:api_tags'), {'topic': self.new.pk}).content)
        by_query = json.loads(self.client.get(reverse('catalog:api_tags'), {'q': 'ластичн'}).content)
        for data in (by_topic, by_query):
            names = [t['name'] for t in data['tags']]
            self.assertEqual(names, ['Эластичность спроса'])
