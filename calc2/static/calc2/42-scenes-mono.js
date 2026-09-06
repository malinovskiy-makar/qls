// Монополия: MR и MC, потолок, налог, естественная, под-режимы.
/* ---------------------------------------------------------------------
   БЛОК 8г. МОНОПОЛИЯ — предельный доход MR и предельные издержки MC (Задача 3).
   Монополист выпускает Q, где MR = MC, и берёт цену с кривой спроса.
   MR и MC — производные: численно (центральная разность), поэтому работают
   для ЛЮБОЙ формы кривой спроса и затрат.
   --------------------------------------------------------------------- */

// Источник предельных издержек: явная кривая MC, иначе предложение S
// (в совершенной конкуренции S = MC — стандартное допущение, удобно как fallback).
function mcSourceCurve() {
  return curveByRole('mc') || curveByRole('supply') || null;
}
// То же для интерфейса и пресетов: роль занята и погашенной кривой тоже.
function mcSourceCurveAny() {
  return curveByRoleAny('mc') || curveByRoleAny('supply') || null;
}

// Предельные издержки в точке Q: прямая кривая MC/S, иначе d(TC)/dQ.
function mcAt(q) {
  const direct = mcSourceCurve();
  if (direct) return evalCurve(direct, q);
  const TC = curveByRole('tc');
  if (TC) {
    const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
    const a = evalCurve(TC, q + h), b = evalCurve(TC, q - h);
    if (isNaN(a) || isNaN(b)) return NaN;
    return (a - b) / (2 * h);            // центральная разность производной
  }
  return NaN;
}

/* ⚠️ НИЖНЯЯ ГРАНИЦА ЛЮБОЙ ПЛОЩАДИ ПОД ПРЕДЕЛЬНЫМИ ИЗДЕРЖКАМИ — ОДИН ПОМОЩНИК
   НА ВСЕ СЮЖЕТЫ МОНОПОЛИИ.

   Отрицательных предельных издержек не бывает: произвести единицу нельзя
   дешевле, чем даром. Кривая MC вида Q − 20 уходит под ось Q, и площадь под
   ней без обрезки ГАСИЛА САМА СЕБЯ: у D = 100 − Q переменные издержки
   монополиста выходили ровно ноль (кусок под осью в точности съедал кусок над
   ней), а вычтенный из выручки минус утекал в излишек производителя. Признак
   болезни простой: PS + VC обязаны давать выручку TR, и без обрезки не давали.

   Зовут его ЧИСЛА и ЗАЛИВКИ одинаково: поправить одно без другого значит
   развести картинку с числом, а это хуже исходной ошибки (ADR 0086).

   ⚠️ ОПТИМУМ ЭТОТ ПОМОЩНИК НЕ ТРОГАЕТ. Выпуск по-прежнему ищется на НАСТОЯЩЕЙ
   кривой (MR = MC, D = MC, перебор кандидатов при потолке): решение
   монополиста принимается по его собственным издержкам, а первая четверть —
   правило ИЗМЕРЕНИЯ площади. Ровно так это уже сделано у дискриминации
   1-й степени: Qcomp ищется по mcAt, а прибыль меряется от нуля. */
function mcFloor(v) { return (v > 0) ? v : 0; }

// Предельный доход MR(Q) = d(TR)/dQ, где TR = P(Q)·Q = D(Q)·Q.
// Центральная разность точна для линейного спроса (даёт MR = a − 2bQ).
function marginalRevenue(D, q) {
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const tr = (x) => { const p = evalCurve(D, x); return isNaN(p) ? NaN : p * x; };
  const a = tr(q + h), b = tr(q - h);
  if (isNaN(a) || isNaN(b)) return NaN;
  return (a - b) / (2 * h);
}

// Заливки монополии: области CS / VC / PS до Qm (Задача 1) и DWL (между D и MC от Qm до Qc).
function drawMonopolyAreas() {
  if (!STATE.mono) return;
  const m = STATE.mono;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };

  // Три области под спросом от 0 до Qm: тремя слоями (накладываются только границами).
  if (m.Qm > 0) {
    const s1 = samp(0, m.Qm);
    if (STATE.showMonoVC) {   // VC — под кривой MC (от оси P=0 до MC). Нейтральный серо-голубой.
      const a = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(mcFloor(mcAt(d))));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.22).attr('data-legend', 'Переменные издержки (VC)');
    }
    if (STATE.showMonoPS) {   // PS (TR − VC) — между MC (низ) и ценой Pm (верх). Красный, как PS конкуренции.
      const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(sy(m.Pm));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек производителя (TR - VC)');
    }
    if (STATE.showMonoCS) {   // CS — между ценой Pm (низ) и спросом D (верх). Синий, как CS конкуренции.
      const a = d3.area().x(d => sx(d)).y0(sy(m.Pm)).y1(d => sy(evalCurve(STATE.D, d)));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
    }
  }

  // DWL — между D и MC от Qm до Qc (потери против конкуренции), как раньше.
  if (m.Qc != null) {
    const lo = Math.min(m.Qm, m.Qc), hi = Math.max(m.Qm, m.Qc);
    if (hi > lo) {
      const s2 = samp(lo, hi);
      const aD = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(evalCurve(STATE.D, d)));
      g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
    }
  }
}

// Кривая MR (пунктир) и — если MC выведена из TC — сама кривая MC.
function drawMonopoly() {
  if (!STATE.mono) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const sample = (f) => {
    const pts = [];
    for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = f(q); pts.push(isNaN(v) ? null : [q, v]); }
    return pts;
  };
  // MR — фиолетовый пунктир. Продолжение ниже оси Q рисует общий помощник
  // (см. drawMarginalCurve в 30-curves.js): до нуля породившего спроса.
  drawMarginalCurve(g, q => marginalRevenue(STATE.D, q), STATE.D, COL.MR, { width: 2 });
  // Если MC выведена из TC (нет явной кривой mc/S) — нарисуем её красным.
  if (!mcSourceCurve() && curveByRole('tc')) {
    g.append('path').datum(sample(mcAt))
      .attr('fill', 'none').attr('stroke', COL.S).attr('stroke-width', 2.5).attr('d', line);
  }
}

// Точки оптимума, проекции и конкурентный ориентир (бледный, по галочке «было → стало»).
function drawMonopolyPoints() {
  if (!STATE.mono) return;
  const m = STATE.mono;
  const ox = sx(0), oy = sy(0);
  const g = svg.append('g');
  const [pxm, pym] = toPx(m.Qm, m.Pm);
  const [, pymc] = toPx(m.Qm, m.mcAtQm);
  const dash = (x1, y1, x2, y2) => g.append('line')
    .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');

  // Конкурентный ориентир (Qc, Pc) — бледный, как призрак (Задача 2).
  if (STATE.showGhost && m.Qc != null) {
    const [pxc, pyc] = toPx(m.Qc, m.Pc);
    g.append('circle').attr('cx', pxc).attr('cy', pyc).attr('r', 4)
      .attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', pxc + 7).attr('y', pyc + 13)
      .attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('К');
    axisValueX(g, pxc, oy, fmt(m.Qc), 'c');
  }

  // Вертикаль Qm (через точку MR=MC до спроса) + горизонталь к оси P.
  dash(pxm, oy, pxm, pym);
  dash(ox, pym, pxm, pym);
  // Точка MR=MC (фиолетовая) на вертикали.
  g.append('circle').attr('cx', pxm).attr('cy', pymc).attr('r', 3.5)
    .attr('fill', COL.MR).attr('stroke', COL.halo).attr('stroke-width', 1.2);
  // Точка монополии (Qm, Pm) на кривой спроса.
  g.append('circle').attr('cx', pxm).attr('cy', pym).attr('r', 4.5)
    .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  pointName(g, pxm, pym, 'M', COL.ink);
  axisValueX(g, pxm, oy, fmt(m.Qm), 'm');
  axisValueY(g, ox, pym, fmt(m.Pm), 'm');
}

// Табло монополии: Qm, Pm, конкурентные Qc/Pc, DWL, прибыль (если задана ATC).
function updateMonoPanel() {
  const box = document.getElementById('info-mono');
  if (!box) return;
  if (!STATE.D) { box.innerHTML = '<div class="muted">Отметьте кривую спроса (роль D).</div>'; return; }
  if (!mcSourceCurve() && !curveByRole('tc')) {
    box.innerHTML = '<div class="muted">Нужны предельные издержки: роль MC (либо TC, либо S как MC).</div>'; return;
  }
  if (!STATE.mono) { box.innerHTML = '<div class="warn">Оптимум MR = MC не найден в первой четверти.</div>'; return; }
  const m = STATE.mono;
  let html = '';
  html += `<div class="stat"><span>Qm (монополия)</span><b>${fmt(m.Qm)}</b></div>`;
  html += `<div class="stat"><span>Pm (цена)</span><b>${fmt(m.Pm)}</b></div>`;
  if (m.Qc != null) {
    html += `<div class="stat"><span>$Q_c$ (конкуренция)</span><b>${fmt(m.Qc)}</b></div>`;
    html += `<div class="stat"><span>$P_c$ (конкуренция)</span><b>${fmt(m.Pc)}</b></div>`;
  }
  if (m.dwl != null) html += `<div class="stat"><span>$DWL$ (потери)</span><b>${fmt(m.dwl)}</b></div>`;
  // Области (Задача 1). PS — это излишек производителя (TR − VC), НЕ прибыль:
  // прибыль = TR − TC, и от PS она отличается на постоянные издержки FC.
  html += `<div class="stat"><span>$CS$ (потребитель)</span><b>${fmt(m.csM)}</b></div>`;
  html += `<div class="stat"><span>$VC$ (перем. издержки)</span><b>${fmt(m.vcM)}</b></div>`;
  html += `<div class="stat"><span>Излишек произв. (TR&nbsp;−&nbsp;VC)</span><b>${fmt(m.psM)}</b></div>`;
  if (m.profit != null) html += `<div class="stat"><span>Прибыль (TR&nbsp;−&nbsp;TC)</span><b>${fmt(m.profit)}</b></div>`;
  // Вмешательство государства (потолок / пол / налог / субсидия) показывается отдельно —
  // в табло «Вмешательство» (info-tax) через updateMonoInterventionPanel().
  box.innerHTML = html;
}

/* Структура рынка: конкуренция ↔ монополия. Кнопок у неё больше нет
   (удалены 24.08), структуру задаёт карточка главного экрана — функция
   осталась единственной дверью смены STATE.market. */
function setMarket(mode) {
  STATE.market = mode;
  const mh = document.getElementById('mono-hint');
  if (mh) mh.style.display = (mode === 'monopoly') ? '' : 'none';
  // Вход в монополию — подставить стандартные кривые/поля, если их нет (Задача 1).
  if (mode === 'monopoly') ensureMonopolyPreset();
  // Уровни каскада вмешательства (вид налога, сторона) видны только в
  // конкуренции: в монополии налог входит в предельные издержки (monopolyTax
  // сдвигает MC), процентная форма туда не переносится. При входе в монополию
  // честно возвращаем потоварный вид, чтобы не считать по «не той» модели.
  if (mode === 'monopoly' && STATE.taxKind === 'advalorem') {
    STATE.taxForm = 'unit'; STATE.subKind = 'unit';
    syncTaxKind();
    applyTaxRateBounds();
    STATE.tax = Math.min(STATE.tax, CONFIG.Pmax);
  }
  applyIntervCascade();
  // Видимость под-режима монополии и его панелей (галочки областей / дискриминация / ломаный).
  applyMonoVisibility();
  if (typeof updatePult === 'function') updatePult();   // монополия: пульт = слайдеры D/MC + поле вмешательства
  redrawAll();
}

/* ---------------------------------------------------------------------
   БЛОК 8д. ПОТОЛОК ЦЕНЫ В МОНОПОЛИИ (Задача 3).
   Потолок Pc делает предельный доход «ломаным»: пока монополист продаёт по
   фиксированной цене Pc (не сбивая её), MR_eff = Pc — горизонтальна на [0, Q̂],
   где Q̂ — точка, в которой потолок встречает спрос (D(Q̂)=Pc). Правее Q̂
   MR_eff = обычный падающий MR. Монополист выпускает там, где ломаный MR_eff
   пересекает MC. Правильный потолок УВЕЛИЧИВАЕТ выпуск (парадокс); слишком
   низкий (ниже MC) — даёт дефицит. Всё численно (работает для любых кривых).
   --------------------------------------------------------------------- */

