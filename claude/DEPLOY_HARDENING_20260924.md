# Выкатка «Укрепление беты 24.09» на бой

Ветка `fix/beta-hardening-20260924` → `main` (только после зелёного CI и
визуальной приёмки владельца). Команды — по порядку, на сервере под `makar`,
все `docker compose` — из `/srv/weconomics/app/deploy`. Стиль и ловушки —
`docs/SERVER.md`.

## 0. До выкатки — снять числа «было» (только чтение)

```bash
cd /srv/weconomics/app/deploy
docker compose exec -T web python manage.py shell < ../claude/diag_leaderboards_20260924.py
```

(Команда `rerank_spend` появится только после выкатки; числа «было» по поиску
уже записаны в `claude/JOURNAL_HARDENING_20260924.md`, фаза 3.)

## 1. Свежий бэкап

```bash
sudo /srv/weconomics/app/deploy/backup.sh
```

⚠️ С этой ветки скрипт кладёт рядом и архив тома media
(`weconomics-media-*.tar.gz`) — первый раз это займёт дольше обычного и
скачает образ `alpine:3.20`. Проверить, что в конце строка «копий на диске:
дампов N, архивов media M».

## 2. Код, образ, контейнеры

```bash
cd /srv/weconomics/app && git pull --ff-only
cd /srv/weconomics/app/deploy
docker compose build web
docker compose up -d web          # миграция problems.0077 накатится сама (5 новых полей)
docker compose up -d ws           # ws живёт из того же образа weconomics-web:latest
docker compose ps                 # web и ws — healthy
docker compose logs --tail 50 web | grep -i "0077\|error" || true
```

## 3. nginx: конфиг и страница 429

Конфиг сам не подтягивается (`docs/SERVER.md`, «Если менялась конфигурация
nginx»). Сначала сохранить действующий — для отката.

```bash
cp /srv/weconomics/nginx/conf.d/weconomics.conf /srv/weconomics/nginx/weconomics.conf.before-20260924
cp /srv/weconomics/app/deploy/nginx/available/django.conf /srv/weconomics/nginx/available/django.conf
cp /srv/weconomics/nginx/available/django.conf /srv/weconomics/nginx/conf.d/weconomics.conf
cp /srv/weconomics/app/deploy/nginx/html/429.html /srv/weconomics/nginx/html/429.html
cd /srv/weconomics/app/deploy
docker compose exec nginx nginx -t          # ТОЛЬКО если «test is successful» — дальше
docker compose exec nginx nginx -s reload
docker compose restart nginx                # ловушка 17.09: после пересоздания web nginx держит старый IP
```

Если `nginx -t` ругается — НЕ делать reload, вернуть старый файл:

```bash
cp /srv/weconomics/nginx/weconomics.conf.before-20260924 /srv/weconomics/nginx/conf.d/weconomics.conf
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

⚠️ Что меняется в nginx: `X-Forwarded-For` теперь ровно `$remote_addr`
(Django читает `X-Real-IP`), и лимиты скорости по адресу: страницы задач
60/мин, `*/api/` 120/мин, выгрузки подборок 6/мин, вход 10/мин, остальное
10/с. Локально `nginx -t` не прогонялся (Docker Desktop был выключен) —
проверка шагом выше обязательна.

## 4. Проверки после выкатки (только чтение)

```bash
curl -sI -A 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)' \
  'https://weconomics.ai/catalog/?q=%D1%81%D0%BF%D1%80%D0%BE%D1%81' | grep -i x-smart-search
#   ждём: X-Smart-Search: bot

curl -sI 'https://weconomics.ai/catalog/?q=%D1%81%D0%BF%D1%80%D0%BE%D1%81' | grep -i x-smart-search
#   ждём: X-Smart-Search: deferred (платит только скрипт страницы)

curl -s https://weconomics.ai/robots.txt
#   ждём строки: Disallow: /catalog/*?q=   Disallow: /catalog/*&q=   Disallow: /catalog/api/

curl -s https://weconomics.ai/catalog/problem/<id задачи с решением>/ | grep -c 'help-sol-tpl\|help-invite-tpl'
#   ждём: help-sol-tpl нет, help-invite-tpl есть (гостю решения в разметке нет)

cd /srv/weconomics/app/deploy
docker compose exec -T web python manage.py rerank_spend
#   сегодня: «потолок выбран — нет»; повторить вечером
docker compose exec -T web python manage.py scrape_report
docker compose exec -T web python manage.py shell < ../claude/diag_leaderboards_20260924.py
```

Через сутки: `rerank_spend` — в столбце «потолок выбран» «нет»; в админке
«Расход на ИИ» → вид `search_rerank` — строки только в часы, когда ищут люди.

## 5. Откат

```bash
cd /srv/weconomics/app && git log --oneline -3          # запомнить прежний коммит
git checkout <прежний коммит>        # отсоединённый HEAD; вернуться потом: git checkout main
cd deploy && docker compose build web && docker compose up -d web ws
cp /srv/weconomics/nginx/weconomics.conf.before-20260924 /srv/weconomics/nginx/conf.d/weconomics.conf
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload && docker compose restart nginx
```

⚠️ Миграция 0077 только ДОБАВЛЯЕТ поля — старый код с ними работает, откатывать
схему не нужно (и `migrate --fake` без владельца нельзя, P0).

## 6. Владельцу — вне выкатки

- Завести внешнее хранилище и вписать `BACKUP_S3_*` в `/srv/weconomics/.env` —
  тогда наружу поедут и дамп, и архив media.
- Жёсткие лимиты расходов в кабинетах провайдеров ИИ (страховка поверх
  `AI_DAILY_COST_CAPS`).
- Новые переменные `.env` (все необязательны, умолчания в коде):
  `CATALOG_CHECK_DAILY_CAP_USD`, `CATALOG_OCR_DAILY_CAP_USD`,
  `HOMEWORK_PLAN_DAILY_CAP_USD` (по $1), `SMART_SEARCH_QUOTA_VISITOR/USER/IP`
  (40/80/150), `SMART_SEARCH_RERANK_CACHE_SECONDS` (86400),
  `SCRAPE_QUOTA_IP_HOUR/DAY` (150/600), `SCRAPE_QUOTA_USER_HOUR/DAY` (300/1000),
  `SCRAPE_GUARD_ENABLED` (1).
