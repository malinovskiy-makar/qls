import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto('http://127.0.0.1:8099/calc2/', { waitUntil: 'networkidle' }); await page.waitForTimeout(900);
for (const e of ['100 - L', 'L = 100 - W', '100 - W', 'W = 100 - L', 'Ld = 100 - W']) {
  console.log(e.padEnd(14), JSON.stringify(await page.evaluate((e) => {
    resetSceneMemory(); pickScene('labor'); redrawAll();
    const c = STATE.curves.find(x => x.role === 'demand');
    const err = updateCurveExpr(c, e); redrawAll();
    return { err, form: c.srcForm, expr: c.expr, eq: STATE.laborEq, axis: STATE.axisYDefault, pre: curvePrefix(c), params: Object.keys(STATE.params || {}) };
  }, e)));
}
console.log('errs', errs);
await browser.close();
