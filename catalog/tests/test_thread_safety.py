"""Общее состояние каталога при потоках gunicorn (gthread, ADR 0140).

Гонку потоков в тесте не поймать честно — она редкая. Поэтому «соседний
поток» вызывается прямо В ОКНЕ гонки: изнутри построения кэша, подменой
функции, которая выполняется между двумя шагами. Небезопасная версия в этом
месте отдаёт недостроенное состояние, безопасная — нет.
"""
import json
from unittest import mock

from django.test import SimpleTestCase

from catalog import views
from catalog.taxonomy_map import JSON_PATH


def _reset():
    views._TOPIC_MAP_CACHE.clear()
    views._TOPIC_MAP_CACHE['payload'] = None
    views._TAG_SECTIONS = None


class TopicMapPayloadTests(SimpleTestCase):
    def setUp(self):
        _reset()
        self.addCleanup(_reset)

    def test_neighbour_never_sees_text_without_etag(self):
        seen = []
        real_sha = views.hashlib.sha256

        def sha_with_neighbour(data):
            # Соседний поток приходит, пока ETag ещё считается.
            if not seen:
                seen.append(None)
                seen.append(views._topic_map_payload())
            return real_sha(data)

        with mock.patch.object(views.hashlib, 'sha256', side_effect=sha_with_neighbour):
            text, etag = views._topic_map_payload()
        _text, neighbour_etag = seen[1]
        self.assertTrue(etag)
        self.assertEqual(neighbour_etag, etag)


class TagSectionTests(SimpleTestCase):
    def setUp(self):
        _reset()
        self.addCleanup(_reset)
        nodes = json.loads(JSON_PATH.read_text(encoding='utf-8'))['nodes']
        tags = [n for n in nodes if n.get('k') == 'tag']
        self.first, self.last = tags[0], tags[-1]

    def test_neighbour_never_sees_half_built_sections(self):
        seen = []
        real_normalize = views.normalize_topic
        built = {'n': 0}

        def normalize_with_neighbour(name):
            built['n'] += 1
            # После первого тега словарь у небезопасной версии уже не пуст.
            if built['n'] == 2 and not seen:
                seen.append(views._tag_section(self.last['l'], 'ЗАПАСНОЙ'))
            return real_normalize(name)

        with mock.patch.object(views, 'normalize_topic', side_effect=normalize_with_neighbour):
            views._tag_section(self.first['l'], 'ЗАПАСНОЙ')
        self.assertEqual(seen, [self.last.get('g', 'other')])

    def test_section_by_name_and_fallback(self):
        self.assertEqual(views._tag_section(self.first['l'], 'x'), self.first.get('g', 'other'))
        self.assertEqual(views._tag_section('такого тега нет вовсе', 'x'), 'x')
