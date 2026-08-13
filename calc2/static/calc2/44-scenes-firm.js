// Фирма: издержки, производство, изокванты, два завода.
/* ---------------------------------------------------------------------
   БЛОК 10. ИЗДЕРЖКИ ФИРМЫ — кривые MC/ATC/AVC/AFC из TC и FC (Задача 2).
   База — суммарные затраты TC(Q) и постоянные FC. Остальное выводится:
     VC = TC − FC,  ATC = TC/Q,  AVC = VC/Q,  AFC = FC/Q,  MC = d(TC)/dQ.
   MC — численная производная (центральная разность), работает для любой TC.
   --------------------------------------------------------------------- */

// Значение TC(Q) по компилированной формуле (Q и x — обе переменные).
function evalTC(q) {
  if (!STATE.costsCompiled) return NaN;
  try { const v = STATE.costsCompiled.evaluate(paramScope({ x: q, Q: q })); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
  catch (e) { return NaN; }
}
function costVC(q)  { const tc = evalTC(q); return isNaN(tc) ? NaN : tc - STATE.costsFC; }   // переменные = TC − FC
function costATC(q) { const tc = evalTC(q); return isNaN(tc) ? NaN : tc / q; }                // средние общие
function costAVC(q) { const vc = costVC(q); return isNaN(vc) ? NaN : vc / q; }                // средние переменные
function costAFC(q) { return STATE.costsFC / q; }                                            // средние постоянные
// MC = d(TC)/dQ численно (центральная разность) — как mcAt для TC.
function costMC(q) {
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const a = evalTC(q + h), b = evalTC(q - h);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / (2 * h);
}

// Минимум функции f на [qLo, qHi]: грубый скан + локальное уточнение.
// Через него находим точки закрытия (min AVC) и безубыточности (min ATC).
function minOf(f, qLo, qHi) {
  let bestQ = null, bestV = Infinity;
  const scan = (lo, hi, n) => {
    for (let i = 0; i <= n; i++) {
      const q = lo + (hi - lo) * i / n, v = f(q);
      if (!isNaN(v) && v < bestV) { bestV = v; bestQ = q; }
    }
  };
  scan(qLo, qHi, 2000);
  if (bestQ != null) { const step = (qHi - qLo) / 2000; scan(Math.max(qLo, bestQ - step), Math.min(qHi, bestQ + step), 400); }
  return bestQ == null ? null : { Q: bestQ, val: bestV };
}

// Пересчёт издержек: компиляция TC, ключевые точки (минимумы AVC и ATC).
function recomputeCosts() {
  STATE.costsReady = false;
  STATE.minAVC = STATE.minATC = null;
  const { compiled } = compileFormula(STATE.costsTC);
  if (!compiled) { STATE.costsCompiled = null; return; }
  STATE.costsCompiled = compiled;
  STATE.costsReady = true;
  // Сканируем от малого Q>0 (у средних кривых при Q→0 значения уходят в бесконечность).
  STATE.minAVC = minOf(costAVC, 0.5, CONFIG.Qmax);   // точка закрытия
  STATE.minATC = minOf(costATC, 0.5, CONFIG.Qmax);   // точка безубыточности
}

// Точки кривой издержек от малого Q (>0) до Qmax. Выбросы за пределы экрана обрываем.
function costPoints(f) {
  const N = 400, q0 = 0.5, out = [];
  for (let i = 0; i <= N; i++) {
    const q = q0 + (CONFIG.Qmax - q0) * i / N;
    const v = f(q);
    out.push((isNaN(v) || v < 0 || v > CONFIG.Pmax * 4) ? null : [q, v]);
  }
  return out;
}

// Отрисовка кривых издержек + точки закрытия (min AVC) и безубыточности (min ATC).
function drawCostCurves() {
  if (!STATE.costsReady) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const curve = (f, color, on, dash) => {
    if (!on) return;
    const p = g.append('path').datum(costPoints(f)).attr('fill', 'none')
      .attr('stroke', color).attr('stroke-width', 2.2).attr('d', line);
    if (dash) p.attr('stroke-dasharray', dash);
  };
  curve(costVC,  COL.costVC, STATE.showVC, '5 4');   // VC — полные переменные (по желанию)
  curve(costAFC, COL.costAFC, STATE.showAFC);
  curve(costAVC, COL.costAVC, STATE.showAVC);
  curve(costATC, COL.costATC, STATE.showATC);
  curve(costMC,  COL.costMC, STATE.showMC);

  // Подписи кривых (Фаза 3): у правого края, а если кривая там вне окна —
  // у ближайшего места, где она видна. Раньше подпись просто пропадала.
  if (STATE.showMC)  labelCurve(g, costMC,  'MC',  COL.costMC);
  if (STATE.showATC) labelCurve(g, costATC, 'ATC', COL.costATC);
  if (STATE.showAVC) labelCurve(g, costAVC, 'AVC', COL.costAVC, { below: true });
  if (STATE.showAFC) labelCurve(g, costAFC, 'AFC', COL.costAFC);
  if (STATE.showVC)  labelCurve(g, costVC,  'VC',  COL.costVC, { below: true });

  // Ключевые точки: безубыточность (min ATC) и закрытие (min AVC) — MC проходит через них.
  const mark = (pt, color, label) => {
    if (!pt || pt.val > CONFIG.Pmax || pt.Q > CONFIG.Qmax) return;
    const [px, py] = toPx(pt.Q, pt.val);
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4)
      .attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    g.append('text').attr('x', px).attr('y', py - 9)
      .attr('text-anchor', 'middle').attr('font-size', FS.small).attr('font-weight', 600).attr('fill', color)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
  };
  if (STATE.showATC) mark(STATE.minATC, COL.costATC, 'безубыт.');
  if (STATE.showAVC) mark(STATE.minAVC, COL.costAVC, 'закрытие');
}

