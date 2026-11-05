// Неравенство доходов: Лоренц, Джини, децили.
/* ---------------------------------------------------------------------
   БЛОК 13. НЕРАВЕНСТВО ДОХОДОВ (ЧК1–3).
   Оси: доля населения (X) и доля дохода (Y), обе 0..100 %. Кривая Лоренца,
   коэффициенты Джини / Робин Гуда (Гувера) / децильный / квинтильный.
   Все три способа ввода сводятся к массиву точек Лоренца {p, L} в долях 0..1.
   Поле графика — квадратное (свои шкалы 0..100, переопределяют общие).
   --------------------------------------------------------------------- */

// Разбор списка чисел из строки (через запятую/пробел/точку с запятой).
function parseNumberList(str) {
  return (str || '').split(/[\s,;]+/).map(s => s.trim()).filter(s => s.length)
    .map(Number).filter(v => !isNaN(v));
}

// Доли дохода по группам равного населения (фракции, сумма = 1) из текущего ввода
// 'groups'/'incomes'. Возвращает { shares, N, warn } или null. (Формула — отдельно.)
function inequalitySharesFromInput() {
  const r=ineqDistribution(ineqFirstConfig());
  return r.error?null:{shares:r.shares,pops:r.pops,N:r.shares?.length,warn:null,reordered:r.reordered,sortedGroups:r.sorted?.map(i=>STATE.ineqGroups[i])};
}

// Кривая Лоренца [[p, L], ...] из долей дохода по группам равного населения.
// Накопленные доли населения (k/N) против накопленных долей дохода. Начинается (0,0).
function lorenzFromShares(shares) {
  const N = shares.length, pts = [[0, 0]];
  let cum = 0;
  for (let k = 0; k < N; k++) { cum += shares[k]; pts.push([(k + 1) / N, Math.min(1, cum)]); }
  pts[pts.length - 1][1] = 1;   // закрываем ровно в (1,1)
  return pts;
}

// Кривая Лоренца из функции L(p) (переменная p, x — синоним). Возвращает { pts, warn, error }.
function lorenzFromFormula(expr) { return ineqDistribution({input:'formula',formula:expr}); }

// Площадь под кривой Лоренца (метод трапеций по вершинам). points = [[p, L], ...].
function lorenzAreaUnder(pts) {
  let area = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    if (isNaN(a[1]) || isNaN(b[1])) continue;
    area += (a[1] + b[1]) / 2 * (b[0] - a[0]);
  }
  return area;
}

// Интерполяция L на доле населения p (по ломаной Лоренца).
function lorenzAt(pts, p) {
  if (p <= 0) return 0;
  if (p >= 1) return pts[pts.length - 1][1];
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    if (p >= a[0] && p <= b[0] && b[0] > a[0]) { const t = (p - a[0]) / (b[0] - a[0]); return a[1] + t * (b[1] - a[1]); }
  }
  return NaN;
}

// Коэффициенты неравенства из кривой Лоренца.
//  Джини = 1 − 2∫L dp (площадь A между диагональю и кривой / 0.5).
//  Робин Гуда (Гувера) = max(p − L(p)) — макс. вертикальный разрыв (в вершине ломаной).
//  Децильный = (1 − L(0.9)) / L(0.1);  квинтильный = (1 − L(0.8)) / L(0.2).
function inequalityStats(pts) {
  const B = lorenzAreaUnder(pts);
  const gini = 1 - 2 * B;
  let hoover = 0, hooverP = 0;
  pts.forEach(pt => { if (!isNaN(pt[1])) { const d = pt[0] - pt[1]; if (d > hoover) { hoover = d; hooverP = pt[0]; } } });
  const L10 = lorenzAt(pts, 0.1), L90 = lorenzAt(pts, 0.9);
  const L20 = lorenzAt(pts, 0.2), L80 = lorenzAt(pts, 0.8);
  // Фаза 13. «Децильный коэффициент» в российской (росстатовской) традиции —
  // это КОЭФФИЦИЕНТ ФОНДОВ: отношение СУММАРНОГО дохода верхних 10 % населения
  // к СУММАРНОМУ доходу нижних 10 %. По кривой Лоренца это ровно
  // (1 − L(0.9)) / L(0.1): числитель — доля дохода верхней децили, знаменатель —
  // нижней. Деление на неравные группы даёт интерполяция внутри lorenzAt.
  const decile = (L10 > 1e-9) ? (1 - L90) / L10 : null;
  const quintile = (L20 > 1e-9) ? (1 - L80) / L20 : null;
  return { gini, hoover, hooverP, decile, funds: decile, quintile };
}

