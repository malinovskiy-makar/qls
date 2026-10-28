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

## Фаза 3. Telegram: ссылка, бот, проверка подписки

- `b2244469`. `vp/telegram.py` (`call`, `subscription`, `check_subscription`; `urllib`,
  `# nosec B310` после проверки схемы `https://`; токен вычищается, исключение
  поднимается вне `except` — без цепочки с адресом). `vp/bot.py` (`TEXTS`, `/start <код>`
  с атомарным гашением, переход привязки к свежему коду, кнопка «Проверить» с
  `answerCallbackQuery` на каждое нажатие, правка → `sendMessage` при отказе).
- Адреса: `POST wall/tg/<слаг>/` (тот же код 30 минут, 10 новых в час → `?tg=often`),
  `POST wall/check/<слаг>/` (не чаще раза в 5 с), `GET wall/state/?v=` (гость 403,
  скрытый слаг 404), `POST tg/hook/` (пустой секрет — всегда 403; `compare_digest` по
  байтам; >64 КБ / не JSON → 400; повтор `update_id` за сутки не обрабатывается; ошибка → 200).
- Команды `tg_setup` (`--ping/--check/--set-webhook/--delete-webhook/--info`) и `tg_poll`
  (`--force` только для бота разработки). Переменные — в `deploy/env.example`,
  `deploy/env.dev.example`.
- Экраны окна 01 (кнопка), 02 (скрыт рядом с 01, `data-poll`), 03 (без опроса).
- Новые тесты `vp/tests/test_wall_tg.py`: 24. Тесты сессии: 647 → **671**, OK.

| Дефект | Покраснело |
|---|---|
| вебхук не проверяет секрет | `test_empty_secret_closes_the_hook_for_everyone`, `test_missing_or_wrong_secret_is_403_and_does_nothing`, `test_non_ascii_header_is_403_not_500` |
| пустой секрет пропускает | `test_empty_secret_closes_the_hook_for_everyone` |
| код не гасится после использования | `test_same_or_old_code_is_expired`, `test_start_with_subscription_links_and_gives_contact` |
| `left` считается подпиской | `test_left_asks_to_subscribe_then_check_gives_contact`, `test_states` |
| на «Проверить» без подписки нет `answerCallbackQuery` | `test_every_check_press_is_answered` |
| токен попадает в текст исключения | `test_network_error_has_no_token` |

## Фаза 4. Окно стены и анкета по макетам

- `4a51744b`. Экран 06 и `POST wall/survey/<слаг>/`: контакта нет → окно; несданная
  попытка → в неё; анкета сохраняется один раз (не перезаписывается); класс в профиле
  пишется, только если пуст (профиль не создаётся); режим — из `vp_wall_next`, иначе из
  скрытого поля. Класс заранее: анкета → профиль → класс варианта.
- Окно (`_wall.html`): шапка «Демоверсия 2 тура · 10 класс · 70 минут» (`landing.wall_eyebrow`,
  `duration_words`), шаги, экраны 01/02/03/04/04b/05/06/«закрыто» по таблице; без JS — блок
  на странице, с JS — модальное (`close()` → `showModal()`; отложенный `close` не стирает
  `?wall`). Опрос `wall/state` — только на 02, каждые 3 с, ≤10 мин, только видимая вкладка.
- Стили — только токены раздела; телефон ≤560 px — окно снизу с ручкой; ссылка в подписи
  галочки — `--accent-ink` (в тёмной теме была браузерной синей).
- Глазами (сервер на копии, подставной бот `weconomics_wall_dev_bot`): 01, 02, переход
  02→03 опросом после имитации ответа бота, 06, телефон 390 px (`scrollWidth 390 = clientWidth 390`),
  тёмная тема 04. Ошибок в консоли нет.
- Окно гостя при `MAIL_ENABLED`: «логин, почта и пароль – почту подтвердим кодом из письма».
- Новые тесты `vp/tests/test_wall_screens.py`: 26. Тесты сессии: 671 → **697**, OK.

| Дефект | Покраснело |
|---|---|
| анкета перезаписывает класс | `test_profile_grade_filled_only_when_empty` |
| окно показывается при пройденной стене | `test_no_window_after_wall_is_passed` |
| `with_timer` теряется (всегда 1) | `test_complete_answers_start_the_attempt_with_chosen_mode`, `test_guest_without_timer_all_the_way` |
| анкета не проверяет несданную попытку | `test_double_post_makes_one_attempt` |
| на 03 включён опрос | `test_no_sub_is_screen_03_without_polling` |

## Фаза 5. Данные, удаление, статистика, документация

- `2e7dc689`. `erase_user`: строки стены уходят каскадом от `user.delete()` (тест).
  `problems/retention.py`: коды привязки старше суток — в `plan()` и `purge()`.
- Админка: `VPWall` (список, фильтры путь/класс/источник/2 тур), привязки и коды — только
  чтение, отпечаток кода не показывается. Команда `vp_wall_stats [--days 7]`.
- События: `vp_wall_shown`, `vp_wall_tg_click`, `vp_wall_tg_ok`, `vp_wall_tg_nosub`,
  `vp_wall_email_sent`, `vp_wall_email_ok`, `vp_wall_survey_done` (описаны в `vp/tracking.py`).
- Документы: `docs/VP.md` «Стена 2 тура», `docs/MAIL.md` (интерфейс), ADR **0168**,
  `docs/SECURITY-MATRIX.md` (6 адресов), `docs/SECURITY.md`, строка в `CLAUDE.md`,
  `scripts/legal/pd_inventory.py` (Telegram ID и ник; ответы анкеты — в docs/VP.md).
- Новые тесты `vp/tests/test_wall_data.py`: 4. Тесты сессии: 697 → **701**, OK;
  `problems.tests.test_security_headers` (обход маршрутов: GET ничего не пишет) — OK.

