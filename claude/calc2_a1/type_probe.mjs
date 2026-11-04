/* Набор в поле D настоящей клавиатурой MathLive: что приходит в поле и что видно под ним. */
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch(); keepAnswerOpen(browser);
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' }); await page.waitForTimeout(900);
const run = (c) => page.evaluate(async (c) => { const o = (new Function(c))(); await new Promise(r => setTimeout(r, 80)); return o; }, c);
export async function typeInto(page, run, text, scene = 'sd', idx = 0) {
  await run(`resetSceneMemory(); pickScene('${scene}'); redrawAll();`);
  await page.waitForTimeout(500);
  const mf = page.locator('#curve-list .fc-card').nth(idx).locator('math-field');
  await mf.click(); await page.waitForTimeout(150);
  await page.keyboard.press('Meta+a'); await page.waitForTimeout(150);
  await page.keyboard.press('Backspace'); await page.waitForTimeout(300);
  await page.keyboard.type(text, { delay: 60 });
  await page.keyboard.press('Enter'); await page.waitForTimeout(800);
  return run(`var card = document.querySelectorAll('#curve-list .fc-card')[${idx}];
    var d = STATE.curves.find(function (c) { return String(c.id) === card.getAttribute('data-cid'); });
    var inp = card.querySelector('.curve-expr-inp'), pre = card.querySelector('.fc-prefix'), qp = card.querySelector('.fc-qp');
    var why = card.querySelector('.f-why');
    var mf = card.querySelector('math-field');
    return { mfValue: mf && mf.value, inpValue: inp && inp.value, expr: d && d.expr, srcForm: d && d.srcForm, eq: STATE.eq,
      prefix: pre && pre.textContent.slice(0, 3), qpLine: qp && qp.textContent, bad: inp && inp.classList.contains('bad'),
      why: why ? why.textContent : '' };`);
}
if (process.argv[1].endsWith('type_probe.mjs')) {
  for (const t of process.argv.slice(2).length ? process.argv.slice(2) : ['Q=100-2P', '100-2P', 'P=100-2P', 'Q_d=100-2P']) {
    console.log(t, JSON.stringify(await typeInto(page, run, t)));
  }
  console.log('Ошибок страницы: ' + errs.length + ' ' + errs.slice(0, 3).join(' | '));
  await browser.close();
}
