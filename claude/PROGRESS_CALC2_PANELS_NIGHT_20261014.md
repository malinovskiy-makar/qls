# Графики: тихие панели — ночной прогон 14.10.2026, этапы А–Г (сессии 1–4 из 7)

Задание — `claude/mockups/calc2_panels_20261014/PROMPT_NIGHT.md` (совпадает с присланным в чат), правила —
README пакета. Ветка `feat/calc2-redesign`. Приборы — сервер 8099 (`--settings=config.settings_check`, с
автоперезагрузкой). Замеры «до» — на копии кода `9b2c3e54` (git worktree в папке сеанса, сервер 8098), чтобы правка
статики не попала в базу «до».

## Фаза −1. Сверка с реальностью — пройдена

- `caffeinate -is -t 57600` запущен в фоне.
- `git status` чистый, кроме папки пакета; ветка `feat/calc2-redesign`; на месте журнал
  `claude/PROGRESS_CALC2_FIXES_B_20261013.md` и ADR 0149. Пакет взят из `~/Downloads/calc2_panels_20261014.zip`
  (одна копия, в ней `PROMPT_NIGHT.md`), положен в `claude/mockups/calc2_panels_20261014/`, коммит `9b2c3e54`.
- Notion прочитан: решения …81de…, …81eb…, …8142…, …81d6…, (пересматриваемое) …812a…; задача-зонтик …8178… («Надо»);
  карточки …8196…, …8121…, …8169…, …81ec… (одна дискуссия); «Задачи» «В работе» и «Надо», 5 последних «Решений».
- `manage.py check` — 0 ошибок; `makemigrations --check --dry-run` — «No changes detected»; node 24.16;
  Playwright Chromium 151 и WebKit 26.5 запускаются.
- ADR: последний занятый 0149 (локально, `origin/main` и все ветки) → свободны 0150, 0151, 0152.
- Опись «до»: `claude/panels_night/A_before.json` (42 модели); сверка с `data/inventory_a95cae66.json` —
  **расхождений нет**; подсказок `data-tip` 1 214, поясняющих строк: «Условие» 59, «Ответ» 90, «Вид» 42.

### Приборы «до» (Chromium, сервер 8098 на коде `9b2c3e54`)

Список приборов, которые читают или меряют колонку «Ответ», «Разбор» или ширину холста на ≥ 1 240 (поиск по
`params-panel`, `ans-hero`, `ans-cell`, `#explain`, `ex-body`, `sb-body`, `col-note`, `ans-hide`, `ans-rail` и размеру
окна, пересечённый с приборами, которые называют `calc2/CLAUDE.md`, `calc2/tests/README.md` и Django-тесты): три
прибора CI — `redesign/parity_quick.mjs`, `calc2_math.mjs`, `canon_checks.mjs`; затем `redesign/answer_probe.mjs`,
`redesign/answer_rows_probe.mjs`, `redesign/modes_probe.mjs`, `redesign/layout_probe.mjs`, `self_probe.mjs`,
`math_answer_probe.mjs`, `mc_drag_probe.mjs`, `webkit_probe.mjs`, `control_numbers.mjs`, `input_probe.mjs`,
`calc2_ui.mjs`, `priyomka_probe.mjs`, `final_fn_probe.mjs`, `calc2_blocks.mjs`, `audit_matrix.mjs`,
`sum_visual_probe.mjs`, `night2_font_audit.mjs` (аудит), `math_shots.mjs` (снимки). Вне списка — 27 разовых приборов
прошлых сессий (`night_*`, `interv_phase*`, `priyomka31`, `quadrant*`, `pct_tax*`, `panel_*`, `phase4_inventory`,
`scripts/calc2_*_probe.js`, листы снимков): ни один документ их не называет действующими, их ожидания заморожены на
своих сессиях; не гонялись. Итоги «до» — `claude/panels_night/probes/before/summary.txt` (сводка ниже, в итоге этапа А).

## Этап А. «Ответ»: поведение

### А1–А2 (сделано)
- `wireAnswerHide`: открыт, только если в памяти `'0'` (решение …81de…). Стрелка `#ans-hide` — один узел, прямой
  ребёнок `#params-panel` вне `.side-inner`, круг 40, шеврон SVG (закрыт — повёрнут «‹»), `aria-label` /
  `aria-expanded`, без `data-tip`. Полоска — только «Ответ» 13 / 600 с 64 px. `.col-note` «пересчитывается сразу» и
  «Спрятать ›» убраны из разметки. Шапка «Ответа» с 34 px слева, `.cv-bar` с запасом 24 px справа — только от 1 240.
- **Открытие колонки пересобирает «Ответ»** (`afterColumnShown` → `answerReflow`: сброс `_answerSig` сразу и ещё раз
  через два кадра / 300 мс). Строка табло, набранная без прямоугольника (`typesetStats`, 60-overlays.js), запоминает
  исходное значение (`_typesetBlind`) и перенабирается, как только её видно (`retypesetSeenRows` в начале каждой
  `buildAnswer`); пока сетка колонок едет (`.app.getAnimations()`), не мерим. `hideDrainedBlocks` решает «блок пуст»
  по вычисленному стилю узла и предков (`getComputedStyle`), не по `getClientRects`.
