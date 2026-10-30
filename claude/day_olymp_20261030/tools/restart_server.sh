#!/bin/sh
# Перезапуск сервера площадки дня на 8097 (подставной поставщик ИИ, как ночью).
cd "$(dirname "$0")/../../.." || exit 1
PID=$(lsof -ti tcp:8097 -sTCP:LISTEN)
[ -n "$PID" ] && kill $PID && sleep 1
NIGHT_AI_PROVIDER=fake QLS_FAKE_REPLY="$(cat claude/night_olymp_20261030/tools/fake_reply_59997.json)" \
  nohup ./venv313/bin/python manage.py runserver 8097 --settings=config.settings_olympiads_screens --noreload \
  >> claude/day_olymp_20261030/logs/server.log 2>&1 &
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -s -o /dev/null http://127.0.0.1:8097/olympiads/ && echo "сервер 8097 поднят" && exit 0
  sleep 1
done
echo "сервер не поднялся"; exit 1
