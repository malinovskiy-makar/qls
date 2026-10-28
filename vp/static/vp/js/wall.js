/* Окно стены 2 тура на интро (docs/VP.md, «Стена 2 тура»).
 *
 * ⚠️ ОКНО РАБОТАЕТ И БЕЗ ЭТОГО СКРИПТА: экран выбирает сервер, каждое действие —
 * обычная форма POST с редиректом обратно на `?wall=…`. Скрипт только:
 * 1) делает отрисованное открытым окно модальным;
 * 2) после «Подключить Telegram» переключает 01 на 02 без перезагрузки;
 * 3) опрашивает `wall/state` и перезагружает окно, когда состояние изменилось.
 *
 * ⚠️ ОПРОС НА 02 – ДО ЛЮБОГО ОТВЕТА БОТА (подписка есть, подписки нет, ошибка);
 * НА 03 («осталось подписаться», `data-poll-ok-only` на окне) – ТОЛЬКО ДО
 * ПОДТВЕРЖДЁННОЙ ПОДПИСКИ. Бот после «Проверить» обещает, что вкладка обновится сама,
 * поэтому на 03 опрос нужен. Но уходить с 03 на `no_sub` нельзя: перезагрузка снова
 * покажет 03, и страница ходила бы по кругу. Решение «уходить или нет» – чистая
 * функция `vpWallLeave`, её таблица проверяется через node (vp/tests/test_wall_js.py).
 * Каждые 3 с на 02 и 5 с на 03, не дольше 10 минут, только видимая вкладка.
 */
/* Что делать с ответом `wall/state`: 'ok' – уходить (стена пройдена или путь Telegram
   подтверждён), 'nosub' – уходить на экран 03 (только с 02), null – остаться. */
function vpWallLeave(okOnly, state) {
  if (!state) return null;
  if (state.step !== 'contact' || state.tg === 'ok') return 'ok';
  if (!okOnly && (state.tg === 'no_sub' || state.tg === 'error')) return 'nosub';
  return null;
}
if (typeof module !== 'undefined' && module.exports) module.exports = { vpWallLeave: vpWallLeave };

(function () {
  'use strict';

  if (typeof document === 'undefined') return;
  var dialog = document.getElementById('vp-wall');
  if (!dialog) return;

  var POLL_EVERY = 3000;
  var POLL_EVERY_OK_ONLY = 5000;
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
  /* Что опрашиваем: скрытый до «Старт» экран 02 или (на 03) само окно. */
  var okOnly = dialog.hasAttribute('data-poll-ok-only');
  var pollUrl = okOnly ? dialog.getAttribute('data-poll') : (waitScreen && waitScreen.getAttribute('data-poll'));
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
    fetch(pollUrl, {
      credentials: 'same-origin', headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (state) {
      if (!state) return;
      var leave = vpWallLeave(okOnly, state);
      if (leave === 'ok') {
        track('vp_wall_tg_ok', { variant: slug });
        reloadWall();
      } else if (leave === 'nosub') {
        track('vp_wall_tg_nosub', { variant: slug, error: state.tg === 'error' });
        reloadWall();
      }
    }).catch(function () { /* сеть мигнула — следующий тик попробует ещё */ });
  }

  function poll() {
    if (!pollUrl || timer) return;
    if (!okOnly && waitScreen.hidden) return;
    startedAt = Date.now();
    timer = window.setInterval(tick, okOnly ? POLL_EVERY_OK_ONLY : POLL_EVERY);
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
