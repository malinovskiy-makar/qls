/**
 * Разведка глазами: замеряет то, что питон-тесты не видят.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/obzor_probe.js [порт]
 * Ничего не сохраняет — только читает и снимает.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  await page.goto(`${BASE}/teacher/groups/2/?tab=overview`,
    { waitUntil: 'networkidle' });

  // Растворение правого края теплокарты: есть ли оно и видно ли.
  const fade = await page.evaluate(() => {
    const box = document.querySelector('.fade-box');
    if (!box) return { нет: true };
    const after = getComputedStyle(box, '::after');
    const scroller = box.querySelector('.stats-table-wrap');
    return {
      ширина: after.width,
      фон: after.background.slice(0, 120),
      прозрачность: after.opacity,
      классКонца: box.className,
      прокрутка: scroller
        ? { видимая: scroller.clientWidth, полная: scroller.scrollWidth }
        : null,
    };
  });
  console.log('РАСТВОРЕНИЕ КРАЯ:', JSON.stringify(fade, null, 2));

  const surface = await page.evaluate(() => {
    const panel = document.querySelector('.fade-box').closest('.panel');
    return {
      панель: getComputedStyle(panel).backgroundColor,
      страница: getComputedStyle(document.body).backgroundColor,
      ячейка: getComputedStyle(
        document.querySelector('.stats-table td')).backgroundColor,
    };
  });
  console.log('ФОНЫ:', JSON.stringify(surface));

  await page.screenshot({
    path: path.join(SHOTS, 'обзор-теплокарта-до.png'),
    clip: await page.evaluate(() => {
      const box = document.querySelector('.fade-box').getBoundingClientRect();
      return { x: box.x, y: box.y + window.scrollY - 40,
               width: box.width, height: Math.min(box.height + 60, 400) };
    }),
  });

  // Подсказка на заголовке колонки.
  const head = await page.$('.stats-table th[data-hint]');
  if (head) {
    await head.hover();
    await page.waitForTimeout(200);
    const tip = await page.$eval('.k-tip', el =>
      ({ виден: !el.hidden, текст: el.textContent })).catch(() => null);
    console.log('ПОДСКАЗКА ЗАГОЛОВКА:', JSON.stringify(tip));
  }

  // Подсказка на клетке «по группе».
  const groupCell = await page.$('tr:last-child .matrix-cell[data-hint]');
  if (groupCell) {
    await groupCell.hover();
    await page.waitForTimeout(200);
    const tip = await page.$eval('.k-tip', el =>
      ({ виден: !el.hidden, текст: el.textContent })).catch(() => null);
    console.log('ПОДСКАЗКА «ПО ГРУППЕ»:', JSON.stringify(tip));
  }

  await browser.close();
})();
