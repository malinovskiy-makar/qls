/* Wecon Rush: сбой сети не замораживает забег.

   Раннер гоняет живую страницу игры в Chromium, подменяя ответ сервера на
   /game/api/answer/, и печатает результат проверок машинно-разбираемой
   строкой после ###RUSH-JSON###. Решение «зелёный/красный» принимает
   питон-тест `game/tests/test_browser_freeze.py`.

   Случай 1 — прокси отдал 502 страницей HTML: виден тост «Нет связи»,
   кнопки вариантов снова нажимаются, повторный клик уходит на сервер.
   Случай 2 — состояние забега истекло (`reason: no_run`): оверлей «Забег
   потерян» с кнопкой «На старт», и она ведёт на старт.

   Запуск руками против живого сервера (нужен пул Блица от 10 вопросов):
     RUSH_BASE_URL=http://127.0.0.1:8000 node game/tests/browser_freeze.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер или страница не
   поднялись. Красные проверки раннер не роняют: их читает питон.          */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

async function startBlitz(page) {
  await page.goto(BASE + '/game/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#screen-start.active', { timeout: 15000 });
  await page.keyboard.press('Enter');          // Блиц — режим по умолчанию
  await page.waitForSelector('#screen-play.active', { timeout: 15000 });
  await page.waitForSelector('#opts .opt', { timeout: 15000 });
}

async function waitUntil(fn, ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (fn()) return true;
    await new Promise((r) => setTimeout(r, 50));
  }
  return fn();
}

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

try {
  /* Случай 1: 502 страницей HTML на первый ответ, дальше — настоящий сервер. */
  const ctx1 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page1 = await ctx1.newPage();
  let calls = 0;
  await page1.route('**/game/api/answer/', (route) => {
    calls += 1;
    if (calls === 1) {
      return route.fulfill({ status: 502, contentType: 'text/html',
                             body: '<html><body><h1>502 Bad Gateway</h1></body></html>' });
    }
    return route.continue();
  });
  try {
    await startBlitz(page1);
  } catch (e) {
    console.log('страница игры не загрузилась: ' + e.message);
    await browser.close();
    process.exit(3);
  }
  await page1.click('#opts .opt');
  let toast = true;
  try {
    await page1.waitForSelector('#net-toast:not([hidden])', { timeout: 3000 });
  } catch (e) { toast = false; }
  check('toast_visible', toast, { calls });
  await page1.waitForTimeout(300);
  // Клик без ожидания «кнопка готова»: замороженная кнопка не должна
  // превращать проверку в таймаут — она просто не отправит запрос.
  await page1.click('#opts .opt', { timeout: 2000 }).catch(() => {});
  const sent = await waitUntil(() => calls >= 2, 3000);
  check('second_click_sent', sent, { calls });
  await ctx1.close();

  /* Случай 2: состояние забега истекло — сервер честно говорит no_run. */
  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page2 = await ctx2.newPage();
  await page2.route('**/game/api/answer/', (route) => route.fulfill({
    status: 400, contentType: 'application/json',
    body: JSON.stringify({ error: 'Забег не начат', reason: 'no_run' }) }));
  await startBlitz(page2);
  await page2.click('#opts .opt');
  let lost = true;
  try {
    await page2.waitForSelector('#lost-overlay:not([hidden])', { timeout: 3000 });
  } catch (e) { lost = false; }
  check('lost_overlay_visible', lost, {});
  let home = false;
  let label = '';
  if (lost) {
    label = (await page2.textContent('#lost-home')).trim();
    await page2.click('#lost-home');
    await page2.waitForSelector('#screen-start.active', { timeout: 15000 }).catch(() => {});
    home = label === 'На старт' && new URL(page2.url()).pathname === '/game/';
  }
  check('lost_button_home', home, { label, url: page2.url() });
  await ctx2.close();

  /* Случаи 3 и 4 (24.09.2026): финиш раунда. Ответ на вопрос — настоящий,
     раунд завершается выходом (крестик → «Выйти»): такой раунд с ответом
     сохраняется незачётным. */
  async function quitAfterOneAnswer(page) {
    await startBlitz(page);
    await page.click('#opts .opt');
    await page.waitForTimeout(600);
    await page.click('#btn-quit');
    await page.click('#quit-yes');
  }

  /* Случай 3: первый финиш — 502, повтор уходит на сервер и сохраняет. */
  const ctx3 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page3 = await ctx3.newPage();
  let finishCalls3 = 0;
  await page3.route('**/game/api/session/finish/', (route) => {
    finishCalls3 += 1;
    if (finishCalls3 === 1) {
      return route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502</h1>' });
    }
    return route.continue();
  });
  await quitAfterOneAnswer(page3);
  const retried = await waitUntil(() => finishCalls3 >= 2, 8000);
  await page3.waitForTimeout(800);
  const note3 = (await page3.textContent('#ranked-note').catch(() => '')) || '';
  check('finish_retry_saved', retried && !note3.includes('не сохранён'),
        { finishCalls3, note3 });
  await ctx3.close();

  /* Случай 4: финиш не проходит никогда — честная плашка на итоге. */
  const ctx4 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page4 = await ctx4.newPage();
  let finishCalls4 = 0;
  await page4.route('**/game/api/session/finish/', (route) => {
    finishCalls4 += 1;
    return route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502</h1>' });
  });
  await quitAfterOneAnswer(page4);
  let plate = false;
  try {
    await page4.waitForFunction(() => {
      const el = document.getElementById('ranked-note');
      return el && !el.hidden && el.textContent.includes('Результат не сохранён');
    }, null, { timeout: 15000 });
    plate = true;
  } catch (e) { plate = false; }
  check('finish_unsaved_plate', plate && finishCalls4 === 4, { finishCalls4 });
  await ctx4.close();
} catch (e) {
  out.error = String((e && e.stack) || e);
} finally {
  await browser.close();
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
