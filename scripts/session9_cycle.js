/**
 * Сквозной сценарий сессии 9 со снимками каждого шага.
 *
 * Вход репетитором → «Ученики» → занятие → обзор → «Задания» → создание
 * работы описанием → сводка решений → проверка задачи → «глазами ученика» →
 * карточка ученика → индивидуальный ученик. Затем вход учеником → игра →
 * статистика.
 *
 * ⚠️ Сохраняющих действий не делает — только смотрит и снимает. Всё равно
 * ходит по проверочной базе (`config.settings_check`), как все сценарии.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/session9_cycle.js [порт]
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

async function login(page, who) {
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', who);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

// ⚠️ Снимок ОБЯЗАН сверять код ответа: первая версия проверки в сессии 4
// открывала чужой экран, получала 403 и «успешно» снимала страницу ошибки.
async function shot(page, url, name) {
  const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
  check(`${name} (200)`, resp.status() === 200, resp.status());
  await page.screenshot({ path: path.join(SHOTS, `с9-цикл-${name}.png`),
                          fullPage: true });
  return resp;
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  console.log('\n— репетитор');
  await login(page, 'tutor@test.local');
  check('вход ведёт к ученикам', page.url().endsWith('/teacher/groups/'),
    page.url());

  await shot(page, '/teacher/groups/', '01-ученики');
  const kinds = await page.$$eval('.k-chip-kind', (n) => n.map((e) => e.textContent.trim()));
  check('на экране есть и группы, и индивидуальные',
    kinds.includes('группа') && kinds.includes('индивидуально'),
    JSON.stringify(kinds));

  await shot(page, '/teacher/groups/2/?tab=overview&period=month', '02-обзор-группы');
  const columns = await page.$$eval('[data-fade] .stats-table thead th',
    (n) => n.length - 1);
  check('в теплокарте 23 канонические темы', columns === 23, columns);

  await shot(page, '/teacher/groups/2/?tab=assignments', '03-задания');
  const badge = await page.$eval('.tabs .k-count', (e) => e.textContent.trim())
    .catch(() => null);
  const total = await page.$eval('.ass-waiting-count b', (e) => e.textContent.trim())
    .catch(() => null);
  check('кружок у вкладки и счётчик над списком совпадают', badge === total,
    `${badge} / ${total}`);

  await shot(page, '/teacher/assignment/generate/?group=2', '04-создание-описанием');
  const title = await page.$eval('.page-title', (e) => e.textContent.trim());
  check('заголовок общий — «Новая работа»', title === 'Новая работа', title);
  // ⚠️ С обзора 13.08 вид работы — сегментированный переключатель
  // (`.bh-kind__opt`), а не плитки: пять одинаковых плиток на экране не
  // давали понять, какие из них главные.
  const switcher = await page.$$eval('.bh-kind__opt',
    (n) => n.map((e) => e.textContent.trim()));
  check('переключатель вида на месте',
    switcher.join(',') === 'Домашка,Контрольная', JSON.stringify(switcher));

  await shot(page, '/teacher/assignment/create/?group=2', '05-искать-самому');
  const stripes = await page.$$eval('.problem-card[data-kind]', (n) => n.length);
  check('карточки задач помечены типом', stripes > 0, stripes);

  await shot(page, '/teacher/groups/2/assignments/6/submissions/', '06-сводка-решений');
  await shot(page, '/teacher/student/9/progress/?period=all', '07-карточка-ученика');
  const cards = await page.$$eval('.cards3 .card3-cap',
    (n) => n.map((e) => e.textContent.trim().replace(/\s+/g, ' ')));
  check('четыре карточки, среди них минуты', cards.length === 4
    && cards.some((c) => /Минут на сайте/.test(c)), JSON.stringify(cards));

  await shot(page, '/teacher/groups/3/?tab=overview', '08-индивидуальный');
  check('у индивидуального нет теплокарты', !(await page.$('[data-fade]')));
  check('у индивидуального нет таблицы учеников',
    !(await page.$('#students-table')));

  console.log('\n— ученик');
  // ⚠️ СВОЙ КОНТЕКСТ, А НЕ ВКЛАДКА. Вкладки делят куки: вход учеником
  // выбивал сессию репетитора, и его экраны дальше отвечали 403 — сценарий
  // «успешно» снимал бы страницы ошибок.
  const studentCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const student = await studentCtx.newPage();
  student.on('pageerror', (e) => errors.push(e.message));
  await login(student, 'student1@test.local');
  const game = await student.goto(`${BASE}/game/`, { waitUntil: 'networkidle' });
  check('игра открылась', game.status() === 200, game.status());
  await student.screenshot({ path: path.join(SHOTS, 'с9-цикл-09-игра.png') });
  const icons = await student.$$eval('.mode-card .mode-icon svg', (n) => n.length);
  check('у режимов рисованные иконки', icons === 4, icons);
  const emoji = await student.evaluate(() => {
    const re = /[\u{1F300}-\u{1FAFF}\u{2764}\u{2665}\u{2661}]/u;
    const bad = [];
    document.querySelectorAll('body *').forEach((el) => {
      if (el.tagName === 'STYLE' || el.tagName === 'SCRIPT') return;
      el.childNodes.forEach((n) => {
        if (n.nodeType === 3 && re.test(n.textContent)) bad.push(n.textContent.trim());
      });
    });
    return bad;
  });
  check('эмодзи в игре не осталось', emoji.length === 0, JSON.stringify(emoji));

  const stats = await student.goto(`${BASE}/profile/stats/`, { waitUntil: 'networkidle' });
  check('статистика ученика открылась', stats.status() === 200, stats.status());
  await student.screenshot({ path: path.join(SHOTS, 'с9-цикл-10-статистика.png'),
                             fullPage: true });
  const minutes = await student.$eval('[data-metric=minutes]', (e) => e.textContent.trim());
  check('карточка времени не ноль', !/^0 /.test(minutes), minutes);
  const best = await student.$$eval('.record .when', (n) => n.length);
  check('у «Лучшего дня» появилась дата', best > 0, best);

  // ── Тёмная тема и 380 пикселей на тронутых экранах ──────────────────
  console.log('\n— тёмная тема и 380px');
  const SCREENS = [
    ['/teacher/groups/', 'ученики'],
    ['/teacher/groups/2/?tab=overview', 'обзор'],
    ['/teacher/student/9/progress/', 'карточка'],
    ['/teacher/assignment/generate/?group=2', 'создание'],
    ['/teacher/groups/3/?tab=overview', 'индивидуальный'],
  ];
  for (const [url, name] of SCREENS) {
    const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
    if (resp.status() !== 200) { check(`тёмная: ${name}`, false, resp.status()); continue; }
    await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
    await page.waitForTimeout(120);
    await page.screenshot({ path: path.join(SHOTS, `с9-тёмная-${name}.png`),
                            fullPage: true });
  }
  check('тёмная тема снята со всех тронутых экранов', true);

  const narrow = await ctx.newPage();
  await narrow.setViewportSize({ width: 380, height: 900 });
  const widths = [];
  for (const [url, name] of SCREENS) {
    const resp = await narrow.goto(BASE + url, { waitUntil: 'networkidle' });
    if (resp.status() !== 200) continue;
    await narrow.screenshot({ path: path.join(SHOTS, `с9-380-${name}.png`),
                              fullPage: true });
    widths.push([name, await narrow.evaluate(() => document.body.scrollWidth)]);
  }
  console.log('  ширина страницы на 380px:', JSON.stringify(widths));
  console.log('  (шапка _nav.html тянет страницу вбок на всём сайте — '
    + 'старая поломка, чинить в этой сессии запрещено)');

  check('ошибок в консоли нет', errors.length === 0, JSON.stringify(errors));
  await browser.close();
  console.log(`\nИтого: ${ok} из ${ok + bad}`);
  process.exit(bad ? 1 : 0);
})();
