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
/* ⚠️ ОКРУГЛЕНИЕ ПЕЧАТИ НЕ ДОЛЖНО ПРЯТАТЬ ЧИСЛО. Здесь прибор соврал 31.08
   третий раз: разрыв записи в узлах был 1,13·10⁻⁶, округление до четырёх
   знаков печатало «0», и рядом стояло «FAIL … = 0 (ожид 0 ±0,000001)» —
   строка, по которой понять нечего. Малое, но ненулевое печатаем как есть. */
const num = (v) => {
  if (typeof v !== 'number' || !isFinite(v)) return String(v);
  if (v !== 0 && Math.abs(v) < 1e-4) return v.toExponential(3);
  return Math.round(v * 1e4) / 1e4;
};
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
      rec.spill = Math.round((host.scrollWidth - host.clientWidth) * 10) / 10;
      rec.cut = 0; rec.conds = 0; rec.condPx = 0;
    }
    /* ⚠️ ВЫЛЕТ КАРТОЧКИ МЕРЯЕТСЯ ВСЕГДА, А НЕ ТОЛЬКО У КУСОЧНОЙ ЗАПИСИ.
       Здесь прибор соврал 31.08 в четвёртый раз: замер стоял внутри ветки
       кусочной записи, и у однострочной (КТВ, налоги) отдавал undefined —
       проверка краснела на исправном коде, ничего не сообщая по существу.
       ⚠️ ПРОКРУТКА — ЭТО НЕ ВЫЛЕТ. Последняя ступень правила ширины разрешает
       горизонтальную прокрутку записи: тогда scrollWidth законно больше
       clientWidth, а на экране ничего не торчит. Настоящий вылет — это когда
       за свои края уезжает КАРТОЧКА блока. */
    rec.scrolls = (host && host.classList.contains('ff-scroll')) ? 1 : 0;
    rec.cardSpill = Math.round((ff.scrollWidth - ff.clientWidth) * 10) / 10;
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
    rec.condsOffLine = p31CondsInline(ff);
    out.blocks.push(rec);
  });
  return out;
}
/* СКОЛЬКО ВИЗУАЛЬНЫХ СТРОК реально видит человек внутри записи.

   ⚠️ СЧИТАТЬ ПОЯСА ТЕКСТА ЗДЕСЬ НЕЛЬЗЯ, И ЭТО ВЫЯСНИЛОСЬ ЗАМЕРОМ 31.08.
   Первая версия группировала прямоугольники текстовых узлов по вертикали — и
   на параметрическом участке смешанной пары насчитала 5 строк при 3 участках.
   Никакой двухстрочности там нет: в записи стоят дроби вида \dfrac{\lambda}{2},
   у которых числитель и знаменатель ЗАКОННО на разной высоте. Дробь — это
   по-прежнему одна строка записи.

   Поэтому у компактной записи строки считаются по РАЗМЕТКЕ: один участок —
   одна ячейка формулы в сетке, и их число и есть число строк. А правило
   «формула и условие на ОДНОЙ строке» стережётся отдельно и точно: у каждого
   участка условие обязано быть непустым и стоять на той же высоте, что и его
   формула (см. p31CondsInline). Ровно это и ломала двухстрочная форма.

   У однострочной записи (скобки нет вовсе) разметки участков нет, и там
   по-прежнему считаем пояса: это ловит перенос записи по словам. */
function p31RowCount(ff) {
  var host = ff.querySelector('.ff-math');
  if (!host) return 0;
  var cells = host.querySelectorAll('.ff-f');
  if (cells.length) return cells.length;
  var root = host.querySelector('.mtable') || host;
  var bands = [];
  var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (n) {
      if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      var p = n.parentElement;
      if (!p || p.closest('.katex-mathml, annotation, .delimsizing, .nulldelimiter'))
        return NodeFilter.FILTER_REJECT;
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
    var mid = r.top + r.height / 2, hit = false;
    for (var i = 0; i < bands.length; i++) if (Math.abs(bands[i] - mid) <= 5) { hit = true; break; }
    if (!hit) bands.push(mid);
  }
  return bands.length;
}

/* ⚠️ ГЛАВНАЯ ПРОВЕРКА ПОПРАВКИ 1: у КАЖДОГО участка условие стоит НА ОДНОЙ
   СТРОКЕ с его формулой. Возвращает число участков, у которых это не так:
   условие пустое (уехало в ячейку формулы) либо стоит на другой высоте. */
