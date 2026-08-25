// КПВ: одна кривая, сумма нескольких, торговля.
/* ---------------------------------------------------------------------
   БЛОК 12. КПВ — граница производственных возможностей (Задача 3).
   Другой тип осей: по горизонтали товар X, по вертикали товар Y.
   Граница Y = f(X). Наклон $\left|\frac{dY}{dX}\right|$ — альтернативные издержки X в единицах Y.
   Своя компиляция (переменная X), но координаты/оси — общие (drawAxes('X','Y')).
   --------------------------------------------------------------------- */

// Компиляция Y = f(X). В отличие от рыночной — переменная X (и x как синоним).
/* ── Единый ввод кривой КПВ (Фаза 11) ─────────────────────────────────
   Одна строка на все случаи: пользователь пишет уравнение целиком, а какой
   оно формы — разбираемся сами.

     y = 100 - x        явная: сразу считаем
     x = 50 - 0.5*y     обратная: приводим численно, для каждого x ищем свой y
     x^2 + y^2 = 25     неявная: то же самое, но общий вид

   Раньше форму надо было выбрать кнопками заранее, и поле принимало только
   правую часть. Возвращаем { f(x), kind, error }; f — всегда «Y от X».  */
function parsePpfEquation(src) {
  const t = String(src || '').trim();
  if (!t) return { error: 'Пустая строка.' };
  const eq = topLevelEqIndex(t);

  // Явная запись: слева одинокая буква вертикальной оси.
  if (eq >= 0) {
    const lhs = t.slice(0, eq).trim(), rhs = t.slice(eq + 1).trim();
    if (/^[yY]$/.test(lhs)) {
      const r = compilePpf(rhs);
      if (!r.compiled) return { error: r.error };
      return { kind: 'explicit', src: rhs, f: (x) => ppfEvalWith(r.compiled, x) };
    }
    // Обратная запись x = g(y): считаем g и обращаем численно.
    if (/^[xX]$/.test(lhs)) {
      const g = parseYofX(rhs);
      if (g.error) return { error: g.error };
      return { kind: 'inverse', src: rhs, f: makeInverseF(g.f) };
    }
  }
  // Без знака равенства — это просто правая часть «Y = …», как было раньше.
  if (eq < 0) {
    const r = compilePpf(t);
    if (!r.compiled) return { error: r.error };
    return { kind: 'explicit', src: t, f: (x) => ppfEvalWith(r.compiled, x) };
  }
  // Всё остальное — неявное уравнение F(x, y) = G(x, y).
  const G = parseConstraint(t);
  if (!G) return { error: 'Не понял уравнение.' };
  return { kind: 'implicit', src: t, f: makeImplicitF(G) };
}

// Функция одной переменной, где переменная названа y (для записи x = g(y)).
function parseYofX(rhs) {
  try {
    const compiled = math.parse(prepExpr(rhs)).compile();
    const probe = scopeFor(rhs, { y: 1, Y: 1, x: 1, X: 1 });
    compiled.evaluate(probe);
    return { f: (y) => {
      try {
        const v = compiled.evaluate(scopeFor(rhs, { y: y, Y: y }));
        return (typeof v === 'number' && isFinite(v)) ? v : NaN;
      } catch (e) { return NaN; }
    } };
  } catch (e) { return { error: e.message }; }
}

/* Обращение x = g(y) в y = f(x). Сканируем y сверху вниз и берём первую
   смену знака у g(y) − x: КПВ убывает, поэтому корень там ровно один. */
function makeInverseF(g) {
  return (x) => {
    const hi = Math.max(CONFIG.Pmax * 4, 1e3);
    const h = (y) => { const v = g(y); return isFinite(v) ? v - x : NaN; };
    const N = 400;
    let prevY = 0, prevV = h(0);
    for (let i = 1; i <= N; i++) {
      const y = hi * i / N, v = h(y);
      if (!isNaN(prevV) && !isNaN(v) && prevV * v <= 0 && prevV !== v) {
        return (prevV === 0) ? prevY : (v === 0 ? y : bisect(h, prevY, y));
      }
      prevY = y; prevV = v;
    }
    return NaN;
  };
}

/* Неявное F(x, y) = 0: для каждого x ищем наибольший неотрицательный корень
   по y. Наибольший, а не первый: у окружности x² + y² = 25 нас интересует
   верхняя дуга, она и есть граница возможностей. */
function makeImplicitF(G) {
  return (x) => {
    const hi = Math.max(CONFIG.Pmax * 2, 1e2);
    const g = (y) => G(x, y);
    const N = 400;
    let found = NaN, prevY = 0, prevV = g(0);
    for (let i = 1; i <= N; i++) {
      const y = hi * i / N, v = g(y);
      if (!isNaN(prevV) && !isNaN(v) && prevV * v <= 0 && prevV !== v) {
        const r = (prevV === 0) ? prevY : (v === 0 ? y : bisect(g, prevY, y));
        if (isFinite(r)) found = r;
      }
      prevY = y; prevV = v;
    }
    return found;
  };
}

/* Разбор формулы КПВ запоминается по тексту (А2). Кривые складываются по
   Минковскому, и на каждую точку суммы приходится несколько сотен вычислений
   слагаемых; сам разбор при этом шёл заново на каждую перерисовку. */
const _ppfCompileCache = new Map();
function compilePpf(expr) {
  const key = String(expr || '');
  const hit = _ppfCompileCache.get(key);
  if (hit) return hit;
  let res;
  try {
    const compiled = math.parse(prepExpr(expr)).compile();
    compiled.evaluate(scopeFor(expr, { x: 1, X: 1 }));   // пробный расчёт ловит опечатки
    /* Исходный текст носим на самом узле — как это давно делает compileTwoVar.
       Он нужен расчёту: по нему ppfEvalWith узнаёт, какие буквы в формуле есть,
       и подставляет единицу той, у которой ползунка ещё нет. */
    compiled._src = String(expr || '');
    res = { compiled, error: null };
  } catch (e) { res = { compiled: null, error: e.message }; }
  if (_ppfCompileCache.size > 200) _ppfCompileCache.clear();
  _ppfCompileCache.set(key, res);
  return res;
}

// Значение границы Y в точке X. Считает разобранное уравнение (Фаза 11):
// одинаково для явной, обратной и неявной записи.
function evalPpf(x) {
  if (!STATE.ppfF) return NaN;
  const v = STATE.ppfF(x);
  return (typeof v === 'number' && isFinite(v)) ? v : NaN;
}

// Наклон границы dY/dX численно (центральная разность). |наклон| = альтернативные издержки X.
function ppfSlope(x) {
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const a = evalPpf(x + h), b = evalPpf(x - h);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / (2 * h);
}

// Зажать X в допустимый диапазон: [0, Qmax] и не дальше точки, где Y уходит ниже 0.
function clampPpfX(x) {
  x = Math.max(0, Math.min(CONFIG.Qmax, x));
  if (evalPpf(x) < 0) { const r = findRoot(evalPpf); if (r != null) x = Math.min(x, r); }
  return x;
}

/* Тип КПВ по тому, как ведут себя альтернативные издержки вдоль кривой.
   П40: раньше всё, что не прямая, называлось «вогнутая (растущие альт. изд.)».
   На кусочной КПВ вроде «x < 50 ? 100 − x : 75 − 0.5x» издержки как раз ПАДАЮТ
   (с 1 до 0.5), и подпись прямо противоречила таблице издержек под ней.
   Теперь смотрим на сами издержки: растут — вогнутая, падают — выпуклая,
   держатся — линейная. Числа те же, что в таблице разбора. */
function ppfTypeLabel() {
  const s1 = ppfSlope(CONFIG.Qmax * 0.25), s2 = ppfSlope(CONFIG.Qmax * 0.5), s3 = ppfSlope(CONFIG.Qmax * 0.75);
  if (isNaN(s1) || isNaN(s2) || isNaN(s3)) return 'нелинейная';
  const c1 = Math.abs(s1), c3 = Math.abs(s3);
  const flat = Math.abs(s1 - s2) < 1e-4 && Math.abs(s2 - s3) < 1e-4;
  if (flat) return 'линейная: постоянные альтернативные издержки';
  if (c3 > c1 * (1 + 1e-4)) return 'вогнутая: растущие альтернативные издержки';
  if (c3 < c1 * (1 - 1e-4)) return 'выпуклая: падающие альтернативные издержки';
  return 'нелинейная';
}

// Пересчёт КПВ: компиляция формулы, удержание точки в допустимой зоне.
function recomputePpf() {
  STATE.ppfReady = false;
  STATE.ppfF = null; STATE.ppfF2 = null; STATE.ppfErr = null;
  // Единый ввод (Фаза 11): строка принимает и «y = …», и «x = …», и неявное
  // уравнение. Разбирает parsePpfEquation, движку по-прежнему приходит Y от X.
  const r = parsePpfEquation(STATE.ppfFormula);
  if (r.error) { STATE.ppfCompiled = null; STATE.ppfErr = r.error; return; }
  STATE.ppfF = r.f; STATE.ppfKind = r.kind;
  STATE.ppfCompiled = true;      // прежний флаг «формула принята»
  STATE.ppfReady = true;
  // Вторая кривая для сравнения (Фаза 12) — по тому же стандарту ввода.
  if (STATE.ppfCompare) {
    const r2 = parsePpfEquation(STATE.ppfFormula2);
    if (!r2.error) STATE.ppfF2 = r2.f; else STATE.ppfErr = r2.error;
  }
  // Авто-масштаб под границу: рамка из перехватов по обеим кривым (+10% воздуха).
  const edges = [{ f: evalPpf }];
  if (STATE.ppfF2) edges.push({ f: (x) => evalPpf2(x) });
  let mx = 0, my = 0;
  edges.forEach(e => {
    const a = ppfXmaxOf(e.f); if (a > 0 && isFinite(a)) mx = Math.max(mx, a);
    const b = e.f(0); if (b > 0 && !isNaN(b)) my = Math.max(my, b);
  });
  if (!(mx > 0)) mx = CONFIG.Qmax;
  if (!(my > 0)) my = CONFIG.Pmax;
  applyAutoRanges(padMax(mx), padMax(my));
}

// Вторая КПВ сцены сравнения.
function evalPpf2(x) {
  if (!STATE.ppfF2) return NaN;
  const v = STATE.ppfF2(x);
  return (typeof v === 'number' && isFinite(v)) ? v : NaN;
}

/* Луч потребления в комплектах (Фаза 11.4). Пропорция «столько X на столько Y»
   задаёт луч из начала координат y = (ky/kx)·x; где он пересекает границу, там
   и лежит максимальный набор. Целых комплектов столько, сколько раз пропорция
   укладывается в этот набор. */
function bundleRay(f) {
  const kx = +STATE.bundleX, ky = +STATE.bundleY;
  if (!(kx > 0) || !(ky > 0)) return null;
  const slope = ky / kx;
  const g = (x) => { const y = f(x); return isFinite(y) ? y - slope * x : NaN; };
  const hi = ppfXmaxOf(f);
  if (!(hi > 0)) return null;
  const x = findRootIn(g, 1e-6, hi);
  if (x == null) return null;
  const y = slope * x;
  return { x, y, slope, kx, ky, whole: Math.floor(Math.min(x / kx, y / ky) + 1e-9) };
}

/* Н18, Н19. Поворот луча комплектов в точку (x, y) плоскости.

   Отдельной функцией, а не замыканием внутри обработчика: так поворот можно
   проверить числом, не изображая жест мышью. Правила: в отрицательные значения
   луч не поворачивается (комплекта из минус единиц не бывает); подойдя ближе
   KEY_SNAP_PX к излому КПВ или КТВ, наклон падает ровно в него; единицы X
   остаются как задал человек, меняется только Y, поэтому поле «Единиц X» не
   прыгает под рукой. */
function bundleSlopeAt(x, y) {
  if (!(x > 0)) return null;                    // левее оси Y наклона нет
  let s = Math.max(1e-6, y / x);                // в минус не поворачиваем
  const kinks = STATE._bundleKinks || [];
  const near = kinks.find(k => Math.abs(sy(k * x) - sy(s * x)) <= KEY_SNAP_PX);
  return (near != null) ? near : s;
}
function bundleDragTo(x, y) {
  const s = bundleSlopeAt(x, y);
  if (s == null || !isFinite(s)) return;
  const kx = Math.max(1e-6, +STATE.bundleX || 1);
  STATE.bundleX = kx;
  STATE.bundleY = Math.round(s * kx * 1000) / 1000;
  // Поля единиц идут за лучом во время вращения — во всех трёх моделях блока.
  [['inp-bundle-x', 'inp-bundle-y'], ['inp-bundle-x2', 'inp-bundle-y2'],
   ['inp-bundle-xt', 'inp-bundle-yt']].forEach(([ix, iy]) => {
    const ex = document.getElementById(ix), ey = document.getElementById(iy);
    if (ex && ex.value !== '') ex.value = fmtInput(STATE.bundleX);
    if (ey && ey.value !== '') ey.value = fmtInput(STATE.bundleY);
  });
  redrawAll();
}

/* Н16. Выигрыш от торговли по кривой комплектов: две точки на одном луче.
   Луч задан пропорцией потребления (единиц X к единицам Y), поэтому его наклон
   s = ky / kx. С КПВ он встречается там, где страна потребляет только своё
   (автаркия), с КТВ — там, где она уже обменяла часть выпуска (торговля).
   Возвращает null, если луч не построен: тогда прирост считать нечем. */
function tradeBundleGain(d) {
  if (!d || !d.line || !d.ppfPts || !d.ppfPts.length) return null;
  const kx = +STATE.bundleX, ky = +STATE.bundleY;
  if (!STATE.bundleOn || !(kx > 0) || !(ky > 0)) return null;
  const s = ky / kx;
  // Автаркия: луч встречает саму КПВ (ищем численно, форма любая).
  const aut = bundleRay((x) => interpY(d.ppfPts, x));
  if (!aut) return null;
  /* Торговля: луч встречает прямую КТВ y = intercept − slope·x. Здесь пересечение
     берётся явно: s·x = intercept − slope·x  ⇒  x = intercept / (s + slope). */
  const den = s + d.line.slope;
  if (!(Math.abs(den) > 1e-12)) return null;
  const tx = d.line.intercept / den;
  if (!isFinite(tx) || tx < 0) return null;
  const tr = { x: tx, y: s * tx };
  return { aut: { x: aut.x, y: aut.y }, tr, dx: tr.x - aut.x, dy: tr.y - aut.y };
}

// Кривая КПВ, вторая кривая сравнения, области и луч комплектов.
function drawPpfCurve() {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const mk = (f) => {
    const pts = [];
    for (let i = 0; i <= 400; i++) {
      const x = CONFIG.Qmin + (CONFIG.Qmax - CONFIG.Qmin) * i / 400;
      const y = f(x);
      pts.push((isNaN(y) || y < 0 || x < 0) ? null : [x, y]);
    }
    return pts;
  };
  const area = d3.area().defined(d => d !== null).x(d => sx(d[0])).y0(sy(0)).y1(d => sy(d[1]));
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const c1 = STATE.ppfColor1 || COL.D, c2 = STATE.ppfColor2 || COL.S;
  const pts = mk(evalPpf);

  // Недостижимое — всё, что выше границы: рисуем полосой до верха окна.
  if (STATE.ppfShowOut) {
    const out = d3.area().defined(d => d !== null).x(d => sx(d[0]))
      .y0(d => sy(d[1])).y1(sy(CONFIG.Pmax));
    g.append('path').datum(pts).attr('d', out)
      .attr('fill', STATE.areaColor.ppfOut || COL.DWL).attr('opacity', 0.13)
      .attr('data-legend', 'Недостижимые наборы');
  }
  if (STATE.ppfShowIn) {
    g.append('path').datum(pts).attr('d', area)
      .attr('fill', STATE.areaColor.ppfIn || c1).attr('opacity', 0.1)
      .attr('data-legend', 'Достижимые наборы');
  }
  g.append('path').datum(pts).attr('fill', 'none').attr('stroke', c1).attr('stroke-width', 2.5).attr('d', line);
  labelCurve(g, evalPpf, STATE.ppfName1 || 'КПВ', c1, {});

  if (STATE.ppfF2) {
    const p2 = mk(evalPpf2);
    g.append('path').datum(p2).attr('fill', 'none').attr('stroke', c2).attr('stroke-width', 2.5).attr('d', line);
    labelCurve(g, evalPpf2, STATE.ppfName2 || 'КПВ 2', c2, { below: true });
  }

  // Подпись «достижимо» привязана к самой области, а не к доле окна: при
  // сильном отдалении она уезжала в пустоту далеко от кривой (Фаза 12.4).
  if (STATE.ppfShowIn) {
    const xm = ppfXmaxOf(evalPpf), ym = evalPpf(0);
    if (xm > 0 && ym > 0) {
      const lx = xm * 0.28, ly = evalPpf(lx) * 0.4;
      if (isFinite(ly) && ly > 0) {
        g.append('text').attr('x', sx(lx)).attr('y', sy(ly))
          .attr('font-size', FS.base).attr('fill', c1).attr('opacity', 0.75).text('Достижимо');
      }
    }
  }
  if (STATE.bundleOn) drawBundleRay(g, evalPpf, c1);
}

