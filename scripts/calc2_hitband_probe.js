/* ФАЗА 3.1 сессии 21.08. ПОЛОСА ЗАХВАТА КРИВОЙ ВО ВСЕХ СЦЕНАХ (п. 21 ревью).

   ⚠️ СНАЧАЛА ПРИЗНАК, ПОТОМ СЧЁТ. Замер владельца дал 28 полос в 14 сценах,
   отчёт прошлой сессии — 30 сцен из 41. Расходятся не сцены, а признак:
   полос ДВА рода и у них разные атрибуты.
     · `data-hit`      — ставит общий рисовальщик кривых тем, что лежит в
                         STATE.curves (он же кладёт и `data-hit-name`);
     · `data-hit-name` — ставит и общий рисовальщик, и добор `drawCurveHits`
                         для кривых, которые сцена рисует сама.
   Считать по `data-hit` значит не видеть добор вовсе. Здесь печатаются ОБА
   числа, и итог берётся по `data-hit-name`: щёлкнуть можно по любой полосе,
   чем бы она ни была поставлена.

   Запуск: node scripts/calc2_hitband_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');
const PORT = process.argv[2] || '8099';
const OUT  = process.argv[3] || 'reports/calc2_hitband.json';
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
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof pickScene === 'function');
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(900);
    out[key] = await page.evaluate(() => {
      const wrap = document.querySelector('.graph-wrap') || document;
      const vis = el => el.getClientRects().length > 0 || !!el.closest('svg');
      const byHit  = [...wrap.querySelectorAll('path[data-hit]')].filter(vis);
      const byName = [...wrap.querySelectorAll('path[data-hit-name]')].filter(vis);
      /* Сколько кривых ВООБЩЕ нарисовано: полосы должно хватать на каждую.
         Считаем по тому же списку, по которому строится добор. */
      let targets = [];
      try { targets = (snapTargets() || []).map(t => t.name); } catch (e) {}
      return {
        dataHit: byHit.length,
        dataHitName: byName.length,
        names: byName.map(p => p.getAttribute('data-hit-name')),
        targets,
        missing: targets.filter(n => !byName.some(p => p.getAttribute('data-hit-name') === n)),
      };
    });
    process.stdout.write('.');
  }
  console.log('');
  const withBand = Object.values(out).filter(v => v.dataHitName > 0).length;
  const withHit  = Object.values(out).filter(v => v.dataHit > 0).length;
  console.log('сцен всего:', scenes.length,
              '· с полосой (data-hit-name):', withBand,
              '· с полосой (data-hit):', withHit);
  console.log('сцен без единой полосы:', Object.entries(out).filter(([, v]) => !v.dataHitName).map(([k]) => k).join(', ') || '—');
  fs.writeFileSync(OUT, JSON.stringify({ scenes: out, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
})();
