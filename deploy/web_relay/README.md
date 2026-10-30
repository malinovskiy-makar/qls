# Вход для VPN на машине tg-relay (инструкция для Андрея и Макара)

## Что это и зачем

Часть учеников сидит под VPN, и адрес выхода их VPN бывает в чёрном списке РКН. Тогда российский
фильтр (ТСПУ) режет трафик между этим адресом и нашим боевым сервером в Selectel (`135.106.181.151`):
сайт у человека просто не открывается.

Решение (Notion, «Доступность сайта с VPN…», поправка 30.10): зарубежная машина принимает
соединения на 443 и 80 и **пересылает их на боевой как есть**. Путь «VPN → зарубежная машина»
целиком за границей и фильтр не задевает, а путь «зарубежная машина → боевой» проверен.

```
ученик с VPN ──443──► tg-relay (Нидерланды) ──8443 + PROXY──► боевой nginx ──► Django
             ──80───►                       ──8080 + PROXY──►
```

- **Трафик не расшифровывается.** Сертификат есть только на боевом; tg-relay пересылает байты и
  содержимого не видит. Поэтому работает всё: вход, формы, стена, дуэли (WebSocket).
- **Настоящий адрес ученика доходит до боевого.** tg-relay первой строкой соединения шлёт PROXY
  protocol с адресом клиента, а боевой nginx верит этой строке **только от адреса tg-relay**.
  Без этого все VPN-пользователи выглядели бы одним адресом и упирались бы в общие лимиты входа.
- Россияне без VPN ходят напрямую, как сейчас. Позже DNS (Gcore, ответ по стране) начнёт отдавать
  адрес tg-relay всем, кроме России. Настройка Gcore — карточка в Notion, здесь её нет.

**Почему на той же машине, что туннель бота.** Тариф VDSina $0,07 в день даётся один на аккаунт;
пересылка почти не нагружает машину. Минус: если машина ляжет, лягут и бот, и вход. Сайт при этом
вернётся на боевой сам — через проверку здоровья в Gcore. Отдельную машину заведём, если адрес
попадёт в чёрный список или вырастет трафик (docs/SERVER.md, «Вход для VPN»).

**Туннель бота не трогаем.** `setup.sh` меняет только nginx, правила ufw для 80/443 и продление
старого сертификата `tg.weconomics.ai`. Службу `tg-tunnel`, её ключ и вход на машину по SSH он не
меняет. Состояние туннеля скрипт проверяет в начале и в конце.

## Что лежит в папке

| Файл | Где работает | Что делает |
|---|---|---|
| `nginx-stream.conf` | tg-relay | пересылка 443 → боевой:8443, 80 → боевой:8080 с PROXY protocol |
| `setup.sh` | tg-relay | установка входа, самопроверка |
| `rollback.sh` | tg-relay | откат `setup.sh` |
| `prod_realip.sh` | боевой | говорит nginx, чьему PROXY-заголовку верить |
| `prod_firewall.sh` | боевой | пускает к 8080/8443 только tg-relay |
| `relay_ip.sh` | боевой | общий разбор `WEB_RELAY_IP` для двух скриптов выше |

Юнит для файрвола после перезагрузки — `deploy/systemd/weconomics-web-relay-firewall.service`.

## Порядок: сначала боевой, потом tg-relay

`setup.sh` в конце проверяет всю цепочку до боевого. Если боевой ещё не готов, проверка упадёт.

### 1. На боевом (от `root` или через `sudo`)

Код ветки уже в `main` и подтянут на сервер (`git pull`, docs/SERVER.md, «Обновить сайт до
свежего кода»).

**1.1. Адрес tg-relay в `.env`.** Открыть `/srv/weconomics/.env` и дописать строку (адрес — публичный
IPv4 машины tg-relay, тот, по которому на неё заходите по SSH):

```
WEB_RELAY_IP=<адрес tg-relay>
```

**1.2. Файрвол — ДО публикации портов**, чтобы 8080/8443 ни минуты не были открыты всем.
Юнит запускает `prod_firewall.sh` сразу и после каждой перезагрузки:

