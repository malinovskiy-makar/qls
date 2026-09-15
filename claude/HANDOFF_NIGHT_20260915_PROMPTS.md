# Сообщения владельца дословно — ночная сессия 15.09.2026

> Приложение к `claude/HANDOFF_NIGHT_20260915_FULL.md`. Здесь **дословно** все
> сообщения, которые владелец набрал сам: пять присылок промпта (три разные
> версии) и шесть коротких указаний по ходу работы. Тела навыков и
> автопродолжения среды, которые в транскрипте выглядят как сообщения
> пользователя, сюда не вошли — они не от владельца.
>
> Время московское. Длинный промпт присылался пять раз; у сообщений 17, 18, 20
> и 21 тело промпта совпадает дословно, различаются только приписки владельца
> сверху, поэтому повторы не дублируются — стоит ссылка.

---

### Сообщение 1 — 15.09.2026 07:10 МСК, запуск e5a27f43

Длина: 57448 знаков.

````text
Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09»
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09. Все решения владельца, на которых стоит сессия, приняты в чате 15.09 и перечислены в Фазе 0 — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Запись в локальную базу (Фаза 8) разрешена — она обратима по снимку.
Вопрос без ответа → запиши в журнал предположение, которое принял, и иди дальше. Единственное исключение — расхождение якорей в Фазе −1: тогда стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг `venv313\Scripts\python.exe scripts\run_tests.py --scope-from-git` (вывод в файл, код возврата читать сразу, `| tail` запрещён — он съедает код). Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Возьми за образец harness `test_design_canon`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` (следующий свободный номер смотри по `showmigrations problems`), `game` — с 0016. Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
ФАЗА −1. Сверка с реальностью
Ничего не меняй, пока не сверишь. Выведи в отчёт результат по каждому пункту.

1. `git status` — дерево чистое? Если нет — стоп.
2. `git branch --show-current`, `git log --oneline -3`. Если ветка `feat/night-20260915` уже существует — это повторный запуск: переключись на неё, прочитай журнал, продолжай.
3. `venv313\Scripts\python.exe --version` → 3.13.x; `venv313\Scripts\python.exe -c "import django; print(django.get_version())"` → 5.2.x.
4. `venv313\Scripts\python.exe manage.py showmigrations game | tail -5` — цепочка непрерывна до последнего применённого; новые — с 0016. `showmigrations problems | tail -3` — запомни последний номер.
5. `venv313\Scripts\python.exe manage.py check` → 0 ошибок.
6. Якоря — файлы существуют и содержат строки (проверь `grep`):
   * `templates/_feedback.html`: `function grabShot()`, число `4000`, правило `.fb-btn svg { width: 15px; height: 15px; }` внутри `<style>`.
   * `templates/_nav.html`: два вхождения `<button type="button" class="fb-btn"` и следом `<svg viewBox="0 0 24 24"` без атрибутов `width`/`height`.
   * `problems/feedback_options.py`: `FEEDBACK_OPTIONS`, `FEEDBACK_ALIASES`, `PAGE_KEY_RULES`, функция `options_for`.
   * `problems/views_platform.py`: `def api_feedback`, `FEEDBACK_MAX_SCREENSHOT`.
   * `problems/models_platform.py`: `class Feedback(models.Model)`.
   * `game/templates/game/game.html`: `function api(url, opts)` с телом `return fetch(url, opts).then(function (r) { return r.json(); });`; `function postAnswer(payload, onResult)`; `function prefetchNext()`; `function advance()`; `function tick(ts)`; `var inputLocked = true;`; глобальный `document.addEventListener('keydown', function (e) {` с ветками `if (state === 'playing')`; `function chartCurve(s)` с `var W = 400, H = 130, P = 8;`; `$('dm-create').addEventListener('click'`; `function listen(code)`; `function countdown(n)`; `<div class="duel-lobby" id="duel-lobby">`; `<div class="vs" id="vs" hidden>`; `<div class="entry-row" id="entry-row">`; `<section class="lb-card" id="lb-card">`; `id="entry-daily"`, `id="entry-duel"`, `id="entry-records"`; подключение `{% include '_feedback.html' %}` в самом низу.
   * `game/consumers.py`: `COUNTDOWN_S = 3`, `async def _announce_presence`, `async def duel_start`.
   * `game/views.py`: `@login_required` над `def duel_new`; `def api_answer`; `def _new_state`; `def api_question`.
   * `game/config.py`: `MODES` с ключами `bullet`, `blitz`, `rapid`, `classic`, `figure`; `DEFAULT_MODE = 'blitz'`; `MIN_PLAYABLE = 10`.
   * `game/state.py`: `TTL_SLACK = 600`, `DUEL_TTL`, функции `duel_join`, `duel_leave`.
   * `game/static/game/sound.js`: функция `audio`, объект `window.rushSound` с `isOn`, `toggle`, `correct`, `wrong`.
   * `catalog/rerank.py`: `def _build_corpus`, `def get_corpus`, `def build_pool`, `def _score_pool`, `def _log`, `def apply`.
   * `catalog/semantic.py`: `def is_enabled`, `def get_index`, `def search`.
   * `catalog/views.py`: `def _search_ids`, строки `response['X-Smart-Search'] = context['smart_search_status']`.
   * `catalog/templates/catalog/problem_list.html`: `<span class="ask-busy" aria-live="polite"><i></i>Ищу похожие задачи…</span>` и блок `{% if degraded %}`.
   * `catalog/templates/catalog/_catalog_js.html`: `form.classList.add('is-busy')`.
   * `catalog/placeholder_phrases.py`: `CATALOG_PHRASES`, `CATALOG_STOP_TEXT`.
   * `catalog/chat.py`: `PROFILE = 'catalog_chat'`, `HISTORY_LIMIT = 6`, `def answer(`; `catalog/views.py`: `def api_chat`; `catalog/templates/catalog/problem_detail.html`: `<section class="ai"`, `id="ai-sug"`, `id="ai-text"`, `id="copy-label"`.
   * `problems/ai/providers.py`: `class GLMProvider(BaseProvider)`, `def _user_content(self, user_text, images)`, `IMAGE_TYPES`; `problems/ai/core.py`: `def run(profile, user_text, schema, user,` с параметрами `provider`, `model`, `system`, `parse`, `log`, `check_budget`; `AI_DAILY_COST_CAPS` в `config/settings.py`.
   * `catalog/testplay.py`: `def game_of(problem, parts=None)`; `problems/models.py`: `class ProblemPart(models.Model)` с полями `label`, `statement`, `answer`, `solution`, `points`, `order`; `problems/answer_check.py`: `normalize_label`, `catalog_test_correct_labels`; `problems/problem_types.py`: `test_kind`, `MULTI`, `TEST_TYPE_VALUES`.
   * `reports/corpus_transfer_20260913/TEST_WIDGET_RECON.md` и `reports/corpus_transfer_20260913/dead_test_widget_ids.txt` (4 510 строк).
   * `deploy/entrypoint.sh`: `exec gunicorn config.wsgi:application` с `--max-requests 1000`.
   * `config/urls.py`: `path('api/feedback/', views_platform.api_feedback`.

Если хоть один якорь не совпал — остановись и напиши, что именно разошлось.
ФАЗА 0. Ветка, журнал, Notion
Ветка `feat/night-20260915` от актуального `main`. Создай `reports/night_20260915/JOURNAL.md` с таблицей фаз.
Notion «Задачи» (`39bb11c9-2bc1-81c4-b770-000b48caa895`): на каждую фазу 1–13 карточка, статус «Надо», направление по смыслу. Перед созданием — поиск по названию: часть тем уже заведена (например «Виджет теста ожил» и «Виджет теста не соберётся ни у одной из переносимых задач», «В каталоге нет поля короткого ответа», «Умный поиск открыт всем»). Нашёл существующую — не дублируй, добавь комментарий «делается в ночной сессии 15.09, фаза N» и веди её. Массовая запись в этой сессии согласована владельцем заранее.
Notion «Решения» (`39bb11c9-2bc1-81b9-9cfd-000b7f654c8f`): проверь поиском, есть ли карточки от 15.09 с названиями ниже. Нет — создай (дата 15.09.2026, автор — владелец, в чате с Claude). Это решения владельца, не твои:

1. Аналитика беты — своя таблица событий в Django, без внешних сервисов. Почему: закрытая бета друзей, нужны сырые события для глубокого разбора после беты; отвергнуты Яндекс.Метрика и PostHog (внешняя зависимость, данные не у нас).
2. Виджет тестов: варианты из текста условия переносятся в `ProblemPart`, блок вариантов вырезается из условия в базе обратимо, со снимком. Почему: данные становятся такими же, как у 1 434 живых виджетов, одна ветка рендера; отвергнут разбор при показе (два представления одной задачи).
3. Дуэль — строго синхронный старт. Пока соперник не зашёл — играть нельзя, только ждать или отменить. Отвергнуты асинхронная дуэль (нынешняя) и вариант со ссылкой «не ждать».
4. Чат на задаче: «Как решать» выдаёт метод и план без итогового ответа; «Проверь моё решение» оценивает честно, без баллов. Файлы — фото и PDF (PDF конвертируется в картинки на сервере). Модель — GLM-5.3.
5. Бесконечные тесты — внутри Wecon Rush на игровом пуле, без таймера, жизней и очков, с «назад/вперёд». Отвергнута отдельная страница на каталожном виджете (пул меньше).
6. Экраны Wecon Rush правятся по списку без макета, приёмка по скринам.
7. Кнопка «Плохая задача» — пять причин, одинаковая в каталоге и в игре, без снимка экрана; в игре открытие окна ставит забег на паузу.

Чекпоинт-коммит: `checkpoint: фаза 0 — ветка, журнал, карточки`.
ФАЗА 1. Игра: клавиши не пробивают модалы, забег умеет паузу
Дефект. Глобальный `keydown` в `game.html` в состоянии `playing` ловит пробел → `skip()`, цифры 1–6 → `answer()`/`toggleOption()`, Enter → `submitMulti()`/`submitNumeric()` без проверки, что открыт модал (окно «Проблема или предложение» `.fb-back`, окно выхода `#quit-modal`, окно фильтров) или что фокус стоит в текстовом поле. Человек печатает жалобу и одновременно пропускает вопросы. Таймер при этом идёт.
Что сделать.

1. В самом начале обработчика `keydown` — два раннних выхода: 

```js
if (isTypingTarget(e.target)) return;   // INPUT, TEXTAREA, SELECT, contenteditableif (modalIsOpen()) return;              // .fb-back, .rp-back, dialog[open], #quit-modal:not([hidden]), #fmodal:not([hidden])

```

Исключение: в режиме `numeric` поле ввода ответа — это INPUT, и Enter/пробел там должны работать как сейчас. Проверяй по `id` этого поля, а не по тегу.
2. Пауза забега. Рядом с `tick`: 

```js
var pausedAt = null;function rushPause()  { if (state !== 'playing' || pausedAt) return; pausedAt = performance.now(); cancelAnimationFrame(rafId); /* сердцебиение стоп, если шло */ }function rushResume() { if (!pausedAt) return; pausedAt = null; lastTick = performance.now(); rafId = requestAnimationFrame(tick); paintHud(); }

```

`timeLeft` во время паузы не меняется. Таймер-звук/сердцебиение останавливаются на паузе и возвращаются по `paintHud()`.
3. Единый механизм: `templates/_feedback.html` при открытии/закрытии окна шлёт `document.dispatchEvent(new CustomEvent('weco:modal', {detail: {open: true|false}}))`. То же делает новое окно «Плохая задача» (Фаза 5) и окно выхода. Игра слушает `weco:modal` и зовёт `rushPause`/`rushResume`. Так же ставь паузу при открытии окна фильтров, если оно доступно из игры.
4. Серверное время ответа (`elapsed_server` в `api_answer`) паузу не знает: бонус за скорость на этом вопросе сгорит. Это принято, не чинить; одна строка в журнал и комментарий в коде рядом с `rushPause`.

Тесты. Браузерный (Playwright, `serial`, причина — живой сервер + браузер) `game/tests/test_browser_modals.py`: забег в Блице на демо-пуле; открыть `.fb-btn`; в textarea набрать пробел, «1», Enter; инварианты: текст вопроса тот же, число отвеченных 0; `#hud-timer` через 2 с паузы отличается от значения на момент открытия не более чем на 0,1 с; после закрытия таймер снова идёт (через 1,5 с уменьшился ≥ 1 с). Зубастость: с возвращённым дефектом тест красный.
Чекпоинт-коммит.
ФАЗА 2. Игра: фриз с горящей кнопкой
Корень. `api()` = `fetch(...).then(r => r.json())`: не-JSON ответ (502/504 от nginx, 429, HTML страницы входа) → отклонённый промис без `catch` → `inputLocked` остаётся `true` навсегда. Второй путь: `postAnswer` при `d.error` снимает блокировку, но ничего не показывает и игру не двигает — при `reason: 'no_run'` (состояние забега истекло по TTL или вытеснено Redis с `allkeys-lru`) это выглядит как заморозка. Третий: `prefetchNext()` без `catch` → `advance()` крутится по `setTimeout(advance, 120)` вечно.
Что сделать.

1. `api()`: не-OK ответ превращать в объект, а не в исключение: 

```js
return fetch(url, opts).then(function (r) {  if (r.ok) return r.json();  return r.json().catch(function () { return {}; }).then(function (d) {    d.error = d.error || ('HTTP ' + r.status); d.status = r.status; return d;  });});

```

Сетевой сбой (нет соединения) по-прежнему отклоняет промис — у каждого вызывающего появляется `.catch`.
2. `postAnswer`: одна функция `answerFailed(d)`:
   * `d.reason === 'no_run'` → оверлей «Забег потерян: соединение или время ожидания. Начните новый» с одной кнопкой «На старт» (`location.href = '/game/'`);
   * `d.status === 409` («Вопрос уже отвечен») → считать отвеченным: `advance()`;
   * иначе → `inputLocked = false`, снять подсветку выбранной кнопки, показать тост «Нет связи. Нажмите ответ ещё раз» (свой маленький `#net-toast`, 3 с; без эмодзи). `.catch` сетевого сбоя — тот же путь.
3. `prefetchNext()`: `catch` с повтором через 300 / 800 / 1 600 мс (три попытки), потом флаг `prefetchFailed`. `advance()`: если ждёт буфер дольше 6 с суммарно — ещё один `prefetchNext()`; если `prefetchFailed` и буфера нет — тост с кнопкой «Повторить».
4. `startRun()` и остальные вызовы `api(...).then(` без `catch` — пройди по всем (их ~10), добавь `catch` с честным сообщением там, где отсутствие ответа замораживает экран. Где не замораживает — не трогай.

Тесты. Playwright `game/tests/test_browser_freeze.py`: перехват `/game/api/answer/` → один раз ответить 502 с HTML; после клика по варианту инварианты: тост виден, через 300 мс кнопки вариантов снова кликабельны (второй клик отправляет запрос — перехватчик считает вызовы = 2). Второй кейс: ответ `{"error": "Забег не начат", "reason": "no_run"}` со статусом 400 → оверлей с кнопкой «На старт». Зубастость обоих.
Чекпоинт-коммит.
ФАЗА 3. Огромная иконка в шапке и подпись на графике
3а. FOUC значка «Проблема или предложение». SVG в `_nav.html` (две кнопки) задан только `viewBox`, а размер `.fb-btn svg { width: 15px }` лежит в `<style>` файла `_feedback.html`, который подключается в самом конце body. Пока страница грузится, значок рисуется в размере по умолчанию.
Фикс: (1) добавь `width="15" height="15"` обоим SVG в `_nav.html` и SVG кнопки в `login.html`/`register.html`; (2) перенеси правила `.fb-btn`, `.fb-btn svg`, `.fb-btn.is-busy`, медиа-запрос 1420 и `.fb-btn--onpage` из `_feedback.html` туда, где живут стили шапки и разбираются ДО разметки кнопки (проверь, где у `_nav.html` стили — в `<head>` базовых шаблонов или в самом партиале; цель — правило разобрано раньше разметки). Комментарий с причиной перенеси вместе с правилами. В `_feedback.html` остаются только стили окна, кружка Telegram и печати. Инвариант: `grep -n "\.fb-btn" templates/_feedback.html` не находит правил кнопки; `test_design_canon` зелёный; страницы каталога, игры, calc2, кабинета, входа отдают 200 и содержат `class="fb-btn"` (тест шаблонов).
3б. Числа «Динамики забега» режутся. В `chartCurve` подпись последнего значения ставится на `y = yScore(last) − 5`; последнее значение почти всегда максимум, `yScore(max) = P = 8`, подпись уезжает выше `viewBox`. Введи верхний отступ под подпись: `var PT = 22;` и `yScore = H − P − (v / maxScore) * (H − P − PT)`, подпись `y = yScore(last) − 6` (теперь ≥ 16). Инвариант вынеси в комментарий и в тест: чистую функцию расчёта `y` вынеси в маленький модуль `game/static/game/chart_math.js` (или проверь через `node -e` в тесте, как у calc2), тест: для `scores=[0, 10, 20]`, `H=130`, `P=8` подпись `y ≥ 12` и все точки в `[P, H − P]`.
Чекпоинт-коммит.
ФАЗА 4. «Проблема или предложение»: варианты по экранам, снимок, модальные события
4а. Варианты. `problems/feedback_options.py` — замени списки. Владелец попросил убрать бессмысленные варианты и говорить словами школьника. Новые значения (ровно эти, порядок сохранить):

```python
'calc2':   ['График построен неправильно', 'Модель не поняла мою формулу',
            'Не работают точки, площади или подписи', 'Ползунки или параметры ведут себя странно',
            'Не получилось скачать или экспортировать', 'Медленно или подвисает'],
'catalog': ['Поиск не находит нужное', 'Поиск слишком долгий', 'Фильтры работают не так',
            'Тест не даёт выбрать вариант', 'Формулы или картинки отображаются неправильно',
            'Задача открывается долго или не открывается'],
'game':    ['Игра зависла, кнопки не нажимаются', 'Вопрос с ошибкой или без верного ответа',
            'Таймер, очки или жизни считаются странно', 'Дуэль не соединилась или не стартовала',
            'Звук или анимация мешают', 'Не понял правила'],
'lessons': ['Не могу вступить в группу, код не работает', 'Работа не сдаётся или не сохраняется',
            'Проверка или баллы неверные', 'Не находится нужная задача для домашки'],
'stats':   ['Цифры выглядят неверно', 'Не могу войти или зарегистрироваться',
            'Не сохраняются данные профиля', 'Не загружается аватар'],
'home':    ['Непонятно, с чего начать', 'Не нашёл, где искать задачи',
            'Что-то не открывается', 'Плохо видно или плохо читается'],
'textbook': ['В тексте ошибка или опечатка', 'Формулы отображаются неправильно',
            'Не открывается нужная глава', 'Непонятно объяснено'],
'other':   ['Ошибка в данных: дата, льгота, ссылка', 'Что-то не открывается',
            'Непонятно, что делать на экране', 'Плохо видно или плохо читается'],

```

`home` и `textbook` убрать из `FEEDBACK_ALIASES` (у них теперь свои списки), остальные алиасы оставить. Экран «задача» (`/catalog/problem/`) — остаётся алиасом `catalog`: у него появится своя кнопка «Плохая задача» (Фаза 5), и жалобы на саму задачу пойдут туда. Обнови тесты `feedback_options`.
4б. Снимок: причина отсутствия. В `grabShot()` резолвить `{blob, note}`, где `note` ∈ `ok | timeout | error | nolib`; таймаут 4 000 → 6 000 мс. В форму добавить `screenshot_note`; в модель `Feedback` — поле `screenshot_note = CharField(max_length=16, blank=True)` (миграция `problems`); в админке — в `list_display` после `has_shot`. Тест `api_feedback`: поле сохраняется, битые значения обрезаются до 16 символов.
4в. Модальные события. См. Фазу 1: `_feedback.html` шлёт `weco:modal` при `build()` и `close()`. Проверь, что `Escape` внутри окна закрывает его, а до игры не долетает (`stopPropagation` или порядок обработчиков).
Чекпоинт-коммит.
ФАЗА 5. Кнопка «Плохая задача» в каталоге и в игре
Смысл. Школьник видит битую задачу или тест и одной кнопкой говорит, что не так. Пять причин, без снимка экрана. Одинаковая кнопка в шапке задачи в каталоге (рядом со «Скопировать ссылку») и под каждым вопросом в Wecon Rush.
Модель в `problems/models_platform.py` (рядом с `Feedback`):

```python
class ProblemReport(models.Model):
    class Kind(models.TextChoices):
        NOT_PROBLEM = 'not_problem', 'Это вообще не задача'
        NO_QUESTION = 'no_question', 'Непонятно, что нужно найти'
        FIGURE      = 'figure',      'Графика или таблицы нет, либо они неправильные'
        DISPLAY     = 'display',     'Плохо отображается: формулы, символы, обрывки текста'
        OTHER       = 'other',       'Другое'
    user = FK(AUTH_USER_MODEL, SET_NULL, null=True, blank=True)   # гостю можно
    problem = FK('problems.Problem', SET_NULL, null=True, blank=True)
    game_question_id = PositiveIntegerField(null=True, blank=True)  # без FK: game зависит от problems, не наоборот
    source = CharField(max_length=16)          # 'catalog' | 'game'
    kind = CharField(max_length=16, choices=Kind.choices)
    text = TextField(blank=True)               # обязателен при kind=other
    url = CharField(max_length=500, blank=True)
    user_agent = CharField(max_length=300, blank=True)
    created_at = DateTimeField(auto_now_add=True, db_index=True)
    handled = BooleanField(default=False)
    note = TextField(blank=True)

```

Миграция `problems`. Админка по образцу `FeedbackAdmin`: список `created_at, source, kind, problem, game_question_id, who, short, handled`, фильтры по `kind`, `source`, `handled`; `problem` ссылкой на страницу задачи. Для `game` найди, как `GameQuestion` знает свою задачу (в `api_answer` в ответ кладётся `problem_id`) — заполняй `problem`, если связь есть.
API `POST /api/problem-report/` в `problems/views_platform.py` рядом с `api_feedback`: CSRF обязателен, гостю можно, тот же `ratelimit` (свой scope `problem_report`), валидация: `kind` из списка; `other` без `text` → 400 «Напишите, что не так»; `problem_id`/`game_question_id` — целые, хотя бы одно; `text` ≤ 2 000. Ответ `{'ok': True, 'id': …}`.
Партиал `templates/_problem_report.html`: стили + разметка окна + скрипт, по образцу `_feedback.html` (те же классы окна, префикс `rp-`: `.rp-back`, `.rp-box`). Заголовок «Что не так с этой задачей?», подзаголовок «Одна кнопка — и мы починим», пять радиокнопок с текстами `Kind`, textarea «Расскажите подробнее (необязательно)» (при «Другое» — обязательно, подпись меняется), кнопка «Отправить», после отправки «Спасибо, разберёмся» и закрытие через 1,5 с. Открывается кликом по любому `.btn-report` с `data-problem-id` и/или `data-game-question-id` и `data-source`. Шлёт `weco:modal` (Фаза 1).
Кнопка — общий класс `.btn-report`, вид одинаковый в обоих местах: тихая кнопка со значком (SVG «флажок» или «треугольник с восклицательным знаком», 15 px) и подписью «Плохая задача?». В каталоге — `problem_detail.html`, в ту же строку действий, где `#copy-label`, тем же классом кнопки, что и «Скопировать ссылку», плюс `.btn-report`. Если в `_problem_modal.html` есть строка действий со «Скопировать ссылку» — добавь и туда, если нет — не добавляй. В игре — на экране `#screen-play` под блоком вариантов/поля ввода, справа, мелко; `data-game-question-id` обновляется в `showQuestion(q)`. Окно открыто → пауза и блок клавиш (Фаза 1).
Тесты: API (валидация, гость, лимит, `other` без текста); страница задачи содержит `btn-report` с `data-problem-id`; страница игры содержит `btn-report`; партиал подключён там же, где `_feedback.html` (все базовые шаблоны).
Чекпоинт-коммит.
ФАЗА 6. Умный поиск: прогрев, разбивка времени, честная плашка, документ для боя
Что известно. Три ноги: dense (BGE-M3 через контейнер `search`), bm25 (индекс в памяти воркера), реранжирование GLM-5.3-Flash. `_build_corpus()` строит bm25-индекс по всему видимому каталогу лениво, при первом запросе, в каждом gunicorn-воркере отдельно; gunicorn перезапускает воркеры каждые ~1 000 запросов (`--max-requests 1000`). После переноса корпуса каталог вырос с 5 090 до 14 070 задач — холодный воркер платит за сборку на каждом «первом» поиске. Проверено владельцем 15.09 с боя: `X-Smart-Search: rerank` — реранж GLM на проде включён и работает на bm25-пуле; плотной ноги нет. Значит «20+ с» — это сборка индекса в холодном воркере плюс хвост задержки модели, а не выключенный флаг. То же у `semantic.get_index()` (все векторы из базы в память). Отсюда «20+ с вместо 7». На бою по docs/SERVER.md контейнер `search` не развёрнут и `SEMANTIC_SEARCH_ENABLED=0` — плашка «Ищем по словам» честная.
6а. Замер. До правок измерь локально в `manage.py shell`: `time` сборки `rerank.get_corpus()` и `semantic.get_index()` (по два прогона: холодный/тёплый), число задач в корпусе, RSS процесса до и после (`psutil` есть? если нет — `resource`/диспетчер по коду не трогать, просто запиши, что не измерил). Числа — в журнал и в `docs/EMBEDDINGS.md`.
6б. Прогрев воркера. Новый файл `config/gunicorn_conf.py` с хуком `post_worker_init(worker)`: за флагом `SMART_SEARCH_WARMUP` (по умолчанию `1`; в тестах не задействован), в `try/except`, зовёт `catalog.rerank.get_corpus()` и, если `semantic.is_enabled()`, `catalog.semantic.get_index()`; логирует `прогрев: корпус N задач за X с, индекс M векторов за Y с`. В `deploy/entrypoint.sh` к команде gunicorn добавить `-c /app/config/gunicorn_conf.py` (проверь, куда Dockerfile кладёт проект, и что путь верный; для dev-площадки `deploy/docker-compose.dev-site.yml` — тот же entrypoint?). Прогрев занимает воркер до того, как он берёт запросы; остальные воркеры при этом обслуживают. Функцию прогрева вынеси в `catalog/warmup.py` и покрой тестом (вызывается, логирует, не падает при пустой базе, при `SMART_SEARCH_WARMUP=0` ничего не делает).
6в. Разбивка времени в логе. В `rerank._log` и строке `reports/smart_search_log.jsonl` добавь `corpus_build_seconds` (0, если индекс был тёплый), `pool_seconds`, `model_seconds` (есть), `total_seconds` (есть). Добавь заголовок ответа `X-Smart-Search-Ms` (целое, общее время поиска в мс) рядом с `X-Smart-Search` — чтобы владелец мерил с Mac одним `curl -sI`. Тесты на оба поля/заголовок.
6г. Живая проверка с ключом. Если в локальном `.env` есть `GLM_API_KEY` и `SMART_SEARCH_RERANK=1`: `manage.py rerank_trace "налог на монополиста"` и ещё два запроса (короткий по теме, описание своими словами) — пул по ногам, пачки, `model_seconds`, статус — в журнал. Если ключа нет — запиши и иди дальше. Плотную ногу локально попробуй: `docker compose -f docker-compose.dev.yml -f docker-compose.dev.local.yml up -d search` + `SEARCH_SERVICE_URL=http://127.0.0.1:8001`; Docker не поднят — запиши, не чини.
6д. Плашка. `{% if degraded %}`: когда `smart_search_status == 'rerank'` (GLM отработал на bm25-пуле), текст: «Ищем по словам с умной сортировкой. Поиск по смыслу пока выключен — результаты могут быть беднее обычного.» Иначе текст прежний. Передай статус в шаблон.
6е. Документ для владельца. В `docs/SERVER.md` раздел «Включение смысловой ноги на бою» — точные команды (проверь пути и имена по compose):

```bash
free -m                                   # нужно ≥ 3 ГБ свободных вместе с buff/cache
cd /srv/weconomics/app/deploy
docker compose build search && docker compose up -d search
docker compose logs -f search             # ждать загрузки модели (минуты)
docker compose exec web curl -fsS http://search:8001/healthz
# в /srv/weconomics/.env: SEMANTIC_SEARCH_ENABLED=1  SMART_SEARCH_RERANK=1  SEARCH_SERVICE_URL=http://search:8001
docker compose up -d web ws
curl -sI "https://weconomics.ai/catalog/?q=налог" | grep -i x-smart-search

```

Плюс проверка, что у боевых задач есть векторы (поле `embedding` попадает в дамп `dump_for_deploy`? — проверь по коду и напиши честно) и что при их отсутствии нужен `build_embeddings` изнутри контейнера. Обнови `docs/EMBEDDINGS.md` (прогрев, поля лога).
Чекпоинт-коммит.
ФАЗА 7. Поиск: анимация ожидания с фразами
Поиск — обычная отправка формы; пока грузится новая страница, старая показывает `.ask-busy`. Сейчас там «Ищу похожие задачи…».

1. `catalog/placeholder_phrases.py` — константа `SEARCH_BUSY_PHRASES`, первой идёт `думается думается…`, затем (порядок случайный при каждом запросе, первая всегда первая): `ищу равновесие…`, `сдвигаю кривую спроса…`, `сравниваю предельные выгоды и издержки…`, `считаю площадь под кривой…`, `проверяю условие первого порядка…`, `перебираю КПВ…`, `дисконтирую варианты…`, `ищу точку Курно…`, `заглядываю в ящик Эджворта…`, `спрашиваю у Лаффера…`, `ceteris paribus…`, `максимизирую полезность выдачи…`, `раскладываю по Парето…`, `ещё чуть-чуть, модель думает…`.
2. Шаблон: `<span class="ask-busy"><i></i><span id="ask-busy-text">думается думается…</span></span>`, фразы — через `json_script`. Скрипт в `_catalog_js.html`: при `is-busy` менять фразу каждые 1 600 мс с плавной сменой (opacity 160 мс); `<i>` — маленький крутящийся ring 12 px или три точки (уже есть? проверь CSS `.ask-busy i`; если анимации нет — добавь, скромно). При `prefers-reduced-motion` — статичная первая фраза, без ring-анимации.
3. Появление выдачи: если `searched`, карточкам результатов класс `ct-appear` с лёгким stagger (первые 12 карточек, шаг 40 мс, длительность 220 мс, только opacity/translateY 4 px). При reduced-motion — выключено.
4. Ничего крупного и кричащего: размеры и цвета — из токенов, без новых цветов.

Тесты: шаблон содержит `думается думается…` и не содержит «Ищу похожие задачи»; фразы отдаются через `json_script`; `test_design_canon` зелёный.
Чекпоинт-коммит.
ФАЗА 8. Виджет тестов: подпункты из текста условия (запись в локальную базу)
Факты. По `TEST_WIDGET_RECON.md`: мёртвых виджетов 4 527, из них у 4 510 нет `ProblemPart` вовсе: 3 956 — варианты записаны текстом в условии (2 460 с шапкой «Варианты ответа:», 1 496 без шапки), 554 — `верно_неверно` без подпунктов, `answer` ∈ {Верно, Неверно}. Живой виджет = `ProblemPart` с меткой (`normalize_label`) и текстом варианта; верные метки читаются из `problem.answer` через `catalog_test_correct_labels`. Решение владельца: создать настоящие подпункты и вырезать блок вариантов из условия в базе, обратимо, со снимком — чтобы данные были как у 1 434 живых.
8а. Разбор — чистая функция `problems/test_options_parse.py`: `parse_options(statement) -> ParsedOptions | None` с полями `stem`, `options: [(label, text)]`, `header: bool`, `style` (`numbered_lettered` — «1. (a) …», `lettered` — «а) …», `numbered` — «1) …»). Правила:

* блок вариантов — только хвост условия: с шапки (`Варианты ответа:`, `Варианты ответов:`, `Варианты:`, регистр и двоеточие/точка гибко) или с первой строки-варианта до конца текста; после блока ничего нет;
* строка-варианта: `^\s*(\d{1,2})[.)]\s*\(?([a-zа-яё])\)?[.)]?\s+(.+)$` (номер + буква), либо `^\s*([а-яёa-z])[.)]\s+(.+)$`, либо `^\s*(\d{1,2})[.)]\s+(.+)$`; один стиль на весь блок, ≥ 2 строк, номера/буквы по порядку без пропусков;
* текст варианта: срезать завершающие `;`/`.`, схлопнуть пробелы; пустой → None;
* метки уникальны после `normalize_label`;
* ложные срабатывания запрещены: нумерованные подвопросы («1. Найдите равновесие. 2. Постройте график») — это задачи, не тесты; поэтому функция зовётся только для `problem_type` тестовых видов `single`/`multi` (`problem_types.test_kind`) и только при нулевом числе подпунктов, а строки с глаголом-заданием в начале («найдите», «постройте», «определите», «рассчитайте», «докажите», «объясните») в стиле `numbered` → None;
* `stem` = условие без блока и шапки, обрезка хвостовых пробелов/переносов, не пустой. Для `верно_неверно` (`boolean`): подпункты по образцу живых. Сначала посмотри, как хранятся подпункты у живой `верно_неверно` задачи (`ProblemPart` по `problem_type` и `parts__isnull=False`): какие `label`, `statement`, `answer`. Повтори ровно этот формат. Условие таких задач не меняется.

8б. Команда `problems/management/commands/test_options_from_statement.py`: `--dry-run` (по умолчанию), `--apply`, `--revert <snapshot.json>`, `--ids-file` (по умолчанию `reports/corpus_transfer_20260913/dead_test_widget_ids.txt`, но объём проверяется заново по базе: тестовый вид и 0 подпунктов), `--limit N`, `--report DIR` (по умолчанию `reports/night_20260915/test_options/`). Для каждой задачи: разбор → верные метки `catalog_test_correct_labels(problem)` (должны быть непустыми и ⊆ разобранных; `single` → ровно одна; иначе причина `answer_mismatch`) → план: создать подпункты (`label`, `statement`=текст, `answer` — по формату живых: посмотри, что там лежит у живых вариантов, и скопируй соглашение; `order` по порядку; `points` как у живых) и записать `statement = stem`. Поле `answer` `Problem` не трогается. `content_status`, `human_review`, `status` не трогаются.

* `--dry-run`: ничего не пишет; отчёт `REPORT.md`: счётчики по причинам (`parsed`, `no_block`, `mixed_style`, `answer_mismatch`, `single_multi_correct`, `verb_like_subquestion`, `boolean_synthetic`), гистограмма числа вариантов, 20 случайных примеров «было / стало» (полный текст условия до и после, список вариантов, верные метки) — этот отчёт владелец читает утром.
* `--apply`: транзакция; перед записью — снимок `snapshot_<timestamp>.json`: `{problem_id: {"statement_before": …, "part_ids": […]}}`; в конце инвариант: для каждой применённой задачи `testplay.game_of(problem)` не `None` — иначе откат транзакции и стоп.
* `--revert <snapshot>`: вернуть `statement` побайтно, удалить ровно созданные `part_ids` (если подпункт с тех пор изменён — не удалять, сообщить); после `--revert` повторный `--dry-run` находит те же кандидаты.
* Идемпотентность: второй `--apply` подряд ничего не меняет (кандидатов 0).

8в. Тесты (`problems/tests/test_test_options_parse.py`, `test_test_options_command.py`): ≥ 10 фикстур разбора — оба стиля, с шапкой и без, `;` и `.` на концах, кириллица/латиница в метках, пропуск номера → None, нумерованные подвопросы с глаголами → None, вариант из одной строки → None; команда: dry-run не пишет (счётчик `Problem`/`ProblemPart` не меняется), apply создаёт и переписывает, `game_of` жив, revert возвращает байт-в-байт и удаляет части, apply идемпотентен. Зубастость каждого.
8г. Применение локально. После зелёных тестов: `--dry-run` на полном объёме → прочитай отчёт сам, проверь 20 примеров на здравый смысл → `--apply`. Числа (применено / пропущено по причинам / стало живых виджетов по `game_of` на видимом каталоге до и после) — в журнал и в отчёт. Замечание для владельца: у переписанных условий устареет хеш эмбеддинга (`build_embeddings --stale` их подхватит) — в журнал, не запускать.
8д. Для боя (в итоговый отчёт): команда та же, изнутри контейнера: `docker compose exec web python manage.py test_options_from_statement --dry-run --report /app/reports/test_options_prod` → владелец читает отчёт → `--apply`. Прод не трогать.
Чекпоинт-коммит.
ФАЗА 9. Аналитика беты: своя таблица событий
Решение владельца: без внешних сервисов. Собираем сырые события — клики, экраны, время на экране, пути — в свою таблицу; анализ будет после беты. Про конфиденциальность в этой бете не думаем (согласие участников есть), но ничего из профиля сверх `user` и cookie посетителя не пишем.
Модель `problems/models_platform.py`:

```python
class Event(models.Model):
    ts = DateTimeField(auto_now_add=True, db_index=True)
    user = FK(AUTH_USER_MODEL, SET_NULL, null=True, blank=True)
    visitor = CharField(max_length=40, db_index=True)   # cookie weco_vid (uuid4), ставит скрипт
    session_key = CharField(max_length=40, blank=True)
    page_key = CharField(max_length=32, db_index=True)  # feedback_options.page_key_for(path)
    path = CharField(max_length=500)
    name = CharField(max_length=48, db_index=True)      # page_view, page_leave, click, search, …
    props = JSONField(default=dict, blank=True)
    duration_ms = PositiveIntegerField(null=True, blank=True)
    viewport = CharField(max_length=16, blank=True)
    user_agent = CharField(max_length=200, blank=True)
    class Meta: indexes = [Index(fields=['name', 'ts']), Index(fields=['visitor', 'ts'])]

```

Миграция `problems`.
API `POST /api/track/` (`problems/views_platform.py`): тело JSON `{"events": [{name, path, props, duration_ms, viewport, t}]}`, ≤ 50 событий за запрос, `props` ≤ 2 КБ после сериализации (лишнее — обрезать, не отвергать всё), гостю можно. `navigator.sendBeacon` не умеет ставить заголовки, поэтому вьюха `csrf_exempt`, а вместо CSRF — ручная проверка происхождения: заголовок `Origin` (или `Referer`, если `Origin` нет) обязан быть нашим хостом из `ALLOWED_HOSTS`, иначе 403; плюс `ratelimit` по `visitor`: не больше 600 событий за 10 минут. Запиши это в `docs/SECURITY.md` («почему csrf_exempt и что вместо»). `page_key` считает сервер по `path`.
Скрипт `static/track.js` (≤ 200 строк, без зависимостей), подключается во всех базовых шаблонах рядом с `_feedback.html` (те же семь мест). Что делает:

* cookie `weco_vid` (uuid4, год, `SameSite=Lax`), если нет;
* `page_view` при загрузке (`props.referrer`), `page_leave` при `pagehide` / `visibilitychange→hidden` с `duration_ms` активного времени (счёт стоит, пока вкладка скрыта); отправка `sendBeacon`;
* `click` — делегированный слушатель на `a, button, [role=button], input[type=submit]`: `props = {text: (aria-label || textContent).trim().slice(0, 60), id, cls: первые два класса, href}`; клики внутри окон обратной связи и «плохой задачи» — тоже (там кнопки);
* `window.weco = {track(name, props)}` для явных событий;
* очередь: сброс каждые 5 с, или при 20 событиях, или на `pagehide`; `fetch(..., {keepalive: true})` как запасной путь, если `sendBeacon` нет. Никакого учёта Do-Not-Track — решение владельца.

Явные события (через `weco.track`):

* игра: `game_start {mode, filtered}`, `game_answer {mode, correct, skip, elapsed_ms, number}`, `game_end {mode, reason, score, answered, correct}`, `duel_create`, `duel_start`, `practice_start`, `practice_end {answered, correct}`;
* поиск: сервер кладёт в контейнер выдачи `data-search-status="{{ smart_search_status }}" data-search-total="{{ total }}" data-search-degraded`, скрипт при `searched` шлёт `search {q_len, status, total, degraded}`; при отправке формы — `search_submit {q_len}`;
* каталог: `problem_open {problem_id}` (страница и модалка), `test_answer {problem_id, correct, attempt}`, `copy_link`;
* чат: `chat_send {mode, has_file}` (Фаза 10); обратная связь: `feedback_send {kind}`; плохая задача: `report_send {kind, source}`. Ищи уже существующие точки (`showQuestion`, `endRun`, `openCatalogModal`, отправка форм) и добавляй по одной строке — не переписывай функции.

Админка `EventAdmin`: список `ts, name, page_key, path, who, visitor(8)`, фильтры `name`, `page_key`, `user`, `date_hierarchy`, поиск по `path`, `visitor`. Команда `analytics_export --since YYYY-MM-DD [--until] --out FILE` → CSV (плоские колонки + `props` JSON-строкой).
Тесты: API (валидация, ≤ 50, обрезка props, чужой `Origin` → 403, лимит), `page_key` считается сервером, `Event` создаётся, скрипт подключён во всех базовых шаблонах (тест по списку файлов), команда экспорта пишет CSV.
Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — ПЕРВЫМ ДЕЛОМ. Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (из 10.0), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель уходит список `(mime, bytes)`, максимум 5. Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения — или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков — просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец забега) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль — только с аккаунтом: соперника нужно как-то называть» с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но забег ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге забега дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время забега; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев, поля лога, заголовок `X-Smart-Search-Ms`;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам: адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.
````

### Сообщение 5 — 15.09.2026 12:45 МСК, запуск e5a27f43

Длина: 26 знаков.

````text
сделай хэндофф этой сессии
````

### Сообщение 6 — 15.09.2026 13:26 МСК, запуск 206b05bd

Длина: 46462 знаков.

Отличается от сообщения 1: убраны разделы ФАЗА −1, ФАЗА 0, ФАЗА 1, ФАЗА 2, ФАЗА 3, ФАЗА 4, ФАЗА 5 (сделаны в первом запуске, вместо них строка «ФАЗЫ −1…5 — сделаны в первом запуске»); добавлен раздел «ФАЗА 6½. Пауза засчитывается: серверная фиксация с потолком»; переписана преамбула (заголовок «ПРОДОЛЖЕНИЕ с Фазы 6», требование сначала прочитать claude/HANDOFF_NIGHT_20260915.md и reports/night_20260915/JOURNAL.md, HEAD `c34bce28`, разрешение мигрировать рабочую базу `db.sqlite3`, новый блок «Дополнение для продолжения (после первого запуска)» с состоянием фаз, порядком старта из пяти пунктов, решениями владельца по вопросам хэндоффа и списком найденных правил проекта); изменены разделы ФАЗА 6 (прогрев в фоновом потоке 6б′, новый пункт 6е′ о перевозе векторов файлом), ФАЗА 8 (требование мигрированной рабочей базы), ФАЗА 9 (track.js во все девять шаблонов вместо семи), ФАЗА 10 (правка на один знак), ФАЗА 11 («раунд» вместо «забег», окно «Закончить?» шлёт weco:modal), ФАЗА 12 (без длинных тире, «раунд» вместо «забег»), ФАЗА 14 (в документы добавлены пауза с серверной фиксацией, экспорт векторов, команда embeddings_export_vectors, приёмку за фазы 1–5 не переписывать, а дополнять); без изменений разделы ФАЗА 7 и ФАЗА 13

````text
Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09», ПРОДОЛЖЕНИЕ с Фазы 6
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Затем — обязательно — `claude/HANDOFF_NIGHT_20260915.md` и `reports/night_20260915/JOURNAL.md`: это состояние после первого запуска. Раздел «Дополнение для продолжения» ниже важнее любых расхождений между ними и текстом фаз.
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09; продолжение — по хэндоффу первого запуска (ветка `feat/night-20260915`, HEAD `c34bce28` или новее). Все решения владельца, на которых стоит сессия, приняты в чате 15.09, записаны в Notion «Решения» (семь карточек от 15.09) и повторены в «Дополнении» ниже — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Рабочая локальная база `db.sqlite3`: владелец разрешил накатить на неё миграции и применить подпункты тестов (Фаза 8, обратимо по снимку). `runserver` у владельца не запущен; перед `migrate` всё равно проверь порт 8000 (`netstat -ano | findstr :8000`) — занят → не мигрируй, журнал, Фазу 8г пропусти.
Вопрос без ответа → запиши в журнал предположение, которое принял, и иди дальше. Единственное исключение — расхождение якорей в Фазе −1: тогда стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг явными лейблами (`scripts\run_tests.py <app.tests.module> …`): `--scope-from-git` на общем шаблоне `templates/_*.html` раздувается до полного шага A (~112 мин), это найдено в первом запуске. Вывод в файл `> лог 2>&1`, код возврата читать сразу, числа брать из лога, а не из памяти (инструмент иногда теряет вывод); `| tail` запрещён — он съедает код. Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Образец уже есть в ветке: раннер `game/tests/browser_*.mjs` (Playwright в node, JSON после маркера `###RUSH-JSON###`) + питон-обёртка на `StaticLiveServerTestCase`; запуск `scripts/run_tests.py game.tests.test_browser_modals --only-serial`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` — следующая 0067, `game` — с 0016. В тестах по странице — `assertTrue(x in html, 'коротко')`, не `assertIn` (при падении печатает весь HTML). Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
Дополнение для продолжения (после первого запуска)
Состояние. Фазы −1…5 закрыты (клавиши и пауза, фриз, значок и график, варианты обратной связи и причина пустого снимка, кнопка «Плохая задача?»), миграции `problems/0065`, `0066` созданы, но на рабочую базу не накатаны. Фаза 6 наполовину: `catalog/warmup.py`, `config/gunicorn_conf.py`, `-c` в `entrypoint.sh`, поля `corpus_build_seconds`/`pool_seconds` в `rerank.py`; четыре теста красные намеренно (`test_smart_search_timing`: три на заголовок `X-Smart-Search-Ms`, один на текст плашки) — реализации ещё нет. Прогрев выключен до появления настройки `SMART_SEARCH_WARMUP`. Второй запуск успел только повторить сверку и собрать факты для Фазы 6.
Старт этого запуска, по порядку:

1. `git status`, `git diff --stat`. Неотслеживаемые личные файлы владельца в корне (`.txt`, `Claude outputs/`, `kachat_vektora.ps1`, старые хэндоффы и т. п.) — не трогать, не коммитить. Изменения в отслеживаемых файлах, оставшиеся от второго окна: относятся к Фазе 6 → коммит `checkpoint: фаза 6 — остатки второго запуска`; непонятно чьи → `git stash push -m night-leftovers`, запись в журнал.
2. Сверку якорей Фазы −1 не повторяй целиком: шесть известных расхождений описаны в хэндоффе и ожидаемы. Достаточно `manage.py check`, ветка, HEAD.
3. Рабочая база: `manage.py migrate` (разрешено, см. правила; порт 8000 проверить). Результат — в журнал.
4. Временные файлы первого запуска в `%LOCALAPPDATA%\Temp\claude\C--Users-shipu-qls\…\scratchpad\` (копия базы `db_copy.sqlite3` 1,3 ГБ, `zero_*.sqlite3`) — удалить, место нужно.
5. Notion: карточку Фазы 6 держи «В работе»; из двух одинаковых карточек 13.09 в «Решениях» («Перенос корпуса на прод — весь видимый каталог минус подтверждённый брак…», id `…81eab96af7c3968ec8b3` и `…81058c5fe744a6a4fbda`) оставь созданную раньше, вторую переведи в «На удаление» с комментарием «дубль». Ничего не удалять.

Решения владельца по вопросам хэндоффа:

* Пауза засчитывается — раунд с открытым окном не снимается с таблицы лидеров. Реализация — Фаза 6½ ниже, с серверной фиксацией и потолком.
* Прогрев по умолчанию включён, но в фоновом потоке, чтобы арбитр gunicorn не убивал воркер — Фаза 6, пункт 6б′.
* Векторы на бой едут файлом из локальной базы — Фаза 6, пункт 6е′.
* Рабочую базу мигрировать и применять подпункты локально — разрешено.

Правила проекта, которые первый запуск нашёл (обязательны для фаз 7–14):

* На экране игры только «раунд», слово «забег» запрещено тестом (`game.tests.test_wecon_texts.RoundNotRaceTests`). Везде ниже, где написано «забег», читай «раунд».
* В видимых строках игры и каталога запрещено длинное тире (`scripts/check_em_dash.py`): двоеточие, запятая или «–». Тексты фаз ниже уже исправлены; если встретишь тире в UI-строке — заменяй.
* Любое новое окно поверх игры (`#dm-auth` из Фазы 12, «Закончить?» из Фазы 11) обязано слать `weco:modal {open: true|false}` и попадать под `modalIsOpen()` в `game.html`, иначе пробел и цифры снова пробьют окно.
* `_feedback.html` подключён в девяти шаблонах: семь базовых плюс `registration/login.html` и `registration/register.html`. `track.js` (Фаза 9) подключай во все девять — воронка входа тоже нужна.
* `problems/ratelimit.py` — лестница штрафов на 24 ч, а не счётчик окна. Для «600 событий за 10 минут» в Фазе 9 — свой счётчик в кэше (`cache.incr` по ключу `track:<visitor>:<10-минутное окно>`).
* Docker Desktop выключен: PostgreSQL на 55432 и контейнер `search` недоступны. Что требует их — журнал и дальше; проверка миграций на PostgreSQL — в Фазе 14, если Docker так и не поднят, честно записать.
* Зубастость через временную порчу файла: текст дефекта готовить до записи, исходник возвращать в `finally`; якорь для порчи должен встречаться в файле ровно один раз (второй запуск на этом остановился).

ФАЗЫ −1…5 — сделаны в первом запуске
Не повторять. Их результат и таблица утренней приёмки — `claude/HANDOFF_NIGHT_20260915.md`; подробности — журнал.
ФАЗА 6. Умный поиск: прогрев, разбивка времени, честная плашка, документ для боя
Что известно. Три ноги: dense (BGE-M3 через контейнер `search`), bm25 (индекс в памяти воркера), реранжирование GLM-5.3-Flash. `_build_corpus()` строит bm25-индекс по всему видимому каталогу лениво, при первом запросе, в каждом gunicorn-воркере отдельно; gunicorn перезапускает воркеры каждые ~1 000 запросов (`--max-requests 1000`). После переноса корпуса каталог вырос с 5 090 до 14 070 задач — холодный воркер платит за сборку на каждом «первом» поиске. Проверено владельцем 15.09 с боя: `X-Smart-Search: rerank` — реранж GLM на проде включён и работает на bm25-пуле; плотной ноги нет. Значит «20+ с» — это сборка индекса в холодном воркере плюс хвост задержки модели, а не выключенный флаг. То же у `semantic.get_index()` (все векторы из базы в память). Отсюда «20+ с вместо 7». На бою по docs/SERVER.md контейнер `search` не развёрнут и `SEMANTIC_SEARCH_ENABLED=0` — плашка «Ищем по словам» честная.
6а. Замер. До правок измерь локально в `manage.py shell`: `time` сборки `rerank.get_corpus()` и `semantic.get_index()` (по два прогона: холодный/тёплый), число задач в корпусе, RSS процесса до и после (`psutil` есть? если нет — `resource`/диспетчер по коду не трогать, просто запиши, что не измерил). Числа — в журнал и в `docs/EMBEDDINGS.md`.
6б. Прогрев воркера — уже написан (`catalog/warmup.py::warm_worker`, `config/gunicorn_conf.py::post_worker_init`, `-c` в entrypoint, 8 зелёных тестов). Осталась настройка `SMART_SEARCH_WARMUP` в `config/settings.py` (из env, по умолчанию `1`) и строка в `deploy/env.example`.
6б′. Прогрев в фоновом потоке — переделать. Арбитр gunicorn убивает воркер, молчащий дольше `--timeout 60`, в том числе внутри `post_worker_init`; на боевом объёме сборка может быть дольше. Поэтому `post_worker_init` не зовёт `warm_worker` напрямую, а запускает `threading.Thread(target=warm_worker, daemon=True, name="smart-search-warmup")` и сразу возвращается: воркер обслуживает запросы, а корпус строится параллельно (`get_corpus()` под своим замком — ранний поиск просто дождётся сборки, как и сейчас, но она уже начата). В конце `warm_worker` закрыть соединение с базой потока (`django.db.connection.close()`), параметр `notify` больше не нужен — убрать. Тесты `test_warmup` поправить: сама функция синхронна и тестируется как раньше; отдельный тест — что `post_worker_init` стартует поток и возвращается быстрее чем за 1 с при подменённом долгом `warm_worker`.
6в. Разбивка времени в логе — поля уже есть (`corpus_build_seconds`, `pool_seconds`). Осталось: в `catalog/views.py::_catalog_context` замерить время поиска (`_search_ids` + `rerank.apply`), положить в контекст целым числом мс (0 без запроса) и в `problem_list` и `api_filter_state` поставить заголовок ответа `X-Smart-Search-Ms` (целое, общее время поиска в мс) рядом с `X-Smart-Search` — чтобы владелец мерил одним `curl -sI`. Тесты уже написаны и красные (`HeaderTests` ×3) — они должны позеленеть.
6г. Живая проверка с ключом. Если в локальном `.env` есть `GLM_API_KEY` и `SMART_SEARCH_RERANK=1`: `manage.py rerank_trace "налог на монополиста"` и ещё два запроса (короткий по теме, описание своими словами) — пул по ногам, пачки, `model_seconds`, статус — в журнал (ключ есть, флаг стоит — проверено первым запуском; это платно, разрешено). Контейнер `search` локально не поднять (Docker Desktop выключен): плотная нога уйдёт в деградацию, так и запиши.
6д. Плашка. `{% if degraded %}`: когда `smart_search_status == 'rerank'` (GLM отработал на bm25-пуле), текст: «Ищем по словам с умной сортировкой. Поиск по смыслу пока выключен, результаты могут быть беднее обычного.» (без длинного тире: в каталоге оно запрещено). Иначе текст прежний. Передай статус в шаблон и поправь комментарий «Не для шаблона» у ключа `smart_search_status`. Тест `DegradedNoteTests.test_rerank_on_words_pool_says_so` уже написан и красный.
6е. Документ для владельца. В `docs/SERVER.md` раздел «Включение смысловой ноги на бою» — точные команды (проверь пути и имена по compose):

```bash
free -m                                   # нужно ≥ 3 ГБ свободных вместе с buff/cache
cd /srv/weconomics/app/deploy
docker compose build search && docker compose up -d search
docker compose logs -f search             # ждать загрузки модели (минуты)
docker compose exec web curl -fsS http://search:8001/healthz
# в /srv/weconomics/.env: SEMANTIC_SEARCH_ENABLED=1  SMART_SEARCH_RERANK=1  SEARCH_SERVICE_URL=http://search:8001
docker compose up -d web ws
curl -sI "https://weconomics.ai/catalog/?q=налог" | grep -i x-smart-search

```

6е′. Векторы на бой. Найдено в первом запуске: `dump_for_deploy` вырезает `embedding` (`BANK_ONLY_PROBLEM_STRIP`), на бою векторов нет, а `build_embeddings` в контейнере `web` не запустится — там нет `sentence_transformers`/torch (ADR 0002). Путь один: перевезти векторы файлом из локальной базы, где посчитаны все 41 307 по активной формуле. Сделай команду `problems/management/commands/embeddings_export_vectors.py`: `--out FILE` (`.npz`: `ids` int64, `vectors` float32 [N×1024], `formula`, `model`, `count`), по умолчанию только видимый каталог (`filters.base_queryset('catalog')`), `--all` — весь банк; формат должен ровно совпадать с тем, что читает существующий `embeddings_import_vectors` (прочитай его первым; если он ждёт другой формат — пиши в его формат). Тест кругового обмена: 3 задачи с векторами → export → import в чистую тестовую базу → векторы побайтно равны, хеши формулы совпадают. Прогони экспорт видимого каталога локально, размер файла и число векторов — в журнал. Раздел `docs/SERVER.md` дополни шагами: экспорт локально → `scp` на сервер в `/srv/weconomics/` → `docker compose exec web python manage.py embeddings_import_vectors …` → `embeddings_check_build` → только потом включение контейнера `search`. Обнови `docs/EMBEDDINGS.md` (прогрев в потоке, поля лога, заголовок, экспорт векторов).
Чекпоинт-коммит.
ФАЗА 6½. Пауза засчитывается: серверная фиксация с потолком
Решение владельца: раунд с открытым окном (обратная связь, «Плохая задача?», выход) не должен сниматься с таблицы лидеров. Сейчас потолок `game/views.py::_rank_run` (`duration × 2 + 60 с`) меряет стенные часы → `time_overrun`. Владелец предупреждён, что учёт паузы открывает щель в анти-чите; поэтому пауза не «со слов клиента», а фиксируется сервером:

1. Два вызова: `POST /game/api/pause/` и `POST /game/api/resume/` (в `game/views.py`, CSRF, только для активного раунда). Сервер пишет в состояние раунда `pauses = [[start_ms, end_ms], …]` по своим часам. Открытая пауза без `resume` закрывается автоматически следующим запросом к раунду (ответ, вопрос, финиш) — моментом этого запроса.
2. Во время открытой паузы `api_answer` и `api_question` отвечают 409 `{'error': 'paused', 'reason': 'paused'}` — отвечать на паузе нельзя.
3. Потолок: суммарная пауза за раунд ≤ 120 с и ≤ 5 пауз; сверх — сервер паузу принимает (клиент честно стоит), но в зачёт не берёт.
4. `_rank_run`: из стенного времени вычитается зачтённая пауза; порог `time_overrun` считается после вычета.
5. Клиент: `rushPause()`/`rushResume()` из Фазы 1 дополнительно шлют эти два запроса (без `catch` не оставлять — Фаза 2). Ответ 409 `paused` на клике по варианту — снять блокировку, ничего не показывать (окно и так открыто).
6. `docs/GAME.md`: раздел «Пауза» — что фиксирует сервер, потолок, почему.

Тесты: пауза пишется по серверным часам (подмена времени); ответ на паузе → 409; `_rank_run` с паузой 30 с при стенном превышении на 20 с — раунд в таблице; суммарно больше 120 с — в зачёт только 120; открытая пауза закрывается следующим запросом. Зубастость каждого.
Чекпоинт-коммит.
ФАЗА 7. Поиск: анимация ожидания с фразами
Поиск — обычная отправка формы; пока грузится новая страница, старая показывает `.ask-busy`. Сейчас там «Ищу похожие задачи…».

1. `catalog/placeholder_phrases.py` — константа `SEARCH_BUSY_PHRASES`, первой идёт `думается думается…`, затем (порядок случайный при каждом запросе, первая всегда первая): `ищу равновесие…`, `сдвигаю кривую спроса…`, `сравниваю предельные выгоды и издержки…`, `считаю площадь под кривой…`, `проверяю условие первого порядка…`, `перебираю КПВ…`, `дисконтирую варианты…`, `ищу точку Курно…`, `заглядываю в ящик Эджворта…`, `спрашиваю у Лаффера…`, `ceteris paribus…`, `максимизирую полезность выдачи…`, `раскладываю по Парето…`, `ещё чуть-чуть, модель думает…`.
2. Шаблон: `<span class="ask-busy"><i></i><span id="ask-busy-text">думается думается…</span></span>`, фразы — через `json_script`. Скрипт в `_catalog_js.html`: при `is-busy` менять фразу каждые 1 600 мс с плавной сменой (opacity 160 мс); `<i>` — маленький крутящийся ring 12 px или три точки (уже есть? проверь CSS `.ask-busy i`; если анимации нет — добавь, скромно). При `prefers-reduced-motion` — статичная первая фраза, без ring-анимации.
3. Появление выдачи: если `searched`, карточкам результатов класс `ct-appear` с лёгким stagger (первые 12 карточек, шаг 40 мс, длительность 220 мс, только opacity/translateY 4 px). При reduced-motion — выключено.
4. Ничего крупного и кричащего: размеры и цвета — из токенов, без новых цветов.

Тесты: шаблон содержит `думается думается…` и не содержит «Ищу похожие задачи»; фразы отдаются через `json_script`; `test_design_canon` зелёный.
Чекпоинт-коммит.
ФАЗА 8. Виджет тестов: подпункты из текста условия (запись в локальную базу)
Факты. По `TEST_WIDGET_RECON.md`: мёртвых виджетов 4 527, из них у 4 510 нет `ProblemPart` вовсе: 3 956 — варианты записаны текстом в условии (2 460 с шапкой «Варианты ответа:», 1 496 без шапки), 554 — `верно_неверно` без подпунктов, `answer` ∈ {Верно, Неверно}. Живой виджет = `ProblemPart` с меткой (`normalize_label`) и текстом варианта; верные метки читаются из `problem.answer` через `catalog_test_correct_labels`. Решение владельца: создать настоящие подпункты и вырезать блок вариантов из условия в базе, обратимо, со снимком — чтобы данные были как у 1 434 живых.
8а. Разбор — чистая функция `problems/test_options_parse.py`: `parse_options(statement) -> ParsedOptions | None` с полями `stem`, `options: [(label, text)]`, `header: bool`, `style` (`numbered_lettered` — «1. (a) …», `lettered` — «а) …», `numbered` — «1) …»). Правила:

* блок вариантов — только хвост условия: с шапки (`Варианты ответа:`, `Варианты ответов:`, `Варианты:`, регистр и двоеточие/точка гибко) или с первой строки-варианта до конца текста; после блока ничего нет;
* строка-варианта: `^\s*(\d{1,2})[.)]\s*\(?([a-zа-яё])\)?[.)]?\s+(.+)$` (номер + буква), либо `^\s*([а-яёa-z])[.)]\s+(.+)$`, либо `^\s*(\d{1,2})[.)]\s+(.+)$`; один стиль на весь блок, ≥ 2 строк, номера/буквы по порядку без пропусков;
* текст варианта: срезать завершающие `;`/`.`, схлопнуть пробелы; пустой → None;
* метки уникальны после `normalize_label`;
* ложные срабатывания запрещены: нумерованные подвопросы («1. Найдите равновесие. 2. Постройте график») — это задачи, не тесты; поэтому функция зовётся только для `problem_type` тестовых видов `single`/`multi` (`problem_types.test_kind`) и только при нулевом числе подпунктов, а строки с глаголом-заданием в начале («найдите», «постройте», «определите», «рассчитайте», «докажите», «объясните») в стиле `numbered` → None;
* `stem` = условие без блока и шапки, обрезка хвостовых пробелов/переносов, не пустой. Для `верно_неверно` (`boolean`): подпункты по образцу живых. Сначала посмотри, как хранятся подпункты у живой `верно_неверно` задачи (`ProblemPart` по `problem_type` и `parts__isnull=False`): какие `label`, `statement`, `answer`. Повтори ровно этот формат. Условие таких задач не меняется.

8б. Команда `problems/management/commands/test_options_from_statement.py`: `--dry-run` (по умолчанию), `--apply`, `--revert <snapshot.json>`, `--ids-file` (по умолчанию `reports/corpus_transfer_20260913/dead_test_widget_ids.txt`, но объём проверяется заново по базе: тестовый вид и 0 подпунктов), `--limit N`, `--report DIR` (по умолчанию `reports/night_20260915/test_options/`). Для каждой задачи: разбор → верные метки `catalog_test_correct_labels(problem)` (должны быть непустыми и ⊆ разобранных; `single` → ровно одна; иначе причина `answer_mismatch`) → план: создать подпункты (`label`, `statement`=текст, `answer` — по формату живых: посмотри, что там лежит у живых вариантов, и скопируй соглашение; `order` по порядку; `points` как у живых) и записать `statement = stem`. Поле `answer` `Problem` не трогается. `content_status`, `human_review`, `status` не трогаются.

* `--dry-run`: ничего не пишет; отчёт `REPORT.md`: счётчики по причинам (`parsed`, `no_block`, `mixed_style`, `answer_mismatch`, `single_multi_correct`, `verb_like_subquestion`, `boolean_synthetic`), гистограмма числа вариантов, 20 случайных примеров «было / стало» (полный текст условия до и после, список вариантов, верные метки) — этот отчёт владелец читает утром.
* `--apply`: транзакция; перед записью — снимок `snapshot_<timestamp>.json`: `{problem_id: {"statement_before": …, "part_ids": […]}}`; в конце инвариант: для каждой применённой задачи `testplay.game_of(problem)` не `None` — иначе откат транзакции и стоп.
* `--revert <snapshot>`: вернуть `statement` побайтно, удалить ровно созданные `part_ids` (если подпункт с тех пор изменён — не удалять, сообщить); после `--revert` повторный `--dry-run` находит те же кандидаты.
* Идемпотентность: второй `--apply` подряд ничего не меняет (кандидатов 0).

8в. Тесты (`problems/tests/test_test_options_parse.py`, `test_test_options_command.py`): ≥ 10 фикстур разбора — оба стиля, с шапкой и без, `;` и `.` на концах, кириллица/латиница в метках, пропуск номера → None, нумерованные подвопросы с глаголами → None, вариант из одной строки → None; команда: dry-run не пишет (счётчик `Problem`/`ProblemPart` не меняется), apply создаёт и переписывает, `game_of` жив, revert возвращает байт-в-байт и удаляет части, apply идемпотентен. Зубастость каждого.
8г. Применение локально. Рабочая база должна быть мигрирована (см. старт запуска). После зелёных тестов: `--dry-run` на полном объёме → прочитай отчёт сам, проверь 20 примеров на здравый смысл → `--apply`. Числа (применено / пропущено по причинам / стало живых виджетов по `game_of` на видимом каталоге до и после) — в журнал и в отчёт. Замечание для владельца: у переписанных условий устареет хеш эмбеддинга (`build_embeddings --stale` их подхватит) — в журнал, не запускать.
8д. Для боя (в итоговый отчёт): команда та же, изнутри контейнера: `docker compose exec web python manage.py test_options_from_statement --dry-run --report /app/reports/test_options_prod` → владелец читает отчёт → `--apply`. Прод не трогать.
Чекпоинт-коммит.
ФАЗА 9. Аналитика беты: своя таблица событий
Решение владельца: без внешних сервисов. Собираем сырые события — клики, экраны, время на экране, пути — в свою таблицу; анализ будет после беты. Про конфиденциальность в этой бете не думаем (согласие участников есть), но ничего из профиля сверх `user` и cookie посетителя не пишем.
Модель `problems/models_platform.py`:

```python
class Event(models.Model):
    ts = DateTimeField(auto_now_add=True, db_index=True)
    user = FK(AUTH_USER_MODEL, SET_NULL, null=True, blank=True)
    visitor = CharField(max_length=40, db_index=True)   # cookie weco_vid (uuid4), ставит скрипт
    session_key = CharField(max_length=40, blank=True)
    page_key = CharField(max_length=32, db_index=True)  # feedback_options.page_key_for(path)
    path = CharField(max_length=500)
    name = CharField(max_length=48, db_index=True)      # page_view, page_leave, click, search, …
    props = JSONField(default=dict, blank=True)
    duration_ms = PositiveIntegerField(null=True, blank=True)
    viewport = CharField(max_length=16, blank=True)
    user_agent = CharField(max_length=200, blank=True)
    class Meta: indexes = [Index(fields=['name', 'ts']), Index(fields=['visitor', 'ts'])]

```

Миграция `problems`.
API `POST /api/track/` (`problems/views_platform.py`): тело JSON `{"events": [{name, path, props, duration_ms, viewport, t}]}`, ≤ 50 событий за запрос, `props` ≤ 2 КБ после сериализации (лишнее — обрезать, не отвергать всё), гостю можно. `navigator.sendBeacon` не умеет ставить заголовки, поэтому вьюха `csrf_exempt`, а вместо CSRF — ручная проверка происхождения: заголовок `Origin` (или `Referer`, если `Origin` нет) обязан быть нашим хостом из `ALLOWED_HOSTS`, иначе 403; плюс свой счётчик в кэше по `visitor` (`cache.incr`, ключ на 10-минутное окно; `problems/ratelimit.py` для этого не подходит — это лестница штрафов): не больше 600 событий за 10 минут, сверх — 429 и события отбрасываются. Запиши это в `docs/SECURITY.md` («почему csrf_exempt и что вместо»). `page_key` считает сервер по `path`.
Скрипт `static/track.js` (≤ 200 строк, без зависимостей), подключается во всех девяти шаблонах, где есть `_feedback.html` (семь базовых плюс `registration/login.html` и `registration/register.html`). Что делает:

* cookie `weco_vid` (uuid4, год, `SameSite=Lax`), если нет;
* `page_view` при загрузке (`props.referrer`), `page_leave` при `pagehide` / `visibilitychange→hidden` с `duration_ms` активного времени (счёт стоит, пока вкладка скрыта); отправка `sendBeacon`;
* `click` — делегированный слушатель на `a, button, [role=button], input[type=submit]`: `props = {text: (aria-label || textContent).trim().slice(0, 60), id, cls: первые два класса, href}`; клики внутри окон обратной связи и «плохой задачи» — тоже (там кнопки);
* `window.weco = {track(name, props)}` для явных событий;
* очередь: сброс каждые 5 с, или при 20 событиях, или на `pagehide`; `fetch(..., {keepalive: true})` как запасной путь, если `sendBeacon` нет. Никакого учёта Do-Not-Track — решение владельца.

Явные события (через `weco.track`):

* игра: `game_start {mode, filtered}`, `game_answer {mode, correct, skip, elapsed_ms, number}`, `game_end {mode, reason, score, answered, correct}`, `duel_create`, `duel_start`, `practice_start`, `practice_end {answered, correct}`;
* поиск: сервер кладёт в контейнер выдачи `data-search-status="{{ smart_search_status }}" data-search-total="{{ total }}" data-search-degraded`, скрипт при `searched` шлёт `search {q_len, status, total, degraded}`; при отправке формы — `search_submit {q_len}`;
* каталог: `problem_open {problem_id}` (страница и модалка), `test_answer {problem_id, correct, attempt}`, `copy_link`;
* чат: `chat_send {mode, has_file}` (Фаза 10); обратная связь: `feedback_send {kind}`; плохая задача: `report_send {kind, source}`. Ищи уже существующие точки (`showQuestion`, `endRun`, `openCatalogModal`, отправка форм) и добавляй по одной строке — не переписывай функции.

Админка `EventAdmin`: список `ts, name, page_key, path, who, visitor(8)`, фильтры `name`, `page_key`, `user`, `date_hierarchy`, поиск по `path`, `visitor`. Команда `analytics_export --since YYYY-MM-DD [--until] --out FILE` → CSV (плоские колонки + `props` JSON-строкой).
Тесты: API (валидация, ≤ 50, обрезка props, чужой `Origin` → 403, лимит), `page_key` считается сервером, `Event` создаётся, скрипт подключён во всех девяти шаблонах (тест по списку файлов), команда экспорта пишет CSV.
Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — ПЕРВЫМ ДЕЛОМ. Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (из 10.0), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель уходит список `(mime, bytes)`, максимум 5. Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения, или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков: просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец раунда) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» (шлёт `weco:modal`, входит в `modalIsOpen()`) → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль только с аккаунтом: соперника нужно как-то называть» (шлёт `weco:modal`, входит в `modalIsOpen()`) с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но раунд ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге раунда дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время раунда; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза с серверной фиксацией и потолком, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев в потоке, поля лога, заголовок `X-Smart-Search-Ms`, экспорт векторов;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `embeddings_export_vectors`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам (для 1–5 таблица уже есть в хэндоффе, не переписывай, дополни): адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, перевоз векторов и включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.
````

