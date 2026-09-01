/* КОНТРОЛЬНЫЕ ЧИСЛА КАЛЬКУЛЯТОРА — полный список одним прогоном.
   Печатает «ожидалось / получилось» по КАЖДОМУ числу, а не только по
   провалившимся: этим прибором сдаётся сессия.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/control_numbers.mjs

   ⚠️ Расходится число — сломан ДВИЖОК, а не прибор. Подгонять ожидание под
   код запрещено: числа выверены и приняты владельцем.
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
  const ok = (typeof got === 'number' && isFinite(got)) ? Math.abs(got - want) <= tol : (got === want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'OK  ' : 'FAIL') + ' ' + label.padEnd(46)
    + 'ожидалось ' + String(want).padEnd(12) + 'получилось ' + num(got));
}

const run = (code) => page.evaluate(async (c) => {
  const out = (new Function(c))();
  await new Promise(r => setTimeout(r, 60));
  return out;
}, code);

/* --- рыночные сцены ------------------------------------------------- */
const MKT = `
  /* У монополии вместо предложения кривая предельных затрат: роль другая,
     а место в сцене то же. Один помощник на обе — иначе пришлось бы держать
     два одинаковых куска настройки. */
  var setDS = function (scene, d, s) {
    resetSceneMemory(); pickScene(scene);
    updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), d);
    var low = STATE.curves.find(function (c) { return c.role === 'supply' || c.role === 'mc'; });
    if (low) updateCurveExpr(low, s);
    redrawAll();
  };
`;

head('Спрос и предложение');
let r = await run(MKT + `setDS('sd', '100-Q', 'Q');
  return { Q: STATE.eq.Q, P: STATE.eq.P, cs: STATE.cs, ps: STATE.ps };`);
cmp('Q*', r.Q, 50, 1e-4); cmp('P*', r.P, 50, 1e-4);
cmp('CS', r.cs, 1250, 1e-3); cmp('PS', r.ps, 1250, 1e-3);
r = await run(MKT + `setDS('sd', '100-Q', 'Q^2/100'); return { Q: STATE.eq.Q };`);
cmp('нелинейное S = Q²/100: Q*', r.Q, 61.80, 0.01);

head('Налог и субсидия');
r = await run(MKT + `setDS('taxes', '100-Q', 'Q'); setType('tax'); setTaxForm('unit'); setTax(20); redrawAll();
  return { Q: STATE.taxEq.Q, Pb: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, tx: STATE.tx, dwl: STATE.dwl };`);
cmp('налог 20: Q₁', r.Q, 40, 1e-4); cmp('налог 20: Pb', r.Pb, 60, 1e-4);
cmp('налог 20: Ps', r.Ps, 40, 1e-4); cmp('налог 20: сбор', r.tx, 800, 1e-3);
cmp('налог 20: DWL', r.dwl, 100, 1e-3);
for (const side of ['seller', 'buyer']) {
  r = await run(MKT + `setDS('taxes', '100-Q', 'Q'); setType('subsidy'); setTaxForm('unit');
    setTaxSide('${side}'); setTax(20); redrawAll();
    return { Q: STATE.taxEq.Q, bud: STATE.budget, dwl: STATE.dwl };`);
  cmp('субсидия 20 (' + side + '): Q₁', r.Q, 60, 1e-4);
  cmp('субсидия 20 (' + side + '): расход', r.bud, -1200, 1e-3);
  cmp('субсидия 20 (' + side + '): DWL', r.dwl, 100, 1e-3);
}

head('Потолок и пол цены');
r = await run(MKT + `setDS('ceil', '100-Q', 'Q'); setType('ceiling'); setPRegFields(30); redrawAll();
  var p = STATE.pc || {};
  return { Qd: p.Qd, Qs: p.Qs, gap: p.gap, dwl: STATE.pcDwl != null ? STATE.pcDwl : (p.dwl != null ? p.dwl : NaN) };`);
cmp('потолок 30: Qd', r.Qd, 70, 1e-4); cmp('потолок 30: Qs', r.Qs, 30, 1e-4);
cmp('потолок 30: дефицит', r.gap, 40, 1e-4);
r = await run(MKT + `setDS('ceil', '100-Q', 'Q'); setType('floor'); setPRegFields(70); redrawAll();
  var p = STATE.pc || {};
  return { Qd: p.Qd, Qs: p.Qs, gap: p.gap };`);
cmp('пол 70: Qs', r.Qs, 70, 1e-4); cmp('пол 70: Qd', r.Qd, 30, 1e-4);
cmp('пол 70: избыток', r.gap, 40, 1e-4);

head('Монополия');
for (const [tag, code] of [['стартовое окно', ''], ['окно до Q = 30', 'CONFIG.Qmin=0; CONFIG.Qmax=30; redrawAll();']]) {
  r = await run(MKT + `setDS('mono', '100-Q', '20'); ${code}
    var m = STATE.mono || {};
    return { Qm: m.Qm, Pm: m.Pm, Qc: m.Qc };`);
  cmp('монополия (' + tag + '): Qm', r.Qm, 40, 1e-3);
  cmp('монополия (' + tag + '): Pm', r.Pm, 60, 1e-3);
  cmp('монополия (' + tag + '): Qc', r.Qc, 80, 1e-3);
}

head('Эквивалентность форм налога');
for (const [form, rate] of [['unit', 40], ['excise', 50], ['vat', 100]]) {
  r = await run(MKT + `setDS('taxes', '120-Q', 'Q'); setType('tax'); setTaxForm('${form}'); setTax(${rate}); redrawAll();
    return { Q: STATE.taxEq.Q, Pb: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, tx: STATE.tx, dwl: STATE.dwl };`);
  cmp(form + ' ' + rate + ': Q', r.Q, 40, 1e-3);
  cmp(form + ' ' + rate + ': Pd', r.Pb, 80, 1e-3);
  cmp(form + ' ' + rate + ': Ps', r.Ps, 40, 1e-3);
  cmp(form + ' ' + rate + ': сбор', r.tx, 1600, 1e-2);
  cmp(form + ' ' + rate + ': DWL', r.dwl, 400, 1e-2);
}

