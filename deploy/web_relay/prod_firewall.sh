#!/usr/bin/env bash
# Вход для VPN, БОЕВОЙ сервер: к портам 8080/8443 — только tg-relay (README.md рядом).
#
#     sudo /srv/weconomics/app/deploy/web_relay/prod_firewall.sh
#
# После перезагрузки запускается сам: юнит
# deploy/systemd/weconomics-web-relay-firewall.service.
#
# ⚠️ ПОЧЕМУ НЕ ufw. Docker публикует порты правилами iptables ВЫШЕ ufw
# (docs/SERVER.md, «Главная ловушка: Docker обходит ufw»): `ufw deny 8443`
# ничего бы не закрыл. Своё правило Docker разрешает класть только в цепочку
# DOCKER-USER — её он проходит раньше собственных правил и не трогает.
#
# ⚠️ ПОЧЕМУ --ctorigdstport. В DOCKER-USER пакет приходит уже после DNAT, с
# адресом контейнера в получателе. Порт, на который клиент стучался снаружи,
# помнит только conntrack — по нему и отбираем.
#
# Своя цепочка WEB-RELAY: при каждом запуске она очищается и заполняется
# заново, а переход на неё из DOCKER-USER ставится один раз. Поэтому скрипт
# можно запускать сколько угодно раз — правила не дублируются.
# Внутри: 8080 и 8443 с внешнего интерфейса от WEB_RELAY_IP — пропустить,
# от остальных — отбросить. WEB_RELAY_IP пуст — отбрасываются все.
# Остальные порты (80, 443, 22) цепочка не трогает.
set -euo pipefail

ENV_FILE="${ENV_FILE:-/srv/weconomics/.env}"
CHAIN=WEB-RELAY
PORTS=(8080 8443)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=relay_ip.sh
source "$HERE/relay_ip.sh"

if [[ $EUID -ne 0 ]]; then
    echo "ОШИБКА: запускать от root (sudo)." >&2
    exit 1
fi

RELAY_IP="$(web_relay_ip "$ENV_FILE")"

# Внешний интерфейс — тот, через который идёт маршрут по умолчанию. Без -i
# правило задело бы и исходящие соединения контейнеров на чужие 8080/8443.
EXT_IF="$(ip -4 route show default \
          | awk '{for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit }}')"
if [[ -z "$EXT_IF" ]]; then
    echo "ОШИБКА: не нашёлся внешний интерфейс (ip -4 route show default пуст)." >&2
    exit 1
fi

if ! iptables -n -L DOCKER-USER >/dev/null 2>&1; then
    echo "ОШИБКА: нет цепочки DOCKER-USER — Docker не запущен?" >&2
    exit 1
fi

iptables -N "$CHAIN" 2>/dev/null || true
iptables -F "$CHAIN"
for port in "${PORTS[@]}"; do
    if [[ -n "$RELAY_IP" ]]; then
        iptables -A "$CHAIN" -i "$EXT_IF" -p tcp -s "$RELAY_IP" \
            -m conntrack --ctorigdstport "$port" --ctdir ORIGINAL -j RETURN
    fi
    iptables -A "$CHAIN" -i "$EXT_IF" -p tcp \
        -m conntrack --ctorigdstport "$port" --ctdir ORIGINAL -j DROP
done
iptables -C DOCKER-USER -j "$CHAIN" 2>/dev/null || iptables -I DOCKER-USER 1 -j "$CHAIN"

iptables -n -v -L "$CHAIN"
if [[ -n "$RELAY_IP" ]]; then
    echo "ГОТОВО: 8080/8443 на $EXT_IF открыты только для $RELAY_IP."
else
    echo "ГОТОВО: WEB_RELAY_IP пуст — 8080/8443 на $EXT_IF закрыты всем."
fi
