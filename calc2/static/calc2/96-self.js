// «Сначала сам» (редизайн 10.2026, фаза 9; README макета, раздел 9).
/* ---------------------------------------------------------------------
   Режим прячет числа ответа: главные числа становятся полями ответа с
   «Проверить» и «Показать»; бремя, таблицы, итоговая функция и «Разбор»
   закрыты пунктирной кнопкой «после ответа»; выделенные значения на осях —
   обозначениями; координаты ключевых точек — «(?; ?)»; свои точки — без
   координат, площади — «S₁ = ?». Числа движок считает как обычно: режим
   только прячет показ (паритет чисел снимается при выключенном режиме,
   COVERAGE, раздел 9, п. 5).

   Состояние режима — в документе (класс body.self-on) и в памяти страницы:
   вписанное помнится по моделям, вердикты снимает любая правка модели
   (событие calc2:history из 91-session.js).
   --------------------------------------------------------------------- */
const SELF = { on: false, all: false, typed: {}, open: {}, verdict: {} };

/* Допуск (README макета, 9): ответ и число ячейки читаются одинаково —
   убрать пробелы (в том числе U+202F и U+00A0), «−» → «-», запятая → точка.
   Верно, если |a − b| ≤ max(0,011; 0,0005·|b|). */
function selfNum(t) {
  const s = String(t == null ? '' : t).replace(/[\s   ]+/g, '').replace(/[−–]/g, '-').replace(',', '.');
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
  return parseFloat(s);
}
/* ОТВЕТ — НЕ ТОЛЬКО ОДНО ЧИСЛО (решение владельца 09.10, ADR 0143).
   Ответом считается: число; список чисел через «;»; точка «(x; y)»; список
   точек через «;»; «нет» (пустой список). Одно число — частный случай списка,
   поэтому экономические ячейки работают как раньше.
   Разбор: пробелы (и U+00A0, U+202F) не важны; «−», «–» и «-» — минус;
   запятая внутри числа — десятичная; «;» разделяет и список, и координаты
   внутри скобок; регистр «нет» не важен. Хвост «°» («∘») или «%» у числа ячейки
   (угол наклона, ставка) — подпись единицы, а не часть ответа.
   Вернёт { pts: bool, items: [[x], …] | [[x, y], …] } или null — не разобрали. */
const SELF_NUM = '-?\\d+(?:[.,]\\d+)?';
function selfParse(t) {
  let s = String(t == null ? '' : t).replace(/[\s\u00a0\u202f\u2009\u200b]+/g, '').replace(/[−–—]/g, '-').toLowerCase();
  if (!s) return null;
  if (s === 'нет') return { pts: null, items: [] };
  s = s.replace(/;$/, '');
  const num = (x) => parseFloat(x.replace(',', '.'));
  const PT = new RegExp('^\\((' + SELF_NUM + ');(' + SELF_NUM + ')\\)$');
  const N1 = new RegExp('^(' + SELF_NUM + ')[°∘%]?$');   // ∘ — градус, набранный KaTeX
  if (s.charAt(0) === '(') {
    const parts = s.match(/\([^()]*\)/g);
    if (!parts || parts.join(';') !== s) return null;
    const items = [];
    for (const p of parts) { const m = PT.exec(p); if (!m) return null; items.push([num(m[1]), num(m[2])]); }
    return { pts: true, items };
  }
  const items = [];
  for (const p of s.split(';')) { const m = N1.exec(p); if (!m) return null; items.push([num(m[1])]); }
  return { pts: false, items };
}
function selfClose(a, b) { return Math.abs(a - b) <= Math.max(0.011, 0.0005 * Math.abs(b)); }
/* Сравнение как мультимножеств: порядок не важен, число значений обязано
   совпасть, каждая координата — с прежним допуском. «нет» = пустой список.
   null — ответ человека не разобрался (вердикта нет). */
