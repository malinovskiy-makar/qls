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
