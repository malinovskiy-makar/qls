# Журнал: стена тренажёра ВП 2 тура (сессия S2, 29.10.2026)

Ветка `feat/vp-wall-20261029` от `cec1be97`, worktree
`.claude/worktrees/vp-tour2-20261025`. Промпт — «Тренажёр ВП 2 тур — сессия
стены (S2)». Notion-задача `407b11c9-2bc1-81d0-8c96-c584cf360aa9`.

## Фаза −1. Сверка с реальностью

| # | Проверка | Результат |
|---|---|---|
| 1 | worktree `.claude/worktrees/vp-tour2-20261025` | есть |
| 2 | ветка, дерево, HEAD | `feat/vp-tour2-20261025`, чисто, HEAD = origin = `cec1be97` (первый запуск) |
| 3 | чужие изменения в worktree | нет |
| 4 | `origin/feat/mail-codes-20261026` | `9c991b77`, новых коммитов нет |
| 5 | макеты | `~/Downloads/vp_wall_mockups_20261028.zip`: README, 9 PNG, 9 HTML + vars.css + ds/, 9 .dc.html + vars.css — совпало |
| 6 | базовая линия на `cec1be97` | `vp` 479, `test_auth_hardening` 26, `test_register` 5, `test_erase_user` 8, `test_purge_expired` 14 = 532, OK (skipped=1) |
| 7 | максимальный ADR по веткам | 0167 (`origin/feat/ai-exam-c`) → **мой номер 0168** |
| 8 | общая база (только чтение) | `VPAttempt` 2, `VPAnswer` 88, пользователей 16 |
| 9 | копия | `cp db.sqlite3 db_check.sqlite3` — сделано |
| 10 | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` в `.env` | **не проверено**: чтение `.env` закрыто правилами доступа сессии. Считаю «нет» — живой бот в фазе 6 пропускается |

## Фаза 0. Почта Анича в ветке и общий кусок кода

- `43fdf56a` — макеты стены ВП (35 файлов).
- `4bc3ba0a` — слияние `origin/feat/mail-codes-20261026` без конфликтов (56 файлов).
- `migrate --settings=config.settings_check`: в копии применились `problems`
  0080, 0081 (копия была старше ветки), 0082, 0083. Общая база не тронута.
- Тесты сессии после слияния: **616** (= 479 `vp` + 84 почты + 53 прежних), OK (skipped=1).
- `0341570b` — `attach_verified_email` + `EmailTaken` + `TAKEN_MESSAGE`, тексты
  `send_error` / `check_error` / `minutes` переехали в `problems/email_codes.py`;
  `account_email` пользуется ими, согласие по галочке — после привязки. Тесты
  Анича без правок зелёные (`test_account_email` 13, `test_register` 5,
  `test_register_email` 24, `test_password_reset_code` 9).
- Новые тесты `problems/tests/test_attach_verified_email.py`: 4.
- Тесты сессии: 616 → 620.

| Дефект | Покраснело |
|---|---|
| убрать И повторную проверку, И перехват `IntegrityError` | `test_email_verified_by_other_raises_and_changes_nothing`, `test_race_other_account_confirms_after_free_check` (ERROR: IntegrityError) |
