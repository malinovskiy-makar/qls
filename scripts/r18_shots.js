/**
 * Съёмка экранов ревью 17.08 (функциональная сессия) — одной пачкой.
 *
 * Семь фаз: баллы, числа, читаемость, остатки потока, блоки и
 * таблицы, общий блок активности, текст. Обе темы и 380 пикселей.
 *
 * Каждый экран снимается в двух темах и на 380 пикселях. Код ответа
 * СВЕРЯЕТСЯ: снимок страницы «403» ничего не доказывает, и на этом уже
 * ловились прошлые сессии.
 *
 * Запуск: node scripts/r18_shots.js [порт]
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8300';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review');

const SCREENS = [
  ['ф1-состав-баллы', 'tutor', '/teacher/work/compose/?group=2'],
  ['ф1-выдача-правило', 'tutor', '/teacher/work/give/?group=2'],
  ['ф1-выдача-контрольная', 'tutor', '/teacher/work/give/?group=2&kind=exam'],
  ['ф2-занятие-обзор', 'tutor', '/teacher/groups/2/?tab=overview'],
  ['ф2-сводка-решений', 'tutor', '/teacher/groups/2/assignments/6/submissions/'],
  ['ф2-разбор-работы', 'tutor', '/teacher/groups/2/assignments/6/students/9/'],
  ['ф2-задание-баллы', 'tutor', '/teacher/groups/2/assignments/6/'],
  ['ф3-статистика-ученика', 'student', '/profile/stats/'],
  ['ф3-своя-задача', 'tutor', '/teacher/problems/new/?to_cart=1&group=2'],
  ['ф4-шаг-что-нашлось', 'tutor', '/teacher/assignment/generate/?group=2'],
  ['ф4-шаг-что-кладём', 'tutor', '/teacher/work/?group=2'],
  ['ф5-занятие-задания', 'tutor', '/teacher/groups/2/?tab=assignments'],
  ['ф5-карточка-ученика', 'tutor', '/teacher/student/9/progress/'],
  ['ф6-активность-репетитор', 'tutor', '/teacher/student/9/progress/?period=month'],
  ['ф6-активность-ученик', 'student', '/profile/stats/?period=month'],
  ['ф7-разбор-глазами-ученика', 'student', '/student/work/6/'],
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
          path: path.join(OUT, `р18-${name}-${theme}.png`), fullPage: true });
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
          path: path.join(OUT, `р18-${name}-380.png`), fullPage: true });
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
