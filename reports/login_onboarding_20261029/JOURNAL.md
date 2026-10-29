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

---

## Фаза 2. Вход через VK ID и Яндекс ID

**Файлы (новые):** `problems/social/{__init__,providers,views,urls}.py`,
`problems/templatetags/social_tags.py`, `templates/social/{_buttons,finish,error}.html`,
`static/social/{vk,yandex}.svg` (заглушки с комментарием «заменить на значок из
официального набора»), `problems/tests/test_social_login.py`.
Заготовки онбординга для URL (`problems/views_onboarding.py`,
`problems/urls_onboarding.py`) — наполняются в фазе 3.

**Чужие файлы, точечно:** `config/settings.py` (блок флагов и ключей после
Telegram), `config/urls.py` (+2 строки: `auth/`, `welcome/`),
`templates/registration/login.html` и `register.html` — **ровно по одной строке**
`{% include 'social/_buttons.html' %}` над формой (`git diff --stat`: 1 insertion
в каждом).

**Как устроено:**
- Сервисы — `providers.py`, единый словарь `{uid, first_name, last_name, email,
  email_verified, birth_date, avatar_url}`; токен живёт только внутри
  `fetch_profile`. HTTP — `urllib.request`, таймаут 10 с, адреса — константы
  `https://`.
- PKCE S256 у обоих; `state` 32 байта, `code_verifier` 86 знаков, поток в сессии
  10 минут и одноразовый (забирается при возврате).
- Порядок возврата — по промпту (известный uid → вход; вошёл → привязка, чужой
  uid → «Этот VK ID уже привязан к другому аккаунту»; автосклейка только
  «подтверждена там И подтверждена у нас»; иначе `social_pending` 30 минут без
  токенов → `/auth/finish/`).
- «Почти готово»: инициалы, строки `Имя · Почта (маска) · Дата рождения
  (только при флаге) · Фото`, **две** галочки Анича теми же шаблонами
  (`legal/_agree_label.html` уже несёт «18+ либо с согласия родителя»,
  `legal/_mail_label.html` — только при `MAIL_ENABLED`), «Продолжить», «Это не я».
  Создание — одной транзакцией; логин `econ_` + 6 знаков `[a-z0-9]`, пароль
  непригодный; почта подтверждена и свободна → `attach_verified_email`;
  `consent.grant` с источником `register`; `record_signup`; вход явным
  `EmailOrUsernameBackend`.
- После создания: без подтверждённой почты и при `MAIL_ENABLED` →
  `/account/email/?next=<онбординг>`; иначе онбординг с `next` (при выключенном
  онбординге — `next` или прежний `/profile/?welcome=1`).
- Аватар: только `https://` и хост из белого списка (точное имя или поддомен),
  без переадресаций, 5 с, ≤ 3 МБ, дальше существующий `AvatarForm` (квадрат JPEG
  256). Любая ошибка — молча.
- Частота: возвраты — scope `social` (промахи по адресу), создание — scope
  `register`, как у регистрации.

**Расхождения с ожидаемым (не стоп):**
- Официальная документация VK ID (`id.vk.com/about/business/go/docs`) не
  открылась загрузчику; адреса и поля VK взяты из промпта и сверены с открытыми
  библиотеками (PKCE обязателен, `device_id` приходит в адресе возврата и нужен
  при обмене, `user_info` — POST `client_id` + `access_token`). Живой вход
  проверяется после выдачи ключей.
- Яндекс сверен с yandex.ru/dev/id/doc: всё как в промпте; при PKCE
  `client_secret` не обязателен (шлём, если задан). Неполная дата («0000-12-23»)
  отбрасывается. Права Яндекса: `login:info login:email login:avatar`, плюс
  `login:birthday` — **только при `SOCIAL_STORE_BIRTHDATE=1`** (без флага дату
  не просим и не кладём даже в сессию).
- Аватар на «Почти готово» — инициалы, не картинка сервиса: политика `img-src`
  (`config/security_headers.py`) пускает только свои адреса, а картинка встаёт в
  профиль сразу после регистрации.
- Отказы (`state`, ошибка сервиса, «Отмена» у сервиса, чужой uid) — страница
  `social/error.html` со статусом 400 (429 при запрете частоты), без 500.

**Границы доступа (ресурс × кто × действие):**

| Ресурс | Аноним | Вошедший | Закрыто тестом |
|---|---|---|---|
| `/auth/<p>/start/` при выключенном флаге или без ключей | 404 | 404 | да (`FlagTests`) |
| `/auth/<p>/callback/` с чужим/устаревшим `state` | 400, аккаунтов 0 | 400 | да |
| callback, uid привязан к A | вход в A | если это не A — отказ | да (оба) |
| callback, почта подтверждена у A | вход в A | — | да |
| callback, почта у A НЕ подтверждена | экран, A не тронут | — | да |
| `/auth/finish/` без `social_pending` | → `/login/` | → профиль | кодом |
| `/auth/finish/` POST без согласия | 200 с ошибкой, аккаунтов 0 | — | да |
| `next` чужого хоста | отброшен | отброшен | да |

Владелец объекта нигде не берётся из запроса: привязка к вошедшему — только
`request.user`, к чужому — только по подтверждённой почте.

**Тесты:** `test_social_login` (33) + `test_social_models` (4) — 37 OK. Девять
пунктов промпта: 1 `test_wrong_state…`; 2 `test_pkce…`; 3 `test_known_uid…`; 4 —
`AutoMergeTests` (4 строки таблицы); 5 `test_without_consent…`,
`test_with_consent…`; 6 `BirthDateTests`; 7 `NoTokensAnywhereTests`; 8
`AvatarTests`; 9 `FlagTests`.
Соседи: `test_register_email`, `test_auth_hardening`, `test_accounts`,
`test_profile_account_tab`, `test_signup_source`, `test_production_settings`,
`legal` — 346 OK, код 0. `ruff` чисто, `bandit -ll` — 0, `check_em_dash` — 0.

---

## Фаза 3. Онбординг ученика (+ фаза 4 в том же коммите)

Код учеников и преподавателей живёт в одних файлах (`problems/views_onboarding.py`,
`templates/onboarding/*`), поэтому фазы 3 и 4 закоммичены вместе; записи раздельные.

**Файлы (новые):** `problems/views_onboarding.py`, `problems/urls_onboarding.py`,
`templates/onboarding/{base,step,group,plan,_choices,_bar,_role_icon}.html`,
`static/onboarding/{onboarding.css,onboarding.js}`, `problems/tests/test_onboarding.py`.
Чужих файлов в этой фазе не правил (адрес `welcome/` подключён в фазе 2).

**Как устроено:**
- `/welcome/` сам выбирает шаг: первый, не подтверждённый в этом проходе
  (`onboarding_done` в сессии) или не заполненный в профиле. Новый человек
  начинает с «Кто вы?», старый видит свои ответы выбранными и жмёт «Дальше».
- Пропуск запрещён на сервере: шаг открывается, только когда в ПРОФИЛЕ есть
  ответы всех шагов до него (`step_filled`); иначе — редирект на первый
  незаполненный. POST тоже проверяется (прыжок формой на «Город и школа» без
  класса → редирект на «Класс и уровень», `onboarded_at` пуст).
- Ответ пишется в профиль после каждого шага; `onboarded_at` — после «Города и
  школы»; при правке через «Изменить» дата первого прохода не переписывается.
- Каркас: знак, полоска из N делений без подписей, тихое «Выйти» (POST);
  заголовок и элементы; липкая полоса «Назад» / «Дальше» (графитовая
  `k-btn--main`). «Дальше» выключает скрипт, пока шаг не заполнен; без скрипта —
  ошибка сервера у поля.
- Выбор — `.k-tile` из `_kit.html` и свои сегмент/пилюли (`onboarding.css`),
  всегда `<label>` с настоящим radio/checkbox и `aria-pressed`.
- Класс — коды профиля (решение владельца в начале сессии): `≤7 · 8 · 9 · 10 ·
  11 · Не школьник`. Уровни — подписи `Level` и `LEVEL_HINTS` профиля.
- «Олимпиада»: 6 плиток, подпись «Откуда вы узнали о Weconomics?», 8 пилюль в
  порядке стены, сноска дословно (общий `_instagram_note.html`).
- `next`: сохраняется из `/welcome/?next=` (только свой адрес); «посадочные»
  адреса (`/`, `/profile/…`, `/student/`, `/teacher/`, `/welcome/…`) не считаются —
  регистрация без `next` ведёт на `/profile/?welcome=1`, и тогда после анкеты
  показывается «План готов». С настоящим `next` — сразу туда, план потом по
  `/welcome/plan/`.
- Аккаунт из VK/Яндекса без подтверждённой почты при `MAIL_ENABLED` сначала
  уходит на `/account/email/?next=/welcome/`; старые без почты — не блокируются.

**«План готов»:** чипы (класс, уровень, олимпиада, город) + «Изменить» → шаг 2;
«Три задачи» — `catalog.filters.base_queryset('catalog')` (тот же шлюз, что у
каталога и карты сайта), сложность по уровню (1–2 / 2–3 / 3–4 / 4–5), с решением
в приоритете, зерно `sha256(user_id:дата)`; строка — название (или «Задача: тема»,
как у каталога), точка темы `--map-g-*`, звёзды. «Тренажёр 2 тура «Высшей пробы»» —
при `hse` или классе 9–11: вариант своего класса из `vp.visibility.visible_variants()`
(нет — `/vp/variants/`), строка «До тура N дней» от `vp/config.TOUR_DATES`. Иначе —
«Олимпиада» со ссылкой на `/olympiads/`. «Вызов дня» → `/game/daily/`, «Сыграть».
«Начать» → первая задача. Заголовки карточек 1–2 — сами ссылки: свои надписи
вроде «Открыть» не добавлял.

**Тесты (`test_onboarding`, 34 OK)** — семь пунктов промпта:
1 `test_post_without_answer…`; 2 `test_full_pass_writes_the_profile`;
3 `test_old_profile_answers_are_preselected`; 4 `test_jump_over_a_step…`;
5 `TextGuardTests` (нет «около», «секунд», «Дальше —», «Что мы настроим»; `<p>` в
`<main>` — 0, кроме сноски; сноска дословно; пилюли в порядке стены);
6 `PlanTests` (уровень → сложность, один набор на день, решение в приоритете,
скрытые не попадают); 7 `test_next_survives_onboarding`.

**Телефон 390 px** — проверяется в браузере после фазы 5 (одним проходом по всем
экранам).

## Фаза 4. Онбординг преподавателя

- «Кто вы?» → «Преподаватель» → «Где и кого вы учите?» (три плитки `teach_places`,
  подпись «Классы», пилюли 5–11, по одному обязательно) → «Первая группа».
- `onboarded_at` ставится после шага 2; `role` → `tutor`, `User.role` → `teacher`
  синхронно (`UserProfile.save()`).
- «Первая группа»: поле «Название», сегмент «Группа / Индивидуально», «Создать
  группу». Создание — той же моделью (`StudentGroup.objects.create`, код выдаёт её
  `save()`). ⚠️ Отличие от `teacher/views_groups.group_create`: индивидуальное
  занятие создаётся без ученика — у нового преподавателя учеников нет, человек
  придёт по коду. После создания — карточка: название, код крупно,
  «Скопировать», «В кабинет». «Позже» → кабинет без группы.
- Защита: у кого уже есть свои группы, тот не может на шаге 1 стать учеником
  (иначе одним нажатием терял бы кабинет с работами учеников).

**Тесты (в том же файле):** полный проход (+1 группа, код `XXXX-XXXX`), «Позже»
(групп 0, `onboarded_at` есть), без мест/без классов → ошибка, индивидуальное без
ученика, группы держат роль, шаги ученика закрыты преподавателю.

**После коммита фазы 2 (автопроверка безопасности):** отмечена автосклейка по
почте. Сама склейка — решение владельца 29.10 (вариант «спросить пароль»
отвергнут), её не менял. Добавил одно ужесточение: **сотрудников и
суперпользователей не склеиваем никогда** (`is_staff`/`is_superuser` → экран
«Почти готово», тест `test_staff_is_never_merged`).

---

## Фаза 5. Шлюз онбординга

- `problems/middleware_onboarding.py` (`OnboardingGateMiddleware`) — в
  `config/settings.py` **сразу после** `legal.middleware.ConsentGateMiddleware`
  (тест сверяет позицию). Условия — все пять из промпта; белый список: `/welcome/`,
  `/auth/`, `/logout/`, `/legal/` (там и экран согласия), `/account/email/`,
  `/password/`, `/static/`, `/media/`, `/admin/` + служебные адреса слоя согласия
  (`/health*`, `/api/track/`, `/csp-report/`, `robots.txt`, `sitemap.xml`).
  Признак «запрос скрипта» — общий `legal.middleware.is_script_request`.
- Действие: `302 → /welcome/?next=<путь с запросом>`; `next` проверяет сам
  `/welcome/` (`is_safe`).
- Запроса к базе на каждой странице нет: после прохода признак `onboarded` лежит
  в сессии.
- Почта аккаунтов из сервисов — между согласием и анкетой: её требует сам
  `/welcome/` (`needs_service_email`), шлюз ведёт туда.
- `ONBOARDING_ENABLED`: из окружения, в тестах по умолчанию `0`, иначе `1`; в
  `settings_production.py` не переопределяется.

