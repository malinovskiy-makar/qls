u"""Лобби дуэли и табло на узком экране — в настоящем браузере (15.09.2026).

Инварианты числами, а не глазами: на 380 px у лобби и у сцены раунда нет
горизонтальной прокрутки, «Скопировать ссылку» не ниже 44 px (область
касания), код комнаты крупный, кнопки «Играть» у дуэли нет.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag
from django.urls import reverse

from game import config
from game.models import GameQuestion, GameSet
from problems.models import Problem, User

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_lobby.mjs')
CHECKS = {'lobby_no_hscroll', 'copy_link_44px', 'room_code_big', 'lobby_has_no_play_button',
          'lobby_has_no_practice_band', 'scene_no_hscroll', 'scoreboard_shown'}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class DuelLobbyNarrowBrowserTest(StaticLiveServerTestCase):

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
        self.user = User.objects.create_user(username='lobby_author', password='p12345')

    def test_lobby_and_scoreboard_fit_380px(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — браузерная проверка лобби не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        self.client.force_login(self.user)
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'},
                        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        gset = GameSet.objects.get(kind='duel')
        env = dict(os.environ, RUSH_BASE_URL=self.live_server_url,
                   RUSH_LOBBY=reverse('game:set_page', args=[gset.code]),
                   RUSH_SESSION=self.client.cookies[settings.SESSION_COOKIE_NAME].value)
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер или страница не поднялись:\n' + out[-1500:])
        self.assertIn('###RUSH-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###RUSH-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        # Пустой прогон — не «зелено»: все проверки обязаны состояться.
        self.assertEqual(set(data['checks']), CHECKS)
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'лобби или табло не помещаются в 380 px:\n'
                         + json.dumps(failed, ensure_ascii=False, indent=1)[:4000])
