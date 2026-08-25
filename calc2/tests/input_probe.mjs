/* Прибор «ядро и конструктор»: кадр против математики, утечка строк
   конструктора кусочной, ширина поля, вопросики, подсветка карточки.

   Числа печатаются ВСЕГДА, а не только при провале: этим прибором снимаются
   и «до», и «после», и сравнивать надо именно числа, а не слово OK.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/input_probe.mjs                 # всё
     node calc2/tests/input_probe.mjs К П             # только эти наборы

   Наборы:
     К — кадр и ядро: пять сцен, каждая на ТРЁХ масштабах (стартовом,
         суженном до 30 и расширенном до 400). Числа обязаны совпасть;
     П — утечка строк конструктора кусочной между полями и сценами;
     Ш — ширина поля под собранной кусочной записью;
     В — одинокие «?» в левой панели;
     Ф — подсветка первой карточки на первом экране;
     З — ширина аналитической записи в правой панели.
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
const num = (v) => (typeof v === 'number' && isFinite(v)) ? (Math.round(v * 1e6) / 1e6) : String(v);
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
// Три числа с трёх масштабов совпадают между собой? Это и есть инвариант фазы 1.
function same3(label, vals, tol) {
  const ok = vals.every(v => typeof v === 'number' && isFinite(v)) &&
    Math.abs(vals[0] - vals[1]) <= tol && Math.abs(vals[1] - vals[2]) <= tol;
  if (!ok) bad++;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + ': ' + vals.map(num).join('  |  ') + '   (допуск ' + tol + ')');
}

const HELP = `
/* Три масштаба одной рукой: стартовый (какой поставила сцена), суженный и
   расширенный. Между ними — та подготовка, которую сцена требует заново
   (формулы переввести, точку эластичности поставить): определитель линейности
   срабатывает при РАЗБОРЕ формулы, а не каждый кадр. */
function ipScales(prepare, snap) {
  var out = [];
  prepare();
  redrawAll();
  out.push(Object.assign({ win: ipWin() }, snap()));
  setRanges(30, 30); prepare(); redrawAll();
  out.push(Object.assign({ win: ipWin() }, snap()));
  setRanges(400, 400); prepare(); redrawAll();
  out.push(Object.assign({ win: ipWin() }, snap()));
  return out;
}
function ipWin() { return { qmax: CONFIG.Qmax, pmax: CONFIG.Pmax }; }
function ipCurve(role) { return STATE.curves.find(function (c) { return c.role === role; }); }
function ipSet(role, expr) { var c = ipCurve(role); if (c) updateCurveExpr(c, expr); }

/* Строки конструктора так, как их видит человек: из состояния PW и из полей
   окна. Читаем оба — состояние может расходиться с показанным. */
function ipPwSnap() {
  var dom = [];
  document.querySelectorAll('#pw-rows .pw-row').forEach(function (r) {
    var ins = r.querySelectorAll('input, math-field');
    var vals = [];
    ins.forEach(function (i) { vals.push(String(i.value == null ? '' : i.value)); });
    dom.push(vals);
  });
  var prev = document.getElementById('pw-preview');
  return {
    v: PW.v, n: PW.n,
    inp: PW.inp ? (PW.inp.id || '(без id)') : null,
    rows: JSON.parse(JSON.stringify(PW.rows)),
    dom: dom,
    formula: (typeof pwFormula === 'function') ? pwFormula() : '',
    preview: prev ? prev.textContent.replace(/\\s+/g, ' ').trim() : '',
  };
}
/* Поля, которые человек СЕЙЧАС видит в левой панели. Смотрим на строку, а не
   на само поле: там, где доехал MathLive, исходный input спрятан под ним, и
   проверка offsetParent у него всегда даёт «невидимо». Полю без id выдаём
   временный — прибору нужно за что-то держаться. */
var _ipTmp = 0;
function ipVisibleFields() {
  return [].slice.call(document.querySelectorAll('#tools-panel .f-row'))
    .filter(function (r) { return r.offsetParent; })
    .map(function (r) { return r.querySelector('input'); })
    .filter(Boolean)
    .map(function (i) { if (!i.id) i.id = 'ip-tmp-' + (++_ipTmp); return i.id; });
}
// Открыть конструктор ровно тем путём, каким его открывает человек:
// кнопка клавиатуры в строке поля -> «Кусочная функция» в подвале клавиатуры.
function ipOpenPw(inpId) {
  var inp = document.getElementById(inpId);
  if (!inp) return 'нет поля ' + inpId;
  var row = inp.closest('.f-row');
  var btn = row && row.querySelector('.f-help');
  if (!btn) return 'нет кнопки клавиатуры у ' + inpId;
  btn.click();
  var wrap = inp.closest('.f-wrap');
  var kbd = wrap && wrap.parentElement ? wrap.parentElement.querySelector('.mkbd.open') : null;
  if (!kbd) kbd = document.querySelector('.mkbd.open');
  var foot = kbd && kbd.querySelector('.mkbd-foot button');
  if (!foot) return 'нет входа в конструктор у ' + inpId;
  foot.click();
  return null;
}
function ipClosePw() { if (typeof closePiecewise === 'function') closePiecewise(); }
// «Поставить в поле» — та же кнопка, что нажимает человек.
function ipApplyPw() { var b = document.getElementById('pw-apply'); if (b) b.click(); }

/* Вопросики левой панели: сколько их всего видно и сколько висит без текста
   слева. «Без текста слева» — вопросик, у чьего якоря нет собственного текста
   кроме самого знака. */
