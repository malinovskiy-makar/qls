/* Прибор «внешний вид сложения»: цвета, контраст, непрерывность, подписи,
   левая и правая панели сцены «Сложение спросов и предложений».

   Числа печатаются ВСЕГДА, а не только при провале: этим прибором снимаются
   и «до», и «после», и сравнивать надо именно числа, а не слово OK.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/sum_visual_probe.mjs                 # всё
     node calc2/tests/sum_visual_probe.mjs Ц Н             # только эти разделы

   Разделы:
     Ц — цвета кривых числами, попарные расстояния, совпадения группа/сумма;
     К — контраст ИТОГОВОГО цвета линии к холсту в обеих темах;
     Н — непрерывность: сколько путей на суммарную кривую и сколько разрывов;
     Ш — штрих: есть ли пунктир на «несуществующем» участке суммарной кривой;
     П — подписи на графике: пересечения и выходы за холст;
     Л — левая панель: строки суммарных кривых против строк групп;
     Р — правая панель: обрезка подписей ползунков;
     Г — схема при 2, 3 и 4 группах в каждом семействе;
     В — выпуклость суммарного спроса (наклон падает по модулю).

   ⚠️ ПРИБОР ОБЯЗАН САМ РАСКРЫТЬ ЭКРАН. Сцена открывается со свёрнутыми
   карточками, а измерять видимое — значит занижать. Прокрутка панелей
   сбрасывается перед каждым замером: иначе прямоугольники подписей
   приезжают из другого места.
*/
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SHOTS = process.env.SV_SHOTS || 'reports/calc2_sum_visual/probe';

const want = process.argv.slice(2).map(s => s.toUpperCase());
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

/* ── Наборы ────────────────────────────────────────────────────────────
   Те же два, на которых стоят числа прошлых сессий: сравнивать внешний вид
   имеет смысл только там, где математика уже проверена. */
const SETS = {
  'А': { d: ['100-Q', '60-Q'], s: ['Q', 'Q+20'] },
  'Б': { d: ['100-Q', '60-Q', '40-Q'], s: ['Q-100', 'Q+20'] },
};

