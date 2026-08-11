// Математика как раздел: касательная, экстремумы, деформации, min и max.
/* =====================================================================
   БЛОК 13. МАТЕМАТИКА (Фаза 7) — общий инструментарий, не привязанный ни к
   одной экономической модели. Шесть сюжетов по учебникам Сафронова и Бахарева:
     'tangent'    — функция, касательная, производная снизу (7а);
     'optimum'    — максимумы, минимумы, выпуклость, перегибы (7б);
     'transform'  — деформации графика одним параметром a (7в);
     'minmax'     — Z = min(f, g) или max(f, g) (7д);
     'constraint' — максимум F(a, b) при ограничении (7е).

   Отличие от всех прочих режимов: здесь нужен ПОЛНЫЙ план, а не первая
   четверть (иначе не показать ни f(−x), ни f(|x|), ни обычную параболу).
   Поэтому у режима свои шкалы и свои оси через начало координат; общий
   код осей первой четверти не тронут.

   Производные — центральной разностью, как MC и наклон КПВ в остальном
   движке. Отдельного аналитического дифференциатора нет и не нужно:
   численный путь работает для любой пользовательской функции, включая
   кусочные, а на школьных примерах сходится с известным ответом.
   ===================================================================== */

// Компиляция функции одной переменной. Имя переменной задаётся явно, синоним x
// добавляет compileVar — поэтому и «x^2», и «y^2/10» разбираются одинаково.
function compileMath(expr, name) { return compileVar(expr, [name]); }
function evalMathAt(compiled, name, v) { return compiled ? evalVar(compiled, v, [name]) : NaN; }

// Шаг численного дифференцирования: доля видимого диапазона, а не константа —
// иначе на окне 0..0.1 шаг «съест» всю картинку, а на 0..1000 потеряет точность.
function mathH() { return Math.max(1e-6, (STATE.mathXmax - STATE.mathXmin) * 1e-4); }
function dNum(f, x, h) {
  h = h || mathH();
  const a = f(x + h), b = f(x - h);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / (2 * h);
}
function d2Num(f, x, h) {
  h = h || Math.max(1e-4, mathH() * 20);   // вторая разность шумит сильнее — шаг крупнее
  const a = f(x + h), c = f(x), b = f(x - h);
  return (isNaN(a) || isNaN(b) || isNaN(c)) ? NaN : (a - 2 * c + b) / (h * h);
}

// Готовая f(x) текущего режима или null, если формула не разобралась.
function mathF() {
  const { compiled } = compileMath(STATE.mathFormula, 'x');
  if (!compiled) return null;
  return (x) => evalMathAt(compiled, 'x', x);
}

// Нули функции g на отрезке: сетка + бисекция на каждой смене знака.
// Тем же способом ищутся равновесие и корни во всём остальном движке.
function rootsOf(g, lo, hi, N) {
  N = N || 600;
  const out = [];
  const push = (r) => {
    if (r == null || isNaN(r)) return;
    if (!out.length || Math.abs(r - out[out.length - 1]) > (hi - lo) * 1e-3) out.push(r);
  };
  let px = lo, pg = g(lo);
  for (let i = 1; i <= N; i++) {
    const x = lo + (hi - lo) * i / N, cur = g(x);
    if (!isNaN(pg) && !isNaN(cur)) {
      // Узел РОВНО на нуле — частый случай на школьных примерах: у x² производная
      // обращается в нуль в x = 0, и это ровно узел сетки. Проверка «произведение
      // меньше нуля» такой корень пропускает, поэтому нули ловим отдельно.
      if (pg === 0) push(px);
      else if (cur === 0) push(x);
      else if (pg * cur < 0) push(bisect(g, px, x));
    }
    px = x; pg = cur;
  }
  if (pg === 0) push(hi);
  return out;
}

// Экстремумы и перегибы. Экстремум — нуль первой производной, тип определяет
// знак второй; перегиб — смена знака второй производной.
function mathAnalyse(f, lo, hi) {
  const ext = rootsOf((x) => dNum(f, x), lo, hi).map(x => {
    const s = d2Num(f, x);
    return { x, y: f(x), kind: (s > 0 ? 'min' : (s < 0 ? 'max' : 'flat')) };
  }).filter(p => !isNaN(p.y));
  const inf = rootsOf((x) => d2Num(f, x), lo, hi)
    .map(x => ({ x, y: f(x) })).filter(p => !isNaN(p.y));
  // Глобальные — с учётом концов отрезка: у школьных задач ответ часто на краю.
  let gMax = null, gMin = null;
  const consider = (x) => {
    const y = f(x); if (isNaN(y)) return;
    if (!gMax || y > gMax.y) gMax = { x, y };
    if (!gMin || y < gMin.y) gMin = { x, y };
  };
  ext.forEach(p => consider(p.x));
  consider(lo); consider(hi);
  return { ext, inf, gMax, gMin };
}

// Преобразование графика (7в). Возвращает новую функцию и человеческую подпись.
const MATH_TRANS = {
  up:     { tex: 'f(x) + a',  note: 'Плюс a поднимает график, минус опускает.' },
  left:   { tex: 'f(x + a)',  note: 'Внимание: при a > 0 график уезжает ВЛЕВО, а не вправо. Внутри скобок всё наоборот, и это самое частое место, где путаются.' },
  scaleY: { tex: 'a · f(x)',  note: 'Больше единицы растягивает вверх, меньше прижимает к оси x, отрицательное ещё и переворачивает.' },
  scaleX: { tex: 'f(a · x)',  note: 'И здесь наоборот: a > 1 СЖИМАЕТ график к оси y, а 0 < a < 1 растягивает.' },
  negY:   { tex: '−f(x)',     note: 'Отражение относительно оси x: что было сверху, окажется снизу.' },
  negX:   { tex: 'f(−x)',     note: 'Отражение относительно оси y: правая половина становится левой.' },
  absY:   { tex: '|f(x)|',    note: 'Всё, что ниже оси x, отражается наверх.' },
  absX:   { tex: 'f(|x|)',    note: 'Правая половина копируется налево, левая исходная пропадает.' },
};
function mathTransformed(f, kind, a) {
  switch (kind) {
    case 'up':     return (x) => f(x) + a;
    case 'left':   return (x) => f(x + a);
    case 'scaleY': return (x) => a * f(x);
    case 'scaleX': return (x) => f(a * x);
    case 'negY':   return (x) => -f(x);
    case 'negX':   return (x) => f(-x);
    case 'absY':   return (x) => Math.abs(f(x));
    case 'absX':   return (x) => f(Math.abs(x));
    default:       return f;
  }
}

/* ── Оси полного плана ──────────────────────────────────────────────────
   Отдельная функция: общая drawAxes умеет только первую четверть со
   стрелками из нуля, а здесь ось может пройти по середине холста. */
function mathScales(yTop, yBot, yLo, yHi) {
  const m = CONFIG.margin;
  return {
    mx: d3.scaleLinear().domain([STATE.mathXmin, STATE.mathXmax]).range([m.left, W - m.right]),
    my: d3.scaleLinear()
          .domain([yLo == null ? STATE.mathYmin : yLo, yHi == null ? STATE.mathYmax : yHi])
          .range([yBot == null ? H - m.bottom : yBot, yTop == null ? m.top : yTop]),
  };
}
function drawPlaneAxes(g, mx, my, xlab, ylab) {
  const [px0, px1] = mx.range(), [py0, py1] = my.range();
  const ox = mx(0), oy = my(0);       // ось стоит в нуле и уезжает вместе с ним
  const seeY = ox >= px0 - 1 && ox <= px1 + 1;
  const seeX = oy >= py1 - 1 && oy <= py0 + 1;
  // Стрелка всегда на конце, смотрящем в сторону роста: вправо по x, вверх по y.
  if (seeX) g.append('line').attr('x1', px0).attr('y1', oy).attr('x2', px1).attr('y2', oy)
    .attr('stroke', COL.ink).attr('stroke-width', 1.4).attr('marker-end', 'url(#arrow)');
  if (seeY) g.append('line').attr('x1', ox).attr('y1', py0).attr('x2', ox).attr('y2', py1)
    .attr('stroke', COL.ink).attr('stroke-width', 1.4).attr('marker-end', 'url(#arrow)');
  if (seeX) planeTicksX(g, mx, oy);
  if (seeY) planeTicksY(g, my, ox);
  if (xlab && seeX) g.append('text').attr('x', px1 - 2).attr('y', oy - 7).attr('text-anchor', 'end')
    .attr('font-size', 13).attr('font-weight', 600).attr('fill', COL.ink).text(xlab || 'x');
  if (ylab && seeY) g.append('text').attr('x', ox + 7).attr('y', py1 + 11)
    .attr('font-size', 13).attr('font-weight', 600).attr('fill', COL.ink).text(ylab || 'y');
}
function planeTicksX(g, mx, oy) {
  axisTicks(mx, 10, STATE.xStep).forEach(t => {
    if (Math.abs(t) < 1e-9) return;
    g.append('line').attr('x1', mx(t)).attr('y1', oy - 3).attr('x2', mx(t)).attr('y2', oy + 3)
      .attr('stroke', COL.ink).attr('stroke-width', 1);
    g.append('text').attr('x', mx(t)).attr('y', oy + 7)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'hanging')
      .attr('font-size', 10).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.2).text(fmt(t));
  });
}
function planeTicksY(g, my, ox) {
  axisTicks(my, 8, STATE.yStep).forEach(t => {
    if (Math.abs(t) < 1e-9) return;
    g.append('line').attr('x1', ox - 3).attr('y1', my(t)).attr('x2', ox + 3).attr('y2', my(t))
      .attr('stroke', COL.ink).attr('stroke-width', 1);
    g.append('text').attr('x', ox - 6).attr('y', my(t))
      .attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
      .attr('font-size', 10).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.2).text(fmt(t));
  });
}

