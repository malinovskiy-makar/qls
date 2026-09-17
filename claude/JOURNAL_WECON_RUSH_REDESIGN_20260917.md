# Журнал: редизайн Wecon Rush по макетам 17.09.2026 (фазы P1–P8)

Ветка `feat/wecon-rush-redesign`. Макеты и спецификации — `claude/mockups/wecon_rush_20260917/`.
Журнал обновляется после каждой подфазы и коммитится вместе с кодом. При повторном запуске
промпта: первая подфаза без галочки — место, откуда продолжать.

## Фаза −1 — сверка с реальностью

- Дата: 2026-09-17. Машина: macOS (Darwin 25.3), команды — `./venv313/bin/python`.
- Python 3.13.15, Django 5.2.17.
- База ветки: `main` = `origin/main` = `e586516e` (после быстрой перемотки, см. расхождения).
- `manage.py check` — 0 проблем.
- Базовый прогон `manage.py test game olympiads.tests.test_views olympiads.tests.test_training`:
  **867 тестов за 101 с, failures=1, skipped=1**. Падал браузерный
  `game.tests.test_browser_modals.RushModalPauseBrowserTest.test_modal_takes_keys_and_pauses_run`:
  тест кликал по `.fb-other`, а с коммита `364d3e1c` (bank-sync-v4, «Другое — галочка с полем
  по ней») поле скрыто до галочки «Другое, своими словами». Игра не сломана — устарел тест.
  Стоп-гейт «красное до правок» — спросил владельца, ответ: «Закоммитить починку и продолжать».
  Починка — одна строка в `game/tests/browser_modals.mjs` (отметить галочку перед кликом по
  полю); тест зелёный (1 тест, 7 с).

### Расхождения фазы −1 и как поступил
1. Локальная `main` отставала от `origin/main` на 20 коммитов: влитая 17.09 04:01 сессия
   bank-sync-v4. Своих коммитов в локальной `main` не было, дерево чистое. Это стоп-гейт
   фазы −1 — спросил владельца, ответ: «Подтянуть и продолжать». Выполнено
   `git merge --ff-only origin/main`, ветка создана от `e586516e`. В подтянутом есть метка
   «Beta 1.0» (`templates/_site_version.html`) — без неё фаза P8 не нашла бы саму метку.
2. Папки `claude/mockups/wecon_rush_20260917/` в репозитории не было; та же папка лежала в
   `~/Downloads/wecon_rush_20260917` (35 `.dc.html`, `canvas.json`, `README.md`, 8 файлов в
   `SPEC/` — числа сходятся). Спросил владельца, ответ: «Скопировать и закоммитить».
3. Все файлы из пункта 4 промпта на месте. «Три шаблона `game_set*.html`» — это
   `game_set_create.html`, `game_set_detail.html`, `game_sets_list.html`.

### Notion — что увидел
- Решения 17.09: все шесть на месте (главная-аркада, разбор 3 с, вызов дня, бесконечные тесты,
  наборы по коду, страница результата). Прежние 15.09 (ADR 0106, пауза сервером, синхронная
  дуэль) — на месте.
- Карточки-баги: все восемь найдены. P3 «автор не видит сравнение…» — `3deb11c9-2bc1-812a-8622-dc7624554d99`;
  P3 «живое табло… связь потеряна» — `3deb11c9-2bc1-8174-be0e-c993f6ed61fc`.
- Не в списке промпта, но относится к прогону: «Wecon Rush: подключить метку Beta 1.0
  (_site_version.html) в game.html» (`3deb11c9-2bc1-81a4-a8a2-cad99dcca9d1`, ответственный —
  «Сессия редизайна Wecon Rush») — беру в P8; «Игра: знаки «✕» и «→» заменить на SVG-значки»
  (`3dcb11c9-2bc1-815d-91d3-ce76f0225b15`) — закрывается общим правилом «иконки только SVG» в P1–P2;
  «Дуэль: сервер не запрещает начать раунд без соперника» (`3dcb11c9-2bc1-81d4-836e-cf26f22bb457`) —
  смотрю в P3.
- Сводной карточки «редизайн Wecon Rush» не было — создана: «Wecon Rush: редизайн по макетам 17.09 —
  все экраны игры и наборы учителя» (`3deb11c9-2bc1-813b-8c79-e36c5d291de1`), статус «В работе».

## Чек-лист фаз

- [x] Фаза −1 — сверка, ветка, макеты в репозитории, журнал, сводная карточка Notion

- [x] P1 Главная `/game/`
  - [x] P1.0 ADR 0108, `docs/GAME.md` «Стартовый экран»
  - [x] P1.1 Сервер: вкладки режимов, квота по режимам, рекорды вошедшего, ячейка «Вызов дня»
        (`daily.daily_cell`, `daily.streak_for` — P4.1 сделана заранее), `api/set_check`
  - [x] P1.2 Разметка `_start.html`, стили и код трёх зон, окно «Мои рекорды», `?mode=`/`?duel=`
  - [x] P1.3 Тесты: перенос старых проверок, новые (рендер, серия, код, клавиши), браузерный
  - [x] P1.4 Зубастость (50/50), Notion
- [x] P2 Раунд
  - [x] P2.0 Стоп-гейт A: анализ и план записаны (раздел «Стоп-гейт A» ниже)
  - [x] P2.1 Сервер: разбор 3 с (константы), брошенный раунд `quit`, пауза в табло дуэли
  - [x] P2.2 Полоса HUD, шапка скрыта, вопрос и варианты, нижний ряд
  - [x] P2.3 Разбор ошибки 3 с при стоящих часах, отсчёт 3-2-1
  - [x] P2.4 Служебные окна одной семьёй (выход, набор, «прервался», «нет связи», конец по жизням)
  - [x] P2.5 ADR 0109/0110, GAME.md, тесты
  - [x] P2.6 Зубастость (42/42), Notion
