/**
 * Поле даты после ревью 16.08 (фаза 3) — проверка ИСПОЛНЕНИЕМ.
 *
 * ⚠️ Питон-тесты видят исходник скрипта, но не видят живого поведения:
 * страница отдаёт 200 при любой ошибке в JS. Здесь браузер печатает
 * с клавиатуры, крутит колесо и жмёт стрелки — ровно как человек.
 *
 * Запуск: node scripts/r16_date_probe.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8211';
const BASE = `http://127.0.0.1:${PORT}`;

let passed = 0;
const failures = [];

function check(name, ok, extra) {
  if (ok) { passed += 1; return; }
  failures.push(name + (extra ? ' — ' + extra : ''));
}

async function login(page) {
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));

  await login(page);

  // ⚠️ Экран переехал: прежний конструктор удалён (ревью 17.08, п. 4.5),
  // поле срока живёт на шаге «Выдача».
  const url = `${BASE}/teacher/work/give/?group=2`;
  const res = await page.goto(url);
  check('шаг «Выдача» отвечает 200', res.status() === 200, String(res.status()));

  const box = page.locator('[data-k-date]').first();
  const text = box.locator('.k-date__text');
  const native = box.locator('.k-date__native');

  // ── 3.1 Двузначный год ──────────────────────────────────────────────
  // ⚠️ Дата заведомо в будущем: с этой сессии срок в прошлом — отказ
  // (п. 3.2), и «14.08.26» проверяло бы уже не год, а границу.
  await text.click();
  await text.fill('');
  await page.keyboard.type('141226 2000');
  const typing = await text.inputValue();
  // ⚠️ ОЖИДАНИЕ ПЕРЕСЧИТАНО (ревью 17.08, п. 7.2). Проверка ловила, что
  // маска не выбрасывает набранный разделитель, — это по-прежнему так.
  // Изменилось другое: двузначный год разворачивается СРАЗУ, а не при
  // открытии календаря, и на экране уже стоит канонический вид.
  check('маска не съедает набранный разделитель и разворачивает год',
        typing === '14.12.2026, 20:00', typing);
  await text.blur();
  const iso = await native.inputValue();
  check('двузначный год даёт 20xx', iso === '2026-12-14T20:00', iso);
  // Разобранное поле показывает КАНОНИЧЕСКИЙ вид: год полностью. Так
  // видно, что именно поняли из набранного.
  const shown = await text.inputValue();
  check('после разбора год показан целиком',
        shown === '14.12.2026, 20:00', shown);

  // Слитный полный набор по-прежнему работает.
  await text.fill('');
  await page.keyboard.type('200820261830');
  await text.blur();
  const iso2 = await native.inputValue();
  check('слитный набор работает', iso2 === '2026-08-20T18:30', iso2);

  // ── 3.2 Границы ─────────────────────────────────────────────────────
  await text.fill('');
  await page.keyboard.type('01.01.2020, 10:00');
  await text.blur();
  const past = (await box.locator('.k-date__err').textContent()).trim();
  check('прошлая дата объясняется словами', /прошла/i.test(past), past);
  check('поле подсвечено', await text.evaluate((el) => el.classList.contains('is-bad')));

  await text.fill('');
  await page.keyboard.type('01.01.2030, 10:00');
  await text.blur();
  const far = (await box.locator('.k-date__err').textContent()).trim();
  check('слишком далёкая дата объясняется', /далеко/i.test(far), far);
  check('в сообщении нет образцового времени', !/\d\d:\d\d/.test(far), far);

  // ── 3.3 Кнопка заперта ──────────────────────────────────────────────
  const submit = page.locator('#wk-next');
  const why = (await page.locator('#wk-why').textContent()).trim();
  check('кнопка выдачи заперта', await submit.isDisabled());
  check('причина названа', /срок сдачи/i.test(why), why);

  // ── 3.5 Значок календаря не уезжает ─────────────────────────────────
  const withErr = await box.locator('.k-date__pick').boundingBox();
  await text.fill('');
  await page.keyboard.type('20.08.2026, 18:30');
  await text.blur();
  const clean = await box.locator('.k-date__pick').boundingBox();
  check('значок календаря стоит на месте',
        Math.abs(withErr.y - clean.y) < 1 && Math.abs(withErr.x - clean.x) < 1,
        `с ошибкой ${JSON.stringify(withErr)} без ${JSON.stringify(clean)}`);

  // ── 3.6 Время — число, а не поле ────────────────────────────────────
  await box.locator('.k-date__pick').click();
  await page.locator('.k-cal__day:not(.is-off)').nth(20).click();
  check('панель времени открылась', await page.locator('.k-time').isVisible());
  check('полей ввода в панели нет',
        (await page.locator('.k-cal__step--time input').count()) === 0);

  const hour = page.locator('.k-time__num[data-time-part="hour"]');
  const minute = page.locator('.k-time__num[data-time-part="minute"]');

  await hour.click();
  check('активное число подсвечено',
        await hour.evaluate((el) => el.classList.contains('is-on')));
  await page.keyboard.type('09');
  check('часы набираются с клавиатуры', (await hour.textContent()).trim() === '09');
  check('после часов активны минуты',
        await minute.evaluate((el) => el.classList.contains('is-on')));
  await page.keyboard.type('45');
  check('минуты набираются', (await minute.textContent()).trim() === '45');

  await minute.click();
  await page.keyboard.press('ArrowUp');
  check('стрелка меняет на единицу', (await minute.textContent()).trim() === '46');
  await page.keyboard.press('Escape');
  check('Escape возвращает прежнее', (await minute.textContent()).trim() === '45');

  await hour.click();
  await hour.hover();
  await page.mouse.wheel(0, -120);
  check('колесо крутит число', (await hour.textContent()).trim() === '10');

  await page.locator('[data-cal-done]').click();
  const finalIso = await native.inputValue();
  check('выбранное время уехало в поле', /T10:45$/.test(finalIso), finalIso);

  check('ошибок в консоли нет', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log(`\nПроверок пройдено: ${passed}`);
  if (failures.length) {
    console.log('НЕ ПРОШЛО:');
    failures.forEach((f) => console.log('  ✗ ' + f));
    process.exit(1);
  }
  console.log('Все проверки зелёные.');
})();