head('Процентные субсидии');
for (const [kind, label, wQ, wPd, wPs, wBud, wDwl] of [
  ['subbuyer', 'от цены покупателя', 72, 48, 72, -1728, 144],
  ['subseller', 'от цены продавца', 80, 40, 80, -3200, 400]]) {
  r = await run(MKT + `setDS('taxes', '120-Q', 'Q'); setType('subsidy'); setTaxForm('${kind}'); setTax(50); redrawAll();
    return { Q: STATE.taxEq.Q, Pb: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, bud: STATE.budget, dwl: STATE.dwl };`);
  cmp(label + ': Q', r.Q, wQ, 1e-3);
  cmp(label + ': Pd', r.Pb, wPd, 1e-3);
  cmp(label + ': Ps', r.Ps, wPs, 1e-3);
  cmp(label + ': расход', r.bud, wBud, 1e-2);
  cmp(label + ': DWL', r.dwl, wDwl, 1e-2);
}

head('Центр поворота при акцизе');
r = await run(MKT + `setDS('taxes', '120-Q', '0.5*Q+30'); setType('tax'); setTaxForm('excise'); setTax(25); redrawAll();
  var p = (typeof taxPivotQ === 'function') ? taxPivotQ() : null;
  return { Q: STATE.taxEq.Q, Pb: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, tx: STATE.tx, dwl: STATE.dwl, pivot: p };`);
cmp('акциз 25 %: Q', r.Q, 48, 1e-3); cmp('акциз 25 %: Pd', r.Pb, 72, 1e-3);
cmp('акциз 25 %: Ps', r.Ps, 54, 1e-3); cmp('акциз 25 %: сбор', r.tx, 864, 1e-2);
cmp('акциз 25 %: DWL', r.dwl, 108, 1e-2);
cmp('центр поворота по Q', r.pivot, -60, 1e-3);

head('Сложение спросов и предложений');
r = await run(`resetSceneMemory(); pickScene('sdsum'); redrawAll();
  var st = sumGroupStats();
  return { Q: STATE.eq.Q, P: STATE.eq.P, d1: st.D[0].q, d2: st.D[1].q,
           s1: st.S[0].q, s2: st.S[1].q, cs1: st.D[0].surplus, cs2: st.D[1].surplus,
           cs: st.csGroups, ps1: st.S[0].surplus, ps2: st.S[1].surplus, ps: st.psGroups,
           sw: st.csGroups + st.psGroups, warn: (document.getElementById('info-sum').innerHTML.indexOf('warn') >= 0) ? 1 : 0 };`);
cmp('набор А: Q*', r.Q, 70, 1e-4); cmp('набор А: P*', r.P, 45, 1e-4);
cmp('набор А: спрос группы 1', r.d1, 55, 1e-4); cmp('набор А: спрос группы 2', r.d2, 15, 1e-4);
cmp('набор А: предложение группы 1', r.s1, 45, 1e-4); cmp('набор А: предложение группы 2', r.s2, 25, 1e-4);
cmp('набор А: CS группы 1', r.cs1, 1512.5, 1e-3); cmp('набор А: CS группы 2', r.cs2, 112.5, 1e-3);
cmp('набор А: CS вместе', r.cs, 1625, 1e-3);
cmp('набор А: PS группы 1', r.ps1, 1012.5, 1e-3); cmp('набор А: PS группы 2', r.ps2, 312.5, 1e-3);
cmp('набор А: PS вместе', r.ps, 1325, 1e-3); cmp('набор А: SW', r.sw, 2950, 1e-3);

r = await run(`resetSceneMemory(); pickScene('sdsum');
  sumSetCount('D', 3); sumSetCount('S', 2);
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  ['100-Q','60-Q','40-Q'].forEach(function (e, i) { updateCurveExpr(gd[i], e); });
  ['Q-100','Q+20'].forEach(function (e, i) { updateCurveExpr(gs[i], e); });
  redrawAll();
  var st = sumGroupStats();
  return { Q: STATE.eq.Q, P: STATE.eq.P, cs1: st.D[0].surplus, cs2: st.D[1].surplus, cs3: st.D[2].surplus,
           cs: st.csGroups, ps1: st.S[0].surplus, ps2: st.S[1].surplus, ps: st.psGroups,
           psWhole: st.psGroups - st.psGap, sw: st.csGroups + st.psGroups,
           warn: (document.getElementById('info-sum').innerHTML.indexOf('class="warn"') >= 0) ? 1 : 0 };`);
cmp('набор Б: Q*', r.Q, 128, 1e-3); cmp('набор Б: P*', r.P, 24, 1e-3);
cmp('набор Б: CS 1', r.cs1, 2888, 1e-2); cmp('набор Б: CS 2', r.cs2, 648, 1e-2);
cmp('набор Б: CS 3', r.cs3, 128, 1e-2); cmp('набор Б: CS вместе', r.cs, 3664, 1e-2);
cmp('набор Б: PS 1', r.ps1, 2688, 1e-2); cmp('набор Б: PS 2', r.ps2, 8, 1e-2);
cmp('набор Б: PS вместе', r.ps, 2696, 1e-2);
cmp('набор Б: PS по суммарной кривой', r.psWhole, 2696, 1e-2);
cmp('набор Б: SW', r.sw, 6360, 1e-2);
cmp('набор Б: красного предупреждения НЕТ', r.warn, 0, 0);

head('Вмешательство без исходного равновесия');
/* «Предложение обращается в ноль при цене 400» — это цена, при которой
   КОЛИЧЕСТВО равно нулю, то есть значение кривой P = f(Q) в точке Q = 0. */
r = await run(MKT + `setDS('taxes', '100-P', '0.5*p-200');
  var base = evalCurve(STATE.S, 0);
  setType('tax'); setTaxForm('unit'); setTax(100); redrawAll();
  var after = evalCurve(STATE.taxAfterS, 0);
  var dwlTax = STATE.dwl;
  var noBase1 = STATE.taxNoBase ? 1 : 0;
  setType('subsidy'); setTaxForm('unit'); setTax(450); redrawAll();
  var te = STATE.taxEq;
  return { base: base, after: after, dwlTax: dwlTax, noBase1: noBase1,
           Q: te ? te.Q : NaN, Pb: te ? te.Pb : NaN, Ps: te ? te.Ps : NaN,
           bud: STATE.budget, dwlSub: STATE.dwl, noBase2: STATE.taxNoBase ? 1 : 0 };`);
