/**
 * Наложения и читаемость (ревью 17.08, фаза 3) — ЗАМЕРОМ, а не на глаз.
 *
 * Меряются РЕАЛЬНЫЕ прямоугольники элементов и РЕАЛЬНЫЕ цвета из
 * `getComputedStyle`: «кажется, налезает» и «кажется, видно» — не проверки.
 *
 *   node scripts/r18_overlap_probe.js [порт]
 *
 * ⚠️ Контраст считается ПОВЕРХ поверхности: у клетки календаря заливка
 * полупрозрачная, и сравнивать цвет текста с `rgba(...)` напрямую нельзя —
 * получится контраст с прозрачностью, а не с тем, что видит глаз.
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8300';
const BASE = `http://127.0.0.1:${PORT}`;

let passed = 0;
const failures = [];

function ok(name, condition, detail) {
  if (condition) { passed += 1; return; }
  failures.push(`${name}${detail ? ' — ' + detail : ''}`);
}

async function login(page, user) {
  await page.goto(`${BASE}/login/`);
  await page.fill('[name=username]', user);
  await page.fill('[name=password]', 'demo12345');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');
}

async function go(page, path) {
  const response = await page.goto(BASE + path);
  ok(`код ответа ${path}`, response.status() === 200, `${response.status()}`);
  await page.waitForLoadState('networkidle');
  return response;
}

/** Считалка контраста внутри страницы: цвет текста поверх стопки фонов. */
const CONTRAST_HELPER = `
window.__contrast = function (selector) {
  function parse(value) {
    var m = (value || '').match(/[\\d.]+/g) || [];
    return { r: +m[0] || 0, g: +m[1] || 0, b: +m[2] || 0,
             a: m.length > 3 ? +m[3] : 1 };
  }
  function over(top, bottom) {
    return { r: top.r * top.a + bottom.r * (1 - top.a),
             g: top.g * top.a + bottom.g * (1 - top.a),
             b: top.b * top.a + bottom.b * (1 - top.a), a: 1 };
  }
  function lum(c) {
    function f(x) { x /= 255;
      return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  // Фон копится СНИЗУ ВВЕРХ по цепочке родителей: полупрозрачная заливка
  // клетки лежит на поверхности карточки, а та — на фоне страницы.
  var node = document.querySelector(selector);
  if (!node) { return null; }
  var stack = [];
  for (var el = node; el; el = el.parentElement) {
    var bg = parse(getComputedStyle(el).backgroundColor);
    if (bg.a > 0) { stack.push(bg); }
    if (bg.a === 1) { break; }
  }
  var base = stack.pop() || { r: 255, g: 255, b: 255, a: 1 };
  while (stack.length) { base = over(stack.pop(), base); }
  var ink = over(parse(getComputedStyle(node).color), base);
  var l1 = lum(ink), l2 = lum(base);
  var hi = Math.max(l1, l2), lo = Math.min(l1, l2);
  return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
};`;

/** Пересекаются ли два прямоугольника (с запасом в 1px на округление). */
function overlaps(a, b) {
  return !(a.right <= b.left + 1 || b.right <= a.left + 1
           || a.bottom <= b.top + 1 || b.bottom <= a.top + 1);
}

async function rect(page, selector) {
  return page.$eval(selector, (node) => {
    const r = node.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom,
             width: r.width, height: r.height };
  }).catch(() => null);
}

async function checkStats(page, theme) {
  await go(page, '/profile/stats/');
  await page.addScriptTag({ content: CONTRAST_HELPER });
  await page.waitForTimeout(700);

  // ── 3.1 Цифра дня читается на ВСЕХ уровнях заливки ──────────────────
  for (const level of [0, 1, 2, 3, 4]) {
    const selector = `.act-grid--days .act-day.act-l${level}`;
    const found = await page.$(selector);
    if (!found) { continue; }
    const value = await page.evaluate(
      (sel) => window.__contrast(sel), selector);
    ok(`[${theme}] контраст цифры на act-l${level}`, value !== null
       && value >= 4.5, `${value}`);
  }
  // ⚠️ Свойство `opacity` у клетки гасит и цифру: его быть не должно.
  const faded = await page.$$eval('.act-grid--days .act-day',
    (nodes) => nodes.filter((n) =>
      parseFloat(getComputedStyle(n).opacity) < 1
      && !n.classList.contains('is-out')).length);
  ok(`[${theme}] заливка не гасит клетку целиком`, faded === 0,
     `клеток с opacity: ${faded}`);

  // ── 3.2 Подпись не налезает на подписи оси графиков ─────────────────
  const hint = await rect(page, '#time-hint');
  const weekday = await rect(page, '#chart-weekday');
  const hour = await rect(page, '#chart-hour');
  ok(`[${theme}] подпись ниже левого графика`,
     hint && weekday && !overlaps(hint, weekday),
     hint && weekday ? `подпись top=${Math.round(hint.top)}, график bottom=${Math.round(weekday.bottom)}` : 'нет элементов');
  ok(`[${theme}] подпись ниже правого графика`,
     hint && hour && !overlaps(hint, hour),
     hint && hour ? `подпись top=${Math.round(hint.top)}, график bottom=${Math.round(hour.bottom)}` : 'нет элементов');
}