- [x] P3 Итог и дуэль
  - [x] P3.0 Сверка с кодом, базовый прогон (314 OK), ADR 0111/0112
  - [x] P3.1 Сервер итога: места в таблице, прошлый рекорд, доска дня, попытки, дуэль; правило рекорда
  - [x] P3.2 Итог: вердикт и действия, «Ход раунда», два ряда карточек, ошибки на странице, телефон
  - [x] P3.3 Варианты итога (вызов дня, набор, брошенный, дуэль) проверены глазами; браузерный тест итога
  - [x] P3.4 Дуэль: окно создания, лобби отдельной страницей (синхронный старт — на PostgreSQL)
  - [x] P3.5 Дуэль: приглашение, ожидание, сравнение для обоих (починка условия автора)
  - [x] P3.6 Тесты, зубастость (47/47), GAME.md, Notion (живое табло — только диагностика)
- [ ] P4 Вызов дня
- [ ] P5 Бесконечные тесты
- [ ] P6 Страница набора ученика и публичная страница результата
- [ ] P7 Кабинет учителя: наборы
- [ ] P8 Олимпиады, Beta 1.0, финал

## Стоп-гейт A (P2) — анализ и план

Промпт требует остановиться и показать это владельцу. Владелец 17.09 объявил сессию автономной
(«сам принимай решения»), поэтому анализ записан здесь ДО правок, а работа продолжена.

1. **Как пауза вызывается при разборе.** Клиент получает ответ `correct=false` → существующий
   `rushPause()` (POST `/game/api/pause/` через очередь `pauseSync`, `cancelAnimationFrame`) →
   через `CFG.reveal_wrong_ms` (3000) или раньше (пробел, Enter, «Дальше сразу») → `rushResume()`
   (POST `/game/api/resume/`) → `advance()`. Вопрос и следующий ответ уходят той же очередью ПОСЛЕ
   resume. Практика: без pause/resume (времени нет). Ответ, снявший последнюю жизнь: тоже 3 с
   разбора, затем оверлей конца; открытую паузу закрывает `api_session_finish` (`_close_pause`).
2. **Что говорит `_rank_run`.** Потолок `duration × (1 + TIME_BONUS_CAP_FACTOR) + 60 с`; из
   стенного времени вычитается `credited_pause_ms` — первые `PAUSE_MAX_COUNT = 5` закрытых пауз,
   суммарно не больше `PAUSE_CAP_SECONDS = 120`. Три ошибки = три паузы по 3 с = 9 с, остаётся две
   зачётные паузы на окна. Бюджет не выбивается даже без вычета: 9 с много меньше запаса 60 с.
   Бонус за скорость разбор не трогает: `elapsed_ms` меряет клиент от показа карточки.
3. **План правок.**
   - `config.REVEAL_WRONG_MS = 3000`, `config.ROUND_COUNTDOWN_S = 3` → в `CFG`.
   - `_end_reason`: `claimed == 'quit'` → `'quit'`.
   - `api_session_finish`: `reason='quit'` принимается только у раунда без набора и с непустым
     журналом; иначе 400 без сохранения (вторая защита «попытка набора не сгорает»).
   - `_rank_run`: сразу после `anonymous` — `ended == 'quit'` → `(False, 'quit')`.
   - `config.UNRANKED_REASONS`: `('quit', 'вы вышли из раунда')` вторым пунктом.
   - `leaderboard.best_run` и `best_scores`: брошенный раунд рекордом не считается — иначе текст
     окна «в таблицу и рекорды не пойдёт» был бы ложью. «Моя статистика» (`personal_stats`,
     `records_panel`) не меняется: брошенный учитывается, как любой незачётный.
   - `consumers.seconds_left_for`: вычитать паузу (зачтённая + открытая сейчас), иначе время в
     табло соперника убегало бы на 3 с за каждую ошибку в дуэли. Отдельной функцией в `views`.
   - У `ended_reason` (16) и `unranked_reason` (24) нет `choices` — миграция не нужна.
4. **Выход из дуэли сейчас.** Крестик → окно → `quitRun()` → `show('start')` БЕЗ
   `/session/finish/`: результат не сохраняется, событие `finished` сопернику не уходит. Сокет не
   закрывается (страница та же), `presence leave` не приходит — у соперника табло замирает на
   последнем счёте вышедшего, а его время дотикивает до нуля по локальным часам. На странице
   сравнения `/game/d/<код>/` вышедшего нет (нет `GameResult`). Логику не меняю; текст окна для
   дуэли: «Выйти из дуэли? Результат не сохранится: на странице дуэли останется только результат
   соперника».

## Факты сверки со спецификациями

### P1
1. `#mode-grid` был пустым `div`, карточки режимов рисовал JS (`renderModeCards`). Теперь вкладки
   рисует сервер (`start_modes`, режим с пустым пулом не рисуется) — иначе Django-тест рендера не
   увидел бы «4 вкладки»; JS (`renderModeTabs`) дорисовывает иконку, числа под фильтром, выбор.
2. `visibleModes` (играбельные режимы) заменён парой `shownModes` (вкладки на экране) +
   `isPlayable`; клавиши 1–5 ходят по вкладкам на экране, выключенная вкладка не выбирается.
3. «Моя статистика» (`api/me/stats/?mode=`) — ПО РЕЖИМУ, а не «все режимы», как в макете. Подпись
   сделал честной: «Моя статистика · <режим>» + «режим тот же, что слева».
4. Строка «Зачётных раундов сегодня» (`_quota_line`) считалась только по режиму по умолчанию, а
   квота — по режиму. Заменил на `_quota_payload` (все режимы одним запросом): «N из 10» у
   выбранного режима.
5. Серверного лучшего счёта в данных страницы не было — добавил `my_best`
   (`leaderboard.best_scores`, одним запросом). У гостя — `localStorage`, как было.
6. Публичные API игры (`leaderboard`, `pool_counts`) ничем не ограничены по частоте. Для
   `set_check` взял существующую лестницу задержек `problems/ratelimit.py` (как у кода занятия):
   промахи по адресу, 30 промахов → 30 с.
7. Режимов в `config.MODES` пять («График» за флагом). Вкладок столько, сколько режимов с пулом;
   ячейка «Вызов дня» считает вызовы так же (режим без вопросов вызова не получает).
8. Старая недоработка: фильтр из адреса или `localStorage` не отрисовывался при загрузке
   (`paintChips` звался только после правки). Починено: `paintChips()` + `refreshCounts()` при старте.
