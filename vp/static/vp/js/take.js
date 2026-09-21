/*
 * Прохождение варианта «Высшей пробы» в браузере.
 *
 * Ванильный JS, без сборки. Один файл, разделы по порядку:
 *   1. ответы — чтение полей, «отвечено», плитки навигатора;
 *   2. «сейчас здесь» и переход к заданию;
 *   3. клавиатура: Enter ведёт по змейке вниз и НИКОГДА не сдаёт работу;
 *   4. шапка: высота, тема;
 *   5. автосохранение пачкой;
 *   6. время: часы, состояния шапки, опрос сервера;
 *   7. сдача: окно подтверждения, «время вышло».
 *
 * ⚠️ КЛИЕНТ НЕ ИСТОЧНИК ПРАВДЫ О ВРЕМЕНИ. Он рисует обратный отсчёт (часы —
 * `platform/exam_timer.js`: монотонные, `Date.now()` не вызывается, серверная
 * сверка умеет только УМЕНЬШИТЬ остаток), а решение «время вышло» принимает
 * СЕРВЕР. Здесь мы приходим к нему сдаваться.
 *
 * ⚠️ Имена узлов задаёт `templates/vp/take.html` и `_take_item.html`:
 * `#vp-item-<n>`, `.vp-cell[data-n]`, поля `name="item-<n>"`.
 */
