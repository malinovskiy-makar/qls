// Ввод формул: кусочные функции, MathLive, виртуальная клавиатура.
/* ── Красивая математика в подсказках и предпросмотре (Фаза 4б) ──────────
   Поле ввода остаётся обычным текстом с синтаксисом Math.js: считается ровно
   то, что написано. Меняется только то, что человек видит рядом.

   Перевод в LaTeX делает сам Math.js — у разобранного дерева есть toTex().
   Это надёжнее самодельных замен: степени, дроби, корни и функции он знает
   лучше любой регулярки, и второй библиотеки не нужно. Пока формула
   недописана («100 - »), разбор падает — тогда работает запасной грубый
   перевод, чтобы предпросмотр не мигал пустотой на каждой букве. */
function texFallback(expr) {
  return String(expr)
    .replace(/\bsqrt\(([^()]*)\)/g, '\\sqrt{$1}')
    .replace(/\^(\w+)/g, '^{$1}')
    .replace(/\*/g, '\\cdot ')
    .replace(/<=/g, '\\le ').replace(/>=/g, '\\ge ');
}
function mathToTex(expr) {
  const s = String(expr || '').trim();
  if (!s) return '';
  try { return math.parse(s).toTex({ parenthesis: 'auto' }); }
  catch (e) { return texFallback(s); }
}
// Отрисовать формулу в элемент. Без KaTeX (CDN недоступен) показываем исходный
// текст — предпросмотр деградирует, но ничего не ломается.
function renderTex(el, expr) {
  if (!el) return;
  const tex = mathToTex(expr);
  if (!tex) { el.textContent = ''; el.classList.remove('has'); return; }
  el.classList.add('has');
  if (typeof katex === 'undefined') { el.textContent = expr; return; }
  if (!katexInto(el, tex)) el.textContent = expr;
}
// То же, но на вход уже готовый LaTeX (кусочная функция собирается сразу в него).
function renderTexRaw(el, tex) {
  if (!el) return;
  if (!tex) { el.textContent = ''; el.classList.remove('has'); return; }
  el.classList.add('has');
  if (typeof katex === 'undefined') { el.textContent = tex; return; }
  if (!katexInto(el, tex)) el.textContent = tex;
}
// KaTeX подгружается отложенно — когда доедет, перерисовываем то, что уже на экране.
const _texPending = [];
function onKatexReady() { _texPending.forEach(fn => { try { fn(); } catch (e) {} }); }

/* Подсказка формата формулы (Фаза 4а). Карточка под полем: заголовок, сетка
   примеров (каждый — набранная формула + за что её берут) и строка о синтаксисе.
   Пример кликабелен: подставляется в поле, считать заново руками не нужно. */
/* Как называется переменная в поле каждого вида: конструктор кусочной функции
   должен писать условие в тех же буквах, что и сама формула. */
const FORMULA_VAR = { PQ: 'Q', QP: 'P', TC: 'Q', PROD: 'L', PPF: 'X', MATHF: 'x', ISO: 'L', UTIL: 'x',
  DEMAND: 'Q', SUPPLY: 'Q', MC: 'Q', ATC: 'Q', MACRO: 'Y', MATHY: 'y', MATHAB: 'a' };

/* ── Конструктор кусочной функции ──────────────────────────────────────
   Движок понимает кусочную запись через условие «услвие ? то : иначе» и
   вложенные условия, но набирать её руками неудобно. Здесь спрашиваем число
   кусков и собираем ту же запись из отдельных полей. */
/* ── Кусочная функция (Фаза 5) ────────────────────────────────────────
   У каждого куска ДВЕ границы: «от» и «до». Пустая левая граница у первого
   куска означает «от нуля», пустая правая у последнего — «и дальше».
   Для движка собирается цепочка условий, для показа — одна фигурная скобка
   на всю функцию (LaTeX cases), которую MathLive умеет и рисовать, и править. */
const PW = { inp: null, v: 'Q', n: 2, rows: [] };

// Условие одного куска для Math.js: «от a до b» с учётом пустых границ.
function pwCond(v, a, b, last) {
  const parts = [];
  if (a !== '') parts.push(v + ' >= ' + a);
  // У последнего куска правая граница по умолчанию открыта: он и есть «иначе».
  if (b !== '') parts.push(v + ' < ' + b);
  if (!parts.length) return '';
  return parts.length === 1 ? parts[0] : '(' + parts.join(' and ') + ')';
}

function pwRows() {
  const out = [];
  for (let i = 0; i < PW.n; i++) {
    const r = PW.rows[i] || {};
    out.push({ f: String(r.f || '').trim(), a: String(r.a || '').trim(), b: String(r.b || '').trim() });
  }
  return out;
}

function pwFormula() {
  const rows = pwRows();
  const v = pwVar();       // условие пишем той же буквой, что и сами куски
  // Идём с конца: последний кусок без условия становится веткой «иначе».
  let out = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    const f = rows[i].f || '0';
    const cond = pwCond(v, rows[i].a, rows[i].b, i === rows.length - 1);
    if (out === null) { out = cond ? (cond + ' ? ' + f + ' : NaN') : f; continue; }
    if (!cond) { out = f; continue; }              // кусок без границ перекрывает всё ниже
    const tail = out.indexOf('?') >= 0 ? '(' + out + ')' : out;
    out = cond + ' ? ' + f + ' : ' + tail;
  }
  return out || '0';
}

/* Та же запись одной фигурной скобкой — это и предпросмотр, и то, что уходит в
   поле. Перед условием стоит «если»: без него формула и участок слипались в
   одну строку и читались как продолжение друг друга. */
function pwLatex() {
  const rows = pwRows();
  const v = pwVar();
  const lines = rows.map(r => {
    const f = mathToTex(r.f || '0');
    let cond;
    if (r.a !== '' && r.b !== '') cond = mathToTex(r.a) + ' \\le ' + v + ' < ' + mathToTex(r.b);
    else if (r.a !== '') cond = v + ' \\ge ' + mathToTex(r.a);
    else if (r.b !== '') cond = v + ' < ' + mathToTex(r.b);
    // Запятая стоит ПОСЛЕ формулы, перед «если»: так читается «сто минус Q,
    // если Q меньше сорока». Раньше её не было вовсе, и формула с условием
    // слипались в одну строку.
    else return f + ', & \\text{иначе}';
    return f + ', & \\text{если } ' + cond;
  });
  return '\\begin{cases}' + lines.join('\\\\') + '\\end{cases}';
}

/* Какой буквой писать условие. По умолчанию берём переменную поля, но если в
   формулах кусков пользователь пишет ту же букву в другом регистре («x» там,
   где поле ждёт «X»), условие идёт за ним: иначе в одной строке оказывались
   и x, и X, и это читалось как две разные величины. */
function pwVar() {
  const want = PW.v;
  const alt = new RegExp('(?:^|[^A-Za-z0-9_])(' + want.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')(?![A-Za-z0-9_])', 'i');
  for (const r of pwRows()) {
    const m = alt.exec(r.f || '');
    if (m && m[1] !== want) return m[1];
  }
  return want;
}

/* Разбор одной фигурной скобки обратно в выражение Math.js. Нужен и для
   того, что собрал конструктор, и для того, что Math.js сам печатает через
   toTex, — поэтому понимаем оба вида условия: «a ≤ Q < b» и «если …». */
function casesToMath(body) {
  const rows = body.split(/\\\\/);
  const parts = [];
  rows.forEach(row => {
    if (!row.trim()) return;
    const cells = row.split('&');
    // Запятая после формулы — часть записи «сто минус Q, если …», а не часть
    // выражения: перед разбором её убираем.
    const expr = latexToMath(cells[0] || '').trim().replace(/,\s*$/, '');
    let cond = cells.length > 1 ? cells.slice(1).join('&') : '';
    cond = cond.replace(/\\quad|\\;|\\,/g, ' ')
               .replace(/\\text\{[^}]*\}/g, (m) => (/иначе|otherwise/i.test(m) ? ' ELSE' : ' '))
               .replace(/\\mathrm\{[^}]*\}/g, ' ');
    if (cond.indexOf(' ELSE') >= 0) cond = '';
    cond = latexToMath(cond).replace(/[{}]/g, '').trim();
    parts.push({ expr: expr || '0', cond: condToMath(cond) });
  });
  if (!parts.length) return '';
  let out = null;
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (out === null) { out = p.cond ? (p.cond + ' ? ' + p.expr + ' : NaN') : p.expr; continue; }
    if (!p.cond) { out = p.expr; continue; }
    const tail = out.indexOf('?') >= 0 ? '(' + out + ')' : out;
    out = p.cond + ' ? ' + p.expr + ' : ' + tail;
  }
  return out;
}

// Двойное неравенство «a ≤ Q < b» Math.js не понимает — разворачиваем в «и».
function condToMath(t) {
  const s = String(t || '').trim();
  if (!s) return '';
  const m = /^(.+?)\s*(<=|<)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|<)\s*(.+)$/.exec(s);
  if (m) {
    const lo = (m[2] === '<=') ? '>=' : '>';
    return '(' + m[3] + ' ' + lo + ' ' + m[1].trim() + ' and ' + m[3] + ' ' + m[4] + ' ' + m[5].trim() + ')';
  }
  return s;
}

