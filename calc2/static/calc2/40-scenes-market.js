// Рынок: равновесие, области, налог, регулирование, внешние эффекты.
/* ---------------------------------------------------------------------
   БЛОК 5. РАВНОВЕСИЕ — численный поиск и отрисовка точки D = S.
   --------------------------------------------------------------------- */

// Найти кривую с заданной ролью ('demand' / 'supply'), либо null.
function curveByRole(role) { return STATE.curves.find(c => c.role === role) || null; }

// Пересчёт сценария БЕЗ рисования: складываем результаты в STATE,
// чтобы функции отрисовки и табло читали готовые числа.
function recompute() {
  STATE.D = curveByRole('demand');
  STATE.S = curveByRole('supply');
  STATE.eq = (STATE.D && STATE.S) ? findEquilibrium(STATE.D, STATE.S) : null;

  // Площади излишков (шаг 6) — численным интегрированием от 0 до Q*.
  STATE.cs = STATE.ps = STATE.sw = null;
  if (STATE.eq) {
    const { Q, P } = STATE.eq;
    STATE.cs = integrate(q => evalCurve(STATE.D, q) - P, 0, Q);   // ∫ (D - P*) dQ
    STATE.ps = integrate(q => P - evalCurve(STATE.S, q), 0, Q);   // ∫ (P* - S) dQ
    STATE.sw = STATE.cs + STATE.ps;
  }

  // Вмешательство государства (шаг 7 — налог, шаг 8 — субсидия).
  // Налог сдвигает S вверх на t, субсидия — вниз на s. Дальше математика общая.
  STATE.taxActive = false;
  STATE.taxEq = null;
  // В режиме монополии конкурентные сценарии вмешательства отключены.
  // Интервенции активны только в обычном сценарии (не при эластичности/сдвигах/внешнем эффекте).
  const compMarket = (STATE.market !== 'monopoly');
  const scenarioNone = (STATE.scenario === 'none');
  const isTaxType = compMarket && scenarioNone && (STATE.intervType === 'tax' || STATE.intervType === 'subsidy');
  if (isTaxType && STATE.tax > 0 && STATE.D && STATE.S && STATE.eq) {
    const isSub = (STATE.intervType === 'subsidy');
    const adv = (STATE.taxKind === 'advalorem');
    const tau = adv ? STATE.tax / 100 : 0;        // адвалорная ставка в долях (STATE.tax — проценты)
    const shift = isSub ? -STATE.tax : STATE.tax; // потоварная ставка со знаком
    // Кривая предложения ПОСЛЕ вмешательства — единый источник и для чисел, и для отрисовки.
    //  • специфическое: параллельный СДВИГ  S ± ставка (разрыв постоянен);
    //  • адвалорное: ПОВОРОТ. Налог: покупатель платит в (1+τ) раз больше, чем получает
    //    продавец при том же объёме ⇒ S_после = (1+τ)·S. Субсидия — зеркально: продавец
    //    получает в (1+τ) раз больше, чем платит покупатель ⇒ S_после = S/(1+τ).
    //    Вертикальный разрыв между S и S_после = τ·S(Q) — растёт вместе с Q.
    const factor = isSub ? 1 / (1 + tau) : (1 + tau);
    // texExpr — запись той же кривой формулой, для выгрузки в LaTeX (А49).
    // Отдельное поле, а не expr: движок кривых поле expr понимает по-своему,
    // и подкладывать ему выражение в объект, у которого есть только fn, нельзя.
    const sSrc = (STATE.S && STATE.S.expr) ? String(STATE.S.expr) : '';
    const sAfter = adv
      ? { fn: q => { const s = evalCurve(STATE.S, q); return isNaN(s) ? NaN : s * factor; },
          texExpr: sSrc ? '(' + sSrc + ') * ' + factor : '' }
      : { fn: q => evalCurve(STATE.S, q) + shift,
          texExpr: sSrc ? '(' + sSrc + ') + (' + shift + ')' : '' };
    const te = findEquilibrium(STATE.D, sAfter);
    if (te) {
      const Q1 = te.Q, Q0 = STATE.eq.Q;
      const Pb = evalCurve(STATE.D, Q1);          // цена покупателя
      // Цена продавца: в обоих случаях это S(Q1) (для потоварного — ровно Pb − ставка).
      const Ps = adv ? evalCurve(STATE.S, Q1) : (Pb - shift);
      const lo = Math.min(Q1, Q0), hi = Math.max(Q1, Q0);
      STATE.shift = shift;
      STATE.advTau = adv ? tau : 0;
      STATE.taxAfterS = sAfter;                   // ту же функцию рисует drawShiftedSupply
      // Эквивалентная запись «налог платит покупатель» (для рисования): при потоварном —
      // D − t, при адвалорном — D/(1+τ). Объём и цены получаются те же самые.
      const dSrc = (STATE.D && STATE.D.expr) ? String(STATE.D.expr) : '';
      STATE.taxAfterD = adv
        ? { fn: q => { const d = evalCurve(STATE.D, q); return isNaN(d) ? NaN : d / factor; },
            texExpr: dSrc ? '(' + dSrc + ') / ' + factor : '' }
        : { fn: q => evalCurve(STATE.D, q) - STATE.tax,
            texExpr: dSrc ? '(' + dSrc + ') - (' + STATE.tax + ')' : '' };
      STATE.taxEq = { Q: Q1, Pb, Ps };
      // Объём денег = площадь прямоугольника между ценами покупателя и продавца.
      // Для потоварного это в точности ставка·Q1, для адвалорного — τ·Ps·Q1 (налог).
      STATE.tx = Math.abs(Pb - Ps) * Q1;
      STATE.budget = (STATE.intervType === 'subsidy' ? -1 : 1) * STATE.tx;  // +сбор / -расход
      STATE.csTax = integrate(q => evalCurve(STATE.D, q) - Pb, 0, Q1);
      STATE.psTax = integrate(q => Ps - evalCurve(STATE.S, q), 0, Q1);
      // DWL — площадь между D и S на интервале между старым и новым Q (всегда > 0).
      STATE.dwl = areaBetween(q => evalCurve(STATE.D, q) - evalCurve(STATE.S, q), lo, hi);
      if (STATE.intervType === 'subsidy') {
        STATE.incBuyer = STATE.eq.P - Pb;         // выигрыш покупателя (цена упала)
        STATE.incSeller = Ps - STATE.eq.P;        // выигрыш продавца (цена выросла)
      } else {
        STATE.incBuyer = Pb - STATE.eq.P;         // бремя покупателя
        STATE.incSeller = STATE.eq.P - Ps;        // бремя продавца
      }
      STATE.taxActive = true;
    }
  }

  // Ценовое регулирование: потолок / пол цены (Задача 1).
  // Государство фиксирует P_reg. Объём торговли — короткая сторона рынка.
  STATE.pcMode = compMarket && scenarioNone && (STATE.intervType === 'ceiling' || STATE.intervType === 'floor');
  STATE.pcActive = false;
  STATE.pc = null;
  if (STATE.pcMode && STATE.D && STATE.S && STATE.eq && STATE.pReg > 0) {
    const Preg = STATE.pReg;
    const isCeiling = (STATE.intervType === 'ceiling');
    // Связывает ли регулирование: потолок ниже равновесия / пол выше равновесия.
    const binding = isCeiling ? (Preg < STATE.eq.P) : (Preg > STATE.eq.P);
    const Qd = invCurve(STATE.D, Preg);   // объём спроса при цене Preg (D⁻¹)
    const Qs = invCurve(STATE.S, Preg);   // объём предложения при цене Preg (S⁻¹)
    const Qtrade = (Qd != null && Qs != null) ? Math.min(Qd, Qs) : null;  // короткая сторона
    const gap = (Qd != null && Qs != null) ? Math.abs(Qd - Qs) : null;    // дефицит/избыток
    STATE.pc = { Preg, isCeiling, binding, Qd, Qs, Qtrade, gap };
    if (binding && Qtrade != null) {
      // CS / PS считаем интегрированием по фактическому объёму торговли.
      STATE.pc.cs = integrate(q => evalCurve(STATE.D, q) - Preg, 0, Qtrade);
      STATE.pc.ps = integrate(q => Preg - evalCurve(STATE.S, q), 0, Qtrade);
      STATE.pc.sw = STATE.pc.cs + STATE.pc.ps;
      // DWL — площадь между D и S от Q_trade до Q* (недо-/перепроизводство).
      const lo = Math.min(Qtrade, STATE.eq.Q), hi = Math.max(Qtrade, STATE.eq.Q);
      STATE.pc.dwl = areaBetween(q => evalCurve(STATE.D, q) - evalCurve(STATE.S, q), lo, hi);
      STATE.pcActive = true;
    }
  }

  // Монополия: оптимум MR = MC, цена берётся с кривой спроса (Задача 3).
  STATE.mono = null;
  if (STATE.market === 'monopoly' && STATE.D && (mcSourceCurve() || curveByRole('tc'))) {
    const Qm = findRoot(q => marginalRevenue(STATE.D, q) - mcAt(q));   // MR(Q) = MC(Q)
    if (Qm != null && Qm > 0) {
      const Pm = evalCurve(STATE.D, Qm);          // цена монополии — на кривой спроса
      const mcAtQm = mcAt(Qm);
      const Qc = findRoot(q => evalCurve(STATE.D, q) - mcAt(q));       // конкуренция: D = MC
      const Pc = (Qc != null) ? mcAt(Qc) : null;
      let dwl = null;
      if (Qc != null) {                            // потери — площадь между D и MC от Qm до Qc
        const lo = Math.min(Qm, Qc), hi = Math.max(Qm, Qc);
        dwl = areaBetween(q => evalCurve(STATE.D, q) - mcAt(q), lo, hi);
      }
      let profit = null;                           // прибыль (TR − TC) — только если задана ATC
      const ATC = curveByRole('atc');
      if (ATC) { const a = evalCurve(ATC, Qm); if (!isNaN(a)) profit = (Pm - a) * Qm; }
      // Области монополии (Задача 1) — все численным интегрированием от 0 до Qm.
      // Под спросом до Qm три слоя без перекрытия: VC (под MC), PS (MC..Pm), CS (Pm..D).
      const csM = integrate(q => evalCurve(STATE.D, q) - Pm, 0, Qm);  // ∫ (D − Pm) dQ — излишек потребителя
      const vcM = integrate(q => mcAt(q), 0, Qm);                     // ∫ MC dQ — переменные издержки (VC(0)=0)
      const psM = integrate(q => Pm - mcAt(q), 0, Qm);               // ∫ (Pm − MC) dQ = TR − VC — излишек производителя
      STATE.mono = { Qm, Pm, mcAtQm, Qc, Pc, dwl, profit, csM, vcM, psM };
    }
  }

  // Вмешательство государства в монополии (Фаза 2): налог/субсидия (сдвиг MC,
  // оптимум MR = MC ± ставка), потолок (готовая ломаная-MR логика) и пол цены.
  // Активно только в обычной монополии и обычном сценарии; управляется ОБЩИМ
  // блоком «Вмешательство» — теми же intervType / STATE.tax / STATE.pReg, что и конкуренция.
  STATE.monoCeil = null; STATE.monoTax = null; STATE.monoFloor = null;
  if (STATE.market === 'monopoly' && STATE.monoMode === 'simple' && scenarioNone && STATE.mono) {
    const it = STATE.intervType;
    if ((it === 'tax' || it === 'subsidy') && STATE.tax > 0) {
      STATE.monoTax = monopolyTax(it === 'subsidy' ? -STATE.tax : STATE.tax);   // shift: +t налог / −s субсидия
    } else if (it === 'ceiling' && STATE.pReg > 0) {
      STATE.monoCeil = monopolyCeiling(STATE.pReg);
    } else if (it === 'floor' && STATE.pReg > 0) {
      STATE.monoFloor = monopolyFloor(STATE.pReg);
    }
  }

  // Естественная монополия (Фаза 3в): считается ПОВЕРХ обычной монополии —
  // Qm/Pm/Qc берутся из STATE.mono, добавляются FC, ATC и два режима регулирования.
  STATE.natural = null;
  if (STATE.market === 'monopoly' && STATE.monoMode === 'natural' && STATE.mono) recomputeNatural();

  // Ценовая дискриминация 1-й степени (Задача 4): монополист забирает весь излишек,
  // продавая каждую единицу по её цене спроса до точки, где спрос = MC (= конкурентный выпуск).
  STATE.discr1 = null;
  if (STATE.market === 'monopoly' && STATE.monoMode === 'discr1' && STATE.D && (mcSourceCurve() || curveByRole('tc'))) {
    const Qcomp = findRoot(q => evalCurve(STATE.D, q) - mcAt(q));   // выпуск: D = MC
    if (Qcomp != null && Qcomp > 0) {
      const profit = integrate(q => evalCurve(STATE.D, q) - mcAt(q), 0, Qcomp);   // вся область между D и MC
      STATE.discr1 = { Qcomp, profit };   // CS=0, DWL=0
    }
  }

  // Эластичность спроса вдоль кривой (Задача 2). Точка вдоль D + единичная точка (MR=0).
  STATE.elast = null;
  if (compMarket && STATE.scenario === 'elasticity' && STATE.D) {
    const D = STATE.D;
    // Единичная эластичность |Ed|=1 ровно там, где MR=0 (MR = d(P·Q)/dQ).
    const unitQ = findRoot(q => marginalRevenue(D, q));
    let unit = null;
    if (unitQ != null && unitQ > 0) { const up = evalCurve(D, unitQ); if (!isNaN(up)) unit = { Q: unitQ, P: up, TR: up * unitQ }; }
    // Конец спроса по Q (где D пересекает ось Q): для зон и зажима точки.
    let qDmax = invCurve(D, 0);
    if (qDmax == null || !(qDmax > 0)) qDmax = CONFIG.Qmax;
    if (STATE.elastQ == null) STATE.elastQ = unit ? unit.Q : qDmax * 0.5;
    STATE.elastQ = Math.max(qDmax * 1e-3, Math.min(STATE.elastQ, qDmax * 0.999));
    const q = STATE.elastQ, p = evalCurve(D, q), slope = curveDeriv(D, q);
    const Ed = (q > 0 && slope !== 0 && !isNaN(slope) && !isNaN(p)) ? p / (q * slope) : NaN;
    STATE.elast = { unit, qDmax, q, p, slope, Ed, absEd: Math.abs(Ed), TR: p * q };
  }

  // Эластичность ПРЕДЛОЖЕНИЯ (Фаза 2а) — та же механика на кривой S.
  // Es = (dQ/dP)·(P/Q) = P/(Q·dP/dQ); у растущего предложения dP/dQ > 0, поэтому Es > 0.
  // Прямая через начало координат даёт Es = 1 при любом Q (наглядный частный случай).
  STATE.elastS = null;
  if (compMarket && STATE.scenario === 'elasticity' && STATE.S && STATE.showElastS) {
    const S = STATE.S;
    // Стартовая позиция — правее равновесия, чтобы точка на предложении не легла
    // ровно поверх точки на спросе (в равновесии обе кривые проходят через одну точку).
    if (STATE.elastQS == null) STATE.elastQS = STATE.eq ? STATE.eq.Q * 1.3 : CONFIG.Qmax * 0.6;
    STATE.elastQS = Math.max(CONFIG.Qmax * 1e-3, Math.min(STATE.elastQS, CONFIG.Qmax * 0.999));
    const q = STATE.elastQS, p = evalCurve(S, q), slope = curveDeriv(S, q);
    const Es = (q > 0 && slope !== 0 && !isNaN(slope) && !isNaN(p)) ? p / (q * slope) : NaN;
    STATE.elastS = { q, p, slope, Es, absEs: Math.abs(Es) };
  }

  // Разложение двойных сдвигов спроса и предложения (Задача 3): четыре равновесия.
  STATE.shiftActive = false;
  STATE.shiftRes = null;
  if (compMarket && STATE.scenario === 'shift' && STATE.D && STATE.S && STATE.eq) {
    const dD = STATE.shiftD || 0, dS = STATE.shiftS || 0;
    const Dsh = { fn: q => evalCurve(STATE.D, q) + dD };   // спрос со сдвигом по вертикали
    const Ssh = { fn: q => evalCurve(STATE.S, q) + dS };   // предложение со сдвигом по вертикали
    const E0 = STATE.eq;
    const Ed = findEquilibrium(Dsh, STATE.S);   // сдвинут только спрос
    const Es = findEquilibrium(STATE.D, Ssh);   // сдвинуто только предложение
    const E1 = findEquilibrium(Dsh, Ssh);       // оба сдвига вместе
    if (Ed && Es && E1) {
      STATE.shiftRes = {
        dD, dS, E0, Ed, Es, E1,
        dQ: { demand: Ed.Q - E0.Q, supply: Es.Q - E0.Q, total: E1.Q - E0.Q },
        dP: { demand: Ed.P - E0.P, supply: Es.P - E0.P, total: E1.P - E0.P },
      };
      STATE.shiftActive = true;
    }
  }

  // Внешний эффект и корректирующий инструмент Пигу (Задача 4 + Фаза 2б).
  // Два ЗЕРКАЛЬНЫХ случая, общий код:
  //   'neg' — эффект на ИЗДЕРЖКАХ: MSC = MPC + ext (MPC = кривая S). Рынок (D = MPC)
  //           выпускает БОЛЬШЕ оптимума (D = MSC) → перепроизводство, лечится НАЛОГОМ.
  //   'pos' — эффект на ВЫГОДЕ: MSB = MPB + ext (MPB = кривая D). Рынок (MPB = S)
  //           выпускает МЕНЬШЕ оптимума (MSB = S) → недопроизводство, лечится СУБСИДИЕЙ.
  // Рыночное равновесие в обоих случаях одно и то же (пересечение частных кривых).
  STATE.ext = null;
  if (compMarket && STATE.scenario === 'externality' && STATE.D && STATE.S && STATE.eq) {
    const pos = (STATE.extSign === 'pos');
    // Общественная кривая = частная той стороны, где сидит эффект, плюс внешний эффект.
    const social = pos
      ? (q => { const d = evalCurve(STATE.D, q), x = evalExt(q); return (isNaN(d) || isNaN(x)) ? NaN : d + x; })
      : (q => { const s = evalCurve(STATE.S, q), x = evalExt(q); return (isNaN(s) || isNaN(x)) ? NaN : s + x; });
    // «Противоположная» частная кривая — с ней общественная и пересекается в оптимуме.
    const other = pos ? (q => evalCurve(STATE.S, q)) : (q => evalCurve(STATE.D, q));
    const Qmkt = STATE.eq.Q, Pmkt = STATE.eq.P;
    const Qopt = findRoot(q => social(q) - other(q));
    let Popt = null, dwl = null, corrective = null, pigouEq = null;
    if (Qopt != null) {
      Popt = other(Qopt);                                  // высота точки пересечения
      const lo = Math.min(Qopt, Qmkt), hi = Math.max(Qopt, Qmkt);
      // Клин потерь — площадь между общественной и противоположной частной кривой.
      dwl = areaBetween(q => social(q) - other(q), lo, hi);
      corrective = evalExt(Qopt);                          // величина эффекта в оптимуме
      // Корректирующий инструмент приводит рынок ровно в Qопт, двигая предложение:
      // отрицательный эффект → налог (S + t); положительный → субсидия (S − s).
      const Sp = { fn: q => evalCurve(STATE.S, q) + (pos ? -corrective : corrective) };
      pigouEq = findEquilibrium(STATE.D, Sp);
    }
    STATE.ext = { pos, social, other, msc: social, Qmkt, Pmkt, Qopt, Popt, dwl,
                  corrective, pigou: corrective, pigouEq, applyPigou: STATE.applyPigou };
  }

  // Малая открытая экономика (Фаза 4в) — считается отдельной функцией.
  STATE.open = null;
  if (compMarket && STATE.scenario === 'openecon' && STATE.D && STATE.S) recomputeOpenEconomy();
}