- ⚠️ Ловушка, найденная прибором: при «меньше движения» сайт даёт ВСЕМ свойствам переход 0,01 мс, и в кадр щелчка
  сетка колонок ещё «… 44px»: строки вставали в стопку по ширине 44. Отсюда отложенный проход и проверка анимаций.
- ⚠️ Старый дефект, ставший заметным: на 1280 первое открытие «Ответа» давало шаг «Отменить» (так и на `9b2c3e54`:
  `STATE.legendSpot` — место легенды по ширине холста — не был ключом вида истории). `legendSpot` добавлен в
  `HIST_VIEW_KEYS` (91-session.js). Теперь «Ответ» закрыт по умолчанию, и это увидел бы каждый.
- «Разбор»: полоса `#ex-bar` (в `FORM_SKIP_IDS`) внутри `#ex-title`, «Разбор» + «N вопросов» (`questionsWord`),
  свёрнут классом `body.ex-shown` (нет — свёрнут), сброс при каждой смене модели (`syncExplainBar`). Ни один вопрос
  не раскрыт по умолчанию, память раскрытых `ANSWER_OPEN` прежняя. Телефон: полосы нет, содержимое раскрыто.
- Жирное внутри фразы «Разбора» — класс `ex-inline` (перед ним есть текст), строчное; свой заголовок врезки
  (жирное в начале) остаётся блоком. Вступление «Налогов» — текст прямо в `.sb-note`, не `<p>`.
- Новый прибор `calc2/tests/redesign/answer_panel_probe.mjs` (разделы А, А2, Б; `ENGINES`, `KEYS`).

### А3. Приборы (сделано)

Общий помощник `calc2/tests/answer_open.mjs`: `keepAnswerOpen(browser)` ставит ключ памяти `'0'` до каждой загрузки во
всех контекстах браузера (свои `localStorage.clear()` приборов перехвачены и ключ возвращают); `answerShown(page)` —
предусловие «`#params-panel > .side-inner` видна» (ниже 1 240 истинно). Итоги «до» — копия кода `9b2c3e54` (8098),
«после» — 8099; ⚠️ у части приборов замер «до» пошёл уже с добавленным предусловием (файлы правились во время
фонового прогона) — там на базе оно истинно, число проверок «до» и «после» одно.

| Прибор | Что поменяли | До → после |
|---|---|---|
| `redesign/parity_quick.mjs` (CI) | `keepAnswerOpen`, предусловие | 1 944 проверок, 0 → 1 945, 0 |
| `calc2_math.mjs` (CI) | `keepAnswerOpen`, предусловие | 239 / 0 → 240 / 0 |
| `canon_checks.mjs` (CI) | `expandAll` открывает «Ответ» (`setAnswerHidden(false, true)`) и «Разбор» (`#ex-bar`); ключ `answer_closed` без потолка (+ имя в `test_design_canon.py`) | все ключи 0, `label_shake` 1 (старый) → то же, `answer_closed` 0 |
| `redesign/answer_probe.mjs` | `keepAnswerOpen`, предусловие | 44 модели → 44 |
| `redesign/answer_rows_probe.mjs` | `keepAnswerOpen` (и WebKit), предусловие при первой странице ≥ 1 240 | 119 → 120 |
| `redesign/modes_probe.mjs` | раздел В: «по умолчанию открыт» → «закрыт, полоска открывает» (+1 проверка), подпись «Спрятать ›» → «стрелка «›»», полоска «Ответ‹» → «Ответ» с `aria-label` «Показать «Ответ»» — со ссылкой на …81de… | 54 → 55 |
| `redesign/layout_probe.mjs` | `keepAnswerOpen`, предусловие на 1 440 и 1 280 | норма → норма |
| `self_probe.mjs`, `math_answer_probe.mjs`, `mc_drag_probe.mjs`, `webkit_probe.mjs` | `keepAnswerOpen`, предусловие | 82, 117, 38, 136 → те же |
| `control_numbers.mjs`, `input_probe.mjs`, `calc2_ui.mjs`, `priyomka_probe.mjs`, `final_fn_probe.mjs`, `calc2_blocks.mjs`, `sum_visual_probe.mjs` | `keepAnswerOpen`, предусловие своим способом отчёта | 516; всё; 159; 3 провала (старые, на базе те же); 5 провалов (старые); 67; всё → те же |
| `audit_matrix.mjs`, `night2_font_audit.mjs`, `math_shots.mjs` (аудиты и снимки) | `keepAnswerOpen`, предусловие (`process.exitCode = 1`) | без провалов → то же |
| вне «Ответа»: `state_probe` 44/44, `session_probe` 0 провалов, `picker_probe` 87, `memory_probe` 30, `tex/ci_quick` цела, `check_font_scale` чисто, `nodrag` 0 сдвинутых | — | те же |

`priyomka_probe` (3) и `final_fn_probe` (5) красные и на базе `9b2c3e54` теми же строками (ожидания 25–26.08,
переписанные позже решениями о записи КПВ и суммарном предложении без верхней границы) — не эта сессия.
