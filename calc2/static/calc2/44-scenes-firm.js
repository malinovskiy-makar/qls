// Фирма: издержки, производство, изокванты, два завода.
/* ---------------------------------------------------------------------
   БЛОК 10. ИЗДЕРЖКИ ФИРМЫ — кривые MC/ATC/AVC/AFC из TC и FC (Задача 2).
   База — суммарные затраты TC(Q) и постоянные FC. Остальное выводится:
     VC = TC − FC,  ATC = TC/Q,  AVC = VC/Q,  AFC = FC/Q,  MC = d(TC)/dQ.
   MC — численная производная (центральная разность), работает для любой TC.
   --------------------------------------------------------------------- */

/* До какого выпуска ищутся минимумы средних и корень P = MC. Число ПОСТОЯННОЕ
   и от окна не зависит: минимум AVC — свойство функции затрат, а не текущего
   масштаба, и не должен меняться от прокрутки колеса. Если человек отодвинул
   окно дальше этого предела, ищем до края окна (зависимость односторонняя,
   поэтому обратной связи «скан двигает окно, окно двигает скан» здесь нет —
   в отличие от заводов, где именно она когда-то раздувала ось). */
const COST_SCAN_Q = 200;
function costScanTop() { return Math.max(COST_SCAN_Q, CONFIG.Qmax); }
// Малый Q > 0: у средних кривых при Q → 0 значения уходят в бесконечность.
const COST_SCAN_LO = 1e-3;

