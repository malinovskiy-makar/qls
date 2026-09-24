"""Решение в ленте помощи в настоящем браузере: гость и вошедший (24.09.2026, ADR 0129).

Раннер — `catalog/tests/guest_solution_runner.mjs`. Нет node или Playwright —
тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag
from django.urls import reverse

from problems.tests.factories import make_problem, make_user

RUNNER = os.path.join(os.path.dirname(__file__), 'guest_solution_runner.mjs')
SOLUTION = 'Секретное решение: приравниваем MR к MC и находим выпуск.'


# ⚠️ ПРИЧИНА МЕТКИ `serial`: живой сервер и Chromium отдельным процессом node —
# внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('catalog', 'browser', 'serial')
class GuestSolutionBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Монополист выбирает выпуск.', solution=SOLUTION, answer='Q = 10')
        self.client.force_login(make_user('sol_browser_user'))
        self.session = self.client.cookies['sessionid'].value

    def test_guest_gets_invite_user_gets_solution(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, SOL_BASE_URL=self.live_server_url, SOL_SESSION=self.session,
                   SOL_PATH=reverse('catalog:problem_detail', args=[self.problem.pk]))
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###SOL-JSON###', out, out[-2000:])
        data = json.loads(out.split('###SOL-JSON###', 1)[1].strip().splitlines()[0])
        guest, user = data['guest'], data['user']
        self.assertNotIn('fail', guest, guest)
        self.assertNotIn('fail', user, user)
        self.assertEqual(guest['errors'], [])
        self.assertEqual(user['errors'], [])
        self.assertIn('короткой бесплатной регистрации', guest['feed'])
        self.assertNotIn('Секретное решение', guest['feed'])
        self.assertEqual(len(guest['invite']), 2)
        self.assertTrue(all('next=%2Fcatalog%2Fproblem%2F' in href for href in guest['invite']))
        self.assertIn('Секретное решение', user['feed'])
        self.assertEqual(user['invite'], [])
