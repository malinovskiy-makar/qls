// ФАЗА 4. Три описи по всем сценам. Только чтение: ничего не применяет и не
// сохраняет, поля правки закрывает клавишей Escape.
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const page = await browser.newPage();
const errors = []; page.on('pageerror', e => errors.push(e.message));
await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin'); await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1300);

const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const names = await page.$$eval('.scard', els => Object.fromEntries(
  els.map(e => [e.dataset.scene, (e.querySelector('.scard-name') || e).textContent.trim()])));

const rows = [];
for (const key of scenes) {
  await page.evaluate(k => { pickScene(k); setToolsOpen(true); }, key);
  await page.waitForTimeout(600);
  const r = await page.evaluate(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const vis = el => !!(el && el.getClientRects().length);

    // ── ОПИСЬ 1. Что на холсте берётся мышью.
    const drag = [];
    document.querySelectorAll('#chart *').forEach(e => {
      const c = getComputedStyle(e).cursor;
      if (!/grab|move|resize|pointer/.test(c)) return;
      if (!vis(e)) return;
      const b = e.getBBox ? e.getBBox() : null;
      drag.push({ cur: c, tag: e.tagName, cls: e.getAttribute('class') || '',
                  w: b ? Math.round(b.width) : null, h: b ? Math.round(b.height) : null });
    });

    // ── ОПИСЬ 3. Сколько на холсте графиков (у сцены с двумя своя сетка на каждый).
    const grids = document.querySelectorAll('#chart g.grid, #chart .grid').length;

    // ── ОПИСЬ 2. Где щелчок по значению даёт ПОЛЕ С РАМКОЙ.
    // Кандидаты — всё, по чему в правой панели щёлкают ради правки значения.
    const clickable = [...document.querySelectorAll(
      '#params-body .pchip-editable, #params-body .param-bound, #params-body .pchip-lab, ' +
      '#params-body .pchip-val, #sb-body .stat b, #params-body b')].filter(vis);
    const edits = [];
    for (const el of clickable.slice(0, 24)) {
      const label = (el.textContent || '').trim().slice(0, 24);
      const beforeInputs = new Set([...document.querySelectorAll('#params-panel input, #sb-body input')]);
      el.click(); await sleep(160);
      const fresh = [...document.querySelectorAll('#params-panel input, #sb-body input')]
        .filter(i => !beforeInputs.has(i) && vis(i));
      for (const i of fresh) {
        const cs = getComputedStyle(i);
        const rect = i.getBoundingClientRect();
        const bordered = parseFloat(cs.borderTopWidth) > 0.5 || parseFloat(cs.borderBottomWidth) > 0.5;
        const boxed = bordered || (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent');
        edits.push({ what: label, cls: i.className || '', id: i.id || '',
                     w: Math.round(rect.width), bordered, bg: cs.backgroundColor,
                     border: cs.borderTopWidth + '/' + cs.borderBottomWidth, boxed });
      }
      document.activeElement && document.activeElement.blur();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await sleep(90);
    }
    return { drag, grids, edits, mode: STATE.mode };
  });
  rows.push({ key, name: names[key] || key, ...r });
  process.stdout.write('.');
}
process.stdout.write('\n');
writeFileSync(process.env.OUT || 'phase4.json', JSON.stringify({ rows, errors }, null, 1));
console.log('сцен:', rows.length, 'ошибок страницы:', errors.length);
await browser.close();
