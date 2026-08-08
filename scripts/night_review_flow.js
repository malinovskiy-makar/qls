/*
 * Сквозной сценарий проверки работы (фаза 13): пройти работу ученика
 * НАСКВОЗЬ через «Сохранить и дальше», дойти до экрана завершения и
 * написать общий комментарий — ни разу не возвращаясь в список.
 *
 * ⚠️ Именно это и переделывалось: раньше работа из семи задач стоила семи
 * заходов, потому что после каждой задачи экран уводил обратно в список.
 *
 * Запуск ИЗ КОРНЯ проекта:  node scripts/night_review_flow.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;

let failures = 0;
function check(name, ok, extra) {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${extra ? ' — ' + extra : ''}`);
  if (!ok) failures += 1;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  // Сводка решений: карточка ученика ведёт сразу на первую непроверенную.
  await page.goto(`${BASE}/teacher/groups/2/assignments/6/submissions/?view=students`,
                  { waitUntil: 'networkidle' });
  const checkBtn = await page.$('a.k-btn--main');
  check('на сводке есть кнопка «Проверить …»', !!checkBtn);
  if (!checkBtn) { await browser.close(); process.exit(1); }

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    checkBtn.click(),
  ]);

  check('открылся экран проверки', page.url().includes('/submissions/'));
  const pos = await page.textContent('.rv-pos');
  check('видно «задача N из M»', /задача \d+ из \d+/.test(pos), pos.trim());
  check('есть карточки «ответил ученик» и «верный ответ»',
        (await page.$$('.rv-box')).length >= 2);
  check('«Отметить ошибки» с экрана убрано',
        !(await page.evaluate(() => document.body.innerText)).includes('Отметить ошибки'));
  check('«Комментарий ко всей работе» с этого экрана убран',
        !(await page.evaluate(() => document.body.innerText)).includes('Комментарий ко всей работе'));

  // Балл ставится нажатием: пресет подставляет число и подсвечивается.
  const presets = await page.$$('.rv-preset');
  check('есть кнопки-пресеты балла', presets.length >= 2, `${presets.length} шт.`);
  await presets[presets.length - 1].click();
  const filled = await page.$eval('#score-input', (e) => e.value);
  check('пресет подставил балл в поле', filled !== '', `значение «${filled}»`);
  check('нажатый пресет подсвечен',
        await presets[presets.length - 1].evaluate((b) => b.classList.contains('is-on')));

  // Проходим работу насквозь: жмём «Сохранить и дальше», пока не завершится.
  let steps = 0;
  while (steps < 12) {
    const next = await page.$('button[name=go][value=next]');
    if (!next) break;
    const before = page.url();
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle' }),
      next.click(),
    ]);
    steps += 1;
    if (page.url().includes('/done/')) break;
    check(`шаг ${steps}: не вернулись в список`,
          !page.url().includes('/submissions/?') &&
          !page.url().endsWith('/submissions/'),
          page.url().replace(BASE, ''));
    if (page.url() === before) break;
  }

  check('дошли до экрана завершения работы', page.url().includes('/done/'),
        page.url().replace(BASE, ''));
  if (page.url().includes('/done/')) {
    const text = await page.evaluate(() => document.body.innerText);
    check('на завершении виден итоговый балл', /\d+ \/ \d+/.test(text));
    check('на завершении есть комментарий ко всей работе',
          text.includes('Комментарий ко всей работе'));

    await page.fill('#work-comment', 'Разобрали эластичность, повтори среднюю точку.');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle' }),
      page.click('button[type=submit]'),
    ]);
    check('после «Готово» вернулись к сводке',
          page.url().includes('/submissions/'), page.url().replace(BASE, ''));
  }

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(failures ? `\nПРОВАЛЕНО: ${failures}` : '\nвсе проверки прошли');
  process.exit(failures ? 1 : 0);
})();
