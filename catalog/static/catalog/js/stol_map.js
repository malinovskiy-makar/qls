/* «Стол»: карта тем на том же экране (README §6, решения владельца 17–18.09.2026).

   Кнопка «Карта тем» → фоновое облако входа выходит на передний план:
   содержимое каталога уходит каскадом, камера полной карты (`topic_map.js`)
   отъезжает от кадра облака (`TopicMapPreview.handoff()`), потом входят
   панели карты. Обратно — то же в обратном порядке. Файл грузится при первом
   нажатии «Карта тем» (`weco.stol.openMap` в `stol.js`), а на `/catalog/map/`
   — сразу; движок и разметку карты он догружает сам.

   ⚠️ ВЫБОР = ФИЛЬТР КАТАЛОГА, ОДНО СОСТОЯНИЕ. Клик по теме или тегу пишет
   `weco.filters.state` (темы по «или», теги по «и») и перерисовывает вход под
   картой; фильтр, поставленный чипом, виден на карте. Любой выход оставляет
   фильтр применённым. */
(function () {
  'use strict';
  window.weco = window.weco || {};
  weco.stol = weco.stol || {};
  var app = document.getElementById('stol-app');
  if (!app || weco.stolMap) return;

  var F = weco.filters;
  var entryUrl = app.getAttribute('data-entry-url');
  var mapUrl = app.getAttribute('data-map-url');
  var quiet = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var EASE = 'cubic-bezier(.2,.75,.2,1)';
  var busy = false, scroll = 0, engine = null;

  function $(id) { return document.getElementById(id); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function query() { return F ? F.buildQuery() : ''; }
  function withQuery(url) { var q = query(); return url + (q ? '?' + q : ''); }
  function bg() { return weco.stol.entry && weco.stol.entry.map ? weco.stol.entry.map() : null; }
  function selected() {
    if (F) return { topics: Array.from(F.state.topics), tags: Array.from(F.state.tags) };
    var node = $('stol-map-selected');
    return node ? JSON.parse(node.textContent) : { topics: [], tags: [] };
  }
  function plural(n, forms) {
    var a = n % 100, b = n % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b === 1) return forms[0];
    return b > 1 && b < 5 ? forms[1] : forms[2];
  }

  /* Настройки движка — до его загрузки (он читает их при старте). Наклон и
     сдвиг покоя — README §6: наклон 0,40 рад, центр на 140 px левее (место
     панели «Разделы корпуса»). */
  window.TMAP_URL = app.getAttribute('data-map-data');
  window.TMAP_EMBED = {
    pitch: -0.40,
    offsetX: function () { return window.innerWidth >= 1100 ? -140 : 0; },
    themeLabels: true,
    howto: 'Крупный узел – тема, мелкий – тег. Тяните мышью, чтобы повернуть корпус. ' +
           'Нажмите на тему или тег: выбор сразу становится фильтром каталога.',
    selected: selected(),
    onPick: onPick,
    onReady: function () { if (engine) engine(); }
  };

  /* ── Нижняя полоса: «Выбрано: 2 темы, 1 тег» + названия ─────────────── */
  function paintFoot(list) {
    var nt = 0, ng = 0, names = [];
    list.forEach(function (n) { if (n.k === 'theme') nt++; else ng++; names.push(n.l); });
    var parts = [];
    if (nt) parts.push(nt + ' ' + plural(nt, ['тема', 'темы', 'тем']));
    if (ng) parts.push(ng + ' ' + plural(ng, ['тег', 'тега', 'тегов']));
    $('stol-map-count').textContent = parts.length ? 'Выбрано: ' + parts.join(', ') : 'Темы и теги не выбраны';
    $('stol-map-names').textContent = names.join(' · ');
    $('tmap-reset').hidden = !list.length;
    $('stol-map-show-l').textContent = list.length ? 'Показать задачи' : 'Показать все задачи';
    qa('[data-map-exit]', $('stol-map')).forEach(function (a) { a.href = withQuery(entryUrl); });
  }
  function pickedNodes() {
    var s = selected(), topics = {}, tags = {};
    s.topics.forEach(function (v) { topics[String(v)] = true; });
    s.tags.forEach(function (v) { tags[String(v)] = true; });
    return window.TMAP ? TMAP.nodes().filter(function (n) {
      if (n.db === null || n.db === undefined) return false;
      return n.k === 'theme' ? topics[String(n.db)] : tags[String(n.db)];
    }) : [];
  }

  /* Клик по узлу карты → фильтр каталога; вход под картой перерисуется сам. */
  function onPick(list) {
    paintFoot(list);
    if (!F) return;
    var topics = [], tags = [];
    list.forEach(function (n) {
      if (n.db === null || n.db === undefined) return;
      (n.k === 'theme' ? topics : tags).push(String(n.db));
    });
    var same = topics.length === F.state.topics.size && tags.length === F.state.tags.size &&
      topics.every(function (v) { return F.state.topics.has(v); }) &&
      tags.every(function (v) { return F.state.tags.has(v); });
    if (same) return;
    F.state.topics = new Set(topics);
    F.state.tags = new Set(tags);
    F.refresh();
    if (app.getAttribute('data-view') === 'map') history.replaceState({ stol: 'map' }, '', withQuery(mapUrl));
  }

  /* ── Загрузка: разметка, стиль, движок ───────────────────────────────── */
  function load(src, tag) {
    return new Promise(function (resolve, reject) {
      var el = document.createElement(tag);
      if (tag === 'link') { el.rel = 'stylesheet'; el.href = src; } else { el.src = src; }
      el.onload = resolve;
      el.onerror = function () { reject(new Error(src)); };
      document.head.appendChild(el);
    });
  }
  var ready = null;
  function ensure() {
    if (ready) return ready;
    var css = app.getAttribute('data-map-css');
    var steps = [];
    if (!qa('link[rel="stylesheet"]').some(function (l) { return l.getAttribute('href') === css; })) steps.push(load(css, 'link'));
    if (!$('stol-map')) {
      steps.push(fetch(mapUrl + '?pane=1' + (query() ? '&' + query() : ''), { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (d) { app.insertAdjacentHTML('beforeend', d.html); bindMap(); }));
    } else { bindMap(); }
    ready = Promise.all(steps).then(function () {
      return new Promise(function (resolve) {
        engine = resolve;
        if (window.TMAP && TMAP.isReady()) resolve();
        else if (!window.TMAP) load(app.getAttribute('data-map-engine'), 'script');
      });
    }).then(function () { paintFoot(pickedNodes()); });
    ready.catch(function () { ready = null; });
    return ready;
  }

  /* ── Каскад: вход уходит и возвращается, панели карты входят после ─── */
  var CATALOG = [['.se-head', 210, 560], ['.se-search', 140, 640], ['.se-map', 140, 640],
                 ['.se-line', 70, 720], ['#ct-results', 0, 800]];
  var PANELS = [['.tmap-head', 'translateY(-18px)', 620], ['.tmap-panel', 'translateX(26px)', 720],
                ['.tmap-foot', 'translateY(18px)', 800], ['.tmap-zoom', 'translateY(18px)', 800]];
  /* Свои анимации хранятся на узле: у шапки входа есть и CSS-переходы
     (сжатие после первого фильтра), их трогать нельзя. */
  function clearFx(el) { if (el && el.stolFx) { el.stolFx.forEach(function (a) { a.cancel(); }); el.stolFx = null; } }
  function fx(el, from, to, delay) {
    if (!el || !el.animate) return;
    clearFx(el);
    var d = quiet ? 0 : delay;
    el.stolFx = [
      el.animate([{ opacity: from.o }, { opacity: to.o }], { duration: quiet ? 0 : 550, delay: d, easing: 'ease', fill: 'both' }),
      el.animate([{ transform: from.t }, { transform: to.t }], { duration: quiet ? 0 : 850, delay: d, easing: EASE, fill: 'both' })
    ];
  }
  var AWAY = { o: 0, t: 'translateY(34px) scale(.975)' }, HERE = { o: 1, t: 'none' };
  function catalogOut() { CATALOG.forEach(function (c) { fx(app.querySelector(c[0]), HERE, AWAY, c[1]); }); }
  function catalogIn() { CATALOG.forEach(function (c) { fx(app.querySelector(c[0]), AWAY, HERE, c[2]); }); }
  function panelsIn() { PANELS.forEach(function (p) { fx($('stol-map').querySelector(p[0]), { o: 0, t: p[1] }, HERE, p[2]); }); }
  function panelsOut() { PANELS.forEach(function (p) { fx($('stol-map').querySelector(p[0]), HERE, { o: 0, t: p[1] }, 0); }); }
  function catalogClear() { CATALOG.forEach(function (c) { clearFx(app.querySelector(c[0])); }); }

  /* Кадр облака для движка. Облака ещё нет (раскладка не готова) — кадр
     собирается по его настройкам: переход останется, только без раскладки. */
  function frameOfBg() {
    var b = bg(), h = b && b.handoff();
    if (h) return h;
    var el = $('stol-bg'), r = el ? el.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth, height: 600 };
    var v = TMAP.view();
    return { yaw: v.yaw, pitch: -0.26, scale: v.fit * 1.55, cx: r.left + r.width / 2, cy: r.top + r.height * 0.42, pos: {} };
  }

  /* ── Открыть ────────────────────────────────────────────────────────── */
  function open(opts) {
    opts = opts || {};
    if (busy || app.getAttribute('data-view') === 'map') return;
    busy = true;
    var pill = $('se-map');
    if (pill) pill.classList.add('is-loading');
    if (weco.stol.entry && weco.stol.entry.closeDropdowns) weco.stol.entry.closeDropdowns();
    ensure().then(function () {
      if (pill) pill.classList.remove('is-loading');
      scroll = window.scrollY;
      window.scrollTo(0, 0);
      TMAP.setPicked(selected());
      paintFoot(pickedNodes());
      var from = frameOfBg();
      var root = $('stol-map');
      root.hidden = false;
      app.classList.add('is-map-moving');
      weco.stol.setView('map');
      TMAP.pause(false);
      if (bg()) bg().hold(true);
      catalogOut();
      panelsIn();
      if (opts.push !== false) history.pushState({ stol: 'map' }, '', withQuery(mapUrl));
      document.title = 'Карта тем · Экономика';
      if (weco.trackPage) weco.trackPage();
      TMAP.enter(from, function () {
        app.classList.remove('is-map-moving');
        app.classList.add('is-map-on');
        busy = false;
        TMAP.tour();
      });
    }).catch(function () { location.href = withQuery(mapUrl); });
  }

  /* ── Закрыть: «В каталог», «×», «Показать задачи», Esc, «назад» ─────── */
  function close(opts) {
    opts = opts || {};
    if (busy || app.getAttribute('data-view') !== 'map') return;
    var b = bg();
    if (opts.instant) {
      /* Сразу к задаче («назад» браузера с карты на задачу): без перехода. */
      $('stol-map').hidden = true;
      TMAP.pause(true);
      app.classList.remove('is-map-on', 'is-map-moving');
      if (b) b.hold(false);
      return;
    }
    busy = true;
    app.classList.remove('is-map-on');
    app.classList.add('is-map-moving');
    if (b) b.hold(false);
    var to = frameOfBg();
    catalogIn();
    panelsOut();
    if (opts.push !== false) history.pushState({ stol: 'entry' }, '', withQuery(entryUrl));
    document.title = 'Умный каталог · Экономика';
    if (weco.trackPage) weco.trackPage();
    TMAP.leave(to, function () {
      if (b) b.setYaw(TMAP.view().yaw);
      $('stol-map').hidden = true;
      TMAP.pause(true);
      app.classList.remove('is-map-moving');
      weco.stol.setView('entry');
      window.setTimeout(function () {
        catalogClear();
        busy = false;
        /* «Показать задачи» — к началу входа с применённым фильтром (снимок 08). */
        window.scrollTo(0, opts.show ? 0 : scroll);
      }, quiet ? 0 : 800 + 850 - 1250);
    });
  }

  /* ── Разметка карты: выходы и клавиши ────────────────────────────────── */
  function bindMap() {
    var root = $('stol-map');
    if (!root || root.hasAttribute('data-bound')) return;
    root.setAttribute('data-bound', '');
    root.addEventListener('click', function (e) {
      var a = e.target.closest('[data-map-exit]');
      if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      close({ show: a.getAttribute('data-map-exit') === 'show' });
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || app.getAttribute('data-view') !== 'map') return;
    var tour = $('tmap-tour');
    if (tour && !tour.hidden) return;
    var q = $('tmap-q');
    if (q && document.activeElement === q && q.value) return;
    close();
  });

  /* Фильтр сменился снаружи (чипы) — карта показывает его же. */
  document.addEventListener('weco:filters', function () {
    if (!window.TMAP || !TMAP.isReady()) return;
    TMAP.setPicked(selected());
    paintFoot(pickedNodes());
  });

  weco.stolMap = { open: open, close: close, prefetch: function () { ensure().catch(function () {}); } };

  /* `/catalog/map/`: карта уже в разметке — движок и сразу вид карты, без перехода. */
  if (app.getAttribute('data-view') === 'map') {
    history.replaceState({ stol: 'map' }, '', location.href);
    if (bg()) bg().hold(true);
    ensure().then(function () { TMAP.pause(false); TMAP.tour(); });
  }
})();
