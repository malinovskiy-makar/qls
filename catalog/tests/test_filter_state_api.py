"""Фаза 2.3: эндпоинт живого состояния фильтров и теги темы.

`GET /catalog/api/filter-state/` отдаёт числа по вариантам, чипы и список
одним ответом, собранным тем же кодом и теми же партиалами, что страница.
`GET /catalog/api/tags/?topic=<id>` — теги видимых задач темы с числами.
"""
import json

from django.test import TestCase
from django.urls import reverse

from problems.models import Tag
from problems.tests.factories import make_problem, make_topic


class _Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация')
        cls.el = make_topic('Эластичность')
        cls.t_kurno = Tag.objects.create(name='Курно', slug='kurno')
        cls.t_tariff = Tag.objects.create(name='Двухчастный тариф', slug='tariff')
        cls.t_hidden = Tag.objects.create(name='Скрытый тег', slug='hidden-tag')
        cls.p1 = make_problem('Монополист один.', topic=cls.mon, difficulty=4)
        cls.p2 = make_problem('Монополист два.', topic=cls.mon, difficulty=5,
                              solution='Решение.')
        cls.p3 = make_problem('Эластичность спроса.', topic=cls.el, difficulty=5)
        cls.p_hidden = make_problem('Скрытая задача.', topic=cls.mon, flagged=True)
        cls.p1.tags.add(cls.t_kurno)
        cls.p2.tags.add(cls.t_kurno, cls.t_tariff)
        cls.p3.tags.add(cls.t_tariff)
        cls.p_hidden.tags.add(cls.t_hidden)


class FilterStateApiTests(_Fixture):
    def _get(self, params=None):
        resp = self.client.get(reverse('catalog:api_filter_state'), params or {})
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.content)

    def test_keys_and_total_match_the_page(self):
        params = {'topic': self.mon.pk, 'difficulty': 5}
        data = self._get(params)
        self.assertEqual(set(data), {'total', 'counts', 'selected_count',
                                     'chips_html', 'results_html', 'url'})
        self.assertEqual(set(data['counts']),
                         {'topic', 'tag', 'difficulty', 'kind', 'test_type',
                          'source', 'has_solution', 'character', 'feature'})
        page = self.client.get('/catalog/', params)
        self.assertEqual(data['total'], page.context['total'])
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['selected_count'], 2)
        self.assertIn('data-chip="topic"', data['chips_html'])
        self.assertIn('data-chip="difficulty"', data['chips_html'])
        self.assertIn('id="ct-results"', data['results_html'])
        self.assertIn('/catalog/problem/%d/' % self.p2.pk, data['results_html'])
        self.assertIn('topic=%d' % self.mon.pk, data['url'])
        self.assertIn('difficulty=5', data['url'])

    def test_counts_cover_the_corpus_and_follow_the_other_filters(self):
        counts = self._get()['counts']
        self.assertEqual(set(counts['topic']), {str(self.mon.pk), str(self.el.pk)})
        self.assertEqual(counts['topic'][str(self.mon.pk)], 2)
        self.assertEqual(counts['difficulty'], {'4': 1, '5': 2})
        self.assertEqual(counts['kind'], {'open': 3})
        self.assertEqual(counts['test_type'], {})
        self.assertEqual(counts['has_solution'], 1)
        self.assertEqual(counts['character'], {})
        self.assertEqual(counts['feature'], {})
        # Выбрана тема: темы считаются БЕЗ неё, сложности — внутри неё.
        narrowed = self._get({'topic': self.el.pk})['counts']
        self.assertEqual(narrowed['topic'][str(self.mon.pk)], 2)
        self.assertEqual(narrowed['difficulty'], {'4': 0, '5': 1})
        self.assertEqual(set(narrowed['tag']), {str(self.t_tariff.pk)})

    def test_two_topics_are_a_union(self):
        data = self._get({'topic': [self.mon.pk, self.el.pk]})
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['url'].count('topic='), 2)

    def test_view_mode_and_query_ride_along(self):
        data = self._get({'view': 'gallery', 'topic': self.mon.pk})
        self.assertIn('view=gallery', data['url'])
        self.assertIn('topic=%d' % self.mon.pk, data['url'])
        self.assertIn('class="ct-gallery"', data['results_html'])
        # С запросом список зависит от поиска (в тестах он идёт по словам),
        # поэтому здесь проверяется только адрес: запрос и фильтр остаются.
        with_query = self._get({'view': 'gallery', 'topic': self.mon.pk, 'q': 'спрос'})
        self.assertIn('q=', with_query['url'])
        self.assertIn('topic=%d' % self.mon.pk, with_query['url'])

    def test_endpoint_renders_the_same_results_partial_as_the_page(self):
        params = {'topic': self.mon.pk}
        page = self.client.get('/catalog/', params).content.decode()
        start = page.index('<section class="ct-results"')
        section = page[start:page.index('</section>', start) + len('</section>')]
        self.assertEqual(self._get(params)['results_html'].strip(), section.strip())


class ApiTagsByTopicTests(_Fixture):
    def test_topic_mode_lists_only_that_topics_tags_without_zeros(self):
        url = reverse('catalog:api_tags')
        data = json.loads(self.client.get(url, {'topic': self.mon.pk}).content)
        self.assertEqual([(t['name'], t['count']) for t in data['tags']],
                         [('Курно', 2), ('Двухчастный тариф', 1)])
        self.assertEqual(data['tags'][0]['id'], self.t_kurno.pk)
        data = json.loads(self.client.get(url, {'topic': self.el.pk}).content)
        self.assertEqual([(t['name'], t['count']) for t in data['tags']],
                         [('Двухчастный тариф', 1)])
        # Тег, висящий только на скрытой задаче, не подсказывается.
        names = {t['name'] for t in json.loads(
            self.client.get(url, {'topic': self.mon.pk}).content)['tags']}
        self.assertNotIn('Скрытый тег', names)

    def test_q_mode_is_unchanged(self):
        url = reverse('catalog:api_tags')
        # Игла в нижнем регистре внутри слова: LIKE у SQLite не знает
        # регистра кириллицы, и «ку» не нашло бы «Курно» (на PostgreSQL иначе).
        data = json.loads(self.client.get(url, {'q': 'урн'}).content)
        self.assertEqual([t['name'] for t in data['tags']], ['Курно'])
        self.assertEqual(json.loads(self.client.get(url, {'q': 'к'}).content), {'tags': []})
