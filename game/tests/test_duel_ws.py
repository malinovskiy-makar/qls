# -*- coding: utf-8 -*-
u"""
WebSocket дуэли: кого пускаем, что рассылаем и чего не слушаем.

Главные инварианты:
- источник счёта только сервер; клиентский `score` игнорируется;
- в комнату пускаются лишь вошедшие и лишь участники этой дуэли;
- реакции из закрытого списка и не чаще одной в две секунды;
- разрыв не ломает забег, переподключение восстанавливает табло;
- `/ws/health/` отвечает без входа и без базы.
"""
import json

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import HttpCommunicator, WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings

from channels.routing import URLRouter

from config.asgi import application
from game import consumers, routing as game_routing, state as run_state

# ⚠️ СОКЕТ ПОДНИМАЕТСЯ БЕЗ ORIGIN-ПРОВЕРКИ И БЕЗ AuthMiddlewareStack, и это
# намеренно: у WebsocketCommunicator нет ни заголовка Origin, ни куки
# сессии, а проверяем мы СВОЙ консьюмер, а не обвязку channels. Что обвязка
# на месте, отдельно закрепляет AsgiWiringTests ниже.
ws_app = URLRouter(game_routing.websocket_urlpatterns)
from game.models import GameQuestion, GameSet
from problems.models import Problem

IN_MEMORY = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


def make_question():
    p = Problem.objects.create(
        title='Т', statement='Условие про рынок.',
        problem_type='тест: один ответ', answer='а',
        status=Problem.Status.PUBLISHED)
    return GameQuestion.objects.create(
        problem=p, question_type='single', question='Что со спросом?',
        options=['вырастет', 'упадёт'], correct_index=0, lang='ru',
        topics=[], source_group='books')


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
class DuelSocketTests(TransactionTestCase):
    u"""Комната дуэли."""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.a = User.objects.create_user('duel_a', password='x')
        self.b = User.objects.create_user('duel_b', password='x')
        self.c = User.objects.create_user('duel_c', password='x')
        qs = [make_question() for _ in range(4)]
        self.gset = GameSet.objects.create(
            code='DUEL0001', mode='blitz', kind='duel',
            author=self.a, question_ids=[q.id for q in qs])

    def connect(self, user=None, code=None):
        comm = WebsocketCommunicator(
            ws_app, '/ws/duel/%s/' % (code or self.gset.code))
        comm.scope['user'] = user if user is not None else _Anon()
        return comm

    async def test_anonymous_is_refused(self):
        comm = self.connect(user=_Anon())
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, consumers.CLOSE_FORBIDDEN)

    async def test_a_third_player_is_refused(self):
        u"""У дуэли ровно две стороны; смотреть можно на странице дуэли."""
        await database_sync_to_async(run_state.duel_register_run)(
            self.gset.code, self.b.id, 'run-b')
        first = self.connect(self.a)
        second = self.connect(self.b)
        self.assertTrue((await first.connect())[0])
        self.assertTrue((await second.connect())[0])

        third = self.connect(self.c)
        connected, code = await third.connect()
        self.assertFalse(connected)
        self.assertEqual(code, consumers.CLOSE_FORBIDDEN)
        await first.disconnect()
        await second.disconnect()

    async def test_unknown_room_is_refused(self):
        comm = self.connect(self.a, code='NOSUCH01')
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, consumers.CLOSE_FORBIDDEN)

    async def test_start_only_when_both_are_here(self):
        first = self.connect(self.a)
        self.assertTrue((await first.connect())[0])
        # Свой же приход: присутствие есть, старта нет.
        await first.receive_from()          # presence(join) про себя
        self.assertTrue(await first.receive_nothing(timeout=0.2))

        second = self.connect(self.b)
        self.assertTrue((await second.connect())[0])

        kinds = set()
        for _ in range(4):
            if await first.receive_nothing(timeout=0.3):
                break
            kinds.add(json.loads(await first.receive_from())['type'])
        self.assertIn('start', kinds)
        await first.disconnect()
        await second.disconnect()

    async def test_client_score_is_ignored(self):
        u"""Счёт рисует только сервер. Иначе его нарисует любой."""
        first = self.connect(self.a)
        second = self.connect(self.b)
        await first.connect()
        await second.connect()
        await _drain(first)
        await _drain(second)

        await second.send_to(text_data=json.dumps({
            'type': 'score', 'score': 999999, 'lives': 3}))
        self.assertTrue(await first.receive_nothing(timeout=0.3),
                        'клиентский счёт долетел до соперника')
        await first.disconnect()
        await second.disconnect()

    async def test_server_score_reaches_the_rival(self):
        first = self.connect(self.a)
        second = self.connect(self.b)
        await first.connect()
        await second.connect()
        await _drain(first)
        await _drain(second)

        layer = get_channel_layer()
        await layer.group_send(consumers.room_name(self.gset.code), {
            'type': 'duel.score', 'user_id': self.b.id, 'username': 'duel_b',
            'score': 250, 'correct': 3, 'lives': 2, 'seconds_left': 40})
        payload = json.loads(await first.receive_from())
        self.assertEqual(payload['type'], 'score')
        self.assertEqual(payload['score'], 250)
        self.assertEqual(payload['username'], 'duel_b')
        # Себе своё же событие не приходит: дубль на экране мигал бы.
        self.assertTrue(await second.receive_nothing(timeout=0.2))
        await first.disconnect()
        await second.disconnect()

    async def test_emoji_whitelist_and_cooldown(self):
        first = self.connect(self.a)
        second = self.connect(self.b)
        await first.connect()
        await second.connect()
        await _drain(first)
        await _drain(second)

        # Сначала ЧУЖАЯ реакция: белый список проверяется до задержки, и
        # отброшенная реакция задержку не тратит.
        await second.send_to(text_data=json.dumps({
            'type': 'emoji', 'name': '<img src=x>'}))
        self.assertTrue(await first.receive_nothing(timeout=0.3),
                        'реакция вне белого списка пролезла')

        await second.send_to(text_data=json.dumps({
            'type': 'emoji', 'name': 'gg'}))
        payload = json.loads(await first.receive_from())
        self.assertEqual(payload['type'], 'emoji')
        self.assertEqual(payload['name'], 'gg')

        # Восемь подряд за те же две секунды: отбрасываются молча.
        for _ in range(8):
            await second.send_to(text_data=json.dumps({
                'type': 'emoji', 'name': 'fire'}))
        self.assertTrue(await first.receive_nothing(timeout=0.3),
                        'частые реакции пролезли')
        await first.disconnect()
        await second.disconnect()

    async def test_reconnect_restores_the_board(self):
        u"""Разрыв не ломает забег: табло восстанавливается по состоянию."""
        await database_sync_to_async(run_state.duel_register_run)(
            self.gset.code, self.b.id, 'run-b')
        await database_sync_to_async(run_state.save_by_id)({
            'run_id': 'run-b', 'mode': 'blitz', 'score': 420, 'lives': 2,
            'log': [{'outcome': 'correct'}, {'outcome': 'correct'},
                    {'outcome': 'wrong'}]})

        first = self.connect(self.a)
        await first.connect()
        await _drain(first)
        await first.send_to(text_data=json.dumps({'type': 'hello'}))
        payload = json.loads(await first.receive_from())
        self.assertEqual(payload['type'], 'score')
        self.assertEqual(payload['score'], 420)
        self.assertEqual(payload['correct'], 2)
        self.assertEqual(payload['lives'], 2)
        await first.disconnect()


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
class HealthTests(TransactionTestCase):
    u"""Проверка живости ASGI-процесса."""

    async def test_health_answers_without_login(self):
        comm = HttpCommunicator(application, 'GET', '/ws/health/')
        response = await comm.get_response(timeout=5)
        self.assertEqual(response['status'], 200)
        self.assertIn(b'ws ok', response['body'])


