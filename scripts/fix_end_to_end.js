/*
 * Сквозной сценарий сессии фиксов после приёмки — девять шагов из задания,
 * подряд, в одном браузере.
 *
 * ⚠️ Зачем именно браузером. Всё, что здесь проверяется, питон-тесты видят
 * лишь наполовину: стёрлось ли поле по нажатию, читается ли надпись на
 * кнопке, спрятан ли элемент НА САМОМ ДЕЛЕ (а не только атрибутом) — это
 * решается в браузере. Прошлые сессии дважды ловили тут настоящие поломки.
 *
 * Запуск ИЗ КОРНЯ проекта:  node scripts/fix_end_to_end.js [порт]
 * Перед запуском: manage.py seed_platform_demo и поднятый сервер.
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = 'reports/fix/08-end-to-end';
const HW = '/teacher/groups/2/assignments/6/';

let failures = 0;
const shots = [];

function check(name, ok, extra) {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${extra ? ' — ' + extra : ''}`);
  if (!ok) failures += 1;
}

async function login(page, who) {
  const users = {
    tutor: ['tutor@test.local', 'demo12345'],
    student: ['student1@test.local', 'demo12345'],
  };
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', users[who][0]);
  await page.fill('input[name=password]', users[who][1]);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

async function shot(page, name, caption) {
  fs.mkdirSync(OUT, { recursive: true });
  const file = `${OUT}/${name}.png`;
  await page.screenshot({ path: file, fullPage: true });
  shots.push({ file: `${name}.png`, caption });
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await login(page, 'tutor');
  await page.goto(BASE + HW, { waitUntil: 'networkidle' });
  const text = () => page.evaluate(() => document.body.innerText);

  // 1. «Ждёт проверки» — ненулевое число.
  const waiting = await page.$$eval('.summary-cell', (cells) => {
    const cell = cells.find((c) => c.textContent.includes('Ждёт проверки'));
    return cell ? cell.querySelector('.summary-value').textContent.trim() : null;
  });
  check('«Ждёт проверки» показывает ненулевое число',
        waiting && Number(waiting) > 0, `${waiting}`);

  // 2. Янтарная позиция есть БЕЗ ручного вмешательства.
  const warn = await page.$('.check-state.is-warn');
  check('янтарная позиция есть сама по себе', !!warn);
  await shot(page, '01-assignment',
             'Страница задания: «Ждёт проверки» не ноль, есть янтарные позиции, баллы заперты.');

  // 3. Правка эталона переживает переключение режима туда и обратно.
  const itemId = await warn.getAttribute('data-check');
  const probe = 'сквозная проверка 777';
  await warn.$eval('.ans-input', (e, v) => { e.value = v; }, probe);
  await warn.$eval('.ans-toggle', (b) => b.click());
  await page.waitForFunction(
    (id) => document.querySelector(`[data-check="${id}"]`).classList.contains('is-ok'),
    itemId, { timeout: 5000 });
  const box = await page.$(`[data-check="${itemId}"]`);
  await box.$eval('.ans-toggle', (b) => b.click());
  await page.waitForFunction(
    (id) => document.querySelector(`[data-check="${id}"]`).classList.contains('is-warn'),
    itemId, { timeout: 5000 });
  check('значение в поле эталона на месте после двух переключений',
        (await box.$eval('.ans-input', (e) => e.value)) === probe);

  // 4. Одна кнопка, надпись по состоянию, «готово» нигде нет.
  const shown = await box.$$eval('.ans-actions .k-btn',
    (n) => n.filter((b) => getComputedStyle(b).display !== 'none')
            .map((b) => b.textContent.trim()));
  check('кнопка в блоке ОДНА', shown.length === 1, shown.join(' | '));
  check('надпись соответствует состоянию',
        shown[0] === 'Включить автопроверку', shown[0]);
  check('слова «готово» на странице нет', !/\bготово\b/i.test(await text()));

  // 5. Максимальный балл заперт, и написано почему.
  check('поля правки балла нет', !(await page.$('.pts-input')));
  check('крупная цифра балла осталась', !!(await page.$('.k-score__value')));
  check('экран объясняет, почему заперто',
        (await text()).toLowerCase().includes('работу уже сдавали'));

  // 6. Комментарий «заметка для себя» — ученик его не видит.
  const form = await page.$('.comment-form');
  await form.$eval('textarea', (e) => { e.value = 'Сквозная заметка только себе'; });
  await form.$eval('.vis-select', (e) => {
    e.value = 'self'; e.dispatchEvent(new Event('change'));
  });
  await form.$eval('button[type=submit]', (b) => b.click());
  await page.waitForFunction(
    () => document.body.innerText.includes('Сквозная заметка только себе'),
    null, { timeout: 5000 });
  check('заметка появилась у автора', true);
  const noteMark = await page.$$eval('.comment-private',
    (n) => n.map((e) => e.textContent.trim()));
  check('заметка помечена «только я»', noteMark.includes('только я'),
        noteMark.join(' | '));
  await shot(page, '02-talk',
             'Переписка: реплика ученика на подложке, пометки видимости только у исключений.');

  // 7. Работа Петра: ответ `30` без полного балла, пустые задачи с нулём.
  await page.goto(`${BASE}/teacher/groups/2/assignments/6/submissions/`,
                  { waitUntil: 'networkidle' });
  const buttons = await page.$$eval('.stu-card .k-btn',
    (n) => n.map((b) => b.textContent.trim()));
  check('в сводке есть кнопка «Смотреть работу»',
        buttons.includes('Смотреть работу'), buttons.join(' | '));
  const eyes = await page.$('.stu-eyes');
  check('«глазами ученика» — отдельная тихая ссылка', !!eyes);
  await shot(page, '03-submissions',
             'Сводка решений: главная кнопка ведёт на проверку, разбор глазами ученика — тихой ссылкой.');

  // «Смотреть работу» обязана открыть страницу ПРОВЕРКИ.
  const seeWork = (await page.$$('.stu-card .k-btn')).find(async () => true);
  const hrefs = await page.$$eval('.stu-card .k-btn',
    (n) => n.map((b) => [b.textContent.trim(), b.getAttribute('href')]));
  const pair = hrefs.find((h) => h[0] === 'Смотреть работу');
  check('«Смотреть работу» ведёт на проверку',
        !!pair && /\/submission\/|\/submissions\/\d+/.test(pair[1] || '')
        || (!!pair && pair[1].includes('/review')), pair && pair[1]);

  // 8. Разбор глазами ученика: `30` без полного балла, пустые задачи с 0.
  await login(page, 'student');
  // ⚠️ `/student/work/<pk>/` принимает pk ЗАДАНИЯ, а не сдачи. Ошибка в
  // адресе не даёт ошибки на экране: открывается ДРУГАЯ работа, и проверка
  // молча меряет не то. Поймано этим же сценарием.
  await page.goto(`${BASE}/student/work/6/`, { waitUntil: 'networkidle' });
  const workName = await page.$eval('.wr-name, h1, .page-title',
    (e) => e.textContent.trim()).catch(() => '');
  check('открыта именно домашка №3', workName.includes('Домашка №3'), workName);
  const rows = await page.$$eval('.wr-item', (items) => items.map((el) => ({
    title: el.querySelector('.wr-title').textContent.trim(),
    flag: el.querySelector('.wr-flag').textContent.trim(),
    points: el.querySelector('.wr-points').textContent.replace(/\s+/g, ' ').trim(),
    state: el.dataset.state,
  })));
  const elasticity = rows.find((r) => r.title.includes('Эластичность спроса по цене'));
  check('задача с ответом «30» НЕ имеет полного балла',
        !!elasticity && !/^2 \/ 2/.test(elasticity.points),
        elasticity && `${elasticity.flag} · ${elasticity.points}`);
  const blanks = rows.filter((r) => r.state === 'blank');
  check('задачи без ответа показывают 0, а не прочерк',
        blanks.length > 0 && blanks.every((r) => r.points.startsWith('0')),
        blanks.map((r) => r.points).join(' | '));
  check('ученик НЕ видит заметку преподавателя для себя',
        !(await text()).includes('Сквозная заметка только себе'));
  await shot(page, '04-student-work',
             'Разбор глазами ученика: пустые задачи получили честный ноль, ответ «30» полного балла не имеет.');

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  fs.writeFileSync(`${OUT}/shots.json`, JSON.stringify(shots, null, 2));
  await browser.close();
  console.log(failures ? `\nПРОВАЛЕНО: ${failures}` : '\nсквозной сценарий пройден целиком');
  process.exit(failures ? 1 : 0);
})();
