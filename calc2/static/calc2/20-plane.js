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

/* Запас левого поля под подпись координаты (см. разбор в fitMargins). */
const COORD_LABEL_PAD = 24;

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
  /* 8 px отступа подписи от оси (её ставит drawAxes) + 6 px запаса у края,
     плюс запас под ПОДПИСЬ КООРДИНАТЫ. У неё, в отличие от деления шкалы,
     бывают дробная часть и индекс различителя: деление «80» занимает 16 px, а
     подпись «54,55_b» — 40. Без этого запаса подпись не помещалась в поле, и
     общий haloText разворачивал её ВНУТРЬ первой четверти, поверх поля
     построения, — ровно то, на что жаловался владелец («65_min» на линии МРОТ).
     Число подобрано замером живых подписей по всем сценам, а не на глаз:
     scripts/calc2_coordlabel_probe.js считает, сколько подписей залезло правее
     оси, и при этом запасе их ноль. */
  m.left = Math.max(30, Math.min(120, Math.ceil(wide) + 14 + COORD_LABEL_PAD));

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
  /* Обычная сцена — одна панель на весь холст, и её шкалы это и есть sx/sy.
     Регистрируем прямо здесь: makeScales зовут все сцены без своей геометрии,
     и держать список «кто должен зарегистрироваться» пришлось бы вручную. */
  registerPanel('main', sx, sy, {
    x0: m.left, y0: m.top, x1: W - m.right, y1: H - m.bottom,
  });
}

/* ---------------------------------------------------------------------
   РЕЕСТР ПАНЕЛЕЙ
   --------------------------------------------------------------------- */
/* ⚠️ СЛОЙ ПОВЕРХ СЦЕНЫ ЖИВЁТ В ПАНЕЛИ, А НЕ В ГЛОБАЛЬНЫХ ГРАНИЦАХ.

   `mainScales()` строил свои шкалы из CONFIG.Qmin/Qmax на всю ширину холста.
   Сделано это было нарочно — чтобы не брать глобальные sx/sy, в которых у
   многопанельных сцен остаётся шкала ПОСЛЕДНЕЙ панели. Лечение вышло хуже
   болезни: слой перестал совпадать НИ С ОДНОЙ панелью. В «Неравенстве
   доходов» кривая Лоренца рисуется в квадрате 0…100, а вершины площадей и
   ключевые точки считались по шкале на всю ширину — отклонение по X около
   54 px, и оно росло при зуме. В сюжете про производную площадь натягивалась
   полигоном между верхним и нижним графиком, а на нижнем мышь липла к f(x),
   которой там нет.

   Панель — это прямоугольный кусок холста со своими шкалами. Сцена объявляет
   свои панели сама, сразу после того, как построила шкалы. Точка, вершина и
   посчитанная площадь помнят, в какой панели их поставили, и рисуются по её
   шкалам. Второго механизма «границы кадра» заводить нельзя. */
/* Сцена, у которой геометрия своя, объявляет об этом ОДНОЙ строкой: сначала
   гасит то, что успел зарегистрировать makeScales, потом заводит свои панели.
   Без этого 'main' на весь холст остался бы рядом с квадратом Лоренца и с
   панелями производной, и панель под курсором выбиралась бы наугад. */
function clearPanels() { STATE.panels = []; }

function registerPanel(id, mx, my, rect) {
  const r = rect || {};
  const p = {
    id: String(id),
    mx, my,
    x0: Math.min(r.x0, r.x1), x1: Math.max(r.x0, r.x1),
    y0: Math.min(r.y0, r.y1), y1: Math.max(r.y0, r.y1),
  };
  if (!Array.isArray(STATE.panels)) STATE.panels = [];
  // Перерисовка в один кадр бывает вложенной (сцена зовёт makeScales дважды);
  // панель с тем же id заменяем, а не копим дубли.
  const i = STATE.panels.findIndex(o => o.id === p.id);
  if (i >= 0) STATE.panels[i] = p; else STATE.panels.push(p);
  return p;
}