cmp('S в ноль при цене', r.base, 400, 1e-3);
cmp('с налогом 100 — при цене', r.after, 500, 1e-3);
cmp('DWL при налоге НЕ показан', r.dwlTax === null ? 1 : 0, 1, 0);
cmp('субсидия 450: Q', r.Q, 50, 1e-3);
cmp('субсидия 450: Pd', r.Pb, 50, 1e-3);
cmp('субсидия 450: Ps', r.Ps, 500, 1e-3);
cmp('субсидия 450: расход', Math.abs(r.bud), 22500, 1e-2);
cmp('субсидия 450: DWL НЕ показан', r.dwlSub === null ? 1 : 0, 1, 0);

head('Суммарная КПВ');
const PPF = `
  var take = function (exprs) {
    var cs = exprs.map(function (e) { return classifyPpf(parsePpfEquation(e).f); });
    var g = ppfSumAnalytic(cs);
    return g ? g : null;
  };
`;
for (const [name, exprs, pts] of [
  ['линейные 100−x и 60−2x', ['y = 100 - x', 'y = 60 - 2*x'], [[0, 160], [100, 60], [130, 0]]],
  ['плюс 40−4x', ['y = 100 - x', 'y = 60 - 2*x', 'y = 40 - 4*x'], [[0, 200], [100, 100], [130, 40], [140, 0]]],
  ['(а) учебник с.185', ['y = 20 - 4*x', 'y = 16 - x^2'], [[0, 36], [2, 32], [5, 20], [7, 12], [9, 0]]],
  ['(б) две параболы', ['y = 16 - x^2', 'y = 36 - 4*x^2'], [[0, 52], [5, 32], [6, 20], [7, 0]]],
  ['(г) учебник с.182', ['y = 5 - 0.625*x', 'y = 8 - 2*x'], [[0, 13], [8, 8], [12, 0]]],
  ['(ф9) убывающие АИ', ['y = 60 - 20*sqrt(x)', 'y = 40 - 10*x'], [[0, 100], [4, 60], [6.25, 50], [9, 40], [13, 0]]],
]) {
  const got = await run(PPF + `var g = take(${JSON.stringify(exprs)});
    if (!g) return null;
    return { tex: g.latex, vals: ${JSON.stringify(pts.map(p => p[0]))}.map(function (x) { var v = g.evalY(x); return isNaN(v) ? null : v; }) };`);
  if (!got) { cmp(name + ': закрытая форма', 'нет', 'есть', 0); continue; }
  console.log('  · ' + name + ':  ' + got.tex);
  pts.forEach(([x, want], i) => cmp(name + ': Y(' + x + ')', got.vals[i], want, 1e-6));
}

head('Внешние эффекты');
r = await run(`resetSceneMemory(); loadScene('ext'); STATE.mscOn = true; STATE.mscExpr = 'Q + 20';
  recompileSocial(); redrawAll();
  var e = STATE.ext || {};
  return { qm: e.Qmkt, q: e.Qopt, dwl: e.dwl, tax: e.corrective };`);
cmp('MSC = Q + 20: рыночное Q', r.qm, 50, 0.3);
cmp('MSC = Q + 20: оптимум Q', r.q, 40, 0.4);
cmp('MSC = Q + 20: DWL', r.dwl, 100, 2);
cmp('MSC = Q + 20: налог Пигу', r.tax, 20, 0.2);
r = await run(`resetSceneMemory(); loadScene('ext'); STATE.msbOn = true; STATE.msbExpr = '120 - Q';
  recompileSocial(); redrawAll();
  var e = STATE.ext || {};
  return { qm: e.Qmkt, q: e.Qopt, dwl: e.dwl, sub: -e.corrective };`);
cmp('MSB = 120 − Q: рыночное Q', r.qm, 50, 0.3);
cmp('MSB = 120 − Q: оптимум Q', r.q, 60, 0.4);
cmp('MSB = 120 − Q: DWL', r.dwl, 100, 2);
cmp('MSB = 120 − Q: субсидия Пигу', r.sub, 20, 0.2);

head('Математика');
/* Корни функции ищет общий rootsOf по окну сцены — тот же, которым
   калькулятор рисует нули на графике. */
r = await run(`setMode('math'); setMathSub('optimum'); STATE.mathFormula='x^3 - 3*x';
  setMathWindow(-3,3,-6,6); redrawAll();
  var f = function (x) { return x * x * x - 3 * x; };
  var roots = rootsOf(f, -3, 3).slice().sort(function (x, y) { return x - y; });
  var a = STATE.mathRes || {};
  var mx = (a.ext || []).filter(function (p) { return p.kind === 'max'; })[0] || {};
  var mn = (a.ext || []).filter(function (p) { return p.kind === 'min'; })[0] || {};
  return { n: roots.length, r0: roots[0], r1: roots[1], r2: roots[2],
           xmax: mx.x, xmin: mn.x };`);
cmp('x³ − 3x: корней', r.n, 3, 0);
cmp('x³ − 3x: корень 1', r.r0, -1.732, 0.01);
cmp('x³ − 3x: корень 2', r.r1, 0, 0.01);
cmp('x³ − 3x: корень 3', r.r2, 1.732, 0.01);
cmp('x³ − 3x: x максимума', r.xmax, -1, 0.02);
cmp('x³ − 3x: x минимума', r.xmin, 1, 0.02);
/* Пересечение f₁ и f₂ — контрольная пара владельца. Сюжет «Наибольшее и
   наименьшее»: Z = min(x², 4 − x) меняет ветвь ровно в точке пересечения. */
r = await run(`setMode('math'); setMathSub('minmax'); STATE.mathFormula = 'x^2'; STATE.mathG2 = '4 - x';
  setMathWindow(-1, 4, -1, 6); redrawAll();
  var sw = (STATE.mathRes && STATE.mathRes.switches) ? STATE.mathRes.switches : [];
  var x = sw.length ? sw[sw.length - 1] : NaN;
  return { n: sw.length, x: x, y: isFinite(x) ? x * x : NaN };`);