9. Режим по умолчанию оставлен серверный (`DEFAULT_MODE` = Блиц), хотя макет гостя открыт на
   Пуле: доска первой вкладки едет со страницей, а браузерные прогоны жмут Enter = Блиц.
10. Иконки из макета (play, calendar, duel, infinity, sliders, arrow_right, close, code) заведены
    в общий набор `_icon.html`/`_icons.html` со stroke 1.75: этого требует тест сетки иконок
    (`test_icons_follow_the_house_grid`), а не 2 px, как в промпте.
11. Токены: `--on-accent` (обе темы), `--medal-gold/silver/bronze` (металл одинаков в обеих темах,
    объявлен в `:root`). Остальные нужные (`--accent-ring`, `--accent-tint`, `--amber-tint` и др.)
    уже были.
12. Длинное тире в текстах макета («— просто решай», «Enter — старт») запрещено сканером
    `scripts/check_em_dash.py` (решение владельца) — в видимых строках «–» или двоеточие.
13. Слово «Забег» из спецификации в `aria-label` заменено на «Раунд» (решение 04.09: игрок
    «забега» не видит, держит тест `RoundNotRaceTests`).

### P2
1. Чип комбо по спецификации — «только при множителе ≥ ×2», но ступени экономики v2 начинаются с
   ×1,25 (`COMBO_STEPS`): при ×2 чип появлялся бы только на длинной серии. Показываю при множителе
   больше ×1.
2. Esc в обычном раунде действительно не открывал окно выхода: ветка клавиатуры знала Esc только у
   практики и окон. Теперь Esc открывает окно выхода (на отсчёте и на разборе тоже).
3. `consumers.seconds_left_for` паузы не вычитал: время соперника в табло убегало бы на 3 с за каждый
   разбор. Добавлен `views.paused_ms_now` (зачтённые паузы плюс открытая сейчас, тот же потолок).
4. Сервер отмечает `issued_at` вопроса при ПРЕДЗАПРОСЕ, то есть в момент показа предыдущего вопроса:
   бонус за скорость меряется вместе со временем над прошлым вопросом, а после ошибки — ещё и с 3 с
   разбора. Дефект старше фазы, экономику не трогаю — карточка в Notion «Надо».
5. Гонка, найденная браузерным тестом: после разбора ответ и подкачка следующего вопроса ждали
   одного resume и уходили разом; сервер пишет состояние забега целиком, и один из двух запросов
   терял запись (в тесте — изредка ответ без разбора). Починка — одна очередь запросов забега
   `queueRun` (пауза, resume, подкачка, ответ, финиш), зависший запрос держит её не дольше 8 с.
   Тест `answer_waits_for_prefetch` (подкачка задержана на 400 мс, ответ обязан уйти после неё).
6. Ошибка, забравшая последнюю жизнь: раунд на сервере уже закрыт, пауза разбора получала 409 и
   сыпала ошибку в консоль. Часы такого разбора стоят только в клиенте.
7. Плавающая кнопка обратной связи шапки на раунде скрыта, а браузерный `browser_modals.mjs`
   открывал окно через неё: переведён на «Плохая задача?» (тот же партиал формы, та же пауза)
   плюс проверка «Esc открывает окно выхода, часы стоят».
8. Потолок «очков за верный – до N» считает клиент числами `config` из `CFG` (они уже были для
   поповера старта) и эффективной сложностью, которую сервер теперь кладёт в вопрос.
9. Телефон 390 px: «−1» у сердец справа вылезал за экран (прокрутка вбок 13 px) — на телефоне он
   слева от сердец; чип рекорда «рекорд · ещё N» не помещался во второй ряд (22 px) — на телефоне
   рекорд текстом, как в макете RoundMobile, без «ещё N»; до 360 px скрыт «вопрос N».
10. Кнопки звука и выхода в макете телефона 30 px, правило промпта — цели от 44 px: квадрат 30 px
    рисует `::before`, зона нажатия 44 px; «Пропустить», «Плохая задача?», «Дальше сразу» на
    телефоне 44 px. Браузерная проверка `mobile_reveal_no_side_scroll_targets_44`.
11. Многострочный `{# … #}` Django не понимает — выводил текст на страницу (старт прокручивался на
    19 px). Комментарии разметки — только `{% comment %}`.
12. Карточка Notion «знаки ✕ и →»: `#btn-quit`, закрытие окна фильтров, «Свернуть (Esc)» — значок
    `close`; `#code-go` — `arrow_right` (P1); «Ссылка скопирована ✓» в итоге и на публичной
    странице — новый значок `check`. Метки вариантов «✓/✗» оставлены: так требует спецификация,
    а тест кабинета прямо относит галочки к типографским знакам, не к эмодзи.

### P3
1. «17 сентября в 02:19» при 12:xx по Москве: код показывал дату в часовом поясе браузера
   (`toLocaleString` без `timeZone`), а сервер присылал `played_at` = «сейчас» на каждом вызове finish.
   Снимок был из браузера в UTC−7 (похоже на облачную автоматизацию). Теперь `played_at` — момент
   сохранения результата; показ остаётся в поясе зрителя, как требует спецификация (тест с
   Владивостоком и Лос-Анджелесом).
2. «Итоговый счёт 6» при итоге 52: счётчик набегает кадрами `requestAnimationFrame`, в фоновой или
   скрытой вкладке кадры не идут — число застывало. Итог теперь ставится ещё и таймером через 850 мс.
3. Рекорд считался тремя правилами: чип на раунде и `CFG.my_best` — все раунды, кроме брошенных;
   «Моя статистика» и «Мои рекорды» — все раунды вместе с брошенными; плашка итога — `localStorage`
   браузера по любому раунду (у гостя, по набору, с фильтром). Сведено к одному: лучший ЗАЧЁТНЫЙ
   раунд режима (`leaderboard.record_runs`).
4. У вызова дня `share.set.board_url` вёл на доску набора, а не на доску дня — исправлено.
5. «В игре»: в `GameResult` нет длительности и прибавки, `wall_ms` включает отсчёт и паузы — время
   считает клиент по своему таймеру (запас + прибавка − остаток), подпись «2:00 + 45 с за верные».
