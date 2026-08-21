// Рынок труда: монопсония, профсоюз, МРОТ.
/* =====================================================================
   БЛОК 10б. РЫНОК ТРУДА (Чекпоинт 1) — отдельный режим mode='labor'.
   Оси: труд L (горизонталь), зарплата W (вертикаль) — drawAxes('L','W').
   Кривые: спрос на труд D = MRPL (роль demand), предложение труда S (роль supply).
   Две структуры: совершенная конкуренция и монопсония (один наниматель).
   Вся математика — численная, через те же методы (findEquilibrium / findRoot /
   findRootIn / invCurve / integrate / центральные разности).
   ===================================================================== */

// Предельные издержки на труд MCL(L) = d(W_s(L)·L)/dL, где W_s = кривая предложения.
// Численная центральная разность — как marginalRevenue, работает для любой формы S.
// Для линейного S = a + bL даёт MCL = a + 2bL (вдвое круче предложения).
function laborMCL(S, l) {
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const f = (x) => { const w = evalCurve(S, x); return isNaN(w) ? NaN : w * x; };
  const a = f(l + h), b = f(l - h);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / (2 * h);
}

// Оптимум монопсонии при МРОТ W_min: ломаные предельные издержки труда.
// Пока наниматель платит фиксированный W_min (не повышая зарплату), MCL_eff = W_min —
// горизонтальна на [0, L̂], где W_s(L̂) = W_min. Правее L̂ MCL_eff = обычный MCL.
// Оптимум — где ломаный MCL_eff встречает спрос; занятость может ВЫРАСТИ (парадокс).
// Та же механика, что у потолка цены в монополии (monopolyCeiling).
function laborMinMonopsony(Wmin) {
  const D = STATE.laborD, S = STATE.laborS, mono = STATE.laborMono;
  if (!D || !S || !mono) return null;
  const Wm = mono.Wm, Lm = mono.Lm, Lk = mono.Lk;
  const Lhat = invCurve(S, Wmin);                 // объём предложения при зарплате W_min: W_s(L̂)=W_min
  // МРОТ не выше монопсонической зарплаты (или вне области) — не связывает.
  if (Wmin <= Wm + 1e-9 || Lhat == null) {
    return { binding: false, Lstar: Lm, wage: Wm, Lhat, unemployment: 0, Wmin, dwl: mono.dwl };
  }
  // Относительная прибыль R(L) = ∫ (D − MCL_eff) dL; MCL_eff = W_min до L̂, далее обычный MCL.
  const Rel = (L) => {
    const a = Math.min(L, Lhat);
    let r = integrate(l => evalCurve(D, l) - Wmin, 0, a);
    if (L > Lhat) r += integrate(l => evalCurve(D, l) - laborMCL(S, l), Lhat, L);
    return r;
  };
  // Кандидаты: 0, точка D=W_min на плоской части, сам L̂, обычный MCL=D за изломом.
  const cands = [{ L: 0 }];
  const lflat = findRootIn(l => evalCurve(D, l) - Wmin, 0, Lhat);
  if (lflat != null) cands.push({ L: lflat });
  cands.push({ L: Lhat });
  const lbeyond = findRootIn(l => evalCurve(D, l) - laborMCL(S, l), Lhat, CONFIG.Qmax);
  if (lbeyond != null) cands.push({ L: lbeyond });
  cands.forEach(c => c.R = Rel(c.L));
  let best = cands[0];
  cands.forEach(c => { if (c.R > best.R + 1e-6 || (Math.abs(c.R - best.R) <= 1e-6 && c.L > best.L)) best = c; });
  const Lstar = best.L;
  // Зарплата: на плоской части = W_min, иначе с кривой предложения.
  const wage = (Lstar <= Lhat + 1e-9) ? Wmin : evalCurve(S, Lstar);
  // Безработица = желающие работать при W_min (L̂) минус нанятые (Lstar).
  const unemployment = Math.max(0, Lhat - Lstar);
  let dwl = null;
  if (Lk != null) { const lo = Math.min(Lstar, Lk), hi = Math.max(Lstar, Lk); dwl = areaBetween(l => evalCurve(D, l) - evalCurve(S, l), lo, hi); }
  return { binding: true, Lstar, wage, Lhat, unemployment, dwl, Wmin };
}

// МРОТ в конкуренции: при W_min выше равновесия — классическая безработица.
// Занятость = объём спроса при W_min (короткая сторона); безработица = Qs − Qd.
function laborMinCompetition(Wmin) {
  const D = STATE.laborD, S = STATE.laborS, eq = STATE.laborEq;
  if (!D || !S || !eq) return null;
  const binding = (Wmin > eq.P + 1e-9);
  const dAt0 = evalCurve(D, 0);
  let Qd = invCurve(D, Wmin);                     // спрос на труд при W_min
  /* ⚠️ «КОРНЯ НЕТ» И «ЗАНЯТОСТЬ НОЛЬ» — РАЗНЫЕ ОТВЕТЫ, А ФОРМА У НИХ БЫЛА ОДНА.
     При МРОТ выше начала кривой спроса нанимать не станут никого: занятость
     ровно 0, а безработными оказываются все, кто готов работать за эту
     зарплату. Прежде здесь оставался null, он показывался как «0» и означал
     ровно противоположное — что безработицы нет. */
  if (Qd == null && isFinite(dAt0) && Wmin > dAt0) Qd = 0;
  const sAt0 = evalCurve(S, 0);
  let Qs = invCurve(S, Wmin);                     // предложение труда при W_min
  // Зеркальный случай: предложение труда не опускается до такой зарплаты.
  if (Qs == null && isFinite(sAt0) && Wmin < sAt0) Qs = 0;
  const employment = (Qd != null) ? Qd : null;
  const unemployment = (Qd != null && Qs != null) ? Math.max(0, Qs - Qd) : null;
  return { binding, Wmin, Qd, Qs, employment, unemployment };
}