function renderPw() {
  const cnt = document.getElementById('pw-count');
  if (cnt && document.activeElement !== cnt) cnt.value = PW.n;
  while (PW.rows.length < PW.n) PW.rows.push({ f: '', a: '', b: '' });
  const box = document.getElementById('pw-rows');
  if (box) {
    box.innerHTML = '';
    for (let i = 0; i < PW.n; i++) {
      const row = document.createElement('div');
      row.className = 'pw-row';
      // Формула куска набирается тем же движком, что и в панели: пользователь
      // пишет 0.5*x и сразу видит точку умножения, дробь рисуется дробью.
      const slot = document.createElement('div');
      slot.className = 'f-slot';
      const f = document.createElement('input');
      f.type = 'text'; f.value = PW.rows[i].f; f.placeholder = 'Формула куска';
      f.setAttribute('aria-label', 'Формула куска ' + (i + 1));
      f.addEventListener('input', () => { PW.rows[i].f = f.value; pwPreview(); });
      slot.appendChild(f);
      const from = document.createElement('span'); from.className = 'pw-when'; from.textContent = 'От';
      const a = document.createElement('input');
      a.type = 'text'; a.className = 'pw-bound'; a.value = PW.rows[i].a;
      a.placeholder = i === 0 ? '0' : '';
      a.setAttribute('aria-label', 'Начало участка ' + (i + 1));
      a.addEventListener('input', () => { PW.rows[i].a = a.value; pwPreview(); });
      const to = document.createElement('span'); to.className = 'pw-when'; to.textContent = 'До';
      const b = document.createElement('input');
      b.type = 'text'; b.className = 'pw-bound'; b.value = PW.rows[i].b;
      b.placeholder = i === PW.n - 1 ? '∞' : '';
      b.setAttribute('aria-label', 'Конец участка ' + (i + 1));
      b.addEventListener('input', () => { PW.rows[i].b = b.value; pwPreview(); });
      row.append(slot, from, a, to, b);
      box.appendChild(row);
      upgradeFormulaField(f);
      // Клавиатура переезжает в ту строку, где стоит курсор (Фаза 7).
      const focusRow = () => pwAttachKeyboard(row, f);
      f.addEventListener('focus', focusRow);
      if (f._mf) f._mf.addEventListener('focusin', focusRow);
      if (i === 0) focusRow();
    }
  }
  pwPreview();
}

/* Одна кнопка клавиатуры на весь редактор: она переезжает к строке, в которой
   стоит курсор. Пять иконок на пять кусков читались как пять разных настроек,
   хотя клавиатура нужна ровно одной строке за раз. */
function pwAttachKeyboard(row, inp) {
  const kbd = document.getElementById('pw-kbd');
  if (!kbd) return;
  let btn = document.getElementById('pw-kbd-btn');
  if (!btn) {
    btn = document.createElement('button');
    btn.type = 'button'; btn.id = 'pw-kbd-btn'; btn.className = 'f-help f-kbd';
    btn.title = 'Клавиатура';
    btn.setAttribute('aria-label', 'Открыть математическую клавиатуру');
    btn.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
      + ' stroke-width="1.8" stroke-linecap="round"><rect x="2.5" y="6" width="19" height="12" rx="2"/>'
      + '<path d="M6 9.5h.01M9.5 9.5h.01M13 9.5h.01M16.5 9.5h.01M6 12.8h.01M9.5 12.8h.01M13 12.8h.01M16.5 12.8h.01"/>'
      + '<path d="M8.2 15.6h7.6"/></svg>';
    btn.addEventListener('click', () => {
      const open = kbd.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open && btn._inp) buildKeyboard(kbd, btn._inp);
    });
  }
  if (btn.parentElement !== row) row.appendChild(btn);
  btn._inp = inp;
  if (kbd.classList.contains('open')) buildKeyboard(kbd, inp);
}

function pwPreview() {
  const prev = document.getElementById('pw-preview');
  if (prev) renderTexRaw(prev, pwLatex());
}

function openPiecewise(inp, v) {
  PW.inp = inp; PW.v = v || 'Q';
  if (!PW.rows.length) {
    PW.rows = [{ f: '100 - ' + PW.v, a: '0', b: '40' }, { f: '80 - 0.5*' + PW.v, a: '40', b: '' }];
  }
  const m = document.getElementById('pw-modal');
  if (!m) return;
  // Окно открываем ДО сборки полей: MathLive, собранный внутри inert-подложки,
  // остаётся без обработчика клавиш и потом не печатается.
  m.classList.add('open'); m.removeAttribute('inert');
  renderPw();
  const first = m.querySelector('.pw-row math-field, .pw-row input');
  if (first) { if (first.focusField) first.focusField(); else first.focus(); }
}
function closePiecewise() {
  const m = document.getElementById('pw-modal');
  if (!m) return;
  m.classList.remove('open'); m.setAttribute('inert', '');
}

/* Вставка кусочка формулы туда, где стоит курсор. Поле не очищается, поэтому
   формулу можно набирать кнопками по частям. back — на сколько символов увести
   курсор назад, чтобы он оказался внутри только что поставленных скобок. */
function insertIntoFormula(inp, text, back) {
  if (!inp) return;
  const s = inp.selectionStart == null ? inp.value.length : inp.selectionStart;
  const e = inp.selectionEnd == null ? s : inp.selectionEnd;
  inp.value = inp.value.slice(0, s) + text + inp.value.slice(e);
  const caret = s + text.length - (back || 0);
  inp.dispatchEvent(new Event('input', { bubbles: true }));   // предпросмотр и слушатели поля
  inp.focus();
  try { inp.setSelectionRange(caret, caret); } catch (err) { /* поле без выделения */ }
}

/* =====================================================================
   ФАЗА 4. МАТЕМАТИЧЕСКИЙ ВВОД
   Поле формулы должно вести себя так же, как в Desmos или GeoGebra:
   напечатал слэш — увидел дробь, крышку — степень, подчёркивание — индекс.
   Этим занимается MathLive.

   Устройство. Обычный <input> остаётся в разметке и остаётся источником
   правды: в нём лежит текст для Math.js, и весь остальной код по-прежнему
   читает и пишет именно его. Рядом появляется <math-field>, который
   показывает ту же формулу набранной и правится мышью и клавиатурой.
   Два поля синхронизируются в обе стороны. Если MathLive не загрузился,
   input просто остаётся видимым — калькулятор работает как раньше.
   ===================================================================== */

let MATHLIVE_READY = false;
const _mfPending = [];      // поля, которые ждут загрузки библиотеки

// Класс поля берём из глобали библиотеки: UMD-сборка кладёт его и напрямую,
// и внутрь window.MathLive — какой путь сработает, зависит от сборки.
function mathfieldClass() {
  return window.MathfieldElement || (window.MathLive && window.MathLive.MathfieldElement) || null;
}

function onMathliveReady() {
  const MF = mathfieldClass();
  if (!MF) return;
  window.MathfieldElement = MF;
  MATHLIVE_READY = true;
  const V = '0.110.0';
  try {
    MF.fontsDirectory = 'https://cdn.jsdelivr.net/npm/mathlive@' + V + '/fonts';
    MF.soundsDirectory = null;   // щелчки клавиш здесь только мешают
  } catch (e) {}
  // Своя клавиатура рисуется в панели, встроенная всплывать не должна.
  try { window.mathVirtualKeyboard.visible = false; } catch (e) {}
  _mfPending.splice(0).forEach(fn => { try { fn(); } catch (e) { console.warn(e); } });
  flushMathfields();
}

/* ── Перевод набранной формулы в выражение Math.js ────────────────────
   MathLive хранит LaTeX, движок считает через Math.js. Разбираем ровно то,
   что реально может появиться в наших полях; всё незнакомое оставляем как
   есть, чтобы человек увидел свою запись, а не молчаливую потерю куска. */
const TEX_FUNCS = ['sin', 'cos', 'tan', 'cot', 'arcsin', 'arccos', 'arctan',
  'ln', 'log', 'exp', 'min', 'max', 'abs', 'sqrt'];
const TEX_GREEK = { alpha: 'alpha', beta: 'beta', gamma: 'gamma', delta: 'delta',
  epsilon: 'epsilon', theta: 'theta', lambda: 'lambda', mu: 'mu', pi: 'pi',
  rho: 'rho', sigma: 'sigma', tau: 'tau', phi: 'phi', omega: 'omega',
  Delta: 'Delta', Sigma: 'Sigma', Omega: 'Omega' };

/* П16. ОШИБКА СТОИТ У ТОГО ПОЛЯ, ГДЕ ВОЗНИКЛА, И НЕ СДВИГАЕТ МАКЕТ.

   Канон 2.4: три носителя сразу — линия, цвет и фраза; фраза называет
   ТРЕБОВАНИЕ, а не диагноз, и встаёт В ТУ ЖЕ СТРОКУ. Прежде красный текст про
   пустое поле печатался в общий блок ошибок наверху панели: он относился к
   одному полю, а стоял у другого, и появление фразы двигало вниз всё, что под
   ней. Место под фразу занято ВСЕГДА (пустая строка той же высоты) — тот же
   приём, что у кнопки возврата масштаба в подфазе 3b. */
function fieldProblem(inp, msg) {
  if (!inp) return;
  /* ⚠️ МЕСТО ПОД СООБЩЕНИЕ ЛЕЖИТ ПОД ВСЕЙ СТРОКОЙ, А НЕ ВНУТРИ ПОЛЯ.

     Замер: кнопка клавиатуры была 58,8 px при поле 40,8. Разница ровно в это
     место — 16 px плюс 2 отступа. Причина: резерв клался в тот же блок, что и
     поле, а строка выравнивает детей по высоте (`align-items: stretch`), и
     кнопка честно повторяла высоту соседа вместе с невидимым резервом.

     Сам резерв убирать нельзя: он держит вёрстку от прыжка, когда сообщение
     появится. Поэтому он переезжает НАРУЖУ строки — под неё. На экране
     сообщение остаётся там же, где было, а высоту строки больше не задаёт. */
  const host = inp.closest('.f-wrap') || inp.closest('.f-slot, .field, .grow') || inp.parentElement;
  if (!host) return;
  let box = host._problem;
  if (!box) {
    box = document.createElement('div');
    box.className = 'f-why';
    box.setAttribute('role', 'status');
    host.appendChild(box);
    host._problem = box;
  }
  box.textContent = msg || '';
  box.classList.toggle('is-bad', !!msg);
  const slot = inp.closest('.f-slot') || inp;
  slot.classList.toggle('is-bad', !!msg);
  if (msg) inp.setAttribute('aria-invalid', 'true'); else inp.removeAttribute('aria-invalid');
}

