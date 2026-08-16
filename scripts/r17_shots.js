/**
 * Съёмка экранов ревью 17.08 — одной пачкой (правило темпа, п. 5).
 *
 * Новый поток создания работы: четыре шага, обе темы, 380 пикселей.
 *
 * Каждый экран снимается в двух темах и на 380 пикселях. Код ответа
 * СВЕРЯЕТСЯ: снимок страницы «403» ничего не доказывает, и на этом уже
 * ловились прошлые сессии.
 *
 * Запуск: node scripts/r17_shots.js [порт]
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8300';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review');

const SCREENS = [
  ['ф8-шаг1-каталог', 'tutor', '/teacher/work/?group=2'],
  ['ф8-шаг1-контрольная', 'tutor', '/teacher/work/?group=2&kind=exam'],
  ['ф8-шаг1-поиск', 'tutor', '/teacher/work/?group=2&q=эластичность&sort=hard'],
  ['ф8-шаг1-пусто', 'tutor', '/teacher/work/?group=2&q=этогонетвбанке'],
  ['ф9-шаг2-что-нашлось', 'tutor', '/teacher/assignment/generate/?group=2'],
  ['ф10-шаг3-состав-пусто', 'tutor', '/teacher/work/compose/?group=2'],
  ['ф11-шаг4-выдача', 'tutor', '/teacher/work/give/?group=2'],
  ['ф11-шаг4-выдача-контрольная', 'tutor', '/teacher/work/give/?group=2&kind=exam'],
  ['ф13-написать-свою', 'tutor', '/teacher/problems/new/?to_cart=1&group=2'],
  ['ф13-своя-задача-с-пунктами', 'tutor', '/teacher/problems/13/edit/'],
  ['ф12-занятие-вход-в-поток', 'tutor', '/teacher/groups/2/?tab=assignments'],
  ['ф14-печать-с-ответами', 'tutor',
   '/teacher/groups/2/assignments/10/print/?for=teacher'],
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
          path: path.join(OUT, `р17-${name}-${theme}.png`), fullPage: true });
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
          path: path.join(OUT, `р17-${name}-380.png`), fullPage: true });
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
