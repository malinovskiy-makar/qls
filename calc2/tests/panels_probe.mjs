/* РЕЕСТР ПАНЕЛЕЙ И СЛОЙ ПОВЕРХ СЦЕНЫ — постоянные проверки сессии 01.09.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/panels_probe.mjs

   Что стережёт прибор:
     • у каждой сцены реестр панелей непуст и панели не выходят за холст;
     • у сцен с двумя полями панелей ДВЕ, а не одна на весь холст;
     • вершина рядом с изломом Лоренца встаёт НА кривую (это про то, что слой
       считает по шкалам панели, а не по CONFIG на всю ширину);
     • на нижней панели производной притяжение даёт f′(x), а не f(x);
     • вершины на разных панелях площадь не считают;
     • колесо над одной панелью не трогает соседнюю.

   ⚠️ Прибор стережёт ПРАВИЛО, а не отпечаток реализации: числом здесь не
   зафиксировано ни сколько всего панелей в калькуляторе, ни густота сетки.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0, total = 0;
const num = (v) => (typeof v === 'number' && isFinite(v)) ? (Math.round(v * 1e4) / 1e4) : String(v);
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }
function cmp(label, got, want, tol) {
  total++;
  const ok = (typeof got === 'number' && isFinite(got)) ? Math.abs(got - want) <= (tol || 0) : (got === want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'OK  ' : 'FAIL') + ' ' + label.padEnd(46)
    + 'ожидалось ' + String(want).padEnd(12) + 'получилось ' + num(got));
}
const run = (code) => page.evaluate(async (c) => {
  const out = (new Function(c))();
  await new Promise(r => setTimeout(r, 60));
  return out;
}, code);

/* ── 1. Опись: сцена → её панели ─────────────────────────────────────── */
head('Опись панелей по сценам');
const inv = await run(`
  var out = [];
  Object.keys(SCENE_ROUTE).forEach(function (k) {
    try {
      pickScene(k); redrawAll();
      out.push({ key: k, ids: (STATE.panels || []).map(function (p) { return p.id; }),
                 bad: (STATE.panels || []).filter(function (p) {
                   return !(p.x1 > p.x0) || !(p.y1 > p.y0)
                       || p.x0 < -1 || p.y0 < -1 || p.x1 > W + 1 || p.y1 > H + 1;
                 }).length });
    } catch (e) { out.push({ key: k, ids: [], err: String(e && e.message || e) }); }
  });
  return out;
`);
const byIds = {};
inv.forEach(r => {
  const sig = r.ids.join(' + ') || '(нет)';
  (byIds[sig] = byIds[sig] || []).push(r.key);
});
Object.keys(byIds).sort().forEach(sig => {
  console.log('  ' + String(byIds[sig].length).padStart(2) + ' сцен · ' + sig.padEnd(30)
    + ' · ' + byIds[sig].join(', '));
});
cmp('сцен без единой панели', inv.filter(r => !r.ids.length).length, 0);
cmp('панелей за краем холста', inv.reduce((a, r) => a + (r.bad || 0), 0), 0);
cmp('сцен, уронивших перерисовку', inv.filter(r => r.err).length, 0);
inv.filter(r => r.err).forEach(r => console.log('    ! ' + r.key + ': ' + r.err));

/* Сцены с двумя полями обязаны отдать ДВЕ панели. Список именно этих сцен —
   правило, а не отпечаток: у сюжета два графика, значит и панелей две. */
head('Двухпанельные сюжеты');
[['mono-d3', 2], ['monoexport', 2], ['prod', 2], ['tradeprice', 2], ['ineq', 1]].forEach(([k, n]) => {
  const row = inv.find(r => r.key === k);
  cmp(k + ': панелей', row ? row.ids.length : 0, n);
});
{
  const tan = await run(`setMode('math'); setMathSub('tangent'); redrawAll();
    return (STATE.panels || []).map(function (p) { return p.id; });`);
  cmp('производная: панелей', tan.length, 2);
  cmp('производная: верхняя есть', tan.includes('deriv-top'), true);
  cmp('производная: нижняя есть', tan.includes('deriv-bottom'), true);
}

/* ── 2. Вершина садится НА кривую Лоренца (дефект А) ─────────────────── */
/* Ставим вершину рядом с изломом (80; 50) и сверяем ЭКРАННЫЕ координаты
   нарисованной вершины с экранными координатами узла самой кривой. До правки
   отклонение по X было около 54 px и росло при зуме. */