// Оптимум монополиста при потолке Pc через ломаный MR_eff.
// Возвращает { binding, Qstar, price, Qhat, shortage, dwl, csM, vcM, psM, Pc }.
function monopolyCeiling(Pc) {
  const D = STATE.D, m = STATE.mono;
  if (!D || !m) return null;
  const Pm = m.Pm, Qm = m.Qm, Qc = m.Qc;
  const Qhat = invCurve(D, Pc);                 // объём спроса при цене Pc: D(Q̂)=Pc
  // Потолок не ниже монопольной цены (или выше спроса) — не связывает.
  if (Pc >= Pm - 1e-9 || Qhat == null) {
    return { binding: false, Qstar: Qm, price: Pm, Qhat, shortage: 0, Pc, dwl: m.dwl, csM: m.csM, vcM: m.vcM, psM: m.psM };
  }
  // Относительная прибыль R(Q) = ∫ (MR_eff − MC) dQ; MR_eff горизонтальна (=Pc) до Q̂, далее обычный MR.
  // Разрыв в Q̂ учитываем, разбивая интеграл.
  /* ⚠️ ЗДЕСЬ mcFloor НЕ ЗОВЁТСЯ, И ЭТО НАРОЧНО. Rel — не показываемая площадь,
     а ВЫБОР монополиста: он решает по своим настоящим издержкам. Первая
     четверть — правило ИЗМЕРЕНИЯ площади, а не правило принятия решения; то же
     разделение стоит у дискриминации 1-й степени (выпуск ищется по mcAt,
     прибыль меряется от нуля) и у корня MR = MC в обычной монополии. */
  const Rel = (Q) => {
    const a = Math.min(Q, Qhat);
    let r = integrate(q => Pc - mcAt(q), 0, a);
    if (Q > Qhat) r += integrate(q => marginalRevenue(D, q) - mcAt(q), Qhat, Q);
    return r;
  };
  // Кандидаты на оптимум: 0, точка MC=Pc на плоской части, сам Q̂, обычный MR=MC за изломом.
  const cands = [{ Q: 0 }];
  const qmc = findRootIn(q => Pc - mcAt(q), 0, Qhat);
  if (qmc != null) cands.push({ Q: qmc });
  cands.push({ Q: Qhat });
  const qfall = findRootIn(q => marginalRevenue(D, q) - mcAt(q), Qhat, CONFIG.Qmax);
  if (qfall != null) cands.push({ Q: qfall });
  cands.forEach(c => c.R = Rel(c.Q));
  let best = cands[0];
  cands.forEach(c => { if (c.R > best.R + 1e-6 || (Math.abs(c.R - best.R) <= 1e-6 && c.Q > best.Q)) best = c; });
  const Qstar = best.Q;
  const price = (Qstar <= Qhat + 1e-9) ? Pc : evalCurve(D, Qstar);   // на плоской части цена = потолок
  const shortage = Math.max(0, Qhat - Qstar);                        // Qd(Pc)=Q̂, Qs=Qstar
  let dwl = null;
  if (Qc != null) {                              // потери — площадь между D и MC от Qstar до Qc
    const lo = Math.min(Qstar, Qc), hi = Math.max(Qstar, Qc);
    dwl = areaBetween(q => evalCurve(D, q) - mcFloor(mcAt(q)), lo, hi);
  }
  // Области CS/VC/PS до нового выпуска при новой цене (для табло и заливок).
  const csM = integrate(q => evalCurve(D, q) - price, 0, Qstar);
  const vcM = integrate(q => mcFloor(mcAt(q)), 0, Qstar);
  const psM = integrate(q => price - mcFloor(mcAt(q)), 0, Qstar);
  return { binding: true, Qstar, price, Qhat, shortage, Pc, dwl, csM, vcM, psM };
}

// Заливки при связывающем потолке: CS/VC/PS до Qstar (при новой цене) + DWL от Qstar до Qc.
function drawMonoCeilingAreas() {
  const mc = STATE.monoCeil, m = STATE.mono;
  if (!mc || !mc.binding || !m) return;
  const D = STATE.D, g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const Qs = mc.Qstar, P = mc.price;
  if (Qs > 1e-6) {
    const s1 = samp(0, Qs);
    if (STATE.showMonoVC) { const a = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(mcFloor(mcAt(d)))); g.append('path').datum(s1).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.22).attr('data-legend', 'Переменные издержки (VC)'); }
    if (STATE.showMonoPS) { const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(sy(P)); g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек производителя (TR - VC)'); }
    if (STATE.showMonoCS) { const a = d3.area().x(d => sx(d)).y0(sy(P)).y1(d => sy(evalCurve(D, d))); g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)'); }
  }
  if (m.Qc != null) {                            // DWL — между D и MC от Qstar до Qc
    const lo = Math.min(Qs, m.Qc), hi = Math.max(Qs, m.Qc);
    if (hi > lo) { const s2 = samp(lo, hi); const aD = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(evalCurve(D, d))); g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)'); }
  }
}

// Ломаный предельный доход MR_eff: горизонталь на уровне Pc до Q̂ + «обрыв» вниз в Q̂.
function drawMonoKinkedMR() {
  const mc = STATE.monoCeil;
  if (!mc || !mc.binding || mc.Qhat == null) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const yPc = sy(mc.Pc);
  g.append('line').attr('x1', sx(0)).attr('y1', yPc).attr('x2', sx(mc.Qhat)).attr('y2', yPc)
    .attr('stroke', COL.MR).attr('stroke-width', 3).attr('stroke-dasharray', '2 2');
  const mrHat = marginalRevenue(STATE.D, mc.Qhat);   // обрыв MR в Q̂ вниз к обычному MR
  if (!isNaN(mrHat)) {
    g.append('line').attr('x1', sx(mc.Qhat)).attr('y1', yPc).attr('x2', sx(mc.Qhat)).attr('y2', sy(Math.max(0, mrHat)))
      .attr('stroke', COL.MR).attr('stroke-width', 1.5).attr('stroke-dasharray', '2 2').attr('opacity', 0.6);
  }
  g.append('text').attr('x', sx(mc.Qhat * 0.4)).attr('y', yPc - 5).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.MR)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('MRэфф = Pc');
}

// Точки при связывающем потолке: новый выпуск M(Qstar, price), призрак M₀(Qm,Pm), полоса дефицита.
function drawMonoCeilingPoints() {
  const mc = STATE.monoCeil, m = STATE.mono;
  if (!mc || !mc.binding || !m) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  // Призрак исходной монополии M₀(Qm, Pm).
  if (STATE.showGhost) {
    const [px0, py0] = toPx(m.Qm, m.Pm);
    g.append('circle').attr('cx', px0).attr('cy', py0).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', px0 + 7).attr('y', py0 - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('M₀');
  }
  // Новый выпуск/цена (Qstar, price).
  if (mc.Qstar > 1e-6) {
    const [pxm, pym] = toPx(mc.Qstar, mc.price);
    dash(pxm, oy, pxm, pym); dash(ox, pym, pxm, pym);
    g.append('circle').attr('cx', pxm).attr('cy', pym).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, pxm, pym, 'M', COL.ink);
    axisValueX(g, pxm, oy, fmt(mc.Qstar), '');
  }
  // Дефицит на оси Q между Qstar и Q̂ (объём спроса при цене Pc).
  if (mc.shortage > 1e-6) {
    const xLo = sx(Math.min(mc.Qstar, mc.Qhat)), xHi = sx(Math.max(mc.Qstar, mc.Qhat));
    g.append('line').attr('x1', xLo).attr('y1', oy).attr('x2', xHi).attr('y2', oy).attr('stroke', COL.bad).attr('stroke-width', 5).attr('opacity', 0.5);
    axisValueX(g, sx(mc.Qhat), oy, fmt(mc.Qhat), 'd');
    haloText(g, (xLo + xHi) / 2, oy + 24, 'Дефицит = ' + fmt(mc.shortage), 'middle', 'hanging');
  }
}

// Перетаскиваемая линия потолка (рисуется всегда, пока тип = потолок и Pc задан).
// Уровень — общий STATE.pReg; перетаскивание — общий attachPcDrag → setPReg.
function drawMonoCeilingLine() {
  if (STATE.intervType !== 'ceiling' || !STATE.pRegSet) return;
  const ox = sx(0), xMax = sx(CONFIG.Qmax), yPc = sy(STATE.pReg);
  const g = svg.append('g');
  g.append('line').attr('x1', ox).attr('y1', yPc).attr('x2', xMax).attr('y2', yPc)
    .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueY(g, ox, yPc, fmt(STATE.pReg), 'c');
  const hit = g.append('rect').attr('x', ox).attr('y', yPc - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  attachPcDrag(hit);
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.72).attr('cy', yPc).attr('r', 7)
    .attr('fill', COL.reg).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

/* ---------------------------------------------------------------------
   БЛОК 8д-2. НАЛОГ / СУБСИДИЯ / ПОЛ ЦЕНЫ В МОНОПОЛИИ (Фаза 2).
   Налог t: MC → MC+t, оптимум MR = MC+t (цена выше, выпуск ниже).
   Субсидия s: MC → MC−s, оптимум MR = MC−s (цена ниже, выпуск выше).
   Пол цены Pf: монополист не может назначать ниже Pf. Если Pm ≥ Pf — не связывает;
   если Pm < Pf — цена поднимается до Pf, выпуск = спрос при цене Pf (ещё ниже Qm).
   Всё численно (как остальная монополия) — работает для любых кривых D и MC.
   --------------------------------------------------------------------- */

// Оптимум монополиста при потоварном налоге/субсидии (shift = +t налог / −s субсидия).
function monopolyTax(shift) {
  const D = STATE.D, m = STATE.mono;
  if (!D || !m) return null;
  const mcEff = (q) => mcAt(q) + shift;                          // MC, сдвинутая на ставку
  const Qt = findRoot(q => marginalRevenue(D, q) - mcEff(q));    // MR = MC ± ставка
  if (Qt == null || !(Qt > 0)) return null;
  const Pt = evalCurve(D, Qt);                                   // цена — с кривой спроса
  const rate = Math.abs(shift), isTax = (shift > 0);
  const budget = (isTax ? 1 : -1) * rate * Qt;                  // +сбор / −расход = ставка·Q
  const csM = integrate(q => evalCurve(D, q) - Pt, 0, Qt);       // CS при новой цене
  /* VC — НАСТОЯЩИЕ издержки ресурсов, под социальной MC: ставка на них не
     влияет. PS — между ФАКТИЧЕСКОЙ границей монополиста (MC+t при налоге,
     MC−s при субсидии) и его ценой: деньги бюджета лежат между MC и MC±ставка
     и в излишек производителя НЕ входят, это перевод, а не излишек.
     Отсюда тождество CS + PS + сбор + DWL = весь общественный излишек
     (при субсидии расход вычитается). */
  const vcM = integrate(q => mcFloor(mcAt(q)), 0, Qt);
  const psM = integrate(q => Pt - mcFloor(mcEff(q)), 0, Qt);
  // DWL — против эффективного выпуска (D = СОЦИАЛЬНАЯ MC, без ставки): вмешательство его увеличивает.
  let dwl = null;
  if (m.Qc != null) { const lo = Math.min(Qt, m.Qc), hi = Math.max(Qt, m.Qc); dwl = areaBetween(q => evalCurve(D, q) - mcFloor(mcAt(q)), lo, hi); }
  return { isTax, shift, rate, Qt, Pt, budget, csM, vcM, psM, dwl, mcAtQt: mcAt(Qt) };
}

// Оптимум монополиста при поле цены Pf (минимальная допустимая цена).
function monopolyFloor(Pf) {
  const D = STATE.D, m = STATE.mono;
  if (!D || !m) return null;
  // Пол не выше монопольной цены — монополист и так выше пола, не связывает.
  if (Pf <= m.Pm + 1e-9) return { binding: false, Pf, Q: m.Qm, price: m.Pm };
  const Q = invCurve(D, Pf);                                     // выпуск = спрос при цене Pf
  if (Q == null || !(Q >= 0)) return { binding: false, Pf, Q: m.Qm, price: m.Pm };
  const price = Pf;
  const csM = integrate(q => evalCurve(D, q) - price, 0, Q);
  const vcM = integrate(q => mcFloor(mcAt(q)), 0, Q);
  const psM = integrate(q => price - mcFloor(mcAt(q)), 0, Q);
  let dwl = null;
  if (m.Qc != null) { const lo = Math.min(Q, m.Qc), hi = Math.max(Q, m.Qc); dwl = areaBetween(q => evalCurve(D, q) - mcFloor(mcAt(q)), lo, hi); }
  return { binding: true, Pf, Q, price, csM, vcM, psM, dwl };
}

/* ---------------------------------------------------------------------
   КВОТА В МОНОПОЛИИ (приёмка владельца 31.08).

   ⚠️ ЭТОГО СЛУЧАЯ ЗДЕСЬ НЕ БЫЛО ВОВСЕ, И ИМЕННО ПОЭТОМУ КВОТА «НЕ РАБОТАЛА».
   Каскад вмешательства в монополии разбирал три вида — налог/субсидию, потолок
   и пол, — а «квота» не совпадала ни с одним, и ветка просто не исполнялась:
   ни расчёта, ни отрисовки, ни строки на табло. Механизм квоты, написанный для
   конкурентного рынка, сюда попасть не мог по другой причине: он опирается на
   кривую предложения S и на равновесие D = S, а в монополии нет ни того, ни
   другого — есть спрос и предельные издержки MC.

   ЭКОНОМИКА СЮЖЕТА.
     • Квота ограничивает выпуск СВЕРХУ и связывает, только если Qk < Qm.
     • Связывающая квота: монополист выпускает ровно Qk и назначает
       МАКСИМАЛЬНУЮ цену, по которой этот объём выбирают, то есть P = D(Qk).
     • ⚠️ КОРИДОРА ЦЕН ЗДЕСЬ НЕТ, и это главное отличие от конкурентного рынка.
       Там цена при квоте не определена однозначно и лежит между S(Qk) и D(Qk),
       потому что назначать её некому. У монополиста есть рыночная власть, и он
       всегда берёт ВЕРХНИЙ край. Ползунок «цена внутри коридора» в монополии не
       появляется — не потому, что его забыли, а потому, что выбирать нечего.
     • Квота монополисту НЕВЫГОДНА: его излишек падает. Если в модели он от
       квоты выигрывает — это знак ошибки, а не открытие.
   --------------------------------------------------------------------- */

// Оптимум монополиста при квоте Qk (верхняя граница выпуска).
// Возвращает { binding, Qk, Q, price, csM, vcM, psM, dwl } либо null.
function monopolyQuota(Qk) {
  const D = STATE.D, m = STATE.mono;
  /* ⚠️ КВОТА НОЛЬ СВЯЗЫВАЕТ, И ОТВЕТ У НЕЁ ЕСТЬ: выпуска нет, излишков нет,
     потери равны всему, что рынок давал раньше. Прежнее `Qk > 0` понимало
     ноль как «квоты не задали» и показывало обычную монополию. */
  if (!D || !m || !(Qk >= 0) || !STATE.quotaSet) return null;
  // Квота не ниже монопольного выпуска — не связывает, всё как без неё.
  if (Qk >= m.Qm - 1e-9) {
    return { binding: false, Qk, Q: m.Qm, price: m.Pm,
             csM: m.csM, vcM: m.vcM, psM: m.psM, dwl: m.dwl };
  }
  const Q = Qk;
  const price = evalCurve(D, Q);          // максимальная цена, по которой берут Qk
  if (isNaN(price)) return null;
  const csM = integrate(q => evalCurve(D, q) - price, 0, Q);
  const vcM = integrate(q => mcFloor(mcAt(q)), 0, Q);
  const psM = integrate(q => price - mcFloor(mcAt(q)), 0, Q);
  /* Потери считаются против ЭФФЕКТИВНОГО выпуска (D = MC), как и у остальных
     видов вмешательства в монополии: квота уводит выпуск дальше от него. */
  let dwl = null;
  if (m.Qc != null) {
    const lo = Math.min(Q, m.Qc), hi = Math.max(Q, m.Qc);
    dwl = areaBetween(q => evalCurve(D, q) - mcFloor(mcAt(q)), lo, hi);
  }
  return { binding: true, Qk, Q, price, csM, vcM, psM, dwl };
}

// Заливки при связывающей квоте: CS/VC/PS до Qk (при цене D(Qk)) + DWL до Qc.
function drawMonoQuotaAreas() {
  const qt = STATE.monoQuota, m = STATE.mono;
  if (!qt || !qt.binding || !m) return;
  const D = STATE.D, g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  if (qt.Q > 1e-6) {
    const s1 = samp(0, qt.Q);
    if (STATE.showMonoVC) { const a = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(mcFloor(mcAt(d)))); g.append('path').datum(s1).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.22).attr('data-legend', 'Переменные издержки (VC)'); }
    if (STATE.showMonoPS) { const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(sy(qt.price)); g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек производителя (TR - VC)'); }
    if (STATE.showMonoCS) { const a = d3.area().x(d => sx(d)).y0(sy(qt.price)).y1(d => sy(evalCurve(D, d))); g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)'); }
  }
  if (m.Qc != null) {
    const lo = Math.min(qt.Q, m.Qc), hi = Math.max(qt.Q, m.Qc);
    if (hi > lo) {
      const s2 = samp(lo, hi);
      const aD = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(evalCurve(D, d)));
      g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
    }
  }
}

