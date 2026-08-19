// Макроэкономика: AD-AS, Филлипс, деньги, IS-LM, Лаффер.
/* =====================================================================
   БЛОК 10г. МАКРОЭКОНОМИКА (Фазы 16–22) — режим mode='macro'.

   Семь моделей живут в одном режиме, потому что устроены одинаково:
   две кривые на СВОИХ осях, пересечение, числа в табло. Отличаются только
   подписи осей, форма ввода и «сверх-логика» (разрыв выпуска, вытеснение,
   ломаная Лаффера). Общая часть — один код, специфика — в реестре MACRO.

   Форма ввода различается по модели и подписана явно:
     y = f(x)  — AD/AS/SRAS, кривая Филлипса, IS/LM (цена от количества);
     x = g(y)  — денежный рынок, заёмные средства, валютный рынок
                 (количество от ставки/курса — как их и записывают в задачах).
     Второй случай приводится к первому тем же обращением, что ввод Q(P)
     в Фазе 1б: линейная — явно, любая другая — численно бисекцией.
   Вертикальные кривые (LRAS, долгосрочная Филлипса, Ms) — тип из Фазы 15.
   ===================================================================== */

// Компиляция выражения с ИМЕНЕМ переменной модели (Y, u, i, r, e, Q) + синоним x.
function compileVar(expr, names) {
  try {
    const compiled = math.parse(prepExpr(expr)).compile();
    const ctx = paramScope({ x: 1 }); names.forEach(n => { ctx[n] = 1; });
    // Буква, у которой ползунка ещё нет, на пробе считается единицей: это будущий
    // параметр, а не опечатка.
    if (paramsAllowed()) freeSymbols(expr).forEach(n => { if (ctx[n] === undefined) ctx[n] = 1; });
    compiled.evaluate(ctx);
    return { compiled, error: null };
  } catch (e) { return { compiled: null, error: e.message }; }
}
function evalVar(compiled, v, names) {
  try {
    const ctx = paramScope({ x: v }); names.forEach(n => { ctx[n] = v; });
    const r = compiled.evaluate(ctx);
    return (typeof r === 'number' && isFinite(r)) ? r : NaN;
  } catch (e) { return NaN; }
}

// Кривая, заданная как y = f(x) — прямо в каноне движка.
function macroCurveY(expr, names) {
  const { compiled, error } = compileVar(expr, names);
  if (error) return { error };
  return { fn: (v) => evalVar(compiled, v, names) };
}

// Кривая, заданная как x = g(y) («количество от ставки»). Приводим к y = f(x):
// линейную — явной формулой, любую другую — численным обращением (та же идея,
// что invertQofP в Фазе 1б).
function macroCurveInv(expr, names, yMax) {
  const { compiled, error } = compileVar(expr, names);
  if (error) return { error };
  const g = (y) => evalVar(compiled, y, names);
  const y1 = yMax * 0.2, y2 = yMax * 0.5, y3 = yMax * 0.8;
  const f1 = g(y1), f2 = g(y2), f3 = g(y3);
  const d12 = (f2 - f1) / (y2 - y1), d23 = (f3 - f2) / (y3 - y2);
  if (isFinite(d12) && isFinite(d23) && Math.abs(d12 - d23) < 1e-6 * (1 + Math.abs(d12)) && Math.abs(d12) > 1e-9) {
    const d = d12, c = f1 - d * y1;          // x = c + d·y  ⇒  y = (x − c)/d
    return { fn: (v) => (v - c) / d, inv: { c, d } };
  }
  return { fn: (v) => {
    const h = (y) => { const q = g(y); return isNaN(q) ? NaN : q - v; };
    const hi = Math.max(1, yMax * 3);
    let prevY = 0, prevH = h(0);
    for (let k = 1; k <= 240; k++) {
      const y = hi * k / 240, cur = h(y);
      if (!isNaN(prevH) && !isNaN(cur) && prevH * cur <= 0 && prevH !== cur) return (cur === 0) ? y : bisect(h, prevY, y);
      prevY = y; prevH = cur;
    }
    return NaN;
  } };
}

