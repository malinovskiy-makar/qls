/* Фаза 2: «Итоговая функция» для Q(P) и регрессия P(Q). */
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch(); keepAnswerOpen(browser);
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' }); await page.waitForTimeout(900);
const run = (c) => page.evaluate(async (c) => { const o = (new Function(c))(); await new Promise(r => setTimeout(r, 80)); return o; }, c);
const MKT = `var setDS = function (scene, d, s) { resetSceneMemory(); pickScene(scene);
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), d);
  var low = STATE.curves.find(function (c) { return c.role === 'supply' || c.role === 'mc'; }); if (low) updateCurveExpr(low, s); redrawAll(); };
  var ff = function () { var e = document.getElementById('info-final'); var m = e && e.querySelector('.katex-mathml annotation'); return m ? m.textContent : (e ? e.textContent : ''); };`;
for (const [d, s, tag, setup] of [
  ['180-P', '3*P-60', 'налог 24 продавцу', "setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(24);"],
  ['180-P', '3*P-60', 'НДС 50', "setType('tax'); setTaxForm('vat'); setTax(50);"],
  ['180-P', '3*P-60', 'субсидия 24 продавцу', "setType('subsidy'); setTaxForm('unit'); setTaxSide('seller'); setTax(24);"],
  ['180-P', '3*P-60', 'субсидия 25 % от цены продавца', "setType('subsidy'); setTaxForm('subseller'); setTax(25);"],
  ['180-P', '3*P-60', 'налог 24 покупателю', "setType('tax'); setTaxForm('unit'); setTaxSide('buyer'); setTax(24);"],
  ['100-Q', 'Q', 'P(Q) субсидия покупателю 20', "setType('subsidy'); setTaxForm('unit'); setTaxSide('buyer'); setTax(20);"],
  ['100-Q', 'Q', 'P(Q) субсидия продавцу 20', "setType('subsidy'); setTaxForm('unit'); setTaxSide('seller'); setTax(20);"],
  ['100-Q', 'Q', 'P(Q) налог покупателю 20', "setType('tax'); setTaxForm('unit'); setTaxSide('buyer'); setTax(20);"],
  ['100-Q', 'Q', 'P(Q) налог продавцу 20', "setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(20);"],
  ['180-P', '0.01*P^2', 'нелинейная Q(P), налог 24', "setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(24);"],
]) {
  const r = await run(MKT + `setDS('taxes', '${d}', '${s}'); ${setup} redrawAll();
    var a = intervOnBuyer() ? STATE.taxAfterD : STATE.taxAfterS;
    return { fe: a && a.finalExpr, lhs: a && a.finalLhs, txt: (document.getElementById('info-final')||{}).textContent.slice(-40), tex: a && a.texExpr, recY: a && a.recY, eq: STATE.taxEq, T: STATE.tx, B: STATE.budget };`);
  console.log(tag.padEnd(34), JSON.stringify(r));
}
console.log('Ошибок страницы: ' + errs.length + ' ' + errs.slice(0, 3).join(' | '));
await browser.close();
