/* Аналитика беты: сырые события в свою таблицу (решение владельца 15.09.2026).

   Экран (page_view), уход с него с активным временем (page_leave), клики по
   ссылкам и кнопкам, поиск и явные события страниц через
   `weco.track(name, props)`. Шлёт пачками на /api/track/: раз в 5 с, при 20
   событиях и при уходе со страницы (`sendBeacon`, запасной путь —
   `fetch` с keepalive). Серверу из профиля ничего не уходит: только cookie
   посетителя `weco_vid`, путь без строки запроса и то, что передано в props.
   Учёт Do-Not-Track не ведётся — решение владельца (бета с согласием). */
(function () {
  'use strict';
  if (window.weco && window.weco.track) return;          // подключён дважды

  var ENDPOINT = '/api/track/';
  var FLUSH_MS = 5000;
  var FLUSH_AT = 20;
  var BATCH = 50;                                         // потолок сервера
  var queue = [];

  function randomId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
  }

  // Посетитель — один браузер на год; ставит скрипт, сервер без неё не пишет.
  if (!/(?:^|;\s*)weco_vid=/.test(document.cookie)) {
    document.cookie = 'weco_vid=' + randomId() + '; max-age=31536000; path=/; SameSite=Lax';
  }

  function track(name, props, durationMs) {
    var event = {
      name: String(name),
      path: location.pathname,
      props: props || {},
      viewport: window.innerWidth + 'x' + window.innerHeight,
      t: Date.now()
    };
    if (typeof durationMs === 'number') event.duration_ms = Math.round(durationMs);
    queue.push(event);
    if (queue.length >= FLUSH_AT) flush();
  }

  function send(body) {
    try {
      if (navigator.sendBeacon
          && navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }))) {
        return;
      }
    } catch (e) { /* уйдём запасным путём */ }
    if (window.fetch) {
      fetch(ENDPOINT, {
        method: 'POST', body: body, keepalive: true, credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }
      }).catch(function () {});
    }
  }

  function flush() {
    while (queue.length) {
      send(JSON.stringify({ events: queue.splice(0, BATCH) }));
    }
  }
  setInterval(flush, FLUSH_MS);

  /* Активное время экрана: счёт стоит, пока вкладка скрыта. Уход объявляется
     на каждом скрытии вкладки с накопленным временем — последняя запись
     одного просмотра (`view`) и есть его длительность. */
  var view = randomId();
  var activeMs = 0;
  var shownAt = document.visibilityState === 'hidden' ? null : Date.now();

  function leave() {
    if (shownAt !== null) {
      activeMs += Date.now() - shownAt;
      shownAt = null;
    }
    track('page_leave', { view: view }, activeMs);
    flush();
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      if (shownAt !== null) leave();
    } else if (shownAt === null) {
      shownAt = Date.now();
    }
  });
  window.addEventListener('pagehide', function () {
    if (shownAt !== null) leave();
  });

  // Клики — в фазе перехвата: окна обратной связи гасят всплытие у себя.
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest
      ? e.target.closest('a, button, [role=button], input[type=submit]') : null;
    if (!el) return;
    var classes = typeof el.className === 'string' ? el.className.split(/\s+/) : [];
    track('click', {
      text: (el.getAttribute('aria-label') || el.textContent || el.value || '')
        .replace(/\s+/g, ' ').trim().slice(0, 60),
      id: el.id || '',
      cls: classes.filter(Boolean).slice(0, 2).join(' '),
      href: el.getAttribute('href') || ''
    });
  }, true);

  function pageView(referrer) {
    track('page_view', { view: view, referrer: referrer.slice(0, 200) });
    // Страница задачи: номер из адреса, разметку ради аналитики не трогаем.
    var problem = location.pathname.match(/^\/catalog\/problem\/(\d+)\//);
    if (problem) track('problem_open', { problem_id: Number(problem[1]) });
  }
  pageView(document.referrer);

  /* Смена экрана без перезагрузки («Стол», 18.09.2026): прежний просмотр
     закрывается уходом с активным временем, новый — свой `view`. */
  var lastPath = location.pathname;
  function trackPage() {
    if (shownAt !== null) leave();
    view = randomId();
    activeMs = 0;
    shownAt = document.visibilityState === 'hidden' ? null : Date.now();
    pageView(location.origin + lastPath);
    lastPath = location.pathname;
  }

  // Выдача поиска: состояние кладёт сервер в data-атрибуты секции результатов.
  var query = document.getElementById('ct-q');
  var results = document.querySelector('[data-search-status]');
  if (results) {
    track('search', {
      q_len: query ? query.value.trim().length : 0,
      status: results.getAttribute('data-search-status'),
      total: Number(results.getAttribute('data-search-total')) || 0,
      degraded: results.hasAttribute('data-search-degraded')
    });
  }
  var askForm = document.getElementById('ct-ask-form');
  if (askForm && query) {
    askForm.addEventListener('submit', function () {
      track('search_submit', { q_len: query.value.trim().length });
      flush();
    });
  }

  window.weco = window.weco || {};
  window.weco.track = track;
  window.weco.trackPage = trackPage;
})();
