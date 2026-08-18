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
/* ⚠️ ШИРИНУ ПОДПИСИ МЕРЯЕТ БРАУЗЕР, А НЕ «СТОЛЬКО-ТО ПИКСЕЛЕЙ НА ЗНАК».

   Прежняя оценка `знаков × 6.2` занижала ширину, и поле слева выходило меньше
   подписи. Замер (`scripts/calc2_layout_probe.js`): в «Производственной
   функции» деления «1 000 … 4 000» начинались с координаты −5…−7 px, то есть
   ЗА холстом, и на экране читалось «000». Причин занижения две, и обе
   неустранимы константой: разряды разделены узким неразрывным пробелом,
   а ширина цифры зависит от шрифта, которым страницу в итоге нарисовали.

   Меряем в ОТДЕЛЬНОМ невидимом svg, а не в самом холсте: по `#chart` ходят
   проходы `applyLabelInk`, `applyLabelSize`, `spreadLabels` и сборка `.tex`,
   и служебный узел подмешался бы во все четыре. При этом узел лежит ВНУТРИ
   `#graph-wrap`, чтобы наследовать тот же шрифт, что и подписи холста.

   Проверка канона 5.1: подставить значения в 10 000 раз крупнее — ни одна
   подпись не обрезана. */
let _measSvg = null, _measText = null;
function measureText(str, size, weight) {
  const txt = String(str == null ? '' : str);
  if (!txt) return 0;
  try {
    if (!_measText || !_measText.isConnected) {
      const host = document.getElementById('graph-wrap') || document.body;
      _measSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      _measSvg.setAttribute('aria-hidden', 'true');
      _measSvg.setAttribute('data-skip-export', '1');
      _measSvg.style.cssText = 'position:absolute;left:-9999px;top:-9999px;'
                             + 'width:10px;height:10px;overflow:hidden;pointer-events:none;';
      _measText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      _measSvg.appendChild(_measText);
      host.appendChild(_measSvg);
    }
    _measText.setAttribute('font-size', size || FS.small);
    _measText.setAttribute('font-weight', weight || 400);
    _measText.textContent = txt;
    const w = _measText.getComputedTextLength();
    if (w > 0) return w;
  } catch (e) { /* до сборки страницы мерить нечем — уходим в оценку */ }
  return txt.length * 6.2;             // запасная оценка, пока холста нет
}

/* Полоса под осью X: строка чисел делений (от oy+8) плюс строка подписи,
   которую сцены печатают на oy+24 («Дефицит = 40», «Безработица = 30»).
   Замер: при поле 30 такая подпись уходила на 5 px ЗА нижний край холста
   в четырёх сценах. Полоса одна на все сцены намеренно: список «кто пишет
   под осью» разъехался бы со сценами, а стоит она 14 px из ~790 по высоте. */
const BOTTOM_BAND = 44;

function fitMargins() {
  const m = CONFIG.margin;
  makeScales();
  let wide = 0;
  try {
    // Деления зависят только от диапазона, поэтому в «Математике» берём её
    // окно: там по вертикали свои границы, а не первая четверть.
    const dom = (STATE.mode === 'math')
      ? [STATE.mathYmin, STATE.mathYmax]
      : [CONFIG.Pmin, CONFIG.Pmax];
    const probe = d3.scaleLinear().domain(dom).range([0, 1]);
    axisTicks(probe, 8, STATE.yStep).forEach(t => {
      const w = measureText(fmt(t), FS.small);
      if (w > wide) wide = w;
    });
  } catch (e) { /* сцена ещё не готова — останемся со стартовыми полями */ }
  // 8 px отступа подписи от оси (её ставит drawAxes) + 6 px запаса у края.
  m.left = Math.max(30, Math.min(120, Math.ceil(wide) + 14));

  /* Справа за стрелкой стоит НАЗВАНИЕ оси X, и оно бывает длинным:
     «t (ставка)» — 76 px, «Поступления» — 106. При поле 32 такое название
     уезжало за холст на полсотни пикселей. Имя берём то же, что нарисует
     drawAxes: своё, если человек его задал, иначе сценовое. */
  const xName = STATE.axisXName || STATE.axisXDefault || 'Q';
  m.right = Math.max(32, Math.min(140,
              Math.ceil(AXIS_LABEL_GAP + measureText(xName, FS.large, 600)) + 6));

  m.bottom = BOTTOM_BAND;
  /* Сверху: полоса под своё название графика плюс место под НАЗВАНИЕ оси Y,
     которое drawAxes печатает над стрелкой. */
  const yName = STATE.axisYName || STATE.axisYDefault || 'P';
  const yNeed = yName ? AXIS_LABEL_GAP + Math.ceil(FS.large * 1.2) : 0;
  m.top = Math.max((STATE.graphTitle || '').trim() ? 44 : 26, yNeed + 8);
  makeScales();
}