function checkGuess(answer, truth) {
  const a = selfParse(answer), b = selfParse(truth);
  if (a == null || b == null) return null;
  if (a.items.length !== b.items.length) return false;
  if (!b.items.length) return true;
  if (a.pts !== b.pts) return false;
  const used = new Array(b.items.length).fill(false);
  return a.items.every(g => {
    const k = b.items.findIndex((w, i) => !used[i] && w.every((v, j) => selfClose(g[j], v)));
    if (k < 0) return false;
    used[k] = true;
    return true;
  });
}
// Значение ячейки — ответ (а не поясняющий текст)?
function selfIsAnswer(truth) { return selfParse(truth) != null; }

// Текст узла без невидимой половины KaTeX (calc2/CLAUDE.md, ловушки).
function selfText(el) {
  if (!el) return '';
  const c = el.cloneNode(true);
  c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
  return c.textContent.replace(/\s+/g, ' ').trim();
}

function selfKey() { return (typeof modelKeyOf === 'function' ? modelKeyOf(STATE.sceneKey) : STATE.sceneKey) || ''; }

function setSelfMode(on) {
  SELF.on = !!on;
  if (!on) { SELF.typed = {}; SELF.open = {}; SELF.verdict = {}; SELF.all = false; }
  document.body.classList.toggle('self-on', SELF.on);
  const b = document.getElementById('btn-self');
  if (b) b.setAttribute('aria-pressed', SELF.on ? 'true' : 'false');
  applySelf();
  if (typeof redrawAll === 'function') redrawAll();
}

/* Ячейка главного числа в режиме: поле ответа, «Проверить», «Показать».
   Значение ячейки остаётся в разметке (его читает прибор паритета и
   проверка), режим только прячет его стилем. */
function selfCell(cell, idx) {
  const k = selfKey();
  const id = k + '#' + idx;
  let box = cell.querySelector(':scope > .self-box');
  const val = cell.querySelector('.ans-val');
  const truth = selfText(val);
  // Без поля и открытой остаётся только ячейка, значение которой не ответ вовсе.
  const opened = SELF.all || SELF.open[id] || !selfIsAnswer(truth);
  cell.classList.toggle('self-hidden', SELF.on && !opened);
  if (!SELF.on || opened) { if (box) box.remove(); return; }
  // Ячейка уже с полем: вердикт мог сброситься правкой — перекрашиваем.
  if (box) { if (box._paint) box._paint(); return; }
  box = document.createElement('div');
  box.className = 'self-box';
  const inp = document.createElement('input');
  inp.type = 'text'; inp.className = 'self-inp'; inp.placeholder = '?';
  const lab = (cell.querySelector('.ans-lab') || {}).textContent || '';
  inp.setAttribute('aria-label', 'Ваш ответ: ' + lab);
  inp.value = SELF.typed[id] || '';
  const row = document.createElement('div'); row.className = 'self-acts';
  const chk = document.createElement('button'); chk.type = 'button'; chk.className = 'self-check'; chk.textContent = 'Проверить';
  const show = document.createElement('button'); show.type = 'button'; show.className = 'self-show'; show.textContent = 'Показать';
  const pill = document.createElement('span'); pill.className = 'self-pill'; pill.setAttribute('role', 'status');
  const paintVerdict = () => {
    const v = SELF.verdict[id];
    pill.textContent = v === true ? '✓ верно' : (v === false ? '✗ не сходится' : '');
    pill.className = 'self-pill' + (v === true ? ' is-ok' : (v === false ? ' is-bad' : ''));
    inp.classList.toggle('is-ok', v === true); inp.classList.toggle('is-bad', v === false);
  };
  const check = () => {
    const cur = selfText(cell.querySelector('.ans-val'));
    const r = checkGuess(inp.value, cur);
    // Не разобрали — подсказка формата, вердикта нет. Неверно — только «не
    // сходится»: сколько значений не хватает, не выдаём.
    if (r == null) { toast('Впишите числа через «;», точку как (x; y) или «нет»'); return; }
    SELF.verdict[id] = r; paintVerdict(); selfAfterAnswer();
    /* Перерисовки здесь НЕТ намеренно: подпись ключевой точки собирается при
       каждом наведении и сама видит новый вердикт. Перерисовка будила проверку
       истории, та рассылала calc2:history, и вердикт тут же стирался. */
  };
  inp.addEventListener('input', () => { SELF.typed[id] = inp.value; delete SELF.verdict[id]; paintVerdict(); });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); check(); } });
  chk.addEventListener('click', check);
  show.addEventListener('click', () => { SELF.open[id] = true; applySelf(); selfAfterAnswer(); });
  row.append(chk, show, pill);
  box._paint = paintVerdict;
  box.append(inp, row);
  cell.appendChild(box);
  paintVerdict();
}

