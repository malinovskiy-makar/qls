/* ФАЗА 6. ДЁРГАНЬЕ ПОДПИСИ КРИВОЙ.

   Тот самый прогон, которым дефект был найден: параметр «a» ведётся от 1,00 до
   2,00 шагами по 0,05, и на каждом шаге меряется место подписи.

   ⚠️ Заодно меряется положение деления «2» на оси: если плоскость сама
   поехала, дёрганье подписи было бы честным следствием, а не дефектом. В
   исходном замере деление стояло на 471,3 px все двадцать один шаг.

   Запуск: node scripts/calc2_labelshake_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/labelshake.json';
const BASE = `http://127.0.0.1:${PORT}`;

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
  await page.evaluate(() => pickScene('m-graph'));
  await page.waitForTimeout(1100);
  await page.evaluate(() => {
    const box = document.getElementById('graph-rows');
    if (box) openSection(box.closest('.section').id);
    const inp = document.querySelector('#graph-rows .f-slot > input');
    inp.value = 'a*x^2 - 3*x';
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(1200);

  const steps = [];
  for (let i = 0; i <= 20; i++) {
    const a = 1 + i * 0.05;
    await page.evaluate((v) => {
      if (STATE.params && STATE.params.a) STATE.params.a.value = v;
      redrawAll();
    }, a);
    await page.waitForTimeout(220);      // сглаживание успевает доехать
    const st = await page.evaluate(() => {
      const lab = document.querySelector('#chart text.curve-name');
      const box = document.querySelector('#chart').getBoundingClientRect();
      const tick = Array.from(document.querySelectorAll('#chart text.axis-num'))
        .filter(t => t.textContent.trim() === '2')[0];
      const r = lab ? lab.getBoundingClientRect() : null;
      const tr = tick ? tick.getBoundingClientRect() : null;
      return { x: r ? +(r.left - box.left).toFixed(1) : null,
               y: r ? +(r.top - box.top).toFixed(1) : null,
               tick: tr ? +(tr.left - box.left).toFixed(1) : null };
    });
    steps.push({ a: +a.toFixed(2), ...st });
  }

  let maxDy = 0, maxDx = 0, tickMove = 0;
  for (let i = 1; i < steps.length; i++) {
    if (steps[i].y != null && steps[i - 1].y != null)
      maxDy = Math.max(maxDy, Math.abs(steps[i].y - steps[i - 1].y));
    if (steps[i].x != null && steps[i - 1].x != null)
      maxDx = Math.max(maxDx, Math.abs(steps[i].x - steps[i - 1].x));
    if (steps[i].tick != null && steps[0].tick != null)
      tickMove = Math.max(tickMove, Math.abs(steps[i].tick - steps[0].tick));
  }
  fs.writeFileSync(OUT, JSON.stringify({ steps, maxDy, maxDx, tickMove, pageErrors: errs }, null, 1), 'utf8');
  console.log('шагов:', steps.length);
  console.log('вертикаль подписи:', steps.map(s => s.y).join(' → '));
  console.log('плоскость (деление «2»):', steps[0].tick, '· ушла максимум на', tickMove.toFixed(1), 'px');
  console.log('наибольший скачок по вертикали за шаг:', maxDy.toFixed(1), 'px');
  console.log('по горизонтали за шаг:', maxDx.toFixed(1), 'px');
  console.log('ошибок страницы:', errs.length);
  console.log(maxDy <= 2 ? '\nСОШЛОСЬ: подпись не дёргается (не больше 2 px за шаг)'
                         : '\nНЕ СОШЛОСЬ: подпись дёргается');
  await browser.close();
  process.exit(maxDy <= 2 ? 0 : 1);
})();
