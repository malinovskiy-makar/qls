#!/usr/bin/env bash
# Вход для VPN, БОЕВОЙ сервер: чьему PROXY-заголовку верит nginx (README.md рядом).
#
#     sudo /srv/weconomics/app/deploy/web_relay/prod_realip.sh
#
# Читает WEB_RELAY_IP из /srv/weconomics/.env и пишет одну строку
#     set_real_ip_from <адрес>;
# в /srv/weconomics/nginx/conf.d/web_relay_realip.conf. Вторая половина realip
# (`real_ip_header proxy_protocol`) — в deploy/nginx/available/django.conf.
# Файл подхватывает `include /etc/nginx/conf.d/*.conf` в nginx.conf образа,
# отдельный include не нужен; нет файла — nginx не падает.
#
# WEB_RELAY_IP пуст — файл пишется без директив: заголовку не верит никто, и
# пришедшие через вход видны с адресом tg-relay. Это и есть откат.
#
# Дальше nginx -t и reload. nginx -t упал — прежний файл возвращается, nginx
# не перезагружается: сайт остаётся на старой конфигурации.
#
# Для тестов (config/tests/test_web_relay.py): ENV_FILE, OUT_FILE и
# NGINX_RELOAD=0 — без docker.
set -euo pipefail

ENV_FILE="${ENV_FILE:-/srv/weconomics/.env}"
OUT_FILE="${OUT_FILE:-/srv/weconomics/nginx/conf.d/web_relay_realip.conf}"
COMPOSE_DIR="${COMPOSE_DIR:-/srv/weconomics/app/deploy}"
NGINX_RELOAD="${NGINX_RELOAD:-1}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=relay_ip.sh
source "$HERE/relay_ip.sh"

RELAY_IP="$(web_relay_ip "$ENV_FILE")"

NEW="$(mktemp)"
OLD=""
cleanup() { rm -f "$NEW" ${OLD:+"$OLD"}; }
trap cleanup EXIT

{
    echo "# Создан deploy/web_relay/prod_realip.sh из WEB_RELAY_IP в .env. Руками не править:"
    echo "# правьте .env и запустите скрипт снова."
    if [[ -n "$RELAY_IP" ]]; then
        echo "set_real_ip_from $RELAY_IP;"
    else
        echo "# WEB_RELAY_IP пуст: PROXY-заголовку не верим ни от кого."
    fi
} > "$NEW"

if [[ -f "$OUT_FILE" ]]; then
    OLD="$(mktemp)"
    cat "$OUT_FILE" > "$OLD"
fi
cat "$NEW" > "$OUT_FILE"
chmod 644 "$OUT_FILE"

restore() {
    if [[ -n "$OLD" ]]; then
        cat "$OLD" > "$OUT_FILE"
    else
        rm -f "$OUT_FILE"
    fi
}

if [[ "$NGINX_RELOAD" == 1 ]]; then
    cd "$COMPOSE_DIR"
    if ! docker compose exec -T nginx nginx -t; then
        restore
        echo "ОШИБКА: nginx -t не прошёл, прежний $OUT_FILE возвращён, nginx не перезагружался." >&2
        exit 1
    fi
    docker compose exec -T nginx nginx -s reload
fi

if [[ -n "$RELAY_IP" ]]; then
    echo "ГОТОВО: nginx верит PROXY-заголовку только от $RELAY_IP ($OUT_FILE)."
else
    echo "ГОТОВО: WEB_RELAY_IP пуст — PROXY-заголовку не верим ни от кого ($OUT_FILE)."
fi
