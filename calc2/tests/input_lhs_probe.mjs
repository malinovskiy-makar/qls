/* ВВОД ФОРМУЛ: ЛЕВАЯ ЧАСТЬ, Q(P) ВО ВСЕХ МОДЕЛЯХ, ОШИБКИ ПО-РУССКИ
   (сессия А1 24.10, карточки Notion …81be… и …816c…, ADR 0157).

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/input_lhs_probe.mjs

   Стережёт ПРАВИЛА, а не устройство кода:
     Л  — запись с левой частью («Q = 100 − 2P», «Qd = …») считается так же, как без неё;
          неверная левая часть и «P = 100 − 2P» — ошибка под полем ПО-РУССКИ, и она видна
          после Enter; приставка поля идёт за формой записи сразу; строка «в расчётах»
          без десятичной точки, простая дробь — дробью;
     М  — запись Q(P) в моделях со своими полями (Лаффер, дискриминация 3-й степени,
          внешний рынок, составной спрос, AD–AS) даёт тот же ответ, что запись P(Q);
     Е  — сообщения Math.js переведены, английских слов на экране нет.
   Набор в список кривых — НАСТОЯЩЕЙ клавиатурой MathLive (мост поля и Enter — часть
   правила: 24.10 ошибка терялась ровно на Enter). Поля сцен — тем же событием input,
   что шлёт мост (setFieldValue).

   ⚠️ Расходится число — сломан движок, а не прибор. */
import { chromium } from 'playwright';
import { keepAnswerOpen } from './answer_open.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
keepAnswerOpen(browser);
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0, total = 0;
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length)));
function ok(label, cond, got) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (cond ? '' : '  -> ' + JSON.stringify(got)));
}
const near = (a, b, tol) => typeof a === 'number' && isFinite(a) && Math.abs(a - b) <= tol;
/* Текст узла БЕЗ невидимой копии формулы для чтецов экрана: textContent у набранной KaTeX
   буквы утраивает её («PPP», ловушка calc2/CLAUDE.md). */
const PLAIN = `var plain = function (el) { if (!el) return ''; var c = el.cloneNode(true);
  [].forEach.call(c.querySelectorAll('.katex-mathml, annotation'), function (n) { n.remove(); }); return c.textContent; };`;
const run = (code) => page.evaluate(async (c) => { const out = (new Function(c))(); await new Promise(r => setTimeout(r, 80)); return out; }, PLAIN + code);
// Английское слово на экране — три латинские буквы подряд (обозначения вроде P, MC, TR в
// сообщениях ввода не встречаются, кроме одиночных букв).
const ENGLISH = /[A-Za-z]{3,}/;

/* Набрать запись в поле кривой списка настоящей клавиатурой и нажать Enter. */
async function typeCurve(scene, idx, text) {
  await run(`resetSceneMemory(); pickScene('${scene}'); redrawAll();`);
  await page.waitForTimeout(500);
  const mf = page.locator('#curve-list .fc-card').nth(idx).locator('math-field');
  await mf.click(); await page.waitForTimeout(150);
  await page.keyboard.press('Meta+a'); await page.waitForTimeout(150);
  await page.keyboard.press('Backspace'); await page.waitForTimeout(300);
  await page.keyboard.type(text, { delay: 60 });
  await page.keyboard.press('Enter'); await page.waitForTimeout(900);
  return run(`var card = document.querySelectorAll('#curve-list .fc-card')[${idx}];
    var pre = card.querySelector('.fc-prefix'), why = card.querySelector('.f-why'), qp = card.querySelector('.fc-qp-math');
    var ann = qp && qp.querySelector('annotation');
    var preAnn = pre && pre.querySelector('annotation');
    return { eq: STATE.eq, inp: card.querySelector('.curve-expr-inp').value,
      pre: preAnn ? preAnn.textContent : (pre ? pre.textContent : ''),
      preShown: !!(pre && getComputedStyle(pre).display !== 'none'),
      why: plain(why), qp: ann ? ann.textContent : (qp ? qp.textContent : null),
      bad: card.querySelector('.curve-expr-inp').classList.contains('bad') };`);
}
/* Что читает человек слева от записи: видимая приставка либо своя левая часть поля. */
const readsAs = (r) => r.preShown ? r.pre.replace(/\\,/g, '').replace(/\s/g, '') : (r.inp.split('=')[0].trim() + '=');

