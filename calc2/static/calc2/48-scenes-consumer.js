// Выбор потребителя: бюджет, кривые безразличия, Слуцкий.
/* =====================================================================
   БЛОК 10в. ТЕОРИЯ ПОТРЕБИТЕЛЯ (Фаза 8) — отдельный режим mode='consumer'.
   Оси: благо x (горизонталь) и благо y (вертикаль).
   Бюджетная линия Px·x + Py·y = I; оптимум и кривые безразличия считает
   ОБЩИЙ движок касания уровня (Фаза 7). Никаких закрытых формул под
   конкретный вид предпочтений — один численный путь на всё, включая
   пользовательскую функцию; совпадение с аналитикой служит проверкой.
   ===================================================================== */

// Функция полезности по текущему типу предпочтений. Возвращает { f } или { error }.
function consumerUtility() {
  const t = STATE.consType, A = STATE.consA, B = STATE.consB, k = STATE.consK;
  if (t === 'cobb')  return { f: (x, y) => Math.pow(Math.max(0, x), A) * Math.pow(Math.max(0, y), B) };
  if (t === 'subs')  return { f: (x, y) => A * x + B * y };
  if (t === 'compl') {
    const a = (Math.abs(A) > 1e-9) ? A : 1, b = (Math.abs(B) > 1e-9) ? B : 1;
    return { f: (x, y) => Math.min(x / a, y / b) };
  }
  if (t === 'quasi') return { f: (x, y) => x + k * Math.sqrt(Math.max(0, y)) };
  const { compiled, error } = compileTwoVar(STATE.consCustom);
  if (error) return { error };
  return { f: (x, y) => evalTwoVar(compiled, x, y) };
}

// Один расчёт оптимума при заданных ценах и доходе (обёртка над общим движком).
function consumerOptimum(f, px, py, I) {
  const r = optimizeAlongConstraint(f, px, py, I);
  if (!r) return null;
  return { x: r.a, y: r.b, U: r.value, mrs: r.mrs, xInt: r.aMax, yInt: r.bMax, px, py, I };
}

/* Включение разложения Слуцкого. Вынесено из обработчика галочки, потому что
   этим же путём входит карточка «Декомпозиция по Слуцкому» из блока 8. */
function setConsSlutsky(on) {
  STATE.consSlutskyOn = !!on;
  const chk = document.getElementById('chk-cons-slutsky');
  if (chk) chk.checked = !!on;
  const r = document.getElementById('cons-px1-row');
  if (r) r.style.display = on ? '' : 'none';
  if (typeof updatePult === 'function') updatePult();
  _wantRangeAnim = true;
  redrawAll();
}

function recomputeConsumer() {
  STATE.cons = null; STATE.consErr = null;
  const u = consumerUtility();
  if (u.error) { STATE.consErr = u.error; return; }
  const f = u.f, px = STATE.consPx, py = STATE.consPy, I = STATE.consI;
  const base = consumerOptimum(f, px, py, I);
  if (!base) { STATE.consErr = 'Проверьте цены и доход: должны быть положительными.'; return; }
  const res = { f, base, slutsky: null };
  // 8в. Разложение Слуцкого: старый набор должен остаться just affordable по НОВЫМ ценам.
  if (STATE.consSlutskyOn && STATE.consPx1 > 0) {
    const px1 = STATE.consPx1;
    const Icomp = px1 * base.x + py * base.y;            // компенсированный доход по Слуцкому
    const comp = consumerOptimum(f, px1, py, Icomp);     // промежуточный оптимум
    const fin = consumerOptimum(f, px1, py, I);          // новый фактический оптимум
    if (comp && fin) {
      res.slutsky = {
        px1, Icomp, comp, fin,
        subX: comp.x - base.x,                           // эффект замещения по x
        incX: fin.x - comp.x,                            // эффект дохода по x
        totX: fin.x - base.x,                            // общий эффект
        subY: comp.y - base.y, incY: fin.y - comp.y, totY: fin.y - base.y,
      };
    }
  }
  STATE.cons = res;
  // Авто-масштаб под все показываемые бюджетные линии (включая компенсированную).
  let xm = base.xInt, ym = base.yInt;
  if (res.slutsky) {
    xm = Math.max(xm, res.slutsky.comp.xInt, res.slutsky.fin.xInt);
    ym = Math.max(ym, res.slutsky.comp.yInt, res.slutsky.fin.yInt);
  }
  applyAutoRanges(niceMax(xm * 1.12), niceMax(ym * 1.12));
}

