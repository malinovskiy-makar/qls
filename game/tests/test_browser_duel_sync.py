u"""Синхронный старт дуэли — в двух настоящих браузерах (15.09.2026).

Решение владельца: пока соперник не зашёл, играть нельзя; оба стартуют по
одному отсчёту от пяти. Здесь это меряется, а не читается из кода
(`browser_duel_sync.mjs`): автор ждёт в лобби, соперник входит, у обоих идёт
отсчёт, экран раунда открывается у обоих в пределах секунды и не раньше, чем
через ~4 с после входа соперника.

⚠️ НУЖЕН ЖИВОЙ daphne, А НЕ WSGI-СЕРВЕР. Отсчёт приходит по WebSocket, а
`StaticLiveServerTestCase` сокетов не держит. `ChannelsLiveServerTestCase`
поднимает daphne отдельным процессом, и этому процессу нужна ФАЙЛОВАЯ база:
на SQLite в памяти (локальный прогон по умолчанию) тест пропускается с
причиной, на PostgreSQL (`--settings=config.settings_test_pg`, CI) идёт
по-настоящему.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess
import unittest

from channels.testing import ChannelsLiveServerTestCase
from django.conf import settings
from django.test import Client, tag
from django.urls import reverse

from game import config
from game.models import GameQuestion, GameSet
from problems.models import Problem, User

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_duel_sync.mjs')
CHECKS = {'rival_sees_author', 'author_counts_down_from_five', 'rival_counts_down',
          'both_started', 'started_together', 'waited_for_countdown'}
DB = settings.DATABASES['default']
IN_MEMORY_SQLITE = (DB['ENGINE'].endswith('sqlite3')
                    and not (DB.get('TEST') or {}).get('NAME'))


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает daphne отдельным процессом и гоняет
# по нему два Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
@unittest.skipIf(IN_MEMORY_SQLITE, 'daphne отдельным процессом не видит SQLite в памяти: '
                 'тест идёт на PostgreSQL (--settings=config.settings_test_pg)')
class DuelSyncStartBrowserTest(ChannelsLiveServerTestCase):

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
        self.author = User.objects.create_user(username='sync_author', password='p12345')
        self.rival = User.objects.create_user(username='sync_rival', password='p12345')

    @staticmethod
    def session_for(user):
        client = Client()
        client.force_login(user)
        return client, client.cookies[settings.SESSION_COOKIE_NAME].value

    def test_both_players_start_on_one_countdown(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — браузерная проверка дуэли не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        author_client, author_session = self.session_for(self.author)
        author_client.get(reverse('game:duel_new'), {'mode': 'blitz'},
                          HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        gset = GameSet.objects.get(kind='duel')
        _rival_client, rival_session = self.session_for(self.rival)
        env = dict(os.environ, RUSH_BASE_URL=self.live_server_url,
                   RUSH_LOBBY=reverse('game:set_page', args=[gset.code]),
                   RUSH_AUTHOR=self.author.username,
                   RUSH_AUTHOR_SESSION=author_session, RUSH_RIVAL_SESSION=rival_session)
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер или лобби не поднялись:\n' + out[-1500:])
        self.assertIn('###RUSH-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###RUSH-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        # Пустой прогон — не «зелено»: все проверки обязаны состояться.
        self.assertEqual(set(data['checks']), CHECKS)
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'синхронный старт дуэли:\n'
                         + json.dumps(failed, ensure_ascii=False, indent=1)[:4000])
