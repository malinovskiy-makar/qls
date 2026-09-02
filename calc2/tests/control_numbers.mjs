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

/* ================================================================
   СЕССИЯ 01.09 (3) · МЕЖДУНАРОДНАЯ ТОРГОВЛЯ.
   Квота идёт за направлением торговли, тариф упирается в цену автаркии,
   мировая цена выше резервной цены покупателя это «внутри не покупают».
   ⚠️ Площади меряются У НАРИСОВАННОГО (тот же приём, что в ADR 0057):
   треугольников потерь ДВА, поэтому складываются все фигуры с этой подписью,
   а полоса денег — прямоугольник, и площадь у неё считается по сторонам.
   ================================================================ */
const OPEN = `
  var openWorld = function (pw, tool, rate) {
    resetSceneMemory(); pickScene('smallopen');
    updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
    updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
    redrawAll();
    setOpenPw(pw); setOpenTool(tool);
    if (tool === 'tariff') STATE.openTariff = rate;
    if (tool === 'quota')  STATE.openQuota  = rate;
    redrawAll();
  };
  var polyArea = function (el) {
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
  var dwlDrawn = function () {
    var t = 0;
    [].slice.call(document.querySelectorAll('#chart path[data-legend="Потери общества (DWL)"]'))
      .forEach(function (el) { t += polyArea(el); });
    return t;
  };
  var moneyDrawn = function (legend) {
    var el = document.querySelector('#chart rect[data-legend="' + legend + '"]');
    if (!el) return 0;
    var x = +el.getAttribute('x'), y = +el.getAttribute('y');
    var w = +el.getAttribute('width'), h = +el.getAttribute('height');
    if (!(w > 0) || !(h > 0)) return 0;
    return Math.abs((sx.invert(x + w) - sx.invert(x)) * (sy.invert(y + h) - sy.invert(y)));
  };
  var quotaLabel = function () {
    var n = document.getElementById('open-quota-name');
    return n ? n.textContent.trim() : '';
  };
  var openSays = function (s) {
    return ((document.getElementById('info-open') || {}).textContent || '').indexOf(s) >= 0 ? 1 : 0;
  };
`;

head('Сессия 01.09 (3) · свободная торговля при Pw = 62 (экспорт)');
r = await run(OPEN + `openWorld(62, 'none', 0);
  var o = STATE.open || {};
  return { Qd: o.Qd, Qs: o.Qs, vol: o.volume, imp: o.importing ? 1 : 0, cs: o.csFree, ps: o.psFree };`);
cmp('Qd', r.Qd, 38, 1e-3); cmp('Qs', r.Qs, 62, 1e-3);
cmp('экспорт', r.vol, 24, 1e-3); cmp('страна экспортирует', r.imp, 0, 0);
cmp('CS свободной торговли', r.cs, 722, 1e-2);
cmp('PS свободной торговли', r.ps, 1922, 1e-2);

head('Сессия 01.09 (3) · квота становится КВОТОЙ ЭКСПОРТА');
r = await run(OPEN + `openWorld(62, 'quota', 10);
  var o = STATE.open || {};
  return { P1: o.P1, Qd1: o.Qd1, Qs1: o.Qs1, vol1: o.vol1, money: o.money,
           dP: o.dwlProd, dC: o.dwlCons, dT: o.dwlTotal, cs1: o.cs1, ps1: o.ps1,
           label: quotaLabel(), aDwl: dwlDrawn(), aMoney: moneyDrawn('Рента квоты'),
           free: o.csFree + o.psFree, after: o.cs1 + o.ps1 + o.money };`);
cmp('экспортная квота 10: внутренняя цена', r.P1, 55, 1e-3);
cmp('экспортная квота 10: Qd′', r.Qd1, 45, 1e-3);
cmp('экспортная квота 10: Qs′', r.Qs1, 55, 1e-3);
cmp('экспортная квота 10: экспорт', r.vol1, 10, 1e-3);
cmp('экспортная квота 10: рента', r.money, 70, 1e-2);
cmp('экспортная квота 10: CS', r.cs1, 1012.5, 1e-2);
cmp('экспортная квота 10: PS', r.ps1, 1512.5, 1e-2);
cmp('экспортная квота 10: потери производства', r.dP, 24.5, 1e-2);
cmp('экспортная квота 10: потери потребления', r.dC, 24.5, 1e-2);
cmp('экспортная квота 10: потери всего', r.dT, 49, 1e-2);
cmp('подпись ползунка сменила смысл', r.label, 'Квота вывоза', 0);
cmp('нарисованы оба треугольника потерь', r.aDwl, 49, 0.5);
cmp('нарисована полоса ренты', r.aMoney, 70, 0.5);
cmp('было: CS + PS свободной торговли', r.free, 2644, 1e-2);
cmp('стало: CS + PS + рента', r.after, 2595, 1e-2);
cmp('разница ровно в потерях', r.free - r.after, 49, 1e-2);

r = await run(OPEN + `openWorld(30, 'quota', 20);
  var o = STATE.open || {};
  return { P1: o.P1, imp: o.importing ? 1 : 0, label: quotaLabel(), rent: o.money };`);
