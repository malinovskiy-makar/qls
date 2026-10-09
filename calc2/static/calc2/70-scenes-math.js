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

// Шаг численного дифференцирования: доля ОТРЕЗКА ОТВЕТА, а не константа —
// иначе на отрезке 0..0.1 шаг «съест» всю картинку, а на 0..1000 потеряет точность.
// ⚠️ Не доля окна (ADR 0143): тогда приближение меняло бы f′(x₀) в «Ответе».
// Отрезок на кадр один (_ansSeg ставит перерисовка); до первой перерисовки — окно.
function mathH() {
  const s = _ansSeg;
  const w = s ? (s.b - s.a) : (STATE.mathXmax - STATE.mathXmin);
  return Math.max(1e-6, w * 1e-4);
}
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
  /* Локальные экстремумы — те же, что в «Ответе» любой модели (ansAnalyse):
     смена знака производной внутри отрезка. Прежняя проверка знаком второй
     производной объявляла «плато» узел, где f′ = 0 без смены знака. */
  const an = ansAnalyse(f, lo, hi);
  const ext = an.max.concat(an.min).sort((a, b) => a.x - b.x);
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

/* ── ОТРЕЗОК ОТВЕТА (ADR 0143) ──────────────────────────────────────────
   Корни, экстремумы и пересечения «Математики» и «Построения графиков»
   считаются на ОТРЕЗКЕ ОТВЕТА, а не в окне: ответ — свойство функции, а не
   кадра (то же правило, что ADR 0020 для экономики). Окно решает только, что
   нарисовано; приближение и сдвиг на ответ не влияют.
   Отрезок — вход модели (STATE.ansA/ansB/ansHand): его задаёт человек в
   «Условии», а пока не задал, он подобран по формуле (autoAnswerSeg) и идёт за
   ней при каждой её смене. */
const ANS_AUTO_SPAN = 100;     // подбор по формуле перебирает [−100; 100]
const ANS_AUTO_N = 1000;       // шаг 0,2: подбору хватает, ответ считается гуще
const ANS_N = 1200;            // сетка на самом отрезке ответа
const ANS_MAX_KEYS = 12;       // ключевых точек больше — функция периодическая
// Пробные x для подписи функции: совпали значения — функция та же (кэш).
const ANS_PROBE = [-7.31, -2.17, -0.53, 0.37, 1.13, 2.71, 4.49, 9.07];
let _ansSeg = null;            // отрезок текущего кадра (ставит refreshAnswerSeg)
const _ansCache = new Map();

/* Число ответа: запятая, настоящий минус, ТРИ знака после запятой (лишние
   нули срезаются). Корни и вершины — иррациональные числа, и двух знаков
   общего fmt мало, чтобы сверить свой ответ: «1,73» и «1,74» оба верны в
   пределах сотой. Так записаны и контрольные числа «Математики» (−1,732). */
function ansFmt(v) {
  if (!isFinite(v)) return String(v);
  let r = Math.round(v * 1000) / 1000;
  if (r === 0) r = 0;                       // −0 не печатаем
  const a = Math.abs(r), whole = Math.floor(a);
  let s = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, NBTHIN);
  const frac = String(Math.round((a - whole) * 1000)).padStart(3, '0').replace(/0+$/, '');
  if (frac) s += ',' + frac;
  return (r < 0 ? '−' : '') + s;
}
function ansPt(x, y) { return '(' + ansFmt(x) + '; ' + ansFmt(y) + ')'; }
// Несколько значений — через «; », нет ни одного — «нет» (решение владельца 09.10).
function ansList(xs) { return xs.length ? xs.map(v => ansFmt(v)).join('; ') : 'нет'; }
function ansPts(ps) { return ps.length ? ps.map(p => ansPt(p.x, p.y)).join('; ') : 'нет'; }

function fnSig(f) {
  return ANS_PROBE.map(x => { let v; try { v = f(x); } catch (e) { v = NaN; } return isFinite(v) ? v.toPrecision(12) : 'n'; }).join(',');
}
function ansCached(key, make) {
  if (_ansCache.has(key)) return _ansCache.get(key);
  if (_ansCache.size > 60) _ansCache.clear();
  const v = make();
  _ansCache.set(key, v);
  return v;
}

/* Нули на отрезке: смена знака и бисекция (rootsOf). Отсеиваются полюса и
   скачки через ноль (у 1/x знак меняется в нуле, а корня нет: значение в
   найденной точке не мало рядом с соседями) и участки, где функция равна
   нулю целиком (совпадение кривых — не точка пересечения). */
function ansZeros(f, lo, hi, N) {
  const d = (hi - lo) / N / 2;
  return rootsOf(f, lo, hi, N).filter(x => {
    const y = f(x);
    if (!isFinite(y)) return false;
    const l = Math.abs(f(x - d)), r = Math.abs(f(x + d));
    const nb = Math.max(isFinite(l) ? l : 0, isFinite(r) ? r : 0);
    if (!(nb > 0)) return false;
    return Math.abs(y) <= 1e-6 * (1 + nb);
  });
}

/* Локальные экстремумы: производная меняет знак внутри отрезка; концы
   отрезка экстремумами не считаются. Вид — по знаку производной слева и
   справа, а не по второй производной: так ловится и излом (|x|, огибающая
   min/max), и не ловится плато (x³ в нуле). Полюс (1/x² в нуле) отсеивается
   скачком значения: у настоящей вершины соседние значения рядом. */
function ansExtrema(f, lo, hi, N) {
  const d = (hi - lo) / N / 2, h = Math.max(1e-9, (hi - lo) * 1e-5);
  const df = (x) => dNum(f, x, h);
  const out = [];
  rootsOf(df, lo, hi, N).forEach(x => {
    if (x <= lo + d || x >= hi - d) return;
    const y = f(x);
    if (!isFinite(y)) return;
    const l = df(x - d), r = df(x + d);
    const kind = (l > 0 && r < 0) ? 'max' : ((l < 0 && r > 0) ? 'min' : null);
    if (!kind) return;
    const yl = f(x - d), yr = f(x + d), yl2 = f(x - 2 * d), yr2 = f(x + 2 * d);
    const jump = Math.max(Math.abs(y - yl), Math.abs(y - yr));
    const ref = Math.max(Math.abs(yl - yl2), Math.abs(yr - yr2));
    if (!(jump <= 4 * ref + 1e-9 * (1 + Math.abs(y)))) return;
    out.push({ x, y, kind });
  });
  return out;
}

/* Всё, что «Ответ» знает об одной функции на отрезке: нули (вместе с
   касанием оси — у x² корень есть, а смены знака нет), локальные максимумы и
   минимумы, значение в нуле (если ноль на отрезке). Кэш по подписи функции и
   отрезку: кадр колеса пересчёта не стоит. */
function ansAnalyse(f, lo, hi, sig) {
  return ansCached('a|' + (sig || fnSig(f)) + '|' + lo + '|' + hi, () => {
    const ext = ansExtrema(f, lo, hi, ANS_N);
    const step = (hi - lo) / ANS_N;
    const zeros = ansZeros(f, lo, hi, ANS_N);
    ext.forEach(p => { if (Math.abs(p.y) <= 1e-8 && !zeros.some(z => Math.abs(z - p.x) < step)) zeros.push(p.x); });
    zeros.sort((a, b) => a - b);
    const v0 = (lo <= 0 && hi >= 0) ? f(0) : NaN;
    return {
      zeros,
      max: ext.filter(p => p.kind === 'max'),
      min: ext.filter(p => p.kind === 'min'),
      y0: isFinite(v0) ? v0 : null,
    };
  });
}

// Пересечения двух функций на отрезке: нули разности, точка — по первой.
function ansCrosses(f, g, lo, hi) {
  return ansZeros((x) => f(x) - g(x), lo, hi, ANS_N)
    .map(x => ({ x, y: f(x) })).filter(p => isFinite(p.y));
}

/* «Круглое» число 1, 2, 5 × 10ᵏ наружу: нижний край вниз, верхний вверх. */
function niceOut(v, up) {
  if (v === 0 || !isFinite(v)) return v;
  const a = Math.abs(v), grow = (up === (v > 0));     // от нуля или к нулю
  const k = Math.floor(Math.log10(a));
  const steps = [1, 2, 5, 10].map(m => m * Math.pow(10, k));
  const eps = a * 1e-9;
  const n = grow ? steps.find(s => s >= a - eps) : steps.slice().reverse().find(s => s <= a + eps);
  return Math.sign(v) * n;
}

/* Отрезок по формуле: ключевые точки на [−100; 100] — нули, локальные
   экстремумы, пересечение с осью y и пересечения кривых. Их не больше 12 —
   [min; max] с запасом max(1; 25 % размаха) с каждой стороны, не уже [−5; 5],
   края округлены наружу до круглых. Больше 12 (периодическая функция) — [−10; 10]. */
function autoAnswerSeg(keyFns, diffFns) {
  const L = -ANS_AUTO_SPAN, R = ANS_AUTO_SPAN, N = ANS_AUTO_N;
  const xs = [];
  const add = (x) => { if (isFinite(x) && !xs.some(v => Math.abs(v - x) < 1e-6)) xs.push(x); };
  keyFns.forEach(f => {
    ansZeros(f, L, R, N).forEach(add);
    ansExtrema(f, L, R, N).forEach(p => add(p.x));
    if (isFinite(f(0))) add(0);
  });
  diffFns.forEach(g => ansZeros(g, L, R, N).forEach(add));
  if (xs.length > ANS_MAX_KEYS) return { a: -10, b: 10 };
  if (!xs.length) return { a: -5, b: 5 };
  const lo = Math.min.apply(null, xs), hi = Math.max.apply(null, xs);
  const pad = Math.max(1, (hi - lo) * 0.25);
  return { a: Math.min(-5, niceOut(lo - pad, false)), b: Math.max(5, niceOut(hi + pad, true)) };
}

