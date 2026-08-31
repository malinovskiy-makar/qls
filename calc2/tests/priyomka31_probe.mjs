/* Прибор приёмки владельца 31.08: блок «Итоговая функция», две поломки.

   Числа печатаются ВСЕГДА, а не только при провале: этим прибором снимаются
   и «до», и «после».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/priyomka31_probe.mjs                # все наборы
     node calc2/tests/priyomka31_probe.mjs Д1 Д3          # только эти
     P31_SHOTS=reports/calc2_priyomka_31aug/after node calc2/tests/priyomka31_probe.mjs

   Наборы:
     Д1 — суммарное предложение обрывается на служебном потолке цены (180; 100);
     Д2 — запись кривой после вмешательства не раскрывает скобки;
     Д3 — запись в блоке «Итоговая функция» кривая: строки центрированы.

   ⚠️ ПРИБОР ОБЯЗАН САМ РАСКРЫТЬ СВЁРНУТЫЕ КАРТОЧКИ. Считать только раскрытое —
   значит занижать. Каждый признак снимается ДВУМЯ способами: числом и снимком.
*/
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SHOTS = process.env.P31_SHOTS || 'reports/calc2_priyomka_31aug/before';

const want = process.argv.slice(2);
const need = (name) => !want.length || want.includes(name);
fs.mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

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

