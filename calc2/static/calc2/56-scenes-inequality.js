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
  if (STATE.ineqInput === 'groups') {
    const g0 = STATE.ineqGroups.map(Number).filter(v => !isNaN(v));
    const N = g0.length;
    if (N < 2) return null;
    // Кривая Лоренца строится от беднейших к богатейшим → доли групп ОБЯЗАНЫ идти
    // по неубыванию (иначе кривая теряет вогнутость). Сортируем по возрастанию.
    const g = g0.slice().sort((a, b) => a - b);
    const reordered = g.some((v, i) => v !== g0[i]);   // порядок реально изменился?
    const sum = g.reduce((a, b) => a + b, 0);
    if (!(sum > 0)) return null;
    let warn = null;
    if (Math.abs(sum - 100) > 0.5) warn = 'Сумма долей = ' + fmt(sum) + '% (нормировано до 100%).';
    return { shares: g.map(v => Math.max(0, v) / sum), N, warn, reordered, sortedGroups: g };
  }
  if (STATE.ineqInput === 'incomes') {
    const xs0 = parseNumberList(STATE.ineqIncomes).filter(v => v >= 0);
    if (xs0.length < 2) return null;
    const xs = xs0.slice().sort((a, b) => a - b);
    const reordered = xs.some((v, i) => v !== xs0[i]);   // ввод был не по возрастанию?
    const total = xs.reduce((a, b) => a + b, 0);
    if (!(total > 0)) return null;
    return { shares: xs.map(v => v / total), N: xs.length, warn: null, reordered };
  }
  return null;
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
function lorenzFromFormula(expr) {
  let compiled;
  try { compiled = math.parse(prepExpr(expr)).compile(); compiled.evaluate(scopeFor(expr, { p: 0.5, x: 0.5 })); }
  catch (e) { return { pts: null, error: e.message }; }
  const N = 100, pts = [];
  for (let i = 0; i <= N; i++) {
    const p = i / N;
    let L;
    try { const v = compiled.evaluate(paramScope({ p: p, x: p })); L = (typeof v === 'number' && isFinite(v)) ? v : NaN; }
    catch (e) { L = NaN; }
    pts.push([p, L]);
  }
  // Мягкая проверка корректности функции Лоренца (рисуем в любом случае).
  let warn = null;
  const L0 = pts[0][1], L1 = pts[pts.length - 1][1];
  if (isNaN(L0) || isNaN(L1)) warn = 'Функция не вычисляется на всём [0,1].';
  else if (Math.abs(L0) > 0.02 || Math.abs(L1 - 1) > 0.02) warn = 'Ожидается L(0)=0 и L(1)=1.';
  else { for (let i = 1; i < pts.length; i++) { if (!isNaN(pts[i][1]) && !isNaN(pts[i - 1][1]) && pts[i][1] < pts[i - 1][1] - 1e-6) { warn = 'L(p) должна быть неубывающей.'; break; } } }
  return { pts, warn };
}

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
  if (n < 2) return null;
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
function applyRedistribution(shares) {
  const N = shares.length;
  if (STATE.ineqRedistTool === 'tax') {
    const tau = Math.max(0, Math.min(1, STATE.ineqTau));
    return shares.map(s => (1 - tau) * s + tau * (1 / N));
  }
  const T = Math.max(0, STATE.ineqTransfer) / 100;       // доля общего дохода
  const out = shares.slice();
  let ri = 0; for (let i = 1; i < N; i++) if (out[i] > out[ri]) ri = i;   // богатейшая группа
  const take = Math.min(T, out[ri]);                     // нельзя забрать больше, чем у неё есть
  out[ri] -= take;
  for (let i = 0; i < N; i++) out[i] += take / N;
  return out;
}

