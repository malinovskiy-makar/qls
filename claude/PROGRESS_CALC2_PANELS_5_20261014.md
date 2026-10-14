# Графики: тихие панели — сессия 5 (14.10.2026): правки по приёмке (этап А) и карточки (этапы Б–Г)

Задание — `claude/mockups/calc2_panels_20261014/PROMPT_5.md` (совпадает с присланным в чат), правила — README
пакета. Ветка `feat/calc2-redesign`. Приборы — сервер 8099 (`--settings=config.settings_check`, с
автоперезагрузкой). Замеры «до» — на копии кода `786e2ab1` (git worktree в папке сеанса, сервер 8098 на копии
`db_check.sqlite3`), чтобы правка статики не попала в базу «до». Прогон приборов — `claude/panels_s5/run_probes.sh`
(последовательно, лог и сводка в папку).

## Фаза −1. Сверка с реальностью

- `caffeinate -is -t 57600` запущен в фоне.
- Ветка `feat/calc2-redesign`, `git log -1` — `786e2ab1` («тихие панели, финал»), с `origin` вровень.
- `git status`: изменён только `.claude/launch.json` — приложение дописало локальный сервер `dev-mac` (порт 8000);
  calc2 и задания не касается, в коммиты не берётся. Не расхождение с заданием, а локальная настройка.
- Notion прочитан: решения …81de…, …81eb…, …8142…, …81d6…, …81c3… (новое: «Расходы бюджета» положительным);
  задачи …811d… (правки по приёмке, «Надо»), зонтик …8178… («В работе»); «Задачи» «В работе» и «Надо» по
  калькулятору, 5 последних «Решений».
- `manage.py check` — 0 ошибок; `makemigrations --check --dry-run` — «No changes detected»; node 24.16;
  Playwright: chromium-1234 и webkit-2336 на месте.
- ADR: последний занятый 0152 (локально, `origin/main`, все ветки) → свободен **0153**.
- Опись «до»: `claude/panels_s5/S5_before.json` (42 модели, сервер 8098 на копии `786e2ab1`); сверка с
  `claude/panels_night/D_after.json` — **расхождений нет** (`S5_before_vs_D.txt`); подсказок `data-tip` 1 211,
  поясняющих строк: Условие 0, Ответ 5, Вид 0.

### Приборы «до» (Chromium, сервер 8098 на `786e2ab1`) — `claude/panels_s5/probes/before/summary.txt`

| Прибор | До |
|---|---|
| `redesign/view_probe` | 13 / 13 |
| `redesign/answer_panel_probe` | 86 / 86 |
| `redesign/quiet_probe` | 19 / 19 |
| `redesign/state_probe` | 44 / 44 |
| `redesign/session_probe` | 0 провалов |
| `redesign/parity_quick` | 1 945 проверок, 0 расхождений |
| `redesign/answer_probe` | 44 модели |
| `redesign/answer_rows_probe` | 123 |
| `control_numbers` | 516 |
| `calc2_math` | 240 / 0 |
| `redesign/layout_probe` | норма |
| `tex/ci_quick` | цела (44 старта, превью 42) |
| `scripts/calc2_nodrag_probe.js` | 0 сдвинутых |
| `check_font_scale` | чисто |
| `canon_checks` | все ключи 0, `label_shake` 1 (старый, m-graph, карточка …8192…) |

Старые провалы вне списка (`final_fn_probe` 5, `priyomka_probe` 3) не гонялись: прибор не затронут, число сверю в
финале.

**Фаза −1 пройдена, расхождений с реальностью нет. Следующий шаг:** этап А (правки А1–А5).