**Тесты (`test_onboarding_gate`, 13 OK)** — таблица промпта: без онбординга
`GET /catalog/` → `302 /welcome/?next=/catalog/`; POST формы (`/profile/`) — не
перехвачен; `/legal/privacy/` — 200; сотрудник, прошедший, гость, флаг выключен —
не перехвачены; не принял документы → сначала `/legal/accept/`, после согласия —
`/welcome/`. Плюс: запрос скрипта, сам `/welcome/`, `next` с запросом, признак в
сессии, позиция слоя.

**Проверка в браузере (сервер worktree на 8010, флаги ONBOARDING/SOCIAL с
подставными ключами, `MAIL_ENABLED=0`, демо-данные `seed_demo` в базе worktree):**
- `/register/` — над формой «VK ID» · «Яндекс ID» и «или», остальное как было.
- Регистрация → сразу `/welcome/role/` → 4 шага → «План готов»: чипы «10 класс ·
  Начинающий · Высшая проба · Казань», карточки «Три задачи» (3 строки),
  «Тренажёр 2 тура «Высшей пробы»» со строкой «До тура 15 дней», «Вызов дня»;
  «Начать» → `/catalog/problem/1/`.
- **Телефон 390 px:** на каждом шаге и на плане `scrollWidth == clientWidth ==
  390`; плитки 358 px (один столбец), сегмент класса 6×60 px, пилюли в пределах
  экрана, нижняя полоса прилипает (низ = 844 при закрытой плашке cookie; при
  открытой — стоит над ней). «Дальше» неактивна до выбора, на «Городе и школе» —
  до заполнения обоих полей.
- Преподаватель: 3 деления, «Где и кого вы учите?» → «Первая группа» → код
  `XXXX-XXXX` (325 px шириной, влезает), «Скопировать» и «В кабинет».
- Тёмная тема: фон `rgb(29,26,22)`, текст `rgb(242,236,217)`, карточки
  `rgb(44,41,37)`, «Начать» графитовая.
- Снимки экрана панель браузера отдавала с таймаутом — проверка числами в
  странице. Для запуска на время проверки в `C:\Users\shipu\qls\.claude\launch.json`
  (основная папка) добавлялась запись `login-onboarding`; после проверки файл
  возвращён `git checkout` — в основной папке изменений нет.

---

## Фаза 6. Стена ВП не переспрашивает — ПРОПУЩЕНА

Условие фазы −1, пункт 6 — «нет» (в `_wall.html` сноска ещё не ред. 2). `vp/` не
трогал. Карточка Notion «Стена ВП: не переспрашивать класс и «откуда узнали» после
онбординга — сделать после слияния ред. 2» (`408b11c9-2bc1-811f-a528-d299306f9f2c`),
в неё же — свести подписи источников в одно место.

---

## Фаза 7. Зубастость, проверки, документы, Notion

**Зубастость** (всё закоммичено; по одному дефекту → тест → `git checkout -- <файл>`
→ снова тест; скрипт в черновиках сессии):

| Дефект | Файл | Тест | С дефектом | После отката |
|---|---|---|---|---|
| убрать проверку `state` | `problems/social/views.py` | `StateAndPkceTests.test_wrong_state_is_400_and_creates_nothing` | красный | OK |
| склеивать по неподтверждённой почте | `problems/social/views.py` | `AutoMergeTests.test_unverified_email_here_is_not_merged` | красный | OK |
| `birth_date` без флага | `problems/social/providers.py` | `BirthDateTests.test_flag_off_no_birth_date…` | красный | OK |
| токен в словарь → в сессию | `problems/social/providers.py` | `NoTokensAnywhereTests.test_token_never_reaches_session_or_database` | красный | OK |
| без проверки домена аватара | `problems/social/providers.py` | `AvatarTests` | красный | OK |
| шлюз перехватывает POST | `problems/middleware_onboarding.py` | `GateTableTests.test_post_is_not_intercepted` | красный | OK |
| слой онбординга раньше слоя согласия | `config/settings.py` | `GateTableTests.test_documents_screen_comes_first` | красный | OK |
| абзац-пояснение на шаге 2 | `templates/onboarding/step.html` | `TextGuardTests.test_no_paragraphs_besides_the_instagram_note` | красный | OK |
| прыжок через шаг | `problems/views_onboarding.py` | `StudentFlowTests.test_jump_over_a_step…` | красный | OK |

Фазы 6 не было — строки про стену нет. После всех откатов `git status` чистый.

**Нули:** `manage.py check` — 0; `makemigrations --check --dry-run` — No changes
detected; `scripts/check_em_dash.py` — 0 (код 0); `ruff check` по 19 изменённым
`.py` — чисто; `bandit -ll -r` по новым модулям — No issues (код 0).

**Документы:** `docs/SECURITY-MATRIX.md` — 4 строки (`/auth/<p>/start/`,
`/auth/<p>/callback/`, `/auth/finish/`, `/welcome/…`); `docs/SECURITY.md` — раздел
«Вход через VK ID и Яндекс ID (29.10.2026)»; `CLAUDE.md` — абзац с флагами,
адресами возврата и «allauth не ставить».

**Notion (новые карточки «Задачи», статус «Надо», дубли искал поиском — нет):**
1. «Стена ВП: не переспрашивать…» — Техническое (фаза 6).
2. «Зарегистрировать приложения VK ID и Яндекс ID и выдать ключи» — Бизнес и
   запуск, Андрей; адреса возврата, права, «телефон не запрашивать».
3. «Заменить заглушки значков на официальные кнопки VK ID и Яндекс ID» — Дизайн.
4. «Документы ред. 3: вход через VK ID и Яндекс ID, дата рождения — до включения
   на бою» — Бизнес и запуск, Анич; ссылка на `405b11c9-2bc1-813b-910a-daa1430286f3`.
5. «Профиль: показать привязанные VK ID / Яндекс ID, отвязать и задать пароль
   аккаунту из сервиса» — Кабинеты (замечено, не делалось; открытый вопрос карточки
   задачи про пароль).

**Порядок включения на бою:**
1. Стена → main.
2. Эта ветка переносится на свежий main без `rebase` общих веток: новая ветка от
   main + `merge` этой (или как скажет владелец). Перед этим `showmigrations
   problems`: если в main у `problems` появится своя 0084+, нужна миграция-сшивка.
3. Ред. 3 документов в main (Анич).
4. На сервере ключи сервисов, затем `SOCIAL_LOGIN_ENABLED=1`.
5. `ONBOARDING_ENABLED` — по умолчанию включён; выкатка **не во время тура ВП
   13–22.11** (до заморозки 11.11 или после 22.11). Если ветка уезжает на бой в
   окно тура — `ONBOARDING_ENABLED=0` в окружении до 23.11.
6. `SOCIAL_STORE_BIRTHDATE=1` — только после ред. 3.

**Прогоны фазы 7** (без `--parallel`, SQLite):
- Набор из промпта + модули по `grep` (шаблоны входа/регистрации, `source_channel`,
  `MIDDLEWARE`, `profile.html`, маркеры ИИ, doctype-сторожа) — **1 366 тестов**:
  первый проход — 2 провала, оба на МОЮ новую корневую страницу
  `templates/onboarding/base.html`:
  `legal.tests.test_pages…test_every_root_template_links_to_legal` (нет ссылки на
  документы) и `legal.tests.test_cookie_bar…test_every_counter_root_has_the_bar_and_the_gate`
  (корней со счётчиком 14 при ожидаемых 13). Починка: в каркас онбординга
  добавлен `_legal_footer.html`, счётчик и плашка cookie — с `metrika_private=True`,
  как в кабинетах (там вводят город и школу); онбординг вписан в инвентаризацию
  корней обоих тестов (как прежде экран согласия). После: эти модули + онбординг +
  `test_signup_source` — 118 OK.
- `vp` — **607 OK** (`skipped=1`, браузерный), код 0 — **без класса
  `vp.tests.test_wall_poll.PollSignalTests`**: его тест шлёт процессу SIGTERM
  (`os.kill(os.getpid(), signal.SIGTERM)`), а на Windows это убивает весь прогон
  (код 15, итог не печатается). Тест из ветки стены (`3ea1f17a`), к этой работе
  отношения не имеет; на Linux (CI) он, по смыслу, проходит. Не правил — сообщаю в
  отчёте.

**Чужие файлы фазы 7:** `legal/tests/test_cookie_bar.py`, `legal/tests/test_pages.py`
(+1 корень в инвентаризации), `docs/SECURITY-MATRIX.md`, `docs/SECURITY.md`,
`CLAUDE.md`.

**Не делалось намеренно:** блок «Текущий фокус» в CLAUDE.md и запись в
`CLAUDE_ARCHIVE.md` — в этой ветке они дали бы конфликт при слиянии со стеной и
main; история сессии — этот журнал.

---
---

# РАУНД 2 (ночь 29→30.10.2026): переделка по живой проверке владельца

Промпт «Вход и онбординг, раунд 2». Эталон — макет `docs/design/onboarding_r2/`
(README + 19 снимков просмотрены до правки шаблонов). Notion прочитан: «Решения» от
26.10 и новее (в т. ч. три решения раунда 2 от 29.10: макет-эталон, «почта + пароль»,
цели/отдельный «Откуда»/автопереход) и «Задачи» «В работе»/«Надо».

## Р2 · Фаза −1. Сверка

- **Макет на месте:** `README.md` + 19 файлов `shots/*.png` + `*.dc.html`, `w.css`,
  `w2.css`, `logos/` (5 файлов), `ds/` (bundle.css, шрифты). Закоммичен первым:
  `da442daa docs: макет входа и онбординга, раунд 2`. До него последний коммит —
  `9268cd73` (ф.7 прошлой сессии), `git status` был чистым, кроме `docs/design/`.
- **Слияние стены:** `git fetch` → `origin/feat/vp-wall-20261029` = `866c9ff1`
  (12 новых коммитов: документы ред. 2, ai_version, сноски стены, бот). `git merge
  --no-ff` — **без конфликтов**.
- **Сноска ред. 2 в `vp/templates/vp/_wall.html:61` ЕСТЬ:** «…которая признана
  экстремистской организацией и запрещена в России». → **фаза 7 выполняется.**
- **Миграции `problems`:** последняя — `0084_login_onboarding`; после слияния
  `makemigrations --check --dry-run` → `No changes detected`, второго листа нет.
- **Тесты прошлой сессии:** `test_social_login` + `test_onboarding` +
  `test_onboarding_gate` — **81 OK**.

### Как устроено сейчас (до правки)

- **`RegisterView`** (`problems/views_auth.py:178`), шаблон
  `templates/registration/register.html`:
  - `MAIL_ENABLED=0` — форма `RegisterForm` (`UserCreationForm`): `username` (+подсказка
    «Им вы входите…»), `password1`, `password2` («Пароль ещё раз»), `role` (радио
    «Я ученик / Я преподаватель», по умолчанию ученик), `consent`. Аккаунт, профиль с
    ролью и согласие ПДн — одной транзакцией, затем `finish_signup` (вход
    `ModelBackend`, `record_signup`, переход на `next` или `/profile/?welcome=1`).
  - `MAIL_ENABLED=1` — `RegisterWithEmailForm`: те же поля + `email` (+подсказка) +
    `mail_consent`. Шаг 1 кладёт анкету в сессию (`pending_registration`, только хеш
    пароля), шлёт код; **код проверяется в `RegisterConfirmView`**
    (`/register/confirm/`, шаблон `register_confirm.html`), он же внутри транзакции
    перепроверяет занятость логина и почты и создаёт аккаунт.
- **Тесты Анича, которые их держат:** `problems.tests.test_register_email` (24 теста:
  шаг 1 без пользователя и пароля, галочка рассылки не отмечена, неверный/верный код,
  `next`, занятая почта, логин заняли между шагами, 30 минут, повтор кода, «изменить
  почту», `@` в логине, вход почтой, старый одношаговый режим);
  `legal.tests.test_register` (5: одна запись ПДн, без галочки ничего, транзакция,
  текст галочки, шлюз); соседи — `test_accounts`, `test_signup_source`,
  `test_beta_smoke`, `test_password_reset_code`, `test_email_codes`.
- **Поле класса в профиле:** `UserProfile.grade`, `Grade`: `le7` «7 класс и младше»,
  `8`…`11` «N класс», `none` «Уже не школьник». Уровни `Level`: `novice` Новичок,
  `basic` Начинающий, `region` Продолжающий, `final` Профи + `LEVEL_HINTS`.
- **Логотип в шапке сайта:** `templates/_nav.html` — инлайновый SVG круглого знака W
  27×27 (заливка круга `#fffce6` под графитовую шапку); партиала у него нет.
  Полное начертание «W + economics» — партиал `templates/_wordmark.html` (буквы
  `currentColor`), его же рисует макет и в шапке сайта, и в шапке онбординга
  (`height: 44–50px; width: auto`). В раунде 1 шапка онбординга брала
  `_wordmark.html` с `width: 132px; height: auto`.
- **Роль по умолчанию:** `UserProfile.role` — у регистрации всегда задаётся
  (`student`/`tutor`), у входа через сервисы — `student`.

### Браузер

Есть: встроенный браузер приложения и Playwright. Снимки — в
`reports/login_onboarding_20261029/shots_r2/`.

## Р2 · Фаза 1. VK ID и Яндекс ID

### Диагностика (что открылось)

