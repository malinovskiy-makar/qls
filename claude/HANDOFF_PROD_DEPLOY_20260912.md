# Хэндофф: первый прод-деплой за долгое время — 12.09.2026

> Сессия Claude Code (Opus, Effort High), ночь с 11 на 12 сентября.
> Слияние трёх направлений работы в `main`, полный прогон и выкатка на
> боевой сервер. Команды на сервере запускал владелец, всё остальное —
> Claude Code.
>
> Читать сверху вниз: порядок здесь тот же, в котором всё происходило.

---

## Короткий итог

Три направления работы (фиксы Wecon Rush и сайта, обогащение v2 с
олимпиадным слоем, дедуп корпуса с сортировщиком поиска) сведены в `main`
и выкачены на прод. **188 коммитов, 353 файла, +118 896 / −4 312**
относительно прежнего состояния GitHub.

По дороге найдены и починены три настоящих бага, два из них — на бою.
Корпус на прод НЕ переносился: это отдельная задача.

| Что | До | После |
|---|---|---|
| Код на сервере | `f30aa088` от 06.09 | `5b675b87` от 12.09 |
| Миграции `problems` | до `0047` | до `0062` |
| Контейнер дуэли `ws` | не запущен с 02.09 | поднят, `ws ok` снаружи |
| Вопросов игры | 1 404 | 1 404 |
| Задач в банке | 5 095 | 5 095 (корпус не переносили) |

---

## Фаза −1. Сверка с реальностью

Цель фазы — не поверить постановке задачи на слово, а проверить её.
Это оказалось не формальностью: **постановка расходилась с реальностью в
трёх местах**.

### Что запускали

```bash
git status --short
git worktree list
git log --all --author="QLS Teacher" --oneline        # работа с макбука
git branch -a --contains 26edcc7                      # где она лежит
git rev-list --count origin/main..main                # локальный main впереди?
git rev-list --count main..origin/main                # и позади?
```

### Расхождение 1: ветки с макбука локально нет

Коммиты с макбука идут под git-именем `QLS Teacher`. Их 19, все от 08.09,
и содержимое сверено с ожидаемым: шапка и переименование в «Wecon Rush»,
заглушка «Скоро» на олимпиадах, вкладки профиля, красная виньетка, звук,
синие ссылки, одна кнопка «Поделиться», окно «Бросить вызов», табло дуэли,
сводка забега, девять графиков, панель «Мои рекорды».

Но ветки `feat/game-and-site-fixes-20260908` локально **не существует**:
её уже влили в `origin/main` через pull request №7 от 09.09, и она уже три
дня жила на площадке `dev.weconomics.ai` через автодеплой.

### Расхождение 2: визуальной приёмки этой работы нигде нет

В Notion все 12 карточек фаз 08.09 стояли «На проверке», ни одной
«Готово». Поиск по «Результатам» тоже ничего не дал.

По правилу сессии это стоп-гейт: непринятое глазами в `main` не сливаем.

### Расхождение 3: локальный `main` разошёлся с GitHub

```
локальный main:  на 139 коммитов ВПЕРЁД (29.08–07.09, из них 121 — Андрей)
                 на 19 коммитов НАЗАД (работа с макбука)
общий предок:    f857580 (PR #6)
```

В этих 139 коммитах **уже влиты** `feat/taxonomy-v2-openai-provider`
(обогащение v2, 5 миграций, коммит `b08a1b3`) и `feat/olympiad-text-dedup`
(коммит `b29d23d`) — те самые ветки, которые в постановке были помечены
«не трогать». Отделить их от `feat/smart-search-rerank` нельзя: она
построена поверх них. Пуш `main` = пуш всего этого.

### Состояние прода до выкатки (снято по SSH, только на чтение)

```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
cd /srv/weconomics/app && git log -1 --pretty='%h %ad %s' --date=iso
cd deploy && docker compose ps
docker compose exec -T web python manage.py shell -c "..."
```

Код `f30aa088` от 06.09. В банке 5 095 задач против 41 307 локальных,
последнее изменение 24.08. `DuplicateCandidate` и `ReviewVerdict` пусты,
модели `DupMark` в коде на сервере нет вовсе. Подняты `nginx`, `postgres`,
`redis`, `web`; **не подняты `ws` и `search`**. Свободно 59 ГБ из 79.

### Перенос корпуса: механизм есть

Найден и описан в `docs/RUNBOOK.md`, раздел «Выкатка Wecon Rush», шаг 4:

