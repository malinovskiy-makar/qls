/*
 * Скриншоты страниц платформы под разными ролями — сессия «Статистика и
 * контрольные».
 *
 * Зачем скриптом, а не глазами: страниц в этой сессии полтора десятка, у
 * каждой две ширины (десктоп и 380px) и три роли. Руками это час кликов и
 * гарантированный пропуск.
 *
 * Запуск ИЗ КОРНЯ проекта (иначе require('playwright') не разрешится):
 *   node scripts/session_shots.js [порт] [папка]
 *
 * Сервер должен быть уже поднят: ./venv/bin/python manage.py runserver <порт>
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8123';
const OUT = process.argv[3] || 'reports/session_stats/shots';
const BASE = `http://127.0.0.1:${PORT}`;

const USERS = {
  student: ['student1@test.local', 'demo12345'],
  tutor: ['tutor@test.local', 'demo12345'],
  parent: ['parent@test.local', 'demo12345'],
};

// Что снимаем: [роль, адрес, имя файла]. Адрес может быть функцией — тогда
// он вычисляется уже после входа (например, «первая домашка ученика»).
const PAGES = process.env.SHOT_PAGES
  ? JSON.parse(process.env.SHOT_PAGES)
  : [
      ['student', '/student/', 'student-dashboard'],
      ['student', '/student/assignment/6/', 'student-assignment'],
      ['student', '/profile/stats/', 'student-stats'],
      ['tutor', '/teacher/', 'tutor-inbox'],
      ['tutor', '/teacher/groups/', 'tutor-groups'],
    ];

async function login(page, role) {
  const [username, password] = USERS[role];
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
  const report = [];

  for (const width of [1280, 380]) {
    const suffix = width === 380 ? '-380' : '';
    let role = null;
    const context = await browser.newContext({
      viewport: { width, height: 900 },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const errors = [];
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text());
    });

    for (const [wantRole, url, name] of PAGES) {
      if (wantRole !== role) {
        await login(page, wantRole);
        role = wantRole;
      }
      const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' })
        .catch((e) => ({ status: () => 'ERR ' + e.message }));
      const status = resp ? resp.status() : '?';
      const file = path.join(OUT, `${name}${suffix}.png`);
      await page.screenshot({ path: file, fullPage: true });
      const metrics = await page.evaluate(() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
        // Что именно вылезает за правый край — чтобы не гадать.
        widest: (() => {
          let worst = null;
          document.querySelectorAll('body *').forEach((el) => {
            const r = el.getBoundingClientRect();
            if (r.width === 0) return;
            if (!worst || r.right > worst.right) {
              worst = { right: Math.round(r.right), tag: el.tagName,
                        cls: (el.className || '').toString().slice(0, 40) };
            }
          });
          return worst;
        })(),
      }));
      report.push({ width, name, url, status, ...metrics });
    }
    await context.close();
    if (errors.length) report.push({ width, consoleErrors: errors.slice(0, 10) });
  }

  await browser.close();
  console.log(JSON.stringify(report, null, 1));
})();
