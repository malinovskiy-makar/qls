# -*- coding: utf-8 -*-
"""Умный поиск: разбивка времени, заголовок X-Smart-Search-Ms, честная плашка.

«20+ с вместо 7» на бою было не разобрать: в журнале стояло только общее время.
Здесь проверяется, что журнал отделяет сборку корпуса в холодном воркере от
сборки пула и модели, что общее время поиска видно одним `curl -sI`, и что
плашка при сортировке моделью на пуле по словам говорит правду (15.09.2026).

⚠️ Настоящий корпус здесь не строится: пакета `bm25s` нет в
`requirements/dev.txt`, по которому CI ставит тестовое окружение.
"""
import json
import os
import tempfile
import time
from unittest import mock

from django.test import TestCase, override_settings

from catalog import rerank
from problems.tests.factories import make_problem

RERANK_TEXT = 'Ищем по словам с умной сортировкой.'
WORDS_TEXT = 'Ищем по словам. Смысловой поиск сейчас недоступен'


class LogBreakdownTests(TestCase):

    def test_log_row_has_corpus_and_pool_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'smart_search_log.jsonl')
            result = rerank.RerankResult(
                [1], 'rerank', batches=1, model_seconds=1.2, total_seconds=9.5,
                corpus_build_seconds=7.25, pool_seconds=0.8)
            with mock.patch.object(rerank, '_log_path', return_value=path):
                rerank._log('монополия', result)
            with open(path, encoding='utf-8') as handle:
                row = json.loads(handle.readline())
        self.assertEqual(row['corpus_build_seconds'], 7.25)
        self.assertEqual(row['pool_seconds'], 0.8)

    def test_cold_worker_reports_corpus_build_and_warm_reports_zero(self):
        def slow_build():
            time.sleep(0.05)
            return None, {}

        def pool_through_corpus(query):
            rerank.get_corpus()
            return [], {'bm25': 0}, {}

        self.addCleanup(rerank.invalidate_corpus)
        with mock.patch.object(rerank, '_build_corpus', side_effect=slow_build), \
                mock.patch.object(rerank, 'build_pool', side_effect=pool_through_corpus):
            rerank.invalidate_corpus()
            cold = rerank._run('монополия')
            warm = rerank._run('монополия')
        self.assertGreaterEqual(cold.corpus_build_seconds, 0.05)
        self.assertEqual(warm.corpus_build_seconds, 0.0)
        self.assertLess(cold.pool_seconds, cold.corpus_build_seconds)


@override_settings(SEMANTIC_SEARCH_ENABLED=False, SMART_SEARCH_RERANK=False)
class HeaderTests(TestCase):

    def test_search_page_reports_search_milliseconds(self):
        response = self.client.get('/catalog/', {'q': 'налог'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['X-Smart-Search-Ms'].isdigit())

    def test_page_without_query_reports_zero(self):
        self.assertEqual(self.client.get('/catalog/')['X-Smart-Search-Ms'], '0')

    def test_filter_state_reports_it_too(self):
        response = self.client.get('/catalog/api/filter-state/', {'q': 'налог'})
        self.assertTrue(response['X-Smart-Search-Ms'].isdigit())


class DegradedNoteTests(TestCase):

    def setUp(self):
        self.problem = make_problem('Налог на монополиста.')

    def _page(self, apply_result):
        ids = [self.problem.pk]
        with mock.patch('catalog.views._search_ids', return_value=(ids, {}, True)), \
                mock.patch('catalog.rerank.apply', return_value=apply_result):
            return self.client.get('/catalog/', {'q': 'налог'}).content.decode('utf-8')

    def test_rerank_on_words_pool_says_so(self):
        html = self._page(([self.problem.pk], 'rerank'))
        self.assertTrue(RERANK_TEXT in html)
        self.assertFalse(WORDS_TEXT in html)

    def test_plain_words_search_keeps_the_old_note(self):
        html = self._page((None, 'fallback'))
        self.assertTrue(WORDS_TEXT in html)
        self.assertFalse(RERANK_TEXT in html)
