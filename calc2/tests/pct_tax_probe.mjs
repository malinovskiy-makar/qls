/* Прибор «процентные налоги и субсидии»: четыре процентные формы против
   теоремы эквивалентности, и правило первой четверти против галочки.

   Числа печатаются ВСЕГДА, а не только при провале: этим прибором снимаются
   и «до», и «после», и сравнивать надо именно числа, а не слово OK.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/pct_tax_probe.mjs                 # всё
     node calc2/tests/pct_tax_probe.mjs Э Г             # только эти наборы

   Наборы:
     Э — эквивалентность налогов: D 120−Q, S Q; потоварный 40, акциз 50 %,
         НДС 100 %. Все три обязаны дать ОДНУ точку;
     С — субсидии: те же кривые, ставка 50 %, оба процентных вида;
     П — центр поворота: D 120−Q, S 0.5Q+30, акциз 25 %;
     Г — галочка «только первая четверть» против правила первой четверти:
         экономическая сцена и «Математика» рядом;
     О — обнуление ставки при смене вида и отсутствие рублей у процентных форм.

   ⚠️ Наборы с налогом идут в сцене «Налоги и субсидии», а не в «Спросе и
   предложении»: в последней весь блок вмешательства заперт каскадом сцен
   (lock: sec-tax), и ставку там задать нечем. Кривые те же самые.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const want = process.argv.slice(2).map(s => s.toUpperCase());
const need = (name) => !want.length || want.includes(name);

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

/* Развернуть налоговую сцену: свои кривые, свой вид вмешательства, своя ставка.
   Формулы ставим через updateCurveExpr — тем же путём, что и человек в поле. */
const SETUP = `
function pctSetup(dExpr, sExpr, type, form, rate) {
  resetSceneMemory();
  pickScene('taxes');
  var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
  var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
  if (d) updateCurveExpr(d, dExpr);
  if (s) updateCurveExpr(s, sExpr);
  setType(type);
  setTaxForm(form);
  setTax(rate);
  redrawAll();
}
// Снимок налогового табло: всё, ради чего заведён прибор, одним объектом.
function pctSnap() {
  var te = STATE.taxEq;
  var rl = document.getElementById('rate-letter');
  var sl = document.getElementById('tax-slider');
  var inp = document.getElementById('tax-input');
  var val = document.getElementById('tax-val');
  var hint = document.getElementById('tax-hint');
  var keys = document.getElementById('info-eq');
  var txbox = document.getElementById('info-tax');
  return {
    kind: STATE.taxKind, form: STATE.taxForm, subKind: STATE.subKind,
    type: STATE.intervType, rate: STATE.tax,
    active: !!STATE.taxActive,
    Q: te ? te.Q : null, Pd: te ? te.Pb : null, Ps: te ? te.Ps : null,
    money: STATE.tx, budget: STATE.budget, dwl: STATE.dwl,
    cs: STATE.csTax, ps: STATE.psTax,
    letter: rl ? rl.textContent.trim() : '',
    sliderMax: sl ? sl.max : '', inputMax: inp ? inp.max : '',
    valText: val ? val.textContent.trim() : '',
    inputValue: inp ? inp.value : '',
    hint: hint ? hint.textContent.replace(/\\s+/g, ' ').trim() : '',
    keysText: keys ? keys.textContent.replace(/\\s+/g, ' ').trim() : '',
    taxText: txbox ? txbox.textContent.replace(/\\s+/g, ' ').trim() : '',
  };
}
// Текст «Объяснения модели» без невидимой копии формул для чтецов экрана.
function pctExplain() {
  var ex = document.getElementById('ex-body');
  if (!ex) return '';
  var clone = ex.cloneNode(true);
  clone.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
  return clone.textContent.replace(/\\s+/g, ' ').trim();
}
// Сколько точек НАРИСОВАННОГО пути кривой лежат ниже нуля по вертикали.
function pctBelowAxis(pick) {
  var out = [];
  document.querySelectorAll('path[data-curve]').forEach(function (el) {
    var id = +el.getAttribute('data-curve');
    var cur = STATE.curves.find(function (c) { return c.id === id; });
    if (pick && !pick(cur)) return;
    var pts = [];
    String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
      var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
      if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
    });
    var below = pts.filter(function (p) { return p[1] < -1e-6; });
    out.push({
      role: cur ? cur.role : null, expr: cur ? String(cur.expr || '') : '',
      n: pts.length, below: below.length,
      minP: pts.length ? Math.min.apply(null, pts.map(function (p) { return p[1]; })) : null,
    });
  });
  return out;
}
`;
await page.addScriptTag({ content: SETUP });