head('Л · левая часть записи в списке кривых («Спрос и предложение», S: P = Q)');
const third = 100 / 3;
for (const t of ['Q=100-2P', 'Qd=100-2P', '100-2P']) {
  const r = await typeCurve('sd', 0, t);
  ok(`«${t}»: Q* = 100/3`, near(r.eq && r.eq.Q, third, 1e-6), r.eq);
  ok(`«${t}»: P* = 100/3`, near(r.eq && r.eq.P, third, 1e-6), r.eq);
  ok(`«${t}»: читается «Q = …», а не «P = …»`, /^Q/.test(readsAs(r)), { pre: r.pre, shown: r.preShown, inp: r.inp });
  ok(`«${t}»: ошибки под полем нет`, !r.bad && !r.why, r.why);
  ok(`«${t}»: строка «в расчётах» — дробью, без десятичной точки`, !!r.qp && r.qp.indexOf('\\frac{1}{2}') >= 0 && !/\d\.\d/.test(r.qp), r.qp);
}
{
  const r = await typeCurve('sd', 0, 'P=100-Q');
  ok('«P=100-Q»: 50; 50, приставка «P =»', near(r.eq && r.eq.Q, 50, 1e-6) && /^P/.test(readsAs(r)), { eq: r.eq, pre: r.pre });
}
for (const [t, want] of [['P=100-2P', /Справа от .P =. не должно быть P/], ['Q=100-2Q', /Справа от .Q =. не должно быть Q/],
                         ['Z=100-2P', /Слева от .=. понятны Q, P или имя поля/], ['100-', /Формула оборвалась/]]) {
  const r = await typeCurve('sd', 0, t);
  ok(`«${t}»: ошибка под полем видна после Enter`, r.bad && !!r.why, { why: r.why, bad: r.bad });
  ok(`«${t}»: текст ошибки по правилу`, want.test(r.why), r.why);
  ok(`«${t}»: в ошибке нет английских слов`, !ENGLISH.test(r.why), r.why);
}
{
  /* Приставка СРАЗУ: «100 − Q» правится на «100 − 2P» — «Q =» без перезагрузки. */
  const r = await typeCurve('sd', 0, '100-2P');
  ok('правка «100 − Q» → «100 − 2P»: приставка видна и это «Q =»', r.preShown && /^Q/.test(r.pre), { pre: r.pre, shown: r.preShown });
  const r2 = await typeCurve('sd', 1, '3P-60');
  ok('S «3P − 60»: в расчётах P = \\frac{1}{3}Q + 20', !!r2.qp && r2.qp.replace(/\s/g, '').indexOf('\\frac{1}{3}Q+20') >= 0, r2.qp);
}

