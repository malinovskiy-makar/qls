# Синхронизация веток — журнал сессии (05–06.09.2026)

**Единственный источник правды о ходе работы.** Дописывается после каждой фазы.
При сжатии контекста: перечитать задание и этот файл, найти первую фазу без ✅,
продолжить с неё, ничего не переделывая.

## Цель

Прод (`weconomics.site` / `weconomics.ai`, один сервер, один клон) стоит на
`main` = `6b84061`. Шесть готовых веток собираются в `integration/sync-20260905`,
один полный прогон на PostgreSQL, один пуш в CI, одна визуальная приёмка
владельца; потом (сессия B) `main` → прод и удаление веток. В этой сессии
ничего не удаляется и ничего не пушится — команды пуша выписываются владельцу.

Три блока, три контрольные точки:
- **A1** — страховка (теги, хвосты wip/*) и четыре слияния (beta-polish,
  scoped-test-runner, olympiads-screens, catalog-redesign + склейка миграций) → **КТ1**
- **A2** — два слияния (calc2-monoexport, embeddings-c13), граф миграций → **КТ2**
- **A3** — номера ADR, документы, четыре быстрых джоба CI → **КТ3**, затем
  полный прогон (фаза 13), итог (14), стоп-гейт рабочей базы (15).

## Таблица фактов (сверено фазой −1, 06.09.2026)

| Что | Значение | Сверка |
|---|---|---|
| `main` = `origin/main` = прод | `6b8406110d9d7e24afb8e796e6e0dc10197eb143` | ✅ |
| `feat/beta-polish-0904` (локальная = origin) | `13b3e1ff3efeabb184508c8f99ff51ddbe9d7b1e`, +23 | ✅ |
| `feat/scoped-test-runner` (локальная = origin) | `1690397f2cdb30f7e32ef95d5162e2f83467d781`, +5 | ✅ |
| `origin/feat/olympiads-screens` (только origin) | `128391ed6138ab881f87e84bcdd96d0bcfd1bbab`, +27 | ✅ OK-olymp |
| `origin/feat/catalog-redesign` (только origin) | `36de913d217030920d94835205ca04406b012c3a`, +26 | ✅ |
| `feat/calc2-monoexport-one-chart` | `aca9bd255f5f4a59de38fe7f4c8884bb270067cc`, +24 — **только origin** (см. поправку 1) | ⚠️ |
| `feat/embeddings-c13-diagnostics` (локальная = origin) | `0729a47168f5a9a9c50a5fd2e538d64ba4ccee78`, +29 | ✅ |
| `feat/taxonomy-v2-openai-provider` в `qls-models` | живая работа, НЕ ТРОГАТЬ | ✅ ветка на месте |
| `wip/mac-leftovers-20260906` на origin | склад с Mac, не трогать | ✅ подтянута fetch |
| Stash в `qls` | один: `wip-tooling-before-publish-readiness` (база `0729a47`) | ✅ |
| Worktree | 11 папок + призрак `.claude/worktrees/import-new-sources-edbc26`; `main` ни в одном | ✅ |
| Неучтённое в корне `qls` | `.txt`, `Claude outputs/`, `claude/`, `session_c15_transcript_20260830.md` — **четыре**, не три (см. поправку 2) | ⚠️ |
| Теги до сессии | `backup/main-before-final-function`, `backup/main-before-priyomka-31aug` | ✅ |
| Python / check | 3.13.12 / 0 ошибок | ✅ |

## Фазы

| Фаза | Статус | Коммит | Числа / отклонения |
|---|---|---|---|
| −1 Сверка с реальностью | ✅ | — | два расхождения → стоп → владелец ответил (поправки 1, 2) |
| 0 Теги | ✅ | — | 8 тегов, все хеши совпали с ожиданием |
| 0б Хвосты wip/* | ✅ | см. раздел «Хвосты» | stash применился чисто, `git stash list` пуст |
| 1 Ветка integration и журнал | ✅ | `c34fa9c6` | `integration/sync-20260905` от `main`. Отклонение: `reports/*` игнорируется — добавлено исключение `!reports/branch_sync_20260905/` в `.gitignore` по принятому в репозитории паттерну |
| 2 Слияние beta-polish | ✅ | `062e7abf` | Конфликт только в `.gitignore` — самодельный (моё исключение против блока beta-polish в конце файла), объединение. `git diff --stat feat/beta-polish-0904 HEAD` — только `.gitignore` (+4) и `reports/branch_sync_20260905/`. `main..HEAD` = 25 ✅. `check` чист. `git ls-files -ci --exclude-standard` = 105 — столько же на `main` и на beta-polish (старые папки `reports/calc2-*`, `reports/vsosh_*`), не наше; инвариант читаем как «не больше 105» |
| 3 Слияние scoped-test-runner | ✅ | `3de777d0` | без конфликтов; `check` чист; `python -m unittest discover -s scripts/tests -t .` → **50 OK** (команда — из докстрингов `scripts/tests/*.py`; в `docs/TESTING.md` она не описана — отметить в фазе 11) |
| 4 Слияние olympiads-screens | ✅ | `52219591` | Конфликты ровно ожидаемые: `.gitignore` (объединение), `CLAUDE.md` (шапка и NOTION-SYNC — сторона с датой 09-04, т. е. HEAD/beta-polish; остальное слилось само), `CLAUDE_ARCHIVE.md` (обе записи, по датам). `git diff --check` чист; `check` чист; `makemigrations --check` → No changes detected; `showmigrations olympiads` 0001–0006 одной цепочкой; `git ls-files data/olympiads` = 118. Тесты `olympiads + test_template_hygiene + test_nav` → **117 OK** (`logs/04-tests-olympiads.txt`). `main..HEAD` = 60 |
| 5 Слияние catalog-redesign + 0054_merge | ✅ | слияние `9a73fe5c`, миграция `cc6ec3fa` | Конфликты ровно пять ожидаемых. Подробности — раздел «Фаза 5: разрешение конфликтов каталога». `showmigrations problems` до склейки: два листа `0052_feedback` (⚠️ уже применена к рабочей базе — beta-polish накатывала свои 0050–0052 локально) и `0053_hint_reviewed_backfill` (не применена). `makemigrations --merge problems --no-input` → `0054_merge_0052_feedback_0053_hint_reviewed_backfill.py`, зависимости ровно `('problems','0052_feedback')`, `('problems','0053_hint_reviewed_backfill')`, `operations = []` — проверено глазами. После: `makemigrations --check` → No changes detected; листовой узел problems один. Тесты: первый прогон 442 → 3 падения (столкновения правил веток, не код; см. ниже) → починены → повтор 89 OK → полный повтор списка → **442 OK, skipped 0** (`logs/05-tests-catalog-final.txt`). По модулям: catalog 311 (test_topic_map 83, test_catalog_redesign 31, test_catalog 19, test_smart_catalog 18, test_search_service 16, test_filters_multi 15, test_problem_page 14, test_testplay 14, test_semantic_degradation 13, test_no_slop 12, test_chat_api 9, test_collections 9, test_hints 9, test_attempts 8, test_similar_titles 8, test_attempt_api 7, test_attempt_files 7, test_filter_state_api 7, test_problem_test_page 7, test_catalog_modal 5), game.test_filter_window 31, config.test_nav 22, problems: test_tails 20, test_sections 17, test_r15_align 13, test_r15_pair 13, test_label_set 8, test_import_problem_attributes 5, test_template_hygiene 2. Пять обязательных файлов тестов существуют и зелёные |
| КТ1 | ✅ | журнал — этот коммит | HEAD после миграции `cc6ec3fa`; `main..HEAD` = 88 = 23+5+27+26 + 4 merge + 3 служебных (журнал ×2, миграция), +1 этот коммит журнала; четыре ветки — предки HEAD; status — четыре `??`; `check` чист; `makemigrations --check` → No changes detected; 8 тегов; `qls-models` не изменилась (`772ac87e`, status пуст); `main` = `6b840611` не сдвинулся. ⛔ Стоп до «продолжай» |
| 6 Сверка перед A2 | ✅ | `75511ff2` (поправки КТ1) | ветка integration, четыре `??`, `main` = `6b840611`, stash пуст. Владелец уже запушил КТ1: `origin/integration/sync-20260905` есть, локально +1 коммит поправок. Поправки 3–7 исполнены (см. раздел) |
| 7 Слияние calc2-monoexport | ✅ | слияние `73da570d`, карта `88b0cc8f` | Взята `origin/feat/calc2-monoexport-one-chart` (поправка 1). Конфликты ровно `CLAUDE.md` (шапка+NOTION-SYNC — HEAD, 09-04 против 09-02), `CLAUDE_ARCHIVE.md` (объединение, порядок по датам сохранился сам). `diff --check`, `check`, `makemigrations --check` — чисто. **`manage.py test calc2`**: 21 тест, 1 падение, 1 пропуск (`logs/07-tests-calc2-django.txt`). Падение `test_calc2_map.test_function_index_matches_code` — «`ineqSnapshot` из карты не найдена в файле»: доказано, что **красный на самой вершине ветки `aca9bd25`** (временный worktree) и зелёный на `main` — ветка убрала функцию и не пересобрала `docs/calc2/CALC2_MAP.md`; на слитом дереве `manage.py calc2_map` (пишет только этот файл) → тест зелёный. Пропуск `test_calc2_control_numbers` — «node-раннер не уложился в 180 с» (известный симптом). **Узловой прогон против `runserver 8099`** (`logs/07-node-probes.txt`): `calc2_math.mjs` **237 прошло / 1 провалено** из 238 — провал «Регулятор сцены · правка значения», ширина 40,375 px при потолке 40 = известный красный из таблицы фактов; **доказательство**: тот же `calc2_math.mjs` на чистом `main` (worktree `qls-tmp-main`, `runserver 8098`, `logs/07-node-calc2_math-on-main.txt`) — тот же единственный ✗ 40,375 px → не регрессия. `control_numbers.mjs` — **ВСЕ 512 КОНТРОЛЬНЫХ ЧИСЕЛ СОШЛИСЬ**, ошибок страницы 0. Worktree `qls-tmp-main` и `qls-tmp-calc2` удалены (в `qls-tmp-main` ставилась junction на `qls/node_modules` ради playwright — снята) |
| 8 Слияние embeddings-c13 | ✅ | слияние `e4a505be`, правка `65854422` | Конфликты ровно пять ожидаемых: `.gitignore` (объединение), `CLAUDE.md` (HEAD: 09-04 против 08-30), `CLAUDE_ARCHIVE.md` (объединение, обе записи С15 и 29.08 по датам), `problems/ai/prompts.py` — **объединение без пересечений**: HEAD нёс `topic_tagging`, `answer_blind`, `catalog_check`, `catalog_chat`, `catalog_ocr`, c13 добавил `search_query_backgen`; одинаковых ключей с разным текстом нет (7 ключей, дублей 0) — «c13 правил <имя>» не понадобилось; `problems/tests/test_template_hygiene.py` — комментарии обеих сторон, `SKIP_PARTS` — версия HEAD (надмножество: `.claude` + `data/olympiads/raw`), ни одна проверка не пропала. `makemigrations --check` сразу после слияния — `CommandError: multiple leaf nodes (0047_problem_figure_raster, 0054_merge…)` — это ожидаемое состояние фазы 9, не расхождение моделей; после шага 2а фазы 9 → **No changes detected**. Тесты (`logs/08-tests-c13.txt`): **157, 1 падение** — сторож c13 `test_eval_set_b.test_в_исходниках_нет_запрещённых_ограничений_массива` нашёл `'maxItems': MAX_STEPS` в `catalog/attempts.py:40` (редизайн). ⚠️ **Настоящий дефект, пойманный слиянием**: схема уходит в `core.run` → structured output Anthropic, а он отвечает 400 на любой `maxItems` (c13: так 28.08 упал пилот набора B) — проверка решений на бою падала бы на каждом запросе. Правка по образцу c13: `maxItems` из схемы убран, ограничение держат профиль промпта («шагов не больше восьми») и `validate()` (`steps[:MAX_STEPS]` там уже был). Повтор `test_eval_set_b + test_attempts + test_attempt_api + test_attempt_files` → 39 OK. Skipped 0 (тесты BGE-M3 в этот список не входят). По модулям: test_new_source_figures 25, test_search_eval_metrics 20, test_eval_set_b 18, test_solo_merge 17, test_eval_sets 14, test_eval_set_c_markdown 9, test_search_eval_command 9, test_search_eval_scope 5, test_template_hygiene 2, catalog: test_catalog_redesign 31, test_similar_titles 8 |
| 9 Граф миграций | ✅ (шаг 4 — см. отклонение) | `d33e36cc` | По skill, свидетельства в `logs/09-*.txt`. **1.** `showmigrations problems`: два листа — `0054_merge…` не применена, `0047_problem_figure_raster` **применена** к рабочей базе (c13 накатывала локально). **2а.** В `0054_merge…py` дописана зависимость `('problems','0047_problem_figure_raster')` с комментарием — файл никем не применён. **3.** `makemigrations --check` → No changes detected; листовой узел problems один. **4. С нуля на PostgreSQL — НЕ ВЫПОЛНЕНО ЛОКАЛЬНО**: Docker Desktop не был запущен, а при запуске падал на старом сокете `sailor-ingest.sock` («The file cannot be accessed by the system»); сокет удалён, Docker перезапущен — итог см. строку «Фаза 9, шаг 4 (PostgreSQL)» ниже таблицы. Запасной шаг: **с нуля на пустой SQLite** (`logs/09-zero-sqlite.txt`) — 99 миграций за 18 с: admin 3, auth 12, contenttypes 2, game 15, olympiads 6, problems 60, sessions 1; `makemigrations --check` чист. **5. Путь обновления на КОПИИ** — рабочая база это **SQLite `db.sqlite3` 889 МБ**, не PostgreSQL (таблица фактов и задание ошибались): копия файлом в `logs/qls_upgrade_check_20260905.sqlite3`, settings-файл `logs/settings_upgrade_check.py` (вне `config/`, вне git). `migrate --plan` (`logs/09-upgrade-path-sqlite-copy.txt`): ровно 10 новых — `olympiads` 0002–0006, `problems` 0050_problem_character_features, 0051_catalog_attempt, 0052_hint_ai_flags, 0053_hint_reviewed_backfill (RunPython), 0054_merge. Beta-polish 0050–0052 и 0047_problem_figure_raster на копии уже стояли (локальная база), на проде их нет — там план будет длиннее ровно на них. `migrate` — 55 с, без ошибок, неприменённых 0. **6. Обратимость**: `migrate problems 0049_merge_20260902_2058` снял 8 (обе цепочки 0050–0054; `0047_problem_figure_raster` не тронут — он не потомок 0049), 29 с, без ошибок; вперёд снова 8 за 29 с; `makemigrations --check` на копии чист. RunPython: `0051_studentgroup_invite_code` (`fill_codes`, откат `noop`) и `0053_hint_reviewed_backfill` (`mark_reviewed`, откат `noop`) — откат схемы идёт, данные RunPython назад не восстанавливаются (по замыслу: `noop`). **7.** Копия — файл в `logs/` (вне git), удалю в фазе 14 |
| КТ2 | ✅ | журнал — этот коммит | `main..HEAD` = 148 = 89 (КТ1) + 1 поправки + 24 calc2 + 1 merge + 1 карта + 29 c13 + 1 merge + 1 схема + 1 склейка; merge-коммитов 9 (6 веток + 3 внутри веток); шесть веток — предки HEAD; четыре `??`; stash пуст; `check` чист; `makemigrations --check` → No changes detected; листовой узел problems один; три `wip/*` на месте; `qls-search-eval` чист (кроме расшифровки), `qls-sol` чист; ignored-tracked без разницы с main; `qls-models` `772ac87e` не изменилась; `main` `6b840611`. ⛔ Стоп до «продолжай» |

**Фаза 9, шаг 4 (PostgreSQL):** ✅ после удаления старого сокета Docker Desktop поднялся за 52 с, `docker compose -f docker-compose.dev.yml up -d postgres redis` — оба healthy. База `qls_dev` из `settings_test_pg` НЕ пуста (104 таблицы, контейнер живёт с 01.09) — поэтому создана свежая `qls_zero_20260905` и Django направлен на неё через `DATABASE_URL` (settings_test_pg его читает). `migrate --noinput --settings=config.settings_test_pg` — **99 миграций за 16 с**, по приложениям те же, что на SQLite (admin 3, auth 12, contenttypes 2, game 15, olympiads 6, problems 60, sessions 1), неприменённых 0, таблиц 110; `makemigrations --check --dry-run --settings=config.settings_test_pg` → **No changes detected**. Свидетельство — `logs/09-zero-postgres.txt`. База `qls_zero_20260905` удалена (артефакт сессии). Docker Desktop оставлен работающим — нужен фазам 12 и 13.
| 10 Номера ADR | ✅ | (этот коммит) | 13 `git mv` ровно по таблице (все файлы были на месте, 0077–0089 свободны); в шапку каждого — строка «Нумерация: перенумерован из …», заголовок `# ADR 00XX` заменён. Ссылки путями: слаг однозначен — заменены по всему дереву (8 файлов); текст ссылок `[ADR N](…M-slug.md)` приведён к номеру пути (несовпадений 0). Голые упоминания (162) разобраны по контексту: 22 файла правлены (calc2-код и docs → 0083–0088; редизайн каталога в `catalog/*`, `problems/ai/*`, `problems/models.py:1031`, `config/tests/test_nav.py`, `DESIGN.md` §1.9, `docs/redesign/catalog-2026-09.md`, запись редизайна в архиве → 0078–0082); упоминания beta-polish (0070 vendor, 0071 sections, 0072 nav, 0073 password, 0074 invite), main (0054 semantic, 0055–0057 game, 0036 topic-map, 0017 calc2-math) — не тронуты. Инварианты: дубли номеров — только 0013–0015; старых слагов 0 (`git grep`); каждый путь `docs/adr/NNNN-*.md` существует, КРОМЕ (было битым до сессии): `0034-legacy-stores-converted-text.md` из `0089-canonical-database-copy.md` (c13) — файла нет ни в одной влитой ветке (живёт в taxonomy-v2, см. «Для будущего слияния»); четыре строки в `reports/site_polish_20260904/PROGRESS.md:118–121` — исторический перечень чужих номеров, не ссылки. Попутно починена опечатка слага в `0071-five-sections-one-module.md` (→ `0053-topic-map-seven-section-colours.md`). Тесты `test_template_hygiene + config` → 62 OK, skipped 4. Следующий свободный номер — **0090** |
| 11 CLAUDE.md и документы | ✅ | (этот коммит) | CLAUDE.md: шапка «Обновлён: 2026-09-06 (синхронизация веток…)»; P0 про `makemigrations game` переписан (game 0001–0015 непрерывна, новые с 0016; двойные номера problems 0050–0054 склеены 0054_merge); `olympiads` добавлен в bandit и в `run_tests.py` (и в `ci.yml` — джобы security и tests); «Часто нужные команды»: все 17 существуют, добавлены `import_olympiads_data`, `import_problem_attributes`, `calc2_map`, `search_eval`; «Боевой сервер» — два имени уже были; «Границы приложений» — строка `olympiads`, два исключения, `game` с GAME.md — уже были; «Карта источников» — все 9 файлов существуют; «Ручное ревью» — три механизма, `content_status` в models.py = 0; вне NOTION-SYNC «не запушена/поверх origin» — 0; блок «Текущий фокус» пересобран из Notion (В работе 7, На проверке 215 + 3 свежих, Надо 7 из 253, решения 3). DESIGN.md §1.9: «пять страниц чтения (задача, …)» → четыре без задачи + исключение 1120 (ADR 0078, решение 05.09, сторож test_nav) одним связным текстом. docs/TESTING.md: команда `unittest discover -s scripts/tests -t .` (50). CLAUDE_ARCHIVE.md: запись «2026-09-05/06 · Синхронизация веток» (что влито, конфликты каталога, миграции, найдено слиянием — attempts.py, номера ADR, известные красные). Числа полного прогона — после фазы 13. `check` чист; `test_template_hygiene + config` → 62 OK, skipped 4; `git diff --stat` — только документы и ci.yml |
| 12 Четыре быстрых джоба CI | ✅ | — | Локально, поимённо как в ci.yml (`logs/12-*.txt`): **lint** `ruff check .` → All checks passed (rc 0); **security** `bandit -r … olympiads -ll` → No issues identified (Medium 0, High 0), `pip-audit -r requirements/base.txt` → No known vulnerabilities found; **migrations** на СВЕЖЕЙ PG-базе `qls_ci_migrations_20260906` (qls_dev не пуста) → 99 миграций, `makemigrations --check` No changes detected, база удалена; **deploy-check** с переменными джоба из ci.yml → `System check identified no issues (1 silenced)`, rc 0. **CI GitHub**: run #112 (`183f632`, КТ1) — success, все пять джобов; run #113 (`800f322`, КТ2) — **failure**: упал только джоб «Тесты на PostgreSQL 17», шаг «Прогон (два шага)»; остальные четыре зелёные. Падение принесли слияния A2 (calc2/c13) или правки после них — воспроизводится фазой 13 локально на PostgreSQL |
| КТ3 (без остановки) | ✅ | `2ac4c123` документы, `91c4c1d7` тире | Отчёт по шаблону — раздел «КТ3 (без остановки)» ниже. Перед фазой 13 разобрано падение CI #113: `test_typography.EmDashTests` — четыре длинных тире из ветки calc2 (`60-overlays.js` ×2 — подсказка площади, `calc2.html` ×2 — пояснение квоты); ветка отделилась до уборки тире на main. Тем же приёмом (тире → двоеточие, в паре «ввозим/вывозим» — короткое тире); `test_typography` 4 OK; `panels_probe.mjs` проверяет подстроку «разных графиках» — цела. Карточка Notion «Задачи» — Готово |
| 13 Полный прогон PostgreSQL | ✅ | (этот коммит) | `scripts/run_tests.py problems catalog teacher student calc2 game calendar_stub config olympiads --settings=config.settings_test_pg --noinput` (`logs/13-full-run.txt`), `--parallel` не трогался. **Шаг A: Ran 4411 tests in 1090.9s — OK (skipped=1). Шаг B: Ran 8 tests in 270.6s — OK (skipped=4).** Код возврата 0. failures 0, errors 0. Причины пропусков при verbosity 1 не печатаются; по составу шага B — три `BitExactEncodingTests` (нет модели BGE-M3) и браузерная регрессия calc2 (node-раннер > 180 с). Известный красный calc2 (`calc2_math.mjs`, 40,375 px) в Django-прогон не попадает — он в пропуске раннера, доказан фазой 7 отдельно. Новых падений нет (тире починены до запуска). Числа вписаны в CLAUDE.md («Проверки перед сдачей») |
| 16 Обход сайта (ночная фаза) | ✅ | (этот коммит) | Команда обхода из полировки — `scripts/site_audit_probe.js` (боты `shot_bot*` уже в базе, записей не понадобилось). `bash scripts/polish_server.sh 8901` → `node scripts/site_audit_probe.js 8901 logs/16-audit.json` (4 мин 34 с) → сервер погашен. **Страниц: 19 адресов × роли (гость/ученик/учитель по доступу) × 3 ширины × 2 темы; ошибок консоли и разбора скриптов 0; ответов 4xx/5xx на свои запросы 0; внутренних ссылок проверено 75, битых 0.** Находок 8 — все об одном: `/catalog/problem/63321/` на 380 px едет вбок (документ 484 px; за краем `ARTICLE.pd-main`, `DIV.pd-acts`, `DIV.pp-rows`, `DIV.pp-row`; гость и ученик, обе темы). Это страница редизайна (`.pd-wrap`) — визуальный дефект, ночью не чинился → карточка «Задачи» (Надо) + «Вопросы к утру». Дополнительно коды гостя по 22 адресам curl-ом (`logs/16-guest-codes.txt`): публичные 12 → 200 (в т. ч. `/olympiads/vseros/`, `/textbook/`, `/calendar/` — открыт гостю), закрытые 8 → 302 на `/login/?next=…`, `/admin/` → 302 на `/admin/login/`, несуществующий → 404; 5xx нет |
| 17 План сессии B (только чтение) | ✅ | `7fc78bdf` | `reports/branch_sync_20260905/B_PLAN.md`: (а) 45 веток origin — предки integration (`logs/17-origin-branches.txt`), (б) пять хвостов — теги покрывают вершины на origin, (в) команды `git push origin --delete` по 10 в строку, (г) 29 локальных веток к `-d` + 5 к `-D` с причиной, (д) 11 worktree: 9 к сносу (3 с неучтённым — осмотр владельца), `qls-models` и `qls-olymp` остаются, (е) серверные команды из docs/SERVER.md с ожиданием хеша; ⚠️ nginx-конфиг менялся (`weconomics.ai` в `server_name`, коммит `2f7adb9`) — на сервере копируется руками через `nginx -t`. Ничего не выполнялось |
| 18 Утренний блок (владелец вернулся) | ✅ | CSS `4b22940c`, олимпиады `e9f06794`, журнал — этот коммит | **1. `/calendar/` гостю 200** — так задумано (решение 01.09 «Калькулятор и календарь открыты», design/landing-bg в main); в обходе список ролей у адреса — не ожидание, а кто по нему ходит; тест `problems/tests/test_feedback.py:243` уже держит `/calendar/` среди публичных — править нечего, вопрос закрыт. **2. finat** — диагноз: одна строка из 88 в `benefits.jsonl` (slug `finat`, Финуниверситет, БВИ, обществознание, уровень 3, источник fa-perechen-olimpiad-2026); по сырому документу (`data/olympiads/raw/benefits/fa-perechen-olimpiad-2026.pdf`, взят из `origin/wip/mac-leftovers-20260906` без вливания, стр. 1 п. 1) льгота записана ВЕРНО — «Финатлон для старшеклассников», Группа 4, БВИ +, 100 баллов +, уровень 3. Падала команда: олимпиады `finat` нет в `olympiads.jsonl`, а её карточку (организатор, адрес, вид, классы) из перечня не восстановить — по ADR 0067 не выдумываем. Сделано: `_load_benefits` пропускает льготу без олимпиады с предупреждением «ПРОПУЩЕНО: …» в отчёте (данные не тронуты); штатной очистки без демо не было — добавлен `--wipe` у `import_olympiads_data`, список удаления вынесен в `wipe_section()` и используется обеими командами (seed `_wipe` → он же); два теста (`MissingOlympiadTests`, `WipeTests`); `manage.py test olympiads` → **95 OK**. Локальная база: `import_olympiads_data --yes --wipe` (`logs/18-import-olympiads-real.txt`) → источники 37, олимпиады **17** (опубликовано 16), уровни 50, этапы 32 строки → 30 записей (две строки с одним ключом обновили одну запись), даты 15, баллы 9, программы 7, льготы **87** (+1 пропущена: finat), регионы **89**, комплекты 12; заглушек `is_placeholder` 0. Карточка «Задачи» finat → Готово; новая «Надо»: завести олимпиаду Финатлон. **3. Страница задачи 380 px** — замер тем же приёмом, что обход (`logs/18-width-before.txt`): виновник — выключная формула KaTeX 412 px в условии; колонка `.pd-grid` при ≤980 px была `1fr` без `minmax(0, …)`, min-content формулы растягивал `.pd-main` до 464. Правка точечная в `problem_detail.html`: `.pd-main, .pd-side { min-width: 0 }`, `minmax(0, 1fr)` в узкой раскладке, `.katex-display` и таблицы условия — `overflow-x: auto` (канон 1.9.1). Замер после (`logs/18-width-after.txt`): 380/768/1280 — ширина документа = окно (остаток «за краем» — невидимый MathML-слой KaTeX). Отдельного теста на ширину страницы задачи нет; `test_problem_page + test_catalog_redesign + test_no_slop + test_problem_test_page + test_nav + hygiene + typography` → **92 OK**. Карточка → Готово. **4. Разметка признаков задач** — закрыт решением владельца 06.09: к бете не требуется, файл даст прогон обогащения taxonomy-v2 (карточка «Разметить характер задачи и особенности…» уже в Notion). `check` чист; `makemigrations --check` → No changes detected; `ruff check olympiads catalog` чист |
| 14 Итог сессии | ✅ | `b2f45188` | Инварианты: четыре `??`; `check` чист; `makemigrations --check` → No changes detected; `main..HEAD` = 156 до этого коммита (157 с ним); шесть веток — предки HEAD; дубли ADR только 0013–0015; stash пуст; `main` = `origin/main` = `6b840611`; `qls-models` `772ac87e` не тронута; ignored-tracked без разницы с main. Копии баз сессии (`logs/*.sqlite3`) удалены; `db.sqlite3.bak_pre_sync_20260906` (932 МБ) оставлена владельцу. Notion: карточка задачи дополнена строкой «A1–A3 сделаны 06.09…»; комментарий в «Два ADR 0050/0051» (статус не менял); запись в «Результаты» 06.09; карточки «Задачи»: maxItems (Готово), тире calc2 (Готово), import_olympiads finat (Надо), страница задачи 380 px (Надо); «Решения»: заглушка «Учебник» (06.09). Отчёт и утренний список — раздел «Итог сессии» ниже |
| 15 Рабочая база `db.sqlite3` (разрешено заранее) | ✅ (шаг 5 пропущен, шаг 4 — демо) | — (база вне git) | **1.** На порту 8000 сидела цепочка `manage.py runserver` из `qls` (pid 20796→12816→27544→26876, автоперезагрузка) — сервер владельца; погашен `taskkill /T` (действие вне репозитория, по разрешению фазы 15). **2.** Копия `db.sqlite3.bak_pre_sync_20260906`, 932 548 608 байт = оригинал. **3.** `migrate --plan` (`logs/15-migrate-working-db.txt`) — ровно 10: olympiads 0002–0006, problems 0050_problem_character_features, 0051_catalog_attempt, 0052_hint_ai_flags, 0053_hint_reviewed_backfill, 0054_merge (0047 и beta-polish 0050–0052 уже стояли); `migrate` 28 с без ошибок; неприменённых 0. **4.** `import_olympiads_data` без `--yes` — план: 37 источников, 17 олимпиад, 50 уровней, 32 этапа, 15 дат, 9 баллов, 7 программ, 88 льгот, 89 регионов, 12 комплектов. `--yes` — **упал** в `_load_benefits`: `Olympiad.DoesNotExist` — `benefits.jsonl` ссылается на slug `finat` (Финуниверситет, коммит `0d8394f` сессии 2), которого нет в `olympiads.jsonl`; остальные файлы ссылаются только на существующие slug. Команда атомарна — все таблицы olympiads остались по нулям. По ночному правилу («раздел остался пустым») — `seed_olympiads_demo` план → `--yes`: 21 олимпиада (16 main + 5 related), 4 этапа/4 даты у vseros, 7 программ, 21 льгота, 14 баллов, 12 комплектов, 85 регионов, все 11 инвариантов сошлись, `is_placeholder=True` (`logs/15-seed-olympiads.txt`). Данные `data/olympiads/out` не правились — карточка «Задачи» (Надо) + «Вопросы к утру». **5.** `import_problem_attributes` — **пропущено: файла разметки нет** (ни `reports/problem_attributes/`, ни `*attr*.jsonl` в дереве; команда ждёт путь к JSONL аргументом; по коду пишет только `character` и `features` — P0 не нарушала бы) |

## Теги (фаза 0)

| Тег | Вершина |
|---|---|
| `backup/main-before-sync-20260905` | `6b840611` |
| `archive/feat-calc2-map-21aug` | `766c68ee` |
| `archive/feat-import-new-sources` | `e53d76d5` (локальная, впереди origin `94327a68`) |
| `archive/feat-calc2-trade-and-ui` | `af4ab67f` |
| `archive/feat-calc2-mono-surpluses` | `cd3ba208` |
| `archive/feat-calc2-panels-and-keypoints` | `5444086d` |
| `archive/chore-corpus-consolidation-20260822` | `001828e4` |
| `archive/backup-search-eval-c14-before-rebase` | `5b18366b` |

## Хвосты wip/* (фаза 0б)

| Ветка | Где | Вершина | Что внутри |
|---|---|---|---|
| `wip/search-eval-c14-leftovers` | `qls-search-eval` | `571d056e` | `docs/EMBEDDINGS.md`, `problems/data/eval_set_c_v3.json`, `problems/data/manual_search_queries_65.md`. Расшифровка `session_c14_transcript_20260829.md` осталась неучтённой — намеренно |
| `wip/sol-vs-glm-scripts` | `qls-sol` | `169bd39a` | `sol_enrich_run.py`, `scripts/sol_vs_glm_blind.py`, `scripts/sol_vs_glm_compare.py`; status пуст |
| `wip/c13-tooling-stash` | `qls` (от `0729a47`) | `70b0195e` | содержимое stash: `problems/ai/core.py`, `problems/ai/prompts.py`, `build_eval_set_b.py`, `test_eval_set_b.py`. Stash удалён при чистом применении. На ветке c13 папка `deploy_fixtures_bank/` неучтённая — в индекс не добавлялась |

`qls_palette/_incoming/` и `qls-gate-revert/tatus` — не тронуты (сессия B).

### Опись неучтённого в `qls`

- В корне на всех ветках: `.txt`, `Claude outputs/`, `claude/`,
  `session_c15_transcript_20260830.md` — не трогать (поправка 2).
- На ветке `feat/embeddings-c13-diagnostics` (и `wip/c13-tooling-stash`):
  `deploy_fixtures_bank/` — не трогать, в индекс не добавлять (поправка 7).
- `reports/branch_sync_20260905/logs/` — выводы команд этой сессии, на диске,
  в git не идут (поправка 5).

### Для чек-листа приёмки (фаза 14)

- Окно «Все фильтры» каталога: подписи блоков короткие («Микро», «Макро»,
  «Финансы», «Математика», «Прочее»), точки блоков и чипы тем красятся пятью
  цветами блоков (поправка 4).

## Фаза 5: разрешение конфликтов каталога

Основа файлов каталога — catalog-redesign (решение Notion 05.09: «редизайн
сливается первым, Полировка подстраивается»). Точечные правки beta-polish
перенесены внутрь новой структуры.

| Файл | Как решено |
|---|---|
| `catalog/filters.py` | Объединение обеих сторон: импорты редизайна (`topic_blocks`) + `TOPIC_GROUPS` из `problems.sections.canonical_groups()` (beta-polish). Объединение разрезало `tuple(` по закрывающей скобке — блок переставлен: импорты, затем `TOPIC_GROUPS` со своей скобкой |
| `catalog/topic_blocks.py` (редизайн, без конфликта в git) | ⚠️ **Содержательное решение.** Редизайн нёс свою таблицу пяти блоков (`BLOCKS`, 23+29 названий) и СЕМЬ цветов разделов карты (`base/market/firm/state/macro/fin/tools`); beta-polish заменил токены `--map-g-*` на ПЯТЬ (`micro/macro/fin/math/other`) и завёл `problems/sections.py`. Решение Notion 05.09 прямо: «таблица названий переезжает в sections.py; topic_blocks становится тонким импортом; семь цветов отвергнуты». Сделано ровно это: `topic_blocks.py` переписан как тонкий слой — `BLOCKS` строится из `SECTIONS`/`CANONICAL_SECTION`/`V2_TOPIC_NAMES`, `section_of` = блок, `BLOCK_SECTION = {key: key}`, запасной цвет `other`; сохранены `normalize` (нестрогое сравнение), `is_known`, `block_of`, `order_in_block`, `block_label`. Порядок тем в блоке — порядок `CANONICAL_SECTION` (живые 23), затем v2 по номерам. `git grep Микроэкономика -- '*.py'` вне `problems/sections.py` находит только команды импорта и тесты источников — захардкоженных блоков нет. **Видимое следствие для приёмки:** подписи блоков в окне фильтров стали короткими («Микро», «Макро», …, как на карте и в тренажёре — решение 04.09 «подписи короткие»), а чипы/облачка тем красятся пятью цветами блоков вместо семи цветов карты |
| `catalog/views.py` | Конфликт: старый цикл похожих (main+beta-polish) против блока `saved` редизизайна → взят редизайн (похожие у него живут в `_similar_cards`). В `_similar_cards` добавлен ключ `title_display`: настоящий заголовок → `similar_title(s)` (beta-polish: обрывок формулы срезается по незакрытому доллару, валюта остаётся), заголовок-обрезок условия или пустой → `cut_words(preview, 120)` (редизайн). `similar_title`, `_last_unpaired_dollar`, `_RX_PLAIN_NUMBER`, `textbook`, `LANDING_OLYMPIADS = '25'` — слились автоматически, на месте. Запасной цвет `'tools'` → `'other'` (2 места) |
| `catalog/templates/catalog/problem_detail.html` | Оба конфликта → редизайн (`.pd-wrap` 1120, две колонки). Строка `.page-wrap { max-width: var(--w-read); }` **не добавлена** (ADR 0070 + решение 05.09). Старые классы main (`.problem-meta`, `.tag-pill`, `similar-block`) ушли вместе со старой разметкой — редизайн их не использует. В карточке похожей задачи `{{ s.title }}` → `{{ s.title_display }}` с `{% comment %}`; многострочных `{# #}` нет (`git grep "{#"` по файлу пуст) |
| `catalog/static/catalog/js/catalog_filters.js` | запасной цвет `'tools'` → `'other'` (1 место) |
| `catalog/CLAUDE.md` | абзац про блоки тем переписан: источник — `problems/sections.py`, `topic_blocks` — тонкий слой |
| `CLAUDE.md` | три конфликта (шапка + NOTION-SYNC); у обеих сторон «Обновлено: 2026-09-04» — ничья, взят HEAD (beta-polish, уже в дереве); блок пересобирается в фазе 11. Счётчик «На проверке»: 205 у beta-polish против 215 у редизайна — пересчитать в фазе 11/13 |
| `CLAUDE_ARCHIVE.md` | обе записи; запись редизайна (09-04) переставлена выше записей 09-03 — порядок по датам, текст не тронут |

### Тесты, подстроенные под слитое дерево (устаревшие утверждения, не новые тесты)

| Тест | Было | Стало | Почему |
|---|---|---|---|
| `catalog/tests/test_catalog_redesign.py`, `test_catalog_modal.py`, `test_filters_multi.py`, `test_problem_page.py` — 11 утверждений | цвета `firm`/`tools`/`macro` (семь разделов карты), подпись «Макроэкономика» | `micro`/`other`, «Макро» | семь цветов отвергнуты решением 05.09; `--map-g-firm` в `_tokens.html` больше не существует (beta-polish); `test_sections_match_the_map_file` сравнивает с `topic_map.json`, где групп уже пять |
| `test_catalog_redesign.test_exactly_one_typing_implementation_in_the_repository` | `str(path.relative_to(BASE))` | `.as_posix()` | тест писался на Mac и на Windows падал бы и без слияния (разделитель `\`); CI на Linux его не ловит |
| `config/tests/test_nav.ContentWidthTests.test_reading_pages_narrow_themselves` (beta-polish) | требовал `.page-wrap 860` в `problem_detail.html` | страница задачи убрана из списка чтения, в докстринг — ссылка на ADR 0070 и решение 05.09 | прямое следствие правила фазы 5 «строку не добавлять» |
| `catalog/tests/test_no_slop.NoPromisesInTemplatesTests` (редизайн) | нашёл «скоро» в `textbook.html` (заглушка учебника beta-polish) | `EXEMPT = ('textbook.html',)` с объяснением | ⚠️ **столкновение двух решений владельца от 04.09**: заглушка учебника обязана показывать ровно «Скоро.» (beta-polish, сторожит `test_nav.test_page_opens_for_guest`), а правило «без обещаний» редизайна писалось для экранов каталога. Выбрано исключение для заглушки, а не переписывание текста владельца. **Нужно подтверждение владельца на КТ1**; альтернатива — другое слово на заглушке |

## КТ3 (без остановки) — блок A3: номера ADR, документы, четыре джоба

```
КТ3 — блок A3 (без остановки, ночной режим)
HEAD integration/sync-20260905: 91c4c1d7 (тире) ← 2ac4c123 (документы) ← 9a7c6ac6 (ADR) ← 583d0be4 (журнал ночного режима)
  коммитов над main: 153 (149 на КТ2 + журнал ночного режима + ADR + документы + тире)
ADR: 13 переименований (0017→0077; 0070–0074 редизайна→0078–0082; 0054–0059 calc2→0083–0088; 0036 c13→0089);
  ссылки путями — 8 файлов, голые упоминания — 22 файла; дубли только 0013–0015; старых слагов 0;
  битых путей после сессии 0 новых (0034 из c13 — файл в taxonomy-v2; site_polish PROGRESS — исторические строки)
Документы: CLAUDE.md (шапка 06.09, P0 про makemigrations без имени приложения, olympiads в bandit и run_tests,
  четыре команды добавлены, «Текущий фокус» из Notion), .github/workflows/ci.yml (olympiads в security и tests),
  DESIGN.md §1.9 (четыре страницы чтения + исключение 1120), docs/TESTING.md (scripts/tests discover),
  CLAUDE_ARCHIVE.md (запись «2026-09-05/06 · Синхронизация веток»)
Четыре джоба локально: lint ✅ ruff 0 · security ✅ bandit 0/0, pip-audit чист · migrations ✅ 99 на свежей PG,
  No changes detected · deploy-check ✅ rc 0 (1 silenced)
CI GitHub: #112 (КТ1) ✅ пять джобов · #113 (КТ2) ❌ только tests — test_typography, 4 тире из ветки calc2 → починено 91c4c1d7
git status: четыре ??, журнал — правится
Дальше: фаза 13 (полный прогон на PostgreSQL, фон) → 15 → 16 → 17 → 14
```

## Итог сессии (фаза 14) — отчёт по шаблону

```
Итог — блоки A1–A3 + ночные фазы 13, 15, 16, 17
HEAD integration/sync-20260905: коммит журнала фазы 14 (предыдущий — 3fb3cd08); коммитов над main: 157
  (формула: 6 веток = 23+5+27+26+24+29 = 134 · 6 merge · 17 служебных: журнал ×9, миграция 0054 ×2,
   карта calc2, схема attempts, ADR, документы, тире, числа прогона)
Влито: feat/beta-polish-0904 13b3e1f · feat/scoped-test-runner 1690397 · origin/feat/olympiads-screens 128391e ·
  origin/feat/catalog-redesign 36de913 · origin/feat/calc2-monoexport-one-chart aca9bd2 · feat/embeddings-c13-diagnostics 0729a47
Конфликты и как решены: журналы — объединение / сторона с поздней датой; .gitignore — объединение;
  catalog/filters.py — редизайн + TOPIC_GROUPS из sections; catalog/topic_blocks.py — тонкий слой над problems/sections.py
  (пять блоков, пять цветов); catalog/views.py — редизайн + title_display через similar_title; problem_detail.html —
  1120 без .page-wrap 860; prompts.py и test_template_hygiene.py — объединение без потерь
Миграции: problems — один лист 0054_merge (зависимости 0052_feedback, 0053_hint_reviewed_backfill, 0047_problem_figure_raster),
  файлы не перенумерованы; olympiads 0001–0006; с нуля на PostgreSQL 99 миграций; путь обновления и откат — на копии; локальная
  db.sqlite3 мигрирована (10 новых)
Тесты: полный прогон PostgreSQL — A 4411 OK (skipped 1), B 8 OK (skipped 4), код 0; известные красные: calc2_math.mjs
  «Регулятор сцены» 40,375 px — тот же на чистом main (не регрессия); control_numbers 512/512
Отклонения от задания: рабочая база SQLite, не PostgreSQL (поправка 3); logs/ вне git (поправка 5); Docker Desktop
  перезапущен после удаления сокета; два кода-исправления после слияний (карта calc2, схема attempts) + тире из calc2;
  import_olympiads_data не прошёл (finat) — раздел на демо; import_problem_attributes — файла нет
Нужны решения владельца (утро): finat в olympiads.jsonl; страница задачи 380 px; /calendar/ гостю 200; удалить ли
  db.sqlite3.bak после приёмки; integration после перемотки main
Команды владельцу: git push origin integration/sync-20260905
Дальше: утренний список ниже → сессия B по B_PLAN.md
```

### Утренний список владельца

1. `git push origin integration/sync-20260905` → пять джобов CI на GitHub (локально все зелёные; #113 падал на
   тире — починено).
2. Проверить Actions: https://github.com/malinovskiy-makar/qls/actions — новый run на вершине ветки.
3. `venv313\Scripts\python.exe manage.py runserver` (база уже мигрирована, олимпиады — демо) → чек-лист приёмки:
   - `/` — шапка с пятью блоками и пунктом «Учебник», тёмная тема;
   - `/catalog/` — поле поиска, множественный выбор, окно «Все фильтры»: **подписи блоков короткие («Микро», «Макро»,
     «Финансы», «Математика», «Прочее»), точки блоков и чипы тем — пятью цветами блоков**; живой счётчик;
   - `/catalog/problem/<id>/` — полоса 1120, карточка чата справа, похожие задачи без обрывков формул
     (⚠️ на 380 px едет вбок — карточка Надо);
   - `/catalog/map/`, `/olympiads/`, `/olympiads/vseros/` (демо-данные, is_placeholder);
   - `/calc2/` — сцены «Монополист и внешний рынок» и «Международная торговля»;
   - регистрация и профиль с аватаром, вход в группу по коду приглашения, клавиатура формул, виджет обратной связи,
     `/textbook/` — «Скоро.».
4. Ответы на «Вопросы к утру» (finat, 380 px, /calendar/).
5. Сессия B по `reports/branch_sync_20260905/B_PLAN.md`: перемотка main → прод (nginx-конфиг руками) → теги и
   wip/* на origin → удаление 46 веток origin, 34 локальных, 9 worktree.

## Поправки владельца

1. **06.09, фаза −1.** Строка таблицы фактов про `calc2-monoexport` ошибочна —
   ветка только на origin, как olympiads и catalog-redesign. В фазе 7 брать
   `origin/feat/calc2-monoexport-one-chart` напрямую, локальную ветку не создавать.
2. **06.09, фаза −1.** `Claude outputs/` — четвёртый неучтённый элемент: не
   трогать, в git не добавлять, в `.gitignore` не вносить. Во всех инвариантах
   «три `??`» читать как «четыре `??`».
3. **06.09, КТ1.** «Учебник»: текст «Скоро.» остаётся, исключение
   `EXEMPT=('textbook.html',)` в `test_no_slop` остаётся с комментарием в одну
   строку (заглушка раздела и есть обещание раздела). Карточка в Notion «Решения».
4. **06.09, КТ1.** Пять блоков, пять цветов, короткие подписи в окне фильтров —
   подтверждено; пункт «подписи блоков в окне „Все фильтры“ и цвета чипов»
   добавить в чек-лист приёмки фазы 14.
5. **06.09, КТ1.** `reports/branch_sync_20260905/logs/` в git не коммитить:
   правило в `.gitignore` под исключением, из индекса убрано (`git rm --cached`,
   файлы на диске). В журнале — выдержки и числа.
6. **06.09, КТ1.** Инвариант «`git ls-files -ci --exclude-standard` пуст» читать
   как «не больше 105 и без новых путей относительно main» — проверять разницей
   списков (`diff <(… --with-tree=main) <(…)`), не числом.
7. **06.09, КТ1.** `deploy_fixtures_bank/` — не трогать, в индекс не добавлять.

### 06.09, КТ2 — НОЧНОЙ РЕЖИМ (текст владельца целиком, единственный источник новых правил после сжатия контекста)

> продолжай. НОЧНОЙ РЕЖИМ: владелец уходит спать, дальше — до конца без остановок. Первое действие: записать этот текст целиком в `reports/branch_sync_20260905/PROGRESS.md`, раздел «Поправки владельца» — после сжатия контекста это единственный источник новых правил. Второе: `git config --global user.name "Makar Malinovskiy"` и `git config --global user.email mmakarghost@gmail.com` — все дальнейшие коммиты под этой подписью (старые не трогать).
>
> **Решения владельца по КТ2**
>
> 1. Правку `catalog/attempts.py` (снятие `maxItems` из схемы structured output) подтверждаю. Это найденный и починенный баг редизайна: карточка в Notion «Задачи» — «catalog/attempts.py: maxItems в схеме проверки решений — Anthropic structured output отвечает 400», статус «Готово», направление «Каталог и поиск»; в заметках: найдено сторожем из embeddings-c13 при слиянии 06.09, `validate()` режет `steps[:MAX_STEPS]`, ограничение в схеме было лишним. Упомянуть в записи CLAUDE_ARCHIVE.md (фаза 11).
> 2. Docker Desktop — оставить запущенным до конца сессии. Удаление сокета `sailor-ingest.sock` и перезапуск Docker записать в журнал как действие вне репозитория.
> 3. Рабочая локальная база — SQLite `db.sqlite3` (~0,9 ГБ, около 41 тыс. задач): везде, где задание говорит «рабочая локальная база PostgreSQL», читать «`db.sqlite3`».
> 4. В журнал: CI на GitHub по `integration/sync-20260905` — run #112 (`183f632`, состояние КТ1) завершён успешно, все пять джобов, 11 минут; run #113 (`800f323`, КТ2) запущен — результат вписать в фазе 12 (`https://github.com/malinovskiy-makar/qls/actions`, читать без входа).
>
> **Изменения режима на ночь**
>
> - **КТ3 отменяется.** После фазы 12 — сразу фаза 13. Отчёт по шаблону всё равно записать в журнал как «КТ3 (без остановки)».
> - **Вопросов владельцу до утра нет.** Развилка, не описанная здесь: выбрать безопасный вариант (ничего не удалять, не пушить, тексты задач не трогать), записать в журнал в раздел «Вопросы к утру» и продолжать; если развилка блокирует — остановиться с отчётом по шаблону.
> - **Порядок фаз:** 10 → 11 → 12 → 13 → 15 → 16 → 17 → 14 (итог — последним).
> - **Фаза 12, pip-audit:** если падает по сети (VPN) — записать «локально не проверено, проверит CI», не стоп.
> - **Фаза 13, полный прогон:** запускать в фоновом режиме инструмента с выводом в `reports/branch_sync_20260905/logs/13-full-run.txt`; проверять хвост файла каждые несколько минут; ждать до конца (до 60 минут); не обрывать; `--parallel` руками не трогать. Новое падение в коде: если причина — слияние и есть тест, который её ловит (по образцу `maxItems`), — точечная правка, тест зелёный, запись в журнал и карточка «Задачи» (Готово); причина непонятна — не чинить наугад: в «Вопросы к утру», остальные фазы продолжить, итоговый статус «жёлтый».
> - **Фаза 15 разрешена заранее** (это и есть «да» владельца), строго в таком порядке:
>   1) убедиться, что `db.sqlite3` никем не занят (runserver и другие процессы python погашены);
>   2) копия файла `db.sqlite3` → `db.sqlite3.bak_pre_sync_20260906`, сверить размеры;
>   3) `manage.py migrate --plan` → logs; `manage.py migrate`; `manage.py showmigrations` — всё применено, число новых миграций в журнал (ожидание: olympiads 0002–0006, problems 0050–0054 цепочки редизайна; 0047 и 0052 уже стояли);
>   4) `manage.py import_olympiads_data`: прочитать код команды, найти флаг сухого прогона/плана — сначала он, потом запись; если раздел остался пустым — `manage.py seed_olympiads_demo --yes`; числа (олимпиады, этапы, льготы, регионы) в журнал;
>   5) `manage.py import_problem_attributes`: сначала прочитать код — какой файл она ждёт и какие поля пишет. Запускать ТОЛЬКО если файл существует И команда не правит `statement` / `answer` / `solution` (P0). Иначе записать «пропущено: <причина>».
> - **Фаза 16 (новая): обход сайта.** Найти команду обхода страниц из бета-полировки (фаза 8 «обход сайта, границы доступа»): искать в `*/management/commands/`, `scripts/`, тестах по словам «обход», «crawl», «walk», «smoke». Если есть: поднять `runserver` в фоне на свободном порту (8000 или 8001), прогнать обход на мигрированной базе, записать: страниц всего, распределение кодов 200/3xx/4xx/5xx, список не-200 с адресами; погасить runserver. Скриншотов нет — только коды. Команды нет — пропустить с пометкой.
> - **Фаза 17 (новая, только чтение): план для сессии B** в `reports/branch_sync_20260905/B_PLAN.md`: (а) список веток origin, которые станут предками `main` после перемотки — `git merge-base --is-ancestor origin/<b> HEAD` для каждой `origin/*`, кроме `main`, `integration/sync-20260905`, `feat/taxonomy-v2-openai-provider`, `feat/olympiad-text-dedup`, `wip/*`; (б) хвосты с архивными тегами (`feat/calc2-map-21aug`, `feat/import-new-sources`, `feat/calc2-trade-and-ui`, `feat/calc2-mono-surpluses`, `feat/calc2-panels-and-keypoints`) с проверкой, что тег покрывает вершину; (в) готовые команды `git push origin --delete …` (по 10 веток на строку); (г) локальные ветки к удалению с результатом проверки «предок main / внутри taxonomy-v2 / есть тег»; (д) worktree к сносу и что в них неучтённого; (е) серверные команды деплоя с подставленным хешем HEAD. Ничего не выполнять.
> - **Фаза 14 (итог) — последняя.** Отчёт по шаблону плюс «Утренний список владельца»: 1) `git push origin integration/sync-20260905` → CI; 2) проверить Actions; 3) `runserver` → чек-лист приёмки (включая подписи блоков и цвета чипов в окне «Все фильтры»); 4) сессия B по `B_PLAN.md`. Notion — как в фазе 14 задания.

Действия вне репозитория (по пункту 2): в фазе 9 удалён старый сокет-файл `C:\Users\shipu\AppData\Local\Docker\run\sailor-ingest.sock` (Docker Desktop не стартовал: «The file cannot be accessed by the system»), Docker Desktop перезапущен и оставлен работающим; подняты dev-контейнеры `qls_postgres_dev` и `qls_redis_dev`.

CI (по пункту 4): run #112 (`183f632`, КТ1) — успешно, пять джобов, 11 мин; run #113 (`800f323`, КТ2) — запущен, результат в фазе 12.

## Вопросы к утру

1. ✅ ЗАКРЫТ (фаза 18). **`import_olympiads_data` падает на `benefits.jsonl`**: льготы olympiad `finat`
   без записи олимпиады в `olympiads.jsonl` (см. фазу 15, карточка «Задачи» —
   Надо). Раздел `/olympiads/` на локальной базе сейчас на демо-данных
   (`seed_olympiads_demo`, `is_placeholder=True`). Решение владельца: добавить
   `finat` в `olympiads.jsonl` или убрать её льготы, затем `seed … --wipe` и
   повторный импорт. Данные не трогал.
2. ✅ ЗАКРЫТ решением владельца 06.09: к бете не требуется, файл разметки даст прогон обогащения taxonomy-v2 (карточка «Разметить характер задачи и особенности…» уже в Notion). Разметки признаков задач (`import_problem_attributes`) нет — облачка
   характера/особенностей и две группы фильтров не появятся (правило нуля,
   не поломка). Ждёт файла владельца.
3. ✅ ЗАКРЫТ (фаза 18). **Страница задачи редизайна на 380 px едет вбок** (документ 484 px,
   `.pd-main/.pd-acts/.pp-rows`) — единственная находка обхода фазы 16;
   канон 1.9.1 запрещает горизонтальную прокрутку. Карточка «Задачи» (Надо).
   Ночью не правилось — визуальная работа под глаза владельца.
4. ✅ ЗАКРЫТ (фаза 18, так задумано — решение 01.09). `/calendar/` отвечает гостю 200 (в списке пробы адрес числится для ученика
   и учителя). Возможно, так и задумано — проверить на приёмке.


### 06.09, перед сессией B — фаза B0: CI красный (текст владельца целиком)

> Перед сессией B — фаза B0: CI красный, разобраться и починить. Первое действие: записать этот текст целиком в `reports/branch_sync_20260905/PROGRESS.md`, раздел «Поправки владельца» (как делали с ночным режимом). B1 не начинать, пока CI по интеграционной ветке не зелёный.
>
> **Что известно (владелец скачал логи трёх красных прогонов Actions, разбор сделан)**
>
> 1. **`integration/sync-20260905` @ `03ebe57`, run #114** (https://github.com/malinovskiy-makar/qls/actions/runs/34024626960): четыре быстрых джоба зелёные (ruff 33 с, bandit/pip-audit 49 с, миграции с нуля 54 с, продакшен-настройки 22 с). «Тесты на PostgreSQL 17»: шаг A — `Ran 4413 tests`, `FAILED (failures=1, skipped=5)`; шаг B — 8 тестов OK, calc2-регрессия 238/238. Единственный провал:
>
>    FAIL: test_table_does_not_force_full_width (problems.tests.test_rendering.TableCssTests.test_table_does_not_force_full_width)
>    AssertionError: Regex matched: 'width: 100%' matches 'width\\s*:\\s*100%' in ' display: block; max-width: 100%; overflow-x: auto; '
>
>    Причина (проверить, а не верить на слово): утренний коммит `4b22940` («Страница задачи: на узком экране не едет вбок») добавил в `catalog/templates/catalog/problem_detail.html` строку 74 — `.math-content table { display: block; max-width: 100%; overflow-x: auto; }`. Это ВТОРОЕ правило для того же селектора, и стоит оно раньше исходного на строке 149 — `.math-content table { border-collapse: collapse; margin: .75em 0; }`. Тест (`problems/tests/test_rendering.py`, строки 333–337) берёт ПЕРВОЕ правило `.math-content table {…}` и проверяет `assertNotRegex(m.group(1), r'width\s*:\s*100%')` — у регулярки нет левой границы, и она ловит `max-width: 100%`. Дефекта два: (а) регулярка проверяет не то, что обещает докстринг «не растягивать таблицу без нужды» — `max-width` как раз НЕ растягивает, а ограничивает; (б) два правила на один селектор в одном файле. Полный прогон фазы 13 был ДО этого коммита; после правки CSS запускался только замер ширины, тесты шаблона — нет. Вот почему локально «A 4 411 OK», а CI красный.
>
> 2. **`feat/taxonomy-v2-openai-provider` @ `772ac87`** (прогон 06.09 02:07 МСК — пуш владельца) и **`wip/sol-vs-glm-scripts` @ `169bd39`** (закладка стэша из A1): красные 6 тестов контраста (`test_readable.ActivityCellContrastTests` ×2, `test_small_fixes.DarkButtonContrastTests` ×2, `test_obzor_review.PendingColourTests` ×2 — ERROR) плюс `test_design_canon.CanonBrowserChecks.test_canon` в шаге B; на wip ещё `test_glm_ramp_probe.RunOneLevelTests.test_метрики_считаются_из_прогона` (12 != 8). Обе ветки стоят на `a6f9283` «Новая цветовая палитра» и не содержат 134 коммита main — в том числе правки токенов (`templates/_tokens.html`: `--act-a1..3`, `--surface`) и обновлённые тесты контраста. К интеграционной ветке отношения не имеет. **НЕ чинить, в этих ветках ничего не трогать:** wip — закладка; taxonomy-v2 получит main при подготовке к слиянию, тогда и перепроверить. Только запись в журнал и Notion (B0.5–B0.6).
>
> **Шаги**
>
> **B0.1. Воспроизвести локально на PostgreSQL** (docker-compose.dev.yml поднят, Docker не гасить):
> venv313\Scripts\python.exe manage.py test problems.tests.test_rendering --settings=config.settings_test_pg
> Ожидание: ровно один провал, тот же самый. Провала нет или он другой — стоп, отчёт по шаблону.
>
> **B0.2. Правка — минимальная, ничего сверх этого:**
> - `problems/tests/test_rendering.py`, строка 337: `r'width\s*:\s*100%'` → `r'(?<![-\w])width\s*:\s*100%'`. Голый `width: 100%` по-прежнему запрещён; `max-width` / `min-width` регулярку не задевают. В докстринг тест-метода добавить одну фразу: «`max-width: 100%` допустим — он не растягивает, а ограничивает».
> - `catalog/templates/catalog/problem_detail.html`: два правила `.math-content table` слить в одно на строке 149 — `.math-content table { border-collapse: collapse; margin: .75em 0; display: block; max-width: 100%; overflow-x: auto; }`; строку 74 убрать. Комментарий ⚠️ про 380 px и строку 73 (`.math-content .katex-display`) оставить как есть. Поведение CSS не менять: `max-width: 100%` оставить — он страхует от `<table width=…>` в старых условиях.
>
> **B0.3. Зубастость.** Сначала закоммитить B0.2 (сообщение: «test_rendering: регулярка width:100% ловила max-width; два правила .math-content table слиты в одно»). Затем временно вписать в это правило `width: 100%;` → тот же прогон → должен покраснеть именно `test_table_does_not_force_full_width`; убрать → зелёный. Временную правку не коммитить, `git status --short` пуст.
>
> **B0.4. Соседи**, все с `--settings=config.settings_test_pg`: `problems.tests.test_rendering catalog.tests config.tests.test_nav`. Все зелёные, числа в журнал. Плюс замер ширины документа тем же приёмом, что в фазе 18 (`site_audit_probe.js`): 380 / 768 / 1280 — ширина документа равна окну; числа в журнал.
>
> **B0.5. Журнал** `PROGRESS.md`, раздел «B0. CI #114»: причина, правка, хеш коммита, результаты зубастости и соседей, числа замера. Отдельный абзац про два других красных прогона (taxonomy-v2 и wip) с формулировкой «не относится к интеграции; перепроверить после слияния main в taxonomy-v2». Одной строкой в `docs/TESTING.md`, где описан быстрый круг: «после правки шаблона гонять тесты шаблона (`problems.tests.test_rendering`, `catalog.tests`, `config.tests.test_nav`), а не только замер». Этот коммит — отдельный.
>
> **B0.6. Notion.** Карточка в «Задачи» уже есть: «CI красный на integration/sync-20260905: test_rendering ловит max-width как width: 100%», ID `3d3b11c9-2bc1-8141-aaaa-f544d2f83be3`. После зелёных соседей — статус «Готово», в «Заметки» дописать хеш коммита. Про taxonomy-v2: поискать в «Задачи» карточку о подготовке `feat/taxonomy-v2-openai-provider` к слиянию; есть — дописать строку «CI на 772ac87 красный: 6 тестов контраста + test_canon, старая база a6f9283; перепроверить после merge main»; нет — новая карточка, статус «Надо», направление «Техническое». Ничего в Notion не удалять.
>
> **B0.7. Команда владельцу:** `git push origin integration/sync-20260905`. Затем ждать CI #115 (https://github.com/malinovskiy-makar/qls/actions, читать без входа): все пять джобов зелёные, числа шага A/B в журнал. Пока CI не зелёный — B1 не начинать. Отчёт по шаблону: что сделано / результат с цифрами / чего не смог / что записано в Notion.
>
> Модель: та же сессия (Sonnet). Effort: High.


## B0. CI красный на run #114 — test_rendering ловил max-width как width:100%

**Причина (подтверждено, не только по описанию владельца).** Утренний коммит
`4b22940` («Страница задачи: на узком экране не едет вбок») добавил в
`catalog/templates/catalog/problem_detail.html` ВТОРОЕ правило для селектора
`.math-content table` (строка 74) — оно стояло раньше исходного правила на
строке 149. Тест `problems/tests/test_rendering.py::TableCssTests::
test_table_does_not_force_full_width` берёт через `re.search` ПЕРВОЕ
совпадение и проверяет `assertNotRegex(…, r'width\s*:\s*100%')` — регулярка
без левой границы ловит `max-width: 100%` из нового правила. Дефекта два:
регулярка не различает `width` и `max-width` (а `max-width` как раз не
растягивает, что и требует тест), и в файле было два правила на один
селектор. Полный прогон фазы 13 прошёл ДО коммита `4b22940`; после него
гонялся только замер ширины браузером (тест шаблона не входил в тот список).

**B0.1 Воспроизведено** локально на PostgreSQL
(`--settings=config.settings_test_pg`): ровно один провал, тот же самый
(`logs/b0-repro-before.txt`).

**B0.2 Правка.** `problems/tests/test_rendering.py`: регулярка
`r'width\s*:\s*100%'` → `r'(?<![-\w])width\s*:\s*100%'` (голый `width:
100%` по-прежнему запрещён, `max-width`/`min-width` регулярку не задевают),
докстринг дополнен фразой про `max-width`. `problem_detail.html`: два
правила `.math-content table` слиты в одно на месте исходного (строка 149:
`border-collapse`, `margin`, `display: block`, `max-width: 100%`,
`overflow-x: auto`); дублирующая строка 74 убрана; поведение CSS не
изменилось. Коммит `1dfd956e`.

**B0.3 Зубастость.** После коммита правки временно вписано `width: 100%;` в
слитое правило → прогон покраснел именно `test_table_does_not_force_full_
width` (`FAILED (failures=1)`); правка убрана без коммита, `git status
--short` пуст (кроме четырёх неучтённых с корня).

**B0.4 Соседи** (`--settings=config.settings_test_pg`):
`problems.tests.test_rendering catalog.tests config.tests.test_nav` →
**372 OK** за 242 с (`logs/b0-neighbors.txt`). Замер ширины тем же приёмом,
что фаза 18 (`/catalog/problem/63321/`, `documentElement.scrollWidth`):
**380/768/1280 — ширина документа равна окну** на всех трёх
(`logs/b0-width-measure.txt`); элементы «за краем» на 380 px — тот же
невидимый MathML-слой KaTeX, что и в фазе 18, не документ.

**Не относится к интеграции (не чинить).** CI-логи, скачанные владельцем,
показывают красные прогоны ещё на двух ветках: `feat/taxonomy-v2-openai-
provider` @ `772ac87` (пуш 06.09 02:07 МСК) и `wip/sol-vs-glm-scripts` @
`169bd39` — обе стоят на `a6f9283` «Новая цветовая палитра» и не содержат
134 коммита `main`, включая правки токенов (`templates/_tokens.html`:
`--act-a1..3`, `--surface`) и обновлённые тесты контраста. Красные: шесть
тестов контраста (`test_readable.ActivityCellContrastTests` ×2,
`test_small_fixes.DarkButtonContrastTests` ×2,
`test_obzor_review.PendingColourTests` ×2 — ERROR) и
`test_design_canon.CanonBrowserChecks.test_canon`; на `wip` дополнительно
`test_glm_ramp_probe.RunOneLevelTests.test_метрики_считаются_из_прогона`
(12 != 8). **Перепроверить после слияния `main` в `taxonomy-v2`** — этой
сессии не касается: `wip/sol-vs-glm-scripts` — закладка стэша A1,
`taxonomy-v2` — живая работа, обе ветки не трогались.

## Для будущего слияния taxonomy-v2

- Её `0047_problem_figure_raster` — тот же файл, что в c13 (байт в байт по
  решению Notion от 05.09); после этой сессии в дереве он уже будет — при
  слиянии taxonomy-v2 конфликта по нему быть не должно, но нужна ещё одна
  склеивающая миграция problems.
- ADR: перенумеровать её 0059–0062 и 0067–0069 (номера заняты после фазы 10).
  **Следующий свободный номер после этой сессии — 0090.**
- Её `0034-legacy-stores-converted-text.md`: на него ссылается `docs/adr/0089-canonical-database-copy.md` (c13) — после слияния taxonomy-v2 ссылка станет живой (если 0034 не перенумеруют).

## Для A3

### Коллизии номеров ADR по факту дерева (`git ls-files docs/adr`, 82 файла, максимум 0076)

| Номер | Файлы |
|---|---|
| 0013 | `0013-calc2-static-version-tag.md`, `0013-x-frame-options-owner.md` — старые, не трогать |
| 0014 | `0014-calc2-kink-as-regular-keypoint.md`, `0014-referrer-policy-and-nosniff-owner.md` — старые, не трогать |
| 0015 | `0015-calc2-single-input-card.md`, `0015-search-service-fp32.md` — старые, не трогать |
| 0017 | `0017-calc2-math-independent-of-viewport.md` (main), `0077-scoped-test-runner-boundaries.md` → 0077 |
| 0036 | `0036-topic-map-subject-colour-layer.md` (main), `0089-canonical-database-copy.md` → 0089 |
| 0054 | `0054-semantic-threshold-is-a-setting.md` (main), `0083-calc2-overlay-lives-in-a-panel.md` → 0083 |
| 0055 | `0055-game-economy-v2.md` (main), `0084-calc2-key-point-is-what-the-scene-drew.md` → 0084 |
| 0056 | `0056-game-leaderboard-personal-records.md` (main), `0085-calc2-zero-is-a-value-hidden-curve-is-absent.md` → 0085 |
| 0057 | `0057-game-realtime-duel-architecture.md` (main), `0086-calc2-monopoly-surpluses-in-first-quadrant.md` → 0086 |
| 0070 | `0070-vendor-browser-libraries.md` (beta-polish), `0078-problem-page-wider-than-reading-column.md` → 0078 |
| 0071 | `0071-five-sections-one-module.md` (beta-polish), `0079-catalog-attempt-check-is-synchronous.md` → 0079 |
| 0072 | `0072-active-nav-item-underline-and-fill.md` (beta-polish), `0080-problem-chat-is-stateless.md` → 0080 |
| 0073 | `0073-password-change-without-old.md` (beta-polish), `0081-photo-is-recognised-before-the-check.md` → 0081 |
| 0074 | `0074-join-group-by-invite-code.md` (beta-polish), `0082-catalog-test-unlimited-attempts.md` → 0082 |

0058–0059 (calc2) дублей не имеют, но уезжают вместе с блоком → 0087, 0088.
Совпадает с таблицей фазы 10 один в один: лишних и недостающих файлов нет.

### Красные тесты calc2 с доказательством

| Тест | На integration | На чистом `main` | Вывод |
|---|---|---|---|
| `calc2_math.mjs` → «Регулятор сцены · правка значения», ширина поля 40,375 px при потолке 40 | ✗ (237/238) | ✗ (237/238, `logs/07-node-calc2_math-on-main.txt`) | не регрессия, известный красный |
| `calc2.tests.test_calc2_math.test_calc2_control_numbers` (Django-обёртка) | пропущен: node-раннер не уложился в 180 с | по архиву — тот же пропуск по таймауту | не красный, а пропуск; отдельный `control_numbers.mjs` — 512/512 |
| `calc2.tests.test_calc2_map.test_function_index_matches_code` | был ✗, после `calc2_map` ✓ | ✓ | красный принесла ветка calc2 (`aca9bd25`), починен пересборкой карты |

### Прочее для A3

- `docs/TESTING.md`: команда `python -m unittest discover -s scripts/tests -t .` не описана (фаза 3).
- Рабочая локальная база — SQLite, не PostgreSQL; формулировки про «31 тыс. задач в PostgreSQL» уточнить в фазе 11.
- Фазы 12 (джоб `migrations`) и 13 (полный прогон на PostgreSQL) требуют Docker — статус см. фазу 9.

## Сессия B: main → прод → чистка GitHub и Windows

### Фаза −1. Сверка с реальностью

✅ Все пункты сошлись с ожиданием, расхождений нет.

| Проверка | Ожидание | Факт |
|---|---|---|
| `git status --short -uall` (без `??`) | пусто | пусто |
| `git branch --show-current` | `integration/sync-20260905` | совпало |
| `git rev-parse HEAD origin/integration/sync-20260905` | оба `7458d560…` | оба `7458d5608a0676512aebbd748ff9abf8f9bc6c3b` |
| `git rev-parse main origin/main` | оба `6b8406110d9d7e24afb8e796e6e0dc10197eb143` | совпало |
| `git merge-base --is-ancestor main HEAD` | ff-ok | ff-ok |
| `git rev-list --count main..HEAD` | 164 | 164 |
| `git stash list` | пусто | пусто |
| `git worktree list` | 11 записей (B_PLAN §5а) + сама `qls` | 12 строк, состав совпал с B_PLAN §5а |
| `git ls-remote --tags origin \| grep -c archive/\|backup/main-before-sync` | 8 | 8 |
| `git ls-remote --heads origin \| wc -l` | 54 | 54 |
| `qls-models` status / HEAD | пусто / `772ac87e…` | пусто / `772ac87e4de094c221970ce8f4f4af950696ba51` |

**CI #115** — [run 34026895692](https://github.com/malinovskiy-makar/qls/actions/runs/34026895692), `headSha` `7458d5608a0676512aebbd748ff9abf8f9bc6c3b` = HEAD. Все пять джобов зелёные (Стиль/ruff, Миграции с нуля, Безопасность, Продакшен-настройки, Тесты на PostgreSQL 17). Числа шага A/B из джоба «Тесты на PostgreSQL 17»: **шаг A — 4413 тестов, OK (skipped=5), 447,9 с; шаг B — 8 тестов, OK (skipped=3), 208,0 с.** Отличается от локального прогона фазы 13 (4411/1 и 8/4) — расхождение в среде CI (два теста больше в сборе, другой набор пропусков), не красное, стопа не требует.

Вопрос владельцу задан (приёмка на runserver) — ответ **«Принято»** получен, B1 разрешена.

### Фаза B1. Перемотка `main` и тег

`git checkout main` прошёл без конфликтов (main нигде не выписан в worktree).
`git merge --ff-only integration/sync-20260905` — чистый fast-forward, без
merge-коммита. Тег `sync-20260905` создан на вершине.

Отклонение от буквы задания (ожидаемое, не расхождение): вершина `main`
после перемотки — `a93e67b`, а не `7458d560`, потому что коммит журнала
фазы −1 этой сессии лёг поверх `7458d560` ещё на `integration/sync-20260905`
до `checkout main`. Это ровно случай, описанный в правилах сессии
(«после B1 коммиты журнала ложатся на main»), просто на один коммит раньше
графика.

| Проверка | Значение |
|---|---|
| `git rev-parse HEAD` (main) | `a93e67bef77944bd587fed9d9e732cf7cc45af27` |
| `git log --oneline -3` | `a93e67b` (журнал фазы −1) ← `7458d56` (журнал B0) ← `1dfd956` |
| `git rev-parse sync-20260905^{}` | `a93e67bef77944bd587fed9d9e732cf7cc45af27` (= HEAD) |

⛔ **Стоп-гейт 1.** Команды владельцу: `git push origin main` и
`git push origin sync-20260905`. Владелец выполнил (из `qls-models`, общий
`.git` с `qls` — это допустимо, репозиторий один): `main` `6b84061..798dc14`,
тег `sync-20260905` создан на GitHub. Пуш прошёл раньше, чем этот коммит
журнала лёг поверх — поэтому вершина после пуша `798dc14`, а не `a93e67b`;
тег на GitHub — объект `46a73c30`, `^{}` = `a93e67b` (коммит слияния, до
журнала фазы B1) — это ожидаемо и корректно, тег фиксирует именно момент
слияния.

**Поправка владельца (пересчёт хешей).** Правило задания «HEAD на проде =
7458d560» устарело: тег и `main` теперь на `a93e67b`/`798dc14`
(коммиты журнала фаз −1/B1 поверх проверенного CI #115 коммита). Проверено
командой `git diff --stat 7458d560 main` — разница ровно один файл,
`reports/branch_sync_20260905/PROGRESS.md` (46 строк), `reports/` в
`.dockerignore` (строка 34) — в образ на проде не попадает. Значит код,
который реально придёт на сервер, побайтово равен коммиту `7458d560`,
проверенному CI #115; отличаются только журнальные файлы вне сборки.
**Правило для B2 и B5: ожидание HEAD на проде после `git pull` — вершина
`main` на момент выдачи команд владельцу (`git rev-parse --short=8 main`
прямо перед шагом), а не зафиксированный заранее хеш.** На момент этой
записи — `798dc148`.

| Проверка | Значение |
|---|---|
| `git rev-parse origin/main` | `798dc148321c4a1e979c9fbe2caabbd086626c05` = локальный `main` |
| `git ls-remote --tags origin sync-20260905` | `46a73c307996f33fa34d5f5c3bb1a7e5dc6a4311` (объект тега) |
| `git diff --stat 7458d560 main` | только `reports/branch_sync_20260905/PROGRESS.md`, +46 |
| CI #116 на `main` (run `34029085274`) | запущен, результат — при появлении, ждать не обязательно |

### Фаза B2, шаг 0. Карта выкатки и план отката (Claude Code, до сервера)

**Что придёт на сервер одним `git pull`** — коммитов от `6b840611` (текущий
прод) до `main` (`6b0315b9` на момент записи, дальше — журнальные коммиты).
Кода это не касается: `git diff --stat 7458d560 main` (см. выше) — только
`reports/branch_sync_20260905/PROGRESS.md`, вне `.dockerignore` не попадает.

**Миграции — ровно 14 файлов** (`git diff --stat 6b840611 main -- problems/migrations olympiads/migrations`,
проверено командой, не по памяти):

- `olympiads`: 0002_trainingattempt_trainingdraft_trainingitemresult_and_more,
  0003_olympiadvariant_is_placeholder, 0004_alter_regionalcoordinator_options_and_more,
  0005_olympiadbenefit_who_gets, 0006_olympiadstage_source (5 файлов)
- `problems`: 0047_problem_figure_raster, 0050_problem_character_features,
  0050_userprofile_avatar_userprofile_level, 0051_catalog_attempt,
  0051_studentgroup_invite_code, 0052_feedback, 0052_hint_ai_flags,
  0053_hint_reviewed_backfill, 0054_merge_0052_feedback_0053_hint_reviewed_backfill
  (9 файлов)

Все обратимы по схеме (проверено на копии в фазе 9 сессии A). Две `RunPython`:
`0051_studentgroup_invite_code` (`fill_codes`, откат `noop`) и
`0053_hint_reviewed_backfill` (`mark_reviewed`, откат `noop`) — откат схемы
идёт, данные RunPython назад не возвращаются. `entrypoint.sh` (строки 82, 89)
накатывает `migrate --noinput` и `collectstatic --noinput` сам при старте
контейнера `web` — руками ничего катить не нужно. nginx: `deploy/nginx/available/django.conf`
уже несёт `weconomics.ai`/`www.weconomics.ai` в `server_name` (проверка diff-ом
на сервере всё равно обязательна — B2 шаг 3). Данные: заливка олимпиад по
`--yes` на шаге 6 (finat чинится пропуском с предупреждением, не блокирует).
`import_problem_attributes` — пропуск, файла разметки нет.

Имена служб в `deploy/docker-compose.yml` подтверждены: `postgres`, `redis`,
`web`, `ws`, `search`, `nginx`, `certbot` (плюс тома и сеть `backend`) —
совпадает с ожиданием SERVER.md.

**План отката** (записан ДО выкатки):

- **А. Заглушка.** Сайт сломан, чинить некогда —
  `cp /srv/weconomics/nginx/available/stub.conf /srv/weconomics/nginx/conf.d/weconomics.conf && docker compose exec nginx nginx -s reload`
  (раздел «Откат» SERVER.md, команда проверена дважды на живом сайте
  21.08). Данные и `web` целы, nginx просто перестаёт проксировать.
- **Б. Откат кода = откат базы.** Старый код не переживёт новые NOT NULL
  колонки без дефолта на уровне базы (`userprofile.avatar`/`level`,
  `problemfigure.content_type` и т. п.) — регистрация и другие вставки
  упадут. Порядок: `docker compose stop web` → переименовать боевую базу
  (не удалять) → создать пустую → восстановить свежий дамп шага 1
  (`pg_restore --no-owner --no-privileges`, раздел «Как восстановиться»
  SERVER.md, но поверх боевой, не во временную) → `git reset --hard 6b8406110d9d7e24afb8e796e6e0dc10197eb143`
  в клоне → `docker compose build web && docker compose up -d web` →
  `manage.py fix_sequences` (сперва показать, затем `--apply`) → проверки
  шага 2. Записи пользователей между выкаткой и откатом теряются — сказать
  владельцу прямо, если до этого дойдёт.
- **В. Частичный откат без отката базы** (данные после выкатки уже ценны):
  на новом коде — `manage.py migrate problems 0049_merge_20260902_2058` и
  `manage.py migrate olympiads 0001_initial`, затем А или Б. Колонки
  `0047_problem_figure_raster` не потомок 0049 — остаются, старый код их
  не трогает, риск только при загрузке картинок.

⛔ **Стоп-гейт 2.** Карта и план отката показаны. Вопрос владельцу: план
отката прочитан, дамп будем снимать — да? Ответ: **да, снимаем дамп.**

### Фаза B2, шаг 1. Свежий дамп и факты «до» (владелец, сервер)

**Ожидания записаны ДО выдачи команды владельцу:**

| Что | Ожидание |
|---|---|
| HEAD на сервере (до pull) | `6b840611` (старый прод, не обновлялся с 21.08–03.09) |
| `git status --short` в `/srv/weconomics/app` | пусто |
| Файл дампа | новый, с сегодняшним временем (06.09.2026), в `/srv/weconomics/backups/` |
| `docker compose ps` | четыре службы `Up ... (healthy)`: `postgres`, `redis`, `web`, `nginx` (`ws`/`search` — если подняты, тоже healthy) |
| Миграций `[ ]` (неприменённых) | пусто — прод стоял ровно на своей версии |
| `problems_problem` (N_p) | ориентир ~505 (smoke-набор по SERVER.md) |
| пользователей (N_u) | ориентир 3 (`weco_admin`, `demo_teacher`, `demo_student` по SERVER.md) |
| `olympiads.Olympiad` | ориентир 0 (раздел ещё не заводился на проде) |

Расхождение с любым пунктом — стоп, не подгонять объяснение под факт.

**Команды владельцу** (SSH-ключ и пользователь — из `docs/SERVER.md`):

```bash
ssh -i $env:USERPROFILE\.ssh\id_ed25519_weconomics makar@135.106.181.151
cd /srv/weconomics/app && git rev-parse --short=8 HEAD && git status --short
sudo /srv/weconomics/app/deploy/backup.sh
sudo sh -c 'ls -lt /srv/weconomics/backups/*.dump.gz | head -2'
cd /srv/weconomics/app/deploy && docker compose ps
docker compose exec web python manage.py showmigrations problems olympiads | grep -c "\[X\]"
docker compose exec web python manage.py showmigrations problems olympiads | grep "\[ \]"
docker compose exec web python manage.py shell -c "from problems.models import Problem; from django.contrib.auth import get_user_model; print('problems', Problem.objects.count(), 'users', get_user_model().objects.count())"
docker compose exec web python manage.py shell -c "from olympiads.models import Olympiad; print('olympiads', Olympiad.objects.count())"
```

Пришлите весь вывод целиком — сверю с ожиданием построчно, без дампа с
сегодняшней датой на B2 шаг 2 не пойдём.

**Вывод получен, сверка построчно — ДВА РАСХОЖДЕНИЯ, ⛔ СТОП.**

| Проверка | Ожидание | Факт | Статус |
|---|---|---|---|
| HEAD | `6b840611` | `6b840611` | ✅ |
| `git status --short` | пусто | `?? deploy/deploy_fixtures_approved.tar.gz` | ⚠️ РАСХОЖДЕНИЕ |
| Дамп | сегодня | `weconomics-20260906-141743.dump.gz`, 29 МБ, 14:17 | ✅ |
| `docker compose ps` | 4 healthy | `nginx`, `postgres`, `redis`, `web` — все `Up ... (healthy)` | ✅ |
| Миграций `[X]` | — (записать) | 52 | ✅ записано |
| Миграций `[ ]` | пусто | пусто | ✅ |
| `problems_problem` (N_p) | ориентир ~505 | **5095** | ⚠️ РАСХОЖДЕНИЕ, ×10 |
| пользователей (N_u) | ориентир 3 | 3 | ✅ |
| `olympiads.Olympiad` | ориентир 0 | 0 | ✅ |

**Расхождение 1 — неучтённый файл.** `deploy/deploy_fixtures_approved.tar.gz`
в `git status` клона на сервере. Имя перекликается с `deploy_fixtures_bank/`
из ветки `feat/embeddings-c13-diagnostics` (поправка 7 сессии A: «не трогать,
в индекс не добавлять») — возможно, тот же класс артефакта, положенный на
сервер вручную мимо git. Не в git-дереве `main`, `git pull --ff-only` его
не тронет, но происхождение и содержимое неизвестны Claude Code (на сервер
не хожу).

**Расхождение 2 — задач в десять раз больше ориентира.** `docs/SERVER.md`
и `CLAUDE.md` фиксируют «smoke-набор 505 задач, не весь корпус» (последняя
проверка 21.08). Факт сейчас — 5095. Это может быть: (а) владелец уже залил
более широкий набор после 21.08 вручную (тогда просто документы устарели),
(б) как-то связано с найденным файлом `deploy_fixtures_approved.tar.gz` —
название прямо намекает на заливку одобренных задач, (в) что-то, что надо
разобрать отдельно. Дальнейший план отката (в шаге 0) строился на
предположении «501 задача, копия небольшая» — при 5095 время `pg_dump`/
`pg_restore` и объём дампа те же (29 МБ, уже снят), риск отката не меняется
качественно, но **план читает "ориентир ~505" как факт устройства прода — это предположение больше не подтверждено**, и продолжать выкатку до объяснения
не буду.

⛔ **Стоп. Вопрос владельцу перед B2 шагом 2:** что такое
`deploy/deploy_fixtures_approved.tar.gz` на сервере и почему задач 5095, а
не ~505 — заливали ли вы туда что-то в обход `git`/деплоя после 21.08?

**Ответ владельца — оба расхождения объяснены, не аномалия.**

1. **5095 задач — верно.** 24.08.2026 по решению владельца на прод залито
   approved-подмножество корпуса: 5090 задач с `human_review='approved'` и
   эмбеддингами, фикстурами `deploy_fixtures_approved/` (13 файлов, 44 МБ),
   через `loaddata` + `fix_sequences` + `cache_similar`. 500 из 505
   smoke-задач при этом удалены и перезалиты в составе approved, 5 остались
   — итого 5095 = 5090 + 5. Источник: Notion «Задачи» карточка «Залить
   approved-подмножество корпуса (5090 задач) на прод»
   (`3c5b11c9-2bc1-819a-a3b7-f3ecbebf41d4`, Готово) и «Результаты» от
   24.08.2026. Цифра «505» в `docs/SERVER.md`/`CLAUDE.md` — замер 21.08,
   устарела. **Новая базовая линия инвариантов: N_p = 5095, N_u = 3, M = 52.**
2. **`deploy_fixtures_approved.tar.gz` — тот самый архив фикстур** для
   заливки 24.08, забытый в клоне. К `git`/выкатке отношения не имеет,
   `git pull --ff-only` его не заденет; во время выкатки не трогать. После
   шага 7 — перенос (не удаление) отдельной командой владельцу:
   `mv /srv/weconomics/app/deploy/deploy_fixtures_approved.tar.gz /home/makar/deploy_fixtures_approved_20260824.tar.gz`
   (клон обязан оставаться одноразовым, SERVER.md «состояние сервера живёт
   вне клона»).

План отката (шаг 0) — без изменений: дамп `weconomics-20260906-141743.dump.gz`
(29 МБ) восстанавливается быстро, пункт Б в силе. Для фазы B5: одна строка в
`docs/SERVER.md` рядом с таблицей восстановления — «с 24.08.2026 на проде
approved-подмножество, ~5090 задач; числа в таблице — замер 21.08 на
smoke-наборе» (правка документов делается в B5, не сейчас).

### Фаза B2, шаг 2. Выкатка — ожидания (записаны ДО команды)

Хеш к выкатке — вершина `main` на момент выдачи команды владельцу
(правило пересчёта хешей, зафиксированное после стоп-гейта 1): на момент
записи `main` = `c2781c5` (сдвинется ещё на коммит после этой записи —
финальный хеш возьму `git rev-parse --short=8 main` прямо перед выдачей).

| Что | Ожидание |
|---|---|
| HEAD после `pull` | вершина `main` на момент команды (не `7458d560`) |
| `docker compose ps` | `web` healthy до минуты |
| Логи `web` | 14 строк «Applying …migration… OK», ни одного Traceback |
| Миграций `[ ]` | пусто |
| Миграций `[X]` | 52 + 14 = **66** |
| `makemigrations --check --dry-run` | No changes detected |
| `problems_problem` (N_p) | **5095** (новая базовая линия, не 505) |
| пользователей (N_u) | **3** |
| `weconomics.site` / `weconomics.ai` | оба `HTTP/2 200` |

⛔ **Стоп-гейт 3.** Вопрос владельцу: выкатываю вершину `main`
(`git rev-parse --short=8 main` прямо перед командой) на прод — да?
Ответ: **да.**

**Сбой и разбор (ошибка Claude Code, не владельца).** После стоп-гейта 1
локально было сделано ещё пять коммитов журнала (`ad94236` … `f76844c8`),
но пуш на GitHub после них не запрашивался — правило «пуш только по
команде владельцу» из задания было соблюдено буквально, но новый пуш перед
шагом 2 не был затребован. `origin/main` оставался на `798dc148` (вершина
после стоп-гейта 1). Из-за этого вопрос стоп-гейта 3 назвал неверное
ожидание (`f76844c8`) для серверного `git pull`.

Дополнительно был сбой с `tmux`: первая попытка (`tmux new -s deploy`)
вернула `duplicate session: deploy`, реальные команды деплоя в неё не
попали (сессия существовала пустой), а следующая команда выполнилась
из `~`, а не из `deploy/` (`no configuration file provided`).
`tmux capture-pane` в одной из попыток вернул нечитаемые управляющие
последовательности вместо текста — разбирать не стали, перешли на
пошаговый режим без `tmux`.

**Восстановление.** `cd /srv/weconomics/app && git pull --ff-only` —
прошёл, честный fast-forward (много файлов из шести веток: `static/vendor/mathlive-0.110.0/*`,
`student/tests/test_dashboard_queries.py`, `teacher/templates/teacher/groups/*`
и т. д.). `git rev-parse --short=8 HEAD` → **`798dc148`** — это и есть
правильное ожидание (не `f76844c8`), содержимое кода то же, что проверено
CI #115 (см. разбор выше — разница с `7458d560` только в `PROGRESS.md`).
Дальше работаем от `798dc148`, без `tmux` (шаги короткие), команды по одной,
вывод — текстом, не скриншотом.

**Шаг 2 — выкатка, результат: ✅ зелёный по всем пунктам.**

| Проверка | Ожидание | Факт |
|---|---|---|
| `git status --short` после `pull` | только `deploy_fixtures_approved.tar.gz` (не мешает) | совпало |
| `docker compose build web` | без ошибок | `Image weconomics-web:latest Built` |
| `docker compose up -d web` | `web` healthy | healthy через 40 с |
| Логи `web`, `Applying\|Traceback\|Error` | 14 строк `OK`, 0 ошибок | ровно 14 строк `Applying … OK`, `Traceback`/`Error` — 0 (⚠️ с `--tail=200` строки не попали в срез — вытеснены выводом `collectstatic`; без `--tail` нашлись) |
| Миграций `[ ]` | пусто | пусто |
| Миграций `[X]` | 66 | 66 |
| `makemigrations --check` | No changes detected | No changes detected |
| `problems_problem` / users | 5095 / 3 | 5095 / 3 |
| `weconomics.site` / `.ai` | оба 200 | оба `HTTP/2 200` |

Прод обновлён: `main` = `798dc148`, 14 миграций накатились без ошибок, данные
не сдвинулись. Дальше — шаг 3 (nginx, сверка diff-ом).

**Шаг 3 — nginx: ✅ SAME.** `diff .../deploy/nginx/available/django.conf
.../nginx/conf.d/weconomics.conf` — пусто, конфиги идентичны. Как и
предполагал B_PLAN («скорее всего, на сервере копировать нечего»),
`weconomics.ai` уже был в активном конфиге. Копировать и перезагружать
nginx не нужно.

### Фаза B2, шаг 4. Коды ответа по адресам обхода

Id для `/catalog/problem/<id>/` на проде — `4` (первый по возрастанию,
совпадает с локальным списком `logs/16-guest-codes.txt`). Ожидание по
22 адресам (из фазы 16 сессии A): 12 публичных → 200, 8 закрытых → 302 на
`/login/?next=…`, `/admin/` → 302 на `/admin/login/?next=/admin/`,
несуществующий → 404. Команда-цикл для обоих доменов — ниже, ждём вывод.

**Результат: 21 из 22 точно совпало, одно расхождение — объяснено.**
`.site`: `/`, `/catalog/`, `/catalog/problem/4/`, `/catalog/map/`,
`/textbook/`, `/olympiads/`, `/calc2/`, `/game/`, `/login/`, `/register/`,
`/calendar/` — все 200 (11 из 12 публичных); восемь личных адресов и
`/admin/` — 302 на правильный `/login/?next=…` / `/admin/login/?next=/admin/`;
`/nonexistent-page/` — 404. `.ai`: `/`, `/catalog/`, `/login/` — все 200.

### Внеочередной инцидент: пустая навигация на проде — найден и починен

При визуальной приёмке шага 5 владелец увидел на `weconomics.ai` пустую
верхнюю навигацию (между логотипом и «Войти»/«Создать аккаунт» — ничего).
Claude Code открыл сайт напрямую (Browser pane) и разобрал: `<div
class="nav-links">` в HTML — пустой на ОБОИХ доменах, в десктопной строке и
в мобильной панели `☰`, консоль и сеть чистые (не CSS, не 404, не кэш
браузера).

**Причина.** С 04.09.2026 (`beta-polish-0904`) состав меню считает
`config/context_processors.py::site_meta`, подключённый в
`config/settings.py` (строка 99). `config/settings_production.py` держит
СВОЙ отдельный список `TEMPLATES[…]['context_processors']` (ради
кэширующего загрузчика шаблонов) — и при рефакторинге шапки его не
обновили. На бою `nav_items` не определена, Django молча даёт пустой список
в `{% for item in nav_items %}` — ни исключения, ни ошибки. Прод до сегодня
был на коде до 04.09 (старая четырёхкопийная шапка без `site_meta`), поэтому
баг не мог проявиться раньше сегодняшней выкатки; локальный `runserver`
всегда на `config.settings` (там `site_meta` есть) — приёмка на нём баг не
ловила; теста на `settings_production` для навигации тоже нет.

**Решение владельца:** чинить сейчас же, вне очереди.

**Фикс** — [config/settings_production.py](config/settings_production.py):
добавлена строка `'config.context_processors.site_meta',` в список
context_processors (коммит `b75123b`). Проверено: `manage.py check --deploy
--settings=config.settings_production` (с переменными как в джобе
`deploy-check` из `ci.yml`) → чисто (1 silenced, как обычно); напрямую в
Python подтверждено `site_meta` в списке; `config.tests.test_nav` — 22 OK.
Выкачено тем же циклом (`git pull --ff-only` → `798dc148..b75123b5` →
`docker compose build web` → `up -d web`, healthy). Проверено вживую через
браузер на широком (1920) и обычном окне, на ОБОИХ доменах: пункты меню
(«Каталог», «Учебник», «Олимпиады», «Графики», «Тренажёр») на месте,
консоль чистая.

⚠️ **`/olympiads/vseros/` → 404, а не 200** — расхождение с ожиданием.
Причина (не догадка, а факт из шага 1): `olympiads.Olympiad.objects.count()`
на проде = 0 (раздел ещё не заведён, данные заливаются только на шаге 6).
`/olympiads/` — список, рендерится и пустым (200); `/olympiads/vseros/` —
страница конкретной олимпиады по slug `vseros`, которой в базе физически
нет — Django корректно отдаёт 404. Локальный список ожиданий снимался на
базе с `seed_olympiads_demo` (демо-олимпиады, включая `vseros`), а на прод
`seed_olympiads_demo` запрещён. Не дефект, не 5xx — перепроверить `/olympiads/vseros/`
после шага 6 (заливка реальных данных), там ожидание снова 200.

### Фаза B2, шаг 6. Данные олимпиад

Раздел на проде пуст (`olympiads.Olympiad = 0`, шаг 1) — по правилу нужен
отдельный стоп-гейт перед записью. План (`import_olympiads_data` без флага)
— **точно по ожиданию**: источники 37, олимпиады 17, уровни 50, этапы 32,
даты 15, баллы 9, программы 7, льготы 88, регионы 89, комплекты 12.

⛔ Стоп-гейт 4 — «да», запись.

### Внеочередной инцидент 2: `DataError` на PostgreSQL при `--yes`

Реальная запись (`import_olympiads_data --yes`) упала:
`django.db.utils.DataError: value too long for type character varying(300)`,
в `_load_olympiads` (`olympiads/management/commands/import_olympiads_data.py:173`).
Проверка `Olympiad.objects.count()` сразу после — **0**, частичной записи не
осталось (команда атомарна).

**Разбор.** Полный трейсбек по кусочкам (терминал резал вывод) указал на
файл и строку. Сверка всех девяти файлов `data/olympiads/out/*.jsonl`
против `max_length` соответствующих полей моделей (`olympiads/models.py`,
скрипт-разовый, интроспекция через Django) нашла ровно ОДНО превышение:
`olympiads.jsonl`, slug `vernadsky`, поле `organizer` — **441 символ** при
`CharField(max_length=300)`. Значение — не мусор, а список девяти вузов
консорциума («Бурятский государственный университет…», далее по списку).
**Почему не поймано раньше:** тот же файл и код успешно отработали в
сессии A (фаза 18) на **SQLite** — SQLite не проверяет длину `varchar`
физически, PostgreSQL проверяет. Ровно случай из предупреждения CLAUDE.md
«зелёный прогон на SQLite — не доказательство, прод на PostgreSQL».

**Фикс** (коммит `d00ba04`, применён навык `weco-migration-safety`):
`Olympiad.organizer` — `CharField(max_length=300)` → `TextField` (без лимита,
как уже сделано для `description`), миграция `0007_alter_olympiad_organizer`.
Чек-лист:
- граф цел, `0007` — единственный лист (`showmigrations olympiads`);
- `makemigrations --check --dry-run` → No changes detected;
- накат с нуля на свежей PostgreSQL (`qls_zero_migtest_b3`, докер
  `qls_postgres_dev`) — все 68 миграций (включая новую) без ошибок;
- обратимость: `migrate olympiads 0006` → `0007` туда-обратно на пустой
  таблице — ОК; отдельно отмечено — на данных с `organizer` длиннее 300
  откат назад технически невозможен (сузить `text` в `varchar(300)`
  нельзя), это ожидаемо для операции расширения поля, не дефект;
- `manage.py test olympiads --settings=config.settings_test_pg` → **95 OK**
  (совпадает с сессией A);
- **полный `import_olympiads_data --yes` на чистой PostgreSQL** (отдельная
  тестовая база `qls_import_test_b3`) — прошёл целиком: источники 37,
  олимпиады 17, уровни 50, этапы 32, даты 15, баллы 9, программы 7,
  **льготы 87** (+ `ПРОПУЩЕНО: льгота finat / Финуниверситет: олимпиады
  «finat» нет в olympiads.jsonl`), регионы 89, комплекты 12 — «Залито.»;
  `vernadsky.organizer` — 441 символ, цел; `Olympiad.objects.count()` = 17,
  `is_placeholder=True` = 0. Тестовые базы удалены.

Дальше: пуш `d00ba04`, `git pull` + пересборка `web` на проде (тот же
цикл), и только потом повтор `import_olympiads_data --yes` на самом проде.

**Прод: выкачен `f30aa088` (+ journal-коммит), миграция 0007 применена без
ошибок, `import_olympiads_data --yes` прошёл целиком на боевой базе.**
Результат — точно по ожиданию: источники 37, олимпиады 17, уровни 50,
этапы 32, даты 15, баллы 9, программы 7, льготы 87 (+ пропуск finat),
регионы 89, комплекты 12. Проверено: `Olympiad.objects.count()` = 17,
`is_placeholder=True` = 0; `/olympiads/vseros/` → 200 (было 404 до заливки,
объяснение из шага 4 подтвердилось). Открыл `/olympiads/vernadsky/` через
браузер напрямую — карточка организатора («Консорциум вузов: … девять
вузов…») отображается полностью, вёрстка не едет.

**Шаг 6 закрыт.** Фаза B2 закончена: код на проде, 14+1 миграций применены,
nginx не трогали (уже совпадал), навигация починена (инцидент 1), олимпиады
залиты (инцидент 2 починен). Оба инцидента — новые баги, найденные и
исправленные ПРЯМО в ходе B2, не относятся к плану сессии A. Дальше — фаза
B3 (удаление веток на GitHub), только после того как `origin/main`
содержит интеграцию (да, содержит) и прод выкачен (да, выкачен).

## Фаза B3. GitHub — удаление веток, вошедших в `main`

**3.1 Страховка.** `git ls-remote --tags origin` — 8 архивных/backup тегов
(все ожидаемые: `backup/main-before-sync-20260905`,
`archive/feat-calc2-map-21aug`, `archive/feat-calc2-mono-surpluses`,
`archive/feat-calc2-panels-and-keypoints`,
`archive/feat-calc2-trade-and-ui`, `archive/feat-import-new-sources`,
`archive/chore-corpus-consolidation-20260822`,
`archive/backup-search-eval-c14-before-rebase`) плюс `sync-20260905`.
`git ls-remote --heads` — `feat/olympiad-text-dedup` и все четыре `wip/*`
на месте. Всё, что нужно для страховки, есть — продолжаю.

**3.2 Пересчёт на живом дереве** (после `git fetch origin --prune --tags`):
54 ветки на origin, из проверки исключены `main`,
`integration/sync-20260905`, `feat/taxonomy-v2-openai-provider`,
`feat/olympiad-text-dedup`, четыре `wip/*` — 46 к проверке. Результат
(`git merge-base --is-ancestor origin/<b> origin/main` для каждой):
**45 предков + 1 непредок** (`feat/calc2-map-21aug`) — совпадает с B_PLAN
§4а/4б один в один, включая полный список. `feat/calc2-map-21aug` покрыта
тегом: `git rev-parse origin/feat/calc2-map-21aug archive/feat-calc2-map-21aug^{}`
— оба `766c68ee`.

⛔ **Стоп-гейт 5.** Таблица: 45 предков `main` (полный список — B_PLAN.md
§4а, сверен заново и идентичен) + 1 покрыта тегом (`feat/calc2-map-21aug`)
= **46 к удалению**. Остаются 8: `main`, `integration/sync-20260905`,
`feat/taxonomy-v2-openai-provider`, `feat/olympiad-text-dedup`, четыре
`wip/*`. Жду «да» (можно «да, кроме …»).
