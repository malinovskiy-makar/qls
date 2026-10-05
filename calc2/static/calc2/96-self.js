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
function checkGuess(answer, truth) {
  const a = selfNum(answer), b = selfNum(truth);
  if (a == null || b == null) return null;
  return Math.abs(a - b) <= Math.max(0.011, 0.0005 * Math.abs(b));
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
  const truth = val ? (val.textContent || '').trim() : '';
  const numeric = selfNum(truth) != null;
  const opened = SELF.all || SELF.open[id] || !numeric;
  cell.classList.toggle('self-hidden', SELF.on && !opened);
  if (!SELF.on || opened) { if (box) box.remove(); return; }
  if (box) return;
  box = document.createElement('div');
  box.className = 'self-box';
  const inp = document.createElement('input');
  inp.type = 'text'; inp.className = 'self-inp'; inp.inputMode = 'decimal'; inp.placeholder = '?';
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
    const cur = (cell.querySelector('.ans-val') || {}).textContent || '';
    const r = checkGuess(inp.value, cur);
    if (r == null) { toast('Впишите число, можно с запятой'); return; }
    SELF.verdict[id] = r; paintVerdict(); selfAfterAnswer();
  };
  inp.addEventListener('input', () => { SELF.typed[id] = inp.value; delete SELF.verdict[id]; paintVerdict(); });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); check(); } });
  chk.addEventListener('click', check);
  show.addEventListener('click', () => { SELF.open[id] = true; applySelf(); selfAfterAnswer(); });
  row.append(chk, show, pill);
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
    const truth = ((c.querySelector('.ans-val') || {}).textContent || '').trim();
    return SELF.open[id] || SELF.verdict[id] === true || selfNum(truth) == null;
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
}

/* Холст: выделенные значения на осях — обозначениями главных чисел, у
   ключевых точек «(?; ?)». Зовётся после каждой перерисовки (60-overlays). */
function selfCanvas() {
  if (!SELF.on || SELF.all) return;
  const chart = document.getElementById('chart');
  if (!chart) return;
  const heroes = [...document.querySelectorAll('#ans-hero .ans-cell')].map(c => ({
    not: ((c.querySelector('.ans-not') || {}).textContent || '').replace(/\s+/g, '').trim(),
    v: selfNum(((c.querySelector('.ans-val') || {}).textContent || '').trim()),
  })).filter(h => h.v != null);
  chart.querySelectorAll('text.coord-num').forEach(t => {
    // Подпись может нести индекс («60_b»): число — её начало.
    const m = /^\s*(-?[\d\s\u202f.,\u2212]+)/.exec(t.textContent || '');
    const v = m ? selfNum(m[1]) : null;
    if (v == null) return;
    const h = heroes.find(x => Math.abs(x.v - v) <= Math.max(0.011, 0.0005 * Math.abs(x.v)));
    t.textContent = h && h.not ? h.not : '?';
  });
  chart.querySelectorAll('g.cross-label text').forEach(t => { t.textContent = '(?; ?)'; });
}

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