### Сообщение 10 — 15.09.2026 14:59 МСК, запуск 206b05bd

Длина: 33 знаков.

````text
спасибо! я пошел дальше работать.
````

### Сообщение 11 — 15.09.2026 15:00 МСК, запуск 0cc7fb20

Длина: 28752 знаков.

Отличается от сообщения 6: убраны разделы ФАЗА 6, ФАЗА 6½, ФАЗА 7, ФАЗА 8, ФАЗА 9 (сделаны, вместо них строка «ФАЗЫ −1…9 и 10.0 — сделаны»); добавлен раздел «ФАЗА 8½. Косметика подпунктов и свежие векторы»; переписана преамбула (заголовок «ПРОДОЛЖЕНИЕ с Фазы 8½ и 10.1», HEAD `58ef4bf9`, новое правило «владелец в этот запуск на связи»: стратегические развилки спрашивать, мелочи решать самому; блок «Дополнение для продолжения (после третьего запуска)» вместо «после первого» — двойная нумерация у 15 задач, строка вариантов «Верно/Неверно» у 554 задач (прежняя инструкция «условие таких задач не меняется» названа ошибкой), пересчёт устаревших векторов, зрение чата CATALOG_CHAT_VISION_MODEL = glm-5.3-flash по двухшаговому паттерну ADR 0081, ошибка загрузки ресурса в консоли каталога; правила первого запуска сжаты в одну строку); изменены разделы ФАЗА 10 (пункт 10.0 помечен сделанным, в 10.1 прописана vision-модель, в 10.3 и 10.5 добавлены поля vision_text и токены расшифровки) и ФАЗА 14 (добавлен блок «Модель и усилие»); без изменений разделы ФАЗА 11, ФАЗА 12, ФАЗА 13

