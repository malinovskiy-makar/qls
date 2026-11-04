/* Посадочная ВП: окно «Правила и формат».
 *
 * ⚠️ СОДЕРЖИМОЕ ОКНА УЖЕ В HTML — скрипт его только показывает. Без JS правила
 * всё равно доедут до поисковика и до читалки, просто не будут складываться в окно.
 *
 * Адрес `/vp/#rules` открывает окно сразу: с экрана выбора варианта на правила
 * ведёт обычная ссылка, а не кнопка.
 */
/* Один выбранный класс на формат, таблицу и «моё». Ссылки работают и без JS. */
(function () {
  'use strict';
  var select = document.getElementById('vp-format-band');
  if (!select) return;
  document.getElementById('vp-format-apply').hidden = true;
  select.addEventListener('change', function () { select.form.requestSubmit(); });
})();

(function () {
  'use strict';

  var dialog = document.getElementById('vp-rules');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  var cont = document.getElementById('vp-rules-cont');
  var navButtons = Array.prototype.slice.call(dialog.querySelectorAll('.vp-rules-nav button'));
  var opener = null;

  function open(from) {
    opener = from || null;
    if (!dialog.open) dialog.showModal();
  }

  document.querySelectorAll('[data-open-rules]').forEach(function (button) {
    button.addEventListener('click', function () { open(button); });
  });

  /* Крестик и клик по подложке. Esc `<dialog>` обрабатывает сам. */
  dialog.addEventListener('click', function (event) {
    if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
  });

  dialog.addEventListener('close', function () {
    if (opener) opener.focus();
  });

  /* Навигация по разделам: подсветка активного и прокрутка содержимого к нему. */
  navButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      var section = document.getElementById(button.getAttribute('data-sec'));
      if (!section || !cont) return;
      navButtons.forEach(function (other) { other.classList.toggle('is-on', other === button); });
      cont.scrollTo({ top: section.offsetTop - cont.offsetTop, behavior: 'smooth' });
    });
  });

  /* Активный раздел следует за прокруткой: иначе подсветка врёт. */
  if (cont) {
    cont.addEventListener('scroll', function () {
      var edge = cont.scrollTop + cont.offsetTop + 24;
      var current = navButtons[0];
      navButtons.forEach(function (button) {
        var section = document.getElementById(button.getAttribute('data-sec'));
        if (section && section.offsetTop <= edge) current = button;
      });
      navButtons.forEach(function (other) { other.classList.toggle('is-on', other === current); });
    });
  }

  if (window.location.hash === '#rules') open(null);
})();

/* Проверка записи использует существующий серверный endpoint, без копии правил. */
(function () {
  'use strict';
  var dialog = document.getElementById('vp-probe-dialog');
  var button = document.querySelector('[data-open-probe]');
  if (!dialog || !button || !window.fetch || typeof dialog.showModal !== 'function') return;
  button.addEventListener('click', function (event) { event.preventDefault(); dialog.showModal(); });
  dialog.querySelector('[data-close-probe]').addEventListener('click', function () { dialog.close(); });
  dialog.addEventListener('click', function (event) {
    if (event.target !== dialog) return;
    var rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  var help = document.getElementById('vp-probe-help');
  var tip = document.getElementById('vp-probe-tip');
  function showHelp(open) { tip.hidden = !open; help.setAttribute('aria-expanded', String(open)); }
  help.addEventListener('click', function (event) {
    showHelp(event.pointerType === 'touch' ? tip.hidden : true);
  });
  help.addEventListener('focus', function () { if (help.matches(':focus-visible')) showHelp(true); });
  help.addEventListener('blur', function () { showHelp(false); });
  help.parentElement.addEventListener('pointerenter', function (event) { if (event.pointerType === 'mouse') showHelp(true); });
  help.parentElement.addEventListener('pointerleave', function (event) { if (event.pointerType === 'mouse') showHelp(false); });
  dialog.addEventListener('pointerdown', function (event) { if (!help.parentElement.contains(event.target)) showHelp(false); });
  dialog.addEventListener('cancel', function (event) { if (!tip.hidden) { event.preventDefault(); showHelp(false); } });
  dialog.addEventListener('close', function () { showHelp(false); button.focus(); });
  var box = document.getElementById('vp-probe');
  var input = document.getElementById('vp-probe-in');
  var out = document.getElementById('vp-probe-out');
  var timer, asked = 0;
  function check() {
    var mine = ++asked;
    box.classList.remove('is-ok', 'is-bad');
    if (!input.value.trim()) { out.textContent = ''; return; }
    fetch(box.dataset.checkUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': box.dataset.csrf },
      body: JSON.stringify({ raw: input.value })
    }).then(function (response) {
      if (!response.ok) throw new Error('format check failed');
      return response.json();
    }).then(function (data) {
      if (mine !== asked) return;
      out.textContent = data.text || '';
      box.classList.toggle('is-ok', !!data.ok);
      box.classList.toggle('is-bad', !data.ok && data.reason !== 'empty');
    }).catch(function () {
      if (mine === asked) out.textContent = 'Не удалось проверить. Попробуйте ещё раз.';
    });
  }
  input.addEventListener('input', function () {
    window.clearTimeout(timer); ++asked;
    out.textContent = ''; box.classList.remove('is-ok', 'is-bad');
    timer = window.setTimeout(check, 300);
  });
  box.querySelectorAll('[data-probe]').forEach(function (sample) {
    sample.addEventListener('click', function () {
      window.clearTimeout(timer); input.value = sample.dataset.probe; check(); input.focus();
    });
  });
})();
