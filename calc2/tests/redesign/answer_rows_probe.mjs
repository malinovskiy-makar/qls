/* «ОТВЕТ» СТРОКАМИ ПО ГРУППАМ (сессия 3, 10.2026; решение владельца 09.10, ADR 0144).

   Разделы (можно выбрать: --only Р,П):
     Р  строки по всем моделям на 1440 и 1280: значение не перенесено и не
        вылезает за колонку; подписей в три строки и больше нет; двухэтажные
        строки (подпись сверху, значение под ней) перечисляются по моделям;
     К  две ступени кегля цифр значений (с 14.10, README пакета calc2_panels_20261014, 5): главные
        20 px, прочие 16 px (разброс ≤ 0,5 px); одно начертание; один кегль у всех подписей;
     П  паритет: тексты главных значений и «было · Δ» те же, что в эталоне
        answer_baseline_20261009.json (замер фазы −1), у sd плюс три строки
        «Излишки»; ни одна величина не показана в колонке дважды;
     Г  «Построение графиков», x^2-4 и x+2: две группы кривых по 4 строки и
        группа «Пересечения кривых» с одной строкой «f и g» → (−2; 0); (3; 5);
        строка об отрезке ответа под шапкой с живыми числами (вторая фраза — в «Разборе»);
     Т  телефон 390: горизонтальной прокрутки нет ни в одной модели (вкладка
        «Ответ»); полоса главных чисел на 1000 px — по пункту на главную строку;
     В  левая колонка: кнопки кривых площади (по кнопке на кривую во всех
        моделях, радио-группа, ни одна не выбрана на старте, стрелки, «Посчитать
        площадь под D» → то же число, что прежде через список), сегмент «Под
        кривой | Между точками» вместо тумблера, строка «x от … до …» и
        «Вернуть по формуле» только при ручном отрезке;
     Э  окно «Скачать»: заголовок и имя файла — по текущей модели; правка
        заголовка помнится в своей модели и не идёт в историю; подсказка TeX
        честная; в начале .tex — две строки о сборке и проверка движка.
   Часть 3 (13.10.2026, полировка):
     Ж  изменение «50 − 10» вместо «было 50 · −10» (taxes), нигде нет «было»;
     Ч  разряды через пробел: sd и ceil «1 250», обход моделей — нет 4+ цифр подряд;
     И  «Излишек потребителя / производителя»: код calc2 и экран всех моделей;
     Н  три точки в строке: перенос только между точками, ничего за колонкой,
        кнопка чата не накрывает строк (1280, 1440, 390);
     З  заголовки групп «Ответа» разные (costs и обход моделей);
     С  после ссылки и перезагрузки нет сырой ячейки (через 0,5 и 3 с);
     Б  «Кто несёт налог»: «10 (50 %)» без «·».

   node calc2/tests/redesign/answer_rows_probe.mjs [--only Р,К] [--keys a,b]
   Код 0 — всё сошлось.                                                     */
import { chromium } from 'playwright';
import { keepAnswerOpen, answerShown } from '../answer_open.mjs';
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
/* Эталон 09.10 записан строкой «было 50 · −10»; с решения 13.10 (Notion …81a2…) та же
   разность пишется «50 − 10»: число до и изменение со знаком. */
const wasNew = (w) => {
  const m = /^было\s+(\S+)(?:\s+·\s+([+−-])(\S+))?$/.exec(String(w || '').trim());
  if (!m) return w;
  return m[2] ? m[1] + ' ' + (m[2] === '+' ? '+' : '−') + ' ' + m[3] : m[1];
};
const norm = (s) => String(s == null ? '' : s).replace(/[\s   ​]+/g, '').replace(/[−–]/g, '-');

const browser = await chromium.launch();
/* «Ответ» от 1240 px закрыт по умолчанию (решение 14.10, Notion …81de…, ADR 0150): прибор открывает его,
   как у человека, однажды открывшего «Ответ»; первая проверка — колонка видна (answer_open.mjs). */