cmp('импортная квота 20 не сдвинулась: цена', r.P1, 40, 1e-3);
cmp('импортная квота 20 не сдвинулась: рента', r.rent, 200, 1e-2);
cmp('у импортёра квота снова ввозная', r.label, 'Квота ввоза', 0);

head('Сессия 01.09 (3) · запретительный тариф');
r = await run(OPEN + `openWorld(43, 'tariff', 11);
  var o = STATE.open || {};
  return { P1: o.P1, Qd1: o.Qd1, Qs1: o.Qs1, vol1: o.vol1, money: o.money,
           dT: o.dwlTotal, cs1: o.cs1, ps1: o.ps1, proh: o.prohibitive ? 1 : 0,
           aDwl: dwlDrawn(), aMoney: moneyDrawn('Доход бюджета'),
           says: openSays('Тариф запретительный') };`);
cmp('тариф 11: внутренняя цена равна автаркической', r.P1, 50, 1e-3);
cmp('тариф 11: Qd′', r.Qd1, 50, 1e-3);
cmp('тариф 11: Qs′', r.Qs1, 50, 1e-3);
cmp('тариф 11: импорт', r.vol1, 0, 1e-6);
cmp('тариф 11: доход бюджета', r.money, 0, 1e-6);
cmp('тариф 11: потерь нет', r.dT, 0, 1e-6);
cmp('тариф 11: CS', r.cs1, 1250, 1e-2);
cmp('тариф 11: PS', r.ps1, 1250, 1e-2);
cmp('тариф 11: тариф назван запретительным', r.proh + r.says, 2, 0);
cmp('тариф 11: треугольников не нарисовано', r.aDwl, 0, 1e-6);
cmp('тариф 11: полосы бюджета не нарисовано', r.aMoney, 0, 1e-6);

r = await run(OPEN + `openWorld(43, 'tariff', 5);
  var o = STATE.open || {};
  return { P1: o.P1, Qd1: o.Qd1, Qs1: o.Qs1, vol1: o.vol1, money: o.money,
           dT: o.dwlTotal, proh: o.prohibitive ? 1 : 0, aDwl: dwlDrawn() };`);
cmp('обычный тариф 5: внутренняя цена', r.P1, 48, 1e-3);
cmp('обычный тариф 5: Qd′', r.Qd1, 52, 1e-3);
cmp('обычный тариф 5: Qs′', r.Qs1, 48, 1e-3);
cmp('обычный тариф 5: импорт', r.vol1, 4, 1e-3);
cmp('обычный тариф 5: доход бюджета', r.money, 20, 1e-2);
cmp('обычный тариф 5: потери общества', r.dT, 25, 1e-2);
cmp('обычный тариф 5: не запретительный', r.proh, 0, 0);
cmp('обычный тариф 5: потери нарисованы', r.aDwl, 25, 0.5);

head('Сессия 01.09 (3) · мировая цена выше резервной цены покупателя');
r = await run(OPEN + `openWorld(120, 'none', 0);
  var o = STATE.open || {};
  return { pw: o.Pw, Qd: o.Qd, Qs: o.Qs, vol: o.volume, imp: o.importing ? 1 : 0,
           cs: o.csFree, ps: o.psFree, err: o.error ? 1 : 0,
           says: openSays('Внутри не покупают') };`);
cmp('Pw = 120 задаётся (потолок у модели, а не у кадра)', r.pw, 120, 1e-6);
cmp('ошибки нет', r.err, 0, 0);
cmp('Qd', r.Qd, 0, 1e-6);
cmp('Qs', r.Qs, 120, 1e-3);
cmp('экспорт', r.vol, 120, 1e-3);
cmp('страна экспортирует', r.imp, 0, 0);
cmp('CS', r.cs, 0, 1e-6);
cmp('PS', r.ps, 7200, 1e-2);
cmp('табло говорит «Внутри не покупают»', r.says, 1, 0);

r = await run(OPEN + `openWorld(0, 'none', 0);
  var o = STATE.open || {};
  return { pw: o.Pw, Qd: o.Qd, Qs: o.Qs, imp: o.importing ? 1 : 0, cs: o.csFree, ps: o.psFree };`);
cmp('Pw = 0 (первая сессия) не сдвинулось: Pw', r.pw, 0, 1e-6);
cmp('Pw = 0: Qd', r.Qd, 100, 1e-3);
cmp('Pw = 0: Qs', r.Qs, 0, 1e-3);
cmp('Pw = 0: страна импортирует', r.imp, 1, 0);
cmp('Pw = 0: CS', r.cs, 5000, 1e-2);
cmp('Pw = 0: PS', r.ps, 0, 1e-6);

head('Сессия 01.09 (3) · сцена «Автаркия» убрана, галочка переименована');
r = await run(`return {
    card: document.querySelector('[data-scene="autarky"]') ? 1 : 0,
    old: (document.body.textContent || '').indexOf('Два треугольника потерь') >= 0 ? 1 : 0,
    now: ((document.querySelector('#chk-open-dwl') || {}).parentElement || {}).textContent || '' };`);