// Кривая на полном плане: разрывы (NaN или далеко за окном) режут линию.
function mathLine(g, f, mx, my, color, width, dash) {
  const [lo, hi] = mx.domain(), [ylo, yhi] = my.domain();
  const pad = (yhi - ylo) * 2;
  const line = d3.line().defined(d => d !== null).x(d => mx(d[0])).y(d => my(d[1]));
  const pts = [];
  for (let i = 0; i <= 500; i++) {
    const x = lo + (hi - lo) * i / 500, v = f(x);
    pts.push((isNaN(v) || v < ylo - pad || v > yhi + pad) ? null : [x, v]);
  }
  const p = g.append('path').datum(pts).attr('fill', 'none')
    .attr('stroke', color).attr('stroke-width', width || 2.5).attr('d', line);
  if (dash) p.attr('stroke-dasharray', dash);
  return pts;
}

/* Точка с подписью. Если передан key, подпись можно переименовать прямо на
   графике: щелчок по тексту открывает поле ввода на его месте. «max 12.5» это
   то, что нашла машина, а назвать точку в своей задаче человек хочет по-своему
   («точка выхода», «оптимум фирмы»). Имена живут в STATE.pointNames и
   сбрасываются вместе с остальным оформлением при смене сцены. */
/* Куда поставить подпись, чтобы она не легла на ось и на соседнюю подпись.
   Занятые места помнит список, который обнуляется на каждой перерисовке. */
let _labelBoxes = [];
function resetLabelBoxes() { _labelBoxes = []; }
function dodgeLabel(x, y, axisY, w) {
  const H_ = 18;                       // под осью идут числа делений — им нужно место
  const hitsAxis = (v) => Math.abs(v - axisY) < H_;
  const hitsOther = (v) => _labelBoxes.some(b => Math.abs(b.y - v) < 13 && Math.abs(b.x - x) < (b.w + w) / 2);
  let v = y;
  // Уводим ВВЕРХ: под осью стоят числа делений, там подпись всё равно ляжет на них.
  if (hitsAxis(v)) v = axisY - H_ - 4;
  for (let k = 0; k < 6 && (hitsOther(v) || hitsAxis(v)); k++) v -= H_ + 2;
  _labelBoxes.push({ x, y: v, w });
  return v;
}

function mathDot(g, mx, my, x, y, color, label, dy, key) {
  g.append('circle').attr('cx', mx(x)).attr('cy', my(y)).attr('r', 4.5)
    .attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 1.6);
  if (!label) return;
  const shown = (key && STATE.pointNames[key] != null) ? STATE.pointNames[key] : label;
  if (!shown) return;
  const tx = mx(x) + 8;
  let ty = my(y) + (dy == null ? -8 : dy);
  // Подпись не должна лежать на оси: там уже стоят числа делений, и «перегиб:
  // x∗ = 0» садился прямо на деление «1». Уводим её от оси и от соседних
  // подписей, вниз по одной строке, пока место не освободится.
  ty = dodgeLabel(tx, ty, my(0), String(shown).length * 6 + 8);
  const t = g.append('text').attr('x', tx).attr('y', ty)
    .attr('font-size', 11).attr('font-weight', 600).attr('fill', color)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6);
  if (hasMathMarkup(shown)) mathTspans(t, shown); else t.text(shown);
  if (!key) return;
  makeRenamable(t, shown, tx, ty, (v) => {
    if (v) STATE.pointNames[key] = v; else delete STATE.pointNames[key];
  });
}

/* Любую подпись на графике переименовывают двойным щелчком прямо по ней.
   Одиночный щелчок оставлен свободным: им ставят точки и включают области, и
   переименование по нему срабатывало бы против воли. */
function makeRenamable(t, current, px, py, apply) {
  t.style('cursor', 'text').append('title').text('Двойной щелчок, чтобы переименовать');
  t.on('dblclick', (ev) => {
    ev.stopPropagation(); ev.preventDefault();
    editInlineLabel(current, px, py, apply);
  });
}

// Совместимость: прежнее имя оставлено, вызовы через него по-прежнему работают.
function editPointName(key, current, px, py) {
  editInlineLabel(current, px, py, (v) => {
    if (v) STATE.pointNames[key] = v; else delete STATE.pointNames[key];
  });
}

/* Поле ввода поверх графика на месте подписи. Enter и уход фокуса сохраняют,
   Esc отменяет, пустая строка возвращает машинное имя. */
function editInlineLabel(current, px, py, apply) {
  const wrap = document.getElementById('graph-wrap');
  if (!wrap) return;
  const old = document.getElementById('pt-rename');
  if (old) old.remove();
  const inp = document.createElement('input');
  inp.id = 'pt-rename'; inp.type = 'text'; inp.value = current;
  inp.style.cssText = 'position:absolute;z-index:40;font-size:11px;font-weight:600;padding:2px 5px;'
    + 'border:1px solid var(--accent);border-radius:var(--r-sm);background:var(--surface);'
    + 'color:var(--text);min-width:110px;'
    + 'left:' + Math.round(px) + 'px;top:' + Math.round(py - 16) + 'px;';
  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    if (save) apply(inp.value.trim());
    inp.remove();
    redrawAll();
  };
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  inp.addEventListener('blur', () => finish(true));
  wrap.appendChild(inp);
  inp.focus(); inp.select();
}

/* ── 7а. Производная и касательная ─────────────────────────────────────
   Две панели: сверху f(x) с точкой и касательной, снизу $f'(x)$ численно.
   Панели РАЗДЕЛЬНЫЕ. У каждой своё окно (и по x, и по y), свой зум и своя
   панорама, а рисование заперто в её прямоугольник через clip: раньше окно
   было общим, колесо над одной панелью тянуло обе, и при отдалении верхняя
   кривая заезжала на территорию нижней.
   Связь между панелями осталась ровно одна и осмысленная — точка x₀: её
   можно вести и сверху по кривой, и снизу по производной. */

// Геометрия панелей. Одна функция на всех, чтобы отрисовка и попадание
// курсора считали границы одинаково.
function tangentLayout() {
  const m = CONFIG.margin;
  const top = m.top, bottom = H - m.bottom;
  const gap = 34, hTop = (bottom - top - gap) * 0.58;
  const yMid = top + hTop;
  return { top, bottom, gap, yMid, botTop: yMid + gap };
}

// Какая панель под курсором: 'top', 'bot' или null (мимо обеих).
function tangentPanelAt(py) {
  const L = tangentLayout();
  if (py >= L.top - 6 && py <= L.yMid + 6) return 'top';
  if (py >= L.botTop - 6 && py <= L.bottom + 6) return 'bot';
  return null;
}

// Окно панели. Заводится при первом обращении — из общего окна раздела.
function tanWin(which) {
  const key = (which === 'bot') ? 'tanBot' : 'tanTop';
  if (!STATE[key]) {
    STATE[key] = { xmin: STATE.mathXmin, xmax: STATE.mathXmax,
                   ymin: STATE.mathYmin, ymax: STATE.mathYmax, auto: (which === 'bot') };
  }
  return STATE[key];
}

// Сбросить окна панелей (вход в сюжет, смена формулы, двойной щелчок).
function tanResetWindows() {
  STATE.tanTop = null; STATE.tanBot = null;
}

// Шкалы одной панели по её собственному окну.
function tanScales(which, pxTop, pxBot) {
  const m = CONFIG.margin, w = tanWin(which);
  return {
    mx: d3.scaleLinear().domain([w.xmin, w.xmax]).range([m.left, W - m.right]),
    my: d3.scaleLinear().domain([w.ymin, w.ymax]).range([pxBot, pxTop]),
  };
}