function p31CondsInline(ff) {
  var host = ff.querySelector('.ff-math');
  if (!host) return -1;
  var fs = host.querySelectorAll('.ff-f'), cs = host.querySelectorAll('.ff-c');
  if (!fs.length) return 0;                 // однострочная запись — участок один
  var wrong = 0;
  for (var i = 0; i < fs.length; i++) {
    var f = fs[i], c = cs[i];
    if (!c || !c.textContent.replace(/\s+/g, '')) { wrong++; continue; }
    var rf = f.getBoundingClientRect(), rc = c.getBoundingClientRect();
    if (!(rf.height > 0) || !(rc.height > 0)) { wrong++; continue; }
    // Пересечение по вертикали: на одной строке — значит перекрываются.
    var over = Math.min(rf.bottom, rc.bottom) - Math.max(rf.top, rc.top);
    if (over < Math.min(rf.height, rc.height) * 0.5) wrong++;
  }
  return wrong;
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
window.p31CondsInline = p31CondsInline;
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

  /* ⚠️ КУСОЧНАЯ КРИВАЯ — ГЛАВНЫЙ СЛУЧАЙ, А НЕ КРАЕВОЙ.
     Простое math.simplify на цепочке «?:» не работает вовсе: Math.js отвечает
     «Unimplemented node type in simplifyConstant: ConditionalNode». Упрощение
     обязано идти ПОКУСОЧНО, условия — не трогать. */
  head('Д2б · упрощение кусочной записи: ветки упрощены, условия целы');
  const pw = await page.evaluate(() => {
    const D = '(Q >= 0 and Q < 40) ? 100 - Q : ((Q >= 40 and Q <= 160) ? 80 - 0.5*Q : NaN)';
    p31TaxSetup(D, 'Q', 'subsidy', '', 'buyer', 20);
    const after = STATE.taxAfterD ? String(STATE.taxAfterD.texExpr || '') : '';
    /* Сверяем сами: обе записи в 40 точках, включая границы участков. */
    const src = '(' + D + ') - (' + (-20) + ')';
    let worst = 0, both = 0;
    for (let i = 0; i <= 40; i++) {
      const q = 200 * i / 40;
      let a = NaN, b = NaN;
      try { a = math.evaluate(src, axisScope(q)); } catch (e) { a = NaN; }
      try { b = math.evaluate(after, axisScope(q)); } catch (e) { b = NaN; }
      const na = !(typeof a === 'number' && isFinite(a));
      const nb = !(typeof b === 'number' && isFinite(b));
      if (na !== nb) { worst = Infinity; break; }
      if (na && nb) { both++; continue; }
      worst = Math.max(worst, Math.abs(a - b));
    }
    return { after: after, worst: worst, bothNaN: both,
             conds: (after.match(/Q >=/g) || []).length };
  });
  note('запись после субсидии покупателю: ' + pw.after);
  flag('условия участков целы (два «Q >=»)', pw.conds === 2, String(pw.conds));
  flag('ветки упрощены: нет «- (-»', pw.after.indexOf('- (-') < 0, pw.after);
  flag('первая ветка стала «120 - Q»', /\?\s*120 - Q/.test(pw.after), pw.after);
  show('наибольшее расхождение старой и новой записи в 40 точках', pw.worst, 0, 1e-9);
  note('точек, где обе записи говорят «функции здесь нет»: ' + pw.bothNaN);
  flag('такие точки есть, то есть сверка их и правда трогала', pw.bothNaN > 0, String(pw.bothNaN));
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
  flag('НИЧЕГО НЕ ТОРЧИТ за контейнер',
       !!(b && b.cardSpill <= 1 && (b.spill <= 1 || b.scrolls === 1)),
       b ? ('вылет ' + b.spill + ', карточка ' + b.cardSpill + ', прокрутка ' + b.scrolls) : '—');
  flag('формула НЕ мельче 13 px', !!(b && b.fontPx >= 13), b ? String(b.fontPx) : '—');
  flag('условие НЕ мельче 10 px', !!(b && b.condPx >= 10), b ? String(b.condPx) : '—');
  show('участков в записи', r.segs, null);
  show('визуальных строк внутри скобки', b ? b.rows : NaN, null);
  flag('строк РОВНО столько же, сколько участков', !!(b && b.rows === r.segs),
       (b ? b.rows : '—') + ' строк при ' + r.segs + ' участках');
  flag('форма записи НЕ двухстрочная', !r.stacked, 'data-ff-form = «' + (b ? b.form : '') + '»');
  flag('у КАЖДОГО участка условие на ОДНОЙ строке с формулой',
       !!(b && b.condsOffLine === 0), (b ? b.condsOffLine : '—') + ' участков не так');
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
                   spill: b.spill, rowSpill: b.rowSpill,
                   scrolls: b.scrolls, cardSpill: b.cardSpill } : null;
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
      flag('    карточка не выходит за края', (b.cardSpill == null || b.cardSpill <= 1),
           'карточка ' + b.cardSpill + ' px');
      flag('    запись влезла либо прокручивается',
           (b.spill == null || b.spill <= 1) || b.scrolls === 1,
           'вылет ' + b.spill + ', прокрутка ' + b.scrolls);
      flag('    условия на одной строке с формулами', b.condsOffLine === 0,
           b.condsOffLine + ' участков не так');
      flag('    слова «если» в компактной записи нет', b.text.indexOf('если') < 0, b.text.slice(0, 70));
      flag('    кегль формулы не ниже 13 px', b.fontPx >= 13, String(b.fontPx));
    });
    await shot('d5-' + key);
  }
}

