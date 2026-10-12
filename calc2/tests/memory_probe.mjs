/* СДВИГ КРИВОЙ НЕ КОПИТ ПАМЯТЬ — постоянные проверки починки 13.10.2026.

     ./venv313/bin/python manage.py runserver 8099 --noreload --settings=config.settings_check
     node calc2/tests/memory_probe.mjs              # TIMING=1 — ещё и время шага чередованием

   Что сломалось. Каждый шаг ползунка сдвига шёл через setCurveFreeTerm →
   renderCurveList(): список функций строился заново вместе с полями MathLive,
   а замыкание каждого поля навсегда оседало в очередях ожидания библиотек
   (_texPending, _mfPending, 82-input.js). 808 шагов «Сдвига MC» в Chromium —
   узлов DOM 15 979 → 487 483, Safari закрывал вкладку.

   Что стережёт прибор (счётчики после 1,5 с затишья и сборки мусора через CDP):
     А. ?m=mono, ползунок «Сдвиг MC», 400 шагов: узлов DOM больше стартовых
        не более чем на 5 000, обработчиков событий — не более чем на 1 000.
     Б. То же на ?m=sd (ползунок «Сдвиг D»).
     В. ?m=ceil: мышью тянуть линию потолка 100 раз; ?m=costs: линию цены 100 раз.
     Г. 100 шагов «Сдвига MC»: 0 новых math-field и 0 полных пересборок списка.
     Д. Текст формулы MC в списке равен формуле кривой (старт «20», сдвиг +7 →
        «27»); «Отменить» после затишья возвращает «20» одним шагом;
        автосохранение пишет «27».
     Е. Очереди ожидания библиотек после загрузки пусты (_texPending, _mfPending).

   ⚠️ Узлы считает Memory.getDOMCounters: он видит и оторванные от страницы, но
   живые узлы — ровно то, что держали замыкания.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = process.env.ONLY || '';
const SHORT = !!process.env.SHORT;            // короткий прогон для CI: 150 шагов только в А
const TIMING = !!process.env.TIMING;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
const cdp = await ctx.newCDPSession(page);
await cdp.send('HeapProfiler.enable');

let bad = 0, total = 0;
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}
const want = (sec) => !ONLY || ONLY.includes(sec);

async function counters() {
  await page.waitForTimeout(1500);                  // очередь flushMathfields разбирается на кадре
  await cdp.send('HeapProfiler.collectGarbage');
  return cdp.send('Memory.getDOMCounters');
}
async function open(model) {
  await page.goto(`${BASE}/calc2/?m=${model}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  if (!(await page.evaluate(() => typeof pickScene === 'function'))) { console.log('calc2 не загрузился'); process.exit(3); }
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
}
// Ползунок сдвига кривой роли role: чип пульта по data-cid.
async function shiftSlider(role) {
  return page.evaluate((role) => {
    const c = STATE.curves.find(x => x.role === role);
    const sl = c && document.querySelector('.pchip[data-pult-box="params-curves"][data-cid="' + c.id + '"] input[type=range]');
    if (!sl) return null;
    sl.id = sl.id || '__shift_' + role;
    return { id: sl.id, min: +sl.min, max: +sl.max, cid: c.id, expr: c.expr };
  }, role);
}
// n шагов туда и обратно по ползунку (value + событие input, как у ручки).
async function sweep(id, n) {
  return page.evaluate(([id, n]) => {
    const s = document.getElementById(id);
    const lo = Math.max(+s.min, -50), hi = Math.min(+s.max, 50);
    const half = Math.max(1, Math.floor(n / 2)), step = (hi - lo) / half;
    let k = 0;
    const set = (v) => { s.value = v; s.dispatchEvent(new Event('input', { bubbles: true })); k++; };
    for (let i = 0; i < half; i++) set(lo + step * i);
    for (let i = 0; k < n; i++) set(hi - step * i);
    return k;
  }, [id, n]);
}
function growth(label, c0, c1, maxNodes, maxListeners) {
  const dn = c1.nodes - c0.nodes, dl = c1.jsEventListeners - c0.jsEventListeners;
  ok(label + ': прирост узлов DOM ≤ ' + maxNodes, dn <= maxNodes, c0.nodes + ' → ' + c1.nodes + ' (' + (dn >= 0 ? '+' : '') + dn + ')');
  ok(label + ': прирост обработчиков ≤ ' + maxListeners, dl <= maxListeners,
    c0.jsEventListeners + ' → ' + c1.jsEventListeners + ' (' + (dl >= 0 ? '+' : '') + dl + ')');
}
// Протяжка мышью по зоне захвата линии (rect с курсором grab) n раз вверх-вниз.
async function dragLine(n) {
  const box = await page.evaluate(() => {
    const r = [...document.querySelectorAll('#chart rect')].find(e => e.style.cursor === 'grab' && e.getBBox().width > 20);
    if (!r) return null;
    const b = r.getBoundingClientRect();
    return { x: b.x + b.width * 0.5, y: b.y + b.height / 2 };
  });
  if (!box) return 0;
  await page.mouse.move(box.x, box.y);
  await page.mouse.down();
  let k = 0;
  for (let i = 0; i < n; i++) { await page.mouse.move(box.x, box.y + ((i % 20) < 10 ? -(i % 10) * 4 : -(10 - (i % 10)) * 4)); k++; }
  await page.mouse.up();
  return k;
}

/* ── А. Монополия, «Сдвиг MC» ──────────────────────────────────────── */
if (want('А')) {
  head('А. «Стандартная монополия»: ползунок «Сдвиг MC»');
  await open('mono');
  const s = await shiftSlider('mc');
  ok('ползунок «Сдвиг MC» найден', !!s, s && JSON.stringify(s));
  if (s) {
    const c0 = await counters();
    const n = await sweep(s.id, SHORT ? 150 : 400);
    const c1 = await counters();
    growth(n + ' шагов', c0, c1, SHORT ? 2000 : 5000, SHORT ? 400 : 1000);
  }
}

