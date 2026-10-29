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

## Фаза 2. «Открыть в приложении Telegram»

- `POST /vp/wall/tg/<слаг>/` с `app=1` – тот же выбор кода (тот же 30-минутный код, тот же лимит
  10 в час), 302 на `tg://resolve?domain=<бот>&start=<код>`. Стандартный `HttpResponseRedirect`
  схему `tg` не пускает (`DisallowedRedirect`), поэтому класс `TgAppRedirect` с `allowed_schemes = ['tg']`.
- Экран 02: под «Открыть бота ещё раз» мелкая строка «Не открылось? Открыть в приложении Telegram» –
  форма с `app=1` БЕЗ `target="_blank"` (иначе останется пустая вкладка). Экран 01 не менялся.
- Новые тесты: `AppLinkTests` (5) в `test_wall_tg.py` и 1 в `test_wall_screens.py`. Всего новых 6.
- ⚠️ Замечено, не чинилось: `form-action 'self'` в CSP. Политика сейчас в режиме отчёта (ничего не
  блокирует), но Chrome сверяет с `form-action` и перенаправление формы, так что при включении
  принуждения `t.me` и `tg://` после POST придётся разрешить (`form-action 'self' https://t.me tg:`).
  Сейчас на каждое нажатие уйдёт отчёт на `/csp-report/`.

| Дефект | Покраснело |
|---|---|
| `app=1` отдаёт `t.me` | `test_app_redirect_is_tg_scheme_with_the_same_code` |
| у `app=1` новый код | `test_app_redirect_is_tg_scheme_with_the_same_code`, `test_app_first_then_site_button_shares_one_code` |
| форма `app=1` с `target="_blank"` | `test_waiting_has_the_open_in_app_form_without_new_tab` |
| ответ обычным `HttpResponseRedirect` (схема не разрешена) | три теста `AppLinkTests` |

## Фаза 3. Посредник для Андрея и порядок выкатки

- `deploy/tg_relay/nginx.conf`: порт 80 – только `/.well-known/acme-challenge/` (остальное `return 444`);
  порт 443 – `allow __OUR_SERVER_IP__; deny all;`, `proxy_pass https://api.telegram.org;`,
  `proxy_ssl_server_name on`, `Host api.telegram.org`, `proxy_read_timeout`/`send_timeout 90s`,
  `access_log off` на обоих серверах, `error_log … crit` (строка ошибки nginx несёт адрес с токеном).
  Имя и IP – две метки `__RELAY_HOST__`, `__OUR_SERVER_IP__`, README подставляет их одной командой `sed`.
  Без IPv6: запись DNS только A. `nginx` на маке нет – синтаксис конфига не проверялся самим nginx
  (проверит Андрей командой `nginx -t` на шаге 4б); тесты стерегут состав директив.
- `deploy/tg_relay/README.md`: шаги 0–6 + «Если не работает». Команды по одной, после каждой – что увидеть.
  Сертификат: сначала временный блок только на 80 порту (иначе `nginx -t` падает без сертификата), потом настоящий файл.
- `docs/VP.md`: «Выкатка стены – по шагам» переписана (боты есть → посредник → `.env` → пересоздать `web` и
  `restart nginx` → `tg_setup --ping` → `--check` → `--delete-webhook` и `tgbot` → почта → `vp_wall_status` →
  две учётки); раздел «Бот: посредник и длинный опрос»; вебхук – запасной (опрос и вебхук вместе не
  работают); «Если Telegram перестал отвечать во время тура».
- `docs/adr/0168`: «Дополнение 28.10: посредник и опрос» (факт, решение, отвергнутое: Cloudflare Worker, стена без Telegram, вебхук).
- `deploy/env.example`: пояснение к `TELEGRAM_API_BASE` и секрету.
- Новые тесты `RelayFilesTests` (6) в `test_wall_poll.py`.
- **Для Анича:** через посредника идут токен бота и Telegram ID учеников. Трансграничная передача (Telegram +
  хостинг посредника) – в Политику и в уведомление РКН.

