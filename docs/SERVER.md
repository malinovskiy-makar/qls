> **Владелец:** Claude Code
> **Обновлён:** 2026-09-07 (сессия D1: площадка dev.weconomics.ai)
> **Статус:** актуален

# SERVER.md — боевой сервер weconomics.site

На той же машине с 07.09.2026 живёт **площадка разработчиков**
`dev.weconomics.ai` — отдельный раздел ниже.

Что это: VDS в Selectel (Москва, РФ), на котором живёт платформа.
На нём подняты база, Redis, **Django** и nginx с сертификатом.
Сайт https://weconomics.site и https://weconomics.ai открывает настоящее приложение.

Паролей и ключей в этом файле нет и быть не должно. Пароли служб живут
в `/srv/weconomics/.env` на сервере; пароль root — в менеджере паролей
у владельца.

---

## Коротко

| Что | Значение |
|---|---|
| IP | `135.106.181.151` |
| Домены | `weconomics.site`, `www.weconomics.site` |
| ОС | Ubuntu 24.04 LTS |
| Ресурсы | 4 vCPU / 8 ГБ / 80 ГБ + 2 ГБ подкачки |
| Имя хоста | `weconomics-prod` |
| Часовой пояс | Europe/Moscow |
| Рабочий пользователь | `makar` (sudo, вход только по ключу) |
| Каталог проекта | `/srv/weconomics` |

---

## Как подключиться

```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
```

На Windows в PowerShell:

```bash
ssh -i $env:USERPROFILE\.ssh\id_ed25519_weconomics makar@135.106.181.151
```

**Вход по паролю запрещён, вход под root по SSH запрещён.** Работает только
ключ `id_ed25519_weconomics` и только под пользователем `makar`. Нужны права
root — `sudo` (пароль не спрашивает, потому что у аккаунта его нет вовсе).

**Запасной вход, если SSH недоступен:** веб-консоль в панели Selectel. Это
обычная веб-страница, она работает даже когда SSH не проходит. Там вход
**под root по паролю** — тому самому, что лежит в менеджере паролей.
Единственное, ради чего этот пароль существует.

---

## Что где лежит

```
/srv/weconomics/
├── app/                        # КЛОН РЕПОЗИТОРИЯ. Только чтение из GitHub.
│   └── deploy/
│       ├── docker-compose.yml  #   описание всех служб — ЗАПУСКАТЬ ОТСЮДА
│       ├── backup.sh           #   резервное копирование
│       └── systemd/            #   таймер бэкапа
├── .env                        # ПАРОЛИ. Права 600, владелец makar.
│                               #   В репозиторий не попадает никогда.
├── backups/                    # копии базы. Права 700, владелец root.
├── nginx/
│   ├── available/
│   │   ├── django.conf         #   боевой конфиг (проксирование в Django)
│   │   └── stub.conf           #   заглушка «Сайт скоро откроется»
│   ├── conf.d/weconomics.conf  # АКТИВНЫЙ — копия одного из двух выше
│   └── html/index.html         # страница заглушки
├── certbot/
│   ├── conf/                   # сертификаты и настройки продления
│   └── www/                    # каталог для проверок Let's Encrypt
└── docker-compose.yml.pre-django.bak   # прежний compose, до Django
```

⚠️ **Все команды `docker compose` запускаются из `/srv/weconomics/app/deploy`**,
и только оттуда. Файла `docker-compose.yml` в корне `/srv/weconomics` больше
нет: он лежал бы вторым описанием тех же служб, и однажды кто-нибудь поднял бы
службы по устаревшей копии.

⚠️ **Состояние сервера живёт ВНЕ клона.** `.env`, `backups/`, `nginx/`,
`certbot/` лежат в `/srv/weconomics`, а не в `app/`. Клон можно снести целиком
и склонировать заново — ничего не потеряется. Поэтому в `docker-compose.yml`
эти каталоги подключены **абсолютными** путями, а не через `./`.

Копии всего, кроме `.env`, лежат в репозитории в `deploy/`. Образец
переменных — `deploy/env.example`.

### Как код попадает на сервер: deploy key

⚠️ **Репозиторий ПУБЛИЧНЫЙ** (проверено 07.09.2026:
`api.github.com/repos/malinovskiy-makar/qls` отдаёт `"private": false`;
раньше здесь было написано «приватный» — это устарело). Реестра образов
у проекта нет, образ собирается прямо
на сервере. Значит серверу нужен доступ к GitHub — и он выдан **отдельным
ключом только на чтение**:

- ключ: `/home/makar/.ssh/id_ed25519_deploy` (создан на сервере, приватная
  часть сервер никогда не покидала);
- публичная часть добавлена в репозиторий: **Settings → Deploy keys**,
  **без** галочки «Allow write access»;
- `~/.ssh/config` привязывает этот ключ к `github.com`.

⚠️ **Право записи не даём никогда.** Взломанный сервер с ключом на запись —
это подменённый код в репозитории, то есть отравленная следующая выкатка
у всех. С ключом на чтение потеря ограничена самим сервером.

Проверить доступ:

```bash
ssh -T git@github.com     # «Hi malinovskiy-makar/qls! You've successfully authenticated»
```

Данные базы и Redis — в именованных томах Docker (`weconomics_pgdata`,
`weconomics_redisdata`), а не в этом каталоге. Они переживают
`docker compose down` и пересоздание контейнеров.

---

## Службы

| Служба | Образ | Наружу | Зачем |
|---|---|---|---|
| `postgres` | postgres:17-alpine | **нет** | база |
| `redis` | redis:7-alpine | **нет** | кэш, сессии, счётчики частоты |
| `web` | `weconomics-web:latest` (собирается на месте) | **нет** | Django под gunicorn |
| `ws` | тот же `weconomics-web:latest` | **нет** | WebSocket дуэли под daphne |
| `search` | `weconomics-search:latest` | **нет** | кодирование поисковых запросов. ⚠️ **На 07.09.2026 НЕ РАЗВЁРНУТ:** контейнера нет вовсе, он ни разу не создавался (`docker compose ps -a` показывает пять служб, не шесть). Сайту это безразлично — `SEMANTIC_SEARCH_ENABLED=0`, поиск идёт по словам. Разворачивать вместе с включением флага |
| `nginx` | nginx:1.27-alpine | 80, 443 | единственная дверь снаружи |
| `certbot` | certbot/certbot | — | выпуск и продление сертификата |

`certbot` сам не поднимается (он в профиле `tools`), его вызывают точечно.

### ⚠️ У `ws` СВОЙ entrypoint, и в нём НЕТ миграций

⚠️ **02.09–07.09.2026 контейнер `ws` НЕ РАБОТАЛ ВОВСЕ, и это не было видно
снаружи.** `deploy/entrypoint-ws.sh` попал в репозиторий с режимом `100644`
вместо `100755`, а `entrypoint` задан exec-формой: файл без бита
исполняемости запустить нельзя. Контейнер застрял в состоянии `Created` —
`docker compose ps` **без `-a` его не показывал вовсе**, логи были пусты
(процесс не стартовал, писать было нечему), сайт при этом полностью живой, а
дуэль в реальном времени молча превращалась в асинхронную.

Найдено 07.09.2026 сессией площадки — по `docker compose ps -a`. Починено
`git update-index --chmod=+x deploy/entrypoint-ws.sh`; сторож —
`config/tests/test_deploy_scripts_executable.py` (читает индекс git, а не
файловую систему: на Windows бита исполняемости нет вовсе).

⚠️ **Вывод на будущее: `docker compose ps` без `-a` — не проверка.** Он
показывает только запущенное, и контейнер, который не смог стартовать,
выглядит как отсутствующий. Проверять состав служб — только с `-a`.


Образ у `web` и `ws` один, а точки входа разные:
`deploy/entrypoint.sh` против `deploy/entrypoint-ws.sh`. Это прямое следствие
запрета ниже: миграции накатывает ровно один процесс. В `entrypoint-ws.sh`
нет ни `migrate`, ни `collectstatic` — только ожидание служб и запуск daphne.

Живость `ws` проверяется своей ручкой `/ws/health/`: она **не ходит ни в
Django, ни в базу** и отвечает на вопрос «жив ли ASGI-процесс». gunicorn
может отвечать, а daphne лежать; сайт при этом полностью живой, а дуэль молча
превращается в асинхронную, и заметил бы это только игрок посреди забега.

Погасить дуэль в реальном времени, не трогая сайт:

```bash
cd /srv/weconomics/app/deploy
docker compose stop ws
```

Обоснование устройства — [ADR 0062](adr/0062-game-realtime-duel-implemented.md).

### ⚠️ Контейнер `web` ровно один, и второй поднимать нельзя

