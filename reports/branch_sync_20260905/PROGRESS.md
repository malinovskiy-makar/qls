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
| 6 Сверка перед A2 | | | |
| 7 Слияние calc2-monoexport | | | |
| 8 Слияние embeddings-c13 | | | |
| 9 Граф миграций | | | |
| КТ2 | | | |
| 10 Номера ADR | | | |
| 11 CLAUDE.md и документы | | | |
| 12 Четыре быстрых джоба CI | | | |
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

## Для будущего слияния taxonomy-v2

- Её `0047_problem_figure_raster` — тот же файл, что в c13 (байт в байт по
  решению Notion от 05.09); после этой сессии в дереве он уже будет — при
  слиянии taxonomy-v2 конфликта по нему быть не должно, но нужна ещё одна
  склеивающая миграция problems.
- ADR: перенумеровать её 0059–0062 и 0067–0069 (номера заняты после фазы 10).
  Следующий свободный номер после этой сессии — заполняется в фазе 10.

## Для A3

(заполняется на КТ2: коллизии ADR по факту дерева, красные тесты calc2 с доказательством)
