/* ТОЧКИ И ПЛОЩАДИ (тихие панели, сессия 7, 15.10.2026; README пакета calc2_panels_20261014, раздел 9;
   решения владельца: вершина площади — это точка …81e0…, площадь по точкам — правило П43 …81be…).

   Разделы (--only Б1,Б2,Б3,Б4,…):
     Б1  шапка панели режима: заголовок «Точки и площади» (h2.pts-title) в шапке, справа «Готово»; кнопки
         «← Условие» и строки-подсказки нет; «Готово» и Esc выходят из режима;
     Б2  «Налоги и субсидии», старт: щелчки в углы клина налога (40; 60), (40; 40) и в пересечение (50; 50) →
         строки «A (40; 60) точка Q₁ и P_b», «B (40; 40) точка Q₁ и P_s», «C (50; 50) пересечение D и S» (по
         TeX-исходникам), у каждой галочка и «⋯»; четвёртая точка — щелчок по спросу при Q = 20 → «(20; 80) на D»;
         «+ По координатам» — в строке заголовка раздела «Точки»;
     Б3  меню «⋯» точки: «Переименовать» → имя в строке, на холсте и в .tex; «Изменить координаты» (45; 55) → точка
         там; «Цвет» перекрашивает точку на холсте; «Пунктир к осям» и «Координаты на графике» меняют холст; каждое
         изменение — один шаг истории, одно «Отменить» его возвращает; открыть и закрыть меню — не шаг; открытое
         меню переживает пересборку списка и работает; Esc при открытом меню (и при открытом окне цвета) закрывает
         только меню, режим остаётся;
     Б4  имена — буквы: первая свободная A … Z (не занятая своей точкой и обозначением на холсте модели: буква
         кривой, ключевой точки, области, оси); в «Неравенстве доходов» первая точка — не A и не B; буква точки
         на спросе в «Налогах» — не D, S, P, Q; старая фикстура (claude/panels_s7/fixtures/old_taxes_pts.json):
         «Точка 1», «Точка 2» на месте, новая точка — «A».
   Между действиями пауза не меньше 1 с (склейка правок одного органа за 900 мс — HIST_GLUE_MS).
   Первая проверка каждого раздела — панель режима видна (README 11).

   ENGINES=chromium,webkit (по умолчанию оба), WIDTHS=1440,1280 (по умолчанию оба).
   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/pts_probe.mjs [--only Б1,Б2]
   Код 0 — всё сошлось.                                                     */
import * as pw from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..', '..');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);
const ENGINES = (process.env.ENGINES || 'chromium,webkit').split(',').filter(Boolean);
const WIDTHS = (process.env.WIDTHS || '1440,1280').split(',').map(Number).filter(Boolean);
const FIXTURE = path.join(ROOT, 'claude', 'panels_s7', 'fixtures', 'old_taxes_pts.json');
const PAUSE = 1100;

let bad = 0, total = 0, eng = '', W0 = 1440;
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' [' + eng + ' ' + W0 + '] ' + label + (detail && !cond ? '  — ' + String(detail).slice(0, 400) : ''));
}
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));
const near = (a, b, t) => Math.abs(a - b) <= (t == null ? 0.05 : t);

