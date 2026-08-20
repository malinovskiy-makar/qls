/* ФАЗА 2 сессии 20.08. КРИВЫЕ МЫШЬЮ НЕ ДВИГАЮТСЯ НИГДЕ.

   Решение владельца 20.08: «на графике нельзя двигать функции графически
   мышкой». Проверяется настоящим протягиванием: прибор находит полосу
   попадания кривой, УБЕЖДАЕТСЯ, ЧТО ЩЕЛЧОК ПОПАДЁТ ИМЕННО В НЕЁ
   (elementFromPoint), тащит на 80 px вниз и сравнивает геометрию видимых линий
   и текст всех формул до и после.

   Отдельно переписываются манипуляторы сцены — подвижные элементы с курсором
   grab (клин налога, потолок цены, МРОТ, мировая цена). Их правило не трогает,
   и они обязаны по-прежнему тащиться.

   Запуск: node scripts/calc2_nodrag_probe.js <порт> <файл.json> [сцены] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2_nodrag.json';
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
async function openScene(page, key) {
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object',
                             null, { timeout: 20000 });
  await page.evaluate(k => pickScene(k), key);
  await page.waitForTimeout(1000);
}

// Отпечаток: видимые линии кривых + все записи формул, какие есть на экране.
const SHOT = () => {
  const round = d => String(d || '').replace(/-?\d+\.\d+/g, m => (+m).toFixed(1));
  const curves = [...document.querySelectorAll('#chart path')].filter(p => {
    if (p.getAttribute('data-skip-export') === '1') return false;
    const c = getComputedStyle(p);
    if (!c.stroke || c.stroke === 'none') return false;
    if (/rgba\((?:\d+,\s*){3}0\)|transparent/.test(c.stroke)) return false;
    if (c.fill && c.fill !== 'none' && !/rgba\((?:\d+,\s*){3}0\)/.test(c.fill)) return false;
    return (p.getAttribute('d') || '').length > 12;
  }).map(p => round(p.getAttribute('d'))).join('|');
  const texts = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS : [])
    .filter(i => i.isConnected).map(i => i.id + '=' + i.value).join(';')
    + '#' + (STATE.curves || []).map(c => c.expr).join(';');
  return { curves, texts };
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
  const only = process.argv[4];
  if (only) scenes = scenes.filter(k => only.split(',').indexOf(k) >= 0);
  console.log('сцен:', scenes.length);

  const out = {};
  for (const key of scenes) {
    await openScene(page, key);
    const rec = { bands: [], grabs: [], moved: [], cursors: {} };

    // Сколько полос попадания и какие у них курсоры.
    const bands = await page.evaluate(() => {
      return [...document.querySelectorAll('#chart path[data-hit], #chart path[data-hit-name]')]
        .map((p, i) => ({ i, name: p.getAttribute('data-hit-name') || p.getAttribute('data-hit') || '?',
                          cursor: getComputedStyle(p).cursor }));
    });
    rec.bands = bands;
    bands.forEach(b => { rec.cursors[b.cursor] = (rec.cursors[b.cursor] || 0) + 1; });

    for (const b of bands) {
      // Точка НА полосе, в которую щелчок действительно попадёт.
      const aim = await page.evaluate((idx) => {
        const p = [...document.querySelectorAll('#chart path[data-hit], #chart path[data-hit-name]')][idx];
        if (!p) return null;
        const len = p.getTotalLength();
        for (let f = 0.25; f <= 0.75; f += 0.06) {
          const pt = p.getPointAtLength(len * f);
          const svg = document.getElementById('chart');
          const r = svg.getBoundingClientRect();
          const vb = svg.viewBox.baseVal;
          const kx = vb && vb.width ? r.width / vb.width : 1;
          const ky = vb && vb.height ? r.height / vb.height : 1;
          const x = r.x + pt.x * kx, y = r.y + pt.y * ky;
          if (document.elementFromPoint(x, y) === p) return { x, y };
        }
        return null;
      }, b.i);
      if (!aim) { rec.moved.push({ name: b.name, skip: 'полоса ничем не ловится' }); continue; }

      const before = await page.evaluate(SHOT);
      await page.mouse.move(aim.x, aim.y);
      await page.mouse.down();
      await page.mouse.move(aim.x, aim.y + 40, { steps: 6 });
      await page.mouse.move(aim.x, aim.y + 80, { steps: 6 });
      await page.mouse.up();
      await page.waitForTimeout(400);
      const after = await page.evaluate(SHOT);
      rec.moved.push({ name: b.name, cursor: b.cursor,
                       curveMoved: before.curves !== after.curves,
                       formulaChanged: before.texts !== after.texts });
      if (before.curves !== after.curves) await openScene(page, key);   // вернуть сцену
    }

    /* Манипуляторы сцены: всё с курсором grab внутри холста. Их правило не
       трогает, поэтому мало перечислить — каждый обязан ПО-ПРЕЖНЕМУ ТАЩИТЬСЯ.
       Признак движения — любое изменившееся число состояния сцены: у клина
       налога это ставка, у потолка цены — регулируемая цена, у точки
       эластичности — её положение. Общий снимок чисел избавляет от списка
       «какое поле у какого манипулятора», который разъехался бы с продуктом. */
    rec.grabs = [];
    const grabCount = await page.evaluate(() => [...document.querySelectorAll('#chart *')]
      .filter(el => getComputedStyle(el).cursor === 'grab').length);
    for (let gi = 0; gi < grabCount; gi++) {
      const aim = await page.evaluate((idx) => {
        const el = [...document.querySelectorAll('#chart *')]
          .filter(e => getComputedStyle(e).cursor === 'grab')[idx];
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const x = r.x + r.width / 2, y = r.y + r.height / 2;
        const nums = {};
        Object.keys(STATE).forEach(k => { if (typeof STATE[k] === 'number') nums[k] = STATE[k]; });
        return { x, y, hit: document.elementFromPoint(x, y) === el, nums: JSON.stringify(nums),
                 tag: el.tagName.toLowerCase() + (el.getAttribute('class') ? '.' + el.getAttribute('class') : '') };
      }, gi);
      if (!aim) continue;
      await page.mouse.move(aim.x, aim.y);
      await page.mouse.down();
      await page.mouse.move(aim.x + 30, aim.y - 45, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(350);
      const nums2 = await page.evaluate(() => {
        const n = {}; Object.keys(STATE).forEach(k => { if (typeof STATE[k] === 'number') n[k] = STATE[k]; });
        return JSON.stringify(n);
      });
      rec.grabs.push({ tag: aim.tag, hit: aim.hit, stillDrags: nums2 !== aim.nums });
      if (nums2 !== aim.nums) await openScene(page, key);
    }
    out[key] = rec;
    process.stdout.write('.');
  }
  console.log('');
  fs.writeFileSync(OUT, JSON.stringify({ scenes: out, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
  console.log('записано:', OUT, '· ошибок страницы:', errs.length);
})();
