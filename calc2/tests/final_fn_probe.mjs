/* Прибор отсмотра 26.08: единый блок «Итоговая функция», четыре дефекта,
   аналитическое сложение КПВ.

   Числа печатаются ВСЕГДА, а не только при провале: этим прибором снимаются
   и «до», и «после».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/final_fn_probe.mjs              # все наборы
     node calc2/tests/final_fn_probe.mjs Д1 Д3        # только эти

   Наборы:
     Д1 — обрыв суммарной кривой при отдалении (последняя точка пути);
     Д2 — подсказка суммарной кривой: язык, связка, хвост, ширина плашки;
     Д3 — субсидия покупателю: какая кривая сдвинута, её имя, текст подсказки;
     Д4 — запись суммарной КПВ: где стоит и помещается ли по ширине;
     Ф  — единый блок «Итоговая функция» во всех четырёх сценах.

   ⚠️ ПРИБОР ОБЯЗАН САМ РАСКРЫТЬ ЭКРАН. Считать только раскрытое — значит
   занижать. Каждый признак снимается ДВУМЯ способами: числом и снимком.
*/
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SHOTS = process.env.FF_SHOTS || 'reports/calc2_final_function/before';

const want = process.argv.slice(2);
const need = (name) => !want.length || want.includes(name);
fs.mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0;
const num = (v) => (typeof v === 'number' && isFinite(v)) ? (Math.round(v * 1e4) / 1e4) : String(v);
function show(label, got, wanted, tol) {
  if (wanted == null) { console.log('     ' + label + ' = ' + num(got)); return; }
  const good = typeof got === 'number' && isFinite(got) && Math.abs(got - wanted) <= tol;
  if (!good) bad++;
  console.log((good ? 'OK   ' : 'FAIL ') + label + ' = ' + num(got) + '   (ожид ' + wanted + ' ±' + tol + ')');
}
function flag(label, cond, detail) {
  if (!cond) bad++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (detail != null ? '  -> ' + detail : ''));
}
function note(s) { console.log('     ' + s); }
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 66 - s.length))); }
async function shot(name) {
  const p = SHOTS + '/' + name + '.png';
  await page.screenshot({ path: p });
  console.log('     снимок: ' + p);
}

