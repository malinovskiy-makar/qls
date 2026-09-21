/*
 * Прохождение варианта «Высшей пробы» в браузере.
 *
 * Ванильный JS, без сборки. Один файл, разделы по порядку:
 *   1. ответы — чтение полей, «отвечено», плитки навигатора;
 *   2. «сейчас здесь» и переход к заданию;
 *   3. клавиатура: Enter ведёт по змейке вниз и НИКОГДА не сдаёт работу;
 *   4. шапка: высота, тема.
 * Автосохранение, таймер и сдача добавляются ниже своими разделами.
 *
 * ⚠️ Имена узлов задаёт `templates/vp/take.html` и `_take_item.html`:
 * `#vp-item-<n>`, `.vp-cell[data-n]`, поля `name="item-<n>"`.
 */
(function () {
  'use strict';

  var cfgNode = document.getElementById('vp-config');
  var form = document.getElementById('vp-form');
  if (!cfgNode || !form) { return; }
  var cfg = JSON.parse(cfgNode.textContent);

  function $(id) { return document.getElementById(id); }
  function card(n) { return document.getElementById('vp-item-' + n); }
  function cells(n) {
    return document.querySelectorAll('.vp-cell[data-n="' + n + '"]');
  }
  function itemOf(node) {
    var box = node && node.closest ? node.closest('.vp-item') : null;
    return box ? parseInt(box.dataset.n, 10) : null;
  }
  var reduceMotion = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var countNode = $('vp-answered');

  // =============================================================== 1. ответы
  /** Что сейчас введено в задании — в том виде, в каком это уходит на сервер. */
  function readValue(n) {
    var box = card(n);
    if (!box) { return null; }
    var kind = box.dataset.kind;
    if (kind === 'short_text') {
      var field = box.querySelector('input[type=text]');
      return field ? field.value.trim() : '';
    }
    if (kind === 'match') {
      var pairs = {};
      box.querySelectorAll('select[data-key]').forEach(function (select) {
        if (select.value !== '') { pairs[select.dataset.key] = parseInt(select.value, 10); }
      });
      return pairs;
    }
    var marked = box.querySelectorAll(
      'input[type=radio]:checked, input[type=checkbox]:checked');
    var values = Array.prototype.map.call(marked, function (input) {
      return parseInt(input.value, 10);
    });
    return kind === 'single' ? (values.length ? values[0] : null) : values;
  }

  /** «Отвечено» — как на сервере: пустая строка, пустой набор, ничего — не ответ. */
  function isAnswered(n) {
    var value = readValue(n);
    if (value === null || value === '') { return false; }
    if (Array.isArray(value)) { return value.length > 0; }
    if (typeof value === 'object') { return Object.keys(value).length > 0; }
    return true;
  }

  function missedNumbers() {
    return cfg.numbers.filter(function (n) { return !isAnswered(n); });
  }

  function recount() {
    if (countNode) { countNode.textContent = cfg.numbers.filter(isAnswered).length; }
  }

  function repaintAnswered(n) {
    var answered = isAnswered(n);
    cells(n).forEach(function (cell) { cell.classList.toggle('is-answered', answered); });
    recount();
  }

  // ============================================ 2. «сейчас здесь», переход
  var currentN = null;

  /** На телефоне плитки — полоса с прокруткой: текущую держим в поле зрения. */
  function keepCellVisible(n) {
    var strip = $('vp-strip');
    if (!strip || strip.offsetParent === null) { return; }
    var cell = strip.querySelector('.vp-cell[data-n="' + n + '"]');
    if (!cell) { return; }
    var offset = cell.getBoundingClientRect().left
      - strip.getBoundingClientRect().left + strip.scrollLeft;
    strip.scrollLeft = offset - (strip.clientWidth - cell.offsetWidth) / 2;
  }

  function setCurrent(n) {
    if (n === currentN) { return; }
    if (currentN !== null) {
      var old = card(currentN);
      if (old) { old.classList.remove('is-current'); }
      cells(currentN).forEach(function (cell) {
        cell.classList.remove('is-current');
        cell.removeAttribute('aria-current');
      });
    }
    currentN = n;
    if (n !== null) {
      card(n).classList.add('is-current');
      cells(n).forEach(function (cell) {
        cell.classList.add('is-current');
        cell.setAttribute('aria-current', 'true');
      });
      keepCellVisible(n);
    }
  }

  /** Переводит фокус в задание. block: 'nearest' (Enter) или 'center' (номер). */
  function focusItem(n, block) {
    var box = card(n);
    if (!box) { return; }
    var target = box.querySelector('input[type=text]')
      || box.querySelector('input[type=radio]:checked, input[type=checkbox]:checked')
      || box.querySelector('input[type=radio], input[type=checkbox], select');
    box.scrollIntoView({ block: block || 'nearest',
                         behavior: reduceMotion ? 'auto' : 'smooth' });
    if (target) { target.focus({ preventScroll: true }); }
  }

  // ========================================================== 3. клавиатура
  /** Enter ведёт по заданиям вниз (Shift+Enter — вверх): из поля змейки — в
   * следующее поле змейки, из последнего — в первое задание следующего блока.
   * Tab работает нативно: порядок фокуса совпадает с порядком заданий. */
  function moveFrom(n, direction) {
    var texts = cfg.textNumbers || [];
    var next = texts[texts.indexOf(n) + direction];
    if (next === undefined && direction > 0) {
      next = cfg.numbers[cfg.numbers.indexOf(n) + 1];   // змейка кончилась — дальше
    }
    if (next !== undefined) { focusItem(next, 'nearest'); }
  }

  form.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' || event.isComposing) { return; }
    var target = event.target;
    if (!(target && target.tagName === 'INPUT' && target.type === 'text')) { return; }
    event.preventDefault();               // Enter форму не отправляет, никогда
    var n = itemOf(target);
    if (n !== null) { moveFrom(n, event.shiftKey ? -1 : 1); }
  });

  form.addEventListener('focusin', function (event) {
    var n = itemOf(event.target);
    if (n !== null) { setCurrent(n); }
  });

  // Одна правка меняет сразу несколько индикаторов: поле, плитку навигатора,
  // общий счётчик (DESIGN 2.9).
  function onEdited(event) {
    var n = itemOf(event.target);
    if (n === null) { return; }
    repaintAnswered(n);
  }
  form.addEventListener('input', onEdited);
  form.addEventListener('change', onEdited);

  document.addEventListener('click', function (event) {
    var cell = event.target.closest ? event.target.closest('.vp-cell') : null;
    if (!cell) { return; }
    event.preventDefault();
    focusItem(parseInt(cell.dataset.n, 10), 'center');
  });

  // ============================================================== 4. шапка
  /** Высота липкой шапки — переменной: от неё зависят отступы прокрутки, чтобы
   * шапка не закрывала поле, в которое перешёл фокус. */
  function measureBar() {
    var bar = $('vp-bar');
    if (bar) {
      document.documentElement.style.setProperty('--vp-bar-h', bar.offsetHeight + 'px');
    }
  }
  window.addEventListener('resize', measureBar);
  if (window.ResizeObserver && $('vp-bar')) {
    new ResizeObserver(measureBar).observe($('vp-bar'));
  }

  // Переключатель темы: шапка сайта здесь спрятана, кнопка жмёт её скрытый
  // переключатель — реализация темы на сайте одна (`_theme_toggle.html`).
  var themeButton = $('vp-theme');
  function paintTheme() {
    if (themeButton) {
      themeButton.textContent =
        document.documentElement.getAttribute('data-theme') === 'dark' ? '☀' : '☾';
    }
  }
  if (themeButton) {
    themeButton.addEventListener('click', function () {
      var site = $('theme-toggle');
      if (site) { site.click(); }
      paintTheme();
    });
    paintTheme();
  }

  measureBar();
  recount();
})();