function ipDots() {
  var panel = document.getElementById('tools-panel');
  if (!panel) return null;
  var anchors = panel.querySelectorAll('.help-anchor');
  var vis = function (el) { return !!(el.offsetParent || el.getClientRects().length); };
  var dots = [].slice.call(panel.querySelectorAll('.help-dot')).filter(vis);
  var lonely = dots.filter(function (d) {
    var host = d.parentElement;
    if (!host) return true;
    var txt = host.textContent.replace(/[?\\s]/g, '');
    return txt.length === 0;
  });
  var hints = [].slice.call(panel.querySelectorAll('.hint')).filter(function (h) {
    return h.style.display !== 'none' && fieldActive(h.parentElement || h);
  });
  return {
    anchors: anchors.length,
    anchorsVisible: [].slice.call(anchors).filter(vis).length,
    dots: dots.length,
    lonely: lonely.length,
    lonelyWhere: lonely.slice(0, 6).map(function (d) {
      var p = d.parentElement;
      return (p ? (p.className || p.tagName) : '?');
    }),
    hintsLive: hints.length,
    // Подсказка, оставшаяся обычным абзацем: якоря ей не нашлось, и это законно.
    hintsShown: hints.filter(function (h) { return !h.classList.contains('hint-hidden'); }).length,
  };
}
`;
await page.addScriptTag({ content: HELP });

const run = (code) => page.evaluate(`(function(){ ${code} })()`);

/* ── НАБОР К. Кадр и ядро ───────────────────────────────────────────── */
if (need('К') || need('K')) {
  console.log('\n=== НАБОР К(а): монополия D 100-Q, MC 20 ===');
  const a = await run(`
    resetSceneMemory(); pickScene('mono');
    var prep = function () {
      ipSet('demand', '100 - Q');
      var mc = ipCurve('mc'); if (mc) updateCurveExpr(mc, '20');
    };
    return ipScales(prep, function () {
      var m = STATE.mono;
      return { Qm: m ? m.Qm : null, Pm: m ? m.Pm : null, Qc: m ? m.Qc : null, dwl: m ? m.dwl : null };
    });
  `);
  a.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Qm=${num(s.Qm)}  Pm=${num(s.Pm)}  Qc=${num(s.Qc)}  DWL=${num(s.dwl)}`));
  same3('Qm на трёх масштабах', a.map(s => s.Qm), 1e-9);
  same3('Pm на трёх масштабах', a.map(s => s.Pm), 1e-9);
  same3('Qc на трёх масштабах', a.map(s => s.Qc), 1e-9);
  show('Qm на СУЖЕННОМ окне', a[1].Qm, 40, 0.05);
  show('Pm на СУЖЕННОМ окне', a[1].Pm, 60, 0.05);
  show('Qc на СУЖЕННОМ окне', a[1].Qc, 80, 0.05);

  console.log('\n=== НАБОР К(б): D 100-Q, S Q^2/100 (нелинейная) ===');
  const b = await run(`
    resetSceneMemory(); pickScene('sd');
    var prep = function () { ipSet('demand', '100 - Q'); ipSet('supply', 'Q^2/100'); };
    return ipScales(prep, function () {
      var s = ipCurve('supply');
      return { Q: STATE.eq ? STATE.eq.Q : null, P: STATE.eq ? STATE.eq.P : null,
               cs: STATE.cs, ps: STATE.ps,
               sLinear: s && s.linear ? (s.linear.a + '/' + s.linear.b) : 'нет (кривая)' };
    });
  `);
  b.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Q*=${num(s.Q)}  P*=${num(s.P)}  CS=${num(s.cs)}  PS=${num(s.ps)}  быстрый путь S: ${s.sLinear}`));
  same3('Q* на трёх масштабах', b.map(s => s.Q), 1e-9);
  same3('P* на трёх масштабах', b.map(s => s.P), 1e-9);
  same3('CS на трёх масштабах', b.map(s => s.cs), 1e-6);
  show('Q* эталон', b[0].Q, 61.803399, 0.001);
  flag('S нигде не запомнена прямой', b.every(s => s.sLinear === 'нет (кривая)'), b.map(s => s.sLinear).join(' | '));

  console.log('\n=== НАБОР К(б2): S кусочная с изломом за краем суженного окна ===');
  /* Излом лежит на Q = 40. На окне до 30 пробная сетка определителя линейности
     видит только первый кусок, запоминает прямую P = Q, и дальше evalCurve
     идёт быстрым путём по НЕВЕРНЫМ коэффициентам на всём остальном отрезке. */
  const b2 = await run(`
    resetSceneMemory(); pickScene('sd');
    var prep = function () { ipSet('demand', '100 - Q'); ipSet('supply', '(Q < 40) ? Q : 2*Q - 40'); };
    return ipScales(prep, function () {
      var s = ipCurve('supply');
      return { Q: STATE.eq ? STATE.eq.Q : null, P: STATE.eq ? STATE.eq.P : null,
               s60: evalCurve(s, 60),
               sLinear: s && s.linear ? (r6(s.linear.a) + '·Q + ' + r6(s.linear.b)) : 'нет (кривая)' };
      function r6(x) { return Math.round(x * 1e6) / 1e6; }
    });
  `);
  b2.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Q*=${num(s.Q)}  P*=${num(s.P)}  S(60)=${num(s.s60)}  быстрый путь S: ${s.sLinear}`));
  same3('Q* на трёх масштабах', b2.map(s => s.Q), 1e-9);
  same3('S(60) на трёх масштабах', b2.map(s => s.s60), 1e-9);
  show('Q* эталон (излом учтён)', b2[0].Q, 46.666667, 0.001);
  flag('S нигде не запомнена прямой', b2.every(s => s.sLinear === 'нет (кривая)'), b2.map(s => s.sLinear).join(' | '));

  console.log('\n=== НАБОР К(в): спрос в форме Q(P) 100-P, предложение P ===');
  const c = await run(`
    resetSceneMemory(); pickScene('sd');
    var prep = function () { ipSet('demand', '100 - P'); ipSet('supply', 'P'); };
    return ipScales(prep, function () {
      var d = ipCurve('demand');
      return { Q: STATE.eq ? STATE.eq.Q : null, P: STATE.eq ? STATE.eq.P : null,
               form: d ? d.srcForm : '?',
               dLin: d && d.srcLinear ? (num2(d.srcLinear.c) + '/' + num2(d.srcLinear.d)) : 'нет' };
      function num2(x) { return Math.round(x * 1e6) / 1e6; }
    });
  `);
  c.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Q*=${num(s.Q)}  P*=${num(s.P)}  форма D: ${s.form}  c/d: ${s.dLin}`));
  same3('Q* на трёх масштабах', c.map(s => s.Q), 1e-9);
  same3('P* на трёх масштабах', c.map(s => s.P), 1e-9);
  show('Q* эталон', c[0].Q, 50, 0.001);

  console.log('\n=== НАБОР К(в2): D задан Q(P) с изломом на P = 60 ===');
  /* Пробные цены определителя линейности по Q(P) — 0,2/0,5/0,8 от Pmax.
     На окне до 30 все три пробы лежат ниже излома, и кривая запоминается
     прямой Q = 100 − P на всём отрезке цен. */
  const c2 = await run(`
    resetSceneMemory(); pickScene('sd');
    var prep = function () { ipSet('demand', '(P < 60) ? 100 - P : 80 - 1.5*P'); ipSet('supply', 'Q'); };
    return ipScales(prep, function () {
      var d = ipCurve('demand');
      return { Q: STATE.eq ? STATE.eq.Q : null, P: STATE.eq ? STATE.eq.P : null,
               form: d ? d.srcForm : '?',
               dLin: d && d.srcLinear ? (r6(d.srcLinear.c) + ' + ' + r6(d.srcLinear.d) + '·P') : 'нет (кривая)' };
      function r6(x) { return Math.round(x * 1e6) / 1e6; }
    });
  `);
  c2.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Q*=${num(s.Q)}  P*=${num(s.P)}  форма ${s.form}  быстрый путь D: ${s.dLin}`));
  same3('Q* на трёх масштабах', c2.map(s => s.Q), 1e-9);
  flag('D нигде не запомнена прямой', c2.every(s => s.dLin === 'нет (кривая)'), c2.map(s => s.dLin).join(' | '));

  console.log('\n=== НАБОР К(в3): нелинейное предложение Q(P) = 0,01·P², спрос 300-Q ===');
  /* Обращение Q(P) сканирует цены до Pmax·3. Равновесная цена здесь 130,28 —
     на суженном окне (Pmax 30) верх сетки 90, и цены просто нет. */
  const c3 = await run(`
    resetSceneMemory(); pickScene('sd');
    var prep = function () { ipSet('demand', '300 - Q'); ipSet('supply', '0.01*P^2'); };
    return ipScales(prep, function () {
      var s = ipCurve('supply');
      return { Q: STATE.eq ? STATE.eq.Q : null, P: STATE.eq ? STATE.eq.P : null,
               s170: evalCurve(s, 170) };
    });
  `);
  c3.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Q*=${num(s.Q)}  P*=${num(s.P)}  S(170)=${num(s.s170)}`));
  same3('Q* на трёх масштабах', c3.map(s => s.Q), 1e-9);
  same3('S(170) на трёх масштабах', c3.map(s => s.s170), 1e-9);
  show('Q* эталон', c3[0].Q, 169.722436, 0.001);

  console.log('\n=== НАБОР К(г): эластичность D 100-Q в точке Q = 50 ===');
  const g = await run(`
    resetSceneMemory(); pickScene('elast');
    var prep = function () { ipSet('demand', '100 - Q'); STATE.elastQ = 50; };
    return ipScales(prep, function () {
      var e = STATE.elast;
      return { Ed: e ? e.Ed : null, slope: e ? e.slope : null, q: e ? e.q : null, p: e ? e.p : null,
               unitQ: e && e.unit ? e.unit.Q : null };
    });
  `);
  g.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Ed=${num(s.Ed)}  наклон=${num(s.slope)}  Q=${num(s.q)}  P=${num(s.p)}  единичная Q=${num(s.unitQ)}`));
  same3('Ed на трёх масштабах', g.map(s => s.Ed), 1e-9);
  same3('наклон на трёх масштабах', g.map(s => s.slope), 1e-9);
  same3('единичная точка на трёх масштабах', g.map(s => s.unitQ), 1e-9);
  show('Ed эталон', g[0].Ed, -1, 1e-6);

  console.log('\n=== НАБОР К(г2): шаг численной производной ===');
  /* Шаг центральной разности берётся от CONFIG.Qmax. На кривой с заметной
     кривизной это прямо меняет ответ: одна и та же точка на разных масштабах
     даёт разный наклон. Меряем ядро напрямую, без сцены. */
  const g2 = await run(`
    var mk = function (e) { var c = compileFormula(e); return { expr: e, compiled: c.compiled, linear: null, fn: null }; };
    var out = [];
    [100, 30, 400].forEach(function (qm) {
      var was = CONFIG.Qmax; CONFIG.Qmax = qm;
      var c = mk('100 - 40*sin(Q)');
      out.push({ qmax: CONFIG.Qmax, h: Math.max(1e-5, Math.abs(3) * 2e-5), d: curveDeriv(c, 3) });
      CONFIG.Qmax = was;
    });
    return out;
  `);
  g2.forEach(s => console.log(`     Qmax ${num(s.qmax)}: шаг h = ${num(s.h)}, производная в Q=3 = ${s.d}`));
  same3('производная на трёх масштабах', g2.map(s => s.d), 1e-9);
  show('производная эталон (−40·cos 3)', g2[0].d, 39.599699, 1e-5);

  console.log('\n=== НАБОР К(д): внешние эффекты MSC = Q+20 при D 100-Q, S Q ===');
  const d = await run(`
    resetSceneMemory(); pickScene('ext');
    var prep = function () {
      ipSet('demand', '100 - Q'); ipSet('supply', 'Q');
      STATE.mscOn = true; STATE.mscExpr = 'Q + 20'; STATE.msbOn = false;
      recompileSocial();
    };
    return ipScales(prep, function () {
      var e = STATE.ext;
      return { Qopt: e ? e.Qopt : null, Popt: e ? e.Popt : null, dwl: e ? e.dwl : null,
               pigou: e ? e.corrective : null };
    });
  `);
  d.forEach(s => console.log(`     окно Q 0…${num(s.win.qmax)}: Qопт=${num(s.Qopt)}  Pопт=${num(s.Popt)}  DWL=${num(s.dwl)}  Пигу=${num(s.pigou)}`));
  same3('Qопт на трёх масштабах', d.map(s => s.Qopt), 1e-9);
  same3('DWL на трёх масштабах', d.map(s => s.dwl), 1e-6);
  show('Qопт на СУЖЕННОМ окне', d[1].Qopt, 40, 0.05);
  show('DWL на СУЖЕННОМ окне', d[1].dwl, 100, 0.5);
}

