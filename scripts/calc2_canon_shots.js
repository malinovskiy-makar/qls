/* Контактный лист работы «Графики под канон»: снимок каждой модели в обеих
   темах плюс собранная страница `reports/calc2-canon/index.html`.

   Смотреть глазами всё равно придётся, но лист избавляет от хождения по
   сорока одной карточке руками и показывает светлую и тёмную рядом.

   Запуск: node scripts/calc2_canon_shots.js [порт]                         */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8601';
const BASE = 'http://127.0.0.1:' + PORT;
const OUT = path.join('reports', 'calc2-canon', 'shots');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));

  await p.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (p.url().includes('login')) {
    await p.fill('input[name="username"]', 'student1');
    await p.fill('input[name="password"]', 'student12345');
    await p.click('button[type=submit], input[type=submit]');
    await p.waitForLoadState('domcontentloaded');
  }
  await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });

  // Экран выбора моделей — тоже часть работы (фаза 7).
  const rows = [];
  for (const theme of ['light', 'dark']) {
    await p.evaluate((t) => setCalcTheme(t), theme);
    await p.evaluate(() => openPicker());
    await p.waitForTimeout(450);
    await p.screenshot({ path: path.join(OUT, 'picker-' + theme + '.png') });
  }
  rows.push({ key: 'picker', name: 'Экран выбора моделей' });

  const keys = await p.evaluate(() => Object.keys(SCENE_ROUTE));
  const names = await p.evaluate(() => (typeof SCENE_NAMES === 'object') ? SCENE_NAMES : {});
  for (const key of keys) {
    for (const theme of ['light', 'dark']) {
      await p.evaluate((a) => {
        setCalcTheme(a.t);
        if (typeof closePicker === 'function') closePicker();
        resetSceneMemory();
        pickScene(a.k);
      }, { k: key, t: theme });
      await p.waitForTimeout(520);
      await p.screenshot({ path: path.join(OUT, key + '-' + theme + '.png') });
    }
    rows.push({ key, name: names[key] || key });
    process.stdout.write('.');
  }
  await b.close();

  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Графики под канон — контактный лист</title>
<style>
  body { margin: 0; padding: 28px 24px 60px; font: 14px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
         background: #f4f5f7; color: #10131a; }
  h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; }
  p.sub { margin: 0 0 24px; color: #5b6472; }
  .row { background: #fff; border: 1px solid #e2e5ea; border-radius: 10px; padding: 14px 16px 16px; margin-bottom: 18px; }
  .row h2 { font-size: 15px; font-weight: 600; margin: 0 0 10px; }
  .row h2 code { font-weight: 400; color: #5b6472; font-size: 13px; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .pair figure { margin: 0; }
  .pair figcaption { font-size: 12px; color: #5b6472; margin-bottom: 5px; }
  .pair img { width: 100%; display: block; border: 1px solid #e2e5ea; border-radius: 6px; }
</style></head><body>
<h1>Графики под канон — контактный лист</h1>
<p class="sub">Каждая модель в светлой и тёмной теме, ширина 1440. Снимки лежат
рядом, в папке <code>shots/</code>. Пересобрать: <code>node scripts/calc2_canon_shots.js 8601</code></p>
${rows.map(r => `<div class="row"><h2>${esc(r.name)} <code>${esc(r.key)}</code></h2>
  <div class="pair">
    <figure><figcaption>светлая</figcaption><img loading="lazy" src="shots/${esc(r.key)}-light.png" alt=""></figure>
    <figure><figcaption>тёмная</figcaption><img loading="lazy" src="shots/${esc(r.key)}-dark.png" alt=""></figure>
  </div></div>`).join('\n')}
</body></html>`;
  fs.writeFileSync(path.join('reports', 'calc2-canon', 'index.html'), html, 'utf8');
  console.log('\nмоделей снято: ' + (rows.length - 1) + ', ошибок страницы: ' + errs.length);
  errs.slice(0, 5).forEach(e => console.log('  ОШИБКА: ' + e));
  console.log('лист: reports/calc2-canon/index.html');
})();
