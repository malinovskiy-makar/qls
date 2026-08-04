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

  window.attachMathfield = function (textarea) {
    if (!textarea || textarea.dataset.mathfieldReady === '1') { return; }
    textarea.dataset.mathfieldReady = '1';

    var panel = el('div', 'mf-panel');

    var toggle = el('button', 'mf-toggle', '∑ Формула');
    toggle.type = 'button';
    panel.appendChild(toggle);

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
    });

    textarea.parentNode.insertBefore(panel, textarea.nextSibling);
  };

  // Автоподключение ко всему, что помечено data-mathfield.
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('textarea[data-mathfield]')
      .forEach(window.attachMathfield);
  });
})();