`deploy/entrypoint.sh` накатывает миграции при старте **без всякой
блокировки**. Это безопасно ровно до тех пор, пока процесс один. Два
контейнера пойдут мигрировать одновременно, каждый увидит незаконченную
работу другого, и схема развалится — а обнаружится это не в момент старта,
а на первом запросе к изменившейся таблице.

Масштабирование — **только числом воркеров gunicorn внутри одного
контейнера**, переменная `GUNICORN_WORKERS`.

### ⚠️ Почему воркеров четыре, а не девять

Формула «2 × ядра + 1» дала бы девять. Столько ставить нельзя:

| Что | Сколько |
|---|---|
| ОЗУ сервера | 7,8 ГБ |
| 4 воркера gunicorn | ~350 МБ (замер: 86 МБ на воркер) |
| PostgreSQL + Redis + nginx | ~75 МБ |
| **Зарезервировано под сервис поиска** | **~2,5 ГБ** |
| Запас | остальное |

Модель эмбеддингов весит 2,12 ГБ. Когда «мину №1» будут расшивать, модель
переедет в **отдельный процесс** — один на сервер, а не по копии на воркер.
Место под неё держим заранее: поднять число воркеров сейчас означает потом
объяснять, почему сервис поиска не помещается.

Замер после прогрева (шесть запросов к поиску, три страницы каталога):
худший воркер — **86,1 МБ**, контейнер `web` целиком — 258 МБ, свободно
**6,8 Gi**.

### Что лежит в `.env`

Полный список ключей с пояснениями — `deploy/env.example` (значения там
пустые). Коротко, что обязательно:

| Ключ | Смысл |
|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | база |
| `REDIS_PASSWORD` | Redis |
| `DATABASE_URL` | `postgres://ПОЛЬЗОВАТЕЛЬ:ПАРОЛЬ@postgres:5432/БАЗА` |
| `REDIS_URL` | `redis://:ПАРОЛЬ@redis:6379` — **без номера базы** |
| `SECRET_KEY` | ключ подписи Django |
| `DJANGO_SETTINGS_MODULE` | `config.settings_production` |
| `ALLOWED_HOSTS` | `weconomics.site,www.weconomics.site,weconomics.ai,www.weconomics.ai` |
| `CSRF_TRUSTED_ORIGINS` | они же со схемой `https://` |
| `SEMANTIC_SEARCH_ENABLED` | `0` — см. [ADR 0012](adr/0012-semantic-search-flag-off-in-prod.md) |
| `GUNICORN_WORKERS` | `4` |
| `BACKUP_S3_*` | внешнее хранилище копий, пока пусто |

⚠️ **`DATABASE_URL` и `REDIS_URL` живут ТОЛЬКО в `.env`.** Раньше
`docker-compose.yml` собирал их сам из `POSTGRES_*`; оттуда убрано. Секция
`environment` в compose перебивает `env_file`, поэтому при двух источниках
правка `.env` не давала бы никакого эффекта — а искали бы причину долго.
Меняете пароль базы — правьте и строку `DATABASE_URL`.

⚠️ **Значения в `.env` — только латиница и цифры, без пробелов и кавычек.**
Причина не в красоте: файл читают и оболочка (`. .env` в скриптах), и разбор
URL. Значение вида `a(b)c` для оболочки — уже синтаксис, и скрипт падает с
`word unexpected`; символы `@ : / # ?` ломают разбор адреса базы. Так уже
упал первый прогон бэкапа на `SECRET_KEY`. С тех пор ключ перевыпущен
64 знаками `[A-Za-z0-9]`, а `backup.sh` читает нужные значения **текстом**,
не исполняя файл, — но полагаться на одну защиту из двух не стоит.

Хост `redis` и `postgres` — это имена служб во внутренней сети Docker,
наружу порты не опубликованы.

⚠️ **Номер базы не указывать.** Его дописывают настройки Django:

| База Redis | Что там живёт |
|---|---|
| 0 | кэш приложения (алиас `default`) |
| 1 | сессии (алиас `sessions`) |
| 2 | брокер Celery — зарезервировано |
| 3 | channel layer WebSocket-дуэлей (алиас `channels`, `config/settings.py::CHANNEL_LAYERS`) |
| 14, 15 | только прогоны тестов |

⚠️ **База 3 больше не «зарезервировано» — с ADR 0062 она в работе.**
`CHANNEL_LAYERS['default']['CONFIG']['hosts']` читает `f'{REDIS_URL}/3'`:
контейнер `ws` (daphne) и `web` (gunicorn) обмениваются через неё табло
дуэли и восемь реакций. `REDIS_URL` в `.env` номер базы не содержит — его
дописывают настройки, как и для кэша/сессий выше.

Кэш и сессии разведены по разным базам не для порядка: `cache.clear()` у
Redis-бэкенда Django — это `FLUSHDB`, он вычищает базу целиком. Лежи
сессии рядом с кэшем, любой сброс кэша разлогинил бы всех.

⚠️ **Без `REDIS_URL` боевые настройки не поднимутся вовсе** — упадут при
старте с `ImproperlyConfigured`. Это сделано нарочно: без переменной Django
взял бы кэш в памяти процесса, сайт бы поднялся, и на девяти воркерах вышло
бы девять независимых кэшей. Подробности и отвергнутые варианты —
[ADR 0011](adr/0011-redis-cache-and-sessions.md).

Проверить, что Redis отвечает (пароль в вывод не попадает):

```bash
cd /srv/weconomics/app/deploy
docker compose exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
```

---

## Выкатка и обновление

### ⚠️ Первое, что надо сделать после пуша ветки `feat/prod-deploy`

Клон на сервере сейчас стоит на `main` и содержит **локальные правки** —
файлы `deploy/`, которые ещё не были в репозитории на момент развёртывания.
Они байт-в-байт совпадают с коммитом этой сессии (сверено по sha256), поэтому
терять нечего, но
обычный `git pull` на них споткнётся.

Когда ветка будет запушена и влита, на сервере:

```bash
cd /srv/weconomics/app && git fetch origin && git reset --hard origin/main && git status --short
```

`git status --short` должен вывести пусто. Проверить, что ничего не поехало:

```bash
sha256sum deploy/docker-compose.yml deploy/backup.sh deploy/nginx/available/django.conf
cd deploy && docker compose config --quiet && echo ok
```

После этого `git pull --ff-only` работает как обычно, и весь раздел ниже —
про обычную жизнь.

### Обновить сайт до свежего кода

```bash
cd /srv/weconomics/app && git pull --ff-only && cd deploy && docker compose build web && docker compose up -d web
```

Что происходит: подтянулся код → пересобрался образ → контейнер `web`
пересоздался, а его `entrypoint` сам дождался базы и Redis, накатил миграции
и пересобрал статику. Простой — секунды: `nginx`, `postgres` и `redis`
не перезапускаются.

Проверить, что получилось:

```bash
cd /srv/weconomics/app/deploy
docker compose ps                                  # web должен быть healthy
docker compose exec web python manage.py makemigrations --check --dry-run
curl -sI https://weconomics.site/ | head -1
```

⚠️ **Если менялась конфигурация nginx** — она НЕ подтягивается сама:
активен файл `/srv/weconomics/nginx/conf.d/weconomics.conf`, а не тот, что
в клоне. Обновлять явно:

```bash
cp /srv/weconomics/app/deploy/nginx/available/django.conf /srv/weconomics/nginx/available/django.conf
cp /srv/weconomics/nginx/available/django.conf /srv/weconomics/nginx/conf.d/weconomics.conf
cd /srv/weconomics/app/deploy && docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

Сначала `nginx -t`, только потом `reload`. Перезагрузка со сломанным
конфигом уронит сайт.

### ⚠️ Откат к заглушке — ОДНОЙ КОМАНДОЙ

Если после выкатки сайт сломался и чинить некогда: вернуть страницу
«Сайт скоро откроется» вместо ошибок.

```bash
cd /srv/weconomics/app/deploy && cp /srv/weconomics/nginx/available/stub.conf /srv/weconomics/nginx/conf.d/weconomics.conf && docker compose exec nginx nginx -s reload
```

Обратно на Django — та же команда с `django.conf` вместо `stub.conf`.

**Команда проверена, а не написана по памяти** (2026-08-21). Проверка делалась
дважды: до первой замены конфига на боевой и ещё раз после переезда
`docker-compose.yml` в клон — путь в команде от этого переезда меняется, и
непроверенная команда отката врала бы ровно в тот момент, когда нужна.

- Первый раз, до Django: конфиг подменён на отдающий `503`, сайт действительно
  отдал `503`, после команды — `200` с заглушкой.
- Второй раз, на живом сайте: `200` «ЭкЗадачи» → команда → `200` «Weconomics.
  Сайт скоро откроется» → та же команда с `django.conf` → снова «ЭкЗадачи».

Заглушка не трогает Django: контейнер `web` продолжает работать, просто
nginx перестаёт в него проксировать. Данные и сессии на месте.

### Сервис поиска: проверка, что порт закрыт наружу

⚠️ **Это место проверяется отдельно, и «сайт работает» доказательством не
считается.** У контейнера `search` эндпоинт `/encode` работает **без
авторизации**: он кодирует текст моделью, то есть жжёт CPU. Опубликованный
наружу порт раздавал бы эту молотилку кому угодно, и заметно это стало бы
только по счёту за электричество или по упавшему поиску.

Защита ровно одна — **у сервиса `search` в compose нет секции `ports`**.
Проверять надо все три ответа, а не один:

```bash
cd /srv/weconomics/app/deploy