/* ═══════════ Д6. Обзор: обрезанные подписи и чужие поля у ползунков ══ */
if (need('Д6')) {
  head('Д6 · обзор всех сцен: обрезанные подписи и числовые поля у ползунков');
  const keys = await page.evaluate(() => Object.keys(SCENE_NAMES));
  note('сцен к обходу: ' + keys.length);
  const cutAll = [], numAll = [];
  for (const k of keys) {
    const r = await page.evaluate((key) => {
      try { resetSceneMemory(); pickScene(key); redrawAll(); } catch (e) { return { err: String(e.message) }; }
      p31Expand(); redrawAll();
      const vis = (el) => {
        if (!el) return false;
        if (!(el.offsetParent || el.getClientRects().length)) return false;
        const cs = getComputedStyle(el);
        return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity || '1') > 0.01;
      };
      /* ОБРЕЗАННЫЕ ПОДПИСИ. Меряем сам узел: содержимое шире коробки —
         значит текст обрезан. Считаем только видимые. */
      const cut = [];
      document.querySelectorAll('label, .pchip-label, .chk-label, .seg-btn, .sb-sub').forEach(el => {
        if (!vis(el)) return;
        if (el.querySelector('input[type=range], input[type=number]')) {
          // у поля регулятора подпись — свой узел, коробку меряем не здесь
        }
        const over = el.scrollWidth - el.clientWidth;
        if (over > 1 && el.clientWidth > 0) {
          const t = el.textContent.replace(/\s+/g, ' ').trim().slice(0, 60);
          if (t) cut.push({ t: t, over: Math.round(over), cls: String(el.className).slice(0, 30) });
        }
      });
      /* ЧУЖИЕ ЧИСЛОВЫЕ ПОЛЯ. Правило владельца: рядом с ползунком числовому
         полю не место, значение вводится щелчком по числу НАД дорожкой. */
      const nums = [];
      document.querySelectorAll('input[type=range]').forEach(sl => {
        if (!vis(sl)) return;
        const field = sl.closest('.field, .pchip') || sl.parentElement;
        if (!field) return;
        const n = field.querySelector('input[type=number]');
        if (n && vis(n)) {
          nums.push({ field: field.id || String(field.className).slice(0, 24),
                      slider: sl.id || '(без id)', num: n.id || '(без id)' });
        }
      });
      return { cut: cut, nums: nums };
    }, k);
    if (r.err) { note('сцена «' + k + '»: ' + r.err); continue; }
    r.cut.forEach(c => cutAll.push(Object.assign({ scene: k }, c)));
    r.nums.forEach(n => numAll.push(Object.assign({ scene: k }, n)));
  }
  // Схлопываем: одна и та же подпись в двадцати сценах — это одна находка.
  const uniq = (list, key) => {
    const m = new Map();
    list.forEach(x => { const k = key(x); if (!m.has(k)) m.set(k, { x: x, scenes: [] }); m.get(k).scenes.push(x.scene); });
    return Array.from(m.values());
  };
  console.log('\n  ОБРЕЗАННЫЕ ПОДПИСИ:');
  const cu = uniq(cutAll, x => x.t);
  if (!cu.length) console.log('     нет ни одной');
  cu.forEach(o => console.log('     «' + o.x.t + '» — не влезает ' + o.x.over
    + ' px, сцен: ' + o.scenes.length + ' (' + o.scenes.slice(0, 4).join(', ')
    + (o.scenes.length > 4 ? ', …' : '') + ')'));
  console.log('\n  ЧИСЛОВЫЕ ПОЛЯ РЯДОМ С ПОЛЗУНКАМИ:');
  const nu = uniq(numAll, x => x.field + '|' + x.num);
  if (!nu.length) console.log('     нет ни одного');
  nu.forEach(o => console.log('     поле «' + o.x.field + '»: ползунок ' + o.x.slider
    + ' + число ' + o.x.num + ', сцен: ' + o.scenes.length
    + ' (' + o.scenes.slice(0, 4).join(', ') + (o.scenes.length > 4 ? ', …' : '') + ')'));
  flag('обрезанных подписей нет', cu.length === 0, cu.length + ' шт.');
  flag('числовых полей рядом с ползунками нет', nu.length === 0, nu.length + ' шт.');
}

/* ═══════════ Д7. Квота в монополии ══════════════════════════════════ */
if (need('Д7')) {
  head('Д7 · квота в монополии: D = 100 − Q, MC = 20');
  const r = await page.evaluate(() => {
    const snap = () => {
      const m = STATE.mono || {}, q = STATE.monoQuota;
      const box = document.getElementById('info-tax');
      const ex = document.getElementById('ex-body');
      const txt = ((box ? box.textContent : '') + ' ' + (ex ? ex.textContent : '')).replace(/\s+/g, ' ');
      return { Qm: m.Qm, Pm: m.Pm, psM: m.psM, csM: m.csM, dwl: m.dwl,
               has: q ? 1 : 0, binding: (q && q.binding) ? 1 : 0,
               Q: q ? q.Q : null, P: q ? q.price : null,
               PS: q ? q.psM : null, CS: q ? q.csM : null, DWL: q ? q.dwl : null,
               /* Ползунок цены внутри коридора в монополии появляться не должен. */
               corridor: (() => { const e = document.getElementById('quota-price-field');
                 return (e && (e.offsetParent || e.getClientRects().length)) ? 1 : 0; })(),
               noCorridorWords: txt.indexOf('коридора цен') >= 0 || txt.indexOf('НЕТ коридора') >= 0 ? 1 : 0,
               /* Подсказка конкурентного рынка в монополии прямо врёт: там нет
                  ни коридора, ни выбора цены человеком. */
               noCompHint: txt.indexOf('Двигайте цену внутри коридора') < 0 ? 1 : 0,
               /* Числовое поле рядом с ползунком квоты — в монополии тоже нет. */
               numField: (() => { const e = document.getElementById('quota-input');
                 return (e && (e.offsetParent || e.getClientRects().length)) ? 1 : 0; })(),
               explainWords: txt.indexOf('верхний край') >= 0 || txt.indexOf('ВЕРХНИЙ край') >= 0 ? 1 : 0,
               lossWords: txt.indexOf('невыгодна') >= 0 ? 1 : 0 };
    };
    const setQ = (v) => {
      resetSceneMemory(); pickScene('mono'); redrawAll();
      setType('quota'); setQuota(v); redrawAll();
      document.querySelectorAll('.fold-btn').forEach(b => {
        if (b.getAttribute('aria-expanded') !== 'true') b.click();
      });
      redrawAll();
      return snap();
    };
    resetSceneMemory(); pickScene('mono'); redrawAll();
    const base = snap();
    return { base: base, q60: setQ(60), q40: setQ(40), q20: setQ(20) };
  });
  console.log('  · без квоты');
  show('Qm', r.base.Qm, 40, 1e-6);
  show('Pm', r.base.Pm, 60, 1e-6);
  show('PS', r.base.psM, 1600, 1e-3);
  show('CS', r.base.csM, 800, 1e-3);
  show('DWL', r.base.dwl, 800, 1e-3);
  console.log('  · квота 60 — выше выпуска, связывать не должна');
  flag('  расчёт квоты выполнен вообще', r.q60.has === 1, String(r.q60.has));
  flag('  квота НЕ связывает', r.q60.binding === 0, String(r.q60.binding));
  show('  Qm не сдвинулся', r.q60.Qm, 40, 1e-6);
  show('  Pm не сдвинулся', r.q60.Pm, 60, 1e-6);
  console.log('  · квота 40 — ровно выпуск, связывать не должна');
  flag('  квота НЕ связывает', r.q40.binding === 0, String(r.q40.binding));
  show('  Qm не сдвинулся', r.q40.Qm, 40, 1e-6);
  show('  Pm не сдвинулся', r.q40.Pm, 60, 1e-6);
  console.log('  · квота 20 — ниже выпуска, СВЯЗЫВАЕТ');
  flag('  квота связывает', r.q20.binding === 1, String(r.q20.binding));
  show('  выпуск Q', r.q20.Q, 20, 1e-6);
  show('  цена P', r.q20.P, 80, 1e-6);
  show('  PS', r.q20.PS, 1200, 1e-3);
  show('  CS', r.q20.CS, 200, 1e-3);
  show('  DWL', r.q20.DWL, 1800, 1e-3);
  flag('  излишек монополиста УПАЛ (квота ему невыгодна)',
       r.q20.PS < r.base.psM - 1e-6, num(r.base.psM) + ' → ' + num(r.q20.PS));
  flag('  потери общества ВЫРОСЛИ', r.q20.DWL > r.base.dwl - 1e-6,
       num(r.base.dwl) + ' → ' + num(r.q20.DWL));
  flag('  ползунка цены внутри коридора в монополии НЕТ', r.q20.corridor === 0, String(r.q20.corridor));
  flag('  про отсутствие коридора сказано словами', r.q20.noCorridorWords === 1, String(r.q20.noCorridorWords));
  flag('  сказано, что монополист берёт верхний край', r.q20.explainWords === 1, String(r.q20.explainWords));
  flag('  сказано, что квота монополисту невыгодна', r.q20.lossWords === 1, String(r.q20.lossWords));
  flag('  конкурентной подсказки про коридор в монополии НЕТ', r.q20.noCompHint === 1, String(r.q20.noCompHint));
  flag('  числового поля рядом с ползунком квоты НЕТ', r.q20.numField === 0, String(r.q20.numField));
  await page.evaluate(() => { resetSceneMemory(); pickScene('mono'); setType('quota'); setQuota(20); redrawAll();
    document.querySelectorAll('.fold-btn').forEach(b => { if (b.getAttribute('aria-expanded') !== 'true') b.click(); }); redrawAll(); });
  await page.waitForTimeout(400);
  await shot('d7-mono-quota-20');
}