// Расстояние от пикселя до прямоугольника панели (0 — внутри).
function panelDist(p, px, py) {
  const dx = Math.max(p.x0 - px, 0, px - p.x1);
  const dy = Math.max(p.y0 - py, 0, py - p.y1);
  return Math.hypot(dx, dy);
}

/* Панель под пикселем. Мимо всех прямоугольников — ближайшая: курсор в поле
   холста (там же оси и подписи) обязан вести себя как курсор в панели, иначе
   постановка точки у самой оси уходила бы в чужие шкалы. */
function panelAt(px, py) {
  const list = STATE.panels || [];
  if (!list.length) return null;
  let best = null, bd = Infinity;
  list.forEach(p => {
    const d = panelDist(p, px, py);
    if (d < bd) { bd = d; best = p; }
  });
  return best;
}

// Панель под последней известной позицией курсора; курсора не было — первая.
function activePanel() {
  const list = STATE.panels || [];
  if (!list.length) return null;
  if (STATE.pointerPx == null || STATE.pointerPy == null) return list[0];
  return panelAt(STATE.pointerPx, STATE.pointerPy) || list[0];
}

// Панель по id (для точек и вершин, помнящих свою). Нет такой — активная.
function panelById(id) {
  const list = STATE.panels || [];
  if (!id) return activePanel();
  return list.find(p => p.id === id) || activePanel();
}

/* ── ОКНО ПАНЕЛИ, ВЫБРАННОЕ ЧЕЛОВЕКОМ ─────────────────────────────────
   Колесо и перетаскивание фона меняют окно ТОЙ панели, над которой курсор.
   У панели со своими границами (мини-рынок, квадрат Лоренца) окно считает
   сама сцена — по своим кривым. Как только человек покрутил колесо, окно
   становится ЕГО, и сцена больше его не пересчитывает: то же правило, что у
   `STATE.zoomLock` для главной панели.

   ⚠️ Живёт это в STATE, а не в записи панели: записи пересобираются на каждой
   перерисовке, а выбор человека обязан её пережить. */
function panelWin(id, x0, x1, y0, y1) {
  const st = STATE.panelWin || (STATE.panelWin = {});
  return st[id] || { x0, x1, y0, y1 };
}
function resetPanelWins() { STATE.panelWin = {}; }

/* Приблизить окно панели к точке (px, py). Возвращает false, если панели нет
   или окно выродилось — тогда жест просто ничего не делает.
   ⚠️ КВАДРАТ ЛОРЕНЦА ОСТАЁТСЯ КВАДРАТОМ: обе оси умножаются на ОДИН и тот же
   множитель, поэтому равные размахи остаются равными сами собой. Оси там
   несут проценты, и растянуть одну без другой значит соврать про смысл
   картинки. */
function panelZoomBy(id, factor, px, py) {
  const p = (STATE.panels || []).find(q => q.id === id);
  if (!p || !isFinite(factor) || factor <= 0) return false;
  const [x0, x1] = p.mx.domain(), [y0, y1] = p.my.domain();
  const w = Math.max(1, p.x1 - p.x0), h = Math.max(1, p.y1 - p.y0);
  const tx = Math.min(1, Math.max(0, (px - p.x0) / w));
  const ty = Math.min(1, Math.max(0, (py - p.y0) / h));
  const xc = x0 + (x1 - x0) * tx, yc = y1 - (y1 - y0) * ty;
  const nx0 = xc - (xc - x0) * factor, nx1 = xc + (x1 - xc) * factor;
  const ny0 = yc - (yc - y0) * factor, ny1 = yc + (y1 - yc) * factor;
  if (!((nx1 - nx0) > 1e-9) || !((ny1 - ny0) > 1e-9)) return false;
  if (!isFinite(nx0) || !isFinite(nx1) || !isFinite(ny0) || !isFinite(ny1)) return false;
  (STATE.panelWin || (STATE.panelWin = {}))[id] = { x0: nx0, x1: nx1, y0: ny0, y1: ny1 };
  return true;
}