// Точки при связывающей квоте: призрак M₀(Qm,Pm) + новый M(Qk, D(Qk)).
function drawMonoQuotaPoints() {
  const qt = STATE.monoQuota, m = STATE.mono;
  if (!qt || !qt.binding || !m) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  if (STATE.showGhost) {
    const [px0, py0] = toPx(m.Qm, m.Pm);
    g.append('circle').attr('cx', px0).attr('cy', py0).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', px0 + 7).attr('y', py0 - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft).attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('M₀');
  }
  if (qt.Q > 1e-6) {
    const [pxm, pym] = toPx(qt.Q, qt.price);
    dash(ox, pym, pxm, pym);
    g.append('circle').attr('cx', pxm).attr('cy', pym).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, pxm, pym, 'M', COL.ink);
    axisValueY(g, ox, pym, fmt(qt.price), '');
  }
}

/* Вертикаль разрешённого объёма — она же сама квота. Рисуется и тогда, когда
   квота НЕ связывает: человек двигает ползунок и должен видеть, где линия
   стоит и почему пока ничего не меняется. */
function drawMonoQuotaLine() {
  if (STATE.intervType !== 'quota' || !STATE.quotaSet) return;
  const oy = sy(0), g = svg.append('g'), xQ = sx(STATE.quota);
  g.append('line').attr('x1', xQ).attr('y1', oy).attr('x2', xQ).attr('y2', sy(CONFIG.Pmax))
    .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueX(g, xQ, oy, fmt(STATE.quota), 'к');
}

/* =====================================================================
   БЛОК 8ж. ЕСТЕСТВЕННАЯ МОНОПОЛИЯ И РЕГУЛИРОВАНИЕ (Фаза 3в).
   Та же база, что у обычной монополии (спрос D + предельные издержки MC),
   плюс постоянные издержки FC. Большие FC делают ATC убывающей — одной фирме
   производить дешевле, чем нескольким (отсюда «естественная»).
   Три ориентира показываются ОДНОВРЕМЕННО:
     1) нерегулируемая монополия  — MR = MC (Qm, Pm), максимум прибыли;
     2) регулирование по предельным издержкам P = MC — эффективный выпуск Qc,
        но цена ниже средних затрат ⇒ убыток, нужна субсидия (ATC−P)·Q;
     3) регулирование по средним издержкам P = ATC — нулевая прибыль
        («второе лучшее»). Уравнение D = ATC может иметь ДВА корня (обе кривые
        убывают) — берём БОЛЬШИЙ, лежащий между Qm и Qc.
   Всё численно: ATC через интеграл MC, корни — сканирование + бисекция.
   ===================================================================== */

// Средние общие издержки: ATC(Q) = (FC + ∫₀^Q MC dq) / Q.
// Интеграл — теми же трапециями, что везде в движке, поэтому работает для любой
// формы MC (при постоянной MC = c даёт привычное ATC = FC/Q + c).
function naturalATC(q) {
  if (!(q > 0)) return NaN;
  const eps = Math.max(1e-9, q * 1e-6);          // страховка: MC в самом нуле может быть NaN
  const m0 = mcAt(eps);
  if (isNaN(m0)) return NaN;
  const vc = integrate(x => mcFloor(mcAt(x)), eps, q, 400) + mcFloor(m0) * eps;
  return isNaN(vc) ? NaN : (STATE.natFC + vc) / q;
}

// НАИБОЛЬШИЙ корень g(Q)=0 на [lo,hi]: идём с правого края и берём первую смену
// знака. Нужен там, где корней может быть два, а осмыслен только правый (D = ATC).
function findRootLast(g, lo, hi) {
  const N = 1000;
  let prevX = hi, prevG = g(hi);
  for (let i = N - 1; i >= 0; i--) {
    const x = lo + (hi - lo) * i / N, cur = g(x);
    if (!isNaN(prevG) && !isNaN(cur) && prevG * cur <= 0 && prevG !== cur) {
      if (prevG === 0) return prevX;
      if (cur === 0) return x;
      return bisect(g, x, prevX);
    }
    prevX = x; prevG = cur;
  }
  return null;
}

function recomputeNatural() {
  STATE.natural = null;
  const D = STATE.D, m = STATE.mono;
  if (!D || !m) return;
  const Qm = m.Qm, Pm = m.Pm, Qc = m.Qc;
  const atcAtQm = naturalATC(Qm);
  const profit = isNaN(atcAtQm) ? null : (Pm - atcAtQm) * Qm;   // прибыль нерегулируемой монополии
  // (2) P = MC — эффективный выпуск = конкурентному Qc; убыток = (ATC − P)·Q = субсидия.
  let mcReg = null;
  if (Qc != null && Qc > 0) {
    const Pmc = mcAt(Qc), atcC = naturalATC(Qc);
    const subsidy = (isNaN(atcC) || isNaN(Pmc)) ? null : (atcC - Pmc) * Qc;
    mcReg = { Q: Qc, P: Pmc, atc: atcC, subsidy };
  }
  // (3) P = ATC — ищем корень D − ATC СПРАВА, в окне [Qm, Qc]: там разность
  // меняет знак с «+» (монополия прибыльна) на «−» (при Qc она в убытке).
  let acReg = null, acNote = null;
  if (Qc != null && Qc > Qm) {
    const g = (q) => { const d = evalCurve(D, q), a = naturalATC(q); return (isNaN(d) || isNaN(a)) ? NaN : d - a; };
    const Qac = findRootLast(g, Qm, Qc);
    if (Qac != null) acReg = { Q: Qac, P: evalCurve(D, Qac), atc: naturalATC(Qac) };
    else acNote = (g(Qm) < 0)
      ? 'При таких FC монополия убыточна даже в своей лучшей точке, поэтому цены по средним издержкам не существует.'
      : 'Пересечение D = ATC между Qm и Qc не найдено.';
  }
  STATE.natural = { Qm, Pm, atcAtQm, profit, mcReg, acReg, acNote, FC: STATE.natFC };
}

// Заливки: прибыль монополии (Pm − ATC(Qm))·Qm и убыток при P = MC (ATC − P)·Qc.
function drawNaturalAreas() {
  const n = STATE.natural; if (!n) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const rect = (q, yLo, yHi, color, op) => {
    if (!(q > 0) || isNaN(yLo) || isNaN(yHi)) return;
    g.append('rect').attr('x', sx(0)).attr('y', sy(Math.max(yLo, yHi)))
      .attr('width', sx(q) - sx(0)).attr('height', Math.abs(sy(Math.min(yLo, yHi)) - sy(Math.max(yLo, yHi))))
      .attr('fill', color).attr('opacity', op);
  };
  if (STATE.showNatProfit && n.profit != null && n.profit > 0) rect(n.Qm, n.atcAtQm, n.Pm, COL.tax, 0.20);
  if (STATE.showNatLoss && n.mcReg && n.mcReg.subsidy != null && n.mcReg.subsidy > 0)
    rect(n.mcReg.Q, n.mcReg.P, n.mcReg.atc, COL.bad, 0.18);
}

// Кривые: ATC (янтарная — «ориентир регулятора») и обычный падающий MR.
function drawNaturalCurves() {
  const D = STATE.D; if (!D) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const sample = (f, q0) => {
    const pts = [], a = q0 || 0;
    for (let i = 0; i <= 400; i++) { const q = a + (CONFIG.Qmax - a) * i / 400; const v = f(q); pts.push((isNaN(v) || v > CONFIG.Pmax * 4) ? null : [q, v]); }
    return pts;
  };
  drawMarginalCurve(g, q => marginalRevenue(D, q), D, COL.MR, { width: 2, cap: CONFIG.Pmax * 4 });
  g.append('path').datum(sample(naturalATC, CONFIG.Qmax * 0.005))
    .attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2.5).attr('d', line);
  // ATC естественной монополии круто уходит вверх у нуля — ярлык ищем по
  // видимому участку (Фаза 3), а не на фиксированной точке.
  labelCurve(g, naturalATC, 'ATC', COL.reg, { from: 0.93 });
}

// Три вертикальных ориентира: M (монополия), MC (цена по предельным
// издержкам), AC (цена по средним). Расшифровка — в панели расчётов.
function drawNaturalPoints() {
  const n = STATE.natural; if (!n) return;
  const oy = sy(0), ox = sx(0), g = svg.append('g');
  const mark = (Q, P, label, color, side, idx) => {
    if (Q == null || !(Q > 0) || isNaN(P)) return;
    const px = sx(Q), py = sy(P);
    g.append('line').attr('x1', px).attr('y1', oy).attr('x2', px).attr('y2', py)
      .attr('stroke', color).attr('stroke-width', 1.2).attr('stroke-dasharray', '4 3').attr('opacity', 0.85);
    g.append('line').attr('x1', ox).attr('y1', py).attr('x2', px).attr('y2', py)
      .attr('stroke', color).attr('stroke-width', 1).attr('stroke-dasharray', '4 3').attr('opacity', 0.55);
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5)
      .attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    /* Правило 47: на холсте только обозначение. Что это за ориентир —
       говорит панель «Естественная монополия», а не подпись у точки. */
    pointName(g, px, py, label, color,
              { dx: side < 0 ? -9 : 9, dy: -9, size: FS.base, weight: 700 })
      .attr('text-anchor', side < 0 ? 'end' : 'start');
    axisValueX(g, px, oy, fmt(Q), idx || '');
    /* Пунктир шёл и к оси цены, а числа там не было: линия упиралась в пустоту.
       Различитель обязателен — на оси цены встают ТРИ разные цены: монопольная
       и два ориентира регулирования. */
    axisValueY(g, ox, py, fmt(P), idx || '');
  };
  mark(n.Qm, n.Pm, 'M', COL.ink, -1, 'm');
  if (n.acReg) mark(n.acReg.Q, n.acReg.P, 'E_{ATC}', COL.reg, 1, 'ATC');
  if (n.mcReg) mark(n.mcReg.Q, n.mcReg.P, 'E_{MC}', COL.MC, -1, 'MC');
}

// Полная отрисовка под-режима «Естественная монополия».
function drawNaturalFull() {
  drawNaturalAreas();
  drawCurves();          // спрос D и предельные издержки MC из списка кривых
  drawNaturalCurves();   // MR и ATC
  drawNaturalPoints();
}

// Табло естественной монополии: три ориентира и вывод о компромиссе регулятора.
function updateNaturalPanel() {
  const box = document.getElementById('info-nat'); if (!box) return;
  if (!STATE.D) { box.innerHTML = '<div class="muted">Отметьте кривую спроса (роль D).</div>'; return; }
  if (!mcSourceCurve() && !curveByRole('tc')) {
    box.innerHTML = '<div class="muted">Нужны предельные издержки: роль MC (либо TC, либо S как MC).</div>'; return;
  }
  const n = STATE.natural;
  if (!n) { box.innerHTML = '<div class="warn">Оптимум монополии не найден. Проверьте кривые.</div>'; return; }
  let html = `<div class="stat"><span>Постоянные издержки FC</span><b>${fmt(n.FC)}</b></div>`;
  html += `<div class="stat"><span>M · монополия: ($Q$; $P$)</span><b>(${fmt(n.Qm)}; ${fmt(n.Pm)})</b></div>`;
  if (!isNaN(n.atcAtQm)) html += `<div class="stat"><span>&nbsp;&nbsp;&nbsp;(ATC(Qm); прибыль)</span><b>(${fmt(n.atcAtQm)}; ${fmt(n.profit)})</b></div>`;
  if (n.mcReg) {
    html += `<div class="stat" style="margin-top:4px;"><span>$E_{MC}$ · цена $P = MC$: $Q$ / $P$</span><b>${fmt(n.mcReg.Q)} / ${fmt(n.mcReg.P)}</b></div>`;
    html += `<div class="stat"><span>&nbsp;&nbsp;&nbsp;ATC на этом Q</span><b>${fmt(n.mcReg.atc)}</b></div>`;
    if (n.mcReg.subsidy != null) html += `<div class="stat"><span>&nbsp;&nbsp;&nbsp;Нужна субсидия</span><b>${fmt(n.mcReg.subsidy)}</b></div>`;
  }
  if (n.acReg) {
    html += `<div class="stat" style="margin-top:4px;"><span>$E_{ATC}$ · цена $P = ATC$: $Q$ / $P$</span><b>${fmt(n.acReg.Q)} / ${fmt(n.acReg.P)}</b></div>`;
    html += `<div class="stat"><span>&nbsp;&nbsp;&nbsp;Прибыль</span><b>0</b></div>`;
  } else if (n.acNote) {
    html += `<div class="warn" style="margin-top:4px;">${n.acNote}</div>`;
  }
  html += '<div class="hint" style="margin-top:6px;">Компромисс регулятора: цена по предельным издержкам эффективна, ' +
    'но при убывающей ATC даёт фирме убыток (нужна субсидия из бюджета). Цена по средним издержкам ' +
    'обходится без субсидии, но выпуск меньше эффективного, поэтому часть выигрыша теряется.</div>';
  box.innerHTML = html;
}

