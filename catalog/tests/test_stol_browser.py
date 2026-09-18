"""«Стол» числами в настоящем браузере — на свежезагруженной странице, до клика.

Раннер `catalog/tests/stol_runner.mjs` (Playwright) открывает каждую страницу
заново и меряет то, что README макетов (`claude/mockups/catalog_stol_20260917/
README.md`) называет числом. Здесь — решение «зелёный/красный».

Появился 18.09.2026 после замера владельца: облако фона входа не рисовалось при
загрузке и было ярче §6, а снимки S1 делались уже после действия, которое его
перерисовывало. Приёмка глазами такое пропускает — число нет.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag

from problems.tests.factories import make_problem, make_topic

RUNNER = os.path.join(os.path.dirname(__file__), 'stol_runner.mjs')

#: README §2 (десктоп) и §8 (телефон).
DESKTOP = (1280, 1440, 1600, 1920)
PHONE = (360, 390, 430)


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium отдельным процессом node — внешние ресурсы, поделить их между
# воркерами шага A нельзя.
@tag('catalog', 'browser', 'serial')
class StolNumbersBrowserTest(StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = None

    def setUp(self):
        cache.clear()
        self.topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        for i in range(25):
            make_problem('Монополист %d выбирает выпуск: $TC = Q^2$.' % i, topic=self.topic,
                         title='Монополист %d' % i, difficulty=1 + i % 5)

    def _run(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — замеры «Стола» не запускались')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, STOL_BASE_URL=self.live_server_url, STOL_TOPIC=str(self.topic.pk))
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###STOL-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###STOL-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        return data

    def test_stol_numbers(self):
        """Один прогон браузера — все замеры; падения собираются списком."""
        data = self._run()
        problems = []

        def check(ok, text):
            if not ok:
                problems.append(text)

        # README §6: облако фона рисуется без действия человека, прозрачность 0,5.
        for key in ('bg light', 'bg dark', 'bg light reduce', 'bg dark reduce'):
            box = data[key]
            check(box['painted'] > 0, '%s: облако не нарисовано при загрузке (%s)' % (key, box))
            check(box['maxAlpha'] <= 130, '%s: ярче прозрачности 0,5 — альфа %d из 255' % (key, box['maxAlpha']))
            check(not box['errors'], '%s: ошибки страницы %s' % (key, box['errors']))

        # README §1–§2, §8: размеры входа и отсутствие горизонтальной прокрутки.
        for width in DESKTOP + PHONE:
            box = data['entry %d' % width]
            check(box['scrollWidth'] <= box['innerWidth'],
                  'вход %d: шире окна (%d > %d)' % (width, box['scrollWidth'], box['innerWidth']))
            check(not box['errors'], 'вход %d: ошибки страницы %s' % (width, box['errors']))
            phone = width < 760
            check(box['titleSize'] == (26 if phone else 34),
                  'вход %d: заголовок %s px, по README %d' % (width, box['titleSize'], 26 if phone else 34))
            check(box['chipHeight'] == (36 if phone else 32),
                  'вход %d: чип %s px, по README %d' % (width, box['chipHeight'], 36 if phone else 32))
            if not phone:
                check(box['searchWidth'] == 820, 'вход %d: карточка поиска %s, по README 820' % (width, box['searchWidth']))
                check(box['colWidth'] == 1120, 'вход %d: колонка %s, по README 1120' % (width, box['colWidth']))
                check(box['fieldSize'] == 19, 'вход %d: текст поля %s, по README 19' % (width, box['fieldSize']))

        # README §2: выпадашки 400/250/280, не выше 430 и видны целиком.
        need = {'topic': 400, 'difficulty': 250, 'kind': 280}
        for key, box in data['dropdowns 1280x800'].items():
            check(box['width'] == need[key], 'выпадашка %s: ширина %d, по README %d' % (key, box['width'], need[key]))
            check(box['height'] <= 430, 'выпадашка %s: высота %d > 430' % (key, box['height']))
            check(box['bottom'] <= box['vh'], 'выпадашка %s: низ %d за краем окна %d' % (key, box['bottom'], box['vh']))

        # Отклик выбора при медленном ответе: через 150 мс, а не через секунды.
        box = data['loading feedback']
        check(box == {'loading': True, 'busyShown': True, 'skeletonRows': 6, 'pressed': 'true'},
              'выбор темы при медленном ответе без мгновенного отклика: %s' % box)

        self.assertEqual(problems, [], 'Расхождения со спецификацией:\n' + '\n'.join(problems))
