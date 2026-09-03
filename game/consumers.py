# -*- coding: utf-8 -*-
u"""
WebSocket дуэли Wecon Rush: живое табло соперника и реакции.

⚠️ ЧТО ЗДЕСЬ НЕ ПРОИСХОДИТ. Игра НЕ идёт по WebSocket. Вопросы выдаёт и
ответы принимает обычный HTTP (`api_question` / `api_answer`), очки считает
сервер там же. Здесь только ТАБЛО и РЕАКЦИИ. Отсюда главное свойство:
разрыв соединения не ломает забег — пропадает табло соперника, и всё.
Переподключение восстанавливает его из состояния забега (game/state.py).

⚠️ ИСТОЧНИК СЧЁТА — ТОЛЬКО СЕРВЕР. Событие `score` рассылает `api_answer`
после записи состояния. Сообщение `score`, пришедшее ОТ КЛИЕНТА,
игнорируется молча: иначе счёт соперника рисовал бы любой, кто откроет
консоль. Это то же правило, по которому очки вообще считает сервер
(game/CLAUDE.md), и здесь оно особенно на месте — второго счёта у нас нет.

⚠️ КТО ПУСКАЕТСЯ. Только вошедшие и только в набор `kind='duel'`. Аноним и
чужой пользователь закрываются кодом 4403. «Чужой» значит: набор уже играют
двое других — третьего в комнату не пускаем, у дуэли ровно две стороны.
Смотреть чужую дуэль можно на её обычной странице `/game/d/<код>/`.
"""
import json
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from game import config

# Ровно восемь реакций. Белый список закрытый: свободный текст в дуэли
# означал бы чат без модерации между школьниками.
EMOJI = ('gg', 'wow', 'fire', 'think', 'oops', 'fast', 'close', 'gl')

# Не чаще одной реакции в две секунды на игрока. Лишние молча отбрасываются:
# отвечать на них ошибкой значит учить клиента ретраить.
EMOJI_COOLDOWN_S = 2.0

# Обратный отсчёт перед стартом, когда оба на месте.
COUNTDOWN_S = 3

CLOSE_FORBIDDEN = 4403


def room_name(code):
    return 'duel_%s' % code


