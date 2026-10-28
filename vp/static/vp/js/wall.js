/* Окно стены 2 тура на интро (docs/VP.md, «Стена 2 тура»).
 *
 * ⚠️ ОКНО РАБОТАЕТ И БЕЗ ЭТОГО СКРИПТА: экран выбирает сервер, каждое действие —
 * обычная форма POST с редиректом обратно на `?wall=…`. Скрипт только:
 * 1) делает отрисованное открытым окно модальным;
 * 2) после «Подключить Telegram» переключает 01 на 02 без перезагрузки;
 * 3) на экране 02 опрашивает `wall/state` и перезагружает окно, когда бот ответил.
 *
 * ⚠️ ОПРОС ТОЛЬКО НА 02: на 03 («подписки нет») есть кнопка «проверить», а опрос
 * там только жёг бы запросы. Каждые 3 с, не дольше 10 минут, только видимая вкладка.
 */
(function () {
  'use strict';

  var dialog = document.getElementById('vp-wall');
  if (!dialog) return;

  var POLL_EVERY = 3000;
  var POLL_FOR = 10 * 60 * 1000;
  var slug = dialog.getAttribute('data-variant') || '';
  var modal = typeof dialog.showModal === 'function';

  function track(name, props) {
    if (window.weco && window.weco.track) window.weco.track(name, props);
  }

  /* Сервер отрисовал окно открытым (`open`): без скрипта это блок на странице.
     ⚠️ На уже открытом <dialog> showModal() падает — сначала close(). */
  if (modal && dialog.hasAttribute('data-open')) {
    dialog.close();
    dialog.showModal();
  }

  /* Крестик и клик по подложке: закрыть и убрать ?wall из адреса. Без showModal
     крестик остаётся ссылкой на интро без параметра. */
  dialog.addEventListener('click', function (event) {
    if (!modal) return;
    if (event.target === dialog || event.target.closest('[data-close]')) {
      event.preventDefault();
      dialog.close();
    }
  });
  dialog.addEventListener('close', function () {
    /* Событие `close` приходит отложенно — и от переоткрытия выше тоже. Окно уже
       снова открыто — значит, его никто не закрывал. */
    if (dialog.open) return;
    var url = new URL(window.location.href);
    if (!url.searchParams.has('wall') && !url.searchParams.has('tg')) return;
    url.searchParams.delete('wall');
    url.searchParams.delete('tg');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
  });

  var tgScreen = dialog.querySelector('[data-screen="tg"]');
  var waitScreen = dialog.querySelector('[data-screen="waiting"]');
  var openForm = dialog.querySelector('form[data-tg-open]');
  var timer = null;
  var startedAt = 0;

  function reloadWall() {
    if (timer) window.clearInterval(timer);
    timer = null;
    window.location.replace(window.location.pathname + '?wall=1');
  }

  function tick() {
    if (Date.now() - startedAt > POLL_FOR) {
      window.clearInterval(timer);
      timer = null;
      return;
    }
    if (document.visibilityState !== 'visible') return;
    fetch(waitScreen.getAttribute('data-poll'), {
      credentials: 'same-origin', headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (state) {
      if (!state) return;
      /* Переход — только когда состояние стало другим, чем у экрана 02. */
      if (state.step !== 'contact' || state.tg === 'ok') {
        track('vp_wall_tg_ok', { variant: slug });
        reloadWall();
      } else if (state.tg === 'no_sub' || state.tg === 'error') {
        track('vp_wall_tg_nosub', { variant: slug, error: state.tg === 'error' });
        reloadWall();
      }
    }).catch(function () { /* сеть мигнула — следующий тик попробует ещё */ });
  }

  function poll() {
    if (!waitScreen || waitScreen.hidden || timer) return;
    startedAt = Date.now();
    timer = window.setInterval(tick, POLL_EVERY);
  }

  /* 01 → 02: форма уходит в новую вкладку (`target="_blank"`), окно остаётся
     здесь и ждёт «Старт». Разметка 02 уже на странице, скрыта. */
  if (openForm && tgScreen && waitScreen) {
    openForm.addEventListener('submit', function () {
      window.setTimeout(function () {
        tgScreen.hidden = true;
        waitScreen.hidden = false;
        poll();
      }, 0);
    });
  }

  poll();
})();
