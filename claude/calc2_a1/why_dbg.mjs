/* Отладка: кто стирает сообщение под полем D после Enter. */
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const browser = await chromium.launch(); keepAnswerOpen(browser);
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
await page.goto('http://127.0.0.1:8099/calc2/', { waitUntil: 'networkidle' }); await page.waitForTimeout(900);
await page.evaluate(() => {
  resetSceneMemory(); pickScene('sd'); redrawAll();
  window._log = [];
  const orig = window.fieldProblem;
  window.fieldProblem = function (i, m) {
    window._log.push([i.id, m, m ? '' : (new Error()).stack.split('\n').slice(2, 6).join(' | ')]);
    return orig(i, m);
  };
});
const mf = page.locator('#curve-list .fc-card').first().locator('math-field');
await mf.click(); await page.keyboard.press('Meta+a'); await page.keyboard.press('Backspace'); await page.waitForTimeout(300);
await page.keyboard.type('P=100-2P', { delay: 60 }); await page.waitForTimeout(800);
const before = await page.evaluate(() => [...document.querySelectorAll('#curve-list .fc-card')][0].querySelector('.f-why')?.textContent);
await page.keyboard.press('Enter'); await page.waitForTimeout(800);
console.log(JSON.stringify(await page.evaluate((b) => {
  const card = document.querySelector('#curve-list .fc-card');
  return { before: b, log: window._log.slice(-5), whys: [...card.querySelectorAll('.f-why')].map(w => w.textContent),
    mf: card.querySelector('math-field').value, inp: card.querySelector('.curve-expr-inp').value,
    sameCard: !!card.querySelector('.f-why') };
}, before), null, 1));
await browser.close();
