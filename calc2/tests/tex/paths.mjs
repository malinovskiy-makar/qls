/* Сторож «запись не меняет рисунок» (прибор tex_paths).

   Запись ставится пометкой на готовый узел, поэтому атрибут d каждого пути
   холста обязан остаться тем же знак в знак, а порядок узлов — тем же.
   Прибор снимает по каждому состоянию (44 старта и все рецепты набора) число
   путей и отпечаток их d в порядке узлов.

   node calc2/tests/tex/paths.mjs                       снять и записать OUT/paths.json
   WITH=calc2/tests/tex/paths_e165aff.json node …        снять и сравнить; код 1, если что-то сдвинулось
   KEYS=taxes,mono …                                     только эти модели

   Отпечаток, снятый на нетронутом коде (коммит e165aff), лежит в git:
   calc2/tests/tex/paths_e165aff.json. */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { OUT_ROOT, openPage, openScene, loadStates, loadRecipes } from './lib.mjs';

const OUT = process.env.OUT || path.join(OUT_ROOT, 'paths');
fs.mkdirSync(OUT, { recursive: true });
const recipes = loadRecipes();
const only = process.env.KEYS ? new Set(process.env.KEYS.split(',')) : null;
const states = loadStates().filter(s => (s.src === 'start' || s.src === 'recipe') && (!only || only.has(s.key)));
const browser = await chromium.launch();
let f = await openPage(browser, { w: 1440, h: 760, theme: 'light' });
const res = {};
let failed = 0;
for (const st of states) {
  try {
    await openScene(f.page, st.key);
    const code = st.src === 'recipe' ? recipes[st.recipe] : '';
    if (code) { await f.page.evaluate((c) => { (new Function(c))(); redrawAll(); }, code); await f.page.waitForTimeout(650); }
    await f.page.evaluate(() => { redrawAll(); redrawAll(); });
    await f.page.waitForTimeout(120);
    const ds = await f.page.evaluate(() => [...document.querySelectorAll('#chart path')].filter(p => !p.closest('defs')).map(p => p.getAttribute('d') || ''));
    res[st.id] = { paths: ds.length, sha: crypto.createHash('sha1').update(ds.join('\n')).digest('hex').slice(0, 16) };
  } catch (e) {
    // состояние не построилось: это ошибка прибора или рецепта, а не «рисунок изменился»
    failed++;
    res[st.id] = { paths: -1, sha: 'ошибка: ' + String(e.message || e).split('\n')[0].slice(0, 120) };
    console.log('   ОШИБКА', st.id, res[st.id].sha);
    await f.ctx.close().catch(() => {});
    f = await openPage(browser, { w: 1440, h: 760, theme: 'light' });
  }
}
await browser.close();
const file = path.join(OUT, 'paths.json');
fs.writeFileSync(file, JSON.stringify(res, null, 1) + '\n');
console.log('состояний', Object.keys(res).length, 'ошибок', failed, '→', file);
if (process.env.WITH) {
  const old = JSON.parse(fs.readFileSync(process.env.WITH, 'utf8'));
  const diff = Object.keys(res).filter(k => !old[k] || old[k].sha !== res[k].sha || old[k].paths !== res[k].paths);
  diff.slice(0, 40).forEach(k => console.log('   ИЗМЕНИЛСЯ РИСУНОК', k, old[k] ? old[k].paths + ' → ' + res[k].paths + ' путей' : 'нет в прежнем снимке'));
  console.log(diff.length ? 'изменилось состояний: ' + diff.length : 'пути те же во всех состояниях: ' + Object.keys(res).length);
  process.exit(diff.length || failed ? 1 : 0);
}
process.exit(failed ? 1 : 0);