head('Неравенство: вершина совпадает с кривой Лоренца');
const LOR = `
  var setup = function () {
    pickScene('ineq'); setIneqInput('incomes');
    STATE.ineqIncomes = '10, 20, 30, 40, 100';
    recomputeInequality(); redrawAll();
  };
  var probe = function () {
    var p = (STATE.panels || [])[0];
    var f = snapTargets().filter(function (t) { return t.name === 'Лоренц'; })[0];
    if (!p || !f) return null;
    var x = 80, y = f.f(x);
    // Ставим вершину ровно в узел кривой и меряем, куда её нарисовал слой.
    STATE.areaVerts = [];
    addAreaVert(x, y, '');
    redrawAll();
    var v = STATE.areaVerts[0];
    var s = mainScales(v.panel);
    return { dx: Math.abs(s.mx(v.x) - p.mx(x)), dy: Math.abs(s.my(v.y) - p.my(y)),
             y: y, panel: v.panel };
  };
`;
let r = await run(LOR + `setup(); return probe();`);
cmp('вершина у излома: расхождение X, px', r && r.dx, 0, 1);
cmp('вершина у излома: расхождение Y, px', r && r.dy, 0, 1);
cmp('вершина помнит свою панель', r && r.panel, 'lorenz');
r = await run(LOR + `setup(); zoomBy(0.8, 400, 400); zoomBy(0.8, 400, 400); return probe();`);
cmp('после двух щелчков колеса: X, px', r && r.dx, 0, 1);
cmp('после двух щелчков колеса: Y, px', r && r.dy, 0, 1);
r = await run(LOR + `setup(); zoomBy(1.25, 400, 400); zoomBy(1.25, 400, 400); return probe();`);
cmp('колесо в другую сторону: X, px', r && r.dx, 0, 1);
cmp('колесо в другую сторону: Y, px', r && r.dy, 0, 1);
// Квадрат остаётся квадратом при любом зуме: оси там несут проценты.
r = await run(LOR + `setup(); zoomBy(0.7, 400, 300);
  var p = (STATE.panels || [])[0];
  var dx = p.mx.domain()[1] - p.mx.domain()[0], dy = p.my.domain()[1] - p.my.domain()[0];
  return { dx: dx, dy: dy, w: Math.abs(p.x1 - p.x0), h: Math.abs(p.y1 - p.y0) };`);
cmp('квадрат Лоренца: окно по осям равно', Math.abs(r.dx - r.dy), 0, 1e-6);
cmp('квадрат Лоренца: стороны равны, px', Math.abs(r.w - r.h), 0, 1);

/* ── 3. Нижняя панель производной отдаёт f′(x) (дефект А) ────────────── */
head('Производная: у каждой панели своя функция');
const TAN = `
  var setup = function () {
    setMode('math'); setMathSub('tangent');
    STATE.mathFormula = 'x^2';
    var inp = document.getElementById('inp-mathf');
    if (inp) { inp.value = 'x^2'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    redrawAll();
  };
  var atPanel = function (id, x) {
    var p = (STATE.panels || []).filter(function (q) { return q.id === id; })[0];
    if (!p) return null;
    STATE.pointerPx = (p.x0 + p.x1) / 2; STATE.pointerPy = (p.y0 + p.y1) / 2;
    var names = snapTargets().map(function (t) { return t.name; });
    var vals = snapTargets().map(function (t) { return t.f(x); });
    return { names: names, vals: vals };
  };
`;
r = await run(TAN + `setup(); return { top: atPanel('deriv-top', 3), bot: atPanel('deriv-bottom', 3) };`);
cmp('верхняя панель при x = 3 даёт f = 9', r.top && r.top.vals[0], 9, 1e-6);
cmp('верхняя панель: кривых', r.top && r.top.names.length, 1);
cmp('нижняя панель при x = 3 даёт f′ = 6', r.bot && r.bot.vals[0], 6, 1e-6);
cmp('нижняя панель: кривых', r.bot && r.bot.names.length, 1);
// То же через настоящее притяжение мыши, а не через список кривых.
r = await run(TAN + `setup();
  var p = (STATE.panels || []).filter(function (q) { return q.id === 'deriv-bottom'; })[0];
  var px = p.mx(3), py = p.my(6);
  STATE.pointerPx = px; STATE.pointerPy = py;
  var hit = snapPointAt(px, py);
  return hit ? { x: hit.x, y: hit.y } : null;`);