// Бюджетная линия от (I/Px, 0) до (0, I/Py) + подписи перехватов.
function drawBudgetLine(opt, color, dashed, label) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const p = g.append('line')
    .attr('x1', sx(0)).attr('y1', sy(opt.yInt)).attr('x2', sx(opt.xInt)).attr('y2', sy(0))
    .attr('stroke', color).attr('stroke-width', 2.5);
  if (dashed) p.attr('stroke-dasharray', '7 4').attr('opacity', 0.85);
  if (label) {
    const mx = opt.xInt * 0.55, my = opt.yInt * 0.45;
    g.append('text').attr('x', sx(mx)).attr('y', sy(my) - 5)
      .attr('font-size', 10.5).attr('font-weight', 600).attr('fill', color)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
  }
}

// Кривая безразличия (или изокванта) заданного уровня.
function drawLevelCurve(f, level, color, width, opacity, dash) {
  const pts = traceLevelCurve(f, level, CONFIG.Qmax, CONFIG.Pmax * 6, 220);
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const p = g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color)
    .attr('stroke-width', width || 2.2).attr('opacity', opacity == null ? 1 : opacity).attr('d', line);
  if (dash) p.attr('stroke-dasharray', dash);
}

// Точка выбора с проекциями и подписью.
function drawChoicePoint(x, y, color, label) {
  const ox = sx(0), oy = sy(0), g = svg.append('g'), [px, py] = toPx(x, y);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(px, py, px, oy); dash(px, py, ox, py);
  haloText(g, px, oy + 8, fmt(x), 'middle', 'hanging');
  haloText(g, ox - 8, py, fmt(y), 'end', 'middle');
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 5).attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 2);
  if (label) g.append('text').attr('x', px + 9).attr('y', py - 9)
    .attr('font-size', 12).attr('font-weight', 700).attr('fill', color)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
}

// Перетаскиваемые концы бюджетной линии: тянем за перехват — меняется соответствующая цена.
function attachBudgetHandles(opt) {
  const g = svg.append('g');
  const mk = (cx, cy, onDrag) => {
    const h = g.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 11)
      .attr('fill', 'transparent').style('cursor', 'grab');
    h.call(d3.drag().container(() => svg.node())
      .on('start', () => { document.body.style.cursor = 'grabbing'; })
      .on('drag', (e) => onDrag(e))
      .on('end', () => { document.body.style.cursor = ''; }));
    g.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 4.5)
      .attr('fill', COL.halo).attr('stroke', COL.reg).attr('stroke-width', 2).style('pointer-events', 'none');
  };
  // Перехват по x: I/Px = позиция ⇒ Px = I / позиция.
  mk(sx(opt.xInt), sy(0), (e) => {
    const xv = toData(e.x, e.y)[0];
    if (xv > 1e-6) setConsumerNum('consPx', STATE.consI / xv, 'cons-px');
  });
  // Перехват по y: I/Py = позиция ⇒ Py = I / позиция.
  mk(sx(0), sy(opt.yInt), (e) => {
    const yv = toData(e.x, e.y)[1];
    if (yv > 1e-6) setConsumerNum('consPy', STATE.consI / yv, 'cons-py');
  });
}

// Единый путь смены числового параметра потребителя (поле / перетаскивание).
function setConsumerNum(key, value, inputId) {
  if (!(value > 0) || !isFinite(value)) return;
  STATE[key] = Math.round(value * 1000) / 1000;
  const e = document.getElementById(inputId); if (e) e.value = STATE[key];
  _wantRangeAnim = true;   // масштаб может поехать — плавно, с дебаунсом
  redrawAll();
}