/* Помощники, живущие в СТРАНИЦЕ. Ставятся один раз на загрузку. */
const HELP = `
function ffExpandAll() {
  document.querySelectorAll('.crow-more').forEach(function (m) { m.classList.add('open'); });
  document.querySelectorAll('details').forEach(function (d) { d.open = true; });
  document.querySelectorAll('.sb-card.folded, .card.folded, .pchip-param.folded')
    .forEach(function (e) { e.classList.remove('folded'); });
  document.querySelectorAll('.fold-btn').forEach(function (b) {
    if (b.getAttribute('aria-expanded') !== 'true') b.click();
  });
  ['tools-panel', 'params-body', 'side-body', 'ex-body', 'info-body', 'sb-body']
    .forEach(function (id) { var e = document.getElementById(id); if (e) e.scrollTop = 0; });
  document.querySelectorAll('.panel, .side, .sb, .drawer, .side-scroll').forEach(function (e) { e.scrollTop = 0; });
}
function ffVisible(el) {
  if (!el) return false;
  if (!(el.offsetParent || el.getClientRects().length)) return false;
  var cs = getComputedStyle(el);
  return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity || '1') > 0.01;
}
/* Видимый текст поддерева: скрытые стилем ветки выбрасываем. Ровно этим
   прибор врал раньше — .sb-note-src лежит в табло, но человеку не показан. */
function ffTextVisible(el) {
  if (!el) return '';
  var out = [];
  (function walk(n) {
    if (n.nodeType === 3) { out.push(n.nodeValue); return; }
    if (n.nodeType !== 1) return;
    if (n.classList && (n.classList.contains('katex-mathml'))) return;
    if (n.tagName === 'ANNOTATION') return;
    if (!ffVisible(n)) return;
    Array.prototype.forEach.call(n.childNodes, walk);
  })(el);
  return out.join(' ').replace(/\s+/g, ' ').trim();
}
function ffText(el) {
  if (!el) return '';
  var c = el.cloneNode(true);
  c.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
  return c.textContent.replace(/\\s+/g, ' ').trim();
}
/* Точки пути кривой в координатах МОДЕЛИ. Читаем сам атрибут d, а не формулу:
   врать умеет ровно разрыв между расчётом и отрисовкой. */
function ffPathPoints(sel) {
  var el = document.querySelector(sel);
  if (!el) return null;
  var pts = [];
  String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
    var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
    if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
  });
  return pts;
}
/* Сплошная (не «призрачная») часть суммарной кривой стороны side. */
function ffSumPath(side) {
  var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === side; });
  if (!c) return null;
  var real = document.querySelector('path[data-curve="' + c.id + '"][data-sum-part="real"]');
  var plain = document.querySelector('path[data-curve="' + c.id + '"]:not([data-sum-part])');
  var el = real || plain;
  if (!el) return null;
  var pts = [];
  String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
    var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
    if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
  });
  return { n: pts.length, first: pts[0] || null, last: pts[pts.length - 1] || null,
           expr: c.expr, breaks: (c.sumBreaks || []).slice(), domainTo: c.sumDomainTo || null };
}
/* Место подписи кривой на холсте (текст .curve-name с нужной надписью). */
function ffLabelAt(txt, curve) {
  var out = null;
  document.querySelectorAll('text.curve-name').forEach(function (t) {
    if (ffText(t) === txt && !out) {
      /* Место подписи берём из САМИХ атрибутов x/y — они уже в системе
         координат холста, и путать их с экранным прямоугольником не надо. */
      var q = sx.invert(+t.getAttribute('x'));
      var p = sy.invert(+t.getAttribute('y'));
      var v = curve ? evalCurve(curve, q) : NaN;
      /* Подпись ставится с отступом от линии (±7 и ±14 px по вертикали),
         поэтому «на линии» меряем в ПИКСЕЛЯХ и с запасом на этот отступ. */
      var gapPx = isFinite(v) ? Math.abs(sy(v) - (+t.getAttribute('y'))) : Infinity;
      out = { q: q, p: p, v: v, gap: isFinite(v) ? Math.abs(v - p) : Infinity,
              gapPx: Math.round(gapPx * 10) / 10,
              onCurve: isFinite(v) && gapPx <= 22 };
    }
  });
  return out;
}
/* Сцена налогов: свои кривые, свой вид вмешательства, своя ставка и сторона. */
function ffTaxSetup(dExpr, sExpr, type, form, side, rate) {
  resetSceneMemory();
  pickScene('taxes');
  var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
  var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
  if (d) updateCurveExpr(d, dExpr);
  if (s) updateCurveExpr(s, sExpr);
  setType(type);
  if (form) setTaxForm(form);
  if (side) setTaxSide(side);
  setTax(rate);
  redrawAll();
}
/* Что нарисовано пунктиром «после вмешательства»: имя, цвет, значение при Q=0. */
function ffShiftedSnap() {
  var el = document.querySelector('path[stroke-dasharray="6 4"]');
  var out = { paths: document.querySelectorAll('path[stroke-dasharray="6 4"]').length,
              side: STATE.taxSide, type: STATE.intervType, rate: STATE.tax,
              hint: ffText(document.getElementById('tax-hint')),
              names: [] };
  document.querySelectorAll('text.curve-name').forEach(function (t) { out.names.push(ffText(t)); });
  if (el) {
    out.stroke = el.getAttribute('stroke');
    var pts = [];
    String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
      var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
      if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
    });
    out.at0 = pts.length ? pts[0][1] : null;
    out.atQ0 = pts.length ? pts[0][0] : null;
    out.n = pts.length;
  }
  var te = STATE.taxEq;
  out.Q = te ? te.Q : null; out.Pd = te ? te.Pb : null; out.Ps = te ? te.Ps : null;
  out.budget = STATE.budget; out.dwl = STATE.dwl;
  out.dColor = (STATE.D || {}).color; out.sColor = (STATE.S || {}).color;
  return out;
}
/* Ширина набранной записи ВНУТРИ .katex и ширина её контейнера. */
function ffMathWidth(rootSel, needle) {
  var root = document.querySelector(rootSel);
  if (!root) return null;
  var host = null;
  root.querySelectorAll('p, div, .ff-math').forEach(function (p) {
    if (!host && ffText(p).indexOf(needle) >= 0 && p.querySelector('.katex')) host = p;
  });
  if (!host) return null;
  var k = null, kw = -1;
  host.querySelectorAll('.katex').forEach(function (c) {
    var w = c.getBoundingClientRect().width;
    if (w > kw) { kw = w; k = c; }
  });
  if (!k) return null;
  var kr = k.getBoundingClientRect(), hr = host.getBoundingClientRect();
  var cs = getComputedStyle(k);
  return { katexW: Math.round(kr.width * 10) / 10, hostW: Math.round(hr.width * 10) / 10,
           fontPx: Math.round(parseFloat(cs.fontSize) * 10) / 10,
           over: Math.round((kr.width - hr.width) * 10) / 10 };
}
window.ffVisible = ffVisible;
window.ffTextVisible = ffTextVisible;
window.ffExpandAll = ffExpandAll;
window.ffText = ffText;
window.ffPathPoints = ffPathPoints;
window.ffSumPath = ffSumPath;
window.ffLabelAt = ffLabelAt;
window.ffTaxSetup = ffTaxSetup;
window.ffShiftedSnap = ffShiftedSnap;
window.ffMathWidth = ffMathWidth;
`;
await page.addInitScript(HELP);
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(900);

