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
/* п. 22. РАЗРЫВ НЕ СОЕДИНЯЕТСЯ ОТРЕЗКОМ.

   У 1/(Q−30) в точке 30 полюс: слева функция уходит вниз, справа приходит
   сверху. Соседние узлы сетки давали −8000 и +8000, и рисователь честно
   соединял их прямой — на графике появлялась отвесная линия, которой у
   функции нет. Её принимали за часть кривой: она даже пересекала другие
   кривые и создавала «точки пересечения» из ничего.

   Признак полюса выбран по СМЫСЛУ, а не по величине: значения соседних
   узлов лежат по разные стороны от нуля И оба вышли далеко за окно. Крутая,
   но настоящая кривая под это правило не попадает — она окно не покидает
   или покидает с одной стороны. Разрыв отмечается `null`, и `d3.line`
   с `.defined` разрывает путь сам. */
function curvePoints(curve) {
  const N = 400;
  const out = [];
  // Считаем от видимого края, но не левее нуля: P = f(Q) для Q < 0 в экономике
  // смысла не имеет, а после панорамирования вправо незачем считать то,
  // что всё равно останется за кадром.
  const lo = quadLo(sx.domain()[0]), hi = sx.domain()[1];
  if (!(hi > lo)) return out;
  const [yLo, yHi] = sy.domain();
  const span = Math.abs(yHi - yLo) || 1;
  const OUT = span * 4;                     // «далеко за окном»
  let prev = null;
  for (let i = 0; i <= N; i++) {
    const q = lo + (hi - lo) * i / N;
    const p = evalCurve(curve, q);
    const val = isNaN(p) ? null : [q, p];
    if (val && prev && ((prev[1] - yLo) * (val[1] - yLo) < 0 || (prev[1] < yLo && val[1] > yHi) || (prev[1] > yHi && val[1] < yLo))
        && Math.abs(val[1] - prev[1]) > OUT) {
      out.push(null);                        // полюс: путь рвётся здесь
    }
    out.push(val);
    prev = val;
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
function markExpr(sel, curveOrExpr, varName, domain) {
  const expr = (curveOrExpr && typeof curveOrExpr === 'object')
    ? (curveOrExpr.texExpr || curveOrExpr.expr)
    : curveOrExpr;
  if (expr) {
    sel.attr('data-expr', String(expr));
    if (varName) sel.attr('data-expr-var', varName);
    /* Свой отрезок построения (Б5). Нужен кусочным кривым: у совокупных
       издержек двух заводов каждый гладкий кусок живёт на своём промежутке,
       и без этого pgfplots рисовал бы обе формулы во всю ширину. */
    if (domain && isFinite(domain[0]) && isFinite(domain[1])) {
      sel.attr('data-expr-from', domain[0]).attr('data-expr-to', domain[1]);
    }
  }
  return sel;
}

/* Производная формулы В ВИДЕ ФОРМУЛЫ (Б4). Предельные величины движок считает
   численно — это правильно, потому что работает для любой функции. Но в файл
   такая кривая уходила таблицей из шестидесяти точек, хотя для обычной записи
   производная берётся символьно и получается настоящая формула. Пробуем взять
   её; не вышло (корни, модули, кусочные) — возвращаем null, и кривая честно
   уходит точками с пояснением. */
function derivativeExpr(expr, varName) {
  if (!expr || typeof math === 'undefined' || typeof math.derivative !== 'function') return null;
  const v = varName || 'Q';
  try {
    const src = String(expr).replace(/\bx\b/g, v).replace(/\bQ\b/g, v).replace(/\bL\b/g, v);
    const d = math.derivative(src, v).toString();
    // Пробное вычисление: символьная производная бывает верной, но незаписываемой.
    const c = math.parse(d).compile();
    const probe = c.evaluate(paramScope(axisScope(1, { [v]: 1 })));
    return (typeof probe === 'number' && isFinite(probe)) ? d : null;
  } catch (e) { return null; }
}

/* ⚠️ ПОДПИСЬ ДЕРЖИТСЯ ЗА СВОЁ МЕСТО, ПОКА ОНО НЕ СТАЛО ПЛОХИМ.

   Замер дефекта: ползунок «a» вели от 1,00 до 2,00 шагами по 0,05. Деление «2»
   на оси не сдвинулось ни разу за все двадцать один шаг — плоскость стояла.
   Подпись при этом по горизонтали плыла плавно, а по вертикали скакала
   вверх-вниз на КАЖДОМ шаге: 87,6 → 95,8 → 101,1 → 93,1 → 86,3 → 94,5 → 85,8.
   До 13,6 px за шаг, а на участке от 0 до 3 — до 19,2.

   Причина не в сглаживании (оно уже есть и работает по горизонтали), а в
   выборе САМОГО МЕСТА: якорь искался заново каждый кадр — перебором 72 проб
   справа налево до первой, где кривая видна. Стоит форме кривой чуть
   измениться, и «первая видимая» проба становится соседней; у крутой кривой
   соседний узел сетки отстоит по вертикали далеко. Отсюда болтанка на ровном
   месте.

   Лечится памятью о МЕСТЕ ПО ОСИ X, а не сглаживанием пикселей: анимация
   такую болтанку только размазала бы в волну. Пока прежнее место годится
   (кривая там видна и подпись не уходит за холст), подпись остаётся на нём.
   Стало негодным — ищем заново, и уже переезд сглаживается как прежде. */
const _anchorQ = new Map();
/* Запас у края окна: место считается годным, пока кривая в нём не жмётся к
   самой границе — иначе подпись «удерживалась» бы ровно там, где её обрежет. */
const ANCHOR_EDGE = 0.02;

function curveAnchor(f, fromFrac, toFrac, key) {
  const from = (fromFrac == null) ? 0.97 : fromFrac;
  const to   = (toFrac   == null) ? 0.04 : toFrac;
  const [qLo, qHi] = sx.domain();
  const [vLo, vHi] = sy.domain();
  const pad = (vHi - vLo) * ANCHOR_EDGE;
  /* ⚠️ ГОДНОСТЬ МЕСТА СЧИТАЕТСЯ ПО НАСТОЯЩЕМУ ОКНУ, А НЕ ПО ПЕРВОЙ ЧЕТВЕРТИ.
     Первая версия требовала v ≥ 0 — условие из времён, когда все сцены жили в
     первой четверти. В полном плане («Построение графиков», вся «Математика»)
     кривая законно уходит под ось, прежнее место каждый раз объявлялось
     негодным, и память не работала вовсе: подпись искала якорь заново каждый
     кадр, как и до правки. Замер это и показал — скачок 14,1 px остался. */
  const good = (q, v) => !isNaN(v) && q >= qLo && q <= qHi &&
                         v >= vLo + pad && v <= vHi - pad;
  /* ⚠️ ДЕРЖИМСЯ ЗА МЕСТО ПОДПИСИ НА ЭКРАНЕ, А НЕ ЗА КООРДИНАТУ ПО ОСИ X.

     Первая попытка запоминала именно x и держалась за него, пока кривая в нём
     видна. Это дало ПИЛУ, и замер её показал: пока прежний x годится, подпись
     едет вверх вместе с кривой (кривая-то под ним меняется), доезжает до края
     окна, место объявляется негодным — и подпись прыгает на новое, заметно
     ниже. Дальше всё повторяется. Скачок 16,7 px за шаг.

     Правильная опора — то, что человек видит: САМО МЕСТО ПОДПИСИ. Среди годных
     точек берём ту, куда подпись сдвинется меньше всего в пикселях. Кривая
     деформируется — подпись скользит вдоль неё на ближайшее место, а не
     перепрыгивает. Прежнего места не было (первая отрисовка) — берём крайнее
     правое, как и раньше.

     Узлов больше прежних 72: место обязано двигаться плавно, а не шагами по
     проценту с лишним ширины окна. */
  const N = 240;
  const at = (q) => { try { const v = f(q); return isNaN(v) ? null : v; } catch (e) { return null; } };
  let best = null, loose = null, prevQ = null, prevV = null;
  for (let i = 0; i <= N; i++) {
    const q = qHi * (from + (to - from) * i / N);
    const v = at(q);
    if (v == null || v < vLo || v > vHi) { prevQ = q; prevV = v; continue; }
    if (!loose) loose = { q, v };
    if (good(q, v)) { best = { q, v, prevQ, prevV }; break; }
    prevQ = q; prevV = v;
  }
  const pick = best || loose;
  if (!pick) { if (key) _anchorQ.delete(key); return null; }

  /* ⚠️ ГРАНИЦУ ВИДИМОСТИ НАХОДИМ ТОЧНО, А НЕ ПО УЗЛУ СЕТКИ. Вот где сидела
     болтанка. Когда кривую делают круче, она уходит вверх за окно, и подпись
     садится у самого места, где кривая пересекает верх. Место это искалось
     перебором по сетке — то есть округлялось до узла. У крутой кривой соседние
     узлы разнесены по вертикали далеко, и значение в «первом годном» узле
     скакало между «у самого края» и «заметно ниже»: замер дал 16 px за шаг при
     НЕПОДВИЖНОЙ плоскости и строго монотонном движении самого якоря по
     горизонтали. Досчитываем пересечение бисекцией — и подпись едет по краю
     ровно, а не ступеньками.
     Если предыдущий узел был внутри окна (кривая никуда не уходит), уточнять
     нечего: сцена ведёт себя как раньше. */
  if (pick.prevV != null && pick.prevQ != null) {
    /* Сравниваем с ПОЛОСОЙ ГОДНОСТИ, а не с сырым окном. Первая версия
       сравнивала с окном, и уточнение не включалось никогда: к моменту, когда
       узел признан негодным, значение в нём уже внутри окна — просто в запасе
       у края. Замер это и показал: числа не сдвинулись ни на десятую. */
    const limit = (pick.prevV > vHi - pad) ? vHi - pad
                : ((pick.prevV < vLo + pad) ? vLo + pad : null);
    if (limit != null) {
      let lo = pick.prevQ, hi = pick.q;
      for (let k = 0; k < 40; k++) {
        const mid = (lo + hi) / 2;
        const v = at(mid);
        if (v == null) { lo = mid; continue; }
        const inside = (v <= vHi - pad && v >= vLo + pad);
        if (inside) hi = mid; else lo = mid;
      }
      const v = at(hi);
      if (v != null && v >= vLo && v <= vHi) { pick.q = hi; pick.v = v; }
      void limit;
    }
  }
  if (key) _anchorQ.set(key, pick.q);
  return { q: pick.q, v: pick.v };
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

/* Разведение подписей (А60).

   Замер попарно: в сцене налога подпись $Q_1 = 40$ налезала на деления оси 30,
   40 и 50 и читалась как «3Q₁=400 60», подпись кривой $S$ налезала на $S + t$.
   Всего по десяти сценам пятнадцать наложений.

   Подписи рисуют полсотни разных мест, поэтому разводим их одним проходом
   после отрисовки — тем же приёмом, что и общий размер. Кто нарисован раньше,
   тот и остаётся на месте: деления осей рисуются первыми и потому не двигаются
   никогда. Сдвиг только по вертикали и небольшой: подпись должна остаться у
   своего объекта, иначе разведение вредит больше, чем наложение. */
/* ⚠️ ПОДПИСЬ, КОТОРУЮ РЕЖЕТ СОБСТВЕННАЯ ОБРЕЗКА, ПЕРЕЕЗЖАЕТ НАРУЖУ (Добавка А).

   Обрезка нужна КРИВЫМ: без неё круто растущая линия вылезала бы за окно, а в
   сценах с двумя панелями — из своей панели в соседнюю. Подпись же не кривая:
   она стоит У края по устройству (деление оси, название кривой), и тот же
   прямоугольник срезал ей по половине знака. Замер этого не видел вовсе, пока
   Добавка А не научила его сравнивать подпись ещё и с клипом: подпись лежит
   ВНУТРИ холста, но СНАРУЖИ клипа. Найдено 39 подписей в 6 сценах: «−6» без
   минуса в «Функции и её производной», деления обеих панелей в «Мировой цене»,
   срезанные «AVC» и «MC» у правого края в издержках и монополии.

   Два предохранителя, чтобы проход не сделал хуже:
   · переезжает только та подпись, которую РЕЖЕТ. Спрятанная целиком остаётся
     спрятанной: её скрыли намеренно (деление панели, ось которой ушла за кадр),
     и вытащить её значит нарисовать лишнее;
   · переезд отменяется, если у любого предка есть `transform`: узел сменил бы
     систему координат и уехал. В calc2 таких групп нет, но правило дешевле
     проверки «а не завели ли новую».
   Слой один на холст и стоит последним, поэтому подписи оказываются поверх
   всего — им там и место. */
function unclipLabels() {
  const node = svg.node();
  if (!node) return;
  const box = node.getBoundingClientRect();
  let layer = null;
  const clipBox = new Map();
  const boxOf = (holder) => {
    if (clipBox.has(holder)) return clipBox.get(holder);
    let r = null;
    const m = (holder.getAttribute('clip-path') || '').match(/url\(#([^)]+)\)/);
    const def = m && (node.querySelector('#' + m[1]) || document.getElementById(m[1]));
    const rc = def && def.querySelector('rect');
    const ctm = holder.getScreenCTM && holder.getScreenCTM();
    if (rc && ctm) {
      const num = (a) => parseFloat(rc.getAttribute(a)) || 0;
      const at = (px, py) => {
        const p = node.ownerSVGElement ? node.ownerSVGElement.createSVGPoint() : node.createSVGPoint();
        p.x = px; p.y = py; return p.matrixTransform(ctm);
      };
      const a = at(num('x'), num('y')), b = at(num('x') + num('width'), num('y') + num('height'));
      r = { left: Math.min(a.x, b.x), top: Math.min(a.y, b.y),
            right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y) };
    }
    clipBox.set(holder, r);
    return r;
  };
  Array.prototype.forEach.call(node.querySelectorAll('text'), (t) => {
    let el = t.parentNode, holder = null, moved = false;
    while (el && el !== node) {
      if (el.getAttribute) {
        if (el.getAttribute('transform')) moved = true;
        if (!holder && /url\(#/.test(el.getAttribute('clip-path') || '')) holder = el;
      }
      el = el.parentNode;
    }
    if (!holder || moved) return;
    const cl = boxOf(holder);
    if (!cl) return;
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    const whole = r.left >= cl.left - 0.5 && r.right <= cl.right + 0.5
               && r.top >= cl.top - 0.5 && r.bottom <= cl.bottom + 0.5;
    if (whole) return;                                    // целиком внутри — не режет
    const touches = r.left < cl.right && cl.left < r.right
                 && r.top < cl.bottom && cl.top < r.bottom;
    if (!touches) return;                                 // спрятана целиком и намеренно
    void box;
    if (!layer) {
      layer = node.querySelector('g.free-labels');
      if (!layer) {
        layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        layer.setAttribute('class', 'free-labels');
      }
      node.appendChild(layer);                            // последним: подписи поверх всего
    }
    layer.appendChild(t);
  });
}

/* ⚠️ НАЗВАНИЕ ОСИ ЗАЖИМАЕТСЯ ПОСЛЕ ТОГО, КАК ПРИМЕНЁН РАЗМЕР ПОДПИСЕЙ.

   `drawAxes` уже зажимает название внутрь холста, но меряет его ПРЕЖНИМ
   кеглем: общий проход `applyLabelSize` идёт позже и множит размер всех
   подписей на выбранный человеком коэффициент. У якоря по центру подпись
   растёт в обе стороны, и «e (курс)» уезжала за левый край на 1,8 px,
   «Поступления» — на 4,6, «t (ставка)» и «Валюта» — за правый.
   Зажимаем ещё раз, уже по фактическому размеру: два предохранителя на одну
   беду, как и с самим `drawAxes`. Трогаем только названия осей — обычную
   подпись сдвиг оторвал бы от её объекта. */
function keepAxisNamesInside() {
  const node = svg.node();
  if (!node) return;
  const box = node.getBoundingClientRect();
  const EDGE = 2;
  Array.prototype.forEach.call(node.querySelectorAll('text.axis-name'), (t) => {
    const r = t.getBoundingClientRect();
    if (r.width < 0.5) return;
    let dx = 0;
    if (r.left - box.left < EDGE) dx = EDGE - (r.left - box.left);
    else if (r.right - box.left > box.width - EDGE) dx = box.width - EDGE - (r.right - box.left);
    if (!dx) return;
    const cur = parseFloat(t.getAttribute('x'));
    if (isFinite(cur)) t.setAttribute('x', cur + dx);
  });
}

function spreadLabels() {
  const node = svg.node();
  if (!node) return;
  const items = [];
  node.querySelectorAll('text').forEach(t => {
    if (t.getAttribute('data-no-spread')) return;
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    items.push({ el: t, x: r.left, y: r.top, w: r.width, h: r.height });
  });
  if (items.length < 2) return;

  const hit = (a, b) => (Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) > 2
                     && (Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)) > 2;
  const m = CONFIG.margin;
  /* ⚠️ ПЛАВАЮЩИЕ БЛОКИ — ТАКОЕ ЖЕ ЗАНЯТОЕ МЕСТО, ЧТО И ЧУЖАЯ ПОДПИСЬ (п. 39).
     Стопка кнопок масштаба лежит НАД холстом и вне SVG, поэтому разведение
     её не видело: «S» пряталась под кнопками почти во всех рыночных сценах.
     Кладём их в занятое ПЕРВЫМИ — двигать блок нельзя, двигается подпись. */
  const placed = (typeof floatRects === 'function' ? floatRects() : [])
    .map(r => ({ el: null, x: r.left, y: r.top, w: r.w, h: r.h }));
  const STEP = 13;               // чуть больше строки: подпись уходит целиком
  items.forEach(it => {
    if (!placed.length) { placed.push(it); return; }
    let dy = 0, dx = 0;
    /* Сначала вверх и вниз с нарастающим шагом, и только потом вбок: подпись
       обязана остаться у своего объекта, а сдвиг по вертикали связь с ним
       рвёт меньше. Вбок уходим последней попыткой — для подписей у самой оси,
       где сверху кривая, а снизу деление. */
    /* ⚠️ ШАГИ ПОБОЛЬШЕ — ПОТОМУ ЧТО ТЕПЕРЬ УХОДИТЬ ПРИХОДИТСЯ И ОТ БЛОКОВ.
       Стопка кнопок масштаба высотой около полутора сотен пикселей: подпись
       кривой у правого края (AVC в издержках, заголовок панели экспорта)
       прежним набором попыток из-под неё просто не вылезала и садилась на
       соседнюю подпись. Прежние мелкие шаги идут первыми — подпись обязана
       остаться у своего объекта, а большой сдвиг это последняя мера. */
    const tries = [
      [0, -STEP], [0, STEP], [0, -2 * STEP], [0, 2 * STEP], [0, -3 * STEP], [0, 3 * STEP],
      [22, 0], [-22, 0], [26, -STEP], [-26, -STEP],
      [-46, 0], [-46, -STEP], [-46, STEP], [-70, 0], [-70, -STEP],
      [0, 4 * STEP], [0, 5 * STEP], [-70, 2 * STEP],
    ];
    const box = node.getBoundingClientRect();
    for (let k = 0; k < tries.length; k++) {
      if (!placed.some(p => hit(it, p))) break;
      const [wx, wy] = tries[k];
      const top = it.y + wy, bottom = top + it.h;
      // За поле графика не выпускаем: там подпись всё равно не читается.
      if (top < box.top + m.top - 6 || bottom > box.top + (H - m.bottom) + 16) continue;
      const probe = { x: it.x + wx, y: top, w: it.w, h: it.h };
      if (!placed.some(p => hit(probe, p))) { dy = wy; dx = wx; it.y = top; it.x = probe.x; break; }
    }
    if (dy) {
      const cur = parseFloat(it.el.getAttribute('y'));
      if (isFinite(cur)) it.el.setAttribute('y', cur + dy);
    }
    if (dx) {
      const cur = parseFloat(it.el.getAttribute('x'));
      if (isFinite(cur)) it.el.setAttribute('x', cur + dx);
    }
    placed.push(it);
  });
}

/* ───────────────────────────────────────────────────────────────────────
   П75. ЧЕРНИЛА ПОДПИСИ — НЕ ЦВЕТ КРИВОЙ.

   Подпись на холсте это ТЕКСТ, и к ней применяется правило 5 части 4 канона:
   контраст не ниже 4,5 в ОБЕИХ темах. Цвета самих кривых при этом не трогаются
   — они предметная семантика (канон 5.1): спрос всегда одного цвета,
   предложение другого, и ученик запоминает пару.

   Замер до правки (`scripts/calc2_canon_probe.js`, все 41 сцена × 2 темы):
   106 подписей из 1796 ниже нормы. Аудит назвал пять примеров, на деле их
   в двадцать раз больше: `S` (#E0563B на белом) — 3,77; `MC` (#119C8A) — 3,42;
   `AVC`/`ATC`/«закрытие» (#B5791F) — 3,67; «безубыточность» (#2F6FED
   на тёмном) — 4,05; «Исходная» (#9AA0A6) — 2,64.

   Почему ОДИН ПРОХОД по холсту, а не правка в местах отрисовки. Подписи ставят
   больше сорока функций в девяти файлах, и каждая берёт цвет у своей кривой.
   Проход по готовому SVG чинит их все разом, работает для сцен, которых ещё
   нет, и повторяет уже принятый в проекте приём applyLabelSize (общий размер
   подписей). Он идемпотентен: исправленный цвет норму проходит, и следующий
   проход его не трогает.

   Оттенок сохраняется: двигаем только СВЕТЛОТУ в HSL и только в сторону от
   фона. Поэтому «S» остаётся тем же красным, только различимым. */
const _inkCache = new Map();

function parseColor(c) {
  if (!c) return null;
  c = String(c).trim();
  const m = /rgba?\(([^)]+)\)/.exec(c);
  if (m) {
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  }
  const h = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(c);
  if (!h) return null;
  let v = h[1];
  if (v.length === 3) v = v.split('').map(x => x + x).join('');
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16), 1];
}

function relLum(rgb) {
  const f = rgb.slice(0, 3).map(v => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
}

function contrastOf(a, b) {
  const l1 = relLum(a), l2 = relLum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn;
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  let h;
  if (mx === r) h = ((g - b) / d + (g < b ? 6 : 0));
  else if (mx === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return [h / 6, s, l];
}

function hslToRgb(h, s, l) {
  if (s === 0) { const v = Math.round(l * 255); return [v, v, v, 1]; }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  const ch = (t) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [Math.round(ch(h + 1 / 3) * 255), Math.round(ch(h) * 255), Math.round(ch(h - 1 / 3) * 255), 1];
}

/* ⚠️ ЦЕЛЬ ВЫШЕ НОРМЫ AA НАМЕРЕННО — ЭТО ЗАПАС, А НЕ ПРИДИРКА.
   Поиск идёт шагом 0,01 по светлоте и останавливается на первом значении,
   которое норму прошло. При цели ровно 4,5 минимум по всем 1796 подписям
   вышел 4,51, и 116 подписей сели в полосу 4,51…4,6: любая будущая правка
   цвета — своя тень, другой фон холста, новая тема — роняет их обратно под
   норму, и дефект возвращается целым классом. Цель 4,6 стоит того, что стоит:
   оттенок не меняется вовсе (двигается только светлота), а до фона остаётся
   один шаг запаса. Тот же порог зашит в тест канона (фаза 9, проверка 3)
   и в scripts/calc2_canon_probe.js — три числа обязаны совпадать. */
const INK_MIN_TEXT = 4.6;
const INK_MIN_LARGE = 3.0;

/* Цвет подписи, читаемый на фоне холста. Возвращает исходный цвет, если он
   и так проходит норму: большинство подписей менять не нужно. */
function labelInk(color, bgStr, large) {
  const bg = parseColor(bgStr) || [255, 255, 255, 1];
  const key = color + '|' + bgStr + '|' + (large ? 'L' : 'S');
  if (_inkCache.has(key)) return _inkCache.get(key);
  const need = large ? INK_MIN_LARGE : INK_MIN_TEXT;
  const fg = parseColor(color);
  let out = color;
  if (fg) {
    // Полупрозрачную подпись сначала кладём на фон: контраст меряется у того,
    // что видно, а не у объявленного цвета.
    const flat = fg[3] >= 1 ? fg
      : [0, 1, 2].map(i => Math.round(fg[i] * fg[3] + bg[i] * (1 - fg[3]))).concat([1]);
    if (contrastOf(flat, bg) < need) {
      const hsl = rgbToHsl(flat[0], flat[1], flat[2]);
      const darken = relLum(bg) > 0.5;     // светлый фон — темним, тёмный — светлим
      let best = null;
      for (let i = 1; i <= 100; i++) {
        const l = darken ? hsl[2] - i * 0.01 : hsl[2] + i * 0.01;
        if (l < 0 || l > 1) break;
        const cand = hslToRgb(hsl[0], hsl[1], l);
        if (contrastOf(cand, bg) >= need) { best = cand; break; }
      }
      if (!best) best = darken ? [0, 0, 0, 1] : [255, 255, 255, 1];
      out = 'rgb(' + best[0] + ', ' + best[1] + ', ' + best[2] + ')';
    }
  }
  _inkCache.set(key, out);
  return out;
}

/* Общий проход: после каждой перерисовки поправить чернила всех подписей.
   Смена темы меняет --canvas, поэтому кэш держит фон в ключе. */
function applyLabelInk() {
  const node = svg.node();
  if (!node) return;
  const bg = cssVar('--canvas') || '#ffffff';
  node.querySelectorAll('text').forEach(t => {
    const cs = getComputedStyle(t);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const fill = (cs.fill && cs.fill !== 'none') ? cs.fill : cs.color;
    const size = parseFloat(cs.fontSize) || 12;
    const bold = parseInt(cs.fontWeight, 10) >= 700;
    const op = parseFloat(cs.opacity);
    if (isFinite(op) && op < 0.05) return;   // спрятано прозрачностью — это не подпись
    /* ⚠️ ПРИГЛУШЕНИЕ ТЕКСТА ЧЕРЕЗ opacity ОТМЕНЯЕТСЯ, А НЕ ПОДКРАШИВАЕТСЯ.
       Канон 2.6: «Гашение через opacity не применять: оно делает текст
       нечитаемым, а не второстепенным». Пять подписей («Достижимо» 0,75,
       «эластичный»/«неэластичный» 0,8, «A»/«B» 0,85) остались бы ниже нормы
       даже с исправленным цветом — прозрачность разбавила бы его обратно.
       Поэтому прозрачность сворачивается В ЦВЕТ: считаем, как подпись
       выглядит на фоне, правим уже этот цвет и ставим полную непрозрачность.
       Второстепенность после этого несёт сам оттенок, а не мутность. */
    const eff = (isFinite(op) && op < 1) ? mixToBg(fill, bg, op) : fill;
    const ink = labelInk(eff, bg, size >= 24 || (size >= 18.66 && bold));
    if (ink && ink !== fill) t.setAttribute('fill', ink);
    if (isFinite(op) && op < 1) t.style.opacity = '1';
  });
}

function mixToBg(color, bgStr, op) {
  const fg = parseColor(color), bg = parseColor(bgStr);
  if (!fg || !bg) return color;
  const a = fg[3] * op;
  const m = [0, 1, 2].map(i => Math.round(fg[i] * a + bg[i] * (1 - a)));
  return 'rgb(' + m[0] + ', ' + m[1] + ', ' + m[2] + ')';
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
  const out = { px: nx, py: ny, toLeft: flip, below: prev.below };
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
function resetLabelPositions() { _labelPos.clear(); _anchorQ.clear(); }

function labelCurve(g, f, txt, color, opts) {
  const o = opts || {};
  const anchorKey = o.key || (o.curve && o.curve.id) || txt;
  const a = curveAnchor(f, o.from, o.to, anchorKey);
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
  /* ⚠️ У ПЕРЕВОРОТА ВВЕРХ-ВНИЗ ТОЖЕ ДОЛЖЕН БЫТЬ ЗАПАС.

     Горизонтальному перевороту запас дали давно (FLIP_HYST), а вертикальный
     решался голым сравнением: подпись стоит над кривой, а если упёрлась в
     верхний край — под кривой. Разница между вариантами 21 px, и пока порог
     проходил туда-сюда, подпись прыгала на эти самые 21 px на каждом шаге
     ползунка. Замер дефекта: 87,6 → 95,8 → 101,1 → 93,1 → 86,3 → 94,5 → 85,8,
     до 13,6 px за шаг при НЕПОДВИЖНОЙ плоскости.

     Теперь сторона помнится вместе с местом. Уходим с неё, только когда она
     стала по-настоящему плохой (подпись вылезает за холст), а возвращаемся —
     когда стало заведомо просторно. На самой границе решение не меняется. */
  const topLimit = m.top + 12, botLimit = H - m.bottom - 4;
  let below = (sm.below === undefined) ? !!o.below : sm.below;
  if (!below && py - 7 < topLimit) below = true;                       // упёрлись в верх
  else if (below && py + 14 > botLimit) below = false;                 // упёрлись в низ
  else if (below && !o.below && py - 7 > topLimit + FLIP_HYST) below = false;
  else if (!below && o.below && py + 14 < botLimit - FLIP_HYST) below = true;
  sm.below = below;
  _labelPos.set(key, sm);
  const y = py + (below ? 14 : -7);
  const tx = toLeft ? px - 6 : px + 6;
  void rawPy;                                     // сырое место нужно было только для сглаживания
  const t = g.append('text')
    .attr('class', 'curve-name')     // реестр обозначений и проверка канона ищут по нему
    .attr('x', tx).attr('y', y)
    .attr('text-anchor', toLeft ? 'end' : 'start')
    .attr('font-size', o.size || curveLabelSize()).attr('font-weight', 600).attr('fill', color)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6);
  // А28: название кривой набирается как величина (MC, S + t, Q_d), а не
  // обычным текстом. Решает общий разбор, тот же, что у панели и у файла.
  renderLabelText(t, txt);
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
    /* ⚠️ У ПОЛОСЫ ПОВЕРХ КРИВОЙ ДВА РАЗНЫХ СМЫСЛА, И ОНИ РАЗВЕДЕНЫ.

       Полоса делала сразу две вещи: давала допуск попадания по кривой И
       служила ручкой перетаскивания. Пока они были одним свойством, каждая
       кривая, по которой хочется щёлкнуть, автоматически становилась
       подвижной, а каждая неподвижная — недоступной щелчку. Отсюда обе беды
       ревью сразу: вписанную формулу утягивало мышью, а по кривой, которую
       двигать нельзя, нельзя было и попасть.

       Теперь свойства раздельные:
         · «по кривой можно щёлкнуть» — полоса строится ВСЕГДА, курсор pointer;
         · «кривую можно тянуть»      — та же полоса работает ручкой, ns-resize.

       Ширина 16 px остаётся: владелец просил, чтобы щелчок рядом с кривой
       считался щелчком по кривой. Курсор не имеет права обещать действие,
       которого нет, поэтому он выбирается по второму свойству, а не по факту
       существования полосы.

       Пока набирают вершины или ставят свою точку, полосы нет вовсе: иначе
       она перехватывала бы щелчок, которым ставят точку. */
    if (!canvasArmed()) {
      const drag = curveDraggable(curve);
      const hit = g.append('path').datum(pts)
        .attr('fill', 'none').attr('stroke', 'transparent').attr('stroke-width', CURVE_HIT_PX)
        .attr('data-skip-export', '1')    // это полоса для мыши, а не линия графика
        .attr('data-hit', curve.id)
        .attr('data-hit-name', curveShortName(curve))
        .attr('d', line).style('cursor', drag ? 'ns-resize' : 'pointer');
      if (drag) attachDrag(hit, curve);
      /* Щелчок по полосе взводит кривую: загораются её ключевые точки.
         Порога смещения не вводим — люди щёлкают статично, в один пиксель
         (решение владельца). Перетаскиванию это не мешает: у d3.drag свой
         порог, и после настоящего протягивания щелчок браузером не выдаётся. */
      hit.on('click', (ev) => { ev.stopPropagation(); armCurve(curveShortName(curve)); });
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

/* Б34. Сдвиг спроса рукой — основной сюжет темы и главный интерактив
   калькулятора, поэтому фичу не убираем. Настоящая беда в другом: на
   отдельных графиках одновременно двигается слишком много всего, и рука
   попадает не туда, куда метила. Разгружаем ТОЧЕЧНО — там, где у сюжета есть
   свои подвижные объекты и кривые им мешают:
     · эластичность — по кривым уже ездят две точки эластичности;
     · потоварные и адвалорные налоги — там своя подвижная линия ставки.
   В остальных сценах сдвиг кривых мышью работает как раньше. */
/* На сколько надо сдвинуть указатель, чтобы нажатие по кривой стало
   прокатыванием точки, а не щелчком по кривой. */
const ROLL_START_PX = 4;

/* ⚠️ ДОГОВОР О ПАРАМЕТРАХ: РЫЧАГ, КОТОРЫЙ НИЧЕГО НЕ ДВИГАЕТ, НЕ ПОКАЗЫВАЕТСЯ.

   Замер живым набором по всем сорока одной сцене (`scripts/calc2_params_probe.js`)
   нашёл ровно одну болезнь и ровно в трёх сценах: «Дискриминация 3-й степени»,
   «Составной спрос» и «Монополист и внешний рынок» рисуют свои кривые по
   СОБСТВЕННЫМ полям формул (`d3D1`, `kiD1`, `kinkMC`), а карточка «Кривые» с
   общим списком у них при этом открыта. Человек вписывал туда формулу с буквой,
   получал ползунок — и ползунок не двигал ничего. Ни ошибки, ни предупреждения:
   ученик решает, что неправильно вписал формулу.

   Молчащий рычаг хуже отсутствующего, поэтому карточка общего списка живёт
   только там, где сцена этот список действительно рисует. Признак берётся из
   состояния модели, а не из ключа карточки: `pickScene` ставит `STATE.sceneKey`
   ПОСЛЕ `run()`, и правило, спрошенное по ключу, читало бы ключ прошлой сцены.

   Второй половиной договора занимается `syncParams`: пока список не рисуется,
   буквы из него ползунков не заводят. Иначе рычаг остался бы, просто без своей
   карточки — та же болезнь, вид сбоку. */
function sceneDrawsCurveList() {
  if (STATE.mode !== 'market') return true;             // остальные режимы свой список рисуют
  if (STATE.market !== 'monopoly') return true;
  return STATE.monoMode !== 'discr3' && STATE.monoMode !== 'kinked';
}

/* Показать или спрятать карточку общего списка кривых. Зовут два места, где
   меняется признак: смена режима (applyScenarioVisibility) и смена под-режима
   монополии (applyMonoVisibility). Второй копии правила рядом быть не должно. */
function syncCurveListVisibility() {
  const box = document.getElementById('sec-curves');
  if (!box) return;
  if (STATE.mode !== 'market' && STATE.mode !== 'labor') return;   // там карточку прячет setMode
  box.style.display = sceneDrawsCurveList() ? '' : 'none';
}

const NO_CURVE_DRAG = ['elast', 'tax', 'tax-adv'];

/* ⚠️ «СЦЕНА НЕ ДВИГАЕТ КРИВЫЕ ВООБЩЕ» И «КРИВЫЕ НЕ ТЯНУТСЯ МЫШЬЮ» — РАЗНОЕ.

   Список выше читает не только холст: `pultCurveList` в правой панели гасит по
   нему ползунки сдвига D и S. Пока это было одним признаком, запрет мыши в
   «Спросе и предложении» унёс с собой и ползунки — то есть отнял у сцены
   единственный оставшийся способ сдвинуть кривые, прямо вопреки решению
   владельца. Нашёл прибор; ни разбор исходников, ни тесты этого не видели.

   Поэтому запрет мыши живёт отдельным списком. В «Спросе и предложении»
   кривые мышью не тянутся, а ползунки на месте и работают. */
const NO_MOUSE_DRAG = ['sd'];
function curveDragAllowed() {
  return NO_CURVE_DRAG.indexOf(STATE.sceneKey) < 0;
}

/* Глубина округления сдвинутой мышью формулы — три знака (решение владельца
   19.08). Отдельно от roundShown (два знака, канон 2.2): та отвечает за ЧИСЛА
   НА ЭКРАНЕ, а это — за запись функции, которая обязана совпадать с тем, что
   нарисовано, вплоть до последнего разряда. */
const DRAG_DECIMALS = 3;
const DRAG_POW = Math.pow(10, DRAG_DECIMALS);
function roundDrag(v) { return Math.round(v * DRAG_POW) / DRAG_POW; }

/* Ширина полосы попадания по кривой. Одно число на весь калькулятор: по нему
   же считает допуск проверка, и второй копии рядом быть не должно. */
const CURVE_HIT_PX = 16;

/* ⚠️ КРИВЫЕ МЫШЬЮ НЕ ДВИГАЮТСЯ НИГДЕ (решение владельца 20.08).

   Дословно: «на графике нельзя двигать функции графически мышкой». Это отмена
   прежнего «варианта Б» (тянуть можно, но формула переписывается вместе с
   кривой) — тот записан в карточке решений 19.08 и больше не действует.

   Кривая — это спрос, предложение, MR, MC, ATC, КПВ, КТВ, линия уровня,
   вписанная человеком функция: всё, что задано формулой. Формулу правят в
   строке ввода, и второго способа задать её у продукта нет.

   МАНИПУЛЯТОРЫ СЦЕНЫ ЭТО ПРАВИЛО НЕ ТРОГАЕТ. Точка клина налога t, линия
   потолка цены, минимальная зарплата, мировая цена Pw и им подобные задают
   СЮЖЕТ модели, а не функцию; они по-прежнему тянутся, и курсор у них grab.
   Их рисуют сами сцены, мимо этой функции.

   Полоса попадания остаётся: ею щёлкают, чтобы взвести ключевые точки
   (п. 21 ревью). Меняется только то, что она больше не работает ручкой, и
   курсор над ней больше не обещает перетаскивания.

   Ниже — прежние условия. Они теперь недостижимы: код перезаписи формулы при
   перетаскивании (setCurveFreeTerm, attachDrag) остался мёртвым и ждёт
   отдельного решения о судьбе — карточка в Notion. Удалять его вслепую в этой
   сессии нельзя: на нём же держатся ползунки сдвига кривых в правой панели. */
const CURVE_MOUSE_DRAG = false;

/* Можно ли тянуть ИМЕННО ЭТУ кривую мышью. Отдельно от «можно щёлкнуть»:
   см. разбор в drawCurves. Условия читаются сверху вниз, от общего к частному. */
function curveDraggable(curve) {
  if (!CURVE_MOUSE_DRAG) return false;         // решение владельца 20.08, см. выше
  if (!curve || !curve.linear) return false;   // нелинейные не тянутся вовсе
  if (!curveDragAllowed()) return false;       // сцена не двигает кривые вовсе
  if (NO_MOUSE_DRAG.indexOf(STATE.sceneKey) >= 0) return false;   // сцена запретила мышь
  if (canvasArmed()) return false;             // сейчас на холсте ставят точку
  /* Формулу вписал человек — не тянем. Решение владельца: обычная функция
     вида «x» не подразумевает изменения себя на графике. Полоса попадания при
     этом остаётся, и щелчком такая кривая по-прежнему взводится. */
  if (curve.handTyped) return false;
  /* ⚠️ КРИВАЯ С БУКВОЙ-ПАРАМЕТРОМ НЕ ТЯНЕТСЯ, И ЭТО НЕ ПРИДИРКА.
     Правило владельца: значение параметра меняется ТОЛЬКО ползунком и вводом
     числа рядом с ним, никак иначе. Но разбор прямой (detectLinear) подставляет
     в коэффициенты текущие значения букв, а перезапись формулы печатает их
     числами: «100 - a*Q», утянутая мышью, стала бы «95.5 - 2*Q» — параметр
     исчез бы вместе с ползунком. Сдвинуть свободный член, сохранив букву,
     значит вести вторую запись формулы рядом с первой, и они разъедутся.
     Поэтому такая кривая только щёлкается. На практике случай пустой: формулы
     с буквами человек вписывает сам, а вписанные и так не тянутся. */
  if (typeof curveParamNames === 'function' && curveParamNames(curve).length) return false;
  return true;
}
// Сдвиг линейной кривой по вертикали: меняем свободный член b (наклон a сохраняется),
// обновляем подпись и перерисовываем. ЕДИНАЯ точка для перетаскивания мышью И для
// ползунка-слайдера в пульте — никакой параллельной математики.
function setCurveFreeTerm(curve, b) {
  if (!curve || !curve.linear) return;
  /* ⚠️ ДВИЖОК ХРАНИТ РОВНО ТО ЧИСЛО, ЧТО НАПИСАНО В ФОРМУЛЕ (п. 3).
     Формула собирается ниже через fmtLinear, а он печатает два знака. Пока
     сюда приходило сырое 85.2247, на экране стояло «85.22 - Q», а считалось
     по 85.2247 — то есть у одной величины было два значения, и какое из них
     правда, по экрану узнать было нельзя. Перетаскивание с точностью до сотой
     ничего не теряет: пиксель холста и так крупнее. */
  /* ⚠️ ЗАПИСЬ ФУНКЦИИ НЕ ИМЕЕТ ПРАВА ВРАТЬ (главный пункт ревью 19.08).
     Панель утверждала «y = x», холст рисовал «y = x − 1,7», и оба считали себя
     правыми. Число в формуле и число в расчёте — одно и то же число, поэтому
     округление делается ОДИН раз, здесь, и той же глубины, какой печатается
     ниже. Глубина три знака: решение владельца. */
  curve.linear.b = roundDrag(b);
  b = curve.linear.b;
  if (curve.srcForm === 'QP') {
    // Кривая введена как Q(P) — показываем её в ТОЙ ЖЕ форме (Фаза 1б).
    // P = a·Q + b  ⟺  Q = (−b/a) + (1/a)·P; канон curve.linear уже обновлён выше.
    const a = curve.linear.a;
    curve.srcLinear = { c: -b / a, d: 1 / a };
    curve.srcExpr = curve.expr = curve.name = fmtLinear(1 / a, -b / a, 'P', DRAG_DECIMALS);
  } else {
    curve.expr = curve.name = fmtLinear(curve.linear.a, curve.linear.b, 'Q', DRAG_DECIMALS);
  }
  /* Кривую перерисовывает не только холст: строка «Построения графиков» живёт
     своим списком, и без этого прохода в поле оставалась бы прежняя запись —
     то есть ровно тот дефект, ради которого фаза и затевалась. */
  if (typeof renderGraphRows === 'function' && document.getElementById('graph-rows'))
    renderGraphRows();
  if (STATE.mode === 'labor') _wantRangeAnim = true;   // труд авто-масштабируется → плавно (Фаза 4)
  redrawAll();        // перерисуем кривую и всё зависимое (равновесие/области)
  renderCurveList();  // обновим формулу в списке кривых (и слайдеры пульта — в конце renderCurveList)
}

/* п. 24. ПОРОГ СМЕЩЕНИЯ. Щелчок это не перетаскивание.

   Дорожка захвата шириной 16 px лежит поверх кривой, и любое нажатие внутри
   неё d3 считает началом перетаскивания. Мышь во время обычного щелчка
   съезжает на пиксель-другой, событие всё равно приходит, и модель меняется:
   два щелчка мимо превращали «100 - Q» в «99.5 - Q», а «Q» в «Q + 0.17». Числа при
   этом становятся нечитаемыми, а человек уверен, что ничего не трогал. Поэтому
   кривая стоит, пока указатель не ушёл от места нажатия дальше порога;
   после этого перетаскивание идёт как раньше, до отпускания. */
const CURVE_DRAG_MIN_PX = 5;

function attachDrag(sel, curve) {
  let live = false, x0 = 0, y0 = 0;
  sel.call(d3.drag()
    .container(() => svg.node())   // координаты события — в пикселях SVG
    .on('start', (event) => { live = false; x0 = event.x; y0 = event.y; })
    .on('drag', (event) => {
      if (!live) {
        if (Math.hypot(event.x - x0, event.y - y0) < CURVE_DRAG_MIN_PX) return;
        live = true;
        // Снимок берётся один раз за жест, а не на каждый кадр: иначе двадцать
        // шагов отмены съедало бы одно протягивание мыши.
        pushUndo();
      }
      const [q, p] = toData(event.x, event.y);
      // Прямая проходит через курсор с прежним наклоном -> пересчитываем b тем же путём.
      setCurveFreeTerm(curve, p - curve.linear.a * q);
    })
    .on('end', () => { live = false; }));
}
// TODO (будущие шаги): перетаскивание нелинейных кривых (парабол и т.п.).

