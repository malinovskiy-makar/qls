/* Краевые случаи А1: MC = Q − 200 (вершина прибыли MR = 0), составной спрос при убывающей MC. */
import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
await page.goto('http://127.0.0.1:8099/calc2/', { waitUntil: 'networkidle' }); await page.waitForTimeout(900);
const r = await page.evaluate(() => {
  const set = (d, s) => { resetSceneMemory(); pickScene('mono');
    updateCurveExpr(STATE.curves.find(c => c.role === 'demand'), d);
    updateCurveExpr(STATE.curves.find(c => c.role === 'mc' || c.role === 'supply'), s); redrawAll(); return STATE.mono; };
  const a = set('100-Q', 'Q-200');
  const out = { mcQminus200: { Q: a.Qm, P: a.Pm, alts: a.alts } };
  resetSceneMemory(); pickScene('mono-kink'); STATE.kinkInput = 'individual'; STATE.kiD1 = '120 - Q'; STATE.kiD2 = ''; STATE.kiD3 = ''; STATE.kinkMC = '160 - 4*Q'; redrawAll();
  const k = STATE.kinked || {}; out.kink = { Q: k.Qstar, P: k.Pstar, profit: k.profit };
  return out;
});
console.log(JSON.stringify(r));
await browser.close();
