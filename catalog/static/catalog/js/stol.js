/* «Стол» — один экран на каталог, задачу и карту тем (решения владельца
   17–18.09.2026, README `claude/mockups/catalog_stol_20260917/README.md`).
   Одно пространство имён — `weco.stol`. Фильтры — одно состояние
   `weco.filters` (catalog_filters.js): чипы входа, окно «Все фильтры» и
   поиск пишут в него и перерисовываются по событию `weco:filters`.
   Без скрипта экран рабочий: поиск — GET-форма, строки — ссылки. */

/* ── Вход (вид `entry`): поиск, чипы, лента, карта-фон ────────────────── */
(function () {
  'use strict';
  window.weco = window.weco || {};
  weco.stol = weco.stol || {};
  var entry = document.getElementById('stol-entry');
  if (!entry) return;

  var form = document.getElementById('ct-ask-form');
  var field = document.getElementById('ct-q');
  var clearBtn = document.getElementById('ask-clear');
  var quiet = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var F = weco.filters;               /* нет его — остаёмся на серверных ссылках */
  var stateUrl = F ? JSON.parse(document.getElementById('ct-filter-state').textContent).urls.state : '';

  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function results() { return document.getElementById('ct-results'); }

  /* ── Поле запроса ──────────────────────────────────────────────────
     Крестик виден при тексте; поле растёт под введённый текст, пустое —
     возвращается к высоте из CSS (scrollHeight пустого поля считает и
     перенесённый placeholder — меряем только при тексте). */
  function syncField() {
    var text = field.value.trim();
    form.classList.toggle('has-text', text.length > 0);
    field.style.height = '';
    if (text) { field.style.height = Math.max(88, field.scrollHeight) + 'px'; }
  }
  field.addEventListener('input', syncField);
  field.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  if (clearBtn) clearBtn.addEventListener('click', function () { field.value = ''; syncField(); field.focus(); });

  /* Фразы ожидания: первая всегда первая, остальные в новом порядке на
     каждый запрос, смена раз в 1,6 с (решение 15.09.2026). */
  var busyText = document.getElementById('ask-busy-text');
  var phrasesNode = document.getElementById('search-busy-phrases');
  var busyPhrases = phrasesNode ? JSON.parse(phrasesNode.textContent) : [];
  var busyTimer = null;
  function busy(on) {
    form.classList.toggle('is-busy', on);
    clearInterval(busyTimer); busyTimer = null;
    if (!on || !busyText || busyPhrases.length < 2 || quiet) return;
    var rest = busyPhrases.slice(1);
    for (var i = rest.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)); var t = rest[i]; rest[i] = rest[j]; rest[j] = t;
    }
    var order = busyPhrases.slice(0, 1).concat(rest), n = 0;
    busyText.textContent = order[0];
    busyTimer = setInterval(function () {
      busyText.classList.add('is-fading');
      setTimeout(function () {
        n = (n + 1) % order.length; busyText.textContent = order[n]; busyText.classList.remove('is-fading');
      }, 160);
    }, 1600);
  }
  /* Поиск без перезагрузки: тот же ответ `api_filter_state`, что у фильтров,
     с `log=1` — строка журнала поиска (ADR 0117). */
  form.addEventListener('submit', function (e) {
    if (!F) { if (field.value.trim()) busy(true); return; }
    e.preventDefault();
    var text = field.value.trim();
    if (text && text === F.state.q) return;
    F.state.q = text;
    if (text) busy(true);
    F.refresh({ log: !!text });
  });

  /* ── Выпадашки чипов: одна открыта, клик мимо и Esc закрывают ─────── */
  function closeAll(except) {
    qa('[data-dd]').forEach(function (btn) {
      if (btn === except) return;
      btn.setAttribute('aria-expanded', 'false');
      var dd = document.getElementById(btn.getAttribute('aria-controls'));
      if (dd) dd.hidden = true;
    });
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-dd]');
    if (btn) {
      var open = btn.getAttribute('aria-expanded') !== 'true';
      closeAll(btn);
      btn.setAttribute('aria-expanded', String(open));
      document.getElementById(btn.getAttribute('aria-controls')).hidden = !open;
      return;
    }
    if (e.target.closest('[data-dd-close]')) { closeAll(); return; }
    if (!e.target.closest('.se-dd')) closeAll();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAll(); });

  var sol = document.getElementById('se-sol');
  if (sol && F) sol.addEventListener('click', function () {
    F.state.has_solution = !F.state.has_solution;
    F.refresh();
  });

  /* ── Подписи активных чипов: «Олигополия и…», «Темы · 2», «4★ 5★», «Тесты» ── */
  function labelOf(sel) { var el = document.querySelector(sel + ' .se-opt-l'); return el ? el.textContent.trim() : ''; }
  function setChip(key, text, on) {
    var l = document.querySelector('[data-chip-label="' + key + '"]');
    if (!l) return;
    l.textContent = text;
    l.closest('.se-chip').classList.toggle('is-on', on);
  }
  function paintChips(s) {
    var topics = Array.from(s.topics);
    var one = topics.length === 1 ? labelOf('.se-opt[data-topic="' + topics[0] + '"]') : '';
    setChip('topic', one || (topics.length ? 'Темы · ' + topics.length : 'Тема'), topics.length > 0);
    var levels = Array.from(s.difficulties).map(Number).sort();
    setChip('difficulty', levels.length ? levels.map(function (d) { return d + '★'; }).join(' ') : 'Сложность',
            levels.length > 0);
    setChip('kind', s.kind === 'test' ? 'Тесты' : s.kind === 'open' ? 'Задачи' : 'Задачи и тесты', !!s.kind);
    var all = document.querySelector('[data-kind-all]');
    if (all) all.setAttribute('aria-pressed', String(!s.kind));
    if (sol) sol.setAttribute('aria-pressed', String(!!s.has_solution));
  }

  /* ── Лента входа: скелет на время запроса, «Показать ещё» на месте ──── */
  var skelTimer = null;
  function skeleton() {
    var box = document.getElementById('ct-rows');
    if (!box) return;
    box.textContent = '';
    for (var i = 0; i < 6; i++) {
      var row = document.createElement('div');
      row.className = 'rail-skel';
      /* Своя разметка без данных — innerHTML здесь безопасен. */
      row.innerHTML = '<i class="k1"></i><span class="k2"><i style="width:' + (34 + (i * 13) % 30) +
        '%"></i><i style="width:' + (55 + (i * 17) % 35) + '%"></i></span><i class="k3"></i><i class="k4"></i>';
      box.appendChild(row);
    }
  }
  document.addEventListener('weco:filters-start', function (e) {
    clearTimeout(skelTimer);
    /* Ответ фильтра приходит за доли секунды — скелет, только если ждём дольше. */
    skelTimer = setTimeout(skeleton, e.detail.log ? 0 : 250);
  });
  document.addEventListener('weco:filters-error', function () { clearTimeout(skelTimer); busy(false); });
  function replaceResults(html) {
    var tpl = document.createElement('template');
    tpl.innerHTML = html.trim();
    var fresh = tpl.content.firstElementChild;
    if (!fresh || !results()) return;
    results().replaceWith(fresh);
    if (typeof window.renderMathIn === 'function') window.renderMathIn(fresh);
  }
  document.addEventListener('click', function (e) {
    var more = e.target.closest('[data-more]');
    if (!more || !F) return;
    e.preventDefault();
    fetch(stateUrl + more.search, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (data) { replaceResults(data.results_html); })
      .catch(function () { location.href = more.href; });
  });

  /* ── Карта тем фоном: выбранные темы и теги подсвечены (выбор = фильтры) ── */
  var bg = document.getElementById('stol-bg'), bgMap = null;
  var selNode = document.getElementById('stol-map-selected');
  if (bg && window.TopicMapPreview) {
    bgMap = TopicMapPreview.mount(bg, {
      dataUrl: bg.getAttribute('data-map-url'), inert: true,
      zoom: 1.9, pitch: -0.26, cy: 0.4, dim: 0.5,
      selected: selNode ? JSON.parse(selNode.textContent) : null
    });
  }
  var mapLabel = document.getElementById('se-map-l');
  var mapTotal = document.getElementById('se-map-total');
  function paintMap(s) {
    var n = s.topics.size + s.tags.size;
    if (mapLabel) mapLabel.textContent = n ? 'Карта тем: выбрано ' + n : mapTotal.textContent;
    if (bgMap) bgMap.select({ topics: Array.from(s.topics), tags: Array.from(s.tags) });
  }

  /* ── Ответ состояния: шапка, чипы, карта, случайная задача, оценка поиска ── */
  var random = document.getElementById('se-random');
  var randomBase = random ? random.pathname : '';
  document.addEventListener('weco:filters', function (e) {
    var s = e.detail.state, data = e.detail.data;
    clearTimeout(skelTimer);
    busy(false);
    entry.classList.toggle('is-calm', !s.q && !data.selected_count);
    paintChips(s);
    paintMap(s);
    if (random) { var q = F.buildQuery(); random.href = randomBase + (q ? '?' + q : ''); }
    var res = results();
    if (res && res.hasAttribute('data-search-log') && weco.searchRating) weco.searchRating.consider(res);
  });

  syncField();
  if (F) paintChips(F.state);
  weco.stol.entry = { closeDropdowns: closeAll, map: function () { return bgMap; } };
})();