// Сдвинуть окно панели на столько единиц, на сколько уехал курсор.
function panelPanBy(id, dxPx, dyPx) {
  const p = (STATE.panels || []).find(q => q.id === id);
  if (!p) return false;
  const [x0, x1] = p.mx.domain(), [y0, y1] = p.my.domain();
  const w = Math.max(1, p.x1 - p.x0), h = Math.max(1, p.y1 - p.y0);
  const dx = (x1 - x0) * dxPx / w, dy = (y1 - y0) * dyPx / h;
  (STATE.panelWin || (STATE.panelWin = {}))[id] =
    { x0: x0 - dx, x1: x1 - dx, y0: y0 + dy, y1: y1 + dy };
  return true;
}

/* Панель, окном которой распоряжается ЖЕСТ, а не сцена. У 'main' окном
   по-прежнему распоряжаются CONFIG.Qmax/Pmax, у панелей производной — их
   собственный, давно написанный механизм tanWin. Остальные ходят сюда. */
function gesturePanelId(px, py) {
  const p = panelAt(px, py);
  if (!p || p.id === 'main') return null;
  if (p.id === 'deriv-top' || p.id === 'deriv-bottom') return null;
  return p.id;
}

/* ⚠️ ДВЕ РАЗНЫЕ ВЕЩИ, КОТОРЫЕ РАНЬШЕ БЫЛИ ОДНИМ ФЛАГОМ.

   До 24.08 `STATE.firstQuad` делал две работы сразу: он был и «сцена
   экономическая», и «показывать только первую четверть». Из-за этого правило
   первой четверти выключалось ровно тогда, когда его результат становился
   виден: при снятой галочке оси уезжали в минус, а кривая спроса 100 − Q
   уходила за ось Q на 160 точек пути (замер набора Г).

   По решению владельца «правило первой четверти действует всегда в
   экономических сценах» вещи разведены:

     • isEconScene() — СВОЙСТВО СЦЕНЫ, человек его не переключает. Экономическая
       кривая существует только при P ≥ 0 и Q ≥ 0. Исключения (предельные
       кривые, центр поворота, пересечение вне четверти) рисуются пунктиром
       каждое своим кодом и через econLo не проходят.
     • STATE.firstQuad — ГАЛОЧКА «только первая четверть». Управляет ТОЛЬКО
       осями, сеткой, границами плоскости и clip-path холста. На то, где
       существует кривая, не влияет.

   В «Математике» и в построении графиков кривая — это функция, а не экономика:
   там правило не действует, и отрицательные значения строятся как раньше. */
function isEconScene() { return STATE.mode !== 'math' && STATE.mode !== 'graph'; }

/* Нижняя граница ЭКОНОМИКИ по оси: в экономической сцене всё, что левее и ниже
   нуля, не существует. От галочки не зависит — см. блок выше. Одна функция на
   весь движок, чтобы обрезка кривых, поиск пересечений и прокатывание точки не
   разошлись между собой. */
function econLo(v) { return isEconScene() ? Math.max(0, v) : v; }

/* Нижняя граница ВИДА (окно, сетка, clip-path холста). Это про галочку: сняли
   её — показываем настоящую границу окна, включая отрицательную часть плана. */
function quadLo(v) { return STATE.firstQuad ? Math.max(0, v) : v; }