// Значение TC(Q) по компилированной формуле (Q и x — обе переменные).
function evalTC(q) {
  if (!STATE.costsCompiled) return NaN;
  try { const v = STATE.costsCompiled.evaluate(paramScope(axisScope(q))); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
  catch (e) { return NaN; }
}

/* Значение отдельно заданной кривой режима «по отдельности».
   STATE.costsParts хранит скомпилированные формулы; пустое поле = кривая
   не задана, и наружу уходит NaN, а не выдуманное число. */
function evalPart(key, q) {
  const c = STATE.costsParts && STATE.costsParts[key];
  if (!c) return NaN;
  try { const v = c.evaluate(paramScope(axisScope(q))); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
  catch (e) { return NaN; }
}
function hasPart(key) { return !!(STATE.costsParts && STATE.costsParts[key]); }

/* Постоянные затраты. В режиме «задаю TC» это TC(0) — определение, а не
   соглашение. В режиме «задаю кривые» постоянные берутся из разности средних:
   AFC = ATC − AVC, значит FC = (ATC − AVC)·Q. */
function costsFC() {
  const info = STATE.costsFCInfo;
  return (info && info.kind !== 'none') ? info.val : NaN;
}

function costTC(q)  {
  if (STATE.costsMode === 'curves') {
    const atc = evalPart('ATC', q);
    if (!isNaN(atc)) return atc * q;
    const avc = evalPart('AVC', q), fc = costsFC();
    return (isNaN(avc) || isNaN(fc)) ? NaN : avc * q + fc;
  }
  return evalTC(q);
}
function costVC(q)  {
  if (STATE.costsMode === 'curves') { const a = evalPart('AVC', q); return isNaN(a) ? NaN : a * q; }
  const tc = evalTC(q), fc = costsFC();
  return (isNaN(tc) || isNaN(fc)) ? NaN : tc - fc;               // переменные = TC − FC
}
function costATC(q) {
  if (STATE.costsMode === 'curves') return evalPart('ATC', q);
  const tc = evalTC(q); return isNaN(tc) ? NaN : tc / q;          // средние общие
}
function costAVC(q) {
  if (STATE.costsMode === 'curves') return evalPart('AVC', q);
  const vc = costVC(q); return isNaN(vc) ? NaN : vc / q;          // средние переменные
}
function costAFC(q) {
  if (STATE.costsMode === 'curves') {
    const atc = evalPart('ATC', q), avc = evalPart('AVC', q);
    return (isNaN(atc) || isNaN(avc)) ? NaN : atc - avc;
  }
  const fc = costsFC(); return isNaN(fc) ? NaN : fc / q;          // средние постоянные
}
// MC = d(TC)/dQ численно (центральная разность) — как mcAt для TC.
function costMC(q) {
  if (STATE.costsMode === 'curves') return evalPart('MC', q);
  const h = Math.max(1e-4, CONFIG.Qmax * 1e-5);
  const a = evalTC(q + h), b = evalTC(q - h);
  return (isNaN(a) || isNaN(b)) ? NaN : (a - b) / (2 * h);
}
// Есть ли у сцены эта кривая вообще (в режиме «по отдельности» — только заданные).
function costHas(name) {
  if (STATE.costsMode !== 'curves') {
    // Без постоянных затрат нет ни VC, ни AVC, ни AFC.
    if (name === 'VC' || name === 'AVC' || name === 'AFC' || name === 'FC') return !isNaN(costsFC());
    return true;
  }
  if (name === 'MC' || name === 'ATC' || name === 'AVC') return hasPart(name);
  if (name === 'AFC' || name === 'VC' || name === 'FC') return hasPart('ATC') && hasPart('AVC');
  if (name === 'TC') return hasPart('ATC');
  return false;
}

/* Минимум функции f на [qLo, qHi] с ЧЕСТНЫМ ответом о том, что найдено (Б26).

   Прежняя версия возвращала «наименьшее из просканированного». Если
   внутреннего минимума нет, наружу уходила ГРАНИЦА ОТРЕЗКА — то есть край
   цикла for, выданный за экономическую величину: у TC = Q² + 18 средние
   переменные AVC = Q растут всюду, а панель писала «Закрытие (min AVC):
   Q = 0,5, AVC = 0,5».

   kind: 'interior' — настоящий внутренний минимум (только его и можно
                      показывать числом);
         'boundary' — функция монотонна, наименьшее значение на краю отрезка;
         'flat'     — функция постоянна, минимума нет. */
function minOf(f, qLo, qHi) {
  let bestQ = null, bestV = Infinity, topV = -Infinity;
  const scan = (lo, hi, n) => {
    for (let i = 0; i <= n; i++) {
      const q = lo + (hi - lo) * i / n, v = f(q);
      if (isNaN(v)) continue;
      if (v < bestV) { bestV = v; bestQ = q; }
      if (v > topV) topV = v;
    }
  };
  scan(qLo, qHi, 2000);
  if (bestQ == null) return null;
  const scale = Math.max(1e-9, Math.abs(bestV), Math.abs(topV));
  if (topV - bestV <= 1e-6 * scale) return { Q: bestQ, val: bestV, kind: 'flat' };
  const step = (qHi - qLo) / 2000;
  // Внутренний минимум — тот, что не прижат к краю отрезка. Запас в два шага
  // сетки: ровно на краю сетка не отличает «минимум здесь» от «дальше ниже».
  const interior = (bestQ > qLo + 2 * step) && (bestQ < qHi - 2 * step);
  scan(Math.max(qLo, bestQ - step), Math.min(qHi, bestQ + step), 400);
  return { Q: bestQ, val: bestV, kind: interior ? 'interior' : 'boundary' };
}
// Показывать точкой на графике можно только настоящий внутренний минимум.
function realMin(m) { return (m && m.kind === 'interior') ? m : null; }

/* Цена закрытия — НИЖНЯЯ ГРАНЬ средних переменных затрат, и это не то же
   самое, что «точка закрытия». У AVC = 0,5Q + 10 внутреннего минимума нет:
   кривая растёт всюду, точки закрытия на графике не существует. Но ниже 10
   средние переменные не опускаются, и при цене ниже 10 производить нельзя.
   Поэтому точку показываем только для внутреннего минимума (Б26), а правило
   остановки считаем по УРОВНЮ, каким бы он ни был достигнут (Б25). */
function shutdownPrice() {
  const m = STATE.minAVC;
  return (m && isFinite(m.val)) ? m.val : NaN;
}

/* Постоянные затраты из функции TC (Б24). Обычно это просто TC(0). Если в нуле
   функция не определена (например TC = Q·ln Q), считаем предел справа: берём
   всё меньшие Q и смотрим, сходится ли ряд значений. Расходится (TC = 1/Q) —
   говорим об этом честно и не рисуем AFC. */
function computeFCfromTC() {
  const direct = evalTC(0);
  if (isFinite(direct)) return { val: direct, kind: direct < -1e-9 ? 'negative' : 'exact' };
  const qs = [1e-2, 1e-3, 1e-4, 1e-6, 1e-8];
  const vs = qs.map(evalTC);
  if (vs.some(v => isNaN(v))) return { val: NaN, kind: 'none' };
  const last = vs[vs.length - 1], prev = vs[vs.length - 2];
  if (Math.abs(last) > 1e9) return { val: NaN, kind: 'none' };
  const scale = Math.max(1, Math.abs(evalTC(1)) || 1);
  if (Math.abs(last - prev) > 1e-3 * scale) return { val: NaN, kind: 'none' };
  // Хвост вроде −1,8·10⁻⁷ у Q·ln Q — это ноль, а не «отрицательные постоянные».
  const val = (Math.abs(last) < 1e-4 * scale) ? 0 : last;
  return { val, kind: val < -1e-9 ? 'negative' : 'limit' };
}

/* Отпечаток входных данных разбора издержек. Минимумы AVC и ATC, постоянные
   затраты и вид кривой MC от ЦЕНЫ не зависят вовсе — они свойство функции
   затрат. Раньше их считали заново на каждую перерисовку, то есть на каждый
   пиксель перетаскивания линии цены: три скана по 2400 вычислений формулы
   каждый плюс повторная компиляция (Б32). */
function costsSignature() {
  return [STATE.costsMode, STATE.costsTC, STATE.costsMCx, STATE.costsATCx, STATE.costsAVCx,
          costScanTop(), paramsSignature()].join(' ');
}
// Значения буквенных параметров: от них разбор тоже зависит.
function paramsSignature() {
  const p = STATE.params || {};
  return Object.keys(p).sort().map(k => k + '=' + (p[k] && p[k].value)).join(',');
}

// Пересчёт издержек: компиляция формул, постоянные затраты, ключевые точки.
function recomputeCosts() {
  const sig = costsSignature();
  if (STATE.costsSig === sig && STATE.costsReady) return;   // входные данные те же
  STATE.costsSig = sig;
  STATE.mcFlat = null;
  STATE.costsReady = false;
  STATE.minAVC = STATE.minATC = null;
  STATE.costsFCInfo = null;
  STATE.costsWarn = null;
  STATE.costsParts = null;

  if (STATE.costsMode === 'curves') {
    const parts = {};
    [['MC', STATE.costsMCx], ['ATC', STATE.costsATCx], ['AVC', STATE.costsAVCx]].forEach(([k, src]) => {
      if (!(src || '').trim()) return;
      const { compiled } = compileFormula(src);
      if (compiled) parts[k] = compiled;
    });
    STATE.costsParts = parts;
    if (!Object.keys(parts).length) return;
    STATE.costsReady = true;
    // Постоянные затраты выводимы только из пары средних: FC = (ATC − AVC)·Q.
    if (parts.ATC && parts.AVC) {
      const probe = Math.max(1, costScanTop() * 0.05);
      const fc = (evalPart('ATC', probe) - evalPart('AVC', probe)) * probe;
      STATE.costsFCInfo = isFinite(fc) ? { val: fc, kind: 'parts' } : null;
    }
  } else {
    const { compiled } = compileFormula(STATE.costsTC);
    if (!compiled) { STATE.costsCompiled = null; return; }
    STATE.costsCompiled = compiled;
    STATE.costsReady = true;
    STATE.costsFCInfo = computeFCfromTC();
  }

  const hi = costScanTop();
  if (costHas('AVC')) STATE.minAVC = minOf(costAVC, COST_SCAN_LO, hi);   // точка закрытия
  if (costHas('ATC')) STATE.minATC = minOf(costATC, COST_SCAN_LO, hi);   // точка безубыточности
  checkCostsConsistency();
}

/* Согласованность заданных по отдельности кривых (Б24, режим 'curves').
   Запрещать ничего не надо: олимпиадное условие бывает и «неаккуратным».
   Но молчать тоже нельзя — MC обязана проходить через минимумы средних. */
function checkCostsConsistency() {
  if (STATE.costsMode !== 'curves' || !STATE.costsReady) return;
  const bad = [];
  const near = (a, b) => Math.abs(a - b) <= 0.02 * Math.max(1, Math.abs(a), Math.abs(b));
  [['ATC', realMin(STATE.minATC)], ['AVC', realMin(STATE.minAVC)]].forEach(([name, m]) => {
    if (!m || !hasPart('MC')) return;
    const mc = costMC(m.Q);
    if (!isNaN(mc) && !near(mc, m.val)) bad.push(name);
  });
  if (hasPart('ATC') && hasPart('AVC')) {
    const probe = Math.max(1, costScanTop() * 0.05);
    if (evalPart('ATC', probe) < evalPart('AVC', probe) - 1e-9) bad.push('порядок');
  }
  if (!bad.length) return;
  STATE.costsWarn = (bad.indexOf('порядок') >= 0)
    ? 'Средние общие затраты оказались ниже средних переменных, а такого быть не может: разность ATC − AVC это постоянные затраты, делённые на выпуск.'
    : ('Предельные затраты не проходят через минимум ' + bad.join(' и ') +
       ': по определению MC пересекает среднюю кривую ровно в её минимуме. Кривые построены, но между собой они не согласованы.');
}

/* Точки кривой издержек. Выбросы за пределы экрана обрываем.

   Б46. Начинать ВСЕ кривые с Q = 0,5 было нельзя: у AFC в нуле асимптота, и
   для неё порог оправдан, а у MC, TC и VC в нуле конечные значения — им левый
   край графика просто отрезали. Поэтому идём от самого нуля и обрываем ровно
   там, где кривая не определена: у средних это выходит само (деление на ноль
   даёт бесконечность и точка отбрасывается), у остальных ничего не теряется. */
function costPoints(f) {
  const N = 400, out = [];
  const q0 = Math.max(0, CONFIG.Qmin);
  const step = (CONFIG.Qmax - q0) / N;
  for (let i = 0; i <= N; i++) {
    // Ровно ноль пропускаем: там у средних кривых деление на ноль.
    const q = (i === 0 && q0 === 0) ? step * 1e-3 : q0 + step * i;
    const v = f(q);
    out.push((isNaN(v) || v < 0 || v > CONFIG.Pmax * 4) ? null : [q, v]);
  }
  return out;
}

/* Выражения кривых издержек — то самое «описание сцены», из которого строится
   выгрузка (Б35). Всё выводится из одной введённой функции по определению:
   FC = TC(0), VC = TC − FC, ATC = TC/Q, AVC = VC/Q, AFC = FC/Q, MC = dTC/dQ.
   Пустое значение означает «формулы нет» — тогда кривая уходит точками, и в
   файл идёт пояснение почему. */
function costExprs() {
  const out = { TC: '', VC: '', ATC: '', AVC: '', AFC: '', MC: '', FC: '' };
  if (!STATE.costsReady) return out;
  if (STATE.costsMode === 'curves') {
    out.MC = (STATE.costsMCx || '').trim();
    out.ATC = (STATE.costsATCx || '').trim();
    out.AVC = (STATE.costsAVCx || '').trim();
    if (out.ATC) out.TC = '(' + out.ATC + ')*Q';
    if (out.AVC) out.VC = '(' + out.AVC + ')*Q';
    if (out.ATC && out.AVC) out.AFC = '(' + out.ATC + ') - (' + out.AVC + ')';
    const fc = costsFC();
    if (isFinite(fc)) out.FC = String(fc);
    return out;
  }
  const tc = (STATE.costsTC || '').trim();
  if (!tc) return out;
  const fc = costsFC();
  out.TC = tc;
  out.ATC = '(' + tc + ')/Q';
  out.MC = derivativeExpr(tc, 'Q') || '';
  if (isFinite(fc)) {
    out.FC = String(fc);
    out.VC = '(' + tc + ') - (' + fc + ')';
    out.AVC = '((' + tc + ') - (' + fc + '))/Q';
    out.AFC = '(' + fc + ')/Q';
  }
  return out;
}

// Отрисовка кривых издержек + точки закрытия (min AVC) и безубыточности (min ATC).
function drawCostCurves() {
  if (!STATE.costsReady) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  /* Б4, Б35. Кривая, у которой есть выражение, объявляет его сцене — и уходит
     в файл ФОРМУЛОЙ, а не таблицей из шестидесяти точек. Выражения здесь есть
     почти у всех: TC вводит человек, остальное из неё выводится по правилу
     (ATC = TC/Q, VC = TC − FC и так далее). Предельные затраты берём символьной
     производной; не вышло — кривая честно уходит точками. */
  const curve = (f, color, on, dash, expr) => {
    if (!on) return;
    const p = g.append('path').datum(costPoints(f)).attr('fill', 'none')
      .attr('stroke', color).attr('stroke-width', 2.2).attr('d', line);
    if (dash) p.attr('stroke-dasharray', dash);
    if (expr) markExpr(p, expr, 'Q');
  };
  const E = costExprs();
  // Кривой, которой у сцены нет (нет постоянных затрат либо поле пустое),
  // не существует: галочка её не воскрешает.
  // Полные затраты (Б21): TC, VC и FC — тройка, живут вместе.
  curve(costTC,  COL.costTC, STATE.showTC && costHas('TC'), '5 4', E.TC);
  curve(() => costsFC(), COL.costFC, STATE.showFC && costHas('FC'), '2 4', E.FC);
  curve(costVC,  COL.costVC, STATE.showVC && costHas('VC'), '5 4', E.VC);   // VC — полные переменные (по желанию)
  curve(costAFC, COL.costAFC, STATE.showAFC && costHas('AFC'), null, E.AFC);
  curve(costAVC, COL.costAVC, STATE.showAVC && costHas('AVC'), null, E.AVC);
  curve(costATC, COL.costATC, STATE.showATC && costHas('ATC'), null, E.ATC);
  curve(costMC,  COL.costMC, STATE.showMC && costHas('MC'), null, E.MC);

  // Подписи кривых (Фаза 3): у правого края, а если кривая там вне окна —
  // у ближайшего места, где она видна. Раньше подпись просто пропадала.
  if (STATE.showMC  && costHas('MC'))  labelCurve(g, costMC,  'MC',  COL.costMC);
  if (STATE.showATC && costHas('ATC')) labelCurve(g, costATC, 'ATC', COL.costATC);
  if (STATE.showAVC && costHas('AVC')) labelCurve(g, costAVC, 'AVC', COL.costAVC, { below: true });
  if (STATE.showAFC && costHas('AFC')) labelCurve(g, costAFC, 'AFC', COL.costAFC);
  if (STATE.showVC  && costHas('VC'))  labelCurve(g, costVC,  'VC',  COL.costVC, { below: true });
  if (STATE.showTC  && costHas('TC'))  labelCurve(g, costTC,  'TC',  COL.costTC);
  if (STATE.showFC  && costHas('FC'))  labelCurve(g, () => costsFC(), 'FC', COL.costFC, { below: true });

  // Ключевые точки: безубыточность (min ATC) и закрытие (min AVC) — MC проходит
  // через них. Показываем только НАСТОЯЩИЙ внутренний минимум: край отрезка
  // сканирования экономической точкой не является (Б26).
  const mark = (pt, color, label) => {
    if (!pt || pt.val > CONFIG.Pmax || pt.Q > CONFIG.Qmax) return;
    const [px, py] = toPx(pt.Q, pt.val);
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4)
      .attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    g.append('text').attr('x', px).attr('y', py - 9)
      .attr('text-anchor', 'middle').attr('font-size', FS.small).attr('font-weight', 600).attr('fill', color)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
  };
  if (STATE.showATC && costHas('ATC')) mark(realMin(STATE.minATC), COL.costATC, 'безубыточность');
  if (STATE.showAVC && costHas('AVC')) mark(realMin(STATE.minAVC), COL.costAVC, 'закрытие');
}

/* Объяснение на месте несуществующего минимума (Б26). Числа с края отрезка
   сканирования сюда не попадают: если внутреннего минимума нет, говорим об
   этом словами и объясняем, почему его нет. */
function noMinNote(m, what, avgName) {
  if (!m) return '';
  if (m.kind === 'flat')
    return `<div class="hint">Кривая ${avgName} постоянна, поэтому минимума у неё нет, и ${what} в обычном смысле не существует.</div>`;
  if (m.kind === 'boundary')
    return `<div class="hint">Внутреннего минимума ${avgName} нет: кривая монотонна на всём диапазоне, поэтому ${what} в обычном смысле не существует.</div>`;
  return '';
}

// Табло издержек: ключевые точки закрытия и безубыточности.
function updateCostsPanel() {
  const box = document.getElementById('info-costs');
  if (!box) return;
  if (!STATE.costsReady) {
    box.innerHTML = '<div class="warn">' + (STATE.costsMode === 'curves'
      ? 'Задайте хотя бы одну кривую: MC, ATC или AVC.'
      : 'Не понял формулу TC.') + '</div>';
    return;
  }
  let html = '';
  // Постоянные затраты: отдельного поля нет, число выведено из самой функции.
  const fi = STATE.costsFCInfo;
  if (STATE.costsMode === 'tc') {
    if (fi && (fi.kind === 'exact' || fi.kind === 'limit'))
      html += `<div class="stat"><span>Постоянные затраты $FC = TC(0)$</span><b>${fmt(fi.val)}</b></div>`;
    else if (fi && fi.kind === 'negative')
      html += '<div class="warn">Постоянные затраты вышли отрицательными: $TC(0) < 0$. Так быть не может, проверьте формулу.</div>';
    else
      html += '<div class="hint">Постоянные затраты по этой функции не определены: $TC(0)$ не существует. Поэтому AFC, AVC и VC не строятся, а точки закрытия нет.</div>';
  } else if (fi) {
    html += `<div class="stat"><span>Постоянные затраты $FC = (ATC - AVC) \\cdot Q$</span><b>${fmt(fi.val)}</b></div>`;
  }

  const mATC = realMin(STATE.minATC), mAVC = realMin(STATE.minAVC);
  if (mATC) html += `<div class="stat"><span>Безубыточность (min ATC)</span><b>Q = ${fmt(mATC.Q)}, ATC = ${fmt(mATC.val)}</b></div>`;
  else html += noMinNote(STATE.minATC, 'точки безубыточности', 'ATC');
  if (mAVC) html += `<div class="stat"><span>Закрытие (min AVC)</span><b>Q = ${fmt(mAVC.Q)}, AVC = ${fmt(mAVC.val)}</b></div>`;
  else html += noMinNote(STATE.minAVC, 'точки закрытия', 'AVC');

  if (STATE.costsWarn) html += `<div class="warn">${STATE.costsWarn}</div>`;
  // Про пересечение говорим ровно о тех точках, которые на графике есть.
  if (mATC && mAVC)
    html += '<div class="hint">В точках закрытия и безубыточности MC пересекает соответственно AVC и ATC (в их минимумах).</div>';
  else if (mATC)
    html += '<div class="hint">В точке безубыточности MC пересекает ATC — ровно в её минимуме.</div>';
  else if (mAVC)
    html += '<div class="hint">В точке закрытия MC пересекает AVC — ровно в её минимуме.</div>';
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
  /* Правило 46: подпись оси — символ величины. Здесь на вертикали стоят и
     цена, и издержки в тех же деньгах, и это одна величина — `P`. Фраза
     «Издержки, цена» тем же кеглем, что и деления, была подписью-объяснением,
     а не обозначением; что именно нарисовано, говорят имена самих кривых
     (MC, ATC, AVC, AFC). */
  drawAxes('Q', 'P');
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
  if (!STATE.costsReady || !STATE.lrOn || !costHas('MC')) return;
  const P = STATE.lrPrice;
  if (!(P > 0)) return;
  const fc = costsFC();
  // Долгосрочная точка входа/выхода: P = min ATC (нулевая экономическая прибыль).
  const breakeven = realMin(STATE.minATC) ? STATE.minATC.val : null;
  const sp = shutdownPrice();
  /* Правило остановки решается ПЕРВЫМ, до поиска корня P = MC. Иначе случай
     «цена ниже предельных затрат на всём диапазоне» уходил в ветку «корня нет»
     и убыток, равный постоянным затратам, не назывался вовсе, хотя фирма его
     несёт: закрыться не значит ничего не потерять. */
  const shutdown = isFinite(sp) && P < sp - 1e-9;
  const base = {
    P, breakeven, fc, shutdown,
    shutPrice: sp, shutIsPoint: !!realMin(STATE.minAVC),
    Q: shutdown ? 0 : null,
    profit: shutdown ? (isNaN(fc) ? null : -fc) : null,
  };

  /* Оптимума может не быть вовсе, и молчать об этом нельзя (Б27): раньше при
     постоянных предельных затратах findRootLast возвращал null, весь блок цены,
     выпуска и прибыли исчезал с экрана без единого слова, и это выглядело как
     поломка калькулятора. Разбираем случай явно. */
  const hi = costScanTop();
  // Вид кривой MC от цены не зависит, поэтому считается один раз на функцию.
  if (STATE.mcFlat === null || STATE.mcFlat === undefined) STATE.mcFlat = minOf(costMC, COST_SCAN_LO, hi) || false;
  const mcMin = STATE.mcFlat || null;
  if (mcMin && mcMin.kind === 'flat') {
    const mc = mcMin.val;
    const note = (P > mc + 1e-9)
      ? 'Предельные затраты постоянны и цена выше них, поэтому каждая следующая единица приносит одну и ту же прибавку к прибыли: конечного оптимума нет, выпуск выгодно наращивать без предела.'
      : (P < mc - 1e-9
        ? 'Предельные затраты постоянны и цена ниже них, поэтому любая выпущенная единица приносит убыток: выгодно не производить вовсе.'
        : 'Цена в точности равна постоянным предельным затратам, поэтому любой выпуск даёт одну и ту же прибыль (нулевую сверх постоянных затрат): единственного оптимума нет.');
    STATE.lr = Object.assign({}, base, { Qmc: null, atc: NaN, avc: NaN, note });
    return;
  }

  const g = (q) => { const m = costMC(q); return isNaN(m) ? NaN : P - m; };   // P − MC: слева +, справа −
  const Qmc = findRootLast(g, COST_SCAN_LO, hi);
  if (Qmc == null || !(Qmc > 0)) {
    // Корня нет: либо цена ниже всей кривой MC, либо выше её на всём диапазоне.
    const mcLo = costMC(COST_SCAN_LO), mcHi = costMC(hi);
    const note = (!isNaN(mcHi) && P > mcHi)
      ? `Цена выше предельных затрат на всём просмотренном диапазоне (до Q = ${fmt(hi)}), поэтому выпуск выгодно наращивать дальше: оптимум лежит за этими пределами.`
      : ((!isNaN(mcLo) && P < mcLo)
        ? 'Цена ниже предельных затрат уже на первой единице, поэтому производить невыгодно ни при каком выпуске.'
        : 'Уравнение P = MC решений не имеет: проверьте функцию затрат.');
    // При закрытии выпуск и убыток уже стоят в base — их и показываем, а
    // объяснение просто добавляем: закрыться не значит ничего не потерять.
    STATE.lr = Object.assign({}, base, { Qmc: null, atc: NaN, avc: NaN, note: shutdown ? null : note, extra: note });
    return;
  }

  const atc = costATC(Qmc), avc = costAVC(Qmc);
  /* Краткосрочное правило остановки (Б25). Раньше этот флаг только считался:
     панель показывала положительный выпуск, рисовала на нём прямоугольник
     убытка и тут же писала «выгоднее закрыться». Теперь он МЕНЯЕТ ответ. */
  const Q = shutdown ? 0 : Qmc;
  const profit = shutdown ? base.profit : (isNaN(atc) ? null : (P - atc) * Qmc);
  STATE.lr = Object.assign({}, base, { Q, Qmc, atc, avc, profit, note: null });
}

/* Прямоугольник прибыли (зелёный) или убытка (красный) между P и ATC на [0, Q].
   При закрытии (Б25) прямоугольника нет: выпуск нулевой, значит нулевая и
   ширина. Убыток при этом равен постоянным затратам, и он показывается
   отрезком на оси — подписанным, чтобы его не прочли как цену. */
function drawLongRunArea() {
  /* Своя группа с постоянным местом в порядке отрисовки. Во время
     перетаскивания цены её содержимое меняется на месте, а холст целиком не
     пересобирается (Б32) — поэтому заливка так и остаётся ПОД кривыми. */
  const g = svg.append('g').attr('class', 'lr-area').attr('clip-path', 'url(#plot-clip)');
  fillLongRunArea(g);
}

function fillLongRunArea(g) {
  const lr = STATE.lr; if (!lr || !STATE.lrArea || lr.profit == null) return;
  if (lr.shutdown) {
    const fc = lr.fc;
    if (isNaN(fc) || !(fc > 0) || fc > CONFIG.Pmax) return;
    const ox = sx(0);
    g.append('line').attr('x1', ox).attr('y1', sy(0)).attr('x2', ox).attr('y2', sy(fc))
      .attr('stroke', COL.bad).attr('stroke-width', 7).attr('opacity', 0.55).attr('stroke-linecap', 'butt');
    renderLabelText(
      g.append('text').attr('x', ox + 10).attr('y', sy(fc / 2)).attr('dominant-baseline', 'middle')
        .attr('font-size', FS.small).attr('font-weight', 600).attr('fill', COL.bad)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5),
      'убыток = FC = ' + fmt(fc));
    return;
  }
  if (Math.abs(lr.profit) < 1e-9 || !(lr.Q > 0)) return;
  const yHi = Math.max(lr.P, lr.atc), yLo = Math.min(lr.P, lr.atc);
  g.append('rect').attr('x', sx(0)).attr('y', sy(yHi))
    .attr('width', sx(lr.Q) - sx(0)).attr('height', Math.abs(sy(yLo) - sy(yHi)))
    .attr('fill', lr.profit > 0 ? 'url(#hatch-profit)' : 'url(#hatch-loss)')
    .attr('data-legend', lr.profit > 0 ? 'Прибыль фирмы' : 'Убыток фирмы');
}