/* ═══════════ Д1. Обрыв суммарной кривой при отдалении ═══════════════ */
if (need('Д1')) {
  head('Д1 · суммарная кривая обрывается на изломе при отдалении');
  const r = await page.evaluate(() => {
    resetSceneMemory(); pickScene('sdsum'); redrawAll();
    CONFIG.Qmin = 0; CONFIG.Qmax = 220; redrawAll();
    ffExpandAll();
    return {
      win: [CONFIG.Qmin, CONFIG.Qmax],
      D: ffSumPath('D'), S: ffSumPath('S'),
      eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
      cs: STATE.cs, ps: STATE.ps,
      labD: ffLabelAt('D', STATE.D), labS: ffLabelAt('S', STATE.S),
    };
  });
  note('окно по Q: ' + r.win.join(' … '));
  note('запись D: ' + (r.D ? r.D.expr : '—'));
  note('изломы D: [' + (r.D ? r.D.breaks.join(', ') : '') + ']  правый конец области: ' + (r.D ? r.D.domainTo : '—'));
  note('изломы S: [' + (r.S ? r.S.breaks.join(', ') : '') + ']  правый конец области: ' + (r.S ? r.S.domainTo : '—'));
  /* ⚠️ ДОПУСК ПИКСЕЛЬНЫЙ, А НЕ МАТЕМАТИЧЕСКИЙ. Точки читаются с атрибута `d`
     и переводятся обратно в координаты модели, то есть через округление до
     пикселя: при окне 0…220 на ~770 px пиксель это 0,29 единицы Q. Требовать
     здесь 1e-6 значило бы мерить не кривую, а разрешение экрана. */
  const PX = 0.35;
  /* ПРАВИЛО, А НЕ ОТПЕЧАТОК: путь кривой доходит до правого конца ЕЁ ОБЛАСТИ
     ОПРЕДЕЛЕНИЯ, а не до последнего излома. Числа 160 и 180 — тот же ответ,
     названный конкретно для этого набора. */
  show('последняя точка D по Q', r.D && r.D.last ? r.D.last[0] : NaN, 160, PX);
  show('последняя точка D по P', r.D && r.D.last ? r.D.last[1] : NaN, 0, PX);
  flag('путь D доходит до конца своей области определения',
       !!(r.D && r.D.last && r.D.domainTo && Math.abs(r.D.last[0] - r.D.domainTo) <= PX),
       (r.D && r.D.last ? num(r.D.last[0]) : '—') + ' против ' + (r.D ? r.D.domainTo : '—'));
  flag('путь D НЕ обрывается на изломе',
       !!(r.D && r.D.last && r.D.breaks.every(b => Math.abs(r.D.last[0] - b) > 1)),
       'изломы [' + (r.D ? r.D.breaks.join(', ') : '') + ']');
  show('последняя точка S по Q', r.S && r.S.last ? r.S.last[0] : NaN, 180, PX);
  show('последняя точка S по P', r.S && r.S.last ? r.S.last[1] : NaN, 100, PX);
  flag('путь S доходит до конца своей области определения',
       !!(r.S && r.S.last && r.S.domainTo && Math.abs(r.S.last[0] - r.S.domainTo) <= PX),
       (r.S && r.S.last ? num(r.S.last[0]) : '—') + ' против ' + (r.S ? r.S.domainTo : '—'));
  flag('путь S НЕ обрывается на изломе',
       !!(r.S && r.S.last && r.S.breaks.every(b => Math.abs(r.S.last[0] - b) > 1)),
       'изломы [' + (r.S ? r.S.breaks.join(', ') : '') + ']');
  show('точек в пути D', r.D ? r.D.n : NaN, null);
  show('точек в пути S', r.S ? r.S.n : NaN, null);
  flag('точек в пути D — единицы, а не сотни', !!r.D && r.D.n <= 12, r.D ? r.D.n : '—');
  show('равновесие Q*', r.eq ? r.eq.Q : NaN, 70, 1e-4);
  show('равновесие P*', r.eq ? r.eq.P : NaN, 45, 1e-4);
  show('CS', r.cs, 1625, 1e-3);
  show('PS', r.ps, 1325, 1e-3);
  /* Подпись обязана сидеть НА ЛИНИИ, а не за её концом: это второй дефект,
     а не тот же самый. Считаем расстояние от места подписи до самой кривой. */
  note('подпись D на холсте при Q ≈ ' + (r.labD ? num(r.labD.q) : '—')
       + ', расхождение с кривой по P: ' + (r.labD ? num(r.labD.gap) : '—'));
  note('подпись S на холсте при Q ≈ ' + (r.labS ? num(r.labS.q) : '—')
       + ', расхождение с кривой по P: ' + (r.labS ? num(r.labS.gap) : '—'));
  flag('подпись D стоит на своей линии', !!(r.labD && r.labD.onCurve),
       r.labD ? ('Q ' + num(r.labD.q) + ', расхождение ' + num(r.labD.gap)) : 'подписи нет');
  flag('подпись S стоит на своей линии', !!(r.labS && r.labS.onCurve),
       r.labS ? ('Q ' + num(r.labS.q) + ', расхождение ' + num(r.labS.gap)) : 'подписи нет');
  await shot('d1-sum-zoom-220');
}

