/*
 * Съёмка экранов ночной сессии «кабинет преподавателя».
 *
 * Один снимальщик на всю сессию: экранов двадцать, у каждого три ширины
 * (1440 / 768 / 380) и две темы. Руками это несколько часов кликов и
 * гарантированные пропуски.
 *
 * Запуск ИЗ КОРНЯ проекта (иначе require('playwright') не разрешится):
 *   node scripts/night_shots.js <папка-вывода> '<json-список-страниц>' [порт]
 *
 * Формат списка страниц: [["роль", "/адрес/", "имя-файла"], ...]
 * Роли: tutor | student | parent.
 *
 * Ширины и темы задаются переменными окружения (через запятую):
 *   WIDTHS=1440,768,380   THEMES=light,dark
 *
 * Скрипт СВЕРЯЕТ КОД ОТВЕТА и валит съёмку с ненулевым кодом, если страница
 * отдала не 200. Иначе легко снять страницу ошибки 403 и посчитать её успехом
 * (ровно это случилось в сессии 4).
 *
 * Сервер должен быть уже поднят на указанном порту.
 */
const { chromium } = require('playwright');
const fs = require('fs');

const OUT = process.argv[2] || 'reports/night/shots';
const PAGES = JSON.parse(process.argv[3] || '[]');
const PORT = process.argv[4] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;

const WIDTHS = (process.env.WIDTHS || '1440').split(',').map(Number);
const THEMES = (process.env.THEMES || 'light').split(',');
const FULL = process.env.FULL_PAGE !== '0';

const USERS = {
  tutor: ['tutor@test.local', 'demo12345'],
  student: ['student1@test.local', 'demo12345'],
  parent: ['parent@test.local', 'demo12345'],
};

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
  const bad = [];
  const done = [];

  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      const context = await browser.newContext({
        viewport: { width, height: 900 },
        deviceScaleFactor: 1,
      });
      // Тему ставим ДО первой загрузки: скрипт анти-мигания в _tokens.html
      // читает localStorage до применения CSS.
      await context.addInitScript(`try{localStorage.setItem('theme','${theme}')}catch(e){}`);
      let role = null;
      const page = await context.newPage();
      const errors = [];
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

      for (const [want, url, name] of PAGES) {
        if (want !== role) { await login(page, want); role = want; }
        const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
        const status = resp ? resp.status() : 0;
        if (status !== 200) bad.push(`${name} [${theme}/${width}] → HTTP ${status} (${url})`);
        const wsuffix = WIDTHS.length > 1 ? `-${width}` : '';
        const tsuffix = THEMES.length > 1 ? `-${theme}` : '';
        const file = `${OUT}/${name}${wsuffix}${tsuffix}.png`;
        await page.screenshot({ path: file, fullPage: FULL });
        done.push(`${file}  HTTP ${status}`);
      }
      if (errors.length) {
        console.log(`  ошибки консоли [${theme}/${width}]:`, errors.slice(0, 5).join(' | '));
      }
      await context.close();
    }
  }
  await browser.close();
  console.log(done.join('\n'));
  if (bad.length) {
    console.error('\nНЕ 200:\n' + bad.join('\n'));
    process.exit(1);
  }
  console.log(`\nвсе страницы отдали 200, снимков: ${done.length}`);
})();
