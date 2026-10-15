/* Быстрая проверка выгрузки .tex для CI (её зовёт calc2/tests/test_calc2_tex.py).

   44 старта моделей: файл строится, проверка текста без TeX проходит
   (lint.mjs: запрещённые команды выражением сервера, знаки, скобки,
   окружения), дефектов записи нет (кривая или область без записи, запись не
   сошлась с нарисованным), окружений axis столько же, сколько панелей на
   холсте. Пять моделей разных семей дают побайтно один файл при двух окнах
   (1440×760 светлая и 390×844 тёмная).

   Свои точки и площади (тихие панели, сессия 7, Г1): состояние taxes@pts-areas (шаг 3 цепочки В — точки A (30; 70),
   B (40; 40), C (60; 50) и площадь S₁ по ним): проверка текста, дефектов записи нет, в файле $A$, $B$, $C$ и
   многоугольник S₁ по вершинам (30; 70), (40; 40), (60; 50) с записью в легенде $S_{1}$.

   Сторож свежести превью экрана выбора (ADR 0141): у каждой модели из
   calc2/static/calc2/previews.json отпечаток описи старта (previews/inpage.js)
   совпадает с записанным в файле. Не совпал — старт модели поменялся, а
   превью нет: «превью устарело: <модель>, пересоберите командой …».

   node calc2/tests/tex/ci_quick.mjs          (CALC2_BASE_URL — сервер)
   OUT=папка — записать 44 файла (тест соберёт их pdflatex, где он есть).
   Коды: 0 — всё сошлось; 1 — провал; 3 — calc2 не загрузился; 4 — нет Playwright. */
import fs from 'node:fs';
import path from 'node:path';
import { BASE, prime, openScene, loadStates, loadRecipes } from './lib.mjs';
import { lintTex } from './lint.mjs';
import { tokenTable, addPreviewScript, PREVIEWS_JSON, REBUILD } from '../previews/lib.mjs';

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
await addPreviewScript(wide);
const PV = JSON.parse(fs.readFileSync(PREVIEWS_JSON, 'utf8'));
const TOK = tokenTable();
Object.keys(PV).filter(k => !KEYS.includes(k)).forEach(k => fails.push('превью для модели без старта: ' + k));
let pvChecked = 0;
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
  if (PV[k]) {
    const fp = await wide.evaluate((t) => window.__PV.fp(t), TOK);
    pvChecked++;
    if (fp !== PV[k].fp) fails.push('превью устарело: ' + k + ', пересоберите командой ' + REBUILD + ' (отпечаток старта ' + fp + ', в previews.json ' + PV[k].fp + ')');
  }
}
// Свои точки и площади (сессия 7, Г1).
{
  const code = loadRecipes()['taxes@pts-areas'];
  await openScene(wide, 'taxes');
  await wide.evaluate((c) => { (new Function(c))(); redrawAll(); }, code);
  await wide.waitForTimeout(300);
  const r = await texOf(wide);
  const why = [];
  const lint = lintTex(r.tex);
  if (!lint.ok) why.push('проверка текста: ' + lint.problems.slice(0, 3).join('; '));
  DEF.forEach(d => { if (r.stats[d]) why.push(d + ' ' + r.stats[d]); });
  ['{$A$}', '{$B$}', '{$C$}', '\\addlegendentry{$S_{1}$}'].forEach(t => { if (r.tex.indexOf(t) < 0) why.push('нет ' + t); });
  const poly = r.tex.split('\n').find(l => /^\\fill\[[^\]]*\] \(axis cs:/.test(l) && /% S1: многоугольник/.test(l)) || '';
  ['(axis cs:30,70)', '(axis cs:40,40)', '(axis cs:60,50)'].forEach(v => { if (poly.indexOf(v) < 0) why.push('у S₁ нет вершины ' + v); });
  if (why.length) fails.push('taxes@pts-areas: ' + why.join(' | '));
  if (OUT) fs.writeFileSync(path.join(OUT, 'taxes@pts-areas.tex'), r.tex);
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
  ' | стартов ' + KEYS.length + ', своих точек и площадей 1, двух окон ' + TWO.length + ', превью сверено ' + pvChecked + ', ' + s + ' с');
process.exit(fails.length ? 1 : 0);
