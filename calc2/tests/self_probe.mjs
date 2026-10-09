/* «СНАЧАЛА САМ»: ОТВЕТ СПИСКОМ, ТОЧКОЙ И «НЕТ»; КООРДИНАТЫ КЛЮЧЕВЫХ ТОЧЕК
   «(?; ?)» ДО ВЕРНОГО ОТВЕТА — постоянные проверки сессии 09.10.2026 (ADR 0143).

     ./venv313/bin/python manage.py runserver 8099 --noreload --settings=config.settings_check
     node calc2/tests/self_probe.mjs

   Что стережёт прибор:
     А. При включённом режиме у шести моделей «Математики» и у «Спроса и
        предложения» нет ни одной главной ячейки с числами, открытой без поля.
     Б. Разбор и сравнение ответа: порядок не важен, число значений обязано
        совпасть, «нет» — ответ, точка «(x; y)», неразобранное — подсказка без
        вердикта; экономические ячейки с одним числом — как раньше.
     В. Подпись ключевой точки при наведении — «(?; ?)», пока её координаты не
        открыты верным ответом или «Показать»; закрепка до того недоступна.
        «Показать всё» открывает все; выключенный режим — всё как без него.
     Г. Столбик (сессия 3, ADR 0144): подпись строкой, поле на всю ширину и
        «Проверить» справа, ниже вердикт и «Показать». У всех полей колонки одна
        ширина (разброс ≤ 1 px), поле не уже 60 % строки; подписей, обрезанных
        многоточием, нет; высота строки до и после вердикта одна; пояснение
        формата ответа у математики и у экономики своё.
     Д. Режим — вид, а не вход модели (ADR 0144): включение не делает шаг
        истории; «ползунок → режим → Отменить» откатывает ползунок, режим
        остаётся; в сценарии из 20 шагов (включить, выключить, отменить,
        повторить, сменить модель) кнопка и режим не расходятся ни разу;
        ссылка «Поделиться» с галочкой несёт режим (&self=1).
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = process.env.ONLY || '';

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
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
const ev = (fn, arg) => page.evaluate(fn, arg);

await page.addScriptTag({ content: `
window.__sp = {
  wait: (ms) => new Promise(r => setTimeout(r, ms || 150)),
  t: (el) => { if (!el) return ''; const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
    return c.textContent.replace(/[\\s\\u00a0\\u202f\\u2009\\u200b]+/g, ''); },
  open: async (key, setup) => {
    if (typeof setSelfMode === 'function' && SELF.on) setSelfMode(false);
    resetSceneMemory(); pickScene(key); await __sp.wait(250);
    if (setup) { setup(); redrawAll(); await __sp.wait(250); }
    // Включение режима больше не шаг истории (ADR 0144, раздел Д), но перерисовка
    // после него будит проверку истории через 300 мс затишья. Ждём её.
    setSelfMode(true); await __sp.wait(600);
  },
  cells: () => [...document.querySelectorAll('#ans-hero .ans-cell')].map((c, i) => ({
    // «подпись:обозначение». С сессии 3 (ADR 0144) у математики обозначение не
    // выносится в значение: оно в data-not и в конце подписи — снимаем его оттуда.
    i, lab: c.querySelector('.ans-not') ? __sp.t(c.querySelector('.ans-lab')) + ':' + __sp.t(c.querySelector('.ans-not'))
      : (c.dataset.not ? __sp.t(c.querySelector('.ans-lab')).replace(new RegExp(c.dataset.not.replace(/[*∗]/g, '.') + '$'), '') + ':' + c.dataset.not
        : __sp.t(c.querySelector('.ans-lab'))),
    val: __sp.t(c.querySelector('.ans-val')), field: !!c.querySelector('.self-inp'),
    hidden: c.classList.contains('self-hidden') })),
  // Ячейка по подписи «слова:обозначение».
  idx: (re) => { const c = __sp.cells().find(x => new RegExp(re).test(x.lab)); return c ? c.i : -1; },
  // Подпись при наведении на ключевую точку (x; y) взведённой кривой.
  armFirst: async () => { const t = snapTargets(); if (t.length && STATE.armedCurve !== t[0].name) armCurve(t[0].name); await __sp.wait(200); },
  hoverAt: async (x, y) => {
    const pts = keyTargets(armedPanelId()).filter(keyPointLit);
    const k = pts.findIndex(p => Math.abs(p.x - x) < 1e-3 && Math.abs(p.y - y) < 1e-3);
    if (k < 0) return { label: '(точки нет)', pin: null };
    const it = document.querySelectorAll('#chart g.crosses g.cross-item')[k];
    it.dispatchEvent(new PointerEvent('pointerenter'));
    await __sp.wait(80);
    const lab = it.querySelector('g.cross-label text');
    const pin = it.querySelector('g.cross-pin');
    const res = { label: lab ? lab.textContent : '(нет подписи)', pin: pin ? (pin.classList.contains('is-off') ? 'off' : 'on') : 'нет' };
    it.dispatchEvent(new PointerEvent('pointerleave'));
    STATE.hoverCross = null;
    return res;
  },
  // Щелчок по значку закрепки: добавилась ли своя точка.
  pinAt: async (x, y) => {
    const pts = keyTargets(armedPanelId()).filter(keyPointLit);
    const k = pts.findIndex(p => Math.abs(p.x - x) < 1e-3 && Math.abs(p.y - y) < 1e-3);
    if (k < 0) return -1;
    const it = document.querySelectorAll('#chart g.crosses g.cross-item')[k];
    it.dispatchEvent(new PointerEvent('pointerenter')); await __sp.wait(80);
    const before = (STATE.marks || []).length;
    const pin = it.querySelector('g.cross-pin');
    if (pin) pin.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await __sp.wait(150);
    return (STATE.marks || []).length - before;
  },
};`});

// Вписать ответ в ячейку и нажать Enter: вердикт, подсказка формата.
async function answer(re, text) {
  const i = await ev((re) => __sp.idx(re), re);
  if (i < 0) return { verdict: '(нет ячейки ' + re + ')' };
  const inp = page.locator('#ans-hero .ans-cell').nth(i).locator('.self-inp');
  if (!(await inp.count())) return { verdict: '(у ячейки нет поля)' };
  await ev(() => { const t = document.getElementById('toast') || document.querySelector('.toast'); if (t) t.textContent = ''; });
  await inp.fill(text);
  await inp.press('Enter');
  await page.waitForTimeout(250);
  return ev((i) => {
    const c = document.querySelectorAll('#ans-hero .ans-cell')[i];
    const pill = c ? c.querySelector('.self-pill') : null;
    const toastEl = document.querySelector('.toast, #toast');
    return { verdict: pill ? (pill.classList.contains('is-ok') ? '✓' : (pill.classList.contains('is-bad') ? '✗' : '—')) : '(нет)',
             toast: toastEl ? toastEl.textContent : '' };
  }, i);
}

const KEYS = ['m-graph', 'm-optimum', 'm-tangent', 'm-transform', 'm-minmax', 'm-constraint', 'sd'];

/* ── А. Открытых без поля ячеек с числами нет ──────────────────────── */
if (want('А')) {
  head('А. Режим прячет все главные числа');
  let openNum = 0;
  for (const key of KEYS) {
    const c = await ev(async (key) => { await __sp.open(key); return __sp.cells(); }, key);
    const open = c.filter(x => !x.field && /\d/.test(x.val));
    openNum += open.length;
    ok(key + ': ячеек ' + c.length + ', открытых без поля с числами ' + open.length, !open.length && c.length > 0,
      open.map(x => x.lab + ' = ' + x.val).join(' | '));
  }
  eq('открытых без поля главных ячеек с числами всего', openNum, 0);
}