# 1. С хоста — ОТКАЗ. Это главная проверка.
curl -sS --max-time 5 http://localhost:8001/healthz ; echo "  ^ ожидается отказ соединения"

# 2. Изнутри самого контейнера — успех.
docker compose exec search curl -fsS http://127.0.0.1:8001/healthz

# 3. Из контейнера web по имени сервиса — успех. Именно так ходит Django.
docker compose exec web curl -fsS http://search:8001/healthz
```

Первый ответ обязан быть «Failed to connect», второй и третий —
`{"ok":true,...}`. Если первый вдруг ответил — в compose появилась секция
`ports`, и её надо убрать немедленно.

⚠️ С 17.09.2026 `/healthz` — проверка **готовности**: пока модель грузится,
второй и третий ответ — `503` с `{"ok":false,"model_loaded":false,...}`, и
`curl -f` пишет ошибку. Это не закрытый порт, а загрузка: подождать, пока
`docker compose ps` покажет у `search` `healthy` (до 4 минут), и повторить.

⚠️ `docker ps` показывает у контейнера `8001/tcp` — это `EXPOSE` из образа,
а НЕ опубликованный порт. Опубликованный выглядел бы как
`0.0.0.0:8001->8001/tcp`. Спутать легко, поэтому проверяем curl-ом, а не
глазами по `docker ps`.

⚠️ **Модель грузится сама при старте контейнера** (с 17.09.2026; раньше —
только по первому `/encode`, после перезагрузки его приходилось дёргать
руками). Загрузка 2,12 ГБ с тома `hfcache` занимает минуты; при пустом томе
модель сначала качается с Hugging Face — это дольше, и повторно она не
качается: том переживает пересборку образа. `/healthz` отвечает сразу, но
`503`, пока модели нет; healthcheck даёт на загрузку `start_period: 240s`.
Перезапуска по нездоровью compose не делает, так что долгая первая загрузка
контейнер не убьёт — он просто дольше будет `unhealthy`. В журнале —
строка `Модель загружена за N с.` (`docker compose logs search`). Живой
сайт загрузку переживает: пока сервис не готов, поиск деградирует до поиска
по словам.

Порядок проверки сторожится и тестом — `ComposeIsolationTests` в
`catalog/tests/test_search_service.py` читает оба compose-файла текстом и
краснеет, если секция `ports` появится.

### Синхронизация банка на бою (`bank_sync_export` → `bank_sync_apply`)

Штатный путь любой правки банка на бой ([ADR 0107](adr/0107-bank-sync-by-update.md),
`docs/DATA.md`, «Синхронизация банка с боем»): пакет собирается ДОМА, на бою
меняется только отличающееся, со снимком и откатом. Задачи, которых на бою нет,
не создаются; задачи боя вне пакета не трогаются. Выполняет владелец.
Репетиция на копии боя 17.09.2026 — `reports/bank_sync_20260917/JOURNAL.md`,
Фаза 6 (запись 33 с, откат 22 с, повторный прогон — 0 изменений).

⚠️ Порядок: **код → бэкап → пакет каталога → (второй пакет) → векторы →
«похожие» → перезапуск.** Векторы — ПОСЛЕ синхронизации: до неё ввоз снова
разойдётся с текстами.

**0. Код** с командами синхронизации — обычная выкатка («Обновить сайт до
свежего кода»). Миграций у сессии 17.09 нет.

**1. Свежая копия базы** — бэкап в 03:20 может быть старым:

```bash
sudo /srv/weconomics/app/deploy/backup.sh
```

**2. Пакет дома** (PowerShell, `C:\Users\shipu\qls`) и отправка сжатым — пакет
каталога весит ~200 МБ, почти всё — картинки в base64:

```bash
venv313\Scripts\python.exe manage.py bank_sync_export --scope catalog --out reports/bank_sync/bank_sync_prod
tar -czf reports/bank_sync/bank_sync_prod.tar.gz -C reports/bank_sync bank_sync_prod
scp reports/bank_sync/bank_sync_prod.tar.gz <адрес из «Как подключиться»>:/srv/weconomics/bank_sync/
```

Второй пакет — задачи, скрытые дома, но видимые на бою (17.09: 139 задач,
`content_status` needs_fix/junk) — **везти, решение владельца 17.09.2026**: дом — источник истины и по видимости:

```bash
venv313\Scripts\python.exe manage.py bank_sync_export --ids-file reports/bank_sync_20260917/prod_visible_home_hidden_ids.txt --out reports/bank_sync/bank_sync_prod_hidden
tar -czf reports/bank_sync/bank_sync_prod_hidden.tar.gz -C reports/bank_sync bank_sync_prod_hidden
scp reports/bank_sync/bank_sync_prod_hidden.tar.gz <адрес из «Как подключиться»>:/srv/weconomics/bank_sync/
```

**3. На сервере:** распаковать и положить в контейнер (томов с
`/srv/weconomics` у `web` нет):

```bash
sudo mkdir -p /srv/weconomics/bank_sync && cd /srv/weconomics/bank_sync
tar -xzf bank_sync_prod.tar.gz
cd /srv/weconomics/app/deploy
docker compose cp /srv/weconomics/bank_sync/bank_sync_prod web:/tmp/bank_sync_prod
```

**4. Сухой прогон и отчёт.** Отчёты — в `/tmp/bank_sync_reports`, а не в каталог
пакета: `docker compose cp` кладёт пакет от root, и `weco` не создаст в нём папку.

```bash
docker compose exec web python manage.py bank_sync_apply --package /tmp/bank_sync_prod --report /tmp/bank_sync_reports/prod_dry
docker compose cp web:/tmp/bank_sync_reports/prod_dry /srv/weconomics/bank_sync/prod_dry
less /srv/weconomics/bank_sync/prod_dry/REPORT.md
```

Ждать (по копии боя 17.09): задач с изменениями ~7 300, нет в базе ~151,
справочники source 5 и topic 13, флаги видимости — 0. Файл повреждён при
переносе — команда откажет сама (хеши `manifest.json`).

**5. Запись и снимок наружу СРАЗУ** (пересоздание контейнера унесёт `/tmp`):

```bash
docker compose exec web python manage.py bank_sync_apply --package /tmp/bank_sync_prod --apply --report /tmp/bank_sync_reports/prod_apply
docker compose cp web:/tmp/bank_sync_reports/prod_apply /srv/weconomics/bank_sync/prod_apply
# идемпотентность: обязано сказать «Изменений нет.»
docker compose exec web python manage.py bank_sync_apply --package /tmp/bank_sync_prod --report /tmp/bank_sync_reports/prod_again
```

Второй пакет — те же шаги 3–5 с `bank_sync_prod_hidden`.

**6. Векторы без ключа** (файлы — «Включение смысловой ноги на бою», шаг 1):

```bash
docker compose exec web python manage.py embeddings_import_vectors --vectors /tmp/vectors/catalog --state /tmp/vectors/catalog.state.json
docker compose exec web python manage.py embeddings_import_vectors --vectors /tmp/vectors/catalog --state /tmp/vectors/catalog.state.json --apply
```

В плане «пропущено, текст изменился» должно быть 0.

**7. «Похожие» и перезапуск:**

```bash
docker compose exec web python manage.py cache_similar --rebuild
docker compose up -d --force-recreate web ws
```

Проверить: `/catalog/` — фильтр тем показывает 29 тем; чип источника на
странице задачи ведёт на первоисточник; `/catalog/?has_solution=1` отвечает.
Перезапуск без ручного прогрева — «Обслуживание».

**Откат** — снимками в обратном порядке (сначала второй пакет):

```bash
docker compose cp /srv/weconomics/bank_sync/prod_apply web:/tmp/prod_apply
docker compose exec web python manage.py bank_sync_apply --revert /tmp/prod_apply/snapshot_<время>.json
```

Правку, сделанную после синхронизации кем-то ещё, откат не затирает и
называет в `snapshot_<время>_REVERT.md`.

### Включение смысловой ноги на бою

⚠️ **Порядок важен: векторы в базе → контейнер `search` → флаг.** Флаг без
векторов включит поиск по пустой матрице, контейнер без свободной памяти
уронит соседей. Выполняет владелец; сессия 15.09.2026 подготовила команды,
файл векторов и прогрев. Устройство — `docs/EMBEDDINGS.md`, раздел «Прогрев
воркера, разбивка времени и векторы на бой».

**0. Прогрев уже едет с кодом.** С 15.09 gunicorn стартует с
`-c /app/config/gunicorn_conf.py`: хук `post_worker_init` запускает фоновый
поток, который строит корпус bm25 (и матрицу векторов, если
`SEMANTIC_SEARCH_ENABLED=1`) сразу после старта воркера. Замер на 14 082
задачах: корпус 22–26 с, индекс 3 с. Выключатель — `SMART_SEARCH_WARMUP=0` в
`/srv/weconomics/.env`. После выкатки в журнале у каждого воркера строка
`прогрев: корпус N задач за X с, …`:

```bash
cd /srv/weconomics/app/deploy
docker compose logs web | grep 'прогрев:'
```

⚠️ **Везти вывоз от 15.09.2026 20:56 — он свежий.** Подпункты тестов из условия
сделали устаревшими 4 096 векторов; все пересчитаны на рабочей базе (повторный
`build_embeddings --stale` — 0), вывезено 14 082 вектора, 55,0 МБ, сухой ввоз на
рабочей базе — «к записи 14 082, пропущено 0» (`docs/EMBEDDINGS.md`, «Векторы на
бой — файлом»). Прежний вывоз 13:42 удалён. На бою ввозить ПОСЛЕ
`test_options_from_statement --apply` («Варианты теста из условия на бою»), иначе
ввоз пропустит эти задачи строкой «пропущено, текст изменился».

**1. Векторы — файлом с машины владельца.** Посчитать их в `web` нечем
(ADR 0002), а `dump_for_deploy` поле `embedding` не везёт. Готовый вывоз
15.09.2026 лежит дома, в `C:\Users\shipu\qls`, — отправить его:

```bash
scp reports/night_20260915/vectors_20260915_2056/catalog.f32 reports/night_20260915/vectors_20260915_2056/catalog.meta.json reports/night_20260915/vectors_20260915_2056/catalog.state.json <адрес из «Как подключиться»>:/srv/weconomics/vectors/
```

Следующий вывоз — после новых правок текстов, сначала `build_embeddings --stale`:

```bash
venv313\Scripts\python.exe manage.py embeddings_export_vectors --out reports/vectors/catalog
scp reports/vectors/catalog.f32 reports/vectors/catalog.meta.json reports/vectors/catalog.state.json <адрес из «Как подключиться»>:/srv/weconomics/vectors/
```

Получатся три файла: векторы (~55 МБ на 14 082 задачи), метаданные и копия
отметки сверки билда. У контейнера `web` папки `/srv/weconomics` нет (томов
только `static` и `media`), поэтому файлы кладутся внутрь `docker compose cp`:

```bash
cd /srv/weconomics/app/deploy
docker compose cp /srv/weconomics/vectors/. web:/tmp/vectors/
# план: сколько запишется, у скольких текст разошёлся, скольких нет в базе
docker compose exec web python manage.py embeddings_import_vectors --vectors /tmp/vectors/catalog --state /tmp/vectors/catalog.state.json
# запись — одной транзакцией, со свип-детектором текстов
docker compose exec web python manage.py embeddings_import_vectors --vectors /tmp/vectors/catalog --state /tmp/vectors/catalog.state.json --apply
```

⚠️ **`embeddings_check_build` на бою не запускается и не нужен.** Модели нет
в `web`, а у `search` нет ни базы, ни кода проекта. Сверку «видеокарта против
CPU-контейнера поиска» провели дома 09.09.2026 на этих самых векторах
(минимум косинуса 0,9999999) — её отметку и везёт `catalog.state.json`, без
неё ввоз не пишет. Строка «пропущено, текст изменился» в плане — это задачи,
у которых на бою текст другой: им вектор не пишется, и это правильно.

**Временный ввоз 16.09 с ключом `--ignore-text-check`: почему и когда
повторить без ключа.** План ввоза вывоза от 15.09 показал: к записи 3 520, а
10 411 из 14 082 строк — «пропущено, текст изменился после вывоза». Причина —
не порча файла: боевой банк отстал от домашнего с 13.09 (перенос корпуса на
прод ещё не выполнен, у ~3 000 задач на бою нет тем/тегов и обогащения,
которые входят в отпечаток `v2_focus_repeat`), а `bulk_load_fixtures`, которым
заливались фикстуры, умеет только добавлять строки и не обновляет
существующие. Решение владельца 16.09: ввезти домашние векторы под нынешние
боевые тексты ключом `--ignore-text-check` — векторы посчитаны по тем же
задачам, просто по более богатым (домашним) текстам, и `catalog/semantic.py`
отпечаток текста не сверяет вовсе. Команда:

```bash
docker compose exec web python manage.py embeddings_import_vectors --vectors /tmp/vectors/catalog --state /tmp/vectors/catalog.state.json --apply --ignore-text-check
```

⚠️ Ключ — **временная мера**, не новый обычный режим. После синхронизации
банка (раздел «Синхронизация банка на бою» ниже, 17.09.2026) ввоз повторяется
штатно, **без** ключа: только тогда расхождение отпечатка снова станет
сигналом «текст правда другой», а не шумом от отставшего банка. Репетиция на
копии боя 17.09: после синхронизации «пропущено, текст изменился» — 0 из 13 931.

**2. Контейнер поиска.**

```bash
free -m                                   # нужно ≥ 3 ГБ свободных вместе с buff/cache
cd /srv/weconomics/app/deploy
docker compose build search && docker compose up -d search
docker compose logs -f search             # ждать «Модель загружена за N с.» (минуты), выход — Ctrl+C
docker compose ps search                  # healthy
docker compose exec web curl -fsS http://search:8001/healthz   # {"ok":true,"model_loaded":true,...}
```

Затем три проверки закрытого порта из раздела выше — все три, не одну.

**3. Флаги.** В `/srv/weconomics/.env`:
`SEMANTIC_SEARCH_ENABLED=1`, `SMART_SEARCH_RERANK=1`,
`SEARCH_SERVICE_URL=http://search:8001`. Затем:

