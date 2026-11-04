"""Сценарии сессии R на настоящих демоверсиях 2 тура и PostgreSQL."""
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

from vp import scoring
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import load_demo


@tag('vp', 'browser', 'serial')
class Tour2BrowserTests(StaticLiveServerTestCase):
    def test_real_demos_save_controls_and_touch_sign(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Живой сервер с автосохранением проверяется на PostgreSQL.')
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Для обязательной проверки второго тура нужен Node.')
        user = get_user_model().objects.create_user('vp_tour2_browser', password='local-test')
        client = Client()
        client.force_login(user)
        codes = {}
        for band in ('9', '10', '11'):
            variant = load_demo(band)
            attempt = VPAttempt.objects.create(
                variant=variant, user=user, public_code=f'br-t2-{band}',
                with_timer=False, max_score=variant.max_score)
            codes[band] = attempt.public_code
        shots = Path(settings.BASE_DIR) / '.test-logs' / 'tour2-browser'
        shots.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, VP_TOUR2_BASE=self.live_server_url,
                   VP_TOUR2_SESSION=client.cookies['sessionid'].value,
                   VP_TOUR2_CODES=json.dumps(codes), VP_TOUR2_SHOTS=str(shots))
        result = subprocess.run(
            [node, str(Path(__file__).with_name('browser_tour2.mjs'))],
            cwd=settings.BASE_DIR, env=env, capture_output=True, text=True,
            encoding='utf-8', timeout=150)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report['screens'], 12)
        self.assertEqual(report['controls'], ['deselect_saved', 'flags_persist', 'touch_sign_saved'])
        attempt = VPAttempt.objects.get(public_code=codes['10'])
        match = VPAnswer.objects.filter(attempt=attempt, item__number=4).first()
        self.assertTrue(scoring.is_blank(match.raw if match else None))
        self.assertEqual(VPAnswer.objects.get(attempt=attempt, item__number=11).raw, '-0,12')
