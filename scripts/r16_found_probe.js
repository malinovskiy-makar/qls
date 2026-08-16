/**
 * Шаг «Что нашлось» после ревью 16.08 (фаза 9) — проверка ИСПОЛНЕНИЕМ.
 *
 * Экран требует слоя модели. Ключа локально нет — поднимаем сервер с
 * подставным поставщиком (`config/settings_check.py` + QLS_FAKE_REPLY),
 * он заведён в проекте ровно для этого.
 *
 * Запуск: node scripts/r16_found_probe.js [порт]
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

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  const res = await page.goto(`${BASE}/teacher/assignment/generate/?group=2`,
                              { waitUntil: 'domcontentloaded' });
  check('шаг «Что кладём» отвечает 200', res.status() === 200, String(res.status()));

  // ⚠️ Настройки просят ЧЕТЫРЕ задачи и НОЛЬ тестов, а подставной план
  // модели просит два теста — ровно случай владельца из п. 9.1.
  await page.fill('#gen-text', 'Нужны задачи и тесты по эластичности спроса');
  await page.fill('[name=count_open]', '4');
  await page.fill('[name=count_test]', '0');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button:has-text("Разобрать запрос")'),
  ]);

  const tally = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('.gen-tally .tally')]
      .map((n) => ({ text: n.innerText.replace(/\s+/g, ' ').trim(),
                     cls: n.className }));
    return { rows, buttons: document.querySelectorAll('.gen-tally button').length,
             first: (document.querySelector('.gen-tally') || {}).offsetTop };
  });
  check('сводка «просили — набрали» есть', tally.rows.length > 0,
        JSON.stringify(tally.rows));
  check('задачи посчитаны',
        tally.rows.some((r) => /задачи: \d+ из \d+/.test(r.text)),
        JSON.stringify(tally.rows));
  check('противоречие по тестам названо',
        tally.rows.some((r) => /тесты/.test(r.text)
                               && /в настройках стоит/.test(r.text)),
        JSON.stringify(tally.rows));
  check('расхождение помечено янтарём',
        tally.rows.some((r) => /tally--off|tally--short/.test(r.cls)));
  check('рядом кнопка добора', tally.buttons > 0, String(tally.buttons));

  // 9.2 — две строки условия и кнопка «Целиком».
  const cards = await page.evaluate(() => {
    const first = document.querySelector('.cand');
    if (!first) { return null; }
    const lead = first.querySelector('.cand-lead');
    return {
      hasLead: !!lead,
      leadText: lead ? lead.textContent.trim().slice(0, 40) : '',
      clamp: lead ? getComputedStyle(lead).webkitLineClamp : '',
      button: !!first.querySelector('.cand-full'),
    };
  });
  if (cards) {
    check('в строке видно начало условия', cards.hasLead && cards.leadText.length > 10,
          cards.leadText);
    check('условие обрезано двумя строками', cards.clamp === '2', cards.clamp);
    check('кнопка «Целиком» есть', cards.button);
    // Карточка запроса могла открыться сама — жмём заголовок только
    // когда она закрыта, иначе клик её СХЛОПНЕТ.
    const isOpen = await page.evaluate(
      () => document.querySelector('.plan-block').classList.contains('is-open'));
    if (!isOpen) { await page.click('.plan-block .q-head'); }
    await page.click('.cand .cand-full');
    const opened = await page.evaluate(() => {
      const first = document.querySelector('.cand');
      return { shown: first.classList.contains('is-shown'),
               body: getComputedStyle(first.querySelector('.cand-body')).display,
               lead: getComputedStyle(first.querySelector('.cand-lead')).display };
    });
    check('«Целиком» раскрывает условие', opened.shown && opened.body !== 'none',
          JSON.stringify(opened));
    check('превью прячется при раскрытии', opened.lead === 'none', opened.lead);
  } else {
    check('карточки кандидатов нарисованы', false, 'ни одной .cand');
  }

  // 9.4 — остаток разборов вместо стоимости.
  const cost = await page.evaluate(() => {
    const el = document.querySelector('.gen-cost');
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
  });
  check('внизу остаток разборов', /осталось \d+ разбор/.test(cost || ''), cost);
  check('стоимости и модели на экране нет',
        !/\$|haiku|claude/i.test(cost || ''), cost);

  // 9.1 — кнопка добора работает и не ходит к модели.
  const before = cost;
  const blocksBefore = await page.evaluate(
    () => document.querySelectorAll('.plan-block').length);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('.gen-tally button'),
  ]);
  const after = await page.evaluate(() => ({
    cost: (document.querySelector('.gen-cost') || {}).textContent || '',
    rows: [...document.querySelectorAll('.gen-tally .tally')]
      .map((n) => n.innerText.replace(/\s+/g, ' ').trim()),
    blocks: document.querySelectorAll('.plan-block').length,
  }));
  check('добор добавил строку в план', after.blocks > blocksBefore,
        `было ${blocksBefore}, стало ${after.blocks}`);
  check('к модели не обращались',
        after.cost.replace(/\s+/g, ' ').trim() === before, after.cost.trim());
  check('после добора тесты посчитаны',
        after.rows.some((r) => /тесты: \d+ из \d+/.test(r)),
        JSON.stringify(after.rows));

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