const HELP = `
/* Развернуть сцену сложения: столько-то групп, у каждой своя формула. */
function svSetup(dExprs, sExprs) {
  resetSceneMemory();
  pickScene('sdsum');
  sumSetCount('D', dExprs.length);
  sumSetCount('S', sExprs.length);
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  dExprs.forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
  sExprs.forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
  /* Список левой панели пересобираем ЯВНО. updateCurveExpr меняет модель, но
     строку списка не трогает: у человека он и так набирает текст в этом поле.
     Прибор же ставит формулу мимо поля, и без пересборки замер левой панели
     читал бы прежнее значение — прибор врал бы ровно там, где его смотрят. */
  if (typeof renderCurveList === 'function') renderCurveList();
  redrawAll();
}
/* Раскрыть ВСЁ, что сцена свернула, и сбросить прокрутку обеих панелей.
   Иначе замер считает только то, что случайно оказалось на экране. */
function svExpandAll() {
  document.querySelectorAll('.crow-more').forEach(function (m) { m.classList.add('open'); });
  document.querySelectorAll('details').forEach(function (d) { d.open = true; });
  document.querySelectorAll('.sb-card.folded, .card.folded, .pchip-param.folded')
    .forEach(function (e) { e.classList.remove('folded'); });
  ['tools-panel', 'params-body', 'side-body', 'ex-body', 'info-body']
    .forEach(function (id) { var e = document.getElementById(id); if (e) e.scrollTop = 0; });
  document.querySelectorAll('.panel, .side, .sb, .drawer').forEach(function (e) { e.scrollTop = 0; });
}
function svRGB(s) {
  s = String(s == null ? '' : s).trim();
  if (!s || s === 'none' || s === 'transparent') return null;
  if (s.charAt(0) === '#') {
    var h = s.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  var m = s.match(/rgba?\\(([^)]+)\\)/);
  if (m) {
    var p = m[1].split(/[,\\s\\/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2]];
  }
  return null;
}
function svHex(c) {
  if (!c) return '—';
  return '#' + c.map(function (v) { var h = Math.round(v).toString(16); return h.length < 2 ? '0' + h : h; }).join('').toUpperCase();
}
function svLum(c) {
  var f = c.map(function (v) { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
}
function svContrast(a, b) {
  if (!a || !b) return NaN;
  var l1 = svLum(a), l2 = svLum(b);
  if (l1 < l2) { var t = l1; l1 = l2; l2 = t; }
  return Math.round(((l1 + 0.05) / (l2 + 0.05)) * 100) / 100;
}
/* ⚠️ ПРИГЛУШЕНИЕ ПРОЗРАЧНОСТЬЮ СЧИТАЕТСЯ В ЦВЕТЕ, А НЕ ОТДЕЛЬНО.
   Полупрозрачная линия на холсте выглядит своим смешанным цветом, и мерить
   контраст исходного тона значило бы завышать его ровно на приглушение. */
function svBlend(fg, bg, al) {
  if (!fg || !bg) return fg;
  return [0, 1, 2].map(function (i) { return Math.round(fg[i] * al + bg[i] * (1 - al)); });
}
function svDist(a, b) {
  if (!a || !b) return NaN;
  return Math.round(Math.sqrt(Math.pow(a[0]-b[0],2) + Math.pow(a[1]-b[1],2) + Math.pow(a[2]-b[2],2)) * 10) / 10;
}
function svCanvasBg() {
  return svRGB(getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim());
}
/* Все нарисованные куски одной кривой. Полосу попадания мыши (она прозрачная
   и вдесятеро толще) отбрасываем — это не линия графика. */
function svPathsOf(id) {
  return [].slice.call(document.querySelectorAll('#chart path[data-curve="' + id + '"]'))
    .filter(function (p) { return p.getAttribute('data-skip-export') !== '1'; });
}
function svSegInfo(p, bg) {
  var cs = getComputedStyle(p);
  var op = parseFloat(p.getAttribute('opacity') != null ? p.getAttribute('opacity') : (cs.opacity || '1'));
  var so = parseFloat(cs.strokeOpacity || '1');
  var al = (isFinite(op) ? op : 1) * (isFinite(so) ? so : 1);
  var col = svRGB(p.getAttribute('stroke') || cs.stroke);
  var d = p.getAttribute('d') || '';
  return {
    stroke: svHex(col),
    width: Math.round(parseFloat(p.getAttribute('stroke-width') || cs.strokeWidth || '0') * 100) / 100,
    dash: (p.getAttribute('stroke-dasharray') || cs.strokeDasharray || 'none').replace(/px/g, ''),
    alpha: Math.round(al * 100) / 100,
    part: p.getAttribute('data-sum-part') || '',
    moves: (d.match(/M/g) || []).length,
    eff: svHex(svBlend(col, bg, al)),
    contrast: svContrast(svBlend(col, bg, al), bg),
  };
}
// Снимок всех кривых сцены: что в модели и что на самом деле нарисовано.
function svCurves() {
  var bg = svCanvasBg();
  var out = [];
  STATE.curves.forEach(function (c) {
    if (!c.visible || !c.expr) return;
    var segs = svPathsOf(c.id).map(function (p) { return svSegInfo(p, bg); });
    // Образец цвета в строке левой панели.
    var swatch = null;
    var rows = [].slice.call(document.querySelectorAll('#curve-list .curve-row'));
    var idx = STATE.curves.filter(function (x) { return true; }).indexOf(c);
    var row = rows[idx];
    if (row) {
      var sw = row.querySelector('.swatch');
      if (sw) swatch = svHex(svRGB(getComputedStyle(sw).backgroundColor));
    }
    // Точка у ползунка в правой панели.
    var dot = null;
    var chip = document.querySelector('#params-curves .pchip[data-cid="' + c.id + '"] .pchip-dot');
    if (chip) dot = svHex(svRGB(getComputedStyle(chip).backgroundColor));
    out.push({
      id: c.id, label: (typeof curveShortName === 'function') ? curveShortName(c) : (c.label || ''),
      kind: c.kind || '', side: c.sumGroup || '',
      color: svHex(svRGB(c.color)), swatch: swatch, dot: dot,
      segs: segs, bg: svHex(bg),
    });
  });
  return { bg: svHex(bg), curves: out };
}
/* Подписи кривых на холсте. Текст берём из data-raw — там исходная запись,
   а не склейка tspan'ов и невидимой половины KaTeX. */
function svLabels() {
  var chart = document.getElementById('chart');
  if (!chart) return { host: null, items: [], pairs: [], outside: [] };
  var host = chart.getBoundingClientRect();
  var items = [];
  chart.querySelectorAll('text.curve-name').forEach(function (t) {
    var r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    var cs = getComputedStyle(t);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity || '1') < 0.05) return;
    var raw = t.getAttribute('data-raw');
    if (raw == null) {
      var cl = t.cloneNode(true);
      cl.querySelectorAll('.katex-mathml, annotation').forEach(function (x) { x.remove(); });
      raw = cl.textContent;
    }
    items.push({ t: String(raw).trim(), x: r.left, y: r.top, w: r.width, h: r.height });
  });
  /* ⚠️ ПРОБЕЛ МЕЖДУ ПОДПИСЯМИ МЕРИТСЯ ВНУТРЕННИМ ПРОБЕЛОМ САМОЙ ПОДПИСИ.
     Строгое пересечение прямоугольников — слишком слабая линейка: замер 25.08
     дал «пересечений 0» на экране, где «спрос третьей группы» и «спрос второй
     группы» стояли в семи пикселях друг от друга и читались одной строкой
     «спрос третьей группы спрос второй группы». Порог берём у самого шрифта:
     разные подписи обязаны стоять дальше, чем слова внутри одной, — иначе
     глазу нечем разделить их на две. */
  /* ⚠️ ПОРОГ НЕ ИМЕЕТ ПРАВА ОСЛАБНУТЬ ОТ СМЕНЫ ШРИФТА. Пробел меряется в том
     же шрифте, каким набраны подписи, а он у математического набора уже: после
     перехода на обозначения замер дал 3,3 px вместо 7,22, то есть проверка
     стала бы вдвое мягче сама собой. Держим нижний предел в половину кегля. */
  var sample0 = chart.querySelector('text.curve-name');
  var fs0 = sample0 ? parseFloat(getComputedStyle(sample0).fontSize) : 14;
  var spaceW = Math.max(svSpaceWidth(chart), (isFinite(fs0) ? fs0 : 14) / 4);
  var pairs = [], glued = [];
  for (var i = 0; i < items.length; i++) {
    for (var j = i + 1; j < items.length; j++) {
      var a = items[i], b = items[j];
      var ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      var oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ox > 2 && oy > 2) { pairs.push({ a: a.t, b: b.t, ox: Math.round(ox), oy: Math.round(oy) }); continue; }
      // Слипание: по вертикали строки совпадают, а зазор по горизонтали меньше
      // двух внутренних пробелов.
      if (oy > 2 && ox > -(spaceW * 2)) {
        glued.push({ a: a.t, b: b.t, gap: Math.round(-ox * 10) / 10 });
      }
    }
  }
  var outside = items.filter(function (it) {
    return it.x < host.left - 1 || it.y < host.top - 1 ||
           it.x + it.w > host.right + 1 || it.y + it.h > host.bottom + 1;
  }).map(function (it) {
    return { t: it.t, over: Math.round(Math.max(host.left - it.x, host.top - it.y,
      it.x + it.w - host.right, it.y + it.h - host.bottom)) };
  });
  return { host: { w: Math.round(host.width), h: Math.round(host.height) },
           items: items, pairs: pairs, glued: glued, outside: outside,
           spaceW: Math.round(spaceW * 100) / 100 };
}
/* Ширина пробела в шрифте подписей — линейка для «слипания». Меряем тем же
   шрифтом и кеглем, каким набраны сами подписи: разница между строкой с
   пробелами и той же строкой без них, делённая на число пробелов. */
function svSpaceWidth(chart) {
  var sample = chart.querySelector('text.curve-name');
  var size = sample ? getComputedStyle(sample).fontSize : '14px';
  var weight = sample ? getComputedStyle(sample).fontWeight : '600';
  var fam = sample ? getComputedStyle(sample).fontFamily : 'sans-serif';
  var svgEl = chart.querySelector('svg') || chart;
  var mk = function (txt) {
    var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', '-9999'); t.setAttribute('y', '-9999');
    t.style.fontSize = size; t.style.fontWeight = weight; t.style.fontFamily = fam;
    t.textContent = txt;
    svgEl.appendChild(t);
    var w = t.getBBox().width;
    t.remove();
    return w;
  };
  var withSp = mk('аб вг де'), noSp = mk('абвгде');
  var d = (withSp - noSp) / 2;
  return (isFinite(d) && d > 0.5) ? d : 4;
}
/* Строки левой панели: у кого есть поле формулы, у кого нет и чем строка
   суммарной кривой отличается от строки группы. */
function svRows() {
  return [].slice.call(document.querySelectorAll('#curve-list .curve-row')).map(function (row, i) {
    var c = STATE.curves[i];
    var f = row.querySelector('.crow-formula');
    var nm = row.querySelector('span.curve-name');
    var r = row.getBoundingClientRect();
    return {
      label: c ? ((typeof curveShortName === 'function') ? curveShortName(c) : c.label) : '?',
      kind: c ? (c.kind || '') : '',
      hasFormula: !!f,
      formulaText: f ? String((f.querySelector('input') || {}).value || '') : null,
      note: (function () {
        var n = row.querySelector('.crow-auto, .crow-sum-note');
        return n ? n.textContent.replace(/\\s+/g, ' ').trim() : null;
      })(),
      h: Math.round(r.height),
      cls: row.className,
      nameW: nm ? Math.round(nm.getBoundingClientRect().width) : 0,
    };
  });
}
/* Подписи ползунков правой панели: полный текст против того, что видно.
   ⚠️ ОБРЕЗКА ИЩЕТСЯ ДВУМЯ ЛИНЕЙКАМИ. Многоточие ставит CSS (scrollWidth
   больше clientWidth), а до него текст мог быть уже урезан в самом коде
   (…) — вторую обрезку CSS не покажет вовсе. */
function svSliders() {
  return [].slice.call(document.querySelectorAll('#params-curves .pchip')).map(function (chip) {
    var lab = chip.querySelector('.pchip-label');
    var cid = chip.dataset.cid;
    var c = STATE.curves.find(function (x) { return String(x.id) === String(cid); });
    var full = c ? ('Сдвиг ' + ((typeof curveShortName === 'function') ? curveShortName(c) : c.label)) : '';
    var seen = '';
    if (lab) {
      var cl = lab.cloneNode(true);
      cl.querySelectorAll('.katex-mathml, annotation').forEach(function (x) { x.remove(); });
      seen = cl.textContent.replace(/\\s+/g, ' ').trim();
    }
    var track = chip.querySelector('.param-track');
    var sl = chip.querySelector('input[type=range]');
    /* ⚠️ СВЕТЛОТА АКЦЕНТА РЕШАЕТ, КАКОЙ БУДЕТ НЕЗАЛИТАЯ ДОРОЖКА.
       Chromium сам переключает её на тёмную, когда accent-color слишком
       светлый. Порог измерен перебором 25.08: 0,2487 — ещё светлая,
       0,2545 — уже тёмная. Прибор держит запас и требует не выше 0,245:
       иначе на панели оказываются рядом дорожки двух разных видов. */
    var acc = sl ? svRGB(getComputedStyle(sl).accentColor) : null;
    return {
      cid: cid, full: full, seen: seen,
      ellipsisCss: lab ? (lab.scrollWidth > lab.clientWidth + 1) : false,
      ellipsisChar: /…/.test(seen),
      scrollW: lab ? lab.scrollWidth : 0, clientW: lab ? lab.clientWidth : 0,
      accent: svHex(acc),
      accentLum: acc ? Math.round(svLum(acc) * 10000) / 10000 : null,
      trackLeft: track ? Math.round(track.getBoundingClientRect().left * 10) / 10 : null,
      slLeft: sl ? Math.round(sl.getBoundingClientRect().left * 10) / 10 : null,
      slValue: sl ? Number(sl.value) : null,
      slMin: sl ? Number(sl.min) : null, slMax: sl ? Number(sl.max) : null,
    };
  });
}
/* Наклон суммарного спроса на участках: выпуклость к началу координат
   означает, что |наклон| падает с ростом Q. */
function svConvexity(side) {
  var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === side; });
  if (!c) return null;
  var Qmax = 0;
  (STATE.curves || []).forEach(function (x) {
    if (x.sumGroup !== side || x.kind === 'sum' || !x.expr) return;
  });
  Qmax = (typeof modelSpanQ === 'function') ? modelSpanQ() : CONFIG.Qmax;
  var out = [], N = 60, prev = null;
  for (var i = 1; i <= N; i++) {
    var q0 = Qmax * (i - 1) / N, q1 = Qmax * i / N;
    var p0 = evalCurve(c, q0), p1 = evalCurve(c, q1);
    if (!isFinite(p0) || !isFinite(p1)) { prev = null; continue; }
    var k = (p1 - p0) / (q1 - q0);
    out.push({ q: Math.round(((q0 + q1) / 2) * 100) / 100, k: Math.round(k * 1e4) / 1e4 });
    prev = k;
  }
  return { span: Math.round(Qmax * 100) / 100, slopes: out };
}
/* Стык пунктирного и сплошного кусков суммарной кривой в ПИКСЕЛЯХ.
   Щель шириной в шаг сетки на экране видна как разрыв, а число «путей 2»
   само по себе о ней ничего не говорит. */
function svJoinGap(side) {
  var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === side; });
  if (!c) return null;
  var ps = svPathsOf(c.id);
  var gh = ps.find(function (p) { return p.getAttribute('data-sum-part') === 'ghost'; });
  var re = ps.find(function (p) { return p.getAttribute('data-sum-part') === 'real'; });
  if (!gh || !re) return null;
  var a = gh.getPointAtLength(gh.getTotalLength());
  var b = re.getPointAtLength(0);
  return Math.round(Math.hypot(a.x - b.x, a.y - b.y) * 1000) / 1000;
}
/* Все пунктиры сцены с их числами: чем один вид пунктира отличается от
   другого, видно только рядом. */
function svDashes() {
  var chart = document.getElementById('chart');
  if (!chart) return [];
  var bg = svCanvasBg();
  return [].slice.call(chart.querySelectorAll('path[stroke-dasharray], line[stroke-dasharray]'))
    .filter(function (p) { return p.getAttribute('stroke-dasharray') !== 'none'; })
    .map(function (p) {
      var cs = getComputedStyle(p);
      var op = parseFloat(p.getAttribute('opacity') != null ? p.getAttribute('opacity') : (cs.opacity || '1'));
      return {
        what: p.getAttribute('data-sum-part') || p.getAttribute('data-offquad') && 'вне первой четверти'
              || p.getAttribute('data-marginal-tail') && 'предельная кривая'
              || (p.getAttribute('class') || p.parentElement && p.parentElement.getAttribute('class') || 'прочее'),
        dash: p.getAttribute('stroke-dasharray'),
        width: Math.round(parseFloat(p.getAttribute('stroke-width') || cs.strokeWidth || '0') * 100) / 100,
        alpha: Math.round((isFinite(op) ? op : 1) * 100) / 100,
        stroke: svHex(svRGB(p.getAttribute('stroke') || cs.stroke)),
      };
    });
}
/* Есть ли на суммарной кривой участок «рынка здесь нет» — тот, где кривая
   лежит на оси Q (цена ноль при положительном количестве). */
function svGhostRange(side) {
  var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === side; });
  if (!c || !c.expr) return null;
  var span = (typeof modelSpanQ === 'function') ? modelSpanQ() : CONFIG.Qmax;
  var N = 800, lo = null, hi = null;
  for (var i = 0; i <= N; i++) {
    var q = span * i / N;
    var p = evalCurve(c, q);
    if (isFinite(p) && Math.abs(p) < 1e-9) { if (lo == null) lo = q; hi = q; }
  }
  if (lo == null) return null;
  return { from: Math.round(lo * 100) / 100, to: Math.round(hi * 100) / 100 };
}
function svTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('theme', t); } catch (e) {}
  if (typeof refreshColors === 'function') refreshColors();
  redrawAll();
}
`;
await page.addScriptTag({ content: HELP });

