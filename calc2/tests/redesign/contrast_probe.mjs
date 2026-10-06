/* КОНТРАСТ ЛИНИЙ К ХОЛСТУ (инвариант задания редизайна calc2): у каждой
   нарисованной кривой каждой из 44 моделей контраст цвета линии к фону
   холста не ниже 3 : 1 — в светлой и в тёмной теме. Линия — путь холста без
   заливки толщиной от 1,5 px; цвет — вычисленный stroke с учётом прозрачности;
   фон холста — вычисленный цвет --canvas. Служебные узлы (data-service) и
   заливки не меряются.

   node calc2/tests/redesign/contrast_probe.mjs [--keys a,b]
   Код 0 — все линии не ниже 3 : 1.                                          */
import { chromium } from 'playwright';

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('keys', '') || '').split(',').filter(Boolean);
const MIN = 3;

const browser = await chromium.launch();
let bad = 0, n = 0, worst = { c: 99 };
for (const theme of ['light', 'dark']) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 760 }, reducedMotion: 'reduce' });
  await ctx.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
  const page = await ctx.newPage();
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
  const keys = (await page.evaluate(() => Object.keys(SCENE_ROUTE))).filter(k => !ONLY.length || ONLY.includes(k));
  for (const key of keys) {
    await page.evaluate((k) => { resetSceneMemory(); pickScene(k); if (typeof closePicker === 'function') closePicker(); redrawAll(); }, key);
    await page.waitForTimeout(250);
    const r = await page.evaluate(() => {
      const rgb = (s) => { const m = String(s).match(/[\d.]+/g); return m ? m.slice(0, 4).map(Number) : null; };
      const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const probe = document.createElement('div'); probe.style.color = getComputedStyle(document.documentElement).getPropertyValue('--canvas') || '#fff';
      document.body.appendChild(probe); const bg = rgb(getComputedStyle(probe).color); probe.remove();
      const out = [];
      // Линия кривой: путь без заливки, толщиной от 1,5 px; оси, сетка, деления,
      // служебные узлы и заливки не меряются (у направляющих к осям 1 px).
      document.querySelectorAll('#chart path, #chart polyline').forEach(p => {
        if (p.closest('[data-service], defs, clipPath, marker, pattern, .axes, .grid, [class*="axis"], [class*="grid"], [class*="tick"]')) return;
        const cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden' || cs.stroke === 'none' || +cs.opacity === 0) return;
        const fill = rgb(cs.fill);
        if (cs.fill !== 'none' && fill && (fill[3] == null || fill[3] > 0)) return;
        if (parseFloat(cs.strokeWidth) < 1.5) return;
        const c = rgb(cs.stroke); if (!c) return;
        const num = (v) => (v === '' || v == null || isNaN(+v)) ? 1 : +v;
        const a = (c[3] == null ? 1 : c[3]) * num(cs.strokeOpacity) * num(cs.opacity);
        if (a < 0.05) return;   // прозрачная полоса захвата кривой — зона попадания, не линия
        const mix = [0, 1, 2].map(i => c[i] * a + bg[i] * (1 - a));
        const L1 = lum(mix), L2 = lum(bg);
        out.push({ name: p.getAttribute('data-curve') || p.getAttribute('class') || 'путь', c: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), stroke: cs.stroke, a });
      });
      return out;
    });
    r.forEach(x => {
      n++;
      if (x.c < worst.c) worst = Object.assign({ key, theme }, x);
      if (x.c < MIN) { bad++; console.log(`FAIL ${theme} ${key} · ${x.name}: ${x.c.toFixed(2)} : 1 (${x.stroke}, прозрачность ${x.a})`); }
    });
  }
  await ctx.close();
}
await browser.close();
console.log(`линий ${n}, ниже ${MIN} : 1 — ${bad}; худшая: ${worst.theme || ''} ${worst.key || ''} · ${worst.name || ''} ${worst.c ? worst.c.toFixed(2) : ''} : 1`);
process.exit(bad || !n ? 1 : 0);
