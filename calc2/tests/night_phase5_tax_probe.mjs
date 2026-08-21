/* Ночная сессия. ФАЗА 5 — «Вмешательство государства» в правой панели.
   Блок переехал КАК ЕСТЬ; проба сверяет, что он на новом месте, виден там,
   где и раньше, и считает прежние числа.
     node calc2/tests/night_phase5_tax_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

let ok = true;
const rep = (n, pass, d) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + n + (d ? '  -> ' + d : '')); if (!pass) ok = false; };

const where = await page.evaluate(() => {
  const t = document.getElementById('sec-tax');
  return { inRight: !!(t && document.getElementById('params-panel').contains(t)),
           inLeft: !!(t && document.getElementById('tools-panel').contains(t)) };
});
rep('блок лежит в правой панели', where.inRight && !where.inLeft, JSON.stringify(where));

// Видимость по сценам: где блок был доступен раньше, там доступен и теперь.
const vis = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const out = {};
  for (const k of Object.keys(SCENE_ROUTE)) {
    resetSceneMemory(); pickScene(k); await wait(160);
    const t = document.getElementById('sec-tax');
    out[k] = !!(t && t.offsetParent !== null && !t.classList.contains('scoped-off'));
  }
  return out;
});
const shown = Object.keys(vis).filter(k => vis[k]);
console.log('     блок доступен в ' + shown.length + ' сценах: ' + shown.join(', '));
rep('доступен ровно в сценах вмешательства', shown.slice().sort().join() === ['tax','tax-adv','ceil','mono'].sort().join(),
    shown.join(', '));

const nums = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const out = {};
  resetSceneMemory(); pickScene('tax'); await wait(300);
  setType('tax'); setTax(20); redrawAll(); await wait(150);
  out.tax = { Q1: (STATE.taxEq || {}).Q, Pb: (STATE.taxEq || {}).Pb, Ps: (STATE.taxEq || {}).Ps,
              Tx: STATE.tx, DWL: STATE.dwl };
  setType('subsidy'); setTax(20); redrawAll(); await wait(150);
  out.sub = { Q1: (STATE.taxEq || {}).Q, spend: STATE.budget, DWL: STATE.dwl };
  resetSceneMemory(); pickScene('ceil'); await wait(300);
  setType('ceiling'); setPReg(30); redrawAll(); await wait(150);
  out.ceil = { type: STATE.intervType, P: STATE.pReg, active: STATE.pcActive,
               qd: (STATE.pc || {}).Qd, qs: (STATE.pc || {}).Qs, gap: (STATE.pc || {}).gap };
  setType('floor'); setPReg(70); redrawAll(); await wait(150);
  out.floor = { type: STATE.intervType, P: STATE.pReg, active: STATE.pcActive,
                qd: (STATE.pc || {}).Qd, qs: (STATE.pc || {}).Qs, gap: (STATE.pc || {}).gap };
  return out;
});
console.log(JSON.stringify(nums, null, 1));
const near = (a, b, e) => a != null && Math.abs(a - b) < (e || 0.3);
rep('налог t=20: Q1=40', near(nums.tax.Q1, 40), 'Q1=' + nums.tax.Q1);
rep('налог t=20: Pb=60',  near(nums.tax.Pb, 60), 'Pb=' + nums.tax.Pb);
rep('налог t=20: Ps=40',  near(nums.tax.Ps, 40), 'Ps=' + nums.tax.Ps);
rep('налог t=20: Tx=800', near(nums.tax.Tx, 800, 6), 'Tx=' + nums.tax.Tx);
rep('налог t=20: DWL=100', near(nums.tax.DWL, 100, 3), 'DWL=' + nums.tax.DWL);
rep('субсидия s=20: Q1=60', near(nums.sub.Q1, 60), 'Q1=' + nums.sub.Q1);
rep('субсидия s=20: расход бюджета −1200', near(nums.sub.spend, -1200, 6), 'расход=' + nums.sub.spend);
rep('субсидия s=20: DWL=100', near(nums.sub.DWL, 100, 3), 'DWL=' + nums.sub.DWL);
rep('потолок 30 связывает: дефицит Qd=70 > Qs=30', nums.ceil.type === 'ceiling' && nums.ceil.active
    && near(nums.ceil.qd, 70) && near(nums.ceil.qs, 30), JSON.stringify(nums.ceil));
rep('пол 70 связывает: избыток Qs=70 > Qd=30', nums.floor.type === 'floor' && nums.floor.active
    && near(nums.floor.qs, 70) && near(nums.floor.qd, 30), JSON.stringify(nums.floor));
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'блок вмешательства работает на новом месте' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