/* ⚠️ ПОЛЕ СЛЕВА ПОД ЧУЖИЕ ДЕЛЕНИЯ (п. 35).
   fitMargins меряет деления ГЛАВНОЙ вертикали сцены — [CONFIG.Pmin, Pmax].
   Сцены с двумя панелями считают вертикаль сами: у производственной функции
   верхняя панель доходит до 5 000, и её «5 000» начиналось с координаты −7,
   то есть за левым краем холста, а на экране читалось «000».
   Сцена зовёт эту функцию СВОИМИ значениями делений ДО того, как построит
   шкалы: поле только расширяется, сузить его чужая панель не может. */
function fitLeftForLabels(values) {
  let wide = 0;
  (values || []).forEach(v => {
    const w = measureText(typeof v === 'number' ? fmt(v) : String(v), FS.small);
    if (w > wide) wide = w;
  });
  const need = Math.max(30, Math.min(120, Math.ceil(wide) + 14));
  if (need > CONFIG.margin.left) { CONFIG.margin.left = need; makeScales(); }
  return CONFIG.margin.left;
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

/* Отступ подписи оси от конца оси (П22). Один на обе оси и на все режимы,
   включая полный план в «Математике» и панели с двумя графиками. */
const AXIS_LABEL_GAP = 10;

// Перевод координат туда-обратно (пригодится для перетаскивания мышью).
function toPx(q, p) { return [sx(q), sy(p)]; }
function toData(px, py) { return [sx.invert(px), sy.invert(py)]; }

/* Формат числа для подписей делений (без длинных хвостов после точки).
   Числа пишем целиком: «5000», а не «5k» (П45). Раньше от тысячи включался
   формат `.2~s`, и сокращение вылезало и на осях, и в координатах точек, и в
   таблице площадей. Тысячи разделяем узким неразрывным пробелом — так
   «12 500» читается с одного взгляда и не разваливается по переносу строки.
   Ширину подписи меряет fitMargins по длине этой строки, поэтому поле слева
   само раздвинется под новые, более длинные числа. */
const NBTHIN = ' ';        // узкий неразрывный пробел — разделитель разрядов

/* ⚠️ ЧИСЛО НА ЭКРАНЕ ОКРУГЛЯЕТСЯ РОВНО В ОДНОМ МЕСТЕ (канон 2.2).
   Глубина округления — здесь и больше нигде: любое «Math.round(v*100)/100»,
   написанное рядом с выводом, рано или поздно разъедется с этим. */
const SHOWN_DECIMALS = 2;
const SHOWN_POW = Math.pow(10, SHOWN_DECIMALS);
function roundShown(v) { return Math.round(v * SHOWN_POW) / SHOWN_POW; }

/* ⚠️ СУММА СЧИТАЕТСЯ ИЗ ОКРУГЛЁННЫХ СЛАГАЕМЫХ, А НЕ ОКРУГЛЯЕТСЯ САМА (п. 1).
   На экране стояло «SW = CS + PS», а под ним CS 907,91 + PS 907,91 = 1 815,81:
   сумма считалась по сырым float и округлялась отдельно от слагаемых, поэтому
   в последнем разряде расходилась с тем, что человек видит и складывает сам.
   Первое, что заметит ученик, — именно это.
   Математика не меняется: STATE.sw по-прежнему точная сумма, из округлённого
   собирается только ПОКАЗ. */
function fmtSum(...parts) {
  const s = parts.reduce((acc, v) => acc + (isFinite(v) ? roundShown(v) : NaN), 0);
  return fmt(s, sumDecimals(parts));
}
/* Та же оговорка для разности: столбец «Δ» в таблице «До / После / Δ» обязан
   сходиться с двумя соседними столбцами, а не считаться по сырым значениям. */
function shownDiff(after, before) { return roundShown(after) - roundShown(before); }
function fmtDiff(after, before) {
  const d = shownDiff(after, before);
  return (d > 0 ? '+' : '') + fmt(d, sumDecimals([after, before]));
}

/* ⚠️ У СУММЫ ТА ЖЕ ГЛУБИНА, ЧТО У СЛАГАЕМЫХ (канон 2.2).
   «290,65 + 290,65 = 581,3» арифметически верно и всё равно читается как
   ошибка: в столбце два знака у слагаемых и один у итога, глаз ищет
   пропавшую копейку. Незначащий ноль печатается только там, где рядом
   стоят числа с этим разрядом; одиночное «50» так и остаётся «50».
   shownDecimals отвечает на вопрос «сколько знаков fmt напечатает САМ»,
   поэтому padding никогда не срезает значащую цифру. */
function shownDecimals(v) {
  const r = roundShown(v);
  if (!isFinite(r)) return 0;
  let frac = Math.round(Math.abs(r) * SHOWN_POW) % SHOWN_POW;
  let d = SHOWN_DECIMALS;
  while (d > 0 && frac % 10 === 0) { frac /= 10; d--; }
  return d;
}
function sumDecimals(parts) {
  return parts.reduce((d, v) => isFinite(v) ? Math.max(d, shownDecimals(v)) : d, 0);
}

function fmt(v, minDecimals) {
  const r = roundShown(v);
  if (!isFinite(r)) return String(v);
  const sign = r < 0 ? '-' : '';
  const a = Math.abs(r);
  const whole = Math.floor(a);
  let s = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, NBTHIN);
  const want = Math.max(shownDecimals(r), minDecimals || 0);
  // Дробная часть отделяется ЗАПЯТОЙ: интерфейс русский (Б15).
  if (want > 0) {
    const frac = String(Math.round((a - whole) * SHOWN_POW))
                   .padStart(SHOWN_DECIMALS, '0');
    s += ',' + frac.slice(0, want);
  }
  return sign + s;
}

