// Замер Фазы 6 (Б30, Б31): калькулятор не должен ломаться ни на одной
// введённой функции. Прогоняет набор из ТЗ по трём сюжетам и печатает
// таблицу «сцена × функция × что показано × есть ли ошибка».
//   node calc2/tests/robust_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const MARKET = [
  ['100 - Q', 'прямая'],
  ['100 - Q^2/100', 'выпуклая'],
  ['sqrt(10000 - Q^2)', 'четверть окружности'],
  ['100/(1 + Q/20)', 'гипербола, асимптота'],
  ['max(0, 80 - Q)', 'кусочная, ломается в Q = 80'],
  ['100 - 0*Q', 'горизонтальная'],
];
const COSTS = [
  ['Q^3 - 6*Q^2 + 15*Q + 18', 'классическая'],
  ['Q^2 + 18', 'минимума AVC нет'],
  ['20*Q', 'постоянная MC'],
  ['Q^3 - 6*Q^2 + 15*Q', 'нулевые постоянные'],
  ['0.5*Q^2 + 10*Q + 50', 'минимум AVC на краю'],
  ['Q^2*sqrt(Q) + 30', 'нецелая степень'],
];
const PROD = [
  ['30*L^2 - L^3', 'классическая'],
  ['10*L', 'MP постоянна'],
  ['100*sqrt(L)', 'максимума TP нет'],
  ['L^2', 'MP растёт всегда'],
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e.message).slice(0, 120)));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

const short = (s) => (s || '').replace(/\s+/g, ' ').trim().slice(0, 110);

console.log('## Спрос и предложение (меняем D)\n');
for (const [expr, note] of MARKET) {
  const before = errors.length;
  const r = await page.evaluate((e) => {
    resetSceneMemory(); pickScene('sd');
    const d = curveByRole('demand');
    const err = d ? updateCurveExpr(d, e) : 'нет кривой D';
    redrawAll();
    ['sb-btn'].forEach(id => { const b = document.getElementById(id); if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); });
    return { err: err || '', eq: STATE.eq ? [STATE.eq.Q, STATE.eq.P] : null,
             cs: STATE.cs, ps: STATE.ps, lin: !!(d && d.linear),
             panel: (document.getElementById('sb-body') || {}).innerText || '' };
  }, expr);
  const n = errors.length - before;
  console.log(`- \`${expr}\` (${note}): ` + (r.err ? 'НЕ РАЗОБРАНА: ' + r.err : '') +
    (r.eq ? `равновесие (${r.eq[0].toFixed(2)}; ${r.eq[1].toFixed(2)}), CS ${Number(r.cs).toFixed(1)}, PS ${Number(r.ps).toFixed(1)}` : 'равновесия нет') +
    (r.lin ? ', распознана как прямая' : '') + (n ? `  ⚠ ошибок страницы ${n}` : ''));
}

console.log('\n## Издержки фирмы\n');
for (const [expr, note] of COSTS) {
  const before = errors.length;
  const r = await page.evaluate((e) => {
    resetSceneMemory(); pickScene('costs');
    STATE.costsTC = e; STATE.lrOn = true; STATE.lrPrice = 15.54; redrawAll();
    ['sb-btn'].forEach(id => { const b = document.getElementById(id); if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); });
    return { ready: STATE.costsReady, panel: (document.getElementById('info-costs') || {}).innerText || '' };
  }, expr);
  const n = errors.length - before;
  console.log(`- \`${expr}\` (${note}): ` + (r.ready ? '' : 'НЕ РАЗОБРАНА. ') + short(r.panel) + (n ? `  ⚠ ошибок ${n}` : ''));
}

console.log('\n## Производственная функция\n');
for (const [expr, note] of PROD) {
  const before = errors.length;
  const r = await page.evaluate((e) => {
    resetSceneMemory(); pickScene('prod');
    STATE.prodExpr = e; redrawAll();
    ['sb-btn'].forEach(id => { const b = document.getElementById(id); if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); });
    return { ok: !!STATE.prod, panel: (document.getElementById('info-prod') || {}).innerText || '' };
  }, expr);
  const n = errors.length - before;
  console.log(`- \`${expr}\` (${note}): ` + (r.ok ? '' : 'НЕ РАЗОБРАНА. ') + short(r.panel) + (n ? `  ⚠ ошибок ${n}` : ''));
}

await browser.close();
console.log('\nОшибок страницы всего: ' + errors.length);
errors.slice(0, 6).forEach(e => console.log('  ' + e));
