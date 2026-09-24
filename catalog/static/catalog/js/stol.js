/* «Стол» — один экран на каталог, задачу и карту тем (решения владельца
   17–18.09.2026, README `claude/mockups/catalog_stol_20260917/README.md`).
   Одно пространство имён — `weco.stol`. Фильтры — одно состояние
   `weco.filters` (catalog_filters.js): чипы входа, окно «Все фильтры» и
   поиск пишут в него и перерисовываются по событию `weco:filters`.
   Без скрипта экран рабочий: поиск — GET-форма, строки — ссылки. */

/* ── Вид экрана: `entry` · `stol` · `map` ───────────────────────────────
   Одна точка смены вида: атрибут `data-view` у `#stol-app` и узор «W» на
   фоне — он есть только у открытой задачи (решение владельца 18.09.2026: на
   входе и на карте фоном служит облако тем). */
(function () {
  'use strict';
  window.weco = window.weco || {};
  weco.stol = weco.stol || {};
  weco.stol.setView = function (view) {
    var app = document.getElementById('stol-app');
    if (app) app.setAttribute('data-view', view);
    if (view === 'stol') { delete document.body.dataset.bgPattern; } else { document.body.dataset.bgPattern = 'off'; }
    document.dispatchEvent(new CustomEvent('weco:view', { detail: { view: view } }));
  };

  /* Карта тем (README §6): `stol_map.js` и движок грузятся при наведении на
     «Карта тем» или при первом нажатии — не на каждый вход в каталог. */
  var waiting = null;
  function withMap(cb) {
    if (weco.stolMap) { cb(weco.stolMap); return; }
    if (waiting) { waiting.push(cb); return; }
    waiting = [cb];
    var app = document.getElementById('stol-app');
    var s = document.createElement('script');
    s.src = app.getAttribute('data-map-js');
    s.onload = function () { var list = waiting; waiting = null; list.forEach(function (f) { f(weco.stolMap); }); };
    s.onerror = function () { location.href = app.getAttribute('data-map-url'); };
    document.head.appendChild(s);
  }
  weco.stol.openMap = function (opts) { withMap(function (m) { m.open(opts); }); };
  weco.stol.prefetchMap = function () { withMap(function (m) { m.prefetch(); }); };
})();

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
      var dd = document.getElementById(btn.getAttribute('aria-controls'));
      dd.hidden = !open;
      /* Не ниже края окна: «Готово» внизу выпадашки обязано быть видно. */
      if (open) dd.style.maxHeight = Math.max(220, Math.min(430, window.innerHeight - dd.getBoundingClientRect().top - 16)) + 'px';
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
  /* Отклик на выбор — сразу, а не когда придёт ответ: на медленной базе
     `api_filter_state` думает секунды, и немой экран читается как «не нажалось»
     (замечание владельца 18.09.2026). Галочка ставится до запроса
     (`catalog_filters.js`), здесь — скелет ленты и «Обновляю…» в выпадашке. */
  function loading(on) { entry.classList.toggle('is-loading', on); }
  document.addEventListener('weco:filters-start', function () {
    clearTimeout(skelTimer);
    loading(true);
    skeleton();
  });
  document.addEventListener('weco:filters-error', function () { clearTimeout(skelTimer); loading(false); busy(false); });
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
    fetch(stateUrl + more.search, { headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-Weco-Search': '1' } })
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
      zoom: 1.55, nodeScale: 1.1, pitch: -0.26, cy: 0.42, dim: 0.5, eager: true,
      selected: selNode ? JSON.parse(selNode.textContent) : null
    });
  }
  var mapPill = document.getElementById('se-map');
  if (mapPill) mapPill.addEventListener('click', function (e) {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    weco.stol.openMap();
  });
  if (mapPill) {
    mapPill.addEventListener('pointerenter', weco.stol.prefetchMap, { once: true });
    mapPill.addEventListener('focus', weco.stol.prefetchMap, { once: true });
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
    loading(false);
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
  /* Отложенный умный поиск (24.09.2026): страница пришла с `?q=`, но без
     сортировки — полная загрузка за неё не платит. Просим её сразу, под
     индикатором; строку журнала поиска пишет этот запрос (`log=1`). */
  var pending = results();
  if (F && pending && pending.hasAttribute('data-search-deferred')) {
    busy(true);
    F.refresh({ log: true });
  }
  weco.stol.entry = { closeDropdowns: closeAll, map: function () { return bgMap; } };
})();

