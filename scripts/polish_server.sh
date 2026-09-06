#!/usr/bin/env bash
# Перезапуск локального сервера для проб сессии «Полировка к бете».
#
# ⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ СКРИПТ, А НЕ pkill. На Windows `pkill -f runserver`
# процесс не снимает, и старый сервер продолжает слушать порт ВМЕСТЕ с
# новым: запросы уходят то в один, то в другой. Один раз это уже стоило
# получаса — снимки карты тем показывали семь старых разделов, потому что
# отвечал процесс, поднятый до пересборки JSON (вьюха читает файл один раз
# на процесс и держит в памяти).
#
# Запуск: bash scripts/polish_server.sh [порт]
set -u
PORT="${1:-8901}"

for pid in $(netstat -ano 2>/dev/null | grep ":${PORT}.*LISTENING" | awk '{print $NF}' | sort -u); do
  taskkill //PID "$pid" //F >/dev/null 2>&1
done
sleep 2

left=$(netstat -ano 2>/dev/null | grep -c ":${PORT}.*LISTENING")
if [ "$left" -ne 0 ]; then
  echo "ОСТАНОВ: порт ${PORT} всё ещё занят ($left процессов)"
  exit 1
fi

(venv313/Scripts/python.exe manage.py runserver "$PORT" --noreload > "/tmp/srv${PORT}.log" 2>&1 &)
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/" || true)
  [ "$code" = "200" ] && break
  sleep 1
done

count=$(netstat -ano 2>/dev/null | grep ":${PORT}.*LISTENING" | awk '{print $NF}' | sort -u | wc -l)
echo "порт ${PORT}: ответ ${code}, слушающих процессов ${count}"
[ "$count" = "1" ] || { echo "ОСТАНОВ: процессов должно быть ровно один"; exit 1; }
