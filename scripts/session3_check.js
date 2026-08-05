/*
 * Браузерные проверки сессии 3. Питон-тесты этот класс дефектов не видят:
 * они не исполняют JavaScript и не нажимают клавиш.
 *
 * Запуск ИЗ КОРНЯ проекта (иначе require('playwright') не разрешится):
 *   node scripts/session3_check.js [порт]
 * Сервер должен быть поднят: ./venv/bin/python manage.py runserver <порт>
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8123';
const BASE = `http://127.0.0.1:${PORT}`;
const STUDENT = ['student3@test.local', 'demo12345'];

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: Boolean(ok), detail: detail === undefined ? '' : detail });
}

async function login(page, [username, password]) {
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', username);
  await page.fill('input[name=password]', password);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

(async () => {
  try { await main(); } catch (error) {
    check('прогон дошёл до конца', false, String(error).slice(0, 300));
    report(1);
  }
})();

function report(code) {
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({
    checks: results,
    passed: results.length - failed.length,
    total: results.length,
  }, null, 1));
  process.exit(code === undefined ? (failed.length ? 1 : 0) : code);
}

async function main() {
  const examId = process.env.EXAM_ID || '8';
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  await login(page, STUDENT);

  // Начинаем контрольную (или входим в начатую).
  await page.goto(`${BASE}/student/exam/${examId}/`, { waitUntil: 'domcontentloaded' });
  const startBtn = await page.$('button[type=submit]');
  if (startBtn) {
    await Promise.all([page.waitForNavigation(), startBtn.click()]);
  }
  await page.waitForSelector('#timer', { timeout: 5000 });

  // ── 1. Таймер не зависит от системных часов ─────────────────────────
  const before = await page.textContent('#timer');
  await page.evaluate(() => {
    // Ученик перевёл системные часы на 10 минут назад.
    const shift = -10 * 60 * 1000;
    const realNow = Date.now.bind(Date);
    Date.now = () => realNow() + shift;
  });
  await page.waitForTimeout(2500);
  const after = await page.textContent('#timer');
  const beforeSec = toSeconds(before);
  const afterSec = toSeconds(after);
  check('таймер не вырос после перевода часов назад',
    afterSec !== null && beforeSec !== null && afterSec <= beforeSec,
    `${before} → ${after}`);

  // ── 2. Статус задачи по черновику ───────────────────────────────────
  const firstBadge = await page.textContent('[data-status-badge]');
  check('до ввода задача «Не начата»', /Не начата/.test(firstBadge || ''), firstBadge);

  const shortInput = await page.$('input.answer-short');
  const area = await page.$('textarea.answer-text');
  if (shortInput) { await shortInput.fill('42'); }
  else if (area) { await area.fill('черновик'); }
  await page.waitForTimeout(400);
  const badgeAfter = await page.textContent('[data-status-badge]');
  check('после ввода задача «В работе»', /В работе/.test(badgeAfter || ''), badgeAfter);
  const counter = await page.textContent('#answered-count');
  check('счётчик отвеченных вырос', Number(counter) >= 1, counter);

  // ── 3. Формула рендерится сразу ─────────────────────────────────────
  if (area) {
    await area.click();
    await area.fill('Ответ: $\\frac{TR}{Q}$');
    await page.waitForTimeout(500);
    const rendered = await page.evaluate(() => {
      const node = document.querySelector('.mf-preview');
      if (!node || node.hidden) { return null; }
      return {
        katex: node.querySelectorAll('.katex').length,
        text: node.textContent.slice(0, 80),
      };
    });
    check('предпросмотр показывает собранную формулу',
      rendered && rendered.katex > 0, JSON.stringify(rendered));
  }

  // ── 4. Shift+Enter и Enter не отправляют работу ─────────────────────
  const urlBefore = page.url();
  if (area) {
    await area.click();
    await page.keyboard.press('Shift+Enter');
    await page.keyboard.press('Enter');
  }
  if (shortInput) {
    await shortInput.click();
    await page.keyboard.press('Enter');
  }
  await page.waitForTimeout(700);
  check('Shift+Enter и Enter не отправили работу', page.url() === urlBefore,
    `${urlBefore} → ${page.url()}`);

  // ── 5. Подтверждение сдачи с фактами ────────────────────────────────
  let dialogText = null;
  page.on('dialog', async (d) => { dialogText = d.message(); await d.dismiss(); });
  await page.click('#finish-btn');
  await page.waitForTimeout(600);
  check('перед сдачей спрашивают подтверждение', Boolean(dialogText), dialogText);
  check('в подтверждении есть факты (задачи/время)',
    dialogText && /без ответа|осталось|Дописать/i.test(dialogText), dialogText);
  check('отмена подтверждения оставляет на странице', page.url() === urlBefore);

  check('ошибок в консоли нет', consoleErrors.length === 0,
    consoleErrors.slice(0, 5).join(' | '));
  await browser.close();
  report();
}

function toSeconds(text) {
  if (!text) { return null; }
  const parts = text.trim().split(':').map(Number);
  if (parts.some(Number.isNaN)) { return null; }
  return parts.reduce((acc, value) => acc * 60 + value, 0);
}
