/**
 * Фаза 5 сессии 9 — сводка решений и переход к разбору.
 *
 * Проверяем ИСПОЛНЕНИЕМ то, чего питон-тесты не видят:
 *  5.1 два крупных числа стоят на одной высоте;
 *  5.2 «1,5» набирается с клавиатуры и доезжает до базы и обратно;
 *  5.3 «глазами ученика» открывает ту же задачу и доводит её до глаз.
 *
 * ⚠️ Сценарий СОХРАНЯЕТ оценки — работает по проверочной базе
 * (`config.settings_check`).
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/session9_review.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
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
  check('вход ведёт к ученикам', page.url().endsWith('/teacher/groups/'), page.url());

  // ── 5.1 выравнивание крупных баллов ───────────────────────────────────
  console.log('\n— 5.1 крупные баллы на одной высоте');
  const summary = `${BASE}/teacher/groups/2/assignments/6/submissions/`;
  let resp = await page.goto(summary, { waitUntil: 'networkidle' });
  check('сводка решений открылась', resp.status() === 200, resp.status());

  const rows = await page.$$eval('.stu-scores', (nodes) => nodes.map((box) => {
    const values = Array.prototype.map.call(
      box.querySelectorAll('.k-score__value'),
      (v) => Math.round(v.getBoundingClientRect().top));
    return values;
  }));
  const pairs = rows.filter((r) => r.length === 2);
  check('на экране есть карточка с двумя числами', pairs.length > 0, rows.length);
  const misaligned = pairs.filter(([a, b]) => Math.abs(a - b) > 1);
  check('числа выровнены', misaligned.length === 0, JSON.stringify(misaligned));
  await page.screenshot({ path: path.join(SHOTS, 'с9ф05-сводка-решений.png') });

  // ── 5.2 запятая в поле балла ──────────────────────────────────────────
  console.log('\n— 5.2 «1,5» с клавиатуры');
  const link = await page.$('.stu-card a.k-btn');
  await link.click();
  await page.waitForLoadState('networkidle');
  check('экран проверки открылся', /submissions\/\d+/.test(page.url()), page.url());

  const type = await page.getAttribute('#score-input', 'type');
  check('поле балла текстовое', type === 'text', type);
  const mode = await page.getAttribute('#score-input', 'inputmode');
  check('клавиатура на телефоне цифровая', mode === 'decimal', mode);

  await page.fill('#score-input', '');
  await page.type('#score-input', '1,5');
  const typed = await page.inputValue('#score-input');
  check('поле приняло запятую', typed === '1,5', JSON.stringify(typed));

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[name=go][value=list]'),
  ]);
  // Возвращаемся на ту же задачу и смотрим, что показано.
  await page.goBack({ waitUntil: 'networkidle' });
  await page.reload({ waitUntil: 'networkidle' });
  const shown = await page.inputValue('#score-input');
  check('сохранённое значение вернулось в поле с запятой',
    shown === '1,50' || shown === '1,5', JSON.stringify(shown));
  const bigScore = await page.textContent('.k-score__value');
  check('крупный балл показывает дробь',
    /1,5/.test(bigScore.replace(/\s+/g, '')), JSON.stringify(bigScore));
  await page.screenshot({ path: path.join(SHOTS, 'с9ф05-запятая-в-балле.png') });

  // ── 5.3 «глазами ученика» открывает нужную задачу ─────────────────────
  console.log('\n— 5.3 переход к нужной задаче');
  const eyes = await page.getAttribute('a.k-btn--quiet', 'href');
  check('ссылка несёт номер позиции', /\?open=\d+/.test(eyes || ''), eyes);
  await page.goto(BASE + eyes, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);

  const opened = await page.$$eval('.wr-item[open]', (n) => n.length);
  check('раскрыта ровно одна задача', opened === 1, opened);
  const isTarget = await page.$$eval('.wr-item[open]',
    (n) => n.every((e) => e.hasAttribute('data-open-target')));
  check('раскрыта именно та задача', isTarget);
  const inView = await page.$eval('[data-open-target]', (el) => {
    const box = el.getBoundingClientRect();
    return box.top >= -4 && box.top < window.innerHeight;
  });
  check('задача доведена до глаз прокруткой', inView);
  await page.screenshot({ path: path.join(SHOTS, 'с9ф05-глазами-ученика-открыта.png') });

  await browser.close();
  console.log(`\nИтого: ${ok} из ${ok + bad}`);
  process.exit(bad ? 1 : 0);
})();
