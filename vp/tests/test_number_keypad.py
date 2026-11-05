"""Ввод чисел сенсорной клавиатурой: реальные страницы, запросы и PostgreSQL."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import Client, tag
from django.utils import timezone

from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import load_demo


# Один живой сервер и браузеры, поэтому проверка запускается в последовательном этапе.
@tag('vp', 'browser', 'serial')
class NumberKeypadBrowserTests(StaticLiveServerTestCase):
    def test_touch_keypad_saves_exact_number_and_keeps_strict_rules(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Живой сервер с автосохранением требует PostgreSQL.')
        node = shutil.which('node')
        self.assertIsNotNone(node)
        user = get_user_model().objects.create_user('vp_keypad', password='local-test')
        client = Client()
        client.force_login(user)
        variant = load_demo('10')
        for code, submitted in [('kp-live', None), ('kp-result', timezone.now())]:
            VPAttempt.objects.create(variant=variant, user=user, public_code=code,
                                     with_timer=False, max_score=variant.max_score,
                                     submitted_at=submitted, score=0 if submitted else None)
        shots = Path(settings.BASE_DIR) / '.test-logs' / 'number-keypad'
        shots.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [node, str(Path(__file__).with_name('browser_number_keypad.mjs'))],
            cwd=settings.BASE_DIR, env=dict(os.environ, VP_KEYPAD_BASE=self.live_server_url,
                VP_KEYPAD_SESSION=client.cookies['sessionid'].value, VP_KEYPAD_SHOTS=str(shots)),
            capture_output=True, text=True, encoding='utf-8', timeout=240)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report['touch'], 8)
        self.assertEqual(report['desktop'], 2)
        self.assertEqual(report['nojs'], 2)
        attempt = VPAttempt.objects.get(public_code='kp-live')
        self.assertIsNone(attempt.submitted_at)
        self.assertEqual(VPAnswer.objects.get(attempt=attempt, item__number=11).raw, '-0,12')
        result_attempt = VPAttempt.objects.get(public_code='kp-result')
        self.assertEqual(result_attempt.score, 0)
        self.assertFalse(result_attempt.answers.exists())
