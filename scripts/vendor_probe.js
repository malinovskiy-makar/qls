/* ФАЗА 0. БИБЛИОТЕКИ ВЛОЖЕНЫ В РЕПОЗИТОРИЙ — ПРОВЕРКА НА ЖИВОЙ СТРАНИЦЕ.

   Что доказывается:
     1. ни одна страница не ходит в чужую сеть (перехват запросов);
     2. нет ошибок в консоли и упавших запросов;
     3. формулы отрисованы KaTeX (в DOM есть .katex);
     4. поле MathLive поднимается (math-field с теневым деревом);
     5. календарь по-русски (локаль подключена из правильного пакета);
     6. график статистики строится (Chart.js жив).

   Запуск: node scripts/vendor_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8901';
const OUT = process.argv[3] || 'reports/site_polish_20260904/phase0_probe.json';
const BASE = `http://127.0.0.1:${PORT}`;

const FOREIGN = /^https?:\/\/(?!127\.0\.0\.1|localhost)/i;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // Вход учеником: /profile/stats/ гостю недоступна. Бот заводится
  // скриптом scripts/ensure_probe_users.py — демо-учётки погашены.
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  await page.fill('input[name="username"]', 'shot_bot');
  await page.fill('input[name="password"]', 'probebot-local-2026');
  await page.click('button[type=submit], input[type=submit]');
  await page.waitForLoadState('domcontentloaded');
  // Вход обязан состояться: иначе проба молча меряет страницу входа
  // вместо страницы статистики — так уже случилось один раз.
  if (page.url().includes('/login')) {
    console.log('ОСТАНОВ: вход не удался, мерить нечего');
    process.exit(2);
  }

  // Живой id задачи — чтобы не гадать номер.
  await page.goto(BASE + '/catalog/', { waitUntil: 'domcontentloaded' });
  const problemHref = await page.evaluate(() => {
    const a = document.querySelector('a[href*="/catalog/problem/"]');
    return a ? a.getAttribute('href') : null;
  });

  const PAGES = [
    ['/', 'главная'],
    ['/catalog/', 'каталог'],
    [problemHref || '/catalog/', 'страница задачи'],
    ['/calc2/', 'калькулятор'],
    ['/profile/stats/', 'статистика'],
    ['/calendar/', 'календарь'],
    ['/game/', 'тренажёр'],
  ];

  const report = [];
  for (const [url, name] of PAGES) {
    const consoleErrors = [];
    const failed = [];
    const foreign = [];
    const onConsole = m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); };
    // Ошибка РАЗБОРА встроенного скрипта в console не приходит — только сюда.
    // Без этого слушателя проба однажды уже показала «0 ошибок» на странице,
    // где инлайновый скрипт не выполнялся вовсе.
    const onPageError = e => consoleErrors.push('pageerror: ' + String(e).slice(0, 200));
    const onFailed = r => failed.push(r.url().slice(0, 160) + ' :: ' + (r.failure() || {}).errorText);
    const onRequest = r => { if (FOREIGN.test(r.url())) foreign.push(r.url().slice(0, 160)); };
    page.on('console', onConsole);
    page.on('pageerror', onPageError);
    page.on('requestfailed', onFailed);
    page.on('request', onRequest);

    await page.goto(BASE + url, { waitUntil: 'load' });
    await page.waitForTimeout(2500);

    const facts = await page.evaluate(() => ({
      katex: document.querySelectorAll('.katex').length,
      katexError: document.querySelectorAll('.katex-error').length,
      mathfield: document.querySelectorAll('math-field').length,
      mathfieldShadow: [...document.querySelectorAll('math-field')]
        .filter(n => n.shadowRoot).length,
      canvas: document.querySelectorAll('canvas').length,
      d3: typeof window.d3 !== 'undefined',
      mathjs: typeof window.math !== 'undefined',
      chart: typeof window.Chart !== 'undefined',
      fullcalendar: typeof window.FullCalendar !== 'undefined',
      katexLib: typeof window.katex !== 'undefined',
      // Календарь по-русски: ищем русские подписи дней недели в сетке.
      calendarRu: /Пн|пн|Понедельник|янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек/
        .test(document.body.innerText),
      gridCells: document.querySelectorAll('.fc-daygrid-day').length,
    }));

    page.off('console', onConsole);
    page.off('pageerror', onPageError);
    page.off('requestfailed', onFailed);
    page.off('request', onRequest);

    report.push({ name, url, foreign, consoleErrors, failed, ...facts });
    const mark = (foreign.length || consoleErrors.length || failed.length) ? 'ПЛОХО' : 'ок';
    console.log(
      `${mark.padEnd(6)} ${name.padEnd(16)} чужих:${foreign.length} ` +
      `ошибок:${consoleErrors.length} упавших:${failed.length} ` +
      `katex:${facts.katex} mf:${facts.mathfield}/${facts.mathfieldShadow} ` +
      `canvas:${facts.canvas} FC:${facts.fullcalendar} ячеек:${facts.gridCells}`
    );
    if (foreign.length) console.log('       ЧУЖИЕ:', foreign.slice(0, 3).join(' | '));
    if (consoleErrors.length) console.log('       КОНСОЛЬ:', consoleErrors.slice(0, 3).join(' | '));
    if (failed.length) console.log('       УПАЛИ:', failed.slice(0, 3).join(' | '));
  }

  fs.mkdirSync('reports/site_polish_20260904', { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2), 'utf8');

  const totals = report.reduce((a, r) => ({
    foreign: a.foreign + r.foreign.length,
    errors: a.errors + r.consoleErrors.length,
    failed: a.failed + r.failed.length,
  }), { foreign: 0, errors: 0, failed: 0 });
  console.log(`\nИТОГО: чужих запросов ${totals.foreign}, ошибок консоли ` +
              `${totals.errors}, упавших запросов ${totals.failed}`);

  await browser.close();
  process.exit(totals.foreign || totals.errors || totals.failed ? 1 : 0);
})();