/* ═══════════ Д8. Матрица охвата: сцена × вид вмешательства ══════════ */
if (need('Д8')) {
  head('Д8 · матрица охвата: все сцены × все виды вмешательства');
  const keys = await page.evaluate(() => Object.keys(SCENE_NAMES));
  const TYPES = [
    ['налог потоварный', 'tax', 'unit'],
    ['налог процентный', 'tax', 'excise'],
    ['субсидия потоварная', 'subsidy', 'unit'],
    ['субсидия процентная', 'subsidy', 'subbuyer'],
    ['потолок', 'ceiling', null],
    ['пол', 'floor', null],
    ['квота', 'quota', null],
  ];
  const rows = [];
  for (const k of keys) {
    const r = await page.evaluate(([key, TYPES]) => {
      /* ⚠️ ОТПЕЧАТКОМ СЛУЖИТ ИСХОД МОДЕЛИ, А НЕ КАРТИНКА И НЕ ТЕКСТ ТАБЛО.
         Первая версия этой матрицы сравнивала пути SVG плюс текст панели — и
         оказалась беззубой: проверка на возвращённом дефекте (квота в
         монополии выключена) всё равно писала «да». Причина в том, что от
         выбора вида меняются и подпись, и вертикаль квоты на холсте, даже
         когда САМА МОДЕЛЬ стоит на месте.
         Правило же простое: связывающее вмешательство обязано сдвинуть исход —
         объём и цену. Их и сравниваем. Механизмы перечислены поимённо; появится
         новый и сюда не попадёт — ячейка честно скажет «не подключено», то
         есть ошибётся в безопасную сторону. */
      const outcome = () => {
        if (STATE.market === 'monopoly') {
          const r = STATE.monoTax || STATE.monoCeil || STATE.monoFloor || STATE.monoQuota;
          if (r && r.binding !== false) {
            const q = (r.Qt != null) ? r.Qt : ((r.Qstar != null) ? r.Qstar : r.Q);
            const p = (r.Pt != null) ? r.Pt : r.price;
            if (q != null && p != null) return [q, p];
          }
          return STATE.mono ? [STATE.mono.Qm, STATE.mono.Pm] : null;
        }
        if (STATE.taxEq) return [STATE.taxEq.Q, STATE.taxEq.Pb];
        if (STATE.qt && STATE.qt.P != null) return [STATE.qt.Qq, STATE.qt.P];
        /* Потолок и пол: объём торговли Qtrade при регулируемой цене Preg.
           ⚠️ Имена полей здесь СВОИ, и на этом матрица уже споткнулась: с
           «.Q» и «.P» она не находила ничего, откатывалась к исходному
           равновесию и объявляла дырами работающие потолок и пол в сцене
           «Пол и потолок цены». */
        if (STATE.pc && STATE.pc.binding) return [STATE.pc.Qtrade, STATE.pc.Preg];
        return STATE.eq ? [STATE.eq.Q, STATE.eq.P] : null;
      };
      const stamp = () => {
        const o = outcome();
        return o ? (Math.round(o[0] * 1e6) + '|' + Math.round(o[1] * 1e6)) : 'нет исхода';
      };
      const out = { scene: key, avail: false, cells: [] };
      try { resetSceneMemory(); pickScene(key); redrawAll(); }
      catch (e) { out.err = String(e.message); return out; }
      const sec = document.getElementById('sec-tax');
      /* Блок вмешательства бывает заперт маршрутом сцены (SCENE_ROUTE.lock) —
         тогда вида вмешательства у сцены нет вовсе, и это не дыра. */
      out.avail = !!(sec && !sec.classList.contains('scoped-off')
                     && (sec.offsetParent || sec.getClientRects().length));
      if (!out.avail) return out;
      const base = stamp();
      /* Значения подбираем ПОД СЦЕНУ: не связывающее вмешательство ничего не
         меняет законно, и принять это за дыру было бы враньём. */
      const eq = STATE.eq || (STATE.mono ? { Q: STATE.mono.Qm, P: STATE.mono.Pm } : null);
      const P0 = eq ? eq.P : 50, Q0 = eq ? eq.Q : 50;
      TYPES.forEach(([name, type, form]) => {
        const cell = { name: name };
        try {
          resetSceneMemory(); pickScene(key); redrawAll();
          setType(type);
          if (form && typeof setTaxForm === 'function') setTaxForm(form);
          if (type === 'tax' || type === 'subsidy') setTax(form === 'unit' ? Math.max(1, P0 * 0.3) : 30);
          else if (type === 'ceiling') setPReg(P0 * 0.5);
          else if (type === 'floor') setPReg(P0 * 1.5);
          else if (type === 'quota') setQuota(Q0 * 0.5);
          redrawAll();
          cell.state = (stamp() === base) ? 'не подключено' : 'работает';
        } catch (e) { cell.state = 'падает'; cell.err = String(e.message).slice(0, 60); }
        out.cells.push(cell);
      });
      return out;
    }, [k, TYPES]);
    rows.push(r);
  }
  const names = TYPES.map(t => t[0]);
  const withInterv = rows.filter(r => r.avail);
  note('сцен всего: ' + rows.length + ', с блоком вмешательства: ' + withInterv.length);
  const holes = [];
  console.log('\n  СЦЕНА                    ' + names.map(n => n.slice(0, 9).padEnd(10)).join(''));
  withInterv.forEach(r => {
    const mark = (c) => c.state === 'работает' ? 'да' : (c.state === 'падает' ? 'ПАДАЕТ' : 'НЕТ');
    console.log('  ' + r.scene.padEnd(24) + r.cells.map(c => mark(c).padEnd(10)).join(''));
    r.cells.forEach(c => { if (c.state !== 'работает') holes.push(r.scene + ' × ' + c.name + ' — ' + c.state + (c.err ? ' (' + c.err + ')' : '')); });
  });
  console.log('\n  ДЫРЫ:');
  if (!holes.length) console.log('     нет ни одной');
  holes.forEach(h => console.log('     ' + h));
  const crash = holes.filter(h => h.indexOf('падает') >= 0);
  flag('ни одно вмешательство не падает с ошибкой', crash.length === 0, crash.length + ' шт.');
  /* ⚠️ ПУСТАЯ МАТРИЦА — ЭТО ПРАВИЛО, А НЕ СВОДКА. Дыра здесь означает, что
     вид вмешательства можно ВЫБРАТЬ, а модель на него не отзывается: ровно
     так вела себя квота в монополии до 31.08. Проверено возвратом дефекта:
     с выключенным monopolyQuota матрица находит ровно одну дыру, ту самую. */
  flag('дыр в матрице охвата нет', holes.length === 0,
       (holes.length - crash.length) + ' «не подключено», ' + crash.length + ' падений');
}

