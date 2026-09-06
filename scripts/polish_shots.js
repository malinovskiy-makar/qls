/* СНИМКИ ЭКРАНОВ ДЛЯ СЕССИИ «ПОЛИРОВКА К БЕТЕ».

   Каждый экран снимается в ДВУХ темах и на ТРЁХ ширинах (1440 / 1024 / 380) —
   так, как их будет смотреть владелец. Заодно меряется горизонтальное
   переполнение: страница, которая едет вбок, видна числом, а не на глаз.

   Запуск:
     node scripts/polish_shots.js <фаза> <порт> [роль] [список,через,запятую]

   Роль: guest | student | teacher | parent (боты — scripts/ensure_probe_users.py)
   Список — ключи из PAGES ниже; без него снимаются все.
*/
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PHASE = process.argv[2] || 'phase0';
const PORT = process.argv[3] || '8901';
const ROLE = process.argv[4] || 'student';
const ONLY = (process.argv[5] || '').split(',').filter(Boolean);
const BASE = `http://127.0.0.1:${PORT}`;
const OUTDIR = path.join('reports', 'site_polish_20260904', 'shots', PHASE);

const BOTS = {
  student: ['shot_bot', 'probebot-local-2026'],
  teacher: ['shot_bot_teacher', 'probebot-local-2026'],
  parent: ['shot_bot_parent', 'probebot-local-2026'],
};

const PAGES = {
  home: '/',
  catalog: '/catalog/',
  calc2: '/calc2/',
  stats: '/profile/stats/',
  calendar: '/calendar/',
  game: '/game/',
  olympiads: '/olympiads/',
  login: '/login/',
  map: '/catalog/map/',
  student: '/student/',
  teacher: '/teacher/',
  profile: '/profile/',
  textbook: '/textbook/',
  register: '/register/',
  /* Вкладка «Безопасность» — там смена пароля; вкладку выбирает адрес,
     поэтому это отдельная страница, а не состояние одной. */
  profile_security: '/profile/?tab=security',
  teacher_groups: '/teacher/groups/',
};

const WIDTHS = [[1440, 900], [1024, 800], [380, 780]];
const THEMES = ['light', 'dark'];

(async () => {
  fs.mkdirSync(OUTDIR, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  if (ROLE !== 'guest') {
    const [u, pw] = BOTS[ROLE] || BOTS.student;
    await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
    await page.fill('input[name="username"]', u);
    await page.fill('input[name="password"]', pw);
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
    if (page.url().includes('/login')) {
      console.log(`ОСТАНОВ: вход ролью ${ROLE} не удался`);
      process.exit(2);
    }
  }

  // Живой id задачи — для экрана задачи.
  await page.goto(BASE + '/catalog/', { waitUntil: 'domcontentloaded' });
  const href = await page.evaluate(() => {
    const a = document.querySelector('a[href*="/catalog/problem/"]');
    return a ? a.getAttribute('href') : null;
  });
  if (href) PAGES.problem = href;

  const keys = ONLY.length ? ONLY : Object.keys(PAGES);
  const overflow = [];

  for (const key of keys) {
    const url = PAGES[key];
    if (!url) { console.log(`  пропуск: нет адреса для «${key}»`); continue; }
    for (const theme of THEMES) {
      for (const [w, h] of WIDTHS) {
        await page.setViewportSize({ width: w, height: h });
        await page.goto(BASE + url, { waitUntil: 'load' });
        await page.evaluate(t => {
          try { localStorage.setItem('theme', t); } catch (e) {}
          document.documentElement.setAttribute('data-theme', t);
        }, theme);
        await page.waitForTimeout(900);
        const box = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          client: document.documentElement.clientWidth,
          status: document.title,
        }));
        if (box.scroll > box.client + 1) {
          overflow.push(`${key} ${theme} ${w}px: scrollWidth ${box.scroll} > ${box.client}`);
        }
        const file = path.join(OUTDIR, `${ROLE}_${key}_${theme}_${w}.png`);
        await page.screenshot({ path: file, fullPage: w === 1440 });
      }
    }
    console.log(`  снят: ${key}`);
  }

  console.log(`\nСнимки: ${OUTDIR}`);
  if (overflow.length) {
    console.log('ГОРИЗОНТАЛЬНОЕ ПЕРЕПОЛНЕНИЕ:');
    overflow.forEach(o => console.log('  ' + o));
  } else {
    console.log('Горизонтального переполнения нет ни на одной ширине.');
  }
  await browser.close();
})();
