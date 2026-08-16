/**
 * Снимки НАПОЛНЕННЫХ шагов потока (ревью 17.08).
 *
 * ⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ПРОГОН. Корзина живёт в хранилище вкладки, и обычная
 * съёмка по списку адресов застаёт все шаги пустыми: на снимке «Состав»
 * стояло бы пустое состояние, то есть ровно то, чего владелец не просил
 * смотреть. Здесь сначала набирается работа, и только потом снимаются
 * экраны — в том виде, в каком их видит человек.
 *
 *   node scripts/r17_shots_full.js [порт]
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8300';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review');
const GROUP = 2;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  const bad = [];
  let shots = 0;

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  // Набираем работу: три задачи из каталога.
  const pick = await page.goto(`${BASE}/teacher/work/?group=${GROUP}`,
                               { waitUntil: 'networkidle' });
  if (!pick || pick.status() !== 200) { bad.push('отбор: код ответа'); }
  const adds = page.locator('#pane-catalog .wk-add');
  for (let i = 0; i < 3; i += 1) { await adds.nth(i).click(); }
  await page.waitForTimeout(900);

  async function shoot(name, url, prepare) {
    for (const theme of ['light', 'dark']) {
      const res = await page.goto(BASE + url, { waitUntil: 'networkidle' });
      if (res && res.status() !== 200) {
        bad.push(`${name} (${theme}): код ${res.status()}`);
        continue;
      }
      await page.evaluate((value) => {
        document.documentElement.setAttribute('data-theme', value);
      }, theme);
      await page.waitForTimeout(1100);
      if (prepare) { await prepare(page); }
      await page.screenshot({
        path: path.join(OUT, `р17-${name}-${theme}.png`), fullPage: true });
      shots += 1;
    }
    await page.setViewportSize({ width: 380, height: 900 });
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'light');
    });
    await page.waitForTimeout(1100);
    if (prepare) { await prepare(page); }
    await page.screenshot({
      path: path.join(OUT, `р17-${name}-380.png`), fullPage: true });
    shots += 1;
    await page.setViewportSize({ width: 1440, height: 1100 });
  }

  await shoot('ф8-шаг1-набрано', `/teacher/work/?group=${GROUP}`);
  await shoot('ф10-шаг3-состав', `/teacher/work/compose/?group=${GROUP}`);
  await shoot('ф10-шаг3-позиция-целиком',
              `/teacher/work/compose/?group=${GROUP}`,
              async (p) => {
                await p.locator('.wk-open').first().click();
                await p.waitForTimeout(700);
              });
  await shoot('ф11-шаг4-выдача-набрано', `/teacher/work/give/?group=${GROUP}`,
              async (p) => {
                await p.fill('[name=name]', 'Домашка 7 — издержки');
                await p.waitForTimeout(800);
              });

  await browser.close();
  console.log(`Снимков: ${shots}`);
  if (bad.length) {
    console.log('НЕ СНЯТО:');
    bad.forEach((b) => console.log('  ✗ ' + b));
    process.exit(1);
  }
})();
