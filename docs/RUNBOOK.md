> **Владелец:** Claude Code
> **Обновлён:** 2026-09-02 (сессия «Wecon Rush — подготовка к выкатке»:
> `## Деплой` больше не «хостинг не выбран», выкатка переписана под
> `--bank-only`)
> **Статус:** актуален

# Эксплуатация

Что здесь: как выкатить, как залить данные, как восстановиться, что делать при
инциденте. Устройство системы — в [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Локальный запуск

```bash
./venv/bin/python manage.py runserver          # macOS
venv/Scripts/python.exe manage.py runserver    # Windows
```

Терминал напишет `Starting development server at http://127.0.0.1:8000/` — значит
сайт работает. **Окно не закрывать**, пока пользуетесь сайтом. Остановить —
`Ctrl + C` в том же окне.

Сайт: http://127.0.0.1:8000/ · Админка: `/admin/`
Наполнить примерами: `manage.py seed_demo` (идемпотентна, дублей не делает).

### Что внутри — для справки

| Где | Что |
|---|---|
| `config/` | настройки проекта |
| `problems/models.py` | описание всех сущностей: задача, источник, тема и прочее |
| `problems/admin.py` | как это выглядит в админке |
| `db.sqlite3` | сама база — один файл со всеми задачами |
| `venv/` | библиотеки; трогать не нужно |

В админке раздел **Problems**: «Задачи» (кнопка «Добавить задачу» справа сверху),
плюс справочники — темы, теги, источники, файлы, пользователи. Добавить ученика:
«Пользователи» → «Добавить», роль «Ученик».

⚠️ **Пароль администратора сменить до показа кому-либо.** В админке:
«Пользователи» → `admin` → ссылка на смену пароля внизу. Дев-пароли публично
известны, поэтому есть команда `lockdown_dev_accounts` — см. ниже.

⚠️ `runserver --noreload` **не перечитывает python-код**: правишь `views.py` во
время прогона — перезапусти сервер. Шаблоны при этом перечитываются на каждый
запрос, и расхождение выглядит как мистика.

⚠️ **Django кэширует шаблоны в памяти процесса.** Долго живущий `runserver`
отдаёт старую версию шаблона даже при жёстком обновлении браузера. Симптом
«правка не появляется» лечится перезапуском сервера, а не F5.

---

## Деплой

⚠️ **Этот раздел устарел с 2026-08.** Хостинг выбран и работает: Selectel
VDS, `weconomics.site` / `weconomics.ai`, Docker Compose с nginx/Django/
Redis/PostgreSQL. Что где лежит, как подключиться, как обновить код, как
устроены службы и откат — весь этот раздел переехал целиком в
[docs/SERVER.md](SERVER.md). Раздел «Выкатка Wecon Rush» ниже — про
конкретно ЭТУ ветку (игра, `ws`, банк задач); общий порядок обновления
кода и nginx — в SERVER.md.

Что раньше обеспечивал Render (прежний, ныне отключённый хостинг) и
чек-лист переезда на новый — [docs/MIGRATION-CHECKLIST.md](MIGRATION-CHECKLIST.md),
справочно.

**Проверка после выката:** открыть главную, `/catalog/`, страницу любой
задачи — раздел «Обновить сайт до свежего кода» в
[docs/SERVER.md](SERVER.md) даёт точные команды и что смотреть.

---

## Данные: заливка в прод

Внешнее `loaddata` непригодно (по одному INSERT на объект по медленному
внешнему каналу — часы и обрывы). Рабочий способ — `bulk_create` локально
против внешней базы.

⚠️ **Если заливаете БАНК ЗАДАЧ на прод, где ещё нет учётных записей и работ
учеников (первая заливка, репетиция, восстановление с нуля) — используйте
`dump_for_deploy --bank-only`, а не команду без флага ниже.** Без флага
дамп несёт также `Submission`, `TeacherFeedback`, `AssignmentItem` и весь
слой ученик↔преподаватель — решением владельца от 03.09 (152-ФЗ) это на
прод не заливается. Точные команды, включая заливку изнутри контейнера
`web` — раздел «Выкатка Wecon Rush», шаг 4.

Раздел ниже описывает ОБЩИЙ механизм (полный дамп, для последующих
регулярных обновлений корпуса на уже живом проде, где заливка идёт по
внешнему `DATABASE_URL`, а не изнутри контейнера).

```bash
# 1. собрать порционные gzip-фикстуры (исключают embedding, чистят NUL-байты)
./venv/bin/python manage.py dump_for_deploy --outdir deploy_fixtures --chunk 2000
gzip -f deploy_fixtures/*.json

# 2. залить (ignore_conflicts → идемпотентно)
SECRET_KEY=любой \
DATABASE_URL="<EXTERNAL_DB_URL>?sslmode=require" \
DJANGO_SETTINGS_MODULE=config.settings_production \
./venv/bin/python manage.py bulk_load_fixtures --dir deploy_fixtures
```

`EXTERNAL_DB_URL` — строка подключения к боевой базе; где её брать на новом
хостинге, пока не выбранном, — см. [MIGRATION-CHECKLIST.md](MIGRATION-CHECKLIST.md).

### ⚠️ Две мины, на которых уже подрывались

**1. `bulk_load_fixtures` только ВСТАВЛЯЕТ.** `ignore_conflicts=True` молча
пропускает записи, которые уже есть по pk. **Правки в существующих задачах на
прод так не попадают, сколько ни перезаливай.** Именно поэтому результат
ИИ-чистки ILE сначала не доехал.

Для обновления существующих — `update_prod_problems`: точечный `bulk_update` по
списку id, пересобирает подпункты, задачи с привязанными `Hint` пропускает,
работает одной транзакцией, поддерживает `--dry-run`.

Порядок: (1) бэкап, (2) `--dry-run`, (3) боевой прогон.

**2. Отставшие sequence в PostgreSQL.** `bulk_load_fixtures` грузит строки с
явными id, но **не двигает счётчик таблицы**. Потом первая же вставка без явного
id получает занятый номер → `UniqueViolation`. На SQLite не воспроизводится,
поэтому локально проблемы не видно.

### ✅ Обязательный шаг после любой заливки фикстур: `fix_sequences`

Раньше здесь стоял ручной разбор счётчиков по двум таблицам. Теперь есть
команда, которая проходит по **всем** — 85 таблиц со счётчиком, включая
24 промежуточные таблицы связей «многие ко многим». У них свой `id` со своим
счётчиком, отстать он может так же, а заметить труднее: модели с таким именем
в коде нет.

```bash
# 1. посмотреть (по умолчанию НИЧЕГО не меняет)
DATABASE_URL="<EXTERNAL_DB_URL>?sslmode=require" \
DJANGO_SETTINGS_MODULE=config.settings_production SECRET_KEY=любой \
./venv313/bin/python manage.py fix_sequences

# 2. выровнять
DATABASE_URL="<EXTERNAL_DB_URL>?sslmode=require" \
DJANGO_SETTINGS_MODULE=config.settings_production SECRET_KEY=любой \
./venv313/bin/python manage.py fix_sequences --apply

# 3. проверить: повторный холостой прогон обязан сказать
#    «отставших счётчиков нет»
```

Команда печатает, какие счётчики сдвинуты и на сколько — вид вывода:

```
Проверено таблиц со счётчиком: 85

Отстают счётчики (1):

  problems_topic  выдаст 1000  занято до 900001  отставание 899002

Холостой прогон: ничего не изменено. Повторите с --apply, чтобы выровнять.
```

⚠️ **Порядок именно такой: заливка → `fix_sequences --apply` → и только потом
пускать людей.** Между заливкой и выравниванием сайт выглядит рабочим, а первая
же попытка создать задачу, сдать работу или оставить комментарий падает с
`UniqueViolation`. Ломается не заливка, а обычное действие человека — и
виноватым выглядит оно, а не заливка, прошедшая неделю назад.

⚠️ **На SQLite команда откажется работать, и это правильно.** У SQLite
отставших счётчиков не бывает — он выдаёт `max(rowid) + 1`. Проверить
поведение локально можно только против PostgreSQL:
`--settings=config.settings_test_pg` (см. [TESTING.md](TESTING.md)).

Команда покрыта тестом `problems/tests/test_fix_sequences.py`. Тест устроен
так, что **краснеет, если `fix_sequences` не вызвать** — иначе он был бы
зелёным и на сломанной команде.

---

## Выкатка Wecon Rush

> Репетиция «только банк» проведена на ЧИСТОЙ PostgreSQL 17 (сессия
> «Wecon Rush — подготовка к выкатке», 02.09; предыдущая репетиция полного
> дампа — сессия «закрытие», фаза 8). Времена ниже замерены, а не оценены.
>
> **Три решения владельца приняты 03.09 (в сессии не обсуждаются):**
> 1. На прод заливается **полный банк задач, и только банк** — без работ
>    учеников, назначений, комментариев преподавателя, событий, результатов
>    игр (152-ФЗ). Заливка — командой `dump_for_deploy --bank-only` (шаг 4).
> 2. `GAME_GENERATED_ENABLED` — **выключен** (`config/settings_production.py`).
>    Шаг 6 (генерация сгенерированных вопросов) **пропускается**.
> 3. `GAME_FIGURE_ENABLED` («График») — **выключен** (тот же файл).
>
> Порядок ниже написан так, что оба флага и способ заливки — по одной
> строке-развилке на шаг, не по всему документу.

Игра ссылается на `Problem` по внешнему ключу. **Без банка на проде игры
нет:** `build_game_pool` соберёт пул из тех задач, что есть, и на 505
smoke-задачах он выйдет крошечным.

### Порядок

```bash
# 0. БЭКАП. Первым шагом и без исключений.
cd /srv/weconomics/app/deploy
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
    > /srv/weconomics/backups/before_rush_$(date +%Y%m%d_%H%M).dump

# 1. Код.
cd /srv/weconomics/app
git pull --ff-only

# 2. Образ. Один на оба сервиса: ws использует тот же weconomics-web:latest.
cd deploy
docker compose build web

# 3. Миграции — ОДНИМ контейнером. Их накатывает web при старте.
docker compose up -d web
docker compose logs -f web | head -40     # дождаться «gunicorn…»
```

**4. Банк — только банк (`--bank-only`, решение 1 выше).** Три подшага:
выгрузка локально из канона `db.sqlite3`, передача на сервер, заливка
изнутри контейнера `web` (этот путь не зависит от VPN владельца — заливка
идёт по внутренней сети Docker, а не по внешнему `DATABASE_URL`).

```bash
# 4а. ЛОКАЛЬНО на Windows (Git Bash), из корня репозитория — канон db.sqlite3.
venv313/Scripts/python.exe manage.py dump_for_deploy --bank-only \
    --outdir deploy_fixtures_bank --chunk 2000
gzip -f deploy_fixtures_bank/*.json
```

```bash
# 4б. Передача на сервер. Каталог фикстур создаём заранее — scp его сам
#     не создаст. Ключ и адрес — docs/SERVER.md, раздел «Как подключиться».
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151 \
    mkdir -p /srv/weconomics/backups/fixtures
scp -i ~/.ssh/id_ed25519_weconomics deploy_fixtures_bank/*.json.gz \
    makar@135.106.181.151:/srv/weconomics/backups/fixtures/
```

```bash
# 4в. НА СЕРВЕРЕ, из /srv/weconomics/app/deploy. bulk_load_fixtures читает
#     .json.gz сам (распаковку внутри не гонять отдельно). Файлы копируются
#     ВНУТРЬ контейнера — у web нет volume-монтирования backups/, поэтому
#     `docker compose cp`, а не прямой --dir на хостовый путь.
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
cd /srv/weconomics/app/deploy
docker compose exec -T web mkdir -p /tmp/bank_fixtures
docker compose cp /srv/weconomics/backups/fixtures/. web:/tmp/bank_fixtures
docker compose exec -T web python manage.py bulk_load_fixtures --dir /tmp/bank_fixtures
docker compose exec -T web python manage.py fix_sequences --apply
docker compose exec -T web python manage.py fix_sequences   # холостой — «отставших нет»
docker compose exec -T web rm -rf /tmp/bank_fixtures
```

```bash
# 5. Пул игры.
docker compose exec -T web python manage.py build_game_pool

# 6. Сгенерированные вопросы — ПРОПУСКАЕТСЯ (решение 2 выше:
#    GAME_GENERATED_ENABLED=False на проде). Строка ниже — только для
#    памяти, если владелец решение пересмотрит:
# docker compose exec -T web python manage.py generate_game_questions \
#     --per-archetype 100 --confirm

# 7. WebSocket дуэли.
docker compose up -d ws
docker compose ps ws                       # healthy

# 8. nginx — ⚠️⚠️ С 07.09.2026 ЭТОТ ШАГ ВСЛЕПУЮ ВЫПОЛНЯТЬ НЕЛЬЗЯ.
#    В активном конфиге сервера живёт ЕЩЁ И блок площадки
#    dev.weconomics.ai, дописанный руками. Копирование django.conf
#    поверх сотрёт площадку целиком. Сначала сверить:
#        diff /srv/weconomics/app/deploy/nginx/available/django.conf #             /srv/weconomics/nginx/conf.d/weconomics.conf
#    Файлы совпали — копировать не нужно вовсе (так было 12.09.2026).
#    Разошлись — переносить ИМЕННО изменившиеся боевые строки, а блок
#    площадки в конце файла оставлять на месте.
#
#    ⚠️ КОНФИГУРАЦИЯ НЕ ПОДТЯГИВАЕТСЯ САМА ИЗ КЛОНА, копируем явно
#    (та же ловушка, что в SERVER.md, «Обновить сайт до свежего кода»).
#    В этой ветке файл поменялся (добавлен блок location /ws/ — иначе
#    дуэли уходят к gunicorn, который про сокеты не знает), и без этого
#    шага изменение до сервера не доедет, сколько ни катай web.
cp /srv/weconomics/app/deploy/nginx/available/django.conf \
    /srv/weconomics/nginx/available/django.conf
cp /srv/weconomics/nginx/available/django.conf \
    /srv/weconomics/nginx/conf.d/weconomics.conf
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

### Smoke после выкатки

```bash
# страница игры
curl -fsS -o /dev/null -w '%{http_code}\n' https://weconomics.site/game/

# лидерборд отвечает JSON
curl -fsS 'https://weconomics.site/game/api/leaderboard/?mode=blitz' | head -c 200

# живость ASGI-процесса (без входа, без базы)
curl -fsS https://weconomics.site/ws/health/          # ws ok

# один забег целиком: старт, вопрос, ответ
curl -fsS -c /tmp/rush.jar 'https://weconomics.site/game/api/session/start/?mode=blitz'
curl -fsS -b /tmp/rush.jar  https://weconomics.site/game/api/question/
```

⚠️ **`/ws/health/` проверять обязательно.** gunicorn может отвечать, а
daphne лежать: сайт при этом полностью живой, а дуэль молча превращается в
асинхронную. Заметил бы это только игрок посреди забега.

### Что проверить глазами

- `/game/` — карточки режимов, числа под ними, лидерборд справа;
- один забег в Блице до конца: очки, жизни, экран итогов;
- `/game/duel/new/` из-под двух разных пользователей в двух браузерах:
  полоса соперника, обратный отсчёт, реакции;
- карточка ссылки: отправить `https://weconomics.site/game/` в мессенджер
  и посмотреть превью (`og:image` берётся из
  `game/static/game/og_default.png`).

### Откат каждого шага

| Шаг | Откат |
|---|---|
| 7 (`ws`) | `docker compose stop ws` — дуэль становится асинхронной, сайт цел |
| 8 (nginx) | `git checkout -- deploy/nginx` на сервере, затем `nginx -t` и reload |
| 6 (генерация) | пропущен решением владельца — откатывать нечего; если решение пересмотрят и шаг всё же выполнят — `docker compose exec -T web python manage.py purge_generated` |
| 5 (пул) | `build_game_pool` идемпотентен: повторный прогон пересобирает |
| 4 (банк) | восстановление из дампа шага 0; фикстуры на сервере — `/srv/weconomics/backups/fixtures/`, пересобрать заново можно тем же `dump_for_deploy --bank-only` локально |
| 3 (миграции) | `migrate game 0012` и `migrate problems 0046` откатывают то, что добавила эта ветка |
| 1–2 (код) | `git checkout <прежний хеш>` + `docker compose build web` + `up -d web ws` |

Полный откат к заглушке — раздел «Откат» в [SERVER.md](SERVER.md).

### Времена, замеренные на репетиции

Репетиция «только банк» (`--bank-only`) шла на локальной машине против
отдельной чистой базы PostgreSQL 17 в том же контейнере
`docker-compose.dev.yml` (сессия «Wecon Rush — подготовка к выкатке»,
02.09); на сервере числа будут другими, но порядок величин тот же. Шаги
6 (`generate_game_questions`) и «график» (`generate_figure_questions`) в
эту репетицию не входят — оба флага на проде выключены (решения 2 и 3
выше), и на сервере эти команды не запускаются вовсе.

| Шаг | Время |
|---|---|
| Миграции с нуля (все приложения) | 13,6 с |
| `makemigrations --check` | 1,8 с |
| Выгрузка банка `--bank-only` из канона `db.sqlite3` | 3 мин 22 с |
| `bulk_load_fixtures` в чистую базу | 28,8 с |
| `fix_sequences --apply` | 1,7 с |
| `fix_sequences` холостой («отставших нет») | 1,5 с |
| `build_game_pool` | 5,6 с |

Числа сошлись с локальной базой точно, до единицы: 41 307 задач, пул
4 751 вопрос (совпадает разбивка и по типам — 3 468 single / 589 boolean /
630 multi / 64 numeric, и по источникам — books 3 035, ap 1 454, vsosh 216,
ieo 42, без источника 4). Во всех 50 таблицах вне банка (пользователи,
`Submission`, `TeacherFeedback`, назначения, группы, события, результаты
игр, очереди ревью и так далее — полный список см. коммит «Фаза 1» этой
сессии) — 0 строк.

⚠️ **Выгрузка занимает больше, чем всё остальное вместе.** Планируя окно,
считайте по ней, а не по миграциям.

---

## Бэкап и восстановление

Встроенный бэкап хостинга — не гарантия (на прежнем free-тарифе Render его не
было вовсе). Делаем свои независимо от того, что даёт хостинг:

```bash
# бэкап боевой базы (pg_dump ставится через `brew install libpq`)
pg_dump "<EXTERNAL_DB_URL>?sslmode=require" -Fc -f prod_backup_$(date +%Y%m%d_%H%M).dump
```

⚠️ **Дамп не коммитить.** `.gitignore` закрыт от `*.dump` и `prod_backup_*`;
один такой дамп уже лежит в истории, см. [SECURITY.md](SECURITY.md).

Локальная база — просто файл: `cp db.sqlite3 backups/db_$(date +%Y%m%d).sqlite3`.
Перед любой массовой правкой корпуса бэкап обязателен (см. [DATA.md](DATA.md)).

---

## Учётные записи на проде

Render (отключён 2026-08) не давал shell на бесплатном тарифе, поэтому команды
ниже написаны для запуска локально против внешней базы. На новом хостинге
проверить: если shell доступен — выполнять их может быть проще прямо там.

```bash
# создать суперпользователя
DATABASE_URL="<EXTERNAL_DB_URL>?sslmode=require" \
DJANGO_SETTINGS_MODULE=config.settings_production SECRET_KEY=любой \
./venv/bin/python manage.py createsuperuser

# погасить дев-аккаунты (сначала без --apply — покажет, что найдено)
DATABASE_URL="<EXTERNAL_DB_URL>?sslmode=require" \
DJANGO_SETTINGS_MODULE=config.settings_production SECRET_KEY=любой \
./venv/bin/python manage.py lockdown_dev_accounts --apply
```

Новые пароли печатаются один раз в терминал и нигде не сохраняются — скопировать сразу.

---

## Инциденты

⚠️ Здесь раньше стояли пункты «Сайт не отвечает» и «Деплой `Timed Out`» —
описывали конкретные лимиты Render (90-дневная бесплатная PostgreSQL, сон
после 15 минут, скан порта ~3 минуты). Render отключён, эти цифры к новому
хостингу отношения не имеют — убрал, актуальную диагностику для нового
хостинга завести после переезда.

**Петля перезапусков.** Тяжёлая фоновая операция душит `gunicorn` на общем CPU,
health-чек падает. Останавливаем операцию, а не увеличиваем таймаут — это не
зависит от хостинга.

**`UniqueViolation` при вставке.** Отставший sequence — см. мину 2 выше.

**Правки не доехали на прод.** Использовали `bulk_load_fixtures` там, где нужен
`update_prod_problems` — см. мину 1 выше.

---

## Если GitHub или PyPI недоступны

⚠️ **Это инструкция, а не описание сделанного. Зеркало пока не заведено** —
работа ждёт решения владельца, карточка в Notion «Задачи».

Риск конкретный: код лежит в приватном репозитории на GitHub, зависимости
ставятся с PyPI, а CI работает на раннерах GitHub. Любой из трёх может стать
недоступен — по санкциям, по блокировке или просто потому, что упал. Тогда
встают сразу и разработка, и выкатка.

### Второй remote: GitVerse

[GitVerse](https://gitverse.ru) — российский хостинг репозиториев.
Заводим зеркало и пушим **в оба места одной командой**:

```bash
# 1. добавить второй адрес тому же remote `origin`
git remote set-url --add --push origin git@github.com:malinovskiy-makar/qls.git
git remote set-url --add --push origin git@gitverse.ru:<логин>/qls.git

# 2. проверить, что адресов стало два
git remote -v          # у origin должно быть ДВА push-адреса

# 3. дальше всё как обычно — уходит в оба
git push origin main
```

⚠️ **`set-url --add --push` первым вызовом ЗАМЕНЯЕТ адрес, а не добавляет.**
Поэтому GitHub перечислен явно первой строкой. Пропустить её — значит остаться
с одним GitVerse и узнать об этом в тот день, когда понадобится GitHub.

⚠️ **`git pull` тянет только с первого адреса.** Двойной push не делает
зеркало равноправным: это именно резервная копия. Переключаться на GitVerse
как на основной — отдельное действие (`git remote set-url origin ...`).

Прежняя выкатка на Render была привязана к GitHub (авто-деплой по пушу). Пока
GitVerse — только хранилище кода; устройство выкатки на новом хостинге ещё не
выбрано — останется ли она привязана к GitHub, решится вместе с выбором
хостинга (переезд на российский сервер и так в планах, см.
[MIGRATION-CHECKLIST.md](MIGRATION-CHECKLIST.md)).

### Локальный кеш PyPI

Локи (`requirements/*.txt`) фиксируют версии, но не сами файлы. Если PyPI
недоступен, `pip install` не соберёт окружение даже по локу.

```bash
# заранее: скачать все колёса боевого лока в папку
./venv313/bin/python -m pip download -r requirements/base.txt -d wheelhouse

# в день, когда PyPI недоступен: поставить только из папки
./venv313/bin/python -m pip install --no-index --find-links=wheelhouse \
    -r requirements/base.txt
```

`--no-index` обязателен: без него pip всё равно пойдёт в сеть и будет ждать
таймаута по каждому пакету.

⚠️ **Колёса зависят от платформы и версии Python.** Скачанные на Windows не
поставятся на Linux-сервер. Для выкатки нужен `pip download` с
`--platform manylinux2014_x86_64 --python-version 3.13 --only-binary=:all:`,
и то не всё соберётся — часть пакетов приезжает только исходниками.

⚠️ **Папку `wheelhouse` в репозиторий не класть.** Это сотни мегабайт
двоичных файлов, которые git будет хранить вечно; в проекте уже есть
незакрытая карточка про дамп базы, попавший в историю.