/* ── Б. Разбор и сравнение ответа ──────────────────────────────────── */
if (want('Б')) {
  head('Б. Ответ списком, точкой и «нет»');
  await ev(async () => { await __sp.open('m-graph'); });
  const X = 'Пересекаетось:x', MIN = '^Локальныйминимум', MAX = '^Локальныймаксимум';
  for (const [g, w] of [['2; −2', '✓'], ['−2,0; 2', '✓'], ['2;-2', '✓'], ['−2', '✗'], ['−2; 2; 3', '✗']]) {
    eq('x²−4, ось x: «' + g + '»', (await answer(X, g)).verdict, w);
  }
  const r = await answer(X, 'абв');
  eq('x²−4, ось x: «абв» — вердикта нет', r.verdict, '—');
  ok('«абв» — подсказка формата', /Впишите числа через «;», точку как \(x; y\) или «нет»/.test(r.toast), r.toast);
  for (const [g, w] of [['(0; −4)', '✓'], ['(0;-4)', '✓'], ['(0; 4)', '✗']]) eq('x²−4, минимум: «' + g + '»', (await answer(MIN, g)).verdict, w);
  for (const [g, w] of [['нет', '✓'], ['Нет', '✓'], ['(0; 1)', '✗']]) eq('x²−4, максимум: «' + g + '»', (await answer(MAX, g)).verdict, w);
  // Ответ ячейки поменялся (другая формула) — её вердикт снимается.
  eq('x²−4, ось x: «2; −2» перед сменой формулы', (await answer(X, '2; −2')).verdict, '✓');
  await ev(async () => { STATE.curves[0].expr = 'x^2-9'; const r = compileFormula('x^2-9'); STATE.curves[0].compiled = r.compiled; redrawAll(); await __sp.wait(600); });
  eq('после смены формулы на x²−9: вердикт оси x снят', await ev(() => { const c = document.querySelectorAll('#ans-hero .ans-cell')[__sp.idx('Пересекаетось:x')]; const p = c.querySelector('.self-pill'); return p && p.classList.contains('is-ok') ? '✓' : '—'; }), '—');
  await ev(async () => { await __sp.open('m-graph', () => { STATE.curves = []; curveCounter = 0; addCurve('x^3-3*x'); renderGraphRows(); }); });
  eq('x³−3x, ось x: «0; 1,732; −1,732»', (await answer(X, '0; 1,732; −1,732')).verdict, '✓');
  eq('x³−3x, максимум: «(−1; 2)»', (await answer(MAX, '(−1; 2)')).verdict, '✓');
  eq('x³−3x, минимум: «(1; −2)»', (await answer(MIN, '(1; −2)')).verdict, '✓');
  await ev(async () => { await __sp.open('sd'); });
  eq('«Спрос и предложение», Q*: «50»', (await answer('Q', '50')).verdict, '✓');
  eq('«Спрос и предложение», Q*: «49»', (await answer('Q', '49')).verdict, '✗');
}

