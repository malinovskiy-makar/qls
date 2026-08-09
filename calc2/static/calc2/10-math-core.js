// Математика: разбор формул, корни, интегрирование, касание уровня.
/* ---------------------------------------------------------------------
   БЛОК 2. МАТЕМАТИКА
   «Всеядность»: любую формулу разбирает и считает Math.js. Поэтому код
   ниже одинаково работает и для прямых, и для кривых (парабол, корней…).
   --------------------------------------------------------------------- */

// Компиляция формулы P = f(Q). Возвращает { compiled, error }.
// Пользователь пишет от Q; внутри даём Math.js обе переменные (Q и x),
// чтобы принимались оба варианта записи.
function compileFormula(expr) {
  try {
    const compiled = math.parse(prepExpr(expr)).compile();
    // Пробный расчёт ловит опечатки сразу (L — синоним для рынка труда).
    // Там, где буквы становятся параметрами, незнакомая буква — не опечатка,
    // а будущий ползунок, поэтому на пробу подставляем ей единицу.
    const ctx = paramScope({ x: 1, Q: 1, L: 1 });
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
    const v = evalWithParams(curve.compiled, { x: q, Q: q, L: q }, curve.expr);   // L — синоним переменной (рынок труда)
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
    try { const v = compiled.evaluate(paramScope({ x: q, Q: q, L: q })); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
    catch (e) { return NaN; }
  };
  const q1 = CONFIG.Qmax * 0.2, q2 = CONFIG.Qmax * 0.5, q3 = CONFIG.Qmax * 0.8;
  const f1 = at(q1), f2 = at(q2), f3 = at(q3);
  if (isNaN(f1) || isNaN(f2) || isNaN(f3)) return null;
  const a12 = (f2 - f1) / (q2 - q1), a23 = (f3 - f2) / (q3 - q2);
  if (Math.abs(a12 - a23) > 1e-6 * (1 + Math.abs(a12))) return null;  // наклон «гуляет» -> нелинейная
  const a = a12, b = f1 - a * q1;
  return { a, b };
}

// Красивая запись прямой по a и b (для подписи в списке при перетаскивании).
// varName — имя переменной ('Q' по умолчанию; 'P' для записи Q(P), Фаза 1б).
function fmtLinear(a, b, varName) {
  const V = varName || 'Q';
  const r = (v) => Math.round(v * 100) / 100; a = r(a); b = r(b);
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
  try { const c = math.parse(expr).compile(); c.evaluate(scopeFor(expr, { x: 1, Q: 1 })); return { compiled: c, error: null }; }
  catch (e) { return { compiled: null, error: e.message }; }
}
function evalExt(q) {
  if (!STATE.extCompiled) return NaN;
  try {
    const v = STATE.extCompiled.evaluate(scopeFor(STATE.extExpr, { x: q, Q: q }));
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
function compileTwoVar(expr) {
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
  for (let k = 0; k < 80; k++) {
    const mid = (lo + hi) / 2, gm = g(mid);
    if (isNaN(gm)) { lo = mid; continue; }
    if (gm === 0) return mid;
    if (gm < 0) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// Трассировка НЕЯВНОЙ кривой уровня f(a, b) = level по сетке значений a.
// Возвращает массив [a, b] или null в точках, где уровень недостижим.
function traceLevelCurve(f, level, aMax, bMax, steps) {
  const N = steps || 200, out = [];
  for (let i = 0; i <= N; i++) {
    const a = aMax * i / N;
    const b = solveLevelB(f, level, a, bMax);
    out.push((b == null) ? null : [a, b]);
  }
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