```bash
# локально
manage.py dump_for_deploy --bank-only --outdir deploy_fixtures_bank --chunk 2000
gzip -f deploy_fixtures_bank/*.json
# на сервер
scp ... :/srv/weconomics/backups/fixtures/
# на сервере, ВНУТРЬ контейнера (у web нет монтирования backups/)
docker compose cp /srv/weconomics/backups/fixtures/. web:/tmp/bank_fixtures
docker compose exec -T web python manage.py bulk_load_fixtures --dir /tmp/bank_fixtures
docker compose exec -T web python manage.py fix_sequences --apply
```

Заодно выяснилось, что блокер этого механизма снят ещё 07.09 коммитом
`1ea306b`: `test_deploy_dump` и `test_deploy_dump_bank_only` — 10 тестов,
все зелёные на PostgreSQL. Запись в `CLAUDE.md` об их красноте устарела.

### Флаг сортировщика

Подтверждено по коду `config/settings.py`: `SMART_SEARCH_RERANK` без
переменной окружения равен `False`, и включается он только для персонала.

### Два стоп-гейта и ответы владельца

1. **Приёмка работы с макбука.** Ответ: «считаю принятой, идём дальше».
   Отклонён вариант отложить выкатку: работа уже в `origin/main` и прод
   унесёт её при любой следующей выкатке.
2. **Объём пуша.** Ответ: «пушим всё — так и задумывалось». Запрет
   относился к веткам как к веткам; их содержимое приняли в `main`
   прошлые сессии, а вынимать его обратно значило бы переписывать
   историю, что решением 09.09 запрещено.

---

## Фаза A. Прогон тестов отвязан от `.env` разработчика

**Проблема.** Пять модулей тестов `catalog` краснели только на машине
владельца: в его `.env` лежат ключ модели и `SMART_SEARCH_RERANK=1`, а
`config/settings.py` этот файл читает. В CI переменных нет, джоб зелёный —
и расхождение «у меня красное, в CI зелёное» перестало быть сигналом
настоящей поломки.

**Порядок работы был обратный привычному: сначала тест, потом код.**

```bash
# 1. Тест написан и ПРОВАЛЕН до единой строки правки
venv313/Scripts/python.exe manage.py test config.tests.test_env_isolation
#    → ModuleNotFoundError: No module named 'config.test_runner'
```

Появился `config/test_runner.py` с бегуном `EnvIsolatedRunner` и одна
строка `TEST_RUNNER` в настройках. Бегун гасит ключи всех поставщиков —
список берётся из реестра `PROVIDERS`, а не переписан рядом, иначе шестой
поставщик молча выпал бы — и возвращает флаг сортировщика к умолчанию.

**Вторая половина бага, которая чуть не ушла незамеченной.** Одиночный
прогон позеленел, а параллельный остался красным:

```bash
venv313/Scripts/python.exe manage.py test catalog --parallel 4
#    → 6 красных из 366, ровно те же пять модулей
```

Причина: Windows поднимает воркеры через spawn, каждый заново импортирует
настройки вместе с чтением `.env`, а тот кладёт значения через
`os.environ.setdefault`. Удалённый ключ возвращался обратно в каждом
воркере. Поэтому зачистка **выставляет пустое значение, а не удаляет
ключ**. На это заведён отдельный сторож `SurvivesDotenvReloadTests` —
без него правка выглядела бы рабочей и отменялась бы на прогоне.

**Результат:** `catalog` — 366 тестов, было 6 красных, стало 0.
Коммит `40037b1`.

---

## Фаза B. Слияние в `main`

Слияния делались на отдельной ветке `integration/deploy-20260912`, а
`main` переставлялся на результат перемоткой. Так `main` ни секунды не
был в промежуточном состоянии.

```bash
git checkout -b integration/deploy-20260912 main
git merge --no-ff origin/main                    # работа с макбука
git merge --no-ff feat/smart-search-rerank       # дедуп и сортировщик
git branch -f main integration/deploy-20260912
```

Перед каждым слиянием конфликты проверялись без записи на диск:

```bash
git merge-tree --write-tree --name-only main origin/main
```

**Конфликты — только в документах и один тривиальный в коде.**

- `CLAUDE_ARCHIVE.md` — обе записи сессий 08.09 сохранены целиком.
- `CLAUDE.md` — блок между маркерами `NOTION-SYNC` генерируется из Notion
  и руками не правится; взята свежая версия, блок перегенерирован в конце
  сессии.