(function () {
  'use strict';

  var cfgNode = document.getElementById('vp-config');
  var form = document.getElementById('vp-form');
  if (!cfgNode || !form) { return; }
  var cfg = JSON.parse(cfgNode.textContent);

  function $(id) { return document.getElementById(id); }
  function card(n) { return document.getElementById('vp-item-' + n); }
  function cells(n) {
    return document.querySelectorAll('.vp-cell[data-n="' + n + '"]');
  }
  function itemOf(node) {
    var box = node && node.closest ? node.closest('.vp-item') : null;
    return box ? parseInt(box.dataset.n, 10) : null;
  }
  var reduceMotion = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var countNode = $('vp-answered');
  var stateNode = $('vp-save-state');
  var csrfField = form.querySelector('input[name=csrfmiddlewaretoken]');
  var csrf = csrfField ? csrfField.value : '';
  function now() { return performance.now(); }

  // =============================================================== 1. ответы
  /** Что сейчас введено в задании — в том виде, в каком это уходит на сервер. */
  function readValue(n) {
    var box = card(n);
    if (!box) { return null; }
    var kind = box.dataset.kind;
    if (kind === 'short_text') {
      var field = box.querySelector('input[type=text]');
      return field ? field.value.trim() : '';
    }
    if (kind === 'match') {
      var pairs = {};
      box.querySelectorAll('select[data-key]').forEach(function (select) {
        if (select.value !== '') { pairs[select.dataset.key] = parseInt(select.value, 10); }
      });
      return pairs;
    }
    var marked = box.querySelectorAll(
      'input[type=radio]:checked, input[type=checkbox]:checked');
    var values = Array.prototype.map.call(marked, function (input) {
      return parseInt(input.value, 10);
    });
    return kind === 'single' ? (values.length ? values[0] : null) : values;
  }

  /** «Отвечено» — как на сервере: пустая строка, пустой набор, ничего — не ответ. */
  function isAnswered(n) {
    var value = readValue(n);
    if (value === null || value === '') { return false; }
    if (Array.isArray(value)) { return value.length > 0; }
    if (typeof value === 'object') { return Object.keys(value).length > 0; }
    return true;
  }

  function missedNumbers() {
    return cfg.numbers.filter(function (n) { return !isAnswered(n); });
  }

  function recount() {
    if (countNode) { countNode.textContent = cfg.numbers.filter(isAnswered).length; }
  }

  function repaintAnswered(n) {
    var answered = isAnswered(n);
    cells(n).forEach(function (cell) { cell.classList.toggle('is-answered', answered); });
    recount();
  }

  // ============================================ 2. «сейчас здесь», переход
  var currentN = null;

  /** На телефоне плитки — полоса с прокруткой: текущую держим в поле зрения. */
  function keepCellVisible(n) {
    var strip = $('vp-strip');
    if (!strip || strip.offsetParent === null) { return; }
    var cell = strip.querySelector('.vp-cell[data-n="' + n + '"]');
    if (!cell) { return; }
    var offset = cell.getBoundingClientRect().left
      - strip.getBoundingClientRect().left + strip.scrollLeft;
    strip.scrollLeft = offset - (strip.clientWidth - cell.offsetWidth) / 2;
  }

  function setCurrent(n) {
    if (n === currentN) { return; }
    if (currentN !== null) {
      var old = card(currentN);
      if (old) { old.classList.remove('is-current'); }
      cells(currentN).forEach(function (cell) {
        cell.classList.remove('is-current');
        cell.removeAttribute('aria-current');
      });
    }
    currentN = n;
    if (n !== null) {
      card(n).classList.add('is-current');
      cells(n).forEach(function (cell) {
        cell.classList.add('is-current');
        cell.setAttribute('aria-current', 'true');
      });
      keepCellVisible(n);
    }
  }

  /** Переводит фокус в задание. block: 'nearest' (Enter) или 'center' (номер). */
  function focusItem(n, block) {
    var box = card(n);
    if (!box) { return; }
    var target = box.querySelector('input[type=text]')
      || box.querySelector('input[type=radio]:checked, input[type=checkbox]:checked')
      || box.querySelector('input[type=radio], input[type=checkbox], select');
    box.scrollIntoView({ block: block || 'nearest',
                         behavior: reduceMotion ? 'auto' : 'smooth' });
    if (target) { target.focus({ preventScroll: true }); }
  }

  // ========================================================== 3. клавиатура
  /** Enter ведёт по заданиям вниз (Shift+Enter — вверх): из поля змейки — в
   * следующее поле змейки, из последнего — в первое задание следующего блока.
   * Tab работает нативно: порядок фокуса совпадает с порядком заданий. */
  function moveFrom(n, direction) {
    var texts = cfg.textNumbers || [];
    var next = texts[texts.indexOf(n) + direction];
    if (next === undefined && direction > 0) {
      next = cfg.numbers[cfg.numbers.indexOf(n) + 1];   // змейка кончилась — дальше
    }
    if (next !== undefined) { focusItem(next, 'nearest'); }
  }

  form.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' || event.isComposing) { return; }
    var target = event.target;
    if (!(target && target.tagName === 'INPUT' && target.type === 'text')) { return; }
    event.preventDefault();               // Enter форму не отправляет, никогда
    var n = itemOf(target);
    if (n !== null) { moveFrom(n, event.shiftKey ? -1 : 1); }
  });

  form.addEventListener('focusin', function (event) {
    var n = itemOf(event.target);
    if (n !== null) { setCurrent(n); }
  });

  // Одна правка меняет сразу несколько индикаторов: поле, плитку навигатора,
  // общий счётчик (DESIGN 2.9).
  function onEdited(event) {
    var n = itemOf(event.target);
    if (n === null) { return; }
    repaintAnswered(n);
    paintBanner();
    markDirty(n);
  }
  form.addEventListener('input', onEdited);
  form.addEventListener('change', onEdited);
  // Ушли из поля — не ждём тишины в 3 секунды (но и не чаще одного запроса в 10).
  form.addEventListener('focusout', function (event) {
    var n = itemOf(event.target);
    if (n !== null && dirty[n]) { scheduleFlush(0); }
  });

  document.addEventListener('click', function (event) {
    var cell = event.target.closest ? event.target.closest('.vp-cell') : null;
    if (!cell) { return; }
    event.preventDefault();
    focusItem(parseInt(cell.dataset.n, 10), 'center');
  });

  // ============================================================== 4. шапка
  /** Высота липкой шапки — переменной: от неё зависят отступы прокрутки, чтобы
   * шапка не закрывала поле, в которое перешёл фокус. */
  function measureBar() {
    var bar = $('vp-bar');
    if (bar) {
      document.documentElement.style.setProperty('--vp-bar-h', bar.offsetHeight + 'px');
    }
  }
  window.addEventListener('resize', measureBar);
  if (window.ResizeObserver && $('vp-bar')) {
    new ResizeObserver(measureBar).observe($('vp-bar'));
  }

  // Переключатель темы: шапка сайта здесь спрятана, кнопка жмёт её скрытый
  // переключатель — реализация темы на сайте одна (`_theme_toggle.html`).
  var themeButton = $('vp-theme');
  function paintTheme() {
    if (themeButton) {
      themeButton.textContent =
        document.documentElement.getAttribute('data-theme') === 'dark' ? '☀' : '☾';
    }
  }
  if (themeButton) {
    themeButton.addEventListener('click', function () {
      var site = $('theme-toggle');
      if (site) { site.click(); }
      paintTheme();
    });
    paintTheme();
  }

  // ================================================ 5. автосохранение пачкой
  // Изменения копятся и уходят ОДНОЙ пачкой: через 3 секунды после последнего
  // нажатия, но не чаще одного запроса в 10 секунд; сразу (без ожидания) — только
  // при уходе со страницы. Потеря фокуса полем приближает отправку к моменту, когда
  // минимальный интервал позволит, но интервал не нарушает.
  var IDLE_MS = 3000;
  var MIN_GAP_MS = 10000;
  var dirty = {};          // n → true, пока сервер не подтвердил ТЕКУЩЕЕ значение
  var version = {};        // n → счётчик правок (чтобы не снять «грязное» зря)
  var flushTimer = null;
  var lastSentAt = null;
  var inFlight = false;
  var offline = false;
  var stopped = false;

  function anyDirty() { return Object.keys(dirty).length > 0; }

  function paintSave() {
    if (!stateNode) { return; }
    stateNode.classList.toggle('is-offline', offline);
    if (offline) {
      stateNode.textContent = 'нет связи, ответы сохранены на странице, пробуем отправить';
    } else if (inFlight || anyDirty()) {
      stateNode.textContent = 'сохраняем…';
    } else {
      stateNode.textContent = 'сохранено';
    }
  }

  function markDirty(n) {
    if (stopped) { return; }
    version[n] = (version[n] || 0) + 1;
    dirty[n] = true;
    paintSave();
    scheduleFlush(IDLE_MS);
  }

  /** Отправка через `delay` мс, но не раньше, чем пройдёт MIN_GAP_MS с прошлой. */
  function scheduleFlush(delay) {
    if (stopped) { return; }
    var wait = delay;
    if (lastSentAt !== null) { wait = Math.max(wait, lastSentAt + MIN_GAP_MS - now()); }
    clearTimeout(flushTimer);
    flushTimer = setTimeout(flush, Math.max(0, wait));
  }

  function collect() {
    var numbers = Object.keys(dirty).map(Number).sort(function (a, b) { return a - b; });
    var sent = {};
    var answers = numbers.map(function (n) {
      sent[n] = version[n] || 0;
      return { item: n, raw: readValue(n) };
    });
    return { answers: answers, sent: sent };
  }

  function flush() {
    flushTimer = null;
    if (stopped || inFlight || !anyDirty()) { paintSave(); return; }
    var batch = collect();
    inFlight = true;
    lastSentAt = now();
    paintSave();
    fetch(cfg.saveUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ answers: batch.answers })
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .then(function (result) {
        inFlight = false;
        offline = false;
        if (result.status === 409) { onClosed(); return; }
        if (result.ok) {
          Object.keys(batch.sent).forEach(function (key) {
            if ((version[key] || 0) === batch.sent[key]) { delete dirty[key]; }
          });
          if (!anyDirty()) { forgetStash(); }
          onServerTime(result.data.seconds_remaining);
        } else if (result.data && result.data.retry) {
          offline = true;               // сервер честно сказал «не сохранил» — повтор
        } else {
          // Отказ по существу (400): повторять то же самое бессмысленно.
          Object.keys(batch.sent).forEach(function (key) { delete dirty[key]; });
        }
        paintSave();
        if (anyDirty()) { scheduleFlush(offline ? MIN_GAP_MS : IDLE_MS); }
      })
      .catch(function () {
        inFlight = false;
        offline = true;
        paintSave();
        scheduleFlush(MIN_GAP_MS);
      });
  }

  /** Работа закрыта на сервере (сдана или время вышло): идём к нему сдаваться. */
  function onClosed() {
    // Без таймера «закрыто» значит «сдано в другой вкладке» — экран «время вышло»
    // был бы неправдой: просто идём на результат.
    if (timer) { enterTimeUp(); } else { submitNow(false); }
  }

  function onServerTime(seconds) { syncFromServer(seconds); }

  // --- откладывание несохранённого на время перезагрузки -------------------------
  // ⚠️ `sendBeacon` доставляется ПАРАЛЛЕЛЬНО загрузке новой страницы: сервер может
  // отрисовать её раньше, чем дойдёт последняя запись, — участник увидел бы пустые
  // поля, хотя всё сохранено. Поэтому несохранённое ещё и СИНХРОННО откладывается в
  // sessionStorage и при загрузке возвращается в поля (и уходит на сервер снова).
  var STORE_KEY = 'vp:dirty:' + cfg.saveUrl;

  function forgetStash() {
    try { sessionStorage.removeItem(STORE_KEY); } catch (error) { /* нет хранилища */ }
  }

  function stashDirty() {
    try {
      var snapshot = {};
      Object.keys(dirty).forEach(function (n) { snapshot[n] = readValue(parseInt(n, 10)); });
      if (Object.keys(snapshot).length) {
        sessionStorage.setItem(STORE_KEY, JSON.stringify(snapshot));
      } else {
        sessionStorage.removeItem(STORE_KEY);
      }
    } catch (error) { /* хранилище недоступно — остаётся sendBeacon */ }
  }

  /** Возвращает значение в поля задания (обратное к `readValue`). */
  function applyValue(n, value) {
    var box = card(n);
    if (!box) { return; }
    var kind = box.dataset.kind;
    if (kind === 'short_text') {
      var field = box.querySelector('input[type=text]');
      if (field) { field.value = value || ''; }
    } else if (kind === 'match') {
      box.querySelectorAll('select[data-key]').forEach(function (select) {
        var chosen = value && value[select.dataset.key];
        select.value = chosen === undefined || chosen === null ? '' : String(chosen);
      });
    } else {
      var wanted = kind === 'single' ? (value === null ? [] : [value]) : (value || []);
      box.querySelectorAll('input[type=radio], input[type=checkbox]').forEach(function (input) {
        input.checked = wanted.indexOf(parseInt(input.value, 10)) !== -1;
      });
    }
  }

  function restoreDirty() {
    var snapshot = null;
    try { snapshot = JSON.parse(sessionStorage.getItem(STORE_KEY) || 'null'); }
    catch (error) { snapshot = null; }
    forgetStash();
    if (!snapshot) { return; }
    Object.keys(snapshot).forEach(function (key) {
      var n = parseInt(key, 10);
      applyValue(n, snapshot[key]);
      repaintAnswered(n);
      markDirty(n);                     // и на сервер — ещё раз, повтор безвреден
    });
  }

  /** Уход со страницы: всё несохранённое уезжает сразу, без интервала. `sendBeacon`
   * не умеет заголовков, поэтому шлёт форму: токен CSRF и та же пачка строкой. */
  function flushOnLeave() {
    if (stopped) { return; }
    stashDirty();
    if (!anyDirty()) { return; }
    var payload = JSON.stringify({ answers: collect().answers });
    var data = new FormData();
    data.append('csrfmiddlewaretoken', csrf);
    data.append('payload', payload);
    var queued = false;
    try { queued = navigator.sendBeacon && navigator.sendBeacon(cfg.saveUrl, data); }
    catch (error) { queued = false; }
    if (!queued) {
      try {
        fetch(cfg.saveUrl, { method: 'POST', keepalive: true, credentials: 'same-origin',
                             headers: { 'X-CSRFToken': csrf }, body: data });
      } catch (error) { /* страница закрывается — больше сделать нечего */ }
    }
  }

  window.addEventListener('pagehide', flushOnLeave);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') { flushOnLeave(); } else { forgetStash(); }
  });
  window.addEventListener('online', function () {
    offline = false; paintSave(); if (anyDirty()) { scheduleFlush(0); }
  });
  window.addEventListener('offline', function () { offline = true; paintSave(); });
  // Возврат кнопкой «назад» из кэша страницы: работа могла быть уже сдана, а
  // страница ожила бы со старым состоянием. Решает сервер.
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) { window.location.reload(); }
  });

  // ============================================================== 6. время
  var POLL_MS = 20000;
  var timer = (cfg.timed && window.ExamTimer)
    ? window.ExamTimer.create({ seconds: cfg.seconds }) : null;
  var timeUp = false;
  var intervals = [];
  var banner = $('vp-banner');
  var timerNode = $('vp-timer');
  var clockNode = $('vp-clock');
  var capNode = $('vp-timer-cap');

  function plural(n, one, few, many) {
    var m = Math.abs(n) % 100;
    if (m >= 11 && m <= 14) { return many; }
    m = m % 10;
    if (m === 1) { return one; }
    if (m >= 2 && m <= 4) { return few; }
    return many;
  }

  function setBanner(text, danger) {
    if (!banner) { return; }
    if (text === null) { banner.hidden = true; return; }
    banner.hidden = false;
    banner.classList.toggle('is-danger', danger);
    // Живой регион: перезапись тем же текстом заставила бы читалку экрана
    // повторять фразу каждую секунду.
    if (banner.textContent !== text) { banner.textContent = text; }
  }

  function paintBanner() {
    if (!timer) { return; }
    var left = timer.remaining();
    if (timeUp || left <= 60) {
      setBanner('Последняя минута. Работа сдастся сама — всё, что введено, '
        + 'засчитается.', true);
    } else if (left <= 300) {
      var missed = missedNumbers();
      setBanner('Осталось пять минут. ' + (missed.length
        ? 'Не отвечено ' + missed.length + ' '
          + plural(missed.length, 'задание', 'задания', 'заданий')
          + ': ' + missed.join(', ') + '.'
        : 'Все задания отвечены.'), false);
    } else {
      setBanner(null, false);
    }
  }

  function paintTimer() {
    if (!timer || !timerNode) { return; }
    var left = timer.remaining();
    var danger = timeUp || left <= 60;
    var warn = !danger && left <= 300;
    timerNode.textContent = timeUp ? '00:00' : timer.text();
    clockNode.classList.toggle('is-warn', warn);
    clockNode.classList.toggle('is-danger', danger);
    if (capNode) {
      capNode.textContent = timeUp ? 'время вышло'
        : (danger ? 'последняя минута'
          : (warn ? 'осталось пять минут' : 'осталось'));
    }
    paintBanner();
  }

  function syncFromServer(value) {
    if (timer && timer.applyServer(value) === 'accepted') { paintTimer(); }
  }

  function tick() {
    if (!timer || timeUp) { return; }
    paintTimer();
    if (timer.expired()) { enterTimeUp(); }
  }

  /** Опрос сервера: клиент рисует секунды сам, а тут сверяется с настоящими. */
  function pollTime() {
    if (stopped || timeUp || !cfg.timeUrl) { return; }
    fetch(cfg.timeUrl, { credentials: 'same-origin',
                         headers: { 'X-Requested-With': 'fetch' } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        offline = false;
        if (data.expired) { enterTimeUp(); return; }
        syncFromServer(data.seconds_remaining);
        paintSave();
      })
      .catch(function () { /* сеть отвалилась — отсчёт идёт своими часами */ });
  }

  // ============================================================== 7. сдача
  function stopAll() {
    stopped = true;
    clearTimeout(flushTimer);
    intervals.forEach(function (id) { clearInterval(id); });
    intervals = [];
  }

  /** Форма уезжает на сервер со ВСЕМИ полями: последняя порция набранного не
   * теряется, даже если автосохранение отстало. */
  function submitNow(auto) {
    if (form.dataset.submitted) { return; }
    form.dataset.submitted = '1';
    var wasDirty = anyDirty() && !offline && !auto;
    var batch = wasDirty ? collect() : null;
    stopAll();
    forgetStash();
    var flag = $('vp-auto');
    if (flag) { flag.value = auto ? '1' : '0'; }
    if (!batch) { form.submit(); return; }
    // ⚠️ Стереть ответ можно только через `save`, а он несёт лишь то, что участник
    // менял: пустые поля формы сдачи ничего не стирают (устаревшая страница не
    // должна затирать сохранённое). Поэтому сначала дожидаемся отправки изменённого.
    var sent = false;
    function go() { if (!sent) { sent = true; form.submit(); } }
    setTimeout(go, 4000);               // не ждём дольше: форма — запасной путь
    fetch(cfg.saveUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ answers: batch.answers })
    }).then(go, go);
  }

  /** Время вышло (по нашим часам, опросу или ответу 409): показываем экран и
   * сдаёмся. Засчитывается всё, что введено, — решение за сервером. */
  function enterTimeUp() {
    if (timeUp) { return; }
    timeUp = true;
    stopAll();
    paintTimer();
    document.body.classList.add('vp-is-timeup');
    setTimeout(function () { submitNow(true); }, 300);
  }

  var dialog = $('vp-dialog');
  function openDialog() {
    var missed = missedNumbers();
    var total = cfg.numbers.length;
    var head = timer ? 'Осталось ' + timer.text() + ', и не отвечено ' : 'Не отвечено ';
    var text = missed.length
      ? head + missed.length + ' ' + plural(missed.length, 'задание', 'задания', 'заданий')
        + '. Неотвеченное засчитывается как ноль.'
      : 'Отвечены все ' + total + ' ' + plural(total, 'задание', 'задания', 'заданий') + '.';
    text += ' После сдачи менять ответы нельзя.';

    if (!dialog || typeof dialog.showModal !== 'function') {
      if (window.confirm(text)) { submitNow(false); }
      return;
    }
    $('vp-dialog-text').textContent = text;
    var chips = $('vp-dialog-chips');
    chips.textContent = '';
    missed.forEach(function (n) {
      var link = document.createElement('a');
      link.className = 'vp-chip';
      link.href = '#vp-item-' + n;
      link.dataset.n = n;
      link.textContent = n;
      chips.appendChild(link);
    });
    dialog.showModal();
  }

  $('vp-submit').addEventListener('click', openDialog);
  $('vp-back').addEventListener('click', function () { dialog.close(); });
  $('vp-confirm').addEventListener('click', function () {
    dialog.close();
    submitNow(false);
  });
  // Номер в окне: закрыть окно и прокрутить к заданию.
  $('vp-dialog-chips').addEventListener('click', function (event) {
    var chip = event.target.closest ? event.target.closest('.vp-chip') : null;
    if (!chip) { return; }
    event.preventDefault();
    dialog.close();
    focusItem(parseInt(chip.dataset.n, 10), 'center');
  });

  measureBar();
  restoreDirty();
  recount();
  paintSave();
  paintTimer();
  if (timer) {
    intervals.push(setInterval(tick, 1000));
    intervals.push(setInterval(pollTime, POLL_MS));
  }
})();