```bash
docker compose up -d web ws
```

**4. Проверка.** Через минуту после перезапуска (прогрев):

```bash
curl -sI "https://weconomics.ai/catalog/?q=%D0%BD%D0%B0%D0%BB%D0%BE%D0%B3" | grep -i x-smart-search
```

Ожидается `X-Smart-Search: rerank` и `X-Smart-Search-Ms:` с числом. Плашки
«Ищем по словам…» на странице поиска быть не должно. Пока `search` не
`healthy` (модель грузится после старта), поиск законно уходит в поиск по
словам — плашка на нём честная; ручной прогрев `/encode` не нужен.

**Откат:** `SEMANTIC_SEARCH_ENABLED=0` в `.env`, `docker compose up -d web ws`,
затем `docker compose stop search`. Векторы в базе поиску по словам не мешают.

### Варианты теста из условия на бою (`test_options_from_statement`)

Ночная сессия 15.09.2026 перенесла варианты теста из текста условия в подпункты
(`ProblemPart`) и вырезала блок вариантов из условия — обратимо, со снимком
([ADR 0104](adr/0104-test-options-from-statement.md), `docs/DATA.md`). На бою
команда идёт изнутри `web` **после выкатки ветки и ДО ввоза векторов**: векторы
посчитаны дома по уже укороченным условиям, и ввоз до записи пропустил бы эти
задачи строкой «пропущено, текст изменился».

⚠️ Перед записью — свежий дамп базы: бэкап в 03:20 может быть старым.

```bash
cd /srv/weconomics/app/deploy
# 1. Сухой прогон основного прохода: REPORT.md и preview.html, база не меняется
docker compose exec web python manage.py test_options_from_statement --dry-run --report /app/reports/test_options_prod
docker compose cp web:/app/reports/test_options_prod ./test_options_prod   # прочитать REPORT.md и preview.html
# 2. Запись основного прохода; снимок отката ложится в тот же каталог
docker compose exec web python manage.py test_options_from_statement --apply --report /app/reports/test_options_prod
# 3. Хвост «Верно/Неверно» у «верно/неверно» с подпунктами: сухой прогон, затем запись
docker compose exec web python manage.py test_options_from_statement --boolean-tail --dry-run --report /app/reports/test_options_prod_tail
docker compose exec web python manage.py test_options_from_statement --boolean-tail --apply --report /app/reports/test_options_prod_tail
# 4. Снимки наружу СРАЗУ: пересборка контейнера унесёт /app/reports
docker compose cp web:/app/reports/test_options_prod ./test_options_prod
docker compose cp web:/app/reports/test_options_prod_tail ./test_options_prod_tail
# 5. Идемпотентность: оба повторных сухих прогона обязаны сказать «к записи: задач 0»
docker compose exec web python manage.py test_options_from_statement --dry-run --report /app/reports/test_options_prod_again
docker compose exec web python manage.py test_options_from_statement --boolean-tail --dry-run --report /app/reports/test_options_prod_tail_again
```

