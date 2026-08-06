/*
 * Контрольная в браузере: таймер и автосохранение.
 *
 * ⚠️ КЛИЕНТ НЕ ИСТОЧНИК ПРАВДЫ О ВРЕМЕНИ. Он рисует обратный отсчёт, но
 * решение «время вышло» принимает СЕРВЕР. Сама арифметика отсчёта живёт в
 * `exam_timer.js` (её можно проверить без браузера): часы там МОНОТОННЫЕ,
 * `Date.now()` не вызывается ни разу, а серверная сверка умеет только
 * УМЕНЬШИТЬ остаток.
 *
 * ⚠️ СВЕРКА ИДЁТ ПО ТАЙМЕРУ, А НЕ ПО НАБОРУ ТЕКСТА. Раньше остаток
 * пересинхронизировался только вместе с автосохранением — то есть лишь
 * когда ученик печатал. Тот, кто просто смотрел на таймер, не сверялся с
 * сервером ни разу. Теперь есть отдельный лёгкий запрос раз в 15 секунд.
 *
 * ⚠️ РАБОТА НЕ ТЕРЯЕТСЯ. Изменение уезжает через 2 секунды после остановки
 * ввода и при потере фокуса. Пропала сеть — накопленное лежит в памяти
 * страницы, повтор каждые 10 секунд, на экране честное «нет связи».
 * Последняя порция уезжает ещё раз вместе с нажатием «Завершить»: обычной
 * отправкой формы, так что даже упавший автосейв ничего не съедает.
 */