let browser = null, engName = '', ctxCount = 0;
async function newCtx(opts) {
  // WebKit Playwright: не больше 63 контекстов на один запущенный браузер — перезапуск.
  if (ctxCount >= 40 && !browser.contexts().length) { await browser.close(); browser = await pw[engName].launch(); ctxCount = 0; }
  ctxCount++;
  return browser.newContext(opts);
}
/* Страница модели с чистой памятью; «Ответ» открыт (ключ памяти до загрузки). init — что положить в память. */
async function openModel(key, init) {
  const ctx = await newCtx({ viewport: { width: W0, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((o) => {
    try {
      if (sessionStorage.getItem('__probeInit')) return;
      sessionStorage.setItem('__probeInit', '1');
      localStorage.clear(); localStorage.setItem('theme', 'dark'); localStorage.setItem('calc2.v1.answerHidden', '0');
      if (o) Object.entries(o).forEach(([k, v]) => localStorage.setItem(k, v));
    } catch (e) {}
  }, init || null);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'load', timeout: 40000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined' && STATE.sceneKey, null, { timeout: 40000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  await page.waitForTimeout(700);
  return { ctx, page, errors };
}
const settle = (page, ms) => page.waitForTimeout(ms == null ? PAUSE : ms);
const panelShown = (page) => page.evaluate(() => { const e = document.getElementById('pts-panel'); return !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden'); });
async function enterPts(page) {
  await page.click('#tool-pts');
  await settle(page, 500);
  return panelShown(page);
}
/* Пиксель точки модели (x; y) в окне страницы. */
const pxOf = (page, x, y) => page.evaluate(([x, y]) => {
  const { mx, my } = mainScales(null); const r = document.getElementById('chart').getBoundingClientRect();
  return [r.left + mx(x), r.top + my(y)];
}, [x, y]);
async function clickModel(page, x, y) {
  const [cx, cy] = await pxOf(page, x, y);
  await page.mouse.click(cx, cy);
  await settle(page);
}
const undoLen = (page) => page.evaluate(() => histOf().undo.length);
async function undo(page) {
  await page.evaluate(() => { const b = document.getElementById('btn-undo'); if (b) b.click(); else historyUndo(); });
  await settle(page);
}
const texOf = (sel) => `[...(${sel}).querySelectorAll('annotation')].map(a => a.textContent).join(' ')`;
/* Строки списка точек: имя (TeX), координаты (TeX), «на чём стоит» (текст и TeX), галочка, «⋯». */
const rows = (page) => page.evaluate(() => {
  const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ' ').trim(); };
  const tex = (e) => e ? [...e.querySelectorAll('annotation')].map(a => a.textContent).join(' ') : '';
  return [...document.querySelectorAll('#mark-list .mark-row:not(.mark-draft)')].filter(r => r.getClientRects().length).map(r => ({
    id: r.dataset.mark,
    name: tx(r.querySelector('.mark-name')), nameTex: tex(r.querySelector('.mark-name')),
    xy: tx(r.querySelector('.mark-xy')), xyTex: tex(r.querySelector('.mark-xy')),
    on: tx(r.querySelector('.mark-on')), onTex: tex(r.querySelector('.mark-on')),
    pick: !!r.querySelector('input[type=checkbox]'), more: !!r.querySelector('[aria-haspopup]'),
    extra: [...r.querySelectorAll('button, input, .edval')].filter(e => e.getClientRects().length).length,
  }));
});
const marks = (page) => page.evaluate(() => (STATE.marks || []).filter(m => !m.pending).map(m => ({ id: m.id, text: m.text, x: m.x, y: m.y, color: m.color, showDash: m.showDash, showCoords: m.showCoords })));
/* Холст: подпись точки (первая строка) и её цвет, пунктиры, вторая строка координат. */
const canvasMark = (page, id) => page.evaluate((id) => {
  const t = document.querySelector('#chart g.marks text[data-mark-id="' + id + '"]');
  const g = t ? t.parentNode : null;
  const circ = [...document.querySelectorAll('#chart g.marks circle')].find(c => c.getAttribute('data-mark-id') === String(id));
  return { label: t ? t.textContent : null, fill: circ ? circ.getAttribute('fill') : null,
    dash: [...document.querySelectorAll('#chart g.marks line[data-mark-id="' + id + '"]')].length,
    coords: [...document.querySelectorAll('#chart g.marks text[data-mark-coords="' + id + '"]')].map(x => x.textContent).join(' ') };
}, String(id));
const exitedMode = (page) => page.evaluate(() => !CANVAS.pts && !document.body.classList.contains('pts-on'));

/* ── Б1 ── */
async function sectionB1() {
  head('Б1. Шапка панели режима');
  const { ctx, page, errors } = await openModel('taxes');
  ok('панель режима видна после входа', await enterPts(page));
  const h = await page.evaluate(() => {
    const head = document.querySelector('#pts-panel .pts-head');
    const title = head && head.querySelector('h2.pts-title');
    const cs = title ? getComputedStyle(title) : null;
    return { title: title ? title.textContent.trim() : '', fs: cs ? cs.fontSize : '', fw: cs ? cs.fontWeight : '',
      done: !!(head && head.querySelector('#pts-done')), back: !!document.getElementById('pts-back'),
      backText: [...document.querySelectorAll('#pts-panel button')].filter(b => b.getClientRects().length).some(b => /Условие/.test(b.textContent)),
      hint: [...document.querySelectorAll('#pts-panel .pts-hint')].length,
      titles: document.querySelectorAll('#pts-panel h2').length,
      order: head ? [...head.children].map(c => c.tagName + (c.id ? '#' + c.id : '')).join(',') : '' };
  });
  ok('в шапке слева «Точки и площади» 18 / 600, справа «Готово»', h.title === 'Точки и площади' && h.fs === '18px' && +h.fw === 600 && h.done && /^H2,BUTTON#pts-done$/.test(h.order), JSON.stringify(h));
  ok('«← Условие» нет, строки-подсказки нет, заголовок колонки один', !h.back && !h.backText && !h.hint && h.titles === 1, JSON.stringify(h));
  await page.click('#pts-done');
  await settle(page, 500);
  ok('«Готово» выходит из режима', await exitedMode(page));
  await enterPts(page);
  await page.evaluate(() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); });
  await page.keyboard.press('Escape');
  await settle(page, 500);
  ok('Esc выходит из режима', await exitedMode(page));
  ok('Б1: ошибок страницы нет', !errors.length, errors.join(' | '));
  await ctx.close();
}

const SECTIONS = [['Б1', sectionB1]];
for (const name of ENGINES) {
  eng = name; engName = name; ctxCount = 0;
  try { browser = await pw[name].launch(); } catch (e) {
    console.log('\n!!! ' + name + ': движок не запустился — НЕ ПРОВЕРЕНО (' + String(e).slice(0, 120) + ')');
    continue;
  }
  for (const w of WIDTHS) {
    W0 = w;
    for (const [s, fn] of SECTIONS) if (want(s)) await fn();
  }
  await browser.close();
}
console.log('\nИТОГ pts_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
