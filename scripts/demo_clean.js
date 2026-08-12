/**
 * Витрина после `seed_platform_demo` — проверка ГЛАЗАМИ И ЧИСЛАМИ.
 *
 * ⚠️ Гоняется по БОЕВОЙ базе и НИЧЕГО не нажимает: только смотрит. Все
 * сохраняющие сценарии сессии работают по отдельной `db_check.sqlite3`
 * (`config/settings_check.py`), и этот прогон подтверждает, что следов от
 * них в витрине не осталось.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/demo_clean.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');

let ok = 0, bad = 0;
function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  ✓', name); }
  else { bad += 1; console.log('  ✗', name, extra === undefined ? '' : extra); }
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  let resp = await page.goto(`${BASE}/teacher/groups/2/`, { waitUntil: 'networkidle' });
  check('обзор группы (200)', resp.status() === 200, resp.status());
  const works = await page.$$eval('.wk-table tbody tr',
    (rows) => rows.map((r) => r.querySelector('.wk-name').textContent.trim()));
  // ⚠️ Ищем ИМЕНА, которые создают сценарии ЭТОЙ сессии. Работы прежних
  // сессий («Домашка тест торговля», «Контрольная 67») лежали в базе до
  // неё — их удаление к чистоте витрины отношения не имеет и решается
  // владельцем, а не сценарием.
  check('в истории работ нет следов сценариев сессии 8',
        !works.some((w) => /Проверка связки|Сквозная работа сессии/.test(w)),
        JSON.stringify(works));
  await page.screenshot({ path: path.join(SHOTS, 'ф10-витрина-обзор-группы.png'),
                          fullPage: true });

  resp = await page.goto(`${BASE}/teacher/groups/2/assignments/6/submissions/`,
                         { waitUntil: 'networkidle' });
  check('сводка решений (200)', resp.status() === 200, resp.status());
  await page.screenshot({ path: path.join(SHOTS, 'ф10-витрина-сводка-решений.png'),
                          fullPage: true });

  resp = await page.goto(`${BASE}/teacher/problems/`, { waitUntil: 'networkidle' });
  const mine = await page.evaluate(() => document.body.innerText);
  check('в своих задачах нет задач сценариев',
        !/Задача с пунктами \(проверка\)|Сквозная задача с пунктами/.test(mine));

  console.log(`\nитого: ${ok} успешно, ${bad} неудачно`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
