/* ФАЗА 3.5 сессии 21.08. ПУНКТИР К ОСИ БЕЗ ЧИСЛА — ПАНЕЛЬНО-ЧЕСТНЫЙ ЗАМЕР.

   ⚠️ ПРИБОР 20.08 СВЕРЯЛ ПУНКТИРЫ ПАНЕЛЕЙ С ГЛАВНЫМИ ШКАЛАМИ. У сцен с двумя
   и более панелями (производство, дискриминация, монополист на внешнем рынке,
   двусторонняя монополия) каждая панель живёт в своей системе координат, её
   ось стоит не там, где `sx(0)`/`sy(0)`, и всякий пунктир такой панели
   объявлялся «идущим в никуда». Отсюда четыре из шести названных сцен.

   Здесь оси находятся ПО САМОМУ ХОЛСТУ: деления шкалы помечены классом
   `axis-num`, и у горизонтальной оси они выстраиваются в ряд по y, у
   вертикальной — в столбец по x. Ось панели находится своими делениями,
   реестра панелей заводить не нужно.

   Дефект: пунктирный отрезок, доходящий до оси, у которого на этой оси в
   ближайших 34 px нет ни подписи координаты (`coord-num`), ни деления.

   Запуск: node scripts/calc2_dashaxis_probe.js <порт> <файл.json> [сцены] */
const { chromium } = require('playwright');
const fs = require('fs');
const PORT = process.argv[2] || '8099';
const OUT  = process.argv[3] || 'reports/calc2_dashaxis.json';
const BASE = `http://127.0.0.1:${PORT}`;

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

/* ⚠️ ВСЁ МЕРЯЕТСЯ В ОДНОЙ СИСТЕМЕ КООРДИНАТ — ЭКРАННОЙ.

   Первая версия брала у подписей `getBBox()` (координаты ЛОКАЛЬНЫЕ, внутри
   своей группы), а у пунктиров — атрибуты x1/y1 (локальные внутри СВОЕЙ
   группы). У панельных сцен группы разные и сдвинуты друг относительно друга,
   поэтому число и пунктир, стоящие на экране рядом, в замере оказывались за
   сотни пикселей друг от друга: «Дискриминация 3-й степени» и «Монополист на
   внешнем рынке» отчитались четырьмя дефектами на четыре пунктира, а на
   снимке экрана все четыре числа стоят на месте.

   Поэтому и подписи, и концы отрезков приводятся к экрану: подписи через
   getBoundingClientRect, отрезки через getScreenCTM. */