cmp('карточки «Автаркия» больше нет', r.card, 0, 0);
cmp('слов «Два треугольника потерь» на странице нет', r.old, 0, 0);
cmp('галочка называется «Потери общества»', /Потери общества/.test(r.now), true, 0);

/* ================================================================
   СЕССИЯ 01.09 (3) · ОБРЕЗКА НУЛЁМ — ВЕЗДЕ, А НЕ В ОДНОМ МЕСТЕ.
   Долг ADR 0057 закрыт: обычная монополия, потолок, пол, квота, ставка,
   составной спрос и естественная монополия берут нижнюю границу площади
   у одного помощника mcFloor. Признак болезни — PS + VC ≠ TR.
   ================================================================ */
head('Сессия 01.09 (3) · обрезка нулём: обычная монополия');
r = await run(MKT + AREA + `setDS('mono', '100-Q', 'Q-20');
  STATE.showMonoVC = true; STATE.showMonoPS = true; STATE.showMonoCS = true; redrawAll();
  var m = STATE.mono || {};
  return { Q: m.Qm, P: m.Pm, vc: m.vcM, ps: m.psM, cs: m.csM, dwl: m.dwl,
           tr: m.Qm * m.Pm, aVC: areaOf(VCA), aPS: areaOf(PSA), aDWL: areaOf(DWLA) };`);
cmp('MC = Q − 20: выпуск', r.Q, 40, 1e-3);
cmp('MC = Q − 20: цена', r.P, 60, 1e-3);
cmp('MC = Q − 20: VC (было 0)', r.vc, 200, 1e-2);
cmp('MC = Q − 20: PS (было 2400)', r.ps, 2200, 1e-2);
cmp('MC = Q − 20: DWL не сдвинулся', r.dwl, 400, 1e-2);
cmp('MC = Q − 20: PS + VC = TR', r.ps + r.vc, 2400, 1e-2);
cmp('MC = Q − 20: выручка TR', r.tr, 2400, 1e-2);
cmp('нарисован VC', r.aVC, 200, 0.5);
cmp('нарисован PS', r.aPS, 2200, 0.5);
cmp('нарисован DWL', r.aDWL, 400, 0.5);

r = await run(MKT + `setDS('mono', '100-Q', 'Q'); redrawAll();
  var m = STATE.mono || {};
  return { Q: m.Qm, P: m.Pm, vc: m.vcM, ps: m.psM };`);
cmp('контроль MC = Q: выпуск не сдвинулся', r.Q, 33.3333, 1e-3);
cmp('контроль MC = Q: цена не сдвинулась', r.P, 66.6667, 1e-3);
cmp('контроль MC = Q: VC не сдвинулся', r.vc, 555.5556, 1e-2);
cmp('контроль MC = Q: PS не сдвинулся', r.ps, 1666.6667, 1e-2);

head('Сессия 01.09 (3) · обрезка нулём: вмешательство, квота, пол, потолок');
/* ⚠️ Числа названы поимённо, а не проверены неравенством «VC > 0». У пола 80 и
   квоты 20 выпуск равен 20, предельные издержки Q − 20 на всём этом отрезке
   НЕ ПОЛОЖИТЕЛЬНЫ, и ноль там — верный ответ, а не болезнь. Отличает верный
   ноль от больного как раз обрезка: без неё те же случаи дают VC = −200.
   ⚠️ Тождество PS + VC = TR у СТАВКИ не выполняется, и это не ошибка: между
   MC и MC ± ставка лежат деньги бюджета, они в излишек не входят (ADR 0057). */
for (const [tag, setup, key, wQ, wP, wVC, wPS] of [
  ['потолок 50', `setType('ceiling'); setPReg(50);`, 'monoCeil', 50, 50, 450, 2050],
  ['пол 80',     `setType('floor'); setPReg(80);`,   'monoFloor', 20, 80, 0, 1600],
  ['квота 20',   `setType('quota'); setQuota(20);`,  'monoQuota', 20, 80, 0, 1600]]) {
  r = await run(MKT + `setDS('mono', '100-Q', 'Q-20'); ${setup} redrawAll();
    var t = STATE.${key} || {};
    var Q = (t.Qstar != null ? t.Qstar : t.Q), P = t.price;
    return { Q: Q, P: P, vc: t.vcM, ps: t.psM, tr: Q * P };`);
  cmp(tag + ': выпуск', r.Q, wQ, 1e-3);
  cmp(tag + ': цена', r.P, wP, 1e-3);
  cmp(tag + ': VC', r.vc, wVC, 1e-2);
  cmp(tag + ': PS', r.ps, wPS, 1e-2);
  cmp(tag + ': PS + VC = TR', r.ps + r.vc - r.tr, 0, 1e-2);
}
for (const [tag, setup, wQ, wP, wVC] of [
  ['налог 10',    `setType('tax'); setTaxForm('unit'); setTax(10);`,     36.6667, 63.3333, 138.8889],
  ['субсидия 10', `setType('subsidy'); setTaxForm('unit'); setTax(10);`, 43.3333, 56.6667, 272.2222]]) {
  r = await run(MKT + `setDS('mono', '100-Q', 'Q-20'); ${setup} redrawAll();
    var t = STATE.monoTax || {};
    return { Q: t.Qt, P: t.Pt, vc: t.vcM, ps: t.psM };`);
  cmp(tag + ': выпуск', r.Q, wQ, 1e-3);
  cmp(tag + ': цена', r.P, wP, 1e-3);
  cmp(tag + ': VC под социальной MC', r.vc, wVC, 1e-2);
  cmp(tag + ': PS не отрицателен', r.ps > 0, true, 0);
}
r = await run(MKT + AREA + `setDS('mono-kink', '100-Q', 'Q-20');
  STATE.d3D1 = '100 - Q'; STATE.d3D2 = '60 - Q'; STATE.d3MC = 'Q-20';
  STATE.showMonoVC = true; STATE.showMonoPS = true; redrawAll();
  var k = STATE.kinked || {};
  return { found: k.found ? 1 : 0, vc: k.vcM, ps: k.psM, tr: k.Qstar * k.Pstar,
           aVC: areaOf(VCA), aPS: areaOf(PSA) };`);