/* Функции, о которых говорит «Ответ» текущей модели: keyFns — у них нули,
   экстремумы и ось y; diffFns — у них нули это пересечения кривых. null —
   у модели отрезка ответа нет («С ограничением»: две переменные, область
   задаёт само ограничение) или формула не разобралась. */
function answerSpec() {
  if (STATE.mode === 'graph') {
    const fs = STATE.curves.filter(c => c.visible && !isVertical(c)).map(c => (x) => evalCurve(c, x));
    if (!fs.length) return null;
    const diff = [], pairs = [];
    for (let i = 0; i < fs.length; i++) for (let j = i + 1; j < fs.length; j++) {
      diff.push((x) => fs[i](x) - fs[j](x)); pairs.push([fs[i], fs[j]]);
    }
    return { keyFns: fs, diffFns: diff, pairs };
  }
  if (STATE.mode !== 'math' || STATE.mathSub === 'constraint') return null;
  const f = mathF();
  if (!f) return null;
  if (STATE.mathSub === 'transform') return { keyFns: [mathTransformed(f, STATE.mathTrans, paramValue('a', 1))], diffFns: [], pairs: [] };
  if (STATE.mathSub === 'minmax') {
    const mm = mmParts(f);
    if (mm.parts.length < 2) return { keyFns: [f], diffFns: [], pairs: [] };
    const diff = [], pairs = [];
    for (let i = 0; i < mm.parts.length; i++) for (let j = i + 1; j < mm.parts.length; j++) {
      const a = mm.parts[i].fn, b = mm.parts[j].fn;
      diff.push((x) => a(x) - b(x)); pairs.push([a, b]);
    }
    return { keyFns: [mm.z], diffFns: diff, pairs };
  }
  return { keyFns: [f], diffFns: [], pairs: [] };
}

/* Ключевые точки ответа на отрезке: нули, локальные экстремумы, пересечение
   с осью y, пересечения кривых. По ним строится окно (фаза 3, ADR 0143). */
function answerKeyPoints(spec, seg) {
  spec = spec || answerSpec();
  seg = seg || answerSeg();
  if (!spec) return [];
  const out = [];
  const add = (x, y) => { if (isFinite(x) && isFinite(y)) out.push({ x, y }); };
  spec.keyFns.forEach(f => {
    const r = ansAnalyse(f, seg.a, seg.b);
    r.zeros.forEach(x => add(x, 0));
    r.max.concat(r.min).forEach(p => add(p.x, p.y));
    if (r.y0 != null) add(0, r.y0);
  });
  (spec.pairs || []).forEach(([f, g]) => ansCrosses(f, g, seg.a, seg.b).forEach(p => add(p.x, p.y)));
  return out;
}

/* ОКНО ПО ФУНКЦИИ («Построение графиков»: старт, «Вписать», «Вернуть
   исходный вид»). Полный план, все четыре четверти:
     · по x — отрезок ответа; шире, если ключевая точка не помещается с запасом;
     · по y — ключевые точки, ноль (ось x видна) и основная масса значений
       кривых на этом отрезке (5–95 %: полюс 1/x не раздувает окно);
     · запас 10 % с каждой стороны: у любой ключевой точки до края ≥ 8 %.
   Кривых нет — привычные −10…10 по обеим осям. */
function graphFitWindow() {
  const spec = answerSpec();
  if (!spec) return { x0: -10, x1: 10, y0: -10, y1: 10 };
  const seg = answerSeg();
  const pts = answerKeyPoints(spec, seg);
  let x0 = seg.a, x1 = seg.b;
  for (let k = 0; k < 3; k++) {                  // ключевые точки по x — с запасом
    const m = (x1 - x0) * 0.1;
    pts.forEach(p => { x0 = Math.min(x0, p.x - m); x1 = Math.max(x1, p.x + m); });
  }
  const vals = [];
  spec.keyFns.forEach(f => {
    for (let i = 0; i <= 400; i++) { const v = f(x0 + (x1 - x0) * i / 400); if (isFinite(v)) vals.push(v); }
  });
  vals.sort((a, b) => a - b);
  const q = (t) => vals.length ? vals[Math.min(vals.length - 1, Math.max(0, Math.round(t * (vals.length - 1))))] : 0;
  let lo = Math.min(0, q(0.05)), hi = Math.max(0, q(0.95));
  pts.forEach(p => { lo = Math.min(lo, p.y); hi = Math.max(hi, p.y); });
  if (!(hi - lo > 1e-9)) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.1;
  let y0 = lo - pad, y1 = hi + pad;
  if (STATE.firstQuad) { x0 = Math.max(0, x0); y0 = Math.max(0, y0); }
  return { x0, x1, y0, y1 };
}

// Поставить окно «Построения графиков» ровно (старт и «Вписать»).
function setGraphWindow(w) {
  CONFIG.Qmin = w.x0; CONFIG.Qmax = w.x1; CONFIG.Pmin = w.y0; CONFIG.Pmax = w.y1;
  syncViewFields();
}
// Раздвинуть, но не сжать (правило ADR 0087): новая функция вышла за край —
// окно растёт до неё; окно, выбранное человеком (zoomLock), не трогаем.
function growGraphWindow() {
  if (STATE.zoomLock) return;
  const w = graphFitWindow();
  const n = { x0: Math.min(CONFIG.Qmin, w.x0), x1: Math.max(CONFIG.Qmax, w.x1),
              y0: Math.min(CONFIG.Pmin, w.y0), y1: Math.max(CONFIG.Pmax, w.y1) };
  if (n.x0 < CONFIG.Qmin - 1e-9 || n.x1 > CONFIG.Qmax + 1e-9 || n.y0 < CONFIG.Pmin - 1e-9 || n.y1 > CONFIG.Pmax + 1e-9) {
    setGraphWindow(n);
    redrawAll();
  }
}

// Отрезок ответа текущей модели: свой у человека или подобранный по формуле.
function answerSeg() {
  const a = +STATE.ansA, b = +STATE.ansB;
  if (STATE.ansHand && STATE.ansA != null && STATE.ansB != null && isFinite(a) && isFinite(b) && b > a) return { a, b, hand: true };
  const spec = answerSpec();
  if (!spec) return { a: -5, b: 5, hand: false };
  const sig = 's|' + spec.keyFns.map(fnSig).join('/') + '|' + spec.diffFns.map(fnSig).join('/');
  const s = ansCached(sig, () => autoAnswerSeg(spec.keyFns, spec.diffFns));
  return { a: s.a, b: s.b, hand: false };
}

/* Отрезок кадра: считается один раз в начале перерисовки модели и тут же
   показывается в строке «Ответ ищем на отрезке». */
function refreshAnswerSeg() {
  _ansSeg = answerSeg();
  syncAnsSegUI(_ansSeg);
  return _ansSeg;
}

// Запись числа в поле отрезка: запятая и настоящий минус, как в «Ответе».
function ansSegText(v) { return String(+(+v).toFixed(6)).replace('.', ',').replace(/^-/, '−'); }
function ansSegParse(t) {
  const s = String(t == null ? '' : t).replace(/[\s  ]+/g, '').replace(/[−–]/g, '-').replace(',', '.');
  if (!/^-?\d+(\.\d+)?$|^-?\.\d+$/.test(s)) return null;
  return parseFloat(s);
}

/* Строка «Ответ ищем на отрезке x от [ ] до [ ]» живёт под полями функций
   своего сюжета: в «Построении графиков» — под строками кривых, в «Функциях
   min и max» — под их полями, в остальных — под полем f(x). Узел один и
   переезжает; у «С ограничением» строки нет. */
function syncAnsSegUI(seg) {
  const row = document.getElementById('ans-seg-row');
  if (!row) return;
  const graph = (STATE.mode === 'graph');
  const show = graph || (STATE.mode === 'math' && STATE.mathSub !== 'constraint');
  const after = document.getElementById(graph ? 'graph-rows'
    : (STATE.mathSub === 'minmax' ? 'mm-rows' : 'math-error'));
  if (show && after && after.nextElementSibling !== row) after.after(row);
  if (row.style.display !== (show ? '' : 'none')) row.style.display = show ? '' : 'none';
  if (!show) return;
  [['ans-a', seg.a], ['ans-b', seg.b]].forEach(([id, v]) => {
    const e = document.getElementById(id);
    if (e && document.activeElement !== e) { const t = ansSegText(v); if (e.value !== t) e.value = t; }
  });
  const back = document.getElementById('ans-seg-auto');
  if (back) back.hidden = !seg.hand;
  // Ползунок точки касания ходит по отрезку ответа, а не по окну.
  if (STATE.mode === 'math' && STATE.mathSub === 'tangent') {
    const sl = document.getElementById('mathx0-slider');
    if (sl && (+sl.min !== seg.a || +sl.max !== seg.b)) {
      sl.min = seg.a; sl.max = seg.b; sl.step = (seg.b - seg.a) / 200; sl.value = STATE.mathX0;
    }
  }
}

/* Человек вписал границы. Пусто или «от ≥ до» — отрезок возвращается к
   подобранному по формуле, и об этом говорит короткая подсказка. */
