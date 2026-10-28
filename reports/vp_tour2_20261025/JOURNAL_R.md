# Журнал: тренажёр 2 тура ВП, сессия R (R1 + R1b + R2 + R3), с 28.10.2026

Промпт — `~/Downloads/PROMPT_VP_TOUR2_R_20261028.md` (вставлен в чат, сохранён туда же
Claude Code для повторных запусков). Работа — в worktree
`.claude/worktrees/vp-tour2-20261025`, ветка `feat/vp-tour2-20261025`, поверх `6d9389d9`.
Пуша и вливания в `main` нет.

## Фаза −1. Сверка с реальностью — ЗАКРЫТА (запуск 1, 28.10)

| Проверка | Факт |
|---|---|
| worktree `.claude/worktrees/vp-tour2-20261025` | есть |
| Ветка, дерево | `feat/vp-tour2-20261025`, чистое; после `git fetch` `HEAD` = `origin/…` = `6d9389d9` |
| Другая сессия в worktree | нет (чужих правок нет) |
| Макеты | `~/Downloads/vp_tour2_mockups_20261028.zip` → `claude/mockups/vp_tour2_20261028/`: `README.md`, `screens/` 10 PNG, `html/` 10 HTML + `vp.css` + `ds/`, `source/` 8 `.dc.html`; коммит `d10c7ae0` |
| Демоверсии в локальной базе | 3 опубликованных варианта 2 тура: 9 — 17, 10 — 18, 11 — 18 заданий |
| Базовая линия базы | `VPAttempt` 2, `VPAnswer` 88 |
| `manage.py test vp` до правок | 416 тестов, OK, `skipped=1`, код 0 (53,6 с) |
| `rescore_vp --all --dry-run` | вариантов 13, сданных попыток проверено 2, «Изменений нет» |
| `node`, Playwright | `node` v24.16.0 есть; в worktree нет `node_modules/playwright` → `test_browser.py` пропускается (к тому же он идёт только на PostgreSQL) |

Notion прочитан: R1 `404b11c9…5224` (переведена в «В работе»), R2–R3 `404b11c9…02e8`, решение
`407b11c9…dedf`.

## Фаза 1. Подсчёт, правила, тексты условий — ЗАКРЫТА (коммит `04480c3a`)

* `vp/scoring.py`: `_LONG_MINUS` (U+2212, U+2012, U+2013, U+2014, U+FE63, U+FF0D); причина `minus`
  проверяется ПЕРВОЙ; `_soft_number` — единственное место мягкой починки; `canonical_number`
  (починка + округление до сотых `ROUND_HALF_UP`, не число → `None`); `_would_be_correct`
  переведён на них (сверка с `accepted` — и до округления, и после, как раньше «3,125»).
* `vp/review.py::_number_fix`: `minus` → «-»; совет только если исправленное проходит
  `NUMBER_FORMAT` (для «−25 000» и «37.5.1» — пусто).
* `result.html`: строка причины `minus`; у `dot`/`space` без совета «Нужно …» не пишется.
* `_rules.html`: «Как вводить число» начинается с «Без апелляции: …», повтор «0 баллов, как на
  туре» убран, в «Неверно» добавлено «−318». Ссылка на тренировку — в фазе 8.
* `vp_extras.nbsp_num` (вне формул) подключён к условию, кускам пропусков, вариантам, строкам
  соотнесения, решениям, определениям змейки — в прохождении, разборе и «Дорешать»
  (`_practice.html` получил свой `{% load vp_extras %}`: include тегов не наследует).
* YAML: демо 10 №16, демо 11 №15 — `2 \\cdot M/P`. `--dry-run`: 9 — «Изменений нет», 10 — «№16:
  изменены поля statement», 11 — «№15: изменены поля statement». Загружено `--publish`,
  повторный `--dry-run` — «Изменений нет» у обоих, 3 варианта 2 тура опубликованы (17/18/18).
* Тесты `vp/tests/test_r_scoring.py` (6): таблица из 8 строк + все шесть знаков, `canonical_number`
  (11 строк), `nbsp_num`, строка разбора владельцу / её нет у чужого.
* `manage.py test vp`: 416 → 422, OK (`skipped=1`). `rescore_vp --all --dry-run` — 2 попытки,
  «Изменений нет». Длинных тире в изменённых шаблонах — 0.

Изменённые старые тесты: нет.

| Дефект | Покраснело |
|---|---|
| проверка `minus` убрана из `_format_error` | `test_every_long_minus_sign_is_minus`, `test_owner_sees_long_minus_reason_and_fix` |
| `_number_fix` без проверки `NUMBER_FORMAT` | `LongMinusTableTests.test_table` (−25 000, 37.5.1) |
| `canonical_number` без округления | `CanonicalNumberTests` (1,607, 3,125, −0,125) |
| `nbsp_num` трогает формулы | `NbspNumTests` |
| ветка `minus` в `result.html` выключена | `test_owner_sees_long_minus_reason_and_fix` |
| `_soft_number` не меняет длинный минус | `CanonicalNumberTests`, `test_every_long_minus_sign_is_minus` |

