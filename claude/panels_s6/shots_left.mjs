/* Снимки левой панели («Условие») моделей: node claude/panels_s5/shots_left.mjs <папка> [ключи…]
   BASE=… (по умолчанию 8099), THEMES="light dark", W=1440. */
import { chromium } from 'playwright';
import fs from 'fs';
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const [dir, ...keys] = process.argv.slice(2);
fs.mkdirSync(dir, { recursive: true });
const W = +(process.env.W || 1440);
const b = await chromium.launch();
for (const theme of (process.env.THEMES || 'light').split(' ')) {
  const ctx = await b.newContext({ viewport: { width: W, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU', deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { try { localStorage.clear(); localStorage.setItem('theme', t); } catch (e) {} }, theme);
  const p = await ctx.newPage();
  await p.goto(BASE + '/calc2/'); await p.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
  for (const k of keys) {
    const [key, extra] = k.split('@');
    await p.evaluate(([k, x]) => { resetSceneMemory(); pickScene(k); closePicker(); if (x) (new Function(x))(); redrawAll(); }, [key, extra ? decodeURIComponent(extra) : '']);
    await p.waitForTimeout(700);
    const r = await p.evaluate(() => { const e = document.getElementById('tools-panel'); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: Math.min(e.scrollHeight, 900 - r.y) }; });
    await p.screenshot({ path: dir + '/' + key.replace(/[^a-z0-9-]/g, '') + (extra ? '_' + extra.replace(/[^a-zA-Z0-9]/g, '').slice(0, 12) : '') + '_' + theme + '.png', clip: { x: r.x, y: r.y, width: r.w, height: r.h } });
  }
  await ctx.close();
}
await b.close();