cmp('притяжение на нижней панели: x', r && r.x, 3, 0.05);
cmp('притяжение на нижней панели: y', r && r.y, 6, 0.05);

/* ── 4. Площадь не пересекает границу панели ─────────────────────────── */
head('Площадь считается внутри одной панели');
r = await run(TAN + `setup();
  var top = (STATE.panels || []).filter(function (q) { return q.id === 'deriv-top'; })[0];
  var bot = (STATE.panels || []).filter(function (q) { return q.id === 'deriv-bottom'; })[0];
  STATE.areaVerts = []; STATE.areaCalcMode = 'poly';
  STATE.pointerPx = (top.x0 + top.x1) / 2; STATE.pointerPy = (top.y0 + top.y1) / 2;
  addAreaVert(1, 1, ''); addAreaVert(2, 4, '');
  STATE.pointerPx = (bot.x0 + bot.x1) / 2; STATE.pointerPy = (bot.y0 + bot.y1) / 2;
  addAreaVert(3, 6, '');
  redrawAll();
  var btn = document.getElementById('ac-calc');
  var note = document.querySelector('#ac-verts .vert-mixed');
  return { panels: STATE.areaVerts.map(function (v) { return v.panel; }),
           disabled: btn ? !!btn.disabled : null,
           note: note ? note.textContent.trim() : '' };`);
cmp('вершины помнят разные панели', r.panels.join(','), 'deriv-top,deriv-top,deriv-bottom');
cmp('кнопка «Посчитать площадь» не активна', r.disabled, true);
cmp('в списке вершин стоит строка-объяснение',
  /разных графиках/.test(r.note), true);
// Все вершины в одной панели — кнопка снова живая.
r = await run(TAN + `setup();
  var top = (STATE.panels || []).filter(function (q) { return q.id === 'deriv-top'; })[0];
  STATE.areaVerts = []; STATE.areaCalcMode = 'poly';
  STATE.pointerPx = (top.x0 + top.x1) / 2; STATE.pointerPy = (top.y0 + top.y1) / 2;
  addAreaVert(1, 1, ''); addAreaVert(2, 4, ''); addAreaVert(3, 9, '');
  redrawAll();
  var btn = document.getElementById('ac-calc');
  return btn ? !!btn.disabled : null;`);
cmp('вершины в одной панели: кнопка активна', r, false);

/* ── 5. Колесо работает в панели под курсором ────────────────────────── */
head('Колесо крутит панель под курсором');
r = await run(`
  pickScene('monoexport');
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
  redrawAll();
  var before = (STATE.panels || []).map(function (p) { return p.mx.domain()[1]; });
  var left = (STATE.panels || [])[0], right = (STATE.panels || [])[1];
  if (!left || !right) return { err: 'панелей не две' };
  zoomBy(0.8, (left.x0 + left.x1) / 2, (left.y0 + left.y1) / 2);
  var afterL = (STATE.panels || []).map(function (p) { return p.mx.domain()[1]; });
  zoomBy(0.8, (right.x0 + right.x1) / 2, (right.y0 + right.y1) / 2);
  var afterR = (STATE.panels || []).map(function (p) { return p.mx.domain()[1]; });
  return { before: before, afterL: afterL, afterR: afterR };`);
if (r.err) { cmp('монополист и внешний рынок: две панели', r.err, 'две панели'); }
else {
  cmp('колесо слева: левая панель изменилась', r.afterL[0] !== r.before[0], true);
  cmp('колесо слева: правая панель НЕ изменилась', Math.abs(r.afterL[1] - r.before[1]), 0, 1e-9);
  cmp('колесо справа: правая панель изменилась', r.afterR[1] !== r.afterL[1], true);
  cmp('колесо справа: левая панель НЕ изменилась', Math.abs(r.afterR[0] - r.afterL[0]), 0, 1e-9);
}

