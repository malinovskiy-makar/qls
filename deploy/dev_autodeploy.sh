#!/bin/bash
# Автовыкатка площадки dev.weconomics.ai: подтянуть main, если CI по нему зелёный.
#
# Запускается таймером systemd раз в 5 минут (deploy/systemd/), а также руками:
#     /srv/weconomics/dev/app/deploy/dev_autodeploy.sh
#
# ⚠️ ЭТО PULL, А НЕ PUSH, И ЭТО РЕШЕНИЕ, А НЕ УДОБСТВО. Выкатка из GitHub
# Actions потребовала бы дать GitHub ключ на ЗАПИСЬ к серверу; здесь сервер
# сам ходит наружу, а ключ деплоя остаётся только на чтение. Взломанный
# GitHub-аккаунт при такой схеме не даёт доступа к серверу.
#
# ⚠️ БОЙ ЭТОТ СКРИПТ НЕ ТРОГАЕТ НИ ОДНОЙ КОМАНДОЙ. Он работает только в
# /srv/weconomics/dev/app и только с compose-проектом weconomics-dev.
#
# ⚠️ ИМЕНА ПЕРЕМЕННЫХ ЛАТИНИЦЕЙ (как в deploy/backup.sh): оболочка допускает
# в именах только [A-Za-z0-9_]. Комментарии — по-русски.
set -euo pipefail

DEV_DIR=/srv/weconomics/dev
APP_DIR="${DEV_DIR}/app"
COMPOSE_FILE=deploy/docker-compose.dev-site.yml
LOG="${DEV_DIR}/autodeploy.log"
# ⚠️ Метка последней неудачи. Без неё сломанный main пересобирался бы каждые
# пять минут круглосуточно: сборка занимает минуты и ест CPU того же сервера,
# на котором живёт бой. С меткой один и тот же плохой коммит пробуется один
# раз, а следующий коммит пробуется снова. Снять запрет вручную:
#     rm /srv/weconomics/dev/autodeploy.failed
FAILED_MARK="${DEV_DIR}/autodeploy.failed"
REPO=malinovskiy-makar/qls
CONTAINER=weco-web-dev
HEALTH_TIMEOUT=180

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

# Строка в журнал плюс та же строка в вывод: вывод подхватывает journald,
# и `journalctl -u weconomics-dev-autodeploy` показывает то же самое.
fail() {
    log "$1 FAIL $2"
    echo "FAIL: $2" >&2
    # Хвост логов контейнера — чтобы причина была видна там же, где отказ,
    # а не искалась отдельной командой через сутки.
    docker compose -f "$COMPOSE_FILE" logs --tail=30 web-dev 2>&1 \
        | sed 's/^/    /' >> "$LOG" || true
    echo "$1" > "$FAILED_MARK"
    exit 1
}

cd "$APP_DIR"

# ── ПРЕДОХРАНИТЕЛЬ: работаем только с базой площадки ─────────────────────────
#
# ⚠️ ЭТА ПРОВЕРКА СТОИТ ПЕРЕД ВСЕМ ОСТАЛЬНЫМ И ВЫХОДИТ НЕМЕДЛЕННО.
# Скрипт задуман для дев-клона, но лежит в репозитории — значит его точная
# копия есть и в БОЕВОМ клоне /srv/weconomics/app/deploy/. Запусти его оттуда
# (или из дев-клона, но с испорченным .env) — и он начал бы пересобирать и
# перезапускать службы на БОЕВОЙ базе. Одна ошибочная строка в подсказке
# командной строки, одна привычка «сделать то же, но здесь».
#
# Имя базы — последний кусок DATABASE_URL после «/». Оно обязано оканчиваться
# на `_dev`. Боевая база называется `weconomics`, площадка — `weconomics_dev`:
# проверка отличает их надёжно и не требует знать имя заранее.
DEV_ENV=/srv/weconomics/dev/.env
[ -f "$DEV_ENV" ] || { echo "Нет ${DEV_ENV} — это не сервер площадки." >&2; exit 1; }