// Фаза 13. АЛЬТЕРНАТИВНАЯ метрика — отношение ПОРОГОВ P90/P10 (девятый дециль
// к первому). Это НЕ коэффициент фондов: там отношение сумм доходов групп, здесь —
// отношение граничных доходов. Считается только там, где известны сами доходы;
// для долей по группам и формулы Лоренца порогов нет — возвращаем null.
function inequalityP90P10() {
  if (STATE.ineqInput !== 'incomes') return null;
  const xs = parseNumberList(STATE.ineqIncomes).filter(v => v >= 0).sort((a, b) => a - b);
  const n = xs.length;
  if (n < 10) return null;
  const q = (p) => {                       // порядковая статистика с линейной интерполяцией
    const idx = (n - 1) * p, lo = Math.floor(idx), hi = Math.min(n - 1, lo + 1);
    return xs[lo] + (idx - lo) * (xs[hi] - xs[lo]);
  };
  const p10 = q(0.1), p90 = q(0.9);
  return (p10 > 1e-9) ? { p10, p90, ratio: p90 / p10 } : null;
}

// Доли дохода по группам равного населения для перераспределения (ЧК3).
// groups/incomes — берём готовые доли; formula — выделяем 10 децилей из кривой Лоренца.
function ineqRedistShares() {
  if (STATE.ineqInput === 'formula') {
    if (!STATE.ineqLorenz) return null;
    const N = 10, sh = [];
    for (let k = 1; k <= N; k++) sh.push(lorenzAt(STATE.ineqLorenz, k / N) - lorenzAt(STATE.ineqLorenz, (k - 1) / N));
    return sh;
  }
  return STATE.ineqShares ? STATE.ineqShares.slice() : null;
}

// Применить перераспределение к долям (сумма сохраняется = 1).
//  Налог: новая доля = (1−τ)·старая + τ·(1/N) — линейное подтягивание к равенству.
//  Трансферт: T% общего дохода забираем у богатейшей группы, делим поровну между всеми.
function applyRedistribution(shares, pops=shares.map(()=>1/shares.length)) {
  const N = shares.length;
  if (STATE.ineqRedistTool === 'tax') {
    const tau = Math.max(0, Math.min(1, STATE.ineqTau));
    return shares.map((s,i) => (1 - tau) * s + tau * pops[i]);
  }
  const T = Math.max(0, STATE.ineqTransfer) / 100;       // доля общего дохода
  const out = shares.slice();
  let ri = 0; for (let i = 1; i < N; i++) if (out[i]/pops[i] > out[ri]/pops[ri]) ri = i;   // богатейшая группа
  const take = Math.min(T, out[ri]);                     // нельзя забрать больше, чем у неё есть
  out[ri] -= take;
  for (let i = 0; i < N; i++) out[i] += take * pops[i];
  return out;
}

// Пересчёт неравенства БЕЗ рисования — складываем кривую и коэффициенты в STATE.
function recomputeInequality() {
  // Доли могут стать неравными или временно ошибочными при ручном вводе.
  // Сегмент «Равные группы» должен отражать их до любого раннего выхода.
  if(!TaxMotion.drawing)ineqRenderRows(document.getElementById('ineq-groups-table'),false);
  STATE.ineqLorenz=null;STATE.ineqStats=null;STATE.ineqWarn=null;STATE.ineqShares=null;STATE.ineqShareN=0;STATE.ineqRedist=null;STATE.ineqSortNote=false;
  const calc=ineqCalculate(),r=calc.result;STATE.ineqDistribution=r;STATE.ineqCountries=calc.countries;
  if(!TaxMotion.drawing)renderIneqCountryControls();
  if(r.error){STATE.ineqWarn=r.error;return;}
  STATE.ineqLorenz=r.pts;STATE.ineqStats=r.stats;STATE.ineqShares=r.shares||null;STATE.ineqShareN=r.shares?.length||0;
  const first=calc.first;
  if(STATE.ineqInput==='groups'&&first.reordered){
    STATE.ineqGroups=first.sorted.map(i=>STATE.ineqGroups[i]);if(STATE.ineqPops)STATE.ineqPops=first.sorted.map(i=>STATE.ineqPops[i]);renderIneqGroupsTable();
  }
  STATE.ineqSortNote=!!first.reordered;
  if(STATE.ineqRedistOn){
    if(STATE.ineqRedistTool==='tax'&&r.expr&&r.continuous){
      const tau=Math.max(0,Math.min(1,STATE.ineqTau));const rd=ineqDistribution({input:'formula',formula:'('+CalcNumber.expression(1-tau)+')*('+r.expr+')+('+CalcNumber.expression(tau)+')*p'});
      if(!rd.error)STATE.ineqRedist={lorenz:rd.pts,stats:rd.stats,distribution:rd};
    }else{
      const pts=r.pts,pops=r.pops||pts.slice(1).map((p,i)=>p[0]-pts[i][0]),shares=r.shares||pts.slice(1).map((p,i)=>p[1]-pts[i][1]);
      const ns=applyRedistribution(shares,pops),rd=ineqDistribution({input:'groups',groups:ns,pops});
      if(!rd.error)STATE.ineqRedist={lorenz:rd.pts,stats:rd.stats,distribution:rd};
    }
  }
}

