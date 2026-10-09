/* ОТВЕТ «МАТЕМАТИКИ» НЕ ЗАВИСИТ ОТ МАСШТАБА — постоянные проверки сессии
   09.10.2026 (ADR 0143).

     ./venv313/bin/python manage.py runserver 8099 --noreload --settings=config.settings_check
     node calc2/tests/math_answer_probe.mjs

   Что стережёт прибор:
     А. Отрезок ответа подобран по формуле: x² − 4 и x³ − 3x → [−5; 5], sin x → [−10; 10].
     Б. Тексты ВСЕХ величин «Ответа» (главные ячейки и строки табло) побайтно те
        же при масштабе 100 %, ~1480 %, ~3664 % (приближение к вершине), после
        сдвига, когда в окне нет ни одного корня, и после «Вписать». Шесть
        моделей «Математики», каждая на трёх тестовых функциях.
     В. Ответы в формате сайта: «−2; 2», «(0; −4)», «нет».
     Г. Ручной отрезок переживает масштаб, сдвиг, «Вписать», перезагрузку
        (настоящий ввод, автосохранение) и ссылку «Поделиться»; [0; 10] у
        x² − 4 оставляет один корень 2; «Вернуть по формуле» → [−5; 5].
     Д. Окно «Построения графиков» на старте и по «Вписать» — вокруг ключевых
        точек во всех четырёх четвертях (фаза 3).
     Е. Локальные максимум и минимум — главные ячейки (фаза 4).

   ⚠️ Прибор стережёт ПРАВИЛО: ответ — свойство функции и отрезка, а не кадра.
   Числа окна (−10…10 и т. п.) не закреплены, кроме требований к запасу.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = process.env.ONLY || '';     // буква раздела: ONLY=Б — только он

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
if (!(await page.evaluate(() => typeof pickScene === 'function'))) { console.log('calc2 не загрузился'); process.exit(3); }

let bad = 0, total = 0;
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}
function eq(label, got, want) { ok(label, got === want, 'ожидалось «' + want + '», получилось «' + got + '»'); }
const want = (sec) => !ONLY || ONLY.includes(sec);

// Помощники внутри страницы: тексты «Ответа», жесты окна.
const INPAGE = `
window.__ma = {
  wait: (ms) => new Promise(r => setTimeout(r, ms || 120)),
  // Текст узла без невидимой половины KaTeX; пробелы и вид минуса не важны.
  t: (el) => { if (!el) return ''; const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
    return c.textContent.replace(/[\\s\\u00a0\\u202f\\u2009\\u200b]+/g, '').replace(/-/g, '−'); },
  // Строки табло своей модели (в «Построении графиков» — #info-graph).
  rows: () => [...document.querySelectorAll(STATE.mode === 'graph' ? '#info-graph .stat' : '#info-math .stat')]
    .map(s => ({ lab: __ma.t(s.querySelector(':scope > span')), val: __ma.t(s.querySelector(':scope > b')) })),
  cells: () => [...document.querySelectorAll('#ans-hero .ans-cell')]
    .map(c => ({ lab: __ma.t(c.querySelector('.ans-lab')) + (c.querySelector('.ans-not') ? ':' + __ma.t(c.querySelector('.ans-not')) : ''),
                 val: __ma.t(c.querySelector('.ans-val')) })),
  // Все тексты ответа одной строкой: по ней сверяется неизменность.
  all: () => JSON.stringify({ rows: __ma.rows(), cells: __ma.cells() }),
  find: (re) => { const r = __ma.rows().find(x => re.test(x.lab)); return r ? r.val : null; },
  panel0: () => (STATE.panels && STATE.panels[0]) ? STATE.panels[0].id : undefined,
  span: () => { const w = viewWindow(__ma.panel0()); return w.x1 - w.x0; },
  // Приблизить к точке (x; y) так, чтобы масштаб стал pct процентов от стартового.
  zoomTo: async (pct, x, y, base) => {
    const pid = __ma.panel0();
    const { mx, my } = mainScales(pid);
    zoomBy((base * 100 / pct) / __ma.span(), mx(x), my(y));
    await __ma.wait();
    return document.getElementById('zoom-level').textContent;
  },
  // Сдвинуть окно на 50 его ширин вправо: в окне не остаётся ни одного корня.
  panAway: async () => {
    const pid = __ma.panel0();
    const panel = (STATE.mode === 'math' && STATE.mathSub === 'tangent') ? 'top' : null;
    const { mx } = mainScales(pid);
    const px = Math.abs(mx.range()[1] - mx.range()[0]);
    panByPixels(-px * 50, 0, panel);
    await __ma.wait();
  },
  fit: async () => { resetZoom(); await __ma.wait(); },
  open: async (key, setup) => {
    resetSceneMemory(); pickScene(key); await __ma.wait(200);
    if (setup) { setup(); redrawAll(); await __ma.wait(200); }
  },
  setGraph: (exprs) => { STATE.curves = []; curveCounter = 0; exprs.forEach(e => addCurve(e)); renderGraphRows(); },
  setMath: (e) => { STATE.mathFormula = e; const i = document.getElementById('inp-mathf'); if (i) i.value = e; },
};`;
await page.addScriptTag({ content: INPAGE });
const ev = (fn, arg) => page.evaluate(fn, arg);

/* Тестовые функции и вершины, к которым приближаемся. */
const FUNCS = [
  { e: 'x^2-4',   v: [0, -4] },
  { e: 'x^3-3*x', v: [1, -2] },
  { e: 'sin(x)',  v: [Math.PI / 2, 1] },
];
const MODELS = [
  { key: 'm-graph',     setup: (e) => `__ma.setGraph(['${e}'])` },
  { key: 'm-optimum',   setup: (e) => `__ma.setMath('${e}')` },
  { key: 'm-tangent',   setup: (e) => `__ma.setMath('${e}')` },
  { key: 'm-transform', setup: (e) => `__ma.setMath('${e}')` },
  { key: 'm-minmax',    setup: (e) => `__ma.setMath('${e}')` },
  { key: 'm-constraint', setup: () => '', once: true },
];

