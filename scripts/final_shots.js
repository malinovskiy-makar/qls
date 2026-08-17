/*
 * Съёмка затронутых экранов завершающей сессии ревью 17.08.2026.
 * Светлая тема, тёмная и узкий экран 380 px.
 *
 * Запуск ИЗ КОРНЯ ПРОЕКТА:  node scripts/final_shots.js 8501
 * ⚠️ СВЕРЯЕМ КОД ОТВЕТА: первая версия подобной съёмки в сессии 4 снимала
 * страницу 403 и рапортовала об успехе.
 */
const fs = require('fs');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8501';
const BASE = 'http://127.0.0.1:' + PORT;
const OUT = 'reports/review/final';

const SHOTS = [
  ['solo-overview', '/teacher/groups/3/?tab=overview', 'tutor'],
  ['group-overview', '/teacher/groups/2/?tab=overview', 'tutor'],
  ['group-assignments', '/teacher/groups/2/?tab=assignments', 'tutor'],
  ['group-materials', '/teacher/groups/2/?tab=materials', 'tutor'],
  ['students-list', '/teacher/groups/', 'tutor'],
  ['student-card', '/teacher/student/11/progress/', 'tutor'],
  ['work-compose', '/teacher/work/compose/', 'tutor'],
  ['work-pick', '/teacher/work/', 'tutor'],
  ['student-stats', '/profile/stats/', 'student'],
];

async function login(browser, email, width) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(BASE + '/login/');
  await page.fill('input[name=username]', email);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  return page;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let bad = 0, made = 0;

  for (const [theme, width, suffix] of [['light', 1440, ''],
                                        ['dark', 1440, '-dark'],
                                        ['light', 380, '-380']]) {
    const pages = {
      tutor: await login(browser, 'tutor@test.local', width),
      student: await login(browser, 'student1@test.local', width),
    };
    for (const page of Object.values(pages)) {
      await page.evaluate(t => {
        localStorage.setItem('theme', t);
        document.documentElement.setAttribute('data-theme', t === 'dark' ? 'dark' : '');
      }, theme);
    }
    for (const [name, path, role] of SHOTS) {
      const page = pages[role];
      const response = await page.goto(BASE + path);
      if (response.status() !== 200) {
        console.log('  ✗ ' + name + suffix + ' — код ' + response.status());
        bad++;
        continue;
      }
      await page.waitForTimeout(350);
      await page.screenshot({ path: OUT + '/' + name + suffix + '.png',
                              fullPage: true });
      made++;
    }
    for (const page of Object.values(pages)) { await page.context().close(); }
  }

  console.log('снимков: ' + made + ', отказов: ' + bad);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
