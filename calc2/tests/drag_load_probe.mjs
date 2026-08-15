// Замер Фазы 7 (Б34): сколько объектов на графике можно двигать мышью
// одновременно, по каждой сцене. Считаем зоны захвата на холсте (курсор grab
// или move) и ползунки «Сдвиг кривых» в правой панели.
//   node calc2/tests/drag_load_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

const keys = await page.evaluate(() =>
  Object.keys(SCENE_ROUTE).filter(k => !(SCENE_ROUTE[k] || {}).soon));

const rows = [];
for (const k of keys) {
  const r = await page.evaluate(async (key) => {
    resetSceneMemory();
    pickScene(key);
    await new Promise(res => setTimeout(res, 220));
    // Подвижное на самом ГРАФИКЕ: элемент с курсором захвата.
    const grab = [];
    document.querySelectorAll('svg#chart *').forEach(el => {
      const cs = getComputedStyle(el);
      if (!/grab|move|ew-resize|ns-resize/.test(cs.cursor)) return;
      if (!el.getClientRects().length) return;
      grab.push(el.tagName.toLowerCase() + (el.getAttribute('class') ? '.' + el.getAttribute('class') : ''));
    });
    // Кривые, которые тянутся мышью (у них своя прозрачная дорожка).
    const curves = (typeof pultCurveList === 'function') ? pultCurveList().length : 0;
    return { grab: grab.length, kinds: grab.slice(0, 6), shift: curves };
  }, k);
  rows.push([k, r]);
}
await browser.close();

/* Правило перегруза считаем по объектам НА ГРАФИКЕ: именно за них борется
   рука. Ползунок «Сдвиг кривых» живёт в правой панели и мышью на холсте не
   мешает — его показываем отдельной колонкой как второй показ того же
   действия, но в счёт перегруза не берём. */
console.log('| Сцена | подвижных на графике | ползунков «Сдвиг кривых» (второй показ) |');
console.log('|---|---|---|');
let over = [];
for (const [k, r] of rows) {
  if (r.grab > 3) over.push(`${k} (${r.grab})`);
  console.log(`| ${k} | ${r.grab}${r.grab > 3 ? ' !' : ''} ${r.kinds.length ? '· ' + r.kinds.join(', ') : ''} | ${r.shift} |`);
}
console.log('\nСцен с перегрузом (больше трёх подвижных объектов на графике): ' +
  (over.length ? over.length + ' — ' + over.join(', ') : 'нет'));
console.log('Сцен, где сдвиг кривых показан дважды (мышью и ползунком): ' +
  rows.filter(([, r]) => r.shift > 0).length);
