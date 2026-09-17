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
- [ ] P2 Раунд
  - [x] P2.0 Стоп-гейт A: анализ и план записаны (раздел «Стоп-гейт A» ниже)
  - [ ] P2.1 Сервер: разбор 3 с (константы), брошенный раунд `quit`, пауза в табло дуэли
  - [ ] P2.2 Полоса HUD, шапка скрыта, вопрос и варианты, нижний ряд
  - [ ] P2.3 Разбор ошибки 3 с при стоящих часах, отсчёт 3-2-1
  - [ ] P2.4 Служебные окна одной семьёй (выход, набор, «прервался», «нет связи», конец по жизням)
  - [ ] P2.5 ADR 0109/0110, GAME.md, тесты, зубастость, Notion
- [ ] P3 Итог и дуэль
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

## Числа тестов

| Когда | Набор | Тестов | Итог |
|---|---|---|---|
| Фаза −1, до правок | game + olympiads.tests.test_views + test_training | 867 | failures=1 (устаревший браузерный тест), skipped=1 |
| Фаза −1, после починки теста | game.tests.test_browser_modals | 1 | OK |
| P1, после фазы | game + config.tests.test_nav + problems.tests.test_stats_cards/test_obzor_nav/test_palette_tokens | 931 | OK (skipped=1) |
| P1, новые тесты | game.tests.test_start_layout (+ браузерный StartScreenBrowserTest, 16 проверок) | 38 + 1 | OK |

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

## ADR этого прогона

- 0108 — главная Wecon Rush: «стартовый экран аркады» (P1)