6. Сводка знала три группы сложности (пончик) — добавлены полоски по звёздам `stars` (эффективная
   сложность) и очки по темам `topic_rows[].points` для «Где набрано».
7. Клиент собирал в разбор только ошибки — теперь и пропуски, с ответом игрока и верным ответом
   (верный сервер присылает и у пропуска).
8. Дуэль: автор не видел сравнения (пара «автор + я»); подмена «первый сыгравший» подписывала
   соперника вызвавшим, если автор ещё играл; «150 вопр.» шло из `gset.size`; «Реванш» и «Бросить
   вызов дальше» были ссылками на `duel_new`, который вошедшему отвечает JSON-ом.
9. Лобби жило на странице игры поверх скрытых зон старта — теперь зоны не отдаются вовсе, а код
   старта получает пустышки через `$` (48 элементов главной, 75 обращений; править каждое рискованнее).
10. Запрет начать раунд дуэли без соперника по-прежнему только в интерфейсе (карточка 81d4 в
    Notion «Надо»): в списке промпта для P3 её нет, отмечено ценой в ADR 0112.
11. Живое табло «связь потеряна и 0» — только диагностика по коду, находки в карточке Notion.
12. Браузерная проверка синхронной дуэли требует PostgreSQL; локально есть Homebrew PostgreSQL 17 —
    прогнан `test_browser_duel_sync` и `test_browser_lobby` на `config.settings_test_pg` (зелёные).

## Решения по ходу

### P1
- Сессия автономна (сообщение владельца 17.09): развилки решаю сам, записываю сюда.
- «Как считаются очки» — поповер с числами из конфига (`score_rules`), знак «?» с подсказкой убран.
- Панель «Мои рекорды» открывается окном (`#records-modal`) со вкладки «Статистика»: в карточке 440 px
  таблицы панели не читаются, а под полосой её не видно без прокрутки.
- «Сбросить всё» у строки фильтров оставлен (функция «снять фильтр без окна» сохраняется).
- Пометки «Без фильтров: ×1,3» и «С фильтрами: множителя не будет» убраны из-под фильтров: про ×1,3
  говорит поповер; под строкой остаётся только «Раунд тренировочный: в таблицу не идёт».
- Своя строка «Вы · имя» внизу таблицы показывается всегда, когда она есть (как в макете ученика).
- Снизу у экрана 84 px: кружок Telegram (53 + 16 px) не ложится на ячейки полосы.
- Enter на кнопке или ссылке (кроме вкладки и «Играть») нажимает её саму, а не запускает раунд;
  клавиши с Cmd/Ctrl/Alt отданы браузеру (Cmd+F, Ctrl+1).
- На странице набора Enter нажимает «Играть» карточки набора; в лобби дуэли — ничего.

### P2
- Размытие под окнами раунда оставлено: пока часы стоят, вопрос под окном не читается (анти-чит).
- Зелёная плашка «Верно, +N с.» сделана (в спецификации «по желанию») на прежних задержках.
- Разбор в дуэли — с той же серверной паузой: архитектура позволяет, табло соперника вычитает паузы.
- Раунд по набору и раунд без ответов сервер с `reason='quit'` не сохраняет (400 `quit_not_saved`) —
  вторая линия защиты «попытка набора не сгорает», первая — клиент.
- Брошенный раунд не рекорд: `.exclude(ended_reason='quit')` в `best_run` и `best_scores`, иначе
  текст окна «в таблицу и рекорды не пойдёт» был бы неправдой. «Моя статистика» его считает, как
  любой незачётный.
- Дуэль, выход крестиком: логика не менялась (стоп-гейт A, п. 4), окно говорит честно «Результат не
  сохранится: на странице дуэли останется только результат соперника».
- Клик в любом месте экрана раунда во время разбора — «дальше сразу» (макет телефона «Тап по экрану —
  сразу»), кроме звука, выхода, «Плохой задачи» и реакций.
- Экран практики в P2 не перестраивался (фаза P5): работает на новом каркасе, тесты практики зелёные.

### P3
- Правило рекорда — только зачётные раунды (см. факт 3): иначе «личный рекорд» рядом с «Не в таблице».
  У гостя плашки рекорда на итоге нет; рекорды устройства остаются на стартовом экране.
- «Верных 9 из 11» — верные из ответов (без пропусков), рядом точность и число пропусков: у сервера
  точность считается без пропусков, и «9 из 14 · 64 %» макета противоречило бы его же проценту.
- Столбец действий 356 px вместо 320: кнопки в доме 700, «Работа над ошибками · 10 вопросов · 2 темы»
  в 320 px обрезалась.
- Подпись кривой — сырые очки, при поправке на точность «623 · ×0,63 → 395»: крупный итог и кривая
  иначе противоречили бы друг другу.
- «Последние раунды» и «Против себя обычного» — от двух раундов в режиме (история включает этот).
- «Разделы»: тема вне разделов не считается; разделы без вопросов — строкой «Не было в этом раунде».
- Блок «Чисто! Ошибок нет» снят — в макете его нет, «Работа над ошибками» просто не показывается.
- Enter на итоге жмёт основную кнопку (у вызова дня — доска, у дуэли — итог дуэли), а не «ещё раз».
- «Ещё раз» у набора учителя, пока есть попытки, начинает тот же набор.
- Имена на страницах дуэли — логины (страница публичная); вердикт «Победа за <логин>» без рода.
- «Разобрать свои ошибки (N)» на странице дуэли ведёт на публичную страницу своего результата.
- «Бросить вызов другому» — `/game/?duel=<режим>` (окно создания; фильтр не переносится).
- Лобби: у соперника ссылка «Не сейчас – в обычную игру»; отмены дуэли на сервере нет, «Отменить
  дуэль» у автора — переход на главную игры.
- Больше двоих сыграло дуэль — остальные строкой «Ещё сыграли» под сравнением.

## Зубастость

