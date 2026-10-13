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
