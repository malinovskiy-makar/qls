/**
 * «Глазами ученика» получает проверку (п. 14.4).
 *
 * Проверяем: при открытии всё свёрнуто; внутри раскрытой задачи есть
 * пресеты балла и комментарий; сохранение идёт без ухода со страницы;
 * балл выше максимума обрезает СЕРВЕР.
 *
 * ⚠️ Сценарий сохраняет оценки — работает по ОТДЕЛЬНОЙ базе
 * (`config.settings_check`).
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/eyes_grade.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const URL = `${BASE}/teacher/groups/2/assignments/6/students/9/`;
const SHOTS = path.join('reports', 'review');

let ok = 0, bad = 0;
function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  ✓', name); }
  else { bad += 1; console.log('  ✗', name, extra === undefined ? '' : extra); }
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

  const resp = await page.goto(URL, { waitUntil: 'networkidle' });
  check('разбор открылся (200)', resp.status() === 200, resp.status());

  const opened = await page.$$eval('.wr-item[open]', (n) => n.length);
  const total = await page.$$eval('.wr-item', (n) => n.length);
  check('при открытии всё свёрнуто', opened === 0, `${opened} из ${total}`);
  await page.screenshot({ path: path.join(SHOTS, 'ф09-глазами-ученика-свёрнуто.png') });

  // Раскрываем первую задачу.
  await page.click('.wr-item summary');
  await page.waitForTimeout(300);
  const hasBlock = await page.$$eval('.wr-item[open] .gi-block', (n) => n.length);
  check('внутри раскрытой задачи есть оценивание', hasBlock === 1, hasBlock);
  const presets = await page.$$eval('.wr-item[open] .gi-preset',
    (n) => n.map((e) => e.textContent.trim()));
  check('пресеты балла на месте', presets.length >= 2, JSON.stringify(presets));

  const max = await page.$eval('.wr-item[open] .gi-block',
    (b) => parseFloat(b.dataset.max));
  // ⚠️ Ставим ЗАВЕДОМО больше максимума: обрезать обязан сервер.
  await page.$eval('.wr-item[open] .gi-input', (el, value) => {
    el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, String(max + 100));
  await page.fill('.wr-item[open] .gi-comment', 'Проверка из режима ученика');
  const urlBefore = page.url();
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/teacher/api/grade/')),
    page.click('.wr-item[open] .gi-save'),
  ]);
  await page.waitForTimeout(600);
  check('со страницы не ушли', page.url() === urlBefore, page.url());
  const said = await page.$eval('.wr-item[open] .gi-said',
    (el) => el.hidden ? '' : el.textContent.trim());
  check('появилась отметка «сохранено»', said === 'сохранено', said);
  const shown = await page.$eval('.wr-item[open] .gi-input', (el) => el.value);
  check('балл обрезан по максимуму сервером',
        Math.abs(parseFloat(shown) - max) < 0.01, `${shown} при максимуме ${max}`);
  await page.screenshot({ path: path.join(SHOTS, 'ф09-оценка-в-разборе.png') });

  // Перезагружаем — оценка на месте.
  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.click('.wr-item summary');
  await page.waitForTimeout(300);
  const saved = await page.$eval('.wr-item[open] .gi-comment', (el) => el.value);
  check('комментарий сохранился', saved.includes('режима ученика'), saved);

  console.log(`\nитого: ${ok} успешно, ${bad} неудачно`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