cmp('пересечение f₁ и f₂: x', r.x, 1.5616, 1e-3);
cmp('пересечение f₁ и f₂: y', r.y, 2.4384, 1e-3);

/* --- приёмка 31.08: новые семейства КПВ и смешанные пары -------------- */
head('Приёмка 31.08 · многочлен второй степени и степенная кривая');
r = await run(`
  var cls = function (e) { var q = compileFormula(e);
    return classifyPpf(function (x) { return ppfEvalWith(q.compiled, x); }); };
  var sum = function (a, b) {
    resetSceneMemory(); pickScene('ppfsum');
    STATE.ppfSumCount = 2; ppfSumSet(0, 'y = ' + a); ppfSumSet(1, 'y = ' + b);
    if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
    recomputePpfSum(); redrawAll();
    var d = STATE.ppfSumData || {};
    return { tex: String(d.formulaTex || ''), Xtot: d.Xtot, Ytot: d.Ytot, kinks: d.kinks || [] };
  };
  var p = cls('100 - 20*x + x^2'), w = cls('64 - x^3');
  var A = sum('100 - 20*x + x^2', '50 - 5*x'), B = sum('64 - x^3', '30 - 12*x');
  var kx = function (o, i) { return (o.kinks[i] || [])[0]; };
  var ky = function (o, i) { return (o.kinks[i] || [])[1]; };
  return { pType: p.type, pCost: ppfCostOf(p), pXmax: p.Xmax, pYmax: p.Ymax, pC1: p.c1, pC2: p.c2,
           wType: w.type, wCost: ppfCostOf(w), wK: w.k, wXmax: w.Xmax, wYmax: w.Ymax,
           aP1: A.tex.indexOf('150 - 5X') >= 0 ? 1 : 0,
           aP2: A.tex.indexOf('X^2 - 40X + 400') >= 0 ? 1 : 0,
           aP3: A.tex.indexOf('100 - 5X') >= 0 ? 1 : 0,
           aXtot: A.Xtot, aYtot: A.Ytot,
           aK1x: kx(A, 0), aK1y: ky(A, 0), aK2x: kx(A, 1), aK2y: ky(A, 1),
           bP1: B.tex.indexOf('94 - X^{3}') >= 0 ? 1 : 0,
           bP2: B.tex.indexOf('110 - 12X') >= 0 ? 1 : 0,
           bP3: B.tex.indexOf('64 - (X - 2,5)^{3}') >= 0 ? 1 : 0,
           bXtot: B.Xtot, bYtot: B.Ytot,
           bK1x: kx(B, 0), bK1y: ky(B, 0), bK2x: kx(B, 1), bK2y: ky(B, 1) };`);
cmp('100 − 20x + x²: семейство', r.pType, 'poly2', 0);
cmp('100 − 20x + x²: издержки', r.pCost, 'down', 0);
cmp('100 − 20x + x²: Xmax', r.pXmax, 10, 1e-6);
cmp('100 − 20x + x²: Ymax', r.pYmax, 100, 1e-9);
cmp('100 − 20x + x²: c₁', r.pC1, -20, 1e-6);
cmp('100 − 20x + x²: c₂', r.pC2, 1, 1e-6);
cmp('64 − x³: семейство', r.wType, 'power', 0);
cmp('64 − x³: издержки', r.wCost, 'up', 0);
cmp('64 − x³: показатель k', r.wK, 3, 1e-6);
cmp('64 − x³: Xmax', r.wXmax, 4, 1e-6);
cmp('64 − x³: Ymax', r.wYmax, 64, 1e-9);
cmp('многочлен+прямая: участок 150 − 5X', r.aP1, 1, 0);
cmp('многочлен+прямая: участок X² − 40X + 400', r.aP2, 1, 0);
cmp('многочлен+прямая: участок 100 − 5X', r.aP3, 1, 0);
cmp('многочлен+прямая: конец X', r.aXtot, 20, 1e-4);
cmp('многочлен+прямая: конец Y', r.aYtot, 150, 1e-6);
cmp('многочлен+прямая: узел 1 X', r.aK1x, 10, 1e-6);
cmp('многочлен+прямая: узел 1 Y', r.aK1y, 100, 1e-6);
cmp('многочлен+прямая: узел 2 X', r.aK2x, 15, 1e-6);
cmp('многочлен+прямая: узел 2 Y', r.aK2y, 25, 1e-6);
cmp('степенная+прямая: участок 94 − X³', r.bP1, 1, 0);
cmp('степенная+прямая: участок 110 − 12X', r.bP2, 1, 0);
cmp('степенная+прямая: участок 64 − (X − 2,5)³', r.bP3, 1, 0);
cmp('степенная+прямая: конец X', r.bXtot, 6.5, 1e-4);
cmp('степенная+прямая: конец Y', r.bYtot, 94, 1e-6);
cmp('степенная+прямая: узел 1 X', r.bK1x, 2, 1e-6);
cmp('степенная+прямая: узел 1 Y', r.bK1y, 86, 1e-6);
cmp('степенная+прямая: узел 2 X', r.bK2x, 4.5, 1e-6);
cmp('степенная+прямая: узел 2 Y', r.bK2y, 56, 1e-6);

head('Приёмка 31.08 · смешанная пара КПВ и параметрическая запись');
r = await run(`
  resetSceneMemory(); pickScene('ppfsum');
  STATE.ppfSumCount = 2; ppfSumSet(0, 'y = 100 - x^2'); ppfSumSet(1, 'y = 20 - 10*sqrt(x)');
  if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
  recomputePpfSum(); redrawAll();
  var d = STATE.ppfSumData || {};
  var q1 = compileFormula('100 - x^2'), q2 = compileFormula('20 - 10*sqrt(x)');
  var f1 = function (x) { return ppfEvalWith(q1.compiled, x); };
  var f2 = function (x) { return ppfEvalWith(q2.compiled, x); };
  var cs = [classifyPpf(f1), classifyPpf(f2)];
  var rec = ppfSumMixedPair(cs);
  var worst = 0;
  for (var i = 0; i <= 200; i++) {
    var X = 14 * i / 200;
    var a = rec ? rec.evalY(X) : NaN, b = maxAllocY(f1, f2, X, 10, 4);
    if (isFinite(a) && isFinite(b)) worst = Math.max(worst, Math.abs(a - b));
  }
  var F1 = ppfFam(cs[0]), F2 = ppfFam(cs[1]);
  var corner5 = Math.max(F2.Ymax(cs[1]) + F1.f(cs[0], 5), F1.f(cs[0], 5 - F2.Xmax(cs[1])));
  return { n: rec ? rec.pieces.length : 0, Xtot: d.Xtot, Ytot: d.Ytot,
           at5: rec ? rec.evalY(5) : NaN, corner5: corner5, worst: worst,
           k1x: (d.kinks[0] || [])[0], k1y: (d.kinks[0] || [])[1],
           k2x: (d.kinks[1] || [])[0], k2y: (d.kinks[1] || [])[1] };`);
