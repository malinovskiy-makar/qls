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

/* ── Б4: имена — буквы ── */
async function sectionB4() {
  head('Б4. Имена своих точек — буквы');
  let { ctx, page, errors } = await openModel('taxes');
  ok('панель режима видна', await enterPts(page));
  for (const [x, y] of [[40, 60], [40, 40], [50, 50], [20, 80]]) await clickModel(page, x, y);
  let m = await marks(page);
  ok('taxes: три точки — A, B, C', m.length === 4 && m[0].text === 'A' && m[1].text === 'B' && m[2].text === 'C', JSON.stringify(m.map(x => x.text)));
  ok('taxes: буква точки на спросе — не D, S, P, Q (' + (m[3] && m[3].text) + ')', !!m[3] && /^[A-Z]$/.test(m[3].text) && !/[DSPQ]/.test(m[3].text), JSON.stringify(m[3]));
  const cv = await canvasMark(page, m[0].id);
  ok('подпись на холсте — то же имя', cv.label === 'A', JSON.stringify(cv));
  ok('Б4 taxes: ошибок страницы нет', !errors.length, errors.join(' | '));
  await ctx.close();
  ({ ctx, page, errors } = await openModel('ineq'));
  ok('ineq: панель режима видна', await enterPts(page));
  await clickModel(page, 30, 10);
  m = await marks(page);
  const legend = await page.evaluate(() => [...document.querySelectorAll('#chart [data-legend]')].map(e => e.getAttribute('data-legend')));
  ok('ineq: первая точка — не A и не B (области A и B: ' + legend.join(', ') + ')', m.length === 1 && /^[A-Z]$/.test(m[0].text) && !/[AB]/.test(m[0].text), JSON.stringify(m));
  ok('Б4 ineq: ошибок страницы нет', !errors.length, errors.join(' | '));
  await ctx.close();
  // Старая фикстура: автосохранение кода старта сессии (фаза −1).
  const fx = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
  ({ ctx, page, errors } = await openModel('taxes', { 'calc2.v1.model.taxes': fx.done.autosave }));
  ok('фикстура: панель режима видна', await enterPts(page));
  m = await marks(page);
  ok('фикстура: «Точка 1», «Точка 2» на месте', m.length === 2 && m[0].text === 'Точка 1' && m[1].text === 'Точка 2', JSON.stringify(m.map(x => x.text)));
  await clickModel(page, 80, 70);
  m = await marks(page);
  ok('фикстура: новая точка — «A»', m.length === 3 && m[2].text === 'A', JSON.stringify(m.map(x => x.text)));
  ok('Б4 фикстура: ошибок страницы нет', !errors.length, errors.join(' | '));
  await ctx.close();
}