head('М · запись Q(P) в моделях со своими полями');
const SET = `var put = function (id, v) { var e = document.getElementById(id); setFieldValue(e, v); e.dispatchEvent(new Event('change')); };`;
{
  const q = await run(`resetSceneMemory(); pickScene('laffer'); STATE.macro.laffer.d = '120 - P'; STATE.macro.laffer.s = 'P'; redrawAll();
    var r = STATE.macroRes; return { err: STATE.macroErr, t: r && r.best.t, rev: r && r.best.rev };`);
  const p = await run(`resetSceneMemory(); pickScene('laffer'); STATE.macro.laffer.d = '120 - Q'; STATE.macro.laffer.s = 'Q'; redrawAll();
    var r = STATE.macroRes; return { err: STATE.macroErr, t: r && r.best.t, rev: r && r.best.rev, tmax: STATE.macro.laffer.tmax };`);
  const l = await run(`resetSceneMemory(); pickScene('laffer'); STATE.macro.laffer.d = 'Q = 120 - P'; STATE.macro.laffer.s = 'Q = P'; redrawAll();
    var r = STATE.macroRes; return { err: STATE.macroErr, t: r && r.best.t, rev: r && r.best.rev };`);
  ok('Лаффер, D: Q = 120 − P, S: Q = P — график строится, ошибки нет', !q.err && q.t != null, q);
  ok('Лаффер: максимум при t = 60', near(q.t, 60, 1e-9), q);
  ok('Лаффер: сбор T = 1 800', near(q.rev, 1800, 1e-6), q);
  ok('Лаффер: предел ставки модели не меньше 60', p.tmax >= 60, p.tmax);
  ok('Лаффер: Q(P) и P(Q) совпадают до 1e-9', near(q.t, p.t, 1e-9) && near(q.rev, p.rev, 1e-9), { q, p });
  ok('Лаффер: запись с левой частью «Q = 120 − P» — то же', near(l.t, p.t, 1e-9) && near(l.rev, p.rev, 1e-9), l);
}
{
  const d3 = (d1, d2) => run(`resetSceneMemory(); pickScene('mono-d3'); STATE.d3D1 = '${d1}'; STATE.d3D2 = '${d2}'; STATE.d3MC = '20'; redrawAll();
    var d = STATE.discr3 || {}; return { found: d.found, q1: d.q1, q2: d.q2, P1: d.P1, P2: d.P2 };`);
  const a = await d3('120 - Q', '80 - Q'), b = await d3('120 - P', '80 - P'), c = await d3('Q = 120 - P', 'P = 80 - Q');
  const same = (x, y) => ['q1', 'q2', 'P1', 'P2'].every(k => near(x[k], y[k], 1e-9));
  ok('Дискриминация 3-й степени: оба спроса Q(P) — ответ найден', b.found === true, b);
  ok('Дискриминация 3-й степени: Q(P) и P(Q) совпадают до 1e-9', same(a, b), { a, b });
  ok('Дискриминация 3-й степени: «Q = 120 − P» и «P = 80 − Q» — то же', same(a, c), { a, c });
}
{
  const r = await run(`resetSceneMemory(); pickScene('monoexport'); STATE.d3D1 = 'Q = 100 - P'; STATE.d3D2 = '50'; STATE.d3MC = 'Q'; redrawAll();
    var d = STATE.discr3 || {}; return { found: d.found, q1: d.q1, P1: d.P1, q2: d.q2 };`);
  ok('Монополист и внешний рынок, D: Q = 100 − P: внутри 25', near(r.q1, 25, 1e-3), r);
  ok('…по цене 75', near(r.P1, 75, 1e-3), r);
  ok('…экспорт 25', near(r.q2, 25, 1e-3), r);
}
{
  const r = await run(`resetSceneMemory(); pickScene('mono-kink'); STATE.kinkInput = 'individual';
    STATE.kiD1 = '100 - P'; STATE.kiD2 = 'Q = 60 - P'; STATE.kiD3 = ''; STATE.kinkMC = '20'; redrawAll();
    var k = STATE.kinked || {}; return { found: k.found, Q: k.Qstar, P: k.Pstar };`);
  ok('Составной спрос, D₁: 100 − P, D₂: Q = 60 − P — Q 60', near(r.Q, 60, 1e-3), r);
  ok('…P 50', near(r.P, 50, 1e-3), r);
}
{
  const ad = (e) => run(`resetSceneMemory(); pickScene('adas'); STATE.macro.adas.ad = '${e}'; redrawAll();
    var r = STATE.macroRes; return { err: STATE.macroErr, eq: r && r.eq };`);
  const a = await ad('400 + 1600/P'), b = await ad('Y = 400 + 1600/P'), c = await ad('P = 1600/(Y - 400)');
  ok('AD–AS, AD: 400 + 1600/P — равновесие найдено, ошибки нет', !a.err && !!a.eq, a);
  ok('AD–AS: «400 + 1600/P» и «P = 1600/(Y − 400)» — то же равновесие', !!a.eq && !!c.eq && near(a.eq.Q, c.eq.Q, 1e-6) && near(a.eq.P, c.eq.P, 1e-6), { a, c });
  ok('AD–AS: «Y = 400 + 1600/P» — то же равновесие', !!b.eq && !!c.eq && near(b.eq.Q, c.eq.Q, 1e-6) && near(b.eq.P, c.eq.P, 1e-6), { b, c });
}
{
  /* Ошибка в поле сцены видна под полем (а у составного спроса прежде был пустой экран). */
  const r = await run(SET + `resetSceneMemory(); pickScene('mono-kink'); redrawAll();
    put('inp-ki-1', 'P = 100 - 2P'); return null;`);
  await page.waitForTimeout(500);
  const w = await run(`var e = document.getElementById('inp-ki-1'); var host = e.closest('.f-wrap'); var why = host && host.querySelector('.f-why');
    return { why: plain(why), shown: !!(why && why.offsetParent), bad: e.classList.contains('bad') };`);
  ok('Составной спрос: «P = 100 − 2P» — ошибка под полем видна', w.bad && w.shown && /Справа от/.test(w.why), w);
  ok('…без английских слов', !ENGLISH.test(w.why), w.why);
  const r2 = await run(`resetSceneMemory(); pickScene('mono-kink'); STATE.kinkInput = 'individual'; STATE.kiD1 = 'Q = 50'; redrawAll();
    var b = document.getElementById('kink-error'); return { txt: plain(b), shown: !!(b && b.offsetParent && getComputedStyle(b).display !== 'none') };`);
  ok('Составной спрос: ошибка разбора «Q = 50» дошла до экрана', r2.shown && r2.txt.length > 0, r2);
  ok('…по-русски', !ENGLISH.test(r2.txt), r2.txt);
  void r;
}

