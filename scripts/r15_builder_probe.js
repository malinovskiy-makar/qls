/**
 * Конструктор работы: одна корзина, третья вкладка, поле на весь экран
 * (ревью 15.08, фаза 11). Проверка в живом браузере.
 *
 * Запуск: node scripts/r15_builder_probe.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
let passed = 0, failed = 0;

function ok(name, condition, extra) {
  if (condition) { passed += 1; console.log('  ok  ' + name); }
  else { failed += 1; console.log('  FAIL ' + name + (extra ? ' — ' + extra : '')); }
}

async function login(page) {
  await page.goto(BASE + '/login/');
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1360, height: 950 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await login(page);

  console.log('\n— 11.1 Одна корзина на работу —');
  await page.goto(BASE + '/teacher/assignment/create/?group=2');
  await page.locator('.problem-card .btn-add').first().click();
  await page.locator('.problem-card .btn-add').nth(1).click();
  const cartBefore = await page.evaluate(() =>
    Object.keys(JSON.parse(sessionStorage.getItem('work_cart') || '{}')));
  ok('в корзине две задачи', cartBefore.length === 2, cartBefore.join(','));

  // Переключаемся на контрольную — это переход по ссылке.
  await page.locator('.bh-kind__opt', { hasText: 'Контрольная' }).click();
  await page.waitForLoadState('domcontentloaded');
  const cartAfter = await page.evaluate(() =>
    Object.keys(JSON.parse(sessionStorage.getItem('work_cart') || '{}')));
  ok('корзина пережила переключение на контрольную',
     cartAfter.length === 2 && cartAfter.join() === cartBefore.join(),
     cartAfter.join(','));
  const chosen = await page.locator('#cart-list .cart-item, .cart-item').count();
  ok('выбранное видно в корзине контрольной', chosen === 2, 'строк ' + chosen);

  await page.locator('.bh-kind__opt', { hasText: 'Домашка' }).click();
  await page.waitForLoadState('domcontentloaded');
  const cartBack = await page.evaluate(() =>
    Object.keys(JSON.parse(sessionStorage.getItem('work_cart') || '{}')));
  ok('и обратный переход её не потерял', cartBack.length === 2, cartBack.join(','));

  console.log('\n— 11.2 Третья вкладка «Мои задачи» —');
  const tabs = page.locator('.picker-tab');
  ok('вкладок три', (await tabs.count()) === 3, 'найдено ' + (await tabs.count()));
  const names = await tabs.evaluateAll(list => list.map(n => n.textContent.trim()));
  ok('третья называется «Мои задачи»', /^Мои задачи \(\d+\)$/.test(names[2]),
     names.join(' | '));
  await tabs.nth(2).click();
  const own = page.locator('#pane-own .problem-card');
  ok('внутри карточки своих задач', (await own.count()) > 0,
     'карточек ' + (await own.count()));
  const key = await own.first().getAttribute('data-pid');
  ok('ключ карточки — «c<номер>»', /^c\d+$/.test(key), key);
  ok('кнопка «Условие» на месте',
     await own.first().locator('.btn-preview').isVisible());

  await own.first().locator('.btn-preview').click();
  await page.waitForTimeout(500);
  const modalTitle = await page.locator('#modal-title').textContent();
  ok('окно условия показывает свою задачу', modalTitle && modalTitle !== '…',
     modalTitle);
  await page.keyboard.press('Escape');

  await own.first().locator('.btn-add').click();
  ok('своя задача легла в ту же корзину',
     (await page.evaluate(() =>
       Object.keys(JSON.parse(sessionStorage.getItem('work_cart') || '{}'))
     )).includes(key));
  ok('карточка приглушилась',
     await own.first().evaluate(n => n.classList.contains('is-added')));

  console.log('\n— 11.5 Занятие из адреса отмечено —');
  const checked = await page.locator('input[name=groups]:checked')
    .evaluateAll(list => list.map(n => n.value));
  ok('отмечено ровно занятие из адреса',
     checked.length === 1 && checked[0] === '2', checked.join(','));

  console.log('\n— 11.3 Вход на «Мои задачи» —');
  await page.goto(BASE + '/teacher/groups/');
  const link = page.locator('a[href="/teacher/problems/"]');
  ok('ссылка «Мои задачи» есть на экране «Ученики»', await link.count() > 0);
  await link.first().click();
  await page.waitForLoadState('domcontentloaded');
  ok('она ведёт на страницу своих задач',
     page.url().includes('/teacher/problems/'), page.url());

  console.log('\n— 11.4 Поле на весь экран —');
  await page.goto(BASE + '/teacher/problems/new/');
  const box = page.locator('.zoom-box').first();
  ok('кнопка «развернуть» есть', await box.locator('.zoom-btn').isVisible());
  await box.locator('textarea').fill('Спрос задан $Q_d = 100 - 2P$.');
  await box.locator('.zoom-btn').click();
  ok('поле развернулось',
     await box.evaluate(n => n.classList.contains('is-zoomed')));
  const big = await box.locator('textarea').boundingBox();
  ok('поле занимает пол-экрана и больше', big && big.height > 300,
     JSON.stringify(big));
  ok('введённое сохранилось',
     (await box.locator('textarea').inputValue()).includes('100 - 2P'));
  ok('кнопка формул поехала вместе с полем',
     await box.locator('.mf-toggle').count() > 0);
  const preview = box.locator('.zoom-preview__body');
  ok('живой предпросмотр рисует формулу',
     (await preview.innerHTML()).includes('katex'),
     (await preview.innerHTML()).slice(0, 60));
  await box.locator('textarea').type(' Ещё строка.');
  await page.waitForTimeout(200);
  ok('предпросмотр обновляется на лету',
     (await preview.textContent()).includes('Ещё строка'));
  await page.keyboard.press('Escape');
  ok('Escape сворачивает',
     !(await box.evaluate(n => n.classList.contains('is-zoomed'))));
  await box.locator('.zoom-btn').click();
  await box.locator('.zoom-head .k-btn').click();
  ok('кнопка «Свернуть» тоже',
     !(await box.evaluate(n => n.classList.contains('is-zoomed'))));
  ok('текст пережил оба сворачивания',
     (await box.locator('textarea').inputValue()).includes('Ещё строка'));

  // Пункт, добавленный уже после загрузки страницы.
  await page.locator('#add-part-btn').click();
  await page.waitForTimeout(150);
  const partBox = page.locator('#parts-list .zoom-box').first();
  ok('у нового пункта кнопка «развернуть» появилась сама',
     await partBox.locator('.zoom-btn').count() > 0);

  ok('ошибок в консоли нет', errors.length === 0, errors.join(' | '));
  console.log('\nИтого: ' + passed + ' ок, ' + failed + ' провалов');
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