// Полная перерисовка режима «Потребитель».
function redrawConsumer() {
  recomputeConsumer();
  makeScales();
  svg.selectAll('*').remove();
  addDefs(); drawGrid(); drawAxes('x', 'y');
  const c = STATE.cons;
  if (!c) { updateConsumerPanel(); return; }
  const f = c.f, b = c.base, s = c.slutsky;
  // Веер соседних кривых безразличия — «карта» предпочтений (ниже и выше оптимума).
  if (STATE.consFan && b.U > 0) {
    [0.62, 0.8, 1.22].forEach(m => drawLevelCurve(f, b.U * m, COL.indiff, 1.6, 0.35));
  }
  if (s) {
    // Три бюджетные линии: старая, компенсированная (Слуцкий), новая.
    drawBudgetLine(b, COL.ghost, true, 'старая');
    drawBudgetLine(s.comp, COL.MR, true, 'компенсир.');
    drawBudgetLine(s.fin, COL.reg, false, 'новая');
    drawLevelCurve(f, b.U, COL.indiff, 2.2, 1);          // кривая исходного уровня
    if (s.fin.U > 0) drawLevelCurve(f, s.fin.U, COL.reg, 2, 0.9, '5 4');
    drawChoicePoint(b.x, b.y, COL.ghost, 'A');
    drawChoicePoint(s.comp.x, s.comp.y, COL.MR, 'B');
    drawChoicePoint(s.fin.x, s.fin.y, COL.ink, 'C');
  } else {
    drawBudgetLine(b, COL.reg, false, null);
    drawLevelCurve(f, b.U, COL.indiff, 2.6, 1);
    drawChoicePoint(b.x, b.y, COL.ink, 'E');
    attachBudgetHandles(b);
  }
  updateConsumerPanel();
}

