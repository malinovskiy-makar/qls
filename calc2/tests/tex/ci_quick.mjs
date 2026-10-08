/* Быстрая проверка выгрузки .tex для CI (её зовёт calc2/tests/test_calc2_tex.py).

   44 старта моделей: файл строится, проверка текста без TeX проходит
   (lint.mjs: запрещённые команды выражением сервера, знаки, скобки,
   окружения), дефектов записи нет (кривая или область без записи, запись не
   сошлась с нарисованным), окружений axis столько же, сколько панелей на
   холсте. Пять моделей разных семей дают побайтно один файл при двух окнах
   (1440×760 светлая и 390×844 тёмная).

   node calc2/tests/tex/ci_quick.mjs          (CALC2_BASE_URL — сервер)
   OUT=папка — записать 44 файла (тест соберёт их pdflatex, где он есть).
   Коды: 0 — всё сошлось; 1 — провал; 3 — calc2 не загрузился; 4 — нет Playwright. */
import fs from 'node:fs';
import path from 'node:path';
import { BASE, prime, openScene, loadStates } from './lib.mjs';
import { lintTex } from './lint.mjs';

let chromium;
try { ({ chromium } = await import('playwright')); } catch (e) { console.log('Playwright недоступен: ' + e.message); process.exit(4); }

const OUT = process.env.OUT || '';
const KEYS = loadStates().filter(s => s.src === 'start').map(s => s.key);
const TWO = ['taxes', 'mono-d3', 'labor-bilat', 'ppfsum', 'm-tangent'];   // пять семей; две модели о двух панелях
const DEF = ['curvesNoRecPoly', 'curvesNoRecSampled', 'curvesMismatch', 'areasNoRecPoly', 'areasNoRecSampled', 'areasMismatch'];
const t0 = Date.now();
const browser = await chromium.launch();

async function open(w, h, theme) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((th) => { try { localStorage.setItem('theme', th); } catch (e) {} }, theme);
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  try {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
    await page.waitForFunction(() => typeof pickScene === 'function' && typeof buildTex === 'function', null, { timeout: 25000 });
  } catch (e) {
    console.log('calc2 не загрузился: ' + e.message.split('\n')[0]);
    await browser.close();
    process.exit(3);
  }
  await prime(page);
  return page;
}
const texOf = (page) => page.evaluate(() => ({
  tex: buildTex('', ''), stats: buildTex._stats || {},
  panels: (STATE.panels || []).length,
}));

const fails = [];
const wide = await open(1440, 760, 'light');
const files = {};
for (const k of KEYS) {
  await openScene(wide, k);
  const r = await texOf(wide);
  files[k] = r.tex;
  const why = [];
  const lint = lintTex(r.tex);
  if (!lint.ok) why.push('проверка текста: ' + lint.problems.slice(0, 3).join('; '));
  DEF.forEach(d => { if (r.stats[d]) why.push(d + ' ' + r.stats[d]); });
  const axes = (r.tex.match(/\\begin\{axis\}/g) || []).length;
  if (axes !== Math.max(1, r.panels)) why.push('окружений axis ' + axes + ', панелей ' + r.panels);
  if (why.length) fails.push(k + ': ' + why.join(' | '));
  if (OUT) { fs.mkdirSync(OUT, { recursive: true }); fs.writeFileSync(path.join(OUT, k + '.tex'), r.tex); }
}
const narrow = await open(390, 844, 'dark');
for (const k of TWO) {
  await openScene(narrow, k);
  const r = await texOf(narrow);
  if (r.tex !== files[k]) fails.push(k + ': файл при 390×844 (тёмная) не тот же, что при 1440×760 (светлая)');
}
await browser.close();
const s = ((Date.now() - t0) / 1000).toFixed(1);
fails.forEach(f => console.log('ПРОВАЛ ' + f));
console.log((fails.length ? 'ВЫГРУЗКА .tex: провалов ' + fails.length : 'ВЫГРУЗКА .tex ЦЕЛА') +
  ' | стартов ' + KEYS.length + ', двух окон ' + TWO.length + ', ' + s + ' с');
process.exit(fails.length ? 1 : 0);
