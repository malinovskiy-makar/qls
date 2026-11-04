"""Подписи и мобильная раскладка объединённого выпуска: настоящий браузер."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag


@tag('calc2', 'browser', 'serial')  # Один живой сервер и браузер; общий внешний ресурс.
class ReleaseVisualTests(StaticLiveServerTestCase):
    def test_labels_handles_and_phone_flow(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Проверка выпуска требует Node и Playwright.')
        env = dict(os.environ, CALC2_BASE_URL=self.live_server_url)
        result = subprocess.run(
            [node, str(Path(__file__).with_name('release_visuals.mjs'))],
            cwd=settings.BASE_DIR, env=env, capture_output=True,
            text=True, encoding='utf-8', timeout=240,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report['screens'], 48)
