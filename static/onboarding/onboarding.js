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
