# -*- coding: utf-8 -*-
"""Поиск: фразы ожидания и появление выдачи (решение владельца 15.09.2026).

Пока грузится выдача, под полем сменяются фразы; первая — «думается
думается…» — стоит в разметке, все приходят через json_script. Карточки
найденного появляются лесенкой, только первые двенадцать и только после
поиска.
"""
import json
import re
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from catalog import views
from catalog.placeholder_phrases import SEARCH_BUSY_PHRASES
from problems.tests.factories import make_problem

#: С S7 «Стола» (19.09.2026) фразы ожидания крутит модуль входа `stol.js`.
JS = 'catalog/static/catalog/js/stol.js'


@override_settings(SEMANTIC_SEARCH_ENABLED=False, SMART_SEARCH_RERANK=False)
class BusyPhrasesPageTests(TestCase):

    def page(self, **params):
        return self.client.get('/catalog/', params).content.decode('utf-8')

    def test_page_shows_the_first_phrase_instead_of_the_old_text(self):
        html = self.page()
        self.assertTrue('<span id="ask-busy-text">думается думается…</span>' in html,
                        'в разметке нет первой фразы')
        self.assertFalse('Ищу похожие задачи' in html, 'остался старый текст')

    def test_phrases_come_through_json_script(self):
        match = re.search(
            r'<script id="search-busy-phrases" type="application/json">(.*?)</script>',
            self.page(), re.S)
        self.assertTrue(match, 'нет json_script с фразами')
        self.assertEqual(json.loads(match.group(1)), list(SEARCH_BUSY_PHRASES))

    def test_search_results_appear_on_the_first_twelve_cards(self):
        ids = [make_problem('Налог на монополиста, вариант %d.' % i).pk
               for i in range(14)]
        with mock.patch('catalog.views._search_ids', return_value=(ids, {}, False)):
            html = self.page(q='налог')
        self.assertEqual(html.count('class="rail-row ct-appear"'),
                         min(12, views.PAGE_STEP))

    def test_plain_catalog_does_not_animate_cards(self):
        make_problem('Спрос и предложение.')
        self.assertFalse('class="rail-row ct-appear"' in self.page(),
                         'карточки анимируются без поиска')


class BusyPhrasesSourceTests(SimpleTestCase):

    def test_first_phrase_is_always_the_thinking_one(self):
        self.assertEqual(SEARCH_BUSY_PHRASES[0], 'думается думается…')
        self.assertEqual(len(SEARCH_BUSY_PHRASES), 15)

    def test_script_rotates_and_respects_reduced_motion(self):
        with open(JS, encoding='utf-8') as handle:
            js = handle.read()
        self.assertTrue("getElementById('search-busy-phrases')" in js,
                        'скрипт не читает фразы')
        self.assertTrue('}, 1600);' in js, 'нет смены раз в 1,6 с')
        self.assertTrue('quiet' in js and 'prefers-reduced-motion' in js,
                        'смена фраз не уважает «уменьшить движение»')
        self.assertTrue('busyPhrases.slice(0, 1).concat(rest)' in js,
                        'первая фраза не закреплена первой')
