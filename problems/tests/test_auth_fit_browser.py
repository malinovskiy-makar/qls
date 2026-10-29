# -*- coding: utf-8 -*-
"""Регистрация и вход влезают в окно без прокрутки (раунд 4, 29.10.2026).

Окна владельца: 1440×778 (его браузер) и 1536×730 (ноутбук 1920×1080 с
масштабом 125 %). Мерим как у владельца: с кнопками обоих сервисов и с почтой —
тогда на регистрации две галочки, и карточка самая высокая. Онбординг включён, как
на бою: без него регистрация спрашивает роль (аварийный режим), и карточка выше.

Раннер `auth_fit_runner.py` (Python-Playwright из `venv313`, не node: в рабочей
папке может не быть `node_modules`). Нет Playwright или браузера — ПРОПУСК.
"""
import importlib.util
import json
import os
import subprocess
import sys

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings, tag

RUNNER = os.path.join(os.path.dirname(__file__), 'auth_fit_runner.py')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: живой сервер и Chromium — внешние ресурсы, поделить их
# между воркерами шага A нельзя.
@tag('browser', 'serial')
@override_settings(SOCIAL_LOGIN_ENABLED=True, VK_ID_CLIENT_ID='51234567',
                   YANDEX_CLIENT_ID='0123456789abcdef0123456789abcdef', MAIL_ENABLED=True,
                   ONBOARDING_ENABLED=True)
class AuthFitsTheWindowTest(StaticLiveServerTestCase):

    def test_register_and_login_have_no_scroll(self):
        if importlib.util.find_spec('playwright') is None:
            self.skipTest('Python-Playwright не установлен')
        res = subprocess.run([sys.executable, RUNNER, self.live_server_url],
                             capture_output=True, text=True, encoding='utf-8',
                             errors='replace', timeout=300)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest(out[-1500:])
        self.assertIn('###FIT-JSON###', out, out[-2000:])
        seen = json.loads(out.split('###FIT-JSON###', 1)[1].strip().splitlines()[0])
        self.assertEqual(len(seen), 4)
        for key, (scroll, inner, buttons, ticks) in seen.items():
            with self.subTest(key):
                self.assertEqual(buttons, 2, 'кнопок сервисов нет — замер не как у владельца')
                if key.startswith('/register/'):
                    self.assertEqual(ticks, 2)
                self.assertLessEqual(scroll, inner, '%s: прокрутка %d px' % (key, scroll - inner))