| Дефект | Покраснело |
|---|---|
| `VPWall` без каскада (переживает удаление аккаунта) | `test_erase_user_leaves_no_wall_rows` |
| `purge` не удаляет коды привязки | `test_tokens_older_than_a_day_go_fresh_stay` |
| сухой прогон молчит о кодах привязки | `test_tokens_older_than_a_day_go_fresh_stay` |
| привязку можно править в админке | `test_wall_pages_open_and_links_are_read_only` |
| статистика не считает застрявших | `test_stats_show_paths_and_survey` |

## Фаза 6. Инварианты

| Проверка | Итог |
|---|---|
| тесты сессии | 532 (до слияния) → 616 (слияние) → **701**, OK (skipped=1) |
| `manage.py check` | 0 |
| `check --deploy --fail-level WARNING`, окружение джоба `deploy-check` | 0 |
| то же с `TELEGRAM_BOT_TOKEN=` | ровно `vp.W001` |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate` / `showmigrations problems vp` на копии | всё применено |
| `scripts/check_em_dash.py` | 0 |
| `ruff check` по 57 изменённым .py | чисто |
| `bandit -r vp problems -ll` | Medium 0, High 0 |
| общая база: `VPAttempt` / `VPAnswer` / пользователи | 2 / 88 / 16 — как в фазе −1; `vp/0005` к ней не применялась |
| живой бот | пропущено: чтение `.env` закрыто правилами доступа сессии, токена я не видел |

---

# S2b: доделка стены (28.10.2026, вечер)

Продолжение в той же ветке `feat/vp-wall-20261029` от `c0f006d3`. Причина: с боевого сервера
Telegram недоступен (`curl https://api.telegram.org/` – timeout, Андрей, 28.10) –
решения Notion `407b11c9-2bc1-8120-98b1-faa08aea97d1` (посредник и длинный опрос) и
`407b11c9-2bc1-818f-9138-f2539e50d554` (боты `@weconomics_bot`, `@weconomics_dev_bot`).

## Фаза −1. Сверка

| # | Проверка | Результат |
|---|---|---|
| 1 | ветка, дерево, `HEAD` после `git fetch` | `feat/vp-wall-20261029`, чисто, `HEAD` = `origin/…` = `c0f006d3` |
| 2 | другая сессия в worktree | нет (по `git worktree list` у ветки один worktree) |
| 3 | тесты сессии + `test_security_headers` | **715**, OK (skipped=1). Состав: `vp`, `problems.tests.{test_auth_hardening, test_account_email, test_attach_verified_email, test_email_codes, test_mail_channel, test_register_email, test_password_reset_code, test_security_headers}`, `legal.tests.{test_register, test_erase_user, test_purge_expired, test_mail_consent}` |
| 4 | `tg_poll`, `wall_tg` как в журнале S2 | да; **расхождение: `tg_poll` не мог работать вовсе** (см. фазу 1) |

## Фаза 1. Длинный опрос как боевая служба

- **Найдена ошибка S2.** `telegram.call(method, *, timeout=8, **params)`: HTTP-таймаут назывался так же,
  как параметр `timeout` метода `getUpdates`. Прежний `tg_poll` падал с `TypeError: got multiple values
  for keyword argument 'timeout'` на первом же запросе – в S2 живого бота не было, и тесты `getUpdates`
  не гоняли. Теперь HTTP-таймаут – `http_timeout`.
- `TelegramError.code` (код Telegram или HTTP): по нему опрос отличает 409 и 401.
- `vp.bot.handle_once(update)` – единственный отсев повторов (`cache.add('vp:tg:update:<id>', сутки)`) и
  единственный перехват сбоя обработки; вебхук и опрос пользуются ею.
- `tg_poll`: `timeout=50`, HTTP `timeout+10`, `allowed_updates`, `offset`; сетевая ошибка и 5xx – пауза
  5/10/20/40/60 с, сброс после удачи; 409 и 401 – `CommandError` (код 1); старт `getMe` → «Опрос запущен,
  бот @…» → `getWebhookInfo`; метка жизни `/tmp/tg_poll_alive`; SIGTERM – выход с кодом 0 (прерывает
  ожидание сети, но не обработку уже взятого обновления); скрытые `--max-loops` и `sleep` для тестов.
- `config/settings.py`: логгер `vp` (INFO, консоль) – без него «Опрос запущен» и паузы не попали бы в
  `docker compose logs`.
- Служба `tgbot` в `deploy/docker-compose.yml` (профиль `tgbot`, без портов, ждёт `web` и `redis`),
  `deploy/entrypoint-tgbot.sh` (без `migrate`, режим 755), раздел в `docs/SERVER.md`.
  `docker` на маке нет: compose проверен разбором YAML (тест `TgbotServiceTests`).
- Новые тесты `vp/tests/test_wall_poll.py`: 30.

| Дефект | Покраснело |
|---|---|
| пауза не растёт | 4 теста `PollNetworkTests` |
| повтор не отсекается в опросе | 3 теста `PollOnceTests` |
| 409 продолжает цикл | `test_409_stops_with_a_clear_message`, `test_exit_code_of_409_is_not_zero` |
| `offset` не сдвигается | `test_two_updates_are_handled_and_offset_moves` |
| HTTP- и Telegram-`timeout` снова одно имя | оба теста `RealCallShapeTests` |
| SIGTERM не прерывает ожидание | `test_sigterm_while_waiting_for_telegram_exits_cleanly` |
| вебхук не ловит сбой обработки | `test_hook_answers_200_when_handling_fails` (**раньше этого теста не было** – мутация выжила, тест добавлен) |
| у службы нет профиля / в entrypoint `migrate` | `TgbotServiceTests` |