- **Яндекс** — https://yandex.ru/dev/id/doc/ru/codes/code-url открылась. Адрес
  `https://oauth.yandex.ru/authorize`, параметры `response_type=code`, `client_id`,
  `redirect_uri` (точное совпадение с настройкой), `scope`, `state`,
  `code_challenge`/`code_challenge_method=S256`; обмен `POST oauth.yandex.ru/token`:
  `grant_type`, `code`, `client_id`, `code_verifier`, `client_secret` при PKCE не
  обязателен. **Наш код совпадает пункт в пункт.**
- **«400 неизвестное приложение» = подставной `client_id`: ДА.** Документация: на
  ненайденное/заблокированное приложение — `invalid_client`. Живой запрос
  `oauth.yandex.ru/authorize?client_id=demo` без входа в Яндекс — 302 на паспорт
  (`retpath` с тем же `client_id=demo`), после входа владелец видел страницу 400.
- **VK ID** — `id.vk.com/about/business/go/docs/...` загрузчику НЕ открылась;
  документация переехала на **id.vk.ru** и открылась:
  `.../vk-id/connection/api-integration/api-description` и
  `.../vk-id/connection/create-application`. Сверено: authorize — `response_type,
  client_id, redirect_uri, state, code_challenge, code_challenge_method=S256`
  (+ `scope`); возврат — `code, state, device_id`; обмен `POST /oauth2/auth` —
  ровно семь обязательных `grant_type, code_verifier, redirect_uri, code, client_id,
  device_id, state`; `user_info` — `POST client_id + access_token`; `state` —
  `[a-zA-Z0-9_-]`, ≥ 32; `code_verifier` — те же знаки, 43–128. **Наш код
  совпадает** (`token_urlsafe(32)` → 43 знака, `token_urlsafe(64)` → 86).
- **«Ошибка загрузки» VK = подставной `client_id` (+ VPN): ДА.** Живой запрос
  `id.vk.com/authorize?client_id=demo` → в странице `"client_id is missing"`
  (`invalid_request`): у VK номер приложения только цифрами. С выдуманным числом —
  `"app is deleted"` (`invalid_client`).
- **VK ID и `http://localhost`:** документация «Создание приложения»: «Доверенный
  redirect URL пропишите с http и без порта — http://localhost»; https — только на
  443; «Другие порты временно не поддерживаются»; `127.0.0.1` не упомянут. ⇒ на
  `127.0.0.1:8010` VK не проверить, только `runserver localhost:80` (записано в
  `docs/SOCIAL_KEYS.md`). Яндекс принимает любой адрес из списка приложения.
- `id.vk.com` и `id.vk.ru` отвечают одинаково (проверено запросом к обоим) —
  перешли на `id.vk.ru`, как в актуальной документации.

### Что исправлено

- `problems/social/providers.py`: VK — `id.vk.ru` (authorize, token, user_info);
  `Provider.configured` — ключ не пустой, не заглушка (`demo`, `test`, …) и нужного
  вида (VK `[0-9]{4,12}`, Яндекс `[0-9a-fA-F]{32}`); `enabled` = флаг + `configured`;
  порядок кнопок — Яндекс, затем VK (как в макете).
- `problems/social/views.py`: флаг включён, а ключ не настоящий → на `/start/` и
  `/callback/` наша страница «Вход через VK ID пока не настроен» (503), к сервису не
  уводим. Флаг выключен или сервис неизвестен — 404, как было.
- Официальные значки: `static/social/yandex.svg` — знак (круг + буква) из официальной
  кнопки `personal-button-null.svg` документации Яндекс ID без изменений (вырезан
  `viewBox`); `static/social/vk.svg` — белый знак 28×28 из официального образца кнопки
  VK ID. Отрисовка официальной кнопки Яндекса проверена в Chrome: «Войти с Яндекс ID».
  Источники и правила — `static/social/README.md`.
- `templates/social/_buttons.html`: кнопки во всю ширину, одна под другой, 44 px;
  Яндекс — чёрная, VK — `#0077FF`; тексты «Войти с Яндекс ID» / «Войти с VK ID».
- `docs/SOCIAL_KEYS.md` — пошагово: Яндекс, VK ID, PowerShell, `.env`, что должно
  получиться, почему не работало.

**Тесты:** `test_social_login` — 39 OK (новые: `KeyCheckTests` ×3 — заглушки и
кривые ключи прячут кнопку, прямой заход — наша страница 503, настоящие ключи —
обе кнопки в порядке макета; `OfficialParamsTests` ×2 — знаки `state`/`verifier` и
семь полей обмена VK). Старые тесты переведены на ключи настоящего вида.

**Живая проверка (п. 5):** настоящих ключей в окружении и `.env` нет — пропущена.

## Р2 · Фаза 2. Регистрация и вход: почта + пароль

**Регистрация** (`RegisterForm`, `RegisterWithEmailForm`, `RegisterView`,
`RegisterConfirmView`, `templates/registration/register.html`):
- `MAIL_ENABLED=1`: поля «Почта» и «Пароль» (одно поле, глаз «показать»), галочки
  Анича (`legal/_agree_label.html`, `legal/_mail_label.html`), «Создать аккаунт» → код.
  **Логин создаёт сайт** при создании аккаунта: `problems/usernames.py::free_username`
  (`econ_` + 6 `[a-z0-9]`, свободный без учёта регистра) — та же функция теперь у входа
  через сервисы (вынесена из `problems/social/views.py`).
- `MAIL_ENABLED=0`: «Логин» и «Пароль», без подсказки.
- Убрано в обоих режимах: выбор роли, «Пароль ещё раз», подзаголовок, подсказка под
  логином и почтой. Пароль по-прежнему проверяют и хешируют формы Django: поле
  `password2` удалено, валидаторы (длина 10, распространённые, похожесть на логин и
  почту) применены к `password1` (`_post_clean`). Роль профиля до онбординга — `student`.
- Сверху официальные кнопки, разделитель «или», внизу «Уже есть аккаунт? Войти».

**Решение этой ночи (Notion):** при `ONBOARDING_ENABLED=0` (аварийный выключатель на
время тура) роль на регистрации **остаётся** — иначе преподаватель не смог бы
зарегистрироваться преподавателем: спросить роль больше негде. При включённом
онбординге роли нет.

**Цель Метрики и вид регистрации.** Роль теперь известна только на «Кто вы?»: при
включённом онбординге `record_signup(..., defer_goal=True)` пишет источник с видом
«ученик» и ставит в сессию отметку; шаг «Кто вы?» зовёт
`signup_source.confirm_role` — уточняет `SignupSource.signup_kind` и отправляет цель
`signup_student`/`signup_teacher` ровно один раз. Старый аккаунт источник не трогает.

**Вход** (`login.html`): «Почта или логин» (при `MAIL_ENABLED=0` — «Логин», как было),
«Пароль» с глазом, «Забыли пароль?» над полем, «Войти», сверху кнопки сервисов, внизу
«Нет аккаунта? Создать». `RoleBasedLoginView`/`EmailOrUsernameBackend` не менялись.
Строка «Нет почты в аккаунте? → Telegram» осталась на странице сброса пароля.
Левая колонка — только правдивые цифры: число видимых задач (тот же шлюз, что у
каталога, кэш 1 ч) и «2 тур 13–22 ноября» из `vp/config.py` (после тура строки нет).

**Старые аккаунты (решение за владельца, в Notion):** входят логином в поле «Почта
или логин»; логин меняется в профиле, почта добавляется и подтверждается на
«Почте»; без подтверждённой почты при `MAIL_ENABLED=1` в онбординге есть шаг «Почта»
с тихой ссылкой «Позже» (мягко, без блокировки — решение 26.10). Делается в фазе 3.

**Вид (макет Main / Register / Code / Consent / NeedEmail / PhLogin):** страницы
теперь с шапкой сайта (`_nav.html`) и фоном-узором, подвал в потоке; слева
заголовок и пункты/шаги, справа карточка 420 px с тенью; переключатель «Вход |
Регистрация»; поля 44, графитовая кнопка 48. «Код из письма» — шесть ячеек поверх
поля `code` (вставка заполняет все, после шестой цифры форма уходит сама; без
скрипта — одно поле). «Почти готово» и «Осталась почта» — в том же стиле.
«Осталась почта» — это `/account/email/` в виде экрана входа
(`registration/need_email.html`) для аккаунта из сервиса без почты и для шага
онбординга `src=onb`; галочка рассылки едет скрытым полем, чтобы не отозвать её.
На 760 px и уже — левой колонки и переключателя нет, карточка без рамки, поля 16.

**Тесты Анича — под новую правду, без ослабления** (`test_register_email`, 29 OK):
- шаг 1 — почта + пароль; логин `^econ_[a-z0-9]{6}$`; подложенная `role=tutor`
  игнорируется (при онбординге);
- «логин заняли между шагами» → «почту подтвердили другим аккаунтом между шагами»
  (гонка осталась только за почтой) + новый «сгенерированный логин не берёт занятый»;
- «@ в логине» → «логин из формы не берётся вовсе»;
- новые: в HTML нет `name="role"`, `password2`, «Им вы входите»; валидаторы на
  одном поле; старый аккаунт входит логином в поле «Почта или логин»; без
  онбординга роль на форме остаётся.
- `test_accounts`: «пароли должны совпадать» → «единственный пароль по-прежнему
  проверяется» (короткий и похожий на логин — отказ). `test_signup_source`: из списка
  замаскированных полей убран `password2`.
- Связка `test_register_email`, `legal.test_register`, `test_accounts`,
  `test_signup_source`, `test_social_login` — 159 OK.

## Р2 · Фаза 3. Онбординг: новая структура

**Данные — миграция `problems/0085_onboarding_goals`** (0084 не тронута): `goals`
(JSON-список кодов `vsosh / listed / international / knowledge / undecided`, как
`olympiad_history`) вместо `main_olympiad`; `source_other` (`CharField(120)`). Перевод
старых ответов в той же миграции (`hse/mosh/listed → listed`, `vsosh → vsosh`,
`ieo → international`, `undecided → undecided`), обратный ход есть. Тестовые данные
ветки, не бой. На базе ветки применена: `0085 … OK`. `profile_markers.py`: `goals`,
`source_other` (маркер «ОткудаМаркер»), `main_olympiad` убран.

**Шаги** (`problems/views_onboarding.py` переписан, `templates/onboarding/step.html`):
- ученик: `role → grade (класс → уровень) → goals → school (кроме none) → source →
  [email] → build → plan`; преподаватель: `role → teach → source → [email] → group`;
  `onboarded_at` — после `source` у обеих ролей;
- **одиночный выбор = кнопка отправки** (`<button name=role value=student>`): без
  скрипта форма уходит сама, со скриптом — галочка 280 мс и переход без перезагрузки;
- «Кто вы?»: у нового ничего не `aria-pressed="true"` (`_role_preset`: подсвечено
  только у преподавателя или у ученика с ответами в профиле);
- класс и уровень — один адрес, два этапа: POST `grade` → тот же шаг на этапе
  уровня (пилюля «10 класс · Изменить», `?change=1` — снова классы); POST `level` →
  дальше. «Уже не школьник» — так же;
- цели — плитки 2 в ряд с настоящими логотипами (`static/onboarding/logos/` + README
  с источниками), квадратная отметка, «Пока не решил» во всю ширину; сервер отвечает
  ошибкой «не сочетается», скрипт гасит остальные;
- «Где вы учитесь?» — город и школа (подсказки — фаза 4);
- «Откуда узнали» — 8 пилюль стены; «Другое» разворачивает поле «Где именно?» и
  «Готово»; любая другая — сразу дальше; сноска про Instagram внизу шага;
- «Добавьте почту» — старому аккаунту без подтверждённой почты при `MAIL_ENABLED=1`,
  последним перед планом: «Получить код» ведёт на `/account/email/?src=onb` (экран
  `need_email.html`, логика Анича), «Позже» — дальше, в этот проход шаг не вернётся;
- преподаватель: «Где и кого вы учите?» (3 плитки + пилюли 5–11), «Первая группа» —
  код приглашения показан ДО создания (выдан `StudentGroup._free_invite_code()`, лежит
  в сессии, из формы не берётся), «Создать группу» → кабинет, «Позже».
- Адреса раунда 1 (`olympiad`, `place`) ведут на начало.

**Каркас** (`templates/onboarding/base.html`): шапка 68 px — логотип `_wordmark.html`
высотой 44 (раунд 1 держал его шириной — отсюда «съехали»), «Назад» (место держит и
скрытая), сплошная полоса прогресса `(N−1)/M`, «N из M», «Выйти». Справа карточка
«Ваш профиль» (`_me.html`): текущая строка акцентом, только что заполненная мигает;
у «не школьника» строки «Школа» нет; < 960 px карточки нет. Нижней полосы нет:
«Дальше» под выбором, подвал с документами — блок в потоке (на телефоне «Дальше»
`sticky` к низу, подвал под ней).

**Скрипт** (`static/onboarding/onboarding.js`): запрос → смена середины с анимацией
(уезжает влево 200 мс, приезжает справа 320 мс, «Назад» зеркально; класс → уровень —
сжатие и проявление), `history.pushState`, «Назад» браузера (`popstate`); полоса в
шапке остаётся и доезжает за 500 мс; фокус на заголовок нового шага. «Дальше»
выезжает после первого выбора. `prefers-reduced-motion` — без движения и задержек.

**Шлюз:** не менялся — он ведёт на `/welcome/`, а тот сам выбирает шаг по профилю и
сессии; пропуск «школы» у «не школьника» и повторный вход «туда, где остановился»
закрыты тестами.