- `config/settings.py` — две независимые вставки в конец файла
  (`OLYMPIADS_PUBLIC` из ветки игры и `TEST_RUNNER` отсюда). Оставлены обе.

После каждого слияния:

```bash
venv313/Scripts/python.exe manage.py check                     # 0 ошибок
venv313/Scripts/python.exe manage.py makemigrations --check --dry-run
#    → No changes detected
```

Граф миграций проверен отдельно: 14 новых, все в `problems`, лист один
(`0062`), двойные номера `0048–0054` — намеренные и склеены узлами
слияния. По содержимому: только `AddField`, `CreateModel`,
`AlterField(choices)` и `AddConstraint`. **Ни одна не удаляет и не
переписывает данные, `RunPython` среди новых нет.** Боевые зависимости
(`requirements/base.txt`) не менялись.

Коммиты `a8f9957` и `133e18b`.

---

## Фаза C. Полный прогон — по-настоящему

Прогон шёл на **PostgreSQL**, а не на SQLite: прод живёт на PostgreSQL, и
зелёный SQLite доказательством не считается. Это же покрывает джоб CI
«схема с нуля» — тестовая база создаётся прогоном всех миграций.

```bash
venv313/Scripts/python.exe scripts/run_tests.py \
    problems catalog teacher student calc2 game calendar_stub config olympiads \
    --settings=config.settings_test_pg --summary
```

| Шаг | Тестов | Время |
|---|---|---|
| A, параллельный | 5 771 | 112,3 мин |
| B, `serial` | 8, пропущено 4 | 4,4 мин |
| всего | — | **116,7 мин** |

Остальные четыре джоба CI прогнаны поимённо и зелёные:

```bash
venv313/Scripts/python.exe -m ruff check .                    # зелёный
venv313/Scripts/python.exe -m bandit -r problems catalog teacher \
    student game calc2 config olympiads -ll                   # зелёный
venv313/Scripts/python.exe -m pip_audit -r requirements/base.txt
#    → No known vulnerabilities found
DJANGO_SETTINGS_MODULE=config.settings_production ... \
    manage.py check --deploy --fail-level WARNING             # зелёный
```

### Красные модули: три ожидаемых и два нет

Было 15 падений и 6 ошибок. Три модуля входили в известный список
(`test_corpus_diagnostics`, `test_embedding_formula`,
`test_embeddings_transfer`) и дали **14 падений и 4 ошибки** — до единицы
та же цифра, что записана в `CLAUDE.md` про тесты, зашитые на
спецификацию отпечатка `v1`, тогда как активна `v2_focus_repeat`.

Два модуля в список не входили. По правилу сессии на них остановились и
разобрали каждый до причины.

### Баг 1. Полоса активности теряла сегодняшний забег три часа каждую ночь

**Это настоящий баг продукта, а не теста.** В `game/leaderboard.py`
верхний край окна брался `timezone.now().date()` — это дата по UTC, а день
забега считался `timezone.localtime(...).date()` — дата по Москве. С
полуночи до трёх ночи московская дата на сутки впереди, и сегодняшний
забег оказывался **выше** верхнего края окна: панель «Мои рекорды»
показывала ноль там, где человек только что играл.

Нашлось только потому, что прогон шёл в начале третьего ночи. Тест «окно
ровно в 30 дней» краснел ровно в эти три часа и зеленел в остальные
двадцать один — то есть ловил баг по часам машины, а не по существу.

⚠️ **Первая редакция нового теста зеленела на сломанном коде.** Подменка
`timezone.now` возвращала время с московским смещением, и `.date()` у
такого значения давала московскую дату. Настоящий `now()` всегда в UTC —
в этом весь баг и был. Тест переписан, чтобы подменка отдавала UTC.

Правка одна: `timezone.localdate()` вместо `timezone.now().date()`.
Коммит `cdc6bb8`, проверено — `game` 43 теста на PostgreSQL зелёные.

### Баг 2. Сторож имён полей ронял вставку на PostgreSQL

`problems/tests/test_field_name_values.py` писал в поле его собственное
имя. У `enrichment_source` колонка `varchar(8)`, а имя длиной 17 символов:
SQLite глотает молча, PostgreSQL отвечает `value too long`. Вставка
падала, транзакция `TestCase` уходила в аборт — и краснело заодно
следующее поле, `text_quality`, хотя с ним всё в порядке.