cmp('составной спрос: сюжет посчитан', r.found, 1, 0);
cmp('составной спрос: VC не съел сам себя', r.vc > 1e-6, true, 0);
cmp('составной спрос: PS + VC = TR', r.vc + r.ps - r.tr, 0, 1e-2);
cmp('составной спрос: нарисованный VC совпал с числом', r.aVC - r.vc, 0, 0.5);
cmp('составной спрос: нарисованный PS совпал с числом', r.aPS - r.ps, 0, 0.5);

r = await run(MKT + `setDS('mono-nat', '100-Q', 'Q-20'); STATE.natFC = 100; redrawAll();
  return { atc40: naturalATC(40), vcOnly: naturalATC(40) * 40 - 100 };`);
cmp('естественная монополия: ATC(40) считается', isFinite(r.atc40), true, 0);
cmp('естественная монополия: VC(40) обрезан нулём', r.vcOnly, 200, 0.5);

/* ================================================================
   СЕССИЯ 01.09 (3) · ПРАВАЯ ПАНЕЛЬ.
   Карточки справа сворачиваются при смене модели; пояснения под ползунками
   вмешательства живут в «Объяснении модели» и меняются вместе со смыслом;
   лишние строки убраны.
   ================================================================ */
const PANEL = `
  var opened = function (sel) {
    return [].slice.call(document.querySelectorAll(sel))
      .filter(function (e) { return e.classList.contains('open'); }).length;
  };
  var explain = function () {
    var e = document.getElementById('ex-body');
    return e ? (e.textContent || '').replace(/\\s+/g, ' ').trim() : '';
  };
  /* Абзац ПРО ВМЕШАТЕЛЬСТВО, а не весь разбор сцены. Общий рассказ сцены
     «Потолок и пол цены» законно называет оба случая сразу, поэтому искать
     в нём слово «дефицит» бессмысленно: оно там есть всегда. */
  var intervPara = function () {
    var e = document.querySelector('#ex-body .sb-note');
    return e ? (e.textContent || '').replace(/\\s+/g, ' ').trim() : '';
  };
  var panelText = function () {
    var e = document.getElementById('sec-tax');
    return e ? (e.textContent || '').replace(/\\s+/g, ' ').trim() : '';
  };
  var shown = function (id) {
    var e = document.getElementById(id);
    if (!e) return 0;
    return (e.offsetParent !== null && e.getClientRects().length > 0) ? 1 : 0;
  };
`;

head('Сессия 01.09 (3) · карточки справа сворачиваются при смене модели');
r = await run(PANEL + `resetSceneMemory(); pickScene('sd'); redrawAll();
  openSection('scoreboard'); openSection('explain');
  var before = opened('#params-panel .side-part > .fold-body');
  resetSceneMemory(); pickScene('mono'); redrawAll();
  var after = opened('#params-panel .side-part > .fold-body');
  var left = opened('#tools-panel .tools-body > .section > .fold-body');
  var inp = document.getElementById('sec-input');
  var inpOpen = (inp && inp.querySelector(':scope > .fold-body').classList.contains('open')) ? 1 : 0;
  return { before: before, after: after, left: left, inpOpen: inpOpen };`);
cmp('раскрыли две карточки справа', r.before, 2, 0);
cmp('после смены модели справа раскрытых нет', r.after, 0, 0);
/* Слева раскрытой остаётся РОВНО ОДНА карточка — «Ввод функций»: она открыта
   всегда и во всех моделях (решение владельца 22.08), и правило это. */
cmp('слева раскрыт ровно «Ввод функций»', r.left, 1, 0);
cmp('и это именно он', r.inpOpen, 1, 0);
r = await run(PANEL + `resetSceneMemory(); pickScene('mono'); redrawAll();
  openSection('scoreboard');
  return { ok: opened('#params-panel .side-part > .fold-body') };`);
