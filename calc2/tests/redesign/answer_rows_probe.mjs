/* «ОТВЕТ» СТРОКАМИ ПО ГРУППАМ (сессия 3, 10.2026; решение владельца 09.10, ADR 0144).

   Разделы (можно выбрать: --only Р,П):
     Р  строки по всем моделям на 1440 и 1280: значение не перенесено и не
        вылезает за колонку; подписей в три строки и больше нет; двухэтажные
        строки (подпись сверху, значение под ней) перечисляются по моделям;
     К  один видимый кегль у всех цифр значений колонки (разброс ≤ 0,5 px) и
        одно начертание; один кегль у всех подписей;
     П  паритет: тексты главных значений и «было · Δ» те же, что в эталоне
        answer_baseline_20261009.json (замер фазы −1), у sd плюс три строки
        «Излишки»; ни одна величина не показана в колонке дважды;
     Г  «Построение графиков», x^2-4 и x+2: две группы кривых по 4 строки и
        группа «Пересечения кривых» с одной строкой «f и g» → (−2; 0); (3; 5);
        строка об отрезке ответа под шапкой с живыми числами;
     Т  телефон 390: горизонтальной прокрутки нет ни в одной модели (вкладка
        «Ответ»); полоса главных чисел на 1000 px — по пункту на главную строку;
     В  левая колонка: кнопки кривых площади (по кнопке на кривую во всех
        моделях, радио-группа, ни одна не выбрана на старте, стрелки, «Посчитать
        площадь под D» → то же число, что прежде через список), сегмент «Под
        кривой | Между точками» вместо тумблера, строка «x от … до …» и
        «Вернуть по формуле» только при ручном отрезке.

   node calc2/tests/redesign/answer_rows_probe.mjs [--only Р,К] [--keys a,b]
   Код 0 — всё сошлось.                                                     */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const KEYS = (arg('keys', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);
const BASELINE = JSON.parse(fs.readFileSync(path.join(HERE, 'answer_baseline_20261009.json'), 'utf8'));

let bad = 0, total = 0;
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}
function eq0(label, got, want) { ok(label, got === want, 'ожидалось «' + want + '», получилось «' + got + '»'); }
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));
const norm = (s) => String(s == null ? '' : s).replace(/[\s   ​]+/g, '').replace(/[−–]/g, '-');

const browser = await chromium.launch();
async function openPage(w, h, opts) {
  const ctx = await browser.newContext(Object.assign({ viewport: { width: w, height: h }, reducedMotion: 'reduce', locale: 'ru-RU' }, opts || {}));
  await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  await page.addScriptTag({ content: INPAGE });
  return { ctx, page, errors };
}
const settle = async (page) => {
  await page.waitForTimeout(450);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(150);
};
const openKey = async (page, key, setup) => {
  await page.evaluate(([k, s]) => {
    if (typeof setSelfMode === 'function' && SELF.on) setSelfMode(false);
    resetSceneMemory(); pickScene(k); closePicker();
    if (s) (new Function(s))();
    redrawAll();
  }, [key, setup || '']);
  await settle(page);
};

