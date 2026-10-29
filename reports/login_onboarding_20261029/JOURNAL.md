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