/* ── Б3: меню «⋯» точки ── */
const menuOpen = (page) => page.evaluate(() => { const m = document.querySelector('.pts-menu'); return !!(m && m.classList.contains('open') && m.getClientRects().length); });
/* Действия — настоящими щелчками мыши (Playwright): история пишет только события человека (isTrusted). */
async function openMenuOf(page, id) {
  await page.locator('#mark-list .mark-row[data-mark="' + id + '"] [aria-haspopup]').click();
  await settle(page, 400);
}
async function menuItem(page, text) {
  await page.locator('.pts-menu.open .pts-mi', { hasText: text }).first().click();
}
async function menuCheck(page, re) {
  await page.locator('.pts-menu.open label.pts-mi', { hasText: re }).locator('input').click();
}
async function sectionB3() {
  head('Б3. Меню «⋯» точки');
  const { ctx, page, errors } = await openModel('taxes');
  ok('панель режима видна', await enterPts(page));
  await clickModel(page, 40, 60);
  let m = await marks(page);
  const id = m[0] && m[0].id;
  ok('точка A поставлена', m.length === 1 && m[0].text === 'A', JSON.stringify(m));
  // Открыть и закрыть — не шаг.
  let u0 = await undoLen(page);
  await openMenuOf(page, id);
  const items = await page.evaluate(() => [...document.querySelectorAll('.pts-menu.open .pts-mi')].map(x => x.textContent.trim()));
  ok('меню открылось: Переименовать, Изменить координаты, Цвет, Пунктир к осям, Координаты на графике, Убрать',
    (await menuOpen(page)) && items.join('|') === 'Переименовать|Изменить координаты|Цвет|Пунктир к осям|Координаты на графике|Убрать', JSON.stringify(items));
  await page.keyboard.press('Escape');
  await settle(page);
  ok('Esc при открытом меню закрывает только меню: меню закрыто, режим остаётся', !(await menuOpen(page)) && !(await exitedMode(page)));
  ok('открыть и закрыть меню — не шаг истории', (await undoLen(page)) === u0, (await undoLen(page)) + ' против ' + u0);
  // Пунктир к осям: один шаг, «Отменить» возвращает.
  let c0 = await canvasMark(page, id);
  u0 = await undoLen(page);
  await openMenuOf(page, id);
  await menuCheck(page, /Пунктир/);
  await settle(page);
  let c1 = await canvasMark(page, id);
  ok('«Пунктир к осям» снят: пунктиров на холсте ' + c0.dash + ' → ' + c1.dash, c0.dash === 2 && c1.dash === 0, JSON.stringify({ c0, c1 }));
  ok('«Пунктир к осям» — ровно один шаг истории', (await undoLen(page)) === u0 + 1, (await undoLen(page)) + ' против ' + u0);
  // Пересборка списка при открытом меню: меню живо и работает.
  await page.evaluate(() => { renderMarkList(); redrawAll(); });
  await settle(page, 400);
  ok('меню пережило пересборку списка', await menuOpen(page));
  await menuCheck(page, /Координаты/);
  await settle(page);
  c1 = await canvasMark(page, id);
  ok('после пересборки пункт меню работает: «Координаты на графике» меняют холст (' + c0.coords + ' → ' + c1.coords + ')', c0.coords !== c1.coords, JSON.stringify({ c0, c1 }));
  ok('«Координаты на графике» — ещё один шаг', (await undoLen(page)) === u0 + 2, (await undoLen(page)) + ' против ' + u0);
  await page.keyboard.press('Escape'); await settle(page, 300);
  await undo(page);
  ok('одно «Отменить» вернуло координаты на холсте', (await canvasMark(page, id)).coords === c0.coords);
  await undo(page);
  ok('ещё одно — пунктир', (await canvasMark(page, id)).dash === 2);
  // Цвет: окно цвета из меню; Esc закрывает только окно цвета.
  await openMenuOf(page, id);
  await page.locator('.pts-menu.open .pts-mi-color .cpick-btn').click();
  await settle(page, 400);
  const cp = await page.evaluate(() => !!document.querySelector('.cpick-menu'));
  await page.keyboard.press('Escape');
  await settle(page, 500);
  const after = await page.evaluate(() => ({ cp: !!document.querySelector('.cpick-menu'), menu: !!document.querySelector('.pts-menu.open') }));
  ok('Esc при открытом окне цвета закрывает только его: меню и режим остаются', cp && !after.cp && after.menu && !(await exitedMode(page)), JSON.stringify(after));
  u0 = await undoLen(page);
  const col0 = (await canvasMark(page, id)).fill;
  await page.locator('.pts-menu.open .pts-mi-color .cpick-btn').click();
  await settle(page, 400);
  const k = await page.evaluate((c) => [...document.querySelectorAll('.cpick-menu .cpick-sw')].findIndex(x => normHex(x.style.background) !== normHex(c || '')), col0);
  await page.locator('.cpick-menu .cpick-sw').nth(k).click();
  await settle(page);
  const col1 = (await canvasMark(page, id)).fill;
  ok('«Цвет» перекрашивает точку на холсте (' + col0 + ' → ' + col1 + '), один шаг', col1 && col1 !== col0 && (await undoLen(page)) === u0 + 1, JSON.stringify({ col0, col1 }));
  await page.keyboard.press('Escape'); await settle(page, 300);
  await undo(page);
  ok('«Отменить» вернула цвет', (await canvasMark(page, id)).fill === col0);
  // Переименовать: правка на холсте, имя в строке, на холсте и в .tex.
  u0 = await undoLen(page);
  await openMenuOf(page, id);
  await menuItem(page, 'Переименовать');
  await settle(page, 400);
  const inp = await page.evaluate(() => !!document.getElementById('pt-rename'));
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type('Ж');
  await page.keyboard.press('Enter');
  await settle(page);
  const rn = await page.evaluate((id) => {
    const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.trim(); };
    const r = document.querySelector('#mark-list .mark-row[data-mark="' + id + '"]');
    return { row: tx(r && r.querySelector('.mark-name')), tex: /Ж/.test(buildTex('', '')) };
  }, String(id));
  const cvn = await canvasMark(page, id);
  ok('«Переименовать» — правка на холсте; новое имя в строке, на холсте и в .tex', inp && rn.row === 'Ж' && cvn.label === 'Ж' && rn.tex, JSON.stringify({ inp, rn, cvn }));
  ok('переименование — один шаг истории', (await undoLen(page)) === u0 + 1, (await undoLen(page)) + ' против ' + u0);
  await undo(page);
  ok('«Отменить» вернула имя A', (await marks(page))[0].text === 'A');
  // Изменить координаты (45; 55).
  await openMenuOf(page, id);
  await menuItem(page, 'Изменить координаты');
  await settle(page, 400);
  const eds = await page.evaluate((id) => [...document.querySelectorAll('#mark-list .mark-row[data-mark="' + id + '"] .mark-xy .edval')].length, String(id));
  ok('«Изменить координаты»: в строке поля координат', eds === 2, String(eds));
  for (const [i, v] of [[0, '45'], [1, '55']]) {
    u0 = await undoLen(page);
    await page.locator('#mark-list .mark-row[data-mark="' + id + '"] .mark-xy .edval').nth(i).click();
    await settle(page, 300);
    await page.keyboard.press('ControlOrMeta+a');
    await page.keyboard.type(v);
    await page.keyboard.press('Enter');
    await settle(page);
    ok('координата ' + (i ? 'P' : 'Q') + ' = ' + v + ' — один шаг', (await undoLen(page)) === u0 + 1, (await undoLen(page)) + ' против ' + u0);
  }
  m = await marks(page);
  ok('точка стоит в (45; 55)', near(m[0].x, 45) && near(m[0].y, 55), JSON.stringify(m[0]));
  await undo(page);
  m = await marks(page);
  ok('«Отменить» вернула P = 60', near(m[0].x, 45) && near(m[0].y, 60), JSON.stringify(m[0]));
  ok('режим «Точки и площади» всё время включён', !(await exitedMode(page)));
  ok('Б3: ошибок страницы нет', !errors.length, errors.join(' | '));
  await ctx.close();
}

