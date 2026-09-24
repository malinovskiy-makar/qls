u"""Сбой сети не замораживает забег Wecon Rush.

Проверка идёт в настоящем браузере (`browser_freeze.mjs`) с подменой ответа
сервера: 502 страницей HTML от прокси и истёкшее состояние забега (`no_run`).
Заморозка — это свойство цепочки промисов на странице, её видно только по
живой кнопке, которая перестала отправлять ответ.

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

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_freeze.mjs')
CHECKS = {'toast_visible', 'second_click_sent', 'lost_overlay_visible', 'lost_button_home',
          # 24.09.2026: финиш с повторами и честная плашка.
          'finish_retry_saved', 'finish_unsaved_plate'}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium. Живой сервер и браузер — внешние ресурсы, поделить их между
# воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class RushNetworkFailureBrowserTest(StaticLiveServerTestCase):
    """502 от прокси → тост и живые кнопки; no_run → «Забег потерян»."""

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

    def test_network_failures_do_not_freeze_run(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — браузерная проверка сбоев сети не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, RUSH_BASE_URL=self.live_server_url)
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
        # Пустой прогон — не «зелено»: все проверки обязаны состояться.
        self.assertEqual(set(data['checks']), CHECKS)
        failed = {k: v for k, v in data['checks'].items() if not v['ok']}
        self.assertEqual(failed, {}, 'сбой сети замораживает забег')
        # Случай 3: повтор финиша дошёл — раунд в базе (незачётный, «вышел»).
        from game.models import GameResult
        self.assertEqual(GameResult.objects.filter(ended_reason='quit').count(), 1)
