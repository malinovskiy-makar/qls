/**
 * Фаза 6 сессии 9 — обзор группы.
 *
 * 6.1 теплокарта слушается переключателя периода;
 * 6.2 полосы прокрутки нет, прокрутка работает, край растворяется;
 * 6.3 «История работ» сортируется по клику на заголовок;
 * 6.4 проценты — цветными метками, тип — чипом, несданная строка приглушена.
 *
 * Ничего не сохраняет, но ходит по проверочной базе, как все сценарии сессии.
 * Запускать ИЗ КОРНЯ проекта: node scripts/session9_overview.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');
const GROUP = `${BASE}/teacher/groups/2/`;

let ok = 0, bad = 0;
function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  ✓', name); }
  else { bad += 1; console.log('  ✗', name, extra === undefined ? '' : extra); }
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  // ── 6.1 теплокарта слушается периода ─────────────────────────────────
  console.log('\n— 6.1 теплокарта и период');
  async function heat(period) {
    await page.goto(`${GROUP}?tab=overview&period=${period}`,
      { waitUntil: 'networkidle' });
    return page.$$eval('.stats-table td .matrix-cell:not(.matrix-none)',
      (n) => n.length);
  }
  const all = await heat('all');
  const day = await heat('day');
  check('за всё время клетки с данными есть', all > 0, all);
  check('за день их меньше — теплокарта слушается периода', day < all,
    `день=${day}, всё=${all}`);

  await page.goto(`${GROUP}?tab=overview&period=month`, { waitUntil: 'networkidle' });
  const stale = await page.$$eval('.panel-allt', (n) => n.length);
  check('пометки «за всё время» больше нет', stale === 0, stale);

  // ⚠️ Считаем заголовки ИМЕННО теплокарты: на экране есть ещё таблица
  // «Ученики» с тем же классом, и общий селектор давал 29 вместо 23.
  const columns = await page.$$eval('[data-fade] .stats-table thead th',
    (n) => n.length - 1);
  check('колонок ровно 23 — только канонические темы', columns === 23, columns);

  // ── 6.2 полоса спрятана, прокрутка жива, край растворяется ───────────
  console.log('\n— 6.2 прокрутка без полосы');
  const box = await page.$('[data-fade]');
  check('обёртка с растворением на месте', !!box);
  const scroll = await page.$eval('[data-fade] .stats-table-wrap', (el) => ({
    hidden: getComputedStyle(el).scrollbarWidth === 'none',
    overflow: getComputedStyle(el).overflowX,
    canScroll: el.scrollWidth > el.clientWidth + 1,
    barHeight: el.offsetHeight - el.clientHeight,
  }));
  check('полоса прокрутки спрятана', scroll.barHeight === 0, scroll.barHeight);
  check('прокрутка осталась рабочей',
    scroll.overflow === 'auto' && scroll.canScroll, JSON.stringify(scroll));

  const fadeBefore = await page.$eval('[data-fade]',
    (el) => !el.classList.contains('is-end'));
  check('пока не доскроллили — край растворён', fadeBefore);
  await page.$eval('[data-fade] .stats-table-wrap',
    (el) => { el.scrollLeft = el.scrollWidth; });
  await page.waitForTimeout(200);
  const fadeAfter = await page.$eval('[data-fade]',
    (el) => el.classList.contains('is-end'));
  check('доскроллили — растворение погасло', fadeAfter);
  await page.$eval('[data-fade] .stats-table-wrap', (el) => { el.scrollLeft = 0; });
  await page.waitForTimeout(200);

  // ── 6.3 сортировка истории работ ─────────────────────────────────────
  console.log('\n— 6.3 сортировка истории работ');
  const table = '#group-works-table';
  check('таблица истории на месте', !!(await page.$(table)));
  const before = await page.$$eval(`${table} tbody tr td.wk-name`,
    (n) => n.map((e) => e.textContent.trim()));
  await page.click(`${table} thead th:nth-child(1)`);
  await page.waitForTimeout(150);
  const after = await page.$$eval(`${table} tbody tr td.wk-name`,
    (n) => n.map((e) => e.textContent.trim()));
  const sorted = after.slice().sort((a, b) => a.localeCompare(b, 'ru'));
  check('клик по заголовку сортирует',
    JSON.stringify(after) === JSON.stringify(sorted),
    JSON.stringify({ before, after }));

  // Числовой столбец сортируется как число, а не как текст.
  await page.click(`${table} thead th:nth-child(5)`);
  await page.waitForTimeout(150);
  const marks = await page.$$eval(`${table} tbody tr td:nth-child(5)`,
    (n) => n.map((e) => parseFloat(e.dataset.sort)));
  const asc = marks.slice().sort((a, b) => a - b);
  check('числовой столбец сортируется числом',
    JSON.stringify(marks) === JSON.stringify(asc), JSON.stringify(marks));

  const hint = await page.$$eval('.panel-hint',
    (n) => n.some((e) => /отсортировать/.test(e.textContent)));
  check('подпись про сортировку на месте', hint);

  // ── 6.4 вид истории ──────────────────────────────────────────────────
  console.log('\n— 6.4 вид истории работ');
  const levels = await page.$$eval(`${table} .k-level`,
    (n) => n.map((e) => e.className));
  check('проценты показаны цветной меткой', levels.length > 0, levels.length);
  const known = levels.every((c) => /k-level--(good|mid|bad)/.test(c));
  check('метки только трёх уровней, серых среди них нет', known,
    JSON.stringify(levels));
  const chips = await page.$$eval(`${table} .wk-kind`, (n) => n.length);
  check('тип работы — тихий чип', chips > 0, chips);
  const dashes = await page.$$eval(`${table} tbody td.wk-num`,
    (n) => n.filter((e) => e.textContent.trim() === '—').length);
  const dashLevels = await page.$$eval(`${table} tbody td.wk-num`,
    (n) => n.filter((e) => e.textContent.trim() === '—'
                        && e.querySelector('.k-level')).length);
  check('прочерк меткой не красится', dashLevels === 0, `${dashLevels} из ${dashes}`);

  await page.goto(`${GROUP}?tab=overview&period=month`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(SHOTS, 'с9ф06-обзор-группы.png'),
                          fullPage: true });
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  await page.waitForTimeout(150);
  await page.screenshot({ path: path.join(SHOTS, 'с9ф06-обзор-группы-тёмная.png'),
                          fullPage: true });

  // Узкий экран.
  const narrow = await ctx.newPage();
  await narrow.setViewportSize({ width: 380, height: 900 });
  await narrow.goto(`${GROUP}?tab=overview&period=month`, { waitUntil: 'networkidle' });
  const width = await narrow.evaluate(() => document.body.scrollWidth);
  console.log(`\n— узкий экран: scrollWidth = ${width} (шапка тянет, это старая поломка)`);
  await narrow.screenshot({ path: path.join(SHOTS, 'с9ф06-обзор-группы-380.png'),
                            fullPage: true });

  await browser.close();
  console.log(`\nИтого: ${ok} из ${ok + bad}`);
  process.exit(bad ? 1 : 0);
})();