cmp('смешанная пара: участков', r.n, 3, 0);
cmp('смешанная пара: конец X', r.Xtot, 14, 1e-4);
cmp('смешанная пара: конец Y', r.Ytot, 120, 1e-6);
cmp('смешанная пара: узел 1 X', r.k1x, 4.386, 1e-3);
cmp('смешанная пара: узел 1 Y', r.k1y, 100.7628, 1e-3);
cmp('смешанная пара: узел 2 X', r.k2x, 5.25, 1e-3);
cmp('смешанная пара: узел 2 Y', r.k2y, 98.4375, 1e-3);
cmp('смешанная пара: Y при X = 5 (внутреннее решение)', r.at5, 99.0746, 1e-3);
cmp('то же по одним УГЛАМ — было бы ровно 99', r.corner5, 99, 1e-6);
cmp('сверка с численным Минковским, 200 точек', r.worst, 0, 1e-6);

/* --- Сессия 01.09: ноль значит ноль, погашенная кривая, MSB/MSC ------- */
head('Сессия 01.09 · ноль значит ноль');
r = await run(MKT + `setDS('ceil', '100-Q', 'Q'); setType('ceiling'); setPReg(0); redrawAll();
  return { Q: STATE.pc.Qtrade, cs: STATE.pc.cs, ps: STATE.pc.ps, dwl: STATE.pc.dwl,
           no: !!STATE.pc.noMarket };`);
cmp('потолок 0: объём торговли', r.Q, 0, 1e-9);
cmp('потолок 0: CS', r.cs, 0, 1e-9);
cmp('потолок 0: PS', r.ps, 0, 1e-9);
cmp('потолок 0: DWL', r.dwl, 2500, 1e-3);
cmp('потолок 0: рынка нет', r.no, true, 0);
r = await run(MKT + `setDS('ceil', '100-Q', 'Q'); setType('floor'); setPReg(101); redrawAll();
  return { Q: STATE.pc.Qtrade, dwl: STATE.pc.dwl };`);
cmp('пол 101: объём торговли', r.Q, 0, 1e-9);
cmp('пол 101: DWL', r.dwl, 2500, 1e-3);
r = await run(MKT + `setDS('ceil', '100-Q', 'Q'); setType('ceiling'); setPReg(40); redrawAll();
  return { Q: STATE.pc.Qtrade, gap: STATE.pc.gap };`);
cmp('потолок 40 (связывает): Q', r.Q, 40, 1e-6);
cmp('потолок 40: дефицит', r.gap, 20, 1e-6);
r = await run(MKT + `setDS('sd', '100-Q', 'Q');
  var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
  s.visible = false; redrawAll();
  var out = { S: STATE.S ? 1 : 0, eq: STATE.eq ? 1 : 0, cs: STATE.cs, ps: STATE.ps };
  s.visible = true; redrawAll();
  out.backQ = STATE.eq.Q; out.backCs = STATE.cs;
  return out;`);
cmp('погашенная S: для модели её нет', r.S, 0, 0);
cmp('погашенная S: равновесия нет', r.eq, 0, 0);
cmp('погашенная S: CS пуст', r.cs === null, true, 0);
cmp('галочка вернула равновесие', r.backQ, 50, 1e-6);
cmp('галочка вернула CS', r.backCs, 1250, 1e-3);
r = await run(MKT + `setDS('mono', '100-Q', '20'); setType('quota'); setQuota(0); redrawAll();
  var t = STATE.monoQuota || {}; return { b: t.binding ? 1 : 0, Q: t.Q, ps: t.psM, cs: t.csM, dwl: t.dwl };`);
cmp('монополия, квота 0: связывает', r.b, 1, 0);
cmp('квота 0: Q', r.Q, 0, 1e-9);
cmp('квота 0: PS', r.ps, 0, 1e-9);
cmp('квота 0: CS', r.cs, 0, 1e-9);
cmp('квота 0: DWL', r.dwl, 3200, 1e-3);

head('Сессия 01.09 · MSB и MSC слышат набранное');
r = await page.evaluate(async () => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  resetSceneMemory(); pickScene('ext');
  updateCurveExpr(STATE.curves.find(c => c.role === 'demand'), '100-Q');
  updateCurveExpr(STATE.curves.find(c => c.role === 'supply'), 'Q');
  redrawAll();
  ['msb', 'msc'].forEach(k => { STATE[k + 'On'] = true; });
  // Печатаем ТОЛЬКО событием input — так же, как шлёт мост MathLive.
  const put = (id, txt) => {
    const i = document.getElementById(id);
    i.disabled = false; i.value = txt;
    i.dispatchEvent(new Event('input', { bubbles: true }));
  };
  put('inp-msb', '100 - a*Q'); put('inp-msc', 'b*Q');
  await wait(420);
  STATE.params.a = Object.assign({ min: 0, max: 10, step: 0.1 }, STATE.params.a, { value: 3.3 });
  STATE.params.b = Object.assign({ min: 0, max: 10, step: 0.1 }, STATE.params.b, { value: 2.6 });
  redrawAll();
  await wait(200);
  const e = STATE.ext || {};
  return { msb: STATE.msbExpr, msc: STATE.mscExpr, Qopt: e.Qopt, Popt: e.Popt, Qmkt: e.Qmkt };
});
cmp('MSB дошла до состояния', r.msb, '100 - a*Q', 0);
cmp('MSC дошла до состояния', r.msc, 'b*Q', 0);
cmp('общественный оптимум Q', r.Qopt, 16.9492, 1e-3);
cmp('общественный оптимум P', r.Popt, 44.0678, 1e-3);
cmp('рыночное равновесие не сдвинулось', r.Qmkt, 50, 1e-4);

