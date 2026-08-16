/**
 * Съёмка экранов ревью 16.08 — одной пачкой (правило темпа, п. 5).
 *
 * Каждый экран снимается в двух темах и на 380 пикселях. Код ответа
 * СВЕРЯЕТСЯ: снимок страницы «403» ничего не доказывает, и на этом уже
 * ловились прошлые сессии.
 *
 * Запуск: node scripts/r16_shots.js [порт]
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8211';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review');

const SCREENS = [
  ['ф1-задание-своя-задача', 'tutor', '/teacher/groups/4/assignments/26/'],
  ['ф1-печать-ученику', 'tutor',
   '/teacher/groups/4/assignments/26/print/?for=student'],
  ['ф3-настройки-даты', 'tutor', '/teacher/assignment/create/?group=2'],
  ['ф4-статистика-активность', 'student', '/profile/stats/'],
  ['ф6-обзор-занятия', 'tutor', '/teacher/groups/2/'],
  ['ф6-карточка-ученика', 'tutor', '/teacher/student/9/progress/'],
  ['ф6-каталог-таблица', 'tutor', '/catalog/?view=table&difficulty=3'],
  ['ф7-мои-задачи', 'tutor', '/teacher/problems/'],
  ['ф7-редактор-своей-задачи', 'tutor', '/teacher/problems/14/edit/'],
];

const WHO = { tutor: 'tutor@test.local', student: 'student1@test.local' };

async function login(context, who) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', who);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  return page;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const problems = [];
  let shots = 0;

  for (const role of ['tutor', 'student']) {
    // ⚠️ Роли — РАЗНЫЕ контексты браузера: вкладки делят куки, и вход
    // учеником выбивал бы сессию репетитора (урок сессии 9).
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 } });
    const page = await login(context, WHO[role]);

    for (const [name, needs, url] of SCREENS) {
      if (needs !== role) { continue; }
      for (const theme of ['light', 'dark']) {
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((value) => {
          try { localStorage.setItem('theme', value); } catch (e) {}
        }, theme);
        // ⚠️ `goto` отдаёт null, если браузер не делал запроса (тот же
        // адрес). Тогда код ответа брать неоткуда — считаем страницу той
        // же самой, что и была.
        const res = await page.goto(BASE + url, { waitUntil: 'networkidle' });
        if (res && res.status() !== 200) {
          problems.push(`${name} (${theme}): код ${res.status()}`);
          continue;
        }
        await page.evaluate((value) => {
          document.documentElement.setAttribute('data-theme', value);
        }, theme);
        await page.waitForTimeout(500);
        await page.screenshot({
          path: path.join(OUT, `р16-${name}-${theme}.png`), fullPage: true });
        shots += 1;
      }
      // Узкий экран — только светлая тема: проверяем укладку, не цвет.
      await page.setViewportSize({ width: 380, height: 900 });
      await page.evaluate(() => {
        document.documentElement.setAttribute('data-theme', 'light');
      });
      const narrow = await page.goto(BASE + url, { waitUntil: 'networkidle' });
      if (!narrow || narrow.status() === 200) {
        await page.waitForTimeout(400);
        await page.screenshot({
          path: path.join(OUT, `р16-${name}-380.png`), fullPage: true });
        shots += 1;
      }
      await page.setViewportSize({ width: 1440, height: 1100 });
    }
    await context.close();
  }

  await browser.close();
  console.log(`Снимков: ${shots}`);
  if (problems.length) {
    console.log('НЕ СНЯТО (код ответа не 200):');
    problems.forEach((p) => console.log('  ✗ ' + p));
    process.exit(1);
  }
})();
