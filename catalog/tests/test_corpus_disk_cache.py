"""Корпус умного поиска на диске (17.09.2026).

Воркер при старте читает готовый корпус вместо сборки 20–25 с. Файл узнаёт
себя по общей версии корпуса и отпечатку данных; другая версия, битый файл,
старый файл и изменившиеся данные — сборка заново, без падения поиска.
"""
import json
import shutil
import tempfile
import time
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from catalog import lexical_bm25, rerank
from problems.tests.factories import make_problem, make_topic


class CorpusDiskCacheTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix='qls_corpus_')
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media, SMART_SEARCH_CORPUS_DISK_CACHE=True)
        override.enable()
        self.addCleanup(override.disable)
        cache.clear()
        rerank.invalidate_corpus()
        self.addCleanup(rerank.invalidate_corpus)
        topic = make_topic('Эластичность', is_canonical=True)
        make_problem('Эластичность спроса по цене в точке равновесия.', topic=topic)
        make_problem('Монополист выбирает выпуск при линейном спросе.', topic=topic)

    def new_worker(self):
        """Новый процесс того же сервера: памяти нет, общая версия та же."""
        rerank._corpus_cache = None
        rerank._corpus_cache_version = None

    def corpus_dirs(self):
        from pathlib import Path
        return sorted((Path(self.media) / '_cache').glob('corpus_*'))

    def test_built_corpus_is_saved_and_read_back(self):
        index, rows = rerank.get_corpus()
        self.assertEqual(len(self.corpus_dirs()), 1)
        self.new_worker()
        with mock.patch.object(rerank, '_build_corpus', side_effect=AssertionError('собирал заново')):
            loaded_index, loaded_rows = rerank.get_corpus()
        self.assertEqual(loaded_rows, rows)
        self.assertEqual(lexical_bm25.search(loaded_index, 'эластичность спроса'),
                         lexical_bm25.search(index, 'эластичность спроса'))

    def test_other_version_is_ignored(self):
        rerank.get_corpus()
        rerank.invalidate_corpus()          # синхронизация банка меняет версию
        with mock.patch.object(rerank, '_build_corpus', wraps=rerank._build_corpus) as build:
            rerank.get_corpus()
        self.assertEqual(build.call_count, 1)

    def test_broken_file_is_ignored(self):
        rerank.get_corpus()
        (self.corpus_dirs()[0] / 'rows.json').write_text('{битый', encoding='utf-8')
        self.new_worker()
        with mock.patch.object(rerank, '_build_corpus', wraps=rerank._build_corpus) as build:
            _index, rows = rerank.get_corpus()
        self.assertEqual(build.call_count, 1)
        self.assertEqual(len(rows), 2)

    def test_old_file_is_ignored(self):
        rerank.get_corpus()
        meta = self.corpus_dirs()[0] / 'meta.json'
        meta.write_text(json.dumps({'built_at': time.time() - rerank.CORPUS_FILE_MAX_AGE - 1}),
                        encoding='utf-8')
        self.new_worker()
        with mock.patch.object(rerank, '_build_corpus', wraps=rerank._build_corpus) as build:
            rerank.get_corpus()
        self.assertEqual(build.call_count, 1)

    def test_changed_data_changes_the_key(self):
        rerank.get_corpus()
        make_problem('Новая задача про внешние эффекты.')
        self.new_worker()
        with mock.patch.object(rerank, '_build_corpus', wraps=rerank._build_corpus) as build:
            _index, rows = rerank.get_corpus()
        self.assertEqual(build.call_count, 1)
        self.assertEqual(len(rows), 3)

    def test_off_by_default_writes_nothing(self):
        with override_settings(SMART_SEARCH_CORPUS_DISK_CACHE=False):
            rerank.invalidate_corpus()
            rerank.get_corpus()
        self.assertEqual(self.corpus_dirs(), [])
