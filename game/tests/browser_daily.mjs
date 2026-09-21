/* Wecon Rush: вызов дня и доска дня (фаза P4, решение владельца 17.09.2026).

   Раннер открывает страницы в Chromium и печатает результат каждой проверки
   после ###RUSH-JSON###. Решение принимает
   `game/tests/test_browser_daily.py::DailyBrowserTest`.

   Инварианты:
   - `?auto=1`: стартовый экран не виден, пока сервер не ответил на старт раунда,
     дальше сразу отсчёт 3-2-1 (ответ сервера задержан на 1,5 с, чтобы окно было);
   - `/game/daily/` на 1440×800: четыре карточки в ряд, без прокрутки;
   - телефон 390×844: без прокрутки вбок, карточки столбиком, одна строка лидера,
     кнопки не ниже 44 px;
   - доска дня на ПК: «Таблица» и «Где ошиблись» рядом; на телефоне таблица
     помещается в ширину, вкладки режимов и листалка дней не ниже 44 px.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_SESSION=значение_sessionid RUSH_DAILY_CODE=код node game/tests/browser_daily.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const SESSION = process.env.RUSH_SESSION || '';
const CODE = process.env.RUSH_DAILY_CODE || '';

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

async function open(path, { session = false, width = 1440, height = 800, waitUntil = 'load', before } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  if (session && SESSION) {
    await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  }
  const page = await context.newPage();
  if (before) await before(page);
  await page.goto(BASE + path, { waitUntil, timeout: 30000 });
  return { context, page };
}

try {
  // ── ?auto=1: старт невидим до ответа сервера, дальше отсчёт ──
  {
    const { context, page } = await open('/game/s/' + CODE + '/?auto=1', {
      waitUntil: 'domcontentloaded',
      before: (p) => p.route('**/game/api/session/start_set/**', async (route) => {
        await new Promise((r) => setTimeout(r, 1500));
        await route.continue();
      }),
    });
    await page.waitForTimeout(400);
    const early = await page.evaluate(() => {
      const start = document.getElementById('screen-start');
      const shown = (id) => {
        const el = document.getElementById(id);
        return !!el && el.checkVisibility({ visibilityProperty: true });
      };
      return { visibility: getComputedStyle(start).visibility, active: start.classList.contains('active'),
               setIntro: shown('set-intro'), setPlay: shown('set-play'), startMain: shown('start-main') };
    });
    await page.waitForSelector('#countdown:not([hidden])', { timeout: 15000 }).catch(() => {});
    const later = await page.evaluate(() => ({
      play: document.getElementById('screen-play').classList.contains('active'),
      countdown: !document.getElementById('countdown').hidden,
    }));
    check('autostart_no_start_flash', early.visibility === 'hidden' && early.active && !early.setIntro
          && !early.setPlay && !early.startMain && later.play && later.countdown, { early, later });
    await context.close();
  }

  // ── /game/daily/ на ПК: четыре в ряд, без прокрутки ──
  {
    const { context, page } = await open('/game/daily/', { session: true });
    const m = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.dy-dc')].map((c) => c.getBoundingClientRect());
      return { cards: cards.length, tops: [...new Set(cards.map((r) => Math.round(r.top)))],
               sh: document.documentElement.scrollHeight, ih: innerHeight,
               sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
    });
    check('daily_desktop_row_no_scroll', m.cards === 4 && m.tops.length === 1 && m.sh <= m.ih && m.sw <= m.cw, m);
    await context.close();
  }

  // ── /game/daily/ на телефоне: столбик, одна строка лидера, цели 44 px ──
  {
    const { context, page } = await open('/game/daily/', { session: true, width: 390, height: 844 });
    const m = await page.evaluate(() => {
      const visible = (el) => el.checkVisibility();
      const cards = [...document.querySelectorAll('.dy-dc')];
      const boxes = cards.map((c) => c.getBoundingClientRect());
      const stacked = boxes.every((b, i) => i === 0 || b.top >= boxes[i - 1].bottom);
      const leaders = cards.map((c) => [...c.querySelectorAll('.dy-row')].filter(visible).length);
      const small = [...document.querySelectorAll('.dy-main a')].filter(visible)
        .map((a) => ({ text: a.textContent.trim().slice(0, 30), h: Math.round(a.getBoundingClientRect().height) }))
        .filter((a) => a.h < 44 && !a.text.startsWith('Wecon Rush'));
      return { stacked, leaders, small, sw: document.documentElement.scrollWidth,
               cw: document.documentElement.clientWidth };
    });
    check('daily_mobile_column', m.stacked && m.leaders.every((n) => n <= 1) && m.leaders.some((n) => n === 1)
          && m.small.length === 0 && m.sw <= m.cw, m);
    await context.close();
  }

  // ── Доска дня на ПК: две колонки ──
  {
    const { context, page } = await open('/game/daily/blitz/', { session: true, width: 1440, height: 900 });
    const m = await page.evaluate(() => {
      const t = document.querySelector('.gb-board').getBoundingClientRect();
      const w = document.querySelector('.gb-where').getBoundingClientRect();
      return { tableTop: Math.round(t.top), whereTop: Math.round(w.top), tableRight: Math.round(t.right),
               whereLeft: Math.round(w.left), whereWidth: Math.round(w.width),
               sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
    });
    check('board_desktop_two_columns', m.tableTop === m.whereTop && m.whereLeft > m.tableRight
          && m.whereWidth === 560 && m.sw <= m.cw, m);
    await context.close();
  }

  // ── Доска дня на телефоне: таблица в ширину, цели 44 px ──
  {
    const { context, page } = await open('/game/daily/blitz/', { session: true, width: 390, height: 844 });
    const m = await page.evaluate(() => {
      const scroll = document.querySelector('.gb-scroll');
      const targets = [...document.querySelectorAll('.db-seg a, .db-arr, .db-lnk, #db-play')]
        .filter((el) => el.checkVisibility())
        .map((el) => Math.round(el.getBoundingClientRect().height));
      return { tableFits: !scroll || scroll.scrollWidth <= scroll.clientWidth, targets,
               sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
    });
    check('board_mobile_fits', m.tableFits && m.targets.length >= 6 && m.targets.every((h) => h >= 44)
          && m.sw <= m.cw, m);
    await context.close();
  }
} catch (e) {
  out.error = String((e && e.stack) || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