/* ⚠️ ЦЕНА КРИВОЙ В ПЕРВОЙ ЧЕТВЕРТИ: ниже нуля читается как ноль.

   Обратная функция предложения Q − 100 при Q < 100 отрицательна. Формально
   это «цена, за которую продавец готов отдать сотую единицу», но продавец не
   доплачивает покупателю за то, что тот забрал товар: минимальная цена, при
   которой он выйдет на рынок, равна нулю. Готовность платить у покупателя —
   тем же: ниже нуля она не бывает.

   Пока этого правила не было, излишек продавца считался ПО ВСЕЙ площади до
   отрицательных цен: замер 24.08 давал PS первой группы 7 688 вместо 2 688 —
   ровно на пять тысяч больше, то есть на треугольник под осью Q.

   ⚠️ ОДНА ФУНКЦИЯ НА ВЕСЬ ДВИЖОК, И ЧИСЛО С ЗАЛИВКОЙ СЧИТАЮТСЯ ЕЮ ОБА.
   Число и закрашенная область — это одна и та же площадь, увиденная двумя
   способами. Стоит посчитать их по разным правилам, и на экране появляется
   заливка, которая не соответствует подписанному под ней числу — владелец
   именно это и увидел («PS показывается неправильно» рядом с «PS = NaN»).

   Галочкой «только первая четверть» правило НЕ управляется: это экономика, а
   не вид на плоскость. Отрицательных цен не бывает независимо от того, какую
   часть плоскости человек сейчас показывает. */
function quadPrice(curve, q) {
  const v = evalCurve(curve, q);
  return isNaN(v) ? NaN : Math.max(0, v);
}

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

  /* ⚠️ ТО ЖЕ ОКНО ПЛЮС ПОЛОВИНА ТОЛЩИНЫ ЛИНИИ СНИЗУ.
     Линия, идущая ровно по нижней границе окна, теряет ровно половину своей
     толщины: обрезка режет по оси, а штрих у пути рисуется в обе стороны от
     неё. Замер 25.08: пунктирный участок суммарного предложения при Q от 0 до
     100 объявлен толщиной 3,2, а на экране от него оставался ОДИН ряд
     пикселей — то есть выглядел он вчетверо тоньше сплошной части той же
     кривой, хотя решение владельца требует ровно ту же толщину.

     Этим окном пользуется ТОЛЬКО такая линия. Соврать оно не может: за
     границу выходит не кривая, а её собственный штрих, и всего на полтора
     пикселя. Обычные кривые по-прежнему режутся по оси — правило первой
     четверти этим не трогается. */
  const lip = (typeof LW === 'object' ? LW.bold : 3.2) / 2 + 0.5;
  defs.append('clipPath').attr('id', 'plot-clip-lip').append('rect')
    .attr('x', x0).attr('y', y1)
    .attr('width', Math.max(0, x1 - x0))
    .attr('height', Math.max(0, y0 - y1) + lip);

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

/* ── ЧИСЛО ТОЧКИ НА ОСИ (фаза 5 ревью 19.08) ──────────────────────────────

   Решение владельца: значения координат уходят ЗА оси. Цена — левее оси цены,
   количество — ниже оси количества, внутри поля построения подписей координат
   не остаётся вовсе. Имя оси при этом не повторяется: вместо «P*=50» на оси
   стоит просто «50» — какая это ось, написано у её стрелки.

   ⚠️ ПОЧЕМУ ЭТО ЗАОДНО ЧИНИТ РАСПОЛОЖЕНИЕ, А НЕ ТОЛЬКО ТЕКСТ. Замер до правки:
   поле построения по горизонтали 32…816, а подпись «P∗=50» лежала на 32…69,
   то есть внутри поля, поверх сетки и заливок. Причина не в том, что её туда
   поставили: haloText разворачивает подпись внутрь графика, когда она не
   влезает в поле слева, а «P∗=50» шириной 37 px в поля шириной 32 px не
   влезала никогда. Оставшись одним числом, подпись становится не шире деления
   шкалы — и спокойно встаёт туда же, где стоят деления.

   Различитель сохраняется. Там, где на одной оси стоят две РАЗНЫЕ величины
   (цена покупателя и цена продавца в потоварном налоге), имя оси снимается, а
   индекс остаётся и переезжает за ось вместе с числом: иначе на оси окажутся
   голые «60» и «40», и различить их станет нечем.

   Совпало с делением шкалы — ДЕЛЕНИЕ УСТУПАЕТ МЕСТО: серое число шкалы
   убирается, на его месте печатается число точки акцентным цветом и жирным.
   Двух чисел друг на друге не остаётся. */

