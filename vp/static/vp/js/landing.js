/* Посадочная ВП: окно «Правила и формат».
 *
 * ⚠️ СОДЕРЖИМОЕ ОКНА УЖЕ В HTML — скрипт его только показывает. Без JS правила
 * всё равно доедут до поисковика и до читалки, просто не будут складываться в окно.
 *
 * Адрес `/vp/#rules` открывает окно сразу: с экрана выбора варианта на правила
 * ведёт обычная ссылка, а не кнопка.
 */
(function () {
  'use strict';

  /* Вкладки таблицы лучших попыток по классам (2 тур). Это ссылки `?board=`: без
     скрипта страница перезагрузится с нужной таблицей, со скриптом — переключит на месте. */
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-board-tab]'));
  var tablist = document.querySelector('[data-band-url]');
  /* `?board=` до сервера не доходит — выбор класса сообщаем ему сами (он запомнит его
     для экрана вариантов и «что дальше»). Ответа не ждём. */
  function remember(band) {
    if (!tablist || !window.fetch) return;
    try {
      fetch(tablist.getAttribute('data-band-url'), {
        method: 'POST', credentials: 'same-origin', body: band,
        headers: { 'X-CSRFToken': tablist.getAttribute('data-csrf') || '',
                   'Content-Type': 'text/plain;charset=UTF-8' }
      }).catch(function () { /* не запомнили — не беда */ });
    } catch (error) { /* старый браузер */ }
  }
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function (event) {
      event.preventDefault();
      var band = tab.getAttribute('data-board-tab');
      remember(band);
      tabs.forEach(function (other) {
        other.setAttribute('aria-selected', other === tab ? 'true' : 'false');
      });
      document.querySelectorAll('[data-board-panel]').forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-board-panel') !== band;
      });
    });
  });
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

/* Пробник записи ответа: засчитают ли такую запись на туре. Проверяет сервер (`format/check/`,
   тот же код, что считает баллы), не чаще раза в 300 мс после паузы ввода; ответ — текстом.
   Без скрипта блока нет (`hidden`). */
(function () {
  'use strict';

  var box = document.getElementById('vp-probe');
  if (!box || !window.fetch) return;
  box.hidden = false;
  var input = document.getElementById('vp-probe-in');
  var out = document.getElementById('vp-probe-out');
  var url = box.getAttribute('data-check-url');
  var csrf = box.getAttribute('data-csrf') || '';
  var timer = null;
  var asked = 0;

  function check() {
    var raw = input.value;
    var mine = ++asked;
    fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ raw: raw })
    }).then(function (response) { return response.json(); }).then(function (data) {
      if (mine !== asked) return;                 // пришёл ответ на устаревшую запись
      out.textContent = data.text || '';
      box.classList.toggle('is-ok', !!data.ok);
      box.classList.toggle('is-bad', !data.ok && data.reason !== 'empty');
    }).catch(function () { out.textContent = 'Нет связи.'; });
  }

  input.addEventListener('input', function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(check, 300);
  });
  Array.prototype.forEach.call(box.querySelectorAll('[data-probe]'), function (button) {
    button.addEventListener('click', function () {
      input.value = button.getAttribute('data-probe');
      window.clearTimeout(timer);
      check();
      input.focus();
    });
  });
})();