/* ── В. Координаты ключевых точек до верного ответа ────────────────── */
if (want('В')) {
  head('В. «(?; ?)» до верного ответа, закрепка');
  await ev(async () => { await __sp.open('m-graph'); await __sp.armFirst(); });
  let h = await ev(() => __sp.hoverAt(2, 0));
  eq('корень (2; 0) до ответа: подпись', h.label, '(?; ?)');
  eq('корень до ответа: закрепка', h.pin, 'off');
  eq('корень до ответа: щелчок по закрепке не добавляет точку', await ev(() => __sp.pinAt(2, 0)), 0);
  h = await ev(() => __sp.hoverAt(0, -4));
  eq('вершина (0; −4) до ответа', h.label, '(?; ?)');
  await answer('Пересекаетось:x', '2; −2');
  await ev(() => __sp.armFirst());
  eq('после «2; −2»: корень (−2; 0)', (await ev(() => __sp.hoverAt(-2, 0))).label, '(-2; 0)');
  h = await ev(() => __sp.hoverAt(2, 0));
  eq('после «2; −2»: корень (2; 0)', h.label, '(2; 0)');
  eq('после «2; −2»: закрепка доступна', h.pin, 'on');
  eq('после «2; −2»: закрепка добавляет точку', await ev(() => __sp.pinAt(2, 0)), 1);
  eq('вершина всё ещё скрыта', (await ev(() => __sp.hoverAt(0, -4))).label, '(?; ?)');
  await page.waitForTimeout(500);   // закрепка — шаг истории; вердикт обязан пережить его
  eq('закрепка не стёрла «✓» оси x', await ev(() => { const c = document.querySelectorAll('#ans-hero .ans-cell')[__sp.idx('Пересекаетось:x')]; return c.querySelector('.self-pill').classList.contains('is-ok') ? '✓' : '—'; }), '✓');
  await answer('Пересекаетось:y', '−4');
  await ev(() => __sp.armFirst());
  eq('после «−4» на оси y: вершина (0; −4)', (await ev(() => __sp.hoverAt(0, -4))).label, '(0; -4)');
  // Та же вершина — через верный минимум.
  await ev(async () => { await __sp.open('m-graph'); await __sp.armFirst(); });
  await answer('^Локальныйминимум', '(0; −4)');
  await ev(() => __sp.armFirst());
  eq('после верного минимума: вершина (0; −4)', (await ev(() => __sp.hoverAt(0, -4))).label, '(0; -4)');
  eq('…а корень всё ещё скрыт', (await ev(() => __sp.hoverAt(2, 0))).label, '(?; ?)');
  // «Показать» у ячейки открывает её точки.
  await ev(async () => { await __sp.open('m-graph'); await __sp.armFirst(); });
  await ev(() => { const c = document.querySelectorAll('#ans-hero .ans-cell')[__sp.idx('Пересекаетось:x')]; c.querySelector('.self-show').click(); });
  await page.waitForTimeout(250);
  await ev(() => __sp.armFirst());
  eq('после «Показать» у оси x: корень (2; 0)', (await ev(() => __sp.hoverAt(2, 0))).label, '(2; 0)');
  // «Показать всё».
  await ev(async () => { await __sp.open('m-graph'); await __sp.armFirst(); document.getElementById('self-showall').click(); await __sp.wait(250); await __sp.armFirst(); });
  eq('«Показать всё»: вершина', (await ev(() => __sp.hoverAt(0, -4))).label, '(0; -4)');
  eq('«Показать всё»: корень', (await ev(() => __sp.hoverAt(2, 0))).label, '(2; 0)');
  // Режим выключен — всё как без него.
  await ev(async () => { await __sp.open('m-graph'); setSelfMode(false); await __sp.wait(200); await __sp.armFirst(); });
  h = await ev(() => __sp.hoverAt(2, 0));
  eq('режим выключен: корень', h.label, '(2; 0)');
  eq('режим выключен: закрепка', h.pin, 'on');
  // «Спрос и предложение»: равновесие до верных Q* и P*.
  await ev(async () => { await __sp.open('sd'); const t = snapTargets().find(t => /спрос|^D/i.test(t.name)) || snapTargets()[0]; armCurve(t.name); await __sp.wait(200); });
  eq('равновесие (50; 50) до ответа', (await ev(() => __sp.hoverAt(50, 50))).label, '(?; ?)');
  await answer('Q', '50');
  await ev(async () => { if (!STATE.armedCurve) { const t = snapTargets()[0]; armCurve(t.name); } await __sp.wait(150); });
  eq('после верного Q*: равновесие всё ещё скрыто', (await ev(() => __sp.hoverAt(50, 50))).label, '(?; ?)');
  eq('…а проекция (50; 0) открыта', (await ev(() => __sp.hoverAt(50, 0))).label, '(50; 0)');
  await answer('P', '50');
  await ev(async () => { if (!STATE.armedCurve) { const t = snapTargets()[0]; armCurve(t.name); } await __sp.wait(150); });
  eq('после верных Q* и P*: равновесие', (await ev(() => __sp.hoverAt(50, 50))).label, '(50; 50)');
  await ev(() => setSelfMode(false));
}

