// .tex состояния модели: старт или рецепт (tex/recipes). node claude/calc2_labor/tex_peek.mjs <ключ>[@рецепт] [файл]
import fs from 'node:fs';
import { chromium } from 'playwright';
import { BASE, prime, openScene, loadRecipes } from '../../calc2/tests/tex/lib.mjs';
const [id, out] = process.argv.slice(2);
const [key, rec] = id.split('@');
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 760 }, reducedMotion: 'reduce', locale: 'ru-RU' });
const page = await ctx.newPage();
await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function' && typeof buildTex === 'function');
await prime(page);
await openScene(page, key);
if (rec) { await page.evaluate((c) => { (new Function(c))(); redrawAll(); }, loadRecipes()[id]); await page.waitForTimeout(400); }
const r = await page.evaluate(() => ({ tex: buildTex('', ''), stats: buildTex._stats || {} }));
if (out) fs.writeFileSync(out, r.tex);
console.log(JSON.stringify(r.stats));
console.log(r.tex.split('\n').filter(l => /MRL|min|Безработица|MCL|Исход|M\$|\{\$M|E|Диапазон|fill|draw|node/.test(l)).join('\n').slice(0, 6000));
await browser.close();
