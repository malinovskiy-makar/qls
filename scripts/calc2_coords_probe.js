/* ФАЗА 5. КООРДИНАТНАЯ ПЛОСКОСТЬ И ПОДПИСИ КООРДИНАТ.

   Три вопроса приёмки:
     1) какие границы у «Построения графиков» и не сдвинулись ли чужие;
     2) остались ли подписи координат ВНУТРИ поля построения;
     3) не стоят ли два числа друг на друге у оси.

   ⚠️ «Внутри поля» считается по прямоугольнику ШКАЛ сцены, а не по холсту:
   поля холста узкие, и подпись, лежащая в них, снаружи поля построения, но
   внутри картинки. Ровно это и есть правильное место.

   Запуск: node scripts/calc2_coords_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/coords.json';
const BASE = `http://127.0.0.1:${PORT}`;

const snap = () => {
  const svgEl = document.querySelector('#chart');
  const box = svgEl.getBoundingClientRect();
  const s = mainScales();
  const [rx0, rx1] = s.mx.range(), [ry0, ry1] = s.my.range();
  const plot = { x0: Math.min(rx0, rx1), x1: Math.max(rx0, rx1),
                 y0: Math.min(ry0, ry1), y1: Math.max(ry0, ry1) };
  const vis = (el) => {
    const c = getComputedStyle(el);
    return c.display !== 'none' && c.visibility !== 'hidden';
  };
  const texts = Array.from(document.querySelectorAll('#chart text')).filter(vis).map(el => {
    const r = el.getBoundingClientRect();
    return { t: (el.textContent || '').trim(),
             cls: el.getAttribute('class') || '',
             left: +(r.left - box.left).toFixed(1), right: +(r.right - box.left).toFixed(1),
             top: +(r.top - box.top).toFixed(1), bottom: +(r.bottom - box.top).toFixed(1) };
  });
  /* ⚠️ ДЕЛЕНИЕ ШКАЛЫ — НЕ ПОДПИСЬ КООРДИНАТЫ, И В ПОЛНОМ ПЛАНЕ ОНО ЛЕЖИТ
     ВНУТРИ ПОЛЯ ПО УСТРОЙСТВУ: оси проходят через середину, и числа при них
     стоят там же. Первая версия прибора считала их нарушением и объявляла
     «числа внутри поля» на всех шести математических сценах разом.
     Деления помечены классом axis-num в единой точке печати — по нему и
     отличаем. */
  const isCoord = (t) => /^[−-]?[\d\s.,]+$/.test(t.t.replace(/−/g, '-')) &&
                         t.cls !== 'axis-name' && t.cls !== 'axis-num';
  /* ⚠️ ЧИСЛО У САМОЙ ОСИ — НЕ НАРУШЕНИЕ, ГДЕ БЫ ЭТА ОСЬ НИ ПРОХОДИЛА.
     В полном плане оси идут через середину поля, и деления при них лежат
     внутри прямоугольника построения по устройству. Часть сцен печатает
     деления своим кодом, без общего класса, поэтому отличаем по МЕСТУ:
     число, прижатое к линии оси, стоит там, где ему и положено. Нарушение —
     это число, висящее в поле вдали от обеих осей, поверх сетки и заливок. */
  const axX = s.mx(Math.max(s.mx.domain()[0], Math.min(0, s.mx.domain()[1])));
  const axY = s.my(Math.max(s.my.domain()[0], Math.min(0, s.my.domain()[1])));
  const nearAxis = (t) => {
    const cx = (t.left + t.right) / 2 - box.left + box.left, cy = (t.top + t.bottom) / 2;
    return Math.abs((t.left + t.right) / 2 - axX) < 26 || Math.abs(cy - axY) < 26;
  };
  const inside = (t) => t.left < plot.x1 - 2 && t.right > plot.x0 + 2 &&
                        t.top < plot.y1 - 2 && t.bottom > plot.y0 + 2 && !nearAxis(t);
  // повтор имени оси: подпись вида «P*=50», «Qd=30»
  const named = texts.filter(t => /^[A-Za-zА-Яа-я][A-Za-zА-Яа-я₀-₉*∗]*\s*=\s*[−-]?\d/.test(t.t));
  // два числа друг на друге у осей
  const nums = texts.filter(isCoord);
  const pairs = [];
  for (let i = 0; i < nums.length; i++)
    for (let j = i + 1; j < nums.length; j++) {
      const a = nums[i], b = nums[j];
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 2 && h > 2) pairs.push([a.t, b.t]);
    }
  return {
    domain: { x: s.mx.domain().map(v => +v.toFixed(3)), y: s.my.domain().map(v => +v.toFixed(3)) },
    plot,
    namedCoords: named.map(t => t.t),
    numbersInsidePlot: nums.filter(inside).map(t => t.t),
    overlapping: pairs,
    eqCircles: document.querySelectorAll('g.equilibrium circle').length,
    eqName: Array.from(document.querySelectorAll('g.equilibrium text.point-name')).map(e => e.textContent.trim()),
    eqDashes: document.querySelectorAll('g.equilibrium line').length,
  };
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
  fs.writeFileSync(OUT, JSON.stringify({ scenes: res, pageErrors: errs }, null, 1), 'utf8');

  const named = Object.keys(res).filter(k => res[k].namedCoords.length);
  const insideBad = Object.keys(res).filter(k => res[k].numbersInsidePlot.length);
  const over = Object.keys(res).filter(k => res[k].overlapping.length);
  console.log('границы «Построения графиков»: x', JSON.stringify(res['m-graph'].domain.x),
              ' y', JSON.stringify(res['m-graph'].domain.y));
  console.log('равновесие: кружков', res.sd.eqCircles, '· подпись', JSON.stringify(res.sd.eqName),
              '· пунктиров', res.sd.eqDashes);
  console.log('\nсцен с повтором имени оси в координате:', named.length);
  named.forEach(k => console.log('   ' + k + ': ' + res[k].namedCoords.join(', ')));
  console.log('сцен с числом внутри поля построения:', insideBad.length);
  insideBad.slice(0, 8).forEach(k => console.log('   ' + k + ': ' + res[k].numbersInsidePlot.join(', ')));
  console.log('сцен с наложением чисел:', over.length);
  over.slice(0, 8).forEach(k => console.log('   ' + k + ': ' + JSON.stringify(res[k].overlapping)));
  console.log('\nошибок страницы:', errs.length);
  await browser.close();
})();
