/*
 * Контрольная по описанию (фаза 19): пройти подбор в режиме «контрольная» и
 * убедиться, что найденное уезжает в ОБЫЧНЫЙ конструктор контрольной, где
 * уже спрошены окно и лимит времени.
 *
 * ⚠️ Второй формы настроек времени мы не пишем — это была бы та же форма,
 * обречённая разойтись с первой.
 *
 * Запуск ИЗ КОРНЯ проекта:  node scripts/night_exam_generate.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8200';
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = 'reports/night/19-exam-generate';

let failures = 0;
function check(name, ok, extra) {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${extra ? ' — ' + extra : ''}`);
  if (!ok) failures += 1;
}

(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
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

  // Контрольная по описанию, из группы.
  await page.goto(`${BASE}/teacher/assignment/generate/?kind=exam&group=2`,
                  { waitUntil: 'networkidle' });
  const head = await page.evaluate(() => document.body.innerText);
  check('заголовок про контрольную', head.includes('Новая контрольная'));
  // Активных плиток на экране ДВЕ: способ набора и тип работы. Смотрим все,
  // иначе проверка ловит первую попавшуюся («Описать словами»).
  const active = await page.$$eval('.k-tile--on',
                                   (nodes) => nodes.map((n) => n.textContent));
  check('плитка «Контрольная» активна',
        active.some((t) => t.includes('Контрольная')), active.length + ' активных');
  check('плитка «Описать словами» активна',
        active.some((t) => t.includes('Описать словами')));
  await page.screenshot({ path: `${OUT}/step1.png`, fullPage: true });

  await page.fill('#gen-text', 'Контрольная на монополию и эластичность');
  await page.fill('#id_open', '3');
  await page.fill('#id_test', '2');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit]'),
  ]);
  check('дошли до шага «что нашлось»',
        (await page.evaluate(() => document.body.innerText)).includes('Вот что нашлось'));

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[value=search]'),
  ]);
  const found = await page.evaluate(() => document.body.innerText);
  const line = (found.split('\n').find((l) => l.includes('Найдено задач')) || '').trim();
  check('подобрались задачи', /Найдено задач: [1-9]/.test(line), line);
  await page.screenshot({ path: `${OUT}/step3.png`, fullPage: true });

  // Отправляем в конструктор — он должен быть конструктором КОНТРОЛЬНОЙ.
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#to-cart'),
  ]);
  check('уехали в конструктор контрольной',
        page.url().includes('/exams/new/'), page.url().replace(BASE, ''));

  const builder = await page.evaluate(() => document.body.innerText);
  check('в конструкторе есть настройки времени',
        builder.includes('Окно') || builder.includes('лимит')
        || builder.includes('минут'), '');
  check('корзина донесла задачи',
        !(await page.$eval('#cart-count', (e) => e.textContent.trim() === '0')),
        'в корзине ' + await page.$eval('#cart-count', (e) => e.textContent.trim()));
  check('ряд из трёх способов есть и здесь',
        (await page.$$('.k-tile')).length >= 3);
  await page.screenshot({ path: `${OUT}/builder.png`, fullPage: true });

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(failures ? `\nПРОВАЛЕНО: ${failures}` : '\nвсе проверки прошли');
  process.exit(failures ? 1 : 0);
})();
