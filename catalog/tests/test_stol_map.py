"""Карта тем в «Столе» (README §1, §6): `/catalog/map/` — тот же экран.

Адрес рисует `stol.html` в виде `map`: под картой лежит вход с теми же
фильтрами, выход с карты возвращает на него без перезагрузки. Со входа карта
грузится лениво: разметка — ответом `?pane=1`, движок — только при открытии.
Переход и выбор в браузере меряет `test_stol_browser`.
"""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from problems.tests.factories import make_problem, make_topic


class MapViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        make_problem('Монополист выбирает выпуск.', topic=self.topic, title='Монополист и выпуск')
        self.url = reverse('catalog:topic_map')

    def test_map_is_the_stol_screen_with_the_entry_under_it(self):
        resp = self.client.get(self.url)
        self.assertTemplateUsed(resp, 'catalog/stol.html')
        self.assertTemplateUsed(resp, 'catalog/stol/_stol_map.html')
        self.assertTemplateUsed(resp, 'catalog/stol/_stol_entry.html')
        self.assertTemplateNotUsed(resp, 'catalog/topic_map.html')
        html = resp.content.decode()
        self.assertIn('class="stol-app is-map-on" id="stol-app" data-view="map"', html)
        self.assertIn('<section class="stol-map" id="stol-map" aria-label="Карта тем">', html)
        self.assertIn('data-bg-pattern="off"', html)
        self.assertIn('catalog/js/stol_map.js', html)
        self.assertIn('<title>Карта тем', html)

    def test_sections_and_counts_come_from_the_map_data(self):
        resp = self.client.get(self.url)
        html = resp.content.decode()
        ctx = resp.context
        self.assertEqual(html.count('class="tmap-sec-row"'), len(ctx['sections']))
        self.assertIn('%d&nbsp;' % ctx['theme_count'], html)
        self.assertIn('Разделы корпуса', html)

    def test_filters_ride_into_the_foot_and_every_exit(self):
        html = self.client.get(self.url, {'topic': self.topic.pk}).content.decode()
        self.assertIn('<b id="stol-map-count">Выбрано: 1&nbsp;тема</b>', html)
        self.assertIn('>Показать задачи<', html)
        self.assertEqual(html.count('href="/catalog/?topic=%d" data-map-exit' % self.topic.pk), 3)
        self.assertNotIn('id="tmap-reset" hidden', html)

    def test_nothing_chosen_shows_all_tasks(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('Темы и теги не выбраны', html)
        self.assertIn('>Показать все задачи<', html)
        self.assertIn('id="tmap-reset" hidden', html)

    def test_pane_gives_only_the_map_markup_hidden(self):
        resp = self.client.get(self.url, {'pane': '1', 'topic': self.topic.pk})
        self.assertEqual(resp['Content-Type'], 'application/json')
        part = json.loads(resp.content)['html']
        self.assertTrue(part.lstrip().startswith('<section class="stol-map" id="stol-map" aria-label="Карта тем" hidden>'))
        self.assertIn('id="tmap-canvas"', part)
        self.assertIn('Выбрано: 1&nbsp;тема', part)
        self.assertNotIn('<html', part)


class EntryLoadsTheMapLazilyTests(TestCase):

    def test_entry_has_no_map_engine_only_the_addresses(self):
        html = self.client.get(reverse('catalog:problem_list')).content.decode()
        self.assertIn('data-map-engine="/static/catalog/js/topic_map.js"', html)
        self.assertIn('data-map-js="/static/catalog/js/stol_map.js"', html)
        self.assertNotIn('<script defer src="/static/catalog/js/topic_map.js"', html)
        self.assertNotIn('<script defer src="/static/catalog/js/stol_map.js"', html)
        self.assertNotIn('id="stol-map"', html)
        self.assertIn('class="se-map" id="se-map" href="/catalog/map/"', html)