const run = (code) => page.evaluate(`(function(){ ${code} })()`);
const setup = async (key) => {
  const s = SETS[key];
  await run(`svSetup(${JSON.stringify(s.d)}, ${JSON.stringify(s.s)}); svExpandAll();`);
  await page.waitForTimeout(260);
};
const setTheme = async (t) => { await run(`svTheme(${JSON.stringify(t)});`); await page.waitForTimeout(240); };
const shot = async (name) => {
  await run(`svExpandAll();`);
  const f = path.join(SHOTS, name + '.png');
  await page.screenshot({ path: f });
  return f;
};

/* ═══ Ц. ЦВЕТА ══════════════════════════════════════════════════════ */
if (need('Ц')) {
  for (const key of ['А', 'Б']) {
    console.log(`\n=== Ц · ЦВЕТА · набор ${key} ===`);
    await setup(key);
    await setTheme('light');
    const snap = await run(`return svCurves();`);
    note('холст ' + snap.bg);
    snap.curves.forEach(c => {
      const seg = c.segs[0] || {};
      note(`${(c.kind === 'sum' ? '[СУММА] ' : '        ') + c.label}`.padEnd(38) +
        ` цвет ${c.color}  на пути ${seg.stroke || '—'}  толщина ${seg.width}  прозр ${seg.alpha}` +
        `  образец ${c.swatch || '—'}  точка ${c.dot || '—'}`);
    });
    const sums = snap.curves.filter(c => c.kind === 'sum');
    const groups = snap.curves.filter(c => c.kind !== 'sum');
    const clash = [];
    groups.forEach(g => sums.forEach(s => { if (g.color === s.color) clash.push(g.label + ' = ' + s.label + ' (' + g.color + ')'); }));
    flag(`ни один цвет группы не совпадает с цветом суммарной кривой`, clash.length === 0, clash.join('; ') || 'совпадений 0');
    // Попарные расстояния между всеми нарисованными цветами.
    const all = snap.curves.map(c => ({ n: c.label, c: c.color }));
    let minD = Infinity, minPair = '';
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
      const d = await run(`return svDist(svRGB(${JSON.stringify(all[i].c)}), svRGB(${JSON.stringify(all[j].c)}));`);
      if (d < minD) { minD = d; minPair = all[i].n + ' × ' + all[j].n; }
    }
    note(`ближайшая пара цветов: ${minPair} — расстояние ${minD}`);
    // Образец и точка обязаны совпасть с линией.
    const mism = snap.curves.filter(c => (c.swatch && c.swatch !== c.color) || (c.dot && c.dot !== c.color))
      .map(c => c.label + ': линия ' + c.color + ', образец ' + c.swatch + ', точка ' + c.dot);
    flag('образец слева и точка справа показывают цвет линии', mism.length === 0, mism.join('; ') || 'расхождений 0');
    await shot(`c-${key}-light`);
  }
}