keepAnswerOpen(browser);
let _preDone = false;
async function openPage(w, h, opts, br) {
  const ctx = await (br || browser).newContext(Object.assign({ viewport: { width: w, height: h }, reducedMotion: 'reduce', locale: 'ru-RU' }, opts || {}));
  await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  await page.addScriptTag({ content: INPAGE });
  if (w >= 1240 && !_preDone) { _preDone = true; ok('предусловие: «Ответ» открыт (#params-panel > .side-inner видна)', await answerShown(page)); }
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
        out.push({ hero: !!el.closest('#ans-hero'), fs: parseFloat(cs.fontSize), fam: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(),
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
        /* Естественная монополия (карточка Notion …8121…, 14.10): строка табло «(ATC(Qm); прибыль) = (40; 800)»
           в «Ответе» — две ячейки info-nat#2.1, #2.2. Для сверки с эталоном склеиваем их обратно в пару. */
        const cells = (await page.evaluate(() => __ar.cells())).reduce((acc, c) => {
          const m = /^(.+#\d+)\.(\d+)$/.exec(c.src || '');
          if (!m) { acc.push(c); return acc; }
          const last = acc[acc.length - 1];
          if (m[2] === '1' || !last || last.src !== m[1]) acc.push(Object.assign({}, c, { src: m[1], val: '(' + c.val + ';' }));
          else last.val += c.val;
          return acc;
        }, []).map(c => /;$/.test(c.val) ? c : (/^\(/.test(c.val) && !/\)$/.test(c.val) ? Object.assign(c, { val: c.val + ')' }) : c));
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
          /* Точки Слуцкого A, B, C — запись «(50; 25)» вместо «50 / 25» по карточке …81fd… (тихие панели, сессия 7,
             А3.1): у них сверяются числа по порядку, как REFORMATTED в parity_quick.mjs. */
          const numsOf = (v) => (norm(v).match(/-?\d+(?:,\d+)?/g) || []).join('|');
          if (key === 'cons-slutsky' && /^[ABC]:/.test(String(b.cap).trim())) { if (numsOf(c.val) !== numsOf(b.val)) par.push(key + ': «' + b.cap + '» числа ' + b.val + ' → ' + c.val); }
          else if (norm(c.val) !== norm(b.val)) par.push(key + ': «' + b.cap + '» ' + b.val + ' → ' + c.val);
          if (norm(c.was) !== norm(wasNew(b.was))) par.push(key + ': «' + b.cap + '» было ' + b.was + ' → ' + c.was);
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
      /* Две ступени значений (тихие панели 14.10, README пакета calc2_panels_20261014, раздел 5): главные
         числа (#ans-hero) — 20 px, остальные строки «Ответа» и табло — 16 px; было «один кегль у всех». */
      const tier = (want) => {
        const ds = digs.filter(d => d.hero === (want === 20));
        const sizes = ds.map(d => d.fs);
        const lo = Math.min(...sizes), hi = Math.max(...sizes);
        const odd = ds.filter(d => Math.abs(d.fs - want) > 0.5);
        const oddBy = new Map(); odd.forEach(d => oddBy.set(d.fs + '/' + d.w, (oddBy.get(d.fs + '/' + d.w) || []).concat(d.key + ' «' + d.txt + '»')));
        ok(W + ': кегль цифр ' + (want === 20 ? 'главных чисел 20' : 'остальных значений 16') + ' px (разброс ≤ 0,5 px)', ds.length > 0 && hi - lo <= 0.5 && !odd.length,
          lo + '…' + hi + ' px' + (odd.length ? '; не ' + want + ': ' + [...oddBy].map(([k, v]) => k + ' ×' + v.length + ' (' + v.slice(0, 4).join(', ') + ')').join(' | ') : ''));
      };
      tier(20); tier(16);
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
  // По ВСЕМ строкам «Ответа», а не только в группах кривых: без групп (поломка 2
  // зубастости) проверка иначе проходила вхолостую.
  const allLabs = g.flatMap(x => x.rows.map(r => r.lab));
  ok('подписи без хвоста «, кривая f»', allLabs.length > 0 && allLabs.every(l => !/кривая/.test(l)), allLabs.filter(l => /кривая/.test(l)).join(' | '));
  const cr = g.find(x => x.head === 'Пересечения кривых');
  ok('группа «Пересечения кривых»: одна строка «f и g» → (−2; 0); (3; 5)',
    !!cr && cr.rows.length === 1 && norm(cr.rows[0].lab) === 'fиg' && norm(cr.rows[0].val) === '(-2;0);(3;5)',
    cr ? JSON.stringify(cr.rows) : 'группы нет');
  ok('значения кривой f: −2; 2 · −4 · нет · (0; −4)', fg[0] && fg[0].rows.map(r => norm(r.val)).join('|') === '-2;2|-4|нет|(0;-4)', fg[0] && fg[0].rows.map(r => r.val).join(' | '));
  const note = await page.evaluate(() => __ar.t(document.getElementById('ans-seg-note')));
  // Вторая фраза («Масштаб графика на ответ не влияет») — пояснение, она в «Разборе» (тихие панели 14.10, README 5).
  ok('строка об отрезке: «Ищем на отрезке x от −5 до 5.»', norm(note) === norm('Ищем на отрезке x от −5 до 5.'), note);
  const exScale = await page.evaluate(() => (document.getElementById('ex-body').textContent || '').includes('Масштаб графика на ответ не влияет.'));
  ok('вторая фраза строки об отрезке — в «Разборе»', exScale);
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
  /* С 13.10 (ADR 0148) кнопки кривых живут в панели режима «Точки и площади» и видны,
     когда открыто построение «+ Под кривой»: человек идёт туда тем же путём. */
  await page.click('#tool-pts');
  await page.click('#ac-curve');
  await settle(page);
  const t0 = await page.evaluate(() => ({ text: __ar.t(document.getElementById('ac-calc')), dis: document.getElementById('ac-calc').disabled,
    group: document.getElementById('ac-pick-btns').getAttribute('role'), selHidden: document.getElementById('ac-pick').hidden,
    upgraded: !!document.querySelector('#ac-pane-curve .sel-btn') }));
  ok('группа кнопок — radiogroup, список спрятан и своей кнопки поверх нет', t0.group === 'radiogroup' && t0.selHidden && !t0.upgraded, JSON.stringify(t0));
  eq0('кнопка расчёта до выбора', t0.text + (t0.dis ? ' (выкл.)' : ''), 'Сначала выберите кривую (выкл.)');
  // Кнопка спрятана (поломка 4 зубастости) — понятный провал, а не падение прибора.
  const dVis = await page.evaluate(() => { const b = document.querySelector('#ac-pick-btns .ac-cbtn[data-name="D"]'); return !!(b && b.getClientRects().length); });
  ok('кнопка «D» видна', dVis);
  if (dVis) await page.click('#ac-pick-btns .ac-cbtn[data-name="D"]');
  else await page.evaluate(() => { const b = document.querySelector('#ac-pick-btns .ac-cbtn[data-name="D"]'); if (b) b.click(); });
  await page.waitForTimeout(250);
  const t1 = await page.evaluate(() => ({ text: __ar.t(document.getElementById('ac-calc')), dis: document.getElementById('ac-calc').disabled,
    sel: document.getElementById('ac-pick').value, checked: [...document.querySelectorAll('#ac-pick-btns [aria-checked="true"]')].map(b => b.dataset.name) }));
  ok('щелчок по D: выбрана D, список = D, «Посчитать площадь под D»', t1.sel === 'D' && t1.checked.join() === 'D' && t1.text === 'Посчитать площадь под D' && !t1.dis, JSON.stringify(t1));
  await page.click('#ac-calc');
  await page.waitForTimeout(300);
  const area = await page.evaluate(() => { const a = (STATE.areaCalcList || [])[0]; return a ? a.value : null; });
  ok('площадь под D — 5000, как через список до сессии', Math.abs(area - 5000) < 1e-9, String(area));
  await page.evaluate(() => { const b = document.querySelector('#ac-pick-btns .ac-cbtn[data-name="D"]'); if (b) b.focus(); });
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

/* ── Э: окно «Скачать» ─────────────────────────────────────────────── */
if (want('Э')) {
  head('Э. Окно «Скачать»: заголовок по модели, подсказка TeX, начало .tex');
  const { ctx, page, errors } = await openPage(1440, 900);
  const state = () => page.evaluate(() => ({ title: document.getElementById('exp-title').value, file: exportBaseName(),
    note: document.getElementById('exp-fmt-note').textContent, undo: document.getElementById('btn-undo').disabled }));
  const openTex = async () => { await page.evaluate(() => openExport()); await page.waitForTimeout(400); await page.click('#exp-fmt [data-fmt="tex"]'); await page.waitForTimeout(200); };
  const close = async () => { await page.evaluate(() => closeExport()); await page.waitForTimeout(150); };
  await openKey(page, 'm-graph');
  await openTex();
  const s0 = await state();
  eq0('«Построение графиков»: заголовок окна', s0.title, 'Построение графиков');
  await close();
  await page.evaluate(() => { pickScene('trade'); closePicker(); redrawAll(); });
  await settle(page);
  await openTex();
  const s1 = await state();
  eq0('после смены модели: заголовок «КТВ. Одна страна»', s1.title, 'КТВ. Одна страна');
  eq0('…и имя файла', s1.file + '.tex', 'КТВ. Одна страна.tex');
  eq0('подсказка TeX', s1.note.replace(/\u00a0/g, ' '), 'Готовый документ LaTeX. Собирайте через pdfLaTeX, в Overleaf: Menu → Compiler → pdfLaTeX.');
  ok('подсказка TeX без длинного тире', !/—/.test(s1.note));
  const tex = await page.evaluate(() => buildTex(document.getElementById('exp-title').value, ''));
  const lines = tex.split('\n');
  ok('.tex: первые две строки — чем собирать и имя файла', /^% Собирайте через pdfLaTeX; в Overleaf: Menu > Compiler > pdfLaTeX\.$/.test(lines[0]) && /^% Имя файла должно кончаться на \.tex/.test(lines[1]), lines.slice(0, 2).join(' | '));
  ok('.tex: проверка движка сразу после \\documentclass', lines.indexOf('\\usepackage{iftex}') === lines.findIndex(l => /^\\documentclass/.test(l)) + 1
    && lines.some(l => /^\\ifPDFTeX\\else\\errmessage\{Соберите этот файл через pdfLaTeX/.test(l)), lines.slice(2, 6).join(' | '));
  ok('.tex: подпись под картинкой — заголовок этой модели', /\\caption\{КТВ\. Одна страна\}/.test(tex));
  // Правка заголовка руками: щелчок по значению, набор, Enter.
  const undo0 = (await state()).undo;
  await page.click('#exp-title-slot .edval');
  await page.keyboard.type('Мой график');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  const s2 = await state();
  eq0('правка руками в trade', s2.title, 'Мой график');
  ok('правка заголовка не идёт в историю («Отменить» как была)', s2.undo === undo0, 'было ' + undo0 + ', стало ' + s2.undo);
  await close();
  await page.evaluate(() => { pickScene('sd'); closePicker(); redrawAll(); });
  await settle(page);
  await openTex();
  eq0('в sd — своё название', (await state()).title, 'Спрос и предложение');
  await close();
  await page.evaluate(() => { pickScene('trade'); closePicker(); redrawAll(); });
  await settle(page);
  await openTex();
  const s3 = await state();
  eq0('назад в trade — «Мой график»', s3.title, 'Мой график');
  eq0('…и файл «Мой график.tex»', s3.file + '.tex', 'Мой график.tex');
  await close();
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ══ Часть 3 (13.10.2026): полировка «Ответа» ══════════════════════════ */
const SETGRAPH = (exprs, seg) => "STATE.curves = []; curveCounter = 0; " + JSON.stringify(exprs) + ".forEach(e => addCurve(e)); renderGraphRows();"
  + (seg ? ` STATE.ansHand = true; STATE.ansA = ${seg[0]}; STATE.ansB = ${seg[1]};` : '');
const SURPLUS_OLD = /[Ии]злиш\S*\s+(покупател|продав)/;

/* ── Ж: изменение «50 − 10» вместо «было 50 · −10» (Notion …81a2…) ─── */
if (want('Ж')) {
  head('Ж. Изменение строкой «50 − 10»');
  const { ctx, page, errors } = await openPage(1440, 900);
  await openKey(page, 'taxes');
  const cells = await page.evaluate(() => __ar.cells());
  const byNot = (n) => cells.find(c => c.not.replace(/\s+/g, '') === n) || {};
  const WANT = [['Q', '40', '50 − 10'], ['Pb', '60', '50 + 10'], ['Ps', '40', '50 − 10'], ['DWL', '100', '0 + 100']];
  WANT.forEach(([n, v, w]) => {
    const c = byNot(n);
    ok(`taxes: ${n} = ${v}, под ним «${w}»`, c.val === v && c.was === w, `${n} = ${c.val}, «${c.was}»`);
  });
  ok('taxes: знак разности — минус U+2212, не дефис и не тире', cells.every(c => !/[-–—]/.test(c.was)), cells.map(c => c.was).join(' | '));
  const withWas = [];
  for (const key of MODELS) {
    await openKey(page, key);
    (await page.evaluate(() => [...document.querySelectorAll('#ans-hero .ans-was')].map(w => __ar.t(w))))
      .forEach(t => { if (/было|·/.test(t)) withWas.push(key + ': «' + t + '»'); });
  }
  ok('ни в одной модели в .ans-was нет «было» и «·»', !withWas.length, withWas.slice(0, 6).join(' | '));
  await openKey(page, 'taxes');
  await page.evaluate(() => setSelfMode(true));
  await settle(page);
  const shownWas = await page.evaluate(() => [...document.querySelectorAll('#ans-hero .ans-was')].filter(__ar.vis).map(w => __ar.t(w)));
  ok('«Сначала сам» прячет эти числа', !shownWas.length, shownWas.join(' | '));
  await page.evaluate(() => setSelfMode(false));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── Ч: пробел тысяч (карточка …81b4…) ─────────────────────────────── */
if (want('Ч')) {
  head('Ч. Разряды через пробел в «Ответе» и табло');
  const { ctx, page, errors } = await openPage(1440, 900);
  await openKey(page, 'sd');
  const sd = await page.evaluate(() => __ar.cells());
  const v = (n) => (sd.find(c => c.not === n) || {}).val;
  ok('sd: CS «1 250», PS «1 250», SW «2 500»', v('CS') === '1 250' && v('PS') === '1 250' && v('SW') === '2 500', `CS ${v('CS')}, PS ${v('PS')}, SW ${v('SW')}`);
  const VALS = () => {
    const out = [];
    document.querySelectorAll('#ans-hero .ans-val, #ans-hero .ans-was, #params-panel #sb-body .stat > b, #params-panel #sb-body .tx-table td, #ans-burden .burden-val').forEach(el => {
      if (__ar.vis(el)) out.push(__ar.t(el));
    });
    return out;
  };
  await openKey(page, 'ceil');
  const cv = await page.evaluate(VALS);
  ok('ceil: излишки «1 250» и «2 500» с пробелом', cv.includes('1 250') && cv.includes('2 500') && !cv.some(t => /(^|[^\d,])(1250|2500)(?!\d)/.test(t)), cv.filter(t => /\d{3}/.test(t)).slice(0, 8).join(' | '));
  const glued = [];
  for (const key of MODELS) {
    await openKey(page, key);
    (await page.evaluate(VALS)).forEach(t => { const m = /(^|[^\d,.])(\d{4,})(?!\d)/.exec(t); if (m) glued.push(key + ': «' + t.slice(0, 30) + '»'); });
  }
  ok('обход 44 моделей: целой части из 4+ цифр без пробела нет', !glued.length, glued.length + ': ' + glued.slice(0, 8).join(' | '));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── И: «Излишек потребителя / производителя» (решение …8110…) ──────── */
if (want('И')) {
  head('И. Излишки одной парой слов');
  const ROOT = path.resolve(HERE, '../../..');
  const files = fs.readdirSync(path.join(ROOT, 'calc2/static/calc2')).filter(f => /\.(js|css)$/.test(f)).map(f => 'calc2/static/calc2/' + f)
    .concat(['calc2/templates/calc2/calc2.html']);
  const hits = [];
  files.forEach(f => fs.readFileSync(path.join(ROOT, f), 'utf8').split('\n').forEach((l, i) => { if (SURPLUS_OLD.test(l)) hits.push(f + ':' + (i + 1)); }));
  ok('в коде calc2 и шаблоне нет «Излишек покупателя / продавца»', !hits.length, hits.slice(0, 8).join(' | '));
  const { ctx, page, errors } = await openPage(1440, 900);
  const seen = [];
  for (const key of MODELS) {
    await openKey(page, key);
    const t = await page.evaluate(() => {
      const st = document.createElement('style'); st.textContent = '.katex-mathml{display:none!important}';
      document.head.appendChild(st);
      const s = document.querySelector('.app').innerText + ' ' + [...document.querySelectorAll('#chart text, [data-legend]')].map(x => x.textContent + ' ' + (x.getAttribute('data-legend') || '')).join(' ');
      st.remove(); return s;
    });
    const m = SURPLUS_OLD.exec(t);
    if (m) seen.push(key + ': «' + t.slice(Math.max(0, m.index - 10), m.index + 30).replace(/\s+/g, ' ') + '»');
  }
  ok('обход 44 моделей: на экране нет «покупателя / продавца» у излишков', !seen.length, seen.slice(0, 6).join(' | '));
  await openKey(page, 'sd');
  const words = await page.evaluate(() => {
    const st = document.createElement('style'); st.textContent = '.katex-mathml{display:none!important}';
    document.head.appendChild(st);
    const s = document.querySelector('.app').innerText; st.remove(); return s;
  });
  ok('sd: «Излишек потребителя» и «Излишек производителя» на экране', /Излишек потребителя/.test(words) && /Излишек производителя/.test(words));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── Н: перенос длинного значения только между точками (карточка …8100…) ── */
if (want('Н')) {
  head('Н. Три точки в строке: перенос между точками, ничего за колонкой');
  const SETUP = SETGRAPH(['0.001*x^3', '7*x', '100-x^2']);
  const FIT = () => {
    const col = document.querySelector('#params-panel .side-scroll');
    const cr = col.getBoundingClientRect();
    const out = { vals: [], items: [], maxItems: 0, over: [] };
    document.querySelectorAll('#ans-hero .ans-val').forEach(v => {
      if (!__ar.vis(v)) return;
      const n = v.querySelectorAll('.ans-item').length;
      out.maxItems = Math.max(out.maxItems, n);
      if (v.scrollWidth > v.clientWidth + 1) out.vals.push(__ar.t(v).slice(0, 40) + ' ' + v.scrollWidth + '>' + v.clientWidth);
      const r = v.getBoundingClientRect();
      if (r.right > cr.right - parseFloat(getComputedStyle(col).paddingRight) + 1 || r.left < cr.left) out.over.push(__ar.t(v).slice(0, 40));
      v.querySelectorAll('.ans-item').forEach(it => {
        const lh = __ar.lineH(v);
        if (it.getBoundingClientRect().height > lh * 1.4) out.items.push(__ar.t(it));
      });
    });
    return out;
  };
  /* Оба движка: Chromium переносит по <wbr> даже при white-space: nowrap, WebKit
     (Safari) — нет, и обрезка из карточки видна только в нём. */
  const { webkit } = await import('playwright');
  let wk = null;
  try { wk = keepAnswerOpen(await webkit.launch()); } catch (e) { ok('WebKit запускается', false, 'НЕ ПРОВЕРЕНО в WebKit: ' + e.message.split('\n')[0]); }
  for (const [eng, W, H] of [['chromium', 1280, 800], ['chromium', 1440, 900], ['chromium', 390, 844], ['webkit', 1280, 800], ['webkit', 1440, 900], ['webkit', 390, 844]]) {
    if (eng === 'webkit' && !wk) continue;
    const { ctx, page, errors } = await openPage(W, H, Object.assign(W < 760 ? { hasTouch: true } : {}, W < 760 && eng === 'chromium' ? { isMobile: true } : {}), eng === 'webkit' ? wk : null);
    await openKey(page, 'm-graph', SETUP);
    if (W < 760) { await page.click('#ph-tabs .ph-tab[data-tab="ans"]').catch(() => null); await page.waitForTimeout(300); }
    const f = await page.evaluate(FIT);
    ok(eng + ' ' + W + ': есть строка с тремя точками', f.maxItems >= 3, 'пунктов в строке ' + f.maxItems);
    ok(eng + ' ' + W + ': у каждой .ans-val scrollWidth ≤ clientWidth', !f.vals.length, f.vals.join(' | '));
    ok(eng + ' ' + W + ': значение в пределах колонки', !f.over.length, f.over.join(' | '));
    ok(eng + ' ' + W + ': каждая точка в одной строке', !f.items.length, f.items.join(' | '));
    // Колонка до низа: круглая кнопка чата не лежит на строках ответа.
    const fab = await page.evaluate(() => {
      const col = document.querySelector('#params-panel .side-scroll');
      col.scrollTop = col.scrollHeight;
      // Телефон: колонка не прокручивается сама, прокручивается её предок (body).
      for (let p = col.parentElement; p; p = p.parentElement) p.scrollTop = p.scrollHeight;
      const b = document.querySelector('.tg-fab');
      if (!b || !__ar.vis(b)) return { none: true };
      const br = b.getBoundingClientRect();
      const hit = [...document.querySelectorAll('#ans-hero .ans-cell, #params-panel #sb-body .stat, #ex-body p')].filter(__ar.vis).filter(c => {
        const r = c.getBoundingClientRect();
        return r.right > br.left && r.left < br.right && r.bottom > br.top && r.top < br.bottom && r.height > 0;
      }).map(c => __ar.t(c).slice(0, 30));
      return { hit };
    });
    await page.waitForTimeout(100);
    ok(eng + ' ' + W + ': кнопка чата не накрывает строк ответа (колонка прокручена до низа)', fab.none || !fab.hit.length, fab.none ? 'кнопки нет' : fab.hit.join(' | '));
    if (process.env.SHOTS && W === 1280 && eng === 'chromium') await page.screenshot({ path: process.env.SHOTS + '/long_points_1280.png', clip: { x: W - 360, y: 0, width: 360, height: H } });
    ok(eng + ' ' + W + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
  if (wk) await wk.close();
}

/* ── З: заголовки групп не повторяются (карточка …819f…) ───────────── */
if (want('З')) {
  head('З. Заголовки групп «Ответа» разные');
  const { ctx, page, errors } = await openPage(1440, 900);
  const dup = [];
  let costs = [];
  for (const key of MODELS) {
    await openKey(page, key);
    /* Заголовки колонки: группы «Ответа» и заголовки блоков табло ниже — свои
       (.section-title) и нарисованные стилем (::before у #info-*, calc2.css). */
    const hs = await page.evaluate(() => {
      const out = [...document.querySelectorAll('#ans-hero .ans-ghead')].filter(__ar.vis).map(h => __ar.t(h));
      [...document.querySelectorAll('#sb-body > *')].filter(__ar.vis).forEach(b => {
        const bs = getComputedStyle(b, '::before'), c = bs.content;
        if (bs.display !== 'none' && c && c !== 'none' && c !== 'normal' && b.textContent.trim()) out.push(c.replace(/^["']|["']$/g, ''));
        const st = b.querySelector(':scope > .section-title');
        if (st && __ar.vis(st)) out.push(__ar.t(st));
      });
      return out;
    });
    if (key === 'costs') costs = hs;
    const seen = new Set();
    hs.forEach(h => { if (seen.has(h)) dup.push(key + ': «' + h + '»'); seen.add(h); });
  }
  ok('costs: заголовки групп разные', costs.length >= 1 && new Set(costs).size === costs.length, costs.join(' | '));
  ok('обход моделей: двух .ans-ghead с одним текстом нет', !dup.length, dup.join(' | '));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── С: после загрузки ячейка набрана формулой (карточка …815c…) ─────── */
if (want('С')) {
  head('С. После загрузки ни одной сырой ячейки');
  const { ctx, page, errors } = await openPage(1440, 900);
  await openKey(page, 'm-graph', SETGRAPH(['x^2-4', 'x^2-a', '5000-x^2'], [-5, 200]));
  const RAW = () => {
    const bad = [];
    document.querySelectorAll('#ans-hero .ans-val').forEach(v => {
      if (!__ar.vis(v) || v.classList.contains('ans-val--none')) return;
      if (!v.querySelector('.katex')) bad.push('«Ответ»: ' + __ar.t(v.closest('.ans-cell')).slice(0, 50));
    });
    document.querySelectorAll('#info-graph .stat > b').forEach(b => {
      const t = __ar.t(b);
      if (/^[(−\-\d]/.test(t) && !b.querySelector('.katex')) bad.push('табло: ' + __ar.t(b.parentElement).slice(0, 50));
    });
    return bad;
  };
  const before = await page.evaluate(RAW);
  ok('до загрузки: все значения набраны', !before.length, before.join(' | '));
  const lastOne = await page.evaluate(() => { const v = [...document.querySelectorAll('#ans-hero .ans-val')].pop(); return v ? v.querySelectorAll('.ans-item').length + ':' + __ar.t(v) : ''; });
  console.log('  ИНФО последняя ячейка: ' + lastOne);
  const link = await page.evaluate(async () => shareLinkOf());
  for (const how of ['ссылка «Поделиться»', 'перезагрузка']) {
    const p2 = await ctx.newPage();
    if (how === 'перезагрузка') {
      await page.evaluate(() => { historyMark('probe'); redrawAll(); });
      await page.waitForTimeout(800);
      await p2.goto(BASE + '/calc2/?m=m-graph', { waitUntil: 'load' });
    } else await p2.goto(link, { waitUntil: 'load' });
    await p2.addScriptTag({ content: INPAGE });
    for (const ms of [500, 3000]) {
      await p2.waitForTimeout(ms === 500 ? 500 : 2500);
      const r = await p2.evaluate(RAW);
      const n = await p2.evaluate(() => document.querySelectorAll('#ans-hero .ans-val').length);
      ok(`${how}: через ${ms / 1000} с сырых ячеек нет (${n} значений)`, n > 0 && !r.length, r.join(' | '));
    }
    await p2.close();
  }
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── Б: «Кто несёт налог» — «10 (50 %)» ────────────────────────────── */
if (want('Б')) {
  head('Б. «Кто несёт налог»: «10 (50 %)»');
  const { ctx, page, errors } = await openPage(1440, 900);
  await openKey(page, 'taxes');
  const b = await page.evaluate(() => ({
    vals: [...document.querySelectorAll('#ans-burden .burden-col')].map(c => [__ar.t(c.querySelector('.burden-name')), __ar.t(c.querySelector('.burden-val'))]),
    aria: (document.querySelector('#ans-burden .burden-bar') || { getAttribute: () => '' }).getAttribute('aria-label'),
  }));
  const get = (n) => (b.vals.find(x => x[0] === n) || [])[1];
  ok('taxes: «Покупатели» «10 (50 %)», «Продавцы» «10 (50 %)»', get('Покупатели') === '10 (50 %)' && get('Продавцы') === '10 (50 %)', JSON.stringify(b.vals));
  ok('ни в одном .burden-val нет «·»', b.vals.every(x => !/·/.test(x[1] || '')));
  ok('aria-label полосы прежний', /^Покупатели 50\s%, продавцы 50\s%$/.test(String(b.aria).replace(/[  ]/g, ' ')), b.aria);
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

await browser.close();
console.log(bad ? '\nНЕ СОШЛОСЬ: ' + bad + ' из ' + total : '\nВСЁ СОШЛОСЬ: ' + total + ' проверок');
process.exit(bad ? 1 : 0);