const SNAP = () => {
  const svgEl = document.getElementById('chart');
  const toScreen = (el, x, y) => {
    const m = el.getScreenCTM();
    if (!m) return null;
    const p = svgEl.createSVGPoint(); p.x = x; p.y = y;
    const d = p.matrixTransform(m);
    return { x: d.x, y: d.y };
  };
  const centers = (sel) => [...document.querySelectorAll(sel)].map(t => {
    const b = t.getBoundingClientRect();
    if (!(b.width >= 0) || (b.width === 0 && b.height === 0)) return null;
    return { x: b.x + b.width / 2, y: b.y + b.height / 2,
             right: b.x + b.width, top: b.y,
             text: (t.getAttribute('data-raw') || t.textContent || '').trim() };
  }).filter(Boolean);

  const ticks  = centers('#chart text.axis-num');
  const coords = centers('#chart text.coord-num');

  const groupBy = (arr, key, tol) => {
    const gs = [];
    arr.slice().sort((a, b) => a[key] - b[key]).forEach(p => {
      const g = gs[gs.length - 1];
      if (g && Math.abs(p[key] - g.at) <= tol) {
        g.items.push(p); g.at = (g.at * (g.items.length - 1) + p[key]) / g.items.length;
      } else gs.push({ at: p[key], items: [p] });
    });
    return gs.filter(g => g.items.length >= 2);
  };
  const hAxes = groupBy(ticks, 'y', 5).map(g => ({ y: Math.min(...g.items.map(i => i.top)), n: g.items.length }));
  const vAxes = groupBy(ticks, 'x', 8).map(g => ({ x: Math.max(...g.items.map(i => i.right)), n: g.items.length }));

  const AX_TOL = 20;    // от подписи до самой оси
  const NEAR   = 34;    // насколько близко к концу пунктира ищем число

  const dashed = [...document.querySelectorAll('#chart line')].filter(l => {
    const c = getComputedStyle(l);
    if (!c.strokeDasharray || c.strokeDasharray === 'none') return false;
    if (parseFloat(c.strokeOpacity || '1') < 0.05) return false;
    return true;
  }).map(l => {
    const a = toScreen(l, +l.getAttribute('x1'), +l.getAttribute('y1'));
    const b = toScreen(l, +l.getAttribute('x2'), +l.getAttribute('y2'));
    return (a && b) ? { x1: a.x, y1: a.y, x2: b.x, y2: b.y } : null;
  }).filter(Boolean);

  const bad = [], good = [];
  const numbersAt = (x, y) => [...coords, ...ticks]
    .filter(t => Math.hypot(t.x - x, t.y - y) <= NEAR);

  /* Второй вопрос того же места: не напечатано ли число ДВАЖДЫ. Две точки,
     сошедшиеся в одну (равновесие и точка единичной эластичности), рисуют
     свою подпись каждая, и на оси встаёт «50» под «50». */
  const dup = [];
  dashed.forEach(d => {
    const horiz = Math.abs(d.y1 - d.y2) < 1.5, vert = Math.abs(d.x1 - d.x2) < 1.5;
    if (!horiz && !vert) return;
    let at = null, rec = null;
    if (vert) {
      const yEnd = Math.max(d.y1, d.y2);
      const ax = hAxes.find(a => Math.abs(yEnd - a.y) <= AX_TOL);
      if (!ax) return;
      at = { x: d.x1, y: ax.y + 8 };
      rec = { kind: 'к оси X', x: Math.round(d.x1), y: Math.round(ax.y) };
    } else {
      const xEnd = Math.min(d.x1, d.x2);
      const ax = vAxes.find(a => Math.abs(xEnd - a.x) <= AX_TOL);
      if (!ax) return;
      at = { x: ax.x - 8, y: d.y1 };
      rec = { kind: 'к оси Y', x: Math.round(ax.x), y: Math.round(d.y1) };
    }
    const found = numbersAt(at.x, at.y);
    if (!found.length) bad.push(rec);
    else {
      good.push(rec);
      const same = found.map(f => f.text);
      const twice = same.filter((t, i) => t && same.indexOf(t) !== i);
      if (twice.length) dup.push(Object.assign({ text: twice[0] }, rec));
    }
  });
  return { hAxes: hAxes.length, vAxes: vAxes.length,
           dashed: dashed.length, ok: good.length,
           bad, badN: bad.length, dup, dupN: dup.length };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  let scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  if (process.argv[4]) scenes = scenes.filter(k => process.argv[4].split(',').indexOf(k) >= 0);
  const out = {};
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof pickScene === 'function');
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(900);
    out[key] = await page.evaluate(SNAP);
    process.stdout.write('.');
  }
  console.log('');
  const bad = Object.entries(out).filter(([, v]) => v.badN > 0);
  const dup = Object.entries(out).filter(([, v]) => v.dupN > 0);
  console.log('сцен всего:', scenes.length, '· с пунктиром без числа:', bad.length,
              '· с задвоенным числом:', dup.length);
  bad.forEach(([k, v]) => console.log('  без числа · ' + k + ': ' + v.badN + ' из ' + (v.badN + v.ok) +
                                      ' (осей: ' + v.hAxes + '×' + v.vAxes + ')  ' +
                                      JSON.stringify(v.bad.slice(0, 4))));
  dup.forEach(([k, v]) => console.log('  дважды   · ' + k + ': ' + JSON.stringify(v.dup.slice(0, 4))));
  fs.writeFileSync(OUT, JSON.stringify({ scenes: out, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
})();
