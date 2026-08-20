/* ФАЗЫ 4.6–4.8 сессии 20.08. КОНСОЛЬ БРАУЗЕРА ПРИ ОБХОДЕ ВСЕХ СЦЕН.

   Отлаживать в консоли было нечем: за один обход сорока одной сцены набиралось
   около полутора тысяч предупреждений. MathLive жаловался на три настройки,
   переданные в конструктор, где он их не читает; KaTeX — на узкий неразрывный
   пробел (наш разделитель разрядов) и на кириллицу в математическом режиме.

   Прибор открывает каждую сцену, раскрывает карточки панелей (поля формул
   собираются лениво и только когда видны) и считает всё, что попало в консоль.

   Запуск: node scripts/calc2_console_probe.js <порт> */
const { chromium } = require('playwright');
const PORT = process.argv[2] || '8701';
const BASE = `http://127.0.0.1:${PORT}`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const msgs = [], errs = [];
  page.on('console', m => { if (/warning|error/.test(m.type())) msgs.push(m.text().slice(0, 160)); });
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  for (const k of scenes) {
    await page.evaluate(k => pickScene(k), k);
    await page.evaluate(() => {
      document.querySelectorAll('#tools-panel .section, #params-panel .section').forEach(s => { if (s.id) openSection(s.id); });
      document.querySelectorAll('.fold-btn').forEach(b => { if (b.getAttribute('aria-expanded') === 'false') b.click(); });
    });
    await page.waitForTimeout(300);
    process.stdout.write('.');
  }
  console.log('');
  const groups = {};
  msgs.forEach(t => {
    const key = t.replace(/"[^"]*"/g, '"…"').replace(/\d+/g, 'N').slice(0, 90);
    groups[key] = (groups[key] || 0) + 1;
  });
  console.log('сцен пройдено: ' + scenes.length);
  console.log('предупреждений и ошибок консоли: ' + msgs.length);
  Object.entries(groups).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => console.log('   ' + v + ' × ' + k));
  console.log('ошибок страницы: ' + errs.length);
  errs.slice(0, 5).forEach(e => console.log('   ' + e.slice(0, 120)));
  await browser.close();
  process.exit(msgs.length || errs.length ? 1 : 0);
})();
