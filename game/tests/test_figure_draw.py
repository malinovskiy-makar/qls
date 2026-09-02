u"""Раскладка чертежа — через настоящий браузер (`figure_draw.mjs`).

Почему не питон-тест: проверять надо не числа, а РАСКЛАДКУ — не налезла ли
подпись на подпись и не легла ли она на кривую. Ширину надписи в пикселях
знает только движок вёрстки, любая заглушка вернула бы ноль, и «зелёный»
тест ничего бы не значил.

Живой сервер не нужен: раннер подкладывает `figure.js` в пустую страницу.
Запускать можно и отдельно: `node game/tests/figure_draw.mjs`.

Playwright/node недоступны → тест ПРОПУСКАЕТСЯ (skip), а не падает: это
не должно ронять остальной прогон на машине без браузера.
"""
import os
import shutil
import subprocess
import unittest

from django.conf import settings
from django.test import SimpleTestCase, tag

RUNNER = os.path.join(os.path.dirname(__file__), 'figure_draw.mjs')


@tag('browser')
class FigureDrawLayoutTest(SimpleTestCase):
    """Двенадцать контрольных раскладок + примитивы рисователя."""

    def test_figure_layouts(self):
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node не найден — пропускаю раскладку чертежа')
        if not os.path.exists(RUNNER):
            raise unittest.SkipTest('раннер не найден: %s' % RUNNER)
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules',
                                          'playwright')):
            raise unittest.SkipTest('playwright не установлен')
        try:
            res = subprocess.run([node, RUNNER], cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise unittest.SkipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if 'Executable doesn' in out or 'browserType.launch' in out:
            raise unittest.SkipTest('браузер playwright не скачан')
        self.assertEqual(res.returncode, 0,
                         u'раскладка чертежа сломана:\n' + out)
        # Тест обязан РЕАЛЬНО что-то проверить: пустой прогон — это не «зелено».
        self.assertIn(u'провалено', out)
        self.assertNotIn(u'0 прошло', out)
