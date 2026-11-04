"""Реальный браузер: согласованная главная и проверка записи без потери класса."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, tag

from problems.models_platform import UserProfile
from vp.models import VPAttempt
from vp.tests.helpers import load_demo


@tag('serial', 'browser')  # Один живой HTTP-сервер и браузер, общий внешний ресурс.
class LandingPolishBrowserTests(StaticLiveServerTestCase):
    def test_responsive_actions_class_dialog_and_keyboard(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Обязательная браузерная проверка требует Node.')
        demos = {b: load_demo(b) for b in ('9', '10', '11')}
        user = get_user_model().objects.create_user('landing_polish_browser')
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.grade = '10'
        profile.save()
        attempt = VPAttempt.objects.create(user=user, variant=demos['9'],
                                           public_code='polish-live', with_timer=False)
        client = Client()
        client.force_login(user)
        out = Path(settings.BASE_DIR) / '.test-logs' / 'vp-polish'
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, VP_POLISH_BASE=self.live_server_url,
                   VP_POLISH_SESSION=client.cookies['sessionid'].value, VP_POLISH_OUT=str(out))
        result = subprocess.run([node, str(Path(__file__).with_name('browser_ui_polish.mjs'))],
                                cwd=settings.BASE_DIR, env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report['screens'], 40)
        profile.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(profile.grade, '10')
        self.assertEqual(attempt.variant_id, demos['9'].pk)