/* =====================================================================
   БЛОК 8з. МАЛАЯ ОТКРЫТАЯ ЭКОНОМИКА (Фаза 4в).
   ВНИМАНИЕ: это модель ЧАСТИЧНОГО РАВНОВЕСИЯ по ЦЕНЕ — обычные D(Q) и S(Q)
   одного рынка. Её нельзя путать с рикардианскими моделями через КПВ
   («КТВ через КПВ» и «Как определяется мировая цена»), где по осям стоят
   два товара, а «цена» — это альтернативные издержки.
   Страна мала ⇒ мировая цена Pw дана извне и горизонтальна.
     Qd = D⁻¹(Pw), Qs = S⁻¹(Pw);  Qd > Qs → импорт, Qs > Qd → экспорт.
   Инструменты (для случая импорта):
     • тариф t: внутренняя цена P₁ = Pw + t, доход бюджета = t·(Qd′ − Qs′);
     • квота q: цена находится ЧИСЛЕННО из условия Qd(P) − Qs(P) = q,
       средний прямоугольник — рента от квоты (кому она достаётся, зависит
       от распределения лицензий, поэтому в подписи нейтрально).
   Потери разбиты на ДВА треугольника — искажение производства и искажение
   потребления; они не суммируются в одно число без разбивки.
   ===================================================================== */
function recomputeOpenEconomy() {
  const D = STATE.D, S = STATE.S, Pw = STATE.openPw;
  if (!(Pw > 0)) return;
  const Qd = invCurve(D, Pw), Qs = invCurve(S, Pw);
  if (Qd == null || Qs == null) { STATE.open = { Pw, error: 'При такой мировой цене объёмы спроса/предложения не определены.' }; return; }
  const importing = (Qd > Qs);
  const volume = Math.abs(Qd - Qs);
  // Свободная торговля: излишки считаются по фактическим объёмам сторон.
  const csFree = integrate(q => evalCurve(D, q) - Pw, 0, Qd);
  const psFree = integrate(q => Pw - evalCurve(S, q), 0, Qs);
  const swFree = csFree + psFree;
  // Автаркия — для сравнения (выигрыш от торговли).
  const aut = STATE.eq;
  const swAut = (aut && STATE.cs != null) ? STATE.sw : null;
  const gain = (swAut != null) ? swFree - swAut : null;

  const res = { Pw, Qd, Qs, importing, volume, csFree, psFree, swFree, swAut, gain,
                tool: STATE.openTool, aut };

  // Инструменты применяются только к импорту (экспортные — отложены, см. отчёт).
  if (STATE.openTool !== 'none' && importing) {
    let P1 = null, note = null;
    if (STATE.openTool === 'tariff') {
      P1 = Pw + STATE.openTariff;
    } else {
      // Квота: ищем внутреннюю цену, при которой избыточный спрос равен квоте.
      // Избыточный спрос Qd(P) − Qs(P) убывает по цене ⇒ корень единственный.
      const q = Math.max(0, STATE.openQuota);
      const excess = (p) => {
        const a = invCurve(D, p), b = invCurve(S, p);
        return (a == null || b == null) ? NaN : (a - b) - q;
      };
      const hiP = Math.max(Pw, CONFIG.Pmax);
      const root = findRootIn(excess, Pw, hiP);
      if (root != null) P1 = root;
      else { P1 = null; note = 'Цена под такую квоту не найдена: возможно, квота не меньше свободного импорта.'; }
    }
    if (P1 != null) {
      const Qd1 = invCurve(D, P1), Qs1 = invCurve(S, P1);
      if (Qd1 != null && Qs1 != null) {
        const vol1 = Math.max(0, Qd1 - Qs1);
        const money = (P1 - Pw) * vol1;                  // тариф → бюджет; квота → рента
        // ДВА треугольника потерь, по отдельности:
        //  производство — площадь между S и Pw на [Qs, Qs′] (дороже произвели дома);
        //  потребление  — площадь между D и Pw на [Qd′, Qd] (недопотребили).
        const dwlProd = areaBetween(q => evalCurve(S, q) - Pw, Qs, Qs1);
        const dwlCons = areaBetween(q => Pw - evalCurve(D, q), Qd1, Qd);
        const cs1 = integrate(q => evalCurve(D, q) - P1, 0, Qd1);
        const ps1 = integrate(q => P1 - evalCurve(S, q), 0, Qs1);
        res.tool = STATE.openTool;
        res.P1 = P1; res.Qd1 = Qd1; res.Qs1 = Qs1; res.vol1 = vol1;
        res.money = money; res.dwlProd = dwlProd; res.dwlCons = dwlCons;
        res.dwlTotal = dwlProd + dwlCons;
        res.cs1 = cs1; res.ps1 = ps1;
        res.sw1 = cs1 + ps1 + (STATE.openTool === 'tariff' ? money : 0);   // рента квоты — не доход государства
      }
    }
    res.note = note;
  } else if (STATE.openTool !== 'none' && !importing) {
    res.note = 'Тариф и импортная квота действуют, когда страна импортирует. Сейчас при Pw страна экспортирует.';
  }
  STATE.open = res;
}

// Заливки открытой экономики: излишки, деньги (бюджет/рента) и два треугольника потерь.
function drawOpenAreas() {
  const o = STATE.open; if (!o || o.error) return;
  const D = STATE.D, S = STATE.S;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const out = []; for (let i = 0; i <= 100; i++) out.push(a + (b - a) * i / 100); return out; };
  const Pdom = (o.P1 != null) ? o.P1 : o.Pw;             // фактическая внутренняя цена
  const qD = (o.Qd1 != null) ? o.Qd1 : o.Qd;
  const qS = (o.Qs1 != null) ? o.Qs1 : o.Qs;
  if (STATE.showCS && qD > 0) {
    const a = d3.area().x(d => sx(d)).y0(sy(Pdom)).y1(d => sy(evalCurve(D, d)));
    g.append('path').datum(samp(0, qD)).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  if (STATE.showPS && qS > 0) {
    const a = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(S, d))).y1(sy(Pdom));
    g.append('path').datum(samp(0, qS)).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек продавца (PS)');
  }
  if (o.P1 == null) return;
  // Прямоугольник денег: между Pw и внутренней ценой, шириной в фактический импорт.
  if (STATE.showOpenMoney && o.vol1 > 1e-9) {
    g.append('rect').attr('x', sx(qS)).attr('y', sy(o.P1))
      .attr('width', sx(qD) - sx(qS)).attr('height', sy(o.Pw) - sy(o.P1))
      .attr('fill', COL.tax).attr('opacity', 0.22).attr('data-legend', STATE.openTool === 'quota' ? 'Рента квоты' : 'Доход бюджета');
  }
  // Два треугольника потерь — рисуем отдельными фигурами, чтобы их было ВИДНО как два.
  if (STATE.showOpenDwl) {
    if (o.Qs1 > o.Qs + 1e-9) {
      const a = d3.area().x(d => sx(d)).y0(sy(o.Pw)).y1(d => sy(evalCurve(S, d)));
      g.append('path').datum(samp(o.Qs, o.Qs1)).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.38).attr('data-legend', 'Потери общества (DWL)');
    }
    if (o.Qd > o.Qd1 + 1e-9) {
      const a = d3.area().x(d => sx(d)).y0(sy(o.Pw)).y1(d => sy(evalCurve(D, d)));
      g.append('path').datum(samp(o.Qd1, o.Qd)).attr('d', a).attr('fill', COL.dwl).attr('opacity', 0.38).attr('data-legend', 'Потери общества (DWL)');
    }
  }
}

