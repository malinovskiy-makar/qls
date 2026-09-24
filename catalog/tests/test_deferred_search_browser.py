"""Отложенный умный поиск в настоящем браузере (24.09.2026, ADR 0128).

Полная загрузка `/catalog/?q=…` не платит за сортировку: страница прячет
порядок «по словам», показывает индикатор и сама просит `api_filter_state` с
заголовком `X-Weco-Search: 1`. Выдача показывается ОДИН раз — уже
отсортированной (решение владельца 11.09). Раннер —
`catalog/tests/deferred_search_runner.mjs`.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess
from unittest import mock

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings, tag

from catalog import rerank
from problems.tests.factories import make_problem, make_topic

RUNNER = os.path.join(os.path.dirname(__file__), 'deferred_search_runner.mjs')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: живой сервер и Chromium отдельным процессом node —
# внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('catalog', 'browser', 'serial')
@override_settings(SMART_SEARCH_RERANK=True)
class DeferredSearchBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        cache.clear()
        topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        self.problems = [make_problem('Монополист выбирает цену %d.' % i,
                                      title='Монополия %d' % i, topic=topic)
                         for i in range(4)]

    def test_page_asks_once_and_shows_the_sorted_order(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        ids = [p.pk for p in self.problems]
        sorted_ids = ids[::-1]
        calls = []

        def fake_run(query):
            calls.append(query)
            return rerank.RerankResult(sorted_ids, 'rerank')

        env = dict(os.environ, DEFER_BASE_URL=self.live_server_url, DEFER_QUERY='монополист')
        with mock.patch('catalog.views._search_ids', return_value=(ids, {}, False)), \
                mock.patch.object(rerank, '_run', side_effect=fake_run):
            try:
                res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                     capture_output=True, text=True, encoding='utf-8',
                                     errors='replace', timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###DEFER-JSON###', out, out[-2000:])
        data = json.loads(out.split('###DEFER-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('fail', data, data)
        self.assertEqual(data['errors'], [])
        # До ответа: страница отложена, порядок «по словам» не виден, индикатор горит.
        self.assertTrue(data['before']['deferred'])
        self.assertEqual(data['before']['visibleWordRows'], 0)
        self.assertTrue(data['before']['busy'])
        # Запрос скрипта один, с заголовком; платный вызов один.
        self.assertEqual(len(data['requests']), 1, data['requests'])
        self.assertEqual(data['requests'][0]['header'], '1')
        self.assertEqual(len(calls), 1)
        # После: итог отсортирован, индикатор погас.
        self.assertEqual(data['after']['status'], 'rerank')
        self.assertEqual(data['after']['ids'], [str(i) for i in sorted_ids])
        self.assertFalse(data['after']['busy'])
        # Без JS страница не прячет ничего: список «по словам» на месте.
        self.assertEqual(data['noJsVisibleRows'], len(ids))
