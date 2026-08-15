// Разовый разбор Фазы 3 (Б6, Б8, Б9, Б10): что именно уходит в .tex из сцены
// «Сложение заводов» и откуда оно на холсте берётся.
//   node calc2/tests/tex_leak_probe.mjs [ключ_сцены] [light|dark]
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SCENE = process.argv[2] || 'plants';
const THEME = process.argv[3] || 'dark';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

const out = await page.evaluate(({ scene, theme }) => {
  document.documentElement.setAttribute('data-theme', theme);
  resetSceneMemory();
  pickScene(scene);
  redrawAll();
  const tex = buildTex('', '');
  // Полный список того, что видит обход холста, с происхождением каждого узла.
  const rows = [];
  const walk = (node, path) => {
    for (const el of node.children) {
      const tag = el.tagName.toLowerCase();
      if (tag === 'defs' || tag === 'clippath' || tag === 'marker') continue;
      const cls = String(el.getAttribute('class') || '');
      if (cls === 'axes' || cls === 'grid') continue;
      if (tag === 'g') { walk(el, path + '/g' + (cls ? '.' + cls : '')); continue; }
      const cs = getComputedStyle(el);
      rows.push({
        tag, path,
        fill: cs.fill, stroke: cs.stroke,
        skip: !!el.getAttribute('data-skip-export'),
        expr: el.getAttribute('data-expr') || '',
        exp: el.getAttribute('data-export') || '',
        d: (el.getAttribute('d') || '').slice(0, 40),
        txt: (el.textContent || '').slice(0, 30),
      });
    }
  };
  walk(document.getElementById('chart'), '');
  const canvas = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
  const halo = getComputedStyle(document.documentElement).getPropertyValue('--halo').trim();
  return { tex, rows, canvas, halo, bounds: { Qmin: CONFIG.Qmin, Qmax: CONFIG.Qmax, Pmin: CONFIG.Pmin, Pmax: CONFIG.Pmax } };
}, { scene: SCENE, theme: THEME });

await browser.close();

console.log('== холст: ' + out.canvas + ', гало: ' + out.halo);
console.log('== окно: Q ' + out.bounds.Qmin.toFixed(1) + '…' + out.bounds.Qmax.toFixed(1) +
            ', P ' + out.bounds.Pmin.toFixed(1) + '…' + out.bounds.Pmax.toFixed(1));
console.log('\n== узлы холста ==');
out.rows.forEach((r, i) => console.log(
  String(i).padStart(3) + ' ' + r.tag.padEnd(7) + ' ' + r.path.padEnd(28) +
  ' fill=' + String(r.fill).padEnd(22) + ' stroke=' + String(r.stroke).padEnd(22) +
  (r.skip ? ' SKIP' : '') + (r.expr ? ' expr=' + r.expr : '') + (r.txt ? ' «' + r.txt + '»' : '')));
console.log('\n== .tex ==\n' + out.tex);
