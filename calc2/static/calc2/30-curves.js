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
function curveLabelSize() {
  const v = +STATE.labelSize;
  return (isFinite(v) && v >= 8 && v <= 22) ? v : 11;
}

function labelCurve(g, f, txt, color, opts) {
  const o = opts || {};
  const a = curveAnchor(f, o.from, o.to);
  if (!a) return null;
  const px = sx(a.q), py = sy(a.v);
  const m = CONFIG.margin;
  const right = W - m.right;
  const wide = txt.length * 6.3 + 8;              // грубая ширина текста, px
  const toLeft = (px + wide > right);
  let y = py + (o.below ? 14 : -7);
  if (y < m.top + 12) y = py + 14;                // упёрлись в верх — под кривую
  if (y > H - m.bottom - 4) y = py - 7;           // упёрлись в низ — над кривой
  const tx = toLeft ? px - 6 : px + 6;
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

