// «Разбор» модели целиком текстом (абзацы по порядку, с классом источника).
//   node claude/calc2_labor/razbor_peek.mjs <ключ> ["D;S"] [МРОТ|off] [base]
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const [key = 'labor-union', curves = '', minw = '', base = 'http://127.0.0.1:8099'] = process.argv.slice(2);
const browser = keepAnswerOpen(await chromium.launch());
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
await page.goto(base + '/calc2/?m=' + key, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.evaluate(([curves, minw]) => {
  if (curves) { const [d, s] = curves.split(';'); STATE.curves = []; addCurve(d); setRole(STATE.curves[0], 'demand'); addCurve(s); setRole(STATE.curves[1], 'supply'); renderCurveList(); }
  if (minw === 'off') { const c = document.getElementById('chk-labmin'); if (c && c.checked) c.click(); }
  else if (minw) { const c = document.getElementById('chk-labmin'); if (c && !c.checked) c.click(); setLaborMin(parseFloat(minw)); }
  redrawAll();
}, [curves, minw]);
await page.waitForTimeout(900);
await page.click('#ex-bar').catch(() => {});
await page.waitForTimeout(600);
const ps = await page.evaluate(() => Array.from(document.querySelectorAll('#explain p, #explain .ex-from-cond, #explain .ex-from-answer'))
  .filter(p => p.getClientRects().length)
  .map(p => { const c = p.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
    return (p.className ? '[' + p.className + '] ' : '') + c.textContent.replace(/\s+/g, ' ').trim(); }));
console.log(ps.join('\n'));
await browser.close();
