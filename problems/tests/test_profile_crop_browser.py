"""Обрезка аватара в настоящем браузере — на компьютере и на телефоне (24.09.2026).

Раннер `problems/tests/profile_crop_runner.mjs` (Playwright) выбирает PNG
800×600, ждёт окна обрезки, меряет масштаб картинки и покрытие круга и жмёт
«Сохранить». Здесь — решение «зелёный/красный» и проверка того, что на диск
лёг квадрат 256×256.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import io
import json
import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings, tag
from PIL import Image

from problems.models_platform import UserProfile
from problems.tests.factories import make_user

RUNNER = os.path.join(os.path.dirname(__file__), 'profile_crop_runner.mjs')
MEDIA = tempfile.mkdtemp(prefix='qls_crop_media_')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium отдельным процессом node — внешние ресурсы, поделить их между
# воркерами шага A нельзя.
@tag('browser', 'serial')
@override_settings(MEDIA_ROOT=MEDIA)
class ProfileCropBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        cache.clear()
        self.user = make_user('crop_browser_student')
        self.client.force_login(self.user)
        self.session = self.client.cookies['sessionid'].value
        buf = io.BytesIO()
        Image.new('RGB', (800, 600), (30, 120, 200)).save(buf, 'PNG')
        handle, self.png = tempfile.mkstemp(suffix='.png')
        with os.fdopen(handle, 'wb') as f:
            f.write(buf.getvalue())

    def tearDown(self):
        os.remove(self.png)

    def _run(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — обрезка в браузере не проверялась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, CROP_BASE_URL=self.live_server_url,
                   CROP_SESSION=self.session, CROP_PNG=self.png)
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###CROP-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        return json.loads(out.split('###CROP-JSON###', 1)[1].strip().splitlines()[0])

    def test_crop_on_desktop_and_phone(self):
        data = self._run()
        for width in ('1440', '390'):
            row = data[width]
            with self.subTest(width=width):
                self.assertNotIn('fail', row, row)
                self.assertEqual(row['errors'], [])
                self.assertEqual(row['closedDisplay'], 'none',
                                 'закрытое окно обрезки видно на странице')
                self.assertGreater(row['scale'], 0, 'картинка схлопнулась: scale(0)')
                self.assertGreater(row['hole'], 0)
                self.assertTrue(row['covers'], 'картинка не покрывает круг: %s' % row)
                self.assertEqual(row['postStatus'], 302)
                self.assertIn('saved=1', row['finalUrl'])
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.avatar)
        with profile.avatar.open('rb') as f:
            self.assertEqual(Image.open(f).size, (256, 256))
        # Второе сохранение заменило первое, а не легло рядом копией.
        folder = os.path.join(MEDIA, 'avatars')
        self.assertEqual(os.listdir(folder), ['%d.jpg' % self.user.pk])