````text
Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09», ПРОДОЛЖЕНИЕ с Фазы 8½ и 10.1
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Затем — обязательно — `claude/HANDOFF_NIGHT_20260915.md` и `reports/night_20260915/JOURNAL.md`: это состояние после первого запуска. Раздел «Дополнение для продолжения (после третьего запуска)» ниже важнее любых расхождений между ними и текстом фаз.
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09; продолжение — по хэндоффу первого запуска (ветка `feat/night-20260915`, HEAD `58ef4bf9` или новее). Все решения владельца, на которых стоит сессия, приняты в чате 15.09, записаны в Notion «Решения» (семь карточек от 15.09) и повторены в «Дополнении» ниже — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Рабочая локальная база `db.sqlite3`: владелец разрешил накатить на неё миграции и применить подпункты тестов (Фаза 8, обратимо по снимку). `runserver` у владельца не запущен; перед `migrate` всё равно проверь порт 8000 (`netstat -ano | findstr :8000`) — занят → не мигрируй, журнал, Фазу 8г пропусти.
Владелец в этот запуск на связи. Стратегическая развилка (что-то, что меняет поведение продукта или структуру данных и не описано в фазе) — задай вопрос коротко, с вариантами, и жди ответа. Мелочи и технические выборы — решай сам и записывай в журнал предположение. Расхождение якорей — стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг явными лейблами (`scripts\run_tests.py <app.tests.module> …`): `--scope-from-git` на общем шаблоне `templates/_*.html` раздувается до полного шага A (~112 мин), это найдено в первом запуске. Вывод в файл `> лог 2>&1`, код возврата читать сразу, числа брать из лога, а не из памяти (инструмент иногда теряет вывод); `| tail` запрещён — он съедает код. Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Образец уже есть в ветке: раннер `game/tests/browser_*.mjs` (Playwright в node, JSON после маркера `###RUSH-JSON###`) + питон-обёртка на `StaticLiveServerTestCase`; запуск `scripts/run_tests.py game.tests.test_browser_modals --only-serial`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` — следующая 0067, `game` — с 0016. В тестах по странице — `assertTrue(x in html, 'коротко')`, не `assertIn` (при падении печатает весь HTML). Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
Дополнение для продолжения (после третьего запуска)
Состояние. HEAD `58ef4bf9` (после фикса CSV-инъекции в `analytics_export`), дерево чистое (кроме личных неотслеживаемых файлов владельца). Закрыты фазы −1…9 и пункт 10.0. Хэндофф обновлён: раздел «Состояние после третьего запуска» в `claude/HANDOFF_NIGHT_20260915.md` — читать первым. Рабочая база мигрирована до `problems/0067`, подпункты тестов применены (4 076 задач, 16 282 подпункта, 3 251 условие укорочено, снимок для отката и копия базы сохранены — пути в журнале). Векторы экспортированы (14 082, 55 МБ) — до переписывания условий, поэтому файл устарел, см. Фазу 8½. Зрение: `glm-5.3` картинки не принимает, `glm-5.3-flash` читает.
Старт этого запуска: `git status`/`git diff --stat` (остатки → коммит или `stash`, как раньше), `manage.py check`, ветка и HEAD. Если Docker Desktop поднят (владелец обещал включить) — `docker compose -f docker-compose.dev.yml up -d` и проверь порт 55432: тогда в Фазе 14 миграции проверяются на PostgreSQL. Не поднят — журнал, без остановки.
Решения по хвостам третьего запуска (владелец согласился):

* Двойная нумерация у 15 задач («1) (1) …»): парсер режет повторный номер, когда он равен метке; переприменить только эти 15 через `--revert` по их id из снимка и `--apply --ids` с новым парсером, новый снимок, идемпотентность.
* Строка вариантов у «верно/неверно» («1) Верно 2) Неверно» и подобные в хвосте условия) у 554 задач — вырезать так же обратимо, как у остальных; прежняя инструкция «условие таких задач не меняется» была ошибкой: плитки дублируют строку. Парсер: хвостовая строка/строки только из вариантов «Верно/Неверно» (любой регистр, нумерация цифрой или буквой, одна или две строки) → `stem` без них; подпункты уже созданы, их не трогать.
* Устаревшие векторы у переписанных условий: пересчитать локально `build_embeddings --stale` (после ВСЕХ правок условий этого запуска), затем заново `embeddings_export_vectors` → новый файл; старый удалить; числа и время — в журнал и в команды для боя.
* Зрение чата: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, текст — `glm-5.3`. Двухшаговый паттерн ADR 0081: реплика с файлом сначала идёт во Flash с задачей «перепиши дословно всё, что написано на фото/страницах: текст, формулы (LaTeX), подписи к графикам; не оценивай и не решай», а расшифровка (с пометкой «[расшифровка фото]») вклеивается в текст реплики для GLM-5.3. Обе стороны шага логируются в `ChatTurn` (поле `vision_text`, токены Flash — отдельно).
* Ошибка загрузки ресурса в консоли каталога (connection refused): один шаг — найти адрес в DevTools-логе браузерного теста или `test_page_js`; если это наш код (сокет, сервис поиска, статика) — починить, если внешнее или локальная среда — записать и не трогать.

Правила проекта из первого запуска остаются в силе (раунд, а не забег; без длинных тире в UI; `weco:modal` для новых окон; девять шаблонов; свой счётчик вместо `ratelimit.py`; зубастость через порчу файла с уникальным якорем; тесты лейблами; числа из логов).
ФАЗЫ −1…9 и 10.0 — сделаны
Не повторять. Итоги и таблицы приёмки — в хэндоффе и журнале.
ФАЗА 8½. Косметика подпунктов и свежие векторы

1. Парсер `problems/test_options_parse.py`: (а) повторный номер «1) (1) …» / «1. 1) …» — если число в скобках равно метке, убрать его из текста варианта; (б) для `boolean` — хвостовые строки, целиком состоящие из вариантов «Верно»/«Неверно» (с нумерацией или без, в одну строку через пробелы/табы или в две), отрезаются от `stem`. Тесты: по 3 фикстуры на каждый случай, включая ложные («Верно ли, что…» в середине условия — не трогать). Зубастость.
2. Команда: флаг `--ids ID,ID,…` (или файл) поверх существующих; выборка для (а) — 15 задач по отчёту третьего запуска (их id — в `reports/night_20260915/test_options/REPORT.md` или пересчитай регэкспом по базе), для (б) — все `boolean` с подпунктами, у которых хвост условия совпадает с паттерном. Порядок: `--revert` только для (а) → `--apply` (а) и (б) с новыми снимками → повторный `--dry-run` даёт 0. Инвариант: число живых виджетов не уменьшилось (было 5 485).
3. `build_embeddings --stale` локально — время и число пересчитанных в журнал (ожидается ≈ 3 251 + правки этой фазы). Затем `embeddings_export_vectors` в новый файл, старый удалить, размер и число векторов — в журнал; строку с именем файла обновить в `docs/SERVER.md`.
4. `docs/DATA.md`: дополнить раздел о подпунктах (двойная нумерация, «верно/неверно», пересчёт векторов). Notion: комментарий к карточке Фазы 8.

Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — СДЕЛАНО в третьем запуске (`scripts/glm_vision_probe.py`): `glm-5.3` картинки не принимает, `glm-5.3-flash` читает. Решение принято: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, двухшаговый паттерн из «Дополнения». Исходный текст пункта оставлен для контекста: Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (`glm-5.3-flash`, см. «Дополнение»), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель зрения (Flash) уходит список `(mime, bytes)`, максимум 5; в GLM-5.3 — только текст расшифровки (двухшаговый паттерн). Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения, или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `vision_text` (расшифровка Flash, blank), `vision_input_tokens`, `vision_output_tokens`, `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков: просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец раунда) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» (шлёт `weco:modal`, входит в `modalIsOpen()`) → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль только с аккаунтом: соперника нужно как-то называть» (шлёт `weco:modal`, входит в `modalIsOpen()`) с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но раунд ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге раунда дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время раунда; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза с серверной фиксацией и потолком, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев в потоке, поля лога, заголовок `X-Smart-Search-Ms`, экспорт векторов;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `embeddings_export_vectors`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам (для 1–5 таблица уже есть в хэндоффе, не переписывай, дополни): адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, перевоз векторов и включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.