cmp('прибор по-прежнему может раскрыть карточку сам', r.ok, 1, 0);

head('Сессия 01.09 (3) · пояснения вмешательства переехали в «Объяснение модели»');
for (const [tag, setup, mark] of [
  ['потоварный налог',      `setType('tax'); setTaxForm('unit'); setTaxSide('seller');`, 'Потоварный налог на стороне производителя'],
  ['налог от цены продавца',`setType('tax'); setTaxForm('vat');`,                        'продавца'],
  ['налог от цены покупателя',`setType('tax'); setTaxForm('excise');`,                   'покупателя'],
  ['потоварная субсидия',   `setType('subsidy'); setTaxForm('unit'); setTaxSide('seller');`, 'Потоварная субсидия на стороне производителя'],
  ['субсидия от цены продавца',`setType('subsidy'); setTaxForm('subseller');`,           'продавца'],
  ['субсидия от цены покупателя',`setType('subsidy'); setTaxForm('subbuyer');`,          'покупателя']]) {
  r = await run(MKT + PANEL + `setDS('taxes', '100-Q', 'Q'); ${setup} setTax(20); redrawAll();
    openSection('explain');
    return { ex: explain().indexOf(${JSON.stringify(mark)}) >= 0 ? 1 : 0,
             hintShown: shown('tax-hint'),
             exLen: explain().length };`);
  cmp(tag + ': текст в «Объяснении модели»', r.ex, 1, 0);
  cmp(tag + ': под ползунком его нет', r.hintShown, 0, 0);
  cmp(tag + ': «Объяснение модели» не пусто', r.exLen > 80, true, 0);
}

head('Сессия 01.09 (3) · у потолка и пола пояснения РАЗНЫЕ');
r = await run(MKT + PANEL + `setDS('ceil', '100-Q', 'Q'); setType('ceiling'); setPReg(40); redrawAll();
  openSection('explain');
  var c = intervPara();
  setType('floor'); setPReg(60); redrawAll();
  var f = intervPara();
  return { cDef: /дефицит/.test(c) ? 1 : 0, cSur: /избыток/.test(c) ? 1 : 0,
           fSur: /избыток/.test(f) ? 1 : 0, fDef: /дефицит/.test(f) ? 1 : 0,
           same: (c === f) ? 1 : 0, hintShown: shown('pc-hint'),
           cQueue: /очеред/.test(c) ? 1 : 0, fUnsold: /непродан/.test(f) ? 1 : 0 };`);
cmp('потолок: сказано про дефицит', r.cDef, 1, 0);
cmp('потолок: про избыток не сказано', r.cSur, 0, 0);
cmp('потолок: сказано про очередь', r.cQueue, 1, 0);
cmp('пол: сказано про избыток', r.fSur, 1, 0);
cmp('пол: про дефицит не сказано', r.fDef, 0, 0);
cmp('пол: сказано про нераспроданное', r.fUnsold, 1, 0);
cmp('тексты у пола и потолка разные', r.same, 0, 0);
cmp('под ползунком цены пояснения нет', r.hintShown, 0, 0);

head('Сессия 01.09 (3) · убранные строки');
r = await run(`resetSceneMemory(); pickScene('m-constraint'); redrawAll();
  var sb = document.getElementById('sb-body');
  var t = sb ? (sb.textContent || '') : '';
  return { seek: /Ищем/.test(t) ? 1 : 0, len: t.length };`);
cmp('«Оптимум на ограничении»: строки «Ищем» в ключевых значениях нет', r.seek, 0, 0);
cmp('ключевые значения не опустели', r.len > 20, true, 0);
r = await run(`resetSceneMemory(); pickScene('ineq'); redrawAll();
  return { alpha: document.getElementById('ineq-alpha-num') ? 1 : 0,
           ghost: document.getElementById('ineq-ghost') ? 1 : 0,
           slider: document.getElementById('ineq-alpha') ? 1 : 0 };`);
cmp('«Неравенство»: поля «α (точное значение)» нет', r.alpha, 0, 0);
cmp('«Неравенство»: галочки «было → стало» нет', r.ghost, 0, 0);
cmp('«Неравенство»: сам ползунок α на месте', r.slider, 1, 0);

/* ================================================================
   СЕССИЯ 01.09 (3) · ПОЛЯ ВВОДА И СПИСКИ.
   ================================================================ */
head('Сессия 01.09 (3) · выделение в поле формулы видно');
r = await run(`resetSceneMemory(); pickScene('sd'); redrawAll();
  var inp = document.querySelector('.f-slot input[type=text]');
  inp.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  inp.focus();
  return { woke: 1 };`);
await page.waitForTimeout(700);
r = await run(`var inp = document.querySelector('.f-slot input[type=text]');
  var mf = inp && inp._mf;
  if (!mf) return { noMf: 1 };
  mf.blur();
  return { blurred: 1 };`);
await page.waitForTimeout(200);
r = await run(`var inp = document.querySelector('.f-slot input[type=text]');
  var mf = inp._mf;
  mf.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  mf.focus();
  return { ok: 1 };`);