// Линии цен (мировая — перетаскиваемая, внутренняя — при вмешательстве) и полоса торговли.
function drawOpenLines() {
  const o = STATE.open; if (!o) return;
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax), g = svg.append('g');
  const yPw = sy(o.Pw);
  g.append('line').attr('x1', ox).attr('y1', yPw).attr('x2', xMax).attr('y2', yPw)
    .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueY(g, ox, yPw, fmt(o.Pw), 'w');
  if (o.error) { attachOpenPwDrag(g.append('rect').attr('x', ox).attr('y', yPw - 12).attr('width', xMax - ox).attr('height', 24).attr('fill', 'transparent').style('cursor', 'grab')); return; }
  // Внутренняя цена при тарифе/квоте — вторая линия.
  if (o.P1 != null) {
    const y1 = sy(o.P1);
    g.append('line').attr('x1', ox).attr('y1', y1).attr('x2', xMax).attr('y2', y1)
      .attr('stroke', COL.MR).attr('stroke-width', 2.5).attr('stroke-dasharray', '7 4').style('pointer-events', 'none');
    axisValueY(g, ox, y1, fmt(o.P1), '1');
  }
  // Проекции и полоса объёма торговли на уровне действующей цены.
  const Pdom = (o.P1 != null) ? o.P1 : o.Pw;
  const yD = sy(Pdom);
  const qD = (o.Qd1 != null) ? o.Qd1 : o.Qd, qS = (o.Qs1 != null) ? o.Qs1 : o.Qs;
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(sx(qS), yD, sx(qS), oy); dash(sx(qD), yD, sx(qD), oy);
  axisValueX(g, sx(qS), oy, fmt(qS), 's');
  axisValueX(g, sx(qD), oy, fmt(qD), 'd');
  const lo = Math.min(sx(qS), sx(qD)), hi = Math.max(sx(qS), sx(qD));
  if (hi > lo + 1) {
    g.append('line').attr('x1', lo).attr('y1', yD).attr('x2', hi).attr('y2', yD)
      .attr('stroke', o.importing ? COL.D : COL.S).attr('stroke-width', 6).attr('opacity', 0.45);
    haloText(g, (lo + hi) / 2, yD - 12, (o.importing ? 'Импорт = ' : 'Экспорт = ') + fmt(Math.abs(qD - qS)), 'middle', 'auto');
  }
  // Точки на кривых + автаркическое равновесие бледным призраком.
  g.append('circle').attr('cx', sx(qS)).attr('cy', yD).attr('r', 4).attr('fill', COL.S).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  g.append('circle').attr('cx', sx(qD)).attr('cy', yD).attr('r', 4).attr('fill', COL.D).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  if (STATE.showGhost && o.aut) {
    const [px, py] = toPx(o.aut.Q, o.aut.P);
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4).attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
    g.append('text').attr('x', px + 7).attr('y', py - 6).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Автаркия');
  }
  // Зона захвата мировой цены (перетаскивание линии Pw).
  const hit = g.append('rect').attr('x', ox).attr('y', yPw - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  attachOpenPwDrag(hit);
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.86).attr('cy', yPw).attr('r', 7)
    .attr('fill', COL.reg).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

function attachOpenPwDrag(sel) {
  sel.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => { setOpenPw(sy.invert(event.y)); })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Единый путь смены мировой цены (ползунок, поле, перетаскивание линии).
function setOpenPw(p) {
  p = Math.max(0, Math.min(p, CONFIG.Pmax));
  STATE.openPw = p;
  const s = document.getElementById('open-pw-slider'); if (s) s.value = p;
  const l = document.getElementById('open-pw-val');    if (l) l.textContent = fmt(p);
  const i = document.getElementById('open-pw-input');  if (i) i.value = fmtInput(p);
  redrawAll();
}

// Переключатель инструмента: без вмешательства / тариф / квота.
function setOpenTool(tool) {
  STATE.openTool = (tool === 'tariff' || tool === 'quota') ? tool : 'none';
  [['oi-none', 'none'], ['oi-tariff', 'tariff'], ['oi-quota', 'quota']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', v === STATE.openTool); });
  const tf = document.getElementById('open-tariff-field'), qf = document.getElementById('open-quota-field');
  if (tf) tf.style.display = (STATE.openTool === 'tariff') ? '' : 'none';
  if (qf) qf.style.display = (STATE.openTool === 'quota') ? '' : 'none';
  if (typeof updatePult === 'function') updatePult();
  redrawAll();
}

// Табло открытой экономики: направление торговли, выигрыш, разбивка потерь.
function updateOpenPanel() {
  const box = document.getElementById('info-open'); if (!box) return;
  if (!STATE.D || !STATE.S) { box.innerHTML = '<div class="muted">Отметьте кривые D и S.</div>'; return; }
  const o = STATE.open;
  if (!o) { box.innerHTML = '<div class="muted">Задайте мировую цену Pw.</div>'; return; }
  if (o.error) { box.innerHTML = '<div class="warn">' + o.error + '</div>'; return; }
  let html = `<div class="stat"><span>Мировая цена Pw</span><b>${fmt(o.Pw)}</b></div>`;
  if (o.aut) html += `<div class="stat"><span>Автаркия: $(Q^*; P^*)$</span><b>(${fmt(o.aut.Q)}; ${fmt(o.aut.P)})</b></div>`;
  html += `<div class="stat"><span>При Pw: (Qd; Qs)</span><b>(${fmt(o.Qd)}; ${fmt(o.Qs)})</b></div>`;
  html += `<div class="stat"><span>${o.importing ? 'Импорт' : 'Экспорт'}</span><b>${fmt(o.volume)}</b></div>`;
  html += `<div class="stat"><span>(CS; PS) при своб. торговле</span><b>(${fmt(o.csFree)}; ${fmt(o.psFree)})</b></div>`;
  if (o.gain != null) html += `<div class="stat"><span>Выигрыш от торговли</span><b>${(o.gain >= 0 ? '+' : '') + fmt(o.gain)}</b></div>`;
  if (o.note) html += `<div class="warn" style="margin-top:6px;">${o.note}</div>`;
  if (o.P1 != null) {
    const isTar = (o.tool === 'tariff');
    html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
    html += `<div class="stat"><span>${isTar ? 'Тариф t' : 'Квота'}</span><b>${fmt(isTar ? STATE.openTariff : STATE.openQuota)}</b></div>`;
    html += `<div class="stat"><span>Внутренняя цена P₁</span><b>${fmt(o.P1)}</b></div>`;
    html += `<div class="stat"><span>($Q_d^{\\prime}$; $Q_s^{\\prime}$)</span><b>(${fmt(o.Qd1)}; ${fmt(o.Qs1)})</b></div>`;
    html += `<div class="stat"><span>Импорт после</span><b>${fmt(o.vol1)} (было ${fmt(o.volume)})</b></div>`;
    html += `<div class="stat"><span>${isTar ? 'Доход бюджета' : 'Рента от квоты'}</span><b>${fmt(o.money)}</b></div>`;
    if (!isTar) html += '<div class="hint">Рента от квоты это не доход государства: кому она достанется, ' +
      'зависит от того, как распределены лицензии на импорт (могут получить импортёры, иностранные ' +
      'поставщики или бюджет, если лицензии продаются).</div>';
    // Разбивка потерь — по отдельности, без «одного числа».
    html += `<div class="stat" style="margin-top:4px;"><span>Потери: искажение производства</span><b>${fmt(o.dwlProd)}</b></div>`;
    html += `<div class="stat"><span>Потери: искажение потребления</span><b>${fmt(o.dwlCons)}</b></div>`;
    html += `<div class="stat"><span>Итого потери</span><b>${fmtSum(o.dwlProd, o.dwlCons)}</b></div>`;
    html += '<div class="hint">Левый треугольник это производственное искажение: часть импорта заместили ' +
      'более дорогим отечественным выпуском. Правый это потребительское искажение: часть покупателей ушла с рынка ' +
      'из-за выросшей цены.</div>';
  }
  box.innerHTML = html;
}

// Точка равновесия E*: пунктирные проекции на оси + подпись.
function drawEquilibrium() {
  if (!STATE.eq) return;
  const { Q, P } = STATE.eq;
  const [px, py] = toPx(Q, P);
  const ox = sx(0), oy = sy(0);
  const g = svg.append('g').attr('class', 'equilibrium');

  // Пунктирные проекции к осям.
  g.append('line').attr('x1', px).attr('y1', py).attr('x2', px).attr('y2', oy)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  g.append('line').attr('x1', px).attr('y1', py).attr('x2', ox).attr('y2', py)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');

  // Числа Q* и P* у осей (с белой обводкой, чтобы читались поверх делений).
  axisValueX(g, px, oy, fmt(Q), '');
  axisValueY(g, ox, py, fmt(P), '');

  /* Кружок у точки пересечения снят решением владельца: пунктиры к осям уже
     показывают, где точка, а числа на осях — какая она. Подпись «E*» остаётся:
     это ИМЯ точки, а не повтор переменной. */
  pointName(g, px, py, 'E*', COL.ink);
}

// Текст с белой обводкой (halo) — чтобы подписи равновесия читались над сеткой.
// Подпись держится внутри холста: поля стали узкими (Фаза 1), и длинная строка
// вроде «P*=50» у оси Y иначе обрезалась бы левым краем. Не влезла слева —
// разворачиваем ту же подпись внутрь графика; у верхнего и нижнего края
// опускаем и поднимаем. Это только про место на экране, не про математику.
/* ── Математика в подписях на графике (Фаза 9) ────────────────────────
   Разбираем лёгкую разметку и рисуем настоящие индексы: «x*» — звёздочка
   верхним индексом, «Q_1» — нижним, «x^2» — верхним. Фигурные скобки после
   ^ и _ берут несколько символов: «Q_{макс}».

   Почему tspan, а не KaTeX: KaTeX печатает HTML, его пришлось бы класть в
   foreignObject. Такая подпись не попала бы ни в PNG (снимок холста рисует
   SVG в canvas, а foreignObject там не отрисовывается), ни в выгрузку .tex,
   и ещё ловила бы щелчки поверх графика. tspan остаётся частью SVG: ездит
   вместе с точкой, попадает во все выгрузки и щелчкам не мешает. */
function mathTspans(sel, txt) {
  const s = String(txt == null ? '' : txt);
  const parts = [];
  let buf = '', i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (ch === '*' && buf && /[A-Za-zА-Яа-яЁё0-9)\]]$/.test(buf)) {
      parts.push({ t: 'txt', v: buf }); buf = '';
      parts.push({ t: 'sup', v: '∗' }); i++; continue;
    }
    if ((ch === '^' || ch === '_') && i + 1 < s.length) {
      let j = i + 1, v;
      if (s[j] === '{') { const k = s.indexOf('}', j); v = s.slice(j + 1, k < 0 ? s.length : k); j = (k < 0 ? s.length : k) + 1; }
      else { v = s[j]; j++; }
      parts.push({ t: 'txt', v: buf }); buf = '';
      parts.push({ t: ch === '^' ? 'sup' : 'sub', v: v });
      i = j; continue;
    }
    buf += ch; i++;
  }
  parts.push({ t: 'txt', v: buf });
  // dy у tspan накапливается, поэтому после индекса возвращаем базовую линию.
  let shift = 0;
  parts.forEach(p => {
    if (!p.v) return;
    if (p.t === 'txt') {
      const ts = sel.append('tspan').text(p.v);
      if (shift) { ts.attr('dy', (-shift).toFixed(2) + 'em'); shift = 0; }
    } else {
      const d = (p.t === 'sup') ? -0.42 : 0.26;
      sel.append('tspan').attr('dy', (d - shift).toFixed(2) + 'em')
        .attr('font-size', '76%').text(p.v);
      shift = d;
    }
  });
  if (shift) sel.append('tspan').attr('dy', (-shift).toFixed(2) + 'em').text('\u200b');
  return sel;
}

// Есть ли в подписи что-то математическое: иначе не стоит и разбирать.
function hasMathMarkup(txt) { return /[*^_]/.test(String(txt == null ? '' : txt)); }

