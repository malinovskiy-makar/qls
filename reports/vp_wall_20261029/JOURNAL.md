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

## Фаза 1. Модели и правило стены

- `7b69be1a`. Миграция `vp/0005_wall` (`VPWall`, `VPTelegramLink`, `VPTelegramToken`) —
  только `vp`; применена к копии (`migrate --settings=config.settings_check`).
- Правило — `vp/wall.py` (`required`, `paths`, `step`, `pass_contact` атомарным
  `UPDATE … WHERE contact_via=''`). Подтверждённая почта контактом не считается.
- `vp.views.start`: гость → регистрация с `next=интро?wall=1` безусловно, выбор
  режима — в `session['vp_wall_next']`; несданная попытка — до стены; стена →
  `?wall=1` без попытки; нет путей → `?wall=closed` + предупреждение в лог. Тело
  создания попытки — `_start_attempt`.
- Настройки: `VP_WALL_ENABLED` (тесты 0, иначе 1, в боевых не переопределено),
  `VP_WALL_TG_ENABLED`, `TELEGRAM_*` (в тестах пустые), `config.WALL_TOURS=(2,)`.
- `vp.W001` (предупреждение), `ci.yml` джоб `deploy-check` — подставные `TELEGRAM_*`
  и почта. Команда `vp_wall_status`.
- `student_band`: анкета после `session['vp_band']`, до класса последней попытки.
- `test_gate`: 4 ожидания адреса `next` (строки 28, 70, 71, 129) → `…%3Fwall%3D1`.
- Новые тесты `vp/tests/test_wall_rule.py`: 15. Тесты сессии: 620 → **635**, OK.

| Дефект | Покраснело |
|---|---|
| `start` не спрашивает стену | `test_no_contact_goes_to_wall_without_attempt`, `test_contact_without_survey_still_walls`, `test_verified_email_alone_is_not_a_contact`, `test_staff_meets_the_wall_on_tour2_but_not_on_tour1`, `test_no_paths_at_all_closes_the_entrance` |
| `step` считает `has_verified_email` контактом | `test_verified_email_alone_is_not_a_contact` |
| несданная попытка проверяется после стены | `test_unfinished_attempt_returns_without_wall` |
| класс из анкеты выше сессии | `test_tab_choice_in_session_beats_survey` |

## Фаза 2. Почта в окне стены

- `39535830`. `POST /vp/wall/email/<слаг>/` (`vp/views_wall.py::wall_email`): `send`,
  `confirm`, `resend`, `change`, `use`. Вход обязателен (гость → `/login/`), вариант —
  `_variant_or_404`, стена для варианта нужна, `MAIL_ENABLED=0` → 404. Свою логику кодов
  не пишем — только `problems.email_codes` и `legal.consent`.
- `send` при уже подтверждённой почте → 400; `use` без неё → 400, кодов не шлёт.
  Со стены согласие только даётся (`Source.VP_WALL`), не отзывается.
- Окно на интро (`vp/templates/vp/_wall.html`, `wall_window`): экраны 04, 04b, 05,
  «закрыто», 01 (пока без кнопки Telegram — фаза 3). Сообщения — через сессию
  (`vp_wall_flash`), окно работает без JS. «Другая почта» → `/account/email/?next=интро?wall=email&src=vp`.
- `ym-hide-content` на показанной почте, `ym-disable-keys` на полях почты и кода.
- Новые тесты `vp/tests/test_wall_email.py`: 12. Тесты сессии: 635 → **647**, OK.

| Дефект | Покраснело |
|---|---|
| галочка отмечена по умолчанию | `test_screens_hide_email_from_webvisor` |
| `use` шлёт код | `test_use_with_verified_email_needs_no_code` |
| стена отзывает согласие | `test_unchecked_box_never_revokes` |
| `send` разрешён при подтверждённой почте | `test_send_with_verified_email_is_refused` |