// Реестр моделей: подписи осей и пресеты полей. Поля живут в STATE.macro[model].
const MACRO = {
  adas:     { title: 'AD–AS', xl: 'Y', yl: 'P', vars: ['Y'] },
  phillips: { title: 'Кривая Филлипса', xl: 'u, %', yl: 'π, %', vars: ['u'] },
  money:    { title: 'Денежный рынок', xl: 'M', yl: 'i, %', vars: ['i'] },
  /* Правило 46: подпись оси — СИМВОЛ величины из реестра (DESIGN.md 5.1),
     единица добавляется только у доли и процента. Было «Объём», «Валюта»,
     «e (курс)», «t (ставка)», «Поступления» — пять фраз там, где у величины
     есть общепринятая буква. `Tx` уже стоит в легенде под поступлениями
     бюджета, `t` — ставка потоварного налога в деньгах (не процент). */
  loanable: { title: 'Рынок заёмных средств', xl: 'Q', yl: 'r, %', vars: ['r'] },
  fx:       { title: 'Валютный рынок', xl: 'Q', yl: 'e', vars: ['e'] },
  laffer:   { title: 'Кривая Лаффера', xl: 't', yl: 'Tx', vars: ['Q'] },
  islm:     { title: 'IS–LM', xl: 'Y', yl: 'r, %', vars: ['Y'] },
};

function macroP() { return STATE.macro[STATE.macroModel] || {}; }
// Запас поиска равновесия для макромоделей: масштаб осей подбирается ПОСЛЕ расчёта,
// поэтому искать в пределах текущего кадра нельзя — пересечение может быть за краем.
const MACRO_SEARCH = 5000;

