/* Тесты рисователя чертежей Econ Rush (game/static/game/figure.js).

   Почему настоящий браузер, а не заглушка DOM: проверять надо РАСКЛАДКУ —
   не налезла ли подпись на подпись и не легла ли она на кривую. Ширину
   надписи в пикселях знает только движок вёрстки; любая заглушка вернула бы
   ноль, и тест «зелёный» ничего бы не значил. Playwright уже стоит в проекте
   (см. CLAUDE.md), браузеры скачаны.

   Сервер НЕ нужен: файл рисователя подкладывается в пустую страницу.
   Запуск отдельно:  node game/tests/figure_draw.mjs
*/
import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const STATIC = join(HERE, '..', 'static', 'game');
const JS = readFileSync(join(STATIC, 'figure.js'), 'utf8');
const CSS = readFileSync(join(STATIC, 'figure.css'), 'utf8');

/* ---------- контрольные раскладки ----------
   Двенадцать штук: шесть «как в сюжетах режима» и шесть заведомо тесных —
   точки вплотную, длинные подписи, точка ровно на пересечении кривых. */
const L = [];

function lin(role, label, from, to, dash) {
  return { role, label, from, to, dash: !!dash };
}
function pt(x, y, label, role, coords) {
  const p = { x, y, label: label || '', role: role || 'd' };
  if (coords) p.coords = true;
  return p;
}
function poly(role, points, outline) {
  const a = { role, label: '', points };
  if (outline) a.outline = true;
  return a;
}

// 1. Излишек потребителя: равновесие ЛЕЖИТ НА ДВУХ кривых сразу.
L.push({ name: 'излишек потребителя', fig: {
  kind: 'cs', xmax: 100, ymax: 120, xlabel: 'Q, шт.', ylabel: 'P, руб.',
  lines: [lin('d', 'D', [0, 100], [100, 0]), lin('s', 'S', [0, 40], [40, 120])],
  areas: [poly('cs', [[0, 100], [0, 80], [20, 80]], true)],
  points: [pt(20, 80, 'E', 'd', true)],
  marks: [{ axis: 'x', at: 20, label: 'Q^*' }, { axis: 'y', at: 80, label: 'P^*' }],
  callouts: [{ text: 'CS = 200', role: 'zone',
               points: [[0, 100], [0, 80], [20, 80]] }] } });

// 2. Налог: три точки на одной вертикали — классическая давка подписей.
L.push({ name: 'налог: три цены на одной вертикали', fig: {
  kind: 'tax', xmax: 60, ymax: 140, xlabel: 'Q, тыс.', ylabel: 'P, руб.',
  lines: [lin('d', 'D', [0, 120], [60, 0]), lin('s', 'S', [0, 30], [60, 90]),
          lin('s', "S'", [0, 60], [60, 120], true)],
  areas: [poly('dwl', [[20, 80], [20, 50], [30, 60]], true)],
  points: [pt(30, 60, 'E_0', 'd', true), pt(20, 80, 'B', 'd', true),
           pt(20, 50, 'C', 's', true)],
  marks: [{ axis: 'y', at: 80, label: 'P_b' }, { axis: 'y', at: 50, label: 'P_s' },
          { axis: 'y', at: 60, label: 'P_0' }, { axis: 'x', at: 20, label: 'Q_1' },
          { axis: 'x', at: 30, label: 'Q_0' }],
  callouts: [{ text: 'DWL = 150', role: 'dwl',
               points: [[20, 80], [20, 50], [30, 60]] }] } });

// 3. Потолок цены: короткая сторона рынка.
L.push({ name: 'потолок цены', fig: {
  kind: 'ceiling', xmax: 80, ymax: 120, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [80, 20]), lin('s', 'S', [0, 20], [80, 100]),
          lin('reg', 'потолок', [0, 40], [80, 40])],
  areas: [poly('dwl', [[20, 80], [20, 40], [40, 60]], true)],
  points: [pt(20, 80, 'A', 'd', true), pt(60, 40, 'D_2', 'd', true),
           pt(20, 40, 'S_2', 's', true)],
  marks: [{ axis: 'x', at: 20, label: 'продано' }, { axis: 'x', at: 60, label: 'спрос' },
          { axis: 'y', at: 40, label: 'P̄' }] } });