// Табло издержек: ключевые точки закрытия и безубыточности.
function updateCostsPanel() {
  const box = document.getElementById('info-costs');
  if (!box) return;
  if (!STATE.costsReady) { box.innerHTML = '<div class="warn">Не понял формулу TC.</div>'; return; }
  let html = '';
  if (STATE.minATC) html += `<div class="stat"><span>Безубыточность (min ATC)</span><b>Q=${fmt(STATE.minATC.Q)}, ATC=${fmt(STATE.minATC.val)}</b></div>`;
  if (STATE.minAVC) html += `<div class="stat"><span>Закрытие (min AVC)</span><b>Q=${fmt(STATE.minAVC.Q)}, AVC=${fmt(STATE.minAVC.val)}</b></div>`;
  html += '<div class="hint">В точках закрытия и безубыточности MC пересекает соответственно AVC и ATC (в их минимумах).</div>';
  html = updateLongRunPanel(html);   // 9в — цена, оптимум P = MC, прибыль/убыток
  box.innerHTML = html;
}

// Полная перерисовка режима «Фирма»: три сюжета (Фаза 9).
function redrawCosts() {
  if (STATE.costsSub === 'production') { redrawProduction(); return; }   // 9а
  if (STATE.costsSub === 'isoquant')   { redrawIsoquant();   return; }   // 9б
  if (STATE.costsSub === 'plants')     { redrawPlants();     return; }   // Фаза 10
  recomputeCosts();
  recomputeLongRun();     // 9в — после recomputeCosts: нужны minATC / minAVC
  svg.selectAll('*').remove();
  addDefs();
  drawGrid();
  drawAxes('Q', '');
  svg.append('text').attr('x', sx(0) + 6).attr('y', sy(CONFIG.Pmax) - 5)
    .attr('text-anchor', 'start').attr('font-size', FS.base).attr('fill', COL.inkSoft).text('Издержки, цена');
  drawLongRunArea();      // прямоугольник прибыли/убытка — под кривыми
  drawCostCurves();
  if (STATE.lrOn) drawLongRunMarks();
  updateCostsPanel();
}

/* =====================================================================
   БЛОК 10а-2. ФИРМА: ПРОИЗВОДСТВО, ИЗОКВАНТЫ, ДОЛГИЙ ПЕРИОД (Фаза 9).
   Три сюжета внутри режима «Фирма» (costsSub):
     'costs'      — прежние кривые из TC + долгосрочное равновесие (9в);
     'production' — Q = f(L): TP, MP = dQ/dL, AP = Q/L (9а);
     'isoquant'   — Q(L,K), изокоста w·L + r·K = C, оптимум $MRTS = \frac{w}{r}$ (9б).
   9б переиспользует ДВИЖОК КАСАНИЯ УРОВНЯ из Фазы 7 без изменений — тот же,
   что рисует кривые безразличия потребителя.
   ===================================================================== */

/* --- 9в. Долгосрочное равновесие конкурентной фирмы --------------------- */
// Оптимум фирмы-ценополучателя: P = MC на ВОЗРАСТАЮЩЕЙ ветке (у U-образных
// издержек MC = P пересекается дважды; левый корень — минимум прибыли).
// Поэтому ищем корень справа налево, как findRootLast.
function recomputeLongRun() {
  STATE.lr = null;
  if (!STATE.costsReady || !STATE.lrOn) return;
  const P = STATE.lrPrice;
  if (!(P > 0)) return;
  const g = (q) => { const m = costMC(q); return isNaN(m) ? NaN : P - m; };   // P − MC: слева +, справа −
  const Q = findRootLast(g, 0.5, CONFIG.Qmax);
  if (Q == null || !(Q > 0)) return;
  const atc = costATC(Q), avc = costAVC(Q);
  const profit = isNaN(atc) ? null : (P - atc) * Q;
  // Краткосрочное правило остановки: цена ниже минимума AVC — выгоднее закрыться.
  const shutdown = (STATE.minAVC && P < STATE.minAVC.val - 1e-9);
  // Долгосрочная точка входа/выхода: P = min ATC (нулевая экономическая прибыль).
  const breakeven = STATE.minATC ? STATE.minATC.val : null;
  STATE.lr = { P, Q, atc, avc, profit, shutdown, breakeven };
}

// Прямоугольник прибыли (зелёный) или убытка (красный) между P и ATC на [0, Q].
function drawLongRunArea() {
  const lr = STATE.lr; if (!lr || !STATE.lrArea || lr.profit == null) return;
  if (Math.abs(lr.profit) < 1e-9 || !(lr.Q > 0)) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const yHi = Math.max(lr.P, lr.atc), yLo = Math.min(lr.P, lr.atc);
  g.append('rect').attr('x', sx(0)).attr('y', sy(yHi))
    .attr('width', sx(lr.Q) - sx(0)).attr('height', Math.abs(sy(yLo) - sy(yHi)))
    .attr('fill', lr.profit > 0 ? COL.tax : COL.bad).attr('opacity', lr.profit > 0 ? 0.20 : 0.18);
}