/* Убрать деление шкалы, стоящее ровно там, где сейчас встанет число точки.
   Деления рисует drawAxes ДО сцены, поэтому к этому моменту они уже в
   разметке и их можно просто снять. Ищем среди своих же подписей делений
   (класс axis-num), а не среди всех текстов холста. */
function dropTickAt(coord, horizontal) {
  if (!svg || !svg.node()) return false;
  let hit = false;
  svg.selectAll('text.axis-num').each(function () {
    const v = parseFloat(this.getAttribute(horizontal ? 'x' : 'y'));
    if (!isFinite(v) || Math.abs(v - coord) > 7) return;
    this.remove();
    hit = true;
  });
  return hit;
}

/* ⚠️ ЗНАЧЕНИЕ ПРИХОДИТ СЮДА И ЧИСЛОМ, И УЖЕ НАБРАННОЙ СТРОКОЙ.

   Из пятидесяти с лишним мест вызова почти все пишут `axisValueY(g, ox, py,
   fmt(P), 'b')` — то есть отдают готовую строку, а не число. Пока на входе
   стояла проверка `!isFinite(value)`, это работало ТОЛЬКО для целых: `fmt(40)`
   даёт «40», и `isFinite('40')` — правда, а `fmt(54.5454)` даёт «54,55», и
   `isFinite('54,55')` — ложь, потому что десятичный разделитель у нас запятая.
   Функция молча возвращала null, и подписи координат пропадали ЦЕЛИКОМ у любой
   дробной величины: в «Процентных налогах» пунктиры вели к осям и упирались в
   пустоту при значениях по умолчанию.

   Правило показа теперь одно: подпись выводится ВСЕГДА. «Деление уступает
   место» — это разрешение столкновения, а не условие показа. Число нужно
   отдельно, только чтобы проверить совпадение с делением; не разобралось —
   столкновения просто не ищем, но подпись рисуем. */
function coordValue(value) {
  if (typeof value === 'number') return isFinite(value) ? { text: fmt(value), num: value } : null;
  const s = String(value == null ? '' : value).trim();
  if (!s) return null;
  // Разбираем обратно нашу же запись: узкий неразрывный пробел разрядов и запятая.
  const num = parseFloat(s.replace(/[\s\u202f\u00a0]/g, '').replace(',', '.'));
  return { text: s, num: num };
}

/* Число точки под осью количества. `oy` — пиксель самой оси, `idx` — индекс
   различителя ('b', 's', '1', 'спрос'…) или пустая строка. */
/* ⚠️ ОДНО МЕСТО — ОДНО ЧИСЛО. Две точки, сошедшиеся в одну, печатают свою
   координату каждая, и на оси встаёт «50» поверх «50»: в «Эластичности»
   равновесие и точка единичной эластичности сходятся при исходных формулах, в
   разложении Слуцкого — старый и компенсированный наборы. Читается это как
   опечатка, а разводить такие подписи нельзя: они и должны стоять там, где
   стоят, потому что это одно и то же число.

   Проверка живёт ЗДЕСЬ, в общей точке печати координат, а не в сценах: сцены
   не знают друг о друге, а второй такой же проверки рядом быть не должно. */
function coordAlreadyAt(px, horiz, text) {
  let found = false;
  svg.selectAll('text.coord-num').each(function () {
    if (found) return;
    if ((this.getAttribute('data-raw') || this.textContent || '').trim() !== String(text).trim()) return;
    const at = horiz ? +this.getAttribute('x') : +this.getAttribute('y');
    if (isFinite(at) && Math.abs(at - px) < 6) found = true;
  });
  return found;
}

/* ---------------------------------------------------------------------
   НАРИСОВАННЫЕ КЛЮЧЕВЫЕ ТОЧКИ
   --------------------------------------------------------------------- */
