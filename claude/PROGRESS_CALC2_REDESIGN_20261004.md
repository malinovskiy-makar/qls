# Прогресс: редизайн вкладки «Графики» (calc2) по макету 04.10

**Задание:** `claude/mockups/calc2_redesign_20261004/PROMPT.md` (перечитывать после сжатия контекста и в начале сессии).
**Ветка:** `feat/calc2-redesign`, создана 05.10.2026 от `origin/main` = `6b797588`. Привязка к `origin/main` снята
(`git branch --unset-upstream`), чтобы случайный `git push` не ушёл в `main`. Пуш не выполнялся.
**Notion:** доступен (05.10): прочитаны задача `3e8b11c9…3ae2`, решения 27.09 и 04.10, карточка контраста.

## Окружение (фаза −1, 05.10)
- macOS, `./venv313/bin/python` 3.13.15, `manage.py check` — 0 ошибок.
- node v24.16.0, Playwright есть, Chromium 151.0.7922.34 запускается.
- `pdflatex` нет → PDF в «не проверено на…». `ruff`, `bandit`, `pip-audit` есть в `venv313/bin`.
- База `config.settings` — локальная SQLite `db.sqlite3`. Боты заведены `scripts/ensure_probe_users.py`
  (`shot_bot`, `shot_bot_teacher`, `shot_bot_parent`).
- Переменные приборов: `CALC2_BASE_URL=http://127.0.0.1:8099`, `CALC2_USER=shot_bot`, `CALC2_PASS` — из скрипта.
- Сервер: `manage.py runserver 8099 --noreload` (конфигурация `calc2-night` в `.claude/launch.json`), `/calc2/` — 200.
- `git remote` → `malinovskiy-makar/qls`; `origin/main` = `6b79758` ровно, после него `calc2/` никто не менял.
- Невлитых веток с правками `calc2/` нет ни на `origin`, ни локально.
- Пакет на месте: README, COVERAGE, CODE_NOTES, INVENTORY, PROMPT, START_HERE, `mockup/` 33 файла, `reference/` 163 PNG,
  `tools/shoot_mockup.mjs`; доска `Kit` снимается в файл (сеть есть).

## Принято без вопроса владельцу
1. **Неотслеживаемые файлы ВП в рабочей копии.** На ветке `feat/vp-trainer` лежали 25 неотслеживаемых файлов
   (`data/vp/*.yaml`, `vp/static/vp/figures/*`), которые в `origin/main` есть как отслеживаемые; 10 из них отличаются
   от версий в `main`. Переключение ветки их затёрло бы. Сделано без потерь: все 25 скопированы в
   `~/Downloads/qls_platform_untracked_vp_backup_20261005/` (хеши сверены, там же `LIST.txt` и `README.txt`), затем
   убраны из рабочей копии, и только после этого создана ветка. К calc2 они отношения не имеют.

2. **Приборы ходят на проверочную копию базы.** Локальная `db.sqlite3` отстала от миграций `main` (нет
   `problems.0076–0078`, `vp.0002–0003`), и вошедшему боту `/calc2/` отдавал 500 (`no such column:
   problems_userprofile.telegram`). Базу владельца не трогал: скопировал её в `db_check.sqlite3` (в `.gitignore`), накатил
   миграции на копию, завёл ботов там. Серверы приборов идут с `--settings=config.settings_check` (готовый модуль проекта
   для браузерных проверок): `reports/calc2_redesign/serve.sh new` (порт 8099, рабочая копия) и `serve.sh old`
   (порт 8098, копия нетронутого кода `../qls_platform_old6b79`, `git worktree` на `6b797588`).
3. **Слепок прибора — 10 значащих цифр, а не 12.** При 12 знаках пересечение D и S выходило то 50, то 49,9999999999
   между двумя загрузками (численный поиск `crossPoints`). Допуск инварианта «слепок STATE» 1e-9: десяти знаков хватает.
4. **Перед стартовым слепком грузятся все объявленные шрифты и холст перерисовывается.** Поля графика считаются по
   ширине подписей, а шрифты KaTeX грузятся лениво: первая показанная формула сдвигала поля на доли пикселя, и шаг
   «открыть подсказку» менял геометрию. Это не дефект движка для человека (сдвиг меньше 0,001 px), но без этого прибор
   не детерминирован.

