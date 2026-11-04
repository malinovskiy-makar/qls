// Фикстура «старого сохранения» (фаза −1 сессии 7): на коде старта (сервер 8098, b4152f73) в «Налогах и субсидиях»
// две свои точки и площадь «Между точками» по трём вершинам; плюс второй снимок — с недонабранной площадью (две
// вершины в STATE.areaVerts). Сохраняет автосохранение модели и ссылку «Поделиться».
//   node claude/panels_s7/make_fixture.mjs [base] [out.json]
import { chromium } from 'playwright';
import fs from 'fs';
const BASE = process.argv[2] || 'http://127.0.0.1:8098';
const OUT = process.argv[3] || 'claude/panels_s7/fixtures/old_taxes_pts.json';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
await page.goto(BASE + '/calc2/?m=taxes', { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const px = (x, y) => page.evaluate(([x, y]) => {
  const { mx, my } = mainScales(null); const r = document.getElementById('chart').getBoundingClientRect();
  return [r.left + mx(x), r.top + my(y)];
}, [x, y]);
const clickAt = async (x, y) => { const [cx, cy] = await px(x, y); await page.mouse.click(cx, cy); await page.waitForTimeout(1100); };
await page.click('#tool-pts'); await page.waitForTimeout(500);
// Две точки: на спросе при Q = 20 и в пустом месте (70; 20).
await clickAt(20, 80);
await clickAt(70, 20);
// Площадь «Между точками» по трём вершинам: углы клина налога и пересечение D и S.
await page.click('#ac-poly'); await page.waitForTimeout(600);
await clickAt(40, 60); await clickAt(40, 40); await clickAt(50, 50);
await page.click('#cv-mode-stop'); await page.waitForTimeout(1500);
const done = await page.evaluate(async () => ({
  autosave: localStorage.getItem('calc2.v1.model.taxes'),
  link: await shareLinkOf(),
  marks: STATE.marks.map(m => ({ id: m.id, text: m.text, x: m.x, y: m.y, on: markOnText(m) })),
  areas: STATE.areaCalcList.map(r => ({ label: r.label, kind: r.kind, value: r.value, ring: r.ring })),
  counters: { mark: markCounter, area: areaCalcCounter },
}));
// Недонабранная площадь: «Между точками», две вершины, без «Готово».
await page.click('#ac-poly'); await page.waitForTimeout(600);
await clickAt(10, 30); await clickAt(30, 10);
await page.waitForTimeout(1500);
const pending = await page.evaluate(async () => ({
  autosave: localStorage.getItem('calc2.v1.model.taxes'),
  link: await shareLinkOf(),
  areaVerts: STATE.areaVerts, areaCalcMode: STATE.areaCalcMode,
}));
fs.writeFileSync(OUT, JSON.stringify({ base: BASE, made: new Date().toISOString(), code: 'b4152f73', done, pending, errors }, null, 1));
console.log(JSON.stringify({ marks: done.marks, areas: done.areas, counters: done.counters, pendingVerts: pending.areaVerts, errors }, null, 1));
await browser.close();
