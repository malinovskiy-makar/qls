#!/usr/bin/env bash
# Вход для VPN, БОЕВОЙ сервер: адрес машины tg-relay из .env (README.md рядом).
#
# Подключается через `source` из prod_realip.sh и prod_firewall.sh, сам ничего
# не делает. Один разбор на оба скрипта: иначе nginx верил бы одному адресу,
# а файрвол пускал бы другой.
#
#   web_relay_ip /srv/weconomics/.env   → печатает адрес или пустую строку;
#                                         неверное значение — код 1 и причина.

web_relay_ip() {
    local env_file="$1" value octet
    if [[ ! -r "$env_file" ]]; then
        echo "ОШИБКА: не читается $env_file" >&2
        return 1
    fi
    # Последняя строка WEB_RELAY_IP=… побеждает — так же читает docker compose.
    # Кавычки, пробелы и \r (файл правили в Windows) отбрасываем.
    value="$(grep -E '^[[:space:]]*WEB_RELAY_IP=' "$env_file" | tail -n 1 \
             | cut -d= -f2- | tr -d " \t\r\"'")" || true
    if [[ -z "$value" ]]; then
        echo ""
        return 0
    fi
    # Ровно один IPv4: маска (0.0.0.0/0 — «верить всем») и порт не проходят.
    if [[ ! "$value" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
        echo "ОШИБКА: WEB_RELAY_IP=$value — нужен один адрес IPv4, без маски и порта" >&2
        return 1
    fi
    for octet in "${BASH_REMATCH[@]:1}"; do
        if (( 10#$octet > 255 )); then
            echo "ОШИБКА: WEB_RELAY_IP=$value — число больше 255" >&2
            return 1
        fi
    done
    if (( 10#${BASH_REMATCH[1]} == 0 || 10#${BASH_REMATCH[1]} == 127 )); then
        echo "ОШИБКА: WEB_RELAY_IP=$value — это не адрес машины в интернете" >&2
        return 1
    fi
    echo "$value"
}