/* ⚠️ КЛЮЧЕВАЯ ТОЧКА — ЭТО ТО, ЧТО СЦЕНА НАРИСОВАЛА (решение владельца 01.09).

   Равновесие E, оптимум монополиста M, Qопт и Qрын, точка на границе квоты —
   всё это точки с пунктиром к обеим осям и числом на каждой оси. Раньше слой
   поверх сцены о них не знал вовсе: он считал только пересечения кривых.

   Список берётся У НАРИСОВАННОГО, а не у второй копии правила — тем же
   приёмом, что `offQuadShownPoints()` читает `data-marginal-tail` с холста
   ([ADR 0026]). Порядок вызовов это позволяет: `redrawScene()` рисует сцену
   целиком, и только потом `drawOverlays()` спрашивает ключевые точки.

   Помечать точки поштучно в тридцати с лишним местах не пришлось: число на
   оси печатают ровно два помощника, `axisValueX` и `axisValueY`, и сцены
   зовут их ПАРОЙ с одним и тем же различителем idx. Пара с обеими половинами
   и есть нарисованная точка. Имя ей даёт `pointName` — та самая буква, что
   стоит на холсте («E», «M»); её нет — имя собирается из различителя.

   ⚠️ Записывать намерение ДО отрисовки нельзя: сцена, вышедшая раньше срока,
   объявила бы точку, которой на экране нет. Поэтому запись идёт из самих
   помощников, в тот момент, когда они печатают. */
let _kpX = [], _kpY = [], _kpNames = [];
function resetDrawnKeyPoints() { _kpX = []; _kpY = []; _kpNames = []; }

// Панель, чьи шкалы сейчас лежат в глобальных sx/sy: их и печатают помощники.
function panelOfGlobalScales() {
  return (STATE.panels || []).find(p => p.mx === sx && p.my === sy) || null;
}

function kpNode(g) { return (g && g.node) ? g.node() : g; }

/* Пункт (б) собирается ПОСЛЕ отрисовки сцены, в один проход. Раньше пары
   искались по различителю `idx`, и это покрывало равновесие и оптимум
   монополиста, но не налог (одно Q на две цены), не потолок (одна цена на два
   Q) и не квоту. Пара ищется по ГЕОМЕТРИИ: угол (число на оси Q, число на оси
   P) считается точкой ровно тогда, когда из него выходит ПУНКТИР — то самое,
   по чему точку узнаёт и человек. Лишние углы (у монополии их два из четырёх)
   пунктира не имеют и отсеиваются сами. */
/* Пунктиры ищем по ВСЕМУ холсту, а не внутри одной группы: линию МРОТ и
   числа при ней печатают разные группы, и точка занятости иначе терялась.
   Сетку исключаем — её штрих не проекция точки, а фон.

   ⚠️ СПИСОК СЧИТАЕТСЯ ОДИН РАЗ НА КАДР. Раньше запрос по всему SVG уходил
   ВНУТРИ двойного цикла — на каждую пару «число на оси Q × число на оси P»,
   то есть до девяти раз за кадр по одному и тому же холсту. */
function collectDashes() {
  const out = [];
  try {
    svg.selectAll('line[stroke-dasharray]').each(function () {
      if ((this.getAttribute('class') || '').indexOf('grid') >= 0) return;
      out.push([+this.getAttribute('x1'), +this.getAttribute('y1'),
                +this.getAttribute('x2'), +this.getAttribute('y2')]);
    });
  } catch (e) { /* холста ещё нет — пунктиров тоже */ }
  return out;
}

/* ⚠️ ПУНКТИР ЗАСЧИТЫВАЕТСЯ ТОЛЬКО СВОЕЙ ПАНЕЛИ. В двухпанельной сцене штрих
   из соседней панели подтверждал бы угол в этой, стоило пикселям совпасть.
   Допуск 6 px нужен потому, что пунктир к оси упирается ровно в границу
   панели; расстояние между соседними панелями — десятки пикселей, так что
   перепутать их этот допуск не даёт. */