/* Подпись-величина на холсте (А28 · А29).

   Было: в правой панели «$P_b$» набиралось формулой, а на холсте та же
   величина стояла обычным текстом «Pb=60». Даже внутри холста согласия не
   было: «Q₁» пользовалось юникодной цифрой, а «Pb» и «Ps» — обычными буквами.
   Всего таких «текстовых формул» на холсте было больше восьмидесяти.

   Разбор ведёт ТА ЖЕ функция, что и для панели и для файла (qtyParts), так что
   решение «величина это или проза» принимается один раз и в одном месте.
   На холсте формула набирается средствами самого SVG (tspan со смещением
   базовой линии): KaTeX сюда не встанет, а вставка через foreignObject
   выпала бы из снимка холста, то есть из выгрузки в PNG. */
function qtyTspans(sel, raw) {
  const parts = qtyParts(raw);
  let shift = 0;
  const put = (v, kind) => {
    if (!v) return;
    if (kind === 'txt') {
      const ts = sel.append('tspan').text(v);
      if (shift) { ts.attr('dy', (-shift).toFixed(2) + 'em'); shift = 0; }
      return;
    }
    const d = (kind === 'sup') ? -0.42 : 0.26;
    sel.append('tspan').attr('dy', (d - shift).toFixed(2) + 'em')
      .attr('font-size', '76%').text(v);
    shift = d;
  };
  parts.forEach(p => {
    if (p.kind === 'sym') {
      put(p.greek ? qtyGreekChar(p.greek) : p.s, 'txt');
      if (p.sub) put(p.sub, 'sub');
      if (p.sup) put(p.sup, 'sup');
    } else put(p.s, 'txt');
  });
  // dy у tspan накапливается: возвращаем базовую линию, иначе следующая
  // подпись в той же строке поедет вслед за индексом.
  if (shift) sel.append('tspan').attr('dy', (-shift).toFixed(2) + 'em').text('​');
  return sel;
}

// Греческая буква остаётся собой: в LaTeX она пишется командой, на экране
// печатается как есть.
function qtyGreekChar(cmd) {
  const back = Object.keys(QTY_GREEK).find(ch => QTY_GREEK[ch] === cmd);
  return back || cmd;
}

/* Единая точка печати подписи. Явная разметка (P_b, Q^2) разбирается как
   раньше; величина без разметки (Pb, Q₁) — через общий разбор; проза
   печатается как есть. */
/* ⚠️ НА ХОЛСТЕ НЕТ KaTeX, ПОЭТОМУ `$…$` РАЗБИРАЕТ ЭТА ФУНКЦИЯ (п. 42).

   Подписи холста набираются средствами самого SVG (tspan со сдвигом базовой
   линии): KaTeX сюда не встанет, а вставка через foreignObject выпала бы из
   снимка холста, то есть из выгрузки в PNG. Но авторы сцен пишут подписи ТАК,
   КАК ПРИВЫКЛИ в остальном проекте — долларами и командами. Разбор их не
   понимал (`hasMathMarkup` проверял только `[*^_]`), и на график уезжал
   сырой код: «перегиб TP: $\max MP$ при $L = 10$», «$f'(x)$, производная».
   Замер: 12 подписей в двух сценах.

   Лечим в ОДНОМ месте, а не в четырёх строках сцен: иначе следующая подпись,
   написанная долларами, снова окажется сырой на экране. Доллар-разделитель
   снимается, известные команды переводятся в юникод, `\$` остаётся настоящим
   знаком доллара (в проекте литеральный доллар так и пишется). Всё остальное
   отдаётся прежнему разбору `^` / `_` / `*`. */
const TEX_ON_CANVAS = [
  [/\\max\b/g, 'max'], [/\\min\b/g, 'min'], [/\\log\b/g, 'log'],
  [/\\ln\b/g, 'ln'], [/\\lim\b/g, 'lim'], [/\\text\{([^}]*)\}/g, '$1'],
  [/\\mathrm\{([^}]*)\}/g, '$1'], [/\\operatorname\{([^}]*)\}/g, '$1'],
  [/\\ne(?![a-zA-Z])/g, '\u2260'], [/\\le(?![a-zA-Z])/g, '\u2264'],
  [/\\ge(?![a-zA-Z])/g, '\u2265'], [/\\approx\b/g, '\u2248'],
  [/\\cdot\b/g, '\u00b7'], [/\\times\b/g, '\u00d7'],
  [/\\to\b/g, '\u2192'], [/\\infty\b/g, '\u221e'],
  [/\\prime\b/g, '\u2032'], [/\\Delta\b/g, '\u0394'],
  [/\\alpha\b/g, '\u03b1'], [/\\beta\b/g, '\u03b2'],
  [/\\pi\b/g, '\u03c0'], [/\\lambda\b/g, '\u03bb'],
  [/\\left|\\right/g, ''], [/\\,|\\;|\\!/g, ''],
];
const DOLLAR_HOLD = '\uE001';          // место настоящего доллара на время разбора

function texToCanvasText(raw) {
  let s = String(raw == null ? '' : raw);
  if (!/[$\\]/.test(s)) return s;
  s = s.replace(/\\\$/g, DOLLAR_HOLD);   // «\$» — это знак доллара, не разделитель
  s = s.replace(/\$/g, '');                // разделители формул снимаем
  TEX_ON_CANVAS.forEach(([re, to]) => { s = s.replace(re, to); });
  return s.replace(new RegExp(DOLLAR_HOLD, 'g'), '$');
}

function renderLabelText(sel, txt) {
  const s = texToCanvasText(txt);
  /* ⚠️ ИСХОДНАЯ РАЗМЕТКА ПОДПИСИ ОСТАЁТСЯ ПРИ УЗЛЕ.
     Нарисованная подпись разложена на tspan'ы, и собрать из них разметку
     обратно нельзя: «60» с подстрочным «b» читается как «60b», то есть
     индекс теряется молча. На холсте это незаметно (там он нарисован), а в
     выгрузке на бумагу подпись уезжала уже без него. Вместо угадывания по
     готовой картинке держим исходную запись рядом с узлом — её и читает
     сборка файла. */
  if (sel && sel.attr) sel.attr('data-raw', s);
  if (hasMathMarkup(s)) return mathTspans(sel, s);
  if (typeof qtyIsQuantity === 'function' && qtyIsQuantity(s)) return qtyTspans(sel, s);
  return sel.text(s);
}

/* Седьмой аргумент — `{ noFlip: true }`: подпись НЕ разворачивать, даже если
   она не влезает. Нужен подписям координат у оси цены: развернувшись, они
   уезжают в первую четверть, а там их быть не должно (см. axisValueY). Такие
   подписи считают своё место сами, по настоящей ширине нарисованного текста. */
function haloText(g, x, y, txt, anchor, baseline, opts) {
  const w = String(txt).length * 5.9 + 6;      // ширина строки при кегле 10
  const noFlip = !!(opts && opts.noFlip);
  let ax = anchor, px = x;
  if (noFlip) { /* место выбирает вызывающий */ }
  else if (ax === 'end' && x - w < 2) { ax = 'start'; px = x + 8; }
  else if (ax === 'start' && x + w > W - 2) { ax = 'end'; px = x - 8; }
  else if (ax === 'middle') px = Math.max(w / 2 + 2, Math.min(W - w / 2 - 2, x));
  const py = Math.max(9, Math.min(H - 4, y));
  const t = g.append('text').attr('x', px).attr('y', py)
    .attr('text-anchor', ax).attr('dominant-baseline', baseline)
    .attr('font-size', FS.small).attr('font-weight', 600).attr('fill', COL.ink)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 3);
  renderLabelText(t, txt);
  return t;
}

/* ПРАВИЛО 47. НА ХОЛСТЕ У ТОЧКИ СТОИТ ТОЛЬКО ОБОЗНАЧЕНИЕ.
   Одна заглавная латинская буква; звёздочка — тогда и только тогда, когда со
   звёздочкой подписаны координаты («Q*» и «P*» → точка «E*»).
   ЧТО это за точка, говорит легенда или панель, а не холст: холст и так самый
   плотный объект на экране. До этой функции на нём жили пять грамматик сразу —
   «E*», «E», «M», «M · монополия», «AC · P=ATC».
   Класс `point-name` нужен реестру обозначений (Добавка В) и проверке канона:
   собирать обозначения «по коротким текстам» нельзя, деление оси «60» тоже
   короткое. */
function pointName(g, px, py, sym, color, opts) {
  if (!sym) return null;
  const o = opts || {};
  const t = g.append('text').attr('class', 'point-name')
    .attr('x', px + (o.dx == null ? 8 : o.dx))
    .attr('y', py + (o.dy == null ? -8 : o.dy))
    .attr('font-size', o.size || FS.large).attr('font-weight', o.weight || 600)
    .attr('fill', color || COL.ink)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5);
  renderLabelText(t, sym);
  return t;
}

// Подпись значения у оси Y (зарплата/цена). Разворот внутрь графика теперь
// умеет сам haloText, поэтому здесь остался только вызов.
function yWageLabel(g, ox, py, txt) {
  haloText(g, ox - 8, py, txt, 'end', 'middle');
}

/* Значение зарплаты у оси — тем же помощником, что и все прочие координаты. */
function yWageValue(g, ox, py, value, idx) { return axisValueY(g, ox, py, value, idx || ''); }

/* Заголовок раздела равновесия — СВОЙСТВО СЦЕНЫ, а не константа (А51 · А52).

   Раньше «Равновесие D = S» стояло в разметке жёстко и показывалось в
   тринадцати сценах, шесть из которых монопольные. У монополиста кривой
   предложения не существует вовсе, оптимум там MR = MC, и в трёх сценах
   раздел вдобавок навсегда застревал в состоянии «Отметьте одну кривую как D»:
   второй кривой в модели нет, значит и появиться ему было не из чего. Ниже,
   отдельным блоком, та же сцена честно показывала Qm = 40.

   Малая открытая экономика оставлена, но переименована. Точка D = S там
   существует и нужна: это равновесие БЕЗ торговли, то самое, с которым
   сравнивают мировую цену. Убирать её нельзя, а называть «равновесием» без
   оговорки — сбивать с толку: при мировой цене рынок приходит в другую точку,
   а разрыв закрывает импорт. */
/* Список монопольных сюжетов — по КЛЮЧУ КАРТОЧКИ, а не по STATE.market.
   Проверка через STATE.market казалась естественной и оказалась неверной:
   после монополии этот флаг остаётся поднятым в сценах рынка труда
   (монопсония и двусторонняя монополия ставят его сами), и заголовок
   «Оптимум монополии» уезжал туда, где его быть не должно. Ключ карточки
   такой двусмысленности не имеет. */
const MONOPOLY_SCENES = ['mono', 'mono-nat', 'mono-d1', 'mono-d3', 'mono-kink', 'monoexport'];
function isMonopolyScene() {
  const key = (typeof baseScene === 'function') ? baseScene(STATE.sceneKey) : STATE.sceneKey;
  return MONOPOLY_SCENES.indexOf(STATE.sceneKey) >= 0 || MONOPOLY_SCENES.indexOf(key) >= 0;
}

/* п. 82. Условие равновесия — МАТЕМАТИКА, и набирается как математика.
   Обычным текстом среди набранных формул «D = S» читалось как опечатка:
   на соседних строках те же буквы стоят курсивом. */
function eqSectionTitle() {
  if (isMonopolyScene()) return 'Оптимум монополии: $MR = MC$';
  if (STATE.scenario === 'openecon') return 'Равновесие без торговли (автаркия)';
  return 'Равновесие $D = S$';
}

/* ⚠️ Сверяем ИСХОДНУЮ строку, а не то, что на экране: после KaTeX внутри
   заголовка лежат его узлы, `textContent` уже не равен исходнику, и сравнение
   с ним переписывало бы заголовок на каждой перерисовке, стирая набор. */
function updateEqSectionTitle() {
  const sec = document.getElementById('sec-eq');
  const t = sec && sec.querySelector('.section-title');
  if (!t) return;
  const raw = eqSectionTitle();
  if (t.dataset.raw === raw) return;
  t.dataset.raw = raw;
  t.textContent = raw;
  if (typeof renderMathIn === 'function') renderMathIn(t);
}

