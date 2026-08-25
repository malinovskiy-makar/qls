/* Прибор приёмки 25.08: вмешательство без равновесия, порядок правой панели,
   конструктор кусочной, точки вне четверти, скорость и вид сложения,
   аналитическая запись суммарной КПВ.

   Числа печатаются ВСЕГДА, а не только при провале: этим прибором снимаются
   и «до», и «после».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/priyomka_probe.mjs                # все наборы
     node calc2/tests/priyomka_probe.mjs В О            # только эти

   Наборы:
     В — вмешательство без равновесия (сдвиг S, поворот S, числа табло);
     П — порядок элементов карточки «Вмешательство государства»;
     К — конструктор кусочной: колонки внутри окна при 2/3/5 кусках, 1280/1440;
     О — точки вне первой четверти в видимом прямоугольнике;
     С — сложение: время кадра, вызовы формулы, точки пути, толщина/штрих/контраст;
     Р — аналитическая запись суммарной КПВ.

   ⚠️ ПРИБОР ОБЯЗАН САМ РАСКРЫТЬ ЭКРАН и сбросить прокрутку панелей: измерять
   только раскрытое — значит занижать (урок восьми вранья за пять сессий).
   Каждый признак снимается ДВУМЯ способами — числом и снимком.
*/
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SHOTS = process.env.PF_SHOTS || 'reports/calc2_priyomka_fixes/probe';

const want = process.argv.slice(2).map(s => s.toUpperCase());
const need = (name) => !want.length || want.includes(name);
fs.mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0;
const num = (v) => (typeof v === 'number' && isFinite(v)) ? (Math.round(v * 1e4) / 1e4) : String(v);
function show(label, got, wanted, tol) {
  if (wanted == null) { console.log('     ' + label + ' = ' + num(got)); return; }
  const good = typeof got === 'number' && isFinite(got) && Math.abs(got - wanted) <= tol;
  if (!good) bad++;
  console.log((good ? 'OK   ' : 'FAIL ') + label + ' = ' + num(got) + '   (ожид ' + wanted + ' ±' + tol + ')');
}
function flag(label, cond, detail) {
  if (!cond) bad++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (detail != null ? '  -> ' + detail : ''));
}
function note(s) { console.log('     ' + s); }
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 66 - s.length))); }

