// Плоскость: шкалы, оси, сетка, перевод данные-пиксели.
/* ---------------------------------------------------------------------
   БЛОК 3. КООРДИНАТЫ И ОСИ
   Рисуем только первую четверть: Q вправо, P вверх. Начало (0,0) —
   в левом нижнем углу. Оси, сетку и подписи рисуем сами через D3.
   --------------------------------------------------------------------- */
const svg = d3.select('#chart');   // корневой SVG-элемент
let W = 0, H = 0;                  // размеры области графика в пикселях
let sx, sy;                       // D3-шкалы: данные -> пиксели

// Размер SVG берём из контейнера (обновляется при изменении окна).
function computeSize() {
  const wrap = document.getElementById('graph-wrap');
  W = wrap.clientWidth;
  H = wrap.clientHeight;
  svg.attr('width', W).attr('height', H);
  fitMargins();
}

/* Поля холста ровно под то, что в них печатается (Фаза 1).
   Считаем в два прохода: сначала пробные шкалы со старыми полями — по ним
   узнаём, какие деления будут подписаны; потом по самой широкой подписи
   ставим левое поле и пересобираем шкалы. Проход дешёвый (две линейные
   шкалы), зато рамка вокруг плоскости исчезает: «100» и «12 500» получают
   разное место, а не одинаковые 76 px на всякий случай. */
function fitMargins() {
  const m = CONFIG.margin;
  makeScales();
  let wide = 1;
  try {
    // Деления зависят только от диапазона, поэтому в «Математике» берём её
    // окно: там по вертикали свои границы, а не первая четверть.
    const dom = (STATE.mode === 'math')
      ? [STATE.mathYmin, STATE.mathYmax]
      : [CONFIG.Pmin, CONFIG.Pmax];
    const probe = d3.scaleLinear().domain(dom).range([0, 1]);
    axisTicks(probe, 8, STATE.yStep).forEach(t => {
      const s = fmt(t);
      if (s.length > wide) wide = s.length;
    });
  } catch (e) { /* сцена ещё не готова — останемся со стартовыми полями */ }
  // 6.2 px на знак при кегле 10 + 8 px отступа от оси + 6 px запаса у края.
  m.left = Math.max(30, Math.min(88, Math.round(wide * 6.2) + 14));
  m.right = 32;                        // буква оси X справа от стрелки
  m.bottom = 30;                       // строка чисел под осью X
  // Своё название графика печатается над плоскостью — ему нужна полоса.
  m.top = (STATE.graphTitle || '').trim() ? 44 : 26;
  makeScales();
}

// Линейные шкалы по двум осям. Границы берём из CONFIG целиком: нижние
// (Qmin/Pmin) двигает панорамирование и поля «от» в меню плоскости.
function makeScales() {
  const m = CONFIG.margin;
  sx = d3.scaleLinear().domain([CONFIG.Qmin, CONFIG.Qmax]).range([m.left, W - m.right]);
  sy = d3.scaleLinear().domain([CONFIG.Pmin, CONFIG.Pmax]).range([H - m.bottom, m.top]);
}

/* Нижняя граница отрисовки по оси. В режиме «только первая четверть» всё, что
   левее и ниже нуля, не рисуется совсем; выключили режим — считаем и рисуем от
   настоящей границы окна. Одна функция на весь движок, чтобы обрезка кривых,
   clip-path и расчёты не разошлись между собой. */
function quadLo(v) { return STATE.firstQuad ? Math.max(0, v) : v; }

// Перевод координат туда-обратно (пригодится для перетаскивания мышью).
function toPx(q, p) { return [sx(q), sy(p)]; }
function toData(px, py) { return [sx.invert(px), sy.invert(py)]; }

// Формат числа для подписей делений (без длинных хвостов после точки).
function fmt(v) {
  if (Math.abs(v) >= 1000) return d3.format('.2~s')(v);
  return (Math.round(v * 100) / 100).toString();
}

