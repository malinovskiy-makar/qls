/** Замер выравнивания столбцов: центр заголовка против центра значений. */
const { chromium } = require('playwright');
const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
const PAGES = [
  ['/teacher/groups/2/', '#students-table', 'Ученики'],
  ['/teacher/groups/2/', '#group-works-table', 'История работ (занятие)'],
  ['/teacher/student/11/progress/', '#student-works-table', 'История работ (ученик)'],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  for (const [url, sel, name] of PAGES) {
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    const data = await page.evaluate((sel) => {
      const table = document.querySelector(sel);
      if (!table) return null;
      const heads = [...table.querySelectorAll('thead th')];
      const rows = [...table.querySelectorAll('tbody tr')];
      // Центр «чернил» — середина клиентского прямоугольника текста.
      const inkCenter = (cell) => {
        const range = document.createRange();
        range.selectNodeContents(cell);
        const r = range.getBoundingClientRect();
        return r.width ? r.left + r.width / 2 : null;
      };
      return heads.map((th, i) => {
        const values = rows.map((tr) => tr.children[i])
          .filter(Boolean).map(inkCenter).filter((v) => v !== null);
        const hc = inkCenter(th);
        return {
          столбец: th.textContent.replace(/\s+/g, ' ').trim().slice(0, 22),
          тип: th.dataset.type || '—',
          сдвиг: values.length && hc !== null
            ? Math.round(Math.max(...values.map((v) => Math.abs(v - hc))))
            : null,
        };
      });
    }, sel);
    console.log(`\n${name}`);
    (data || []).forEach((c) => console.log(
      `  ${c.тип.padEnd(5)} ${String(c.столбец).padEnd(24)} расхождение центров: ${c.сдвиг} px`));
  }
  await browser.close();
})();