Модель и усилие
Opus, effort High; на фазах 8, 10, 12 — Max; на механических шагах (чекпоинты, прогоны, документация) — Medium.
````

### Сообщение 17 — 15.09.2026 17:50 МСК, запуск 0cc7fb20

Длина: 28881 знаков.

Отличается от сообщения 11: тело промпта (все разделы от «Промпт для Claude Code…» до «Модель и усилие») совпадает дословно; сверху добавлена приписка владельца «ИНТЕРНЕТ ВЕРНУЛСЯ, ПРОДОЛЖАЙ ПО ПРОМПТУ НИЖЕ ЧЕТКО И ПРОВЕРЬ КАК ТАМ BACKGROUND TASKS, А ТО ТАМ УЖЕ 2 ЧАСА ЧТО-ТО ИДЕТ. РАБОТАЙ» и пустая строка после неё

````text
ИНТЕРНЕТ ВЕРНУЛСЯ, ПРОДОЛЖАЙ ПО ПРОМПТУ НИЖЕ ЧЕТКО И ПРОВЕРЬ КАК ТАМ BACKGROUND TASKS, А ТО ТАМ УЖЕ 2 ЧАСА ЧТО-ТО ИДЕТ. РАБОТАЙ

Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09», ПРОДОЛЖЕНИЕ с Фазы 8½ и 10.1
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Затем — обязательно — `claude/HANDOFF_NIGHT_20260915.md` и `reports/night_20260915/JOURNAL.md`: это состояние после первого запуска. Раздел «Дополнение для продолжения (после третьего запуска)» ниже важнее любых расхождений между ними и текстом фаз.
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09; продолжение — по хэндоффу первого запуска (ветка `feat/night-20260915`, HEAD `58ef4bf9` или новее). Все решения владельца, на которых стоит сессия, приняты в чате 15.09, записаны в Notion «Решения» (семь карточек от 15.09) и повторены в «Дополнении» ниже — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Рабочая локальная база `db.sqlite3`: владелец разрешил накатить на неё миграции и применить подпункты тестов (Фаза 8, обратимо по снимку). `runserver` у владельца не запущен; перед `migrate` всё равно проверь порт 8000 (`netstat -ano | findstr :8000`) — занят → не мигрируй, журнал, Фазу 8г пропусти.
Владелец в этот запуск на связи. Стратегическая развилка (что-то, что меняет поведение продукта или структуру данных и не описано в фазе) — задай вопрос коротко, с вариантами, и жди ответа. Мелочи и технические выборы — решай сам и записывай в журнал предположение. Расхождение якорей — стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг явными лейблами (`scripts\run_tests.py <app.tests.module> …`): `--scope-from-git` на общем шаблоне `templates/_*.html` раздувается до полного шага A (~112 мин), это найдено в первом запуске. Вывод в файл `> лог 2>&1`, код возврата читать сразу, числа брать из лога, а не из памяти (инструмент иногда теряет вывод); `| tail` запрещён — он съедает код. Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Образец уже есть в ветке: раннер `game/tests/browser_*.mjs` (Playwright в node, JSON после маркера `###RUSH-JSON###`) + питон-обёртка на `StaticLiveServerTestCase`; запуск `scripts/run_tests.py game.tests.test_browser_modals --only-serial`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` — следующая 0067, `game` — с 0016. В тестах по странице — `assertTrue(x in html, 'коротко')`, не `assertIn` (при падении печатает весь HTML). Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
Дополнение для продолжения (после третьего запуска)
Состояние. HEAD `58ef4bf9` (после фикса CSV-инъекции в `analytics_export`), дерево чистое (кроме личных неотслеживаемых файлов владельца). Закрыты фазы −1…9 и пункт 10.0. Хэндофф обновлён: раздел «Состояние после третьего запуска» в `claude/HANDOFF_NIGHT_20260915.md` — читать первым. Рабочая база мигрирована до `problems/0067`, подпункты тестов применены (4 076 задач, 16 282 подпункта, 3 251 условие укорочено, снимок для отката и копия базы сохранены — пути в журнале). Векторы экспортированы (14 082, 55 МБ) — до переписывания условий, поэтому файл устарел, см. Фазу 8½. Зрение: `glm-5.3` картинки не принимает, `glm-5.3-flash` читает.
Старт этого запуска: `git status`/`git diff --stat` (остатки → коммит или `stash`, как раньше), `manage.py check`, ветка и HEAD. Если Docker Desktop поднят (владелец обещал включить) — `docker compose -f docker-compose.dev.yml up -d` и проверь порт 55432: тогда в Фазе 14 миграции проверяются на PostgreSQL. Не поднят — журнал, без остановки.
Решения по хвостам третьего запуска (владелец согласился):

* Двойная нумерация у 15 задач («1) (1) …»): парсер режет повторный номер, когда он равен метке; переприменить только эти 15 через `--revert` по их id из снимка и `--apply --ids` с новым парсером, новый снимок, идемпотентность.
* Строка вариантов у «верно/неверно» («1) Верно 2) Неверно» и подобные в хвосте условия) у 554 задач — вырезать так же обратимо, как у остальных; прежняя инструкция «условие таких задач не меняется» была ошибкой: плитки дублируют строку. Парсер: хвостовая строка/строки только из вариантов «Верно/Неверно» (любой регистр, нумерация цифрой или буквой, одна или две строки) → `stem` без них; подпункты уже созданы, их не трогать.
* Устаревшие векторы у переписанных условий: пересчитать локально `build_embeddings --stale` (после ВСЕХ правок условий этого запуска), затем заново `embeddings_export_vectors` → новый файл; старый удалить; числа и время — в журнал и в команды для боя.
* Зрение чата: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, текст — `glm-5.3`. Двухшаговый паттерн ADR 0081: реплика с файлом сначала идёт во Flash с задачей «перепиши дословно всё, что написано на фото/страницах: текст, формулы (LaTeX), подписи к графикам; не оценивай и не решай», а расшифровка (с пометкой «[расшифровка фото]») вклеивается в текст реплики для GLM-5.3. Обе стороны шага логируются в `ChatTurn` (поле `vision_text`, токены Flash — отдельно).
* Ошибка загрузки ресурса в консоли каталога (connection refused): один шаг — найти адрес в DevTools-логе браузерного теста или `test_page_js`; если это наш код (сокет, сервис поиска, статика) — починить, если внешнее или локальная среда — записать и не трогать.

Правила проекта из первого запуска остаются в силе (раунд, а не забег; без длинных тире в UI; `weco:modal` для новых окон; девять шаблонов; свой счётчик вместо `ratelimit.py`; зубастость через порчу файла с уникальным якорем; тесты лейблами; числа из логов).
ФАЗЫ −1…9 и 10.0 — сделаны
Не повторять. Итоги и таблицы приёмки — в хэндоффе и журнале.
ФАЗА 8½. Косметика подпунктов и свежие векторы

1. Парсер `problems/test_options_parse.py`: (а) повторный номер «1) (1) …» / «1. 1) …» — если число в скобках равно метке, убрать его из текста варианта; (б) для `boolean` — хвостовые строки, целиком состоящие из вариантов «Верно»/«Неверно» (с нумерацией или без, в одну строку через пробелы/табы или в две), отрезаются от `stem`. Тесты: по 3 фикстуры на каждый случай, включая ложные («Верно ли, что…» в середине условия — не трогать). Зубастость.
2. Команда: флаг `--ids ID,ID,…` (или файл) поверх существующих; выборка для (а) — 15 задач по отчёту третьего запуска (их id — в `reports/night_20260915/test_options/REPORT.md` или пересчитай регэкспом по базе), для (б) — все `boolean` с подпунктами, у которых хвост условия совпадает с паттерном. Порядок: `--revert` только для (а) → `--apply` (а) и (б) с новыми снимками → повторный `--dry-run` даёт 0. Инвариант: число живых виджетов не уменьшилось (было 5 485).
3. `build_embeddings --stale` локально — время и число пересчитанных в журнал (ожидается ≈ 3 251 + правки этой фазы). Затем `embeddings_export_vectors` в новый файл, старый удалить, размер и число векторов — в журнал; строку с именем файла обновить в `docs/SERVER.md`.
4. `docs/DATA.md`: дополнить раздел о подпунктах (двойная нумерация, «верно/неверно», пересчёт векторов). Notion: комментарий к карточке Фазы 8.

Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — СДЕЛАНО в третьем запуске (`scripts/glm_vision_probe.py`): `glm-5.3` картинки не принимает, `glm-5.3-flash` читает. Решение принято: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, двухшаговый паттерн из «Дополнения». Исходный текст пункта оставлен для контекста: Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (`glm-5.3-flash`, см. «Дополнение»), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель зрения (Flash) уходит список `(mime, bytes)`, максимум 5; в GLM-5.3 — только текст расшифровки (двухшаговый паттерн). Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения, или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `vision_text` (расшифровка Flash, blank), `vision_input_tokens`, `vision_output_tokens`, `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков: просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец раунда) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» (шлёт `weco:modal`, входит в `modalIsOpen()`) → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль только с аккаунтом: соперника нужно как-то называть» (шлёт `weco:modal`, входит в `modalIsOpen()`) с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но раунд ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге раунда дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время раунда; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза с серверной фиксацией и потолком, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев в потоке, поля лога, заголовок `X-Smart-Search-Ms`, экспорт векторов;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `embeddings_export_vectors`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам (для 1–5 таблица уже есть в хэндоффе, не переписывай, дополни): адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, перевоз векторов и включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.