head('Сессия 01.09 · ключевые точки');
r = await run(MKT + `setDS('sd', '100-Q', 'Q');
  var k = keyTargets();
  var at = function (x, y) { return k.some(function (p) {
    return Math.abs(p.x - x) < 0.5 && Math.abs(p.y - y) < 0.5; }) ? 1 : 0; };
  return { n: k.length, pr1: at(0, 50), pr2: at(50, 0) };`);
cmp('«Спрос и предложение»: ключевых точек', r.n, 6, 0);
cmp('проекция равновесия (0; 50)', r.pr1, 1, 0);
cmp('проекция равновесия (50; 0)', r.pr2, 1, 0);
r = await run(`pickScene('sdsum'); redrawAll();
  var k = keyTargets().filter(function (p) {
    return Math.abs(p.x - 40) < 0.5 && Math.abs(p.y - 60) < 0.5; })[0];
  return { есть: k ? 1 : 0, хоз: (k && k.owners.indexOf('рыночный спрос') >= 0) ? 1 : 0,
           Q: STATE.eq.Q, cs: STATE.cs, ps: STATE.ps };`);
cmp('излом суммарного спроса (40; 60) в списке', r['есть'], 1, 0);
cmp('его хозяин — суммарный спрос', r['хоз'], 1, 0);
cmp('числа сложения не сдвинулись: Q*', r.Q, 70, 1e-4);
cmp('CS', r.cs, 1625, 1e-3);
cmp('PS', r.ps, 1325, 1e-3);


/* ================================================================
   СЕССИЯ 01.09 (2) · МОНОПОЛИЯ: ИЗЛИШКИ СЧИТАЮТСЯ И РИСУЮТСЯ.

   ⚠️ ПЛОЩАДИ БЕРУТСЯ У НАРИСОВАННОГО, а не у состояния. Иначе проверка не
   заметила бы ровно того дефекта, ради которого заведена: числа PS и VC в
   монополии под налогом считались бы верно, а заливок на холсте не было бы
   вовсе. Площадь фигуры меряется по её же пути: точки пути переводятся
   обратно в координаты модели и складываются формулой площади многоугольника.
   Числом узлов пути и порядком элементов НИЧЕГО не закрепляется.
   ================================================================ */
const AREA = `
  var areaOf = function (legend) {
    var el = document.querySelector('#chart [data-legend="' + legend + '"]');
    if (!el) return 0;
    var pts = [];
    String(el.getAttribute('d') || '').replace(
      /[ML](-?[\\d.]+),(-?[\\d.]+)/g,
      function (_, x, y) { pts.push([sx.invert(+x), sy.invert(+y)]); return ''; });
    if (pts.length < 3) return 0;
    var a = 0;
    for (var i = 0; i < pts.length; i++) {
      var j = (i + 1) % pts.length;
      a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1];
    }
    return Math.abs(a) / 2;
  };
  var CSA = 'Излишек покупателя (CS)', PSA = 'Излишек производителя (TR - VC)';
  var VCA = 'Переменные издержки (VC)', DWLA = 'Потери общества (DWL)';
`;

head('Сессия 01.09 (2) · монополия под налогом');
r = await run(MKT + AREA + `setDS('mono', '100-Q', '20');
  STATE.showMonoVC = true; STATE.showMonoPS = true; STATE.showMonoCS = true;
  setType('tax'); setTaxForm('unit'); setTax(20); redrawAll();
  var t = STATE.monoTax || {}, m = STATE.mono || {};
  var whole = integrate(function (q) { return evalCurve(STATE.D, q) - mcAt(q); }, 0, m.Qc);
  var money = areaOf('Сбор бюджета');
  return { Q: t.Qt, P: t.Pt, cs: t.csM, vc: t.vcM, ps: t.psM, bud: t.budget, dwl: t.dwl,
           aCS: areaOf(CSA), aVC: areaOf(VCA), aPS: areaOf(PSA), aDWL: areaOf(DWLA),
           aMoney: money, whole: whole,
           ident: areaOf(CSA) + areaOf(PSA) + money + areaOf(DWLA) };`);
cmp('налог 20: Q', r.Q, 30, 1e-3);
cmp('налог 20: P', r.P, 70, 1e-3);
cmp('налог 20: CS', r.cs, 450, 1e-2);
cmp('налог 20: VC', r.vc, 600, 1e-2);
cmp('налог 20: PS', r.ps, 900, 1e-2);
cmp('налог 20: сбор бюджета', r.bud, 600, 1e-2);
cmp('налог 20: DWL', r.dwl, 1250, 1e-2);
cmp('нарисован CS', r.aCS, 450, 0.5);
cmp('нарисован VC', r.aVC, 600, 0.5);
cmp('нарисован PS', r.aPS, 900, 0.5);
cmp('нарисована полоса сбора', r.aMoney, 600, 0.5);
cmp('нарисован DWL', r.aDWL, 1250, 0.5);
cmp('весь общественный излишек', r.whole, 3200, 1e-2);
cmp('тождество CS + PS + сбор + DWL', r.ident, 3200, 1);

head('Сессия 01.09 (2) · монополия под субсидией');
r = await run(MKT + AREA + `setDS('mono', '100-Q', '20');
  STATE.showMonoVC = true; STATE.showMonoPS = true; STATE.showMonoCS = true;
  setType('subsidy'); setTaxForm('unit'); setTax(10); redrawAll();
  var t = STATE.monoTax || {}, m = STATE.mono || {};
  var whole = integrate(function (q) { return evalCurve(STATE.D, q) - mcAt(q); }, 0, m.Qc);
  var money = areaOf('Расход бюджета');
  return { Q: t.Qt, P: t.Pt, cs: t.csM, vc: t.vcM, ps: t.psM, bud: t.budget, dwl: t.dwl,
           aCS: areaOf(CSA), aVC: areaOf(VCA), aPS: areaOf(PSA), aDWL: areaOf(DWLA),
           aMoney: money, whole: whole,
           ident: areaOf(CSA) + areaOf(PSA) - money + areaOf(DWLA) };`);
