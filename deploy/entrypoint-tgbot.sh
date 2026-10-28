#!/bin/sh
# Порядок старта контейнера tgbot (бот стены ВП: длинный опрос Telegram).
#
# ⚠️ ЗДЕСЬ НЕТ `migrate` И НЕ БУДЕТ. Миграции накатывает ровно один процесс –
# web, и без всякой блокировки. Два процесса, пошедшие мигрировать
# одновременно, развалят схему; это записанный запрет P0 проекта. Здесь
# только ожидание служб и запуск `manage.py tg_poll`.
#
# ⚠️ `collectstatic` тоже не зовём: бот статику не отдаёт.
#
# ⚠️ ЭКЗЕМПЛЯР ОДИН. Второй опрос получит от Telegram 409 и остановится; вдвоём они
# отнимали бы друг у друга сообщения. Масштабировать эту службу нельзя и незачем.
set -e

# Метка жизни прошлого запуска не должна выдавать за живой остановившийся процесс.
rm -f /tmp/tg_poll_alive

echo "[tgbot] ждём PostgreSQL и Redis…"

python - <<'PY'
import os
import sys
import time

import dj_database_url
import psycopg
import redis

ПРЕДЕЛ = int(os.environ.get('WAIT_FOR_SERVICES_TIMEOUT', '60'))
край = time.time() + ПРЕДЕЛ


def ждать(имя, проверка):
    последняя = None
    while time.time() < край:
        try:
            проверка()
            print('[tgbot] %s готов' % имя, flush=True)
            return
        except Exception as exc:            # noqa: BLE001 — ждём любую беду
            последняя = exc
            time.sleep(1)
    print('[tgbot] %s не поднялся за %d с: %s' % (имя, ПРЕДЕЛ, последняя),
          file=sys.stderr)
    sys.exit(1)


def проверить_базу():
    cfg = dj_database_url.parse(os.environ['DATABASE_URL'])
    with psycopg.connect(
            host=cfg['HOST'], port=cfg['PORT'], dbname=cfg['NAME'],
            user=cfg['USER'], password=cfg['PASSWORD'], connect_timeout=3):
        pass


def проверить_redis():
    redis.Redis.from_url(os.environ['REDIS_URL'] + '/0',
                         socket_connect_timeout=3).ping()


ждать('PostgreSQL', проверить_базу)
ждать('Redis', проверить_redis)
PY

echo "[tgbot] опрос Telegram…"
exec python manage.py tg_poll
