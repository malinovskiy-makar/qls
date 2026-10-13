/* РЕЖИМ «ТОЧКИ И ПЛОЩАДИ» И ПРЯЧУЩИЙСЯ «ОТВЕТ» (часть 2 из 3, 13.10.2026;
   решение владельца 13.10, ADR 0148).

   Разделы (можно выбрать: --only А,Б):
     А  холст: ровно два инструмента «Курсор» и «Точки и площади»; щелчок в
        режиме ставит точку на кривую («на спросе»); Esc возвращает «Курсор», и
        щелчок больше точку не ставит; «+ Между точками» по трём вершинам и
        «Готово» → площадь 100 (налоги); «+ Под кривой», D, [0; 40] → 3 200;
        смена модели возвращает «Курсор»; ошибок страницы нет;
     Б  левая панель по режиму (появится в фазе 2);
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

await browser.close();
console.log('\n' + (bad ? 'ЕСТЬ ПРОВАЛЫ: ' + bad + ' из ' + total : 'ВСЁ СОШЛОСЬ: ' + total + ' проверок'));
process.exit(bad ? 1 : 0);