function applyAnsSegInputs() {
  const a = ansSegParse((document.getElementById('ans-a') || {}).value);
  const b = ansSegParse((document.getElementById('ans-b') || {}).value);
  if (a == null || b == null || !(b > a)) {
    STATE.ansHand = false; STATE.ansA = null; STATE.ansB = null;
    if (typeof toast === 'function') toast(a == null || b == null
      ? 'Пустое поле: отрезок снова подобран по формуле'
      : '«От» должно быть меньше «до»: отрезок снова подобран по формуле');
  } else {
    STATE.ansHand = true; STATE.ansA = a; STATE.ansB = b;
  }
  redrawAll();
}
function resetAnsSegToAuto() {
  STATE.ansHand = false; STATE.ansA = null; STATE.ansB = null;
  redrawAll();
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
/* Оси полного плана. `opts.ticks === false` — сцена печатает деления сама.
   Так сделано в «Как определяется мировая цена»: у неё два поля со своими
   масштабами, деления она рисует ВНЕ обрезки (иначе их срезало бы), а эта
   функция печатала ВТОРОЙ комплект внутри обрезки — то есть невидимый.
   Замер Добавки А нашёл ровно эти 24 подписи-невидимки. */
function drawPlaneAxes(g, mx, my, xlab, ylab, opts) {
  const o = opts || {};
  const [px0, px1] = mx.range(), [py0, py1] = my.range();
  const ox = mx(0), oy = my(0);       // ось стоит в нуле и уезжает вместе с ним
  const seeY = ox >= px0 - 1 && ox <= px1 + 1;
  const seeX = oy >= py1 - 1 && oy <= py0 + 1;
  // Стрелка всегда на конце, смотрящем в сторону роста: вправо по x, вверх по y.
  if (seeX) g.append('line').attr('x1', px0).attr('y1', oy).attr('x2', px1).attr('y2', oy)
    .attr('stroke', COL.ink).attr('stroke-width', 1.4).attr('marker-end', 'url(#arrow)');
  if (seeY) g.append('line').attr('x1', ox).attr('y1', py0).attr('x2', ox).attr('y2', py1)
    .attr('stroke', COL.ink).attr('stroke-width', 1.4).attr('marker-end', 'url(#arrow)');
  if (seeX && o.ticks !== false) planeTicksX(g, mx, oy);
  if (seeY && o.ticks !== false) planeTicksY(g, my, ox);
  // Класс `axis-name` один на все режимы: по нему живут реестр обозначений,
  // общий проход размера подписей и проверка канона.
  if (xlab && seeX) g.append('text').attr('class', 'axis-name')
    .attr('x', px1 - 2).attr('y', oy - 7).attr('text-anchor', 'end')
    .attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.ink).text(xlab || 'x');
  if (ylab && seeY) g.append('text').attr('class', 'axis-name')
    .attr('x', ox + 7).attr('y', py1 + 11)
    .attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.ink).text(ylab || 'y');
}
function planeTicksX(g, mx, oy) {
  axisTicks(mx, 10, STATE.xStep).forEach(t => {
    if (Math.abs(t) < 1e-9) return;
    g.append('line').attr('x1', mx(t)).attr('y1', oy - 3).attr('x2', mx(t)).attr('y2', oy + 3)
      .attr('stroke', COL.ink).attr('stroke-width', 1);
    /* ⚠️ КЛАСС `axis-num` — ЭТО НЕ УКРАШЕНИЕ, А ПРИЗНАК «ЭТО ДЕЛЕНИЕ ШКАЛЫ».
       По нему работают три разные вещи: `dropTickAt` снимает деление, на место
       которого встаёт подпись координаты; `applyLabelSize` НЕ увеличивает
       деления вместе с прочими подписями; выгрузка отличает шкалу от подписи.
       У полного плана свой рисователь осей, и он этот класс не ставил вовсе —
       в «Деформациях графика» деления выглядели так же, а вели себя иначе. */
    g.append('text').attr('x', mx(t)).attr('y', oy + 7).attr('class', 'axis-num')
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'hanging')
      .attr('font-size', FS.small).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.2).text(fmt(t));
  });
}
function planeTicksY(g, my, ox) {
  axisTicks(my, 8, STATE.yStep).forEach(t => {
    if (Math.abs(t) < 1e-9) return;
    g.append('line').attr('x1', ox - 3).attr('y1', my(t)).attr('x2', ox + 3).attr('y2', my(t))
      .attr('stroke', COL.ink).attr('stroke-width', 1);
    g.append('text').attr('x', ox - 6).attr('y', my(t)).attr('class', 'axis-num')
      .attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
      .attr('font-size', FS.small).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.2).text(fmt(t));
  });
}

/* Запись для .tex графика «Математики»: rec.expr — формула от x (запись
   человека или собранная из неё), иначе узлы расчёта с причиной rec.why. */
function mathMark(sel, rec) {
  if (rec && rec.expr) return markExpr(sel, rec.expr, 'x', null, { name: rec.name || '' });
  return markNumeric(sel, (rec && rec.why) || 'график посчитан по точкам: записи формулой у него нет', (rec && rec.name) || '');
}
// Формула expr с подстановкой вместо x (деревом Math.js, а не правкой строки); null — не разобралась.
function mathSubst(expr, by) {
  try {
    return math.parse(prepExpr(String(expr))).transform(n => (n.isSymbolNode && n.name === 'x') ? math.parse(by) : n).toString();
  } catch (e) { return null; }
}
// Запись деформации графика: та же формула f(x), собранная по виду деформации.
function mathTransformExpr(expr, kind, a) {
  const A = '(' + a + ')';
  switch (kind) {
    case 'up':     return '(' + expr + ') + ' + A;
    case 'left':   return mathSubst(expr, '(x + ' + A + ')');
    case 'scaleY': return A + ' * (' + expr + ')';
    case 'scaleX': return mathSubst(expr, '(' + A + ' * x)');
    case 'negY':   return '-(' + expr + ')';
    case 'negX':   return mathSubst(expr, '(-x)');
    case 'absY':   return 'abs(' + expr + ')';
    case 'absX':   return mathSubst(expr, 'abs(x)');
    default:       return expr;
  }
}

// Кривая на полном плане: разрывы (NaN или далеко за окном) режут линию.
// rec — запись для .tex (mathMark).
function mathLine(g, f, mx, my, color, width, dash, rec) {
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
  mathMark(p, rec);
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
    .attr('font-size', FS.base).attr('font-weight', 600).attr('fill', color)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6);
  renderLabelText(t, shown);
  if (!key) return;
  makeRenamable(t, shown, tx, ty, (v) => {
    if (v) STATE.pointNames[key] = v; else delete STATE.pointNames[key];
  });
}

/* Любую подпись на графике переименовывают двойным щелчком прямо по ней.
   Одиночный щелчок оставлен свободным: им ставят точки и включают области, и
   переименование по нему срабатывало бы против воли. */
/* ⚠️ ЦЕЛЬ ДЛЯ ДВОЙНОГО ЩЕЛЧКА НЕ БЫВАЕТ МЕНЬШЕ 24×24 (решение владельца 20.08).

   Сама подпись «D» занимает 7×14 пикселей, и попасть в неё двойным щелчком
   почти невозможно: на приёмке промахнулись трижды подряд, каждый раз мимо на
   один-два пикселя. У кривых эта беда решена давно полосой захвата в 16 px;
   подписи достаётся невидимый прямоугольник вокруг слова.

   Вид подписи не меняется ни на пиксель: прямоугольник прозрачный и в выгрузку
   не идёт (`data-skip-export`).

   ЧУЖИЕ ЩЕЛЧКИ ОН НЕ СЪЕДАЕТ, и вот почему:
     · всё, что рисуется ПОЗЖЕ (ключевые точки, добор полос захвата,
       манипуляторы сцены), лежит выше него и получает свой щелчок первым;
     · одиночный щелчок ВСПЛЫВАЕТ до холста, поэтому панорама, постановка
       точки и набор вершин работают как работали;
     · единственное, что оказалось бы ниже, — полоса захвата своей же кривой,
       и одиночный щелчок по имени кривой делает ровно то же, что щелчок по
       ней самой: взводит её ключевые точки. */
const RENAME_HIT_PX = 24;
function makeRenamable(t, current, px, py, apply, armName) {
  // Плашки у подписи нет: она открывается двойным щелчком, и всплывающее
  // под указателем мешало бы попасть. Про переименование сказано в
  // подсказке блока «Точки на графике».
  t.style('cursor', 'text');
  const open = (ev) => {
    ev.stopPropagation(); ev.preventDefault();
    // Узел подписи нужен правке: у неё нет своего вида, она берёт кегль, вес и
    // цвет у самой подписи и встаёт ровно на её место.
    editInlineLabel(current, px, py, apply, t.node());
  };
  t.on('dblclick', open);

  const node = t.node();
  const parent = node && node.parentNode;
  let bb = null;
  try { bb = node.getBBox(); } catch (e) { bb = null; }
  if (!bb || !parent || !(bb.width > 0)) return;
  const w = Math.max(RENAME_HIT_PX, bb.width + 10);
  const h = Math.max(RENAME_HIT_PX, bb.height + 8);
  /* ⚠️ ПРЯМОУГОЛЬНИК ВСТАЁТ ПОД САМУ ПОДПИСЬ, А НЕ НАД НЕЙ. Он прозрачный, и
     на вид разницы нет никакой, но щелчок по самим буквам обязан доставаться
     тексту: иначе всякая проверка, целящаяся в подпись, упирается в чужую
     фигуру («intercepts pointer events»), а человек теряет ровно ту цель, по
     которой он и метит. Прямоугольник добирает ПОЛЯ вокруг слова, и только. */
  const hit = d3.select(parent).insert('rect', () => node)
    .attr('x', bb.x + bb.width / 2 - w / 2)
    .attr('y', bb.y + bb.height / 2 - h / 2)
    .attr('width', w).attr('height', h)
    .attr('fill', 'transparent')
    .attr('data-skip-export', '1')
    .attr('data-rename-hit', '1')
    .style('cursor', 'text');
  hit.on('dblclick', open);
  if (armName) {
    hit.on('click', (ev) => {
      ev.stopPropagation();
      if (typeof armCurve === 'function') armCurve(armName);
    });
  }
}