// 4. Монополия: четыре кривые + прямоугольник прибыли.
L.push({ name: 'монополия с ATC', fig: {
  kind: 'monopoly', xmax: 100, ymax: 120, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [100, 0]), lin('mr', 'MR', [0, 100], [50, 0]),
          lin('mc', 'MC', [0, 20], [100, 20]),
          lin('atc', 'ATC', [10, 60], [100, 24])],
  areas: [poly('zone', [[0, 30], [40, 30], [40, 60], [0, 60]], true)],
  points: [pt(40, 60, 'M', 'd', true)],
  marks: [{ axis: 'y', at: 60, label: 'P^*' }, { axis: 'y', at: 30, label: 'ATC' },
          { axis: 'y', at: 20, label: 'MC' }, { axis: 'x', at: 40, label: 'Q^*' }],
  callouts: [{ text: 'прибыль = 1200', role: 'zone',
               points: [[0, 30], [40, 30], [40, 60], [0, 60]] }] } });

// 5. Единичная эластичность: прямоугольник выручки.
L.push({ name: 'единичная эластичность', fig: {
  kind: 'elasticity', xmax: 60, ymax: 120, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [50, 0])],
  areas: [poly('zone', [[0, 0], [25, 0], [25, 50], [0, 50]], true)],
  points: [pt(25, 50, '|E| = 1', 'd', true)],
  marks: [{ axis: 'x', at: 25, label: 'Q' }, { axis: 'y', at: 50, label: 'P' }],
  callouts: [{ text: 'TR = 1250', role: 'zone',
               points: [[0, 0], [25, 0], [25, 50], [0, 50]] }] } });

// 6. КПВ двух хозяйств: ломаная с изломом.
L.push({ name: 'совместная КПВ (ломаная)', fig: {
  kind: 'ppf', xmax: 120, ymax: 90, xlabel: 'X, шт.', ylabel: 'Y, шт.',
  polylines: [{ role: 'ppf', label: 'КПВ', dash: false,
                points: [[0, 70], [60, 40], [100, 0]] }],
  areas: [poly('feasible', [[0, 0], [0, 70], [60, 40], [100, 0]], true)],
  points: [pt(60, 40, 'излом', 'd', true)],
  marks: [{ axis: 'x', at: 60, label: '' }, { axis: 'y', at: 40, label: '' }] } });

// 7–12. Заведомо тесные раскладки.
L.push({ name: 'тесно: две точки в пяти пикселях', fig: {
  kind: 'tight', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [100, 0])],
  points: [pt(50, 50, 'A', 'd', true), pt(52, 48, 'B', 's', true)] } });

L.push({ name: 'тесно: четыре точки в углу', fig: {
  kind: 'corner', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 20], [100, 0])],
  points: [pt(90, 3, 'K', 'd', true), pt(95, 6, 'L', 's', true),
           pt(85, 9, 'M', 'mr', true), pt(97, 1, 'N', 'mc', true)] } });

L.push({ name: 'тесно: длинные подписи', fig: {
  kind: 'longlabels', xmax: 40, ymax: 40, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 40], [40, 0])],
  points: [pt(10, 30, 'равновесие до', 'd', true),
           pt(30, 10, 'равновесие после', 's', true)] } });

L.push({ name: 'тесно: точка на пересечении трёх кривых', fig: {
  kind: 'triple', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [100, 0]), lin('s', 'S', [0, 0], [100, 100]),
          lin('mc', 'MC', [0, 50], [100, 50])],
  points: [pt(50, 50, 'E', 'd', true)] } });

L.push({ name: 'тесно: пять засечек подряд по X', fig: {
  kind: 'ticks', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [100, 0])],
  points: [pt(50, 50, 'E', 'd', true)],
  marks: [{ axis: 'x', at: 40, label: 'Q_1' }, { axis: 'x', at: 44, label: 'Q_2' },
          { axis: 'x', at: 48, label: 'Q_3' }, { axis: 'x', at: 52, label: 'Q_4' },
          { axis: 'x', at: 56, label: 'Q_5' }] } });

L.push({ name: 'тесно: точка у самого верха оси', fig: {
  kind: 'top', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
  lines: [lin('d', 'D', [0, 100], [100, 0])],
  points: [pt(2, 98, 'верх', 'd', true), pt(8, 92, 'рядом', 's', true)] } });