Модель и усилие
Opus, effort High; на фазах 8, 10, 12 — Max; на механических шагах (чекпоинты, прогоны, документация) — Medium.
````

### Сообщение 18 — 15.09.2026 18:18 МСК, запуск 0cc7fb20

Длина: 28880 знаков.

Отличается от сообщения 17: тело промпта совпадает дословно, приписка та же; убрана пустая строка между припиской и заголовком промпта — отличие ровно в один знак

````text
ИНТЕРНЕТ ВЕРНУЛСЯ, ПРОДОЛЖАЙ ПО ПРОМПТУ НИЖЕ ЧЕТКО И ПРОВЕРЬ КАК ТАМ BACKGROUND TASKS, А ТО ТАМ УЖЕ 2 ЧАСА ЧТО-ТО ИДЕТ. РАБОТАЙ
Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09», ПРОДОЛЖЕНИЕ с Фазы 8½ и 10.1
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Затем — обязательно — `claude/HANDOFF_NIGHT_20260915.md` и `reports/night_20260915/JOURNAL.md`: это состояние после первого запуска. Раздел «Дополнение для продолжения (после третьего запуска)» ниже важнее любых расхождений между ними и текстом фаз.
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09; продолжение — по хэндоффу первого запуска (ветка `feat/night-20260915`, HEAD `58ef4bf9` или новее). Все решения владельца, на которых стоит сессия, приняты в чате 15.09, записаны в Notion «Решения» (семь карточек от 15.09) и повторены в «Дополнении» ниже — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Рабочая локальная база `db.sqlite3`: владелец разрешил накатить на неё миграции и применить подпункты тестов (Фаза 8, обратимо по снимку). `runserver` у владельца не запущен; перед `migrate` всё равно проверь порт 8000 (`netstat -ano | findstr :8000`) — занят → не мигрируй, журнал, Фазу 8г пропусти.
Владелец в этот запуск на связи. Стратегическая развилка (что-то, что меняет поведение продукта или структуру данных и не описано в фазе) — задай вопрос коротко, с вариантами, и жди ответа. Мелочи и технические выборы — решай сам и записывай в журнал предположение. Расхождение якорей — стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг явными лейблами (`scripts\run_tests.py <app.tests.module> …`): `--scope-from-git` на общем шаблоне `templates/_*.html` раздувается до полного шага A (~112 мин), это найдено в первом запуске. Вывод в файл `> лог 2>&1`, код возврата читать сразу, числа брать из лога, а не из памяти (инструмент иногда теряет вывод); `| tail` запрещён — он съедает код. Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Образец уже есть в ветке: раннер `game/tests/browser_*.mjs` (Playwright в node, JSON после маркера `###RUSH-JSON###`) + питон-обёртка на `StaticLiveServerTestCase`; запуск `scripts/run_tests.py game.tests.test_browser_modals --only-serial`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` — следующая 0067, `game` — с 0016. В тестах по странице — `assertTrue(x in html, 'коротко')`, не `assertIn` (при падении печатает весь HTML). Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
Дополнение для продолжения (после третьего запуска)
Состояние. HEAD `58ef4bf9` (после фикса CSV-инъекции в `analytics_export`), дерево чистое (кроме личных неотслеживаемых файлов владельца). Закрыты фазы −1…9 и пункт 10.0. Хэндофф обновлён: раздел «Состояние после третьего запуска» в `claude/HANDOFF_NIGHT_20260915.md` — читать первым. Рабочая база мигрирована до `problems/0067`, подпункты тестов применены (4 076 задач, 16 282 подпункта, 3 251 условие укорочено, снимок для отката и копия базы сохранены — пути в журнале). Векторы экспортированы (14 082, 55 МБ) — до переписывания условий, поэтому файл устарел, см. Фазу 8½. Зрение: `glm-5.3` картинки не принимает, `glm-5.3-flash` читает.
Старт этого запуска: `git status`/`git diff --stat` (остатки → коммит или `stash`, как раньше), `manage.py check`, ветка и HEAD. Если Docker Desktop поднят (владелец обещал включить) — `docker compose -f docker-compose.dev.yml up -d` и проверь порт 55432: тогда в Фазе 14 миграции проверяются на PostgreSQL. Не поднят — журнал, без остановки.
Решения по хвостам третьего запуска (владелец согласился):

* Двойная нумерация у 15 задач («1) (1) …»): парсер режет повторный номер, когда он равен метке; переприменить только эти 15 через `--revert` по их id из снимка и `--apply --ids` с новым парсером, новый снимок, идемпотентность.
* Строка вариантов у «верно/неверно» («1) Верно 2) Неверно» и подобные в хвосте условия) у 554 задач — вырезать так же обратимо, как у остальных; прежняя инструкция «условие таких задач не меняется» была ошибкой: плитки дублируют строку. Парсер: хвостовая строка/строки только из вариантов «Верно/Неверно» (любой регистр, нумерация цифрой или буквой, одна или две строки) → `stem` без них; подпункты уже созданы, их не трогать.
* Устаревшие векторы у переписанных условий: пересчитать локально `build_embeddings --stale` (после ВСЕХ правок условий этого запуска), затем заново `embeddings_export_vectors` → новый файл; старый удалить; числа и время — в журнал и в команды для боя.
* Зрение чата: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, текст — `glm-5.3`. Двухшаговый паттерн ADR 0081: реплика с файлом сначала идёт во Flash с задачей «перепиши дословно всё, что написано на фото/страницах: текст, формулы (LaTeX), подписи к графикам; не оценивай и не решай», а расшифровка (с пометкой «[расшифровка фото]») вклеивается в текст реплики для GLM-5.3. Обе стороны шага логируются в `ChatTurn` (поле `vision_text`, токены Flash — отдельно).
* Ошибка загрузки ресурса в консоли каталога (connection refused): один шаг — найти адрес в DevTools-логе браузерного теста или `test_page_js`; если это наш код (сокет, сервис поиска, статика) — починить, если внешнее или локальная среда — записать и не трогать.

Правила проекта из первого запуска остаются в силе (раунд, а не забег; без длинных тире в UI; `weco:modal` для новых окон; девять шаблонов; свой счётчик вместо `ratelimit.py`; зубастость через порчу файла с уникальным якорем; тесты лейблами; числа из логов).
ФАЗЫ −1…9 и 10.0 — сделаны
Не повторять. Итоги и таблицы приёмки — в хэндоффе и журнале.
ФАЗА 8½. Косметика подпунктов и свежие векторы

1. Парсер `problems/test_options_parse.py`: (а) повторный номер «1) (1) …» / «1. 1) …» — если число в скобках равно метке, убрать его из текста варианта; (б) для `boolean` — хвостовые строки, целиком состоящие из вариантов «Верно»/«Неверно» (с нумерацией или без, в одну строку через пробелы/табы или в две), отрезаются от `stem`. Тесты: по 3 фикстуры на каждый случай, включая ложные («Верно ли, что…» в середине условия — не трогать). Зубастость.
2. Команда: флаг `--ids ID,ID,…` (или файл) поверх существующих; выборка для (а) — 15 задач по отчёту третьего запуска (их id — в `reports/night_20260915/test_options/REPORT.md` или пересчитай регэкспом по базе), для (б) — все `boolean` с подпунктами, у которых хвост условия совпадает с паттерном. Порядок: `--revert` только для (а) → `--apply` (а) и (б) с новыми снимками → повторный `--dry-run` даёт 0. Инвариант: число живых виджетов не уменьшилось (было 5 485).
3. `build_embeddings --stale` локально — время и число пересчитанных в журнал (ожидается ≈ 3 251 + правки этой фазы). Затем `embeddings_export_vectors` в новый файл, старый удалить, размер и число векторов — в журнал; строку с именем файла обновить в `docs/SERVER.md`.
4. `docs/DATA.md`: дополнить раздел о подпунктах (двойная нумерация, «верно/неверно», пересчёт векторов). Notion: комментарий к карточке Фазы 8.

Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — СДЕЛАНО в третьем запуске (`scripts/glm_vision_probe.py`): `glm-5.3` картинки не принимает, `glm-5.3-flash` читает. Решение принято: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, двухшаговый паттерн из «Дополнения». Исходный текст пункта оставлен для контекста: Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (`glm-5.3-flash`, см. «Дополнение»), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель зрения (Flash) уходит список `(mime, bytes)`, максимум 5; в GLM-5.3 — только текст расшифровки (двухшаговый паттерн). Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения, или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `vision_text` (расшифровка Flash, blank), `vision_input_tokens`, `vision_output_tokens`, `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков: просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец раунда) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» (шлёт `weco:modal`, входит в `modalIsOpen()`) → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль только с аккаунтом: соперника нужно как-то называть» (шлёт `weco:modal`, входит в `modalIsOpen()`) с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но раунд ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге раунда дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время раунда; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза с серверной фиксацией и потолком, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев в потоке, поля лога, заголовок `X-Smart-Search-Ms`, экспорт векторов;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `embeddings_export_vectors`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам (для 1–5 таблица уже есть в хэндоффе, не переписывай, дополни): адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, перевоз векторов и включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.

