/* РЕЖИМ «ТОЧКИ И ПЛОЩАДИ» И ПРЯЧУЩИЙСЯ «ОТВЕТ» (часть 2 из 3, 13.10.2026;
   решение владельца 13.10, ADR 0148).

   Разделы (можно выбрать: --only А,Б):
     А  холст: ровно два инструмента «Курсор» и «Точки и площади»; щелчок в
        режиме ставит точку на кривую («на спросе»); Esc возвращает «Курсор», и
        щелчок больше точку не ставит; «+ Между точками» по трём вершинам и
        «Готово» → площадь 100 (налоги); «+ Под кривой», D, [0; 40] → 3 200;
        смена модели возвращает «Курсор»; ошибок страницы нет;
     Б  левая панель по режиму: в «Курсоре» в «Условии» нет разделов точек и
        площадей (и текста «Свои точки и площади»); в режиме «Условие» не видно,
        видна панель «Точки и площади» с разделами «Точки» и «Площади»; «Готово»
        и «← Условие» возвращают «Условие», поле формулы D после возврата живое
        (набор 100-2Q меняет кривую); площадь 100 стоит в «Ответе» в группе
        «Свои площади» и на холсте; «Сначала сам» прячет её число; 390 и
        760 px: панель режима открывается и закрывается, прокрутки вбок нет;
     В  «Ответ» прячется в полоску (появится в фазе 3).

   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/modes_probe.mjs [--only А]
   Код 0 — всё сошлось.                                                     */
import { chromium } from 'playwright';

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);

let bad = 0, total = 0;
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));

const browser = await chromium.launch();
async function openPage(w, h, opts) {
  const ctx = await browser.newContext(Object.assign({ viewport: { width: w, height: h }, reducedMotion: 'reduce', locale: 'ru-RU' }, opts || {}));
  await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 30000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  return { ctx, page, errors };
}
const settle = async (page) => {
  await page.waitForTimeout(400);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(120);
};
const openKey = async (page, key) => {
  await page.evaluate((k) => {
    if (typeof setSelfMode === 'function' && SELF.on) setSelfMode(false);
    resetSceneMemory(); pickScene(k); closePicker(); redrawAll();
  }, key);
  await settle(page);
};
// Щелчок в экранную точку модели (x; y) главной панели — настоящей мышью.
async function clickModel(page, x, y) {
  const p = await page.evaluate(([x, y]) => {
    const { mx, my } = mainScales();
    const r = document.getElementById('chart').getBoundingClientRect();
    return [r.left + mx(x), r.top + my(y)];
  }, [x, y]);
  await page.mouse.click(p[0], p[1]);
  await page.waitForTimeout(160);
}
const mode = (page) => page.evaluate(() => ({
  pts: !!CANVAS.pts, cm: canvasMode(), body: document.body.classList.contains('pts-on'),
  cursor: document.getElementById('tool-cursor').getAttribute('aria-pressed'),
  ptsBtn: document.getElementById('tool-pts').getAttribute('aria-pressed'),
}));