/* Кривая комплектов (П4).
   Это луч из начала координат с наклоном Y/X по введённым единицам, и он идёт
   ДО КРАЯ ПЛОСКОСТИ, а не до КПВ: раньше он обрывался на границе, и было
   непонятно, что это прямая, а не отрезок. Точка, где он упирается в границу,
   по-прежнему отмечена и подписана. Если в сцене есть и КПВ, и КТВ, луч
   обязан пересечь обе, и обе точки показываются (второй аргумент curves —
   список пар «функция, имя»). */
function drawBundleRay(g, f, color, curves) {
  const b = bundleRay(f);
  const slope = (+STATE.bundleY > 0 && +STATE.bundleX > 0) ? (+STATE.bundleY / +STATE.bundleX) : null;
  if (slope == null) return;
  const col = COL.MR;

  // Луч до края видимой плоскости: упираемся либо в правый край, либо в верхний.
  const [, xHi] = sx.domain(), [, yHi] = sy.domain();
  const xEnd = Math.min(xHi, (slope > 0) ? yHi / slope : xHi);
  g.append('line').attr('x1', sx(0)).attr('y1', sy(0))
    .attr('x2', sx(xEnd)).attr('y2', sy(slope * xEnd))
    .attr('stroke', col).attr('stroke-width', 1.8).attr('stroke-dasharray', '6 4');
  labelCurve(g, (x) => slope * x, 'Комплекты', col, { key: 'bundle', from: 0.8, to: 0.2 });

  /* Н18, Н19. Луч крутится мышью вокруг начала координат. Тянуть тонкую
     пунктирную линию неудобно, поэтому поверх неё лежит широкая прозрачная
     «дорожка» — она и ловит захват (в выгрузку не идёт, помечена data-skip-export).
     В отрицательные значения луч не поворачивается: комплект из отрицательного
     числа единиц не бывает. Подойдя близко к излому КПВ или КТВ, наклон падает
     ровно в него — тот же магнит, что у ключевых точек. */
  /* Изломы ищем своим частым сканом, а не общим kinksOf: тот настроен на окно
     «Математики» и на широком диапазоне КПВ (здесь 0…60) стык при X = 20
     проскакивал между узлами. Здесь нужен только наклон луча через излом, и
     достаточно сравнить наклон слева и справа от узла. */
  const kinkSlopes = [];
  (curves && curves.length ? curves : [{ f, name: 'КПВ' }]).forEach(c => {
    if (typeof c.f !== 'function') return;
    const hi = ppfXmaxOf(c.f);
    if (!(hi > 0)) return;
    const N = 600, h = hi / N;
    let prev = null;
    for (let i = 1; i < N; i++) {
      const x = h * i;
      const a = c.f(x - h), b = c.f(x), d = c.f(x + h);
      if (!isFinite(a) || !isFinite(b) || !isFinite(d)) { prev = null; continue; }
      const left = (b - a) / h, right = (d - b) / h;
      if (prev !== null && Math.abs(right - left) > 0.15 * (1 + Math.abs(left)) && b > 0) {
        kinkSlopes.push(b / x);
        i += 3;                                  // один стык — одна запись
      }
      prev = left;
    }
  });
  STATE._bundleKinks = kinkSlopes;      // наклоны изломов для магнита (и для проверки)
  g.append('line').attr('class', 'bundle-grab').attr('data-skip-export', '1')
    .attr('x1', sx(0)).attr('y1', sy(0))
    .attr('x2', sx(xEnd)).attr('y2', sy(slope * xEnd))
    .attr('stroke', 'transparent').attr('stroke-width', 14)
    .style('cursor', 'grab').style('pointer-events', 'stroke')
    .call(d3.drag().container(() => svg.node())
      .on('drag', (ev) => bundleDragTo(sx.invert(ev.x), sy.invert(ev.y))));

  // Пересечения со всеми заданными кривыми — как ключевые точки, с координатами.
  const list = (curves && curves.length) ? curves : [{ f, name: 'КПВ' }];
  list.forEach(c => {
    if (typeof c.f !== 'function') return;
    const hi = ppfXmaxOf(c.f) || xHi;
    const x = findRootIn((t) => { const y = c.f(t); return isFinite(y) ? y - slope * t : NaN; }, 1e-6, hi);
    if (x == null) return;
    const y = slope * x;
    g.append('circle').attr('cx', sx(x)).attr('cy', sy(y)).attr('r', 5)
      .attr('fill', COL.halo).attr('stroke', col).attr('stroke-width', 2.4);
    haloText(g, sx(x) + 9, sy(y) - 9,
             (c.name ? c.name + ' ' : '') + '(' + fmt(x) + '; ' + fmt(y) + ')', 'start', 'auto');
  });
  void b; void color;
}

// Табло КПВ: тип, перехваты Макс X / Макс Y, альтернативные издержки X.
// Форму границы задают ползунки пульта «Макс X / Макс Y» (точку производства убрали).
/* Альтернативные издержки в точке — численно, через наклон касательной.
   Раньше брался наклон в середине окна и выдавался за «издержки X» на всей
   кривой: для нелинейной КПВ это просто неверно, и издержки Y не считались
   вовсе. Теперь обе величины и в трёх точках (Фаза 12.5).
     издержки X = |dY/dX|   (сколько Y теряется за единицу X)
     издержки Y = |dX/dY| = 1 / |dY/dX|   (обратная величина) */
function ppfOppAt(f, x) {
  const k = Math.abs(ppfSlopeOf(f, x));
  if (!isFinite(k) || k <= 0) return null;
  return { x, y: f(x), oppX: k, oppY: 1 / k };
}

function updatePpfPanel() {
  const box = document.getElementById('info-ppf');
  if (!box) return;
  if (!STATE.ppfReady) {
    box.innerHTML = '<div class="warn">' + (STATE.ppfErr || 'Не понял уравнение КПВ.') + '</div>';
    return;
  }
  const f = evalPpf;
  const maxY = f(0), maxX = ppfXmaxOf(f);
  const type = ppfTypeLabel();
  const at = [0.2, 0.5, 0.8].map(k => ppfOppAt(f, maxX * k)).filter(Boolean);
  const linear = /линей/i.test(type);

  let html = `<div class="stat"><span>Тип КПВ</span><b>${type}</b></div>`;
  html += `<div class="stat"><span>$X_{max}$ (весь ресурс на X)</span><b>${fmt(maxX)}</b></div>`;
  html += `<div class="stat"><span>$Y_{max}$ (весь ресурс на Y)</span><b>${fmt(maxY)}</b></div>`;
  if (at.length) {
    const mid = at[Math.floor(at.length / 2)];
    html += `<div class="stat"><span>Альт. издержки X в середине</span><b>${fmt(mid.oppX)} Y за ед. X</b></div>`;
    html += `<div class="stat"><span>Альт. издержки Y в середине</span><b>${fmt(mid.oppY)} X за ед. Y</b></div>`;
  }
  if (STATE.ppfF2) {
    const m2x = ppfXmaxOf(evalPpf2), m2y = evalPpf2(0);
    html += `<div class="stat"><span>${STATE.ppfName2 || 'КПВ 2'}: $X_{max}$ / $Y_{max}$</span>`
          + `<b>${fmt(m2x)} / ${fmt(m2y)}</b></div>`;
    const k2 = Math.abs(ppfSlopeOf(evalPpf2, m2x * 0.5));
    html += `<div class="stat"><span>${STATE.ppfName2 || 'КПВ 2'}: альтернативные издержки X</span><b>${fmt(k2)} Y за ед. X</b></div>`;
  }
  if (STATE.bundleOn) {
    const b = bundleRay(f);
    if (b) {
      html += `<div class="stat"><span>Комплект ${fmt(b.kx)} X на ${fmt(b.ky)} Y</span>`
            + `<b>${fmt(b.x)}; ${fmt(b.y)}</b></div>`;
      html += `<div class="stat"><span>Целых комплектов</span><b>${b.whole}</b></div>`;
    }
  }

  // Разбор: откуда взялись эти числа.
  html += '<div class="sb-note"><b>Как это получилось</b>';
  html += '<p><b>Где кончается кривая?</b> Граница возможностей это все наборы, при которых ресурс израсходован '
        + 'полностью. Концы кривой и есть крайние случаи: весь ресурс на один товар. '
        + `Здесь это $X_{max} = ${fmt(maxX)}$ и $Y_{max} = ${fmt(maxY)}$; они найдены численно, `
        + 'как точки пересечения кривой с осями.</p>';
  html += '<p><b>Откуда берутся альтернативные издержки?</b> Это наклон касательной в точке. Берём две близкие '
        + 'точки слева и справа и делим прирост Y на прирост X, поэтому счёт одинаково '
        + 'работает и для прямой, и для дуги, и для неявного уравнения. '
        + 'Издержки Y это та же величина наоборот: $|dX/dY| = 1 / |dY/dX|$.</p>';
  if (linear) {
    html += '<p><b>Меняются ли издержки вдоль кривой?</b> Нет: кривая прямая, наклон один и тот же везде. За каждую единицу X '
          + `теряется ${fmt(at.length ? at[0].oppX : NaN)} единиц Y, сколько бы X уже ни выпускали. `
          + 'Ресурсы взаимозаменяемы, и специализация ничего не удорожает.</p>';
  } else if (at.length >= 2) {
    const grow = at[at.length - 1].oppX > at[0].oppX;
    html += '<p><b>Меняются ли издержки вдоль кривой?</b> Да: наклон меняется, а вместе с ним и издержки:</p>';
    html += '<div class="tbl">' + at.map(p =>
      `<div><span>при X = ${fmt(p.x)}</span><b>${fmt(p.oppX)} Y за ед. X</b></div>`).join('') + '</div>';
    html += grow
      ? '<p>Издержки растут: чем больше X уже выпускают, тем дороже обходится следующая '
        + 'единица. Так бывает, когда ресурсы не одинаково пригодны для обоих товаров, и в ход '
        + 'идут всё менее подходящие. Кривая выпуклая к началу координат.</p>'
      : '<p>Издержки убывают: следующая единица X обходится дешевле предыдущей. Это редкий '
        + 'случай, он означает отдачу от масштаба в производстве X.</p>';
  }
  if (STATE.bundleOn) {
    const b = bundleRay(f);
    if (b) {
      html += `<p>Комплект это фиксированная пропорция ${fmt(b.kx)} X на ${fmt(b.ky)} Y. Все такие наборы `
            + `лежат на луче $y = ${fmt(b.slope)}x$ из начала координат. Луч упирается в границу в точке `
            + `(${fmt(b.x)}; ${fmt(b.y)}) это и есть самый большой доступный набор нужной пропорции.</p>`;
      html += `<p>Если блага делимы, комплектов получается ${fmt(Math.min(b.x / b.kx, b.y / b.ky))}. `
            + `Если брать только целые, то ${b.whole}: остаток ресурса на полный комплект уже не хватает.</p>`;
    }
  }
  html += '<p><b>Что означают точки ВНУТРИ кривой и снаружи?</b> Точка внутри достижима, но там '
        + 'ресурс использован не полностью: можно выпустить больше хотя бы одного товара, ничего '
        + 'не теряя. Точка снаружи при нынешних ресурсах и технологии недостижима вовсе. Сама '
        + 'граница это наборы, где выигрыш в одном товаре обязательно оплачен потерей в другом.</p>';
  html += '<p><b>Что двигает саму кривую?</b> Рост количества ресурсов или улучшение технологии. '
        + 'Если улучшение касается только одного товара, кривая уезжает наружу не целиком, а лишь '
        + 'по своей оси, и наклон меняется. Именно поэтому в задачах спрашивают не «выросла ли '
        + 'экономика», а «по какому товару выросла»: от ответа зависит, изменились ли '
        + 'альтернативные издержки.</p>';
  html += '<p><b>Вывод.</b> Кривая отвечает сразу на три вопроса: что достижимо, чем приходится '
        + 'платить за каждую единицу и что считать полным использованием ресурса. Форма кривой это '
        + 'это ответ на второй вопрос, и в задачах спрашивают почти всегда именно его.</p>';
  html += '</div>';
  box.innerHTML = html;
}

// Полная перерисовка режима КПВ (свои подписи осей X/Y).
function redrawPpf() {
  if (STATE.ppfSub === 'sum')   { redrawPpfSum();   return; }   // Задача 1: сумма двух КПВ
  if (STATE.ppfSub === 'trade') { redrawPpfTrade(); return; }   // Задача 2: КТВ
  recomputePpf();
  makeScales();   // recomputePpf мог изменить масштаб (авто-рамка) — пересчитать шкалы
  svg.selectAll('*').remove();
  addDefs();
  drawGrid();
  drawAxes('X', 'Y');
  // Точку производства убрали: форму КПВ задают ползунки «Макс X / Макс Y» в пульте.
  if (STATE.ppfReady) drawPpfCurve();
  updatePpfPanel();
}

/* ---------------------------------------------------------------------
   БЛОК 12б. СУММА ДВУХ КПВ (Задача 1) и КТВ — торговые возможности (Задача 2).
   Оба под-режима режима «КПВ»: оси «товар X / товар Y», координаты и
   рисование осей — общие (drawAxes('X','Y')). Класс функций ограничен набором:
   линейная (a-b*x), вогнутая-эллипс sqrt(a-b*x^2), вогнутая-парабола (a-b*x^2),
   выпуклая (a-b*sqrt(x)) — все убывающие, в первой четверти.
   --------------------------------------------------------------------- */

/* Значение скомпилированной КПВ Y=f(X) (переменные X и x — синонимы).
   П21: значения ползунков подмешиваем обязательно, иначе расчёт падает на
   букве и молча отдаёт NaN, ppfXmaxOf получает null, и сцена показывает
   «Не удалось определить границы КПВ» на пустом холсте. Через эту функцию
   идут одиночная КПВ, сумма КПВ и обе сцены торговли — чинится всё разом.

   ⚠️ ЗДЕСЬ СТОЯЛО, ЧТО «РАЗБОР ФОРМУЛЫ 100 − a*X ПРОХОДИЛ». Это перестало
   быть правдой и сбило с пути целую сессию: compilePpf звал math.parse БЕЗ
   общей подготовки, поэтому падал как раз разбор — «100-ax» отвечало
   «Undefined symbol ax», хотя буква «a» ползунок исправно заводила. Замер
   22.08 и правка — в разделе CLAUDE.md за 22.08. Комментарий не доказывает,
   что код делает написанное: сверяться надо с прогоном, а не с текстом. */
