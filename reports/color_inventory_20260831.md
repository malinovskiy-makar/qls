# Инвентарь цветов, 2026-08-31

Снят `scripts/color_inventory.py` перед большой дизайн-работой, чтобы
через две недели можно было сказать, каким цвет был до правки, и вернуть.
Скрипт только читает; ни один цвет этой съёмкой не изменён.

## Числа

| | |
|---|---:|
| Живых вхождений (вне комментариев) | 660 |
| Вхождений в комментариях (историю цитируют, кода не красят) | 115 |
| Всего найдено | 775 |
| Уникальных цветов (живых) | 256 |

Уникальных по экранам:

«Сайт» — `templates/`, `catalog/`, `student/`, `teacher/`, `problems/`
и `calendar_stub/`. «Прочее» — то, чего человек на экране не видит:
одноразовые скрипты замеров в `scripts/` и заглушка nginx в `deploy/`.

| Экран | Уникальных цветов | Вхождений |
|---|---:|---:|
| сайт | 151 | 340 |
| calc2 | 83 | 181 |
| game | 26 | 38 |
| печатные и офлайн-выгрузки | 23 | 67 |
| прочее | 20 | 34 |

## Цвета по убыванию частоты

| Цвет | Раз | В каких файлах |
|---|---:|---|
| `#ffffff` | 85 | `templates/_nav.html` ×18, `calc2/static/calc2/calc2.css` ×8, `game/templates/game/game.html` ×7, `problems/review_bundle_assets/reviewer.html` ×7, `calendar_stub/templates/calendar_stub/calendar_student.html` ×3, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×3 и ещё 23 |
| `rgba(255,255,255,0.6)` | 26 | `templates/_nav.html` ×26 |
| `#666666` | 13 | `problems/review_bundle_assets/reviewer.html` ×5, `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 и ещё 3 |
| `rgba(0,0,0,0)` | 13 | `templates/_kit.html` ×8, `calc2/tests/audit_matrix.mjs` ×1, `calc2/tests/calc2_math.mjs` ×1, `calc2/tests/phase4_inventory.mjs` ×1, `catalog/static/catalog/css/topic_map.css` ×1, `scripts/r16_tables_probe.js` ×1 |
| `#333333` | 10 | `teacher/templates/teacher/assignment_print.html` ×7, `problems/review_bundle_assets/reviewer.html` ×3 |
| `#6b7280` | 10 | `calendar_stub/templates/calendar_stub/calendar.html` ×8, `templates/_error_base.html` ×2 |
| `#e8e8e4` | 10 | `catalog/templates/catalog/smart_search.html` ×4, `calendar_stub/templates/calendar_stub/calendar_student.html` ×3, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×3 |
| `#888888` | 9 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×4, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×4, `calc2/static/calc2/60-overlays.js` ×1 |
| `#be185d` | 9 | `problems/review_bundle_assets/reviewer.html` ×5, `catalog/static/catalog/js/topic_map.js` ×1, `game/templates/game/game.html` ×1, `problems/static/platform/stats.js` ×1, `scripts/r15_cycle.js` ×1 |
| `#dfe3e8` | 9 | `calc2/tests/interv_contact_sheet.mjs` ×3, `calc2/tests/night2_contact_sheet.mjs` ×3, `calc2/tests/night_contact_sheet.mjs` ×3 |
| `#3b82f6` | 8 | `calendar_stub/templates/calendar_stub/calendar.html` ×8 |
| `#5b6472` | 8 | `scripts/calc2_canon_shots.js` ×3, `calc2/static/calc2/calc2.css` ×1, `catalog/static/catalog/js/topic_map.js` ×1, `problems/static/platform/stats.js` ×1, `scripts/final_check.js` ×1, `scripts/r15_cycle.js` ×1 |
| `#999999` | 8 | `teacher/templates/teacher/assignment_print.html` ×5, `problems/review_bundle_assets/reviewer.html` ×3 |
| `#10141c` | 7 | `calc2/static/calc2/calc2.css` ×2, `calc2/tests/interv_contact_sheet.mjs` ×1, `calc2/tests/night2_contact_sheet.mjs` ×1, `calc2/tests/night_contact_sheet.mjs` ×1, `catalog/static/catalog/js/topic_map.js` ×1, `game/static/game/figure.css` ×1 |
| `#555555` | 7 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1, `catalog/templates/catalog/smart_search.html` ×1 и ещё 1 |
| `#aadddd` | 7 | `scripts/custom_parts.js` ×2, `scripts/session8_cycle.js` ×2, `scripts/r15_builder_probe.js` ×1, `scripts/r18_overlap_probe.js` ×1, `scripts/work_flow_check.js` ×1 |
| `#cccccc` | 7 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1, `problems/review_bundle_assets/reviewer.html` ×1 и ещё 1 |
| `#dddddd` | 7 | `calc2/static/calc2/calc2.css` ×1, `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 и ещё 1 |
| `#10b981` | 6 | `calendar_stub/templates/calendar_stub/calendar.html` ×6 |
| `#777777` | 6 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1, `problems/review_bundle_assets/reviewer.html` ×1 |
| `#f97316` | 6 | `calendar_stub/templates/calendar_stub/calendar.html` ×6 |
| `#000000` | 5 | `calc2/static/calc2/calc2.css` ×3, `teacher/templates/teacher/assignment_print.html` ×2 |
| `#16181c` | 5 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 |
| `#303338` | 5 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 |
| `#3a3d43` | 5 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 |
| `#a2a6ad` | 5 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 |
| `#b26b00` | 5 | `catalog/templates/catalog/smart_search.html` ×3, `problems/review_bundle_assets/reviewer.html` ×1, `problems/static/platform/stats.js` ×1 |
| `#d8d8de` | 5 | `problems/review_bundle_assets/reviewer.html` ×5 |
| `#e6e6e6` | 5 | `calc2/tests/input_contact_sheet.mjs` ×1, `calc2/tests/pct_tax_contact_sheet.mjs` ×1, `calc2/tests/priyomka_contact_sheet.mjs` ×1, `calc2/tests/quadrant_contact_sheet.mjs` ×1, `calc2/tests/sum_visual_contact_sheet.mjs` ×1 |
| `rgba(0,0,0,0.07)` | 5 | `catalog/templates/catalog/problem_list.html` ×1, `game/templates/game/game.html` ×1, `problems/static/platform/stats.js` ×1, `teacher/templates/teacher/dashboard.html` ×1, `templates/_kit.html` ×1 |
| `rgba(255,255,255,0.55)` | 5 | `student/templates/student/base.html` ×2, `teacher/templates/teacher/base.html` ×2, `catalog/templates/catalog/base.html` ×1 |
| `#123456` | 4 | `calc2/tests/calc2_ui.mjs` ×4 |
| `#2d2d2d` | 4 | `templates/_tokens.html` ×4 |
| `#8b3fe0` | 4 | `calc2/static/calc2/calc2.css` ×3, `game/static/game/figure.css` ×1 |
| `#b5791f` | 4 | `calc2/static/calc2/calc2.css` ×3, `game/static/game/figure.css` ×1 |
| `#f7f7f5` | 4 | `catalog/templates/catalog/smart_search.html` ×2, `calc2/tests/final_night_shots.mjs` ×1, `deploy/nginx/html/index.html` ×1 |
| `#ff4d94` | 4 | `game/templates/game/game.html` ×3, `catalog/static/catalog/js/topic_map.js` ×1 |
| `rgba(0,0,0,0.14)` | 4 | `calc2/static/calc2/calc2.css` ×2, `templates/_kit.html` ×1, `templates/_tokens.html` ×1 |
| `rgba(255,255,255,0.08)` | 4 | `catalog/templates/catalog/base.html` ×1, `student/templates/student/base.html` ×1, `teacher/templates/teacher/base.html` ×1, `templates/_tokens.html` ×1 |
| `rgba(255,255,255,0.15)` | 4 | `catalog/templates/catalog/base.html` ×1, `student/templates/student/base.html` ×1, `teacher/templates/teacher/base.html` ×1, `templates/admin/base_site.html` ×1 |
| `#119c8a` | 3 | `calc2/static/calc2/calc2.css` ×2, `game/static/game/figure.css` ×1 |
| `#1d7e45` | 3 | `catalog/templates/catalog/smart_search.html` ×1, `problems/review_bundle_assets/reviewer.html` ×1, `problems/static/platform/stats.js` ×1 |
| `#232322` | 3 | `templates/_tokens.html` ×3 |
| `#2e9e44` | 3 | `calc2/static/calc2/calc2.css` ×2, `game/static/game/figure.css` ×1 |
| `#2f6fed` | 3 | `calc2/static/calc2/calc2.css` ×2, `game/static/game/figure.css` ×1 |
| `#4a5361` | 3 | `calc2/tests/interv_contact_sheet.mjs` ×1, `calc2/tests/night2_contact_sheet.mjs` ×1, `calc2/tests/night_contact_sheet.mjs` ×1 |
| `#81b5b4` | 3 | `templates/_tokens.html` ×3 |
| `#96969f` | 3 | `game/templates/game/game.html` ×3 |
| `#cc0000` | 3 | `scripts/katex_damage.js` ×1, `scripts/latex_probe.js` ×1, `scripts/raw_tex_probe.js` ×1 |
| `#eceff3` | 3 | `calc2/tests/interv_contact_sheet.mjs` ×1, `calc2/tests/night2_contact_sheet.mjs` ×1, `calc2/tests/night_contact_sheet.mjs` ×1 |
| `#f5f5f3` | 3 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1, `catalog/static/catalog/js/topic_map.js` ×1 |
| `#f6f7f9` | 3 | `calc2/tests/interv_contact_sheet.mjs` ×1, `calc2/tests/night2_contact_sheet.mjs` ×1, `calc2/tests/night_contact_sheet.mjs` ×1 |
| `#ff00aa` | 3 | `calc2/tests/calc2_ui.mjs` ×3 |
| `rgba(0,0,0,0.06)` | 3 | `calendar_stub/templates/calendar_stub/calendar.html` ×1, `catalog/templates/catalog/smart_search.html` ×1, `templates/_kit.html` ×1 |
| `rgba(0,0,0,0.18)` | 3 | `calendar_stub/templates/calendar_stub/calendar.html` ×1, `catalog/templates/catalog/problem_list.html` ×1, `teacher/templates/teacher/_picker_style.html` ×1 |
| `#00ccdd` | 2 | `calc2/tests/calc2_ui.mjs` ×2 |
| `#010203` | 2 | `scripts/katex_damage.js` ×2 |
| `#186e3c` | 2 | `templates/_tokens.html` ×2 |
| `#1a1a1a` | 2 | `catalog/static/catalog/js/topic_map.js` ×1, `problems/review_bundle_assets/reviewer.html` ×1 |
| `#1a1f2e` | 2 | `catalog/templates/catalog/smart_search.html` ×1, `templates/_nav.html` ×1 |
| `#1a5ccc` | 2 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1 |
| `#1f2937` | 2 | `templates/_error_base.html` ×2 |
| `#222222` | 2 | `problems/review_bundle_assets/reviewer.html` ×1, `teacher/templates/teacher/assignment_print.html` ×1 |
| `#2a2f3a` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#2e7d32` | 2 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1 |
| `#3e6c99` | 2 | `catalog/static/catalog/js/topic_map.js` ×1, `templates/_tokens.html` ×1 |
| `#3fc77f` | 2 | `game/templates/game/game.html` ×1, `templates/_tokens.html` ×1 |
| `#444444` | 2 | `teacher/templates/teacher/assignment_print.html` ×2 |
| `#4a5260` | 2 | `catalog/static/catalog/js/topic_map.js` ×1, `templates/_tokens.html` ×1 |
| `#5c5346` | 2 | `templates/_tokens.html` ×2 |
| `#5e6675` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#6b7482` | 2 | `calc2/tests/interv_contact_sheet.mjs` ×1, `calc2/tests/night2_contact_sheet.mjs` ×1 |
| `#8b5cf6` | 2 | `calendar_stub/templates/calendar_stub/calendar.html` ×2 |
| `#8c8c84` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#8fbee0` | 2 | `catalog/static/catalog/js/topic_map.js` ×1, `templates/_tokens.html` ×1 |
| `#98a1b0` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#9aa0a6` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#b0338c` | 2 | `calc2/static/calc2/calc2.css` ×2 |
| `#b45309` | 2 | `calc2/templates/calc2/calc2.html` ×2 |
| `#b93526` | 2 | `templates/_tokens.html` ×2 |
| `#c74440` | 2 | `calc2/static/calc2/calc2.css` ×1, `calc2/tests/calc2_ui.mjs` ×1 |
| `#c8ceda` | 2 | `catalog/static/catalog/js/topic_map.js` ×1, `templates/_tokens.html` ×1 |
| `#d14343` | 2 | `calc2/static/calc2/calc2.css` ×2 |
| `#d6a525` | 2 | `templates/_tokens.html` ×2 |
| `#d7dbe3` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#e0563b` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/static/game/figure.css` ×1 |
| `#e2e5ea` | 2 | `scripts/calc2_canon_shots.js` ×2 |
| `#e5e7eb` | 2 | `templates/_error_base.html` ×2 |
| `#e65100` | 2 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1 |
| `#e8f0fe` | 2 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1 |
| `#e8f5e9` | 2 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1 |
| `#ec4899` | 2 | `calendar_stub/templates/calendar_stub/calendar.html` ×2 |
| `#f0f0ee` | 2 | `catalog/templates/catalog/smart_search.html` ×1, `deploy/nginx/html/index.html` ×1 |
| `#f2ecd9` | 2 | `templates/_tokens.html` ×2 |
| `#f2f2f4` | 2 | `problems/review_bundle_assets/reviewer.html` ×2 |
| `#f4eed2` | 2 | `templates/_tokens.html` ×2 |
| `#f5f5f5` | 2 | `catalog/templates/catalog/smart_search.html` ×2 |
| `#f7f7f9` | 2 | `problems/review_bundle_assets/reviewer.html` ×2 |
| `#fdf2f7` | 2 | `problems/review_bundle_assets/reviewer.html` ×2 |
| `#fff3e0` | 2 | `calendar_stub/templates/calendar_stub/calendar_student.html` ×1, `calendar_stub/templates/calendar_stub/calendar_teacher.html` ×1 |
| `rgba(0,0,0,0.08)` | 2 | `game/templates/game/game.html` ×1, `student/templates/student/dashboard.html` ×1 |
| `rgba(0,0,0,0.1)` | 2 | `catalog/templates/catalog/collection_new.html` ×1, `catalog/templates/catalog/home.html` ×1 |
| `rgba(0,0,0,0.4)` | 2 | `calendar_stub/templates/calendar_stub/calendar.html` ×1, `problems/templates/platform/problem_form.html` ×1 |
| `rgba(0,0,0,0.45)` | 2 | `catalog/templates/catalog/problem_list.html` ×1, `teacher/templates/teacher/_picker_style.html` ×1 |
| `rgba(0,0,0,0.55)` | 2 | `calc2/static/calc2/calc2.css` ×1, `game/templates/game/game.html` ×1 |
| `rgba(255,255,255,0.07)` | 2 | `calc2/static/calc2/calc2.css` ×1, `templates/_tokens.html` ×1 |
| `rgba(255,255,255,0.13)` | 2 | `templates/_tokens.html` ×2 |
| `rgba(255,255,255,0.2)` | 2 | `templates/_nav.html` ×2 |
| `rgba(255,255,255,0.3)` | 2 | `student/templates/student/base.html` ×1, `teacher/templates/teacher/base.html` ×1 |
| `rgba(255,255,255,0.45)` | 2 | `student/templates/student/base.html` ×1, `teacher/templates/teacher/base.html` ×1 |
| `rgba(255,255,255,0.8)` | 2 | `student/templates/student/base.html` ×1, `teacher/templates/teacher/base.html` ×1 |
| `rgba(255,255,255,0.85)` | 2 | `student/templates/student/base.html` ×1, `teacher/templates/teacher/base.html` ×1 |
| `#0000ee` | 1 | `scripts/r15_cycle.js` ×1 |
| `#006c6d` | 1 | `templates/_tokens.html` ×1 |
| `#00797a` | 1 | `templates/_tokens.html` ×1 |
| `#016769` | 1 | `templates/_tokens.html` ×1 |
| `#07090e` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#0d0d12` | 1 | `game/templates/game/game.html` ×1 |
| `#0f8c7c` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#10131a` | 1 | `scripts/calc2_canon_shots.js` ×1 |
| `#11151d` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#17171a` | 1 | `deploy/nginx/html/index.html` ×1 |
| `#1a1a18` | 1 | `calc2/tests/final_night_shots.mjs` ×1 |
| `#1c1c1a` | 1 | `deploy/nginx/html/index.html` ×1 |
| `#23211d` | 1 | `templates/_tokens.html` ×1 |
| `#252c3f` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#2a3140` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#2a8f3e` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#2d504f` | 1 | `templates/_tokens.html` ×1 |
| `#2d70b3` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#2e2e33` | 1 | `deploy/nginx/html/index.html` ×1 |
| `#343432` | 1 | `templates/_tokens.html` ×1 |
| `#348543` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#3b332a` | 1 | `templates/_tokens.html` ×1 |
| `#3c3531` | 1 | `templates/_tokens.html` ×1 |
| `#3d3d39` | 1 | `calc2/tests/final_night_shots.mjs` ×1 |
| `#3f3f3d` | 1 | `templates/_tokens.html` ×1 |
| `#43566f` | 1 | `templates/_tokens.html` ×1 |
| `#4a4136` | 1 | `templates/_tokens.html` ×1 |
| `#4f7cff` | 1 | `game/templates/game/game.html` ×1 |
| `#4fbf6a` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#504a2d` | 1 | `templates/_tokens.html` ×1 |
| `#5a6472` | 1 | `catalog/static/catalog/js/topic_map.js` ×1 |
| `#5aa3e8` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#5c5c57` | 1 | `calc2/tests/final_night_shots.mjs` ×1 |
| `#6042a6` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#665e51` | 1 | `templates/_tokens.html` ×1 |
| `#666c7e` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#6b6b66` | 1 | `deploy/nginx/html/index.html` ×1 |
| `#6b6b78` | 1 | `game/templates/game/game.html` ×1 |
| `#723c09` | 1 | `templates/_tokens.html` ×1 |
| `#7c261b` | 1 | `problems/review_bundle_assets/reviewer.html` ×1 |
| `#7d7466` | 1 | `templates/_tokens.html` ×1 |
| `#8a6fb0` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#8a8172` | 1 | `templates/_tokens.html` ×1 |
| `#8a8a82` | 1 | `calc2/tests/final_night_shots.mjs` ×1 |
| `#8a93a0` | 1 | `calc2/tests/night_contact_sheet.mjs` ×1 |
| `#8e96a4` | 1 | `catalog/static/catalog/js/topic_map.js` ×1 |
| `#96500c` | 1 | `templates/_tokens.html` ×1 |
| `#96a0af` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#9a9a94` | 1 | `deploy/nginx/html/index.html` ×1 |
| `#9bc6c5` | 1 | `templates/_tokens.html` ×1 |
| `#9d1250` | 1 | `problems/review_bundle_assets/reviewer.html` ×1 |
| `#9d174d` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#a78bfa` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#a7aebc` | 1 | `catalog/static/catalog/js/topic_map.js` ×1 |
| `#a8bcd6` | 1 | `templates/_tokens.html` ×1 |
| `#aaaaaa` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#b06a6a` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#b23a67` | 1 | `calc2/tests/night_contact_sheet.mjs` ×1 |
| `#b5ab99` | 1 | `templates/_tokens.html` ×1 |
| `#b91c1c` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#bbbbbb` | 1 | `problems/review_bundle_assets/reviewer.html` ×1 |
| `#bfecd4` | 1 | `templates/_tokens.html` ×1 |
| `#c0392b` | 1 | `problems/static/platform/stats.js` ×1 |
| `#c2680f` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#c3bca8` | 1 | `templates/_tokens.html` ×1 |
| `#c4bba9` | 1 | `templates/_tokens.html` ×1 |
| `#c8c2b0` | 1 | `templates/_tokens.html` ×1 |
| `#d0c7b5` | 1 | `templates/_tokens.html` ×1 |
| `#d23b3b` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#e0b4b4` | 1 | `calc2/tests/night2_contact_sheet.mjs` ×1 |
| `#e0e0e0` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#e2e2dd` | 1 | `deploy/nginx/html/index.html` ×1 |
| `#e3e3de` | 1 | `calc2/tests/final_night_shots.mjs` ×1 |
| `#e6f5eb` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#e7e9ef` | 1 | `catalog/static/catalog/js/topic_map.js` ×1 |
| `#ebebef` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#eceef2` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#efa273` | 1 | `templates/_tokens.html` ×1 |
| `#efefeb` | 1 | `calc2/tests/final_night_shots.mjs` ×1 |
| `#f2e8bd` | 1 | `templates/_tokens.html` ×1 |
| `#f4f4f4` | 1 | `teacher/templates/teacher/assignment_print.html` ×1 |
| `#f4f5f7` | 1 | `scripts/calc2_canon_shots.js` ×1 |
| `#f5a623` | 1 | `game/templates/game/game.html` ×1 |
| `#f9eae1` | 1 | `templates/_tokens.html` ×1 |
| `#fa7e19` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#fca5a5` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#fce7f3` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#ff6b66` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#ff8a8a` | 1 | `templates/_tokens.html` ×1 |
| `#ffa94d` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `#ffd2d2` | 1 | `templates/_tokens.html` ×1 |
| `#fff5f5` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#fff8e6` | 1 | `catalog/templates/catalog/smart_search.html` ×1 |
| `#fff8f8` | 1 | `calc2/tests/night2_contact_sheet.mjs` ×1 |
| `#fffce6` | 1 | `templates/_tokens.html` ×1 |
| `rgba(0,0,0,0.03)` | 1 | `catalog/templates/catalog/collection_detail.html` ×1 |
| `rgba(0,0,0,0.04)` | 1 | `templates/_error_base.html` ×1 |
| `rgba(0,0,0,0.05)` | 1 | `student/templates/student/work_review.html` ×1 |
| `rgba(0,0,0,0.12)` | 1 | `catalog/templates/catalog/problem_list.html` ×1 |
| `rgba(0,0,0,0.16)` | 1 | `templates/_kit.html` ×1 |
| `rgba(0,0,0,0.28)` | 1 | `templates/_kit.html` ×1 |
| `rgba(0,0,0,0.35)` | 1 | `problems/templates/platform/_stats_style.html` ×1 |
| `rgba(0,0,0,0.6)` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `rgba(0,108,109,0.09)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(0,121,122,0.32)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(125,116,102,0.22)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(129,181,180,0.16)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(129,181,180,0.4)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(138,129,114,0.26)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(15,18,26,0.42)` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `rgba(15,18,28,0.06)` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `rgba(15,18,28,0.18)` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `rgba(15,23,42,0.55)` | 1 | `teacher/templates/teacher/work/compose.html` ×1 |
| `rgba(150,80,12,0.11)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(150,80,12,0.34)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(168,188,214,0.16)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(168,188,214,0.34)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(178,58,103,0.18)` | 1 | `calc2/tests/night_contact_sheet.mjs` ×1 |
| `rgba(185,53,38,0.09)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(185,53,38,0.28)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(192,57,43,0.35)` | 1 | `game/templates/game/game.html` ×1 |
| `rgba(22,26,38,0.34)` | 1 | `scripts/final_check.js` ×1 |
| `rgba(239,162,115,0.15)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(239,162,115,0.34)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(24,110,60,0.09)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(24,110,60,0.3)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(255,138,138,0.15)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(255,138,138,0.3)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(255,255,255,0.05)` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `rgba(255,255,255,0.075)` | 1 | `calc2/static/calc2/calc2.css` ×1 |
| `rgba(255,255,255,0.28)` | 1 | `templates/admin/base_site.html` ×1 |
| `rgba(255,255,255,0.34)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(255,255,255,0.35)` | 1 | `catalog/templates/catalog/base.html` ×1 |
| `rgba(255,255,255,0.7)` | 1 | `templates/_nav.html` ×1 |
| `rgba(45,40,30,0.17)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(45,45,45,0.07)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(45,45,45,0.08)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(45,45,45,0.14)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(45,45,45,0.34)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(63,199,127,0.15)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(63,199,127,0.32)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(67,86,111,0.09)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(67,86,111,0.28)` | 1 | `templates/_tokens.html` ×1 |
| `rgba(8,11,18,0.58)` | 1 | `catalog/static/catalog/css/topic_map.css` ×1 |

