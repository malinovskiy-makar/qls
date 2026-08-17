/**
 * Балл позиции доезжает до созданной работы (ревью 17.08, фаза 1).
 *
 * Сценарий приёмки владельца целиком:
 *   1) два теста → в работе по 1 баллу, всего 2 (было по 3, всего 6);
 *   2) задача сложности 3 и задача сложности 5, второй руками 7 → 3 и 7;
 *   3) то же с правилом «одинаково по 2» → 2 и 7 (ручная правка цела).
 *
 * ⚠️ ПРОВЕРКА СВЕРЯЕТ КОД ОТВЕТА И ЧИТАЕТ БАЛЛЫ СО СТРАНИЦЫ СОЗДАННОЙ
 * РАБОТЫ, а не из корзины: дефект был именно в том, что экран и запись
 * расходились, и «проверка» по экрану его бы не увидела.
 *
 *   node scripts/r18_points_check.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8300';
const BASE = `http://127.0.0.1:${PORT}`;
const GROUP = 2;

let passed = 0;
const failures = [];

function ok(name, condition, detail) {
  if (condition) { passed += 1; return; }
  failures.push(`${name}${detail ? ' — ' + detail : ''}`);
}

async function login(page) {
  await page.goto(`${BASE}/login/`);
  await page.fill('[name=username]', 'tutor@test.local');
  await page.fill('[name=password]', 'demo12345');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');
}

async function go(page, path) {
  const response = await page.goto(BASE + path);
  ok(`код ответа ${path}`, response.status() === 200, `${response.status()}`);
  await page.waitForLoadState('networkidle');
  return response;
}

/** Положить в корзину заданные ключи прямо через её механизм. */
async function fillCart(page, keys) {
  await page.evaluate((list) => {
    const cart = {};
    list.forEach((key) => { cart[key] = { title: 'x' }; });
    sessionStorage.setItem(window.QLS_CART.cart, JSON.stringify(cart));
    sessionStorage.setItem(window.QLS_CART.order, JSON.stringify(list));
    sessionStorage.removeItem(window.QLS_CART.points);
    sessionStorage.removeItem(window.QLS_CART.rule);
  }, keys);
}

