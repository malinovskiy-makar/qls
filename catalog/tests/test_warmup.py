# -*- coding: utf-8 -*-
"""Прогрев воркера gunicorn (`catalog/warmup.py`, `config/gunicorn_conf.py`).

⚠️ СБОРКА КОРПУСА И ИНДЕКСА ЗДЕСЬ ПОДМЕНЯЕТСЯ. Пакета `bm25s` нет в
`requirements/dev.txt`, по которому CI ставит тестовое окружение (та же
ловушка, что описана в `test_rerank.py`), а проверяем мы не сборку, а то, что
прогрев её зовёт, пишет итог и не роняет воркер.
"""
import io
from unittest import mock

from django.test import SimpleTestCase, override_settings

from catalog import warmup

INDEX = {'ids': [1, 2, 3], 'matrix': None, 'is_test_flags': [False] * 3}


@override_settings(SMART_SEARCH_WARMUP=True)
class WarmWorkerTests(SimpleTestCase):

    def test_builds_corpus_and_index_and_logs_one_line(self):
        lines = []
        with mock.patch('catalog.rerank.get_corpus',
                        return_value=(None, {1: {}, 2: {}})) as corpus, \
                mock.patch('catalog.semantic.is_enabled', return_value=True), \
                mock.patch('catalog.semantic.get_index', return_value=INDEX) as index:
            result = warmup.warm_worker(log=lines.append)
        corpus.assert_called_once_with()
        index.assert_called_once_with()
        self.assertEqual((result['corpus'], result['index']), (2, 3))
        self.assertEqual(len(lines), 1)
        self.assertIn('прогрев: корпус 2 задач за', lines[0])
        self.assertIn('индекс 3 векторов за', lines[0])

    def test_index_is_skipped_when_semantic_search_is_off(self):
        lines = []
        with mock.patch('catalog.rerank.get_corpus', return_value=(None, {1: {}})), \
                mock.patch('catalog.semantic.is_enabled', return_value=False), \
                mock.patch('catalog.semantic.get_index') as index:
            warmup.warm_worker(log=lines.append)
        index.assert_not_called()
        self.assertIn('индекс не строился', lines[0])

    def test_empty_bank_warms_to_zero(self):
        lines = []
        with mock.patch('catalog.rerank.get_corpus', return_value=(None, {})), \
                mock.patch('catalog.semantic.is_enabled', return_value=False):
            result = warmup.warm_worker(log=lines.append)
        self.assertEqual(result['corpus'], 0)
        self.assertIn('корпус 0 задач', lines[0])

    def test_failure_does_not_crash_the_worker(self):
        lines = []
        with mock.patch('catalog.rerank.get_corpus', side_effect=RuntimeError('нет базы')), \
                self.assertLogs('catalog.warmup', level='WARNING'):
            result = warmup.warm_worker(log=lines.append)
        self.assertIsNone(result['corpus'])
        self.assertEqual(lines, [])

    def test_heartbeat_between_steps(self):
        notify = mock.Mock()
        with mock.patch('catalog.rerank.get_corpus', return_value=(None, {})), \
                mock.patch('catalog.semantic.is_enabled', return_value=True), \
                mock.patch('catalog.semantic.get_index', return_value=INDEX):
            warmup.warm_worker(log=lambda line: None, notify=notify)
        self.assertGreaterEqual(notify.call_count, 3)

    @override_settings(SMART_SEARCH_WARMUP=False)
    def test_switched_off_does_nothing(self):
        with mock.patch('catalog.rerank.get_corpus') as corpus:
            self.assertIsNone(warmup.warm_worker(log=lambda line: None))
        corpus.assert_not_called()


class GunicornHookTests(SimpleTestCase):

    def test_hook_warms_with_worker_log_and_heartbeat(self):
        from config import gunicorn_conf
        worker = mock.Mock()
        with mock.patch('catalog.warmup.warm_worker') as warm:
            gunicorn_conf.post_worker_init(worker)
        warm.assert_called_once_with(log=worker.log.info, notify=worker.notify)

    def test_entrypoint_loads_the_config(self):
        src = io.open('deploy/entrypoint.sh', encoding='utf-8').read()
        self.assertIn('-c /app/config/gunicorn_conf.py', src)