function drawMathTangent(f) {
  const m = CONFIG.margin;
  const L = tangentLayout();
  const dfun = (x) => dNum(f, x);
  const wTop = tanWin('top'), wBot = tanWin('bot');

  // Нижняя панель по умолчанию подбирает высоту под размах производной. Как
  // только пользователь сам покрутил колесо над ней, авто-подбор отступает.
  if (wBot.auto) {
    let dLo = 0, dHi = 0;
    for (let i = 0; i <= 200; i++) {
      const x = wBot.xmin + (wBot.xmax - wBot.xmin) * i / 200;
      const v = dfun(x);
      if (!isNaN(v) && isFinite(v)) { dLo = Math.min(dLo, v); dHi = Math.max(dHi, v); }
    }
    const pad = Math.max(1, (dHi - dLo) * 0.15);
    wBot.ymin = dLo - pad; wBot.ymax = dHi + pad;
  }

  const s1 = tanScales('top', L.top, L.yMid);
  const s2 = tanScales('bot', L.botTop, L.bottom);

  // Каждая панель рисуется в своём прямоугольнике и за него не выходит.
  const defs = svg.append('defs');
  const clipRect = (id, y0, y1) => {
    defs.append('clipPath').attr('id', id).append('rect')
      .attr('x', m.left - 1).attr('y', y0)
      .attr('width', Math.max(0, W - m.right - m.left + 2))
      .attr('height', Math.max(0, y1 - y0));
  };
  clipRect('tan-clip-top', L.top, L.yMid);
  clipRect('tan-clip-bot', L.botTop, L.bottom);

  const gTop = svg.append('g').attr('clip-path', 'url(#tan-clip-top)');
  const gBot = svg.append('g').attr('clip-path', 'url(#tan-clip-bot)');
  const gUi  = svg.append('g');    // подписи панелей: им обрезка ни к чему

  drawGrid(s1.mx, s1.my, gTop); drawGrid(s2.mx, s2.my, gBot);
  drawPlaneAxes(gTop, s1.mx, s1.my, 'x', 'y');
  drawPlaneAxes(gBot, s2.mx, s2.my, 'x', 'f′');
  // Тонкая черта между панелями: видно, что это две разные области.
  gUi.append('line').attr('x1', m.left).attr('y1', L.yMid + L.gap / 2)
    .attr('x2', W - m.right).attr('y2', L.yMid + L.gap / 2)
    .attr('stroke', COL.grid).attr('stroke-width', 1);
  // Подписи панелей крупнее и в цвет своей кривой: сразу видно, где сама
  // функция, а где производная.
  gUi.append('text').attr('x', m.left + 4).attr('y', L.top + 14)
    .attr('font-size', 13.5).attr('font-weight', 700).attr('fill', COL.tanF).text('f(x), сама функция');
  gUi.append('text').attr('x', m.left + 4).attr('y', L.botTop + 14)
    .attr('font-size', 13.5).attr('font-weight', 700).attr('fill', COL.tanD).text("$f'(x)$, производная");

  mathLine(gTop, f, s1.mx, s1.my, COL.tanF, 2.6);
  mathLine(gBot, dfun, s2.mx, s2.my, COL.tanD, 2.4);

  const x0 = STATE.mathX0, y0 = f(x0), k = dfun(x0);
  STATE.mathRes = { x0, y0, k, secant: null };
  if (isNaN(y0)) { updateMathPanel(); return; }

  // Касательная: y = y0 + k·(x − x0).
  if (!isNaN(k)) {
    mathLine(gTop, (x) => y0 + k * (x - x0), s1.mx, s1.my, COL.reg, 2, null);
    // Треугольник Δx / Δy — наглядное «отношение катетов = тангенс = производная».
    const dx = Math.min(STATE.mathDx, (wTop.xmax - wTop.xmin) * 0.25);
    const xa = x0, xb = x0 + dx, ya = y0, yb = y0 + k * dx;
    const tri = [[s1.mx(xa), s1.my(ya)], [s1.mx(xb), s1.my(ya)], [s1.mx(xb), s1.my(yb)]];
    gTop.append('path').attr('d', 'M' + tri.map(p => p.join(',')).join('L') + 'Z')
      .attr('fill', COL.reg).attr('opacity', 0.14)
      .attr('stroke', COL.reg).attr('stroke-width', 1.2).attr('stroke-dasharray', '4 3');
    gTop.append('text').attr('x', (s1.mx(xa) + s1.mx(xb)) / 2).attr('y', s1.my(ya) + 13)
      .attr('text-anchor', 'middle').attr('font-size', 10.5).attr('fill', COL.reg)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.4)
      .text('Δx = ' + fmt(dx));
    gTop.append('text').attr('x', s1.mx(xb) + 6).attr('y', (s1.my(ya) + s1.my(yb)) / 2)
      .attr('dominant-baseline', 'middle').attr('font-size', 10.5).attr('fill', COL.reg)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.4)
      .text('Δy = ' + fmt(k * dx));
  }

  // Секущая через две точки — видно, как она ложится на касательную при малом Δx.
  if (STATE.mathSecant) {
    const dx = STATE.mathDx, y1 = f(x0 + dx);
    if (!isNaN(y1)) {
      const ks = (y1 - y0) / dx;
      mathLine(gTop, (x) => y0 + ks * (x - x0), s1.mx, s1.my, COL.tax, 1.8, '6 4');
      mathDot(gTop, s1.mx, s1.my, x0 + dx, y1, COL.tax, null);
      STATE.mathRes.secant = ks;
    }
  }

  /* Точку ведут и сверху, и снизу: обе тянут одно и то же x₀. Рекурсии нет —
     перетаскивание меняет x₀ и просит перерисовку, а перерисовка обработчиков
     не дёргает. */
  const grabX = (sc, w) => (ev) => {
    setMathX0(Math.max(w.xmin, Math.min(w.xmax, sc.invert(ev.x))));
  };
  const dot = gTop.append('circle').attr('cx', s1.mx(x0)).attr('cy', s1.my(y0)).attr('r', 6)
    .attr('fill', COL.tanF).attr('stroke', COL.halo).attr('stroke-width', 2).style('cursor', 'ew-resize');
  dot.call(d3.drag().container(() => svg.node()).on('drag', grabX(s1.mx, wTop)));
  if (!isNaN(k)) {
    mathDot(gBot, s2.mx, s2.my, x0, k, COL.tanD, 'f′ = ' + fmt(k), null, 'deriv');
    const dot2 = gBot.append('circle').attr('cx', s2.mx(x0)).attr('cy', s2.my(k)).attr('r', 6)
      .attr('fill', 'transparent').attr('stroke', COL.tanD).attr('stroke-width', 2.2)
      .style('cursor', 'ew-resize');
    dot2.append('title').text('Ведите её, и касательная сверху перестроится');
    dot2.call(d3.drag().container(() => svg.node()).on('drag', grabX(s2.mx, wBot)));
  }
  updateMathPanel();
}

/* ── 7б. Оптимизация: экстремумы, выпуклость, перегибы ─────────────── */
function drawMathOptimum(f) {
  const { mx, my } = mathScales();
  const g = svg.append('g');
  drawGrid(mx, my, g);
  drawPlaneAxes(g, mx, my, 'x', 'y');
  const lo = STATE.mathXmin, hi = STATE.mathXmax;

  // Заливка по знаку второй производной: вверх выпуклая или вниз.
  if (STATE.mathConvex) {
    const N = 240, w = (mx.range()[1] - mx.range()[0]) / N;
    for (let i = 0; i < N; i++) {
      const x = lo + (hi - lo) * (i + 0.5) / N, s = d2Num(f, x);
      if (isNaN(s) || Math.abs(s) < 1e-9) continue;
      g.append('rect').attr('x', mx(lo + (hi - lo) * i / N)).attr('y', my.range()[1])
        .attr('width', w + 0.6).attr('height', my.range()[0] - my.range()[1])
        .attr('fill', s > 0 ? COL.D : COL.S).attr('opacity', 0.055);
    }
  }
  mathLine(g, f, mx, my, COL.D, 2.8);

  const a = mathAnalyse(f, lo, hi);
  STATE.mathRes = a;
  /* Подпись «максимум 2» не говорила, что это: координата точки или значение
     функции. Пишем обе величины и называем их: x* — где, y* — сколько. */
  const ptLabel = (kind, p) => kind + ': $(x^*; y^*) = (' + fmt(p.x) + '; ' + fmt(p.y) + ')$';
  a.ext.forEach((p, i) => {
    if (p.y < my.domain()[0] || p.y > my.domain()[1]) return;
    mathDot(g, mx, my, p.x, p.y, p.kind === 'max' ? COL.S : COL.MC,
            ptLabel(p.kind === 'max' ? 'max' : (p.kind === 'min' ? 'min' : 'плато'), p),
            null, 'ext' + i);
  });
  if (STATE.mathInflect) a.inf.forEach((p, i) => {
    if (p.y < my.domain()[0] || p.y > my.domain()[1]) return;
    mathDot(g, mx, my, p.x, p.y, COL.MR, ptLabel('перегиб', p), 14, 'inf' + i);
  });
  updateMathPanel();
}

/* ── 7в. Деформации графика ────────────────────────────────────────── */
function drawMathTransform(f) {
  const { mx, my } = mathScales();
  const g = svg.append('g');
  drawGrid(mx, my, g);
  drawPlaneAxes(g, mx, my, 'x', 'y');
  const t = mathTransformed(f, STATE.mathTrans, paramValue('a', 1));
  mathLine(g, f, mx, my, COL.ghost, 2.2, '6 4');   // исходная — бледным пунктиром
  mathLine(g, t, mx, my, COL.D, 2.8);
  labelCurveMath(g, f, mx, my, 'Исходная', COL.ghost);
  labelCurveMath(g, t, mx, my, MATH_TRANS[STATE.mathTrans].tex, COL.D);
  STATE.mathRes = { trans: STATE.mathTrans, a: paramValue('a', 1) };
  updateMathPanel();
}
// Подпись кривой на полном плане: ищем видимый участок, как в Фазе 3.
/* П25. Здесь и скакали подписи сильнее всего: якорь ищется перебором 60 проб
   в ДОЛЯХ от окна, и при зуме условие «точка внутри окна» срабатывает на
   соседнем узле — подпись прыгает сразу на процент с лишним ширины. Место
   ищется по-прежнему, но едет к нему подпись плавно, тем же сглаживанием, что
   и у экономических сцен (smoothLabel). Ключ у каждой подписи свой — иначе
   «Исходная» и «После» тянули бы одну и ту же память. */
function labelCurveMath(g, f, mx, my, txt, color, key) {
  const [lo, hi] = mx.domain(), [ylo, yhi] = my.domain();
  for (let i = 0; i <= 60; i++) {
    const x = hi - (hi - lo) * (0.06 + i * 0.014);
    const v = f(x);
    if (!isNaN(v) && v >= ylo && v <= yhi) {
      const sm = smoothLabel('math:' + (key || txt), mx(x), my(v), true);
      g.append('text').attr('x', sm.px - 4).attr('y', sm.py - 7).attr('text-anchor', 'end')
        .attr('font-size', curveLabelSize()).attr('font-weight', 600).attr('fill', color)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6).text(txt);
      return;
    }
  }
}

/* ── 7д. Наименьшая или наибольшая из нескольких функций ─────────────
   Функций может быть сколько угодно (не только две). Первые четыре живут в
   отдельных полях состояния, остальные в массиве; пустое поле не участвует. */
const MM_KEYS = ['mathFormula', 'mathG2', 'mathG3', 'mathG4'];
const MM_SUB = ['₁', '₂', '₃', '₄', '₅', '₆', '₇', '₈'];

