// Снимки стартов четырёх моделей труда (1440 × 900, «Ответ» открыт) и состояние галочки МРОТ.
//   node claude/calc2_labor/shot_starts.mjs [папка] [base] [engine]
import * as pw from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const [dir = 'claude/shots/calc2_labor', base = 'http://127.0.0.1:8099', engine = 'chromium'] = process.argv.slice(2);
const browser = keepAnswerOpen(await pw[engine].launch());
for (const key of ['labor', 'labor-mono', 'labor-union', 'labor-bilat']) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
  await page.goto(base + '/calc2/?m=' + key, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const st = await page.evaluate(() => {
    const chk = document.getElementById('chk-labmin'), lab = chk && chk.closest('label');
    const vis = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
    return { chkShown: vis(lab), checked: chk && chk.checked, field: vis(document.getElementById('labmin-field')),
      minLine: [...document.querySelectorAll('#chart text.coord-num')].some(t => /min/.test(t.textContent)) };
  });
  console.log(key, JSON.stringify(st));
  await page.screenshot({ path: `${dir}/start_${key}_${engine}.png` });
  await page.close();
}
await browser.close();