// Профсоюз как монополист труда (ЧК4) — зеркало монопсонии. Профсоюз продаёт труд
// монопольно: спрос на труд D (=MRPL) — его «спрос», предельный доход MRL ниже D;
// «предельные издержки» — кривая предложения S (резервная зарплата). Оптимум Lп:
// MRL = S. Зарплата Wп берётся с кривой спроса D в точке Lп (выше конкурентной).
function laborUnionMonopoly() {
  const D = STATE.laborD, S = STATE.laborS, eq = STATE.laborEq;
  if (!D || !S) return null;
  const Lu = findRoot(l => { const mr = marginalRevenue(D, l), s = evalCurve(S, l); return (isNaN(mr) || isNaN(s)) ? NaN : mr - s; });
  if (Lu == null || Lu <= 1e-6) return null;
  const Wu = evalCurve(D, Lu);                       // зарплата = D(Lп), НЕ MRL и НЕ S
  let dwl = null;
  if (eq) { const lo = Math.min(Lu, eq.Q), hi = Math.max(Lu, eq.Q); dwl = areaBetween(l => evalCurve(D, l) - evalCurve(S, l), lo, hi); }
  return { Lu, Wu, Lk: eq ? eq.Q : null, Wk: eq ? eq.P : null, dwl };
}

// Профсоюз диктует зарплату W выше конкурентной (ЧК4): занятость падает по кривой
// СПРОСА (Lп где D(Lп)=W), желающих работать — по предложению (Qs где S=W).
// Безработица = Qs − Lп. Это ровно ценовой пол на рынке труда.
function laborUnionWageFloor(W) {
  const D = STATE.laborD, S = STATE.laborS, eq = STATE.laborEq;
  if (!D || !S || !eq) return null;
  const binding = (W > eq.P + 1e-9);
  const Lu = invCurve(D, W);                         // занятость = D⁻¹(W) (короткая сторона)
  const Qs = invCurve(S, W);                         // желающие работать = S⁻¹(W)
  const unemployment = (Lu != null && Qs != null) ? Math.max(0, Qs - Lu) : null;
  return { binding, W, Lu, Qs, employment: Lu, unemployment, Lk: eq.Q, Wk: eq.P };
}

// Пересчёт рынка труда БЕЗ рисования — складываем результаты в STATE.
function recomputeLabor() {
  STATE.laborD = curveByRole('demand');
  STATE.laborS = curveByRole('supply');
  STATE.laborEq = STATE.laborMono = STATE.laborMin = null;
  STATE.laborWorkerCS = STATE.laborFirmCS = null;
  STATE.laborMinWelfare = null;
  STATE.laborUnion = null;
  const D = STATE.laborD, S = STATE.laborS;
  if (!D || !S) return;
  // Конкурентное равновесие D = S — считаем всегда (нужно и как ориентир монопсонии).
  const eq = findEquilibrium(D, S);
  STATE.laborEq = eq;
  if (eq) {
    STATE.laborWorkerCS = integrate(l => eq.P - evalCurve(S, l), 0, eq.Q);   // излишек рабочих (над S, под W)
    STATE.laborFirmCS = integrate(l => evalCurve(D, l) - eq.P, 0, eq.Q);     // излишек фирм (под D, над W)
  }
  // Монопсония: оптимум MCL = D, зарплата опускается на кривую предложения.
  // При двусторонней монополии (Фаза 12) она нужна как НИЖНЯЯ граница диапазона.
  if (STATE.laborStruct === 'monopsony' || STATE.laborStruct === 'bilateral') {
    const Lm = findRoot(l => laborMCL(S, l) - evalCurve(D, l));
    if (Lm != null && Lm > 0) {
      const Wm = evalCurve(S, Lm);               // зарплата = W_s(Lm) (НЕ с точки MCL=D и НЕ с D)
      let dwl = null;
      if (eq) { const lo = Math.min(Lm, eq.Q), hi = Math.max(Lm, eq.Q); dwl = areaBetween(l => evalCurve(D, l) - evalCurve(S, l), lo, hi); }
      STATE.laborMono = { Lm, Wm, Lk: eq ? eq.Q : null, Wk: eq ? eq.P : null, dwl };
    }
  }
  // Профсоюз (ЧК4): монополист труда (MRL=S) или диктат зарплаты (ценовой пол).
  if (STATE.laborStruct === 'union') {
    STATE.laborUnion = (STATE.unionModel === 'wagefloor')
      ? laborUnionWageFloor(STATE.unionWage)
      : laborUnionMonopoly();
  }
  /* Двусторонняя монополия (Фаза 12): один наниматель против одного профсоюза.
     ВАЖНО ПРО МОДЕЛЬ: единственного равновесия здесь НЕТ — исход зависит от
     переговорной силы сторон, и стандартная трактовка в учебниках именно такая.
     Поэтому считаем не «точку», а ДИАПАЗОН [Wм; Wп]: снизу — что назначил бы
     монопсонист в одиночку, сверху — чего добился бы профсоюз-монополист.
     Обе границы берём из уже проверенных функций, ничего не пересчитывая. */
  STATE.laborBilateral = null;
  if (STATE.laborStruct === 'bilateral') {
    STATE.laborUnion = laborUnionMonopoly();
    const m = STATE.laborMono, u = STATE.laborUnion;
    if (m && u) {
      const lo = Math.min(m.Wm, u.Wu), hi = Math.max(m.Wm, u.Wu);
      STATE.laborBilateral = { Wlo: lo, Whi: hi, Wm: m.Wm, Lm: m.Lm, Wu: u.Wu, Lu: u.Lu,
                               Wk: eq ? eq.P : null, Lk: eq ? eq.Q : null };
    }
  }
  // Минимальная зарплата (МРОТ).
  if (STATE.laborMinOn && STATE.laborMinW > 0 && eq) {
    STATE.laborMin = (STATE.laborStruct === 'monopsony')
      ? laborMinMonopsony(STATE.laborMinW)
      : laborMinCompetition(STATE.laborMinW);
  }
  // Благосостояние при связывающем МРОТ (Задача 3): перестраиваем под фактическое
  // состояние (занятость L*, фактическая зарплата W_факт) — единый источник чисел для
  // заливок и табло. L* и W_факт берём из уже найденного STATE.laborMin (не пересчитываем).
  if (STATE.laborMin && STATE.laborMin.binding && eq) {
    const min = STATE.laborMin;
    const Lstar = (STATE.laborStruct === 'monopsony') ? min.Lstar : min.employment;
    const Wfact = (STATE.laborStruct === 'monopsony') ? min.wage : min.Wmin;
    if (Lstar != null && Lstar > 0 && Wfact != null) {
      const workerCS = integrate(l => Wfact - evalCurve(S, l), 0, Lstar);   // над S, под W_факт, до L*
      const firmCS = integrate(l => evalCurve(D, l) - Wfact, 0, Lstar);     // под D, над W_факт, до L*
      const Lk = eq.Q, lo = Math.min(Lstar, Lk), hi = Math.max(Lstar, Lk);
      const dwl = areaBetween(l => evalCurve(D, l) - evalCurve(S, l), lo, hi);  // между D и S от L* до Lk
      STATE.laborMinWelfare = { Lstar, Wfact, workerCS, firmCS, dwl };
    }
  }
  // Авто-масштаб осей под кривые труда (Фаза 4): рамка из перехватов D/S и значимых
  // уровней зарплаты (МРОТ / профсоюз), +10% воздуха. Плавно при кручении ползунков
  // (applyAutoRanges), мгновенно на входе. Только геометрия — числа выше не меняются.
  let Lmax = invCurve(D, 0); if (!(Lmax > 0) || !isFinite(Lmax)) Lmax = CONFIG.Qmax;
  let Wmax = evalCurve(D, 0); if (!(Wmax > 0) || isNaN(Wmax)) Wmax = CONFIG.Pmax;
  const sEnd = evalCurve(S, Lmax); if (sEnd > Wmax) Wmax = sEnd;        // предложение на правом краю
  if (STATE.laborMinOn && STATE.laborMinW > Wmax) Wmax = STATE.laborMinW;
  if (STATE.laborStruct === 'union' && STATE.unionModel === 'wagefloor' && STATE.unionWage > Wmax) Wmax = STATE.unionWage;
  applyAutoRanges(padMax(Lmax), padMax(Wmax));
}