/* ── Страница задачи: ночной первый шаг (ADR 0120), переезжает в S2 ────── */
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
  if (!root || (weco.stol && weco.stol.toggle)) return;

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

  /* 1100–1399: лента выезжает поверх задачи — клик мимо неё закрывает. */
  var OVERLAY = window.matchMedia('(min-width: 1100px) and (max-width: 1399px)');
  document.addEventListener('click', function (e) {
    if (!state.rail || !OVERLAY.matches) return;
    if (e.target.closest('.stol-rail, [data-stol]')) return;
    state.rail = false; save(state); paint();
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

  /* Телефон: кнопки нижней панели нажимают кнопки страницы. */
  var PHONE = { hint: 'hint-btn', sol: 'sol-btn', reveal: 'reveal-btn' };
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-phone]');
    if (!btn) return;
    var what = btn.getAttribute('data-phone');
    if (what === 'ai') {
      var ai = document.querySelector('.pd-side .ai');
      if (ai) { ai.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
      var field = document.getElementById('ai-text');
      if (field) { field.focus({ preventScroll: true }); }
      return;
    }
    var target = document.getElementById(PHONE[what]);
    if (target && !target.disabled) {
      target.click();
      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  });

  paint();
  weco.stol = weco.stol || {};
  weco.stol.toggle = toggle;
  weco.stol.focus = focus;
})();
