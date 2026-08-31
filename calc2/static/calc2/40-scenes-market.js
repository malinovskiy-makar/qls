// Рынок: равновесие, области, налог, регулирование, внешние эффекты.
/* ---------------------------------------------------------------------
   БЛОК 5. РАВНОВЕСИЕ — численный поиск и отрисовка точки D = S.
   --------------------------------------------------------------------- */

// Найти кривую с заданной ролью ('demand' / 'supply'), либо null.
function curveByRole(role) { return STATE.curves.find(c => c.role === role) || null; }

// Пересчёт сценария БЕЗ рисования: складываем результаты в STATE,
// чтобы функции отрисовки и табло читали готовые числа.
function recompute() {
  /* Суммарные кривые пересобираются ДО чтения ролей: они и есть D и S этой
     сцены, и обязаны отвечать текущим формулам групп. Отдельного «нажмите
     построить» здесь нет — правка группы сразу меняет сумму. */
  sumRebuild();
  STATE.D = curveByRole('demand');
  STATE.S = curveByRole('supply');

  /* ⚠️ В СЦЕНЕ СЛОЖЕНИЯ РАВНОВЕСИЕ И ИЗЛИШКИ СЧИТАЮТСЯ РАЗ НА НАБОР ФОРМУЛ.

     Суммарная кривая живёт кусочной записью, и каждое её значение проходит
     через Math.js: замер 24.08 — 3,6 мкс на вызов, а вызовов на кадр около
     девяти тысяч. Отсюда и жалоба «график лагает при панорамировании»: тянешь
     мышь, и на каждое движение движок заново ищет равновесие по тысяче узлов
     и заново берёт четыре интеграла.

     Кэшировать это раньше было НЕЛЬЗЯ честно: и запись, и отрезок поиска
     зависели от границ кадра, так что после панорамы числа действительно
     могли поменяться. Теперь не зависят ни то, ни другое, и панорама изменить
     их не может в принципе — значит, и считать их заново не за чем. Ключ —
     подпись формул и отрезок поиска: сменилось что-то из этого, считаем. */
  const memoKey = sumSceneOn() ? sumAnalyticsKey() : null;
  const memo = (memoKey && memoKey === STATE._sumAnaKey) ? STATE._sumAnaVal : null;
  if (memo) {
    // Копию, а не ту же ссылку: STATE.eq дальше по коду читают и сравнивают,
    // и отдавать наружу внутренность кэша нельзя.
    STATE.eq = memo.eq ? { Q: memo.eq.Q, P: memo.eq.P } : null;
    STATE.cs = memo.cs; STATE.ps = memo.ps; STATE.sw = memo.sw;
    STATE.offEq = memo.offEq ? { Q: memo.offEq.Q, P: memo.offEq.P } : null;
  } else {
    STATE.eq = (STATE.D && STATE.S) ? findEquilibrium(STATE.D, STATE.S) : null;

    // Площади излишков (шаг 6) — численным интегрированием от 0 до Q*.
    STATE.cs = STATE.ps = STATE.sw = null;
    if (STATE.eq) {
      const { Q, P } = STATE.eq;
      /* По участкам, если кривая знает свои изломы (суммарная знает): метод
         трапеций точен на прямой только когда излом лежит в узле сетки. */
      STATE.cs = integrateBroken(q => quadPrice(STATE.D, q) - P, 0, Q, quadBreaks(STATE.D, Q));   // ∫ (D - P*) dQ
      STATE.ps = integrateBroken(q => P - quadPrice(STATE.S, q), 0, Q, quadBreaks(STATE.S, Q));   // ∫ (P* - S) dQ
      STATE.sw = STATE.cs + STATE.ps;
    }

    /* Равновесия в первой четверти нет — но кривые могли пересечься за её
       пределами, и об этом надо сказать (решение владельца «пересечение вне
       первой четверти»). Ищем только тогда: там, где рынок есть, эта точка
       не нужна и лишних четырёх тысяч вычислений за неё платить не за что. */
    STATE.offEq = (!STATE.eq && STATE.D && STATE.S)
      ? findOffQuadIntersection(STATE.D, STATE.S) : null;

    if (memoKey) {
      STATE._sumAnaKey = memoKey;
      STATE._sumAnaVal = { eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
                           cs: STATE.cs, ps: STATE.ps, sw: STATE.sw,
                           offEq: STATE.offEq ? { Q: STATE.offEq.Q, P: STATE.offEq.P } : null };
    }
  }

  // Вмешательство государства (шаг 7 — налог, шаг 8 — субсидия).
  // Налог сдвигает S вверх на t, субсидия — вниз на s. Дальше математика общая.
  STATE.taxActive = false;
  STATE.taxEq = null;
  /* ⚠️ ХВОСТЫ ПРОШЛОГО ВМЕШАТЕЛЬСТВА ГАСНУТ ЗДЕСЬ, А НЕ «КОГДА-НИБУДЬ».
     Гасились только два поля из десяти, и остальные восемь доживали до
     следующей сцены. Замер 25.08 на D = 100−P, S = 0,5·p−200 без равновесия:
     в состоянии лежали сбор 800 и DWL 100 — числа с ПРОШЛОГО набора кривых,
     а `taxAfterS` оставалась функцией, замкнутой на прежнюю ставку, и на
     вопрос «где обращается в ноль» отвечала 420 вместо 500. Панель их не
     показывала, поэтому и не замечали; но по ним считает выгрузка и по ним
     же меряет прибор. */
  STATE.taxAfterS = null;
  STATE.taxAfterD = null;
  STATE.taxCurveOn = false;
  STATE.taxNoBase = false;
  STATE.shift = 0;
  STATE.advTau = 0;
  STATE.tx = null;
  STATE.budget = null;
  STATE.dwl = null;
  STATE.csTax = null;
  STATE.psTax = null;
  STATE.incBuyer = null;
  STATE.incSeller = null;
  // В режиме монополии конкурентные сценарии вмешательства отключены.
  // Интервенции активны только в обычном сценарии (не при эластичности/сдвигах/внешнем эффекте).
  const compMarket = (STATE.market !== 'monopoly');
  const scenarioNone = (STATE.scenario === 'none');
  const isTaxType = compMarket && scenarioNone && (STATE.intervType === 'tax' || STATE.intervType === 'subsidy');
  /* ⚠️ РАВНОВЕСИЕ ЗДЕСЬ НЕ УСЛОВИЕ, А ОДНО ИЗ СЛАГАЕМЫХ ОТВЕТА.
     Раньше в этом условии стояло ещё и `STATE.eq`, и одно это слагаемое
     выключало вмешательство ЦЕЛИКОМ: у рынка без равновесия в первой
     четверти (D = 100−P, S = 0,5·p−200 — обычная олимпиадная ловушка) налог
     не двигал кривую вовсе, и человек видел неподвижный график.

     А сдвиг и поворот кривой предложения — операции над ФУНКЦИЕЙ. Ставка
     есть, кривая есть, значит есть и кривая после вмешательства; пересекается
     она со спросом или нет, к самой операции отношения не имеет.

     Разделяем три вещи, и каждая живёт по своему условию:
       • КРИВАЯ ПОСЛЕ — есть S и ставка (это условие, `STATE.taxCurveOn`);
       • ЧИСЛА ПО НОВОМУ РАВНОВЕСИЮ (Q₁, Pd, Ps, сбор, излишки после) —
         нашлось новое равновесие в первой четверти (`STATE.taxActive`);
       • ЧИСЛА ПО ДВУМ РАВНОВЕСИЯМ (DWL и все «было → стало») — вдобавок
         было и исходное. Не было — не считаем и говорим об этом словами
         (`STATE.taxNoBase`), а не подставляем ноль вместо «до».

     Отсюда же берётся и краевой случай, который прежде терялся совсем: без
     вмешательства кривые пересекаются вне четверти, а с ним — внутри
     (субсидия 450 на тех же кривых даёт Q = 50). Числа обязаны появиться. */
  if (isTaxType && STATE.tax > 0 && STATE.D && STATE.S) {
    const isSub = (STATE.intervType === 'subsidy');
    const pf = pctForm();                         // строка таблицы PCT_FORMS либо null
    const adv = !!pf;
    const tau = adv ? STATE.tax / 100 : 0;        // процентная ставка в долях (STATE.tax — проценты)
    const shift = isSub ? -STATE.tax : STATE.tax; // потоварная ставка со знаком
    /* Кривая предложения ПОСЛЕ вмешательства — единый источник и для чисел, и для
       отрисовки.
         • потоварное: параллельный СДВИГ S ± ставка (разрыв постоянен);
         • процентное: ПОВОРОТ S_после = factor·S, где factor берётся ОДНОЙ строкой
           таблицы PCT_FORMS. Вертикальный разрыв между S и S_после растёт вместе с Q.
       Цена продавца при повороте всегда Ps = Pd/factor, поэтому четыре соотношения
       цен из таблицы получаются сами, без четырёх веток здесь. */
    const factor = adv ? pf.factor(tau) : 1;
    // texExpr — запись той же кривой формулой, для выгрузки в LaTeX (А49).
    // Отдельное поле, а не expr: движок кривых поле expr понимает по-своему,
    // и подкладывать ему выражение в объект, у которого есть только fn, нельзя.
    /* ⚠️ ЗАПИСЬ УПРОЩАЕТСЯ, А НЕ ОСТАЁТСЯ ШАБЛОНОМ (приёмка владельца 31.08).
       Подстановка в шаблон давала человеку «(Q) + (-20)» и «(100 - Q) - (-20)»:
       пока запись не показывалась, это было неважно, а теперь она стоит в
       блоке «Итоговая функция». simplifyRecord упрощает ПОКУСОЧНО и сверяет
       результат с исходником численно — не сошлось, оставит исходник. */
    const sSrc = (STATE.S && STATE.S.expr) ? String(STATE.S.expr) : '';
    const sAfter = adv
      ? { fn: q => { const s = evalCurve(STATE.S, q); return isNaN(s) ? NaN : s * factor; },
          texExpr: sSrc ? simplifyRecord('(' + sSrc + ') * ' + factor) : '' }
      : { fn: q => evalCurve(STATE.S, q) + shift,
          texExpr: sSrc ? simplifyRecord('(' + sSrc + ') + (' + shift + ')') : '' };
    /* Кривая после вмешательства готова — её и рисуем, независимо от того,
       найдётся ли дальше новое равновесие. */
    STATE.shift = shift;
    STATE.advTau = adv ? tau : 0;
    STATE.taxAfterS = sAfter;                     // ту же функцию рисует drawShiftedSupply
    /* Эквивалентная запись «налог платит покупатель» (для рисования): при потоварном —
       D − t, при адвалорном — D/(1+τ). Объём и цены получаются те же самые.
       Строится ЗДЕСЬ, рядом с sAfter: при налоге на покупателя рисуется именно
       она, и её отсутствие означало бы неподвижный график ровно так же. */
    const dSrc = (STATE.D && STATE.D.expr) ? String(STATE.D.expr) : '';
    STATE.taxAfterD = adv
      ? { fn: q => { const d = evalCurve(STATE.D, q); return isNaN(d) ? NaN : d / factor; },
          texExpr: dSrc ? simplifyRecord('(' + dSrc + ') / ' + factor) : '' }
      /* ⚠️ ЗНАК БЕРЁТСЯ У `shift`, А НЕ У СТАВКИ.
         Здесь стояло `- STATE.tax`, то есть знак был жёстко налоговым: при
         субсидии покупателю эффективный спрос ПОДНИМАЕТСЯ на ставку, а
         рисовался бы опущенным. `shift` уже несёт знак (`isSub ? -tax : tax`),
         поэтому вычитание его даёт оба случая разом: налог D − t, субсидия
         D + s. Процентную ветку (`d / factor`) это не касается — она верна
         для всех четырёх форм таблицы PCT_FORMS. */
      : { fn: q => evalCurve(STATE.D, q) - shift,
          texExpr: dSrc ? simplifyRecord('(' + dSrc + ') - (' + shift + ')') : '' };
    STATE.taxCurveOn = true;

    const te = findEquilibrium(STATE.D, sAfter);
    if (te) {
      const Q1 = te.Q;
      const Pb = evalCurve(STATE.D, Q1);          // цена покупателя
      // Цена продавца: в обоих случаях это S(Q1) (для потоварного — ровно Pb − ставка).
      const Ps = adv ? evalCurve(STATE.S, Q1) : (Pb - shift);
      STATE.taxEq = { Q: Q1, Pb, Ps };
      // Объём денег = площадь прямоугольника между ценами покупателя и продавца.
      // Для потоварного это в точности ставка·Q1, для адвалорного — τ·Ps·Q1 (налог).
      STATE.tx = Math.abs(Pb - Ps) * Q1;
      STATE.budget = (STATE.intervType === 'subsidy' ? -1 : 1) * STATE.tx;  // +сбор / -расход
      STATE.csTax = integrate(q => quadPrice(STATE.D, q) - Pb, 0, Q1);
      STATE.psTax = integrate(q => Ps - quadPrice(STATE.S, q), 0, Q1);
      STATE.taxActive = true;

      /* ⚠️ ДВА КРАЯ У ЭТОГО ПРАВИЛА, И ОБА ЗДЕСЬ.
         DWL и все «было → стало» требуют ОБОИХ равновесий: площадь считается
         МЕЖДУ старым и новым объёмом, а бремя — как разность с исходной ценой.
         Исходного равновесия не было — считать не из чего, и подставить нуль
         вместо «до» нельзя: нуль это число, и на табло он читался бы как
         «до вмешательства торговли не было», а правда другая — рынка не было
         вовсе. Поэтому величины остаются пустыми, а панель говорит словами
         (STATE.taxNoBase). */
      if (STATE.eq) {
        const Q0 = STATE.eq.Q;
        const lo = Math.min(Q1, Q0), hi = Math.max(Q1, Q0);
        // DWL — площадь между D и S на интервале между старым и новым Q (всегда > 0).
        STATE.dwl = areaBetween(q => evalCurve(STATE.D, q) - evalCurve(STATE.S, q), lo, hi);
        if (STATE.intervType === 'subsidy') {
          STATE.incBuyer = STATE.eq.P - Pb;       // выигрыш покупателя (цена упала)
          STATE.incSeller = Ps - STATE.eq.P;      // выигрыш продавца (цена выросла)
        } else {
          STATE.incBuyer = Pb - STATE.eq.P;       // бремя покупателя
          STATE.incSeller = STATE.eq.P - Ps;      // бремя продавца
        }
      } else {
        STATE.taxNoBase = true;
      }
    }
  }

  // Ценовое регулирование: потолок / пол цены (Задача 1).
  // Государство фиксирует P_reg. Объём торговли — короткая сторона рынка.
  STATE.pcMode = compMarket && scenarioNone && (STATE.intervType === 'ceiling' || STATE.intervType === 'floor');
  STATE.pcActive = false;
  STATE.pc = null;
  /* Равновесие здесь тоже не пропуск: фиксированная цена и короткая сторона
     рынка считаются по самим кривым. Ниже равновесие входит только туда, где
     оно действительно нужно, — в проверку «связывает ли» и в потери. */
  if (STATE.pcMode && STATE.D && STATE.S && STATE.pReg > 0) {
    const Preg = STATE.pReg;
    const isCeiling = (STATE.intervType === 'ceiling');
    // Связывает ли регулирование: потолок ниже равновесия / пол выше равновесия.
    /* Без исходного равновесия сравнивать не с чем, и вместо сравнения
       действует его определение: регулирование связывает, когда при этой цене
       спрос и предложение не сходятся. Там, где равновесие есть, оба способа
       дают одно и то же, поэтому проверенные числа не двигаются — сравнение
       остаётся первым. */
    const binding = STATE.eq
      ? (isCeiling ? (Preg < STATE.eq.P) : (Preg > STATE.eq.P))
      : (() => {
          const a = invCurve(STATE.D, Preg), b = invCurve(STATE.S, Preg);
          return (a != null && b != null) ? Math.abs(a - b) > 1e-9 : false;
        })();
    const Qd = invCurve(STATE.D, Preg);   // объём спроса при цене Preg (D⁻¹)
    const Qs = invCurve(STATE.S, Preg);   // объём предложения при цене Preg (S⁻¹)
    const Qtrade = (Qd != null && Qs != null) ? Math.min(Qd, Qs) : null;  // короткая сторона
    /* Дефицит и избыток существуют, только когда регулирование СВЯЗЫВАЕТ.
       Раньше разность считалась всегда, и у несвязывающего потолка в состоянии
       лежало «40» — число, которого на этом рынке нет: по равновесной цене
       рынок расчищается. Панель его не показывала, но состояние врало. */
    const gap = (binding && Qd != null && Qs != null) ? Math.abs(Qd - Qs) : null;
    STATE.pc = { Preg, isCeiling, binding, Qd, Qs, Qtrade, gap };
    if (binding && Qtrade != null) {
      // CS / PS считаем интегрированием по фактическому объёму торговли.
      STATE.pc.cs = integrate(q => quadPrice(STATE.D, q) - Preg, 0, Qtrade);
      STATE.pc.ps = integrate(q => Preg - quadPrice(STATE.S, q), 0, Qtrade);
      STATE.pc.sw = STATE.pc.cs + STATE.pc.ps;
      // DWL — площадь между D и S от Q_trade до Q* (недо-/перепроизводство).
      // Требует ОБОИХ объёмов: без исходного равновесия второго края у площади нет.
      if (STATE.eq) {
        const lo = Math.min(Qtrade, STATE.eq.Q), hi = Math.max(Qtrade, STATE.eq.Q);
        STATE.pc.dwl = areaBetween(q => evalCurve(STATE.D, q) - evalCurve(STATE.S, q), lo, hi);
        STATE.pcActive = true;
      } else {
        /* ⚠️ ГРАНИЦА У ПОТОЛКА И ПОЛА ПРОВЕДЕНА ИНАЧЕ, ЧЕМ У НАЛОГА, И НАРОЧНО.
           Линия цены, проекции Qd и Qs и зона дефицита рисуются по STATE.pc —
           а она теперь считается и без равновесия, поэтому графика работает.
           А вот `pcActive` оставляем при равновесии: за ним идут таблица
           «до → после», ключевые значения и заливка потерь, и все три
           построены вокруг исходного состояния. Регулировать цену на рынке,
           которого нет, — случай без экономического смысла: в отличие от
           налога, здесь не бывает так, чтобы вмешательство рынок СОЗДАЛО. */
        STATE.pc.dwl = null;
        STATE.pc.noBase = true;
      }
    }
  }

  /* КВОТА — прямое ограничение объёма (ночная сессия «вмешательство»).
     Экономика сюжета:
       • квота Qк ВЫШЕ равновесного объёма не связывает — рынок работает как обычно;
       • квота НИЖЕ равновесного объёма задаёт КОРИДОР цен [S(Qк); D(Qк)]:
         цена внутри него не определена однозначно, её выбирает пользователь;
       • CS = ∫₀^Qк (D − P), PS = ∫₀^Qк (P − S) — при движении цены по коридору
         они перетекают друг в друга;
       • CS + PS = ∫₀^Qк (D − S) от цены НЕ зависит, и потери
         DWL = ∫_Qк^Q* (D − S) тоже: обе величины считаются без участия P. */
  STATE.quotaMode = compMarket && scenarioNone && (STATE.intervType === 'quota');
  STATE.quotaActive = false;
  STATE.qt = null;
  if (STATE.quotaMode && STATE.D && STATE.S && STATE.eq && STATE.quota > 0) {
    const Qq = STATE.quota;
    const binding = Qq < STATE.eq.Q;
    const Plo = evalCurve(STATE.S, Qq);   // нижняя граница коридора: цена предложения
    const Phi = evalCurve(STATE.D, Qq);   // верхняя граница коридора: цена спроса
    STATE.qt = { Qq, binding, Plo, Phi };
    if (binding && isFinite(Plo) && isFinite(Phi) && Phi > Plo) {
      const pos = Math.max(0, Math.min(1, STATE.quotaPos));
      const P = Plo + (Phi - Plo) * pos;
      STATE.qt.P = P;
      STATE.qt.pos = pos;
      STATE.qt.width = Phi - Plo;
      STATE.qt.cs = integrate(q => quadPrice(STATE.D, q) - P, 0, Qq);
      STATE.qt.ps = integrate(q => P - quadPrice(STATE.S, q), 0, Qq);
      STATE.qt.sw = STATE.qt.cs + STATE.qt.ps;
      // Потери — площадь между D и S от квоты до равновесного объёма.
      // Цена в это выражение не входит: трапеция от положения ползунка не зависит.
      STATE.qt.dwl = areaBetween(q => evalCurve(STATE.D, q) - evalCurve(STATE.S, q), Qq, STATE.eq.Q);
      STATE.quotaActive = true;
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
  STATE.monoCeil = null; STATE.monoTax = null; STATE.monoFloor = null; STATE.monoQuota = null;
  if (STATE.market === 'monopoly' && STATE.monoMode === 'simple' && scenarioNone && STATE.mono) {
    const it = STATE.intervType;
    if ((it === 'tax' || it === 'subsidy') && STATE.tax > 0) {
      STATE.monoTax = monopolyTax(it === 'subsidy' ? -STATE.tax : STATE.tax);   // shift: +t налог / −s субсидия
    } else if (it === 'ceiling' && STATE.pReg > 0) {
      STATE.monoCeil = monopolyCeiling(STATE.pReg);
    } else if (it === 'floor' && STATE.pReg > 0) {
      STATE.monoFloor = monopolyFloor(STATE.pReg);
    } else if (it === 'quota' && STATE.quota > 0) {
      /* ⚠️ ЭТОЙ ВЕТКИ ЗДЕСЬ НЕ БЫЛО, И ИМЕННО ПОЭТОМУ КВОТА В МОНОПОЛИИ «НЕ
         РАБОТАЛА» (приёмка владельца 31.08). Каскад разбирал три вида из
         четырёх, «квота» не совпадала ни с одним, и не исполнялось ничего:
         ни расчёта, ни отрисовки, ни строки на табло. Конкурентный механизм
         квоты (выше в этой же функции) сюда попасть не мог: он опирается на
         кривую предложения S и на равновесие D = S, а в монополии есть спрос
         и предельные издержки. Подробности — в monopolyQuota. */
      STATE.monoQuota = monopolyQuota(STATE.quota);
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

  // Внешний эффект и корректирующий инструмент Пигу (Задача 4 + Фаза 2б).
  // Два ЗЕРКАЛЬНЫХ случая, общий код:
  //   'neg' — эффект на ИЗДЕРЖКАХ: MSC = MPC + ext (MPC = кривая S). Рынок (D = MPC)
  //           выпускает БОЛЬШЕ оптимума (D = MSC) → перепроизводство, лечится НАЛОГОМ.
  //   'pos' — эффект на ВЫГОДЕ: MSB = MPB + ext (MPB = кривая D). Рынок (MPB = S)
  //           выпускает МЕНЬШЕ оптимума (MSB = S) → недопроизводство, лечится СУБСИДИЕЙ.
  // Рыночное равновесие в обоих случаях одно и то же (пересечение частных кривых).
  STATE.ext = null;
  if (compMarket && STATE.scenario === 'externality' && STATE.D && STATE.S && STATE.eq) {
    /* Спрос ЕСТЬ предельная частная выгода MPB, предложение ЕСТЬ предельные
       частные издержки MPC — отдельных кривых для них не заводим и D с S не
       переименовываем. Общественные MSB и MSC по умолчанию совпадают с
       частными: пока чекбокс выключен, кривая просто не отличается от своей
       частной пары, оптимум совпадает с рынком, а DWL равен нулю. */
    const msb = q => (STATE.msbOn && STATE.msbCompiled)
      ? evalSocial(STATE.msbCompiled, STATE.msbExpr, q) : evalCurve(STATE.D, q);
    const msc = q => (STATE.mscOn && STATE.mscCompiled)
      ? evalSocial(STATE.mscCompiled, STATE.mscExpr, q) : evalCurve(STATE.S, q);
    const Qmkt = STATE.eq.Q, Pmkt = STATE.eq.P;
    // Общественный оптимум — там, где MSB = MSC (а не где D = S).
    const Qopt = findRoot(q => msb(q) - msc(q));
    let Popt = null, dwl = null, corrective = null, pigouEq = null, pos = false;
    if (Qopt != null) {
      Popt = msc(Qopt);                                    // высота пересечения MSB и MSC
      const lo = Math.min(Qopt, Qmkt), hi = Math.max(Qopt, Qmkt);
      /* Потери — площадь между общественными кривыми на промежутке от рыночного
         выпуска до оптимального. Правее оптимума каждая следующая единица стоит
         обществу дороже, чем даёт выгоды; левее — наоборот, недополученная выгода. */
      dwl = areaBetween(q => msb(q) - msc(q), lo, hi);
      pos = (Qopt - Qmkt) > 1e-9;                          // недопроизводство = эффект положительный
      /* Корректирующий инструмент двигает предложение так, чтобы ЧАСТНЫЙ рынок
         пришёл ровно в Qопт: D(Qопт) = S(Qопт) + сдвиг. Плюс — налог Пигу,
         минус — корректирующая субсидия. Формула общая на оба случая. */
      corrective = evalCurve(STATE.D, Qopt) - evalCurve(STATE.S, Qopt);
      const Sp = { fn: q => evalCurve(STATE.S, q) + corrective };
      pigouEq = findEquilibrium(STATE.D, Sp);
    }
    STATE.extSign = pos ? 'pos' : 'neg';   // знак — ВЫВОД расчёта, а не выбор кнопкой
    STATE.ext = { pos, msb, msc, social: pos ? msb : msc, other: pos ? msc : msb,
                  msbOn: !!STATE.msbOn, mscOn: !!STATE.mscOn,
                  Qmkt, Pmkt, Qopt, Popt, dwl,
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
  /* Звёздочка у буквы равновесия убрана (решение владельца 22.08): на холсте
     остаётся одна буква «E». Координаты по осям звёздочку сохраняют — там она
     и различает равновесное значение от текущего, а у самой точки различать
     нечего: другой E на графике нет. */
  pointName(g, px, py, 'E', COL.ink);
}

/* Пунктир в сторону пересечения, лежащего вне первой четверти.

   ⚠️ ЭТО НЕ РАВНОВЕСИЕ, И ВЫГЛЯДИТ ОНО ИНАЧЕ. Ни буквы E, ни чисел у осей:
   всё это язык настоящего равновесия, и повторять его здесь нельзя — числа
   на осях читались бы как обычные равновесные. Разговор об этой точке идёт
   в «Объяснении модели» целым абзацем, который нельзя прочитать вполглаза.

   Точка часто лежит за краем холста (у Qd = 100 − P и Qs = −200 + 0,5·P она
   в (−100, 200)). Специально расширять окно под неё не надо: пунктир доходит
   до края, и этого достаточно, чтобы стало видно, КУДА уехало пересечение. */
function drawOffQuadIntersection() {
  const off = STATE.offEq;
  if (!off || STATE.eq || !STATE.D || !STATE.S) return;
  const g = svg.append('g').attr('class', 'offquad').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const lo = Math.min(0, off.Q), hi = Math.max(0, off.Q);
  const N = 160;
  [STATE.D, STATE.S].forEach(c => {
    const pts = [];
    for (let i = 0; i <= N; i++) {
      const q = lo + (hi - lo) * i / N;
      const p = evalCurve(c, q);
      pts.push(isFinite(p) ? [q, p] : null);
    }
    g.append('path').datum(pts)
      .attr('fill', 'none').attr('stroke', c.color).attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '5 4').attr('opacity', 0.65)
      .attr('data-offquad', '1')
      .attr('data-skip-export', '1')   // продолжение за область смысла в .tex не уходит
      .attr('d', line);
  });
  // Сама точка — только если попала в кадр. Крестик без имени и без чисел у осей.
  const [qa, qb] = sx.domain(), [pa, pb] = sy.domain();
  if (off.Q >= qa && off.Q <= qb && off.P >= pa && off.P <= pb) {
    const [px, py] = toPx(off.Q, off.P);
    [[-5, -5, 5, 5], [-5, 5, 5, -5]].forEach(([a, b, cc, d]) => {
      g.append('line').attr('x1', px + a).attr('y1', py + b).attr('x2', px + cc).attr('y2', py + d)
        .attr('stroke', COL.inkSoft).attr('stroke-width', 1.5).attr('data-offquad', '1');
    });
  }
}

/* Абзац разбора про то же пересечение. Живёт в «Объяснении модели», а не в
   «Ключевых значениях»: строка с числами в табло соседствовала бы с
   настоящими равновесными значениями других сцен и слишком легко читалась бы
   как ещё одно нормальное число. Обозначений $Q^*$ и $P^*$ здесь нет
   намеренно — звёздочка это и есть знак равновесия. */
function offQuadExplainHtml() {
  const off = STATE.offEq;
  if (!off || STATE.eq) return '';
  const negQ = off.Q < -1e-9, negP = off.P < -1e-9;
  const why = (negQ && negP)
    ? 'Ни отрицательного количества, ни отрицательной цены на рынке не бывает'
    : (negQ ? 'Отрицательного количества на рынке не бывает'
            : 'Отрицательной цены на рынке не бывает');
  return '<div class="sb-note">' +
    '<p><b>Кривые пересекаются — но не там, где рынок возможен.</b> ' +
    'Пересечение приходится на $P = ' + fmt(off.P) + '$ и $Q = ' + fmt(off.Q) + '$. ' +
    why + ', поэтому равновесия нет: точка лежит за пределами первой четверти, ' +
    'и торговать в ней некому и нечем. Излишки, налоги и потери общества для неё ' +
    'не считаются — числа для несуществующего рынка были бы враньём.</p>' +
    '<p><b>Вывод:</b> найдя цену, обязательно проверяйте количество. ' +
    'Правдоподобная цена сама по себе ещё не означает, что решение найдено.</p>' +
    '</div>';
}

/* Абзац разбора про ПРОЦЕНТНУЮ форму. Соотношение цен набирается математикой
   ($...$, KaTeX), а не обычным текстом: «Ps = (1-t)*Pd», написанное буквами,
   у ученика читается как строка кода, а не как формула из учебника.

   Живёт рядом с offQuadExplainHtml и подключается тем же проходом
   moveExplanations (86-workspace.js): общий рассказ сцены остаётся на месте,
   а этот абзац приписывается в конец — он про конкретную выбранную форму. */
function pctFormExplainHtml() {
  const pf = pctForm();
  if (!pf || !STATE.taxActive || !STATE.taxEq) return '';
  const isSub = (pf.type === 'subsidy');
  const baseName = (pf.base === 'buyer') ? 'цены покупателя' : 'цены продавца';
  const mirror = (pf.base === 'buyer')
    ? 'Это зеркало акциза: та же база, обратный знак.'
    : 'Это зеркало НДС: та же база, обратный знак.';
  return '<div class="sb-note">' +
    '<p><b>' + pf.label + ': ставка это доля, а не сумма.</b> ' +
    (isSub ? 'Субсидия' : 'Налог') + ' берётся долей $\\tau$ от ' + baseName +
    ', поэтому предложение не сдвигается, а <b>поворачивается</b>: ' +
    '$S_{после}(Q) = ' + pf.curveTex + '$. ' +
    'Цены связаны так: $' + pf.priceTex + '$, а ' + (isSub ? 'расход бюджета' : 'сбор') +
    ' равен $' + pf.moneyTex + '$.</p>' +
    (isSub ? '<p>' + mirror + '</p>' : '') +
    '<p><b>Чем это отличается от потоварной формы?</b> У потоварной клин между ценами ' +
    'постоянен и равен ставке в рублях. У процентной он растёт вместе с ценой, поэтому ' +
    'при больших $Q$ разрыв между $S$ и $S_{после}$ шире, чем при малых.</p>' +
    '</div>';
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
      markNotationTspan(sel.append('tspan').attr('dy', (d - shift).toFixed(2) + 'em')
        .attr('font-size', '76%').text(p.v), p.v);
      shift = d;
    }
  });
  if (shift) sel.append('tspan').attr('dy', (-shift).toFixed(2) + 'em').text('\u200b');
  return sel;
}

// Есть ли в подписи что-то математическое: иначе не стоит и разбирать.
function hasMathMarkup(txt) { return /[*^_]/.test(String(txt == null ? '' : txt)); }

/* ── СМЕШАННАЯ ПОДПИСЬ: СЛОВА ПЛЮС ОБОЗНАЧЕНИЯ ───────────────────────────

   «TP, общий продукт», «max AP = MP при L = 15», «D частн.», «TC совокупная».
   Правило владельца требует набрать математикой ТОЛЬКО обозначение, а слова
   оставить шрифтом сайта. Поставить одно начертание на всю подпись нельзя:
   вместе с TP в математический шрифт уехало бы и слово «продукт».

   Раньше такие подписи объявлялись «долгом на отдельную задачу»: их пришлось
   бы резать на tspan'ы, а это переносы и съехавшая привязка. Переносов у
   подписи холста нет вовсе (она однострочная), а привязка держится на самом
   <text> — режется безопасно. Смещения базовой линии здесь тоже нет: все
   куски стоят на одной строке, меняется только шрифт.

   Берём ТОЛЬКО фразы, где есть кириллица: подпись, состоящая из одних
   обозначений, — это уже забота typesetChartLabels, и два хозяина у одного
   правила заводить незачем. */
/* Индекс-обозначение набирается математикой отдельно от своего основания.

   «68,28_{ATC}», «80_{MC}», «M_1» — основание это ЧИСЛО (ему положены
   табличные цифры, а не математический курсив), а индекс — обозначение
   кривой. Одним начертанием на всю подпись такое не выразить, поэтому шрифт
   ставится прямо на tspan индекса. */
function markNotationTspan(ts, v) {
  const s = String(v == null ? '' : v).trim();
  if (!s) return ts;
  /* Пометка `data-mathset` стоит на самом tspan, а не на подписи целиком:
     основание осталось обычным шрифтом намеренно, и помечать его как
     «набрано математикой» значило бы соврать прибору. */
  if (CHART_MATH_WORDS.has(s)) {
    ts.attr('style', "font-family:'KaTeX_Main','Times New Roman',serif;font-style:normal")
      .attr('data-mathset', 'upright');
  } else if (/^[A-Za-z]$/.test(s)) {
    ts.attr('style', "font-family:'KaTeX_Math','Times New Roman',serif;font-style:italic")
      .attr('data-mathset', 'italic');
  }
  return ts;
}

let _mixedRe = null;
function mixedNotationRe() {
  if (_mixedRe) { _mixedRe.lastIndex = 0; return _mixedRe; }
  const words = Array.from(CHART_MATH_WORDS).sort((a, b) => b.length - a.length);
  _mixedRe = new RegExp('(^|[^A-Za-zА-Яа-яЁё0-9_])('
    + words.join('|') + '|[A-Z])(?![A-Za-zА-Яа-яЁё0-9_])', 'g');
  return _mixedRe;
}

function mixedMathTspans(sel, txt) {
  const s = String(txt);
  const re = mixedNotationRe();
  const parts = [];
  let last = 0, m;
  while ((m = re.exec(s))) {
    const at = m.index + m[1].length;
    if (at > last) parts.push({ math: false, v: s.slice(last, at) });
    parts.push({ math: true, v: m[2] });
    last = at + m[2].length;
    re.lastIndex = last;
  }
  if (!parts.some(p => p.math)) return null;      // обозначений нет — не наше дело
  if (last < s.length) parts.push({ math: false, v: s.slice(last) });
  parts.forEach(p => {
    if (!p.v) return;
    const ts = sel.append('tspan').text(p.v);
    if (!p.math) return;
    /* Многобуквенное обозначение — прямым начертанием (как \mathrm{MC}),
       одиночная величина — наклонным. Тот же выбор, что и у целых подписей. */
    if (/^[A-Z]{2,}$/.test(p.v)) {
      ts.attr('style', "font-family:'KaTeX_Main','Times New Roman',serif;font-style:normal");
    } else {
      ts.attr('style', "font-family:'KaTeX_Math','Times New Roman',serif;font-style:italic");
    }
    ts.attr('data-mathset', /^[A-Z]{2,}$/.test(p.v) ? 'upright' : 'italic');
  });
  // Подпись разобрана здесь целиком: общему правилу тут делать нечего.
  sel.attr('data-mathset', 'mixed');
  return sel;
}

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
  /* Третий аргумент — «это часть ВЕЛИЧИНЫ, а не проза». Основание величины
     («M» в «Md», «Q» в «Q*») набирается математикой так же, как её индекс:
     без этого у денежного рынка буква M стояла системным шрифтом, а её
     индекс — математическим, то есть в одной подписи два шрифта подряд.
     Числовое основание («68,28» в «68,28_ATC») markNotationTspan не трогает:
     числу положены табличные цифры, а не математический курсив. */
  const put = (v, kind, isSym) => {
    if (!v) return;
    if (kind === 'txt') {
      const ts = sel.append('tspan').text(v);
      if (isSym) markNotationTspan(ts, v);
      if (shift) { ts.attr('dy', (-shift).toFixed(2) + 'em'); shift = 0; }
      return;
    }
    const d = (kind === 'sup') ? -0.42 : 0.26;
    markNotationTspan(sel.append('tspan').attr('dy', (d - shift).toFixed(2) + 'em')
      .attr('font-size', '76%').text(v), v);
    shift = d;
  };
  parts.forEach(p => {
    if (p.kind === 'sym') {
      put(p.greek ? qtyGreekChar(p.greek) : p.s, 'txt', true);
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
  // Слова вперемешку с обозначениями: обозначения набираются, слова остаются.
  if (/[А-Яа-яЁё]/.test(s)) { const mixed = mixedMathTspans(sel, s); if (mixed) return mixed; }
  return sel.text(s);
}

/* Седьмой аргумент — `{ noFlip: true }`: подпись НЕ разворачивать, даже если
   она не влезает. Нужен подписям координат у оси цены: развернувшись, они
   уезжают в первую четверть, а там их быть не должно (см. axisValueY). Такие
   подписи считают своё место сами, по настоящей ширине нарисованного текста. */
function haloText(g, x, y, txt, anchor, baseline, opts) {
  /* ⚠️ НЕЧИСЛОВАЯ КООРДИНАТА — ЭТО НЕ «ПОДПИСЬ ПОСЕРЕДИНЕ», А ПОДПИСЬ В НУЛЕ.
     x="NaN" браузер отбрасывает и рисует текст от левого края холста; при
     якоре middle половина строки уезжает за край. Замер 21.08 («Безработица
     = 0» в рынке труда): bbox.x = −50 при ширине 100, на экране читалось
     «тица = 0». Молча не рисуем и говорим об этом в консоль: подпись без
     координаты — всегда ошибка расчёта выше по течению. */
  if (!isFinite(x) || !isFinite(y)) { console.warn('haloText: нечисловая координата', { x, y, txt }); return null; }
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
  /* ⚠️ ОРЕОЛ РИСУЕТСЯ ПЕРЕД БУКВОЙ И ШИРЕ ЕЁ (решение владельца 22.08).
     `paint-order: stroke` кладёт обводку ПОД заливку — иначе она съела бы
     половину штриха самой буквы. Цвет обводки — фон холста (--halo), поэтому
     кривая, прошедшая через подпись, обрывается у её края и не идёт сквозь
     букву. Ширина 5 (по 2,5 px с каждой стороны) при кегле FS.large: прежние
     2,5 давали 1,25 px, и линия толщиной 2,5 px протыкала букву насквозь —
     ровно то, что видел владелец у точки равновесия. */
  const t = g.append('text').attr('class', 'point-name')
    .attr('x', px + (o.dx == null ? 8 : o.dx))
    .attr('y', py + (o.dy == null ? -8 : o.dy))
    .attr('font-size', o.size || FS.large).attr('font-weight', o.weight || 600)
    .attr('fill', color || COL.ink)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo)
    .attr('stroke-width', o.halo == null ? 5 : o.halo).attr('stroke-linejoin', 'round');
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
  /* ⚠️ ПРИ СВЯЗЫВАЮЩЕМ ЦЕНОВОМ РЕГУЛИРОВАНИИ РАВНОВЕСИЯ НЕТ ВОВСЕ.
     Цену назначает государство, величина спроса и величина предложения при
     ней расходятся, и рынок не расчищается. Заголовок «Равновесие D = S» над
     этими числами был бы неправдой, поэтому он меняется вместе с числами. */
  if (STATE.pcActive && STATE.pc) return STATE.pc.isCeiling ? 'Рынок при потолке цены' : 'Рынок при поле цены';
  if (STATE.quotaActive) return 'Рынок при квоте';
  if (STATE.taxActive) return (STATE.intervType === 'subsidy') ? 'Рынок после субсидии' : 'Рынок после налога';
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

/* Ключевые значения РЫНКА С ВМЕШАТЕЛЬСТВОМ. Возвращает готовую разметку или
   null, если вмешательства нет (или оно не связывает) — тогда табло печатает
   обычное равновесие.

   Числа берутся из того же расчёта, по которому рисуется график
   (STATE.pc / STATE.taxEq / STATE.qt), — никакой параллельной математики. */
function interventionKeyValues() {
  /* Строка «было» существует только тогда, когда было. Без исходного
     равновесия она пустая, а объяснение «рынок появился из-за вмешательства»
     печатает вызывающий блок. */
  const was = STATE.eq
    ? ('Равновесие без вмешательства: $Q^* = ' + fmt(STATE.eq.Q)
       + '$, $P^* = ' + fmt(STATE.eq.P) + '$.')
    : '';

  // (1) Потолок и пол цены. Связывают — равновесия нет, есть Qd, Qs и разрыв.
  if (STATE.pcActive && STATE.pc) {
    const pc = STATE.pc;
    const isC = pc.isCeiling;
    return `<div class="stat"><span>${isC ? '$P_c$ (потолок цены)' : '$P_f$ (пол цены)'}</span><b>${fmt(pc.Preg)}</b></div>` +
      `<div class="stat"><span>$Q_d$ (величина спроса)</span><b>${fmt(pc.Qd)}</b></div>` +
      `<div class="stat"><span>$Q_s$ (величина предложения)</span><b>${fmt(pc.Qs)}</b></div>` +
      `<div class="stat"><span>${isC ? 'Дефицит' : 'Избыток'}</span><b>${fmt(pc.gap)}</b></div>` +
      `<div class="stat"><span>$DWL$ (потери общества)</span><b>${fmt(pc.dwl)}</b></div>` +
      `<div class="hint">Цену назначило государство, поэтому равновесия нет: ` +
      `по цене ${fmt(pc.Preg)} рынок не расчищается. Торгуется короткая сторона — ${fmt(pc.Qtrade)}. ` +
      was + `</div>`;
  }

  // (2) Налог и субсидия. Рынок расчищается, но цен становится ДВЕ.
  if (STATE.taxActive && STATE.taxEq) {
    const t = STATE.taxEq;
    const sub = (STATE.intervType === 'subsidy');
    return `<div class="stat"><span>$Q$ (объём торговли)</span><b>${fmt(t.Q)}</b></div>` +
      `<div class="stat"><span>$P_b$ (платит покупатель)</span><b>${fmt(t.Pb)}</b></div>` +
      `<div class="stat"><span>$P_s$ (получает продавец)</span><b>${fmt(t.Ps)}</b></div>` +
      `<div class="hint">Цена покупателя и цена продавца разошлись на ` +
      `${sub ? 'субсидию' : 'налог'} — одной цены на этом рынке больше нет. ` + was + `</div>`;
  }

  // (3) Квота. Объём задан прямо, а цена не определена — она лежит в коридоре.
  if (STATE.quotaActive && STATE.qt) {
    const q = STATE.qt;
    return `<div class="stat"><span>$Q$ (объём торговли)</span><b>${fmt(q.Qq)}</b></div>` +
      `<div class="stat"><span>$P$ (выбранная цена)</span><b>${fmt(q.P)}</b></div>` +
      `<div class="stat"><span>Коридор возможных цен</span><b>${fmt(q.Plo)} … ${fmt(q.Phi)}</b></div>` +
      `<div class="hint">Квота ниже равновесного объёма, поэтому одной цены рынок не задаёт: ` +
      `подойдёт любая внутри коридора. ` + was + `</div>`;
  }
  return null;
}

// Табло слева: показываем Q* и P* (или подсказку / «не найдено»).
/* Сколько раз кривые пересекаются в области модели.
   В сцене сложения ответ дорогой (кусочная запись через Math.js) и при этом
   от кадра не зависит — держим его в кэше рядом с остальной аналитикой.
   В обычных сценах кривые прямые, и считать заново нечего. */
function countCrossings(D, S) {
  const span = eqSearchSpan(D, S);
  const key = sumSceneOn() ? (STATE._sumSig + '|' + span) : null;
  if (key && key === STATE._sumCrossKey) return STATE._sumCrossVal;
  const n = crossingCount(q => evalCurve(D, q) - evalCurve(S, q), 0, span);
  if (key) { STATE._sumCrossKey = key; STATE._sumCrossVal = n; }
  return n;
}

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
    /* ⚠️ СОВЕТ «ОТОДВИНЬТЕ ГРАНИЦЫ ПЛОСКОСТИ» УБРАН — ОН БОЛЬШЕ НЕ ПРАВДА.
       Он был верен ровно потому, что равновесие искалось до края видимого
       окна: отодвинул границы — нашлось. Ровно эту зависимость и убрала
       фаза 1, теперь область поиска у модели своя, и двигать окно бесполезно.
       Оставить совет значило бы посылать человека делать то, что не работает. */
    const off = STATE.offEq
      ? ' Кривые всё-таки пересекаются, но за пределами первой четверти — ' +
        'разбор этой точки в «Объяснении модели».'
      : '';
    /* ⚠️ ВМЕШАТЕЛЬСТВО МОЖЕТ РЫНОК СОЗДАТЬ, И ТОГДА «РАВНОВЕСИЯ НЕТ» — ВРАНЬЁ.
       Замер 25.08: D = 100 − P, S = 0,5·p − 200, потоварная субсидия 450 даёт
       настоящую торговлю Q = 50 по цене покупателя 50, а табло печатало
       «Кривые не пересекаются в первой четверти, поэтому равновесия нет».
       Числа с вмешательством считаются по НОВОМУ равновесию и от исходного не
       зависят, поэтому показываем их — и отдельной строкой объясняем, что до
       вмешательства рынка тут не было. */
    const made = interventionKeyValues();
    if (made) {
      box.innerHTML = made +
        '<div class="hint">Без вмешательства кривые в первой четверти не пересекаются: рынка ' +
        'не было вовсе, и он появился ровно из-за вмешательства.' + off + '</div>';
      return;
    }
    box.innerHTML = '<div class="warn">Кривые не пересекаются в первой четверти, ' +
      'поэтому равновесия нет. Измените формулу спроса или предложения.' + off + '</div>';
    return;
  }
  /* ⚠️ ТАБЛО ПОКАЗЫВАЕТ ТО, ЧТО НА РЫНКЕ НА САМОМ ДЕЛЕ (приёмка владельца 24.08).
     До правки здесь всегда печаталось STATE.eq — голое пересечение D и S, то
     есть равновесие БЕЗ вмешательства. График при этом рисовался по ветке
     регулирования, и на одном экране стояли числа из двух разных миров:
     замер — потолок 30 при D = 100 − Q и S = Q давал в табло «Q* 50, P* 50»,
     хотя по цене 30 величина спроса 70, величина предложения 30 и дефицит 40.
     Оговорка «до вмешательства государства» этого не спасала: она объясняла
     ЧУЖОЕ число вместо того, чтобы показать своё.

     Роли блоков при этом не смешиваются: «Ключевые значения» отвечают на
     вопрос «что сейчас», а «Вмешательство» — на вопрос «как изменилось»
     (таблица До/После остаётся там и здесь не повторяется).
     Несвязывающее регулирование (потолок выше равновесной цены, пол ниже)
     равновесия не отменяет — там всё по-прежнему. */
  const pcOut = interventionKeyValues();
  if (pcOut) { box.innerHTML = pcOut; return; }

  let html =
    `<div class="stat"><span>$Q^*$ (количество)</span><b>${fmt(STATE.eq.Q)}</b></div>` +
    `<div class="stat"><span>$P^*$ (цена)</span><b>${fmt(STATE.eq.P)}</b></div>` +
    beforeInterventionNote();
  /* Б31. Кривые могут пересечься не один раз, и тогда равновесие не одно.
     Молчать об этом нельзя: все дальнейшие числа считаются вокруг ОДНОГО
     из них, и человек вправе знать, вокруг какого. */
  /* ⚠️ СКОЛЬКО РАЗ КРИВЫЕ ПЕРЕСЕКАЮТСЯ — ТОЖЕ СВОЙСТВО МОДЕЛИ, А НЕ КАДРА.
     Здесь стоял `CONFIG.Qmax`, и подсказка «равновесий несколько» появлялась
     и исчезала от колеса мыши: отдалились — второе пересечение вошло в кадр,
     приблизились — пропало. Считаем по той же области, по которой ищем само
     равновесие. Заодно это снимает восемьсот вычислений кусочной записи с
     каждого кадра панорамирования. */
  const n = countCrossings(STATE.D, STATE.S);
  if (n > 1) html += `<div class="hint">Кривые пересекаются ${n} раза, то есть равновесий несколько. ` +
    `Взято ближайшее к началу координат: ${'$Q^* = ' + fmt(STATE.eq.Q) + '$'}. Излишки и потери посчитаны вокруг него.</div>`;
  box.innerHTML = html;
}


/* =====================================================================
   БЛОК 5б. СЛОЖЕНИЕ СПРОСОВ И ПРЕДЛОЖЕНИЙ — горизонтальная сумма.

   Договорённость созвона: сначала спрашиваем, СКОЛЬКО спросов и сколько
   предложений; затем выписываем каждый; складываются они ГОРИЗОНТАЛЬНО —
   по количествам при одной цене, а не по ценам.

   ⚠️ ГРУППА С ОТРИЦАТЕЛЬНЫМ КОЛИЧЕСТВОМ В СУММУ НЕ ВХОДИТ. При цене выше
   своей запретительной покупатель просто не покупает, а продавец с высокими
   издержками при низкой цене не продаёт — «минус пять штук» на рынке не
   бывает. Именно это выключение и создаёт изломы суммарной кривой: в точке,
   где очередная группа входит в торговлю, наклон меняется скачком.

   ⚠️ ОСОБОГО ПУТИ ДЛЯ ЭТИХ ИЗЛОМОВ НЕТ. Суммарная кривая — обычная кривая
   списка (роль «спрос» / «предложение»), поэтому её изломы, пересечения и
   выходы на оси находит общий детектор ключевых точек. В проекте уже убирали
   особый путь для излома кусочной ([ADR: решение 22.08]) — повторять не надо.
   ===================================================================== */

// Идёт ли сейчас сюжет сложения.
function sumSceneOn() { return !!STATE.sumOn; }

// Группы одной стороны рынка, у которых набрана формула ('D' — спрос, 'S' — предложение).
function sumGroupsOf(side) {
  return STATE.curves.filter(c => c.sumGroup === side && c.kind !== 'sum' && c.expr);
}

/* Количество одной группы при цене P. Ноль означает «эта группа при такой цене
   не торгует» — и в сумму она не входит. Прямые считаем по свободному члену и
   наклону (это точно и дёшево), остальное — общей обратной функцией. */
function sumGroupQty(c, P) {
  if (c.linear && isFinite(c.linear.a) && c.linear.a !== 0) {
    const q = (P - c.linear.b) / c.linear.a;
    return (isFinite(q) && q > 0) ? q : 0;
  }
  const q = invCurve(c, P);
  return (q != null && isFinite(q) && q > 0) ? q : 0;
}

/* Запретительная цена группы — та, при которой её количество обращается в ноль.
   Для спроса это верхняя граница («дороже не куплю»), для предложения нижняя
   («дешевле не выйду на рынок»). Ровно в этих ценах суммарная кривая ломается,
   поэтому они попадают в расчёт ТОЧНО, а не в ближайший узел сетки. */
function sumChokePrice(c) {
  const p = evalCurve(c, 0);
  return isFinite(p) ? p : NaN;
}

/* ── Аналитическая запись суммарной кривой ────────────────────────────
   Пока все группы заданы прямыми, сумма считается точно и в закрытом виде:
   на каждом участке цен активен свой набор групп, и суммарное количество
   линейно по цене. Обращаем — получаем P = f(Q) по участкам, то есть ровно
   ту кусочную запись, которую движок и поле уже умеют (Фаза 3).

   Возвращает строку Math.js или null, если хоть одна группа не прямая. */
/* ⚠️ ВЕРХНЯЯ ГРАНИЦА ЗАПИСИ — СВОЙСТВО ГРУПП, А НЕ КАДРА.

   Здесь стоял `CONFIG.Pmax`, то есть верх ВИДИМОГО окна. Из-за этого границы
   участков в «Объяснении модели» ехали вместе с масштабом: один и тот же
   набор групп давал «Q <= 180» на стартовом окне и «Q <= 300» после
   отдаления — три разные записи одной и той же кривой. А поскольку по этой
   записи кривая и считается (одно значение — один источник), вместе с ней
   ехала и вся арифметика излишков.

   Берём самую высокую запретительную цену групп с двойным запасом: выше неё
   торгует всё тот же набор групп, участок там один и тянется сколь угодно
   далеко, поэтому конкретное значение верха на числа уже не влияет — важно
   лишь, чтобы оно было ОДНО И ТО ЖЕ при любом масштабе. Сотня — пол для
   вырожденного случая, когда все запретительные цены нулевые. */
function sumPriceTop(ls) {
  let top = 0;
  ls.forEach(l => { if (isFinite(l.b) && l.b > top) top = l.b; });
  return Math.max(100, top * 2);
}

/* ⚠️ СТОРОНА РЫНКА ЗДЕСЬ НЕ УКРАШЕНИЕ, А ЧАСТЬ ОТВЕТА.
   Границы у спроса и предложения РАЗНОЙ ПРИРОДЫ, и различить их по одной
   только арифметике участков нельзя:
     • у СПРОСА последний участок кончается при P = 0 — все группы исчерпаны,
       дальше покупателей нет. Для 100−Q и 60−Q это Q = 160, и это настоящая
       экономическая граница;
     • у ПРЕДЛОЖЕНИЯ верхней границы НЕ СУЩЕСТВУЕТ. Последний участок обрывался
       на `sumPriceTop` — служебной подпорке для перебора участков по ценам
       (max(100, 2 × макс. запретительная цена)). Для S₁ = Q, S₂ = Q + 20 это
       ровно 100, при P = 100 объём равен 180 — и число 180 уезжало в
       `sumDomainTo`, а оттуда в условие «20 ≤ Q ≤ 180» и в обрыв линии.
   Почему формула последнего участка верна и выше потолка: потолок по
   построению строго больше любой запретительной цены, значит выше него ни
   одна новая группа войти уже не может, набор торгующих не меняется, и
   участок тянется сколь угодно далеко. */
function sumLinearRecord(groups, side) {
  if (!groups.length) return null;
  const ls = [];
  for (const c of groups) {
    const l = c.linear;
    if (!l || !isFinite(l.a) || !isFinite(l.b) || l.a === 0) return null;
    ls.push(l);
  }
  const Pmax = sumPriceTop(ls);
  const round = (v) => Math.round(v * 1e9) / 1e9;
  // Границы участков по цене: концы собственного диапазона модели плюс все
  // запретительные цены внутри него.
  const marks = [0, Pmax];
  ls.forEach(l => { if (l.b > 0 && l.b < Pmax) marks.push(l.b); });
  const ps = Array.from(new Set(marks.map(round))).sort((a, b) => a - b);
  const segs = [];
  for (let i = 0; i < ps.length - 1; i++) {
    const p0 = ps[i], p1 = ps[i + 1], mid = (p0 + p1) / 2;
    // Кто торгует на этом участке цен. Смотрим в середине: набор внутри постоянен.
    let A = 0, C = 0, n = 0;
    ls.forEach(l => {
      if ((mid - l.b) / l.a > 0) { A += 1 / l.a; C += -l.b / l.a; n++; }   // Q = A·P + C
    });
    if (!n || Math.abs(A) < 1e-12) continue;
    const q0 = A * p0 + C, q1 = A * p1 + C;
    const lo = Math.min(q0, q1), hi = Math.max(q0, q1);
    if (!(hi - lo > 1e-9)) continue;
    // Обращаем: P = (Q − C) / A. Числа A и C держим как есть — печатать их
    // будет sumSegExpr, и он сам решит, раскрывать дробь или нет.
    segs.push({ lo: round(lo), hi: round(hi), A: A, C: C });
  }
  if (!segs.length) return null;
  segs.sort((x, y) => x.lo - y.lo);
  // У предложения последний участок не имеет правого края — см. выше.
  const openRight = (side === 'S');

  /* ⚠️ ЗАПИСЬ ОБЯЗАНА БЫТЬ СПЛОШНОЙ ОТ Q = 0.

   Запись начиналась там, где первая группа выходит на рынок. У предложения
   Q − 100 это Q = 100: сама группа при нулевой цене уже готова отдать сто
   штук, но участка «от нуля до ста» в записи не было вовсе, и на нём функция
   давала NaN. Дальше этот NaN уходил в интеграл излишка продавца — и вместо
   числа на табло стояло «PS = NaN», а рядом краснело предупреждение о
   расхождении.

   Считаем количество при НУЛЕВОЙ цене: если оно положительно, значит на
   отрезке от нуля до него товар предлагают уже даром, и обратная функция там
   равна нулю (цена не бывает отрицательной — решение «правило первой
   четверти»). Этот кусок и дописываем в начало. */
  let qAtZero = 0;
  ls.forEach(l => { const q = -l.b / l.a; if (q > 0) qAtZero += q; });
  qAtZero = round(qAtZero);
  /* ⚠️ ЭТОТ КУСОК — ЕДИНСТВЕННОЕ МЕСТО, ГДЕ РЫНКА НЕТ, А ЗАПИСЬ ЕСТЬ.
     Мы дописали его сами, чтобы функция не давала NaN, — значит мы же и
     обязаны сказать об этом отрисовке. Отсюда ghostTo: до этого количества
     кривая рисуется пунктиром (решение владельца 25.08). Угадывать «здесь
     цена ноль» по готовой записи нельзя: у предложения P = Q цена тоже ноль,
     но ровно в одной точке, и рынок там существует. */
  let ghostTo = 0;
  if (qAtZero > 1e-9 && Math.abs(segs[0].lo - qAtZero) < 1e-6) {
    segs.unshift({ lo: 0, hi: qAtZero, A: 0, C: 0, body: '0' });
    ghostTo = qAtZero;
  }

  // Точки излома по количеству — границы участков, кроме самого начала.
  const breaks = segs.map(x => x.lo).filter(x => x > 1e-9);
  /* ⚠️ ПРАВЫЙ КОНЕЦ ОБЛАСТИ ОПРЕДЕЛЕНИЯ — ЭТО НЕ ИЗЛОМ, НО ЭТО УЗЕЛ.
     В `breaks` лежат только ЛЕВЫЕ края участков, и правого конца записи
     (у спроса 100−Q и 60−Q это Q = 160) среди них нет. Пока правый край окна
     был левее 160, узел `hi` считался и линия рисовалась целиком; как только
     окно стало шире области определения, узел `hi` дал NaN, точка стала
     null — и путь оборвался на последнем живом узле, то есть на изломе
     (замер 26.08: последняя точка пути (40; 60) вместо (160; 0)).

     Отдаём правый конец отдельным полем. В `breaks` его дописывать НЕЛЬЗЯ:
     оттуда читают ключевые точки (лишняя отметка на графике) и
     integrateBroken — а конец кривой изломом не является. */
  const domainTo = openRight ? Infinity : segs[segs.length - 1].hi;
  /* Собираем цепочку условий тем же способом, что и конструктор кусочной:
     показывать её плоским списком умеет condChainToCases (82-input.js).
     Хвост NaN означает «вне участков функции нет» — там она не рисуется. */
  let out = null;
  for (let i = segs.length - 1; i >= 0; i--) {
    const s = segs[i];
    const last = (i === segs.length - 1);
    const cond = (last && openRight)
      ? '(Q >= ' + s.lo + ')'
      : '(Q >= ' + s.lo + ' and Q ' + (last ? '<= ' : '< ') + s.hi + ')';
    const body = (s.body != null) ? s.body : sumSegExpr(s.A, s.C);
    if (out === null) { out = cond + ' ? ' + body + ' : NaN'; continue; }
    out = cond + ' ? ' + body + ' : (' + out + ')';
  }
  return { expr: out, breaks: breaks, ghostTo: ghostTo, domainTo: domainTo };
}

/* ⚠️ ИНТЕГРАЛ ПОД ЛОМАНОЙ СЧИТАЕТСЯ ПО УЧАСТКАМ, А НЕ ОДНОЙ СЕТКОЙ.
   Метод трапеций точен на прямой, но только если излом попал в УЗЕЛ сетки.
   Замер 24.08: излишек покупателей под суммарным спросом выходил 1625,0003
   вместо 1625 — излом при Q = 40 лёг внутрь трапеции (шаг 70/1000 = 0,07,
   узла в 40 нет). Три десятитысячных — это не округление, а промах метода, и
   на сверке двух путей с допуском 1e-6 он виден сразу. Разбиваем отрезок
   точками излома: на каждом куске функция снова прямая и трапеции точны. */
function integrateBroken(f, a, b, breaks) {
  if (!(b > a)) return 0;
  const inner = (breaks || []).filter(x => x > a + 1e-12 && x < b - 1e-12);
  if (!inner.length) return integrate(f, a, b);
  const pts = [a].concat(inner.slice().sort((x, y) => x - y), [b]);
  let acc = 0;
  for (let i = 0; i < pts.length - 1; i++) acc += integrate(f, pts[i], pts[i + 1], 400);
  return acc;
}

// Точки излома кривой, если она их знает (суммарная — знает). Иначе пусто.
function curveBreaks(c) { return (c && c.sumBreaks) ? c.sumBreaks : []; }

/* ⚠️ ОБРЕЗКА НУЛЁМ САМА СОЗДАЁТ ИЗЛОМ, И ИНТЕГРАТОР ОБЯЗАН О НЁМ ЗНАТЬ.

   quadPrice читает отрицательную цену как ноль, поэтому у предложения Q − 100
   при Q = 100 появляется угол: слева площадь считается от нуля, справа — от
   прямой. Метод трапеций точен на прямой только тогда, когда излом попал в
   УЗЕЛ сетки. Замер 24.08: излишек первой группы выходил 2 687,9981 вместо
   2 688 — шаг 124/1000 = 0,124, узла ровно в сотне нет. Две тысячных это не
   округление, а промах метода, и сторож сходимости с допуском 1e-6 ловит его
   сразу. Добавляем ноль кривой к её собственным изломам. */
function quadBreaks(c, hi) {
  const out = curveBreaks(c).slice();
  const zero = curveZeroQ(c, Math.max(hi, 1));
  if (zero > 1e-9 && zero < hi - 1e-9) out.push(zero);
  return out;
}

/* ⚠️ УЧАСТОК СУММАРНОЙ КРИВОЙ ПИШЕТСЯ ДРОБЬЮ, ЕСЛИ НАКЛОН НЕ ДЕЛИТСЯ НАЦЕЛО.
   Суммарное количество на участке линейно по цене: Q = A·P + C. Обратно
   P = (Q − C) / A. У двух одинаковых групп A = −2, и раскрытая запись
   «80 − 0.5·Q» точна. У ТРЁХ одинаковых A = −3, и раскрытая дала бы
   «73.333 − 0.333·Q» — неправду в третьем знаке. А по этой записи кривая и
   считается (одно значение — один источник), поэтому враньё ушло бы прямо в
   излишки: сверка «сумма по группам против площади под суммарной кривой»
   расходилась бы на тысячные и обвиняла бы сложение вместо округления.
   Поэтому дробь раскрываем только когда это точно, иначе оставляем делением. */
function sumSegExpr(A, C) {
  const r9 = (v) => Math.round(v * 1e9) / 1e9;
  const slope = 1 / A, free = -C / A;
  const rs = Math.round(slope * 1e6) / 1e6, rf = Math.round(free * 1e6) / 1e6;
  if (Math.abs(rs - slope) < 1e-12 && Math.abs(rf - free) < 1e-12) return fmtLinear(rs, rf, 'Q', 6);
  const a = r9(A), c = r9(C);
  const inner = (sign) => {
    // sign = +1 → «Q − C», sign = −1 → «C − Q»
    if (c === 0) return sign > 0 ? 'Q' : '-Q';
    if (sign > 0) return c < 0 ? ('Q + ' + (-c)) : ('Q - ' + c);
    return c < 0 ? ('-Q - ' + (-c)) : (c + ' - Q');
  };
  return (a > 0) ? ('(' + inner(1) + ')/' + a) : ('(' + inner(-1) + ')/' + (-a));
}

/* Суммарная кривая по точкам — запасной путь для нелинейных групп.
   Идём по ценам, при каждой складываем количества торгующих групп и получаем
   ломаную в осях (Q, P); значение между узлами берём линейно. */
function sumPolyline(groups) {
  // Верх диапазона — как и у аналитической записи, свойство групп, а не кадра
  // (см. sumPriceTop): иначе ломаная перестраивалась бы при каждом зуме.
  let top = 0;
  groups.forEach(c => { const p = sumChokePrice(c); if (isFinite(p) && p > top) top = p; });
  const Pmax = Math.max(100, top * 2), N = 400;
  const prices = [];
  for (let i = 0; i <= N; i++) prices.push(Pmax * i / N);
  groups.forEach(c => { const p = sumChokePrice(c); if (p > 0 && p < Pmax) prices.push(p); });
  prices.sort((a, b) => a - b);
  const pts = [];
  prices.forEach(P => {
    let q = 0, n = 0;
    groups.forEach(c => { const g = sumGroupQty(c, P); if (g > 0) { q += g; n++; } });
    if (n) pts.push([q, P]);
  });
  pts.sort((a, b) => a[0] - b[0]);
  /* Та же дырка у нуля, что и в аналитической записи: при нулевой цене товар
     уже предлагают, и слева от этого количества ломаной не было вовсе.
     Дотягиваем её до Q = 0 по нулевой цене. */
  if (pts.length && pts[0][0] > 1e-9 && Math.abs(pts[0][1]) < 1e-9) {
    pts._ghostTo = pts[0][0];   // докуда рынка нет — см. sumLinearRecord
    pts.unshift([0, 0]);
  }
  return pts;
}

// Пересобрать одну суммарную кривую под текущие формулы групп.
function sumRebuildSide(side) {
  const cur = STATE.curves.find(c => c.kind === 'sum' && c.sumGroup === side);
  if (!cur) return;
  const groups = sumGroupsOf(side);
  cur.linear = null; cur.compiled = null; cur.fn = null; cur.sumBreaks = [];
  cur.sumGhostTo = 0;
  cur.sumDomainTo = 0;
  if (!groups.length) { cur.expr = ''; cur.sumNumeric = false; return; }
  const rec = sumLinearRecord(groups, side);
  if (rec) {
    /* ⚠️ ОДНО ЗНАЧЕНИЕ — ОДИН ИСТОЧНИК. Аналитическая запись не рисуется
       рядом с кривой «для красоты»: по ней кривая и считается. Второй
       математики (отдельно запись, отдельно ломаная) здесь нет. */
    const { compiled } = compileFormula(rec.expr);
    cur.expr = rec.expr; cur.compiled = compiled; cur.sumNumeric = false;
    cur.sumBreaks = rec.breaks;
    cur.sumGhostTo = rec.ghostTo || 0;
    /* Правый конец собственной области определения записи — тоже узел кривой
       (см. sumLinearRecord). Без него линия обрывается на последнем изломе,
       как только окно шире области. */
    cur.sumDomainTo = rec.domainTo || 0;
  } else {
    const pts = sumPolyline(groups);
    /* Ломаная затыкает ту же дырку у нуля (см. sumPolyline), и помечать её
       надо тем же признаком: иначе у нелинейных групп пунктира не было бы. */
    cur.sumGhostTo = (pts._ghostTo || 0);
    /* У численной суммы область определения кончается там, где кончается сама
       ломаная. Узлами эта ветка не пользуется (изломы найдены приблизительно,
       и доверять им нельзя), но правый конец знать полезно: по нему меряется
       та же проверка, что и у аналитической ветки. */
    cur.sumDomainTo = pts.length ? pts[pts.length - 1][0] : 0;
    cur.expr = 'сумма посчитана по точкам';
    cur.fn = (q) => interpY(pts, q);
    cur.sumNumeric = true;
    // Излом суммарной кривой — там, где очередная группа входит в торговлю.
    let chokeTop = 0;
    groups.forEach(c => { const p = sumChokePrice(c); if (isFinite(p) && p > chokeTop) chokeTop = p; });
    const pTop = Math.max(100, chokeTop * 2);   // тот же собственный диапазон, что у ломаной
    cur.sumBreaks = groups.map(c => {
      const p = sumChokePrice(c);
      if (!isFinite(p) || p <= 0 || p >= pTop) return null;
      let q = 0;
      groups.forEach(g => { q += sumGroupQty(g, p); });
      return q > 1e-9 ? q : null;
    }).filter(v => v != null);
  }
}

/* Подпись входа пересборки: всё, от чего запись суммарных кривых зависит, и
   больше ничего. Формулы групп, сколько их, и значения ползунков-параметров
   (буква в формуле группы меняет её наклон, а значит и сумму). */
function sumSignature() {
  const parts = [];
  ['D', 'S'].forEach(side => {
    const g = sumGroupsOf(side);
    parts.push(side + ':' + g.length + ':' + g.map(c => String(c.expr || '')).join('~'));
  });
  parts.push(paramSignature(Object.keys(STATE.params || {}).sort()));
  return parts.join('|');
}

/* Пересчёт обеих сумм. Зовётся из recompute — то есть на каждой перерисовке.

   ⚠️ ПЕРЕСОБИРАЕМ ТОЛЬКО КОГДА ЕСТЬ ЧТО ПЕРЕСОБИРАТЬ.

   Панорама зовёт redrawAll на каждый кадр мыши, оттуда recompute, оттуда
   сюда — и sumRebuildSide заново собирал строку записи и заново компилировал
   её через Math.js, дважды на кадр. Кэшировать это раньше было нельзя честно:
   запись зависела от CONFIG.Pmax, то есть от границ кадра, и после панорамы
   действительно менялась. Теперь запись — свойство групп (см. sumPriceTop),
   и от движения окна не зависит вовсе, поэтому подписи достаточно. */
function sumRebuild() {
  if (!sumSceneOn()) { STATE._sumSig = null; return; }
  const sig = sumSignature();
  if (sig === STATE._sumSig) return;
  STATE._sumSig = sig;
  sumRebuildSide('D');
  sumRebuildSide('S');
}

/* Ключ кэша аналитики: подпись формул плюс отрезок поиска равновесия.
   Отрезок входит в ключ, потому что от него зависит ответ: сузили область —
   могло пропасть дальнее пересечение. При панорамировании он постоянен
   (см. eqSearchSpan), поэтому кэш там и живёт. */
function sumAnalyticsKey() {
  const D = curveByRole('demand'), S = curveByRole('supply');
  if (!D || !S || !STATE._sumSig) return null;
  return STATE._sumSig + '|' + eqSearchSpan(D, S);
}


/* ── Сборка сцены: сколько групп, такие и поля ────────────────────────
   Порядок работы для человека взят с созвона: сначала СКОЛЬКО групп спроса и
   предложения, потом по полю на каждую. Поля — обычные строки списка кривых,
   поэтому имя правится там же, где и формула, и ничего нового учить не надо. */
const SUM_ORDINAL = ['первой', 'второй', 'третьей', 'четвёртой', 'пятой', 'шестой', 'седьмой', 'восьмой'];
// Учебный набор по умолчанию: у каждой следующей группы своя запретительная цена,
// поэтому суммарная кривая ломается ровно там, где очередная группа входит в торговлю.
const SUM_START_D = [100, 60, 40, 30, 25, 20, 15, 10];   // P = b − Q
const SUM_START_S = [0, 20, 40, 55, 65, 72, 78, 84];     // P = Q + b
const SUM_MAX_GROUPS = 8;

function sumGroupName(side, i) {
  const ord = SUM_ORDINAL[i] || ((i + 1) + '-й');
  return (side === 'D' ? 'спрос ' : 'предложение ') + ord + ' группы';
}

/* ── ОБОЗНАЧЕНИЕ КРИВОЙ НА ХОЛСТЕ (Фаза 3) ────────────────────────────
   На холсте у кривой стоит ОБОЗНАЧЕНИЕ, а полное имя живёт в левой панели.
   Это то же правило, что уже записано для точек: холст и так самый плотный
   объект на экране.

   Замер 25.08: «спрос первой группы» занимает 137 px, «предложение второй
   группы» — 181 px. Три такие подписи выстраивались вдоль нижнего края с
   зазором 7,5 и 9,8 px при внутреннем пробеле шрифта 7,22 — то есть читались
   одной строкой «спрос третьей группы спрос второй группы спрос первой
   группы». На 380 px все шесть вылезали за холст.

   Связь с левой панелью держится тем, что ТО ЖЕ обозначение стоит в строке
   списка перед именем и в подписи ползунка справа. Полное имя никуда не
   девается: оно в панели, в подсказке и в табло по группам.

   Своё имя человека сильнее: переименовал кривую — на холсте его имя, а не
   наше обозначение. Отличаем по совпадению с именем по умолчанию — отдельного
   признака «переименовано» для этого заводить не надо. */
function sumTagOf(c) {
  if (!c || !c.sumGroup) return null;
  if (c.kind === 'sum') return (c.sumGroup === 'D') ? 'D' : 'S';
  const i = c.sumIdx || 0;
  return (c.sumGroup === 'D' ? 'D_' : 'S_') + (i + 1);
}
/* Имя кривой сложения на холсте и в узких местах панелей. */
function sumShortTag(c) {
  if (!sumSceneOn() || !c || !c.sumGroup) return null;
  const def = (c.kind === 'sum')
    ? ((c.sumGroup === 'D') ? 'рыночный спрос' : 'рыночное предложение')
    : sumGroupName(c.sumGroup, c.sumIdx || 0);
  // Человек дал своё имя — оно и идёт, обозначение не спорит с ним.
  if (c.label && c.label !== def) return null;
  return sumTagOf(c);
}

/* ── ЦВЕТ ГРУППЫ (решение владельца 25.08: «свой цвет, но тише») ───────
   Группа берёт цвет из СВОЕЙ палитры, а не из общей палитры выбора.
   Общая начинается с канонических D и S, поэтому «спрос первой группы»
   выходил того же цвета, что «рыночный спрос», а «спрос второй группы» —
   того же, что «рыночное предложение» (замер 25.08: 2 совпадения в наборе
   А, 3 в наборе Б, а при трёх группах ещё и две группы делили один цвет).

   ⚠️ ОБЩУЮ ПАЛИТРУ ВЫБОРА НЕ ТРОГАЕМ. Кривые, которые человек добавляет
   кнопкой, по-прежнему получают цвета из nextColor(): та палитра живёт во
   всех сорока одной сцене, и разделить их — как раз и значит починить
   сложение, ничего больше не сломав.

   Слоты чередуются между семьями: спрос берёт чётные (1, 3, 5, 7),
   предложение — нечётные (2, 4, 6, 8). Так число групп одной стороны можно
   менять, не перекрашивая другую, и при четырёх группах в каждом семействе
   все восемь цветов различны. С пятой группы в семье палитра идёт по
   второму кругу — владелец это принял: «если при пяти-шести станет тесно,
   вернуться к «Сумме против фона». */
const SUM_PALETTE_KEYS = ['sumG1', 'sumG2', 'sumG3', 'sumG4', 'sumG5', 'sumG6', 'sumG7', 'sumG8'];
function sumGroupColor(side, i) {
  const slot = ((side === 'D' ? 2 * i : 2 * i + 1) % SUM_PALETTE_KEYS.length + SUM_PALETTE_KEYS.length)
    % SUM_PALETTE_KEYS.length;
  return COL[SUM_PALETTE_KEYS[slot]] || COL.MR;
}
function sumStartExpr(side, i) {
  if (side === 'D') return fmtLinear(-1, SUM_START_D[i] === undefined ? 20 : SUM_START_D[i], 'Q', 3);
  return fmtLinear(1, SUM_START_S[i] === undefined ? 20 * i : SUM_START_S[i], 'Q', 3);
}

/* Порядок строк в списке: сначала группы спроса и их сумма, затем группы
   предложения и их сумма. Сумма стоит ПОД своими слагаемыми — так же, как в
   столбик на бумаге. */
function sumReorder() {
  const rank = (c) => (c.sumGroup === 'S' ? 1000 : 0) + (c.kind === 'sum' ? 999 : (c.sumIdx || 0));
  STATE.curves.sort((a, b) => rank(a) - rank(b));
}

function sumAddGroup(side, i) {
  addCurve(sumStartExpr(side, i));
  const c = STATE.curves[STATE.curves.length - 1];
  c.sumGroup = side; c.sumIdx = i;
  c.label = sumGroupName(side, i);
  /* Цвет ставим ПОСЛЕ addCurve: та выдала цвет из общей палитры выбора, и
     именно он и был причиной каши. Свой цвет человека (пикер ставит
     colorCustom) здесь ещё неоткуда взяться — кривая только что заведена. */
  c.color = sumGroupColor(side, i);
  return c;
}

// Собрать сцену с нуля под текущие STATE.sumN.
function sumBuildScene() {
  STATE.curves = []; curveCounter = 0;
  ['D', 'S'].forEach(side => {
    const n = Math.max(1, Math.min(SUM_MAX_GROUPS, (STATE.sumN && STATE.sumN[side]) || 2));
    for (let i = 0; i < n; i++) sumAddGroup(side, i);
    /* Суммарная кривая — обычная кривая списка с ролью «спрос»/«предложение».
       Именно поэтому равновесие, излишки, ключевые точки и изломы считает
       общий движок, а не свой особый код. */
    curveCounter++;
    const sum = {
      id: curveCounter, expr: '', compiled: null, fn: null, linear: null,
      color: (side === 'D') ? COL.D : COL.S, role: null, visible: true,
      kind: 'sum', sumGroup: side,
      label: (side === 'D') ? 'рыночный спрос' : 'рыночное предложение',
    };
    STATE.curves.push(sum);
    setRole(sum, (side === 'D') ? 'demand' : 'supply');
  });
  sumReorder();
  /* Сцену собрали заново — суммарные кривые сейчас ПУСТЫЕ, и подпись от
     прошлой сборки совпала бы с новой (набор групп по умолчанию тот же).
     Сбрасываем её явно, иначе кэш вернул бы «пересобирать нечего». */
  STATE._sumSig = null;
  sumRebuild();
  renderCurveList();
}

// Сменить число групп одной стороны, НЕ теряя уже набранные формулы.
function sumSetCount(side, n) {
  if (!sumSceneOn()) return;
  n = Math.max(1, Math.min(SUM_MAX_GROUPS, Math.round(n)));
  if (!isFinite(n)) return;
  STATE.sumN[side] = n;
  const list = STATE.curves.filter(c => c.sumGroup === side && c.kind !== 'sum');
  if (list.length > n) {
    const drop = new Set(list.slice(n));
    STATE.curves = STATE.curves.filter(c => !drop.has(c));
  } else {
    for (let i = list.length; i < n; i++) sumAddGroup(side, i);
  }
  sumReorder();
  sumRebuild();
  renderCurveList();
  redrawAll();
}

// Показать поля «сколько групп» только в своём сюжете и держать их числа честными.
function syncSumUi() {
  const box = document.getElementById('sum-counts');
  if (box) box.style.display = sumSceneOn() ? '' : 'none';
  if (!sumSceneOn()) return;
  [['sum-nd', 'D'], ['sum-ns', 'S']].forEach(([id, side]) => {
    const e = document.getElementById(id);
    if (e && document.activeElement !== e) e.value = STATE.sumN[side];
  });
}

/* ── Аналитика по группам (Фаза 9) ────────────────────────────────────
   При равновесной цене у каждой группы своё количество и свой излишек.
   Сумма излишков групп ОБЯЗАНА совпасть с площадью под суммарной кривой:
   это и есть проверка того, что сложение сделано верно, а не «примерно». */
function sumGroupStats() {
  if (!sumSceneOn() || !STATE.eq) return null;
  /* Табло по группам — та же арифметика по тем же формулам при той же
     равновесной цене, и от кадра оно не зависит. Раз в кадр это пять
     интегралов по тысяче узлов плюс две сверки по кусочной записи (замер
     24.08: 8,6 мс). Считаем на смену формул и цены, а не на движение мыши. */
  const key = STATE._sumSig + '|' + STATE.eq.Q + '|' + STATE.eq.P;
  if (key === STATE._sumStatsKey) return STATE._sumStatsVal;
  const P = STATE.eq.P;
  const side = (which) => sumGroupsOf(which).map(c => {
    const q = sumGroupQty(c, P);
    // Излишек группы — площадь между её кривой и равновесной ценой до q.
    const surplus = (q > 0)
      ? (which === 'D' ? integrateBroken(t => quadPrice(c, t) - P, 0, q, quadBreaks(c, q))
                       : integrateBroken(t => P - quadPrice(c, t), 0, q, quadBreaks(c, q)))
      : 0;
    return { name: curveShortName(c), color: c.color, expr: c.expr, q, surplus };
  });
  const D = side('D'), S = side('S');
  const sum = (arr, k) => arr.reduce((acc, r) => acc + r[k], 0);
  /* Второй путь к тому же числу: интеграл под СУММАРНОЙ кривой. Расхождение
     означает ошибку в сложении, а не в округлении, поэтому оно и печатается. */
  const csWhole = (STATE.D && STATE.eq.Q > 0)
    ? integrateBroken(q => quadPrice(STATE.D, q) - P, 0, STATE.eq.Q, quadBreaks(STATE.D, STATE.eq.Q)) : NaN;
  const psWhole = (STATE.S && STATE.eq.Q > 0)
    ? integrateBroken(q => P - quadPrice(STATE.S, q), 0, STATE.eq.Q, quadBreaks(STATE.S, STATE.eq.Q)) : NaN;
  const out = {
    P, Q: STATE.eq.Q, D, S,
    qD: sum(D, 'q'), qS: sum(S, 'q'),
    csGroups: sum(D, 'surplus'), psGroups: sum(S, 'surplus'),
    csWhole, psWhole,
    csGap: Math.abs(sum(D, 'surplus') - csWhole),
    psGap: Math.abs(sum(S, 'surplus') - psWhole),
  };
  STATE._sumStatsKey = key; STATE._sumStatsVal = out;
  return out;
}


/* Записи обеих суммарных кривых — данными, а не разметкой.

   ⚠️ РАЗМЕТКУ ЗДЕСЬ БОЛЬШЕ НЕ ВЕРСТАЕМ. До 26.08 запись печаталась в
   `#info-sum` внутри `<div class="sb-note">` — и общий проход
   `moveExplanations` уносил её в «Объяснение модели», где по умолчанию
   свёрнуто. Теперь верстает один помощник `setFinalFunctions` (86-workspace.js),
   а сцена только отдаёт ему имя, цвет и саму запись. */
function sumFinalRecords() {
  const one = (side, name) => {
    const c = STATE.curves.find(x => x.kind === 'sum' && x.sumGroup === side);
    if (!c || !c.expr) return null;                 // групп нет — и записи нет
    if (c.sumNumeric) {
      return { name, color: c.color,
               note: 'Среди групп есть непрямая, поэтому сумма посчитана по точкам: '
                   + 'записи по участкам у неё нет.' };
    }
    /* Запись обратная: цена как функция количества, ровно та, по которой
       кривая и считается (одно значение — один источник). Левая часть «P»
       живёт отдельным полем: в expr её нет, потому что expr обязан
       вставляться обратно в поле формулы как есть. */
    return { name, color: c.color, expr: c.expr, lhs: 'P' };
  };
  return [one('D', 'Рыночный спрос $D$'), one('S', 'Рыночное предложение $S$')].filter(Boolean);
}
// Табло «По группам»: количество и излишек каждой группы плюс сумма.
function updateSumPanel() {
  syncSumUi();
  const box = document.getElementById('info-sum');
  if (!box) return;
  if (!sumSceneOn()) { box.innerHTML = ''; return; }
  /* ⚠️ ЗАПИСЬ КРИВОЙ НЕ ЗАВИСИТ ОТ ТОГО, ЕСТЬ ЛИ РАВНОВЕСИЕ. Это свойство
     набора групп, а не точки пересечения: то же правило, по которому кривая
     после вмешательства рисуется на рынке без равновесия. Поэтому итоговые
     функции ставятся ДО проверки на равновесие. */
  if (typeof setFinalFunctions === 'function') setFinalFunctions(sumFinalRecords());
  const st = sumGroupStats();
  if (!st) {
    box.innerHTML = '<div class="muted">Суммарные кривые не пересекаются: равновесия нет.</div>';
    return;
  }
  const rows = (list, title, qSum, sSum, tag) => {
    let h = `<div class="sb-sub">${title}</div>`;
    list.forEach(r => {
      h += `<div class="stat"><span>${r.name}</span><b>${fmt(r.q)}</b></div>`;
    });
    h += `<div class="stat"><span>вместе $Q$</span><b>${fmt(qSum)}</b></div>`;
    list.forEach(r => {
      h += `<div class="stat"><span>${tag} — ${r.name}</span><b>${fmt(r.surplus)}</b></div>`;
    });
    h += `<div class="stat"><span>вместе $${tag}$</span><b>${fmt(sSum)}</b></div>`;
    return h;
  };
  let html = '';
  html += `<div class="stat"><span>Равновесная цена $P^*$</span><b>${fmt(st.P)}</b></div>`;
  /* ⚠️ РАЗБОР ОСТАЛСЯ, ХОТЯ ЗАПИСЬ ИЗ НЕГО УЕХАЛА, И ЭТО НЕ МЕЛОЧЬ.
     Единственной врезкой этой сцены была сама запись; унеся её в «Ключевые
     значения», мы оставили бы «Объяснение модели» пустым — а пустой раскрытый
     блок читается как недоделка (та же беда, что описана в hasAnalytics).
     Величина уехала в табло, объяснение осталось объяснением: здесь сказано,
     ОТКУДА у записи участки, а не какая она. */
  html += '<div class="sb-note"><b>Как это получилось</b>'
        + '<p><b>Почему у рыночной кривой участки?</b> Складываем по горизонтали: '
        + 'при каждой цене берём количество КАЖДОЙ группы и складываем эти количества. '
        + 'Пока цена выше запретительной цены группы, эта группа не торгует вовсе и в '
        + 'сумму не входит; как только цена доходит до неё, группа включается, и наклон '
        + 'рыночной кривой в этот момент меняется. Отсюда и излом, и участки в записи.</p>'
        + '<p>Сама запись стоит первой в «Ключевых значениях», блоком «Итоговая функция»: '
        + 'это посчитанная величина, а не разбор. По ней кривая и рисуется: второй '
        + 'математики здесь нет.</p></div>';
  html += rows(st.D, 'Покупатели по группам', st.qD, st.csGroups, 'CS');
  html += rows(st.S, 'Продавцы по группам', st.qS, st.psGroups, 'PS');
  /* Сходимость двух путей печатается, а не проверяется молча: расхождение
     это ошибка сложения, и человек имеет право её увидеть. */
  const eps = 1e-6;
  const ok = (st.csGap <= eps && st.psGap <= eps);
  html += ok
    ? `<div class="hint">Сумма излишков по группам сошлась с площадью под суммарной кривой: ` +
      `$CS = ${fmt(st.csGroups)}$, $PS = ${fmt(st.psGroups)}$.</div>`
    : `<div class="warn">Сумма по группам разошлась с площадью под суммарной кривой ` +
      `(CS на ${st.csGap.toExponential(2)}, PS на ${st.psGap.toExponential(2)}). Это ошибка сложения, а не округления.</div>`;
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
    const csArea = d3.area().x(d => sx(d)).y0(sy(P)).y1(d => sy(quadPrice(STATE.D, d)));
    g.append('path').datum(samples).attr('d', csArea).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  // PS — между кривой предложения (низ) и ценой P* (верх).
  if (STATE.showPS && STATE.S) {
    const psArea = d3.area().x(d => sx(d)).y0(d => sy(quadPrice(STATE.S, d))).y1(sy(P));
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
  /* Квота — тоже вмешательство. Замер 24.08: при связывающей квоте оговорки
     не было вовсе, и «CS 1 250» в «Излишках» читалось как нынешнее число,
     хотя на деле относилось к рынку без квоты. */
  if (!STATE.taxActive && !pcOn && !STATE.quotaActive) return '';
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

/* НА ЧЬЕЙ СТОРОНЕ ВМЕШАТЕЛЬСТВО — ОДИН ВОПРОС И ОДИН ОТВЕТ НА ВЕСЬ ФАЙЛ.
   Спрашивают его трое: отрисовка сдвинутой кривой, её имя и блок «Итоговая
   функция». Пока ответ считался на месте у каждого, они могли разъехаться —
   и разъехались. */
/* ⚠️ СТОРОНА ЧИТАЕТСЯ У ОБОИХ ВИДОВ ВМЕШАТЕЛЬСТВА, А НЕ ТОЛЬКО У НАЛОГА.
   Здесь стояло `STATE.intervType === 'tax' && …`, и у субсидии сторона не
   читалась вовсе: переключатель «Субсидию получает: Покупатель» на графике
   не менял ничего (замер 26.08 — сдвинутой по-прежнему рисовалась S − s).
   У процентных форм сторона закреплена самой формой (`setTaxForm` ставит
   `taxSide = 'seller'` при `pctForm()`), поэтому лишнего здесь не сработает. */
function intervOnBuyer() {
  const rate = (STATE.intervType === 'tax' || STATE.intervType === 'subsidy');
  return rate && STATE.taxSide === 'buyer';
}

// Сдвинутая пунктиром кривая. При налоге на ПРОДАВЦА (по умолчанию) и при субсидии
// двигается предложение (S ± ставка). При налоге на ПОКУПАТЕЛЯ (Задача 1) двигается
// спрос вниз (D − t): эффективный спрос. Итоговые числа в обоих случаях идентичны —
// меняется только то, какую кривую рисуем; считаем в recompute одинаково.
function drawShiftedSupply() {
  /* По признаку «кривая после вмешательства построена», а не «числа сошлись».
     Прежде здесь стоял STATE.taxActive, и на рынке без равновесия кривая не
     рисовалась вовсе — хотя сдвиг и поворот равновесия не спрашивают. */
  if (!STATE.taxCurveOn) return;
  const buyerTax = intervOnBuyer();
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
  const pf = pctForm();
  const isSub = (STATE.intervType === 'subsidy');
  // Имя сдвинутой кривой берём из той же строки таблицы, что и её множитель:
  // иначе на графике оказалась бы подпись от другой формы.
  /* Имя сдвинутой кривой: у субсидии покупателю это D + s, а не D − t.
     Знак у обеих сторон один и тот же — налог опускает, субсидия поднимает. */
  const nm = buyerTax ? (pf ? pf.curveD : (isSub ? 'D + s' : 'D − t'))
                      : (pf ? pf.curve : (isSub ? 'S − s' : 'S + t'));
  labelCurve(g, q => evalCurve(after, q), nm, base.color, { from: 0.82 });
}

/* ⚠️ ЦЕНТР ПОВОРОТА ПРИ ПРОЦЕНТНОМ ВМЕШАТЕЛЬСТВЕ (рис. 81 учебника Бахарева).

   S_после = factor·S, поэтому обе кривые обращаются в ноль ровно при одном и
   том же Q: там, где ноль исходное предложение. Эта общая точка на оси Q и
   есть центр, вокруг которого поворот происходит, и она объясняет, ПОЧЕМУ
   поворот именно такой, а не какой-нибудь другой.

   ⚠️ ПРОДОЛЖЕНИЕ РИСУЕТСЯ НЕ ВСЕГДА. Если центр лежит ВНУТРИ первой четверти
   (S пересекает ось Q при Q ≥ 0, как у S = Q или S = Q − 100), показывать
   нечего: обе кривые и так приходят в эту точку на глазах. Продолжение имеет
   смысл только когда центр ушёл влево за ось цен.

   ⚠️ ГАЛОЧКА «ТОЛЬКО ПЕРВАЯ ЧЕТВЕРТЬ» ЗДЕСЬ НИ ПРИ ЧЁМ — ровно как у
   продолжения предельной кривой (30-curves.js). Рисуем всегда; при включённой
   галочке прямоугольный clip-path режет холст по оси цен, и продолжение просто
   не попадает на экран. Условие «рисовать только при снятой галочке» дало бы то
   же самое на экране, но добавило бы вторую точку правды. */
function taxPivotQ() {
  const S = STATE.S;
  if (!S || (typeof isVertical === 'function' && isVertical(S))) return null;
  // Прямая: перехват считается формулой, без всякой сетки.
  const l = S.linear;
  if (l && isFinite(l.a) && isFinite(l.b) && Math.abs(l.a) > 1e-12) {
    const z = -l.b / l.a;
    return isFinite(z) ? z : null;
  }
  // Кривая: ищем смену знака слева от нуля и уточняем половинным делением.
  const span = Math.max(CONFIG.Qmax, 1) * 4;
  const N = 400;
  let prev = evalCurve(S, -span), best = null;
  for (let i = 1; i <= N; i++) {
    const q = -span + span * i / N;
    const cur = evalCurve(S, q);
    if (!isNaN(prev) && !isNaN(cur) && prev * cur <= 0 && prev !== cur) {
      let a = -span + span * (i - 1) / N, b = q;
      for (let k = 0; k < 50; k++) {
        const m = (a + b) / 2, v = evalCurve(S, m);
        if (isNaN(v)) break;
        if (evalCurve(S, a) * v <= 0) b = m; else a = m;
      }
      best = (a + b) / 2;
    }
    prev = cur;
  }
  return best;
}

// Центр поворота, если его есть смысл показывать; иначе null.
function taxPivotPoint() {
  // Центр поворота — свойство пары кривых, а не найденного равновесия.
  if (!STATE.taxCurveOn || !pctForm() || !STATE.S || !STATE.taxAfterS) return null;
  const q = taxPivotQ();
  if (q == null || !(q < -1e-9)) return null;   // ноль или правее — показывать нечего
  return { Q: q, P: 0 };
}

// Пунктирные продолжения обеих кривых предложения вниз-влево к центру поворота.
function drawTaxPivot() {
  const p = taxPivotPoint();
  if (!p) return;
  const g = svg.append('g').attr('class', 'pivot').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const color = (STATE.S && STATE.S.color) || COL.S;
  const N = 160;
  [STATE.S, STATE.taxAfterS].forEach((c, idx) => {
    const pts = [];
    for (let i = 0; i <= N; i++) {
      const q = p.Q + (0 - p.Q) * i / N;
      const v = evalCurve(c, q);
      pts.push(isFinite(v) ? [q, v] : null);
    }
    /* Продолжение отличается от самой кривой толщиной и прозрачностью, а не
       штрихом: S_после и так уже пунктирная, и одним штрихом их не развести —
       тот же урок, что у продолжения предельной кривой. */
    g.append('path').datum(pts)
      .attr('fill', 'none').attr('stroke', color)
      .attr('stroke-width', 1.1).attr('stroke-dasharray', '5 4').attr('opacity', 0.5)
      .attr('data-pivot', String(idx + 1))
      .attr('d', line);
  });
  // Сама точка центра — маленький кружок, без имени и без чисел у осей: это
  // построение, а не значение модели.
  const [qa, qb] = sx.domain(), [pa, pb] = sy.domain();
  if (p.Q >= qa && p.Q <= qb && p.P >= pa && p.P <= pb) {
    const [px, py] = toPx(p.Q, p.P);
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 3.2)
      .attr('fill', 'none').attr('stroke', color).attr('stroke-width', 1.4)
      .attr('opacity', 0.75).attr('data-pivot', 'dot');
  }
}

// Заливки сценария вмешательства: CS, PS, деньги бюджета (прямоугольник), DWL (потери).
function drawTaxAreas() {
  if (!STATE.taxActive) return;
  const { Q, Pb, Ps } = STATE.taxEq;
  /* Исходного равновесия может не быть вовсе (без вмешательства кривые
     пересекаются вне первой четверти). Тогда заливки излишков и денег
     бюджета рисуются как обычно — они считаются по НОВОМУ равновесию, — а
     области потерь нет: у неё второго края нет. */
  const Q0 = STATE.eq ? STATE.eq.Q : null;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const s1 = samp(0, Q);

  if (STATE.showCS) {   // CS: между ценой покупателя Pb и спросом
    const a = d3.area().x(d => sx(d)).y0(sy(Pb)).y1(d => sy(quadPrice(STATE.D, d)));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  if (STATE.showPS) {   // PS: между предложением и ценой продавца Ps
    const a = d3.area().x(d => sx(d)).y0(d => sy(quadPrice(STATE.S, d))).y1(sy(Ps));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16).attr('data-legend', 'Излишек продавца (PS)');
  }
  // Деньги бюджета (сбор налога / расход на субсидию) — прямоугольник между Pb и Ps
  // на [0, Q1]. По фиксированной палитре налог/субсидия/бюджет — один зелёный цвет.
  const lowP = Math.min(Pb, Ps), highP = Math.max(Pb, Ps);
  const aTx = d3.area().x(d => sx(d)).y0(sy(lowP)).y1(sy(highP));
  g.append('path').datum(s1).attr('d', aTx)
    .attr('fill', COL.tax).attr('opacity', 0.22).attr('data-legend', STATE.intervType === 'subsidy' ? 'Расход бюджета' : 'Сбор бюджета');
  // DWL — между D и S на интервале между старым и новым Q (налог: [Q1,Q0]; субсидия: [Q0,Q1]).
  const lo = (Q0 == null) ? 0 : Math.min(Q, Q0), hi = (Q0 == null) ? 0 : Math.max(Q, Q0);
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
  /* Подпись клина. У процентных форм ставка — доля, и писать её без знака
     процента нельзя: «t=50» рядом с рублёвой осью читается как 50 рублей,
     а это не так (решение владельца «ставка только в процентах»). */
  const yMid = (yPb + yPs) / 2;
  const unit = rateUnit();
  haloText(g, xQ1 + 16, yMid, rateLetter() + '=' + fmt(STATE.tax) + (unit ? ' ' + unit : ''),
           'start', 'middle');
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
  /* Предел спрашиваем у МОДЕЛИ, а не у атрибута ползунка: формулу правят
     после того, как каскад расставил границы, и атрибут остаётся от прежних
     кривых. Ползунку и полю тут же выправляем max — иначе набранное число
     проходит, а ручка стоит в упоре. */
  const pf = pctForm();
  const maxT = pf ? (parseFloat(slider && slider.max) || PCT_MAX_FREE) : unitRateMax();
  if (!pf) ['tax-slider', 'tax-input'].forEach(id => {
    const e = document.getElementById(id); if (e) e.max = maxT;
  });
  t = Math.max(0, Math.min(t, maxT));
  STATE.tax = t;
  if (slider) slider.value = t;                        // ползунок (step=1, целые)
  const lbl = document.getElementById('tax-val');
  if (lbl) lbl.textContent = fmt(t);
  const inp = document.getElementById('tax-input');
  if (inp) inp.value = fmtInput(t);                         // числовое поле (точное)
  redrawAll();
}

/* ---------------------------------------------------------------------
   КАСКАД ВЫБОРА ВМЕШАТЕЛЬСТВА (ночная сессия «вмешательство государства»).
   Уровни идут строго сверху вниз, и следующий появляется ТОЛЬКО после
   предыдущего — все сразу на экране не показываются никогда:
     1) вид вмешательства: налог / субсидия / потолок / пол;
     2) вид налога (потоварный / НДС / акциз) либо вид субсидии
        (потоварная / процентная);
     3) кто формально платит потоварный налог (у НДС и акциза плательщик
        закреплён законом, поэтому уровня нет);
     4) кому достаётся субсидия;
     5) само значение — ставка или регулируемая цена.
   Ветка налога и ветка субсидии никогда не видны одновременно.
   --------------------------------------------------------------------- */

/* ⚠️ ЧЕТЫРЕ ПРОЦЕНТНЫЕ ФОРМЫ ЖИВУТ ОДНОЙ ТАБЛИЦЕЙ, А НЕ ЧЕТЫРЬМЯ ВЕТКАМИ.

   Раньше процентных форм было две (НДС и «процентная субсидия»), и обе были
   вписаны прямо в расчёт условными выражениями. Акциз при этом проваливался
   в потоварную ветку: замер набора Э давал у него точку (35; 85/35) вместо
   (40; 80/40) — то есть он сдвигал кривую на 50 рублей вместо поворота.
   Стоило добавить второй вид субсидии, и таких веток стало бы четыре, каждая
   со своим множителем, своим пределом ставки и своей подписью.

   Поэтому форма описывается ОДНОЙ строкой таблицы, а расчёт, отрисовка,
   пределы ползунка, подсказка и разбор читают её поля. Основание — учебник
   Бахарева, глава «Налоги и субсидии», раздел «Акцизный налог и НДС»
   (рис. 81, 83, 84) и решение владельца «два вида процентной субсидии».

     Форма                       Кривая после   Соотношение цен   Деньги    Предел
     Акциз (от цены покупателя)  S/(1−t)        Ps = (1−t)·Pd     t·Pd·Q    t < 100 %
     НДС (от цены продавца)      S·(1+t)        Ps = Pd/(1+t)     t·Ps·Q    без верха
     Субсидия от цены покупателя S/(1+t)        Ps = (1+t)·Pd     t·Pd·Q    без верха
     Субсидия от цены продавца   S·(1−t)        Ps = Pd/(1−t)     t·Ps·Q    t < 100 %

   Симметрия ровная: налог поднимает кривую предложения, субсидия опускает;
   предел «меньше ста процентов» стоит там, где иначе цена одной из сторон
   обратилась бы в ноль (делитель 1 − t).

   ⚠️ ДЕНЬГИ СЧИТАЮТСЯ ОДНОЙ ФОРМУЛОЙ НА ВСЕ ЧЕТЫРЕ: (Pd − Ps)·Q. Столбец
   «Деньги» — не второй способ счёта, а тождество, и прибор его проверяет
   до последнего знака. Ps всегда равно Pd/factor, поэтому
   (Pd − Pd/factor)·Q сводится ровно к строке таблицы. Разошлись — это ошибка
   формулы, а не округление.

   Поля строки:
     type    — при каком вмешательстве форма доступна;
     label   — подпись кнопки каскада (уровень 2);
     factor  — множитель кривой предложения: S_после(Q) = factor·S(Q);
     capped  — ставка обязана быть строго меньше 100 %;
     curve   — как назвать сдвинутую кривую на графике;
     curveTex/priceTex/moneyTex — кривая, соотношение цен и деньги формулой
               для «Объяснения модели» (набираются KaTeX, а не обычным текстом);
     hint    — подсказка под ползунком ставки. */
const PCT_FORMS = {
  excise:    { type: 'tax',     label: 'Акциз',              base: 'buyer',
               factor: t => 1 / (1 - t), capped: true,  curve: 'S/(1−τ)', curveD: 'D·(1−τ)',
               curveTex: '\\dfrac{S(Q)}{1-\\tau}',
               priceTex: 'P_s = (1-\\tau)\\cdot P_d', moneyTex: 'T = \\tau\\cdot P_d\\cdot Q',
               hint: 'Акциз берётся долей от цены ПОКУПАТЕЛЯ: продавцу остаётся ' +
                 'P<sub>s</sub>&nbsp;=&nbsp;(1−τ)·P<sub>b</sub>. Предложение не сдвигается, а ' +
                 '<b>поворачивается</b>: S<sub>после</sub>(Q)&nbsp;=&nbsp;S(Q)/(1−τ). Сбор равен ' +
                 'τ·P<sub>b</sub>·Q. Ставка строго меньше 100 %: при ста продавцу не осталось бы ничего.' },
  vat:       { type: 'tax',     label: 'НДС',                base: 'seller',
               factor: t => 1 + t,       capped: false, curve: 'S·(1+τ)', curveD: 'D/(1+τ)',
               curveTex: '(1+\\tau)\\cdot S(Q)',
               priceTex: 'P_s = \\dfrac{P_d}{1+\\tau}', moneyTex: 'T = \\tau\\cdot P_s\\cdot Q',
               hint: 'НДС берётся долей от цены ПРОДАВЦА и начисляется сверх неё: ' +
                 'P<sub>b</sub>&nbsp;=&nbsp;P<sub>s</sub>·(1+τ). Предложение не сдвигается, а ' +
                 '<b>поворачивается</b>: S<sub>после</sub>(Q)&nbsp;=&nbsp;(1+τ)·S(Q). Сбор равен ' +
                 'τ·P<sub>s</sub>·Q. Верхнего предела у ставки нет.' },
  subbuyer:  { type: 'subsidy', label: '% от цены покупателя', base: 'buyer',
               factor: t => 1 / (1 + t), capped: false, curve: 'S/(1+τ)', curveD: 'D·(1+τ)',
               curveTex: '\\dfrac{S(Q)}{1+\\tau}',
               priceTex: 'P_s = (1+\\tau)\\cdot P_d', moneyTex: 'G = \\tau\\cdot P_d\\cdot Q',
               hint: 'Зеркало акциза: субсидия считается долей от цены ПОКУПАТЕЛЯ, продавец ' +
                 'получает P<sub>s</sub>&nbsp;=&nbsp;(1+τ)·P<sub>b</sub>. Предложение ' +
                 '<b>поворачивается</b> вниз: S<sub>после</sub>(Q)&nbsp;=&nbsp;S(Q)/(1+τ). Расход ' +
                 'бюджета равен τ·P<sub>b</sub>·Q. Верхнего предела у ставки нет.' },
  subseller: { type: 'subsidy', label: '% от цены продавца',  base: 'seller',
               factor: t => 1 - t,       capped: true,  curve: 'S·(1−τ)', curveD: 'D/(1−τ)',
               curveTex: '(1-\\tau)\\cdot S(Q)',
               priceTex: 'P_s = \\dfrac{P_d}{1-\\tau}', moneyTex: 'G = \\tau\\cdot P_s\\cdot Q',
               hint: 'Зеркало НДС: субсидия считается долей от цены ПРОДАВЦА, покупатель платит ' +
                 'P<sub>b</sub>&nbsp;=&nbsp;P<sub>s</sub>·(1−τ). Предложение <b>поворачивается</b> ' +
                 'вниз: S<sub>после</sub>(Q)&nbsp;=&nbsp;(1−τ)·S(Q). Расход бюджета равен ' +
                 'τ·P<sub>s</sub>·Q. Ставка строго меньше 100 %: при ста покупатель платил бы ноль.' },
};

/* Верхняя граница процентной ставки у форм с делителем (1 − τ). Строго меньше
   ста: ровно при ста цена одной из сторон обращается в ноль, а кривая после
   вмешательства — в вертикаль. Число целое, чтобы ползунок с шагом 1 доезжал
   до него ровно, а не останавливался за полшага. */
const PCT_CAP = 99;
const PCT_MAX_FREE = 200;   // предел у форм без верхней границы (как было у НДС)

/* Какая форма выбрана СЕЙЧАС. Каскад хранит выбор человека двумя полями —
   taxForm у налога и subKind у субсидии, — и одно из них действует. */
function taxFormKey() {
  return (STATE.intervType === 'subsidy') ? STATE.subKind : STATE.taxForm;
}

/* Строка таблицы для текущей формы либо null, если форма потоварная.
   ⚠️ Строка обязана СОВПАСТЬ по типу вмешательства: при переключении
   налог ↔ субсидия второе поле остаётся прежним, и без этой проверки
   «акциз» дожил бы до субсидии, а множитель 1/(1−τ) оказался бы налоговым. */
function pctForm() {
  const f = PCT_FORMS[taxFormKey()];
  return (f && f.type === STATE.intervType) ? f : null;
}

// STATE.taxKind — производная величина: математике важно только «сдвиг или
// поворот». Каскад же хранит выбор человека (taxForm / subKind), и эта
// функция сводит одно к другому в единственном месте.
function syncTaxKind() {
  STATE.taxKind = pctForm() ? 'advalorem' : 'unit';
}

// Показать ровно те уровни каскада, которые заслужены сделанным выбором.
function applyIntervCascade() {
  const type = STATE.intervType;
  const comp = (STATE.market !== 'monopoly');
  const isRate = (type === 'tax' || type === 'subsidy');
  const isQuota = (type === 'quota');
  const isPrice = (type === 'ceiling' || type === 'floor');
  const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? '' : 'none'; };
  // Уровень 5 — значение: ставка у налога/субсидии, цена у потолка/пола,
  // объём у квоты (и вслед за ним — выбор цены внутри коридора).
  show('tax-field', isRate);    show('tax-hint', isRate);
  show('pc-field', isPrice);    show('pc-hint', isPrice);
  show('quota-field', isQuota); show('quota-hint', isQuota);
  // Ползунок цены появляется ТОЛЬКО когда коридор существует: квота задана и
  // связывает. Пока квоты нет или она не связывает, выбирать нечего.
  show('quota-price-field', isQuota && !!STATE.quotaActive);
  if (isQuota) updateQuotaPriceLabel();

  // Уровень 2 — вид налога / вид субсидии. Только в конкуренции: в монополии
  // налог входит в MC (monopolyTax), процентная форма туда не переносится.
  /* Уровень 2 — вид налога / вид субсидии. Ряд ОДИН на оба случая, и кнопок
     в нём теперь три и там, и там: у процентных форм две базы — цена
     покупателя и цена продавца, — и по решению владельца обе есть и у налога
     (акциз и НДС), и у субсидии. Кнопки разложены ПО БАЗЕ, а не по названию:
     tk-vat — форма от цены продавца, tk-exc — от цены покупателя. Так пара
     «акциз ↔ субсидия от цены покупателя» стоит на одном месте каскада. */
  const isSub = (type === 'subsidy');
  show('taxkind-row', isRate && comp);
  const kl = document.getElementById('taxkind-label');
  if (kl) kl.textContent = isSub ? 'Вид субсидии:' : 'Вид налога:';
  const bU = document.getElementById('tk-unit');
  if (bU) bU.textContent = isSub ? 'Потоварная' : 'Потоварный';
  const seller = isSub ? 'subseller' : 'vat';      // форма от цены ПРОДАВЦА
  const buyer  = isSub ? 'subbuyer'  : 'excise';   // форма от цены ПОКУПАТЕЛЯ
  const form = taxFormKey();
  [['tk-unit', 'unit'], ['tk-vat', seller], ['tk-exc', buyer]].forEach(([id, k]) => {
    const b = document.getElementById(id);
    if (!b) return;
    b.style.display = '';
    if (k !== 'unit') b.textContent = PCT_FORMS[k].label;
    b.classList.toggle('active', form === k);
  });

  /* Уровень 3 (потоварный налог) и уровень 4б (субсидия): сторона.
     У процентных форм плательщик и получатель закреплены самой формой
     (доля от чьей цены берётся), поэтому ряда стороны у них нет — ни у
     налога, ни теперь у субсидии. */
  const sideOn = comp && !pctForm() && (type === 'tax' || isSub);
  show('taxside-row', sideOn);
  const sl = document.getElementById('taxside-label');
  if (sl) sl.textContent = isSub ? 'Субсидию получает:' : 'Налог платит:';
  // Подсказка — такой же уровень каскада, как всё остальное здесь.
  syncTaxHint();
}

/* Уровень 2 каскада: вид налога ('unit' | 'vat' | 'excise') или вид субсидии
   ('unit' | 'subseller' | 'subbuyer').

   ⚠️ СТАРЫЕ ИМЕНА ОСТАЮТСЯ РАБОЧИМИ. У субсидии процентный вид назывался
   'percent' и означал ровно нынешний 'subbuyer' (кривая S/(1+τ), замер 24.08:
   Q 72, Pd 48, Ps 72, расход 1728). Готовые сцены и тесты зовут его прежним
   словом, поэтому 'percent' и 'advalorem' переводятся сюда, а не отвергаются.

   ⚠️ СТАВКА ПРИ СМЕНЕ ВИДА ОБНУЛЯЕТСЯ (решение владельца). Пересчитывать её
   в «эквивалентную» нельзя: эквивалент зависит от самих кривых и прыгал бы
   при каждой правке формулы. Обнуление — только когда вид ДЕЙСТВИТЕЛЬНО
   сменился: повторный щелчок по уже выбранной кнопке ставку не сбрасывает. */
function setTaxForm(form) {
  const was = taxFormKey();
  if (STATE.intervType === 'subsidy') {
    const alias = (form === 'vat' || form === 'percent' || form === 'advalorem') ? 'subbuyer' : form;
    STATE.subKind = (alias === 'subbuyer' || alias === 'subseller') ? alias : 'unit';
  } else {
    STATE.taxForm = (form === 'vat' || form === 'excise') ? form : 'unit';
  }
  // У процентных форм плательщик закреплён самой формой — сторона к продавцу.
  if (pctForm()) STATE.taxSide = 'seller';
  syncTaxKind();
  applyIntervCascade();
  setTaxSideButtons();
  applyTaxRateBounds();
  setTax(taxFormKey() === was ? STATE.tax : 0);
}

// Переключение типа вмешательства: налог <-> субсидия <-> потолок <-> пол.
function setType(type) {
  STATE.intervType = type;
  const map = { tax: 'seg-tax', subsidy: 'seg-sub', ceiling: 'seg-ceil', floor: 'seg-floor', quota: 'seg-quota' };
  Object.values(map).forEach(id => {
    const b = document.getElementById(id); if (b) b.classList.remove('active');
  });
  const ab = document.getElementById(map[type]); if (ab) ab.classList.add('active');

  const isTax = (type === 'tax' || type === 'subsidy');
  syncTaxKind();          // taxKind зависит от того, налог сейчас или субсидия
  applyIntervCascade();   // уровни каскада: что показать, что спрятать
  setTaxSideButtons();

  if (isTax) {
    applyTaxRateBounds();   // подпись ставки (t / s / τ,%) и пределы ползунка
  } else if (type === 'quota') {
    /* Единый механизм: выбрал вид — его настройка появилась уже рабочей.
       Пустая квота показывала бы обычное равновесие и «задайте объём», то есть
       выбор вида ничего не менял бы на графике. Стартуем связывающей квотой
       в четырёх пятых равновесного объёма — коридор виден сразу. */
    if (!(STATE.quota > 0) && STATE.eq && STATE.eq.Q > 0) {
      STATE.quotaPos = 0.5;
      setQuotaFields(Math.round(STATE.eq.Q * 0.8 * 10) / 10);
    }
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

/* --- Пределы и подпись ставки: рубли у потоварной формы, проценты у четырёх
       процентных ------------------------------------------------------------

   ⚠️ У ПРОЦЕНТНЫХ ФОРМ СТАВКА ЗАДАЁТСЯ И ПОКАЗЫВАЕТСЯ ТОЛЬКО В ПРОЦЕНТАХ
   (решение владельца). Записи величины в деньгах у них не остаётся нигде:
   ни в поле ввода, ни в подписи ползунка, ни в «Ключевых значениях», ни
   в выгрузке. Отсюда и буква «τ, %», и предел не от масштаба цены. */
/* Буква ставки и её единица — ОДНА точка правды на панель, ленту регуляторов
   и подпись клина. Раньше буква жила в разметке, а лента подставляла свою «t»,
   и ставка акциза 50 % читалась в ленте как 50 рублей. */
function rateLetter() {
  if (pctForm()) return 'τ';
  return (STATE.intervType === 'subsidy') ? 's' : 't';
}
function rateUnit() { return pctForm() ? '%' : ''; }

/* Верхняя граница ПОТОВАРНОЙ ставки — свойство МОДЕЛИ, а не кадра.

   Стояло `CONFIG.Pmax`, то есть край видимого окна. У рынка D = 100 − P,
   S = 0,5·p − 200 окно подбирается по спросу и уходит до ста, а осмысленная
   субсидия там начинается с трёхсот (ниже неё рынок так и не появляется).
   Ползунок останавливался на сотне, и нужное число нельзя было даже набрать —
   ровно та же болезнь «ядро смотрит на кадр», что уже вылечена у поиска
   равновесия и у findRoot.

   Берём масштаб цен самой модели: цену каждой кривой при нулевом количестве
   (для параллельного сдвига важна именно она), полтора запаса сверху и
   округление до круглого числа. Кадр остаётся нижней границей — сузить
   прежний предел эта правка не может ни в одном случае. */
function unitRateMax() {
  let far = 0;
  [STATE.D, STATE.S].forEach(c => {
    if (!c) return;
    const v = evalCurve(c, 0);
    if (isFinite(v) && Math.abs(v) > far) far = Math.abs(v);
  });
  if (!(far > 0)) return CONFIG.Pmax;
  return Math.max(CONFIG.Pmax, niceMax(far * 1.5));
}

function applyTaxRateBounds() {
  const pf = pctForm();
  // Верхняя граница: у форм с делителем (1 − τ) — строго меньше ста, у
  // остальных процентных — как было у НДС, у потоварной — масштаб цен модели.
  const max = pf ? (pf.capped ? PCT_CAP : PCT_MAX_FREE) : unitRateMax();
  ['tax-slider', 'tax-input'].forEach(id => { const e = document.getElementById(id); if (e) e.max = max; });
  const rl = document.getElementById('rate-letter');
  if (rl) rl.textContent = rateLetter();
  // Единица стоит справа от ЧИСЛА, а не рядом с буквой: «Ставка τ = 50 %»
  // читается как процент, «Ставка τ, % = 50» — как непонятно что.
  const ru = document.getElementById('rate-unit');
  if (ru) ru.textContent = rateUnit() ? ' %' : '';
}

/* ⚠️ ПОДСКАЗКА ГОВОРИТ ПРО ТУ КРИВУЮ, КОТОРАЯ СЕЙЧАС ДВИГАЕТСЯ.
   Текст был постоянным — «на стороне производителя: кривая S сдвигается», — и
   при выборе «Субсидию получает: Покупатель» он врал вместе с графиком
   (замер 26.08). Собирается здесь, вместе с остальным каскадом, поэтому
   меняется вслед за стороной, а не живёт своей жизнью. */
/* ⚠️ ПОДСКАЗКА КВОТЫ ЗАВИСИТ ОТ СТРОЕНИЯ РЫНКА, А НЕ ТОЛЬКО ОТ ВИДА
   ВМЕШАТЕЛЬСТВА. В разметке лежит текст конкурентного рынка — про коридор
   возможных цен и про то, что цену внутри него выбирает человек. В монополии
   он прямо ВРЁТ: коридора там нет, цену назначает монополист и берёт верхний
   край. На приёмке 31.08 этот текст стоял под связывающей квотой в монополии
   рядом с таблицей, где никакого коридора не было. */
const QUOTA_HINT_COMP =
  'Квота ограничивает объём напрямую. Если она НИЖЕ равновесного количества, рыночная цена '
  + 'не определена однозначно: подойдёт любая цена от той, по которой продавцы готовы отдать '
  + 'этот объём, до той, по которой покупатели готовы его выбрать. Двигайте цену внутри '
  + 'коридора: излишки перетекают между сторонами, а их сумма и потери общества не меняются.';
const QUOTA_HINT_MONO =
  'Квота ограничивает выпуск сверху и связывает, только если она НИЖЕ монопольного выпуска. '
  + 'Коридора цен здесь нет: цену назначает сам монополист и берёт верхний край, то есть '
  + 'максимальную цену, по которой разрешённый объём ещё выбирают. Квота монополисту '
  + 'невыгодна: его излишек падает, а потери общества растут.';
function syncQuotaHint() {
  const h = document.getElementById('quota-hint');
  if (!h) return;
  h.textContent = (STATE.market === 'monopoly') ? QUOTA_HINT_MONO : QUOTA_HINT_COMP;
}

function syncTaxHint() {
  syncQuotaHint();
  const h = document.getElementById('tax-hint');
  if (!h) return;
  const pf = pctForm();
  if (pf) { h.innerHTML = pf.hint; return; }
  const isSub = (STATE.intervType === 'subsidy');
  const onBuyer = intervOnBuyer();
  // Вверх: налог продавцу и субсидия покупателю. Вниз: налог покупателю и
  // субсидия продавцу. Одним признаком — совпали ли «субсидия» и «покупатель».
  const up = (isSub === onBuyer);
  const what = isSub ? 'субсидия' : 'налог';
  const who = onBuyer ? 'покупателя' : 'производителя';
  const curve = onBuyer ? 'кривая спроса D' : 'кривая предложения S';
  const sign = onBuyer ? (isSub ? 'D + s' : 'D − t') : (isSub ? 'S − s' : 'S + t');
  h.innerHTML = 'Потоварн' + (isSub ? 'ая ' : 'ый ') + what + ' на стороне ' + who
    + ': ' + curve + ' <b>сдвигается</b> ' + (up ? 'вверх' : 'вниз')
    /* ⚠️ БЕЗ ДЛИННОГО ТИРЕ: в калькуляторе оно запрещено (проверка
       «в интерфейсе нет длинных тире» в calc2_ui.mjs). */
    + ' на величину ставки (' + sign + '). Объём и цены от выбора стороны не меняются: '
    + 'меняется только то, какую кривую мы рисуем сдвинутой. '
    + 'Клин между ценами покупателя и продавца можно тянуть мышью.';
}

/* Старый вход «вид ставки» ('unit' | 'advalorem'). Оставлен рабочим: на него
   завязаны готовые сцены и контрольные числа. Переводит математический вид
   в выбор каскада: у налога это НДС, у субсидии — «% от цены покупателя»
   ('subbuyer'), потому что прежний единственный процентный вид субсидии был
   именно им, и менять его смысл задним числом нельзя. */
function setTaxKind(kind) {
  const adv = (kind === 'advalorem');
  setTaxForm(adv ? (STATE.intervType === 'subsidy' ? 'subbuyer' : 'vat') : 'unit');
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
  const isSub = (STATE.intervType === 'subsidy');
  /* ИТОГОВАЯ ФУНКЦИЯ — кривая ПОСЛЕ вмешательства. Условие то же, что у её
     отрисовки (`taxCurveOn`), а не «нашлось ли новое равновесие»: сдвиг и
     поворот кривой равновесия не спрашивают. Источник записи один и тот же —
     `texExpr`, посчитанный в recompute рядом с самой функцией. */
  if (typeof setFinalFunctions === 'function') {
    const onBuyer = intervOnBuyer();
    const after = onBuyer ? STATE.taxAfterD : STATE.taxAfterS;
    const base = onBuyer ? STATE.D : STATE.S;
    if (STATE.taxCurveOn && after && after.texExpr && base) {
      const what = onBuyer ? 'Спрос' : 'Предложение';
      const tag = onBuyer ? "$D'$" : "$S'$";
      setFinalFunctions([{
        name: what + ' после ' + (isSub ? 'субсидии' : 'налога') + ' ' + tag,
        color: base.color, lhs: 'P', expr: after.texExpr,
      }]);
    } else {
      setFinalFunctions([]);
    }
  }
  if (!STATE.taxActive) {
    /* Ставка задана, кривая после вмешательства построена, а рынка всё равно
       нет: спрос и новое предложение не пересеклись в первой четверти.
       Говорим об этом здесь, потому что блок равновесия рассказывает про
       ИСХОДНЫЕ кривые и про вмешательство ничего не знает. */
    if (!STATE.eq) {
      box.innerHTML = STATE.taxCurveOn
        ? `<div class="muted">Кривая после вмешательства построена и на графике видна, но со спросом она
           по-прежнему не пересекается в первой четверти: рынка нет, и считать пока нечего.</div>`
        : '';
      return;
    }
    box.innerHTML = `<div class="muted">Двигайте ползунок или тяните клин на графике, чтобы ввести ${isSub ? 'субсидию' : 'налог'}.</div>`;
    return;
  }
  const e0 = STATE.eq, te = STATE.taxEq;
  /* ⚠️ СТОЛБЦА «ДО» НЕТ, КОГДА ДО НИЧЕГО НЕ БЫЛО.
     Исходного равновесия в первой четверти не существовало (обычный случай:
     без вмешательства кривые пересекаются вне четверти, а с ним — внутри).
     Ставить в столбец «До» нуль нельзя: нуль это число, и читался бы он как
     «раньше торговали ноль», хотя правда другая — рынка не было вовсе. По той
     же причине из таблицы уходят DWL и обе строки бремени: и площадь потерь,
     и бремя считаются РАЗНОСТЬЮ с исходным состоянием. */
  const noBase = !e0;
  const rows = noBase ? [
    ['Q', te.Q],
    ['P покупателя', te.Pb],
    ['P продавца', te.Ps],
    ['CS', STATE.csTax],
    ['PS', STATE.psTax],
    [isSub ? 'Бюджет (расход)' : 'Бюджет (сбор)', STATE.budget],
  ] : [
    ['Q', e0.Q, te.Q],
    ['P покупателя', e0.P, te.Pb],
    ['P продавца', e0.P, te.Ps],
    ['CS', STATE.cs, STATE.csTax],
    ['PS', STATE.ps, STATE.psTax],
    [isSub ? 'Бюджет (расход)' : 'Бюджет (сбор)', 0, STATE.budget],
    ['DWL', 0, STATE.dwl],
  ];
  const pf = pctForm();
  const adv = !!pf;
  // Название формы стоит рядом с числом: «τ = 50 %» без слова «акциз» не
  // отличить от «τ = 50 %» у НДС, а точки у них разные.
  let html = `<div class="stat"><span>${adv ? ('Ставка τ · ' + pf.label) : (isSub ? 'Субсидия s' : 'Налог t')}</span>` +
             `<b>${fmt(STATE.tax)}${adv ? ' %' : ''}</b></div>`;
  if (noBase) {
    html += '<table class="tx-table"><tr><th></th><th>После вмешательства</th></tr>';
    rows.forEach(([k, b]) => { html += `<tr><td>${k}</td><td>${fmt(b)}</td></tr>`; });
    html += '</table>';
    html += `<div class="hint" style="margin-top:6px;">Столбца «до» здесь нет, и это не пропуск:
      без ${isSub ? 'субсидии' : 'налога'} спрос и предложение пересекаются за пределами первой четверти,
      то есть рынка не было вовсе. Сравнивать не с чем, поэтому потери общества (DWL) и
      ${isSub ? 'выигрыш' : 'бремя'} сторон не считаются: обе величины — разность с исходным состоянием.</div>`;
  } else {
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
  }
  // Вывод об эквивалентности (только для налога): кто платит — не влияет на итог.
  if (adv) {
    /* Отношение цен и деньги — по строке таблицы PCT_FORMS, а не по формуле,
       переписанной здесь второй раз. База (цена покупателя или продавца)
       у четырёх форм разная, и именно ею они и различаются. */
    const k = pf.factor(STATE.tax / 100);
    const baseName = (pf.base === 'buyer') ? 'цены покупателя' : 'цены продавца';
    const money = (pf.base === 'buyer') ? (STATE.tax / 100) * te.Pb * te.Q
                                        : (STATE.tax / 100) * te.Ps * te.Q;
    html += `<div class="hint" style="margin-top:6px;">${pf.label}: ставка берётся долей от ` +
      `${baseName}. Кривая после — ${pf.curve}, то есть S<sub>после</sub> = ${fmt(k)}·S. ` +
      `Цена продавца Ps = ${fmt(te.Ps)}, цена покупателя Pb = ${fmt(te.Pb)}. ` +
      `${isSub ? 'Расход' : 'Сбор'} по ставке = ${fmt(money)}, и он же равен (Pb − Ps)·Q = ${fmt(STATE.tx)}.</div>`;
  }
  if (!isSub) html += `<div class="hint" style="margin-top:6px;">Результат не зависит от того, кто формально платит налог: ` +
    `объём Q, цены покупателя/продавца и распределение бремени одинаковы при налоге на продавца и на покупателя.</div>`;
  box.innerHTML = html;
}

// Переключение стороны налога (продавец / покупатель). На числа не влияет —
// меняется только визуально сдвигаемая кривая (Задача 1).
function setTaxSide(side) {
  STATE.taxSide = side;
  setTaxSideButtons();
  /* Каскад пересобирается целиком: от стороны зависит не только подсветка
     кнопки, но и подсказка под ставкой (см. syncTaxHint). */
  applyIntervCascade();
  redrawAll();
}

// Подсветка выбранной стороны. Вынесена отдельно: каскад тоже её обновляет,
// когда НДС или акциз возвращают сторону к продавцу.
function setTaxSideButtons() {
  const sel = document.getElementById('tsb-seller'), buy = document.getElementById('tsb-buyer');
  if (sel) sel.classList.toggle('active', STATE.taxSide === 'seller');
  if (buy) buy.classList.toggle('active', STATE.taxSide === 'buyer');
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
      .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.5)
      .call(sel => renderLabelText(sel, '|Ed|=1 · MR=0 · TR макс'));
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
  /* Пунктир к оси без числа на самой оси. Точка эластичности на ПРЕДЛОЖЕНИИ
     тянула обе проекции и не подписывала ни одной, хотя её зеркало на спросе
     подписывает обе: две линии в никуда, и прочесть по ним значение нечем. */
  axisValueX(g, px, oy, fmt(e.q), '');
  axisValueY(g, ox, py, fmt(e.p), '');
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
  if (hi <= lo) return;   // оптимум совпал с рынком — терять нечего
  const samp = []; for (let i = 0; i <= 100; i++) samp.push(lo + (hi - lo) * i / 100);
  const aD = d3.area().x(d => sx(d)).y0(d => sy(e.msc(d))).y1(d => sy(e.msb(d)));
  g.append('path').datum(samp).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28).attr('data-legend', 'Потери от внешнего эффекта (DWL)');
}

// Общественная кривая MSC (эффект на издержках) либо MSB (эффект на выгоде)
// + (если применён) частная кривая после корректирующего налога / субсидии.
function drawExtCurves(e) {
  if (!e) return;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const line = d3.line().defined(d => d !== null).x(d => sx(d[0])).y(d => sy(d[1]));
  const pts = (f) => { const o = []; for (let i = 0; i <= 400; i++) { const q = CONFIG.Qmax * i / 400; const v = f(q); o.push(isNaN(v) ? null : [q, v]); } return o; };
  /* Рисуем ТОЛЬКО включённые общественные кривые. Выключенная совпадает со
     своей частной парой, и вторая линия поверх D или S ничего не сообщала бы,
     а только путала: на графике оказались бы две кривые в одном месте. */
  if (e.mscOn) {
    g.append('path').datum(pts(e.msc)).attr('fill', 'none').attr('stroke', COL.reg).attr('stroke-width', 2.5).attr('d', line);
    labelCurve(g, e.msc, 'MSC', COL.reg, { from: 0.9 });
  }
  if (e.msbOn) {
    g.append('path').datum(pts(e.msb)).attr('fill', 'none').attr('stroke', COL.MR).attr('stroke-width', 2.5).attr('d', line);
    labelCurve(g, e.msb, 'MSB', COL.MR, { from: 0.9 });
  }
  // Корректирующий инструмент: налог поднимает предложение, субсидия — опускает (зелёный пунктир).
  if (e.applyPigou && e.corrective != null && Math.abs(e.corrective) > 1e-9) {
    g.append('path').datum(pts(q => evalCurve(STATE.S, q) + e.corrective))
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
  if (!STATE.D || !STATE.S) { box.innerHTML = '<div class="muted">Отметьте кривые D и S.</div>'; return; }
  if (!STATE.eq) { box.innerHTML = '<div class="warn">Рыночное равновесие не найдено.</div>'; return; }
  const e = STATE.ext;
  if (!e) { box.innerHTML = '<div class="muted">Расчёт не готов.</div>'; return; }
  const none = !e.msbOn && !e.mscOn;
  let html = '';
  html += `<div class="stat"><span>Рынок (D = S)</span><b>Q = ${fmt(e.Qmkt)}, P = ${fmt(e.Pmkt)}</b></div>`;
  if (e.Qopt != null) {
    html += `<div class="stat"><span>Оптимум (MSB = MSC)</span><b>Q = ${fmt(e.Qopt)}, P = ${fmt(e.Popt)}</b></div>`;
    html += `<div class="stat"><span>$DWL$ (потери)</span><b>${fmt(e.dwl)}</b></div>`;
    if (!none && Math.abs(e.corrective) > 1e-9) {
      const tool = (e.corrective > 0) ? 'Корректирующий налог (Пигу)' : 'Корректирующая субсидия';
      html += `<div class="stat"><span>${tool}</span><b>${fmt(Math.abs(e.corrective))}</b></div>`;
    }
    const gap = e.Qopt - e.Qmkt;
    html += `<div class="hint" style="margin-top:4px;">${none
      ? 'MSB и MSC пока совпадают с частными кривыми: внешнего эффекта нет, рынок и так в оптимуме. ' +
        'Включите MSB или MSC во «Вводе функций» и измените формулу, тогда появится расхождение.'
      : (gap < -1e-6
        ? 'Рынок выпускает <b>больше</b> общественного оптимума на ' + fmt(-gap) + ': <b>перепроизводство</b>, ' +
          'общественные издержки выше частных.'
        : (gap > 1e-6
          ? 'Рынок выпускает <b>меньше</b> общественного оптимума на ' + fmt(gap) + ': <b>недопроизводство</b>, ' +
            'общественная выгода выше частной.'
          : 'Рынок уже в общественном оптимуме: расхождения нет.'))}</div>`;
    if (e.applyPigou && e.pigouEq && Math.abs(e.corrective) > 1e-9) {
      html += `<div class="stat" style="margin-top:4px;"><span>Новое равновесие</span><b>Q = ${fmt(e.pigouEq.Q)}, P = ${fmt(e.pigouEq.P)}</b></div>`;
      html += `<div class="hint">${(e.corrective > 0) ? 'Налог Пигу поднял издержки' : 'Субсидия опустила издержки'}, рынок пришёл в оптимум, DWL устранён.</div>`;
    }
  } else {
    html += '<div class="warn">Оптимум MSB = MSC не найден в первой четверти.</div>';
  }
  box.innerHTML = html;
}

/* Знак эффекта кнопкой больше не выбирают — он вытекает из расчёта. Функция
   осталась ПРОГРАММНЫМ входом: она включает ту общественную кривую, которая
   этому знаку отвечает, оставляя формулу прежней (её правит человек).
   Отрицательный эффект живёт на издержках (MSC), положительный — на выгоде (MSB). */
function setExtSign(sign) {
  const pos = (sign === 'pos');
  STATE.msbOn = pos; STATE.mscOn = !pos;
  syncSocialFields();
  recompileSocial();
  redrawAll();
}

// Тексты и значения полей MSB/MSC приводятся в согласие с состоянием.
function syncSocialFields() {
  const put = (id, on) => { const e = document.getElementById(id); if (e) e.checked = !!on; };
  put('chk-msb', STATE.msbOn); put('chk-msc', STATE.mscOn);
  /* ⚠️ ПОЛЕ ФОРМУЛЫ ЗЕРКАЛИТСЯ MathLive. Само поле ввода спрятано, человек
     видит математический близнец рядом. Тот перечитывает значение по событию
     `input` — значит присвоить `.value` мало: на экране осталась бы прежняя
     формула, хотя считает движок уже по новой. Отправляем событие, и мост
     buildMathfield → fromInput доводит значение до видимого поля. */
  const set = (id, val) => {
    const e = document.getElementById(id);
    if (!e || document.activeElement === e) return;
    if (e.value === val) return;
    e.value = val;
    e.dispatchEvent(new Event('input', { bubbles: true }));
  };
  set('inp-msb', STATE.msbExpr); set('inp-msc', STATE.mscExpr);
  // Формулу правят только у включённой кривой: выключенная равна своей частной паре.
  ['msb', 'msc'].forEach(k => {
    const e = document.getElementById('inp-' + k);
    if (e) e.disabled = !STATE[k + 'On'];
  });
  const hint = document.getElementById('ext-hint');
  if (hint) {
    hint.innerHTML = (!STATE.msbOn && !STATE.mscOn)
      ? 'Спрос это предельная выгода частного лица, предложение это его предельные издержки. ' +
        'Пока MSB и MSC выключены, общественные кривые совпадают с частными: оптимум там же, где рынок.'
      : 'Общественный оптимум там, где MSB&nbsp;=&nbsp;MSC, а рынок приходит туда, где D&nbsp;=&nbsp;S. ' +
        'Расстояние между ними и есть потери от внешнего эффекта.';
  }
}

// Умолчание общественной кривой — формула её частной пары (MSB = D, MSC = S).
function socialDefaultExpr(which) {
  const c = (which === 'msb') ? STATE.D : STATE.S;
  return (c && c.expr) ? String(c.expr) : '';
}

// Перекомпиляция обеих общественных кривых. Ошибку показываем одной строкой.
function recompileSocial() {
  const errs = [];
  ['msb', 'msc'].forEach(k => {
    if (!STATE[k + 'Expr']) STATE[k + 'Expr'] = socialDefaultExpr(k);
    const r = compileExt(STATE[k + 'Expr']);
    STATE[k + 'Compiled'] = r.compiled;
    if (r.error && STATE[k + 'On']) errs.push(k.toUpperCase() + ': ' + r.error);
  });
  const errBox = document.getElementById('social-error');
  if (errBox) {
    errBox.style.display = errs.length ? 'block' : 'none';
    errBox.textContent = errs.length ? 'Не понял формулу: ' + errs.join('; ') : '';
  }
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
    const a = d3.area().x(d => sx(d)).y0(sy(Preg)).y1(d => sy(quadPrice(STATE.D, d)));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16).attr('data-legend', 'Излишек покупателя (CS)');
  }
  if (STATE.showPS) {   // PS — между предложением (низ) и ценой Preg (верх)
    const a = d3.area().x(d => sx(d)).y0(d => sy(quadPrice(STATE.S, d))).y1(sy(Preg));
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

/* =====================================================================
   БЛОК 8е. КВОТА — прямое ограничение объёма.
   Смысл сюжета: при связывающей квоте рыночная цена НЕ ОПРЕДЕЛЕНА
   однозначно, а лежит в коридоре [S(Qк); D(Qк)]. Пользователь выбирает
   цену внутри коридора ползунком; излишки перетекают, их сумма и
   трапеция потерь стоят на месте.
   ===================================================================== */

// Заполнить поля квоты, НЕ перерисовывая: нужно там, где перерисовка идёт
// следом сама (setType) — иначе redrawAll вызывается дважды подряд.
function setQuotaFields(q) {
  const slider = document.getElementById('quota-slider');
  const maxQ = slider ? (parseFloat(slider.max) || CONFIG.Qmax) : CONFIG.Qmax;
  q = Math.max(0, Math.min(q, maxQ));
  STATE.quota = q;
  if (slider) slider.value = q;
  const lbl = document.getElementById('quota-val'); if (lbl) lbl.textContent = fmt(q);
  const inp = document.getElementById('quota-input'); if (inp) inp.value = fmtInput(q);
}

// Объём квоты: единый путь для ползунка и числового поля.
function setQuota(q) {
  setQuotaFields(q);
  redrawAll();
}

// Положение цены внутри коридора: 0 — нижняя граница, 1 — верхняя.
// Ползунок размечен в процентах: доля коридора читается без пересчёта окна.
function setQuotaPos(pos) {
  pos = Math.max(0, Math.min(1, pos));
  STATE.quotaPos = pos;
  const slider = document.getElementById('quota-price-slider');
  if (slider) slider.value = Math.round(pos * 100);
  updateQuotaPriceLabel();
  redrawAll();
}

// Подпись под ползунком цены: сама цена и границы коридора.
function updateQuotaPriceLabel() {
  const lbl = document.getElementById('quota-price-val');
  if (!lbl) return;
  const q = STATE.qt;
  lbl.textContent = (q && q.P != null) ? fmt(q.P) : '…';
  const rng = document.getElementById('quota-price-range');
  if (rng) rng.textContent = (q && q.P != null)
    ? 'коридор от ' + fmt(q.Plo) + ' до ' + fmt(q.Phi)
    : 'коридора нет';
}

// Заливки при связывающей квоте: CS, PS и трапеция потерь.
function drawQuotaAreas() {
  if (!STATE.quotaActive) return;
  const { Qq, P } = STATE.qt;
  const g = svg.append('g').attr('clip-path', 'url(#plot-clip)');
  const samp = (a, b) => { const o = []; for (let i = 0; i <= 100; i++) o.push(a + (b - a) * i / 100); return o; };
  const s1 = samp(0, Qq);
  if (STATE.showCS) {   // CS — между выбранной ценой (низ) и спросом (верх)
    const a = d3.area().x(d => sx(d)).y0(sy(P)).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.D).attr('opacity', 0.16)
      .attr('data-legend', 'Излишек покупателя (CS)');
  }
  if (STATE.showPS) {   // PS — между предложением (низ) и выбранной ценой (верх)
    const a = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(sy(P));
    g.append('path').datum(s1).attr('d', a).attr('fill', COL.S).attr('opacity', 0.16)
      .attr('data-legend', 'Излишек продавца (PS)');
  }
  // Потери — площадь между D и S от квоты до равновесного объёма.
  const lo = Math.min(Qq, STATE.eq.Q), hi = Math.max(Qq, STATE.eq.Q);
  if (hi > lo) {
    const s2 = samp(lo, hi);
    const aD = d3.area().x(d => sx(d)).y0(d => sy(evalCurve(STATE.S, d))).y1(d => sy(evalCurve(STATE.D, d)));
    g.append('path').datum(s2).attr('d', aD).attr('fill', COL.inkSoft).attr('opacity', 0.28)
      .attr('data-legend', 'Потери общества (DWL)');
  }
}

// Линия квоты, закрашенный коридор возможных цен и выбранная цена внутри него.
function drawQuotaLines() {
  if (!STATE.quotaMode) return;
  const q = STATE.qt;
  if (!q) { drawEquilibrium(); return; }
  const ox = sx(0), oy = sy(0), xMax = sx(CONFIG.Qmax);
  const g = svg.append('g');
  const xQ = sx(q.Qq);

  // Вертикаль разрешённого объёма — это и есть сама квота.
  g.append('line').attr('x1', xQ).attr('y1', oy).attr('x2', xQ).attr('y2', sy(CONFIG.Pmax))
    .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
  axisValueX(g, xQ, oy, fmt(q.Qq), 'к');

  if (!STATE.quotaActive) {
    // Квота выше равновесного объёма не связывает: коридора нет, рынок обычный.
    drawEquilibrium();
  } else {
    const yLo = sy(q.Plo), yHi = sy(q.Phi), yP = sy(q.P);
    // КОРИДОР возможных цен — закрашенная полоса от P_s(квота) до P_d(квота)
    // на участке, где сделки и происходят (от нуля до квоты).
    g.append('rect').attr('x', ox).attr('y', Math.min(yLo, yHi))
      .attr('width', Math.max(0, xQ - ox)).attr('height', Math.abs(yLo - yHi))
      .attr('fill', COL.reg).attr('opacity', 0.12)
      .attr('data-legend', 'Коридор возможных цен');
    // Границы коридора — тонкий пунктир с числами на оси цены.
    [[q.Plo, 's'], [q.Phi, 'd']].forEach(([val, idx]) => {
      const y = sy(val);
      g.append('line').attr('x1', ox).attr('y1', y).attr('x2', xQ).attr('y2', y)
        .attr('stroke', COL.reg).attr('stroke-width', 1).attr('stroke-dasharray', '4 3');
      axisValueY(g, ox, y, val, idx);
    });
    // Выбранная цена — сплошная линия внутри коридора и точка сделки на квоте.
    g.append('line').attr('x1', ox).attr('y1', yP).attr('x2', xMax).attr('y2', yP)
      .attr('stroke', COL.reg).attr('stroke-width', 2.5).style('pointer-events', 'none');
    g.append('circle').attr('cx', xQ).attr('cy', yP).attr('r', 4)
      .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.5);
    // Тянуть цену можно прямо на графике — тем же жестом, что и линию потолка.
    const hit = g.append('rect')
      .attr('x', ox).attr('y', yP - 12).attr('width', Math.max(0, xMax - ox)).attr('height', 24)
      .attr('fill', 'transparent').style('cursor', 'grab');
    attachQuotaDrag(hit);
  }
}

// Перетаскивание цены внутри коридора: за его края цена не выходит.
function attachQuotaDrag(sel) {
  sel.call(d3.drag()
    .container(() => svg.node())
    .on('start', () => { document.body.style.cursor = 'grabbing'; })
    .on('drag', (event) => {
      const q = STATE.qt;
      if (!q || q.width == null || !(q.width > 0)) return;
      setQuotaPos((sy.invert(event.y) - q.Plo) / q.width);
    })
    .on('end', () => { document.body.style.cursor = ''; }));
}

// Табло квоты: коридор, выбранная цена, перетекание излишков и потери.
function updateQuotaPanel() {
  // Ползунок цены живёт ровно столько, сколько существует коридор: сам
  // коридор появляется только у связывающей квоты, и знать об этом можно
  // лишь ПОСЛЕ расчёта — поэтому видимость обновляется здесь, а не в каскаде.
  const pf = document.getElementById('quota-price-field');
  if (pf) pf.style.display = STATE.quotaActive ? '' : 'none';
  updateQuotaPriceLabel();
  const box = document.getElementById('info-tax');
  if (!box) return;
  if (!STATE.D || !STATE.S) { box.innerHTML = '<div class="muted">Сначала отметьте кривые D и S.</div>'; return; }
  if (!STATE.eq) { box.innerHTML = '<div class="warn">Равновесие не найдено.</div>'; return; }
  const q = STATE.qt;
  if (!q || !(STATE.quota > 0)) {
    box.innerHTML = '<div class="muted">Задайте разрешённый объём, который допускает квота.</div>';
    return;
  }
  if (!q.binding) {
    box.innerHTML = `<div class="warn">Квота ${fmt(q.Qq)} больше равновесного объёма (Q*=${fmt(STATE.eq.Q)}), ` +
      'поэтому не связывает. Рынок работает как обычно, коридора цен нет.</div>';
    return;
  }
  let html = `<div class="stat"><span>Коридор цен</span><b>${fmt(q.Plo)} … ${fmt(q.Phi)}</b></div>`;
  html += `<div class="stat"><span>Выбранная цена</span><b>${fmt(q.P)}</b></div>`;
  const rows = [
    ['Q', STATE.eq.Q, q.Qq],
    ['CS', STATE.cs, q.cs],
    ['PS', STATE.ps, q.ps],
    ['CS + PS', STATE.sw, q.sw],
    ['DWL', 0, q.dwl],
  ];
  html += '<table class="tx-table"><tr><th></th><th>До</th><th>После</th><th>Δ</th></tr>';
  rows.forEach(([k, a, b]) => {
    html += `<tr><td>${k}</td><td>${fmt(a)}</td><td>${fmt(b)}</td><td>${fmtDiff(b, a)}</td></tr>`;
  });
  html += '</table>';
  html += '<div class="hint" style="margin-top:6px;">Двигая цену внутри коридора, вы перекладываете выигрыш ' +
    'между покупателем и продавцом. Сумма CS + PS и треугольник потерь при этом не меняются: ' +
    'цена в их расчёт не входит.</div>';
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
  if (!(STATE.taxActive || STATE.pcActive || STATE.quotaActive) || !STATE.eq) return;
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

