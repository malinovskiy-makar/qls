# Журнал: тренажёр 2 тура ВП, сессия R (R1 + R1b + R2 + R3), с 28.10.2026

Промпт — `~/Downloads/PROMPT_VP_TOUR2_R_20261028.md` (вставлен в чат, сохранён туда же
Claude Code для повторных запусков). Работа — в worktree
`.claude/worktrees/vp-tour2-20261025`, ветка `feat/vp-tour2-20261025`, поверх `6d9389d9`.
Пуша и вливания в `main` нет.

## Фаза −1. Сверка с реальностью — ЗАКРЫТА (запуск 1, 28.10)

| Проверка | Факт |
|---|---|
| worktree `.claude/worktrees/vp-tour2-20261025` | есть |
| Ветка, дерево | `feat/vp-tour2-20261025`, чистое; после `git fetch` `HEAD` = `origin/…` = `6d9389d9` |
| Другая сессия в worktree | нет (чужих правок нет) |
| Макеты | `~/Downloads/vp_tour2_mockups_20261028.zip` → `claude/mockups/vp_tour2_20261028/`: `README.md`, `screens/` 10 PNG, `html/` 10 HTML + `vp.css` + `ds/`, `source/` 8 `.dc.html`; коммит `d10c7ae0` |
| Демоверсии в локальной базе | 3 опубликованных варианта 2 тура: 9 — 17, 10 — 18, 11 — 18 заданий |
| Базовая линия базы | `VPAttempt` 2, `VPAnswer` 88 |
| `manage.py test vp` до правок | 416 тестов, OK, `skipped=1`, код 0 (53,6 с) |
| `rescore_vp --all --dry-run` | вариантов 13, сданных попыток проверено 2, «Изменений нет» |
| `node`, Playwright | `node` v24.16.0 есть; в worktree нет `node_modules/playwright` → `test_browser.py` пропускается (к тому же он идёт только на PostgreSQL) |

Notion прочитан: R1 `404b11c9…5224` (переведена в «В работе»), R2–R3 `404b11c9…02e8`, решение
`407b11c9…dedf`.

## Фаза 1. Подсчёт, правила, тексты условий — ЗАКРЫТА (коммит `04480c3a`)

* `vp/scoring.py`: `_LONG_MINUS` (U+2212, U+2012, U+2013, U+2014, U+FE63, U+FF0D); причина `minus`
  проверяется ПЕРВОЙ; `_soft_number` — единственное место мягкой починки; `canonical_number`
  (починка + округление до сотых `ROUND_HALF_UP`, не число → `None`); `_would_be_correct`
  переведён на них (сверка с `accepted` — и до округления, и после, как раньше «3,125»).
* `vp/review.py::_number_fix`: `minus` → «-»; совет только если исправленное проходит
  `NUMBER_FORMAT` (для «−25 000» и «37.5.1» — пусто).
* `result.html`: строка причины `minus`; у `dot`/`space` без совета «Нужно …» не пишется.
* `_rules.html`: «Как вводить число» начинается с «Без апелляции: …», повтор «0 баллов, как на
  туре» убран, в «Неверно» добавлено «−318». Ссылка на тренировку — в фазе 8.
* `vp_extras.nbsp_num` (вне формул) подключён к условию, кускам пропусков, вариантам, строкам
  соотнесения, решениям, определениям змейки — в прохождении, разборе и «Дорешать»
  (`_practice.html` получил свой `{% load vp_extras %}`: include тегов не наследует).
* YAML: демо 10 №16, демо 11 №15 — `2 \\cdot M/P`. `--dry-run`: 9 — «Изменений нет», 10 — «№16:
  изменены поля statement», 11 — «№15: изменены поля statement». Загружено `--publish`,
  повторный `--dry-run` — «Изменений нет» у обоих, 3 варианта 2 тура опубликованы (17/18/18).
* Тесты `vp/tests/test_r_scoring.py` (6): таблица из 8 строк + все шесть знаков, `canonical_number`
  (11 строк), `nbsp_num`, строка разбора владельцу / её нет у чужого.
* `manage.py test vp`: 416 → 422, OK (`skipped=1`). `rescore_vp --all --dry-run` — 2 попытки,
  «Изменений нет». Длинных тире в изменённых шаблонах — 0.

Изменённые старые тесты: нет.

| Дефект | Покраснело |
|---|---|
| проверка `minus` убрана из `_format_error` | `test_every_long_minus_sign_is_minus`, `test_owner_sees_long_minus_reason_and_fix` |
| `_number_fix` без проверки `NUMBER_FORMAT` | `LongMinusTableTests.test_table` (−25 000, 37.5.1) |
| `canonical_number` без округления | `CanonicalNumberTests` (1,607, 3,125, −0,125) |
| `nbsp_num` трогает формулы | `NbspNumTests` |
| ветка `minus` в `result.html` выключена | `test_owner_sees_long_minus_reason_and_fix` |
| `_soft_number` не меняет длинный минус | `CanonicalNumberTests`, `test_every_long_minus_sign_is_minus` |