/* Шаг делений из «красивой» лесенки 1–2–5. Считается только от размаха окна,
   поэтому при плавном зуме он держится постоянным на целом диапазоне масштабов,
   а деления просто съезжают. Раньше шаг подбирал d3 по числу делений, и на
   каждом повороте колеса набор чисел мог перевыбраться заново — отсюда и
   дёрганье подписей. */
function niceTickStep(span, target) {
  if (!(span > 0) || !isFinite(span)) return 1;
  const raw = span / Math.max(1, target || 10);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  return (n <= 1 ? 1 : (n <= 2 ? 2 : (n <= 5 ? 5 : 10))) * mag;
}

/* Деления оси: свой шаг, если задан в меню плоскости, иначе «красивая» лесенка.
   Свой шаг режем по числу линий — 400 подписей на экране никому не помогут.
   Значения считаем как first + i·step (а не накоплением +=): иначе на мелком
   шаге копится погрешность и подписи расползаются. */
function axisTicks(scale, count, step) {
  const [lo, hi] = scale.domain();
  const s = (step > 0 && (hi - lo) / step <= 400) ? step : niceTickStep(hi - lo, count);
  if (!(s > 0) || !isFinite(s)) return [];
  const out = [];
  const first = Math.ceil(lo / s - 1e-9) * s;
  for (let i = 0; i < 500; i++) {
    const v = first + i * s;
    if (v > hi + 1e-9) break;
    out.push(Math.abs(v) < s * 1e-6 ? 0 : v);
  }
  return out;
}
function xTicks() { return axisTicks(sx, 10, STATE.xStep); }
function yTicks() { return axisTicks(sy, 8, STATE.yStep); }

// Стрелки на концах осей — один раз как <marker> в <defs>.
function addDefs() {
  const defs = svg.append('defs');
  defs.append('marker')
    .attr('id', 'arrow').attr('viewBox', '0 0 10 10')
    .attr('refX', 8).attr('refY', 5)
    .attr('markerWidth', 7).attr('markerHeight', 7)
    .attr('orient', 'auto-start-reverse')
    .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', COL.ink);

  // Прямоугольник-«окно»: видимая часть первой четверти. Всё, что нарисовано
  // с этим clip-path, обрезается по осям и по краям окна — кривые и заливки
  // не вылезают в отрицательную зону и не выходят за границы вида.
  const x0 = sx(quadLo(CONFIG.Qmin)), x1 = sx(CONFIG.Qmax);
  const y1 = sy(CONFIG.Pmax), y0 = sy(quadLo(CONFIG.Pmin));
  defs.append('clipPath').attr('id', 'plot-clip').append('rect')
    .attr('x', x0).attr('y', y1)
    .attr('width', Math.max(0, x1 - x0))
    .attr('height', Math.max(0, y0 - y1));
}

