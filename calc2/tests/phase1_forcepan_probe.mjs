// Фаза 1 — «не сломай»: сдвиг поля правой кнопкой / с зажатым Shift даже
// начатый ПРЯМО НА ручке манипулятора, и двойной щелчок сбрасывает вид.
//   node calc2/tests/phase1_forcepan_probe.mjs
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

await page.evaluate(() => { resetSceneMemory(); pickScene('tax'); });
await page.waitForTimeout(200);
const handle = await page.evaluate(() => {
  const r = Array.from(document.querySelectorAll('svg#chart rect')).find(r => getComputedStyle(r).cursor === 'grab').getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
});

// --- правая кнопка прямо на ручке манипулятора двигает поле --------------
{
  const before = await page.evaluate(() => [sx.domain()[0], sx.domain()[1], STATE.tax]);
  await page.mouse.move(handle.x, handle.y);
  await page.mouse.down({ button: 'right' });
  for (let i = 1; i <= 15; i++) await page.mouse.move(handle.x - 100 * i / 15, handle.y);
  await page.mouse.up({ button: 'right' });
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => [sx.domain()[0], sx.domain()[1], STATE.tax]);
  report('правая кнопка на ручке двигает поле', Math.abs(after[0] - before[0]) > 1e-6,
    `domain ${before[0].toFixed(1)}->${after[0].toFixed(1)}`);
  report('правая кнопка на ручке НЕ меняет ставку (d3-drag её не видит)', Math.abs(after[2] - before[2]) < 1e-6,
    `tax ${before[2]}->${after[2]}`);
}

// --- Shift + левая кнопка прямо на ручке манипулятора двигает поле -------
await page.evaluate(() => { resetSceneMemory(); pickScene('tax'); });
await page.waitForTimeout(200);
const handle2 = await page.evaluate(() => {
  const r = Array.from(document.querySelectorAll('svg#chart rect')).find(r => getComputedStyle(r).cursor === 'grab').getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
});
{
  const before = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  await page.keyboard.down('Shift');
  await page.mouse.move(handle2.x, handle2.y);
  await page.mouse.down();
  for (let i = 1; i <= 15; i++) await page.mouse.move(handle2.x - 100 * i / 15, handle2.y);
  await page.mouse.up();
  await page.keyboard.up('Shift');
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  report('Shift + левая кнопка на ручке двигает поле', Math.abs(after[0] - before[0]) > 1e-6,
    `domain ${before[0].toFixed(1)}->${after[0].toFixed(1)}`);
}

// --- двойной щелчок сбрасывает вид ----------------------------------------
{
  const panned = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  await page.mouse.dblclick(handle2.x + 120, handle2.y - 150);
  await page.waitForTimeout(150);
  const after = await page.evaluate(() => [sx.domain()[0], sx.domain()[1], CONFIG.Qmin, CONFIG.Qmax]);
  report('двойной щелчок сбрасывает вид', Math.abs(after[0] - after[2]) < 1e-6 && Math.abs(after[1] - after[3]) < 1e-6,
    `было ${panned.map(v=>v.toFixed(1))}, после сброса ${[after[0], after[1]].map(v=>v.toFixed(1))}, канон [${after[2]}, ${after[3]}]`);
}

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'всё цело' : 'ЕСТЬ РЕГРЕССИЯ'));
process.exit(ok ? 0 : 1);