/* П17 · П18. КОМАНДА, КОТОРУЮ РАЗБОР НЕ ЗНАЕТ, БОЛЬШЕ НЕ ПРЕВРАЩАЕТСЯ
   В ПРОИЗВЕДЕНИЕ БУКВ.

   Неизвестная команда прежде теряла обратный слэш, а текст оставался: `\pm`
   становился `pm`, дальше раскрытие неявного умножения делало из него `p*m`,
   и на экране молча появлялись два ползунка — `p` и `m`. Буква `p` в
   экономике это цена, и такой ползунок дезориентирует полностью. То же
   случалось с `\int` и с `\frac{d}{dx}`: последняя превращалась в
   `d/(d*x)` и «считалась».

   Обе клавиши с клавиатуры убраны (движок интегралов и производных по формуле
   не считает — правило «либо считается, либо не предлагается»), но набрать
   команду можно и руками, поэтому есть проверка. */
const TEX_KNOWN = new Set([
  'frac', 'dfrac', 'tfrac', 'sqrt', 'left', 'right', 'bigl', 'bigr',
  'cdot', 'times', 'ast', 'div', 'le', 'leq', 'ge', 'geq', 'ne', 'neq',
  'lt', 'gt', 'infty', 'placeholder', 'begin', 'end', 'text', 'mathrm',
  'mathit', 'operatorname', 'exponentialE', 'imaginaryI', 'log',
  'lbrace', 'rbrace', 'cases', 'nthRoot',
].concat(TEX_FUNCS).concat(Object.keys(TEX_GREEK)));

function unknownTexCommand(tex) {
  const s = String(tex == null ? '' : tex);
  const re = /\\([A-Za-z]+)/g;
  let m;
  while ((m = re.exec(s))) if (!TEX_KNOWN.has(m[1])) return '\\' + m[1];
  return null;
}

// Содержимое группы, начинающейся на позиции i (символ '{'), с учётом вложенности.
function texGroup(s, i) {
  if (s[i] !== '{') return null;
  let d = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === '{' && s[j - 1] !== '\\') d++;
    else if (s[j] === '}' && s[j - 1] !== '\\') { d--; if (d === 0) return { body: s.slice(i + 1, j), end: j + 1 }; }
  }
  return null;
}

function latexToMath(tex) {
  let s = String(tex == null ? '' : tex);
  if (!s.trim()) return '';
  let out = '';
  let i = 0;
  const guard = s.length * 4 + 500;
  let steps = 0;
  while (i < s.length && steps++ < guard) {
    const c = s[i];
    // Степень: ^{…} или ^один-символ. Math.js требует скобки, иначе «Q^2+P»
    // прочиталось бы как Q в степени (2+P).
    if (c === '^') {
      let j = i + 1;
      while (s[j] === ' ') j++;
      const g = texGroup(s, j);
      if (g) { out += '^(' + latexToMath(g.body) + ')'; i = g.end; continue; }
      if (s[j] === '\\') {                                   // ^\alpha и подобное
        const mm = /^\\([A-Za-z]+)/.exec(s.slice(j));
        if (mm) { out += '^(' + latexToMath('\\' + mm[1]) + ')'; i = j + 1 + mm[1].length; continue; }
      }
      out += '^(' + (s[j] === undefined ? '' : s[j]) + ')'; i = j + 1; continue;
    }
    // Индекс: часть имени переменной (P_1, K_max) — Math.js это понимает.
    // Внутри индекса легко оказывается лишнее: набирая «P_1+P_2», человек
    // не выходит из индекса стрелкой, и в группу попадает весь хвост. Берём
    // в имя только его начало, остальное выпускаем наружу как обычный текст.
    if (c === '_') {
      let j = i + 1;
      while (s[j] === ' ') j++;
      const g = texGroup(s, j);
      if (g) {
        const inner = latexToMath(g.body);
        const head = (/^[0-9A-Za-z_]*/.exec(inner) || [''])[0];
        out += '_' + head + inner.slice(head.length);
        i = g.end; continue;
      }
      out += '_' + (s[j] === undefined ? '' : s[j]); i = j + 1; continue;
    }
    if (c !== '\\') {
      if (c === '{' || c === '}') { i++; continue; }        // группировка без команды
      if (c === '~') { out += ' '; i++; continue; }
      out += c; i++; continue;
    }
    // Команда: \имя или \символ
    const m = /^\\([A-Za-z]+)/.exec(s.slice(i));
    if (!m) {                                               // \{ \} \% \$ \, \; \! \
      const ch = s[i + 1];
      if (ch === ',' || ch === ';' || ch === ':' || ch === ' ') { out += ' '; i += 2; continue; }
      if (ch === '!') { i += 2; continue; }
      out += (ch === undefined ? '' : ch); i += 2; continue;
    }
    const name = m[1];
    let j = i + 1 + name.length;
    const skipSpace = () => { while (s[j] === ' ') j++; };
    skipSpace();
    if (name === 'frac' || name === 'dfrac' || name === 'tfrac') {
      const a = texGroup(s, j); if (!a) { i = j; continue; }
      let k = a.end; while (s[k] === ' ') k++;
      const b = texGroup(s, k);
      if (!b) { out += '(' + latexToMath(a.body) + ')'; i = a.end; continue; }
      out += '((' + latexToMath(a.body) + ')/(' + latexToMath(b.body) + '))';
      i = b.end; continue;
    }
    if (name === 'sqrt') {
      let deg = null;
      if (s[j] === '[') {
        const close = s.indexOf(']', j);
        if (close > 0) { deg = s.slice(j + 1, close); j = close + 1; }
      }
      const a = texGroup(s, j);
      const body = a ? latexToMath(a.body) : '';
      out += deg ? ('nthRoot(' + body + ', ' + latexToMath(deg) + ')') : ('sqrt(' + body + ')');
      i = a ? a.end : j; continue;
    }
    if (name === 'left' || name === 'right' || name === 'bigl' || name === 'bigr') {
      const ch = s[j];
      if (ch === '.') { i = j + 1; continue; }              // невидимая скобка
      out += (ch === undefined ? '' : ch); i = j + 1; continue;
    }
    if (name === 'cdot' || name === 'times' || name === 'ast') { out += '*'; i = j; continue; }
    if (name === 'div') { out += '/'; i = j; continue; }
    if (name === 'le' || name === 'leq') { out += '<='; i = j; continue; }
    if (name === 'ge' || name === 'geq') { out += '>='; i = j; continue; }
    if (name === 'ne' || name === 'neq') { out += '!='; i = j; continue; }
    if (name === 'lt') { out += '<'; i = j; continue; }
    if (name === 'gt') { out += '>'; i = j; continue; }
    if (name === 'infty') { out += 'Infinity'; i = j; continue; }
    if (name === 'placeholder') { const a = texGroup(s, j); i = a ? a.end : j; continue; }
    if (name === 'begin') {
      const g = texGroup(s, j);
      const env = g ? g.body.trim() : '';
      // Слэш обязан быть удвоен: '\end{' разбирается как 'end{' (у \e нет
      // значения в JS), поиск закрывающей команды промахивался на один символ,
      // и в разобранное тело кусочной функции попадал лишний слэш.
      const endTag = '\\end{' + env + '}';
      const close = s.indexOf(endTag, g ? g.end : j);
      const body = (close >= 0) ? s.slice(g.end, close) : s.slice(g ? g.end : j);
      i = (close >= 0) ? close + endTag.length : s.length;
      out += (env === 'cases') ? casesToMath(body) : latexToMath(body);
      continue;
    }
    if (name === 'text' || name === 'mathrm' || name === 'mathit' || name === 'operatorname') {
      const a = texGroup(s, j);
      if (a) { out += a.body; i = a.end; } else i = j;
      continue;
    }
    if (name === 'exponentialE') { out += 'e'; i = j; continue; }
    if (name === 'imaginaryI') { out += 'i'; i = j; continue; }
    if (TEX_GREEK[name]) { out += TEX_GREEK[name]; i = j; continue; }
    if (TEX_FUNCS.indexOf(name) >= 0) {
      // \ln x, \ln{x}, \ln\left(x\right) — во всех случаях нужна функция со скобкой.
      const a = texGroup(s, j);
      if (a) { out += name + '(' + latexToMath(a.body) + ')'; i = a.end; continue; }
      out += name; i = j; continue;
    }
    if (name === 'log') { out += 'log'; i = j; continue; }
    if (name === 'lbrace') { out += '{'; i = j; continue; }
    if (name === 'rbrace') { out += '}'; i = j; continue; }
    // Неизвестная команда: выбрасываем обратный слэш, но текст сохраняем.
    out += name; i = j;
  }
  return out.replace(/\s+/g, ' ').trim();
}

/* Обратный перевод: выражение Math.js → LaTeX для показа в поле.
   Основную работу делает сам Math.js (toTex), запасной путь — грубая замена. */
function mathToLatexField(expr) {
  const e = String(expr == null ? '' : expr).trim();
  if (!e) return '';
  return mathToTex(e);
}

/* ── Превращение обычного поля в поле формул ────────────────────────── */
/* Поля собираются не сразу, а когда рабочее место реально открыто.
   Пока сверху висит окно выбора сценария, вся сцена помечена inert, и поле,
   созданное в этот момент, остаётся без обработчика клавиш: значение ему
   поставить можно, а набрать с клавиатуры нельзя. Проверено на живой
   странице — то же поле, собранное после закрытия окна, печатается нормально. */
const _mfWaiting = [];
let _sceneOpen = false;   // окно выбора закрыто хотя бы раз — сцена доступна

function upgradeFormulaField(inp) {
  if (!inp || inp._mfDone) return;
  inp._mfDone = true;
  _mfWaiting.push(inp);
  /* Запасной путь: как только к полю прикоснулись, собираем его немедленно и
     не полагаясь на учёт видимости. Ленивая сборка экономит четыре десятка
     тяжёлых компонентов, но она не должна оставлять человека с обычным
     текстовым окошком, если геометрию секции мы посчитали неверно. */
  const wake = () => {
    inp.removeEventListener('pointerdown', wake);
    inp.removeEventListener('focus', wake);
    const i = _mfWaiting.indexOf(inp);
    if (i >= 0) _mfWaiting.splice(i, 1);
    if (!inp._mf && MATHLIVE_READY) {
      try { buildMathfield(inp); if (inp._mf) inp._mf.focus(); }
      catch (e) { console.warn('Поле формулы:', e); }
    }
  };
  inp.addEventListener('pointerdown', wake);
  inp.addEventListener('focus', wake);
  flushMathfields();
}

