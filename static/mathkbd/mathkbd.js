/* Клавиатура формул — ОДНА на весь сайт (04.09.2026, ADR 0075).
 *
 * ⚠️ РАСКЛАДКА ПЕРЕНЕСЕНА ИЗ `calc2/static/calc2/82-input.js` ДОСЛОВНО.
 * Эталоном назначена клавиатура калькулятора: она обкатана на живых занятиях,
 * а в домашках стояли четыре ряда быстрых кнопок другого набора и другого
 * вида. «Заодно улучшить» раскладку при переносе было бы подменой задачи —
 * сравнение раскладок посимвольно держит тест
 * `problems/tests/test_mathkbd.py`.
 *
 * ⚠️ КЛАВИАТУРА НЕ ЗНАЕТ, КУДА ОНА ПИШЕТ. Между ней и полем стоит АДАПТЕР:
 *
 *     MathKbd.build(box, {
 *       insert(tex, txt, back),   // вставить кусок формулы
 *       deleteBack(),             // стереть символ
 *       clear(),                  // очистить поле
 *       piecewise: fn | null,     // «Кусочная функция»; null — кнопки не будет
 *     });
 *
 * В калькуляторе адаптер зовёт `insertIntoField`/`setFieldValue` и открывает
 * конструктор кусочной функции; в домашках — пишет в `<math-field>` и
 * вставляет заготовку `\begin{cases}`. Без адаптера этот файл пришлось бы
 * тащить вместе с половиной калькулятора.
 */
