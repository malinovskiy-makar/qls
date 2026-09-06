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
| КТ3 | | | |
| 13 Полный прогон PostgreSQL | | | |
| 14 Итог сессии | | | |
| 15 Стоп-гейт: рабочая база | | | |

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

(заполняется ночью; пусто = вопросов нет)


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