function mmSlots() { return Math.max(4, STATE.mmCount || 2); }
function mmGet(i) {
  return (i < 4) ? String(STATE[MM_KEYS[i]] || '') : String((STATE.mathGmore || [])[i - 4] || '');
}
function mmSet(i, v) {
  if (i < 4) STATE[MM_KEYS[i]] = v;
  else { STATE.mathGmore = STATE.mathGmore || []; STATE.mathGmore[i - 4] = v; }
}
// Как назвать i-ю исходную функцию: f₁, f₂, f₃…
function mmLabel(i) { return 'f' + (MM_SUB[i] || ('_' + (i + 1))); }
// Цвет i-й кривой: свой из пикера или очередной из палитры.
function mmColor(i) {
  const own = (STATE.colorOverride || {})['mm' + i];
  if (own) return own;
  const pal = [COL.D, COL.S, COL.reg, COL.MR, COL.tax, COL.MC, COL.costATC, COL.costAVC];
  return pal[i % pal.length];
}

function drawMathMinMax(f) {
  const { mx, my } = mathScales();
  const g = svg.append('g');
  drawGrid(mx, my, g);
  drawPlaneAxes(g, mx, my, 'x', 'y');
  const parts = [{ fn: f, name: mmLabel(0), color: mmColor(0) }];
  for (let i = 1; i < mmSlots(); i++) {
    const expr = mmGet(i);
    if (!expr.trim()) continue;
    const { compiled } = compileMath(expr, 'x');
    if (!compiled) continue;
    parts.push({ fn: (x) => evalMathAt(compiled, 'x', x), name: mmLabel(i), color: mmColor(i) });
  }
  if (parts.length < 2) { STATE.mathRes = { error: 'Нужна хотя бы вторая функция.' }; updateMathPanel(); return; }
  const isMin = (STATE.mathMinMax === 'min');
  const z = (x) => {
    let best = NaN;
    parts.forEach(p => {
      const v = p.fn(x);
      if (isNaN(v)) return;
      if (isNaN(best)) { best = v; return; }
      best = isMin ? Math.min(best, v) : Math.max(best, v);
    });
    return best;
  };
  parts.forEach(p => {
    mathLine(g, p.fn, mx, my, p.color, 1.8, '5 4');
    labelCurveMath(g, p.fn, mx, my, p.name, p.color);
  });
  const zName = (STATE.mmName || 'Z').trim() || 'Z';
  const zColor = COL.mmZ || COL.MC;
  mathLine(g, z, mx, my, zColor, 3.2);
  labelCurveMath(g, z, mx, my, zName, zColor);
  // Точки, где ветви меняются местами: корни разности каждой пары, но в зачёт
  // идут только те, где обе функции в этот момент и есть итоговая Z.
  const sw = [];
  for (let a = 0; a < parts.length; a++) {
    for (let b2 = a + 1; b2 < parts.length; b2++) {
      rootsOf((x) => parts[a].fn(x) - parts[b2].fn(x), STATE.mathXmin, STATE.mathXmax).forEach(x => {
        const y = parts[a].fn(x);
        if (isNaN(y)) return;
        if (Math.abs(y - z(x)) > Math.max(1e-6, Math.abs(y) * 1e-6)) return;   // ветвь не главная
        if (sw.some(v => Math.abs(v - x) < (STATE.mathXmax - STATE.mathXmin) * 1e-4)) return;
        sw.push(x);
        mathDot(g, mx, my, x, y, COL.MC, null);
      });
    }
  }
  sw.sort((a, b2) => a - b2);
  STATE.mathRes = { switches: sw, isMin, count: parts.length };
  updateMathPanel();
}

/* ── 7е. Оптимизация с ограничением ───────────────────────────────────
   Переиспользует движок касания уровня (optimizeAlongConstraint /
   traceLevelCurve). Своей математики здесь нет.
   Переменные называются x и y: буквы a и b были нейтральны, но занимали имена,
   которые школьник привычно берёт под параметры. */
// Своя компиляция f(x, y): общая compileTwoVar пробует формулу на x/y/L/K и на
// «x^0.5 * y^0.5» справляется, но здесь нужны ещё и старые имена a/b — записи
// из прошлых версий должны продолжать считаться.
function compileAB(expr) {
  try {
    const compiled = math.parse(expr).compile();
    compiled.evaluate(scopeFor(expr, { a: 1, b: 1, x: 1, y: 1, L: 1, K: 1 }));
    return { compiled, error: null };
  } catch (e) { return { compiled: null, error: 'Не понял формулу f(x, y): ' + e.message }; }
}

/* Произвольное (неявное) ограничение G(a, b) = 0.
   Прямая pa·a + pb·b = M — частный случай, но школьные задачи часто дают
   окружность (a² + b² = 25) или другую кривую. Ищем её точки численно:
   для каждого a решаем G(a, b) = 0 по b, а на найденной линии перебираем
   значение целевой функции. Метод тот же, что у линии уровня. */
function parseConstraint(src) {
  const t = String(src || '').trim();
  if (!t) return null;
  const eq = t.indexOf('=');
  const expr = (eq >= 0) ? ('(' + t.slice(0, eq) + ') - (' + t.slice(eq + 1) + ')') : t;
  const r = compileAB(expr);
  if (!r.compiled) return null;
  return (a, b) => {
    try {
      const v = r.compiled.evaluate(paramScope({ a, b, x: a, y: b, L: a, K: b }));
      return (typeof v === 'number' && isFinite(v)) ? v : NaN;
    } catch (e) { return NaN; }
  };
}

/* Точки ограничения в прямоугольнике окна: для каждого x — первый y, где
   G(x, y) меняет знак. Границы приходят снаружи, поэтому кривую видно и в
   отрицательной части плоскости, если пользователь снял первую четверть. */
function constraintPointsIn(G, x0, x1, y0, y1, N) {
  N = N || 260;
  const out = [];
  for (let i = 0; i <= N; i++) {
    const a = x0 + (x1 - x0) * i / N;
    const g = (b) => G(a, b);
    let prevB = y0, prevV = g(y0);
    for (let j = 1; j <= 160; j++) {
      const b = y0 + (y1 - y0) * j / 160, v = g(b);
      if (!isNaN(prevV) && !isNaN(v) && prevV * v <= 0 && prevV !== v) {
        const root = (prevV === 0) ? prevB : (v === 0 ? b : bisect(g, prevB, b));
        if (isFinite(root)) { out.push([a, root]); break; }
      }
      prevB = b; prevV = v;
    }
  }
  return out;
}
// Прежняя форма вызова (от нуля до предела) — через общий вариант.
function constraintPoints(G, aMax, bMax, N) {
  return constraintPointsIn(G, 0, aMax, 0, bMax, N);
}

// Максимум (или минимум) F вдоль произвольного ограничения.
function optimizeAlongCurve(f, pts, wantMax) {
  let best = null;
  pts.forEach(([a, b]) => {
    const v = f(a, b);
    if (!isFinite(v)) return;
    if (!best || (wantMax ? v > best.value : v < best.value)) best = { a, b, value: v };
  });
  return best;
}

/* Подогнать окно под ограничение. Делается ОДИН раз при входе в сюжет и при
   смене формулы, а не на каждой перерисовке: иначе своё окно, выбранное
   колесом, сцена возвращала бы себе обратно, и зум не работал бы вовсе. */
function constraintFit() {
  let xMax = 12, yMax = 12;
  const G = parseConstraint(STATE.mathGC);
  if (G) {
    const probe = constraintPoints(G, 1e3, 1e3, 120);
    if (probe.length) {
      xMax = padMax(Math.max.apply(null, probe.map(q => q[0])));
      yMax = padMax(Math.max.apply(null, probe.map(q => q[1])));
    }
  }
  // Запоминаем размах задачи: по нему ищется оптимум независимо от того,
  // насколько человек приблизил картинку.
  STATE.consFit = { xMax: xMax || 12, yMax: yMax || 12 };
  setMathWindow(0, xMax || 12, 0, yMax || 12);
  STATE.viewDirty = false;
  updateResetViewBtn();
}

function drawMathConstraint() {
  const g = svg.append('g');
  const { compiled, error } = compileAB(STATE.mathFC);
  // Окно общее для всего раздела, поэтому колесо и перетаскивание работают
  // здесь ровно так же, как в остальных сюжетах.
  const { mx, my } = mathScales();
  drawGrid(mx, my, g);
  drawPlaneAxes(g, mx, my, 'x', 'y');
  if (!compiled) {
    STATE.mathRes = { error: error || 'не понял формулу' };
    updateMathPanel(); return;
  }
  const f = (a, b) => {
    try {
      const v = compiled.evaluate(paramScope({ x: a, y: b, a, b, L: a, K: b }));
      return (typeof v === 'number' && isFinite(v)) ? v : NaN;
    } catch (e) { return NaN; }
  };
  const line = d3.line().x(d => mx(d[0])).y(d => my(d[1]));
  const G = parseConstraint(STATE.mathGC);
  if (!G) {
    STATE.mathRes = { error: 'Не понял ограничение. Пример: x^2 + y^2 = 25' };
    updateMathPanel(); return;
  }
  const [x0, x1] = mx.domain(), [y0, y1] = my.domain();
  // Рисуем ту часть ограничения, что попала в окно.
  const pts = constraintPointsIn(G, x0, x1, y0, y1);
  if (pts.length > 1) {
    g.append('path').datum(pts).attr('fill', 'none')
      .attr('stroke', COL.S).attr('stroke-width', 2.6).attr('d', line);
  }
  /* А ищем по всей задаче, а не по видимому куску: приблизили картинку — ответ
     не должен меняться. Область поиска это размах ограничения, объединённый с
     текущим окном. */
  const fit = STATE.consFit || { xMax: x1, yMax: y1 };
  const sx0 = Math.min(x0, 0), sx1 = Math.max(x1, fit.xMax);
  const sy0 = Math.min(y0, 0), sy1 = Math.max(y1, fit.yMax);
  const searchPts = (sx0 === x0 && sx1 === x1 && sy0 === y0 && sy1 === y1)
    ? pts : constraintPointsIn(G, sx0, sx1, sy0, sy1);
  const opt = optimizeAlongCurve(f, searchPts, STATE.mathConsWantMax !== false);
  /* Точки ограничения кладём в состояние: по ним катается точка и по ним же
     ищутся ключевые точки сюжета (Н66). Пересчитывать их второй раз в
     mathSnapTargets значило бы делать ту же тяжёлую работу дважды за кадр. */
  STATE.mathRes = { opt, wantMax: STATE.mathConsWantMax !== false, conPts: pts };
  if (opt) {
    // Веер линий уровня + линия, проходящая через оптимум (она и касается ограничения).
    [0.55, 0.78, 1.25].forEach(k => drawLevelCurveOn(g, mx, my, f, opt.value * k, COL.D, 1.5, 0.32));
    drawLevelCurveOn(g, mx, my, f, opt.value, COL.D, 2.6, 1);
    mathDot(g, mx, my, opt.a, opt.b, COL.ink,
      (STATE.mathConsWantMax === false ? 'минимум (' : 'максимум (') + fmt(opt.a) + '; ' + fmt(opt.b) + ')', null, 'opt');
  }
  updateMathPanel();
}
// Линия уровня F = const на своих шкалах (движок трассировки — общий).
function drawLevelCurveOn(g, mx, my, f, level, color, width, opacity) {
  const pts = traceLevelCurve(f, level, mx.domain()[1], my.domain()[1], 220);
  if (!pts || pts.length < 2) return;
  const line = d3.line().defined(d => d !== null).x(d => mx(d[0])).y(d => my(d[1]));
  g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color)
    .attr('stroke-width', width).attr('opacity', opacity).attr('d', line);
}