// Лёгкая сетка по делениям шкал. Рисуется под осями, поэтому первой.
// Крупные линии совпадают с подписанными делениями осей (drawAxes берёт те же
// xTicks()/yTicks()) — каждая линия сетки «читается» по числу на оси.
// Мелкая сетка добавляет 4 бледные линии между крупными, без подписей.
function drawGrid(mx, my, parent) {
  if (!STATE.showGrid) return;
  // Шкалы приходят аргументом: у «Математики» и у сцен с двумя панелями окно
  // своё, и сетка, посчитанная от CONFIG, там просто не появлялась. Без
  // аргументов работает как раньше — по главным шкалам сцены.
  mx = mx || sx; my = my || sy;
  const g = (parent || svg).append('g').attr('class', 'grid');
  const [xLeft, xRight] = mx.range();
  const [yBot, yTop] = my.range();
  const [xLo, xHi] = mx.domain();
  const [yLo, yHi] = my.domain();
  const tx = axisTicks(mx, 10, STATE.xStep), ty = axisTicks(my, 8, STATE.yStep);
  const inX = (v) => v >= xLo - 1e-9 && v <= xHi + 1e-9;
  const inY = (v) => v >= yLo - 1e-9 && v <= yHi + 1e-9;
  // Мелкие линии — сначала (крупные лягут поверх и останутся заметнее).
  if (STATE.gridDense) {
    const SUB = 5;                                    // делений между соседними подписями
    const minor = (ticks, lo, hi, ok, draw) => {
      if (ticks.length < 2) return;
      const step = (ticks[1] - ticks[0]) / SUB;
      if (!(step > 0)) return;
      const first = Math.ceil(lo / step - 1e-9) * step;
      for (let v = first; v <= hi + 1e-9; v += step) {
        if (!ok(v)) continue;
        if (ticks.some(t => Math.abs(t - v) < step * 1e-6)) continue;   // тут уже яркая линия
        draw(v);
      }
    };
    minor(tx, xLo, xHi, inX, (v) => g.append('line')
      .attr('x1', mx(v)).attr('y1', yBot).attr('x2', mx(v)).attr('y2', yTop)
      .attr('stroke', COL.grid).attr('stroke-width', 1).attr('opacity', 0.45));
    minor(ty, yLo, yHi, inY, (v) => g.append('line')
      .attr('x1', xLeft).attr('y1', my(v)).attr('x2', xRight).attr('y2', my(v))
      .attr('stroke', COL.grid).attr('stroke-width', 1).attr('opacity', 0.45));
  }
  tx.forEach(t => {                        // вертикальные линии (по оси Q)
    if (!inX(t) || Math.abs(t) < 1e-12) return;
    g.append('line').attr('x1', mx(t)).attr('y1', yBot).attr('x2', mx(t)).attr('y2', yTop)
      .attr('stroke', COL.grid).attr('stroke-width', 1);
  });
  ty.forEach(t => {                        // горизонтальные линии (по оси P)
    if (!inY(t) || Math.abs(t) < 1e-12) return;
    g.append('line').attr('x1', xLeft).attr('y1', my(t)).attr('x2', xRight).attr('y2', my(t))
      .attr('stroke', COL.grid).attr('stroke-width', 1);
  });
}

/* Дополнительное деление на оси (Фаза 8). Важная координата не всегда попадает
   на «красивый» шаг, а подпись вида «Xмакс=100» прямо на поле только мешает и
   налезает на соседнее число. Ставим на самой оси ещё одно деление с числом.
   Если такое число на оси уже есть, ничего не рисуем. */
function extraTickX(g, v, color) {
  if (!isFinite(v)) return;
  const [lo, hi] = sx.domain();
  if (v < lo || v > hi) return;
  const span = Math.abs(hi - lo);
  if (xTicks().some(t => Math.abs(t - v) < span * 0.025)) return;
  const oy = sy(0);
  g.append('line').attr('x1', sx(v)).attr('y1', oy - 4).attr('x2', sx(v)).attr('y2', oy + 4)
    .attr('stroke', color || COL.ink).attr('stroke-width', 1.4);
  haloText(g, sx(v), oy + 8, fmt(v), 'middle', 'hanging');
}
function extraTickY(g, v, color) {
  if (!isFinite(v)) return;
  const [lo, hi] = sy.domain();
  if (v < lo || v > hi) return;
  const span = Math.abs(hi - lo);
  if (yTicks().some(t => Math.abs(t - v) < span * 0.025)) return;
  const ox = sx(0);
  g.append('line').attr('x1', ox - 4).attr('y1', sy(v)).attr('x2', ox + 4).attr('y2', sy(v))
    .attr('stroke', color || COL.ink).attr('stroke-width', 1.4);
  haloText(g, ox - 8, sy(v), fmt(v), 'end', 'middle');
}