// Линия цены, точка P = MC и подписи.
function drawLongRunMarks() {
  const g = svg.append('g').attr('class', 'lr-marks');
  fillLongRunMarks(g);
}

function fillLongRunMarks(g) {
  const lr = STATE.lr; if (!lr) return;
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax);
  const yP = sy(lr.P);
  g.append('line').attr('x1', ox).attr('y1', yP).attr('x2', xMax).attr('y2', yP)
    .attr('stroke', COL.price).attr('stroke-width', 2.5).style('pointer-events', 'none');
  haloText(g, ox - 8, yP, 'P=' + fmt(lr.P), 'end', 'middle');
  // Корня P = MC может не быть вовсе — тогда на графике только линия цены.
  if (lr.Qmc == null || lr.Qmc > CONFIG.Qmax) { drawLongRunHandle(g, lr, ox, xMax, yP); return; }
  const px = sx(lr.Qmc);
  /* При закрытии точка P = MC остаётся, но бледной и с оговоркой: это корень
     уравнения, а не выбор фирмы. Иначе экран утверждал бы одновременно и
     «выпускай столько», и «закройся». */
  const dim = lr.shutdown ? 0.35 : 1;
  g.append('line').attr('x1', px).attr('y1', yP).attr('x2', px).attr('y2', oy)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3').attr('opacity', dim);
  g.append('circle').attr('cx', px).attr('cy', yP).attr('r', 4.5)
    .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5).attr('opacity', dim);
  if (lr.shutdown) {
    renderLabelText(
      g.append('text').attr('x', px + 8).attr('y', yP - 8).attr('font-size', FS.small).attr('fill', COL.inkSoft)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5),
      'математический корень, но производить невыгодно');
  }
  haloText(g, px, oy + 8, 'Q=' + fmt(lr.Qmc), 'middle', 'hanging');
  drawLongRunHandle(g, lr, ox, xMax, yP);
}

