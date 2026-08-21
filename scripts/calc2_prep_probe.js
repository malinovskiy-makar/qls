/* ФАЗА 0 / 4.1 сессии 22.08 — матрица разбора формулы.

   Прогоняет один и тот же список строк через prepExpr / freeSymbols /
   compilePpf на живой странице. Ничего не чинит и ничего не набирает:
   это снимок состояния разбора ДО и ПОСЛЕ правки.

   Запуск: node scripts/calc2_prep_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8710';
const OUT  = process.argv[3] || 'reports/calc2_22aug/prep_before.json';
const BASE = `http://127.0.0.1:${PORT}`;

const CASES = [
  '100-2x',
  '100-ax',
  '100-a*x',
  '100-a\\cdot x',
  'y=100-a\\cdot x',
  '\\frac{100}{x}',
  '100-a\\times x',
  '\\left(100-x\\right)',
  '100-a\\cdot x^{2}',
  '\\sqrt{100-x}',
];

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const KEY = process.argv[4] || 'ppf';
  // Неизвестный ключ сцены калькулятор молча уводит на «Спрос и предложение»
  // (девятый способ, которым врёт прибор): сверяем ключ ДО открытия.
  const known = await page.evaluate(() => Object.keys(SCENE_ROUTE || {}));
  if (!known.includes(KEY)) { console.error('НЕТ ТАКОГО КЛЮЧА СЦЕНЫ: ' + KEY); process.exit(2); }
  await page.evaluate(k => pickScene(k), KEY);
  await page.waitForTimeout(800);

  const rows = await page.evaluate((cases) => cases.map(s => {
    const r = { src: s };
    try { r.prep = prepExpr(s); } catch (e) { r.prep = 'THROW: ' + e.message; }
    try { r.free = freeSymbols(s); } catch (e) { r.free = 'THROW: ' + e.message; }
    try { const c = compilePpf(s); r.ppf = c.error || 'ok'; } catch (e) { r.ppf = 'THROW: ' + e.message; }
    try { const p = parsePpfEquation(s); r.eq = p.error || p.kind; } catch (e) { r.eq = 'THROW: ' + e.message; }
    return r;
  }), CASES);

  fs.mkdirSync(require('path').dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(rows, null, 2), 'utf8');
  rows.forEach(r => console.log(
    r.src.padEnd(22), '| prep:', String(r.prep).padEnd(20),
    '| free:', JSON.stringify(r.free).padEnd(12),
    '| ppf:', String(r.ppf).slice(0, 34).padEnd(34),
    '| eq:', String(r.eq).slice(0, 30)));
  await browser.close();
})();