cmp('субсидия 10: Q', r.Q, 45, 1e-3);
cmp('субсидия 10: P', r.P, 55, 1e-3);
cmp('субсидия 10: CS', r.cs, 1012.5, 1e-2);
cmp('субсидия 10: VC', r.vc, 900, 1e-2);
cmp('субсидия 10: PS', r.ps, 2025, 1e-2);
cmp('субсидия 10: расход бюджета', r.bud, -450, 1e-2);
cmp('субсидия 10: DWL', r.dwl, 612.5, 1e-2);
cmp('нарисован CS', r.aCS, 1012.5, 0.5);
cmp('нарисован VC', r.aVC, 900, 0.5);
cmp('нарисован PS', r.aPS, 2025, 0.5);
cmp('нарисована полоса расхода', r.aMoney, 450, 0.5);
cmp('нарисован DWL', r.aDWL, 612.5, 0.5);
cmp('тождество CS + PS − расход + DWL', r.ident, 3200, 1);

head('Сессия 01.09 (2) · дискриминация 1-й степени в первой четверти');
r = await run(MKT + AREA + `setDS('mono-d1', '100-Q', 'Q-30');
  var d = STATE.discr1 || {};
  return { Q: d.Qcomp, P: evalCurve(STATE.D, d.Qcomp), profit: d.profit,
           drawn: areaOf('Излишек фирмы: весь излишек рынка'),
           raw: integrate(function (q) { return evalCurve(STATE.D, q) - mcAt(q); }, 0, d.Qcomp),
           cut: integrate(function (q) { return -mcAt(q); }, 0, 30) };`);
cmp('MC = Q − 30: выпуск', r.Q, 65, 1e-3);
cmp('MC = Q − 30: цена', r.P, 35, 1e-3);
cmp('MC = Q − 30: прибыль', r.profit, 3775, 1e-2);
cmp('нарисованная прибыль', r.drawn, 3775, 0.5);
cmp('прибыль без отсечения (было)', r.raw, 4225, 1e-2);
cmp('кусок под осью', r.cut, 450, 1e-2);
cmp('4225 − 3775 = кусок под осью', r.raw - r.profit, 450, 2e-2);
r = await run(MKT + AREA + `setDS('mono-d1', '100-Q', 'Q');
  var d = STATE.discr1 || {};
  return { Q: d.Qcomp, profit: d.profit, drawn: areaOf('Излишек фирмы: весь излишек рынка') };`);
cmp('контроль MC = Q: выпуск', r.Q, 50, 1e-3);
cmp('контроль MC = Q: прибыль', r.profit, 2500, 1e-2);
cmp('контроль MC = Q: нарисовано', r.drawn, 2500, 0.5);

head('Сессия 01.09 (2) · составной спрос: излишки');
r = await run(AREA + `resetSceneMemory(); pickScene('mono-kink');
  STATE.kinkInput = 'individual'; STATE.kiD1 = '100 - Q'; STATE.kiD2 = '60 - Q'; STATE.kiD3 = '';
  STATE.kinkMC = '20';
  STATE.showMonoVC = true; STATE.showMonoPS = true; STATE.showMonoCS = true;
  redrawAll();
  var k = STATE.kinked || {};
  var mc = function (q) { return evalCurve(k.mcCurve, q); };
  var at40 = k.cands.filter(function (c) { return Math.abs(c.Q - 40) < 1e-6; })[0] || {};
  return { Q: k.Qstar, P: k.Pstar, prof: k.profit,
           cs: k.csM, vc: k.vcM, ps: k.psM, Qc: k.Qc, dwl: k.dwl,
           aCS: areaOf(CSA), aVC: areaOf(VCA), aPS: areaOf(PSA), aDWL: areaOf(DWLA),
           ident: areaOf(CSA) + areaOf(PSA) + areaOf(DWLA),
           whole: integrateBroken(function (q) { return k.Dfn(q) - mc(q); }, 0, k.Qc, k.kinks),
           kink: k.kinks[0], kinkP: k.Dfn(k.kinks[0]),
           mrLo: marginalRevenue(k.segs[0].D, 40), mrHi: marginalRevenue(k.segs[1].D, 40),
           profAt40: at40.profit };`);
cmp('излом ломаного спроса: Q', r.kink, 40, 1e-6);
cmp('излом ломаного спроса: P', r.kinkP, 60, 1e-6);
cmp('MR в изломе снизу', r.mrLo, 20, 1e-6);
cmp('MR в изломе сверху', r.mrHi, 40, 1e-6);
cmp('оптимум Q', r.Q, 60, 1e-3);
cmp('оптимум P', r.P, 50, 1e-3);
cmp('прибыль в оптимуме', r.prof, 1800, 1e-2);
cmp('кандидат Q = 40 даёт прибыль', r.profAt40, 1600, 1e-2);
cmp('CS', r.cs, 1300, 1e-2);
cmp('VC', r.vc, 1200, 1e-2);
cmp('PS', r.ps, 1800, 1e-2);
cmp('конкурентный выпуск', r.Qc, 120, 1e-3);
cmp('DWL', r.dwl, 900, 1e-2);
cmp('нарисован CS', r.aCS, 1300, 0.5);
cmp('нарисован VC', r.aVC, 1200, 0.5);
cmp('нарисован PS', r.aPS, 1800, 0.5);
cmp('нарисован DWL', r.aDWL, 900, 0.5);
cmp('площадь между ломаным спросом и MC', r.whole, 4000, 1e-2);
cmp('тождество CS + PS + DWL', r.ident, 4000, 1);

head('Сессия 01.09 (2) · монополист и внешний рынок');
/* Проверяется НАБЛЮДАЕМОЕ: нарисованы ли обе панели (по их заголовкам и по
   реестру панелей) и что говорит табло. Число узлов и порядок элементов не
   закрепляются. */
