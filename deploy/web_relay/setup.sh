#!/usr/bin/env bash
# Вход для VPN на машине tg-relay (VDSina, Нидерланды) — установка. README.md рядом.
#
#     sudo bash setup.sh          (из скопированной на машину папки web_relay)
#
# nginx начинает принимать 443/80 и пересылать TCP на боевой 8443/8080 без
# расшифровки, с PROXY protocol (nginx-stream.conf).
#
# ⚠️ НА ЭТОЙ МАШИНЕ ЖИВЁТ ТУННЕЛЬ БОТА — служба tg-tunnel (deploy/tg_relay/).
# Скрипт не трогает ни её, ни её ключ, ни настройки входа на машину: он
# меняет только nginx, правила ufw для 80/443 и продление старого сертификата.
# Состояние туннеля проверяется до начала и после конца.
#
# Что ещё делает (решение владельца 30.10.2026):
#   - старый nginx-сайт tg_relay (прежняя схема бота, не используется с
#     29.10) и сайт default отключаются: ссылки из sites-enabled уходят в
#     /root/web_relay_backup/, rollback.sh возвращает их на место;
#   - продление сертификата tg.weconomics.ai отключается так же: порт 80
#     теперь уходит на боевой, и продление падало бы дважды в сутки.
#     Боту сертификат не нужен — он ходит через туннель;
#   - любая другая программа на 80/443 или любой другой включённый сайт
#     nginx — СТОП, ничего не меняется.
#
# Повторный запуск безопасен. Откат — rollback.sh рядом.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR=/root/web_relay_backup
STATE="$BACKUP_DIR/state"
STREAM_CONF=/etc/nginx/web_relay_stream.conf
NGINX_CONF=/etc/nginx/nginx.conf
INCLUDE_LINE="include $STREAM_CONF;  # web_relay: вход для VPN (deploy/web_relay)"
OLD_SITES=(default tg_relay)
OLD_CERT=tg.weconomics.ai
PACKAGES=(nginx libnginx-mod-stream unattended-upgrades curl)

say()  { echo; echo "== $*"; }
stop() { echo; echo "СТОП: $*" >&2; echo "Ничего не изменено." >&2; exit 1; }
installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed'; }

[[ $EUID -eq 0 ]] || stop "запускать от root: sudo bash setup.sh"
[[ -f "$HERE/nginx-stream.conf" ]] || stop "рядом нет nginx-stream.conf — скопируйте папку web_relay целиком"

# ─── 1. Туннель бота ДО начала ───────────────────────────────────────────────
TUNNEL_BEFORE="$(systemctl is-active tg-tunnel 2>/dev/null || true)"
say "Туннель бота (tg-tunnel) до начала: ${TUNNEL_BEFORE:-неизвестно}"
if [[ "$TUNNEL_BEFORE" != active ]]; then
    echo "⚠️  Туннель бота сейчас НЕ работает (это было до скрипта)."
    echo "    Посмотреть: systemctl status tg-tunnel; journalctl -u tg-tunnel -n 50"
    read -r -p "Продолжить установку входа? [y/N] " ANSWER || ANSWER=""
    [[ "$ANSWER" =~ ^[yYдД]$ ]] || stop "остановлено по ответу"
fi

# ─── 2. Кто занимает 80/443 ──────────────────────────────────────────────────
say "Кто слушает 80/443"
LISTENERS="$(ss -H -ltnp '( sport = :80 or sport = :443 )' || true)"
echo "${LISTENERS:-никто}"
FOREIGN="$(printf '%s\n' "$LISTENERS" | grep -v '^[[:space:]]*$' | grep -v '"nginx"' || true)"
[[ -z "$FOREIGN" ]] || stop "порты 80/443 держит не nginx:
$FOREIGN
Разберитесь, что это за программа, и запустите скрипт снова."

