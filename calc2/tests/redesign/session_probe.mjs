/* ИСТОРИЯ, АВТОСОХРАНЕНИЕ, ССЫЛКА (фаза 3 редизайна calc2).

   Для каждой модели (44 ключа без синонимов tax и tax-adv — 42 модели):
     1. до трёх правок разными органами (паузы больше склейки), столько же
        отмен — старт, столько же повторов — конец;
     2. перезагрузка страницы (адрес ?m=) возвращает модель с правками;
     3. состояние → ссылка → чистый браузер: то же состояние, хранилище пусто,
        #s= уходит из адреса после первой правки.
   Один раз на весь прогон:
     4. склейка: две правки одного органа с паузой 300 мс — один шаг;
     5. битая ссылка — модель по умолчанию и тост;
     6. ?texState=1 жив после входа в модель;
     7. без localStorage страница работает и считает;
     8. с ЗАПОЛНЕННЫМ хранилищем программный pickScene даёт тот же старт, что и
        базовый снимок (приборы не зависят от того, что лежит в браузере).
   node calc2/tests/redesign/session_probe.mjs --base calc2/tests/redesign/baseline [--keys …]
   Код возврата 0 — всё сошлось.                                            */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import * as L from './lib.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BL = arg('base', path.join(HERE, 'baseline'));
const LAYER = arg('layer', 'old');
const JOBS = +arg('jobs', '3');
const layer = await import(path.join(HERE, 'layer_' + LAYER + '.mjs'));
L.configure({ layer, base: BASE, layerName: LAYER });
const ONLY = (arg('keys', '') || '').split(',').filter(Boolean);
const all = fs.readdirSync(BL).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5));
const keys = all.filter(k => !['tax', 'tax-adv'].includes(k)).filter(k => !ONLY.length || ONLY.includes(k));
const browser = await chromium.launch();
const fails = [];
const ok = (cond, msg) => { if (!cond) fails.push(msg); return cond; };