Файл id основного прохода по умолчанию
(`reports/corpus_transfer_20260913/dead_test_widget_ids.txt`) в образ не едет:
`reports/` в `.gitignore`. Положить его в контейнер `docker compose cp` или
передать свой `--ids-file`; проход хвоста кандидатов из файла не берёт, он идёт по
всем «верно/неверно» с подпунктами. **Откат — в обратном порядке снимков:**
сначала `--revert <снимок хвоста>`, затем `--revert <снимок основного прохода>`;
правленые после записи условия и подпункты откат не трогает и называет.

### Библиотеки браузера едут со своего же сервера

С **04.09.2026 внешних CDN у сайта нет**: KaTeX, MathLive, D3, Math.js,
Chart.js, FullCalendar и html2canvas лежат в репозитории, в `static/vendor/`
([ADR 0070](adr/0070-vendor-browser-libraries.md)). Причина простая: когда
чужую сеть режут или она тормозит, сайт продолжает открываться, но формулы,
калькулятор, статистика и календарь остаются мёртвыми — снаружи это выглядит
как рабочий сайт, и потому хуже честного отказа.

**Руками на сервере делать не надо ничего.** Штатная выкатка `git pull` →
`docker compose build web` → `docker compose up -d web` тянет папку вместе с
кодом, а `collectstatic` в entrypoint раскладывает её как всю остальную
статику. Отдаёт эти файлы тот же nginx, что и прочую статику (см. ниже).

⚠️ Папки шрифтов (`katex-0.16.9/fonts/` — 60 файлов,
`mathlive-0.110.0/fonts/` — 20) обязаны быть целыми: `ManifestStaticFilesStorage`
разбирает CSS и **роняет сборку образа**, если хоть один упомянутый шрифт
отсутствует. Это не придирка, а способ узнать о пропаже до выкатки, а не после.

### Кто отдаёт статику

⚠️ **Это место проверяется отдельно, и вот почему.** В проекте стоит
WhiteNoise — Django умеет отдавать статику сам. Ошибись мы в `alias`
в nginx, запрос ушёл бы в `location /`, попал в Django, и файл всё равно
отдался бы. Страница выглядела бы правильной, а nginx при этом не работал
бы вовсе — и обнаружилось бы это только под нагрузкой. «Файл открылся»
доказательством не считается.

Доказательство — четыре независимых признака:

```bash
# 1. Заголовок-метка, который есть только у ответов nginx:
curl -sI https://weconomics.site/static/admin/css/nav_sidebar.dd925738f4cc.css | grep -i x-served-by
#    x-served-by: nginx-static

# 2. Запись в отдельном журнале nginx:
cd /srv/weconomics/app/deploy && docker compose exec nginx tail -2 /var/log/nginx/static_access.log

# 3. Контроль: в журнале gunicorn таких запросов НЕТ:
docker compose logs web | grep -c "GET /static/"     # 0

# 4. Контроль наоборот — как выглядит ответ WhiteNoise (мимо nginx):
docker compose exec web curl -sI -H 'Host: weconomics.site' \
  http://127.0.0.1:8000/static/admin/css/nav_sidebar.dd925738f4cc.css | head -3
#    Server: gunicorn      ← вот так выглядит «зелёное по неправильной причине»
```

### Как перезапустить

```bash
cd /srv/weconomics/app/deploy
docker compose ps                    # что живо и здорово ли
docker compose restart nginx         # одну службу
docker compose up -d                 # поднять всё, чего не хватает
docker compose down && docker compose up -d   # пересоздать всё
```

`docker compose down` **не трогает данные** — они в именованных томах.
Данные удаляет только `down -v`. Этот ключ здесь не нужен никогда.

### Где смотреть логи

```bash
cd /srv/weconomics/app/deploy
docker compose logs -f nginx         # живой поток
docker compose logs --tail=100 postgres
journalctl -u docker -n 50           # сам Docker
sudo journalctl -u weconomics-certbot.service -n 50   # продление сертификата
sudo tail -50 /var/log/auth.log      # входы и попытки входа
sudo fail2ban-client status sshd     # кого забанили
```

Логи контейнеров ротируются (10 МБ × 3 файла на контейнер) — диск они
не съедят.

---

## Сертификат

Let's Encrypt, на четыре имени (`weconomics.site`, `www.weconomics.site`,
`weconomics.ai`, `www.weconomics.ai`).

⚠️ **У аккаунта Let's Encrypt НЕ ЗАДАНА ПОЧТА** (`Email contact: none`,
проверено 07.09.2026 командой `docker compose run --rm certbot show_account`).
Следствий два, и оба надо знать.

Первое: в командах выпуска сертификата **не передавать `--email`** — его
значения не существует. Аккаунт уже зарегистрирован, certbot переиспользует
его молча; добавляйте `--non-interactive`, чтобы он не попытался спросить
почту и не повис в `tmux` без видимой причины.

Второе, важнее: **Let's Encrypt не пришлёт предупреждение об истечении.**
Обычно письмо приходит за 20 и за 7 дней до срока — это последняя сеть
безопасности на случай, если сломается таймер продления. Её у нас нет, и
продление сторожит только сам таймер. Проверять глазами:
`systemctl list-timers weconomics-certbot.timer`. Завести почту — решение
владельца, карточка в Notion.

```bash
cd /srv/weconomics/app/deploy
docker compose run --rm certbot certificates     # что есть и до какого числа
```

Команда расширения на добавленные имена (папка сертификата остаётся
`live/weconomics.site/` — это метка, не домен, nginx-пути менять не нужно):

```bash
cd /srv/weconomics/app/deploy
docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
  --cert-name weconomics.site --expand \
  -d weconomics.site -d www.weconomics.site -d weconomics.ai -d www.weconomics.ai
```

Продление автоматическое: systemd-таймер `weconomics-certbot.timer`
дважды в сутки (03:00 и 15:00 плюс случайная задержка до часа). После
продления nginx перечитывает конфигурацию.

```bash
systemctl list-timers weconomics-certbot.timer   # когда сработает
sudo systemctl start weconomics-certbot.service  # запустить прямо сейчас
```

⚠️ **Проверять продление только с `--dry-run`.** У Let's Encrypt лимит
примерно пять неудачных попыток в час на домен, и его легко исчерпать
отладкой, закрыв себе выдачу.

⚠️ **`certbot renew` не зависает, а спит.** При неинтерактивном запуске он
добавляет случайную задержку **до 8 минут** перед работой — это защита
серверов LE от одновременного наплыва. Выглядит как зависание на строке
`Processing ...`. Для ручного запуска задержку снимает
`--no-random-sleep-on-renew`.

---

## Что закрыто

- Вход по паролю по SSH — запрещён.
- Вход под root по SSH — запрещён.
- `ufw`: снаружи открыты **только 22, 80, 443**, остальное закрыто.
- `fail2ban`: 5 промахов за 10 минут → бан на час, дальше по нарастающей.
- Автоматические обновления безопасности включены.
- Порты базы и Redis наружу не опубликованы вовсе.

### ⚠️ Главная ловушка: Docker обходит ufw

Публикация портов в Docker (`ports: "5432:5432"`) пишет правила в iptables
**выше** правил ufw. Порт окажется открыт всему интернету, а `ufw status`
будет показывать, что всё закрыто. Базы, торчащие наружу, находят сканерами
за часы.

**Поэтому у `postgres` и `redis` секции `ports` нет вообще.** Они общаются
с другими службами по внутренней сети Docker `backend`, по именам
`postgres` и `redis`. Django в следующей сессии будет ходить туда же.

Если порт всё-таки понадобится для отладки — **только с явным адресом**:
`"127.0.0.1:5432:5432"`. Без `127.0.0.1` в начале порт открыт всем.

### ⚠️ Вторая ловушка: cloud-init возвращает вход по паролю

Файлы из `/etc/ssh/sshd_config.d/` перебивают основной `sshd_config`,
потому что `Include` стоит в его начале, а в OpenSSH выигрывает **первое**
встреченное значение. Cloud-init держит там `50-cloud-init.conf`
с `PasswordAuthentication yes` и может восстановить его при загрузке.