/* ═══════════ Д2. Подсказка суммарной кривой ═════════════════════════ */
if (need('Д2')) {
  head('Д2 · подсказка суммарной кривой: язык, связка, хвост, ширина');
  await page.evaluate(() => { resetSceneMemory(); pickScene('sdsum'); redrawAll(); ffExpandAll(); });
  await page.waitForTimeout(400);
  const target = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('.crow-auto'));
    if (!rows.length) return null;
    const r = rows[0].getBoundingClientRect();
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
             tip: rows[0].getAttribute('data-tip') };
  });
  if (!target) { flag('строка суммарной кривой найдена', false); }
  else {
    note('data-tip строки: ' + target.tip.slice(0, 220));
    await page.mouse.move(target.x, target.y);
    await page.waitForTimeout(400);
    const t = await page.evaluate(() => {
      const el = document.getElementById('hint-tip');
      if (!el || el.style.display === 'none') return null;
      const r = el.getBoundingClientRect();
      const ch = document.querySelector('#chart');
      const cr = ch ? ch.getBoundingClientRect() : null;
      const k = el.querySelector('.katex');
      const kr = k ? k.getBoundingClientRect() : null;
      return {
        text: ffText(el),
        rect: { l: Math.round(r.left), t: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
        inWindow: r.left >= 0 && r.top >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight,
        overChart: !!cr && !(r.right <= cr.left || r.left >= cr.right || r.bottom <= cr.top || r.top >= cr.bottom),
        katexW: kr ? Math.round(kr.width) : null,
        katexOver: kr ? Math.round(kr.right - r.right) : null,
        winW: window.innerWidth,
      };
    });
    if (!t) flag('плашка подсказки всплыла', false);
    else {
      note('текст плашки: ' + t.text.slice(0, 240));
      note('плашка: ' + t.rect.w + '×' + t.rect.h + ' при окне ' + t.winW);
      flag('нет английского if', t.text.indexOf('if') < 0, t.text.indexOf('if') >= 0 ? 'есть' : '');
      flag('нет otherwise', t.text.indexOf('otherwise') < 0);
      flag('нет связки ∧', t.text.indexOf('∧') < 0);
      flag('нет служебного ∞', t.text.indexOf('∞') < 0);
      flag('есть «если 0 ≤ Q < 40»', /если\s*0\s*≤\s*Q\s*<\s*40/.test(t.text.replace(/ | /g, ' ')));
      flag('есть «если 40 ≤ Q ≤ 160»', /если\s*40\s*≤\s*Q\s*≤\s*160/.test(t.text.replace(/ | /g, ' ')));
      flag('плашка целиком в окне браузера', t.inWindow, JSON.stringify(t.rect));
      flag('плашка не залезает на холст', !t.overChart);
      show('запись выходит за правый край плашки, px', t.katexOver, null);
      flag('запись НЕ выходит за правый край плашки', t.katexOver != null && t.katexOver <= 1,
           t.katexOver + ' px');
      await shot('d2-tip-sum');
    }
  }
  /* ⚠️ ДВА КРАЯ У ПРАВИЛА, И ВТОРОЙ — ДЛИННАЯ ЗАПИСЬ. Два куска влезают в
     плашку и без всякой подгонки; проверять надо и тот случай, ради которого
     подгонка написана. Набор Б даёт спросу ТРИ участка. */
  head('Д2 (второй край) · длинная запись из трёх участков');
  await page.evaluate(() => {
    resetSceneMemory(); pickScene('sdsum');
    sumSetCount('D', 3); sumSetCount('S', 2);
    const gd = STATE.curves.filter(c => c.sumGroup === 'D' && c.kind !== 'sum');
    const gs = STATE.curves.filter(c => c.sumGroup === 'S' && c.kind !== 'sum');
    ['100-Q', '60-Q', '40-Q'].forEach((e, i) => updateCurveExpr(gd[i], e));
    ['Q-100', 'Q+20'].forEach((e, i) => updateCurveExpr(gs[i], e));
    redrawAll(); ffExpandAll();
  });
  await page.waitForTimeout(400);
  const t2 = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('.crow-auto'));
    if (!rows.length) return null;
    const r = rows[0].getBoundingClientRect();
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
  });
  if (t2) {
    await page.mouse.move(t2.x, t2.y);
    await page.waitForTimeout(400);
    const w = await page.evaluate(() => {
      const el = document.getElementById('hint-tip');
      if (!el || el.style.display === 'none') return null;
      const r = el.getBoundingClientRect();
      const ch = document.querySelector('#chart');
      const cr = ch ? ch.getBoundingClientRect() : null;
      const k = el.querySelector('.katex');
      const kr = k ? k.getBoundingClientRect() : null;
      const ann = k ? k.querySelector('annotation[encoding="application/x-tex"]') : null;
      return {
        text: ffText(el), wide: el.classList.contains('tip-math'),
        stacked: /gathered/.test(ann ? ann.textContent : ''),
        w: Math.round(r.width), over: kr ? Math.round(kr.right - r.right) : null,
        inWindow: r.left >= 0 && r.top >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight,
        onChart: !!cr && !(r.right <= cr.left || r.left >= cr.right || r.bottom <= cr.top || r.top >= cr.bottom),
      };
    });
    if (!w) flag('плашка всплыла', false);
    else {
      note('текст: ' + w.text.slice(0, 220));
      note('плашка ' + w.w + ' px, расширена: ' + w.wide + ', вторая форма: ' + w.stacked);
      flag('нет английского if', w.text.indexOf('if') < 0);
      flag('нет служебного ∞', w.text.indexOf('∞') < 0);
      show('запись выходит за правый край плашки, px', w.over, null);
      flag('запись НЕ выходит за правый край плашки', w.over != null && w.over <= 1, w.over + ' px');
      flag('плашка целиком в окне браузера', w.inWindow);
      await shot('d2-tip-sum-3');
    }
  }
  /* ⚠️ ТРЕТИЙ СЛУЧАЙ — ЗАВЕДОМО ШИРОКАЯ ЗАПИСЬ. Настоящие наборы дают запись,
     которая влезает и без подгонки, и на них правило ширины никогда бы не
     сработало: проверка, которая не может покраснеть, ничего не стережёт.
     Берём длинные коэффициенты и смотрим, что плашка расширилась либо запись
     пересобрана второй формой — и в обоих случаях осталась внутри плашки. */
  head('Д2 (третий край) · заведомо широкая запись');
  const w3 = await page.evaluate(() => {
    const LONG = '(Q >= 0 and Q < 40) ? 123.456789 - 0.987654*Q : '
               + '((Q >= 40 and Q < 80) ? 987.654321 - 0.123456*Q : '
               + '((Q >= 80 and Q <= 200) ? 1234.56789 - 0.456789*Q : NaN))';
    const dot = document.querySelector('.crow-auto') || document.body;
    showHintTip(dot, 'Сейчас это ' + tipExpr(LONG));
    const el = document.getElementById('hint-tip');
    const r = el.getBoundingClientRect();
    const k = el.querySelector('.katex');
    const kr = k ? k.getBoundingClientRect() : null;
    const ann = k ? k.querySelector('annotation[encoding="application/x-tex"]') : null;
    return {
      text: ffText(el), wide: el.classList.contains('tip-math'),
      stacked: /gathered/.test(ann ? ann.textContent : ''),
      w: Math.round(r.width), over: kr ? Math.round(kr.right - r.right) : null,
      inWindow: r.left >= 0 && r.top >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight,
    };
  });
  note('плашка ' + w3.w + ' px, расширена: ' + w3.wide + ', вторая форма: ' + w3.stacked);
  note('текст: ' + w3.text.slice(0, 200));
  flag('широкая запись включила правило ширины', w3.wide || w3.stacked,
       'расширение ' + w3.wide + ', вторая форма ' + w3.stacked);
  show('запись выходит за правый край плашки, px', w3.over, null);
  flag('широкая запись НЕ выходит за правый край плашки', w3.over != null && w3.over <= 1,
       w3.over + ' px');
  flag('плашка целиком в окне браузера', w3.inWindow);
  await shot('d2-tip-wide');
}