/* ── Г. Раскладка в столбик ───────────────────────────────────────── */
if (want('Г')) {
  head('Г. Столбик: подпись, поле на всю ширину, вердикт под полем');
  const geo = () => ev(() => [...document.querySelectorAll('#ans-hero .ans-cell')].filter(c => c.querySelector('.self-inp')).map(c => {
    const r = c.getBoundingClientRect(), inp = c.querySelector('.self-inp').getBoundingClientRect();
    const lab = c.querySelector('.ans-lab'), chk = c.querySelector('.self-check').getBoundingClientRect();
    const acts = c.querySelector('.self-acts').getBoundingClientRect(), lr = lab.getBoundingClientRect();
    const cs = getComputedStyle(lab);
    return { h: r.height, w: inp.width, rowW: r.width, sameLine: Math.abs((inp.top + inp.bottom) - (chk.top + chk.bottom)) < 2,
      chkRight: chk.right <= r.right + 0.5, labAbove: lr.bottom <= inp.top + 0.5, actsBelow: acts.top >= inp.bottom - 0.5,
      ellipsis: cs.textOverflow === 'ellipsis' && lab.scrollWidth > lab.clientWidth };
  }));
  const widths = [];
  for (const key of KEYS) {
    await ev(async (key) => { await __sp.open(key); }, key);
    const g = await geo();
    g.forEach(x => widths.push(x.w));
    ok(key + ': поле не уже 60 % строки', g.length > 0 && g.every(x => x.w >= 0.6 * x.rowW), g.map(x => Math.round(x.w) + '/' + Math.round(x.rowW)).join(' '));
    ok(key + ': подпись над полем, «Проверить» в строке поля, вердикт и «Показать» под ним', g.every(x => x.labAbove && x.sameLine && x.chkRight && x.actsBelow));
    ok(key + ': подписей, обрезанных многоточием, нет', g.every(x => !x.ellipsis));
  }
  ok('у всех полей одна ширина (разброс ≤ 1 px)', Math.max(...widths) - Math.min(...widths) <= 1, Math.min(...widths).toFixed(1) + '…' + Math.max(...widths).toFixed(1));
  await ev(async () => { await __sp.open('m-graph'); });
  const h0 = (await geo()).map(x => x.h);
  await answer('Пересекаетось:x', '2; −2');
  await answer('Пересекаетось:y', '4');
  const h1 = (await geo()).map(x => x.h);
  ok('высота строки до и после вердикта одна (✓ и ✗)', h0.length && h0.every((h, i) => Math.abs(h - h1[i]) < 0.5), h0.map(Math.round).join(',') + ' → ' + h1.map(Math.round).join(','));
  const note = await ev(() => document.getElementById('self-note').textContent);
  eq('пояснение у математики', note, 'Впишите ответ: числа через «;», точку как (x; y) или «нет».');
  await ev(async () => { await __sp.open('sd'); });
  const note2 = await ev(() => document.getElementById('self-note').textContent);
  ok('пояснение у экономики — числом, своё', /^Впишите ответ числом/.test(note2), note2);
  await ev(() => setSelfMode(false));
}