/* Разбор «как получен ответ» для сюжета с экстремумами. Не пересказ учебника,
   а ход именно этой задачи: где обнулилась производная, какой знак у второй
   производной в каждой такой точке и что из этого следует. */
function mathOptimumReasoning(r) {
  const f = mathF();
  if (!f) return '';
  const ext = r.ext || [], inf = r.inf || [];
  let h = '<div class="sb-note"><b>Как это получилось</b>';
  h += "<p><b>По чему ищутся экстремумы?</b> Экстремум там, где касательная горизонтальна, то есть $f'(x) = 0$. "
     + 'Корни ищутся численно: сетка по отрезку и уточнение делением пополам, '
     + 'поэтому подходит любая функция, даже кусочная.</p>';
  if (!ext.length) h += '<p><b>А если ничего не нашлось?</b> На этом отрезке производная в нуль не обращается: ни максимумов, ни минимумов.</p>';
  ext.forEach(p => {
    const s = d2Num(f, p.x);
    const kind = p.kind === 'max' ? 'максимум' : (p.kind === 'min' ? 'минимум' : 'плато');
    const sign = s > 0 ? 'больше нуля' : (s < 0 ? 'меньше нуля' : 'равна нулю');
    h += `<p>$x^* = ${fmt(p.x)}$: здесь $f' = 0$, а $f'' = ${fmt(s)}$, то есть ${sign}. `
       + `Значит, ${kind}. ${p.kind === 'max' ? 'Кривая выпукла вверх' : (p.kind === 'min' ? 'Кривая выпукла вниз' : 'Знак не определился')}.</p>`;
  });
  h += "<p>Перегиб это смена знака второй производной $f''$: до него кривая выгнута "
     + 'в одну сторону, после в другую. Поэтому его и ищут как корень f″(x) = 0, '
     + 'но засчитывают только там, где знак действительно поменялся.</p>';
  if (inf.length) {
    h += '<p>Найдено: ' + inf.map(p => '$x^* = ' + fmt(p.x) + '$').join(', ') + '.</p>';
  } else {
    h += '<p>Здесь вторая производная знак не меняет, поэтому перегибов нет.</p>';
  }
  h += '<p>Наибольшее и наименьшее на отрезке берутся не только по этим точкам, '
     + 'но и по его концам: у школьных задач ответ часто именно на краю.</p>';
  return h + '</div>';
}

// Табло раздела.
function updateMathPanel() {
  const box = document.getElementById('info-math');
  if (!box) return;
  const r = STATE.mathRes || {};
  let html = '';
  if (STATE.mathSub === 'tangent') {
    if (isNaN(r.y0)) html = '<div class="warn">В этой точке функция не определена.</div>';
    else {
      html += `<div class="stat"><span>Точка $x_0$</span><b>${fmt(r.x0)}</b></div>`;
      html += `<div class="stat"><span>$f(x_0)$</span><b>${fmt(r.y0)}</b></div>`;
      html += `<div class="stat"><span>Наклон касательной $f'(x_0)$</span><b>${fmt(r.k)}</b></div>`;
      html += `<div class="stat"><span>Угол наклона</span><b>${fmt(Math.atan(r.k) * 180 / Math.PI)}°</b></div>`;
      if (r.secant != null) {
        html += `<div class="stat"><span>Наклон секущей</span><b>${fmt(r.secant)}</b></div>`;
        html += `<div class="stat"><span>Разница с касательной</span><b>${fmt(Math.abs(r.secant - r.k))}</b></div>`;
      }
      html += `<div class="stat"><span>Касательная</span><b>y = ${fmt(r.y0)} ${r.k >= 0 ? '+' : '-'} ${fmt(Math.abs(r.k))}·(x ${r.x0 >= 0 ? '-' : '+'} ${fmt(Math.abs(r.x0))})</b></div>`;
      // Разбор: откуда взялось это число и что показывает треугольник.
      html += '<div class="sb-note"><b>Как это получилось</b>'
        + `<p><b>Что вообще такое производная?</b> Это скорость: на сколько меняется y, если x подвинуть чуть-чуть. `
        + `Берём две близкие точки слева и справа от x₀ и делим прирост y на прирост x. `
        + `Шаг подбирается от ширины окна, поэтому счёт одинаково точен и на отрезке 0…0.1, и на 0…1000.</p>`
        + `<p><b>При чём здесь треугольник?</b> Он и есть это отношение: горизонтальный катет Δx, `
        + `вертикальный Δy = ${fmt(r.k)}·Δx. Их частное не зависит от размера треугольника, `
        + `оно и равно наклону.</p>`
        + (r.secant != null
            ? `<p>Секущая проходит через две точки на расстоянии Δx и имеет наклон ${fmt(r.secant)}. `
              + `Разница с касательной ${fmt(Math.abs(r.secant - r.k))}: уменьшайте Δx, и она стремится к нулю. `
              + `Это и есть предел, которым определяют производную.</p>`
            : '<p>Включите секущую, и будет видно, как при уменьшении Δx она ложится на касательную.</p>')
        + `<p>Внизу нарисована $f'(x)$ целиком: там, где она выше нуля, функция растёт, `
        + `где ниже, там убывает. А её собственные нули это максимумы и минимумы самой функции.</p>`
        + '</div>';
    }
  } else if (STATE.mathSub === 'optimum') {
    if (r.gMax) html += `<div class="stat"><span>Наибольшее на отрезке</span><b>$y^* = ${fmt(r.gMax.y)}$ при $x^* = ${fmt(r.gMax.x)}$</b></div>`;
    if (r.gMin) html += `<div class="stat"><span>Наименьшее на отрезке</span><b>$y^* = ${fmt(r.gMin.y)}$ при $x^* = ${fmt(r.gMin.x)}$</b></div>`;
    (r.ext || []).forEach(p => {
      html += `<div class="stat"><span>${p.kind === 'max' ? 'Локальный максимум' : (p.kind === 'min' ? 'Локальный минимум' : 'Плато')}</span><b>$(x^*; y^*) = (${fmt(p.x)}; ${fmt(p.y)})$</b></div>`;
    });
    (r.inf || []).forEach(p => { html += `<div class="stat"><span>Перегиб</span><b>$(x^*; y^*) = (${fmt(p.x)}; ${fmt(p.y)})$</b></div>`; });
    // Разбор: как машина к этому пришла, шаг за шагом и с числами.
    html += mathOptimumReasoning(r);
    if (!html) html = '<div class="muted">На этом отрезке ни экстремумов, ни перегибов.</div>';
  } else if (STATE.mathSub === 'transform') {
    const t = MATH_TRANS[STATE.mathTrans];
    html += `<div class="stat"><span>Преобразование</span><b>${t.tex}</b></div>`;
    html += `<div class="stat"><span>Параметр $a$</span><b>${fmt(paramValue('a', 1))}</b></div>`;
    html += `<div class="hint">${t.note}</div>`;
  } else if (STATE.mathSub === 'minmax') {
    if (r.error) html = `<div class="warn">${r.error}</div>`;
    else {
      const nm = (STATE.mmName || 'Z').trim() || 'Z';
      const names = [];
      for (let i = 0; i < mmSlots(); i++) if (mmGet(i).trim()) names.push(mmLabel(i));
      html += `<div class="stat"><span>Строим</span><b>${nm} = ${r.isMin ? 'min' : 'max'}(${names.join(', ')})</b></div>`;
      html += `<div class="stat"><span>Функций участвует</span><b>${r.count}</b></div>`;
      html += `<div class="stat"><span>Кривые меняются местами</span><b>${(r.switches || []).length ? r.switches.map(fmt).join(', ') : 'нигде'}</b></div>`;
      html += '<div class="sb-note"><b>Как это получилось</b>'
        + `<p><b>Как строится итоговая кривая?</b> В каждой точке x берётся ${r.isMin ? 'наименьшее' : 'наибольшее'} из значений всех функций. `
        + `Получается ломаная из кусков исходных кривых: ${r.isMin ? 'нижняя' : 'верхняя'} огибающая. `
        + `${r.isMin ? 'Она всюду не выше любой из них' : 'Она всюду не ниже любой из них'}, и совпадает с той, что в этой точке главная.</p>`
        + `<p><b>Откуда берутся изломы?</b> Точки перелома это корни разности пары функций: где f₁ − f₂ меняет знак, там кривые и меняются местами. `
        + `Корни ищутся численно и засчитываются только там, где обе функции в этот момент и есть ${nm}.</p>`
        + `<p>Экономический смысл тот же у нижней огибающей средних издержек: в каждой точке фирма выбирает `
        + `самый дешёвый способ, и длинная кривая складывается из кусков коротких.</p>`
        + '</div>';
    }
  } else if (STATE.mathSub === 'constraint') {
    if (r.error) html = `<div class="warn">${r.error}</div>`;
    else if (!r.opt) html = '<div class="muted">Точка не нашлась: проверьте формулы и границы окна.</div>';
    else {
      html += `<div class="stat"><span>$x^*$</span><b>${fmt(r.opt.a)}</b></div>`;
      html += `<div class="stat"><span>$y^*$</span><b>${fmt(r.opt.b)}</b></div>`;
      html += `<div class="stat"><span>$f(x^*,\, y^*)$</span><b>${fmt(r.opt.value)}</b></div>`;
      html += `<div class="stat"><span>Ищем</span><b>${r.wantMax ? 'максимум' : 'минимум'}</b></div>`;
      html += '<div class="sb-note"><b>Как это получилось</b>'
        + '<p><b>Что такое ограничение на графике?</b> Это кривая: точки, где g(x, y) обращается в ноль. '
        + 'Она ищется численно, для каждого x подбирается свой y, поэтому подходит '
        + 'любая форма, а не только прямая.</p>'
        + `<p><b>Как ищется оптимум?</b> Вдоль этой кривой перебирается значение цели, и берётся ${r.wantMax ? 'наибольшее' : 'наименьшее'}. `
        + 'Тонкими линиями нарисован веер линий уровня цели, жирной та, что проходит через найденную точку.</p>'
        + '<p><b>Почему именно касание?</b> Линия уровня касается ограничения, а не пересекает его. Это и есть признак оптимума: '
        + 'сдвинуться вдоль ограничения в любую сторону значит перейти на линию уровня хуже.</p>'
        + '</div>';
    }
  }
  box.innerHTML = html;
}

