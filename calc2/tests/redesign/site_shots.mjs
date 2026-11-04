/* СНИМКИ САЙТА В СОСТОЯНИЯХ ЭТАЛОНОВ МАКЕТА и контактные листы «макет | сайт».

   Эталоны лежат в claude/mockups/calc2_redesign_20261004/reference/ (список и
   рецепты — reference/INDEX.md). Для каждого эталона здесь есть рецепт: размер
   окна, тема, модель и что сделать на странице, чтобы прийти в то же
   состояние. Рецепты, которым нужен новый экран (окна «Поделиться», «Сначала
   сам», телефон), появляются вместе с ним; пока рецепта нет, строка листа
   говорит «рецепта нет» — это видно глазами, а не теряется.

   Запуск (сервер calc2 на CALC2_BASE_URL):
     node calc2/tests/redesign/site_shots.mjs --set models,models_dark,models_1280 \
       --out reports/calc2_redesign/sheets/phase0 [--only sd,taxes]
   В --out появятся site/<набор>/<файл>.png и sheet_<набор>.png (склейка).    */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { RECIPES } from './site_recipes.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REF = path.resolve(HERE, '../../../claude/mockups/calc2_redesign_20261004/reference');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const SETS = arg('set', 'models').split(',');
const OUT = path.resolve(arg('out', 'reports/calc2_redesign/sheets/now'));
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);

const browser = await chromium.launch();
fs.mkdirSync(OUT, { recursive: true });

async function shoot(r, file) {
  const ctx = await browser.newContext({ viewport: { width: r.w, height: r.h }, deviceScaleFactor: r.dpr || 1,
    reducedMotion: 'reduce', locale: 'ru-RU', isMobile: !!r.mobile, hasTouch: !!r.mobile });
  await ctx.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) {} }, r.theme || 'light');
  const page = await ctx.newPage();
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 25000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  if (r.key) await page.evaluate((k) => pickScene(k), r.key);
  await page.waitForTimeout(700);
  if (r.run) await r.run(page);
  await page.waitForTimeout(500);
  await page.screenshot({ path: file });
  await ctx.close();
}

for (const set of SETS) {
  const list = (RECIPES[set] || []).filter(r => !ONLY.length || ONLY.some(o => r.file.includes(o)));
  const dir = path.join(OUT, 'site', set);
  fs.mkdirSync(dir, { recursive: true });
  const rows = [];
  for (const r of list) {
    const ref = path.join(REF, set, r.file);
    const site = path.join(dir, r.file);
    let note = r.note || '';
    if (r.pending) note = 'рецепта нет: ' + r.pending;
    else {
      try { await shoot(r, site); } catch (e) { note = 'ошибка: ' + String(e.message || e).slice(0, 160); }
    }
    rows.push({ name: set + '/' + r.file, ref: fs.existsSync(ref) ? ref : null, site: fs.existsSync(site) ? site : null, note });
    console.log(set + '/' + r.file + (note ? ' · ' + note : ''));
  }
  // Склейка: каждая пара строкой, слева макет, справа сайт, подпись над парой.
  const html = '<!doctype html><meta charset="utf-8"><style>body{margin:0;font:14px sans-serif;background:#fff}'
    + '.r{display:flex;gap:12px;padding:10px;border-bottom:1px solid #ccc}.c{flex:1}.c img{width:100%;border:1px solid #999}'
    + 'h3{margin:0 0 6px;font-size:14px}.n{color:#a00}</style>'
    + rows.map(x => `<div class="r"><div class="c"><h3>макет · ${x.name}</h3>${x.ref ? `<img src="file://${x.ref}">` : '<p class="n">эталона нет</p>'}</div>`
      + `<div class="c"><h3>сайт · ${x.name} <span class="n">${x.note}</span></h3>${x.site ? `<img src="file://${x.site}">` : '<p class="n">снимка нет</p>'}</div></div>`).join('');
  const hp = path.resolve(OUT, 'sheet_' + set + '.html');
  fs.writeFileSync(hp, html);
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('file://' + hp);
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.resolve(OUT, 'sheet_' + set + '.png'), fullPage: true });
  await ctx.close();
}
await browser.close();