## Найдено по дороге (не чинилось, в отчёт)
- Двойной щелчок по холсту в Playwright не возвращает масштаб: события `click` доходят, `dblclick` браузер не
  порождает — первый щелчок перерисовывает холст, и узел под курсором меняется. Человеком не проверено; базовый снимок
  записывает исход как есть («нет сброса»).

## Перенацеленные проверки
(что было → что стало → почему)

## Числа «до» (нетронутый код, `6b79758`, 05.10, проверочная база, вход ботом)
| Прибор | Код | Время, с | Итог |
|---|---|---|---|
| `calc2_math.mjs` | 1 | 100 | 237 из 238; красный «Регулятор сцены · правка значения» (поле 40,375 px при потолке 40) — **было красным до** (карточка Notion) |
| `control_numbers.mjs` | 0 | 27 | 512 из 512 |
| `calc2_ui.mjs` | 1 | 64 | 155 из 159; красные: «клавиша ставит символ, не стирая» («100-»), «раздел букв даёт латиницу и греческие», «Построение графиков открывается пустой» (кривых 1), «ровно одна пустая строка» (строк 2) — **были красными до**; 2 ошибки консоли (503 и 400 на загрузке ресурса) |
| `calc2_blocks.mjs` | 1 | 77 | 65 из 66; красный «левый край дорожек ползунков совпадает» (1190,39 и 1176,39) — **было красным до** (карточка Notion) |
| `audit_matrix.mjs` | — | 135 | вывод сохранён (`reports/calc2_redesign/before/audit_matrix.log`), ошибок страницы 0 |
| `panels_probe.mjs` | 0 | 10 | 84 из 84 |
| `formula_input_probe.mjs` | 0 | 222 | 6 из 6 |
| `input_probe.mjs` | 0 | 33 | всё сошлось |
| `export_audit.mjs` | 0 | 29 | всё сошлось |
| `canon_checks.mjs` | 0 | 29 | обход прошёл, JSON сохранён (решение — у `test_design_canon`) |
| `drag_probe.mjs` | — | 3 | вывод сохранён: 1 пересборка, 212 мс, цена 32,94, выпуск 5,16 |
| `manipulator_pan_probe.mjs` | 0 | 6 | ставка изменилась, окно не сдвинулось |
| `phase5_vertex_snap_probe.mjs` | 0 | 3 | промах 0 px |
| `sum_visual_probe.mjs` | 0 | 31 | всё сошлось |
| `check_tex_escapes.mjs` | 0 | 1 | слэшей нет |
| `speed_audit.mjs` | 0 | 22 | сверх порога: открытие 0, перерисовка 0 из 44 |

Логи: `reports/calc2_redesign/before/` (не в git).

**Остальные 34 прибора с кодом возврата** (одна пачка, `reports/calc2_redesign/before_rest/`): зелёные 24 —
`check_font_scale`, `eq_title_audit`, `interv_baseline_probe`, `interv_phase2..5_probe`, `labels_audit`,
`night_panel_check`, `night_phase11_ring_probe`, `night_phase3_reset_probe`, `night_phase6_areas_probe`,
`night_phase7_input_probe`, `night_phase8_labels_probe`, `overlap_audit`, `pct_tax_probe`, `phase1_forcepan_probe`,
`phase1_notbroken_probe`, `phase2_ktv_piecewise_probe`, `phase4_empty_field_probe`, `phase5_hint_hover_probe`,
`priyomka31_probe`, `quadrant_probe`, `title_audit`. **Были красными до** (10): `final_fn_probe` (S до 220 вместо 180:
старое правило, отменённое 31.08), `interv_phase1_probe` (акциз t=20: ждёт числа потоварного налога, прибор старше
ADR 0018), `night_phase10_elabel_probe`, `night_phase5_tax_probe` (список сцен вмешательства), `night_phase9_sliders_probe`
(левый край дорожек — та же карточка Notion, что `calc2_blocks`), `panel_audit`, `pdf_probe` (503: нет `pdflatex`),
`phase3_kink_keypoint_probe`, `phase5_coord_prefix_probe`, `priyomka_probe` (запись КПВ набрана не KaTeX).

## Фазы
| Фаза | Статус | Коммит |
|---|---|---|
| −1 Сверка с реальностью | сделано 05.10 | — |
| 0 Страховочная сетка | в работе | |

## Что не получилось

## Не проверено на…
- PDF: на этой машине нет `pdflatex`.

## Следующий шаг
Фаза 0: прогнать приборы «до» на нетронутом коде и записать числа.
