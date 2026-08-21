// Фаза 5, пункт 3 — в режиме выбора вершин площади своя точка должна
// захватываться так же надёжно, как ключевая точка. Сначала числом
// воспроизводим промах, потом чиним.
//   node calc2/tests/phase5_vertex_snap_probe.mjs
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

await page.evaluate(() => {
  resetSceneMemory(); pickScene('sd');
  // Своя точка НЕ на кривой и не в пересечении — единственный кандидат её найти это snapVertexAt.
  STATE.marks = [{ x: 22, y: 71, name: '' }];
  STATE.areaVerts = [];
  armVerts(true);
  redrawAll();
});
await page.waitForTimeout(200);

const geom = await page.evaluate(() => {
  const s = mainScales();
  const rect = document.getElementById('chart').getBoundingClientRect();
  const mk = STATE.marks[0];
  return { px: rect.left + s.mx(mk.x), py: rect.top + s.my(mk.y), dataX: mk.x, dataY: mk.y };
});

// Щёлкаем на 5 px в сторону от истинного центра своей точки — реалистичный промах руки.
const OFFSET = 5;
await page.mouse.click(geom.px + OFFSET, geom.py - OFFSET);
await page.waitForTimeout(150);

const result = await page.evaluate(({ dataX, dataY }) => {
  const s = mainScales();
  const v = (STATE.areaVerts || [])[0];
  if (!v) return { placed: false };
  const missPx = Math.hypot(s.mx(v.x) - s.mx(dataX), s.my(v.y) - s.my(dataY));
  return { placed: true, vx: v.x, vy: v.y, missPx: Math.round(missPx * 100) / 100 };
}, { dataX: geom.dataX, dataY: geom.dataY });

console.log('своя точка (данные):', geom.dataX, geom.dataY);
console.log('щёлкнули с промахом', OFFSET, 'px от центра точки');
console.log('поставленная вершина:', JSON.stringify(result));

report('вершина легла ТОЧНО на свою точку (промах ~0 px), а не на щелчок', result.placed && result.missPx < 1, JSON.stringify(result));

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'своя точка захватывается точно' : 'ПОДТВЕРЖДЁН ПРОМАХ — своя точка не захватывается'));
process.exit(ok ? 0 : 1);
