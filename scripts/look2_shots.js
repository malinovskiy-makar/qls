/**
 * Съёмка визуальной сессии 17.08, фазы 4–6.
 *
 * Каждый экран — в СВЕТЛОЙ теме, в ТЁМНОЙ и на 380 пикселях.
 * Код ответа СВЕРЯЕТСЯ: снимок страницы «403» ничего не доказывает.
 *
 * ⚠️ РОЛИ — РАЗНЫЕ КОНТЕКСТЫ БРАУЗЕРА. Вкладки одного контекста делят
 * куки, и вход учеником выбивал бы сессию репетитора: сценарий «успешно»
 * снимал бы страницы 403 (находка сессии 9).
 *
 * ⚠️ Окно «глазами ученика» и лист выдачи приходят ПУСТЫМИ, пока в корзине
 * ничего нет, — поэтому перед их съёмкой работа набирается.
 *
 * Запуск (сервер на проверочной базе):
 *   cp db.sqlite3 db_check.sqlite3
 *   QLS_FAKE_REPLY='{"rows": [], "note": ""}' \
 *     ./venv/bin/python manage.py runserver 8401 \
 *     --settings=config.settings_check
 *   node scripts/look2_shots.js 8401
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8401';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join('reports', 'review');

const SCREENS = [
  ['ф4-статистика', 'student', '/profile/stats/'],
  ['ф5-ученики', 'tutor', '/teacher/groups/'],
  ['ф5-карточка-ученика', 'tutor', '/teacher/student/9/progress/'],
  ['ф6-обзор-занятия', 'tutor', '/teacher/groups/2/?tab=overview'],
  ['ф6-задания-занятия', 'tutor', '/teacher/groups/2/?tab=assignments'],
];

const WHO = { tutor: 'tutor@test.local', student: 'student1@test.local' };

async function login(browser, who) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', who);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  return { context, page };
}

async function shoot(page, name, theme, width) {
  await page.evaluate((value) => {
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.waitForTimeout(500);
  const tail = width === 380 ? '380' : theme;
  await page.screenshot({ path: path.join(OUT, `вид2-${name}-${tail}.png`),
                          fullPage: true });
}

// Набираем работу: без неё оба предпросмотра листа пусты.
async function fillCart(page) {
  await page.goto(`${BASE}/teacher/work/?group=2`, { waitUntil: 'networkidle' });
  const adds = page.locator('#pane-catalog .wk-add');
  const total = await adds.count();
  for (let i = 0; i < Math.min(4, total); i += 1) {
    await adds.nth(i).click();
    await page.waitForTimeout(150);
  }
  return total > 0;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const problems = [];
  let shots = 0;

  const sessions = {};
  for (const role of Object.keys(WHO)) {
    sessions[role] = await login(browser, WHO[role]);
  }

  for (const [name, role, url] of SCREENS) {
    const page = sessions[role].page;
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

  // Лист работы — оба предпросмотра, после набора корзины.
  const tutor = sessions.tutor.page;
  if (await fillCart(tutor)) {
    for (const theme of ['light', 'dark']) {
      await tutor.emulateMedia({ colorScheme: theme });
      await tutor.goto(`${BASE}/teacher/work/compose/?group=2`,
                       { waitUntil: 'networkidle' });
      await tutor.waitForTimeout(1200);
      const open = await tutor.$('#wk-eyes-open');
      if (open) {
        await open.click();
        await tutor.waitForTimeout(600);
        await shoot(tutor, 'ф6-лист-глазами-ученика', theme, 1440);
        shots += 1;
      } else {
        problems.push(`ф6-лист-глазами-ученика (${theme}): окно не открылось`);
      }
      await tutor.goto(`${BASE}/teacher/work/give/?group=2`,
                       { waitUntil: 'networkidle' });
      await tutor.waitForTimeout(1200);
      await shoot(tutor, 'ф6-лист-выдача', theme, 1440);
      shots += 1;
    }
  } else {
    problems.push('лист работы: в каталоге не нашлось задач для корзины');
  }

  await browser.close();
  console.log(`Снимков: ${shots}`);
  if (problems.length) {
    console.log('НЕ СНЯТО:');
    problems.forEach((p) => console.log('  ✗ ' + p));
    process.exit(1);
  }
})();
