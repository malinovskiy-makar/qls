// Кривые: отрисовка по формулам и перетаскивание мышью.
/* ---------------------------------------------------------------------
   БЛОК 4. КРИВЫЕ — отрисовка кривых по формулам.
   --------------------------------------------------------------------- */

// Палитра: цвета «обычным» кривым выдаются по очереди при добавлении.
// Читаем COL лениво (на момент вызова), т.к. COL наполняется в refreshColors().
function nextColor() {
  const pal = [COL.D, COL.S, COL.tax, COL.reg, COL.MR, COL.MC];
  return pal[STATE.curves.length % pal.length];
}

// Набор точек кривой: 400 отрезков по Q. NaN -> разрыв (null).
// Точки с P<0 или P>Pmax не выбрасываем — их аккуратно срежет clip-path
// по первой четверти (см. addDefs), линия обрывается ровно на оси.
function curvePoints(curve) {
  const N = 400;
  const out = [];
  // Считаем от видимого края, но не левее нуля: P = f(Q) для Q < 0 в экономике
  // смысла не имеет, а после панорамирования вправо незачем считать то,
  // что всё равно останется за кадром.
  const lo = quadLo(sx.domain()[0]), hi = sx.domain()[1];
  if (!(hi > lo)) return out;
  for (let i = 0; i <= N; i++) {
    const q = lo + (hi - lo) * i / N;
    const p = evalCurve(curve, q);
    out.push(isNaN(p) ? null : [q, p]);
  }
  return out;
}

/* ── Подписи кривых (Фаза 3) ─────────────────────────────────────────────
   Раньше подпись жёстко висела на одной пробной точке (Q = 0.96·Qmax) и, если
   кривая там уходила за верх окна, не рисовалась ВООБЩЕ. Отсюда и «мигание»
   подписей при смене масштаба: пробная точка переезжала, а вместе с ней
   пропадала и подпись. Теперь ищем ближайшее к правому краю место, где кривая
   реально видна, и вешаем подпись туда. Совсем скрываем только если кривой
   нет в кадре — подписывать тогда нечего.

   Якорь: идём от правого края влево, берём первую точку внутри окна. */
/* Пометить нарисованный путь формулой кривой (А49).

   Выгрузка в LaTeX по этой пометке рисует кривую ФОРМУЛОЙ (\addplot{...}), а
   не таблицей из шестидесяти точек. Раньше формулой уходили только кривые из
   списка (D и S), а всё, что рисует сама сцена, — сдвинутая S + t, MR,
   кривые издержек, — оцифровывалось точками, хотя выражение у них есть.

   Это общий способ: любая сцена может подключиться одной строкой, ничего не
   зная про экспорт. Кривые, у которых аналитического выражения нет вовсе
   (изокванта, сумма КПВ по Минковскому, горизонтальная сумма заводов),
   по-прежнему честно уходят точками. */
function markExpr(sel, curveOrExpr, varName) {
  const expr = (curveOrExpr && typeof curveOrExpr === 'object')
    ? (curveOrExpr.texExpr || curveOrExpr.expr)
    : curveOrExpr;
  if (expr) {
    sel.attr('data-expr', String(expr));
    if (varName) sel.attr('data-expr-var', varName);
  }
  return sel;
}

function curveAnchor(f, fromFrac, toFrac) {
  const from = (fromFrac == null) ? 0.97 : fromFrac;
  const to   = (toFrac   == null) ? 0.04 : toFrac;
  const N = 72;
  for (let i = 0; i <= N; i++) {
    const q = sx.domain()[1] * (from + (to - from) * i / N);
    const v = f(q);
    if (!isNaN(v) && v >= 0 && v <= sy.domain()[1]) return { q, v };
  }
  return null;
}

/* Подпись у якоря, зажатая внутрь поля графика: у правого края текст
   разворачивается влево, у верхнего — переезжает под кривую. Так подпись
   переносится, а не исчезает. */
// Кегль подписей кривых. Один на весь график: настройка у каждой строки списка
// дала бы десяток одинаковых полей ради того, что меняют раз на задачу.
/* П50. Размер подписей задаётся тремя буквами А: маленькая 12, средняя 16,
   большая 20. Меняется ВСЁ внутри графика — подписи кривых и точек,
   координаты, названия осей, легенда, врезки, подписи областей, — кроме
   отметок координат на осях: их размер оставлен как есть.

   Полсотни мест рисуют текст с размером, вбитым числом прямо в коде. Вместо
   того чтобы править каждое (и промахнуться на следующем), после отрисовки
   идёт один проход по всем <text> внутри холста и множит их размер на общий
   коэффициент. Новая подпись получает его бесплатно, ничего не зная о нём.
   Отметки осей помечены классом axis-num и в проход не попадают. */