/* «После ответа»: все главные числа сошлись или открыты — остальное
   открывается само, с тостом (README макета, 9). */
function selfAfterAnswer() {
  if (!SELF.on || SELF.all) return;
  const k = selfKey();
  const cells = [...document.querySelectorAll('#ans-hero .ans-cell')];
  if (!cells.length) return;
  const done = cells.every((c, i) => {
    const id = k + '#' + i;
    const truth = selfText(c.querySelector('.ans-val'));
    return SELF.open[id] || SELF.verdict[id] === true || !selfIsAnswer(truth);
  });
  if (done) {
    SELF.all = true; applySelf(); if (typeof redrawAll === 'function') redrawAll();
    toast('Всё сошлось: таблица «было → стало» и итоговая функция открыты');
  }
}

function applySelf() {
  // Смена модели снимает «Показать всё»; вписанное помнится по моделям.
  const k = selfKey();
  if (SELF.lastKey !== k) { SELF.all = false; SELF.verdict = {}; SELF.lastKey = k; }
  document.body.classList.toggle('self-all', SELF.on && SELF.all);
  document.querySelectorAll('#ans-hero .ans-cell').forEach((c, i) => selfCell(c, i));
  const gate = document.getElementById('self-gate');
  if (gate) gate.hidden = !(SELF.on && !SELF.all);
  const note = document.getElementById('self-note');
  if (note) note.hidden = !SELF.on;
  const showAll = document.getElementById('self-showall');
  if (showAll) showAll.hidden = !(SELF.on && !SELF.all);
  const pending = document.querySelector('.col-answer .col-note');
  if (pending) pending.hidden = SELF.on && !SELF.all;
  // «Ответ» собирается кадром позже холста: обозначения на осях берём из
  // этой, свежей сборки (раньше холст размечался по прошлой).
  selfCanvas();
}

/* Холст: выделенные значения на осях — обозначениями главных чисел, у
   ключевых точек «(?; ?)». Зовётся после каждой перерисовки (60-overlays). */
