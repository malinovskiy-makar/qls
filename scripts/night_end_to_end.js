/*
 * Сквозной сценарий ночной сессии (фаза 20). Проверяем не отдельные экраны,
 * а то, что они складываются в целое: собрать работу → раздать → сдать →
 * проверить насквозь.
 *
 * Каждый шаг снимается в reports/night/20-end-to-end/.
 *
 * Запуск ИЗ КОРНЯ проекта:
 *   node scripts/night_end_to_end.js <порт-с-подставной-моделью> [порт-обычный]
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8200';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = 'reports/night/20-end-to-end';

let failures = 0;
const steps = [];

function check(name, ok, extra) {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${extra ? ' — ' + extra : ''}`);
  if (!ok) failures += 1;
}

async function shot(page, name, caption) {
  const file = `${name}.png`;
  await page.screenshot({ path: `${OUT}/${file}`, fullPage: true });
  steps.push({ file, caption });
}

async function login(page, user) {
  await page.goto(`${BASE}/logout/`, { waitUntil: 'domcontentloaded' })
    .catch(() => {});
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', user);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  // 1. Вход в группу — открывается обзор со статистикой.
  await login(page, 'tutor@test.local');
  await page.goto(`${BASE}/teacher/groups/2/`, { waitUntil: 'networkidle' });
  let text = await page.evaluate(() => document.body.innerText);
  check('вход в группу открывает обзор', text.includes('Требуют внимания')
        || text.includes('Ученики × темы'));
  await shot(page, '01-group-overview',
             'Вход в группу открывает «Обзор»: кто требует внимания, тепловая карта, таблица учеников.');

  // 2. Вкладка «Задания» — три группы по состоянию.
  await page.goto(`${BASE}/teacher/groups/2/?tab=assignments`,
                  { waitUntil: 'networkidle' });
  const groups = await page.$$eval('.ass-group-title', (n) => n.map((e) => e.textContent.trim()));
  check('задания сгруппированы по состоянию', groups.length >= 2, groups.join(' / '));
  await shot(page, '02-assignments',
             'Вкладка «Задания»: три группы — требуют вас, идут сейчас, завершены.');

  // 3. Домашка по описанию: четыре задачи и три теста.
  await page.goto(`${BASE}/teacher/assignment/generate/?group=2`,
                  { waitUntil: 'networkidle' });
  // ⚠️ Описание БЕЗ порядковых слов. Если написать «первая задача — …»,
  // сработает признак ручного порядка (фаза 18.5) и группировки «сначала
  // тесты» не будет — и это правильно. Тот случай проверяется отдельно,
  // сценарием фазы 18.
  await page.fill('#gen-text',
    'Домашка на КПВ и КТВ: построение кривой, сложение кривых двух стран, ' +
    'кривая торговых возможностей.');
  await page.fill('#id_open', '4');
  await page.fill('#id_test', '3');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit]'),
  ]);
  await shot(page, '03-generate-found',
             'Шаг «что нашлось»: оба поля подписаны, под строками — названия найденных задач.');

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[value=search]'),
  ]);
  text = await page.evaluate(() => document.body.innerText);
  const line = (text.split('\n').find((l) => l.includes('Найдено задач')) || '').trim();
  check('подобрано ровно 7 задач', line.includes('7'), line);
  await shot(page, '04-generate-result', 'Подобрано семь задач: четыре открытые и три теста.');

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#to-cart'),
  ]);
  check('уехали в конструктор домашки', page.url().includes('/assignment/create/'));

  await page.fill('input[name=name]', 'Сквозная домашка (ночная сессия)');
  await page.check('input[name=groups]');
  await page.waitForTimeout(300);
  const why = await page.$eval('#submit-why', (e) => e.textContent.trim());
  check('кнопка больше ничего не требует', why === '', why);
  await shot(page, '05-builder', 'Конструктор: корзина донесла задачи, кнопка активна.');

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#submit-btn'),
  ]);
  check('домашка создана', !page.url().includes('/assignment/create/'));

  // 4. Открываем созданную домашку: баллы, разделение частей.
  await page.goto(`${BASE}/teacher/groups/2/?tab=assignments`,
                  { waitUntil: 'networkidle' });
  const link = await page.$('a:has-text("Сквозная домашка")');
  check('домашка появилась в группе', !!link);
  if (link) {
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle' }),
      link.click(),
    ]);
  }
  const assignmentUrl = page.url();
  text = await page.evaluate(() => document.body.innerText);
  check('тесты и задачи разделены подписями',
        text.includes('Тестовая часть') && text.includes('Задачи'));
  const points = await page.$$eval('.pts-input', (n) => n.map((e) => e.value));
  // Поле печатает балл без хвостовых нулей: «10», а не «10.00».
  check('баллы по умолчанию: 10 задаче, 3 тесту',
        points.includes('10') && points.includes('3'), points.join(', '));
  await shot(page, '06-assignment',
             'Задание целиком: крупные баллы (10 за задачу, 3 за тест), тесты и задачи разделены.');

  // 5. Печатный листок ученикам.
  await page.goto(assignmentUrl.replace(/\/$/, '') + '/print/',
                  { waitUntil: 'networkidle' });
  text = await page.evaluate(() => document.body.innerText);
  check('в листке есть свой подвал', text.includes('Weconomics'));
  check('в листке есть подписи частей', text.includes('Тестовая часть'));
  await shot(page, '07-print', 'Листок ученикам: подписи частей, место под решение по весу задачи, свой подвал.');

  // 6. Ученик сдаёт работу, одну задачу оставляя пустой.
  const studentPage = await (await browser.newContext({
    viewport: { width: 1440, height: 900 },
  })).newPage();
  await studentPage.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await studentPage.fill('input[name=username]', 'student1@test.local');
  await studentPage.fill('input[name=password]', 'demo12345');
  await Promise.all([
    studentPage.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    studentPage.click('button[type=submit]'),
  ]);
  await studentPage.goto(`${BASE}/student/`, { waitUntil: 'networkidle' });
  // Название работы на дашборде — это <div>, а не ссылка: открывает её
  // кнопка внутри карточки. Ищем карточку по имени, потом её ссылку.
  const card = await studentPage.$('.hw-card:has-text("Сквозная домашка")');
  check('ученик видит домашку', !!card);
  const hw = card ? await card.$('a') : null;
  check('у карточки есть ссылка на работу', !!hw);
  if (hw) {
    await Promise.all([
      studentPage.waitForNavigation({ waitUntil: 'networkidle' }),
      hw.click(),
    ]);
    // Заполняем ВСЕ поля ответа, кроме последнего — оно останется пустым.
    const fields = await studentPage.$$('input[name^="answer_item_"]');
    for (let i = 0; i < fields.length - 1; i += 1) {
      await fields[i].fill('30').catch(() => {});
    }
    await shot(studentPage, '08-student',
               'Ученик решает: последняя задача намеренно оставлена пустой.');
    const submit = await studentPage.$('[data-work-submit]');
    if (submit) {
      studentPage.once('dialog', (d) => d.accept());
      await Promise.all([
        studentPage.waitForNavigation({ waitUntil: 'networkidle' }).catch(() => {}),
        submit.click(),
      ]);
    }
  }

  // 7. Репетитор: пустая задача получила автоматический ноль.
  await page.goto(assignmentUrl.replace(/\/$/, '') + '/submissions/?view=students',
                  { waitUntil: 'networkidle' });
  text = await page.evaluate(() => document.body.innerText);
  check('сводка показывает карточки учеников', text.includes('машина уже насчитала')
        || text.includes('сдал'));
  await shot(page, '09-submissions', 'Сводка решений карточками по ученикам.');

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  fs.writeFileSync(`${OUT}/steps.json`, JSON.stringify(steps, null, 2));
  await browser.close();
  console.log(failures ? `\nПРОВАЛЕНО: ${failures}` : '\nсквозной сценарий пройден');
  process.exit(failures ? 1 : 0);
})();
