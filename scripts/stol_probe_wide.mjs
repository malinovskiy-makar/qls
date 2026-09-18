/* Проба: какие элементы выходят за правый край окна (18.09.2026).
   node scripts/stol_probe_wide.mjs [порт] [ширина] [путь] */
import { chromium } from 'playwright';

const PORT = process.argv[2] || '8000';
const W = Number(process.argv[3] || 360);
const PATH = process.argv[4] || '/catalog/';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: W, height: 800 } })).newPage();
await page.goto('http://127.0.0.1:' + PORT + PATH, { waitUntil: 'load' });
console.log(JSON.stringify(await page.evaluate(() => {
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > innerWidth + 0.5) {
      out.push((el.tagName + '.' + [...el.classList].join('.') + '#' + el.id).slice(0, 70) + ' right=' + Math.round(r.right));
    }
  }
  return { scrollWidth: document.documentElement.scrollWidth, list: out.slice(0, 15) };
}), null, 1));
await browser.close();