await page.waitForTimeout(500);
r = await run(`var inp = document.querySelector('.f-slot input[type=text]');
  var mf = inp._mf, sr = mf.shadowRoot;
  var box = sr.querySelector('.ML__selection');
  var cs = box ? getComputedStyle(box) : null;
  var rc = box ? box.getBoundingClientRect() : null;
  return { collapsed: mf.selectionIsCollapsed ? 1 : 0,
           atoms: sr.querySelectorAll('.ML__selected').length,
           boxes: sr.querySelectorAll('.ML__selection').length,
           bg: cs ? cs.backgroundColor : '',
           w: rc ? Math.round(rc.width) : 0, h: rc ? Math.round(rc.height) : 0 };`);
/* ⚠️ Правило, а не отпечаток: выделение ЕСТЬ (модель) и его ВИДНО (подложка с
   непрозрачным фоном и ненулевым размером). Ни ширина в пикселях, ни число
   выделенных узлов не закрепляются: они зависят от самой формулы. */
cmp('выделение в модели есть', r.collapsed, 0, 0);
cmp('выделенные узлы отрисованы', r.atoms > 0, true, 0);
cmp('подложка выделения нарисована', r.boxes > 0, true, 0);
cmp('подложка не прозрачная', /rgba?\(.*[1-9].*\)/.test(r.bg) && !/, 0\)$/.test(r.bg), true, 0);
cmp('подложка ненулевого размера', r.w > 2 && r.h > 2, true, 0);

head('Сессия 01.09 (3) · свои выпадающие списки вместо системных');
for (const [tag, scene, id] of [
  ['деформации графика', 'm-transform', 'math-trans'],
  ['число групп неравенства', 'ineq', 'ineq-ngroups']]) {
  r = await run(`resetSceneMemory(); pickScene('${scene}'); redrawAll();
    var sel = document.getElementById('${id}');
    var btn = sel && sel.parentNode.querySelector('.sel-btn');
    var hidden = sel ? sel.classList.contains('sel-native-hidden') : false;
    var n = sel ? sel.options.length : 0;
    if (btn) btn.click();
    var menu = document.querySelector('.sel-menu');
    var items = menu ? menu.querySelectorAll('.sel-item').length : 0;
    var picked = '';
    if (menu) { var last = menu.querySelectorAll('.sel-item')[items - 1]; last.click(); picked = sel.value; }
    return { btn: btn ? 1 : 0, hidden: hidden ? 1 : 0, n: n, items: items,
             picked: picked, lastVal: sel ? sel.options[n - 1].value : '' };`);
  cmp(tag + ': своя кнопка вместо коробочки ОС', r.btn, 1, 0);
  cmp(tag + ': системный список спрятан', r.hidden, 1, 0);
  cmp(tag + ': в меню столько же вариантов, сколько в списке', r.items, r.n, 0);
  cmp(tag + ': выбор из меню доходит до модели', r.picked, r.lastVal, 0);
}

head('Сессия 01.09 (3) · силу неравенства можно задать числом');
r = await run(`resetSceneMemory(); pickScene('ineq'); redrawAll();
  var val = document.getElementById('ineq-master-slider-val');
  var sl = document.getElementById('ineq-master-slider');
  var clickable = val ? (val.classList.contains('pchip-editable') ? 1 : 0) : 0;
  val.click();
  var inp = val.querySelector('input');
  if (!inp) return { clickable: clickable, opened: 0 };
  inp.value = 137;
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.blur();
  return { clickable: clickable, opened: 1, sl: parseFloat(sl.value),
           shown: val.textContent.trim(), s: STATE.ineqMasterS };`);
cmp('число помечено как правимое', r.clickable, 1, 0);
cmp('щелчок открывает поле точного ввода', r.opened, 1, 0);
cmp('ползунок встал на набранное', r.sl, 137, 1e-6);
cmp('на экране снова проценты', r.shown, '137%', 0);
cmp('модель приняла значение', r.s, 1.37, 1e-6);
r = await run(`var val = document.getElementById('ineq-master-slider-val');
  val.click();
  var inp = val.querySelector('input');
  inp.value = 999; inp.dispatchEvent(new Event('input', { bubbles: true })); inp.blur();
  var sl = document.getElementById('ineq-master-slider');
  return { sl: parseFloat(sl.value), max: parseFloat(sl.max) };`);
cmp('значение за границей зажимается потолком ползунка', r.sl, r.max, 1e-6);

head('Сессия 01.09 (3) · пол цены выше резервной цены покупателя');
r = await run(MKT + `setDS('ceil', '100-Q', 'Q'); setType('floor'); setPReg(101); redrawAll();
  var sl = document.getElementById('pc-slider');
  return { pReg: STATE.pReg, max: parseFloat(sl.max), Q: STATE.pc.Qtrade,
           dwl: STATE.pc.dwl, no: !!STATE.pc.noMarket, cs: STATE.pc.cs, ps: STATE.pc.ps };`);
