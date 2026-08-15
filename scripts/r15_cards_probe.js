/** Замер: на одной ли линии значения четырёх карточек-показателей. */
const { chromium } = require('playwright');
const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
const PAGES = [
  ['/teacher/student/11/progress/', 'карточка ученика'],
  ['/teacher/groups/3/', 'занятие один на один'],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  for (const width of [1440, 380]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const [url, name] of PAGES) {
      await page.goto(BASE + url, { waitUntil: 'networkidle' });
      const tops = await page.$$eval('.card3-value',
        (nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().top)));
      const same = tops.length ? Math.max(...tops) - Math.min(...tops) : null;
      console.log(`${width}px ${name}: верх значений ${JSON.stringify(tops)}`
        + `, разброс ${same} px`);
    }
  }
  await browser.close();
})();