function dashEndsNear(dashes, px, py, rect) {
  const T = 6;
  const inside = (x, y) => !rect ||
    (x >= rect.x0 - T && x <= rect.x1 + T && y >= rect.y0 - T && y <= rect.y1 + T);
  for (let i = 0; i < dashes.length; i++) {
    const d = dashes[i];
    if (!inside(d[0], d[1]) || !inside(d[2], d[3])) continue;
    if (Math.hypot(d[0] - px, d[1] - py) <= 2 || Math.hypot(d[2] - px, d[3] - py) <= 2) return true;
  }
  return false;
}

function flushDrawnKeyPoints() {
  const fb = panelOfGlobalScales();
  const fid = fb ? fb.id : '';
  const dashes = collectDashes();
  /* ⚠️ УГОЛ СОСТАВЛЯЕТСЯ ИЗ ЧИСЕЛ ОДНОЙ ПАНЕЛИ. Числа помнят, где их
     напечатали; без панели — значит на общих осях, и хозяйку им отдаёт
     panelOfGlobalScales, как и раньше. Так мини-рынки объявляют свои точки
     наравне с общими осями, не заводя второго механизма. */
  const groups = new Map();
  const bag = (id) => { if (!groups.has(id)) groups.set(id, { x: [], y: [] }); return groups.get(id); };
  _kpX.forEach(a => bag(a.panel || fid).x.push(a));
  _kpY.forEach(b => bag(b.panel || fid).y.push(b));
  groups.forEach((grp, pid) => {
    const rect = (STATE.panels || []).find(p => p.id === pid) || null;
    const seen = [];
    grp.x.forEach(a => {
      grp.y.forEach(b => {
        if (!dashEndsNear(dashes, a.px, b.py, rect)) return;   // угол без пунктира — не точка
        if (seen.some(s => Math.abs(s[0] - a.px) <= 2 && Math.abs(s[1] - b.py) <= 2)) return;
        seen.push([a.px, b.py]);
        // Имя точки — буква, которую сцена написала рядом; нет буквы — по различителю.
        let nm = null, bd = 10;
        _kpNames.forEach(n => {
          const d = Math.hypot(n.px - a.px, n.py - b.py);
          if (d <= bd) { bd = d; nm = n.sym; }
        });
        if (!nm) {
          const qs = a.idx ? ('Q' + a.idx) : '', ps = b.idx ? ('P' + b.idx) : '';
          nm = (qs && ps) ? ('точка ' + qs + ' и ' + ps)
             : (qs || ps ? ('точка ' + (qs || ps)) : 'отмеченная точка');
        }
        d3.select(a.node).append('circle').attr('class', 'kp-mark')
          .attr('cx', a.px).attr('cy', b.py).attr('r', 0)
          .attr('fill', 'none').attr('pointer-events', 'none')
          .attr('data-skip-export', '1')
          .attr('data-key-point', nm)
          .attr('data-kp-x', a.x).attr('data-kp-y', b.y)
          .attr('data-kp-panel', pid);
      });
    });
  });
}

/* Объявление «на этой оси, в этом пикселе, напечатано это число». Зовут его
   ДВА печатника общих осей (axisValueX/axisValueY) и мини-рынок, который свои
   числа печатает сам — по причинам, записанным у него в коде. Это один
   механизм с параметром, а не второй рядом: список, поиск пар и правило
   пунктира общие. Панель нужна потому, что у мини-рынка свои шкалы. */
function noteAxisX(g, px, value, idx, panel) {
  const v = coordValue(value);
  if (v && isFinite(v.num)) _kpX.push({ node: kpNode(g), px, x: v.num, idx: String(idx || ''), panel: panel || '' });
  return v;
}
function noteAxisY(g, py, value, idx, panel) {
  const v = coordValue(value);
  if (v && isFinite(v.num)) _kpY.push({ node: kpNode(g), py, y: v.num, idx: String(idx || ''), panel: panel || '' });
  return v;
}

