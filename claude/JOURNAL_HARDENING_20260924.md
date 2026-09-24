# Журнал сессии «Укрепление беты 24.09»

Ветка `fix/beta-hardening-20260924` от `origin/main` @ `f50266d`, папка
`C:\Users\shipu\qls-harden` (junction на `venv313` и `node_modules` из `qls`).
Промпт сессии — 17 пунктов владельца, фазы −1…9. Карточка сессии в Notion:
https://app.notion.com/3e5b11c92bc1813eb587efa119842068

## Фаза −1. Сверка с реальностью — СДЕЛАНО

- `origin/main` = `f50266d` ровно, новее нет → файлы фаз никем не задеты.
- `manage.py check` в новой папке — 0 ошибок (без `.env`: `REDIS_URL` не
  задан, кэш в памяти — для тестов это норма).
- 9 из 9 фактов подтверждены чтением:
  1. `profile.html`: `{{ form.username }}` стр. 532, форма данных открывается
     на стр. 546 → поле вне формы.
  2. `profile.js` `start()`: `measure()` (228) и `crop.base` (229) до
     `dialog.showModal()` (235).
  3. `game/views.py:1868` `json.dumps(ctx['auto_set'])` → `game.html:2407`
     `{{ auto_set_json|safe }}`.
  4. `client_ip()` берёт первый из `X-Forwarded-For`; в nginx четыре
     `$proxy_add_x_forwarded_for` (стр. 196, 214, 359, 394).
  5. `catalog/views.py:524` — перед `rerank.apply()` только `seo.is_crawler`.
  6. `_stol_help.html:100` `help-sol-tpl` и 104 `help-part-answers-tpl` —
     без проверки входа.
  7. `teacher/picker.py` `cart_items()` (стр. 490):
     `Problem.objects.filter(pk__in=catalog_ids)` без видимости; ключей в
     `views_generate.py:484` сколько угодно.
  8. `game/leaderboard.py:78` и `:138` — `achieved=Min('created_at')`.
  9. `vp/board.py` `ranked_attempts()` — без `variant__is_published`.
- Notion прочитан: «Задачи» (В работе / Надо), 8 последних «Решений»
  (в т.ч. три от 24.09: «Решить заново», решения только вошедшим, умный
  поиск), карточки «Подозрительный трафик», «SEO-фикс», «Лидерборд по
  личным рекордам».

## Фаза 1. Безопасность — СДЕЛАНО

Коммиты: `0966c549` (XSS), `31bc6a6c` (IP + админка), `be0276bf` (потолки ИИ),
загрузки, `ad7027f8` (бэкап media), `6ec472ea` + правка (SECURITY.md).

- **1.1 XSS в наборе игры.** `game/views.py:1868` → `dumps_for_script`.
  Обход всего проекта: `|safe` внутри `<script>` — 8 мест; 7 уже шли через
  `dumps_for_script`/`script_json` (`calendar.html` ×2, `game.html` CFG,
  `stats.html`, `_stol_center.html`, `_catalog_modal.html`,
  `_typing_placeholder.html`), дырявое одно — `AUTO_SET`. `mark_safe(json…)`
  в Python — ноль. `added_ids_json` (`collection_detail.html`) без `|safe`,
  числа — безопасно.
- **1.2 Настоящий IP.** nginx: 4 места `X-Forwarded-For $remote_addr`
  (+ пояснение в основном `location /`); `client_ip()`: `X-Real-IP` →
  `REMOTE_ADDR`. Других читателей XFF в коде нет (grep — ноль).
  ⚠️ В репо лежит устаревший снимок `deploy/nginx/conf.d/weconomics.conf`
  (231 строка против 409, без блока dev) — на сервер не монтируется, не
  правил; вопрос в «Чистка: вопросы владельцу».
- **1.3 `/admin/login/`** — обёртка `views_auth.admin_login` тем же счётчиком
  `login`, маршрут выше `admin.site.urls`.
- **1.4 Потолки ИИ.** Виды, до которых дотягивается сайт: `search_rerank`
  ($0,50), `catalog_chat` ($1) — были; добавлены `catalog_check`,
  `catalog_ocr`, `homework_plan` — по $1, `.env`:
  `CATALOG_CHECK_/CATALOG_OCR_/HOMEWORK_PLAN_DAILY_CAP_USD`. Команды данных
  (`topic_tagging`, `answer_blind`, eval) — без потолка намеренно.
- **1.5 Загрузки** — 30/сутки по `FileAsset` (kind=student_work), 429.
- **1.6 Бэкап media** — `backup.sh`: tar.gz тома `weconomics_media`
  (alpine, том :ro, `gzip -t`), отправка обоих файлов при `BACKUP_S3_*`,
  ротация по видам. `bash -n`/`sh -n` чистые, `shellcheck` нет. Раздел
  «Восстановление media» в `docs/SERVER.md`.
- **1.7 Карточки Notion** — отложены до фазы 9 одним списком (их больше
  пяти: правило CLAUDE.md «массовая запись — после показа владельцу»).
  Почта Let's Encrypt уже есть карточкой («Надо», 07.09) — дубль не заводить.

Зубастость (дефект возвращён → красный → восстановлен → зелёный):
- `test_set_title_cannot_close_the_script_tag` — красный до правки (TDD).
- `ClientIpTests` ×3 — красные на `ratelimit.py` из `f50266d`.
- `AdminLoginRateLimitTests` ×3 (кроме контрольного «хороший вход») —
  красные с закомментированным маршрутом.
- `CostCapsTests` ×2 — красные без ключа `homework_plan`.
- `test_empty_pending_does_not_escape_the_daily_limit` — красный без проверки.

Инвариант: лейблы фазы (`test_auth_hardening`, `test_ai_cost_caps`,
`test_attempt_files`, `test_rerank`, `test_chat_api`, `test_xss_payloads`,
`game.tests.test_sets`, `config.tests`) — **256 тестов, OK, код 0**
(шаг B: 3 serial пропущены — браузерные config без node в этом наборе).

⚠️ `--scope-from-git` при правке `config/settings.py`/`urls.py` сам
расширяется до ПОЛНОГО прогона — запущенный было прогон остановлен (правило
сессии: полный — только CI). Дальше — явные лейблы.

## Предположения

- `.env` в новую папку не копировал (секреты); для тестов не нужен.
- Потолок $1/сутки у трёх новых видов ИИ — значение по умолчанию из промпта.
- Обрыв DNS/Notion-карточки 1.7 — в фазе 9 одним списком.

## Следующий шаг

Фаза 2 — профиль.
