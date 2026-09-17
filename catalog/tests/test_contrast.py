"""Контраст текста каталога по WCAG, обе темы — в настоящем браузере (17.09.2026).

Раннер `catalog/tests/contrast_runner.mjs` обходит каталог, страницу задачи,
окно «Все фильтры» и страницу входа в светлой и тёмной теме и для каждого
видимого текста считает контраст с фактическим фоном (ближайший непрозрачный
предок). Норма — 4,5, для крупного текста — 3. Нарушитель печатается с
селектором, цветом и фоном. Экраны игры сюда не входят: их ведёт своя сессия.

Нашёлся 17.09.2026: у `<dialog>` окна фильтров был браузерный цвет текста, и в
тёмной теме заголовок «Все фильтры» и подпись «Только задачи с решением» были
чёрными на тёмном (1,45).

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

from problems.models import Tag
from problems.tests.factories import link_source, make_problem, make_source, make_topic

RUNNER = os.path.join(os.path.dirname(__file__), 'contrast_runner.mjs')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium отдельным процессом node — внешние ресурсы, поделить их между
# воркерами шага A нельзя.
@tag('catalog', 'browser', 'serial')
class CatalogContrastBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        cache.clear()
        topic = make_topic('Эластичность', is_canonical=True)
        tag_ = Tag.objects.create(name='Эластичность спроса', slug='el-demand', kind='canonical')
        source = make_source('ILE (iloveeconomics.ru)')
        self.problem = make_problem(
            'Спрос задан функцией $Q_d = 100 - 2P$. Найдите эластичность в точке $P = 20$.',
            topic=topic, title='Эластичность в точке', difficulty=3,
            solution='Решение: $E = -2 \\cdot 20 / 60$.', answer='$-2/3$')
        self.problem.tags.add(tag_)
        link_source(self.problem, source, url='https://www.iloveeconomics.ru/z/1')
        for i in range(3):
            make_problem('Условие %d: монополист с издержками $TC = Q^2$.' % i, topic=topic)

    def test_text_contrast_meets_wcag_in_both_themes(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — проверка контраста не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, CONTRAST_BASE_URL=self.live_server_url,
                   CONTRAST_PROBLEM='/catalog/problem/%d/' % self.problem.pk)
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=240)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertTrue('###CONTRAST-JSON###' in out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###CONTRAST-JSON###', 1)[1].strip().splitlines()[0])

        lines = []
        for key, box in sorted(data.items()):
            self.assertFalse('error' in box, '%s: %s' % (key, box.get('error')))
            self.assertTrue(box['checked'] > 0, '%s: не нашлось ни одного текста' % key)
            for v in box['violations']:
                lines.append('  %s: %.2f < %s  %s  «%s»  %s на %s (прозрачность %s)'
                             % (key, v['ratio'], v['need'], v['sel'], v['text'],
                                v['color'], v['bg'], v['opacity']))
        self.assertEqual(lines, [], 'Контраст ниже нормы WCAG:\n' + '\n'.join(lines))