// Точка рынка труда с проекциями к осям и подписями L/W.
function laborPoint(g, L, W, color, label, opts) {
  opts = opts || {};
  const ox = sx(0), oy = sy(0), [px, py] = toPx(L, W);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(px, py, px, oy); dash(px, py, ox, py);
  /* Своя подпись сцены (opts.lText) идёт как есть: она называет не координату,
     а величину сюжета. Без неё печатается число на оси общим помощником. */
  if (opts.lText) haloText(g, px, oy + 8, opts.lText, 'middle', 'hanging');
  else if (opts.lText !== null) axisValueX(g, px, oy, L, opts.lIdx || '');
  /* Своя подпись сцены идёт как есть; без неё — число на оси общим помощником. */
  if (opts.wText) yWageLabel(g, ox, py, opts.wText);
  else if (opts.wText !== null) yWageValue(g, ox, py, W, opts.wIdx || '');
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5).attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  pointName(g, px, py, label, color);
}

// Бледный конкурентный ориентир (Lk, Wk) — точка «К» (по галочке «было → стало»).
function drawLaborGhost(L, W, label) {
  if (!STATE.showGhost || L == null || W == null) return;
  const oy = sy(0), g = svg.append('g'), [px, py] = toPx(L, W);
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
  g.append('text').attr('x', px + 7).attr('y', py + 13).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label || 'К');
  axisValueX(g, px, oy, fmt(L), 'k');
}

// Заливки излишков в конкуренции: излишек рабочих (над S, под W) и фирм (под D, над W).
function drawLaborSurpluses() {
  const eq = STATE.laborEq; if (!eq || eq.Q <= 0) return;
  const D = STATE.laborD, S = STATE.laborS, W = eq.P;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = []; for (let i = 0; i <= 100; i++) samp.push(eq.Q * i / 100);
  // Излишек рабочих — между предложением (низ) и зарплатой W (верх).
  const wA = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(S, d))).y1(sy(W));
  g.append('path').datum(samp).attr('d', wA).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек работников');
  // Излишек фирм — между зарплатой W (низ) и спросом D=MRPL (верх).
  const fA = d3.area().x(d => sx(d)).y0(sy(W)).y1(d => sy(evalCurve(D, d)));
  g.append('path').datum(samp).attr('d', fA).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек фирм');
}

// Благосостояние при связывающем МРОТ (Задача 3): перестроенные излишки + DWL.
// Те же цвета/стиль, что без МРОТ; границы по L* и W_факт из STATE.laborMinWelfare
// (стыкуются без зазоров). Работает в обеих структурах (конкуренция и монопсония).
function drawLaborMinWelfare() {
  const wf = STATE.laborMinWelfare, eq = STATE.laborEq;
  if (!wf || !eq) return;
  const D = STATE.laborD, S = STATE.laborS, Lstar = wf.Lstar, Wfact = wf.Wfact;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const s1 = samp(0, Lstar);
  // Излишек рабочих — между предложением S (низ) и фактической зарплатой (верх), до L*.
  const wA = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(S, d))).y1(sy(Wfact));
  g.append('path').datum(s1).attr('d', wA).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек работников');
  // Излишек фирм — между фактической зарплатой (низ) и спросом D (верх), до L*.
  const fA = d3.area().x(d => sx(d)).y0(sy(Wfact)).y1(d => sy(evalCurve(D, d)));
  g.append('path').datum(s1).attr('d', fA).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек фирм');
  // DWL — между D и S от L* до конкурентной занятости Lk (недозанятость/безработица).
  const Lk = eq.Q, lo = Math.min(Lstar, Lk), hi = Math.max(Lstar, Lk);
  if (hi > lo) {
    const s2 = samp(lo, hi);
    const dA = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(S, d))).y1(d => sy(evalCurve(D, d)));
    g.append('path').datum(s2).attr('d', dA).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
  }
}