// --- Отрисовка неравенства (квадратное поле, доли 0..100 %) ---

// Линия равенства (диагональ) — зелёный пунктир.
function drawInequalityDiagonal() {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  g.append('line').attr('x1', sx(0)).attr('y1', sy(0)).attr('x2', sx(100)).attr('y2', sy(100))
    .attr('stroke', COL.tax).attr('stroke-width', 1.8).attr('stroke-dasharray', '6 4');
  g.append('text').attr('x', sx(80)).attr('y', sy(86)).attr('font-size', FS.base).attr('fill', COL.tax)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Равенство');
}

// Подписи осей (длинные, рисуем сами; drawAxes вызываем без меток).
function drawInequalityCaptions() {
  const g = svg.append('g'), ox = sx(0), oy = sy(0), xMid = (sx(0) + sx(100)) / 2, yTop = sy(100);
  /* Подпись под осью стоит НИЖЕ строки чисел делений: числа висят от oy + 8
     и занимают около 13 px, поэтому прежние oy + 30 садились ровно на них
     (замер: «40» × «Доля населения, %» в трёх ширинах окна). Место под эту
     строку резервирует BOTTOM_BAND в 20-plane.js — они меняются вместе. */
  g.append('text').attr('x', xMid).attr('y', oy + 38).attr('text-anchor', 'middle')
    .attr('class', 'axis-name')
    .attr('font-size', FS.base).attr('fill', COL.inkSoft).text('N, %');
  g.append('text').attr('x', ox + 6).attr('y', yTop - 5).attr('text-anchor', 'start')
    .attr('class', 'axis-name')
    .attr('font-size', FS.base).attr('fill', COL.inkSoft).text('I, %');
}

/* Запись для .tex. По группам и по доходам кривая Лоренца — ломаная по
   точкам (доля населения; доля дохода): это её точный вид, а не приближение.
   По формуле L(p) — та же формула на осях в процентах: 100·L(x/100); буква p
   (и синоним x) подставляется деревом Math.js. */
function ineqDrawData(pts) {
  return [STATE.ineqDistribution,...(STATE.ineqCountries||[]),STATE.ineqRedist?.distribution].find(r=>r?.pts===pts);
}
function ineqPercentExpr(expr) {
  return '100*('+math.parse(expr).transform(n=>n.isSymbolNode&&n.name==='p'?math.parse('(x/100)'):n).toString()+')';
}
function lorenzPlotExpr(pts) {
  const r=ineqDrawData(pts);return r?.expr&&r.continuous?ineqPercentExpr(r.expr):null;
}
function lorenzMark(sel, pts, name='кривая Лоренца') {
  const r=ineqDrawData(pts),e=lorenzPlotExpr(pts);
  if(e)return markExpr(sel,e,'x',null,{name});
  if(r?.approx)return markNumeric(sel,'объединение пересекающихся распределений: численная кривая с проверкой сходимости',name);
  return markPoly(sel,'кривая Лоренца по группам: точная ломаная по долям населения и дохода',name);
}
// Площадь A (between: между диагональю и кривой) или B (под кривой).
function lorenzMarkArea(sel, pts, between) {
  const e = lorenzPlotExpr(pts);
  const ok = pts.every(d => !isNaN(d[1]));
  if (e && ok) return markArea(sel, { from: 0, to: 100, lo: between ? e : 0, hi: between ? 'x' : e, v: 'x' });
  if (STATE.ineqInput === 'formula') return markNumeric(sel, 'граница площади (кривая Лоренца) без записи формулой: площадь по точкам расчёта');
  return markPoly(sel, between ? 'площадь A между диагональю и ломаной Лоренца: многоугольник по вершинам'
    : 'площадь B под ломаной Лоренца: многоугольник по вершинам', between ? 'площадь A' : 'площадь B');
}

