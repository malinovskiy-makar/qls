/**
 * Переключение пяти панелей шага «Что кладём» — проверка ИСПОЛНЕНИЕМ.
 *
 * Питон-тесты видят разметку, но не видят, что происходит при нажатии:
 * корзина живёт в `sessionStorage`, панели переключает скрипт, а лента
 * шагов рисуется на каждом состоянии заново. Именно на этом стыке уже
 * ловились дефекты, которых не видел ни один питон-тест.
 *
 * Проверяем: корзина не теряется при переключении вкладок и при переходе
 * в состояние «что нашлось»; занятие и вид работы едут в каждом адресе;
 * лента шагов ВСЕГДА из трёх.
 *
 * Запуск: node scripts/look_panels.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8401';
const BASE = `http://127.0.0.1:${PORT}`;
const GROUP = 2;

let passed = 0;
const failed = [];

function ok(what, condition) {
  if (condition) { passed += 1; } else { failed.push(what); }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  // ── Вход в поток: корзина занятия чистится намеренно.
  await page.goto(`${BASE}/teacher/work/start/?group=${GROUP}`,
                  { waitUntil: 'networkidle' });
  await page.waitForURL('**/teacher/work/**');

  const rail = async () =>
    page.$$eval('.wk-rail__s', (nodes) => nodes.length);
  ok('лента из трёх шагов на «Что кладём»', await rail() === 3);

  // ── Кладём задачу в работу.
  await page.goto(`${BASE}/teacher/work/?group=${GROUP}&q=издержки`,
                  { waitUntil: 'networkidle' });
  await page.click('.wk-card .wk-add');
  const inCart = async () => page.evaluate((g) => {
    try { return Object.keys(JSON.parse(
      sessionStorage.getItem('work_cart:' + g) || '{}')).length; }
    catch (e) { return -1; }
  }, GROUP);
  ok('задача легла в корзину', await inCart() === 1);
  ok('кнопка отвечает «в работе»',
     await page.$eval('.wk-card .wk-add',
                      (b) => b.classList.contains('added')));
  ok('карточка покрашена, а не приглушена',
     await page.$eval('.wk-card',
                      (c) => c.classList.contains('is-added')
                             && getComputedStyle(c).opacity === '1'));

  // ── Переключение вкладок: корзина цела, страница не перезагружается.
  const panes = ['pane-ai', 'pane-own', 'pane-saved', 'pane-catalog'];
  for (const pane of panes) {
    await page.click(`.wk-tab[data-pane="${pane}"]`);
    const shown = await page.$eval(`#${pane}`, (el) => !el.hidden);
    ok(`панель ${pane} открылась без перезагрузки`, shown);
    ok(`корзина цела после ${pane}`, await inCart() === 1);
  }
  ok('лента шагов не изменилась', await rail() === 3);

  // ── Занятие и вид работы едут в каждом адресе.
  await page.goto(`${BASE}/teacher/work/?group=${GROUP}&kind=exam&tab=ai`,
                  { waitUntil: 'networkidle' });
  const links = await page.$$eval('.wk-tab[href], .wk-rail__s a[href]',
                                  (nodes) => nodes.map((n) => n.getAttribute('href')));
  ok('ссылки шага несут занятие',
     links.every((href) => href.includes(`group=${GROUP}`)));
  ok('ссылки шага несут вид работы',
     links.every((href) => href.includes('kind=exam')));
  ok('вид работы отмечен на переключателе',
     await page.$eval('.bh-kind__opt.is-on', (n) => n.textContent.trim())
       === 'Контрольная');

  // ── Второе состояние панели: корзина и вид работы переживают разбор.
  await page.goto(`${BASE}/teacher/work/?group=${GROUP}&tab=ai`,
                  { waitUntil: 'networkidle' });
  const field = await page.$('#gen-text');
  if (field) {
    await field.fill('эластичность спроса, две задачи');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle' }),
      page.click('#pane-ai button[type=submit]'),
    ]);
    ok('лента и после разбора из трёх шагов', await rail() === 3);
    ok('ряд способов набора на месте',
       (await page.$$('.wk-tab')).length === 5);
    const active = await page.$eval('.wk-tab.is-on', (n) => n.textContent);
    ok('«Описать словами» отмечена активной',
       active.includes('Описать словами'));
    ok('корзина пережила разбор запроса', await inCart() === 1);
    const numbers = await page.$$eval('.wk-rail__n',
                                      (nodes) => nodes.map((n) => n.textContent.trim()));
    ok('шаги пронумерованы 1–2–3 и четвёртого нет',
       numbers.join('') === '123');
  } else {
    failed.push('панель «Описать словами» не открылась (слой модели?)');
  }

  // ── Редактор своей задачи: тот же ряд и та же лента.
  await page.goto(`${BASE}/teacher/problems/new/?to_cart=1&group=${GROUP}`,
                  { waitUntil: 'networkidle' });
  ok('у редактора та же лента из трёх', await rail() === 3);
  ok('у редактора тот же ряд способов',
     (await page.$$('.wk-tab')).length === 5);
  ok('корзина цела и здесь', await inCart() === 1);

  await browser.close();
  console.log(`Проверок пройдено: ${passed}`);
  if (failed.length) {
    console.log('НЕ ПРОШЛО:');
    failed.forEach((f) => console.log('  ✗ ' + f));
    process.exit(1);
  }
})();