// Линия цены, точка P = MC и подписи.
function drawLongRunMarks() {
  const lr = STATE.lr; if (!lr) return;
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax), g = svg.append('g');
  const yP = sy(lr.P);
  g.append('line').attr('x1', ox).attr('y1', yP).attr('x2', xMax).attr('y2', yP)
    .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
  haloText(g, ox - 8, yP, 'P=' + fmt(lr.P), 'end', 'middle');
  const px = sx(lr.Q);
  g.append('line').attr('x1', px).attr('y1', yP).attr('x2', px).attr('y2', oy)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  g.append('circle').attr('cx', px).attr('cy', yP).attr('r', 4.5)
    .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  haloText(g, px, oy + 8, 'Q=' + fmt(lr.Q), 'middle', 'hanging');
  // Зона захвата линии цены — тянется мышью.
  const hit = g.append('rect').attr('x', ox).attr('y', yP - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  hit.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (e) => setLrPrice(sy.invert(e.y)))
    .on('end', () => { document.body.style.cursor = ''; }));
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.9).attr('cy', yP).attr('r', 7)
    .attr('fill', COL.reg).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

function setLrPrice(p) {
  p = Math.max(0, Math.min(p, CONFIG.Pmax));
  STATE.lrPrice = Math.round(p * 100) / 100;
  const s = document.getElementById('lr-price-slider'); if (s) s.value = STATE.lrPrice;
  const l = document.getElementById('lr-price-val');    if (l) l.textContent = fmt(STATE.lrPrice);
  const i = document.getElementById('lr-price-input');  if (i) i.value = STATE.lrPrice;
  redrawAll();
}

function updateLongRunPanel(html) {
  const lr = STATE.lr;
  if (!lr) return html;
  html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
  html += `<div class="stat"><span>Цена P</span><b>${fmt(lr.P)}</b></div>`;
  html += `<div class="stat"><span>Выпуск Q (P = MC)</span><b>${fmt(lr.Q)}</b></div>`;
  html += `<div class="stat"><span>$ATC(Q)$</span><b>${fmt(lr.atc)}</b></div>`;
  html += `<div class="stat"><span>${lr.profit >= 0 ? 'Прибыль' : 'Убыток'} (P − ATC)·Q</span><b>${fmt(lr.profit)}</b></div>`;
  if (lr.breakeven != null) html += `<div class="stat"><span>Вход/выход: P = min ATC</span><b>${fmt(lr.breakeven)}</b></div>`;
  html += `<div class="hint" style="margin-top:4px;">${lr.shutdown
    ? 'Цена ниже минимума AVC, поэтому в коротком периоде выгоднее <b>закрыться</b>: выручка не покрывает даже переменные издержки.'
    : (lr.profit > 1e-9
      ? 'Прибыль положительна, поэтому в долгом периоде в отрасль входят новые фирмы и цена падает к min ATC.'
      : (lr.profit < -1e-9
        ? 'Убыток при P выше min AVC: в коротком периоде производить стоит, в долгом фирмы уходят и цена растёт к min ATC.'
        : 'Нулевая экономическая прибыль и есть долгосрочное равновесие.'))}</div>`;
  return html;
}

/* --- 9а. Производственная функция Q = f(L) ------------------------------ */
function prodEval(L) {
  if (!STATE.prodCompiled) return NaN;
  try {
    const v = STATE.prodCompiled.evaluate(scopeFor(STATE.prodExpr, { L: L, x: L, Q: L }));
    return (typeof v === 'number' && isFinite(v)) ? v : NaN;
  } catch (e) { return NaN; }
}
// Предельный продукт MP = dQ/dL — центральная разность (как везде в движке).
function prodMP(L) {
  const h = Math.max(1e-5, L * 1e-5 || 1e-5), lo = Math.max(0, L - h);
  const a = prodEval(L + h), b = prodEval(lo);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / ((L + h) - lo);
}
function prodAP(L) { const q = prodEval(L); return (isNaN(q) || L <= 0) ? NaN : q / L; }

// Максимум произвольной функции на отрезке (зеркало minOf).
function maxOf(f, lo, hi) {
  let bestQ = null, bestV = -Infinity;
  const scan = (a, b, n) => { for (let i = 0; i <= n; i++) { const q = a + (b - a) * i / n, v = f(q); if (!isNaN(v) && v > bestV) { bestV = v; bestQ = q; } } };
  scan(lo, hi, 2000);
  if (bestQ != null) { const st = (hi - lo) / 2000; scan(Math.max(lo, bestQ - st), Math.min(hi, bestQ + st), 400); }
  return bestQ == null ? null : { L: bestQ, val: bestV };
}

