/* Сторож «запись не меняет рисунок»: отпечаток всех путей холста по состояниям.

   Запись ставится пометкой на готовый узел, поэтому атрибут d каждого пути
   обязан остаться тем же знак в знак. Прибор снимает по каждому состоянию
   (44 старта и все рецепты) число путей и отпечаток их d в порядке узлов.

   node paths.mjs                      снять и записать OUT/paths.json
   WITH=старый.json node paths.mjs     снять и сравнить со снятым раньше; код 1, если что-то сдвинулось

   Порядок работы: снять на нетронутом коде, поставить записи, сравнить. */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { HERE, OUT_ROOT, openPage, openScene } from './lib.mjs';

const OUT = process.env.OUT || OUT_ROOT;
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const { page } = await openPage(browser, { w: 1440, h: 760, theme: 'light' });
const states = (await page.evaluate(() => Object.keys(SCENE_NAMES))).map(k => ({ id: k, key: k, code: '' }));
for (const f of ['recipes.json', 'recipes_nonlinear.json', 'recipes_window.json']) {
  const r = JSON.parse(fs.readFileSync(path.join(HERE, f), 'utf8'));
  Object.keys(r).filter(k => !k.startsWith('_')).forEach(k => Object.keys(r[k]).forEach(v => states.push({ id: k + '@' + v, key: k, code: r[k][v] })));
}
const only = process.env.KEYS ? new Set(process.env.KEYS.split(',')) : null;
const res = {};
let failed = 0;
for (const st of states) {
  if (only && !only.has(st.key)) continue;
  try {
    await openScene(page, st.key);
    if (st.code) { await page.evaluate((c) => { (new Function(c))(); redrawAll(); }, st.code); await page.waitForTimeout(650); }
    await page.evaluate(() => { redrawAll(); redrawAll(); });
    await page.waitForTimeout(120);
    const ds = await page.evaluate(() => [...document.querySelectorAll('#chart path')].filter(p => !p.closest('defs')).map(p => p.getAttribute('d') || ''));
    res[st.id] = { paths: ds.length, sha: crypto.createHash('sha1').update(ds.join('\n')).digest('hex').slice(0, 16) };
  } catch (e) {
    // состояние не построилось: это ошибка прибора или рецепта, а не «рисунок изменился»
    failed++;
    res[st.id] = { paths: -1, sha: 'ошибка: ' + String(e.message || e).split('\n')[0].slice(0, 120) };
    console.log('   ОШИБКА', st.id, res[st.id].sha);
  }
}
await browser.close();
const file = path.join(OUT, 'paths.json');
fs.writeFileSync(file, JSON.stringify(res, null, 1));
console.log('состояний', Object.keys(res).length, 'ошибок', failed, '→', file);
if (process.env.WITH) {
  const old = JSON.parse(fs.readFileSync(process.env.WITH, 'utf8'));
  const diff = Object.keys(res).filter(k => !old[k] || old[k].sha !== res[k].sha || old[k].paths !== res[k].paths);
  diff.slice(0, 40).forEach(k => console.log('   ИЗМЕНИЛСЯ РИСУНОК', k, old[k] ? old[k].paths + ' → ' + res[k].paths + ' путей' : 'нет в прежнем снимке'));
  console.log(diff.length ? 'изменилось состояний: ' + diff.length : 'пути те же во всех состояниях: ' + Object.keys(res).length);
  process.exit(diff.length || failed ? 1 : 0);
}
process.exit(failed ? 1 : 0);