/* ═══════════ Д3. Субсидия покупателю ═══════════════════════════════ */
if (need('Д3')) {
  head('Д3 · субсидия покупателю не двигает график');
  for (const [tag, dE, sE, rate, wantQ, wantPd, wantPs, wantBud] of [
    ['а', '100-Q', 'Q', 20, 60, 40, 60, -1200],
    ['б', '100-P', '0.5p-200', 450, 50, 50, 500, 22500],
  ]) {
    for (const side of ['seller', 'buyer']) {
      const r = await page.evaluate(([d, s, sd, rt]) => {
        ffTaxSetup(d, s, 'subsidy', 'unit', sd, rt);
        ffExpandAll();
        return ffShiftedSnap();
      }, [dE, sE, side, rate]);
      console.log('  -- набор (' + tag + ') ' + dE + ' / ' + sE + ', субсидия ' + rate + ', сторона ' + side);
      show('    Q', r.Q, wantQ, 1e-4);
      show('    цена покупателя', r.Pd, wantPd, 1e-4);
      show('    цена продавца', r.Ps, wantPs, 1e-4);
      show('    расход бюджета', r.budget, tag === 'а' ? wantBud : -wantBud, 1e-3);
      note('    имена кривых на холсте: ' + r.names.join(' · '));
      note('    сдвинутая кривая: цвет ' + r.stroke + ' (D ' + r.dColor + ', S ' + r.sColor + '), при Q='
           + num(r.atQ0) + ' даёт ' + num(r.at0));
      const movedD = (r.stroke === r.dColor);
      flag('    сдвинута ' + (side === 'buyer' ? 'кривая СПРОСА' : 'кривая ПРЕДЛОЖЕНИЯ'),
           side === 'buyer' ? movedD : !movedD, 'stroke=' + r.stroke);
      if (side === 'buyer' && tag === 'а') {
        show('    сдвинутый спрос при Q=0', r.at0, 120, 1e-6);
        flag('    имя сдвинутой кривой «D + s»', r.names.indexOf('D + s') >= 0, r.names.join(' · '));
      }
      if (side === 'seller' && tag === 'а') {
        show('    сдвинутое предложение при Q=0', r.at0, -20, 1e-6);
        flag('    имя сдвинутой кривой «S − s»', r.names.indexOf('S − s') >= 0, r.names.join(' · '));
      }
      note('    подсказка: ' + r.hint.slice(0, 160));
      /* ⚠️ Проверяем НЕ наличие слова «покупатель» — оно есть в любой
         подсказке («между ценами покупателя и продавца»), и такой случай
         покраснеть не может никогда. Проверяем то, ради чего подсказка
         существует: названа ли ДВИГАЮЩАЯСЯ кривая. */
      const saysD = /кривая\s*D|спроса\s*D|кривая\s+спроса/i.test(r.hint);
      const saysS = /кривая\s*S|предложения\s*S|кривая\s+предложения/i.test(r.hint);
      flag('    подсказка называет ДВИГАЮЩУЮСЯ кривую',
           side === 'buyer' ? (saysD && !saysS) : (saysS && !saysD),
           'D=' + saysD + ' S=' + saysS);
      await shot('d3-' + tag + '-' + side);
    }
  }
}

