/* Wecon Rush: стартовый экран «аркады» (ADR 0108, макеты 17.09.2026).

   Раннер открывает /game/ в Chromium и печатает результат каждой проверки
   после ###RUSH-JSON###. Решение принимает
   `game/tests/test_browser_layout.py::StartScreenBrowserTest`.

   Инварианты фазы P1:
   - на 1440×800 у документа нет вертикальной прокрутки (гость и вошедший);
   - вкладок режимов 4; медалей в таблице при ≥3 строках 3, у 4-й строки число;
   - клавиша 1 выбирает режим и НЕ начинает раунд; Enter начинает ровно один;
   - F открывает окно фильтров; смена режима перезапрашивает таблицу в нём;
   - неверный код: ни одного перехода и строка под полем; код дуэли → /game/d/…;
   - /game/?mode=rapid выбирает Рапид; /game/?duel=rapid открывает окно дуэли
     (гостю — окно «Дуэль только с аккаунтом»);
   - вкладка «Статистика» гостя: четыре карточки рекордов и «Войти»;
   - на 1280, 700, 460 и 380 px нет горизонтальной прокрутки.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_DUEL_CODE=ABCD2345 RUSH_SESSION=значение_sessionid node game/tests/browser_start.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const DUEL_CODE = process.env.RUSH_DUEL_CODE || '';
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

async function openPage(width, height, withSession, path) {
  const context = await browser.newContext({ viewport: { width, height } });
  if (withSession && SESSION) {
    await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  }
  const page = await context.newPage();
  const requests = [];
  page.on('request', (r) => requests.push(r.url()));
  await page.goto(BASE + (path || '/game/'), { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#screen-start.active', { timeout: 15000 });
  await page.waitForTimeout(400);
  return { context, page, requests };
}

const activeMode = (page) => page.evaluate(() => {
  const on = document.querySelector('#mode-grid .mtab.is-on');
  return on && on.dataset.mode;
});

try {
  // ── Гость, 1440×800 ───────────────────────────────────────────────────
  {
    const { context, page, requests } = await openPage(1440, 800, false);
    const m = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('#lb-rows .lb-row'));
      return {
        scrollHeight: document.documentElement.scrollHeight, innerHeight: window.innerHeight,
        tabs: document.querySelectorAll('#mode-grid .mtab').length,
        cells: document.querySelectorAll('#entry-row > .cell:not([hidden])').length,
        rows: rows.length,
        medals: document.querySelectorAll('#lb-rows svg.medal').length,
        fourth: rows[3] ? rows[3].querySelector('.pl').textContent.trim() : null,
      };
    });
    check('guest_no_vscroll_1440x800', m.scrollHeight <= m.innerHeight, m);
    check('four_mode_tabs', m.tabs === 4, m);
    check('four_band_cells', m.cells === 4, m);
    check('three_medals_then_number', m.rows >= 4 && m.medals === 3 && m.fourth === '4', m);

    // Клавиша 1 выбирает первый режим и не начинает раунд.
    const before = await activeMode(page);
    const startsBefore = requests.filter((u) => u.includes('/game/api/session/start')).length;
    await page.keyboard.press('1');
    await page.waitForTimeout(600);
    const after = await activeMode(page);
    const firstTab = await page.evaluate(() => document.querySelector('#mode-grid .mtab').dataset.mode);
    const stillStart = await page.evaluate(() => !!document.querySelector('#screen-start.active'));
    const startsAfter = requests.filter((u) => u.includes('/game/api/session/start')).length;
    check('key1_selects_not_starts', after === firstTab && after !== before && stillStart
          && startsAfter === startsBefore, { before, after, firstTab, stillStart, startsBefore, startsAfter });
    const board = requests.filter((u) => u.includes('/game/api/leaderboard/?mode=' + after));
    check('board_follows_mode', board.length >= 1, { after, board });

    // F открывает окно фильтров, Esc закрывает.
    await page.keyboard.press('f');
    await page.waitForTimeout(200);
    const fOpen = await page.evaluate(() => !document.getElementById('fmodal').hidden);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    const fClosed = await page.evaluate(() => document.getElementById('fmodal').hidden);
    check('f_opens_filters', fOpen && fClosed, { fOpen, fClosed });

    // Вкладка «Статистика» гостя: рекорды устройства и «Войти».
    await page.click('#tab-stats');
    await page.waitForTimeout(200);
    const st = await page.evaluate(() => ({
      cards: document.querySelectorAll('#local-records .rec-c').length,
      login: Array.from(document.querySelectorAll('#pane-stats a'))
        .some((a) => a.textContent.trim() === 'Войти' && a.getBoundingClientRect().height > 0),
    }));
    check('guest_stats_tab', st.cards === 4 && st.login, st);
    await page.click('#tab-board');

    // Неверный код: страница остаётся, под полем строка.
    await page.fill('#code-input', 'zz zz 9999');
    await page.press('#code-input', 'Enter');
    await page.waitForSelector('#code-error:not([hidden])', { timeout: 10000 }).catch(() => {});
    // ⚠️ Замер без падения на чужой странице: ушли по неверному коду на 404 —
    // это красная проверка, а не ошибка раннера.
    const wrong = await page.evaluate(() => {
      const err = document.getElementById('code-error');
      return { path: location.pathname, error: err ? err.textContent.trim() : null,
               shown: !!err && !err.hidden };
    });
    const stayed = wrong.path === '/game/';
    check('wrong_code_stays', stayed && wrong.shown
          && wrong.error === 'Набора с таким кодом нет. Проверьте код.', wrong);
    let cleared = false;
    if (stayed) {
      await page.type('#code-input', 'x');
      cleared = await page.evaluate(() => document.getElementById('code-error').hidden);
    }
    check('wrong_code_message_clears_on_input', cleared, { cleared, stayed });

    // Код дуэли ведёт на её страницу.
    if (DUEL_CODE && stayed) {
      await page.fill('#code-input', DUEL_CODE.toLowerCase());
      await Promise.all([
        page.waitForURL('**/game/d/' + DUEL_CODE + '/', { timeout: 10000 }).catch(() => {}),
        page.press('#code-input', 'Enter'),
      ]);
      check('duel_code_goes_to_duel_page', page.url().endsWith('/game/d/' + DUEL_CODE + '/'), page.url());
    } else if (DUEL_CODE) {
      check('duel_code_goes_to_duel_page', false, 'неверный код увёл со страницы раньше');
    }
    await context.close();
  }

  // ── Гость: Enter начинает ровно один раунд ────────────────────────────
  {
    const { context, page, requests } = await openPage(1440, 800, false);
    await page.keyboard.press('Enter');
    await page.waitForSelector('#screen-play.active', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(500);
    const playing = await page.evaluate(() => !!document.querySelector('#screen-play.active'));
    const starts = requests.filter((u) => u.includes('/game/api/session/start/')).length;
    check('enter_starts_one_round', playing && starts === 1, { playing, starts });
    await context.close();
  }

  // ── Адрес с режимом ───────────────────────────────────────────────────
  {
    const { context, page } = await openPage(1440, 800, false, '/game/?mode=rapid');
    const mode = await activeMode(page);
    const search = await page.evaluate(() => location.search);
    check('url_mode_selects_rapid', mode === 'rapid' && !search.includes('mode='), { mode, search });
    await context.close();
  }
  {
    const { context, page } = await openPage(1440, 800, false, '/game/?duel=rapid');
    const auth = await page.evaluate(() => !document.getElementById('dm-auth').hidden);
    const duel = await page.evaluate(() => !document.getElementById('dmodal').hidden);
    check('url_duel_guest_sees_account_window', auth && !duel, { auth, duel });
    await context.close();
  }

  // ── Вошедший ──────────────────────────────────────────────────────────
  if (SESSION) {
    {
      const { context, page } = await openPage(1440, 800, true);
      const m = await page.evaluate(() => ({
        scrollHeight: document.documentElement.scrollHeight, innerHeight: window.innerHeight,
        quota: !!document.getElementById('quota'),
      }));
      check('student_no_vscroll_1440x800', m.scrollHeight <= m.innerHeight && m.quota, m);
      await context.close();
    }
    {
      const { context, page } = await openPage(1440, 800, true, '/game/?duel=rapid');
      const d = await page.evaluate(() => {
        const on = document.querySelector('#dm-modes .dm-mode[aria-pressed="true"]');
        return { open: !document.getElementById('dmodal').hidden, mode: on && on.dataset.mode };
      });
      check('url_duel_student_opens_create_window', d.open && d.mode === 'rapid', d);
      await context.close();
    }
  }

  // ── Ширины без горизонтальной прокрутки ───────────────────────────────
  for (const width of [1280, 700, 460, 380]) {
    const { context, page } = await openPage(width, 900, false);
    const m = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
    }));
    check('no_hscroll@' + width, m.scrollWidth <= m.clientWidth, m);
    await context.close();
  }
} catch (e) {
  out.error = String(e && e.message || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
