// Скорость по всем сценам (фаза 5, пункты А1, А2, А7, А55, А56).
// Меряет: первый вход, повторный вход (прогретый кэш), перерисовку,
// число полей MathLive и полей ввода в разметке.
// Порог (решение штаба от 13.08): открытие 300 мс, перерисовка 100 мс.
// Запуск: node calc2/tests/speed_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const OPEN_MS = +(process.env.OPEN_MS || 300);
const DRAW_MS = +(process.env.DRAW_MS || 100);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);

const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
// Первый вход считаем по порядку списка, каждую сцену открываем впервые.
const first = {};
for (const k of keys) {
  first[k] = await page.evaluate((key) => {
    const t = performance.now();
    pickScene(key);
    return performance.now() - t;
  }, k);
}
// Повторный вход и перерисовка — на прогретом кэше, берём лучшее из трёх.
const rows = [];
for (const k of keys) {
  const r = await page.evaluate((key) => {
    const best = (fn) => { let m = Infinity; for (let i = 0; i < 3; i++) { const t = performance.now(); fn(); m = Math.min(m, performance.now() - t); } return m; };
    pickScene(key);
    const open = best(() => pickScene(key));
    const draw = best(() => redrawAll());
    return {
      open, draw,
      mf: document.querySelectorAll('math-field').length,
      inputs: document.querySelectorAll('input, select, textarea').length,
    };
  }, k);
  rows.push([k, r]);
}
await browser.close();

let slowOpen = 0, slowDraw = 0;
console.log('сцена          первый  повтор  перерисовка  MathLive  полей');
rows.forEach(([k, r]) => {
  const bad = r.open > OPEN_MS || r.draw > DRAW_MS;
  if (r.open > OPEN_MS) slowOpen++;
  if (r.draw > DRAW_MS) slowDraw++;
  console.log(
    (bad ? '! ' : '  ') + k.padEnd(14) +
    String(Math.round(first[k])).padStart(6) +
    String(Math.round(r.open)).padStart(8) +
    String(Math.round(r.draw)).padStart(13) +
    String(r.mf).padStart(10) + String(r.inputs).padStart(7)
  );
});
console.log(`\nСверх порога: открытие ${slowOpen}, перерисовка ${slowDraw} (из ${rows.length})`);
process.exit(slowOpen || slowDraw ? 1 : 0);
