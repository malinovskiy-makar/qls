/* Фаза 0 сессии А1 (24.10): замер «до». Ничего не чинит, только печатает, что модель отвечает сейчас.
     node claude/calc2_a1/phase0.mjs   (сервер на 8099) */
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
keepAnswerOpen(browser);
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
const run = (code) => page.evaluate(async (c) => { const out = (new Function(c))(); await new Promise(r => setTimeout(r, 80)); return out; }, code);
const MKT = `
  var setDS = function (scene, d, s) {
    resetSceneMemory(); pickScene(scene);
    updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), d);
    var low = STATE.curves.find(function (c) { return c.role === 'supply' || c.role === 'mc'; });
    if (low) updateCurveExpr(low, s);
    redrawAll();
  };
  var txt = function (id) { var e = document.getElementById(id); return e ? e.textContent.replace(/\\s+/g, ' ').trim().slice(0, 400) : '(нет узла)'; };
`;
const show = (t, v) => console.log('— ' + t + '\n   ' + JSON.stringify(v));

for (const mc of ['160-4*Q', '150-3*Q', 'Q^2-42*Q+520', '2*Q', '40']) {
  const r = await run(MKT + `setDS('mono', '120-P', '${mc}'); var m = STATE.mono;
    return { mono: m ? { Qm: m.Qm, Pm: m.Pm, psM: m.psM, vcM: m.vcM, Qc: m.Qc, dwl: m.dwl } : null, panel: txt('info-mono') };`);
  show('монополия D: Q = 120 − P, MC = ' + mc, r);
}
{
  const r = await run(MKT + `setDS('mono', '120-P', '2*Q+30'); setType('tax'); setTax(45); redrawAll();
    var t = STATE.monoTax; return t ? { Qt: t.Qt, Pt: t.Pt } : null;`);
  show('монополия MC = 2Q + 30, налог 45', r);
}
for (const [tag, setup] of [['налог 24 продавцу', "setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(24);"],
                            ['НДС 50 %', "setType('tax'); setTaxForm('vat'); setTax(50);"],
                            ['субсидия 24 продавцу', "setType('subsidy'); setTaxForm('unit'); setTaxSide('seller'); setTax(24);"],
                            ['налог 24 покупателю', "setType('tax'); setTaxForm('unit'); setTaxSide('buyer'); setTax(24);"]]) {
  const r = await run(MKT + `setDS('taxes', '180-P', '3*P-60'); ${setup} redrawAll();
    return { S: STATE.taxAfterS && STATE.taxAfterS.texExpr, D: STATE.taxAfterD && STATE.taxAfterD.texExpr, eq: STATE.taxEq, final: txt('info-final') };`);
  show('налоги, Qd = 180 − P, Qs = 3P − 60, ' + tag, r);
}
{
  const r = await run(`resetSceneMemory(); pickScene('laffer'); STATE.macro.laffer.d = '120-P'; STATE.macro.laffer.s = 'P'; redrawAll();
    return { err: STATE.macroErr, best: STATE.macroRes && STATE.macroRes.best };`);
  show('Лаффер D = 120 − P, S = P', r);
}
{
  const r = await run(`resetSceneMemory(); pickScene('adas'); STATE.macro.adas.ad = '400 + 1600/P'; redrawAll();
    return { err: STATE.macroErr, eq: STATE.macroRes && STATE.macroRes.eq };`);
  show('AD–AS, AD: 400 + 1600/P', r);
}
{
  const r = await run(`resetSceneMemory(); pickScene('mono-d3'); STATE.d3D1 = '120 - P'; STATE.d3D2 = '100 - Q'; STATE.d3MC = '20'; redrawAll();
    var e = document.getElementById('d3-error'); return { d3: STATE.discr3 && { found: STATE.discr3.found, q1: STATE.discr3.q1 }, err: e && e.style.display !== 'none' ? e.textContent : '' };`);
  show('дискриминация 3-й степени, D₁ = 120 − P', r);
}
{
  const r = await run(`resetSceneMemory(); pickScene('monoexport'); STATE.d3D1 = '100 - P'; STATE.d3MC = 'Q'; redrawAll();
    var e = document.getElementById('d3-error'); return { d3: STATE.discr3 && { found: STATE.discr3.found, q1: STATE.discr3.q1, q2: STATE.discr3.q2 }, err: e && e.style.display !== 'none' ? e.textContent : '' };`);
  show('монополист и внешний рынок, D = 100 − P', r);
}
{
  const r = await run(`resetSceneMemory(); pickScene('mono-kink'); STATE.kinkInput = 'individual'; STATE.kiD1 = '100 - P'; STATE.kiD2 = '60 - P'; STATE.kiD3 = ''; STATE.kinkMC = '20'; redrawAll();
    var k = STATE.kinked || {}; return { found: k.found, Q: k.Qstar, P: k.Pstar, panel: (document.getElementById('info-kinked') || {}).textContent };`);
  show('составной спрос, D₁ = 100 − P, D₂ = 60 − P', r);
}
for (const mc of ['160-4*Q', '150-3*Q']) {
  const r = await run(`resetSceneMemory(); pickScene('mono-d3'); STATE.d3D1 = '120 - Q'; STATE.d3D2 = '80 - Q'; STATE.d3MC = '${mc}'; redrawAll();
    var d = STATE.discr3 || {}; return { found: d.found, Qtot: d.Qtot, q1: d.q1, q2: d.q2, P1: d.P1, P2: d.P2 };`);
  show('дискриминация 3-й, D₁ 120 − Q, D₂ 80 − Q, MC ' + mc, r);
  const r2 = await run(`resetSceneMemory(); pickScene('monoexport'); STATE.d3D1 = '120 - Q'; STATE.d3D2 = '30'; STATE.d3MC = '${mc}'; redrawAll();
    var d = STATE.discr3 || {}; return { found: d.found, Qtot: d.Qtot, q1: d.q1, q2: d.q2, P1: d.P1, unb: d.unbounded };`);
  show('внешний рынок, D 120 − Q, Pw 30, MC ' + mc, r2);
}

/* Ввод в поле D руками: «Q=100-2P» через настоящую клавиатуру MathLive. */
await run(`resetSceneMemory(); pickScene('sd'); redrawAll();`);
await page.waitForTimeout(400);
const typeInto = async (text) => {
  const mf = page.locator('#curve-list .fc-card').first().locator('math-field');
  await mf.click();
  await page.keyboard.press('Meta+a');
  await page.keyboard.type(text, { delay: 30 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(700);
  return run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
    var card = document.querySelector('#curve-list .fc-card');
    var inp = card.querySelector('.curve-expr-inp'), pre = card.querySelector('.fc-prefix'), qp = card.querySelector('.fc-qp');
    var prob = card.querySelector('.field-problem, .fp-msg, [role=alert]');
    return { inpValue: inp && inp.value, expr: d.expr, srcForm: d.srcForm, eq: STATE.eq,
      prefix: pre && pre.textContent, qpLine: qp && qp.textContent, bad: inp && inp.classList.contains('bad'),
      problem: prob ? prob.textContent : '' };`);
};
show('поле D: набрано «Q=100-2P»', await typeInto('Q=100-2P'));
await run(`resetSceneMemory(); pickScene('sd'); redrawAll();`);
await page.waitForTimeout(400);
show('поле D: набрано «100-2P»', await typeInto('100-2P'));
show('поле D: затем «P=100-2P»', await typeInto('P=100-2P'));

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
await browser.close();