// Пересчёт неравенства БЕЗ рисования — складываем кривую и коэффициенты в STATE.
function recomputeInequality() {
  STATE.ineqLorenz = null; STATE.ineqStats = null; STATE.ineqWarn = null;
  STATE.ineqShares = null; STATE.ineqShareN = 0; STATE.ineqRedist = null;
  STATE.ineqSortNote = false;
  if (STATE.ineqInput === 'formula') {
    const r = lorenzFromFormula(STATE.ineqFormula);
    if (!r.pts) { STATE.ineqWarn = 'Не понял формулу: ' + (r.error || ''); return; }
    STATE.ineqLorenz = r.pts; STATE.ineqWarn = r.warn;
    STATE.ineqStats = inequalityStats(r.pts);
  } else {
    const s = inequalitySharesFromInput();
    if (!s) { STATE.ineqWarn = 'Введите хотя бы две группы / два дохода.'; return; }
    // Если сортировка реально переставила группы — фиксируем порядок в таблице и
    // показываем мягкую подсказку (только при настоящей пересортировке).
    if (STATE.ineqInput === 'groups' && s.reordered && s.sortedGroups) {
      STATE.ineqGroups = s.sortedGroups.slice();
      renderIneqGroupsTable();
    }
    STATE.ineqSortNote = !!s.reordered;
    STATE.ineqShares = s.shares; STATE.ineqShareN = s.N; STATE.ineqWarn = s.warn;
    STATE.ineqLorenz = lorenzFromShares(s.shares);
    STATE.ineqStats = inequalityStats(STATE.ineqLorenz);
  }
  // Перераспределение (ЧК3): строим «после» из текущих долей.
  if (STATE.ineqRedistOn && STATE.ineqLorenz) {
    const sh = ineqRedistShares();
    if (sh) {
      const ns = applyRedistribution(sh);
      // Вогнутость: кривая Лоренца строится от беднейших к богатейшим. Трансферт может
      // сделать бывшую богатейшую группу не самой богатой — сортируем доли по возрастанию,
      // как при ручном вводе. Налог порядок не переворачивает, для него это идемпотентно.
      ns.sort((a, b) => a - b);
      const rl = lorenzFromShares(ns);
      STATE.ineqRedist = { lorenz: rl, stats: inequalityStats(rl) };
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

// Заливки A (между диагональю и кривой) и B (под кривой) — смысл Джини.
function drawInequalityAreas(pts) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const bArea = d3.area().defined(d => !isNaN(d[1])).x(d => sx(d[0] * 100)).y0(sy(0)).y1(d => sy(d[1] * 100));
  g.append('path').datum(pts).attr('d', bArea).attr('fill', COL.dwl).attr('opacity', 0.15);
  const aArea = d3.area().defined(d => !isNaN(d[1])).x(d => sx(d[0] * 100)).y0(d => sy(d[0] * 100)).y1(d => sy(d[1] * 100));
  g.append('path').datum(pts).attr('d', aArea).attr('fill', COL.D).attr('opacity', 0.12);
  g.append('text').attr('x', sx(33)).attr('y', sy(52)).attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.D).attr('opacity', 0.85).text('A');
  g.append('text').attr('x', sx(66)).attr('y', sy(18)).attr('font-size', FS.large).attr('font-weight', 600).attr('fill', COL.dwl).attr('opacity', 0.85).text('B');
}

// Кривая Лоренца (доли 0..1 → проценты). dashed — для «было»/исходной.
function drawLorenzCurve(pts, color, dashed) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => !isNaN(d[1])).x(d => sx(d[0] * 100)).y(d => sy(d[1] * 100));
  const path = g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2.6).attr('d', line);
  if (dashed) path.attr('stroke-dasharray', '6 4').attr('opacity', 0.75);
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
  if (STATE.ineqInput === 'formula') return;
  const pts = STATE.ineqLorenz;
  const g = svg.append('g');
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
  const g = STATE.ineqGroups.map(Number);
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
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
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
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Стрелка «налог подтянул кривую к равенству» (ЧК3) — от «до» к «после» в p=0.5.
function drawRedistArrow(base, redist) {
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const p = 0.5, Lb = lorenzAt(base, p), Lr = lorenzAt(redist, p);
  if (isNaN(Lb) || isNaN(Lr) || Lr <= Lb + 1e-6) return;
  const x = sx(p * 100), y0 = sy(Lb * 100), y1 = sy(Lr * 100);
  g.append('line').attr('x1', x).attr('y1', y0).attr('x2', x).attr('y2', y1)
    .attr('stroke', COL.tax).attr('stroke-width', 1.6);
  g.append('path').attr('d', `M${x - 4},${y1 + 6} L${x},${y1} L${x + 4},${y1 + 6}`)
    .attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 1.6);
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
  const box = document.getElementById('info-inequality'); if (!box) return;
  if (!STATE.ineqStats) { box.innerHTML = '<div class="warn">' + (STATE.ineqWarn || 'Введите данные.') + '</div>'; return; }
  const s = STATE.ineqStats;
  let html = '';
  if (STATE.ineqWarn) html += '<div class="warn" style="margin-bottom:6px;">' + STATE.ineqWarn + '</div>';
  html += `<div class="stat"><span>Коэффициент Джини</span><b>${fmt(s.gini)}</b></div>`;
  html += `<div class="stat"><span>Робин Гуда (Гувера)</span><b>${fmt(s.hoover)}</b></div>`;
  // Фаза 13: явные подписи — что именно показано.
  html += `<div class="stat"><span>Коэф. фондов (децильный)</span><b>${s.decile == null ? '∞' : fmt(s.decile)}</b></div>`;
  html += `<div class="stat"><span>Квинтильный коэф. фондов</span><b>${s.quintile == null ? '∞' : fmt(s.quintile)}</b></div>`;
  const pp = inequalityP90P10();
  if (pp) {
    html += `<div class="stat"><span>$\\frac{P_{90}}{P_{10}}$ (пороги)</span><b>${fmt(pp.ratio)}</b></div>`;
    html += `<div class="hint">Это ДВЕ разные величины. <b>Коэффициент фондов</b> это отношение
      суммарного дохода верхних 10&nbsp;% населения к суммарному доходу нижних 10&nbsp;%
      (российская, росстатовская традиция; здесь ${fmt(s.decile)}). <b>P90/P10</b> это отношение
      граничных доходов: девятого дециля (${fmt(pp.p90)}) к первому (${fmt(pp.p10)}),
      здесь ${fmt(pp.ratio)}. Фонды учитывают «хвост» самых богатых, а пороги нет.</div>`;
  } else {
    html += '<div class="hint">Показан <b>коэффициент фондов</b>: отношение суммарного дохода ' +
      'верхних 10&nbsp;% к суммарному доходу нижних 10&nbsp;% (не отношение порогов P90/P10, ' +
      'это другая величина). Пороги можно посчитать только по способу ввода «Доходы».</div>';
  }
  // Перераспределение «до → после» (ЧК3) — имеет приоритет над снимком ЧК2.
  if (STATE.ineqRedist) {
    const r = STATE.ineqRedist.stats, d = r.gini - s.gini;
    html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
    html += `<div class="stat"><span>Джини до</span><b>${fmt(s.gini)}</b></div>`;
    html += `<div class="stat"><span>Джини после</span><b>${fmt(r.gini)}</b></div>`;
    html += `<div class="stat"><span>Δ Джини</span><b style="color:${d < -1e-6 ? COL.tax : (d > 1e-6 ? COL.S : COL.inkSoft)}">${d >= 0 ? '+' : ''}${fmt(d)}</b></div>`;
    html += `<div class="stat"><span>Робин Гуда до/после</span><b>${fmt(s.hoover)} / ${fmt(r.hoover)}</b></div>`;
  }
  html += '<div class="hint" style="margin-top:6px;">Джини: 0 значит полное равенство, 1 значит весь доход у одного. ' +
    'Робин Гуда показывает, какую долю дохода нужно перераспределить для равенства (макс. разрыв с диагональю). ' +
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
      drawLorenzCurve(STATE.ineqLorenz, COL.D, false);
      drawRobinHood();
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
  a = parseFloat(a);
  if (isNaN(a) || a < 1) a = 1;
  STATE.ineqAlpha = Math.round(a * 100) / 100;
  STATE.ineqFormula = 'p^' + STATE.ineqAlpha;
  // Отдельного числового поля α больше нет (01.09): точное значение вводится
  // щелчком по самому ползунку, общим компонентом регулятора.
  const sl = document.getElementById('ineq-alpha'),
        val = document.getElementById('ineq-alpha-val'), fm = document.getElementById('ineq-formula');
  if (sl) sl.value = STATE.ineqAlpha;
  if (val) val.textContent = fmt(STATE.ineqAlpha);
  if (fm) fm.value = STATE.ineqFormula;
  ineqRedraw();   // живой ползунок α — пересчёт троттлом (без мигания)
}

