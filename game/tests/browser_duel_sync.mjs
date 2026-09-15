/* Wecon Rush: синхронный старт дуэли в двух браузерах (решение владельца 15.09.2026).

   Автор открывает лобби и ждёт; соперник открывает то же лобби. Сервер
   назначает общий момент старта (+5 с), у обоих идёт отсчёт, и экран раунда
   появляется у обоих одновременно. Результат каждой проверки — строкой после
   ###RUSH-JSON###, решение «зелёный/красный» принимает питон-тест
   `game/tests/test_browser_duel_sync.py`.

   Запуск руками (нужен ASGI-сервер с сокетами, дуэль и две сессии):
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_LOBBY=/game/s/КОД/ RUSH_AUTHOR=имя_автора RUSH_AUTHOR_SESSION=… RUSH_RIVAL_SESSION=… node game/tests/browser_duel_sync.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер или лобби не
   поднялись. Красные проверки раннер не роняют: их читает питон.          */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const LOBBY = process.env.RUSH_LOBBY || '/game/';
const AUTHOR = process.env.RUSH_AUTHOR || '';

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

/* Метки ставит сама страница: какие цифры показал отсчёт и когда открылся
   экран раунда. Часы у страниц и у node одни — машина одна. */
function watch() {
  window.__rush = { counts: [], startedAt: null };
  document.addEventListener('DOMContentLoaded', () => {
    const play = document.getElementById('screen-play');
    new MutationObserver(() => {
      if (play.classList.contains('active') && !window.__rush.startedAt) {
        window.__rush.startedAt = Date.now();
      }
    }).observe(play, { attributes: true, attributeFilter: ['class'] });
    const cd = document.getElementById('duel-countdown');
    if (!cd) return;
    new MutationObserver(() => {
      const text = cd.textContent.trim();
      const seen = window.__rush.counts;
      if (text && seen[seen.length - 1] !== text) seen.push(text);
    }).observe(cd, { childList: true, characterData: true, subtree: true });
  });
}

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

async function openLobby(session) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addCookies([{ name: 'sessionid', value: session,
                              domain: new URL(BASE).hostname, path: '/' }]);
  await context.addInitScript(watch);
  const page = await context.newPage();
  await page.goto(BASE + LOBBY, { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#duel-lobby', { timeout: 15000 });
  return page;
}

// Ждём экран раунда; не дождались — отдаём, что успели записать.
function startOf(page) {
  return page.waitForFunction(() => window.__rush.startedAt, null, { timeout: 20000 })
    .catch(() => null)
    .then(() => page.evaluate(() => window.__rush));
}

let author;
let rival;
let rivalOpenedAt = 0;
try {
  author = await openLobby(process.env.RUSH_AUTHOR_SESSION || '');
  // Автор уже в комнате: сокет открыт, «привет» ушёл, ждёт соперника.
  await author.waitForTimeout(1500);
  rivalOpenedAt = Date.now();
  rival = await openLobby(process.env.RUSH_RIVAL_SESSION || '');
} catch (e) {
  console.log('лобби не загрузилось: ' + e.message);
  await browser.close();
  process.exit(3);
}

try {
  const rivalLine = await rival.evaluate(
    () => document.getElementById('duel-lobby-text').textContent.trim());
  check('rival_sees_author', rivalLine === 'Соперник: ' + AUTHOR, { rivalLine });

  const [a, b] = await Promise.all([startOf(author), startOf(rival)]);
  check('author_counts_down_from_five', a.counts[0] === '5' && a.counts.includes('Поехали!'), a);
  check('rival_counts_down', b.counts.includes('1') && b.counts.includes('Поехали!'), b);
  check('both_started', !!(a.startedAt && b.startedAt), { a: a.startedAt, b: b.startedAt });
  const together = a.startedAt && b.startedAt ? Math.abs(a.startedAt - b.startedAt) : null;
  check('started_together', together !== null && together <= 1000, { diffMs: together });
  // Старт не раньше, чем через ~4 с после входа соперника: отсчёт шёл, а не
  // пропустился (5 с минус загрузка страницы соперника).
  const waited = a.startedAt ? a.startedAt - rivalOpenedAt : null;
  check('waited_for_countdown', waited !== null && waited >= 3500, { waitedMs: waited });
} catch (e) {
  out.error = String(e && e.message || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
