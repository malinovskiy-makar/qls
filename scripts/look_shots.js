/**
 * Съёмка визуальной сессии 17.08 (фазы 0–3) — одной пачкой.
 *
 * Каждый экран снимается в СВЕТЛОЙ теме, в ТЁМНОЙ и на 380 пикселях.
 * Код ответа СВЕРЯЕТСЯ: снимок страницы «403» ничего не доказывает, и на
 * этом уже ловились прошлые сессии.
 *
 * ⚠️ Состояние «Что нашлось» приходит только POST-ом (визуальная сессия
 * 17.08, п. 2.1), поэтому у него свой шаг: заполнить поле панели и нажать
 * «Разобрать запрос». Открыть его адресом больше нельзя — GET уводит в
 * панель, и снимок вышел бы не тем экраном.
 *
 * Запуск (сервер на проверочной базе):
 *   cp db.sqlite3 db_check.sqlite3
 *   QLS_FAKE_REPLY='{"rows": [...], "note": ""}' \
 *     ./venv/bin/python manage.py runserver 8401 \
 *     --settings=config.settings_check
 *   node scripts/look_shots.js 8401
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8401';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review');

const SCREENS = [
  ['ф0-занятие-задания', 'tutor', '/teacher/groups/2/?tab=assignments'],
  ['ф0-занятие-обзор', 'tutor', '/teacher/groups/2/?tab=overview'],
  ['ф1-чипы-и-раскрытие', 'tutor', '/teacher/work/?group=2&q=издержки'],
  ['ф1-числа-состав', 'tutor', '/teacher/work/compose/?group=2'],
  ['ф1-числа-своя-задача', 'tutor', '/teacher/problems/new/?to_cart=1&group=2'],
  ['ф2-что-кладём', 'tutor', '/teacher/work/?group=2'],
  ['ф2-описать-словами', 'tutor', '/teacher/work/?group=2&tab=ai'],
  ['ф2-мои-задачи', 'tutor', '/teacher/work/?group=2&tab=mine'],
  ['ф2-отложенные', 'tutor', '/teacher/work/?group=2&tab=saved'],
  ['ф2-выдача', 'tutor', '/teacher/work/give/?group=2'],
  ['ф3-список-сдач', 'tutor', '/teacher/groups/2/assignments/6/submissions/'],
  ['ф3-проверка-задачи', 'tutor', '/teacher/groups/2/submissions/16/'],
  ['ф3-итоги-проверки', 'tutor',
   '/teacher/groups/2/assignments/6/students/9/done/'],
];

const WHO = { tutor: 'tutor@test.local' };

async function login(context, who) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', who);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  return page;
}

// Второе состояние панели «Описать словами»: только через нажатие.
async function openFound(page) {
  await page.goto(`${BASE}/teacher/work/?group=2&tab=ai`,
                  { waitUntil: 'networkidle' });
  const field = await page.$('#gen-text');
  if (!field) { return false; }
  await field.fill('эластичность спроса, две задачи');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#pane-ai button[type=submit]'),
  ]);
  return true;
}

async function shoot(page, name, theme, width) {
  await page.evaluate((value) => {
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.waitForTimeout(450);
  const tail = width === 380 ? '380' : theme;
  await page.screenshot({ path: path.join(OUT, `вид-${name}-${tail}.png`),
                          fullPage: true });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const problems = [];
  let shots = 0;

  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 } });
  const page = await login(context, WHO.tutor);

  for (const [name, , url] of SCREENS) {
    for (const theme of ['light', 'dark']) {
      await page.emulateMedia({ colorScheme: theme });
      const res = await page.goto(BASE + url, { waitUntil: 'networkidle' });
      if (res && res.status() !== 200) {
        problems.push(`${name} (${theme}): код ${res.status()}`);
        continue;
      }
      await shoot(page, name, theme, 1440);
      shots += 1;
    }
    await page.setViewportSize({ width: 380, height: 900 });
    const narrow = await page.goto(BASE + url, { waitUntil: 'networkidle' });
    if (!narrow || narrow.status() === 200) {
      await shoot(page, name, 'light', 380);
      shots += 1;
    }
    await page.setViewportSize({ width: 1440, height: 1100 });
  }

  // «Что нашлось» — отдельно, оно приходит POST-ом.
  for (const theme of ['light', 'dark']) {
    await page.emulateMedia({ colorScheme: theme });
    if (await openFound(page)) {
      await shoot(page, 'ф2-что-нашлось', theme, 1440);
      shots += 1;
    } else {
      problems.push(`ф2-что-нашлось (${theme}): панель не открылась`);
    }
  }
  await page.setViewportSize({ width: 380, height: 900 });
  if (await openFound(page)) {
    await shoot(page, 'ф2-что-нашлось', 'light', 380);
    shots += 1;
  }

  await context.close();
  await browser.close();
  console.log(`Снимков: ${shots}`);
  if (problems.length) {
    console.log('НЕ СНЯТО:');
    problems.forEach((p) => console.log('  ✗ ' + p));
    process.exit(1);
  }
})();
