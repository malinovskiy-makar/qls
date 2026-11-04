/* Прогон прототипа по моделям и состояниям:
   бумажный прогон → снимок холста на листе → опись → сборка → .tex.

   node run.mjs                       все 44 модели в стартовом состоянии
   KEYS=taxes,mono node run.mjs       только названные
   SETUP=recipes.json KEYS=taxes@subsidy,sd@qp node run.mjs
                                      состояния по рецептам: «ключ@вариант»
   SETUP=recipes_nonlinear.json ALL=1 node run.mjs
                                      все варианты из файла рецептов
   SETUP=recipes_nonlinear.json ALL=1 KEYS=taxes,mono node run.mjs
                                      все варианты названных моделей
   Переменные: OUT (куда писать), VW, VH (окно), THEME (light | dark),
   CALC2_BASE_URL (сервер, по умолчанию http://127.0.0.1:8099).

   Пишет в OUT: <состояние>.tex, <состояние>.list.json (опись),
   <состояние>.paper.png (холст на листе), _summary.json (счётчики). */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { HERE, OUT_ROOT, openPage, openScene, statRow, sumStats } from './lib.mjs';

const OUT = process.env.OUT || path.join(OUT_ROOT, 'run');
const SETUP = process.env.SETUP ? path.resolve(HERE, process.env.SETUP) : '';
fs.mkdirSync(OUT, { recursive: true });
const recipes = SETUP ? JSON.parse(fs.readFileSync(SETUP, 'utf8')) : {};
const browser = await chromium.launch();
const { page, errors } = await openPage(browser, { w: +(process.env.VW || 1440), h: +(process.env.VH || 760), theme: process.env.THEME || 'light', scale: 2 });
let keys = process.env.KEYS ? process.env.KEYS.split(',') : null;
if (process.env.ALL && SETUP) {
  // ALL=1 — все варианты файла рецептов; вместе с KEYS — все варианты названных моделей
  const only = keys ? new Set(keys) : null;
  keys = Object.keys(recipes).filter(k => !k.startsWith('_') && (!only || only.has(k))).flatMap(k => Object.keys(recipes[k]).map(v => k + '@' + v));
}
if (!keys) keys = await page.evaluate(() => Object.keys(SCENE_NAMES));
const summary = {};
let failed = 0;
for (const key0 of keys) {
  const [key, variant] = key0.split('@');
  try {
    await openScene(page, key);
    if (variant) {
      const code = recipes[key] && recipes[key][variant];
      if (!code) throw new Error('нет рецепта ' + key0);
      await page.evaluate((c) => { (new Function(c))(); redrawAll(); }, code);
      await page.waitForTimeout(650);
    }
    await page.evaluate(() => { redrawAll(); redrawAll(); });      // экран в неподвижной точке
    await page.waitForTimeout(120);
    await page.evaluate(() => { window.__leave = TXP.enterPaper(); });
    await page.waitForTimeout(100);
    const shot = await page.locator('#chart').screenshot({ type: 'png' }).catch(() => null);
    if (shot) fs.writeFileSync(path.join(OUT, key0 + '.paper.png'), shot);
    const res = await page.evaluate(() => {
      const list = TXP.capture();
      const r = TXP.emit(list, { title: '' });
      return { tex: r.tex, stats: r.stats, warn: list.warn, size: [list.W, list.H], list: JSON.parse(JSON.stringify(list, (k, v) => (typeof v === 'function' ? undefined : v))) };
    });
    await page.evaluate(() => { window.__leave(); window.__leave = null; });
    fs.writeFileSync(path.join(OUT, key0 + '.tex'), res.tex);
    fs.writeFileSync(path.join(OUT, key0 + '.list.json'), JSON.stringify(res.list));
    summary[key0] = { stats: res.stats, warn: res.warn, size: res.size };
    console.log(key0.padEnd(18), statRow(res.stats), res.warn.length ? ' ⚠ ' + [...new Set(res.warn)].join('; ') : '');
  } catch (e) {
    failed++;
    console.log(key0.padEnd(18), 'ОШИБКА', String(e.message || e).split('\n')[0]);
    summary[key0] = { error: String(e.message || e) };
    await page.evaluate(() => { try { if (window.__leave) window.__leave(); } catch (e) {} window.__leave = null; }).catch(() => {});
  }
}
fs.writeFileSync(path.join(OUT, '_summary.json'), JSON.stringify(summary, null, 1));
const ok = Object.values(summary).filter(v => v.stats).map(v => v.stats);
console.log('ИТОГО'.padEnd(18), statRow(sumStats(ok)), ' состояний ' + ok.length + ', ошибок ' + failed);
if (errors.length) console.log('ошибки страницы:', [...new Set(errors)].slice(0, 8));
await browser.close();
process.exit(failed ? 1 : 0);