const D3 = `
  var seen = function (s) {
    return [].slice.call(document.querySelectorAll('#chart text'))
      .some(function (e) { return (e.textContent || '').indexOf(s) >= 0; }) ? 1 : 0;
  };
  var pans = function () { return (STATE.panels || []).map(function (p) { return p.id; }).sort().join(','); };
  var told = function (s) { return ((document.getElementById('d3-panel-probe') || document.getElementById('info-d3') || {}).textContent || '').indexOf(s) >= 0 ? 1 : 0; };
  var world = function (d1, d2, mc) {
    resetSceneMemory(); pickScene('monoexport');
    STATE.d3D1 = d1; STATE.d3D2 = d2; STATE.d3MC = mc; redrawAll();
  };
`;
for (const [tag, d2, mc, wQ, wq1, wP1, wq2] of [
  ['норма Pw = 50, MC = Q', '50', 'Q', 50, 25, 75, 25],
  ['Pw = 120 выше резервной цены', '120', 'Q', 120, 0, null, 120]]) {
  r = await run(D3 + `world('100 - Q', '${d2}', '${mc}');
    var d = STATE.discr3 || {};
    return { found: d.found ? 1 : 0, Qtot: d.Qtot, q1: d.q1, P1: d.P1, q2: d.q2,
             t1: seen('Внутренний рынок'), t2: seen('Экспорт по мировой цене'),
             pans: pans(), noHome: told('рынка нет') };`);
  cmp(tag + ': общий выпуск', r.Qtot, wQ, 1e-3);
  cmp(tag + ': внутри q₁', r.q1, wq1, 1e-3);
  if (wP1 != null) cmp(tag + ': внутри P₁', r.P1, wP1, 1e-3);
  cmp(tag + ': экспорт q₂', r.q2, wq2, 1e-3);
  cmp(tag + ': обе панели нарисованы', r.t1 + r.t2, 2, 0);
  cmp(tag + ': реестр панелей', r.pans, 'mini-1,mini-2', 0);
}
r = await run(D3 + `world('100 - Q', '120', 'Q');
  return { noHome: told('рынка нет') };`);
cmp('Pw выше резервной цены: «внутреннего рынка нет»', r.noHome, 1, 0);

r = await run(D3 + `world('100 - Q', '50', '5');
  var d = STATE.discr3 || {}, u = d.unbounded || {};
  return { found: d.found ? 1 : 0, unb: d.unbounded ? 1 : 0, q1: u.q1, P1: u.P1, Pw: u.Pw,
           t1: seen('Внутренний рынок'), t2: seen('Экспорт по мировой цене'),
           note: seen('Объём экспорта не ограничен'), pans: pans(),
           says: told('не ограничен') };`);
cmp('MC = 5 ниже Pw: общий выпуск не найден', r.found, 0, 0);
cmp('MC = 5 ниже Pw: внутренний рынок посчитан', r.unb, 1, 0);
cmp('MC = 5 ниже Pw: внутри q₁', r.q1, 25, 1e-3);
cmp('MC = 5 ниже Pw: внутри P₁', r.P1, 75, 1e-3);
cmp('MC = 5 ниже Pw: обе панели нарисованы', r.t1 + r.t2, 2, 0);
cmp('MC = 5 ниже Pw: реестр панелей', r.pans, 'mini-1,mini-2', 0);
cmp('MC = 5 ниже Pw: подпись на правой панели', r.note, 1, 0);
cmp('MC = 5 ниже Pw: табло говорит «не ограничен»', r.says, 1, 0);

head('Сессия 01.09 (2) · ключевые точки мини-панелей');
r = await run(D3 + `world('100 - Q', '50', 'Q');
  var at = function (list, x, y) { return list.some(function (p) {
    return Math.abs(p.x - x) < 0.5 && Math.abs(p.y - y) < 0.5; }) ? 1 : 0; };
  var L = keyTargets('mini-1'), R = keyTargets('mini-2');
  var proj = L.filter(function (p) { return /^проекция/.test(p.name); })[0];
  /* ⚠️ Различающая точка — та, что бывает ТОЛЬКО на своей панели. Проекция
     (25; 0) есть у обеих законно: внутри продают 25 и на экспорт идёт 25.
     А цена 75 существует лишь на внутреннем рынке. */
  return { l: at(L, 25, 75), lx: at(L, 25, 0), ly: at(L, 0, 75),
           r: at(R, 25, 75) + at(R, 0, 75), rOwn: at(R, 25, 50),
           name: proj ? proj.name : '' };`);
cmp('левая панель: точка (25; 75)', r.l, 1, 0);
cmp('левая панель: проекция (0; 75)', r.ly, 1, 0);
cmp('левая панель: проекция (25; 0)', r.lx, 1, 0);
cmp('правая панель: точки левой не появились', r.r, 0, 0);
cmp('правая панель: своя точка (25; 50)', r.rOwn, 1, 0);
cmp('имя проекции без мёртвой замены', /^проекция .* на ось [QP]$/.test(r.name), true, 0);

head('Сессия 01.09 (2) · квота 31.08 не сдвинулась');
r = await run(MKT + `setDS('mono', '100-Q', '20'); setType('quota'); setQuota(20); redrawAll();
  var t = STATE.monoQuota || {};
  return { b: t.binding ? 1 : 0, Q: t.Q, P: t.price, ps: t.psM, cs: t.csM, dwl: t.dwl };`);
cmp('квота 20: связывает', r.b, 1, 0);
cmp('квота 20: Q', r.Q, 20, 1e-3);
cmp('квота 20: P', r.P, 80, 1e-3);
cmp('квота 20: PS', r.ps, 1200, 1e-2);
cmp('квота 20: CS', r.cs, 200, 1e-2);
cmp('квота 20: DWL', r.dwl, 1800, 1e-2);
for (const qk of [40, 60]) {
  r = await run(MKT + `setDS('mono', '100-Q', '20'); setType('quota'); setQuota(${qk}); redrawAll();
    var t = STATE.monoQuota || {}; return { b: t.binding ? 1 : 0 };`);
  cmp('квота ' + qk + ' не связывает', r.b, 0, 0);
}

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
console.log(bad ? ('ПРОВАЛОВ: ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' КОНТРОЛЬНЫХ ЧИСЕЛ СОШЛИСЬ'));
await browser.close();
process.exit(bad ? 1 : 0);