Модель и усилие
Opus, effort High; на фазах 8, 10, 12 — Max; на механических шагах (чекпоинты, прогоны, документация) — Medium.
````

### Сообщение 20 — 15.09.2026 19:13 МСК, запуск 0cc7fb20

Длина: 28965 знаков.

Отличается от сообщения 18: тело промпта совпадает дословно; приписка владельца расширена концовкой «. ТАМ МОЖЕТ БЫТЬ ПРАВДА ЧТО-ТО СБРОСИЛОСЬ ПО ЭМБЕДДИНГАМ, ПРОВЕРЬ ГДЕ ОНО СОХРАНИЛОСЬ»

````text
ИНТЕРНЕТ ВЕРНУЛСЯ, ПРОДОЛЖАЙ ПО ПРОМПТУ НИЖЕ ЧЕТКО И ПРОВЕРЬ КАК ТАМ BACKGROUND TASKS, А ТО ТАМ УЖЕ 2 ЧАСА ЧТО-ТО ИДЕТ. РАБОТАЙ. ТАМ МОЖЕТ БЫТЬ ПРАВДА ЧТО-ТО СБРОСИЛОСЬ ПО ЭМБЕДДИНГАМ, ПРОВЕРЬ ГДЕ ОНО СОХРАНИЛОСЬ
Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09», ПРОДОЛЖЕНИЕ с Фазы 8½ и 10.1
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Затем — обязательно — `claude/HANDOFF_NIGHT_20260915.md` и `reports/night_20260915/JOURNAL.md`: это состояние после первого запуска. Раздел «Дополнение для продолжения (после третьего запуска)» ниже важнее любых расхождений между ними и текстом фаз.
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09; продолжение — по хэндоффу первого запуска (ветка `feat/night-20260915`, HEAD `58ef4bf9` или новее). Все решения владельца, на которых стоит сессия, приняты в чате 15.09, записаны в Notion «Решения» (семь карточек от 15.09) и повторены в «Дополнении» ниже — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Рабочая локальная база `db.sqlite3`: владелец разрешил накатить на неё миграции и применить подпункты тестов (Фаза 8, обратимо по снимку). `runserver` у владельца не запущен; перед `migrate` всё равно проверь порт 8000 (`netstat -ano | findstr :8000`) — занят → не мигрируй, журнал, Фазу 8г пропусти.
Владелец в этот запуск на связи. Стратегическая развилка (что-то, что меняет поведение продукта или структуру данных и не описано в фазе) — задай вопрос коротко, с вариантами, и жди ответа. Мелочи и технические выборы — решай сам и записывай в журнал предположение. Расхождение якорей — стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг явными лейблами (`scripts\run_tests.py <app.tests.module> …`): `--scope-from-git` на общем шаблоне `templates/_*.html` раздувается до полного шага A (~112 мин), это найдено в первом запуске. Вывод в файл `> лог 2>&1`, код возврата читать сразу, числа брать из лога, а не из памяти (инструмент иногда теряет вывод); `| tail` запрещён — он съедает код. Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Образец уже есть в ветке: раннер `game/tests/browser_*.mjs` (Playwright в node, JSON после маркера `###RUSH-JSON###`) + питон-обёртка на `StaticLiveServerTestCase`; запуск `scripts/run_tests.py game.tests.test_browser_modals --only-serial`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` — следующая 0067, `game` — с 0016. В тестах по странице — `assertTrue(x in html, 'коротко')`, не `assertIn` (при падении печатает весь HTML). Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
Дополнение для продолжения (после третьего запуска)
Состояние. HEAD `58ef4bf9` (после фикса CSV-инъекции в `analytics_export`), дерево чистое (кроме личных неотслеживаемых файлов владельца). Закрыты фазы −1…9 и пункт 10.0. Хэндофф обновлён: раздел «Состояние после третьего запуска» в `claude/HANDOFF_NIGHT_20260915.md` — читать первым. Рабочая база мигрирована до `problems/0067`, подпункты тестов применены (4 076 задач, 16 282 подпункта, 3 251 условие укорочено, снимок для отката и копия базы сохранены — пути в журнале). Векторы экспортированы (14 082, 55 МБ) — до переписывания условий, поэтому файл устарел, см. Фазу 8½. Зрение: `glm-5.3` картинки не принимает, `glm-5.3-flash` читает.
Старт этого запуска: `git status`/`git diff --stat` (остатки → коммит или `stash`, как раньше), `manage.py check`, ветка и HEAD. Если Docker Desktop поднят (владелец обещал включить) — `docker compose -f docker-compose.dev.yml up -d` и проверь порт 55432: тогда в Фазе 14 миграции проверяются на PostgreSQL. Не поднят — журнал, без остановки.
Решения по хвостам третьего запуска (владелец согласился):

* Двойная нумерация у 15 задач («1) (1) …»): парсер режет повторный номер, когда он равен метке; переприменить только эти 15 через `--revert` по их id из снимка и `--apply --ids` с новым парсером, новый снимок, идемпотентность.
* Строка вариантов у «верно/неверно» («1) Верно 2) Неверно» и подобные в хвосте условия) у 554 задач — вырезать так же обратимо, как у остальных; прежняя инструкция «условие таких задач не меняется» была ошибкой: плитки дублируют строку. Парсер: хвостовая строка/строки только из вариантов «Верно/Неверно» (любой регистр, нумерация цифрой или буквой, одна или две строки) → `stem` без них; подпункты уже созданы, их не трогать.
* Устаревшие векторы у переписанных условий: пересчитать локально `build_embeddings --stale` (после ВСЕХ правок условий этого запуска), затем заново `embeddings_export_vectors` → новый файл; старый удалить; числа и время — в журнал и в команды для боя.
* Зрение чата: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, текст — `glm-5.3`. Двухшаговый паттерн ADR 0081: реплика с файлом сначала идёт во Flash с задачей «перепиши дословно всё, что написано на фото/страницах: текст, формулы (LaTeX), подписи к графикам; не оценивай и не решай», а расшифровка (с пометкой «[расшифровка фото]») вклеивается в текст реплики для GLM-5.3. Обе стороны шага логируются в `ChatTurn` (поле `vision_text`, токены Flash — отдельно).
* Ошибка загрузки ресурса в консоли каталога (connection refused): один шаг — найти адрес в DevTools-логе браузерного теста или `test_page_js`; если это наш код (сокет, сервис поиска, статика) — починить, если внешнее или локальная среда — записать и не трогать.

Правила проекта из первого запуска остаются в силе (раунд, а не забег; без длинных тире в UI; `weco:modal` для новых окон; девять шаблонов; свой счётчик вместо `ratelimit.py`; зубастость через порчу файла с уникальным якорем; тесты лейблами; числа из логов).
ФАЗЫ −1…9 и 10.0 — сделаны
Не повторять. Итоги и таблицы приёмки — в хэндоффе и журнале.
ФАЗА 8½. Косметика подпунктов и свежие векторы

1. Парсер `problems/test_options_parse.py`: (а) повторный номер «1) (1) …» / «1. 1) …» — если число в скобках равно метке, убрать его из текста варианта; (б) для `boolean` — хвостовые строки, целиком состоящие из вариантов «Верно»/«Неверно» (с нумерацией или без, в одну строку через пробелы/табы или в две), отрезаются от `stem`. Тесты: по 3 фикстуры на каждый случай, включая ложные («Верно ли, что…» в середине условия — не трогать). Зубастость.
2. Команда: флаг `--ids ID,ID,…` (или файл) поверх существующих; выборка для (а) — 15 задач по отчёту третьего запуска (их id — в `reports/night_20260915/test_options/REPORT.md` или пересчитай регэкспом по базе), для (б) — все `boolean` с подпунктами, у которых хвост условия совпадает с паттерном. Порядок: `--revert` только для (а) → `--apply` (а) и (б) с новыми снимками → повторный `--dry-run` даёт 0. Инвариант: число живых виджетов не уменьшилось (было 5 485).
3. `build_embeddings --stale` локально — время и число пересчитанных в журнал (ожидается ≈ 3 251 + правки этой фазы). Затем `embeddings_export_vectors` в новый файл, старый удалить, размер и число векторов — в журнал; строку с именем файла обновить в `docs/SERVER.md`.
4. `docs/DATA.md`: дополнить раздел о подпунктах (двойная нумерация, «верно/неверно», пересчёт векторов). Notion: комментарий к карточке Фазы 8.

Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — СДЕЛАНО в третьем запуске (`scripts/glm_vision_probe.py`): `glm-5.3` картинки не принимает, `glm-5.3-flash` читает. Решение принято: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, двухшаговый паттерн из «Дополнения». Исходный текст пункта оставлен для контекста: Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (`glm-5.3-flash`, см. «Дополнение»), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель зрения (Flash) уходит список `(mime, bytes)`, максимум 5; в GLM-5.3 — только текст расшифровки (двухшаговый паттерн). Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения, или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `vision_text` (расшифровка Flash, blank), `vision_input_tokens`, `vision_output_tokens`, `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков: просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец раунда) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» (шлёт `weco:modal`, входит в `modalIsOpen()`) → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль только с аккаунтом: соперника нужно как-то называть» (шлёт `weco:modal`, входит в `modalIsOpen()`) с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но раунд ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге раунда дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время раунда; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза с серверной фиксацией и потолком, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев в потоке, поля лога, заголовок `X-Smart-Search-Ms`, экспорт векторов;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `embeddings_export_vectors`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам (для 1–5 таблица уже есть в хэндоффе, не переписывай, дополни): адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, перевоз векторов и включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.