/* Собираем только те поля, которые ПРЯМО СЕЙЧАС на экране (А56).

   Полей формул в разметке четыре десятка, а видно в любой сцене три-четыре:
   остальные лежат в спрятанных секциях других моделей. MathLive это тяжёлый
   веб-компонент, и собирать их все разом ради трёх видимых незачем. Поле,
   которого не видно, остаётся в очереди и соберётся, когда его секция
   откроется, — очередь разбирается после каждой перерисовки. */
function fieldOnScreen(inp) {
  const slot = inp && inp.parentNode;
  if (!slot || !slot.getBoundingClientRect) return false;
  if (!slot.offsetParent && getComputedStyle(slot).position !== 'fixed') return false;
  const r = slot.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

/* Разобрать очередь на СЛЕДУЮЩЕМ кадре. Панель или секцию только что
   раскрыли, но раскладка ещё не пересчитана: поле в этот момент числится
   невидимым и остаётся в очереди до следующей перерисовки. */
let _flushQueued = false;
function flushMathfieldsSoon() {
  if (_flushQueued) return;
  _flushQueued = true;
  requestAnimationFrame(() => { _flushQueued = false; flushMathfields(); });
}

function flushMathfields() {
  if (!MATHLIVE_READY || !_sceneOpen || !_mfWaiting.length) return;
  const app = document.querySelector('.app');
  if (app && app.hasAttribute('inert')) return;    // сцена ещё под окном выбора
  const keep = [];
  while (_mfWaiting.length) {
    const inp = _mfWaiting.shift();
    if (!inp.isConnected) continue;                // строку успели пересобрать
    if (!fieldOnScreen(inp)) { keep.push(inp); continue; }
    try { buildMathfield(inp); } catch (e) { console.warn('Поле формулы:', e); inp._mfDone = false; }
  }
  keep.forEach(inp => _mfWaiting.push(inp));
}

/* ⚠️ ОДНА ДВЕРЬ К KaTeX НА ВЕСЬ КАЛЬКУЛЯТОР.

   Печатать формулу звали из девяти мест, и каждое отдавало KaTeX сырую строку.
   Он честно писал в консоль про всё, что не по правилам: за один обход сорока
   одной сцены набиралось 467 предупреждений двух родов.

   Первый род — узкий неразрывный пробел U+202F. Это НАШ разделитель разрядов
   («1 250»), и в шрифтах KaTeX такого символа нет вовсе: он ругался дважды на
   каждое число («Unrecognized Unicode» и «No character metrics»). Заменяем его
   на математический тонкий пробел `\,` — на экране он выглядит так же.

   Второй род — кириллица в математическом режиме («Безработица», индекс
   «предл»). Это не только шум в консоли: в математическом режиме буквы
   набираются курсивным математическим шрифтом, то есть читаются как
   произведение переменных. Слова обязаны идти текстом. Оборачиваем в
   `\text{...}` РОВНО ТО, что стоит вне уже существующих текстовых групп:
   считаем глубину фигурных скобок после `\text{`, `\mathrm{`, `\operatorname{`,
   и внутри них ничего не трогаем — там кириллица уже на своём месте. */
const TEX_TEXT_CMD = /\\(?:text|textrm|textbf|textit|mathrm|operatorname)\s*\{/g;

function katexSafe(src) {
  let s = String(src == null ? '' : src).replace(/[  ]/g, '\\,');
  if (!/[А-Яа-яЁё]/.test(s)) return s;
  // Где начинаются текстовые группы: внутрь них не заглядываем.
  const spans = [];
  let m;
  TEX_TEXT_CMD.lastIndex = 0;
  while ((m = TEX_TEXT_CMD.exec(s)) !== null) {
    let depth = 1, i = m.index + m[0].length;
    while (i < s.length && depth > 0) {
      if (s[i] === '{') depth++;
      else if (s[i] === '}') depth--;
      i++;
    }
    spans.push([m.index, i]);
  }
  const inText = (i) => spans.some(([a, b]) => i >= a && i < b);
  let out = '', run = '';
  // Хвостовой пробел в текстовую группу не берём: он принадлежит формуле рядом.
  const flush = () => {
    const t = run.replace(/\s+$/, '');
    if (t) out += '\\text{' + t + '}';
    if (run.length > t.length) out += '\\,';
    run = '';
  };
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (/[А-Яа-яЁё ]/.test(ch) && !inText(i) && (ch !== ' ' || run)) { run += ch; continue; }
    flush(); out += ch;
  }
  flush();
  return out;
}

/* Печать формулы: одна точка входа, один разбор ошибок. Не собралось — на
   экране остаётся исходный текст, как и было. */
function katexInto(el, tex, opts) {
  if (!el) return false;
  const raw = String(tex == null ? '' : tex);
  if (typeof katex === 'undefined') { el.textContent = raw; return false; }
  try {
    katex.render(katexSafe(raw), el, Object.assign({ throwOnError: false, displayMode: false }, opts || {}));
    return true;
  } catch (e) { el.textContent = raw; return false; }
}

/* ⚠️ ОБРАЗЕЦ В СТРОКЕ ВВОДА — ЭТО ПРОЗА ПЛЮС ФОРМУЛА, А НЕ ОДНА ФОРМУЛА.
   MathLive печатает свой placeholder математикой целиком, и двоеточие в
   «Например: 100 − Q» верстается как знак отношения, с отбивкой по обе
   стороны: на экране выходило «Например : 100 − Q». Слово и двоеточие
   отдаём текстом, математикой остаётся только сама формула. */
function placeholderTex(raw) {
  const s = String(raw || '');
  const i = s.indexOf(':');
  if (i < 0) return '\\text{' + texSafeText(s) + '}';
  const head = s.slice(0, i + 1), tail = s.slice(i + 1).trim();
  const math = (typeof mathToLatexField === 'function' && tail) ? mathToLatexField(tail) : tail;
  return '\\text{' + texSafeText(head) + '}\\;' + math;
}
// Экранируем то, что в \text{} значит не себя.
function texSafeText(t) {
  return String(t || '').replace(/([\\{}$&#^_~%])/g, '\\$1');
}

function buildMathfield(inp) {
  const slot = inp.parentNode;
  /* Запасную накладку с набранной формулой убираем СРАЗУ. Она лежит абсолютом
     поверх ячейки, и раньше оставалась висеть над только что собранным полем:
     формула показывалась дважды и внахлёст. Уходила она лишь после правки в
     поле, потому что пряталась в обработчике ввода — отсюда и «стёр символ,
     набрал заново, и стало нормально». */
  const ts = slot.querySelector('.f-typeset');
  if (ts) ts.classList.remove('show');
  const mf = new window.MathfieldElement({
    mathVirtualKeyboardPolicy: 'manual',   // всплывающую клавиатуру ведём сами
  });
  /* ⚠️ ЭТИ ТРИ НАСТРОЙКИ ЧИТАЮТСЯ ТОЛЬКО У ГОТОВОГО ПОЛЯ, НЕ У КОНСТРУКТОРА.
     Переданные в `new MathfieldElement({...})`, они молча не применялись, а
     MathLive писал в консоль предупреждение на каждое поле: за один обход
     сорока одной сцены набиралось под девятьсот строк, и отлаживать в консоли
     было нечем. Значения те же, что задумывал автор кода: «e» и «x» остаются
     переменными, а не превращаются в слова; закрывающая скобка ставится сама;
     лишние скобки при вводе не убираются. */
  mf.smartMode = false;
  mf.smartFence = true;
  mf.removeExtraneousParentheses = false;
  mf.setAttribute('aria-label', inp.getAttribute('aria-label') || 'Формула');
  if (inp.placeholder) mf.setAttribute('placeholder', placeholderTex(inp.placeholder));
  slot.appendChild(mf);
  inp.classList.add('mf-hidden');
  inp._mf = mf;

  /* Клавиши с настоящей клавиатуры MathLive принимает не сам элемент, а
     невидимый приёмник внутри него. Фокус на самом поле (щелчком или из кода)
     до приёмника не доходит, и набранное пропадало. Переводим фокус туда сами
     после того, как поле обработает щелчок и поставит курсор. */
  const sink = () => mf.shadowRoot && mf.shadowRoot.querySelector('.ML__keyboard-sink');
  const grabKeys = () => {
    const s = sink();
    if (s && mf.shadowRoot.activeElement !== s) s.focus();
    else if (!s) mf.focus();
  };
  mf.focusField = () => { mf.focus(); grabKeys(); setTimeout(grabKeys, 0); };

  /* ⚠️ НАБОР В ПОЛЕ ФОРМУЛЫ ЗАМЕНЯЕТ ПРЕЖНЮЮ ЗАПИСЬ, А НЕ ДОПИСЫВАЕТСЯ К НЕЙ.

     Причина не во вкусе, а в устройстве: клавиши MathLive принимает не сам
     элемент, а невидимый приёмник внутри него, и перевод фокуса туда (grabKeys
     выше) сбрасывает курсор в КОНЕЦ записи. Куда бы человек ни щёлкнул — в
     начало строки, в середину, по самой формуле, — набранное приезжает в хвост.

     Отсюда дефект, который владелец видел живьём и принял за пропажу параметра:
     щёлкнул по полю КПВ, набрал «y=100-a*x», нажал «Построить» — а в поле лежит
     «y=100-xy=100-a*x», разбор его не понимает, и модель молча остаётся с
     прежней формулой «y = 100 − x». Ползунок буквы при этом заводится (его
     список читает ТЕКСТ ПОЛЯ, а не состояние модели), выглядит рабочим и не
     двигает ничего.

     Раз курсор поставить всё равно нельзя, набор обязан заменять: выделяем
     запись целиком, как это давно делают значение параметра и имя точки. Чтобы
     поправить один символ, щёлкают второй раз — поле уже в фокусе, выделение
     снимается, дальше правка обычная.

     Тот же дефект и той же природы уже чинили 20.08 у редактора границ
     ползунка («значение дописывается вместо замены», п. 18). У полей формул
     он остался. */
  let hadFocus = false;
  const selectAllOnEntry = () => {
    if (hadFocus) return;
    hadFocus = true;
    try { mf.select(); } catch (e) {}
  };
  mf.addEventListener('blur', () => { hadFocus = false; });
  ['pointerdown', 'pointerup', 'focus'].forEach(ev => {
    mf.addEventListener(ev, () => {
      grabKeys();
      setTimeout(() => { grabKeys(); selectAllOnEntry(); }, 0);
    });
  });

  let syncing = false;
  const toInput = () => {
    if (syncing) return;
    syncing = true;
    try {
      /* П17 · П18. Команда, которой разбор не знает, дальше не идёт. Прежде она
         теряла слэш и уходила в движок буквами: `\pm` становился `p*m` и
         заводил два ползунка, один из которых назывался ценой. */
      const bad = unknownTexCommand(mf.value);
      if (bad) {
        inp.dataset.texUnknown = bad;
        if (typeof fieldProblem === 'function')
          fieldProblem(inp, 'Не понимаю команду ' + bad + ' — калькулятор её не считает');
        return;
      }
      delete inp.dataset.texUnknown;
      if (typeof fieldProblem === 'function') fieldProblem(inp, '');
      const text = latexToMath(mf.value);
      if (inp.value !== text) {
        inp.value = text;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
      }
    } finally { syncing = false; }
  };
  const fromInput = () => {
    if (syncing) return;
    syncing = true;
    try {
      const want = mathToLatexField(inp.value);
      // Сравниваем по смыслу, а не побуквенно: обратный перевод даёт другую,
      // но равносильную запись, и слепое присваивание сбивало бы курсор.
      if (latexToMath(mf.value).replace(/\s/g, '') !== String(inp.value || '').replace(/\s/g, '')) {
        mf.value = want;
      }
    } finally { syncing = false; }
  };

  /* Русская раскладка ломала ввод десятичных чисел: точка превращалась в дробь.
     MathLive не находит кириллическую раскладку в своих таблицах и переходит на
     запасной путь, где смотрит на ФИЗИЧЕСКИЙ код клавиши, а не на набранный
     символ. В русской раскладке точка сидит на той же клавише, где в английской
     слэш, — отсюда и дробь вместо «0.5». Настройками MathLive это не лечится:
     подмена происходит раньше. Решаем сами и по e.key, то есть по тому, что
     человек НАБРАЛ. */
  const layoutGuard = (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    let tex = null;
    if (e.key === '.' || e.key === ',') tex = '.';               // десятичный разделитель
    else if (e.key === '/') tex = '\\frac{#@}{#?}';              // дробь — только настоящий слэш
    if (tex == null) return;
    e.preventDefault();
    e.stopPropagation();
    mf.executeCommand(['insert', tex, { focus: true, feedback: false }]);
    mf.dispatchEvent(new Event('input', { bubbles: true }));
  };
  // Перехват в фазе погружения: до того, как клавиша дойдёт до приёмника внутри
  // теневого дерева, где её разбирает сам MathLive.
  mf.addEventListener('keydown', layoutGuard, true);
  const armSink = () => {
    const s = sink();
    if (s && !s._layoutGuard) { s._layoutGuard = 1; s.addEventListener('keydown', layoutGuard, true); }
  };
  armSink(); setTimeout(armSink, 0);

  mf.addEventListener('input', toInput);
  inp.addEventListener('input', fromInput);
  // Enter в поле формулы = «добавить кривую», как и раньше в обычном поле.
  mf.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); }
  });
  mf.addEventListener('focusin', () => { closeAllKeyboardsExcept(slot); });
  fromInput();
}

