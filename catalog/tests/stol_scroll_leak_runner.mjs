/* Пустая прокрутка под «Столом» от формул в ленте помощи и в левой ленте (13.10.2026).

   Решение «зелёный/красный» принимает `catalog/tests/test_stol_scroll_leak_browser.py`;
   здесь только замеры. Критерий: документ не длиннее body —
   `document.documentElement.scrollHeight <= body.height + 1`. Плюс доказательства,
   что замер не пустой: формулы есть, скроллер действительно переполнен.

   Запуск руками (нужны адрес, сессия вошедшего и id задачи с длинным решением):
     LEAK_BASE_URL=http://127.0.0.1:8000 LEAK_SESSION=… LEAK_PROBLEM=… \
     node catalog/tests/stol_scroll_leak_runner.mjs

   Печатает одну строку `###LEAK-JSON###{...}`. Коды возврата: 0 — прогон
   дошёл до конца, 3 — браузер не поднялся. */
import { chromium } from 'playwright';

const BASE = process.env.LEAK_BASE_URL || 'http://127.0.0.1:8000';
const SESSION = process.env.LEAK_SESSION || '';
const PID = process.env.LEAK_PROBLEM || '';

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

const out = {};
async function fresh(path, panels, width, height) {
  const ctx = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
  await ctx.addInitScript(`try { localStorage.setItem('weco_stol', ${JSON.stringify(JSON.stringify(panels))});
    localStorage.setItem('weco_help_tip_seen', '1'); } catch (e) {}`);
  if (SESSION) await ctx.addCookies([{ name: 'sessionid', value: SESSION, url: BASE }]);
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(BASE + path, { waitUntil: 'load' });
  return { ctx, page, errors };
}
/* Замер: насколько документ длиннее body и переполнен ли скроллер `sel`. */
const measure = (page, sel) => page.evaluate(s => {
  const box = document.querySelector(s);
  return { doc: document.documentElement.scrollHeight,
           body: document.body.getBoundingClientRect().height,
           katex: box.querySelectorAll('.katex-mathml').length,
           over: box.scrollHeight - box.clientHeight };
}, sel);
async function section(name, fn) {
  try { await fn(); } catch (e) { out['fail ' + name] = String(e && e.message || e).split(/\r?\n/)[0].slice(0, 300); }
}

try {
  /* Лента помощи: «Эталонное решение» → «Открыть» → решение с формулами в ленте. */
  for (const [width, height] of [[1781, 902], [1440, 900], [1280, 800]]) {
    await section('help ' + width, async () => {
      if (!(PID && SESSION)) return;
      const { ctx, page, errors } = await fresh('/catalog/problem/' + PID + '/', { rail: false, help: true }, width, height);
      /* Решение уже открывали на прошлой ширине — сервер рисует его сам, лестницы нет. */
      if (!(await page.$('.help-feed .sol-body'))) {
        await page.click('.help-ladder [data-step="sol"]');
        await page.click('.help-feed [data-confirm="yes"]');
      }
      await page.waitForFunction(() => document.querySelectorAll('.help-feed .sol-body .katex').length >= 4);
      out['help ' + width] = Object.assign(await measure(page, '.help-body'), { errors });
      await ctx.close();
    });
  }

  /* Левая лента: строки выдачи без названия показывают превью условия с формулами. */
  await section('rail', async () => {
    if (!SESSION) return;
    const { ctx, page, errors } = await fresh('/catalog/', { rail: true, help: false }, 1440, 900);
    const first = await page.evaluate(() => Number(document.querySelector('#ct-rows .rail-row').getAttribute('data-id')));
    await page.evaluate(id => weco.stol.open(id), first);
    await page.waitForFunction(id => weco.stol.state.problemId === id && weco.stol.state.view === 'stol', first);
    await page.waitForFunction(() => document.querySelectorAll('#stol-rail-list .katex').length >= 10);
    out.rail = Object.assign(await measure(page, '#stol-rail-list'), { errors });
    await ctx.close();
  });
} catch (e) {
  out.error = String(e && e.stack || e);
}
await browser.close();
console.log('###LEAK-JSON###' + JSON.stringify(out));