# Читаем ТЕКСТОМ, а не через `. .env`: исполнение файла с паролями означало бы,
# что значение вида a(b)c роняет скрипт синтаксической ошибкой (эта ловушка
# уже стоила проекта одного упавшего бэкапа — docs/SERVER.md).
DEV_DB_NAME=$(sed -n 's/^DATABASE_URL=//p' "$DEV_ENV" | head -1 | sed 's/?.*//; s#.*/##')
case "$DEV_DB_NAME" in
    *_dev) : ;;
    '')    echo "В ${DEV_ENV} не найден DATABASE_URL." >&2; exit 1 ;;
    *)     echo "ОТКАЗ: база в DATABASE_URL называется «${DEV_DB_NAME}», а не *_dev." >&2
           echo "Похоже, это боевая база. Скрипт площадки её не трогает." >&2
           exit 1 ;;
esac

# ── Что уже выкачено ─────────────────────────────────────────────────────────
# ⚠️ СПРАШИВАЕМ КОНТЕЙНЕР, А НЕ КЛОН, И ЭТО ВАЖНО. HEAD клона говорит лишь
# «какой код лежит на диске», а нас интересует «какой код РАБОТАЕТ». Они
# расходятся ровно в интересном случае: слияние прошло, сборка упала, старые
# контейнеры продолжают работать. Сравнивай мы HEAD с origin/main — скрипт
# сказал бы «всё свежее» и площадка молча осталась бы на старом коде навсегда.
DEPLOYED=$(docker inspect --format \
    '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" 2>/dev/null \
    | sed -n 's/^GIT_SHA=//p' | head -1 || true)

git fetch --quiet origin main
TARGET=$(git rev-parse --short=7 origin/main)

if [ "$DEPLOYED" = "$TARGET" ]; then
    # ⚠️ В ЖУРНАЛ ЭТО НЕ ПИШЕТСЯ НАМЕРЕННО. Раз в пять минут — это 288 строк
    # в сутки; за неделю они утопили бы десяток настоящих записей о выкатках,
    # ради которых журнал и заведён. Кто хочет видеть каждый тик — смотрит
    # journalctl -u weconomics-dev-autodeploy.
    echo "up to date: $TARGET"
    exit 0
fi

if [ -f "$FAILED_MARK" ] && [ "$(cat "$FAILED_MARK")" = "$TARGET" ]; then
    echo "коммит $TARGET уже падал, жду следующий (снять: rm $FAILED_MARK)"
    exit 0
fi

# ── Зелёный ли CI по этому коммиту ───────────────────────────────────────────
# ⚠️ БЕЗ ТОКЕНА. Репозиторий публичный (проверено 07.09.2026:
# api.github.com/repos/… отдаёт "private": false), а безымянному запросу
# GitHub даёт 60 обращений в час на адрес — при опросе раз в пять минут это
# 12. Токен здесь означал бы ещё один секрет на сервере ради ничего.
FULL=$(git rev-parse origin/main)
API="https://api.github.com/repos/${REPO}/actions/runs?head_sha=${FULL}&per_page=5"

if ! ANSWER=$(curl -fsS --max-time 20 -H 'Accept: application/vnd.github+json' "$API"); then
    # Сеть моргнула или GitHub недоступен — это не повод считать коммит
    # плохим. Выходим молча, следующий тик через пять минут попробует снова.
    echo "GitHub недоступен, пробую в следующий раз"
    exit 0
fi

# ⚠️ РАЗБОР ПИТОНОМ, А НЕ jq: jq на сервере не установлен и обещать его
# наличие в скрипте автовыкатки — значит однажды получить отказ в 3 часа ночи.
# python3 в Ubuntu 24.04 есть всегда.
VERDICT=$(printf '%s' "$ANSWER" | python3 -c "
import json, sys
данные = json.load(sys.stdin)
прогоны = [r for r in данные.get('workflow_runs', []) if r.get('name') == 'CI']
if not прогоны:
    print('none'); raise SystemExit
завершённые = [r for r in прогоны if r.get('status') == 'completed']
if not завершённые:
    print('pending'); raise SystemExit
if any(r.get('conclusion') == 'success' for r in завершённые):
    print('success')
else:
    print('bad:' + ','.join(str(r.get('conclusion')) for r in завершённые))
")

case "$VERDICT" in
    success) : ;;
    none|pending)
        # CI ещё идёт или прогон не появился. Не ошибка: слияние только что
        # произошло, проверки занимают около получаса.
        echo "жду CI по $TARGET ($VERDICT)"
        exit 0
        ;;
    *)
        log "$TARGET FAIL CI не зелёный ($VERDICT) — на площадку не выкачено"
        echo "CI не зелёный по $TARGET: $VERDICT" >&2
        # ⚠️ Метку НЕ ставим: красный CI — это про код, а не про сборку.
        # Починят и запушат — придёт новый коммит с новым хешем.
        exit 1
        ;;