/* Помощники, живущие В СТРАНИЦЕ. Ставятся один раз на загрузку. */
const HELP = `
/* Раскрыть ВСЁ: свёрнутая карточка меряется нулевой шириной, и замер по ней
   врёт в «влезло». */
function p31Expand() {
  document.querySelectorAll('details').forEach(function (d) { d.open = true; });
  document.querySelectorAll('.sb-card.folded, .card.folded').forEach(function (e) { e.classList.remove('folded'); });
  document.querySelectorAll('.fold-btn').forEach(function (b) {
    if (b.getAttribute('aria-expanded') !== 'true') b.click();
  });
  document.querySelectorAll('.panel, .side, .sb, .drawer, .side-scroll').forEach(function (e) { e.scrollTop = 0; });
}
function p31Text(el) {
  if (!el) return '';
  var c = el.cloneNode(true);
  c.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
  return c.textContent.replace(/\\s+/g, ' ').trim();
}
/* Точки пути суммарной кривой стороны side в координатах МОДЕЛИ.
   Читаем сам атрибут d: врать умеет ровно разрыв между расчётом и отрисовкой. */
function p31SumPath(side) {
  var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === side; });
  if (!c) return null;
  var el = document.querySelector('path[data-curve="' + c.id + '"][data-sum-part="real"]')
        || document.querySelector('path[data-curve="' + c.id + '"]:not([data-sum-part])');
  if (!el) return null;
  var pts = [];
  String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
    var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
    if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
  });
  return { n: pts.length, first: pts[0] || null, last: pts[pts.length - 1] || null,
           expr: String(c.expr || ''), breaks: (c.sumBreaks || []).slice(),
           domainTo: c.sumDomainTo, ghostTo: c.sumGhostTo || 0 };
}
/* Блок «Итоговая функция»: что в нём набрано и какой ширины. */
function p31Final() {
  var box = document.getElementById('info-final');
  if (!box) return null;
  var out = { blocks: [] };
  box.querySelectorAll('.ff').forEach(function (ff) {
    var host = ff.querySelector('.ff-math');
    var k = host ? host.querySelector('.katex') : null;
    var rec = {
      name: p31Text(ff.querySelector('.ff-name')),
      eyebrow: p31Text(ff.querySelector('.ff-eyebrow')),
      tex: host ? (host.getAttribute('data-ff-tex') || '') : '',
      form: host ? (host.getAttribute('data-ff-form') || '') : '',
      expr: (ff.querySelector('.ff-copy') || {}).getAttribute
            ? ff.querySelector('.ff-copy').getAttribute('data-ff-expr') : '',
      text: p31Text(host),
      hasExpand: !!ff.querySelector('.ff-expand'),
      copies: ff.querySelectorAll('.ff-copy').length,
    };
    if (host) {
      rec.hostW = Math.round(host.clientWidth * 10) / 10;
      rec.fontPx = Math.round(parseFloat(getComputedStyle(host).fontSize) * 10) / 10;
    }
    /* ⚠️ У КОМПАКТНОЙ ЗАПИСИ ОДНОГО .katex НЕТ, И МЕРИТЬ ПЕРВЫЙ — ВРАТЬ.
       Здесь прибор соврал 31.08 второй раз: после правки Фазы 1 запись
       собрана из отдельных ячеек, каждая со своим KaTeX, и первый из них —
       это приставка «P =». Замер давал 33,3 px и бодрое «переполнения нет»
       на записи, у которой условия были усечены многоточием.
       Считаем так же, как считает сама подгонка: постоянная часть (приставка,
       скобка, отбивки) плюс самая широкая формула плюс отбивка колонок плюс
       самое широкое условие. */
    var kw = function (el) {
      var kk = el && el.querySelector('.katex');
      return kk ? kk.getBoundingClientRect().width : 0;
    };
    var widest = function (list) {
      var m = 0;
      Array.prototype.forEach.call(list, function (e) { m = Math.max(m, kw(e)); });
      return m;
    };
    if (host && host.classList.contains('ff-cases')) {
      var rowsEl = host.querySelector('.ff-rows');
      var lhs = host.querySelector('.ff-lhs');
      var brace = host.querySelector('.ff-brace');
      var gap = parseFloat(getComputedStyle(rowsEl).columnGap) || 0;
      var outer = parseFloat(getComputedStyle(host).columnGap) || 0;
      var fixed = (lhs ? lhs.getBoundingClientRect().width : 0)
                + (brace ? brace.getBoundingClientRect().width : 0)
                + outer * (lhs ? 2 : 1);
      var fW = widest(host.querySelectorAll('.ff-f'));
      var cW = widest(host.querySelectorAll('.ff-c'));
      rec.katexW = Math.round((fixed + fW + (cW > 0 ? gap + cW : 0)) * 10) / 10;
      rec.over = Math.round((rec.katexW - rec.hostW) * 10) / 10;
      rec.fixedW = Math.round(fixed * 10) / 10;
      rec.formulaW = Math.round(fW * 10) / 10;
      rec.condW = Math.round(cW * 10) / 10;
      var f0 = host.querySelector('.ff-f'), c0 = host.querySelector('.ff-c');
      rec.fontPx = f0 ? Math.round(parseFloat(getComputedStyle(f0).fontSize) * 10) / 10 : rec.fontPx;
      rec.condPx = c0 ? Math.round(parseFloat(getComputedStyle(c0).fontSize) * 10) / 10 : 0;
      rec.cut = host.querySelectorAll('.ff-c.ff-cut').length;
      rec.conds = host.querySelectorAll('.ff-c').length;
      /* ⚠️ «ВЛЕЗЛО» У КОМПАКТНОЙ ЗАПИСИ — ЭТО «НИЧЕГО НЕ ТОРЧИТ», А НЕ
         «полная запись поместилась». Лестница отступления штатно кончается
         усечением условия: полная запись шире панели, а на экране при этом
         всё ровно. Меряем реальный вылет разметки. */
      rec.spill = Math.round((host.scrollWidth - host.clientWidth) * 10) / 10;
      var lastRow = host.querySelector('.ff-c:last-child');
      rec.rowSpill = 0;
      Array.prototype.forEach.call(host.querySelectorAll('.ff-f, .ff-c'), function (e) {
        var d = e.getBoundingClientRect().right - host.getBoundingClientRect().right;
        if (d > rec.rowSpill) rec.rowSpill = Math.round(d * 10) / 10;
      });
    } else if (k) {
      rec.katexW = Math.round(k.getBoundingClientRect().width * 10) / 10;
      rec.over = Math.round((rec.katexW - rec.hostW) * 10) / 10;
      rec.cut = 0; rec.conds = 0; rec.condPx = 0;
    }
    /* ⚠️ СТРОКИ НАДЗАГОЛОВКА СЧИТАЮТСЯ ПО ДИАПАЗОНУ, А НЕ ПО САМОМУ УЗЛУ.
       Здесь прибор уже соврал 31.08: узел .ff-eyebrow лежит внутри флексбокса и
       потому сам является блоком, а у блока getClientRects() отдаёт ОДНУ
       рамку на всю коробку — сколько бы строк текста в ней ни стояло. Замер
       показывал «одна строка» на снимке, где надпись явно шла в две.
       Диапазон по СОДЕРЖИМОМУ отдаёт по рамке на строку — это и есть ответ. */
    var eb = ff.querySelector('.ff-eyebrow');
    rec.eyebrowLines = 0;
    if (eb) {
      var rg = document.createRange();
      rg.selectNodeContents(eb);
      var tops = [];
      Array.prototype.forEach.call(rg.getClientRects(), function (r) {
        if (!(r.height > 1) || !(r.width > 1)) return;
        var m = Math.round(r.top);
        if (tops.indexOf(m) < 0) tops.push(m);
      });
      rec.eyebrowLines = tops.length;
    }
    /* ЧИСЛО ВИЗУАЛЬНЫХ СТРОК ВНУТРИ СКОБКИ. Меряем по разметке KaTeX:
       у окружения cases это строки первой колонки массива; у сложенной
       (двухстрочной) формы внутри каждой строки заводится своё окружение
       gathered, и строк становится вдвое больше. */
    rec.rows = p31RowCount(ff);
    out.blocks.push(rec);
  });
  return out;
}
/* СКОЛЬКО ВИЗУАЛЬНЫХ СТРОК реально видит человек внутри записи.

   ⚠️ СЧИТАЕМ ТЕКСТ, А НЕ РАЗМЕТКУ. Разметка у двух форм записи разная
   (окружение cases против вложенного gathered, а после правки 31.08 — вообще
   свои узлы), и счёт по ней был бы отпечатком реализации, а не правилом.
   Правило же простое: сколько строк текста стоит одна под другой. Поэтому
   берём прямоугольники САМИХ ТЕКСТОВЫХ УЗЛОВ и группируем по вертикали.
   Скрытую копию MathML и подпись annotation выбрасываем: их не видно. */
function p31RowCount(ff) {
  var host = ff.querySelector('.ff-math');
  if (!host) return 0;
  /* «Внутри скобки» — это область участков, а не весь блок: приставка «P =»
     стоит сбоку, а сама скобка у KaTeX склеена из трёх глифов друг под другом
     и дала бы три лишние строки. */
  var root = host.querySelector('.ff-rows') || host.querySelector('.mtable') || host;
  var bands = [];
  var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (n) {
      if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      var p = n.parentElement;
      if (!p || p.closest('.katex-mathml, annotation')) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  var n;
  while ((n = w.nextNode())) {
    var rg = document.createRange();
    rg.selectNodeContents(n);
    var r = rg.getBoundingClientRect();
    rg.detach && rg.detach();
    if (!(r.height > 0.5) || !(r.width > 0.2)) continue;
    var mid = r.top + r.height / 2;
    var hit = false;
    for (var i = 0; i < bands.length; i++) {
      /* Полосой считаем то, что пересекается по вертикали больше чем на
         половину: подстрочные индексы и дроби внутри одной строки не должны
         давать вторую строку. */
      if (Math.abs(bands[i] - mid) <= 5) { hit = true; break; }
    }
    if (!hit) bands.push(mid);
  }
  return bands.length;
}
/* Ширина набранной записи ВНУТРИ .katex против ширины контейнера. */
function p31Width() {
  var host = document.querySelector('#info-final .ff-math');
  if (!host) return null;
  var k = host.querySelector('.katex');
  if (!k) return null;
  return { katexW: Math.round(k.getBoundingClientRect().width * 10) / 10,
           hostW: Math.round(host.clientWidth * 10) / 10,
           fontPx: Math.round(parseFloat(getComputedStyle(host).fontSize) * 10) / 10 };
}
/* Сцена налогов: свои кривые, вид вмешательства, форма, сторона и ставка. */
function p31TaxSetup(dExpr, sExpr, type, form, side, rate) {
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
  p31Expand();
  redrawAll();
}
window.p31Expand = p31Expand;
window.p31Text = p31Text;
window.p31SumPath = p31SumPath;
window.p31Final = p31Final;
window.p31RowCount = p31RowCount;
window.p31Width = p31Width;
window.p31TaxSetup = p31TaxSetup;
`;

