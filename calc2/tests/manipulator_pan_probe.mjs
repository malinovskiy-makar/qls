// Фаза 0 (сессия 21.08, жесты): воспроизвести протяжку ручки налога РУКАМИ —
// то есть событиями УКАЗАТЕЛЯ, а не мышиными синтетическими событиями.
//
// page.mouse.* в Playwright/Chromium идёт через CDP Input.dispatchMouseEvent —
// это тот же путь, каким браузер получает вход от настоящего тачпада, поэтому
// движок сначала получает pointerdown/pointermove/pointerup, а из них уже
// синтезирует mousedown/mousemove/mouseup. dispatchEvent(new MouseEvent(...))
// из page.evaluate этот путь МИНУЕТ и pointer-событий не порождает вовсе —
// именно так три предыдущих замера дали ложное «не воспроизводится».
//
//   ./venv313/bin/python manage.py runserver 8099 --noreload
//   node calc2/tests/manipulator_pan_probe.mjs
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

const ready = await page.evaluate(() => typeof redrawAll === 'function' && typeof STATE === 'object');
if (!ready) { console.error('SKIP: функции calc2 не загрузились'); await browser.close(); process.exit(3); }

await page.evaluate(() => { resetSceneMemory(); pickScene('tax'); });
await page.waitForTimeout(200);

const before = await page.evaluate(() => ({
  tax: STATE.tax,
  dx: [sx.domain()[0], sx.domain()[1]],
  dy: [sy.domain()[0], sy.domain()[1]],
}));

// Находим ручку клина налога на экране: rect с курсором grab внутри #chart.
const handle = await page.evaluate(() => {
  const rects = Array.from(document.querySelectorAll('svg#chart rect'))
    .filter(r => getComputedStyle(r).cursor === 'grab');
  if (!rects.length) return null;
  const r = rects[0].getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2, count: rects.length };
});
if (!handle) { console.error('ФЕЙЛ ПРОБЫ: ручка налога не найдена на экране (rect с cursor:grab)'); await browser.close(); process.exit(2); }

// Протяжка на 150 px влево-вверх, 30 промежуточных шагов — настоящая мышь
// в Playwright шлёт события указателя с pointerId и isPrimary сама.
await page.mouse.move(handle.x, handle.y);
await page.mouse.down();
const STEPS = 30;
for (let i = 1; i <= STEPS; i++) {
  await page.mouse.move(handle.x - 150 * i / STEPS, handle.y - 150 * i / STEPS);
  await page.waitForTimeout(5);
}
await page.mouse.up();
await page.waitForTimeout(150);

const after = await page.evaluate(() => ({
  tax: STATE.tax,
  dx: [sx.domain()[0], sx.domain()[1]],
  dy: [sy.domain()[0], sy.domain()[1]],
}));

await browser.close();

const fmt = (v) => v.toFixed(3);
console.log('ручек с cursor:grab на холсте: ' + handle.count);
console.log('ставка (STATE.tax) до:    ' + fmt(before.tax));
console.log('ставка (STATE.tax) после: ' + fmt(after.tax));
console.log('sx.domain() до:    [' + before.dx.map(fmt).join(', ') + ']');
console.log('sx.domain() после: [' + after.dx.map(fmt).join(', ') + ']');
console.log('sy.domain() до:    [' + before.dy.map(fmt).join(', ') + ']');
console.log('sy.domain() после: [' + after.dy.map(fmt).join(', ') + ']');

const taxMoved = Math.abs(after.tax - before.tax) > 1e-6;
const domainMoved = Math.abs(after.dx[0] - before.dx[0]) > 1e-6 || Math.abs(after.dx[1] - before.dx[1]) > 1e-6 ||
                     Math.abs(after.dy[0] - before.dy[0]) > 1e-6 || Math.abs(after.dy[1] - before.dy[1]) > 1e-6;
console.log('\nИТОГ: ставка ' + (taxMoved ? 'изменилась' : 'НЕ изменилась') +
            '; окно ' + (domainMoved ? 'СДВИНУЛОСЬ (дефект воспроизведён)' : 'не сдвинулось (дефект не воспроизведён)'));
