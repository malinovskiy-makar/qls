/* Кабинет учителя: сборка игрового набора на одном экране (фаза P7, ADR 0116).

   Раннер печатает результат каждой проверки после ###RUSH-JSON###. Решение
   принимает `game/tests/test_browser_teacher_sets.py`.

   Инварианты:
   - набор не теряется при смене темы и «Показать ещё 20» (прежний мастер
     перезагружал страницу и стирал собранное);
   - случайная перезагрузка страницы восстанавливает набор из sessionStorage;
   - стрелка «ниже» меняет порядок, и скрытое поле question_ids — тоже;
   - смена режима при непустом наборе спрашивает, «Оставить как есть» ничего не меняет;
   - сохранение ведёт на страницу набора и чистит черновик;
   - телефон 390 px: сборка и страница набора без прокрутки вбок.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_SESSION=значение_sessionid node game/tests/browser_teacher_sets.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const SESSION = process.env.RUSH_SESSION || '';

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}
const host = new URL(BASE).hostname;

const contexts = [];
async function block(names, fn) {
  try {
    await fn();
  } catch (e) {
    const detail = String((e && e.message) || e).slice(0, 400);
    names.forEach((name) => { if (!out.checks[name]) check(name, false, { error: detail }); });
  }
  while (contexts.length) await contexts.pop().close().catch(() => {});
}

async function open(path, { width = 1440, height = 940 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  contexts.push(context);
  await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  const page = await context.newPage();
  await page.goto(BASE + path, { waitUntil: 'load', timeout: 30000 });
  return { context, page };
}

const pickedIds = (page) => page.$eval('#question_ids', (el) => el.value);
const count = (page) => page.$eval('#picked-count', (el) => el.textContent.trim());

try {
  await block(['set_survives_filters_and_paging', 'set_restored_after_reload', 'arrows_reorder_question_ids',
               'mode_switch_asks_when_not_empty', 'save_clears_the_draft'], async () => {
    const { page } = await open('/teacher/game-sets/new/?mode=blitz');
    await page.waitForSelector('#sb-list [data-toggle]', { timeout: 15000 });
    await page.click('#sb-list li:nth-child(1) [data-toggle]');
    await page.click('#sb-list li:nth-child(2) [data-toggle]');
    const before = await pickedIds(page);

    const found = await page.$eval('#sb-found', (el) => el.textContent);
    await page.click('#sb-topics button:nth-of-type(2)');
    await page.waitForFunction((t) => document.getElementById('sb-found').textContent !== t, found, { timeout: 8000 });
    const items = await page.$$eval('#sb-list li', (li) => li.length);
    await page.click('#sb-more');
    await page.waitForFunction((n) => document.querySelectorAll('#sb-list li').length > n, items, { timeout: 8000 });
    const after = { count: await count(page), ids: await pickedIds(page),
                    rows: await page.$$eval('#sb-picked li', (li) => li.length) };
    check('set_survives_filters_and_paging', after.count === '2' && after.ids === before && after.rows === 2,
          { before, after });

    await page.reload({ waitUntil: 'load' });
    await page.waitForSelector('#sb-picked li', { timeout: 8000 });
    const restored = { count: await count(page), ids: await pickedIds(page) };
    check('set_restored_after_reload', restored.count === '2' && restored.ids === before, restored);

    await page.click('#sb-picked li:nth-child(1) button[data-op="down"]');
    const reordered = await pickedIds(page);
    const [a, b] = before.split(',');
    check('arrows_reorder_question_ids', reordered === [b, a].join(','), { before, reordered });

    await page.click('.sb-mode[data-mode="bullet"]');
    const asked = await page.$eval('#sb-ask', (el) => !el.hidden);
    await page.click('#sb-ask-keep');
    const kept = { hidden: await page.$eval('#sb-ask', (el) => el.hidden), count: await count(page),
                   mode: await page.$eval('#sb-mode', (el) => el.value) };
    check('mode_switch_asks_when_not_empty', asked && kept.hidden && kept.count === '2' && kept.mode === 'blitz',
          { asked, kept });

    await page.fill('#sb-title', 'Контрольная из браузера');
    await Promise.all([page.waitForURL(/\/teacher\/game-sets\/[A-Z0-9]+\/\?created=1$/, { timeout: 15000 }),
                       page.click('#btn-save')]);
    const saved = await page.evaluate(() => ({
      title: document.querySelector('.sd-ttl') && document.querySelector('.sd-ttl').textContent.trim(),
      drafts: Object.keys(sessionStorage).filter((k) => k.indexOf('teacher-game-set:') === 0).length,
    }));
    check('save_clears_the_draft', saved.title === 'Контрольная из браузера' && saved.drafts === 0, saved);
  });

  await block(['builder_and_detail_mobile_no_side_scroll'], async () => {
    const widths = {};
    for (const path of ['/teacher/game-sets/new/?mode=blitz', '/teacher/game-sets/']) {
      const { page } = await open(path, { width: 390, height: 844 });
      widths[path] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    }
    const detail = await open('/teacher/game-sets/', { width: 1440, height: 900 });
    const href = await detail.page.$eval('.gs-table a.gs-btn', (a) => a.getAttribute('href')).catch(() => null);
    if (href) {
      const { page } = await open(href, { width: 390, height: 844 });
      widths[href] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    }
    check('builder_and_detail_mobile_no_side_scroll', !!href && Object.values(widths).every(([sw, cw]) => sw <= cw), widths);
  });
} catch (e) {
  out.error = String((e && e.stack) || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