// Вставить кусок формулы в активное поле: в поле MathLive — набранным
// символом, в обычное поле — текстом Math.js.
function insertIntoField(inp, tex, txt, back) {
  if (!inp) return;
  if (inp._mf) {
    if (inp._mf.focusField) inp._mf.focusField(); else inp._mf.focus();
    inp._mf.executeCommand(['insert', tex, { focus: true, feedback: false, scrollIntoView: true }]);
    inp._mf.dispatchEvent(new Event('input', { bubbles: true }));
    return;
  }
  insertIntoFormula(inp, txt != null ? txt : tex, back || 0);
}

/* ── Раскладка клавиатуры ─────────────────────────────────────────────
   Каждая клавиша: [подпись, вставка в набранном виде, вставка текстом,
   насколько отвести курсор назад в обычном поле].
   #@ — то, что выделено (или предыдущий кусок), #? — пустое место. */
const MKBD_BASE = [
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
const MKBD_FUNCS = [
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
const MKBD_LETTERS = [
  ['Латинские буквы', 'abcdefghijklmnopqrstuvwxyz'.split('').map(ch => [ch, ch, ch])],
  ['Заглавные', 'ABCDEFGHIKLMNPQRSTVWXYZ'.split('').map(ch => [ch, ch, ch])],
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

function mkbdKey(k, inp) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'mk';
  b.textContent = k[0];
  /* Знак без слова обязан называть себя доступному чтению: нативной подсказки
     на сайте нет (правило 18 части 4), а «⌫» и «✕» на слух не читаются. */
  if (k[1] === 'DEL') b.setAttribute('aria-label', 'Стереть символ');
  if (k[1] === 'CLEAR') b.setAttribute('aria-label', 'Очистить поле');
  if (k[0].length > 2) b.classList.add('fn');
  b.addEventListener('mousedown', (e) => e.preventDefault());   // не терять фокус поля
  b.addEventListener('click', () => {
    if (k[1] === 'DEL') {
      if (inp._mf) inp._mf.executeCommand('deleteBackward');
      else { inp.value = inp.value.slice(0, -1); inp.dispatchEvent(new Event('input', { bubbles: true })); }
      return;
    }
    if (k[1] === 'CLEAR') {
      if (inp._mf) inp._mf.value = '';
      setFieldValue(inp, '');
      return;
    }
    insertIntoField(inp, k[1], k[2], k[3]);
  });
  return b;
}

// Собрать клавиатуру под конкретным полем. Три раздела, открыт один.
function buildKeyboard(box, inp) {
  box.innerHTML = '';
  const tabs = document.createElement('div'); tabs.className = 'mkbd-tabs';
  const panes = [];
  const SECTIONS = [
    ['123', (pane) => {
      MKBD_BASE.forEach(row => {
        const r = document.createElement('div'); r.className = 'mkbd-row';
        row.forEach(k => r.appendChild(mkbdKey(k, inp)));
        pane.appendChild(r);
      });
    }],
    ['Функции', (pane) => {
      MKBD_FUNCS.forEach(([label, keys]) => {
        const l = document.createElement('div'); l.className = 'mkbd-lab'; l.textContent = label;
        const g = document.createElement('div'); g.className = 'mkbd-grid';
        keys.forEach(k => g.appendChild(mkbdKey(k, inp)));
        pane.append(l, g);
      });
    }],
    ['Буквы', (pane) => {
      MKBD_LETTERS.forEach(([label, keys]) => {
        const l = document.createElement('div'); l.className = 'mkbd-lab'; l.textContent = label;
        const g = document.createElement('div'); g.className = 'mkbd-grid';
        keys.forEach(k => g.appendChild(mkbdKey(k, inp)));
        pane.append(l, g);
      });
    }],
  ];
  SECTIONS.forEach(([name, fill], idx) => {
    const t = document.createElement('button');
    t.type = 'button'; t.className = 'mkbd-tab' + (idx === 0 ? ' active' : '');
    t.textContent = name;
    const pane = document.createElement('div');
    pane.className = 'mkbd-pane' + (idx === 0 ? ' active' : '');
    fill(pane);
    t.addEventListener('click', () => {
      tabs.querySelectorAll('.mkbd-tab').forEach(x => x.classList.remove('active'));
      panes.forEach(x => x.classList.remove('active'));
      t.classList.add('active'); pane.classList.add('active');
    });
    tabs.appendChild(t); panes.push(pane);
  });
  box.appendChild(tabs);
  panes.forEach(p => box.appendChild(p));

  /* Внизу — только вход в конструктор кусочной функции. Раздел «Примеры формул»
     убран: он повторял раздел «Функции», а вернуться из него обратно к
     клавиатуре было нечем. */
  const foot = document.createElement('div'); foot.className = 'mkbd-foot';
  const pw = document.createElement('button'); pw.type = 'button'; pw.textContent = 'Кусочная функция';
  pw.addEventListener('click', () => {
    box.classList.remove('open');
    openPiecewise(inp, box._var || 'x');
  });
  foot.appendChild(pw);
  box.appendChild(foot);
}

// Закрыть все открытые клавиатуры, кроме той, что в переданном слоте.
function closeAllKeyboardsExcept(slot) {
  document.querySelectorAll('.mkbd.open').forEach(b => {
    if (slot && b._slot === slot) return;
    b.classList.remove('open');
    if (b._btn) b._btn.setAttribute('aria-expanded', 'false');
  });
}

/* ── Реестр строк ввода формул ────────────────────────────────────────
   Каждое поле, прошедшее через equipFormulaField, попадает сюда. По реестру
   собираются буквы-параметры: формулы сцен лежат в своих полях, а не в
   STATE.curves, и без реестра «a - Q» в КПВ или в макро ползунка бы не дало. */
const FORMULA_FIELDS = [];
/* П19: панель ползунков обновляется прямо во время набора формулы.
   Раньше буква становилась ползунком только после «Построить» или Enter:
   syncParams живёт внутри redrawAll, а сценовые поля перерисовку по каждому
   символу не запускают. Вешаем на каждое формульное поле отложенный вызов
   syncParams — он сам ничего не перестраивает, пока НАБОР букв не изменился
   (флаг changed внутри), поэтому печатать «100 - 2*Q» так же дёшево, как было.
   График по-прежнему строится кнопкой: здесь обновляется только панель. */
let _paramsSyncTimer = null;
function scheduleParamsSync() {
  clearTimeout(_paramsSyncTimer);
  _paramsSyncTimer = setTimeout(() => {
    try { if (typeof syncParams === 'function') syncParams(); } catch (e) {}
  }, 200);
}
function registerFormulaField(inp) {
  if (!inp || FORMULA_FIELDS.indexOf(inp) >= 0) return;
  /* Часть полей собирается заново при каждой перерисовке сюжета (строки «min и
     max», страны в сумме КПВ). Прежние узлы из разметки уходят, но в реестре
     оставались, и liveFormulaTexts читала формулы у оторванных полей: буквы
     старых формул продолжали заводить ползунки. Чистим при каждой записи. */
  for (let i = FORMULA_FIELDS.length - 1; i >= 0; i--) {
    if (!FORMULA_FIELDS[i].isConnected) FORMULA_FIELDS.splice(i, 1);
  }
  FORMULA_FIELDS.push(inp);
  inp.addEventListener('input', scheduleParamsSync);
}

/* Поле «живо», если его секцию не спрятала сцена. Смотрим на display:none и
   hidden по цепочке родителей, а не на offsetParent: свёрнутая боковая панель
   тоже убирает элемент с экрана, но формулы при этом никуда не деваются, и
   ползунки параметров не должны от этого пропадать. */
function fieldActive(el) {
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    if (n.hidden) return false;
    if (n.style && n.style.display === 'none') return false;
    if (n.classList && n.classList.contains('scoped-off')) return false;
  }
  return true;
}

function liveFormulaTexts() {
  return FORMULA_FIELDS.filter(fieldActive).map(i => i.value);
}

/* Какой набор примеров и какая переменная у поля. Ключи — те же, что в
   FORMULA_EXAMPLES; поле, которого здесь нет, общей оснастки не получает
   (имена, заголовки и списки чисел формулами не являются). */
const FORMULA_FIELD_KINDS = {
  'ext-input': 'PQ',
  'inp-d3-1': 'DEMAND', 'inp-d3-2': 'DEMAND', 'inp-d3-mc': 'MC',
  'inp-ki-1': 'DEMAND', 'inp-ki-2': 'DEMAND', 'inp-ki-3': 'DEMAND',
  'inp-kp-1': 'DEMAND', 'inp-kp-2': 'DEMAND', 'inp-kink-mc': 'MC',
  'inp-pl1': 'TC', 'inp-pl2': 'TC',
  'inp-cmc': 'MC', 'inp-catc': 'ATC', 'inp-cavc': 'ATC',
  'ineq-formula': 'MATHF',
  'inp-ppft': 'PPF',   // строки стран собираются на лету и оснащаются там же
  'inp-tb1': 'PPF', 'inp-tb2': 'PPF',
  'ma-sras': 'MACRO', 'ma-ad': 'MACRO', 'ma-md': 'MACRO', 'ma-ls': 'MACRO',
  'ma-ld': 'MACRO', 'ma-fxd': 'MACRO', 'ma-fxs': 'MACRO',
  'ma-lafd': 'MACRO', 'ma-lafs': 'MACRO', 'ma-is': 'MACRO', 'ma-lm': 'MACRO',
};

/* Достроить недостающую обвязку и подключить общую механику.
   Поля сцен размечены просто («label + input»), а attachFormulaHelp ждёт
   готовых кнопки и всплывашки. Здесь их создаём, дальше работает ровно тот же
   код, что у полей, размеченных вручную: набранная формула в строке, LaTeX-ввод,
   клавиатура, примеры и конструктор кусочной функции. */
function equipFormulaField(inputId, kind) {
  const inp = document.getElementById(inputId);
  if (!inp || inp._equipped) return;
  inp._equipped = true;

  let wrap = inp.closest('.f-wrap');
  if (!wrap) { wrap = inp.parentElement; wrap.classList.add('f-wrap'); }
  let row = inp.closest('.f-row');
  if (!row) {
    row = document.createElement('div');
    row.className = 'f-row';
    inp.parentNode.insertBefore(row, inp);
    row.appendChild(inp);
  }
  let btn = row.querySelector('.f-help');
  if (!btn) {
    btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'f-help'; btn.id = 'fh-auto-' + inputId;
    btn.setAttribute('aria-expanded', 'false');
    btn.title = 'Как писать формулы';
    btn.textContent = '?';
    row.appendChild(btn);
  }
  let pop = wrap.querySelector('.f-pop');
  if (!pop) {
    pop = document.createElement('div');
    pop.className = 'f-pop'; pop.id = 'fp-auto-' + inputId;
    pop.setAttribute('role', 'region');
    pop.setAttribute('aria-label', 'Примеры формул');
    wrap.appendChild(pop);
  }
  btn.setAttribute('aria-controls', pop.id);
  attachFormulaHelp(btn.id, pop.id, inputId, kind);
  registerFormulaField(inp);
}

// Оснастить разом все формульные поля сцен из таблицы выше.
function equipAllFormulaFields() {
  Object.keys(FORMULA_FIELD_KINDS).forEach(id => equipFormulaField(id, FORMULA_FIELD_KINDS[id]));
}

function attachFormulaHelp(btnId, popId, inputId, kind) {
  const btn = document.getElementById(btnId), pop = document.getElementById(popId);
  if (!btn || !pop) return;
  const inp = document.getElementById(inputId);
  registerFormulaField(inp);

  // Набранная формула в САМОЙ строке. Пока в поле не пишут, поверх него лежит
  // та же формула, но напечатанная как в учебнике; стоит щёлкнуть или перейти
  // табом — сверху снова обычный текст, который и правится. Так формула и
  // выглядит по-человечески, и остаётся ровно тем, что считает движок:
  // разбирать набранную запись обратно в Math.js не нужно, а значит нечему и
  // ломаться.
  //
  // Отдельного предпросмотра под полем больше нет. Он не только дублировал
  // строку, но и ломал добавление кривой: на потере фокуса блок схлопывался,
  // кнопка «Добавить» уезжала вверх между нажатием и отпусканием мыши, и щелчок
  // не доходил. Накладка лежит абсолютом внутри своей ячейки и высоту строки
  // не меняет, поэтому ничего не прыгает.
  let kbd = null;
  if (inp) {
    const slot = document.createElement('div');
    slot.className = 'f-slot';
    inp.parentNode.insertBefore(slot, inp);
    slot.appendChild(inp);
    // Запасной вид: если MathLive не загрузился, поверх обычного поля лежит
    // та же формула, напечатанная как в учебнике (прежнее поведение).
    const typeset = document.createElement('div');
    typeset.className = 'f-typeset';
    typeset.title = 'Щёлкните, чтобы поправить формулу';
    slot.appendChild(typeset);

    const focused = () => document.activeElement === inp;
    const sync = () => {
      if (inp._mf) { typeset.classList.remove('show'); return; }
      const val = (inp.value || '').trim();
      renderTex(typeset, val);
      typeset.classList.toggle('show', !focused() && !!val && typeset.classList.contains('has'));
    };
    inp.addEventListener('input', sync);
    inp.addEventListener('focus', sync);
    inp.addEventListener('blur', sync);
    typeset.addEventListener('mousedown', (e) => { e.preventDefault(); inp.focus(); });
    _texPending.push(sync);
    sync();

    upgradeFormulaField(inp);
    _mfPending.push(sync);   // библиотека доехала — накладка больше не нужна

    // Клавиатура живёт под полем и раскрывается кнопкой в строке ввода.
    kbd = document.createElement('div');
    kbd.className = 'mkbd';
    kbd._slot = slot; kbd._btn = btn; kbd._pop = pop; kbd._helpBtn = btn;
    pop.parentNode.insertBefore(kbd, pop.nextSibling);
  }

  // Кнопка «?» стала кнопкой клавиатуры: примеры формул теперь лежат внутри неё.
  btn.classList.add('f-kbd');
  btn.title = 'Клавиатура и примеры формул';
  btn.setAttribute('aria-label', 'Открыть математическую клавиатуру');
  btn.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
    ' stroke-width="1.8" stroke-linecap="round"><rect x="2.5" y="6" width="19" height="12" rx="2"/>' +
    '<path d="M6 9.5h.01M9.5 9.5h.01M13 9.5h.01M16.5 9.5h.01M6 12.8h.01M9.5 12.8h.01M13 12.8h.01M16.5 12.8h.01"/>' +
    '<path d="M8.2 15.6h7.6"/></svg>';

  const render = () => {
    const k = (typeof kind === 'function') ? kind() : kind;
    const set = FORMULA_EXAMPLES[k] || FORMULA_EXAMPLES.PQ;
    pop.innerHTML = '';
    const t = document.createElement('div');
    t.className = 'f-pop-title'; t.textContent = set.title;
    pop.appendChild(t);

    const grid = document.createElement('div');
    grid.className = 'f-grid';
    set.items.forEach(([ex, note]) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'f-ex'; b.title = 'Поставить эту формулу в поле';
      const m = document.createElement('span'); m.className = 'f-ex-math';
      renderTex(m, ex);
      const s = document.createElement('span'); s.className = 'f-ex-note'; s.textContent = note;
      b.append(m, s);
      b.addEventListener('click', () => {
        if (!inp) return;
        inp.value = ex;
        inp.dispatchEvent(new Event('input', { bubbles: true }));   // предпросмотр и слушатели поля
        inp.focus();
        pop.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      });
      grid.appendChild(b);
    });
    pop.appendChild(grid);

    // Палитра операций: подставляется в строку по кусочкам, поле не очищается.
    // Это то место, где новичок видит, из чего вообще можно собрать формулу.
    const pt = document.createElement('div');
    pt.className = 'f-pop-title'; pt.style.marginTop = '12px';
    pt.textContent = 'Из чего собрать формулу';
    pop.appendChild(pt);
    const lead = document.createElement('div');
    lead.className = 'f-pal-lead';
    lead.textContent = 'Нажимайте по очереди: кусочки подставляются в строку туда, где стоит курсор.';
    pop.appendChild(lead);

    FORMULA_PALETTE.forEach(([groupName, ops]) => {
      const gl = document.createElement('div');
      gl.className = 'f-pal-group'; gl.textContent = groupName;
      pop.appendChild(gl);
      const row = document.createElement('div');
      row.className = 'f-pal-row';
      ops.forEach(([shown, note, insRaw, back]) => {
        const ins = insRaw != null ? insRaw : shown;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'f-pal'; b.textContent = shown; b.title = note;
        b.addEventListener('click', () => { insertIntoFormula(inp, ins, back || 0); });
        row.appendChild(b);
      });
      pop.appendChild(row);
    });

    // Отдельный вход в конструктор: он собирает ту же кусочную запись, но по полям.
    const pwRow = document.createElement('div');
    pwRow.className = 'f-pal-row'; pwRow.style.marginTop = '6px';
    const pwBtn = document.createElement('button');
    pwBtn.type = 'button'; pwBtn.className = 'f-pal wide';
    pwBtn.textContent = 'Собрать кусочную функцию';
    pwBtn.title = 'Спросим число кусков и соберём запись из отдельных полей';
    pwBtn.addEventListener('click', () => {
      pop.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
      openPiecewise(inp, FORMULA_VAR[k] || 'x');
    });
    pwRow.appendChild(pwBtn);
    pop.appendChild(pwRow);

    const f = document.createElement('div'); f.className = 'f-pop-foot'; f.textContent = FORMULA_FOOT;
    pop.appendChild(f);
  };
  pop._render = render;
  // Кнопка открывает клавиатуру; примеры формул — раздел внутри неё.
  btn.addEventListener('click', () => {
    if (!kbd) {
      const open = pop.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) render();
      return;
    }
    pop.classList.remove('open');
    const open = !kbd.classList.contains('open');
    closeAllKeyboardsExcept(null);
    if (open) {
      kbd._var = FORMULA_VAR[(typeof kind === 'function') ? kind() : kind] || 'x';
      if (!kbd._built) { buildKeyboard(kbd, inp); kbd._built = true; }
      kbd.classList.add('open');
      if (inp && inp._mf) inp._mf.focusField(); else if (inp) inp.focus();
    }
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
}

/* ---------------------------------------------------------------------
   ФАЗА 1б. Переключатель формы записи кривой: P(Q) ↔ Q(P).
   Меняет только то, КАК пользователь пишет формулу; в математику всегда
   уходит канон P = f(Q) (см. buildCurveFromQP). Форма запоминается у каждой
   кривой отдельно — можно смешивать в одной сцене.
   --------------------------------------------------------------------- */
function setCurveForm(form) {
  STATE.curveForm = (form === 'QP') ? 'QP' : 'PQ';
  const a = document.getElementById('cf-pq'), b = document.getElementById('cf-qp');
  if (a) a.classList.toggle('active', STATE.curveForm === 'PQ');
  if (b) b.classList.toggle('active', STATE.curveForm === 'QP');
  applyNewRoleUI();
}

/* Какой набор примеров показать в справке поля кривой. Зависит от того, ЧТО
   пользователь собрался добавить: рядом с предельными издержками объяснять
   запись спроса бессмысленно. */
function newCurveRole() {
  const sel = document.getElementById('new-role');
  return sel ? sel.value : '';
}
function curveHelpKind() {
  if (STATE.curveForm === 'QP') return 'QP';          // «объём от цены» — свой набор
  return { demand: 'DEMAND', supply: 'SUPPLY', mc: 'MC', tc: 'TC', atc: 'ATC' }[newCurveRole()] || 'PQ';
}

/* Подсказка, плейсхолдер и доступность формы записи под выбранную роль.
   Запись «объём от цены» осмысленна для спроса и предложения; предельные и
   средние затраты по определению функции количества, поэтому для них
   переключатель формы прячется. */
function applyNewRoleUI() {
  const role = newCurveRole();
  const qpOk = (role === '' || role === 'demand' || role === 'supply');
  const seg = document.getElementById('curve-form-seg');
  if (seg) seg.style.display = qpOk ? '' : 'none';
  if (!qpOk && STATE.curveForm === 'QP') { STATE.curveForm = 'PQ'; setCurveForm('PQ'); return; }

  const inp = document.getElementById('inp-formula');
  const ph = { demand: 'Например: 100 - Q', supply: 'Например: Q',
               mc: 'Например: 20', tc: 'Например: Q^2 + 10*Q + 50',
               atc: 'Например: Q - 10 + 100/Q' };
  if (inp) inp.placeholder = (STATE.curveForm === 'QP') ? 'Например: 100 - 2*P' : (ph[role] || 'Например: 100 - Q');

  const h = document.getElementById('curve-form-hint');
  const note = {
    demand: 'Спрос: цена как функция количества, P&nbsp;=&nbsp;f(Q).',
    supply: 'Предложение: цена как функция количества, P&nbsp;=&nbsp;f(Q).',
    mc: 'Предельные издержки как функция выпуска, MC(Q). Форма записи тут одна.',
    tc: 'Суммарные затраты как функция выпуска, TC(Q). Средние и предельные посчитаем сами.',
    atc: 'Средние затраты как функция выпуска, ATC(Q).',
  };
  if (h) h.innerHTML = (STATE.curveForm === 'QP')
    ? 'Количество как функция цены: Q&nbsp;=&nbsp;f(P). Приведём к P&nbsp;=&nbsp;f(Q) сами: линейную явно, любую другую численно.'
    : (note[role] || 'Цена как функция количества: P&nbsp;=&nbsp;f(Q).');

  const pop = document.getElementById('fp-formula');
  if (pop && pop.classList.contains('open') && typeof pop._render === 'function') pop._render();
}


/* ── Н75, Н60, Н72. Редактируемое значение ────────────────────────────────
   Один компонент на все места, где человек правит число или короткий текст.
   До него интерфейс был засыпан обычными прямоугольными полями: шаг «0.01» в
   рамке, координаты точки в двух рамках, значение параметра при щелчке
   превращалось в подсвеченное поле с рамкой и синим выделением. Выглядит это
   как черновик, а не как инструмент.

   Правила компонента:
     • в покое   — отрендеренная формула, без рамки и фона, снизу пунктир;
     • наведение — пунктир и само значение становятся акцентными, курсор текстовый;
     • щелчок    — правка НА МЕСТЕ: тот же кегль, тот же пунктир, рамки нет,
                   курсор в конце, выделения всего текста нет;
     • ввод      — применяется на каждый символ, если значение уже осмысленно;
                   неполное («−», «1e») не применяется, пунктир краснеет;
     • выход     — Enter и потеря фокуса применяют, Esc возвращает прежнее.

   Во время набора показываем обычный текст того же кегля, а формулу собираем
   заново по выходе: KaTeX умеет рендерить и на каждый символ (так сделано в его
   собственном примере), но менять разметку под курсором значит терять каретку.

   opts: { get, set, tex, fmt, title, kind:'number'|'text', min, max } */
function makeEditableValue(opts) {
  const el = document.createElement('span');
  el.className = 'edval';
  el.tabIndex = 0;
  el.setAttribute('role', 'textbox');
  if (opts.title) el.title = opts.title;
  const isNum = (opts.kind || 'number') === 'number';

  const shown = () => {
    const v = opts.get();
    if (typeof opts.fmt === 'function') return opts.fmt(v);
    /* А30. Пустое числовое значение показываем пустым, а не нулём. Раньше
       незаполненная координата уходила в fmt, а тот на пустой строке считал
       ноль: черновик точки открывался с «x = 0, y = 0», и человек нажимал
       галочку не глядя, получая точку в начале координат. */
    if (isNum && (v === '' || v == null || !isFinite(v))) return '';
    return isNum ? fmt(v) : String(v == null ? '' : v);
  };
  const paint = () => {
    if (el.classList.contains('editing')) return;
    const text = shown();
    if (typeof katex === 'undefined' || typeof opts.tex !== 'function') { el.textContent = text; return; }
    if (!katexInto(el, opts.tex(opts.get(), text))) el.textContent = text;
  };
  el._repaint = paint;
  paint();

  const parse = (raw) => {
    if (!isNum) return raw;
    const v = parseFloat(String(raw).replace(',', '.'));
    if (!isFinite(v)) return null;
    if (opts.min != null && v < opts.min) return null;
    if (opts.max != null && v > opts.max) return null;
    return v;
  };

  const begin = () => {
    if (el.classList.contains('editing')) return;
    const before = opts.get();
    el.classList.add('editing');
    el.textContent = isNum ? String(shown()).replace(/ /g, '') : String(before == null ? '' : before);
    el.contentEditable = 'plaintext-only';
    if (el.contentEditable !== 'plaintext-only') el.contentEditable = 'true';   // Firefox
    el.focus();
    /* А61. Содержимое ВЫДЕЛЯЕТСЯ целиком: первый же набранный символ заменяет
       прежнее значение. Раньше курсор ставился в конец, и набор «45» поверх
       нуля давал «045». Это отмена прежнего решения: дописывать к значению
       по-прежнему можно, для этого достаточно нажать стрелку или щёлкнуть
       второй раз, а вот случайное «045» ловилось глазами не всегда. */
    const r = document.createRange(); r.selectNodeContents(el);
    const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);

    const live = () => {
      const v = parse(el.textContent.trim());
      el.classList.toggle('bad', el.textContent.trim() !== '' && v === null);
      if (v !== null) opts.set(v);
    };
    const finish = (cancel) => {
      el.removeEventListener('input', live);
      el.removeEventListener('keydown', onKey);
      el.removeEventListener('blur', onBlur);
      el.classList.remove('editing', 'bad');
      el.contentEditable = 'false';
      /* ⚠️ НЕЗАПОЛНЕННОЕ ПОЛЕ ВОЗВРАЩАЕТ ПРЕЖНЕЕ ЗНАЧЕНИЕ, А НЕ ПУСТОТУ.
         У редактора границ ползунка поля показываются ПУСТЫМИ намеренно (копия
         Десмоса), то есть `before` там — пустая строка. А выход из правки
         честно звал `set(before)`, и пустая строка уезжала прямо в границу
         ползунка: `sl.max = ''` — полоса ломается, значение обнуляется,
         ползунок перестаёт двигаться. Пустое «прежнее» означает «прежнего
         числа не было», и правильный ответ на него — не трогать ничего. */
      const restorable = !isNum || (before !== '' && before != null && isFinite(before));
      if (cancel) { if (restorable) opts.set(before); }
      else {
        const v = parse(el.textContent.trim());
        if (v !== null) opts.set(v);
        else if (restorable) opts.set(before);
      }
      paint();
    };
    function onKey(e) {
      if (e.key === 'Enter') { e.preventDefault(); finish(false); }
      else if (e.key === 'Escape') { e.preventDefault(); finish(true); }
    }
    function onBlur() { finish(false); }
    el.addEventListener('input', live);
    el.addEventListener('keydown', onKey);
    el.addEventListener('blur', onBlur);
  };

  el.addEventListener('click', begin);
  /* Tab ведёт по полям редактора по порядку, и пришедшее фокусом поле сразу
     готово к набору. Без этого Tab переводил фокус, но правку не открывал, и
     второе число приходилось начинать щелчком. Повторного входа не будет:
     `begin` первым делом ставит класс «editing» и только потом зовёт focus. */
  el.addEventListener('focus', () => { if (!el.classList.contains('editing')) begin(); });
  el.addEventListener('keydown', (e) => {
    if (!el.classList.contains('editing') && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); begin(); }
  });
  return el;
}