await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.addInitScript(HELP);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

/* ═══════════ Д1. Предложение обрывается на служебном потолке ═════════ */
if (need('Д1')) {
  head('Д1 · суммарное предложение обрывается на потолке цены (180; 100)');
  const r = await page.evaluate(() => {
    resetSceneMemory(); pickScene('sdsum'); redrawAll();
    CONFIG.Qmin = 0; CONFIG.Qmax = 320; redrawAll();
    p31Expand(); redrawAll();
    return {
      win: [CONFIG.Qmin, CONFIG.Qmax],
      D: p31SumPath('D'), S: p31SumPath('S'),
      eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
      cs: STATE.cs, ps: STATE.ps,
      final: p31Final(),
    };
  });
  note('окно по Q: ' + r.win.join(' … '));
  note('запись S: ' + (r.S ? r.S.expr : '—'));
  note('запись D: ' + (r.D ? r.D.expr : '—'));
  note('правый конец области S: ' + (r.S ? r.S.domainTo : '—')
       + '   правый конец области D: ' + (r.D ? r.D.domainTo : '—'));
  const PX = 0.5;
  show('последняя точка S по Q', r.S && r.S.last ? r.S.last[0] : NaN, r.win[1], PX);
  show('последняя точка D по Q', r.D && r.D.last ? r.D.last[0] : NaN, 160, PX);
  show('последняя точка D по P', r.D && r.D.last ? r.D.last[1] : NaN, 0, PX);
  flag('в записи предложения НЕТ числа 180',
       !!(r.S && !/(^|[^\d.])180([^\d.]|$)/.test(r.S.expr)), r.S ? r.S.expr : '—');
  flag('у предложения нет верхней границы области',
       !!(r.S && !isFinite(r.S.domainTo)), r.S ? String(r.S.domainTo) : '—');
  show('равновесие Q*', r.eq ? r.eq.Q : NaN, 70, 1e-4);
  show('равновесие P*', r.eq ? r.eq.P : NaN, 45, 1e-4);
  show('CS', r.cs, 1625, 1e-3);
  show('PS', r.ps, 1325, 1e-3);
  (r.final ? r.final.blocks : []).forEach((b, i) => {
    note('блок ' + (i + 1) + ' «' + b.name + '»: ' + b.text);
  });
  await shot('d1-sdsum-q320');

  /* ⚠️ ОДНОГО ОКНА ДЛЯ ЭТОГО ПРАВИЛА МАЛО. «Верхней границы не существует»
     значит, что линия доходит до края кадра ПРИ ЛЮБОМ отдалении, а не до
     какого-то одного числа. Проверяем на трёх окнах подряд, и заодно —
     что подпись кривой не осталась висеть у пустого места. */
  head('Д1б · предложение при отдалении до 500 и 1000');
  for (const W of [500, 1000]) {
    const q = await page.evaluate((qmax) => {
      CONFIG.Qmin = 0; CONFIG.Qmax = qmax; redrawAll();
      const lab = (txt, curve) => {
        let out = null;
        document.querySelectorAll('text.curve-name').forEach(t => {
          if (p31Text(t) === txt && !out) {
            const q = sx.invert(+t.getAttribute('x'));
            const v = evalCurve(curve, q);
            const gapPx = isFinite(v) ? Math.abs(sy(v) - (+t.getAttribute('y'))) : Infinity;
            out = { q: q, gapPx: Math.round(gapPx * 10) / 10, onCurve: isFinite(v) && gapPx <= 22 };
          }
        });
        return out;
      };
      return { win: [CONFIG.Qmin, CONFIG.Qmax],
               S: p31SumPath('S'), D: p31SumPath('D'),
               eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
               cs: STATE.cs, ps: STATE.ps,
               labS: lab('S', STATE.S), labD: lab('D', STATE.D) };
    }, W);
    console.log('  · окно до Q = ' + W);
    show('  последняя точка S по Q', q.S && q.S.last ? q.S.last[0] : NaN, W, 0.8);
    show('  последняя точка D по Q', q.D && q.D.last ? q.D.last[0] : NaN, 160, 0.8);
    show('  равновесие Q*', q.eq ? q.eq.Q : NaN, 70, 1e-4);
    show('  CS', q.cs, 1625, 1e-3);
    show('  PS', q.ps, 1325, 1e-3);
    /* ⚠️ ПОДПИСЬ КРИВОЙ ЗДЕСЬ — ЗАМЕР, А НЕ ПРОВЕРКА, И ЭТО НЕ ПОБЛАЖКА.
       Подписи суммарных кривых уезжают с линии при сильном отдалении, и это
       СТАРЫЙ дефект, а не последствие снятия верхней границы: замер 31.08 на
       коде ДО правки дал те же 30,2 px у S и 23,2 px у D при окне 500. Правка
       его даже уменьшила — при окне 1000 отклонение S было бесконечным (линии
       там просто не было), стало 46,5 px. Красный флажок по чужому дефекту
       приучил бы не смотреть на прибор; поэтому число печатаем, а карточка
       заведена отдельно. Здесь стережём одно: подпись НЕ пропала совсем. */
    note('  подпись S: Q ' + (q.labS ? num(q.labS.q) : '—')
         + ', отклонение от линии ' + (q.labS ? q.labS.gapPx : '—') + ' px'
         + '   (старый дефект, см. карточку про подписи при отдалении)');
    note('  подпись D: Q ' + (q.labD ? num(q.labD.q) : '—')
         + ', отклонение от линии ' + (q.labD ? q.labD.gapPx : '—') + ' px');
    flag('  подпись S на холсте ЕСТЬ', !!q.labS, q.labS ? 'есть' : 'пропала');
    flag('  подпись D на холсте ЕСТЬ', !!q.labD, q.labD ? 'есть' : 'пропала');
    await shot('d1-sdsum-q' + W);
  }
  await page.evaluate(() => { CONFIG.Qmin = 0; CONFIG.Qmax = 100; redrawAll(); });
}

