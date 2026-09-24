/* Решение в ленте помощи в настоящем браузере (24.09.2026, ADR 0129).

   Гость: «Полное решение» → карточка-приглашение, текста решения нет.
   Вошедший: «Полное решение» → «Открыть» → решение пришло запросом и видно.
   Решение — `test_guest_solutions_browser.py`. Печатает `###SOL-JSON###{...}`. */
import { chromium } from 'playwright';

const BASE = process.env.SOL_BASE_URL;
const PATH = process.env.SOL_PATH;
const SESSION = process.env.SOL_SESSION;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36';

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}
const out = {};
async function run(key, session) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, userAgent: UA });
  if (session) {
    await ctx.addCookies([{ name: 'sessionid', value: session, domain: new URL(BASE).hostname, path: '/' }]);
  }
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  const row = { errors: [] };
  page.on('pageerror', e => row.errors.push(e.message));
  try {
    await page.goto(BASE + PATH, { waitUntil: 'load' });
    await page.click('#help-ladder [data-step="sol"]');
    if (session) {
      await page.click('#help-feed [data-confirm="yes"]');
      await page.waitForSelector('#help-feed .feed-sol');
    } else {
      await page.waitForSelector('#help-feed .feed-invite');
    }
    row.feed = await page.$eval('#help-feed', el => el.innerText);
    row.invite = await page.$$eval('#help-feed .feed-invite a', as => as.map(a => a.getAttribute('href')));
  } catch (e) {
    row.fail = String(e && e.message || e);
  }
  out[key] = row;
  await ctx.close();
}
await run('guest', '');
await run('user', SESSION);
await browser.close();
console.log('###SOL-JSON###' + JSON.stringify(out));
