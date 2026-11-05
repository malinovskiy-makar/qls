/* Числовая клавиатура ВП: только сенсорные устройства, без изменения правил ответа.
 * Поле остаётся обычным input: выделение, вставка и физическая клавиатура работают.
 * Каждое изменение отправляет input, поэтому используется прежнее автосохранение.
 */
(function () {
  'use strict';
  var panel = document.getElementById('vp-number-keypad');
  var fields = Array.prototype.slice.call(document.querySelectorAll('input.vp-input--number'));
  if (!panel || !fields.length || !window.matchMedia) return;
  var touch = window.matchMedia('(any-pointer: coarse)');
  var active = null;
  var start = 0;
  var end = 0;
  var frame = 0;
  var next = panel.querySelector('[data-number-key="next"]');

  function usable(field) {
    return field && field.isConnected && !field.disabled && !field.readOnly && field.getClientRects().length;
  }
  function remember() {
    if (!active) return;
    start = active.selectionStart;
    end = active.selectionEnd;
  }
  function close() {
    panel.hidden = true;
    document.body.classList.remove('vp-number-keypad-open');
    document.documentElement.style.removeProperty('--vp-number-keypad-height');
    active = null;
  }
  function revealField() {
    if (frame) window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(function () {
      frame = 0;
      if (!usable(active) || panel.hidden) return;
      var rect = active.getBoundingClientRect();
      var top = panel.getBoundingClientRect().top;
      var bar = document.getElementById('vp-bar') || document.querySelector('.site-nav');
      var ceiling = bar ? Math.max(0, bar.getBoundingClientRect().bottom) + 12 : 12;
      if (rect.bottom > top - 16) window.scrollBy(0, rect.bottom - top + 16);
      else if (rect.top < ceiling) window.scrollBy(0, rect.top - ceiling);
    });
  }
  function measure() {
    if (panel.hidden) return;
    document.documentElement.style.setProperty('--vp-number-keypad-height', panel.offsetHeight + 'px');
    revealField();
  }
  function open(field) {
    if (!touch.matches || !usable(field)) return;
    active = field;
    remember();
    // Пробник может находиться в нативном dialog: клавиатура тоже должна быть в верхнем слое.
    var host = field.closest('dialog') || document.body;
    if (panel.parentNode !== host) host.appendChild(panel);
    next.textContent = field.closest('[data-practice-form]') ? 'Проверить' : 'Далее →';
    panel.hidden = false;
    document.body.classList.add('vp-number-keypad-open');
    measure();
  }
  function configure() {
    fields.forEach(function (field) { field.inputMode = touch.matches ? 'none' : 'text'; });
    if (!touch.matches) close();
    else if (fields.indexOf(document.activeElement) !== -1) open(document.activeElement);
  }
  fields.forEach(function (field) {
    field.addEventListener('focus', function () { open(field); });
    field.addEventListener('click', function () { open(field); });
    field.addEventListener('select', remember);
    field.addEventListener('keyup', remember);
    field.addEventListener('input', remember);
  });
  document.addEventListener('selectionchange', function () {
    if (document.activeElement === active) remember();
  });
  document.addEventListener('focusin', function (event) {
    if (active && event.target !== active && !panel.contains(event.target)) close();
  });
  document.addEventListener('focusout', function () {
    window.setTimeout(function () {
      if (active && document.activeElement !== active && !panel.contains(document.activeElement)) close();
    }, 0);
  });
  document.addEventListener('pointerdown', function (event) {
    if (active && event.target !== active && !panel.contains(event.target)) close();
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && active) {
      var field = active;
      close();
      field.blur();
    }
  });
  // Нажатие клавиши не уводит фокус из ответа и не запускает проверку недописанного числа.
  // Не отменяем pointerdown: WebKit тогда подавляет click от касания.
  panel.addEventListener('mousedown', function (event) {
    if (event.target.closest('button')) event.preventDefault();
  });
  panel.addEventListener('click', function (event) {
    var button = event.target.closest('[data-number-key]');
    if (!button || !usable(active)) { close(); return; }
    var field = active;
    var key = button.dataset.numberKey;
    if (key === 'hide') { close(); field.blur(); return; }
    if (key === 'next') {
      field.dispatchEvent(new CustomEvent('vp-number-next', { bubbles: true }));
      // Последнее задание или проверка дорешивания: Enter не сдаёт всю работу.
      if (document.activeElement === field || panel.contains(document.activeElement)) {
        close(); field.blur();
      }
      return;
    }
    if (document.activeElement === field) remember();
    var from = start;
    var to = end;
    var insert = key === 'delete' ? '' : key;
    if (key === 'delete' && from === to) from = Math.max(0, from - 1);
    if (field.maxLength >= 0 && field.value.length - (to - from) + insert.length > field.maxLength) return;
    field.setRangeText(insert, from, to, 'end');
    start = end = from + insert.length;
    field.focus({ preventScroll: true });
    field.setSelectionRange(start, end);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
  window.addEventListener('resize', measure);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', measure);
  if (touch.addEventListener) touch.addEventListener('change', configure);
  else touch.addListener(configure);
  configure();
})();
