/* КАРТОЧКИ ФУНКЦИЙ ЛЕВОЙ ПАНЕЛИ (тихие панели, сессия 5, 14.10.2026; решение владельца «левая панель одна во
   всех моделях и только про условие», Notion …8142…; ADR 0153; README пакета 4, 8).

   Разделы (--only К,М,Б,В,Г,Д,Е,Ж) — К, М, Д, Е, Ж сессии 6 и модели этапов сессии 5:
     Б  ppf, ppfsum, trade, tradeprice (у второй КПВ — поле MathLive и клавиатура, сессия 6, А6);   В  prod, costs (и «Задаю кривые»), plants, isoquant;
     Г  mono-d3, mono-kink (и «Кусочный»), monoexport, mono-nat, mono, mono-d1, labor, labor-mono, labor-union,
        labor-bilat, smallopen.
   В каждой модели (и состоянии):
     · каждое видимое поле формулы «Условия» — внутри карточки (.fc-card);
     · у карточки есть обозначение (KaTeX в .fc-notation) и имя (.fc-name, непустое), имя не обрезается
       (нет text-overflow: ellipsis и white-space: nowrap);
     · в верхнем ряду только то, что что-то делает: глаз — щелчок меняет картинку холста (и второй возвращает);
       «⋯» — в меню есть орган; кнопка цвета — выбор другого цвета перекрашивает линию холста; простой значок
       цвета — не кнопка и не в табуляции;
     · id органов модели из описи (по умолчанию claude/panels_s5/S5_A.json, --before) на месте в документе;
       ОРГАН: id видимых полей формул «Условия» те же, что на коде до обёртки (сервер BEFORE) — опись пишет поле
       MathLive без id (id у скрытого input), поэтому panels_compare подмену поля копией с новым id не видит;
     · ввод формулы в карточке (одна контрольная запись на модель, потом вернуть) меняет «Ответ» так же, как на
       коде до обёртки (сервер BEFORE, по умолчанию 8098 — копия кода до карточек; нет сервера — громкий пропуск);
     · ничего не вылезает: у карточек и их потомков scrollWidth ≤ clientWidth + 1, у «Условия» нет прокрутки вбок.

   К  (сессия 6, А1–А2; ADR 0154) — один вид карточки и числа плашкой, на старте 42 моделей и в состояниях CASES,
      ширина 1 440 и 1 280 (на 1 240–1 399 колонка 305 px): у каждого видимого НЕкусочного поля карточки кегль 18 px
      или, если запись при 18 шире поля, от 16 до 18; ни одна такая запись не обрезана (.ML__content: scrollWidth ≤
      clientWidth + 1); кусочная запись (\begin{cases}) — тот же кегль и тот же вид, что на коде BEFORE; видимый
      круг точки цвета 16 ± 1 px с кольцом у всех карточек, у кнопки цвета размер нажатия ≥ 26 px; у каждого
      видимого числа строки параметров вид плашки (фон --surface-2, рамка 1 px --border, радиус 6, цифры справа,
      76 ± 1 × 36 ± 1, без пунктира) — в светлой и тёмной теме.

   Д  (сессия 6, Б1–Б2) consumer, cons-slutsky: карточка U «Полезность» (обозначение и имя, список вида, формула вида,
      a и b), «Параметры» — цены и доход числами; список переключает все пять видов (щелчком по списку), и «Ответ» у
      каждого вида тот же, что на коде BEFORE (там — выбор в системном списке); ввод a, b, k, цен, дохода и своей
      формулы меняет «Ответ» так же; id органов cons-* на месте; у Слуцкого обозначение P_{x₁} набрано KaTeX, без «…».
   Е  (сессия 6, этап В) макро: adas, islm, phillips, money, loanable, fx, laffer — общие проверки карточек (поле формулы
      в карточке, обозначение и имя, id те же, контрольная запись меняет «Ответ» так же, как на коде BEFORE; у phillips
      карточек нет); плюс: LRAS — поле ЧИСЛА в карточке без кнопки клавиатуры; ни у одной модели макро нет ползунка
      своей переменной оси (у loanable — буквы r); строки чисел и ползунков — словами слева.
   Ж  (сессия 6, этап Г) неравенство и математика: ineq — «5 групп | 10 групп» сегментом (щелчок даёт тот же «Ответ»,
      что выбор в прежнем списке на коде BEFORE), группы числами, «Сила неравенства» — дорожка цвета --accent,
      строки τ и T словами и значением; карточка L в «Формуле» (общие проверки); математика — см. ниже по моделям.
   М  (сессия 6, А3; Notion …812b…) — «КТВ. Две страны-партнёра»: строка «Мировая цена» в «Условии» и «Мировая цена
      Pw» в «Ответе» — одно число на старте (1,41), после «Сбросить к равновесной» и после сдвига дорожки.

   CALC2_BASE_URL=http://127.0.0.1:8099 BEFORE=http://127.0.0.1:8098 node calc2/tests/redesign/cards_probe.mjs
   ENGINES=chromium,webkit (по умолчанию оба), KEYS="ppf costs" — выборка. Код 0 — всё сошлось.            */
import * as pw from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..', '..');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BEFORE = process.env.BEFORE || 'http://127.0.0.1:8098';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);
const ENGINES = (process.env.ENGINES || 'chromium,webkit').split(',').filter(Boolean);
const INV = arg('before', path.join(ROOT, 'claude', 'panels_s5', 'S5_A.json'));
const KEYS = process.env.KEYS ? process.env.KEYS.split(/\s+/).filter(Boolean) : null;