class _Anon(object):
    is_authenticated = False
    id = None

    def get_username(self):
        return ''


async def _drain(comm, timeout=0.3):
    u"""Вычитать всё, что уже пришло (присутствие, старт)."""
    while not await comm.receive_nothing(timeout=timeout):
        await comm.receive_from()


class AsgiWiringTests(TransactionTestCase):
    u"""Обвязка ASGI на месте: без неё сокет открывается с чужого сайта.

    Проверка Origin — это защита от CSRF на сокете: без неё любая страница
    в интернете открывает WebSocket с куками игрока, а обычная CSRF-защита
    Django сокеты не покрывает.
    """

    def test_websocket_is_wrapped_in_origin_and_auth(self):
        from channels.security.websocket import OriginValidator
        from channels.sessions import CookieMiddleware

        ws = application.application_mapping['websocket']
        # AllowedHostsOriginValidator — фабрика, она возвращает
        # OriginValidator со списком из ALLOWED_HOSTS.
        self.assertIsInstance(ws, OriginValidator)
        # Дальше обязан идти AuthMiddlewareStack, а не голый роутер: иначе
        # у консьюмера не будет scope['user'], и «только вошедшие» стало бы
        # «никто».
        self.assertIsInstance(ws.application, CookieMiddleware)

    def test_http_keeps_django_and_adds_health(self):
        self.assertIn('http', application.application_mapping)