const run = (code) => page.evaluate(`(function(){ ${code} })()`);

/* ── НАБОР Э. Теорема эквивалентности налогов ───────────────────────── */
if (need('Э') || need('E')) {
  console.log('\n=== НАБОР Э (эквивалентность налогов): D 120-Q, S Q ===');
  const base = await run(`pctSetup('120-Q', 'Q', 'tax', 'unit', 0); return { eq: STATE.eq };`);
  show('без вмешательства Q*', base.eq && base.eq.Q, 60, 0.05);
  show('без вмешательства P*', base.eq && base.eq.P, 60, 0.05);

  const cases = [
    ['а) потоварный t = 40', 'unit', 40],
    ['б) акциз t = 50 %', 'excise', 50],
    ['в) НДС t = 100 %', 'vat', 100],
  ];
  const got = [];
  for (const [name, form, rate] of cases) {
    const s = await run(`pctSetup('120-Q', 'Q', 'tax', '${form}', ${rate}); return pctSnap();`);
    got.push(s);
    console.log(`  ${name}  [taxKind=${s.kind}, ставка ${num(s.rate)}, буква «${s.letter}», предел ${s.sliderMax}]`);
    show('    Q1', s.Q, 40, 0.05);
    show('    Pd (покупателя)', s.Pd, 80, 0.05);
    show('    Ps (продавца)', s.Ps, 40, 0.05);
    show('    сбор', s.money, 1600, 0.5);
    show('    DWL', s.dwl, 400, 0.5);
    // Тождество: сбор по формуле из таблицы обязан совпасть с (Pd − Ps)·Q.
    const byFormula = (form === 'unit') ? s.rate * s.Q
                    : (form === 'excise') ? (s.rate / 100) * s.Pd * s.Q
                    : (s.rate / 100) * s.Ps * s.Q;
    show('    сбор по формуле таблицы', byFormula, s.money, 1e-6);
  }
  const same = (a, b, t) => Math.abs(a - b) <= t;
  flag('ВСЕ ТРИ ТОЧКИ СОВПАДАЮТ (Q, Pd, Ps)',
    got.every(s => same(s.Q, got[0].Q, 1e-6) && same(s.Pd, got[0].Pd, 1e-6) && same(s.Ps, got[0].Ps, 1e-6)),
    got.map(s => `(${num(s.Q)}; ${num(s.Pd)}/${num(s.Ps)})`).join('  '));

  // Регрессия потоварного налога — числа прошлых сессий не должны съехать.
  const r = await run(`pctSetup('100-Q', 'Q', 'tax', 'unit', 20); return pctSnap();`);
  console.log('  регрессия: D 100-Q, S Q, потоварный t = 20');
  show('    Q1', r.Q, 40, 0.05);
  show('    Pb', r.Pd, 60, 0.05);
  show('    Ps', r.Ps, 40, 0.05);
  show('    сбор', r.money, 800, 0.5);
  show('    DWL', r.dwl, 100, 0.5);
}

/* ── НАБОР С. Две процентные субсидии ───────────────────────────────── */
if (need('С') || need('C')) {
  console.log('\n=== НАБОР С (субсидии): D 120-Q, S Q, ставка 50 % ===');
  for (const [name, form, wQ, wPd, wPs, wMoney, wDwl] of [
    ['от цены покупателя', 'subbuyer', 72, 48, 72, 1728, 144],
    ['от цены продавца', 'subseller', 80, 40, 80, 3200, 400],
  ]) {
    const s = await run(`pctSetup('120-Q', 'Q', 'subsidy', '${form}', 50); return pctSnap();`);
    console.log(`  субсидия ${name}  [taxKind=${s.kind}, subKind=${s.subKind}, буква «${s.letter}», предел ${s.sliderMax}]`);
    show('    Q1', s.Q, wQ, 0.05);
    show('    Pd (покупателя)', s.Pd, wPd, 0.05);
    show('    Ps (продавца)', s.Ps, wPs, 0.05);
    show('    расход (модуль)', s.money, wMoney, 0.5);
    show('    бюджет со знаком', s.budget, -wMoney, 0.5);
    show('    DWL', s.dwl, wDwl, 0.5);
    const byFormula = (form === 'subbuyer') ? 0.5 * s.Pd * s.Q : 0.5 * s.Ps * s.Q;
    show('    расход по формуле таблицы', byFormula, s.money, 1e-6);
  }
  const r = await run(`pctSetup('100-Q', 'Q', 'subsidy', 'unit', 20); return pctSnap();`);
  console.log('  регрессия: D 100-Q, S Q, потоварная субсидия s = 20');
  show('    Q1', r.Q, 60, 0.05);
  show('    бюджет со знаком', r.budget, -1200, 0.5);
  show('    DWL', r.dwl, 100, 0.5);
}