head('Е · ошибки Math.js по-русски');
{
  const r = await run(`return {
    a: mathErrorRu('Undefined symbol X'), b: mathErrorRu('Unexpected end of expression (char 5)'),
    c: mathErrorRu('Parenthesis ) expected (char 7)'), d: mathErrorRu('Unexpected operator / (char 3)'),
    e: mathErrorRu('Value expected (char 4)'), f: mathErrorRu('Something completely different'),
    g: compileFormula('100 - (Q').error, h: compileFormulaP('100 -').error };`);
  ok('Undefined symbol X → «Не знаю букву X»', r.a === 'Не знаю букву X', r.a);
  ok('Unexpected end → «Формула оборвалась»', r.b === 'Формула оборвалась', r.b);
  ok('Parenthesis ) expected → «Не хватает закрывающей скобки»', r.c === 'Не хватает закрывающей скобки', r.c);
  ok('Unexpected operator → «Лишний или пропущенный знак»', r.d === 'Лишний или пропущенный знак', r.d);
  ok('Value expected → «Лишний или пропущенный знак»', r.e === 'Лишний или пропущенный знак', r.e);
  ok('прочее → «Не понял формулу» без английского', r.f === 'Не понял формулу', r.f);
  ok('compileFormula отвечает по-русски', !!r.g && !ENGLISH.test(r.g), r.g);
  ok('compileFormulaP отвечает по-русски', !!r.h && !ENGLISH.test(r.h), r.h);
  const m = await run(`resetSceneMemory(); pickScene('laffer'); STATE.macro.laffer.d = '120 - (P'; redrawAll();
    return { err: STATE.macroErr, box: (document.getElementById('macro-error') || {}).textContent };`);
  ok('Лаффер: ошибка разбора по-русски', !!m.err && !ENGLISH.test(m.err), m);
  const p = await run(`resetSceneMemory(); pickScene('sd'); redrawAll(); var c = STATE.curves.find(function (x) { return x.role === 'demand'; });
    return { two: updateCurveExpr(c, 'Q = 100 - P = 3'), expr: c.expr, form: c.srcForm };`);
  ok('два знака «=» — ошибка, кривая прежняя', /два знака/.test(p.two || '') && p.form === 'PQ', p);
}