// Заливки A (между диагональю и кривой) и B (под кривой) — смысл Джини.
function drawInequalityAreas(pts) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const bArea = d3.area().defined(d => !isNaN(d[1])).x(d => sx(d[0] * 100)).y0(sy(0)).y1(d => sy(d[1] * 100));
  lorenzMarkArea(g.append('path').datum(pts).attr('d', bArea).attr('fill', COL.dwl).attr('opacity', 0.15), pts, false);
  const aArea = d3.area().defined(d => !isNaN(d[1])).x(d => sx(d[0] * 100)).y0(d => sy(d[0] * 100)).y1(d => sy(d[1] * 100));
  lorenzMarkArea(g.append('path').datum(pts).attr('d', aArea).attr('fill', COL.D).attr('opacity', 0.12), pts, true);
  g.append('text').attr('x', sx(33)).attr('y', sy(52)).attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.D).attr('opacity', 0.85).text('A');
  g.append('text').attr('x', sx(66)).attr('y', sy(18)).attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.dwl).attr('opacity', 0.85).text('B');
}

// Кривая Лоренца (доли 0..1 → проценты). dashed — для «было»/исходной.
function drawLorenzCurve(pts, color, dashed, thin=false, name='кривая Лоренца') {
  const g=svg.append('g').attr('clip-path','url(#plot-clip)'),r=ineqDrawData(pts);
  const line=d3.line().defined(d=>Number.isFinite(d[1])).x(d=>sx(d[0]*100)).y(d=>sy(d[1]*100));
  const parts=r?.continuous&&r.pieces?r.pieces:[null];
  for(const part of parts){
    let data=part?pts.filter(q=>q[0]>=part.lo-1e-12&&q[0]<=part.hi+1e-12):pts;
    if(data.length>1200){const step=Math.ceil(data.length/1000),last=data.at(-1);data=data.filter((_,i)=>i%step===0);if(data.at(-1)!==last)data.push(last);}
    const path=g.append('path').datum(data).attr('fill','none').attr('stroke',color).attr('stroke-width',thin?1.5:STATE.ineqCountries?3.4:2.6).attr('d',line);
    if(dashed)path.attr('stroke-dasharray','6 4').attr('opacity',.75);
    if(part)markExpr(path,ineqPercentExpr(part.expr),'x',null,{name});else lorenzMark(path,pts,name);
  }
}

// Вертикальный отрезок Робин Гуда в p* (макс. разрыв диагональ−кривая) + подпись.
function drawRobinHood() {
  const st = STATE.ineqStats, pts = STATE.ineqLorenz;
  if (!st || st.hoover <= 1e-9) return;
  const p = st.hooverP, L = lorenzAt(pts, p), x = sx(p * 100);
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  g.append('line').attr('x1', x).attr('y1', sy(L * 100)).attr('x2', x).attr('y2', sy(p * 100))
    .attr('stroke', COL.S).attr('stroke-width', 2.6);
  g.append('circle').attr('cx', x).attr('cy', sy(L * 100)).attr('r', 3).attr('fill', COL.S);
  g.append('circle').attr('cx', x).attr('cy', sy(p * 100)).attr('r', 3).attr('fill', COL.S);
  const ymid = sy((L + p) / 2 * 100);
  g.append('text').attr('x', x + 7).attr('y', ymid).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.S)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Робин Гуд ' + fmt(st.hoover));
}

// Узлы кривой Лоренца. В способах 'groups' и 'incomes' — перетаскиваемые
// (ЧК2 / Задача 2); в 'formula' — узлов нет.
function drawLorenzNodes() {
  if (STATE.ineqInput === 'formula' || STATE.ineqCountryB) return;
  const pts = STATE.ineqLorenz;
  const g = svg.append('g').attr('class','model-drag-handles');
  for (let i = 1; i < pts.length - 1; i++) {           // концы (0,0) и (1,1) зафиксированы
    const px = sx(pts[i][0] * 100), py = sy(pts[i][1] * 100);
    if (STATE.ineqInput === 'groups' || STATE.ineqInput === 'incomes') {
      const hit = g.append('circle').attr('cx', px).attr('cy', py).attr('r', 12).attr('fill', 'transparent').style('cursor', 'ns-resize');
      attachLorenzNodeDrag(hit, i);                     // ЧК2 (groups) / Задача 2 (incomes)
    }
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4)
      .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5).style('pointer-events', 'none');
  }
}