class DuelConsumer(AsyncWebsocketConsumer):
    u"""Одна комната на дуэль, максимум два участника."""

    async def connect(self):
        self.code = self.scope['url_route']['kwargs']['code']
        self.group = room_name(self.code)
        self.last_emoji = 0.0

        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        self.user_id = user.id
        self.username = user.get_username()

        allowed = await self._may_join()
        if not allowed:
            await self.close(code=CLOSE_FORBIDDEN)
            return

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self._announce_presence('join')

    async def disconnect(self, code):
        if getattr(self, 'group', None) is None:
            return
        await self._announce_presence('leave')
        await self.channel_layer.group_discard(self.group, self.channel_name)

    # ---------------------------------------------------------------- ввод
    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or '{}')
        except ValueError:
            return
        kind = data.get('type')

        if kind == 'emoji':
            name = data.get('name')
            if name not in EMOJI:
                return
            now = time.monotonic()
            if now - self.last_emoji < EMOJI_COOLDOWN_S:
                return          # лишнюю реакцию молча отбрасываем
            self.last_emoji = now
            await self.channel_layer.group_send(self.group, {
                'type': 'duel.emoji', 'name': name,
                'user_id': self.user_id, 'username': self.username})
            return

        if kind == 'hello':
            # Переподключился: восстанавливаем табло по состоянию соперника.
            await self._send_board()
            return

        # ⚠️ `score` и всё прочее от клиента ИГНОРИРУЕТСЯ. Счёт рассылает
        # только сервер из api_answer.

    # -------------------------------------------------------------- вывод
    async def duel_presence(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence', 'action': event['action'],
            'user_id': event['user_id'], 'username': event['username'],
        }, ensure_ascii=False))

    async def duel_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'start', 'in': event.get('in', COUNTDOWN_S),
        }))

    async def duel_score(self, event):
        # Свой же счёт обратно не шлём: клиент его и так знает от api_answer,
        # а дубль на экране мигал бы.
        if event.get('user_id') == self.user_id:
            return
        await self.send(text_data=json.dumps({
            'type': 'score', 'user_id': event['user_id'],
            'username': event.get('username', ''),
            'score': event.get('score', 0),
            'correct': event.get('correct', 0),
            'lives': event.get('lives', 0),
            'seconds_left': event.get('seconds_left'),
        }, ensure_ascii=False))

    async def duel_emoji(self, event):
        if event.get('user_id') == self.user_id:
            return
        await self.send(text_data=json.dumps({
            'type': 'emoji', 'name': event['name'],
            'user_id': event['user_id'],
            'username': event.get('username', ''),
        }, ensure_ascii=False))

    async def duel_finished(self, event):
        if event.get('user_id') == self.user_id:
            return
        await self.send(text_data=json.dumps({
            'type': 'finished', 'user_id': event['user_id'],
            'username': event.get('username', ''),
            'score': event.get('score', 0),
            'correct': event.get('correct', 0),
        }, ensure_ascii=False))

    # ------------------------------------------------------------ помощь
    async def _announce_presence(self, action):
        from game import state as run_state
        if action == 'join':
            present = await database_sync_to_async(run_state.duel_join)(
                self.code, self.user_id)
        else:
            present = await database_sync_to_async(run_state.duel_leave)(
                self.code, self.user_id)
        await self.channel_layer.group_send(self.group, {
            'type': 'duel.presence', 'action': action,
            'user_id': self.user_id, 'username': self.username,
            'present': present})
        # ⚠️ ОБРАТНЫЙ ОТСЧЁТ — КОГДА ОБА НА МЕСТЕ, И СЧИТАЕМ ПО ЛЮДЯМ, А НЕ
        # ПО СОКЕТАМ. У игрока может быть открыто две вкладки, и «двое в
        # комнате» тогда значило бы одного человека против самого себя.
        if action == 'join' and len(present) >= 2:
            await self.channel_layer.group_send(self.group, {
                'type': 'duel.start', 'in': COUNTDOWN_S})

    async def _send_board(self):
        u"""Табло соперника по состоянию его забега (переподключение)."""
        row = await self._opponent_row()
        if row is None:
            return
        await self.send(text_data=json.dumps(
            dict(row, type='score'), ensure_ascii=False))

    @database_sync_to_async
    def _may_join(self):
        u"""Пускаем, если набор существует, это дуэль и мест ещё хватает.

        ⚠️ УЧАСТНИКОВ СЧИТАЕМ ПО ТРЁМ ИСТОЧНИКАМ, и все три нужны:
        автор набора (он вызвал), те, кто уже СЫГРАЛ (GameResult), и те, кто
        уже НАЧАЛ забег (запись комнаты). Без третьего третий игрок успевал
        бы влезть в комнату, пока соперник ещё играет: результата у соперника
        нет, а место, с точки зрения базы, свободно.
        """
        from game.models import GameResult, GameSet
        from game import state as run_state
        gset = GameSet.objects.filter(code=self.code, kind='duel').first()
        if gset is None:
            return False
        self.mode = gset.mode
        players = set(
            GameResult.objects.filter(game_set=gset, user__isnull=False)
            .values_list('user_id', flat=True))
        if gset.author_id:
            players.add(gset.author_id)
        room = run_state._duel_room(self.code)
        players.update(int(uid) for uid in room['runs'])
        players.update(int(uid) for uid in room['present'])
        if self.user_id in players:
            return True
        return len(players) < 2

    @database_sync_to_async
    def _opponent_row(self):
        u"""Счёт соперника: сначала живой забег, потом готовый результат.

        Живой забег адресуется через запись комнаты (state.duel_rivals):
        `GameResult` тут не годится — он появляется, только когда забег
        ЗАКОНЧЕН, а табло нужно во время.
        """
        from game.models import GameResult, GameSet
        from game import state as run_state
        from problems.models import User

        for uid, run_id in run_state.duel_rivals(self.code, self.user_id):
            live = run_state.load_by_id(run_id)
            if not live:
                continue
            name = User.objects.filter(pk=uid).values_list(
                'username', flat=True).first() or ''
            return {
                'user_id': uid,
                'username': name,
                'score': live.get('score', 0),
                'correct': sum(1 for r in live.get('log', [])
                               if r.get('outcome') == 'correct'),
                'lives': live.get('lives', 0),
                'seconds_left': None,
            }

        gset = GameSet.objects.filter(code=self.code, kind='duel').first()
        if gset is None:
            return None
        rival = (GameResult.objects
                 .filter(game_set=gset, user__isnull=False)
                 .exclude(user_id=self.user_id)
                 .select_related('user').order_by('-created_at').first())
        if rival is None:
            return None
        return {
            'user_id': rival.user_id,
            'username': rival.user.get_username(),
            'score': rival.score,
            'correct': rival.correct_count,
            'lives': 0,
            'seconds_left': 0,
        }


async def health(scope, receive, send):
    u"""`/ws/health/` — жив ли ASGI-процесс. Без входа и без БД.

    Нужна балансировщику и выкатке: gunicorn может отвечать, а daphne
    лежать, и без отдельной проверки это заметит только игрок.
    """
    await send({'type': 'http.response.start', 'status': 200,
                'headers': [(b'content-type', b'text/plain; charset=utf-8')]})
    await send({'type': 'http.response.body', 'body': b'ws ok'})


def duel_score_event(state, user, seconds_left=None):
    u"""Событие табло из состояния забега. Зовётся из api_answer.

    Считает ЗДЕСЬ, а не во вьюхе, чтобы поле «верных» у табло и у сводки
    считалось одной формулой: два счётчика одного и того же разъезжаются.
    """
    return {
        'type': 'duel.score',
        'user_id': user.id if user and user.is_authenticated else None,
        'username': user.get_username() if user
        and user.is_authenticated else '',
        'score': state.get('score', 0),
        'correct': sum(1 for r in state.get('log', [])
                       if r.get('outcome') == 'correct'),
        'lives': state.get('lives', config.MODES.get(
            state.get('mode'), {}).get('lives', 0)),
        'seconds_left': seconds_left,
    }