/* ═══════════ Д2. Запись после вмешательства не раскрывает скобки ═════ */
if (need('Д2')) {
  head('Д2 · запись кривой после вмешательства не раскрывает скобки');
  const cases = [
    ['субсидия покупателю', '100 - Q', 'Q', 'subsidy', '', 'buyer', 20, '120 - Q'],
    ['субсидия продавцу', '100 - Q', 'Q', 'subsidy', '', 'seller', 20, 'Q - 20'],
    ['налог покупателю', '100 - Q', 'Q', 'tax', '', 'buyer', 20, '80 - Q'],
    ['налог продавцу', '100 - Q', 'Q', 'tax', '', 'seller', 20, 'Q + 20'],
  ];
  for (const [label, dE, sE, type, form, side, rate, wantExpr] of cases) {
    const r = await page.evaluate(([dE, sE, type, form, side, rate]) => {
      p31TaxSetup(dE, sE, type, form || '', side, rate);
      const f = p31Final();
      return {
        final: f,
        afterD: STATE.taxAfterD ? String(STATE.taxAfterD.texExpr || '') : '',
        afterS: STATE.taxAfterS ? String(STATE.taxAfterS.texExpr || '') : '',
        Q: STATE.taxEq ? STATE.taxEq.Q : NaN, Pd: STATE.taxEq ? STATE.taxEq.Pb : NaN,
        Ps: STATE.taxEq ? STATE.taxEq.Ps : NaN,
        budget: STATE.budget, dwl: STATE.dwl,
      };
    }, [dE, sE, type, form, side, rate]);
    const shown = (r.final && r.final.blocks[0]) ? r.final.blocks[0].expr : '';
    console.log('  · ' + label);
    note('запись на табло: ' + (shown || '—') + '   (ожид «' + wantExpr + '»)');
    note('taxAfterD.texExpr = ' + (r.afterD || '—'));
    note('taxAfterS.texExpr = ' + (r.afterS || '—'));
    flag('  нет подстроки «- (-»', shown.indexOf('- (-') < 0, shown);
    flag('  нет подстроки «+ (-»', shown.indexOf('+ (-') < 0, shown);
    flag('  нет подстроки «(Q)»', shown.indexOf('(Q)') < 0, shown);
    flag('  запись равна «' + wantExpr + '»', shown.replace(/\s+/g, ' ').trim() === wantExpr, shown);
  }
  // Числа модели не должны сдвинуться.
  const nums = await page.evaluate(() => {
    p31TaxSetup('100 - Q', 'Q', 'subsidy', '', 'seller', 20);
    const a = { Q: STATE.taxEq.Q, Pd: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, budget: STATE.budget, dwl: STATE.dwl };
    p31TaxSetup('100 - Q', 'Q', 'tax', '', 'seller', 20);
    const b = { Q: STATE.taxEq.Q, Pd: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, budget: STATE.budget, dwl: STATE.dwl };
    p31TaxSetup('120 - Q', 'Q', 'subsidy', 'subbuyer', 'seller', 50);
    const c = { Q: STATE.taxEq.Q, Pd: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps, budget: STATE.budget, dwl: STATE.dwl,
                afterS: String(STATE.taxAfterS.texExpr || ''), afterD: String(STATE.taxAfterD.texExpr || ''),
                shown: (p31Final().blocks[0] || {}).expr || '' };
    return { sub: a, tax: b, pct: c };
  });
  console.log('  · числа модели');
  show('субсидия 20: Q', nums.sub.Q, 60, 1e-6);
  show('субсидия 20: Pd', nums.sub.Pd, 40, 1e-6);
  show('субсидия 20: Ps', nums.sub.Ps, 60, 1e-6);
  show('субсидия 20: расход', nums.sub.budget, -1200, 1e-6);
  show('субсидия 20: DWL', nums.sub.dwl, 100, 1e-6);
  show('налог 20: Q', nums.tax.Q, 40, 1e-6);
  show('налог 20: Pd', nums.tax.Pd, 60, 1e-6);
  show('налог 20: Ps', nums.tax.Ps, 40, 1e-6);
  show('налог 20: сбор', nums.tax.budget, 800, 1e-6);
  show('налог 20: DWL', nums.tax.dwl, 100, 1e-6);
  console.log('  · процентная форма (50 % от цены покупателя, D 120−Q, S Q)');
  show('Q', nums.pct.Q, 72, 1e-6);
  show('Pd', nums.pct.Pd, 48, 1e-6);
  show('Ps', nums.pct.Ps, 72, 1e-6);
  show('расход', nums.pct.budget, -1728, 1e-6);
  show('DWL', nums.pct.dwl, 144, 1e-6);
  note('taxAfterS.texExpr = ' + nums.pct.afterS);
  note('taxAfterD.texExpr = ' + nums.pct.afterD);
  note('на табло: ' + nums.pct.shown);
  await shot('d2-taxes-subsidy');
}