// Кривая MCL монопсонии (оранжевый пунктир). При связывающем МРОТ — ломаная MCL_eff.
// Предельные издержки труда. Разводим два объекта (Задача 2):
//  1) НАСТОЯЩАЯ MCL = d(W_s·L)/dL — объективная кривая рынка, от МРОТ НЕ зависит.
//     Рисуем её ЦЕЛИКОМ всегда (амбер-пунктир #f59e0b) — и без МРОТ, и с МРОТ.
//  2) ЭФФЕКТИВНАЯ ломаная MCL_eff (полка W_min до L̂, дальше = настоящая MCL) — ПОВЕРХ
//     настоящей, отдельным видом (тёмно-оранжевый #c2410c, сплошной, потолще). Это
//     вспомогательная линия выбора равновесия; математику выбора НЕ меняем.
function drawLaborMCL() {
  const S = STATE.laborD ? STATE.laborS : null; if (!S) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  // (1) Настоящая MCL — всегда во всю длину.
  const ptsFull = []; for (let i = 0; i <= 400; i++) { const l = CONFIG.Qmax * i / 400; const v = laborMCL(S, l); ptsFull.push(isNaN(v) ? null : [l, v]); }
  g.append('path').datum(ptsFull).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
  const ql = CONFIG.Qmax * 0.85, vl = laborMCL(S, ql);
  if (!isNaN(vl) && vl <= CONFIG.Pmax) g.append('text').attr('x', sx(ql)).attr('y', sy(vl) - 4).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.reg)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('MCL');
  // (2) Эффективная ломаная MCL_eff — поверх настоящей, при связывающем МРОТ.
  const min = STATE.laborMin;
  if (min && min.binding && min.Lhat != null) {
    const yW = sy(min.Wmin);
    // Полка W_min до L̂ (сплошная, тёмно-оранжевая, потолще).
    g.append('line').attr('x1', sx(0)).attr('y1', yW).attr('x2', sx(min.Lhat)).attr('y2', yW)
      .attr('stroke', COL.warn).attr('stroke-width', 3.5);
    // Дальше L̂ MCL_eff совпадает с настоящей MCL — подчёркиваем сплошной поверх пунктира.
    const ptsBeyond = []; for (let i = 0; i <= 400; i++) { const l = CONFIG.Qmax * i / 400; if (l < min.Lhat) { ptsBeyond.push(null); continue; } const v = laborMCL(S, l); ptsBeyond.push(isNaN(v) ? null : [l, v]); }
    g.append('path').datum(ptsBeyond).attr('fill', 'none').attr('stroke', COL.warn).attr('stroke-width', 3).attr('d', line);
    // Вертикальный скачок в L̂ от W_min к настоящей MCL.
    const mclHat = laborMCL(S, min.Lhat);
    if (!isNaN(mclHat)) g.append('line').attr('x1', sx(min.Lhat)).attr('y1', yW).attr('x2', sx(min.Lhat)).attr('y2', sy(mclHat))
      .attr('stroke', COL.warn).attr('stroke-width', 2).attr('stroke-dasharray', '3 2').attr('opacity', 0.7);
    g.append('text').attr('x', sx(min.Lhat * 0.4)).attr('y', yW - 5).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.warn)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('MCLэфф');
  }
}

// DWL монопсонии (между D и S от Lm до Lk) — недозанятость.
function drawLaborDWL(Lfrom) {
  const mono = STATE.laborMono; if (!mono || mono.Lk == null) return;
  const Lm = (Lfrom != null) ? Lfrom : mono.Lm;
  const D = STATE.laborD, S = STATE.laborS;
  const lo = Math.min(Lm, mono.Lk), hi = Math.max(Lm, mono.Lk);
  if (hi <= lo) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = []; for (let i = 0; i <= 100; i++) samp.push(lo + (hi - lo) * i / 100);
  const a = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(S, d))).y1(d => sy(evalCurve(D, d)));
  g.append('path').datum(samp).attr('d', a).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
}

// Точки монопсонии: оптимум на MCL=D, зарплата вниз на S, ориентир «К».
function drawLaborMonopsonyPoints() {
  const mono = STATE.laborMono; if (!mono) return;
  const min = STATE.laborMin, bind = (min && min.binding);
  // Бледный конкурентный ориентир.
  drawLaborGhost(mono.Lk, mono.Wk, 'К');
  const g = svg.append('g');
  const ox = sx(0), oy = sy(0);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  if (bind) {
    // Призрак исходной монопсонии M₀(Lm, Wm).
    if (STATE.showGhost) {
      const [px0, py0] = toPx(mono.Lm, mono.Wm);
      g.append('circle').attr('cx', px0).attr('cy', py0).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
      g.append('text').attr('x', px0 + 7).attr('y', py0 - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('M₀');
    }
    // Новый оптимум при МРОТ.
    /* ⚠️ ДВЕ ПОДПИСИ ОДНОГО ЧИСЛА У ОДНОЙ ТОЧКИ — ЭТО НЕ НАЛОЖЕНИЕ, А ПОВТОР
       (п. 34, последний случай). Когда МРОТ поставлен ровно на зарплату
       монопсониста, у оси печаталось «W=65» поверх «Wmin=65»: развести их
       нельзя, потому что они об одном и том же. Говорит тот, кто объясняет
       БОЛЬШЕ: линия МРОТ названа человеком, а зарплата в этой точке ей и
       равна. Само число не пропадает ни в каком случае. */
    if (min.Lstar > 1e-6) {
      const sameAsMin = STATE.laborMinOn && STATE.laborMinW > 0
                        && fmt(min.wage) === fmt(STATE.laborMinW);
      laborPoint(g, min.Lstar, min.wage, COL.ink, 'M',
                 { wText: sameAsMin ? null : undefined });
    }
    // Безработица на оси L между Lstar и L̂ (желающие при W_min).
    if (min.unemployment > 1e-6) {
      const xLo = sx(Math.min(min.Lstar, min.Lhat)), xHi = sx(Math.max(min.Lstar, min.Lhat));
      g.append('line').attr('x1', xLo).attr('y1', oy).attr('x2', xHi).attr('y2', oy).attr('stroke', COL.bad).attr('stroke-width', 5).attr('opacity', 0.5);
      haloText(g, (xLo + xHi) / 2, oy + 24, 'Безработица = ' + fmt(min.unemployment), 'middle', 'hanging');
    }
  } else {
    // Точка пересечения MCL = D (на уровне MCL).
    const mclY = laborMCL(STATE.laborS, mono.Lm);
    const [pxm, pyMcl] = toPx(mono.Lm, mclY);
    const [, pyW] = toPx(mono.Lm, mono.Wm);
    // Вертикаль Lm: от MCL=D вниз до зарплаты на предложении.
    g.append('line').attr('x1', pxm).attr('y1', pyMcl).attr('x2', pxm).attr('y2', oy)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    // Точка MCL=D (оранжевая) на вертикали.
    g.append('circle').attr('cx', pxm).attr('cy', pyMcl).attr('r', 3.5).attr('fill', COL.reg).attr('stroke', COL.halo).attr('stroke-width', 1.2);
    // Зарплата опускается вертикально на кривую предложения: точка M(Lm, Wm).
    dash(ox, pyW, pxm, pyW);
    g.append('circle').attr('cx', pxm).attr('cy', pyW).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, pxm, pyW, 'M', COL.ink);
    axisValueX(g, pxm, oy, fmt(mono.Lm), 'м');
    yWageValue(g, ox, pyW, mono.Wm, 'м');
  }
}