/* Зона захвата линии цены (тянется мышью) и её кружок-рукоятка. Вынесено
   отдельной функцией: линия цены нужна и там, где корня P = MC нет вовсе,
   иначе за цену стало бы не ухватиться ровно в тех случаях, где её и хочется
   подвинуть. */
function drawLongRunHandle(g, lr, ox, xMax, yP) {
  const hit = g.append('rect').attr('x', ox).attr('y', yP - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab').attr('data-skip-export', '1');
  hit.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; beginLrDrag(); })
    .on('drag', (e) => dragLrPrice(sy.invert(e.y)))
    .on('end', () => { document.body.style.cursor = ''; endLrDrag(); }));
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.9).attr('cy', yP).attr('r', 7)
    .attr('fill', COL.price).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

function setLrPrice(p) {
  p = Math.max(0, Math.min(p, CONFIG.Pmax));
  STATE.lrPrice = Math.round(p * 100) / 100;
  syncLrPriceFields();
  redrawAll();
}

// Ползунок, подпись и числовое поле цены — три разных показа одного числа.
function syncLrPriceFields() {
  const s = document.getElementById('lr-price-slider'); if (s) s.value = STATE.lrPrice;
  const l = document.getElementById('lr-price-val');    if (l) l.textContent = fmt(STATE.lrPrice);
  const i = document.getElementById('lr-price-input');  if (i) i.value = STATE.lrPrice;
}