cmp('пол 101 действительно задан (не зажат сотней)', r.pReg, 101, 1e-9);
cmp('потолок ползунка поднят выше резервной цены', r.max > 100, true, 0);
cmp('пол 101: объём торговли', r.Q, 0, 1e-9);
cmp('пол 101: рынка нет', r.no, true, 0);
cmp('пол 101: CS', r.cs, 0, 1e-9);
cmp('пол 101: PS', r.ps, 0, 1e-9);
cmp('пол 101: потери общества', r.dwl, 2500, 1e-3);

/* ================================================================
   СЕССИЯ 01.09 (3) · РАЗДЕЛ «МАТЕМАТИКА».
   ================================================================ */
head('Сессия 01.09 (3) · производная: регуляторы переехали в аналитику');
r = await run(`resetSceneMemory(); pickScene('m-tangent'); redrawAll();
  var inSide = function (id, panel) {
    var e = document.getElementById(id);
    return e && e.closest(panel) ? 1 : 0;
  };
  var sec = document.getElementById('chk-secant');
  sec.checked = true; sec.dispatchEvent(new Event('change', { bubbles: true }));
  return { x0right: inSide('mathx0-field', '#params-panel'),
           x0left: inSide('mathx0-field', '#tools-panel'),
           secRight: inSide('math-secant-row', '#params-panel'),
           dxRight: inSide('mathdx-field', '#params-panel'),
           dxShown: (document.getElementById('mathdx-field').style.display !== 'none') ? 1 : 0,
           inputLeft: inSide('inp-mathf', '#tools-panel'),
           numHidden: document.getElementById('mathx0-input').classList.contains('reg-num-hidden') ? 1 : 0,
           eq: !!document.querySelector('#mathx0-field .reg-eq') };`);
cmp('ползунок x₀ в правой панели', r.x0right, 1, 0);
cmp('его в левой больше нет', r.x0left, 0, 0);
cmp('секущая тоже справа', r.secRight, 1, 0);
cmp('её ползунок Δx уехал вместе с ней', r.dxRight, 1, 0);
cmp('и показался вместе с галочкой', r.dxShown, 1, 0);
cmp('ввод функции остался слева', r.inputLeft, 1, 0);
cmp('x₀ получил общий компонент регулятора', r.eq, true, 0);
cmp('своё числовое поле спрятано', r.numHidden, 1, 0);
r = await run(`var sec = document.getElementById('chk-secant');
  sec.checked = false; sec.dispatchEvent(new Event('change', { bubbles: true }));
  return { dxShown: (document.getElementById('mathdx-field').style.display !== 'none') ? 1 : 0 };`);
cmp('снятая галочка снова прячет Δx', r.dxShown, 0, 0);

head('Сессия 01.09 (3) · «Построение графиков» открывается с функцией');
r = await run(`resetSceneMemory(); pickScene('m-graph'); redrawAll();
  var c = (STATE.curves || [])[0] || {};
  var box = document.getElementById('sb-body');
  return { n: (STATE.curves || []).length, expr: c.expr,
           at0: c.compiled ? evalCurve(c, 0) : null,
           at2: c.compiled ? evalCurve(c, 2) : null,
           panel: box ? (box.textContent || '').length : 0 };`);
cmp('кривая одна', r.n, 1, 0);
cmp('это x^2-4', r.expr, 'x^2-4', 0);
cmp('значение в нуле', r.at0, -4, 1e-9);
cmp('значение в двойке', r.at2, 0, 1e-9);
cmp('ключевые значения не пусты', r.panel > 10, true, 0);

head('Сессия 01.09 (3) · «Функции min и max» и подсказки по наведению');
r = await run(`resetSceneMemory(); pickScene('m-minmax'); redrawAll();
  var lab = document.querySelector('#math-pane-minmax .field label');
  var t = document.getElementById('mm-mode');
  var txt = t ? (t.textContent || '').replace(/\\s+/g, ' ').trim() : '';
  var host = t ? t.parentElement : null;
  var all = host ? (host.textContent || '').replace(/\\s+/g, ' ') : '';
  return { lab: lab ? lab.textContent.trim() : '', txt: txt,
           noOld: /Наименьшую|Наибольшую/.test(all) ? 0 : 1 };`);
cmp('подпись переключателя', r.lab, 'Какую функцию ищем', 0);
cmp('прежних слов не осталось', r.noOld, 1, 0);
cmp('варианты названы min и max', /min/.test(r.txt) && /max/.test(r.txt), true, 0);

/* ⚠️ Стережём ПРАВИЛО «подсказка открывается по наведению», а не список
   кнопок: атрибута data-pop-trigger больше нет, и наведение обязано работать
   у КАЖДОЙ кнопки «?» с плашкой — иначе следующую снова забудут. */
r = await run(`var bad = [], n = 0;
  document.querySelectorAll('.hint-btn[data-pop]').forEach(function (b) {
    var pop = document.getElementById(b.getAttribute('data-pop'));
    if (!pop) return;
    n++;
    pop.classList.remove('open');
    b.dispatchEvent(new PointerEvent('pointerenter', { bubbles: true }));
    if (!pop.classList.contains('open')) bad.push(b.getAttribute('data-pop'));
    b.dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }));
  });
  return { n: n, bad: bad.length, who: bad.join(','),
           attr: document.querySelectorAll('[data-pop-trigger]').length };`);