| Фаза | Тест | Как ломал | Покраснел? |
|---|---|---|---|
| P1 | test_three_zones_for_a_guest | класс ячейки «Играть по коду» испорчен | да |
| P1 | test_what_the_owner_removed_is_gone | вернул класс rush-head на заголовок | да |
| P1 | test_mode_without_questions_has_no_tab | сервер рисует вкладку и режиму без вопросов | да |
| P1 | test_tab_caption_is_duration_and_pool | «мин» → «минут» в подписи | да |
| P1 | test_guest_sees_login_line_under_the_board_and_no_quota | другая строка гостя под таблицей | да |
| P1 | test_student_sees_quota_stats_and_records_button | квота скрыта у вошедшего | да |
| P1 | test_how_points_popover_takes_numbers_from_config | в поповере зашито 25 вместо конфига | да |
| P1 | test_guest_line_has_no_streak_and_no_played | гостю «сыграно 0 из 4» | да |
| P1 | test_student_with_one_played_daily_today | сыграно N+1 | да |
| P1 | test_reset_moment_comes_from_the_server | пустой data-reset-at | да |
| P1 | test_unknown_code | неизвестный код → exists=true | да |
| P1 | test_set_code_leads_to_the_set_page_case_and_spaces_ignored | код без нормализации | да |
| P1 | test_duel_code_leads_to_the_duel_page | дуэль ведёт на /game/s/ | да |
| P1 | test_many_misses_from_one_address_are_slowed_down | промах не пишется в лестницу | да |
| P1 | test_empty_code_is_not_a_miss | пустой код считается промахом | да |
| P1 | test_best_scores_per_mode_for_the_student | рекорды без фильтра версии экономики | да |
| P1 | test_page_config_carries_best_and_quota_only_for_the_student | гостю my_best не пуст | да |
| P1 | test_quota_is_counted_per_mode_for_today | квота пишется в один режим | да |
| P1 | test_digits_select_a_mode_and_do_not_start | цифра стартует раунд | да |
| P1 | test_f_opens_the_filter_window_and_modifiers_are_left_to_the_browser | убрана проверка Cmd/Ctrl/Alt | да |
| P1 | test_tab_click_only_selects | клик по вкладке стартует | да |
| P1 | test_medals_for_places_one_to_three | медали только у 1–2 | да |
| P1 | test_board_follows_the_selected_mode | доска не перезапрашивается при смене режима | да |
| P1 | test_code_is_checked_without_leaving_the_page | код уводит на /game/s/ | да |
| P1 | test_mode_and_duel_from_the_address | адрес не чистится | да |
| P1 | test_tokens_exist_in_both_themes | нет --on-accent в тёмной | да |
| P1 | test_no_hex_colours_in_the_start_markup | хекс в разметке старта | да |
| P1 | test_time_left_to_moscow_midnight_is_drawn_not_computed | остаток считается по часам браузера | да |
| P1 | test_nothing_played | best +1 | да |
| P1 | test_chain_up_to_yesterday_is_kept_until_midnight | серия только от сегодня | да |
| P1 | test_a_gap_of_one_day_resets | цепочка не рвётся на пропуске | да |
| P1 | test_two_challenges_on_one_day_are_one_day | сыграно считает дни, а не вызовы | да |
| P1 | test_round_saved_after_midnight_counts_for_its_set_day | день по created_at, а не по набору | да |
| P1 | test_week_is_monday_to_sunday_with_today_marked | неделя с воскресенья | да |
| P1 | test_anonymous_has_no_streak_and_no_errors | аноним уходит в запрос | да |
| P1 | test_one_query_per_user | второй запрос в streak_for | да |
| P1 | StartScreenBrowserTest: key1_selects_not_starts | цифра стартует раунд (браузер) | да |
| P1 | StartScreenBrowserTest: three_medals_then_number | медали только у 1–2 (браузер) | да |
| P1 | StartScreenBrowserTest: guest_no_vscroll_1440x800 + student_no_vscroll_1440x800 | min-height 900 px | да |
| P1 | StartScreenBrowserTest: wrong_code_stays | неверный код уводит на /game/s/ (браузер) | да |
| P1 | StartScreenBrowserTest: url_duel_guest_sees_account_window + url_duel_student_opens_create_window | ?duel= не открывает окно | да |
| P1 | StartScreenBrowserTest: f_opens_filters | F не открывает фильтры | да |
| P1 | StartScreenBrowserTest: board_follows_mode | доска не следует за режимом (браузер) | да |
| P1 | StartScreenBrowserTest: guest_stats_tab | нет контейнера рекордов гостя | да |
| P1 | StartScreenBrowserTest: four_mode_tabs | пятая вкладка без вопросов | да |
| P1 | StartScreenBrowserTest: four_band_cells | ячейка «Вызов дня» скрыта | да |
| P1 | StartScreenBrowserTest: enter_starts_one_round | Enter стартует дважды | да |
| P1 | StartScreenBrowserTest: url_mode_selects_rapid | ?mode= не выбирает режим | да |
| P1 | StartScreenBrowserTest: wrong_code_message_clears_on_input | строка ошибки не гаснет при вводе | да |
| P1 | StartScreenBrowserTest: duel_code_goes_to_duel_page | код дуэли на /game/s/ (браузер) | да |

P1: 50 дефектов, 50 красных. Раннер — `scratchpad/teeth.py` (дефект → прогон одного теста → `git checkout`).
Первый прогон `mb_code` покраснел ошибкой раннера, а не проверкой: раннер переписан (замер без падения
на чужой странице, проверка кода дуэли записывается и когда до неё не дошли) — после этого красный
именно на `wrong_code_stays`.

