// Быстрый взгляд: модель, режим точек, щелчки по точкам модели, вывод STATE.marks и строк списка.
//   node claude/panels_s7/peek.mjs taxes "40,60 40,40 50,50 20,80" [base]
import { chromium } from 'playwright';
const [key, pts, base] = [process.argv[2] || 'taxes', process.argv[3] || '', process.argv[4] || 'http://127.0.0.1:8099'];
const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript(() => { localStorage.clear(); localStorage.setItem('calc2.v1.answerHidden', '0'); });
const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
await p.goto(base + '/calc2/?m=' + key, { waitUntil: 'load' }); await p.waitForTimeout(1200);
await p.click('#tool-pts'); await p.waitForTimeout(400);
for (const xy of pts.split(' ').filter(Boolean)) {
  const [x, y] = xy.split(',').map(Number);
  const [cx, cy] = await p.evaluate(([x, y]) => { const { mx, my } = mainScales(null); const r = document.getElementById('chart').getBoundingClientRect(); return [r.left + mx(x), r.top + my(y)]; }, [x, y]);
  await p.mouse.click(cx, cy); await p.waitForTimeout(1100);
}
console.log(JSON.stringify(await p.evaluate(() => ({
  marks: STATE.marks.map(m => [m.id, m.text, +m.x.toFixed(2), +m.y.toFixed(2), m.snapTo, m.on, markOnText(m)]),
  rows: [...document.querySelectorAll('#mark-list .mark-row')].map(r => { const c = r.cloneNode(true); c.querySelectorAll('.katex-mathml').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim() + ' || ' + [...r.querySelectorAll('annotation')].map(a => a.textContent).join(' · '); }),
})), null, 1), errs);
await b.close();