**Тесты (`test_onboarding` + `test_onboarding_gate`, 69 OK)**, новые сверх прежних:
выбор роли без кнопки; у нового ни одной `aria-pressed="true"`; класс → уровень на
одном экране; «Пока не решил» + другая → ошибка; «не школьник» → «4 из 4», `school`
закрыт; «Другое» с текстом / без «Другое»; шаг «Почта» и «Позже»; карточка профиля
(строки, `is-now`, `is-new`, нет «Школы»); подвал после `</main>` без обёртки и ни
одного `position: fixed` в стилях; логотипы целей на месте; вид регистрации
уточняется на «Кто вы?» один раз; миграция 0085 — `GoalsMigrationTests` (hse →
listed, ieo → international, undecided, пусто).

## Р2 · Фаза 4. Подсказки городов и школ

**Города.** Кандидаты: `hflabs/city` — лицензия в README явная, **CC BY-SA 4.0**;
`arbaev/russia-cities` — файла лицензии нет (404), лицензия непонятна → не берём.
`city.csv` HFLabs (1 117 строк) скачан в отдельную папку черновиков; собран
`problems/data/cities_ru.json` — 1 116 городов, поля `name`, `region` (словами),
`population`, по населению. Ловушка источника: у Москвы, Санкт-Петербурга и
городов-округов (Балашиха, Химки…) поле `city` пустое, название в `area` — сборка
берёт `city or settlement or area`. Восемь кривых регионов («Республика Удмуртская»,
«Саха /Якутия/», «Ханты-Мансийский Автономный округ - Югра автономный округ» …)
приведены к обычному виду. Источник, лицензия, авторство и пометка «производный
набор под CC BY-SA» — `problems/data/README.md`.

Сборка (для пересборки): читать `city.csv` `csv.DictReader`; `name = city or
settlement or area or (region при region_type='г')`; регион = `region` для «г»,
«Республика X» для «Респ», иначе `region + тип словами`; поправить восемь названий
(словарь в журнале выше по смыслу); сортировать по `-population`; убрать повторы
(name, region).

**Поиск** (`problems/school_search.py`): «ё» = «е», без регистра; город — с начала
названия > с начала слова > в середине, внутри по населению; синонимы `мск`, `спб`,
`питер`, `петербург`, `екб`, `нск`; до 8, вторая строка — регион. Числительные словами
до 3000 — свой разборщик (`words_to_number`: количественные, порядковые по основам с
окончаниями, «тысяча»). Школа — только в выбранном городе; номер из запроса
(`57`, `№57`, `школа 57`, `57-я`, `лицей 1535`, словами); точный номер → номер с начала →
по названию; до 8; последняя строка «Нет в списке – оставить «…»».

**Школы — попытка 1 не удалась:** `obrnadzor.gov.ru`, `isga.obrnadzor.gov.ru`,
`data.mos.ru`, `apidata.mos.ru`, `data.gov.ru` — все **таймаут** с этой машины
(госсайты РФ отсюда не открываются). Формат выгрузки реестра проверить нельзя.
**Попытка 2:** таблица `problems.School` (миграция **0086**, `problems/models_schools.py`:
название, короткое, вид, номер, город, регион, `city_norm`, уникальность
(название, город, регион)) + `manage.py load_schools <csv> [--apply]` (сухой прогон
по умолчанию, идемпотентно) — заливается CSV, как его получить из реестра —
`problems/data/README.md`. Пока справочник пуст, подсказки берут названия, которые
ввели ученики этого города, **только если одно название ввели ≥ 3 других человек (спрашивающий не считается)** (чтобы
в подсказку не утекла случайная запись одного человека). Карточка Notion «Загрузить
реестр школ» (Техническое).

**Адреса:** `GET /welcome/api/cities/?q=`, `GET /welcome/api/schools/?city=&q=` —
JSON `{"results": [...]}`; гость — 403; потолок 120 запросов в минуту на человека
(429); пустой `q` — пусто. Интерфейс (`onboarding.js`): выпадающий список под полем,
задержка 150 мс, стрелки/Enter/Escape, совпавшие буквы жирные, `role=combobox`,
`aria-expanded`, `aria-activedescendant`, `role=listbox/option`; после выбора города —
зелёная галочка и выезжает поле «Школа»; без скрипта — два обычных поля.
Проверено в браузере: «мо» → Москва первой; «57» → «Школа № 57», «№ 571», «Лицей № 579».

**Тесты (`test_school_search`, 18 OK):** 12 примеров числительных; «мо» → Москва;
«питер»/«спб» → Санкт-Петербург; ё/е; «57», «пятьдесят седьмая», «школа 57», «№57»,
«57-я» → № 57 первой; только свой город; по названию; чужие вводы — только повторённые;
гость — 403; потолок частоты; `load_schools` дважды → строк столько же; сухой прогон
ничего не пишет.

## Р2 · Фаза 5. «План готов»: сборка и содержание

- **Сборка** — `/welcome/build/` (`templates/onboarding/build.html`): шапка с полной
  полосой и «Готово», без «Выйти»; плитка с «искрой» вращается (6 с на оборот);
  строки по одной через 450 мс: индикатор → галочка с «пружинкой»; потом строки
  уезжают вверх, снизу поднимаются три заготовки карточек, и страница уходит на план
  (≈ 2,7 с на три строки). Строки: «Подбираем задачи для {N} класса» («…для 7 и
  младше класса» у `le7`; у «не школьника» — «Подбираем задачи под ваш уровень»),
  «Смотрим ближайшие туры», «Собираем план». Со стены ВП (`next`) — две строки и
  сразу в `next` (`?to=`, адрес проверяется `is_safe`). Без скрипта — `<noscript>`
  с мгновенным переходом; при «уменьшить движение» скрипт уходит сразу.
- **План** (`plan.html`, `plan_cards()`): «{Имя}, план готов» (без имени — «План
  готов»), чипы класса, уровня и целей + «Изменить» (`/welcome/grade/?change=1`),
  справа «Начать» → первая задача. Сетка 1,15 : 1 : 1 — «Три задачи для старта» на две
  строки сетки (название целиком с переносом, без обрезки; точка темы; 5 звёзд с
  погашенными), олимпиадная карточка, «Вызов дня», широкий «Умный поиск»; под
  сеткой пунктирная «Скоро · Подбор задач по вашим ошибкам» — единственное обещание.
- **Олимпиадная карточка по целям:** `listed` или класс 9–11 → «Тренажёр 2 тура
  «Высшей пробы»» с логотипом ВП, «N дней до тура» из `vp/config.py`, «Открыть
  вариант N класса» (нет варианта — «Открыть варианты»); только `vsosh` → «Задачи
  ВсОШ» — каталог с источниками, в названии которых «ВсОШ»/«Всеросс», и сложностью по
  уровню (нет таких источников — каталог с `q=ВсОШ`); `knowledge`/`undecided` →
  «Карта тем» `/catalog/map/`. Кнопки внутри — `k-btn--plain`.
- «Умный поиск» — пример «задача про монополию с налогом» → `/catalog/?q=…`.
- Телефон: всё столбцом, «Начать» прибита к низу (`sticky`), подвал под ней.
- **Тест:** состав карточек для (10, `listed`), (8, `vsosh`), («не школьник»,
  `knowledge`) — `PlanTests` в `test_onboarding`.

## Р2 · Фаза 6. Полировка и сверка с макетом

Обход скриптом Playwright (`.playwright-mcp/walk_r2.js` в основной папке, вне
репозитория): 18 экранов × (1280×800, 390×844) × (светлая, тёмная) = **72 снимка** в
`reports/login_onboarding_20261029/shots_r2/*_ours.png`. На каждом замер: прокрутки
вбок нет — 72/72; подвал с документами есть и не внутри `position: fixed` — 72/72;
логотип цел (шапка сайта 27×27, онбординг 83×44; на телефоне онбординга логотипа
нет, как в макете); обрезанного многоточием текста — 0. Тёмная тема — токены
(фон `rgb(29,26,22)`). Длинных тире в тексте сайта — 0 (`check_em_dash.py`).
Плашки логотипов олимпиад белые в обеих темах (подложка знака, см. README).

| Экран | Эталон | Проверено | Снимок | Отступления |
|---|---|---|---|---|
| Вход | Main | раскладка, кнопки, поля, тема, 390 | Main*_ours | шапка — настоящая `_nav.html` (круглый знак 27 px, а не начертание, и «Войти/Создать аккаунт» справа); подвал — партиал сайта («Рекомендации», слева «Beta»), а не центрированная строка макета; число задач — живое из каталога |
| Регистрация | Register | то же | Register*_ours | тексты галочек — Анича дословно (длиннее макета, карточка выше 800 px); «Продолжить с …» → «Войти с …»: сервисы запрещают менять текст кнопки |
| Код из письма | Code | шесть ячеек, вставка, автоотправка | Code*_ours | «Отправить код ещё раз через N с» — прежняя кнопка Анича вместо «0:42» |
| Почти готово | Consent | строки, галочки | Consent*_ours | строки «Дата рождения» нет, пока выключен `SOCIAL_STORE_BIRTHDATE` |
| Осталась почта | NeedEmail | — | NeedEmail*_ours | нет |
| Кто вы? | Role | ничего не выбрано, переход по нажатию | Role*_ours, OldRole*_ours | нет |
| Класс → уровень | Grade, Level, PhLevel | этапы, пилюля «Изменить» | Grade*/Level*_ours | тексты уровней — из кода (как требует промпт) |
| Цели | Goals, PhGoals | логотипы, отметки, «Дальше» выезжает | Goals*_ours | «Перечневые олимпиады» на телефоне полностью (в макете «Перечневые олимпиады / … РАНХиГС») |
| Где вы учитесь? | School | подсказки, галочка | School*_ours | ширина полей 560 (в макете 560) |
| Откуда узнали | Source | 8 пилюль, «Другое», сноска | Source*_ours, GradSource*_ours | нет |
| Добавьте почту | Email | «Позже» | Email*_ours | поле 560 вместо ~480 |
| Сборка | Build | строки, галочки | Build*_ours | нет |
| План | Plan | сетка, карточки | Plan*_ours | «Вызов дня»: подпись «Wecon Rush» без «2 минуты» — у вызова дня несколько режимов (1–10 мин), «2 минуты» было бы неправдой; на компьютере одна «Начать» (справа сверху, как в макете), нижняя — только на телефоне |
| Преподаватель | Teach1, Teach2 | плитки, пилюли, код | Teach1*/Teach2*_ours | без сегмента «Группа / Индивидуально» раунда 1 (его нет в макете); индивидуальное занятие — в кабинете |

Общие отступления: фон-узор логотипов на шагах онбординга выключен (в макете его
нет на шагах, есть на сборке и плане — так и сделано); `«—»` из макета («Минута —
и…», «Нет в списке — …») заменено на «–»: длинное тире на сайте запрещено правилом
владельца.

## Р2 · Фаза 7. Стена ВП и бот: один онбординг на всё

Ред. 2 в ветке есть (фаза −1) → сделано по карточке Notion
`408b11c9-2bc1-811f-a528-d299306f9f2c`:
- `vp/views_wall.py`: `survey_known(user)` — класс 9–11 и «откуда узнали» из профиля;
  анкета показывает только неизвестное (`ask_grade`, `ask_source`), «Вы прошли во 2
  тур?» — всегда; заголовок по числу вопросов: «Три вопроса / Два вопроса / Последний
  вопрос – и начинаем»; при сохранении известное сервер берёт **из профиля, а не из
  формы**; обратно в профиль стена пишет пустые класс (как было) и теперь
  `source_channel`.
- `vp/templates/vp/_wall.html`: только `{% if %}` вокруг двух `fieldset` и заголовок
  из контекста; строки сносок не тронуты. Строка шагов окна «2 · Три вопроса» не
  тронута (вне разрешённой правки) — при одном вопросе она остаётся прежней.
- Подписи источников — одно место: `VPWall.SOURCE_CHOICES =
  tuple(UserProfile.SourceChannel.choices)`; `makemigrations --check` — изменений нет.
- **Обратное направление:** анкета стены раньше онбординга → профиль получает класс и
  источник → онбординг открывает «класс» сразу на этапе уровня с «10 класс · Изменить»,
  а на «Откуда узнали» пилюля `vk` уже `aria-pressed="true"`. Доказано тестом.
- **Бот Telegram** (`vp/bot.py`) — проверено по коду: функции `_start`, `_ready_text`,
  `_check_keyboard`, `_message`, `_callback` шлют только привязку аккаунта и проверку
  подписки; ни класса, ни «откуда узнали» бот не спрашивает. Код бота не трогал.

**Тесты (`vp/tests/test_wall_onboarding.py`, 6 OK):** 10 класс + источник → один
вопрос, POST только с `tour2_status` создаёт попытку, подложенные `grade`/`source` из
формы проигнорированы; 8 класс → вопрос о классе есть; пустой профиль → три; стена →
онбординг показывает ответы; источники стены = профиля; путь «гость → регистрация с
`next` на вариант → шлюз → онбординг → `/welcome/build/?to=<вариант>` → после
контакта стена не спрашивает ни класс, ни источник».

Карточка Notion — в «Готово» (фаза 8).

## Р2 · Фаза 8. Зубастость, прогоны, документы, Notion

**Зубастость** — по одному дефекту на новый тест, тест, `git checkout` файла, снова
тест (скрипт в черновиках сессии). 12/12 краснеют, после откатов `git status` пуст:

| у нового человека «Ученик» выбран заранее | `problems/views_onboarding.py` | `problems.tests.test_onboarding.StudentFlowTests.test_new_person_sees_nothing_preselected` | красный | OK |
| «не школьник» не пропускает шаг 4 | `problems/views_onboarding.py` | `problems.tests.test_onboarding.StudentFlowTests.test_not_a_pupil_skips_the_school_step` | красный | OK |
| «пятьдесят седьмая» не разбирается | `problems/school_search.py` | `problems.tests.test_school_search.NumberWordsTests` | красный (вставлен вручную: строка в скрипте не совпала) | OK |
| подвал внутри фиксированной полосы | `static/onboarding/onboarding.css` | `problems.tests.test_onboarding.FooterTests` | красный | OK |
| регистрация снова показывает role | `problems/forms_accounts.py` | `problems.tests.test_register_email.RegisterWithEmailTests.test_form_is_email_and_password_only` | красный | OK |
| кнопка сервиса с ключом demo | `problems/social/providers.py` | `problems.tests.test_social_login.KeyCheckTests` | красный | OK |
| «Пока не решил» сохраняется вместе с другой целью | `problems/views_onboarding.py` | `problems.tests.test_onboarding.StudentFlowTests.test_undecided_does_not_go_with_another_goal` | красный | OK |
| «Другое» без «Другое» всё равно пишет текст | `problems/views_onboarding.py` | `problems.tests.test_onboarding.StudentFlowTests.test_other_source_keeps_the_text` | красный | OK |
| свой профиль добирает порог подсказок школ | `problems/school_search.py` | `problems.tests.test_school_search.SchoolSearchTests` | красный | OK |
| стена берёт класс из формы, а не из профиля | `vp/views_wall.py` | `vp.tests.test_wall_onboarding.WallAsksOnlyTheUnknownTests.test_known_grade_and_source_leave_one_question` | красный | OK |
| логин регистрации берётся из формы | `problems/views_auth.py` | `problems.tests.test_register_email.RegisterWithEmailTests.test_right_code_creates_verified_account_with_mail_consent` | красный | OK |
| шаг «Почта» не появляется у старого аккаунта | `problems/views_onboarding.py` | `problems.tests.test_onboarding.EmailStepTests.test_old_account_without_email_gets_the_step_last` | красный | OK |

**Прогон** (без `--parallel`, SQLite): `legal`, весь `vp` (кроме
`vp.tests.test_wall_poll.PollSignalTests`: шлёт процессу SIGTERM и на Windows убивает весь
прогон — остальные классы файла прогнаны поимённо), `test_register_email`,
`test_auth_hardening`, `test_accounts`, `test_profile_account_tab`, `test_signup_source`,
`test_production_settings`, новые (`test_onboarding`, `test_onboarding_gate`,
`test_social_login`, `test_social_models`, `test_school_search`, `test_wall_onboarding`),
сторожа шаблонов/ПДн и всё, что нашёл `grep` по изменённым шаблонам и полям
(`test_beta_smoke`, `test_email_codes`, `test_fb_button_style`, `test_feedback`,
`test_obzor_nav`, `test_password_reset_code`, `test_print_sheet`, `test_r15_builder`,
`test_track`, `legal.test_erase_user`, `catalog.test_attempts`, `test_chat_api`,
`test_guest_solutions`, `test_seo`, `config.test_nav`, `game.test_duel_page`,
`test_final_screen`, `test_wecon_texts`) — **1 459 тестов за 20,6 мин, 1 падение,
skipped=1** (браузерный): `vp.tests.test_wall_screens.SurveyTests.test_grade_is_preselected_from_profile`
— старая правда «класс из профиля выбран заранее»; по карточке стены известный класс
теперь не спрашивается вовсе. Тест переписан под новую правду
(`test_grade_from_profile_is_not_asked_again`) + добавлен
`test_grade_is_preselected_from_the_variant_when_profile_is_empty` (предвыбор по
варианту остался). Перепрогон `test_wall_screens` + `test_wall_onboarding` — 43 OK;
`test_security_headers` (обход матрицы) — 15 OK.

**Нули:** `manage.py check` — 0; `makemigrations --check --dry-run` — No changes detected;
`check_em_dash.py` — 0 (код 0); `ruff check` по 42 изменённым `.py` — All checks passed;
`bandit -ll` по новым и изменённым модулям — No issues identified.

**Документы:** `docs/SOCIAL_KEYS.md` (новый), `static/social/README.md`,
`static/onboarding/logos/README.md`, `problems/data/README.md`, `docs/SECURITY.md`
(раздел «Раунд 2»), `docs/SECURITY-MATRIX.md` (+2 строки), `CLAUDE.md` (абзац входа).
Блок «Текущий фокус» и `CLAUDE_ARCHIVE.md` не трогал — как и в раунде 1, чтобы не
было конфликтов со стеной и main.

**Служебное:** для проверки в браузере в `C:\Users\shipu\qls\.claude\launch.json`
(основная папка) временно добавлялась запись `login-r2` (порт 8017); после проверки
файл возвращён `git checkout`. Тестовые аккаунты (`r2new`, `r2tutor`, `r2grad`,
`kostya_econ`, `econ_vk0001`, пароль `Ochen-Dlinnyi-Parol-77`) и 5 школ Москвы — в
`db.sqlite3` worktree, не на бою.

**Notion (записано):**
- «Решения», 4 новые (30.10): старые аккаунты и шаг «Почта»; логотип из партиала;
  источник городов и школ и лицензия; правило автоперехода.
- «Задачи»: новая «Загрузить реестр школ для подсказок онбординга» (Техническое, Надо);
  «Стена ВП: не переспрашивать…» → Готово; «Заменить заглушки значков…» → Готово;
  комментарий в «Зарегистрировать приложения VK ID и Яндекс ID» (localhost:80, SOCIAL_KEYS.md);
  главная задача `408b11c9-…ab62e` — итог раунда 2 в «Заметки», «На проверке».
- Не записано как решение (лимит «больше 5 карточек — после показа владельцу»):
  «при `ONBOARDING_ENABLED=0` роль остаётся на регистрации» — вынесено в отчёт.

---

# РАУНД 3 (29.10.2026): правки владельца после живой проверки

Промпт «Вход и онбординг, раунд 3». Notion прочитан: «Задачи» («В работе», «Надо») и
10 последних «Решений» — три решения 29.10 этого раунда уже записаны (школа не зависит
от города; логотипы целей без плашек; реестр школ — своя таблица + еженедельная
синхронизация), повторно не пишу.

## Р3 · Фаза −1. Сверка

- `git status` — чисто; последний коммит `a84340fc` (р2 ф.8) — совпадает с журналом.
- Тесты раунда 2: `test_social_login` + `test_onboarding` + `test_onboarding_gate` +
  `test_school_search` — **126 OK** (103 с). ⚠️ В окне владельца задан
  `MAIL_ENABLED=1` без почтового канала → `manage.py test` падает на системной
  проверке `mail.E001` до первого теста. Тесты гоняю с `env -u MAIL_ENABLED -u
  SOCIAL_* -u YANDEX_* -u VK_ID_* -u ONBOARDING_ENABLED` (тесты сами включают что нужно).
- **Ключи сервисов** (значения не печатались, только проверка вида):

  | Переменная | Состояние |
  |---|---|
  | `YANDEX_CLIENT_ID` | задан, похож на настоящий (32 знака 0–9a–f) |
  | `YANDEX_CLIENT_SECRET` | задан |
  | `VK_ID_CLIENT_ID` | задан, похож на настоящий (только цифры) |
  | `VK_ID_CLIENT_SECRET` | задан |
  | `SOCIAL_LOGIN_ENABLED` | задан, `1` |
  | `SOCIAL_REDIRECT_BASE` | не задан |

- Школ в `problems.School` (база worktree) — **5** (тестовые московские из раунда 2);
  городов в `problems/data/cities_ru.json` — **1 116**.
- Папки `C:\Users\shipu\weconomics-data\schools\` нет — файла реестра заранее нет.

## Р3 · Фаза 1. Вход через VK ID и Яндекс ID: живая проверка

**Ключи есть — живая проверка сделана.**

### Что выяснилось запросами (без печати ключей)

- **Яндекс** без входа в Яндекс уводит `oauth.yandex.ru/authorize` → `passport.yandex.ru`
  (`retpath`) и о приложении ничего не говорит. Зато обмен заведомо неверного кода
  (`POST oauth.yandex.ru/token`) различает: наш `client_id` → `invalid_grant` («Code has
  expired»), выдуманный → `invalid_client` («Client not found»). Это и есть проверка
  «приложение существует» в `social_check`.
- **VK ID** проверяет приложение И адрес возврата ещё до входа: с
  `http://localhost/auth/vk/callback/` в странице есть «Weconomics», с чужим адресом в
  странице встроено `"error":{"message":"redirect_uri is missing or invalid","code":
  "invalid_request"}`. Обмен (`/oauth2/auth`) с поддельным кодом отвечает одинаково
  («invalid device id») для любого `client_id` — для диагностики бесполезен.
- `id.vk.ru` с машины владельца изредка рвёт TLS (1 запрос из ~5) — в `social_check`
  один повтор при сбое связи.

### `https` за прокси

`config/settings_production.py:59` — `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO',
'https')`; nginx (`deploy/nginx/available/django.conf`, `location /`) шлёт
`X-Forwarded-Proto $scheme` и `Host $host` → `build_absolute_uri()` даёт `https://…`.
**Но** сайт отвечает на двух именах (`server_name weconomics.site … weconomics.ai …`,
без переадресации одного на другое), а в кабинетах сервисов один адрес возврата: с
weconomics.site сервис отказал бы. Поэтому добавлена `SOCIAL_REDIRECT_BASE`: адрес
возврата строится от неё; вход, начатый не на её хосте, сначала переводится на то же
начало на нём (иначе `state` лежал бы в сессии другого имени). Для `.env` сервера —
`SOCIAL_REDIRECT_BASE=https://weconomics.ai` (`docs/SOCIAL_KEYS.md`, раздел 4).

### Что сделано

- `manage.py social_check [--base]` (`problems/management/commands/social_check.py`):
  флаг, ключ (только «задан, длина N»), адрес возврата, GET адреса авторизации с
  параметрами настоящей кнопки (код, конечный хост, признаки ошибки, встроенная ошибка
  VK), для Яндекса — обмен неверного кода, итог одной строкой.
- Понятные ошибки возврата (`problems/social/views.py`, `templates/social/error.html`):
  `error=` сервиса разбирается ДО проверки `state` (аккаунтов не трогает): `access_denied`
  → «Вход через … отменён», `invalid_request`/`invalid_scope` → «… не принял запрос
  сайта», `invalid_client`/`unauthorized_client` → «… не узнал сайт», прочее — «… отказал
  во входе»; сбой обмена → «… не ответил», нет токена/номера → «… не передал данные
  аккаунта» (`SocialError.step`). Кнопки «Попробовать снова» (тот же `next`) и «Войти по
  почте» («Войти по логину» без почты). Журнал: `Вход через <сервис> не удался: шаг X,
  код Y`, код ошибки — только `[a-z0-9_]{1,40}`, иначе `other`.
- VK ID не на `localhost`/`localhost:80` при `DEBUG` и без `SOCIAL_REDIRECT_BASE` → наша
  страница «Для проверки VK ID откройте http://localhost/login/» (сессия не трогается).

**Тесты:** новый `problems.tests.test_social_r3` — 20 (ошибки: `access_denied`,
`invalid_request`, без `state`, чужой код в журнал не попадает, сбой обмена — в журнале
нет кода/`state`/токена, нет данных, «Войти по логину»; адрес возврата с боевым
`SECURE_PROXY_SSL_HEADER` и `X-Forwarded-Proto: https` → `https://weconomics.ai/auth/`;
`SOCIAL_REDIRECT_BASE` и перевод с .site; обмен шлёт тот же адрес; VK на 127.0.0.1 /
localhost / без DEBUG; `social_check` ×7 с подменой сети). Вместе с `test_social_login` —
**59 OK**.

### Живая проверка (Playwright, Python; поставлен в `venv313`: `playwright 1.64.1`)

| Сервис | Сервер | Конечный хост | Ошибки на странице | Снимок |
|---|---|---|---|---|
| Яндекс | `127.0.0.1:8010` | `passport.yandex.ru` (вход в Яндекс) | нет («Неизвестное приложение» нет) | `shots_r3/yandex_authorize.png` |
| VK ID | `localhost:80` (порт был свободен) | `id.vk.ru` | нет; страница «Вход в «Weconomics.ai»» с логотипом | `shots_r3/vk_authorize.png` |

`/auth/vk/start/` на `127.0.0.1:8010` → 400 и «Для проверки VK ID откройте
http://localhost/login/» (проверено curl). Дальше «Разрешить» нажимает владелец.

### `social_check` (вывод без ключей)

```
--base http://127.0.0.1:8010
  Яндекс: адрес возврата http://127.0.0.1:8010/auth/yandex/callback/; авторизация 200 → passport.yandex.ru;
          обмен неверного кода 400 invalid_grant
  VK ID:  адрес возврата http://127.0.0.1:8010/auth/vk/callback/; 200 → id.vk.ru;
          ошибка в странице: redirect_uri is missing or invalid (invalid_request)
  Яндекс: готов (адрес возврата Яндекс сверяет после входа — он должен стоять в кабинете буква в букву)
  VK: VK ID на своём компьютере принимает только http://localhost (порт 80); адрес возврата не прописан в кабинете сервиса

--base http://localhost
  Яндекс: … 400 invalid_grant → Яндекс: готов (…)
  VK ID: 200 → id.vk.ru; приложение узнано: в странице есть «Weconomics» → VK: готов

без --base (боевой https://weconomics.ai)
  Яндекс: готов (…) · VK: готов
```