/* --- Расчёты по моделям ------------------------------------------------- */
function recomputeMacro() {
  STATE.macroRes = null; STATE.macroErr = null;
  const m = STATE.macroModel, P = macroP(), V = MACRO[m].vars;
  const fail = (msg) => { STATE.macroErr = msg; };

  if (m === 'adas') {
    const sras = macroCurveY(P.sras, V), ad = macroCurveY(P.ad, V);
    if (sras.error || ad.error) return fail(sras.error || ad.error);
    const lras = makeVerticalCurve(P.lras);
    const eq = findEquilibrium(ad, sras, MACRO_SEARCH);     // краткосрочное равновесие
    const lr = findEquilibrium(ad, lras, MACRO_SEARCH);     // где AD пересекает LRAS
    if (!eq) return fail('Краткосрочное равновесие AD = SRAS не найдено.');
    const gap = eq.Q - P.lras;                              // >0 инфляционный, <0 рецессионный
    STATE.macroRes = { kind: 'adas', curves: [['AD', ad, COL.D], ['SRAS', sras, COL.S]],
                       vertical: [['LRAS', lras, COL.MC]], eq, lr, gap, Ystar: P.lras };
    applyAutoRanges(niceMax(Math.max(P.lras, eq.Q) * 1.5), niceMax(Math.max(eq.P, 1) * 2));
    return;
  }
  if (m === 'phillips') {
    // $\pi = \pi_e - \beta(u - u^*)$: прямая с наклоном −β через точку $(u^*;\\ \\pi_e)$.
    const f = (u) => P.pe - P.beta * (u - P.ustar);
    const sr = { fn: f };
    const lrp = makeVerticalCurve(P.ustar);
    STATE.macroRes = { kind: 'phillips', curves: [['SRPC', sr, COL.D]],
                       vertical: [['LRPC', lrp, COL.MC]],
                       eq: { Q: P.ustar, P: f(P.ustar) }, f, params: P };
    applyAutoRanges(niceMax(Math.max(P.ustar * 2.4, 10)), niceMax(Math.max(f(0), P.pe * 2, 10)));
    return;
  }
  if (m === 'money') {
    const md = macroCurveInv(P.md, V, 100);                 // M = f(i) → i = f(M)
    if (md.error) return fail(md.error);
    const ms = makeVerticalCurve(P.ms);
    const eq = findEquilibrium(md, ms, MACRO_SEARCH);
    if (!eq) return fail('Равновесие Md = Ms не найдено при неотрицательной ставке.');
    STATE.macroRes = { kind: 'money', curves: [['Md', md, COL.D]], vertical: [['Ms', ms, COL.S]], eq };
    applyAutoRanges(niceMax(Math.max(P.ms, eq.Q) * 1.7), niceMax(Math.max(eq.P, 1) * 2.4));
    return;
  }
  if (m === 'loanable') {
    // Спрос на заёмные средства ЧАСТНЫЙ; дефицит ΔG сдвигает ОБЩИЙ спрос вправо.
    const sv = macroCurveInv(P.s, V, 100), dv = macroCurveInv(P.d, V, 100);
    if (sv.error || dv.error) return fail(sv.error || dv.error);
    // Общий спрос = частный, сдвинутый вправо на ΔG по объёму. Ниже объёма ΔG
    // ставки нет вовсе: государству нужны эти ΔG при любой ставке, то есть там
    // кривая вертикальна и как r = f(Q) не выражается. Возвращаем NaN, чтобы не
    // рисовать вместо неё ложную горизонтальную полку на уровне запретительной ставки.
    const dTot = { fn: (x) => (x < P.dg) ? NaN : dv.fn(x - P.dg) };
    const base = findEquilibrium(dv, sv, MACRO_SEARCH);
    const after = findEquilibrium(dTot, sv, MACRO_SEARCH);
    if (!base || !after) return fail('Равновесие на рынке заёмных средств не найдено.');
    // ВЫТЕСНЕНИЕ считаем по ИСХОДНОЙ кривой частного спроса при НОВОЙ ставке.
    const privAfter = invCurve(dv, after.P);
    const crowding = (privAfter == null) ? null : base.Q - privAfter;
    STATE.macroRes = { kind: 'loanable', curves: [['S', sv, COL.S], ['D частн.', dv, COL.D]],
                       extra: (P.dg > 0) ? [['D общий', dTot, COL.reg]] : [],
                       vertical: [], eq: after, base, privAfter, crowding, dg: P.dg };
    applyAutoRanges(niceMax(Math.max(base.Q, after.Q) * 1.6), niceMax(Math.max(base.P, after.P) * 2));
    return;
  }
  if (m === 'fx') {
    const dv = macroCurveInv(P.d, V, 100), sv = macroCurveInv(P.s, V, 100);
    if (dv.error || sv.error) return fail(dv.error || sv.error);
    const eq = findEquilibrium(dv, sv, MACRO_SEARCH);
    if (!eq) return fail('Равновесный курс не найден.');
    // Фиксированный курс — ТА ЖЕ геометрия, что потолок/пол цены: короткая сторона
    // рынка торгуется, разрыв покрывают интервенции ЦБ.
    let fixed = null;
    if (P.fixedOn && P.fixed > 0) {
      const Qd = invCurve(dv, P.fixed), Qs = invCurve(sv, P.fixed);
      if (Qd != null && Qs != null) {
        fixed = { e: P.fixed, Qd, Qs, trade: Math.min(Qd, Qs), gap: Math.abs(Qd - Qs),
                  deficit: Qd > Qs };   // спрос выше предложения ⇒ ЦБ продаёт резервы
      }
    }
    STATE.macroRes = { kind: 'fx', curves: [['D валюты', dv, COL.D], ['S валюты', sv, COL.S]],
                       vertical: [], eq, fixed };
    applyAutoRanges(niceMax(eq.Q * 1.7), niceMax(eq.P * 2.2));
    return;
  }
  if (m === 'laffer') {
    // Фаза 21: НЕ отдельная формула — прогоняем уже проверенный механизм
    // «равновесие с потоварным налогом» по сетке ставок и копим пары (t, доход).
    const dr = compileFormula(P.d), sr = compileFormula(P.s);
    if (dr.error || sr.error) return fail(dr.error || sr.error);
    const D = { compiled: dr.compiled, linear: detectLinear(dr.compiled) };
    const S = { compiled: sr.compiled, linear: detectLinear(sr.compiled) };
    const pts = [];
    let best = { t: 0, rev: 0, Q: null };
    const N = 200, tMax = P.tmax;
    for (let i = 0; i <= N; i++) {
      const t = tMax * i / N;
      const st = { fn: (q) => { const v = evalCurve(S, q); return isNaN(v) ? NaN : v + t; } };
      const e = findEquilibrium(D, st);
      const rev = e ? t * e.Q : 0;
      pts.push([t, rev]);
      if (rev > best.rev) best = { t, rev, Q: e ? e.Q : null };
    }
    STATE.macroRes = { kind: 'laffer', pts, best, tMax };
    applyAutoRanges(niceMax(tMax), niceMax(Math.max(best.rev, 1) * 1.25));
    return;
  }
  if (m === 'islm') {
    const is = macroCurveY(P.is, V), lm = macroCurveY(P.lm, V);
    if (is.error || lm.error) return fail(is.error || lm.error);
    const eq = findEquilibrium(is, lm, MACRO_SEARCH);
    if (!eq) return fail('Пересечение IS и LM не найдено в первой четверти.');
    STATE.macroRes = { kind: 'islm', curves: [['IS', is, COL.D], ['LM', lm, COL.S]], vertical: [], eq };
    applyAutoRanges(niceMax(eq.Q * 1.6), niceMax(Math.max(eq.P, 1) * 3));
    return;
  }
}

