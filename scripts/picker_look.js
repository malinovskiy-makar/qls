/**
 * Ручной поиск по каталогу: вид и корзина (п. 13).
 *
 * Снимает экран и проверяет, что правка вида ничего не сломала:
 *  • кнопки карточки стоят СПРАВА от названия, а не под текстом;
 *  • корзина переживает уход на другую плитку и возврат.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/picker_look.js [порт]
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

  const url = `${BASE}/teacher/assignment/create/?q=%D1%81%D0%BF%D1%80%D0%BE%D1%81`;
  let resp = await page.goto(url, { waitUntil: 'networkidle' });
  check('экран открылся (200)', resp.status() === 200, resp.status());

  const geom = await page.$eval('.problem-card', (card) => {
    const title = card.querySelector('.card-title').getBoundingClientRect();
    const acts = card.querySelector('.card-actions').getBoundingClientRect();
    return { titleLeft: title.left, actsLeft: acts.left,
             titleTop: title.top, actsTop: acts.top };
  });
  check('кнопки справа от названия', geom.actsLeft > geom.titleLeft + 100,
        JSON.stringify(geom));
  check('кнопки на одной высоте с названием',
        Math.abs(geom.actsTop - geom.titleTop) < 40, JSON.stringify(geom));

  // Ряд фильтров одной высоты.
  const heights = await page.$$eval(
    '.filters-row .k-input, .filters-row .k-select, .filters-row .k-btn',
    (nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().height)));
  check('поля фильтров одной высоты', new Set(heights).size === 1,
        JSON.stringify(heights));

  // Кладём три задачи в корзину.
  const adds = await page.$$('[data-add]');
  for (let i = 0; i < Math.min(3, adds.length); i += 1) { await adds[i].click(); }
  await page.waitForTimeout(300);
  const inCart = await page.$eval('#cart-count', (n) => n.textContent.trim());
  check('в корзине три задачи', inCart === '3', inCart);
  await page.screenshot({ path: path.join(SHOTS, 'ф08-ручной-поиск.png'),
                          fullPage: false });

  // Уходим на другую плитку и возвращаемся.
  await page.goto(`${BASE}/teacher/assignment/generate/`,
                  { waitUntil: 'networkidle' });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const back = await page.$eval('#cart-count', (n) => n.textContent.trim());
  check('корзина пережила переход', back === '3', back);

  console.log(`\nитого: ${ok} успешно, ${bad} неудачно`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