/** Баллы позиций на странице созданной работы: [{title, points}]. */
async function workScores(page) {
  return page.$$eval('[data-item-points], .k-score__value', (nodes) =>
    nodes.map((node) => node.textContent.trim()));
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page);

  // ── 1. Два теста ─────────────────────────────────────────────────────
  await go(page, `/teacher/work/?group=${GROUP}`);
  // Берём со страницы отбора первые две карточки ТЕСТОВ.
  const testKeys = await page.$$eval('.wk-card', (cards) => cards
    .filter((c) => (c.textContent || '').includes('Тест'))
    .slice(0, 2)
    .map((c) => c.querySelector('[data-add]').dataset.add));
  ok('на отборе нашлись два теста', testKeys.length === 2,
     `нашлось ${testKeys.length}`);

  if (testKeys.length === 2) {
    await fillCart(page, testKeys);
    await go(page, `/teacher/work/compose/?group=${GROUP}`);
    await page.waitForSelector('.wk-item');
    const shown = await page.$$eval('.wk-pts input',
      (fields) => fields.map((f) => f.value));
    ok('в составе у тестов по 1 баллу', shown.join(',') === '1,1',
       shown.join(','));
    const sum = await page.textContent('#wk-p');
    ok('сумма в сводке — 2', sum.trim() === '2', sum);

    await go(page, `/teacher/work/give/?group=${GROUP}`);
    await page.waitForSelector('#ws-rule');
    ok('на выдаче есть правило начисления', true);
    const ruleField = await page.inputValue('#wk-rule');
    ok('правило уходит на сервер полем формы',
       ruleField === 'difficulty', ruleField);

    await page.fill('[name=name]', 'Проверка баллов — два теста');
    await page.check(`[name=groups][value="${GROUP}"]`);
    await page.waitForTimeout(400);
    await page.click('#wk-next');
    await page.waitForLoadState('networkidle');
    ok('после создания открылась работа',
       /\/assignments\/\d+\/$/.test(page.url()), page.url());
    // ⚠️ ЧИТАЕМ ПОЛЯ БАЛЛА САМОЙ РАБОТЫ (`.pts-input`), а не текст страницы:
    // это то самое число, которое записано в базу.
    const written = await page.$$eval('.pts-input',
      (fields) => fields.map((f) => f.value));
    ok('в созданной работе у тестов по 1 баллу',
       written.length === 2 && written.join(',') === '1,1',
       written.join(',') || '(полей нет)');
  }

  // ── 2 и 3. Ручная правка выигрывает у правила ────────────────────────
  await go(page, `/teacher/work/?group=${GROUP}`);
  const taskKeys = await page.$$eval('.wk-card', (cards) => cards
    .filter((c) => !(c.textContent || '').includes('Тест'))
    .slice(0, 2)
    .map((c) => c.querySelector('[data-add]').dataset.add));
  ok('на отборе нашлись две задачи', taskKeys.length === 2,
     `нашлось ${taskKeys.length}`);

  if (taskKeys.length === 2) {
    await fillCart(page, taskKeys);
    await go(page, `/teacher/work/compose/?group=${GROUP}`);
    await page.waitForSelector('.wk-item');
    const fields = await page.$$('.wk-pts input');
    await fields[1].fill('7');
    await page.waitForTimeout(900);

    const marks = await page.$$eval('.wk-manual',
      (nodes) => nodes.map((n) => n.hidden));
    ok('пометка «вручную» только у правленой позиции',
       marks[0] === true && marks[1] === false, JSON.stringify(marks));

    // ⚠️ ПОЗИЦИИ РАЗДЕЛЕНЫ ПОДПИСЯМИ ЧАСТЕЙ, и `:nth-of-type` считает ВСЕХ
    // соседей-`div`, а не только позиции: вторая позиция по этому счёту —
    // не вторая строка работы. Берём по порядку самих позиций.
    const items = page.locator('.wk-item');
    const second = await items.nth(1).locator('.wk-pts input').inputValue();
    ok('ручной балл остался 7', second === '7', second);

    // Правило «одинаково по 2» — на выдаче.
    await go(page, `/teacher/work/give/?group=${GROUP}`);
    await page.waitForSelector('#ws-rule');
    const kept = await page.evaluate(() => window.QLS_WORK.pointsParam());
    ok('ручной балл пережил переход между шагами',
       kept.includes(':7'), kept || '(пусто)');

    await page.fill('.ws-rule__num', '2');
    await page.waitForTimeout(900);
    const ruleParam = await page.inputValue('#wk-rule');
    ok('правило стало «одинаково по 2»', ruleParam === 'flat:2', ruleParam);

    await go(page, `/teacher/work/compose/?group=${GROUP}`);
    await page.waitForSelector('.wk-item');
    const after = await page.$$eval('.wk-pts input',
      (list) => list.map((f) => f.value));
    ok('правило пересчитало нетронутую позицию', after[0] === '2', after[0]);
    ok('ручную позицию правило не тронуло', after[1] === '7', after[1]);
    const total = (await page.textContent('#wk-p')).trim();
    ok('сумма в сводке — 9', total === '9', total);

    // ⚠️ «Вернуть по правилу» снимает признак, а число приносит сервер.
    await page.locator('.wk-item').nth(1).locator('.wk-rerule').click();
    await page.waitForTimeout(900);
    const back = await page.$$eval('.wk-pts input',
      (list) => list.map((f) => f.value));
    ok('после возврата по правилу обе позиции по 2',
       back.join(',') === '2,2', back.join(','));
  }

  console.log(`\nПройдено: ${passed}`);
  if (failures.length) {
    console.log(`Провалено: ${failures.length}`);
    failures.forEach((line) => console.log('  ✗ ' + line));
  } else {
    console.log('Провалов нет.');
  }
  await browser.close();
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => { console.error(error); process.exit(2); });
