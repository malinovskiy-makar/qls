// Проверка страниц платформы: консоль браузера + горизонтальный вылет на 380px.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8123';

const PAGES = [
  ['/teacher/', 'дашборд входящих'],
  ['/teacher/groups/', 'список групп'],
  ['/teacher/groups/create/', 'создание группы'],
  ['/profile/', 'профиль'],
  ['/profile/?tab=saved', 'профиль: сохранённое'],
  ['/teacher/problems/', 'мои задачи'],
  ['/teacher/problems/new/', 'редактор задачи'],
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 380, height: 800 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('JS: ' + e.message));

  // Вход репетитором.
  await page.goto(BASE + '/login/', { waitUntil: 'networkidle' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit], input[type=submit]')]);

  // Групповые страницы — узнаём id.
  const ids = JSON.parse(process.env.QLS_IDS);
  PAGES.push([`/teacher/groups/${ids.group}/`, 'страница группы']);
  PAGES.push([`/teacher/groups/${ids.group}/?tab=assignments`, 'группа: задания']);
  PAGES.push([`/teacher/groups/${ids.group}/assignments/${ids.assignment}/`, 'задание целиком']);
  PAGES.push([`/teacher/groups/${ids.group}/assignments/${ids.assignment}/submissions/`, 'проверка решений']);

  console.log('ширина 380px — вылет по горизонтали:');
  for (const [url, name] of PAGES) {
    const before = errors.length;
    const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
    const m = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }));
    const overflow = m.scrollW > m.clientW + 1;
    const newErrs = errors.slice(before);
    console.log(
      `  ${resp.status()} ${overflow ? 'ВЫЛЕТ ' + m.scrollW + '>' + m.clientW : 'ок  '} ` +
      `${newErrs.length ? 'JS-ошибок: ' + newErrs.length : ''}  ${name}  ${url}`);
    if (newErrs.length) newErrs.forEach(e => console.log('      ! ' + e.slice(0, 160)));
  }

  // Ученик.
  const ctx2 = await browser.newContext({ viewport: { width: 380, height: 800 } });
  const p2 = await ctx2.newPage();
  const errors2 = [];
  p2.on('console', m => { if (m.type() === 'error') errors2.push(m.text()); });
  p2.on('pageerror', e => errors2.push('JS: ' + e.message));
  await p2.goto(BASE + '/login/', { waitUntil: 'networkidle' });
  await p2.fill('input[name=username]', 'student1@test.local');
  await p2.fill('input[name=password]', 'demo12345');
  await Promise.all([p2.waitForNavigation(), p2.click('button[type=submit], input[type=submit]')]);
  const r = await p2.goto(BASE + `/student/assignment/${ids.assignment}/`, { waitUntil: 'networkidle' });
  const m2 = await p2.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
    comments: document.querySelectorAll('.pf-comment-form').length,
    locked: document.querySelectorAll('.pf-locked').length,
  }));
  console.log(`  ${r.status()} ${m2.scrollW > m2.clientW + 1 ? 'ВЫЛЕТ ' + m2.scrollW : 'ок  '} ` +
    `формы вопросов: ${m2.comments}, плашек «решение откроется»: ${m2.locked}  домашка глазами ученика`);
  if (errors2.length) errors2.forEach(e => console.log('      ! ' + e.slice(0, 160)));

  await browser.close();
})();
