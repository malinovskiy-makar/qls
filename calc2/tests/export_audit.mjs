// Замер содержимого выгрузки .tex (фаза 2, пункты А45–А49).
// Печатает по сцене: размер картинки, кегли, сколько кривых формулой против
// таблиц координат, сколько подписей математикой, совпадает ли набор подписей
// с тем, что видно на экране.
// Запуск: node calc2/tests/export_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SCENES = (process.env.SCENES || 'sd,tax,mono,adas,isoquant,costs').split(',');

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);
if (!await page.evaluate(() => typeof buildTex === 'function')) {
  console.error('SKIP: calc2 не загрузился'); await browser.close(); process.exit(3);
}

const measure = async (key) => page.evaluate(async (k) => {
  pickScene(k);
  await new Promise(r => setTimeout(r, 450));
  const tex = buildTex('Проба', '');
  const size = /width=([\d.]+)cm, height=([\d.]+)cm/.exec(tex);
  const plots = tex.match(/\\addplot\[[^\]]*\]/g) || [];
  const tableBlocks = [...tex.matchAll(/\\addplot\[[^\]]*\] *coordinates \{([^}]*)\}/g)]
    .map(m => (m[1].match(/\(/g) || []).length);
  const tables = tableBlocks.length;
  const bigTables = tableBlocks.filter(n => n > 5).length;   // настоящие кривые точками
  const segs = tableBlocks.filter(n => n <= 5).length;       // короткие отрезки-проекции
  const formulas = (tex.match(/\\addplot\[[^\]]*\] *\{/g) || []).length;
  const nodes = tex.match(/\\node\[[^\]]*\] at \(axis cs:[^)]*\) \{([^}]*(?:\{[^}]*\}[^}]*)*)\}/g) || [];
  const mathNodes = nodes.filter(n => /\{\$/.test(n)).length;
  const pts = [...tex.matchAll(/font=\\fontsize\{([\d.]+)\}/g)].map(m => +m[1]);
  // Подписи, которые видит человек на холсте.
  const vis = [];
  document.querySelectorAll('#chart text').forEach(t => {
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    const own = Array.prototype.filter.call(t.childNodes, n => n.nodeType === 3).map(n => n.nodeValue).join('').trim();
    if (own) vis.push(own);
  });
  return {
    w: size ? +size[1] : null, h: size ? +size[2] : null,
    plots: plots.length, tables, formulas, bigTables, segs,
    nodes: nodes.length, mathNodes,
    pts: [...new Set(pts)].sort((a, b) => a - b),
    visible: vis.length,
    legendEntries: (tex.match(/\\addlegendentry/g) || []).length,
    chars: tex.length,
  };
}, key);

console.log('сцена       картинка   форм/крив+отр  подписей(мат.)  видимых  кегли(pt)  легенд');
for (const key of SCENES) {
  const r = await measure(key);
  console.log(
    key.padEnd(11) +
    `${r.w}×${r.h}см`.padEnd(11) +
    `${r.formulas}/${r.bigTables}+${r.segs}`.padEnd(15) +
    `${r.nodes} (${r.mathNodes})`.padEnd(16) +
    String(r.visible).padEnd(9) +
    r.pts.join(',').padEnd(11) +
    String(r.legendEntries)
  );
}

// Независимость от ширины окна: тот же .tex при другом окне.
const same = [];
for (const key of ['sd', 'tax']) {
  await page.setViewportSize({ width: 1280, height: 900 });
  const a = await page.evaluate(async (k) => { pickScene(k); await new Promise(r => setTimeout(r, 450)); return buildTex('Проба', ''); }, key);
  await page.setViewportSize({ width: 820, height: 620 });
  const b = await page.evaluate(async (k) => { pickScene(k); await new Promise(r => setTimeout(r, 450)); return buildTex('Проба', ''); }, key);
  same.push([key, a === b, a.length, b.length]);
}
console.log('\nОдинаков ли .tex при разной ширине окна:');
same.forEach(([k, eq, la, lb]) => console.log(`  ${k.padEnd(6)} ${eq ? 'да' : 'НЕТ'}  (${la} против ${lb} знаков)`));

await browser.close();