Модель и усилие
Opus, effort High; на фазах 8, 10, 12 — Max; на механических шагах (чекпоинты, прогоны, документация) — Medium.
````

### Сообщение 21 — 15.09.2026 19:55 МСК, запуск 0cc7fb20

Длина: 29086 знаков.

Отличается от сообщения 20: тело промпта совпадает дословно; приписка про интернет и background tasks заменена на цитату отчёта о векторах («Векторы: пересчёт остановлен, как вы решили. В базе сохранено 3 200 из 4 096, осталось 896…») и требование «нужно доделать векторы и их досчитать, чтобы точно все из промпта было выполнено»

````text
"Векторы: пересчёт остановлен, как вы решили. В базе сохранено 3 200 из 4 096, осталось 896. Список их id лежит в reports/night_20260915/vectors_stale_remaining_ids.txt, команды продолжения — в журнале, docs/EMBEDDINGS.md и в карточке Notion «Надо»." нужно доделать векторы и их досчитать, чтобы точно все из промпта было выполнено:

Промпт для Claude Code — ночная автономная сессия «Баги, поиск, тесты, дуэль, чат: 15.09», ПРОДОЛЖЕНИЕ с Фазы 8½ и 10.1
Привет! Прочитай CLAUDE.md, затем прочитай текущие задачи в Notion-штабе — обе базы, и «Задачи», и «Решения».
Затем — обязательно — `claude/HANDOFF_NIGHT_20260915.md` и `reports/night_20260915/JOURNAL.md`: это состояние после первого запуска. Раздел «Дополнение для продолжения (после третьего запуска)» ниже важнее любых расхождений между ними и текстом фаз.
Что это за сессия
Ночная автономная сессия на машине Windows (`C:\Users\shipu\qls`, окружение `venv313\Scripts\python.exe`). Владелец спит, спрашивать некого. Утром он принимает всё глазами на локальном сервере и на скринах, потом сам пушит и выкатывает.
Промпт писался по состоянию `main` на 12.09.2026 (коммит `bae68c5`) и CLAUDE.md от 13.09; продолжение — по хэндоффу первого запуска (ветка `feat/night-20260915`, HEAD `58ef4bf9` или новее). Все решения владельца, на которых стоит сессия, приняты в чате 15.09, записаны в Notion «Решения» (семь карточек от 15.09) и повторены в «Дополнении» ниже — их не пересматривать.
Правило контекста. Работай до 20 % остатка. Как подойдёшь к порогу — доделай текущую фазу, сделай чекпоинт-коммит, допиши журнал, напиши отчёт и остановись. Владелец запустит этот же промпт снова. Первое действие любого запуска: если существует `reports/night_20260915/JOURNAL.md` — прочитай его и `git log --oneline -15` и продолжай с первой фазы, у которой в журнале нет пометки «✅». Не пытайся ужать фазы, чтобы «успеть всё»: половина четырнадцати фаз хуже, чем целиком сделанные семь. Порядок фаз не менять.
Стоп-гейтов в этой сессии нет, кроме трёх: `git push` не делаешь (пишешь точную команду в отчёт); в `main` не мержишь; боевой сервер и боевую базу не трогаешь вовсе — всё, что нужно сделать на проде, ты пишешь командами в отчёт. Рабочая локальная база `db.sqlite3`: владелец разрешил накатить на неё миграции и применить подпункты тестов (Фаза 8, обратимо по снимку). `runserver` у владельца не запущен; перед `migrate` всё равно проверь порт 8000 (`netstat -ano | findstr :8000`) — занят → не мигрируй, журнал, Фазу 8г пропусти.
Владелец в этот запуск на связи. Стратегическая развилка (что-то, что меняет поведение продукта или структуру данных и не описано в фазе) — задай вопрос коротко, с вариантами, и жди ответа. Мелочи и технические выборы — решай сам и записывай в журнал предположение. Расхождение якорей — стоп.
Чекпоинт-коммит после каждой фазы: `checkpoint: фаза N — <что сделано>`. `git add` только по именам файлов, никогда `.` и не паттерны.
Журнал `reports/night_20260915/JOURNAL.md`: по фазе — статус (✅ / ⚠️ частично / ⛔ не делал и почему), что сделано, числа, что осталось, принятые предположения. Пишется по ходу, не в конце.
Тесты. Каждая фаза с изменением кода заканчивается тестами, и у каждого нового теста проверена зубастость: закоммить фикс, временно верни дефект (`git stash` или правка), убедись, что тест КРАСНЫЙ, верни фикс, убедись, что зелёный. Запиши в журнал имя теста и что именно краснело. Во время работы — только быстрый круг явными лейблами (`scripts\run_tests.py <app.tests.module> …`): `--scope-from-git` на общем шаблоне `templates/_*.html` раздувается до полного шага A (~112 мин), это найдено в первом запуске. Вывод в файл `> лог 2>&1`, код возврата читать сразу, числа брать из лога, а не из памяти (инструмент иногда теряет вывод); `| tail` запрещён — он съедает код. Полный прогон всех пяти джобов CI — один раз, в Фазе 14.
Проверка глазами невозможна: ты не откроешь браузер как человек. Но Playwright установлен (им идут `test_design_canon` и браузерные тесты calc2) — headless-проверки с числовыми инвариантами (нет горизонтальной прокрутки, кнопка кликабельна, таймер не сдвинулся) — это твой инструмент. Образец уже есть в ветке: раннер `game/tests/browser_*.mjs` (Playwright в node, JSON после маркера `###RUSH-JSON###`) + питон-обёртка на `StaticLiveServerTestCase`; запуск `scripts/run_tests.py game.tests.test_browser_modals --only-serial`. Метка `serial` — только с записанной причиной («живой сервер + браузер»).
Принципы: хирургическая правка, минимальный код, ноль заглушек и мёртвых кнопок, только SVG-иконки, дизайн-канон `DESIGN.md`, тексты интерфейса — словами школьника. `makemigrations` только с явным именем приложения: `problems` — следующая 0067, `game` — с 0016. В тестах по странице — `assertTrue(x in html, 'коротко')`, не `assertIn` (при падении печатает весь HTML). Модели — только в `problems` (кроме двух записанных исключений). Комментарии в коде — по-русски, с «почему».
Что в сессию НЕ входит (владелец делает сам, с Mac по SSH): разбор проблемы с VPN на сервере; развёртывание контейнера `search` и включение `SEMANTIC_SEARCH_ENABLED` на бою; выкатка и прогон команд на боевой базе. Ты только готовишь для этого документацию и команды.
Effort: High. На фазах 8, 10, 12 — Max. На чекпоинтах, прогонах уже написанных тестов и правке документации — Medium.
Дополнение для продолжения (после третьего запуска)
Состояние. HEAD `58ef4bf9` (после фикса CSV-инъекции в `analytics_export`), дерево чистое (кроме личных неотслеживаемых файлов владельца). Закрыты фазы −1…9 и пункт 10.0. Хэндофф обновлён: раздел «Состояние после третьего запуска» в `claude/HANDOFF_NIGHT_20260915.md` — читать первым. Рабочая база мигрирована до `problems/0067`, подпункты тестов применены (4 076 задач, 16 282 подпункта, 3 251 условие укорочено, снимок для отката и копия базы сохранены — пути в журнале). Векторы экспортированы (14 082, 55 МБ) — до переписывания условий, поэтому файл устарел, см. Фазу 8½. Зрение: `glm-5.3` картинки не принимает, `glm-5.3-flash` читает.
Старт этого запуска: `git status`/`git diff --stat` (остатки → коммит или `stash`, как раньше), `manage.py check`, ветка и HEAD. Если Docker Desktop поднят (владелец обещал включить) — `docker compose -f docker-compose.dev.yml up -d` и проверь порт 55432: тогда в Фазе 14 миграции проверяются на PostgreSQL. Не поднят — журнал, без остановки.
Решения по хвостам третьего запуска (владелец согласился):

* Двойная нумерация у 15 задач («1) (1) …»): парсер режет повторный номер, когда он равен метке; переприменить только эти 15 через `--revert` по их id из снимка и `--apply --ids` с новым парсером, новый снимок, идемпотентность.
* Строка вариантов у «верно/неверно» («1) Верно 2) Неверно» и подобные в хвосте условия) у 554 задач — вырезать так же обратимо, как у остальных; прежняя инструкция «условие таких задач не меняется» была ошибкой: плитки дублируют строку. Парсер: хвостовая строка/строки только из вариантов «Верно/Неверно» (любой регистр, нумерация цифрой или буквой, одна или две строки) → `stem` без них; подпункты уже созданы, их не трогать.
* Устаревшие векторы у переписанных условий: пересчитать локально `build_embeddings --stale` (после ВСЕХ правок условий этого запуска), затем заново `embeddings_export_vectors` → новый файл; старый удалить; числа и время — в журнал и в команды для боя.
* Зрение чата: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, текст — `glm-5.3`. Двухшаговый паттерн ADR 0081: реплика с файлом сначала идёт во Flash с задачей «перепиши дословно всё, что написано на фото/страницах: текст, формулы (LaTeX), подписи к графикам; не оценивай и не решай», а расшифровка (с пометкой «[расшифровка фото]») вклеивается в текст реплики для GLM-5.3. Обе стороны шага логируются в `ChatTurn` (поле `vision_text`, токены Flash — отдельно).
* Ошибка загрузки ресурса в консоли каталога (connection refused): один шаг — найти адрес в DevTools-логе браузерного теста или `test_page_js`; если это наш код (сокет, сервис поиска, статика) — починить, если внешнее или локальная среда — записать и не трогать.

Правила проекта из первого запуска остаются в силе (раунд, а не забег; без длинных тире в UI; `weco:modal` для новых окон; девять шаблонов; свой счётчик вместо `ratelimit.py`; зубастость через порчу файла с уникальным якорем; тесты лейблами; числа из логов).
ФАЗЫ −1…9 и 10.0 — сделаны
Не повторять. Итоги и таблицы приёмки — в хэндоффе и журнале.
ФАЗА 8½. Косметика подпунктов и свежие векторы

1. Парсер `problems/test_options_parse.py`: (а) повторный номер «1) (1) …» / «1. 1) …» — если число в скобках равно метке, убрать его из текста варианта; (б) для `boolean` — хвостовые строки, целиком состоящие из вариантов «Верно»/«Неверно» (с нумерацией или без, в одну строку через пробелы/табы или в две), отрезаются от `stem`. Тесты: по 3 фикстуры на каждый случай, включая ложные («Верно ли, что…» в середине условия — не трогать). Зубастость.
2. Команда: флаг `--ids ID,ID,…` (или файл) поверх существующих; выборка для (а) — 15 задач по отчёту третьего запуска (их id — в `reports/night_20260915/test_options/REPORT.md` или пересчитай регэкспом по базе), для (б) — все `boolean` с подпунктами, у которых хвост условия совпадает с паттерном. Порядок: `--revert` только для (а) → `--apply` (а) и (б) с новыми снимками → повторный `--dry-run` даёт 0. Инвариант: число живых виджетов не уменьшилось (было 5 485).
3. `build_embeddings --stale` локально — время и число пересчитанных в журнал (ожидается ≈ 3 251 + правки этой фазы). Затем `embeddings_export_vectors` в новый файл, старый удалить, размер и число векторов — в журнал; строку с именем файла обновить в `docs/SERVER.md`.
4. `docs/DATA.md`: дополнить раздел о подпунктах (двойная нумерация, «верно/неверно», пересчёт векторов). Notion: комментарий к карточке Фазы 8.

Чекпоинт-коммит.
ФАЗА 10. Чат на задаче: GLM-5.3, три кнопки, файл с решением, полные логи
Что уже есть. Правая колонка страницы задачи `<section class="ai">` (ADR 0080): три кнопки-подсказки, ввод, `POST /catalog/api/chat/` → `chat.answer()` → `core.run('catalog_chat', …)`; история — шесть реплик с клиента, на сервере не хранится; только для вошедших; модель — общая `AI_PROVIDER`/`AI_MODEL` (по умолчанию `anthropic`/`claude-haiku-4-5`). Решение владельца: модель GLM-5.3 (не Flash), три кнопки «Объясни теорию» / «Как решать» / «Проверь моё решение», загрузка фото и PDF, честная и хладнокровная оценка без баллов, полные логи разговоров — цель беты понять, подходит ли модель (почерк, плохие фото, графики).
10.0. Диагностика зрения — СДЕЛАНО в третьем запуске (`scripts/glm_vision_probe.py`): `glm-5.3` картинки не принимает, `glm-5.3-flash` читает. Решение принято: `CATALOG_CHAT_VISION_MODEL = glm-5.3-flash`, двухшаговый паттерн из «Дополнения». Исходный текст пункта оставлен для контекста: Скрипт `scripts/glm_vision_probe.py` (не тест, запускается руками): рисует PNG 600×200 с текстом «Ответ: 42» и простым графиком (Pillow), шлёт через `GLMProvider.complete` с `images=[('image/png', bytes)]` и вопросом «Что написано на картинке? Ответь одной строкой», модели по очереди: `glm-5.3`, `glm-5.3-flash`. Пиши в журнал: ответ, `usage` (есть ли токены изображения), ошибка API, если была. Если ни одна не читает картинку — открой `https://docs.z.ai` (WebFetch), найди действующее имя модели со зрением у Z.AI и проверь её тем же скриптом. Итог фиксируй как настройку `CATALOG_CHAT_VISION_MODEL` (пусто = модель чата и так видит). Если ключа `GLM_API_KEY` в локальном `.env` нет — дальше делай всё, а в журнал крупно: «зрение не проверено, нет ключа». Модель для текста не менять ни при каком исходе — `glm-5.3`, решение владельца.
10.1. Настройки в `config/settings.py`: `CATALOG_CHAT_PROVIDER` (по умолчанию `glm`), `CATALOG_CHAT_MODEL` (`glm-5.3`), `CATALOG_CHAT_VISION_MODEL` (`glm-5.3-flash`, см. «Дополнение»), `AI_DAILY_COST_CAPS['catalog_chat'] = 1.0` ($ в сутки, переменная `CATALOG_CHAT_DAILY_CAP_USD`). `chat.answer` зовёт `core.run(..., provider=providers.get_provider(CATALOG_CHAT_PROVIDER), model=…)` — переопределения уже есть, см. как ими пользуется `rerank.py`. При исчерпанном потолке — человеческое сообщение в чате, не 500. `deploy/env.example` — новые переменные с комментарием.
10.2. Режимы. Параметр `mode` ∈ `theory | method | check | free` (`free` — обычный ввод, как сейчас). Системные блоки (по-русски, отдельно от общего профиля; общий запрет на данные профиля остаётся):

* `theory`: «Объясни теорию, нужную для этой задачи: понятия, формулы, типичные ловушки. Приведи короткий пример НЕ из этой задачи. Не решай задачу.»
* `method`: «Опиши метод и план шагов решения: какие величины ввести, какое условие использовать, в каком порядке считать. Итоговый ответ и подстановку чисел НЕ давай — задача остаётся за учеником.»
* `check`: в контекст добавляются эталонный `answer` и `solution` задачи (только в этом режиме, только в системный блок). Инструкция: «Перед тобой решение ученика (текст и/или фото). Оцени честно и хладнокровно: что верно, где первая ошибка и в чём она, чего не хватает. Баллы и оценки не ставь. Эталонное решение не пересказывай и итоговый ответ не раскрывай, если у ученика он неверен — укажи на шаг, где расходится, и задай вопрос, который ведёт к исправлению. Если фото нечитаемо или это не решение этой задачи — так и скажи.» Ответ до 1 200 символов (поднять `REPLY_MAX` для `check`).
* Домашний режим (`in_active_homework`) сохраняется поверх всех.