function redrawMath() {
  svg.selectAll('*').remove();
  addDefs();
  const err = document.getElementById('math-error');
  // Сюжеты со своей формулой f(x) не нужны «Ограничению» и «Осям наоборот».
  if (STATE.mathSub === 'constraint') { if (err) err.style.display = 'none'; drawMathConstraint(); return; }
  const f = mathF();
  if (!f) {
    if (err) { err.style.display = 'block'; err.textContent = 'Не понял формулу f(x).'; }
    const { mx, my } = mathScales();
    const gErr = svg.append('g');
    drawGrid(mx, my, gErr);
    drawPlaneAxes(gErr, mx, my, 'x', 'y');
    STATE.mathRes = {}; updateMathPanel(); return;
  }
  if (err) err.style.display = 'none';
  if (STATE.mathSub === 'tangent')   drawMathTangent(f);
  else if (STATE.mathSub === 'optimum')   drawMathOptimum(f);
  else if (STATE.mathSub === 'transform') drawMathTransform(f);
  else if (STATE.mathSub === 'minmax')    drawMathMinMax(f);
}

// Переключение сюжета: показываем нужную панель и характерный пример.
const MATH_PRESETS = {
  tangent:    { f: 'x^2',            win: [-6, 6, -4, 20] },
  optimum:    { f: 'x^3 - 3*x',      win: [-3, 3, -6, 6] },
  transform:  { f: 'x^2',            win: [-8, 8, -6, 14] },
  minmax:     { f: 'x^2',            win: [-5, 6, -3, 12] },
  constraint: { f: 'x^2',            win: [0, 12, 0, 12] },
};
function setMathSub(sub, keepFormula) {
  STATE.mathSub = sub;
  [['ms-tangent', 'tangent'], ['ms-optimum', 'optimum'], ['ms-transform', 'transform'],
   ['ms-minmax', 'minmax'], ['ms-constraint', 'constraint']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === sub); });
  ['tangent', 'optimum', 'transform', 'minmax', 'constraint'].forEach(v => {
    const p = document.getElementById('math-pane-' + v);
    if (p) p.style.display = (v === sub) ? '' : 'none';
  });
  // Свои поля есть у «Ограничения» и у сюжета min/max: общее f(x) им не нужно.
  const rowF = document.getElementById('math-row-f');
  if (rowF) rowF.style.display = (sub === 'constraint' || sub === 'minmax') ? 'none' : '';
  if (sub === 'minmax') renderMmRows();
  if (sub === 'constraint' && !keepFormula) { constraintFit(); redrawAll(); return; }
  const p = MATH_PRESETS[sub];
  if (p && !keepFormula) {
    STATE.mathFormula = p.f;
    const inp = document.getElementById('inp-mathf');
    if (inp) { inp.value = p.f; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    setMathWindow(p.win[0], p.win[1], p.win[2], p.win[3]);
  }
  redrawAll();
}
function setMathWindow(x0, x1, y0, y1) {
  tanResetWindows();     // окна панелей сюжета про производную считаются заново
  // «Только первая четверть» работает и здесь: окно не заходит в минус,
  // ширина и высота при этом сохраняются.
  if (STATE.firstQuad) {
    if (x0 < 0) { x1 -= x0; x0 = 0; }
    if (y0 < 0) { y1 -= y0; y0 = 0; }
  }
  STATE.mathXmin = x0; STATE.mathXmax = x1; STATE.mathYmin = y0; STATE.mathYmax = y1;
  syncViewFields();     // поля границ в меню плоскости идут за окном вживую
  const sl = document.getElementById('mathx0-slider');
  if (sl) { sl.min = x0; sl.max = x1; sl.step = (x1 - x0) / 200; }
  setMathX0(Math.max(x0, Math.min(x1, STATE.mathX0)));
}
function setMathX0(x) {
  STATE.mathX0 = x;
  // Точное значение показывает поле #mathx0-input рядом с ползунком, отдельной
  // подписи-значения в разметке нет (Свх-4б).
  const s = document.getElementById('mathx0-slider'); if (s) s.value = x;
  // Поле точного значения не трогаем, пока в нём печатают: иначе округление
  // отгрызает у «-11.78» последний знак прямо под руками.
  const n = document.getElementById('mathx0-input');
  if (n && document.activeElement !== n) n.value = Math.round(x * 1000) / 1000;
  redrawAll();
}