// [раздел, ключ модели, подпись состояния, код состояния, контрольная запись: [id поля, новая запись]]
const CASES = [
  ['Б', 'ppf', '', '', ['inp-ppf', 'y = 80 - x']],
  ['Б', 'ppf', 'вторая КПВ', "document.getElementById('btn-ppf-compare').click();", ['inp-ppf2b', 'y = 70 - x']],
  ['Б', 'ppfsum', '', '', ['inp-ppfsum-0', 'y = 90 - x']],
  ['Б', 'trade', '', '', ['inp-ppft', '90 - X']],
  ['Б', 'tradeprice', '', '', ['inp-tb1', '90 - X']],
  ['В', 'prod', '', '', ['inp-prod', '20*L^2 - L^3']],
  ['В', 'costs', '', '', ['inp-tc', 'Q^3 - 6*Q^2 + 15*Q + 30']],
  ['В', 'costs', 'Задаю кривые', "document.getElementById('cm-curves').click();", ['inp-cmc', '3*Q^2 - 12*Q + 20']],
  ['В', 'plants', '', '', ['inp-pl1', '1.5*Q^2']],
  ['В', 'isoquant', '', '', ['inp-iso', 'L^0.4 * K^0.6']],
  ['Г', 'mono-d3', '', '', ['inp-d3-1', '90 - Q']],
  ['Г', 'mono-kink', '', '', ['inp-ki-1', '90 - Q']],
  ['Г', 'mono-kink', 'Кусочный', "document.getElementById('ki-piece').click();", ['inp-kp-1', '90 - Q']],
  ['Г', 'monoexport', '', '', ['inp-d3-1', '90 - Q']],
  ['Г', 'mono-nat', '', '', ['curve-expr-1', '90 - Q']],
  ['Г', 'mono', '', '', ['curve-expr-1', '90 - Q']],
  ['Г', 'mono-d1', '', '', ['curve-expr-1', '90 - Q']],
  ['Г', 'labor', '', '', ['curve-expr-1', '90 - L']],
  ['Г', 'labor-mono', '', '', ['curve-expr-1', '90 - L']],
  ['Г', 'labor-union', '', '', ['curve-expr-1', '90 - L']],
  ['Г', 'labor-bilat', '', '', ['curve-expr-1', '90 - L']],
  ['Г', 'smallopen', '', '', ['curve-expr-1', '90 - Q']],
  ['Е', 'adas', '', '', ['ma-sras', '5 + 0.5*Y']],
  ['Е', 'islm', '', '', ['ma-is', '25 - 0.1*Y']],
  ['Е', 'phillips', '', '', ['ma-pe', '6']],
  ['Е', 'money', '', '', ['ma-md', '220 - 4*i']],
  ['Е', 'loanable', '', '', ['ma-ls', '40 + 2*r']],
  ['Е', 'fx', '', '', ['ma-fxd', '110 - 2*e']],
  ['Е', 'laffer', '', '', ['ma-lafd', '90 - Q']],
  ['Ж', 'ineq', 'Формула', "setIneqInput('formula');", ['ineq-formula', 'p^3']],
  ['Д', 'consumer', 'своя формула', "setConsumerType('custom');", ['cons-custom', 'x^0.3 * y^0.7']],
  ['Д', 'cons-slutsky', 'своя формула', "setConsumerType('custom');", ['cons-custom', 'x^0.3 * y^0.7']],
];

// Модели без карточек функций (README 8): «Кривая Филлипса» — только «Параметры».
const NO_CARDS_MODELS = new Set(['phillips']);
const ALL42 = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer'.split(' ');
// К: кусочная запись — та же на коде BEFORE (кегль, высокая строка) — [модель, поле, запись].
const K_CASES_REC = ['sd', 'curve-expr-1', 'Q < 40 ? 100 - Q : 140 - 2*Q'];

