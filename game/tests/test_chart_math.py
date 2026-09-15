u"""Подпись последнего значения на графике «Динамика раунда» не уходит за край.

Считает `game/static/game/chart_math.js` — тот же файл, что грузит страница:
node исполняет его и отдаёт числа питону. Проверка арифметическая, потому что
и дефект арифметический: подпись на 5 px выше точки максимума, стоявшей на
отступе 8, получала y = 3 и обрезалась верхним краем viewBox.
"""
import io
import json
import os
import shutil
import subprocess
import unittest

from django.conf import settings
from django.test import SimpleTestCase

MODULE = os.path.join(str(settings.BASE_DIR), 'game', 'static', 'game', 'chart_math.js')
PAGE = os.path.join(str(settings.BASE_DIR), 'game', 'templates', 'game', 'game.html')
H, P = 130, 8

# process.argv[1] у `node -e` — первый переданный аргумент, то есть путь модуля.
NODE_SCRIPT = r"""
require(process.argv[1]);
const m = globalThis.rushChartMath;
const scores = [0, 10, 20];
const max = Math.max(...scores);
const ys = scores.map((v) => m.scoreY(v, max, %d, %d));
console.log(JSON.stringify({ ys: ys, label: m.labelY(ys[ys.length - 1]) }));
""" % (H, P)


class ChartLabelInsideFrameTests(SimpleTestCase):

    @unittest.skipIf(shutil.which('node') is None, 'node не установлен')
    def test_label_and_points_stay_inside_the_frame(self):
        res = subprocess.run(['node', '-e', NODE_SCRIPT, MODULE], capture_output=True,
                             text=True, encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(data['label'], 12, data)
        for y in data['ys']:
            self.assertGreaterEqual(y, P, data)
            self.assertLessEqual(y, H - P, data)

    def test_page_draws_the_curve_through_the_module(self):
        u"""Страница не держит вторую копию формулы: иначе проверялся бы
        модуль, а рисовала бы старая арифметика."""
        src = io.open(PAGE, encoding='utf-8').read()
        self.assertIn("{% static 'game/chart_math.js' %}", src)
        self.assertIn('rushChartMath.scoreY(', src)
        self.assertIn('rushChartMath.labelY(', src)
        self.assertNotIn('yScore(scores[scores.length - 1]) - 5', src)