const HELP = `
/* Раскрыть ВСЁ, что сцена свернула, и сбросить прокрутку панелей. */
function pfExpandAll() {
  document.querySelectorAll('.crow-more').forEach(function (m) { m.classList.add('open'); });
  document.querySelectorAll('details').forEach(function (d) { d.open = true; });
  document.querySelectorAll('.sb-card.folded, .card.folded, .pchip-param.folded')
    .forEach(function (e) { e.classList.remove('folded'); });
  document.querySelectorAll('.fold-btn').forEach(function (b) {
    if (b.getAttribute('aria-expanded') !== 'true') b.click();
  });
  ['tools-panel', 'params-body', 'side-body', 'ex-body', 'info-body', 'sb-body']
    .forEach(function (id) { var e = document.getElementById(id); if (e) e.scrollTop = 0; });
  document.querySelectorAll('.panel, .side, .sb, .drawer, .side-scroll').forEach(function (e) { e.scrollTop = 0; });
}
/* Текст узла без невидимой копии формул для чтецов экрана. */
function pfText(el) {
  if (!el) return '';
  var c = el.cloneNode(true);
  c.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
  return c.textContent.replace(/\\s+/g, ' ').trim();
}
/* Налоговая сцена: свои кривые, свой вид вмешательства, своя ставка. */
function pfTaxSetup(dExpr, sExpr, type, form, rate) {
  resetSceneMemory();
  pickScene('taxes');
  var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
  var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
  if (d) updateCurveExpr(d, dExpr);
  if (s) updateCurveExpr(s, sExpr);
  setType(type);
  if (form) setTaxForm(form);
  setTax(rate);
  redrawAll();
}
/* Табло налоговой сцены одним объектом. */
function pfTaxSnap() {
  var te = STATE.taxEq;
  return {
    form: STATE.taxForm, subKind: STATE.subKind, kind: STATE.taxKind,
    type: STATE.intervType, rate: STATE.tax, active: !!STATE.taxActive,
    eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
    offEq: STATE.offEq ? { Q: STATE.offEq.Q, P: STATE.offEq.P } : null,
    Q: te ? te.Q : null, Pd: te ? te.Pb : null, Ps: te ? te.Ps : null,
    money: STATE.tx, budget: STATE.budget, dwl: STATE.dwl,
    cs: STATE.csTax, ps: STATE.psTax,
    hasAfterS: !!STATE.taxAfterS,
    curveOn: !!STATE.taxCurveOn,
    /* Сколько путей на холсте объявлено кривой после вмешательства. Числу в
       состоянии верить нельзя: врёт ровно разрыв между расчётом и отрисовкой. */
    afterPaths: document.querySelectorAll('path[stroke-dasharray="6 4"]').length,
    keys: pfText(document.getElementById('info-eq')),
    taxbox: pfText(document.getElementById('info-tax')),
    explain: pfText(document.getElementById('ex-body'))
  };
}
/* Цена, при которой НАРИСОВАННАЯ кривая после вмешательства обращается в ноль.
   Читаем сам путь на холсте, а не формулу: врать умеет ровно разрыв
   между расчётом и отрисовкой. */
function pfSupplyZeroPrice(sel) {
  var el = document.querySelector(sel);
  if (!el) return null;
  var pts = [];
  String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
    var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
    if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
  });
  if (pts.length < 2) return null;
  /* Ищем P при Q = 0 линейной экстраполяцией по двум первым точкам пути. */
  var a = pts[0], b = pts[1];
  if (Math.abs(b[0] - a[0]) < 1e-9) return a[1];
  var t = (0 - a[0]) / (b[0] - a[0]);
  return a[1] + t * (b[1] - a[1]);
}
/* Сколько путей рисует кривая после вмешательства и где она вообще есть. */
function pfShiftedPaths() {
  var out = [];
  document.querySelectorAll('path[data-after], path.after-s, path[data-shifted]').forEach(function (el) {
    out.push({ cls: el.getAttribute('class') || '', d: (el.getAttribute('d') || '').length });
  });
  return out;
}
/* Порядок элементов карточки «Вмешательство государства» сверху вниз.
   Идём по ВИДИМЫМ узлам всей правой панели и отмечаем те, что нас касаются:
   так видно и то, что элемент уехал из карточки в ленту регуляторов. */
function pfPanelOrder() {
  var marks = [
    ['вид вмешательства', '#sec-tax > .seg'],
    ['вид налога/субсидии', '#taxkind-row'],
    ['кто платит/получает', '#taxside-row'],
    ['ставка', '#tax-field'],
    ['регулируемая цена', '#pc-field'],
    ['объём квоты', '#quota-field'],
    ['цена в коридоре', '#quota-price-field'],
    ['подсказка', '#tax-hint'],
    ['было -> стало', '#chk-ghost']
  ];
  var panel = document.getElementById('params-panel');
  var out = [];
  marks.forEach(function (m) {
    var el = document.querySelector(m[1]);
    if (!el) { return; }
    var vis = !!(el.offsetParent || el.getClientRects().length);
    if (!vis) return;
    var r = el.getBoundingClientRect();
    var inCard = !!el.closest('#sec-tax');
    var inRibbon = !!el.closest('#params-body');
    out.push({ name: m[0], y: Math.round(r.top), inCard: inCard, inRibbon: inRibbon });
  });
  out.sort(function (a, b) { return a.y - b.y; });
  return out;
}
/* Конструктор кусочной: геометрия окна и колонок. */
function pfPwOpen(n) {
  /* Открываем конструктор у поля кривой спроса — тем же путём, что человек. */
  var inp = document.querySelector('#curve-list input[type=text], #curve-list .f-slot input');
  if (!inp) {
    var slot = document.querySelector('.f-slot > input');
    inp = slot || null;
  }
  openPiecewise(inp, 'Q');
  PW.n = n;
  renderPw();
  return true;
}
function pfPwGeom() {
  var card = document.querySelector('#pw-modal .modal-card');
  if (!card) return null;
  var cr = card.getBoundingClientRect();
  var rows = [];
  document.querySelectorAll('#pw-rows .pw-row').forEach(function (row, i) {
    var slot = row.querySelector('.f-slot');
    var mf = row.querySelector('math-field');
    var bounds = row.querySelectorAll('input.pw-bound');
    var whens = row.querySelectorAll('.pw-when');
    var rr = row.getBoundingClientRect();
    var last = null;
    if (bounds.length) last = bounds[bounds.length - 1].getBoundingClientRect();
    rows.push({
      i: i,
      rowW: Math.round(rr.width), rowRight: Math.round(rr.right),
      slotW: slot ? Math.round(slot.getBoundingClientRect().width) : null,
      mfW: mf ? Math.round(mf.getBoundingClientRect().width) : null,
      boundW: bounds.length ? Math.round(bounds[0].getBoundingClientRect().width) : null,
      lastRight: last ? Math.round(last.right) : null,
      whenN: whens.length,
      /* Сумма собственных ширин детей строки: если она больше ширины строки,
         часть колонок физически не поместилась. */
      needW: Math.round(Array.prototype.reduce.call(row.children, function (s, ch) {
        return s + ch.getBoundingClientRect().width;
      }, 0) + 6 * Math.max(0, row.children.length - 1))
    });
  });
  var prev = document.getElementById('pw-preview');
  var pr = prev ? prev.getBoundingClientRect() : null;
  return {
    cardW: Math.round(cr.width), cardLeft: Math.round(cr.left), cardRight: Math.round(cr.right),
    cardH: Math.round(cr.height), scrollW: card.scrollWidth, clientW: card.clientWidth,
    winW: window.innerWidth,
    rows: rows,
    previewClipped: pr ? (pr.right > cr.right + 1 || pr.left < cr.left - 1) : null,
    previewRight: pr ? Math.round(pr.right) : null
  };
}
function pfPwClose() { var b = document.getElementById('pw-close'); if (b) b.click(); }
/* Лежит ли точка внутри видимого прямоугольника, и с каким запасом по краю. */
function pfPointInView(Q, P) {
  var qa = CONFIG.Qmin, qb = CONFIG.Qmax, pa = CONFIG.Pmin, pb = CONFIG.Pmax;
  var dq = qb - qa, dp = pb - pa;
  return {
    inside: (Q > qa && Q < qb && P > pa && P < pb),
    /* Запас до ближайшего края в долях окна: 0 значит «лежит на границе». */
    marginQ: Math.min(Q - qa, qb - Q) / dq,
    marginP: Math.min(P - pa, pb - P) / dp,
    win: { qa: qa, qb: qb, pa: pa, pb: pb }
  };
}
/* Сцена сложения: столько-то групп, у каждой своя формула. */
function pfSumSetup(dExprs, sExprs) {
  resetSceneMemory();
  pickScene('sdsum');
  sumSetCount('D', dExprs.length);
  sumSetCount('S', sExprs.length);
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  dExprs.forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
  sExprs.forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
  if (typeof renderCurveList === 'function') renderCurveList();
  redrawAll();
}
/* Числа сцены сложения — то, что не должно сдвинуться ни в одном знаке. */
function pfSumNumbers() {
  return {
    eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
    cs: STATE.cs, ps: STATE.ps, sw: STATE.sw,
    breaksD: (STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'D'; }) || {}).sumBreaks || [],
    breaksS: (STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'S'; }) || {}).sumBreaks || [],
    ghostD: (STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'D'; }) || {}).sumGhostTo || 0,
    ghostS: (STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'S'; }) || {}).sumGhostTo || 0,
    exprD: (STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'D'; }) || {}).expr || '',
    exprS: (STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'S'; }) || {}).expr || '',
    warn: (function () {
      var t = pfText(document.getElementById('info-eq')) + ' ' + pfText(document.getElementById('sb-body'));
      return /расхожден|не сошл|расчёт разошёлся/i.test(t);
    })()
  };
}
/* Вид всех кривых сцены: цвет, толщина, штрих, прозрачность, число точек пути. */
function pfCurveLook() {
  var out = [];
  document.querySelectorAll('path[data-curve]').forEach(function (el) {
    var id = +el.getAttribute('data-curve');
    var cur = STATE.curves.find(function (c) { return c.id === id; });
    var cs = getComputedStyle(el);
    var d = el.getAttribute('d') || '';
    out.push({
      id: id,
      name: cur ? (cur.label || ('#' + id)) : ('#' + id),
      kind: cur ? (cur.kind || '') : '',
      side: cur ? (cur.sumGroup || '') : '',
      part: el.getAttribute('data-sum-part') || '',
      stroke: cs.stroke, width: parseFloat(cs.strokeWidth),
      dash: (cs.strokeDasharray === 'none' ? '' : cs.strokeDasharray),
      opacity: parseFloat(cs.opacity || '1'),
      pts: (d.match(/[ML]/g) || []).length
    });
  });
  /* Заливка под суммарной кривой, если она есть. */
  document.querySelectorAll('path[data-sum-fill]').forEach(function (el) {
    var cs = getComputedStyle(el);
    out.push({ id: 'fill', name: 'заливка под суммой', kind: 'fill', side: el.getAttribute('data-sum-fill'),
      part: '', stroke: cs.fill, width: 0, dash: '', opacity: parseFloat(cs.opacity || '1'), pts: 0 });
  });
  return out;
}
/* Относительная светлота и контраст двух цветов (WCAG). */
function pfLum(rgb) {
  var f = rgb.map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
}
function pfRGB(s) {
  s = String(s == null ? '' : s).trim();
  if (!s || s === 'none' || s === 'transparent') return null;
  if (s.charAt(0) === '#') {
    var h = s.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  var m = s.match(/rgba?\\(([^)]+)\\)/);
  if (m) { var p = m[1].split(/[,\\s\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2]]; }
  return null;
}
function pfContrast(a, b) {
  var la = pfLum(a), lb = pfLum(b);
  var hi = Math.max(la, lb), lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}
/* Цвет холста темы. */
function pfCanvasRGB() {
  var v = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
  return pfRGB(v) || [255, 255, 255];
}
/* Итоговый цвет полупрозрачной линии на холсте. */
function pfBlend(c, alpha, bg) {
  return [0, 1, 2].map(function (i) { return c[i] * alpha + bg[i] * (1 - alpha); });
}
/* Счётчик вызовов формулы кривой: обёртка вокруг evalCurve на время замера. */
function pfCountStart() {
  if (window._pfOrigEval) return;
  window._pfOrigEval = evalCurve;
  window._pfCalls = 0;
  window.evalCurve = function () { window._pfCalls++; return window._pfOrigEval.apply(null, arguments); };
}
function pfCountStop() {
  if (!window._pfOrigEval) return 0;
  window.evalCurve = window._pfOrigEval;
  window._pfOrigEval = null;
  return window._pfCalls;
}
/* Время кадра панорамирования: сдвигаем окно, как это делает мышь, и мерим
   ПОЛНУЮ перерисовку. 60 шагов, три прогона, берём медиану. */
function pfPanTiming(steps) {
  var runs = [];
  for (var r = 0; r < 3; r++) {
    var dq = (CONFIG.Qmax - CONFIG.Qmin) * 0.004;
    var t0 = performance.now();
    for (var i = 0; i < steps; i++) {
      CONFIG.Qmin += dq; CONFIG.Qmax += dq;
      redrawAll();
    }
    var t1 = performance.now();
    CONFIG.Qmin -= dq * steps; CONFIG.Qmax -= dq * steps;
    redrawAll();
    runs.push((t1 - t0) / steps);
  }
  runs.sort(function (a, b) { return a - b; });
  return { median: runs[1], all: runs };
}

/* ⚠️ ЧЕСТНОЕ «ДО И ПОСЛЕ» МЕРИТСЯ ЧЕРЕДОВАНИЕМ В ОДНОМ СЕАНСЕ.
   Замер подряд врёт: третий прогон медленнее первого на четверть даже при
   одинаковом коде (сборка мусора, разогрев, тепловой режим машины). Замер
   25.08: «без drawCurves» получилось 48 мс против 39 мс «как есть» — то есть
   выключение работы «замедлило» кадр. Поэтому оба состояния мерятся
   ПООЧЕРЁДНО, по многу раз, и берётся медиана каждого: общий дрейф ложится
   на оба одинаково и из разницы уходит.

   «Прежнее поведение» воспроизводится буквально:
     • кривые снова строятся по сетке (piecewiseNodesQ отключён);
     • табло снова переписывается на каждом кадре (снимаем память о тексте). */
function pfPanTimingAB(steps, rounds) {
  var origNodes = window.piecewiseNodesQ;
  var boxes = ['info-eq', 'info-areas', 'info-sum', 'info-tax'].map(function (id) {
    return document.getElementById(id);
  }).filter(Boolean);
  var before = [], after = [];
  var pan = function (old) {
    var dq = (CONFIG.Qmax - CONFIG.Qmin) * 0.004;
    var t0 = performance.now();
    for (var i = 0; i < steps; i++) {
      if (old) boxes.forEach(function (b) { b._srcHtml = null; });
      CONFIG.Qmin += dq; CONFIG.Qmax += dq;
      redrawAll();
    }
    var t1 = performance.now();
    CONFIG.Qmin -= dq * steps; CONFIG.Qmax -= dq * steps;
    redrawAll();
    return (t1 - t0) / steps;
  };
  for (var r = 0; r < (rounds || 5); r++) {
    window.piecewiseNodesQ = function () { return null; };
    before.push(pan(true));
    window.piecewiseNodesQ = origNodes;
    after.push(pan(false));
  }
  window.piecewiseNodesQ = origNodes;
  var med = function (a) { var b = a.slice().sort(function (x, y) { return x - y; });
    return b[Math.floor(b.length / 2)]; };
  return { before: med(before), after: med(after), beforeAll: before, afterAll: after };
}

/* Вызовов формулы за кадр при прежнем и нынешнем поведении — тем же чередованием. */
function pfCallsAB() {
  var origNodes = window.piecewiseNodesQ;
  window.piecewiseNodesQ = function () { return null; };
  var before = pfCallsPerFrame();
  window.piecewiseNodesQ = origNodes;
  var after = pfCallsPerFrame();
  return { before: before, after: after };
}
/* Сколько раз формула зовётся за ОДИН кадр панорамирования. */
function pfCallsPerFrame() {
  var dq = (CONFIG.Qmax - CONFIG.Qmin) * 0.004;
  redrawAll();
  pfCountStart();
  CONFIG.Qmin += dq; CONFIG.Qmax += dq;
  redrawAll();
  var n = pfCountStop();
  CONFIG.Qmin -= dq; CONFIG.Qmax -= dq;
  redrawAll();
  return n;
}
/* Сцена сложения КПВ: столько-то кривых, у каждой формула. */
function pfPpfSetup(exprs) {
  resetSceneMemory();
  pickScene('ppfsum');
  STATE.ppfSumCount = exprs.length;
  exprs.forEach(function (e, i) { ppfSumSet(i, e); });
  STATE.ppfSumData = null;
  if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
  redrawAll();
  ensurePpfSum();
  redrawAll();
}
/* Что показано в «Форме кривой» — и обычным текстом, и математикой. */
function pfPpfForm() {
  var d = STATE.ppfSumData;
  var box = document.getElementById('info-ppfsum');
  var html = box ? box.innerHTML : '';
  /* Ищем абзац «Форма кривой». */
  var text = '';
  if (box) {
    box.querySelectorAll('p').forEach(function (p) {
      if (/Форма кривой/i.test(p.textContent)) text = pfText(p);
    });
  }
  var mathN = 0;
  if (box) {
    box.querySelectorAll('p').forEach(function (p) {
      if (/Форма кривой/i.test(p.textContent)) mathN += p.querySelectorAll('.katex').length;
    });
  }
  return {
    ok: !!(d && d.ok), n: d ? d.n : null,
    formulaText: d ? d.formulaText : null,
    type: d ? d.type : null,
    kinks: d ? (d.kinks || []) : [],
    pieces: d ? (d.formulaPieces || null) : null,
    panelText: text, katexInForm: mathN,
    /* Не вылезает ли запись за ширину панели. */
    overflow: (function () {
      if (!box) return null;
      var w = box.clientWidth, sw = box.scrollWidth;
      return { clientW: w, scrollW: sw, over: sw - w };
    })()
  };
}
`;

