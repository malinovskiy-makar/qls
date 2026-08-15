/**
 * Своё поле даты и свой календарь — проверка в живом браузере
 * (ревью 15.08, фаза 10).
 *
 * Питон-тесты проверяют разбор маски исполнением в node, но НЕ видят
 * главного: что окно вообще открывается, что клик по дню ведёт к панели
 * времени и что значение доезжает до скрытого поля с именем. Страница
 * отдаёт 200 при любой ошибке скрипта — только браузер это ловит.
 *
 * Запуск (из корня проекта, сервер проверки на 8199):
 *   node scripts/r15_date_probe.js [порт]
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
  await page.click('button[type=submit], input[type=submit]');
  await page.waitForLoadState('networkidle');
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));

  await login(page);

  console.log('\n— Поле срока на конструкторе домашки —');
  const response = await page.goto(BASE + '/teacher/assignment/create/');
  ok('страница открылась', response.status() === 200, 'код ' + response.status());

  const box = page.locator('[data-k-date]').first();
  ok('обёртка готова (is-ready)', await box.evaluate(n => n.classList.contains('is-ready')));
  ok('родное поле спрятано',
     await box.locator('.k-date__native').evaluate(n => getComputedStyle(n).display === 'none'));

  // --- Маска: набираем ОДНИ ЦИФРЫ, как владелец ---------------------------
  const text = box.locator('.k-date__text');
  await text.click();
  await text.type('20082026 1830', { delay: 12 });
  ok('маска расставила знаки', (await text.inputValue()) === '20.08.2026, 18:30',
     await text.inputValue());
  await text.blur();
  const native = box.locator('.k-date__native');
  ok('значение уехало в поле с именем',
     (await native.inputValue()) === '2026-08-20T18:30', await native.inputValue());

  // --- Неполный ввод объясняется словами ---------------------------------
  await text.fill('');
  await text.type('2008', { delay: 10 });
  await text.blur();
  const err = box.locator('.k-date__err');
  ok('неполный ввод не проходит молча', await err.isVisible());
  ok('в отказе есть объяснение', ((await err.textContent()) || '').length > 15);
  ok('прежнее значение уцелело',
     (await native.inputValue()) === '2026-08-20T18:30', await native.inputValue());

  // --- Календарь: сначала дата, потом время ------------------------------
  await box.locator('.k-date__pick').click();
  ok('окно открылось', await box.locator('.k-cal').isVisible());
  ok('первый шаг — сетка месяца',
     await box.locator('.k-cal__step--date').isVisible());
  ok('панель времени пока скрыта',
     !(await box.locator('.k-cal__step--time').isVisible()));

  const month = (await box.locator('[data-cal-title]').textContent()).trim();
  await box.locator('[data-cal-next]').click();
  ok('месяц листается',
     (await box.locator('[data-cal-title]').textContent()).trim() !== month);
  await box.locator('[data-cal-prev]').click();

  await box.locator('.k-cal__day:not(.is-out)').nth(9).click();
  ok('после дня открылась панель времени',
     await box.locator('.k-cal__step--time').isVisible());
  ok('сетка месяца ушла',
     !(await box.locator('.k-cal__step--date').isVisible()));

  await box.locator('[data-cal-hours] .k-cal__pick').nth(9).click();
  await box.locator('[data-cal-minutes] .k-cal__pick').nth(3).click();
  const picked = await native.inputValue();
  ok('время попало в значение', /T09:15$/.test(picked), picked);
  ok('поле показывает выбранное',
     (await text.inputValue()).endsWith('09:15'), await text.inputValue());

  await box.locator('[data-cal-done]').click();
  ok('«Готово» закрывает окно', !(await box.locator('.k-cal').isVisible()));

  // --- Escape и клик вне -------------------------------------------------
  await box.locator('.k-date__pick').click();
  await page.keyboard.press('Escape');
  ok('Escape закрывает', !(await box.locator('.k-cal').isVisible()));
  await box.locator('.k-date__pick').click();
  await page.mouse.click(5, 5);
  ok('клик вне закрывает', !(await box.locator('.k-cal').isVisible()));

  // --- Клавиатура: стрелки двигают по дням, Enter выбирает ---------------
  await box.locator('.k-date__pick').click();
  const before = await native.inputValue();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Enter');
  const after = await native.inputValue();
  ok('стрелка и Enter дают тот же результат, что мышь', before !== after,
     before + ' → ' + after);
  ok('после Enter открыта панель времени',
     await box.locator('.k-cal__step--time').isVisible());

  // --- «Очистить» --------------------------------------------------------
  await page.keyboard.press('Escape');
  await box.locator('.k-date__pick').click();
  if (await box.locator('.k-cal__step--time').isVisible()) {
    await box.locator('[data-cal-back]').click();
  }
  await box.locator('[data-cal-clear]').click();
  ok('«Очистить» обнуляет срок', (await native.inputValue()) === '',
     await native.inputValue());
  ok('и текстовое поле тоже', (await text.inputValue()) === '');

  // --- Узкий экран: лист снизу -------------------------------------------
  console.log('\n— 380 пикселей —');
  await page.setViewportSize({ width: 380, height: 740 });
  await page.reload();
  const narrow = page.locator('[data-k-date]').first();
  await narrow.locator('.k-date__pick').click();
  const rect = await narrow.locator('.k-cal').boundingBox();
  const style = await narrow.locator('.k-cal').evaluate(n => getComputedStyle(n).position);
  ok('окно — лист снизу', style === 'fixed', style);
  ok('в экран влезает', rect && rect.x >= 0 && rect.x + rect.width <= 381,
     JSON.stringify(rect));
  const docWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  ok('страницу вбок не тянет (кроме известной поломки меню)', docWidth <= 940,
     'scrollWidth ' + docWidth);

  console.log('\n— Все три поля на конструкторе контрольной —');
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(BASE + '/teacher/groups/2/exams/new/');
  const boxes = page.locator('[data-k-date].is-ready');
  ok('поля готовы', (await boxes.count()) >= 3, 'найдено ' + (await boxes.count()));
  const names = await page.locator('[data-k-date] .k-date__native')
    .evaluateAll(list => list.map(n => n.name));
  ok('имена полей не изменились',
     ['deadline', 'starts_at', 'ends_at'].every(n => names.includes(n)),
     names.join(','));

  ok('ошибок в консоли нет', errors.length === 0, errors.join(' | '));

  console.log('\nИтого: ' + passed + ' ок, ' + failed + ' провалов');
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
