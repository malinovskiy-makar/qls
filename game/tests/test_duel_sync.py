# -*- coding: utf-8 -*-
u"""Дуэль: только с аккаунтом, лобби, синхронный старт, табло, итог (15.09.2026).

Решение владельца: дуэль строго синхронна — пока соперник не зашёл, играть
нельзя; оба стартуют по одному отсчёту от пяти со звуком; аноним видит окно
регистрации. Итог — таблица сравнения двоих по тем метрикам, что реально
хранятся в `GameResult`.
"""
import json
import os
import shutil
import subprocess
import unittest

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from game import config, consumers, routing as game_routing, state as run_state
from game.models import GameResult, GameSet
from game.tests.test_duel import make_q
from game.tests.test_page_js import inline_js, page_source

User = get_user_model()
IN_MEMORY = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
ws_app = URLRouter(game_routing.websocket_urlpatterns)
XHR = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class DuelNeedsAccountTests(TestCase):
    def setUp(self):
        make_q(12)

    def test_xhr_without_login_gets_json_403(self):
        resp = self.client.get(reverse('game:duel_new'), {'mode': 'blitz'}, **XHR)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json(), {'ok': False, 'error': 'login'})
        self.assertFalse(GameSet.objects.exists())

    def test_address_bar_without_login_goes_to_login(self):
        resp = self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue('/login/' in resp['Location'], resp['Location'])

    def test_start_screen_has_the_account_window(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        for needle in ('id="dm-auth"', 'Дуэль только с аккаунтом: соперника нужно как-то называть',
                       'href="/register/?next=/game/"', 'href="/login/?next=/game/"'):
            self.assertTrue(needle in html, 'нет на стартовой: %s' % needle)
        js = inline_js(page_source())
        self.assertTrue("'#dm-auth:not([hidden])'" in js, 'окно входа не в modalIsOpen')
        self.assertTrue("d.error === 'login'" in js, 'окно вызова не ловит отказ входа')
        self.assertTrue("if (on && !CFG.is_authenticated) { openDuelAuth(true); return; }" in js,
                        'гостю открывается окно вызова, а не окно входа')


class DuelLobbyTests(TestCase):
    def setUp(self):
        make_q(12)
        self.author = User.objects.create_user(username='avtor', password='p12345')
        self.client.force_login(self.author)
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'}, **XHR)
        self.gset = GameSet.objects.get(kind='duel')
        self.url = reverse('game:set_page', args=[self.gset.code])

    def test_duel_set_page_is_a_lobby_without_a_play_button(self):
        html = self.client.get(self.url).content.decode('utf-8')
        self.assertFalse('id="set-play"' in html, 'у дуэли осталась кнопка «Играть»')
        for needle in ('id="duel-lobby"', 'id="duel-code">%s<' % self.gset.code,
                       '>Скопировать код<', '>Скопировать ссылку<', 'Ждём соперника',
                       'href="/game/">Отменить дуэль<'):
            self.assertTrue(needle in html, 'нет в лобби: %s' % needle)

    def test_lobby_is_a_page_without_the_start_screen_behind(self):
        u"""Макет DuelLobby (ADR 0112): шапка сайта и карточка, зон главной нет."""
        html = self.client.get(self.url).content.decode('utf-8')
        for gone in ('id="mode-grid"', 'id="start-main"', 'id="lb-card"', 'id="entry-row"',
                     'id="play-btn"'):
            self.assertFalse(gone in html, 'в лобби осталась главная: %s' % gone)
        # На обычной странице игры зоны на месте.
        self.assertTrue('id="mode-grid"' in self.client.get(reverse('game:page')).content.decode('utf-8'))

    def test_lobby_says_terms_and_shows_two_slots(self):
        html = self.client.get(self.url).content.decode('utf-8')
        mode = config.MODES['blitz']
        title = '%s · 2 мин · 3 жизни' % mode['title']
        self.assertTrue(title in html, 'нет условий дуэли: %s' % title)
        self.assertTrue('без фильтров · у обоих одни и те же вопросы · раунд без лимита вопросов' in html)
        self.assertTrue('Вы · avtor' in html)
        self.assertTrue('id="duel-slot-rival"' in html and 'Ждём соперника…' in html)
        self.assertFalse('150' in html.split('id="duel-lobby"', 1)[1].split('</section>', 1)[0])

    def test_rival_sees_the_author_in_the_lobby(self):
        self.client.force_login(User.objects.create_user(username='sopernik', password='p12345'))
        html = self.client.get(self.url).content.decode('utf-8')
        self.assertTrue('Соперник: avtor' in html, 'сопернику не назван автор')

    def test_challenge_window_goes_straight_to_the_lobby(self):
        js = inline_js(page_source())
        self.assertTrue('location.href = d.play_url;' in js, 'окно не уводит в лобби')
        for gone in ("$('dm-step2')", 'function listen(code)', "$('dm-play')"):
            self.assertFalse(gone in js, 'окно вызова всё ещё слушает сокет: %s' % gone)

    def test_invitation_page_accepts_instead_of_playing(self):
        self.client.force_login(User.objects.create_user(username='gost', password='p12345'))
        html = self.client.get(reverse('game:duel', args=[self.gset.code])).content.decode('utf-8')
        self.assertTrue('>Принять вызов</a>' in html, 'на приглашении нет «Принять вызов»')


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
class DuelStartSocketTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user('sync_a', password='x')
        self.b = User.objects.create_user('sync_b', password='x')
        self.gset = GameSet.objects.create(code='SYNC0001', mode='blitz', kind='duel',
                                           author=self.a, question_ids=[1, 2, 3])

    def connect(self, user):
        comm = WebsocketCommunicator(ws_app, '/ws/duel/%s/' % self.gset.code)
        comm.scope['user'] = user
        return comm

    async def start_message(self, comm):
        for _ in range(6):
            payload = json.loads(await comm.receive_from(timeout=2))
            if payload['type'] == 'start':
                return payload
        self.fail('старта не пришло')

    def test_countdown_is_five_seconds(self):
        self.assertEqual(consumers.COUNTDOWN_S, 5)

    async def test_second_player_gets_start_with_at_now_and_five(self):
        first, second = self.connect(self.a), self.connect(self.b)
        self.assertTrue((await first.connect())[0])
        self.assertTrue((await second.connect())[0])
        start = await self.start_message(first)
        self.assertEqual(start['in'], 5)
        self.assertTrue(4000 < start['at'] - start['now'] <= 5000, start)
        stored = await database_sync_to_async(run_state.duel_started_at)(self.gset.code)
        self.assertEqual(stored, start['at'])
        await first.disconnect()
        await second.disconnect()

    async def test_hello_after_the_start_gets_the_same_moment(self):
        first, second = self.connect(self.a), self.connect(self.b)
        await first.connect()
        await second.connect()
        at = (await self.start_message(first))['at']
        await self.start_message(second)
        await first.send_to(text_data=json.dumps({'type': 'hello'}))
        again = await self.start_message(first)
        self.assertEqual(again['at'], at)
        self.assertTrue(again['in'] <= 5)
        await first.disconnect()
        await second.disconnect()


class DuelStartMomentTests(TestCase):
    u"""Момент старта назначается один раз: второй вход в комнату его не двигает."""

    def setUp(self):
        cache.clear()

    def test_the_moment_is_set_once(self):
        self.assertIsNone(run_state.duel_started_at('ONCE0001'))
        self.assertEqual(run_state.duel_start_at('ONCE0001', 1000), 1000)
        self.assertEqual(run_state.duel_start_at('ONCE0001', 9000), 1000)
        self.assertEqual(run_state.duel_started_at('ONCE0001'), 1000)


class DuelCompareTableTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='anna', password='p12345')
        self.b = User.objects.create_user(username='boris', password='p12345')
        self.gset = GameSet.objects.create(code='CMP00001', mode='blitz', kind='duel',
                                           author=self.a, question_ids=[1, 2])

    def result(self, user, **fields):
        return GameResult.objects.create(game_set=self.gset, user=user, mode='blitz', **fields)

    def test_duel_page_compares_two_players_metric_by_metric(self):
        self.result(self.a, score=1200, correct_count=9, wrong_count=2, skip_count=1,
                    total_count=11, max_combo=1.5, avg_correct_ms=1800, wall_ms=125000)
        self.result(self.b, score=800, correct_count=6, wrong_count=3, skip_count=0,
                    total_count=9, max_combo=1.25, avg_correct_ms=None, wall_ms=None)
        self.client.force_login(self.b)
        html = self.client.get(reverse('game:duel', args=[self.gset.code])).content.decode('utf-8')
        # Смотрит boris — его столбец слева. Лучший выделен В СТРОКЕ (ADR 0112):
        # у anna больше очков, у boris меньше пропусков; нет замера — без выделения.
        rows = {
            'Очки': '<td>800</td><td class="w">1\u00a0200</td>',
            'Верных': '<td>6</td><td class="w">9</td>',
            'Ошибок': '<td>3</td><td class="w">2</td>',
            'Пропусков': '<td class="w">0</td><td>1</td>',
            'Точность': '<td>67 %</td><td class="w">82 %</td>',
            'Лучшее комбо': '<td>×1,25</td><td class="w">×1,5</td>',
            'Секунд на верный': '<td>–</td><td>1,8</td>',
            'Продержался': '<td>–</td><td>2:05</td>',
        }
        for label, cells in rows.items():
            needle = '<th scope="row">%s</th>%s' % (label, cells)
            self.assertTrue(needle in html, 'нет в итоге дуэли: %s' % needle)
        self.assertTrue('Реванш' in html)


class SoundCountdownTests(TestCase):
    JS = os.path.join(settings.BASE_DIR, 'game', 'static', 'game', 'sound.js')

    def test_countdown_is_in_the_sound_module(self):
        with open(self.JS, encoding='utf-8') as handle:
            src = handle.read()
        self.assertTrue('countdown: function (n) {' in src, 'нет rushSound.countdown')
        self.assertTrue('freq: 660' in src and 'freq: 990' in src)

    def test_lobby_countdown_beeps_on_every_second_and_on_go(self):
        js = inline_js(page_source())
        self.assertTrue("rush('countdown', left);" in js, 'цифры отсчёта немые')
        self.assertTrue("rush('countdown', 0);" in js, '«Поехали!» немое')

    @unittest.skipIf(shutil.which('node') is None, 'node не установлен')
    def test_sound_module_parses(self):
        proc = subprocess.run(['node', '--check', self.JS], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