/* ── Н15, Н50, Н73. Настоящий тумблер ──────────────────────────────────────
   Переключатель-пилюля с кружком, который ездит из края в край, вместо двух
   сегментных кнопок. Один компонент на все места: точки, площади, «min и max».
   Возвращает обёртку;值 читается как el.value ('left' | 'right'). */
function makeToggle(leftText, rightText, startRight, onChange) {
  const wrap = document.createElement('div');
  wrap.className = 'tgl';
  const l = document.createElement('span'); l.className = 'tgl-lab'; l.textContent = leftText;
  const r = document.createElement('span'); r.className = 'tgl-lab'; r.textContent = rightText;
  const sw = document.createElement('button');
  sw.type = 'button'; sw.className = 'tgl-sw';
  sw.setAttribute('role', 'switch');
  const knob = document.createElement('span'); knob.className = 'tgl-knob';
  sw.appendChild(knob);
  wrap.append(l, sw, r);

  const paint = () => {
    const right = wrap.value === 'right';
    wrap.classList.toggle('is-right', right);
    sw.setAttribute('aria-checked', right ? 'true' : 'false');
    sw.setAttribute('aria-label', right ? rightText : leftText);
    l.classList.toggle('on', !right);
    r.classList.toggle('on', right);
  };
  const set = (right, fire) => {
    wrap.value = right ? 'right' : 'left';
    paint();
    if (fire && typeof onChange === 'function') onChange(wrap.value);
  };
  wrap._set = (right) => set(right, false);
  sw.addEventListener('click', () => set(wrap.value !== 'right', true));
  // Щелчок по самой подписи тоже переключает: попасть в слово проще, чем в кружок.
  l.addEventListener('click', () => set(false, true));
  r.addEventListener('click', () => set(true, true));
  set(!!startRight, false);
  return wrap;
}

