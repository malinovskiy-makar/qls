const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8701';
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  p.on('pageerror', e => console.log('PAGEERR', e.message));
  p.on('console', m => { const t = m.text(); if (t.startsWith('DBG')) console.log(t); });
  await p.goto(BASE + '/login/');
  await p.fill('input[name="username"]', 'student1');
  await p.fill('input[name="password"]', 'student12345');
  await p.click('button[type=submit], input[type=submit]');
  await p.waitForLoadState('domcontentloaded');
  await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  await p.evaluate(() => pickScene('sd'));
  await p.waitForTimeout(1200);
  // инструментируем: смотрим, доходит ли событие до полосы
  await p.evaluate(() => {
    window.__hits = [];
    document.querySelectorAll('path[data-hit-name]').forEach(el => {
      el.addEventListener('click', () => { window.__hits.push('native click ' + el.getAttribute('data-hit-name')); }, true);
      el.addEventListener('mousedown', () => { window.__hits.push('mousedown'); }, true);
      el.addEventListener('mouseup', () => { window.__hits.push('mouseup'); }, true);
    });
    const chart = document.querySelector('#chart');
    chart.addEventListener('click', () => window.__hits.push('chart click'), false);
    window.__armCalls = [];
    const orig = window.armCurve;
    window.armCurve = function (n) { window.__armCalls.push(n); return orig.apply(this, arguments); };
  });
  const spot = await p.evaluate(() => {
    const band = document.querySelector('path[data-hit-name="D"]');
    const L = band.getTotalLength();
    const box = document.querySelector('#chart').getBoundingClientRect();
    for (let i = 10; i <= 90; i += 2) {
      const pt = band.getPointAtLength(L * i / 100);
      const m = band.getScreenCTM();
      const sx = pt.x*m.a + pt.y*m.c + m.e, sy = pt.x*m.b + pt.y*m.d + m.f;
      if (sx < box.left+4 || sx > box.right-4 || sy < box.top+4 || sy > box.bottom-4) continue;
      if (document.elementFromPoint(sx, sy) === band) return {x: sx, y: sy};
    }
    return null;
  });
  console.log('spot', spot);
  await p.mouse.click(spot.x, spot.y);
  await p.waitForTimeout(700);
  console.log(await p.evaluate(() => ({
    hits: window.__hits, armCalls: window.__armCalls, armed: STATE.armedCurve,
    handlerPresent: !!document.querySelector('path[data-hit-name="D"]').__on,
    onList: (document.querySelector('path[data-hit-name="D"]').__on || []).map(o => o.type + '.' + (o.name||'')),
  })));
  await b.close();
})();