(function () {
  'use strict';

  var config = window.EXAM || {};
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';

  var pending = {};        // id позиции → {answer, solution} к отправке
  var offline = false;
  var saving = 0;
  var timers = {};

  var stateNode = document.getElementById('save-state');
  var timerNode = document.getElementById('timer');

  // ---------------------------------------------------------------- таймер
  var rawSeconds = timerNode && timerNode.dataset.seconds !== ''
    ? parseInt(timerNode.dataset.seconds, 10) : null;
  var timer = window.ExamTimer.create({
    seconds: (rawSeconds === null || isNaN(rawSeconds)) ? null : rawSeconds
  });
  var timeUp = false;

  function paintTimer() {
    if (!timerNode || !timer.hasLimit()) { return; }
    var left = timer.remaining();
    timerNode.textContent = timeUp ? 'время вышло' : timer.text();
    // Предупреждающий цвет за 5 минут, тревожный за 1. Без звуков.
    timerNode.classList.toggle('warn', !timeUp && left <= 300 && left > 60);
    timerNode.classList.toggle('danger', timeUp || left <= 60);
  }

  function tick() {
    if (!timer.hasLimit() || timeUp) { return; }
    paintTimer();
    if (timer.expired()) {
      // Время кончилось по нашему счёту. Уходим на сдачу — решение
      // «действительно ли вышло» принимает СЕРВЕР, мы только приходим
      // спросить.
      enterTimeUp();
    }
  }

  function syncFromServer(value) {
    if (timer.applyServer(value) === 'accepted') { paintTimer(); }
  }

  /** Время вышло по СЕРВЕРУ: страница сама уходит на сдачу.
   *
   * Раньше этого не было: истёкшая контрольная продолжала выглядеть живой,
   * пока ученик не нажмёт что-нибудь сам. Ученик писал в поле, которое
   * сервер уже не принимал. */
  function enterTimeUp() {
    if (timeUp) { return; }
    timeUp = true;
    paintTimer();
    if (stateNode) {
      stateNode.textContent = 'время вышло — работа сдаётся';
    }
    flushAll(true);
  }

  /** Лёгкий запрос «сколько осталось» — раз в 15 секунд, независимо от
   * того, печатает ученик или просто смотрит на таймер. */
  function pollTime() {
    if (timeUp || !config.timeUrl) { return; }
    fetch(config.timeUrl, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        offline = false;
        if (data.expired) { enterTimeUp(); return; }
        syncFromServer(data.seconds_remaining);
        paintState();
      })
      .catch(function () { /* сеть отвалилась — отсчёт идёт своими часами */ });
  }

  // ------------------------------------------------------------ индикатор
  function paintState() {
    if (!stateNode) { return; }
    stateNode.classList.toggle('is-offline', offline);
    stateNode.classList.toggle('is-saving', !offline && saving > 0);
    if (offline) {
      stateNode.textContent = 'нет связи — ответы сохранены на странице, '
        + 'пробуем отправить';
    } else if (saving > 0) {
      stateNode.textContent = 'сохраняем…';
    } else {
      stateNode.textContent = 'сохранено';
    }
  }

  // ----------------------------------------------------------- отправка
  // Читаем карточку ОБЩЕЙ меркой (`work_form.js`): иначе счётчик «без
  // ответа» в диалоге подтверждения и автосохранение начнут расходиться.
  function collect(itemId) {
    var card = document.getElementById('item-' + itemId);
    if (!card) { return null; }
    return window.WorkForm.readCard(card);
  }

  /* Поля карточки, каждое со своим адресом на сервере.
   *
   * ⚠️ У задачи с пунктами ответ СВОЙ НА КАЖДЫЙ ПУНКТ, и уезжают они
   * раздельно: склеить «а» и «б» в один черновик значит лишить
   * автопроверку возможности проверить их по отдельности. Задача без
   * пунктов — тот же код с одним полем без `part_id`. */
  function cardFields(itemId) {
    var card = document.getElementById('item-' + itemId);
    if (!card) { return []; }
    var fields = [];

    var checked = card.querySelectorAll(
      'input[type=radio], input[type=checkbox]');
    if (checked.length) {
      var chosen = Array.prototype.filter.call(checked, function (input) {
        return input.checked;
      }).map(function (input) { return input.value; }).join(', ');
      fields.push({ key: itemId + ':опции', body: { answer: chosen } });
    }

    card.querySelectorAll('input.answer-short').forEach(function (input) {
      var partId = input.dataset.part || '';
      var body = { answer: input.value.trim() };
      if (partId) { body.part_id = partId; }
      fields.push({ key: itemId + ':a' + partId, body: body });
    });

    var area = card.querySelector('textarea.answer-text');
    if (area) {
      fields.push({ key: itemId + ':решение',
                    body: { solution: area.value } });
    }
    return fields;
  }

  /* ⚠️ ОДИН ЗАПРОС В ПОЛЁТЕ НА ВСЮ СТРАНИЦУ.
   *
   * Раньше ограничение было «по одному запросу на задачу». После разбиения
   * ответа по пунктам запросов стало кратно больше (пункт + пункт +
   * решение), и параллельные записи упёрлись в блокировку SQLite: сервер
   * честно отвечал 503 «повтори», клиент честно повторял, но три ошибки
   * подряд посреди контрольной — не то, что должен видеть ученик.
   *
   * Очередь глобальная и «побеждает последний»: пока запрос в полёте,
   * новые значения того же поля просто вытесняют старые в очереди, а не
   * копятся. Ничего не теряется — уезжает всегда самое свежее.
   */
  var queue = {};          // ключ поля → {itemId, body}
  var order = [];          // порядок ключей
  var busy = false;

  function enqueue(itemId, field) {
    if (!(field.key in queue)) { order.push(field.key); }
    queue[field.key] = { itemId: itemId, body: field.body };
    pump();
  }

  function pump() {
    if (busy) { return; }
    var key = order.shift();
    while (key !== undefined && !(key in queue)) { key = order.shift(); }
    if (key === undefined) { return; }
    var task = queue[key];
    delete queue[key];
    busy = true;
    saving += 1;
    paintState();

    var body = { item_id: task.itemId };
    Object.keys(task.body).forEach(function (name) {
      body[name] = task.body[name];
    });

    fetch(config.autosaveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(body)
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .then(function (result) {
        saving -= 1;
        busy = false;
        offline = false;
        syncFromServer(result.data.seconds_remaining);
        if (result.status === 409 || result.data.expired) {
          enterTimeUp();
          return;
        }
        if (result.ok) {
          delete pending[task.itemId];
        } else if (result.data.retry) {
          // Сервер честно сказал «не сохранил» — возвращаем в очередь.
          // Выбрасывать значение нельзя ни при каких условиях.
          enqueue(task.itemId, { key: key, body: task.body });
          offline = true;
        }
        markAnswered(task.itemId, collect(task.itemId) || {});
        paintState();
        pump();
      })
      .catch(function () {
        saving -= 1;
        busy = false;
        offline = true;
        enqueue(task.itemId, { key: key, body: task.body });
        paintState();
      });
  }

  function send(itemId) {
    pending[itemId] = collect(itemId);
    cardFields(itemId).forEach(function (field) {
      enqueue(itemId, field);
    });
  }

  // Задача считается начатой по НАПИСАННОМУ, а не по отправленному —
  // то же правило, что у сервера (`assignment_rows.work_status`).
  function isAnswered(payload) {
    return Boolean((payload.answer || '').trim()
      || (payload.solution || '').trim());
  }

  function countUnanswered() {
    var empty = 0;
    (config.itemIds || []).forEach(function (itemId) {
      var payload = collect(itemId);
      if (!payload || !isAnswered(payload)) { empty += 1; }
    });
    return empty;
  }

  function markAnswered(itemId, payload) {
    var answered = isAnswered(payload);
    var link = document.querySelector('#qnav a[data-item="' + itemId + '"]');
    if (link) { link.classList.toggle('is-answered', answered); }

    var badge = document.querySelector(
      '[data-status-badge="' + itemId + '"]');
    if (badge && !badge.dataset.locked) {
      badge.textContent = answered ? 'В работе' : 'Не начата';
      badge.className = 'status-badge status-'
        + (answered ? 'in_progress' : 'not_started');
    }
    repaintAnsweredCount();
  }

  function repaintAnsweredCount() {
    var node = document.getElementById('answered-count');
    if (!node) { return; }
    var count = 0;
    (config.itemIds || []).forEach(function (itemId) {
      var payload = collect(itemId);
      if (payload && isAnswered(payload)) { count += 1; }
    });
    node.textContent = count;
  }

  function retryPending() {
    var ids = Object.keys(pending);
    if (!ids.length) { return; }
    ids.forEach(function (itemId) { send(parseInt(itemId, 10)); });
  }

  function flushAll(submit) {
    (config.itemIds || []).forEach(function (itemId) {
      pending[itemId] = collect(itemId) || { answer: '', solution: '' };
    });
    if (submit) {
      var form = document.getElementById('exam-form');
      if (form && !form.dataset.submitted) {
        form.dataset.submitted = '1';
        form.submit();
      }
    }
  }

  function schedule(itemId) {
    clearTimeout(timers[itemId]);
    // Две секунды после остановки ввода: чаще — лишние запросы на каждую
    // букву, реже — слишком много можно потерять при обрыве.
    timers[itemId] = setTimeout(function () { send(itemId); }, 2000);
  }

  // ------------------------------------------------------------ подключение
  document.addEventListener('DOMContentLoaded', function () {
    paintTimer();
    if (timer.hasLimit()) {
      setInterval(tick, 1000);
      // Сверка с сервером — по таймеру, а не по вводу. Пятнадцать секунд:
      // чаще незачем (расхождение внутри допуска), реже — ученик слишком
      // долго смотрел бы на неправду.
      setInterval(pollTime, 15000);
    }
    setInterval(retryPending, 10000);

    (config.itemIds || []).forEach(function (itemId) {
      var card = document.getElementById('item-' + itemId);
      if (!card) { return; }
      // Статус и счётчик красим СРАЗУ по вводу, не дожидаясь ответа
      // сервера: ученик написал ответ — задача уже «в работе», даже если
      // автосохранение ещё в полёте или сеть отвалилась.
      card.addEventListener('input', function () {
        markAnswered(itemId, collect(itemId) || {});
        schedule(itemId);
      });
      card.addEventListener('change', function () {
        markAnswered(itemId, collect(itemId) || {});
        send(itemId);
      });
      card.addEventListener('focusout', function () {
        clearTimeout(timers[itemId]);
        send(itemId);
      });
    });

    // Работу отправляет ТОЛЬКО кнопка. Enter в поле — перенос строки:
    // Shift+Return однажды сдал контрольную посреди работы.
    var form = document.getElementById('exam-form');
    if (form) { window.WorkForm.guardEnter(form); }

    var finish = document.getElementById('finish-btn');
    if (finish) {
      finish.addEventListener('click', function () {
        if (!window.WorkForm.confirmSubmit({
          unanswered: countUnanswered(),
          secondsLeft: timer.remaining(),
          warning: 'После завершения дописать будет нельзя, '
            + 'вернуться к работе не получится.',
          question: 'Завершить контрольную?'
        })) { return; }
        flushAll(true);
      });
    }

    window.addEventListener('online', function () {
      offline = false; paintState(); retryPending();
    });
    window.addEventListener('offline', function () {
      offline = true; paintState();
    });
  });
})();
