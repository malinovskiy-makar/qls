/* РЫНОК ТРУДА (сессия «рынок труда одной сессией», 15.10.2026, ADR 0156; решения владельца: профсоюз максимизирует
   фонд оплаты …81ac…, безработица при ставке профсоюза в «Ответе» …813c…, «Разбор» с единичной эластичностью
   …81e9…, новый стартовый пример …81df…, МРОТ в «Двусторонней монополии» …8168…).

   Разделы (--only А,Б,В):
     А  «Профсоюз», монополист, кривые задаются явно:
        новый пример D = 100 − L, S = 10 + 0,5L — точка «MRL = 0» на оси L в 50 цветом MRL, подпись «MRL = 0»
        цветом MRL; точки «MRL = S» нет (кружков цвета MRL вне оси нет); «Ответ» — восемь строк по порядку:
        Lп 50, Wп 50, фонд 2 500, желающих 80, безработица 30, Lk 60, Wk 40, DWL 75; «Сначала сам» прячет фонд,
        желающих и безработицу; «Разбор» содержит «единичной эластичности»;
        угол — «Угол» D = 100 − L, S = 2L (33,33 / 66,67, фонд 2 222,22) и «Старый пример» D = 100 − L, S = L
        (50 / 50, фонд 2 500): подсказка про конкурентную ставку, строк «Желающих работать», «Безработица», DWL нет.
     Б  старт каждой модели труда (новый пример D = 100 − L, S = 10 + 0,5L, решение …81df…): «Ответ» из таблицы задания —
        конкуренция с МРОТ 45 (занятость 55, было 60; безработица 15; на оси L «55 спрос» и «70 предл»), монопсония с
        МРОТ 45 (M (55; 45), «МРОТ увеличил занятость (парадокс монопсонии).»), профсоюз (как в А), двусторонняя без
        МРОТ (32,5 … 50, «Безработица на границах» 0 и 30; галочка МРОТ видна и снята, линии МРОТ нет, полоса торга
        от 32,5 до 50).
     В  МРОТ в «Двусторонней монополии» (решение …8168…), новый пример со старта модели, цепочка шагов:
        1 старт — галочка видна и снята, линии МРОТ нет, «Ответ» основного раздела;
        2 галочка → МРОТ 45: «С МРОТ» (45 … 50, занятость 55 и 50, безработица 15 и 30), холст — M (55; 45), «MCLэфф»,
          «Безработица = 15», полоса 45 … 50; один шаг истории;
        3 МРОТ 36 (щелчок по значению, набор, Enter) → 36 … 50, 52 и 50, 0 и 30, полосы безработицы нет;
        4 30 → «не связывает», основной раздел; 5 50 → исход один 50, занятость 50, безработица 30;
        6 60 → исход один 60, 40, 60, надпись «Исход один: зарплата = МРОТ», полосы торга нет;
        7 линия МРОТ мышью 45 → 60 → исход один по живому МРОТ (занятость 100 − W, безработица 3W − 120); один шаг;
        8 снять галочку → как шаг 1; одно «Отменить» → МРОТ снова включён;
        9 ссылка «Поделиться» и автосохранение с МРОТ 45 туда и обратно → те же числа;
        10 «Второй пример» D = 120 − 2L, S = 20 + L: МРОТ 55 → 55 … 60, 32,5 и 30, 2,5 и 10; МРОТ 70 → исход один 70, 25, 25;
        11 старые сохранения (claude/calc2_labor/fixtures/old_<ключ>.json, код bfb74cc3): ссылка и автосохранение тем же
           путём, что autosaveModel, открываются без ошибок, числа «Старого примера» (двусторонняя: галочка видна и
           включена, исход один 65, занятость 35, безработица 30).
   Первая проверка каждой страницы — «Ответ» открыт и виден (answerShown, README 11).
   Между действиями, которые пишут историю, пауза не меньше 1 с (склейка HIST_GLUE_MS = 900).

   ENGINES=chromium,webkit (по умолчанию оба), WIDTHS=1440,1280 (по умолчанию оба).
   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/labor_probe.mjs [--only А,Б,В]
   Код 0 — всё сошлось.                                                     */
import * as pw from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { answerShown } from '../answer_open.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..', '..');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);
const ENGINES = (process.env.ENGINES || 'chromium,webkit').split(',').filter(Boolean);
const WIDTHS = (process.env.WIDTHS || '1440,1280').split(',').map(Number).filter(Boolean);
const PAUSE = 1100;

