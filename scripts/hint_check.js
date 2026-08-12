/**
 * Фаза 1 сессии 9 — подсказки-вопросики.
 *
 * Проверяем ИСПОЛНЕНИЕМ: подсказка появляется сразу при наведении, при
 * фокусе с клавиатуры и по нажатию (сенсорный экран); не уезжает за край
 * окна ни на 1440, ни на 380 пикселях; `title` на знаке не остался.
 *
 * ⚠️ Ничего не сохраняет, но всё равно ходит по проверочной базе
 * (`config.settings_check`) — как все сценарии сессии.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/hint_check.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');

// Все экраны, где знак вопроса уже стоит.
const PAGES = [
  ['витрина набора', '/teacher/styleguide/'],
  ['обзор группы', '/teacher/groups/2/?tab=overview'],
  ['карточка ученика', '/teacher/student/9/progress/'],
];

let ok = 0, bad = 0;
function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  ✓', name); }
  else { bad += 1; console.log('  ✗', name, extra === undefined ? '' : extra); }
}

async function tipBox(page) {
  return page.evaluate(() => {
    const t = document.querySelector('.k-tip');
    if (!t || t.hidden) return null;
    const r = t.getBoundingClientRect();
    return { text: t.textContent.trim(), left: r.left, right: r.right,
             top: r.top, bottom: r.bottom, w: r.width, h: r.height };
  });
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  for (const [label, url] of PAGES) {
    console.log(`\n— ${label} (${url})`);
    const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
    check('страница открылась (200)', resp.status() === 200, resp.status());

    const marks = await page.$$('.k-hintmark');
    check('знаки вопроса на месте', marks.length > 0, marks.length);
    if (!marks.length) continue;

    // `title` убран — иначе браузерная подсказка всплывала бы поверх своей.
    const titles = await page.$$eval('.k-hintmark',
      (n) => n.filter((e) => e.hasAttribute('title')).length);
    check('атрибута title не осталось', titles === 0, titles);

    const texts = await page.$$eval('.k-hintmark',
      (n) => n.map((e) => (e.getAttribute('data-hint') || '').length));
    check('у каждого знака есть текст', texts.every((l) => l > 10),
      JSON.stringify(texts));

    // Наведение: подсказка обязана появиться СРАЗУ, без выдержки.
    let shown = 0, offscreen = 0;
    for (let i = 0; i < marks.length; i += 1) {
      await marks[i].scrollIntoViewIfNeeded();
      await marks[i].hover();
      const box = await tipBox(page);
      if (box && box.text.length > 10) shown += 1;
      if (box && (box.left < 0 || box.right > 1440 || box.top < 0)) offscreen += 1;
      await page.mouse.move(2, 2);
    }
    check('подсказка появляется на каждом знаке', shown === marks.length,
      `${shown} из ${marks.length}`);
    check('ни одна не уехала за край экрана', offscreen === 0, offscreen);

    // Клавиатура.
    await page.evaluate(() => document.querySelector('.k-hintmark').focus());
    const byKeyboard = await tipBox(page);
    check('появляется по фокусу с клавиатуры', !!byKeyboard);
    await page.keyboard.press('Escape');

    // Нажатие — сенсорный экран, где наведения нет.
    await page.evaluate(() => document.querySelector('.k-hintmark').blur());
    await page.mouse.move(2, 2);
    await marks[0].scrollIntoViewIfNeeded();
    await marks[0].click();
    const byTap = await tipBox(page);
    check('появляется по нажатию', !!byTap);
  }

  // Снимок для приёмки: подсказка раскрыта на витрине набора.
  await page.goto(`${BASE}/teacher/styleguide/`, { waitUntil: 'networkidle' });
  const mark = await page.$('.k-hintmark');
  await mark.scrollIntoViewIfNeeded();
  await mark.hover();
  await page.waitForTimeout(120);
  await page.screenshot({ path: path.join(SHOTS, 'с9ф01-подсказка-светлая.png') });
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  await mark.hover();
  await page.waitForTimeout(120);
  await page.screenshot({ path: path.join(SHOTS, 'с9ф01-подсказка-тёмная.png') });

  // 380 пикселей: подсказка не имеет права вылезти за края узкого экрана.
  console.log('\n— узкий экран 380px');
  const narrow = await ctx.newPage();
  await narrow.setViewportSize({ width: 380, height: 800 });
  await narrow.goto(`${BASE}/teacher/groups/2/?tab=overview`,
    { waitUntil: 'networkidle' });
  const nMarks = await narrow.$$('.k-hintmark');
  let nBad = 0;
  for (const m of nMarks) {
    await m.scrollIntoViewIfNeeded();
    await m.hover();
    const box = await tipBox(narrow);
    if (!box) { nBad += 1; continue; }
    if (box.left < 0 || box.right > 380 || box.top < 0) nBad += 1;
    if (box.w > 260.5) nBad += 1;
  }
  check('на 380px подсказки в границах и не шире 260px', nBad === 0, nBad);
  const m0 = nMarks[0];
  if (m0) { await m0.scrollIntoViewIfNeeded(); await m0.hover(); }
  await narrow.waitForTimeout(120);
  await narrow.screenshot({ path: path.join(SHOTS, 'с9ф01-подсказка-380.png') });

  await browser.close();
  console.log(`\nИтого: ${ok} из ${ok + bad}`);
  process.exit(bad ? 1 : 0);
})();