Разобрано так: в колонку короче своего имени баг физически не заводится,
и там надо проверять, что сторож **молчит**. Список полей, куда имя
влезает, закреплён явно и сверяется с самой схемой отдельным тестом —
иначе сужение колонки тихо сделало бы проверку пустой.

Коммит `053a81f`, 8 тестов зелёные и на PostgreSQL, и на SQLite.

---

## Фаза D. Пуш

```bash
git push origin feat/smart-search-rerank
git push origin main
#    44a8891..5b675b8  main -> main
```

---

## Фаза E. Выкатка на прод

Команды собраны по факту состояния сервера, а не по памяти: `entrypoint.sh`
прочитан, состояние прода снято по SSH, конфигурация nginx сверена
побайтно. Полный файл — `reports/deploy_20260912/DEPLOY_COMMANDS.md`.

### 0. Бэкап. Первым шагом и без исключений

```bash
sudo /srv/weconomics/app/deploy/backup.sh
sudo ls -lh /srv/weconomics/backups | tail -3
```

Штатный скрипт ночного таймера. Результат: 30 МБ, как у копий за 10 и 11
сентября, оглавление дампа читается.

### 1. Код

```bash
cd /srv/weconomics/app
git pull --ff-only
git log -1 --pretty='%h %ad %s' --date=iso
#    → 5b675b87, совпало с локальным
```

### 2. Образ и запуск

```bash
cd /srv/weconomics/app/deploy
docker compose build web
docker compose up -d web
```

⚠️ Контейнер `web` строго один: второй пойдёт мигрировать параллельно с
первым и развалит схему.

### 3. Миграции — отдельной команды НЕТ

`deploy/entrypoint.sh` накатывает их сам при старте контейнера, до
`gunicorn`, под `set -e`. Упавшая миграция не даёт контейнеру подняться.
Там же собирается статика.

```bash
docker compose logs --tail 40 web     # ждём «[entrypoint] gunicorn…»
```

Все 14 применились, статика собрана, gunicorn поднялся с четырьмя
воркерами.

### 4. Пул игры — руками

Автоматически не пересобирается: в `entrypoint.sh` его нет.

⚠️ Перед запуском проверено, не обнулит ли пул новый фильтр. Команда
теперь требует `content_status = ok`, а это поле приехало сегодняшней
миграцией. Миграция ставит существующим строкам `ok` по умолчанию, и на
проде это подтвердилось: 5 095 задач со статусом `ok`, кандидатов 5 078.

```bash
docker compose exec -T web python manage.py build_game_pool
#    → Пул пересобран: 1404 вопросов (было 1404), схлопнуто повторов: 0
```

### 5. Дуэль в реальном времени

```bash
docker compose up -d ws
docker compose ps ws                  # healthy
```

### 6. nginx — по плану делать было нечего

⚠️ Шаг 8 старого ранбука копирует `django.conf` поверх активной
конфигурации сервера. С 07.09 в ней живёт **ещё и блок площадки
`dev.weconomics.ai`**, дописанный руками: копирование вслепую стёрло бы
площадку целиком при ближайшей перезагрузке nginx.

Сегодня копировать не потребовалось: версия из `main` и активная
конфигурация совпали побайтно (`md5 be1496b1675d874a55b2b9ef55dcecb3`,
409 строк с обеих сторон). Предупреждение с командой сверки внесено в сам
ранбук.

---

## Нештатный шаг: nginx держал ЧУЖОЙ публичный адрес

Этого шага в плане не было — ловушка вскрылась только на живом сервере.

**Симптом.** Контейнер `ws` поднят и healthy, но снаружи `/ws/health/`
отдаёт 504.

**Что показала диагностика.**

```bash
# изнутри контейнера nginx — дуэль достижима
docker compose exec -T nginx curl -sS -o /dev/null -w '%{http_code}\n' \
    http://ws:8001/ws/health/
#    → 200

# а в журнале ошибок nginx
docker compose logs nginx | grep upstream
#    upstream timed out while connecting to upstream,
#    request: "GET /ws/health/", upstream: "http://64.70.19.33:8001/ws/health/"

docker inspect weco-ws --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
#    → 172.18.0.9
```

`64.70.19.33` — адрес в публичном интернете.

**Причина.** `proxy_pass http://ws:8001` разрешает имя **один раз**, при
загрузке конфигурации. Nginx стартовал три недели назад, когда контейнера
`ws` не было: внутренний DNS Docker имя не нашёл, запрос ушёл к внешнему
DNS, и тот на голое слово «ws» вернул чужой адрес. Nginx держал бы его
вечно.

