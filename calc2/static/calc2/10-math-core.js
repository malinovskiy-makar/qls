// Математика: разбор формул, корни, интегрирование, касание уровня.
/* ---------------------------------------------------------------------
   БЛОК 2. МАТЕМАТИКА
   «Всеядность»: любую формулу разбирает и считает Math.js. Поэтому код
   ниже одинаково работает и для прямых, и для кривых (парабол, корней…).
   --------------------------------------------------------------------- */

// Компиляция формулы P = f(Q). Возвращает { compiled, error }.
// Пользователь пишет от Q; внутри даём Math.js обе переменные (Q и x),
// чтобы принимались оба варианта записи.
/* П14. Область подстановки переменной графика: одно место на весь движок.
   Строчная буква — тот же аргумент, что заглавная; `L` синоним для рынка
   труда, `X` — для блока КПВ, где горизонталь называется товаром X.
   ⚠️ Вертикальные обозначения (`P`, `y`, `Y`) сюда НЕ входят: они значение,
   а не аргумент, и подставлять их нельзя. */
function axisScope(q, extra) {
  const c = extra || {};
  c.x = q; c.Q = q; c.q = q; c.L = q; c.l = q; c.X = q;
  return c;
}

function compileFormula(expr) {
  try {
    const compiled = math.parse(prepExpr(expr)).compile();
    // Пробный расчёт ловит опечатки сразу (L — синоним для рынка труда).
    // Там, где буквы становятся параметрами, незнакомая буква — не опечатка,
    // а будущий ползунок, поэтому на пробу подставляем ей единицу.
    const ctx = paramScope(axisScope(1));
    if (paramsAllowed()) freeSymbols(expr).forEach(n => { if (ctx[n] === undefined) ctx[n] = 1; });
    compiled.evaluate(ctx);
    return { compiled, error: null };
  } catch (e) {
    return { compiled: null, error: e.message };
  }
}

// Значение кривой в точке Q. Возвращает число или NaN (на ошибке/разрыве).
function evalCurve(curve, q) {
  // Вертикальная кривая (Фаза 15) не задаёт цену как функцию количества.
  if (curve.kind === 'vertical') return NaN;
  // Синтетическая кривая, заданная функцией (например, предложение S + налог t).
  if (curve.fn) return curve.fn(q);
  // Быстрый путь для прямых (нужен и для плавного перетаскивания).
  if (curve.linear) return curve.linear.a * q + curve.linear.b;
  try {
    const v = evalWithParams(curve.compiled, axisScope(q), curve.expr);
    return (typeof v === 'number' && isFinite(v)) ? v : NaN;
  } catch (e) {
    return NaN;
  }
}

