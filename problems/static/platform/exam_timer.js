/*
 * Часы контрольной — вынесены отдельным файлом, чтобы их можно было
 * проверить без браузера (node-харнесс в `problems/tests/test_exam_timer_js.py`).
 *
 * ⚠️ ГЛАВНОЕ ПРАВИЛО: ЗДЕСЬ НИКОГДА НЕ ВЫЗЫВАЕТСЯ `Date.now()`.
 * Ученик, переведя системные часы на десять минут назад, увидел на экране
 * ДЕСЯТЬ ЛИШНИХ МИНУТ. Отсчёт обязан идти по МОНОТОННЫМ часам —
 * `performance.now()` считает миллисекунды от загрузки страницы и не
 * реагирует ни на перевод системного времени, ни на смену часового пояса,
 * ни на переход на летнее время.
 *
 * ⚠️ ВТОРОЕ ПРАВИЛО: ОСТАТОК НИКОГДА НЕ РАСТЁТ. Серверная сверка может
 * только УМЕНЬШИТЬ показанное время. Законного случая, когда времени стало
 * больше, не существует; зато незаконных два — подкрученные часы устройства
 * и (при запуске сервера на той же машине) подкрученные часы сервера.
 * Поэтому прибавку мы отвергаем, а убавку принимаем молча.
 */
(function (root) {
  'use strict';

  // Насколько расходиться с сервером не страшно: пакет шёл по сети, пока
  // шёл — время текло. Меньше пяти секунд — обычная задержка, не повод
  // дёргать цифру на экране.
  var TOLERANCE = 5;

  function defaultClock() {
    if (typeof performance !== 'undefined' && performance
        && typeof performance.now === 'function') {
      return performance.now();
    }
    // Совсем старый браузер без performance. Date.now() тут ХУЖЕ, чем
    // ничего: именно его и подкручивают. Отдаём NaN — вызывающий увидит
    // «без ограничения» и будет полагаться только на сервер.
    return NaN;
  }

  /**
   * options.seconds — сколько осталось по серверу в момент создания
   *                   (null = без ограничения времени);
   * options.clock   — источник монотонных миллисекунд (для тестов).
   */
  function create(options) {
    options = options || {};
    var clock = options.clock || defaultClock;
    var granted = options.seconds;
    var anchorMono = clock();
    var anchorLeft = (granted === null || granted === undefined
                      || isNaN(granted)) ? null : Number(granted);

    function remaining() {
      if (anchorLeft === null) { return null; }
      var mono = clock();
      if (isNaN(mono) || isNaN(anchorMono)) { return anchorLeft; }
      return Math.max(0, anchorLeft - Math.floor((mono - anchorMono) / 1000));
    }

    /**
     * Сверка с сервером. Возвращает 'accepted' | 'ignored' | 'skipped'.
     * 'ignored' — сервер прислал БОЛЬШЕ, чем у нас: время не растёт.
     */
    function applyServer(value) {
      if (value === null || value === undefined || isNaN(value)) {
        return 'skipped';
      }
      value = Math.max(0, Math.floor(Number(value)));
      if (anchorLeft === null) {
        // Ограничения не было, а сервер прислал остаток — принимаем:
        // это не «время выросло», это появление лимита там, где его не
        // показывали.
        anchorLeft = value;
        anchorMono = clock();
        return 'accepted';
      }
      var mine = remaining();
      if (value > mine + TOLERANCE) { return 'ignored'; }
      if (Math.abs(value - mine) <= TOLERANCE) { return 'skipped'; }
      anchorLeft = value;
      anchorMono = clock();
      return 'accepted';
    }

    function expired() {
      var left = remaining();
      return left !== null && left <= 0;
    }

    function pad(value) { return value < 10 ? '0' + value : String(value); }

    function text() {
      var left = remaining();
      if (left === null) { return ''; }
      var hours = Math.floor(left / 3600);
      var minutes = Math.floor((left % 3600) / 60);
      var seconds = left % 60;
      return hours > 0
        ? hours + ':' + pad(minutes) + ':' + pad(seconds)
        : pad(minutes) + ':' + pad(seconds);
    }

    return {
      remaining: remaining,
      applyServer: applyServer,
      expired: expired,
      text: text,
      hasLimit: function () { return anchorLeft !== null; }
    };
  }

  root.ExamTimer = { create: create, TOLERANCE: TOLERANCE };
})(typeof window !== 'undefined' ? window : globalThis);
