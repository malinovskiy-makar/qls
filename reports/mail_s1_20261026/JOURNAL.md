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