/* ── А. Отрезок по формуле ─────────────────────────────────────────── */
if (want('А')) {
  head('А. Отрезок ответа по умолчанию — по формуле');
  for (const [e, a, b] of [['x^2-4', -5, 5], ['x^3-3*x', -5, 5], ['sin(x)', -10, 10]]) {
    const r = await ev(async (e) => { await __ma.open('m-graph', () => __ma.setGraph([e])); return [_ansSeg.a, _ansSeg.b, _ansSeg.hand]; }, e);
    eq(e + ': отрезок', r[0] + '…' + r[1], a + '…' + b);
    ok(e + ': подобран по формуле, не руками', r[2] === false);
  }
  const r = await ev(async () => { await __ma.open('m-graph'); return [_ansSeg.a, _ansSeg.b, getComputedStyle(document.getElementById('ans-seg-row')).display]; });
  eq('старт «Построения графиков»: отрезок', r[0] + '…' + r[1], '-5…5');
  ok('строка отрезка видна', r[2] !== 'none');
  const rc = await ev(async () => { await __ma.open('m-constraint'); return getComputedStyle(document.getElementById('ans-seg-row')).display; });
  eq('«С ограничением»: строки отрезка нет', rc, 'none');
}

/* ── Б. Тексты «Ответа» не зависят от кадра ─────────────────────────── */
if (want('Б')) {
  head('Б. Тексты «Ответа» при масштабе, сдвиге и «Вписать»');
  let diffs = 0;
  for (const m of MODELS) {
    for (const f of (m.once ? [FUNCS[0]] : FUNCS)) {
      const r = await ev(async ({ key, setup, v }) => {
        await __ma.open(key, setup ? new Function(setup) : null);
        const base = __ma.span();
        const out = { start: __ma.all(), steps: [] };
        out.steps.push(['~1480 %', await __ma.zoomTo(1480, v[0], v[1], base), __ma.all()]);
        out.steps.push(['~3664 %', await __ma.zoomTo(3664, v[0], v[1], base), __ma.all()]);
        await __ma.panAway(); out.steps.push(['сдвиг без корней', '', __ma.all()]);
        await __ma.fit(); out.steps.push(['«Вписать»', '', __ma.all()]);
        return out;
      }, { key: m.key, setup: m.setup(f.e), v: m.key === 'm-constraint' ? [5, 5] : f.v });
      const name = m.key + (m.once ? '' : ' · ' + f.e);
      const changed = r.steps.filter(s => s[2] !== r.start);
      diffs += changed.length;
      ok(name + ': ответ один и тот же (' + r.steps.map(s => s[0] + (s[1] ? ' ' + s[1] : '')).join(', ') + ')',
        !changed.length, changed.map(s => s[0] + ': ' + s[2].slice(0, 160) + ' ≠ ' + r.start.slice(0, 160)).join(' | '));
    }
  }
  eq('расхождений всего', diffs, 0);
}