// Установить накопленную долю дохода в узле i = vFraction (доля 0..1), сохранив
// монотонность: зажимаем в [cumL[i−1], cumL[i+1]] (доли соседних групп ≥ 0).
// Меняются доли групп i−1 и i; остальные не трогаются; сумма остаётся 100%.
function ineqDragNode(i, vFraction) {
  const d=ineqDistribution(ineqFirstConfig());if(d.error)return;
  if(STATE.ineqGroupMode==='counts'){STATE.ineqPops=d.pops.map(x=>x*100);STATE.ineqGroups=d.shares.map(x=>x*100);STATE.ineqGroupMode='shares';}
  const g = d.shares.map(x=>x*100);
  const sum = g.reduce((a, b) => a + b, 0) || 1;
  const frac = g.map(x => Math.max(0, x) / sum);       // доли (сумма = 1)
  const cum = [0]; for (let k = 0; k < frac.length; k++) cum.push(cum[k] + frac[k]);
  if (i < 1 || i > frac.length - 1) return;            // только внутренние узлы
  let v = Math.max(cum[i - 1], Math.min(cum[i + 1], vFraction));
  cum[i] = v;
  const nf = []; for (let k = 0; k < frac.length; k++) nf.push(cum[k + 1] - cum[k]);
  STATE.ineqGroups = nf.map(f => Math.round(f * 1000) / 10);   // обратно в % (сумма = 100)
}

// Перетаскивание узла i в способе 'incomes' = изменение дохода человека i.
// Узел i (1..N−1) соответствует i-му человеку отсортированного списка (богатейший N
// закреплён в (1,1)). Целевая накопленная доля v → новый доход человека i =
// (v·T − кумул. доход до i−1). Зажим между доходами соседей сохраняет порядок (→ вогнутость).
function ineqDragIncome(i, vFraction) {
  const xs = parseNumberList(STATE.ineqIncomes).filter(v => v >= 0).sort((a, b) => a - b);
  const N = xs.length;
  if (i < 1 || i > N - 1) return;                      // последний человек закреплён
  const T = xs.reduce((a, b) => a + b, 0) || 1;
  let cumPrev = 0; for (let k = 0; k < i - 1; k++) cumPrev += xs[k];
  const lo = (i >= 2) ? xs[i - 2] : 0;                 // доход предыдущего человека (или 0)
  const hi = xs[i];                                    // доход следующего человека
  let xnew = vFraction * T - cumPrev;
  xnew = Math.max(lo, Math.min(hi, xnew));
  xs[i - 1] = Math.round(xnew * 100) / 100;
  STATE.ineqIncomes = xs.join(', ');
}

// Перетаскивание узла i кривой Лоренца по вертикали. Способ 'groups' (ЧК2) —
// меняется накопленная доля дохода → доли соседних групп; способ 'incomes' (Задача 2)
// — меняется доход соответствующего человека. Общий механизм, разная логика.
function attachLorenzNodeDrag(sel, i) {
  sel.call(d3.drag().container(() => svg.node())
    .on('start', () => { TaxMotion.hold();document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => {
      const v = sy.invert(event.y) / 100;              // тянем по Y (доля дохода, 0..1)
      if (STATE.ineqInput === 'incomes') {
        ineqDragIncome(i, v);
        const inc = document.getElementById('ineq-incomes'); if (inc) inc.value = STATE.ineqIncomes;
      } else {
        ineqDragNode(i, v);
        renderIneqGroupsTable();
      }
      if (typeof ineqMasterDetach === 'function') ineqMasterDetach();   // ручная правка узла → отвязка мастера
      redrawAll();
    })
    .on('end', () => { TaxMotion.release();document.body.style.cursor = ''; }));
}

// Стрелка «налог подтянул кривую к равенству» (ЧК3) — от «до» к «после» в p=0.5.
function drawRedistArrow(base, redist) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const p = 0.5, Lb = lorenzAt(base, p), Lr = lorenzAt(redist, p);
  if (isNaN(Lb) || isNaN(Lr) || Lr <= Lb + 1e-6) return;
  const x = sx(p * 100), y0 = sy(Lb * 100), y1 = sy(Lr * 100);
  g.append('line').attr('x1', x).attr('y1', y0).attr('x2', x).attr('y2', y1)
    .attr('stroke', COL.tax).attr('stroke-width', 1.6);
  markPoly(g.append('path').attr('d', `M${x - 4},${y1 + 6} L${x},${y1} L${x + 4},${y1 + 6}`)
    .attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 1.6), 'наконечник стрелки «к равенству»: ломаная по трём точкам');
  g.append('text').attr('x', x + 8).attr('y', (y0 + y1) / 2).attr('font-size', FS.small).attr('font-weight', 600).attr('fill', COL.tax)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('К равенству');
}