Закрыто тремя слоями, все три нужны:
1. `/etc/ssh/sshd_config.d/00-hardening.conf` — читается раньше по алфавиту;
2. сам `50-cloud-init.conf` переписан на `no`;
3. `/etc/cloud/cloud.cfg.d/99-disable-ssh-pwauth.cfg` — `ssh_pwauth: false`.

Проверить действующие значения (не то, что написано в файлах, а то, что
реально применяется):

```bash
sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin'
```

Должно быть `no` и `no`.

---

## Если сайт не отвечает

По порядку, сверху вниз.

**1. Сервер вообще жив?**
```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151 uptime
```
Не отвечает → веб-консоль Selectel, дальше пункт 6.

**2. Контейнеры на месте?**
```bash
cd /srv/weconomics/app/deploy && docker compose ps
```
Здоровый набор — ЧЕТЫРЕ службы в состоянии `Up ... (healthy)`:
`postgres`, `redis`, `web`, `nginx`. Кого-то нет
или `unhealthy` → `docker compose up -d`, затем `docker compose logs --tail=50 <служба>`.

**3. nginx отвечает изнутри?**
```bash
docker compose exec nginx wget -qO- http://127.0.0.1/healthz
```
Должно вернуть `ok`. Не возвращает → смотреть `docker compose logs nginx`.

**4. Конфигурация nginx валидна?**
```bash
docker compose exec nginx nginx -t
```
После любой правки конфигурации — сначала `nginx -t`, только потом
`nginx -s reload`. Перезагрузка со сломанным конфигом уронит сайт.

**5. Сертификат не истёк?**
```bash
echo | openssl s_client -connect weconomics.site:443 -servername weconomics.site 2>/dev/null | openssl x509 -noout -dates
```

**6. Не забанил ли fail2ban ваш собственный адрес?**

Симптом: SSH перестал пускать именно с вашей сети, при этом сайт открывается.
Через веб-консоль Selectel:
```bash
fail2ban-client status sshd                     # список забаненных
fail2ban-client set sshd unbanip <ваш-адрес>
```

**7. Место на диске не кончилось?**
```bash
df -h /; docker system df
```
Чистка неиспользуемого: `docker system prune -a` (образы и кеш; **тома
не трогает**).

---

## Обслуживание

**Обновления безопасности** ставятся сами. Но **автоматической перезагрузки
нет намеренно**: внезапный ребут уронил бы сайт. Поэтому обновления ядра
применяются вручную — примерно раз в месяц:

```bash
[ -f /var/run/reboot-required ] && cat /var/run/reboot-required
sudo reboot
```

После перезагрузки всё поднимается само: Docker включён в автозапуск,
у контейнеров `restart: unless-stopped`, ufw и fail2ban стартуют сами.
**Ручного прогрева нет** (с 17.09.2026): модель поиска грузится сама при
старте `search`, воркеры `web` читают корпус умного поиска с диска
(`MEDIA_ROOT/_cache`, том `media`) за секунды вместо сборки 20–25 с.
Проверка после перезагрузки:

```bash
cd /srv/weconomics/app/deploy
docker compose ps                                              # все healthy; search — до 4 минут
docker compose exec web curl -fsS http://search:8001/healthz   # "ok":true
docker compose logs web | grep 'корпус умного поиска'          # «с диска за N с» (первый раз после смены данных — «собран»)
```

**Проверено настоящей перезагрузкой 2026-08-21.** Через 53 секунды после
возвращения все четыре контейнера были `healthy`, ufw активен, fail2ban
активен, оба таймера (продление сертификата и бэкап) на месте, сайт отдавал
`200`, статику по-прежнему отдавал nginx (`x-served-by: nginx-static`),
цепочка `http → https` — один редирект, 505 задач в базе на месте.

---

## Бэкапы

Скрипт `deploy/backup.sh`, таймер systemd `weconomics-backup.timer`,
ежедневно в 03:20 МСК (плюс случайная задержка до 5 минут).

| Что | Как |
|---|---|
| Формат | `pg_dump -Fc -Z0` → `gzip -9` |
| Куда | `/srv/weconomics/backups/weconomics-ГГГГММДД-ЧЧММСС.dump.gz` |
| Права | каталог 700, файлы 600, владелец root |
| Хранить | 30 копий, лишние удаляются по имени (в нём дата) |
| Внешняя копия | `BACKUP_S3_*` в `.env`, **пока пусто** |

`-Z0` выключает встроенное сжатие `pg_dump`: формат `-Fc` сжимает сам, и без
`-Z0` файл сжимался бы дважды — gzip поверх сжатого не даёт почти ничего,
зато тратит время на каждом ночном прогоне.

Каждый прогон сразу же читает оглавление получившегося архива
(`pg_restore --list`). Дамп, который не читается, обнаруживают в тот день,
когда он нужен; эта проверка стоит доли секунды.

```bash
sudo /srv/weconomics/app/deploy/backup.sh          # снять копию прямо сейчас
systemctl list-timers weconomics-backup.timer      # когда сработает
sudo journalctl -u weconomics-backup.service -n 30 # что было в прошлый раз
sudo ls -la /srv/weconomics/backups/
```

⚠️ **Каталог копий закрыт от `makar` (права 700, владелец root).** Обычный
`ls /srv/weconomics/backups/*.dump.gz` под `sudo` не сработает: шаблон `*`
раскрывает НЕпривилегированная оболочка, ещё до `sudo`, и не видит каталога.
Правильно так: `sudo sh -c 'ls -1t /srv/weconomics/backups/*.dump.gz'`.

### ⚠️ Копии лежат у того же провайдера, что и сервер

**Правило проекта: бэкап живёт не у того же провайдера, что сервер.** Сейчас
оно НЕ выполнено. Копии рядом с сервером спасают от «уронили таблицу» и не
спасают ровно от того, ради чего бэкап и делают: провайдер потерял диск,
заблокировал аккаунт, сервер изъяли.

Скрипт умеет отправлять копию в S3-совместимое хранилище — заполнить
`BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY`,
`BACKUP_S3_SECRET_KEY` в `.env`, больше ничего не требуется. Пока они пусты,
скрипт печатает предупреждение на каждом прогоне. Карточка на подключение
хранилища заведена в Notion: это действие владельца, не Claude Code.

`aws-cli` в систему не установлен намеренно: он нужен только когда хранилище
подключат, и тогда приедет контейнером.

### Как восстановиться

**Бэкап, который ни разу не восстанавливали, бэкапом не является.**
Проверка сделана 2026-08-21 и вот её порядок — повторять примерно раз в квартал.

```bash
cd /srv/weconomics/app/deploy
LAST=$(sudo sh -c 'ls -1t /srv/weconomics/backups/*.dump.gz | head -1')
PGUSER=$(sudo sed -n 's/^POSTGRES_USER=//p' /srv/weconomics/.env | head -1)
PGDB=$(sudo sed -n 's/^POSTGRES_DB=//p' /srv/weconomics/.env | head -1)

# 1. Восстанавливаем во ВРЕМЕННУЮ базу, а не поверх боевой.
docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" \
  -c "CREATE DATABASE weconomics_restore_test OWNER $PGUSER;"
sudo gunzip -c "$LAST" | docker compose exec -T postgres \
  pg_restore -U "$PGUSER" -d weconomics_restore_test --no-owner --no-privileges

# 2. Сверяем число строк по ключевым таблицам (обе базы должны совпасть).
# 3. Удаляем временную базу.
docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" \
  -c "DROP DATABASE weconomics_restore_test;"
```

Результат проверки 2026-08-21 — расхождений ноль по восьми таблицам:

| Таблица | Боевая | Восстановленная |
|---|---|---|
| `problems_problem` | 505 | 505 |
| `problems_problempart` | 554 | 554 |
| `problems_topic` | 849 | 849 |
| `problems_tag` | 551 | 551 |
| `problems_source` | 23 | 23 |
| `problems_sourcereference` | 505 | 505 |
| `problems_user` | 3 | 3 |
| `django_migrations` | 68 | 68 |

⚠️ **Восстанавливать поверх боевой базы — только осознанно.** Для настоящей
аварии порядок другой: остановить `web`, переименовать боевую базу (а не
удалить — она ещё пригодится для разбора), создать пустую, восстановить,
поднять `web`.

⚠️ **После заливки данных с явными идентификаторами — счётчики.** В
PostgreSQL вставка строк с готовыми `id` не двигает последовательности, и
следующая обычная вставка падает с конфликтом ключа. У проекта есть команда
`manage.py fix_sequences` (по умолчанию только показывает, `--apply`
применяет), она проходит по всем 85 таблицам со счётчиком, включая 24
промежуточные таблицы связей многие-ко-многим. `loaddata` выравнивает
счётчики загруженных моделей сам, но полагаться на это нельзя: для `COPY`,
`psql -f` и восстановления из дампа это неверно.

---