/* Заливки при налоге/субсидии: VC, PS, CS, полоса денег бюджета и DWL.

   ⚠️ VC и PS ЗДЕСЬ РАНЬШЕ НЕ РИСОВАЛИСЬ ВОВСЕ, хотя галочки «Показывать VC» и
   «Показывать PS» стояли и работали в соседних сюжетах (квота, пол цены).
   Порядок фигур снизу вверх ПРИ НАЛОГЕ: VC (0…MC), полоса сбора (MC…MC+t),
   PS (MC+t…цена), CS (цена…спрос) — они не накладываются.
   ПРИ СУБСИДИИ полоса расхода лежит НИЖЕ кривой MC, между MC−s и MC, то есть
   внутри PS и внутри VC: субсидия и есть часть выигрыша производителя, за
   которую заплатил бюджет. Поэтому полоса денег рисуется ПОСЛЕДНЕЙ — иначе
   при субсидии её накрыла бы заливка PS. */
function drawMonoTaxAreas() {
  const t = STATE.monoTax, m = STATE.mono;
  if (!t || !m) return;
  const D = STATE.D, g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const mcEff = (d) => mcAt(d) + t.shift;      // фактическая граница монополиста
  if (t.Qt > 1e-6) {
    const s1 = samp(0, t.Qt);
    // VC — под СОЦИАЛЬНОЙ MC: издержки ресурсов настоящие, ставка их не меняет.
    if (STATE.showMonoVC) {
      const a = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(mcFloor(mcAt(d))));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.22).attr('data-legend', 'Переменные издержки (VC)');
    }
    // PS — между фактической границей (MC ± ставка) и ценой монополиста.
    if (STATE.showMonoPS) {
      const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcEff(d)))).y1(sy(t.Pt));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек производителя (TR - VC)');
    }
    if (STATE.showMonoCS) {   // CS — между ценой Pt (низ) и спросом (верх)
      const a = d3.area().x(d => sx(d)).y0(sy(t.Pt)).y1(d => sy(evalCurve(D, d)));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
    }
    // Деньги бюджета — полоса между MC и MC±ставка на [0,Qt]; её площадь = ставка·Qt = бюджет.
    const a2 = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(mcFloor(mcEff(d))));
    g.append('path').datum(s1).attr('d', a2).attr('fill', COL.tax).attr('opacity', 0.22).attr('data-legend', STATE.intervType === 'subsidy' ? 'Расход бюджета' : 'Сбор бюджета');
  }
  // DWL — между D и социальной MC от Qt до конкурентного Qc.
  if (m.Qc != null) {
    const lo = Math.min(t.Qt, m.Qc), hi = Math.max(t.Qt, m.Qc);
    if (hi > lo) { const s2 = samp(lo, hi); const aD = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(evalCurve(D, d))); g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)'); }
  }
}

// Пунктирная сдвинутая кривая MC ± ставка (как drawShiftedSupply для конкуренции).
function drawMonoTaxShiftedMC() {
  const t = STATE.monoTax;
  if (!t) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const pts = [];
  for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = mcAt(q) + t.shift; pts.push(isNaN(v) ? null : [q, v]); }
  g.append('path').datum(pts).attr('fill', 'none').attr('stroke', COL.MC).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
  // Подпись сдвинутой кривой.
  const qLab = CONFIG.Qmax * 0.62, vLab = mcAt(qLab) + t.shift;
  if (!isNaN(vLab) && vLab > 0) g.append('text').attr('x', sx(qLab)).attr('y', sy(vLab) - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.MC)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(t.isTax ? 'MC+t' : 'MC−s');
}

// Точки при налоге/субсидии: призрак M₀(Qm,Pm) + новый M(Qt,Pt) с проекциями.
function drawMonoTaxPoints() {
  const t = STATE.monoTax, m = STATE.mono;
  if (!t || !m) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  if (STATE.showGhost) {
    const [px0, py0] = toPx(m.Qm, m.Pm);
    g.append('circle').attr('cx', px0).attr('cy', py0).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', px0 + 7).attr('y', py0 - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft).attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('M₀');
  }
  if (t.Qt > 1e-6) {
    const [pxm, pym] = toPx(t.Qt, t.Pt);
    dash(pxm, oy, pxm, pym); dash(ox, pym, pxm, pym);
    g.append('circle').attr('cx', pxm).attr('cy', pym).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, pxm, pym, 'M', COL.ink);
    axisValueX(g, pxm, oy, fmt(t.Qt), '');
    axisValueY(g, ox, pym, fmt(t.Pt), '');
  }
}

// Заливки при связывающем поле цены: CS/VC/PS до Q + DWL.
function drawMonoFloorAreas() {
  const fl = STATE.monoFloor, m = STATE.mono;
  if (!fl || !fl.binding || !m) return;
  const D = STATE.D, g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  if (fl.Q > 1e-6) {
    const s1 = samp(0, fl.Q);
    if (STATE.showMonoVC) { const a = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(mcFloor(mcAt(d)))); g.append('path').datum(s1).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.22).attr('data-legend', 'Переменные издержки (VC)'); }
    if (STATE.showMonoPS) { const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(sy(fl.price)); g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек производителя (TR - VC)'); }
    if (STATE.showMonoCS) { const a = d3.area().x(d => sx(d)).y0(sy(fl.price)).y1(d => sy(evalCurve(D, d))); g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)'); }
  }
  if (m.Qc != null) { const lo = Math.min(fl.Q, m.Qc), hi = Math.max(fl.Q, m.Qc); if (hi > lo) { const s2 = samp(lo, hi); const aD = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(evalCurve(D, d))); g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)'); } }
}

// Точки при связывающем поле: призрак M₀(Qm,Pm) + новый M(Q, Pf).
function drawMonoFloorPoints() {
  const fl = STATE.monoFloor, m = STATE.mono;
  if (!fl || !fl.binding || !m) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  if (STATE.showGhost) {
    const [px0, py0] = toPx(m.Qm, m.Pm);
    g.append('circle').attr('cx', px0).attr('cy', py0).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', px0 + 7).attr('y', py0 - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft).attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('M₀');
  }
  if (fl.Q > 1e-6) {
    const [pxm, pym] = toPx(fl.Q, fl.price);
    dash(pxm, oy, pxm, pym); dash(ox, pym, pxm, pym);
    g.append('circle').attr('cx', pxm).attr('cy', pym).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(g, pxm, pym, 'M', COL.ink);
    axisValueX(g, pxm, oy, fmt(fl.Q), '');
  }
}

// Перетаскиваемая линия пола цены Pf (общий STATE.pReg, перетаскивание attachPcDrag → setPReg).
function drawMonoFloorLine() {
  if (STATE.intervType !== 'floor' || !STATE.pRegSet) return;
  const ox = sx(0), xMax = sx(CONFIG.Qmax), yPf = sy(STATE.pReg);
  const g = svg.append('g');
  g.append('line').attr('x1', ox).attr('y1', yPf).attr('x2', xMax).attr('y2', yPf)
    .attr('stroke', COL.MR).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueY(g, ox, yPf, fmt(STATE.pReg), 'f');
  const hit = g.append('rect').attr('x', ox).attr('y', yPf - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  attachPcDrag(hit);
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.72).attr('cy', yPf).attr('r', 7)
    .attr('fill', COL.MR).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

// Табло вмешательства в монополии (info-tax): налог / субсидия / потолок / пол.
function updateMonoInterventionPanel() {
  /* П12, та же оговорка, что у конкурентного рынка: блок говорит только там,
     где его инструмент есть. Естественная монополия и обе дискриминации
     запирают блок вмешательства (SCENE_ROUTE.lock), и подсказка «двигайте
     ставку» обещала бы ползунок, которого на экране нет. */
  {
    const _sec = document.getElementById(L_INTERV);
    const _box = document.getElementById('info-tax');
    if (_sec && _box && _sec.classList.contains('scoped-off')) { _box.innerHTML = ''; return; }
  }
  const box = document.getElementById('info-tax');
  if (!box) return;
  if (STATE.monoMode !== 'simple') { box.innerHTML = '<div class="muted">Вмешательство государства доступно в режиме «Обычная» монополия.</div>'; return; }
  if (!STATE.mono) { box.innerHTML = '<div class="muted">Нужны спрос (роль D) и предельные издержки (роль MC / S / TC).</div>'; return; }
  const m = STATE.mono, it = STATE.intervType;
  if (it === 'tax' || it === 'subsidy') {
    const isSub = (it === 'subsidy');
    if (!STATE.monoTax || !(STATE.tax > 0)) {
      box.innerHTML = `<div class="muted">Двигайте ставку: ${isSub ? 'субсидия снизит MC' : 'налог поднимет MC'}; новый оптимум: MR = MC ${isSub ? '−' : '+'} ставка.</div>`;
      return;
    }
    const t = STATE.monoTax;
    const rows = [
      ['Q', m.Qm, t.Qt],
      ['P (цена)', m.Pm, t.Pt],
      [isSub ? 'Бюджет (расход)' : 'Бюджет (сбор)', 0, t.budget],
      ['CS', m.csM, t.csM],
      ['PS', m.psM, t.psM],
      ['VC', m.vcM, t.vcM],
      ['DWL', m.dwl, t.dwl],
    ];
    let html = `<div class="stat"><span>${isSub ? 'Субсидия s' : 'Налог t'}</span><b>${fmt(STATE.tax)}</b></div>`;
    html += '<table class="tx-table"><tr><th></th><th>Было</th><th>Стало</th><th>Δ</th></tr>';
    rows.forEach(([k, a, b]) => { if (a == null || b == null) return; const d = b - a, ds = (d > 0 ? '+' : '') + fmt(d); html += `<tr><td>${k}</td><td>${fmt(a)}</td><td>${fmt(b)}</td><td>${ds}</td></tr>`; });
    html += '</table>';
    html += `<div class="hint" style="margin-top:6px;">${isSub ? 'Субсидия снижает предельные издержки: выпуск растёт, цена падает.' : 'Налог поднимает предельные издержки: выпуск падает, цена растёт, потери (DWL) увеличиваются.'}</div>`;
    box.innerHTML = html;
    return;
  }
  if (it === 'ceiling') {
    const mc = STATE.monoCeil;
    if (!mc || !STATE.pRegSet) { box.innerHTML = '<div class="muted">Двигайте линию/ползунок цены, чтобы задать потолок Pc.</div>'; return; }
    if (!mc.binding) { box.innerHTML = `<div class="warn">Потолок Pc=${fmt(mc.Pc)} не ниже монопольной цены (Pm=${fmt(m.Pm)}), поэтому не связывает.</div>`; return; }
    let html = `<div class="stat"><span>Потолок Pc</span><b>${fmt(mc.Pc)}</b></div>`;
    html += `<div class="stat"><span>Выпуск</span><b>${fmt(mc.Qstar)} (было ${fmt(m.Qm)})</b></div>`;
    html += `<div class="stat"><span>Цена</span><b>${fmt(mc.price)} (было ${fmt(m.Pm)})</b></div>`;
    if (mc.shortage > 1e-6) html += `<div class="stat"><span>Дефицит</span><b>${fmt(mc.shortage)}</b></div>`;
    if (mc.dwl != null) html += `<div class="stat"><span>$DWL$</span><b>${fmt(mc.dwl)} (было ${fmt(m.dwl)})</b></div>`;
    const dq = mc.Qstar - m.Qm;
    html += `<div class="hint" style="margin-top:6px;">${dq > 1e-6 ? 'Грамотный потолок увеличил выпуск (парадокс монополии).' : (dq < -1e-6 ? 'Слишком низкий потолок: выпуск упал, возник дефицит.' : 'Выпуск не изменился.')}</div>`;
    box.innerHTML = html;
    return;
  }
  if (it === 'quota') {
    const qt = STATE.monoQuota;
    /* ⚠️ РАЗБОР ПРО ОТСУТСТВИЕ КОРИДОРА СТОИТ ЗДЕСЬ, А НЕ В ПОДСКАЗКЕ, И
       ВЫВОДИТСЯ ВСЕГДА, ПОКА ВЫБРАНА КВОТА. Класс `sb-note` уносит его в
       «Объяснение модели» (moveExplanations). Без этих слов ученик, знакомый
       с квотой на конкурентном рынке, решит, что коридор просто забыли
       нарисовать, — указание владельца 31.08. */
    const why = '<div class="sb-note"><b>Как это получилось</b>'
      + '<p><b>Почему у квоты в монополии НЕТ коридора цен?</b> На конкурентном рынке '
      + 'цену не назначает никто, поэтому при квоте она не определена однозначно и может '
      + 'стоять где угодно между $S(Q_к)$ и $D(Q_к)$: этот промежуток и рисуется коридором. '
      + 'У монополиста рыночная власть: цену назначает он сам и всегда берёт ВЕРХНИЙ край, '
      + 'то есть максимальную цену, по которой разрешённый объём ещё выбирают, $P = D(Q_к)$. '
      + 'Выбирать не из чего, поэтому ползунка цены здесь нет. Его не забыли.</p>'
      + '<p><b>Выгодна ли квота монополисту?</b> Нет. Он и без неё выпускал ровно столько, '
      + 'сколько считал выгодным; запрет может только помешать. Излишек производителя падает, '
      + 'потери общества растут: квота ниже монопольного выпуска уводит рынок ЕЩЁ ДАЛЬШЕ от '
      + 'эффективного объёма, а не приближает к нему.</p></div>';
    if (!qt || !STATE.quotaSet) {
      box.innerHTML = '<div class="muted">Двигайте ползунок квоты $Q_к$: она ограничивает выпуск сверху. '
        + 'Связывает, только если ниже монопольного выпуска.</div>' + why;
      return;
    }
    if (!qt.binding) {
      box.innerHTML = `<div class="warn">Квота Q<sub>к</sub>=${fmt(qt.Qk)} не ниже монопольного выпуска `
        + `(Q<sub>m</sub>=${fmt(m.Qm)}), поэтому не связывает: монополист и так выпускает меньше.</div>` + why;
      return;
    }
    const rows = [
      ['Q (выпуск)', m.Qm, qt.Q],
      ['P (цена)', m.Pm, qt.price],
      ['CS', m.csM, qt.csM],
      ['PS', m.psM, qt.psM],
      ['DWL', m.dwl, qt.dwl],
    ];
    let html = `<div class="stat"><span>Квота $Q_к$</span><b>${fmt(qt.Qk)}</b></div>`;
    html += '<table class="tx-table"><tr><th></th><th>Было</th><th>Стало</th><th>Δ</th></tr>';
    rows.forEach(([k, a, b]) => {
      if (a == null || b == null) return;
      const d = b - a, ds = (d > 0 ? '+' : '') + fmt(d);
      html += `<tr><td>${k}</td><td>${fmt(a)}</td><td>${fmt(b)}</td><td>${ds}</td></tr>`;
    });
    html += '</table>';
    html += '<div class="hint" style="margin-top:6px;">Выпуск падает до квоты, цена растёт до '
          + 'спроса при этом объёме. Коридора цен нет: монополист назначает цену сам и берёт '
          + 'верхний край. Его излишек при этом ПАДАЕТ: квота монополисту невыгодна.</div>';
    box.innerHTML = html + why;
    return;
  }
  if (it === 'floor') {
    const fl = STATE.monoFloor;
    if (!fl || !STATE.pRegSet) { box.innerHTML = '<div class="muted">Двигайте линию/ползунок цены, чтобы задать пол Pf.</div>'; return; }
    if (!fl.binding) { box.innerHTML = `<div class="warn">Пол Pf=${fmt(fl.Pf)} не выше монопольной цены (Pm=${fmt(m.Pm)}), поэтому не связывает.</div>`; return; }
    let html = `<div class="stat"><span>Пол Pf</span><b>${fmt(fl.Pf)}</b></div>`;
    html += `<div class="stat"><span>Цена</span><b>${fmt(fl.price)} (было ${fmt(m.Pm)})</b></div>`;
    html += `<div class="stat"><span>Выпуск</span><b>${fmt(fl.Q)} (было ${fmt(m.Qm)})</b></div>`;
    if (fl.dwl != null) html += `<div class="stat"><span>$DWL$</span><b>${fmt(fl.dwl)} (было ${fmt(m.dwl)})</b></div>`;
    html += '<div class="hint" style="margin-top:6px;">Пол выше монопольной цены заставляет поднять цену ещё выше; выпуск падает (определяется спросом при поле).</div>';
    box.innerHTML = html;
    return;
  }
  box.innerHTML = '';
}

/* =====================================================================
   БЛОК 8е. ПОД-РЕЖИМЫ МОНОПОЛИИ (Чекпоинт 2) — внутри структуры «Монополия».
   monoMode: 'simple' (как раньше, не трогаем) | 'discr1' (ценовая дискриминация
   1-й степени) | 'discr3' (3-й степени, два рынка) | 'kinked' (ломаный спрос).
   Переиспользуем существующие численные методы (findRoot / findRootIn / integrate /
   marginalRevenue / mcAt / invCurve). Каждый под-режим самодостаточен.
   ===================================================================== */

// Построить «кривую» из произвольной формулы (число или f(Q)) — пригодна для evalCurve.
function makeCurve(expr) {
  const { compiled, error } = compileFormula((expr || '').trim());
  if (error) return { error };
  return { compiled, linear: detectLinear(compiled), error: null };
}

/* --- Задача 4: ценовая дискриминация 1-й степени --- */

// Отрисовка: D и MC, вся область между ними до Qcomp = прибыль (CS=0, DWL=0).
function drawDiscr1() {
  const D = STATE.D, d1 = STATE.discr1;
  drawCurves();                         // спрос D и (если задана как кривая) MC
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  // Если MC выведена из TC (нет кривой mc/S) — нарисуем её красным.
  if (!mcSourceCurve() && curveByRole('tc')) {
    const pts = []; for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = mcAt(q); pts.push(isNaN(v) ? null : [q, v]); }
    g.append('path').datum(pts).attr('fill', 'none').attr('stroke', COL.S).attr('stroke-width', 2.5).attr('d', line);
  }
  if (!d1) return;
  /* Заливка прибыли — между MC (низ) и D (верх) от 0 до Qcomp.
     ⚠️ Низ — max(0, MC), а не сама MC: при MC, пересекающей ось P ниже нуля,
     заливка уезжала вместе с кривой в четвёртую четверть. Ровно то же
     ограничение стоит у ЧИСЛА прибыли в recompute — поправить одно без
     другого значит развести картинку с числом. */
  const samp = []; for (let i = 0; i <= 120; i++) samp.push(d1.Qcomp * i / 120);
  const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcAt(d)))).y1(d => sy(evalCurve(D, d)));
  g.append('path').datum(samp).attr('d', a).attr('fill', COL.tax).attr('opacity', 0.20).attr('data-legend', 'Излишек фирмы: весь излишек рынка');
  // Точка Qcomp на спросе + проекции.
  const ox = sx(0), oy = sy(0), Pq = evalCurve(D, d1.Qcomp);
  const og = svg.append('g'), [px, py] = toPx(d1.Qcomp, Pq);
  og.append('line').attr('x1', px).attr('y1', py).attr('x2', px).attr('y2', oy).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  og.append('circle').attr('cx', px).attr('cy', py).attr('r', 4).attr('fill', COL.tax).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  axisValueX(og, px, oy, fmt(d1.Qcomp), 'comp');
  haloText(og, sx(d1.Qcomp * 0.45), sy(Math.max(0, (Pq + mcAt(d1.Qcomp * 0.45)) / 2)), 'Прибыль', 'middle', 'middle');
}