// Подсказка о пересортировке — показываем только в активном способе ввода и только
// когда сортировка реально изменила порядок (STATE.ineqSortNote).
function updateIneqSortNote() {
  const ng = document.getElementById('ineq-note-groups');
  const ni = document.getElementById('ineq-note-incomes');
  if (ng) ng.style.display = (STATE.ineqSortNote && STATE.ineqInput === 'groups') ? '' : 'none';
  if (ni) ni.style.display = (STATE.ineqSortNote && STATE.ineqInput === 'incomes') ? '' : 'none';
}

// Табло неравенства.
function updateInequalityPanel() {
  if(TaxMotion.drawing)return;
  const box = document.getElementById('info-inequality'); if (!box) return;
  if (!STATE.ineqStats) { setFinalFunctions([]);box.innerHTML = '<div class="warn">' + ffEsc(STATE.ineqWarn || 'Введите данные.') + '</div>'; return; }
  const s = STATE.ineqStats,r=STATE.ineqDistribution;
  setFinalFunctions([{name:STATE.ineqCountries?'Кривая Лоренца союза':'Кривая Лоренца',color:COL.D,...(r.expr?{expr:r.expr,lhs:'L(p)'}:{note:'Построена численно: диапазоны доходов стран пересекаются. Явная кусочная формула не найдена.'})}]);
  const coefficient=(v,available)=>available===false?'Недостаточно данных':v==null?'Не определён':fmt(v);
  let html = '';
  if (STATE.ineqWarn) html += '<div class="warn" style="margin-bottom:6px;">' + STATE.ineqWarn + '</div>';
  html += `<div class="stat"><span>Коэффициент Джини</span><b>${r.approx?'≈ '+Number(s.gini.toFixed(3)).toLocaleString('ru-RU',{maximumFractionDigits:3}):fmt(s.gini)}</b></div>`;
  html += `<div class="stat"><span>Робин Гуда (Гувера)</span><b>${fmt(s.hoover)}</b></div>`;
  // Фаза 13: явные подписи — что именно показано.
  html += `<div class="stat"><span>Коэф. фондов (децильный)</span><b>${coefficient(s.decile,s.decileAvailable)}</b></div>`;
  html += `<div class="stat"><span>Квинтильный коэф. фондов</span><b>${coefficient(s.quintile,s.quintileAvailable)}</b></div>`;
  if(STATE.ineqCountries){STATE.ineqCountries.forEach((c,i)=>{html+=`<div class="stat"><span>Джини страны ${i?'B':'A'}</span><b>${fmt(c.stats.gini)}</b></div>`;});}
  if(s.decileAvailable===false||s.quintileAvailable===false)html+='<div class="hint">Для коэффициента нужны границы соответствующих групп. Доходы внутри укрупнённой группы не известны; людей на части не делим.</div>';
  const pp = STATE.ineqCountries?null:inequalityP90P10();
  if (pp) {
    html += `<div class="stat"><span>$\\frac{P_{90}}{P_{10}}$ (пороги)</span><b>${fmt(pp.ratio)}</b></div>`;
    html += `<div class="hint">Это ДВЕ разные величины. <b>Коэффициент фондов</b> это отношение
      суммарного дохода верхних 10&nbsp;% населения к суммарному доходу нижних 10&nbsp;%
      (российская, росстатовская традиция; здесь ${fmt(s.decile)}). <b>P90/P10</b> это отношение
      граничных доходов: девятого дециля (${fmt(pp.p90)}) к первому (${fmt(pp.p10)}),
      здесь ${fmt(pp.ratio)}. Фонды учитывают «хвост» самых богатых, а пороги нет.</div>`;
  }
  /* «Показан коэффициент фондов…» убрано (сессия 5, А4): вопрос «Разбора» «Чем отличается коэффициент фондов?»;
     «пороги — только по способу ввода «Доходы»» — интерфейс. */
  // Перераспределение «до → после» (ЧК3) — имеет приоритет над снимком ЧК2.
  if (STATE.ineqRedist) {
    const r = STATE.ineqRedist.stats, d = r.gini - s.gini;
    html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
    html += `<div class="stat"><span>Джини до</span><b>${fmt(s.gini)}</b></div>`;
    html += `<div class="stat"><span>Джини после</span><b>${fmt(r.gini)}</b></div>`;
    html += `<div class="stat"><span>Δ Джини</span><b style="color:${d < -1e-6 ? COL.tax : (d > 1e-6 ? COL.S : COL.inkSoft)}">${d >= 0 ? '+' : ''}${fmt(d)}</b></div>`;
    html += `<div class="stat"><span>Робин Гуда до/после</span><b>${fmt(s.hoover)} / ${fmt(r.hoover)}</b></div>`;
  }
  html += '<div class="hint" style="margin-top:6px;">Робин Гуда показывает, какую долю дохода нужно перераспределить для равенства (макс. разрыв с диагональю). ' +
    'Дец./квинт. показывают, во сколько раз доход верхних 10%/20% больше дохода нижних.</div>';
  box.innerHTML = html;
}

