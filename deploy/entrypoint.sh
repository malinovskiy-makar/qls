#!/bin/sh
# Порядок старта контейнера web. Любой шаг упал — контейнер не поднимается.
#
# set -e обязателен: без него упавшая миграция не остановила бы запуск, и
# gunicorn поднялся бы на несогласованной схеме. Сайт при этом «работает»,
# а разваливается на первом же запросе к изменившейся таблице.
set -e

echo "[entrypoint] ждём PostgreSQL и Redis…"

# ⚠️ НЕ `sleep 10`. Задержка наугад либо ждёт зря, либо не дожидается: на
# холодном сервере PostgreSQL поднимается дольше, и контейнер падал бы через
# раз. Проверяем НАСТОЯЩЕЕ соединение, средствами самого приложения —
# те же драйверы, те же адреса из окружения, что и у Django.
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
            print('[entrypoint] %s готов' % имя, flush=True)
            return
        except Exception as exc:            # noqa: BLE001 — ждём любую беду
            последняя = exc
            time.sleep(1)
    # Текст ошибки печатаем: без него «не дождались» невозможно разбирать.
    # Пароля в нём нет — psycopg и redis его в сообщение не кладут.
    print('[entrypoint] %s не поднялся за %d с: %s' % (имя, ПРЕДЕЛ, последняя),
          file=sys.stderr, flush=True)
    sys.exit(1)


настройки = dj_database_url.config()
if not настройки:
    print('[entrypoint] DATABASE_URL не задан', file=sys.stderr)
    sys.exit(1)


def проверить_базу():
    with psycopg.connect(
        dbname=настройки['NAME'],
        user=настройки.get('USER') or None,
        password=настройки.get('PASSWORD') or None,
        host=настройки.get('HOST') or None,
        port=настройки.get('PORT') or None,
        connect_timeout=3,
    ) as соединение:
        соединение.execute('SELECT 1')


адрес = os.environ.get('REDIS_URL', '').strip()
if not адрес:
    print('[entrypoint] REDIS_URL не задан', file=sys.stderr)
    sys.exit(1)


def проверить_redis():
    redis.Redis.from_url(адрес + '/0', socket_connect_timeout=3).ping()


ждать('PostgreSQL', проверить_базу)
ждать('Redis', проверить_redis)
PY

# ⚠️ КОНТЕЙНЕР web РОВНО ОДИН, поэтому гонки миграций нет и блокировка не
# нужна. Если когда-нибудь поднимут второй — два процесса пойдут накатывать
# миграции одновременно. Django этого не переживёт. Запрет и причина
# записаны в docs/SERVER.md; не поднимайте второй web без чтения этого места.
echo "[entrypoint] миграции…"
python manage.py migrate --noinput

# ⚠️ ИМЕННО ЗДЕСЬ, А НЕ НА ЭТАПЕ СБОРКИ ОБРАЗА. Статика лежит в именованном
# томе, который монтируется при запуске и перекрывает каталог из образа:
# собранная при сборке статика оказалась бы не видна, и сайт поехал бы без
# единого стиля. Ловушка стоила бы вечера разбора «почему всё голое».
echo "[entrypoint] статика…"
python manage.py collectstatic --noinput

echo "[entrypoint] gunicorn…"
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-4}" \
    --timeout 60 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