// Определяем, линейна ли кривая: считаем наклон по трём точкам.
// Постоянный наклон -> это прямая P = a*Q + b (возвращаем {a, b}),
// иначе null. Работает для ЛЮБОЙ записи формулы (не разбираем строку).
function detectLinear(compiled) {
  const at = (q) => {
    // Значения ползунков подмешиваем: иначе «a*x» без них падает на неизвестной
    // букве и прямая считалась бы кривой (а её нельзя ни таскать, ни двигать).
    try { const v = compiled.evaluate(paramScope(axisScope(q))); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
    catch (e) { return NaN; }
  };
  /* Б30. Проверять три точки В СЕРЕДИНЕ диапазона нельзя: кусочная функция
     на этом участке бывает прямой, а на другом нет. «max(0, Q - 10)» при
     Qmax = 100 давала в точках 20, 50 и 80 значения 10, 40 и 70 — наклон
     всюду единичный, и кривая запоминалась как прямая P = Q. Дальше evalCurve
     шёл быстрым путём по этим коэффициентам, и на участке Q < 10 и график, и
     все расчёты уходили по неверной прямой.
     Смотрим сетку из 13 точек и обязательно окрестность нуля (там живут
     перехваты и постоянные затраты) и правый край. */
  const hi = CONFIG.Qmax;
  const qs = [0, hi * 0.01, hi * 0.05];
  for (let i = 1; i <= 9; i++) qs.push(hi * i / 10);
  qs.push(hi);
  const vs = qs.map(at);
  if (vs.some(isNaN)) return null;
  const a = (vs[vs.length - 1] - vs[0]) / (qs[qs.length - 1] - qs[0]);
  if (!isFinite(a)) return null;
  const b = vs[0] - a * qs[0];
  // Расхождение хоть в одной точке — не прямая. Порог берём от масштаба самих
  // значений, иначе крупные числа не пройдут проверку из-за ошибок округления.
  const scale = Math.max(1, ...vs.map(Math.abs));
  for (let i = 0; i < qs.length; i++) {
    if (Math.abs(vs[i] - (a * qs[i] + b)) > 1e-7 * scale) return null;
  }
  return { a, b };
}

/* Н7. Прямая запоминается коэффициентами один раз, и дальше evalCurve идёт
   быстрым путём. Если в формуле есть буква-параметр («100 - a*Q»), то запомнены
   коэффициенты при ТОМ значении, которое буква имела в момент разбора: ползунок
   потом двигал только число в состоянии, а кривая на графике стояла на месте.
   Ломались ровно те формулы, которые выглядят прямыми, — «100 - a*Q^2» работала,
   потому что быстрого пути у неё нет.

   Быстрый путь нужен (по нему идёт плавное перетаскивание), поэтому не убираем
   его, а обновляем: перед каждой перерисовкой сверяем значения букв, от которых
   кривая зависит, с теми, при которых её раскладывали, и пересчитываем при
   расхождении. */
function curveParamNames(curve) {
  /* Ключ кэша — формула И набор занятых сценой букв: freeSymbols отсеивает то,
     что занято сюжетом (ставка t, зарплата w), а это зависит от сцены. Кривая
     «t*Q», разобранная при видимом поле ставки, дала бы пустой список, и после
     перехода в сцену, где t свободна, кэш продолжал бы утверждать, что букв
     нет, — и Н7 к ней не применялся бы вовсе. */
  const busy = (typeof sceneReserved === 'function') ? [...sceneReserved()].sort().join(',') : '';
  const key = curve.expr + '|' + busy;
  if (curve._pNames === undefined || curve._pNamesFor !== key) {
    curve._pNamesFor = key;
    curve._pNames = (typeof freeSymbols === 'function' && curve.expr) ? freeSymbols(curve.expr) : [];
  }
  return curve._pNames;
}

function paramSignature(names) {
  const p = STATE.params || {};
  return names.map(n => n + '=' + (p[n] ? p[n].value : '?')).join(',');
}

function refreshLinearForParams() {
  /* Сумма КПВ считается один раз и живёт в кэше. Раньше кэш сбрасывался
     ЗДЕСЬ, как только менялось значение любого ползунка, и это давало ДВА
     полных пересчёта Минковского на одно открытие сцены: карточка
     перерисовывает её дважды, а между перерисовками сброс параметров успевал
     обнулить кэш (А2). Теперь у кэша есть подпись входа (ppfSumSignature), и
     значения ползунков в неё уже входят: отдельный сброс не нужен и только
     вредит. Подпись параметров всё равно ведём — по ней пересобираются
     прямые с буквой ниже. */
  const allSig = paramSignature(Object.keys(STATE.params || {}).sort());
  if (allSig !== STATE._paramsSig) STATE._paramsSig = allSig;
  (STATE.curves || []).forEach(curve => {
    // Синтетические кривые (curve.fn) считают себя сами, вертикали не про Q.
    if (!curve.compiled || curve.fn || curve.kind === 'vertical') return;
    const names = curveParamNames(curve);
    if (!names.length) return;
    const sig = paramSignature(names);
    if (sig === curve._pSig) return;
    curve._pSig = sig;
    curve.linear = detectLinear(curve.compiled);
    // Запись Q(P) держит свой разбор отдельно — обновляем и его.
    if (curve.srcForm === 'QP' && curve.srcCompiled) curve.srcLinear = detectLinearP(curve.srcCompiled);
  });
}

// Красивая запись прямой по a и b (для подписи в списке при перетаскивании).
// varName — имя переменной ('Q' по умолчанию; 'P' для записи Q(P), Фаза 1б).
/* dec — глубина округления. По умолчанию два знака, как было у всех прежних
   вызовов. Перетаскивание просит три (решение владельца 19.08) и передаёт их
   ЯВНО: печатать глубже, чем хранится в curve.linear, нельзя — запись и
   расчёт разошлись бы в последнем разряде, а это ровно та беда, из-за которой
   округление в движке вообще появилось. */
function fmtLinear(a, b, varName, dec) {
  const V = varName || 'Q';
  const pow = Math.pow(10, (dec === undefined ? 2 : dec));
  const r = (v) => Math.round(v * pow) / pow; a = r(a); b = r(b);
  if (a === 0) return `${b}`;
  if (a < 0) {
    const aa = Math.abs(a), aPart = aa === 1 ? V : `${aa}*${V}`;
    return b === 0 ? `-${aPart}` : `${b} - ${aPart}`;
  }
  const aPart = a === 1 ? V : `${a}*${V}`;
  if (b === 0) return aPart;
  return b > 0 ? `${aPart} + ${b}` : `${aPart} - ${Math.abs(b)}`;
}

/* --- Фаза 1б. Ввод Q(P): приведение к каноническому виду P = f(Q) ----------
   Вся остальная архитектура движка требует P = f(Q). Поэтому кривую, введённую
   как «объём от цены», приводим к канону ПЕРЕД использованием — двумя путями:
     • линейная Q = c + d·P (d ≠ 0)  →  явно  P = (Q − c)/d = (1/d)·Q − c/d;
     • любая другая                  →  численно: для заданного Q ищем P, при
       котором Q(P) = Q (сканирование сетки + бисекция — тот же метод, что
       findEquilibrium/findRoot, только по оси цен).
   Формула хранится КАК ВВЕДЕНА (curve.srcExpr), в математику уходит канон. */

// Компиляция формулы Q = f(P). Переменные: P (основная), p и x — синонимы.
function compileFormulaP(expr) {
  try {
    const compiled = math.parse(expr).compile();
    compiled.evaluate(scopeFor(expr, { P: 1, p: 1, x: 1 }));   // пробный расчёт ловит опечатки
    return { compiled, error: null };
  } catch (e) {
    return { compiled: null, error: e.message };
  }
}

// Значение Q(P) в точке P. NaN — на ошибке/разрыве.
function evalQofP(compiled, p) {
  try { const v = compiled.evaluate(paramScope({ P: p, p: p, x: p })); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
  catch (e) { return NaN; }
}

// Линейность Q(P) по трём точкам: Q = c + d·P → { c, d } или null.
// Сетка проб по цене (0.2/0.5/0.8 от Pmax) — зеркало detectLinear по количеству.
function detectLinearP(compiled) {
  const at = (p) => evalQofP(compiled, p);
  const p1 = CONFIG.Pmax * 0.2, p2 = CONFIG.Pmax * 0.5, p3 = CONFIG.Pmax * 0.8;
  const f1 = at(p1), f2 = at(p2), f3 = at(p3);
  if (isNaN(f1) || isNaN(f2) || isNaN(f3)) return null;
  const d12 = (f2 - f1) / (p2 - p1), d23 = (f3 - f2) / (p3 - p2);
  if (Math.abs(d12 - d23) > 1e-6 * (1 + Math.abs(d12))) return null;   // наклон «гуляет» → нелинейная
  const d = d12, c = f1 - d * p1;
  return { c, d };
}

// Численное обращение Q(P): найти цену P ≥ 0, при которой Q(P) = q.
// Сканируем сетку цен [0, Pmax·3], на смене знака уточняем бисекцией.
// Работает и для убывающей (спрос), и для возрастающей (предложение) функции.
function invertQofP(compiled, q) {
  const g = (p) => { const v = evalQofP(compiled, p); return isNaN(v) ? NaN : v - q; };
  const hi = Math.max(1, CONFIG.Pmax * 3);
  const N = 240;                       // сетка проб: компромисс «точность / скорость перерисовки»
  let prevP = 0, prevG = g(0);
  if (prevG === 0) return 0;
  for (let i = 1; i <= N; i++) {
    const p = hi * i / N, cur = g(p);
    if (!isNaN(prevG) && !isNaN(cur) && prevG * cur <= 0 && prevG !== cur) {
      if (cur === 0) return p;
      return bisect(g, prevP, p);
    }
    prevP = p; prevG = cur;
  }
  return NaN;                          // цены, дающей такой объём, в первой четверти нет
}

// Собрать кривую из формулы Q(P): вернуть поля для STATE.curves или { error }.
// Возвращает { linear|fn, srcCompiled, srcLinear } — дальше используется как обычная кривая.
function buildCurveFromQP(expr) {
  const { compiled, error } = compileFormulaP(expr);
  if (error) return { error };
  const lp = detectLinearP(compiled);
  if (lp) {
    if (Math.abs(lp.d) < 1e-9) {
      // Q не зависит от цены: кривая вертикальна (совершенно неэластична),
      // как P = f(Q) она не записывается — честно говорим об этом.
      return { error: 'объём не зависит от цены, такая кривая вертикальна и не задаётся как P = f(Q)' };
    }
    // Q = c + d·P  ⇒  P = (1/d)·Q − c/d
    return { srcCompiled: compiled, srcLinear: lp, linear: { a: 1 / lp.d, b: -lp.c / lp.d }, fn: null };
  }
  // Нелинейная: канон задаём численным обращением (кэш не нужен — вызовы редкие и дешёвые).
  return { srcCompiled: compiled, srcLinear: null, linear: null, fn: (q) => invertQofP(compiled, q) };
}

/* --- Фаза 15. ВЕРТИКАЛЬНАЯ кривая -----------------------------------------
   Все обычные кривые движка имеют вид P = f(Q). Для макромоделей нужен ещё
   один тип: вертикальная прямая — фиксированное количество при ЛЮБОЙ цене
   (LRAS на потенциальном выпуске, долгосрочная кривая Филлипса при u*,
   предложение денег, заданное центральным банком).
   Как P = f(Q) она не записывается, поэтому у неё свой kind и своя ветка
   в поиске равновесия. «Почти вертикальную» кривую с огромным наклоном
   гнать через бисекцию нельзя — численно неустойчиво. */
function makeVerticalCurve(atQ, opts) {
  return Object.assign({ kind: 'vertical', atQ: atQ, linear: null, fn: null, compiled: null,
                         visible: true, color: null }, opts || {});
}
function isVertical(c) { return !!(c && c.kind === 'vertical'); }

// Численный поиск равновесия D(Q) = S(Q).
// Идём по мелкой сетке, ищем интервал смены знака g = D - S, уточняем
// бисекцией. Работает для ЛЮБЫХ кривых (прямых и нелинейных).
// Если пересечения в первой четверти нет — возвращаем null (не падаем).
// qMaxOpt — необязательная ВЕРХНЯЯ ГРАНИЦА ПОИСКА. По умолчанию это край видимой
// области (как было), но макромодели ищут равновесие ДО того, как подобран масштаб,
// и передают свой запас — иначе пересечение за краем кадра просто не находится.
function findEquilibrium(D, S, qMaxOpt) {
  // Фаза 15: одна из кривых вертикальна ⇒ решение тривиально, бисекция не нужна.
  if (isVertical(D) || isVertical(S)) {
    if (isVertical(D) && isVertical(S)) return null;   // две вертикали: либо совпали, либо решения нет
    const v = isVertical(D) ? D : S, other = isVertical(D) ? S : D;
    const Q = v.atQ, P = evalCurve(other, Q);
    return (isFinite(P) && Q >= 0 && P >= 0) ? { Q, P } : null;
  }
  const g = (q) => {
    const d = evalCurve(D, q), s = evalCurve(S, q);
    return (isNaN(d) || isNaN(s)) ? NaN : d - s;
  };
  const priceAt = (q) => (evalCurve(D, q) + evalCurve(S, q)) / 2;
  const QM = (qMaxOpt != null && qMaxOpt > 0) ? qMaxOpt : CONFIG.Qmax;
  const N = 1000;                       // число узлов сетки
  let prevQ = 0, prevG = g(0);
  for (let i = 1; i <= N; i++) {
    const q = QM * i / N;
    const cur = g(q);
    // Смена знака (или попадание точно в ноль на границе интервала).
    if (!isNaN(prevG) && !isNaN(cur) && prevG * cur <= 0 && prevG !== cur) {
      const qstar = (prevG === 0) ? prevQ : (cur === 0 ? q : bisect(g, prevQ, q));
      const p = priceAt(qstar);
      if (qstar >= 0 && p >= 0) return { Q: qstar, P: p };   // только первая четверть
    }
    prevQ = q; prevG = cur;
  }
  return null;
}

// Бисекция: уточняет корень f на отрезке [lo, hi], где знак f меняется.
function bisect(f, lo, hi) {
  let flo = f(lo);
  for (let k = 0; k < 100; k++) {
    const mid = (lo + hi) / 2, fm = f(mid);
    if (fm === 0 || (hi - lo) < 1e-9) return mid;
    if (flo * fm < 0) hi = mid; else { lo = mid; flo = fm; }
  }
  return (lo + hi) / 2;
}

// Численное интегрирование методом трапеций (мелкая сетка из n шагов).
// Через него считаем площади CS/PS — работает для ЛЮБОЙ формы кривой.
function integrate(f, a, b, n = 1000) {
  if (!(b > a)) return 0;
  const h = (b - a) / n;
  let sum = 0.5 * (f(a) + f(b));
  for (let i = 1; i < n; i++) sum += f(a + i * h);
  return sum * h;
}

/* Площадь между двумя кривыми на отрезке (Б31).

   Считать её как МОДУЛЬ ИНТЕГРАЛА разности верно ровно до тех пор, пока
   разность не меняет знак. При двух и более пересечениях куски с разными
   знаками гасят друг друга, и площадь выходит заниженной: у потерь общества
   это прямо неверное число. Поэтому режем отрезок по нулям разности и
   складываем МОДУЛИ кусков. */
/* Места, где разность меняет знак на отрезке.

   Проверять «произведение соседних значений отрицательно» недостаточно: если
   ноль приходится РОВНО НА УЗЕЛ сетки, оба произведения равны нулю, и смена
   знака теряется целиком. Случай не выдуманный: у прямых D и S равновесие
   часто попадает ровно на круглое число. Поэтому следим за последним НЕнулевым
   знаком, а сам ноль в узле принимаем за место пересечения. */
function signChanges(g, lo, hi, n = 400) {
  const out = [];
  if (!(hi > lo)) return out;
  const step = (hi - lo) / n;
  let lastSign = 0, lastX = lo, zeroX = null;
  for (let i = 0; i <= n; i++) {
    const x = lo + step * i, v = g(x);
    if (isNaN(v)) continue;
    const s = v > 0 ? 1 : (v < 0 ? -1 : 0);
    if (s === 0) { zeroX = x; continue; }
    if (lastSign !== 0 && s !== lastSign) out.push(zeroX != null ? zeroX : bisect(g, lastX, x));
    lastSign = s; lastX = x; zeroX = null;
  }
  return out;
}

function areaBetween(g, lo, hi, n = 400) {
  if (!(hi > lo)) return 0;
  let total = 0, from = lo;
  signChanges(g, lo, hi, n).forEach(root => {
    total += Math.abs(integrate(g, from, root));
    from = root;
  });
  return total + Math.abs(integrate(g, from, hi));
}

// Сколько раз разность меняет знак на отрезке: столько же и пересечений.
function crossingCount(g, lo, hi, n = 400) { return signChanges(g, lo, hi, n).length; }

// Универсальный поиск корня g(Q)=0 в первой четверти [0, Qmax].
// Сканируем мелкую сетку, на смене знака уточняем бисекцией; null — если корня нет.
// Та же идея, что в findEquilibrium, но для любой функции (обратные кривые, MR=MC).
function findRoot(g) {
  const N = 1000;
  let prevQ = 0, prevG = g(0);
  for (let i = 1; i <= N; i++) {
    const q = CONFIG.Qmax * i / N;
    const cur = g(q);
    if (!isNaN(prevG) && !isNaN(cur) && prevG * cur <= 0 && prevG !== cur) {
      return (prevG === 0) ? prevQ : (cur === 0 ? q : bisect(g, prevQ, q));
    }
    prevQ = q; prevG = cur;
  }
  return null;
}

// Обратная функция кривой: Q, при котором P(Q) = targetP (то есть D⁻¹ или S⁻¹).
// У вертикальной кривой объём один и тот же при любой цене (Фаза 15).
function invCurve(curve, targetP) {
  if (isVertical(curve)) return curve.atQ;
  return findRoot(q => { const v = evalCurve(curve, q); return isNaN(v) ? NaN : v - targetP; });
}

// Производная кривой dP/dQ численно (центральная разность). Нужна для эластичности (Задача 2).
function curveDeriv(curve, q) {
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const a = evalCurve(curve, q + h), b = evalCurve(curve, q - h);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / (2 * h);
}

// Внешние предельные издержки (Задача 4): константа или функция от Q (как спрос — переменная Q).
function compileExt(expr) {
  try { const c = math.parse(expr).compile(); c.evaluate(scopeFor(expr, axisScope(1))); return { compiled: c, error: null }; }
  catch (e) { return { compiled: null, error: e.message }; }
}
function evalExt(q) {
  if (!STATE.extCompiled) return NaN;
  try {
    const v = STATE.extCompiled.evaluate(scopeFor(STATE.extExpr, axisScope(q)));
    return (typeof v === 'number' && isFinite(v)) ? v : NaN;
  } catch (e) { return NaN; }
}

/* =====================================================================
   БЛОК 2б. ДВИЖОК КАСАНИЯ УРОВНЯ (Фаза 7) — общий для потребителя и фирмы.

   Работает с функцией ДВУХ переменных f(a, b). Геометрический смысл
   переменных движку не важен: для потребителя это полезность U(x, y),
   для фирмы — выпуск Q(L, K). Отсюда и переиспользование: кривая
   безразличия и изокванта — одна и та же математика.

   Всё численно, закрытых формул нет — поэтому произвольная пользовательская
   функция «просто работает», а для стандартных форм численный ответ обязан
   совпасть с известной аналитикой (это и есть проверка правильности).
   ===================================================================== */

// Компиляция функции двух переменных. Пользователь пишет через x,y (потребитель)
// или L,K (фирма) — внутрь подаём обе пары синонимов, поэтому годятся обе записи.
/* Скомпилированная формула двух переменных запоминается по тексту (А55).
   Сцены зовут compileTwoVar из своего пересчёта, а пересчёт идёт на каждую
   перерисовку: изокванта разбирала и компилировала одну и ту же строку
   заново по десять раз в секунду, пока пользователь просто двигал ползунок. */
const _twoVarCache = new Map();
function compileTwoVar(expr) {
  const key = String(expr || '');
  const hit = _twoVarCache.get(key);
  if (hit) return hit;
  const res = compileTwoVarUncached(expr);
  if (_twoVarCache.size > 200) _twoVarCache.clear();
  _twoVarCache.set(key, res);
  return res;
}

function compileTwoVarUncached(expr) {
  try {
    const compiled = math.parse(expr).compile();
    compiled.evaluate(scopeFor(expr, { x: 1, y: 1, L: 1, K: 1 }));   // пробный расчёт ловит опечатки
    // Исходный текст носим на самом скомпилированном узле: evalTwoVar получает
    // только его, а буквы-параметры надо подставлять по тексту формулы.
    compiled._src = String(expr || '');
    return { compiled, error: null };
  } catch (e) { return { compiled: null, error: e.message }; }
}
function evalTwoVar(compiled, a, b) {
  try {
    const v = compiled.evaluate(scopeFor(compiled._src, { x: a, y: b, L: a, K: b }));
    return (typeof v === 'number' && isFinite(v)) ? v : NaN;
  } catch (e) { return NaN; }
}

// Найти b ∈ [0, bMax], при котором f(a, b) = level — бисекцией по b.
// Предполагается, что f монотонно РАСТЁТ по b: это стандартное свойство функций
// полезности и выпуска (положительная предельная полезность / производительность).
// Если корня в разумном диапазоне нет — возвращаем null (точку просто пропустим,
// а не уроним всю кривую).
function solveLevelB(f, level, a, bMax) {
  const g = (b) => { const v = f(a, b); return (typeof v === 'number' && isFinite(v)) ? v - level : NaN; };
  let lo = 0, hi = bMax;
  let glo = g(lo);
  if (isNaN(glo)) { lo = bMax * 1e-9; glo = g(lo); }   // f может быть не определена ровно в нуле
  const ghi = g(hi);
  if (isNaN(glo) || isNaN(ghi)) return null;
  if (glo > 0) return null;    // уровень достигнут уже при b=0 — кривая ниже сетки
  if (ghi < 0) return null;    // даже при b=bMax уровня не достичь
  /* Восьмидесяти делений пополам не нужно никогда: интервал [0, bMax] за 40
     шагов сжимается до триллионной доли, а на экране различима миллионная.
     Выходим, как только точность заведомо избыточна, — это вдвое меньше
     вычислений функции на каждой точке кривой уровня (А55). */
  const eps = Math.max(1e-12, Math.abs(bMax) * 1e-9);
  for (let k = 0; k < 60; k++) {
    if (hi - lo < eps) break;
    const mid = (lo + hi) / 2, gm = g(mid);
    if (isNaN(gm)) { lo = mid; continue; }
    if (gm === 0) return mid;
    if (gm < 0) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

/* Трассировка НЕЯВНОЙ кривой уровня f(a, b) = level по сетке значений a.
   Возвращает массив [a, b] или null в точках, где уровень недостижим.

   Результат запоминается на одну перерисовку (А55). Одна и та же кривая
   уровня считается по нескольку раз за кадр: её рисует сцена, её же просит
   движок прокатывания точки, её же берут ключевые точки.

   Ключ памяти — сама функция плюс её аргументы плюс ЗНАЧЕНИЯ ПОЛЗУНКОВ.
   Сегодня сцены пересоздают функцию на каждый пересчёт, и одного ключа по
   функции хватило бы; но функция считает через общую область видимости, куда
   подмешаны значения букв-параметров, и стоит будущей сцене запомнить свою
   функцию — запись молча устареет, а кривая замрёт при движении ползунка.
   Подпись параметров снимает этот класс целиком и стоит копейки. */
const _levelCache = new WeakMap();
function traceLevelCurve(f, level, aMax, bMax, steps) {
  const N = steps || 200;
  const psig = (typeof paramSignature === 'function')
    ? paramSignature(Object.keys(STATE.params || {}).sort()) : '';
  const key = level + '|' + aMax + '|' + bMax + '|' + N + '|' + psig;
  let box = _levelCache.get(f);
  if (box) {
    const hit = box.get(key);
    if (hit) return hit;
  } else {
    box = new Map();
    _levelCache.set(f, box);
  }
  const out = [];
  for (let i = 0; i <= N; i++) {
    const a = aMax * i / N;
    const b = solveLevelB(f, level, a, bMax);
    out.push((b == null) ? null : [a, b]);
  }
  if (box.size > 32) box.clear();
  box.set(key, out);
  return out;
}

// Частные производные численно (центральная разность, у границы — односторонняя).
function partialA(f, a, b) {
  const h = Math.max(1e-6, Math.abs(a) * 1e-5), lo = Math.max(0, a - h);
  const v1 = f(a + h, b), v0 = f(lo, b);
  return (isFinite(v1) && isFinite(v0)) ? (v1 - v0) / ((a + h) - lo) : NaN;
}
function partialB(f, a, b) {
  const h = Math.max(1e-6, Math.abs(b) * 1e-5), lo = Math.max(0, b - h);
  const v1 = f(a, b + h), v0 = f(a, lo);
  return (isFinite(v1) && isFinite(v0)) ? (v1 - v0) / ((b + h) - lo) : NaN;
}
// Предельная норма замещения (для фирмы — технического замещения MRTS):
// MRS = (∂f/∂a)/(∂f/∂b) — сколько b компенсирует единицу a на том же уровне.
function mrsAt(f, a, b) {
  const pa = partialA(f, a, b), pb = partialB(f, a, b);
  return (isFinite(pa) && isFinite(pb) && Math.abs(pb) > 1e-12) ? pa / pb : NaN;
}

// Максимум f(a, b) при линейном ограничении priceA·a + priceB·b = income.
// Параметризуем по a: b = (income − priceA·a)/priceB, ищем argmax ТРОЙНЫМ поиском
// (унимодальность вдоль бюджетной линии — стандартное свойство поддерживаемых
// видов предпочтений). Закрытых формул для Кобба-Дугласа и т.п. НЕТ намеренно:
// один численный путь для любой функции, а совпадение с аналитикой — проверка.
// Концы отрезка проверяем отдельно: при линейных предпочтениях (совершенные
// субституты) оптимум лежит ровно в углу, куда тройной поиск сам может не дойти.
function optimizeAlongConstraint(f, priceA, priceB, income) {
  if (!(priceA > 0) || !(priceB > 0) || !(income > 0)) return null;
  const aMax = income / priceA, bMax = income / priceB;
  const val = (a) => {
    if (a < 0 || a > aMax) return -Infinity;
    const b = Math.max(0, (income - priceA * a) / priceB);
    const v = f(a, b);
    return (typeof v === 'number' && isFinite(v)) ? v : -Infinity;
  };
  let lo = 0, hi = aMax;
  for (let k = 0; k < 100; k++) {
    const m1 = lo + (hi - lo) / 3, m2 = hi - (hi - lo) / 3;
    if (val(m1) < val(m2)) lo = m1; else hi = m2;
  }
  let bestA = (lo + hi) / 2, bestV = val(bestA);
  [0, aMax].forEach(c => { const v = val(c); if (v > bestV + 1e-12) { bestV = v; bestA = c; } });
  const b = Math.max(0, (income - priceA * bestA) / priceB);
  return { a: bestA, b, value: bestV, aMax, bMax, mrs: mrsAt(f, bestA, b) };
}


/* =====================================================================
   ВЕЛИЧИНЫ: одна логика набора для экрана, панели и файла (А28 · А46)

   Было: одна и та же величина писалась тремя разными способами. В правой
   панели «P_b» набиралось формулой, на холсте то же самое стояло обычным
   текстом «Pb=60», а в файле .tex не было ни одного математического режима
   вовсе: двенадцать узлов подписи, из них с индексами ноль. Даже внутри
   холста не было согласия: «Q₁» пользовалось юникодной цифрой, а «Pb» и
   «Ps» — обычными буквами.

   Здесь разбор подписи на части и три способа её напечатать. Кто рисует —
   тот и выбирает способ, но РЕШЕНИЕ, что здесь величина, а что проза,
   принимается один раз и в одном месте.
   ===================================================================== */

// Юникодные индексы и степени, которые приходят из подписей сцен.
const QTY_SUB = { '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9' };
const QTY_SUP = { '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9' };
const QTY_GREEK = {
  'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma', 'δ': '\\delta', 'ε': '\\varepsilon',
  'θ': '\\theta', 'λ': '\\lambda', 'μ': '\\mu', 'π': '\\pi', 'ρ': '\\rho',
  'σ': '\\sigma', 'τ': '\\tau', 'φ': '\\varphi', 'ω': '\\omega',
  'Δ': '\\Delta', 'Σ': '\\Sigma', 'Ω': '\\Omega', 'Π': '\\Pi',
};
// Операторы и служебные знаки, которые в формуле печатаются как есть.
const QTY_OPS = {
  '−': '-', '–': '-', '·': '\\cdot ', '×': '\\times ', '÷': '\\div ',
  '≈': '\\approx ', '≤': '\\le ', '≥': '\\ge ', '≠': '\\ne ', '→': '\\to ',
  '±': '\\pm ', '∞': '\\infty ', '∈': '\\in ', '∗': '^*', '*': '^*',
};

// Хвосты, которые в экономике всегда означают индекс, а не продолжение слова.
const QTY_INDEX_WORDS = ['min', 'max', 'avg', 'opt', 'eq', 'tot', 'reg', 'imp', 'exp'];

/* ⚠️ ИМЯ ФУНКЦИИ — ОПЕРАТОР, А НЕ СИМВОЛ С ИНДЕКСОМ (Добавка Б).
   Пока подпись «$\max TP$: $MP = 0$» уезжала на холст сырой, вместе с
   долларами, разбирать было нечего. После чистки долларов (п. 42) её увидел
   общий разбор: правило «заглавная плюс одна-две строчные — это индекс»
   поймало «max» и напечатало «m» с подстрочным «ax». Опечатки в тексте нет,
   ошибка в разборе: имя функции целиком, и резать его нельзя.
   Тот же класс — min, log, ln, lim, exp, sin, cos, tan. */
const QTY_FUNC_WORDS = ['max', 'min', 'log', 'ln', 'lim', 'exp', 'sin', 'cos', 'tan', 'abs'];

function qtyHasCyrillic(s) { return /[А-Яа-яЁё]/.test(String(s || '')); }

/* Подпись — это величина? Величиной считаем запись, где есть латинская буква
   или греческая, нет кириллицы, и нет длинных слов латиницей (иначе «Solution»
   уехало бы в математику). Проза остаётся прозой. */
function qtyIsQuantity(raw) {
  const s = String(raw == null ? '' : raw).trim();
  if (!s || qtyHasCyrillic(s)) return false;
  if (!/[A-Za-zα-ωΑ-Ω]/.test(s)) return false;      // одни цифры — не величина
  if (/[A-Za-z]{5,}/.test(s)) return false;          // длинное слово — это слово
  return true;
}

/* Разбор записи на куски: {kind:'sym'|'num'|'op'|'txt', s, sub, sup}.
   Правило имени: пробег заглавными (MC, ATC, DWL) — это аббревиатура, её не
   трогаем; «Заглавная + строчные» (Pb, Qd, Wmin) — это символ с индексом;
   цифры сразу после символа — тоже индекс (Q1 → Q с индексом 1). */
function qtyParts(raw) {
  const s = String(raw == null ? '' : raw);
  const out = [];
  let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (QTY_GREEK[ch]) { out.push({ kind: 'sym', s: ch, greek: QTY_GREEK[ch], sub: '', sup: '' }); i++; }
    else if (/[A-Za-z]/.test(ch)) {
      let run = '';
      while (i < s.length && /[A-Za-z]/.test(s[i])) { run += s[i]; i++; }
      let name = run, sub = '';
      /* Пробег заглавными (MC, ATC, DWL, LRAS) — аббревиатура, её не трогаем.
         «Заглавная + строчные» — символ с индексом, но ТОЛЬКО когда хвост
         похож на индекс: одна-две буквы (Pb, Qd, Qm) или известное слово
         (Wmin, Pmax). Иначе своё имя кривой вроде «Test» превратилось бы в
         «T» с индексом «est» — на экране это выглядит опечаткой. */
      if (run.length > 1 && !/^[A-Z]+$/.test(run)
          && QTY_FUNC_WORDS.indexOf(run.toLowerCase()) < 0) {
        const tail = run.slice(1);
        if (/^[a-z]{1,2}$/.test(tail) || QTY_INDEX_WORDS.indexOf(tail) >= 0) {
          name = run[0]; sub = tail;
        }
      }
      const part = { kind: 'sym', s: name, sub, sup: '' };
      // Индексы и степени сразу за именем.
      while (i < s.length && (QTY_SUB[s[i]] || QTY_SUP[s[i]] || /[0-9]/.test(s[i]))) {
        if (QTY_SUB[s[i]]) part.sub += QTY_SUB[s[i]];
        else if (QTY_SUP[s[i]]) part.sup += QTY_SUP[s[i]];
        else part.sub += s[i];
        i++;
      }
      if (s[i] === '*' || s[i] === '∗') { part.sup += '*'; i++; }
      out.push(part);
    } else if (/[0-9]/.test(ch)) {
      let run = '';
      while (i < s.length && /[0-9.,]/.test(s[i])) { run += s[i]; i++; }
      out.push({ kind: 'num', s: run });
    } else { out.push({ kind: 'op', s: ch }); i++; }
  }
  return out;
}

/* Запись величины в LaTeX. Проза возвращается как обычный текст (\text{}),
   поэтому функцию можно звать на любой подписи не разбираясь заранее. */
function qtyLatex(raw) {
  const parts = qtyParts(raw);
  let out = '';
  parts.forEach(p => {
    if (p.kind === 'sym') {
      out += (p.greek || p.s);
      if (p.sub) out += (p.sub.length > 1 ? '_{' + p.sub + '}' : '_' + p.sub);
      if (p.sup) out += (p.sup.length > 1 ? '^{' + p.sup + '}' : '^' + p.sup);
    } else if (p.kind === 'num') out += p.s;
    else {
      const ch = p.s;
      // Пробел внутри математики LaTeX игнорирует, поэтому «S + t» без явной
      // отбивки склеилось бы в «S+t». Ставим тонкий пробел.
      if (ch === ' ') out += '\\,';
      else if (QTY_OPS[ch] !== undefined) out += QTY_OPS[ch];
      else if (ch === '%') out += '\\%';
      // Знак равенства отбивается с обеих сторон: «P_b = 60» читается, а
      // «P_b=60» выглядит как машинный вывод.
      else if (ch === '=') out += ' = ';
      else out += ch;
    }
  });
  // Двойная отбивка около знака равенства ни к чему.
  return out.replace(/\\,\s*=\s*/g, ' = ').replace(/\s*=\s*\\,/g, ' = ').replace(/ {2,}/g, ' ');
}