/* ── НАБОР П. Центр поворота ────────────────────────────────────────── */
if (need('П') || need('P')) {
  console.log('\n=== НАБОР П (центр поворота): D 120-Q, S 0.5*Q+30, акциз 25 % ===');
  const s = await run(`
    pctSetup('120-Q', '0.5*Q+30', 'tax', 'excise', 25);
    var snap = pctSnap();
    snap.pivot = (typeof taxPivotPoint === 'function') ? taxPivotPoint() : null;
    snap.dashed = document.querySelectorAll('[data-pivot]').length;
    return snap;
  `);
  show('Q1', s.Q, 48, 0.05);
  show('Pd', s.Pd, 72, 0.05);
  show('Ps', s.Ps, 54, 0.05);
  show('сбор', s.money, 864, 0.5);
  show('DWL', s.dwl, 108, 0.5);
  console.log('     центр поворота: ' + JSON.stringify(s.pivot));
  console.log('     пунктирных продолжений к центру поворота: ' + s.dashed);

  const c = await run(`
    pctSetup('120-Q', 'Q', 'tax', 'excise', 50);
    return { pivot: (typeof taxPivotPoint === 'function') ? taxPivotPoint() : null,
             dashed: document.querySelectorAll('[data-pivot]').length };
  `);
  console.log('     контрпример D 120-Q, S Q, акциз 50 %: центр ' + JSON.stringify(c.pivot) +
              ', продолжений ' + c.dashed);
}

