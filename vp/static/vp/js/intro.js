/* Интро варианта: окно стены регистрации для гостя.
 *
 * ⚠️ ОКНО — ТОЛЬКО ВЕЖЛИВОЕ ОБЪЯСНЕНИЕ, А НЕ ЗАЩИТА. Стена стоит на сервере
 * (`vp.views.start`): без JS форма уйдёт туда и вернётся редиректом на
 * регистрацию. Здесь мы лишь перехватываем отправку, чтобы человек сначала
 * прочитал, зачем аккаунт.
 */
(function () {
  'use strict';

  var dialog = document.getElementById('vp-gate');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  var form = document.getElementById('vp-start-form');
  var button = form ? form.querySelector('button[type=submit]') : null;
  var variantNode = document.querySelector('[data-variant]');
  var variantSlug = variantNode ? variantNode.getAttribute('data-variant') : '';

  /* Аналитика: `weco.track` шлёт события на существующий /api/track/.
     Нет `weco` (заблокирован) - молча ничего, окно от этого не ломается. */
  function track(name, props) {
    if (window.weco && window.weco.track) window.weco.track(name, props);
  }

  function open() {
    dialog.showModal();
    track('vp_gate_shown', { variant: variantSlug });
  }

  if (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      open();
    });
  }

  /* Крестик и клик по подложке. Esc `<dialog>` обрабатывает сам. */
  dialog.addEventListener('click', function (event) {
    if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
  });

  /* Фокус возвращается на кнопку, с которой окно открыли. */
  dialog.addEventListener('close', function () {
    if (button) button.focus();
  });
})();
