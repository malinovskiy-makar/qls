/*
 * Поле ввода с формулами (MathLive) — общий компонент платформы.
 *
 * Нужен в трёх местах: условие своей задачи, «Моё решение» у ученика,
 * решалка. Поэтому он один, а не три похожих куска в трёх шаблонах.
 *
 * Как устроен смешанный ввод (обычный текст + формулы). MathLive — это поле
 * ДЛЯ ФОРМУЛЫ, целый абзац с текстом в него не наберёшь. Поэтому основной
 * ввод остаётся обычной textarea (её содержимое и уходит на сервер), а
 * MathLive работает как «вставщик формул»: набрал формулу в маленьком поле,
 * нажал «Вставить» — в textarea на позицию курсора легло $...$.
 *
 * Так сохраняется главное свойство: в базе лежит ровно тот же формат, что у
 * всех задач банка — текст с формулами в долларах, который рендерит KaTeX.
 * Никакого второго формата хранения не заводится.
 *
 * Наружу торчит одна функция: window.attachMathfield(textarea).
 */
(function () {
  'use strict';

  // Шрифты и звуки MathLive. Адрес папки приходит из шаблона
  // (window.MATHLIVE_DIR, см. _mathfield.html): писать /static/ руками
  // нельзя — на бою у файлов имена с хешем. Звуки клавиш выключены.
  try {
    var MFE = window.MathfieldElement;
    if (MFE) {
      MFE.fontsDirectory = (window.MATHLIVE_DIR || '') + '/fonts';
      MFE.soundsDirectory = null;
    }
  } catch (e) {}

  // Кнопки быстрой вставки. Ориентир — набор IEO (дроби, степени, индексы,
  // корни, скобки, сравнения, греческие), плюс то, без чего не обойтись
  // в экономике: процент, стрелки сдвига кривых, Q_d / Q_s / P_e.
  var QUICK = [
    { group: 'Основное', items: [
      { label: '×', latex: '\\times' },
      { label: '÷', latex: '\\div' },
      { label: '±', latex: '\\pm' },
      { label: '%', latex: '\\%' },
      { label: 'a/b', latex: '\\frac{#0}{#?}' },
      { label: 'x²', latex: '#0^{#?}' },
      { label: 'xₙ', latex: '#0_{#?}' },
      { label: '√', latex: '\\sqrt{#0}' },
      { label: '( )', latex: '\\left(#0\\right)' },
    ]},
    { group: 'Сравнения', items: [
      { label: '≤', latex: '\\le' },
      { label: '≥', latex: '\\ge' },
      { label: '≠', latex: '\\ne' },
      { label: '≈', latex: '\\approx' },
      { label: '→', latex: '\\to' },
      { label: '↑', latex: '\\uparrow' },
      { label: '↓', latex: '\\downarrow' },
    ]},
    { group: 'Экономика', items: [
      { label: 'Q_d', latex: 'Q_d' },
      { label: 'Q_s', latex: 'Q_s' },
      { label: 'P_e', latex: 'P_e' },
      { label: 'Q_e', latex: 'Q_e' },
      { label: 'TR', latex: 'TR' },
      { label: 'MC', latex: 'MC' },
      { label: 'MR', latex: 'MR' },
      { label: 'E_p', latex: 'E_p' },
      { label: 'Δ', latex: '\\Delta' },
    ]},
    { group: 'Греческие', items: [
      { label: 'α', latex: '\\alpha' },
      { label: 'β', latex: '\\beta' },
      { label: 'π', latex: '\\pi' },
      { label: 'σ', latex: '\\sigma' },
      { label: 'λ', latex: '\\lambda' },
      { label: 'μ', latex: '\\mu' },
    ]},
  ];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function insertAtCursor(textarea, snippet) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    var value = textarea.value;
    textarea.value = value.slice(0, start) + snippet + value.slice(end);
    var caret = start + snippet.length;
    textarea.setSelectionRange(caret, caret);
    textarea.focus();
    // Живой предпросмотр слушает 'input' — событие надо послать руками,
    // программная запись в value его не порождает.
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  /* ── Живой предпросмотр ───────────────────────────────────────────────
   *
   * ⚠️ Вставленная формула ОБЯЗАНА сразу выглядеть формулой. Без этого
   * ученик видит в поле «$\frac{TR}{Q}$» и не понимает, вставилось ли то,
   * что он набирал: на экране проверки у преподавателя формула собрана, а
   * в момент ввода — доллары и слэши.
   *
   * Почему предпросмотр ПОД полем, а не рендер поверх редактируемого
   * текста: «поверх» — это отказ от textarea в пользу contenteditable, а
   * с ним уезжают выделение, отмена, автосохранение по `input` и
   * мобильная клавиатура. Цена не сопоставима с выигрышем; отдельная
   * строка «как это будет выглядеть» решает ту же задачу и не ломает
   * ввод. Ориентир IEO — там формула тоже показана собранной рядом.
   */
  function renderPreview(node, text) {
    if (!text.trim()) {
      node.hidden = true;
      return;
    }
    node.hidden = false;
    node.textContent = text;
    if (typeof maskEscapedDollars === 'function') { maskEscapedDollars(node); }
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(node, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false }
        ],
        throwOnError: false
      });
    }
    if (typeof fixCurrencyDollars === 'function') { fixCurrencyDollars(node); }
  }

  window.attachMathfield = function (textarea) {
    if (!textarea || textarea.dataset.mathfieldReady === '1') { return; }
    textarea.dataset.mathfieldReady = '1';

    // Предпросмотр можно выключить: у редактора своей задачи уже есть
    // большая колонка «Так увидит ученик», и вторая строка под полем была
    // бы тем же самым дважды.
    var wantPreview = textarea.dataset.mathfieldPreview !== '0';
    var preview = el('div', 'mf-preview');
    preview.hidden = true;
    if (wantPreview) {
      textarea.parentNode.insertBefore(preview, textarea.nextSibling);
    }

    var previewTimer = null;
    function schedulePreview() {
      if (!wantPreview) { return; }
      clearTimeout(previewTimer);
      // Полторы десятых секунды: рендерить на каждую букву незачем, а
      // ждать дольше — предпросмотр начинает «отставать» от набора.
      previewTimer = setTimeout(function () {
        renderPreview(preview, textarea.value || '');
      }, 150);
    }
    textarea.addEventListener('input', schedulePreview);
    if (wantPreview) { renderPreview(preview, textarea.value || ''); }

    var panel = el('div', 'mf-panel');

    // ⚠️ КНОПКА ФОРМУЛЫ МОЖЕТ ЖИТЬ В ЧУЖОМ РЯДУ (обзор 13.08, п. 69).
    // У редактора своей задачи под полем условия уже стоят две кнопки про
    // графики, и эта отдельной строкой ниже выглядела четвёртым разным
    // объектом. Поле само указывает, куда её положить:
    // `data-mathfield-tools="#statement-tools"`. Тело панели остаётся на
    // своём месте — раскрывается под полем, как и раньше.
    // ⚠️ НАЗВАНА В ОДНОЙ ГРАММАТИКЕ С СОСЕДЯМИ (визуальная сессия 17.08,
    // п. 2.7): все три начинаются с глагола и говорят, что произойдёт.
    // Знак суммы убран: это не «сумма», а любая формула.
    var toggle = el('button', 'mf-toggle', 'Вставить формулу');
    toggle.type = 'button';
    var toolsSelector = textarea.getAttribute('data-mathfield-tools');
    var tools = toolsSelector ? document.querySelector(toolsSelector) : null;
    if (tools) {
      // В чужом ряду кнопка обязана выглядеть как соседи: класс набора.
      toggle.className += ' k-btn k-btn--plain k-btn--sm';
      // ⚠️ ПОРЯДОК В РЯДУ: сначала то, что вставляется В ТЕКСТ, и только
      // потом то, что уводит на другой экран (визуальная сессия 17.08,
      // п. 2.7). Кнопка приезжает скриптом и `appendChild` ставил бы её
      // ЗА ссылкой «Создать график ↗», разрывая пару «Вставить … / Вставить …».
      var outgoing = tools.querySelector('a');
      if (outgoing) { tools.insertBefore(toggle, outgoing); }
      else { tools.appendChild(toggle); }
    } else {
      panel.appendChild(toggle);
    }

    var body = el('div', 'mf-body');
    body.hidden = true;
    panel.appendChild(body);

    var field = document.createElement('math-field');
    field.className = 'mf-field';
    // Виртуальную клавиатуру показываем по нажатию на поле — на телефоне
    // системная клавиатура формулу не наберёт.
    field.setAttribute('math-virtual-keyboard-policy', 'manual');
    body.appendChild(field);

    var row = el('div', 'mf-row');
    var insert = el('button', 'mf-insert', 'Вставить в текст');
    insert.type = 'button';
    var keyboard = el('button', 'mf-kbd', '⌨ Клавиатура');
    keyboard.type = 'button';
    var hint = el('span', 'mf-hint',
      'Формула вставится как $…$ на место курсора.');
    row.appendChild(insert);
    row.appendChild(keyboard);
    row.appendChild(hint);
    body.appendChild(row);

    QUICK.forEach(function (block) {
      var group = el('div', 'mf-group');
      group.appendChild(el('span', 'mf-group-name', block.group));
      block.items.forEach(function (item) {
        var button = el('button', 'mf-key', item.label);
        button.type = 'button';
        button.addEventListener('click', function () {
          field.executeCommand(['insert', item.latex]);
          field.focus();
        });
        group.appendChild(button);
      });
      body.appendChild(group);
    });

    toggle.addEventListener('click', function () {
      body.hidden = !body.hidden;
      if (!body.hidden) { field.focus(); }
    });

    keyboard.addEventListener('click', function () {
      if (window.mathVirtualKeyboard) {
        window.mathVirtualKeyboard.visible =
          !window.mathVirtualKeyboard.visible;
      }
    });

    insert.addEventListener('click', function () {
      var latex = (field.value || '').trim();
      if (!latex) { return; }
      insertAtCursor(textarea, '$' + latex + '$');
      field.value = '';
      // Вставка — единственный момент, когда ждать 150 мс незачем: ученик
      // нажал кнопку и смотрит на результат прямо сейчас.
      clearTimeout(previewTimer);
      if (wantPreview) { renderPreview(preview, textarea.value || ''); }
    });

    var anchor = wantPreview ? preview : textarea;
    anchor.parentNode.insertBefore(panel, anchor.nextSibling);
  };

  // Автоподключение ко всему, что помечено data-mathfield.
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('textarea[data-mathfield]')
      .forEach(window.attachMathfield);
  });
})();
