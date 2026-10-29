/* Вход и регистрация (раунд 2): глаз у пароля и шесть ячеек кода из письма.
   Всё — поверх обычной формы: без скрипта поле пароля и поле кода работают сами. */
(function () {
  'use strict';

  // Глаз «показать пароль»: переключает тип поля и подпись для диктора.
  document.querySelectorAll('[data-pw-eye]').forEach(function (eye) {
    var input = eye.parentNode.querySelector('input');
    if (!input) return;
    eye.hidden = false;
    eye.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      eye.setAttribute('aria-pressed', show ? 'true' : 'false');
      eye.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
      input.focus();
    });
  });

  // Код из письма: настоящее поле `code` прячется, вместо него — N ячеек.
  // Вставка всего кода заполняет все ячейки; после последней цифры форма уходит сама.
  document.querySelectorAll('input[data-code-cells]').forEach(function (field) {
    var count = parseInt(field.getAttribute('data-code-cells'), 10) || 6;
    var form = field.form;
    var row = document.createElement('div');
    row.className = 'au-cells';
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'Код из письма');
    var cells = [];
    for (var i = 0; i < count; i++) {
      var cell = document.createElement('input');
      cell.className = 'au-cell ym-disable-keys';
      cell.type = 'text';
      cell.inputMode = 'numeric';
      cell.maxLength = 1;
      cell.autocomplete = i === 0 ? 'one-time-code' : 'off';
      cell.setAttribute('aria-label', 'Цифра ' + (i + 1) + ' из ' + count);
      cells.push(cell);
      row.appendChild(cell);
    }
    field.type = 'hidden';
    field.removeAttribute('autofocus');
    field.parentNode.insertBefore(row, field);

    var sent = false;
    function sync() {
      var code = cells.map(function (c) { return c.value; }).join('');
      field.value = code;
      cells.forEach(function (c) { c.classList.toggle('is-filled', !!c.value); });
      if (code.length === count && /^\d+$/.test(code) && !sent) {
        sent = true;
        form.requestSubmit ? form.requestSubmit() : form.submit();
      }
    }
    function fill(from, digits) {
      for (var k = 0; k < digits.length && from + k < count; k++) cells[from + k].value = digits[k];
      var next = Math.min(from + digits.length, count - 1);
      cells[next].focus();
      sync();
    }
    cells.forEach(function (cell, index) {
      cell.addEventListener('input', function () {
        var digits = cell.value.replace(/\D/g, '');
        cell.value = '';
        if (digits) fill(index, digits.split('')); else sync();
      });
      cell.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && !cell.value && index > 0) {
          cells[index - 1].value = '';
          cells[index - 1].focus();
          sync();
          e.preventDefault();
        } else if (e.key === 'ArrowLeft' && index > 0) {
          cells[index - 1].focus();
        } else if (e.key === 'ArrowRight' && index < count - 1) {
          cells[index + 1].focus();
        }
      });
      cell.addEventListener('paste', function (e) {
        var text = (e.clipboardData || window.clipboardData).getData('text') || '';
        var digits = text.replace(/\D/g, '').slice(0, count);
        if (!digits) return;
        e.preventDefault();
        fill(0, digits.split(''));
      });
      cell.addEventListener('focus', function () { cell.select(); });
    });
    cells[0].focus();
  });
})();

/* Онбординг /welcome/: отметки выбора и кнопка «Дальше».
   Без скрипта всё работает: выбор — настоящие radio/checkbox внутри <label>,
   незаполненный шаг сервер вернёт с ошибкой у поля. Скрипт только переключает
   aria-pressed / классы и держит «Дальше» неактивной, пока шаг не заполнен. */
(function () {
  'use strict';

  function sync(form) {
    form.querySelectorAll('label[aria-pressed]').forEach(function (label) {
      var input = label.querySelector('input');
      if (!input) return;
      var on = input.checked;
      label.setAttribute('aria-pressed', on ? 'true' : 'false');
      label.classList.toggle('k-tile--on', on && label.classList.contains('k-tile'));
      label.classList.toggle('is-on', on && !label.classList.contains('k-tile'));
    });
  }

  function complete(form) {
    var groups = form.querySelectorAll('[data-ob-need]');
    for (var i = 0; i < groups.length; i++) {
      if (!groups[i].querySelector('input:checked')) return false;
    }
    var fields = form.querySelectorAll('input[required]');
    for (var j = 0; j < fields.length; j++) {
      if (!fields[j].value.trim()) return false;
    }
    return true;
  }

  document.querySelectorAll('[data-ob-form]').forEach(function (form) {
    var next = document.querySelector('[data-ob-next][form="' + form.id + '"]');
    function update() {
      sync(form);
      if (next) next.disabled = !complete(form);
    }
    form.addEventListener('change', update);
    form.addEventListener('input', update);
    update();
  });

  // «Скопировать» код приглашения.
  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var source = document.querySelector('[data-copy-src]');
      if (!source || !navigator.clipboard) return;
      navigator.clipboard.writeText(source.textContent.trim()).then(function () {
        button.setAttribute('data-copied', '1');
      });
    });
  });
})();
