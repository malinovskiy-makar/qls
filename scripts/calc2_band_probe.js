/* ФАЗЫ 2 и 4. ЗАМЕР ПОЛОСЫ ПОПАДАНИЯ ПО КРИВОЙ.

   Отвечает на два раздельных вопроса, которые до фазы 2 были одним:
     · у скольких кривых есть полоса попадания (щелчок по кривой возможен);
     · у скольких из них курсор обещает перетаскивание.

   ⚠️ Прибор смотрит на КУРСОР, а не на наличие обработчика: обещание даёт
   именно курсор, и разошлись бы они незаметно.

   Запуск: node scripts/calc2_band_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/bands.json';
const BASE = `http://127.0.0.1:${PORT}`;

const snap = () => {
  const paths = Array.from(document.querySelectorAll('g.curves path'));
  const bands = [], lines = [];
  paths.forEach(p => {
    const c = getComputedStyle(p);
    const rec = { cursor: c.cursor, width: +(parseFloat(c.strokeWidth) || 0).toFixed(2),
                  skip: p.getAttribute('data-skip-export') === '1',
                  hit: p.getAttribute('data-hit') };
    rec.curveId = p.getAttribute('data-curve');
    if (rec.hit !== null) bands.push(rec); else lines.push(rec);
  });
  /* ⚠️ ЗНАМЕНАТЕЛЬ — КРИВЫЕ, КОТОРЫЕ ОБЩИЙ РИСОВАЛЬЩИК ДЕЙСТВИТЕЛЬНО НАРИСОВАЛ,
     а не длина STATE.curves. Три сцены («ломаный спрос», дискриминация 3°,
     монополист на мировом рынке) держат кривые в состоянии, но рисуют их сами,
     не через drawCurves. Сверка со списком состояния объявляла бы их
     нарушением там, где рисовать полосу попросту нечему. */
  const drawn = lines.filter(l => l.curveId !== null).length;
  return { bands, lines, drawn,
           curves: STATE.curves.filter(c => c.visible).length,
           linear: STATE.curves.filter(c => c.visible && c.linear).length,
           scene: STATE.sceneKey };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));

  const res = {};
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(1000);
    res[key] = await page.evaluate(snap);
    process.stdout.write('.');
  }
  console.log('');

  let bands = 0, drag = 0, click = 0, curves = 0, mismatch = [];
  for (const k of Object.keys(res)) {
    const r = res[k];
    bands += r.bands.length; curves += r.drawn;
    r.bands.forEach(b => { if (b.cursor === 'ns-resize') drag++; else click++; });
    // Полоса обязана быть у каждой видимой кривой сцены — иначе щёлкнуть нельзя.
    if (r.bands.length !== r.drawn)
      mismatch.push(k + ': полос ' + r.bands.length + ' при нарисованных ' + r.drawn +
                    ' (в состоянии ' + r.curves + ')');
  }
  fs.writeFileSync(OUT, JSON.stringify({ scenes: res, pageErrors: errs }, null, 1), 'utf8');
  console.log('видимых кривых всего:', curves);
  console.log('полос попадания:     ', bands, '(курсор ns-resize:', drag + ', pointer:', click + ')');
  console.log('ошибок страницы:     ', errs.length);
  if (mismatch.length) { console.log('\nСЦЕНЫ, ГДЕ ПОЛОС НЕ ПО ЧИСЛУ КРИВЫХ:'); mismatch.forEach(m => console.log('  ' + m)); }
  else console.log('у каждой видимой кривой есть своя полоса');
  await browser.close();
})();