function updateDiscr1Panel() {
  const box = document.getElementById('info-mono'); if (!box) return;
  if (!STATE.D) { box.innerHTML = '<div class="muted">Отметьте кривую спроса (роль D).</div>'; return; }
  if (!mcSourceCurve() && !curveByRole('tc')) { box.innerHTML = '<div class="muted">Нужны предельные издержки: роль MC (либо TC, либо S как MC).</div>'; return; }
  const d1 = STATE.discr1;
  if (!d1) { box.innerHTML = '<div class="warn">Точка D = MC не найдена в первой четверти.</div>'; return; }
  let html = '';
  html += `<div class="stat"><span>Выпуск (= конкурентному)</span><b>${fmt(d1.Qcomp)}</b></div>`;
  html += `<div class="stat"><span>Прибыль (весь излишек)</span><b>${fmt(d1.profit)}</b></div>`;
  html += `<div class="stat"><span>$CS$ (потребитель)</span><b>0</b></div>`;
  html += `<div class="stat"><span>$DWL$ (потери)</span><b>0</b></div>`;
  // Сравнение с простой монополией (STATE.mono считается в recompute параллельно).
  if (STATE.mono) {
    html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
    html += `<div class="stat"><span>Простая монополия: Qm</span><b>${fmt(STATE.mono.Qm)}</b></div>`;
    html += `<div class="stat"><span>Простая монополия: излишек (TR−VC)</span><b>${fmt(STATE.mono.psM)}</b></div>`;
    if (STATE.mono.dwl != null) html += `<div class="stat"><span>Простая монополия: DWL</span><b>${fmt(STATE.mono.dwl)}</b></div>`;
  }
  html += '<div class="hint">Совершенная дискриминация: выпуск растёт до конкурентного, потерь нет, но весь излишек у фирмы.</div>';
  box.innerHTML = html;
}

/* --- Задача 5: ценовая дискриминация 3-й степени (два рынка) --- */