/* Перетаскивание линии цены (Б32, Б33).

   Раньше каждый пиксель движения мыши звал redrawAll: тот пересчитывал
   минимумы AVC и ATC (три скана по 2400 вычислений формулы), заново
   компилировал TC, сносил весь холст и собирал его с нуля — вместе с тем
   самым прямоугольником-захватом, за который человек держится мышью.
   Отсюда и ощущение, что график живёт своей жизнью.

   От цены зависит РОВНО ЧЕТЫРЕ вещи: положение линии, точка P = MC,
   прямоугольник прибыли и числа в табло. Их и трогаем; кривые, оси, сетка и
   ключевые точки на месте. Округление до сотых и синхронизация трёх
   показов числа — на отпускании кнопки, а не на каждом движении (Б33). */
function beginLrDrag() { STATE.lrDragging = true; }

function dragLrPrice(p) {
  if (!STATE.lrDragging) { setLrPrice(p); return; }
  STATE.lrPrice = Math.max(0, Math.min(p, CONFIG.Pmax));
  recomputeLongRun();
  const area = svg.select('g.lr-area'), marks = svg.select('g.lr-marks');
  // Слоёв нет (сцена ещё ни разу не рисовалась) — идём обычным путём.
  if (area.empty() && marks.empty()) { redrawAll(); return; }
  area.selectAll('*').remove(); fillLongRunArea(area);
  marks.selectAll('*').remove(); if (STATE.lrOn) fillLongRunMarks(marks);
  updateCostsPanel();
  // Панель обязана выглядеть так же, как после обычной перерисовки: иначе в
  // пути числа показывались сырым текстом и скачком менялись на отпускании.
  refreshAnalyticsPanel();
}

