/* Отложенный умный поиск в настоящем браузере (24.09.2026, ADR 0128).

   Страница `/catalog/?q=…` приходит без сортировки (`deferred`), прячет
   порядок «по словам», сама просит `api_filter_state` с `X-Weco-Search: 1`
   и показывает итог один раз. Решение — `test_deferred_search_browser.py`.

   Печатает `###DEFER-JSON###{...}`. Код 3 — браузер не поднялся. */
import { chromium } from 'playwright';

const BASE = process.env.DEFER_BASE_URL || 'http://127.0.0.1:8000';
const QUERY = process.env.DEFER_QUERY || 'монополист';

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}
const out = { requests: [], errors: [] };
try {
  /* Свой User-Agent: у Playwright в нём «HeadlessChrome», а безголовый браузер
     для платного поиска — бот (catalog/seo.py). */
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36' });
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  page.on('pageerror', e => out.errors.push(e.message));
  page.on('request', r => {
    if (r.url().includes('/catalog/api/filter-state/')) {
      out.requests.push({ url: r.url(), header: r.headers()['x-weco-search'] || '' });
    }
  });
  /* Ответ скрипта придерживаем, чтобы успеть посмотреть страницу «до». */
  let release;
  const held = new Promise(res => { release = res; });
  await page.route('**/catalog/api/filter-state/**', async route => { await held; await route.continue(); });
  await page.goto(BASE + '/catalog/?q=' + encodeURIComponent(QUERY), { waitUntil: 'load' });
  out.before = await page.evaluate(() => {
    const res = document.getElementById('ct-results');
    /* Строки «по словам», которые видны глазу: скелет не в счёт. */
    const visible = Array.from(document.querySelectorAll('#ct-rows > :not(.rail-skel)'))
      .filter(el => getComputedStyle(el).visibility !== 'hidden').length;
    return {
      deferred: !!(res && res.hasAttribute('data-search-deferred')),
      visibleWordRows: visible,
      busy: document.querySelector('form.is-busy') !== null,
    };
  });
  release();
  await page.waitForFunction(() => {
    const res = document.getElementById('ct-results');
    return res && !res.hasAttribute('data-search-deferred');
  });
  out.after = await page.evaluate(() => ({
    status: document.getElementById('ct-results').getAttribute('data-search-status'),
    ids: Array.from(document.querySelectorAll('#ct-rows [data-id]')).map(a => a.getAttribute('data-id')),
    busy: document.querySelector('form.is-busy') !== null,
  }));
  /* Без JS список виден как есть: правило скрытия — только для скриптов. */
  const noJs = await browser.newContext({ javaScriptEnabled: false,
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36' });
  const plain = await noJs.newPage();
  await plain.goto(BASE + '/catalog/?q=' + encodeURIComponent(QUERY), { waitUntil: 'load' });
  out.noJsVisibleRows = await plain.$$eval('#ct-rows > .rail-row',
    rows => rows.filter(el => getComputedStyle(el).visibility !== 'hidden').length);
} catch (e) {
  out.fail = String(e && e.message || e);
}
await browser.close();
console.log('###DEFER-JSON###' + JSON.stringify(out));
