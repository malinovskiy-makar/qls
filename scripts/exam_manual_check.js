/*
 * Ручная проверка контрольной браузером — четыре сценария самопроверки
 * Части C. Питон-тесты этого класса не видят: они не запускают JS и не
 * умеют «закрыть вкладку» или «отключить сеть».
 *
 * Запуск ИЗ КОРНЯ проекта:
 *   node scripts/exam_manual_check.js [порт] [id контрольной]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8123';
const EXAM = process.argv[3] || '7';
const BASE = `http://127.0.0.1:${PORT}`;
const out = [];

function say(step, ok, detail) {
  out.push(`${ok ? '✅' : '❌'} ${step}${detail ? ' — ' + detail : ''}`);
}

async function login(page) {
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'student1@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await login(page);

  // --- 1. Старт и таймер -------------------------------------------------
  await page.goto(`${BASE}/student/exam/${EXAM}/`, { waitUntil: 'networkidle' });
  const startBtn = page.locator('button:has-text("Начать")');
  if (await startBtn.count()) {
    await Promise.all([page.waitForNavigation(), startBtn.click()]);
  }
  const onTakePage = page.url().includes('/take/');
  say('старт контрольной', onTakePage, page.url());

  await page.waitForTimeout(1500);
  const t1 = await page.locator('#timer').textContent();
  await page.waitForTimeout(2500);
  const t2 = await page.locator('#timer').textContent();
  say('таймер идёт', t1.trim() !== t2.trim(), `${t1.trim()} → ${t2.trim()}`);

  // --- 2. Заполнить, ЗАКРЫТЬ ВКЛАДКУ, открыть заново ---------------------
  const fields = await page.locator('textarea.answer-text').count();
  await page.locator('textarea.answer-text').first().fill('решение из первой вкладки');
  const shortInputs = await page.locator('input.answer-short').count();
  if (shortInputs) {
    await page.locator('input.answer-short').first().fill('123');
  }
  await page.locator('body').click();          // потеря фокуса → автосейв
  await page.waitForTimeout(1200);
  const saveText = (await page.locator('#save-state').textContent()).trim();
  // Точное совпадение: строка «нет связи — ответы сохранены на странице»
  // тоже содержит «сохранен», и проверка по вхождению нас уже обманула.
  say('индикатор сохранения', saveText === 'сохранено', saveText);

  await page.close();
  const page2 = await context.newPage();
  await page2.goto(`${BASE}/student/exam/${EXAM}/take/`, { waitUntil: 'networkidle' });
  const restored = await page2.locator('textarea.answer-text').first().inputValue();
  say('ответы на месте после закрытия вкладки',
      restored === 'решение из первой вкладки', JSON.stringify(restored));

  const timerAfter = (await page2.locator('#timer').textContent()).trim();
  say('таймер продолжается, а не начинается заново',
      timerAfter !== t1.trim(), `было ${t1.trim()}, стало ${timerAfter}`);

  // --- 3. ОТКЛЮЧИТЬ СЕТЬ, печатать, вернуть сеть -------------------------
  await context.setOffline(true);
  await page2.locator('textarea.answer-text').first().fill('дописано без сети');
  await page2.locator('body').click();
  await page2.waitForTimeout(2500);
  const offlineText = (await page2.locator('#save-state').textContent()).trim();
  say('видно «нет связи»', offlineText.includes('нет связи'), offlineText);

  await context.setOffline(false);
  await page2.waitForTimeout(11000);           // повтор идёт раз в 10 секунд
  const backText = (await page2.locator('#save-state').textContent()).trim();
  say('после возврата сети — сохранено', backText === 'сохранено', backText);

  const page3 = await context.newPage();
  await page3.goto(`${BASE}/student/exam/${EXAM}/take/`, { waitUntil: 'networkidle' });
  const afterOffline = await page3.locator('textarea.answer-text').first().inputValue();
  say('написанное без сети дошло до сервера',
      afterOffline === 'дописано без сети', JSON.stringify(afterOffline));

  // --- 4. ПЕРЕВОД ЧАСОВ УСТРОЙСТВА --------------------------------------
  const before = (await page3.locator('#timer').textContent()).trim();
  await page3.evaluate(() => {
    // Подменяем часы устройства на час вперёд — как если бы школьник
    // перевёл системное время.
    const shift = 3600 * 1000;
    const RealDate = Date;
    // eslint-disable-next-line no-global-assign
    Date = class extends RealDate {
      constructor(...args) {
        super(...(args.length ? args : [RealDate.now() + shift]));
      }
      static now() { return RealDate.now() + shift; }
    };
  });
  await page3.waitForTimeout(3000);
  const after = (await page3.locator('#timer').textContent()).trim();
  const [bm, bs] = before.split(':').map(Number);
  const [am, as_] = after.split(':').map(Number);
  const drift = (bm * 60 + bs) - (am * 60 + as_);
  say('перевод часов не сдвинул таймер', drift >= 0 && drift <= 10,
      `${before} → ${after} (ушло ${drift} с вместо ~3)`);

  say('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(out.join('\n'));
})();
