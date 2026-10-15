// Снимок панели «Точки и площади» (taxes, три точки + точка на спросе), 1 440 × 900, тёмная и светлая тема.
//   node claude/panels_s7/shot_pts.mjs <тег> ["x,y …"] [действия JS после щелчков]
import { chromium } from 'playwright';
const tag = process.argv[2] || 'pts', pts = process.argv[3] || '40,60 40,40 50,50 20,80', extra = process.argv[4] || '';
const b = await chromium.launch();
for (const theme of ['dark', 'light']) {
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { localStorage.clear(); localStorage.setItem('theme', t); }, theme);
  const p = await ctx.newPage();
  await p.goto((process.env.BASE || 'http://127.0.0.1:8099') + '/calc2/?m=taxes', { waitUntil: 'load' });
  await p.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  await p.waitForTimeout(800);
  await p.click('#tool-pts'); await p.waitForTimeout(400);
  for (const xy of pts.split(' ').filter(Boolean)) {
    const [x, y] = xy.split(',').map(Number);
    const [cx, cy] = await p.evaluate(([x, y]) => { const { mx, my } = mainScales(null); const r = document.getElementById('chart').getBoundingClientRect(); return [r.left + mx(x), r.top + my(y)]; }, [x, y]);
    await p.mouse.click(cx, cy); await p.waitForTimeout(1100);
  }
  if (extra) { await p.evaluate(extra); await p.waitForTimeout(800); }
  await p.screenshot({ path: `claude/shots/calc2_panels_s7/${tag}_${theme}.png` });
  await ctx.close();
}
await b.close();