## По экранам

### сайт — 151 уникальных, 340 вхождений

| Цвет | Раз |
|---|---:|
| `#ffffff` | 49 |
| `rgba(255,255,255,0.6)` | 26 |
| `#6b7280` | 10 |
| `#e8e8e4` | 10 |
| `rgba(0,0,0,0)` | 9 |
| `#3b82f6` | 8 |
| `#888888` | 8 |
| `#10b981` | 6 |
| `#f97316` | 6 |
| `rgba(255,255,255,0.55)` | 5 |
| `#2d2d2d` | 4 |
| `#b26b00` | 4 |
| `rgba(0,0,0,0.07)` | 4 |
| `rgba(255,255,255,0.08)` | 4 |
| `rgba(255,255,255,0.15)` | 4 |
| `#232322` | 3 |
| `#81b5b4` | 3 |
| `#f5f5f3` | 3 |
| `rgba(0,0,0,0.06)` | 3 |
| `rgba(0,0,0,0.18)` | 3 |
| `#186e3c` | 2 |
| `#1a1f2e` | 2 |
| `#1a5ccc` | 2 |
| `#1d7e45` | 2 |
| `#1f2937` | 2 |
| `#2e7d32` | 2 |
| `#3e6c99` | 2 |
| `#4a5260` | 2 |
| `#5b6472` | 2 |
| `#5c5346` | 2 |
| `#666666` | 2 |
| `#8b5cf6` | 2 |
| `#8fbee0` | 2 |
| `#b93526` | 2 |
| `#be185d` | 2 |
| `#c8ceda` | 2 |
| `#d6a525` | 2 |
| `#e5e7eb` | 2 |
| `#e65100` | 2 |
| `#e8f0fe` | 2 |
| `#e8f5e9` | 2 |
| `#ec4899` | 2 |
| `#f2ecd9` | 2 |
| `#f4eed2` | 2 |
| `#f5f5f5` | 2 |
| `#f7f7f5` | 2 |
| `#fff3e0` | 2 |
| `rgba(0,0,0,0.1)` | 2 |
| `rgba(0,0,0,0.14)` | 2 |
| `rgba(0,0,0,0.4)` | 2 |
| `rgba(0,0,0,0.45)` | 2 |
| `rgba(255,255,255,0.13)` | 2 |
| `rgba(255,255,255,0.2)` | 2 |
| `rgba(255,255,255,0.3)` | 2 |
| `rgba(255,255,255,0.45)` | 2 |
| `rgba(255,255,255,0.8)` | 2 |
| `rgba(255,255,255,0.85)` | 2 |
| `#006c6d` | 1 |
| `#00797a` | 1 |
| `#016769` | 1 |
| `#10141c` | 1 |
| `#1a1a1a` | 1 |
| `#23211d` | 1 |
| `#252c3f` | 1 |
| `#2d504f` | 1 |
| `#343432` | 1 |
| `#3b332a` | 1 |
| `#3c3531` | 1 |
| `#3f3f3d` | 1 |
| `#3fc77f` | 1 |
| `#43566f` | 1 |
| `#4a4136` | 1 |
| `#504a2d` | 1 |
| `#555555` | 1 |
| `#5a6472` | 1 |
| `#665e51` | 1 |
| `#723c09` | 1 |
| `#7d7466` | 1 |
| `#8a8172` | 1 |
| `#8e96a4` | 1 |
| `#96500c` | 1 |
| `#9bc6c5` | 1 |
| `#9d174d` | 1 |
| `#a7aebc` | 1 |
| `#a8bcd6` | 1 |
| `#aaaaaa` | 1 |
| `#b5ab99` | 1 |
| `#b91c1c` | 1 |
| `#bfecd4` | 1 |
| `#c0392b` | 1 |
| `#c3bca8` | 1 |
| `#c4bba9` | 1 |
| `#c8c2b0` | 1 |
| `#d0c7b5` | 1 |
| `#e0e0e0` | 1 |
| `#e6f5eb` | 1 |
| `#e7e9ef` | 1 |
| `#efa273` | 1 |
| `#f0f0ee` | 1 |
| `#f2e8bd` | 1 |
| `#f9eae1` | 1 |
| `#fca5a5` | 1 |
| `#fce7f3` | 1 |
| `#ff4d94` | 1 |
| `#ff8a8a` | 1 |
| `#ffd2d2` | 1 |
| `#fff5f5` | 1 |
| `#fff8e6` | 1 |
| `#fffce6` | 1 |
| `rgba(0,0,0,0.03)` | 1 |
| `rgba(0,0,0,0.04)` | 1 |
| `rgba(0,0,0,0.05)` | 1 |
| `rgba(0,0,0,0.08)` | 1 |
| `rgba(0,0,0,0.12)` | 1 |
| `rgba(0,0,0,0.16)` | 1 |
| `rgba(0,0,0,0.28)` | 1 |
| `rgba(0,0,0,0.35)` | 1 |
| `rgba(0,108,109,0.09)` | 1 |
| `rgba(0,121,122,0.32)` | 1 |
| `rgba(125,116,102,0.22)` | 1 |
| `rgba(129,181,180,0.16)` | 1 |
| `rgba(129,181,180,0.4)` | 1 |
| `rgba(138,129,114,0.26)` | 1 |
| `rgba(15,23,42,0.55)` | 1 |
| `rgba(150,80,12,0.11)` | 1 |
| `rgba(150,80,12,0.34)` | 1 |
| `rgba(168,188,214,0.16)` | 1 |
| `rgba(168,188,214,0.34)` | 1 |
| `rgba(185,53,38,0.09)` | 1 |
| `rgba(185,53,38,0.28)` | 1 |
| `rgba(239,162,115,0.15)` | 1 |
| `rgba(239,162,115,0.34)` | 1 |
| `rgba(24,110,60,0.09)` | 1 |
| `rgba(24,110,60,0.3)` | 1 |
| `rgba(255,138,138,0.15)` | 1 |
| `rgba(255,138,138,0.3)` | 1 |
| `rgba(255,255,255,0.07)` | 1 |
| `rgba(255,255,255,0.28)` | 1 |
| `rgba(255,255,255,0.34)` | 1 |
| `rgba(255,255,255,0.35)` | 1 |
| `rgba(255,255,255,0.7)` | 1 |
| `rgba(45,40,30,0.17)` | 1 |
| `rgba(45,45,45,0.07)` | 1 |
| `rgba(45,45,45,0.08)` | 1 |
| `rgba(45,45,45,0.14)` | 1 |
| `rgba(45,45,45,0.34)` | 1 |
| `rgba(63,199,127,0.15)` | 1 |
| `rgba(63,199,127,0.32)` | 1 |
| `rgba(67,86,111,0.09)` | 1 |
| `rgba(67,86,111,0.28)` | 1 |
| `rgba(8,11,18,0.58)` | 1 |

