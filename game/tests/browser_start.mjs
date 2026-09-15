/* Wecon Rush: стартовый экран — ровные ряды, одна строка вкладок, сетка доски
   (решение владельца 15.09.2026: правки раскладки по списку, приёмка по скринам).

   Раннер открывает /game/ в Chromium на ширинах 1280, 700, 460 и 380 px и
   печатает результат каждой проверки после ###RUSH-JSON###. Решение принимает
   `game/tests/test_browser_layout.py::StartScreenBrowserTest`.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_RECORD_MODE=blitz node game/tests/browser_start.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const RECORD_MODE = process.env.RUSH_RECORD_MODE || '';
// Сколько карточек нижнего ряда в строке на каждой ширине.
const ENTRY_COLUMNS = { 1280: 4, 700: 2, 460: 1, 380: 1 };

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

function measure() {
  // Ряды: элементы с одним верхним краем — один ряд, в нём их высоты.
  const rows = (sel) => {
    const byTop = {};
    Array.from(document.querySelectorAll(sel)).forEach((e) => {
      const r = e.getBoundingClientRect();
      if (!r.height) return;
      const k = Math.round(r.top);
      (byTop[k] = byTop[k] || []).push(Math.round(r.height));
    });
    return Object.keys(byTop).map(Number).sort((a, b) => a - b).map((k) => byTop[k]);
  };
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { top: Math.round(r.top), left: Math.round(r.left), right: Math.round(r.right),
             bottom: Math.round(r.bottom), h: Math.round(r.height) };
  };
  const row = document.querySelector('.lb-row');
  const login = document.querySelector('#lb-foot a');
  const doc = document.documentElement;
  return {
    entryRows: rows('.entry'), modeRows: rows('.mode-card'),
    best: Array.from(document.querySelectorAll('.mode-best')).map((e) => Math.round(e.getBoundingClientRect().height)),
    tabs: box(document.getElementById('lb-modes')),
    period: box(document.getElementById('lb-period')),
    metric: box(document.getElementById('lb-metric')),
    row: row && { row: box(row), nm: box(row.querySelector('.nm')), dt: box(row.querySelector('.dt')),
                  vl: box(row.querySelector('.vl')) },
    login: login && { text: login.textContent.trim(), href: login.getAttribute('href'), box: box(login) },
    duelLink: !!document.querySelector('a[href="/game/duel/new/"]'),
    scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
  };
}

const even = (list) => list.every((r) => Math.max(...r) - Math.min(...r) <= 1);

try {
  for (const width of [1280, 700, 460, 380]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    // Рекорд у ОДНОГО режима: строка «рекорд» у одной карточки и пустая у
    // соседних — ровно тот случай, когда ряды расходились.
    await context.addInitScript((mode) => {
      if (mode) localStorage.setItem('econrush_best_v2_' + mode, '1234');
    }, RECORD_MODE);
    const page = await context.newPage();
    const key = 'start@' + width + ':';
    try {
      await page.goto(BASE + '/game/', { waitUntil: 'load', timeout: 30000 });
      await page.waitForTimeout(400);
      const m = await page.evaluate(measure);
      const columns = ENTRY_COLUMNS[width];
      // В ряду не больше колонок, чем положено ширине, и все ряды, кроме
      // последнего, полные. ⚠️ «Последний ряд может быть короче» раньше
      // пропускал и ОДИН ряд из четырёх на 700 px — зубастость это поймала.
      check(key + 'entry_rows_even', m.entryRows.length > 0 && even(m.entryRows)
            && m.entryRows.every((r) => r.length <= columns)
            && m.entryRows.slice(0, -1).every((r) => r.length === columns),
            { rows: m.entryRows, columns });
      check(key + 'mode_rows_even', m.modeRows.length > 0 && even(m.modeRows), m.modeRows);
      check(key + 'record_line_reserved', m.best.length > 1 && Math.max(...m.best) === Math.min(...m.best), m.best);
      check(key + 'lb_tabs_one_line', m.tabs && m.tabs.h <= 40, m.tabs);
      check(key + 'lb_segments_even', m.period && m.metric && m.period.h === m.metric.h
            && (m.period.top === m.metric.top || m.period.left === m.metric.left),
            { period: m.period, metric: m.metric });
      check(key + 'lb_row_grid', m.row && m.row.dt.left === m.row.nm.left
            && m.row.dt.top >= m.row.nm.bottom - 1 && m.row.row.right - m.row.vl.right <= 9
            && m.row.vl.top > m.row.nm.top, m.row);
      check(key + 'no_hscroll', m.scrollWidth <= m.clientWidth,
            { scrollWidth: m.scrollWidth, clientWidth: m.clientWidth });
      if (width === 1280) {
        check(key + 'login_button', m.login && m.login.text === 'Войти'
              && m.login.href === '/login/?next=/game/' && m.login.box.h >= 32, m.login);
        check(key + 'no_duplicate_links', !m.duelLink, { duelLink: m.duelLink });
      }
    } catch (e) {
      check(key + 'loaded', false, String(e && e.message || e));
    }
    await context.close();
  }
} catch (e) {
  out.error = String(e && e.message || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
