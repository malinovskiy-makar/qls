// Снимки холста трёх моделей карточки А2 (1 440, «Ответ» открыт, тёмная тема).
import { chromium } from 'playwright';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await ctx.addInitScript(() => { localStorage.clear(); localStorage.setItem('theme', 'dark'); localStorage.setItem('calc2.v1.answerHidden', '0'); });
const p = await ctx.newPage();
for (const key of ['labor', 'ext', 'labor-bilat']) {
  await p.goto((process.env.BASE || 'http://127.0.0.1:8099') + '/calc2/?m=' + key, { waitUntil: 'load' });
  await p.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  await p.waitForTimeout(800);
  await p.locator('#chart').screenshot({ path: `claude/shots/calc2_panels_s7/A2_${key}${process.env.TAG || ''}.png` });
}
await b.close();