/* ── В. Ответы в формате сайта ─────────────────────────────────────── */
if (want('В')) {
  head('В. Ответы: числа, точки, «нет»');
  const get = (key, setup) => ev(async ({ key, setup }) => {
    await __ma.open(key, setup ? new Function(setup) : null);
    return __ma.rows();
  }, { key, setup });
  const val = (rows, re) => { const r = rows.find(x => re.test(x.lab)); return r ? r.val : '(нет строки)'; };
  const N = (s) => s.replace(/\s+/g, '').replace(/-/g, '−');
  let rows = await get('m-graph', "__ma.setGraph(['x^2-4'])");
  eq('x²−4: ось x', val(rows, /^Пересекаетосьx/), N('−2; 2'));
  eq('x²−4: ось y', val(rows, /^Пересекаетосьy/), N('−4'));
  eq('x²−4: лок. минимум', val(rows, /^Локальныйминимум/), N('(0; −4)'));
  eq('x²−4: лок. максимум', val(rows, /^Локальныймаксимум/), 'нет');
  rows = await get('m-graph', "__ma.setGraph(['x^3-3*x'])");
  eq('x³−3x: ось x', val(rows, /^Пересекаетосьx/), N('−1,732; 0; 1,732'));
  eq('x³−3x: ось y', val(rows, /^Пересекаетосьy/), '0');
  eq('x³−3x: лок. максимум', val(rows, /^Локальныймаксимум/), N('(−1; 2)'));
  eq('x³−3x: лок. минимум', val(rows, /^Локальныйминимум/), N('(1; −2)'));
  rows = await get('m-graph', "__ma.setGraph(['sin(x)'])");
  eq('sin x: нули на [−10; 10]', val(rows, /^Пересекаетосьx/), N('−9,425; −6,283; −3,142; 0; 3,142; 6,283; 9,425'));
  eq('sin x: максимумы', val(rows, /^Локальныймаксимум/), N('(−4,712; 1); (1,571; 1); (7,854; 1)'));
  eq('sin x: минимумы', val(rows, /^Локальныйминимум/), N('(−7,854; −1); (−1,571; −1); (4,712; −1)'));
  rows = await get('m-graph', "__ma.setGraph(['x^2-4', 'x+2'])");
  eq('x²−4 и x+2: пересечения кривых', val(rows, /^Пересечениякривых/), N('(−2; 0); (3; 5)'));
  // Те же функции в остальных моделях вида y = f(x): экстремумы те же.
  for (const key of ['m-optimum', 'm-tangent', 'm-transform', 'm-minmax']) {
    rows = await get(key, key === 'm-minmax' ? "__ma.setMath('x^3-3*x'); STATE.mathG2 = '100'; STATE.mathMinMax = 'min'" : "__ma.setMath('x^3-3*x')");
    eq(key + ' x³−3x: лок. максимум', val(rows, /^Локальныймаксимум/), N('(−1; 2)'));
    eq(key + ' x³−3x: лок. минимум', val(rows, /^Локальныйминимум/), N('(1; −2)'));
  }
  // Контрольные числа «Математики» (calc2/CLAUDE.md) — на отрезке ответа.
  const cn = await ev(async () => {
    await __ma.open('m-optimum', () => __ma.setMath('x^3 - 3*x'));
    const a = STATE.mathRes;
    const roots = ansAnalyse(mathF(), _ansSeg.a, _ansSeg.b).zeros;
    await __ma.open('m-minmax', () => { __ma.setMath('x^2'); STATE.mathG2 = '4 - x'; STATE.mathMinMax = 'min'; });
    const sw = STATE.mathRes.switches || [];
    return { roots, xmax: (a.ext.find(p => p.kind === 'max') || {}).x, xmin: (a.ext.find(p => p.kind === 'min') || {}).x,
             sw: sw[sw.length - 1], swy: sw.length ? sw[sw.length - 1] ** 2 : NaN };
  });
  eq('контроль: x³−3x корни', cn.roots.map(v => v.toFixed(3)).join('; '), '-1.732; 0.000; 1.732');
  ok('контроль: x³−3x максимум при −1', Math.abs(cn.xmax + 1) < 0.02, String(cn.xmax));
  ok('контроль: x³−3x минимум при 1', Math.abs(cn.xmin - 1) < 0.02, String(cn.xmin));
  ok('контроль: min(x², 4−x) пересечение x = 1,5616', Math.abs(cn.sw - 1.5616) < 1e-3, String(cn.sw));
  ok('контроль: y = 2,4384', Math.abs(cn.swy - 2.4384) < 1e-3, String(cn.swy));
}