function recomputeProduction() {
  STATE.prod = null;
  const { compiled, error } = compileFormula(STATE.prodExpr);
  const errBox = document.getElementById('prod-error');
  if (errBox) { errBox.style.display = error ? 'block' : 'none'; errBox.textContent = error ? ('Не понял формулу: ' + error) : ''; }
  if (!compiled) { STATE.prodCompiled = null; return; }
  STATE.prodCompiled = compiled;
  // Домен по L: до точки, где выпуск возвращается к нулю (или до края сетки).
  let Lmax = CONFIG.Qmax;
  const zero = findRootIn((l) => prodEval(l), CONFIG.Qmax * 0.02, CONFIG.Qmax * 20);
  if (zero != null && zero > 0) Lmax = zero;
  const maxTP = maxOf(prodEval, 0, Lmax);           // максимум выпуска
  const maxMP = maxOf(prodMP, 1e-3, Lmax);          // точка перегиба TP — начало убывающей отдачи
  const maxAP = maxOf(prodAP, 1e-3, Lmax);          // максимум AP: там AP = MP
  const mpAtMaxAP = maxAP ? prodMP(maxAP.L) : NaN;
  STATE.prod = { Lmax, maxTP, maxMP, maxAP, mpAtMaxAP };
}

// Две панели, общая ось L: сверху TP, снизу MP и AP (у них свой масштаб).
function redrawProduction() {
  recomputeProduction();
  svg.selectAll('*').remove();
  addDefs();
  const p = STATE.prod;
  if (!p) { updateProdPanel(); return; }
  const m = CONFIG.margin;
  const left = m.left, right = W - m.right;
  const top = m.top, bottom = H - m.bottom;
  const gap = 34, hTop = (bottom - top - gap) * 0.55, hBot = (bottom - top - gap) - hTop;
  const yTop0 = top + hTop, yBot0 = bottom;
  const Lmax = p.Lmax || CONFIG.Qmax;
  const tpMax = padMax(p.maxTP ? p.maxTP.val : 1);
  const mpMax = padMax(Math.max(p.maxMP ? p.maxMP.val : 1, p.maxAP ? p.maxAP.val : 1));
  const lx = d3.scaleLinear().domain([0, Lmax]).range([left, right]);
  const t1 = d3.scaleLinear().domain([0, tpMax]).range([yTop0, top]);
  const t2 = d3.scaleLinear().domain([0, mpMax]).range([yBot0, yTop0 + gap]);
  const panel = (scale, y0, title) => {
    const g = svg.append('g');
    drawGrid(lx, scale, g);          // у панели свои шкалы — сетку считаем по ним
    g.append('line').attr('x1', left).attr('y1', y0).attr('x2', right).attr('y2', y0)
      .attr('stroke', COL.ink).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
    g.append('line').attr('x1', left).attr('y1', y0).attr('x2', left).attr('y2', scale.range()[1])
      .attr('stroke', COL.ink).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
    g.append('text').attr('x', left + 4).attr('y', scale.range()[1] - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.ink).text(title);
    g.append('text').attr('x', right + 6).attr('y', y0 + 4).attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.ink).text('L');
    scale.ticks(5).forEach(t => { if (t <= 0) return;
      g.append('text').attr('x', left - 6).attr('y', scale(t)).attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
        .attr('font-size', FS.small).attr('fill', COL.inkSoft).text(fmt(t)); });
    lx.ticks(8).forEach(t => { if (t <= 0) return;
      g.append('text').attr('x', lx(t)).attr('y', y0 + 8).attr('text-anchor', 'middle').attr('dominant-baseline', 'hanging')
        .attr('font-size', FS.small).attr('fill', COL.inkSoft).text(fmt(t)); });
    return g;
  };
  const curve = (g, f, scale, color, on, width) => {
    if (!on) return;
    const line = d3.line().defined(d => d !== null).x(d => lx(d[0])).y(d => scale(d[1]));
    const pts = [];
    for (let i = 0; i <= 300; i++) {
      const l = Lmax * i / 300, v = f(l);
      pts.push((isNaN(v) || v < 0 || v > scale.domain()[1] * 1.5) ? null : [l, v]);
    }
    g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color).attr('stroke-width', width || 2.4).attr('d', line);
  };
  const gTop = panel(t1, yTop0, 'TP, общий продукт');
  curve(gTop, prodEval, t1, COL.prodTP, STATE.showTP, 2.6);
  const gBot = panel(t2, yBot0, 'MP и AP');
  curve(gBot, prodMP, t2, COL.prodMP, STATE.showMP);
  curve(gBot, prodAP, t2, COL.prodAP, STATE.showAP);
  // Ключевые вертикали: перегиб TP (максимум MP) и максимум AP (там AP = MP).
  const vline = (L, color, label) => {
    if (L == null) return;
    const x = lx(L);
    svg.append('line').attr('x1', x).attr('y1', top).attr('x2', x).attr('y2', bottom)
      .attr('stroke', color).attr('stroke-width', 1.2).attr('stroke-dasharray', '5 4').attr('opacity', 0.8);
    const g = svg.append('g');
    g.append('text').attr('x', x + 5).attr('y', top + 10).attr('font-size', FS.small).attr('font-weight', 600).attr('fill', color)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
  };
  if (p.maxMP) vline(p.maxMP.L, COL.prodMP, 'перегиб TP · max MP · L=' + fmt(p.maxMP.L));
  if (p.maxAP) vline(p.maxAP.L, COL.prodAP, 'max AP = MP · L=' + fmt(p.maxAP.L));
  if (p.maxTP) vline(p.maxTP.L, COL.ghost, 'max TP · MP=0');
  // Точки на нижней панели.
  if (p.maxAP && STATE.showAP) {
    svg.append('circle').attr('cx', lx(p.maxAP.L)).attr('cy', t2(p.maxAP.val)).attr('r', 4.5)
      .attr('fill', COL.prodAP).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  }
  if (p.maxMP && STATE.showMP) {
    svg.append('circle').attr('cx', lx(p.maxMP.L)).attr('cy', t2(p.maxMP.val)).attr('r', 4.5)
      .attr('fill', COL.prodMP).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  }
  updateProdPanel();
}

