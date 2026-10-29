# Посредник Telegram: обратный SSH-туннель (инструкция для Андрея)

## Зачем и как устроено

С нашего боевого сервера (Selectel, `135.106.181.151`) Telegram не открывается (28.10.2026:
`curl https://api.telegram.org/` – `Connection timed out`). Без Telegram бот стены не может ни получить
«Старт», ни проверить подписку. Решение владельца 28.10: **свой** маленький сервер за рубежом.

**Что выяснилось 29.10.2026.** Сервер-посредник поднят (VDSina.com, Амстердам, `89.124.82.121`,
`tg.weconomics.ai`, nginx + сертификат) и сам работает, но **с боевого сервера до него не доходит ничего**:
80, 443 и 8443 – `timeout`, `tcpdump` на посреднике – 0 пакетов, SSH прошёл один раз и тоже перестал.
Исходящий фаервол боевого ни при чём (`OUTPUT ACCEPT`, `github.com:443` открывается): путь из России
к этому хостингу режется где-то по дороге. **В обратную сторону пускает:** с посредника на боевой идут и
SSH, и `https://weconomics.ai/` (200).

Поэтому соединение открывает **посредник** – обратным SSH-туннелем:

```
контейнер web / tgbot                         боевой хост                          посредник (Амстердам)
api.telegram.org → host-gateway  ──TLS──►  172.17.0.1:18443  ◄══ SSH -R ══  служба tg-tunnel
(TELEGRAM_API_BASE=                        (слушает sshd пользователя             ssh -NT -R … tgtunnel@боевой
 https://api.telegram.org:18443)            tgtunnel)                                  │
                                                                                       ▼
                                                                         api.telegram.org:443  (TLS сквозной)
```

- На боевом хосте адрес `172.17.0.1:18443` – это **прямой TLS до `api.telegram.org`**: посредник пересылает
  байты и **токена не видит** (в отличие от старой схемы с nginx, где TLS кончался на посреднике).
- Контейнеры видят имя `api.telegram.org` как шлюз хоста (`extra_hosts: "api.telegram.org:host-gateway"`
  в `deploy/docker-compose.yml`), поэтому сертификат и SNI настоящие, а порт задаёт
  `TELEGRAM_API_BASE=https://api.telegram.org:18443`.
- Входящих соединений от Telegram к нам не нужно: бот сам спрашивает новые сообщения (служба `tgbot`).

⚠️ **Старая схема «nginx на посреднике» (`nginx.conf`, шаги с сертификатом и `TELEGRAM_API_BASE=https://tg.weconomics.ai`)
НЕ ИСПОЛЬЗУЕТСЯ: путь Россия → хостинг посредника режется.** Файл `nginx.conf` оставлен как справка и на
случай, если когда-нибудь придётся вернуться к прямому пути. Для бота nginx на посреднике больше не нужен.

## 0. Безопасность

- Через туннель идёт **токен бота** (в адресе каждого запроса), но шифрованным сквозным TLS: посредник его
  не расшифровывает. Всё равно доступ к посреднику – **только у вас**.
- Пользователь `tgtunnel` на боевом хосте **ничего не может, кроме одного порта**: оболочка `nologin`, ключ
  с `restrict` и `permitlisten` только на `172.17.0.1:18443`, без терминала.
- Порт `18443` наружу не открыт: слушает только адрес `docker0`, а ufw пускает к нему лишь контейнеры.
- Если ключ посредника мог попасть не туда – удалите строку из `authorized_keys` на боевом хосте (раздел «На боевом»).

## На боевом сервере (один раз, от `root`/через `sudo`)

Выполнено руками 29.10.2026 и проверено; ниже то, что там должно стоять.

**1. Пользователь без оболочки:**

```bash
useradd --system --create-home --shell /usr/sbin/nologin tgtunnel
```

**2. Ключ посредника.** Создаётся **на посреднике** (от `root`, служба `tg-tunnel` работает от него же), без пароля:

```bash
ssh-keygen -t ed25519 -N "" -C tgtunnel@relay -f /root/.ssh/tgtunnel
cat /root/.ssh/tgtunnel.pub
```

Публичную часть (`tgtunnel.pub`) кладём на боевой в `~tgtunnel/.ssh/authorized_keys` **одной строкой с ограничениями**:

```
restrict,port-forwarding,permitlisten="172.17.0.1:18443" ssh-ed25519 AAAA…публичный_ключ… tgtunnel@relay
```

Права: `chmod 700 ~tgtunnel/.ssh && chmod 600 ~tgtunnel/.ssh/authorized_keys && chown -R tgtunnel: ~tgtunnel/.ssh`.

**3. Блок в самом конце `/etc/ssh/sshd_config`** (после него других `Match` быть не должно):

```
Match User tgtunnel
    AllowTcpForwarding remote
    GatewayPorts clientspecified
    X11Forwarding no
    PermitTTY no
    ClientAliveInterval 30
    ClientAliveCountMax 3
```

