/* КАРТОЧКИ ФУНКЦИЙ ЛЕВОЙ ПАНЕЛИ (тихие панели, сессия 5, 14.10.2026; решение владельца «левая панель одна во
   всех моделях и только про условие», Notion …8142…; ADR 0153; README пакета 4, 8).

   Разделы (--only Б,В,Г) — модели этапов сессии 5:
     Б  ppf, ppfsum, trade, tradeprice;   В  prod, costs (и «Задаю кривые»), plants, isoquant;
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
];

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
  await page.evaluate(([id, v]) => setFieldValue(document.getElementById(id), v), [id, expr]);
  await page.waitForTimeout(700);
  const after = await answerNums(page);
  await page.evaluate(([id, v]) => setFieldValue(document.getElementById(id), v), [id, was]);
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
  ok(tag + ': каждое поле формулы в карточке (' + r.cards + ' карточек)', r.cards > 0 && !r.bare.length, 'голые: ' + r.bare.join(', '));
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
    const ids = await formulaIds(page);
    ok(tag + ': ОРГАН — id полей формул те же, что до обёртки (' + beforeAns.ids + ')', ids === beforeAns.ids, 'сейчас ' + ids);
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
  } else console.log('\n!!! сервер BEFORE (' + BEFORE + ') недоступен — сравнение ввода с кодом до обёртки НЕ ПРОВЕРЕНО');
  await b0.close();
} catch (e) { console.log('!!! замер «до» не удался: ' + String(e).slice(0, 160)); }

for (const name of ENGINES) {
  eng = name; engName = name; ctxCount = 0;
  try { browser = await pw[name].launch(); } catch (e) {
    console.log('\n!!! ' + name + ': движок не запустился — НЕ ПРОВЕРЕНО (' + String(e).slice(0, 120) + ')');
    continue;
  }
  let last = '';
  for (const [sec, key, label, extra, ctl] of CASES) {
    if (!want(sec) || (KEYS && !KEYS.includes(key))) continue;
    if (sec !== last) { head(sec + '. ' + { 'Б': 'КПВ и торговля', 'В': 'Фирма', 'Г': 'Монополия, труд, малая открытая' }[sec]); last = sec; }
    await runCase(sec, key, label, extra, ctl, inv, beforeMap[key + '|' + label]);
  }
  await browser.close();
}
console.log('\nИТОГ cards_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