// Табло слева: показываем Q* и P* (или подсказку / «не найдено»).
function updateInfoPanel() {
  updateEqSectionTitle();
  const box = document.getElementById('info-eq');
  if (!box) return;
  /* В монополии числа даёт блок «Монополия» под тем же заголовком: Qm, Pm и
     сравнение с конкурентным выпуском. Своего содержимого у раздела здесь
     нет, и подсказка про «отметьте кривую S» тут была бы неправдой. */
  if (isMonopolyScene()) { box.innerHTML = ''; return; }
  if (!STATE.D || !STATE.S) {
    box.innerHTML = '<div class="muted">Отметьте одну кривую как D&nbsp;(спрос), другую как S&nbsp;(предложение) в списке кривых.</div>';
    return;
  }
  if (!STATE.eq) {
    /* П7. Раньше об отсутствии равновесия говорили ТРИ блока подряд: этот,
       «Излишки» («появятся после нахождения равновесия») и «Вмешательство»
       («двигайте ползунок»). Два последних теперь молчат — говорит один, и
       он называет не только факт, но и что сделать (канон 2.3). */
    box.innerHTML = '<div class="warn">Кривые не пересекаются в первой четверти, ' +
      'поэтому равновесия нет. Измените формулу спроса или предложения ' +
      'либо отодвиньте границы плоскости.</div>';
    return;
  }
  let html =
    `<div class="stat"><span>$Q^*$ (количество)</span><b>${fmt(STATE.eq.Q)}</b></div>` +
    `<div class="stat"><span>$P^*$ (цена)</span><b>${fmt(STATE.eq.P)}</b></div>` +
    beforeInterventionNote();
  /* Б31. Кривые могут пересечься не один раз, и тогда равновесие не одно.
     Молчать об этом нельзя: все дальнейшие числа считаются вокруг ОДНОГО
     из них, и человек вправе знать, вокруг какого. */
  const n = crossingCount(q => evalCurve(STATE.D, q) - evalCurve(STATE.S, q), 0, CONFIG.Qmax);
  if (n > 1) html += `<div class="hint">Кривые пересекаются ${n} раза, то есть равновесий несколько. ` +
    `Взято ближайшее к началу координат: ${'$Q^* = ' + fmt(STATE.eq.Q) + '$'}. Излишки и потери посчитаны вокруг него.</div>`;
  box.innerHTML = html;
}

/* ---------------------------------------------------------------------
   БЛОК 6. ОБЛАСТИ CS / PS — заливка через d3.area (численные площади).
   --------------------------------------------------------------------- */
function drawAreas() {
  if (!STATE.eq) return;
  const { Q, P } = STATE.eq;
  if (Q <= 0) return;
  const g = svg.append('g').attr('class', 'areas').attr('clip-path', 'url(#plot-clip)');

  // Частая сетка по Q от 0 до Q* — заливка повторяет форму кривой.
  const samples = [];
  for (let i = 0; i <= 100; i++) samples.push(Q * i / 100);

  // CS — между ценой P* (низ) и кривой спроса (верх).
  if (STATE.showCS && STATE.D) {
    const csArea = d3.area().x(d => sx(d)).y0(sy(P)).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(samples).attr('d', csArea).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  // PS — между кривой предложения (низ) и ценой P* (верх).
  if (STATE.showPS && STATE.S) {
    const psArea = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(sy(P));
    g.append('path').datum(samples).attr('d', psArea).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек продавца (PS)');
  }
}

// Табло излишков: CS, PS и общественное благосостояние SW.
/* Оговорка «эти числа — до вмешательства» (п. 5, канон 2.13).
   В сцене налога сверху стояло «Q* 50, CS 1 250», а в таблице ниже «После:
   Q 40, CS 800» — два разных значения одной величины на одном экране, и ничто
   не говорило, что верхнее относится к рынку ДО вмешательства. Оговорка стоит
   ПОД числами, а не в сноске, и называет область действия. */
function beforeInterventionNote() {
  const pcOn = !!(STATE.pc && STATE.pc.binding && STATE.pReg > 0);
  if (!STATE.taxActive && !pcOn) return '';
  return '<div class="scope-note">до вмешательства государства</div>';
}

function updateAreasPanel() {
  const box = document.getElementById('info-areas');
  if (!box) return;
  /* П6. В монополии излишки считает и показывает блок «Монополия»: там свои
     Qm, Pm, CS и потери. Заглушка «появятся после нахождения равновесия»
     обещала числа, которые уже стоят рядом на том же экране. */
  if (isMonopolyScene()) { box.innerHTML = ''; return; }
  if (!STATE.eq || STATE.cs == null) { box.innerHTML = ''; return; }   // говорит блок равновесия, см. П7
  box.innerHTML =
    `<div class="stat"><span>$CS$ (потребитель)</span><b>${fmt(STATE.cs)}</b></div>` +
    `<div class="stat"><span>$PS$ (производитель)</span><b>${fmt(STATE.ps)}</b></div>` +
    `<div class="stat"><span>$SW = CS + PS$</span><b>${fmtSum(STATE.cs, STATE.ps)}</b></div>` +
    beforeInterventionNote();
}

/* ---------------------------------------------------------------------
   БЛОК 8. СЦЕНАРИЙ «НАЛОГ» — сдвиг предложения, новые области, клин.
   --------------------------------------------------------------------- */

// Сдвинутая пунктиром кривая. При налоге на ПРОДАВЦА (по умолчанию) и при субсидии
// двигается предложение (S ± ставка). При налоге на ПОКУПАТЕЛЯ (Задача 1) двигается
// спрос вниз (D − t): эффективный спрос. Итоговые числа в обоих случаях идентичны —
// меняется только то, какую кривую рисуем; считаем в recompute одинаково.
function drawShiftedSupply() {
  if (!STATE.taxActive) return;
  const buyerTax = (STATE.intervType === 'tax' && STATE.taxSide === 'buyer');
  const base = buyerTax ? STATE.D : STATE.S;              // чью кривую рисуем сдвинутой
  // Берём ГОТОВУЮ функцию «после вмешательства» из recompute — она уже знает,
  // сдвиг это (потоварное) или поворот (адвалорное). Никакой параллельной математики.
  const after = buyerTax ? STATE.taxAfterD : STATE.taxAfterS;
  if (!after) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const pts = [];
  for (let i = 0; i <= 400; i++) {
    const q = CONFIG.Qmax * i / 400;
    const v = evalCurve(after, q);
    pts.push(isNaN(v) ? null : [q, v]);
  }
  // Формулу объявляем экспорту: на бумагу кривая уйдёт формулой, а не таблицей.
  markExpr(g.append('path').datum(pts).attr('fill', 'none').attr('stroke', base.color)
    .attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line), after);
  // Ярлык сдвинутой кривой. Ищем видимый якорь (Фаза 3): при адвалорной ставке
  // кривая круто уходит вверх и на фиксированной точке ярлык раньше пропадал.
  const adv = (STATE.taxKind === 'advalorem');
  const isSub = (STATE.intervType === 'subsidy');
  const nm = buyerTax ? (adv ? 'D/(1+τ)' : 'D − t')
                      : (adv ? (isSub ? 'S/(1+τ)' : 'S·(1+τ)') : (isSub ? 'S − s' : 'S + t'));
  labelCurve(g, q => evalCurve(after, q), nm, base.color, { from: 0.82 });
}

// Заливки сценария вмешательства: CS, PS, деньги бюджета (прямоугольник), DWL (потери).
function drawTaxAreas() {
  if (!STATE.taxActive) return;
  const { Q, Pb, Ps } = STATE.taxEq;
  const Q0 = STATE.eq.Q;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const s1 = samp(0, Q);

  if (STATE.showCS) {   // CS: между ценой покупателя Pb и спросом
    const a = d3.area().x(d => sx(d)).y0(sy(Pb)).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  if (STATE.showPS) {   // PS: между предложением и ценой продавца Ps
    const a = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(sy(Ps));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек продавца (PS)');
  }
  // Деньги бюджета (сбор налога / расход на субсидию) — прямоугольник между Pb и Ps
  // на [0, Q1]. По фиксированной палитре налог/субсидия/бюджет — один зелёный цвет.
  const lowP = Math.min(Pb, Ps), highP = Math.max(Pb, Ps);
  const aTx = d3.area().x(d => sx(d)).y0(sy(lowP)).y1(sy(highP));
  g.append('path').datum(s1).attr('d', aTx)
    .attr('fill', COL.tax).attr('opacity', 0.22).attr('data-legend', STATE.intervType === 'subsidy' ? 'Расход бюджета' : 'Сбор бюджета');
  // DWL — между D и S на интервале между старым и новым Q (налог: [Q1,Q0]; субсидия: [Q0,Q1]).
  const lo = Math.min(Q, Q0), hi = Math.max(Q, Q0);
  if (hi > lo) {
    const s2 = samp(lo, hi);
    const aD = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
  }
}

// Точки E₀/E₁, проекции, подписи и перетаскиваемый клин налога.
function drawTaxPoints() {
  if (!STATE.taxActive) return;
  const { Q, Pb, Ps } = STATE.taxEq;
  const ox = sx(0), oy = sy(0);
  const xQ1 = sx(Q), yPb = sy(Pb), yPs = sy(Ps);
  const g = svg.append('g');

  // Исходное равновесие E₀ рисует общий слой-призрак drawGhost()
  // (галочка «было → стало»), поэтому здесь его не дублируем.

  // Проекции к осям для цен покупателя/продавца и количества.
  const dash = (x1, y1, x2, y2) => g.append('line')
    .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(xQ1, yPb, xQ1, oy);
  dash(xQ1, yPb, ox, yPb);
  dash(xQ1, yPs, ox, yPs);

  axisValueY(g, ox, yPb, fmt(Pb), 'b');
  axisValueY(g, ox, yPs, fmt(Ps), 's');
  axisValueX(g, xQ1, oy, fmt(Q), '1');

  // Точки покупателя (синяя) и продавца (красная).
  g.append('circle').attr('cx', xQ1).attr('cy', yPb).attr('r', 4)
    .attr('fill', COL.D).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  g.append('circle').attr('cx', xQ1).attr('cy', yPs).attr('r', 4)
    .attr('fill', COL.S).attr('stroke', COL.halo).attr('stroke-width', 1.5);

  // Клин налога: вертикальный отрезок между Ps и Pb.
  g.append('line').attr('x1', xQ1).attr('y1', yPs).attr('x2', xQ1).attr('y2', yPb)
    .attr('stroke', COL.ink).attr('stroke-width', 2.5).style('pointer-events', 'none');
  const letter = (STATE.intervType === 'subsidy') ? 's=' : 't=';
  const yMid = (yPb + yPs) / 2;
  haloText(g, xQ1 + 16, yMid, letter + fmt(STATE.tax), 'start', 'middle');
  // Широкая прозрачная зона захвата поверх клина — удобно хватать мышью.
  const hitRect = g.append('rect')
    .attr('x', xQ1 - 13).attr('y', Math.min(yPb, yPs))
    .attr('width', 26).attr('height', Math.abs(yPb - yPs))
    .attr('fill', 'transparent')
    .style('cursor', 'grab');
  attachTaxDrag(hitRect);
  // Видимая ручка в середине клина (сигнал «меня можно тянуть»).
  g.append('circle').attr('cx', xQ1).attr('cy', yMid).attr('r', 7)
    .attr('fill', COL.reg).attr('stroke', COL.halo).attr('stroke-width', 2)
    .style('pointer-events', 'none');
}

// Перетаскивание клина: вертикальное движение меняет ставку налога/субсидии.
// Используем абсолютное смещение от начала перетаскивания — устойчивее дельт.
function attachTaxDrag(sel) {
  let startY, startTax;
  sel.call(d3.drag()
    .container(() => svg.node())
    .on('start', (event) => {
      startY = event.y;
      startTax = STATE.tax;
      document.body.style.cursor = 'grabbing';
    })
    .on('drag', (event) => {
      // sy.invert: меньший пиксель = выше на экране = бо́льшая цена.
      // Тянем вверх (y уменьшается) → dP > 0 → ставка растёт.
      const dP = sy.invert(event.y) - sy.invert(startY);
      setTax(startTax + dP);
    })
    .on('end', () => {
      document.body.style.cursor = '';
    }));
}

// Установить ставку налога (единый путь для ползунка, числового поля и клина).
function setTax(t) {
  const slider = document.getElementById('tax-slider');
  const maxT = slider ? (parseFloat(slider.max) || CONFIG.Pmax) : CONFIG.Pmax;
  t = Math.max(0, Math.min(t, maxT));
  STATE.tax = t;
  if (slider) slider.value = t;                        // ползунок (step=1, целые)
  const lbl = document.getElementById('tax-val');
  if (lbl) lbl.textContent = fmt(t);
  const inp = document.getElementById('tax-input');
  if (inp) inp.value = fmtInput(t);                         // числовое поле (точное)
  redrawAll();
}

// Переключение типа вмешательства: налог <-> субсидия.
function setType(type) {
  STATE.intervType = type;
  const map = { tax: 'seg-tax', subsidy: 'seg-sub', ceiling: 'seg-ceil', floor: 'seg-floor' };
  Object.values(map).forEach(id => {
    const b = document.getElementById(id); if (b) b.classList.remove('active');
  });
  const ab = document.getElementById(map[type]); if (ab) ab.classList.add('active');

  const isTax = (type === 'tax' || type === 'subsidy');
  // Показ нужного поля ввода и подсказки.
  const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? '' : 'none'; };
  show('tax-field', isTax);   show('tax-hint', isTax);
  show('pc-field', !isTax);   show('pc-hint', !isTax);
  // Выбор плательщика — только для налога и только в конкуренции (в монополии налог
  // на производство; эквивалентность «кто платит» там не задаётся стороной).
  show('taxside-row', type === 'tax' && STATE.market !== 'monopoly');
  // Вид ставки (Фаза 2в) — только для потоварного вмешательства и только в конкуренции:
  // в монополии налог входит в MC (monopolyTax), адвалорная форма туда не переносится.
  show('taxkind-row', isTax && STATE.market !== 'monopoly');

  if (isTax) {
    applyTaxRateBounds();   // подпись ставки (t / s / τ,%) и пределы ползунка
  } else {
    const pl = document.getElementById('pc-letter');
    if (pl) pl.textContent = (type === 'ceiling') ? 'Pc' : 'Pf';
    // Стартовая цена линии: в монополии — монопольная Pm, иначе равновесная P*
    // (линия появляется сразу, пока не связывает).
    if (STATE.pReg <= 0) {
      const base = (STATE.market === 'monopoly' && STATE.mono) ? STATE.mono.Pm : (STATE.eq ? STATE.eq.P : 0);
      if (base > 0) setPRegFields(Math.round(base));
    }
  }
  if (typeof updatePult === 'function') updatePult();   // сменился тип/набор регуляторов пульта
  redrawAll();
}