/* ── НАБОР П. Утечка строк конструктора ─────────────────────────────── */
if (need('П') || need('P')) {
  console.log('\n=== НАБОР П(а): конструктор в «Математике» ===');
  const pa = await run(`
    resetSceneMemory(); pickScene('m-graph');
    if (typeof addCurve === 'function' && !STATE.curves.length) addCurve();
    return null;
  `);
  await page.waitForTimeout(400);
  const paIds = await run(`return ipVisibleFields();`);
  console.log('     видимые поля «Математики»: ' + JSON.stringify(paIds));
  const mathField = paIds[0];
  const pa2 = await run(`
    var err = ipOpenPw(${JSON.stringify(mathField)});
    if (err) return { err: err };
    return ipPwSnap();
  `);
  await page.waitForTimeout(200);
  if (pa2.err) { bad++; console.log('FAIL ' + pa2.err); }
  else {
    console.log(`     поле ${pa2.inp}, переменная PW.v = «${pa2.v}», кусков ${pa2.n}`);
    pa2.rows.forEach((r, i) => console.log(`       кусок ${i + 1}: f = «${r.f}»  от «${r.a}»  до «${r.b}»`));
  }
  await run(`ipClosePw();`);

  console.log('\n=== НАБОР П(б): ушли в «Спрос и предложение», открыли конструктор у спроса ===');
  const pb = await run(`
    resetSceneMemory(); pickScene('sd');
    return null;
  `);
  await page.waitForTimeout(500);
  const pb2 = await run(`
    var err = ipOpenPw('curve-expr-1');
    if (err) return { err: err };
    return ipPwSnap();
  `);
  if (pb2.err) { bad++; console.log('FAIL ' + pb2.err); }
  else {
    console.log(`     поле ${pb2.inp}, переменная PW.v = «${pb2.v}», кусков ${pb2.n}`);
    pb2.rows.forEach((r, i) => console.log(`       кусок ${i + 1}: f = «${r.f}»  от «${r.a}»  до «${r.b}»`));
    const all = pb2.rows.map(r => `${r.f} ${r.a} ${r.b}`).join(' ');
    flag('в кусках нет буквы x/X из «Математики»', !/(^|[^A-Za-z0-9_])[xX]([^A-Za-z0-9_]|$)/.test(all), all);
    flag('куски написаны буквой Q', /(^|[^A-Za-z0-9_])Q([^A-Za-z0-9_]|$)/.test(all), all);
  }
  await run(`ipClosePw();`);

  console.log('\n=== НАБОР П(в): спрос и предложение в ОДНОЙ сцене ===');
  const pv = await run(`
    var e1 = ipOpenPw('curve-expr-1'); if (e1) return { err: e1 };
    PW.rows[0].f = 'МЕТКА-СПРОСА';
    var s1 = ipPwSnap();
    ipClosePw();
    var e2 = ipOpenPw('curve-expr-2'); if (e2) return { err: e2 };
    var s2 = ipPwSnap();
    ipClosePw();
    return { d: s1, s: s2 };
  `);
  if (pv.err) { bad++; console.log('FAIL ' + pv.err); }
  else {
    console.log(`     спрос:       кусок 1 f = «${pv.d.rows[0].f}»`);
    console.log(`     предложение: кусок 1 f = «${pv.s.rows[0].f}»`);
    flag('метка спроса НЕ видна в предложении', pv.s.rows[0].f !== 'МЕТКА-СПРОСА', pv.s.rows[0].f);
  }

  console.log('\n=== НАБОР П(г): обратный ход — снова «Математика» ===');
  await run(`resetSceneMemory(); pickScene('m-graph'); if (typeof addCurve === 'function' && !STATE.curves.length) addCurve();`);
  await page.waitForTimeout(400);
  const pg = await run(`
    var ids = ipVisibleFields();
    var err = ipOpenPw(ids[0]); if (err) return { err: err };
    var s = ipPwSnap(); ipClosePw(); return s;
  `);
  if (pg.err) { bad++; console.log('FAIL ' + pg.err); }
  else {
    console.log(`     поле ${pg.inp}, переменная PW.v = «${pg.v}»`);
    pg.rows.forEach((r, i) => console.log(`       кусок ${i + 1}: f = «${r.f}»  от «${r.a}»  до «${r.b}»`));
    const all = pg.rows.map(r => `${r.f} ${r.a} ${r.b}`).join(' ');
    flag('куски написаны буквой x', /(^|[^A-Za-z0-9_])x([^A-Za-z0-9_]|$)/.test(all), all);
    flag('буквы Q в кусках нет', !/(^|[^A-Za-z0-9_])Q([^A-Za-z0-9_]|$)/.test(all), all);
  }

  console.log('\n=== НАБОР П(д): уже стоящая в поле кусочная разбирается обратно ===');
  const pd = await run(`
    resetSceneMemory(); pickScene('sd');
    return null;
  `);
  await page.waitForTimeout(500);
  const pd2 = await run(`
    var e1 = ipOpenPw('curve-expr-1'); if (e1) return { err: e1 };
    PW.n = 2;
    PW.rows = [{ f: '90 - Q', a: '0', b: '30' }, { f: '60 - 0.5*Q', a: '30', b: '' }];
    renderPw();
    ipApplyPw();
    var after = document.getElementById('curve-expr-1').value;
    /* ⚠️ МЕЖДУ ЗАПИСЬЮ И ПРОВЕРКОЙ ОБЯЗАТЕЛЬНО ЗАХОДИМ В ЧУЖОЕ ПОЛЕ.
       Без этого набор проходил бы и на утечке: строки просто оставались бы
       в PW с прошлого открытия, и «разбор обратно» ничего бы не доказывал. */
    var e0 = ipOpenPw('curve-expr-2'); if (e0) return { err: e0, field: after };
    var mid = ipPwSnap(); ipClosePw();
    var e2 = ipOpenPw('curve-expr-1'); if (e2) return { err: e2, field: after };
    var s = ipPwSnap(); ipClosePw();
    return { field: after, snap: s, mid: mid };
  `);
  if (pd2.err) { bad++; console.log('FAIL ' + pd2.err + ' (поле: ' + pd2.field + ')'); }
  else {
    console.log('     в поле после «Поставить в поле»: ' + pd2.field);
    console.log(`     по дороге зашли в предложение: кусок 1 «${pd2.mid.rows[0].f}» (обязано быть по умолчанию)`);
    flag('чужое поле показало значения по умолчанию, а не чужие куски',
      pd2.mid.rows[0].f === '100 - Q', pd2.mid.rows[0].f);
    pd2.snap.rows.forEach((r, i) => console.log(`       кусок ${i + 1}: f = «${r.f}»  от «${r.a}»  до «${r.b}»`));
    flag('первый кусок разобран обратно', /90/.test(pd2.snap.rows[0].f || ''), pd2.snap.rows[0].f);
    flag('второй кусок разобран обратно', /60/.test((pd2.snap.rows[1] || {}).f || ''), (pd2.snap.rows[1] || {}).f);
  }

  console.log('\n=== НАБОР П(е): в поле обычная формула — значения по умолчанию ===');
  const pe = await run(`
    resetSceneMemory(); pickScene('sd');
    return null;
  `);
  await page.waitForTimeout(500);
  const pe2 = await run(`
    var d = ipCurve('demand'); if (d) updateCurveExpr(d, '100 - 2*Q');
    document.getElementById('curve-expr-1').value = '100 - 2*Q';
    var e = ipOpenPw('curve-expr-1'); if (e) return { err: e };
    var s = ipPwSnap(); ipClosePw(); return s;
  `);
  if (pe2.err) { bad++; console.log('FAIL ' + pe2.err); }
  else {
    pe2.rows.forEach((r, i) => console.log(`       кусок ${i + 1}: f = «${r.f}»  от «${r.a}»  до «${r.b}»`));
    flag('обычная формула не разбирается в куски — стоят значения по умолчанию',
      pe2.rows.length === 2 && pe2.rows[0].f === '100 - Q', JSON.stringify(pe2.rows));
  }
}