## Мелочи, на которых легко споткнуться

- `/root` закрыт для `makar` (права 700). `[ -f /root/что-то ]` вернёт
  «нет» даже когда файл есть. Читать через `sudo`.
- Обрыв SSH **не убивает** контейнер, запущенный через `docker compose run`.
  Он останется работать и будет держать блокировку certbot. Лечится:
  `docker ps -aq --filter name=certbot-run | xargs -r docker rm -f`,
  затем `sudo find /srv/weconomics/certbot/conf -name '*.lock' -delete`.
- Долгие операции запускать в `tmux`, иначе обрыв связи их прервёт:
  `tmux new -s работа`, отцепиться `Ctrl+B`, потом `D`, вернуться `tmux a -t работа`.
- **HSTS включён на ПЯТЬ МИНУТ** (`max-age=300`), без `preload` и без
  `includeSubDomains`. Это не опечатка и не забывчивость: HSTS необратим
  со стороны сервера — пока у посетителя не истечёт запомненный срок,
  вернуть его на HTTP нельзя ничем. Пять минут дают живому посетителю ровно
  то же поведение и стоят ноль риска. Поднять до года — отдельная карточка
  в Notion, после недели работы сайта.
- `ps` в образе `web` нет (он на `python:3.13-slim`). Смотреть процессы —
  через `/proc`: `docker compose exec web python -c "..."` либо
  `docker stats`.
- В базе лежат **три учётки без паролей**: `weco_admin` (суперпользователь),
  `demo_teacher`, `demo_student`. Пароль назначает владелец командой
  `docker compose exec web python manage.py changepassword <логин>`. Две
  демонстрационные — **удалить перед бетой**, карточка заведена.

---

## Площадка dev.weconomics.ai

Второй сайт на том же сервере: **та же машина, те же боевые настройки, другая
база и другой адрес**. Открывается по паролю, показывает свежий `main`.

⚠️ **Зачем она есть.** 06.09.2026 при выкатке на прод всплыли два бага,
которых не могло быть ни локально, ни в тестах: `settings_production.py` без
`site_meta` (пустое меню) и `varchar(300)` на PostgreSQL. Оба — «прошло на
компьютере разработки, упало на бою». До появления площадки код нигде не жил
в боевых условиях до самого боя. Теперь живёт.

| Что | Значение |
|---|---|
| Адрес | `https://dev.weconomics.ai` (A-запись на тот же `135.106.181.151`) |
| Вход | пароль nginx (basic auth), логин `weco` |
| Что выкатывается | `main`, сам, после зелёного CI, проверка раз в 5 минут |
| Данные | копия боевого дампа **без единого человека** |
| Аккаунты | `dev-student`, `dev-teacher`, `dev-parent`, `dev-admin` |
| Компас-проект | `weconomics-dev` (боевой — `weconomics`) |
| Каталог | `/srv/weconomics/dev/` |

### Что где лежит

```
/srv/weconomics/dev/
├── app/                     # ВТОРОЙ клон репозитория, стоит на main
│   └── deploy/
│       ├── docker-compose.dev-site.yml   # ЗАПУСКАТЬ ОТСЮДА
│       ├── dev_autodeploy.sh             # таймер зовёт его раз в 5 минут
│       ├── dev_refresh.sh                # обновление данных, руками
│       └── dev_status.sh                 # «что сейчас на площадке»
├── .env                     # ПАРОЛИ ПЛОЩАДКИ. 600, makar. Образец —
│                            #   deploy/env.dev.example
├── autodeploy.log           # журнал выкаток: только удачи и отказы
└── autodeploy.failed        # метка «этот коммит уже падал» (может не быть)
```

⚠️ **Все команды площадки — из `/srv/weconomics/dev/app`, и только оттуда**,
и всегда с `-f deploy/docker-compose.dev-site.yml`. Боевые команды — из
`/srv/weconomics/app/deploy`, как и раньше. Перепутать каталоги — значит
перезапустить не тот сайт.

### Что общее с боем, а что своё

| Служба | Площадки | Почему |
|---|---|---|
| PostgreSQL | **общий контейнер, своя база** `weconomics_dev` | второй Postgres на 8 ГБ — лишний гигабайт ни за что |
| `search` | **общий**, когда появится | модель весит 2,12 ГБ, второй экземпляр запрещён (P0). ⚠️ На 07.09.2026 на бою НЕ РАЗВЁРНУТ вовсе — площадке безразлично: `SEMANTIC_SEARCH_ENABLED=0` у обоих, в сервис никто не ходит |
| nginx | **общий** | порт 443 на сервере один |
| Redis | **свой** (`redis-dev`) | номера баз (0 кэш, 1 сессии, 3 дуэли) зашиты в настройки; на общем Redis `cache.clear()` площадки — это `FLUSHDB`, и он разлогинил бы живых людей на бою |
| `web` / `ws` | **свои** (`web-dev`, `ws-dev`) | своя база, свой код, свои 2 воркера |

⚠️ **`web-dev` — это не «второй контейнер web», запрещённый правилом P0.**
Запрет касается второго процесса, мигрирующего **в одну и ту же базу**: они
идут без блокировки и развалят схему. У площадки база другая, и мигрирующий
процесс у каждой базы ровно один. Запрет остаётся в силе: второй `web` на
боевой базе по-прежнему нельзя.

⚠️ **Площадка ограничена по памяти, и это не украшение.** `web-dev` 900 МБ,
`ws-dev` 300 МБ, `redis-dev` 128 МБ — потолок 1,3 ГБ из 8. Без пределов
утечка на площадке отдала бы выбор жертвы OOM-killer-у ядра, а тот убивает
самый прожорливый процесс — то есть боевой `search`. Баг на площадке ронял бы
настоящий сайт. По той же причине `dev_autodeploy.sh` не начинает сборку,
если `free -m` показывает меньше 600 МБ available: сборка идёт в демоне
docker, вне контейнеров, и `mem_limit` её не ограничивает.

### Аккаунты площадки

Пароль у всех один, лежит в `DEV_ACCOUNTS_PASSWORD` в `/srv/weconomics/dev/.env`.
**В этом файле паролей нет и быть не должно.**

| Логин | Роль | Что на нём смотреть |
|---|---|---|
| `dev-student` | ученик | кабинет ученика, каталог, домашки, тренажёр |
| `dev-teacher` | репетитор | панель преподавателя, группа «dev-группа», работы |
| `dev-parent` | родитель | экран «Мои дети» (привязан к `dev-student`) |
| `dev-admin` | администратор | `/admin/` (is_staff + is_superuser) |
| — | **гость** | **аккаунт не нужен: гость = окно инкогнито** |

⚠️ **Гостю логина не заводится намеренно.** Гость на сайте — это в точности
разлогиненный браузер: каталог, задача и тренажёр открыты без входа. Логин
«dev-guest» был бы вошедшим пользователем с пустыми правами, то есть проверял
бы не то, что нужно.

`dev-student` состоит в группе `dev-группа` у `dev-teacher`, `dev-parent`
привязан к `dev-student`. Связи заводит `dev_scrub` — теми же механизмами,
что настоящая регистрация, а не своим способом.

### Автовыкатка: как она работает

Таймер `weconomics-dev-autodeploy.timer` раз в 5 минут запускает
`dev_autodeploy.sh`. Тот:

1. смотрит, какой хеш **работает в контейнере** (не какой лежит в клоне);
2. если он равен `origin/main` — выходит молча;
3. спрашивает GitHub, зелёный ли **CI** по этому хешу (без токена —
   репозиторий публичный). Прогон не завершён — ждёт следующего тика;
   красный — пишет в журнал и выходит;
4. `git merge --ff-only`, сборка образа с `GIT_SHA`, `up -d`, ожидание
   `healthy` до 180 с;
5. строка в `/srv/weconomics/dev/autodeploy.log`: `<дата> <sha7> ok` либо
   `<дата> <sha7> FAIL <причина>` с хвостом логов контейнера.

⚠️ **Это pull, а не push.** Выкатка из GitHub Actions потребовала бы дать
GitHub ключ на **запись** к серверу. Здесь сервер сам ходит наружу, а ключ
деплоя остаётся только на чтение.

⚠️ **Сломанный `main` площадку не гасит.** Сборка не трогает работающие
контейнеры: упала — площадка продолжает отвечать старым кодом. Упавший
коммит записывается в `autodeploy.failed` и больше не пробуется, иначе
сломанный `main` пересобирался бы каждые пять минут круглосуточно. Снять
запрет: `rm /srv/weconomics/dev/autodeploy.failed`.

⚠️ **«Всё свежее» в журнал не пишется.** Раз в пять минут — это 288 строк в
сутки, они утопили бы записи о настоящих выкатках. Каждый тик виден в
`journalctl -u weconomics-dev-autodeploy`.