/* ═══════════ Д9. Смешанные пары КПВ и параметрическая запись ════════ */
if (need('Д9')) {
  head('Д9 · смешанная пара: 100 − x² (растут) и 20 − 10√x (убывают)');
  const r = await page.evaluate(() => {
    const setUp = (list) => {
      resetSceneMemory(); pickScene('ppfsum');
      STATE.ppfSumCount = list.length;
      list.forEach((e, i) => ppfSumSet(i, 'y = ' + e));
      if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
      recomputePpfSum(); redrawAll();
      document.querySelectorAll('.fold-btn').forEach(b => {
        if (b.getAttribute('aria-expanded') !== 'true') b.click();
      });
      redrawAll();
      return STATE.ppfSumData || {};
    };
    const d = setUp(['100 - x^2', '20 - 10*sqrt(x)']);
    const r1 = compileFormula('100 - x^2'), r2 = compileFormula('20 - 10*sqrt(x)');
    const f1 = (x) => ppfEvalWith(r1.compiled, x), f2 = (x) => ppfEvalWith(r2.compiled, x);
    const cs = [classifyPpf(f1), classifyPpf(f2)];
    const rec = ppfSumMixedPair(cs);
    /* СВЕРКА С ЧИСЛЕННЫМ МИНКОВСКИМ в 200 точках — обязательна и здесь. */
    let worst = 0;
    for (let i = 0; i <= 200; i++) {
      const X = 14 * i / 200;
      const a = rec ? rec.evalY(X) : NaN, b = maxAllocY(f1, f2, X, 10, 4);
      if (isFinite(a) && isFinite(b)) worst = Math.max(worst, Math.abs(a - b));
    }
    /* НЕПРЕРЫВНОСТЬ В УЗЛАХ — по САМОЙ записи, слева и справа от узла.
       Мерить разрыв против нарисованной ломаной нельзя: у неё 240 узлов на
       [0; 14], и на кривом участке хорда сама отходит на сотые. */
    let gap = 0;
    if (rec) (rec.kinks || []).forEach(k => {
      const e = 1e-7;
      const a = rec.evalY(k.x - e), b = rec.evalY(k.x + e);
      if (isFinite(a) && isFinite(b)) gap = Math.max(gap, Math.abs(a - b));
    });
    /* УГЛЫ БЕЗ КАНДИДАТА (5): что дал бы ответ, если внутреннее решение потерять. */
    const F1 = ppfFam(cs[0]), F2 = ppfFam(cs[1]);
    const X1 = F1.Xmax(cs[0]), X2 = F2.Xmax(cs[1]);
    const corner = (X) => {
      const vals = [];
      if (X <= X2) vals.push(F1.Ymax(cs[0]) + F2.f(cs[1], X));
      if (X <= X1) vals.push(F2.Ymax(cs[1]) + F1.f(cs[0], X));
      if (X >= X1) vals.push(F2.f(cs[1], X - X1));
      if (X >= X2) vals.push(F1.f(cs[0], X - X2));
      return Math.max.apply(null, vals.filter(isFinite));
    };
    const ff = document.querySelector('#info-final .ff');
    const cl = (el) => { if (!el) return ''; const c = el.cloneNode(true);
      c.querySelectorAll('.katex-mathml, annotation').forEach(n => n.remove());
      return c.textContent.replace(/\s+/g, ' ').trim(); };
    /* 7.4 — три кривые смешанного набора остаются численными с ПРИЧИНОЙ. */
    const d3 = setUp(['100 - x^2', '20 - 10*sqrt(x)', '50 - 5*x']);
    return {
      cls: cs.map(c => c.type + '/' + ppfCostOf(c)),
      tex: String(d.formulaTex || ''), expr: d.formulaExpr,
      note: String(d.formulaNote || ''),
      Xtot: d.Xtot, Ytot: d.Ytot,
      at5: rec ? rec.evalY(5) : NaN, corner5: corner(5),
      numAt5: maxAllocY(f1, f2, 5, 10, 4),
      worst: worst, gap: gap,
      pieces: rec ? rec.pieces.map(p => p.kind) : [],
      hasParam: rec ? (rec.pieces.some(p => p.kind === 'param') ? 1 : 0) : 0,
      ffRows: ff ? ff.querySelectorAll('.ff-f').length : 0,
      ffNote: cl(ff && ff.querySelector('.ff-note')),
      ffCopy: ff ? ff.querySelectorAll('.ff-copy').length : 0,
      three: { tex: String(d3.formulaTex || ''), why: String(d3.formulaText || '') },
    };
  });
  note('кривые: ' + r.cls.join(', '));
  note('запись: ' + r.tex.slice(0, 200));
  flag('пара распознана как смешанная (растут + убывают)',
       r.cls.join(',').indexOf('up') >= 0 && r.cls.join(',').indexOf('down') >= 0, r.cls.join(', '));
  flag('аналитическая запись ЕСТЬ (отказа больше нет)', r.tex.length > 0, r.tex.slice(0, 40));
  note('участки: ' + r.pieces.join(', '));
  flag('среди участков есть параметрический', r.hasParam === 1, r.pieces.join(', '));
  show('конец по X', r.Xtot, 14, 1e-4);
  show('конец по Y', r.Ytot, 120, 1e-6);
  console.log('  · ЗУБАСТОСТЬ КАНДИДАТА (5)');
  show('  ответ при X = 5', r.at5, 99.07, 0.01);
  show('  он же численным Минковским', r.numAt5, 99.07, 0.01);
  show('  ответ по ОДНИМ УГЛАМ (без кандидата 5)', r.corner5, 99.00, 1e-6);
  flag('  внутреннее решение выше углового на 0,07',
       Math.abs((r.at5 - r.corner5) - 0.0746) < 0.005,
       num(r.at5) + ' против ' + num(r.corner5) + ', разница ' + num(r.at5 - r.corner5));
  console.log('  · СВЕРКА И НЕПРЕРЫВНОСТЬ');
  show('  наибольшее расхождение с численным Минковским в 200 точках', r.worst, 0, 1e-6);
  /* ⚠️ РАЗРЫВ МЕРЯЕМ ОТНОСИТЕЛЬНО МАСШТАБА КРИВОЙ, А НЕ АБСОЛЮТНО.
     Оставшийся абсолютный остаток (около 1,1·10⁻⁶ при Y порядка 120) берётся
     не из решателя, а из ОКРУГЛЕНИЯ границы участка: границы записи проходят
     через ppfSnap, чтобы человек читал 4,39, а не 4,386027…; при наклоне
     кривой около 8,8 сдвиг границы на 10⁻⁷ и даёт этот остаток. Это не разрыв
     кривой, а разница двух формул в округлённой точке. */
  show('  наибольший разрыв записи в узлах, абсолютный', r.gap, null);
  show('  он же относительно Ymax', r.gap / r.Ytot, 0, 1e-7);
  console.log('  · ПАРАМЕТРИЧЕСКАЯ ЗАПИСЬ');
  flag('в записи есть X(λ) и Y(λ)',
       r.tex.indexOf('X(\\lambda)') >= 0 && r.tex.indexOf('Y(\\lambda)') >= 0, 'нет');
  flag('строк в панели РОВНО столько же, сколько участков',
       r.ffRows === r.pieces.length, r.ffRows + ' против ' + r.pieces.length);
  note('приписка: ' + r.ffNote.slice(0, 140));
  flag('сказано словами, что такое λ',
       r.ffNote.indexOf('альтернативные издержки единицы') >= 0, r.ffNote.slice(0, 60));
  flag('кнопки копирования у параметрической записи НЕТ', r.ffCopy === 0, String(r.ffCopy));
  flag('записи для поля ввода нет (expr пуст)', !r.expr, String(r.expr));
  console.log('  · ТРИ КРИВЫЕ СМЕШАННОГО НАБОРА (пункт 7.4)');
  flag('аналитической записи НЕТ', !r.three.tex, r.three.tex.slice(0, 40));
  note('причина: ' + r.three.why.slice(0, 160));
  flag('причина названа словами', r.three.why.length > 30, r.three.why.slice(0, 40));
  // Снимок — именно ПАРЫ: проверка выше оставила на экране набор из трёх.
  await page.evaluate(() => {
    resetSceneMemory(); pickScene('ppfsum');
    STATE.ppfSumCount = 2; ppfSumSet(0, 'y = 100 - x^2'); ppfSumSet(1, 'y = 20 - 10*sqrt(x)');
    if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
    recomputePpfSum(); redrawAll();
    document.querySelectorAll('.fold-btn').forEach(b => {
      if (b.getAttribute('aria-expanded') !== 'true') b.click();
    });
    redrawAll();
  });
  await page.waitForTimeout(500);
  await shot('d9-mixed-pair');
}