/* ── НАБОР Г. Галочка против правила первой четверти ────────────────── */
if (need('Г') || need('G')) {
  console.log('\n=== НАБОР Г (галочка): «Спрос и предложение», D 100-Q, S Q, окно до Q = 200 ===');
  const on = await run(`
    resetSceneMemory(); pickScene('sd');
    var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
    var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
    if (d) updateCurveExpr(d, '100-Q');
    if (s) updateCurveExpr(s, 'Q');
    document.getElementById('inp-qmax').value = '200';
    document.getElementById('inp-pmax').value = '200';
    applyViewBounds();
    redrawAll();
    return { quad: STATE.firstQuad, pmin: CONFIG.Pmin, qmin: CONFIG.Qmin,
             curves: pctBelowAxis(function (c) { return c && (c.role === 'demand' || c.role === 'supply'); }),
             eq: STATE.eq, cs: STATE.cs, ps: STATE.ps };
  `);
  console.log(`  галочка СТОИТ (Qmin=${num(on.qmin)}, Pmin=${num(on.pmin)}):`);
  on.curves.forEach(c => console.log(`     ${c.role} «${c.expr}»: точек ${c.n}, с P<0 — ${c.below}, min P = ${num(c.minP)}`));
  show('    Q*', on.eq && on.eq.Q, 50, 0.05);
  show('    P*', on.eq && on.eq.P, 50, 0.05);
  show('    CS', on.cs, 1250, 0.5);
  show('    PS', on.ps, 1250, 0.5);

  const off = await run(`
    setFirstQuad(false); redrawAll();
    var grid = document.querySelectorAll('.grid line, [data-grid] line');
    return { quad: STATE.firstQuad, pmin: CONFIG.Pmin, qmin: CONFIG.Qmin,
             curves: pctBelowAxis(function (c) { return c && (c.role === 'demand' || c.role === 'supply'); }),
             grid: grid.length, eq: STATE.eq, cs: STATE.cs, ps: STATE.ps };
  `);
  console.log(`  галочка СНЯТА (Qmin=${num(off.qmin)}, Pmin=${num(off.pmin)}, линий сетки ${off.grid}):`);
  off.curves.forEach(c => console.log(`     ${c.role} «${c.expr}»: точек ${c.n}, с P<0 — ${c.below}, min P = ${num(c.minP)}`));
  const dem = off.curves.find(c => c.role === 'demand');
  flag('при СНЯТОЙ галочке у спроса ноль точек с P < 0', dem && dem.below === 0, dem ? String(dem.below) : 'нет кривой');
  flag('оси раздвинуты в минус', off.qmin < 0 && off.pmin < 0, `Qmin=${num(off.qmin)}, Pmin=${num(off.pmin)}`);
  flag('сетка нарисована', off.grid > 0, String(off.grid));
  show('    Q* не изменилось', off.eq && off.eq.Q, 50, 0.05);
  show('    CS не изменилось', off.cs, 1250, 0.5);

  console.log('  «Математика», парабола x^2-4: правило НЕ действует');
  const m = await run(`
    setMode('math');
    STATE.mathFormula = 'x^2-4';
    var inp = document.getElementById('inp-mathf');
    if (inp) { inp.value = 'x^2-4'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    setMathWindow(-6, 6, -6, 6);
    redrawAll();
    /* У кривой «Математики» нет data-curve: mathLine рисует безымянный path.
       Ищем ту, что ложится на x^2-4, и читаем её ГЛАВНЫМИ шкалами сцены
       (mainScales), а не sx/sy рынка — в «Математике» окно своё. */
    var ms = mainScales(), mx = ms.mx, my = ms.my;
    var best = null;
    Array.from(document.querySelectorAll('path')).forEach(function (el) {
      var pts = [];
      String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
        var mm = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
        if (mm) pts.push([mx.invert(+mm[1]), my.invert(+mm[2])]);
      });
      if (pts.length < 50) return;
      var err = 0;
      pts.forEach(function (p) { err += Math.abs(p[1] - (p[0] * p[0] - 4)); });
      err /= pts.length;
      if (!best || err < best.err) best = { err: err, pts: pts };
    });
    var pts = best ? best.pts : [];
    return { quad: STATE.firstQuad, n: pts.length, err: best ? best.err : null,
             belowY: pts.filter(function (p) { return p[1] < -1e-6; }).length,
             minY: pts.length ? Math.min.apply(null, pts.map(function (p) { return p[1]; })) : null };
  `);
  console.log(`     firstQuad=${m.quad}, точек ${m.n}, невязка с x²−4 = ${num(m.err)}, с y<0 — ${m.belowY}, min y = ${num(m.minY)}`);
  flag('парабола строится в отрицательных значениях', m.belowY > 0, String(m.belowY));
}

/* ── НАБОР О. Обнуление ставки и отсутствие рублей ──────────────────── */
if (need('О') || need('O')) {
  console.log('\n=== НАБОР О: обнуление ставки при смене вида, рубли у процентных форм ===');
  const seq = await run(`
    pctSetup('120-Q', 'Q', 'tax', 'unit', 40);
    var out = [];
    function step(name, fn) { fn(); var s = pctSnap(); s.step = name; out.push(s); }
    step('потоварный 40', function () {});
    step('-> акциз', function () { setTaxForm('excise'); });
    step('-> НДС', function () { setTaxForm('vat'); });
    step('-> потоварный', function () { setTaxForm('unit'); });
    return out;
  `);
  seq.forEach(s => console.log(`     ${s.step}: taxKind=${s.kind}, ставка=${num(s.rate)}, ` +
    `буква «${s.letter}», поле «${s.inputValue}», подпись «${s.valText}», предел ${s.sliderMax}`));
  flag('ставка обнуляется при КАЖДОЙ смене вида',
    seq.slice(1).every(s => s.rate === 0), seq.map(s => num(s.rate)).join(' -> '));
}

console.log('');
if (errs.length) { console.log('ОШИБКИ СТРАНИЦЫ:'); errs.slice(0, 8).forEach(e => console.log('  ' + e)); }
console.log(bad ? `${bad} расхождений` : 'всё сошлось');
await browser.close();
process.exit(bad ? 1 : 0);
