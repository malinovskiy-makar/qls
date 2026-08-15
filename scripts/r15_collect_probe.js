/**
 * Конструктор подборки: позиция целиком, порядок, два предпросмотра
 * (ревью 15.08, фаза 12).
 *
 * Запуск: node scripts/r15_collect_probe.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
let passed = 0, failed = 0;

function ok(name, condition, extra) {
  if (condition) { passed += 1; console.log('  ok  ' + name); }
  else { failed += 1; console.log('  FAIL ' + name + (extra ? ' — ' + extra : '')); }
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1360, height: 950 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE + '/login/');
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);

  // Набираем корзину из каталога, затем идём в конструктор подборки.
  await page.goto(BASE + '/teacher/assignment/create/?group=2');
  for (let i = 0; i < 3; i++) {
    await page.locator('.problem-card .btn-add').nth(i).click();
  }
  await page.goto(BASE + '/teacher/assignment/build/?group=2');
  await page.waitForSelector('.bd-item');

  console.log('\n— Название блока —');
  const head = await page.locator('.bd-head h2').textContent();
  ok('блок называется по тому, что показывает', head.trim() === 'Состав работы',
     head);

  console.log('\n— Позиция раскрывается целиком —');
  const first = page.locator('.bd-item').first();
  ok('кнопка раскрытия есть', await first.locator('.bd-more').isVisible());
  await first.locator('.bd-more').click();
  const full = first.locator('.bd-full');
  ok('условие показано', (await full.textContent()).length > 40);
  ok('видно тип и сложность',
     (await full.locator('.bd-flags').textContent()).includes('сложность'));
  ok('сказано про эталонное решение',
     /решени/.test(await full.locator('.bd-flags').textContent()));
  ok('формулы отрисованы, а не сырым кодом',
     (await full.innerHTML()).includes('katex')
     || !(await full.textContent()).includes('$'),
     (await full.textContent()).slice(0, 60));
  await first.locator('.bd-more').click();
  ok('сворачивается обратно', await full.isHidden());

  console.log('\n— Порядок: кнопки —');
  const before = await page.locator('.bd-name')
    .evaluateAll(list => list.map(n => n.textContent));
  ok('у первой позиции «вверх» недоступна',
     await page.locator('.bd-item .bd-up').first().isDisabled());
  await page.locator('.bd-item').nth(1).locator('.bd-up').click();
  await page.waitForTimeout(600);
  const after = await page.locator('.bd-name')
    .evaluateAll(list => list.map(n => n.textContent));
  ok('вторая поднялась на первое место',
     after[0] === before[1] && after[1] === before[0],
     before.join(' | ') + ' → ' + after.join(' | '));
  const cartOrder = await page.evaluate(() =>
    Object.keys(JSON.parse(sessionStorage.getItem('work_cart') || '{}')));
  ok('порядок сохранён в корзине, а не только на экране',
     cartOrder.length === 3, cartOrder.join(','));
  const manual = await page.locator('#manual-order-input').inputValue();
  ok('ручной порядок отменяет автоперестановку', manual === '1', manual);

  console.log('\n— Порядок: перетаскивание —');
  const dragOk = await page.evaluate(() => {
    const items = document.querySelectorAll('.bd-item');
    return items.length > 1 && items[0].getAttribute('draggable') === 'true';
  });
  ok('позиции перетаскиваются', dragOk);

  console.log('\n— Как увидит ученик —');
  await page.locator('#bd-eyes').click();
  const eyes = page.locator('#bd-eyes-box');
  ok('окно открылось', await eyes.evaluate(n => n.classList.contains('is-open')));
  const tasks = await eyes.locator('.bd-eyes__task').count();
  ok('в окне все задачи', tasks === 3, 'задач ' + tasks);
  ok('места для ответа нарисованы',
     await eyes.locator('.bd-eyes__field').count() > 0);
  ok('ответов ученику не показываем',
     !(await eyes.textContent()).includes('Ответ:'));
  await page.keyboard.press('Escape');
  ok('Escape закрывает',
     !(await eyes.evaluate(n => n.classList.contains('is-open'))));

  console.log('\n— Печатный лист до создания работы —');
  await page.fill('#picker-form [name=name]', 'Проба листка');
  await page.waitForTimeout(300);
  const [sheet] = await Promise.all([
    context.waitForEvent('page'),
    page.locator('button[form=bd-print-form]').click(),
  ]);
  await sheet.waitForLoadState('domcontentloaded');
  const sheetText = await sheet.locator('body').textContent();
  ok('лист открылся отдельной вкладкой', sheet.url().includes('/cart/print/'));
  ok('название взято из настроек', sheetText.includes('Проба листка'));
  ok('сказано, что работа ещё не создана',
     sheetText.includes('работа ещё не создана'));
  const sheetTasks = await sheet.locator('.task').count();
  ok('задачи на листе те же', sheetTasks === 3, 'задач ' + sheetTasks);
  await sheet.close();

  console.log('\n— 380 пикселей —');
  await page.setViewportSize({ width: 380, height: 760 });
  await page.reload();
  await page.waitForSelector('.bd-item');
  await page.locator('.bd-item .bd-more').first().click();
  const width = await page.evaluate(() => {
    const box = document.querySelector('.bd-full');
    return box ? box.getBoundingClientRect().right : 0;
  });
  ok('раскрытая позиция помещается в экран', width <= 381, 'правый край ' + width);

  ok('ошибок в консоли нет', errors.length === 0, errors.join(' | '));
  console.log('\nИтого: ' + passed + ' ок, ' + failed + ' провалов');
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
