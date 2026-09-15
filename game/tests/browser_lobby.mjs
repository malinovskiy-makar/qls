/* Wecon Rush: лобби дуэли и табло на узком экране (решение владельца 15.09.2026).

   Раннер открывает лобби дуэли и раунд Блица в Chromium шириной 380 px и
   печатает результат каждой проверки машинно-разбираемой строкой после
   ###RUSH-JSON###. Решение «зелёный/красный» принимает питон-тест
   `game/tests/test_browser_lobby.py`.

   Запуск руками против живого сервера (нужна дуэль и сессия вошедшего):
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_LOBBY=/game/s/КОД/ RUSH_SESSION=значение_sessionid node game/tests/browser_lobby.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер или страница не
   поднялись. Красные проверки раннер не роняют: их читает питон.          */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const LOBBY = process.env.RUSH_LOBBY || '/game/';
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

try {
  const context = await browser.newContext({ viewport: { width: 380, height: 800 } });
  const host = new URL(BASE).hostname;
  if (SESSION) {
    await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  }
  const page = await context.newPage();

  try {
    await page.goto(BASE + LOBBY, { waitUntil: 'load', timeout: 30000 });
    await page.waitForSelector('#duel-lobby', { timeout: 15000 });
  } catch (e) {
    console.log('лобби не загрузилось: ' + e.message);
    await browser.close();
    process.exit(3);
  }

  const lobby = await page.evaluate(() => {
    const doc = document.documentElement;
    const copy = document.getElementById('duel-copy').getBoundingClientRect();
    const code = getComputedStyle(document.getElementById('duel-code'));
    const band = document.getElementById('practice-band');
    return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
             copyHeight: copy.height, codeSize: parseFloat(code.fontSize),
             playButton: !!document.getElementById('set-play'),
             practiceBand: !!band && !band.hidden };
  });
  check('lobby_no_hscroll', lobby.scrollWidth <= lobby.clientWidth, lobby);
  check('copy_link_44px', lobby.copyHeight >= 44, lobby);
  check('room_code_big', lobby.codeSize >= 40, lobby);
  check('lobby_has_no_play_button', !lobby.playButton, lobby);
  // В лобби играют набор, а не пул: полосы «Бесконечные тесты» там нет.
  check('lobby_has_no_practice_band', !lobby.practiceBand, lobby);

  // Табло раунда на 380 px: обычный Блиц, та же вёрстка `.vs`, что в дуэли.
  await page.goto(BASE + '/game/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#screen-start.active', { timeout: 15000 });
  await page.keyboard.press('Enter');
  await page.waitForSelector('#screen-play.active', { timeout: 15000 });
  await page.waitForFunction(
    () => document.getElementById('q-text').textContent.trim().length > 0,
    null, { timeout: 15000 });
  const scene = await page.evaluate(() => {
    const el = document.querySelector('.scene');
    const vs = document.getElementById('vs');
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
             vsShown: !!vs && !vs.hidden };
  });
  check('scene_no_hscroll', scene.scrollWidth <= scene.clientWidth, scene);
  check('scoreboard_shown', scene.vsShown, scene);
} catch (e) {
  out.error = String(e && e.message || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
