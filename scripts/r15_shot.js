/** Снимок куска страницы по селектору: node scripts/r15_shot.js порт url селектор имя [тема] */
const { chromium } = require('playwright');
const path = require('path');
const [, , PORT, URL, SEL, NAME, THEME = 'light', W = '1440'] = process.argv;
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: Number(W), height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${PORT}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  await page.evaluate((t) => localStorage.setItem('theme', t), THEME);
  await page.goto(`http://127.0.0.1:${PORT}${URL}`, { waitUntil: 'networkidle' });
  const el = await page.$(SEL);
  if (!el) { console.log('нет элемента', SEL); await browser.close(); return; }
  await el.screenshot({ path: path.join('reports', 'review', `р15-${NAME}.png`) });
  console.log('ok', NAME);
  await browser.close();
})();