/* --- Общая отрисовка макромоделей --------------------------------------- */
function drawMacroCurve(c, color, dash, label) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  if (isVertical(c)) {
    g.append('line').attr('x1', sx(c.atQ)).attr('y1', sy(0)).attr('x2', sx(c.atQ)).attr('y2', sy(CONFIG.Pmax))
      .attr('stroke', color).attr('stroke-width', 2.8);
    if (label) g.append('text').attr('x', sx(c.atQ) + 6).attr('y', sy(CONFIG.Pmax * 0.94))
      .attr('font-size', FS.base).attr('font-weight', 600).attr('fill', color)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
    return;
  }
  const pts = [];
  for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = evalCurve(c, q); pts.push(isNaN(v) ? null : [q, v]); }
  const p = g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2.6).attr('d', line);
  if (dash) p.attr('stroke-dasharray', '6 4');
  if (label) {
    for (const t of [0.86, 0.7, 0.5, 0.3, 0.14]) {
      const q = CONFIG.Qmax * t, v = evalCurve(c, q);
      if (!isNaN(v) && v > CONFIG.Pmax * 0.04 && v < CONFIG.Pmax * 0.95) {
        g.append('text').attr('x', sx(q)).attr('y', sy(v) - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', color)
          .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
        break;
      }
    }
  }
}