## Фаза 2. Страница прохождения (макеты 06/07) — ЗАКРЫТА (коммит `ec7d05db`)

* Шапка: название (`with_band`, фильтр заведён здесь, в фазе 4 расходится по остальным
  экранам), «с таймером · ответы сохраняются сами», часы «69:58 осталось из 70:00» (минуты не
  переходят в часы: `clockText()` в `take.js`; общий `exam_timer.js` не тронут) и полоса
  остатка `#vp-timebar` (из того же остатка, что часы), «отвечено N из M», «✓ сохранено /
  сохраняем… / нет связи, повторим», «Сдать работу». Телефон — одна строка: часы «из 70:00»,
  «N из M», «Сдать»; кнопка темы и «сохранено» на телефоне скрыты (беда со связью видна).
* Навигация `#vp-grid` — группы по разделам («Все верные · 1–2», «Пропуски · 3», «Соотнесение · 4»,
  «Задачи с числом · 5–18»): `blocks.TITLES[…]['nav']`, номера из `blocks.sections`; легенда из 4 пунктов.
* Шапки разделов «Задание 4 · Соотнесение» + «9 баллов · каждая строка – своя доля» (одно задание —
  `points_word`, `blocks.SECTION_HOW`), числа — «по 5 баллов: полный балл или ноль».
* «±» `[data-pm]` (виден только при `(hover: none) and (pointer: coarse)`), меняет «-» и любой
  `_LONG_MINUS`, шлёт `input`, фокус в поле.
* Пропуски: `views._row['paras']` — абзацы (строки текста) с метками `a.vp-gapmark` (номер + слово,
  без JS слово из `word`) и списками под каждым абзацем (`vp-gaplist`, две колонки на широком).
* Соотнесение: `views.match_letters` («А – …» → буква и подпись, иначе по порядку), легенда,
  `.vp-abseg` с радиокнопками `name="item-N.k"` (`aria-label` «А – абсолютная бедность»);
  повторное нажатие снимает выбор (`take.js`, `segValue`). ⚠️ Имя `.vp-seg` занято экраном
  вариантов — поэтому `.vp-abseg` (найдено глазами: сегмент растягивался на всю ширину).
* «Вернуться позже» `[data-flag]` — плавает справа в начале текста задания (на телефоне — своей
  строкой); `localStorage` `vp:flags:<saveUrl>`, `is-flagged` у плиток, строка «Отмечены «вернуться
  позже»:» в окне сдачи, ключ удаляется при сдаче.
* Тесты `vp/tests/test_r_take.py` (5). `manage.py test vp`: 422 → 427, OK (`skipped=1`).

Изменённые старые тесты:
* `test_tour2_take.py::test_page_renders_all_items_and_new_kinds` — 4 списка `item-4.N` → 8 радиокнопок (промпт).
* `test_page.py::test_block_headings_and_points` — «Задания 1–30. Змейка» → «Задания 1–30 · Змейка», подпись баллов без ведущей «·» (новая шапка раздела); суть та же.
* `test_page.py` (3 места) и `test_take.py` (1) — счётчик: «отвечено » теперь в своём `<span>` (на телефоне скрыт); число и «из 44» проверяются как раньше.

Проверено глазами (браузерная панель, 1440×900 и телефон 375×812, вошедший): разметка как на 06/07,
выбор в списке меняет метку, «А» дважды — выбор снят и в базе у задания 4 нет ключа «1»
(`{3: {'1': 14}, 4: {'2': 2}}`), пометки 7 и 12 → черта у плиток и строка в окне сдачи, «±» ставит
и снимает «-» (и «−»), сдвига вбок нет. `browser_take.mjs` НЕ дополнен: в worktree нет
`node_modules/playwright`, тест пропускается — сценарий проверен руками в панели.

⚠️ Окружение для глаз: общая база не знает `problems.0079–0081` (вход падал на
`problems_consentrecord`), поэтому глазами смотрится КОПИЯ — `db_check.sqlite3` в worktree
(в `.gitignore`), `--settings=config.settings_check`, полностью смигрирована. Учётка проверки
`vp_r_check` / `vp-r-check-2810` заведена и в общей базе (без сигнала профиля: `bulk_create` +
строка профиля SQL — у общей базы `phone NOT NULL`), и в копии (там же согласие `pd`). В основной
папке в `.claude/launch.json` добавлена запись `vp-r` (порт 8466) — не закоммичена, это чужой файл.
Попытки в общей базе НЕ создавались (только в копии).