// Табло потребителя: оптимум, MRS, свойства типа предпочтений, разложение Слуцкого.
function updateConsumerPanel() {
  const box = document.getElementById('info-consumer'); if (!box) return;
  const err = document.getElementById('cons-error');
  if (err) { err.style.display = STATE.consErr ? 'block' : 'none'; err.textContent = STATE.consErr ? ('Не понял формулу: ' + STATE.consErr) : ''; }
  const c = STATE.cons;
  if (!c) { box.innerHTML = '<div class="warn">' + (STATE.consErr || 'Задайте цены и доход.') + '</div>'; return; }
  const b = c.base;
  let html = '';
  html += `<div class="stat"><span>Оптимум x* / y*</span><b>${fmt(b.x)} / ${fmt(b.y)}</b></div>`;
  html += `<div class="stat"><span>Полезность U</span><b>${fmt(b.U)}</b></div>`;
  html += `<div class="stat"><span>$MRS$ в оптимуме</span><b>${fmt(b.mrs)}</b></div>`;
  html += `<div class="stat"><span>$\frac{P_x}{P_y}$</span><b>${fmt(b.px / b.py)}</b></div>`;
  html += `<div class="stat"><span>Перехваты I/Px, I/Py</span><b>${fmt(b.xInt)}, ${fmt(b.yInt)}</b></div>`;
  // Свойство, характерное для выбранного типа предпочтений.
  const t = STATE.consType;
  if (t === 'subs') {
    const rx = STATE.consA / b.px, ry = STATE.consB / b.py;
    html += `<div class="hint" style="margin-top:4px;">Совершенные субституты: сравниваем «выгоду на рубль» —
      a/Px&nbsp;=&nbsp;${fmt(rx)} против b/Py&nbsp;=&nbsp;${fmt(ry)}. ` +
      (Math.abs(rx - ry) < 1e-9 ? 'Они равны, поэтому годится любой набор на бюджетной линии.'
        : (rx > ry ? 'Весь доход уходит на <b>x</b>: угловое решение.' : 'Весь доход уходит на <b>y</b>: угловое решение.')) + '</div>';
  } else if (t === 'compl') {
    html += `<div class="hint" style="margin-top:4px;">Совершенные комплементы: оптимум всегда на изломе
      x/a&nbsp;=&nbsp;y/b, то есть блага потребляются в жёсткой пропорции
      ${fmt(STATE.consA)}&nbsp;:&nbsp;${fmt(STATE.consB)}. MRS в изломе не определена — касания нет,
      оптимум задаёт пересечение луча пропорции с бюджетной линией.</div>`;
  } else if (t === 'quasi') {
    html += `<div class="hint" style="margin-top:4px;">Квазилинейные предпочтения: <b>потребление y не зависит от дохода</b>
      (пока дохода хватает) — из MRS&nbsp;=&nbsp;Px/Py уходит x. Весь прирост дохода идёт в x.
      Проверьте: измените I — y останется ${fmt(b.y)}.</div>`;
  }
  const s = c.slutsky;
  if (s) {
    html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
    html += `<div class="stat"><span>A: старый выбор (Px=${fmt(b.px)})</span><b>${fmt(b.x)} / ${fmt(b.y)}</b></div>`;
    html += `<div class="stat"><span>B: компенсированный (I′=${fmt(s.Icomp)})</span><b>${fmt(s.comp.x)} / ${fmt(s.comp.y)}</b></div>`;
    html += `<div class="stat"><span>C: новый выбор (Px=${fmt(s.px1)})</span><b>${fmt(s.fin.x)} / ${fmt(s.fin.y)}</b></div>`;
    const sg = (v) => (v > 0 ? '+' : '') + fmt(v);
    html += '<table class="tx-table" style="margin-top:6px;"><tr><th></th><th>замещ.</th><th>доход</th><th>итог</th></tr>';
    html += `<tr><td>Δx</td><td>${sg(s.subX)}</td><td>${sg(s.incX)}</td><td>${sg(s.totX)}</td></tr>`;
    html += `<tr><td>Δy</td><td>${sg(s.subY)}</td><td>${sg(s.incY)}</td><td>${sg(s.totY)}</td></tr>`;
    html += '</table>';
    html += `<div class="hint">Компенсированный доход по Слуцкому I′&nbsp;=&nbsp;Px₁·x₀&nbsp;+&nbsp;Py·y₀&nbsp;=&nbsp;${fmt(s.Icomp)}:
      столько нужно, чтобы СТАРЫЙ набор остался доступен при НОВЫХ ценах. Переход A→B — чистый эффект
      замещения (полезность меняется, покупательная способность старого набора сохранена), B→C — эффект
      дохода. Их сумма равна общему изменению.</div>`;
  }
  box.innerHTML = html;
}

// Показ полей параметров под выбранный тип предпочтений.
function applyConsumerTypeUI() {
  const t = STATE.consType;
  const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? '' : 'none'; };
  show('cons-ab-row', t === 'cobb' || t === 'subs' || t === 'compl');
  show('cons-k-row', t === 'quasi');
  show('cons-custom-row', t === 'custom');
  const la = document.getElementById('cons-a-lbl'), lb = document.getElementById('cons-b-lbl');
  if (la && lb) {
    if (t === 'cobb')  { la.textContent = 'a (степень x)'; lb.textContent = 'b (степень y)'; }
    else if (t === 'subs')  { la.textContent = 'a (польза x)'; lb.textContent = 'b (польза y)'; }
    else if (t === 'compl') { la.textContent = 'a (доля x)';  lb.textContent = 'b (доля y)'; }
  }
}

function setConsumerType(t) {
  STATE.consType = t;
  const sel = document.getElementById('cons-type'); if (sel) sel.value = t;
  // Пресеты параметров под тип — чтобы сцена сразу была осмысленной.
  if (t === 'cobb')  { STATE.consA = 0.5; STATE.consB = 0.5; }
  if (t === 'subs')  { STATE.consA = 2;   STATE.consB = 1; }
  if (t === 'compl') { STATE.consA = 1;   STATE.consB = 2; }
  const ia = document.getElementById('cons-a'), ib = document.getElementById('cons-b');
  if (ia) ia.value = STATE.consA; if (ib) ib.value = STATE.consB;
  applyConsumerTypeUI();
  redrawAll();
}