/* ── Д. Режим не входит в историю ───────────────────────────────────── */
if (want('Д')) {
  head('Д. «Сначала сам» — вид, а не вход модели');
  const snap = () => ev(() => ({ undo: histOf().undo.length, redo: histOf().redo.length,
    undoOff: document.getElementById('btn-undo').disabled,
    pressed: document.getElementById('btn-self').getAttribute('aria-pressed'), on: SELF.on,
    body: document.body.classList.contains('self-on'),
    slider: (document.querySelector('.col-cond input[type=range]:not([disabled])') || {}).value }));
  const step = async (fn) => { await fn(); await page.waitForTimeout(700); };
  const freshSd = () => ev(async () => { if (SELF.on) setSelfMode(false); resetSceneMemory(); pickScene('sd'); closePicker(); redrawAll(); await __sp.wait(700); });
  await freshSd();
  const a0 = await snap();
  await step(() => page.click('#btn-self'));
  const a1 = await snap();
  ok('включение режима не делает шаг истории', a1.undo === a0.undo && a1.undoOff === a0.undoOff && a1.on && a1.pressed === 'true',
    JSON.stringify({ до: [a0.undo, a0.undoOff], после: [a1.undo, a1.undoOff, a1.pressed, a1.on] }));
  await step(() => page.click('#btn-self'));
  // Ползунок → режим → «Отменить»: откатывается ползунок, режим остаётся.
  const sl = page.locator('.col-cond input[type=range]:not([disabled])').first();
  await sl.focus();
  await step(async () => { await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); });
  const b0 = await snap();
  await step(() => page.click('#btn-self'));
  await step(() => page.click('#btn-undo'));
  const b1 = await snap();
  ok('«ползунок → режим → Отменить»: ползунок вернулся, режим остался',
    b1.slider === a0.slider && b0.slider !== a0.slider && b1.on && b1.pressed === 'true' && b1.body,
    JSON.stringify({ было: a0.slider, сдвинут: b0.slider, после: b1.slider, режим: [b1.pressed, b1.on, b1.body] }));
  // 20 шагов: кнопка и режим не расходятся.
  await freshSd();
  const STEPS = ['self', 'undo', 'self', 'redo', 'slider', 'self', 'undo', 'undo', 'model:taxes', 'self',
    'undo', 'redo', 'model:sd', 'self', 'slider', 'undo', 'self', 'redo', 'undo', 'self'];
  const bad20 = [];
  for (let i = 0; i < STEPS.length; i++) {
    const st = STEPS[i];
    if (st === 'self') await step(() => page.click('#btn-self'));
    else if (st === 'undo') await step(() => ev(() => { if (!document.getElementById('btn-undo').disabled) document.getElementById('btn-undo').click(); }));
    else if (st === 'redo') await step(() => ev(() => { if (!document.getElementById('btn-redo').disabled) document.getElementById('btn-redo').click(); }));
    else if (st === 'slider') { const s2 = page.locator('.col-cond input[type=range]:not([disabled])').first(); await s2.focus(); await step(() => page.keyboard.press('ArrowRight')); }
    else if (st.startsWith('model:')) await step(() => ev((k) => { pickScene(k); closePicker(); redrawAll(); }, st.slice(6)));
    const x = await snap();
    if ((x.pressed === 'true') !== x.on || x.body !== x.on) bad20.push((i + 1) + '. ' + st + ': кнопка ' + x.pressed + ', режим ' + x.on + ', body ' + x.body);
  }
  eq('20 шагов: расхождений кнопки и режима', bad20.length + (bad20.length ? ' — ' + bad20.slice(0, 3).join(' | ') : ''), '0');
  // Ссылка «Поделиться» с галочкой «Сначала сам».
  await ev(async () => { if (SELF.on) setSelfMode(false); await __sp.wait(300); });
  await page.click('#btn-share'); await page.waitForTimeout(400);
  await page.check('#share-self'); await page.waitForTimeout(400);
  const link = await ev(() => document.getElementById('share-url').value);
  await ev(() => closePop());
  ok('ссылка несёт режим (&self=1)', /[#&]self=1\b/.test(link), link.slice(-40));
  const p2 = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p2.goto(link, { waitUntil: 'networkidle' });
  await p2.waitForTimeout(1500);
  const r2 = await p2.evaluate(() => ({ on: SELF.on, pressed: document.getElementById('btn-self').getAttribute('aria-pressed'),
    undoOff: document.getElementById('btn-undo').disabled }));
  ok('по ссылке модель открыта в режиме: кнопка и режим согласны, «Отменить» выключена', r2.on && r2.pressed === 'true' && r2.undoOff, JSON.stringify(r2));
  await p2.context().close();
}

ok('ошибок страницы нет', !errs.length, errs.slice(0, 3).join(' | '));
console.log(`\n=== self_probe: ${total - bad} прошло, ${bad} провалено (всего ${total}) ===`);
await browser.close();
process.exit(bad ? 1 : 0);