esac

# ── Выкатка ──────────────────────────────────────────────────────────────────
# --ff-only: если у клона появились свои коммиты (их там быть не должно —
# площадка только читает), слияние честно откажется вместо создания мержа.
git merge --ff-only origin/main --quiet \
    || fail "$TARGET" "git merge --ff-only отказал: в клоне свои коммиты?"

# ── ПРЕДОХРАНИТЕЛЬ: не начинать сборку на исходе памяти ──────────────────────
#
# ⚠️ СБОРКА ОБРАЗА — САМЫЙ ПРОЖОРЛИВЫЙ МОМЕНТ ЖИЗНИ ПЛОЩАДКИ. `pip wheel`
# компилирует зависимости и легко берёт сотни мегабайт сверх обычного. Идёт
# она на том же сервере с 8 ГБ, где живёт бой с моделью поиска на 2,12 ГБ.
# Начни мы сборку на исходе памяти — OOM-killer ядра выбрал бы жертву сам, и
# выбрал бы самый крупный процесс, то есть боевой `search` или боевой `web`.
# Пределы mem_limit в compose тут не спасают: они ограничивают РАБОТАЮЩИЕ
# контейнеры площадки, а сборка идёт в демоне docker, вне их.
# Лучше опоздать с выкаткой на пять минут, чем уронить настоящий сайт.
AVAILABLE=$(free -m | awk '/^Mem:/ {print $7}')
if [ -n "$AVAILABLE" ] && [ "$AVAILABLE" -lt 600 ]; then
    log "$TARGET SKIP: мало памяти (${AVAILABLE} МБ available, нужно 600)"
    echo "SKIP: мало памяти (${AVAILABLE} МБ available)" >&2
    # Метку неудачи НЕ ставим: коммит ни при чём, память освободится сама.
    exit 0
fi

# ⚠️ Сборка НЕ ТРОГАЕТ работающие контейнеры. Упади она — площадка
# продолжает отвечать старым кодом, и это и есть защита: сломанный main не
# гасит площадку, он просто на неё не приезжает.
docker compose -f "$COMPOSE_FILE" build --build-arg "GIT_SHA=${TARGET}" web-dev \
    >/dev/null 2>&1 || fail "$TARGET" "сборка образа упала"

docker compose -f "$COMPOSE_FILE" up -d web-dev ws-dev \
    >/dev/null 2>&1 || fail "$TARGET" "docker compose up -d не поднял службы"

# ── Ждём, пока web-dev станет healthy ────────────────────────────────────────
# Первый старт после правки схемы включает миграции, поэтому предел щедрый.
WAITED=0
while [ "$WAITED" -lt "$HEALTH_TIMEOUT" ]; do
    STATE=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo unknown)
    [ "$STATE" = "healthy" ] && break
    sleep 5
    WAITED=$((WAITED + 5))
done

[ "${STATE:-unknown}" = "healthy" ] \
    || fail "$TARGET" "web-dev не стал healthy за ${HEALTH_TIMEOUT} с (состояние: ${STATE:-unknown})"

rm -f "$FAILED_MARK"
log "$TARGET ok"
echo "выкачено: $TARGET"