// Точки конкуренции: равновесие (Lk, Wk) или результат связывающего МРОТ.
function drawLaborCompPoints() {
  const eq = STATE.laborEq; if (!eq) return;
  const min = STATE.laborMin, bind = (min && min.binding);
  const g = svg.append('g'), ox = sx(0), oy = sy(0);
  if (bind) {
    // Конкурентное равновесие как бледный ориентир.
    drawLaborGhost(eq.Q, eq.P, 'E₀');
    // Линия W_min рисуется отдельно (drawLaborMinLine). Здесь — занятость и безработица.
    const xQd = sx(min.Qd), xQs = sx(min.Qs), yW = sy(min.Wmin);
    const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    dash(xQd, yW, xQd, oy); dash(xQs, yW, xQs, oy);
    axisValueX(g, xQd, oy, fmt(min.Qd), 'спрос');
    axisValueX(g, xQs, oy, fmt(min.Qs), 'предл');
    // Безработица — полоса между Qd и Qs на оси L.
    const xLo = Math.min(xQd, xQs), xHi = Math.max(xQd, xQs);
    g.append('line').attr('x1', xLo).attr('y1', oy).attr('x2', xHi).attr('y2', oy).attr('stroke', COL.bad).attr('stroke-width', 5).attr('opacity', 0.5);
    if (Number.isFinite(min.unemployment)) haloText(g, (xLo + xHi) / 2, oy + 24, 'Безработица = ' + fmt(min.unemployment), 'middle', 'hanging');
    // Точка занятости (короткая сторона) на линии W_min.
    g.append('circle').attr('cx', xQd).attr('cy', yW).attr('r', 4).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  } else {
    laborPoint(g, eq.Q, eq.P, COL.ink, 'E*', { lIdx: 'k', wIdx: 'k' });
  }
}

// Перетаскиваемая линия МРОТ (как линия потолка цены).
function drawLaborMinLine() {
  if (!STATE.laborMinOn || !(STATE.laborMinW > 0)) return;
  const ox = sx(0), xMax = sx(CONFIG.Qmax), yW = sy(STATE.laborMinW);
  const g = svg.append('g');
  g.append('line').attr('x1', ox).attr('y1', yW).attr('x2', xMax).attr('y2', yW)
    .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueY(g, ox, yW, fmt(STATE.laborMinW), 'min');
  const hit = g.append('rect').attr('x', ox).attr('y', yW - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  attachLaborMinDrag(hit);
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.6).attr('cy', yW).attr('r', 7)
    .attr('fill', COL.reg).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

function attachLaborMinDrag(sel) {
  sel.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => { setLaborMin(sy.invert(event.y)); })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Записать уровень МРОТ в поля панели (без перерисовки).
function setLaborMinFields(p) {
  STATE.laborMinW = p;
  const s = document.getElementById('labmin-slider'); if (s) s.value = p;
  const l = document.getElementById('labmin-val'); if (l) l.textContent = fmt(p);
  const i = document.getElementById('labmin-input'); if (i) i.value = fmtInput(p);
}
// Единый путь смены МРОТ (ползунок, поле, перетаскивание).
function setLaborMin(p) {
  const s = document.getElementById('labmin-slider');
  const maxP = s ? (parseFloat(s.max) || CONFIG.Pmax) : CONFIG.Pmax;
  p = Math.max(0, Math.min(p, maxP));
  setLaborMinFields(p);
  if (STATE.mode === 'labor') _wantRangeAnim = true;   // плавный масштаб, если МРОТ двинул рамку
  redrawAll();
}

/* --- Профсоюз (ЧК4): отрисовка MRL, точек, безработицы, DWL --- */

// Кривая предельного дохода профсоюза MRL (фиолетовый пунктир, ниже спроса D).
function drawLaborUnionMRL() {
  const D = STATE.laborD; if (!D) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const pts = []; for (let i = 0; i <= 400; i++) { const l = CONFIG.Qmax * i / 400; const v = marginalRevenue(D, l); pts.push(isNaN(v) ? null : [l, v]); }
  g.append('path').datum(pts).attr('fill', 'none').attr('stroke', COL.MR).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
  const ql = CONFIG.Qmax * 0.28, vl = marginalRevenue(D, ql);
  if (!isNaN(vl) && vl >= 0 && vl <= CONFIG.Pmax) g.append('text').attr('x', sx(ql)).attr('y', sy(vl) - 4).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.MR)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('MRL');
}

// Серая область DWL между D и S на отрезке [La, Lb] (потери от профсоюза).
function drawLaborGapDWL(La, Lb) {
  const D = STATE.laborD, S = STATE.laborS; if (!D || !S || La == null || Lb == null) return;
  const lo = Math.min(La, Lb), hi = Math.max(La, Lb); if (hi <= lo) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = []; for (let i = 0; i <= 100; i++) samp.push(lo + (hi - lo) * i / 100);
  const a = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(S, d))).y1(d => sy(evalCurve(D, d)));
  g.append('path').datum(samp).attr('d', a).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
}