/* ⚠️ БУКВА БЕЗ ПОЛЗУНКА СЧИТАЕТСЯ ЕДИНИЦЕЙ, А НЕ ОБРУШИВАЕТ РАСЧЁТ.

   Здесь стоял голый paramScope, и это был ТРЕТИЙ, отдельный отказ — не тот же
   самый, что мёртвый разбор. Проверка владельца 22.08 показала его в чистом
   виде: `parsePpfEquation('y=100-a*x')` отдаёт `kind: explicit`, то есть
   формула РАЗОБРАЛАСЬ, а `f(5)` возвращает NaN (в JSON — `null`).

   Асимметрия была ровно между двумя соседними строками: пробный расчёт при
   разборе идёт через `scopeFor`, который подставляет единицу букве без
   ползунка, а сам расчёт шёл через `paramScope`, который знает только
   заведённые ползунки. Разбор проходил, счёт падал.

   Окно, в котором это видно, не выдуманное: ползунок заводится ПОСЛЕ того, как
   формула принята (об этом прямо сказано в комментарии к `scopeFor`), и между
   двумя этими моментами кривая считалась в NaN, `ppfXmaxOf` получал null, и
   сцена показывала «Не удалось определить границы КПВ» на пустом холсте.

   Тот же приём, что у `evalWithParams` и `compileTwoVar`: исходный текст
   формулы носит сам скомпилированный узел. */
function ppfEvalWith(compiled, x) {
  try {
    const ctx = (compiled && compiled._src)
      ? scopeFor(compiled._src, { x: x, X: x })
      : paramScope({ x: x, X: x });
    const v = compiled.evaluate(ctx);
    return (typeof v === 'number' && isFinite(v)) ? v : NaN;
  } catch (e) { return NaN; }
}

/* Наклон произвольной функции f в точке x — центральная разность, а на краю
   домена односторонняя. Угловое решение КТВ (cornerByValue) стоит РОВНО на
   границе — xp = 0 или xp = Xmax, — и раньше здесь всегда была NaN: f
   работает через interpY по точкам [0, Xmax], а та честно не экстраполирует
   за массив (см. её же комментарий), и f(Xmax + h) уходила в NaN. Центральной
   разности с одной стороны буквально не из чего считать, но с ДРУГОЙ сторона
   есть — и наклон там определён не хуже, чем в любой другой точке того же
   отрезка (это не излом, это край графика). Настоящая неопределённость
   остаётся только там, где недоступна и точка x, и обе соседние — это и
   означает «здесь функция не задана», а не пограничный артефакт. */
function ppfSlopeOf(f, x) {
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const a = f(x + h), b = f(x - h);
  if (!isNaN(a) && !isNaN(b)) return (a - b) / (2 * h);
  const c = f(x);
  if (isNaN(c)) return NaN;
  if (!isNaN(a)) return (a - c) / h;   // правая сторона доступна — вперёд
  if (!isNaN(b)) return (c - b) / h;   // левая сторона доступна — назад
  return NaN;
}

// Точка пересечения убывающей КПВ с осью X (где Y=0). NaN-зона трактуется как «ниже нуля».
// Возвращает Xmax > 0 или null. Расширяем верхнюю границу, затем уточняем бисекцией.
function ppfXmaxOf(f) {
  const fpos = (x) => { const v = f(x); return isNaN(v) ? -1 : v; };
  if (!(fpos(0) > 0)) return null;                 // f(0) должно быть положительным (Ymax)
  let hi = 1;
  for (let k = 0; k < 40 && fpos(hi) > 0; k++) hi *= 2;   // расширяем до ~1e12
  if (fpos(hi) > 0) return null;                   // граница не найдена (не убывает к нулю)
  let r = bisect(fpos, 0, hi);                     // fpos(0)>0, fpos(hi)≤0 → корень = Xmax
  // Бисекция может остановиться на эпсилон ЗА границей домена (для sqrt там уже NaN).
  // Сдвигаем чуть внутрь, чтобы f(Xmax) была определена (кривая доходит ровно до оси).
  for (let k = 0; k < 60 && (isNaN(f(r)) || f(r) < 0); k++) r -= Math.max(1e-12, Math.abs(r) * 1e-9);
  return r;
}

// Метод наименьших квадратов: прямая ys ≈ slope*xs + intercept + коэффициент r².
function fitLinear(xs, ys) {
  const n = xs.length; let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; sxx += xs[i] * xs[i]; sxy += xs[i] * ys[i]; }
  const den = n * sxx - sx * sx; if (Math.abs(den) < 1e-12) return null;
  const slope = (n * sxy - sx * sy) / den, intercept = (sy - slope * sx) / n;
  const meanY = sy / n; let ssTot = 0, ssRes = 0;
  for (let i = 0; i < n; i++) { const pred = slope * xs[i] + intercept; ssRes += (ys[i] - pred) ** 2; ssTot += (ys[i] - meanY) ** 2; }
  const r2 = ssTot < 1e-12 ? 1 : 1 - ssRes / ssTot;
  return { slope, intercept, r2 };
}

// Распознать тип КПВ из набора по пробным точкам внутри домена.
// Возвращает { type, a, b, Xmax, Ymax }: linear (a-b·x), ellipse (sqrt(a-b·x²)),
// parabola (a-b·x²), convex (a-b·√x) или { type:'unknown' }.
function classifyPpf(f) {
  const Xmax = ppfXmaxOf(f);
  if (Xmax == null || !(Xmax > 0)) return { type: 'unknown', Xmax: null };
  const Ymax = f(0);
  const xs = [0.2, 0.4, 0.6, 0.8].map(t => Xmax * t);
  const ys = xs.map(f);
  if (ys.some(isNaN)) return { type: 'unknown', Xmax, Ymax };
  const TOL = 1e-6;
  const lin = fitLinear(xs, ys);                                   // y vs x
  if (lin && lin.r2 > 1 - TOL) return { type: 'linear', a: Ymax, b: -lin.slope, Xmax, Ymax };
  const ell = fitLinear(xs.map(x => x * x), ys.map(y => y * y));   // y² vs x²  →  эллипс/дуга
  if (ell && ell.r2 > 1 - TOL && ell.slope < 0) return { type: 'ellipse', a: ell.intercept, b: -ell.slope, Xmax, Ymax };
  const par = fitLinear(xs.map(x => x * x), ys);                   // y vs x²   →  парабола
  if (par && par.r2 > 1 - TOL) return { type: 'parabola', a: Ymax, b: -par.slope, Xmax, Ymax };
  const cvx = fitLinear(xs.map(x => Math.sqrt(x)), ys);            // y vs √x   →  выпуклая
  if (cvx && cvx.r2 > 1 - TOL) return { type: 'convex', a: Ymax, b: -cvx.slope, Xmax, Ymax };
  return { type: 'unknown', Xmax, Ymax };
}

// Ближайшее «красивое» число ≥ v (для подгонки масштаба осей).
/* Ближайшее «круглое» число сверху. Ступени ладдера подобраны так, чтобы
   округление вверх не съедало картинку (Б10): между 3 и 4 разрыв в треть, и
   данные до 30 000 давали ось до 40 000 — верхняя четверть графика пустая, и
   на экране, и на бумаге. Добавленные ступени 1,2 · 1,8 · 3,5 · 7 держат
   перебор в пределах примерно десятой доли и остаются числами, по которым
   удобно расставлять деления. */
function niceMax(v) {
  if (!(v > 0)) return 10;
  const k = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 1.8, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 10]) if (m * k >= v - 1e-9) return m * k;
  return 10 * k;
}

// Точки одной КПВ от 0 до Xmax (для бледной отрисовки исходных кривых).
function singlePpfPoints(f, xmax) {
  const N = 200, out = [];
  for (let i = 0; i <= N; i++) { const x = xmax * i / N; const y = f(x); out.push((isNaN(y) || y < 0) ? null : [x, y]); }
  return out;
}

// Универсальный поиск корня g(x)=0 на отрезке [lo, hi] (скан + бисекция). null — нет.
function findRootIn(g, lo, hi) {
  const N = 1000; let prevX = lo, prevG = g(lo);
  for (let i = 1; i <= N; i++) {
    const x = lo + (hi - lo) * i / N, cur = g(x);
    if (!isNaN(prevG) && !isNaN(cur) && prevG * cur <= 0 && prevG !== cur)
      return (prevG === 0) ? prevX : (cur === 0 ? x : bisect(g, prevX, x));
    prevX = x; prevG = cur;
  }
  return null;
}

// Линейная интерполяция Y по X в массиве отсортированных точек.
function interpY(points, X) {
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    if (!a || !b) continue;
    if (X >= a[0] && X <= b[0] && b[0] > a[0]) { const t = (X - a[0]) / (b[0] - a[0]); return a[1] + t * (b[1] - a[1]); }
  }
  return NaN;
}

/* --- Задача 1: суммарная КПВ двух стран ----------------------------- */

// Максимальный суммарный Y при заданном суммарном выпуске X: делим X = x1 + x2
// между странами так, чтобы f1(x1)+f2(x2) был максимален. Двухуровневая сетка —
// надёжно для ЛЮБОЙ пары (вогнутые → оптимум внутри, выпуклые → на краю).
function maxAllocY(f1, f2, X, x1max, x2max) {
  const lo = Math.max(0, X - x2max), hi = Math.min(x1max, X);
  if (hi < lo - 1e-9) return NaN;
  // Аргументы зажимаем в домены стран — страхует от float-эпсилона у самого края (X≈Xmax),
  // где иначе sqrt(отрицательного) даёт NaN и кривая не доходит до оси.
  const obj = (x1) => {
    const a = Math.min(Math.max(x1, 0), x1max), b = Math.min(Math.max(X - x1, 0), x2max);
    const y1 = f1(a), y2 = f2(b);
    return (isNaN(y1) || isNaN(y2)) ? -Infinity : y1 + y2;
  };
  if (hi <= lo + 1e-9) { const v = obj(lo); return v === -Infinity ? NaN : v; }
  let best = -Infinity, bx = lo;
  const M = 200;
  for (let j = 0; j <= M; j++) { const x1 = lo + (hi - lo) * j / M; const v = obj(x1); if (v > best) { best = v; bx = x1; } }
  /* Уточнение вокруг лучшего узла. Сорока точек здесь достаточно: отрезок уже
     сузился в сто раз, и сороковая доля от него это одна четырёхтысячная
     исходного диапазона — на экране такой разницы нет. Было двести, то есть
     ровно та же сетка, что и на грубом проходе, и это удваивало счёт (А2). */
  const step = (hi - lo) / M;
  const lo2 = Math.max(lo, bx - step), hi2 = Math.min(hi, bx + step), M2 = 40;
  for (let j = 0; j <= M2; j++) { const x1 = lo2 + (hi2 - lo2) * j / M2; const v = obj(x1); if (v > best) best = v; }
  return best === -Infinity ? NaN : best;
}

// Численная суммарная (совместная) КПВ: для каждого суммарного X — оптимальное деление.
function combinedPpfPoints(f1, f2, x1max, x2max, N) {
  N = N || 240;
  const Xtot = x1max + x2max, pts = [];
  for (let i = 0; i <= N; i++) { const X = Xtot * i / N; pts.push([X, maxAllocY(f1, f2, X, x1max, x2max)]); }
  return pts;
}

// Точное оптимальное распределение выпуска X между странами (Задача 1: поиск изломов).
// Возвращает { x1, x2, y } — сколько X производит каждая страна и суммарный Y.
// Отдельная, более точная функция (грубый скан + золотое сечение); НЕ трогает maxAllocY.
function allocAt(f1, f2, X, xmax1, xmax2) {
  const lo = Math.max(0, X - xmax2), hi = Math.min(xmax1, X);
  const obj = (x1) => {
    const a = Math.min(Math.max(x1, 0), xmax1), b = Math.min(Math.max(X - x1, 0), xmax2);
    const y1 = f1(a), y2 = f2(b);
    return (isNaN(y1) || isNaN(y2)) ? -Infinity : y1 + y2;
  };
  if (hi <= lo + 1e-12) {                         // единственная допустимая точка
    const x1 = Math.min(Math.max(lo, 0), xmax1), v = obj(x1);
    return { x1, x2: X - x1, y: v === -Infinity ? NaN : v };
  }
  // Грубый скан (на случай невыпуклой КПВ) — находим окрестность максимума.
  const M = 200; let best = -Infinity, bx = lo;
  for (let j = 0; j <= M; j++) { const x1 = lo + (hi - lo) * j / M; const v = obj(x1); if (v > best) { best = v; bx = x1; } }
  // Уточнение золотым сечением вокруг лучшего узла (локально унимодально).
  const step = (hi - lo) / M;
  let a = Math.max(lo, bx - step), b = Math.min(hi, bx + step);
  const gr = (Math.sqrt(5) - 1) / 2;
  let c = b - gr * (b - a), d = a + gr * (b - a), fc = obj(c), fd = obj(d);
  for (let k = 0; k < 60; k++) {
    if (fc > fd) { b = d; d = c; fd = fc; c = b - gr * (b - a); fc = obj(c); }
    else { a = c; c = d; fc = fd; d = a + gr * (b - a); fd = obj(d); }
  }
  const x1 = Math.min(Math.max((a + b) / 2, 0), xmax1), v = obj(x1);
  return { x1, x2: X - x1, y: v === -Infinity ? NaN : v };
}

// Надёжный поиск изломов суммарной КПВ (Задача 1). Излом — точка, где меняется
// ОПТИМАЛЬНЫЙ режим распределения (страна «вступает» в производство X или
// «исчерпывает» свой запас X). Даёт ровно нужное число изломов независимо от формы.
// Возвращает [{ x, y }, …] (внутренние изломы по возрастанию x).
function detectCombinedKinks(f1, f2, xmax1, xmax2) {
  const Xmax = xmax1 + xmax2;
  const N = 600;
  const e1p = 1e-6 * xmax1, e1e = 1e-5 * xmax1, e2p = 1e-6 * xmax2, e2e = 1e-5 * xmax2;
  // «Режим» в точке X — четыре булевых флага по оптимальному распределению.
  const regimeAt = (X) => {
    const al = allocAt(f1, f2, X, xmax1, xmax2);
    return { p1: al.x1 > e1p, e1: al.x1 > xmax1 - e1e, p2: al.x2 > e2p, e2: al.x2 > xmax2 - e2e };
  };
  const flag = { p1: (al) => al.x1 > e1p, e1: (al) => al.x1 > xmax1 - e1e, p2: (al) => al.x2 > e2p, e2: (al) => al.x2 > xmax2 - e2e };
  // Пробы (концы не трогаем).
  const probes = [];
  for (let i = 0; i < N; i++) { const X = Xmax * (i + 0.5) / N; probes.push({ X, r: regimeAt(X) }); }
  const same = (r, s) => r.p1 === s.p1 && r.e1 === s.e1 && r.p2 === s.p2 && r.e2 === s.e2;
  // Кандидаты-«скобки» там, где режим сменился.
  const cands = [];
  for (let i = 1; i < N; i++) if (!same(probes[i - 1].r, probes[i].r)) cands.push({ lo: probes[i - 1].X, hi: probes[i].X, prev: probes[i - 1].r, cur: probes[i].r });
  // Слияние близких кандидатов (ближе 3·Xmax/N).
  const minGap = 3 * Xmax / N, merged = [];
  for (const c of cands) {
    const last = merged[merged.length - 1];
    if (last && c.lo - last.hi < minGap) { last.hi = c.hi; last.cur = c.cur; }
    else merged.push({ lo: c.lo, hi: c.hi, prev: c.prev, cur: c.cur });
  }
  // Уточнение бисекцией по сменившемуся флагу (предикат монотонен по X).
  const xs = [];
  for (const c of merged) {
    let fl = null;
    for (const name of ['p1', 'e1', 'p2', 'e2']) if (c.prev[name] !== c.cur[name]) { fl = name; break; }
    if (!fl) { xs.push((c.lo + c.hi) / 2); continue; }
    const pred = (X) => flag[fl](allocAt(f1, f2, X, xmax1, xmax2));
    let lo = Math.max(0, c.lo - Xmax / N), hi = Math.min(Xmax, c.hi + Xmax / N);
    const base = pred(lo);
    if (base === pred(hi)) { xs.push((c.lo + c.hi) / 2); continue; }   // флаг не флипнулся в скобке
    for (let k = 0; k < 50; k++) { const mid = (lo + hi) / 2; if (pred(mid) === base) lo = mid; else hi = mid; }
    xs.push((lo + hi) / 2);
  }
  // Только внутренние, без дублей, по возрастанию.
  xs.sort((a, b) => a - b);
  const out = [];
  for (const Xk of xs) {
    if (Xk <= Xmax * 1e-3 || Xk >= Xmax * (1 - 1e-3)) continue;
    if (out.length && Math.abs(Xk - out[out.length - 1]) <= Xmax * 1e-3) continue;
    out.push(Xk);
  }
  const result = out.map(Xk => ({ x: Xk, y: allocAt(f1, f2, Xk, xmax1, xmax2).y }));
  if (result.length > 4) console.warn('detectCombinedKinks: аномально много изломов (' + result.length + '). Проверьте входные КПВ');
  return result;
}