function updateProdPanel() {
  const box = document.getElementById('info-prod'); if (!box) return;
  const p = STATE.prod;
  if (!p) { box.innerHTML = '<div class="warn">Не понял формулу Q = f(L).</div>'; return; }
  let html = '';
  if (p.maxMP) html += `<div class="stat"><span>Перегиб TP (max MP)</span><b>L=${fmt(p.maxMP.L)}, MP=${fmt(p.maxMP.val)}</b></div>`;
  if (p.maxAP) html += `<div class="stat"><span>Максимум AP</span><b>L=${fmt(p.maxAP.L)}, AP=${fmt(p.maxAP.val)}</b></div>`;
  if (p.maxAP && !isNaN(p.mpAtMaxAP)) html += `<div class="stat"><span>$MP$ в этой точке</span><b>${fmt(p.mpAtMaxAP)}</b></div>`;
  if (p.maxTP) html += `<div class="stat"><span>Максимум TP</span><b>L=${fmt(p.maxTP.L)}, Q=${fmt(p.maxTP.val)}</b></div>`;
  html += '<div class="hint" style="margin-top:4px;">С точки перегиба TP начинается <b>убывающая предельная отдача</b>: ' +
    'каждый следующий работник добавляет меньше предыдущего. В максимуме AP выполняется <b>AP = MP</b>, ' +
    'пока MP выше среднего, средний растёт; как только MP опускается ниже, средний начинает падать. ' +
    'В максимуме TP предельный продукт равен нулю.</div>';
  box.innerHTML = html;
}

/* --- 9б. Изокванты и изокосты (движок Фазы 7 без изменений) -------------- */
function recomputeIsoquant() {
  STATE.iso = null; STATE.isoErr = null;
  const { compiled, error } = compileTwoVar(STATE.isoExpr);
  if (error) { STATE.isoErr = error; return; }
  const f = (L, K) => evalTwoVar(compiled, L, K);
  const r = optimizeAlongConstraint(f, STATE.isoW, STATE.isoR, STATE.isoC);
  if (!r) { STATE.isoErr = 'Проверьте цены факторов и бюджет: должны быть положительными.'; return; }
  STATE.iso = { f, L: r.a, K: r.b, Q: r.value, mrts: r.mrs, Lint: r.aMax, Kint: r.bMax };
  applyAutoRanges(padMax(r.aMax), padMax(r.bMax));
}

function redrawIsoquant() {
  recomputeIsoquant();
  makeScales();
  svg.selectAll('*').remove();
  addDefs(); drawGrid(); drawAxes('L', 'K');
  const iso = STATE.iso;
  if (!iso) { updateIsoPanel(); return; }
  if (STATE.isoFan && iso.Q > 0) [0.62, 0.8, 1.22].forEach(m => drawLevelCurve(iso.f, iso.Q * m, COL.isoq, 1.6, 0.35));
  drawBudgetLine({ xInt: iso.Lint, yInt: iso.Kint }, COL.reg, false, 'изокоста');
  drawLevelCurve(iso.f, iso.Q, COL.isoq, 2.6, 1);
  drawChoicePoint(iso.L, iso.K, COL.ink, 'E');
  updateIsoPanel();
}

function updateIsoPanel() {
  const box = document.getElementById('info-iso'); if (!box) return;
  const err = document.getElementById('iso-error');
  if (err) { err.style.display = STATE.isoErr ? 'block' : 'none'; err.textContent = STATE.isoErr ? ('Не понял формулу: ' + STATE.isoErr) : ''; }
  const iso = STATE.iso;
  if (!iso) { box.innerHTML = '<div class="warn">' + (STATE.isoErr || 'Задайте цены факторов и бюджет.') + '</div>'; return; }
  let html = '';
  html += `<div class="stat"><span>Оптимум $(L^*; K^*)$</span><b>(${fmt(iso.L)}; ${fmt(iso.K)})</b></div>`;
  html += `<div class="stat"><span>Выпуск Q</span><b>${fmt(iso.Q)}</b></div>`;
  html += `<div class="stat"><span>$MRTS$ в оптимуме</span><b>${fmt(iso.mrts)}</b></div>`;
  html += `<div class="stat"><span>$\\frac{w}{r}$</span><b>${fmt(STATE.isoW / STATE.isoR)}</b></div>`;
  html += `<div class="stat"><span>Потрачено</span><b>${fmt(STATE.isoW * iso.L + STATE.isoR * iso.K)}</b></div>`;
  html += '<div class="hint" style="margin-top:4px;">Условие оптимума то же, что у потребителя, только вместо ' +
    'полезности стоит выпуск, а вместо цен благ цены факторов: <b>$MRTS = \\frac{w}{r}$</b>. Это буквально один и тот же ' +
    'численный движок касания уровня.</div>';
  box.innerHTML = html;
}