/* ---------- прогон ---------- */
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
const consoleErrors = [];
page.on('pageerror', (e) => consoleErrors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
await page.setContent(
  `<!doctype html><meta charset="utf-8"><style>${CSS}</style>` +
  `<body style="font-family:system-ui"><div id="root"></div>`);
await page.addScriptTag({ content: JS });

/* Измеритель: рисует фигуру и возвращает настоящие рамки подписей,
   отрезки сплошных кривых и координаты кружков. */
await page.evaluate(() => {
  window.measure = function (fig) {
    var root = document.getElementById('root');
    root.innerHTML = '';
    var node = window.drawFigure(fig);
    if (!node) return null;
    root.appendChild(node);
    var svg = node.querySelector('svg');
    function box(el) {
      var b = el.getBBox();
      return { x0: b.x, y0: b.y, x1: b.x + b.width, y1: b.y + b.height,
               text: el.textContent, cls: el.getAttribute('class') || '' };
    }
    var texts = Array.prototype.map.call(svg.querySelectorAll('text'), box);
    var segs = Array.prototype.map.call(
      svg.querySelectorAll('line'), function (l) {
        return { x1: +l.getAttribute('x1'), y1: +l.getAttribute('y1'),
                 x2: +l.getAttribute('x2'), y2: +l.getAttribute('y2'),
                 dash: !!l.getAttribute('stroke-dasharray'),
                 cls: l.getAttribute('class') || '',
                 w: +l.getAttribute('stroke-width') };
      });
    var polylines = Array.prototype.map.call(
      svg.querySelectorAll('polyline'), function (p) {
        return { points: p.getAttribute('points'),
                 dash: !!p.getAttribute('stroke-dasharray') };
      });
    var polygons = Array.prototype.map.call(
      svg.querySelectorAll('polygon'), function (p) {
        return { points: p.getAttribute('points'),
                 fill: p.getAttribute('fill'),
                 fillOpacity: p.getAttribute('fill-opacity'),
                 stroke: p.getAttribute('stroke') };
      });
    var circles = Array.prototype.map.call(
      svg.querySelectorAll('circle'), function (c) {
        return { cx: +c.getAttribute('cx'), cy: +c.getAttribute('cy') };
      });
    return { texts: texts, segs: segs, polygons: polygons, circles: circles,
             polylines: polylines, viewBox: svg.getAttribute('viewBox'),
             par: svg.getAttribute('preserveAspectRatio') };
  };
});

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log('✓ ' + name); }
  else { fail++; console.log('✗ ' + name + (detail ? '\n    ' + detail : '')); }
}

function overlaps(a, b) {
  const pad = 0.5;   // касание рамками не считаем наложением
  return !(a.x1 - pad <= b.x0 || b.x1 - pad <= a.x0
        || a.y1 - pad <= b.y0 || b.y1 - pad <= a.y0);
}
function segHitsRect(s, r) {
  const p = { x: s.x1, y: s.y1 }, q = { x: s.x2, y: s.y2 };
  if ((p.x < r.x0 && q.x < r.x0) || (p.x > r.x1 && q.x > r.x1)
      || (p.y < r.y0 && q.y < r.y0) || (p.y > r.y1 && q.y > r.y1)) return false;
  if ((p.x >= r.x0 && p.x <= r.x1 && p.y >= r.y0 && p.y <= r.y1)
      || (q.x >= r.x0 && q.x <= r.x1 && q.y >= r.y0 && q.y <= r.y1)) return true;
  const dx = q.x - p.x, dy = q.y - p.y;
  const cs = [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]];
  let sign = 0;
  for (const c of cs) {
    const cr = dx * (c[1] - p.y) - dy * (c[0] - p.x);
    const s2 = cr > 0 ? 1 : (cr < 0 ? -1 : 0);
    if (s2 === 0) return true;
    if (sign === 0) sign = s2; else if (s2 !== sign) return true;
  }
  return false;
}