(function (global) {
  'use strict';

  /* ── Раскладка клавиатуры ─────────────────────────────────────────────
     Каждая клавиша: [подпись, вставка в набранном виде, вставка текстом,
     насколько отвести курсор назад в обычном поле].
     #@ — то, что выделено (или предыдущий кусок), #? — пустое место. */
  var MKBD_BASE = [
    [['7', '7'], ['8', '8'], ['9', '9'], ['(', '(', '(', 0], [')', ')', ')', 0]],
    [['4', '4'], ['5', '5'], ['6', '6'], ['×', '\\cdot ', '*'], ['÷', '\\frac{#@}{#?}', '/']],
    [['1', '1'], ['2', '2'], ['3', '3'], ['−', '-', '-'], ['+', '+', '+']],
    [['0', '0'], [',', '.', '.'], ['=', '=', '='], ['x²', '#@^2', '^2'], ['xⁿ', '#@^{#?}', '^(', 1]],
    /* П21. Один язык оформления в ряду. Было вперемешку: «×» и «÷» знаками,
       «дробь» и «стереть» словами, «⌫» иконкой. Знак действия рисуется знаком,
       а команда над полем называется словом — «дробь» это то же самое, что «÷»,
       и второй кнопки для неё не нужно. */
    [['xₙ', '#@_{#?}', '_'], ['√', '\\sqrt{#?}', 'sqrt()', 1], ['|x|', '\\left|#?\\right|', 'abs()', 1],
     ['⌫', 'DEL'], ['✕', 'CLEAR']],
  ];
  var MKBD_FUNCS = [
    ['Корни и модуль', [
      ['√', '\\sqrt{#?}', 'sqrt()', 1],
      ['ⁿ√', '\\sqrt[#?]{#@}', 'nthRoot(, )', 4],
      ['|x|', '\\left|#?\\right|', 'abs()', 1],
    ]],
    ['Степень и логарифм', [
      ['xⁿ', '#@^{#?}', '^(', 1],
      ['eˣ', '\\exponentialE^{#?}', 'exp()', 1],
      ['ln', '\\ln\\left(#?\\right)', 'log()', 1],
      ['log', '\\log_{#?}\\left(#?\\right)', 'log(, )', 4],
    ]],
    ['Тригонометрия', [
      ['sin', '\\sin\\left(#?\\right)', 'sin()', 1],
      ['cos', '\\cos\\left(#?\\right)', 'cos()', 1],
      ['tan', '\\tan\\left(#?\\right)', 'tan()', 1],
    ]],
    ['Сравнения', [
      ['<', '<', '<'], ['>', '>', '>'],
      ['≤', '\\le ', '<='], ['≥', '\\ge ', '>='], ['≠', '\\ne ', '!='],
    ]],
    ['Выбор', [
      ['min', '\\min\\left(#?,#?\\right)', 'min(, )', 3],
      ['max', '\\max\\left(#?,#?\\right)', 'max(, )', 3],
      ['если', '#?>#? ? #? : #?', ' ? : ', 3],
    ]],
  ];
  var MKBD_LETTERS = [
    ['Латинские буквы', 'abcdefghijklmnopqrstuvwxyz'.split('').map(function (ch) { return [ch, ch, ch]; })],
    ['Заглавные', 'ABCDEFGHIKLMNPQRSTVWXYZ'.split('').map(function (ch) { return [ch, ch, ch]; })],
    ['Греческие', [
      ['α', '\\alpha ', 'alpha'], ['β', '\\beta ', 'beta'], ['γ', '\\gamma ', 'gamma'],
      ['δ', '\\delta ', 'delta'], ['ε', '\\epsilon ', 'epsilon'], ['θ', '\\theta ', 'theta'],
      ['λ', '\\lambda ', 'lambda'], ['μ', '\\mu ', 'mu'], ['π', '\\pi ', 'pi'],
      ['ρ', '\\rho ', 'rho'], ['σ', '\\sigma ', 'sigma'], ['τ', '\\tau ', 'tau'],
      ['φ', '\\phi ', 'phi'], ['ω', '\\omega ', 'omega'], ['Δ', '\\Delta ', 'Delta'],
      ['Σ', '\\Sigma ', 'Sigma'],
    ]],
    ['Знаки', [
      ['∞', '\\infty ', 'Infinity'], ['%', '\\%', '%'],
      ['≈', '\\approx ', '=='],
    ]],
  ];

  /* Буквы, у которых подпись рисуется формулой, а не текстом.
   *
   * ⚠️ П23 РАЗБОРА ВЛАДЕЛЬЦА: «часть заглавных прямые, часть курсивные».
   * Причина была не в коде, а в шрифте: подпись печаталась обычным текстом,
   * и наклон зависел от того, есть ли у начертания интерфейсного шрифта
   * данная буква в курсиве. Теперь буквы рисует KaTeX — то есть все они
   * набраны математическим курсивом по построению, как в TeX. Смеси быть
   * не может.
   *
   * Цифры и знаки остаются текстом: они и в TeX прямые. */
  var MATH_LABEL_SECTIONS = { 'Латинские буквы': 1, 'Заглавные': 1, 'Греческие': 1 };

  function labelIsFormula(sectionLabel) {
    return MATH_LABEL_SECTIONS[sectionLabel] === 1;
  }

  /** Подпись клавиши: формулой через KaTeX или обычным текстом. */
  function paintLabel(button, key, asFormula) {
    /* Греческие подписываются своей КОМАНДОЙ (`\alpha`), латинские — самой
       буквой: у греческой в подписи стоит символ «α», а KaTeX его не
       понимает, ему нужна команда. Она лежит во втором поле ключа. */
    var tex = asFormula ? (/^[A-Za-z]$/.test(key[0]) ? key[0] : key[1]) : null;
    if (tex && global.katex && global.katex.renderToString) {
      try {
        /* ⚠️ `innerHTML` ЗДЕСЬ БЕЗОПАСЕН, И ВОТ ПОЧЕМУ. Во-первых, на вход
           идёт НЕ пользовательский текст: `tex` — это буква из раскладки
           выше, зашитой в этот файл, и другого источника у неё нет.
           Во-вторых, KaTeX по умолчанию работает с `trust: false` и сырую
           разметку не пропускает. Класть сюда что-либо из запроса или из
           поля ввода нельзя — тогда понадобится очистка. */
        button.innerHTML = global.katex.renderToString(String(tex).trim(), {
          throwOnError: false, displayMode: false,
        });
        return;
      } catch (e) { /* ниже — обычный текст */ }
    }
    /* ⚠️ ЗАПАСНОЙ ПУТЬ ОБЯЗАТЕЛЕН. KaTeX может не загрузиться; клавиатура
       без подписей бесполезна, а с текстовыми подписями — работает. */
    button.textContent = key[0];
  }

  function mkbdKey(key, adapter, sectionLabel) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'mk';
    paintLabel(b, key, labelIsFormula(sectionLabel));
    /* Знак без слова обязан называть себя доступному чтению: нативной
       подсказки на сайте нет (правило 18 части 4), а «⌫» и «✕» на слух не
       читаются. Буквы, нарисованные формулой, тоже подписываем: чтец экрана
       разметку KaTeX прочитает не так, как хочется. */
    if (key[1] === 'DEL') b.setAttribute('aria-label', 'Стереть символ');
    if (key[1] === 'CLEAR') b.setAttribute('aria-label', 'Очистить поле');
    if (labelIsFormula(sectionLabel)) b.setAttribute('aria-label', key[0]);
    if (key[0].length > 2) b.classList.add('fn');
    b.addEventListener('mousedown', function (e) { e.preventDefault(); }); // не терять фокус поля
    b.addEventListener('click', function () {
      if (key[1] === 'DEL') { adapter.deleteBack(); return; }
      if (key[1] === 'CLEAR') { adapter.clear(); return; }
      adapter.insert(key[1], key[2], key[3]);
    });
    return b;
  }

  /** Собрать клавиатуру в `box`. Три раздела, открыт один. */
  function build(box, adapter) {
    box.innerHTML = '';
    var tabs = document.createElement('div');
    tabs.className = 'mkbd-tabs';
    var panes = [];

    function fillRows(pane) {
      MKBD_BASE.forEach(function (row) {
        var r = document.createElement('div');
        r.className = 'mkbd-row';
        row.forEach(function (k) { r.appendChild(mkbdKey(k, adapter, null)); });
        pane.appendChild(r);
      });
    }

    function fillGroups(groups) {
      return function (pane) {
        groups.forEach(function (pair) {
          var label = pair[0], keys = pair[1];
          var l = document.createElement('div');
          l.className = 'mkbd-lab';
          l.textContent = label;
          var g = document.createElement('div');
          g.className = 'mkbd-grid';
          keys.forEach(function (k) { g.appendChild(mkbdKey(k, adapter, label)); });
          pane.appendChild(l);
          pane.appendChild(g);
        });
      };
    }

    var SECTIONS = [
      ['123', fillRows],
      ['Функции', fillGroups(MKBD_FUNCS)],
      ['Буквы', fillGroups(MKBD_LETTERS)],
    ];

    SECTIONS.forEach(function (pair, idx) {
      var name = pair[0], fill = pair[1];
      var t = document.createElement('button');
      t.type = 'button';
      t.className = 'mkbd-tab' + (idx === 0 ? ' active' : '');
      t.textContent = name;
      var pane = document.createElement('div');
      pane.className = 'mkbd-pane' + (idx === 0 ? ' active' : '');
      fill(pane);
      t.addEventListener('click', function () {
        tabs.querySelectorAll('.mkbd-tab').forEach(function (x) { x.classList.remove('active'); });
        panes.forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        pane.classList.add('active');
      });
      tabs.appendChild(t);
      panes.push(pane);
    });

    box.appendChild(tabs);
    panes.forEach(function (p) { box.appendChild(p); });

    /* Внизу — только вход в конструктор кусочной функции. Раздел «Примеры
       формул» убран: он повторял раздел «Функции», а вернуться из него
       обратно к клавиатуре было нечем. */
    if (adapter.piecewise) {
      var foot = document.createElement('div');
      foot.className = 'mkbd-foot';
      var pw = document.createElement('button');
      pw.type = 'button';
      pw.textContent = 'Кусочная функция';
      pw.addEventListener('click', function () { adapter.piecewise(); });
      foot.appendChild(pw);
      box.appendChild(foot);
    }
    return box;
  }

  /** Все подписи клавиш по разделам — для проб и тестов. */
  function labels() {
    var out = { '123': [], 'Функции': [], 'Буквы': [] };
    MKBD_BASE.forEach(function (row) {
      row.forEach(function (k) { out['123'].push(k[0]); });
    });
    MKBD_FUNCS.forEach(function (p) {
      p[1].forEach(function (k) { out['Функции'].push(k[0]); });
    });
    MKBD_LETTERS.forEach(function (p) {
      p[1].forEach(function (k) { out['Буквы'].push(k[0]); });
    });
    return out;
  }

  global.MathKbd = {
    build: build,
    labels: labels,
    BASE: MKBD_BASE,
    FUNCS: MKBD_FUNCS,
    LETTERS: MKBD_LETTERS,
  };
})(window);
