#!/usr/bin/env bash
# Вход для VPN на машине tg-relay — откат setup.sh. README.md рядом.
#
#     sudo bash rollback.sh
#
# Убирает stream-конфиг и его include, возвращает отключённые сайты nginx и
# продление сертификата tg.weconomics.ai из /root/web_relay_backup/, удаляет
# правила ufw для 80/443 — только те, что добавил setup.sh. nginx
# перезапускается, если работал до setup.sh, иначе останавливается.
#
# Туннель бота (tg-tunnel) не трогается; его состояние печатается до и после.
set -euo pipefail

BACKUP_DIR=/root/web_relay_backup
STATE="$BACKUP_DIR/state"
STREAM_CONF=/etc/nginx/web_relay_stream.conf
NGINX_CONF=/etc/nginx/nginx.conf

[[ $EUID -eq 0 ]] || { echo "СТОП: запускать от root: sudo bash rollback.sh" >&2; exit 1; }
[[ -f "$STATE" ]] || { echo "СТОП: нет $STATE — setup.sh здесь не запускался, откатывать нечего." >&2; exit 1; }

was() { grep -qx "$1=yes" "$STATE"; }

TUNNEL_BEFORE="$(systemctl is-active tg-tunnel 2>/dev/null || true)"
echo "== Туннель бота (tg-tunnel) до отката: ${TUNNEL_BEFORE:-неизвестно}"

echo "== Убираю stream-конфиг входа"
rm -f "$STREAM_CONF"
if [[ -f "$NGINX_CONF" ]]; then
    sed -i "\#web_relay_stream.conf#d" "$NGINX_CONF"
fi

for saved in "$BACKUP_DIR"/sites-enabled.*; do
    [[ -e "$saved" || -L "$saved" ]] || continue
    name="${saved##*/sites-enabled.}"
    mv "$saved" "/etc/nginx/sites-enabled/$name"
    echo "== Вернул сайт nginx $name"
done
for saved in "$BACKUP_DIR"/renewal.*.conf; do
    [[ -e "$saved" ]] || continue
    name="${saved##*/renewal.}"
    mv "$saved" "/etc/letsencrypt/renewal/$name"
    echo "== Вернул продление сертификата ${name%.conf}"
done

if was NGINX_WAS_ACTIVE; then
    echo "== nginx работал до setup.sh — проверяю конфигурацию и перезапускаю"
    if ! nginx -t; then
        echo "ОШИБКА: прежняя конфигурация nginx не проходит nginx -t — nginx не перезапускался." >&2
        echo "        Файлы уже возвращены; копия состояния — $BACKUP_DIR." >&2
        exit 1
    fi
    systemctl restart nginx
else
    echo "== nginx до setup.sh не работал — останавливаю"
    systemctl stop nginx || true
    systemctl disable nginx >/dev/null 2>&1 || true
fi

if command -v ufw >/dev/null; then
    was UFW80_WAS  || { echo "== ufw: убираю allow 80/tcp";  ufw delete allow 80/tcp  || true; }
    was UFW443_WAS || { echo "== ufw: убираю allow 443/tcp"; ufw delete allow 443/tcp || true; }
fi

# Копию состояния не удаляем, а откладываем: следующий setup.sh запишет новую.
mv "$BACKUP_DIR" "$BACKUP_DIR.rolled-back.$(date +%Y%m%d-%H%M%S)"

TUNNEL_AFTER="$(systemctl is-active tg-tunnel 2>/dev/null || true)"
echo "== Туннель бота после отката: ${TUNNEL_AFTER:-неизвестно}"
if [[ "$TUNNEL_BEFORE" == active && "$TUNNEL_AFTER" != active ]]; then
    echo "ОШИБКА: туннель бота упал. Поднять: systemctl restart tg-tunnel"
    exit 1
fi
echo "ГОТОВО: вход для VPN снят."
