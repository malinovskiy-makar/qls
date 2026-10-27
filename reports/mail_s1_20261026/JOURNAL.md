# Почта, сессия 1 из 2 — журнал

Ветка `feat/mail-codes-20261026` от `origin/main` (`c5e71939`), машина Анича (Windows).
Промпт — `PROMPT_MAIL_S1_20261026.md`.

## Фаза −1. Сверка с реальностью (27.10.2026)

| # | Ожидание | Факт |
|---|---|---|
| 1 | `git status` чисто | чисто (была ветка `feat/legal-b-20261009`) |
| 2 | `origin/main` = `c5e71939` или новее | ровно `c5e71939` (2026-10-15, Merge PR #10) — новых коммитов нет |
| 3 | последняя миграция `problems` — `0081_remove_userprofile_phone` | так |
| 4 | `problems/0082+` в других `origin/*` | нет ни в одной ветке |
| 5 | отправка почты только в `scripts/legal/pd_inventory.py` | так |
| 6 | Python 3.13.x, Django 5.2.x | 3.13.15, 5.2.17 |
| 7 | PostgreSQL для тестов (55432) | Docker Desktop был выключен — запущен, `postgres:17` и `redis:7` поднялись |
| 8 | базовая линия на PostgreSQL зелёная | **259 тестов, OK** (165 с) — `test_accounts`, `test_auth_hardening`, `test_profile_account_tab`, `test_profile_hardening`, `legal` |
| 9 | ADR: максимум 0158 в `origin/feat/vp-tour2-20261025` | так → **наш номер 0159** |
| 10 | логинов с «@» в локальной базе | **7** (из 16 пользователей; с непустой почтой — 9) |
| 11 | ветка и журнал | `feat/mail-codes-20261026` создана, upstream снят (чтобы `git push` не ушёл в main) |

Notion: карточки задачи, трёх решений от 26.10, задач Андрея, Анича (тексты) и Макара (ВП) прочитаны.
⚠️ SQL-запросы к базам Notion недоступны (нужен тариф Business) — «Задачи» и «Решения» читались
поиском и по ссылкам, а не полной выборкой по статусам.

## Фаза 1. Канал отправки

- `config/settings.py` — блок почты после `LEGAL_ENFORCEMENT_ENABLED` дословно по промпту;
  `config/settings_production.py` — `MAIL_ENABLED` заново из окружения, по умолчанию `0`.
- `problems/mail.py` — `send_templated` (одна повторная попытка при 4xx через 1,2 с, в журнал
  только маска адреса, класс и код ошибки), `mask_email`.
- `problems/checks.py` — `mail.E001`, подключена в `ProblemsConfig.ready`.
- `templates/email/code.txt|code.html|test.txt`; команда `send_test_email`.
- `deploy/env.example`, `deploy/env.dev.example` — блок «Почта».
- Тесты `problems/tests/test_mail_channel.py`: **15, все зелёные** (PostgreSQL). `manage.py check` → 0.
- ruff в `venv313` не было — поставлен из `requirements/dev.txt` (ruff 0.16.3, bandit 1.9.4, pip-audit 2.10.1).

## Фаза 2. Коды подтверждения — коммит `9c21a1aa`

- Миграция **`problems/0082_email_codes`**: модель `EmailCode` (`problems/models_mail.py`),
  `User.email_verified_at`, ограничение `user_verified_email_ci_unique` (Lower(email) при
  подтверждённой почте). Инварианты после `migrate` (локальная SQLite): подтверждённых почт **0**,
  кодов **0**. Откат `migrate problems 0081` → OK, повторный накат → OK; `makemigrations --check` →
  No changes detected.
- `problems/email_codes.py` — API по промпту + `resend_wait()` (сколько ждать до повторной
  отправки, для кнопки с таймером). Проверка кода сверяет со ВСЕМИ непогашенными кодами адреса,
  счётчик и срок — у последнего; поэтому «гасить старый код» несёт нагрузку, а не украшение.
- Админка `EmailCode` только на просмотр, без отпечатка. `purge_expired` — строка
  «problems.EmailCode (старше суток)»; `erase_user` — коды по связи (каскад) и по адресу.
- Тесты `problems/tests/test_email_codes.py`: **17, все зелёные** на PostgreSQL (13 сценариев
  промпта + тема письма сброса, `erase_user`, `verified_user_for`, уникальность подтверждённой почты).

Зубастость (дефект → покрасневший тест):

| Дефект | Покраснел |
|---|---|
| убрать проверку срока | `test_code_expires_after_ten_minutes` (сценарий 6) |
| убрать лимит попыток | `test_five_wrong_tries_lock_the_code` (5) |
| убрать 60 с | `test_resend_too_early_waits` (2) |
| хранить код открытым текстом | `test_send_one_letter_and_store_only_a_digest` (1) и ещё 4 |
| не гасить старый код при новом | `test_resend_after_a_minute_kills_the_old_code` (3) |

## Фаза 3. Регистрация в два шага, вход почтой — коммит `c97f41cb`

- `RegisterWithEmailForm` (почта, галочка рассылки `initial=False`, запрет «@» в логине; то же
  правило в `ProfileForm` — только для нового значения и только при включённой почте).
- Шаг 1 `/register/`: аккаунт не создаётся, в сессии `pending_registration` с ХЕШЕМ пароля.
  Шаг 2 `/register/confirm/` (`RegisterConfirmView`): повторная проверка логина и почты в
  транзакции, `User` с `email_verified_at`, профиль, согласие PD (+ MAIL по галочке), общий хвост
  `finish_signup` (счётчик `register` переехал сюда). `safe_next` вынесен в `problems/redirects.py`.
- Миграция **`problems/0083_consent_mail_kind`** (`ConsentRecord.Kind.MAIL`, источники
  `email`/`vp_wall`) — сделана здесь, а не в Фазе 4: согласие на рассылку выдаётся уже на шаге 2.
- ⚠️ **Отступление от промпта — бэкенды входа.** Промпт: наш бэкенд — единственный. Но путь бэкенда
  записан в каждой живой сессии (`django.contrib.auth.backends.ModelBackend`), и его исчезновение из
  настроек разлогинило бы всех на бою в момент выкатки. Сделано: `EmailOrUsernameBackend` первым
  (только путь «подтверждённая почта»; неверный пароль → `PermissionDenied`, цепочка обрывается,
  путь по логину не пробуется), штатный `ModelBackend` вторым. Поведение входа — как в промпте.
  `login()` после регистрации теперь с явным `backend=`.
- ⚠️ **Нельзя заводить новые корневые шаблоны (с doctype).** Два старых сторожа вместе это запрещают:
  `test_signup_source` требует Метрику в каждом корневом, `test_cookie_bar` — ровно 13 таких.
  Поэтому экраны почты наследуют `register.html` (в нём пустые `{% block %}` — ноль байт на выводе),
  письмо `code.html` — без doctype. Блок почты в `settings.py` переехал ниже: в «блоке LEGAL» тест
  `test_no_private_data_in_the_public_repository` запрещает адреса почты.
- При `MAIL_ENABLED=0` страницы `/login/`, `/register/`, `/register/?next=`, профиль (две вкладки),
  `/legal/` совпадают с эталоном до правок **байт в байт** (снимок через тестовый клиент, сравнение `diff`).
- Тесты `problems/tests/test_register_email.py`: **24, все зелёные** (PostgreSQL). Затронутые
  старые модули (`test_signup_source`, `legal.test_cookie_bar|test_pages|test_requisites`) — зелёные
  без правок.

Зубастость:

| Дефект | Покраснел |
|---|---|
| создавать пользователя на шаге 1 | `test_step1_creates_no_user_and_keeps_no_password` (1) и ещё 6 |
| `initial=True` у галочки | `test_mail_consent_box_is_never_prechecked` (2) |
| вход неподтверждённой почтой | `test_unverified_email_gets_the_same_refusal_as_wrong_password` (10) |
| убрать повторную проверку логина на шаге 2 | `test_username_taken_between_steps` (7) |
