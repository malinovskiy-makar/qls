> **Владелец:** Claude Code
> **Обновлён:** 2026-08-18
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

Сайт: http://127.0.0.1:8000/ · Админка: `/admin/`
Наполнить примерами: `manage.py seed_demo` (идемпотентна, дублей не делает).

⚠️ `runserver --noreload` **не перечитывает python-код**: правишь `views.py` во
время прогона — перезапусти сервер. Шаблоны при этом перечитываются на каждый
запрос, и расхождение выглядит как мистика.

⚠️ **Django кэширует шаблоны в памяти процесса.** Долго живущий `runserver`
отдаёт старую версию шаблона даже при жёстком обновлении браузера. Симптом
«правка не появляется» лечится перезапуском сервера, а не F5.

---

## Деплой

Пуш в `main` → Render выкатывает сам за 2–4 минуты.

```bash
git push origin main
```

**Откат:** Render → сервис `qls-platform` → Events/Deploys → Rollback на
предыдущий деплой.

**Проверка после выката:** открыть главную, `/catalog/`, страницу любой задачи.
Первый запрос после сна идёт ~30 секунд — это норма free-tier, не авария.

---

## Данные: заливка в прод

Внешнее `loaddata` непригодно (по одному INSERT на объект через канал во
Франкфурт — часы и обрывы). Рабочий способ — `bulk_create` локально против
внешней базы.

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

`EXTERNAL_DB_URL` — Render → `qls-db` → Connections → External Database URL.

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

`update_prod_problems` выравнивает sequence для `ProblemPart`. У остальных
таблиц счётчики всё ещё отстают — **выровнять перед следующей крупной заливкой
новых записей** (`manage.py sqlsequencereset problems` против прода).

Диагностика состояния счётчиков (только чтение):

```bash
DATABASE_URL="<EXTERNAL_DB_URL>?sslmode=require" \
DJANGO_SETTINGS_MODULE=config.settings_production SECRET_KEY=x \
./venv/bin/python manage.py dbshell -- -c \
"SELECT 'part_seq' t, last_value v FROM problems_problempart_id_seq
 UNION ALL SELECT 'part_max', max(id) FROM problems_problempart
 UNION ALL SELECT 'prob_seq', last_value FROM problems_problem_id_seq
 UNION ALL SELECT 'prob_max', max(id) FROM problems_problem;"
```

---

## Бэкап и восстановление

На free-тарифе Render встроенных бэкапов **нет** — делаем сами.

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

Shell на free-тарифе недоступен, поэтому всё — локально против внешней базы.

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

**Сайт не отвечает.** Сначала проверить, не истёк ли срок бесплатного PostgreSQL
(90 дней) и не спит ли сервис. Render → Events покажет причину. Первый запрос
после сна — до 30 секунд.

**Деплой `Timed Out`.** В `startCommand` появилась долгая операция до `gunicorn`.
Порт обязан открыться за ~3 минуты. Переносим тяжёлое в отдельный ручной прогон.

**Петля перезапусков.** Тяжёлая фоновая операция душит `gunicorn` на общем CPU,
health-чек падает. Останавливаем операцию, а не увеличиваем таймаут.

**`UniqueViolation` при вставке.** Отставший sequence — см. мину 2 выше.

**Правки не доехали на прод.** Использовали `bulk_load_fixtures` там, где нужен
`update_prod_problems` — см. мину 1 выше.