/* ── ЗАКРЫТАЯ ФОРМА СУММАРНОЙ КПВ ДЛЯ ЛЮБОГО ЧИСЛА ЛИНЕЙНЫХ КРИВЫХ ────
   Было: закрытая форма выводилась только для ДВУХ кривых, и то обычным
   текстом; для трёх и больше панель писала «построена численно», хотя ничего
   численного в сложении прямых нет.

   Задача та же, что у суммарного спроса в сцене сложения, и решается так же:
   отсортировать по альтернативным издержкам и склеить участки.

     • Кто дешевле производит X, тот наращивает его первым — значит участки
       идут по возрастанию наклона b.
     • На k-м участке производит k-й по дешевизне, поэтому наклон там ровно
       его: Y = c − b_k·X, а постоянная c берётся из непрерывности в начале
       участка. Никакого перебора и никакой сетки.
     • Границы участков — накопленные X_max: первый кончается там, где первый
       участник отдал под X весь свой ресурс.
     • Равные альтернативные издержки склеиваются в один кусок: излома между
       ними нет, и рисовать его было бы враньём.

   Числа проверены на образце владельца. Две КПВ y = 100 − x и y = 60 − 2x:
   Y = 160 − X при 0 ≤ X ≤ 100, затем Y = 260 − 2X при 100 < X ≤ 130.
   Три (плюс y = 40 − 4x): 200 − X, затем 300 − 2X, затем 560 − 4X до X = 140.

   ⚠️ ХОТЬ ОДНА КРИВАЯ НЕЛИНЕЙНА — ВОЗВРАЩАЕМ null, и панель честно пишет
   «построена численно». Дуга и парабола складываются не так, и подсунуть им
   ломаную значило бы нарисовать не ту кривую. */
function ppfCoefTex(b) {
  if (Math.abs(b - 1) < 1e-12) return 'X';
  return fmt(b) + 'X';
}
function combinedPpfLinearRecord(cs) {
  if (!cs || cs.length < 2) return null;
  for (const c of cs) {
    if (!c || c.type !== 'linear' || !(c.Xmax > 0) || !isFinite(c.b) || !isFinite(c.a)) return null;
  }
  const ord = cs.map(c => ({ b: c.b, Xmax: c.Xmax })).sort((x, y) => x.b - y.b);
  const Ytot = cs.reduce((s, c) => s + c.a, 0);
  const segs = [];
  let x0 = 0, y0 = Ytot;
  ord.forEach(o => {
    const x1 = x0 + o.Xmax, y1 = y0 - o.b * o.Xmax;
    const last = segs.length ? segs[segs.length - 1] : null;
    if (last && Math.abs(last.b - o.b) < 1e-9) { last.x1 = x1; last.y1 = y1; }
    else segs.push({ x0, x1, y0, y1, b: o.b, c: y0 + o.b * x0 });
    x0 = x1; y0 = y1;
  });
  if (!segs.length) return null;
  const Xtot = segs[segs.length - 1].x1;
  // Набор математикой: тот же \begin{cases}, что у кусочной записи спроса.
  const rows = segs.map((s, i) => {
    const cond = (i === 0)
      ? ('0 \\le X \\le ' + fmt(s.x1))
      : (fmt(s.x0) + ' < X \\le ' + fmt(s.x1));
    return fmt(s.c) + ' - ' + ppfCoefTex(s.b) + ', & ' + cond;
  });
  const latex = (segs.length === 1)
    ? ('Y = ' + fmt(segs[0].c) + ' - ' + ppfCoefTex(segs[0].b) + ',\\ 0 \\le X \\le ' + fmt(Xtot))
    : ('Y = \\begin{cases} ' + rows.join(' \\\\ ') + ' \\end{cases}');
  const evalY = (x) => {
    if (x < -1e-9 || x > Xtot + 1e-9) return NaN;
    for (const s of segs) if (x <= s.x1 + 1e-9) return s.c - s.b * x;
    return NaN;
  };
  /* ⚠️ ГРАНИЦЫ УЧАСТКОВ И ИЗЛОМЫ — НЕ ОДНО И ТО ЖЕ, И ПУТАТЬ ИХ НЕЛЬЗЯ.
     Границ у записи столько же, сколько участков: у двух КПВ это 100 и 130.
     А ИЗЛОМОВ на один меньше: последняя граница — это выход кривой на ось X,
     там кривая кончается, а не ломается.

     Разница не косметическая. `kinks` идёт в отрисовку (от каждого излома
     пунктир к обеим осям и кружок) и в «Схему», которая рисуется только до
     трёх участков. Считать конец кривой изломом значило бы дважды нарисовать
     метку в одной точке — концы табло и так называет отдельно — и отобрать
     схему у сложения трёх кривых.
     Обе границы человек видит: они стоят в самой записи, участками. */
  const bounds = segs.map(s => ({ x: s.x1, y: s.y1 }));
  const kinks = bounds.slice(0, -1);
  return { segs, latex, evalY, kinks, bounds, Xtot, Ytot,
           type: 'линейная (' + segs.length + (segs.length === 1 ? ' кусок)' : (segs.length < 5 ? ' куска)' : ' кусков)')) };
}

// Распознавание аналитической формулы суммарной КПВ (best-effort).
// Возвращает { type, text, evalY|null, kinks }. evalY(x) — аналитическое значение
// (NaN вне распознанной области); проверяется численно перед показом.
function combinedPpfFormula(c1, c2) {
  // Обе линейные → классический «изломанный» вид (1–2 куска).
  if (c1.type === 'linear' && c2.type === 'linear') {
    const lo = (c1.b <= c2.b) ? c1 : c2, hi = (c1.b <= c2.b) ? c2 : c1;  // меньшая альт. цена X специализируется первой
    const Atot = lo.a + hi.a, xk = lo.Xmax, Xtot = lo.Xmax + hi.Xmax, Ykink = hi.a;
    if (Math.abs(lo.b - hi.b) < 1e-6) {
      const text = `Y = ${fmt(Atot)} − ${fmt(lo.b)}·X,  X ∈ [0; ${fmt(Xtot)}]  (равные альтернативные издержки дают одну прямую).`;
      return { type: 'линейная (1 кусок)', text, evalY: (x) => (x >= 0 && x <= Xtot) ? Atot - lo.b * x : NaN, kinks: [] };
    }
    const C = hi.a + hi.b * xk;                       // второй кусок: Y = C − hi.b·X
    const text = `Y = ${fmt(Atot)} − ${fmt(lo.b)}·X при X ∈ [0; ${fmt(xk)}];  ` +
                 `Y = ${fmt(C)} − ${fmt(hi.b)}·X при X ∈ [${fmt(xk)}; ${fmt(Xtot)}].`;
    const evalY = (x) => { if (x < 0 || x > Xtot) return NaN; return x <= xk ? Atot - lo.b * x : C - hi.b * x; };
    return { type: 'линейная (2 куска)', text, evalY, kinks: [[xk, Ykink]] };
  }
  // Обе эллипс/дуга с одинаковым b → одна дуга (эллипс) суммы.
  if (c1.type === 'ellipse' && c2.type === 'ellipse' && Math.abs(c1.b - c2.b) < 1e-4) {
    const b = (c1.b + c2.b) / 2;
    const S = Math.pow(Math.sqrt(c1.a) + Math.sqrt(c2.a), 2);   // (r1+r2)² при b=1
    const psum = Math.sqrt(S / b);
    const text = Math.abs(b - 1) < 1e-4
      ? `Y = √(${fmt(S)} − X²),  X ∈ [0; ${fmt(psum)}]  (дуга радиуса ${fmt(Math.sqrt(S))}).`
      : `Y = √(${fmt(S)} − ${fmt(b)}·X²),  X ∈ [0; ${fmt(psum)}].`;
    return { type: 'дуга/эллипс (1 кусок)', text, evalY: (x) => { const v = S - b * x * x; return v >= 0 ? Math.sqrt(v) : NaN; }, kinks: [] };
  }
  // Обе параболы → внутренняя часть имеет аккуратный вид; хвост строим численно.
  if (c1.type === 'parabola' && c2.type === 'parabola') {
    const a1 = c1.a, a2 = c2.a, b1 = c1.b, b2 = c2.b, bEff = b1 * b2 / (b1 + b2);
    const Xint = Math.min(c1.Xmax * (b1 + b2) / b2, c2.Xmax * (b1 + b2) / b1);
    const text = `внутр. часть: Y = ${fmt(a1 + a2)} − ${fmt(bEff)}·X² при X ∈ [0; ${fmt(Xint)}]; далее идёт хвост (построен численно).`;
    return { type: 'парабола (внутр. часть)', text, evalY: (x) => (x < 0 || x > Xint) ? NaN : (a1 + a2) - bEff * x * x, kinks: [] };
  }
  return { type: 'численная', text: null, evalY: null, kinks: [] };
}

// Сверка аналитической формулы с численной кривой (доля совпавших точек).
function verifyFormula(evalY, points) {
  let tested = 0, ok = 0;
  for (const p of points) {
    if (!p || isNaN(p[1])) continue;
    const y = evalY(p[0]); if (isNaN(y)) continue;
    tested++; if (Math.abs(y - p[1]) <= 0.01 * (1 + Math.abs(p[1]))) ok++;
  }
  return tested >= 5 && ok / tested >= 0.98;
}

// Численное определение изломов (резкая смена наклона) — для не распознанных пар.
function detectKinks(points) {
  const valid = points.filter(p => p && !isNaN(p[1])); const ks = [];
  if (valid.length < 5) return ks;
  const slope = (i) => (valid[i + 1][1] - valid[i][1]) / (valid[i + 1][0] - valid[i][0]);
  for (let i = 1; i < valid.length - 2; i++) {
    const s0 = slope(i - 1), s1 = slope(i);
    if (isFinite(s0) && isFinite(s1) && Math.abs(s1 - s0) > 0.15 * (1 + Math.abs(s0)))
      if (!ks.length || Math.abs(valid[i][0] - ks[ks.length - 1][0]) > 1e-3) ks.push(valid[i]);
  }
  return ks;
}

/* ⚠️ ОТКАЗ НАЗЫВАЕТСЯ ТАМ, ГДЕ ЧЕЛОВЕК НАБИРАЛ, А НЕ ТОЛЬКО В АНАЛИТИКЕ.

   Замер 22.08: непонятую формулу все четыре модели блока честно ловили и
   складывали текст отказа в свой разбор (`info-ppfsum`, `info-ppft`,
   `info-tb`) — то есть в правую панель, в блок «Ключевые значения», который
   по умолчанию свёрнут. Рядом с самим полем в разметке лежали три готовых
   места под сообщение (`ppfsum-error`, `ppft-error`, `tb-error`), и в них не
   писал никто и никогда. Человек смотрит на поле, в которое печатал: для него
   формула не принималась молча, а ползунок буквы при этом заводился и
   выглядел рабочим.

   Пишем в обе стороны и из пути ОТРИСОВКИ, а не из обработчика кнопки: до
   расчёта можно добраться и правкой поля, и Enter, и сменой числа кривых. */
function showPaneError(boxId, msg) {
  const box = document.getElementById(boxId);
  if (!box) return;
  if (msg) { box.textContent = 'Не понял формулу: ' + msg; box.style.display = 'block'; }
  else { box.textContent = ''; box.style.display = 'none'; }
}

// Тяжёлый расчёт суммарной КПВ (кэшируется в STATE.ppfSumData; запускается по «Построить»).
/* Сколько кривых складываем (Фаза 13.1) и их формулы. Первые две живут в
   прежних STATE.ppf1 / STATE.ppf2, чтобы ничего из проверенной пары не
   поехало; остальные — в массиве. */
function ppfSumCount() { return Math.max(2, Math.min(5, +STATE.ppfSumCount || 2)); }
function ppfSumGet(i) {
  if (i === 0) return STATE.ppf1;
  if (i === 1) return STATE.ppf2;
  return (STATE.ppfSumMore || [])[i - 2] || '';
}
function ppfSumSet(i, v) {
  if (i === 0) STATE.ppf1 = v;
  else if (i === 1) STATE.ppf2 = v;
  else { STATE.ppfSumMore = STATE.ppfSumMore || []; STATE.ppfSumMore[i - 2] = v; }
}
function ppfSumName(i) {
  const own = (STATE.ppfSumNames || [])[i];
  return (own && own.trim()) || ('КПВ ' + (i + 1));
}
function ppfSumColor(i) {
  const own = (STATE.ppfSumColors || [])[i];
  if (own) return own;
  const pal = [COL.tax, COL.reg, COL.MR, COL.MC, COL.S];
  return pal[i % pal.length];
}

/* Подпись входа суммы КПВ: формулы стран плюс значения ползунков (А2).

   Кэш суммы был устроен на «пусто значит пересчитать», и этого не хватало:
   открытие сцены перерисовывает её дважды (сначала переключение под-режима,
   потом общая перерисовка карточки), а между перерисовками сброс параметров
   обнулял кэш. Получалось ДВА полных пересчёта Минковского на одно открытие —
   380 миллисекунд из 433. По подписи второй пересчёт не нужен. */
function ppfSumSignature() {
  const parts = [];
  const n = ppfSumCount();
  for (let i = 0; i < n; i++) parts.push(ppfSumGet(i));
  const names = Object.keys(STATE.params || {}).sort();
  // Разделители — служебные символы, которых в формулах не бывает: иначе
  // подписи «100 - X»+«60» и «100»+«- X60» дали бы одну строку.
  return n + '\u0001' + parts.join('\u0001') + '\u0002' + paramSignature(names);
}

function recomputePpfSum() {
  recomputePpfSumRaw();
  if (STATE.ppfSumData) STATE.ppfSumData.sig = ppfSumSignature();
}

// Пересчитать, только если вход изменился с прошлого раза.
function ensurePpfSum() {
  if (!STATE.ppfSumData || STATE.ppfSumData.sig !== ppfSumSignature()) recomputePpfSum();
}

