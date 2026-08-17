// Снимок сцены для глазной проверки: node calc2/tests/shot.mjs <сцена> [файл] [тема]
import { chromium } from 'playwright';
const BASE = 'http://127.0.0.1:8099';
const scene = process.argv[2] || 'sd';
const out = process.argv[3] || 'reports/calc2_night/shot.png';
const theme = process.argv[4] || 'light';
const browser = await chromium.launch();
const page = await browser.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin');
await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
await page.evaluate(k => pickScene(k), scene);
await page.waitForTimeout(700);
const geom = await page.evaluate(() => ({
  W, H, margin: { ...CONFIG.margin },
  plotW: W - CONFIG.margin.left - CONFIG.margin.right,
  plotH: H - CONFIG.margin.top - CONFIG.margin.bottom,
}));
console.log(JSON.stringify(geom));
if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 5).join(' | '));
await page.screenshot({ path: out });
await browser.close();
