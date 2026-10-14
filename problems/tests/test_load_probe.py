"""Зонд «Сайт не встаёт» (problems/loadprobe.py) и медленный подставной ИИ.

Без сети: вердикт и перцентили — на числах, задержка — на самом поставщике.
"""
import inspect
import os
import shutil
import subprocess
import time
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from problems import loadprobe
from problems.ai import providers


def pages(seconds, status=200):
    return [{'path': '/', 'status': status, 'seconds': s} for s in seconds]


def ai(n, ok=True, seconds=20.0):
    return [{'status': 200, 'seconds': seconds, 'ok': ok, 'error': ''} for _ in range(n)]


class PercentileTests(SimpleTestCase):
    def test_nearest_rank(self):
        values = list(range(1, 21))          # 1..20
        self.assertEqual(loadprobe.percentile(values, 50), 10)
        self.assertEqual(loadprobe.percentile(values, 95), 19)
        self.assertEqual(loadprobe.percentile(values, 100), 20)
        self.assertEqual(loadprobe.percentile([7], 95), 7)
        self.assertEqual(loadprobe.percentile([], 95), 0.0)

    def test_p95_is_not_the_median(self):
        values = [0.1] * 90 + [20.0] * 10
        summary = loadprobe.summarize(pages(values), [])
        self.assertEqual(summary['pages']['p50'], 0.1)
        self.assertEqual(summary['pages']['p95'], 20.0)


class VerdictTests(SimpleTestCase):
    def test_fast_is_pass(self):
        summary = loadprobe.summarize(pages([0.05, 0.08, 0.1, 0.12] * 25), ai(8))
        self.assertEqual(loadprobe.verdict(summary, 8, 0.1)[0], 'PASS')

    def test_slow_p95_is_fail(self):
        summary = loadprobe.summarize(pages([0.1] * 80 + [20.0] * 20), ai(8))
        result, reasons = loadprobe.verdict(summary, 8, 0.1)
        self.assertEqual(result, 'FAIL')
        self.assertIn('P95', reasons[0])

    def test_one_502_is_fail(self):
        summary = loadprobe.summarize(pages([0.1] * 99) + pages([0.1], status=502), ai(8))
        result, reasons = loadprobe.verdict(summary, 8, 0.1)
        self.assertEqual(result, 'FAIL')
        self.assertEqual(reasons, ['ошибок лёгких страниц: 1'])

    def test_missing_ai_answer_is_fail(self):
        summary = loadprobe.summarize(pages([0.1] * 50), ai(7) + ai(1, ok=False))
        self.assertEqual(loadprobe.verdict(summary, 8, 0.1)[0], 'FAIL')

    def test_threshold_has_a_floor(self):
        self.assertEqual(loadprobe.threshold(0.05), 1.0)
        self.assertEqual(loadprobe.threshold(0.5), 1.5)
        self.assertEqual(loadprobe.threshold(None), 1.0)


class FakeDelayTests(SimpleTestCase):
    def _call(self, provider):
        return provider.complete(['система'], 'текст', {}, 'glm-5.3', 100)

    @override_settings(AI_FAKE_DELAY_SECONDS=0.2, AI_FAKE_REPLY='{"reply": "проба стенда"}')
    def test_fake_sleeps(self):
        started = time.monotonic()
        reply = self._call(providers.FakeProvider())
        self.assertGreaterEqual(time.monotonic() - started, 0.2)
        self.assertEqual(reply.text, '{"reply": "проба стенда"}')

    def test_no_delay_by_default(self):
        self.assertEqual(settings.AI_FAKE_DELAY_SECONDS, 0)
        with mock.patch.object(providers.time, 'sleep') as sleep:
            self._call(providers.FakeProvider())
        sleep.assert_not_called()

    @override_settings(AI_FAKE_DELAY_SECONDS=5)
    def test_real_provider_does_not_sleep(self):
        class Stop(Exception):
            pass
        with mock.patch.object(providers.time, 'sleep') as sleep, \
                mock.patch.dict(os.environ, {'GLM_API_KEY': 'тест'}), \
                mock.patch('openai.OpenAI', side_effect=Stop):
            with self.assertRaises(Stop):
                self._call(providers.GLMProvider())
        sleep.assert_not_called()

    def test_only_fake_reads_the_delay(self):
        for name, cls in providers.PROVIDERS.items():
            source = inspect.getsource(cls)
            with self.subTest(provider=name):
                self.assertEqual('AI_FAKE_DELAY_SECONDS' in source, name == 'fake')
        self.assertNotIn('AI_FAKE_DELAY_SECONDS', inspect.getsource(providers.BaseProvider))


class EntrypointTests(SimpleTestCase):
    """Строка запуска gunicorn на бою и на площадке (deploy/entrypoint.sh)."""

    def setUp(self):
        path = os.path.join(settings.BASE_DIR, 'deploy', 'entrypoint.sh')
        with open(path, encoding='utf-8') as handle:
            self.text = handle.read()
        self.prelude = self.text[self.text.index('GUNICORN_WORKER_CLASS="${'):
                                 self.text.index('exec gunicorn')]
        self.command = self.text[self.text.index('exec gunicorn'):]

    def test_threads_by_default_with_rollback_variables(self):
        self.assertIn('GUNICORN_WORKER_CLASS="${GUNICORN_WORKER_CLASS:-gthread}"', self.prelude)
        self.assertIn('GUNICORN_THREADS="${GUNICORN_THREADS:-8}"', self.prelude)
        self.assertIn('--worker-class "$GUNICORN_WORKER_CLASS"', self.command)
        self.assertIn('--threads "$GUNICORN_THREADS"', self.command)

    def test_workers_and_timeout_unchanged(self):
        self.assertIn('--workers "${GUNICORN_WORKERS:-4}"', self.command)
        self.assertIn('--timeout 60', self.command)

    def test_rollback_to_sync_drops_threads(self):
        """gunicorn сам меняет sync на gthread при --threads > 1: откат
        GUNICORN_WORKER_CLASS=sync обязан давать ровно один поток."""
        shell = shutil.which('sh')
        if shell is None:
            self.skipTest('нет sh — проверка поведения только в CI')
        cases = {(): ('gthread', '8'), (('GUNICORN_WORKER_CLASS', 'sync'),): ('sync', '1'),
                 (('GUNICORN_WORKER_CLASS', 'sync'), ('GUNICORN_THREADS', '8')): ('sync', '1'),
                 (('GUNICORN_THREADS', '4'),): ('gthread', '4')}
        for given, expected in cases.items():
            env = {k: v for k, v in os.environ.items() if not k.startswith('GUNICORN_')}
            env.update(dict(given))
            out = subprocess.run([shell, '-c', self.prelude + 'echo "$GUNICORN_WORKER_CLASS $GUNICORN_THREADS"'],
                                 env=env, capture_output=True, text=True, check=True).stdout.split()
            with self.subTest(given=given):
                self.assertEqual(tuple(out), expected)
