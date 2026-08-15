/**
 * Съёмка всех тронутых экранов ревью 15.08: светлая, тёмная, 380 пикселей.
 * ⚠️ СВЕРЯЕТ КОД ОТВЕТА: снимок страницы с 403-й ошибкой «успешно» показал бы
 * пустоту (урок сессии 4).
 * Запуск ИЗ КОРНЯ: node scripts/r15_shots.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
const OUT = path.join('reports', 'review');

const PAGES = [
  ['/teacher/groups/', 'ученики'],
  ['/teacher/groups/2/', 'занятие-обзор'],
  ['/teacher/groups/2/?tab=assignments', 'занятие-задания'],
  ['/teacher/groups/2/assignments/6/', 'задание'],
  ['/teacher/groups/2/assignments/6/submissions/', 'сводка'],
  ['/teacher/groups/2/assignments/6/students/9/', 'разбор'],
  ['/teacher/groups/2/assignments/6/students/9/done/', 'итоги'],
  ['/teacher/student/11/progress/', 'карточка-ученика'],
  ['/teacher/assignment/create/?group=2', 'искать-самому'],
  ['/teacher/assignment/build/?group=2', 'конструктор-подборки'],
  ['/teacher/problems/', 'мои-задачи'],
  ['/teacher/problems/new/', 'своя-задача'],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let bad = 0;
  for (const [theme, width, prefix] of [
    ['light', 1440, 'р15-'],
    ['dark', 1440, 'р15-тёмная-'],
    ['light', 380, 'р15-380-'],
  ]) {
    const ctx = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/login/`);
    await page.fill('input[name=username]', 'tutor@test.local');
    await page.fill('input[name=password]', 'demo12345');
    await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
    await page.evaluate((t) => localStorage.setItem('theme', t), theme);
    for (const [url, name] of PAGES) {
      const r = await page.goto(BASE + url, { waitUntil: 'networkidle' });
      if (!r || r.status() !== 200) {
        console.log('  - код', r && r.status(), url); bad += 1; continue;
      }
      await page.screenshot({
        path: path.join(OUT, `${prefix}${name}.png`), fullPage: true });
    }
    await ctx.close();
    console.log(`снято: ${theme} ${width}px`);
  }
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