/* ═══ К. КОНТРАСТ ═══════════════════════════════════════════════════ */
if (need('К')) {
  for (const key of ['А', 'Б']) {
    for (const th of ['light', 'dark']) {
      console.log(`\n=== К · КОНТРАСТ · набор ${key} · тема ${th} ===`);
      await setup(key);
      await setTheme(th);
      const snap = await run(`return svCurves();`);
      note('холст ' + snap.bg);
      let worst = Infinity, worstName = '';
      snap.curves.forEach(c => {
        c.segs.forEach((s, i) => {
          const tag = s.part ? (' [' + s.part + ']') : (c.segs.length > 1 ? ' [' + i + ']' : '');
          note(`${(c.label + tag).padEnd(40)} итог ${s.eff}  контраст ${s.contrast}:1  (толщина ${s.width}, прозр ${s.alpha}, штрих ${s.dash})`);
          if (s.contrast < worst) { worst = s.contrast; worstName = c.label + tag; }
        });
      });
      flag(`контраст каждой линии к холсту не ниже 3:1`, worst >= 3, `худший ${worstName} = ${worst}:1`);
      await shot(`k-${key}-${th}`);
    }
  }
  await setTheme('light');
}

/* ═══ Н. НЕПРЕРЫВНОСТЬ ══════════════════════════════════════════════ */
if (need('Н')) {
  for (const key of ['А', 'Б']) {
    console.log(`\n=== Н · НЕПРЕРЫВНОСТЬ · набор ${key} ===`);
    await setup(key);
    const snap = await run(`return svCurves();`);
    snap.curves.filter(c => c.kind === 'sum').forEach(c => {
      const moves = c.segs.reduce((a, s) => a + s.moves, 0);
      note(`${c.label}: элементов пути ${c.segs.length}, отрезков «M» внутри ${moves}` +
        (c.segs.length > 1 ? ('  части: ' + c.segs.map(s => (s.part || '—') + '/' + s.dash).join(', ')) : ''));
    });
    for (const side of ['D', 'S']) {
      const gap = await run(`return svJoinGap(${JSON.stringify(side)});`);
      if (gap == null) continue;
      show(`стык пунктира и сплошной (${side}), px`, gap, 0, 0.35);
    }
    // Один путь на участок, где рынок есть; пунктирных кусков не больше одного.
    const sums = snap.curves.filter(c => c.kind === 'sum');
    const realOk = sums.every(c => c.segs.filter(s => !s.dash || s.dash === 'none').length === 1);
    const ghostOk = sums.every(c => c.segs.filter(s => s.dash && s.dash !== 'none').length <= 1);
    flag('у каждой суммарной кривой ровно один сплошной путь', realOk,
      sums.map(c => c.label + ': ' + c.segs.filter(s => !s.dash || s.dash === 'none').length).join('; '));
    flag('внутри сплошного пути нет разрывов',
      sums.every(c => c.segs.filter(s => !s.dash || s.dash === 'none').every(s => s.moves === 1)),
      sums.map(c => c.label + ': M=' + c.segs.filter(s => !s.dash || s.dash === 'none').map(s => s.moves).join('/')).join('; '));
    flag('пунктирных кусков не больше одного', ghostOk, '');
  }
}