/* =====================================================================
   БЛОК 10а-3. ДВА ЗАВОДА (Фаза 10) — агрегирование издержек.

   Совокупные издержки — это НЕ поточечная сумма TC₁(Q)+TC₂(Q), а минимум
   суммы по всем способам разделить выпуск:
        TC(Q) = min[Q₁+Q₂=Q] { TC₁(Q₁) + TC₂(Q₂) }.
   Условие оптимума: MC₁(Q₁) = MC₂(Q₂) = MC(Q). Если предельные издержки
   заводов различаются, выпуск выгодно перебросить туда, где дешевле
   следующая единица, — и так до выравнивания.
   Отсюда совокупная MC строится ГОРИЗОНТАЛЬНЫМ сложением: фиксируем уровень
   предельных издержек m, у каждого завода берём его Qᵢ(m) = MCᵢ⁻¹(m) и
   складываем ОБЪЁМЫ (та же логика, что сложение предложений фирм в рыночное).

   Реализация численная и параметрическая ПО УРОВНЮ m: для сетки m считаем
   Q₁(m), Q₂(m) (бисекция по объёму) и получаем пары (Q₁+Q₂, m) — это и есть
   готовая кривая совокупной MC. Дальше TC(Q) — интеграл трапециями по этой
   же таблице; параллельно считается прямая сумма TC₁(Q₁)+TC₂(Q₂) как сверка.
   ===================================================================== */

