// Фаза 3 — КВОТЫ. Главная мысль сюжета: при связывающей квоте цена не
// определена однозначно, а лежит в коридоре [S(Qк); D(Qк)]. Излишки внутри
// коридора ПЕРЕТЕКАЮТ, а их сумма и трапеция потерь стоят на месте.
//   node calc2/tests/interv_phase3_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let ok = true;
function check(label, got, want, tol) {
  const good = typeof got === 'number' && isFinite(got) && Math.abs(got - want) <= tol;
  if (!good) ok = false;
  console.log((good ? 'OK   ' : 'FAIL ') + label + ' = ' +
    ((typeof got === 'number') ? got.toFixed(6) : String(got)) + ' (ожид ' + want + ' ±' + tol + ')');
}
function flag(label, cond, detail) {
  if (!cond) ok = false;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (detail ? '  -> ' + detail : ''));
}

// --- 1. Квота 40 при D = 100 − Q, S = Q: коридор [40; 60] ---------------
// Ручной расчёт: S(40) = 40 — ниже этой цены продавцы не отдадут 40 единиц;
// D(40) = 60 — выше этой цены покупатели не выберут 40 единиц.
const base = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('quota'); redrawAll();
  var q = STATE.qt || {};
  return { Qq: q.Qq, Plo: q.Plo, Phi: q.Phi, binding: q.binding ? 1 : 0,
           active: STATE.quotaActive ? 1 : 0, eqQ: (STATE.eq||{}).Q };
})()`);
check('квота 40 · разрешённый объём', base.Qq, 40, 1e-9);
check('квота 40 · нижняя граница коридора P_s(40)', base.Plo, 40, 1e-6);
check('квота 40 · верхняя граница коридора P_d(40)', base.Phi, 60, 1e-6);
flag('квота 40 связывает (Q* = 50)', base.binding === 1 && base.active === 1 && Math.abs(base.eqQ - 50) < 0.3,
     JSON.stringify(base));

// --- 2. Десять положений ползунка: CS+PS и DWL постоянны ----------------
// Ручной расчёт: CS + PS = ∫₀^40 (D − S) dq = ∫₀^40 (100 − 2q) dq = 4000 − 1600 = 2400.
// DWL = ∫₄₀^50 (100 − 2q) dq = 2500 − 2400 = 100. Цена в оба выражения не входит.
const table = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('quota');
  var rows = [];
  for (var i = 0; i <= 9; i++) {
    setQuotaPos(i / 9);
    var q = STATE.qt || {};
    rows.push({ pos: i / 9, P: q.P, cs: q.cs, ps: q.ps, sw: q.sw, dwl: q.dwl });
  }
  return rows;
})()`);
console.log('\n  цена       CS          PS          CS+PS       DWL');
table.forEach(r => {
  console.log('  ' + r.P.toFixed(4).padStart(8) + '  ' + r.cs.toFixed(6).padStart(11) + '  ' +
    r.ps.toFixed(6).padStart(11) + '  ' + r.sw.toFixed(9).padStart(14) + '  ' + r.dwl.toFixed(9).padStart(12));
});
console.log('');
const sw0 = table[0].sw, dwl0 = table[0].dwl;
const swSpread = Math.max(...table.map(r => Math.abs(r.sw - sw0)));
const dwlSpread = Math.max(...table.map(r => Math.abs(r.dwl - dwl0)));
check('коридор пройден снизу доверху · первая цена', table[0].P, 40, 1e-6);
check('коридор пройден снизу доверху · последняя цена', table[9].P, 60, 1e-6);
check('CS+PS одинаков во всех десяти строках (разброс)', swSpread, 0, 1e-9);
check('DWL одинаков во всех десяти строках (разброс)', dwlSpread, 0, 1e-9);
check('CS+PS равен 2400 (ручной расчёт)', sw0, 2400, 1e-6);
check('DWL равен 100 (ручной расчёт)', dwl0, 100, 1e-6);
// А сами излишки обязаны ПЕРЕТЕКАТЬ, иначе сюжет ничего не показывает.
const csDrop = table[0].cs - table[9].cs, psRise = table[9].ps - table[0].ps;
check('CS при росте цены падает (с 1600 до 800)', csDrop, 800, 1e-6);
check('PS при росте цены растёт (с 800 до 1600)', psRise, 800, 1e-6);
check('перетекание в обе стороны одинаково', Math.abs(csDrop - psRise), 0, 1e-9);
check('нижний край: CS = 1600', table[0].cs, 1600, 1e-6);
check('нижний край: PS = 800', table[0].ps, 800, 1e-6);
check('верхний край: CS = 800', table[9].cs, 800, 1e-6);
check('верхний край: PS = 1600', table[9].ps, 1600, 1e-6);

// --- 3. Квота ВЫШЕ равновесия не связывает ------------------------------
const wide = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('quota'); setQuota(70); redrawAll();
  var q = STATE.qt || {};
  return { binding: q.binding ? 1 : 0, active: STATE.quotaActive ? 1 : 0,
           P: q.P === undefined ? 'нет' : q.P, dwl: q.dwl === undefined ? 'нет' : q.dwl,
           slider: (function(){ var e = document.getElementById('quota-price-field');
                                return e && e.offsetParent !== null ? 1 : 0; })(),
           eqQ: (STATE.eq||{}).Q,
           info: ((document.getElementById('info-tax')||{}).innerText || '').replace(/\\s+/g,' ') };
})()`);
flag('квота 70 (выше Q*=50) не связывает', wide.binding === 0 && wide.active === 0, JSON.stringify({ b: wide.binding, a: wide.active }));
flag('коридора нет', wide.P === 'нет' && wide.dwl === 'нет', JSON.stringify({ P: wide.P, dwl: wide.dwl }));
flag('ползунок цены не показывается', wide.slider === 0);
flag('рынок остаётся в равновесии Q*=50', Math.abs(wide.eqQ - 50) < 0.3, 'Q*=' + wide.eqQ);
flag('панель честно говорит, что не связывает', /не связывает/.test(wide.info), wide.info.slice(0, 130));

// --- 4. Коридор нарисован и подписан ------------------------------------
const draw = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('quota'); redrawAll();
  var legends = [].map.call(document.querySelectorAll('#chart [data-legend]'), function(e){ return e.getAttribute('data-legend'); });
  return { corridor: legends.filter(function(t){ return /Коридор/.test(t); }).length,
           cs: legends.filter(function(t){ return /CS/.test(t); }).length,
           ps: legends.filter(function(t){ return /PS/.test(t); }).length,
           dwl: legends.filter(function(t){ return /DWL/.test(t); }).length,
           sliderShown: (function(){ var e = document.getElementById('quota-price-field');
                                     return e && e.offsetParent !== null ? 1 : 0; })(),
           label: (document.getElementById('quota-price-range')||{}).textContent };
})()`);
flag('коридор закрашен на графике', draw.corridor === 1, 'закрасок коридора: ' + draw.corridor);
flag('излишки и потери закрашены', draw.cs === 1 && draw.ps === 1 && draw.dwl === 1, JSON.stringify(draw));
flag('ползунок цены показан', draw.sliderShown === 1);
flag('границы коридора подписаны числами', /от 40 до 60/.test(draw.label || ''), draw.label);

if (errs.length) { ok = false; console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | ')); }
await browser.close();
console.log('\nФАЗА 3: ' + (ok ? 'СОШЛАСЬ' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
