/* ФАЗА 3.2 сессии 21.08. ЦЕЛЬ ДЛЯ ДВОЙНОГО ЩЕЛЧКА ПО ПОДПИСИ КРИВОЙ.

   Меряется то, во что целится рука: размер области, принимающей двойной
   щелчок, и сам двойной щелчок настоящей мышью по краю подписи — там, где
   владелец промахивался.

   Запуск: node scripts/calc2_labelhit_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');
const PORT = process.argv[2] || '8099';
const OUT  = process.argv[3] || 'reports/calc2_labelhit.json';
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

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  const out = {};
  let small = 0, total = 0;
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof pickScene === 'function');
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(850);
    const r = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('#chart text.curve-name')];
      const hits = [...document.querySelectorAll('#chart rect[data-rename-hit]')];
      const own = n => Array.from(n.childNodes).filter(c => c.nodeType === 3)
                        .map(c => c.nodeValue).join('').trim();
      return labels.map(t => {
        const tb = t.getBoundingClientRect();
        // Прямоугольник, накрывающий эту подпись (у каждой свой, ближайший).
        let best = null, bestD = 1e9;
        hits.forEach(h => {
          const hb = h.getBoundingClientRect();
          const d = Math.hypot(hb.x + hb.width / 2 - (tb.x + tb.width / 2),
                               hb.y + hb.height / 2 - (tb.y + tb.height / 2));
          if (d < bestD) { bestD = d; best = hb; }
        });
        return {
          text: own(t) || t.textContent.trim(),
          label: [Math.round(tb.width), Math.round(tb.height)],
          hit: best && bestD < 30 ? [Math.round(best.width), Math.round(best.height)] : null,
          at: best && bestD < 30 ? [Math.round(best.x + best.width / 2), Math.round(best.y + best.height / 2)] : null,
        };
      });
    });
    out[key] = r;
    r.forEach(x => { total++; if (!x.hit || x.hit[0] < 24 || x.hit[1] < 24) small++; });
    process.stdout.write('.');
  }
  console.log('');
  console.log('подписей кривых:', total, '· с целью меньше 24×24:', small);

  /* Живой двойной щелчок по КРАЮ подписи — там, где рука промахивалась. */
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function');
  await page.evaluate(() => pickScene('sd'));
  await page.waitForTimeout(900);
  const spot = await page.evaluate(() => {
    const t = [...document.querySelectorAll('#chart text.curve-name')][0];
    const b = t.getBoundingClientRect();
    // Восемь пикселей мимо слова вбок и вниз: прежняя цель здесь кончалась.
    return { x: Math.round(b.x + b.width + 6), y: Math.round(b.y + b.height + 4),
             word: t.textContent.trim(), box: [Math.round(b.width), Math.round(b.height)] };
  });
  await page.mouse.dblclick(spot.x, spot.y);
  await page.waitForTimeout(400);
  const opened = await page.evaluate(() => !!document.getElementById('pt-rename'));
  console.log('двойной щелчок мимо слова на 6×4 px открыл правку:', opened,
              '| подпись', JSON.stringify(spot.word), spot.box.join('×'));
  fs.writeFileSync(OUT, JSON.stringify({ scenes: out, missMeasure: { spot, opened }, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
})();