const NEW = ['100 - L', '10 + 0.5*L'];       // новый пример (решение …81df…)
const OLD = ['100 - L', 'L'];                // «Старый пример»
const CORNER = ['100 - L', '2*L'];           // «Угол»
const SECOND = ['120 - 2*L', '20 + L'];      // «Второй пример»

let bad = 0, total = 0, eng = '', W0 = 1440;
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' [' + eng + ' ' + W0 + '] ' + label + (detail && !cond ? '  — ' + String(detail).slice(0, 400) : ''));
}
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));
const near = (a, b, t) => a != null && isFinite(a) && Math.abs(a - b) <= (t == null ? 0.01 : t);
/* Число из записи интерфейса: пробелы тысяч, запятая, минус U+2212. */
const num = (s) => { const m = /[−-]?[\d\s   ]*\d(?:[.,]\d+)?/.exec(String(s || '')); return m ? parseFloat(m[0].replace(/[\s   ]/g, '').replace(',', '.').replace('−', '-')) : NaN; };

let browser = null, engName = '', ctxCount = 0;
async function newCtx(opts) {
  // WebKit Playwright: не больше 63 контекстов на один запущенный браузер — перезапуск.
  if (ctxCount >= 40 && !browser.contexts().length) { await browser.close(); browser = await pw[engName].launch(); ctxCount = 0; }
  ctxCount++;
  return browser.newContext(opts);
}
/* Страница модели с чистой памятью; «Ответ» открыт (ключ памяти до загрузки). init — что положить в память;
   url — свой адрес (ссылка «Поделиться»). */