10.3. Файлы. Модель `ChatAttachment` в `problems/models_platform.py`: `user`, `problem`, `file` (`upload_to='chat/%Y/%m/'`), `mime`, `size`, `pages` (число страниц/картинок, которые ушли в модель), `pages_json` (пути производных PNG для PDF), `created_at`. Эндпоинт `POST /catalog/api/chat/upload/` (только вошедшие, CSRF, `multipart`): jpg/png/webp/pdf, ≤ 10 МБ, проверка магией (Pillow `verify` для картинок, `%PDF` для PDF), лимит 10 файлов на пользователя в сутки. PDF → первые 5 страниц → PNG шириной 1 400 px через PyMuPDF (`pymupdf` в `requirements/base.in`, пересобрать `.txt` тем же способом, каким собраны остальные — посмотри заголовок файла; `pip-audit` должен остаться зелёным). Картинки > 1 600 px по большей стороне — уменьшить, JPEG q85 (токены). В модель зрения (Flash) уходит список `(mime, bytes)`, максимум 5; в GLM-5.3 — только текст расшифровки (двухшаговый паттерн). Файлы никому не отдаются наружу (media закрыта) — только через админку файловой вьюхой по образцу `Feedback.screenshot` (ADR про «вторую и последнюю файловую вьюху» придётся дописать: третья — и объяснить, почему это тот же механизм; запиши в `docs/SECURITY.md`).
10.4. Интерфейс. В `<section class="ai">`: вместо трёх подсказок — три кнопки режимов с теми же классами `.ai-sug` (тексты: «Объясни теорию», «Как решать», «Проверь моё решение»), в строке ввода — кнопка-скрепка (SVG) с `<input type="file" hidden accept="image/*,application/pdf">`, чип прикреплённого файла с «×». «Проверь моё решение» без файла и без текста → подсказка в чате «Прикрепите фото или PDF решения, или опишите решение текстом». Ответы через `renderMath`, если он есть на странице. Индикатор «печатает» уже есть. `weco.track('chat_send', …)` (Фаза 9). Кнопки режимов остаются доступны в любой момент разговора (режим — свойство реплики).
10.5. Полные логи. Модель `ChatTurn`: `user`, `problem`, `thread` (uuid, генерирует клиент при загрузке страницы), `mode`, `user_text`, `attachment` (FK null), `vision_text` (расшифровка Flash, blank), `vision_input_tokens`, `vision_output_tokens`, `reply`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error` (blank), `created_at`. Пишется на каждую реплику, включая ошибочные. Как достать `usage` из `core.run` — смотри, как это делает `rerank._score_pool` (`result.usage`). Админка: список по `created_at`, фильтры `mode`, `model`, `user`, поиск по тексту; страница записи показывает реплики и ссылку на файл. Команда `chat_export --since … --out FILE` → JSONL по тредам.
Тесты: режимы собирают правильные системные блоки (`check` содержит эталон, `theory`/`method`/`free` — нет; данные профиля нигде — существующий P0-тест расширить); загрузка (тип, размер, магия, лимит), PDF из двух страниц (сгенерируй PyMuPDF) → 2 PNG нужной ширины; `ChatTurn` пишется при успехе и при ошибке провайдера (мок); потолок стоимости → сообщение, не 500; шаблон содержит три кнопки и скрепку.
Чекпоинт-коммит.
ФАЗА 11. Бесконечные тесты внутри Wecon Rush
Решение владельца: режим без времени, жизней, очков и лидерборда, на игровом пуле; решаешь тесты один за другим, можно вернуться назад и вперёд; вход — из Wecon Rush. Название на экране — «Бесконечные тесты», подпись «без времени, жизней и очков: просто решай».
Сервер (`game/config.py`, `views.py`, `state.py`):

* `PRACTICE = {'key': 'practice', 'title': 'Бесконечные тесты', 'question_types': ('boolean', 'single', 'multi')}` — отдельная константа, не запись в `MODES` (иначе поедут лидерборд, `pool_counts`, карточки режимов). Проверь все места, где перебирают `MODES`, что `practice` туда не попадает.
* `_new_state('practice', …)`: `duration=None`, `lives=None`, `practice=True`; TTL состояния 2 часа. Кандидаты — те же `_candidate_rows` с фильтром по трём типам; текущий фильтр окна фильтров применяется.
* `api_question`: для практики — как обычно. `api_answer`: при `state['practice']` не считать очки/время/жизни, не писать `GameResult`, ответ дополнить `correct_choices` (метки/индексы верных вариантов) — только в практике; в обычных режимах поле не отдавать (тест на это).
* Завершение: `api_finish` (или существующий конец раунда) в практике отдаёт сводку `answered, correct, skipped, accuracy` и не пишет рекорд. Лидерборд и «Мои рекорды» практику не видят.
* Счётчик доступных вопросов практики = сумма `pool_counts` трёх типов под фильтром (в `api_pool_counts` добавить ключ `practice`).

Клиент (`game.html`):

* Полоса на стартовом экране между карточками режимов и рядом `#entry-row`: заголовок «Бесконечные тесты», подпись, счётчик «N вопросов под фильтром», кнопка «Начать». Класс `.practice-band`, стиль как у карточек.
* `startRun('practice')`: экран игры с `body.practice`: скрыты `.hud-score`, `.timer-box`, `.time-track`, `.hud-lives`, `.hud-combo`; вместо них счётчик «Вопрос 12 · верных 9». После ответа — подсветка верного/неверного варианта по `correct_choices`, без дельты времени и без сердец; звуки «верно/неверно» оставить.
* История на клиенте: `practiceLog = [{q, chosen, correct}]`; кнопки «← Назад» и «Вперёд →» под вопросом (и стрелки клавиатуры): «Назад» показывает прошлый вопрос только для чтения (варианты заблокированы, отмечены ваш и верный), «Вперёд» — к следующему по истории или к новому вопросу. Пробел — «дальше без ответа» (пропуск, считается как `skipped`).
* Выход (✕/Esc) → окно «Закончить?» (шлёт `weco:modal`, входит в `modalIsOpen()`) → сводка практики («решено N, верных M, точность»), кнопки «Ещё раз» и «На старт». Никакого лидерборда.
* `weco.track('practice_start' / 'practice_end')`.

Тесты: состояние практики без `duration`/`lives`; `api_answer` не меняет `score`, отдаёт `correct_choices` только в практике; `GameResult` не создаётся; `practice` отсутствует в лидерборде и в `MODES`; стартовая страница содержит `.practice-band`; `pool_counts['practice']` = сумма трёх.
Чекпоинт-коммит.
ФАЗА 12. Дуэль: только с аккаунтом, лобби, синхронный старт со звуком, табло, итог
Что есть. Дуэль асинхронная: автор создаёт набор из окна «Бросить вызов», видит ссылку, может играть сразу; соперник приходит по ссылке позже; сокет `/ws/duel/<код>/` даёт presence и, когда оба на месте, `start` с `in: 3`, который каждый клиент отсчитывает локально, а автор в этот момент сидит в модалке и только потом переходит на страницу набора. Для анонима `duel_new` под `@login_required` отвечает редиректом на вход, `fetch` получает HTML, `r.json()` падает → «Не удалось создать вызов».
Решение владельца — строго синхронно: пока соперник не зашёл, играть нельзя; оба стартуют по одному отсчёту от 5 со звуком; аноним видит окно регистрации.
12а. Аноним. `duel_new` для XHR (`_wants_json`) без входа → JSON 403 `{'ok': False, 'error': 'login'}` вместо редиректа; страничный запрос — редирект как сейчас. Клиент: на `error === 'login'` (и при клике по карточке «Создать дуэль» без `CFG.is_authenticated`) — окно `#dm-auth` «Дуэль только с аккаунтом: соперника нужно как-то называть» (шлёт `weco:modal`, входит в `modalIsOpen()`) с кнопками «Создать аккаунт» → `/register/?next=/game/` и «Войти» → `/login/?next=/game/`.
12б. Лобби на странице набора. После успешного `duel_new` окно показывает «Создаём…» и сразу уводит автора на `play_url` (`/game/s/<код>/`). Для наборов `kind='duel'` страница набора вместо карточки «Играть» показывает лобби (`#duel-lobby`, переделать): крупный код комнаты (моноширинный, 40–48 px) с кнопкой «Скопировать код»; большая основная кнопка «Скопировать ссылку» (ссылка в `readonly input` под ней); строка состояния «Ждём соперника…» с тихой анимацией; кнопка «Отменить» → `/game/`. Кнопки «Играть» у дуэли нет ни у автора, ни у соперника. Соперник: страница `/game/d/<код>/` → «Принять вызов» → та же страница набора → то же лобби, в состоянии «Соперник: <имя автора>». «Играть по коду» с кодом дуэли ведёт туда же. Сокет подключается уже в лобби (сейчас — только в игре); модальное окно «Бросить вызов» больше не слушает сокет (`listen`, `countdown` из модалки убрать).
12в. Синхронный старт. `game/consumers.py`: `COUNTDOWN_S = 5`; когда в комнате два разных пользователя (по `present`, как сейчас), сервер пишет в комнату (`game/state.py`, словарь дуэли) `started_at = now_ms + 5000` и шлёт `duel.start` с `{at: started_at, now: now_ms, in: 5}`. Повторный `join`/`hello` в комнату с уже назначенным `started_at` получает то же сообщение (переподключение, перезагрузка) — клиент досчитает до того же момента или стартует сразу, если момент прошёл, но раунд ещё в пределах длительности режима. Клиент считает смещение `offset = now − Date.now()` при получении и ведёт отсчёт по `at + offset`, пересчитывая каждую секунду; на нуле зовёт `startRun()` сам. Отсчёт крупный (`.duel-countdown` 96 px по центру лобби), цифры 5…1, потом «Поехали!».
12г. Звук. В `game/static/game/sound.js` функция `countdown(n)` на WebAudio-осцилляторах в духе Марио Карт: для 5…1 — короткий низкий гудок (~660 Гц, 120 мс), на «Поехали!» — длинный высокий (~990 Гц, 450 мс). Уважает общий переключатель звука (`isOn`): звук выключен — отсчёт немой. Вызов — из клиента отсчёта на каждой секунде (`rushSound.countdown(n)`).
12д. Табло сверху. `#vs` упростить до одной строки на две стороны: имя, счёт крупно, «верных N», «время». Точность и комбо из табло убрать (остаются в итоге). На ширине ≤ 720 px стороны друг под другом, разрыв между. Никакого переноса цифр; проверь на 380 px Playwright-инвариантом (`scrollWidth ≤ clientWidth` у `.scene`).
12е. Итог дуэли. На странице `/game/d/<код>/` и в итоге раунда дуэли — таблица сравнения двоих: Очки · Верных · Ошибок · Пропусков · Точность · Лучшее комбо · Среднее время ответа · Время раунда; победитель подсвечен; кнопка «Реванш» остаётся. Бери только то, что реально хранится в `GameResult`/сводке; метрики, которых нет, не выдумывать и не считать приблизительно — опустить и записать в журнал, каких не хватает.
Тесты: `duel_new` XHR без входа → 403 JSON; страница набора дуэли не содержит кнопки «Играть» и содержит лобби с кодом; консьюмер при втором участнике шлёт `start` с `at`, `now`, `in: 5`; повторный `hello` получает тот же `at`; страница дуэли отдаёт таблицу сравнения при двух результатах; Playwright: лобби без горизонтальной прокрутки на 380 px, кнопка «Скопировать ссылку» ≥ 44 px высотой; `sound.js` содержит `countdown` (проверка через `node -e` на синтаксис).
Чекпоинт-коммит.
ФАЗА 13. Экраны Wecon Rush: конкретные правки раскладки
Решение владельца: без макета, по списку, приёмка по скринам утром. Правило: только чинить очевидные дефекты раскладки — переносы, наезды, дубли, неровные высоты. Не перерисовывать и не придумывать новые элементы. Сомневаешься — не трогай, запиши в журнал.

1. Лидерборд `#lb-card`. Вкладки режимов `#lb-modes` в одну строку без переноса на вторую: `flex-wrap: nowrap; overflow-x: auto`, скрытая полоса прокрутки; на широком экране всё помещается. Сегменты `#lb-period` и `#lb-metric` одной высоты, одинаковые отступы. Строки таблицы — сетка «место | имя и дата | значение», значение прижато вправо, дата мельче под именем. Подвал «Войдите, чтобы попасть в таблицу» → одна ссылка-кнопка «Войти» (`/login/?next=/game/`).
2. Дубль входов. Строка текстовых ссылок «Вызов дня · Дуэль с другом» над карточками дублирует карточки `#entry-row` — убрать строку (и привязку `document.querySelector('a[href="/game/duel/new/"]')` оставить с null-проверкой).
3. Карточки `#entry-row`. Все одной высоты (`align-items: stretch`), одинаковые внутренние отступы, структура «заголовок — одна строка подписи — действие». «Бросить вызов» → «Создать дуэль», подпись «соперник по ссылке или коду». `data-soon` у карточек: выясни, что делает, и убери, если помечает «скоро» у уже работающих карточек. Ниже 720 px — две колонки, ниже 480 — одна.
4. «Добавить фильтры». Оставить по центру; показывать число активных фильтров бейджем, как у кнопки «Все фильтры» в каталоге.
5. Карточки режимов. Равная высота в ряду; строка «рекорд» не должна двигать соседей (резервировать высоту).
6. Остальные страницы игры — `daily.html`, `daily_board.html`, `duel.html`, `set_board.html`, `result.html`, `stats.html`: Playwright-инварианты на ширинах 380 и 1280 — `document.documentElement.scrollWidth ≤ clientWidth`, у всех кликабельных элементов высота ≥ 32 px, у кнопок текст не переносится на три строки. Что красное — чинить точечно (перенос, отступ, ширина), результат — в один общий тест `game/tests/test_browser_layout.py`.
7. Тексты кнопок — глаголы, единый регистр («Играть», «Создать дуэль», «Скопировать»), без эмодзи, значки только SVG.

В журнал — список «страница → что изменил → почему» для утреннего сравнения по скринам.
Чекпоинт-коммит.
ФАЗА 14. Финал: полный прогон, документация, Notion, отчёт

1. `manage.py check`; `manage.py makemigrations --check --dry-run` — ничего не предлагает.
2. Полный прогон всех пяти джобов CI по списку из CLAUDE.md, вывод в `reports/night_20260915/ci_<job>.log`, код возврата читать сразу после каждой команды. Ожидаемо красные только три модуля, зашитые на спецификацию v1 (`test_corpus_diagnostics`, `test_embedding_formula`, `test_embeddings_transfer`, 14 падений + 4 ошибки) — всё остальное красное чинишь; не смог — в журнал с именем теста и причиной. `ruff`, `bandit`, `pip-audit` (после `pymupdf`!), миграции с нуля на PostgreSQL, `check --deploy` — статус каждого поимённо в отчёт.
3. Документация (техника — в `docs/`, не в CLAUDE.md, кроме команд):
   * `docs/GAME.md`: практика, синхронная дуэль (лобби, `started_at`, звук), пауза с серверной фиксацией и потолком, обработка сбоев сети, кнопка «Плохая задача»;
   * `docs/SECURITY.md`: `/api/track/` (csrf_exempt + Origin), вложения чата (третья файловая вьюха), `/api/problem-report/`;
   * `docs/SERVER.md`: gunicorn-конфиг с прогревом; раздел включения смысловой ноги; команда `test_options_from_statement` на бою;
   * `docs/EMBEDDINGS.md`: прогрев в потоке, поля лога, заголовок `X-Smart-Search-Ms`, экспорт векторов;
   * `docs/DATA.md`: что сделано с подпунктами тестов, снимок, откат;
   * `CLAUDE.md`: только новые команды в «Часто нужные команды» (`test_options_from_statement`, `embeddings_export_vectors`, `analytics_export`, `chat_export`, `scripts/glm_vision_probe.py`) и блок «Текущий фокус»;
   * ADR в `docs/adr/` на четыре решения: своя аналитика; подпункты тестов из условия (с обратимостью); синхронная дуэль; режим практики. Формат — как у соседних ADR;
   * `CLAUDE_ARCHIVE.md`: история сессии.
4. Notion: карточки фаз → «На проверке» (не «Готово»); «Результаты» (`39bb11c9-2bc1-81da-91c5-e890da24d3c5`) — одна запись с числами: живых виджетов до/после, применено задач, время прогрева, тесты добавлены / прогон; «Решения» — ссылки на ADR в карточках из Фазы 0. Если что-то не сделано — карточка «Надо» с описанием остатка.
5. Отчёт владельцу (в конце сессии и в журнале), по каждой фазе: что сделано / результат с цифрами / ошибки и чего не смог / что записано в Notion. Затем три списка:
   * Утренняя приёмка — по фазам (для 1–5 таблица уже есть в хэндоффе, не переписывай, дополни): адрес, что нажать, что должно быть (например: «/game/ → Блиц → открыть „Проблема или предложение“ → нажать пробел и 1 → вопрос на месте, таймер стоит»);
   * Команды для боя, в порядке выполнения: пуш ветки (точная команда), после мержа — деплой по SERVER.md (миграции накатит entrypoint), перезапуск с новым gunicorn-конфигом, `test_options_from_statement --dry-run` → `--apply` изнутри контейнера, перевоз векторов и включение смысловой ноги (раздел SERVER.md) — и что проверить после каждого шага;
   * Не сделано / сделано частично — честно, с причинами.
6. Последний чекпоинт-коммит и команда пуша в отчёте: `git push -u origin feat/night-20260915`. В `main` не мержить.

Модель и усилие
Opus, effort High; на фазах 8, 10, 12 — Max; на механических шагах (чекпоинты, прогоны, документация) — Medium.
````

### Сообщение 22 — 15.09.2026 20:48 МСК, запуск 0cc7fb20

Длина: 44 знаков.

````text
ОК, ЖДУ ВЕКТОРА, ПОТОМ ДОДЕЛАЙ ВСЁ ПО СПИСКУ
````

### Сообщение 23 — 16.09.2026 01:55 МСК, запуск 0cc7fb20

Длина: 156 знаков.

````text
подготовб полный хэндофф этой сессиии - шаги, изменения, мои промптыя, результаты на данный момент, хронология изменений и так далее. подробно в формате .мд
````