// Совместимость: прежнее имя оставлено, вызовы через него по-прежнему работают.
function editPointName(key, current, px, py) {
  editInlineLabel(current, px, py, (v) => {
    if (v) STATE.pointNames[key] = v; else delete STATE.pointNames[key];
  });
}

/* ⚠️ ПОЛЯ ВВОДА ПРИ ПЕРЕИМЕНОВАНИИ ЧЕЛОВЕК НЕ ВИДИТ (фаза 8 ревью 19.08).

   Было: белое окошко 152×20 с рамкой, всегда одной ширины и всегда вправо от
   подписи. У правого края холста оно вылезало за пределы картинки, а на месте
   аккуратной подписи вдруг появлялся чужой прямоугольник.

   Стало: само название остаётся на месте и получает пунктирное подчёркивание
   ровно по длине слова, акцентным цветом. Содержимое выделено целиком — набор
   сразу заменяет старое имя. Подчёркивание тянется за словом при вводе.

   Поле по-прежнему настоящее (`input`): подменить его на `contenteditable`
   значило бы потерять мобильную клавиатуру, выделение и озвучивание. Просто у
   него нет своего вида — ни фона, ни рамки, — а кегль, вес и цвет оно берёт у
   самой подписи. Подпись на время правки прячется, иначе текст двоился бы.

   Enter и щелчок мимо сохраняют, Escape отменяет, пустое имя откатывается к
   прежнему. Не помещается у края — переезжает ЦЕЛИКОМ левее или правее; на
   вторую строку название не разрывается никогда. */