/* В странице: замеры колонки. */
const INPAGE = `
window.__ar = {
  t: (el) => { if (!el) return ''; const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation, .ans-ctx').forEach(x => x.remove());
    return c.textContent.replace(/[\\s\\u00a0\\u202f\\u2009\\u200b]+/g, ' ').trim(); },
  vis: (el) => !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'),
  // Видимые строки колонки: главные (.ans-cell) и строки табло ниже.
  rows: () => {
    const out = [];
    document.querySelectorAll('#params-panel .ans-cell, #params-panel #sb-body .stat').forEach(r => {
      if (!__ar.vis(r)) return;
      const hero = r.classList.contains('ans-cell');
      const lab = hero ? r.querySelector('.ans-lab') : r.querySelector(':scope > span');
      const val = hero ? r.querySelector('.ans-line') : r.querySelector(':scope > b');
      if (!lab || !val) return;
      out.push({ r, hero, lab, val });
    });
    return out;
  },
  lineH: (el) => { const cs = getComputedStyle(el); const lh = parseFloat(cs.lineHeight); return isFinite(lh) ? lh : parseFloat(cs.fontSize) * 1.45; },
  layout: () => __ar.rows().map(({ r, hero, lab, val }) => {
    const rr = r.getBoundingClientRect(), lr = lab.getBoundingClientRect(), vr = val.getBoundingClientRect();
    const col = document.querySelector('#params-panel .side-scroll') || r.parentElement;
    const cr = col.getBoundingClientRect();
    const vlh = __ar.lineH(val);
    // Значение в одну строку: высота узла меньше полутора строк.
    const wrapped = vr.height > vlh * 1.6;
    const over = vr.right > Math.min(rr.right, cr.right) + 0.5 || vr.left < rr.left - 0.5;
    const labLines = Math.round(lr.height / __ar.lineH(lab));
    const twoStorey = vr.top >= lr.bottom - 2;
    return { hero, lab: __ar.t(lab).slice(0, 40), val: __ar.t(val).slice(0, 40), wrapped, over, labLines, twoStorey };
  }),
  // Цифры значений: самый внутренний узел с цифрой в собственном тексте.
  digits: () => {
    const out = [];
    __ar.rows().forEach(({ val }) => {
      const walk = document.createTreeWalker(val, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        if (!/\\d/.test(n.nodeValue)) continue;
        const el = n.parentElement;
        // Индексы и степени обозначений (MC₁, x²) — не числа ответа.
        if (!el || el.closest('.katex-mathml, .ans-was, .msupsub') || !__ar.vis(el)) continue;
        const cs = getComputedStyle(el);
        out.push({ fs: parseFloat(cs.fontSize), fam: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(),
          w: cs.fontWeight, st: cs.fontStyle, txt: n.nodeValue.slice(0, 12) });
      }
    });
    return out;
  },
  labelSizes: () => __ar.rows().map(({ lab }) => parseFloat(getComputedStyle(lab).fontSize)),
  cells: () => [...document.querySelectorAll('#ans-hero .ans-cell')].map(c => ({
    src: c.dataset.src, val: __ar.t(c.querySelector('.ans-val')), was: __ar.t(c.querySelector('.ans-was')),
    lab: __ar.t(c.querySelector('.ans-lab')), not: __ar.t(c.querySelector('.ans-not')) })),
  // Повторы: строка-источник главной величины или источник заголовка видна в
  // табло; две видимые строки колонки с одной подписью и одним значением.
  dups: () => {
    const out = [];
    document.querySelectorAll('#sb-body .stat.is-hero, #sb-body .stat[data-ans-head]').forEach(s => { if (__ar.vis(s)) out.push('видна строка-источник: ' + __ar.t(s)); });
    /* Одна подпись и одно значение — одна величина. Исключение — разные
       подразделы одного блока («Покупатели по группам: вместе Q» и «Продавцы
       по группам: вместе Q» у сложения — сумма спроса и сумма предложения). */
    const seen = new Map();
    __ar.rows().forEach(({ r, lab, val }) => {
      const k = __ar.t(lab).replace(/\\s+/g, '') + '=' + __ar.t(val).replace(/\\s+/g, '');
      const blk = r.closest('[id^="info-"], #sec-eq, #ans-hero');
      let sub = r.previousElementSibling; while (sub && sub.classList.contains('stat')) sub = sub.previousElementSibling;
      const where = { blk: blk ? blk.id : '', sub: sub ? __ar.t(sub) : '' };
      const prev = seen.get(k);
      if (prev && !(prev.blk === where.blk && prev.blk !== 'ans-hero' && prev.sub !== where.sub)) out.push('дважды: ' + k);
      if (!prev) seen.set(k, where);
    });
    return out;
  },
  groups: () => [...document.querySelectorAll('#ans-hero .ans-group')].map(g => ({
    head: __ar.t(g.querySelector('.ans-ghead')), dot: !!g.querySelector('.ans-gdot'),
    rows: [...g.querySelectorAll('.ans-cell')].map(c => ({ lab: __ar.t(c.querySelector('.ans-lab')), val: __ar.t(c.querySelector('.ans-val')) })) })),
  hscroll: () => {
    const W = window.innerWidth;
    const bad = [];
    document.querySelectorAll('#params-panel *').forEach(el => {
      if (!__ar.vis(el)) return;
      const r = el.getBoundingClientRect();
      if (r.width && r.right > W + 0.5) {
        // Прокручиваемый предок прячет вылет — это не прокрутка страницы.
        for (let p = el.parentElement; p; p = p.parentElement) {
          const o = getComputedStyle(p).overflowX;
          if ((o === 'auto' || o === 'scroll' || o === 'hidden') && p.getBoundingClientRect().right <= W + 0.5) return;
        }
        bad.push((el.id ? '#' + el.id : el.className || el.tagName) + ' ' + Math.round(r.right));
      }
    });
    return { doc: document.scrollingElement.scrollWidth - W, bad: bad.slice(0, 5), n: bad.length };
  },
};`;

