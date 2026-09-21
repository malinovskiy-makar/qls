/* События аналитики ВП: отдаёт то, что посчитал сервер (`vp/tracking.py`), в `weco.track`.
 *
 * Свой эндпоинт не заведён: `weco.track` (static/track.js) копит события и шлёт их на
 * существующий /api/track/. Скрипт `track.js` сайта подключён ПОСЛЕ этого (он в конце
 * страницы), поэтому `weco` в момент запуска ещё может не быть — ждём его коротко.
 * Нет `weco` совсем (заблокирован) — события просто не уходят, страница работает.
 */
(function () {
  'use strict';
  var node = document.getElementById('vp-events');
  if (!node) return;
  var events;
  try { events = JSON.parse(node.textContent); } catch (error) { return; }
  if (!Array.isArray(events)) return;

  var tries = 0;
  function send() {
    if (window.weco && window.weco.track) {
      events.forEach(function (item) { window.weco.track(item.name, item.props || {}); });
    } else if (tries++ < 40) {
      window.setTimeout(send, 100);
    }
  }
  send();
})();