/* ── Б. Спрос и предложение, «Сдвиг D» ─────────────────────────────── */
if (want('Б') && !SHORT) {
  head('Б. «Спрос и предложение»: ползунок «Сдвиг D»');
  await open('sd');
  const s = await shiftSlider('demand');
  ok('ползунок «Сдвиг D» найден', !!s, s && JSON.stringify(s));
  if (s) {
    const c0 = await counters();
    const n = await sweep(s.id, 400);
    const c1 = await counters();
    growth(n + ' шагов', c0, c1, 5000, 1000);
  }
}

/* ── В. Протяжка мышью ─────────────────────────────────────────────── */
if (want('В') && !SHORT) {
  head('В. Мышью: линия потолка (?m=ceil) и линия цены (?m=costs)');
  await open('ceil');
  let c0 = await counters();
  let n = await dragLine(100);
  let c1 = await counters();
  ok('потолок: протяжка состоялась', n === 100, 'шагов ' + n);
  growth('потолок, ' + n + ' шагов мыши', c0, c1, 5000, 1000);

  await open('costs');
  await page.evaluate(() => { STATE.lrOn = true; STATE.lrPrice = 20; redrawAll(); });
  await page.waitForTimeout(300);
  c0 = await counters();
  n = await dragLine(100);
  c1 = await counters();
  ok('цена: протяжка состоялась', n === 100, 'шагов ' + n);
  growth('линия цены, ' + n + ' шагов мыши', c0, c1, 5000, 1000);
}

/* ── Г. Ни одного нового поля и ни одной пересборки ────────────────── */
if (want('Г')) {
  head('Г. 100 шагов «Сдвига MC»: строка обновляется на месте');
  await open('mono');
  const s = await shiftSlider('mc');
  await page.evaluate(() => {
    window.__mem = { mf: 0, rows: 0, rebuilds: 0 };
    const real = window.renderCurveList;
    window.renderCurveList = function () { __mem.rebuilds++; return real.apply(this, arguments); };
    window.__memObs = new MutationObserver(list => list.forEach(m => m.addedNodes.forEach(n => {
      if (n.nodeType !== 1) return;
      if (n.matches('math-field')) __mem.mf++;
      __mem.mf += n.querySelectorAll('math-field').length;
      if (n.matches('.fc-card')) __mem.rows++;
    })));
    __memObs.observe(document.body, { childList: true, subtree: true });
  });
  await sweep(s.id, 100);
  await page.waitForTimeout(800);
  const m = await page.evaluate(() => { __memObs.disconnect(); return __mem; });
  ok('новых math-field: 0', m.mf === 0, String(m.mf));
  ok('полных пересборок списка (renderCurveList): 0', m.rebuilds === 0, String(m.rebuilds));
  ok('новых строк списка (.fc-card): 0', m.rows === 0, String(m.rows));
}