// Точки профсоюза: оптимум монополиста (MRL=S, зарплата вверх на D) или диктат зарплаты.
function drawLaborUnionPoints() {
  const u = STATE.laborUnion; if (!u) return;
  drawLaborGhost(u.Lk, u.Wk, 'К');                 // конкурентный ориентир
  const g = svg.append('g'), ox = sx(0), oy = sy(0);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  if (STATE.unionModel === 'monopoly') {
    const S = STATE.laborS, sAt = evalCurve(S, u.Lu);
    const [px, pyW] = toPx(u.Lu, u.Wu), [, pyS] = toPx(u.Lu, sAt);
    // Вертикаль Lп: от оси вверх до зарплаты Wп на спросе.
    g.append('line').attr('x1', px).attr('y1', oy).attr('x2', px).attr('y2', pyW).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    // Точка MRL=S (фиолетовая) на уровне предложения.
    g.append('circle').attr('cx', px).attr('cy', pyS).attr('r', 3.5).attr('fill', COL.MR).attr('stroke', COL.halo).attr('stroke-width', 1.2);
    // Зарплата профсоюза Wп на кривой спроса (выше конкурентной).
    dash(ox, pyW, px, pyW);
    g.append('circle').attr('cx', px).attr('cy', pyW).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, px, pyW, 'E′', COL.ink);
    axisValueX(g, px, oy, fmt(u.Lu), 'п');
    yWageValue(g, ox, pyW, u.Wu, 'п');
  } else if (u.binding) {
    // Диктат зарплаты (ценовой пол): занятость по спросу, безработица до предложения.
    const yW = sy(u.W), xL = sx(u.Lu), xQs = sx(u.Qs);
    dash(xL, yW, xL, oy); dash(xQs, yW, xQs, oy);
    axisValueX(g, xL, oy, fmt(u.Lu), 'п');
    axisValueX(g, xQs, oy, fmt(u.Qs), 'предл');
    const xLo = Math.min(xL, xQs), xHi = Math.max(xL, xQs);
    g.append('line').attr('x1', xLo).attr('y1', oy).attr('x2', xHi).attr('y2', oy).attr('stroke', COL.bad).attr('stroke-width', 5).attr('opacity', 0.5);
    if (u.unemployment > 1e-6) haloText(g, (xLo + xHi) / 2, oy + 24, 'Безработица = ' + fmt(u.unemployment), 'middle', 'hanging');
    g.append('circle').attr('cx', xL).attr('cy', yW).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, xL, yW, 'E′', COL.ink);
  }
}

// Перетаскиваемая линия зарплаты профсоюза (диктат) — как линия МРОТ.
function drawLaborUnionWageLine() {
  if (!(STATE.unionWage > 0)) return;
  const ox = sx(0), xMax = sx(CONFIG.Qmax), yW = sy(STATE.unionWage);
  const g = svg.append('g');
  g.append('line').attr('x1', ox).attr('y1', yW).attr('x2', xMax).attr('y2', yW)
    .attr('stroke', COL.MC).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueY(g, ox, yW, fmt(STATE.unionWage), 'п');
  const hit = g.append('rect').attr('x', ox).attr('y', yW - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  attachUnionWageDrag(hit);
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.6).attr('cy', yW).attr('r', 7)
    .attr('fill', COL.MC).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

function attachUnionWageDrag(sel) {
  sel.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => { setUnionWage(sy.invert(event.y)); })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Записать уровень зарплаты профсоюза в поля панели (без перерисовки).
function setUnionWageFields(p) {
  STATE.unionWage = p;
  const s = document.getElementById('union-wage-slider'); if (s) s.value = p;
  const l = document.getElementById('union-wage-val'); if (l) l.textContent = fmt(p);
  const i = document.getElementById('union-wage-input'); if (i) i.value = fmtInput(p);
}
// Единый путь смены зарплаты профсоюза (ползунок, поле, перетаскивание).
function setUnionWage(p) {
  const s = document.getElementById('union-wage-slider');
  const maxP = s ? (parseFloat(s.max) || CONFIG.Pmax) : CONFIG.Pmax;
  p = Math.max(0, Math.min(p, maxP));
  setUnionWageFields(p);
  if (STATE.mode === 'labor') _wantRangeAnim = true;   // плавный масштаб, если зарплата двинула рамку
  redrawAll();
}

// Переключатель модели профсоюза: монополист / диктат зарплаты (ЧК4).
function setUnionModel(model) {
  STATE.unionModel = model;
  const a = document.getElementById('un-monopoly'), b = document.getElementById('un-wagefloor');
  if (a) a.classList.toggle('active', model === 'monopoly');
  if (b) b.classList.toggle('active', model === 'wagefloor');
  const wf = document.getElementById('union-wage-field'); if (wf) wf.style.display = (model === 'wagefloor') ? '' : 'none';
  const hm = document.getElementById('un-hint-mono'); if (hm) hm.style.display = (model === 'monopoly') ? '' : 'none';
  // Первый вход в диктат — поставить зарплату-ориентир чуть выше конкурентной.
  if (model === 'wagefloor' && !(STATE.unionWage > 0) && STATE.laborEq) setUnionWageFields(Math.round(STATE.laborEq.P * 1.3));
  if (typeof updatePult === 'function') updatePult();   // поле зарплаты при «диктате» в пульт
  redrawAll();
}

/* --- Фаза 12. Двусторонняя монополия: полоса возможных исходов ----------- */

// Закрашенная горизонтальная полоса между Wм и Wп + обе граничные точки.
// Одной «правильной» точки внутри полосы модель не даёт — так и подписываем.
function drawLaborBilateral() {
  const b = STATE.laborBilateral; if (!b) return;
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax);
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const yLo = sy(b.Wlo), yHi = sy(b.Whi);
  g.append('rect').attr('x', ox).attr('y', yHi).attr('width', xMax - ox).attr('height', Math.abs(yLo - yHi))
    .attr('fill', COL.reg).attr('opacity', 0.16).attr('data-legend', 'Диапазон возможных зарплат');
  g.append('line').attr('x1', ox).attr('y1', yLo).attr('x2', xMax).attr('y2', yLo)
    .attr('stroke', COL.reg).attr('stroke-width', 1.8).attr('stroke-dasharray', '6 4');
  g.append('line').attr('x1', ox).attr('y1', yHi).attr('x2', xMax).attr('y2', yHi)
    .attr('stroke', COL.reg).attr('stroke-width', 1.8).attr('stroke-dasharray', '6 4');
  const gg = svg.append('g');
  axisValueY(gg, ox, yLo, fmt(b.Wm), 'м');
  axisValueY(gg, ox, yHi, fmt(b.Wu), 'п');
  gg.append('text').attr('x', (ox + xMax) / 2).attr('y', (yLo + yHi) / 2)
    .attr('text-anchor', 'middle').attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.warn)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 3)
    .text('Диапазон возможных исходов');
  gg.append('text').attr('x', (ox + xMax) / 2).attr('y', (yLo + yHi) / 2 + 15)
    .attr('text-anchor', 'middle').attr('font-size', FS.small).attr('fill', COL.inkSoft)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 3)
    .text('Конкретная точка зависит от переговорной силы, а её модель не определяет');
  // Две граничные точки: решение монопсониста и решение профсоюза.
  laborPoint(gg, b.Lm, b.Wm, COL.S, 'M', { lIdx: 'м', wText: null });
  laborPoint(gg, b.Lu, b.Wu, COL.MR, 'E′', { lIdx: 'п', wText: null });
}

