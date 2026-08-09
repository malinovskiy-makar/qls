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
  try { katex.render(tex, el, { throwOnError: false, displayMode: false }); }
  catch (e) { el.textContent = expr; }
}
// То же, но на вход уже готовый LaTeX (кусочная функция собирается сразу в него).
function renderTexRaw(el, tex) {
  if (!el) return;
  if (!tex) { el.textContent = ''; el.classList.remove('has'); return; }
  el.classList.add('has');
  if (typeof katex === 'undefined') { el.textContent = tex; return; }
  try { katex.render(tex, el, { throwOnError: false, displayMode: false }); }
  catch (e) { el.textContent = tex; }
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
      const endTag = '\end{' + env + '}';
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
  flushMathfields();
}

function flushMathfields() {
  if (!MATHLIVE_READY || !_sceneOpen || !_mfWaiting.length) return;
  const app = document.querySelector('.app');
  if (app && app.hasAttribute('inert')) return;    // сцена ещё под окном выбора
  while (_mfWaiting.length) {
    const inp = _mfWaiting.shift();
    try { buildMathfield(inp); } catch (e) { console.warn('Поле формулы:', e); inp._mfDone = false; }
  }
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
    smartMode: false,                      // «e» и «x» — переменные, а не слова
    smartFence: true,
    removeExtraneousParentheses: false,
  });
  mf.setAttribute('aria-label', inp.getAttribute('aria-label') || 'Формула');
  if (inp.placeholder) mf.setAttribute('placeholder', inp.placeholder);
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
  ['pointerdown', 'pointerup', 'focus'].forEach(ev => {
    mf.addEventListener(ev, () => { grabKeys(); setTimeout(grabKeys, 0); });
  });

  let syncing = false;
  const toInput = () => {
    if (syncing) return;
    syncing = true;
    try {
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
  [['xₙ', '#@_{#?}', '_'], ['√', '\\sqrt{#?}', 'sqrt()', 1], ['дробь', '\\frac{#@}{#?}', '/'],
   ['⌫', 'DEL'], ['стереть', 'CLEAR']],
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
  ['Анализ', [
    ['d/dx', '\\frac{d}{dx}', 'd/dx'],
    ['∫', '\\int_{#?}^{#?}', 'integral'],
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
    ['±', '\\pm ', '+-'], ['≈', '\\approx ', '=='],
  ]],
];

function mkbdKey(k, inp) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'mk';
  b.textContent = k[0];
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
function registerFormulaField(inp) {
  if (inp && FORMULA_FIELDS.indexOf(inp) < 0) FORMULA_FIELDS.push(inp);
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
  'ineq-formula': 'MATHF',
  'inp-ppf1': 'PPF', 'inp-ppf2': 'PPF', 'inp-ppft': 'PPF',
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