/* --- 1. Подписи точек не пересекаются ни с чем и не лежат на кривых --- */
for (const layout of L) {
  const m = await page.evaluate((f) => window.measure(f), layout.fig);
  const pts = m.texts.filter((t) => t.cls.indexOf('fig-lbl-point') !== -1);
  const others = m.texts.filter((t) => t !== undefined);
  let bad = [];
  for (let i = 0; i < pts.length; i++) {
    for (let j = 0; j < others.length; j++) {
      const o = others[j];
      if (o.text === pts[i].text && o.x0 === pts[i].x0 && o.y0 === pts[i].y0) continue;
      if (overlaps(pts[i], o)) bad.push(`«${pts[i].text}» × «${o.text}»`);
    }
  }
  check(`раскладка «${layout.name}»: подписи точек не налезают`,
        bad.length === 0, bad.join('; '));

  const curves = m.segs.filter((s) => !s.dash && s.w > 2 && !s.cls);
  const onCurve = pts.filter((t) => curves.some((c) => segHitsRect(c, t)))
                     .map((t) => t.text);
  check(`раскладка «${layout.name}»: подписи точек не лежат на кривой`,
        onCurve.length === 0, onCurve.join('; '));
}

/* --- 1б. Если места рядом нет, подпись уезжает и к ней ведётся выноска --- */
{
  const m = await page.evaluate(
    (f) => window.measure(f), L.find((x) => x.name.indexOf('в углу') !== -1).fig);
  check('в тесном углу у отъехавших подписей есть выноски',
        m.segs.some((s) => s.cls.indexOf('fig-lbl-tail') !== -1),
        m.segs.map((s) => s.cls).join('|'));
  // а на просторном чертеже выносок быть не должно — иначе они шум
  const roomy = await page.evaluate((f) => window.measure(f), L[0].fig);
  check('на просторном чертеже выносок у подписей нет',
        !roomy.segs.some((s) => s.cls.indexOf('fig-lbl-tail') !== -1),
        roomy.segs.map((s) => s.cls).join('|'));
}

/* --- 2. Порядок обхода вершин многоугольника значения не имеет --- */
{
  const cw = { kind: 'x', xmax: 100, ymax: 100, xlabel: '', ylabel: '',
               areas: [poly('zone', [[10, 10], [10, 60], [60, 60], [60, 10]], true)] };
  const ccw = { kind: 'x', xmax: 100, ymax: 100, xlabel: '', ylabel: '',
                areas: [poly('zone', [[10, 10], [60, 10], [60, 60], [10, 60]], true)] };
  const a = await page.evaluate((f) => window.measure(f), cw);
  const b = await page.evaluate((f) => window.measure(f), ccw);
  const setOf = (m) => new Set(m.polygons[0].points.trim().split(/\s+/));
  const sa = setOf(a), sb = setOf(b);
  const same = sa.size === sb.size && [...sa].every((v) => sb.has(v));
  check('многоугольник против часовой = по часовой (тот же набор вершин)',
        same, `${[...sa].join(' ')} vs ${[...sb].join(' ')}`);
  check('контурная заливка светлее контура',
        a.polygons.length === 2
        && +a.polygons[0].fillOpacity >= 0.22 && +a.polygons[0].fillOpacity <= 0.28
        && a.polygons[1].fill === 'none' && a.polygons[1].stroke !== 'none',
        JSON.stringify(a.polygons));

  // выноска у СИММЕТРИЧНОЙ фигуры встаёт в одно и то же место при любом обходе
  const cwc = JSON.parse(JSON.stringify(cw));
  cwc.callouts = [{ text: '25', role: 'zone',
                    points: [[10, 10], [10, 60], [60, 60], [60, 10]] }];
  const ccwc = JSON.parse(JSON.stringify(ccw));
  ccwc.callouts = [{ text: '25', role: 'zone',
                     points: [[10, 10], [60, 10], [60, 60], [10, 60]] }];
  const ca = await page.evaluate((f) => window.measure(f), cwc);
  const cb = await page.evaluate((f) => window.measure(f), ccwc);
  const ta = ca.texts.find((t) => t.cls.indexOf('fig-callout') !== -1);
  const tb = cb.texts.find((t) => t.cls.indexOf('fig-callout') !== -1);
  check('выноска не зависит от направления обхода вершин',
        ta && tb && Math.abs(ta.x0 - tb.x0) < 0.6 && Math.abs(ta.y0 - tb.y0) < 0.6,
        JSON.stringify([ta, tb]));
}

