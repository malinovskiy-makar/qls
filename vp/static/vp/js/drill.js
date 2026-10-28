/* «Тренировка записи ответа»: проверка записи на лету.
 *
 * Запись уходит на `format/check/` (тот же код, что считает баллы) по Enter или при уходе из
 * поля — не на каждую букву. Ответ сервера вставляется как ТЕКСТ. Когда проверены все 12 —
 * итог, типы ошибок и событие `vp_drill_done`. Без скрипта работает форма «Проверить все».
 */
(function () {
  'use strict';

  var form = document.getElementById('vp-drill');
  if (!form || !window.fetch) return;
  form.classList.add('is-js');
  var url = form.getAttribute('data-check-url');
  var csrfField = form.querySelector('input[name=csrfmiddlewaretoken]');
  var csrf = csrfField ? csrfField.value : '';
  var rows = Array.prototype.slice.call(form.querySelectorAll('.vp-drill-row[data-i]'));
  var total = rows.length;
  var results = {};          // i → {ok, reason, raw}
  var LABELS = {
    dot: 'точка вместо запятой', space: 'пробел внутри числа', units: 'лишние знаки или единицы',
    minus: 'длинный минус «−»', decimals: 'больше двух знаков после запятой',
    other: 'не по правилам', wrong: 'запись верная, но число другое'
  };
  var done = false;

  function paintCount() {
    var ok = Object.keys(results).filter(function (i) { return results[i].ok; }).length;
    document.getElementById('vp-drill-ok').textContent = ok;
    document.getElementById('vp-drill-bar').style.width = Math.round(ok / total * 100) + '%';
    var checked = Object.keys(results).length;
    if (checked < total) return;
    var final = document.getElementById('vp-drill-final');
    document.getElementById('vp-drill-final-ok').textContent = ok;
    var kinds = [];
    Object.keys(results).forEach(function (i) {
      var label = LABELS[results[i].reason];
      if (!results[i].ok && label && kinds.indexOf(label) === -1) kinds.push(label);
    });
    document.getElementById('vp-drill-final-why').textContent = kinds.length
      ? 'Ошибки по типам: ' + kinds.join(', ') + '.' : 'Все записи – по правилам ВШЭ.';
    final.hidden = false;
    if (!done && window.weco && window.weco.track) {
      done = true;
      window.weco.track('vp_drill_done', { ok: ok, total: total });
    }
  }

  function check(row) {
    var i = Number(row.getAttribute('data-i'));
    var field = row.querySelector('input[type=text]');
    var raw = field.value;
    if (!raw.trim()) return;
    if (results[i] && results[i].raw === raw) return;
    var out = row.querySelector('.vp-drill-out');
    fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ i: i, raw: raw })
    }).then(function (response) { return response.json(); }).then(function (data) {
      if (field.value !== raw) return;              // пока шёл ответ, запись поменяли
      out.textContent = data.text || '';
      row.classList.toggle('is-ok', !!data.ok);
      row.classList.toggle('is-bad', !data.ok);
      results[i] = { ok: !!data.ok, reason: data.reason, raw: raw };
      paintCount();
    }).catch(function () { out.textContent = 'Нет связи. Попробуйте ещё раз.'; });
  }

  rows.forEach(function (row, index) {
    var field = row.querySelector('input[type=text]');
    field.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' || event.isComposing) return;
      event.preventDefault();
      check(row);
      var next = rows[index + 1];
      if (next) next.querySelector('input[type=text]').focus();
    });
    field.addEventListener('change', function () { check(row); });
    field.addEventListener('blur', function () { check(row); });
  });

  /* «±» на сенсорных экранах: в цифровой клавиатуре iPhone нет минуса. */
  form.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('[data-pm-drill]') : null;
    if (!button) return;
    var field = document.getElementById('vp-drill-' + button.getAttribute('data-pm-drill'));
    if (!field) return;
    field.value = /^[-−‒–—﹣－]/.test(field.value)
      ? field.value.slice(1) : '-' + field.value;
    field.focus();
  });
})();