function endLrDrag() {
  STATE.lrDragging = false;
  STATE.lrPrice = Math.round(STATE.lrPrice * 100) / 100;
  syncLrPriceFields();
  redrawAll();
}

function updateLongRunPanel(html) {
  const lr = STATE.lr;
  if (!lr) return html;
  html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
  html += `<div class="stat"><span>Цена P</span><b>${fmt(lr.P)}</b></div>`;
  /* Правило остановки применено, а не только посчитано (Б25): при цене ниже
     минимума AVC выпуск равен нулю, а убыток равен постоянным затратам.
     Разбирается ПЕРВЫМ: у закрытия числа есть, и они важнее объяснения. */
  if (lr.shutdown) {
    html += '<div class="stat"><span>Выпуск Q</span><b>0</b></div>';
    html += `<div class="stat"><span>Убыток = FC</span><b>${lr.profit == null ? '—' : fmt(-lr.profit)}</b></div>`;
    if (lr.Qmc != null) html += `<div class="stat"><span>Корень P = MC (не выбор фирмы)</span><b>${fmt(lr.Qmc)}</b></div>`;
    if (lr.breakeven != null) html += `<div class="stat"><span>Вход/выход: P = min ATC</span><b>${fmt(lr.breakeven)}</b></div>`;
    if (lr.note || lr.extra) html += `<div class="hint" style="margin-top:4px;">${lr.note || lr.extra}</div>`;
    html += '<div class="hint" style="margin-top:4px;">' +
      (lr.shutIsPoint
        ? 'Цена ниже минимума AVC: '
        : `Средние переменные затраты нигде не опускаются ниже ${fmt(lr.shutPrice)}, а цена ниже этого уровня: `) +
      'выручка не покрывает даже переменные затраты, поэтому каждая выпущенная единица увеличивает убыток. ' +
      'Выгоднее <b>закрыться</b>. Закрывшись, фирма всё равно платит постоянные затраты, значит ровно их и теряет: ' +
      'это её убыток при нулевом выпуске. Корень уравнения P = MC на графике остался, но он показывает не выбор ' +
      'фирмы, а точку, где выпуск был бы оптимален, если бы производить вообще стоило.</div>';
    return html;
  }
  // Оптимума может не быть вовсе — тогда вместо чисел стоит объяснение (Б27).
  if (lr.note) {
    html += `<div class="hint" style="margin-top:4px;">${lr.note}</div>`;
    if (lr.breakeven != null) html += `<div class="stat"><span>Вход/выход: P = min ATC</span><b>${fmt(lr.breakeven)}</b></div>`;
    return html;
  }
  html += `<div class="stat"><span>Выпуск Q (P = MC)</span><b>${fmt(lr.Q)}</b></div>`;
  html += `<div class="stat"><span>$ATC(Q)$</span><b>${fmt(lr.atc)}</b></div>`;
  html += `<div class="stat"><span>${lr.profit >= 0 ? 'Прибыль' : 'Убыток'} (P − ATC)·Q</span><b>${fmt(lr.profit)}</b></div>`;
  if (lr.breakeven != null) html += `<div class="stat"><span>Вход/выход: P = min ATC</span><b>${fmt(lr.breakeven)}</b></div>`;
  html += `<div class="hint" style="margin-top:4px;">${lr.profit > 1e-9
    ? 'Прибыль положительна, поэтому в долгом периоде в отрасль входят новые фирмы и цена падает к min ATC.'
    : (lr.profit < -1e-9
      ? 'Убыток при P выше min AVC: в коротком периоде производить стоит, в долгом фирмы уходят и цена растёт к min ATC.'
      : 'Нулевая экономическая прибыль и есть долгосрочное равновесие.')}</div>`;
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

/* Максимум произвольной функции на отрезке — зеркало minOf, включая ЧЕСТНЫЙ
   ответ о том, что найдено (Б26 в производственной функции). У TP = 10·L
   предельный продукт постоянен: перегиба нет вовсе, а панель писала «перегиб
   TP при L = 6,57». У TP = L² предельный продукт растёт всюду: максимум MP
   оказывался на правом краю сетки. И то, и другое — край цикла, выданный за
   экономическую величину. */
function maxOf(f, lo, hi) {
  let bestQ = null, bestV = -Infinity, lowV = Infinity;
  const scan = (a, b, n) => {
    for (let i = 0; i <= n; i++) {
      const q = a + (b - a) * i / n, v = f(q);
      if (isNaN(v)) continue;
      if (v > bestV) { bestV = v; bestQ = q; }
      if (v < lowV) lowV = v;
    }
  };
  scan(lo, hi, 2000);
  if (bestQ == null) return null;
  const scale = Math.max(1e-9, Math.abs(bestV), Math.abs(lowV));
  if (bestV - lowV <= 1e-6 * scale) return { L: bestQ, val: bestV, kind: 'flat' };
  const st = (hi - lo) / 2000;
  const interior = (bestQ > lo + 2 * st) && (bestQ < hi - 2 * st);
  scan(Math.max(lo, bestQ - st), Math.min(hi, bestQ + st), 400);
  return { L: bestQ, val: bestV, kind: interior ? 'interior' : 'boundary' };
}
// Показывать числом можно только настоящий внутренний максимум.
function realMax(m) { return (m && m.kind === 'interior') ? m : null; }

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
  const Lmax = p.Lmax || CONFIG.Qmax;
  const tpMax = padMax(p.maxTP ? p.maxTP.val : 1);
  const mpMax = padMax(Math.max(p.maxMP ? p.maxMP.val : 1, p.maxAP ? p.maxAP.val : 1));
  /* Поле слева считаем ПО СВОИМ делениям: у верхней панели своя вертикаль
     (до 5 000), и общий fitMargins её не видит. `ticks` зависит только от
     области значений, поэтому шкалу для замера можно построить до того, как
     станет известно само поле. */
  fitLeftForLabels([].concat(
    d3.scaleLinear().domain([0, tpMax]).ticks(5),
    d3.scaleLinear().domain([0, mpMax]).ticks(5)));
  const left = m.left, right = W - m.right;
  const top = m.top, bottom = H - m.bottom;
  const gap = 34, hTop = (bottom - top - gap) * 0.55, hBot = (bottom - top - gap) - hTop;
  const yTop0 = top + hTop, yBot0 = bottom;
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
  // Б4: TP вводит человек, MP берём символьной производной, AP = TP/L.
  const pe = (STATE.prodExpr || '').trim();
  const EXPR = { TP: pe, MP: derivativeExpr(pe, 'L') || '', AP: pe ? '(' + pe + ')/L' : '' };
  const curve = (g, f, scale, color, on, width, key) => {
    if (!on) return;
    const line = d3.line().defined(d => d !== null).x(d => lx(d[0])).y(d => scale(d[1]));
    const pts = [];
    for (let i = 0; i <= 300; i++) {
      const l = Lmax * i / 300, v = f(l);
      pts.push((isNaN(v) || v < 0 || v > scale.domain()[1] * 1.5) ? null : [l, v]);
    }
    const path = g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color).attr('stroke-width', width || 2.4).attr('d', line);
    if (key && EXPR[key]) markExpr(path, EXPR[key], 'L', [0, Lmax]);
  };
  // Сцена рисует две панели своими руками и общий drawAxes не зовёт, поэтому
  // названия осей для выгрузки проставляем здесь (Б37).
  STATE.axisXDefault = 'L'; STATE.axisYDefault = 'TP, MP, AP';
  const gTop = panel(t1, yTop0, 'TP, общий продукт');
  curve(gTop, prodEval, t1, COL.prodTP, STATE.showTP, 2.6, 'TP');
  const gBot = panel(t2, yBot0, 'MP и AP');
  curve(gBot, prodMP, t2, COL.prodMP, STATE.showMP, null, 'MP');
  curve(gBot, prodAP, t2, COL.prodAP, STATE.showAP, null, 'AP');
  // Ключевые вертикали: перегиб TP (максимум MP) и максимум AP (там AP = MP).
  const vline = (L, color, label, row) => {
    if (L == null) return;
    const x = lx(L);
    svg.append('line').attr('x1', x).attr('y1', top).attr('x2', x).attr('y2', bottom)
      .attr('stroke', color).attr('stroke-width', 1.2).attr('stroke-dasharray', '5 4').attr('opacity', 0.8);
    const g = svg.append('g');
    // Каждая подпись на своей строке: этажи разводят их даже при близких L.
    renderLabelText(
      g.append('text').attr('x', x + 5).attr('y', top + 10 + (row || 0) * (FS.small + 4))
        .attr('font-size', FS.small).attr('font-weight', 600).attr('fill', color)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5),
      label);
  };
  /* Вертикали ставим только там, где максимум НАСТОЯЩИЙ: край сетки — это не
     точка перегиба и не максимум среднего продукта (Б26). */
  const vMP = realMax(p.maxMP), vAP = realMax(p.maxAP), vTP = realMax(p.maxTP);
  /* Б45. Подписи набираются формулами, а не строками с точкой посередине
     («перегиб TP · max MP · L=10» мешало латиницу с кириллицей и читалось
     как машинный вывод). И разводятся по вертикали: при близких L три
     подписи в один ряд налезали друг на друга. */
  if (vMP) vline(vMP.L, COL.prodMP, 'перегиб TP: $\\max MP$ при $L = ' + fmt(vMP.L) + '$', 0);
  if (vAP) vline(vAP.L, COL.prodAP, '$\\max AP = MP$ при $L = ' + fmt(vAP.L) + '$', 1);
  if (vTP) vline(vTP.L, COL.ghost, '$\\max TP$: $MP = 0$', 2);
  // Точки на нижней панели.
  if (vAP && STATE.showAP) {
    svg.append('circle').attr('cx', lx(vAP.L)).attr('cy', t2(vAP.val)).attr('r', 4.5)
      .attr('fill', COL.prodAP).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  }
  if (vMP && STATE.showMP) {
    svg.append('circle').attr('cx', lx(vMP.L)).attr('cy', t2(vMP.val)).attr('r', 4.5)
      .attr('fill', COL.prodMP).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  }
  updateProdPanel();
}

