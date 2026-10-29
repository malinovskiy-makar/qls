# Журнал: вход через VK ID и Яндекс ID + обязательный онбординг

Ветка `feat/login-onboarding-20261029`, worktree
`C:\Users\shipu\qls\.claude\worktrees\login-onboarding`, база —
`origin/feat/vp-wall-20261029` (`ca37030d`). Задача Notion
`408b11c9-2bc1-8192-8f1e-c815380ab62e` (переведена в «В работе» в начале сессии).

Прочитаны все девять решений 29.10, перечисленных в промпте, и задачи Notion
«В работе» / «Надо».

---

## Фаза −1. Сверка с реальностью

### Основная папка `C:\Users\shipu\qls` (ничего не менялось)

- `git fetch` — пришла `origin/feat/vp-wall-20261029` (новая ветка) и
  обновление `feat/calc2-redesign`.
- `git status`: ветка `fix/stol-bottom-gap` (`5fe82970`), изменений в
  отслеживаемых файлах нет; неотслеживаемые: `.playwright-mcp/`, `.txt`,
  `Claude outputs/`, `New Text Document.txt`, четыре файла в `claude/`,
  `deploy/env.loadtest`, `kachat_vektora.ps1`, `session_c15_transcript_20260830.md`,
  `t1341_local.txt`.
- `origin/feat/vp-wall-20261029` → `ca37030dc7fe808e646936a5e68704b04068f15f`
  (2026-10-29 03:28, «Перед main, ф.4: журнал – Notion и остановка»).
- `git worktree list`: основная папка + `qls-chat`, `qls-exam`, `qls-finbiz`,
  `qls-materials`, `qls-models`, `qls-ref7`, `qls-v5`, `qls-vsosh`. **На ветке
  стены никто не работает.**
- Worktree создан командой `git worktree add .claude/worktrees/login-onboarding
  -b feat/login-onboarding-20261029 origin/feat/vp-wall-20261029` (встроенный
  инструмент не умеет базу от чужой удалённой ветки). `.claude/worktrees/` уже
  был в `.git/info/exclude` — в `git status` основной папки не виден.
  Апстрим снят (`git branch --unset-upstream`), чтобы случайный `git push` не
  ушёл в ветку стены.
- `manage.py check` в новой папке: 0 ошибок (`.env` основной папки не нужен и
  не копировался; без `REDIS_URL` — штатное предупреждение).

### Факты (пункт 4) — все «да», СТОП-ГЕЙТА нет

| Факт | Есть? | Где |
|---|---|---|
| `attach_verified_email`, `EmailTaken` | да | `problems/email_codes.py:241,245` |
| `EmailOrUsernameBackend` | да | `problems/auth_backends.py:36`, первый в `AUTHENTICATION_BACKENDS` |
| `UserProfile.grade/level/city/school/source_channel/olympiad_history/role`, `LEVEL_HINTS` | да | `problems/models_platform.py` |
| уровни `novice/basic/region/final` | да | `UserProfile.Level` |
| `VPWall.grade/tour2_status/source`, 8 кодов источника | да | `vp/models.py:239` |
| `legal.consent.grant` | да | `legal/consent.py:53` |
| `/account/email/?next=` | да | `problems/views_auth.py::account_email` |
| `StudentGroup.invite_code`, создание группы | да | `problems/models.py` (`make_invite_code`, `save()`), `teacher/views_groups.py::group_create` |

⚠️ **Расхождение, решённое владельцем в начале сессии:** класс в профиле — НЕ
5–11, а `le7 / 8 / 9 / 10 / 11 / none` («7 класс и младше» … «Уже не
школьник», с 18.09). Промпт просил сегмент `5 6 7 8 9 10 11` «как в профиле».
Владелец выбрал: **«Как в профиле»** — сегмент шага 2 показывает ровно коды
профиля (`≤7 · 8 · 9 · 10 · 11 · Не школьник`), схема класса не меняется.
`teach_grades` преподавателя — по промпту, 5–11.

### Запись в журнал (пункт 5)

- **`UserProfile.source_channel`** — 5 кодов: `telegram` «Telegram-канал»,
  `teacher` «Преподаватель», `friend` «Друг», `search` «Поиск в интернете»,
  `other` «Другое». С 8 кодами стены НЕ совпадают по составу и подписям, но
  **все 5 старых кодов есть среди 8** — переводить нечего. Таблица «старый →
  новый»: `telegram→telegram`, `teacher→teacher`, `friend→friend`,
  `search→search`, `other→other`; строк к переводу 0. Значит, записи в базу нет
  и СТОП-ГЕЙТ про перевод не нужен: меняются только варианты и подписи поля
  (AlterField в той же единственной миграции).
- **Сложность задачи:** `Problem.difficulty` — `PositiveSmallIntegerField`
  «Сложность (1–5)», `null=True`; рядом `difficulty_native` (метка источника,
  строка). Шкала 1–5 совпадает с промптом.
- **Вызов дня в игре:** есть — `/game/daily/` (`game:daily`).
- **Даты 2 тура в `vp/config.py`:** есть — `TOUR_DATES[2] = ('range',
  (13.11.2026, 22.11.2026))`. Строка «До тура N дней» строится от неё.
- **Порядок middleware:** `legal.middleware.ConsentGateMiddleware` — последний
  в списке, после `problems.signup_source.FirstTouchMiddleware`. Слой
  онбординга встаёт сразу после него.