| Дефект | Покраснело |
|---|---|
| из конфига убран `deny all` | `test_only_our_server_is_let_in` |
| журнал запросов включён | `test_no_access_log_anywhere` |
| `proxy_read_timeout` 30 с (длинный опрос оборвётся) | `test_forwards_to_telegram_and_holds_a_long_poll` |

## Фаза 4. Проверки

| Проверка | Итог |
|---|---|
| тесты сессии + `test_security_headers` | 715 → **757** (+42: опрос и служба 36, `app=1` 6), OK (skipped=1) |
| `manage.py check` | 0 |
| `check --deploy --fail-level WARNING`, окружение джоба `deploy-check` | «no issues» |
| `makemigrations --check --dry-run` | No changes detected (миграций в S2b нет) |
| `docker compose config` | **`docker` на маке нет** – compose проверен разбором YAML в тесте `TgbotServiceTests` (профиль, без портов, зависимости, метка жизни) |
| `bash -n deploy/entrypoint-tgbot.sh` | ок; режим в индексе git `100755` (сторож `test_deploy_scripts_executable` зелёный) |
| `ruff` по изменённым .py | чисто |
| `bandit -r vp -ll` | новых находок нет |
| `scripts/check_em_dash.py` | 0 |
| общая база | мои команды её не открывали (тесты в памяти, ручного прогона на ней не было) |
| nginx | на маке нет, `nginx -t` на `tg_relay/nginx.conf` не запускался – Андрей на шаге 4б |
| глазами | экран 02 с новой строкой НЕ смотрел (живой бот и `.env` недоступны); разметка проверена тестом |
| живой бот | не проверялся (`.env` закрыт); шаги для владельца – в отчёте |

Коммиты S2b: `c7b1e69c` (ф.1), `2c66d152` (ф.2), `3ea1f17a` (ф.3), далее коммит журнала фазы 4.


# S2c – две правки после сквозной проверки (29.10.2026)

## Фаза −1. Сверка

Ветка `feat/vp-wall-20261029`, `HEAD` = `origin/feat/vp-wall-20261029` = `109a7ff9`, дерево чистое.
`manage.py test vp problems.tests.test_security_headers` – **616 тестов**, skipped=1. ⚠️ Базовый прогон шёл в
фоне, пока я уже правил `_wall.html`: единственное падение (`test_no_sub_is_screen_03_without_polling`,
`assertNotIn('data-poll')`) – как раз тест, который эта правка и меняет; остальные 615 зелёные.

## Фаза 1. Экран 03 ждёт подтверждения подписки

Бот после «Проверить» обещает «вкладка обновится сама», а на 03 опроса не было (S2 его убрала: опрос с
переходом на `no_sub` гонял страницу по кругу `no_sub` → перезагрузка → снова 03).

- `wall.js`: решение «уйти или остаться» вынесено в чистую `vpWallLeave(okOnly, state)`: `'ok'` при
  `step≠contact` или `tg=ok`; `'nosub'` только на 02; на 03 `no_sub`/`error`/`waiting`/`none` – остаёмся.
  Опрос на 03 каждые 5 с (на 02 по-прежнему 3 с), ≤10 минут, только видимая вкладка. Шапка файла поправлена.
- `_wall.html`: на окне экрана `nosub` атрибуты `data-poll` и `data-poll-ok-only` (экран 02 не менялся).
- Тесты: `test_wall_screens` +4 (признак на 03 и на 03-error, на 02 его нет, на 01/почте опроса окна нет;
  старый `assertNotIn('data-poll')` снят); новый `vp/tests/test_wall_js.py` – таблица `vpWallLeave` через
  node (15 строк) и сценарий самого скрипта на заглушках DOM/`fetch`: три `no_sub` подряд → перезагрузок 0,
  затем `ok` → один `replace('/vp/x/?wall=1')`; на 02 `no_sub` уводит. Нет node – тесты пропускаются.
