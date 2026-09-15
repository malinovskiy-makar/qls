# -*- coding: utf-8 -*-
"""Прогрев воркера gunicorn (`catalog/warmup.py`, `config/gunicorn_conf.py`).

⚠️ СБОРКА КОРПУСА И ИНДЕКСА ЗДЕСЬ ПОДМЕНЯЕТСЯ. Пакета `bm25s` нет в
`requirements/dev.txt`, по которому CI ставит тестовое окружение (та же
ловушка, что описана в `test_rerank.py`), а проверяем мы не сборку, а то, что
прогрев её зовёт, пишет итог, не роняет воркер, идёт в фоновом потоке и что
поиск, пришедший во время прогрева, ждёт начатую сборку, а не строит вторую.
"""
import io
import threading
import time
from unittest import mock

from django.test import SimpleTestCase, override_settings

from catalog import rerank, semantic, warmup

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

    def test_closes_its_db_connection(self):
        with mock.patch('catalog.rerank.get_corpus', return_value=(None, {})), \
                mock.patch('catalog.semantic.is_enabled', return_value=False), \
                mock.patch('django.db.connection.close') as close:
            warmup.warm_worker(log=lambda line: None)
        close.assert_called_once_with()

    def test_closes_its_db_connection_when_warmup_fails(self):
        with mock.patch('catalog.rerank.get_corpus', side_effect=RuntimeError('нет базы')), \
                mock.patch('django.db.connection.close') as close, \
                self.assertLogs('catalog.warmup', level='WARNING'):
            warmup.warm_worker(log=lambda line: None)
        close.assert_called_once_with()

    @override_settings(SMART_SEARCH_WARMUP=False)
    def test_switched_off_does_nothing(self):
        with mock.patch('catalog.rerank.get_corpus') as corpus:
            self.assertIsNone(warmup.warm_worker(log=lambda line: None))
        corpus.assert_not_called()


class GunicornHookTests(SimpleTestCase):

    def test_hook_warms_in_a_background_thread_and_returns_at_once(self):
        from config import gunicorn_conf
        worker = mock.Mock()
        entered, release = threading.Event(), threading.Event()

        def slow_warm(log=None):
            entered.set()
            release.wait(10)

        with mock.patch('catalog.warmup.warm_worker', side_effect=slow_warm) as warm:
            started = time.perf_counter()
            gunicorn_conf.post_worker_init(worker)
            elapsed = time.perf_counter() - started
            self.assertTrue(entered.wait(5), 'прогрев не запустился')
            threads = [t for t in threading.enumerate()
                       if t.name == 'smart-search-warmup']
            release.set()
        for thread in threads:
            thread.join(5)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(len(threads), 1)
        self.assertTrue(threads[0].daemon)
        warm.assert_called_once_with(log=worker.log.info)

    def test_entrypoint_loads_the_config(self):
        src = io.open('deploy/entrypoint.sh', encoding='utf-8').read()
        self.assertIn('-c /app/config/gunicorn_conf.py', src)


class EarlySearchWaitsForWarmupTests(SimpleTestCase):
    """Поиск во время прогрева ждёт начатую сборку, а не запускает вторую."""

    def setUp(self):
        rerank.invalidate_corpus()
        semantic.invalidate_index()
        self.addCleanup(rerank.invalidate_corpus)
        self.addCleanup(semantic.invalidate_index)

    def test_corpus_is_built_once(self):
        waited = {}

        def search():
            rerank.get_corpus()
            waited['seconds'] = rerank._corpus_build.seconds

        entered = threading.Event()
        builds = []

        def slow_build():
            builds.append(threading.current_thread().name)
            entered.set()
            time.sleep(0.3)
            return None, {1: {}}

        with mock.patch.object(rerank, '_build_corpus', side_effect=slow_build):
            warm = threading.Thread(target=rerank.get_corpus, name='warm')
            warm.start()
            self.assertTrue(entered.wait(5), 'сборка не началась')
            early = threading.Thread(target=search, name='early')
            early.start()
            warm.join(5)
            early.join(5)
        self.assertEqual(builds, ['warm'])
        # Ожидание чужой сборки попадает в разбивку времени этого поиска.
        self.assertGreater(waited['seconds'], 0.1)

    def test_index_is_built_once(self):
        entered = threading.Event()
        builds = []

        def slow_build():
            builds.append(threading.current_thread().name)
            entered.set()
            time.sleep(0.3)
            return INDEX

        with mock.patch.object(semantic, '_build_index', side_effect=slow_build):
            warm = threading.Thread(target=semantic.get_index, name='warm')
            warm.start()
            self.assertTrue(entered.wait(5), 'сборка не началась')
            early = threading.Thread(target=semantic.get_index, name='early')
            early.start()
            warm.join(5)
            early.join(5)
        self.assertEqual(builds, ['warm'])
