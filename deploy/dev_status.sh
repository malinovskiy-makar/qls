#!/bin/bash
# Что сейчас на площадке dev.weconomics.ai. Только читает, ничего не меняет.
#
#     /srv/weconomics/dev/app/deploy/dev_status.sh
#
# Отвечает на один вопрос: «площадка показывает свежий main или отстала?»
# Сравниваются ТРИ вещи, и расхождение между ними — это диагноз:
#
#   контейнер == origin/main            всё хорошо;
#   клон == origin/main, контейнер нет  слияние прошло, сборка упала —
#                                       смотреть хвост журнала ниже;
#   клон != origin/main                 автовыкатка не отработала — жив ли
#                                       таймер (последняя строка вывода).
set -euo pipefail

DEV_DIR=/srv/weconomics/dev
APP_DIR="${DEV_DIR}/app"
COMPOSE_FILE=deploy/docker-compose.dev-site.yml
LOG="${DEV_DIR}/autodeploy.log"
FAILED_MARK="${DEV_DIR}/autodeploy.failed"

cd "$APP_DIR"

# ⚠️ Хеш берётся ИЗ ОКРУЖЕНИЯ КОНТЕЙНЕРА, а не из клона: нас интересует код,
# который РАБОТАЕТ, а не тот, что лежит на диске.
DEPLOYED=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    weco-web-dev 2>/dev/null | sed -n 's/^GIT_SHA=//p' | head -1 || true)

git fetch --quiet origin main 2>/dev/null || echo "(git fetch не прошёл — числа ниже могут быть несвежими)"

echo "─── версии ───────────────────────────────────────────────"
printf '  в контейнере web-dev : %s\n' "${DEPLOYED:-контейнера нет}"
printf '  в клоне (HEAD)       : %s\n' "$(git rev-parse --short=7 HEAD)"
printf '  origin/main          : %s\n' "$(git rev-parse --short=7 origin/main)"

if [ -f "$FAILED_MARK" ]; then
    printf '\n  ⚠️  запрет на коммит %s (последняя выкатка упала).\n' "$(cat "$FAILED_MARK")"
    printf '      Снять и попробовать снова: rm %s\n' "$FAILED_MARK"
fi

echo
echo "─── службы площадки ──────────────────────────────────────"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "─── журнал выкаток (последние 5) ─────────────────────────"
# Журнал пишется ТОЛЬКО при выкатке и при отказе: «всё свежее» раз в пять
# минут утопило бы настоящие записи.
if [ -f "$LOG" ]; then
    tail -5 "$LOG"
else
    echo "  журнала ещё нет — ни одной выкатки не было"
fi

echo
echo "─── таймер ───────────────────────────────────────────────"
systemctl list-timers weconomics-dev-autodeploy.timer --no-pager || true