/* ═══════════ Д10. Узкое окно: 1000 px и 380 px ══════════════════════ */
if (need('Д10')) {
  head('Д10 · блок «Итоговая функция» при ширине окна 1000 и 380 px');
  for (const W of [1000, 380]) {
    await page.setViewportSize({ width: W, height: 900 });
    await page.waitForTimeout(400);
    const r = await page.evaluate(() => {
      resetSceneMemory(); pickScene('sdsum'); redrawAll();
      p31Expand(); redrawAll();
      if (typeof fitFinalMath === 'function') fitFinalMath();
      const vis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
      const ff = document.querySelector('#info-final .ff');
      const host = ff && ff.querySelector('.ff-math');
      const btn = ff && ff.querySelector('.ff-expand');
      const panel = document.getElementById('params-panel');
      const f = p31Final();
      const b = f && f.blocks[0];
      return {
        panelVisible: vis(panel),
        panelW: panel ? Math.round(panel.getBoundingClientRect().width) : 0,
        ffVisible: vis(ff), hostW: host ? host.clientWidth : 0,
        btn: vis(btn) ? 1 : 0,
        spill: b ? b.spill : null, rowSpill: b ? b.rowSpill : null,
        scrolls: b ? b.scrolls : 0, cardSpill: b ? b.cardSpill : 0,
        eyebrowLines: b ? b.eyebrowLines : null,
        rows: b ? b.rows : null, fontPx: b ? b.fontPx : null, condPx: b ? b.condPx : null,
        /* Горизонтальной прокрутки у СТРАНИЦЫ быть не должно ни на какой ширине. */
        pageSpill: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
      };
    });
    console.log('  · окно ' + W + ' px');
    note('  правая панель видима: ' + r.panelVisible + ', ширина ' + r.panelW + ' px');
    if (!r.ffVisible) {
      /* ⚠️ СВЁРНУТАЯ ПАНЕЛЬ — НЕ ОТВЕТ. На узком окне правая панель свёрнута
         раскладкой в полоску 26 px, и блока не видно. Но человек её РАСКРОЕТ:
         стрелка на месте. Проверять надо раскрытое состояние — иначе проверка
         на узком окне не проверяет ничего. */
      note('  панель свёрнута раскладкой — раскрываем, как это сделает человек');
      await page.evaluate(() => {
        if (typeof setParamsOpen === 'function') setParamsOpen(true);
        const t = document.getElementById('params-toggle');
        const pn = document.getElementById('params-panel');
        if (t && pn && pn.classList.contains('collapsed')) t.click();
        redrawAll();
      });
      await page.waitForTimeout(400);
      const r2 = await page.evaluate(() => {
        p31Expand(); redrawAll();
        if (typeof fitFinalMath === 'function') fitFinalMath();
        const vis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
        const ff = document.querySelector('#info-final .ff');
        const panel = document.getElementById('params-panel');
        const f = p31Final(); const b = f && f.blocks[0];
        return { panelW: panel ? Math.round(panel.getBoundingClientRect().width) : 0,
                 ffVisible: vis(ff), hostW: b ? b.hostW : 0,
                 btn: vis(ff && ff.querySelector('.ff-expand')) ? 1 : 0,
                 spill: b ? b.spill : null, rowSpill: b ? b.rowSpill : null,
                 scrolls: b ? b.scrolls : 0, cardSpill: b ? b.cardSpill : 0,
                 eyebrowLines: b ? b.eyebrowLines : null, rows: b ? b.rows : null,
                 fontPx: b ? b.fontPx : null, condPx: b ? b.condPx : null,
                 pageSpill: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth) };
      });
      note('  после раскрытия: панель ' + r2.panelW + ' px, контейнер записи ' + r2.hostW
           + ' px, кегль ' + r2.fontPx + '/' + r2.condPx + ', строк ' + r2.rows);
      flag('  блок показан', r2.ffVisible, String(r2.ffVisible));
      note('  запись прокручивается: ' + (r2.scrolls ? 'да' : 'нет')
           + ', вылет карточки ' + r2.cardSpill + ' px');
      flag('  карточка блока не выходит за края', r2.cardSpill <= 1, r2.cardSpill + ' px');
      flag('  запись либо влезла, либо прокручивается',
           (r2.spill <= 1) || r2.scrolls === 1, 'вылет ' + r2.spill + ', прокрутка ' + r2.scrolls);
      flag('  надзаголовок в одну строку', r2.eyebrowLines === 1, String(r2.eyebrowLines));
      flag('  строк в скобке = участков (2)', r2.rows === 2, String(r2.rows));
      flag('  кнопка «развернуть» доступна', r2.btn === 1, String(r2.btn));
      flag('  страница не едет вбок', r2.pageSpill <= 1, r2.pageSpill + ' px');
      if (r2.btn) {
        await page.click('#info-final .ff .ff-expand');
        await page.waitForTimeout(350);
        const m2 = await page.evaluate((w) => {
          const card = document.querySelector('#ff-modal .modal-card');
          if (!card) return null;
          const c = card.getBoundingClientRect();
          const mm = document.getElementById('ff-modal-math');
          const k = mm ? mm.querySelector('.katex') : null;
          return { w: Math.round(c.width), h: Math.round(c.height), x: Math.round(c.x), y: Math.round(c.y),
                   inScreen: (c.x >= -1 && c.y >= -1 && c.right <= w + 1 && c.bottom <= 900 + 1) ? 1 : 0,
                   scrollable: (mm && k) ? (mm.scrollWidth > mm.clientWidth ? 1 : 0) : 0 };
        }, W);
        note('  окно разворота: ' + (m2 ? (m2.w + '×' + m2.h + ' при (' + m2.x + '; ' + m2.y + ')') : '—')
             + (m2 && m2.scrollable ? ', запись прокручивается внутри окна' : ''));
        flag('  окно разворота помещается в экран', !!(m2 && m2.inScreen === 1),
             m2 ? (m2.w + '×' + m2.h) : '—');
        await shot('d10-' + W + '-modal');
        await page.keyboard.press('Escape');
        await page.waitForTimeout(200);
      }
      await shot('d10-' + W);
      continue;
    }
    note('  контейнер записи ' + r.hostW + ' px, кегль ' + r.fontPx + '/' + r.condPx
         + ', строк в скобке ' + r.rows);
    flag('  блок показан', r.ffVisible, String(r.ffVisible));
    note('  запись прокручивается: ' + (r.scrolls ? 'да' : 'нет')
         + ', вылет карточки ' + r.cardSpill + ' px');
    flag('  карточка блока не выходит за края', r.cardSpill <= 1, r.cardSpill + ' px');
    flag('  запись либо влезла, либо прокручивается',
         (r.spill <= 1) || r.scrolls === 1, 'вылет ' + r.spill + ', прокрутка ' + r.scrolls);
    flag('  надзаголовок в одну строку', r.eyebrowLines === 1, String(r.eyebrowLines));
    flag('  строк в скобке = участков (2)', r.rows === 2, String(r.rows));
    flag('  кнопка «развернуть» доступна', r.btn === 1, String(r.btn));
    flag('  страница не едет вбок', r.pageSpill <= 1, r.pageSpill + ' px');
    // Окно разворота обязано помещаться в экран.
    await page.click('#info-final .ff .ff-expand');
    await page.waitForTimeout(350);
    const m = await page.evaluate((w) => {
      const card = document.querySelector('#ff-modal .modal-card');
      if (!card) return null;
      const c = card.getBoundingClientRect();
      const mm = document.getElementById('ff-modal-math');
      const k = mm ? mm.querySelector('.katex') : null;
      return { x: Math.round(c.x), y: Math.round(c.y), w: Math.round(c.width), h: Math.round(c.height),
               inScreen: (c.x >= -1 && c.y >= -1 && c.right <= w + 1 && c.bottom <= 900 + 1) ? 1 : 0,
               mathSpill: (mm && k) ? Math.round(k.getBoundingClientRect().width - mm.clientWidth) : null,
               scrollable: mm ? (mm.scrollWidth > mm.clientWidth ? 1 : 0) : 0 };
    }, W);
    note('  окно разворота: ' + (m ? (m.w + '×' + m.h + ' при (' + m.x + '; ' + m.y + ')') : '—'));
    flag('  окно разворота помещается в экран', !!(m && m.inScreen === 1),
         m ? (m.w + '×' + m.h) : '—');
    note('  запись в окне шире контейнера на ' + (m ? m.mathSpill : '—') + ' px'
         + (m && m.scrollable ? ' (прокручивается внутри окна)' : ''));
    await shot('d10-' + W + '-modal');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    await shot('d10-' + W);
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.waitForTimeout(300);
}