- Зубастость: (1) на 03 разрешён уход на `no_sub` → красные таблица и сценарий; (2) убран `data-poll-ok-only`
  из разметки → 2 красных; (3) `data-poll-ok-only` повешен и на 02 → 2 красных. Всё возвращено.
- Не проверено: живой опрос в браузере с настоящим ботом (в браузере проверит владелец по шагам отчёта).

## Фаза 2. CSP пропускает Telegram

Формы стены отвечают редиректом на `https://t.me/…` и `tg://…`; при `form-action 'self'` в режиме отчёта
браузер уже писал нарушение, а в боевом режиме остановил бы редирект.

- `config/security_headers.py`: `form-action 'self' https://t.me tg:` с комментарием, почему исключение.
- `problems/tests/test_security_headers.py`: +1 тест – ровно одна директива `form-action` и она равна
  `'self' https://t.me tg:` (лишний источник тоже краснит). Прежний `test_csp_names_the_key_directives`
  (подстрока `form-action 'self'`) не тронут и зелёный.
- `docs/SECURITY.md`: абзац в разделе про CSP.
- Зубастость: убран `tg:` → красный; добавлен посторонний источник → красный. Возвращено.
- Попутно: `problems.tests.test_signup_source.WebvisorTests` – 2 падения (`test_vp_landing_board_is_hidden`,
  `test_vp_my_attempts_list_is_hidden_header_and_tabs_stay`). Они есть и на `109a7ff9` (проверено отдельным
  временным worktree), к S2c отношения не имеют и в набор «тесты сессии» не входят – заведено как баг.
- Не проверено: боевой режим CSP целиком (политика остаётся в режиме отчёта; перевод – отдельная работа).

## Фаза 3. Проверки

| Проверка | Итог |
|---|---|
| `manage.py test vp problems.tests.test_security_headers` | 616 → **624** (+8: экраны 4, CSP 1, wall.js 3), OK (skipped=1) |
| `manage.py check` | 0 |
| `makemigrations --check --dry-run` | No changes detected (миграций в S2c нет) |
| `scripts/check_em_dash.py` | 0 |
| `ruff` по `vp`, `config`, `test_security_headers.py` | чисто |
| `problems.tests.test_signup_source.WebvisorTests` | 2 падения, были и на `109a7ff9` (вне набора сессии) – заведено как баг |
| глазами / живой бот | экран 03 в браузере и настоящий бот НЕ проверялись (`.env` закрыт); сценарий скрипта проверен в node на заглушках; шаги для владельца – в отчёте |

Коммиты S2c: `e561f716` (ф.1), `663e1cf9` (ф.2), далее коммит журнала фазы 3.


# Перед main – подготовка ветки к слиянию (29.10.2026)

Слияние в main НЕ делается: тренажёр выкатывается вместе со стеной, когда на бою работают бот (посредник
за рубежом) и почта. Здесь ветка только готовится.

## Фаза −1. Сверка

- Ветка `feat/vp-wall-20261029`, дерево чистое, после `git fetch` `HEAD` = `origin/feat/vp-wall-20261029` = `b41add52`.
- `origin/main` = `c5e71939`, `git merge-base --is-ancestor origin/main HEAD` – да (main целиком в ветке).
- Другой сессии Claude в worktree нет. Висят только dev-серверы `runserver 8141` (старые, из этого же
  worktree, без записи в общую базу) – тестам не мешают.

## Фаза 1. Три устаревших теста