(Первый прогон `--base http://localhost` дал «VK: нет связи (URLError)» — тот самый
обрыв TLS; после добавления повтора — «готов».)

## Р3 · Фаза 2. Вход и регистрация: тексты и «Забыли пароль?»

- `templates/registration/login.html`: заголовок «Олимпиадная экономика <em>в одном
  месте</em>» — без тире; «Забыли пароль?» перенесена ПОД поле пароля (`au-forgot
  au-forgot--under`), над полем — только подпись «Пароль» (обёртка `au-label-row` у
  пароля убрана). Обе ветки ссылки (почта → `/password/forgot/`, без почты → Telegram)
  сохранены.
- `templates/registration/register.html`: «Настройте сайт <em>под себя за минуту</em>».
- `static/onboarding/onboarding.css`: `.au-forgot--under { align-self: flex-end;
  margin-top: 2px }` — 6 px промежутка `.au-field` + 2 = 8 px от поля; 13 px и
  `--accent-ink` — прежние правила `.au-forgot`. Кнопки не трогал.
- Снимки: `shots_r3/login_1280.png`, `login_390.png`, `register_1280.png` — ссылка под
  полем справа на обеих ширинах.

**Тесты:** новый `problems.tests.test_auth_texts_r3` — 4 (заголовок входа точно и без
«экономика –/—/-» при почте и без; подпись → поле → ссылка, между подписью и полем
ссылки нет; заголовок регистрации; стиль 8 px / вправо / 13 px / акцент). Вместе с
`test_register_email`, `test_auth_hardening`, `test_accounts` — **107 OK**.

## Р3 · Фаза 3. Онбординг: роль и цели

- **«Кто вы?»** — чипы под названием убраны полностью (`ROLE_CHIPS` в
  `problems/views_onboarding.py`, `.ob-role-chips` в шаблоне и стилях); плитка — значок,
  название, отметка; `min-height: 168px` вместо 220.
- **«К чему готовитесь?»** — у всех пяти целей логотип без плашки (`GOAL_PLATES`):
  - `.ob-plate` — 104×64, без фона, рамки и полей; `img` вписан (`object-fit: contain`);
  - ВсОШ, «Перечневые», «Международные» — прежние файлы, класс `ob-plate--olymp`;
    кружки РАНХиГС/РЭШ на `var(--surface)`;
  - «Разобраться в экономике» — новый `static/onboarding/logos/weconomics_w.svg`: путь
    буквы W скопирован программно из `static/img/logo-mark.svg` без круга, `viewBox`
    по границам пути (замер в браузере: 513,4 428,7 411,0 × 298,8), 76×56;
  - «Пока не решил» — веер ВсОШ / «Высшая проба» / IEO / РАНХиГС, стили дословно из
    промпта (`grayscale(1)`, 0,5 → 0,75 при наведении);
  - картинка «спрос и предложение» и пунктирный «?» удалены;
  - тёмная тема: `[data-theme="dark"] .ob-plate--olymp { background: var(--brand-cream);
    border-radius: 10px; padding: 6px }`.
- ⚠️ Токена `--brand-cream` в `templates/_tokens.html` не было (он есть только в
  `docs/design/onboarding_r2/w.css`: `#fffce6`). Добавлен в обе темы рядом с
  `--brand-amber`, с тем же значением, что в макете (брендовый, не тематический).
- `static/onboarding/logos/README.md` — правило «белая плашка» заменено новым.
- Снимки (после перезапуска сервера: первый снимок шёл на старой вьюхе — сервер не
  перечитал Python): `shots_r3/welcome_role_{1280,390}_{light,dark}.png`,
  `welcome_goals_{1280,390}_{light,dark}.png`. Глазами: пять логотипов, в тёмной теме
  подложка только под тремя олимпиадными.

**Тесты:** новый `problems.tests.test_onboarding_r3` — 6 (роль без чипов и
`min-height: 168px`; пять плиток — в каждой `<img>`, нужные файлы, веер из четырёх;
нет `ob-plate--draw`, кривой «спрос-предложение», пунктирного «?», у `.ob-plate` нет
`background`/`border`, `#ffffff` в правилах плашек нет, кружки на `--surface`; подложка
тёмной темы только у трёх олимпиадных; веер бледный и серый). Вместе с `test_onboarding`,
`test_onboarding_gate`, `test_palette_tokens`, `test_tokens_css` — **90 OK**.

## Р3 · Фаза 4. Город и школа

### 4.1. Поломка выпадающего списка — воспроизведена и починена

**Воспроизведение (Playwright, до правки):** пока поле «Школа» было скрыто (город пуст),
поломки нет. Город заполнен → оба поля видны → «мо»: `elementFromPoint` в центре
«Москва» — `LABEL.ob-label`, «Можга» — `INPUT` поля школы. Причина — ровно та, что
предполагал владелец: у `.ob-field` анимация `ob-up` с `animation-fill-mode: both`
оставляет `transform: matrix(1,0,0,1,0,0)` → каждое поле — свой слой, поле «Школа» ниже
по разметке рисуется поверх списка города. В 4.2 школа видна всегда, так что поломка
была бы у всех.

**Починка:**
- `.ob-anim-up` — `backwards` вместо `both` (конечный `transform` не остаётся);
- `.ob-field.is-ac-open { position: relative; z-index: 30 }` — класс ставит скрипт, пока
  список открыт (выше липкой «Дальше» с z-index 4);
- список: сплошной `var(--surface)`, `var(--shadow-pop)`, `max-height: 320px`,
  `overscroll-behavior: contain`; вторая строка серым (регион у города, город у школы);
  полное название (короткого нет) — 13 px;
- выбор — `pointerdown` + `preventDefault()` (поле не теряет фокус); мышь выбирает сразу,
  палец — по `click` (иначе длинный список нельзя листать, не выбрав случайно). Закрытие
  по `blur` — только если указатель не держит список и не над ним;
- клавиатура: стрелки, `Enter`, `Escape`, **`Tab` выбирает подсвеченный**; первый вариант
  подсвечен сразу; совпавшие буквы жирные; пустой результат — одна строка «Нет в списке
  – оставить «…»» (тире короткое: длинное на сайте запрещено);
- на телефоне список сам докручивается в видимую часть (`visualViewport`, минус липкая
  «Дальше»).
- **Найден по пути второй баг:** после выбора скрипт сам шлёт `input` (оживить «Дальше»),
  а подсказки принимали его за ввод и через 150 мс открывали список снова («Нет в списке
  – оставить «Москва»» поверх поля «Школа»). Теперь подсказки отвечают только на
  `isTrusted`-ввод.

**`tools/onb_autocomplete_check.py`** (Playwright, Python): `page.mouse.click()` по
координатам варианта на 1280, `page.touchscreen.tap()` на 390 с `is_mobile/has_touch`,
перед нажатием — `elementFromPoint` (варианты, ушедшие в прокрутку внутри списка, не
проверяются). **16 OK, 0 FAIL:**

| Сценарий | Итог |
|---|---|
| 1280: варианты города ничем не накрыты (9 видимых) | OK |
| 1280: первый подсвечен, совпавшие буквы жирные | OK |
| 1280: список сплошной, z-index поля 30 | OK |
| 1280: «мо» → щелчок по «Москва» → «Москва», галочка, список закрыт | OK |
| 1280: «мо» → ↓ ↑ Enter → «Москва» | OK |
| 1280: ↓ + Tab выбирает подсвеченный («Можга») | OK |
| 1280: Escape закрывает | OK |
| 1280: пустой результат — одна строка | OK |
| 1280: «57» без города — школы разных городов, у каждой город | OK |
| 1280: выбор школы при пустом городе подставляет город | OK |
| 1280: «57» + «Казань» — казанская первой | OK |
| 390×844: поле и список видны целиком, ничем не накрыты (список 207–527) | OK |
| 390×844: «мо» → тап по «Москва» | OK |
| 390×844: «57» → тап по первой школе | OK |
| 390×500 (как с клавиатурой): поле и список видны (111–431) | OK |
| 390×500: «мо» → тап по «Москва» | OK |

Первый прогон скрипта дал 4 FAIL: 2 — настоящий баг с повторным открытием (выше),
2 — ошибка самого скрипта (варианты в прокрутке внутри списка считались «накрытыми»).

Снимки: `shots_r3/ac_city_open_1280.png`, `ac_city_chosen_1280.png`,
`ac_school_57_1280.png`, `ac_city_open_390x844.png`, `ac_city_open_390x500.png`,
`ac_school_57_390.png`.

### 4.2. Школа не зависит от города

- Оба поля видны сразу (`initSchool` и `data-ob-school` удалены); у «Города» снят
  `required`.
- `school_search.schools(city, query)` — по всей стране: кандидаты из `School`
  (`is_active=True`, номер ровно/с начала диапазонами `57, 570–579, 5700–5799` или слова
  в `name_norm`), своего города отдельным запросом; порядок — свой город → точный номер
  → номер с начала → по названию → крупный город раньше (население из
  `cities_ru.json`). До 8. Синонимы города (`мск`, `спб`) работают и здесь.
- Подсказка: `{value, label, full, number, sub, city}`; `sub` — город, а если город с таким
  названием есть в разных регионах — «город, регион». Неоднозначность — по справочнику
  городов (точному), а по таблице школ — только для сёл, которых там нет (иначе «Москва»
  становилась «неоднозначной» из-за школ реестра с регионом «Московская область»).
- `/welcome/api/schools/?q=&city=` — `city` необязателен, влияет только на порядок.
- Скрипт: выбрал школу при пустом «Городе» — город из записи школы (с галочкой).
  Сервер (`SchoolForm.clean`) делает то же без скрипта, если название однозначно указывает
  на один город; иначе «Укажите город.». Школа из другого города сохраняется с введённым
  городом.
- Скорость на 42 025 школах (SQLite): 30–60 мс на запрос (первый — ~250 мс: считается
  список неоднозначных городов, дальше кэш на час).

### 4.3. Реестр школ

