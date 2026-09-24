# Журнал сессии «Укрепление беты 24.09»

Ветка `fix/beta-hardening-20260924` от `origin/main` @ `f50266d`, папка
`C:\Users\shipu\qls-harden` (junction на `venv313` и `node_modules` из `qls`).
Промпт сессии — 17 пунктов владельца, фазы −1…9. Карточка сессии в Notion:
https://app.notion.com/3e5b11c92bc1813eb587efa119842068

## Фаза −1. Сверка с реальностью — СДЕЛАНО

- `origin/main` = `f50266d` ровно, новее нет → файлы фаз никем не задеты.
- `manage.py check` в новой папке — 0 ошибок (без `.env`: `REDIS_URL` не
  задан, кэш в памяти — для тестов это норма).
- 9 из 9 фактов подтверждены чтением:
  1. `profile.html`: `{{ form.username }}` стр. 532, форма данных открывается
     на стр. 546 → поле вне формы.
  2. `profile.js` `start()`: `measure()` (228) и `crop.base` (229) до
     `dialog.showModal()` (235).
  3. `game/views.py:1868` `json.dumps(ctx['auto_set'])` → `game.html:2407`
     `{{ auto_set_json|safe }}`.
  4. `client_ip()` берёт первый из `X-Forwarded-For`; в nginx четыре
     `$proxy_add_x_forwarded_for` (стр. 196, 214, 359, 394).
  5. `catalog/views.py:524` — перед `rerank.apply()` только `seo.is_crawler`.
  6. `_stol_help.html:100` `help-sol-tpl` и 104 `help-part-answers-tpl` —
     без проверки входа.
  7. `teacher/picker.py` `cart_items()` (стр. 490):
     `Problem.objects.filter(pk__in=catalog_ids)` без видимости; ключей в
     `views_generate.py:484` сколько угодно.
  8. `game/leaderboard.py:78` и `:138` — `achieved=Min('created_at')`.
  9. `vp/board.py` `ranked_attempts()` — без `variant__is_published`.
- Notion прочитан: «Задачи» (В работе / Надо), 8 последних «Решений»
  (в т.ч. три от 24.09: «Решить заново», решения только вошедшим, умный
  поиск), карточки «Подозрительный трафик», «SEO-фикс», «Лидерборд по
  личным рекордам».

## Предположения

- `.env` в новую папку не копировал (секреты); для тестов не нужен.

## Следующий шаг

Фаза 1 — безопасность.