const MODELS_ALL = Object.keys(BASELINE);
const MODELS = KEYS.length ? MODELS_ALL.filter(k => KEYS.includes(k)) : MODELS_ALL;

/* ── Р, К, П: все модели на 1440 и 1280 ─────────────────────────────── */
if (want('Р') || want('К') || want('П')) {
  for (const W of [1440, 1280]) {
    const { ctx, page, errors } = await openPage(W, 900);
    head('Ширина ' + W + ': ' + MODELS.length + ' моделей');
    const wrapped = [], over = [], tall = [], two = [], digs = [], labs = [], par = [], dups = [];
    for (const key of MODELS) {
      await openKey(page, key);
      const L = await page.evaluate(() => __ar.layout());
      L.forEach(x => {
        if (x.wrapped) wrapped.push(key + ': ' + x.lab + ' → ' + x.val);
        if (x.over) over.push(key + ': ' + x.lab + ' → ' + x.val);
        if (x.labLines >= 3) tall.push(key + ': «' + x.lab + '» в ' + x.labLines + ' строки');
        if (x.twoStorey) two.push(key + ': ' + x.lab);
      });
      (await page.evaluate(() => __ar.digits())).forEach(d => digs.push(Object.assign({ key }, d)));
      (await page.evaluate(() => __ar.labelSizes())).forEach(s => labs.push({ key, s }));
      if (W === 1440) {
        const cells = await page.evaluate(() => __ar.cells());
        const base = BASELINE[key] || [];
        const extra = key === 'sd' ? 3 : 0;
        if (cells.length !== base.length + extra) par.push(key + ': главных строк ' + cells.length + ', в эталоне ' + base.length + (extra ? ' + ' + extra : ''));
        base.forEach((b, i) => {
          const c = cells[i];
          if (!c) return;
          if (c.src !== b.src) par.push(key + ': строка ' + i + ' источник ' + c.src + ' ≠ ' + b.src);
          /* Без пробелов, как parity_quick: табло само решает, набрать список
             формулой («−2,562;1,562») или текстом («−2,562; 1,562»), по ширине
             подписи (restatWide). Строгую сверку строки с её источником в табло
             держит answer_probe.mjs. */
          if (norm(c.val) !== norm(b.val)) par.push(key + ': «' + b.cap + '» ' + b.val + ' → ' + c.val);
          if (norm(c.was) !== norm(b.was)) par.push(key + ': «' + b.cap + '» было ' + b.was + ' → ' + c.was);
        });
        (await page.evaluate(() => __ar.dups())).forEach(d => dups.push(key + ': ' + d));
      }
    }
    if (want('Р')) {
      ok(W + ': значение перенесено — 0', !wrapped.length, wrapped.slice(0, 6).join(' | '));
      ok(W + ': значение вылезает за колонку — 0', !over.length, over.slice(0, 6).join(' | '));
      ok(W + ': подписей в 3 строки и больше — 0', !tall.length, tall.slice(0, 6).join(' | '));
      console.log('  ИНФО ' + W + ': двухэтажных строк ' + two.length + (two.length ? ' — ' + two.join(' | ') : ''));
    }
    if (want('К')) {
      const sizes = digs.map(d => d.fs);
      const lo = Math.min(...sizes), hi = Math.max(...sizes);
      const odd = digs.filter(d => Math.abs(d.fs - 16) > 0.5);
      const oddBy = new Map(); odd.forEach(d => oddBy.set(d.fs + '/' + d.w, (oddBy.get(d.fs + '/' + d.w) || []).concat(d.key + ' «' + d.txt + '»')));
      ok(W + ': кегль цифр значений один (разброс ≤ 0,5 px)', hi - lo <= 0.5,
        lo + '…' + hi + ' px' + (odd.length ? '; не 16: ' + [...oddBy].map(([k, v]) => k + ' ×' + v.length + ' (' + v.slice(0, 4).join(', ') + ')').join(' | ') : ''));
      const faces = new Map();
      digs.forEach(d => { const k = d.fam + '/' + d.w + '/' + d.st; faces.set(k, (faces.get(k) || []).concat(d.key + ' «' + d.txt + '»')); });
      ok(W + ': начертание цифр значений одно', faces.size === 1, [...faces].map(([k, v]) => k + ' (' + v.length + ': ' + v.slice(0, 3).join(', ') + ')').join(' | '));
      const ls = labs.map(x => x.s);
      ok(W + ': кегль подписей один', Math.max(...ls) - Math.min(...ls) <= 0.5, Math.min(...ls) + '…' + Math.max(...ls) + ' px');
    }
    if (want('П') && W === 1440) {
      ok('паритет главных значений и «было · Δ» с эталоном (фаза −1) — 0 расхождений', !par.length, par.slice(0, 8).join(' | '));
      ok('ни одна величина не показана дважды — 0', !dups.length, dups.slice(0, 6).join(' | '));
      await openKey(page, 'sd');
      const g = await page.evaluate(() => __ar.groups());
      const surplus = g.find(x => x.head === 'Излишки');
      ok('sd: группа «Излишки» — CS, PS, SW словами',
        !!surplus && surplus.rows.map(r => r.lab).join('|') === 'Излишек потребителя|Излишек производителя|Общественное благосостояние',
        JSON.stringify(g.map(x => [x.head, x.rows.map(r => r.lab + ' ' + r.val)])));
    }
    ok(W + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

/* ── Г: две кривые ─────────────────────────────────────────────────── */
if (want('Г')) {
  head('Г. «Построение графиков»: x^2-4 и x+2');
  const { ctx, page } = await openPage(1440, 900);
  await openKey(page, 'm-graph', "STATE.curves = []; curveCounter = 0; ['x^2-4', 'x+2'].forEach(e => addCurve(e)); renderGraphRows();");
  const g = await page.evaluate(() => __ar.groups());
  const desc = g.map(x => (x.dot ? '● ' : '') + x.head + ' [' + x.rows.length + ']').join(' | ');
  const fg = g.filter(x => x.dot);
  ok('две группы кривых с точкой цвета и записью', fg.length === 2 && /^f\(x\)=x2?.*4$/.test(fg[0].head.replace(/\s+/g, '')) && /^g\(x\)=x\+2$/.test(fg[1].head.replace(/\s+/g, '')), desc);
  ok('по 4 строки в группе кривой', fg.length === 2 && fg.every(x => x.rows.length === 4), desc);
  ok('подписи без хвоста «, кривая f»', fg.every(x => x.rows.every(r => !/кривая/.test(r.lab))), fg.map(x => x.rows.map(r => r.lab).join(', ')).join(' | '));
  const cr = g.find(x => x.head === 'Пересечения кривых');
  ok('группа «Пересечения кривых»: одна строка «f и g» → (−2; 0); (3; 5)',
    !!cr && cr.rows.length === 1 && norm(cr.rows[0].lab) === 'fиg' && norm(cr.rows[0].val) === '(-2;0);(3;5)',
    cr ? JSON.stringify(cr.rows) : 'группы нет');
  ok('значения кривой f: −2; 2 · −4 · нет · (0; −4)', fg[0] && fg[0].rows.map(r => norm(r.val)).join('|') === '-2;2|-4|нет|(0;-4)', fg[0] && fg[0].rows.map(r => r.val).join(' | '));
  const note = await page.evaluate(() => __ar.t(document.getElementById('ans-seg-note')));
  ok('строка об отрезке: «Ищем на отрезке x от −5 до 5…»', norm(note) === norm('Ищем на отрезке x от −5 до 5. Масштаб графика на ответ не влияет.'), note);
  await page.evaluate(() => { STATE.ansHand = true; STATE.ansA = -3; STATE.ansB = 4; redrawAll(); });
  await settle(page);
  const note2 = await page.evaluate(() => __ar.t(document.getElementById('ans-seg-note')));
  ok('ручной отрезок −3…4 — числа строки живые', /от-3до4\./.test(norm(note2)), note2);
  await openKey(page, 'sd');
  const hid = await page.evaluate(() => document.getElementById('ans-seg-note').hidden);
  ok('у экономики строки об отрезке нет', hid === true);
  await openKey(page, 'm-constraint');
  const hid2 = await page.evaluate(() => document.getElementById('ans-seg-note').hidden);
  ok('у «С ограничением» строки об отрезке нет', hid2 === true);
  await ctx.close();
}

/* ── Т: телефон и полоса ─────────────────────────────────────────────── */
if (want('Т')) {
  head('Т. Телефон 390 и полоса главных чисел на 1000');
  const { ctx, page } = await openPage(390, 844, { isMobile: true, hasTouch: true });
  const hs = [];
  for (const key of MODELS) {
    await openKey(page, key);
    await page.click('#ph-tabs .ph-tab[data-tab="ans"]').catch(() => null);
    await page.waitForTimeout(200);
    const r = await page.evaluate(() => __ar.hscroll());
    if (r.doc > 0.5 || r.n) hs.push(key + ': страница +' + r.doc + ', вылетов ' + r.n + ' ' + r.bad.join(', '));
    await page.click('#ph-tabs .ph-tab[data-tab="cond"]').catch(() => null);
  }
  ok('390: горизонтальной прокрутки в «Ответе» нет ни в одной модели', !hs.length, hs.slice(0, 6).join(' | '));
  await ctx.close();
  const p2 = await openPage(1000, 800);
  const miss = [];
  for (const key of MODELS) {
    await openKey(p2.page, key);
    const r = await p2.page.evaluate(() => ({ strip: document.querySelectorAll('#ans-strip > span').length,
      cells: document.querySelectorAll('#ans-hero .ans-cell').length,
      shown: getComputedStyle(document.getElementById('ans-strip')).display !== 'none' }));
    if (r.strip !== r.cells) miss.push(key + ': пунктов ' + r.strip + ', строк ' + r.cells);
    if (!r.shown && r.cells) miss.push(key + ': полоса не показана');
  }
  ok('1000: в полосе по пункту на главную строку', !miss.length, miss.slice(0, 6).join(' | '));
  await p2.ctx.close();
}

/* ── В: левая колонка ──────────────────────────────────────────────── */
if (want('В')) {
  head('В. Кнопки кривых, сегмент, отрезок ответа');
  const { ctx, page, errors } = await openPage(1440, 900);
  const miss = [];
  for (const key of MODELS) {
    await openKey(page, key);
    const r = await page.evaluate(() => ({
      want: areaTargets().map(t => t.name),
      got: [...document.querySelectorAll('#ac-pick-btns .ac-cbtn')].map(b => b.dataset.name),
      checked: document.querySelectorAll('#ac-pick-btns [aria-checked="true"]').length,
      roles: [...document.querySelectorAll('#ac-pick-btns .ac-cbtn')].every(b => b.getAttribute('role') === 'radio'),
      sel: document.getElementById('ac-pick').value }));
    if (r.want.join('|') !== r.got.join('|')) miss.push(key + ': кривых ' + r.want.join(',') + ', кнопок ' + r.got.join(','));
    if (r.checked || r.sel) miss.push(key + ': на старте выбрана ' + r.sel);
    if (!r.roles) miss.push(key + ': у кнопки нет role=radio');
  }
  ok('кнопок столько же, сколько кривых, во всех моделях; на старте ни одна не выбрана', !miss.length, miss.slice(0, 5).join(' | '));
  await openKey(page, 'sd');
  const t0 = await page.evaluate(() => ({ text: __ar.t(document.getElementById('ac-calc')), dis: document.getElementById('ac-calc').disabled,
    group: document.getElementById('ac-pick-btns').getAttribute('role'), selHidden: document.getElementById('ac-pick').hidden,
    upgraded: !!document.querySelector('#ac-pane-curve .sel-btn') }));
  ok('группа кнопок — radiogroup, список спрятан и своей кнопки поверх нет', t0.group === 'radiogroup' && t0.selHidden && !t0.upgraded, JSON.stringify(t0));
  eq0('кнопка расчёта до выбора', t0.text + (t0.dis ? ' (выкл.)' : ''), 'Сначала выберите кривую (выкл.)');
  await page.click('#ac-pick-btns .ac-cbtn[data-name="D"]');
  await page.waitForTimeout(250);
  const t1 = await page.evaluate(() => ({ text: __ar.t(document.getElementById('ac-calc')), dis: document.getElementById('ac-calc').disabled,
    sel: document.getElementById('ac-pick').value, checked: [...document.querySelectorAll('#ac-pick-btns [aria-checked="true"]')].map(b => b.dataset.name) }));
  ok('щелчок по D: выбрана D, список = D, «Посчитать площадь под D»', t1.sel === 'D' && t1.checked.join() === 'D' && t1.text === 'Посчитать площадь под D' && !t1.dis, JSON.stringify(t1));
  await page.click('#ac-calc');
  await page.waitForTimeout(300);
  const area = await page.evaluate(() => { const a = (STATE.areaCalcList || [])[0]; return a ? a.value : null; });
  ok('площадь под D — 5000, как через список до сессии', Math.abs(area - 5000) < 1e-9, String(area));
  await page.focus('#ac-pick-btns .ac-cbtn[data-name="D"]');
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(200);
  const t2 = await page.evaluate(() => ({ sel: document.getElementById('ac-pick').value, focus: document.activeElement && document.activeElement.dataset.name }));
  ok('стрелка вправо: выбрана и в фокусе S', t2.sel === 'S' && t2.focus === 'S', JSON.stringify(t2));
  const seg = await page.evaluate(() => ({ role: document.getElementById('ac-mode').getAttribute('role'),
    shown: getComputedStyle(document.getElementById('ac-mode')).display !== 'none',
    tgl: !!document.querySelector('#areascalc-body > .tgl-sw, #ac-mode + .tgl-sw') || [...document.querySelectorAll('.tgl-sw')].some(t => /Под кривой/.test(t.textContent)),
    c: document.getElementById('ac-curve').getAttribute('aria-checked') }));
  ok('сегмент «Под кривой | Между точками» вместо тумблера', seg.role === 'radiogroup' && seg.shown && !seg.tgl && seg.c === 'true', JSON.stringify(seg));
  await page.click('#ac-poly');
  await page.waitForTimeout(200);
  const seg2 = await page.evaluate(() => [document.getElementById('ac-curve').getAttribute('aria-checked'), document.getElementById('ac-poly').getAttribute('aria-checked'), __ar.t(document.getElementById('ac-calc'))]);
  ok('«Между точками»: отметка переехала, кнопка «Посчитать площадь»', seg2.join('|') === 'false|true|Посчитать площадь', seg2.join(' | '));
  await page.click('#ac-curve');
  await openKey(page, 'm-graph');
  const a0 = await page.evaluate(() => ({ lab: __ar.t(document.querySelector('#ans-seg-row label')), row: __ar.t(document.querySelector('#ans-seg-row .opt-range-row')),
    back: !document.getElementById('ans-seg-auto').hidden }));
  ok('«Ответ ищем на отрезке», строка «x от … до …», «Вернуть по формуле» спрятана', a0.lab === 'Ответ ищем на отрезке' && /^x\s*от/.test(a0.row) && !a0.back, JSON.stringify(a0));
  await page.evaluate(() => { STATE.ansHand = true; STATE.ansA = -3; STATE.ansB = 4; redrawAll(); });
  await settle(page);
  const a1 = await page.evaluate(() => { const b = document.getElementById('ans-seg-auto'); const r = b.getBoundingClientRect(), row = document.querySelector('#ans-seg-row .opt-range-row').getBoundingClientRect(); return { back: !b.hidden && !!r.width, below: r.top >= row.bottom - 0.5 }; });
  ok('ручной отрезок: «Вернуть по формуле» видна, отдельной строкой', a1.back && a1.below, JSON.stringify(a1));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

await browser.close();
console.log(bad ? '\nНЕ СОШЛОСЬ: ' + bad + ' из ' + total : '\nВСЁ СОШЛОСЬ: ' + total + ' проверок');
process.exit(bad ? 1 : 0);