/* ── А2 24.10 (ADR 0158): промежуточная запись не остаётся кривой; правка спрятанной кривой показывает её ── */
head('Н · «P=100-2P» по символу: кривая идёт за записью, после ошибки — запись до правки');
{
  await run(`resetSceneMemory(); pickScene('sd'); redrawAll();`);
  await page.waitForTimeout(500);
  const mf = page.locator('#curve-list .fc-card').first().locator('math-field');
  await mf.click(); await page.waitForTimeout(150);
  await page.keyboard.press('Meta+a'); await page.waitForTimeout(150);
  const seen = {};
  for (const ch of 'P=100-2P') {
    await page.keyboard.type(ch); await page.waitForTimeout(300);
    const r = await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); return { expr: d.expr, Q: STATE.eq && STATE.eq.Q };`);
    seen[ch === 'P' && seen['2'] ? 'P2' : ch] = r;
  }
  ok('по дороге «P=100-2» — кривая идёт за записью (Q* 98)', near(seen['2'] && seen['2'].Q, 98, 1e-6), seen['2']);
  await page.keyboard.press('Enter'); await page.waitForTimeout(900);
  const r = await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); var card = document.querySelector('#curve-list .fc-card');
    return { expr: d.expr, eq: STATE.eq, why: plain(card.querySelector('.f-why')), bad: card.querySelector('.curve-expr-inp').classList.contains('bad') };`);
  ok('после Enter: ошибка под полем по-русски', r.bad && !!r.why && !ENGLISH.test(r.why), r.why);
  ok('…кривая — запись до правки «100 - Q»', r.expr === '100 - Q', r.expr);
  ok('…равновесие 50; 50', near(r.eq && r.eq.Q, 50, 1e-6) && near(r.eq && r.eq.P, 50, 1e-6), r.eq);
  ok('…в сообщении — «запись до правки»', /запись до правки/.test(r.why), r.why);
}