// Полная перерисовка режима «Неравенство». Поле — квадратное (свои шкалы 0..100).
function redrawInequality() {
  recomputeInequality();
  const m = CONFIG.margin;
  const availW = W - m.left - m.right, availH = H - m.top - m.bottom;
  const side = Math.max(60, Math.min(availW, availH));
  /* Окно квадрата: 0…100 по обеим осям, пока человек не покрутил колесо.
     ⚠️ КВАДРАТ ОСТАЁТСЯ КВАДРАТОМ при любом зуме — обе оси меняются на один и
     тот же множитель (за это отвечает panelZoomBy). Оси здесь несут проценты,
     и растянуть одну без другой значит соврать про смысл картинки. */
  const wnd = panelWin('lorenz', 0, 100, 0, 100);
  sx = d3.scaleLinear().domain([wnd.x0, wnd.x1]).range([m.left, m.left + side]);
  sy = d3.scaleLinear().domain([wnd.y0, wnd.y1]).range([m.top + side, m.top]);
  /* Поле здесь КВАДРАТ со своими шкалами 0…100, а не холст целиком: слой
     поверх сцены обязан считать по ним. Раньше кривая Лоренца рисовалась в
     квадрате, а вершины площадей и ключевые точки — по шкале на всю ширину:
     координаты были правильные, а нарисованы не там. */
  clearPanels();
  registerPanel('lorenz', sx, sy,
    { x0: m.left, y0: m.top, x1: m.left + side, y1: m.top + side });
  svg.selectAll('*').remove();
  addDefs();
  drawGrid();
  // Подписи осей рисует drawInequalityCaptions, но названия сообщаем — их
  // забирает выгрузка в .tex (Б37).
  /* Правило 46: `N` — доля населения, `I` — доля дохода; обе оси несут
     процент, поэтому единица стоит через запятую. Расшифровка — в подписи
     под графиком и в панели расчётов. */
  drawAxes('', '', { xName: 'N, %', yName: 'I, %' });
  drawInequalityCaptions();
  if (STATE.ineqStats && STATE.ineqLorenz) {
    if (STATE.ineqRedist) {
      // ЧК3: перераспределение — «до» (пунктир) и «после» (сплошная) + стрелка к равенству.
      drawInequalityDiagonal();
      drawLorenzCurve(STATE.ineqLorenz, COL.dwl, true);          // до перераспределения
      drawLorenzCurve(STATE.ineqRedist.lorenz, COL.tax, false);  // после
      drawRedistArrow(STATE.ineqLorenz, STATE.ineqRedist.lorenz);
    } else {
      drawInequalityAreas(STATE.ineqLorenz);
      drawInequalityDiagonal();
      if(STATE.ineqCountries){STATE.ineqCountries.forEach((c,i)=>drawLorenzCurve(c.pts,i?COL.S:COL.dwl,false,true,'страна '+(i?'B':'A')));}
      drawLorenzCurve(STATE.ineqLorenz, COL.D, false,false,STATE.ineqCountries?'союз':'кривая Лоренца');
      drawRobinHood();
      if(STATE.ineqCountries){const legend=svg.append('g');[['Страна A',COL.dwl,1.5],['Страна B',COL.S,1.5],['Союз',COL.D,3.4]].forEach(([label,color,width],i)=>{const x=sx(5),y=sy(96)+i*20;legend.append('line').attr('x1',x).attr('x2',x+22).attr('y1',y).attr('y2',y).attr('stroke',color).attr('stroke-width',width);legend.append('text').attr('x',x+29).attr('y',y+4).attr('font-size',FS.small).attr('fill',COL.inkSoft).text(label);});}
      drawLorenzNodes();
    }
  }
  updateInequalityPanel();
  updateIneqSortNote();
}

