/* Снимки окна «Вид графика»: node claude/panels_s5/shots_view.mjs <папка> ключ… (обе темы, 1440). */
import { chromium } from 'playwright';
import fs from 'fs';
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const [dir, ...keys] = process.argv.slice(2);
fs.mkdirSync(dir, { recursive: true });
const b = await chromium.launch();
for (const theme of ['light', 'dark']) {
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((t) => { try { localStorage.clear(); localStorage.setItem('theme', t); } catch (e) {} }, theme);
  const p = await ctx.newPage();
  await p.goto(BASE + '/calc2/'); await p.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
  for (const key of keys) {
    await p.evaluate(k => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
    await p.waitForTimeout(600);
    await p.click('#btn-view'); await p.waitForTimeout(400);
    const r = await p.evaluate(() => { const e = document.getElementById('wrench-pop'); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: Math.min(r.height, 900 - r.y) }; });
    await p.screenshot({ path: dir + '/view_' + key + '_' + theme + '.png', clip: { x: r.x, y: r.y, width: r.w, height: r.h } });
    await p.click('#btn-view'); await p.waitForTimeout(200);
  }
  await ctx.close();
}
await b.close();