// Объяснение на месте несуществующего максимума (Б26 в производстве).
function noMaxNote(m, what, name, why) {
  if (!m) return '';
  if (m.kind === 'flat')
    return `<div class="hint">Кривая ${name} постоянна на всём диапазоне, поэтому ${what} не существует: ${why}</div>`;
  if (m.kind === 'boundary')
    return `<div class="hint">У кривой ${name} нет внутреннего максимума: она монотонна на всём диапазоне, поэтому ${what} не существует: ${why}</div>`;
  return '';
}

function updateProdPanel() {
  const box = document.getElementById('info-prod'); if (!box) return;
  const p = STATE.prod;
  if (!p) { box.innerHTML = '<div class="warn">Не понял формулу Q = f(L).</div>'; return; }
  let html = '';
  const mMP = realMax(p.maxMP), mAP = realMax(p.maxAP), mTP = realMax(p.maxTP);
  if (mMP) html += `<div class="stat"><span>Перегиб TP (max MP)</span><b>L = ${fmt(mMP.L)}, MP = ${fmt(mMP.val)}</b></div>`;
  else html += noMaxNote(p.maxMP, 'точки перегиба TP', 'MP',
    'убывающая предельная отдача на этом диапазоне не начинается.');
  if (mAP) html += `<div class="stat"><span>Максимум AP</span><b>L = ${fmt(mAP.L)}, AP = ${fmt(mAP.val)}</b></div>`;
  else html += noMaxNote(p.maxAP, 'максимума среднего продукта', 'AP',
    'средний продукт нигде не разворачивается.');
  if (mAP && !isNaN(p.mpAtMaxAP)) html += `<div class="stat"><span>$MP$ в этой точке</span><b>${fmt(p.mpAtMaxAP)}</b></div>`;
  if (mTP) html += `<div class="stat"><span>Максимум TP</span><b>L = ${fmt(mTP.L)}, Q = ${fmt(mTP.val)}</b></div>`;
  else html += noMaxNote(p.maxTP, 'максимума выпуска', 'TP',
    'предельный продукт нигде не обращается в ноль, и выпуск растёт с каждым работником.');
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
  try { const v = compiled.evaluate(paramScope(axisScope(q))); return (typeof v === 'number' && isFinite(v)) ? v : NaN; }
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
  addDefs(); drawGrid(); drawAxes('Q', 'P');    // правило 46: символ, а не «Издержки»
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
    // Б4: у заводов формулы затрат ввёл человек, предельные берём символьно.
    markExpr(g.append('path').datum(mkMC(p.c1)).attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line),
             derivativeExpr(STATE.pl1, 'Q'), 'Q', [0, p.qMax]);
    markExpr(g.append('path').datum(mkMC(p.c2)).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line),
             derivativeExpr(STATE.pl2, 'Q'), 'Q', [0, p.qMax]);
    /* Совокупная кривая строится ЧИСЛЕННО (горизонтальное сложение по уровню
       предельных затрат), замкнутой формулы у неё в общем случае нет. Говорим
       об этом в самом файле, а не выдаём таблицу точек за формулу (Б5). */
    g.append('path').datum(p.table.map(r => [r.Q, r.m])).attr('fill', 'none').attr('stroke', COL.MC).attr('stroke-width', 2.8).attr('d', line)
      .attr('data-numeric', 'совокупная MC получена горизонтальным сложением, замкнутой формулы у неё нет');
    label(p.qMax * 0.5, plantMC(p.c1, p.qMax * 0.5), 'MC₁', COL.tax);
    label(p.qMax * 0.34, plantMC(p.c2, p.qMax * 0.34), 'MC₂', COL.reg);
    const mid = plantsAt(p.Qtot * 0.6); if (mid) label(mid.Q, mid.m, 'MC совокупная', COL.MC);
  } else {
    // TC каждого завода по своему объёму + совокупная TC(Q) (минимум суммы).
    const mkTC = (c) => { const o = []; for (let i = 0; i <= 300; i++) { const q = p.qMax * i / 300; const v = plantTC(c, q); o.push(isNaN(v) ? null : [q, v]); } return o; };
    markExpr(g.append('path').datum(mkTC(p.c1)).attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line),
             STATE.pl1, 'Q', [0, p.qMax]);
    markExpr(g.append('path').datum(mkTC(p.c2)).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line),
             STATE.pl2, 'Q', [0, p.qMax]);
    g.append('path').datum(p.table.map(r => [r.Q, r.tcDirect])).attr('fill', 'none').attr('stroke', COL.D).attr('stroke-width', 2.8).attr('d', line)
      .attr('data-numeric', 'совокупная TC — минимум суммы затрат по всем способам разделить выпуск, замкнутой формулы у неё нет');
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