head('Н · правка формулы спрятанной кривой показывает её (один шаг истории)');
{
  await run(`resetSceneMemory(); pickScene('sd'); redrawAll();`);
  await page.waitForTimeout(500);
  await page.locator('#curve-list .fc-card').first().locator('.fc-eye').click();
  await page.waitForTimeout(1400);
  const h = await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); return { vis: d.visible, eq: STATE.eq };`);
  ok('D спрятана глазом — равновесия нет', h.vis === false && !h.eq, h);
  const mf = page.locator('#curve-list .fc-card').first().locator('math-field');
  await mf.click(); await page.waitForTimeout(150);
  await page.keyboard.press('Meta+a'); await page.keyboard.press('Backspace');
  await page.keyboard.type('120-Q', { delay: 60 }); await page.keyboard.press('Enter'); await page.waitForTimeout(1400);
  const r = await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); var card = document.querySelector('#curve-list .fc-card');
    var eye = card.querySelector('.fc-eye');
    return { vis: d.visible, expr: d.expr, eq: STATE.eq, hidden: card.classList.contains('is-hidden'), pressed: eye.getAttribute('aria-pressed') };`);
  ok('после правки D видна', r.vis === true && !r.hidden && r.pressed === 'false', r);
  ok('…и в расчёте: равновесие 60; 60', near(r.eq && r.eq.Q, 60, 1e-6) && near(r.eq && r.eq.P, 60, 1e-6), r.eq);
  await run(`historyUndo();`); await page.waitForTimeout(900);
  const u = await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); return { vis: d.visible, expr: d.expr };`);
  ok('одно «Отменить» возвращает и формулу, и спрятанность', u.vis === false && u.expr === '100 - Q', u);

  await run(`resetSceneMemory(); pickScene('ext'); closePicker(); redrawAll();`);
  await page.waitForTimeout(600);
  const e0 = await run(`return { on: STATE.msbOn, chk: document.getElementById('chk-msb').checked };`);
  ok('«Внешние эффекты»: MSB на старте спрятана', !e0.on && !e0.chk, e0);
  const mb = page.locator('#inp-msb').locator('xpath=ancestor::*[contains(@class,"f-slot")][1]').locator('math-field');
  await mb.click(); await page.waitForTimeout(150);
  await page.keyboard.press('Meta+a'); await page.keyboard.press('Backspace');
  await page.keyboard.type('120-Q', { delay: 60 }); await page.keyboard.press('Enter'); await page.waitForTimeout(1400);
  const e1 = await run(`var c = document.querySelector('#inp-msb').closest('.sc-extcard'); var eye = c && c.querySelector('.fc-eye');
    var labels = [].map.call(document.querySelectorAll('#chart text'), function (t) { return t.textContent.trim(); });
    return { on: STATE.msbOn, chk: document.getElementById('chk-msb').checked, eye: eye && eye.getAttribute('aria-pressed'),
      onChart: labels.indexOf('MSB') >= 0, Qopt: STATE.ext && STATE.ext.Qopt };`);
  ok('правка MSB включила её глаз', e1.on && e1.chk && e1.eye === 'true', e1);
  ok('…MSB на графике и в расчёте: оптимум 120 − Q = Q + 20 → Q 50', e1.onChart && near(e1.Qopt, 50, 1e-4), e1);
  await run(`historyUndo();`); await page.waitForTimeout(900);
  const e2 = await run(`return { on: STATE.msbOn, chk: document.getElementById('chk-msb').checked, Qopt: STATE.ext && STATE.ext.Qopt };`);
  ok('одно «Отменить» прячет MSB и возвращает оптимум 40', !e2.on && !e2.chk && near(e2.Qopt, 40, 1e-4), e2);
  const e3 = await run(`resetSceneMemory(); pickScene('ext'); closePicker(); redrawAll(); return new Promise(function (res) { setTimeout(function () { res({ on: STATE.msbOn }); }, 700); });`);
  ok('старт сам MSB не включает (умолчание MSB = D — не правка)', e3.on === false, e3);
}

head('Н · «Квоты»: точное значение цены за коридором прижимается к краю');
{
  // Сначала цена 45 (иначе 60 стояло бы и без прижима: это цена по умолчанию).
  await run(`resetSceneMemory(); pickScene('quota'); closePicker(); redrawAll(); setQuotaPrice(45);`);
  await page.waitForTimeout(600);
  ok('предусловие: цена 45', near(await run(`return STATE.qt && STATE.qt.P;`), 45, 1e-9));
  const eq = page.locator('#quota-price-field .reg-eq');
  ok('строка «Цена внутри коридора» видна', await eq.count() > 0 && await eq.isVisible(), await eq.count());
  await eq.click(); await page.waitForTimeout(200);
  ok('щелчок по строке открыл точный ввод', await run(`var a = document.activeElement; return !!a && a.tagName === 'INPUT' && !!a.closest('#quota-price-field');`));
  await page.keyboard.press('Meta+a'); await page.keyboard.type('100'); await page.keyboard.press('Enter'); await page.waitForTimeout(700);
  const r = await run(`var sl = document.getElementById('quota-price-slider'); return { P: STATE.qt && STATE.qt.P, min: +sl.min, max: +sl.max, v: +sl.value,
    lab: plain(document.querySelector('#quota-price-field .reg-eq')), bbh: sl.dataset.boundsByHand || '' };`);
  ok('ввод 100 → цена 60 (верх коридора)', near(r.P, 60, 1e-9), r);
  ok('…ползунок 40…60 и стоит на 60', r.min === 40 && r.max === 60 && r.v === 60, r);
  ok('…подпись показывает прижатое 60', /60/.test(r.lab) && !/100/.test(r.lab), r.lab);
  ok('…полоса не переехала', !r.bbh, r.bbh);
}

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
if (errs.length) bad++;
console.log(bad ? ('ПРОВАЛОВ: ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' ПРОВЕРОК ВВОДА СОШЛИСЬ'));
await browser.close();
process.exit(bad ? 1 : 0);