/* Заменить пару сегментных кнопок настоящим тумблером (Н50, Н73), НЕ трогая
   обвязку. Кнопки остаются в разметке и продолжают быть источником правды:
   сцены читают и ставят у них класс .active, а тумблер лишь щёлкает по ним и
   показывает их состояние. Так переключатель стал другим на вид, а логика
   сцен осталась ровно та же. */
/* Первый аргумент — id самой полосы ИЛИ null: тогда полоса ищется по кнопке.
   Так подключаются переключатели, у которых своего id у полосы нет, и не
   приходится трогать разметку ради одной обвязки (А34, А67). */
function segToToggle(segId, leftId, rightId, leftText, rightText) {
  const l = document.getElementById(leftId), r = document.getElementById(rightId);
  const seg = segId ? document.getElementById(segId) : (l && l.closest('.seg'));
  if (!seg || !l || !r || seg._tgl) return;
  const tgl = makeToggle(leftText, rightText, r.classList.contains('active'), (v) => {
    (v === 'right' ? r : l).click();
  });
  seg.parentElement.insertBefore(tgl, seg);
  seg.style.display = 'none';
  seg._tgl = tgl;
  // Сцена могла переключить режим сама — держим тумблер в согласии с кнопками.
  const sync = () => tgl._set(r.classList.contains('active'));
  new MutationObserver(sync).observe(l, { attributes: true, attributeFilter: ['class'] });
  new MutationObserver(sync).observe(r, { attributes: true, attributeFilter: ['class'] });
}