/* ── Г. Ручной отрезок ─────────────────────────────────────────────── */
if (want('Г')) {
  head('Г. Ручной отрезок: масштаб, «Вписать», перезагрузка, ссылка');
  await ev(async () => { await __ma.open('m-graph'); });
  // Настоящий ввод человека: так пишутся история и автосохранение.
  await page.fill('#ans-a', '0');
  await page.fill('#ans-b', '10');
  await page.press('#ans-b', 'Enter');
  await page.waitForTimeout(400);
  let r = await ev(() => [_ansSeg.a, _ansSeg.b, _ansSeg.hand, __ma.find(/^Пересекаетосьx/), document.getElementById('ans-seg-auto').hidden]);
  eq('ручной отрезок', r[0] + '…' + r[1], '0…10');
  ok('отрезок ручной', r[2] === true);
  eq('[0; 10]: остался один корень 2', r[3], '2');
  ok('видна «Вернуть по формуле»', r[4] === false);
  r = await ev(async () => {
    const base = __ma.span();
    await __ma.zoomTo(1480, 0, -4, base); const z = [_ansSeg.a, _ansSeg.b];
    await __ma.panAway(); const p = [_ansSeg.a, _ansSeg.b];
    await __ma.fit(); const f = [_ansSeg.a, _ansSeg.b];
    return [z.join('…'), p.join('…'), f.join('…')];
  });
  eq('после приближения', r[0], '0…10');
  eq('после сдвига', r[1], '0…10');
  eq('после «Вписать»', r[2], '0…10');
  // Перезагрузка: автосохранение поднимается при загрузке страницы с ?m=.
  await page.waitForTimeout(700);
  await page.goto(`${BASE}/calc2/?m=m-graph`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await page.addScriptTag({ content: INPAGE });
  r = await ev(() => [_ansSeg.a, _ansSeg.b, _ansSeg.hand, document.getElementById('ans-a').value, document.getElementById('ans-b').value]);
  eq('после перезагрузки', r[0] + '…' + r[1] + (r[2] ? ' (руками)' : ''), '0…10 (руками)');
  eq('поля после перезагрузки', r[3] + '…' + r[4], '0…10');
  // Ссылка «Поделиться» на чистой странице.
  const link = await ev(async () => shareLinkOf());
  await ev(() => resetSceneMemory());
  await page.goto(link, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.addScriptTag({ content: INPAGE });
  r = await ev(() => [_ansSeg.a, _ansSeg.b, _ansSeg.hand]);
  eq('по ссылке «Поделиться»', r[0] + '…' + r[1] + (r[2] ? ' (руками)' : ''), '0…10 (руками)');
  await page.click('#ans-seg-auto');
  await page.waitForTimeout(300);
  r = await ev(() => [_ansSeg.a, _ansSeg.b, _ansSeg.hand]);
  eq('«Вернуть по формуле»', r[0] + '…' + r[1] + (r[2] ? ' (руками)' : ''), '-5…5');
  // Пустое поле и «от ≥ до» — назад к формуле.
  await page.fill('#ans-a', '7'); await page.fill('#ans-b', '3'); await page.press('#ans-b', 'Enter');
  await page.waitForTimeout(300);
  r = await ev(() => [_ansSeg.a, _ansSeg.b, _ansSeg.hand]);
  eq('«от ≥ до» → по формуле', r[0] + '…' + r[1] + (r[2] ? ' (руками)' : ''), '-5…5');
  await ev(() => resetSceneMemory());
}

/* ── Д. Окно «Построения графиков» ─────────────────────────────────── */
if (want('Д')) {
  head('Д. Окно «Построения графиков» — вокруг ключевых точек');
  const r = await ev(async () => {
    const out = {};
    const meas = (label) => {
      const w = viewWindow(); const W_ = w.x1 - w.x0, H_ = w.y1 - w.y0;
      const pts = [[0, -4], [-2, 0], [2, 0]];
      const margin = Math.min(...pts.map(([x, y]) => Math.min((x - w.x0) / W_, (w.x1 - x) / W_, (y - w.y0) / H_, (w.y1 - y) / H_)));
      out[label] = { w: [w.x0, w.x1, w.y0, w.y1].map(v => +v.toFixed(3)), margin: +margin.toFixed(3),
        yAxisAt: +((0 - w.x0) / W_).toFixed(3), xAxisAt: +((0 - w.y0) / H_).toFixed(3) };
    };
    await __ma.open('m-graph'); await __ma.wait(2600);   // расширение окна приходит с задержкой
    meas('старт');
    const { mx, my } = mainScales(); zoomBy(0.2, mx(5), my(5)); await __ma.wait(300);
    await __ma.fit(); await __ma.wait(2600); meas('Вписать');
    return out;
  });
  for (const k of Object.keys(r)) {
    const m = r[k];
    console.log('    ' + k + ': окно ' + m.w.join(' … ') + ', запас ' + m.margin + ', ось y на ' + m.yAxisAt + ' ширины');
    ok(k + ': вершина и нули внутри с запасом ≥ 8 %', m.margin >= 0.08, String(m.margin));
    ok(k + ': обе оси видны', m.yAxisAt > 0 && m.yAxisAt < 1 && m.xAxisAt > 0 && m.xAxisAt < 1);
    ok(k + ': ось y примерно посередине', Math.abs(m.yAxisAt - 0.5) < 0.1, String(m.yAxisAt));
  }
}

/* ── Е. Локальные максимум и минимум — главные ячейки ──────────────── */
if (want('Е')) {
  head('Е. Ячейки «Локальный максимум» и «Локальный минимум»');
  for (const key of ['m-graph', 'm-optimum', 'm-tangent', 'm-transform', 'm-minmax']) {
    const c = await ev(async (key) => { await __ma.open(key); await __ma.wait(200); return __ma.cells(); }, key);
    const mx = c.find(x => /^Локальныймаксимум/.test(x.lab)), mn = c.find(x => /^Локальныйминимум/.test(x.lab));
    ok(key + ': ячейка «Локальный максимум»', !!mx, mx ? mx.val : c.map(x => x.lab).join(', '));
    ok(key + ': ячейка «Локальный минимум»', !!mn, mn ? mn.val : '');
    const fmtOk = (v) => v === 'нет' || /^\(−?[\d,]+;−?[\d,]+\)(;\(−?[\d,]+;−?[\d,]+\))*$/.test(v);
    if (mx) ok(key + ': максимум в формате «(x; y)» или «нет»', fmtOk(mx.val), mx.val);
    if (mn) ok(key + ': минимум в формате «(x; y)» или «нет»', fmtOk(mn.val), mn.val);
  }
}

ok('ошибок страницы нет', !errs.length, errs.slice(0, 3).join(' | '));
console.log(`\n=== math_answer_probe: ${total - bad} прошло, ${bad} провалено (всего ${total}) ===`);
await browser.close();
process.exit(bad ? 1 : 0);