function recomputePpfSumRaw() {
  STATE.ppfSumData = null;
  const n = ppfSumCount();
  // Разбираем все кривые общим вводом блока (Фаза 11): каждая строка может быть
  // «y = …», «x = …» или неявным уравнением.
  const fs = [], cs = [], xmax = [], pts = [];
  for (let i = 0; i < n; i++) {
    const r = parsePpfEquation(ppfSumGet(i));
    if (r.error) { STATE.ppfSumData = { ok: false, error: (ppfSumName(i) + ': ' + r.error) }; return; }
    const c = classifyPpf(r.f);
    if (c.Xmax == null || !(c.Xmax > 0)) {
      STATE.ppfSumData = { ok: false, error: 'Не удалось определить границы ' + ppfSumName(i)
        + ' (нужна убывающая кривая, пересекающая обе оси).' };
      return;
    }
    fs.push(r.f); cs.push(c); xmax.push(c.Xmax);
    pts.push(singlePpfPoints(r.f, c.Xmax));
  }

  /* Складываем по Минковскому попарно: сумма ассоциативна, поэтому свёртка
     слева направо даёт тот же результат, что и разом. Для двух кривых путь
     буквально прежний — проверенные контрольные числа не сдвигаются. */
  let accF = fs[0], accX = xmax[0];
  let points = pts[0];
  for (let i = 1; i < n; i++) {
    points = combinedPpfPoints(accF, fs[i], accX, xmax[i], 240);
    accX = accX + xmax[i];
    const snapshot = points;
    accF = (x) => interpY(snapshot, x);
  }

  const Xtot = xmax.reduce((s, v) => s + v, 0);
  const Ytot = fs.reduce((s, f) => s + f(0), 0);

  /* Аналитическая форма и изломы.

     ПЕРВЫМ идёт линейный случай — он работает для ЛЮБОГО числа кривых, даёт
     закрытую форму по участкам и ТОЧНЫЕ изломы (замер 25.08: численный
     детектор давал (99,999; 60,001) там, где ответ ровно (100; 60)).
     Не все кривые линейны — прежние пути на месте: пара разбирается
     распознавателем, три и больше честно строятся численно. */
  let formulaText, formulaTex = null, formulaType = null, kinksXY;
  const lin = combinedPpfLinearRecord(cs);
  if (lin && verifyFormula(lin.evalY, points)) {
    formulaTex = lin.latex;
    formulaText = null;
    formulaType = lin.type;
    kinksXY = lin.kinks;
  } else if (n === 2) {
    const fr = combinedPpfFormula(cs[0], cs[1]);
    formulaText = fr.text;
    if (fr.evalY) {
      if (!verifyFormula(fr.evalY, points)) formulaText = 'Аналитическая форма не подтвердилась, кривая построена численно.';
    } else { formulaText = 'Построена численно (аналитическая форма для этой пары не распознана).'; }
    kinksXY = detectCombinedKinks(fs[0], fs[1], xmax[0], xmax[1]);
  } else {
    formulaText = 'Построена численно: складываем по очереди, ' + n + ' кривые.';
    kinksXY = detectSumKinks(points);
  }
  STATE.ppfSumKinks = kinksXY;
  const kinks = kinksXY.map(k => [k.x, k.y]);       // [x,y]-пары для существующей отрисовки/панели

  // Порядок специализации: кто дешевле производит X, тот и наращивает его первым.
  const order = cs.map((c, i) => ({
    i, name: ppfSumName(i), color: ppfSumColor(i),
    Xmax: xmax[i], Ymax: fs[i](0),
    opp: (c.type === 'linear' && c.b > 0) ? c.b : (fs[i](0) / xmax[i]),
    type: c.type,
  })).sort((a, b) => a.opp - b.opp);

  STATE.ppfSumData = {
    ok: true, points, n, parts: pts,
    c1pts: pts[0], c2pts: pts[1],                   // прежние имена для старой отрисовки
    Xtot, Ytot, x1max: xmax[0], x2max: xmax[1], xmax,
    formulaText, formulaTex,
    kinks, type: formulaType || (n === 2 ? combinedPpfFormula(cs[0], cs[1]).type : 'numeric'),
    order,
  };
  applyAutoRanges(padMax(Xtot), padMax(Ytot));
}

/* Строки ввода складываемых кривых. Заводятся по числу в поле «Сколько кривых»,
   каждая по общему стандарту блока: своё имя, свой цвет, уравнение в любой из
   трёх форм и серый пример в пустой строке. */
function renderPpfSumRows() {
  const box = document.getElementById('ppfsum-rows');
  if (!box) return;
  const n = ppfSumCount();
  const DEF = ['y = 100 - x', 'y = 60 - 3*x', 'y = 40 - 0.5*x', 'y = 90 - 2*x', 'y = 50 - x'];
  STATE.ppfSumNames = STATE.ppfSumNames || [];
  STATE.ppfSumColors = STATE.ppfSumColors || [];
  box.innerHTML = '';
  for (let i = 0; i < n; i++) {
    if (!ppfSumGet(i)) ppfSumSet(i, DEF[i] || 'y = 50 - x');
    const wrap = document.createElement('div');
    wrap.className = 'field f-wrap';

    const lab = document.createElement('label');
    const nameInp = document.createElement('input');
    nameInp.type = 'text'; nameInp.className = 'ppfsum-name';
    nameInp.value = STATE.ppfSumNames[i] || '';
    nameInp.placeholder = 'КПВ ' + (i + 1);
    nameInp.setAttribute('data-tip', 'Имя кривой на графике');
    nameInp.addEventListener('input', () => { STATE.ppfSumNames[i] = nameInp.value; redrawAll(); });
    const pick = makeColorPicker(ppfSumColor(i), (hex) => { STATE.ppfSumColors[i] = hex; redrawAll(); },
                                 'Цвет кривой ' + (i + 1));
    lab.append(pick, nameInp);

    const row = document.createElement('div');
    row.className = 'f-row';
    const inp = document.createElement('input');
    inp.type = 'text'; inp.id = 'inp-ppfsum-' + i;
    inp.value = ppfSumGet(i);
    inp.placeholder = 'Например: ' + (DEF[i] || 'y = 50 - x');
    inp.autocomplete = 'off';
    inp.addEventListener('input', () => { ppfSumSet(i, inp.value.trim()); });
    inp.addEventListener('change', () => { STATE.ppfSumData = null; redrawAll(); });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { ppfSumSet(i, inp.value.trim()); STATE.ppfSumData = null; redrawAll(); }
    });
    row.appendChild(inp);
    wrap.append(lab, row);
    box.appendChild(wrap);
    equipFormulaField(inp.id, 'PPF');
  }
}

/* Изломы численной суммы: точки, где заметно меняется наклон ломаной.
   Для пары кривых работает режимный детектор detectCombinedKinks, он точнее;
   здесь общий запасной путь для трёх и более. */
function detectSumKinks(points) {
  const out = [];
  const p = points.filter(q => q && isFinite(q[1]));
  if (p.length < 5) return out;
  const slope = (i) => (p[i + 1][1] - p[i][1]) / Math.max(1e-9, p[i + 1][0] - p[i][0]);
  const span = Math.abs(p[p.length - 1][0] - p[0][0]);
  for (let i = 1; i < p.length - 2; i++) {
    const a = slope(i - 1), b = slope(i + 1);
    if (!isFinite(a) || !isFinite(b)) continue;
    if (Math.abs(b - a) > 0.06 * (1 + Math.abs(a))) {
      const x = p[i][0], y = p[i][1];
      if (!out.some(k => Math.abs(k.x - x) < span * 0.02)) out.push({ x, y });
    }
  }
  return out.slice(0, 8);
}

// Отрисовка суммарной КПВ: бледные исходные кривые + жирная синяя суммарная + заливка.
function drawPpfSumCurves(d) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(p => p && !isNaN(p[1])).x(p => sx(p[0])).y(p => sy(p[1]));
  // Все слагаемые бледным пунктиром, каждое своим цветом и со своим именем.
  (d.parts || []).forEach((pts, i) => {
    const c = ppfSumColor(i);
    g.append('path').datum(pts).attr('fill', 'none').attr('stroke', c).attr('stroke-width', 1.6)
      .attr('stroke-dasharray', '5 4').attr('opacity', 0.6).attr('d', line);
    labelCurve(g, (x) => interpY(pts, x), ppfSumName(i), c, { below: i % 2 === 1 });
  });
  const area = d3.area().defined(p => p && !isNaN(p[1])).x(p => sx(p[0])).y0(sy(0)).y1(p => sy(p[1]));
  const sumC = STATE.ppfSumColor || COL.D;
  g.append('path').datum(d.points).attr('d', area).attr('fill', sumC).attr('opacity', 0.07)
    .attr('data-legend', 'Достижимые наборы');
  g.append('path').datum(d.points).attr('fill', 'none').attr('stroke', sumC).attr('stroke-width', 2.8).attr('d', line);
  if (STATE.bundleOn) drawBundleRay(g, (x) => interpY(d.points, x), sumC);
}

/* Подписи суммарной КПВ. От каждого излома идёт пунктир к обеим осям с
   координатами (Фаза 13.4): слово «излом» рядом с точкой ничего не добавляло,
   а вот сами числа на осях и есть ответ задачи. */
function drawPpfSumMarks(d) {
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  (d.kinks || []).forEach(k => {
    const px = sx(k[0]), py = sy(k[1]);
    g.append('line').attr('x1', ox).attr('y1', py).attr('x2', px).attr('y2', py)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3').attr('opacity', .7);
    g.append('line').attr('x1', px).attr('y1', oy).attr('x2', px).attr('y2', py)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3').attr('opacity', .7);
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4).attr('fill', COL.ink)
      .attr('stroke', COL.halo).attr('stroke-width', 1.5);
    axisValueX(g, px, oy, fmt(k[0]), '');
    axisValueY(g, ox, py, fmt(k[1]), '');
  });
  // концы суммарной кривой
  axisValueY(g, ox, sy(d.Ytot), fmt(d.Ytot), '');
  axisValueX(g, sx(d.Xtot), oy, fmt(d.Xtot), '');
  const midX = d.Xtot * 0.5, midY = interpY(d.points, midX);
  const nm = (STATE.ppfSumName || '').trim() || 'Сумма';
  if (!isNaN(midY)) g.append('text').attr('x', sx(midX)).attr('y', sy(midY) - 8)
    .attr('font-size', curveLabelSize()).attr('font-weight', 600).attr('fill', STATE.ppfSumColor || COL.D)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(nm);
}

/* Разбор суммарной КПВ (Фаза 13.5). Панель ОБЪЯСНЯЕТ то, что посчитал
   проверенный алгоритм сложения по Минковскому, и ничего не считает заново:
   изломы, концы и порядок специализации берутся из его же результата. */
function updatePpfSumPanel() {
  const box = document.getElementById('info-ppfsum'); if (!box) return;
  const d = STATE.ppfSumData;
  showPaneError('ppfsum-error', (d && !d.ok) ? (d.error || 'Не удалось построить.') : '');
  if (!d) { box.innerHTML = '<div class="muted">Введите кривые и нажмите «Построить сумму».</div>'; return; }
  if (!d.ok) { box.innerHTML = '<div class="warn">' + (d.error || 'Не удалось построить.') + '</div>'; return; }
  const ord = d.order || [];
  let html = '';
  html += `<div class="stat"><span>Складываем кривых</span><b>${d.n}</b></div>`;
  html += `<div class="stat"><span>$X_{max}$ суммарной</span><b>${fmt(d.Xtot)}</b></div>`;
  html += `<div class="stat"><span>$Y_{max}$ суммарной</span><b>${fmt(d.Ytot)}</b></div>`;
  (d.kinks || []).forEach((k, i) => {
    html += `<div class="stat"><span>Точка излома ${i + 1}</span><b>${fmt(k[0])}; ${fmt(k[1])}</b></div>`;
  });
  if (STATE.bundleOn) {
    const b = bundleRay((x) => interpY(d.points, x));
    if (b) {
      html += `<div class="stat"><span>Комплект ${fmt(b.kx)} X на ${fmt(b.ky)} Y</span><b>${fmt(b.x)}; ${fmt(b.y)}</b></div>`;
      html += `<div class="stat"><span>Целых комплектов</span><b>${b.whole}</b></div>`;
    }
  }

  html += '<div class="sb-note"><b>Как это получилось</b>';
  html += '<p><b>Почему кривые нельзя просто сложить по вертикали?</b> Потому что участники ДЕЛЯТ общий выпуск. Складываем по Минковскому: для каждого суммарного выпуска '
        + '$X$ перебираем все способы разделить его между участниками и берём тот, где общий '
        + '$Y$ наибольший. Формально это '
        + '$Y(X) = \\max\\{\\, \\sum_i f_i(x_i) \\;:\\; \\sum_i x_i = X \\,\\}$. '
        + 'Вертикальная сумма $f_1(X) + f_2(X)$ дала бы другую и неверную кривую: '
        + 'она означала бы, что каждый выпускает по $X$ единиц, а не что они делят общий выпуск.</p>';

  if (ord.length) {
    html += '<p><b>Кто начинает первым?</b> Порядок специализации задают альтернативные издержки $X$: первым наращивает '
          + 'тот, кому единица $X$ обходится дешевле в единицах $Y$.</p>';
    html += '<div class="tbl">' + ord.map((o, i) =>
      `<div><span>${i + 1}. ${o.name}</span><b>${fmt(o.opp)} Y за ед. X</b></div>`).join('') + '</div>';
    html += `<p>Поэтому кривая начинается с самого пологого участка (${ord[0].name}, `
          + `${fmt(ord[0].opp)} Y за единицу X) и дальше становится круче: дешёвые возможности `
          + 'кончаются, в дело идут те, у кого X дороже.</p>';
  }

  if ((d.kinks || []).length) {
    html += '<p>Излом появляется там, где очередной участник исчерпал свои возможности по $X$ '
          + 'и эстафету принимает следующий, с более высокими издержками. Координаты изломов '
          + 'следующие:</p>';
    html += '<div class="tbl">' + d.kinks.map((k, i) =>
      `<div><span>излом ${i + 1}</span><b>X = ${fmt(k[0])}, Y = ${fmt(k[1])}</b></div>`).join('') + '</div>';
    if (ord.length >= 2) {
      html += `<p>Первый излом стоит ровно там, где ${ord[0].name} отдал под X весь свой ресурс: `
            + `$X = ${fmt(ord[0].Xmax)}$. Дальше X может наращивать только ${ord[1].name}.</p>`;
    }
  } else {
    html += '<p>Изломов нет: кривые гладкие, издержки меняются непрерывно, и участники '
          + 'наращивают X одновременно, а не по очереди. Так бывает у дуг и парабол.</p>';
  }

  html += `<p>Концы суммарной кривой это просто суммы концов: $X_{max} = ${fmt(d.Xtot)}$ `
        + `и $Y_{max} = ${fmt(d.Ytot)}$. Если все отдадут ресурс одному товару, выпуски складываются.</p>`;
  /* Форма кривой набирается МАТЕМАТИКОЙ, когда закрытая форма есть: запись
     функции здесь и есть предмет обучения, а обычным текстом «X ∈ [0; 100]»
     читается как строка из журнала. Ширину подгоняет общий проход
     fitPanelMath — врезка у него та же. */
  if (d.formulaTex) {
    html += `<p><b>Форма кривой:</b> $${d.formulaTex}$</p>`;
  } else {
    html += `<p><b>Форма кривой:</b> ${d.formulaText || 'не подобралась'}</p>`;
  }
  html += '</div>';
  box.innerHTML = html;
}

/* --- Задача 2: режим «Схема» суммарной КПВ -------------------------- */

// Русская запись числа (десятичная запятая) — для подписей схемы.
function fmtRu(v) { return fmt(v).replace('.', ','); }

