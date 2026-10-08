> **Владелец:** Claude Code
> **Обновлён:** 2026-10-09 (сессия «Сайт не встаёт»)
> **Статус:** актуален до выкатки gthread на бой

# Памятка выкатки: gunicorn gthread (4 воркера × 8 потоков)

Что меняется: вопросы к ИИ больше не занимают весь сайт. Было 4 места на весь
сайт, станет 32. Решение и замеры — [ADR 0140](adr/0140-gunicorn-gthread.md),
подробности — [SERVER.md](SERVER.md), «Воркеры и потоки».

Команды выполняет владелец сам. Подключение из PowerShell на Windows:

```bash
ssh -i $env:USERPROFILE\.ssh\id_ed25519_weconomics makar@135.106.181.151
```

Дальше все команды — на сервере, из каталога `/srv/weconomics/app/deploy`:

```bash
cd /srv/weconomics/app/deploy
```

---

## а) Проверки до выкатки

```bash
free -h
```
**Должно получиться:** в строке `Mem:` столбец `available` не меньше 1,5 Gi.
Меньше — не выкатывать, написать в чат.

```bash
docker exec weco-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "show max_connections"'
```
**Должно получиться:** число, обычно `100`. **Меньше 80 — остановиться и
написать в чат**: у web станет до 32 соединений вместо 4, плюс площадка dev
(до 16) и служба `ws`.

```bash
docker exec weco-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select datname, count(*) from pg_stat_activity group by 1 order by 2 desc"'
```
**Должно получиться:** несколько строк с небольшими числами (обычно до 20 в
сумме). Запишите — сравним после выкатки.

```bash
grep -E "^GUNICORN" /srv/weconomics/.env
```
**Должно получиться:** `GUNICORN_WORKERS=4` и, скорее всего, больше ничего.
Если там уже стоит `GUNICORN_WORKER_CLASS=sync` — потоки не включатся, строку
надо убрать.

## б) Выкатка

```bash
cd /srv/weconomics/app && git pull --ff-only && cd deploy && docker compose build web && docker compose up -d web
```
**Должно получиться:** `git pull` без ошибок, сборка заканчивается
`Built` или `naming to … weconomics-web:latest`, затем `Container weco-web Started`.

```bash
docker compose restart nginx
```
**ОБЯЗАТЕЛЬНО.** nginx запоминает адрес `web` при своём старте; пересозданный
`web` мог получить другой — без перезапуска будет 502.
**Должно получиться:** `Container weco-nginx Started`.

## в) Проверка

```bash
docker compose logs web --since 10m | grep -E "Using worker|Booting worker"
```
**Должно получиться:** одна строка `Using worker: gthread` и **четыре** строки
`Booting worker with pid: …`.

```bash
docker compose ps web
```
**Должно получиться:** у `weco-web` в столбце STATUS `Up … (healthy)` (первые
две минуты может быть `starting` — подождать и повторить).

```bash
docker compose exec web curl -fsS -H 'Host: weconomics.site' http://127.0.0.1:8000/healthz/ ; echo ; curl -s https://weconomics.site/healthz/ ; echo ; curl -sI https://weconomics.site/ | head -1
```
**Должно получиться:** дважды `{"ok": true, …}` (прямо из gunicorn и через
nginx) и `HTTP/2 200`. Плюс открыть сайт в браузере, зайти в каталог и в любую
задачу.

```bash
docker exec weco-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from pg_stat_activity"'
```
**Должно получиться:** заметно меньше `max_connections` (на стенде пик был 33
при перегрузке).

## г) Живая проба на бою (по желанию, ≈ $0,03)

8 настоящих вопросов к ИИ разом и лёгкие страницы 30 секунд. Зонд работает
ВНУТРИ контейнера web, то есть с самого сервера: VPN не влияет.

Нужны: служебный аккаунт команды (логин) и id любой видимой задачи:

```bash
docker compose exec web python manage.py shell -c "from catalog.filters import base_queryset; print(base_queryset('catalog').order_by('id').values_list('id', flat=True).first())"
```

Сначала опора без ИИ, потом K = 8 (`<id>` и `<аккаунт>` подставить):

```bash
docker compose exec web python manage.py ai_load_probe --base http://127.0.0.1:8000 --host weconomics.ai --problem <id> --ai 0 --window 30 --out /tmp/k0.json
```

```bash
docker compose exec web python manage.py ai_load_probe --base http://127.0.0.1:8000 --host weconomics.ai --problem <id> --ai 8 --ai-user <аккаунт> --window 30 --baseline /tmp/k0.json
```

**Должно получиться:** в конце строки `PASS`, `ИИ: OK 8 из 8`, ошибок 0.
Записать P50 / P95 / макс и прислать в чат.

Что останется в базе: 8 строк `ChatTurn` и 8 строк `AiUsageLog` у этого
аккаунта (8 из 30 его суточных обращений, ≈ $0,03 из дневного потолка чата
$1); события «opened» по этой задаче от просмотров страницы; сессия входа
удаляется сама. Если вопросы к ИИ отвечают ошибкой CSRF — повторить с
`--host weconomics.site`.

## д) Откат (если что-то не так)

```bash
echo 'GUNICORN_WORKER_CLASS=sync' >> /srv/weconomics/.env && cd /srv/weconomics/app/deploy && docker compose up -d web && docker compose restart nginx
```

```bash
docker compose logs web --since 5m | grep "Using worker"
```
**Должно получиться:** `Using worker: sync`. Потоки выключены, сайт работает
как до выкатки. Вернуть потоки — удалить эту строку из `/srv/weconomics/.env`
и повторить `docker compose up -d web && docker compose restart nginx`.

## е) Площадка dev.weconomics.ai

После пуша `main` и зелёного CI площадка выкатится сама (проверка раз в 5
минут) и перейдёт на 2 воркера × 8 потоков. Через 10–15 минут после пуша:

```bash
tail -3 /srv/weconomics/dev/autodeploy.log
```
**Должно получиться:** последняя строка с хешем нового коммита и `ok`.

```bash
docker logs weco-web-dev --since 30m 2>&1 | grep -E "Using worker|Booting worker"
```
**Должно получиться:** `Using worker: gthread` и две строки `Booting worker`.

```bash
docker stats --no-stream weco-web-dev
```
**Должно получиться:** память заметно ниже `900MiB` (на стенде в этой
раскладке 340–500 МиБ). ⚠️ Если в эти минуты корпус поиска собирается с нуля,
пик доходит до ~800 МиБ — так было и на sync; если контейнер перезапускается
по памяти, написать в чат.

Открыть `https://dev.weconomics.ai`. ⚠️ Автовыкатка площадки nginx не
перезапускает: если там 502 — выполнить `cd /srv/weconomics/app/deploy && docker compose restart nginx`
(nginx общий у боя и площадки, боевой сайт перезапуск переживает за секунду).