/* ── Свой раскрывающийся список вместо нативного select (А64 · А32) ────────

   Нативный select не переносит текст: он просто РЕЖЕТ его. Замерено шрифтом,
   которым он рисуется: «Что добавляем» имел 179 px при нужных 208, выбор
   кривой в площадях — 128 при нужных 134. Отсюда и «Выберите криву» без
   последней буквы.

   Кроме того, серая системная коробочка выглядела чужеродно рядом с полями,
   где значение правится прямо в тексте.

   Переделываем ПОВЕРХ существующего select: он остаётся в разметке и остаётся
   источником правды, поэтому все прежние обработчики (change) продолжают
   работать, а сцены ничего не знают о подмене. Меню уезжает в body с
   position:fixed — панель прокручивается и обрезала бы его. */
const OPEN_SELECTS = new Set();

function closeAllSelectMenus(except) {
  OPEN_SELECTS.forEach(m => { if (m !== except) m._close(); });
}

function upgradeSelect(id, title) {
  const sel = document.getElementById(id);
  if (!sel || sel._upgraded) return;
  sel._upgraded = true;

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'sel-btn';
  btn.setAttribute('aria-haspopup', 'listbox');
  btn.setAttribute('aria-expanded', 'false');
  if (title) btn.title = title;

  const text = document.createElement('span');
  text.className = 'sel-text';
  const caret = document.createElement('span');
  caret.className = 'sel-caret';
  caret.textContent = '⌄';
  btn.append(text, caret);

  const paint = () => {
    const o = sel.options[sel.selectedIndex];
    text.textContent = o ? o.textContent.trim() : '';
    btn.classList.toggle('sel-empty', !!(o && o.value === ''));
  };
  paint();
  sel.classList.add('sel-native-hidden');
  sel.parentNode.insertBefore(btn, sel);
  sel._paint = paint;
  // Сцена может переставить значение сама — держим кнопку в согласии со списком.
  sel.addEventListener('change', paint);

  let menu = null;
  const close = () => {
    if (!menu) return;
    menu.remove(); menu = null;
    OPEN_SELECTS.delete(api);
    btn.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', onOutside, true);
    window.removeEventListener('resize', close);
    window.removeEventListener('scroll', close, true);
  };
  const api = { _close: close };

  function onOutside(e) { if (!menu || (!menu.contains(e.target) && e.target !== btn)) close(); }

  const open = () => {
    if (menu) { close(); return; }
    closeAllSelectMenus(api);
    menu = document.createElement('div');
    menu.className = 'sel-menu';
    menu.setAttribute('role', 'listbox');
    Array.prototype.forEach.call(sel.options, (o, i) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'sel-item' + (i === sel.selectedIndex ? ' active' : '');
      item.setAttribute('role', 'option');
      item.textContent = o.textContent.trim();
      item.addEventListener('click', () => {
        sel.value = o.value;
        paint();
        close();
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      });
      menu.appendChild(item);
    });
    document.body.appendChild(menu);
    const r = btn.getBoundingClientRect();
    // Ширина не меньше кнопки: вариант должен помещаться целиком.
    menu.style.minWidth = Math.max(r.width, 180) + 'px';
    menu.style.left = Math.max(6, Math.min(window.innerWidth - menu.offsetWidth - 6, r.left)) + 'px';
    const below = window.innerHeight - r.bottom;
    if (below > menu.offsetHeight + 8 || below > r.top) menu.style.top = (r.bottom + 4) + 'px';
    else menu.style.top = Math.max(6, r.top - menu.offsetHeight - 4) + 'px';
    OPEN_SELECTS.add(api);
    btn.setAttribute('aria-expanded', 'true');
    document.addEventListener('pointerdown', onOutside, true);
    window.addEventListener('resize', close);
    window.addEventListener('scroll', close, true);
  };

  btn.addEventListener('click', open);
  btn.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { close(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = sel.options.length;
      if (!n) return;
      sel.selectedIndex = (sel.selectedIndex + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
      paint();
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
}

/* Обычное текстовое поле → правка на месте (А6 · А66).

   Формулы уже набираются своим полем, а имена (кривой, страны, функции) до сих
   пор жили в серых прямоугольных окошках — в одном блоке оказывалось два
   разных способа ввода. Переделываем ПОВЕРХ поля: сам input остаётся в
   разметке и остаётся источником правды, поэтому все прежние обработчики
   («input», «change») продолжают работать. */
function upgradeTextField(inp, placeholder) {
  if (!inp || inp._textUp) return;
  inp._textUp = true;
  const hint = placeholder || inp.placeholder || 'без имени';
  const val = makeEditableValue({
    kind: 'text',
    get: () => inp.value || '',
    set: (v) => {
      inp.value = String(v == null ? '' : v);
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
    },
    fmt: (v) => (String(v || '').trim() || hint),
    title: inp.title || 'Щёлкните, чтобы изменить',
  });
  val.classList.add('edval-text');
  inp.classList.add('text-up-hidden');
  inp.parentNode.insertBefore(val, inp);
  inp._editable = val;
  return val;
}

// Оснастить все обычные текстовые поля внутри контейнера (кроме полей формул).
function upgradeTextFieldsIn(root) {
  const box = (typeof root === 'string') ? document.getElementById(root) : root;
  if (!box) return;
  box.querySelectorAll('input[type="text"]').forEach(inp => {
    if (inp._equipped || inp._mfDone) return;      // это поле формулы, у него свой вид
    if (inp.classList.contains('curve-expr-inp')) return;
    upgradeTextField(inp);
  });
}