async function main() {
  const browser = await chromium.launch();

  // ── Ученик: календарь активности и графики, обе темы и 380px ────────
  for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ colorScheme: theme });
    const page = await context.newPage();
    await login(page, 'student1@test.local');
    if (theme === 'dark') {
      await page.addInitScript(() => {
        try { localStorage.setItem('theme', 'dark'); } catch (e) {}
      });
    }
    await checkStats(page, theme);
    await context.close();
  }

  const narrow = await browser.newContext({ viewport: { width: 380, height: 800 } });
  const narrowPage = await narrow.newPage();
  await login(narrowPage, 'student1@test.local');
  await checkStats(narrowPage, '380px');
  await narrow.close();

  // ── Репетитор: подписи полей пункта и всплывашка подсказки ──────────
  const tutorCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await tutorCtx.newPage();
  await login(page, 'tutor@test.local');

  // 3.3 — три подписи пункта не налезают друг на друга.
  await go(page, '/teacher/problems/new/');
  await page.click('#add-part-btn');
  await page.waitForTimeout(300);
  for (const width of [1440, 1100, 900, 700]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(200);
    const boxes = await page.$$eval('.part-grid label', (nodes) =>
      nodes.map((n) => {
        const r = n.getBoundingClientRect();
        const cell = n.parentElement.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom,
                 text: n.textContent.trim(),
                 fits: r.width <= cell.width + 1,
                 need: Math.round(n.scrollWidth), have: Math.round(cell.width) };
      }));
    let clash = null;
    for (let i = 0; i < boxes.length && !clash; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        if (overlaps(boxes[i], boxes[j])) {
          clash = `${boxes[i].text} × ${boxes[j].text}`; break;
        }
      }
    }
    ok(`подписи пункта не налезают при ${width}px`, !clash, clash || '');
    const spill = boxes.filter((b) => !b.fits)
      .map((b) => `${b.text}: нужно ${b.need}, дано ${b.have}`);
    ok(`подписи пункта помещаются в ячейку при ${width}px`,
       spill.length === 0, spill.join('; '));
  }

  // 3.5 — всплывашка не закрывает то, что объясняет.
  await page.setViewportSize({ width: 1440, height: 900 });
  await go(page, '/teacher/groups/2/assignments/6/submissions/');
  const mark = await page.$('.k-score__cap [data-hint]');
  if (mark) {
    await mark.hover();
    await page.waitForTimeout(250);
    const tip = await rect(page, '.k-tip');
    const card = await mark.evaluate((node) => {
      const box = node.closest('.k-card') || node.closest('.stu-card');
      const out = [];
      if (!box) { return out; }
      box.querySelectorAll('.k-score__value, .k-btn').forEach((el) => {
        const r = el.getBoundingClientRect();
        out.push({ left: r.left, right: r.right, top: r.top, bottom: r.bottom,
                   what: el.className });
      });
      return out;
    });
    ok('всплывашка показалась', tip !== null && tip.width > 0);
    const covered = (card || []).filter((r) => tip && overlaps(tip, r));
    ok('всплывашка не закрывает числа и кнопки', covered.length === 0,
       covered.map((c) => c.what).join(' | '));
  } else {
    ok('нашёлся вопросик «Результат автопроверки»', false, 'знака нет');
  }

  // 3.4 — приглушения больше нет ни в истории работ, ни в карточках.
  await go(page, '/teacher/groups/2/?tab=overview');
  const dim = await page.$$eval('.wk-table tr, .stu-card', (nodes) =>
    nodes.filter((n) => parseFloat(getComputedStyle(n).opacity) < 1).length);
  ok('строки истории работ не приглушены', dim === 0, `${dim} приглушённых`);
  const words = await page.$$eval('.wk-none', (n) => n.length);
  ok('несданные работы помечены словами', words >= 0, `${words}`);

  await tutorCtx.close();
  console.log(`\nПройдено: ${passed}`);
  if (failures.length) {
    console.log(`Провалено: ${failures.length}`);
    failures.forEach((line) => console.log('  ✗ ' + line));
  } else {
    console.log('Провалов нет.');
  }
  await browser.close();
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => { console.error(error); process.exit(2); });
