/**
 * Съёмка тронутых экранов второй сессии объединённого ревью 15.08
 * (фазы 7–15): обе темы плюс 380 пикселей.
 *
 * ⚠️ СВЕРЯЕТ КОД ОТВЕТА. Первая версия такого сценария в сессии 4 «успешно»
 * снимала страницы 403 и мерила ширину страницы ошибки.
 *
 * Запуск: node scripts/r15b_shots.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = 'reports/review';

const SCREENS = [
  ['ф7-задание', '/teacher/groups/2/assignments/6/'],
  ['ф7-разбор', '/teacher/groups/2/assignments/6/students/9/'],
  ['ф7-итоги', '/teacher/groups/2/assignments/6/students/9/done/'],
  ['ф8-карточка-ученика', '/teacher/student/11/progress/'],
  ['ф8-карточка-месяц', '/teacher/student/11/progress/?period=month'],
  ['ф10-создание', '/teacher/assignment/create/?group=2'],
  ['ф11-мои-задачи', '/teacher/problems/'],
  ['ф11-своя-задача', '/teacher/problems/new/'],
  ['ф11-ученики', '/teacher/groups/'],
  ['ф12-подборка', '/teacher/assignment/build/?group=2'],
  ['ф14-лист-учителю', '/teacher/groups/2/assignments/6/print/?for=teacher'],
  ['ф14-лист-ученику', '/teacher/groups/2/assignments/6/print/'],
  ['ф15-занятие-группа', '/teacher/groups/2/'],
  ['ф15-занятие-один', '/teacher/groups/3/'],
];

let shots = 0, bad = 0;

async function login(page) {
  await page.goto(BASE + '/login/');
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
}

(async () => {
  if (!fs.existsSync(OUT)) { fs.mkdirSync(OUT, { recursive: true }); }
  const browser = await chromium.launch();

  for (const [theme, width, tag] of
       [['light', 1440, 'светлая'], ['dark', 1440, 'тёмная'],
        ['light', 380, '380']]) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 } });
    const page = await context.newPage();
    await login(page);
    await page.addInitScript(t => {
      try { localStorage.setItem('theme', t); } catch (e) {}
    }, theme);

    for (const [name, url] of SCREENS) {
      const response = await page.goto(BASE + url, { waitUntil: 'networkidle' });
      const code = response ? response.status() : 0;
      if (code !== 200) {
        bad += 1;
        console.log(`  ПРОПУСК ${name} (${tag}): код ${code}`);
        continue;
      }
      await page.waitForTimeout(250);
      await page.screenshot({
        path: `${OUT}/р15б-${name}-${tag}.png`, fullPage: true });
      shots += 1;
    }
    await context.close();
  }

  await browser.close();
  console.log(`\nСнимков: ${shots}, пропущено по коду ответа: ${bad}`);
  process.exit(bad ? 1 : 0);
})();