/* То же число для ЧИСЛОВОГО ПОЛЯ. Поле type=number принимает только машинную
   запись: и запятая вместо точки, и разделитель разрядов делают значение
   недопустимым, и браузер молча очищает поле. Поэтому показ и заполнение
   поля — две разные записи одного числа. */
function fmtInput(v) {
  const r = Math.round(v * 100) / 100;
  return isFinite(r) ? String(r) : '';
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
function addDefs(mx, my) {
  // Шкалы приходят аргументом: у «Математики» и у панелей окно своё, и
  // прямоугольник обрезки, посчитанный от CONFIG, резал бы не там. Без
  // аргументов работает как раньше — по главным шкалам сцены.
  mx = mx || sx; my = my || sy;
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
  const [dx0, dx1] = mx.domain(), [dy0, dy1] = my.domain();
  const x0 = mx(quadLo(dx0)), x1 = mx(dx1);
  const y1 = my(dy1), y0 = my(quadLo(dy0));
  defs.append('clipPath').attr('id', 'plot-clip').append('rect')
    .attr('x', x0).attr('y', y1)
    .attr('width', Math.max(0, x1 - x0))
    .attr('height', Math.max(0, y0 - y1));

  /* Б43. Прямоугольник прибыли и убытка рисуется ШТРИХОВКОЙ, а не сплошным
     цветом. Сплошная зелёная заливка спорила с кривой MC: цвета не совпадали,
     но читались как один. Штриховка отличает область от линии по САМОМУ ВИДУ,
     а не по оттенку, поэтому спорить им больше нечем. */
  [['hatch-profit', COL.profit], ['hatch-loss', COL.bad]].forEach(([id, color]) => {
    const p = defs.append('pattern').attr('id', id)
      .attr('width', 7).attr('height', 7).attr('patternUnits', 'userSpaceOnUse')
      .attr('patternTransform', 'rotate(45)');
    p.append('rect').attr('width', 7).attr('height', 7).attr('fill', color).attr('opacity', 0.10);
    p.append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 7)
      .attr('stroke', color).attr('stroke-width', 2).attr('opacity', 0.55);
  });
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
/* Третий аргумент — названия осей ДЛЯ ЗАПИСИ, когда подпись сцена рисует сама:
   drawAxes('Q', '', { yName: 'Издержки' }). Без него сцены издержек, производства
   и заводов присылали пустую строку по вертикали, STATE.axisYDefault оставался с
   прошлой сцены (или начальным 'P'), и в выгрузке на графике ЗАТРАТ стояло
   ylabel={P} (Б37). Название оси — свойство сцены, а не побочный эффект того,
   кто рисует подпись. */
function drawAxes(xLabel, yLabel, opts) {
  if (xLabel == null) xLabel = 'Q'; if (yLabel == null) yLabel = 'P';
  if (opts && opts.xName) STATE.axisXDefault = opts.xName;
  if (opts && opts.yName) STATE.axisYDefault = opts.yName;
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
    if (t < sx.domain()[0] - 1e-9 || t > sx.domain()[1] + 1e-9) return;
    if (atZeroX && Math.abs(t) < 1e-12) return;      // ноль подписываем один раз
    if (sx(t) > xRight - 14 || sx(t) < xLeft + 2) return;
    g.append('line').attr('x1', sx(t)).attr('y1', oy).attr('x2', sx(t)).attr('y2', oy + 5)
      .attr('stroke', AX).attr('stroke-width', 1);
    g.append('text').attr('x', sx(t)).attr('y', oy + 8)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'hanging')
      .attr('class', 'axis-num').attr('font-size', FS.small).attr('fill', LBL).text(fmt(t));
  });
  // Деления и числа на оси Y.
  if (atZeroX) yTicks().forEach(t => {
    if (t < sy.domain()[0] - 1e-9 || t > sy.domain()[1] + 1e-9) return;
    if (atZeroY && Math.abs(t) < 1e-12) return;
    if (sy(t) < yTop + 14 || sy(t) > yBot - 2) return;
    g.append('line').attr('x1', ox).attr('y1', sy(t)).attr('x2', ox - 5).attr('y2', sy(t))
      .attr('stroke', AX).attr('stroke-width', 1);
    g.append('text').attr('x', ox - 8).attr('y', sy(t))
      .attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
      .attr('class', 'axis-num').attr('font-size', FS.small).attr('fill', LBL).text(fmt(t));
  });
  // Единственный «0» в начале координат (только если начало видно).
  if (atZeroX && atZeroY) {
    g.append('text').attr('x', ox - 8).attr('y', oy + 8)
      .attr('text-anchor', 'end').attr('dominant-baseline', 'hanging')
      .attr('class', 'axis-num').attr('font-size', FS.small).attr('fill', LBL).text('0');
  }

  /* Подписи осей: X-метка за стрелкой справа, Y-метка над стрелкой сверху.
     П22: отступ у обеих ОДИН и тот же и задан одной константой. Раньше стояло
     6 пикселей вправо у одной и 12 вверх плюс 4 влево у другой — числами по
     месту, и на разных сценах они читались по-разному.
     Пустая строка '' — сигнал «без метки» (неравенство и издержки ставят свою). */
  /* Н24: подпись оси помечена классом. Во-первых, по нему проверка ловит
     наложения; во-вторых, общий проход размера подписей (applyLabelSize) и
     выгрузка отличают её от прочих надписей. */
  /* ⚠️ НАЗВАНИЕ ОСИ ПЕРЕЕЗЖАЕТ, А НЕ УЕЗЖАЕТ ЗА КРАЙ.
     Поля холста считает fitMargins по измеренной ширине названия, но на самой
     первой отрисовке сцены STATE.axisXDefault ещё не заполнен, а человек может
     вписать своё название прямо сейчас — поле догонит его только следующим
     кадром. Поэтому место зажимается ещё и здесь: два предохранителя на одну
     беду, зато подпись не пропадает ни в одном порядке событий.
     Тот же приём уже принят для подписей кривых (curveAnchor): подпись
     переносится, а не скрывается. */
  const EDGE = 2;
  if (xLabel && atZeroY) {
    const w = measureText(xLabel, FS.large, 600);
    const x = Math.min(xRight + AXIS_LABEL_GAP, W - EDGE - w);
    g.append('text').attr('class', 'axis-name')
      .attr('x', Math.max(EDGE, x)).attr('y', oy)
      .attr('text-anchor', 'start').attr('dominant-baseline', 'middle')
      .attr('font-size', FS.large).attr('font-weight', 600)
      .attr('fill', COL.ink).text(xLabel);
  }
  if (yLabel && atZeroX) {
    const w = measureText(yLabel, FS.large, 600);
    // Якорь по центру, поэтому за край выходит половина ширины.
    const x = Math.min(Math.max(ox, EDGE + w / 2), W - EDGE - w / 2);
    const y = Math.max(yTop - AXIS_LABEL_GAP, FS.large + EDGE);
    g.append('text').attr('class', 'axis-name')
      .attr('x', x).attr('y', y)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'auto')
      .attr('font-size', FS.large).attr('font-weight', 600)
      .attr('fill', COL.ink).text(yLabel);
  }
}