**Чем это опасно.** Сайт работает, контейнер числится здоровым, а сокет
дуэли уходит к постороннему серверу. Заметить можно было только по 504.

**Лечение, без простоя:**

```bash
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

После неё `/ws/health/` отвечает `ws ok`. Порядок «сначала `ws`, потом
перезагрузка nginx, потом проверка ответа» внесён в `docs/RUNBOOK.md`,
шаг 7.

---

## Проверка после выкатки

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' https://weconomics.site/
curl -fsS -D - -o /dev/null https://weconomics.site/catalog/ | grep -i x-smart-search
curl -fsS -o /dev/null -w '%{http_code}\n' https://weconomics.site/game/
curl -fsS -o /dev/null -w '%{http_code}\n' https://weconomics.site/olympiads/
curl -fsS https://weconomics.site/ws/health/
curl -fsS 'https://weconomics.site/game/api/leaderboard/?mode=blitz' | head -c 200
```

| Что | Ответ |
|---|---|
| главная | 200 |
| каталог | 200, `X-Smart-Search: off` |
| игра | 200 |
| олимпиады | 200 |
| дуэль | `ws ok` |
| лидерборд | отдаёт JSON с настоящими строками |

---

## Что записано в Notion

**«Решения»** — одна карточка: три направления слиты в `main` одной
выкаткой, с разбором обоих отклонённых вариантов.

**«Результаты»** — подстраница с цифрами прогона, пятью джобами и списком
того, что починено и что осталось красным.

**«Задачи»** — новая со статусом «Надо»: перенос корпуса на прод.
Новые со статусом «Готово»: полоса активности, сторож имён полей, ловушка
ранбука с nginx, чужой адрес апстрима.
Переведены в «Готово»: пять модулей `catalog` из-за `.env`, блокер
заливки `--bank-only`, контейнер `ws` не запущен с 02.09.

---

## Что осталось

1. **Приёмка глазами.** Шапка с «Wecon Rush» и подсветкой активного
   пункта, заглушка «Скоро» на олимпиадах, забег в Блице до экрана итогов,
   панель «Мои рекорды», одна кнопка «Поделиться». Дуэль — вдвоём в двух
   браузерах.
2. **Двенадцать карточек фаз 08.09** ждут перевода в «Готово». Это
   массовая правка, по правилу штаба нужен явный ответ владельца.
3. **Главный открытый вопрос — перенос корпуса.** На проде 5 095 задач из
   41 307. Код дедупа уже там, таблица `DupMark` создана, но **пуста**:
   6 220 пометок посчитаны против локального банка и на проде ссылаться
   им не на что. Пул игры тоже собран из 5 095 задач. Решается отдельной
   сессией и отдельным промптом.
4. **Мелочь.** Файл `reports/calc2_22aug/timing_plain.json` был изменён до
   сессии, отложен в `git stash` перед слияниями; ночной прогон
   браузерных тестов перезаписал его заново, поэтому вернуть отложенное
   поверх не вышло. Stash цел — какая версия нужна, решает владелец.

---

## Справочник: все команды сессии одним списком

```bash
# — сверка с реальностью —
git log --all --author="QLS Teacher" --oneline
git branch -a --contains <sha>
git rev-list --count origin/main..main
git merge-tree --write-tree --name-only main origin/main

# — проверки перед сдачей (пять джобов CI поимённо) —
venv313/Scripts/python.exe -m ruff check .
venv313/Scripts/python.exe -m bandit -r problems catalog teacher student game calc2 config olympiads -ll
venv313/Scripts/python.exe -m pip_audit -r requirements/base.txt
venv313/Scripts/python.exe manage.py makemigrations --check --dry-run
venv313/Scripts/python.exe scripts/run_tests.py <приложения> --settings=config.settings_test_pg --summary
manage.py check --deploy --fail-level WARNING     # с боевым окружением, см. ci.yml

# — слияние —
git checkout -b integration/deploy-20260912 main
git merge --no-ff origin/main
git merge --no-ff feat/smart-search-rerank
git branch -f main integration/deploy-20260912
git push origin main

# — выкатка на сервере —
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
sudo /srv/weconomics/app/deploy/backup.sh
cd /srv/weconomics/app && git pull --ff-only
cd deploy && docker compose build web && docker compose up -d web
docker compose logs --tail 40 web
docker compose exec -T web python manage.py build_game_pool
docker compose up -d ws
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
curl -fsS https://weconomics.site/ws/health/
```
