# План сессии B — `main` → прод → чистка веток и worktree

**Составлен:** 06.09.2026, ночная часть сессии A (фаза 17), только чтение —
ничего из перечисленного НЕ выполнялось. Хеш `integration/sync-20260905` на
момент плана — `2a488680`; окончательный хеш — в отчёте фазы 14 журнала
(`PROGRESS.md`). Перед каждым шагом сессия B перепроверяет команды из этого
файла на живом дереве: ветки могли сдвинуться.

Порядок: 0 (пуш integration и CI) → 1 (перемотка `main`) → 2 (прод) →
3 (теги на origin) → 4 (удаление веток origin) → 5 (локальные ветки и
worktree). Шаги 1–2 — только после «да» владельца и зелёного CI; шаги 4–5 —
только после того, как `main` на origin уже содержит integration.

---

## 0. Пуш integration и CI (владелец, утро)

```bash
git push origin integration/sync-20260905
```

Ждать пять джобов на https://github.com/malinovskiy-makar/qls/actions.
Локально все пять зелёные (фазы 12–13 журнала); CI #113 на КТ2 падал одним
тестом (тире из ветки calc2) — починено `91c4c1d7`.

## 1. Перемотка `main` (P0: пуш в `main` = выкатка, только по «да» владельца)

```bash
cd C:\Users\shipu\qls
git fetch origin --prune
git checkout main
git merge --ff-only integration/sync-20260905      # чистая перемотка, без merge-коммита
git rev-parse HEAD                                 # = вершина integration
git push origin main
```

Если `--ff-only` откажет — на `origin/main` появились чужие коммиты; тогда
СТОП и разбор, не `merge` и не `rebase`.

## 2. Прод (`/srv/weconomics/app`, команды из docs/SERVER.md)

Что придёт на сервер одним выкатом: шесть веток, 154+ коммитов, миграции
`problems` 0047_problem_figure_raster + 0050–0052 (beta-polish) + 0050–0054
(редизайн и склейка) и `olympiads` 0002–0006 — **14 миграций**, из них две с
`RunPython` (0051 раздаёт коды приглашений занятиям, 0053 отмечает подсказки
проверенными) — на боевой базе в 505 задач это секунды. `entrypoint`
контейнера `web` накатывает их сам при старте.

```bash
# 2.1 обновить код и контейнер
cd /srv/weconomics/app && git pull --ff-only && git rev-parse --short=8 HEAD   # ожидание: хеш main из шага 1
cd deploy && docker compose build web && docker compose up -d web

# 2.2 проверить
docker compose ps                                                     # web healthy
docker compose exec web python manage.py showmigrations problems olympiads | grep "\[ \]"   # пусто
docker compose exec web python manage.py makemigrations --check --dry-run                   # No changes detected
curl -sI https://weconomics.site/ | head -1
curl -sI https://weconomics.ai/   | head -1
```

⚠️ **nginx-конфиг менялся** (ветка beta-polish, коммит `2f7adb9`):
`deploy/nginx/conf.d/weconomics.conf` получил `weconomics.ai` и
`www.weconomics.ai` в `server_name` обоих `server`-блоков. Активный файл на
сервере — `/srv/weconomics/nginx/conf.d/weconomics.conf`, он **не
подтягивается сам** (docs/SERVER.md). Если `.ai` на сервере ещё не в
конфиге:

```bash
diff /srv/weconomics/app/deploy/nginx/conf.d/weconomics.conf /srv/weconomics/nginx/conf.d/weconomics.conf
# если различие только в server_name с weconomics.ai и сертификат на .ai уже есть:
cp /srv/weconomics/app/deploy/nginx/conf.d/weconomics.conf /srv/weconomics/nginx/conf.d/weconomics.conf
cd /srv/weconomics/app/deploy && docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

Сначала `nginx -t`, потом `reload`. Сертификат для `weconomics.ai` — вне этого
плана: если его нет, `nginx -t` это покажет, конфиг не менять.

Откат к заглушке одной командой — раздел «Откат» docs/SERVER.md (проверен
дважды). Откат кода: `git reset --hard <хеш main до перемотки: 6b84061>` в
клоне и та же пересборка `web`; миграции назад на проде не откатываются без
отдельного решения.

Данные после выкатки (по одному «да»):
- `import_olympiads_data --yes` — **пока нельзя**: падает на `benefits.jsonl`
  (льготы olympiad `finat` без записи олимпиады; карточка «Задачи», Надо).
  Сначала починить данные. `seed_olympiads_demo` на прод НЕ лить.
- `import_problem_attributes <файл>` — файла разметки нет.

## 3. Теги и хвосты на origin (страховка перед удалением)

```bash
git push origin backup/main-before-sync-20260905 archive/feat-calc2-map-21aug archive/feat-import-new-sources archive/feat-calc2-trade-and-ui archive/feat-calc2-mono-surpluses archive/feat-calc2-panels-and-keypoints archive/chore-corpus-consolidation-20260822 archive/backup-search-eval-c14-before-rebase
git push origin feat/olympiad-text-dedup wip/search-eval-c14-leftovers wip/sol-vs-glm-scripts wip/c13-tooling-stash
git ls-remote --tags origin | grep -c -E "archive/|backup/main-before-sync"     # ожидание: 8
```

Проверено 06.09: каждый архивный тег покрывает вершину своей ветки на origin
(`git merge-base --is-ancestor origin/<b> <tag>` истинно для всех пяти хвостов;
`archive/feat-import-new-sources` стоит на локальной `e53d76d5`, которая
впереди origin `94327a68`, и целиком внутри `taxonomy-v2`).

## 4. Ветки origin к удалению

### 4а. Станут предками `main` после перемотки — 45 веток

Проверено `git merge-base --is-ancestor origin/<b> integration/sync-20260905`
для каждой `origin/*`, кроме `main`, `integration/sync-20260905`,
`feat/taxonomy-v2-openai-provider`, `feat/olympiad-text-dedup`, `wip/*`
(вывод — `logs/17-origin-branches.txt`):

```
audit-a1-a71  blok-konkurencia-firma  chore/parallel-tests  chore/postgres-ci
chore/runtime-py313-dj52  design/landing-bg  feat/beta-polish-0904  feat/calc2-andrei
feat/calc2-final-function  feat/calc2-input  feat/calc2-interv-night  feat/calc2-mono-surpluses
feat/calc2-monoexport-one-chart  feat/calc2-on-main  feat/calc2-panel-night
feat/calc2-panels-and-keypoints  feat/calc2-params-contract  feat/calc2-pct-tax
feat/calc2-priyomka-31aug  feat/calc2-priyomka-fixes  feat/calc2-quadrant  feat/calc2-shipu
feat/calc2-sum-visual  feat/calc2-trade-and-ui  feat/catalog-redesign  feat/econ-rush-arena
feat/econ-rush-figure  feat/econ-rush-lives-results  feat/embeddings-c13-diagnostics
feat/import-new-sources  feat/merge-anich-review  feat/olympiads-screens
feat/platform-foundation  feat/prod-deploy  feat/prod-django  feat/prod-server
feat/redis-cache-sessions  feat/scoped-test-runner  feat/smart-catalog  feat/topic-map-v2
feat/wecon-rush  fix/palette-tests  integration/canonical-base  sec/access-boundaries
sec/content-and-auth
```

### 4б. Не предок, но покрыт архивным тегом — 1 ветка

`feat/calc2-map-21aug` (`766c68ee`, +5 над integration; переделано на main;
тег `archive/feat-calc2-map-21aug` = вершина). Удалять только после шага 3.

### 4в. Остаются на origin

`main`, `feat/taxonomy-v2-openai-provider` (живая работа), `feat/olympiad-text-dedup`
(решение владельца: сохранить), `wip/mac-leftovers-20260906`, `wip/search-eval-c14-leftovers`,
`wip/sol-vs-glm-scripts`, `wip/c13-tooling-stash`, и `integration/sync-20260905` — до
тех пор, пока владелец не решит удалить её после перемотки `main`.

### 4г. Команды (после шага 1 и `git fetch origin --prune`; перед каждой строкой — `git merge-base --is-ancestor origin/<b> origin/main` ещё раз)

```bash
git push origin --delete audit-a1-a71 blok-konkurencia-firma chore/parallel-tests chore/postgres-ci chore/runtime-py313-dj52 design/landing-bg feat/beta-polish-0904 feat/calc2-andrei feat/calc2-final-function feat/calc2-input
git push origin --delete feat/calc2-interv-night feat/calc2-mono-surpluses feat/calc2-monoexport-one-chart feat/calc2-on-main feat/calc2-panel-night feat/calc2-panels-and-keypoints feat/calc2-params-contract feat/calc2-pct-tax feat/calc2-priyomka-31aug feat/calc2-priyomka-fixes
git push origin --delete feat/calc2-quadrant feat/calc2-shipu feat/calc2-sum-visual feat/calc2-trade-and-ui feat/catalog-redesign feat/econ-rush-arena feat/econ-rush-figure feat/econ-rush-lives-results feat/embeddings-c13-diagnostics feat/import-new-sources
git push origin --delete feat/merge-anich-review feat/olympiads-screens feat/platform-foundation feat/prod-deploy feat/prod-django feat/prod-server feat/redis-cache-sessions feat/scoped-test-runner feat/smart-catalog feat/topic-map-v2
git push origin --delete feat/wecon-rush fix/palette-tests integration/canonical-base sec/access-boundaries sec/content-and-auth
git push origin --delete feat/calc2-map-21aug        # только после шага 3 (тег на origin)
```

## 5. Локальные ветки и worktree (Windows, `C:\Users\shipu\qls`)

Сначала worktree (ветка, выписанная в worktree, не удаляется), потом ветки.
Проверка на 06.09 — `logs/17-local-branches.txt`.

### 5а. Worktree к сносу

| Папка | Ветка | Неучтённое | Действие |
|---|---|---|---|
| `qls/.claude/worktrees/import-new-sources-edbc26` | `feat/import-new-sources` | чисто | `git worktree remove` (призрак) |
| `qls-gate-revert` | `feat/boevoi-render-legacy` | `?? tatus` (мусорный файл) | владелец смотрит файл → `git worktree remove --force` |
| `qls-render` | `feat/corpus-converter-render` | чисто | `git worktree remove` |
| `qls-scoped-tests` | `feat/scoped-test-runner` | чисто | `git worktree remove` |
| `qls-search-eval` | `wip/search-eval-c14-leftovers` | `?? session_c14_transcript_20260829.md` | владелец решает про расшифровку → `remove --force` |
| `qls-sol` | `wip/sol-vs-glm-scripts` | чисто | `git worktree remove` |
| `qls-topicmap` | `feat/topic-map-v2` | чисто | `git worktree remove` |
| `qls_map` | `feat/topic-map` | чисто | `git worktree remove` |
| `qls_palette` | `feat/smart-catalog` | `?? _incoming/` | владелец смотрит папку → `remove --force` |
| `qls-models` | `feat/taxonomy-v2-openai-provider` | чисто | **ОСТАВИТЬ** — живая работа |
| `qls-olymp` | `feat/olympiad-text-dedup` | чисто | оставить до пуша ветки (шаг 3), потом по желанию |

```bash
git worktree remove C:\Users\shipu\qls\.claude\worktrees\import-new-sources-edbc26
git worktree remove C:\Users\shipu\qls-render
git worktree remove C:\Users\shipu\qls-scoped-tests
git worktree remove C:\Users\shipu\qls-sol
git worktree remove C:\Users\shipu\qls-topicmap
git worktree remove C:\Users\shipu\qls_map
# с неучтённым — после осмотра владельцем:
git worktree remove --force C:\Users\shipu\qls-gate-revert
git worktree remove --force C:\Users\shipu\qls-search-eval
git worktree remove --force C:\Users\shipu\qls_palette
git worktree prune
```

### 5б. Локальные ветки к удалению (`git branch -d`; `-D` только там, где отмечено)

Предки `integration` (после перемотки — предки `main`), `-d` пройдёт:

```
audit-a1-a71 backup-before-merge blok-konkurencia-firma chore/parallel-tests
claude/import-new-sources-edbc26 design/landing-bg docs/effort-and-simplicity-rules
feat/beta-polish-0904 feat/calc2-andrei feat/calc2-shipu feat/corpus-converter-pilot
feat/corpus-converter-render feat/corpus-converter-scaleup feat/embeddings-c13-diagnostics
feat/markdown-renderer feat/merge-anich-review feat/prod-deploy feat/prod-django
feat/prod-server feat/redis-cache-sessions feat/scoped-test-runner feat/search-eval-c14
feat/smart-catalog feat/topic-map feat/topic-map-v2 feat/wecon-rush
fix/bandit-search-client-nosec fix/palette-tests integration/canonical-base
```

Не предки, но покрыты (нужен `-D`, причина рядом):

| Ветка | Почему можно | Чем покрыта |
|---|---|---|
| `backup/search-eval-c14-before-rebase` | резервная копия перед rebase | тег `archive/backup-search-eval-c14-before-rebase` |
| `chore/corpus-consolidation-20260822` | только локально | тег `archive/chore-corpus-consolidation-20260822` |
| `feat/import-new-sources` (`e53d76d5`) | целиком внутри `taxonomy-v2` | тег `archive/feat-import-new-sources` |
| `feat/boevoi-render-legacy` | целиком внутри `taxonomy-v2` | worktree `qls-gate-revert` снести первым |
| `feat/publish-readiness-legacy-new-sources` | целиком внутри `taxonomy-v2` | — |

Остаются: `main`, `integration/sync-20260905` (до решения владельца),
`feat/taxonomy-v2-openai-provider`, `feat/olympiad-text-dedup`, `wip/*`.

```bash
git branch -d audit-a1-a71 backup-before-merge blok-konkurencia-firma chore/parallel-tests claude/import-new-sources-edbc26 design/landing-bg docs/effort-and-simplicity-rules feat/beta-polish-0904 feat/calc2-andrei feat/calc2-shipu
git branch -d feat/corpus-converter-pilot feat/corpus-converter-render feat/corpus-converter-scaleup feat/embeddings-c13-diagnostics feat/markdown-renderer feat/merge-anich-review feat/prod-deploy feat/prod-django feat/prod-server feat/redis-cache-sessions
git branch -d feat/scoped-test-runner feat/search-eval-c14 feat/smart-catalog feat/topic-map feat/topic-map-v2 feat/wecon-rush fix/bandit-search-client-nosec fix/palette-tests integration/canonical-base
git branch -D backup/search-eval-c14-before-rebase chore/corpus-consolidation-20260822 feat/import-new-sources feat/boevoi-render-legacy feat/publish-readiness-legacy-new-sources
git branch -vv | wc -l          # ожидание: main, integration, taxonomy-v2, olympiad-text-dedup, три wip = 7
```

## 6. Локальная база после сессии

`db.sqlite3` мигрирована (10 миграций 06.09), раздел олимпиад — на демо-данных
(`is_placeholder=True`). Резервная копия до миграций —
`db.sqlite3.bak_pre_sync_20260906` (932 МБ) рядом; удалить, когда приёмка
пройдена. Копия для проверки пути обновления — `reports/branch_sync_20260905/
logs/qls_upgrade_check_20260905.sqlite3` и `zero_20260905.sqlite3` — удаляются в
фазе 14.