- **HTTP-клиент:** боевой код ходит наружу через `urllib.request`
  (`vp/telegram.py`). `requests` стоит локально, но в `requirements/base.txt`
  его НЕТ (только `dev.txt`/`local.txt`) — на бою его может не быть. `httpx`
  локально нет. **Берём `urllib.request`**, как бот стены.

### Условие фазы 6 (пункт 6)

Сноска в `vp/templates/vp/_wall.html:61`: «* Instagram принадлежит компании Meta,
признанной экстремистской и запрещённой в России.» — НЕ та формулировка
ред. 2 («…которая признана экстремистской организацией и запрещена в России»).
**Условие: НЕТ → фаза 6 пропускается**, заводится карточка Notion.

### Что ещё увидено и повлияет на работу

- **Галочек на регистрации Анича две, а не три:** `consent` (текст
  `legal/_agree_label.html` уже содержит «Мне есть 18 лет, либо я регистрируюсь
  с согласия родителя…» + документы) и `mail_consent` (по желанию,
  `legal/_mail_label.html`). Промпт велит «взять из формы Анича, не
  переписывать» — на «Почти готово» ставятся эти же две, теми же шаблонами.
- Регистрация Анича входит бэкендом `ModelBackend`; вход через сервис по
  промпту — явным `EmailOrUsernameBackend` (оба в `AUTHENTICATION_BACKENDS`).
- Регистрация без `next` уводит на `/profile/?welcome=1`. Шлюз онбординга
  перехватит этот адрес как `next`; чтобы после анкеты показывался «План
  готов», «посадочные» адреса (`/`, `/profile/…`, `/student/`, `/teacher/`) не
  считаются сохранённым `next`.
- `teacher/views_groups.py::group_create` требует ученика у индивидуального
  занятия — у нового преподавателя учеников нет. Онбординг создаёт занятие
  той же моделью (`StudentGroup.objects.create`, код выдаёт `save()`), для
  индивидуального — без ученика: человек придёт по коду.
- Сегмента `.k-seg` и пилюль в `_kit.html` нет (есть `.k-tile`, `.k-btn`);
  стена ВП рисует свои `vp-wall-*`. Сегмент и пилюли делаются в
  `static/onboarding/onboarding.css` поверх токенов.
- Варианты «откуда узнали» стена держит у себя (`VPWall.SOURCE_CHOICES`);
  импорт подписей в стену — правка `vp/`, а она разрешена только в фазе 6.
  Пока 8 подписей дублируются в профиле и стене; свести — вместе с фазой 6.

---

## Фаза 1. Данные

- `problems/models_social.py` — `SocialAccount` ровно по промпту (`provider`,
  `uid`, `created_user`, `created_at`, `last_login_at`, уникальность
  `social_provider_uid_unique`); подключён одной строкой в конце
  `problems/models.py`.
- `UserProfile`: `onboarded_at`, `main_olympiad` (6 вариантов в порядке
  промпта, `MAIN_OLYMPIADS`), `teach_places` (`TEACH_PLACES`), `teach_grades`
  (`TEACH_GRADES` = 5…11) — списки JSON, как `olympiad_history`; `birth_date` с
  комментарием про `SOCIAL_STORE_BIRTHDATE` и ред. 3.
- `SourceChannel` приведён к 8 кодам стены, тот же порядок и подписи. Старые 5
  кодов входят в 8 — **данные не переводятся**, строк к переводу 0 (на копии
  рабочей базы все 26 профилей с пустым источником). Тест сверяет список с
  `VPWall.SOURCE_CHOICES` — расхождение покраснеет. Импорт подписей в стену —
  правка `vp/`, ждёт фазы 6.
- **Миграция `problems/0084_login_onboarding`** (одна; лист цепочки на ветке
  стены — 0083; на `main` лист — 0081, у стены 0082–0083 свои; при переносе на
  свежий main сшивка не нужна, если в main не появится своя 0082+ у `problems`).
- `problems/tests/profile_markers.py`: `birth_date`, `main_olympiad`,
  `teach_places`, `teach_grades` + их имена и подписи в `FORBIDDEN`.
- Сноска про Instagram — общий `templates/_instagram_note.html`; поставлена в
  профиль под «Откуда вы узнали» (там теперь виден «Instagram*»).

**Проверки (свидетельства):**
- `makemigrations problems -n login_onboarding` → 0084 (6 операций + модель).
- `migrate` с нуля на пустой SQLite worktree — код 0; `migrate problems 0083`
  (откат) — OK; снова вперёд — OK; `makemigrations --check --dry-run` → `No
  changes detected`.
- Путь обновления: копия рабочей `db.sqlite3` (1,3 ГБ) → `migrate` код 0,
  применились 0079–0084 `problems` и 0004–0005 `vp`. Копия удалена.
- Тесты: `problems.tests.test_social_models` (4), `legal.tests.test_erase_user`,
  `catalog.tests.test_chat_api`, `catalog.tests.test_attempts` (сторожа P0) — 38
  OK; `test_profile_account_tab`, `test_accounts`, `test_beta_smoke` — 80 OK.

**Чужие файлы, правленные точечно:** `problems/models.py` (+1 импорт),
`problems/models_platform.py` (поля и варианты), `problems/tests/profile_markers.py`,
`problems/templates/platform/profile.html` (+1 строка сноски).