- `test_check_deploy_is_clean` (`problems/tests/test_production_settings.py`): подставные пути стены вынесены
  в словарь `WALL_ENV` рядом с `FAKE_ENV` (токен, ник, секрет вебхука, `MAIL_ENABLED`, `EMAIL_*` – те же,
  что в джобе `deploy-check`). Комментарий: на бою оба пути включены; менять оба места вместе.
  Добавлен `test_check_deploy_warns_when_wall_token_is_missing`: без токена боевые настройки дают `vp.W001`
  (раньше `vp.W001` проверялась только вызовом функции, не в боевых настройках).
  ⚠️ Ловушка: `config/settings.py` читает `.env` через `setdefault`, поэтому УДАЛЁННАЯ из окружения переменная
  возвращалась из `.env` разработчика, и тест «без токена» у того, у кого токен в `.env`, молча был бы
  зелёным. Теперь недостающие пути задаются явной ПУСТОЙ строкой (она `.env` перебивает), `VP_WALL_ENABLED=1`
  выставлен явно. (`.env` я не открывал: причину нашёл по тексту загрузчика.)
- `test_vp_landing_board_is_hidden` (`problems/tests/test_signup_source.py`): на 2 туре, вариант
  `load_demo('10')`, зачётные попытки двух пользователей (`_attempt`). Класс блока строк разбирается по
  смыслу: среди классов `vp-land-rows` есть `ym-hide-content` (с `is-nocls` или без). Логины есть в HTML и
  нет в `recorded_text`; «Лучшие попытки» остаются в записи.
- `test_vp_my_attempts_list_is_hidden_header_and_tabs_stay`: на 2 туре. Метка зачётной попытки в `my.html`
  прежняя – «в таблице · 1-е» (проверено по шаблону). Название варианта есть в HTML и не в записи; «Мои
  попытки» и «Все · 1» в записи.
- Зубастость (каждый дефект вносился и возвращался): без `ym-hide-content` у `vp-land-rows` в
  `index.html` – красный только тест 2; без него в `my.html` – красный только тест 3; пустой токен в
  `WALL_ENV` – красный `test_check_deploy_is_clean`. (Первая попытка с `sed -i` на macOS не применилась и
  «OK» ничего не доказывало – повторено через Python-замену.)
- Итог: `vp` + `problems.tests.test_signup_source` + `problems.tests.test_production_settings` целиком –
  671 тест, OK (skipped=1).

## Фаза 2. Полный прогон и разбор падений

`./venv313/bin/python manage.py test` (SQLite в памяти, без `--parallel`, на коммите `d1e4e16a`):

| Что | Значение |
|---|---|
| тестов | **7 659** (на 29.10 было 7 658 + 1 новый `test_check_deploy_warns_when_wall_token_is_missing`) |
| время | 853 с (≈ 14,2 мин) |
| failures / errors / skipped | **2 / 32 / 47** (всего 34 проблемы) |
| код выхода | 1 |

Каждый упавший тест – на `origin/main` (`c5e71939`) во временном worktree (`/tmp/qls_main`, окружение то же
`venv313`; worktree удалён). Все семь затронутых модулей на main: 83 теста, failures=1, errors=32.

| Тест / группа | Падает на main? | Причина одной строкой |
|---|---|---|
| `catalog.tests.test_lexical_bm25` (8 errors) | да | в `venv313` нет `bm25s` и `pymorphy3` |
| `problems.tests.test_find_olympiad_text_duplicates` (11 errors) | да | в `venv313` нет `rapidfuzz` |
| `problems.tests.test_text_dedup.FuzzyRatioTests` (3 errors) | да | нет `rapidfuzz` |
| `catalog.tests.test_corpus_disk_cache` (6 errors) | да | нет `bm25s` (импорт лексической ноги) |
| `problems.tests.test_load_probe.FakeDelayTests.test_real_provider_does_not_sleep` (1 error) | да | в `venv313` нет `openai` |
| `calc2.tests.test_calc2_math.test_calc2_control_numbers` (1 fail) | да (проверено со ссылкой на `node_modules`: те же `✗`) | «Регулятор сцены · правка значения»: поле 40,375 px при потолке 40; `calc2` ветки = `calc2` main (`git diff` пуст). Карточка уже есть: 3ceb11c9 |
| `problems.tests.test_tree_walk.НаЖивомДеревеTests.test_обход_не_выходит_за_пределы_проекта` (1 fail) | на main не запускался в той же папке; на `/tmp` зелёный и у main, и у кода ветки | тест считает чужими все пути, где есть сегмент `worktrees`/`.claude`, а этот worktree сам лежит в `.claude/worktrees/` – краснеет от места папки, не от кода. Код ветки, запущенный из `/tmp/qls_branch_check`: 13/13 OK |