async function openModel(key, init, url) {
  const ctx = await newCtx({ viewport: { width: W0, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((o) => {
    try {
      if (sessionStorage.getItem('__probeInit')) return;
      sessionStorage.setItem('__probeInit', '1');
      localStorage.clear(); localStorage.setItem('theme', 'light'); localStorage.setItem('calc2.v1.answerHidden', '0');
      if (o) Object.entries(o).forEach(([k, v]) => localStorage.setItem(k, v));
    } catch (e) {}
  }, init || null);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(url || (BASE + '/calc2/?m=' + key), { waitUntil: 'load', timeout: 40000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined' && STATE.sceneKey, null, { timeout: 40000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  await page.waitForTimeout(800);
  return { ctx, page, errors };
}
const settle = (page, ms) => page.waitForTimeout(ms == null ? PAUSE : ms);
/* Кривые явно: D и S заново (тот же путь, что у calc2_math). */
async function setCurves(page, [d, s]) {
  await page.evaluate(([d, s]) => {
    STATE.curves = [];
    addCurve(d); setRole(STATE.curves[0], 'demand');
    addCurve(s); setRole(STATE.curves[1], 'supply');
    if (typeof renderCurveList === 'function') renderCurveList();
    redrawAll();
  }, [d, s]);
  await settle(page);
}
/* Табло «Рынок труда» и колонка «Ответ»: строки (подпись, значение, видна ли), подсказки, подзаголовки; главные
   числа «Ответа»; видимый текст колонки. */
const answer = (page) => page.evaluate(() => {
  const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[​]/g, '').replace(/\s+/g, ' ').trim(); };
  const vis = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const box = document.getElementById('info-labor');
  return {
    stats: box ? [...box.querySelectorAll('.stat')].map(s => ({ lab: tx(s.querySelector(':scope > span')), val: tx(s.querySelector(':scope > b')),
      hero: s.classList.contains('is-hero'), shown: vis(s) })) : [],
    hints: box ? [...box.querySelectorAll('.hint')].map(tx) : [],
    subsec: box ? [...box.querySelectorAll('.sb-subsec')].map(tx) : [],
    hero: [...document.querySelectorAll('#ans-hero .ans-cell')].filter(vis).map(c => ({ lab: tx(c.querySelector('.ans-lab')), val: tx(c.querySelector('.ans-val')) })),
    col: (document.querySelector('#params-panel > .side-inner') || {}).innerText || '',
  };
});
/* Строки табло по порядку против ожидания [[подпись-регэксп, число], …]; строка видна в «Ответе» (сама или главным
   числом). */
function checkRows(name, a, want) {
  const got = a.stats.map(s => s.lab + ' = ' + s.val).join(' | ');
  ok(name + ': строк ' + want.length, a.stats.length === want.length, got);
  // Ожидание — число (сверка числом) или строка (сверка записью без пробелов: «55 (было 60)», «32,5…50», «45 и 50»).
  const flat = (x) => String(x).replace(/[\s\u00a0\u202f\u2009]+/g, '');
  want.forEach(([re, v], i) => {
    const s = a.stats[i];
    const valOk = !!s && (typeof v === 'string' ? flat(s.val) === flat(v) : near(num(s.val), v, Math.max(0.011, Math.abs(v) * 0.0005)));
    ok(name + ': строка ' + (i + 1) + ' ' + re + ' = ' + v, !!s && re.test(s.lab) && valOk, s ? s.lab + ' = ' + s.val : 'нет строки');
    if (s) ok(name + ': строка ' + (i + 1) + ' видна в «Ответе»', s.shown || (s.hero && a.hero.some(h => typeof v === 'string' ? flat(h.val) === flat(v) : near(num(h.val), v, 0.011))), JSON.stringify(s));
  });
}
const canvasMRL = (page) => page.evaluate(() => {
  const { mx, my } = mainScales(null);
  const t = document.querySelector('#chart text.labor-mrl0');
  const oy = my(0);
  const cs = [...document.querySelectorAll('#chart circle')].filter(c => c.getAttribute('fill') === COL.MR);
  return {
    label: t ? t.textContent.trim() : null, labelColor: t ? t.getAttribute('fill') === COL.MR : false,
    onAxis: cs.filter(c => Math.abs(+c.getAttribute('cy') - oy) < 1).map(c => mx.invert(+c.getAttribute('cx'))),
    offAxis: cs.filter(c => Math.abs(+c.getAttribute('cy') - oy) >= 1).map(c => [mx.invert(+c.getAttribute('cx')), my.invert(+c.getAttribute('cy'))]),
  };
});
async function explainText(page) {
  await page.evaluate(() => { const b = document.getElementById('ex-bar'); if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); });
  await settle(page, 500);
  // Ответы вопросов «Разбора» свёрнуты: текст берём у разметки (без невидимой копии KaTeX), «Разбор» раскрыт.
  return page.evaluate(() => { const e = document.getElementById('explain'); if (!e || !e.getClientRects().length) return '';
    const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' '); });
}

/* Холст: подписи значений на осях (text.coord-num) текстом без невидимых знаков; точки (кружки) в координатах модели;
   полоса торга двусторонней монополии; линия МРОТ (подпись «… min» у оси W). */
const canvas = (page) => page.evaluate(() => {
  const { mx, my } = mainScales(null);
  const clean = (t) => t.replace(/[\u200b\s]+/g, '');
  const band = document.querySelector('#chart rect[data-legend="Диапазон возможных зарплат"]');
  return {
    coords: [...document.querySelectorAll('#chart text.coord-num')].map(t => clean(t.textContent)),
    texts: [...document.querySelectorAll('#chart text')].map(t => t.textContent.trim()),
    dots: [...document.querySelectorAll('#chart circle')].filter(c => +c.getAttribute('r') >= 4)
      .map(c => [mx.invert(+c.getAttribute('cx')), my.invert(+c.getAttribute('cy'))]),
    band: band ? [my.invert(+band.getAttribute('y') + +band.getAttribute('height')), my.invert(+band.getAttribute('y'))] : null,
  };
});
const dotAt = (c, x, y, t) => c.dots.some(([a, b]) => Math.abs(a - x) <= (t || 0.3) && Math.abs(b - y) <= (t || 0.3));
const chkState = (page) => page.evaluate(() => {
  const c = document.getElementById('chk-labmin'), lab = c && c.closest('label');
  const vis = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none');
  return { shown: vis(lab), checked: !!(c && c.checked), field: vis(document.getElementById('labmin-field')), on: STATE.laborMinOn, w: STATE.laborMinW };
});

/* ── Б ── */
const START = {
  labor: [[/^Lk.*занятость/, 60], [/^Wk.*зарплата/, 40], [/^Излишек рабочих/, 900], [/^Излишек фирм/, 1800],
    [/^МРОТ/, 45], [/^Занятость$/, '55 (было 60)'], [/^Безработица/, 15], [/^Излишек рабочих/, 1168.75],
    [/^Излишек фирм/, 1512.5], [/^DWL/, 18.75]],
  'labor-mono': [[/^Lм.*занятость/, 45], [/^Wм.*зарплата/, 32.5], [/^Lk.*конкуренция/, 60], [/^Wk.*конкуренция/, 40],
    [/^DWL/, 168.75], [/^МРОТ/, 45], [/^Занятость с МРОТ/, '55 (было 45)'], [/^Зарплата/, 45], [/^Безработица/, 15],
    [/^Излишек рабочих/, 1168.75], [/^Излишек фирм/, 1512.5], [/^DWL/, 18.75]],
  'labor-bilat': [[/^Нижняя граница/, 32.5], [/^Верхняя граница/, 50], [/^Диапазон зарплаты/, '32,5…50'],
    [/^Конкурентный ориентир/, 40], [/^Занятость на границах/, '45 и 50'], [/^Безработица на границах/, '0 и 30']],
};
async function sectionB() {
  head('Б. Старт моделей труда: новый пример');
  for (const key of ['labor', 'labor-mono', 'labor-union', 'labor-bilat']) {
    const { ctx, page, errors } = await openModel(key);
    ok(key + ': предусловие «Ответ» открыт', await answerShown(page));
    const st = await page.evaluate(() => STATE.curves.map(c => c.role + ':' + c.expr).join(', '));
    ok(key + ': кривые старта D = 100 − L, S = 10 + 0,5L', st === 'demand:100 - L, supply:10 + 0.5*L', st);
    const a = await answer(page);
    checkRows(key + ' старт', a, key === 'labor-union' ? UNION_NEW : START[key]);
    const c = await canvas(page);
    const k = await chkState(page);
    if (key === 'labor') {
      ok('labor: раздел «С МРОТ»', a.subsec.includes('С МРОТ'), a.subsec.join(' | '));
      ok('labor: на оси L «55 спрос» и «70 предл»', c.coords.includes('55спрос') && c.coords.includes('70предл'), c.coords.join(', '));
      ok('labor: МРОТ на старте 45 и включён', k.on && k.w === 45 && k.checked && k.shown, JSON.stringify(k));
    }
    if (key === 'labor-mono') {
      ok('labor-mono: «МРОТ увеличил занятость (парадокс монопсонии).»', a.hints.includes('МРОТ увеличил занятость (парадокс монопсонии).'), a.hints.join(' | '));
      ok('labor-mono: точка M (55; 45)', dotAt(c, 55, 45), JSON.stringify(c.dots));
      ok('labor-mono: МРОТ на старте 45 и включён', k.on && k.w === 45 && k.checked && k.shown, JSON.stringify(k));
    }
    if (key === 'labor-union') {
      ok('labor-union: точка «MRL = 0» подписана', c.texts.includes('MRL = 0'), c.texts.join(', '));
    }
    if (key === 'labor-bilat') {
      ok('labor-bilat: галочка МРОТ видна и снята, строки МРОТ нет', k.shown && !k.checked && !k.field && !k.on, JSON.stringify(k));
      ok('labor-bilat: линии МРОТ нет (подписи «… min» у оси нет)', !c.coords.some(t => /min/.test(t)), c.coords.join(', '));
      ok('labor-bilat: полоса торга от 32,5 до 50', !!c.band && near(c.band[0], 32.5, 0.2) && near(c.band[1], 50, 0.2), JSON.stringify(c.band));
      ok('labor-bilat: раздела «С МРОТ» нет', !a.subsec.length, a.subsec.join(' | '));
    }
    ok(key + ': ошибок страницы нет', !errors.length, errors.join('; '));
    await ctx.close();
  }
}

/* ── В ── */
const BIL_MAIN = START_BILAT();
function START_BILAT() {
  return [[/^Нижняя граница/, 32.5], [/^Верхняя граница/, 50], [/^Диапазон зарплаты/, '32,5…50'],
    [/^Конкурентный ориентир/, 40], [/^Занятость на границах/, '45 и 50'], [/^Безработица на границах/, '0 и 30']];
}
const bil = (page) => page.evaluate(() => { const b = STATE.laborBilateral; return { on: STATE.laborMinOn, w: STATE.laborMinW, min: b ? b.min || null : null, b }; });
const undoLen = (page) => page.evaluate(() => histOf().undo.length);
/* МРОТ как человек: щелчок по значению «W_min = …», набор, Enter (один шаг истории). */
async function typeMin(page, v) {
  await page.click('#labmin-field .pchip-label');
  await settle(page, 300);
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type(String(v));
  await page.keyboard.press('Enter');
  await settle(page);
}
const between = (W, lo, hi, Llo, Lhi, Ulo, Uhi, wasR, wasL, wasU) => [[/^МРОТ/, W], [/^Диапазон зарплаты/, lo + ' … ' + hi + ' (было ' + wasR + ')'],
  [/^Занятость на границах/, Llo + ' и ' + Lhi + ' (было ' + wasL + ')'], [/^Безработица на границах/, Ulo + ' и ' + Uhi + ' (было ' + wasU + ')']];
const single = (W, L, U, wasR, wasL, wasU) => [[/^МРОТ/, W], [/^Исход один: зарплата/, W + ' (было ' + wasR + ')'],
  [/^Занятость$/, L + ' (было ' + wasL + ')'], [/^Безработица$/, U + ' (было ' + wasU + ')']];
const NEWWAS = ['32,5 … 50', '45 и 50', '0 и 30'];
async function sectionV() {
  head('В. МРОТ в «Двусторонней монополии»');
  const { ctx, page, errors } = await openModel('labor-bilat');
  ok('В1: предусловие «Ответ» открыт', await answerShown(page));
  // 1. Старт.
  let k = await chkState(page), c = await canvas(page), a = await answer(page);
  ok('В1: галочка видна и снята', k.shown && !k.checked && !k.on, JSON.stringify(k));
  ok('В1: линии МРОТ нет', !c.coords.some(t => /min/.test(t)), c.coords.join(', '));
  checkRows('В1', a, BIL_MAIN);
  // 2. Галочка → МРОТ 45.
  let u0 = await undoLen(page);
  await page.click('#chk-labmin');
  await settle(page);
  a = await answer(page); c = await canvas(page);
  ok('В2: «С МРОТ»', a.subsec.includes('С МРОТ'), a.subsec.join(' | '));
  checkRows('В2', a, BIL_MAIN.concat(between(45, 45, 50, 55, 50, 15, 30, ...NEWWAS)));
  ok('В2: подсказка «МРОТ поднял нижнюю границу торга…»', a.hints.some(h => /^МРОТ поднял нижнюю границу торга/.test(h)), a.hints.join(' | '));
  ok('В2: холст — точка M (55; 45)', dotAt(c, 55, 45), JSON.stringify(c.dots));
  ok('В2: холст — полка «MCLэфф» и «Безработица = 15»', c.texts.includes('MCLэфф') && c.texts.includes('Безработица = 15'), c.texts.join(', '));
  ok('В2: холст — полоса 45 … 50', !!c.band && near(c.band[0], 45, 0.2) && near(c.band[1], 50, 0.2), JSON.stringify(c.band));
  ok('В2: у оси W внизу одно число — «45 min» линии МРОТ (не «32,5 м»)', c.coords.some(t => /^45min/.test(t)) && !c.coords.some(t => /^32,5м/.test(t)), c.coords.join(', '));
  ok('В2: один шаг истории', (await undoLen(page)) === u0 + 1, u0 + ' → ' + (await undoLen(page)));
  // 3. 36.
  u0 = await undoLen(page);
  await typeMin(page, 36);
  a = await answer(page); c = await canvas(page);
  checkRows('В3', a, BIL_MAIN.concat(between(36, 36, 50, 52, 50, 0, 30, ...NEWWAS)));
  ok('В3: полосы безработицы нет', !c.texts.some(t => /^Безработица =/.test(t)), c.texts.join(', '));
  ok('В3: один шаг истории', (await undoLen(page)) === u0 + 1);
  // 4. 30.
  await typeMin(page, 30);
  a = await answer(page);
  checkRows('В4', a, BIL_MAIN);
  ok('В4: «не связывает»', a.hints.some(h => /не выше монопсонической зарплаты, поэтому не связывает/.test(h)), a.hints.join(' | '));
  // 5. 50.
  await typeMin(page, 50);
  checkRows('В5', await answer(page), BIL_MAIN.concat(single(50, 50, 30, ...NEWWAS)));
  // 6. 60.
  await typeMin(page, 60);
  a = await answer(page); c = await canvas(page);
  checkRows('В6', a, BIL_MAIN.concat(single(60, 40, 60, ...NEWWAS)));
  ok('В6: надпись «Исход один: зарплата = МРОТ»', c.texts.includes('Исход один: зарплата = МРОТ'), c.texts.join(', '));
  ok('В6: полосы торга нет', !c.band, JSON.stringify(c.band));
  ok('В6: подсказка «МРОТ не ниже ставки профсоюза…»', a.hints.some(h => /^МРОТ не ниже ставки профсоюза/.test(h)), a.hints.join(' | '));
  ok('В6: на оси L «40 спрос» и «100 предл», «Безработица = 60»', c.coords.includes('40спрос') && c.coords.includes('100предл') && c.texts.includes('Безработица = 60'), c.coords.join(', '));
  // 7. Линия МРОТ мышью 45 → 60.
  await typeMin(page, 45);
  u0 = await undoLen(page);
  const [x0, y0] = await page.evaluate(() => { const { mx, my } = mainScales(null); const r = document.getElementById('chart').getBoundingClientRect(); return [r.left + mx(90), r.top + my(45)]; });
  const y1 = await page.evaluate(() => { const { my } = mainScales(null); return document.getElementById('chart').getBoundingClientRect().top + my(60); });
  await page.mouse.move(x0, y0); await page.mouse.down();
  for (let i = 1; i <= 8; i++) { await page.mouse.move(x0, y0 + (y1 - y0) * i / 8); await page.waitForTimeout(30); }
  await page.mouse.up();
  await settle(page);
  let v = await bil(page);
  const W7 = v.w;
  ok('В7: МРОТ протянут к 60 (±0,6)', near(W7, 60, 0.6), String(W7));
  ok('В7: исход один по живому МРОТ', !!v.min && v.min.single && near(v.min.Llo, 100 - W7, 0.02) && near(v.min.Ulo, 3 * W7 - 120, 0.05), JSON.stringify(v.min));
  a = await answer(page);
  ok('В7: «Ответ» — исход один', a.stats.some(r => /^Исход один: зарплата/.test(r.lab) && near(num(r.val), W7, 0.006)), a.stats.map(r => r.lab + '=' + r.val).join(' | '));
  ok('В7: один шаг истории', (await undoLen(page)) === u0 + 1, u0 + ' → ' + (await undoLen(page)));
  // 8. Снять галочку, «Отменить».
  await page.click('#chk-labmin');
  await settle(page);
  k = await chkState(page); c = await canvas(page); a = await answer(page);
  ok('В8: галочка снята, линии МРОТ нет', !k.checked && !k.on && !c.coords.some(t => /min/.test(t)), JSON.stringify(k));
  checkRows('В8', a, BIL_MAIN);
  await page.evaluate(() => { const b = document.getElementById('btn-undo'); if (b) b.click(); else historyUndo(); });
  await settle(page);
  k = await chkState(page); v = await bil(page);
  ok('В8: одно «Отменить» — МРОТ снова включён', k.checked && k.on && !!v.min, JSON.stringify(k));
  // 9. Ссылка и автосохранение с МРОТ 45.
  await typeMin(page, 45);
  const want9 = JSON.stringify((await bil(page)).min);
  const rows9 = (await answer(page)).stats.map(r => r.lab + '=' + r.val).join(' | ');
  const link = await page.evaluate(() => shareLinkOf());
  await settle(page, 1500);   // автосохранение пишется по затишью
  const saved = await page.evaluate(() => localStorage.getItem('calc2.v1.model.labor-bilat'));
  ok('В9: автосохранение записано', !!saved);
  ok('В9: ошибок страницы нет', !errors.length, errors.join('; '));
  await ctx.close();
  for (const [how, init, url] of [['ссылка', null, link], ['автосохранение', { 'calc2.v1.model.labor-bilat': saved }, null]]) {
    const o = await openModel('labor-bilat', init, url);
    await settle(o.page);
    const got = JSON.stringify((await bil(o.page)).min);
    const rows = (await answer(o.page)).stats.map(r => r.lab + '=' + r.val).join(' | ');
    ok('В9: ' + how + ' — те же числа', got === want9 && rows === rows9, got + ' ≠ ' + want9);
    ok('В9: ' + how + ' — ошибок страницы нет', !o.errors.length, o.errors.join('; '));
    await o.ctx.close();
  }
  // 10. «Второй пример».
  {
    const o = await openModel('labor-bilat');
    await setCurves(o.page, SECOND);
    await o.page.click('#chk-labmin'); await settle(o.page);
    await typeMin(o.page, 55);
    let m = (await bil(o.page)).min;
    ok('В10: второй пример, МРОТ 55 → 55 … 60, занятость 32,5 и 30, безработица 2,5 и 10',
      !!m && !m.single && near(m.Wlo, 55) && near(m.Whi, 60) && near(m.Llo, 32.5) && near(m.Lhi, 30) && near(m.Ulo, 2.5) && near(m.Uhi, 10), JSON.stringify(m));
    await typeMin(o.page, 70);
    m = (await bil(o.page)).min;
    ok('В10: второй пример, МРОТ 70 → исход один 70, занятость 25, безработица 25',
      !!m && m.single && near(m.W, 70) && near(m.Llo, 25) && near(m.Ulo, 25), JSON.stringify(m));
    ok('В10: ошибок страницы нет', !o.errors.length, o.errors.join('; '));
    await o.ctx.close();
  }
  // 11. Старые сохранения (код bfb74cc3).
  for (const key of ['labor', 'labor-mono', 'labor-union', 'labor-bilat']) {
    const fx = JSON.parse(fs.readFileSync(path.join(ROOT, 'claude', 'calc2_labor', 'fixtures', 'old_' + key + '.json'), 'utf8'));
    // Автосохранение — тем же путём, что autosaveModel: страница без модели кладёт состояние в хранилище.
    const z = await openModel('sd');
    const saved11 = await z.page.evaluate((st) => { autosaveModel(st); return localStorage.getItem('calc2.v1.model.' + st.key); }, fx.state);
    await z.ctx.close();
    for (const [how, init, url] of [['ссылка', null, fx.link.replace(/^https?:\/\/[^/]+/, BASE)], ['автосохранение', { ['calc2.v1.model.' + key]: saved11 }, null]]) {
      const o = await openModel(key, init, url);
      await settle(o.page);
      const r = await o.page.evaluate(() => ({ eq: STATE.laborEq, mono: STATE.laborMono, union: STATE.laborUnion, min: STATE.laborMin,
        w: STATE.laborMinWelfare, bm: STATE.laborBilateral ? STATE.laborBilateral.min : null, on: STATE.laborMinOn, W: STATE.laborMinW }));
      const tag = 'В11 ' + key + ' (' + how + ')';
      if (key === 'labor') ok(tag + ': конкуренция 50 / 50, МРОТ 65 → 35, безработица 30, 1662,5 и 612,5, DWL 225',
        near(r.eq.Q, 50) && r.on && near(r.W, 65) && near(r.min.employment, 35) && near(r.min.unemployment, 30) && near(r.w.workerCS, 1662.5, 0.05) && near(r.w.firmCS, 612.5, 0.05) && near(r.w.dwl, 225, 0.05), JSON.stringify(r));
      if (key === 'labor-mono') ok(tag + ': монопсония 33,33 / 33,33, МРОТ 65 → 35, зарплата 65, безработица 30',
        near(r.mono.Lm, 33.333, 0.01) && near(r.mono.Wm, 33.333, 0.01) && near(r.min.Lstar, 35) && near(r.min.wage, 65) && near(r.min.unemployment, 30), JSON.stringify(r));
      if (key === 'labor-union') ok(tag + ': профсоюз — угол 50 / 50, фонд 2 500',
        r.union && r.union.corner && near(r.union.Lu, 50) && near(r.union.Wu, 50) && near(r.union.fund, 2500, 0.1), JSON.stringify(r.union));
      if (key === 'labor-bilat') {
        const kk = await chkState(o.page);
        ok(tag + ': галочка МРОТ видна и включена', kk.shown && kk.checked && kk.on, JSON.stringify(kk));
        ok(tag + ': исход один 65, занятость 35, безработица 30', !!r.bm && r.bm.single && near(r.bm.W, 65) && near(r.bm.Llo, 35) && near(r.bm.Ulo, 30), JSON.stringify(r.bm));
      }
      ok(tag + ': ошибок страницы нет', !o.errors.length, o.errors.join('; '));
      await o.ctx.close();
    }
  }
}

/* ── А ── */
const UNION_NEW = [[/^Lп.*занятость/, 50], [/^Wп.*зарплата/, 50], [/^Фонд оплаты/, 2500], [/^Желающих работать/, 80],
  [/^Безработица/, 30], [/^Lk.*конкуренция/, 60], [/^Wk.*конкуренция/, 40], [/^DWL/, 75]];
async function sectionA() {
  head('А. «Профсоюз»: фонд оплаты');
  {
    const { ctx, page, errors } = await openModel('labor-union');
    ok('предусловие: «Ответ» открыт', await answerShown(page));
    await setCurves(page, NEW);
    const c = await canvasMRL(page);
    ok('холст: подпись «MRL = 0»', c.label === 'MRL = 0', c.label);
    ok('холст: подпись цветом MRL', c.labelColor);
    ok('холст: точка «MRL = 0» на оси L в 50', c.onAxis.length === 1 && near(c.onAxis[0], 50, 0.3), JSON.stringify(c.onAxis));
    ok('холст: точки «MRL = S» нет (кружков цвета MRL вне оси нет)', !c.offAxis.length, JSON.stringify(c.offAxis));
    const a = await answer(page);
    checkRows('новый пример', a, UNION_NEW);
    ok('новый пример: подсказка «Серым закрашены потери общества.»', a.hints.includes('Серым закрашены потери общества.'), a.hints.join(' | '));
    // «Сначала сам» прячет фонд, желающих и безработицу так же, как прежние числа.
    await page.click('#btn-self');
    await settle(page, 700);
    const s = await answer(page);
    ['Фонд оплаты', 'Желающих работать', 'Безработица'].forEach(w =>
      ok('«Сначала сам»: «' + w + '» не видно', !s.col.includes(w) && !s.stats.some(r => r.lab.startsWith(w) && r.shown), s.col.slice(0, 300)));
    ok('«Сначала сам»: числа 2 500 и 80 не видно', !/2[\s  ]?500/.test(s.col) && !/(^|\D)80(\D|$)/.test(s.col), s.col.slice(0, 300));
    await page.click('#btn-self');
    await settle(page, 700);
    const ex = await explainText(page);
    ok('«Разбор»: «единичной эластичности»', /единичной эластичности/.test(ex), ex.slice(0, 200));
    ok('«Разбор»: вопрос «Что максимизирует профсоюз в этой модели?»', /Что максимизирует профсоюз в этой модели\?/.test(ex));
    ok('ошибок страницы нет', !errors.length, errors.join('; '));
    await ctx.close();
  }
  for (const [nm, cv, L, Wv, fund] of [['«Угол»', CORNER, 33.33, 66.67, 2222.22], ['«Старый пример»', OLD, 50, 50, 2500]]) {
    const { ctx, page, errors } = await openModel('labor-union');
    ok(nm + ': предусловие «Ответ» открыт', await answerShown(page));
    await setCurves(page, cv);
    const a = await answer(page);
    checkRows(nm, a, [[/^Lп.*занятость/, L], [/^Wп.*зарплата/, Wv], [/^Фонд оплаты/, fund], [/^Lk.*конкуренция/, L], [/^Wk.*конкуренция/, Wv]]);
    ok(nm + ': подсказка про конкурентную ставку', a.hints.some(h => /конкурентная ставка/.test(h) && /потерь нет/.test(h)), a.hints.join(' | '));
    ok(nm + ': строк «Желающих работать», «Безработица», DWL нет', !a.stats.some(s => /Желающих|Безработица|DWL/.test(s.lab)), a.stats.map(s => s.lab).join(' | '));
    const c = await canvasMRL(page);
    ok(nm + ': точка «MRL = 0» на оси в 50', c.onAxis.some(x => near(x, 50, 0.3)), JSON.stringify(c.onAxis));
    ok(nm + ': ошибок страницы нет', !errors.length, errors.join('; '));
    await ctx.close();
  }
}

for (engName of ENGINES) {
  eng = engName;
  browser = await pw[engName].launch(); ctxCount = 0;
  for (W0 of WIDTHS) {
    if (want('А')) await sectionA();
    if (want('Б')) await sectionB();
    if (want('В')) await sectionV();
  }
  await browser.close();
}
console.log('\nИТОГ labor_probe: ' + (total - bad) + ' / ' + total + (bad ? '  — ПРОВАЛОВ ' + bad : '  — всё сошлось'));
process.exit(bad ? 1 : 0);