if [[ -d /etc/nginx/sites-enabled ]]; then
    for site in /etc/nginx/sites-enabled/*; do
        [[ -e "$site" || -L "$site" ]] || continue
        name="$(basename "$site")"
        [[ " ${OLD_SITES[*]} " == *" $name "* ]] \
            || stop "в nginx включён сайт $site — не default и не tg_relay, чей он, неизвестно"
    done
fi
for conf in /etc/nginx/conf.d/*.conf; do
    if [[ -e "$conf" ]]; then
        stop "в /etc/nginx/conf.d лежит $conf — чей он, неизвестно"
    fi
done

# ─── 3. Как было до первого запуска (для rollback.sh) ────────────────────────
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
if [[ ! -f "$STATE" ]]; then
    ufw_had() { command -v ufw >/dev/null && ufw show added 2>/dev/null | grep -qxF "ufw allow $1"; }
    {
        echo "NGINX_WAS_INSTALLED=$(installed nginx && echo yes || echo no)"
        echo "NGINX_WAS_ACTIVE=$([[ "$(systemctl is-active nginx 2>/dev/null || true)" == active ]] && echo yes || echo no)"
        echo "UFW80_WAS=$(ufw_had 80/tcp && echo yes || echo no)"
        echo "UFW443_WAS=$(ufw_had 443/tcp && echo yes || echo no)"
        echo "SAVED_AT=$(date -Is)"
    } > "$STATE"
fi
say "Состояние до первого запуска ($STATE):"
cat "$STATE"

# ─── 4. Пакеты ───────────────────────────────────────────────────────────────
MISSING=()
for pkg in "${PACKAGES[@]}"; do installed "$pkg" || MISSING+=("$pkg"); done
if (( ${#MISSING[@]} )); then
    say "Ставлю: ${MISSING[*]}"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${MISSING[@]}"
else
    say "Пакеты уже стоят: ${PACKAGES[*]}"
fi
# Копия nginx.conf до нашей строки include — на случай ручного разбора.
if [[ ! -f "$BACKUP_DIR/nginx.conf.orig" ]]; then
    cp -p "$NGINX_CONF" "$BACKUP_DIR/nginx.conf.orig"
fi

# ─── 5. Правка nginx (запоминаем, что сделали в ЭТОТ запуск) ─────────────────
MOVED=()
STREAM_PREV=""
INCLUDE_ADDED=no

undo() {
    local item
    if [[ -n "$STREAM_PREV" ]]; then cp -p "$STREAM_PREV" "$STREAM_CONF"; else rm -f "$STREAM_CONF"; fi
    if [[ "$INCLUDE_ADDED" == yes ]]; then sed -i "\#web_relay_stream.conf#d" "$NGINX_CONF"; fi
    for item in "${MOVED[@]}"; do mv "${item%%|*}" "${item##*|}"; done
}

for name in "${OLD_SITES[@]}"; do
    src="/etc/nginx/sites-enabled/$name"
    if [[ -e "$src" || -L "$src" ]]; then
        mv -f "$src" "$BACKUP_DIR/sites-enabled.$name"
        MOVED+=("$BACKUP_DIR/sites-enabled.$name|$src")
        say "Отключён сайт nginx $name (копия: $BACKUP_DIR/sites-enabled.$name)"
    fi
done

renewal="/etc/letsencrypt/renewal/$OLD_CERT.conf"
if [[ -f "$renewal" ]]; then
    mv -f "$renewal" "$BACKUP_DIR/renewal.$OLD_CERT.conf"
    MOVED+=("$BACKUP_DIR/renewal.$OLD_CERT.conf|$renewal")
    say "Отключено продление сертификата $OLD_CERT (копия: $BACKUP_DIR/renewal.$OLD_CERT.conf)"
fi

if [[ -f "$STREAM_CONF" ]]; then
    STREAM_PREV="$BACKUP_DIR/web_relay_stream.conf.prev"
    cp -p "$STREAM_CONF" "$STREAM_PREV"
fi
install -m 644 "$HERE/nginx-stream.conf" "$STREAM_CONF"
if [[ ! -e /proc/net/if_inet6 ]]; then
    # Без IPv6 в ядре `listen [::]` не даст nginx подняться.
    sed -i '/listen \[::\]/d' "$STREAM_CONF"
    say "IPv6 на машине нет — слушаем только IPv4"
fi
if ! grep -qF "$STREAM_CONF" "$NGINX_CONF"; then
    printf '\n%s\n' "$INCLUDE_LINE" >> "$NGINX_CONF"
    INCLUDE_ADDED=yes
fi

say "Проверка конфигурации: nginx -t"
if ! nginx -t; then
    undo
    echo
    echo "ОШИБКА: nginx -t не прошёл. Изменения nginx этого запуска откачены," >&2
    echo "        работающий nginx не перезапускался." >&2
    exit 1
fi

# ─── 6. ufw: только открыть 80/443 ───────────────────────────────────────────
if command -v ufw >/dev/null; then
    say "ufw: разрешаю 80/tcp и 443/tcp"
    ufw allow 80/tcp
    ufw allow 443/tcp
    if ufw status | grep -q 'Status: inactive'; then
        echo "⚠️  ufw выключен: правила записаны, но не действуют. Включать его этот скрипт не будет."
    fi
else
    say "ufw не установлен — правила не нужны"
fi

# ─── 7. Запуск ───────────────────────────────────────────────────────────────
# restart, а не reload: на 443/80 прежде мог слушать http-сайт, теперь —
# stream; перезапуск гарантированно пересоздаёт слушатели. Простой — секунда,
# и до смены DNS сюда никто не ходит. Туннель бота от nginx не зависит.
say "Перезапуск nginx"
systemctl enable nginx >/dev/null 2>&1 || true
systemctl restart nginx
sleep 2

# ─── 8. Самопроверка ─────────────────────────────────────────────────────────
say "Самопроверка"
ERRORS=()

TUNNEL_AFTER="$(systemctl is-active tg-tunnel 2>/dev/null || true)"
echo "а) туннель бота: было ${TUNNEL_BEFORE:-неизвестно}, стало ${TUNNEL_AFTER:-неизвестно}"
if [[ "$TUNNEL_BEFORE" == active && "$TUNNEL_AFTER" != active ]]; then
    echo
    echo "################################################################"
    echo "##  ОШИБКА: ТУННЕЛЬ БОТА УПАЛ                                  ##"
    echo "##  Поднять:  systemctl restart tg-tunnel                       ##"
    echo "##  Журнал:   journalctl -u tg-tunnel -n 50                     ##"
    echo "################################################################"
    ERRORS+=("туннель бота упал")
fi

CURL_ERR="$(mktemp)"
trap 'rm -f "$CURL_ERR"' EXIT

HTTPS_CODE="$(curl -sS -m 15 -o /dev/null -w '%{http_code}' \
              --resolve weconomics.ai:443:127.0.0.1 https://weconomics.ai/ 2>"$CURL_ERR" || true)"
echo "б) https://weconomics.ai/ через вход: $HTTPS_CODE (ждём 200)"
[[ -s "$CURL_ERR" ]] && sed 's/^/   /' "$CURL_ERR" | head -3
[[ "$HTTPS_CODE" == 200 ]] || ERRORS+=("https через вход: $HTTPS_CODE вместо 200")

HEALTH_CODE="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1/healthz 2>"$CURL_ERR" || true)"
echo "в) http://127.0.0.1/healthz через вход: $HEALTH_CODE (ждём 200)"
[[ -s "$CURL_ERR" ]] && sed 's/^/   /' "$CURL_ERR" | head -3
[[ "$HEALTH_CODE" == 200 ]] || ERRORS+=("/healthz через вход: $HEALTH_CODE вместо 200")

echo
if (( ${#ERRORS[@]} )); then
    echo "ОШИБКА: ${ERRORS[*]}"
    echo "Если б) или в) — 000/timeout: на боевом открыты ли 8080/8443 для этой машины"
    echo "(prod_firewall.sh) и прописан ли WEB_RELAY_IP (README, «На боевом»)."
    echo "Откат: sudo bash rollback.sh"
    exit 1
fi
echo "ГОТОВО: вход работает, туннель бота жив."
