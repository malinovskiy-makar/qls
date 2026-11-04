/* Общая часть приборов прототипа: где репозиторий, где сервер, как открыть
   страницу калькулятора и подключить к ней прототип.

   Папка пакета лежит внутри репозитория (claude/mockups/calc2_tex_20261007/),
   поэтому корень находится подъёмом до manage.py, а playwright берётся из
   node_modules репозитория обычным разрешением имён Node. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = (() => {
  if (process.env.CALC2_REPO) return path.resolve(process.env.CALC2_REPO);
  let d = HERE;
  for (let i = 0; i < 8; i++) { if (fs.existsSync(path.join(d, 'manage.py'))) return d; d = path.dirname(d); }
  throw new Error('не найден корень репозитория (manage.py): запусти из папки пакета внутри репозитория или задай CALC2_REPO');
})();
export const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
export const PROTO = process.env.PROTO || path.join(HERE, 'texproto.js');
export const OUT_ROOT = process.env.OUT || path.join(ROOT, 'reports', 'calc2_tex', 'proto');

/* Страница калькулятора с загруженными шрифтами и подключённым прототипом.
   reducedMotion: 'reduce' — как в приборах редизайна (calc2/tests/redesign):
   анимаций нет. Старые приборы calc2 идут с обычными переходами. */
export async function openPage(browser, o) {
  const opt = o || {};
  const ctx = await browser.newContext({ viewport: { width: opt.w || 1440, height: opt.h || 760 }, reducedMotion: 'reduce', locale: 'ru-RU', deviceScaleFactor: opt.scale || 1 });
  await ctx.addInitScript((th) => { try { localStorage.setItem('theme', th); } catch (e) {} }, opt.theme || 'light');
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message || e).slice(0, 300)));
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 25000 });
  /* Шрифты — до первого прогона: поля холста считаются по измеренной ширине
     подписей, и кадр до загрузки шрифтов даёт поля на 3–5 px другие. */
  await page.evaluate(async () => { const all = []; document.fonts.forEach(f => all.push(f.load().catch(() => null))); await Promise.all(all); await document.fonts.ready; });
  await page.addScriptTag({ path: PROTO });
  await page.evaluate(() => {
    // набор значения в поле так, как его увидит обработчик страницы
    window.SETF = (id, v) => { const i = document.getElementById(id); if (!i) throw new Error('нет поля ' + id); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })); };
  });
  return { ctx, page, errors };
}

/* Открыть модель с её стартового состояния. «Сначала сам» снимается явно:
   режим переживает resetSceneMemory() и pickScene(). */
export async function openScene(page, key) {
  await page.evaluate((k) => {
    if (typeof setSelfMode === 'function' && typeof SELF === 'object' && SELF.on) setSelfMode(false);
    if (typeof resetSceneMemory === 'function') resetSceneMemory();
    pickScene(k);
  }, key);
  await page.waitForTimeout(450);
}

export const STAT_COLS = [
  ['панели', s => s.panels], ['осей', s => s.axisLines],
  ['форм', s => s.curvesFormula], ['числ', s => s.curvesNumeric + (s.numericExact ? '(' + s.numericExact + ')' : '')], ['лом+', s => s.curvesPolyRec],
  ['БЕЗ:лом', s => s.curvesNoRecPoly], ['БЕЗ:отсч', s => s.curvesNoRecSampled], ['НЕСОШ', s => s.curvesMismatch],
  ['обл:гран', s => s.areasBounds], ['обл:мн', s => s.areasPoly], ['обл:числ', s => s.areasNumeric],
  ['обл:БЕЗ', s => s.areasNoRecSampled], ['обл:НЕСОШ', s => s.areasMismatch], ['пар', s => s.pairs],
];
export const statRow = (s) => STAT_COLS.map(([n, f]) => (n + ' ' + f(s)).padEnd(n.length + 5)).join(' ');
export const sumStats = (rows) => { const t = {}; rows.forEach(s => Object.keys(s).forEach(k => { t[k] = (t[k] || 0) + s[k]; })); return t; };