/* ═══════════ Д4. Запись суммарной КПВ ══════════════════════════════ */
if (need('Д4')) {
  head('Д4 · запись суммарной КПВ: где стоит и помещается ли');
  const r = await page.evaluate(() => {
    resetSceneMemory(); pickScene('ppfsum');
    ppfSumSet(0, '100 - X'); ppfSumSet(1, '60 - 3*X');
    recomputePpfSum(); redrawAll(); ffExpandAll();
    const sb = document.getElementById('sb-body');
    const ex = document.getElementById('ex-body');
    const has = (root) => root ? ffTextVisible(root).indexOf('Форма кривой') >= 0 : false;
    const ff = document.getElementById('info-final');
    return {
      inKeys: has(sb), inExplain: has(ex),
      hasFinalBox: !!ff, finalText: ff ? ffText(ff) : null,
      texRaw: (STATE.ppfSumData || {}).formulaTex || null,
      textRaw: (STATE.ppfSumData || {}).formulaText || null,
      widthEx: ffMathWidth('#ex-body', 'Форма кривой'),
      widthSb: ffMathWidth('#sb-body', 'Форма кривой'),
      panelW: (() => { const p = document.querySelector('#params-panel .fold-body');
                       return p ? Math.round(p.getBoundingClientRect().width) : null; })(),
      kinks: (STATE.ppfSumData || {}).kinks || [],
      Xtot: (STATE.ppfSumData || {}).Xtot, Ytot: (STATE.ppfSumData || {}).Ytot,
      /* Где именно стоит абзац внутри «Объяснения модели» и свёрнуто ли оно
         по умолчанию — это и есть жалоба «не там». */
      place: (() => {
        const ex = document.getElementById('ex-body');
        if (!ex) return null;
        const ps = Array.from(ex.querySelectorAll('p'));
        const i = ps.findIndex(p => ffText(p).indexOf('Форма кривой') >= 0);
        return { idx: i, total: ps.length, last: i === ps.length - 1 };
      })(),
      /* Ширина той же записи при КАНОНИЧЕСКОМ кегле 15 px: fitPanelMath
         ужимает её, поэтому «влезло» на экране ничего не доказывает. */
      natural: (() => {
        const tex = (STATE.ppfSumData || {}).formulaTex;
        if (!tex || typeof katex === 'undefined') return null;
        const d = document.createElement('div');
        d.style.cssText = 'position:absolute;left:-9999px;top:0;font-size:15px;white-space:nowrap';
        document.body.appendChild(d);
        katex.render(tex, d, { throwOnError: false });
        const k = d.querySelector('.katex');
        const w = k ? Math.round(k.getBoundingClientRect().width * 10) / 10 : null;
        d.remove();
        return w;
      })(),
    };
  });
  note('LaTeX записи: ' + (r.texRaw || r.textRaw || '—'));
  flag('запись ВИДНА в «Ключевых значениях»', r.inKeys, 'inKeys=' + r.inKeys);
  note('запись есть в «Объяснении модели»: ' + r.inExplain);
  flag('контейнер #info-final существует', r.hasFinalBox);
  note('ширина .fold-body правой панели: ' + r.panelW + ' px');
  if (r.widthEx) note('в «Объяснении»: .katex ' + r.widthEx.katexW + ' px при контейнере '
                      + r.widthEx.hostW + ' px, кегль ' + r.widthEx.fontPx + ' px, перебор '
                      + r.widthEx.over + ' px');
  if (r.widthSb) note('в «Ключевых»: .katex ' + r.widthSb.katexW + ' px при контейнере '
                      + r.widthSb.hostW + ' px, кегль ' + r.widthSb.fontPx + ' px, перебор '
                      + r.widthSb.over + ' px');
  show('X суммарной', r.Xtot, 120, 1e-6);
  show('Y суммарной', r.Ytot, 160, 1e-6);
  note('изломы: ' + JSON.stringify(r.kinks));
  if (r.place) note('абзац «Форма кривой» — ' + (r.place.idx + 1) + '-й из ' + r.place.total
                    + ' абзацев «Объяснения», последний: ' + r.place.last);
  note('ширина той же записи при каноническом кегле 15 px: ' + r.natural + ' px');
  flag('запись при 15 px помещается в 246 px', r.natural != null && r.natural <= 246,
       r.natural + ' px против 246');
  await shot('d4-ppfsum-record');
}

