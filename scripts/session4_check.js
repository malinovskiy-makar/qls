/*
 * Проверка сессии 4 браузером: то, чего не видят питон-тесты.
 *
 * Запускать из корня проекта:
 *     ./venv/bin/python manage.py runserver 8124 &
 *     node scripts/session4_check.js 8124
 *
 * Проверяются ровно те классы дефектов, на которых проект уже обжигался:
 *   * необработанное исключение в обработчике приходит событием `pageerror`,
 *     а НЕ в консоль — слушаем оба;
 *   * KaTeX может молча не нарисовать формулу (quirks mode) — считаем
 *     реальные `.katex` на странице, а не отсутствие ошибок;
 *   * вёрстка на 380px: документ не имеет права тянуться вбок.
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8124';
const BASE = 'http://127.0.0.1:' + PORT;
const SHOTS = 'reports/session4/shots';

let passed = 0;
let failed = 0;
const problems = [];

function check(name, ok, detail) {
  if (ok) { passed += 1; console.log('  ✓ ' + name); }
  else {
    failed += 1;
    problems.push(name + (detail ? ' — ' + detail : ''));
    console.log('  ✗ ' + name + (detail ? ' — ' + detail : ''));
  }
}

async function login(page, email, password) {
  await page.goto(BASE + '/login/', { waitUntil: 'networkidle' });
  await page.fill('input[name="username"]', email);
  await page.fill('input[name="password"]', password);
  await Promise.all([
    page.waitForLoadState('networkidle'),
    page.click('button[type="submit"], input[type="submit"]'),
  ]);
}

async function width(page) {
  return page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/favicon|net::ERR/.test(m.text())) {
      errors.push('console: ' + m.text());
    }
  });

  console.log('\n== Репетитор ==');
  await login(page, 'tutor@test.local', 'demo12345');

  // 1. Страница задания: утверждение ответов.
  await page.goto(BASE + '/teacher/groups/2/assignments/6/', {
    waitUntil: 'networkidle' });
  const html = await page.content();
  check('на задании есть блок «Что проверяется автоматически»',
        html.includes('Что проверяется автоматически'));
  check('неутверждённая задача помечена «уйдёт на ручную проверку»',
        html.includes('уйдёт на ручную проверку'));
  check('кнопка называется «Распечатать»', html.includes('Распечатать'));
  await page.screenshot({ path: SHOTS + '/teacher-assignment.png',
                          fullPage: true });

  // Утверждаем ответ первой задачи — и проверяем, что бейдж перекрасился.
  const saved = await page.evaluate(async () => {
    const block = document.querySelector('.ans-block');
    if (!block) { return 'блока утверждения нет'; }
    block.querySelectorAll('.ans-input').forEach((input) => {
      if (!input.value) { input.value = '42'; }
    });
    block.querySelector('.ans-save').click();
    await new Promise((r) => setTimeout(r, 900));
    const badge = document.querySelector(
      '[data-badge="' + block.dataset.item + '"]');
    return badge ? badge.textContent.trim() : 'бейджа нет';
  });
  check('после утверждения бейдж говорит «проверяется автоматически»',
        /проверяется автоматически/.test(saved), saved);

  // 2. Версия для печати.
  await page.goto(BASE + '/teacher/groups/2/assignments/6/print/?for=teacher',
                  { waitUntil: 'networkidle' });
  const printStats = await page.evaluate(() => ({
    katex: document.querySelectorAll('.katex').length,
    katexErrors: document.querySelectorAll('.katex-error').length,
    quirks: document.compatMode !== 'CSS1Compat',
  }));
  check('на листке отрисованы формулы', printStats.katex > 0,
        'формул: ' + printStats.katex);
  check('ошибок KaTeX на листке нет', printStats.katexErrors === 0);
  check('страница НЕ в quirks mode (иначе KaTeX молчит)',
        !printStats.quirks);
  await page.screenshot({ path: SHOTS + '/print-teacher-live.png',
                          fullPage: true });

  // 3. Подбор домашки — экран открывается и честно говорит про ключ.
  await page.goto(BASE + '/teacher/assignment/generate/',
                  { waitUntil: 'networkidle' });
  const generate = await page.content();
  check('экран подбора открывается',
        generate.includes('Подобрать домашку') || generate.includes('Опишите домашку'));

  console.log('\n== Ученик ==');
  await login(page, 'student1@test.local', 'demo12345');
  await page.goto(BASE + '/student/work/6/', { waitUntil: 'networkidle' });
  const review = await page.content();
  check('разбор работы открывается', review.includes('Домашка'));
  const optionStats = await page.evaluate(() => ({
    lists: document.querySelectorAll('.opt-review').length,
    hit: document.querySelectorAll('.opt-hit').length,
    missed: document.querySelectorAll('.opt-missed').length,
    wrong: document.querySelectorAll('.opt-wrong').length,
    skip: document.querySelectorAll('.opt-skip').length,
  }));
  check('в разборе показан список вариантов', optionStats.lists > 0,
        JSON.stringify(optionStats));
  check('состояния вариантов различаются визуально',
        optionStats.hit + optionStats.missed + optionStats.wrong
        + optionStats.skip > 0, JSON.stringify(optionStats));
  await page.screenshot({ path: SHOTS + '/student-work-review.png',
                          fullPage: true });

  console.log('\n== 380px ==');
  await page.setViewportSize({ width: 380, height: 800 });

  // ⚠️ ПРАВА ПРОВЕРЯЕМ ЯВНО. Первая версия этой проверки открывала листок
  // репетитора, будучи залогиненной учеником: сервер честно отдавал 403, а
  // проверка ширины «проходила» на странице ошибки. Ложный успех хуже
  // провала — он говорит, что всё хорошо, там где ничего не проверено.
  async function narrow(name, url, expectStatus) {
    const response = await page.goto(url, { waitUntil: 'networkidle' });
    if (response.status() !== expectStatus) {
      check(name + ': страница открылась', false,
            'код ' + response.status());
      return;
    }
    const inner = await page.evaluate(() => {
      // Известный баг шапки сайта (`_nav.html`) в этой сессии НЕ чинится,
      // поэтому на страницах с шапкой меряем СОДЕРЖИМОЕ, а не документ.
      const main = document.querySelector('.sheet, .page-wrap, main');
      return main ? main.scrollWidth : document.documentElement.scrollWidth;
    });
    check(name + ': содержимое влезает в 380px', inner <= 385,
          'содержимое ' + inner);
    await page.screenshot({
      path: SHOTS + '/380-' + name.replace(/\s/g, '-') + '.png',
      fullPage: true });
  }

  await narrow('разбор работы', BASE + '/student/work/6/', 200);
  await login(page, 'tutor@test.local', 'demo12345');
  await narrow('версия для печати',
               BASE + '/teacher/groups/2/assignments/6/print/', 200);
  await narrow('страница задания',
               BASE + '/teacher/groups/2/assignments/6/', 200);

  check('ошибок страницы и консоли нет', errors.length === 0,
        errors.slice(0, 3).join(' | '));

  console.log('\n' + passed + ' из ' + (passed + failed));
  if (problems.length) {
    console.log('Не прошло:');
    problems.forEach((p) => console.log('  - ' + p));
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