/* ═══════════ Д3. Запись выглядит кривой ═════════════════════════════ */
if (need('Д3')) {
  head('Д3 · запись в блоке «Итоговая функция» кривая (строки центрированы)');
  const r = await page.evaluate(() => {
    resetSceneMemory(); pickScene('sdsum'); redrawAll();
    p31Expand(); redrawAll();
    const f = p31Final();
    const b = f && f.blocks[0];
    // Сколько участков в самой записи: считаем условия в TeX.
    let segs = 0;
    if (b && b.tex) segs = (b.tex.split('\\\\').length);
    return { f, segs,
             stacked: !!(b && b.form === 'stacked'),
             gatheredInTex: !!(b && b.tex.indexOf('gathered') >= 0),
             ifInText: !!(b && b.text.indexOf('если') >= 0) };
  });
  const b = r.f && r.f.blocks[0];
  note('имя блока: ' + (b ? b.name : '—'));
  note('TeX: ' + (b ? b.tex : '—'));
  note('видимый текст: ' + (b ? b.text : '—'));
  show('ширина внутри .katex, px', b ? b.katexW : NaN, null);
  show('ширина контейнера, px', b ? b.hostW : NaN, null);
  show('переполнение (katex − контейнер), px', b ? b.over : NaN, null);
  show('кегль формулы, px', b ? b.fontPx : NaN, null);
  show('кегль условия, px', b ? b.condPx : NaN, null);
  note('раскладка: постоянная часть ' + (b ? b.fixedW : '—')
       + ' + формула ' + (b ? b.formulaW : '—') + ' + условие ' + (b ? b.condW : '—'));
  note('условий усечено многоточием: ' + (b ? b.cut : '—') + ' из ' + (b ? b.conds : '—'));
  show('вылет разметки за контейнер, px', b ? b.spill : NaN, null);
  show('вылет самой правой ячейки, px', b ? b.rowSpill : NaN, null);
  flag('НИЧЕГО НЕ ТОРЧИТ за контейнер', !!(b && b.spill <= 1 && b.rowSpill <= 1),
       b ? ('вылет ' + b.spill + ' / ячейка ' + b.rowSpill) : '—');
  flag('формула НЕ мельче 13 px', !!(b && b.fontPx >= 13), b ? String(b.fontPx) : '—');
  flag('условие НЕ мельче 10 px', !!(b && b.condPx >= 10), b ? String(b.condPx) : '—');
  show('участков в записи', r.segs, null);
  show('визуальных строк внутри скобки', b ? b.rows : NaN, null);
  flag('строк РОВНО столько же, сколько участков', !!(b && b.rows === r.segs),
       (b ? b.rows : '—') + ' строк при ' + r.segs + ' участках');
  flag('форма записи НЕ двухстрочная', !r.stacked, 'data-ff-form = «' + (b ? b.form : '') + '»');
  flag('в компактной записи НЕТ слова «если»', !r.ifInText, b ? b.text : '—');
  show('строк в надзаголовке', b ? b.eyebrowLines : NaN, null);
  flag('надзаголовок в ОДНУ строку', !!(b && b.eyebrowLines === 1), b ? String(b.eyebrowLines) : '—');
  flag('кнопка «развернуть» есть у кусочной записи', !!(b && b.hasExpand),
       b ? String(b.hasExpand) : '—');
  flag('кнопка копирования РОВНО одна', !!(b && b.copies === 1), b ? String(b.copies) : '—');
  await shot('d3-sdsum-final-block');

  /* ⚠️ НАДЗАГОЛОВОК ЛОМАЕТСЯ НЕ ВЕЗДЕ, И ОДНОЙ ШИРИНЫ ДЛЯ ОТВЕТА МАЛО.
     Владелец видел «ИТОГОВАЯ ФУНКЦИЯ» в две строки; на широком окне надпись
     стоит в одну. Проходим по ширинам и печатаем, где именно ломается. */
  head('Д3б · надзаголовок и ширина записи по ширинам окна');
  for (const W of [1920, 1440, 1000, 760, 380]) {
    await page.setViewportSize({ width: W, height: 950 });
    await page.waitForTimeout(350);
    const q = await page.evaluate(() => {
      redrawAll(); p31Expand(); redrawAll();
      if (typeof fitFinalMath === 'function') fitFinalMath();
      const f = p31Final(); const b = f && f.blocks[0];
      return b ? { lines: b.eyebrowLines, katexW: b.katexW, hostW: b.hostW,
                   over: b.over, fontPx: b.fontPx, condPx: b.condPx, rows: b.rows,
                   form: b.form, cut: b.cut, conds: b.conds,
                   spill: b.spill, rowSpill: b.rowSpill } : null;
    });
    if (!q) { note('окно ' + W + ': блока нет'); continue; }
    note('окно ' + W + ' px: надзаголовок строк ' + q.lines
         + ', запись ' + q.katexW + ' против ' + q.hostW + ' (переполнение ' + q.over + ')'
         + ', кегль ' + q.fontPx + '/' + q.condPx
         + ', строк в скобке ' + q.rows + ', усечено ' + q.cut + ' из ' + q.conds
         + ', вылет ' + q.spill + '/' + q.rowSpill);
    await shot('d3-eyebrow-' + W);
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.waitForTimeout(300);
}

/* ═══════════ Д4. Окно разворота записи ══════════════════════════════ */
if (need('Д4')) {
  head('Д4 · разворот записи: слово «если», кегль, колесо, guardPanelBoxes');
  await page.setViewportSize({ width: 1440, height: 950 });
  const pre = await page.evaluate(() => {
    resetSceneMemory(); pickScene('sdsum'); redrawAll();
    p31Expand(); redrawAll();
    /* Метка на узле набранной формулы: если панель ПЕРЕНАБЕРУТ, узел будет
       новый и метка пропадёт. Это и есть проверка guardPanelBoxes. */
    const k = document.querySelector('#info-final .ff-f .katex');
    if (k) k.setAttribute('data-p31mark', '1');
    const box = document.getElementById('info-final');
    return { dom: sx.domain().slice(), marked: !!k, srcLen: (box._srcHtml || '').length };
  });
  note('масштаб до: Q от ' + num(pre.dom[0]) + ' до ' + num(pre.dom[1]));
  // Открываем окно кнопкой, как это делает человек.
  await page.click('#info-final .ff .ff-expand');
  await page.waitForTimeout(350);
  const open = await page.evaluate(() => {
    const m = document.getElementById('ff-modal');
    const mm = document.getElementById('ff-modal-math');
    const k = mm ? mm.querySelector('.katex') : null;
    return {
      open: !!(m && m.classList.contains('open')),
      inert: !!(m && m.hasAttribute('inert')),
      text: p31Text(mm),
      fontPx: mm ? Math.round(parseFloat(getComputedStyle(mm).fontSize) * 10) / 10 : 0,
      align: mm ? getComputedStyle(mm).textAlign : '',
      copies: m ? m.querySelectorAll('[data-ff-expr]').length : 0,
      expr: (document.getElementById('ff-modal-copy') || {}).getAttribute
            ? document.getElementById('ff-modal-copy').getAttribute('data-ff-expr') : '',
      name: p31Text(document.getElementById('ff-modal-name')),
      rect: m ? (() => { const c = m.querySelector('.modal-card').getBoundingClientRect();
                         return { x: Math.round(c.x), y: Math.round(c.y),
                                  w: Math.round(c.width), h: Math.round(c.height) }; })() : null,
      dom: sx.domain().slice(),
    };
  });
  flag('окно открылось', open.open, String(open.open));
  flag('окно НЕ inert, когда открыто', !open.inert, String(open.inert));
  note('запись в окне: ' + open.text);
  flag('в РАЗВОРОТЕ слово «если» ЕСТЬ', open.text.indexOf('если') >= 0, open.text.slice(0, 60));
  show('кегль записи в окне, px', open.fontPx, 20, 0.5);
  flag('выравнивание по левому краю', open.align === 'left' || open.align === 'start', open.align);
  flag('кнопка копирования РОВНО одна', open.copies === 1, String(open.copies));
  note('формат копирования (Math.js): ' + open.expr);
  flag('копируется синтаксис Math.js, а не TeX',
       open.expr.indexOf('?') >= 0 && open.expr.indexOf('\\') < 0, open.expr.slice(0, 50));
  note('имя записи в окне: ' + open.name);
  note('окно: ' + JSON.stringify(open.rect));
  flag('окно помещается в экран', !!(open.rect && open.rect.x >= 0 && open.rect.y >= 0
       && open.rect.w <= 1440 && open.rect.h <= 950),
       open.rect ? (open.rect.w + '×' + open.rect.h + ' при ' + 1440 + '×' + 950) : '—');
  await shot('d4-modal-open');

  /* ⚠️ КОЛЕСО ВНУТРИ ОКНА НЕ ДОЛЖНО МЕНЯТЬ МАСШТАБ ГРАФИКА.
     Крутим ровно над записью — то есть поверх холста, который лежит под окном. */
  const cx = open.rect.x + Math.round(open.rect.w / 2);
  const cy = open.rect.y + Math.round(open.rect.h / 2);
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(250);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(250);
  const after = await page.evaluate(() => ({ dom: sx.domain().slice() }));
  note('масштаб после прокрутки в окне: Q от ' + num(after.dom[0]) + ' до ' + num(after.dom[1]));
  flag('масштаб графика НЕ изменился прокруткой в окне',
       Math.abs(after.dom[0] - pre.dom[0]) < 1e-9 && Math.abs(after.dom[1] - pre.dom[1]) < 1e-9,
       num(pre.dom[1]) + ' → ' + num(after.dom[1]));

  /* ⚠️ КОНТРОЛЬ ОСМЫСЛЕННОСТИ. Проверка выше стоит чего-то только если в той
     же точке БЕЗ окна колесо масштаб МЕНЯЕТ. Иначе она зелёная всегда — хоть
     с заслоном, хоть без него. Закрываем окно и крутим ровно там же. */
  await page.keyboard.press('Escape');
  await page.waitForTimeout(250);
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(300);
  const bare = await page.evaluate(() => ({ dom: sx.domain().slice() }));
  note('масштаб после прокрутки БЕЗ окна: Q от ' + num(bare.dom[0]) + ' до ' + num(bare.dom[1]));
  flag('контроль: без окна та же прокрутка масштаб МЕНЯЕТ',
       Math.abs(bare.dom[1] - pre.dom[1]) > 1e-6,
       num(pre.dom[1]) + ' → ' + num(bare.dom[1]));
  await page.evaluate(() => { CONFIG.Qmin = 0; CONFIG.Qmax = 100; redrawAll(); });
  await page.waitForTimeout(200);

  // Закрытие по Esc.
  await page.keyboard.press('Escape');
  await page.waitForTimeout(250);
  const closed = await page.evaluate(() => {
    const m = document.getElementById('ff-modal');
    const k = document.querySelector('#info-final .ff-f .katex');
    return { open: !!(m && m.classList.contains('open')),
             inert: !!(m && m.hasAttribute('inert')),
             mark: !!(k && k.getAttribute('data-p31mark') === '1') };
  });
  flag('Esc закрывает окно', !closed.open, String(closed.open));
  flag('закрытое окно снова inert', closed.inert, String(closed.inert));
  flag('открытие и закрытие НЕ перенабрали табло (guardPanelBoxes)', closed.mark,
       'метка на узле формулы ' + (closed.mark ? 'цела' : 'пропала — табло перенабрано'));

  /* Закрытие щелчком мимо окна.
     ⚠️ ТОЧКУ «МИМО» НАДО ВЫБИРАТЬ, А НЕ БРАТЬ УГОЛ ЭКРАНА. В левом верхнем
     углу лежит шапка сайта, и она выше окна по слоям: щелчок туда попадает в
     неё, а не в подложку. Берём точку слева от карточки, на её высоте. */
  await page.click('#info-final .ff .ff-expand');
  await page.waitForTimeout(300);
  await page.mouse.click(Math.max(4, Math.round(open.rect.x / 2)),
                         Math.round(open.rect.y + open.rect.h / 2));
  await page.waitForTimeout(250);
  const c2 = await page.evaluate(() => !!document.getElementById('ff-modal').classList.contains('open'));
  flag('щелчок мимо окна закрывает', !c2, String(c2));

  // Закрытие крестиком.
  await page.click('#info-final .ff .ff-expand');
  await page.waitForTimeout(300);
  await page.click('#ff-modal-x');
  await page.waitForTimeout(250);
  const c3 = await page.evaluate(() => !!document.getElementById('ff-modal').classList.contains('open'));
  flag('крестик закрывает', !c3, String(c3));
}

/* ═══════════ Д5. Блок «Итоговая функция» во всех четырёх сценах ═════ */
if (need('Д5')) {
  head('Д5 · компактная запись в четырёх сценах: ширина внутри .katex против контейнера');
  const scenes = [
    ['sdsum', 'Сложение спросов и предложений', () => { resetSceneMemory(); pickScene('sdsum'); redrawAll(); }],
    ['ppfsum', 'Сложение КПВ', () => { resetSceneMemory(); pickScene('ppfsum'); redrawAll(); }],
    ['trade', 'КТВ. Одна страна', () => { resetSceneMemory(); pickScene('trade'); redrawAll(); }],
    ['taxes', 'Налоги и субсидии', () => { p31TaxSetup('100 - Q', 'Q', 'subsidy', '', 'seller', 20); }],
  ];
  for (const [key, name] of scenes) {
    const r = await page.evaluate((k) => {
      if (k === 'taxes') { p31TaxSetup('100 - Q', 'Q', 'subsidy', '', 'seller', 20); }
      else { resetSceneMemory(); pickScene(k); redrawAll(); }
      p31Expand(); redrawAll();
      if (typeof fitFinalMath === 'function') fitFinalMath();
      return p31Final();
    }, key);
    console.log('  · сцена «' + key + '» — ' + name);
    if (!r || !r.blocks.length) { note('блоков «Итоговая функция» нет'); continue; }
    r.blocks.forEach((b, i) => {
      const kind = b.katexW != null && b.conds ? 'кусочная' : 'однострочная';
      note('  блок ' + (i + 1) + ' «' + b.name + '» (' + kind + '): '
           + 'внутри .katex ' + b.katexW + ' px против контейнера ' + b.hostW + ' px'
           + ', кегль ' + b.fontPx + (b.condPx ? '/' + b.condPx : '')
           + ', строк ' + b.rows + ', усечено ' + (b.cut || 0) + ' из ' + (b.conds || 0));
      flag('    ничего не торчит за контейнер', (b.spill == null || b.spill <= 1)
           && (b.rowSpill == null || b.rowSpill <= 1),
           'вылет ' + b.spill + ' / ячейка ' + b.rowSpill);
      flag('    слова «если» в компактной записи нет', b.text.indexOf('если') < 0, b.text.slice(0, 70));
      flag('    кегль формулы не ниже 13 px', b.fontPx >= 13, String(b.fontPx));
    });
    await shot('d5-' + key);
  }
}

if (errs.length) { console.log('\nОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 6).join(' | ')); bad++; }
console.log('\nИТОГО провалов: ' + bad);
await browser.close();
process.exit(bad ? 1 : 0);
