/*
 * Дойти до шага «Что нашлось» и снять его (фаза 18).
 *
 * ⚠️ Этот шаг требует работающего слоя модели, поэтому при аудите он не
 * снимался вовсе. Боевой ключ для осмотра не нужен: в проекте есть
 * ПОДСТАВНОЙ поставщик (`AI_PROVIDER='fake'`) — он заведён ровно для того,
 * чтобы сменяемость модели была проверяемой, а не обещанной. Сервер с ним
 * поднимается отдельно, боевые настройки не трогаются.
 *
 * Запуск ИЗ КОРНЯ проекта:
 *   node scripts/night_generate_step2.js <порт> <папка> <имя-снимка>
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8200';
const OUT = process.argv[3] || 'reports/night/18-generate-found';
const NAME = process.argv[4] || 'step2';
const BASE = `http://127.0.0.1:${PORT}`;

const QUERY = 'Домашка на КПВ и КТВ, четыре задачи и три теста. ' +
  'Первая задача — вывод функции КПВ, вторая и третья на сложение КПВ.';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  await page.goto(`${BASE}/teacher/assignment/generate/`,
                  { waitUntil: 'networkidle' });
  await page.fill('#gen-text', QUERY);
  await page.fill('#id_open', '4');
  await page.fill('#id_test', '3');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit]'),
  ]);

  await page.screenshot({ path: `${OUT}/${NAME}.png`, fullPage: true });
  const text = await page.evaluate(() => document.body.innerText);
  console.log('--- шаг 2, видимый текст ---');
  console.log(text.split('\n').filter((l) => l.trim()).slice(4, 40).join('\n'));

  // Идём дальше — на шаг 3, чтобы проверить состав подборки.
  const go = await page.$('button[name=action][value=search], button[value=search]');
  if (go) {
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle' }),
      go.click(),
    ]);
    await page.screenshot({ path: `${OUT}/${NAME}-step3.png`, fullPage: true });
    const result = await page.evaluate(() => document.body.innerText);
    const line = result.split('\n').find((l) => l.includes('Найдено задач'));
    console.log('\n--- шаг 3 ---\n' + (line || '(строки «Найдено задач» нет)'));
  }

  await browser.close();
})();
