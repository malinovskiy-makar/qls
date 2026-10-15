// Быстрый взгляд на модель труда: открыть ключ, задать кривые (необязательно), МРОТ, снять числа, «Ответ», подписи холста.
//   node claude/calc2_labor/peek.mjs <ключ> ["D;S"] [МРОТ|off] [base] [снимок.png]
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const [key = 'labor-union', curves = '', minw = '', base = 'http://127.0.0.1:8099', shot = ''] = process.argv.slice(2);
const browser = keepAnswerOpen(await chromium.launch());
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errors.push(m.type() + ': ' + m.text().slice(0, 200)); });
await page.goto(base + '/calc2/?m=' + key, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const r = await page.evaluate(([curves, minw]) => {
  if (curves) {
    const [d, s] = curves.split(';');
    STATE.curves = [];
    addCurve(d); setRole(STATE.curves[0], 'demand');
    addCurve(s); setRole(STATE.curves[1], 'supply');
    if (typeof renderCurveList === 'function') renderCurveList();
  }
  if (minw === 'off') { STATE.laborMinOn = false; }
  else if (minw) { STATE.laborMinOn = true; setLaborMin(parseFloat(minw)); }
  redrawAll();
  const rnd = (o) => o && JSON.parse(JSON.stringify(o, (k, v) => typeof v === 'number' ? Math.round(v * 1000) / 1000 : v));
  return {
    union: rnd(STATE.laborUnion), bilat: rnd(STATE.laborBilateral), mono: rnd(STATE.laborMono),
    min: rnd(STATE.laborMin), welfare: rnd(STATE.laborMinWelfare), minOn: STATE.laborMinOn, minW: STATE.laborMinW,
    answer: Array.from(document.querySelectorAll('#info-labor .stat, #info-labor .hint, #info-labor .sb-subsec'))
      .map(e => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim(); }),
    texts: Array.from(document.querySelectorAll('#chart text')).map(t => t.textContent.trim()).filter(Boolean),
  };
}, [curves, minw]);
await page.waitForTimeout(600);
if (shot) await page.screenshot({ path: shot });
console.log(JSON.stringify({ ...r, errors }, null, 1));
await browser.close();
