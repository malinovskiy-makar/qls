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
| 4 Слияние olympiads-screens | ⏳ | | |
| 5 Слияние catalog-redesign + 0054_merge | | | |
| КТ1 | | | |
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