// Предельные издержки завода по его TC (центральная разность).
function plantMC(compiled, q) {
  const h = Math.max(1e-5, q * 1e-5 || 1e-5), lo = Math.max(0, q - h);
  const at = (x) => { try { const v = compiled.evaluate(paramScope({ Q: x, x: x, L: x })); return (typeof v === 'number' && isFinite(v)) ? v : NaN; } catch (e) { return NaN; } };
  const a = at(q + h), b = at(lo);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / ((q + h) - lo);
}
function plantTC(compiled, q) {
  try { const v = compiled.evaluate(paramScope({ Q: q, x: q, L: q })); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
  catch (e) { return NaN; }
}
// Объём завода при уровне предельных издержек m: MC(q) = m. MC растёт по q,
// поэтому чистая бисекция без сканирования — быстро (важно: вызывается сотни раз).
function plantQatMC(compiled, m, qMax) {
  if (!(plantMC(compiled, 1e-6) < m)) return 0;      // даже первая единица дороже m — завод стоит
  if (plantMC(compiled, qMax) <= m) return qMax;     // упёрлись в правый край сетки
  let lo = 0, hi = qMax;
  for (let k = 0; k < 60; k++) {
    const mid = (lo + hi) / 2, v = plantMC(compiled, mid);
    if (isNaN(v)) { hi = mid; continue; }
    if (v < m) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

/* До какого выпуска сканируется один завод. Число постоянное и от вида не
   зависит: 100 — тот же предел, с которым сцена открывалась и раньше. */
const PLANT_SCAN_Q = 100;

function recomputePlants() {
  STATE.plants = null; STATE.plErr = null;
  const r1 = compileFormula(STATE.pl1), r2 = compileFormula(STATE.pl2);
  if (r1.error || r2.error) { STATE.plErr = r1.error || r2.error; return; }
  const c1 = r1.compiled, c2 = r2.compiled;
  /* Предел выпуска ОДНОГО завода. Раньше здесь стоял CONFIG.Qmax — предел
     брался из текущего окна, а окно потом подгонялось под совокупный выпуск
     двух заводов, то есть примерно под удвоенный предел. Получалась обратная
     связь: каждая перерисовка раздвигала окно, окно поднимало предел, предел
     снова раздвигал окно. Со старым запасом ×1.05 «красивое» округление это
     почти гасило, с общим запасом ×1.12 (П33) расхождение стало явным: за
     несколько перерисовок ось уезжала на десятки тысяч, и колесо на сцене
     переставало что-либо менять. Теперь предел не зависит от вида. */
  const qMax = PLANT_SCAN_Q;                         // предел выпуска ОДНОГО завода
  const mMax = Math.max(plantMC(c1, qMax), plantMC(c2, qMax));
  if (!(mMax > 0)) { STATE.plErr = 'Предельные издержки не растут. Проверьте формулы TC.'; return; }
  // Таблица горизонтального сложения: по уровню предельных издержек m.
  const N = 400, table = [];
  let cum = 0;                                       // ∫ m dQ трапециями по таблице
  for (let i = 0; i <= N; i++) {
    const m = mMax * i / N;
    const q1 = plantQatMC(c1, m, qMax), q2 = plantQatMC(c2, m, qMax);
    const Q = q1 + q2;
    if (i > 0) { const p = table[table.length - 1]; cum += (m + p.m) / 2 * (Q - p.Q); }
    table.push({ m, q1, q2, Q, vc: cum, tcDirect: plantTC(c1, q1) + plantTC(c2, q2) });
  }
  STATE.plants = { c1, c2, table, qMax, mMax, Qtot: table[table.length - 1].Q };
  // Масштаб ползунка совокупного выпуска — под суммарный предел.
  const sl = document.getElementById('pl-q-slider'), inp = document.getElementById('pl-q-input');
  const top = Math.max(1, Math.round(STATE.plants.Qtot));
  if (sl) sl.max = top; if (inp) inp.max = top;
}

// Линейная интерполяция строки таблицы по совокупному выпуску Q.
function plantsAt(Q) {
  const p = STATE.plants; if (!p) return null;
  const t = p.table;
  if (Q <= 0) return { Q: 0, q1: 0, q2: 0, m: t[0].m, vc: 0, tcDirect: t[0].tcDirect };
  for (let i = 0; i < t.length - 1; i++) {
    const a = t[i], b = t[i + 1];
    if (Q >= a.Q && Q <= b.Q && b.Q > a.Q) {
      const k = (Q - a.Q) / (b.Q - a.Q);
      return { Q, q1: a.q1 + k * (b.q1 - a.q1), q2: a.q2 + k * (b.q2 - a.q2),
               m: a.m + k * (b.m - a.m), vc: a.vc + k * (b.vc - a.vc),
               tcDirect: a.tcDirect + k * (b.tcDirect - a.tcDirect) };
    }
  }
  const last = t[t.length - 1];
  return { Q: last.Q, q1: last.q1, q2: last.q2, m: last.m, vc: last.vc, tcDirect: last.tcDirect };
}

function redrawPlants() {
  recomputePlants();
  const p = STATE.plants;
  // Масштаб: по совокупной кривой (она самая длинная по Q).
  if (p) {
    const yTop = (STATE.plView === 'mc') ? p.mMax : Math.max(p.table[p.table.length - 1].tcDirect, 1);
    applyAutoRanges(padMax(p.Qtot), padMax(yTop));
  }
  makeScales();
  svg.selectAll('*').remove();
  addDefs(); drawGrid(); drawAxes('Q', '');
  const errBox = document.getElementById('pl-error');
  if (errBox) { errBox.style.display = STATE.plErr ? 'block' : 'none'; errBox.textContent = STATE.plErr ? ('Не понял формулу: ' + STATE.plErr) : ''; }
  if (!p) { updatePlantsPanel(); return; }
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const label = (x, y, txt, color) => {
    if (isNaN(y) || y > CONFIG.Pmax || y < 0) return;
    // А28: величина набирается с индексом, а не слипшимся текстом.
    renderLabelText(
      g.append('text').attr('x', sx(x)).attr('y', sy(y) - 5).attr('font-size', FS.base)
        .attr('font-weight', 600).attr('fill', color)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5),
      txt);
  };
  if (STATE.plView === 'mc') {
    // MC каждого завода по СВОЕМУ объёму + совокупная MC (горизонтальная сумма).
    const mkMC = (c) => { const o = []; for (let i = 0; i <= 300; i++) { const q = p.qMax * i / 300; const v = plantMC(c, q); o.push(isNaN(v) ? null : [q, v]); } return o; };
    g.append('path').datum(mkMC(p.c1)).attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
    g.append('path').datum(mkMC(p.c2)).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
    g.append('path').datum(p.table.map(r => [r.Q, r.m])).attr('fill', 'none').attr('stroke', COL.MC).attr('stroke-width', 2.8).attr('d', line);
    label(p.qMax * 0.5, plantMC(p.c1, p.qMax * 0.5), 'MC₁', COL.tax);
    label(p.qMax * 0.34, plantMC(p.c2, p.qMax * 0.34), 'MC₂', COL.reg);
    const mid = plantsAt(p.Qtot * 0.6); if (mid) label(mid.Q, mid.m, 'MC совокупная', COL.MC);
  } else {
    // TC каждого завода по своему объёму + совокупная TC(Q) (минимум суммы).
    const mkTC = (c) => { const o = []; for (let i = 0; i <= 300; i++) { const q = p.qMax * i / 300; const v = plantTC(c, q); o.push(isNaN(v) ? null : [q, v]); } return o; };
    g.append('path').datum(mkTC(p.c1)).attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
    g.append('path').datum(mkTC(p.c2)).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
    g.append('path').datum(p.table.map(r => [r.Q, r.tcDirect])).attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.8).attr('d', line);
    label(p.qMax * 0.7, plantTC(p.c1, p.qMax * 0.7), 'TC₁', COL.tax);
    label(p.qMax * 0.45, plantTC(p.c2, p.qMax * 0.45), 'TC₂', COL.reg);
    const mid = plantsAt(p.Qtot * 0.7); if (mid) label(mid.Q, mid.tcDirect, 'TC совокупная', COL.D);
  }
  // Метка выбранного совокупного выпуска и его разложение на заводы.
  const cur = plantsAt(STATE.plQ);
  if (cur && cur.Q > 0) {
    const og = svg.append('g'), ox = sx(0), oy = sy(0);
    const yv = (STATE.plView === 'mc') ? cur.m : cur.tcDirect;
    const [px, py] = toPx(cur.Q, yv);
    og.append('line').attr('x1', px).attr('y1', oy).attr('x2', px).attr('y2', py)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    og.append('line').attr('x1', ox).attr('y1', py).attr('x2', px).attr('y2', py)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    og.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    haloText(og, px, oy + 8, 'Q=' + fmt(cur.Q), 'middle', 'hanging');
    haloText(og, ox - 8, py, fmt(yv), 'end', 'middle');
    if (STATE.plView === 'mc') {
      // Показываем ГОРИЗОНТАЛЬНОЕ сложение: на уровне m объёмы заводов складываются.
      og.append('line').attr('x1', ox).attr('y1', py).attr('x2', sx(cur.Q)).attr('y2', py)
        .attr('stroke', COL.MC).attr('stroke-width', 1.6).attr('opacity', 0.5);
      [[cur.q1, COL.tax, 'Q₁'], [cur.q2, COL.reg, 'Q₂']].forEach(([q, c, t]) => {
        if (!(q > 0)) return;
        og.append('circle').attr('cx', sx(q)).attr('cy', py).attr('r', 3.5).attr('fill', c).attr('stroke', COL.halo).attr('stroke-width', 1.2);
        haloText(og, sx(q), py - 10, t + '=' + fmt(q), 'middle', 'auto');
      });
    }
  }
  updatePlantsPanel();
}

function updatePlantsPanel() {
  const box = document.getElementById('info-plants'); if (!box) return;
  const p = STATE.plants;
  if (!p) { box.innerHTML = '<div class="warn">' + (STATE.plErr || 'Введите функции затрат обоих заводов.') + '</div>'; return; }
  const cur = plantsAt(STATE.plQ);
  let html = '';
  if (cur) {
    html += `<div class="stat"><span>Совокупный выпуск Q</span><b>${fmt(cur.Q)}</b></div>`;
    html += `<div class="stat"><span>Завод 1: Q₁</span><b>${fmt(cur.q1)}</b></div>`;
    html += `<div class="stat"><span>Завод 2: Q₂</span><b>${fmt(cur.q2)}</b></div>`;
    html += `<div class="stat"><span>$MC_1 = MC_2 = MC(Q)$</span><b>${fmt(cur.m)}</b></div>`;
    html += `<div class="stat"><span>$TC(Q) = TC_1 + TC_2$</span><b>${fmt(cur.tcDirect)}</b></div>`;
    html += `<div class="stat"><span>∫ MC(q)dq (сверка)</span><b>${fmt(cur.vc)}</b></div>`;
    // Наглядная проверка: неверная «сумма в лоб» TC₁(Q)+TC₂(Q) заметно дороже.
    const naive = plantTC(p.c1, cur.Q) + plantTC(p.c2, cur.Q);
    if (!isNaN(naive)) html += `<div class="stat"><span>«Сумма в лоб» TC₁(Q)+TC₂(Q)</span><b>${fmt(naive)}</b></div>`;
  }
  html += '<div class="hint" style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);">' +
    '<b>Почему сложение ГОРИЗОНТАЛЬНОЕ</b><br>' +
    'Совокупные издержки это не TC₁(Q)&nbsp;+&nbsp;TC₂(Q) (столько стоило бы выпустить <i>по Q</i> на каждом заводе, ' +
    'то есть 2Q всего), а минимум суммы при делении выпуска:<br>' +
    '<code>TC(Q) = min[Q₁+Q₂=Q] { TC₁(Q₁) + TC₂(Q₂) }</code>.<br><br>' +
    'Пока $MC_1 \\ne MC_2$, единицу выгодно перебросить с дорогого завода на дешёвый, значит в оптимуме ' +
    '<b>$MC_1 = MC_2 = MC(Q)$</b>. Поэтому совокупную кривую строят так: фиксируют уровень ' +
    'предельных издержек m, у каждого завода берут его объём Qᵢ(m)&nbsp;=&nbsp;MCᵢ⁻¹(m) и складывают ' +
    '<b>объёмы</b>, а не высоты, ровно как рыночное предложение из предложений фирм.<br><br>' +
    'Проверить можно так: на вкладке «Предельные MC» на выбранном уровне видно, что Q₁&nbsp;+&nbsp;Q₂ даёт ' +
    'точку совокупной кривой, а TC(Q) совпадает с интегралом ∫MC с точностью до постоянных издержек.</div>';
  box.innerHTML = html;
}

function setPlantsView(v) {
  STATE.plView = v;
  const a = document.getElementById('plv-tc'), b = document.getElementById('plv-mc');
  if (a) a.classList.toggle('active', v === 'tc');
  if (b) b.classList.toggle('active', v === 'mc');
  redrawAll();
}
function setPlantsQ(q) {
  if (isNaN(q) || q < 0) return;
  STATE.plQ = q;
  const s = document.getElementById('pl-q-slider'); if (s) s.value = q;
  const l = document.getElementById('pl-q-val');    if (l) l.textContent = fmt(q);
  const i = document.getElementById('pl-q-input');  if (i) i.value = q;
  redrawAll();
}

// Переключатель сюжета режима «Фирма».
function setCostsSub(sub) {
  STATE.costsSub = sub;
  [['cs-costs', 'costs'], ['cs-prod', 'production'], ['cs-iso', 'isoquant'], ['cs-plants', 'plants']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === sub); });
  const panes = { costs: 'costs-pane-costs', production: 'costs-pane-prod',
                  isoquant: 'costs-pane-iso', plants: 'costs-pane-plants' };
  Object.values(panes).forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; });
  const ap = document.getElementById(panes[sub]); if (ap) ap.style.display = '';
  cancelRangeAnim();
  // Шапка сцены показывает конкретный сюжет, а не общее «Издержки фирмы».
  const nm = document.getElementById('scene-name');
  if (nm && STATE.mode === 'costs') nm.textContent =
    ({ costs: 'Издержки фирмы', production: 'Производство: TP, MP, AP',
       isoquant: 'Изокванты и изокосты', plants: 'Два завода' })[sub] || 'Фирма';
  // Характерный масштаб под сюжет: издержки — мелкий, два завода — по объёму заводов.
  if (sub === 'costs') setRanges(10, 50);
  if (sub === 'plants') setRanges(30, 100);
  if (typeof updatePult === 'function') updatePult();
  redrawAll();
}