function redrawMacro() {
  recomputeMacro();
  makeScales();
  svg.selectAll('*').remove();
  addDefs(); drawGrid();
  const M = MACRO[STATE.macroModel];
  drawAxes(M.xl, M.yl);
  const errBox = document.getElementById('macro-error');
  if (errBox) { errBox.style.display = STATE.macroErr ? 'block' : 'none'; errBox.textContent = STATE.macroErr || ''; }
  const r = STATE.macroRes;
  if (!r) { updateMacroPanel(); return; }

  if (r.kind === 'laffer') {
    const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
    const line = d3.line().x(d => sx(d[0])).y(d => sy(d[1]));
    const area = d3.area().x(d => sx(d[0])).y0(sy(0)).y1(d => sy(d[1]));
    g.append('path').datum(r.pts).attr('d', area).attr('fill', COL.tax).attr('opacity', 0.12).attr('data-legend', 'Поступления бюджета');
    g.append('path').datum(r.pts).attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2.8).attr('d', line);
    const og = svg.append('g'), ox = sx(0), oy = sy(0);
    const [px, py] = toPx(r.best.t, r.best.rev);
    og.append('line').attr('x1', px).attr('y1', oy).attr('x2', px).attr('y2', py)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    og.append('line').attr('x1', ox).attr('y1', py).attr('x2', px).attr('y2', py)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    og.append('circle').attr('cx', px).attr('cy', py).attr('r', 5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 2);
    haloText(og, px, oy + 8, 't=' + fmt(r.best.t), 'middle', 'hanging');
    haloText(og, ox - 8, py, fmt(r.best.rev), 'end', 'middle');
    og.append('text').attr('x', px + 9).attr('y', py - 9).attr('font-size', FS.base).attr('font-weight', 700).attr('fill', COL.ink)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Максимум');
    updateMacroPanel();
    return;
  }

  // Разрыв выпуска в AD–AS — отрезок на оси Y между фактическим и потенциальным.
  if (r.kind === 'adas' && Math.abs(r.gap) > 1e-6) {
    const oy = sy(0), g = svg.append('g');
    const x1 = sx(Math.min(r.eq.Q, r.Ystar)), x2 = sx(Math.max(r.eq.Q, r.Ystar));
    g.append('line').attr('x1', x1).attr('y1', oy).attr('x2', x2).attr('y2', oy)
      .attr('stroke', r.gap < 0 ? COL.bad : COL.warn).attr('stroke-width', 6).attr('opacity', 0.55);
    haloText(g, (x1 + x2) / 2, oy + 24, (r.gap < 0 ? 'Рецессионный разрыв = ' : 'Инфляционный разрыв = ') + fmt(Math.abs(r.gap)), 'middle', 'hanging');
  }
  // Фиксированный курс — переиспользуем геометрию потолка/пола цены.
  if (r.kind === 'fx' && r.fixed) {
    const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax), g = svg.append('g');
    const ye = sy(r.fixed.e);
    g.append('line').attr('x1', ox).attr('y1', ye).attr('x2', xMax).attr('y2', ye)
      .attr('stroke', COL.reg).attr('stroke-width', 2.5);
    haloText(g, ox - 8, ye, 'e фикс=' + fmt(r.fixed.e), 'end', 'middle');
    const xa = sx(Math.min(r.fixed.Qd, r.fixed.Qs)), xb = sx(Math.max(r.fixed.Qd, r.fixed.Qs));
    if (xb > xa + 1) {
      g.append('line').attr('x1', xa).attr('y1', oy).attr('x2', xb).attr('y2', oy)
        .attr('stroke', r.fixed.deficit ? COL.bad : COL.MR).attr('stroke-width', 5).attr('opacity', 0.5);
      haloText(g, (xa + xb) / 2, oy + 24,
        (r.fixed.deficit ? 'Дефицит валюты = ' : 'Избыток валюты = ') + fmt(r.fixed.gap), 'middle', 'hanging');
    }
  }
  (r.extra || []).forEach(([lab, c, col]) => drawMacroCurve(c, col, true, lab));
  (r.curves || []).forEach(([lab, c, col]) => drawMacroCurve(c, col, false, lab));
  (r.vertical || []).forEach(([lab, c, col]) => drawMacroCurve(c, col, false, lab));
  // Точка равновесия + бледный исходный ориентир (заёмные средства «до дефицита»).
  if (r.base && STATE.showGhost && Math.abs(r.base.Q - r.eq.Q) > 1e-6) {
    const g = svg.append('g'), [bx, by] = toPx(r.base.Q, r.base.P);
    g.append('circle').attr('cx', bx).attr('cy', by).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', bx + 7).attr('y', by + 14).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Было');
  }
  if (r.eq) drawEquilibriumAt(r.eq.Q, r.eq.P, (r.kind === 'phillips') ? 'u*' : 'E');
  updateMacroPanel();
}

// Точка пересечения с проекциями (обобщение drawEquilibrium под любые оси).
function drawEquilibriumAt(Q, P, label) {
  const ox = sx(0), oy = sy(0), g = svg.append('g'), [px, py] = toPx(Q, P);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(px, py, px, oy); dash(px, py, ox, py);
  haloText(g, px, oy + 8, fmt(Q), 'middle', 'hanging');
  haloText(g, ox - 8, py, fmt(P), 'end', 'middle');
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  pointName(g, px, py, label, COL.ink);
}