```bash
cp /srv/weconomics/app/deploy/systemd/weconomics-web-relay-firewall.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now weconomics-web-relay-firewall.service
systemctl status weconomics-web-relay-firewall.service --no-pager   # active (exited), в конце «ГОТОВО»
iptables -n -v -L WEB-RELAY                                          # 4 правила: 2 RETURN от tg-relay, 2 DROP
```

**1.3. Кому верить PROXY-заголовок:**

```bash
/srv/weconomics/app/deploy/web_relay/prod_realip.sh
cat /srv/weconomics/nginx/conf.d/web_relay_realip.conf   # строка set_real_ip_from <адрес tg-relay>;
```

**1.4. Новый конфиг nginx и новые порты.** Сначала конфиг (как в docs/SERVER.md), потом пересоздание
контейнера nginx — без этого 8080/8443 не будут опубликованы:

```bash
cp /srv/weconomics/app/deploy/nginx/available/django.conf /srv/weconomics/nginx/available/django.conf
cp /srv/weconomics/nginx/available/django.conf /srv/weconomics/nginx/conf.d/weconomics.conf
cd /srv/weconomics/app/deploy && docker compose exec nginx nginx -t && docker compose up -d nginx
docker compose ps nginx                                  # Up … (healthy) через ~30 с
docker compose port nginx 8443                           # 0.0.0.0:8443
curl -sI https://weconomics.ai/ | head -1                # HTTP/2 200 — прямой путь жив
```

**1.5. Бот жив** (вход его не касается, но проверяем):

```bash
cd /srv/weconomics/app/deploy && docker compose --profile tgbot logs --tail=20 tgbot   # без ошибок и «пауза 60 с»
curl -sS -m 10 -o /dev/null -w "%{http_code}\n" --resolve api.telegram.org:18443:172.17.0.1 https://api.telegram.org:18443/   # 302
```

Вторая команда — проверка туннеля из [deploy/tg_relay/README.md](../tg_relay/README.md).

### 2. На tg-relay (от `root`)

Зайти на машину так же, как заходите для туннеля бота. Скопировать папку со своего компьютера
(PowerShell, из корня проекта):

```
scp -r deploy\web_relay root@<адрес tg-relay>:/root/
```

И на машине:

```bash
cd /root/web_relay && bash setup.sh
```

Скрипт спросит «Продолжить?», только если туннель бота уже не работает **до** начала. Тогда сперва
разберитесь с туннелем: `systemctl status tg-tunnel`.

В конце скрипт печатает самопроверку и одно из двух слов:

- **ГОТОВО** — вход работает, туннель бота жив;
- **ОШИБКА: …** — что именно не так. Если упал туннель бота, это написано крупно вместе с командой
  `systemctl restart tg-tunnel`.

Самопроверка — три пункта:

- а) `systemctl is-active tg-tunnel` → `active` (и было `active` в начале);
- б) `curl -sS -o /dev/null -w "%{http_code}" --resolve weconomics.ai:443:127.0.0.1 https://weconomics.ai/` → `200`;
- в) `curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1/healthz` → `200`.

Пункт в) — та же проверка, которой потом будет пользоваться Gcore: запрос по адресу без имени сайта
попадает на боевом в блок по умолчанию, где `/healthz` отвечает `ok`. Код 200 значит, что жива вся
цепочка tg-relay → боевой.

Что ещё делает `setup.sh`, и что вернёт `rollback.sh`:

- старый nginx-сайт `tg_relay` (прежняя схема бота, не используется с 29.10) и сайт `default`
  отключаются: ссылки из `/etc/nginx/sites-enabled/` переезжают в `/root/web_relay_backup/`;
- продление сертификата `tg.weconomics.ai` отключается так же. Порт 80 теперь уходит на боевой, и
  продление падало бы дважды в сутки. Боту сертификат не нужен — он ходит через туннель;
- если 80/443 держит не nginx или в nginx включён какой-то другой сайт, скрипт пишет **СТОП** и
  ничего не меняет.

