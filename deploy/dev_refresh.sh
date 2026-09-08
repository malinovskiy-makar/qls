#!/bin/bash
# Обновить данные площадки dev.weconomics.ai из свежего боевого дампа.
#
# Запускает ВЛАДЕЛЕЦ руками, когда данные площадки устарели:
#     /srv/weconomics/dev/app/deploy/dev_refresh.sh          # только план
#     /srv/weconomics/dev/app/deploy/dev_refresh.sh --yes    # выполнить
#
# ⚠️ ЭТО ДОЛГАЯ ОПЕРАЦИЯ — ЗАПУСКАТЬ В tmux. Обрыв SSH посреди pg_restore
# оставит базу площадки наполовину восстановленной.
#     tmux new -s refresh
#
# Что делает по шагам:
#   1. берёт САМЫЙ СВЕЖИЙ боевой дамп из /srv/weconomics/backups;
#   2. гасит web-dev и ws-dev (нельзя удалять базу под работающим Django);
#   3. пересоздаёт базу площадки (имя берётся из её .env и обязано
#      оканчиваться на _dev) — БОЕВУЮ НЕ ТРОГАЕТ;
#   4. заливает дамп;
#   5. поднимает web-dev — его entrypoint накатывает миграции (у площадки
#      они могут быть новее боевых: код с main, данные с боя);
#   6. `manage.py dev_scrub --yes` — вычищает всех людей, заводит четыре
#      тестовых аккаунта (ученик, учитель, родитель, админ) со связями;
#   7. `manage.py fix_sequences --apply` — счётчики после заливки с явными id;
#   8. печатает числа.
#
# ⚠️ ПОЧЕМУ dev_scrub, А НЕ «ВОССТАНОВИТЬ ТОЛЬКО НУЖНЫЕ ТАБЛИЦЫ». Выборочное
# восстановление означало бы список таблиц, который надо править при каждой
# новой модели, — и однажды он молча отстанет, а персональные данные приедут
# на площадку с общим паролем. Заливаем всё и вычищаем людей кодом, у которого
# есть тесты и предохранитель.
set -euo pipefail

DEV_DIR=/srv/weconomics/dev
APP_DIR="${DEV_DIR}/app"
COMPOSE_FILE=deploy/docker-compose.dev-site.yml
PROD_COMPOSE_DIR=/srv/weconomics/app/deploy
PROD_ENV=/srv/weconomics/.env
BACKUP_DIR=/srv/weconomics/backups

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

# ── Что возьмём ──────────────────────────────────────────────────────────────
# ⚠️ Каталог копий закрыт от makar (700, владелец root), поэтому шаблон `*`
# раскрывается ВНУТРИ sudo-оболочки, а не снаружи: снаружи он не видит
# каталога и не раскрывается вовсе (ловушка записана в docs/SERVER.md).
LAST=$(sudo sh -c "ls -1t ${BACKUP_DIR}/*.dump.gz | head -1")
[ -n "$LAST" ] || { echo "В ${BACKUP_DIR} нет ни одного дампа." >&2; exit 1; }

PGUSER=$(sudo sed -n 's/^POSTGRES_USER=//p' "$PROD_ENV" | head -1)
PGDB=$(sudo sed -n 's/^POSTGRES_DB=//p' "$PROD_ENV" | head -1)
[ -n "$PGUSER" ] && [ -n "$PGDB" ] || { echo "Не прочитались POSTGRES_* из ${PROD_ENV}." >&2; exit 1; }

echo "Дамп:            $LAST ($(sudo stat -c %y "$LAST" | cut -d. -f1))"
echo "Размер:          $(sudo du -h "$LAST" | cut -f1)"
echo "База площадки:   ${DEV_DB_NAME}  ← будет УДАЛЕНА И СОЗДАНА ЗАНОВО"
echo "Боевая база:     ${PGDB}    ← НЕ ТРОГАЕТСЯ (только читается имя пользователя)"
echo "После заливки:   dev_scrub --yes (все люди удаляются, заводятся четыре"
echo "                 аккаунта: dev-student, dev-teacher, dev-parent, dev-admin),"
echo "                 затем fix_sequences --apply"

# ── Стоп-гейт ────────────────────────────────────────────────────────────────
if [ "${1:-}" != "--yes" ]; then
    echo
    echo "Это ПЛАН, ничего не сделано. Выполнить: $0 --yes"
    exit 0
fi

echo
echo "── 1/6 гасим службы площадки ──"
docker compose -f "$COMPOSE_FILE" stop web-dev ws-dev

echo "── 2/6 пересоздаём базу ${DEV_DB_NAME} ──"
cd "$PROD_COMPOSE_DIR"
# ⚠️ Подключаемся к БОЕВОЙ базе только как к «точке входа» psql: удалить базу,
# сидя в ней самой, нельзя. Ни одной команды, меняющей боевые данные, здесь нет.
docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" \
    -c "DROP DATABASE IF EXISTS ${DEV_DB_NAME};"
docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" \
    -c "CREATE DATABASE ${DEV_DB_NAME} OWNER ${PGUSER};"

echo "── 3/6 заливаем дамп (это долго) ──"
# --no-owner/--no-privileges: владелец и права в дампе боевые, а на площадке
# они не нужны и только сыпали бы ошибками.
sudo gunzip -c "$LAST" | docker compose exec -T postgres \
    pg_restore -U "$PGUSER" -d "$DEV_DB_NAME" --no-owner --no-privileges

echo "── 4/6 поднимаем web-dev (entrypoint накатит миграции) ──"
cd "$APP_DIR"
docker compose -f "$COMPOSE_FILE" up -d web-dev
WAITED=0
while [ "$WAITED" -lt 300 ]; do
    STATE=$(docker inspect --format '{{.State.Health.Status}}' weco-web-dev 2>/dev/null || echo unknown)
    [ "$STATE" = "healthy" ] && break
    sleep 5
    WAITED=$((WAITED + 5))
done
[ "${STATE:-unknown}" = "healthy" ] || {
    echo "web-dev не стал healthy за 300 с (состояние: ${STATE:-unknown})." >&2
    docker compose -f "$COMPOSE_FILE" logs --tail=40 web-dev >&2
    exit 1
}

echo "── 5/6 вычищаем людей ──"
docker compose -f "$COMPOSE_FILE" exec -T web-dev python manage.py dev_scrub --yes

echo "── 6/6 счётчики последовательностей ──"
# ⚠️ Обязательный шаг. Восстановление из дампа вставляет строки с готовыми id
# и НЕ двигает счётчики; следующая обычная вставка падает с конфликтом ключа.
# На SQLite это не воспроизводится, поэтому локально не видно.
docker compose -f "$COMPOSE_FILE" exec -T web-dev python manage.py fix_sequences --apply

echo
echo "── что получилось ──"
docker compose -f "$COMPOSE_FILE" exec -T web-dev python manage.py shell -c "
from problems.models import Problem, User
from problems.models_platform import LearningEvent
print('задач:         %d' % Problem.objects.count())
try:
    from olympiads.models import Olympiad
    print('олимпиад:      %d' % Olympiad.objects.count())
except Exception:
    print('олимпиад:      раздела нет')
print('пользователей: %d (%s)' % (
    User.objects.count(),
    ', '.join(sorted(User.objects.values_list('username', flat=True)))))
print('событий:       %d' % LearningEvent.objects.count())
"

docker compose -f "$COMPOSE_FILE" up -d ws-dev
echo
echo "Готово. Площадка на свежих данных боевого дампа, без людей."
