/* Wecon Rush: окно поверх забега забирает клавиатуру и ставит забег на паузу.

   Раннер гоняет живую страницу игры в Chromium и печатает результат каждой
   проверки машинно-разбираемой строкой после ###RUSH-JSON###. Решение
   «зелёный/красный» принимает питон-тест `game/tests/test_browser_modals.py`.

   Запуск руками против живого сервера (нужен пул Блица от 10 вопросов):
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_DURATION=120 node game/tests/browser_modals.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер или страница не
   поднялись. Красные проверки раннер не роняют: их читает питон.          */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const DURATION = Number(process.env.RUSH_DURATION || 120);

/* ⚠️ ОСТАТОК ВРЕМЕНИ БЕРЁТСЯ У ПОЛОСЫ, А НЕ У ЦИФР ТАЙМЕРА. Выше десяти
   секунд цифры целые, а проверке нужна десятая доля. Полосу рисует paintHud
   как scaleX(timeLeft / duration) — в ней остаток без округления.         */
async function secondsLeft(page) {
  const frac = await page.$eval('#time-fill', (el) => {
    const m = /scaleX\(([-\d.e]+)\)/.exec(el.style.transform || '');
    return m ? parseFloat(m[1]) : NaN;
  });
  return frac * DURATION;
}

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let answerPosts = 0;
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().includes('/game/api/answer/')) answerPosts += 1;
  });

  try {
    await page.goto(BASE + '/game/', { waitUntil: 'load', timeout: 30000 });
    await page.waitForSelector('#screen-start.active', { timeout: 15000 });
  } catch (e) {
    console.log('страница игры не загрузилась: ' + e.message);
    await browser.close();
    process.exit(3);
  }

  // Блиц — режим по умолчанию: Enter на стартовом экране начинает забег.
  await page.keyboard.press('Enter');
  await page.waitForSelector('#screen-play.active', { timeout: 15000 });
  await page.waitForFunction(
    () => document.getElementById('q-text').textContent.trim().length > 0,
    null, { timeout: 15000 });
  const question = async () => (await page.textContent('#q-text')).trim();
  const q0 = await question();

  await page.locator('.fb-btn:visible').first().click();
  await page.waitForSelector('.fb-back', { timeout: 15000 });
  const t0 = await secondsLeft(page);
  await page.click('.fb-kind');            // «Проблема» — появляется поле текста
  await page.click('.fb-other');
  await page.keyboard.type(' 1');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(2000);
  const t1 = await secondsLeft(page);
  check('question_same', (await question()) === q0, { q0 });
  check('no_answers_sent', answerPosts === 0, { answerPosts });
  check('timer_paused', Math.abs(t0 - t1) <= 0.1, { t0, t1 });

  await page.click('.fb-x');
  await page.waitForSelector('.fb-back', { state: 'detached', timeout: 5000 });
  await page.waitForTimeout(1500);
  const t2 = await secondsLeft(page);
  check('timer_resumed', t1 - t2 >= 1.0, { t1, t2 });

  // Escape внутри окна закрывает его и в забег не проходит.
  await page.locator('.fb-btn:visible').first().click();
  await page.waitForSelector('.fb-back', { timeout: 15000 });
  const qEsc = await question();
  const postsEsc = answerPosts;
  await page.keyboard.press('Escape');
  let closedByEsc = true;
  try {
    await page.waitForSelector('.fb-back', { state: 'detached', timeout: 3000 });
  } catch (e) { closedByEsc = false; }
  check('escape_closes_modal',
        closedByEsc && (await question()) === qEsc && answerPosts === postsEsc,
        { closedByEsc, answerPosts, postsEsc });

  // «Плохая задача?»: окно жалобы тоже ставит раунд на паузу.
  await page.click('#btn-report');
  let reportOpen = true;
  try {
    await page.waitForSelector('.rp-back', { timeout: 5000 });
  } catch (e) { reportOpen = false; }
  const r0 = await secondsLeft(page);
  await page.waitForTimeout(1500);
  const r1 = await secondsLeft(page);
  if (reportOpen) {
    await page.click('.rp-back .fb-x');
    await page.waitForSelector('.rp-back', { state: 'detached', timeout: 5000 }).catch(() => {});
  }
  check('report_window_pauses', reportOpen && Math.abs(r0 - r1) <= 0.1,
        { reportOpen, r0, r1 });
} catch (e) {
  out.error = String((e && e.stack) || e);
} finally {
  await browser.close();
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
