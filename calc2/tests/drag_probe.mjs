// Замер Фазы 4 (Б32, Б33): сколько раз считается функция TC за одно
// перетаскивание линии цены длиной 200 пикселей и сколько раз пересобирается
// холст. Печатает числа «до/после» в одном формате.
//   node calc2/tests/drag_probe.mjs
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

const r = await page.evaluate(async () => {
  resetSceneMemory();
  pickScene('costs');
  STATE.lrOn = true; STATE.lrPrice = 20;
  redrawAll();

  /* Счётчики. Считать вызовы самого evaluate нельзя: recomputeCosts
     компилирует формулу заново, и подменённый объект теряется после первой же
     перерисовки. Считаем сканы minOf (каждый — 2400 вычислений формулы) и
     полные пересборки холста. */
  let scans = 0, rebuilds = 0, recompiles = 0;
  const realMinOf = window.minOf;
  window.minOf = function () { scans++; return realMinOf.apply(this, arguments); };
  const realRecompute = window.recomputeCosts;
  window.recomputeCosts = function () { recompiles++; return realRecompute.apply(this, arguments); };
  const realRedraw = window.redrawCosts;
  window.redrawCosts = function () { rebuilds++; return realRedraw.apply(this, arguments); };

  // Тянем цену на 200 пикселей: 100 шагов, как даёт настоящая мышь.
  const sc = mainScales();
  const y0 = sc.my(20);
  const t0 = performance.now();
  if (typeof beginLrDrag === 'function') beginLrDrag();
  for (let i = 1; i <= 100; i++) {
    const p = sc.my.invert(y0 - 200 * i / 100);
    (typeof dragLrPrice === 'function' ? dragLrPrice : setLrPrice)(p);
  }
  if (typeof endLrDrag === 'function') endLrDrag();
  const ms = performance.now() - t0;

  return { scans, recompiles, rebuilds, ms: Math.round(ms), price: STATE.lrPrice, Q: (STATE.lr || {}).Q };
});

await browser.close();
console.log('сканов minOf (по 2400 вычислений формулы каждый): ' + r.scans +
            '  =>  вычислений TC около ' + (r.scans * 2400).toLocaleString('ru-RU'));
console.log('перекомпиляций формулы TC:      ' + r.recompiles);
console.log('полных пересборок сцены:        ' + r.rebuilds);
console.log('время, мс:                      ' + r.ms);
console.log('цена после перетаскивания:      ' + r.price + ', выпуск ' + (r.Q == null ? 'нет' : r.Q.toFixed(2)));