| Фаза | Тест | Как ломал | Покраснел? |
|---|---|---|---|
| P2 | test_student_quit_with_an_answer_is_saved_unranked | _rank_run без проверки «раунд брошен» | да |
| P2 | test_guest_quit_is_saved_with_the_first_reason_anonymous | проверка «брошен» раньше «аноним» | да |
| P2 | test_quit_without_a_single_answer_saves_nothing | сервер сохраняет брошенный раунд без ответов | да |
| P2 | test_quit_from_a_set_keeps_the_attempt | убрана проверка set_code — раунд набора сохраняется | да |
| P2 | test_quit_is_the_second_reason_right_after_anonymous | quit третьим пунктом, после mistakes_run | да |
| P2 | test_a_quit_round_is_not_a_record | best_run считает брошенный рекордом | да |
| P2 | test_a_quit_round_is_not_a_record | best_scores считает брошенный рекордом | да |
| P2 | test_closed_pause_is_not_spent_time | seconds_left_for не вычитает паузу | да |
| P2 | test_an_open_pause_counts_up_to_now | открытая пауза не считается | да |
| P2 | test_pause_credit_has_the_same_ceiling_as_ranking | без потолка 120 с | да |
| P2 | test_question_carries_its_effective_difficulty | сложность не уходит с вопросом | да |
| P2 | test_page_config_has_reveal_and_countdown_numbers | reveal_wrong_ms не уходит в CFG | да |
| P2 | test_wrong_answer_pauses_and_the_end_of_reveal_resumes | разбор без вызова паузы | да |
| P2 | test_practice_has_no_pause | практика ставит паузу | да |
| P2 | test_keys_during_reveal_do_not_answer | цифра на разборе зовёт answer | да |
| P2 | test_timer_is_minutes_and_seconds | секунды в таймере вместо m:ss | да |
| P2 | test_record_chip_only_with_a_record_and_never_for_practice | чип рекорда в практике | да |
| P2 | test_site_header_is_hidden_while_playing | класс rush-playing не ставится | да |
| P2 | test_option_grid_keeps_the_number_in_its_own_column | align-items: center у варианта | да |
| P2 | test_countdown_before_a_single_round_but_not_a_duel | старт без отсчёта | да |
| P2 | test_old_scoreboard_and_hint_are_gone_from_the_round | вернул строку-подсказку keys-hint | да |
| P2 | test_eight_duel_reactions_with_text_labels | семь подписей реакций | да |
| P2 | test_escape_opens_the_quit_window | Esc не открывает окно выхода | да |
| P2 | test_quit_run_saves_only_a_round_without_a_set | quitRun → show('start') без финиша | да |
| P2 | test_quit_dialog_texts_by_kind | «незачётный» в окне набора | да |
| P2 | test_all_windows_are_one_family | «Раунд прервался» своим классом | да |
| P2 | RoundBrowserTest: countdown_holds_question_and_clock | старт без отсчёта (браузер) | да |
| P2 | RoundBrowserTest: enter_skips_countdown | Enter не пропускает отсчёт: ни клавиша, ни фокус на карточке | да |
| P2 | RoundBrowserTest: blitz_five_options_no_scroll | шапка сайта на раунде снова видна — низ раунда уезжает за экран | да |
| P2 | RoundBrowserTest: timer_is_m_ss | секунды в таймере (браузер) | да |
| P2 | RoundBrowserTest: site_header_hidden | шапка не скрывается | да |
| P2 | RoundBrowserTest: option_grid_three_columns | пятый вариант в одну колонку | да |
| P2 | RoundBrowserTest: guest_has_no_record_chip | чип рекорда у гостя | да |
| P2 | RoundBrowserTest: digits_do_not_answer_during_reveal | обе защиты сняты: ветка разбора пропускает цифры и ввод на разборе открыт | да |
| P2 | RoundBrowserTest: reveal_pause_to_resume_3000ms | разбор без вызова паузы (браузер) | да |
| P2 | RoundBrowserTest: space_ends_reveal_early | пробел не завершает разбор | да |
| P2 | RoundBrowserTest: student_record_chip | другой текст чипа рекорда | да |
| P2 | RoundBrowserTest: mobile_reveal_no_side_scroll_targets_44 | «−1» справа от сердец на телефоне | да |
| P2 | RoundBrowserTest: mobile_reveal_no_side_scroll_targets_44 | нижние кнопки 34 px на телефоне | да |
| P2 | RoundBrowserTest: answer_waits_for_prefetch (раннер) | подкачка мимо очереди | да |
| P2 | RushModalPauseBrowserTest: escape_opens_quit_and_pauses | Esc не открывает окно выхода (браузер) | да |
| P2 | RoundBrowserTest: classic_600_chars_no_scroll + blitz_five_options_no_scroll | над карточкой 700 px — столбец вопроса уходит под полосу (Классика и Блиц) | да |

P2: 42 дефекта, 42 красных. Первый проход дал 36 из 42; остальные шесть разобраны, и три проверки
пришлось усилить, а не дефект подогнать:
- `enter_skips_countdown` проходила бы и без Enter (отсчёт кончается сам) — теперь меряет, что вопрос
  появился быстрее 700 мс; и Enter у отсчёта два пути (клавиша и фокус на карточке-кнопке), дефект
  снимает оба;
- «помещается» (Блиц, Классика) видела только прокрутку, а у раунда на ПК её нет по устройству
  (`overflow: hidden`): переполнение уходило вверх под полосу, а фокус в поле ответа сдвигал и саму
  полосу. Теперь проверки требуют полосу у верхнего края, строку над карточкой ниже полосы, последний
  вариант, поле ответа и нижний ряд в окне;
- раннер падал на жёстких ожиданиях раньше проверки (`b_countdown`, `b_queue`) — ожидания мягкие;
- `m_esc` был красным с первого раза: unittest сократил строку, по которой искал раннер зубастости.

