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
    // Включение режима — шаг истории (aria-pressed кнопки в форме): через 300 мс
    // затишья она рассылает calc2:history и снимает вердикты. Ждём его.
    setSelfMode(true); await __sp.wait(600);
  },
  cells: () => [...document.querySelectorAll('#ans-hero .ans-cell')].map((c, i) => ({
    i, lab: __sp.t(c.querySelector('.ans-lab')) + (c.querySelector('.ans-not') ? ':' + __sp.t(c.querySelector('.ans-not')) : ''),
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

ok('ошибок страницы нет', !errs.length, errs.slice(0, 3).join(' | '));
console.log(`\n=== self_probe: ${total - bad} прошло, ${bad} провалено (всего ${total}) ===`);
await browser.close();
process.exit(bad ? 1 : 0);
