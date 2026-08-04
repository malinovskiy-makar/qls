/*
 * Контрольная в браузере: таймер и автосохранение.
 *
 * ⚠️ КЛИЕНТ НЕ ИСТОЧНИК ПРАВДЫ О ВРЕМЕНИ. Он рисует обратный отсчёт, но
 * каждый ответ сервера несёт `seconds_remaining`, и по нему отсчёт молча
 * пересинхронизируется. Перевод часов на устройстве не меняет ничего:
 * мы считаем не от `Date.now()` абсолютным временем, а тикаем на единицу
 * раз в секунду и правимся по серверу. Даже если сбить системное время —
 * счётчик не сдвинется, а конец забега объявит сервер.
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
  var secondsLeft = timerNode && timerNode.dataset.seconds !== ''
    ? parseInt(timerNode.dataset.seconds, 10) : null;

  function pad(value) { return value < 10 ? '0' + value : String(value); }

  function paintTimer() {
    if (!timerNode || secondsLeft === null || isNaN(secondsLeft)) { return; }
    var left = Math.max(0, secondsLeft);
    var hours = Math.floor(left / 3600);
    var minutes = Math.floor((left % 3600) / 60);
    var seconds = left % 60;
    timerNode.textContent = hours > 0
      ? hours + ':' + pad(minutes) + ':' + pad(seconds)
      : pad(minutes) + ':' + pad(seconds);
    // Предупреждающий цвет за 5 минут, тревожный за 1. Без звуков.
    timerNode.classList.toggle('warn', left <= 300 && left > 60);
    timerNode.classList.toggle('danger', left <= 60);
  }

  function tick() {
    if (secondsLeft === null || isNaN(secondsLeft)) { return; }
    secondsLeft -= 1;
    paintTimer();
    if (secondsLeft <= 0) {
      // Время кончилось по нашему счёту. Отправляем форму — решение
      // «действительно ли вышло» принимает СЕРВЕР, мы только приходим
      // спросить.
      flushAll(true);
    }
  }

  function syncFromServer(value) {
    if (value === null || value === undefined) { return; }
    if (secondsLeft === null || Math.abs(secondsLeft - value) > 5) {
      // Расхождение больше пяти секунд — молча поправляем. Молча потому,
      // что ученику незачем знать про сетевые задержки посреди работы.
      secondsLeft = value;
      paintTimer();
    }
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
  function collect(itemId) {
    var card = document.getElementById('item-' + itemId);
    if (!card) { return null; }
    var answer = '';
    var checked = card.querySelectorAll(
      'input[type=radio]:checked, input[type=checkbox]:checked');
    if (checked.length) {
      answer = Array.prototype.map.call(checked, function (input) {
        return input.value;
      }).join(', ');
    } else {
      var text = card.querySelector('input.answer-short');
      answer = text ? text.value.trim() : '';
    }
    var area = card.querySelector('textarea.answer-text');
    return { answer: answer, solution: area ? area.value : '' };
  }

  // По одной задаче — не больше ОДНОГО запроса в полёте. Второй не
  // отменяется, а откладывается: когда первый вернётся, уйдёт свежее
  // значение. Иначе два сохранения одной задачи стартуют одновременно и
  // дерутся за одну строку черновика (сервер к этому готов, но лишний
  // запрос — лишний шанс потерять его в плохой сети).
  var inFlight = {};

  function send(itemId) {
    var payload = collect(itemId);
    if (!payload) { return; }
    pending[itemId] = payload;
    if (inFlight[itemId]) { inFlight[itemId] = 'again'; return; }
    inFlight[itemId] = true;
    saving += 1;
    paintState();

    fetch(config.autosaveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({
        item_id: itemId, answer: payload.answer, solution: payload.solution
      })
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .then(function (result) {
        saving -= 1;
        var again = inFlight[itemId] === 'again';
        inFlight[itemId] = false;
        offline = false;
        syncFromServer(result.data.seconds_remaining);
        if (result.status === 409 || result.data.expired) {
          // Сервер сказал «время вышло» — уходим на результат через сдачу.
          flushAll(true);
          return;
        }
        if (result.ok) {
          delete pending[itemId];
        } else if (result.data.retry) {
          // Сервер честно сказал «не сохранил». Значение остаётся в очереди
          // и уедет повтором — выбрасывать его нельзя ни при каких условиях.
          offline = true;
        }
        markAnswered(itemId, payload);
        paintState();
        if (again) { send(itemId); }   // пока ждали, ученик дописал
      })
      .catch(function () {
        saving -= 1;
        inFlight[itemId] = false;
        offline = true;        // накопленное остаётся в `pending`
        paintState();
      });
  }

  function markAnswered(itemId, payload) {
    var link = document.querySelector('#qnav a[data-item="' + itemId + '"]');
    if (link) {
      link.classList.toggle('is-answered',
        Boolean(payload.answer || (payload.solution || '').trim()));
    }
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
    if (secondsLeft !== null && !isNaN(secondsLeft)) {
      setInterval(tick, 1000);
    }
    setInterval(retryPending, 10000);

    (config.itemIds || []).forEach(function (itemId) {
      var card = document.getElementById('item-' + itemId);
      if (!card) { return; }
      card.addEventListener('input', function () { schedule(itemId); });
      card.addEventListener('change', function () { send(itemId); });
      card.addEventListener('focusout', function () {
        clearTimeout(timers[itemId]);
        send(itemId);
      });
    });

    var finish = document.getElementById('finish-btn');
    if (finish) {
      finish.addEventListener('click', function () {
        var empty = 0;
        (config.itemIds || []).forEach(function (itemId) {
          var payload = collect(itemId);
          if (!payload || (!payload.answer && !(payload.solution || '').trim())) {
            empty += 1;
          }
        });
        var message = empty
          ? 'Без ответа осталось задач: ' + empty + '. Завершить работу?'
          : 'Завершить работу? Дописать будет нельзя.';
        if (window.confirm(message)) { flushAll(true); }
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