/* ═══════════ Ф. Единый блок «Итоговая функция» ═════════════════════ */
if (need('Ф')) {
  head('Ф · блок «Итоговая функция» во всех четырёх сценах');
  const scenes = [
    ['sdsum', 'Сложение спросов и предложений', () => { }],
    ['ppfsum', 'Сложение КПВ', () => { ppfSumSet(0, '100 - X'); ppfSumSet(1, '60 - 3*X'); recomputePpfSum(); }],
    ['trade', 'КТВ. Одна страна', () => { }],
    ['taxes', 'Налоги и субсидии', () => { setType('tax'); setTaxForm('unit'); setTax(20); }],
  ];
  for (const [key, title] of scenes) {
    const r = await page.evaluate((k) => {
      resetSceneMemory(); pickScene(k);
      if (k === 'ppfsum') { ppfSumSet(0, '100 - X'); ppfSumSet(1, '60 - 3*X'); recomputePpfSum(); }
      if (k === 'taxes') { setType('tax'); setTaxForm('unit'); setTax(20); }
      redrawAll(); ffExpandAll();
      const ff = document.getElementById('info-final');
      const sb = document.getElementById('sb-body');
      const first = sb ? Array.from(sb.children).filter(e => ffText(e)).map(e => e.id || e.className)[0] : null;
      const blocks = ff ? Array.from(ff.querySelectorAll('.ff')) : [];
      return {
        exists: !!ff, count: blocks.length,
        firstInPanel: first,
        text: ff ? ffText(ff) : '',
        notes: blocks.map(b => {
          const m = b.querySelector('.ff-math');
          const kk = m ? m.querySelector('.katex') : null;
          const cs = m ? getComputedStyle(m) : null;
          return {
            name: ffText(b.querySelector('.ff-name')),
            eyebrow: ffText(b.querySelector('.ff-eyebrow')),
            border: getComputedStyle(b).borderLeftColor,
            note: ffText(b.querySelector('.ff-note')),
            copy: !!b.querySelector('.ff-copy'),
            scroll: m ? m.classList.contains('ff-scroll') : false,
            stacked: m ? m.getAttribute('data-ff-form') === 'stacked' : false,
            /* Кегль меряем у .ff-math — правило владельца про НЕГО. У самого
               .katex он множится на 1,21 своим стилем, и «18,2» ничего не
               доказывает. */
            fontPx: cs ? Math.round(parseFloat(cs.fontSize) * 10) / 10 : null,
            katexW: kk ? Math.round(kk.getBoundingClientRect().width * 10) / 10 : null,
            hostW: m ? Math.round(m.getBoundingClientRect().width * 10) / 10 : null,
          };
        }),
        sbNoteInside: ff ? ff.querySelectorAll('.sb-note, .sb-note-src').length : -1,
      };
    }, key);
    console.log('  -- ' + title + ' (' + key + ')');
    flag('    блок есть', r.exists && r.count > 0, 'блоков ' + r.count);
    flag('    блок стоит ПЕРВЫМ в «Ключевых значениях»', r.firstInPanel === 'info-final', String(r.firstInPanel));
    flag('    внутри блока нет .sb-note', r.sbNoteInside === 0, 'найдено ' + r.sbNoteInside);
    r.notes.forEach(n => {
      note('    «' + n.name + '» · кромка ' + n.border + ' · кегль ' + n.fontPx
           + ' px · запись ' + n.katexW + ' px при контейнере ' + n.hostW + ' px'
           + (n.stacked ? ' · вторая форма' : '') + (n.scroll ? ' · с прокруткой' : '')
           + (n.note ? ' · приписка: ' + n.note : ''));
      if (n.katexW == null) { flag('    запись набрана', !!n.note, 'ни записи, ни приписки'); return; }
      flag('    кегль не ниже 13 px', n.fontPx >= 13, String(n.fontPx));
      flag('    запись помещается по ширине (или прокручивается)',
           n.katexW <= n.hostW + 1 || n.scroll, n.katexW + ' > ' + n.hostW);
      flag('    кнопка «копировать» на месте', n.copy);
    });
    await shot('ff-' + key);
  }
}

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
console.log(bad ? ('ПРОВАЛОВ: ' + bad) : 'ВСЁ СОШЛОСЬ');
await browser.close();
process.exit(bad ? 1 : 0);