await page.addScriptTag({ content: HELP });
const ev = (fn, ...args) => page.evaluate(fn, ...args);
async function reinject() { await page.addScriptTag({ content: HELP }); }
async function setTheme(t) {
  await page.evaluate((th) => {
    document.documentElement.setAttribute('data-theme', th);
  }, t);
  await page.waitForTimeout(250);
}
async function shot(name) {
  await ev(() => pfExpandAll());
  await page.waitForTimeout(120);
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
  return `${SHOTS}/${name}.png`;
}

/* ────────────────────────────────────────────────────────────────────
   ФАЗА −1: сверка с реальностью — контрольные числа прошлых сессий.
   ──────────────────────────────────────────────────────────────────── */
if (need('БАЗА')) {
  head('БАЗА. Контрольные числа прошлых сессий');
  // Сложение: D 100-Q, 60-Q, 40-Q; S Q-100, Q+20 -> Q* 128, P* 24, PS 2696, SW 6360
  await ev(() => pfSumSetup(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']));
  let s = await ev(() => pfSumNumbers());
  show('сложение Q*', s.eq && s.eq.Q, 128, 0.05);
  show('сложение P*', s.eq && s.eq.P, 24, 0.05);
  show('сложение PS', s.ps, 2696, 1);
  show('сложение SW', s.sw, 6360, 1);
  flag('предупреждения о расхождении нет', !s.warn, 'warn=' + s.warn);

  // Налоги: D 120-Q, S Q; потоварный 40, акциз 50 %, НДС 100 %
  for (const [nm, form, rate] of [['потоварный 40', 'unit', 40], ['акциз 50 %', 'excise', 50], ['НДС 100 %', 'vat', 100]]) {
    await ev(([f, r]) => pfTaxSetup('120-Q', 'Q', 'tax', f, r), [form, rate]);
    const t = await ev(() => pfTaxSnap());
    show(nm + ': Q', t.Q, 40, 0.05);
    show(nm + ': Pd', t.Pd, 80, 0.05);
    show(nm + ': Ps', t.Ps, 40, 0.05);
    show(nm + ': сбор', t.money, 1600, 1);
    show(nm + ': DWL', t.dwl, 400, 1);
  }

  // Монополия: D 100-Q, MC 20 при окне до Q = 30 -> Qm 40, Pm 60, Qc 80
  const mono = await ev(() => {
    resetSceneMemory();
    pickScene('mono');
    const d = STATE.curves.find(c => c.role === 'demand');
    if (d) updateCurveExpr(d, '100-Q');
    let mc = STATE.curves.find(c => c.role === 'mc');
    if (mc) updateCurveExpr(mc, '20');
    redrawAll();
    CONFIG.Qmin = 0; CONFIG.Qmax = 30; CONFIG.Pmin = 0; CONFIG.Pmax = 30;
    STATE.viewDirty = true;
    redrawAll();
    return { Qm: STATE.mono && STATE.mono.Qm, Pm: STATE.mono && STATE.mono.Pm, Qc: STATE.mono && STATE.mono.Qc };
  });
  show('монополия Qm (окно до 30)', mono.Qm, 40, 0.05);
  show('монополия Pm', mono.Pm, 60, 0.05);
  show('монополия Qc', mono.Qc, 80, 0.05);
}

/* ────────────────────────────────────────────────────────────────────
   НАБОР В: вмешательство без равновесия.
   ──────────────────────────────────────────────────────────────────── */
if (need('В')) {
  head('НАБОР В. Вмешательство без равновесия (D 100-P, S 0.5*p-200)');
  // (0) Без вмешательства: равновесия нет, абзац про пересечение (-100; 200).
  await ev(() => pfTaxSetup('100-P', '0.5*p-200', 'tax', 'unit', 0));
  let t0 = await ev(() => pfTaxSnap());
  flag('равновесия нет', !t0.eq, 'eq=' + JSON.stringify(t0.eq));
  note('offEq = ' + JSON.stringify(t0.offEq));
  flag('абзац про пересечение вне четверти есть', /пересеч/i.test(t0.explain),
    'explain(' + t0.explain.length + ' симв) содержит «пересеч»: ' + /пересеч/i.test(t0.explain));
  const zero0 = await ev(() => {
    const s = STATE.curves.find(c => c.role === 'supply');
    return s ? evalCurve(s, 0) : null;
  });
  show('S без налога: цена при Q=0', zero0, 400, 0.5);

  // (а) Потоварный налог 100.
  await ev(() => pfTaxSetup('100-P', '0.5*p-200', 'tax', 'unit', 100));
  let ta = await ev(() => pfTaxSnap());
  /* Равновесия здесь по-прежнему нет — и это правильный ответ, а не провал:
     S + 100 уходит ещё дальше от спроса. Проверяем именно это. */
  flag('а) равновесия по-прежнему нет', !ta.eq && !ta.active, 'eq=' + JSON.stringify(ta.eq) + ' active=' + ta.active);
  flag('а) кривая после налога построена (STATE.taxAfterS)', ta.hasAfterS, 'hasAfterS=' + ta.hasAfterS);
  flag('а) кривая после налога РИСУЕТСЯ на холсте', ta.afterPaths > 0, 'путей после вмешательства: ' + ta.afterPaths);
  const zeroA = await ev(() => (STATE.taxAfterS ? STATE.taxAfterS.fn(0) : null));
  show('а) S после налога: цена при Q=0', zeroA, 500, 0.5);
  flag('а) DWL не показан', !(ta.dwl > 0), 'dwl=' + ta.dwl);
  note('а) табло: Q=' + ta.Q + ' Pd=' + ta.Pd + ' Ps=' + ta.Ps + ' сбор=' + ta.money);
  await shot('V-a-unit100');

  // (б) Потоварная субсидия 450.
  await ev(() => pfTaxSetup('100-P', '0.5*p-200', 'subsidy', 'unit', 450));
  let tb = await ev(() => pfTaxSnap());
  flag('б) subsidy taxActive', tb.active, 'active=' + tb.active);
  show('б) Q', tb.Q, 50, 0.1);
  show('б) цена покупателя', tb.Pd, 50, 0.1);
  show('б) цена продавца', tb.Ps, 500, 0.1);
  show('б) расход бюджета', Math.abs(tb.budget), 22500, 5);
  flag('б) DWL НЕ показан', !(tb.dwl > 0), 'dwl=' + tb.dwl);
  flag('б) сказано словами, что сравнивать не с чем',
    /сравнивать не с чем|не с чем сравн|исходного равновесия/i.test(tb.taxbox + ' ' + tb.keys + ' ' + tb.explain),
    'найдено: ' + /сравнивать не с чем|не с чем сравн|исходного равновесия/i.test(tb.taxbox + ' ' + tb.keys + ' ' + tb.explain));
  note('б) «Ключевые значения»: ' + tb.keys.slice(0, 400));
  await shot('V-b-sub450');
}

/* ────────────────────────────────────────────────────────────────────
   НАБОР П: порядок в правой панели.
   ──────────────────────────────────────────────────────────────────── */
if (need('П')) {
  head('НАБОР П. Порядок элементов карточки «Вмешательство государства»');
  const KINDS = [
    ['налог потоварный', 'tax', 'unit'],
    ['налог акциз', 'tax', 'excise'],
    ['налог НДС', 'tax', 'vat'],
    ['субсидия потоварная', 'subsidy', 'unit'],
    ['субсидия от цены покупателя', 'subsidy', 'subbuyer'],
    ['субсидия от цены продавца', 'subsidy', 'subseller'],
    ['потолок', 'ceiling', null],
    ['пол', 'floor', null],
    ['квота', 'quota', null],
  ];
  for (const [nm, type, form] of KINDS) {
    await ev(([ty, f]) => pfTaxSetup('120-Q', 'Q', ty, f, 20), [type, form]);
    await ev(() => pfExpandAll());
    const ord = await ev(() => pfPanelOrder());
    note(nm + ':');
    ord.forEach((o, i) => note('   ' + (i + 1) + '. ' + o.name
      + (o.inRibbon ? '  [ЛЕНТА РЕГУЛЯТОРОВ]' : (o.inCard ? '  [карточка]' : '  [?]')) + '  y=' + o.y));
    const iSide = ord.findIndex(o => o.name === 'кто платит/получает');
    const iRate = ord.findIndex(o => o.name === 'ставка' || o.name === 'регулируемая цена' || o.name === 'объём квоты');
    if (iSide >= 0 && iRate >= 0) flag(nm + ': ряд «кто платит» ВЫШЕ ставки', iSide < iRate, 'side=' + iSide + ' rate=' + iRate);
    const inRibbon = ord.filter(o => o.inRibbon).map(o => o.name);
    flag(nm + ': в ленте регуляторов ставки нет', inRibbon.length === 0, 'в ленте: ' + JSON.stringify(inRibbon));
  }
  await ev(() => pfTaxSetup('120-Q', 'Q', 'tax', 'unit', 40));
  await shot('P-order-tax');
  await ev(() => pfTaxSetup('120-Q', 'Q', 'subsidy', 'unit', 40));
  await shot('P-order-sub');
}

/* ────────────────────────────────────────────────────────────────────
   НАБОР К: конструктор кусочной помещается в окно.
   ──────────────────────────────────────────────────────────────────── */
if (need('К')) {
  head('НАБОР К. Конструктор кусочной: колонки внутри окна');
  for (const W of [1280, 1440]) {
    await page.setViewportSize({ width: W, height: 950 });
    await page.waitForTimeout(200);
    await reinject();
    await ev(() => { resetSceneMemory(); pickScene('sd'); redrawAll(); });
    for (const n of [2, 3, 5]) {
      await ev((k) => pfPwOpen(k), n);
      await page.waitForTimeout(320);
      const g = await ev(() => pfPwGeom());
      if (!g) { flag(`${W}px, ${n} кусков: окно найдено`, false, 'нет .modal-card'); continue; }
      note(`${W}px, ${n} кусков: окно ${g.cardW}px (${(100 * g.cardW / g.winW).toFixed(1)} % ширины браузера), `
        + `left=${g.cardLeft} right=${g.cardRight}, scrollW=${g.scrollW} clientW=${g.clientW}`);
      g.rows.forEach(r => note(`   строка ${r.i + 1}: строка ${r.rowW}px, формула ${r.mfW || r.slotW}px, `
        + `граница ${r.boundW}px, нужно ${r.needW}px, правый край последней «До» = ${r.lastRight}`));
      const overflow = g.rows.filter(r => r.needW > r.rowW + 1);
      flag(`${W}px, ${n} кусков: все колонки помещаются в строку`, overflow.length === 0,
        'не поместилось строк: ' + overflow.length + ' ' + JSON.stringify(overflow.map(r => [r.needW, r.rowW])));
      const outside = g.rows.filter(r => r.lastRight != null && r.lastRight > g.cardRight + 1);
      flag(`${W}px, ${n} кусков: колонка «До» внутри окна`, outside.length === 0,
        'вылезло строк: ' + outside.length);
      flag(`${W}px, ${n} кусков: окно не шире 92 % браузера`, g.cardW <= g.winW * 0.92,
        `${g.cardW} / ${g.winW} = ${(100 * g.cardW / g.winW).toFixed(1)} %`);
      flag(`${W}px, ${n} кусков: горизонтальной прокрутки окна нет`, g.scrollW <= g.clientW + 1,
        `scrollW=${g.scrollW} clientW=${g.clientW}`);
      flag(`${W}px, ${n} кусков: «Что получится» не обрезан`, g.previewClipped === false || g.previewClipped === null,
        'previewClipped=' + g.previewClipped + ' right=' + g.previewRight);
      if (n === 5) await shot(`K-${W}-5`);
      await ev(() => pfPwClose());
      await page.waitForTimeout(150);
    }
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await reinject();
}

/* ────────────────────────────────────────────────────────────────────
   НАБОР О: точки вне первой четверти попадают в кадр.
   ──────────────────────────────────────────────────────────────────── */
if (need('О')) {
  head('НАБОР О. Снятая галочка и точки вне первой четверти');
  // 1) D 100-P, S 0.5*p-200 -> точка пересечения (-100; 200)
  await ev(() => pfTaxSetup('100-P', '0.5*p-200', 'tax', 'unit', 0));
  let w = await ev(() => { setFirstQuad(false); return pfPointInView(-100, 200); });
  note('1) пересечение вне четверти (-100; 200): окно ' + JSON.stringify(w.win));
  flag('1) точка внутри видимого прямоугольника', w.inside, JSON.stringify(w));
  flag('1) точка не на границе (запас > 2 %)', w.inside && w.marginQ > 0.02 && w.marginP > 0.02,
    'marginQ=' + num(w.marginQ) + ' marginP=' + num(w.marginP));
  await shot('O-1-crossing');
  let back = await ev(() => { setFirstQuad(true); return { qa: CONFIG.Qmin, pa: CONFIG.Pmin }; });
  flag('1) обратное включение вернуло в первую четверть', back.qa >= -1e-9 && back.pa >= -1e-9, JSON.stringify(back));

  // 2) «Налоги и субсидии», D 120-Q, S 0.5*Q+30, акциз 25 % -> центр поворота (-60; 0)
  await ev(() => pfTaxSetup('120-Q', '0.5*Q+30', 'tax', 'excise', 25));
  w = await ev(() => { setFirstQuad(false); return pfPointInView(-60, 0); });
  note('2) центр поворота (-60; 0): окно ' + JSON.stringify(w.win));
  flag('2) точка внутри видимого прямоугольника', w.inside, JSON.stringify(w));
  flag('2) точка не на границе (запас > 2 %)', w.inside && w.marginQ > 0.02 && w.marginP > 0.02,
    'marginQ=' + num(w.marginQ) + ' marginP=' + num(w.marginP));
  await shot('O-2-pivot');
  back = await ev(() => { setFirstQuad(true); return { qa: CONFIG.Qmin, pa: CONFIG.Pmin }; });
  flag('2) обратное включение вернуло в первую четверть', back.qa >= -1e-9 && back.pa >= -1e-9, JSON.stringify(back));

  // 3) монополия D 100-Q, MC 20 -> конец продолжения MR (100; -100)
  await ev(() => {
    resetSceneMemory(); pickScene('mono');
    const d = STATE.curves.find(c => c.role === 'demand');
    if (d) updateCurveExpr(d, '100-Q');
    const mc = STATE.curves.find(c => c.role === 'mc');
    if (mc) updateCurveExpr(mc, '20');
    redrawAll();
  });
  w = await ev(() => { setFirstQuad(false); return pfPointInView(100, -100); });
  note('3) конец продолжения MR (100; -100): окно ' + JSON.stringify(w.win));
  flag('3) точка внутри видимого прямоугольника', w.inside, JSON.stringify(w));
  flag('3) точка не на границе (запас > 2 %)', w.inside && w.marginQ > 0.02 && w.marginP > 0.02,
    'marginQ=' + num(w.marginQ) + ' marginP=' + num(w.marginP));
  await shot('O-3-mr');
  back = await ev(() => { setFirstQuad(true); return { qa: CONFIG.Qmin, pa: CONFIG.Pmin }; });
  flag('3) обратное включение вернуло в первую четверть', back.qa >= -1e-9 && back.pa >= -1e-9, JSON.stringify(back));

  /* Разовость: после снятия галочки человек распоряжается окном сам —
     колесо и панорама не имеют права вернуть окно обратно. */
  const once = await ev(() => {
    resetSceneMemory(); pickScene('taxes');
    const d = STATE.curves.find(c => c.role === 'demand');
    const s2 = STATE.curves.find(c => c.role === 'supply');
    if (d) updateCurveExpr(d, '100-P');
    if (s2) updateCurveExpr(s2, '0.5*p-200');
    setType('tax'); setTaxForm('unit'); setTax(0); redrawAll();
    setFirstQuad(false);
    const afterUncheck = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    // Панорама на 10 % вправо — как мышью.
    const dq = (CONFIG.Qmax - CONFIG.Qmin) * 0.1;
    CONFIG.Qmin += dq; CONFIG.Qmax += dq; redrawAll();
    const afterPan = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    // Зум: сузили окно вдвое.
    const mid = (CONFIG.Qmin + CONFIG.Qmax) / 2, half = (CONFIG.Qmax - CONFIG.Qmin) / 4;
    CONFIG.Qmin = mid - half; CONFIG.Qmax = mid + half; redrawAll();
    const afterZoom = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    return { afterUncheck, afterPan, afterZoom, dq,
      resetExists: !!document.getElementById('btn-view-reset'),
      dirty: !!STATE.viewDirty };
  });
  note('после снятия: ' + JSON.stringify(once.afterUncheck));
  note('после панорамы: ' + JSON.stringify(once.afterPan));
  note('после зума:     ' + JSON.stringify(once.afterZoom));
  flag('окно не прыгает обратно после панорамы',
    Math.abs(once.afterPan.qa - (once.afterUncheck.qa + once.dq)) < 1e-6, JSON.stringify(once.afterPan));
  flag('окно не прыгает обратно после зума',
    once.afterZoom.qb - once.afterZoom.qa < (once.afterPan.qb - once.afterPan.qa) * 0.6,
    'ширина ' + num(once.afterZoom.qb - once.afterZoom.qa) + ' против ' + num(once.afterPan.qb - once.afterPan.qa));
  flag('кнопка «Вернуть исходный вид» на месте', once.dirty, 'viewDirty=' + once.dirty);

  // При ВКЛЮЧЁННОЙ галочке не меняется ничего.
  const onCheck = await ev(() => {
    resetSceneMemory(); pickScene('taxes');
    const d = STATE.curves.find(c => c.role === 'demand');
    const s2 = STATE.curves.find(c => c.role === 'supply');
    if (d) updateCurveExpr(d, '100-P');
    if (s2) updateCurveExpr(s2, '0.5*p-200');
    redrawAll();
    const a = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    setFirstQuad(true);
    const b = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    return { a, b };
  });
  flag('при включённой галочке окно не тронуто',
    JSON.stringify(onCheck.a) === JSON.stringify(onCheck.b),
    JSON.stringify(onCheck.a) + ' -> ' + JSON.stringify(onCheck.b));

  // Показывать нечего -> окно не трогается.
  const same = await ev(() => {
    resetSceneMemory(); pickScene('sd');
    const d = STATE.curves.find(c => c.role === 'demand');
    const s = STATE.curves.find(c => c.role === 'supply');
    if (d) updateCurveExpr(d, '100-Q');
    if (s) updateCurveExpr(s, 'Q');
    redrawAll();
    const before = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    setFirstQuad(false);
    const after = { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
    setFirstQuad(true);
    return { before, after };
  });
  note('нечего показывать: до ' + JSON.stringify(same.before) + ' -> после ' + JSON.stringify(same.after));
  flag('нечего показывать — лишнего расширения нет',
    Math.abs(same.after.qa - (-(same.before.qb - same.before.qa) * 0.25)) < 1e-6
    && Math.abs(same.after.qb - same.before.qb) < 1e-6,
    JSON.stringify(same.after));
}

/* ────────────────────────────────────────────────────────────────────
   НАБОР С: сложение — скорость и вид.
   ──────────────────────────────────────────────────────────────────── */
if (need('С')) {
  head('НАБОР С. Сложение: скорость и вид');
  await ev(() => pfSumSetup(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']));
  await ev(() => pfExpandAll());
  const timing = await ev(() => pfPanTiming(60));
  note('время кадра панорамирования: медиана ' + num(timing.median) + ' мс  (три прогона: '
    + timing.all.map(num).join(' / ') + ')');
  const ab = await ev(() => pfPanTimingAB(40, 5));
  note('честное чередование ДО/ПОСЛЕ в одном сеансе (пять пар по 40 шагов):');
  note('   по прежнему поведению: медиана ' + num(ab.before) + ' мс   (' + ab.beforeAll.map(num).join(' / ') + ')');
  note('   по нынешнему:          медиана ' + num(ab.after) + ' мс   (' + ab.afterAll.map(num).join(' / ') + ')');
  note('   выигрыш: ' + num(ab.before - ab.after) + ' мс, то есть в '
    + num(ab.before / ab.after) + ' раза');
  const cab = await ev(() => pfCallsAB());
  note('вызовов формулы кривой за кадр: было ' + cab.before + ', стало ' + cab.after
    + ' (в ' + num(cab.before / Math.max(1, cab.after)) + ' раза меньше)');
  const calls = cab.after;
  const look = await ev(() => pfCurveLook());
  look.forEach(l => note(`  ${l.name}${l.part ? ' [' + l.part + ']' : ''}: цвет ${l.stroke}, толщина ${l.width}, `
    + `штрих «${l.dash || 'сплошная'}», прозрачность ${l.opacity}, точек пути ${l.pts}`));
  for (const th of ['light', 'dark']) {
    await setTheme(th);
    await reinject();
    await ev(() => pfSumSetup(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']));
    const con = await ev(() => {
      const bg = pfCanvasRGB();
      return pfCurveLook().map(l => {
        const c = pfRGB(l.stroke);
        if (!c) return { name: l.name, contrast: null };
        const eff = pfBlend(c, l.opacity, bg);
        return { name: l.name + (l.part ? ' [' + l.part + ']' : ''), contrast: pfContrast(eff, bg),
          opacity: l.opacity, width: l.width, dash: l.dash };
      });
    });
    note('тема ' + th + ':');
    con.forEach(c => {
      const okc = c.contrast != null && c.contrast >= 3;
      if (!okc) bad++;
      console.log('  ' + (okc ? 'OK   ' : 'FAIL ') + c.name + ' контраст = ' + num(c.contrast)
        + ' (прозрачность ' + c.opacity + ', толщина ' + c.width + ', штрих «' + (c.dash || 'сплошная') + '»)');
    });
    await shot('S-look-' + th);
  }
  await setTheme('light');
  await reinject();
}

/* ────────────────────────────────────────────────────────────────────
   НАБОР Р: аналитическая запись суммарной КПВ.
   ──────────────────────────────────────────────────────────────────── */
if (need('Р')) {
  head('НАБОР Р. Аналитическая запись суммарной КПВ');
  await ev(() => pfPpfSetup(['100-x', '60-2x']));
  await ev(() => pfExpandAll());
  let f = await ev(() => pfPpfForm());
  note('две КПВ: n=' + f.n + ' type=' + f.type);
  note('  formulaText: ' + f.formulaText);
  note('  панель: ' + f.panelText);
  note('  изломы: ' + JSON.stringify(f.kinks));
  note('  KaTeX в «Форме кривой»: ' + f.katexInForm + ', переполнение панели: ' + JSON.stringify(f.overflow));
  await shot('R-2ppf');

  await ev(() => pfPpfSetup(['100-x', '60-2x', '40-4x']));
  await ev(() => pfExpandAll());
  f = await ev(() => pfPpfForm());
  note('три КПВ: n=' + f.n + ' type=' + f.type);
  note('  formulaText: ' + f.formulaText);
  note('  панель: ' + f.panelText);
  note('  изломы: ' + JSON.stringify(f.kinks));
  note('  KaTeX в «Форме кривой»: ' + f.katexInForm + ', переполнение панели: ' + JSON.stringify(f.overflow));
  await shot('R-3ppf');
}

console.log('\n--- ошибки страницы: ' + errs.length + (errs.length ? ('\n' + errs.slice(0, 10).join('\n')) : ''));
console.log('--- провалов: ' + bad);
await browser.close();
process.exit(bad ? 1 : 0);