**Источник — реестр Рособрнадзора, скачался с этой машины.** `HEAD` постоянной ссылки:
`200`, `application/zip`, `content-length 352255124`, `data-20261029-structure-20160713.zip`,
`Last-Modified: 29.10.2026 00:11`. Архив (352 256 439 байт) — в
`C:\Users\shipu\weconomics-data\schools\raw\`; внутри `…xml` (1 022 973 535 байт) и `…sig`.
Страница открытых данных — одностраничное приложение без машинного списка версий
(`/api/spa/accredreestr/opendata` → 404), поэтому «последняя версия» = заголовки
постоянной ссылки (имя с датой + размер); `sync_schools` сравнивает их с последней
удачной синхронизацией.

**Структура подтвердилась** (`Certificate` → `ActualEducationOrganization`,
`Supplements/Supplement/EducationalPrograms/EducationalProgram/EduLevelName`).
Наблюдения: одна организация — во многих свидетельствах (старые недействующие +
действующее); филиал приходит приложением со своей карточкой организации; в старых
записях встречается `EduLevelName = «Среднее профессиональное образование»` с
`ProgrammName = «Начальное общее образование»` — такие не считаем (смотрим только
`EduLevelName`). **`KindName` и `TypeName` пусты у всех 42 025 отобранных организаций**,
поэтому отбор — только по уровню программ. В XML есть ФИО директоров, телефоны и почты
— не читаем.

**Разбор** (`problems/school_registry.py`): `iterparse` из ZIP без распаковки, 21 с на весь
реестр, пик выделений Python ≈ 108 МБ. Организация берётся из приложения (так филиал —
отдельная школа). Город из `PostAddress`: пометки «г.», «пгт», «рп/рабочий посёлок», «с.»,
«п.», «д.» (с буквой после — «д. 2» это дом), «ст-ца», «аул/а.», «аал», «улус», «станция»…
в любом месте строки; тип после названия («ЧЕЛЯБИНСК ГОРОД»); город без пометки — по
справочнику городов; название городского округа — последним; Москва, Санкт-Петербург,
Севастополь — по региону; КАПСЛОК → обычное написание. Название: без «ГБОУ/МБОУ/ПО…»,
кавычек, хвостов «г. Москвы», «Калининского района Санкт-Петербурга», «Г.О. Донецк»;
вложенные кавычки выравниваются; КАПСЛОК → «Школа № 71 им. П.Ф. Батулы»; первая буква
прописная.

⚠️ **Ловушка, на которой встал разбор:** проверка «до кавычек одни сокращения»
регуляркой с вложенным квантификатором на длинном префиксе капслоком перебирала
экспоненциально — разбор не кончился и за 10 минут. Нашёл `faulthandler`ом, заменил
проверкой по словам; тест на длинный префикс есть.

Без города после первой версии разбора — 3,53 % (больше порога) → разобрал выборку
адресов, расширил пометки → **0,79 %** (332 школы: в основном школы при посольствах и
адреса без населённого пункта).

**Модель** (миграция `problems/0087_schools_registry`, 0086 не тронута): у `School` +
`registry_id`, `inn`, `kpp`, `is_branch`, `is_active`, `name_norm`; уникальность
(название, город, регион) — только для строк CSV, `registry_id` — уникален, если не пуст;
город может быть пустым. Новая модель `SchoolSyncRun` — журнал синхронизаций (админка,
только чтение). `RunPython` заполняет `name_norm` у старых строк, обратный ход — noop
(поле удаляется откатом). Проверено: `migrate` → откат до 0086 → снова `migrate` — OK;
`makemigrations --check` — No changes detected.

**Движок** (`problems/school_sync.py`), один на `load_schools --format raoo` и
`sync_schools`: новые — добавить, изменённые — поправить, исчезнувшие — выключить; запасной
ключ ИНН + КПП (та же школа под новым идентификатором); одна транзакция; предохранитель —
файл с числом школ меньше половины действующих не применяется. Скачивание: таймаут 60 с,
3 попытки с паузой, проверка размера по `Content-Length`, не меньше 1 МБ, ZIP или XML.
Таймер для сервера — `deploy/systemd/weconomics-schools.{service,timer}` (понедельник
05:30), инструкция — `docs/SERVER.md`, «Справочник школ». **На сервере не включал.**

**Загрузка в базу ветки (не бой):** 5 тестовых московских строк CSV раунда 2 удалены (мои
же тестовые, дублировали бы реестр). Затем:

| Проверка | Порог | Итог |
|---|---|---|
| Школ всего | ≥ 30 000 | **42 025** (филиалов 3 792) |
| Москва | ≥ 700 | **759** (Санкт-Петербург 773) |
| `57` с городом «Москва» | первая — «Школа № 57» | **«Школа № 57», Москва** |
| Повторная загрузка / `sync_schools` второй раз | строк столько же, «изменено 0» | `load_schools --apply` второй раз: новых 0, изменено 0, выключено 0; `sync_schools --file` — то же |
| Сбой скачивания (тест с подменой сети) | таблица не тронута | `test_download_failure_leaves_the_table_alone` — OK |
| Школ без города | ≤ 3 % | **0,79 %** |

(По ходу правок разборщика `sync_schools --file` показывал «изменено 1 804 / 140 / 1 676»
— это перезапись названий новой версией разбора; каждый следующий прогон — 0.)

Примеры: «57» без города → Школа № 57 (Москва), Школа № 57 (Санкт-Петербург), СОШ № 57
(Новосибирск), СОШ № 57 (Екатеринбург), Школа № 57 (Казань)…; «57» + Казань — казанская
первой; «1» + Березовка → «БСШ № 1 им. Е.К. Зырянова» (Березовка, Красноярский край).

**Тесты:** новый `problems.tests.test_schools_r3` — 25 (разбор: только действующие и общее
образование, филиалы, отменённые программы, ZIP, ФИО и почта директора не попадают, 11
названий, 12 адресов, длинный префикс не виснет, «50-летия» не номер; движок: добавить/
изменить/выключить и повтор = 0, ИНН + КПП, битый файл, сухой прогон, строки CSV не
трогаются; `sync_schools` с подменой сети: скачал-разобрал-журнал, тот же файл не качает,
`--force`, сбой скачивания не трогает таблицу, обрыв по размеру и не-архив — отказ,
`load_schools --format raoo`; поиск: «57» без города — разные города с подписью, «57» +
Москва и «мск», регион только у повторяющихся названий, выключенная не видна, API без
`city`; шаг: город из школы, школа из другого города, неизвестная без города — «Укажите
город.», оба поля сразу). `test_school_search` — два теста переведены на новую правду
(«только выбранный город» → «выбранный город первым»). Вместе с `test_onboarding`,
`test_onboarding_r3` — **105 OK**.

## Р3 · Фаза 5. Телефон и сквозная проверка

Скрипт обхода (Playwright, Python; `walk_r3.py` в черновиках сессии, вне репозитория):
пути «ученик» (регистрация → «Кто вы?» → класс → уровень → цели → город и школа тапом /
щелчком по подсказкам → «Откуда узнали» → сборка → план), «не школьник», «преподаватель» —
на 390×844 (`is_mobile`, `has_touch`, тапы) и 1280×800, в светлой и тёмной теме; плюс окно
390×500 (как с экранной клавиатурой) — фокус в каждом поле и открытый список.

На каждом экране: нет прокрутки вбок; подвал с документами есть; липкая «Дальше» не
закрывает поле в фокусе; варианты открытого списка подсказок ничем не накрыты
(`elementFromPoint`); поле в фокусе не за краем окна.

Сервер для обхода — `127.0.0.1:8011` с `MAIL_ENABLED=0`: в `.env` worktree почта включена,
и регистрация просила бы код из письма. Настоящая регистрация — в первом пути каждой
ширины; после 7 регистраций с одного адреса сайт честно отвечает 429 (защита
`REGISTER_SCOPE`), поэтому остальные пути — аккаунты `r3pool1…20` «как после регистрации»
(согласие дано, онбординг не пройден), вход паролем, дальше тот же шлюз на `/welcome/`.

**Итог: 88 экранов, 88 OK.** Снимки — `shots_r3/walk/*.png` (88) и `walk.json`.

| Путь | Экран | 390 светлая | 390 тёмная | 1280 светлая | 1280 тёмная |
|---|---|---|---|---|---|
| ученик | 1_role | OK | OK | OK | OK |
| ученик | 2_grade | OK | OK | OK | OK |
| ученик | 3_level | OK | OK | OK | OK |
| ученик | 4_goals | OK | OK | OK | OK |
| ученик | 5_school | OK | OK | OK | OK |
| ученик | 5_city_open | OK | OK | OK | OK |
| ученик | 5_school_open | OK | OK | OK | OK |
| ученик | 5_chosen | OK | OK | OK | OK |
| ученик | 6_source | OK | OK | OK | OK |
| ученик | 7_build | OK | OK | OK | OK |
| ученик | 8_plan | OK | OK | OK | OK |
| не школьник | 1_role | OK | OK | OK | OK |
| не школьник | 2_grade | OK | OK | OK | OK |
| не школьник | 3_level | OK | OK | OK | OK |
| не школьник | 4_goals | OK | OK | OK | OK |
| не школьник | 6_source | OK | OK | OK | OK |
| не школьник | 7_build | OK | OK | OK | OK |
| не школьник | 8_plan | OK | OK | OK | OK |
| преподаватель | 2_teach | OK | OK | OK | OK |
| преподаватель | 3_source | OK | OK | OK | OK |
| преподаватель | 4_group | OK | OK | OK | OK |
| окно 390×500 | focus_city | OK | — | — | — |
| окно 390×500 | list_city | OK | — | — | — |
| окно 390×500 | focus_school | OK | — | — | — |
| окно 390×500 | list_school | OK | — | — | — |

**Найдено обходом и починено:** в подсказке школ «Школа № 57, Москва» стояла дважды — после
того как её выбрали трое тестовых учеников, она приходила ещё и как «повторённый ввод
людей». Сверка шла по `name_norm` (короткое + полное название вместе), а не по
показываемому названию. Тест `test_school_chosen_by_people_is_not_shown_twice`.
После правки оба сервера перезапущены, обход и `tools/onb_autocomplete_check.py`
прогнаны заново: 88/88 и 16/16.

## Р3 · Фаза 6. Зубастость, прогоны, Notion — ОСТАНОВЛЕНО НА ЗУБАСТОСТИ

Скрипт зубастости (`teeth.py` в черновиках сессии: дефект → тест → `git checkout` файла → тест снова) **остановлен системой из-за нехватки памяти** после 18 из 39 дефектов. Рабочая копия после остановки чистая (`git status` пуст) — ни один дефект в коде не остался. Перезапуск — только по слову владельца. Серверы 8010/8011 остановлены, чтобы освободить память.

| Дефект | Тест | С дефектом | После отката |
|---|---|---|---|
| вернуть тире в заголовок входа | `test_auth_texts_r3.LoginTextTests.test_login_heading_has_no_dash` | красный | OK |
| «Забыли пароль?» снова над полем | — | дефект не вставился (многострочный образец не совпал: переводы строк CRLF) | — |
| старый заголовок регистрации | `test_auth_texts_r3.RegisterTextTests` | красный | OK |
| ссылка сброса вплотную к полю | `test_auth_texts_r3.ForgotStyleTests` | красный | OK |
| redirect_uri с http:// при X-Forwarded-Proto: https | `test_social_r3.RedirectUriTests.test_behind_nginx_with_production_settings_it_is_https` | красный | OK |
| вход с .site не переводится на SOCIAL_REDIRECT_BASE | `test_social_r3.RedirectUriTests.test_base_is_used_and_the_other_name_is_sent_there_first` | красный | OK |
| error=access_denied даёт 500 | `test_social_r3.ReturnErrorTests.test_access_denied` | красный | OK |
| чужой код ошибки сервиса уходит в журнал | `test_social_r3.ReturnErrorTests.test_unknown_error_code_is_not_copied_into_the_log` | красный | OK |
| сбой обмена — без «Попробовать снова» | — | дефект не вставился (многострочный образец не совпал: переводы строк CRLF) | — |
| VK на 127.0.0.1 уходит к сервису | `test_social_r3.VkLocalhostTests.test_vk_on_127_is_our_hint_page` | красный | OK |
| social_check не узнаёт чужой адрес возврата | `test_social_r3.SocialCheckCommandTests.test_vk_wrong_redirect_uri_and_deleted_app` | красный | OK |
| social_check не видит invalid_client Яндекса | `test_social_r3.SocialCheckCommandTests.test_unknown_yandex_app` | красный | OK |
| social_check печатает ключ | — | дефект не вставился (многострочный образец не совпал: переводы строк CRLF) | — |
| чипы вернулись на «Кто вы?» | `test_onboarding_r3.RoleTilesTests.test_role_tile_is_icon_name_and_mark_only` | красный | OK |
| плитка роли снова 220 px | `test_onboarding_r3.RoleTilesTests.test_role_tile_is_about_168px_high` | красный | OK |
| белая плашка вернулась на шаг целей | `test_onboarding_r3.GoalLogosTests.test_no_white_plate_and_no_supply_demand_picture` | красный | OK |
| в тёмной теме подложка белая, а не кремовая | `test_onboarding_r3.GoalLogosTests.test_dark_theme_pad_only_under_olympiad_logos` | красный | OK |

Из 18: **15 красных, все зелёные после отката**; 3 не вставились. Не дошли до очереди 21 дефект (поиск школ без города, город при выборе школы, реестр, синхронизация, `sync_schools`) — список в `teeth.py`.

### Р3 · Фаза 6 — доделано в начале раунда 4 (29.10.2026, вечер)

Прежняя сессия после остановки по памяти дошла по `teeth.py` до дефекта 36 (результаты —
`teeth_results.jsonl` в её черновиках): три «не вставились» (CRLF) вставлены и
покраснели (№1, 8, 12); беззубый тест №28 («ФИО директора попадает в данные») был
зелёным с дефектом — починен коммитом `fcd4465a`, перепроверен — красный. Остались №37–38,
прогнаны сейчас тем же скриптом, без серверов:

| Дефект | Тест | С дефектом | После отката |
|---|---|---|---|
| обрыв скачивания не замечен | `test_schools_r3.SyncSchoolsCommandTests.test_truncated_or_wrong_file_is_refused` | красный | OK |
| сбой скачивания не пишется в журнал | `test_schools_r3.SyncSchoolsCommandTests.test_download_failure_leaves_the_table_alone` | красный | OK |

**Итог зубастости раунда 3: 39 из 39 красные с дефектом, все зелёные после отката**
(один беззубый найден и починен — `fcd4465a`). `git status` после — чистый.

Прогон раунда 3 (без `--parallel`, переменные окна владельца сняты): `test_social_login`,
`test_social_r3`, `test_social_models`, `test_onboarding`, `test_onboarding_r3`,
`test_onboarding_gate`, `test_auth_texts_r3`, `test_register_email`, `test_school_search`,
`test_schools_r3` — **215 тестов, OK, 140,7 с, код 0**. «Нули» раунда 3 сняты вместе с
раундом 4 (фаза 6 ниже) — код раунда 3 с тех пор менялся только правками раунда 4.
Главная карточка Notion — итог раундов 3 и 4 одной записью в фазе 6 раунда 4.

---

# РАУНД 4 (29.10.2026, вечер): финальная полировка после живой проверки владельца

Промпт «Вход и онбординг, раунд 4». Notion прочитан: «Задачи» («В работе», «Надо» — 40
карточек) и 6 последних «Решений»; решение «Подвал с документами — только на главной, в
профиле, на /legal/ и на входе/регистрации» (29.10) уже записано владельцем — не дублирую,
дописываю в него в фазе 6.

## Р4 · Фаза −1. Сверка

- `git status` — чисто, последний коммит `fcd4465a`.
- Фаза 6 раунда 3 не была закрыта (2 дефекта из 39, прогоны, журнал) — доделана, см. выше.
- Тесты, названные в промпте, плюс соседи: **215 OK** (см. выше).
- Ключи сервисов в окружении ЭТОЙ сессии и в `.env` worktree: `YANDEX_CLIENT_ID`,
  `YANDEX_CLIENT_SECRET`, `VK_ID_CLIENT_ID`, `VK_ID_CLIENT_SECRET`, `SOCIAL_LOGIN_ENABLED`,
  `SOCIAL_REDIRECT_BASE` — **не заданы** (владелец задаёт их в своём окне PowerShell).
  Живая проверка VK в фазе 1 — только у владельца.

## Р4 · Фаза 1. VK ID: медленный ответ

### Что было

`providers._request`: один `urlopen` с `timeout=10`, любой сбой → `SocialError` с
текстом, а в журнал уходило `код social_error` — причина терялась. Две попытки из трёх у
владельца упали ровно через ~10 с — это и был `HTTP_TIMEOUT = 10`.

### Что сделано

1. **Причина в журнале.** `SocialError.reason`: `timeout`, `timeout_response`, `network`,
   `network_dns`, `network_tls`, `network_response`, `http_<код> <error>` (поле `error` из
   JSON-тела, только `[a-z0-9_]{1,40}`; `error_description` не читается — в нём бывает эхо),
   `bad_response`, `no_token`, `no_user_id`. Строка: `Вход через vk не удался: шаг exchange,
   причина timeout`. Для `error=` в адресе возврата — тоже «причина» (`шаг authorize,
   причина access_denied`), чтобы формат был один; три проверки журнала в `test_social_r3`
   переписаны с «код» на «причина».
2. **Таймаут** — настройка `SOCIAL_HTTP_TIMEOUT`, по умолчанию 20 с.
3. **Повтор — один и только если запрос не ушёл.** Граница — как ведёт себя `urllib`: сбой
   соединения и отправки приходит `URLError` (повтор), а таймаут ОЖИДАНИЯ ответа — голым
   `TimeoutError` (без повтора: VK мог уже погасить код, и повтор дал бы только
   `invalid_grant`). После любого HTTP-ответа повтора нет. ⚠️ Общий предел на вход с
   повторами — `TOTAL_BUDGET = 50` с: у gunicorn `--timeout 60`, у nginx
   `proxy_read_timeout 60s`; 20 + 20 на обмен и ещё 20 + 20 на данные убили бы воркер раньше,
   чем человек увидел нашу страницу.
4. **Страница таймаута:** «VK ID долго не отвечает. Попробуйте ещё раз» + «Попробовать
   снова» / «Войти по почте».
5. **`ext_id` и `type=code_v2`.** Документация VK ID (id.vk.ru, «Описание API», обмен кода
   `POST /oauth2/auth`, OAuth 2.1): обязательны `grant_type`, `code_verifier`,
   `redirect_uri`, `code`, `client_id`, `device_id`, `state`; `ext_id` и `type` там не
   упоминаются вовсе — **при обмене не нужны**, не передаём. Тест: адрес возврата ровно как у
   владельца (`…&ext_id=…&type=code_v2`) проходит. ⚠️ Попутно: та же страница называет
   `service_token` обязательным «для конфиденциальных приложений». Наше веб-приложение
   публичное (PKCE, без секрета при обмене), и одна из трёх попыток владельца прошла — значит,
   это не наш случай; если VK когда-нибудь ответит `http_400` с жалобой на клиента — смотреть
   сюда первым.
6. **Двойная обработка.** Почему два WARNING на один возврат с разницей 5 с возможны:
   `callback` забирает `state` из сессии в памяти, а в базу сессия попадает только с ответом.
   Пока первый запрос 10 с ждал VK, второй такой же (браузер повторил запрос; точная причина
   на машине владельца не установлена) читал ещё не сохранённую сессию с целым `state` и шёл
   менять тот же код второй раз. Теперь после проверки `state` ставится метка в общий кэш
   `cache.add('social:state:<sha256>')` — атомарно; второй запрос с тем же `state`:
   первый уже вошёл → туда же, куда повёл бы вход; ждёт «Почти готово» → туда;
   первый ещё ждёт сервис → 409 «Вход через VK ID уже выполняется…» + «Попробовать снова».
   Второго обмена нет ни в одном случае. ⚠️ Кэш общий только в пределах Redis на бою (или
   одного процесса runserver локально) — этого достаточно: метка нужна на 10 минут потока.
7. **Тесты** — `problems/tests/test_social_r4.py` (15), сеть подменена на уровне
   `urllib.request.urlopen`: таймаут → повтор → вход; таймаут дважды → «долго не отвечает»;
   HTTP 400 → без повтора, `http_400 invalid_grant` в журнале, `error_description` нет;
   таймаут ожидания ответа → без повтора; DNS → повтор; мусор → `bad_response`; 20 с по
   умолчанию и из настройки; предел 50 с; второй запрос во время первого → 409 и один обмен;
   повторный возврат после входа и при «Почти готово». Во всех — код, `device_id`, токен и
   `state` в журнал не попали. `test_social_r4` + `test_social_r3` + `test_social_login` —
   **74 OK**.
8. **Живая проверка** — ключей в окружении сессии нет; вход нажимает владелец (команда — в
   отчёте). Таблица причин — `docs/SOCIAL_KEYS.md`, раздел 5.

## Р4 · Фаза 2. Без шапки сайта на входе; онбординг с узором и без подвала; подвал — только где нужен

### Решение владельца (29.10.2026) и обоснование

Подвал сайта (метка версии + © · Документы · Политика · Соглашение · Рекомендации ·
Настройки cookie · 12+) — **только** на главной, в профиле (все вкладки), на `/legal/…` и на
входе, регистрации и всём, что их наследует («Почти готово», код из письма, «Осталась почта»,
ошибки сервисов). Обоснование (152-ФЗ): Политика должна быть опубликована и доступна на
сайте, а не стоять на каждой странице; ссылки с главной и профиля это обеспечивают; согласие
человек даёт на регистрации или «Почти готово» — там подвал и остаётся. Окно согласия на
cookie — не подвал: оно на всех страницах, как было. Знак 12+ (436-ФЗ) — отдельный партиал
`_age_mark.html`, вопрос «нужен ли на каждой странице» — карточка Аничу (фаза 6).

### Как сделано

- `templates/_site_footer.html` — новый партиал: `_site_version.html` + `_legal_footer.html`;
  в комментарии — явный список страниц с подвалом и ссылка на решение.
- Каждый корневой шаблон, где подвал был, держит **пустой** `{% block site_footer %}{% endblock %}`
  (с комментарием про решение). Страницы с подвалом: `{% block site_footer %}{% include
  '_site_footer.html' %}{% endblock %}` — `catalog/home.html`, `legal/index.html`,
  `legal/document.html`, `platform/profile.html`, `registration/login.html`, `register.html`.
  `legal/accept.html` (экран согласия, `/legal/…`) не тронут — подвал у него свой.
- `_legal_footer.html`: «12+» вынесен в `{% include '_age_mark.html' %}`. Вернуть знак на все
  страницы без подвала = поставить `_age_mark.html` в пустые блоки корней.
- **Шапка:** во входе и регистрации `{% include '_nav.html' %}` → `{% block site_nav %}{% include
  'registration/_auth_top.html' %}{% endblock %}` — полоса 56 px с логотипом (`_wordmark.html`,
  как у онбординга), он же ссылка на главную. Всё, что наследует `register.html`, получает её
  же. Онбординг шапки сайта и раньше не имел (своя `ob-top`).
- **Узор онбординга:** в `onboarding/base.html` по умолчанию снят `data-bg-pattern="off"` —
  узор на всех шагах (сборка и план и раньше его включали). Карточки и плитки на своём фоне.
  Контраст — снимками в фазе 5.
- **Калькулятор:** полоса `calc-foot` в 30 px убрана, `.app` снова `calc(100vh - 48px -
  var(--ck-h, 0px))`, окно выбора моделей — до низа окна (над окном cookie). Страница задачи
  («Стол»): подвал там и так прятался правилом `stol.css`; правило не тронуто (сторожит тест),
  раскладку в высоту окна подвал не задавал.
- Мёртвые правила `body.ob > .legal-foot` убраны из `onboarding.css`.

### Тронутые строки (для слияния; номера — в файле ДО правки)

| Файл | Строки | Что |
|---|---|---|
| `catalog/templates/catalog/base.html` | 201–202 | версия + подвал → пустой блок |
| `problems/templates/platform/base.html` | 102–103 | то же |
| `student/templates/student/base.html` | 212–213 | то же |
| `teacher/templates/teacher/base.html` | 201–202 | то же |
| `calendar_stub/templates/calendar_stub/calendar.html` | 925–926 | то же |
| `game/templates/game/game.html` | 7336–7337 | то же |
| `game/templates/game/result.html` | 228 | подвал → пустой блок |
| `teacher/templates/teacher/assignment_print.html` | 309 | то же |
| `templates/_error_base.html` | 121 | то же |
| `templates/onboarding/base.html` | 25–26, 32, 46 | комментарий, узор, подвал → пустой блок |
| `calc2/templates/calc2/calc2.html` | 75–89, 2548–2551 | стили полосы, полоса → пустой блок |
| `templates/registration/login.html` | 20, 26, 91–92 | комментарий, шапка → блок, подвал → блок |
| `templates/registration/register.html` | 19–20, 33, 132–133 | то же |
| `templates/_legal_footer.html` | 78 | «12+» → `_age_mark.html` |
| `catalog/home.html`, `legal/index.html`, `legal/document.html`, `platform/profile.html` | в конце файла | +3 строки: блок с подвалом |

### Сторожа

- Новый `problems/tests/test_footer_r4.py` (8): подвал и метка версии есть на `/`,
  `/profile/`, `/profile/?tab=data`, `/legal/`, `/legal/privacy/`, `/login/`, `/register/`;
  нет на `/catalog/` (гость и ученик), странице задачи, `/calc2/`, `/textbook/`,
  `/olympiads/`, `/vp/`, `/game/`, `/student/`, `/teacher/groups/`, `/welcome/role/`; окно cookie
  (`id="cookie-bar"` + `cookie_bar.js`) на всех этих страницах; ни один корень не включает подвал
  мимо блока; `_age_mark.html` отдельно; нет `<nav class="site-nav">` на входе, регистрации,
  сбросе пароля, «Почти готово», ошибке сервиса и шагах онбординга.
- Переписаны под решение: `test_onboarding.FooterTests` (на шагах подвала нет; на входе и
  регистрации есть), `legal/tests/test_pages.py` (`RootTemplateFooterTests` — каждый корень
  решает про подвал блоком; `FooterRenderTests` — подвал на главной/legal/входе, нет в игре,
  калькуляторе, каталоге; калькулятор во всю высоту), `config/tests/test_nav.py`
  (`VersionBadgeTests`: метка там же, где подвал), `test_cookie_bar` (кнопка «Настройки cookie»
  — на главной), `test_print_sheet` (на листке подвала нет), `test_stol_polish` (версия — на
  главной), браузерные раннеры `stol_runner.mjs`, `browser_round.mjs`,
  `browser_teacher_sets.mjs` (метки может не быть вовсе).
- Прогон (без `--parallel`): `legal`, `config`, сторожа каталога, онбординга, входа, сервисов,
  Wecon Rush — **638 тестов, 637 OK, skipped=4, 1 падение**: `test_design_canon.CanonBrowserChecks`
  — раннер `calc2/tests/canon_checks.mjs` не находит пакет Node `playwright` (`node_modules`
  нет ни в worktree, ни в основной папке). Это окружение, а не правка; Python-Playwright в
  `venv313` есть, им идут проверки фаз 3 и 5.

## Р4 · Фаза 3. Регистрация помещается в окно без прокрутки

Замер — Python-Playwright, сервер worktree на `127.0.0.1:8012` с ключами-«похожками»
(`VK_ID_CLIENT_ID=51234567`, Яндекс — 32 hex; кнопки рисуются, к сервисам никто не ходит) и
почтой — то есть как у владельца: две кнопки сервисов, две галочки.

| Шаг | `/register/` 1440×778 | 1536×730 | карточка | `/login/` 1536×730 |
|---|---|---|---|---|
| до (как у владельца: 941 при шапке 48) | 950 (полоса-логотип 56 вместо шапки 48) | 950 | 420×766 | 764 |
| п. 2–3: карточка 500, отступы 12, заголовок 22, галочки 13/1.45, поля `au-main` 8/20 | 797 | 797 | 500×677 | 730 |
| полоса с логотипом поверх фона на широком экране (`position: absolute`, ≥ 761 px) | 778 | 733 | 500×677 | 730 |
| вертикальное поле карточки 24 → 20, поле `au-main` 8 → 4 | **778** | **730** | 500×669 | **730** |

Галочки при 500 px: согласие — 5 строк (было 6), рассылка — 2 (было 3). Тексты Анича не
менялись. Левая колонка по центру карточки по вертикали (`.au-main { align-items: center }` —
было и раньше, на снимках совпадает). Полоса с логотипом на широком экране своей высоты не
берёт: логотип слева вверху, карточка справа, заголовок слева по центру высоты — не
пересекаются (снимки); на узком (≤ 760 px) полоса в потоке, 56 px. Знак — 44 px, как в шапке
онбординга (класс `ob-logo-mark`): при 32 px слово «economics» читалось плохо.

**Итог: без прокрутки на всех четырёх окнах** (1440×778 и 1536×730, вход и регистрация, свет и
тьма). Запас на 1536×730 — 0 px: карточка 669 + поля 8 + подвал 40 + 13 на центровку.

Тест — `problems/tests/test_auth_fit_browser.py` (метка `serial`, живой сервер + Chromium;
раннер `auth_fit_runner.py` отдельным процессом — на Windows синхронный Playwright не
уживается с циклом событий тестового процесса). Мерит с кнопками сервисов, почтой и
включённым онбордингом (без него регистрация спрашивает роль — аварийный режим). OK.
Снимки — `shots_r4/register_*`, `shots_r4/login_*` (8).
