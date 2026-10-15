// Строка чисел «Ответа» (как answerNums в cards_probe) на старте модели труда после ввода в D (curve-expr-1).
//   node claude/calc2_labor/cards_live.mjs [base]
import { chromium } from 'playwright';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const base = process.argv[2] || 'http://127.0.0.1:8099';
const browser = keepAnswerOpen(await chromium.launch());
const out = {};
for (const [key, expr] of [['labor', '90 - L'], ['labor-mono', '90 - L'], ['labor-union', '90 - L'], ['labor-bilat', '90 - L'], ['labor', '100 - L']]) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
  await page.goto(base + '/calc2/?m=' + key, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await page.evaluate((v) => { const e = document.getElementById('curve-expr-1'); setFieldValue(e, v); e.dispatchEvent(new Event('change', { bubbles: true })); }, expr);
  await page.waitForTimeout(900);
  out[key + '|' + expr] = await page.evaluate(() => {
    const tx = (e) => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent; };
    const hero = [...document.querySelectorAll('#ans-hero .ans-cell .ans-val')].map(tx).join('|');
    const sb = [...document.querySelectorAll('#sb-body .stat > b')].map(tx).join('|');
    return (hero + '#' + sb).replace(/[\s   ​]+/g, '').replace(/[()]/g, '').replace(/[;\/]/g, '|');
  });
  await page.close();
}
console.log(JSON.stringify(out, null, 1));
await browser.close();
