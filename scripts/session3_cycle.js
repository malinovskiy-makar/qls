/*
 * Полный цикл «ученик сдал → преподаватель проверил → ученик увидел».
 *
 * Питон-тесты этот цикл теперь проверяют, но глазами его тоже надо
 * увидеть: главная жалоба ручной проверки была именно про него.
 *
 *   node scripts/session3_cycle.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8123';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = 'reports/session3/shots';
const EXAM_ID = process.env.EXAM_ID || '7';
const STUDENT = ['student3@test.local', 'demo12345'];
// В таблице решений ученик подписан ИМЕНЕМ, а не логином.
const STUDENT_NAME = process.env.STUDENT_NAME || 'Сергей';
const TUTOR = ['tutor@test.local', 'demo12345'];

const results = [];
const check = (name, ok, detail) =>
  results.push({ name, ok: Boolean(ok), detail: detail || '' });

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
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());

  // ── Ученик пишет и сдаёт ────────────────────────────────────────────
  await login(page, STUDENT);
  await page.goto(`${BASE}/student/exam/${EXAM_ID}/`, { waitUntil: 'domcontentloaded' });
  const start = await page.$('button[type=submit]');
  if (start) { await Promise.all([page.waitForNavigation(), start.click()]); }
  await page.waitForSelector('#timer');

  // Отвечаем на всё, что есть: открытые — текстом, тесты — отметками.
  for (const input of await page.$$('input.answer-short')) {
    await input.fill('30');
  }
  for (const area of await page.$$('textarea.answer-text')) {
    await area.fill('Приравнял $Q_d$ и $Q_s$.');
  }
  // В каждом тесте отмечаем первый вариант.
  for (const card of await page.$$('.problem-card')) {
    const option = await card.$('input[type=radio], input[type=checkbox]');
    if (option) { await option.check(); }
  }
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, 'exam-take.png'), fullPage: true });

  await Promise.all([page.waitForNavigation(), page.click('#finish-btn')]);
  // Экран результата ПОГЛОЩЁН разбором работы (Часть B): /student/work/<pk>/.
  check('работа сдана', /\/work\/|\/result\//.test(page.url()), page.url());
  await page.screenshot({ path: path.join(OUT, 'exam-result-before-review.png'), fullPage: true });

  // ── Преподаватель проверяет открытую задачу ─────────────────────────
  await login(page, TUTOR);
  await page.goto(`${BASE}/teacher/groups/2/assignments/${EXAM_ID}/submissions/`,
    { waitUntil: 'domcontentloaded' });
  // ⚠️ Берём решение ИМЕННО нашего ученика: первая попавшаяся ссылка
  // ведёт на чужое решение, и проверка «дошло ли до ученика» ничего не
  // проверит (сам на это и наступил).
  const reviewLink = await page.evaluate((login) => {
    const rows = Array.from(document.querySelectorAll('tr'));
    for (const row of rows) {
      if (!row.textContent.includes(login)) { continue; }
      const link = row.querySelector('a[href*="/submissions/"]');
      if (link) { return link.getAttribute('href'); }
    }
    return null;
  }, STUDENT_NAME);
  check('со страницы решений есть переход на проверку', Boolean(reviewLink), String(reviewLink));
  if (reviewLink) {
    await page.goto(BASE + reviewLink, { waitUntil: 'domcontentloaded' });
    const header = await page.textContent('.sub-meta');
    check('на проверке верный тип работы', /Контрольная/.test(header || ''),
      (header || '').replace(/\s+/g, ' ').trim().slice(0, 120));
    await page.screenshot({ path: path.join(OUT, 'tutor-review.png'), fullPage: true });

    // ⚠️ Балл ограничен максимумом задачи (Часть A) — браузер не даст
    // отправить форму с превышением. Берём максимум со страницы.
    const maxScore = await page.evaluate(() => {
      const input = document.querySelector('input[name=score]');
      return input ? Number(input.max) || 10 : 10;
    });
    await page.fill('input[name=score], #id_score', String(maxScore));
    await page.fill('textarea[name=comment], #id_comment',
      'Ход верный, но не хватает единиц измерения в ответе.');
    const mistake = await page.$('input[name=mistakes]');
    if (mistake) { await mistake.check(); }
    await Promise.all([
      page.waitForNavigation(),
      page.click('button[type=submit]'),
    ]);
  }

  // ── Ученик видит оценку ─────────────────────────────────────────────
  await login(page, STUDENT);
  await page.goto(`${BASE}/student/work/${EXAM_ID}/`, { waitUntil: 'domcontentloaded' });
  const body = await page.textContent('body');
  check('ученик видит комментарий преподавателя',
    /не хватает единиц измерения/i.test(body));
  check('ученик видит, что проверял человек',
    /проверил преподаватель/i.test(body));
  check('ученик видит балл за задачу', /\d+\s*\/\s*\d+\s*б\./.test(body));
  await page.screenshot({ path: path.join(OUT, 'exam-result-after-review.png'), fullPage: true });

  await context.close();
  const mobile = await browser.newContext({ viewport: { width: 380, height: 900 } });
  const small = await mobile.newPage();
  await login(small, STUDENT);
  await small.goto(`${BASE}/student/work/${EXAM_ID}/`, { waitUntil: 'domcontentloaded' });
  await small.screenshot({ path: path.join(OUT, 'exam-result-380.png'), fullPage: true });
  await mobile.close();

  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({ checks: results, passed: results.length - failed.length,
    total: results.length }, null, 1));
  process.exit(failed.length ? 1 : 0);
})();