/* --- Фаза 2в. Вид потоварной ставки: специфический ↔ адвалорный --------- */

// Пределы ползунка ставки и подпись её буквы. Специфический — рубли за единицу
// (потолок = масштаб цены Pmax); адвалорный — проценты (потолок 200 %).
function applyTaxRateBounds() {
  const adv = (STATE.taxKind === 'advalorem');
  const max = adv ? 200 : CONFIG.Pmax;
  ['tax-slider', 'tax-input'].forEach(id => { const e = document.getElementById(id); if (e) e.max = max; });
  const rl = document.getElementById('rate-letter');
  if (rl) rl.textContent = adv ? 'τ, %' : ((STATE.intervType === 'subsidy') ? 's' : 't');
  const h = document.getElementById('tax-hint');
  if (h) h.innerHTML = adv
    ? 'Адвалорная ставка берётся долей от цены, поэтому предложение не сдвигается, а <b>поворачивается</b>: ' +
      'S<sub>после</sub>(Q)&nbsp;=&nbsp;(1+τ)·S(Q) при налоге. Вертикальный разрыв между S и S<sub>после</sub> ' +
      'растёт вместе с Q (в отличие от постоянного клина при специфической ставке).'
    : 'Потоварное вмешательство на стороне производителя: кривая S <b>сдвигается</b> ' +
      'на величину ставки: налог вверх, субсидия вниз. Клин между ценами покупателя ' +
      'и продавца можно тянуть мышью.';
}

// Переключатель вида ставки. Значение переносится и зажимается новыми пределами.
function setTaxKind(kind) {
  STATE.taxKind = (kind === 'advalorem') ? 'advalorem' : 'unit';
  const u = document.getElementById('tk-unit'), a = document.getElementById('tk-adv');
  if (u) u.classList.toggle('active', STATE.taxKind === 'unit');
  if (a) a.classList.toggle('active', STATE.taxKind === 'advalorem');
  applyTaxRateBounds();
  setTax(STATE.tax);   // пере-зажать значение под новые пределы + перерисовать
}

// Табло налога: таблица «До / После / Δ» и распределение бремени.
function updateTaxPanel() {
  const box = document.getElementById('info-tax');
  if (!box) return;
  /* ⚠️ П12. БЛОК ГОВОРИТ ТОЛЬКО ТАМ, ГДЕ ЕГО ИНСТРУМЕНТ ЕСТЬ.
     Сюжет объявляет недоступные ему органы управления сам (SCENE_ROUTE.lock →
     класс .scoped-off). «Спрос и предложение» и «Стандартная монополия»
     запирают весь блок вмешательства — и всё равно показывали подсказку
     «двигайте ползунок, чтобы ввести налог» про ползунок, которого на экране
     нет. Спрашиваем ту же разметку, что и прячет: второго списка сцен
     с налогом не заводим, он бы разъехался с маршрутами. */
  const sec = document.getElementById(L_INTERV);
  if (sec && sec.classList.contains('scoped-off')) { box.innerHTML = ''; return; }
  if (!STATE.D || !STATE.S) {
    box.innerHTML = '<div class="muted">Сначала отметьте кривые D и S.</div>'; return;
  }
  if (!STATE.eq) { box.innerHTML = ''; return; }   // об отсутствии равновесия говорит один блок, см. П7
  const isSub = (STATE.intervType === 'subsidy');
  if (!STATE.taxActive) {
    box.innerHTML = `<div class="muted">Двигайте ползунок или тяните клин на графике, чтобы ввести ${isSub ? 'субсидию' : 'налог'}.</div>`;
    return;
  }
  const e0 = STATE.eq, te = STATE.taxEq;
  const rows = [
    ['Q', e0.Q, te.Q],
    ['P покупателя', e0.P, te.Pb],
    ['P продавца', e0.P, te.Ps],
    ['CS', STATE.cs, STATE.csTax],
    ['PS', STATE.ps, STATE.psTax],
    [isSub ? 'Бюджет (расход)' : 'Бюджет (сбор)', 0, STATE.budget],
    ['DWL', 0, STATE.dwl],
  ];
  const adv = (STATE.taxKind === 'advalorem');
  let html = `<div class="stat"><span>${adv ? 'Ставка τ (адвалорная)' : (isSub ? 'Субсидия s' : 'Налог t')}</span>` +
             `<b>${fmt(STATE.tax)}${adv ? ' %' : ''}</b></div>`;
  html += '<table class="tx-table"><tr><th></th><th>До</th><th>После</th><th>Δ</th></tr>';
  rows.forEach(([k, a, b]) => {
    // Δ считается из ОКРУГЛЁННЫХ соседей: иначе столбец не сходится с теми
    // двумя числами, которые человек видит слева от него (п. 1).
    const ds = fmtDiff(b, a);
    html += `<tr><td>${k}</td><td>${fmt(a)}</td><td>${fmt(b)}</td><td>${ds}</td></tr>`;
  });
  html += '</table>';
  const lbl = isSub ? 'Выигрыш' : 'Бремя';
  html += `<div class="stat" style="margin-top:6px;"><span>${lbl} покупателя</span><b>${fmt(STATE.incBuyer)}</b></div>`;
  html += `<div class="stat"><span>${lbl} продавца</span><b>${fmt(STATE.incSeller)}</b></div>`;
  // Вывод об эквивалентности (только для налога): кто платит — не влияет на итог.
  if (adv) {
    const k = 1 + STATE.tax / 100;
    html += `<div class="hint" style="margin-top:6px;">Адвалорная ставка: ` +
      (isSub ? `продавец получает в (1+τ)=${fmt(k)} раза больше покупателя: Ps = Pb·(1+τ) = ${fmt(te.Ps)}.`
             : `покупатель платит в (1+τ)=${fmt(k)} раза больше продавца: Ps = Pb/(1+τ) = ${fmt(te.Ps)}.`) +
      ` Деньги = (Pb − Ps)·Q = ${fmt(STATE.tx)}.</div>`;
  }
  if (!isSub) html += `<div class="hint" style="margin-top:6px;">Результат не зависит от того, кто формально платит налог: ` +
    `объём Q, цены покупателя/продавца и распределение бремени одинаковы при налоге на продавца и на покупателя.</div>`;
  box.innerHTML = html;
}

// Переключение стороны налога (продавец / покупатель). На числа не влияет —
// меняется только визуально сдвигаемая кривая (Задача 1).
function setTaxSide(side) {
  STATE.taxSide = side;
  const sel = document.getElementById('tsb-seller'), buy = document.getElementById('tsb-buyer');
  if (sel) sel.classList.toggle('active', side === 'seller');
  if (buy) buy.classList.toggle('active', side === 'buyer');
  redrawAll();
}

/* ---------------------------------------------------------------------
   БЛОК 8а-2. ЭЛАСТИЧНОСТЬ СПРОСА вдоль кривой (Задача 2).
   Перетаскиваемая точка на D + живой |Ed|, зоны эластичного/неэластичного
   спроса (раздел в единичной точке, где MR=0 и выручка TR максимальна).
   --------------------------------------------------------------------- */

// Бледные заливки зон: эластичный (левее единичной точки) и неэластичный (правее).
function drawElasticityZones() {
  const e = STATE.elast; if (!e || !e.unit) return;
  const D = STATE.D;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const area = d3.area().x(d => sx(d)).y0(sy(0)).y1(d => sy(evalCurve(D, d)));
  g.append('path').datum(samp(0, e.unit.Q)).attr('d', area).attr('fill', COL.tax).attr('opacity', 0.10);          // эластичный
  g.append('path').datum(samp(e.unit.Q, e.qDmax)).attr('d', area).attr('fill', COL.reg).attr('opacity', 0.10);    // неэластичный
  // Подписи зон у оси Q.
  const oy = sy(0);
  const elText = (q, txt, color) => g.append('text').attr('x', sx(q)).attr('y', oy - 8).attr('text-anchor', 'middle')
    .attr('font-size', FS.small).attr('font-weight', 600).attr('fill', color).attr('opacity', 0.8)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(txt);
  elText(e.unit.Q * 0.5, 'эластичный', COL.tax);
  elText((e.unit.Q + e.qDmax) / 2, 'неэластичный', COL.reg);
}

// Единичная точка (MR=0) + перетаскиваемая точка с проекциями и подписью |Ed|.
function drawElasticityPoint() {
  const e = STATE.elast; if (!e || isNaN(e.p)) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  // Единичная точка эластичности.
  if (e.unit) {
    const [ux, uy] = toPx(e.unit.Q, e.unit.P);
    g.append('line').attr('x1', ux).attr('y1', uy).attr('x2', ux).attr('y2', oy)
      .attr('stroke', COL.MR).attr('stroke-width', 1).attr('stroke-dasharray', '3 3');
    g.append('circle').attr('cx', ux).attr('cy', uy).attr('r', 4).attr('fill', COL.MR).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    g.append('text').attr('x', ux + 7).attr('y', uy - 7).attr('font-size', FS.small).attr('font-weight', 600).attr('fill', COL.MR)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('|Ed|=1 · MR=0 · TR макс');
  }
  // Перетаскиваемая точка вдоль спроса.
  const [px, py] = toPx(e.q, e.p);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(px, py, px, oy); dash(px, py, ox, py);
  axisValueX(g, px, oy, fmt(e.q), '');
  axisValueY(g, ox, py, fmt(e.p), '');
  g.append('text').attr('x', px + 9).attr('y', py - 9).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.ink)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('|Ed|=' + fmt(e.absEd));
  const hit = g.append('circle').attr('cx', px).attr('cy', py).attr('r', 13).attr('fill', 'transparent').style('cursor', 'grab');
  attachElastDrag(hit);
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 5.5)
    .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

// Перетаскивание точки эластичности вдоль спроса (по Q; P берётся с кривой; зажим в recompute).
function attachElastDrag(sel) {
  sel.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => { STATE.elastQ = toData(event.x, event.y)[0]; redrawAll(); })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Точка эластичности на кривой ПРЕДЛОЖЕНИЯ (Фаза 2а) — зеркало точки на спросе.
function drawElasticityPointS() {
  const e = STATE.elastS; if (!e || isNaN(e.p)) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  const [px, py] = toPx(e.q, e.p);
  const dash = (x1, y1, x2, y2) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  dash(px, py, px, oy); dash(px, py, ox, py);
  g.append('text').attr('x', px + 9).attr('y', py + 15).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.S)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('|Es|=' + fmt(e.absEs));
  const hit = g.append('circle').attr('cx', px).attr('cy', py).attr('r', 13).attr('fill', 'transparent').style('cursor', 'grab');
  attachElastDragS(hit);
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 5.5)
    .attr('fill', COL.S).attr('stroke', COL.halo).attr('stroke-width', 2).style('pointer-events', 'none');
}

