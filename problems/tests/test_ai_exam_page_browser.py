"""Экзамен для ИИ: страница проверки в настоящем Chromium (без сети, file://).

Выдуманный банк из `test_ai_exam_review`; страница пишется во временную
папку, раннер `ai_exam_page_runner.py` идёт отдельным процессом. Нет
Playwright или Chromium — тест пропускается ГРОМКО, как проверка канона.

Метка `serial` не нужна: порта и общих файлов нет, у каждого процесса свой
Chromium и свой профиль.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from problems.ai_exam import review
from problems.ai_exam.page import build_page
from problems.tests.test_ai_exam_review import SEED, bank

RUNNER = Path(__file__).with_name('ai_exam_page_runner.py')


class PageBrowserTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        rows, records = bank()
        cls.by_id = {r['id']: r for r in rows}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            page = Path(tmp) / 'chunk_1.html'
            page.write_text(build_page(rows, records, 1, 4, SEED), encoding='utf-8')
            res = subprocess.run([sys.executable, str(RUNNER), str(page)],
                                 capture_output=True, text=True, timeout=170,
                                 encoding='utf-8', errors='replace',
                                 env={**os.environ, 'PYTHONUTF8': '1'})
        cls.result, cls.skip_reason = None, None
        if res.returncode != 0:
            cls.skip_reason = ('Playwright/Chromium не запустились, страница экзамена '
                               'в браузере НЕ проверена: %s' % res.stderr.strip()[-300:])
            print('\n⚠️ ПРОПУСК: ' + cls.skip_reason, file=sys.stderr)
        else:
            cls.result = json.loads(res.stdout.strip().splitlines()[-1])

    def setUp(self):
        if self.result is None:
            self.skipTest(self.skip_reason)

    def test_second_number_and_skip_survive_reload(self):
        self.assertEqual(self.result['rows_after_reload'], 2)
        self.assertEqual(self.result['second_after_reload'], ['Q', '12'])
        self.assertTrue(self.result['skip_after_reload'])
        self.assertEqual(self.result['verdict_after_reload'], 'ok')

    def test_row_controls(self):
        self.assertTrue(self.result['inputs_disabled_when_skipped'])
        self.assertTrue(self.result['remove_disabled_on_single_row'])
        self.assertTrue(self.result['remove_enabled_on_two_rows'])

    def test_export_keeps_both_numbers_and_skipped_ask(self):
        payload = self.result['payload']
        self.assertEqual(payload['format'], 'ai_exam_review/2')
        row = next(r for r in payload['rows'] if r['id'] == 103)
        values = row['asks'][0]['values']
        self.assertEqual([(v['label'], v['value']) for v in values],
                         [('P', '30'), ('Q', '12')])
        self.assertEqual([a['skip'] for a in row['asks']], [False, True])
        self.assertEqual(row['asks'][1]['values'], [])

    def test_export_passes_validate_review(self):
        good, complaints = review.validate_review(self.result['payload'], self.by_id)
        self.assertEqual(complaints, [])
        self.assertEqual(sorted(r['id'] for r in good), [101, 103])

    def test_page_is_clean(self):
        self.assertGreater(self.result['katex_count'], 0)
        self.assertEqual(self.result['katex_errors'], 0)
        self.assertEqual(self.result['console_errors'], [])
        self.assertEqual(self.result['page_errors'], [])
        self.assertEqual(self.result['external_requests'], [])