let bad = 0, total = 0, eng = '';
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' [' + eng + '] ' + label + (detail && !cond ? '  — ' + detail : ''));
}
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));
let browser = null, engName = '', ctxCount = 0;
async function newCtx(opts) {
  // WebKit Playwright: не больше 63 контекстов на один запущенный браузер (замер 14.10) — перезапуск.
  if (ctxCount >= 50 && !browser.contexts().length) { await browser.close(); browser = await pw[engName].launch(); ctxCount = 0; }
  ctxCount++;
  return browser.newContext(opts);
}
async function openAt(base) {
  const ctx = await newCtx({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript(() => { try { localStorage.clear(); localStorage.setItem('theme', 'light'); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(base + '/calc2/', { waitUntil: 'load', timeout: 40000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 40000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  return { ctx, page, errors };
}
async function pick(page, key, extra) {
  await page.evaluate(([k, x]) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); if (x) (new Function(x))(); redrawAll(); }, [key, extra || '']);
  await page.waitForTimeout(600);
}
// Числа «Ответа» (главные ячейки и строки табло) — для сравнения «до обёртки / после».
const answerNums = (page) => page.evaluate(() => {
  const tx = (e) => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent; };
  const hero = [...document.querySelectorAll('#ans-hero .ans-cell .ans-val')].map(tx).join('|');
  const sb = [...document.querySelectorAll('#sb-body .stat > b')].map(tx).join('|');
  return (hero + '#' + sb).replace(/[\s   ​]+/g, '');
});
const formulaIds = (page) => page.evaluate(() => [...document.querySelectorAll('#tools-panel math-field, #tools-panel .f-slot > input[type=text]')]
  .filter(e => e.getClientRects().length).map(e => { const i = e.tagName === 'MATH-FIELD' ? e.parentElement.querySelector('input[id]') : e; return i ? i.id : '?'; })
  .filter((x, i, a) => a.indexOf(x) === i).sort().join(','));
async function typeAndRead(page, id, expr) {
  const was = await page.evaluate((id) => { const i = document.getElementById(id); return i ? i.value : null; }, id);
  if (was == null) return { missing: true };
  const before = await answerNums(page);
  // Ввод и уход из поля: input (мост MathLive шлёт его) и change (поле «Своей формулы» потребителя слушает только его).
  const put = ([id, v]) => { const e = document.getElementById(id); setFieldValue(e, v); e.dispatchEvent(new Event('change', { bubbles: true })); };
  await page.evaluate(put, [id, expr]);
  await page.waitForTimeout(700);
  const after = await answerNums(page);
  await page.evaluate(put, [id, was]);
  await page.waitForTimeout(500);
  const back = await answerNums(page);
  return { before, after, back };
}

const cardsCheck = (page) => page.evaluate(() => {
  const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  const tp = document.getElementById('tools-panel');
  const out = { bare: [], noSym: [], noName: [], cut: [], over: [], cards: 0, eyes: [], gears: [], dots: [], other: [] };
  [...tp.querySelectorAll('math-field, .f-slot > input[type=text]')].filter(vis).forEach(f => {
    const inp = f.tagName === 'MATH-FIELD' ? (f.parentElement && f.parentElement.querySelector('input[id]')) : f;
    if (!f.closest('.fc-card')) out.bare.push(inp ? inp.id : '?');
  });
  [...tp.querySelectorAll('.fc-card')].filter(vis).forEach((c, i) => {
    out.cards++;
    const tag = (c.querySelector('input[id]') || {}).id || ('карточка ' + i);
    const sym = c.querySelector(':scope > .crow-top .fc-notation');
    if (!sym || !sym.querySelector('.katex') || !sym.textContent.trim()) out.noSym.push(tag);
    const nm = c.querySelector(':scope > .crow-top .fc-name');
    if (!nm || !nm.textContent.trim() || !vis(nm)) out.noName.push(tag);
    else { const cs = getComputedStyle(nm); if (cs.textOverflow === 'ellipsis' || cs.whiteSpace === 'nowrap') out.cut.push(tag + ' ' + cs.textOverflow + '/' + cs.whiteSpace); }
    [c, ...c.querySelectorAll('*')].forEach(e => {
      if (!vis(e) || e.closest('.fc-menu, .f-pop, .mkbd, math-field, .katex')) return;
      if (e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible' && e.clientWidth > 0) out.over.push(tag + ' ' + e.tagName.toLowerCase() + '.' + String(e.className).split(' ')[0] + ' ' + e.scrollWidth + '>' + e.clientWidth);
    });
    // Старая подпись над полем (её текст пишет сцена — узел остаётся) не видна.
    const oldLab = c.querySelector(':scope > label');
    if (oldLab && vis(oldLab)) out.other.push(tag + ' видна старая подпись «' + oldLab.textContent.trim().slice(0, 30) + '»');
    const top = c.querySelector(':scope > .crow-top');
    [...top.querySelectorAll('button, [tabindex]')].filter(vis).forEach(b => {
      if (b.classList.contains('fc-eye')) out.eyes.push(i);
      else if (b.classList.contains('crow-gear')) out.gears.push(i);
      else if (b.classList.contains('cpick-btn')) out.dots.push(i);
      else out.other.push(tag + ' ' + b.className);
    });
    const dot = top.querySelector('.fc-dot');
    if (dot && (dot.tagName === 'BUTTON' || dot.hasAttribute('tabindex'))) out.other.push(tag + ' значок цвета нажимается');
  });
  out.hscroll = tp.scrollWidth > tp.clientWidth + 1 ? tp.scrollWidth + '>' + tp.clientWidth : '';
  return out;
});
// Картинка холста: пути (обводка, видимость) — для проверки глаза и кнопки цвета.
const pic = (page) => page.evaluate(() => [...document.querySelectorAll('#chart path')].map(p => (p.getAttribute('stroke') || '') + (getComputedStyle(p).display === 'none' ? '-' : '')).sort().join(','));
async function functional(page, r) {
  const fail = [];
  const cardAt = (i) => `#tools-panel .fc-card:nth-match(${i})`;
  for (const i of r.eyes) {
    const p0 = await pic(page);
    await page.evaluate((i) => [...document.querySelectorAll('#tools-panel .fc-card')].filter(c => c.getClientRects().length)[i].querySelector(':scope > .crow-top .fc-eye').click(), i);
    await page.waitForTimeout(400);
    const p1 = await pic(page);
    await page.evaluate((i) => { const c = [...document.querySelectorAll('#tools-panel .fc-card')].filter(c => c.getClientRects().length)[i]; c.querySelector(':scope > .crow-top .fc-eye').click(); }, i);
    await page.waitForTimeout(400);
    const p2 = await pic(page);
    if (p0 === p1) fail.push('карточка ' + i + ': глаз ничего не меняет на холсте');
    if (p2 !== p0) fail.push('карточка ' + i + ': второй щелчок глаза не вернул картинку');
  }
  for (const i of r.gears) {
    const n = await page.evaluate((i) => {
      const c = [...document.querySelectorAll('#tools-panel .fc-card')].filter(c => c.getClientRects().length)[i];
      const m = c.querySelector('.fc-menu');
      return m ? m.querySelectorAll('input:not([type=hidden]), button, select, .edval, textarea').length : 0;
    }, i);
    if (!n) fail.push('карточка ' + i + ': «⋯» с пустым меню');
  }
  for (const i of r.dots) {
    const p0 = await pic(page);
    const b = await page.evaluateHandle((i) => [...document.querySelectorAll('#tools-panel .fc-card')].filter(c => c.getClientRects().length)[i].querySelector(':scope > .crow-top .cpick-btn'), i);
    await b.asElement().click();
    await page.waitForTimeout(200);
    const sw = await page.$('.cpick-menu .cpick-sw[aria-checked="false"]');
    if (!sw) { fail.push('карточка ' + i + ': кнопка цвета не открыла выбор'); continue; }
    await sw.click();
    await page.waitForTimeout(400);
    const p1 = await pic(page);
    if (p0 === p1) fail.push('карточка ' + i + ': выбор цвета не перекрасил холст');
  }
  void cardAt;
  return fail;
}

async function runCase(sec, key, label, extra, ctl, inv, beforeAns) {
  const tag = key + (label ? ' «' + label + '»' : '');
  const { ctx, page, errors } = await openAt(BASE);
  await pick(page, key, extra);
  const r = await cardsCheck(page);
  // У «Кривой Филлипса» карточек нет (README 8: только «Параметры»).
  ok(tag + ': каждое поле формулы в карточке (' + r.cards + ' карточек)', (NO_CARDS_MODELS.has(key) ? r.cards === 0 : r.cards > 0) && !r.bare.length, 'голые: ' + r.bare.join(', '));
  ok(tag + ': у карточек обозначение KaTeX и имя, имя не обрезается', !r.noSym.length && !r.noName.length && !r.cut.length, JSON.stringify({ noSym: r.noSym, noName: r.noName, cut: r.cut }));
  ok(tag + ': в верхнем ряду карточек только глаз, «⋯», кнопка цвета; значок цвета не нажимается; старой подписи не видно', !r.other.length, r.other.join(' | '));
  const f = await functional(page, r);
  ok(tag + ': глаз, «⋯», кнопка цвета что-то делают (глаз ' + r.eyes.length + ', «⋯» ' + r.gears.length + ', цвет ' + r.dots.length + ')', !f.length, f.join(' | '));
  ok(tag + ': ничего не вылезает (карточки, «Условие» вбок)', !r.over.length && !r.hscroll, r.over.slice(0, 4).join(' | ') + ' ' + r.hscroll);
  if (!label && inv && inv[key]) {
    const ids = inv[key].left.map(c => c.id).filter(Boolean);
    const miss = await page.evaluate((ids) => ids.filter(id => !document.getElementById(id)), ids);
    ok(tag + ': id органов описи на месте (' + ids.length + ')', !miss.length, miss.join(', '));
  }
  if (beforeAns && beforeAns.ids != null) {
    // Поля, ставшие полями формул по решению (А6 сессии 6: «КПВ 2» было простым текстовым полем), — не подмена.
    const NEW_FORMULA = new Set(['inp-ppf2b']);
    const strip = (x) => x.split(',').filter(i => i && !NEW_FORMULA.has(i)).join(',');
    const ids = await formulaIds(page);
    ok(tag + ': ОРГАН — id полей формул те же, что до обёртки (' + beforeAns.ids + ')', strip(ids) === strip(beforeAns.ids), 'сейчас ' + ids);
  }
  // Сессия 6, А6 (Notion …8138…): у второй КПВ поле MathLive и кнопка клавиатуры, как у первой.
  if (key === 'ppf' && label) {
    const k2 = await page.evaluate(() => {
      const i = document.getElementById('inp-ppf2b'); const row = i && i.closest('.f-row');
      const kb = row && row.querySelector('.f-kbd, .f-help');
      return { mf: !!(i && i._mf && i._mf.getClientRects().length), kbd: !!(kb && kb.getClientRects().length && getComputedStyle(kb).visibility !== 'hidden') };
    });
    ok(tag + ': у второй КПВ поле MathLive и кнопка клавиатуры (' + JSON.stringify(k2) + ')', k2.mf && k2.kbd, JSON.stringify(k2));
  }
  // Контрольная запись: на свежей модели (без следов щелчков выше).
  await pick(page, key, extra);
  const t = await typeAndRead(page, ctl[0], ctl[1]);
  if (t.missing) ok(tag + ': поле ' + ctl[0] + ' есть', false, 'нет поля');
  else {
    const same = beforeAns ? (beforeAns.after === t.after) : null;
    ok(tag + ': ввод в карточке «' + ctl[0] + '» меняет «Ответ»' + (beforeAns ? ' так же, как до обёртки' : ' (база BEFORE недоступна — сравнение с кодом до обёртки НЕ ПРОВЕРЕНО)') + ', возврат возвращает',
      t.after !== t.before && t.back === t.before && same !== false, JSON.stringify({ now: t.after.slice(0, 120), was: beforeAns && beforeAns.after.slice(0, 120) }));
  }
  ok(tag + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}


/* ── К: один вид карточки и числа плашкой (сессия 6, А1–А2) ── */
const kLook = (page) => page.evaluate(() => {
  const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  const tp = document.getElementById('tools-panel');
  const out = { fields: [], dots: [], nums: [] };
  [...tp.querySelectorAll('.fc-card math-field')].filter(vis).forEach(mf => {
    const id = ((mf.parentElement && mf.parentElement.querySelector('input[id]')) || {}).id || '?';
    const box = mf.shadowRoot && mf.shadowRoot.querySelector('.ML__content');
    if (!box) return;
    const tall = /\\begin\{cases\}/.test(String(mf.value || ''));
    const fs = parseFloat(getComputedStyle(mf).fontSize);
    const cut = box.scrollWidth > box.clientWidth + 1 ? box.scrollWidth + '>' + box.clientWidth : '';
    // Шире ли запись при 18 px (иначе ужатие не оправдано): мерим и возвращаем как было.
    let wide18 = null;
    if (!tall && Math.abs(fs - 18) > 0.1) {
      const was = mf.style.fontSize; mf.style.fontSize = '18px';
      const pre = mf.closest('.crow-formula'); const off = pre && pre.classList.contains('fc-pre-off');
      wide18 = box.scrollWidth > box.clientWidth + 1;
      if (off) { pre.classList.remove('fc-pre-off'); wide18 = true; pre.classList.add('fc-pre-off'); }
      mf.style.fontSize = was;
    }
    out.fields.push({ id, tall, fs, cut, wide18, value: String(mf.value || '').slice(0, 60) });
  });
  [...tp.querySelectorAll('.fc-card > .crow-top')].filter(vis).forEach(top => {
    const card = top.parentElement;
    const tag = ((card.querySelector('input[id]') || {}).id) || 'карточка';
    const d = [...top.querySelectorAll('.fc-dot, .cpick-btn')].find(vis);
    if (!d) return;
    const cs = getComputedStyle(d);
    const r = d.getBoundingClientRect();
    // видимый круг: у кнопки — внутренность рамки (на телефоне рамка прозрачная), у значка — сам узел
    const w = d.clientWidth, h = d.clientHeight;
    const ring = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 1;
    let hit = null;
    if (d.classList.contains('cpick-btn')) {
      d.scrollIntoView({ block: 'center' });
      const rr = d.getBoundingClientRect(), cx = rr.left + rr.width / 2, cy = rr.top + rr.height / 2;
      const at = (x, y) => { const e = document.elementFromPoint(x, y); return !!(e && (e === d || d.contains(e))); };
      hit = at(cx - 12.5, cy) && at(cx + 12.5, cy) && at(cx, cy - 12.5) && at(cx, cy + 12.5);
    }
    out.dots.push({ tag, kind: d.classList.contains('cpick-btn') ? 'кнопка' : 'значок', w, h, ring, hit, rw: Math.round(r.width) });
  });
  const tok = (v, prop) => { const p = document.createElement('div'); p.style.setProperty(prop, 'var(' + v + ')'); if (prop.startsWith('border')) p.style.borderStyle = 'solid'; tp.appendChild(p); const c = getComputedStyle(p)[prop === 'background-color' ? 'backgroundColor' : 'borderTopColor']; p.remove(); return c; };
  const bg = tok('--surface-2', 'background-color'), bc = tok('--border', 'border-top-color');
  [...tp.querySelectorAll('.sc-nrow > input, input.sc-num')].filter(vis).forEach(i => {
    const cs = getComputedStyle(i);
    const bad = [];
    if (cs.backgroundColor !== bg) bad.push('фон ' + cs.backgroundColor + ' ≠ ' + bg);
    ['Top', 'Right', 'Bottom', 'Left'].forEach(sd => {
      if (cs['border' + sd + 'Style'] !== 'solid' || Math.abs(parseFloat(cs['border' + sd + 'Width']) - 1) > 0.1 || cs['border' + sd + 'Color'] !== bc) bad.push('рамка ' + sd + ' ' + cs['border' + sd + 'Style'] + ' ' + cs['border' + sd + 'Width'] + ' ' + cs['border' + sd + 'Color']);
    });
    if (Math.abs(parseFloat(cs.borderTopLeftRadius) - 6) > 0.1) bad.push('радиус ' + cs.borderTopLeftRadius);
    if (cs.textAlign !== 'right') bad.push('цифры ' + cs.textAlign);
    const r = i.getBoundingClientRect();
    if (Math.abs(r.width - 76) > 1 || Math.abs(r.height - 36) > 1) bad.push('размер ' + Math.round(r.width) + '×' + Math.round(r.height));
    out.nums.push({ id: i.id, bad });
  });
  return out;
});
async function kRun(theme) {
  const tag0 = '[' + theme + '] ';
  for (const W of [1440, 1280]) {
    const ctx = await newCtx({ viewport: { width: W, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
    await ctx.addInitScript((t) => { try { localStorage.clear(); localStorage.setItem('theme', t); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} }, theme);
    const page = await ctx.newPage();
    const errors = []; page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
    await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 40000 });
    await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 40000 });
    await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
    const states = ALL42.map(k => [k, '', '']).concat(CASES.filter(c => c[2]).map(c => [c[1], c[2], c[3]]));
    const f = { size: [], cut: [], dot: [], hit: [], num: [] };
    let nF = 0, nD = 0, nN = 0;
    for (const [key, label, extra] of states) {
      if (KEYS && !KEYS.includes(key)) continue;
      await pick(page, key, extra);
      const r = await kLook(page);
      const where = key + (label ? ' «' + label + '»' : '');
      r.fields.filter(x => !x.tall).forEach(x => {
        nF++;
        const okSize = Math.abs(x.fs - 18) <= 0.1 || (x.wide18 && x.fs >= 15.9 && x.fs <= 18.1);
        if (!okSize) f.size.push(where + ' ' + x.id + ' ' + x.fs + ' px' + (x.wide18 === false ? ' (при 18 помещается)' : ''));
        if (x.cut) f.cut.push(where + ' ' + x.id + ' ' + x.cut + ' «' + x.value + '»');
      });
      r.dots.forEach(d => {
        nD++;
        if (Math.abs(d.w - 16) > 1 || Math.abs(d.h - 16) > 1 || !d.ring) f.dot.push(where + ' ' + d.tag + ' ' + d.kind + ' ' + d.w + '×' + d.h + (d.ring ? '' : ' без кольца'));
        if (d.hit === false) f.hit.push(where + ' ' + d.tag);
      });
      r.nums.forEach(n => { nN++; if (n.bad.length) f.num.push(where + ' ' + n.id + ': ' + n.bad.join(', ')); });
    }
    const w = tag0 + W + ': ';
    ok(w + 'запись карточек 18 px, ужата до 16–18 только если при 18 шире поля (' + nF + ' полей)', !f.size.length, f.size.slice(0, 6).join(' | '));
    const onlyNoCards = !!KEYS && KEYS.every(k => NO_CARDS_MODELS.has(k));
    ok(w + 'ни одна некусочная запись карточки не обрезана, TC «Издержек» тоже', (nF > 0 || onlyNoCards) && !f.cut.length, f.cut.slice(0, 6).join(' | '));
    ok(w + 'точка цвета 16 ± 1 px с кольцом у всех карточек (' + nD + ')', (nD > 0 || onlyNoCards) && !f.dot.length, f.dot.slice(0, 6).join(' | '));
    ok(w + 'у кнопки цвета размер нажатия ≥ 26 px', !f.hit.length, f.hit.slice(0, 6).join(' | '));
    if (!KEYS || KEYS.some(k => ['ppf', 'isoquant', 'mono-nat', 'trade', 'ppfsum', 'consumer', 'cons-slutsky', 'phillips', 'money', 'laffer', 'ineq'].includes(k))) ok(w + 'числа строк параметров — плашкой 76 × 36 (' + nN + ')', nN > 0 && !f.num.length, f.num.slice(0, 6).join(' | '));
    ok(w + 'ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
}
// Кусочная запись — как на коде BEFORE (кегль, высокая строка, обрезка).
async function kCases(base) {
  const { ctx, page } = await openAt(base);
  await pick(page, K_CASES_REC[0]);
  await page.evaluate(([id, v]) => setFieldValue(document.getElementById(id), v), [K_CASES_REC[1], K_CASES_REC[2]]);
  await page.waitForTimeout(900);
  await page.evaluate(() => { redrawAll(); });
  await page.waitForTimeout(700);
  const r = await page.evaluate((id) => {
    const i = document.getElementById(id); const mf = i && i._mf; if (!mf) return null;
    const box = mf.shadowRoot.querySelector('.ML__content');
    return { tall: /\\begin\{cases\}/.test(mf.value), fs: getComputedStyle(mf).fontSize, rowTall: !!(i.closest('.f-row') || {}).classList?.contains('f-tall'), fits: box.scrollWidth <= box.clientWidth + 1 };
  }, K_CASES_REC[1]);
  await ctx.close();
  return r;
}

/* ── М: мировая цена «КТВ. Две страны-партнёра» — строка и «Ответ» одним числом (сессия 6, А3) ── */
const twoPw = (page) => page.evaluate(() => {
  const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ''); };
  const num = (t) => { const m = String(t).replace(/−/g, '-').match(/-?\d+(?:[.,]\d+)?/g); return m ? m[m.length - 1].replace(',', '.') : null; };
  const row = document.querySelector('#tb-price-field .reg-eq');
  const st = [...document.querySelectorAll('#info-tb .stat')].find(e => /Мироваяцена/.test(tx(e.querySelector('span'))));
  const hero = [...document.querySelectorAll('#ans-hero .ans-cell')].find(e => /Мироваяцена/.test(tx(e)));
  return { row: num(tx(row)), table: st ? num(tx(st.querySelector('b'))) : null, hero: hero ? num(tx(hero.querySelector('.ans-val'))) : null, rowText: tx(row) };
});
async function mRun() {
  const { ctx, page, errors } = await openAt(BASE);
  await pick(page, 'tradeprice');
  const same = (r) => r.row != null && r.row === r.table && (r.hero == null || r.hero === r.row);
  const a = await twoPw(page);
  ok('М: на старте строка «Мировая цена» и «Ответ» — одно число (' + JSON.stringify(a) + ')', same(a) && a.row === '1.41', JSON.stringify(a));
  await page.evaluate(() => { const s = document.getElementById('tb-price-slider'); s.value = String(+s.min + (+s.max - +s.min) * 0.7); s.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(700);
  const b = await twoPw(page);
  ok('М: после сдвига дорожки — одно число (' + JSON.stringify(b) + ')', same(b) && b.row !== a.row, JSON.stringify(b));
  await page.evaluate(() => document.getElementById('btn-tb-reset').click());
  await page.waitForTimeout(700);
  const c = await twoPw(page);
  ok('М: после «Сбросить к равновесной» — одно число, 1,41 (' + JSON.stringify(c) + ')', same(c) && c.row === '1.41', JSON.stringify(c));
  ok('М: ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── Д: потребитель (сессия 6, Б1–Б2) ── */
const CONS_IDS = ['cons-type', 'cons-a', 'cons-b', 'cons-k', 'cons-custom', 'cons-px', 'cons-py', 'cons-i', 'cons-a-lbl', 'cons-b-lbl', 'cons-ab-row', 'cons-k-row', 'cons-custom-row'];
const CONS_TYPES = [['cobb', 'Кобб-Дуглас'], ['subs', 'Совершенные субституты'], ['compl', 'Совершенные комплементы'], ['quasi', 'Квазилинейные'], ['custom', 'Своя формула']];
// Шаги ввода: [вид, id, значение] — число через change (как у человека: ввод и уход из поля).
const CONS_STEPS = [['cobb', 'cons-a', '0.3'], ['cobb', 'cons-b', '0.7'], ['cobb', 'cons-px', '2'], ['cobb', 'cons-py', '3'], ['cobb', 'cons-i', '150'], ['subs', 'cons-a', '3'], ['quasi', 'cons-k', '3']];
async function consSeries(page, viaUi) {
  const out = {};
  for (const [t, word] of CONS_TYPES) {
    if (viaUi) {
      await page.evaluate(() => { const b = document.querySelector('#sec-consumer .sc-ucard .sel-btn'); if (b) b.click(); });
      await page.waitForTimeout(150);
      const clicked = await page.evaluate((w) => { const it = [...document.querySelectorAll('.sel-menu .sel-item')].find(x => x.textContent.trim() === w); if (it) { it.click(); return true; } return false; }, word);
      if (!clicked) { out[t] = 'нет пункта «' + word + '»'; continue; }
    } else await page.evaluate((t) => { const s = document.getElementById('cons-type'); s.value = t; s.dispatchEvent(new Event('change', { bubbles: true })); }, t);
    await page.waitForTimeout(600);
    out[t] = await answerNums(page);
  }
  for (const [t, id, v] of CONS_STEPS) {
    await page.evaluate((t) => { const s = document.getElementById('cons-type'); if (s.value !== t) { s.value = t; s.dispatchEvent(new Event('change', { bubbles: true })); } }, t);
    await page.waitForTimeout(400);
    await page.evaluate(([id, v]) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('change', { bubbles: true })); }, [id, v]);
    await page.waitForTimeout(500);
    out[t + ':' + id + '=' + v] = await answerNums(page);
  }
  return out;
}
async function dRun(beforeCons) {
  for (const key of ['consumer', 'cons-slutsky']) {
    if (KEYS && !KEYS.includes(key)) continue;
    const { ctx, page, errors } = await openAt(BASE);
    await pick(page, key);
    const look = await page.evaluate(() => {
      const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
      const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ' ').trim(); };
      const card = document.querySelector('#sec-consumer .sc-ucard');
      const sym = card && card.querySelector('.crow-top .fc-notation');
      const nm = card && card.querySelector('.crow-top .fc-name');
      const btns = card ? [...card.querySelectorAll(':scope > .crow-top button')].filter(vis).length : -1;
      const sel = card && card.querySelector('.sel-btn .sel-text');
      const fml = card && card.querySelector('.sc-ufml');
      const lets = card ? [...card.querySelectorAll('.sc-letter')].filter(vis).map(tx) : [];
      const nums = [...document.querySelectorAll('#sec-consumer .sc-nrow')].filter(vis).map(f => tx(f.querySelector('label')));
      const nativeShown = vis(document.getElementById('cons-type'));
      const px1 = document.querySelector('#cons-px1-row .reg-eq');
      const pn = document.querySelector('#cons-px1-row .sc-pname');
      return { card: !!card && vis(card), sym: sym ? tx(sym) : '', symKatex: !!(sym && sym.querySelector('.katex')), name: nm ? tx(nm) : '', btns,
        sel: sel && vis(sel) ? tx(sel) : '', fml: fml && vis(fml) ? tx(fml) : '', fmlKatex: !!(fml && fml.querySelector('.katex')), lets, nums, nativeShown,
        px1: px1 && vis(px1) ? { text: tx(px1), katex: !!px1.querySelector('.katex'), html: px1.innerHTML.includes('msub') || !!px1.querySelector('.msupsub') } : null,
        pname: pn && vis(pn) ? tx(pn) : '' };
    });
    ok(key + ': карточка U «Полезность» — обозначение KaTeX и имя, в верхнем ряду ни глаза, ни «⋯» (' + JSON.stringify([look.sym, look.name, look.btns]) + ')', look.card && look.sym === 'U' && look.symKatex && look.name === 'Полезность' && look.btns === 0, JSON.stringify(look));
    ok(key + ': в карточке список вида словами, формула вида KaTeX, a и b буквами; системного списка не видно', look.sel === 'Кобб-Дуглас' && look.fmlKatex && /U=/.test(look.fml.replace(/\s/g, '')) && look.lets.join(',') === 'a,b' && !look.nativeShown, JSON.stringify(look));
    ok(key + ': «Параметры» — «Цена товара x», «Цена товара y», «Доход» строками чисел', look.nums.join('|') === 'Цена товара x|Цена товара y|Доход', look.nums.join('|'));
    if (key === 'cons-slutsky') ok(key + ': строка «Новая цена товара x», обозначение P_{x₁} набрано KaTeX, многоточия нет (' + JSON.stringify(look.px1) + ')', look.pname === 'Новая цена товара x' && !!look.px1 && look.px1.katex && look.px1.html && !/…|\.\.\./.test(look.px1.text) && /^Px1=4$/.test(look.px1.text.replace(/\s/g, '')), JSON.stringify({ px1: look.px1, pname: look.pname }));
    const miss = await page.evaluate((ids) => ids.filter(id => !document.getElementById(id)), CONS_IDS);
    ok(key + ': id органов cons-* на месте (' + CONS_IDS.length + ')', !miss.length, miss.join(', '));
    const now = await consSeries(page, true);
    const was = beforeCons && beforeCons[key];
    if (!was) ok(key + ': «Ответ» по видам и вводу — сравнение с кодом до сессии НЕ ПРОВЕРЕНО (нет BEFORE)', false, '');
    else {
      const diff = Object.keys(was).filter(k => was[k] !== now[k]);
      const moved = Object.keys(now).filter((k, i, a) => i > 0 && now[k] !== now[a[i - 1]]).length;
      ok(key + ': список переключает 5 видов, ввод a, b, k, цен и дохода — «Ответ» тот же, что на коде до сессии (' + Object.keys(was).length + ' замеров, менялся ' + moved + ' раз)', !diff.length && moved >= 8, diff.map(k => k + ': было ' + String(was[k]).slice(0, 60) + ' / стало ' + String(now[k]).slice(0, 60)).slice(0, 3).join(' | '));
    }
    ok(key + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

/* ── Е: макро (сессия 6, этап В) ── */
const MACRO_KEYS = ['adas', 'islm', 'phillips', 'money', 'loanable', 'fx', 'laffer'];
const MACRO_AXIS = { adas: ['Y'], islm: ['Y', 'r'], phillips: ['u'], money: ['i'], loanable: ['r'], fx: ['e'], laffer: ['Q', 't'] };
async function eRun() {
  const { ctx, page, errors } = await openAt(BASE);
  for (const key of MACRO_KEYS) {
    if (KEYS && !KEYS.includes(key)) continue;
    await pick(page, key);
    const r = await page.evaluate((axis) => {
      const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
      const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ''); };
      const chips = [...document.querySelectorAll('#tools-panel .pchip-param')].filter(vis).map(c => tx(c.querySelector('.pchip-label, .reg-eq') || c));
      const axisChips = chips.filter(t => axis.some(a => t.startsWith(a + '=')));
      const lras = document.getElementById('ma-lras');
      const lc = lras && lras.closest('.fc-card');
      const lrow = lras && lras.closest('.crow-formula');
      const kbd = lrow ? [...lrow.querySelectorAll('.f-kbd, .f-help')].filter(vis).length : -1;
      const rows = [...document.querySelectorAll('#sec-macro .sc-prow, #sec-macro .sc-nrow')].filter(vis).map(f => {
        const nm = f.querySelector('.sc-pname') || f.querySelector(':scope > label');
        return tx(nm);
      });
      return { chips, axisChips, lras: lras ? { card: !!lc && vis(lc), inRow: !!lrow, kbd, sym: lc ? tx(lc.querySelector('.fc-notation')) : '' } : null, rows };
    }, MACRO_AXIS[key]);
    ok(key + ': нет ползунка своей переменной оси (' + MACRO_AXIS[key].join(', ') + ')', !r.axisChips.length, JSON.stringify(r.chips));
    if (key === 'adas') ok('adas: LRAS — поле числа в карточке, без кнопки клавиатуры (' + JSON.stringify(r.lras) + ')', !!r.lras && r.lras.card && r.lras.inRow && r.lras.kbd === 0 && r.lras.sym === 'LRAS', JSON.stringify(r.lras));
    const WANT = { phillips: ['Ожидаемаяинфляцияπe', 'Естественнаябезработицаu∗', 'Наклонβ'], money: ['ПредложениеденегMs'], loanable: ['Дефицитбюджета'], fx: ['Курс'], laffer: ['Ставканаосидо'] };
    if (WANT[key]) ok(key + ': строки «Параметров» словами (' + r.rows.join(' | ') + ')', JSON.stringify(r.rows.filter(x => WANT[key].includes(x))) === JSON.stringify(WANT[key].filter(w => key !== 'fx' || r.rows.includes(w))) && WANT[key].filter(w => key !== 'fx').every(w => r.rows.includes(w)), JSON.stringify(r.rows));
  }
  ok('Е: ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* ── Ж: неравенство и математика (сессия 6, этап Г) ── */
async function ineqSeries(page, viaSeg) {
  const out = {};
  for (const n of ['10', '5']) {
    if (viaSeg) {
      const ok1 = await page.evaluate((n) => { const b = [...document.querySelectorAll('#tools-panel .sc-nseg .seg-btn')].find(x => x.dataset.v === n); if (b) { b.click(); return true; } return false; }, n);
      if (!ok1) { out[n] = 'нет кнопки ' + n; continue; }
    } else await page.evaluate((n) => { const s = document.getElementById('ineq-ngroups'); s.value = n; s.dispatchEvent(new Event('change', { bubbles: true })); }, n);
    await page.waitForTimeout(600);
    out[n] = (await answerNums(page)) + '#rows=' + (await page.evaluate(() => document.querySelectorAll('#ineq-groups-table input').length));
  }
  await page.evaluate(() => { const s = document.getElementById('tau-dummy'); void s; document.getElementById('ineq-redist').click(); });
  await page.waitForTimeout(400);
  await page.evaluate(() => { const t = document.getElementById('ineq-tau'); t.value = '0.4'; t.dispatchEvent(new Event('input', { bubbles: true })); t.dispatchEvent(new Event('change', { bubbles: true })); });
  await page.waitForTimeout(500);
  out.tau = await answerNums(page);
  return out;
}
async function zhIneq(before) {
  if (KEYS && !KEYS.includes('ineq')) return;
  const { ctx, page, errors } = await openAt(BASE);
  await pick(page, 'ineq');
  const look = await page.evaluate(() => {
    const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
    const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ' ').trim(); };
    const seg = [...document.querySelectorAll('#tools-panel .sc-nseg .seg-btn')].filter(vis).map(tx);
    const listShown = [...document.querySelectorAll('#ineq-pane-groups .sel-btn, #ineq-ngroups')].some(vis);
    const ms = document.getElementById('ineq-master-slider');
    const acc = (() => { const d = document.createElement('div'); d.style.color = 'var(--accent)'; document.body.appendChild(d); const c = getComputedStyle(d).color; d.remove(); return c; })();
    return { seg, listShown, accent: ms ? getComputedStyle(ms).accentColor : null, acc, masterLab: ms ? tx(ms.closest('.pchip').querySelector('.pchip-label')) : '' };
  });
  ok('ineq: «Число групп» — сегмент «5 групп | 10 групп», прежнего списка не видно', look.seg.join('|') === '5 групп|10 групп' && !look.listShown, JSON.stringify(look));
  ok('ineq: «Сила неравенства» — дорожка цвета --accent (' + look.accent + ')', look.masterLab === 'Сила неравенства' && look.accent === look.acc, JSON.stringify(look));
  await page.evaluate(() => document.getElementById('ineq-redist').click()); await page.waitForTimeout(400);
  const tau = await page.evaluate(() => { const f = document.getElementById('ineq-tau-field'); const tx = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ''); }; return { name: tx(f.querySelector('.sc-pname')), val: tx(f.querySelector('.sc-pval')), katex: !!f.querySelector('.sc-pval .katex') }; });
  ok('ineq: строка «Прогрессивность τ = 0» — слова слева, значение KaTeX справа (' + JSON.stringify(tau) + ')', tau.name === 'Прогрессивность' && tau.val === 'τ=0' && tau.katex, JSON.stringify(tau));
  await pick(page, 'ineq');
  const now = await ineqSeries(page, true);
  if (before) {
    const diff = Object.keys(before).filter(k => before[k] !== now[k]);
    ok('ineq: «5 | 10 групп» сегментом, перераспределение τ = 0,4 — «Ответ» тот же, что на коде до сессии (' + JSON.stringify(Object.keys(now).map(k => k + ':' + String(now[k]).split('#rows=')[1])) + ')', !diff.length && /rows=10/.test(now['10']) && /rows=5/.test(now['5']), diff.map(k => k + ': было ' + String(before[k]).slice(0, 80) + ' / стало ' + String(now[k]).slice(0, 80)).join(' | '));
  } else ok('ineq: сравнение с кодом до сессии НЕ ПРОВЕРЕНО (нет BEFORE)', false, '');
  ok('ineq: ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

const inv = fs.existsSync(INV) ? JSON.parse(fs.readFileSync(INV, 'utf8')).models : null;
// «До обёртки»: контрольная запись на сервере BEFORE (Chromium, один раз).
const beforeMap = {};
try {
  const b0 = await pw.chromium.launch();
  browser = b0; engName = 'chromium';
  const probe = await fetch(BEFORE + '/calc2/').then(r => r.ok).catch(() => false);
  if (probe) {
    for (const [sec, key, label, extra, ctl] of CASES) {
      if (!want(sec) || (KEYS && !KEYS.includes(key))) continue;
      const { ctx, page } = await openAt(BEFORE);
      await pick(page, key, extra);
      const ids = await formulaIds(page);
      const t = await typeAndRead(page, ctl[0], ctl[1]);
      if (!t.missing) beforeMap[key + '|' + label] = Object.assign(t, { ids });
      await ctx.close();
    }
    if (want('К')) beforeMap.kCases = await kCases(BEFORE);
    if (want('Ж') && (!KEYS || KEYS.includes('ineq'))) {
      const { ctx, page } = await openAt(BEFORE);
      await pick(page, 'ineq');
      beforeMap.ineq = await ineqSeries(page, false);
      await ctx.close();
    }
    if (want('Д')) {
      beforeMap.cons = {};
      for (const key of ['consumer', 'cons-slutsky']) {
        if (KEYS && !KEYS.includes(key)) continue;
        const { ctx, page } = await openAt(BEFORE);
        await pick(page, key);
        beforeMap.cons[key] = await consSeries(page, false);
        await ctx.close();
      }
    }
  } else console.log('\n!!! сервер BEFORE (' + BEFORE + ') недоступен — сравнение ввода с кодом до обёртки НЕ ПРОВЕРЕНО');
  await b0.close();
} catch (e) { console.log('!!! замер «до» не удался: ' + String(e).slice(0, 160)); }

for (const name of ENGINES) {
  eng = name; engName = name; ctxCount = 0;
  try { browser = await pw[name].launch(); } catch (e) {
    console.log('\n!!! ' + name + ': движок не запустился — НЕ ПРОВЕРЕНО (' + String(e).slice(0, 120) + ')');
    continue;
  }
  if (want('К')) {
    head('К. Один вид карточки, числа плашкой (сессия 6)');
    await kRun('light');
    await kRun('dark');
    if (!KEYS || KEYS.includes(K_CASES_REC[0])) {
      const now = await kCases(BASE), was = beforeMap.kCases;
      ok('К: кусочная запись карточки — как на коде до сессии (' + JSON.stringify(now) + ')', !!now && now.tall && (!was || JSON.stringify(now) === JSON.stringify(was)), 'было ' + JSON.stringify(was || 'BEFORE недоступен'));
    }
  }
  if (want('Д')) { head('Д. Потребитель: карточка U, «Параметры»'); await dRun(beforeMap.cons); }
  if (want('Е')) { head('Е. Макро: карточки, строки, нет ползунка переменной оси'); await eRun(); }
  if (want('Ж')) { head('Ж. Неравенство и математика'); await zhIneq(beforeMap.ineq); }
  if (want('М') && (!KEYS || KEYS.includes('tradeprice'))) { head('М. Мировая цена КТВ: строка и «Ответ»'); await mRun(); }
  let last = '';
  for (const [sec, key, label, extra, ctl] of CASES) {
    if (!want(sec) || (KEYS && !KEYS.includes(key))) continue;
    if (sec !== last) { head(sec + '. ' + { 'Б': 'КПВ и торговля', 'В': 'Фирма', 'Г': 'Монополия, труд, малая открытая', 'Д': 'Потребитель (общие проверки карточек)', 'Е': 'Макро (общие проверки карточек)', 'Ж': 'Неравенство и математика (общие проверки карточек)' }[sec]); last = sec; }
    await runCase(sec, key, label, extra, ctl, inv, beforeMap[key + '|' + label]);
  }
  await browser.close();
}
console.log('\nИТОГ cards_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
