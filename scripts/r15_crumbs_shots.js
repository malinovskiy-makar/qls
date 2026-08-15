/** Снимки крошек: три экрана × две темы, обрезка по верхней части. */
const { chromium } = require('playwright');
const path = require('path');
const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
const OUT = path.join('reports', 'review');
const PAGES = [
  ['/teacher/groups/2/assignments/6/submissions/', 'сводка'],
  ['/teacher/assignment/create/?group=3', 'конструктор'],
  ['/teacher/student/11/progress/', 'карточка'],
  ['/teacher/problems/', 'моизадачи'],
  ['/teacher/groups/2/assignments/6/students/9/', 'глазами'],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 800 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  for (const theme of ['light', 'dark']) {
    await page.evaluate((t) => localStorage.setItem('theme', t), theme);
    for (const [url, name] of PAGES) {
      await page.goto(BASE + url, { waitUntil: 'networkidle' });
      const box = await page.$('.crumbs');
      if (!box) { console.log('нет крошек:', url); continue; }
      const b = await box.boundingBox();
      await page.screenshot({
        path: path.join(OUT, `р15-крошки-${name}-${theme}.png`),
        clip: { x: Math.max(0, b.x - 12), y: Math.max(0, b.y - 10),
                width: Math.min(1100, b.width + 40), height: b.height + 22 },
      });
    }
  }
  await browser.close();
})();