/* ── 6. Ключевая точка — это то, что сцена нарисовала (фаза 4) ────────── */
head('Ключевые точки: нарисованное, проекции, изломы');
const MKT = `
  var setDS = function (scene, d, s) {
    resetSceneMemory(); pickScene(scene);
    updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), d);
    var low = STATE.curves.find(function (c) { return c.role === 'supply' || c.role === 'mc'; });
    if (low) updateCurveExpr(low, s);
    redrawAll();
  };
`;
r = await run(MKT + `setDS('sd', '100-Q', 'Q');
  var k = keyTargets();
  var at = function (x, y) { return k.some(function (p) {
    return Math.abs(p.x - x) < 0.5 && Math.abs(p.y - y) < 0.5; }); };
  var s = mainScales();
  var h1 = snapVertexAt(s.mx(0), s.my(50)), h2 = snapVertexAt(s.mx(50), s.my(0));
  var e = k.filter(function (p) { return Math.abs(p.x - 50) < 0.5 && Math.abs(p.y - 50) < 0.5; })[0];
  return { n: k.length, eq: at(50, 50), d0: at(0, 100), d1: at(100, 0),
           pr1: at(0, 50), pr2: at(50, 0), origin: at(0, 0),
           owners: e ? e.owners.slice().sort().join(',') : '',
           snap1: !!(h1 && h1.key && Math.abs(h1.x) < 1e-6 && Math.abs(h1.y - 50) < 1e-6),
           snap2: !!(h2 && h2.key && Math.abs(h2.x - 50) < 1e-6 && Math.abs(h2.y) < 1e-6) };`);
cmp('«Спрос и предложение»: ключевых точек', r.n, 6);
cmp('  равновесие (50; 50)', r.eq, true);
cmp('  начало D (0; 100)', r.d0, true);
cmp('  конец D (100; 0)', r.d1, true);
cmp('  проекция равновесия (0; 50)', r.pr1, true);
cmp('  проекция равновесия (50; 0)', r.pr2, true);
cmp('  начало координат (0; 0)', r.origin, true);
cmp('  у равновесия оба хозяина', r.owners, 'D,S');
cmp('  мышь притягивается к (0; 50)', r.snap1, true);
cmp('  мышь притягивается к (50; 0)', r.snap2, true);

// Нарисованная точка объявлена на холсте и названа своей буквой.
r = await run(MKT + `setDS('sd', '100-Q', 'Q');
  var n = document.querySelector('[data-key-point]');
  return n ? { name: n.getAttribute('data-key-point'),
               x: +n.getAttribute('data-kp-x'), y: +n.getAttribute('data-kp-y'),
               panel: n.getAttribute('data-kp-panel') } : null;`);
cmp('равновесие объявлено на холсте именем', r && r.name, 'E');
cmp('  его координаты: x', r && r.x, 50, 1e-6);
cmp('  его координаты: y', r && r.y, 50, 1e-6);
cmp('  и его панель', r && r.panel, 'main');

/* Излом суммарного спроса. Он стоит ровно там же, где пересечение двух других
   кривых, и раньше выбрасывался дедупликацией ЦЕЛИКОМ — вместе с хозяином,
   то есть переставал загораться щелчком по своей кривой. */
r = await run(`pickScene('sdsum'); redrawAll();
  var k = keyTargets().filter(function (p) {
    return Math.abs(p.x - 40) < 0.5 && Math.abs(p.y - 60) < 0.5; })[0];
  armCurve('рыночный спрос');
  var lit = keyTargets().filter(keyPointLit)
    .some(function (p) { return Math.abs(p.x - 40) < 0.5 && Math.abs(p.y - 60) < 0.5; });
  return { есть: !!k, хозяин: !!(k && k.owners.indexOf('рыночный спрос') >= 0), горит: lit,
           Q: STATE.eq.Q, P: STATE.eq.P, cs: STATE.cs, ps: STATE.ps };`);
cmp('«Сложение»: излом (40; 60) в списке', r['есть'], true);
cmp('  его хозяин — суммарный спрос', r['хозяин'], true);
cmp('  загорается щелчком по нему', r['горит'], true);
cmp('  числа сложения не сдвинулись: Q*', r.Q, 70, 1e-4);
cmp('  P*', r.P, 45, 1e-4);
cmp('  CS', r.cs, 1625, 1e-3);
cmp('  PS', r.ps, 1325, 1e-3);

console.log('\nОшибок страницы: ' + errs.length);
errs.slice(0, 5).forEach(e => console.log('  ! ' + e));
console.log(bad ? ('ПРОВАЛЕНО ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' ПРОВЕРОК ПАНЕЛЕЙ СОШЛИСЬ'));
await browser.close();
process.exit(bad || errs.length ? 1 : 0);