function selfCanvas() {
  if (!SELF.on || SELF.all) return;
  const chart = document.getElementById('chart');
  if (!chart) return;
  // Значения главных ячеек: у списка и точки — каждое число по отдельности.
  const heroes = [];
  document.querySelectorAll('#ans-hero .ans-cell').forEach(c => {
    const not = selfText(c.querySelector('.ans-not')).replace(/\s+/g, '');
    const p = selfParse(selfText(c.querySelector('.ans-val')));
    if (p) p.items.forEach(it => it.forEach(v => heroes.push({ not, v })));
  });
  const yName = String(STATE.axisYDefault || 'P').charAt(0), xName = String(STATE.axisXDefault || 'Q').charAt(0);
  const svgBox = chart.getBoundingClientRect();
  chart.querySelectorAll('text.coord-num').forEach(t => {
    // Подпись может нести индекс («60_b», «40₁» — индекс отдельным узлом):
    // число — первый узел текста.
    const first = t.firstChild ? (t.firstChild.textContent || '') : '';
    const m = /^\s*(-?[\d\s\u202f.,\u2212]+)/.exec(first);
    const v = m ? selfNum(m[1]) : null;
    if (v == null) return;
    // Ось подписи: у вертикальной оси подпись стоит левее поля графика.
    const r = t.getBoundingClientRect();
    const onY = (r.right - svgBox.left) < (CONFIG.margin ? CONFIG.margin.left + 2 : 60);
    const near = heroes.filter(x => Math.abs(x.v - v) <= Math.max(0.011, 0.0005 * Math.abs(x.v)));
    const h = near.find(x => x.not.charAt(0) === (onY ? yName : xName)) || near[0];
    selfMaskText(t, h && h.not ? h.not : '?');
  });
  chart.querySelectorAll('g.cross-label text').forEach(t => { selfMaskText(t, '(?; ?)'); });
  /* Прочие подписи холста с числами ответа (README макета, 9): «Δy = ?»,
     «f′(x₀) = ?», координаты точек «(?; ?)», площади «S₁ = ?», «дефицит ?».
     Деления осей, имена осей и кривых, легенда и ставки («t = 20» — их задал
     сам человек) не трогаются. */
  const skip = 'g.tick, .tick, .axis-name, .curve-name, .legend, [data-legend-box], .chart-title, .graph-title, g.cross-label, text.coord-num';
  chart.querySelectorAll('text').forEach(t => {
    if (t.closest(skip)) return;
    const s = t.textContent || '';
    let out = null;
    if (/^\s*(Δy|Δ\s*y)\s*=/.test(s)) out = 'Δy = ?';
    else if (/f\s*['′]/.test(s) && /=/.test(s)) out = s.replace(/=.*$/, '= ?');
    else if (/\(\s*[−\-]?[\d.,\s\u202f]+;\s*[−\-]?[\d.,\s\u202f]+\)/.test(s)) out = s.replace(/\(\s*[−\-]?[\d.,\s\u202f]+;\s*[−\-]?[\d.,\s\u202f]+\)/g, '(?; ?)');
    else if (/^\s*S\s*[₀-₉\d]*\s*=/.test(s)) out = s.replace(/=.*$/, '= ?');
    else if (/^\s*(дефицит|избыток)\b/i.test(s)) out = s.replace(/[−\-]?\d[\d\s.,\u202f]*/g, '?');
    if (out != null && out !== s) selfMaskText(t, out);
  });
}

/* Спрятать число в подписи холста. Вместе с видимым текстом меняется и
   исходная разметка data-raw: из неё выгрузка .tex берёт текст подписи
   (72-export-tex.js), и без этого в файл уходило число, которого на экране
   нет. Холст перерисовывается заново на каждом кадре, так что разметка
   живёт до следующей перерисовки, как и сам текст. */
function selfMaskText(t, text) {
  t.textContent = text;
  if (t.hasAttribute('data-raw')) t.setAttribute('data-raw', text);
}

// Режим прячет числа (включён и «Показать всё» не нажато): этим пользуются
// выгрузка и печать — там те же «?», что на экране (поправка 04.10, README 9).
function selfMasked() { return !!(SELF.on && !SELF.all); }

function wireSelf() {
  const b = document.getElementById('btn-self');
  if (b) b.addEventListener('click', () => setSelfMode(!SELF.on));
  const all = document.getElementById('self-showall');
  if (all) all.addEventListener('click', () => { SELF.all = true; applySelf(); redrawAll(); });
  const gate = document.getElementById('self-gate');
  if (gate) gate.addEventListener('click', () => { SELF.all = true; applySelf(); redrawAll(); });
  // Любая правка модели, отмена и возврат снимают вердикты; вписанное остаётся.
  window.addEventListener('calc2:history', () => { SELF.verdict = {}; if (SELF.on) applySelf(); });
  // Ссылка с self=1 открывает модель в режиме (README макета, раздел 10).
  try { if (/(^#|[#&])self=1\b/.test(location.hash)) setSelfMode(true); } catch (e) {}
}