## Проверки ДО смены DNS

DNS пока ведёт на боевой. Через вход ходим явно, подставляя адрес tg-relay. Ниже `IP_RELAY` —
адрес tg-relay.

**а) Самопроверка `setup.sh`** — «ГОТОВО» (см. выше).

**б) Боевой видит настоящий адрес, а не адрес tg-relay.** С компьютера Макара (PowerShell):

```
curl.exe -sS --resolve weconomics.ai:443:IP_RELAY "https://weconomics.ai/?relay-check=1" -o NUL -w "%{http_code}\n"
```

Потом на боевом:

```bash
cd /srv/weconomics/app/deploy && docker compose logs --since 10m nginx | grep relay-check
```

Строка должна начинаться с **вашего** адреса (его показывает, например, 2ip.ru), а **не** с адреса
tg-relay. Если первым стоит адрес tg-relay, `web_relay_realip.conf` пуст или в нём другой адрес:
повторите шаг 1.3.

**в) Сайт открывается через вход в трёх положениях:** VPN выключен; VPN включён и `weconomics.ai`
убран из исключений VPN; интернет раздаётся с телефона. В каждом положении по две команды
(PowerShell):

```
curl.exe -sS --resolve weconomics.ai:443:IP_RELAY https://weconomics.ai/ -o NUL -w "%{http_code} %{size_download}\n"
curl.exe -sS --resolve weconomics.ai:443:IP_RELAY https://weconomics.ai/static/vendor/d3-7.9.0/d3.min.js -o NUL -w "%{http_code} %{size_download}\n"
```

Должно быть `200` и число байт. Второй файл весит **279 708 байт**: если пришло столько же, крупный
файл скачался целиком и пересылка не обрывает длинные ответы.

Заодно проверьте, что напрямую 8443 снаружи закрыт: `curl.exe -m 5 -k https://135.106.181.151:8443/`
должен закончиться таймаутом.

**г) Вход по паролю и задача — в браузере через вход.** Временно направить имя сайта на tg-relay:

1. Пуск → набрать «Блокнот» → правой кнопкой → «Запуск от имени администратора».
2. Файл → Открыть → `C:\Windows\System32\drivers\etc\hosts` (в окне выбора: «Все файлы»).
3. Последней строкой дописать `IP_RELAY weconomics.ai` (адрес, пробел, имя) и сохранить.
4. PowerShell: `ipconfig /flushdns`. Закрыть браузер полностью и открыть заново.
5. Открыть `https://weconomics.ai/login/`, войти, открыть любую задачу `https://weconomics.ai/catalog/problem/<номер>/`.
   Что ходили именно через вход, видно на боевом: `docker compose logs --since 10m nginx | grep catalog/problem` —
   ваш адрес в начале строки.
6. **Вернуть как было:** удалить эту строку из `hosts`, сохранить, `ipconfig /flushdns`, перезапустить
   браузер.

⚠️ Если в браузере включён «безопасный DNS» (DNS over HTTPS), Firefox может не смотреть в `hosts`. Для
проверки возьмите Chrome или Edge.

## Откат

1. На tg-relay: `cd /root/web_relay && bash rollback.sh`. Он вернёт старые сайты nginx и продление
   сертификата, уберёт правила ufw, которые добавил `setup.sh`, и проверит, что туннель бота жив.
2. На боевом: стереть значение в строке `WEB_RELAY_IP=` в `/srv/weconomics/.env` (оставить пустым) и выполнить:

```bash
/srv/weconomics/app/deploy/web_relay/prod_realip.sh      # «PROXY-заголовку не верим ни от кого»
systemctl restart weconomics-web-relay-firewall.service  # 8080/8443 закрыты всем
```

Сайт по 80/443 работает как раньше: новые слушатели 8080/8443 никому не мешают, а закрытыми их
держит файрвол. Убрать порты совсем — вернуть прежние `django.conf` и `docker-compose.yml` из git и
пересоздать nginx (`docker compose up -d nginx`).
