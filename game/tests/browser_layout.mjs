/* Wecon Rush: раскладка страниц игры на 380 и 1280 px (решение владельца 15.09.2026).

   Раннер обходит страницы из RUSH_PAGES (через запятую) в Chromium двух
   ширин и печатает результат каждой проверки машинно-разбираемой строкой
   после ###RUSH-JSON###. Решение «зелёный/красный» принимает питон-тест
   `game/tests/test_browser_layout.py`.

   Проверки на каждой странице и ширине:
   - нет горизонтальной прокрутки: scrollWidth ≤ clientWidth у документа;
   - элементы управления не ниже 32 px (кнопки, role=button, отправка формы и
     ссылки, оформленные кнопкой; строчная ссылка внутри текста — не кнопка);
   - текст кнопки не переносится на три строки.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_PAGES=/game/daily/,/game/stats/ RUSH_SESSION=значение_sessionid node game/tests/browser_layout.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const PAGES = (process.env.RUSH_PAGES || '/game/daily/').split(',').filter(Boolean);
const SESSION = process.env.RUSH_SESSION || '';
const WIDTHS = [380, 1280];

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

/* Замер внутри страницы. Скрытые элементы (нулевой прямоугольник) не мерим:
   их человек не видит и нажать не может.
   ⚠️ ОБЩАЯ ШАПКА САЙТА (`nav.site-nav`, панель меню) НЕ МЕРИТСЯ: она одна на
   весь сайт, у неё свои размеры по канону дизайна, и это не экран игры.
   ⚠️ СТРОКИ СЧИТАЮТСЯ ПО СТРОЧНЫМ ПРЯМОУГОЛЬНИКАМ ТЕКСТА (Range), а не
   делением высоты на line-height: у кнопки с фиксированной высотой и
   центрированием деление давало «три строки» там, где строка одна. */
function measure() {
  function lineCount(el) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const tops = Array.from(range.getClientRects())
      .filter((r) => r.width > 0 && r.height > 0)
      .map((r) => r.top).sort((a, b) => a - b);
    let lines = 0;
    let last = -Infinity;
    for (const top of tops) {
      if (top - last > 6) { lines += 1; last = top; }
    }
    return lines;
  }
  const doc = document.documentElement;
  const controls = Array.from(document.querySelectorAll(
    'button, [role="button"], input[type="submit"], a'));
  const low = [];
  const wrapped = [];
  for (const el of controls) {
    if (el.closest('nav.site-nav, #nav-panel')) continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden') continue;
    // Ссылка в строке текста — не элемент управления.
    if (el.tagName === 'A' && style.display === 'inline') continue;
    const label = (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40);
    if (rect.height < 32) low.push({ label, height: Math.round(rect.height) });
    if (el.tagName === 'BUTTON' || el.tagName === 'A') {
      const lines = lineCount(el);
      if (lines >= 3) wrapped.push({ label, lines });
    }
  }
  return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
           low: low.slice(0, 12), wrapped: wrapped.slice(0, 12) };
}

try {
  const host = new URL(BASE).hostname;
  for (const width of WIDTHS) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    if (SESSION) {
      await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
    }
    const page = await context.newPage();
    for (const path of PAGES) {
      const key = path + '@' + width;
      try {
        const resp = await page.goto(BASE + path, { waitUntil: 'load', timeout: 30000 });
        if (!resp || resp.status() >= 400) {
          check(key + ':loaded', false, { status: resp && resp.status() });
          continue;
        }
        await page.waitForTimeout(300);   // скрипты страницы дорисовывают разметку
        const m = await page.evaluate(measure);
        check(key + ':no_hscroll', m.scrollWidth <= m.clientWidth,
              { scrollWidth: m.scrollWidth, clientWidth: m.clientWidth });
        check(key + ':controls_32px', m.low.length === 0, m.low);
        check(key + ':no_three_line_buttons', m.wrapped.length === 0, m.wrapped);
      } catch (e) {
        check(key + ':loaded', false, String(e && e.message || e));
      }
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