// Табло двусторонней монополии.
function updateLaborBilateralPanel() {
  const b = STATE.laborBilateral;
  if (!b) return '<div class="warn">Не удалось найти обе границы: нужны спрос на труд (D) и предложение (S).</div>';
  let html = '';
  html += `<div class="stat"><span>Нижняя граница Wм (монопсония)</span><b>${fmt(b.Wm)}</b></div>`;
  html += `<div class="stat"><span>Верхняя граница Wп (профсоюз)</span><b>${fmt(b.Wu)}</b></div>`;
  html += `<div class="stat"><span>Диапазон зарплаты</span><b>${fmt(b.Wlo)} … ${fmt(b.Whi)}</b></div>`;
  if (b.Wk != null) html += `<div class="stat"><span>Конкурентный ориентир Wk</span><b>${fmt(b.Wk)}</b></div>`;
  html += `<div class="stat"><span>Занятость на границах</span><b>${fmt(b.Lm)} и ${fmt(b.Lu)}</b></div>`;
  html += '<div class="hint" style="margin-top:6px;">Один наниматель против одного профсоюза. У этой модели ' +
    '<b>нет единственного равновесия</b>: если бы монопсонист диктовал условия один, зарплата упала бы до Wм; ' +
    'если бы диктовал профсоюз, поднялась бы до Wп. Реальный исход лежит между и зависит от переговорной силы ' +
    'сторон, которую модель не описывает. Показывать здесь одно «точное» число было бы ложной точностью, ' +
    'поэтому показан диапазон.</div>';
  return html;
}

// Переключатель структуры рынка труда (конкуренция / монопсония / профсоюз).
function setLaborStruct(mode) {
  STATE.laborStruct = mode;
  [['lab-comp', 'competition'], ['lab-mono', 'monopsony'], ['lab-union', 'union'], ['lab-bilat', 'bilateral']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === mode); });
  // Панель профсоюза видна только при структуре «Профсоюз»; МРОТ — только там, где он осмыслен
  // (в двусторонней монополии показывается диапазон, поверх него МРОТ только запутал бы).
  const up = document.getElementById('union-pane'); if (up) up.style.display = (mode === 'union') ? '' : 'none';
  const lb = document.getElementById('labmin-block');
  if (lb) lb.style.display = (mode === 'union' || mode === 'bilateral') ? 'none' : '';
  if (mode === 'union') setUnionModel(STATE.unionModel);   // синхронизировать под-модель/поля
  if (typeof updatePult === 'function') updatePult();   // зарплата профсоюза / МРОТ в пульт
  redrawAll();
}