// Распределение выпуска Qtot между рынками так, что MR₁ = MR₂ (бисекция: h убывает по q1).
function allocateMR(c1, c2, Qtot) {
  const h = (q1) => { const a = marginalRevenue(c1, q1), b = marginalRevenue(c2, Qtot - q1); return (isNaN(a) || isNaN(b)) ? NaN : a - b; };
  const flo = h(1e-9); if (isNaN(flo)) return 0;
  const fhi = h(Qtot - 1e-9);
  if (!(flo > 0)) return 0;            // MR₁ уже ≤ MR₂ → весь выпуск на рынок 2
  if (!(fhi < 0)) return Qtot;         // MR₁ всё ещё ≥ MR₂ → весь выпуск на рынок 1
  let lo = 0, hi = Qtot;
  for (let k = 0; k < 80; k++) { const mid = (lo + hi) / 2, fm = h(mid); if (Math.abs(fm) < 1e-7) return mid; if (fm > 0) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}

// Пересчёт дискриминации 3-й степени: сканируем суммарный Q, на каждом делим по MR₁=MR₂,
// общий MR (max активной отрасли) приравниваем к MC(Qtot). Работает для const и f(Q) MC.
function recomputeDiscr3() {
  STATE.discr3 = null;
  const errBox = document.getElementById('d3-error');
  const c1 = makeCurve(STATE.d3D1), c2 = makeCurve(STATE.d3D2), cm = makeCurve(STATE.d3MC);
  if (c1.error || c2.error || cm.error) { if (errBox) { errBox.style.display = 'block'; errBox.textContent = 'Не понял формулу: ' + (c1.error || c2.error || cm.error); } return; }
  if (errBox) errBox.style.display = 'none';
  const mc = (q) => evalCurve(cm, q);
  const commonMR = (Qtot) => {
    const q1 = allocateMR(c1, c2, Qtot);
    const m1 = marginalRevenue(c1, q1), m2 = marginalRevenue(c2, Qtot - q1);
    return Math.max(isNaN(m1) ? -Infinity : m1, isNaN(m2) ? -Infinity : m2);   // MR следующей единицы (в лучшем рынке)
  };
  const Qtot = findRootIn((Q) => commonMR(Q) - mc(Q), 1e-6, 2 * CONFIG.Qmax);
  if (Qtot == null || !(Qtot > 0)) {
    /* ⚠️ «ОБЩЕГО ВЫПУСКА НЕТ» НЕ ЗНАЧИТ «ОТВЕТА НЕТ». Если предельные издержки
       нигде не дорастают до мировой цены, выгодна любая лишняя единица, и
       суммарный выпуск действительно не ограничен. Но ВНУТРЕННИЙ рынок при
       этом совершенно обычный: альтернативная стоимость домашней единицы —
       это Pw, по которой её можно было продать за границу, поэтому дома
       продаётся столько, что MR внутри = Pw. Раньше эта ветка не считала
       ничего, и сцена оставалась без обеих панелей. */
    let ub = null;
    if (STATE.d3World) {
      const Pw = evalCurve(c2, 0);                     // мировая цена = уровень горизонтального спроса
      const mcFar = evalCurve(cm, 2 * CONFIG.Qmax);    // куда дорастают предельные издержки
      if (!isNaN(Pw) && !isNaN(mcFar) && mcFar < Pw) {
        const q1 = findRootIn(q => marginalRevenue(c1, q) - Pw, 1e-9, 2 * CONFIG.Qmax);
        const has = (q1 != null && q1 > 0);
        ub = { Pw, q1: has ? q1 : 0, P1: has ? evalCurve(c1, q1) : NaN };
      }
    }
    STATE.discr3 = { c1, c2, cm, found: false, unbounded: ub };
    return;
  }
  const q1 = allocateMR(c1, c2, Qtot), q2 = Qtot - q1;
  const P1 = evalCurve(c1, q1), P2 = evalCurve(c2, q2), mcLevel = mc(Qtot);
  STATE.discr3 = { c1, c2, cm, found: true, Qtot, q1, q2, P1, P2, mcLevel };
}

// Мини-график одного рынка в пиксельной полосе [gx0, gx1]: D, MR, MC и точка (qi, Pi).
function drawMiniMarket(gx0, gx1, title, D, qi, Pi, mcCurve, idx) {
  // mt=64: заголовок панели печатается на 12px выше её верха, а сверху слева
  // висит шапка сцены («← Сценарии», до 44px) — с прежними 30 они накладывались.
  const ml = 46, mr = 18, mt = 64, mb = 42;
  const left = gx0 + ml, right = gx1 - mr, top = mt, bottom = H - mb;
  if (right <= left || bottom <= top) return;
  let Xmax = invCurve(D, 0); if (Xmax == null || !(Xmax > 0)) Xmax = CONFIG.Qmax; Xmax = padMax(Xmax);
  let Ymax = evalCurve(D, 0); if (isNaN(Ymax) || !(Ymax > 0)) Ymax = CONFIG.Pmax; Ymax = padMax(Ymax);
  /* Окно панели: своё, пока человек его не покрутил. Тронул колесом — окно
     стало ЕГО, и подгонка под кривую отступает (то же правило, что у
     STATE.zoomLock у главной панели). У горизонтальной мировой цены своего
     масштаба нет вовсе, и раньше эта панель откатывалась к CONFIG — из-за
     чего колесо над ЛЕВОЙ панелью меняло ПРАВУЮ. */
  const wnd = panelWin('mini-' + idx, 0, Xmax, 0, Ymax);
  Xmax = wnd.x1;
  const lx = d3.scaleLinear().domain([wnd.x0, wnd.x1]).range([left, right]);
  const ly = d3.scaleLinear().domain([wnd.y0, wnd.y1]).range([bottom, top]);
  // Мини-рынок — самостоятельная панель со своими шкалами (реестр чистит
  // redrawDiscr3 перед первым из двух вызовов).
  registerPanel('mini-' + idx, lx, ly, { x0: left, y0: top, x1: right, y1: bottom });
  const g = svg.append('g');
  drawGrid(lx, ly, g);               // у мини-рынка свои шкалы — сетку считаем по ним
  const cid = 'mini-clip-' + idx;
  svg.select('defs').append('clipPath').attr('id', cid).append('rect').attr('x', left).attr('y', top).attr('width', right - left).attr('height', bottom - top);
  // Оси.
  g.append('line').attr('x1', left).attr('y1', bottom).attr('x2', right).attr('y2', bottom).attr('stroke', COL.ink).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
  g.append('line').attr('x1', left).attr('y1', bottom).attr('x2', left).attr('y2', top).attr('stroke', COL.ink).attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)');
  /* Заголовок панели зажимается внутрь холста: «Экспорт по мировой цене»
     шире своей половины, и на узком окне уезжал за правый край. */
  const tw = measureText(title, FS.base, 600);
  const tx = Math.max(tw / 2 + 2, Math.min(W - tw / 2 - 2, (left + right) / 2));
  g.append('text').attr('x', tx).attr('y', top - 12).attr('text-anchor', 'middle').attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.ink).text(title);
  g.append('text').attr('x', right + 4).attr('y', bottom + 4).attr('font-size', FS.base).attr('fill', COL.inkSoft).text('Q');
  g.append('text').attr('x', left - 4).attr('y', top - 2).attr('text-anchor', 'end').attr('font-size', FS.base).attr('fill', COL.inkSoft).text('P');
  /* ⚠️ ДЕЛЕНИЕ УСТУПАЕТ МЕСТО ЧИСЛУ ТОЧКИ, И РЕШАЕТСЯ ЭТО В ДАННЫХ.

     Пока у координаты стоял префикс («q=15»), она была шире деления и вставала
     рядом. Оставшись голым числом (фаза 5), она села к делениям вплотную, и
     «12,5» с «15» наложились — единственное наложение подписей во всём
     калькуляторе по замеру.

     Две попытки решить это на экране не годились: по расстоянию между точками
     привязки порог не выражается (числа разной длины: «12,5» шире «15» вдвое),
     а сравнение готовых прямоугольников зависит от порядка отрисовки. В
     ДАННЫХ вопрос простой: деление, стоящее ближе десятой доли окна к
     координате точки, не печатаем вовсе. */
  const near = (a, b, span) => isFinite(a) && isFinite(b) && Math.abs(a - b) < span * 0.1;
  [0.25, 0.5, 0.75, 1].forEach(t => { const xq = Xmax * t;
    if (qi != null && near(xq, qi, Xmax)) return;
    g.append('text').attr('x', lx(xq)).attr('y', bottom + 12).attr('text-anchor', 'middle').attr('class', 'axis-num').attr('font-size', FS.small).attr('fill', COL.inkSoft).text(fmt(xq)); });
  [0.25, 0.5, 0.75, 1].forEach(t => { const yp = Ymax * t;
    if (Pi != null && near(yp, Pi, Ymax)) return;
    g.append('text').attr('x', left - 5).attr('y', ly(yp)).attr('text-anchor', 'end').attr('dominant-baseline', 'middle').attr('class', 'axis-num').attr('font-size', FS.small).attr('fill', COL.inkSoft).text(fmt(yp)); });
  const gc = svg.append('g').attr('clip-path', 'url(#' + cid + ')');
  const line = d3.line().defined(d => d !== null).x(d => lx(d[0])).y(d => ly(d[1]));
  const sample = (f) => { const o = []; for (let i = 0; i <= 300; i++) { const q = Xmax * i / 300; const v = f(q); o.push((isNaN(v) || v < 0) ? null : [q, v]); } return o; };
  gc.append('path').datum(sample(q => evalCurve(D, q))).attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.5).attr('d', line);           // D
  gc.append('path').datum(sample(q => marginalRevenue(D, q))).attr('fill', 'none').attr('stroke', COL.MR).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);  // MR
  gc.append('path').datum(sample(q => evalCurve(mcCurve, q))).attr('fill', 'none').attr('stroke', COL.S).attr('stroke-width', 2).attr('d', line);       // MC
  if (qi != null && qi > 0 && !isNaN(Pi)) {
    const px = lx(qi), py = ly(Pi);
    g.append('line').attr('x1', px).attr('y1', py).attr('x2', px).attr('y2', bottom).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    g.append('line').attr('x1', px).attr('y1', py).attr('x2', left).attr('y2', py).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    /* Мини-панель дискриминации живёт на СВОИХ осях (lx/ly), поэтому общий
       помощник ей не подходит: он считает по шкалам главного графика. Правило
       то же — имя оси не повторяется, остаётся одно число.

       ⚠️ И то же правило про деление. Пока у координаты стоял префикс («q=15»),
       она была шире деления и вставала рядом; оставшись голым числом, она села
       ровно туда же, где уже стоит деление шкалы, и два числа наложились
       (замер поймал наложение на 7,2 px² в этой сцене — единственное во всём
       калькуляторе). Деление на этом месте убираем, число точки печатаем
       акцентным и жирным — как на главных осях. */
    /* ⚠️ УСТУПАЕТ НЕ ТО ДЕЛЕНИЕ, ЧТО СТОИТ РОВНО ТАМ ЖЕ, А ТО, ЧТО НАЛЕЗАЕТ.
       Первая правка снимала деление по расстоянию между их точками привязки
       (порог 7 px). Замер показал, что этого мало: «12,5» шириной 22,7 px и
       «15» стоят в 16 px друг от друга — привязки далеко, а коробки
       пересекаются. Сравниваем настоящие прямоугольники после отрисовки:
       порогу тут верить нельзя, длина числа заранее неизвестна. */
    /* ⚠️ КЛАСС `coord-num` — ПРИЗНАК «ЭТО ЧИСЛО ТОЧКИ НА ОСИ», А НЕ УКРАШЕНИЕ.
       По нему разводятся налезающие подписи (общий проход в 30-curves), по нему
       же выгрузка отличает координату от обычного текста, и по нему её ищут
       проверки. Мини-панель рисовала свои числа мимо axisValueX/Y и класса не
       ставила: на экране числа стояли, а всякий, кто спрашивал «есть ли на оси
       число под этим пунктиром», получал «нет». Та же болезнь, что была у
       делений шкалы (`axis-num`) в пяти рисователях осей. */
    haloText(g, px, bottom + 12, fmt(qi), 'middle', 'hanging')
      .attr('class', 'coord-num')
      .attr('fill', cssVar('--accent')).attr('font-weight', 700);
    haloText(g, left - 5, py, fmt(Pi), 'end', 'middle')
      .attr('class', 'coord-num')
      .attr('fill', cssVar('--accent')).attr('font-weight', 700);
    /* ⚠️ ПЕЧАТАЕМ САМИ — ЗНАЧИТ, САМИ И ОБЪЯВЛЯЕМ. Механизм ключевых точек
       читает то, что напечатали axisValueX/axisValueY, а мини-рынок печатает
       мимо них (у него свои шкалы lx/ly и своё правило уступки делений). Пока
       он молчал, «Дискриминация 3-й степени» и «Монополист и внешний рынок»
       оставались вовсе без ключевых точек. Объявляем ТЕМ ЖЕ списком, называя
       свою панель: угол составляется из чисел одной панели. */
    noteAxisX(g, px, fmt(qi), '', 'mini-' + idx);
    noteAxisY(g, py, fmt(Pi), '', 'mini-' + idx);
  }
}

// Полная перерисовка дискриминации 3-й степени: два мини-графика бок о бок.
function redrawDiscr3() {
  recomputeDiscr3();
  /* «Монополист и внешний рынок» — не два рынка, а ОДИН график: см.
     drawMonoExport ниже. Два мини-графика остаются у настоящей
     дискриминации 3-й степени, где рынка действительно два. */
  if (STATE.d3World) { drawMonoExport(); return; }
  svg.selectAll('*').remove();
  addDefs();
  const d = STATE.discr3;
  // Левая панель начинается ПОСЛЕ дока (56px), иначе её ось и цифры уходят под него.
  const gxLeft = 64, midX = gxLeft + (W - gxLeft) / 2;
  if (!d || !d.found) {
    drawGrid(); drawAxes();
    updateDiscr3Panel();
    return;
  }
  // Панели здесь свои: 'main' на весь холст, заведённая makeScales, тут лишняя.
  clearPanels();
  drawMiniMarket(gxLeft, midX, 'Рынок 1', d.c1, d.q1, d.P1, d.cm, 1);
  drawMiniMarket(midX, W, 'Рынок 2', d.c2, d.q2, d.P2, d.cm, 2);
  // Разделитель между панелями.
  svg.append('line').attr('x1', midX).attr('y1', 52).attr('x2', midX).attr('y2', H - 30).attr('stroke', COL.grid).attr('stroke-width', 1);
  updateDiscr3Panel();
}

/* --- Монополист и внешний рынок: ОДИН график на общий выпуск --- */

/* ⚠️ ЗДЕСЬ ОДИН ГРАФИК, А НЕ ДВА, И ЭТО РЕШЕНИЕ О СМЫСЛЕ, А НЕ ЭКОНОМИЯ МЕСТА.

   Мировая цена работает сразу в ДВУХ ролях: она предельный доход от каждой
   вывезенной единицы (поэтому дома продают ровно столько, что MR внутри = Pw)
   и она же ориентир, до которого фирма наращивает ОБЩИЙ выпуск (поэтому
   MC = Pw). Обе роли — про одну и ту же горизонталь, и увидеть это можно
   только тогда, когда обе точки стоят на ОДНОЙ оси Q. У двух панелей оси Q
   разные: общий выпуск на них не читается вовсе, а экспорт приходилось
   считать в уме как разность двух чисел с разных картинок.

   ⚠️ Дискриминации 3-й степени это НЕ касается: там два разных рынка со своими
   спросами, общей у них только MC, и две панели остаются (drawMiniMarket).

   Панель у сцены одна — 'main', та самая, что заводит makeScales. Поэтому
   точки, площади, ключевые точки и колесо мыши работают общим механизмом, и
   clearPanels() здесь не зовётся ([ADR 0083]). */
function drawMonoExport() {
  const d = STATE.discr3;
  if (!d || (!d.found && !d.unbounded)) {
    svg.selectAll('*').remove();
    addDefs(); drawGrid(); drawAxes();
    updateDiscr3Panel();
    return;
  }
  const u = d.unbounded;
  // Мировая цена — уровень горизонтального «спроса» второго сегмента. Спрашиваем
  // его в нуле: при нулевом экспорте (вывозить невыгодно) q₂ = 0, и брать
  // значение в точке q₂ было бы тем же самым числом окольным путём.
  const Pw = d.found ? evalCurve(d.c2, 0) : u.Pw;
  const q1 = d.found ? d.q1 : u.q1;
  const P1 = d.found ? d.P1 : u.P1;
  const Qtot = d.found ? d.Qtot : null;
  /* Экспорт есть только тогда, когда общий выпуск больше внутреннего. Мировая
     цена ниже предельных издержек в оптимуме — вывозить невыгодно, и фирма
     ведёт себя как обычный монополист внутри страны. Отрицательного экспорта
     не бывает: q₂ = Qtot − q₁, и решатель отдаёт весь выпуск дому сам. */
  const hasExport = (Qtot != null && Qtot > q1 + 1e-6);

  /* Окно сцена подбирает САМА: мировая цена бывает выше резервной цены
     покупателя, а общий выпуск — дальше конца внутреннего спроса, и в кадр
     до ста ни то ни другое не помещается. Общий проход такой кадр пропускает
     (_sceneRangedFrame), см. правило «окно расширяется, но не сжимается». */
  const dEnd = curveZeroQ(d.c1, Math.max(CONFIG.Qmax, 1) * 4);
  const dTop = evalCurve(d.c1, 0);
  const qWant = Math.max(dEnd || 0, q1 || 0, Qtot || 0);
  const pWant = Math.max(isFinite(dTop) ? dTop : 0, isFinite(Pw) ? Pw : 0);
  applyAutoRanges(padMax(qWant), padMax(pWant));
  makeScales();          // applyAutoRanges мог сдвинуть границы — шкалы заново

  svg.selectAll('*').remove();
  addDefs(); drawGrid(); drawAxes();
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(p => p !== null).x(p => sx(p[0])).y(p => sy(p[1]));
  const sample = (f) => {
    const o = [];
    for (let i = 0; i <= 400; i++) {
      const q = CONFIG.Qmax * i / 400, v = f(q);
      o.push((isNaN(v) || v < 0) ? null : [q, v]);
    }
    return o;
  };
  // Внутренний спрос.
  g.append('path').datum(sample(q => evalCurve(d.c1, q)))
    .attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.5).attr('d', line);
  // Предельный доход внутреннего рынка — пунктиром, как в обычной монополии;
  // продолжение ниже оси Q дорисовывает общий помощник.
  drawMarginalCurve(g, q => marginalRevenue(d.c1, q), d.c1, COL.MR, { width: 2 });
  // Предельные издержки от ОБЩЕГО выпуска — они и связывают два рынка в один.
  g.append('path').datum(sample(q => evalCurve(d.cm, q)))
    .attr('fill', 'none').attr('stroke', COL.S).attr('stroke-width', 2.5).attr('d', line);

  // Мировая цена — горизонталь через весь кадр, цветом регулятора: та же роль
  // и тот же вид, что у линии Pw в малой открытой экономике.
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax), yPw = sy(Pw);
  const gl = svg.append('g');
  gl.append('line').attr('x1', ox).attr('y1', yPw).attr('x2', xMax).attr('y2', yPw)
    .attr('stroke', COL.reg).attr('stroke-width', 2.5);
  axisValueY(gl, ox, yPw, fmt(Pw), 'w');
  // Подписи линий — общим помощником: он же разводит их у края кадра.
  labelCurve(gl, q => evalCurve(d.c1, q), 'D', COL.D, { key: 'mx-d' });
  labelCurve(gl, q => marginalRevenue(d.c1, q), 'MR', COL.MR, { key: 'mx-mr', below: true });
  labelCurve(gl, q => evalCurve(d.cm, q), 'MC', COL.S, { key: 'mx-mc' });
  labelCurve(gl, () => Pw, 'P_w', COL.reg, { key: 'mx-pw', below: true });

  const og = svg.append('g');
  const dash = (x1, y1, x2, y2) => og.append('line')
    .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');

  /* Отметка 1: внутренний оптимум (q₁; P₁) — с пунктиром к ОБЕИМ осям, как
     точка M в обычной монополии. Пунктир к двум осям и есть то, по чему
     точку узнаёт и человек, и механизм ключевых точек ([ADR 0084]). */
  if (isFinite(q1) && q1 > 1e-9 && isFinite(P1)) {
    const [px, py] = toPx(q1, P1);
    dash(px, py, px, oy); dash(px, py, ox, py);
    /* Маленькая точка на вертикали — там, где предельный доход внутреннего
       рынка сравнялся с альтернативой. Экспорт есть — она ложится ровно на
       линию мировой цены (MR = Pw); экспорта нет — на MC, и это обычное
       MR = MC закрытой монополии. Уровень спрашиваем у самого MR, а не
       подставляем Pw: подстановка врала бы во втором случае. */
    const mr1 = marginalRevenue(d.c1, q1);
    if (isFinite(mr1)) og.append('circle').attr('cx', px).attr('cy', sy(mr1)).attr('r', 3.5)
      .attr('fill', COL.MR).attr('stroke', COL.halo).attr('stroke-width', 1.2);
    og.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5)
      .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(og, px, py, 'M', COL.ink);
    axisValueX(og, px, oy, fmt(q1), '1');
    axisValueY(og, ox, py, fmt(P1), '1');
  }

  /* Отметка 2: общий выпуск (Q; Pw) — там, где предельные издержки дорастают
     до мировой цены. Рисуется только при живом экспорте: без него общий
     выпуск равен внутреннему, и второй пунктир встал бы поверх первого. */
  if (hasExport) {
    const [px, py] = toPx(Qtot, Pw);
    dash(px, py, px, oy);
    og.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5)
      .attr('fill', COL.S).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    /* Различитель «Σ» — тот же, которым это число названо в панели («Σ выпуск»).
       Он же становится именем ключевой точки: без него угол (Q; Pw) назывался
       бы просто «точка Pw» и не отличался бы словами от самой линии цены. */
    axisValueX(og, px, oy, fmt(Qtot), 'Σ');
  }

  /* Отметка 3: отрезок экспорта прямо на линии мировой цены — тем же приёмом,
     что полоса импорта в малой открытой экономике. */
  const qLo = Math.max(q1 > 0 ? q1 : 0, 0);
  const band = (xa, xb, txt) => {
    if (!(xb > xa + 1)) return;
    gl.append('line').attr('x1', xa).attr('y1', yPw).attr('x2', xb).attr('y2', yPw)
      .attr('stroke', COL.S).attr('stroke-width', 6).attr('opacity', 0.45);
    haloText(gl, (xa + xb) / 2, yPw - 12, txt, 'middle', 'auto');
  };
  if (hasExport) band(sx(qLo), sx(Qtot), 'Экспорт = ' + fmt(Qtot - qLo));
  else if (!d.found) band(sx(qLo), xMax, 'Объём экспорта не ограничен');

  updateDiscr3Panel();
}