### calc2 — 83 уникальных, 181 вхождений

| Цвет | Раз |
|---|---:|
| `#ffffff` | 17 |
| `#dfe3e8` | 9 |
| `#dddddd` | 6 |
| `#10141c` | 5 |
| `#16181c` | 5 |
| `#303338` | 5 |
| `#3a3d43` | 5 |
| `#555555` | 5 |
| `#666666` | 5 |
| `#777777` | 5 |
| `#a2a6ad` | 5 |
| `#cccccc` | 5 |
| `#e6e6e6` | 5 |
| `#123456` | 4 |
| `#000000` | 3 |
| `#4a5361` | 3 |
| `#8b3fe0` | 3 |
| `#b5791f` | 3 |
| `#eceff3` | 3 |
| `#f6f7f9` | 3 |
| `#ff00aa` | 3 |
| `rgba(0,0,0,0)` | 3 |
| `#00ccdd` | 2 |
| `#119c8a` | 2 |
| `#2e9e44` | 2 |
| `#2f6fed` | 2 |
| `#6b7482` | 2 |
| `#b0338c` | 2 |
| `#b45309` | 2 |
| `#c74440` | 2 |
| `#d14343` | 2 |
| `rgba(0,0,0,0.14)` | 2 |
| `#07090e` | 1 |
| `#0f8c7c` | 1 |
| `#11151d` | 1 |
| `#1a1a18` | 1 |
| `#2a2f3a` | 1 |
| `#2a3140` | 1 |
| `#2a8f3e` | 1 |
| `#2d70b3` | 1 |
| `#348543` | 1 |
| `#3d3d39` | 1 |
| `#4fbf6a` | 1 |
| `#5aa3e8` | 1 |
| `#5b6472` | 1 |
| `#5c5c57` | 1 |
| `#5e6675` | 1 |
| `#6042a6` | 1 |
| `#666c7e` | 1 |
| `#888888` | 1 |
| `#8a6fb0` | 1 |
| `#8a8a82` | 1 |
| `#8a93a0` | 1 |
| `#8c8c84` | 1 |
| `#96a0af` | 1 |
| `#98a1b0` | 1 |
| `#9aa0a6` | 1 |
| `#a78bfa` | 1 |
| `#b06a6a` | 1 |
| `#b23a67` | 1 |
| `#c2680f` | 1 |
| `#d23b3b` | 1 |
| `#d7dbe3` | 1 |
| `#e0563b` | 1 |
| `#e0b4b4` | 1 |
| `#e3e3de` | 1 |
| `#ebebef` | 1 |
| `#eceef2` | 1 |
| `#efefeb` | 1 |
| `#f7f7f5` | 1 |
| `#fa7e19` | 1 |
| `#ff6b66` | 1 |
| `#ffa94d` | 1 |
| `#fff8f8` | 1 |
| `rgba(0,0,0,0.55)` | 1 |
| `rgba(0,0,0,0.6)` | 1 |
| `rgba(15,18,26,0.42)` | 1 |
| `rgba(15,18,28,0.06)` | 1 |
| `rgba(15,18,28,0.18)` | 1 |
| `rgba(178,58,103,0.18)` | 1 |
| `rgba(255,255,255,0.05)` | 1 |
| `rgba(255,255,255,0.07)` | 1 |
| `rgba(255,255,255,0.075)` | 1 |