/* ---------------------------------------------------------------------
   ЭКСПОРТ (Фаза 5). Три формата:
     PNG — целиком на клиенте: SVG → картинка → canvas → файл. Работает
           всегда, сервер не нужен.
     TeX — нарисованный холст переводится в TikZ (buildTex): на бумаге
           выходит ровно то же, что на экране, в том же масштабе и сразу для
           любой сцены. Чистый TikZ без pgfplots, поэтому файл собирается
           обычным pdflatex.
     PDF — тот же .tex компилируется на сервере (calc2/views.export_pdf).
           На бесплатном тарифе Render компилятора нет, поэтому кнопка там
           отключена и об этом написано прямо в окне.
   --------------------------------------------------------------------- */

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Имя файла: заголовок из окна экспорта → заголовок графика → название сцены.
function exportBaseName() {
  const t = (document.getElementById('exp-title') || {}).value || STATE.graphTitle
            || SCENE_NAMES[STATE.sceneKey] || 'график';
  return String(t).trim().replace(/[\\/:*?"<>|]+/g, '-').slice(0, 60) || 'график';
}

function exportPNG(scale) {
  const node = document.getElementById('chart');
  if (!node) return;
  const w = node.clientWidth || W, h = node.clientHeight || H;
  const clone = node.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', w); clone.setAttribute('height', h);
  const src = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  img.onload = () => {
    const cv = document.createElement('canvas');
    cv.width = Math.round(w * scale); cv.height = Math.round(h * scale);
    const ctx = cv.getContext('2d');
    ctx.fillStyle = cssVar('--canvas') || '#ffffff';   // фон под тему, иначе прозрачный
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, 0, 0, cv.width, cv.height);
    cv.toBlob(b => {
      if (!b) { toast('Не получилось собрать картинку'); return; }
      downloadBlob(b, exportBaseName() + '.png');
      toast('PNG сохранён');
    });
  };
  img.onerror = () => toast('Не получилось собрать картинку');
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(src);
}

// ── .tex ────────────────────────────────────────────────────────────────
function texEscape(s) {
  return String(s == null ? '' : s)
    .replace(/\\/g, '\\textbackslash{}')
    .replace(/([&%$#_{}])/g, '\\$1')
    .replace(/~/g, '\\textasciitilde{}')
    .replace(/\^/g, '\\textasciicircum{}');
}
const r2 = (v) => (Math.round(v * 100) / 100);

/* ---------------------------------------------------------------------
   ЭКСПОРТ В LaTeX
   Раньше .tex собирался заново из формул рыночной сцены, и в остальных
   тридцати сюжетах выходила не та картинка и не в том масштабе: оси брались
   из CONFIG.Qmax, а «Математика», КПВ, макро, труд и потребитель живут в
   своих окнах, да и заливки с MR, DWL и вмешательством генератор просто не
   знал. Теперь в TikZ переводится уже НАРИСОВАННЫЙ холст, поэтому на бумаге
   получается ровно то же, что на экране, сразу для любой сцены.
   Чистый TikZ без pgfplots: файл собирается обычным pdflatex.
   --------------------------------------------------------------------- */
const TEX_WIDTH_CM = 16;      // ширина картинки на странице

/* Высота картинки в файле — не константа, а пропорция того, что на экране.
   Раньше стояло width × 0.62 при любом холсте: диапазоны осей уходили верные,
   а вот сколько сантиметров приходится на единицу по X и по Y — уже нет, и
   бумага показывала не тот масштаб, который видел пользователь (Фаза 9). */
function texPlotSize() {
  const m = CONFIG.margin;
  const pw = Math.max(1, (W - m.right) - m.left);
  const ph = Math.max(1, (H - m.bottom) - m.top);
  // Слишком вытянутую картинку прижимаем к разумным пределам страницы.
  const ratio = Math.max(0.28, Math.min(1.4, ph / pw));
  return { w: TEX_WIDTH_CM, h: Math.round(TEX_WIDTH_CM * ratio * 10) / 10, ratio };
}
const TEX_MAX_SAMPLES = 420;  // точек на одну кривую при оцифровке

// Символы, которых нет в кириллических шрифтах pdflatex: уводим их в математику.
// Применяется ПОСЛЕ texEscape, потому что подстановки содержат $ и обратный слэш.
const TEX_UNICODE = [
  ['₀', '$_0$'], ['₁', '$_1$'], ['₂', '$_2$'], ['₃', '$_3$'], ['₄', '$_4$'],
  ['₅', '$_5$'], ['₆', '$_6$'], ['₇', '$_7$'], ['₈', '$_8$'], ['₉', '$_9$'],
  ['⁰', '$^0$'], ['¹', '$^1$'], ['²', '$^2$'], ['³', '$^3$'],
  ['′', "$'$"], ['″', "$''$"], ['−', '$-$'], ['–', '--'], ['—', '---'],
  ['×', '$\\times$'], ['·', '$\\cdot$'], ['÷', '$\\div$'], ['±', '$\\pm$'],
  ['≈', '$\\approx$'], ['≤', '$\\le$'], ['≥', '$\\ge$'], ['≠', '$\\ne$'],
  ['∞', '$\\infty$'], ['∫', '$\\int$'], ['∑', '$\\sum$'], ['√', '$\\sqrt{\\ }$'],
  ['°', '$^\\circ$'], ['→', '$\\to$'], ['←', '$\\leftarrow$'], ['↔', '$\\leftrightarrow$'],
  ['Δ', '$\\Delta$'], ['α', '$\\alpha$'], ['β', '$\\beta$'], ['γ', '$\\gamma$'],
  ['π', '$\\pi$'], ['τ', '$\\tau$'], ['σ', '$\\sigma$'], ['λ', '$\\lambda$'],
  ['μ', '$\\mu$'], ['ε', '$\\varepsilon$'], ['θ', '$\\theta$'], ['Σ', '$\\Sigma$'],
  ['∈', '$\\in$'], ['∂', '$\\partial$'], [' ', '~'],
];
function texText(s) {
  let out = texEscape(s);
  TEX_UNICODE.forEach(([from, to]) => { out = out.split(from).join(to); });
  return out;
}

// Любой CSS-цвет → шесть шестнадцатеричных цифр. Браузер уже отдаёт
// вычисленное значение, поэтому переменные темы разворачивать не нужно.
function texHex(css) {
  const s = String(css || '').trim();
  const m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  const two = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).toUpperCase().padStart(2, '0');
  if (m) return two(+m[1]) + two(+m[2]) + two(+m[3]);
  if (/^#[0-9a-f]{6}$/i.test(s)) return s.slice(1).toUpperCase();
  if (/^#[0-9a-f]{3}$/i.test(s)) return s.slice(1).split('').map(c => (c + c).toUpperCase()).join('');
  return '000000';
}

/* Оцифровка нарисованного элемента. getPointAtLength обходит фигуру по длине
   и потому одинаково хорошо берёт и ломаные, и кривые Безье. Пути с разрывами
   (d3 .defined) состоят из нескольких кусков; переход между ними занимает
   нулевую длину, поэтому в выборке он виден скачком — по нему и режем, иначе
   TikZ соединил бы куски прямой через весь график. */
function texSamplePath(el) {
  let len = 0;
  try { len = el.getTotalLength(); } catch (e) { return []; }
  if (!(len > 0)) return [];
  const n = Math.max(2, Math.min(TEX_MAX_SAMPLES, Math.ceil(len / 2)));
  const m = el.getCTM();
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const p = el.getPointAtLength(len * i / n);
    pts.push(m ? [m.a * p.x + m.c * p.y + m.e, m.b * p.x + m.d * p.y + m.f] : [p.x, p.y]);
  }
  const step = len / n, jump = Math.max(6, step * 6);
  const runs = [];
  let run = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1];
    if (Math.hypot(dx, dy) > jump) { if (run.length > 1) runs.push(run); run = [pts[i]]; }
    else run.push(pts[i]);
  }
  if (run.length > 1) runs.push(run);
  return runs;
}

/* ── Перевод выражения Math.js в язык pgfplots ────────────────────────
   Кривая, записанную формулой, незачем выгружать сотнями координат: pgfplots
   умеет рисовать её сам, и файл получается коротким и читаемым. Переводим
   только то, что pgfplots точно понимает; всё остальное честно уходит
   точками (см. комментарий в самом файле). */
const PGF_FUNCS = {
  sqrt: 'sqrt', abs: 'abs', exp: 'exp', ln: 'ln', log: 'ln',
  min: 'min', max: 'max', sin: 'sin', cos: 'cos', tan: 'tan',
};

function mathToPgf(expr, varName) {
  const src = String(expr || '').trim();
  if (!src) return null;
  let node;
  try { node = math.parse(src); } catch (e) { return null; }
  const vars = new Set([varName, 'x', 'Q', 'L', 'X']);
  let bad = false;

  const walk = (n) => {
    if (bad) return '';
    switch (n.type) {
      case 'ConstantNode': return String(n.value);
      case 'SymbolNode': {
        if (vars.has(n.name)) return 'x';
        if (n.name === 'pi') return 'pi';
        if (n.name === 'e') return 'e';
        const p = (STATE.params || {})[n.name];
        if (p) return '(' + p.value + ')';       // параметр печатаем его значением
        bad = true; return '';
      }
      case 'ParenthesisNode': return '(' + walk(n.content) + ')';
      case 'OperatorNode': {
        if (n.args.length === 1) return (n.op === '-' ? '(-' : '(+') + walk(n.args[0]) + ')';
        if (n.args.length !== 2) { bad = true; return ''; }
        if ('+-*/^'.indexOf(n.op) < 0) { bad = true; return ''; }
        return '(' + walk(n.args[0]) + ' ' + n.op + ' ' + walk(n.args[1]) + ')';
      }
      case 'FunctionNode': {
        const name = n.fn && n.fn.name;
        if (name === 'nthRoot' && n.args.length === 2) {
          return '((' + walk(n.args[0]) + ')^(1/(' + walk(n.args[1]) + ')))';
        }
        const f = PGF_FUNCS[name];
        if (!f) { bad = true; return ''; }
        // Тригонометрия в pgfplots считает В ГРАДУСАХ — переводим явно.
        if (f === 'sin' || f === 'cos' || f === 'tan') {
          return f + '(deg(' + n.args.map(walk).join(',') + '))';
        }
        return f + '(' + n.args.map(walk).join(',') + ')';
      }
      default: bad = true; return '';
    }
  };
  const out = walk(node);
  return bad ? null : out;
}

/* Свойства нарисованной линии для pgfplots. */
function pgfStroke(el, cs, colorName) {
  const o = ['color=' + colorName(cs.stroke)];
  const w = parseFloat(cs.strokeWidth) || 1;
  o.push('line width=' + (w * 0.35).toFixed(2) + 'pt');
  const dash = (el.getAttribute('stroke-dasharray') || cs.strokeDasharray || '').trim();
  if (dash && dash !== 'none') o.push('dashed');
  const op = parseFloat(cs.strokeOpacity) * parseFloat(cs.opacity || 1);
  if (isFinite(op) && op < 0.99) o.push('opacity=' + op.toFixed(2));
  return o;
}

/* Главный сборщик .tex. Рисуется ровно то, что на экране: границы осей,
   заливки, кривые, точки, подписи и легенда берутся из текущего состояния
   и текущего холста. */
function buildTex(title, label) {
  const svgEl = document.getElementById('chart');
  if (!svgEl) return '';
  const { mx, my } = mainScales();
  const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
  const notes = [];                       // пояснения, почему что-то ушло точками

  const defs = [];
  const colorName = (css) => {
    const h = texHex(css), key = 'c' + h;
    const line = '\\definecolor{' + key + '}{HTML}{' + h + '}';
    if (defs.indexOf(line) < 0) defs.push(line);
    return key;
  };
  const num = (v) => (Math.round(v * 10000) / 10000);
  const pt = (x, y) => '(' + num(x) + ',' + num(y) + ')';
  const toData = (px, py) => [mx.invert(px), my.invert(py)];

  const body = [];
  const inView = (x, y) => x >= xLo - 1e-9 && x <= xHi + 1e-9 && y >= yLo - 1e-9 && y <= yHi + 1e-9;
  // Подписи и маркеры на бумаге должны занимать ту же долю картинки, что на
  // экране. Без пересчёта они выходят вдвое крупнее и налезают друг на друга.
  const mrg = CONFIG.margin;
  const ptPerPx = (texPlotSize().h * 28.4527) / Math.max(1, H - mrg.top - mrg.bottom);

  // 1) Кривые, у которых есть формула, — одной строкой каждая.
  const drawnByFormula = new Set();
  if (STATE.mode !== 'math') {
    STATE.curves.forEach(c => {
      if (!c.visible || !c.expr || c.kind === 'vertical') return;
      const pgf = mathToPgf(c.expr, 'Q');
      if (!pgf) return;
      drawnByFormula.add(c.id);
      const lo = Math.max(0, xLo), hi = xHi;
      body.push('\\addplot[' + colorName(c.color) + ', very thick, domain=' + num(lo) + ':' + num(hi) +
                ', samples=120, restrict y to domain=' + num(Math.max(0, yLo)) + ':' + num(yHi) + '] {' + pgf + '};');
      const nm = texText(curveShortName(c));
      if (nm) body.push('\\addlegendentry{' + nm + '}');
    });
  }

  // 2) Всё остальное с холста: заливки, точки, пунктиры, подписи.
  const walk = (node) => {
    for (const el of node.children) {
      const tag = el.tagName.toLowerCase();
      if (tag === 'defs' || tag === 'clippath' || tag === 'marker') continue;
      const cls = String(el.getAttribute('class') || '');
      // Оси и сетку pgfplots рисует сам; легенда закрашенных областей нужна
      // на бумаге ровно та же, что на экране, поэтому её переносим как есть.
      if (cls === 'axes' || cls === 'grid') continue;
      if (tag === 'g') { walk(el); continue; }

      if (el.getAttribute('data-skip-export')) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
      // Полностью прозрачный цвет — это служебная фигура (дорожка для мыши,
      // подложка под подсказку). На бумаге её быть не должно.
      const solid = (c) => { const m = /rgba?\([^)]*?,\s*([\d.]+)\s*\)$/.exec(String(c || '')); return !m || parseFloat(m[1]) > 0.01; };
      const hasFill = cs.fill && cs.fill !== 'none' && parseFloat(cs.fillOpacity) > 0 && solid(cs.fill);
      const hasStroke = cs.stroke && cs.stroke !== 'none' && (parseFloat(cs.strokeWidth) || 0) > 0 && solid(cs.stroke);

      if (tag === 'path') {
        const cid = el.getAttribute('data-curve');
        if (cid && drawnByFormula.has(+cid)) continue;          // уже нарисована формулой
        const runs = texSamplePath(el).map(r => {
          // Плотность режем: на бумаге двадцати точек на кривую достаточно,
          // а файл становится читаемым.
          const step = Math.max(1, Math.ceil(r.length / 60));
          return r.filter((p, i) => i % step === 0 || i === r.length - 1).map(p => toData(p[0], p[1]));
        });
        if (hasFill) {
          runs.forEach(r => {
            if (r.length < 3) return;
            body.push('\\fill[' + colorName(cs.fill) + ', opacity=' +
              (parseFloat(cs.fillOpacity) * parseFloat(cs.opacity || 1) || 0.2).toFixed(2) + '] ' +
              r.map(p => '(axis cs:' + num(p[0]) + ',' + num(p[1]) + ')').join(' -- ') + ' -- cycle;');
          });
        }
        if (hasStroke) {
          runs.forEach(r => {
            if (r.length < 2) return;
            if (cid) notes.push('% кривая выгружена точками: её формулу pgfplots не понимает');
            body.push('\\addplot[' + pgfStroke(el, cs, colorName).join(', ') + ', forget plot] coordinates {' +
              r.map(p => pt(p[0], p[1])).join(' ') + '};');
          });
        }
      } else if (tag === 'line') {
        if (!hasStroke) continue;
        const a = toData(+el.getAttribute('x1'), +el.getAttribute('y1'));
        const b = toData(+el.getAttribute('x2'), +el.getAttribute('y2'));
        body.push('\\addplot[' + pgfStroke(el, cs, colorName).join(', ') + ', forget plot] coordinates {' +
          pt(a[0], a[1]) + ' ' + pt(b[0], b[1]) + '};');
      } else if (tag === 'rect') {
        const x = +el.getAttribute('x'), y = +el.getAttribute('y');
        const w = +el.getAttribute('width'), h = +el.getAttribute('height');
        if (!(w > 0 && h > 0) || !hasFill) continue;
        const a = toData(x, y + h), b = toData(x + w, y);
        if (!inView(a[0], a[1]) && !inView(b[0], b[1])) continue;
        body.push('\\fill[' + colorName(cs.fill) + ', opacity=' +
          (parseFloat(cs.fillOpacity) * parseFloat(cs.opacity || 1) || 0.2).toFixed(2) + '] ' +
          '(axis cs:' + num(a[0]) + ',' + num(a[1]) + ') rectangle (axis cs:' + num(b[0]) + ',' + num(b[1]) + ');');
      } else if (tag === 'circle') {
        const c = toData(+el.getAttribute('cx'), +el.getAttribute('cy'));
        if (!inView(c[0], c[1])) continue;
        const col = colorName(hasFill ? cs.fill : cs.stroke);
        body.push('\\addplot[' + col + ', only marks, mark size=' +
          Math.max(0.6, (+el.getAttribute('r') || 4) * ptPerPx).toFixed(1) + 'pt, forget plot] coordinates {' + pt(c[0], c[1]) + '};');
      } else if (tag === 'text') {
        const raw = Array.prototype.filter.call(el.childNodes, n => n.nodeType === 3)
          .map(n => n.nodeValue).join('');
        const txt = texText(raw);
        if (!txt.trim()) continue;
        const c = toData(+el.getAttribute('x') || 0, +el.getAttribute('y') || 0);
        if (!inView(c[0], c[1])) continue;
        const ha = { start: 'west', middle: '', end: 'east' }[cs.textAnchor] ?? '';
        const bl = el.getAttribute('dominant-baseline') || cs.dominantBaseline || '';
        const va = (bl === 'hanging' || bl === 'text-before-edge') ? 'north'
                 : (bl === 'middle' || bl === 'central') ? '' : 'base';
        const anchor = (va + (va && ha ? ' ' : '') + ha).trim() || 'base';
        const fs = Math.max(4, (parseFloat(cs.fontSize) || 11) * ptPerPx);
        const opt = ['anchor=' + anchor, 'text=' + colorName(cs.fill),
                     'font=\\fontsize{' + fs.toFixed(1) + '}{' + (fs * 1.15).toFixed(1) + '}\\selectfont',
                     'inner sep=1pt'];
        body.push('\\node[' + opt.join(', ') + '] at (axis cs:' + num(c[0]) + ',' + num(c[1]) + ') {' + txt + '};');
      }
    }
  };
  walk(svgEl);

  const cap = texText(title || STATE.graphTitle || '');
  const lab = String(label || '').trim().replace(/[^A-Za-z0-9:_-]/g, '');
  const xName = texText(STATE.axisXName || STATE.axisXDefault || 'Q');
  const yName = texText(STATE.axisYName || STATE.axisYDefault || 'P');
  const uniq = [];
  notes.forEach(n => { if (uniq.indexOf(n) < 0) uniq.push(n); });

  return [
    '% Собран калькулятором «Экономика 2.0». Компилируется обычным pdflatex.',
    '\\documentclass[12pt,a4paper]{article}',
    '\\usepackage[T2A]{fontenc}',
    '\\usepackage[utf8]{inputenc}',
    '\\usepackage[english,russian]{babel}',
    '\\usepackage{pgfplots}',
    '\\pgfplotsset{compat=1.18}',
    '\\usetikzlibrary{arrows.meta}',
    '\\usepackage{geometry}',
    '\\geometry{margin=2cm}',
    ...defs,
    '',
    '\\begin{document}',
    '',
    '\\begin{figure}[h]',
    '\\centering',
    '\\begin{tikzpicture}',
    '\\begin{axis}[',
    '  width=' + texPlotSize().w + 'cm, height=' + texPlotSize().h + 'cm,',
    // Размер относится к самому полю графика, а не ко всей картинке вместе
    // с подписями: только так сантиметр на единицу совпадает с экраном.
    '  scale only axis,',
    '  xmin=' + num(xLo) + ', xmax=' + num(xHi) + ', ymin=' + num(yLo) + ', ymax=' + num(yHi) + ',',
    '  xlabel={' + xName + '}, ylabel={' + yName + '},',
    '  axis lines=left, axis line style={-{Stealth[length=6pt]}},',
    '  xlabel style={at={(axis description cs:1,0)}, anchor=west},',
    '  ylabel style={at={(axis description cs:0,1)}, anchor=south, rotate=-90},',
    STATE.showGrid ? '  grid=major, grid style={very thin, gray!25},' : '',
    '  legend pos=north east, legend cell align=left,',
    '  legend style={font=\\small, draw=gray!40},',
    ']',
    ...uniq,
    ...body,
    '\\end{axis}',
    '\\end{tikzpicture}',
    cap ? '\\caption{' + cap + '}' : '',
    lab ? '\\label{' + lab + '}' : '',
    '\\end{figure}',
    '',
    '\\end{document}',
  ].filter(s => s !== '').join('\n');
}
function exportTex() {
  const title = (document.getElementById('exp-title') || {}).value || '';
  const label = (document.getElementById('exp-label') || {}).value || '';
  const tex = buildTex(title, label);
  downloadBlob(new Blob([tex], { type: 'text/plain;charset=utf-8' }), exportBaseName() + '.tex');
  toast('Файл .tex сохранён');
}

function exportPDF() {
  const title = (document.getElementById('exp-title') || {}).value || '';
  const label = (document.getElementById('exp-label') || {}).value || '';
  const btn = document.getElementById('exp-pdf');
  if (btn) { btn.disabled = true; btn.textContent = 'Собираю…'; }
  const body = new FormData();
  body.append('tex', buildTex(title, label));
  body.append('name', exportBaseName());
  body.append('csrfmiddlewaretoken', (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '');
  fetch(CALC2_PDF_URL, { method: 'POST', body })
    .then(r => r.ok ? r.blob() : r.text().then(t => { throw new Error(t.slice(0, 200)); }))
    .then(b => { downloadBlob(b, exportBaseName() + '.pdf'); toast('PDF готов'); })
    .catch(e => toast('PDF не собрался: ' + e.message))
    .finally(() => { if (btn) { btn.disabled = false; btn.textContent = 'Скачать PDF'; } });
}

function openExport() {
  const m = document.getElementById('export-modal');
  if (!m) return;
  const t = document.getElementById('exp-title');
  if (t && !t.value) t.value = STATE.graphTitle || SCENE_NAMES[STATE.sceneKey] || '';
  m.classList.add('open');
  m.removeAttribute('inert');
  if (t) t.focus();
}
function closeExport() {
  const m = document.getElementById('export-modal');
  if (!m) return;
  m.classList.remove('open');
  m.setAttribute('inert', '');
  const b = document.getElementById('dock-export'); if (b) b.focus();
}