/* ── А: холст ──────────────────────────────────────────────────────── */
if (want('А')) {
  head('А. Два инструмента, точка, Esc, площади, смена модели');
  const { ctx, page, errors } = await openPage(1440, 900);
  await openKey(page, 'sd');
  const tools = await page.evaluate(() => [...document.querySelectorAll('#canvas-bar .cv-tool')]
    .filter(b => b.getClientRects().length && getComputedStyle(b).visibility !== 'hidden')
    .map(b => b.textContent.replace(/\s+/g, ' ').trim()));
  ok('в панели холста ровно два инструмента «Курсор» и «Точки и площади»', tools.join('|') === 'Курсор|Точки и площади', tools.join(' | '));
  await page.click('#tool-pts');
  await settle(page);
  const m1 = await mode(page);
  ok('режим включён: кнопка нажата, класс у страницы', m1.pts && m1.body && m1.ptsBtn === 'true' && m1.cursor === 'false', JSON.stringify(m1));
  const sig = await page.evaluate(() => {
    const card = getComputedStyle(document.querySelector('.cv-card'));
    const esc = document.getElementById('cv-esc');
    return { border: card.borderTopColor, shadow: card.boxShadow, accent: getComputedStyle(document.body).getPropertyValue('--accent').trim(),
      esc: esc && esc.getClientRects().length ? esc.textContent.trim() : '' };
  });
  ok('признаки режима: рамка карточки акцентом, подпись «Esc: выйти из режима»',
    sig.shadow !== 'none' && sig.esc === 'Esc: выйти из режима', JSON.stringify(sig));
  await clickModel(page, 30, 70);
  const m = await page.evaluate(() => {
    const done = (STATE.marks || []).filter(x => !x.pending);
    const row = document.querySelector('#mark-list .mark-row:not(.mark-draft) .mark-on');
    return { n: done.length, x: done[0] && done[0].x, y: done[0] && done[0].y, on: row ? row.textContent : '' };
  });
  ok('щелчок в (30; 70) на D: в списке точка (30; 70) «на спросе»',
    m.n === 1 && Math.abs(m.x - 30) < 0.05 && Math.abs(m.y - 70) < 0.05 && m.on === 'на спросе', JSON.stringify(m));
  const m2 = await mode(page);
  ok('после щелчка режим остаётся', m2.pts && m2.cm === 'pts', JSON.stringify(m2));
  await page.evaluate(() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); });
  await page.keyboard.press('Escape');
  await settle(page);
  const m3 = await mode(page);
  ok('Esc → «Курсор»', !m3.pts && !m3.body && m3.cursor === 'true' && m3.ptsBtn === 'false', JSON.stringify(m3));
  await clickModel(page, 60, 40);
  const n3 = await page.evaluate(() => (STATE.marks || []).length);
  ok('в «Курсоре» щелчок по графику точку не ставит', n3 === 1, 'точек ' + n3);

  // Налоги: «+ Между точками», три вершины, «Готово».
  await openKey(page, 'taxes');
  await page.click('#tool-pts');
  await settle(page);
  await page.click('#ac-poly');
  await settle(page);
  const armed = await page.evaluate(() => canvasMode());
  ok('«+ Между точками» взводит набор вершин', armed === 'vert', armed);
  for (const [x, y] of [[40, 60], [40, 40], [50, 50]]) await clickModel(page, x, y);
  const nv = await page.evaluate(() => (STATE.areaVerts || []).length);
  ok('три щелчка — три вершины', nv === 3, String(nv));
  await page.click('#cv-mode-stop');
  await settle(page);
  const a1 = await page.evaluate(() => ({ list: (STATE.areaCalcList || []).map(r => r.value), cm: canvasMode(), verts: (STATE.areaVerts || []).length }));
  ok('«Готово» → площадь 100; набор закрыт, режим остался', a1.list.length === 1 && Math.abs(a1.list[0] - 100) < 0.01 && a1.cm === 'pts' && !a1.verts, JSON.stringify(a1));
  // Замыкание щелчком по первой вершине.
  await page.click('#ac-poly');
  await settle(page);
  for (const [x, y] of [[40, 60], [40, 40], [50, 50], [40, 60]]) await clickModel(page, x, y);
  await settle(page);
  const a2 = await page.evaluate(() => ({ list: (STATE.areaCalcList || []).map(r => r.value), cm: canvasMode() }));
  ok('щелчок по первой вершине замыкает: вторая площадь 100', a2.list.length === 2 && Math.abs(a2.list[1] - 100) < 0.01 && a2.cm === 'pts', JSON.stringify(a2));
  // Esc посреди набора: набор отменён, режим на месте.
  await page.click('#ac-poly');
  await settle(page);
  await clickModel(page, 40, 60);
  await page.keyboard.press('Escape');
  await settle(page);
  const a3 = await page.evaluate(() => ({ cm: canvasMode(), verts: (STATE.areaVerts || []).length, n: (STATE.areaCalcList || []).length }));
  ok('Esc посреди набора: вершин нет, площадь не добавлена, режим остался', a3.cm === 'pts' && !a3.verts && a3.n === 2, JSON.stringify(a3));

  // Спрос и предложение: «+ Под кривой», D, [0; 40].
  await openKey(page, 'sd');
  await page.click('#tool-pts');
  await settle(page);
  await page.click('#ac-curve');
  await settle(page);
  await page.click('#ac-pick-btns .ac-cbtn[data-name="D"]');
  await page.evaluate(() => { STATE.acFrom = 0; STATE.acTo = 40; syncAreaRangeLabel(); syncAreaCalcButton(); });
  await page.click('#ac-calc');
  await settle(page);
  const a4 = await page.evaluate(() => (STATE.areaCalcList || []).map(r => r.value));
  ok('«+ Под кривой», D, [0; 40] → 3 200', a4.length === 1 && Math.abs(a4[0] - 3200) < 0.01, JSON.stringify(a4));
  // Смена модели возвращает «Курсор».
  await page.evaluate(() => { pickScene('mono'); closePicker(); });
  await settle(page);
  const m5 = await mode(page);
  ok('смена модели → «Курсор»', !m5.pts && !m5.body && m5.cursor === 'true', JSON.stringify(m5));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── Б: левая панель по режиму ─────────────────────────────────────── */