const LABEL_BASE = 12;                       // «маленькая А» — базовый размер
function curveLabelSize() { return LABEL_BASE; }
function labelScale() {
  const v = +STATE.labelSize;
  return (isFinite(v) && v >= 8 && v <= 40) ? v / LABEL_BASE : 1;
}

function applyLabelSize() {
  const k = labelScale();
  if (Math.abs(k - 1) < 1e-6) return;
  const node = svg.node();
  if (!node) return;
  node.querySelectorAll('text').forEach(t => {
    if (t.classList.contains('axis-num')) return;      // отметки координат не трогаем
    const cur = parseFloat(t.getAttribute('font-size'));
    const base = isFinite(cur) ? cur : parseFloat(getComputedStyle(t).fontSize);
    if (!isFinite(base) || base <= 0) return;
    t.setAttribute('font-size', Math.round(base * k * 10) / 10);
  });
}

/* Сглаживание подписей (П25).

   Якорь ищется перебором 72 проб в ДОЛЯХ от текущих границ. При изменении
   масштаба условие «точка внутри окна» срабатывает на соседнем узле сетки, и
   подпись прыгает сразу на процент с лишним ширины. Поэтому помним, где
   подпись стояла в прошлый раз, и подтягиваем её к новому месту постепенно:
   на глаз она едет за кривой, а не перескакивает.

   Второй источник дёрганья — мгновенный переворот выравнивания у правого края.
   Ему добавлен запас: переворот происходит только когда текст залезает за край
   на 12 пикселей, а возвращается обратно, лишь когда до края остаётся столько
   же с другой стороны. На самой границе подпись больше не мигает. */
const _labelPos = new Map();
const LABEL_EASE = 0.35;       // доля пути к новому месту за одну перерисовку
const LABEL_JUMP = 60;         // дальше этого едем сразу: масштаб сменился резко
const FLIP_HYST = 12;          // запас на переворот выравнивания, px

function smoothLabel(key, px, py, toLeft) {
  if (!key) return { px, py, toLeft };
  const prev = _labelPos.get(key);
  if (!prev) { _labelPos.set(key, { px, py, toLeft }); return { px, py, toLeft }; }
  const far = Math.hypot(px - prev.px, py - prev.py) > LABEL_JUMP;
  const nx = far ? px : prev.px + (px - prev.px) * LABEL_EASE;
  const ny = far ? py : prev.py + (py - prev.py) * LABEL_EASE;
  // Гистерезис переворота: меняем сторону, только если новое решение уверенное.
  const flip = (toLeft !== prev.toLeft) ? toLeft : prev.toLeft;
  const out = { px: nx, py: ny, toLeft: flip };
  _labelPos.set(key, out);
  // Пока подпись едет, просим следующий кадр — иначе она застынет на полпути.
  if (!far && Math.hypot(px - nx, py - ny) > 0.5) requestLabelFrame();
  return out;
}
let _labelFrame = null;
function requestLabelFrame() {
  if (_labelFrame != null) return;
  _labelFrame = requestAnimationFrame(() => { _labelFrame = null; redrawAll(); });
}
// Сцена сменилась — прошлые места подписей к ней отношения не имеют.
function resetLabelPositions() { _labelPos.clear(); }

function labelCurve(g, f, txt, color, opts) {
  const o = opts || {};
  const a = curveAnchor(f, o.from, o.to);
  if (!a) return null;
  const m = CONFIG.margin;
  const right = W - m.right;
  const wide = txt.length * 6.3 + 8;              // грубая ширина текста, px
  const rawPx = sx(a.q), rawPy = sy(a.v);
  // Переворот с запасом: у самой границы решение не меняется туда-сюда.
  const over = rawPx + wide - right;
  const wantLeft = over > FLIP_HYST ? true : (over < -FLIP_HYST ? false : null);
  const key = o.key || (o.curve && o.curve.id) || txt;
  const prevLeft = (_labelPos.get(key) || {}).toLeft;
  const sm = smoothLabel(key, rawPx, rawPy,
                         wantLeft === null ? (prevLeft === undefined ? over > 0 : prevLeft) : wantLeft);
  const px = sm.px, py = sm.py;
  const toLeft = sm.toLeft;
  let y = py + (o.below ? 14 : -7);
  if (y < m.top + 12) y = py + 14;                // упёрлись в верх — под кривую
  if (y > H - m.bottom - 4) y = py - 7;           // упёрлись в низ — над кривой
  const tx = toLeft ? px - 6 : px + 6;
  void rawPy;                                     // сырое место нужно было только для сглаживания
  const t = g.append('text')
    .attr('x', tx).attr('y', y)
    .attr('text-anchor', toLeft ? 'end' : 'start')
    .attr('font-size', o.size || curveLabelSize()).attr('font-weight', 600).attr('fill', color)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6)
    .text(txt);
  // Название кривой правится двойным щелчком прямо на графике.
  if (o.curve) {
    makeRenamable(t, txt, tx, y, (v) => {
      if (v) o.curve.label = v; else delete o.curve.label;
      if (!o.curve.label) o.curve.name = o.curve.expr;
      renderCurveList();
    });
  }
  return a;
}

