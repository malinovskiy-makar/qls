# Выкатка на прод 12.09.2026 — команды для владельца

> Собрано Claude Code в сессии «первый прод-деплой: слияние трёх направлений».
> Ничего из этого файла Claude Code не выполнял: все команды ниже запускает
> владелец руками.
>
> Сервер: `135.106.181.151` (Selectel, Москва). Вход:
> `ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151`.
> Все `docker compose` — только из `/srv/weconomics/app/deploy`.

## Что было на проде до выкатки (снято 12.09.2026)

| Что | Значение |
|---|---|
| Код | `f30aa088` от 2026-09-06 (ветка `main`) |
| Задач в банке | **5 095** (локально — 41 307) |
| Вопросов игры | 1 404 |
| `DuplicateCandidate` / `ReviewVerdict` | 0 / 0 |
| Контейнеры подняты | `nginx`, `postgres`, `redis`, `web` |
| Контейнеры НЕ подняты | **`ws`** (дуэль в реальном времени), `search` |
| Свободно на диске | 59 ГБ из 79 |
| Последний бэкап | `weconomics-20260911-032031.dump.gz` |

## Что приезжает

**183 коммита, 351 файл, +118 607 / −4 310** относительно `origin/main`.
Три направления:
фиксы Wecon Rush и сайта (уже в `origin/main`, PR #7), обогащение v2 и
олимпиадный слой, дедуп корпуса и сортировщик поиска.

**14 новых миграций, все в `problems`** (`0048`, `0049_title_candidate_source`,
`0049_alter_olympiadref_match_method`, `0050_problem_content_status`,
`0050_olympiadref_is_best_in_cluster_and_more`, `0051_problem_answer_consistency`,
`0055_merge`, `0056_enrichment_v2_layout`, `0057`, `0058`, `0059_merge`, `0060`,
`0061_dupmark`, `0062_dupmark_answer_rule`).

Проверено по `git diff` каждой: только `AddField`, `CreateModel`,
`AlterField(choices)`, `AddConstraint` и узлы слияния. **Ни одна не удаляет
и не переписывает данные.** `RunPython` среди новых нет.

**Боевые зависимости не менялись** — `requirements/base.txt` и `base.in`
между прод-коммитом и `main` не тронуты.

---

## 0. Бэкап. Первым шагом и без исключений

```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
sudo /srv/weconomics/app/deploy/backup.sh
```

Это штатный скрипт ночного таймера: дамп `-Fc`, сжатие, хранение 30 копий
в `/srv/weconomics/backups`. Проверить, что файл создан и не пустой:

```bash
sudo ls -lh /srv/weconomics/backups | tail -3
```

Размер новой копии должен быть того же порядка, что у вчерашней. Пустой или
килобайтный файл — **остановиться и не идти дальше**.

## 1. Код

```bash
cd /srv/weconomics/app
git pull --ff-only
git log -1 --pretty='%h %ad %s' --date=iso
```

Должен показаться **`053a81f`** — «Сторож имён полей: на PostgreSQL он
ронял вставку, а не проверял сторожа». Если
`git pull` просит слияние вместо перемотки — **остановиться**: значит на
сервере есть местная правка, которой нет в репозитории.

## 2. Образ и запуск

```bash
cd /srv/weconomics/app/deploy
docker compose build web
docker compose up -d web
```

⚠️ Контейнер `web` строго один. Второй пойдёт накатывать миграции
параллельно с первым и развалит схему.

## 3. Миграции — ОТДЕЛЬНАЯ КОМАНДА НЕ НУЖНА

`deploy/entrypoint.sh` накатывает их сам при старте контейнера, до
`gunicorn`, под `set -e`: упавшая миграция не даёт контейнеру подняться.
Там же собирается статика. Проверено чтением файла, не по памяти.

Убедиться, что они прошли:

```bash
docker compose logs --tail 60 web        # ждём «[entrypoint] gunicorn…»
docker compose exec -T web python manage.py showmigrations problems | tail -16
docker compose ps                        # web — healthy
```

Все 14 новых должны стоять с `[X]`.

## 4. Пул игры — ЗАПУСКАЕТСЯ РУКАМИ

Автоматически он не пересобирается: в `entrypoint.sh` его нет, только
`migrate` и `collectstatic`. Команда идемпотентна, повторный запуск
пересобирает пул заново (замер репетиции — 5,6 с).

```bash
docker compose exec -T web python manage.py build_game_pool
```

⚠️ Пул соберётся из тех **5 095** задач, что лежат на проде, а не из
41 307 локальных. Больше вопросов он от этой выкатки не получит.

## 5. Дуэль в реальном времени

Контейнер `ws` на проде **не запущен с 02.09** — дуэль всё это время была
асинхронной. Если поднимаем:

```bash
docker compose up -d ws
docker compose ps ws                     # healthy
curl -fsS https://weconomics.site/ws/health/    # ws ok
```

Настройки nginx для этого уже достаточно (см. шаг 6).

## 6. nginx — В ЭТОТ РАЗ НИЧЕГО НЕ ДЕЛАЕМ

⚠️ **Шаг 8 старого ранбука («Выкатка Wecon Rush») сегодня выполнять НЕЛЬЗЯ
вслепую.** Он копирует `deploy/nginx/available/django.conf` поверх
`/srv/weconomics/nginx/conf.d/weconomics.conf`. На сервере в этом файле
живёт ещё и блок площадки `dev.weconomics.ai`, дописанный руками 07.09.

Сегодня копировать не нужно вовсе: сверено побайтно, активный конфиг и
версия из `main` совпадают (`md5 be1496b1675d874a55b2b9ef55dcecb3`,
409 строк с обеих сторон) — блок площадки в репозиторий уже внесён.
`location /ws/` в активном конфиге есть.

## 7. Проверка после выкатки

```bash
# сайт открывается
curl -fsS -o /dev/null -w 'главная %{http_code}\n' https://weconomics.site/

# каталог отвечает и сортировщик ВЫКЛЮЧЕН
curl -fsS -D - -o /dev/null https://weconomics.site/catalog/ | grep -i 'HTTP/\|X-Smart-Search'
#   ждём: HTTP/2 200  и  x-smart-search: off

# игра
curl -fsS -o /dev/null -w 'игра %{http_code}\n' https://weconomics.site/game/
curl -fsS 'https://weconomics.site/game/api/leaderboard/?mode=blitz' | head -c 200

# один забег целиком
curl -fsS -c /tmp/rush.jar 'https://weconomics.site/game/api/session/start/?mode=blitz'
curl -fsS -b /tmp/rush.jar  https://weconomics.site/game/api/question/

# дуэль, если подняли ws
curl -fsS https://weconomics.site/ws/health/
```

**Глазами:** шапка с «Wecon Rush» и подсветкой активного пункта, раздел
«Олимпиады» под заглушкой «Скоро», один забег в Блице до экрана итогов,
панель «Мои рекорды», кнопка «Поделиться» одна.

## 8. Откат

| Шаг | Откат |
|---|---|
| 4 (пул) | `build_game_pool` идемпотентен — просто прогнать снова |
| 5 (`ws`) | `docker compose stop ws` — дуэль снова асинхронная, сайт цел |
| 3 (миграции) | `docker compose exec -T web python manage.py migrate problems 0047` |
| 1–2 (код) | `git checkout f30aa088` → `docker compose build web` → `up -d web` |
| Всё сразу | восстановление из дампа шага 0, порядок — `docs/SERVER.md` |
| Полный | откат к заглушке, раздел «Откат» в `docs/SERVER.md` |

## Чего в этой выкатке НЕТ

- **Корпуса.** На проде остаются 5 095 задач из 41 307. Код дедупа
  приедет, но таблица `DupMark` будет пустой: 6 220 пометок посчитаны
  против локального банка. Перенос корпуса — отдельная операция
  (`dump_for_deploy --bank-only` → `bulk_load_fixtures` → `fix_sequences
  --apply`, порядок в `docs/RUNBOOK.md`), сегодня не выполняется.
- **Сортировщика поиска.** `SMART_SEARCH_RERANK` без переменной окружения
  равен `False` (`config/settings.py`), плюс он только для `is_staff`.
  Заголовок ответа должен быть `X-Smart-Search: off`.
- **Смыслового поиска.** `SEMANTIC_SEARCH_ENABLED=0` остаётся как есть
  (ADR 0012), контейнер `search` не поднимаем.
- **Выравнивания счётчиков.** `fix_sequences --apply` нужен перед крупной
  заливкой строк, а её сегодня нет.