// Буква у точки — её настоящее имя на холсте («E», «M»).
function kpName(g, px, py, sym) {
  if (!sym || !isFinite(px) || !isFinite(py)) return;
  _kpNames.push({ node: kpNode(g), px, py, sym: String(sym) });
}

function axisValueX(g, px, oy, value, idx) {
  if (!isFinite(px)) return null;
  const v = noteAxisX(g, px, value, idx);
  if (!v) return null;
  const span = Math.abs(sx.domain()[1] - sx.domain()[0]);
  const onTick = xTicks().some(t => Math.abs(sx(t) - px) < 7) ||
                 (isFinite(v.num) && xTicks().some(t => Math.abs(t - v.num) < span * 0.02));
  if (coordAlreadyAt(px, true, axisValueText(v.text, idx))) return null;
  if (onTick) dropTickAt(px, true);
  const t = haloText(g, px, oy + 8, axisValueText(v.text, idx), 'middle', 'hanging');
  t.attr('class', 'coord-num');       // по этому классу их и считает проверка
  if (onTick) t.attr('fill', cssVar('--accent')).attr('font-weight', 700);
  return t;
}

/* Число точки левее оси цены. `ox` — пиксель самой оси.

   ⚠️ ПОДПИСЬ КООРДИНАТЫ НЕ ИМЕЕТ ПРАВА УЙТИ В ПЕРВУЮ ЧЕТВЕРТЬ. Общий haloText
   разворачивает не влезшую подпись ВНУТРЬ графика, и с узким левым полем (32 px)
   так уезжали все подписи с индексом: «60_b» и «40_s» в потоварном налоге вставали
   ПРАВЕЕ оси, поверх поля построения, а «65_min» на рынке труда ложилась прямо на
   линию МРОТ. Решение владельца 19.08 требует обратного: цена стоит левее оси цены.

   Поэтому здесь свой разворот, и он считается по НАСТОЯЩЕЙ ширине уже
   нарисованной подписи, а не по оценке «символов × 5,9». Оценка haloText
   считает индекс полноразмерным и завышает ширину «65_min» почти в полтора
   раза — по ней подпись «не влезала» там, где на самом деле влезает. */
function axisValueY(g, ox, py, value, idx) {
  if (!isFinite(py)) return null;
  const v = noteAxisY(g, py, value, idx);
  if (!v) return null;
  const span = Math.abs(sy.domain()[1] - sy.domain()[0]);
  const onTick = yTicks().some(t => Math.abs(sy(t) - py) < 7) ||
                 (isFinite(v.num) && yTicks().some(t => Math.abs(t - v.num) < span * 0.02));
  if (coordAlreadyAt(py, false, axisValueText(v.text, idx))) return null;
  if (onTick) dropTickAt(py, false);
  const t = haloText(g, ox - 8, py, axisValueText(v.text, idx), 'end', 'middle', { noFlip: true });
  t.attr('class', 'coord-num');
  /* Не поместившуюся подпись прижимает к краю холста ОТДЕЛЬНЫЙ ПРОХОД
     (`pinCoordLabels`), а не эта строка. Причина: здесь текст только что создан,
     размеры его ещё не посчитаны, и `getBBox` отвечает про пустой узел — пока
     проверка стояла тут, «31,72_ATC» в естественной монополии спокойно уезжала
     за левый край холста. Проход идёт вместе с разведением подписей, когда
     раскладка уже готова. */
  if (onTick) t.attr('fill', cssVar('--accent')).attr('font-weight', 700);
  return t;
}

/* Само число и, если он есть, индекс различителя нижним индексом. Разбор
   разметки подписей уже умеет «_», и в выгрузку он уходит тем же путём.
   На вход приходит УЖЕ НАБРАННОЕ число (см. coordValue): второй проход fmt
   по строке с запятой её бы испортил. */
function axisValueText(text, idx) {
  const n = String(text);
  if (!idx) return n;
  return String(idx).length > 1 ? (n + '_{' + idx + '}') : (n + '_' + idx);
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