// Табло рынка труда.
function updateLaborPanel() {
  const box = document.getElementById('info-labor'); if (!box) return;
  if (!STATE.laborD || !STATE.laborS) {
    box.innerHTML = '<div class="muted">Отметьте одну кривую как D&nbsp;(спрос на труд, MRPL), другую как S&nbsp;(предложение труда).</div>';
    return;
  }
  if (!STATE.laborEq) { box.innerHTML = '<div class="warn">Равновесие рынка труда не найдено в первой четверти.</div>'; return; }
  const min = STATE.laborMin, bind = (min && min.binding);
  let html = '';
  if (STATE.laborStruct === 'bilateral') {   // Фаза 12 — диапазон, а не точка
    box.innerHTML = updateLaborBilateralPanel();
    return;
  }
  if (STATE.laborStruct === 'union') {
    const u = STATE.laborUnion;
    if (!u) { box.innerHTML = '<div class="warn">Оптимум профсоюза не найден.</div>'; return; }
    if (STATE.unionModel === 'monopoly') {
      html += `<div class="stat"><span>$L_п$ (занятость)</span><b>${fmt(u.Lu)}</b></div>`;
      html += `<div class="stat"><span>$W_п$ (зарплата)</span><b>${fmt(u.Wu)}</b></div>`;
      if (u.Lk != null) html += `<div class="stat"><span>$L_k$ (конкуренция)</span><b>${fmt(u.Lk)}</b></div>`;
      if (u.Wk != null) html += `<div class="stat"><span>$W_k$ (конкуренция)</span><b>${fmt(u.Wk)}</b></div>`;
      if (u.dwl != null) html += `<div class="stat"><span>$DWL$ (недозанятость)</span><b>${fmt(u.dwl)}</b></div>`;
      html += '<div class="hint">Профсоюз-монополист продаёт труд там, где MRL&nbsp;=&nbsp;S, и берёт зарплату Wп с кривой спроса, ВЫШЕ конкурентной, но занятость НИЖЕ. Зеркало монопсонии. Серым закрашены потери общества.</div>';
    } else {
      html += `<div class="stat"><span>Зарплата профсоюза Wп</span><b>${fmt(u.W)}</b></div>`;
      if (u.binding) {
        html += `<div class="stat"><span>Занятость Lп</span><b>${fmt(u.Lu)} (было ${fmt(u.Lk)})</b></div>`;
        html += `<div class="stat"><span>Желающих работать</span><b>${fmt(u.Qs)}</b></div>`;
        if (u.unemployment > 1e-6) html += `<div class="stat"><span>Безработица</span><b>${fmt(u.unemployment)}</b></div>`;
        html += '<div class="hint">Профсоюз диктует зарплату выше равновесия: занятость падает по спросу, возникает безработица (ценовой пол на рынке труда).</div>';
      } else {
        html += `<div class="stat"><span>$L_k$ (конкуренция)</span><b>${fmt(u.Lk)}</b></div>`;
        html += '<div class="hint" style="margin-top:6px;">Зарплата профсоюза не выше конкурентной, поэтому не связывает. Рынок в равновесии.</div>';
      }
    }
    box.innerHTML = html;
    return;
  }
  if (STATE.laborStruct === 'monopsony') {
    const m = STATE.laborMono;
    if (!m) { box.innerHTML = '<div class="warn">Оптимум монопсонии (MCL = D) не найден.</div>'; return; }
    html += `<div class="stat"><span>$L_м$ (занятость)</span><b>${fmt(m.Lm)}</b></div>`;
    html += `<div class="stat"><span>$W_м$ (зарплата)</span><b>${fmt(m.Wm)}</b></div>`;
    if (m.Lk != null) html += `<div class="stat"><span>$L_k$ (конкуренция)</span><b>${fmt(m.Lk)}</b></div>`;
    if (m.Wk != null) html += `<div class="stat"><span>$W_k$ (конкуренция)</span><b>${fmt(m.Wk)}</b></div>`;
    if (m.dwl != null) html += `<div class="stat"><span>$DWL$ (недозанятость)</span><b>${fmt(m.dwl)}</b></div>`;
    html += `<div class="hint">Монопсония занижает и занятость, и зарплату против конкуренции: рабочим платят Wм&nbsp;=&nbsp;W_s(Lм), ниже их предельного продукта. Серым закрашены потери общества.</div>`;
    if (bind) {
      html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
      html += `<div class="stat"><span>МРОТ W_min</span><b>${fmt(min.Wmin)}</b></div>`;
      html += `<div class="stat"><span>Занятость с МРОТ</span><b>${fmt(min.Lstar)} (было ${fmt(m.Lm)})</b></div>`;
      html += `<div class="stat"><span>Зарплата</span><b>${fmt(min.wage)}</b></div>`;
      if (min.unemployment > 1e-6) html += `<div class="stat"><span>Безработица</span><b>${fmt(min.unemployment)}</b></div>`;
      const w = STATE.laborMinWelfare;
      if (w) {
        html += `<div class="stat"><span>Излишек рабочих</span><b>${fmt(w.workerCS)}</b></div>`;
        html += `<div class="stat"><span>Излишек фирм</span><b>${fmt(w.firmCS)}</b></div>`;
        html += `<div class="stat"><span>$DWL$ (потери)</span><b>${fmt(w.dwl)}</b></div>`;
      }
      const dl = min.Lstar - m.Lm;
      html += `<div class="hint">${dl > 1e-6 ? 'МРОТ увеличил занятость (парадокс монопсонии).' : (dl < -1e-6 ? 'МРОТ снизил занятость.' : 'Занятость не изменилась.')}</div>`;
    } else if (STATE.laborMinOn && STATE.laborMinW > 0) {
      html += '<div class="hint" style="margin-top:6px;">МРОТ не выше монопсонической зарплаты, поэтому не связывает.</div>';
    }
  } else {
    const eq = STATE.laborEq;
    html += `<div class="stat"><span>$L_k$ (занятость)</span><b>${fmt(eq.Q)}</b></div>`;
    html += `<div class="stat"><span>$W_k$ (зарплата)</span><b>${fmt(eq.P)}</b></div>`;
    if (STATE.laborWorkerCS != null) html += `<div class="stat"><span>Излишек рабочих</span><b>${fmt(STATE.laborWorkerCS)}</b></div>`;
    if (STATE.laborFirmCS != null) html += `<div class="stat"><span>Излишек фирм</span><b>${fmt(STATE.laborFirmCS)}</b></div>`;
    if (bind) {
      html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
      html += `<div class="stat"><span>МРОТ W_min</span><b>${fmt(min.Wmin)}</b></div>`;
      html += `<div class="stat"><span>Занятость</span><b>${fmt(min.employment)} (было ${fmt(eq.Q)})</b></div>`;
      if (min.unemployment > 1e-6) html += `<div class="stat"><span>Безработица</span><b>${fmt(min.unemployment)}</b></div>`;
      const w = STATE.laborMinWelfare;
      if (w) {
        html += `<div class="stat"><span>Излишек рабочих</span><b>${fmt(w.workerCS)}</b></div>`;
        html += `<div class="stat"><span>Излишек фирм</span><b>${fmt(w.firmCS)}</b></div>`;
        html += `<div class="stat"><span>$DWL$ (потери)</span><b>${fmt(w.dwl)}</b></div>`;
      }
      html += `<div class="hint">МРОТ выше равновесия: занятость падает до спроса при W_min, возникает безработица (избыток предложения труда).</div>`;
    } else if (STATE.laborMinOn && STATE.laborMinW > 0) {
      html += '<div class="hint" style="margin-top:6px;">МРОТ ниже равновесия, поэтому не связывает. Рынок в равновесии.</div>';
    }
  }
  box.innerHTML = html;
}

// Полная перерисовка режима рынка труда.
function redrawLabor() {
  recomputeLabor();
  makeScales();   // recomputeLabor мог изменить масштаб (авто-рамка) — пересчитать шкалы
  svg.selectAll('*').remove();
  addDefs();
  drawGrid();
  drawAxes('L', 'W');
  const minBind = (STATE.laborMin && STATE.laborMin.binding);
  if (STATE.laborStruct === 'bilateral') {
    // Фаза 12: обе «крайние» кривые сразу — MCL нанимателя и MRL профсоюза + полоса исходов.
    drawLaborBilateral();
    drawCurves();
    drawLaborMCL();
    drawLaborUnionMRL();
    drawLaborGhost(STATE.laborBilateral ? STATE.laborBilateral.Lk : null,
                   STATE.laborBilateral ? STATE.laborBilateral.Wk : null, 'К');
  } else if (STATE.laborStruct === 'union') {
    // Профсоюз (ЧК4): потери от ограничения труда + кривые + (для монополиста) MRL + точки.
    const u = STATE.laborUnion;
    if (u && (STATE.unionModel === 'monopoly' || u.binding)) drawLaborGapDWL(u.Lu, u.Lk);
    drawCurves();
    if (STATE.unionModel === 'monopoly') drawLaborUnionMRL();
    drawLaborUnionPoints();
    if (STATE.unionModel === 'wagefloor') drawLaborUnionWageLine();
  } else if (STATE.laborStruct === 'monopsony') {
    if (minBind) drawLaborMinWelfare();   // перестроенные излишки + DWL под МРОТ (Задача 3)
    else drawLaborDWL();                  // потери монопсонии (между D и S от Lm до Lk)
    drawCurves();               // спрос на труд D и предложение S (с перетаскиванием прямых)
    drawLaborMCL();             // настоящая MCL целиком + эффективная ломаная при МРОТ
    drawLaborMonopsonyPoints(); // оптимум, зарплата, ориентир, безработица
  } else {
    if (minBind) drawLaborMinWelfare();   // перестроенные излишки + DWL под МРОТ (Задача 3)
    else drawLaborSurpluses();            // излишки рабочих/фирм в равновесии
    drawCurves();
    drawLaborCompPoints();      // равновесие или занятость/безработица при МРОТ
  }
  if (STATE.laborMinOn && STATE.laborStruct !== 'union') drawLaborMinLine();
  updateLaborPanel();
}

