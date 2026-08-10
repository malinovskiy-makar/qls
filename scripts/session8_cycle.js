/**
 * Сквозной сценарий сессии 8.
 *
 * Репетитор: обзор группы (теплокарта, ученики, история работ) → вкладка
 * «Задания» → сводка решений → проверка задачи → «глазами ученика» с
 * выставлением балла → карточка ученика.
 * Затем: своя задача с двумя пунктами → выдать её группе.
 * Затем ученик: решение по пунктам → сдача → вопрос о сложности → разбор.
 *
 * ⚠️ Сценарий сохраняет данные, поэтому работает по ОТДЕЛЬНОЙ базе
 * (`config.settings_check` → db_check.sqlite3). Витрина не портится.
 * ⚠️ Каждый шаг сверяет КОД ОТВЕТА.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/session8_cycle.js [порт]
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

async function open(page, url, name) {
  const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
  check(`${name} (200)`, resp.status() === 200, resp.status());
  return resp.status() === 200;
}

async function login(ctx, who) {
  const users = { tutor: 'tutor@test.local', student: 'student1@test.local' };
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', users[who]);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  return page;
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const tutorCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await login(tutorCtx, 'tutor');

  // ── Обзор группы ──────────────────────────────────────────────────────
  await open(page, '/teacher/groups/2/', 'обзор группы');
  const blocks = await page.$$eval('.panel-title',
    (n) => n.map((e) => e.textContent.trim()));
  check('на обзоре есть теплокарта, ученики и история работ',
        blocks.some((b) => b.includes('темы')) && blocks.includes('Ученики')
        && blocks.includes('История работ'), JSON.stringify(blocks));

  // ── Вкладка «Задания» и сводка решений ────────────────────────────────
  await open(page, '/teacher/groups/2/?tab=assignments', 'вкладка «Задания»');
  await open(page, '/teacher/groups/2/assignments/6/submissions/', 'сводка решений');

  // ── Проверка задачи ───────────────────────────────────────────────────
  await open(page, '/teacher/groups/2/submissions/112/', 'экран проверки');
  const rawTex = await page.evaluate(() => {
    const errs = document.querySelectorAll('.katex-error').length;
    let raw = 0;
    // ⚠️ Исходник формулы ЛЕЖИТ ВНУТРИ `.katex` (MathML-аннотация), и
    // проверка «нет \\begin в тексте» краснела бы на верно нарисованной
    // таблице. Смотрим текст БЕЗ отрисованных формул.
    document.querySelectorAll('.rv-statement, .problem-statement')
      .forEach((el) => {
        const copy = el.cloneNode(true);
        copy.querySelectorAll('.katex').forEach((k) => k.remove());
        if (/\\begin\{|\\hline/.test(copy.textContent)) { raw += 1; }
      });
    return { errs, raw };
  });
  check('на экране проверки нет сырого TeX',
        rawTex.errs === 0 && rawTex.raw === 0, JSON.stringify(rawTex));

  // ── Глазами ученика с выставлением балла ──────────────────────────────
  await open(page, '/teacher/groups/2/assignments/6/students/9/',
             'глазами ученика');
  const collapsed = await page.$$eval('.wr-item[open]', (n) => n.length);
  check('всё свёрнуто при открытии', collapsed === 0, collapsed);

  // ── Карточка ученика ──────────────────────────────────────────────────
  await open(page, '/teacher/student/9/progress/', 'карточка ученика');

  // ── Своя задача с двумя пунктами ──────────────────────────────────────
  await open(page, '/teacher/problems/new/', 'своя задача');
  await page.fill('#id_title', 'Сквозная задача с пунктами');
  await page.fill('#id_statement', 'Спрос $Q_d=100-2P$, предложение $Q_s=4P-20$.');
  await page.click('#add-part-btn');
  await page.click('#add-part-btn');
  const parts = await page.$$('.part-row');
  await parts[0].$eval('[name=part_statement]', (el) => {
    el.value = 'Найдите равновесную цену.';
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await parts[0].$eval('[name=part_answer]', (el) => { el.value = '20'; });
  await parts[1].$eval('[name=part_statement]', (el) => {
    el.value = 'Найдите равновесное количество.';
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await parts[1].$eval('[name=part_answer]', (el) => { el.value = '60'; });
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit].k-btn--main'),
  ]);
  const customId = (page.url().match(/problems\/(\d+)\/edit/) || [])[1];
  check('своя задача с пунктами сохранена', Boolean(customId), page.url());

  // ── Выдать её группе через конструктор подборки ────────────────────────
  await page.goto(`${BASE}/teacher/assignment/build/?kind=homework&group=2`,
                  { waitUntil: 'networkidle' });
  await page.evaluate((id) => {
    sessionStorage.setItem('hw_cart',
      JSON.stringify({ ['c' + id]: { title: 'Сквозная задача с пунктами' } }));
  }, customId);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const items = await page.$$eval('.bd-item', (n) => n.length);
  check('своя задача приехала в конструктор', items === 1, items);
  await page.fill('[name=name]', 'Сквозная работа сессии 8');
  await page.$eval('[name=groups]', (b) => {
    b.checked = true;
    b.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitForTimeout(200);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#submit-btn'),
  ]);
  const workId = (page.url().match(/assignments\/(\d+)\//) || [])[1];
  check('работа создана и открылась', Boolean(workId), page.url());

  // ── Ученик решает по пунктам ──────────────────────────────────────────
  const studentCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const spage = await login(studentCtx, 'student');
  await open(spage, `/student/assignment/${workId}/`, 'домашка у ученика');
  const fields = await spage.$$('input[name^="answer_item_"][name*="_part_c"]');
  check('у ученика поле на каждый пункт', fields.length === 2, fields.length);
  if (fields.length === 2) {
    await fields[0].fill('20');
    await fields[1].fill('60');
  }
  await spage.screenshot({ path: path.join(SHOTS, 'ф06-ученик-отвечает-по-пунктам.png'),
                           fullPage: true });
  // ⚠️ Подтверждение сдачи — РОДНОЙ `window.confirm` (`work_form.js`:
  // подтверждение с фактами «без ответа осталось N»). Обработчик диалога
  // вешаем ДО клика, иначе Playwright отклонит окно и работа не уедет.
  spage.on('dialog', (dialog) => dialog.accept());
  const submit = await spage.$('[data-work-submit]');
  check('кнопка «Отправить домашку» на месте', Boolean(submit));
  if (submit) {
    await Promise.all([
      spage.waitForNavigation({ waitUntil: 'networkidle' }).catch(() => {}),
      submit.click(),
    ]);
  }
  await spage.waitForTimeout(800);

  // ── Разбор у ученика ──────────────────────────────────────────────────
  await open(spage, `/student/work/${workId}/`, 'разбор у ученика');
  const marks = await spage.$$eval('.part-result, .pr-row, .wr-item',
    (n) => n.length);
  check('разбор показывает работу', marks > 0, marks);
  const asked = await spage.$$eval('.wr-diff', (n) => n.length);
  check('у ученика спрашивают сложность работы', asked === 1, asked);
  await spage.screenshot({ path: path.join(SHOTS, 'ф06-разбор-по-пунктам.png'),
                           fullPage: true });

  console.log(`\nитого: ${ok} успешно, ${bad} неудачно`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