| Дефект | Покраснело |
|---|---|
| абзацы пропусков склеены в один | `test_demo_10_marks_lists_letters_and_plus_minus` |
| радиокнопки соотнесения → галочки | `test_demo_10…`, `test_demo_9_counts` |
| нет `data-pm` | `test_demo_10…`, `test_demo_9_counts` |
| подпись навигации `short` вместо `nav` | `test_demo_10…`, `test_demo_9_counts` |
| одно задание в шапке раздела — «по 9 баллов» | `test_section_heads` |
| метка без выбранного слова | `test_chosen_word_stands_in_the_mark_without_js` |
| сдача формой не читает `item-4.k` | `test_form_finish_with_radios_and_autosave_erase` |
| буквы не разбираются из «А – …» | `test_demo_10…` |
| нет флажка у пропусков | `test_demo_10…` (18 флажков) |

## Фаза 3. Класс ученика — ЗАКРЫТА (коммит `0f524000`)

* `vp/landing.py::student_band(request)` — единственный источник: `?band=` / `?board=` (известный код
  → `session['vp_band']`) → [место под анкету] → `session['vp_band']` → класс последней попытки в
  текущем туре → `None`.
* `views._boards` и `views.variants` берут класс из неё (иначе первый). POST `/vp/band/`
  (`vp:remember_band`, до `<slug>/`, CSRF; тело — код или поле `band`; известный → 204, иначе 400,
  тело длиннее 64 байт — 400); `landing.js` шлёт его при нажатии вкладки, ответа не ждёт
  (токен — `data-csrf` у списка вкладок).
* `landing.my_block`: «следующий вариант» и «пройдено» по своему классу; `band`, `band_label` →
  «Пройдено · 10 класс».
* `board.panel(me, tour, band)` — вкладка целиком, с `my_place` (моё место в этой таблице, в топе
  или нет); `board.top` теперь обёртка над ней (правило отбора одно).
* Таблица: колонка «Класс» только при одной таблице (1 тур), сетка `.is-nocls`; своя строка в топе
  подсвечена («Вы · логин»); подпись — «Вы на первом месте.» / «Ваше место – K-е; выше можно
  подняться…» / «Попыток в таблице: N.».
* Тесты `vp/tests/test_r_band.py` (5). `manage.py test vp`: 427 → 432, OK (`skipped=1`).
  Изменённых старых тестов нет.

| Дефект | Покраснело |
|---|---|
| явный выбор не запоминается | `test_explicit_choice_is_remembered` |
| нет класса из последней попытки | `test_tenth_grader…`, `test_unknown_band_is_refused` |
| `/vp/band/` принимает любой код | `test_unknown_band_is_refused` |
| «моё» не по своему классу | `test_tenth_grader_sees_tenth_grade_everywhere` |
| колонка «Класс» во 2 туре | `test_no_class_column_and_first_place_caption` |
| подпись «первое место» не выбирается | `test_no_class_column_and_first_place_caption` |
| экран вариантов по `?band=` без памяти | `test_explicit_choice…`, `test_tenth_grader…` |

## Фаза 4. Тексты и общие подписи — ЗАКРЫТА (коммит `13093f82`)

* `blocks.in_tasks(sections)` — одна фраза для интро и окна правил: слово по числу ЗАДАНИЙ,
  пара соседних номеров — «3 и 4». В данных формата и интро — `partial_phrase`, `share_phrase`
  (списки `*_ranges` остались для остального и для тестов 1 тура). Проверено на демо 9 и 10:
  10–11 — «В заданиях 1 и 2», «В заданиях 3 и 4»; 9 — «В заданиях 1–3», «В заданиях 4 и 5»;
  «Задачи 5–18» / «6–17» — как были.
* Окно правил: «Ответ в неверном формате – 0 баллов, как на туре» — один раз в «Как считаются
  баллы» (раньше — по разу на каждую группу классов, то есть дважды).
* «Мои попытки»: подзаголовок без змейки; у попытки скрытого тура (`visibility.tour_visible`)
  вместо «в таблице · N-е» — «архив», без галочки; название — `with_band`.
* `landing.variant_meta(variant, parts)` — «Демоверсия ВШЭ · 2026/27 · 18 заданий · 70 мин»
  (карточка) / `parts=('count', 'points')` — для интро (фаза 10). Гостю строки статуса нет.
* `with_band`: шапка результата, карточка вариантов, «следующий вариант» (там убран повтор класса),
  «Мои попытки», шапка прохождения, h1 интро (подзаголовок интро без класса).
* Тесты `vp/tests/test_r_texts.py` (4). `manage.py test vp`: 432 → 436, OK (`skipped=1`).