Новых падений от ветки (зелёных на main, красных на ветке по причине в коде ветки) – **нет**. Починок в п. 3
не потребовалось, повторный полный прогон не нужен. Все три устаревших теста фазы 1 в полном прогоне зелёные.

Карточки «Надо»: окружение мака (нет четырёх пакетов) – новая; `test_tree_walk` в worktree внутри
`.claude/worktrees` – новая; calc2 40,375 px – уже была (3ceb11c9, добавлен комментарий); WebvisorTests –
уже была (407b11c9-…-bc18, закрывается этой сессией); `pip-audit` – уже была (408b11c9), здесь не трогали.

## Фаза 3. Остальные проверки CI у себя (без `pip-audit`)

| Проверка | Итог |
|---|---|
| `ruff check .` | All checks passed |
| `bandit -r problems catalog teacher student game calc2 config olympiads vp -ll` (как в джобе) | No issues identified (Medium 0, High 0; Low 738 ниже порога) |
| `makemigrations --check --dry-run` | No changes detected |
| `manage.py check` | 0 ошибок, 0 silenced |
| `check --deploy --fail-level WARNING` с окружением джоба `deploy-check` | код 0, «no issues (1 silenced)» |
| `scripts/check_em_dash.py` | код 0, «—» вне комментариев: 0 |
| `pip-audit` | НЕ запускался – отдельная задача (408b11c9, Pillow 12.3.0, twisted, msgpack, autobahn) |

## Фаза 4. Notion и остановка

- Задача стены 407b11c9-…-81d0: блок «Перед main» с итогами записан в тело карточки (свойство «Заметки» не переписывалось: длинный прежний текст с экранированием при пересборке испортился бы).
- Основная задача тренажёра 403b11c9-…-8111: комментарий «ветка готова к слиянию, ждём бота и почту на бою».
- Карточка WebvisorTests (407b11c9-…-bc18): «Готово», комментарий с коммитом `d1e4e16a`.
- Новые «Надо / Техническое»: окружение мака без rapidfuzz, bm25s, pymorphy3, openai (32 ошибки); `test_tree_walk` в worktree внутри `.claude/worktrees`. Комментарий в 3ceb11c9 (calc2 40,375 px).
- Ветка НЕ запушена после этой сессии (коммиты `d1e4e16a`, `b7484c2c` и этот): `git push origin feat/vp-wall-20261029`. В main ничего не сливалось, main не трогался.

## Документы ред. 2

### Фаза −1. Сверка (29.10.2026)
- Ветка `feat/vp-wall-20261029`, дерево чистое, `HEAD` = `origin/...` = `ca37030d`.
- В `legal/texts/` семь файлов, везде «Редакция 1 от [ДАТА]»; `docs_version == '1'`; `[ПОСРЕДНИК]` нигде нет.
- `vp/bot.py`: `ready` / `ready_surveyed` / `moved` содержат `{login}` (старые тексты, не PREMAIN).
- `_wall.html`: две «Нажимая кнопку, вы соглашаетесь с» (строки 85 и 172) и одна сноска Instagram (61).
- Базовый прогон `manage.py test legal vp`: 769 тестов, OK (skipped=1), 93 с.

