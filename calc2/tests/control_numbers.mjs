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

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
console.log(bad ? ('ПРОВАЛОВ: ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' КОНТРОЛЬНЫХ ЧИСЕЛ СОШЛИСЬ'));
await browser.close();
process.exit(bad ? 1 : 0);