// Сменить число групп (5 квинтилей / 10 децилей): сбрасывает доли на пресет.
function setIneqGroupN(n) {
  n = parseInt(n) || 5;
  STATE.ineqGroupN = n;
  STATE.ineqGroups = defaultGroupShares(n);
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
function renderIneqGroupsTable() {
  const box = document.getElementById('ineq-groups-table'); if (!box) return;
  box.innerHTML = '';
  STATE.ineqGroups.forEach((v, i) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:4px;';
    const lab = document.createElement('span');
    lab.style.cssText = 'font-size:' + FS.base + 'px;color:var(--text2);width:78px;';
    lab.textContent = 'Группа ' + (i + 1);
    const inp = document.createElement('input');
    inp.type = 'number'; inp.step = '0.1'; inp.value = v;
    // Вид берём из общего правила панели (Н75): рамки нет, снизу пунктир.
    // Своя рамка в inline-стиле била бы любое правило по специфичности.
    inp.style.flex = '1';
    inp.addEventListener('change', () => { const nv = parseFloat(inp.value); if (!isNaN(nv)) { STATE.ineqGroups[i] = nv; if (typeof ineqMasterDetach === 'function') ineqMasterDetach(); redrawAll(); } });
    row.appendChild(lab); row.appendChild(inp); box.appendChild(row);
  });
}

