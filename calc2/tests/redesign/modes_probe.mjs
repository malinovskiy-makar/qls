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
     В  «Ответ» прячется в полоску (с 14.10 по умолчанию закрыт, ADR 0150): 1440 —
        пустая память → полоска, полоска открывает; стрелка → правая колонка 44 px,
        карточка холста шире не меньше чем на 300 px, SVG под новую ширину,
        перерисовок за переключение не больше 3, ошибок 0; после перезагрузки
        спрятан; «Показать ответ» возвращает; шаги истории и ссылка «Поделиться»
        побайтно те же после двух переключений; «Развернуть график» и обратно —
        запомненное состояние; «Сначала сам» при спрятанном открывает «Ответ»;
        1100 — кнопки «Спрятать» нет, #btn-answer выдвигает «Ответ» как раньше
        (и при запомненном «спрятан»); 390 — без изменений.

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
  /* С 14.10 подписи «Esc: выйти из режима» на экране нет (закрытый список README пакета calc2_panels_20261014,
     10.3; решение «никаких подсказок», Notion …81eb…): Esc работает, надписи о нём нет. */
  ok('признаки режима: рамка карточки акцентом, подписи «Esc: выйти из режима» нет',
    sig.shadow !== 'none' && sig.esc === '', JSON.stringify(sig));
  await clickModel(page, 30, 70);
  const m = await page.evaluate(() => {
    const done = (STATE.marks || []).filter(x => !x.pending);
    const row = document.querySelector('#mark-list .mark-row:not(.mark-draft) .mark-on');
    const c = row ? row.cloneNode(true) : null; if (c) c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
    return { n: done.length, x: done[0] && done[0].x, y: done[0] && done[0].y, on: c ? c.textContent.replace(/\s+/g, ' ').trim() : '' };
  });
  /* С сессии 7 «на чём стоит» — обозначением кривой, как на холсте («на D»), а не ролью словами («на спросе»):
     README пакета calc2_panels_20261014, раздел 9. */
  ok('щелчок в (30; 70) на D: в списке точка (30; 70) «на D»',
    m.n === 1 && Math.abs(m.x - 30) < 0.05 && Math.abs(m.y - 70) < 0.05 && m.on === 'на D', JSON.stringify(m));
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
  /* С сессии 7 «← Условие» нет (закрытый список README пакета calc2_panels_20261014, 10.5: выход один — «Готово»,
     Esc работает без надписи): тот же выход клавишей Esc, кнопки «← Условие» в шапке нет. */
  await page.click('#tool-pts');
  await settle(page);
  const noBack = await page.evaluate(() => !document.getElementById('pts-back') && ![...document.querySelectorAll('#pts-panel button')].some(b => /Условие/.test(b.textContent)));
  await page.evaluate(() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); });
  await page.keyboard.press('Escape');
  await settle(page);
  const p3 = await panels(page);
  ok('кнопки «← Условие» нет; Esc → «Условие»', noBack && p3.cond && !p3.pts, JSON.stringify(Object.assign({ noBack }, p3)));
  const expr2 = await typeD(page, '100-Q');
  ok('и снова живое поле D (100-Q)', /^100-Q$/.test(expr2), expr2);
  // В «Курсоре» группа собирается и с нуля: перезагрузка поднимает автосохранение модели.
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  const re = await page.evaluate(() => ({ pts: CANVAS.pts, list: (STATE.areaCalcList || []).length,
    rows: [...document.querySelectorAll('#ans-hero .ans-own .ans-cell')].length }));
  ok('после перезагрузки («Курсор») группа «Свои площади» собрана заново', !re.pts && re.list === 1 && re.rows === 1, JSON.stringify(re));
  await page.click('#btn-self');
  await settle(page);
  const self = await page.evaluate(() => {
    const c = document.querySelector('#ans-hero .ans-own-cell');
    return { hidden: !!(c && c.classList.contains('self-hidden')), field: !!(c && c.querySelector('.self-inp')) };
  });
  ok('«Сначала сам» прячет число своей площади', self.hidden && self.field, JSON.stringify(self));
  await page.click('#btn-self');
  await settle(page);
  /* Поле, спрятанное АТРИБУТОМ hidden, fieldActive считает мёртвым (82-input.js), и
     буквы формул сцен (КПВ, издержки — не STATE.curves, а живые поля) пропадали бы
     на первой же перерисовке в режиме: ползунок a и его значение. Классом — нет. */
  await openKey(page, 'ppf');
  await page.evaluate(() => {
    const inp = document.getElementById('inp-ppf');
    setFormulaFieldQuiet(inp, 'y = 100 - a*x');
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await settle(page);
  await page.evaluate(() => { if (STATE.params.a) { STATE.params.a.value = 2; updatePult(); redrawAll(); } });
  await settle(page);
  const a0 = await page.evaluate(() => STATE.params.a ? STATE.params.a.value : null);
  await page.click('#tool-pts');
  await settle(page);
  await clickModel(page, 10, 80);
  await settle(page);
  await page.click('#pts-done');
  await settle(page);
  const a1 = await page.evaluate(() => ({ a: STATE.params.a ? STATE.params.a.value : null,
    chip: !!document.querySelector('#tools-panel [data-param="a"], #tools-panel .param-chip') }));
  ok('КПВ с буквой a = 2: точка в режиме и возврат не теряют ползунок и значение a', a0 === 2 && a1.a === 2, JSON.stringify({ a0, a1 }));
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

/* ── В: «Ответ» прячется в полоску ─────────────────────────────────── */
// Кнопка не на экране (поломка) — щелчок кодом: провал скажет проверка, а не таймаут прибора.
async function clickAny(page, sel) {
  const shown = await page.evaluate((q) => { const e = document.querySelector(q); return !!(e && e.getClientRects().length); }, sel);
  if (shown) await page.click(sel); else await page.evaluate((q) => { const e = document.querySelector(q); if (e) e.click(); }, sel);
}
async function geo(page) {
  return page.evaluate(() => {
    const w = (sel) => { const e = document.querySelector(sel); return e ? Math.round(e.getBoundingClientRect().width * 10) / 10 : -1; };
    const shown = (sel) => { const e = document.querySelector(sel); return !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden'); };
    return { ans: w('#params-panel'), card: w('.cv-card'), wrap: w('#graph-wrap'), svg: w('#chart'),
      svgAttr: +(document.getElementById('chart').getAttribute('width') || 0),
      hidden: document.body.classList.contains('ans-hidden'), rail: shown('#ans-rail'), hide: shown('#ans-hide'),
      inner: shown('#params-panel > .side-inner') };
  });
}
async function countRedraws(page, fn) {
  await page.evaluate(() => {
    if (!window.__rdOrig) { window.__rdOrig = window.redrawAll; window.redrawAll = function () { window.__rdN = (window.__rdN || 0) + 1; return window.__rdOrig.apply(this, arguments); }; }
    window.__rdN = 0;
  });
  await fn();
  await page.waitForTimeout(500);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  return page.evaluate(() => window.__rdN);
}
const histInfo = (page) => page.evaluate(async () => {
  const h = histOf();
  return { undo: h.undo.length, redo: h.redo.length, link: await shareLinkOf() };
});
if (want('В')) {
  head('В. «Ответ» прячется в полоску');
  const { ctx, page, errors } = await openPage(1440, 900);
  await page.evaluate(() => { try { localStorage.removeItem('calc2.v1.answerHidden'); } catch (e) {} });
  await openKey(page, 'taxes');
  // Правка человека, чтобы в истории был шаг и ссылка несла состояние.
  await page.evaluate(() => { const r = document.querySelector('#sec-tax input[type=range]'); if (r) { r.value = 30; r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true })); } });
  await page.mouse.click(5, 5);
  await page.waitForTimeout(900);
  /* Решение владельца 14.10 (Notion …81de…, ADR 0150) пересмотрело «по умолчанию открыт»: на первом заходе
     «Ответ» ЗАКРЫТ, стрелка #ans-hide стоит на левом краю полоски; открывают стрелкой или полоской. */
  const gc = await geo(page);
  ok('по умолчанию (пустая память) «Ответ» закрыт: полоска 44, стрелка видна (ADR 0150)', gc.hidden && gc.hide && gc.rail && Math.abs(gc.ans - 44) <= 1, JSON.stringify(gc));
  await clickAny(page, '#ans-rail'); await page.waitForTimeout(900);
  const g0 = await geo(page);
  ok('полоска открывает «Ответ»: колонка > 300, стрелка видна, полоски нет', !g0.hidden && g0.hide && !g0.rail && g0.ans > 300, JSON.stringify(g0));
  const h0 = await histInfo(page);
  const n1 = await countRedraws(page, () => clickAny(page, '#ans-hide'));
  const g1 = await geo(page);
  ok('стрелка «›» → правая колонка 44 px (± 1)', Math.abs(g1.ans - 44) <= 1 && g1.rail && !g1.inner, JSON.stringify(g1));
  ok('карточка холста шире не меньше чем на 300 px', g1.card - g0.card >= 300, (g1.card - g0.card) + ' px');
  ok('SVG перерисован под новую ширину', Math.abs(g1.svg - g1.wrap) <= 2 && Math.abs(g1.svgAttr - g1.svg) <= 2 && g1.svg > g0.svg + 290, JSON.stringify({ was: g0.svg, now: g1.svg, wrap: g1.wrap, attr: g1.svgAttr }));
  ok('перерисовок за переключение не больше 3', n1 >= 1 && n1 <= 3, String(n1));
  const rlab = await page.evaluate(() => { const b = document.getElementById('ans-rail'); return { aria: b.getAttribute('aria-label'), text: b.textContent.replace(/\s+/g, '') }; });
  // Полоска — только вертикальное «Ответ», своей «‹» нет: её заменяет стрелка (ADR 0150, README пакета 4).
  ok('полоска — кнопка «Показать «Ответ»» с надписью «Ответ»', rlab.aria === 'Показать «Ответ»' && rlab.text === 'Ответ', JSON.stringify(rlab));
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 30000 });
  await page.waitForTimeout(1200);
  const g2 = await geo(page);
  ok('после перезагрузки «Ответ» по-прежнему спрятан', g2.hidden && Math.abs(g2.ans - 44) <= 1 && g2.rail, JSON.stringify(g2));
  const n3 = await countRedraws(page, () => clickAny(page, '#ans-rail'));
  /* Замер «до» — в той же раскладке, что «после»: пересечения (STATE.crosses,
     ключ вида, в истории не участвует) ищутся по сетке пикселей, и на холсте
     другой ширины их координаты другие в двенадцатом знаке. */
  await page.waitForTimeout(600);
  const h2a = await histInfo(page);
  const g3 = await geo(page);
  ok('«Показать ответ» → колонка вернулась', !g3.hidden && Math.abs(g3.ans - g0.ans) <= 1 && g3.inner && !g3.rail, JSON.stringify(g3));
  ok('перерисовок за обратное переключение не больше 3', n3 >= 1 && n3 <= 3, String(n3));
  await clickAny(page, '#ans-hide'); await page.waitForTimeout(300);
  await clickAny(page, '#ans-rail'); await page.waitForTimeout(900);
  const h2b = await histInfo(page);
  ok('шаги истории и ссылка «Поделиться» те же до и после двух переключений',
    h2a.undo === h2b.undo && h2a.redo === h2b.redo && h2a.link === h2b.link && h2a.link.length > 20,
    JSON.stringify({ before: [h2a.undo, h2a.redo, h2a.link.length], after: [h2b.undo, h2b.redo, h2b.link.length], same: h2a.link === h2b.link }));
  // Подпись истории (вход модели без ключей вида) — одна при открытом и спрятанном «Ответе».
  const sigOpen = await page.evaluate(() => histSig(collectModelState()));
  await clickAny(page, '#ans-hide'); await page.waitForTimeout(600);
  const sigHid = await page.evaluate(() => histSig(collectModelState()));
  await clickAny(page, '#ans-rail'); await page.waitForTimeout(600);
  ok('состояние модели (история, автосохранение, ссылка) не несёт «спрятан»: подпись одна в обоих видах',
    sigOpen === sigHid && h0.undo >= 1, 'шагов ' + h0.undo + ', подписи ' + (sigOpen === sigHid ? 'равны' : 'разные'));
  // «Развернуть график» и обратно — запомненное состояние.
  await clickAny(page, '#ans-hide'); await page.waitForTimeout(300);
  await page.click('#btn-focus'); await page.waitForTimeout(400);
  const g4 = await geo(page);
  await page.click('#btn-focus'); await page.waitForTimeout(500);
  const g5 = await geo(page);
  ok('«Развернуть график» прячет обе колонки, обратно — снова полоска 44', g4.ans <= 1 && Math.abs(g5.ans - 44) <= 1 && g5.rail, JSON.stringify({ focus: g4.ans, back: g5.ans }));
  await clickAny(page, '#ans-rail'); await page.waitForTimeout(300);
  await page.click('#btn-focus'); await page.waitForTimeout(400);
  await page.click('#btn-focus'); await page.waitForTimeout(500);
  const g6 = await geo(page);
  ok('открытый «Ответ» после «Развернуть» и обратно открыт', !g6.hidden && Math.abs(g6.ans - g0.ans) <= 1, JSON.stringify(g6));
  // «Сначала сам» при спрятанном «Ответе».
  await clickAny(page, '#ans-hide'); await page.waitForTimeout(300);
  await page.click('#btn-self'); await page.waitForTimeout(600);
  const g7 = await geo(page);
  const selfOn = await page.evaluate(() => SELF.on && !!document.querySelector('#ans-hero .self-inp'));
  ok('«Сначала сам» при спрятанном «Ответе» → «Ответ» открыт, поля на месте', !g7.hidden && g7.inner && selfOn, JSON.stringify({ g7, selfOn }));
  await page.click('#btn-self'); await page.waitForTimeout(300);
  ok('ошибок страницы нет (1440)', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();

  // 1100: выезжающий «Ответ», и при запомненном «спрятан» тоже.
  for (const stored of ['0', '1']) {
    const P = await openPage(1100, 800);
    await P.page.evaluate((v) => { try { localStorage.setItem('calc2.v1.answerHidden', v); } catch (e) {} }, stored);
    await P.page.reload({ waitUntil: 'load' });
    await P.page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 30000 });
    await openKey(P.page, 'taxes');
    const a = await geo(P.page);
    const btn = await P.page.evaluate(() => { const b = document.getElementById('btn-answer'); return !!(b && b.getClientRects().length); });
    await P.page.click('#btn-answer'); await P.page.waitForTimeout(450);
    const open = await P.page.evaluate(() => ({ cls: document.body.classList.contains('ans-open'),
      tr: getComputedStyle(document.getElementById('params-panel')).transform, vis: getComputedStyle(document.getElementById('params-panel')).visibility,
      inner: !!document.querySelector('#params-panel > .side-inner').getClientRects().length }));
    ok('1100 (запомнено ' + stored + '): «Спрятать» и полоски нет, #btn-answer выдвигает «Ответ»',
      !a.hide && !a.rail && btn && open.cls && open.vis === 'visible' && open.tr === 'none' && open.inner, JSON.stringify({ a, open }));
    ok('1100 (запомнено ' + stored + '): ошибок нет', !P.errors.length, P.errors.slice(0, 3).join(' | '));
    await P.ctx.close();
  }
  // 390: без изменений — вкладки, ни «Спрятать», ни полоски.
  const T = await openPage(390, 844, { isMobile: true, hasTouch: true });
  await T.page.evaluate(() => { try { localStorage.setItem('calc2.v1.answerHidden', '1'); } catch (e) {} });
  await T.page.reload({ waitUntil: 'load' });
  await T.page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 30000 });
  await openKey(T.page, 'taxes');
  await T.page.click('#ph-tabs .ph-tab[data-tab="ans"]'); await T.page.waitForTimeout(300);
  const t = await geo(T.page);
  const hs = await T.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok('390: вкладка «Ответ» открыта, «Спрятать» и полоски нет, прокрутки вбок нет', t.inner && !t.hide && !t.rail && hs <= 0, JSON.stringify({ t, hs }));
  ok('390: ошибок нет', !T.errors.length, T.errors.slice(0, 3).join(' | '));
  await T.ctx.close();
}

await browser.close();
console.log('\n' + (bad ? 'ЕСТЬ ПРОВАЛЫ: ' + bad + ' из ' + total : 'ВСЁ СОШЛОСЬ: ' + total + ' проверок'));
process.exit(bad ? 1 : 0);