function updateDiscr3Panel() {
  const box = document.getElementById('info-d3'); if (!box) return;
  const d = STATE.discr3;
  const world = !!STATE.d3World;
  if (!d) { box.innerHTML = '<div class="muted">Введите ' + (world ? 'внутренний спрос, мировую цену и MC' : 'два спроса и MC') + ', нажмите «Построить».</div>'; return; }
  if (!d.found) {
    // Фаза 4г: вырожденный случай мировой торговли — если предельные издержки НИГДЕ
    // не дорастают до мировой цены, оптимальный экспорт математически не ограничен.
    // Это свойство модели, а не сбой солвера, — так и пишем.
    if (world && d.unbounded) {
      const u = d.unbounded;
      /* Числа внутреннего рынка стоят ПЕРЕД предупреждением: у сцены есть
         ответ, и человек должен увидеть сначала его, а потом оговорку. */
      let html = '';
      if (u.q1 > 1e-9 && !isNaN(u.P1))
        html += `<div class="stat"><span>Внутри: (q₁; P₁)</span><b>(${fmt(u.q1)}; ${fmt(u.P1)})</b></div>`;
      else
        html += '<div class="stat"><span>Внутри</span><b>рынка нет (выпуск 0)</b></div>';
      html += `<div class="stat"><span>Мировая цена $P_w$</span><b>${fmt(u.Pw)}</b></div>`;
      html += '<div class="stat"><span>Экспорт</span><b>не ограничен</b></div>';
      html += '<div class="warn" style="margin-top:6px;">При предельных издержках ниже мировой цены оптимальный ' +
        'объём экспорта не ограничен: фирме выгодна любая дополнительная единица. Это нормальное свойство ' +
        'модели, а не ошибка расчёта: используйте возрастающие MC (например <code>Q</code>).</div>';
      html += '<div class="hint">Внутренний рынок при этом обычный: домашнюю единицу можно было продать за ' +
        'границу по $P_w$, поэтому дома продаётся столько, что <b>MR внутри = $P_w$</b>.</div>';
      box.innerHTML = html;
      return;
    }
    box.innerHTML = '<div class="warn">Оптимум MR = MC не найден.</div>'; return;
  }
  if (world) {
    // Экспорт по мировой цене: сегмент 2 — горизонтальный спрос, поэтому MR₂ = Pw.
    let html = '';
    /* ⚠️ ВНУТРЕННЕЙ ЦЕНЫ ПРИ НУЛЕВОМ ВЫПУСКЕ НЕ СУЩЕСТВУЕТ. Когда мировая цена
       выше резервной цены покупателя (Pw > D(0)), дома не покупает никто:
       весь выпуск идёт на экспорт. Прежняя строка печатала «(0; 100)» —
       цену, по которой ничего не продано. */
    if (d.q1 > 1e-9)
      html += `<div class="stat"><span>Внутри: (q₁; P₁)</span><b>(${fmt(d.q1)}; ${fmt(d.P1)})</b></div>`;
    else
      html += '<div class="stat"><span>Внутри</span><b>рынка нет (выпуск 0): $P_w$ выше резервной цены покупателя</b></div>';
    html += `<div class="stat"><span>Экспорт q₂ (по Pw)</span><b>${fmt(d.q2)} / ${fmt(d.P2)}</b></div>`;
    html += `<div class="stat"><span>Σ выпуск</span><b>${fmt(d.Qtot)}</b></div>`;
    html += `<div class="stat"><span>$MR_1 = P_w = MC$</span><b>${fmt(d.mcLevel)}</b></div>`;
    html += '<div class="hint">Мировой рынок для малой фирмы совершенно эластичен: продать за границей можно ' +
      'сколько угодно по цене Pw, поэтому предельный доход от экспорта постоянен и равен Pw. Условие оптимума такое: ' +
      '<b>MR внутри = Pw = MC(Σ выпуска)</b>: издержки считаются от ОБЩЕГО выпуска, поэтому экспорт влияет ' +
      'на внутреннюю цену. Дома цена выше мировой: классический «обратный демпинг» при растущих издержках.</div>';
    box.innerHTML = html;
    return;
  }
  // Эластичность в точке оптимума: |E| = |P / (Q·dP/dQ)|. Меньше эластичный → выше цена.
  const less = (d.P1 >= d.P2) ? '1' : '2';
  let html = '';
  html += `<div class="stat"><span>Рынок 1: (q₁; P₁)</span><b>(${fmt(d.q1)}; ${fmt(d.P1)})</b></div>`;
  html += `<div class="stat"><span>Рынок 2: (q₂; P₂)</span><b>(${fmt(d.q2)}; ${fmt(d.P2)})</b></div>`;
  html += `<div class="stat"><span>Σ выпуск</span><b>${fmt(d.Qtot)}</b></div>`;
  html += `<div class="stat"><span>$MR_1 = MR_2 = MC$</span><b>${fmt(d.mcLevel)}</b></div>`;
  html += `<div class="hint">Цена выше на менее эластичном рынке (здесь это рынок&nbsp;${less}). Фирма выравнивает предельный доход: MR₁&nbsp;=&nbsp;MR₂&nbsp;=&nbsp;MC.</div>`;
  box.innerHTML = html;
}

// Фаза 4г: подписи полей дискриминации 3° под сюжет «монополист и мировой рынок».
function applyD3WorldLabels() {
  const w = !!STATE.d3World;
  const set = (sel, txt) => { const e = document.querySelector(sel); if (e) e.textContent = txt; };
  const pane = document.getElementById('mono-d3-pane');
  if (!pane) return;
  const labels = pane.querySelectorAll('.field > label');
  if (labels.length >= 3) {
    labels[0].innerHTML = w ? 'Внутренний спрос: P = f(Q)' : 'Спрос рынка&nbsp;1: P&nbsp;=&nbsp;f₁(Q)';
    labels[1].innerHTML = w ? 'Мировая цена Pw (число: спрос совершенно эластичен)' : 'Спрос рынка&nbsp;2: P&nbsp;=&nbsp;f₂(Q)';
    labels[2].innerHTML = w ? 'Предельные издержки MC от ОБЩЕГО выпуска' : 'Общие предельные издержки MC (число или f(Q))';
  }
  const hint = pane.querySelector('.hint');
  if (hint) hint.innerHTML = w
    ? 'Мировой рынок это второй «сегмент» с горизонтальным спросом на уровне Pw. Математика та же, что у ' +
      'дискриминации 3-й степени: фирма выравнивает предельный доход по сегментам, MR₁&nbsp;=&nbsp;MR₂&nbsp;=&nbsp;MC. ' +
      'Так как MR₂&nbsp;=&nbsp;Pw, условие превращается в MR₁&nbsp;=&nbsp;Pw&nbsp;=&nbsp;MC.'
    : 'Фирма распределяет выпуск так, что MR₁&nbsp;=&nbsp;MR₂&nbsp;=&nbsp;MC. На менее эластичном рынке цена выше. ' +
      'Два мини-графика рынков стоят бок о бок.';
}

/* --- Задача 6: монополист при ломаном (кусочном) рыночном спросе --- */

// Единое представление рыночного спроса: { segs:[{q0,q1,D}], kinks:[Q], Dfn } или { error }.
function buildKinkedDemand() {
  if (STATE.kinkInput === 'piecewise') {
    const f1 = makeCurve(STATE.kpD1), f2 = makeCurve(STATE.kpD2);
    if (f1.error) return { error: f1.error };
    if (f2.error) return { error: f2.error };
    let qk = findRoot(q => { const a = evalCurve(f1, q), b = evalCurve(f2, q); return (isNaN(a) || isNaN(b)) ? NaN : a - b; });
    if (qk == null || !(qk > 0) || qk >= CONFIG.Qmax) {            // куски не пересекаются → один кусок
      return { segs: [{ q0: 0, q1: CONFIG.Qmax, D: f1 }], kinks: [], Dfn: q => evalCurve(f1, q) };
    }
    const segs = [{ q0: 0, q1: qk, D: f1 }, { q0: qk, q1: CONFIG.Qmax, D: f2 }];
    return { segs, kinks: [qk], Dfn: q => (q < qk) ? evalCurve(f1, q) : evalCurve(f2, q) };
  }
  // Индивидуальные спросы → горизонтальная сумма.
  const exprs = [STATE.kiD1, STATE.kiD2, STATE.kiD3].map(s => (s || '').trim()).filter(s => s.length);
  if (!exprs.length) return { error: 'Введите хотя бы один спрос' };
  const cs = []; for (const e of exprs) { const c = makeCurve(e); if (c.error) return { error: c.error }; cs.push(c); }
  if (cs.every(c => c.linear)) {
    // Все линейные: изломы — на ценах-перехватах b_i, между ними сумма линейна (точно).
    const lins = cs.map(c => c.linear);
    const prices = [...new Set(lins.map(l => l.b).filter(b => b > 0))].sort((x, y) => y - x);
    prices.push(0);
    const Qat = (P) => lins.reduce((s, l) => { const q = (P - l.b) / l.a; return s + (q > 0 ? q : 0); }, 0);
    const bps = prices.map(P => [Qat(P), P]).filter(p => !isNaN(p[0]));
    const segs = [], kinks = [];
    for (let i = 0; i < bps.length - 1; i++) {
      const [q0, p0] = bps[i], [q1, p1] = bps[i + 1];
      if (q1 <= q0 + 1e-9) continue;
      const a = (p1 - p0) / (q1 - q0), b = p0 - a * q0;
      segs.push({ q0, q1, D: { linear: { a, b } } });
      if (segs.length > 1 && q0 > 1e-9) kinks.push(q0);
    }
    if (!segs.length) return { error: 'Спрос не строится' };
    const Dfn = (Q) => { for (const s of segs) { if (Q >= s.q0 - 1e-9 && Q <= s.q1 + 1e-9) return evalCurve(s.D, Q); } const last = segs[segs.length - 1]; return last ? evalCurve(last.D, Q) : NaN; };
    return { segs, kinks, Dfn };
  }
  // Нелинейный спрос — численная горизонтальная сумма как одна гладкая кривая (без явных изломов).
  const Dfn = (Q) => {
    const Qsum = (P) => cs.reduce((s, c) => { const q = invCurve(c, P); return s + ((q != null && q > 0) ? q : 0); }, 0);
    let lo = 0, hi = CONFIG.Pmax * 4;
    if (Qsum(lo) < Q) return 0;
    for (let k = 0; k < 60; k++) { const mid = (lo + hi) / 2; if (Qsum(mid) > Q) lo = mid; else hi = mid; }
    return (lo + hi) / 2;
  };
  return { segs: [{ q0: 0, q1: CONFIG.Qmax, D: { fn: Dfn } }], kinks: [], Dfn };
}