function attachElastDragS(sel) {
  sel.call(d3.drag().container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => { STATE.elastQS = toData(event.x, event.y)[0]; redrawAll(); })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Табло эластичности: точка, |Ed|, зона, единичная точка и максимальная выручка.
function updateElasticityPanel() {
  const box = document.getElementById('info-elast'); if (!box) return;
  if (!STATE.D) { box.innerHTML = '<div class="muted">Отметьте кривую спроса (роль D).</div>'; return; }
  const e = STATE.elast;
  if (!e || isNaN(e.Ed)) { box.innerHTML = '<div class="warn">Эластичность не определена в этой точке.</div>'; return; }
  const zone = e.absEd > 1.0001 ? 'эластичный, $|E_d| > 1$' : (e.absEd < 0.9999 ? 'неэластичный, $|E_d| < 1$' : 'единичная, $|E_d| = 1$');
  let html = '';
  /* Пара чисел — тоже список, и запятая в нём спорит с десятичным знаком:
     «50,50» читается как одно число с копейками. Разделитель тот же, что у
     остальных списков, — точка с запятой. */
  html += `<div class="stat"><span>Точка спроса (Q, P)</span><b>${fmt(e.q)}; ${fmt(e.p)}</b></div>`;
  html += `<div class="stat"><span>$|E_d|$</span><b>${fmt(e.absEd)}</b></div>`;
  html += `<div class="stat"><span>Зона спроса</span><b>${zone}</b></div>`;
  html += `<div class="stat"><span>Выручка TR = P·Q</span><b>${fmt(e.TR)}</b></div>`;
  // Связь эластичности с выручкой — главный вывод темы, поэтому словами (Фаза 2а).
  const trNote = e.absEd > 1.0001
    ? 'Спрос <b>эластичный</b>: снижение цены (рост Q) <b>увеличивает</b> выручку: объём растёт быстрее, чем падает цена.'
    : (e.absEd < 0.9999
      ? 'Спрос <b>неэластичный</b>: снижение цены (рост Q) <b>уменьшает</b> выручку: объём растёт медленнее, чем падает цена.'
      : 'Единичная эластичность: выручка в максимуме, малое изменение цены её почти не меняет.');
  html += `<div class="hint" style="margin-top:4px;">${trNote}</div>`;
  if (e.unit) {
    html += `<div class="stat" style="margin-top:4px;"><span>Единичная точка</span><b>Q = ${fmt(e.unit.Q)}, P = ${fmt(e.unit.P)}</b></div>`;
    html += `<div class="stat"><span>Макс выручка TR</span><b>${fmt(e.unit.TR)}</b></div>`;
  }
  // Эластичность предложения (Фаза 2а) — вторая точка, своя строка в табло.
  const s = STATE.elastS;
  if (s && !isNaN(s.Es)) {
    const zs = s.absEs > 1.0001 ? 'эластичное, $|E_s| > 1$' : (s.absEs < 0.9999 ? 'неэластичное, $|E_s| < 1$' : 'единичная, $|E_s| = 1$');
    html += '<div style="margin-top:8px;padding-top:8px;border-top:.5px solid var(--border);"></div>';
    html += `<div class="stat"><span>Точка предложения (Q, P)</span><b>${fmt(s.q)}; ${fmt(s.p)}</b></div>`;
    html += `<div class="stat"><span>$|E_s|$</span><b>${fmt(s.absEs)}</b></div>`;
    html += `<div class="stat"><span>Зона предложения</span><b>${zs}</b></div>`;
    /* Б28 · Б29. Правило про перехват верно только для ПРЯМОЙ, и раньше оно
       было записано наоборот. Вывод: у предложения P = b + aQ обратная запись
       Q = (P − b)/a, поэтому Es = (dQ/dP)·(P/Q) = P/(P − b). При b > 0 (прямая
       выходит с оси цен) дробь больше единицы, то есть предложение ЭЛАСТИЧНО;
       при b < 0 (прямая выходит с оси количеств) меньше единицы, то есть
       НЕЭЛАСТИЧНО. Числами: P = 10 + Q в точке Q = 10 даёт Es = 20/10 = 2.
       Для кривого предложения про перехват говорить нечего, поэтому там стоит
       то, что верно всегда. */
    const lin = STATE.S && STATE.S.linear;
    html += '<div class="hint">' + (lin
      ? 'Прямое предложение через начало координат даёт |Es|&nbsp;=&nbsp;1 в любой точке. ' +
        'Если прямая выходит с оси цен (положительный перехват цены), предложение <b>эластично</b>: ' +
        'Es&nbsp;=&nbsp;P/(P&nbsp;−&nbsp;b), а при b&nbsp;&gt;&nbsp;0 эта дробь больше единицы. ' +
        'Если прямая выходит с оси количеств (перехват цены отрицателен), предложение <b>неэластично</b>.'
      : 'Предложение задано не прямой, поэтому эластичность меняется от точки к точке: ' +
        'приведённое значение относится к выбранной точке, а не ко всей кривой.') + '</div>';
  } else if (STATE.showElastS && !STATE.S) {
    html += '<div class="hint" style="margin-top:6px;">Для |Es| отметьте кривую предложения (роль S).</div>';
  }
  box.innerHTML = html;
}

/* ---------------------------------------------------------------------
   БЛОК 8а-3. РАЗЛОЖЕНИЕ ДВОЙНЫХ СДВИГОВ (Задача 3).
   Сдвигаем спрос на ΔD и предложение на ΔS, считаем четыре равновесия
   (E0, только спрос, только предложение, оба) и раскладываем ΔQ и ΔP на
   вклад спроса, предложения и итог.
   --------------------------------------------------------------------- */

// Одна помеченная точка равновесия с проекциями к осям.
function shiftMark(g, pt, label, color) {
  const ox = sx(0), oy = sy(0), [px, py] = toPx(pt.Q, pt.P);
  g.append('line').attr('x1', px).attr('y1', py).attr('x2', px).attr('y2', oy)
    .attr('stroke', color).attr('stroke-width', 1).attr('stroke-dasharray', '3 3').attr('opacity', 0.55);
  g.append('line').attr('x1', px).attr('y1', py).attr('x2', ox).attr('y2', py)
    .attr('stroke', color).attr('stroke-width', 1).attr('stroke-dasharray', '3 3').attr('opacity', 0.55);
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5).attr('fill', color).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  g.append('text').attr('x', px + 8).attr('y', py - 8).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', color)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text(label);
}

// Отрисовка сценария сдвигов: исходные кривые + пунктирные сдвинутые + точки E_d/E_s/E1.
function drawShiftScenario() {
  drawGhost();        // E₀ как бледный призрак (активируется shiftActive)
  drawCurves();       // исходные D и S
  const r = STATE.shiftRes;
  if (!r) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const shifted = (base, sh, color) => {
    if (sh === 0) return;
    const pts = []; for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = evalCurve(base, q); pts.push(isNaN(v) ? null : [q, v + sh]); }
    g.append('path').datum(pts).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
  };
  shifted(STATE.D, r.dD, STATE.D.color);
  shifted(STATE.S, r.dS, STATE.S.color);
  // Промежуточные равновесия и итог. E_d/E_s — разными цветами, E₁ — тёмный (итог).
  const gp = svg.append('g');
  if (r.dD !== 0) shiftMark(gp, r.Ed, 'E_d', COL.D);
  if (r.dS !== 0) shiftMark(gp, r.Es, 'E_s', COL.tax);
  shiftMark(gp, r.E1, 'E₁', COL.ink);
}

// Табло сдвигов: четыре равновесия и таблица разложения ΔQ*/ΔP*.
function updateShiftPanel() {
  const box = document.getElementById('info-shift'); if (!box) return;
  if (!STATE.D || !STATE.S) { box.innerHTML = '<div class="muted">Отметьте кривые D и S.</div>'; return; }
  if (!STATE.eq) { box.innerHTML = '<div class="warn">Исходное равновесие не найдено.</div>'; return; }
  const r = STATE.shiftRes;
  if (!r) { box.innerHTML = '<div class="warn">Равновесие после сдвигов не найдено в первой четверти.</div>'; return; }
  const sg = (v) => (v > 0 ? '+' : '') + fmt(v);
  let html = '';
  html += `<div class="stat"><span>$E_0$ (исходное)</span><b>${fmt(r.E0.Q)}, ${fmt(r.E0.P)}</b></div>`;
  html += `<div class="stat"><span>$E_d$ (только спрос)</span><b>${fmt(r.Ed.Q)}, ${fmt(r.Ed.P)}</b></div>`;
  html += `<div class="stat"><span>$E_s$ (только предложение)</span><b>${fmt(r.Es.Q)}, ${fmt(r.Es.P)}</b></div>`;
  html += `<div class="stat"><span>$E_1$ (оба сдвига)</span><b>${fmt(r.E1.Q)}, ${fmt(r.E1.P)}</b></div>`;
  html += '<table class="tx-table" style="margin-top:6px;"><tr><th></th><th>спрос</th><th>предл.</th><th>итог</th></tr>';
  html += `<tr><td>ΔQ*</td><td>${sg(r.dQ.demand)}</td><td>${sg(r.dQ.supply)}</td><td>${sg(r.dQ.total)}</td></tr>`;
  html += `<tr><td>ΔP*</td><td>${sg(r.dP.demand)}</td><td>${sg(r.dP.supply)}</td><td>${sg(r.dP.total)}</td></tr>`;
  html += '</table>';
  box.innerHTML = html;
}

// Единый путь смены сдвига (ползунок / число): which = 'D' | 'S'.
function setShift(which, v) {
  v = isNaN(v) ? 0 : v;
  const ids = which === 'D'
    ? ['shiftD-slider', 'shiftD-input', 'shiftD-val'] : ['shiftS-slider', 'shiftS-input', 'shiftS-val'];
  if (which === 'D') STATE.shiftD = v; else STATE.shiftS = v;
  const sl = document.getElementById(ids[0]); if (sl) sl.value = v;
  const inp = document.getElementById(ids[1]); if (inp) inp.value = v;
  const lbl = document.getElementById(ids[2]); if (lbl) lbl.textContent = fmt(v);
  redrawAll();
}

/* ---------------------------------------------------------------------
   БЛОК 8а-4. ВНЕШНИЙ ЭФФЕКТ и НАЛОГ ПИГУ (Задача 4).
   Отрицательный внешний эффект производства: MSC = MPC + внешние пред. издержки.
   Рынок выпускает Qрын (D = MPC), оптимум — Qопт (D = MSC). Налог Пигу поднимает
   MPC до MSC и приводит рынок в Qопт. Всё численно (любые кривые).
   --------------------------------------------------------------------- */

// Заливка DWL — клин между общественной и противоположной частной кривой
// на отрезке между рыночным и оптимальным выпуском (Фаза 2б: оба знака).
function drawExtAreas(e) {
  if (!e || e.Qopt == null) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const lo = Math.min(e.Qopt, e.Qmkt), hi = Math.max(e.Qopt, e.Qmkt);
  if (hi <= lo) return;
  const samp = []; for (let i = 0; i <= 100; i++) samp.push(lo + (hi - lo) * i / 100);
  const aD = d3.area().x(d => sx(d)).y0(d => sy(e.other(d))).y1(d => sy(e.social(d)));
  g.append('path').datum(samp).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери от внешнего эффекта (DWL)');
}

// Общественная кривая MSC (эффект на издержках) либо MSB (эффект на выгоде)
// + (если применён) частная кривая после корректирующего налога / субсидии.
function drawExtCurves(e) {
  if (!e) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const pts = (f) => { const o = []; for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = f(q); o.push(isNaN(v) ? null : [q, v]); } return o; };
  g.append('path').datum(pts(e.social)).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2.5).attr('d', line);
  // Ярлык общественной кривой (Фаза 3): у правого края или у ближайшего
  // видимого места — раньше при большом внешнем эффекте он пропадал.
  labelCurve(g, e.social, e.pos ? 'MSB' : 'MSC', COL.reg, { from: 0.9 });
  // Корректирующий инструмент: налог поднимает предложение, субсидия — опускает (зелёный пунктир).
  if (e.applyPigou && e.corrective != null) {
    g.append('path').datum(pts(q => evalCurve(STATE.S, q) + (e.pos ? -e.corrective : e.corrective)))
      .attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2).attr('stroke-dasharray', '6 4').attr('d', line);
  }
}

// Точки Qрын и Qопт (+ налог Пигу — новое равновесие в Qопт), проекции и подписи.
function drawExtPoints(e) {
  if (!e) return;
  const ox = sx(0), oy = sy(0), g = svg.append('g');
  const dash = (x1, y1, x2, y2, c) => g.append('line').attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
    .attr('stroke', c || COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
  // Рыночный выпуск (Qрын, Pрын) — на пересечении D и MPC.
  const [pxm, pym] = toPx(e.Qmkt, e.Pmkt);
  dash(pxm, pym, pxm, oy); dash(pxm, pym, ox, pym);
  g.append('circle').attr('cx', pxm).attr('cy', pym).attr('r', 4.5).attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  g.append('text').attr('x', pxm + 8).attr('y', pym - 8).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.ink)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Qрын');
  axisValueX(g, pxm, oy, fmt(e.Qmkt), 'рын');
  /* Пунктир шёл и к оси цены, а числа там не было: линия упиралась в пустоту.
     Различитель обязателен — на оси цены встают ДВЕ разные величины,
     рыночная цена и цена общественного оптимума. */
  axisValueY(g, ox, pym, fmt(e.Pmkt), 'рын');
  // Общественный оптимум (Qопт, Pопт) — на пересечении D и MSC.
  if (e.Qopt != null) {
    const [pxo, pyo] = toPx(e.Qopt, e.Popt);
    dash(pxo, pyo, pxo, oy, COL.tax); dash(pxo, pyo, ox, pyo, COL.tax);
    g.append('circle').attr('cx', pxo).attr('cy', pyo).attr('r', 4.5).attr('fill', COL.tax).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    g.append('text').attr('x', pxo + 8).attr('y', pyo - 8).attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.tax)
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('Qопт');
    axisValueX(g, pxo, oy, fmt(e.Qopt), 'опт');
    axisValueY(g, ox, pyo, fmt(e.Popt), 'опт');
    // С налогом Пигу новое равновесие совпадает с Qопт — отмечаем кольцом.
    if (e.applyPigou && e.pigouEq) {
      const [pxp, pyp] = toPx(e.pigouEq.Q, e.pigouEq.P);
      g.append('circle').attr('cx', pxp).attr('cy', pyp).attr('r', 7).attr('fill', 'none').attr('stroke', COL.tax).attr('stroke-width', 2);
    }
  }
}

// Полная отрисовка сценария внешнего эффекта.
function drawExtScenario() {
  const e = STATE.ext;
  drawExtAreas(e);
  drawCurves();      // D (MSB) и S (MPC)
  drawExtCurves(e);  // MSC (+ MPC+налог при Пигу)
  drawExtPoints(e);
}