/* ═══ Ш. ШТРИХ НА НЕСУЩЕСТВУЮЩЕМ УЧАСТКЕ ═══════════════════════════ */
if (need('Ш')) {
  console.log(`\n=== Ш · «РЫНКА ЗДЕСЬ НЕТ» · набор Б (S: Q−100, Q+20) ===`);
  await setup('Б');
  const ghost = await run(`return svGhostRange('S');`);
  note('участок, где суммарное предложение лежит на оси: ' +
    (ghost ? `Q от ${ghost.from} до ${ghost.to}` : 'не найден'));
  const snap = await run(`return svCurves();`);
  const sumS = snap.curves.find(c => c.kind === 'sum' && c.side === 'S');
  const dashed = sumS ? sumS.segs.filter(s => s.dash && s.dash !== 'none') : [];
  const solid = sumS ? sumS.segs.filter(s => !s.dash || s.dash === 'none') : [];
  note('кусков суммарного предложения: сплошных ' + solid.length + ', пунктирных ' + dashed.length);
  dashed.forEach(s => note(`  пунктир: цвет ${s.stroke}, толщина ${s.width}, прозр ${s.alpha}, штрих «${s.dash}»`));
  solid.forEach(s => note(`  сплошной: цвет ${s.stroke}, толщина ${s.width}, прозр ${s.alpha}`));
  flag('несуществующий участок показан пунктиром', dashed.length > 0, 'пунктирных кусков ' + dashed.length);
  const all = await run(`return svDashes();`);
  note('все пунктиры сцены:');
  all.forEach(d => note(`  ${String(d.what).padEnd(24)} штрих «${d.dash}»  толщина ${d.width}  прозр ${d.alpha}  цвет ${d.stroke}`));
  if (dashed.length && solid.length) {
    flag('пунктир того же цвета, что и сплошной', dashed[0].stroke === solid[0].stroke,
      dashed[0].stroke + ' против ' + solid[0].stroke);
    flag('пунктир той же толщины, что и сплошной', Math.abs(dashed[0].width - solid[0].width) < 0.01,
      dashed[0].width + ' против ' + solid[0].width);
    flag('пунктир не бледнее сплошного', Math.abs(dashed[0].alpha - solid[0].alpha) < 0.01,
      dashed[0].alpha + ' против ' + solid[0].alpha);
  }
  await shot('sh-B-ghost');

  /* ── Могут ли два вида пунктира встретиться в одной сцене ──────────
     Пунктир первой четверти в сцене сложения даёт только «пересечение вне
     первой четверти», а оно требует, чтобы равновесия в четверти НЕ было.
     Но участок «рынка здесь нет» — это ровная нулевая цена от Q = 0: любой
     падающий спрос доходит до нуля и обязан пересечь её. Проверяем это не
     рассуждением, а перебором. */
  console.log('\n=== Ш · встречаются ли два вида пунктира в одной сцене ===');
  const TRY = [
    { d: ['10-Q'], s: ['Q-100', 'Q+20'] },
    { d: ['40-Q', '30-Q'], s: ['Q-100', 'Q-50'] },
    { d: ['100-Q', '60-Q'], s: ['Q-100', 'Q+200'] },
    { d: ['5-Q'], s: ['Q-300'] },
    { d: ['100-2*Q'], s: ['Q-100', 'Q+20'] },
  ];
  let both = 0;
  for (const t of TRY) {
    await run(`svSetup(${JSON.stringify(t.d)}, ${JSON.stringify(t.s)}); svExpandAll();`);
    await page.waitForTimeout(180);
    const st = await run(`return { eq: !!STATE.eq, off: !!STATE.offEq,
      ghost: [].slice.call(document.querySelectorAll('#chart path[data-sum-part="ghost"]')).length,
      offq: [].slice.call(document.querySelectorAll('#chart path[data-offquad]')).length };`);
    if (st.ghost > 0 && st.offq > 0) both++;
    note(`D ${t.d.join(', ')} | S ${t.s.join(', ')} -> равновесие ${st.eq ? 'есть' : 'нет'}, ` +
      `пунктир «рынка нет» ${st.ghost}, пунктир вне четверти ${st.offq}`);
  }
  note(both ? `оба вида пунктира встретились в ${both} случаях` :
    'ни в одном случае два вида пунктира в одной сцене не встретились — ' +
    'участок нулевой цены от Q = 0 любой падающий спрос обязан пересечь, ' +
    'и равновесие в первой четверти находится всегда');
  // Числами их всё равно разводим: вес, прозрачность и ритм штриха.
  await setup('Б');
  const gh = (await run(`return svDashes();`)).find(d => d.what === 'ghost');
  note(`«рынка здесь нет»: штрих ${gh ? gh.dash : '—'}, толщина ${gh ? gh.width : '—'}, прозрачность ${gh ? gh.alpha : '—'}`);
  note('«вне первой четверти» (тот же движок, сцена «Спрос и предложение»): штрих 5 4, толщина 1.5, прозрачность 0.65');
  note('«предельная кривая» (монополия): штрих 6 4, толщина 0.55·основной, прозрачность 0.45');
}