/* Переключатель способа ввода издержек (Б24). Спрашиваем сразу, при входе в
   сцену: «задам TC, остальное посчитайте» или «задам кривые по отдельности». */
function setCostsInputMode(mode) {
  STATE.costsMode = (mode === 'curves') ? 'curves' : 'tc';
  syncCostsInputMode();
  redrawAll();
}

// Привести переключатель и поля в согласие с STATE (нужно и при возврате в
// модель из памяти сцен, где состояние восстанавливается мимо переключателя).
function syncCostsInputMode() {
  const curves = STATE.costsMode === 'curves';
  const a = document.getElementById('cm-tc'), b = document.getElementById('cm-curves');
  if (a) a.classList.toggle('active', !curves);
  if (b) b.classList.toggle('active', curves);
  const pt = document.getElementById('costs-input-tc'), pc = document.getElementById('costs-input-curves');
  if (pt) pt.style.display = curves ? 'none' : '';
  if (pc) pc.style.display = curves ? '' : 'none';
  const put = (id, v) => { const e = document.getElementById(id); if (e && v != null) e.value = v; };
  put('inp-tc', STATE.costsTC);
  put('inp-cmc', STATE.costsMCx); put('inp-catc', STATE.costsATCx); put('inp-cavc', STATE.costsAVCx);
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