// Доли дохода по группам по умолчанию (умеренное неравенство, сумма = 100%).
function defaultGroupShares(n) {
  if (n === 5) return [8, 12, 16, 24, 40];
  if (n === 10) return [3, 4, 5, 6, 8, 9, 11, 13, 16, 25];
  const arr = []; for (let i = 0; i < n; i++) arr.push(100 / n); return arr;   // запасной вариант
}

// Переключатель способа ввода неравенства: доли по группам / доходы / формула.
function setIneqInput(which) {
  STATE.ineqInput = which;
  [['ineq-in-groups', 'groups'], ['ineq-in-incomes', 'incomes'], ['ineq-in-formula', 'formula']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === which); });
  const panes = { groups: 'ineq-pane-groups', incomes: 'ineq-pane-incomes', formula: 'ineq-pane-formula' };
  Object.values(panes).forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; });
  const ap = document.getElementById(panes[which]); if (ap) ap.style.display = '';
  if (which === 'groups') renderIneqGroupsTable();
  // Свежий способ ввода — сбрасываем мастер «Сила неравенства» (база = текущий профиль на 100 %).
  STATE.ineqMasterBase = null; STATE.ineqMasterDetached = false; STATE.ineqMasterS = 1;
  if (typeof updatePult === 'function') updatePult();   // α (формула) ↔ мастер (доли/доходы)
  redrawAll();
}

// Задача 3: установить α → формула становится p^α, кривая и коэффициенты пересчитываются.
// Синхронизирует ползунок, число и поле формулы. Джини считается общим интегральным
// методом (для p^α совпадает с (α−1)/(α+1)), отдельной формулы не нужно.
function setIneqAlpha(a) {
  a=Number(a);if(!Number.isFinite(a)||a<1)a=1;STATE.ineqAlpha=a;
  const sl=document.getElementById('ineq-alpha'),val=document.getElementById('ineq-alpha-val');if(sl)sl.value=a;if(val)val.textContent=TaxMotion.formatRate(a);
  ineqRedraw();
}

// Сменить число групп (5 квинтилей / 10 децилей): сбрасывает доли на пресет.
function setIneqGroupN(n) {
  n = parseInt(n) || 5;
  STATE.ineqGroupN = n;
  STATE.ineqGroups = defaultGroupShares(n);
  delete STATE.ineqPops;delete STATE.ineqGroupMode;
  renderIneqGroupsTable();
  if (typeof ineqMasterDetach === 'function') ineqMasterDetach();   // новый профиль → мастер перебазируется
  if (typeof updatePult === 'function') updatePult();
  redrawAll();
}

// Переключатель инструмента перераспределения: прогрессивный налог / трансферт (ЧК3).
function setIneqRedistTool(tool) {
  STATE.ineqRedistTool = tool;
  [['ineq-rd-tax', 'tax'], ['ineq-rd-transfer', 'transfer']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === tool); });
  const tf = document.getElementById('ineq-tau-field'), trf = document.getElementById('ineq-transfer-field');
  if (tf) tf.style.display = (tool === 'tax') ? '' : 'none';
  if (trf) trf.style.display = (tool === 'transfer') ? '' : 'none';
  redrawAll();
}

// Таблица долей по группам (поля ввода %). Перерисовывается при смене N и при входе в режим.
function renderIneqGroupsTable() { if(TaxMotion.drawing)return;ineqRenderRows(document.getElementById('ineq-groups-table'),false);renderIneqCountryControls(true); }
