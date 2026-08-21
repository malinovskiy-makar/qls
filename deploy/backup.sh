#!/bin/sh
# Резервная копия боевой базы weconomics.site.
#
# Запускается таймером systemd раз в сутки (deploy/systemd/), а также руками:
#     sudo /srv/weconomics/app/deploy/backup.sh
#
# ⚠️ БЭКАП, КОТОРЫЙ НИ РАЗУ НЕ ВОССТАНАВЛИВАЛИ, БЭКАПОМ НЕ ЯВЛЯЕТСЯ.
# Порядок проверки восстановления — docs/SERVER.md, раздел «Бэкапы».
#
# ⚠️ ИМЕНА ПЕРЕМЕННЫХ ЛАТИНИЦЕЙ, В ОТЛИЧИЕ ОТ КОДА НА ПИТОНЕ В ЭТОМ ПРОЕКТЕ.
# Оболочка допускает в именах только [A-Za-z0-9_]: кириллическое имя она не
# считает именем вовсе и падает с syntax error. Комментарии — по-русски.
set -eu

PROJECT_DIR=/srv/weconomics
BACKUP_DIR="${PROJECT_DIR}/backups"
ENV_FILE="${PROJECT_DIR}/.env"
COMPOSE_DIR="${PROJECT_DIR}/app/deploy"
KEEP=30

# ⚠️ ФАЙЛ .env НЕ ВЫПОЛНЯЕТСЯ ОБОЛОЧКОЙ, И ЭТО ВАЖНО.
# Через `. .env` оболочка ИСПОЛНЯЕТ файл: значение вида a(b)c — уже синтаксис,
# и скрипт падает с «word unexpected». Ровно так он и упал при первом прогоне
# на ключе SECRET_KEY. Ключ с тех пор перевыпущен только буквами и цифрами,
# но полагаться на это нельзя: следующий пароль напишет другой человек.
# Читаем нужные три значения текстом, ничего не исполняя.
read_env() {
    sed -n "s/^$1=//p" "${ENV_FILE}" | head -n 1
}

POSTGRES_USER="$(read_env POSTGRES_USER)"
POSTGRES_DB="$(read_env POSTGRES_DB)"
BACKUP_S3_ENDPOINT="$(read_env BACKUP_S3_ENDPOINT)"
BACKUP_S3_BUCKET="$(read_env BACKUP_S3_BUCKET)"
BACKUP_S3_ACCESS_KEY="$(read_env BACKUP_S3_ACCESS_KEY)"
BACKUP_S3_SECRET_KEY="$(read_env BACKUP_S3_SECRET_KEY)"

if [ -z "${POSTGRES_USER}" ] || [ -z "${POSTGRES_DB}" ]; then
    echo "[backup] ОШИБКА: в ${ENV_FILE} нет POSTGRES_USER или POSTGRES_DB" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="weconomics-${STAMP}.dump.gz"
PATH_OUT="${BACKUP_DIR}/${NAME}"

# ⚠️ cd, А НЕ --project-directory. Флаг --project-directory задаёт рабочий
# каталог, но НЕ говорит compose, где искать сам файл описания: без -f он
# всё равно ищет его в текущем каталоге, не находит и падает.
cd "${COMPOSE_DIR}"

echo "[backup] снимаю дамп → ${NAME}"

# ⚠️ -Z0 ВЫКЛЮЧАЕТ ВСТРОЕННОЕ СЖАТИЕ pg_dump, И ЭТО НАМЕРЕННО.
# Формат -Fc сжимает сам. Без -Z0 файл сжимался бы дважды: gzip поверх уже
# сжатого не даёт почти ничего, зато тратит время на каждом ночном прогоне.
# Сжатие одно, зато настоящее (-9).
#
# Через `exec -T`, а не через порт: порт базы наружу не опубликован
# намеренно (см. комментарий в docker-compose.yml).
docker compose exec -T postgres \
    pg_dump -Fc -Z0 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    | gzip -9 > "${PATH_OUT}.part"

mv "${PATH_OUT}.part" "${PATH_OUT}"
chmod 600 "${PATH_OUT}"

SIZE="$(du -h "${PATH_OUT}" | cut -f1)"
echo "[backup] готово: ${NAME} (${SIZE})"

# ⚠️ ПРОВЕРКА ЦЕЛОСТНОСТИ ЗДЕСЬ ЖЕ. Дамп, который не читается, обнаруживают
# в тот день, когда он нужен. Читаем оглавление архива: это дёшево и ловит
# обрыв записи, переполнение диска и битый gzip.
if ! gunzip -c "${PATH_OUT}" | docker compose exec -T postgres \
        pg_restore --list > /dev/null 2>&1; then
    echo "[backup] ОШИБКА: дамп не читается, удаляю ${NAME}" >&2
    rm -f "${PATH_OUT}"
    exit 1
fi
echo "[backup] оглавление дампа читается"

# --- Копия у другого провайдера ---
#
# ⚠️ ПРАВИЛО ПРОЕКТА: БЭКАП ЖИВЁТ НЕ У ТОГО ЖЕ ПРОВАЙДЕРА, ЧТО СЕРВЕР.
# Копии рядом с сервером спасают от «уронили таблицу» и не спасают ровно от
# того, ради чего бэкап и делают: провайдер потерял диск, заблокировал
# аккаунт, сервер изъяли. Пока переменные BACKUP_S3_* пусты, правило НЕ
# выполнено, и скрипт говорит об этом вслух на каждом прогоне.
#
# aws-cli не установлен в систему намеренно: он нужен только когда хранилище
# подключат, и тогда приедет контейнером.
if [ -n "${BACKUP_S3_ENDPOINT:-}" ] && [ -n "${BACKUP_S3_BUCKET:-}" ] \
   && [ -n "${BACKUP_S3_ACCESS_KEY:-}" ] && [ -n "${BACKUP_S3_SECRET_KEY:-}" ]; then
    echo "[backup] отправляю во внешнее хранилище…"
    docker run --rm \
        -e AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
        -e AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
        -v "${BACKUP_DIR}:/backups:ro" \
        amazon/aws-cli:latest \
        s3 cp "/backups/${NAME}" "s3://${BACKUP_S3_BUCKET}/${NAME}" \
        --endpoint-url "${BACKUP_S3_ENDPOINT}"
    echo "[backup] отправлено во внешнее хранилище"
else
    echo "[backup] ⚠️ ВНЕШНЕЕ ХРАНИЛИЩЕ НЕ НАСТРОЕНО: копии лежат только" \
         "на этом же сервере. Заполните BACKUP_S3_* в ${ENV_FILE}."
fi

# --- Ротация ---
# Считаем и удаляем по ИМЕНИ (оно содержит дату), а не по времени файла:
# время правится копированием, имя — нет.
TOTAL="$(ls -1 "${BACKUP_DIR}"/weconomics-*.dump.gz 2>/dev/null | wc -l)"
if [ "${TOTAL}" -gt "${KEEP}" ]; then
    EXTRA=$((TOTAL - KEEP))
    echo "[backup] копий ${TOTAL}, храним ${KEEP} — удаляю ${EXTRA} старейших"
    ls -1 "${BACKUP_DIR}"/weconomics-*.dump.gz | sort | head -n "${EXTRA}" \
        | while read -r OLD; do
            echo "[backup]   удаляю $(basename "${OLD}")"
            rm -f "${OLD}"
        done
fi

echo "[backup] копий на диске: $(ls -1 "${BACKUP_DIR}"/weconomics-*.dump.gz | wc -l)"