function editInlineLabel(current, px, py, apply, node) {
  const wrap = document.getElementById('graph-wrap');
  if (!wrap) return;
  const old = document.getElementById('pt-rename');
  if (old) old.remove();

  // Вид берём у самой подписи: своего у поля быть не должно.
  const cs = node ? getComputedStyle(node) : null;
  const size = cs ? cs.fontSize : (FS.base + 'px');
  const weight = cs ? cs.fontWeight : '600';
  const color = (cs && cs.fill && cs.fill !== 'none') ? cs.fill : 'var(--text)';
  const family = cs ? cs.fontFamily : 'inherit';
  // Подпись прячем, но место её не трогаем: она вернётся ровно туда же.
  if (node) node.style.visibility = 'hidden';

  const inp = document.createElement('input');
  inp.id = 'pt-rename'; inp.type = 'text'; inp.value = current;
  inp.setAttribute('aria-label', 'Название на графике');
  inp.style.cssText = 'position:absolute;z-index:40;padding:0;margin:0;'
    + 'border:0;border-bottom:1px dashed var(--accent);border-radius:0;background:none;'
    + 'outline:none;box-sizing:content-box;line-height:1.1;'
    + 'font-size:' + size + ';font-weight:' + weight + ';font-family:' + family + ';'
    + 'color:' + color + ';';

  /* Ширина — по содержимому и пересчитывается на каждый ввод: подчёркивание
     обязано тянуться за словом, а не стоять на месте. Меряем настоящим
     размером текста, а не прикидкой по числу символов. */
  const ruler = document.createElement('span');
  ruler.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;padding:0;'
    + 'font-size:' + size + ';font-weight:' + weight + ';font-family:' + family + ';';
  wrap.appendChild(ruler);

  const box = wrap.getBoundingClientRect();
  const fit = () => {
    ruler.textContent = inp.value || ' ';
    const w = Math.max(12, ruler.offsetWidth + 2);
    inp.style.width = w + 'px';
    /* Подпись целиком внутри холста. Не влезла справа — переезжает влево ВСЯ,
       а не переносится по словам: имя на графике разрывать нельзя. */
    let left = px;
    if (left + w > box.width - 4) left = Math.max(4, box.width - 4 - w);
    if (left < 4) left = 4;
    inp.style.left = Math.round(left) + 'px';
  };

  const fs = parseFloat(size) || 13;
  inp.style.top = Math.round(py - fs) + 'px';
  wrap.appendChild(inp);
  fit();

  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    // Пустое имя не сохраняем: откат к прежнему (решение владельца).
    if (save && inp.value.trim()) { pushUndo(); apply(inp.value.trim()); }
    ruler.remove();
    inp.remove();
    if (node) node.style.visibility = '';
    redrawAll();
  };
  inp.addEventListener('input', fit);
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  inp.addEventListener('blur', () => finish(true));
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

  /* Панели объявляются реестру: слой поверх сцены обязан считать по шкалам
     ТОЙ панели, в которой стоит точка. Без этого площадь натягивалась
     полигоном между графиком функции и графиком её производной, а на нижнем
     графике мышь липла к f(x), которой там нет. */
  clearPanels();
  registerPanel('deriv-top', s1.mx, s1.my,
    { x0: m.left, y0: L.top, x1: W - m.right, y1: L.yMid });
  registerPanel('deriv-bottom', s2.mx, s2.my,
    { x0: m.left, y0: L.botTop, x1: W - m.right, y1: L.bottom });

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
    .attr('font-size', FS.large).attr('font-weight', 700).attr('fill', COL.tanF).text('f(x), сама функция');
  /* ⚠️ Подпись панели идёт через ОБЩИЙ разбор, а не через .text().
     Прямой .text() печатал «$f'(x)$, производная» вместе с долларами: KaTeX
     на холсте нет, и снимать разделители умеет только renderLabelText. */
  renderLabelText(
    gUi.append('text').attr('x', m.left + 4).attr('y', L.botTop + 14)
      .attr('font-size', FS.large).attr('font-weight', 700).attr('fill', COL.tanD),
    "$f'(x)$, производная");

  mathLine(gTop, f, s1.mx, s1.my, COL.tanF, 2.6, null, { expr: STATE.mathFormula, name: 'f(x)' });
  mathLine(gBot, dfun, s2.mx, s2.my, COL.tanD, 2.4, null,
    { expr: derivativeExpr(STATE.mathFormula, 'x'), name: 'производная', why: 'производная посчитана численно: символьной записи у неё нет' });

  const x0 = STATE.mathX0, y0 = f(x0), k = dfun(x0);
  STATE.mathRes = { x0, y0, k, secant: null };
  if (isNaN(y0)) { updateMathPanel(); return; }

  // Касательная: y = y0 + k·(x − x0).
  if (!isNaN(k)) {
    mathLine(gTop, (x) => y0 + k * (x - x0), s1.mx, s1.my, COL.reg, 2, null,
      { expr: '(' + y0 + ') + (' + k + ') * (x - (' + x0 + '))', name: 'касательная' });
    // Треугольник Δx / Δy — наглядное «отношение катетов = тангенс = производная».
    const dx = Math.min(STATE.mathDx, (wTop.xmax - wTop.xmin) * 0.25);
    const xa = x0, xb = x0 + dx, ya = y0, yb = y0 + k * dx;
    const tri = [[s1.mx(xa), s1.my(ya)], [s1.mx(xb), s1.my(ya)], [s1.mx(xb), s1.my(yb)]];
    markPoly(gTop.append('path').attr('d', 'M' + tri.map(p => p.join(',')).join('L') + 'Z')
      .attr('fill', COL.reg).attr('opacity', 0.14)
      .attr('stroke', COL.reg).attr('stroke-width', 1.2).attr('stroke-dasharray', '4 3'),
    'треугольник приращений Δx и Δy: по трём вершинам', 'треугольник приращений');
    gTop.append('text').attr('x', (s1.mx(xa) + s1.mx(xb)) / 2).attr('y', s1.my(ya) + 13)
      .attr('text-anchor', 'middle').attr('font-size', FS.small).attr('fill', COL.reg)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.4)
      .text('Δx = ' + fmt(dx));
    gTop.append('text').attr('x', s1.mx(xb) + 6).attr('y', (s1.my(ya) + s1.my(yb)) / 2)
      .attr('dominant-baseline', 'middle').attr('font-size', FS.small).attr('fill', COL.reg)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.4)
      .text('Δy = ' + fmt(k * dx));
  }

  // Секущая через две точки — видно, как она ложится на касательную при малом Δx.
  if (STATE.mathSecant) {
    const dx = STATE.mathDx, y1 = f(x0 + dx);
    if (!isNaN(y1)) {
      const ks = (y1 - y0) / dx;
      mathLine(gTop, (x) => y0 + ks * (x - x0), s1.mx, s1.my, COL.tax, 1.8, '6 4',
        { expr: '(' + y0 + ') + (' + ks + ') * (x - (' + x0 + '))', name: 'секущая' });
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
    // Точку ведут мышью — плашка перехватывала бы указатель.
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
  const lo = STATE.mathXmin, hi = STATE.mathXmax;   // окно — только для заливки
  const seg = _ansSeg || answerSeg();               // ответ — на отрезке (ADR 0143)

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
  mathLine(g, f, mx, my, COL.D, 2.8, null, { expr: STATE.mathFormula, name: 'f(x)' });

  const a = mathAnalyse(f, seg.a, seg.b);
  STATE.mathRes = a;
  /* Подпись «максимум 2» не говорила, что это: координата точки или значение
     функции. Пишем обе величины и называем их: x* — где, y* — сколько. */
  const ptLabel = (kind, p) => kind + ': (x*; y*) = (' + fmt(p.x) + '; ' + fmt(p.y) + ')';
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
  mathLine(g, f, mx, my, COL.ghost, 2.2, '6 4', { expr: STATE.mathFormula, name: 'исходная' });   // исходная — бледным пунктиром
  mathLine(g, t, mx, my, COL.D, 2.8, null,
    { expr: mathTransformExpr(STATE.mathFormula, STATE.mathTrans, paramValue('a', 1)), name: MATH_TRANS[STATE.mathTrans] ? MATH_TRANS[STATE.mathTrans].tex : '' });
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
      // А28: имя кривой набирается с индексом (f с единицей), а не слипшимся текстом.
      /* Класс тот же, что у общего помощника labelCurve: по нему подпись кривой
         находят и реестр обозначений, и проверка канона, и ночная проба
         «сколько кривых подписано». Без него подписи «Математики» — эталона
         поведения по решению владельца 22.08 — были для всех этих проверок
         невидимы, хотя на экране стояли. */
      renderLabelText(
        g.append('text').attr('class', 'curve-name')
          .attr('x', sm.px - 4).attr('y', sm.py - 7).attr('text-anchor', 'end')
          .attr('font-size', curveLabelSize()).attr('font-weight', 600).attr('fill', color)
          .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6),
        txt);
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

/* Исходные функции сюжета и итоговая Z — одна сборка на рисунок и на
   «Ответ» (отрезок ответа подбирается по Z и по парам исходных). */
function mmParts(f) {
  const parts = [{ fn: f, name: mmLabel(0), color: mmColor(0), expr: STATE.mathFormula }];
  for (let i = 1; i < mmSlots(); i++) {
    const expr = mmGet(i);
    if (!expr.trim()) continue;
    const { compiled } = compileMath(expr, 'x');
    if (!compiled) continue;
    parts.push({ fn: (x) => evalMathAt(compiled, 'x', x), name: mmLabel(i), color: mmColor(i), expr });
  }
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
  return { parts, isMin, z };
}

function drawMathMinMax(f) {
  const { mx, my } = mathScales();
  const g = svg.append('g');
  drawGrid(mx, my, g);
  drawPlaneAxes(g, mx, my, 'x', 'y');
  const { parts, isMin, z } = mmParts(f);
  if (parts.length < 2) { STATE.mathRes = { error: 'Нужна хотя бы вторая функция.' }; updateMathPanel(); return; }
  parts.forEach(p => {
    mathLine(g, p.fn, mx, my, p.color, 1.8, '5 4', { expr: p.expr, name: p.name });
    labelCurveMath(g, p.fn, mx, my, p.name, p.color);
  });
  const zName = (STATE.mmName || 'Z').trim() || 'Z';
  const zColor = COL.mmZ || COL.MC;
  // запись Z: наименьшая или наибольшая из тех же формул
  mathLine(g, z, mx, my, zColor, 3.2, null,
    { expr: (isMin ? 'min(' : 'max(') + parts.map(p => '(' + p.expr + ')').join(', ') + ')', name: zName });
  labelCurveMath(g, z, mx, my, zName, zColor);
  // Точки, где ветви меняются местами: корни разности каждой пары, но в зачёт
  // идут только те, где обе функции в этот момент и есть итоговая Z.
  const seg = _ansSeg || answerSeg();
  const sw = [];
  for (let a = 0; a < parts.length; a++) {
    for (let b2 = a + 1; b2 < parts.length; b2++) {
      // На отрезке ответа, а не в окне (ADR 0143): точка вне окна просто не видна.
      ansZeros((x) => parts[a].fn(x) - parts[b2].fn(x), seg.a, seg.b, ANS_N).forEach(x => {
        const y = parts[a].fn(x);
        if (isNaN(y)) return;
        if (Math.abs(y - z(x)) > Math.max(1e-6, Math.abs(y) * 1e-6)) return;   // ветвь не главная
        if (sw.some(v => Math.abs(v - x) < (seg.b - seg.a) * 1e-4)) return;
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
    const compiled = math.parse(prepExpr(expr)).compile();
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
  const eq = topLevelEqIndex(t);
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
    const cp = g.append('path').datum(pts).attr('fill', 'none')
      .attr('stroke', COL.S).attr('stroke-width', 2.6).attr('d', line);
    /* запись для .tex — по форме ввода ограничения (тот же разбор, что у
       строки КПВ): y = f(x) — формула, x = g(y) — «по вертикали», общее
       уравнение — узлы трассировки с причиной */
    const r = parsePpfEquation(STATE.mathGC);
    if (!r.error && r.kind === 'explicit') markExpr(cp, r.src, 'x', null, { name: 'ограничение' });
    else if (!r.error && r.kind === 'inverse') markExpr(cp, r.src, 'y', null, { axis: 'y', name: 'ограничение' });
    else markNumeric(cp, 'ограничение задано общим уравнением и найдено численно (трассировкой): формулы y = f(x) у него нет', 'ограничение');
  }
  /* А ищем по всей задаче, а не по видимому куску: приблизили или сдвинули
     картинку — ответ не меняется (ADR 0143). Область поиска — размах самого
     ограничения (consFit, считается при входе и смене формулы), БЕЗ окна:
     объединение с окном меняло шаг сетки при отдалении и сдвиге. */
  const fit = STATE.consFit || { xMax: x1, yMax: y1 };
  const searchPts = (x0 === 0 && x1 === fit.xMax && y0 === 0 && y1 === fit.yMax)
    ? pts : constraintPointsIn(G, 0, fit.xMax, 0, fit.yMax);
  const opt = optimizeAlongCurve(f, searchPts, STATE.mathConsWantMax !== false);
  /* Точки ограничения кладём в состояние: по ним катается точка и по ним же
     ищутся ключевые точки сюжета (Н66). Пересчитывать их второй раз в
     mathSnapTargets значило бы делать ту же тяжёлую работу дважды за кадр. */
  STATE.mathRes = { opt, wantMax: STATE.mathConsWantMax !== false, conPts: pts };
  if (opt) {
    // Веер линий уровня + линия, проходящая через оптимум (она и касается ограничения).
    // Веер соседних уровней — как слагаемые «Сложения»: непрозрачно (0,95), пунктир 5 4, 1,6 px:
    // при прозрачности 0,35 контраст к холсту был 1,5 : 1 (инвариант 3 : 1, contrast_probe.mjs).
    [0.55, 0.78, 1.25].forEach(k => drawLevelCurveOn(g, mx, my, f, opt.value * k, COL.D, 1.6, 0.95, '5 4'));
    drawLevelCurveOn(g, mx, my, f, opt.value, COL.D, 2.6, 1);
    mathDot(g, mx, my, opt.a, opt.b, COL.ink,
      (STATE.mathConsWantMax === false ? 'минимум (' : 'максимум (') + fmt(opt.a) + '; ' + fmt(opt.b) + ')', null, 'opt');
  }
  updateMathPanel();
}
// Линия уровня F = const на своих шкалах (движок трассировки — общий).
function drawLevelCurveOn(g, mx, my, f, level, color, width, opacity, dash) {
  const pts = traceLevelCurve(f, level, mx.domain()[1], my.domain()[1], 220);
  if (!pts || pts.length < 2) return;
  const line = d3.line().defined(d => d !== null).x(d => mx(d[0])).y(d => my(d[1]));
  const p = g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color)
    .attr('stroke-width', width).attr('opacity', opacity).attr('d', line);
  if (dash) p.attr('stroke-dasharray', dash);
  // запись для .tex: формулы y = f(x) у линии уровня нет, в файл идут узлы трассировки
  markNumeric(p, 'линия уровня функции двух переменных найдена численно (трассировкой): формулы y = f(x) у неё нет');
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
  h += '<p><b>Зачем экономисту вторая производная?</b> Она отличает максимум от минимума, '
     + 'и без неё условие $f\' = 0$ ничего не доказывает. Именно поэтому в задаче про прибыль '
     + 'мало приравнять предельную выручку к предельным издержкам: нужно ещё убедиться, что '
     + 'в этой точке прибыль перестаёт расти, а не перестаёт падать.</p>';
  h += '<p><b>Вывод.</b> Порядок один и тот же в любой задаче на оптимум: найти точки, где '
     + 'производная обращается в ноль, проверить знак второй производной, отдельно посмотреть '
     + 'концы отрезка и только потом называть ответ.</p>';
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
        + `Шаг подбирается от ширины отрезка ответа, поэтому счёт одинаково точен и на отрезке 0…0.1, и на 0…1000, а масштаб графика на него не влияет.</p>`
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
        + `<p><b>Где это встречается в экономике?</b> Почти везде, где есть слово «предельный». `
        + `Предельные издержки это производная общих издержек, предельная выручка это производная `
        + `выручки, предельный продукт это производная выпуска по труду. Поэтому фраза «оптимум там, `
        + `где $MR = MC$» это то же самое, что «производная прибыли обратилась в ноль».</p>`
        + `<p><b>Вывод.</b> Наклон касательной, скорость изменения и предельная величина это три названия одного числа. Три `
        + `названия одного и того же числа. Кто научился читать наклон с картинки, тому не нужно `
        + `запоминать отдельные правила для каждой предельной величины.</p>`
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
    const a = paramValue('a', 1);
    html += `<div class="stat"><span>Преобразование</span><b>${t.tex}</b></div>`;
    html += `<div class="stat"><span>Параметр $a$</span><b>${fmt(a)}</b></div>`;
    html += `<div class="hint">${t.note}</div>`;
    // А53: у сюжета не было разбора вовсе, блок «Объяснение модели» открывался пустым.
    html += '<div class="sb-note"><b>Как это получилось</b>'
      + '<p><b>Что вообще делает преобразование?</b> Оно не меняет саму функцию, оно меняет '
      + 'ПРАВИЛО, по которому из числа получается высота. Бледная кривая это исходная $f(x)$, '
      + 'яркая это та же функция, пропущенная через новое правило. Сравнивать их надо по точкам: '
      + 'взять один и тот же $x$ и посмотреть, куда уехала высота.</p>'
      + '<p><b>Почему сдвиг по горизонтали работает наоборот?</b> В записи $f(x + a)$ прибавление '
      + 'происходит ВНУТРИ функции, до вычисления. Чтобы получить прежнюю высоту, теперь нужен '
      + 'меньший $x$, поэтому график уезжает ВЛЕВО, хотя в формуле стоит плюс. У сдвига по '
      + 'вертикали такой ловушки нет: там прибавление идёт уже к готовой высоте.</p>'
      + '<p><b>Чем растяжение отличается от сдвига?</b> Сдвиг двигает всю кривую целиком и форму '
      + 'не трогает. Растяжение умножает, поэтому точки, стоявшие далеко от оси, уезжают сильнее '
      + 'близких: форма меняется. Точки на самой оси остаются на месте, потому что умножение '
      + 'нуля ничего не даёт, и по ним видно, вокруг чего идёт растяжение.</p>'
      + '<p><b>Зачем это экономисту?</b> Почти все сдвиги кривых в экономике это ровно такие '
      + 'преобразования. Потоварный налог сдвигает предложение вверх на постоянную величину, '
      + 'адвалорный поворачивает его умножением на $(1 + \\tau)$, рост дохода двигает бюджетную '
      + 'линию параллельно. Увидев преобразование в формуле, вы уже знаете, как поедет график.</p>'
      + '<p><b>Вывод.</b> Прибавление снаружи двигает вверх, прибавление внутри двигает влево, '
      + 'умножение снаружи растягивает по вертикали, умножение внутри сжимает по горизонтали. '
      + `Сейчас $a = ${fmt(a)}$: подвиньте ползунок и проверьте правило на этой кривой.</p>`
      + '</div>';
  } else if (STATE.mathSub === 'minmax') {
    if (r.error) html = `<div class="warn">${r.error}</div>`;
    else {
      const nm = (STATE.mmName || 'Z').trim() || 'Z';
      const names = [];
      for (let i = 0; i < mmSlots(); i++) if (mmGet(i).trim()) names.push(mmLabel(i));
      html += `<div class="stat"><span>Строим</span><b>${nm} = ${r.isMin ? 'min' : 'max'}(${names.join(', ')})</b></div>`;
      html += `<div class="stat"><span>Функций участвует</span><b>${r.count}</b></div>`;
      html += `<div class="stat"><span>Кривые меняются местами</span><b>${(r.switches || []).length ? r.switches.map(v => fmt(v)).join('; ') : 'нигде'}</b></div>`;
      html += '<div class="sb-note"><b>Как это получилось</b>'
        + `<p><b>Как строится итоговая кривая?</b> В каждой точке x берётся ${r.isMin ? 'наименьшее' : 'наибольшее'} из значений всех функций. `
        + `Получается ломаная из кусков исходных кривых: ${r.isMin ? 'нижняя' : 'верхняя'} огибающая. `
        + `${r.isMin ? 'Она всюду не выше любой из них' : 'Она всюду не ниже любой из них'}, и совпадает с той, что в этой точке главная.</p>`
        + `<p><b>Откуда берутся изломы?</b> Точки перелома это корни разности пары функций: где f₁ − f₂ меняет знак, там кривые и меняются местами. `
        + `Корни ищутся численно и засчитываются только там, где обе функции в этот момент и есть ${nm}.</p>`
        + `<p>Экономический смысл тот же у нижней огибающей средних издержек: в каждой точке фирма выбирает `
        + `самый дешёвый способ, и длинная кривая складывается из кусков коротких.</p>`
        + `<p><b>Где ещё встречается такая огибающая?</b> В спросе на билеты с двумя тарифами: человек берёт `
        + `тот, что дешевле именно при его числе поездок, поэтому его расход это нижняя огибающая двух прямых. `
        + `В выборе между двумя технологиями: фирма считает по той, что при этом выпуске обходится дешевле. `
        + `Общее у всех случаев одно: выбор делается в КАЖДОЙ точке заново, а не один раз навсегда.</p>`
        + `<p><b>Вывод.</b> Изломы на такой кривой это не дефект и не ошибка счёта: это места, где выгодно `
        + `сменить вариант. Именно они обычно и есть ответ в задаче, потому что вопрос почти всегда звучит `
        + `как «при каком объёме стоит перейти на другой способ».</p>`
        + '</div>';
    }
  } else if (STATE.mathSub === 'constraint') {
    if (r.error) html = `<div class="warn">${r.error}</div>`;
    else if (!r.opt) html = '<div class="muted">Точка не нашлась: проверьте формулы и границы окна.</div>';
    else {
      html += `<div class="stat"><span>$x^*$</span><b>${fmt(r.opt.a)}</b></div>`;
      html += `<div class="stat"><span>$y^*$</span><b>${fmt(r.opt.b)}</b></div>`;
      html += `<div class="stat"><span>$f(x^*,\, y^*)$</span><b>${fmt(r.opt.value)}</b></div>`;
      /* Строки «Ищем = максимум» здесь больше нет (решение владельца 01.09):
         переключатель «Какую функцию ищем» стоит в левой панели, и повторять
         его выбор среди ПОСЧИТАННЫХ величин незачем. Слово осталось в разборе
         ниже — там оно объясняет способ, а не повторяет орган управления. */
      html += '<div class="sb-note"><b>Как это получилось</b>'
        + '<p><b>Что такое ограничение на графике?</b> Это кривая: точки, где g(x, y) обращается в ноль. '
        + 'Она ищется численно, для каждого x подбирается свой y, поэтому подходит '
        + 'любая форма, а не только прямая.</p>'
        + `<p><b>Как ищется оптимум?</b> Вдоль этой кривой перебирается значение цели, и берётся ${r.wantMax ? 'наибольшее' : 'наименьшее'}. `
        + 'Тонкими линиями нарисован веер линий уровня цели, жирной та, что проходит через найденную точку.</p>'
        + '<p><b>Почему именно касание?</b> Линия уровня касается ограничения, а не пересекает его. Это и есть признак оптимума: '
        + 'сдвинуться вдоль ограничения в любую сторону значит перейти на линию уровня хуже.</p>'
        + '<p><b>Почему это одна и та же задача во всей микроэкономике?</b> Потребитель максимизирует полезность '
        + 'при бюджете, фирма максимизирует выпуск при затратах или минимизирует затраты при выпуске, страна '
        + 'выбирает точку на своей КПВ. Меняются названия осей и смысл кривых, а условие остаётся тем же: '
        + 'наклон линии уровня равен наклону ограничения.</p>'
        + '<p><b>Когда касания не будет?</b> Когда оптимум упирается в угол: у совершенных заменителей берут '
        + 'только один товар, и решение сидит на оси. Тогда равенства наклонов нет, а ответ всё равно верный. '
        + 'Поэтому касание это признак оптимума внутри области, а не закон на все случаи.</p>'
        + '<p><b>Вывод.</b> Сначала проверяют, есть ли внутреннее решение по касанию, и только потом смотрят '
        + 'углы. Обратный порядок в олимпиадных задачах чаще всего и приводит к потере ответа.</p>'
        + '</div>';
    }
  }
  box.innerHTML = html;
}

function redrawMath() {
  svg.selectAll('*').remove();
  addDefs();
  refreshAnswerSeg();    // отрезок ответа кадра — до любого расчёта (ADR 0143)
  /* Панель раздела: окно здесь полный план, а не первая четверть, поэтому
     'main', зарегистрированная makeScales по CONFIG, тут не годится совсем.
     Сюжет про производную заменит эту запись двумя своими. */
  {
    const m = CONFIG.margin, ms = mathScales();
    clearPanels();
    registerPanel('main', ms.mx, ms.my,
      { x0: m.left, y0: m.top, x1: W - m.right, y1: H - m.bottom });
  }
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
  /* Точку касания окно больше не трогает (ADR 0143): раньше приближение мимо
     x₀ зажимало её в окно, и f(x₀) в «Ответе» менялось от масштаба. Ползунок
     x₀ ходит по отрезку ответа (syncAnsSegUI). */
  redrawAll();
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
     TeX — buildTex: холст на миг перерисовывается на белом листе
           постоянного размера, опись нарисованного (кривые — формулами по
           записи места рисования, области — границами) собирается в pgfplots
           (72-export-tex.js). Файл собирается обычным pdflatex.
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

/* ── БЕЛЫЙ ЛИСТ (редизайн 10.2026, README макета, раздел 13) ──────────────
   В файл график уходит светлыми токенами на белом, какая бы тема ни стояла
   на экране: картинка уходит в чужой документ и на бумагу. Холст на миг
   перерисовывается в светлой теме с белым фоном, клонируется, и тема
   возвращается — всё в одной задаче браузера, поэтому экран не мигает.
   Из клона вырезаются служебные узлы (data-service: ручки, зажжённые
   ключевые точки, кружок прилипания) — в файл они не идут (COVERAGE, 6.8). */
function paperChartClone() {
  const root = document.documentElement;
  const theme = root.getAttribute('data-theme');
  const paper = cssVar('--paper');
  root.setAttribute('data-theme', 'light');
  root.style.setProperty('--canvas', paper);
  root.style.setProperty('--halo', paper);
  let clone = null, w = W, h = H;
  try {
    refreshColors(); redrawAll();
    const node = document.getElementById('chart');
    if (node) {
      w = node.clientWidth || W; h = node.clientHeight || H;
      clone = node.cloneNode(true);
      clone.querySelectorAll('[data-service]').forEach(n => n.remove());
      clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      clone.setAttribute('width', w); clone.setAttribute('height', h);
    }
  } finally {
    if (theme) root.setAttribute('data-theme', theme); else root.removeAttribute('data-theme');
    root.style.removeProperty('--canvas');
    root.style.removeProperty('--halo');
    refreshColors(); redrawAll();
  }
  return { clone, w, h, paper };
}
// Главные числа ответа строкой: «Q = 40   Pb = 60 …» (ячейки «Ответа»).
function exportNumbersLine() {
  return [...document.querySelectorAll('#ans-hero .ans-cell')].map(c => {
    const t = (el) => { if (!el) return ''; const k = el.cloneNode(true); k.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return k.textContent.replace(/\s+/g, ' ').trim(); };
    const n = t(c.querySelector('.ans-not'));
    const v = (typeof selfMasked === 'function' && selfMasked()) ? '?' : t(c.querySelector('.ans-val'));   // «Сначала сам»
    return (n ? n + ' = ' : t(c.querySelector('.ans-lab')) + ': ') + v;
  }).filter(Boolean).join('    ');
}
function exportExtras() {
  const title = expValue('exp-title').trim();
  const cap = expValue('exp-caption').trim();
  const nb = document.getElementById('exp-nums');
  const nums = (nb && nb.checked) ? exportNumbersLine() : '';
  return { title, cap, nums };
}

function exportPNG(scale, toPreview) {
  const { clone, w, h, paper } = paperChartClone();
  if (!clone) return;
  const src = new XMLSerializer().serializeToString(clone);
  const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(src);
  if (toPreview) { toPreview.src = url; return; }
  const ex = exportExtras();
  const font = getComputedStyle(document.body).fontFamily;
  const ink = cssVar('--ink') || 'black';
  const inkSoft = cssVar('--ink-soft') || ink;
  const img = new Image();
  img.onload = () => {
    const top = ex.title ? 34 : 0;
    const below = (ex.cap ? 24 : 0) + (ex.nums ? 26 : 0) + ((ex.cap || ex.nums) ? 8 : 0);
    const cv = document.createElement('canvas');
    cv.width = Math.round(w * scale); cv.height = Math.round((h + top + below) * scale);
    const ctx = cv.getContext('2d');
    ctx.scale(scale, scale);
    ctx.fillStyle = paper || 'white';     // белый лист, в любой теме
    ctx.fillRect(0, 0, w, h + top + below);
    ctx.drawImage(img, 0, top, w, h);
    ctx.textAlign = 'center';
    if (ex.title) { ctx.fillStyle = ink; ctx.font = '600 15px ' + font; ctx.fillText(ex.title, w / 2, 22); }
    let y = top + h + 18;
    if (ex.cap) { ctx.fillStyle = inkSoft; ctx.font = '400 13px ' + font; ctx.fillText(ex.cap, w / 2, y); y += 24; }
    if (ex.nums) { ctx.fillStyle = ink; ctx.font = '500 14px ' + font; ctx.fillText(ex.nums, w / 2, y); }
    cv.toBlob(b => {
      if (!b) { toast('Не получилось собрать картинку'); return; }
      downloadBlob(b, exportBaseName() + '.png');
      toast('PNG сохранён');
    });
  };
  img.onerror = () => toast('Не получилось собрать картинку');
  img.src = url;
}

// ── .tex ────────────────────────────────────────────────────────────────
/* ЕДИНСТВЕННАЯ ДВЕРЬ ВЫГРУЗКИ .tex (решение владельца 07.10.2026, ADR 0139):
   бумажный прогон → опись → сборка (72-export-tex.js). Её зовут «Скачать TeX»,
   «Скачать PDF», окно «Скачать» и приборы. Прежние сборщики (обход SVG и
   сборка «от состояния», ADR 0030) удалены вместе с переключателем адреса. */
function buildTex(title, label) {
  const r = texEmit(texInventory(), { title: title || '', label: label || '' });
  buildTex._tally = r.tally;      // опись окна «Скачать»
  buildTex._stats = r.stats;      // счётчики сборки (приборы и тесты)
  return r.tex;
}

/* Шрифты — до бумажного прогона: поля холста считаются по измеренной ширине
   подписей, и кадр до загрузки шрифтов даёт поля на 3–5 px другие. */
function afterFonts(fn) {
  if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(fn, fn);
  else fn();
}

function exportTex() {
  afterFonts(() => {
    const title = (document.getElementById('exp-title') || {}).value || '';
    const label = (document.getElementById('exp-label') || {}).value || '';
    const tex = buildTex(title, label);
    downloadBlob(new Blob([tex], { type: 'text/plain;charset=utf-8' }), exportBaseName() + '.tex');
    toast('Файл .tex сохранён');
  });
}

function exportPDF() {
  const title = (document.getElementById('exp-title') || {}).value || '';
  const label = (document.getElementById('exp-label') || {}).value || '';
  const btn = document.getElementById('exp-go');
  if (btn) { btn.disabled = true; btn.textContent = 'Собираю…'; }
  afterFonts(() => exportPDFSend(title, label, btn));
}
function exportPDFSend(title, label, btn) {
  const body = new FormData();
  body.append('tex', buildTex(title, label));
  body.append('name', exportBaseName());
  body.append('csrfmiddlewaretoken', (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '');
  fetch(CALC2_PDF_URL, { method: 'POST', body })
    .then(r => r.ok ? r.blob() : r.text().then(t => { throw new Error(t.slice(0, 200)); }))
    .then(b => { downloadBlob(b, exportBaseName() + '.pdf'); toast('PDF готов'); })
    .catch(e => toast('PDF не собрался: ' + e.message))
    .finally(() => { if (btn) { btn.disabled = false; syncExportFormat(); } });
}

/* Поля окна экспорта правятся НА МЕСТЕ, как и всё остальное в калькуляторе
   (А50): щелчок по значению открывает правку прямо там, без окошка внутри
   окошка. Скрытые input сохранены как хранилище значения, чтобы весь
   остальной код (exportTex, exportPDF) читал их прежним способом. */
function buildExportFields() {
  [['exp-title', 'exp-title-slot', 'Например: Рынок хлеба'],
   ['exp-label', 'exp-label-slot', 'Например: fig:bread']].forEach(([id, slotId, hint]) => {
    const slot = document.getElementById(slotId), inp = document.getElementById(id);
    if (!slot || !inp || slot.dataset.ready) return;
    slot.dataset.ready = '1';
    slot.appendChild(makeEditableValue({
      kind: 'text',
      get: () => inp.value || '',
      set: (v) => { inp.value = String(v == null ? '' : v).trim(); refreshExportPreview(); refreshExportSheet(); },
      fmt: (v) => (String(v || '').trim() || hint),
      title: 'Щёлкните, чтобы изменить',
    }));
  });
}

/* Предпросмотр: что именно уйдёт в файл. Раньше человек жал «Скачать» вслепую.
   Опись холста берётся ОДИН раз на открытие окна: бумажный прогон стоит
   100–600 мс, а окно перестраивает опись на каждую правку поля заголовка;
   под окном модель не меняется, на правку идёт только сборка. */
let _expList = null;
function refreshExportPreview() {
  const box = document.getElementById('exp-preview');
  if (!box) return;
  let r = null;
  try {
    if (!_expList) _expList = texInventory();
    r = texEmit(_expList, { title: expValue('exp-title'), label: expValue('exp-label') });
  } catch (e) { r = null; }
  if (!r || !r.tex || !_expList.panels.length) { box.textContent = 'Пока нечего выгружать: на графике ничего не построено.'; return; }
  const cm = (v) => String(v).replace('.', ',');
  const size = r.tally.plotCm ? [cm(r.tally.plotCm[0]), cm(r.tally.plotCm[1])] : null;
  /* п. 70. Опись перечисляет то, что человек видит на графике, и его словами.
     «Кривых формулой» и «Кривых точками» — это про устройство файла: у одной
     и той же кривой разрыв даёт несколько записей, и на экране с двумя
     кривыми стояло «Кривых точками 10». Как именно кривая записана в файле,
     человека не касается: он выбирает, скачивать или нет. */
  const t = r.tally || {};
  const cap = expValue('exp-title');
  const rows = [
    ['Размер картинки', size ? size[0] + ' на ' + size[1] + ' см' : 'по умолчанию'],
    ['Кривых', String(t.curves || 0)],
    ['Закрашенных областей', String(t.areas || 0)],
    ['Точек', String(t.dots || 0)],
    ['Линий и пунктиров', String(t.lines || 0)],
    ['Подписей', String(t.labels || 0)],
    ['Легенда областей', t.legend ? 'есть' : 'нет'],
    ['Подпись под картинкой', cap || 'без подписи'],
  ];
  box.innerHTML = '';
  rows.forEach(([k, v]) => {
    const r = document.createElement('div');
    r.className = 'exp-prow';
    const a = document.createElement('span'); a.className = 'exp-pk'; a.textContent = k;
    const b = document.createElement('span'); b.className = 'exp-pv'; b.textContent = v;
    r.appendChild(a); r.appendChild(b); box.appendChild(r);
  });
}

function expValue(id) { const el = document.getElementById(id); return el ? el.value : ''; }

/* Формат и одна кнопка «Скачать …» (README макета, раздел 10). */
const EXPORT_FORMATS = {
  png: { btn: 'Скачать PNG', note: 'Картинка с двойной чёткостью для презентации и конспекта.' },
  pdf: { btn: 'Скачать PDF', note: 'Лист A4 с полями для печати и домашки.' },
  tex: { btn: 'Скачать TeX', note: 'Код TikZ для LaTeX: вставьте в свою работу как есть.' },
};
let exportFormat = 'png';
function syncExportFormat() {
  const f = EXPORT_FORMATS[exportFormat] || EXPORT_FORMATS.png;
  document.querySelectorAll('#exp-fmt .seg-btn').forEach(b => {
    const on = b.dataset.fmt === exportFormat;
    b.classList.toggle('active', on);
    b.setAttribute('aria-checked', on ? 'true' : 'false');
  });
  const go = document.getElementById('exp-go'); if (go) go.textContent = f.btn;
  const note = document.getElementById('exp-fmt-note'); if (note) note.textContent = f.note;
  // Метка для перекрёстной ссылки нужна только файлу LaTeX (К4).
  const lf = document.getElementById('exp-label-field'); if (lf) lf.hidden = (exportFormat === 'png');
}
function refreshExportSheet() {
  const ex = exportExtras();
  const tt = document.getElementById('exp-sheet-title'); if (tt) { tt.textContent = ex.title; tt.hidden = !ex.title; }
  const cp = document.getElementById('exp-sheet-cap'); if (cp) { cp.textContent = ex.cap; cp.hidden = !ex.cap; }
  const nm = document.getElementById('exp-sheet-nums'); if (nm) { nm.textContent = ex.nums; nm.hidden = !ex.nums; }
  const img = document.getElementById('exp-sheet-img');
  if (img) exportPNG(1, img);
}
function wireExport() {
  document.querySelectorAll('#exp-fmt .seg-btn').forEach(b => b.addEventListener('click', () => {
    if (b.disabled) return;
    exportFormat = b.dataset.fmt; syncExportFormat(); refreshExportPreview();
  }));
  const go = document.getElementById('exp-go');
  if (go) go.addEventListener('click', () => {
    if (exportFormat === 'tex') exportTex();
    else if (exportFormat === 'pdf') exportPDF();
    else exportPNG(2);   // 2× — читаемо в печати
  });
  const x = document.getElementById('exp-x'); if (x) x.addEventListener('click', () => closeExport());
  ['exp-caption', 'exp-nums'].forEach(id => {
    const e = document.getElementById(id);
    if (e) e.addEventListener(e.type === 'checkbox' ? 'change' : 'input', () => refreshExportSheet());
  });
  // Окно модальное: Tab ходит по кругу внутри (DESIGN.md 2.15).
  const m = document.getElementById('export-modal');
  if (m) m.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const list = [...m.querySelectorAll('button:not([disabled]), input:not([type=hidden]), [tabindex="0"]')].filter(el => el.offsetParent !== null);
    if (!list.length) return;
    const first = list[0], last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  syncExportFormat();
}

function openExport() {
  const m = document.getElementById('export-modal');
  if (!m) return;
  const t = document.getElementById('exp-title');
  if (t && !t.value) t.value = STATE.graphTitle || SCENE_NAMES[STATE.sceneKey] || '';
  m.classList.add('open');
  m.removeAttribute('inert');
  buildExportFields();
  _expList = null;                 // опись — заново на каждое открытие окна
  if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(() => { _expList = null; refreshExportPreview(); });
  const slot = document.getElementById('exp-title-slot');
  const ed = slot && slot.querySelector('.edval');
  if (ed && ed._repaint) ed._repaint();
  const slot2 = document.getElementById('exp-label-slot');
  const ed2 = slot2 && slot2.querySelector('.edval');
  if (ed2 && ed2._repaint) ed2._repaint();
  refreshExportPreview();
  syncExportFormat();
  refreshExportSheet();
  if (ed) ed.focus();
}
function closeExport() {
  const m = document.getElementById('export-modal');
  if (!m) return;
  m.classList.remove('open');
  m.setAttribute('inert', '');
  _expList = null;
  const b = document.getElementById('dock-export'); if (b) b.focus();
}


/* ---------------------------------------------------------------------
   ПОСТРОЕНИЕ ГРАФИКОВ: разбор построенных кривых (А53)

   Раньше у этого сюжета не было ни «Ключевых значений», ни «Объяснения»:
   оба блока открывались пустыми. А это первая сцена, которую открывает новый
   человек, и первое, что он про калькулятор узнавал, — что тут ничего нет.

   Считать здесь есть что, и ровно то, что спрашивают в задачах: где кривая
   пересекает оси, где у неё вершина, где две кривые встречаются.
   --------------------------------------------------------------------- */
function updateGraphPanel() {
  const box = document.getElementById('info-graph');
  if (!box) return;
  if (STATE.mode !== 'graph') { box.innerHTML = ''; return; }
  const shown = STATE.curves.filter(c => c.visible && !isVertical(c));
  if (!shown.length) {
    box.innerHTML = '<div class="muted">Введите формулу в поле слева, и здесь появятся нули функции, '
      + 'её вершины и точки пересечения кривых.</div>'
      + graphExplainNote(0);
    return;
  }
  /* ⚠️ ОТВЕТ СЧИТАЕТСЯ НА ОТРЕЗКЕ ОТВЕТА, А НЕ В ОКНЕ (ADR 0143). Раньше
     здесь стояло mx.domain(): приближение к вершине x² − 4 меняло «−2; 2» на
     «в окне не пересекает», и колонка «Ответ» дёргалась от колеса. */
  const seg = _ansSeg || answerSeg();
  const lo = seg.a, hi = seg.b;
  let html = '';
  const fns = [];
  shown.forEach(c => {
    const f = (x) => evalCurve(c, x);
    fns.push(f);
    const name = curveShortName(c);
    const r = ansAnalyse(f, lo, hi);
    html += `<div class="stat"><span>Кривая</span><b>${name}</b></div>`;
    /* ⚠️ РАЗДЕЛИТЕЛЬ СПИСКА — ТОЧКА С ЗАПЯТОЙ, ПОТОМУ ЧТО ЗАПЯТАЯ ЗАНЯТА.
       Корни 0 и 1 печатались как «0, 1,0»: запятая разделяла список и она же
       была десятичным знаком, прочитать это невозможно. Десятичная запятая —
       требование канона 2.1, значит менять надо разделитель. Стало «0; 1».
       ⚠️ fmt не отдавать в .map напрямую: второй довод у fmt — число знаков. */
    html += `<div class="stat"><span>Пересекает ось $x$</span><b>${ansList(r.zeros)}</b></div>`;
    html += `<div class="stat"><span>Пересекает ось $y$</span><b>${r.y0 == null ? 'нет' : ansFmt(r.y0)}</b></div>`;
    const ext = r.max.concat(r.min).sort((a, b) => a.x - b.x);
    if (ext.length) html += `<div class="stat"><span>Вершины</span><b>${ansPts(ext)}</b></div>`;
  });
  /* Пересечения кривых между собой — нули разности на том же отрезке (раньше
     брались у ключевых точек холста, то есть тоже по окну).
     ⚠️ ПРИ ОДНОЙ КРИВОЙ ПЕРЕСЕКАТЬСЯ НЕЧЕМУ: строки нет. */
  if (fns.length > 1) {
    const cr = [];
    for (let i = 0; i < fns.length; i++) for (let j = i + 1; j < fns.length; j++) {
      ansCrosses(fns[i], fns[j], lo, hi).forEach(p => {
        if (!cr.some(q => Math.abs(q.x - p.x) < (hi - lo) * 1e-6 && Math.abs(q.y - p.y) < 1e-6 * (1 + Math.abs(p.y)))) cr.push(p);
      });
    }
    cr.sort((a, b) => a.x - b.x);
    html += `<div class="stat"><span>Кривые пересекаются</span><b>${ansPts(cr)}</b></div>`;
  }
  box.innerHTML = html + graphExplainNote(shown.length);
}

/* Разбор сюжета. Живёт врезкой .sb-note, поэтому общий проход сам перенесёт
   его в «Объяснение модели», ничего специально делать не нужно. */
function graphExplainNote(count) {
  return '<div class="sb-note"><b>Как это получилось</b>'
    + '<p><b>Что такое график функции?</b> Это множество точек, у которых вторая координата '
    + 'посчитана из первой по одному и тому же правилу. Формула $y = f(x)$ и есть это правило: '
    + 'подставили $x$, получили высоту. Кривая на экране рисуется по частым точкам, поэтому '
    + 'подходит любая запись, а не только та, которую вы проходили в школе.</p>'
    + '<p><b>Зачем нужны нули функции?</b> Ноль это высота оси $x$. Значит корни уравнения '
    + '$f(x) = 0$ ровно там, где кривая пересекает горизонтальную ось. В экономике это привычные '
    + 'вопросы: при каком объёме прибыль обращается в ноль, при какой цене спрос исчезает. '
    + 'Здесь корни ищутся численно: отрезок делится на мелкие куски, и там, где функция меняет '
    + 'знак, корень уточняется делением пополам.</p>'
    + '<p><b>Откуда берутся вершины?</b> В вершине кривая перестаёт расти и начинает убывать, '
    + 'то есть её наклон обращается в ноль. Наклон это производная, поэтому вершины ищутся как '
    + 'нули производной. Производная считается разностью: берутся две близкие точки слева и '
    + 'справа и прирост высоты делится на прирост $x$.</p>'
    + '<p><b>Почему точка пересечения двух кривых важнее остальных?</b> В ней у обеих функций '
    + 'одно и то же значение, то есть выполнено уравнение $f_1(x) = f_2(x)$. Пересечение спроса '
    + 'и предложения даёт равновесие, пересечение выручки и издержек даёт точку безубыточности. '
    + 'Решить уравнение и найти пересечение это одно и то же действие, только записанное '
    + 'по-разному.</p>'
    + (count > 1
        ? '<p><b>Вывод.</b> Несколько кривых на одном поле сравниваются не по формулам, а по '
          + 'взаимному положению: где одна выше другой, там она и выигрывает. Именно так читаются '
          + 'почти все экономические графики.</p>'
        : '<p><b>Вывод.</b> График переводит формулу в картинку, а вопросы про уравнения в вопросы '
          + 'про точки: корень это пересечение с осью, вершина это смена направления, решение '
          + 'системы это общая точка кривых. Добавьте вторую формулу, и станет видно последнее.</p>')
    + '</div>';
}