// Данные для схемы: ключевые точки (НАСТОЯЩИЕ значения) и типы участков.
// Возвращает { ok, n, pts:[{x,y,kind}], segs:[{type, convex?}] } или { ok:false }.
function ppfSumSchemaData() {
  const d = STATE.ppfSumData;
  if (!d || !d.ok) return { ok: false };
  const kinks = (STATE.ppfSumKinks || []).slice().sort((a, b) => a.x - b.x);
  const n = kinks.length + 1;
  if (n > 3) return { ok: false };                  // больше 3 участков — схему не рисуем
  const keyX = [0, ...kinks.map(k => k.x), d.Xtot];
  const keyY = [d.Ytot, ...kinks.map(k => k.y), 0];
  for (let i = 1; i < keyY.length; i++)             // итоговая кривая должна монотонно убывать
    if (keyY[i] > keyY[i - 1] + 1e-6 * (1 + Math.abs(keyY[i - 1]))) return { ok: false };
  // Точная выборка реальной кривой (через allocAt) для определения типа участка.
  const r1 = compilePpf(STATE.ppf1), r2 = compilePpf(STATE.ppf2);
  if (!r1.compiled || !r2.compiled) return { ok: false };
  const f1 = (x) => ppfEvalWith(r1.compiled, x), f2 = (x) => ppfEvalWith(r2.compiled, x);
  const yAt = (X) => allocAt(f1, f2, X, d.x1max, d.x2max).y;
  const segs = [];
  for (let i = 0; i < n; i++) {
    const Xa = keyX[i], Xb = keyX[i + 1], Ya = keyY[i], Yb = keyY[i + 1];
    const scale = Math.max(Math.abs(Xb - Xa), Math.abs(Yb - Ya), 1e-9);   // локальный масштаб участка
    let maxDev = 0, midDev = 0;
    for (let j = 1; j <= 5; j++) {                  // 5 внутренних точек, сравнение с хордой
      const t = j / 6, X = Xa + (Xb - Xa) * t;
      const dev = yAt(X) - (Ya + (Yb - Ya) * t);    // >0: кривая выше хорды (выпуклость наружу)
      if (Math.abs(dev) > Math.abs(maxDev)) maxDev = dev;
      if (j === 3) midDev = dev;
    }
    if (Math.abs(maxDev) < 0.01 * scale) segs.push({ type: 'прямая' });
    else segs.push({ type: 'дуга', convex: midDev >= 0 ? 'out' : 'in' });
  }
  const pts = keyX.map((x, i) => ({ x, y: keyY[i], kind: i === 0 ? 'start' : (i === keyX.length - 1 ? 'end' : 'kink') }));
  return { ok: true, n, pts, segs, Xtot: d.Xtot, Ytot: d.Ytot };
}

// Плашка-пометка в правом верхнем углу области.
function schemaNote(text) {
  const m = CONFIG.margin;
  svg.append('text').attr('x', W - m.right - 4).attr('y', m.top + 2).attr('text-anchor', 'end').attr('dominant-baseline', 'hanging')
    .attr('font-size', FS.base).attr('fill', COL.inkSoft).attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(text);
}

// Отрисовка схемы (НЕ в масштабе): причёсанные высоты, без числовых осей, настоящие подписи.
function drawPpfSumSchema() {
  const sd = ppfSumSchemaData();
  if (!sd.ok) {                                     // схема недоступна — обычный масштабный вид + пометка
    drawGrid(); drawAxes('X', 'Y');
    const d = STATE.ppfSumData; if (d && d.ok) { drawPpfSumCurves(d); drawPpfSumMarks(d); }
    schemaNote('схема недоступна для этого случая');
    return;
  }
  // Фиксированные «красивые» доли (отсчёт fy от верха, y вниз).
  const FR = { 1: [[0, 0], [1, 1]], 2: [[0, 0], [0.52, 0.42], [1, 1]], 3: [[0, 0], [0.30, 0.18], [0.62, 0.55], [1, 1]] }[sd.n];
  const m = CONFIG.margin;
  const plotLeft = m.left, plotTop = m.top, plotW = (W - m.right) - m.left, plotH = (H - m.bottom) - m.top;
  const baseY = H - m.bottom, originX = m.left;
  const PX = FR.map(([fx, fy]) => [plotLeft + fx * plotW, plotTop + fy * plotH]);

  // Оси со стрелками, без чисел.
  const ga = svg.append('g');
  ga.append('line').attr('x1', originX).attr('y1', baseY).attr('x2', W - m.right).attr('y2', baseY)
    .attr('stroke', COL.ink).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
  ga.append('line').attr('x1', originX).attr('y1', baseY).attr('x2', originX).attr('y2', m.top)
    .attr('stroke', COL.ink).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
  ga.append('text').attr('x', W - m.right + 6).attr('y', baseY + 4).attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.ink).text('X');
  ga.append('text').attr('x', originX - 4).attr('y', m.top - 8).attr('text-anchor', 'end').attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.ink).text('Y');

  // Путь кривой по участкам: «прямая» — отрезок, «дуга» — квадратичная Безье (выгиб наружу).
  let dPath = `M ${PX[0][0]} ${PX[0][1]}`;
  for (let i = 0; i < sd.segs.length; i++) {
    const [x0, y0] = PX[i], [x1, y1] = PX[i + 1];
    if (sd.segs[i].type === 'прямая') { dPath += ` L ${x1} ${y1}`; continue; }
    const dx = x1 - x0, dy = y1 - y0, sgn = (sd.segs[i].convex === 'in') ? -1 : 1;
    const cx = (x0 + x1) / 2 + sgn * 0.16 * dy, cy = (y0 + y1) / 2 - sgn * 0.16 * dx;
    dPath += ` Q ${cx} ${cy} ${x1} ${y1}`;
  }
  const last = PX[PX.length - 1];
  const fillPath = dPath + ` L ${last[0]} ${baseY} L ${originX} ${baseY} Z`;
  const g = svg.append('g');
  g.append('path').attr('d', fillPath).attr('fill', COL.D).attr('opacity', 0.07);
  g.append('path').attr('d', dPath).attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.8);

  // Ключевые точки + подписи настоящих значений.
  PX.forEach(([px, py], i) => {
    const pt = sd.pts[i];
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    if (pt.kind === 'start') haloText(g, px - 8, py, fmtRu(pt.y), 'end', 'middle');          // Y-перехват у оси Y
    else if (pt.kind === 'end') haloText(g, px, baseY + 8, fmtRu(pt.x), 'middle', 'hanging'); // Xmax у оси X
    else g.append('text').attr('x', px + 9).attr('y', py - 9).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.ink)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(`(${fmtRu(pt.x)}; ${fmtRu(pt.y)})`);
  });
  schemaNote('Схема · не в масштабе');
}

// Полная перерисовка под-режима «Сумма двух КПВ» (тяжёлый расчёт — только если вход изменился).
function redrawPpfSum() {
  ensurePpfSum();
  makeScales();                                     // setRanges мог изменить границы
  svg.selectAll('*').remove(); addDefs();
  const d = STATE.ppfSumData;
  // Всегда в масштабе (Фаза 13.3): «схема» показывала ту же кривую без чисел
  // и только заставляла выбирать между правдой и картинкой.
  drawGrid(); drawAxes('X', 'Y');
  if (d && d.ok) { drawPpfSumCurves(d); drawPpfSumMarks(d); }
  updatePpfSumPanel();
}

// Переключение вида суммарной КПВ (в масштабе / схема) — только перерисовка, без пересчёта.
function setPpfSumView(view) {
  // Кнопок выбора вида в разметке нет: со времён Фазы 13.3 вид один,
  // «в масштабе», и переключать нечего (Свх-4б).
  STATE.ppfSumView = view;
  redrawAll();
}

/* --- Задача 2: КТВ — кривая торговых возможностей ------------------- */

// Угловое (полная специализация) решение по ценности: специализация туда, где
// суммарная выручка больше. Используется для линейной и выпуклой КПВ.
function cornerByValue(Xmax, Ymax, ratio) {
  if (ratio * Xmax > Ymax) return { xp: Xmax, yp: 0, regime: 'специализация на X' };
  return { xp: 0, yp: Ymax, regime: 'специализация на Y' };
}

// Расчёт КТВ: точка производства и линия торговых возможностей.
/* ТОЧКА ПРОИЗВОДСТВА ПО НАИБОЛЬШЕЙ ЦЕННОСТИ ВЫПУСКА.
   Страна производит там, где выпуск в мировых ценах стоит дороже всего, то
   есть где максимальна величина Y + (Px/Py)·X. Это ОДНО правило на все формы
   КПВ: у прямой и у выпуклой максимум всегда в углу (прежнее поведение
   сохраняется), у вогнутой — во внутренней точке, а у ВОГНУТОЙ КУСОЧНОЙ он
   садится ровно в излом. Особого пути для излома здесь нет и заводить его не
   надо — в проекте уже убирали такой особый путь у ключевых точек.

   ⚠️ Замер 24.08 до правки. Кусочная КПВ Y = 100 − 0,5·X при X < 40 и
   Y = 160 − 2·X при X ≥ 40 (стык в (40; 80), ось при X = 80) при мировой цене
   Px/Py = 1 давала «специализация на Y», производство (0; 100). Ценность там
   100, а в изломе 40·1 + 80 = 120 — движок выбирал заведомо худшую точку,
   потому что кусочная не опознавалась ни как прямая, ни как дуга и уходила в
   ветку «только углы».

   Сетка с уточнением, а не аналитика: КПВ приходит формулой любого вида, и
   производной у неё в изломе просто нет. Четыре прохода по 400 узлов сужают
   отрезок в 400 раз каждый — стык находится точно. */
function bestByValue(f, Xmax, Ymax, ratio) {
  const val = (x) => { const y = f(x); return isFinite(y) ? (y + ratio * x) : -Infinity; };
  let lo = 0, hi = Xmax, bx = 0, bv = val(0);
  for (let pass = 0; pass < 4; pass++) {
    const N = 400, step = (hi - lo) / N;
    if (!(step > 0)) break;
    for (let i = 0; i <= N; i++) {
      const x = lo + step * i, v = val(x);
      if (v > bv + 1e-12) { bv = v; bx = x; }
    }
    lo = Math.max(0, bx - step); hi = Math.min(Xmax, bx + step);
  }
  const eps = Math.max(Xmax * 1e-6, 1e-9);
  if (bx <= eps) return { xp: 0, yp: Ymax, regime: 'специализация на Y' };
  if (bx >= Xmax - eps) return { xp: Xmax, yp: 0, regime: 'специализация на X' };
  const y = f(bx);
  return { xp: bx, yp: isFinite(y) ? y : 0, regime: 'касание (внутр. точка)' };
}

function recomputePpfTrade() {
  STATE.ppfTradeData = null;
  const r = parsePpfEquation(STATE.ppftFormula);
  if (r.error) { STATE.ppfTradeData = { ok: false, error: r.error }; return; }
  const f = r.f;
  const c = classifyPpf(f);
  if (c.Xmax == null || !(c.Xmax > 0)) { STATE.ppfTradeData = { ok: false, error: 'Не удалось определить границы КПВ.' }; return; }
  const Xmax = c.Xmax, Ymax = f(0);
  // Задача 2: зажать мировую цену в диапазон вокруг наклона КПВ — страховка от «улёта».
  const sl = (c.type === 'linear' && c.b > 0) ? c.b : ((Ymax > 0 && Xmax > 0) ? Ymax / Xmax : 1);
  const priceMin = 0.1, priceMax = Math.max(4 * sl, 0.2);
  let ratio = STATE.ppftPrice;
  if (!(ratio > 0)) ratio = sl;                         // запас на пустое/битое значение
  ratio = Math.max(priceMin, Math.min(priceMax, ratio));
  STATE.ppftPrice = Math.round(ratio * 100) / 100;
  ratio = STATE.ppftPrice;
  let xp, yp, regime;
  if (c.type === 'ellipse' || c.type === 'parabola') {
    // Вогнутая: точка касания, где |наклон КПВ| = мировой цене.
    const xt = findRootIn(x => (-ppfSlopeOf(f, x)) - ratio, 1e-4, Xmax - 1e-4);
    if (xt != null) { xp = xt; yp = f(xt); regime = 'касание (внутр. точка)'; }
    else ({ xp, yp, regime } = cornerByValue(Xmax, Ymax, ratio));
  } else if (c.type === 'linear') {
    const b = c.b;                                  // внутренняя альт. цена X
    if (Math.abs(b - ratio) < 1e-9) { xp = null; yp = null; regime = 'нет торговли'; }
    else if (ratio > b) { xp = Xmax; yp = 0; regime = 'специализация на X'; }
    else { xp = 0; yp = Ymax; regime = 'специализация на Y'; }
  } else {
    // Выпуклая, кусочная или незнакомая форма — общее правило по ценности.
    ({ xp, yp, regime } = bestByValue(f, Xmax, Ymax, ratio));
  }
  let line = null, xint = null, yint = null;
  if (regime !== 'нет торговли' && xp != null) {
    const c0 = yp + ratio * xp;                     // Y-перехват КТВ: Y = c0 − ratio·X
    line = { intercept: c0, slope: ratio }; yint = c0; xint = c0 / ratio;
  }
  STATE.ppfTradeData = { ok: true, c, Xmax, Ymax, ratio, xp, yp, regime, line, xint, yint, priceMin, priceMax, ppfPts: singlePpfPoints(f, Xmax) };
  const xm = Math.max(Xmax, xint || 0), ym = Math.max(Ymax, yint || 0);
  applyTradeRanges(padMax(xm), padMax(ym));  // плавно при смене Pw, иначе мгновенно
}

// Отрисовка КТВ: КПВ страны (синяя) + линия торговых возможностей (красная).
function drawPpfTrade(d) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(p => p && !isNaN(p[1])).x(p => sx(p[0])).y(p => sy(p[1]));
  const area = d3.area().defined(p => p && !isNaN(p[1])).x(p => sx(p[0])).y0(sy(0)).y1(p => sy(p[1]));
  g.append('path').datum(d.ppfPts).attr('d', area).attr('fill', COL.D).attr('opacity', 0.06);
  g.append('path').datum(d.ppfPts).attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.5).attr('d', line);
  if (d.line) {
    const pts = [[0, d.line.intercept], [d.xint, 0]];          // прямая КТВ от (0,c0) до (xint,0)
    g.append('path').datum(pts).attr('fill', 'none').attr('stroke', COL.S).attr('stroke-width', 2.5).attr('d', line);
    // Задача 2: линия цены больше не перетаскивается мышью — управление ползунком Px/Py.
  }
  /* П4: в сцене есть и КПВ, и КТВ — луч комплектов обязан пересечь ОБЕ,
     и обе точки показываются с координатами. */
  if (STATE.bundleOn) {
    const ppfF = (x) => interpY(d.ppfPts, x);
    const list = [{ f: ppfF, name: 'КПВ' }];
    if (d.line) {
      const c0 = d.line.intercept, k = (d.xint > 0) ? (c0 / d.xint) : 0;
      list.push({ f: (x) => c0 - k * x, name: 'КТВ' });
    }
    drawBundleRay(g, ppfF, null, list);
  }
}

// Подписи КТВ: точка производства, ярлыки кривых, перехваты (макс потребление).
function drawPpfTradeMarks(d) {
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  if (d.line) {
    g.append('text').attr('x', sx(d.xint * 0.5)).attr('y', sy(d.line.intercept * 0.5) - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.S)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('КТВ');
  }
  if (d.xp != null) {
    const px = sx(d.xp), py = sy(d.yp);
    const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    dash(px, py, px, oy); dash(px, py, ox, py);
    const dot = g.append('circle').attr('cx', px).attr('cy', py).attr('r', 5)
      .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 2);
    // Слово «производство» висело на графике всегда и загораживало кривую.
    // Теперь всплывает при наведении на саму точку.
    hoverLabel(g, dot, px + 8, py - 8, 'производство');
    // Координаты точки производства и пределы потребления — обычными делениями
    // на осях. Подписи вида «Xмакс=100» налезали на соседние числа оси.
    if (Math.abs(d.xp) > 1e-9) extraTickX(g, d.xp);
    if (Math.abs(d.yp) > 1e-9) extraTickY(g, d.yp);
  }
  if (d.line) {
    extraTickY(g, d.yint, COL.S);
    extraTickX(g, d.xint, COL.S);
  }
}