// Рисуем все видимые кривые внутри «окна» первой четверти.
function drawCurves() {
  const g = svg.append('g').attr('class', 'curves').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line()
    .defined(d => d !== null)               // разрыв там, где формула не считается
    .x(d => sx(d[0])).y(d => sy(d[1]));
  STATE.curves.forEach(curve => {
    if (!curve.visible) return;
    const pts = curvePoints(curve);
    g.append('path').datum(pts)
      .attr('fill', 'none').attr('stroke', curve.color).attr('stroke-width', 2.5)
      .attr('data-curve', curve.id)     // экспорт узнаёт кривую и пишет её формулой
      .attr('d', line);
    // Прямые можно перетаскивать: кладём поверх широкую невидимую «дорожку»
    // для удобного захвата мышью и вешаем на неё перетаскивание.
    if (curve.linear) {
      const hit = g.append('path').datum(pts)
        .attr('fill', 'none').attr('stroke', 'transparent').attr('stroke-width', 16)
        .attr('data-skip-export', '1')    // это дорожка для мыши, а не линия графика
        .attr('d', line).style('cursor', 'ns-resize');
      attachDrag(hit, curve);
    }
  });
  // Подписи поверх линий (Фаза 1 и 3): имя кривой видно прямо на графике.
  // Отдельным проходом, чтобы текст не оказался под соседней кривой.
  STATE.curves.forEach((curve, i) => {
    if (!curve.visible) return;
    let nm = curveShortName(curve);
    if (nm.length > 14) nm = nm.slice(0, 13) + '…';
    // Соседние кривые в одной точке — разводим по вертикали, иначе подписи слипнутся.
    labelCurve(g, q => evalCurve(curve, q), nm, curve.color, { below: i % 2 === 1, curve });
  });
}

/* ---------------------------------------------------------------------
   БЛОК 7. ИНТЕРАКТИВ — перетаскивание кривых мышью.
   Линейную кривую тянем по вертикали: меняется свободный член b
   (наклон a сохраняется). Нелинейные пока не перетаскиваются (TODO).
   --------------------------------------------------------------------- */
// Сдвиг линейной кривой по вертикали: меняем свободный член b (наклон a сохраняется),
// обновляем подпись и перерисовываем. ЕДИНАЯ точка для перетаскивания мышью И для
// ползунка-слайдера в пульте — никакой параллельной математики.
function setCurveFreeTerm(curve, b) {
  if (!curve || !curve.linear) return;
  curve.linear.b = b;
  if (curve.srcForm === 'QP') {
    // Кривая введена как Q(P) — показываем её в ТОЙ ЖЕ форме (Фаза 1б).
    // P = a·Q + b  ⟺  Q = (−b/a) + (1/a)·P; канон curve.linear уже обновлён выше.
    const a = curve.linear.a;
    curve.srcLinear = { c: -b / a, d: 1 / a };
    curve.srcExpr = curve.expr = curve.name = fmtLinear(1 / a, -b / a, 'P');
  } else {
    curve.expr = curve.name = fmtLinear(curve.linear.a, curve.linear.b);
  }
  if (STATE.mode === 'labor') _wantRangeAnim = true;   // труд авто-масштабируется → плавно (Фаза 4)
  redrawAll();        // перерисуем кривую и всё зависимое (равновесие/области)
  renderCurveList();  // обновим формулу в списке кривых (и слайдеры пульта — в конце renderCurveList)
}

function attachDrag(sel, curve) {
  sel.call(d3.drag()
    .container(() => svg.node())   // координаты события — в пикселях SVG
    .on('drag', (event) => {
      const [q, p] = toData(event.x, event.y);
      // Прямая проходит через курсор с прежним наклоном -> пересчитываем b тем же путём.
      setCurveFreeTerm(curve, p - curve.linear.a * q);
    }));
}
// TODO (будущие шаги): перетаскивание нелинейных кривых (парабол и т.п.).