// Табло внешнего эффекта: Qрын/Qопт, DWL, налог Пигу, новое равновесие.
function updateExtPanel() {
  const box = document.getElementById('info-ext'); if (!box) return;
  if (!STATE.D || !STATE.S) { box.innerHTML = '<div class="muted">Отметьте D (выгода MSB) и S (частные издержки MPC).</div>'; return; }
  if (!STATE.eq) { box.innerHTML = '<div class="warn">Рыночное равновесие не найдено.</div>'; return; }
  const e = STATE.ext;
  if (!e) { box.innerHTML = '<div class="warn">Введите величину внешнего эффекта.</div>'; return; }
  const mktEq = e.pos ? 'MPB = S' : 'D = MPC', optEq = e.pos ? 'MSB = S' : 'D = MSC';
  const tool = e.pos ? 'Корректирующая субсидия' : 'Корректирующий налог (Пигу)';
  let html = '';
  html += `<div class="stat"><span>Qрын (${mktEq})</span><b>Q = ${fmt(e.Qmkt)}, P = ${fmt(e.Pmkt)}</b></div>`;
  if (e.Qopt != null) {
    html += `<div class="stat"><span>Qопт (${optEq})</span><b>Q = ${fmt(e.Qopt)}, P = ${fmt(e.Popt)}</b></div>`;
    html += `<div class="stat"><span>$DWL$ (потери)</span><b>${fmt(e.dwl)}</b></div>`;
    html += `<div class="stat"><span>${tool}</span><b>${fmt(e.corrective)}</b></div>`;
    const gap = e.Qopt - e.Qmkt;
    html += `<div class="hint" style="margin-top:4px;">${gap < -1e-6
      ? 'Рынок выпускает <b>больше</b> общественного оптимума на ' + fmt(-gap) + ': <b>перепроизводство</b>, частные издержки ниже общественных.'
      : (gap > 1e-6
        ? 'Рынок выпускает <b>меньше</b> общественного оптимума на ' + fmt(gap) + ': <b>недопроизводство</b>, частная выгода ниже общественной.'
        : 'Рынок уже в общественном оптимуме: внешний эффект нулевой.')}</div>`;
    if (e.applyPigou && e.pigouEq) {
      html += `<div class="stat" style="margin-top:4px;"><span>Новое равновесие</span><b>Q = ${fmt(e.pigouEq.Q)}, P = ${fmt(e.pigouEq.P)}</b></div>`;
      html += `<div class="hint">${e.pos ? 'Субсидия опустила издержки' : 'Налог Пигу поднял издержки'}, рынок пришёл в Qопт, DWL устранён.</div>`;
    }
  } else {
    html += `<div class="warn">Оптимум ${optEq} не найден в первой четверти.</div>`;
  }
  box.innerHTML = html;
}

// Переключатель знака внешнего эффекта (Фаза 2б): меняет подписи полей и модель.
function setExtSign(sign) {
  STATE.extSign = (sign === 'pos') ? 'pos' : 'neg';
  const pos = (STATE.extSign === 'pos');
  const n = document.getElementById('ext-neg'), p = document.getElementById('ext-pos');
  if (n) n.classList.toggle('active', !pos);
  if (p) p.classList.toggle('active', pos);
  const lbl = document.getElementById('ext-label');
  if (lbl) lbl.textContent = pos ? 'Внешняя предельная выгода (число или f(Q))'
                                 : 'Внешние предельные издержки (число или f(Q))';
  const pl = document.getElementById('ext-pigou-label');
  if (pl) pl.textContent = pos ? 'Применить корректирующую субсидию' : 'Применить налог Пигу';
  const hn = document.getElementById('ext-hint-neg'), hp = document.getElementById('ext-hint-pos');
  if (hn) hn.style.display = pos ? 'none' : '';
  if (hp) hp.style.display = pos ? '' : 'none';
  redrawAll();
}

// Перекомпиляция внешних предельных издержек (вызывается при смене формулы / сценария).
function recompileExt() {
  const r = compileExt(STATE.extExpr);
  STATE.extCompiled = r.compiled;
  const errBox = document.getElementById('ext-error');
  if (errBox) { errBox.style.display = r.error ? 'block' : 'none'; errBox.textContent = r.error ? 'Не понял формулу: ' + r.error : ''; }
}

/* ---------------------------------------------------------------------
   БЛОК 8б. ЦЕНОВОЕ РЕГУЛИРОВАНИЕ — потолок и пол цены (Задача 1).
   Линия фиксированной цены тянется мышью; рынок не расчищается —
   возникает дефицит (потолок) или избыток (пол).
   --------------------------------------------------------------------- */

// Записать регулируемую цену в поля панели (без перерисовки).
function setPRegFields(p) {
  STATE.pReg = p;
  const slider = document.getElementById('pc-slider'); if (slider) slider.value = p;
  const lbl = document.getElementById('pc-val');       if (lbl) lbl.textContent = fmt(p);
  const inp = document.getElementById('pc-input');     if (inp) inp.value = fmtInput(p);
}

// Единый путь смены цены (ползунок, числовое поле, перетаскивание линии).
function setPReg(p) {
  const slider = document.getElementById('pc-slider');
  const maxP = slider ? (parseFloat(slider.max) || CONFIG.Pmax) : CONFIG.Pmax;
  p = Math.max(0, Math.min(p, maxP));
  setPRegFields(p);
  redrawAll();
}

// Заливки CS / PS / DWL при связывающем регулировании (до Q_trade).
function drawPcAreas() {
  if (!STATE.pcActive) return;
  const { Preg, Qtrade } = STATE.pc;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const s1 = samp(0, Qtrade);
  if (STATE.showCS) {   // CS — между ценой Preg (низ) и спросом (верх)
    const a = d3.area().x(d => sx(d)).y0(sy(Preg)).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  if (STATE.showPS) {   // PS — между предложением (низ) и ценой Preg (верх)
    const a = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(sy(Preg));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек продавца (PS)');
  }
  // DWL — площадь между D и S от Q_trade до Q* (потери от нерасчищенного рынка).
  const lo = Math.min(Qtrade, STATE.eq.Q), hi = Math.max(Qtrade, STATE.eq.Q);
  if (hi > lo) {
    const s2 = samp(lo, hi);
    const aD = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери общества (DWL)');
  }
}

// Перетаскиваемая линия цены + проекции Qs/Qd и зона дефицита/избытка.
function drawPriceControl() {
  if (!STATE.pcMode) return;
  const pc = STATE.pc;
  if (!pc) { drawEquilibrium(); return; }   // цена не задана — обычное равновесие
  const Preg = pc.Preg;
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax);
  const yReg = sy(Preg);
  const g = svg.append('g');
  const lineColor = pc.isCeiling ? COL.reg : COL.MR;

  // Горизонтальная линия фиксированной цены через весь график.
  g.append('line').attr('x1', ox).attr('y1', yReg).attr('x2', xMax).attr('y2', yReg)
    .attr('stroke', lineColor).attr('stroke-width', 2.5).style('pointer-events', 'none');
  // Потолок и пол — разные величины на одной оси: имя снимается, индекс остаётся.
  axisValueY(g, ox, yReg, Preg, pc.isCeiling ? 'c' : 'f');

  if (STATE.pcActive) {
    const { Qs, Qd, Qtrade, gap, isCeiling } = pc;
    const xQs = sx(Qs), xQd = sx(Qd), xQt = sx(Qtrade);
    const dash = (x1, y1, x2, y2) => g.append('line')
      .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
      .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
    dash(xQs, yReg, xQs, oy);   // проекция объёма предложения на ось Q
    dash(xQd, yReg, xQd, oy);   // проекция объёма спроса на ось Q
    axisValueX(g, xQs, oy, fmt(Qs), 's');
    axisValueX(g, xQd, oy, fmt(Qd), 'd');
    // Зона дефицита/избытка — цветная полоса на оси Q между Qs и Qd.
    const xLo = Math.min(xQs, xQd), xHi = Math.max(xQs, xQd);
    g.append('line').attr('x1', xLo).attr('y1', oy).attr('x2', xHi).attr('y2', oy)
      .attr('stroke', isCeiling ? COL.bad : COL.MR).attr('stroke-width', 5).attr('opacity', 0.5);
    haloText(g, (xLo + xHi) / 2, oy + 24, (isCeiling ? 'Дефицит' : 'Избыток') + ' = ' + fmt(gap), 'middle', 'hanging');
    // Точка фактической торговли (короткая сторона рынка) на линии цены.
    g.append('circle').attr('cx', xQt).attr('cy', yReg).attr('r', 4)
      .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
  } else {
    drawEquilibrium();   // не связывает — рынок остаётся в равновесии
  }

  // Зона захвата (24px вокруг линии) + видимая ручка для перетаскивания.
  const hit = g.append('rect')
    .attr('x', ox).attr('y', yReg - 12).attr('width', xMax - ox).attr('height', 24)
    .attr('fill', 'transparent').style('cursor', 'grab');
  attachPcDrag(hit);
  g.append('circle').attr('cx', ox + (xMax - ox) * 0.5).attr('cy', yReg).attr('r', 7)
    .attr('fill', lineColor).attr('stroke', COL.halo).attr('stroke-width', 2)
    .style('pointer-events', 'none');
}

// Перетаскивание линии цены: вертикальное положение курсора = новая цена.
function attachPcDrag(sel) {
  sel.call(d3.drag()
    .container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => { setPReg(sy.invert(event.y)); })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Табло регулирования: таблица «До / После / Δ» и дефицит/избыток.
function updatePcPanel() {
  const box = document.getElementById('info-tax');
  if (!box) return;
  const isCeiling = (STATE.intervType === 'ceiling');
  if (!STATE.D || !STATE.S) { box.innerHTML = '<div class="muted">Сначала отметьте кривые D и S.</div>'; return; }
  if (!STATE.eq) { box.innerHTML = '<div class="warn">Равновесие не найдено.</div>'; return; }
  const pc = STATE.pc;
  if (!pc || STATE.pReg <= 0) {
    box.innerHTML = `<div class="muted">Двигайте ползунок или тяните линию цены, чтобы задать ${isCeiling ? 'потолок' : 'пол'} цены.</div>`;
    return;
  }
  if (!pc.binding) {
    box.innerHTML = `<div class="warn">${isCeiling ? 'Потолок' : 'Пол'} ${isCeiling ? 'выше' : 'ниже'} равновесия (P*=${fmt(STATE.eq.P)}), поэтому не действует. Рынок в равновесии.</div>`;
    return;
  }
  const rows = [
    ['Q (торговля)', STATE.eq.Q, pc.Qtrade],
    ['CS', STATE.cs, pc.cs],
    ['PS', STATE.ps, pc.ps],
    ['SW', STATE.sw, pc.sw],
    ['DWL', 0, pc.dwl],
  ];
  let html = `<div class="stat"><span>${isCeiling ? 'Потолок Pc' : 'Пол Pf'}</span><b>${fmt(pc.Preg)}</b></div>`;
  html += '<table class="tx-table"><tr><th></th><th>До</th><th>После</th><th>Δ</th></tr>';
  rows.forEach(([k, a, b]) => {
    // Δ считается из ОКРУГЛЁННЫХ соседей: иначе столбец не сходится с теми
    // двумя числами, которые человек видит слева от него (п. 1).
    const ds = fmtDiff(b, a);
    html += `<tr><td>${k}</td><td>${fmt(a)}</td><td>${fmt(b)}</td><td>${ds}</td></tr>`;
  });
  html += '</table>';
  html += `<div class="stat" style="margin-top:6px;"><span>${isCeiling ? 'Дефицит' : 'Избыток'}</span><b>${fmt(pc.gap)}</b></div>`;
  box.innerHTML = html;
}

/* ---------------------------------------------------------------------
   БЛОК 8в. «БЫЛО → СТАЛО» — бледный слой исходного состояния (Задача 2).
   При любом активном вмешательстве (налог / субсидия / потолок / пол)
   показывает, где было равновесие ДО него. Рисуется ПОД кривыми и
   точками; общий код для всех сценариев; включается галочкой.
   Сами кривые D и S не дублируем — базовые кривые и так на графике
   (для налога исходная S сплошная, сдвинутая — пунктир).
   --------------------------------------------------------------------- */
function drawGhost() {
  if (!STATE.showGhost) return;
  if (!(STATE.taxActive || STATE.pcActive || STATE.shiftActive) || !STATE.eq) return;
  const { Q, P } = STATE.eq;               // исходное равновесие E₀ (до вмешательства)
  const [px, py] = toPx(Q, P);
  const ox = sx(0), oy = sy(0);
  const g = svg.append('g').attr('class', 'ghost');
  // Бледные проекции исходного равновесия к осям.
  g.append('line').attr('x1', px).attr('y1', py).attr('x2', px).attr('y2', oy)
    .attr('stroke', COL.ghost).attr('stroke-width', 1).attr('stroke-dasharray', '3 3');
  g.append('line').attr('x1', px).attr('y1', py).attr('x2', ox).attr('y2', py)
    .attr('stroke', COL.ghost).attr('stroke-width', 1).attr('stroke-dasharray', '3 3');
  // Бледная полая точка E₀ и подпись.
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4)
    .attr('fill', COL.halo).attr('stroke', COL.ghost).attr('stroke-width', 1.5);
  g.append('text').attr('x', px + 7).attr('y', py - 6)
    .attr('font-size', FS.base).attr('font-weight', 600).attr('fill', COL.inkSoft)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5).text('E₀');
}