/* ── «Стол»: лента · задача · помощь (вид `stol`, README §1, §3) ──────────
   Панели: лента слева и помощь справа сворачиваются в полоски 52 px; первое
   открытие — лента свёрнута, помощь открыта (решение владельца 17.09), дальше
   состояние запоминается (`localStorage`). «Фокус» (F) убирает обе панели и
   шапку, Esc выходит. Клавиши: [ лента, ] помощь, J/K и стрелки по ленте,
   Enter открыть, / поиск; молчат, пока курсор в поле ввода.

   Смена задачи — без перезагрузки: `GET /catalog/problem/<id>/?pane=1`
   отдаёт центр и помощь теми же партиалами, что прямая ссылка; сценарий
   подменяет их, ставит адрес `pushState` и зовёт `weco.stolTask.init`.
   «Назад» браузера возвращает прежнюю задачу или вход с теми же результатами
   и прокруткой (вход не перерисовывается, он просто скрыт). */
(function () {
  'use strict';
  window.weco = window.weco || {};
  weco.stol = weco.stol || {};
  var app = document.getElementById('stol-app');
  var desk = document.getElementById('stol');
  if (!app || !desk) return;

  var KEY = 'weco_stol';
  var center = document.getElementById('stol-center');
  var help = document.getElementById('stol-help');
  var rail = document.getElementById('stol-rail');
  var list = document.getElementById('stol-rail-list');
  var entry = document.getElementById('stol-entry');
  var entryUrl = app.getAttribute('data-entry-url');
  var paneBase = app.getAttribute('data-pane-base');
  var F = weco.filters;
  var OVERLAY = window.matchMedia('(max-width: 1399px)');
  /* Телефон (README §8): лента и помощь — шторки снизу, обе закрыты при каждом
     открытии задачи и в память десктопа не пишутся. */
  var PHONE = window.matchMedia('(max-width: 759px)');
  var phonePanels = { rail: false, help: false };
  function panels() { return PHONE.matches ? phonePanels : state.panels; }

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state.panels)); } catch (e) { /* приватное окно */ } }
  function inField(el) { return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)); }

  var state = weco.stol.state = {
    view: app.getAttribute('data-view'),
    problemId: Number(desk.getAttribute('data-problem')) || null,
    panels: load() || { rail: false, help: true },
    focus: false,
    tab: entry ? 'results' : 'similar',
    filters: F ? F.state : null,
    results: [],
    scroll: 0
  };
  document.addEventListener('weco:view', function (e) { state.view = e.detail.view; });

  /* ── Панели и «Фокус» ──────────────────────────────────────────────── */
  function paint() {
    var p = panels();
    desk.setAttribute('data-rail', p.rail ? 'open' : 'closed');
    desk.setAttribute('data-help', p.help ? 'open' : 'closed');
    document.body.classList.toggle('stol-sheet-open', PHONE.matches && (p.rail || p.help));
  }
  if (PHONE.addEventListener) PHONE.addEventListener('change', paint);
  function focusMode(on) {
    state.focus = on;
    document.body.classList.toggle('stol-is-focus', on);
    desk.querySelectorAll('.stol-focus-label').forEach(function (el) {
      el.textContent = on ? 'Выйти из фокуса' : 'Фокус';
      el.parentNode.classList.toggle('tb-btn--dark', on);
    });
  }
  function toggle(panel) {
    /* Из «Фокуса» кнопка панели её открывает, а не переключает вслепую. */
    var p = panels();
    if (state.focus) { focusMode(false); p[panel] = true; }
    else { p[panel] = !p[panel]; }
    if (PHONE.matches && p[panel]) p[panel === 'rail' ? 'help' : 'rail'] = false;
    if (!PHONE.matches) save();
    paint();
  }
  function openPanel(panel) {
    if (state.focus) focusMode(false);
    var p = panels();
    if (!p[panel]) {
      p[panel] = true;
      if (PHONE.matches) p[panel === 'rail' ? 'help' : 'rail'] = false; else save();
      paint();
    }
  }
  /* Лента поверх задачи (1100–1399) и шторки (< 1100) закрываются кликом мимо. */
  document.addEventListener('click', function (e) {
    if (state.view !== 'stol' || !OVERLAY.matches) return;
    if (e.target.closest('.stol-rail, .help-panel, .stol-strip, .stol-phonebar, [data-stol], [data-help-open], .ct-all, .rp-back')) return;
    var changed = false, p = panels();
    if (p.rail) { p.rail = false; changed = true; }
    if (window.innerWidth < 1100 && p.help) { p.help = false; changed = true; }
    if (changed) paint();
  });
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-stol]');
    if (!btn) return;
    var what = btn.getAttribute('data-stol');
    if (what === 'focus') focusMode(!state.focus); else toggle(what);
  });

  /* ── Лента: вкладки «Выдача / Похожие / Мои» ───────────────────────── */
  var tabs = rail.querySelectorAll('[data-rail-tab]');
  var similarHtml = list.innerHTML, savedHtml = null;
  function tabBtn(name) { return rail.querySelector('[data-rail-tab="' + name + '"]'); }
  /* Выдача — строки блока результатов входа, один источник с ним. */
  function resultsRows() {
    var box = document.getElementById('ct-rows');
    return box ? Array.prototype.slice.call(box.querySelectorAll('.rail-row')) : [];
  }
  function fillList() {
    if (state.tab === 'results') {
      list.textContent = '';
      resultsRows().forEach(function (row) {
        var copy = row.cloneNode(true);
        copy.classList.remove('ct-appear');
        list.appendChild(copy);
      });
      var more = document.querySelector('#ct-results [data-more]');
      if (more) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ct-btn ct-btn--quiet rail-more';
        btn.textContent = more.textContent;
        btn.addEventListener('click', function () { more.click(); });
        list.appendChild(btn);
      }
    } else if (state.tab === 'similar') {
      list.innerHTML = similarHtml;
    } else if (savedHtml !== null) {
      list.innerHTML = savedHtml;
    } else {
      list.textContent = '';
      fetch(rail.getAttribute('data-saved-url'), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          savedHtml = d.rows_html || '<p class="rail-empty">Сохранённых задач пока нет.</p>';
          if (state.tab === 'saved') { list.innerHTML = savedHtml; markCurrent(); }
        })
        .catch(function () { /* вкладка остаётся пустой */ });
    }
    markCurrent();
    if (typeof window.renderMathIn === 'function') window.renderMathIn(list);
  }
  function setTab(name) {
    state.tab = name;
    tabs.forEach(function (t) { t.setAttribute('aria-selected', t.getAttribute('data-rail-tab') === name ? 'true' : 'false'); });
    fillList();
    neighbours();
  }
  tabs.forEach(function (t) { t.addEventListener('click', function () { setTab(t.getAttribute('data-rail-tab')); }); });

  function rowsOfTab() { return Array.prototype.slice.call(list.querySelectorAll('.rail-row')); }
  function markCurrent() {
    rowsOfTab().forEach(function (row) {
      row.classList.toggle('is-current', Number(row.getAttribute('data-id')) === state.problemId);
    });
  }

  /* ── Позиция «3 из 506», стрелки, соседи с названиями, «Дальше» ────── */
  function titleOf(row) { var t = row.querySelector('.rail-title'); return t ? t.textContent.trim() : ''; }
  function totalOfTab(rows) {
    if (state.tab === 'results') {
      var res = document.getElementById('ct-results');
      var n = res && Number(res.getAttribute('data-total'));
      if (n) return n;
    }
    return rows.length;
  }
  function neighbours() {
    if (!state.problemId) return;
    var rows = rowsOfTab();
    var i = -1;
    rows.forEach(function (row, k) { if (Number(row.getAttribute('data-id')) === state.problemId) i = k; });
    if (i < 0 && state.tab !== 'results' && !rows.length) return;   /* список ещё грузится */
    var prev = i > 0 ? rows[i - 1] : null;
    var next = i >= 0 ? rows[i + 1] || null : rows[0] || null;
    if (next && Number(next.getAttribute('data-id')) === state.problemId) next = null;
    var pos = i >= 0 ? (i + 1) + ' из ' + totalOfTab(rows) : '';
    var tbPos = document.getElementById('tb-pos'); if (tbPos) tbPos.textContent = pos;
    var sPos = document.getElementById('strip-pos'); if (sPos) sPos.textContent = i >= 0 ? (i + 1) + '/' + rows.length : '';
    desk.querySelectorAll('[data-stol-step]').forEach(function (a) {
      var row = a.getAttribute('data-stol-step') === '-1' ? prev : next;
      if (a.tagName === 'A') {
        if (row) { a.href = row.getAttribute('href'); a.removeAttribute('aria-disabled'); }
        else { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); }
      } else {
        a.disabled = !row;
      }
    });
    var nb = document.getElementById('stol-nb');
    if (nb) {
      nb.textContent = '';
      [[prev, 'prev', '← предыдущая', '-1'], [next, 'next', 'следующая →', '1']].forEach(function (spec) {
        if (!spec[0]) return;
        var a = document.createElement('a');
        a.className = 'nb-a nb-a--' + spec[1];
        a.href = spec[0].getAttribute('href');
        a.setAttribute('data-stol-step', spec[3]);
        var s = document.createElement('small'); s.textContent = spec[2];
        var b = document.createElement('b'); b.textContent = titleOf(spec[0]);
        a.appendChild(s); a.appendChild(b);
        nb.appendChild(a);
      });
      nb.hidden = !prev && !next;
    }
    var howNext = document.getElementById('how-next');
    if (howNext) {
      var marked = !!document.querySelector('#how [aria-pressed="true"]');
      howNext.hidden = !next || !marked;
    }
    desk.querySelectorAll('#test-next, .stol-phonebar .is-main').forEach(function (a) { a.hidden = !next; });
  }
  document.addEventListener('weco:progress', neighbours);

  /* ── Смена задачи без перезагрузки ─────────────────────────────────── */
  var seq = 0;
  function show(view) {
    state.view = view;
    if (weco.stol.setView) weco.stol.setView(view);
  }
  function open(id, opts) {
    opts = opts || {};
    var mine = ++seq;
    if (state.view === 'entry') { state.scroll = window.scrollY; }
    center.classList.add('is-loading');
    var url = paneBase + id + '/?pane=1' + (F && F.buildQuery() && !F.state.q ? '&' + F.buildQuery() : '');
    return fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        if (mine !== seq) return;
        center.innerHTML = d.center_html;
        help.innerHTML = d.help_html;
        similarHtml = d.similar_html;
        center.classList.remove('is-loading');
        state.problemId = d.id;
        desk.setAttribute('data-problem', d.id);
        if (!tabBtn('results') || tabBtn('results').hidden) { if (state.tab === 'results') state.tab = 'similar'; }
        var first = state.view !== 'stol';
        show('stol');
        if (first && !load()) { state.panels = { rail: false, help: true }; }
        paint();
        if (opts.push !== false) history.pushState({ stol: 'problem', id: d.id }, '', d.url);
        document.title = d.title + ' · Экономика';
        window.scrollTo(0, 0);
        if (typeof window.renderMathIn === 'function') { window.renderMathIn(center); window.renderMathIn(help); }
        if (weco.stolTask) weco.stolTask.init(desk);
        setTab(state.tab);
        if (weco.trackPage) weco.trackPage();
        /* Открытие задачи на месте — событие беты (прежде слала модалка «Условие», `_catalog_js.html`). */
        if (weco.track) weco.track('problem_open', { problem_id: d.id, from: first ? 'entry' : 'stol' });
        if (PHONE.matches) { phonePanels.rail = false; phonePanels.help = false; paint(); }
        else if (OVERLAY.matches && state.panels.rail) { state.panels.rail = false; paint(); }
      })
      .catch(function () {
        if (mine !== seq) return;
        center.classList.remove('is-loading');
        /* Честное сообщение и обычная ссылка: сеть подвела, а не задача пропала. */
        var box = document.createElement('p');
        box.className = 'pane-error';
        box.appendChild(document.createTextNode('Задача не загрузилась. '));
        var a = document.createElement('a');
        a.href = paneBase + id + '/';
        a.textContent = 'Открыть обычной ссылкой';
        box.appendChild(a);
        center.insertBefore(box, center.firstChild);
        show('stol');
      });
  }
  function toEntry(push) {
    if (!entry) { location.href = entryUrl; return; }
    focusMode(false);
    show('entry');
    if (push !== false) history.pushState({ stol: 'entry' }, '', entryUrl + (F && F.buildQuery() ? '?' + F.buildQuery() : ''));
    document.title = 'Умный каталог · Экономика';
    window.scrollTo(0, state.scroll);
    if (weco.trackPage) weco.trackPage();
  }
  weco.stol.open = open;
  weco.stol.toEntry = toEntry;
  weco.stol.openPanel = openPanel;
  weco.stol.toggle = toggle;
  weco.stol.focus = focusMode;

  function plainClick(e) { return !(e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey); }
  function idOf(href) { var m = /\/catalog\/problem\/(\d+)\/?(?:$|\?)/.exec(href || ''); return m ? Number(m[1]) : null; }
  document.addEventListener('click', function (e) {
    if (!plainClick(e)) return;
    var a = e.target.closest('a');
    if (!a) return;
    if (a.hasAttribute('data-stol-home') || (a.pathname === entryUrl && a.closest('.site-nav') && entry)) {
      if (!entry) return;
      e.preventDefault();
      if (state.view === 'map') { if (weco.stolMap) weco.stolMap.close(); return; }
      toEntry();
      return;
    }
    if (a.getAttribute('aria-disabled') === 'true') { e.preventDefault(); return; }
    if (!a.closest('#stol-app')) return;
    var id = idOf(a.getAttribute('href'));
    if (!id || a.target === '_blank') return;
    e.preventDefault();
    if (id === state.problemId && state.view === 'stol') return;
    open(id);
  });
  window.addEventListener('popstate', function () {
    var id = idOf(location.pathname);
    var mapUrl = app.getAttribute('data-map-url');
    if (state.view === 'map' && location.pathname !== mapUrl) {
      /* «Назад» с карты: сначала закрыть карту, потом — куда вёл адрес. */
      if (id) { if (weco.stolMap) weco.stolMap.close({ push: false, instant: true }); open(id, { push: false }); return; }
      if (weco.stolMap) weco.stolMap.close({ push: false });
      return;
    }
    if (id) { open(id, { push: false }); return; }
    if (location.pathname === mapUrl && entry) {
      if (state.view === 'stol') toEntry(false);
      weco.stol.openMap({ push: false });
      return;
    }
    if (location.pathname === entryUrl && entry) { toEntry(false); return; }
    location.reload();
  });
  if (state.view === 'entry') history.replaceState({ stol: 'entry' }, '', location.href);
  else if (state.problemId) history.replaceState({ stol: 'problem', id: state.problemId }, '', location.href);

  /* ── Поиск и фильтры ленты — то же состояние, что у входа ───────────── */
  var railAsk = document.getElementById('rail-ask');
  if (railAsk && F && entry) {
    railAsk.addEventListener('submit', function (e) {
      e.preventDefault();
      var q = railAsk.querySelector('input').value.trim();
      F.state.q = q;
      var field = document.getElementById('ct-q');
      if (field) field.value = q;
      F.refresh({ log: !!q });
      setTab('results');
    });
  }
  var railFilt = document.getElementById('rail-filters');
  if (railFilt && F && F.open) {
    railFilt.addEventListener('click', function (e) { e.preventDefault(); F.open(); });
  }
  function filterSummary() {
    if (!F) return;
    var s = F.state, parts = [];
    s.topics.forEach(function (v) { var el = document.querySelector('.se-opt[data-topic="' + v + '"] .se-opt-l'); if (el) parts.push(el.textContent.trim()); });
    if (s.difficulties.size) parts.push(Array.from(s.difficulties).sort().map(function (d) { return d + '★'; }).join(' '));
    if (s.kind) parts.push(s.kind === 'test' ? 'тесты' : 'задачи');
    if (s.has_solution) parts.push('с решением');
    var n = document.getElementById('rail-filt-n'), sum = document.getElementById('rail-filt-sum');
    var count = s.topics.size + s.tags.size + s.difficulties.size + s.sources.size + s.features.size +
                (s.kind ? 1 : 0) + (s.character ? 1 : 0) + (s.has_solution ? 1 : 0);
    if (n) n.textContent = count ? ' · ' + count : '';
    if (sum) sum.textContent = parts.join(', ');
    var q = document.getElementById('rail-q');
    if (q && document.activeElement !== q) q.value = s.q || '';
  }
  document.addEventListener('weco:filters', function () {
    filterSummary();
    if (state.tab === 'results') fillList();
    neighbours();
  });

  /* ── Клавиши (README §1) ────────────────────────────────────────────── */
  var cursor = -1;
  function move(step) {
    var rows = rowsOfTab();
    if (!rows.length) return;
    openPanel('rail');
    if (cursor < 0) rows.forEach(function (row, k) { if (row.classList.contains('is-current')) cursor = k; });
    cursor = Math.max(0, Math.min(rows.length - 1, cursor + step));
    rows.forEach(function (row, k) { row.classList.toggle('is-cursor', k === cursor); });
    rows[cursor].scrollIntoView({ block: 'nearest' });
  }
  document.addEventListener('keydown', function (e) {
    if (state.view !== 'stol') {
      if (state.view === 'map' || e.key === 'Escape' || inField(e.target)) return;
      if (e.key === '/' && document.getElementById('ct-q')) { e.preventDefault(); document.getElementById('ct-q').focus(); }
      return;
    }
    if (e.altKey || e.ctrlKey || e.metaKey || inField(e.target)) return;
    if (document.querySelector('dialog[open], .fb-back, .rp-back.is-open')) return;
    var k = e.key;
    if (k === '[') { toggle('rail'); }
    else if (k === ']') { toggle('help'); }
    else if (k === 'f' || k === 'F' || k === 'а' || k === 'А') { focusMode(!state.focus); }
    else if (k === 'Escape') { if (state.focus) focusMode(false); else if (entry) toEntry(); else return; }
    else if (k === 'j' || k === 'о' || k === 'ArrowDown') { move(1); }
    else if (k === 'k' || k === 'л' || k === 'ArrowUp') { move(-1); }
    else if (k === 'Enter' && cursor >= 0 && rowsOfTab()[cursor]) { open(idOf(rowsOfTab()[cursor].getAttribute('href'))); cursor = -1; }
    else if (k === '/') { openPanel('rail'); var q = document.getElementById('rail-q'); if (q) q.focus(); }
    else { return; }
    e.preventDefault();
  });

  /* ── Старт ─────────────────────────────────────────────────────────── */
  paint();
  filterSummary();
  if (state.view === 'stol') {
    if (weco.stolTask) weco.stolTask.init(desk);
    setTab(state.tab);
  }
})();
