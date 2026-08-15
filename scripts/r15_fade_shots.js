/** Снимки краёв: прокручиваем теплокарту наполовину и снимаем в двух темах. */
const { chromium } = require('playwright');
const path = require('path');
const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 800 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  for (const theme of ['light', 'dark']) {
    await page.evaluate((t) => localStorage.setItem('theme', t), theme);
    await page.goto(`${BASE}/teacher/groups/2/`, { waitUntil: 'networkidle' });
    const box = await page.$('.fade-box');
    // Середина: видны оба края.
    await page.evaluate(() => {
      const sc = document.querySelector('.fade-box').firstElementChild;
      sc.scrollLeft = Math.round((sc.scrollWidth - sc.clientWidth) / 2);
    });
    await page.waitForTimeout(300);
    await box.screenshot({ path: path.join('reports', 'review',
      `р15-ф5-края-${theme}.png`) });
    console.log('ok', theme);
  }
  await browser.close();
})();