```bash
sshd -t && systemctl reload ssh
```

`clientspecified` нужен, чтобы туннель слушал именно `172.17.0.1`, а не `127.0.0.1`; `ClientAlive…` рвёт
мёртвое соединение за ~90 с, и порт освобождается для нового.

**4. Файрвол:** контейнерам – можно, остальным – нет:

```bash
ufw allow from 172.16.0.0/12 to 172.17.0.1 port 18443 proto tcp
```

## На посреднике (служба `tg-tunnel`)

Unit-файл – [`tg-tunnel.service`](tg-tunnel.service) в этой папке; кладётся в `/etc/systemd/system/`.
Файл сверен с рабочей службой на посреднике (29.10.2026): ключ `/root/.ssh/tgtunnel`, запуск от `root`,
строки `User=` нет.

```bash
install -m 644 tg-tunnel.service /etc/systemd/system/tg-tunnel.service
systemctl daemon-reload && systemctl enable --now tg-tunnel
```

Команда службы: `ssh -NT -i /root/.ssh/tgtunnel -o ServerAliveInterval=30 -o ServerAliveCountMax=3
-o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -R 172.17.0.1:18443:api.telegram.org:443
tgtunnel@135.106.181.151` (`Restart=always`, `RestartSec=10`).
Отпечаток боевого хоста служба запоминает при первом входе сама (`StrictHostKeyChecking=accept-new`).

## Проверка

**С боевого хоста** (не из контейнера): `--resolve` подставляет адрес туннеля под настоящее имя, поэтому
сертификат проверяется по-настоящему.

```bash
curl -sS -m 10 -o /dev/null -w "%{http_code}\n" --resolve api.telegram.org:18443:172.17.0.1 https://api.telegram.org:18443/
```

Должно быть `302` (ответ Telegram). Число и ничего больше – хорошо; `timed out` или «Connection refused» –
см. «Если не работает».

**Из контейнера** (после пересоздания `web` и `tgbot`, см. [docs/VP.md](../../docs/VP.md)):

```bash
docker compose exec web getent hosts api.telegram.org    # → 172.17.0.1  api.telegram.org
docker compose exec web python manage.py tg_setup --ping # → «Telegram отвечает за N мс»
```

## Настройки боевого `.env`

В `/srv/weconomics/.env` (токен и секрет без пробелов и кавычек, `.env` никому не пересылайте):

```
TELEGRAM_API_BASE=https://api.telegram.org:18443
TELEGRAM_BOT_TOKEN=<токен @weconomics_bot от Макара>
TELEGRAM_BOT_USERNAME=weconomics_bot
TELEGRAM_WEBHOOK_SECRET=<длинная случайная строка>
LEGAL_TG_RELAY=VDSina (SERVERS TECH FZCO, ОАЭ), Нидерланды
```

Адрес – без слэша на конце, обязательно `https://`, порт `18443`. Секрет нужен, даже когда вебхука нет (без
него путь Telegram считается ненастроенным): `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`.
Дальше – «Выкатка стены – по шагам» в [docs/VP.md](../../docs/VP.md).

## Если не работает

| Что видите | Что делать |
|---|---|
| `tg_setup --ping`: `timed out` / `Connection refused` | на боевом хосте `ss -ltn \| grep 18443` – должна быть строка с `172.17.0.1:18443`; нет – туннель не поднят: на посреднике `systemctl status tg-tunnel` и `journalctl -u tg-tunnel -n 50` |
| `getent hosts api.telegram.org` в контейнере даёт настоящий адрес Telegram, а не `172.17.0.1` | контейнер создан до правки compose: `docker compose up -d --force-recreate web` (и `tgbot`) |
| `ss` пусто, а на посреднике служба «active» | порт на боевом ещё занят старым соединением: после обрыва он освобождается за ~90 с (`ClientAlive…`); служба сама переподключится (`Restart=always`) |
| в логе службы `remote port forwarding failed` | то же: старый сеанс не умер; подождать ~90 с, `systemctl restart tg-tunnel` на посреднике |
| `Permission denied (publickey)` в логе службы | ключ посредника не в `authorized_keys` пользователя `tgtunnel` или права на `~tgtunnel/.ssh` не 700/600 |
| `curl` отвечает, а `tg_setup --ping`: ошибка сертификата | в контейнере имя ведёт не на шлюз, а `TELEGRAM_API_BASE` указывает на другой хост: база должна быть именно `https://api.telegram.org:18443` |
| в логе `tgbot` постоянные «пауза 60 с» | туннель или Telegram недоступен; пока так, стена пускает по почте |
| сервер посредника пропал или сменился IP | новый сервер: те же ключ и служба `tg-tunnel`, на боевом `authorized_keys` – новый ключ; `.env` не меняется |

Посредник – только пересылка: у него нет базы, нет данных и нет ничего, что надо резервировать.
