/* Опись левой панели: какие карточки видны в каждой из 41 сцены, в каком
   порядке, что внутри «Что изучаем» и «Излишки». Только читает.
     node calc2/tests/night_panel_inventory.mjs [--json файл] */
import { chromium } from 'playwright';
import fs from 'fs';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const outArg = process.argv.indexOf('--json');
const OUT = outArg > 0 ? process.argv[outArg + 1] : null;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.log('PAGEERROR:', e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const data = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const keys = Object.keys(SCENE_ROUTE);
  const rows = [];
  for (const k of keys) {
    resetSceneMemory();
    pickScene(k); await wait(200);
    const cards = [...document.querySelectorAll('#tools-panel .tools-body > .section')]
      .filter(s => s.style.display !== 'none' && s.offsetParent !== null)
      .map(s => {
        const b = s.querySelector(':scope > .fold-btn span > b');
        const body = s.querySelector(':scope > .fold-body');
        const inputs = body ? [...body.querySelectorAll('input,select,button')]
          .filter(e => e.offsetParent !== null).length : 0;
        return { id: s.id, name: b ? b.textContent.trim() : '(без заголовка)',
                 open: (s.querySelector(':scope > .fold-btn') || {}).getAttribute
                       ? s.querySelector(':scope > .fold-btn').getAttribute('aria-expanded') === 'true' : null,
                 controls: inputs };
      });
    rows.push({ key: k, name: SCENE_NAMES[k] || k, mode: STATE.mode, scenario: STATE.scenario, cards });
  }
  return rows;
});

console.log('сцен: ' + data.length);
const counts = {};
data.forEach(r => { const n = r.cards.length; counts[n] = (counts[n] || 0) + 1; });
console.log('карточек в панели → сцен: ' + JSON.stringify(counts));
const seq = {};
data.forEach(r => { const s = r.cards.map(c => c.id).join(' → '); (seq[s] = seq[s] || []).push(r.key); });
console.log('\nразные наборы карточек (' + Object.keys(seq).length + '):');
Object.entries(seq).forEach(([s, ks]) => console.log('  [' + ks.length + '] ' + s + '\n        ' + ks.join(', ')));
const withAnalysis = data.filter(r => r.cards.some(c => c.id === 'sec-analysis'));
const withAreas = data.filter(r => r.cards.some(c => c.id === 'sec-areas'));
const withMono = data.filter(r => r.cards.some(c => c.id === 'sec-mono'));
const withTax = data.filter(r => r.cards.some(c => c.id === 'sec-tax'));
console.log('\n«Что изучаем» (sec-analysis) виден в ' + withAnalysis.length + ' сценах: ' + withAnalysis.map(r=>r.key).join(', '));
console.log('«Излишки» (sec-areas) виден в ' + withAreas.length + ' сценах: ' + withAreas.map(r=>r.key).join(', '));
console.log('«Структура рынка» (sec-mono) виден в ' + withMono.length + ' сценах: ' + withMono.map(r=>r.key).join(', '));
console.log('«Вмешательство» (sec-tax) виден в ' + withTax.length + ' сценах: ' + withTax.map(r=>r.key).join(', '));
if (OUT) { fs.writeFileSync(OUT, JSON.stringify(data, null, 1)); console.log('\nJSON: ' + OUT); }
await browser.close();