### Фаза 1. Тексты документов
- `consent.md`, `privacy.md`, `terms.md`, `consent_mail.md` – дословно из приложений A–D.
- `consent_ai.md`, `cookies.md`, `recommendations.md`: «Редакция 1 от 20.10.2026».
- Согласие на рассылку без пометки «ЧЕРНОВИК» (`legal/documents.py`, `docs/MAIL.md`).
- Согласие на рассылку остаётся «Редакция 1» (так в приложении D), хотя `docs_version` станет 2: оно живёт своей редакцией и от `docs_version` не зависит.
- Тесты: `test_requisites` (маркер редакции по документам), `test_pages` (дата у изменённых из настройки, у трёх неизменённых – 20.10.2026, получатели, пункт 3.4). Пока ожидание «Редакция 2» зашито литералом; фаза 4 свяжет его с `docs_version`.
- `manage.py test legal`: 164 теста, OK.
- Зубастость: `[ДАТА]` обратно в `cookies.md` → красные 3 теста (`..._stay_untouched_by_substitution`, `..._keep_their_own_date`, `..._right_edition_marker`); возвращено.

### Фаза 2. Метка `[ПОСРЕДНИК]` и `legal.E003`
- `settings.LEGAL['tg_relay']` ← `LEGAL_TG_RELAY`; `legal/documents.py`: третья метка (приватный символ до разбора, экранированный HTML после; пусто, длиннее 200 или с переводом строки → «[не заполнено]»).
- `legal/checks.py`: `legal.E003` при `DEBUG=False` и пустом `LEGAL_TG_RELAY` (E001/E002 не менялись).
- Подставное «Example Hosting B.V., Нидерланды»: джоб `deploy-check` в `ci.yml`, `problems/tests/test_production_settings.py`. Переменная (пустая) добавлена в `deploy/env.example` и `deploy/env.dev.example` (площадка dev живёт на боевых настройках, E003 иначе не даст ей подняться). Строки в `docs/VP.md` (порядок выкатки) и `docs/SERVER.md`.
- Тесты: `legal` 170 OK (было 164), `test_production_settings` + `test_signup_source` 62 OK (в них `check --deploy` с окружением джоба – 0 замечаний).
- Зубастость: условие E003 заменено на `if False` → `test_empty_relay_is_error_e003_when_not_debug` красный; возвращено.
- Ловушка: метки в `documents.py` – это `…` (невидимые символы); правка файла скриптом по строке «DATE_MARK = 'DATE'» не находит.

### Фаза 3. Стена и бот
- `_wall.html`: три сноски дословно из приложения E (Instagram; экран почты; экран Telegram «из ваших данных мы передаём ему только ID в Telegram»). Ссылки на Политику те же. Строка «Галочка – по желанию…» на экране `known` (без слов о Политике) не менялась.
- `vp/bot.py`: `ready`, `ready_surveyed`, `moved` из приложения F; `_ready_text` и `tail` больше ничего не подставляют (`.format(login=…)` убран). Остальные тексты бота не менялись.
- Старые строки поправлены в `test_wall_screens.py` и `test_wall_tg.py` (три места).
- Новые тесты: `OnlyTelegramIdLeavesTheSiteTests` (5: подписка есть, подписки нет, «Проверить», вторая редакция «ready_surveyed», перепривязка с другого аккаунта; логин `zzlogin_marker`, почта, имя и фамилия сайта не встречаются в параметрах ни одного вызова `vp.telegram.call`, вызовов > 0) и `FootnoteTests` (5).
- `vp.tests.test_wall_screens` + `test_wall_tg`: 70 тестов OK. `scripts/check_em_dash.py` – 0.
- Зубастость: к тексту `ready` дописан логин → 4 теста инварианта красные; на экран Telegram возвращено «Нажимая кнопку, вы соглашаетесь» → `test_no_screen_says_you_agree_to_the_policy` красный. Оба дефекта убраны.
