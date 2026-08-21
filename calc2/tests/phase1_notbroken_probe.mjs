// Фаза 1 — проверка «не сломай» из карточки 21.08: сдвиг поля по пустому
// месту, щелчок по кривой (взвод ключевых точек) и прокатывание точки по
// кривой должны работать как прежде после того, как манипуляторы сцены
// перестали отдавать нажатие сдвигу поля.
//   node calc2/tests/phase1_notbroken_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let ok = true;
const report = (name, pass, detail) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + name + (detail ? '  -> ' + detail : '')); if (!pass) ok = false; };

// --- A: сдвиг поля по пустому месту -----------------------------------
await page.evaluate(() => { resetSceneMemory(); pickScene('sd'); });
await page.waitForTimeout(200);
{
  const before = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  // Точка в правом верхнем углу графика: выше D=100-Q и правее её пересечения
  // с осью — заведомо пустое место, не задетое ни кривой, ни линией сетки.
  const rect = await page.evaluate(() => { const r = document.getElementById('chart').getBoundingClientRect(); return { left: r.left, top: r.top }; });
  const sxy = await page.evaluate(() => ({ x: sx(85), y: sy(97) }));
  const px0 = rect.left + sxy.x, py0 = rect.top + sxy.y;
  const el = await page.evaluate(({ x, y }) => {
    const e = document.elementFromPoint(x, y);
    return e ? { tag: e.tagName, cursor: getComputedStyle(e).cursor } : null;
  }, { x: px0, y: py0 });
  report('точка A — заведомо фон', el && (el.tag === 'svg' || el.tag === 'rect' || el.tag === 'DIV'), JSON.stringify(el));
  await page.mouse.move(px0, py0);
  await page.mouse.down();
  for (let i = 1; i <= 20; i++) await page.mouse.move(px0 - 80 * i / 20, py0);
  await page.mouse.up();
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  report('пустое место сдвигает поле', Math.abs(after[0] - before[0]) > 1e-6, `domain ${before.map(v=>v.toFixed(1))} -> ${after.map(v=>v.toFixed(1))}`);
}

// --- B: щелчок по кривой взводит ключевые точки (STATE.armedCurve) ------
await page.evaluate(() => { resetSceneMemory(); pickScene('sd'); });
await page.waitForTimeout(200);
{
  const before = await page.evaluate(() => STATE.armedCurve);
  const p = await page.evaluate(() => {
    const rect = document.getElementById('chart').getBoundingClientRect();
    return { x: rect.left + sx(30), y: rect.top + sy(70) };   // на кривой D=100-Q
  });
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  await page.waitForTimeout(30);
  await page.mouse.up();
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => STATE.armedCurve);
  report('щелчок по кривой взводит ключевые точки', before == null && after === 'D', `armedCurve ${before} -> ${after}`);
}

// --- C: прокатывание точки по кривой ------------------------------------
await page.evaluate(() => { resetSceneMemory(); pickScene('sd'); });
await page.waitForTimeout(200);
{
  const p = await page.evaluate(() => {
    const rect = document.getElementById('chart').getBoundingClientRect();
    return { x: rect.left + sx(30), y: rect.top + sy(70) };   // на кривой D=100-Q
  });
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  for (let i = 1; i <= 15; i++) await page.mouse.move(p.x + i, p.y - i * 0.6);
  await page.waitForTimeout(50);
  const rolling = await page.evaluate(() => !!(STATE.roller && STATE.roller.pinned));
  await page.mouse.up();
  await page.waitForTimeout(100);
  const domainAfter = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  report('прокатывание точки по кривой запускается (STATE.roller)', rolling, `roller pinned=${rolling}`);
  report('прокатывание НЕ двигает поле', Math.abs(domainAfter[0] - 0) < 1e-6, `domain после ${domainAfter.map(v=>v.toFixed(1))}`);
}

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'всё цело' : 'ЕСТЬ РЕГРЕССИЯ'));
process.exit(ok ? 0 : 1);