### game — 26 уникальных, 38 вхождений

| Цвет | Раз |
|---|---:|
| `#ffffff` | 9 |
| `#96969f` | 3 |
| `#ff4d94` | 3 |
| `#0d0d12` | 1 |
| `#10141c` | 1 |
| `#119c8a` | 1 |
| `#2a2f3a` | 1 |
| `#2e9e44` | 1 |
| `#2f6fed` | 1 |
| `#3fc77f` | 1 |
| `#4f7cff` | 1 |
| `#5e6675` | 1 |
| `#6b6b78` | 1 |
| `#8b3fe0` | 1 |
| `#8c8c84` | 1 |
| `#98a1b0` | 1 |
| `#9aa0a6` | 1 |
| `#b5791f` | 1 |
| `#be185d` | 1 |
| `#d7dbe3` | 1 |
| `#e0563b` | 1 |
| `#f5a623` | 1 |
| `rgba(0,0,0,0.07)` | 1 |
| `rgba(0,0,0,0.08)` | 1 |
| `rgba(0,0,0,0.55)` | 1 |
| `rgba(192,57,43,0.35)` | 1 |

### печатные и офлайн-выгрузки — 23 уникальных, 67 вхождений

| Цвет | Раз |
|---|---:|
| `#333333` | 10 |
| `#ffffff` | 9 |
| `#999999` | 8 |
| `#666666` | 6 |
| `#be185d` | 5 |
| `#d8d8de` | 5 |
| `#000000` | 2 |
| `#222222` | 2 |
| `#444444` | 2 |
| `#cccccc` | 2 |
| `#f2f2f4` | 2 |
| `#f7f7f9` | 2 |
| `#fdf2f7` | 2 |
| `#1a1a1a` | 1 |
| `#1d7e45` | 1 |
| `#555555` | 1 |
| `#777777` | 1 |
| `#7c261b` | 1 |
| `#9d1250` | 1 |
| `#b26b00` | 1 |
| `#bbbbbb` | 1 |
| `#dddddd` | 1 |
| `#f4f4f4` | 1 |

### прочее — 20 уникальных, 34 вхождений

| Цвет | Раз |
|---|---:|
| `#aadddd` | 7 |
| `#5b6472` | 5 |
| `#cc0000` | 3 |
| `#010203` | 2 |
| `#e2e5ea` | 2 |
| `#0000ee` | 1 |
| `#10131a` | 1 |
| `#17171a` | 1 |
| `#1c1c1a` | 1 |
| `#2e2e33` | 1 |
| `#6b6b66` | 1 |
| `#9a9a94` | 1 |
| `#be185d` | 1 |
| `#e2e2dd` | 1 |
| `#f0f0ee` | 1 |
| `#f4f5f7` | 1 |
| `#f7f7f5` | 1 |
| `#ffffff` | 1 |
| `rgba(0,0,0,0)` | 1 |
| `rgba(22,26,38,0.34)` | 1 |