Изменённые старые тесты:
* `test_variants.py::test_05_guest_sees_the_format_and_no_status` — «44 задания · 30 минут» → «44 задания · 30 мин» (строка меты вместо строки статуса гостя; промпт).

| Дефект | Покраснело |
|---|---|
| нет «3 и 4» для пары соседних | `test_words_and_pairs`, `test_rules_dialog_phrases` |
| слово по числу диапазонов | `test_words_and_pairs`, `test_rules_dialog_phrases` |
| нет «0 баллов, как на туре» в «Как считаются баллы» | `test_rules_dialog_phrases` |
| нет «архива» у скрытого тура | `test_my_attempts_has_no_snake_and_marks_the_archive` |
| змейка в подзаголовке «Моих попыток» | `test_my_attempts_has_no_snake_and_marks_the_archive` |
| год без «/27» | `test_card_meta_and_band_once_on_result` |
| `with_band` всегда дописывает класс | `test_card_meta_and_band_once_on_result` |

**Конец запуска 1 по ориентиру промпта (фазы −1…4). Следующее — фаза 5.**

## Фаза 5. Результат: данные и «Показать ответ» — ЗАКРЫТА (коммиты `4330afd5`, `+1`)

* `review.format_losses(attempt)` → `points`, `items` (`number`, `given`, `fix` — `_number_fix` или
  эталон), `with_fix`, `number_lost` (всего недобрано в задачах с числом — для «Из N баллов…, M –
  запись ответа»). На фикстуре: 25 баллов, пять пар (9: 98.0 → 98,0; 11: -0.12 → -0,12; 13: 11 800 →
  11800; 14: 160 ед → 160; 17: 1,607 → 1,61), `with_fix` 30, `number_lost` 65.
* Строки `tests_review` += `status` (`ok`/`mid`/`fmt`/`bad`/`none`; `tone` не тронут), `lead` (начало
  условия без `[[k]]`), `given_text` / `right_text` («6 из 8 пропусков», «3 из 4 строк», «в разборе»,
  у неотвеченного «–» и пусто), `group`, `letters`, `shared` (общее условие у второй задачи группы);
  `match_rows` += `chosen_letter`, `right_letter`. `review.match_letters` перенесена из `views`
  (одна на прохождение и разбор). `review.STATUS_FILTERS`, `status_counts` → Все 18 / Ошибки 0 /
  Формат 5 / Без ответа 12 / Верно 1.
* `views.result` (только владельцу): `format_losses`, `status_filters`, `own_attempts` (свои сданные
  по варианту, «эта попытка»), `place` (`board.place_of`), `board_url` (`/vp/?board=10`),
  `invite_url` (`config.VP_INVITE_URL = ''`); `_mark_groups` по строкам разбора.
* `practice_check`: `{"item", "reveal": true}` → `{"right", "solution"}` без проверки; обычная
  проверка тоже отдаёт `solution`; охраны те же (владелец, сданная, ничего не пишет).
  `_practice.html` — кнопка «Показать ответ», `result.js` — `reveal()`, решение текстом +
  `renderMathIn`, событие `vp_practice_reveal`.
* Змейка 1 тура: `statement` у каждого слова.
* Тесты `vp/tests/test_r_review.py` (9). `manage.py test vp`: 436 → 444, OK (`skipped=1`).

Изменённые старые тесты:
* `test_review.py::test_stranger_gets_no_review_rows_in_the_context` — в список ключей, которых нет у чужого, добавлены `format_losses`, `status_filters`, `own_attempts`, `place`, `board_url` (промпт; проверка стала строже).
* `test_review.py::test_11_checks_on_the_fly_and_writes_nothing` и `test_tour2_review.py::test_number_gaps_and_matching_by_the_same_rules` — ответ `practice_check` теперь с `solution` (промпт: «расширь»).

| Дефект | Покраснело |
|---|---|
| потеря записи без `would_be_correct` | `test_wrong_number_in_wrong_format_is_not_a_format_loss` (сначала мутант ЖИЛ — тест добавлен) |
| `fix` без эталона | `test_format_losses_and_counters` |
| нет статуса `ok` | `test_format_losses_and_counters`, `test_rows_texts` |
| «Ошибки» считают и формат | `test_format_losses_and_counters` |
| решение неотвеченного в данных | `test_rows_texts` (сначала мутант ЖИЛ: шаблон его не печатал — проверка перенесена в данные) |
| верные варианты неотвеченного в данных | `test_rows_texts` |
| `reveal` не работает | `test_reveal_gives_answer_and_solution_and_writes_nothing` |
| `practice_check` по несданной | `test_reveal_is_for_the_owner_of_a_submitted_attempt_only` |
| определение только у пустых слов змейки | `test_answered_word_has_its_definition` |
| нет `shared` | `test_rows_texts` |
| нет места | `test_owner_side_column_data` |