/* ═══ П. ПОДПИСИ НА ГРАФИКЕ ════════════════════════════════════════ */
if (need('П')) {
  for (const key of ['А', 'Б']) {
    for (const th of ['light', 'dark']) {
      console.log(`\n=== П · ПОДПИСИ · набор ${key} · тема ${th} ===`);
      await setup(key);
      await setTheme(th);
      const L = await run(`return svLabels();`);
      note(`холст ${L.host.w}×${L.host.h}, подписей ${L.items.length}`);
      L.items.forEach(it => note(`  «${it.t}»  x ${Math.round(it.x)}  y ${Math.round(it.y)}  ${Math.round(it.w)}×${Math.round(it.h)}`));
      L.pairs.forEach(p => note(`  ПЕРЕСЕЧЕНИЕ «${p.a}» × «${p.b}» на ${p.ox}×${p.oy} px`));
      L.glued.forEach(g => note(`  СЛИПЛИСЬ «${g.a}» × «${g.b}» — зазор ${g.gap} px`));
      L.outside.forEach(o => note(`  ЗА КРАЕМ «${o.t}» на ${o.over} px`));
      note(`внутренний пробел шрифта ${L.spaceW} px — порог слипания ${Math.round(L.spaceW * 2 * 10) / 10} px`);
      flag('пересекающихся пар подписей нет', L.pairs.length === 0, 'пар ' + L.pairs.length);
      flag('слипшихся пар подписей нет', L.glued.length === 0, 'пар ' + L.glued.length);
      flag('подписей за краями холста нет', L.outside.length === 0, 'штук ' + L.outside.length);
      await shot(`p-${key}-${th}`);
    }
  }
  await setTheme('light');
}