/* ── НАБОР Ш. Ширина поля под кусочной ──────────────────────────────── */
if (need('Ш') || need('SH')) {
  console.log('\n=== НАБОР Ш: кусочная в поле ===');
  for (const n of [2, 3]) {
    await run(`resetSceneMemory(); pickScene('sd');`);
    await page.waitForTimeout(500);
    const rows = n === 2
      ? `[{ f: '100 - Q', a: '0', b: '40' }, { f: '80 - 0.5*Q', a: '40', b: '' }]`
      : `[{ f: '100 - Q', a: '0', b: '30' }, { f: '85 - 0.5*Q', a: '30', b: '60' }, { f: '70 - 0.25*Q', a: '60', b: '' }]`;
    const w = await run(`
      var base = (function () {
        var i = document.getElementById('curve-expr-1');
        var host = i._mf || i;
        var r = host.getBoundingClientRect();
        return { h: r.height };
      })();
      var e = ipOpenPw('curve-expr-1'); if (e) return { err: e };
      PW.n = ${n}; PW.rows = ${rows}; renderPw(); ipApplyPw();
      return { base: base };
    `);
    if (w.err) { bad++; console.log('FAIL ' + w.err); continue; }
    await page.waitForTimeout(700);
    const m = await run(`
      var i = document.getElementById('curve-expr-1');
      var host = i._mf || i;
      var r = host.getBoundingClientRect();
      /* ⚠️ ЛИНЕЙКУ ПРИКЛАДЫВАЕМ ВНУТРИ MathLive, А НЕ СНАРУЖИ. Снаружи поле
         всегда «в порядке»: обрезка живёт на .ML__content в теневом дереве
         (overflow-x: hidden), и scrollWidth самого math-field равен clientWidth
         даже тогда, когда запись обрезана посреди слова. */
      var sr = host.shadowRoot || host;
      var content = sr.querySelector ? sr.querySelector('.ML__content') : null;
      var inner = sr.querySelector ? sr.querySelector('.ML__latex') : null;
      var ir = inner ? inner.getBoundingClientRect() : null;
      var slot = i.closest('.f-slot'), row = i.closest('.f-row');
      return {
        fieldW: r.width, fieldH: r.height,
        contentW: ir ? ir.width : null, contentR: ir ? ir.right : null, fieldR: r.right,
        scrollW: content ? content.scrollWidth : host.scrollWidth,
        clientW: content ? content.clientWidth : host.clientWidth,
        fontSize: content ? getComputedStyle(content).fontSize : getComputedStyle(host).fontSize,
        slotW: slot ? slot.getBoundingClientRect().width : null,
        slotOverflow: slot ? getComputedStyle(slot).overflowX : null,
        rowH: row ? row.getBoundingClientRect().height : null,
        innerTag: inner ? inner.className : '(не нашли)',
        contentBoxR: content ? content.getBoundingClientRect().right : null,
        narrow: (typeof isNarrowCases === 'function') ? isNarrowCases(host.value || '') : null,
        mf: !!i._mf, value: i.value,
      };
    `);
    console.log(`   ${n} куска:`);
    console.log(`     поле ${num(m.fieldW)}×${num(m.fieldH)} px, было по высоте ${num(w.base.h)} px`);
    console.log(`     содержимое ${num(m.contentW)} px, правый край содержимого ${num(m.contentR)} против края видимой области ${num(m.contentBoxR)}`);
    console.log(`     scrollWidth ${num(m.scrollW)} / clientWidth ${num(m.clientW)}  (MathLive: ${m.mf}, кегль ${m.fontSize}, узкий вид ${m.narrow})`);
    console.log(`     слот ${num(m.slotW)} px, overflow-x «${m.slotOverflow}», высота строки ${num(m.rowH)} px`);
    flag(`${n} куска: горизонтальной прокрутки нет`, m.scrollW <= m.clientW + 1, `${m.scrollW} > ${m.clientW}`);
    flag(`${n} куска: содержимое не вылезает вправо`,
      m.contentR == null || m.contentBoxR == null || m.contentR <= m.contentBoxR + 1,
      num(m.contentR) + ' > ' + num(m.contentBoxR));
    flag(`${n} куска: поле выросло в высоту`, m.fieldH > w.base.h + 4, `${num(m.fieldH)} vs ${num(w.base.h)}`);
    /* ⚠️ НА ОБЫЧНОЙ ШИРИНЕ ЗАПИСЬ ОСТАЁТСЯ ЧИТАЕМОЙ — ПО СТРОКЕ НА КУСОК.
       Узкий вид (условие отдельной строкой) заведён для панели в двести
       пикселей, и на полной ширине он был бы шагом назад. Без этой проверки
       случай не краснеет, когда отнимают ширину строки или подбор кегля:
       узкий вид спасает запись от обрезки и прячет обе поломки. */
    flag(`${n} куска: запись в обычном виде, не в узком`, m.narrow === false, String(m.narrow));
    // Каретка стрелками от начала записи до конца и обратно.
    const walk = await run(`
      var i = document.getElementById('curve-expr-1');
      var mf = i._mf;
      if (!mf) return { skip: 'MathLive не доехал' };
      mf.focus();
      mf.executeCommand('moveToMathfieldStart');
      var seen = [], back = [];
      for (var k = 0; k < 60; k++) { seen.push(String(mf.position)); mf.executeCommand('moveToNextChar'); }
      for (var k2 = 0; k2 < 60; k2++) { back.push(String(mf.position)); mf.executeCommand('moveToPreviousChar'); }
      return { fwd: seen, back: back, end: String(mf.position) };
    `);
    if (walk.skip) console.log('     каретка: ' + walk.skip);
    else {
      // Прыжок в начало посреди хода вперёд — это и есть «перекидывает в начало».
      const nums = walk.fwd.map(Number);
      let jumps = 0;
      for (let k = 1; k < nums.length; k++) if (nums[k] < nums[k - 1] - 1) jumps++;
      console.log(`     каретка вперёд: ${walk.fwd.slice(0, 12).join(' ')} … максимум ${Math.max(...nums)}`);
      flag(`${n} куска: каретка не перепрыгивает в начало`, jumps === 0, `прыжков назад: ${jumps}`);
    }
  }

  // Соседние строки кривых на месте, карточка «Ввод функций» не разъехалась.
  const neigh = await run(`
    var s = document.getElementById('curve-expr-2');
    var srow = s ? s.closest('.f-row') : null;
    var card = document.getElementById('sec-curves') || (srow && srow.closest('.section'));
    var cr = card ? card.getBoundingClientRect() : null;
    var panel = document.getElementById('tools-panel').getBoundingClientRect();
    return {
      supplyVisible: !!(srow && srow.offsetParent),
      supplyH: srow ? srow.getBoundingClientRect().height : null,
      supplyValue: s ? s.value : null,
      cardR: cr ? cr.right : null, panelR: panel.right, panelW: panel.width,
    };
  `);
  console.log(`     соседняя строка предложения: видна ${neigh.supplyVisible}, высота ${num(neigh.supplyH)} px, «${neigh.supplyValue}»`);
  console.log(`     карточка «Ввод функций» правым краем ${num(neigh.cardR)} против края панели ${num(neigh.panelR)}`);
  flag('строка предложения на месте и однострочная', neigh.supplyVisible && neigh.supplyH < 60, String(neigh.supplyH));
  flag('карточка не вылезла за панель', neigh.cardR <= neigh.panelR + 1, `${num(neigh.cardR)} > ${num(neigh.panelR)}`);

  // Узкое окно 380 px: то же самое, панель не ломается.
  console.log('   ширина окна 380 px:');
  await page.setViewportSize({ width: 380, height: 950 });
  await run(`resetSceneMemory(); pickScene('sd');`);
  await page.waitForTimeout(700);
  const narrow = await run(`
    var e = ipOpenPw('curve-expr-1'); if (e) return { err: e };
    PW.n = 2; PW.rows = [{ f: '100 - Q', a: '0', b: '40' }, { f: '80 - 0.5*Q', a: '40', b: '' }];
    renderPw(); ipApplyPw();
    return {};
  `);
  await page.waitForTimeout(900);
  if (narrow.err) { bad++; console.log('FAIL ' + narrow.err); }
  else {
    const m380 = await run(`
      var i = document.getElementById('curve-expr-1');
      var host = i._mf || i;
      var sr = host.shadowRoot || host;
      var content = sr.querySelector ? sr.querySelector('.ML__content') : null;
      var panel = document.getElementById('tools-panel').getBoundingClientRect();
      var row = i.closest('.f-row').getBoundingClientRect();
      return {
        h: host.getBoundingClientRect().height,
        scrollW: content ? content.scrollWidth : null, clientW: content ? content.clientWidth : null,
        fontSize: content ? getComputedStyle(content).fontSize : null,
        rowR: row.right, panelR: panel.right, panelW: panel.width,
      };
    `);
    console.log(`     панель ${num(m380.panelW)} px; поле высотой ${num(m380.h)}, кегль ${m380.fontSize}, ` +
      `scroll ${num(m380.scrollW)}/${num(m380.clientW)}; строка правым краем ${num(m380.rowR)} против панели ${num(m380.panelR)}`);
    flag('380 px: горизонтальной прокрутки нет', m380.scrollW <= m380.clientW + 1, `${m380.scrollW} > ${m380.clientW}`);
    flag('380 px: строка не вылезла за панель', m380.rowR <= m380.panelR + 1, `${num(m380.rowR)} > ${num(m380.panelR)}`);
    flag('380 px: кегль не ниже предела 11 px', parseFloat(m380.fontSize) >= 10.99, m380.fontSize);
    /* Узкая запись обязана разбираться обратно в ту же цепочку условий:
       иначе правка формулы прямо в поле молча испортила бы кривую. */
    const rt = await run(`
      var i = document.getElementById('curve-expr-1');
      var mf = i._mf;
      var back = latexToMath(mf.value);
      var c = STATE.curves.find(function (x) { return x.role === 'demand'; });
      return { narrow: isNarrowCases(mf.value), tex: mf.value, field: i.value, back: back,
               same: back.replace(/\\s/g, '') === String(i.value || '').replace(/\\s/g, ''),
               at20: evalCurve(c, 20), at60: evalCurve(c, 60) };
    `);
    console.log(`     узкий вид: ${rt.narrow}; разбор обратно: ${rt.back}`);
    flag('380 px: запись перешла в узкий вид', rt.narrow === true, String(rt.narrow));
    flag('380 px: узкая запись разбирается в ту же цепочку', rt.same, rt.back + '  vs  ' + rt.field);
    show('380 px: D(20) после узкой записи', rt.at20, 80, 0.001);
    show('380 px: D(60) после узкой записи', rt.at60, 50, 0.001);
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.waitForTimeout(300);
}

/* ── НАБОР В. Одинокие вопросики ────────────────────────────────────── */
if (need('В') || need('V')) {
  console.log('\n=== НАБОР В: вопросики в левой панели ===');
  for (const sc of ['sd', 'mono', 'ext', 'sdsum', 'elast', 'taxes', 'ceil', 'ppf']) {
    await run(`resetSceneMemory(); pickScene(${JSON.stringify(sc)});`);
    await page.waitForTimeout(600);
    const v = await run(`return ipDots();`);
    console.log(`     ${sc}: .help-anchor всего ${v.anchors} (видимых ${v.anchorsVisible}), видимых «?» ${v.dots}, ` +
      `из них без текста слева ${v.lonely}, живых подсказок ${v.hintsLive} (абзацем ${v.hintsShown})`);
    if (v.lonely) console.log(`       где: ${JSON.stringify(v.lonelyWhere)}`);
    flag(sc + ': одиноких «?» нет', v.lonely === 0, String(v.lonely));
    /* ⚠️ ВОПРОСИКОВ НЕ БОЛЬШЕ, ЧЕМ ЖИВЫХ ПОДСКАЗОК, А НЕ «РОВНО СТОЛЬКО».
       У одного заголовка намеренно собираются несколько подсказок под ОДИН
       знак (у внешнего эффекта свой текст на каждый знак) — это старое и
       осознанное поведение, ему тут не место ломаться. Дефект был обратный:
       вопросиков БОЛЬШЕ, чем подсказок, вплоть до трёх при нуле живых. */
    flag(sc + ': видимых «?» не больше живых подсказок', v.dots <= v.hintsLive, `${v.dots} > ${v.hintsLive}`);
    flag(sc + ': каждая живая подсказка либо под знаком, либо видна абзацем',
      v.hintsLive === 0 || v.dots > 0 || v.hintsShown > 0, `подсказок ${v.hintsLive}, знаков ${v.dots}, абзацем ${v.hintsShown}`);
  }
}

/* ── НАБОР Ф. Подсветка первой карточки ─────────────────────────────── */
if (need('Ф') || need('F')) {
  console.log('\n=== НАБОР Ф: подсветка карточек на первом экране ===');
  const fresh = await ctx.newPage();
  await fresh.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
  await fresh.waitForTimeout(1200);
  const cards = await fresh.$$('#picker-blocks .bcard');
  const read = async (i) => {
    await cards[i].hover();
    await fresh.waitForTimeout(250);
    return fresh.evaluate((n) => {
      const c = document.querySelectorAll('#picker-blocks .bcard')[n];
      const cs = getComputedStyle(c);
      return { border: cs.borderColor, outline: cs.outlineStyle + ' ' + cs.outlineWidth,
               ring: c.classList.contains('no-init-ring'), name: (c.textContent || '').trim().slice(0, 30) };
    }, i);
  };
  const c0 = await read(0), c1 = await read(1);
  console.log(`     карточка 1 («${c0.name}») при наведении: border ${c0.border}, кольцо «${c0.outline}», no-init-ring=${c0.ring}`);
  console.log(`     карточка 2 («${c1.name}») при наведении: border ${c1.border}, кольцо «${c1.outline}»`);
  flag('border первой карточки при наведении совпадает со второй', c0.border === c1.border,
    `${c0.border} != ${c1.border}`);
  // ⚠️ ПОСЛЕ НАВЕДЕНИЯ КОЛЬЦА БЫТЬ НЕ ДОЛЖНО: мышь не клавиатура.
  flag('после наведения мышью кольца на первой карточке нет', c0.outline.indexOf('none') === 0, c0.outline);
  // А после Tab — обязано появиться.
  await fresh.keyboard.press('Tab');
  await fresh.waitForTimeout(250);
  const afterTab = await fresh.evaluate(() => {
    const a = document.activeElement;
    const cs = a ? getComputedStyle(a) : null;
    return { tag: a ? (a.className || a.tagName) : '?', outline: cs ? cs.outlineStyle + ' ' + cs.outlineWidth : '?',
             ring: !!(a && a.classList && a.classList.contains('no-init-ring')) };
  });
  console.log(`     после Tab фокус на «${afterTab.tag}», кольцо «${afterTab.outline}», no-init-ring=${afterTab.ring}`);
  flag('после Tab кольцо есть', afterTab.outline.indexOf('solid') === 0, afterTab.outline);
  await fresh.close();

  /* ⚠️ ОБА КРАЯ ПРАВИЛА. Кольцо гасится ТОЛЬКО служебным фокусом, поэтому
     проверяем и второй край: посторонняя клавиша (Escape) кольцо не будит,
     а Tab будит. Иначе достаточно было бы снять класс где угодно. */
  const esc = await ctx.newPage();
  await esc.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
  await esc.waitForTimeout(1200);
  await esc.keyboard.press('Escape');
  await esc.waitForTimeout(250);
  const afterEsc = await esc.evaluate(() => {
    const c = document.querySelectorAll('#picker-blocks .bcard')[0];
    const cs = getComputedStyle(c);
    return { outline: cs.outlineStyle + ' ' + cs.outlineWidth, ring: c.classList.contains('no-init-ring') };
  });
  console.log(`     после Escape: кольцо «${afterEsc.outline}», no-init-ring=${afterEsc.ring}`);
  flag('посторонняя клавиша кольца не будит', afterEsc.outline.indexOf('none') === 0, afterEsc.outline);
  await esc.close();
}

/* ── НАБОР З. Ширина записи в правой панели ─────────────────────────── */
if (need('З') || need('Z')) {
  console.log('\n=== НАБОР З: аналитическая запись в правой панели ===');
  await run(`
    resetSceneMemory(); pickScene('sdsum');
    sumSetCount('D', 4); sumSetCount('S', 2);
    var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
    ['100 - Q', '80 - Q', '60 - Q', '40 - Q'].forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
    var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
    ['Q', 'Q + 20'].forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
    redrawAll();
    var b = document.getElementById('ex-btn'); if (b) b.click();
  `);
  await page.waitForTimeout(900);
  const z = await run(`
    var panel = document.getElementById('params-panel');
    var body = document.getElementById('ex-body');
    var pr = panel.getBoundingClientRect();
    var notes = [].slice.call(body.querySelectorAll('.sb-note')).map(function (n) {
      var kx = n.querySelector('.katex-html') || n.querySelector('.katex');
      var r = (kx || n).getBoundingClientRect();
      var nr = n.getBoundingClientRect();
      return { title: (n.querySelector('b') || {}).textContent || '',
               contentW: r.width, contentR: r.right,
               boxW: nr.width, boxR: nr.right,
               scrollW: n.scrollWidth, clientW: n.clientWidth,
               fontSize: kx ? getComputedStyle(kx).fontSize : getComputedStyle(n).fontSize };
    });
    return { panelW: pr.width, panelR: pr.right, bodyW: body.getBoundingClientRect().width, notes: notes };
  `);
  console.log(`     панель ${num(z.panelW)} px, тело «Объяснения модели» ${num(z.bodyW)} px`);
  z.notes.forEach(n => {
    console.log(`     врезка «${n.title.trim()}»: содержимое ${num(n.contentW)} px, правый край ${num(n.contentR)} ` +
      `против края врезки ${num(n.boxR)}; кегль ${n.fontSize}; scroll ${num(n.scrollW)}/${num(n.clientW)}`);
  });
  const over = z.notes.filter(n => n.contentR > n.boxR + 1);
  flag('ни одна врезка не вылезает за свой блок', over.length === 0,
    over.map(n => `${n.title.trim()}: ${num(n.contentR)} > ${num(n.boxR)}`).join('; '));
  const small = z.notes.filter(n => parseFloat(n.fontSize) < 9.99);
  flag('кегль не ниже выбранного предела 10 px', small.length === 0,
    small.map(n => `${n.title.trim()}: ${n.fontSize}`).join('; '));

  // Шесть групп: запись шире, предел кегля ближе — проверяем и этот край.
  console.log('   шесть групп спроса:');
  await run(`
    resetSceneMemory(); pickScene('sdsum');
    sumSetCount('D', 6); sumSetCount('S', 2);
    var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
    ['100 - Q', '90 - Q', '80 - Q', '70 - Q', '60 - Q', '50 - Q']
      .forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
    redrawAll();
    var b = document.getElementById('ex-btn');
    if (b && b.getAttribute('aria-expanded') !== 'true') b.click();
  `);
  await page.waitForTimeout(900);
  const z6 = await run(`
    var body = document.getElementById('ex-body');
    return [].slice.call(body.querySelectorAll('.sb-note')).map(function (n) {
      var kx = n.querySelector('.katex-html') || n.querySelector('.katex');
      var r = (kx || n).getBoundingClientRect(), nr = n.getBoundingClientRect();
      return { title: ((n.querySelector('b') || {}).textContent || '').trim(),
               contentR: r.right, boxR: nr.right, w: r.width,
               fontSize: kx ? getComputedStyle(kx).fontSize : getComputedStyle(n).fontSize };
    });
  `);
  z6.forEach(n => console.log(`     врезка «${n.title}»: содержимое ${num(n.w)} px, правый край ${num(n.contentR)} ` +
    `против края врезки ${num(n.boxR)}; кегль ${n.fontSize}`));
  flag('шесть групп: запись не вылезает за врезку', z6.every(n => n.contentR <= n.boxR + 1),
    z6.map(n => `${n.title}: ${num(n.contentR)} vs ${num(n.boxR)}`).join('; '));
  flag('шесть групп: кегль не ниже 10 px', z6.every(n => parseFloat(n.fontSize) >= 9.99),
    z6.map(n => n.fontSize).join('; '));
}

/* ── НАБОР Я. Якорь подписи: место годно только там, где кривая есть ──
   Сессия «процентные налоги» починила подпись КРИВОЙ: со снятой галочкой «D»
   висела в пустоте при Q ≈ 145, P ≈ −30. Здесь ищем тот же класс у подписей
   ТОЧЕК, у названий осей и у легенды: в экономической сцене всё, что
   привязано к модели, обязано лежать в первой четверти, куда бы ни заходило
   окно. Названия осей, деления и легенда за четверть выходят законно — они
   привязаны к КАДРУ, а не к кривой, поэтому считаются отдельно. */
if (need('Я') || need('YA')) {
  console.log('\n=== НАБОР Я: подписи не висят в пустоте ===');
  const SCENES = [
    ['sd', `ipSet('demand', '100 - Q'); ipSet('supply', 'Q');`],
    ['mono', `ipSet('demand', '100 - Q'); var mc = ipCurve('mc'); if (mc) updateCurveExpr(mc, '20');`],
    ['taxes', `ipSet('demand', '120 - Q'); ipSet('supply', 'Q'); setType('tax'); setTaxForm('unit'); setTax(40);`],
    ['elast', `ipSet('demand', '100 - Q');`],
    ['ext', `ipSet('demand', '100 - Q'); ipSet('supply', 'Q');
             STATE.mscOn = true; STATE.mscExpr = 'Q + 20'; recompileSocial();`],
  ];
  for (const [key, prep] of SCENES) {
    const r = await run(`
      resetSceneMemory(); pickScene(${JSON.stringify(key)});
      ${prep}
      setFirstQuad(false);            // окно уходит в минус, кривая — нет
      redrawAll();
      var svgEl = document.querySelector('#graph-wrap svg');
      if (!svgEl) return { err: 'нет холста' };
      var out = [];
      svgEl.querySelectorAll('text').forEach(function (t) {
        var cls = t.getAttribute('class') || '';
        var pr = t.parentElement ? (t.parentElement.getAttribute('class') || '') : '';
        var r = t.getBoundingClientRect();
        var host = svgEl.getBoundingClientRect();
        var q = sx.invert(r.left + r.width / 2 - host.left);
        var v = sy.invert(r.top + r.height / 2 - host.top);
        var clone = t.cloneNode(true);
        clone.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
        out.push({ cls: cls, parent: pr, txt: clone.textContent.trim().slice(0, 18),
                   q: Math.round(q * 100) / 100, v: Math.round(v * 100) / 100 });
      });
      return { win: { qmin: CONFIG.Qmin, qmax: CONFIG.Qmax, pmin: CONFIG.Pmin, pmax: CONFIG.Pmax }, labels: out };
    `);
    if (r.err) { bad++; console.log('FAIL ' + key + ': ' + r.err); continue; }
    /* Привязано к кадру, а не к модели: деления осей, названия осей, легенда и
       заголовок графика. Им за четвертью быть можно.
       ⚠️ И ОТДЕЛЬНО — ПОЛОСА ВДОЛЬ ОСЕЙ. Число ключевой точки (`coord-num`)
       печатается СНАРУЖИ своей оси: «50» под осью Q лежит при P ≈ −1,9, и это
       правильное место, а не пустота. «Висит в пустоте» — это далеко от осей:
       у подписи «D», ради которой правило и заводили, было Q ≈ 145, P ≈ −30
       при размахе окна 125. Полосу берём в 6 % размаха. */
    const bandQ = (r.win.qmax - r.win.qmin) * 0.06;
    const bandP = (r.win.pmax - r.win.pmin) * 0.06;
    const frameBound = (l) => /axis-num|axis-name|legend|chart-title|graph-title/.test(l.cls + ' ' + l.parent);
    const hang = r.labels.filter(l => !frameBound(l) && (l.q < -bandQ || l.v < -bandP
                                                        || l.q > r.win.qmax || l.v > r.win.pmax));
    console.log(`     ${key}: окно Q ${num(r.win.qmin)}…${num(r.win.qmax)}, P ${num(r.win.pmin)}…${num(r.win.pmax)}; ` +
      `подписей ${r.labels.length}, привязанных к модели ${r.labels.filter(l => !frameBound(l)).length}`);
    if (hang.length) {
      hang.slice(0, 8).forEach(l => console.log(`       ВНЕ ЧЕТВЕРТИ: «${l.txt}» (${l.cls || l.parent}) при Q=${l.q}, P=${l.v}`));
    }
    flag(`${key}: подписей модели вне первой четверти нет`, hang.length === 0, String(hang.length));
  }
}

/* ── СКОРОСТЬ. 60 шагов панорамы ────────────────────────────────────
   Фаза 1 расширяет области поиска, и за это можно заплатить кадром. Меряем
   там, где расширение точно работает: монополия (findRoot дважды на кадр)
   и «Сложение спросов» (самая тяжёлая сцена движка). */
if (need('СКОРОСТЬ') || need('S')) {
  console.log('\n=== СКОРОСТЬ: 60 шагов панорамы ===');
  const speed = async (label, setup) => {
    const sp = await run(`
      ${setup}
      for (var w = 0; w < 5; w++) panByPixels(-3, 0);   // прогрев: первый кадр всегда дороже
      var t0 = performance.now();
      for (var i = 0; i < 60; i++) panByPixels((i % 2 ? -6 : 6), 0);
      var t1 = performance.now();
      return { per: (t1 - t0) / 60, total: t1 - t0 };
    `);
    console.log(`     ${label}: ${num(sp.per)} мс на кадр (всего ${num(sp.total)} мс за 60)`);
    return sp.per;
  };
  await speed('монополия D 100-Q, MC 20', `
    resetSceneMemory(); pickScene('mono');
    var d = ipCurve('demand'); if (d) updateCurveExpr(d, '100 - Q');
    var mc = ipCurve('mc'); if (mc) updateCurveExpr(mc, '20');
    redrawAll();
  `);
  await speed('сложение: 4 группы спроса, 2 предложения', `
    resetSceneMemory(); pickScene('sdsum');
    sumSetCount('D', 4); sumSetCount('S', 2);
    var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
    ['100 - Q', '80 - Q', '60 - Q', '40 - Q'].forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
    var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
    ['Q', 'Q + 20'].forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
    redrawAll();
  `);
  await speed('эластичность D 100-Q', `
    resetSceneMemory(); pickScene('elast');
    var d = ipCurve('demand'); if (d) updateCurveExpr(d, '100 - Q');
    redrawAll();
  `);
}

if (errs.length) console.log('\nОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 6).join(' | '));
console.log(bad ? `\nрасхождений: ${bad}` : '\nвсё сошлось');
await browser.close();
process.exit(bad ? 1 : 0);