// Пересчёт ломаного спроса: кандидаты (MR=MC на каждом куске + сами изломы) → максимум прибыли.
function recomputeKinked() {
  STATE.kinked = null;
  const errBox = document.getElementById('kink-error');
  const km = makeCurve(STATE.kinkMC);
  const built = buildKinkedDemand();
  if ((built && built.error) || km.error) { if (errBox) { errBox.style.display = 'block'; errBox.textContent = 'Не понял формулу: ' + ((built && built.error) || km.error); } return; }
  if (errBox) errBox.style.display = 'none';
  const mc = (q) => evalCurve(km, q);
  const { segs, kinks, Dfn } = built;
  const cands = [];
  segs.forEach(s => { const r = findRootIn(q => marginalRevenue(s.D, q) - mc(q), s.q0, s.q1); if (r != null) cands.push({ Q: r, kind: 'MR=MC' }); });
  kinks.forEach(qk => cands.push({ Q: qk, kind: 'излом' }));
  // ⚠️ Выбор оптимума идёт по НАСТОЯЩЕЙ MC (см. Rel в monopolyCeiling):
  // обрезка нулём — правило измерения площади, а не принятия решения.
  const prof = (Q) => { const p = Dfn(Q); return isNaN(p) ? -Infinity : p * Q - integrate(mc, 0, Q); };
  cands.forEach(c => c.profit = prof(c.Q));
  if (!cands.length) { STATE.kinked = { segs, kinks, Dfn, mcCurve: km, found: false }; return; }
  let best = cands[0]; cands.forEach(c => { if (c.profit > best.profit + 1e-6) best = c; });
  best.win = true;
  const Qstar = best.Q, Pstar = Dfn(Qstar);
  /* Конкурентный выпуск: там, где ЛОМАНЫЙ спрос встречает MC. Ищем по каждому
     куску и берём последний найденный — куски идут слева направо, а у
     убывающего спроса нужен самый правый корень. */
  let Qc = null;
  segs.forEach(s => { const r = findRootIn(q => Dfn(q) - mc(q), s.q0, s.q1); if (r != null && r > 0) Qc = r; });
  /* ⚠️ ПЛОЩАДИ СЧИТАЮТСЯ ПО КУСКАМ. Метод трапеций точен на прямой только
     тогда, когда излом попал в УЗЕЛ сетки, а излом ломаного спроса туда
     попадает случайно. Изломы отдаются интегратору списком — тем же приёмом,
     что у излишков суммарных кривых (quadBreaks). Второго механизма не
     заводим. */
  const csM = integrateBroken(q => Dfn(q) - Pstar, 0, Qstar, kinks);
  const vcM = integrate(q => mcFloor(mc(q)), 0, Qstar);
  const psM = integrate(q => Pstar - mcFloor(mc(q)), 0, Qstar);
  const dwl = (Qc != null && Qc > Qstar)
    ? integrateBroken(q => Dfn(q) - mcFloor(mc(q)), Qstar, Qc, kinks) : null;
  STATE.kinked = { segs, kinks, Dfn, mcCurve: km, found: true, Qstar, Pstar,
                   profit: best.profit, winKind: best.kind, cands,
                   Qc, csM, vcM, psM, dwl };
}

function drawKinkedFull() {
  recomputeKinked();
  svg.selectAll('*').remove();
  addDefs(); drawGrid(); drawAxes();
  const k = STATE.kinked;
  if (!k) { updateKinkPanel(); return; }
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  /* Заливки — ПЕРВЫМИ, чтобы лежать под кривыми. Точки для них берутся так,
     чтобы КАЖДЫЙ ИЗЛОМ БЫЛ УЗЛОМ: иначе многоугольник срезает угол ломаного
     спроса, и нарисованная площадь расходится с числом. То же правило, что у
     интеграла по кускам в recomputeKinked. */
  const mcK = (q) => evalCurve(k.mcCurve, q);
  const sampK = (a, b) => {
    const inner = k.kinks.filter(x => x > a + 1e-9 && x < b - 1e-9).sort((x, y) => x - y);
    const ends = [a].concat(inner, [b]), out = [];
    for (let i = 0; i < ends.length - 1; i++)
      for (let j = 0; j < 60; j++) out.push(ends[i] + (ends[i + 1] - ends[i]) * j / 60);
    out.push(b);
    return out;
  };
  if (k.found && k.Qstar > 1e-6) {
    const s1 = sampK(0, k.Qstar);
    if (STATE.showMonoVC) {
      const a = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(mcFloor(mcK(d))));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.22).attr('data-legend', 'Переменные издержки (VC)');
    }
    if (STATE.showMonoPS) {
      const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcK(d)))).y1(sy(k.Pstar));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек производителя (TR - VC)');
    }
    if (STATE.showMonoCS) {
      const a = d3.area().x(d => sx(d)).y0(sy(k.Pstar)).y1(d => sy(k.Dfn(d)));
      g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
    }
    if (k.Qc != null && k.Qc > k.Qstar + 1e-9) {
      const s2 = sampK(k.Qstar, k.Qc);
      const a = d3.area().x(d => sx(d)).y0(d => sy(mcFloor(mcK(d)))).y1(d => sy(k.Dfn(d)));
      g.append('path').datum(s2).attr('d', a).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
    }
  }
  // Ломаный спрос (по Dfn).
  const dPts = []; for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = k.Dfn(q); dPts.push((isNaN(v) || v < 0) ? null : [q, v]); }
  g.append('path').datum(dPts).attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.5).attr('d', line);
  // MR по каждому куску (отдельные отрезки) + вертикальные разрывы в изломах.
  /* Продолжение вниз имеет смысл только у ПОСЛЕДНЕГО куска: у него
     Q-перехват тот же, что у всего ломаного спроса. Промежуточные куски
     обрываются не на оси, а в изломе, и тянуть их некуда. */
  k.segs.forEach((s, i) => {
    const last = (i === k.segs.length - 1);
    drawMarginalCurve(g, q => marginalRevenue(s.D, q), last ? s.D : null, COL.MR,
                      { width: 2, from: s.q0, to: s.q1, n: 200 });
  });
  k.kinks.forEach(qk => {
    const segL = k.segs.find(s => Math.abs(s.q1 - qk) < 1e-6), segR = k.segs.find(s => Math.abs(s.q0 - qk) < 1e-6);
    if (segL && segR) {
      const mrL = marginalRevenue(segL.D, qk), mrR = marginalRevenue(segR.D, qk);
      if (!isNaN(mrL) && !isNaN(mrR)) g.append('line').attr('x1', sx(qk)).attr('y1', sy(Math.max(0, mrL))).attr('x2', sx(qk)).attr('y2', sy(Math.max(0, mrR)))
        .attr('stroke', COL.MR).attr('stroke-width', 1.3).attr('stroke-dasharray', '2 2').attr('opacity', 0.6);
    }
  });
  // MC.
  const mcPts = []; for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = evalCurve(k.mcCurve, q); mcPts.push(isNaN(v) ? null : [q, v]); }
  g.append('path').datum(mcPts).attr('fill', 'none').attr('stroke', COL.S).attr('stroke-width', 2.5).attr('d', line);
  // Оптимум.
  if (k.found && k.Qstar > 0 && !isNaN(k.Pstar)) {
    const og = svg.append('g'), ox = sx(0), oy = sy(0), [px, py] = toPx(k.Qstar, k.Pstar);
    const dash = (x1, y1, x2, y2) => og.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2).attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    dash(px, py, px, oy); dash(px, py, ox, py);
    og.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    pointName(og, px, py, 'M', COL.ink);
    axisValueX(og, px, oy, fmt(k.Qstar), '');
    axisValueY(og, ox, py, fmt(k.Pstar), '');
  }
  updateKinkPanel();
}

function updateKinkPanel() {
  const box = document.getElementById('info-kink'); if (!box) return;
  const k = STATE.kinked;
  if (!k) { box.innerHTML = '<div class="muted">Введите спрос и MC, нажмите «Построить».</div>'; return; }
  if (!k.found) { box.innerHTML = '<div class="warn">Оптимум не найден (нет кандидатов).</div>'; return; }
  let html = '';
  html += `<div class="stat"><span>$Q^*$ (выпуск)</span><b>${fmt(k.Qstar)}</b></div>`;
  html += `<div class="stat"><span>$P^*$ (цена)</span><b>${fmt(k.Pstar)}</b></div>`;
  html += `<div class="stat"><span>Прибыль π</span><b>${fmt(k.profit)}</b></div>`;
  if (k.csM != null) html += `<div class="stat"><span>$CS$</span><b>${fmt(k.csM)}</b></div>`;
  if (k.psM != null) html += `<div class="stat"><span>$PS$ (TR − VC)</span><b>${fmt(k.psM)}</b></div>`;
  if (k.vcM != null) html += `<div class="stat"><span>$VC$</span><b>${fmt(k.vcM)}</b></div>`;
  if (k.Qc != null) html += `<div class="stat"><span>Конкурентный выпуск</span><b>${fmt(k.Qc)}</b></div>`;
  if (k.dwl != null) html += `<div class="stat"><span>$DWL$</span><b>${fmt(k.dwl)}</b></div>`;
  html += `<div class="stat"><span>Победил кандидат</span><b>${k.winKind} @ Q = ${fmt(k.Qstar)}</b></div>`;
  // Таблица всех кандидатов с прибылью (видно сравнение).
  html += '<table class="tx-table" style="margin-top:6px;"><tr><th>Кандидат</th><th>Q</th><th>π</th></tr>';
  k.cands.forEach(c => {
    const win = (Math.abs(c.Q - k.Qstar) < 1e-6);
    html += `<tr${win ? ' style="font-weight:700;color:var(--text);"' : ''}><td>${c.kind}</td><td>${fmt(c.Q)}</td><td>${fmt(c.profit)}</td></tr>`;
  });
  html += '</table>';
  html += '<div class="hint">Оптимум берётся по МАКСИМУМУ прибыли среди кандидатов, а не по первому пересечению MR&nbsp;=&nbsp;MC.</div>';
  box.innerHTML = html;
}

/* --- Переключатели под-режимов монополии --- */

// Видимость панелей монополии: под-режим и его поля (вызывается из setMarket и setMonoMode).
function applyMonoVisibility() {
  const inMono = (STATE.market === 'monopoly'), mm = STATE.monoMode;
  const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? '' : 'none'; };
  show('mono-submode', inMono);
  // Галочки заливок — общие с обычной монополией; ломаный спрос рисует те же
  // четыре фигуры теми же STATE.showMono*, своих галочек не заводит.
  show('mono-areas-chk', inMono && (mm === 'simple' || mm === 'kinked'));
  show('mono-interv-hint', inMono && mm === 'simple');
  show('mono-d1-pane', inMono && mm === 'discr1');
  show('mono-d3-pane', inMono && mm === 'discr3');
  show('mono-kink-pane', inMono && mm === 'kinked');
  show('mono-nat-pane', inMono && mm === 'natural');
  /* «Дискр.3» и «Ломаный» рисуют кривые по своим полям формул, общий список
     они не читают. Карточку списка в них не показываем: см. разбор договора
     о параметрах у sceneDrawsCurveList. */
  if (typeof syncCurveListVisibility === 'function') syncCurveListVisibility();
}

// Стандартный пресет при входе в монополию (Задача 1): ставится ТОЛЬКО если нужного нет.
// «Обычная»/«Дискр.1» работают на кривых D и MC из списка; «Дискр.3»/«Ломаный» — на полях формул.
// Не перетирает уже заданное пользователем.
function ensureMonopolyCurves() {
  /* Здесь спрашивают «есть ли РОЛЬ», а не «есть ли кривая для модели»: у
     погашенной кривой роль занята, и curveByRole завёл бы вторую такую же. */
  if (!curveByRoleAny('demand')) {                    // нет спроса → добавить D = 100 − Q
    addCurve('100 - Q'); const c = STATE.curves[STATE.curves.length - 1]; if (c) setRole(c, 'demand');
  }
  if (!mcSourceCurveAny() && !curveByRoleAny('tc')) {  // нет источника MC (mc/S/TC) → добавить MC = 20
    addCurve('20'); const c = STATE.curves[STATE.curves.length - 1]; if (c) setRole(c, 'mc');
  }
}
// Заполнить поле формулы стандартным значением, только если оно пустое (+ обновить input).
function fillIfEmpty(key, def, id) {
  if (!((STATE[key] || '').trim())) { STATE[key] = def; const e = document.getElementById(id); if (e) e.value = def; }
}
function ensureD3Fields() {
  fillIfEmpty('d3D1', '100 - Q', 'inp-d3-1');
  fillIfEmpty('d3D2', '80 - 2*Q', 'inp-d3-2');
  fillIfEmpty('d3MC', '20', 'inp-d3-mc');
}
function ensureKinkFields() {
  if (STATE.kinkInput === 'piecewise') { fillIfEmpty('kpD1', '100 - Q', 'inp-kp-1'); fillIfEmpty('kpD2', '120 - 1.5*Q', 'inp-kp-2'); }
  else { fillIfEmpty('kiD1', '100 - Q', 'inp-ki-1'); fillIfEmpty('kiD2', '60 - Q', 'inp-ki-2'); }
  fillIfEmpty('kinkMC', '20', 'inp-kink-mc');
}
// Подставить стандартное по текущему под-режиму монополии (диспетчер).
function ensureMonopolyPreset() {
  const mm = STATE.monoMode;
  if (mm === 'discr3') ensureD3Fields();
  else if (mm === 'kinked') ensureKinkFields();
  else ensureMonopolyCurves();                         // simple / discr1 — кривые D и MC
}

function setMonoMode(mm) {
  STATE.monoMode = mm;
  [['mm-simple', 'simple'], ['mm-d1', 'discr1'], ['mm-d3', 'discr3'],
   ['mm-kink', 'kinked'], ['mm-nat', 'natural']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === mm); });
  if (STATE.market === 'monopoly') ensureMonopolyPreset();   // стандартный пресет, если пусто (Задача 1)
  applyMonoVisibility();
  if (typeof updatePult === 'function') updatePult();   // набор регуляторов ленты зависит от под-режима
  redrawAll();
}

function setKinkInput(which) {
  STATE.kinkInput = which;
  const i = document.getElementById('ki-indiv'), p = document.getElementById('ki-piece');
  if (i) i.classList.toggle('active', which === 'individual');
  if (p) p.classList.toggle('active', which === 'piecewise');
  const ind = document.getElementById('kink-indiv'), pie = document.getElementById('kink-piece');
  if (ind) ind.style.display = (which === 'individual') ? '' : 'none';
  if (pie) pie.style.display = (which === 'piecewise') ? '' : 'none';
  if (STATE.market === 'monopoly' && STATE.monoMode === 'kinked') ensureKinkFields();   // стандартный пример, если пусто (Задача 1)
  redrawAll();
}