// Табло КТВ: режим, мировая цена, точка производства, максимальное потребление, формула линии.
function updatePpfTradePanel() {
  const box = document.getElementById('info-ppft'); if (!box) return;
  const d = STATE.ppfTradeData;
  showPaneError('ppft-error', (d && !d.ok) ? (d.error || 'Не удалось.') : '');
  if (!d) { box.innerHTML = '<div class="muted">Введите КПВ и мировую цену, нажмите «Построить КТВ».</div>'; return; }
  if (!d.ok) { box.innerHTML = '<div class="warn">' + (d.error || 'Не удалось.') + '</div>'; return; }
  // Внутренняя (автарктическая) цена X: наклон КПВ. У прямой он один, у дуги
  // берём его в точке производства — там и происходит сравнение с мировой.
  const inner = (d.c.type === 'linear' && d.c.b > 0)
    ? d.c.b
    : ((d.xp != null && d.xp > 0) ? Math.abs(ppfSlopeOf((x) => interpY(d.ppfPts, x), d.xp))
                                  : (d.Ymax / d.Xmax));
  /* ⚠️ НЕ fmt(inner) НАПРЯМУЮ, ЕСЛИ inner НЕ ЧИСЛО. fmt(NaN) печатает буквально
     «NaN» (isFinite-проверка внутри fmt отдаёт String(v) как есть), а
     fmt(null) — куда коварнее: roundShown(null) считает null нулём, и «нет
     значения» на экране неотличимо от настоящего нуля. Оба варианта врут.
     Есть значение — печатаем; нет — говорим об этом словами. */
  const innerHtml = (typeof inner === 'number' && isFinite(inner))
    ? fmt(inner)
    : '<span class="muted">не определена</span>';
  let html = '';
  html += `<div class="stat"><span>Режим</span><b>${d.regime}</b></div>`;
  html += `<div class="stat"><span>Мировая цена $P_x/P_y$</span><b>${fmt(d.ratio)}</b></div>`;
  html += `<div class="stat"><span>Внутренняя цена X (наклон КПВ)</span><b>${innerHtml}</b></div>`;
  if (d.xp != null) {
    html += `<div class="stat"><span>Производство $(X_п; Y_п)$</span><b>(${fmt(d.xp)}; ${fmt(d.yp)})</b></div>`;
  }
  if (d.line) {
    html += `<div class="stat"><span>Предел потребления $X_{макс}$</span><b>${fmt(d.xint)}</b></div>`;
    html += `<div class="stat"><span>Предел потребления $Y_{макс}$</span><b>${fmt(d.yint)}</b></div>`;
    /* Н16. Прирост от торговли это разница ПОТРЕБЛЕНИЯ, а его задаёт кривая
       комплектов: страна потребляет X и Y в заданной пропорции. Сравнивать надо
       две точки на одном луче — где он встречает КТВ (потребление при торговле)
       и где встречает КПВ (потребление при автаркии). Раньше здесь стояла
       разность перехватов линий с осями (xint − Xmax), то есть сравнивались
       крайние точки, в которых страна потребляет только один товар, а кривая
       комплектов в расчёте не участвовала вовсе. */
    const gain = tradeBundleGain(d);
    if (gain) {
      html += `<div class="stat"><span>Потребление при автаркии $(X; Y)$</span>`
            + `<b>(${fmt(gain.aut.x)}; ${fmt(gain.aut.y)})</b></div>`;
      html += `<div class="stat"><span>Потребление при торговле $(X; Y)$</span>`
            + `<b>(${fmt(gain.tr.x)}; ${fmt(gain.tr.y)})</b></div>`;
      const sign = (v) => (v >= 0 ? '+' : '') + fmt(v);
      html += `<div class="stat"><span>Прирост против автаркии по X</span><b>${sign(gain.dx)}</b></div>`;
      html += `<div class="stat"><span>Прирост против автаркии по Y</span><b>${sign(gain.dy)}</b></div>`;
    } else {
      html += '<div class="stat stat-hint"><span>Прирост против автаркии</span>'
            + '<b>Постройте кривую комплектов</b></div>';
    }
  }

  html += '<div class="sb-note"><b>Как это получилось</b>';
  html += `<p><b>Стоит ли вообще торговать?</b> Сравниваем две цены. Внутренняя цена X это альтернативные издержки: сколько Y страна теряет за `
        + `единицу X, если делает всё сама. Здесь ${fmt(inner)}. Мировая цена ${fmt(d.ratio)}: `
        + (Math.abs(d.ratio - inner) < 1e-6
            ? 'она совпала с внутренней, поэтому торговать нечем.'
            : (d.ratio > inner
                ? 'за X дают больше, чем он стоит внутри, значит X выгодно производить и продавать.'
                : 'за X дают меньше, чем он стоит внутри, значит выгоднее производить Y и покупать X.'))
        + '</p>';

  if (d.xp != null) {
    if (/касание/.test(d.regime)) {
      html += `<p><b>Где остановиться с выпуском?</b> КПВ вогнутая, поэтому специализация неполная: страна наращивает X, пока `
            + `следующая единица обходится дешевле мировой цены. Останавливается там, где `
            + `издержки сравнялись с ней, то есть где наклон касательной к КПВ равен $P_x/P_y$. `
            + `Точка найдена численно: $X_п = ${fmt(d.xp)}$, $Y_п = ${fmt(d.yp)}$.</p>`;
    } else if (/нет торговли/.test(d.regime)) {
      html += '<p>Цены совпали, торговля ничего не меняет: линия возможностей ложится на КПВ.</p>';
    } else {
      html += `<p><b>Где остановиться с выпуском?</b> На самом краю. КПВ прямая, издержки не растут, поэтому выгодно уйти в специализацию целиком. `
            + `Всё производство идёт в ${d.yp === 0 ? 'X' : 'Y'}: $X_п = ${fmt(d.xp)}$, $Y_п = ${fmt(d.yp)}$.</p>`;
    }
  }

  if (d.line) {
    html += `<p>Из точки производства страна может обменивать один товар на другой по мировой `
          + `цене, поэтому линия торговых возможностей проходит через неё с наклоном, равным `
          + `$P_x/P_y = ${fmt(d.ratio)}$. Её уравнение: `
          + `$Y = ${fmt(d.line.intercept)} - ${fmt(d.ratio)}\\,X$. `
          + `Наклон КТВ это и есть мировая цена: продав единицу X, получаешь ${fmt(d.ratio)} единиц Y.</p>`;
    html += `<p>Концы линии показывают предел потребления, если всё продать: `
          + `$X_{макс} = ${fmt(d.xint)}$ против ${fmt(d.Xmax)} в автаркии `
          + `и $Y_{макс} = ${fmt(d.yint)}$ против ${fmt(d.Ymax)}. `
          + `Выигрыш от торговли и есть этот зазор: КТВ лежит выше КПВ везде, кроме самой точки `
          + 'производства, где они соприкасаются.</p>';
  } else {
    html += '<p>Мировая цена равна внутренней, торговать невыгодно: КТВ совпадает с КПВ.</p>';
  }
  html += '</div>';
  box.innerHTML = html;
}

// Задача 2: синхронизировать ползунок и поле мировой цены (сценарий А) с расчётом.
// Ставит диапазон ползунка по бортам, его значение и число — без событий (не зациклить).
function syncPpftPriceUI(d) {
  const sl = document.getElementById('ppft-price-slider'),
        num = document.getElementById('inp-ppft-price'),
        val = document.getElementById('ppft-price-val');
  if (!d || !d.ok) return;
  if (sl) { sl.min = d.priceMin; sl.max = d.priceMax; sl.value = d.ratio; }
  if (num) { num.min = d.priceMin; num.max = d.priceMax; num.value = d.ratio; }
  if (val) val.textContent = fmt(d.ratio);
}

// Полная перерисовка под-режима «КТВ» (расчёт лёгкий — можно каждый раз).
function redrawPpfTrade() {
  if (STATE.tradeScenario === 'B') { redrawTradeB(); return; }   // ЧК5: эндогенная мировая цена
  recomputePpfTrade();
  makeScales();
  svg.selectAll('*').remove(); addDefs(); drawGrid(); drawAxes('X', 'Y');
  const d = STATE.ppfTradeData;
  if (d && d.ok) { drawPpfTrade(d); drawPpfTradeMarks(d); }
  updatePpfTradePanel();
  syncPpftPriceUI(d);
  _wantRangeAnim = false;   // страховка: гасим запрос, даже если recompute вышел по ошибке
}

/* --- ЧК5: сценарий Б — эндогенная мировая цена двух стран -----------
   Две страны с КПВ. Автарктическая цена X каждой = наклон её КПВ. Равновесная
   мировая цена Pw устанавливается МЕЖДУ автарктическими ценами (среднее
   геометрическое — строго внутри интервала). Специализация по сравнительному
   преимуществу: страна с меньшими альт. издержками X специализируется на X и
   экспортирует его, другая — на Y. Линии торговых возможностей при Pw лежат вне
   КПВ обеих стран (выигрыш от торговли). Полноценный баланс спроса-предложения
   требует функций спроса (их нет) — берём разумную минимально достаточную
   версию: Pw эндогенна и в правильном интервале, а не задана извне. */
function recomputeTradeB() {
  STATE.tradeBData = null;
  const r1 = compilePpf(STATE.tbF1), r2 = compilePpf(STATE.tbF2);
  if (!r1.compiled || !r2.compiled) { STATE.tradeBData = { ok: false, error: r1.error || r2.error }; return; }
  const f1 = (x) => ppfEvalWith(r1.compiled, x), f2 = (x) => ppfEvalWith(r2.compiled, x);
  const c1 = classifyPpf(f1), c2 = classifyPpf(f2);
  if (c1.Xmax == null || c2.Xmax == null || !(c1.Xmax > 0) || !(c2.Xmax > 0)) {
    STATE.tradeBData = { ok: false, error: 'Не удалось определить границы КПВ (нужны убывающие кривые, пересекающие оси).' };
    return;
  }
  // Автарктическая цена X = альт. издержки X. Для линейной — наклон c.b; иначе среднее Ymax/Xmax.
  const b1 = (c1.type === 'linear') ? c1.b : (c1.Ymax / c1.Xmax);
  const b2 = (c2.type === 'linear') ? c2.b : (c2.Ymax / c2.Xmax);
  if (Math.abs(b1 - b2) < 1e-9) { STATE.tradeBData = { ok: false, error: 'Альтернативные издержки стран совпали, торговать незачем.' }; return; }
  const co1 = { idx: 1, c: c1, b: b1, color: COL.D, ppts: singlePpfPoints(f1, c1.Xmax) };
  const co2 = { idx: 2, c: c2, b: b2, color: COL.S, ppts: singlePpfPoints(f2, c2.Xmax) };
  const lowIs1 = b1 < b2;                              // у кого меньше альт. цена X — тот экспортирует X
  const lowCo = lowIs1 ? co1 : co2, highCo = lowIs1 ? co2 : co1;
  const bL = lowCo.b, bH = highCo.b;
  const Pweq = Math.sqrt(bL * bH);                     // равновесная (эндогенная) мировая цена в (bL, bH)
  /* Границы регулятора — сам экономически допустимый промежуток (Фаза 8).
     Раньше ползунок ходил по [0.1, 2×макс. автарктической], а введённое вручную
     число молча обрезалось до этого предела: набрал 9 при автарктических 1 и 2,
     получил 4 и картинку состоявшейся торговли. Теперь ползунок не выпускает
     за интервал, а введённое вручную число остаётся как есть и получает
     объяснение вместо тихой подмены. */
  const priceMin = bL, priceMax = bH;
  let manual = (STATE.tbManualPrice != null && STATE.tbManualPrice > 0);
  const Pw = manual ? STATE.tbManualPrice : Pweq;
  const inInterval = (Pw > bL + 1e-9 && Pw < bH - 1e-9);
  // Цена вне интервала: одной из стран выгоднее автаркия, обмена не будет.
  let noTradeMsg = null;
  if (!inInterval) {
    const who = (Pw <= bL + 1e-9) ? lowCo.idx : highCo.idx;
    noTradeMsg = 'Цена ' + fmt(Pw) + ' лежит вне промежутка: она обязана быть между ' +
      fmt(bL) + ' и ' + fmt(bH) + '. При такой цене стране ' + who +
      ' выгоднее автаркия, торговать она не станет, поэтому обмена нет.';
  }
  // Специализация (углы линейной КПВ): низкая страна → весь X, высокая → весь Y.
  lowCo.prod = [lowCo.c.Xmax, 0]; lowCo.exports = 'X';
  highCo.prod = [0, highCo.c.Ymax]; highCo.exports = 'Y';
  // Линия торговых возможностей через точку производства, наклон −Pw: Y = c0 − Pw·X.
  const cpf = (co) => { const c0 = co.prod[1] + Pw * co.prod[0]; return { intercept: c0, yint: c0, xint: c0 / Pw }; };
  lowCo.cpf = cpf(lowCo); highCo.cpf = cpf(highCo);

  /* Предел торговли (Фаза 15.6). Линия возможностей не может уходить в
     бесконечность: партнёр физически не выпускает столько, сколько нужно
     выменять. Страна L специализируется на X и меняет его на Y, но взять Y
     больше, чем весь выпуск страны H, неоткуда, и наоборот.

       L отдаёт E единиц X, получает Pw·E единиц Y.  Ограничение: Pw·E ≤ Y_H
       H отдаёт S единиц Y, получает S/Pw единиц X.  Ограничение: S/Pw ≤ X_L

     Дойдя до предела, страна упирается: чтобы получить ещё, ей придётся
     производить второй товар самой, то есть двигаться по СВОЕЙ КПВ, но уже
     из смещённой точки. Поэтому дальше предела линия ломается и идёт
     параллельно собственной КПВ страны, сдвинутой на объём состоявшейся
     торговли. Всё считается численно, без готовых формул. */
  const Ymax_H = highCo.c.Ymax, Xmax_L = lowCo.c.Xmax;
  // Сколько X реально удастся продать стране L и сколько Y — стране H.
  const E_L = Math.min(Xmax_L, (Pw > 0 ? Ymax_H / Pw : 0));   // экспорт X страной L
  const S_H = Math.min(Ymax_H, Pw * Xmax_L);                  // экспорт Y страной H
  lowCo.limit = {
    trade: E_L,
    // Точка, где партнёр исчерпал свой товар: дальше по прямой не пойти.
    kink: [Xmax_L - E_L, Pw * E_L],
    binding: E_L < Xmax_L - 1e-9,        // предел реально сработал
    shift: [-E_L, Pw * E_L],             // на сколько сдвинута своя КПВ за изломом
  };
  highCo.limit = {
    trade: S_H,
    kink: [S_H / Pw, Ymax_H - S_H],
    binding: S_H < Ymax_H - 1e-9,
    shift: [S_H / Pw, -S_H],
  };

  STATE.tradeBData = { ok: true, Pw, Pweq, manual, inInterval, noTrade: !inInterval, noTradeMsg, priceMin, priceMax,
    bL, bH, b1, b2, co1, co2, lowIdx: lowCo.idx, highIdx: highCo.idx,
    lowCo, highCo, Ymax_H, Xmax_L, E_L, S_H };
  const xm = Math.max(c1.Xmax, c2.Xmax, lowCo.cpf.xint, highCo.cpf.xint);
  const ym = Math.max(c1.Ymax, c2.Ymax, lowCo.cpf.yint, highCo.cpf.yint);
  applyTradeRanges(padMax(xm), padMax(ym));  // плавно при смене Pw, иначе мгновенно
}

/* Линия торговых возможностей страны с учётом предела торговли (Фаза 15.6).
   От точки производства идём по прямой с наклоном мировой цены, пока партнёру
   есть чем меняться; в точке излома торговля упирается в его выпуск, и дальше
   набор наращивается только собственным производством — по своей КПВ,
   сдвинутой на объём уже состоявшегося обмена. */
function tradeCpfPoints(co) {
  const k = co.limit;
  const pts = [[co.prod[0], co.prod[1]], [k.kink[0], k.kink[1]]];
  if (!k.binding) return pts;                 // партнёра хватило: прямая до конца
  // Хвост: своя КПВ, сдвинутая на вектор торговли.
  const own = co.ppts.filter(p => p && isFinite(p[1]));
  const tail = own.map(p => [p[0] + k.shift[0], p[1] + k.shift[1]])
                  .filter(p => p[0] >= -1e-9 && p[1] >= -1e-9);
  // Оставляем только ту часть хвоста, что дальше излома по X (или по Y вверх).
  const useX = (co.exports === 'X');
  const cut = tail.filter(p => useX ? (p[0] <= k.kink[0] + 1e-9) : (p[0] >= k.kink[0] - 1e-9));
  return pts.concat(cut.sort((a, b) => useX ? (b[0] - a[0]) : (a[0] - b[0])));
}

