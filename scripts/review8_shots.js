/**
 * Съёмка тронутых экранов сессии 8: светлая и тёмная тема, 1440 и 380px.
 *
 * ⚠️ КАЖДЫЙ КАДР СВЕРЯЕТ КОД ОТВЕТА. Страница ошибки тоже отдаёт разметку,
 * и без этой сверки съёмка молча меряет ширину чужого экрана.
 * ⚠️ Старую поломку навигации (`_nav.html` тянет страницу вбок на 380px)
 * не чиним — она есть на КАЖДОЙ странице сайта, включая нетронутые;
 * меряем СОДЕРЖИМОЕ (`main`), а не документ целиком.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/review8_shots.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review', 'сессия8');

const SCREENS = [
  ['конструктор-подборки', '/teacher/assignment/build/?kind=homework&group=2'],
  ['обзор-группы', '/teacher/groups/2/'],
  ['своя-задача', '/teacher/problems/new/'],
  ['ручной-поиск', '/teacher/assignment/create/'],
  ['глазами-ученика', '/teacher/groups/2/assignments/6/students/9/'],
  ['экран-проверки', '/teacher/groups/2/submissions/112/'],
  ['витрина', '/teacher/styleguide/'],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let bad = 0;

  for (const scheme of ['light', 'dark']) {
    for (const [width, tag] of [[1440, '1440'], [380, '380']]) {
      const ctx = await browser.newContext({
        viewport: { width, height: 1000 }, colorScheme: scheme,
      });
      const page = await ctx.newPage();
      await page.addInitScript((mode) => {
        try { localStorage.setItem('theme', mode); } catch (e) {}
      }, scheme);
      await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
      await page.fill('input[name=username]', 'tutor@test.local');
      await page.fill('input[name=password]', 'demo12345');
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        page.click('button[type=submit]'),
      ]);

      for (const [name, url] of SCREENS) {
        const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
        if (resp.status() !== 200) {
          console.log(`✗ ${name} ${scheme} ${tag}: КОД ${resp.status()}`);
          bad += 1;
          continue;
        }
        await page.waitForTimeout(700);
        const wide = await page.evaluate(() => {
          const main = document.querySelector('main') || document.body;
          return { content: main.scrollWidth, view: window.innerWidth };
        });
        const over = wide.content > wide.view + 2;
        if (over && tag === '380') {
          console.log(`✗ ${name} ${scheme} ${tag}: содержимое ${wide.content}px при окне ${wide.view}px`);
          bad += 1;
        }
        await page.screenshot({
          path: path.join(OUT, `${name}-${scheme}-${tag}.png`),
          fullPage: tag === '1440',
        });
      }
      await ctx.close();
    }
  }

  console.log(bad ? `\nнеудачных кадров: ${bad}` : '\nвсе кадры сняты, вылетов вбок нет');
  console.log('снимки:', OUT);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