cmp('кнопок «?» с плашкой найдено', r.n > 6, true, 0);
cmp('ни одна не осталась «только по щелчку»', r.bad, 0, 0);
cmp('меток data-pop-trigger не осталось', r.attr, 0, 0);

/* ================================================================
   СЕССИЯ 01.09 (3) · ОКНО РАСШИРЯЕТСЯ, НО НЕ СЖИМАЕТСЯ.
   ⚠️ Стережём ПРАВИЛО: «конец кривой внутри окна» и «окно не уменьшилось».
   Точные границы (600, 1000) не закрепляются: они зависят от округления
   padMax, а правило — нет.
   ================================================================ */
const GROW = `
  var setA = function (a) {
    var p = STATE.params && STATE.params.a;
    if (!p) return 'буквы a нет';
    p.value = a;
    redrawKeepingWindow();
    return null;
  };
`;
head('Сессия 01.09 (3) · масштаб расширяется под конец кривой');
r = await run(MKT + GROW + `setDS('sd', '100-a*Q', 'Q'); redrawAll();
  return { q: CONFIG.Qmax, p: CONFIG.Pmax, a: (STATE.params.a || {}).value,
           eqQ: STATE.eq.Q, eqP: STATE.eq.P };`);
cmp('a = 1: окно по Q не тронуто', r.q, 100, 1e-6);
cmp('a = 1: окно по P не тронуто', r.p, 100, 1e-6);
cmp('a = 1: равновесие', r.eqQ, 50, 1e-3);

r = await run(MKT + GROW + `setDS('sd', '100-a*Q', 'Q'); redrawAll();
  var e = setA(0.2); if (e) return { err: e }; return { ok: 1 };`);
await page.waitForTimeout(900);
r = await run(`return { q: CONFIG.Qmax, p: CONFIG.Pmax, eqQ: STATE.eq.Q, eqP: STATE.eq.P,
  zero: (function () { var d = STATE.D; return d ? curveZeroQ(d, 4096) : null; })() };`);
cmp('a = 0,2: спрос встречает ось Q при', r.zero, 500, 0.5);
cmp('a = 0,2: конец кривой внутри окна', r.q >= 500, true, 0);
cmp('a = 0,2: равновесие Q не сдвинулось', r.eqQ, 83.3333, 1e-3);
cmp('a = 0,2: равновесие P не сдвинулось', r.eqP, 83.3333, 1e-3);
cmp('a = 0,2: по P окно не раздувалось', r.p, 100, 1e-6);
const grownQ = r.q;

r = await run(GROW + `var e = setA(5); if (e) return { err: e }; return { ok: 1 };`);
await page.waitForTimeout(900);
r = await run(`return { q: CONFIG.Qmax, zero: curveZeroQ(STATE.D, 4096) };`);
cmp('a = 5: конец кривой снова близко', r.zero, 20, 0.5);
cmp('a = 5: окно НЕ сжалось', r.q >= grownQ - 1e-6, true, 0);

head('Сессия 01.09 (3) · выбор человека главнее авто-расширения');
r = await run(MKT + GROW + `setDS('sd', '100-a*Q', 'Q'); redrawAll();
  setRanges(140, 140); STATE.zoomLock = true;
  var e = setA(0.2); if (e) return { err: e }; return { ok: 1 };`);
await page.waitForTimeout(900);
r = await run(`return { q: CONFIG.Qmax, p: CONFIG.Pmax, lock: STATE.zoomLock ? 1 : 0 };`);
cmp('окно человека не тронуто по Q', r.q, 140, 1e-6);
cmp('окно человека не тронуто по P', r.p, 140, 1e-6);
cmp('замок на месте', r.lock, 1, 0);
r = await run(`resetZoom();`);
await page.waitForTimeout(300);
r = await run(`return { q: CONFIG.Qmax, lock: STATE.zoomLock ? 1 : 0 };`);
cmp('«Вернуть исходный вид» снимает замок', r.lock, 0, 0);
cmp('и показывает конец кривой целиком', r.q >= 500, true, 0);

head('Сессия 01.09 (3) · составной спрос: конец потерь виден');
r = await run(MKT + `setDS('mono-kink', '100-Q', '20');
  STATE.d3D1 = '100 - Q'; STATE.d3D2 = '60 - Q'; STATE.d3MC = '20'; redrawAll();
  return { qc: (STATE.kinked || {}).Qc, q0: CONFIG.Qmax };`);
await page.waitForTimeout(900);
r = await run(`return { qc: (STATE.kinked || {}).Qc, q: CONFIG.Qmax };`);
cmp('конкурентный выпуск', r.qc, 120, 1e-3);
cmp('окно достало до конца потерь', r.q >= 120, true, 0);

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
console.log(bad ? ('ПРОВАЛОВ: ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' КОНТРОЛЬНЫХ ЧИСЕЛ СОШЛИСЬ'));
await browser.close();
process.exit(bad ? 1 : 0);
