u"""Окно поверх забега забирает клавиатуру и ставит Wecon Rush на паузу.

Проверка идёт в настоящем браузере (`browser_modals.mjs`): дефект живёт на
стыке двух скриптов страницы — игры и окна «Проблема или предложение» — и
виден только по живому таймеру и живым клавишам. Питон-тест шаблона его не
увидел бы.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает: машина без браузера
не должна ронять остальной прогон.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag

from game import config
from game.models import GameQuestion
from problems.models import Problem

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_modals.mjs')
CHECKS = {'question_same', 'no_answers_sent', 'timer_paused', 'timer_resumed',
          'escape_closes_modal', 'report_window_pauses'}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium. Живой сервер и браузер — внешние ресурсы, поделить их между
# воркерами шага A нельзя; а под конкуренцией за процессор проверка таймера
# с допуском 0,1 с краснела бы по чужой вине.
@tag('game', 'browser', 'serial')
class RushModalPauseBrowserTest(StaticLiveServerTestCase):
    """Блиц: окно открыто → пробел, «1» и Enter не трогают забег, таймер стоит;
    окно закрыто → таймер снова идёт."""

    def setUp(self):
        blitz = config.MODES['blitz']
        for i in range(config.MIN_PLAYABLE + 2):
            problem = Problem.objects.create(
                title='', statement='Вопрос номер %d?' % i, answer='',
                problem_type='тест: один ответ', status='published')
            GameQuestion.objects.create(
                problem=problem, question_type=blitz['question_type'],
                question='Вопрос номер %d: что изучает микроэкономика?' % i,
                options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                correct_index=0, difficulty=2, topics=[], lang='ru')

    def test_modal_takes_keys_and_pauses_run(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — браузерная проверка паузы не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, RUSH_BASE_URL=self.live_server_url,
                   RUSH_DURATION=str(config.MODES['blitz']['duration']))
        try:
            # ⚠️ encoding обязателен: без него вывод раннера декодируется
            # кодировкой консоли (cp1251 на русской Windows) и теряется.
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер или страница игры не поднялись:\n' + out[-1500:])

        self.assertIn('###RUSH-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###RUSH-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        # Пустой прогон — не «зелено»: все четыре проверки обязаны состояться.
        self.assertEqual(set(data['checks']), CHECKS)
        failed = {k: v for k, v in data['checks'].items() if not v['ok']}
        self.assertEqual(failed, {}, 'окно поверх забега не держит клавиши или паузу')