/* ── Д. Запись в списке, «Отменить», автосохранение ────────────────── */
if (want('Д')) {
  head('Д. Формула MC в списке, «Отменить», автосохранение');
  await open('mono');
  const s = await shiftSlider('mc');
  const read = () => page.evaluate((cid) => {
    const c = STATE.curves.find(x => x.id === cid);
    const row = document.querySelector('#curve-list .fc-card[data-cid="' + cid + '"]');
    const inp = row && row.querySelector('.curve-expr-inp');
    const mf = inp && inp._mf;
    const saved = Object.keys(localStorage).filter(k => /^calc2\.v1\./.test(k)).map(k => localStorage.getItem(k)).join('\n');
    return { expr: c.expr, field: inp && inp.value, mf: mf ? latexToMath(mf.value) : null,
             tip: row && (row.querySelector('.crow-top .curve-name') || {}).getAttribute && row.querySelector('.crow-top .curve-name').getAttribute('data-tip'),
             saved27: /"expr":"27"/.test(saved) };
  }, s.cid);
  const r0 = await read();
  ok('старт: формула кривой «20»', r0.expr === '20', r0.expr);
  ok('старт: поле списка «20»', r0.field === '20' && (r0.mf == null || r0.mf === '20'), JSON.stringify(r0));
  // Как человек: фокус на ручке и семь нажатий стрелки (шаг 1 при размахе −50…50).
  // Синтетическое событие история за правку человека не считает (ADR 0136).
  await page.focus('#' + s.id);
  for (let i = 0; i < 7; i++) await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(900);                    // затишье истории 300 мс и автосохранение
  const r1 = await read();
  ok('сдвиг +7: формула кривой «27»', r1.expr === '27', r1.expr);
  ok('сдвиг +7: поле списка «27» (и MathLive)', r1.field === '27' && (r1.mf == null || r1.mf === '27'), JSON.stringify(r1));
  ok('сдвиг +7: подсказка строки с новой записью', /27/.test(r1.tip || ''), r1.tip);
  ok('автосохранение пишет «27»', r1.saved27);
  await page.mouse.click(5, 5);                      // уйти с ручки: Ctrl+Z на ползунке — его клавиша
  await page.click('#btn-undo');
  await page.waitForTimeout(600);
  const r2 = await read();
  ok('«Отменить» одним шагом: формула «20»', r2.expr === '20', r2.expr);
  ok('«Отменить»: поле списка «20»', r2.field === '20' && (r2.mf == null || r2.mf === '20'), JSON.stringify(r2));
}

/* ── Е. Очереди ожидания библиотек ─────────────────────────────────── */
if (want('Е')) {
  head('Е. Очереди ожидания KaTeX и MathLive после загрузки пусты');
  await open('mono');
  const s = await shiftSlider('mc');
  await sweep(s.id, 50);
  await page.waitForTimeout(600);
  const q = await page.evaluate(() => ({ tex: _texPending.length, mf: _mfPending.length, katex: typeof katex !== 'undefined', ml: MATHLIVE_READY,
    waiting: _mfWaiting.filter(i => !i.isConnected).length, fields: FORMULA_FIELDS.filter(i => !i.isConnected).length }));
  ok('_texPending пуста (KaTeX загружен: ' + q.katex + ')', q.tex === 0, String(q.tex));
  ok('_mfPending пуста (MathLive загружен: ' + q.ml + ')', q.mf === 0, String(q.mf));
  ok('_mfWaiting без оторванных полей', q.waiting === 0, String(q.waiting));
  ok('FORMULA_FIELDS без оторванных полей', q.fields === 0, String(q.fields));
}

/* ── Время шага, справочно (чередованием: на месте / старой пересборкой) ── */
if (TIMING) {
  head('Время шага «Сдвига MC», мс (справочно, чередование)');
  await open('mono');
  const s = await shiftSlider('mc');
  const r = await page.evaluate(async (id) => {
    const sl = document.getElementById(id);
    const W = () => new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
    const med = (a) => { const b = a.slice().sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };
    const realRefresh = window.refreshCurveRow;
    const tNew = [], tOld = [];
    for (let block = 0; block < 10; block++) {
      const old = block % 2 === 1;
      // «старый путь»: строку не обновлять на месте, а пересобирать список (как до 13.10)
      window.refreshCurveRow = old ? () => false : realRefresh;
      for (let i = 0; i < 15; i++) {
        const t0 = performance.now();
        sl.value = (i % 2 ? 10 : -10) + block; sl.dispatchEvent(new Event('input', { bubbles: true }));
        (old ? tOld : tNew).push(performance.now() - t0);
        await W();
      }
    }
    window.refreshCurveRow = realRefresh;
    return { newMed: med(tNew), oldMed: med(tOld), n: tNew.length };
  }, s.id);
  console.log('  на месте: медиана ' + r.newMed.toFixed(1) + ' мс; пересборкой списка: ' + r.oldMed.toFixed(1) + ' мс (по ' + r.n + ' шагов)');
}

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? '  ' + errs.slice(0, 3).join(' | ') : ''));
console.log(bad ? `ПРОВАЛОВ: ${bad} из ${total}` : `ВСЕ ${total} ПРОВЕРОК ПРОШЛИ`);
await browser.close();
process.exit(bad || errs.length ? 1 : 0);