| Фаза | Тест | Как ломал | Покраснел? |
|---|---|---|---|
| P3 | test_stars_split_outcomes_by_effective_difficulty | звёзды без разбивки по исходам | да |
| P3 | test_topic_rows_carry_the_points_of_their_questions | очки по темам — ноль | да |
| P3 | test_ranked_student_gets_places_and_beats_the_previous_record | место за неделю не отдаётся | да |
| P3 | test_a_lower_score_is_not_a_record | любой раунд — рекорд | да |
| P3 | test_unranked_record_does_not_count_as_the_previous_best | прошлый рекорд и по незачётным | да |
| P3 | test_unranked_round_has_no_places_and_no_record | места и рекорд у незачётного раунда | да |
| P3 | test_played_at_is_the_saved_moment | дата — момент вызова finish | да |
| P3 | test_daily_leads_to_the_day_board_with_place_streak_and_next | у вызова дня доска набора | да |
| P3 | test_teacher_set_says_how_many_attempts_are_left | попытки не вычитаются | да |
| P3 | test_duel_knows_whether_the_rival_has_played_and_how_to_rematch | соперник всегда «не отыграл» | да |
| P3 | test_without_ranked_rounds_there_is_no_record_anywhere | рекорд по всем раундам | да |
| P3 | test_the_record_ignores_a_higher_unranked_round | линия рекорда по всем раундам | да |
| P3 | test_history_average_has_correct_and_skipped_per_round | «обычно пропусков» — ноль | да |
| P3 | test_one_round_flow_card_instead_of_nine_charts | вернул карточку «Лента ответов» | да |
| P3 | test_actions_sit_in_the_verdict_card | у «ещё раз» нет Enter | да |
| P3 | test_mistakes_are_a_list_on_the_page_not_behind_a_toggle | список ошибок спрятан | да |
| P3 | test_empty_cards_are_hidden_instead_of_saying_nothing | пустая «Где набрано» видна | да |
| P3 | test_the_topic_layout_is_not_copied_a_second_time | разделы литералом в коде | да |
| P3 | test_charts_are_still_hand_drawn_svg_through_tokens | цвет кривой не токеном | да |
| P3 | test_local_storage_history_is_gone_entirely | история не с сервера | да |
| P3 | test_record_badge_comes_from_the_server_rule | плашка рекорда по localStorage | да |
| P3 | test_first_action_by_kind_of_round | у вызова дня «ещё раз» | да |
| P3 | test_enter_presses_the_primary_action | Enter на итоге — всегда новый раунд | да |
| P3 | test_score_counter_always_lands_on_the_total | счётчик без страховки таймером | да |
| P3 | test_date_is_the_saved_moment_in_the_viewers_time_zone | дата в поясе Москвы | да |
| P3 | test_misses_collect_wrong_answers_and_skips | пропуски не в разборе | да |
| P3 | test_quit_round_has_its_own_title | брошенный раунд — «Время вышло!» | да |
| P3 | test_accuracy_note_takes_the_threshold_from_config | порог точности литералом | да |
| P3 | test_every_helper_the_final_screen_calls_is_defined | удалён помощник numText | да |
| P3 | FinalBrowserTest: score_and_first_action_above_800 | столбец действий уехал в конец страницы | да |
| P3 | FinalBrowserTest: misses_listed_without_a_click | ошибки скрыты | да |
| P3 | FinalBrowserTest: student_compares_with_history | сравнение с историей не рисуется | да |
| P3 | FinalBrowserTest: zero_points_no_points_card | пустая «Где набрано» видна (браузер) | да |
| P3 | FinalBrowserTest: guest_login_line_instead_of_history | гостю нет строки входа | да |
| P3 | FinalBrowserTest: date_in_the_viewers_time_zone | дата в поясе Москвы (браузер) | да |
| P3 | FinalBrowserTest: mobile_final_no_side_scroll | на телефоне вердикт в две колонки | да |
| P3 | test_author_sees_the_comparison_too | старое условие mine.id != author_result.id | да |
| P3 | test_one_result_says_the_rival_has_not_come_and_has_no_table | ожидание без строки «не пришёл» | да |
| P3 | test_rival_waiting_for_an_author_who_is_still_playing | «играет» по закрытому забегу | да |
| P3 | test_no_queue_size_on_any_view | вернул «150 вопр.» | да |
| P3 | test_invitation_for_a_guest_and_a_signed_in_rival | гостю «Принять вызов» | да |
| P3 | test_each_row_highlights_at_most_one_cell | равные значения выделяются | да |
| P3 | test_win_for_the_viewer | смотрящему не «Вы победили» | да |
| P3 | test_loss_seen_by_the_rival_on_the_left | соперник не слева | да |
| P3 | test_draw_seen_by_a_third_person | ничья — победа левого | да |
| P3 | test_lobby_is_a_page_without_the_start_screen_behind | главная снова позади лобби | да |
| P3 | test_lobby_says_terms_and_shows_two_slots | «3» без «жизни» | да |

P3: 47 дефектов, 47 красных. Первый проход дал 44 из 47; три проверки пришлось усилить, дефекты не
менял:
- `test_played_at_is_the_saved_moment` сравнивал даты двух finish в одну и ту же секунду — теперь
  результат «сохранён» час назад, и повторный finish обязан отдать тот момент;
- `test_charts_are_still_hand_drawn_svg_through_tokens` находил токен у кружка кривой и не видел,
  что линия нарисована литералом, — теперь все `stroke`/`fill` рисунка обязаны быть токенами;
- `test_every_helper_the_final_screen_calls_is_defined` искал только вызовы со скобками, а
  `numText`/`secText` передаются значением в строки «Против себя обычного» — теперь видит и их.

## Числа тестов

| Когда | Набор | Тестов | Итог |
|---|---|---|---|
| Фаза −1, до правок | game + olympiads.tests.test_views + test_training | 867 | failures=1 (устаревший браузерный тест), skipped=1 |
| Фаза −1, после починки теста | game.tests.test_browser_modals | 1 | OK |
| P1, после фазы | game + config.tests.test_nav + problems.tests.test_stats_cards/test_obzor_nav/test_palette_tokens | 931 | OK (skipped=1) |
| P1, новые тесты | game.tests.test_start_layout (+ браузерный StartScreenBrowserTest, 16 проверок) | 38 + 1 | OK |
| P2, после фазы | `scripts/run_tests.py game problems.tests.test_obzor_nav problems.tests.test_stats_cards`: шаг A / шаг B | 913 / 7 | OK / OK (skipped=1: браузерная синхронная дуэль идёт только на PostgreSQL) |
| P2, новые тесты | game.tests.test_round (+ браузерный RoundBrowserTest, 14 проверок) | 25 + 1 | OK |
| P3, до правок | test_duel, test_duel_sync, test_duel_ws, test_game, test_leaderboard, test_wecon_texts | 314 | OK |
| P3, после фазы | game без браузерных | 900 | OK |
| P3, новые тесты | test_final 13, test_final_screen 17, test_duel_page 9, DuelLobbyTests +2 (+ браузерный FinalBrowserTest, 7 проверок) | 41 + 1 | OK |
| P3, PostgreSQL | test_browser_duel_sync + test_browser_lobby на `config.settings_test_pg` (локальный PostgreSQL 17) | 2 | OK |

## Удалено