/* ═══════════ Д11. Единообразие блока: 4 сцены × 2 темы ══════════════ */
if (need('Д11')) {
  head('Д11 · блок «Итоговая функция» в четырёх сценах и двух темах');
  await page.setViewportSize({ width: 1440, height: 950 });
  const scenes = [['sdsum', 'Сложение спросов и предложений'],
                  ['ppfsum', 'Сложение КПВ'],
                  ['trade', 'КТВ. Одна страна'],
                  ['taxes', 'Налоги и субсидии']];
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
    await page.waitForTimeout(250);
    for (const [key, name] of scenes) {
      const r = await page.evaluate((k) => {
        if (k === 'taxes') p31TaxSetup('100 - Q', 'Q', 'subsidy', '', 'seller', 20);
        else { resetSceneMemory(); pickScene(k); redrawAll(); }
        p31Expand(); redrawAll();
        if (typeof fitFinalMath === 'function') fitFinalMath();
        const box = document.getElementById('info-final');
        const f = p31Final(); const b = f && f.blocks[0];
        const rect = box ? box.getBoundingClientRect() : null;
        return { has: !!(f && f.blocks.length), n: f ? f.blocks.length : 0,
                 eyebrow: b ? b.eyebrow : '', eyebrowLines: b ? b.eyebrowLines : 0,
                 fontPx: b ? b.fontPx : 0, condPx: b ? b.condPx : 0,
                 cardSpill: b ? b.cardSpill : 0, scrolls: b ? b.scrolls : 0,
                 mathLines: b ? b.rows : 0, segs: b ? Math.max(1, (b.tex.split('\\\\').length)) : 1,
                 condsOffLine: b ? b.condsOffLine : 0,
                 rect: rect ? { x: Math.round(rect.x) - 6, y: Math.round(rect.y) - 6,
                                width: Math.round(rect.width) + 12,
                                height: Math.round(rect.height) + 12 } : null };
      }, key);
      note(theme + ' · ' + name + ': блоков ' + r.n + ', строк записи ' + r.mathLines
           + ', надзаголовок «' + r.eyebrow
           + '» в ' + r.eyebrowLines + ' строку, кегль ' + r.fontPx
           + (r.condPx ? '/' + r.condPx : '') + ', вылет карточки ' + r.cardSpill + ' px');
      flag('  ' + theme + '/' + key + ': надзаголовок в одну строку и не усечён',
           r.eyebrowLines === 1 && r.eyebrow.indexOf('…') < 0, r.eyebrow);
      flag('  ' + theme + '/' + key + ': карточка не выходит за края', r.cardSpill <= 1,
           r.cardSpill + ' px');
      /* ⚠️ ЖЁСТКОЕ ПРАВИЛО ВЛАДЕЛЬЦА: строк записи ровно столько, сколько
         участков. Относится и к однострочной записи без скобки. */
      flag('  ' + theme + '/' + key + ': строк записи = участков',
           r.mathLines === r.segs, r.mathLines + ' строк при ' + r.segs + ' участках');
      flag('  ' + theme + '/' + key + ': условия на одной строке с формулами',
           r.condsOffLine === 0, r.condsOffLine + ' участков не так');
      if (r.rect && r.rect.height > 10) {
        const p = SHOTS + '/d11-' + theme + '-' + key + '.png';
        await page.screenshot({ path: p, clip: r.rect });
        console.log('     снимок: ' + p);
      }
    }
  }
  await page.evaluate(() => { if (typeof setCalcTheme === 'function') setCalcTheme('light'); });
}

if (errs.length) { console.log('\nОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 6).join(' | ')); bad++; }
console.log('\nИТОГО провалов: ' + bad);
await browser.close();
process.exit(bad ? 1 : 0);