/* ═══ Л. ЛЕВАЯ ПАНЕЛЬ ══════════════════════════════════════════════ */
if (need('Л')) {
  console.log(`\n=== Л · ЛЕВАЯ ПАНЕЛЬ · набор Б ===`);
  await setup('Б');
  const rows = await run(`return svRows();`);
  rows.forEach(r => note(`${(r.kind === 'sum' ? '[СУММА] ' : '        ') + r.label}`.padEnd(38) +
    ` поле формулы ${r.hasFormula ? 'есть «' + r.formulaText + '»' : 'НЕТ'}` +
    `  пояснение ${r.note ? '«' + r.note + '»' : 'нет'}  высота ${r.h}`));
  const sums = rows.filter(r => r.kind === 'sum');
  flag('у строк суммарных кривых есть чем объяснить пустое место',
    sums.every(r => r.hasFormula || r.note), sums.map(r => r.label + ':' + (r.note || 'ничего')).join('; '));
  await shot('l-B-panel');
}

/* ═══ Р. ПРАВАЯ ПАНЕЛЬ ═════════════════════════════════════════════ */
if (need('Р')) {
  for (const key of ['А', 'Б']) {
    console.log(`\n=== Р · ПРАВАЯ ПАНЕЛЬ · набор ${key} ===`);
    await setup(key);
    const sl = await run(`return svSliders();`);
    sl.forEach(s => note(`полный «${s.full}»  видно «${s.seen}»  ` +
      `CSS-обрезка ${s.ellipsisCss ? 'ДА' : 'нет'} (${s.scrollW}/${s.clientW})  многоточие в тексте ${s.ellipsisChar ? 'ДА' : 'нет'}` +
      `  акцент ${s.accent} L=${s.accentLum}  дорожка слева ${s.trackLeft}`));
    const cut = sl.filter(s => s.ellipsisCss || s.ellipsisChar);
    flag('ни одна подпись ползунка не обрезана', cut.length === 0, 'обрезано ' + cut.length + ' из ' + sl.length);
    const bright = sl.filter(s => s.accentLum != null && s.accentLum > 0.245);
    flag('незалитая дорожка у всех ползунков одного вида (светлота акцента ≤ 0,245)',
      bright.length === 0, bright.map(s => s.accent + ' L=' + s.accentLum).join('; ') || 'светлее порога нет');
    const lefts = [...new Set(sl.map(s => s.slLeft))];
    flag('дорожки соседних строк выровнены по левому краю', lefts.length <= 1, 'левых краёв: ' + lefts.join(', '));
    await shot(`r-${key}-panel`);
  }
}