/* ── Б2: раздел «Точки», строки ── */
async function sectionB2() {
  head('Б2. Раздел «Точки»: строки точек');
  const { ctx, page, errors } = await openModel('taxes');
  ok('панель режима видна', await enterPts(page));
  const hdr = await page.evaluate(() => {
    const row = document.querySelector('#sec-view .pts-sec-row');
    const add = document.querySelector('#sec-view .btn-mark-add');
    return { inRow: !!(row && add && row.contains(add)), notInHead: !!(add && !add.closest('h3')), text: add ? add.textContent.trim() : '',
      head: row ? row.querySelector('h3.pts-sec-head').textContent.trim() : '' };
  });
  ok('«+ По координатам» — в строке заголовка «Точки», рядом с h3', hdr.inRow && hdr.notInHead && hdr.text === '+ По координатам' && hdr.head === 'Точки', JSON.stringify(hdr));
  for (const [x, y] of [[40, 60], [40, 40], [50, 50], [20, 80]]) await clickModel(page, x, y);
  const r = await rows(page);
  const want = [
    ['A', '(40;\\ 60)', /точка/, [/Q_\{1\}/, /P_\{b\}/]],
    ['B', '(40;\\ 40)', /точка/, [/Q_\{1\}/, /P_\{s\}/]],
    ['C', '(50;\\ 50)', /пересечение/, [/^D\b|\bD\b/, /\bS\b/]],
  ];
  want.forEach(([n, xy, word, texs], i) => {
    const q = r[i] || {};
    ok('строка ' + n + ' ' + xy + ' «' + (q.on || '') + '»: имя, координаты и «на чём стоит» формулой, галочка и «⋯»',
      q.nameTex === n && q.xyTex === xy && word.test(q.on) && texs.every(t => t.test(q.onTex)) && q.pick && q.more, JSON.stringify(q));
  });
  const d = r[3] || {};
  ok('четвёртая точка — «(20; 80) на D», буква не D, S, P, Q', d.xyTex === '(20;\\ 80)' && /^на D$/.test(d.on.replace(/\s+/g, ' ')) && d.onTex === 'D' && /^[A-Z]$/.test(d.nameTex) && !/[DSPQ]/.test(d.nameTex), JSON.stringify(d));
  ok('в строке ничего больше нет: галочка и «⋯» — все органы строки', r.every(q => q.extra === 2), JSON.stringify(r.map(q => q.extra)));
  // Вид: имя 19 px, координаты 16 px, «на чём стоит» 12 / 500 --text3.
  const st = await page.evaluate(() => {
    const r0 = document.querySelector('#mark-list .mark-row:not(.mark-draft)');
    const cs = (sel) => { const e = r0.querySelector(sel); const c = e && getComputedStyle(e); return c ? [c.fontSize, c.fontWeight, c.color].join(' ') : ''; };
    return { name: cs('.mark-name'), xy: cs('.mark-xy'), on: cs('.mark-on'), text3: getComputedStyle(document.body).getPropertyValue('--text3').trim() };
  });
  ok('вид строки: имя 19 px, координаты 16 px, «на …» 12 / 500', /^19px/.test(st.name) && /^16px/.test(st.xy) && /^12px 500 /.test(st.on), JSON.stringify(st));
  // Галочка выбора — вид, не модель: щелчок не шаг истории.
  const u0 = await undoLen(page);
  await page.locator('#mark-list .mark-row .mark-pick input').first().click();
  await settle(page);
  ok('галочка выбора — не шаг истории и не STATE', (await undoLen(page)) === u0 && (await page.evaluate(() => JSON.stringify(STATE).indexOf('ptsSel') < 0 && CANVAS.ptsSel.length === 1)), String(await undoLen(page)));
  ok('Б2: ошибок страницы нет', !errors.length, errors.join(' | '));
  await ctx.close();
}

const SECTIONS = [['Б1', sectionB1], ['Б2', sectionB2], ['Б3', sectionB3], ['Б4', sectionB4]];
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
