/* Проба: рисуется ли облако фона входа без единого действия (18.09.2026).
   node scripts/stol_probe_bg.mjs [порт] [reduce] */
import { chromium } from 'playwright';

const PORT = process.argv[2] || '8000';
const reduce = process.argv[3] === 'reduce';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2,
                                       reducedMotion: reduce ? 'reduce' : 'no-preference' });
const page = await ctx.newPage();
await page.goto('http://127.0.0.1:' + PORT + '/catalog/', { waitUntil: 'load' });
for (const t of [5, 15, 30]) {
  await page.waitForTimeout(t === 5 ? 5000 : 10000 + (t === 30 ? 5000 : 0));
  const r = await page.evaluate(() => {
    const c = document.querySelector('#stol-bg canvas');
    if (!c) return { canvas: false };
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0, max = 0;
    for (let i = 3; i < d.length; i += 4) { if (d[i]) { n++; if (d[i] > max) max = d[i]; } }
    return { painted: n, maxAlpha: max, stats: document.getElementById('stol-bg').__tmapPreview.stats() };
  });
  console.log(t + 's', JSON.stringify(r));
}
await browser.close();