function updateMacroPanel() {
  const box = document.getElementById('info-macro'); if (!box) return;
  const r = STATE.macroRes;
  if (!r) { box.innerHTML = '<div class="warn">' + (STATE.macroErr || 'Задайте параметры модели.') + '</div>'; return; }
  const P = macroP();
  let html = '';
  if (r.kind === 'adas') {
    html += `<div class="stat"><span>Краткосрочно: (Y; P)</span><b>(${fmt(r.eq.Q)}; ${fmt(r.eq.P)})</b></div>`;
    html += `<div class="stat"><span>Потенциальный выпуск $Y^*$</span><b>${fmt(r.Ystar)}</b></div>`;
    const g = r.gap;
    /* п. 82. У нуля знака нет. «+0» обещает превышение, которого нет: разрыв
       ровно нулевой значит, что выпуск и есть потенциальный. Сравниваем с
       ПОКАЗАННЫМ числом, а не с сырым: −0,004 печатается как «0», и знак
       у него был бы взят от невидимой сотой. */
    const shown = fmt(g);
    const zero = /^-?0([.,]0+)?$/.test(shown);
    html += `<div class="stat"><span>Разрыв выпуска</span><b>${(zero || g < 0) ? shown : '+' + shown}</b></div>`;
    html += `<div class="hint" style="margin-top:4px;">${Math.abs(g) < 1e-6
      ? 'Экономика ровно на потенциале: краткосрочное равновесие совпало с долгосрочным, разрыва нет.'
      : (g < 0
        ? '<b>Рецессионный разрыв</b>: фактический выпуск ниже потенциального на ' + fmt(-g) + ': ресурсы недозагружены, безработица выше естественной.'
        : '<b>Инфляционный разрыв</b>: фактический выпуск выше потенциального на ' + fmt(g) + ': экономика перегрета, давление на цены вверх.')}</div>`;
  } else if (r.kind === 'phillips') {
    const f = r.f;
    html += `<div class="stat"><span>Ожидаемая инфляция πe</span><b>${fmt(P.pe)}</b></div>`;
    html += `<div class="stat"><span>Естественный уровень $u^*$</span><b>${fmt(P.ustar)}</b></div>`;
    html += `<div class="stat"><span>Наклон β</span><b>${fmt(P.beta)}</b></div>`;
    // Обратные слэши УДВОЕНЫ: в строке JS «\p» схлопывается в «p», а «\b» это
    // вовсе символ забоя, и KaTeX на нём падает красной рамкой.
    html += '<table class="tx-table" style="margin-top:6px;"><tr><th>u</th><th>$\\pi = \\pi_e - \\beta(u - u^*)$</th></tr>';
    [P.ustar - 2, P.ustar, P.ustar + 2].forEach(u => { html += `<tr><td>${fmt(u)}</td><td>${fmt(f(u))}</td></tr>`; });
    html += '</table>';
    html += '<div class="hint">Краткосрочная кривая проходит через точку $(u^*;\\ \\pi_e)$ с наклоном $-\\beta$: снизить ' +
      'безработицу ниже естественной можно только ценой более высокой инфляции. Долгосрочная идёт вертикалью ' +
      'при u = u*: в долгом периоде ожидания подстраиваются, и размена нет.</div>';
  } else if (r.kind === 'money') {
    html += `<div class="stat"><span>Предложение денег Ms</span><b>${fmt(P.ms)}</b></div>`;
    html += `<div class="stat"><span>Равновесная ставка i</span><b>${fmt(r.eq.P)}</b></div>`;
    html += '<div class="hint">Предложение денег задаёт ЦБ, оно не зависит от ставки и поэтому вертикально. ' +
      'Ставка уравновешивает спрос на деньги с этим фиксированным предложением.</div>';
  } else if (r.kind === 'loanable') {
    html += `<div class="stat"><span>База: (r; объём)</span><b>(${fmt(r.base.P)}; ${fmt(r.base.Q)})</b></div>`;
    if (r.dg > 0) {
      html += `<div class="stat"><span>Дефицит бюджета ΔG</span><b>${fmt(r.dg)}</b></div>`;
      html += `<div class="stat"><span>Новая ставка r</span><b>${fmt(r.eq.P)}</b></div>`;
      html += `<div class="stat"><span>Частные инвестиции при новой r</span><b>${fmt(r.privAfter)}</b></div>`;
      html += `<div class="stat"><span>Вытеснение</span><b>${fmt(r.crowding)}</b></div>`;
      html += '<div class="hint">Государство занимает, ОБЩИЙ спрос на заёмные средства сдвигается вправо, ставка ' +
        'растёт. Вытеснение считается по <b>исходной</b> кривой ЧАСТНОГО спроса при новой ставке: сколько частных ' +
        'инвестиций ушло. Не путайте её со сдвинутой общей кривой.</div>';
    } else {
      html += '<div class="hint">Задайте дефицит бюджета ΔG, чтобы увидеть эффект вытеснения.</div>';
    }
  } else if (r.kind === 'fx') {
    html += `<div class="stat"><span>Плавающий курс e</span><b>${fmt(r.eq.P)}</b></div>`;
    html += `<div class="stat"><span>Объём при плавающем</span><b>${fmt(r.eq.Q)}</b></div>`;
    if (r.fixed) {
      html += `<div class="stat" style="margin-top:4px;"><span>Фиксированный курс</span><b>${fmt(r.fixed.e)}</b></div>`;
      html += `<div class="stat"><span>(Спрос; предложение)</span><b>(${fmt(r.fixed.Qd)}; ${fmt(r.fixed.Qs)})</b></div>`;
      html += `<div class="stat"><span>${r.fixed.deficit ? 'Дефицит валюты' : 'Избыток валюты'}</span><b>${fmt(r.fixed.gap)}</b></div>`;
      html += `<div class="hint">Это ровно та же геометрия, что потолок и пол цены на обычном рынке: торгуется ` +
        `короткая сторона, а разрыв ${r.fixed.deficit ? 'ЦБ покрывает продажей резервов' : 'ЦБ скупает, наращивая резервы'}.</div>`;
    } else {
      html += '<div class="hint">Включите фиксированный курс, чтобы увидеть дефицит или избыток валюты и ' +
        'необходимые интервенции ЦБ.</div>';
    }
  } else if (r.kind === 'laffer') {
    html += `<div class="stat"><span>Ставка максимума t</span><b>${fmt(r.best.t)}</b></div>`;
    html += `<div class="stat"><span>Максимальные поступления</span><b>${fmt(r.best.rev)}</b></div>`;
    if (r.best.Q != null) html += `<div class="stat"><span>Объём рынка при ней</span><b>${fmt(r.best.Q)}</b></div>`;
    html += '<div class="hint">Кривая построена НЕ отдельной формулой: для каждой ставки прогоняется тот же ' +
      'расчёт рыночного равновесия с потоварным налогом, что и в сцене «Налог», и берётся ставка × объём. ' +
      'Поэтому она согласована с остальным движком по построению. При нулевой ставке поступлений нет; при ' +
      'запретительной рынок схлопывается, поэтому максимум лежит между.</div>';
  } else if (r.kind === 'islm') {
    html += `<div class="stat"><span>Равновесный выпуск Y</span><b>${fmt(r.eq.Q)}</b></div>`;
    html += `<div class="stat"><span>Равновесная ставка r</span><b>${fmt(r.eq.P)}</b></div>`;
    html += '<div class="hint">IS это сочетания Y и r, при которых равновесен товарный рынок; LM те, при которых ' +
      'равновесен денежный. Пересечение даёт единственную пару, где равновесны оба.</div>';
  }
  box.innerHTML = html;
}

// Переключатель макромодели: показ нужной панели полей + перерисовка.
function setMacroModel(m) {
  STATE.macroModel = m;
  cancelRangeAnim();
  Object.keys(MACRO).forEach(k => {
    const b = document.getElementById('mm-' + k); if (b) b.classList.toggle('active', k === m);
    const p = document.getElementById('macro-pane-' + k); if (p) p.style.display = (k === m) ? '' : 'none';
  });
  const nm = document.getElementById('scene-name');
  if (nm && STATE.mode === 'macro') nm.textContent = MACRO[m].title;
  if (typeof updatePult === 'function') updatePult();
  redrawAll();
}