// Оси со стрелками, делениями, числами и подписями.
// Подписи параметризованы: по умолчанию Q/P (рынок, издержки), для КПВ — X/Y.
// Ось нарисована ровно там, где ноль. Уехал ноль за край при панорамировании —
// ось уезжает вместе с ним и на экране её просто нет, как в Desmos. Раньше ось
// прижималась к краю окна, и числа копились у границы, притворяясь осью.
function drawAxes(xLabel, yLabel) {
  if (xLabel == null) xLabel = 'Q'; if (yLabel == null) yLabel = 'P';
  // Своё название оси перекрывает сценовое. Пустую строку '' сцена присылает
  // намеренно («метку рисую сама») — её не трогаем, иначе получим две подписи.
  // Заодно запоминаем сценовые названия для placeholder'ов в меню плоскости.
  if (xLabel) { STATE.axisXDefault = xLabel; if (STATE.axisXName) xLabel = STATE.axisXName; }
  if (yLabel) { STATE.axisYDefault = yLabel; if (STATE.axisYName) yLabel = STATE.axisYName; }
  const g = svg.append('g').attr('class', 'axes');
  const m = CONFIG.margin;
  const xLeft = m.left, xRight = W - m.right, yBot = H - m.bottom, yTop = m.top;
  const ox = sx(0), oy = sy(0);   // оси стоят там, где ноль, и ни к чему не липнут
  const AX = COL.ink, LBL = COL.inkSoft;
  const atZeroX = ox >= xLeft - 1 && ox <= xRight + 1;   // ось Y попадает в кадр
  const atZeroY = oy >= yTop - 1 && oy <= yBot + 1;      // ось X попадает в кадр

  // Ось X (вправо) и ось Y (вверх). Стрелка на конце, смотрящем в сторону роста.
  if (atZeroY) g.append('line').attr('x1', xLeft).attr('y1', oy).attr('x2', xRight).attr('y2', oy)
    .attr('stroke', AX).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
  if (atZeroX) g.append('line').attr('x1', ox).attr('y1', yBot).attr('x2', ox).attr('y2', yTop)
    .attr('stroke', AX).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');

  // Деления и числа на оси X. Ближе 14 px к концу оси не печатаем — иначе
  // налезают на стрелку и на букву оси.
  if (atZeroY) xTicks().forEach(t => {
    if (t < CONFIG.Qmin - 1e-9 || t > CONFIG.Qmax + 1e-9) return;
    if (atZeroX && Math.abs(t) < 1e-12) return;      // ноль подписываем один раз
    if (sx(t) > xRight - 14 || sx(t) < xLeft + 2) return;
    g.append('line').attr('x1', sx(t)).attr('y1', oy).attr('x2', sx(t)).attr('y2', oy + 5)
      .attr('stroke', AX).attr('stroke-width', 1);
    g.append('text').attr('x', sx(t)).attr('y', oy + 8)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'hanging')
      .attr('font-size', 10).attr('fill', LBL).text(fmt(t));
  });
  // Деления и числа на оси Y.
  if (atZeroX) yTicks().forEach(t => {
    if (t < CONFIG.Pmin - 1e-9 || t > CONFIG.Pmax + 1e-9) return;
    if (atZeroY && Math.abs(t) < 1e-12) return;
    if (sy(t) < yTop + 14 || sy(t) > yBot - 2) return;
    g.append('line').attr('x1', ox).attr('y1', sy(t)).attr('x2', ox - 5).attr('y2', sy(t))
      .attr('stroke', AX).attr('stroke-width', 1);
    g.append('text').attr('x', ox - 8).attr('y', sy(t))
      .attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
      .attr('font-size', 10).attr('fill', LBL).text(fmt(t));
  });
  // Единственный «0» в начале координат (только если начало видно).
  if (atZeroX && atZeroY) {
    g.append('text').attr('x', ox - 8).attr('y', oy + 8)
      .attr('text-anchor', 'end').attr('dominant-baseline', 'hanging')
      .attr('font-size', 10).attr('fill', LBL).text('0');
  }

  // Подписи осей: X-метка (справа от стрелки), Y-метка (над стрелкой слева).
  // Пустая строка '' — сигнал «без метки» (напр. неравенство и издержки добавляют свою).
  if (xLabel && atZeroY) g.append('text').attr('x', xRight + 6).attr('y', oy + 4)
    .attr('text-anchor', 'start').attr('dominant-baseline', 'middle')
    .attr('font-size', 13).attr('font-weight', 600)
    .attr('fill', COL.ink).text(xLabel);
  if (yLabel && atZeroX) g.append('text').attr('x', ox - 4).attr('y', yTop - 12)
    .attr('text-anchor', 'end').attr('font-size', 13).attr('font-weight', 600)
    .attr('fill', COL.ink).text(yLabel);
}