/* --- 3. Рисователь честно рисует ЗАВЕДОМО неверную геометрию --- */
{
  const before = consoleErrors.length;
  // точка вне всяких кривых, «бабочка» вместо многоугольника, засечка выше оси
  const wrong = { kind: 'wrong', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
    lines: [lin('d', 'D', [0, 100], [100, 0])],
    areas: [poly('zone', [[10, 10], [60, 60], [10, 60], [60, 10]], true)],
    points: [pt(90, 90, 'мимо', 'd', true)],
    marks: [{ axis: 'y', at: 95, label: 'выше всех' }] };
  const m = await page.evaluate((f) => window.measure(f), wrong);
  check('неверная геометрия рисуется без ошибок',
        m !== null && consoleErrors.length === before,
        consoleErrors.slice(before).join('; '));
  // координаты не «поправлены»: кружок ровно там, куда его послали
  const X0 = 48, Y0 = 360 - 54, W = 520 - 48 - 18, H = 360 - 18 - 54;
  const wantX = X0 + (90 / 100) * W, wantY = Y0 - (90 / 100) * H;
  check('координаты точки не подтянуты к «правильным»',
        Math.abs(m.circles[0].cx - wantX) < 0.01
        && Math.abs(m.circles[0].cy - wantY) < 0.01,
        `${m.circles[0].cx},${m.circles[0].cy} вместо ${wantX},${wantY}`);
  check('самопересекающийся многоугольник нарисован как задан (4 вершины)',
        m.polygons[0].points.trim().split(/\s+/).length === 4,
        m.polygons[0].points);
  check('подпись точки показывает ИМЕННО присланные координаты',
        m.texts.some((t) => t.text.indexOf('(90; 90)') !== -1),
        m.texts.map((t) => t.text).join(' | '));
}

/* --- 4. Выноска, не помещающаяся внутрь, выносится наружу с хвостиком --- */
{
  const tiny = { kind: 'tiny', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
    areas: [poly('dwl', [[40, 40], [46, 40], [43, 46]], true)],
    callouts: [{ text: 'потери общества = 150', role: 'dwl',
                 points: [[40, 40], [46, 40], [43, 46]] }] };
  const m = await page.evaluate((f) => window.measure(f), tiny);
  const c = m.texts.find((t) => t.cls.indexOf('fig-callout') !== -1);
  check('длинная выноска в маленькой области ушла наружу',
        c && c.cls.indexOf('fig-callout-out') !== -1, c && c.cls);
  check('у вынесенной наружу выноски есть хвостик',
        m.segs.some((s) => s.cls.indexOf('fig-callout-tail') !== -1),
        m.segs.map((s) => s.cls).join('|'));

  const big = { kind: 'big', xmax: 100, ymax: 100, xlabel: 'Q', ylabel: 'P',
    areas: [poly('zone', [[5, 5], [95, 5], [95, 95], [5, 95]], true)],
    callouts: [{ text: '1200', role: 'zone',
                 points: [[5, 5], [95, 5], [95, 95], [5, 95]] }] };
  const mb = await page.evaluate((f) => window.measure(f), big);
  const cb2 = mb.texts.find((t) => t.cls.indexOf('fig-callout') !== -1);
  check('короткая выноска в большой области осталась внутри',
        cb2 && cb2.cls.indexOf('fig-callout-in') !== -1, cb2 && cb2.cls);
}

/* --- 5. Кегль и пропорции --- */
{
  const m = await page.evaluate((f) => window.measure(f), L[1].fig);
  const sizes = await page.evaluate(() => Array.prototype.map.call(
    document.querySelectorAll('#root svg text'),
    (t) => +window.getComputedStyle(t).fontSize.replace('px', '')));
  check('минимальный кегль подписи ≥ 11px',
        sizes.length > 0 && Math.min.apply(null, sizes) >= 11,
        'минимум ' + Math.min.apply(null, sizes));
  check('пропорции чертежа сохраняются',
        m.viewBox === '0 0 520 360' && m.par === 'xMidYMid meet',
        m.viewBox + ' / ' + m.par);
}

/* --- 6. Ломаная рисуется одним узлом, а не двумя отрезками --- */
{
  const m = await page.evaluate((f) => window.measure(f), L[5].fig);
  check('ломаная — один polyline с тремя вершинами',
        m.polylines.length === 1
        && m.polylines[0].points.trim().split(/\s+/).length === 3,
        JSON.stringify(m.polylines));
}

await browser.close();
console.log(`\n=== рисователь: ${pass} прошло, ${fail} провалено ===`);
process.exit(fail === 0 ? 0 : 1);