const vis = (sel) => `(function(){ var e=document.querySelector(${JSON.stringify(sel)}); return !!(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden'); })()`;
async function panels(page) {
  return page.evaluate(new Function('return {' +
    'cond:' + vis('#tools-panel') + ',' +
    'pts:' + vis('#pts-panel') + ',' +
    'title:(document.querySelector("#pts-panel .pts-title")||{}).textContent||"",' +
    'heads:[...document.querySelectorAll("#pts-panel .pts-sec-head")].filter(function(h){return h.getClientRects().length}).map(function(h){return h.textContent.trim()}),' +
    'hscroll:document.documentElement.scrollWidth - window.innerWidth' +
  '}'));
}
async function typeD(page, text) {
  const mf = page.locator('#curve-list .fc-card').first().locator('math-field').first();
  await mf.click();
  /* Поле достраивается лениво (А56): щелчок сразу после смены модели или
     показа колонки теряет первые символы и БЕЗ режима (замер 13.10, «0-2Q»).
     Пауза — до набора, проверка — после. */
  await page.waitForTimeout(400);
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type(text, { delay: 30 });
  await page.waitForTimeout(700);
  return page.evaluate(() => {
    const d = (STATE.curves || []).find(c => c.role === 'demand');
    return d ? String(d.expr || '').replace(/\s+/g, '') : '';
  });
}
if (want('Б')) {
  head('Б. Левая панель по режиму, «Свои площади» в «Ответе»');
  const { ctx, page, errors } = await openPage(1440, 900);
  await openKey(page, 'taxes');
  const c0 = await page.evaluate(() => {
    const tp = document.getElementById('tools-panel');
    return { view: !!tp.querySelector('#sec-view'), area: !!tp.querySelector('#sec-areascalc'),
      text: /Свои точки и площади/.test(tp.innerText || ''),
      inPts: !!document.querySelector('#pts-panel #sec-view') && !!document.querySelector('#pts-panel #sec-areascalc')
        && !!document.querySelector('#pts-panel #mark-list') && !!document.querySelector('#pts-panel #ac-mode') && !!document.querySelector('#pts-panel select#ac-pick'),
      once: document.querySelectorAll('#sec-view, #sec-areascalc, #mark-list, #ac-mode, #ac-pick').length };
  });
  ok('«Курсор»: в «Условии» нет #sec-view, #sec-areascalc и текста «Свои точки и площади»', !c0.view && !c0.area && !c0.text, JSON.stringify(c0));
  ok('разделы ПЕРЕЕХАЛИ в панель режима (те же id, по одному узлу)', c0.inPts && c0.once === 5, JSON.stringify(c0));
  const p0 = await panels(page);
  ok('«Курсор»: «Условие» видно, панели режима нет', p0.cond && !p0.pts, JSON.stringify(p0));
  await page.click('#tool-pts');
  await settle(page);
  const p1 = await panels(page);
  ok('режим: «Условие» не видно, видна панель «Точки и площади» с разделами «Точки» и «Площади»',
    !p1.cond && p1.pts && p1.title === 'Точки и площади' && p1.heads.join('|') === 'Точки|Площади', JSON.stringify(p1));
  // Треугольник потерь — площадь 100; в режиме холст перерисовывается (поле D под спрятанной колонкой).
  await page.click('#ac-poly');
  await settle(page);
  for (const [x, y] of [[40, 60], [40, 40], [50, 50]]) await clickModel(page, x, y);
  await page.click('#cv-mode-stop');
  await settle(page);
  await page.click('#pts-done');
  await settle(page);
  const p2 = await panels(page);
  const m2 = await mode(page);
  ok('«Готово» в панели → «Условие» и «Курсор»', p2.cond && !p2.pts && !m2.pts, JSON.stringify(p2));
  const own = await page.evaluate(() => {
    const g = [...document.querySelectorAll('#ans-hero .ans-group')].find(x => /Свои площади/.test((x.querySelector('.ans-ghead') || {}).textContent || ''));
    const rows = g ? [...g.querySelectorAll('.ans-cell')].map(c => {
      const k = c.cloneNode(true); k.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
      return { lab: k.querySelector('.ans-lab').textContent.trim(), val: k.querySelector('.ans-val').textContent.replace(/\s+/g, '') };
    }) : [];
    const last = [...document.querySelectorAll('#ans-hero .ans-group')].pop();
    const drawn = [...document.querySelectorAll('#chart g.areacalc path')].map(x => x.getAttribute('data-legend'));
    return { rows, last: last === g, drawn };
  });
  ok('площадь 100 в «Ответе», группа «Свои площади» последней', own.rows.length === 1 && own.rows[0].val === '100' && own.last, JSON.stringify(own));
  ok('и на холсте', own.drawn.length === 1, JSON.stringify(own.drawn));
  const expr = await typeD(page, '100-2Q');
  ok('после возврата поле D живое: набор 100-2Q меняет кривую', /^100-2\*?Q$/.test(expr), expr);
  // «← Условие» — тот же выход.
  await page.click('#tool-pts');
  await settle(page);
  await page.click('#pts-back');
  await settle(page);
  const p3 = await panels(page);
  ok('«← Условие» → «Условие»', p3.cond && !p3.pts, JSON.stringify(p3));
  const expr2 = await typeD(page, '100-Q');
  ok('и снова живое поле D (100-Q)', /^100-Q$/.test(expr2), expr2);
  await page.click('#btn-self');
  await settle(page);
  const self = await page.evaluate(() => {
    const c = document.querySelector('#ans-hero .ans-own-cell');
    return { hidden: !!(c && c.classList.contains('self-hidden')), field: !!(c && c.querySelector('.self-inp')) };
  });
  ok('«Сначала сам» прячет число своей площади', self.hidden && self.field, JSON.stringify(self));
  await page.click('#btn-self');
  await settle(page);
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
  for (const w of [390, 760]) {
    const P = await openPage(w, w < 760 ? 844 : 1024, w < 760 ? { isMobile: true, hasTouch: true } : {});
    await openKey(P.page, 'taxes');
    await P.page.click('#tool-pts');
    await settle(P.page);
    const a = await panels(P.page);
    await P.page.click('#pts-done');
    await settle(P.page);
    const b = await panels(P.page);
    const tabs = await P.page.evaluate(() => { const t = document.getElementById('ph-tabs'); return t ? getComputedStyle(t).display : ''; });
    ok(w + ' px: панель режима открывается и закрывается, прокрутки вбок нет',
      a.pts && !a.cond && a.hscroll <= 0 && !b.pts && b.cond && b.hscroll <= 0, JSON.stringify({ a, b, tabs }));
    ok(w + ' px: ошибок страницы нет', !P.errors.length, P.errors.slice(0, 3).join(' | '));
    await P.ctx.close();
  }
}

await browser.close();
console.log('\n' + (bad ? 'ЕСТЬ ПРОВАЛЫ: ' + bad + ' из ' + total : 'ВСЁ СОШЛОСЬ: ' + total + ' проверок'));
process.exit(bad ? 1 : 0);
