/* «Стол» на странице задачи (часть B ночи 18.09.2026, первый шаг).

   Панели: лента слева и помощь справа сворачиваются в полоски 52 px;
   первое открытие — лента свёрнута, помощь открыта (решение владельца
   17.09), дальше состояние запоминается в localStorage за браузером.
   «Фокус» (F) убирает обе панели и шапку, Esc выходит. Клавиши [ и ]
   — лента и помощь, J/K и стрелки ходят по ленте, Enter открывает.
   Клавиши молчат, пока курсор в поле ввода.

   Вкладка «Мои» догружает строки с сервера (`/catalog/api/rail/saved/`),
   «Похожие» нарисованы сервером. «Как прошло?» пишет прогресс
   (`/catalog/api/progress/<id>/`, ADR 0119). Одно пространство имён —
   `weco.stol`. */
(function () {
  window.weco = window.weco || {};
  var root = document.getElementById('stol');
  if (!root || weco.stol) return;

  var KEY = 'weco_stol';
  var cfgEl = document.getElementById('pd-config');
  var cfg = {};
  try { cfg = JSON.parse((cfgEl && cfgEl.textContent) || '{}'); } catch (e) { cfg = {}; }
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; }
  }
  function save(state) {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* приватное окно */ }
  }
  var state = load() || { rail: false, help: true };

  function paint() {
    root.setAttribute('data-rail', state.rail ? 'open' : 'closed');
    root.setAttribute('data-help', state.help ? 'open' : 'closed');
  }
  function toggle(panel) {
    // Из «Фокуса» кнопка панели её открывает, а не переключает вслепую.
    if (document.body.classList.contains('stol-is-focus')) {
      focus(false);
      state[panel] = true;
    } else {
      state[panel] = !state[panel];
    }
    save(state);
    paint();
  }
  function focus(on) {
    document.body.classList.toggle('stol-is-focus', on);
    root.querySelectorAll('.stol-focus-label').forEach(function (el) {
      el.textContent = on ? 'Выйти из фокуса' : 'Фокус';
    });
  }

  root.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-stol]');
    if (!btn) return;
    var what = btn.getAttribute('data-stol');
    if (what === 'focus') { focus(!document.body.classList.contains('stol-is-focus')); } else { toggle(what); }
  });

  /* ── Лента: вкладки и ход по строкам ────────────────────────────────── */
  var list = document.getElementById('stol-rail-list');
  var similarHtml = list ? list.innerHTML : '';
  var savedHtml = null;
  root.querySelectorAll('[data-rail-tab]').forEach(function (tab) {
    tab.addEventListener('click', function () {
      root.querySelectorAll('[data-rail-tab]').forEach(function (t) {
        t.classList.toggle('is-on', t === tab);
        t.setAttribute('aria-selected', t === tab ? 'true' : 'false');
      });
      if (tab.getAttribute('data-rail-tab') === 'similar') { list.innerHTML = similarHtml; return; }
      if (savedHtml !== null) { list.innerHTML = savedHtml; return; }
      /* Строки рисует сервер тем же партиалом (экранированный шаблон), не сырые данные. */
      fetch(cfg.railSavedUrl, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          savedHtml = d.rows_html || '<p class="rail-empty">Сохранённых задач пока нет.</p>';
          list.innerHTML = savedHtml;
        })
        .catch(function () { /* вкладка остаётся прежней */ });
    });
  });
  var cursor = -1;
  function rows() { return list ? Array.prototype.slice.call(list.querySelectorAll('.rail-row')) : []; }
  function move(step) {
    var all = rows();
    if (!all.length) return;
    if (!state.rail) { state.rail = true; save(state); paint(); }
    cursor = Math.max(0, Math.min(all.length - 1, cursor + step));
    all.forEach(function (row, i) { row.classList.toggle('is-cursor', i === cursor); });
    all[cursor].scrollIntoView({ block: 'nearest' });
  }

  document.addEventListener('keydown', function (e) {
    var t = e.target;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    if (document.querySelector('[aria-modal="true"]:not([hidden]), .fb-back')) return;
    var k = e.key;
    if (k === '[') { toggle('rail'); } else if (k === ']') { toggle('help'); }
    else if (k === 'f' || k === 'F' || k === 'а' || k === 'А') { focus(!document.body.classList.contains('stol-is-focus')); }
    else if (k === 'Escape' && document.body.classList.contains('stol-is-focus')) { focus(false); }
    else if (k === 'j' || k === 'ArrowDown') { move(1); }
    else if (k === 'k' || k === 'ArrowUp') { move(-1); }
    else if (k === 'Enter' && cursor >= 0 && rows()[cursor]) { location.href = rows()[cursor].href; }
    else { return; }
    e.preventDefault();
  });

  /* ── «Как прошло?» и следы помощи ───────────────────────────────────── */
  function progress(payload) {
    if (!cfg.progressUrl) return Promise.resolve(null);
    return fetch(cfg.progressUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); });
  }
  var how = document.getElementById('how');
  if (how) {
    how.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-how]');
      if (!btn || btn.disabled) return;
      var again = btn.getAttribute('aria-pressed') === 'true';
      progress({ status: again ? null : btn.getAttribute('data-how') }).then(function (d) {
        if (!d || d.error) return;
        how.querySelectorAll('[data-how]').forEach(function (b) {
          b.setAttribute('aria-pressed', !again && b === btn ? 'true' : 'false');
        });
      });
    });
  }
  document.addEventListener('weco:solution-viewed', function () {
    progress({ solution_viewed: true });
    var self = how && how.querySelector('[data-how="self"]');
    if (self) { self.disabled = true; self.title = 'Решение уже открыто'; }
  });

  paint();
  weco.stol = { toggle: toggle, focus: focus };
})();