/* ═══ Г. 2, 3, 4 ГРУППЫ ════════════════════════════════════════════ */
if (need('Г')) {
  for (const n of [2, 3, 4]) {
    console.log(`\n=== Г · ${n} групп в каждом семействе ===`);
    const d = ['100-Q', '60-Q', '40-Q', '30-Q'].slice(0, n);
    const s = ['Q', 'Q+20', 'Q+40', 'Q+55'].slice(0, n);
    await run(`svSetup(${JSON.stringify(d)}, ${JSON.stringify(s)}); svExpandAll();`);
    await page.waitForTimeout(240);
    const snap = await run(`return svCurves();`);
    const sums = snap.curves.filter(c => c.kind === 'sum');
    const groups = snap.curves.filter(c => c.kind !== 'sum');
    const clash = [];
    groups.forEach(g => sums.forEach(x => { if (g.color === x.color) clash.push(g.label + ' = ' + x.label); }));
    const dup = [];
    for (let i = 0; i < groups.length; i++) for (let j = i + 1; j < groups.length; j++)
      if (groups[i].color === groups[j].color) dup.push(groups[i].label + ' = ' + groups[j].label);
    note('цвета: ' + snap.curves.map(c => c.label + ' ' + c.color).join(' · '));
    flag(`${n} групп: цвет группы не совпал с цветом суммы`, clash.length === 0, clash.join('; ') || 'совпадений 0');
    flag(`${n} групп: две группы не делят один цвет`, dup.length === 0, dup.join('; ') || 'совпадений 0');
    let worst = Infinity, wn = '';
    snap.curves.forEach(c => c.segs.forEach(x => { if (x.contrast < worst) { worst = x.contrast; wn = c.label; } }));
    flag(`${n} групп: контраст каждой линии не ниже 3:1`, worst >= 3, `худший ${wn} = ${worst}:1`);
    await shot(`g-${n}`);
  }
}

/* ═══ В. ВЫПУКЛОСТЬ ════════════════════════════════════════════════ */
if (need('В')) {
  for (const key of ['А', 'Б']) {
    console.log(`\n=== В · ВЫПУКЛОСТЬ суммарного спроса · набор ${key} ===`);
    await setup(key);
    const cv = await run(`return svConvexity('D');`);
    if (!cv) { flag('суммарный спрос найден', false, 'нет'); continue; }
    const ks = cv.slopes.filter(s => isFinite(s.k));
    const uniq = [];
    ks.forEach(s => { if (!uniq.length || Math.abs(uniq[uniq.length - 1].k - s.k) > 1e-6) uniq.push(s); });
    note('область ' + cv.span + ', участков наклона ' + uniq.length + ': ' +
      uniq.map(s => `Q≈${s.q}: k=${s.k}`).join('  |  '));
    let mono = true, why = '';
    for (let i = 1; i < uniq.length; i++) {
      if (Math.abs(uniq[i].k) > Math.abs(uniq[i - 1].k) + 1e-6) {
        mono = false; why = `на Q≈${uniq[i].q} |k| вырос с ${Math.abs(uniq[i-1].k)} до ${Math.abs(uniq[i].k)}`;
      }
    }
    flag('|наклон| суммарного спроса монотонно падает с ростом Q', mono, why || 'падает');
  }
}

/* ═══ Ширина 380 px ═════════════════════════════════════════════════ */
if (need('380')) {
  console.log(`\n=== 380 px · узкий экран ===`);
  await page.setViewportSize({ width: 380, height: 900 });
  await page.waitForTimeout(400);
  for (const key of ['А', 'Б']) {
    await setup(key);
    const L = await run(`return svLabels();`);
    note(`набор ${key}: холст ${L.host.w}×${L.host.h}, подписей ${L.items.length}, пересечений ${L.pairs.length}, слипаний ${L.glued.length}, за краем ${L.outside.length}`);
    L.pairs.forEach(p => note(`  ПЕРЕСЕЧЕНИЕ «${p.a}» × «${p.b}» на ${p.ox}×${p.oy} px`));
    L.glued.forEach(g => note(`  СЛИПЛИСЬ «${g.a}» × «${g.b}» — зазор ${g.gap} px`));
    L.outside.forEach(o => note(`  ЗА КРАЕМ «${o.t}» на ${o.over} px`));
    flag(`380px, набор ${key}: пересечений подписей нет`, L.pairs.length === 0, 'пар ' + L.pairs.length);
    flag(`380px, набор ${key}: слипшихся подписей нет`, L.glued.length === 0, 'пар ' + L.glued.length);
    flag(`380px, набор ${key}: подписей за краем нет`, L.outside.length === 0, 'штук ' + L.outside.length);
    await shot(`w380-${key}`);
  }
  await page.setViewportSize({ width: 1440, height: 950 });
}

if (errs.length) { console.log('\nОШИБКИ СТРАНИЦЫ:'); errs.slice(0, 10).forEach(e => console.log('   ' + e)); }
await browser.close();
console.log(bad ? `\nрасхождений: ${bad}` : '\nвсё сошлось');
process.exit(bad ? 1 : 0);