### P1 (всё осталось в git до коммита P1)
- Разметка старта: большой знак `header.rush-head` с лозунгом «Решайте тестовые задачи…» и строкой
  «N вопросов из реальных олимпиад»; колонки `.start-cols`; заголовок «Лидерборд» со знаком «?»
  (`_hint.html`) и ряд режимов `#lb-modes`; секция `#ms-card`; полоса `.practice-band`; нижний ряд
  `.entry-row` (плитки `#entry-daily`, «Играть по коду», `#entry-duel`, `#entry-records`);
  `#filter-open` «Добавить фильтры» и `#filter-chips` на старте (в окне дуэли остались); строка
  квоты; встроенная панель `#records-box` (стала окном).
- Подключение `_hint_js.html` на странице игры (подсказок «?» на ней больше нет).
- CSS: `.rush-head/.rush-sub/.rush-count`, `.mode-grid/.mode-card/.mode-name/.mode-kind/.mode-terms/
  .mode-best/.mode-avail`, старые `.mode-mock/.mock-*`, `.filter-reset`, `.filter-note.unranked`,
  `.start-cols/.start-left/.start-right`, `.lb-card/.lb-head/.lb-tabs/.lb-tab/.lb-seg`,
  `.k-hintmark/.k-tip`, `.lb-login`, `.entry-row/.entry/.entry.soon`, `.records-box .rec-row`,
  `.practice-band/.practice-text/.practice-count/.practice-go`.
- JS: `renderModeCards`, `visibleModes`, ряд режимов в `paintBoardControls`, `markSoon`,
  `isUnfiltered`, клик `#entry-daily`, переключатель `#entry-records`, две пометки про ×1,3.
- Сервер: `_quota_line` (→ `_quota_payload`), ключ контекста `pool_total` (лишний запрос).

### P2 (всё осталось в git до коммита P2)
- Разметка раунда: табло `.vs` целиком (`#vs`, `#vs-me`, `#vs-my-*`, лента ответов `#vs-my-tape`,
  `#vs-them*`, разрыв `#vs-gap*`), строка-подсказка `#keys-hint` про клавиши, `#combo-toast`,
  прежнее окно выхода «Закончить игру? Результат не сохранится.» с «Нет/Да», текст «Раунд потерян ·
  Соединение или время ожидания. Начните новый.»
- CSS: `.vs/.vs-side/.vs-side--off/.vs-row/.vs-score/.vs-who/.vs-state/.vs-lives/.vs-tape/.vs-empty/
  .vs-gap/.vs-gap-num/.vs-gap-note`, `.keys-hint`, `.combo-toast`, `.duel-flyer`, `.go-card`,
  `.timer-box`, `.hud-timer` (секунды), `.numeric-actions`, `.q-chips`, `.quit-x`, `.sound-x`,
  `.report-row`.
- JS: `tapeHtml` (лента последних ответов), `skipLabel`; прямые цепочки `pauseSync.then(...)`
  (стали очередью `queueRun`).
- Текстовые знаки «✕» у выхода и закрытия окна фильтров, «✓» в «Ссылка скопирована».

### P3 (всё осталось в git до коммитов P3)
- Разметка итога: шапка `fin-head`, метрика «Итоговый счёт», блок «Работа над ошибками» с полосой и
  легендой, «Чисто! Ошибок нет», список «Точность по темам», «Подробная статистика» с девятью
  `chart-card` («Ход раунда», «Сколько думали», «Держите ли сложное» пончиком, «Последние раунды»,
  «Лента ответов», «Время на ответ», «Где набрано», «Микро и макро», «Против себя обычного»), блок
  «Поделиться результатом», нижний ряд «Доска набора», «Разобрать все ошибки», «Перейти к темам в
  каталоге», раскрывашка списка ошибок.
- CSS итога: `.fin-head/.fin-sub/.fin-chip-alt/.fin-date/.metric*/.acc-note/.record-badge/.fin-mistakes/
  .fm-*/.fin-clean/.link-btn/.fin-topics/.tp-*/.det-body/.chart-card/.chart-key/.k-combo/.chart-x/
  .chart-lbl/.chart-donut/.donut-legend/.d-easy/.d-medium/.d-hard/.fin-share/.share-lead/.share-row/
  .final-actions/.btn-again/.btn-copy/.btn-board/.fin-chip-set/.miss-empty/.usual-*`; чипы фильтров
  `.filter-bar/.filter-open/.filter-chips/.fchip`; старые `.dm-step/.dm-mode b/small/.dm-count`.
- JS: `segAlpha`/`SEG_ALPHA`, `paintMistakes`, `paintClean`, прежние `paintTopics`/`paintMisses`/
  `paintShare`, `chartEmpty`, `chartTime`, `chartDifficulty`, `chartHistory`, `chartTape`, `chartTimes`,
  `chartPoints`, `chartGroups`, `chartUsual`, `buildCompareCharts`, `buildCharts`, `DIFF_COLOR`,
  рекорд по `localStorage` (`isRecord`, `bestNow`), `chipBoxes` и чипы фильтров с «×», подписи
  «Добавить фильтры» / «Изменить фильтры».
- Страница дуэли: заголовок «<автор> бросает вызов», «N вопр.», кнопка-заглушка «Попытка уже
  использована», подсветка столбца победителя, полоса на весь запас очереди, блок «Скопировать
  ссылку-приглашение», таблица всех сыгравших (осталась строка «Ещё сыграли»).
- Лобби: узкая карточка 520 px, видимая строка «Ждём соперника…» / «Соперник: …» (осталась
  невидимой для теста синхронного старта), «Отменить» (стало «Отменить дуэль»).
- Тесты: класс `NineChartsTests` (проверки перенесены в `test_final_screen.py`),
  `test_clean_badge_requires_at_least_one_correct_answer`, `test_chips_have_a_cross_and_reset`.

## ADR этого прогона

- 0108 — главная Wecon Rush: «стартовый экран аркады» (P1)
- 0109 — разбор неверного ответа: три секунды при стоящих часах (P2)
- 0110 — экран раунда: одна полоса HUD, шапка сайта скрыта (P2)
- 0111 — итог раунда: вердикт и действия сверху, один «Ход раунда», ошибки на странице (P3)
- 0112 — дуэль: лобби отдельной страницей, приглашение, одно сравнение для обоих (P3)