```bash
/srv/weconomics/dev/app/deploy/dev_status.sh          # что сейчас на площадке
sudo systemctl stop weconomics-dev-autodeploy.timer   # остановить автовыкатку
sudo systemctl start weconomics-dev-autodeploy.timer  # включить обратно
sudo journalctl -u weconomics-dev-autodeploy -n 50    # каждый тик, включая тихие
/srv/weconomics/dev/app/deploy/dev_autodeploy.sh      # выкатить прямо сейчас
```

### Собрать площадку руками

Обычно этого делать не нужно — сборкой занимается автовыкатка. Нужно только
при первом запуске или после `docker system prune`:

```bash
cd /srv/weconomics/dev/app
docker compose -f deploy/docker-compose.dev-site.yml build   --build-arg GIT_SHA=$(git rev-parse --short=7 HEAD) web-dev
docker compose -f deploy/docker-compose.dev-site.yml up -d
```

⚠️ **`--short=7`, А НЕ ПРОСТО `--short`, И ЭТО НЕ ПРИДИРКА.** У `--short` без
числа длину выбирает сам git, и на этом репозитории он даёт **восемь** знаков.
`dev_autodeploy.sh` считает целевой хеш ровно семью (`--short=7`), поэтому
восьмизначный хеш в образе не сравняется с ним НИКОГДА — и автовыкатка будет
пересобирать площадку при каждом срабатывании таймера, то есть каждые пять
минут круглосуточно, на том же сервере, где живёт бой.

Поймано 07.09.2026 при первом же запуске: скрипт написал «выкачено» там, где
должен был написать «up to date». Обошлось одной лишней пересборкой — он сам
пересобрал образ уже со своими семью знаками, и с тех пор хеши сходятся.

### Обновить данные площадки

```bash
tmux new -s refresh                                   # операция долгая
/srv/weconomics/dev/app/deploy/dev_refresh.sh         # только ПЛАН
/srv/weconomics/dev/app/deploy/dev_refresh.sh --yes   # выполнить
```

Берёт самый свежий боевой дамп → пересоздаёт `weconomics_dev` → заливает →
миграции → `dev_scrub --yes` (все люди удаляются, заводятся четыре тестовых
аккаунта) → `fix_sequences --apply` → печатает числа.

⚠️ **Боевую базу скрипт не трогает.** К боевой он подключается только как к
«точке входа» `psql`: удалить базу, сидя в ней самой, нельзя.

⚠️ **У обоих скриптов есть страж.** Первым делом они читают `DATABASE_URL` из
`/srv/weconomics/dev/.env` и проверяют, что имя базы оканчивается на `_dev`.
Иначе — немедленный отказ. Причина: копии этих скриптов лежат и в **боевом**
клоне (они в репозитории), и запуск оттуда работал бы с боевой базой.

⚠️ **`dev_scrub` не запустится на бою.** Он требует `SITE_ENV=dev`, а в
боевом `.env` этой переменной нет вовсе (значение по умолчанию — `prod`).
Это его единственный предохранитель, и он же — причина, по которой
`SITE_ENV` вообще существует.

### Сертификат площадки

Выпускается один раз, дальше продлевается тем же таймером, что и боевой.

```bash
# 1. временный блок порта 80 (без него certbot не сможет пройти проверку,
#    а сразу добавить блок 443 нельзя: nginx не поднимется без сертификата
#    и уронит БОЙ — они в одном контейнере)
sudo cp /srv/weconomics/dev/app/deploy/nginx/available/dev-bootstrap.conf         /srv/weconomics/nginx/conf.d/dev-bootstrap.conf
cd /srv/weconomics/app/deploy
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload

# 2. проверка, что блок работает: ожидается 404 от nginx, НЕ 444 и НЕ 301
curl -sI http://dev.weconomics.ai/.well-known/acme-challenge/test | head -1

# 3. сам сертификат
docker compose run --rm certbot certonly --webroot -w /var/www/certbot   -d dev.weconomics.ai --keep-until-expiring --agree-tos --no-eff-email   --non-interactive
sudo ls /srv/weconomics/certbot/conf/live/dev.weconomics.ai/   # fullchain.pem privkey.pem
```

⚠️ **`--email` НЕ ПЕРЕДАЁТСЯ, и это не забывчивость.** У аккаунта Let's
Encrypt почты нет вовсе (см. раздел «Сертификат» выше). Аккаунт уже
зарегистрирован, certbot переиспользует его молча; `--non-interactive`
не даёт ему попытаться спросить почту и повиснуть в `tmux`.

⚠️ **Проверять только с `--dry-run`.** У Let's Encrypt лимит примерно пять
неудачных попыток в час на домен, и его легко исчерпать отладкой, закрыв
себе выдачу.

### Сменить пароль на вход

```bash
docker run --rm httpd:2.4-alpine htpasswd -nbB weco 'НОВЫЙ_ПАРОЛЬ' \
  | sudo tee /srv/weconomics/nginx/conf.d/htpasswd_dev > /dev/null
cd /srv/weconomics/app/deploy && docker compose exec nginx nginx -s reload
```

⚠️ **Файл называется `htpasswd_dev`, без `.conf`.** Каталог `conf.d`
подключён шаблоном `*.conf`: назови мы файл `htpasswd_dev.conf`, nginx
попытался бы разобрать хеш пароля как директивы и не поднялся бы вовсе,
уронив заодно **бой** — они в одном контейнере.

### Отличия от боя, о которых надо помнить

- **Статику отдаёт WhiteNoise внутри `web-dev`, а не nginx.** Заголовка
  `x-served-by: nginx-static` на площадке НЕ БУДЕТ, и это норма. Сделать как
  на бою значило бы примонтировать том площадки в **боевой** контейнер
  nginx — то есть править боевой compose ради площадки.
- **HSTS у площадки нет вовсе.** Он необратим со стороны сервера, а площадку
  открывают три человека, которым известен адрес.
- **Бэкапов у площадки нет.** Своих данных, которые нельзя потерять, на ней
  нет по определению: она пересоздаётся одной командой.

### Если площадка сломалась

Бой при этом работает: у них общие только PostgreSQL, `search` и nginx, и ни
одну из этих служб площадка не перезапускает.

```bash
cd /srv/weconomics/dev/app
docker compose -f deploy/docker-compose.dev-site.yml ps
docker compose -f deploy/docker-compose.dev-site.yml logs --tail=50 web-dev
docker compose -f deploy/docker-compose.dev-site.yml up -d          # поднять
docker compose -f deploy/docker-compose.dev-site.yml down           # погасить
```

`down` данных не трогает — они в именованных томах и в общей базе.
Погасить площадку целиком и надолго: `down` плюс
`sudo systemctl disable --now weconomics-dev-autodeploy.timer`.
---

## Что на сервере есть и чего ещё нет

**Есть:** база, Redis, Django под gunicorn (4 воркера), nginx с
проксированием и отдачей статики, сертификат с автопродлением, ежедневные
бэкапы с проверенным восстановлением, **5 095 задач** в базе.

**Ещё нет:**

- **корпус задач целиком** — сейчас 5 095 из 31 694. ⚠️ Число уточнено
  07.09.2026 при заливке боевого дампа на площадку; раньше здесь стояло 505
  (smoke-набор), и это устарело — данные доливались после;
- **раздел олимпиад пуст** — в боевой базе 0 записей `Olympiad`. Проверено
  той же заливкой: справочник на прод не заливали;
- **внешнее хранилище бэкапов** — копии у того же провайдера;
- **сервис поиска** — «мина №1», единственная оставшаяся из трёх. Модель
  2,12 ГБ должна жить в отдельном процессе, а не по копии на воркер. До тех
  пор `SEMANTIC_SEARCH_ENABLED=0`, поиск честно деградирует до поиска по
  словам ([ADR 0012](adr/0012-semantic-search-flag-off-in-prod.md));
- **KaTeX, D3, Math.js, MathLive, Chart.js, FullCalendar со своего сервера** —
  сейчас 30 внешних загрузок с `cdn.jsdelivr.net` и `cdnjs.cloudflare.com`;
- **CSP в боевом режиме** — сейчас только режим отчёта;
- **отдача загруженных файлов (media)** — сознательно нет ни на одном слое.
  22.08 выяснилось, что приложение туда УЖЕ кладёт (сдача задания с
  прикреплённым файлом — рабочая функция), а nginx до этой сессии отдавал
  том наружу публично — закрыто, `location /media/` теперь безусловно 404.
  Открывать — только после SEC-06 (лимиты, MIME-проверка, приватное
  хранилище, подписанные ссылки). Подробности — `docs/SECURITY.md`, раздел
  «Пользовательские файлы»;
- **HSTS на год** — сейчас пять минут.
