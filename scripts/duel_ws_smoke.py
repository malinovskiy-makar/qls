# -*- coding: utf-8 -*-
u"""
Нагрузочный дым дуэли: 20 комнат × 2 клиента, ни одного потерянного `score`.

⚠️ ЭТО НЕ ТЕСТ НАБОРА, А ОТДЕЛЬНЫЙ ПРОГОН. Он поднимает слой каналов и
двадцать пар консьюмеров разом; в обычном прогоне это заняло бы секунды
чужого времени на каждом запуске и ничего не проверяло бы сверх того, что
уже закреплено в game/tests/test_duel_ws.py. Здесь другой вопрос: не
теряются ли сообщения, когда комнат много.

Считаем строго: каждому из 40 клиентов адресовано ровно `MESSAGES` событий
счёта (их шлёт соперник), и все обязаны дойти. Потеря хотя бы одного —
провал: табло, которое иногда врёт, хуже отсутствующего.

Запуск ИЗ КОРНЯ ПРОЕКТА:
    venv313/Scripts/python.exe scripts/duel_ws_smoke.py
    venv313/Scripts/python.exe scripts/duel_ws_smoke.py --rooms 50
"""
import argparse
import asyncio
import json
import os
import sys
import time

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from channels.layers import get_channel_layer            # noqa: E402
from channels.testing import WebsocketCommunicator       # noqa: E402
from channels.routing import URLRouter                   # noqa: E402

from game import consumers, routing, state as run_state  # noqa: E402


class FakeUser(object):
    is_authenticated = True

    def __init__(self, uid):
        self.id = uid
        self.pk = uid

    def get_username(self):
        return 'p%d' % self.id


async def one_room(app, index, messages):
    u"""Одна комната: двое подключаются, шлют счёт, считают полученное."""
    code = 'SMOKE%03d' % index
    a_id, b_id = 1000 + index * 2, 1001 + index * 2
    # Комната знает обоих: иначе третьего не отличить от участника.
    run_state.duel_register_run(code, a_id, 'run-a-%d' % index)
    run_state.duel_register_run(code, b_id, 'run-b-%d' % index)

    a = WebsocketCommunicator(app, '/ws/duel/%s/' % code)
    a.scope['user'] = FakeUser(a_id)
    b = WebsocketCommunicator(app, '/ws/duel/%s/' % code)
    b.scope['user'] = FakeUser(b_id)

    ok_a, _ = await a.connect()
    ok_b, _ = await b.connect()
    if not (ok_a and ok_b):
        return {'room': code, 'connected': False, 'got_a': 0, 'got_b': 0}

    # Вычитать присутствие и старт, чтобы они не путались со счётом.
    for comm in (a, b):
        while not await comm.receive_nothing(timeout=0.1):
            await comm.receive_from()

    layer = get_channel_layer()
    group = consumers.room_name(code)
    for n in range(messages):
        await layer.group_send(group, {
            'type': 'duel.score', 'user_id': b_id, 'username': 'p%d' % b_id,
            'score': 10 * (n + 1), 'correct': n + 1, 'lives': 3,
            'seconds_left': 100 - n})
        await layer.group_send(group, {
            'type': 'duel.score', 'user_id': a_id, 'username': 'p%d' % a_id,
            'score': 5 * (n + 1), 'correct': n, 'lives': 2,
            'seconds_left': 100 - n})

    got_a = got_b = 0
    for comm, counter in ((a, 'a'), (b, 'b')):
        while not await comm.receive_nothing(timeout=0.4):
            payload = json.loads(await comm.receive_from())
            if payload.get('type') == 'score':
                if counter == 'a':
                    got_a += 1
                else:
                    got_b += 1

    await a.disconnect()
    await b.disconnect()
    return {'room': code, 'connected': True, 'got_a': got_a, 'got_b': got_b}


def setup_rooms(rooms):
    u"""Наборы дуэли для дыма. Создаём и потом сносим: консьюмер обязан
    видеть настоящий GameSet, иначе он честно никого не пустит."""
    from game.models import GameSet
    GameSet.objects.filter(code__startswith='SMOKE').delete()
    GameSet.objects.bulk_create([
        GameSet(code='SMOKE%03d' % i, mode='blitz', kind='duel',
                title='дым', question_ids=[])
        for i in range(rooms)])


def teardown_rooms(rooms):
    u"""Убираем за собой и наборы, и записи комнат в кэше."""
    from django.core.cache import cache
    from game.models import GameSet
    GameSet.objects.filter(code__startswith='SMOKE').delete()
    for i in range(rooms):
        cache.delete(run_state.duel_key('SMOKE%03d' % i))


async def main(rooms, messages):
    app = URLRouter(routing.websocket_urlpatterns)
    started = time.time()
    results = await asyncio.gather(
        *[one_room(app, i, messages) for i in range(rooms)])
    spent = time.time() - started

    bad = [r for r in results if not r['connected']
           or r['got_a'] != messages or r['got_b'] != messages]
    total = sum(r['got_a'] + r['got_b'] for r in results)
    expect = rooms * messages * 2

    print(u'комнат: %d, клиентов: %d, сообщений каждому: %d'
          % (rooms, rooms * 2, messages))
    print(u'доставлено: %d из %d' % (total, expect))
    print(u'время: %.1f с' % spent)
    if bad:
        print(u'ПОТЕРИ в %d комнатах:' % len(bad))
        for r in bad[:10]:
            print(u'  %s: подключены=%s, получено %d/%d'
                  % (r['room'], r['connected'], r['got_a'], r['got_b']))
        return 1
    print(u'Ни одного потерянного score.')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--rooms', type=int, default=20)
    ap.add_argument('--messages', type=int, default=10)
    args = ap.parse_args()
    setup_rooms(args.rooms)
    try:
        code = asyncio.run(main(args.rooms, args.messages))
    finally:
        teardown_rooms(args.rooms)
    sys.exit(code)