/* Два графика рядом: слева страна 1, справа страна 2 (Фаза 15.3). У каждой
   свои шкалы и своя область отрисовки с обрезкой, поэтому кривые одной страны
   не заезжают на территорию другой. Устроено как две панели у производной. */
function tradeBPanels() {
  const m = CONFIG.margin;
  // Заголовку панели нужна своя полоса сверху, иначе он ляжет на кривую.
  m.top = Math.max(m.top, 34);
  const gap = 44;
  const total = (W - m.right) - m.left;
  const half = (total - gap) / 2;
  const yTop = m.top, yBot = H - m.bottom;
  const mk = (x0, d, co) => {
    const xm = Math.max(co.c.Xmax, co.cpf.xint) * 1.08;
    const ym = Math.max(co.c.Ymax, co.cpf.yint) * 1.08;
    return {
      mx: d3.scaleLinear().domain([0, xm]).range([x0, x0 + half]),
      my: d3.scaleLinear().domain([0, ym]).range([yBot, yTop]),
      x0, x1: x0 + half, yTop, yBot,
    };
  };
  return [mk(m.left, 0, STATE.tradeBData.co1), mk(m.left + half + gap, 1, STATE.tradeBData.co2)];
}

// Отрисовка сценария Б: два графика рядом, у каждого своя КПВ и своя КТВ.
function drawTradeB(d) {
  const panels = tradeBPanels();
  [d.co1, d.co2].forEach((co, i) => {
    const p = panels[i];
    const clipId = 'tb-clip-' + i;
    const defs = svg.append('defs');
    defs.append('clipPath').attr('id', clipId).append('rect')
      .attr('x', p.x0 - 2).attr('y', p.yTop - 8)
      .attr('width', (p.x1 - p.x0) + 12).attr('height', (p.yBot - p.yTop) + 10);
    const g = svg.append('g').attr('clip-path', 'url(#' + clipId + ')');
    const line = d3.line().defined(q => q && isFinite(q[1])).x(q => p.mx(q[0])).y(q => p.my(q[1]));

    drawGrid(p.mx, p.my, g);
    /* Деления печатает сама сцена (ниже, вне обрезки). Без этой оговорки
       drawPlaneAxes рисовала ВТОРОЙ комплект внутри обрезки, и он был не виден. */
    drawPlaneAxes(g, p.mx, p.my, 'X', 'Y', { ticks: false });
    // Числа делений: у каждой панели свой масштаб, поэтому и подписи свои.
    // Подписи делений рисуем ВНЕ обрезки: они стоят за краем поля, и обрезка
    // срезала бы их вместе с воздухом.
    const gl = svg.append('g');
    const tk = (scale, horiz) => {
      const [lo, hi] = scale.domain();
      const step = niceTickStep(hi - lo, 5);
      for (let v = step; v <= hi + 1e-9; v += step) {
        // Класс `axis-num` — признак деления шкалы, см. разбор в planeTicksX.
        if (horiz) haloText(gl, scale(v), p.yBot + 8, fmt(v), 'middle', 'hanging').attr('class', 'axis-num');
        else       haloText(gl, p.x0 - 6, scale(v), fmt(v), 'end', 'middle').attr('class', 'axis-num');
      }
    };
    tk(p.mx, true); tk(p.my, false);
    // Заголовок панели рисуем ВНЕ обрезки: она начинается у верхней границы
    // поля, и текст над ней срезался бы вместе с воздухом.
    svg.append('text').attr('x', (p.x0 + p.x1) / 2).attr('y', p.yTop - 6)
      .attr('text-anchor', 'middle').attr('font-size', FS.base).attr('font-weight', 700)
      .attr('fill', co.color).text(tbName(co.idx));

    // КПВ и КТВ обе сплошные (Фаза 15.4): пунктир читался как «ненастоящая».
    g.append('path').datum(co.ppts).attr('fill', 'none')
      .attr('stroke', co.color).attr('stroke-width', 2.2).attr('d', line);
    // Торговли нет — нет и линии возможностей: рисовать её значило бы показывать
    // обмен, которого при такой цене не будет.
    if (!d.noTrade) g.append('path').datum(tradeCpfPoints(co)).attr('fill', 'none')
      .attr('stroke', COL.reg).attr('stroke-width', 2.2).attr('d', line);

    // Точка производства и точка предела торговли.
    if (d.noTrade) return;      // дальше только про состоявшийся обмен
    const pp = [p.mx(co.prod[0]), p.my(co.prod[1])];
    const pdot = g.append('circle').attr('cx', pp[0]).attr('cy', pp[1]).attr('r', 5)
      .attr('fill', co.color).attr('stroke', COL.halo).attr('stroke-width', 2);
    hoverLabel(g, pdot, pp[0] + 8, pp[1] + (co.prod[1] > 0 ? -8 : 16), 'производство');

    if (co.limit.binding) {
      const kp = [p.mx(co.limit.kink[0]), p.my(co.limit.kink[1])];
      g.append('circle').attr('cx', kp[0]).attr('cy', kp[1]).attr('r', 4.5)
        .attr('fill', COL.halo).attr('stroke', COL.reg).attr('stroke-width', 2.4);
      haloText(g, kp[0] + 8, kp[1] - 8, 'предел обмена', 'start', 'auto');
    }
    // Ярлык КТВ у середины прямого участка.
    const mxp = (co.prod[0] + co.limit.kink[0]) / 2, myp = (co.prod[1] + co.limit.kink[1]) / 2;
    haloText(g, p.mx(mxp) + 6, p.my(myp) - 6, 'КТВ', 'start', 'auto');
  });
}

// Подписи рисуются вместе с панелями (drawTradeB): отдельный проход по общим
// шкалам врал бы, у каждой страны теперь своя система координат.
function drawTradeBMarks() {}

// Имя страны на графике: своё или родовое.
function tbName(idx) {
  const own = (STATE.tbNames || [])[idx - 1];
  return (own && own.trim()) || ('КПВ ' + idx);
}

// Табло сценария Б.
function updateTradeBPanel() {
  const box = document.getElementById('info-tb'); if (!box) return;
  const d = STATE.tradeBData;
  showPaneError('tb-error', (d && !d.ok) ? (d.error || 'Не удалось.') : '');
  if (!d) { box.innerHTML = '<div class="muted">Введите две КПВ и нажмите «Построить торговлю».</div>'; return; }
  if (!d.ok) { box.innerHTML = '<div class="warn">' + (d.error || 'Не удалось.') + '</div>'; return; }
  let html = '';
  if (d.noTradeMsg) html += `<div class="warn" style="margin-bottom:6px;">${d.noTradeMsg}</div>`;
  html += `<div class="stat"><span>Автарк. цена X стр.1</span><b>${fmt(d.b1)}</b></div>`;
  html += `<div class="stat"><span>Автарк. цена X стр.2</span><b>${fmt(d.b2)}</b></div>`;
  html += `<div class="stat"><span>Мировая цена Pw</span><b>${fmt(d.Pw)}</b>${d.manual ? ' <span style="color:var(--curve-reg);">(своя)</span>' : ' <span style="color:var(--text2);">(равновесная)</span>'}</div>`;
  if (d.manual) html += `<div class="stat"><span>Равновесная Pw</span><b>${fmt(d.Pweq)}</b></div>`;
  html += `<div class="stat"><span>Экспортируют</span><b>${tbName(d.lowIdx)} → X, ${tbName(d.highIdx)} → Y</b></div>`;
  // Предел торговли (Фаза 15.6): сколько товара реально удаётся обменять.
  html += `<div class="stat"><span>Обмен X (макс.)</span><b>${fmt(d.E_L)}</b></div>`;
  html += `<div class="stat"><span>Обмен Y (макс.)</span><b>${fmt(d.S_H)}</b></div>`;
  if (d.lowCo.limit.binding || d.highCo.limit.binding) {
    const co = d.lowCo.limit.binding ? d.lowCo : d.highCo;
    html += `<div class="stat"><span>Излом КТВ у ${tbName(co.idx)}</span>`
          + `<b>${fmt(co.limit.kink[0])}; ${fmt(co.limit.kink[1])}</b></div>`;
  }

  html += '<div class="sb-note"><b>Почему КТВ ломается</b>';
  html += `<p><b>Откуда берётся прямая?</b> Страна ${tbName(d.lowIdx)} специализируется на X и меняет его на Y по мировой цене `
        + `$P_w = ${fmt(d.Pw)}$: за каждую отданную единицу X она получает ${fmt(d.Pw)} единиц Y. `
        + 'Пока идёт этот обмен, набор движется по прямой с наклоном мировой цены.</p>';
  html += `<p><b>Почему она не идёт бесконечно?</b> Взять Y больше, чем партнёр вообще выпускает, неоткуда. У ${tbName(d.highIdx)} `
        + `весь возможный Y это ${fmt(d.Ymax_H)}, значит продать X можно самое большее `
        + `$${fmt(d.Ymax_H)} / ${fmt(d.Pw)} = ${fmt(d.Ymax_H / d.Pw)}$ единиц. `
        + `Своих X у страны ${fmt(d.Xmax_L)}, поэтому фактический предел обмена это меньшее из двух: `
        + `${fmt(d.E_L)}.</p>`;
  if (d.lowCo.limit.binding) {
    html += `<p>Здесь предел сработал: партнёр кончился раньше, чем свой X. Прямая обрывается в `
          + `точке (${fmt(d.lowCo.limit.kink[0])}; ${fmt(d.lowCo.limit.kink[1])}) это и есть излом. `
          + 'Дальше набор можно наращивать только собственным производством второго товара, '
          + 'то есть двигаясь по своей КПВ, но уже из смещённой точки: к ней прибавлено то, '
          + 'что удалось выменять. Поэтому хвост линии идёт параллельно собственной КПВ страны.</p>';
  } else {
    html += '<p>Здесь предел не сработал: партнёра хватает, чтобы выменять весь выпуск, '
          + 'и линия возможностей идёт прямой до самой оси. Излома нет.</p>';
  }
  html += '<p>Рисовать КТВ бесконечной прямой от края до края неверно: это означало бы, что '
        + 'обменять можно сколько угодно, хотя партнёр физически столько не производит.</p>';
  html += '</div>';
  // Фаза 4б: не просто число, а КАК оно получается — логика избыточного спроса
  // и предложения, границы интервала и честная оговорка о том, чего модель не знает.
  html += '<div class="hint" style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);">' +
    '<b>Откуда берётся Pw</b><br>' +
    `Автарктическая цена X это альтернативные издержки X внутри страны: ` +
    `у страны&nbsp;${d.lowIdx} она ${fmt(d.bL)}, у страны&nbsp;${d.highIdx} она ${fmt(d.bH)}.<br><br>` +
    'Мировая цена уравновешивает мировой рынок: <b>сколько X страна-экспортёр хочет продать при цене Pw, ' +
    'столько же X страна-импортёр хочет купить</b>: избыточное предложение = избыточному спросу.<br><br>' +
    `Отсюда сразу следуют границы. При $P_w \\le ${fmt(d.bL)}$ стране&nbsp;${d.lowIdx} невыгодно продавать X ` +
    '(дома за него дают не меньше), и избыточное предложение обнуляется. ' +
    `При $P_w \\ge ${fmt(d.bH)}$ стране&nbsp;${d.highIdx} невыгодно покупать X (дешевле произвести самой), и ` +
    'обнуляется избыточный спрос. Значит равновесие обязано лежать <b>строго внутри</b> ' +
    `интервала (${fmt(d.bL)};&nbsp;${fmt(d.bH)}), и это следует из ОДНИХ КПВ, без всяких допущений.<br><br>` +
    '<b>Чего модель не знает.</b> Конкретная точка внутри интервала зависит от того, сколько каждая страна ' +
    'хочет ПОТРЕБИТЬ при данной цене, то есть от предпочтений (функций спроса). В модели из одних КПВ их нет, ' +
    'поэтому одним числом точка не определяется, определяется интервал. ' +
    `Калькулятор ставит нейтральную точку строго внутри: среднее геометрическое ` +
    `√(${fmt(d.bL)}·${fmt(d.bH)})&nbsp;=&nbsp;${fmt(d.Pweq)}. Ползунком Pw пройдите весь интервал: ` +
    'чем ближе цена к автарктической цене страны, тем меньше её выигрыш от торговли.</div>';
  if (d.manual) {
    html += `<div class="hint" style="margin-top:6px;">Сейчас цена задана вручную. Кнопка «Сбросить к равновесной» вернёт ${fmt(d.Pweq)}.</div>`;
  }
  box.innerHTML = html;
}

// Задача 2: синхронизировать ползунок и поле мировой цены (сценарий Б) с расчётом.
function syncTbPriceUI(d) {
  const sl = document.getElementById('tb-price-slider'),
        num = document.getElementById('inp-tb-price'),
        val = document.getElementById('tb-price-val');
  if (!d || !d.ok) return;
  // Ползунок ходит только по допустимому промежутку, поле принимает любое
  // число: набранное вручную не подменяем, а объясняем (см. recomputeTradeB).
  if (sl) { sl.min = d.priceMin; sl.max = d.priceMax; sl.step = Math.max((d.priceMax - d.priceMin) / 200, 0.001); sl.value = Math.max(d.priceMin, Math.min(d.priceMax, d.Pw)); }
  if (num) { num.removeAttribute('max'); num.min = 0; if (d.manual) num.value = d.Pw; else num.value = ''; }
  if (val) val.textContent = fmt(d.Pw) + (d.inInterval ? '' : ' (вне промежутка)');
}

// Полная перерисовка сценария Б.
function redrawTradeB() {
  recomputeTradeB();
  makeScales();
  svg.selectAll('*').remove(); addDefs();
  const d = STATE.tradeBData;
  // Два графика рядом (Фаза 15.3): общие оси и сетка тут не годятся, каждая
  // панель рисует свои. Ошибку разбора показываем на пустом поле.
  if (d && d.ok) drawTradeB(d);
  else { drawGrid(); drawAxes('X', 'Y'); }
  updateTradeBPanel();
  syncTbPriceUI(d);
  _wantRangeAnim = false;   // страховка: гасим запрос, даже если recompute вышел по ошибке
}

// Переключатель сценария торговли А / Б (ЧК5).
function setTradeScenario(s) {
  // Сценарий выбирает карточка сюжета, отдельных кнопок А/Б в разметке нет
  // (Свх-4б). Здесь остаётся только показать нужную панель полей.
  STATE.tradeScenario = s;
  const pa = document.getElementById('trade-pane-a'), pb = document.getElementById('trade-pane-b');
  if (pa) pa.style.display = (s === 'A') ? '' : 'none';
  if (pb) pb.style.display = (s === 'B') ? '' : 'none';
  if (typeof updatePult === 'function') updatePult();   // мировая цена A/Б в пульт
  redrawAll();
}

// Переключение под-режима КПВ (одна / сумма / КТВ): показ нужной панели + перерисовка.
function setPpfSub(sub) {
  cancelRangeAnim();   // отложенный переезд осей прошлого под-режима — отменить
  STATE.ppfSub = sub;
  const map = { single: 'ppfsub-single', sum: 'ppfsub-sum', trade: 'ppfsub-trade' };
  Object.values(map).forEach(id => { const b = document.getElementById(id); if (b) b.classList.remove('active'); });
  const ab = document.getElementById(map[sub]); if (ab) ab.classList.add('active');
  const panes = { single: 'ppf-pane-single', sum: 'ppf-pane-sum', trade: 'ppf-pane-trade' };
  Object.values(panes).forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; });
  const ap = document.getElementById(panes[sub]); if (ap) ap.style.display = '';
  // Пересчёт при показе больше не форсируем: кэш сам сверяет подпись входа
  // (ppfSumSignature) и пересчитывает ровно тогда, когда вход изменился.
  if (typeof updatePult === 'function') updatePult();   // сцен-слайдеры КПВ / мировая цена
  redrawAll();
}