const SKIP = /^#(scene-back|dock-export|tools-toggle|params-toggle|btn-scene-reset|btn-zoom(in|out)|btn-wrench|ac-clear)$|hint-btn|swatch|fold-btn|crow-gear|btn-icon/;
function edits(rec) {
  return (rec.steps || []).filter(s => s.path.length === 1 && s.effect === 'model' && !SKIP.test(s.path[0])
    && /^(input:(range|number|checkbox)|math-field|select|exact|switch)$/.test(s.kind))
    .map(s => (rec.controls || []).find(c => c.key === s.path[0])).filter(Boolean).slice(0, 3);
}
/* Сравнимое состояние: STATE без окна, следов и кэшей; значения органов. */
async function sig(page) {
  return page.evaluate(() => {
    const s = window.__RD.stateDump();
    /* mathRes — итоги «Математики», их сцена пересчитывает на каждой
       перерисовке по ОКНУ (точки ограничения берутся по окну x). Окно в
       историю не входит (журнал, «Принято без вопроса», п. 7): после отмены
       оно остаётся раздвинутым, и производное от него сверять нечего. Окно
       «Математики» (mathXmin…mathYmax) — то же окно, только своими полями. */
    ['crosses', 'zoomLock', 'viewDirty', 'panelWin', 'tanTop', 'tanBot', 'mcFlat', 'sceneKey', 'mathRes', 'mathXmin', 'mathXmax', 'mathYmin', 'mathYmax'].forEach(k => delete s[k]);
    Object.keys(s).forEach(k => { if (/Sig$/.test(k)) delete s[k]; });
    // Границы ползунка сдвига — ±Pmax/2, то есть тоже от окна (88-params.js).
    const c = window.__RD.controls().filter(x => /^input|math-field|select|exact|edval|switch/.test(x.kind)).map(x => {
      const p = Object.assign({}, x.props);
      if (/^#params-curves>/.test(x.key) && x.kind === 'input:range') { delete p.min; delete p.max; }
      return x.key.replace(/graph-f-\d+/g, 'graph-f') + '=' + JSON.stringify(p);
    });
    return JSON.stringify([s, c.sort()]);
  });
}
function firstDiff(a, b) {
  const A = JSON.parse(a), B = JSON.parse(b);
  const k = Object.keys(Object.assign({}, A[0], B[0])).find(x => JSON.stringify(A[0][x]) !== JSON.stringify(B[0][x]));
  if (k) return 'STATE.' + k + ': ' + String(JSON.stringify(A[0][k])).slice(0, 80) + ' → ' + String(JSON.stringify(B[0][k])).slice(0, 80);
  const sb = new Set(B[1]), sa = new Set(A[1]);
  const gone = A[1].filter(x => !sb.has(x)), extra = B[1].filter(x => !sa.has(x));
  return 'органы: было ' + gone.slice(0, 3).join(' ; ').slice(0, 200) + ' · стало ' + extra.slice(0, 3).join(' ; ').slice(0, 200);
}
async function openUser(page, key) {
  await page.evaluate((k) => openModelByUser(k), key);
  await L.settle(page);
  await page.evaluate(() => redrawAll());
  await L.settle(page);
  await layer.expand(page);
  await L.settle(page);
}
const quiet = (page) => page.waitForTimeout(1300);   // больше склейки 900 мс и затишья 300 мс

const results = {};
const queue = keys.slice();
async function worker() {
  while (queue.length) {
    const key = queue.shift();
    const rec = JSON.parse(fs.readFileSync(path.join(BL, key + '.json'), 'utf8'));
    const r = { key, edits: 0, notes: [] };
    const f = await L.fresh(browser, 'light');
    try {
      await openUser(f.page, key);
      const s0 = await sig(f.page);
      const list = edits(rec);
      for (const c of list) {
        try { await L.act(f.page, c, key); await L.settle(f.page); await quiet(f.page); r.edits++; }
        catch (e) { r.notes.push('правка ' + c.key + ': ' + String(e.message).slice(0, 60)); await L.layerClose(f.page); }
      }
      await quiet(f.page);
      const s1 = await sig(f.page);
      ok(!r.edits || s1 !== s0, key + ': правки не изменили состояние');
      const can = await f.page.evaluate(() => historyCan());
      ok(!r.edits || can.undo, key + ': после правок «Отменить» недоступна');
      for (let i = 0; i < r.edits; i++) { await f.page.evaluate(() => historyUndo()); await L.settle(f.page); }
      const su = await sig(f.page);
      ok(su === s0, key + ': ' + r.edits + ' отмен не вернули старт — ' + (su !== s0 ? firstDiff(s0, su) : ''));
      ok(!(await f.page.evaluate(() => historyCan().undo)), key + ': после всех отмен «Отменить» ещё доступна');
      for (let i = 0; i < r.edits; i++) { await f.page.evaluate(() => historyRedo()); await L.settle(f.page); }
      const sr = await sig(f.page);
      ok(sr === s1, key + ': ' + r.edits + ' повторов не вернули конец — ' + (sr !== s1 ? firstDiff(s1, sr) : ''));
      // Перезагрузка: адрес ?m= и автосохранение.
      await quiet(f.page);
      const url = await f.page.evaluate(() => location.href);
      ok(/[?&]m=/.test(url), key + ': в адресе нет ?m=');
      await f.page.reload({ waitUntil: 'load' });
      await f.page.waitForFunction(() => typeof pickScene === 'function');
      await f.page.addScriptTag({ content: L.INPAGE });
      await f.page.evaluate((l) => { window.__RD_LAYER = l; }, LAYER);
      await f.page.evaluate(async () => { const a = []; document.fonts.forEach(x => a.push(x.load().catch(() => null))); await Promise.all(a); });
      await L.settle(f.page); await f.page.evaluate(() => redrawAll()); await L.settle(f.page); await layer.expand(f.page); await L.settle(f.page);
      const sl = await sig(f.page);
      ok(sl === s1, key + ': перезагрузка не вернула правки — ' + (sl !== s1 ? firstDiff(s1, sl) : ''));
      // Ссылка в чистом браузере.
      const link = await f.page.evaluate(() => shareLinkOf());
      r.linkLen = link.length;
      const g = await browser.newContext({ viewport: { width: 1324, height: 638 }, reducedMotion: 'reduce', locale: 'ru-RU' });
      const p = await g.newPage();
      const perr = []; p.on('pageerror', e => perr.push(String(e)));
      await p.goto(link, { waitUntil: 'load' });
      await p.waitForFunction(() => typeof pickScene === 'function');
      await p.addScriptTag({ content: L.INPAGE });
      await p.evaluate((l) => { window.__RD_LAYER = l; }, LAYER);
      await p.evaluate(async () => { const a = []; document.fonts.forEach(x => a.push(x.load().catch(() => null))); await Promise.all(a); });
      await p.waitForFunction((k) => STATE.sceneKey && (STATE.sceneKey === k || (k === 'taxes' && /^tax/.test(STATE.sceneKey))), key, { timeout: 8000 }).catch(() => {});
      await L.settle(p); await p.evaluate(() => redrawAll()); await L.settle(p); await layer.expand(p); await L.settle(p);
      const sk = await sig(p);
      ok(sk === s1, key + ': ссылка открыла не то — ' + (sk !== s1 ? firstDiff(s1, sk) : ''));
      const store = await p.evaluate(() => Object.keys(localStorage).filter(k => k.startsWith('calc2.')));
      ok(!store.length, key + ': ссылка записала в хранилище ' + store.join(', '));
      ok(/#s=/.test(await p.evaluate(() => location.hash)), key + ': #s= ушёл из адреса без правки');
      ok(!perr.length, key + ': ошибки страницы по ссылке: ' + perr.join(' | ').slice(0, 200));
      await g.close();
      ok(!f.errors.length, key + ': ошибки страницы: ' + f.errors.join(' | ').slice(0, 200));
    } catch (e) { fails.push(key + ': прибор: ' + String(e.stack || e).slice(0, 300)); }
    await f.ctx.close();
    results[key] = r;
    console.log(key + ': правок ' + r.edits + ', ссылка ' + r.linkLen + ' знаков' + (r.notes.length ? ' · ' + r.notes.join('; ') : ''));
  }
}
await Promise.all(Array.from({ length: Math.min(JOBS, keys.length) }, worker));

// 4. Склейка: две правки одного органа с паузой 300 мс — один шаг.
{
  const f = await L.fresh(browser, 'light');
  await openUser(f.page, 'taxes');
  const s0 = await sig(f.page);
  const h = (await f.page.evaluateHandle(() => document.getElementById('tax-slider'))).asElement();
  await h.focus(); await f.page.keyboard.press('ArrowRight'); await f.page.waitForTimeout(450);
  await f.page.keyboard.press('ArrowRight'); await f.page.waitForTimeout(450);
  await f.page.keyboard.press('ArrowRight'); await quiet(f.page);
  const n = await f.page.evaluate(() => _hist.taxes ? _hist.taxes.undo.length : -1);
  ok(n === 1, 'склейка: три нажатия одного ползунка с паузой 450 мс дали шагов ' + n + ' вместо 1');
  await f.page.evaluate(() => historyUndo()); await L.settle(f.page);
  ok((await sig(f.page)) === s0, 'склейка: одна отмена не вернула старт');
  // А с паузой больше 900 мс — два шага.
  await h.focus(); await f.page.keyboard.press('ArrowRight'); await quiet(f.page);
  await f.page.keyboard.press('ArrowRight'); await quiet(f.page);
  const n2 = await f.page.evaluate(() => _hist.taxes.undo.length);
  ok(n2 === 2, 'склейка: две правки с паузой 1,3 с дали шагов ' + n2 + ' вместо 2');
  // «Сбросить»: один шаг и «Вернуть».
  await f.page.evaluate(() => resetCurrentScene()); await L.settle(f.page);
  ok((await sig(f.page)) === s0, 'сброс: не стартовое состояние');
  const t = await f.page.evaluate(() => { const x = document.querySelector('#calc2-toast .toast-act'); return x ? x.textContent : null; });
  ok(t === 'Вернуть', 'сброс: в тосте нет «Вернуть»');
  await f.page.click('#calc2-toast .toast-act'); await L.settle(f.page);
  ok(await f.page.evaluate(() => STATE.tax) !== 20, 'сброс: «Вернуть» не вернул ставку');
  await f.ctx.close();
}
// 5. Битая ссылка.
{
  const g = await browser.newContext(); const p = await g.newPage();
  await p.goto(BASE + '/calc2/?m=ceil#s=1zXXXXbroken', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function');
  await p.waitForTimeout(1500);
  const r = await p.evaluate(() => [STATE.sceneKey, location.hash, (document.getElementById('calc2-toast') || {}).textContent || '']);
  ok(r[0] === 'ceil' && !r[1] && /Ссылка повреждена/.test(r[2]), 'битая ссылка: ' + JSON.stringify(r));
  await g.close();
}
// 6. ?texState=1 жив.
{
  const g = await browser.newContext(); const p = await g.newPage();
  await p.goto(BASE + '/calc2/?texState=1', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function');
  await p.evaluate(() => openModelByUser('sd')); await p.waitForTimeout(800);
  const r = await p.evaluate(() => [location.search, typeof texFromStateOn === 'function' ? texFromStateOn() : new URLSearchParams(location.search).get('texState')]);
  ok(/texState=1/.test(r[0]) && /m=sd/.test(r[0]), '?texState=1: ' + JSON.stringify(r));
  await g.close();
}
// 7. Без localStorage.
{
  const g = await browser.newContext();
  await g.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('запрещено'); } }); });
  const p = await g.newPage(); const err = []; p.on('pageerror', e => err.push(String(e)));
  await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function');
  await p.evaluate(() => openModelByUser('taxes')); await p.waitForTimeout(600);
  await p.evaluate(() => { setToolsOpen(true); setParamsOpen(true); });
  await p.focus('#tax-slider'); for (let i = 0; i < 10; i++) await p.keyboard.press('ArrowRight');
  await p.waitForTimeout(1300);
  const r = await p.evaluate(() => [STATE.tax, STATE.taxEq && STATE.taxEq.Q, historyCan().undo]);
  ok(r[0] === 30 && Math.abs(r[1] - 35) < 1e-9 && r[2] && !err.length, 'без localStorage: ' + JSON.stringify(r) + ' ' + err.join(' | ').slice(0, 200));
  await g.close();
}
// 8. Заполненное хранилище не меняет программный старт.
{
  const g = await browser.newContext({ viewport: { width: 1324, height: 638 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  const keys2 = all;
  await g.addInitScript((ks) => {
    try {
      ks.forEach(k => localStorage.setItem('calc2.v1.model.' + k, JSON.stringify({ t: 1, s: { v: 1, key: k, state: { tax: 77, consPx: 9, mathX0: 3 }, form: {}, counters: { curve: 0, mark: 0, area: 0 } } })));
      localStorage.setItem('calc2.v1.recent', JSON.stringify(ks.map(k => ({ k, t: 1 }))));
      localStorage.setItem('theme', 'light');
    } catch (e) {}
  }, keys2);
  const p = await g.newPage();
  await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function');
  await p.addScriptTag({ content: L.INPAGE });
  await p.evaluate(async () => { const a = []; document.fonts.forEach(x => a.push(x.load().catch(() => null))); await Promise.all(a); });
  let bad = 0;
  for (const k of keys2) {
    const rec = JSON.parse(fs.readFileSync(path.join(BL, k + '.json'), 'utf8'));
    await p.evaluate((x) => { resetSceneMemory(); pickScene(x); }, k);
    await L.settle(p); await p.evaluate(() => redrawAll()); await L.settle(p);
    const st = await p.evaluate(() => window.__RD.stateDump());
    const d = L.stateDiff(rec.start.state, st);
    const real = Object.keys(d).filter(x => !['crosses', 'sceneKey'].includes(x) && !/Sig$/.test(x));
    if (real.length) { bad++; fails.push('заполненное хранилище: ' + k + ' старт разошёлся: ' + real.slice(0, 5).join(', ')); }
  }
  console.log('заполненное хранилище: моделей с иным стартом ' + bad + ' из ' + keys2.length);
  await g.close();
}
await browser.close();
console.log('\nпроверок не прошло: ' + fails.length);
fails.forEach(x => console.log('  ✗ ' + x));
process.exit(fails.length ? 1 : 0);
