/* Wecon Rush: экран итога раунда (фаза P3, ADR 0111).

   Раннер играет короткие раунды Блица в Chromium и печатает результат каждой
   проверки после ###RUSH-JSON###. Решение принимает
   `game/tests/test_browser_final.py::FinalBrowserTest`.

   Инварианты:
   - 1440×800: счёт и основная кнопка действий на первом экране (выше 800 px);
   - ошибки и пропуски видны списком без единого клика;
   - раунд без очков — без карточки «Где набрано»;
   - гость: строка «Войдите…» вместо «Последних раундов» и «Против себя обычного»;
     вошедший с историей — обе карточки;
   - дата итога — момент с сервера в часовом поясе ЗРИТЕЛЯ (Владивосток и
     Лос-Анджелес видят разные часы одного момента);
   - телефон 390×844: без прокрутки вбок.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_SESSION=значение_sessionid node game/tests/browser_final.mjs

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

async function open({ session = false, width = 1440, height = 800, timezoneId } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, timezoneId });
  if (session && SESSION) {
    await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  }
  const page = await context.newPage();
  await page.goto(BASE + '/game/?mode=blitz', { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#screen-start.active', { timeout: 15000 });
  return { context, page };
}

/* Раунд Блица: `right` верных подряд, потом три ошибки (жизни кончились).
   У тестовых вопросов верный — первый вариант. Разбор ошибки — пробелом. */
async function playRound(page, right) {
  const finish = page.waitForResponse((r) => r.url().includes('/game/api/session/finish/'),
                                      { timeout: 60000 });
  await page.keyboard.press('Enter');
  await page.waitForSelector('#screen-play.active', { timeout: 15000 });
  if (await page.isVisible('#countdown-card')) await page.click('#countdown-card');
  const nextQuestion = async (before) => page.waitForFunction(
    (q) => document.getElementById('q-text').textContent.trim() !== q, before, { timeout: 6000 },
  ).catch(() => {});
  for (let i = 0; i < right + 3; i += 1) {
    await page.waitForFunction(() => document.querySelectorAll('#opts .opt').length > 1
                               && document.getElementById('countdown').hidden, null,
                               { timeout: 8000 });
    const q = await page.$eval('#q-text', (el) => el.textContent.trim());
    if (i < right) {
      await page.keyboard.press('1');
      if (i < right + 2) await nextQuestion(q);
    } else {
      await page.keyboard.press('2');
      await page.waitForSelector('#reveal:not([hidden])', { timeout: 5000 }).catch(() => {});
      await page.keyboard.press(' ');
      if (i < right + 2) await nextQuestion(q);
    }
  }
  const data = await (await finish).json();
  await page.waitForSelector('#screen-final.active', { timeout: 15000 });
  await page.waitForTimeout(600);
  return data.summary;
}

const visible = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s);
  return !!(el && !el.hidden && el.getClientRects().length && getComputedStyle(el).display !== 'none');
}, sel);

try {
  // ── Вошедший с историей: первый экран, ошибки списком, карточки сравнения ──
  if (SESSION) {
    const { context, page } = await open({ session: true });
    await playRound(page, 5);
    const fold = await page.evaluate(() => {
      const primary = document.querySelector('#fin-actions .fin-primary');
      const score = document.getElementById('final-score').getBoundingClientRect();
      return { primary: primary && primary.id,
               primaryBottom: primary ? Math.round(primary.getBoundingClientRect().bottom + scrollY) : null,
               scoreBottom: Math.round(score.bottom + scrollY) };
    });
    check('score_and_first_action_above_800', fold.primary === 'btn-again'
          && fold.primaryBottom < 800 && fold.scoreBottom < 800, fold);
    const misses = await page.evaluate(() => ({
      items: document.querySelectorAll('#miss-list li').length,
      shown: !document.getElementById('fin-misses').hidden
        && document.getElementById('miss-list').getClientRects().length > 0,
    }));
    check('misses_listed_without_a_click', misses.items === 3 && misses.shown, misses);
    await page.waitForFunction(() => !document.getElementById('fin-history').hidden, null,
                               { timeout: 5000 }).catch(() => {});
    const cmp = { history: await visible(page, '#fin-history'), usual: await visible(page, '#fin-usual'),
                  login: await visible(page, '#fin-login') };
    check('student_compares_with_history', cmp.history && cmp.usual && !cmp.login, cmp);
    await context.close();
  }

  // ── Гость без очков: строка входа, без «Где набрано» ──
  {
    const { context, page } = await open();
    const s = await playRound(page, 0);
    const guest = { score: s.score, points: await visible(page, '#fin-points'),
                    history: await visible(page, '#fin-history'), usual: await visible(page, '#fin-usual'),
                    login: await visible(page, '#fin-login') };
    check('zero_points_no_points_card', guest.score === 0 && !guest.points, guest);
    check('guest_login_line_instead_of_history', guest.login && !guest.history && !guest.usual, guest);
    await context.close();
  }

  // ── Дата итога в часовом поясе зрителя ──
  {
    const shown = {};
    for (const tz of ['Asia/Vladivostok', 'America/Los_Angeles']) {
      const { context, page } = await open({ timezoneId: tz });
      const s = await playRound(page, 1);
      const text = await page.$eval('#fin-date', (el) => el.textContent.trim());
      const expected = new Date(s.played_at).toLocaleString('ru-RU', {
        timeZone: tz, day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
      shown[tz] = { text, expected };
      await context.close();
    }
    const vl = shown['Asia/Vladivostok'], la = shown['America/Los_Angeles'];
    check('date_in_the_viewers_time_zone', vl.text === vl.expected && la.text === la.expected
          && vl.text !== la.text, shown);
  }

  // ── Телефон: без прокрутки вбок ──
  {
    const { context, page } = await open({ width: 390, height: 844 });
    await playRound(page, 2);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth,
                                           cw: document.documentElement.clientWidth }));
    check('mobile_final_no_side_scroll', m.sw <= m.cw, m);
    await context.close();
  }
} catch (e) {
  out.error = String((e && e.stack) || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
