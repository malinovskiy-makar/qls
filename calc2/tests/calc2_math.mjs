// Регрессионные тесты МАТЕМАТИКИ калькулятора calc2 (Блок 3).
//
// Самый надёжный путь: гоняем РЕАЛЬНЫЕ функции calc2 в настоящем браузере
// (Playwright + реальные Math.js/D3 с CDN), а не извлекаем инлайн-скрипт и не
// мокаем DOM. Для каждой фичи приводим страницу в нужное состояние через
// глобальные функции (loadScene/setMonoMode/setLaborStruct/…), вызываем
// redrawAll() и читаем результат из STATE — то есть тот же путь, что у юзера.
//
// Запуск (нужен живой сервер calc2):
//   node calc2/tests/calc2_math.mjs
// Параметры через env: CALC2_BASE_URL (http://127.0.0.1:8099), CALC2_USER (admin),
//   CALC2_PASS (admin12345).
// Коды выхода: 0 — все тесты прошли; 1 — есть провалы; 3 — calc2 не загрузился
//   (нет CDN Math.js/D3 или сервер не отдал страницу) → вызывающий тест пропускает.
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

// Контрольные случаи. Каждый run() выполняется В БРАУЗЕРE: приводит calc2 в
// состояние, дёргает redrawAll() и возвращает плоский объект вычисленных величин.
// checks — пары [подпись, ключ, ожидание, допуск?].
const CASES = [
  {
    name: 'Рынок · равновесие D=100−Q, S=Q',
    run: `loadScene('sd'); redrawAll();
          return { Q: STATE.eq.Q, P: STATE.eq.P };`,
    checks: [['Q*', 'Q', 50, 0.3], ['P*', 'P', 50, 0.3]],
  },
  {
    name: 'Рынок · налог t=20 (продавец=покупатель)',
    run: `loadScene('tax'); redrawAll();
          var Q1 = STATE.tx / STATE.tax;            // tx = t·Q1  ⇒  Q1
          var Pb = evalCurve(STATE.D, Q1);          // цена покупателя = D(Q1)
          return { Q1: Q1, Pb: Pb, Ps: Pb - STATE.tax, tx: STATE.tx };`,
    checks: [['Q1', 'Q1', 40, 0.3], ['Pb', 'Pb', 60, 0.3], ['Ps', 'Ps', 40, 0.3], ['tx', 'tx', 800, 5]],
  },
  {
    name: 'Монополия D=100−Q, MC=20',
    // profit (TR−TC) требует FC/ATC; при MC=20 без FC «прибыль» = PS = TR−VC = psM.
    run: `loadScene('mono'); redrawAll();
          return { Qm: STATE.mono.Qm, Pm: STATE.mono.Pm, psM: STATE.mono.psM };`,
    checks: [['Qm', 'Qm', 40, 0.3], ['Pm', 'Pm', 60, 0.3], ['π=PS', 'psM', 1600, 8]],
  },
  {
    name: 'Монополия · дискриминация 1-й степени',
    run: `loadScene('mono'); setMonoMode('discr1'); redrawAll();
          return { Qcomp: STATE.discr1.Qcomp, profit: STATE.discr1.profit };`,
    checks: [['Qcomp', 'Qcomp', 80, 0.4], ['π', 'profit', 3200, 16]],
  },
  {
    name: 'Монополия · дискриминация 3-й степени (D1=100−Q, D2=80−2Q, MC=20)',
    run: `loadScene('mono'); setMonoMode('discr3');
          var b = document.getElementById('btn-discr3-apply'); if (b) b.click();
          redrawAll();
          var d = STATE.discr3 || {};
          return { q1: d.q1, P1: d.P1, q2: d.q2, P2: d.P2 };`,
    checks: [['q1', 'q1', 40, 0.4], ['P1', 'P1', 60, 0.4], ['q2', 'q2', 15, 0.4], ['P2', 'P2', 50, 0.4]],
  },
  {
    name: 'Монополия · ломаный спрос (один кусок 100−Q, MC=20)',
    // piecewise с непересекающимися кусками (стык при Q=0) → один кусок f1=100−Q ⇒
    // ломаный солвер должен воспроизвести обычную монополию 40/60.
    run: `loadScene('mono'); setMonoMode('kinked');
          STATE.kinkInput='piecewise'; STATE.kpD1='100 - Q'; STATE.kpD2='100 - 0.5*Q'; STATE.kinkMC='20';
          recomputeKinked(); redrawAll();
          return { Qstar: (STATE.kinked||{}).Qstar, Pstar: (STATE.kinked||{}).Pstar };`,
    checks: [['Q*', 'Qstar', 40, 0.5], ['P*', 'Pstar', 60, 0.5]],
  },
  {
    name: 'Монополия · налог t=10 (D=100−Q, MC=20): MR=MC+t, Q↓ P↑',
    // База 40/60; при налоге MR=100−2Q=MC+t=30 ⇒ Q=35, P=65, сбор=10·35=350.
    run: `loadScene('mono'); setMonoMode('simple'); setType('tax'); setTax(10); redrawAll();
          var t = STATE.monoTax || {};
          var gap = marginalRevenue(STATE.D, t.Qt) - (mcAt(t.Qt) + 10);
          return { Qt: t.Qt, Pt: t.Pt, budget: t.budget, gap: gap };`,
    checks: [['Qt', 'Qt', 35, 0.4], ['Pt', 'Pt', 65, 0.4], ['сбор', 'budget', 350, 5], ['MR−(MC+t)', 'gap', 0, 0.5]],
  },
  {
    name: 'Монополия · субсидия s=10: MR=MC−s, Q↑ P↓',
    // MR=100−2Q=MC−s=10 ⇒ Q=45, P=55, расход=−10·45=−450.
    run: `loadScene('mono'); setMonoMode('simple'); setType('subsidy'); setTax(10); redrawAll();
          var t = STATE.monoTax || {};
          var gap = marginalRevenue(STATE.D, t.Qt) - (mcAt(t.Qt) - 10);
          return { Qt: t.Qt, Pt: t.Pt, budget: t.budget, gap: gap };`,
    checks: [['Qt', 'Qt', 45, 0.4], ['Pt', 'Pt', 55, 0.4], ['расход', 'budget', -450, 5], ['MR−(MC−s)', 'gap', 0, 0.5]],
  },
  {
    name: 'Монополия · потолок Pc=40: перенос логики идентичен прежней галочке',
    // Связывающий потолок (Pc<Pm=60). Сверяем «проводной» STATE.monoCeil с прямым вызовом.
    run: `loadScene('mono'); setMonoMode('simple'); setType('ceiling'); setPReg(40); redrawAll();
          var wired = (STATE.monoCeil || {}).Qstar;
          var direct = (monopolyCeiling(40) || {}).Qstar;
          return { wired: wired, want: direct, binding: (STATE.monoCeil||{}).binding ? 1 : 0 };`,
    checks: [['Qstar=прямой', 'wired', 'WANT', 0.3], ['Qstar', 'wired', 60, 0.6], ['связывает', 'binding', 1, 0.1]],
  },
  {
    name: 'Монополия · пол Pf=80 > Pm=60: цена = пол, выпуск = D(Pf)',
    run: `loadScene('mono'); setMonoMode('simple'); setType('floor'); setPReg(80); redrawAll();
          var fl = STATE.monoFloor || {};
          return { price: fl.price, Q: fl.Q, binding: fl.binding ? 1 : 0 };`,
    checks: [['цена', 'price', 80, 0.4], ['Q', 'Q', 20, 0.5], ['связывает', 'binding', 1, 0.1]],
  },
  {
    name: 'Монополия · пол Pf=40 < Pm=60: не связывает (без изменений)',
    run: `loadScene('mono'); setMonoMode('simple'); setType('floor'); setPReg(40); redrawAll();
          var fl = STATE.monoFloor || {}; var m = STATE.mono || {};
          return { binding: fl.binding ? 1 : 0, Qm: m.Qm, Pm: m.Pm };`,
    checks: [['не связывает', 'binding', 0, 0.1], ['Qm', 'Qm', 40, 0.4], ['Pm', 'Pm', 60, 0.4]],
  },
  {
    name: 'Эластичность · D=100−Q при Q=50 ⇒ |Ed|=1',
    run: `loadScene('sd'); setScenario('elasticity');
          // двигаем точку на Q=50 (единичная эластичность — середина)
          STATE.elastQ = 50; redrawAll();
          return { absEd: (STATE.elast||{}).absEd };`,
    checks: [['|Ed|', 'absEd', 1, 0.03]],
  },
  {
    /* Внешний эффект ОТРИЦАТЕЛЬНЫЙ. Устройство сюжета переделано ночной
       сессией «вмешательство»: величину эффекта отдельным полем больше не
       вводят, общественная кривая MSC задаётся формулой во «Вводе функций».
       Рынок D = S ⇒ Q=50. Оптимум MSB = MSC ⇒ 100−Q = Q+20 ⇒ Q=40.
       DWL = ∫₄₀^50 (2q−80) dq = 100. Налог Пигу = D(40) − S(40) = 20. */
    name: '(и) Внешний эффект ОТРИЦАТЕЛЬНЫЙ · MSC = Q+20 ⇒ Qрын=50, Qопт=40, DWL=100',
    run: `loadScene('ext'); STATE.mscOn = true; STATE.mscExpr = 'Q + 20';
          recompileSocial(); redrawAll();
          var e = STATE.ext || {};
          return { Qmkt: e.Qmkt, Qopt: e.Qopt, dwl: e.dwl, tax: e.corrective, Popt: e.Popt };`,
    checks: [['Qрын', 'Qmkt', 50, 0.3], ['Qопт', 'Qopt', 40, 0.4], ['DWL', 'dwl', 100, 2],
             ['налог Пигу', 'tax', 20, 0.2], ['Pопт', 'Popt', 60, 0.4]],
  },
  {
    name: 'Труд · монопсония D=100−L, S=L',
    run: `setMode('labor'); setLaborStruct('monopsony'); redrawAll();
          var m = STATE.laborMono || {};
          return { Lm: m.Lm, Wm: m.Wm };`,
    checks: [['Lм', 'Lm', 33.33, 0.1], ['Wм', 'Wm', 33.33, 0.1]],
  },
  {
    name: 'Труд · профсоюз-монополист',
    run: `setMode('labor'); setLaborStruct('union'); redrawAll();
          var u = STATE.laborUnion || {};
          return { Lu: u.Lu, Wu: u.Wu };`,
    checks: [['Lп', 'Lu', 33.33, 0.2], ['Wп', 'Wu', 66.67, 0.2]],
  },
  {
    name: 'Труд · МРОТ=50 в монопсонии ⇒ занятость растёт к 50',
    run: `setMode('labor'); setLaborStruct('monopsony');
          STATE.laborMinOn = true; setLaborMin(50); redrawAll();
          var min = STATE.laborMin || {};
          // занятость при связывающем МРОТ: Lstar (короткая сторона)
          return { Lstar: min.Lstar, binding: min.binding ? 1 : 0 };`,
    checks: [['Lзан', 'Lstar', 50, 0.5], ['связ.', 'binding', 1, 0.1]],
  },
  {
    name: 'Неравенство · доходы 10,20,30,40,100',
    run: `setMode('inequality'); setIneqInput('incomes');
          STATE.ineqIncomes = '10, 20, 30, 40, 100'; redrawAll();
          var s = STATE.ineqStats || {};
          return { gini: s.gini, hoover: s.hoover };`,
    checks: [['Gini', 'gini', 0.40, 0.01], ['Робин Гуда', 'hoover', 0.30, 0.01]],
  },
  {
    name: 'Неравенство · формула Лоренца p^2',
    run: `setMode('inequality'); setIneqInput('formula');
          STATE.ineqFormula = 'p^2'; redrawAll();
          return { gini: (STATE.ineqStats||{}).gini };`,
    checks: [['Gini', 'gini', 0.3333, 0.01]],
  },
  {
    name: 'Неравенство · прогрессивный налог τ=0.5 на 8,12,16,24,40',
    run: `setMode('inequality'); setIneqInput('incomes');
          STATE.ineqIncomes = '8, 12, 16, 24, 40';
          STATE.ineqRedistOn = true; setIneqRedistTool('tax');
          STATE.ineqTau = 0.5; redrawAll();
          var r = STATE.ineqRedist || {};
          return { gini: (r.stats||{}).gini };`,
    checks: [['Gini после', 'gini', 0.152, 0.02]],
  },
  {
    name: 'КПВ · сумма двух дуг √(100−x²)+√(64−x²) ≈ √(324−x²)',
    run: `setMode('ppf'); setPpfSub('sum');
          STATE.ppf1 = 'sqrt(100 - X^2)'; STATE.ppf2 = 'sqrt(64 - X^2)';
          var i1=document.getElementById('inp-ppf1'); if(i1)i1.value=STATE.ppf1;
          var i2=document.getElementById('inp-ppf2'); if(i2)i2.value=STATE.ppf2;
          STATE.ppfSumData = null;
          var b=document.getElementById('btn-ppfsum-apply'); if(b)b.click();
          redrawAll();
          // сэмплируем сумму при X=10 и сравниваем с √(324−100)=√224≈14.966
          var d = STATE.ppfSumData; if(!d||!d.ok||!d.points) return { yAt10: null };
          var best=null,bd=1e9; for(var k=0;k<d.points.length;k++){var p=d.points[k]; if(p&&isFinite(p[1])){var dd=Math.abs(p[0]-10); if(dd<bd){bd=dd;best=p;}}}
          return { xAt: best?best[0]:null, yAt10: best?best[1]:null, want: Math.sqrt(324-best[0]*best[0]) };`,
    checks: [['Σ(x≈10)', 'yAt10', 'WANT', 0.3]],   // сравним с динамическим want
  },
  {
    name: 'КПВ · сумма с изломами (100−x²)+(50−x) ⇒ узлы (0.5;149.75),(50.5;99.75)',
    run: `setMode('ppf'); setPpfSub('sum');
          STATE.ppf1 = '100 - X^2'; STATE.ppf2 = '50 - X';
          var i1=document.getElementById('inp-ppf1'); if(i1)i1.value=STATE.ppf1;
          var i2=document.getElementById('inp-ppf2'); if(i2)i2.value=STATE.ppf2;
          STATE.ppfSumData = null;
          var b=document.getElementById('btn-ppfsum-apply'); if(b)b.click();
          redrawAll();
          var ks = (STATE.ppfSumKinks||[]).slice().sort(function(a,c){return a.x-c.x;});
          var k0 = ks[0]||{}, k1 = ks[ks.length-1]||{};
          return { k0x: k0.x, k0y: k0.y, k1x: k1.x, k1y: k1.y, n: ks.length };`,
    checks: [['узел0 x', 'k0x', 0.5, 0.1], ['узел0 y', 'k0y', 149.75, 0.3],
             ['узел1 x', 'k1x', 50.5, 0.3], ['узел1 y', 'k1y', 99.75, 0.3]],
  },
  {
    name: 'Торговля Б · 100−X и 100−2X ⇒ мировая цена Pw=√2≈1.414 ∈(1,2)',
    run: `setMode('ppf'); setPpfSub('trade'); setTradeScenario('B');
          STATE.ppf1 = '100 - X'; STATE.ppf2 = '100 - 2*X';
          var i1=document.getElementById('inp-ppf1'); if(i1)i1.value=STATE.ppf1;
          var i2=document.getElementById('inp-ppf2'); if(i2)i2.value=STATE.ppf2;
          STATE.tradeBData = null;
          var b=document.getElementById('btn-tb-apply'); if(b)b.click();
          redrawAll();
          var t = STATE.tradeBData || {};
          return { Pweq: t.Pweq, Pw: t.Pw };`,
    checks: [['Pw равн.', 'Pweq', 1.41421, 0.02]],
  },

  /* ── Фаза 1 (сессия B): универсальный ввод P(Q) / Q(P) ───────────────── */
  {
    name: 'Ввод Q(P) · «100 − 2P» ≡ P(Q) «50 − 0.5Q»: одно и то же равновесие с S=Q',
    // Одна и та же кривая спроса, записанная двумя способами, обязана дать
    // одинаковые Q*/P*. Канон Q(P)→P(Q): Q=100−2P ⇒ P = 50 − 0.5Q.
    // setMode('market') обязателен: предыдущий кейс мог оставить режим 'ppf',
    // и тогда redrawAll() ушёл бы в redrawPpf(), не пересчитав STATE.eq.
    run: `setMode('market'); STATE.scenario = 'none'; STATE.curves = [];
          addCurve('50 - 0.5*Q'); setRole(STATE.curves[0], 'demand');
          addCurve('Q');          setRole(STATE.curves[1], 'supply');
          redrawAll();
          var a = { Q: STATE.eq.Q, P: STATE.eq.P };
          STATE.curves = [];
          addCurve('100 - 2*P', 'QP'); setRole(STATE.curves[0], 'demand');
          addCurve('Q');               setRole(STATE.curves[1], 'supply');
          redrawAll();
          var lin = STATE.curves[0].linear;
          return { Qpq: a.Q, Ppq: a.P, Qqp: STATE.eq.Q, Pqp: STATE.eq.P, a: lin.a, b: lin.b };`,
    checks: [['Q* через P(Q)', 'Qpq', 33.333, 0.05], ['P* через P(Q)', 'Ppq', 33.333, 0.05],
             ['Q* через Q(P)', 'Qqp', 33.333, 0.05], ['P* через Q(P)', 'Pqp', 33.333, 0.05],
             ['канон a', 'a', -0.5, 0.005], ['канон b', 'b', 50, 0.05]],
  },
  {
    name: 'Ввод Q(P) · нелинейная 400/(P+1) ⇒ численное обращение бисекцией',
    // Q = 400/(P+1)  ⇒  P = 400/Q − 1: при Q=100 → 3, при Q=50 → 7.
    run: `setMode('market'); STATE.curves = [];
          addCurve('400 / (P + 1)', 'QP');
          var c = STATE.curves[0];
          return { p100: evalCurve(c, 100), p50: evalCurve(c, 50), isFn: c.fn ? 1 : 0 };`,
    checks: [['P(Q=100)', 'p100', 3, 0.01], ['P(Q=50)', 'p50', 7, 0.01], ['численный канон', 'isFn', 1, 0.1]],
  },

  /* ── Фаза 2: эластичность, экстерналии, адвалорный налог ─────────────── */
  {
    name: 'Эластичность спроса · D=100−Q: |Ed| = 3 при Q=25 и 0.333 при Q=75',
    run: `loadScene('elast');
          STATE.elastQ = 25; redrawAll(); var a = (STATE.elast||{}).absEd;
          STATE.elastQ = 75; redrawAll(); var b = (STATE.elast||{}).absEd;
          STATE.elastQ = 50; redrawAll(); var c = (STATE.elast||{}).absEd;
          return { a: a, b: b, c: c, TR: (STATE.elast||{}).TR };`,
    checks: [['|Ed| при Q=25', 'a', 3, 0.02], ['|Ed| при Q=75', 'b', 0.3333, 0.01],
             ['|Ed| при Q=50', 'c', 1, 0.01], ['TR при Q=50', 'TR', 2500, 20]],
  },
  {
    name: 'Эластичность предложения · S=Q (прямая через 0) ⇒ |Es| = 1 в любой точке',
    run: `loadScene('elast'); STATE.showElastS = true;
          STATE.elastQS = 20; redrawAll(); var a = (STATE.elastS||{}).absEs;
          STATE.elastQS = 70; redrawAll(); var b = (STATE.elastS||{}).absEs;
          return { a: a, b: b };`,
    checks: [['|Es| при Q=20', 'a', 1, 0.02], ['|Es| при Q=70', 'b', 1, 0.02]],
  },
  {
    name: '(к) Внешний эффект ПОЛОЖИТЕЛЬНЫЙ · MSB = 120−Q ⇒ Qрын=50, Qопт=60, DWL=100',
    /* Зеркало отрицательного случая: недопроизводство, лечится СУБСИДИЕЙ.
       Оптимум MSB = MSC ⇒ 120−Q = Q ⇒ Q=60, P = 60.
       DWL = ∫₅₀^60 (120−2q) dq = 100. Субсидия = |D(60) − S(60)| = 20
       (в расчёте она приходит со знаком «минус» — это и значит субсидию). */
    run: `loadScene('ext'); STATE.msbOn = true; STATE.msbExpr = '120 - Q';
          recompileSocial(); redrawAll();
          var e = STATE.ext || {};
          return { Qmkt: e.Qmkt, Qopt: e.Qopt, dwl: e.dwl, sub: -e.corrective,
                   Popt: e.Popt, pos: e.pos ? 1 : 0 };`,
    checks: [['Qрын', 'Qmkt', 50, 0.3], ['Qопт', 'Qopt', 60, 0.4], ['DWL', 'dwl', 100, 2],
             ['субсидия', 'sub', 20, 0.2], ['Pопт = MSC(Qопт)', 'Popt', 60, 0.4], ['знак +', 'pos', 1, 0.1]],
  },
  {
    name: 'Адвалорный налог · D=100−Q, S=2Q, τ=50% ⇒ Q1=25, Pb=75, Ps=50, сбор=625',
    // Поворот, а не сдвиг: S_после = (1+τ)·S = 3Q. Вертикальный разрыв между S и
    // S_после РАСТЁТ с Q (20 при Q=20, 40 при Q=40) — в отличие от постоянного клина.
    run: `setMode('market'); STATE.scenario = 'none'; STATE.curves = [];
          addCurve('100 - Q'); setRole(STATE.curves[0], 'demand');
          addCurve('2*Q');     setRole(STATE.curves[1], 'supply');
          setMarket('comp'); setType('tax'); setTaxKind('advalorem'); setTax(50); redrawAll();
          var te = STATE.taxEq || {};
          var g20 = evalCurve(STATE.taxAfterS, 20) - evalCurve(STATE.S, 20);
          var g40 = evalCurve(STATE.taxAfterS, 40) - evalCurve(STATE.S, 40);
          var res = { Q1: te.Q, Pb: te.Pb, Ps: te.Ps, tx: STATE.tx, g20: g20, g40: g40 };
          setTaxKind('unit'); setTax(0);
          return res;`,
    checks: [['Q1', 'Q1', 25, 0.2], ['Pb', 'Pb', 75, 0.3], ['Ps', 'Ps', 50, 0.3],
             ['сбор', 'tx', 625, 5], ['разрыв при Q=20', 'g20', 20, 0.3], ['разрыв при Q=40', 'g40', 40, 0.5]],
  },

  /* ── Фаза 3: естественная монополия и регулирование ──────────────────── */
  {
    name: 'Естественная монополия · D=100−Q, MC=20, FC=800: три ориентира регулирования',
    // ATC(Q) = (800 + 20Q)/Q. Монополия 40/60 (прибыль 800 = FC). P=MC: Q=80, P=20,
    // ATC=30 ⇒ убыток (30−20)·80 = 800 — ровно столько нужно субсидии.
    // P=ATC: 100−Q = 800/Q + 20 ⇒ Q² − 80Q + 800 = 0 ⇒ корни 11.72 и 68.28,
    // берём БОЛЬШИЙ (он и лежит между Qm=40 и Qc=80).
    run: `loadScene('mono'); setMonoMode('natural');
          STATE.natFC = 800; var f = document.getElementById('inp-nat-fc'); if (f) f.value = 800;
          redrawAll();
          var n = STATE.natural || {}, mc = n.mcReg || {}, ac = n.acReg || {};
          var inWindow = (ac.Q != null && ac.Q > n.Qm && ac.Q < mc.Q) ? 1 : 0;
          var res = { Qm: n.Qm, Pm: n.Pm, atcQm: n.atcAtQm, profit: n.profit,
                      Qmc: mc.Q, Pmc: mc.P, atcMc: mc.atc, sub: mc.subsidy,
                      Qac: ac.Q, Pac: ac.P, inWindow: inWindow };
          setMonoMode('simple');
          return res;`,
    checks: [['Qm', 'Qm', 40, 0.3], ['Pm', 'Pm', 60, 0.3], ['ATC(Qm)', 'atcQm', 40, 0.3],
             ['π монополии', 'profit', 800, 8],
             ['Q при P=MC', 'Qmc', 80, 0.4], ['P=MC', 'Pmc', 20, 0.2], ['ATC(80)', 'atcMc', 30, 0.3],
             ['субсидия', 'sub', 800, 8],
             ['Q при P=ATC', 'Qac', 68.284, 0.5], ['P при P=ATC', 'Pac', 31.716, 0.5],
             ['корень между Qm и Qc', 'inWindow', 1, 0.1]],
  },

  /* ── Фаза 4: международная торговля ──────────────────────────────────── */
  {
    name: 'Малая открытая экономика · D=100−Q, S=Q, Pw=30 ⇒ импорт 40 (Qd=70, Qs=30)',
    run: `loadScene('smallopen'); setOpenTool('none'); setOpenPw(30); redrawAll();
          var o = STATE.open || {};
          return { Qd: o.Qd, Qs: o.Qs, imp: o.volume, isImp: o.importing ? 1 : 0,
                   autQ: (o.aut||{}).Q, autP: (o.aut||{}).P };`,
    checks: [['Qd', 'Qd', 70, 0.3], ['Qs', 'Qs', 30, 0.3], ['импорт', 'imp', 40, 0.4],
             ['импортирует', 'isImp', 1, 0.1], ['автаркия Q*', 'autQ', 50, 0.3], ['автаркия P*', 'autP', 50, 0.3]],
  },
  {
    name: 'Тариф t=10 · Qd′=60, Qs′=40, импорт 20, бюджет 200, DWL 50 + 50',
    // Два треугольника СЧИТАЮТСЯ ОТДЕЛЬНО: производственное искажение (S дороже Pw
    // на [30;40]) и потребительское (D ниже Pw на [60;70]) — по 50 каждый.
    run: `loadScene('smallopen'); setOpenPw(30); setOpenTool('tariff');
          STATE.openTariff = 10; redrawAll();
          var o = STATE.open || {};
          return { P1: o.P1, Qd1: o.Qd1, Qs1: o.Qs1, imp1: o.vol1, money: o.money,
                   dwlP: o.dwlProd, dwlC: o.dwlCons, dwlT: o.dwlTotal };`,
    checks: [['P₁', 'P1', 40, 0.3], ['Qd′', 'Qd1', 60, 0.3], ['Qs′', 'Qs1', 40, 0.3],
             ['импорт′', 'imp1', 20, 0.4], ['доход бюджета', 'money', 200, 3],
             ['DWL производства', 'dwlP', 50, 1.5], ['DWL потребления', 'dwlC', 50, 1.5],
             ['DWL всего', 'dwlT', 100, 3]],
  },
  {
    name: 'Квота 20 · та же цена 40 и та же геометрия, но 200 — рента, а не бюджет',
    // Цена ищется ЧИСЛЕННО из условия Qd(P) − Qs(P) = 20 ⇒ (100−P) − P = 20 ⇒ P = 40.
    run: `loadScene('smallopen'); setOpenPw(30); setOpenTool('quota');
          STATE.openQuota = 20; redrawAll();
          var o = STATE.open || {};
          return { P1: o.P1, Qd1: o.Qd1, Qs1: o.Qs1, imp1: o.vol1, rent: o.money,
                   dwlT: o.dwlTotal, tool: (o.tool === 'quota') ? 1 : 0 };`,
    checks: [['P₁ (численно)', 'P1', 40, 0.3], ['Qd′', 'Qd1', 60, 0.3], ['Qs′', 'Qs1', 40, 0.3],
             ['импорт′ = квота', 'imp1', 20, 0.4], ['рента квоты', 'rent', 200, 3],
             ['DWL всего', 'dwlT', 100, 3], ['инструмент = квота', 'tool', 1, 0.1]],
  },
  {
    name: 'Монополист и мировой рынок · D=100−Q, MC=Q, Pw=50 ⇒ MR₁ = Pw = MC(Σ)',
    // Частный случай дискриминации 3°: второй сегмент — горизонтальный спрос на Pw.
    // Условие оптимума MR₁ = Pw = MC(Q₁+Q₂): MC(Σ)=Σ=50, MR₁=100−2q₁=50 ⇒ q₁=25,
    // P₁=75, экспорт q₂=25. См. отчёт: это ОТЛИЧАЕТСЯ от контрольных чисел ТЗ
    // (33.33/66.67/50), которые соответствуют РАЗДЕЛЬНЫМ издержкам по рынкам.
    run: `loadScene('monoexport'); redrawAll();
          var d = STATE.discr3 || {};
          return { q1: d.q1, P1: d.P1, q2: d.q2, P2: d.P2, Qtot: d.Qtot, mc: d.mcLevel,
                   found: d.found ? 1 : 0, world: STATE.d3World ? 1 : 0 };`,
    checks: [['найден оптимум', 'found', 1, 0.1], ['режим мировой торговли', 'world', 1, 0.1],
             ['Σ выпуск (MC=Pw)', 'Qtot', 50, 0.4], ['MR₁=Pw=MC', 'mc', 50, 0.4],
             ['q₁ внутри', 'q1', 25, 0.4], ['P₁ внутри', 'P1', 75, 0.4],
             ['q₂ экспорт', 'q2', 25, 0.4], ['P₂ = Pw', 'P2', 50, 0.3]],
  },

  /* ── Фаза 7: общий движок касания уровня ─────────────────────────────── */
  {
    name: 'Движок касания · Кобб-Дуглас f=√x·√y, Pa=1, Pb=2, I=100 ⇒ a*=50, b*=25, MRS=0.5',
    // Численный оптимум обязан совпасть с известной аналитикой: доля дохода на
    // каждое благо = его показатель степени ⇒ 50 на a (цена 1) и 50 на b (цена 2).
    // Проверяем и обратный ход: кривая уровня через оптимум в точке a=50 даёт b=25.
    run: `var f = function (a, b) { return Math.sqrt(a) * Math.sqrt(b); };
          var r = optimizeAlongConstraint(f, 1, 2, 100);
          var yAt = solveLevelB(f, r.value, r.a, 400);
          var curve = traceLevelCurve(f, r.value, 200, 400, 100);
          var pts = curve.filter(function (p) { return p; });
          return { a: r.a, b: r.b, spend: 1 * r.a + 2 * r.b, mrs: r.mrs,
                   value: r.value, yAt: yAt, nPts: pts.length };`,
    checks: [['a*', 'a', 50, 0.05], ['b*', 'b', 25, 0.05], ['потрачен весь доход', 'spend', 100, 0.1],
             ['MRS = Pa/Pb', 'mrs', 0.5, 0.01], ['уровень f', 'value', 35.355, 0.02],
             ['кривая уровня через оптимум', 'yAt', 25, 0.05], ['точек на кривой', 'nPts', 100, 1]],
  },

  /* ── Фаза 8: теория потребителя ──────────────────────────────────────── */
  {
    name: 'Потребитель · четыре вида предпочтений через ОДИН численный оптимизатор',
    // Кобб-Дуглас (Px=1,Py=2,I=100) → 50/25; комплементы min(x/1,y/2) при 1,1,30 → 10/20;
    // субституты 2x+y при 1,1,50 → угол 50/0; квазилинейные x+2√y при 1,1,50 → 49/1.
    run: `setMode('consumer');
          var out = {};
          setConsumerType('cobb'); STATE.consA = 0.5; STATE.consB = 0.5;
          STATE.consPx = 1; STATE.consPy = 2; STATE.consI = 100; redrawAll();
          out.cdX = STATE.cons.base.x; out.cdY = STATE.cons.base.y; out.cdMrs = STATE.cons.base.mrs;
          setConsumerType('compl'); STATE.consA = 1; STATE.consB = 2;
          STATE.consPx = 1; STATE.consPy = 1; STATE.consI = 30; redrawAll();
          out.coX = STATE.cons.base.x; out.coY = STATE.cons.base.y;
          setConsumerType('subs'); STATE.consA = 2; STATE.consB = 1;
          STATE.consPx = 1; STATE.consPy = 1; STATE.consI = 50; redrawAll();
          out.suX = STATE.cons.base.x; out.suY = STATE.cons.base.y;
          setConsumerType('quasi'); STATE.consK = 2;
          STATE.consPx = 1; STATE.consPy = 1; STATE.consI = 50; redrawAll();
          out.quX = STATE.cons.base.x; out.quY = STATE.cons.base.y;
          // Свойство квазилинейных: y не зависит от дохода.
          STATE.consI = 80; redrawAll();
          out.quY80 = STATE.cons.base.y; out.quX80 = STATE.cons.base.x;
          return out;`,
    checks: [['Кобб-Дуглас x*', 'cdX', 50, 0.05], ['Кобб-Дуглас y*', 'cdY', 25, 0.05],
             ['MRS = Px/Py', 'cdMrs', 0.5, 0.01],
             ['комплементы x*', 'coX', 10, 0.05], ['комплементы y*', 'coY', 20, 0.05],
             ['субституты x* (угол)', 'suX', 50, 0.05], ['субституты y*', 'suY', 0, 0.05],
             ['квазилинейные x*', 'quX', 49, 0.05], ['квазилинейные y*', 'quY', 1, 0.03],
             ['y не зависит от дохода', 'quY80', 1, 0.03], ['весь прирост в x', 'quX80', 79, 0.06]],
  },
  {
    name: 'Слуцкий · Кобб-Дуглас I=100, Py=1, Px 1→4 ⇒ замещение −18.75, доход −18.75',
    // x0 = 50 → компенсированный доход I′ = 4·50 + 1·50 = 250 → x = 31.25 → x1 = 12.5.
    run: `setMode('consumer'); setConsumerType('cobb');
          STATE.consA = 0.5; STATE.consB = 0.5;
          STATE.consPx = 1; STATE.consPy = 1; STATE.consI = 100;
          STATE.consSlutskyOn = true; STATE.consPx1 = 4; redrawAll();
          var c = STATE.cons, s = c.slutsky || {};
          return { x0: c.base.x, y0: c.base.y, Icomp: s.Icomp,
                   xc: (s.comp||{}).x, x1: (s.fin||{}).x,
                   sub: s.subX, inc: s.incX, tot: s.totX };`,
    checks: [['x₀', 'x0', 50, 0.05], ['y₀', 'y0', 50, 0.05], ['I′ компенсир.', 'Icomp', 250, 0.3],
             ['x компенсир.', 'xc', 31.25, 0.05], ['x₁ новый', 'x1', 12.5, 0.05],
             ['эффект замещения', 'sub', -18.75, 0.06], ['эффект дохода', 'inc', -18.75, 0.06],
             ['итого', 'tot', -37.5, 0.08]],
  },

  /* ── Фаза 9: производство, изокванты, долгий период ──────────────────── */
  {
    name: 'Производство · Q=30L²−L³: перегиб TP при L=10, максимум AP при L=15 (AP=MP=225)',
    run: `setMode('costs'); setCostsSub('production');
          STATE.prodExpr = '30*L^2 - L^3'; redrawAll();
          var p = STATE.prod || {};
          return { Lmp: (p.maxMP||{}).L, MP: (p.maxMP||{}).val,
                   Lap: (p.maxAP||{}).L, AP: (p.maxAP||{}).val, mpAtAp: p.mpAtMaxAP,
                   Ltp: (p.maxTP||{}).L };`,
    checks: [['L перегиба TP', 'Lmp', 10, 0.1], ['MP в максимуме', 'MP', 300, 1],
             ['L максимума AP', 'Lap', 15, 0.1], ['AP в максимуме', 'AP', 225, 1],
             ['MP там же = AP', 'mpAtAp', 225, 1], ['L максимума TP', 'Ltp', 20, 0.1]],
  },
  {
    name: 'Изокванты · Q=L^0.5·K^0.5, w=1, r=2, C=100 ⇒ L*=50, K*=25 (тот же движок, что у потребителя)',
    // Те же числа, что в кейсе потребителя, — это и есть доказательство переиспользования Фазы 7.
    run: `setMode('costs'); setCostsSub('isoquant');
          STATE.isoExpr = 'L^0.5 * K^0.5'; STATE.isoW = 1; STATE.isoR = 2; STATE.isoC = 100;
          redrawAll();
          var i = STATE.iso || {};
          return { L: i.L, K: i.K, Q: i.Q, mrts: i.mrts, spend: 1 * i.L + 2 * i.K };`,
    checks: [['L*', 'L', 50, 0.05], ['K*', 'K', 25, 0.05], ['выпуск Q', 'Q', 35.355, 0.03],
             ['MRTS = w/r', 'mrts', 0.5, 0.01], ['потрачен весь бюджет', 'spend', 100, 0.1]],
  },
  {
    name: 'Долгий период · TC=Q³−6Q²+15Q+18: при P=15 Q=4, ATC=11.5, прибыль +14; при P=8 — убыток',
    run: `setMode('costs'); setCostsSub('costs');
          STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 18'; STATE.costsFC = 18;
          STATE.lrOn = true; setLrPrice(15);
          var a = STATE.lr || {};
          var r1 = { Q: a.Q, atc: a.atc, profit: a.profit, be: a.breakeven };
          setLrPrice(8);
          var b = STATE.lr || {};
          return { Q: r1.Q, atc: r1.atc, profit: r1.profit, be: r1.be,
                   Q2: b.Q, loss: b.profit, shut: b.shutdown ? 1 : 0 };`,
    checks: [['Q при P=15', 'Q', 4, 0.05], ['ATC(4)', 'atc', 11.5, 0.05],
             ['прибыль', 'profit', 14, 0.2], ['P безубыточности = min ATC', 'be', 11.35, 0.1],
             ['Q при P=8', 'Q2', 3.291, 0.05], ['убыток < 0', 'loss', -11.7, 0.4],
             ['не закрывается (P > min AVC)', 'shut', 0, 0.1]],
  },

  /* ── Фаза 10: два завода (min-cost allocation + горизонтальная MC) ────── */
  {
    name: 'Два завода · TC₁=Q₁², TC₂=2Q₂² ⇒ при Q=30 делится 20/10, MC=40, TC=600',
    // MC₁=2Q₁, MC₂=4Q₂. В оптимуме MC₁=MC₂ ⇒ 2Q₁=4Q₂ и Q₁+Q₂=30 ⇒ 20 и 10.
    // Совокупная MC(Q) = (4/3)·Q: при Q=30 → 40, при Q=15 → 20 (делится 10/5),
    // TC(15) = 100 + 50 = 150 и то же самое даёт интеграл ∫MC.
    run: `setMode('costs'); setCostsSub('plants');
          STATE.pl1 = 'Q^2'; STATE.pl2 = '2*Q^2'; setPlantsQ(30);
          var a = plantsAt(30), b = plantsAt(15);
          var naive30 = plantTC(STATE.plants.c1, 30) + plantTC(STATE.plants.c2, 30);
          return { q1: a.q1, q2: a.q2, mc30: a.m, tc30: a.tcDirect, vc30: a.vc,
                   q1b: b.q1, q2b: b.q2, mc15: b.m, tc15: b.tcDirect, vc15: b.vc,
                   naive: naive30 };`,
    checks: [['Q₁ при Q=30', 'q1', 20, 0.15], ['Q₂ при Q=30', 'q2', 10, 0.15],
             ['MC₁=MC₂ при Q=30', 'mc30', 40, 0.3], ['TC(30) прямая сумма', 'tc30', 600, 4],
             ['TC(30) через ∫MC', 'vc30', 600, 4],
             ['Q₁ при Q=15', 'q1b', 10, 0.15], ['Q₂ при Q=15', 'q2b', 5, 0.15],
             ['MC при Q=15', 'mc15', 20, 0.3], ['TC(15) прямая сумма', 'tc15', 150, 2],
             ['TC(15) через ∫MC', 'vc15', 150, 2],
             ['«сумма в лоб» дороже', 'naive', 2700, 5]],
  },

  /* ── Фазы 12–13: двусторонняя монополия, коэффициент фондов ──────────── */
  {
    name: 'Двусторонняя монополия · D=100−L, S=L ⇒ диапазон зарплаты [33.33; 66.67], не точка',
    // Границы берутся из уже проверенных монопсонии и профсоюза-монополиста.
    // Кривые задаём явно: предыдущие кейсы могли оставить набор без роли S
    // (например «монополист и мировой рынок» держит D и MC), и тогда рынок труда
    // корректно откажется считать — это не баг, а недостроенная сцена.
    run: `setMode('labor');
          STATE.curves = [];
          addCurve('100 - L'); setRole(STATE.curves[0], 'demand');
          addCurve('L');       setRole(STATE.curves[1], 'supply');
          setLaborStruct('bilateral'); redrawAll();
          var b = STATE.laborBilateral || {};
          return { Wm: b.Wm, Wu: b.Wu, lo: b.Wlo, hi: b.Whi, Wk: b.Wk, Lm: b.Lm, Lu: b.Lu };`,
    checks: [['Wм (монопсония)', 'Wm', 33.33, 0.15], ['Wп (профсоюз)', 'Wu', 66.67, 0.2],
             ['нижняя граница', 'lo', 33.33, 0.15], ['верхняя граница', 'hi', 66.67, 0.2],
             ['конкурентный ориентир', 'Wk', 50, 0.2],
             ['Lм', 'Lm', 33.33, 0.15], ['Lп', 'Lu', 33.33, 0.25]],
  },
  {
    name: 'Коэф. фондов · доходы 10,15,20,25,30,35,40,50,70,150 ⇒ 150/10 = 15 (а P90/P10 = 5.38)',
    // Ровно 10 человек ⇒ дециль = один человек: нижний 10, верхний 150 ⇒ фонды 15.
    // Пороги P90/P10 — другая величина: 78 / 14.5 ≈ 5.38.
    run: `setMode('inequality'); setIneqInput('incomes');
          STATE.ineqRedistOn = false;
          STATE.ineqIncomes = '10, 15, 20, 25, 30, 35, 40, 50, 70, 150'; redrawAll();
          var s = STATE.ineqStats || {}, pp = inequalityP90P10() || {};
          return { funds: s.decile, same: s.funds, p90: pp.p90, p10: pp.p10, ratio: pp.ratio };`,
    checks: [['коэф. фондов', 'funds', 15, 0.05], ['алиас funds', 'same', 15, 0.05],
             ['P90', 'p90', 78, 0.2], ['P10', 'p10', 14.5, 0.1], ['P90/P10', 'ratio', 5.379, 0.03]],
  },

  /* ── Фазы 15–22: вертикальная кривая и макромодели ───────────────────── */
  {
    name: 'Вертикальная кривая · равновесие с ней берётся без бисекции',
    run: `var v = makeVerticalCurve(40);
          var D = { fn: function (q) { return 100 - q; } };
          var e1 = findEquilibrium(D, v), e2 = findEquilibrium(v, D);
          return { Q: e1.Q, P: e1.P, Q2: e2.Q, P2: e2.P,
                   isV: isVertical(v) ? 1 : 0, ev: isNaN(evalCurve(v, 10)) ? 1 : 0,
                   inv: invCurve(v, 999) };`,
    checks: [['Q', 'Q', 40, 0.01], ['P = D(40)', 'P', 60, 0.01],
             ['порядок аргументов не важен', 'Q2', 40, 0.01], ['P (обратный порядок)', 'P2', 60, 0.01],
             ['тип распознан', 'isV', 1, 0.1], ['P=f(Q) не определена', 'ev', 1, 0.1],
             ['обратная = atQ при любой цене', 'inv', 40, 0.01]],
  },
  {
    name: 'AD–AS · LRAS Y*=100, SRAS 10+0.5Y: AD 120−0.6Y без разрыва, 100−0.6Y и 140−0.6Y — по 18.2',
    run: `setMode('macro'); setMacroModel('adas');
          STATE.macro.adas.lras = 100; STATE.macro.adas.sras = '10 + 0.5*Y';
          STATE.macro.adas.ad = '120 - 0.6*Y'; redrawAll();
          var a = STATE.macroRes;
          var base = { Y: a.eq.Q, P: a.eq.P, gap: a.gap };
          STATE.macro.adas.ad = '100 - 0.6*Y'; redrawAll();
          var b = STATE.macroRes;
          STATE.macro.adas.ad = '140 - 0.6*Y'; redrawAll();
          var c = STATE.macroRes;
          STATE.macro.adas.ad = '120 - 0.6*Y'; redrawAll();
          return { Y0: base.Y, P0: base.P, gap0: base.gap,
                   Y1: b.eq.Q, P1: b.eq.P, gap1: b.gap,
                   Y2: c.eq.Q, gap2: c.gap };`,
    checks: [['Y базовый', 'Y0', 100, 0.3], ['P базовый', 'P0', 60, 0.3], ['разрыв = 0', 'gap0', 0, 0.3],
             ['Y при AD1', 'Y1', 81.82, 0.4], ['P при AD1', 'P1', 50.91, 0.4],
             ['рецессионный разрыв', 'gap1', -18.18, 0.4],
             ['Y при AD2', 'Y2', 118.18, 0.4], ['инфляционный разрыв', 'gap2', 18.18, 0.4]],
  },
  {
    name: 'Кривая Филлипса · πe=5, u*=5, β=0.5 ⇒ u=3→π=6, u=7→π=4, u=5→π=5',
    run: `setMode('macro'); setMacroModel('phillips');
          STATE.macro.phillips = { pe: 5, ustar: 5, beta: 0.5 }; redrawAll();
          var f = STATE.macroRes.f;
          return { p3: f(3), p7: f(7), p5: f(5), uStar: STATE.macroRes.eq.Q, piStar: STATE.macroRes.eq.P };`,
    checks: [['π при u=3', 'p3', 6, 0.02], ['π при u=7', 'p7', 4, 0.02], ['π при u=5', 'p5', 5, 0.02],
             ['пересечение при u*', 'uStar', 5, 0.02], ['и π=πe', 'piStar', 5, 0.02]],
  },
  {
    name: 'Денежный рынок · Md = 200 − 4i, Ms = 120 ⇒ i = 20',
    run: `setMode('macro'); setMacroModel('money');
          STATE.macro.money = { md: '200 - 4*i', ms: 120 }; redrawAll();
          return { i: STATE.macroRes.eq.P, M: STATE.macroRes.eq.Q };`,
    checks: [['ставка i', 'i', 20, 0.1], ['объём M = Ms', 'M', 120, 0.1]],
  },
  {
    name: 'Заёмные средства · S=50+2r, D=150−3r ⇒ r=20/Q=90; ΔG=30 ⇒ r=26, вытеснение 18',
    // Ключевое: частные инвестиции при новой ставке берутся по ИСХОДНОЙ кривой D,
    // а не по сдвинутой общей: 150 − 3·26 = 72, вытеснение 90 − 72 = 18.
    run: `setMode('macro'); setMacroModel('loanable');
          STATE.macro.loanable = { s: '50 + 2*r', d: '150 - 3*r', dg: 0 }; redrawAll();
          var b = STATE.macroRes.base;
          STATE.macro.loanable.dg = 30; redrawAll();
          var a = STATE.macroRes;
          return { r0: b.P, q0: b.Q, r1: a.eq.P, priv: a.privAfter, crowd: a.crowding };`,
    checks: [['базовая r', 'r0', 20, 0.1], ['базовый объём', 'q0', 90, 0.2],
             ['новая r', 'r1', 26, 0.15], ['частные инвестиции при r=26', 'priv', 72, 0.3],
             ['вытеснение', 'crowd', 18, 0.3]],
  },
  {
    name: 'Валютный рынок · D=100−2e, S=20+3e ⇒ плавающий e=16, объём 68',
    run: `setMode('macro'); setMacroModel('fx');
          STATE.macro.fx = { d: '100 - 2*e', s: '20 + 3*e', fixedOn: false, fixed: 20 }; redrawAll();
          var f = STATE.macroRes;
          STATE.macro.fx.fixedOn = true; STATE.macro.fx.fixed = 10; redrawAll();
          var g = STATE.macroRes.fixed || {};
          STATE.macro.fx.fixedOn = false; redrawAll();
          return { e: f.eq.P, q: f.eq.Q, Qd: g.Qd, Qs: g.Qs, gap: g.gap, def: g.deficit ? 1 : 0 };`,
    checks: [['плавающий курс e', 'e', 16, 0.1], ['объём', 'q', 68, 0.2],
             ['фикс. e=10: спрос', 'Qd', 80, 0.3], ['фикс. e=10: предложение', 'Qs', 50, 0.3],
             ['дефицит валюты', 'gap', 30, 0.4], ['именно дефицит', 'def', 1, 0.1]],
  },
  {
    name: 'Кривая Лаффера · D=100−Q, S=Q ⇒ максимум при t=50, поступления 1250',
    // Строится прогоном штатного расчёта равновесия с налогом: доход(t) = t·(100−t)/2.
    run: `setMode('macro'); setMacroModel('laffer');
          STATE.macro.laffer = { d: '100 - Q', s: 'Q', tmax: 100 }; redrawAll();
          var r = STATE.macroRes;
          // Значение кривой при t=20 должно равняться 20·80/2 = 800.
          var at20 = null, at80 = null;
          r.pts.forEach(function (p) {
            if (Math.abs(p[0] - 20) < 0.3 && at20 === null) at20 = p[1];
            if (Math.abs(p[0] - 80) < 0.3 && at80 === null) at80 = p[1];
          });
          return { t: r.best.t, rev: r.best.rev, Q: r.best.Q, at20: at20, at80: at80 };`,
    checks: [['ставка максимума', 't', 50, 0.6], ['максимум поступлений', 'rev', 1250, 5],
             ['объём при ней', 'Q', 25, 0.3], ['доход при t=20', 'at20', 800, 6],
             ['доход при t=80', 'at80', 800, 6]],
  },
  {
    name: 'IS–LM · IS r=20−0.1Y, LM r=0.05Y−5 ⇒ Y≈166.67, r≈3.33',
    run: `setMode('macro'); setMacroModel('islm');
          STATE.macro.islm = { is: '20 - 0.1*Y', lm: '0.05*Y - 5' }; redrawAll();
          return { Y: STATE.macroRes.eq.Q, r: STATE.macroRes.eq.P };`,
    checks: [['выпуск Y', 'Y', 166.67, 0.6], ['ставка r', 'r', 3.333, 0.1]],
  },

  // ── Раздел «Математика» (Фаза 7) ─────────────────────────────────────
  // Численные методы те же, что во всей остальной модели: центральная разность
  // для производных, сетка + бисекция для корней, трапеции для площади.
  // Поэтому проверяем их школьными примерами с известным ответом.
  {
    name: 'Математика · касательная к x² в точке 3 ⇒ y = 6x − 9',
    run: `setMode('math'); setMathSub('tangent');
          STATE.mathFormula='x^2'; setMathWindow(-6,6,-4,20); setMathX0(3);
          var f = mathF();
          return { k: dNum(f,3), y0: f(3), atZero: f(3) + dNum(f,3)*(0-3) };`,
    checks: [['f′(3)', 'k', 6, 0.01], ['f(3)', 'y0', 9, 0.01], ['касательная при x=0', 'atZero', -9, 0.02]],
  },
  {
    name: 'Математика · секущая стягивается к касательной при уменьшении Δx',
    run: `setMode('math'); setMathSub('tangent'); STATE.mathFormula='x^2';
          var f = mathF();
          var s = function(dx){ return (f(3+dx)-f(3))/dx; };
          return { big: s(2), small: s(0.05), tang: dNum(f,3) };`,
    checks: [['секущая при Δx=2', 'big', 8, 0.01], ['секущая при Δx=0.05', 'small', 6.05, 0.01],
             ['касательная', 'tang', 6, 0.01]],
  },
  {
    name: 'Математика · производная x³ в точке 2 ⇒ 12 (и 0 в нуле)',
    run: `setMode('math'); setMathSub('tangent'); STATE.mathFormula='x^3'; setMathWindow(-4,4,-20,20);
          var f = mathF(); return { k: dNum(f,2), k0: dNum(f,0) };`,
    checks: [['f′(2)', 'k', 12, 0.02], ['f′(0)', 'k0', 0, 0.01]],
  },
  {
    name: 'Математика · x³−3x: max при −1, min при 1, перегиб в 0',
    run: `setMode('math'); setMathSub('optimum'); STATE.mathFormula='x^3 - 3*x';
          setMathWindow(-3,3,-6,6); redrawAll();
          var a = STATE.mathRes;
          var mx = a.ext.filter(function(p){return p.kind==='max';})[0] || {};
          var mn = a.ext.filter(function(p){return p.kind==='min';})[0] || {};
          return { xmax: mx.x, ymax: mx.y, xmin: mn.x, ymin: mn.y,
                   inf: (a.inf[0]||{}).x, nInf: a.inf.length };`,
    checks: [['x максимума', 'xmax', -1, 0.02], ['значение в нём', 'ymax', 2, 0.03],
             ['x минимума', 'xmin', 1, 0.02], ['значение в нём', 'ymin', -2, 0.03],
             ['перегиб', 'inf', 0, 0.02], ['перегибов всего', 'nInf', 1, 0.01]],
  },
  {
    name: 'Математика · x²: ровно один минимум в нуле, перегибов нет',
    // Нуль производной попадает РОВНО в узел сетки — проверка «произведение
    // соседних значений меньше нуля» такой корень пропускала бы.
    run: `setMode('math'); setMathSub('optimum'); STATE.mathFormula='x^2';
          setMathWindow(-4,4,-2,16); redrawAll();
          var a = STATE.mathRes;
          return { n: a.ext.length, x: a.ext[0].x, isMin: a.ext[0].kind==='min'?1:0, nInf: a.inf.length };`,
    checks: [['экстремумов', 'n', 1, 0.01], ['x', 'x', 0, 0.02],
             ['это минимум', 'isMin', 1, 0.01], ['перегибов', 'nInf', 0, 0.01]],
  },
  {
    name: 'Математика · деформации: f(x+a) при a>0 уводит график ВЛЕВО',
    run: `setMode('math'); setMathSub('transform'); STATE.mathFormula='x^2';
          var f = mathF(); var t = mathTransformed(f,'left',2);
          return { atMinus2: t(-2), atPlus2: t(2), up: mathTransformed(f,'up',3)(0),
                   negY: mathTransformed(f,'negY',0)(2), absX: mathTransformed(f,'absX',0)(-3),
                   scaleY: mathTransformed(f,'scaleY',3)(2) };`,
    checks: [['f(x+2) при x=−2', 'atMinus2', 0, 0.001], ['f(x+2) при x=2', 'atPlus2', 16, 0.001],
             ['f(x)+3 при x=0', 'up', 3, 0.001], ['−f(x) при x=2', 'negY', -4, 0.001],
             ['f(|x|) при x=−3', 'absX', 9, 0.001], ['3·f(x) при x=2', 'scaleY', 12, 0.001]],
  },
  {
    name: 'Математика · Z = min(x², 4−x): смена ветви при x ≈ 1.5616',
    run: `setMode('math'); setMathSub('minmax'); STATE.mathFormula='x^2'; STATE.mathG2='4 - x';
          STATE.mathMinMax='min'; setMathWindow(-5,6,-3,12); redrawAll();
          var sw = STATE.mathRes.switches;
          return { n: sw.length, x: sw[sw.length-1] };`,
    checks: [['точек смены', 'n', 2, 0.01], ['правая точка', 'x', 1.5616, 0.01]],
  },
  {
    // Пресета «ограничение прямой» больше нет: прямая пишется как обычное
    // ограничение, переменные называются x и y.
    name: 'Математика · max x^0.5·y^0.5 при x+y=10 ⇒ (5; 5)',
    run: `setMode('math'); setMathSub('constraint');
          STATE.mathFC='x^0.5 * y^0.5'; STATE.mathGC='x + y = 10';
          STATE.mathConsWantMax = true; constraintFit(); redrawAll();
          var o = STATE.mathRes.opt || {};
          return { a: o.a, b: o.b, F: o.value };`,
    checks: [['x*', 'a', 5, 0.15], ['y*', 'b', 5, 0.15], ['f', 'F', 5, 0.15]],
  },
  {
    name: 'Математика · то же при 2x + y = 12 ⇒ (3; 6)',
    run: `setMode('math'); setMathSub('constraint');
          STATE.mathFC='x^0.5 * y^0.5'; STATE.mathGC='2*x + y = 12';
          STATE.mathConsWantMax = true; constraintFit(); redrawAll();
          var o = STATE.mathRes.opt || {};
          return { a: o.a, b: o.b };`,
    checks: [['x*', 'a', 3, 0.2], ['y*', 'b', 6, 0.3]],
  },
  {
    name: 'Площадь под кривой · D = 100 − Q на [0; 100] ⇒ 5000',
    run: `loadScene('sd'); redrawAll();
          setAreaCalcMode('curve');
          syncAreaCalcUI();
          document.getElementById('ac-pick').value = 'D';
          STATE.areaCalcList = []; runAreaCalc();
          var r = STATE.areaCalcList[0];
          return { S: r ? r.value : NaN };`,
    checks: [['площадь', 'S', 5000, 5]],
  },
  {
    name: 'Площадь по точкам · треугольник (0;0) (10;0) (0;10) ⇒ 50',
    // Вершины набираются щелчками по графику (Фаза 7); здесь ставим их через
    // ту же функцию, что и щелчок, — галочек в списке больше нет.
    run: `loadScene('sd'); redrawAll();
          clearAreaCalc(); setAreaCalcMode('poly'); clearAreaVerts();
          addAreaVert(0, 0, ''); addAreaVert(10, 0, ''); addAreaVert(0, 10, '');
          var armed = STATE.vertArm ? 1 : 0;
          runAreaCalc();
          var r0 = STATE.areaCalcList[0];
          var v = r0 ? r0.value : NaN;
          clearAreaVerts(); clearAreaCalc(); setAreaCalcMode('curve');
          return { S: v, armed: armed };`,
    checks: [['площадь', 'S', 50, 0.01], ['режим набора взведён', 'armed', 1, 0]],
  },
  {
    // Кроме равновесия в списке теперь и пересечения с осями: (100; 0), (0; 100), (0; 0).
    name: 'Пересечение кривых · D = 100 − Q и S = Q ⇒ (50; 50)',
    run: `loadScene('sd'); redrawAll();
          var all = STATE.crosses || [];
          var c = all.filter(function (p) {
            return Math.abs(p.x - 50) < 0.2 && Math.abs(p.y - 50) < 0.2; })[0] || {};
          return { x: c.x, y: c.y, n: all.length };`,
    checks: [['x', 'x', 50, 0.2], ['y', 'y', 50, 0.2], ['всего точек', 'n', 4, 0]],
  },
  {
    name: 'Формула в pgfplots · 100 − 2*Q ⇒ (100 - (2 * x))',
    run: `loadScene('sd');
          var got = mathToPgf('100 - 2*Q', 'Q');
          var bad = mathToPgf('Q < 20 ? 100 - Q : 60', 'Q');
          var root = mathToPgf('sqrt(Q)', 'Q');
          return { ok: (got === '(100 - (2 * x))') ? 1 : 0,
                   rootOk: (root === 'sqrt(x)') ? 1 : 0,
                   badIsNull: (bad === null) ? 1 : 0 };`,
    checks: [['линейная', 'ok', 1, 0], ['корень', 'rootOk', 1, 0], ['кусочная отклонена', 'badIsNull', 1, 0]],
  },
  {
    name: 'Кусочная функция · три куска с двумя границами ⇒ 90 / 60 / 20',
    run: `loadScene('sd');
          PW.inp = document.getElementById('inp-formula'); PW.v = 'Q'; PW.n = 3;
          PW.rows = [{f:'100 - Q', a:'0', b:'40'}, {f:'60', a:'40', b:'70'}, {f:'20', a:'70', b:''}];
          var r = compileFormula(pwFormula());
          var at = function (q) { return r.compiled.evaluate({ x: q, Q: q, L: q }); };
          var back = compileFormula(latexToMath(pwLatex()));
          var atB = function (q) { return back.compiled.evaluate({ x: q, Q: q, L: q }); };
          return { a: at(10), b: at(50), c: at(90), ba: atB(10), bb: atB(50), bc: atB(90) };`,
    checks: [['f(10)', 'a', 90, 0.01], ['f(50)', 'b', 60, 0.01], ['f(90)', 'c', 20, 0.01],
             ['скобка f(10)', 'ba', 90, 0.01], ['скобка f(50)', 'bb', 60, 0.01], ['скобка f(90)', 'bc', 20, 0.01]],
  },
  {
    // Сессия 22.08: «Поставить в поле» стирало приставку «y = » целиком, и
    // разбор КПВ путал «>=» условия куска с настоящим знаком равенства без
    // своего «=» перед ним — собранная запись оставалась непринятой.
    name: 'Конструктор кусочной · КПВ принимает собранную запись (приставка «y =» сохранена)',
    run: `pickScene('ppf');
          var inp = document.getElementById('inp-ppf');
          openPiecewise(inp, 'x');
          PW.n = 2;
          PW.rows = [{f:'100 - x', a:'0', b:'50'}, {f:'75 - 0.5*x', a:'50', b:''}];
          document.getElementById('pw-apply').click();
          var hasPrefix = /^y\\s*=/.test(inp.value) ? 1 : 0;
          var r = parsePpfEquation(STATE.ppfFormula);
          var errOk = r.error ? 0 : 1;
          return { value: inp.value, hasPrefix: hasPrefix, errOk: errOk,
                   y40: errOk ? r.f(40) : null, y60: errOk ? r.f(60) : null };`,
    checks: [['приставка «y =» сохранена (флаг)', 'hasPrefix', 1, 0],
             ['разбор без ошибки (флаг)', 'errOk', 1, 0],
             ['y(40) = 100−40 (первый кусок)', 'y40', 60, 0.5],
             ['y(60) = 75−0,5·60 (второй кусок)', 'y60', 45, 0.5]],
  },
  {
    name: 'Конструктор кусочной · «Неравенство доходов» принимает собранную запись (без приставки)',
    run: `setMode('inequality'); setIneqInput('formula');
          var inp = document.getElementById('ineq-formula');
          inp.value = 'p^2';
          document.getElementById('ineq-formula-apply').click();
          var before = STATE.ineqFormula;
          openPiecewise(inp, 'p');
          PW.n = 2;
          PW.rows = [{f:'0.5*p', a:'0', b:'0.5'}, {f:'p - 0.25', a:'0.5', b:''}];
          document.getElementById('pw-apply').click();
          var changed = (STATE.ineqFormula !== before) ? 1 : 0;
          return { before: before, after: STATE.ineqFormula, changed: changed,
                   lorenzLen: (STATE.ineqLorenz || []).length };`,
    checks: [['формула сменилась (флаг)', 'changed', 1, 0],
             ['точек кривой посчитано', 'lorenzLen', 101, 5]],
  },
  {
    // pwVarForField читает букву условия из ТЕКУЩЕЙ формулы поля, а не из
    // статичной FORMULA_VAR[вид поля] — та не различала рынок труда (всегда
    // «Q», хотя формулы там пишут через L) и три macro-сюжета под одним
    // ярлыком «MACRO» (i / r / Y). Три поля из карточки «10 полей в 8 сценах».
    name: 'Конструктор кусочной · условие берёт букву САМОЙ формулы, а не угадайку по виду поля',
    run: `setMode('labor'); setLaborStruct('competition'); redrawAll();
          var laborLetter = pwVarForField(document.getElementById('curve-expr-1'), 'FALLBACK');
          setMode('macro'); setMacroModel('money'); redrawAll();
          var moneyLetter = pwVarForField(document.getElementById('ma-md'), 'FALLBACK');
          setMode('inequality'); setIneqInput('formula'); redrawAll();
          var ineqLetter = pwVarForField(document.getElementById('ineq-formula'), 'FALLBACK');
          return { laborLetter: laborLetter, moneyLetter: moneyLetter, ineqLetter: ineqLetter,
                   laborOk: (laborLetter === 'L') ? 1 : 0,
                   moneyOk: (moneyLetter === 'i') ? 1 : 0,
                   ineqOk: (ineqLetter === 'p') ? 1 : 0 };`,
    checks: [['Конкурентный рынок труда: буква L, не Q (флаг)', 'laborOk', 1, 0],
             ['Денежный рынок: буква i, не Y (флаг)', 'moneyOk', 1, 0],
             ['Неравенство доходов: буква p, не x (флаг)', 'ineqOk', 1, 0]],
  },
  {
    // ppfSlopeOf брала центральную разность и лезла за границу домена, когда
    // угловое решение КТВ стоит ровно на Xmax: interpY честно не экстраполирует
    // за [0, Xmax] и отдавала NaN. Прогон — ровно репродукция бага 22.08.
    name: 'КТВ. Одна страна · «Внутренняя цена X» — конечное число при кусочной КПВ (не NaN)',
    run: `pickScene('trade');
          STATE.ppftFormula = 'x < 50 ? 100 - x : 75 - 0.5*x';
          recomputePpfTrade();
          var d = STATE.ppfTradeData;
          var inner = (d.c.type === 'linear' && d.c.b > 0) ? d.c.b
            : ((d.xp != null && d.xp > 0)
                ? Math.abs(ppfSlopeOf(function (x) { return interpY(d.ppfPts, x); }, d.xp))
                : (d.Ymax / d.Xmax));
          return { xp: d.xp, isFiniteFlag: (typeof inner === 'number' && isFinite(inner)) ? 1 : 0, inner: inner };`,
    checks: [['xp = Xmax (угловое решение на границе)', 'xp', 150, 0.5],
             ['внутренняя цена — конечное число (флаг)', 'isFiniteFlag', 1, 0],
             ['внутренняя цена = 0,5 (наклон второго отрезка)', 'inner', 0.5, 0.01]],
  },
  {
    name: 'Ползунок параметра · k*Q при k = 3 ⇒ 30 в точке 10',
    run: `loadScene('sd');
          STATE.curves = []; STATE.params = {};
          addCurve('k*Q'); redrawAll();
          var c = STATE.curves[STATE.curves.length - 1];
          var v1 = evalCurve(c, 10);
          STATE.params.k.value = 3; redrawAll();
          var v3 = evalCurve(c, 10);
          return { v1: v1, v3: v3, n: Object.keys(STATE.params).length };`,
    checks: [['k = 1', 'v1', 10, 0.01], ['k = 3', 'v3', 30, 0.01], ['ползунков', 'n', 1, 0]],
  },
  {
    name: 'Ползунков нет там, где буква занята · сцена налога',
    run: `loadScene('tax'); redrawAll();
          return { n: Object.keys(STATE.params || {}).length, Q: STATE.eq.Q };`,
    checks: [['ползунков', 'n', 0, 0], ['равновесие', 'Q', 50, 0.3]],
  },
  {
    name: 'Наименьшая из трёх · min(x, 4 − x, 2) меняет ветвь при x = 2',
    run: `setMode('math'); setMathSub('minmax');
          STATE.mathFormula = 'x'; STATE.mathG2 = '4 - x'; STATE.mathG3 = '2'; STATE.mathG4 = '';
          STATE.mathMinMax = 'min'; setMathWindow(-1, 6, -1, 6); redrawAll();
          var r = STATE.mathRes;
          return { n: r.count, sw: (r.switches || [])[0], k: (r.switches || []).length };`,
    checks: [['функций', 'n', 3, 0], ['смена ветви', 'sw', 2, 0.05], ['точек смены', 'k', 1, 0]],
  },
  {
    name: 'Оптимум при кривом ограничении · max x·y на x² + y² = 25 ⇒ 12.5',
    run: `setMode('math'); setMathSub('constraint');
          STATE.mathFC = 'x*y'; STATE.mathGC = 'x^2 + y^2 = 25';
          STATE.mathConsWantMax = true; constraintFit(); redrawAll();
          var o = STATE.mathRes.opt || {};
          return { a: o.a, b: o.b, v: o.value };`,
    checks: [['x*', 'a', 3.536, 0.06], ['y*', 'b', 3.536, 0.06], ['f', 'v', 12.5, 0.05]],
  },
  {
    // Минимум ищется так же, как максимум, только выбор другой.
    name: 'Минимум при ограничении · min x² + y² на x + y = 10 ⇒ (5; 5)',
    run: `setMode('math'); setMathSub('constraint');
          STATE.mathFC = 'x^2 + y^2'; STATE.mathGC = 'x + y = 10';
          STATE.mathConsWantMax = false; constraintFit(); redrawAll();
          var o = STATE.mathRes.opt || {};
          return { a: o.a, b: o.b, v: o.value };`,
    checks: [['x*', 'a', 5, 0.15], ['y*', 'b', 5, 0.15], ['f', 'v', 50, 1]],
  },
  {
    // Math.js читает «bx» как ОДНО имя переменной, поэтому параметр звался «bx».
    // Теперь склейка букв раскрывается в произведение ещё до разбора.
    name: 'Параметр из bx^2 · это b, а не bx',
    run: `loadScene('sd');
          STATE.curves = []; STATE.params = {};
          addCurve('bx^2'); redrawAll();
          var names = Object.keys(STATE.params).sort();
          var c = STATE.curves[STATE.curves.length - 1];
          var v1 = evalCurve(c, 3);
          STATE.params.b.value = 2; redrawAll();
          var v2 = evalCurve(c, 3);
          return { n: names.length, first: names[0] === 'b' ? 1 : 0, v1: v1, v2: v2 };`,
    checks: [['параметров', 'n', 1, 0], ['имя = b', 'first', 1, 0],
             ['b = 1 ⇒ 9', 'v1', 9, 0.01], ['b = 2 ⇒ 18', 'v2', 18, 0.01]],
  },
  {
    // Свободный член: раньше «c» была занята словарём Math.js и ползунка не давала.
    name: 'Параметр из x^2 + 5 + c · свободный член заводится',
    run: `loadScene('sd');
          STATE.curves = []; STATE.params = {};
          addCurve('x^2 + 5 + c'); redrawAll();
          var names = Object.keys(STATE.params).sort();
          var c = STATE.curves[STATE.curves.length - 1];
          var v1 = evalCurve(c, 2);
          STATE.params.c.value = 10; redrawAll();
          var v2 = evalCurve(c, 2);
          return { n: names.length, first: names[0] === 'c' ? 1 : 0, v1: v1, v2: v2 };`,
    checks: [['параметров', 'n', 1, 0], ['имя = c', 'first', 1, 0],
             ['c = 1 ⇒ 10', 'v1', 10, 0.01], ['c = 10 ⇒ 19', 'v2', 19, 0.01]],
  },
  {
    // Экономические обозначения остаются одним именем: MC это не M·C.
    name: 'MC не рассыпается на буквы · сцена свободного холста',
    run: `loadScene('sd');
          STATE.curves = []; STATE.params = {};
          addCurve('MC + 2*Q'); redrawAll();
          return { n: Object.keys(STATE.params).length,
                   mc: STATE.params.MC ? 1 : 0 };`,
    checks: [['параметров', 'n', 1, 0], ['имя = MC', 'mc', 1, 0]],
  },
  {
    // Пересечения считаются и между кривыми, и с осями координат.
    name: 'Пересечения с осями · D = 100 − Q даёт (100; 0) и (0; 100)',
    run: `loadScene('sd');
          STATE.curves = []; STATE.params = {};
          addCurve('100 - Q'); redrawAll();
          var pts = crossPoints();
          var onX = pts.filter(function (p) { return Math.abs(p.y) < 1e-6; })[0] || {};
          var onY = pts.filter(function (p) { return Math.abs(p.x) < 1e-6; })[0] || {};
          return { n: pts.length, xq: onX.x, yp: onY.y };`,
    checks: [['точек', 'n', 2, 0], ['на оси Q', 'xq', 100, 0.05], ['на оси P', 'yp', 100, 0.05]],
  },
  {
    // Раньше сцена строила свои шкалы на каждой перерисовке и не масштабировалась.
    name: 'Ограничение · колесо меняет масштаб сцены',
    run: `setMode('math'); setMathSub('constraint');
          STATE.mathFC = 'x*y'; STATE.mathGC = 'x + y = 10';
          STATE.mathConsWantMax = true; constraintFit(); redrawAll();
          var before = STATE.mathXmax - STATE.mathXmin;
          zoomBy(0.5, 400, 300); redrawAll();
          var after = STATE.mathXmax - STATE.mathXmin;
          return { ratio: after / before, opt: (STATE.mathRes.opt || {}).a };`,
    checks: [['окно сжалось вдвое', 'ratio', 0.5, 0.02], ['оптимум на месте', 'opt', 5, 0.2]],
  },
  {
    // Функций может быть больше четырёх, и результат зовут как хочется.
    name: 'min из пяти функций · нижняя огибающая в точке 3 равна 1',
    run: `setMode('math'); setMathSub('minmax');
          STATE.mmCount = 5; STATE.mmName = 'y';
          STATE.mathFormula = 'x'; STATE.mathG2 = '10 - x'; STATE.mathG3 = '4';
          STATE.mathG4 = 'x^2'; STATE.mathGmore = ['1'];
          setMathWindow(0, 8, -1, 12); redrawAll();
          var r = STATE.mathRes;
          return { count: r.count, err: r.error ? 1 : 0 };`,
    checks: [['функций', 'count', 5, 0], ['без ошибки', 'err', 0, 0]],
  },
  {
    // Панели сюжета про производную независимы: зум над одной не трогает другую.
    name: 'Производная · зум над верхней панелью не двигает нижнюю',
    run: `setMode('math'); setMathSub('tangent'); resetZoom(); redrawAll();
          var L = tangentLayout();
          var b0 = JSON.stringify(tanWin('bot'));
          zoomBy(0.5, 400, (L.top + L.yMid) / 2);
          var top = tanWin('top'), bot = tanWin('bot');
          return { topSpan: top.xmax - top.xmin,
                   botSame: (JSON.stringify(bot) === b0) ? 1 : 0 };`,
    checks: [['верхняя сжалась', 'topSpan', 6, 0.6], ['нижняя не тронута', 'botSame', 1, 0]],
  },
  {
    name: 'Производная · зум над нижней панелью не двигает верхнюю',
    run: `setMode('math'); setMathSub('tangent'); resetZoom(); redrawAll();
          var L = tangentLayout();
          var t0 = JSON.stringify(tanWin('top'));
          zoomBy(0.5, 400, (L.botTop + L.bottom) / 2);
          var bot = tanWin('bot');
          return { botSpan: bot.xmax - bot.xmin,
                   topSame: (JSON.stringify(tanWin('top')) === t0) ? 1 : 0 };`,
    checks: [['нижняя сжалась', 'botSpan', 6, 0.6], ['верхняя не тронута', 'topSame', 1, 0]],
  },
  {
    // Точку ведут и снизу: касательная сверху идёт за ней.
    name: 'Производная · точка снизу перестраивает касательную сверху',
    run: `setMode('math'); setMathSub('tangent'); resetZoom();
          STATE.mathFormula = 'x^2'; setMathX0(1); redrawAll();
          var k1 = STATE.mathRes.k;
          setMathX0(3); redrawAll();
          var r = STATE.mathRes;
          return { k1: k1, k3: r.k, y3: r.y0, x3: r.x0 };`,
    checks: [['наклон в 1', 'k1', 2, 0.02], ['наклон в 3', 'k3', 6, 0.02],
             ['f(3)', 'y3', 9, 0.02], ['x₀', 'x3', 3, 0.001]],
  },
  {
    // Шаг секущей опускается заметно ниже прежних 0.05.
    name: 'Производная · при малом Δx секущая почти совпала с касательной',
    run: `setMode('math'); setMathSub('tangent'); resetZoom();
          STATE.mathFormula = 'x^2'; setMathX0(2); STATE.mathSecant = true;
          STATE.mathDx = 0.001; redrawAll();
          var r = STATE.mathRes;
          return { k: r.k, sec: r.secant, diff: Math.abs(r.secant - r.k) };`,
    checks: [['касательная', 'k', 4, 0.01], ['секущая', 'sec', 4.001, 0.01],
             ['разница', 'diff', 0.001, 0.0005]],
  },
  {
    // Фаза 3: прокатывание не выезжает за осмысленную область кривой. На КПВ
    // 100 − X правее X = 100 кривой нет, левее нуля тоже.
    name: 'Прокатывание · на КПВ точка не уходит в отрицательную зону',
    run: `setMode('ppf'); setPpfSub('single');
          STATE.ppfFormula = '100 - X'; redrawAll();
          var t = snapTargets()[0];
          return { right: rollerClampX(t.f, 200), left: rollerClampX(t.f, -5),
                   yEdge: t.f(rollerClampX(t.f, 200)) };`,
    checks: [['правый край', 'right', 100, 0.5], ['левый край', 'left', 0, 0.001],
             ['y на краю', 'yEdge', 0, 0.5]],
  },
  {
    // Фаза 2: буква в формуле экономической сцены даёт ползунок, а не ошибку.
    name: 'Параметр в спросе · «a - Q» заводит ползунок a',
    run: `loadScene('sd'); STATE.params = {};
          var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
          updateCurveExpr(d, 'a - Q'); redrawAll();
          var names = Object.keys(STATE.params);
          var v1 = evalCurve(STATE.curves.find(function (c) { return c.role === 'demand'; }), 10);
          STATE.params.a.value = 80; redrawAll();
          var v2 = evalCurve(STATE.curves.find(function (c) { return c.role === 'demand'; }), 10);
          return { n: names.length, isA: names[0] === 'a' ? 1 : 0, v1: v1, v2: v2 };`,
    checks: [['параметров', 'n', 1, 0], ['имя = a', 'isA', 1, 0],
             ['a = 1 ⇒ −9', 'v1', -9, 0.01], ['a = 80 ⇒ 70', 'v2', 70, 0.01]],
  },
  {
    /* П21. Параметр в КПВ раньше ломал сцену: формула разбиралась, а каждый
       расчёт точки падал на неизвестной букве и отдавал NaN, поэтому границы
       КПВ не находились и холст оставался пустым. Проверяем ровно то, что
       обещано: при a = 1 картинка совпадает с «100 - X», при a = 2 наклон
       меняется вдвое. Через ppfEvalWith идут все четыре сцены КПВ и КТВ. */
    name: 'Параметр в КПВ · «100 - a*X» строится и меняет наклон',
    run: `openPicker(); pickScene('trade'); closePicker();
          STATE.params = {};
          var inp = document.getElementById('inp-ppft');
          var apply = document.getElementById('btn-ppft-apply');
          inp.value = '100 - X'; inp.dispatchEvent(new Event('input', { bubbles: true })); apply.click();
          var plain = STATE.ppfTradeData.Xmax;
          inp.value = '100 - a*X'; inp.dispatchEvent(new Event('input', { bubbles: true })); apply.click();
          var ok1 = STATE.ppfTradeData.ok ? 1 : 0;
          var x1 = STATE.ppfTradeData.Xmax;
          STATE.params.a.value = 2; redrawAll();
          var x2 = STATE.ppfTradeData.Xmax;
          return { plain: plain, ok1: ok1, x1: x1, x2: x2 };`,
    checks: [['«100 - X» даёт Xmax = 100', 'plain', 100, 0.01],
             ['с параметром сцена строится', 'ok1', 1, 0],
             ['a = 1 ⇒ тот же Xmax', 'x1', 100, 0.01],
             ['a = 2 ⇒ Xmax вдвое меньше', 'x2', 50, 0.01]],
  },
  {
    /* П36–П37. Договорённость о ключевых точках: пересечения, изломы и
       экстремумы — да, перегибы — нет. Излом кусочной кривой раньше не
       находился совсем: скачок наклона размазывался по двум узлам сетки и не
       проходил порог. Проверяем и сам факт, и точное место стыка.

       ⚠️ ПРОВЕРКА ПЕРЕСЧИТАНА 19.08, А НЕ ОТКЛЮЧЕНА. Прежде она требовала,
       чтобы точки были НА ХОЛСТЕ сразу после перерисовки. Это больше не так и
       не по недосмотру: решением владельца автоматических ключевых точек по
       умолчанию на холсте нет вовсе, они загораются щелчком по своей кривой.
       Прежняя часть про излом (что он найден, где именно и что перегибы не
       считаются) в силе целиком — она про РАСЧЁТ. Добавлено новое требование:
       до взведения точек нет, после взведения кривой её излом появляется.
       Правило П37 «излом показывается сразу, без щелчка» этим отменено:
       общее правило сильнее частного. */
    name: 'Ключевые точки · излом кусочной кривой найден в точке стыка',
    run: `openPicker(); pickScene('sd'); closePicker();
          var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
          updateCurveExpr(d, 'Q < 40 ? 100 - Q : 80 - 0.5*Q'); redrawAll();
          var k = keyTargets();
          var kinks = k.filter(function (p) { return p.kind === 'kink'; });
          var infl = k.filter(function (p) { return /перегиб/.test(p.name); });
          var idle = document.querySelectorAll('.crosses circle').length;
          armCurve(curveShortName(d));
          var lit = document.querySelectorAll('.crosses circle').length;
          var mine = keyTargets().filter(keyPointLit)
                       .filter(function (p) { return p.kind === 'kink'; }).length;
          return { n: kinks.length, x: kinks.length ? kinks[0].x : -1,
                   y: kinks.length ? kinks[0].y : -1, infl: infl.length,
                   idle: idle, lit: lit > 0 ? 1 : 0, mine: mine };`,
    checks: [['излом ровно один', 'n', 1, 0], ['стык при Q = 40', 'x', 40, 0.2],
             ['цена в стыке 60', 'y', 60, 0.2], ['перегибов не отмечаем', 'infl', 0, 0],
             ['без щелчка на холсте точек нет', 'idle', 0, 0],
             ['после щелчка по кривой точки загорелись', 'lit', 1, 0],
             ['излом среди загоревшихся', 'mine', 1, 0]],
  },
  {
    /* П28. Пайплайн добавления точки: кнопка → тумблер → два поля координат.
       Точка появляется, как только заполнены ОБА поля, и переезжает на каждый
       введённый символ. Кнопка «Добавить точку» стоит ПОД созданными точками. */
    name: 'Точки · точка появляется, как только заполнены оба поля',
    run: `openPicker(); pickScene('sd'); closePicker();
          STATE.marks = []; renderMarkList();
          var box = document.getElementById('mark-list');
          var only = box.children.length === 1 && box.firstElementChild.classList.contains('btn-mark-add') ? 1 : 0;
          box.querySelector('.btn-mark-add').click();
          var noBtn = box.querySelector('.btn-mark-add') ? 0 : 1;
          /* Н36, Н47: координаты — не поля в рамке, а редактируемые значения
             (contenteditable внутри .edval). Печатаем в них так же, как человек:
             ставим текст и будим «input». */
          var f = box.querySelectorAll('.mark-draft .mark-xy .edval');
          function type(el, text) {
            el.click();                                   // открыть правку на месте
            el.textContent = text;
            el.dispatchEvent(new Event('input', { bubbles: true }));
          }
          type(f[0], '50');
          var half = STATE.marks.filter(function (m) { return !m.pending; }).length;
          type(f[1], '5');
          var live = STATE.marks.filter(function (m) { return !m.pending; })[0];
          var y1 = live ? live.y : -1;
          type(f[1], '50');
          var y2 = STATE.marks.filter(function (m) { return !m.pending; })[0].y;
          var back = document.getElementById('mark-list').querySelector('.btn-mark-add') ? 1 : 0;
          var lastIsBtn = document.getElementById('mark-list').lastElementChild.classList.contains('btn-mark-add') ? 1 : 0;
          return { only: only, noBtn: noBtn, half: half, y1: y1, y2: y2, back: back, last: lastIsBtn };`,
    checks: [['сначала только кнопка', 'only', 1, 0], ['после щелчка кнопки нет', 'noBtn', 1, 0],
             ['одно поле — точки нет', 'half', 0, 0], ['«5» ⇒ точка (50; 5)', 'y1', 5, 0.001],
             ['дописали «0» ⇒ (50; 50)', 'y2', 50, 0.001],
             ['кнопка вернулась', 'back', 1, 0], ['и стоит последней', 'last', 1, 0]],
  },
  {
    /* П43. Площадь по отмеченным точкам — НАИБОЛЬШАЯ из возможных без
       самопересечений, при этом вершинами остаются ВСЕ отмеченные точки
       (выпуклую оболочку не берём). Прежняя сортировка по углу вокруг центра
       тяжести на 3000 случайных пятёрках проигрывала перебору в 673 случаях.
       Контрольный набор — худший из найденных. */
    name: 'Площадь · по пяти точкам берётся наибольшая, а не по углу',
    run: `openPicker(); pickScene('sd'); closePicker();
          var pts = [[60,58],[61,17],[94,90],[70,20],[7,89]].map(function (p) {
            return { x: p[0], y: p[1], name: '' }; });
          var best = bestAreaRing(pts);
          var byAngle = ringArea(angleRing(pts));
          var self = ringSelfCrosses(best.ring) ? 1 : 0;
          // Внутренний набор: квадрат с точкой внутри — все пять остаются вершинами.
          var sq = [[0,0],[40,0],[40,40],[0,40],[20,15]].map(function (p) {
            return { x: p[0], y: p[1], name: '' }; });
          var sqBest = bestAreaRing(sq);
          return { best: ringArea(best.ring), angle: byAngle, exact: best.exact ? 1 : 0,
                   self: self, n: best.ring.length,
                   sq: ringArea(sqBest.ring), sqN: sqBest.ring.length };`,
    checks: [['перебор даёт 3252', 'best', 3252, 1],
             ['сортировка по углу дала бы 2063', 'angle', 2063, 1],
             ['до восьми вершин перебор точный', 'exact', 1, 0],
             ['самопересечений нет', 'self', 0, 0],
             ['вершины все пять', 'n', 5, 0],
             ['квадрат с точкой внутри ⇒ 1300', 'sq', 1300, 0.01],
             ['и в нём тоже все пять', 'sqN', 5, 0]],
  },
  {
    /* П41, П42, П44. Кнопка расчёта заперта, пока считать нечего; отрезок
       показан рядом с выбором кривой; в таблице два столбца. */
    name: 'Площадь · кнопка заперта до выбора, отрезок и таблица',
    run: `openPicker(); pickScene('sd'); closePicker();
          clearAreaCalc(); clearAreaVerts(); setAreaCalcMode('curve');
          syncAreaCalcUI();
          var btn = document.getElementById('ac-calc');
          var lockedCurve = btn.disabled ? 1 : 0;
          var sel = document.getElementById('ac-pick');
          sel.value = 'D'; syncAreaRangeLabel(); syncAreaCalcButton();
          var openCurve = btn.disabled ? 0 : 1;
          /* Н51, Н52: отрезок стал редактируемым, обе границы набраны формулой.
             Читаем сами значения, а не строку целиком: у KaTeX в textContent
             рядом с видимой записью лежат MathML и исходный TeX. */
          var rangeEl = document.getElementById('ac-range');
          var rangeNums = [].map.call(rangeEl.querySelectorAll('.edval'), function (e) {
            var h = e.querySelector('.katex-html');
            return (h ? h.textContent : e.textContent).trim();
          });
          var range = '[' + rangeNums.join('; ') + ']';
          var rangeEditable = rangeEl.querySelectorAll('.edval').length;
          btn.click();
          var head = [].map.call(document.querySelectorAll('.area-head span'),
                                 function (s) { return s.textContent; }).join('|');
          var areaVal = STATE.areaCalcList[0].value;
          setAreaCalcMode('poly');
          var lockedPoly = btn.disabled ? 1 : 0;
          addAreaVert(0, 0, ''); addAreaVert(10, 0, ''); addAreaVert(10, 10, '');
          var openPoly = btn.disabled ? 0 : 1;
          var crosses = document.querySelectorAll('.vert-row .btn-icon').length;
          // Возвращаем секцию в исходное состояние: следующие случаи считают
          // площадь под кривой, а оставленный режим «между точками» их сломал бы.
          clearAreaVerts(); setAreaCalcMode('curve'); clearAreaCalc();
          return { lockedCurve: lockedCurve, openCurve: openCurve, lockedPoly: lockedPoly,
                   openPoly: openPoly, area: areaVal,
                   rangeOk: range === '[0; 100]' ? 1 : 0,
                   rangeEd: rangeEditable,
                   headOk: head === 'Название|Площадь|' ? 1 : 0,
                   verts: crosses };`,
    checks: [['без кривой кнопка заперта', 'lockedCurve', 1, 0],
             ['выбрали кривую — открылась', 'openCurve', 1, 0],
             ['отрезок [0; 100]', 'rangeOk', 1, 0],
             ['и обе границы правятся (Н52)', 'rangeEd', 2, 0],
             ['площадь под D = 5000', 'area', 5000, 1],
             ['заголовки «Название» и «Площадь» (Н53)', 'headOk', 1, 0],
             ['без вершин кнопка заперта', 'lockedPoly', 1, 0],
             ['три вершины — открылась', 'openPoly', 1, 0],
             ['у каждой вершины крестик', 'verts', 3, 0]],
  },
  {
    /* П40. Разбор построен как вопрос с ответом, и кусочная кривая его не
       ломает. Контрольная КПВ «x < 50 ? 100 − x : 75 − 0.5x»: излом при 50,
       пересечение с осью X при 150, издержки ПАДАЮТ с 1 до 0.5 — значит
       кривая выпуклая, а не вогнутая (раньше всё, что не прямая, называлось
       вогнутым, и подпись противоречила таблице под ней). */
    name: 'Разбор · вопрос в начале абзаца и кусочная КПВ',
    run: `resetSceneMemory(); openPicker(); pickScene('ppf'); closePicker();
          var inp = document.getElementById('inp-ppf');
          inp.value = 'y = x < 50 ? 100 - x : 75 - 0.5*x';
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          document.getElementById('btn-ppf-apply').click();
          var f = parsePpfEquation(STATE.ppfFormula).f;
          var ex = document.getElementById('ex-body');
          var qs = [].map.call(ex.querySelectorAll('p > b'), function (b) { return b.textContent.trim(); });
          /* Форма разбора: каждый абзац с заголовком начинается ВОПРОСОМ,
             кроме последнего — он начинается со слова «Вывод». Раньше здесь
             стояло точное число абзацев (3), и любое дополнение разбора роняло
             проверку формы, хотя форма как раз соблюдена. Считаем нарушения. */
          var bad = qs.filter(function (s) { return !/\\?$/.test(s) && !/^Вывод/.test(s); }).length;
          var junk = /NaN|undefined|Infinity/.test(ex.textContent) ? 1 : 0;
          return { f60: f(60), xmax: ppfXmaxOf(f),
                   type: /выпуклая/.test(ppfTypeLabel()) ? 1 : 0,
                   qs: qs.length, bad: bad,
                   hasConcl: qs.some(function (s) { return /^Вывод/.test(s); }) ? 1 : 0,
                   junk: junk };`,
    checks: [['кусочная считается верно', 'f60', 45, 0.01],
             ['и кончается там, где надо', 'xmax', 150, 0.5],
             ['тип КПВ выпуклая, а не вогнутая', 'type', 1, 0],
             ['абзацев с заголовком не меньше трёх', 'qs', 5, 2],
             ['есть абзац «Вывод»', 'hasConcl', 1, 0],
             ['нарушений формы', 'bad', 0, 0],
             ['мусора в разборе нет', 'junk', 0, 0]],
  },
  {
    /* П20, П51. При переходе между моделями настройки сбрасываются ВСЕГДА, а
       возврат в модель возвращает именно её изменения. Раньше площади,
       галочки заливок и цвета переживали смену сцены и всплывали в чужой
       модели, а собственной памяти у моделей не было вовсе. */
    name: 'Сцены · переход чистит, возврат возвращает своё',
    run: `resetSceneMemory();
          openPicker(); pickScene('sd'); closePicker();
          setAreaCalcMode('curve'); syncAreaCalcUI();
          document.getElementById('ac-pick').value = 'D'; syncAreaCalcButton();
          document.getElementById('ac-calc').click();
          addMarkAt(30, 70, null);
          STATE.showCS = false; STATE.labelSize = 18; redrawAll();
          var mine = { a: STATE.areaCalcList.length, m: STATE.marks.length,
                       cs: STATE.showCS ? 1 : 0, s: STATE.labelSize };
          openPicker(); pickScene('mono'); closePicker();
          var clean = { a: STATE.areaCalcList.length, m: STATE.marks.length,
                        cs: STATE.showCS ? 1 : 0, s: STATE.labelSize };
          openPicker(); pickScene('sd'); closePicker();
          var back = { a: STATE.areaCalcList.length, m: STATE.marks.length,
                       cs: STATE.showCS ? 1 : 0, s: STATE.labelSize };
          resetSceneMemory();
          return { mineA: mine.a, mineM: mine.m,
                   cleanA: clean.a, cleanM: clean.m, cleanCS: clean.cs, cleanS: clean.s,
                   backA: back.a, backM: back.m, backCS: back.cs, backS: back.s };`,
    checks: [['площадь посчитана', 'mineA', 1, 0], ['точка поставлена', 'mineM', 1, 0],
             ['в другой модели площадей нет', 'cleanA', 0, 0],
             ['и точек нет', 'cleanM', 0, 0],
             ['и галочка заливки на месте', 'cleanCS', 1, 0],
             ['и размер подписей свой', 'cleanS', 14, 0],
             ['вернулись — площадь на месте', 'backA', 1, 0],
             ['и точка на месте', 'backM', 1, 0],
             ['и снятая галочка', 'backCS', 0, 0],
             ['и свой размер подписей', 'backS', 18, 0]],
  },
  {
    /* П4. Кривая комплектов: строится только по кнопке, поля пустые, луч идёт
       ДО КРАЯ плоскости, и в сцене с КПВ и КТВ он пересекает обе кривые —
       обе точки показаны с координатами. Комплект 1 к 1 на КПВ y = 100 − x
       даёт (50; 50), на КТВ при мировой цене 2 — (66.67; 66.67). */
    name: 'Комплекты · луч до края и пересечение КПВ и КТВ',
    run: `openPicker(); pickScene('trade'); closePicker();
          STATE.bundleOn = false; redrawAll();
          var chk = document.querySelectorAll('[id^="chk-bundle"]').length;
          var off = STATE.bundleOn ? 1 : 0;
          /* Н17: кнопки «Построить» больше нет — галочка раскрывает поля, и луч
             строится сам, как только заполнены оба числа. */
          var chkT = document.getElementById('chk-bundle-t');
          chkT.checked = true; chkT.dispatchEvent(new Event('change', { bubbles: true }));
          var xt = document.getElementById('inp-bundle-xt');
          var yt = document.getElementById('inp-bundle-yt');
          xt.value = '1'; xt.dispatchEvent(new Event('input', { bubbles: true }));
          yt.value = '1'; yt.dispatchEvent(new Event('input', { bubbles: true }));
          var texts = [].map.call(document.querySelectorAll('#chart text'), function (t) { return t.textContent; });
          var ppf = texts.filter(function (s) { return s.indexOf('КПВ (') === 0; })[0] || '';
          var ktv = texts.filter(function (s) { return s.indexOf('КТВ (') === 0; })[0] || '';
          /* Дробная часть на экране отделяется ЗАПЯТОЙ (Б15), поэтому разбор
             числа с холста обязан её понимать: со старым классом [-\\d.] из
             «66,67» вычитывалось «67». */
          var nums = function (s) { var m = s.match(/([-\\d.,]+); ([-\\d.,]+)/);
            var n = function (t) { return parseFloat(String(t).replace(',', '.')); };
            return m ? [n(m[1]), n(m[2])] : [-1, -1]; };
          return { chk: chk, off: off, on: STATE.bundleOn ? 1 : 0,
                   px: nums(ppf)[0], py: nums(ppf)[1],
                   tx: nums(ktv)[0], ty: nums(ktv)[1],
                   ray: texts.filter(function (s) { return s.indexOf('Комплекты') === 0; }).length };`,
    // Н17 отменяет прежнее правило «галочки нет»: она есть в каждой из трёх
    // моделей блока и по умолчанию снята.
    checks: [['галочка луча в каждой модели блока', 'chk', 3, 0],
             ['без кнопки кривой нет', 'off', 0, 0],
             ['кнопка построила', 'on', 1, 0],
             ['пересечение с КПВ по X', 'px', 50, 0.2], ['и по Y', 'py', 50, 0.2],
             ['пересечение с КТВ по X', 'tx', 66.67, 0.3], ['и по Y', 'ty', 66.67, 0.3],
             ['луч подписан', 'ray', 1, 0]],
  },
  {
    /* П50. Размер подписей меняет ВСЁ внутри графика, кроме отметок координат
       на осях. Полсотни мест задают размер числом прямо в коде, поэтому
       множитель применяется одним проходом по холсту после отрисовки. */
    name: 'Подписи · три размера меняют весь график, кроме отметок осей',
    run: `openPicker(); pickScene('tax'); closePicker();
          function pick() {
            var t = [].slice.call(document.querySelectorAll('#chart text'));
            var curve = null, axis = null, other = null;
            t.forEach(function (n) {
              if (n.classList.contains('axis-num')) { if (axis === null) axis = +n.getAttribute('font-size'); return; }
              /* Текст подписи читаем целиком, а не первым узлом: с А28 величина
                 разложена на tspan'ы, и firstChild у неё элемент, а не текст.
                 Ожидаемые размеры прежние — меняется только способ найти
                 подпись. Подсказку в <title> отбрасываем. */
              var s = labelPlainText(n).trim();
              if (s === 'S' && curve === null) curve = +n.getAttribute('font-size');
              else if (other === null) other = +n.getAttribute('font-size');
            });
            return { curve: curve, axis: axis, other: other };
          }
          document.getElementById('lbl-s').click(); var s = pick();
          document.getElementById('lbl-m').click(); var m = pick();
          document.getElementById('lbl-l').click(); var l = pick();
          var ratio = (s.other > 0) ? (l.other / s.other) : 0;
          document.getElementById('lbl-s').click();
          return { s: s.curve, m: m.curve, l: l.curve,
                   ax: s.axis, axM: m.axis, axL: l.axis, ratio: ratio };`,
    // Н31: три буквы дают 10 · 14 · 18 (прежние 12 · 16 · 20 заменены).
    checks: [['маленькая — 10', 's', 10, 0], ['средняя — 14', 'm', 14, 0],
             ['крупная — 18', 'l', 18, 0],
             ['отметки осей не трогаем', 'ax', 10, 0],
             ['и на средней', 'axM', 10, 0], ['и на крупной', 'axL', 10, 0],
             ['прочие подписи растут в той же мере', 'ratio', 18 / 10, 0.01]],
  },
  {
    /* Н20, Н21. Возврат масштаба вписывает ВСЁ построенное. Порядок такой:
       сначала перехваты кривых с осями, потом проверка, влезли ли точки и
       площади, и только если нет — отдаляемся. Перехваты, а не размах кривой:
       растущая S = Q не кончается никогда, и по протяжённости окно раздувалось
       бы бесконечно. Привычный масштаб сцены остаётся, пока кривые в него
       помещаются. */
    name: 'Масштаб · окно вмещает перехваты кривых (Н20, Н21)',
    run: `resetSceneMemory();
          openPicker(); pickScene('sd'); closePicker();
          STATE.marks = []; STATE.areaCalcList = [];
          resetZoom();
          var std = [CONFIG.Qmax, CONFIG.Pmax];        // стандартная сцена не раздувается
          var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
          updateCurveExpr(d, '300 - 2*Q'); redrawAll(); resetZoom();
          var wide = [CONFIG.Qmax, CONFIG.Pmax];       // перехваты 150 и 300
          addMarkAt(400, 50, null); resetZoom();
          var withMark = CONFIG.Qmax;                  // точка за краем тоже влезла
          resetZoom(); var again = CONFIG.Qmax;        // повтор ничего не двигает
          resetSceneMemory();
          return { stdQ: std[0], stdP: std[1], wideQ: wide[0], wideP: wide[1],
                   mark: withMark, same: (withMark === again) ? 1 : 0 };`,
    checks: [['привычная сцена не раздувается по Q', 'stdQ', 100, 0],
             ['и по P', 'stdP', 100, 0],
             ['перехват X = 150 уместился', 'wideQ', 200, 60],
             ['перехват Y = 300 уместился', 'wideP', 400, 120],
             ['точка (400; 50) уместилась', 'mark', 500, 120],
             ['повтор ничего не двигает', 'same', 1, 0]],
  },
  {
    /* Н17, Н18, Н19. Кривая комплектов: галочка снята по умолчанию, поля пустые,
       луч строится САМ по двум числам и перестраивается при правке; на
       отрицательное значение ошибка и луча нет; луч крутится вокруг начала
       координат и падает в излом КПВ.
       КПВ с изломом: X < 20 ? 100 − X : 120 − 2X. Стык в (20; 80), значит наклон
       луча через него 80/20 = 4. */
    name: 'Комплекты · галочка, автопостроение, вращение и магнит излома (Н17–Н19)',
    run: `resetSceneMemory();
          openPicker(); pickScene('ppf'); closePicker(); setToolsOpen(true);
          var f = document.getElementById('inp-ppf');
          f.value = 'X < 20 ? 100 - X : 120 - 2*X';
          ['input','change'].forEach(function (t) { f.dispatchEvent(new Event(t, {bubbles:true})); });
          f.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
          var chk = document.getElementById('chk-bundle-1');
          var row = document.getElementById('bundle-row');
          var offAtStart = (!chk.checked && getComputedStyle(row).display === 'none') ? 1 : 0;
          chk.checked = true; chk.dispatchEvent(new Event('change', {bubbles:true}));
          var ex = document.getElementById('inp-bundle-x'), ey = document.getElementById('inp-bundle-y');
          var emptyFields = (ex.value === '' && ey.value === '') ? 1 : 0;
          var noRayYet = STATE.bundleOn ? 0 : 1;
          ex.value = '2'; ex.dispatchEvent(new Event('input', {bubbles:true}));
          var halfNoRay = STATE.bundleOn ? 0 : 1;
          ey.value = '1'; ey.dispatchEvent(new Event('input', {bubbles:true}));
          var auto = STATE.bundleOn ? 1 : 0;
          var kinks = (STATE._bundleKinks || []).length;
          var kslope = kinks ? STATE._bundleKinks[0] : -1;
          bundleDragTo(30, 45); var free = STATE.bundleY / STATE.bundleX;
          bundleDragTo(20, 78); var snapped = STATE.bundleY / STATE.bundleX;
          bundleDragTo(20, 30); var away = STATE.bundleY / STATE.bundleX;
          var neg = (bundleSlopeAt(-5, 20) === null) ? 1 : 0;
          ey.value = '-3'; ey.dispatchEvent(new Event('input', {bubbles:true}));
          var err = document.getElementById('bundle-error');
          var badShown = (err && err.style.display !== 'none' && err.textContent.length > 5) ? 1 : 0;
          var badNoRay = STATE.bundleOn ? 0 : 1;
          resetSceneMemory();
          return { offAtStart: offAtStart, emptyFields: emptyFields, noRayYet: noRayYet,
                   halfNoRay: halfNoRay, auto: auto, kinks: kinks, kslope: kslope,
                   free: free, snapped: snapped, away: away, neg: neg,
                   badShown: badShown, badNoRay: badNoRay };`,
    checks: [['галочка снята, поля скрыты', 'offAtStart', 1, 0],
             ['поля пустые', 'emptyFields', 1, 0], ['и луча ещё нет', 'noRayYet', 1, 0],
             ['одно число — луча нет', 'halfNoRay', 1, 0],
             ['два числа — луч сам', 'auto', 1, 0],
             ['излом найден', 'kinks', 1, 0], ['его наклон 4', 'kslope', 4, 0.02],
             ['поворот мимо излома', 'free', 1.5, 0.01],
             ['рядом с изломом падает в него', 'snapped', 4, 0.02],
             ['вдали не липнет', 'away', 1.5, 0.01],
             ['в минус не крутится', 'neg', 1, 0],
             ['на отрицательное — ошибка', 'badShown', 1, 0],
             ['и луч убран', 'badNoRay', 1, 0]],
  },
  {
    /* Н16. Выигрыш от торговли это разница ПОТРЕБЛЕНИЯ, а его задаёт кривая
       комплектов. Сравниваем две точки на одном луче: где он встречает КПВ
       (автаркия) и где встречает КТВ (торговля). Раньше здесь стояла разность
       перехватов линий с осями, то есть сравнивались крайние точки, в которых
       страна потребляет ровно один товар, и кривая комплектов в расчёте не
       участвовала: при КПВ Y = 100 − X, цене 2 и комплекте 1:1 выходило
       «+0 по X и +100 по Y», хотя верный ответ +16.67 по обоим. */
    name: 'Торговля · прирост считается по кривой комплектов (Н16)',
    run: `resetSceneMemory();
          openPicker(); pickScene('trade'); closePicker();
          var f = document.getElementById('inp-ppft');
          f.value = '100 - X';
          ['input','change'].forEach(function (t) { f.dispatchEvent(new Event(t, {bubbles:true})); });
          f.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
          var p = document.getElementById('ppft-price');
          if (p) { p.value = 2; p.dispatchEvent(new Event('input', {bubbles:true})); }
          STATE.bundleOn = true; STATE.bundleX = 1; STATE.bundleY = 1;
          redrawAll();
          var g = tradeBundleGain(STATE.ppfTradeData) || {};
          STATE.bundleOn = false; redrawAll();
          var noBundle = document.getElementById('sb-body').textContent;
          resetSceneMemory();
          return { ax: g.aut && g.aut.x, ay: g.aut && g.aut.y,
                   tx: g.tr && g.tr.x, ty: g.tr && g.tr.y,
                   dx: g.dx, dy: g.dy,
                   hint: /Постройте кривую комплектов/.test(noBundle) ? 1 : 0,
                   quiet: /Прирост против автаркии по X/.test(noBundle) ? 1 : 0 };`,
    checks: [['автаркия X', 'ax', 50, 0.01], ['автаркия Y', 'ay', 50, 0.01],
             ['торговля X', 'tx', 66.667, 0.01], ['торговля Y', 'ty', 66.667, 0.01],
             ['прирост по X', 'dx', 16.667, 0.01], ['прирост по Y', 'dy', 16.667, 0.01],
             ['без луча — подсказка', 'hint', 1, 0],
             ['и без чисел', 'quiet', 0, 0]],
  },
  {
    /* Н59, Свх-5. Области сцены переехали строками в таблицу площадей, и число у
       них считается по САМОЙ нарисованной фигуре: путь разбирается на точки,
       точки переводятся обратно через шкалы, дальше формула площади
       многоугольника. Способ общий, поэтому реестра на каждый сюжет не нужно.
       Сверяем с контрольными числами налога: Tx = 800, DWL = 100. */
    name: 'Площади · области сцены считаются по нарисованному (Н59)',
    run: `resetSceneMemory();
          openPicker(); pickScene('tax'); closePicker(); redrawAll();
          var by = {};
          currentAreas().forEach(function (e) { by[areaShort(e.key)] = e.value; });
          resetSceneMemory();
          return { cs: by['CS'], ps: by['PS'], tx: by['Tx'], dwl: by['DWL'] };`,
    checks: [['CS', 'cs', 800, 6], ['PS', 'ps', 800, 6],
             ['сбор бюджета', 'tx', 800, 6], ['потери общества', 'dwl', 100, 3]],
  },
  {
    /* Н40, Н41, Н66. Начало координат — ключевая точка наравне с пересечениями,
       но своё имя оно берёт, только если в нуле больше ничего нет. Магнит
       ключевой точки один на все случаи: постановка своей точки, вершина
       площади, перетаскивание. В «Оптимуме при ограничении» точка катается по
       самому ограничению, а не по спрятанному чужому полю. */
    name: 'Ключевые точки · начало координат, магнит и ограничение (Н40, Н41, Н66)',
    run: `resetSceneMemory();
          openPicker(); pickScene('sd'); closePicker();
          var zero = keyTargets().filter(function (p) {
            return Math.abs(p.x) < 1e-9 && Math.abs(p.y) < 1e-9; }).length;
          // Магнит: щёлкаем в 12 пикселях от равновесия — обязаны попасть В него.
          var sc = mainScales();
          var eq = STATE.eq;
          var hit = snapVertexAt(sc.mx(eq.Q) + 12, sc.my(eq.P) - 8);
          var gotKey = (hit && hit.key) ? 1 : 0;
          var dq = hit ? Math.abs(hit.x - eq.Q) : 99;
          openPicker(); pickScene('m-constraint'); closePicker(); redrawAll();
          var names = snapTargets().map(function (t) { return t.name; }).join(',');
          resetSceneMemory();
          return { zero: zero, gotKey: gotKey, dq: dq,
                   con: names === 'ограничение' ? 1 : 0 };`,
    checks: [['ноль ровно один', 'zero', 1, 0],
             ['щелчок рядом попал в ключевую точку', 'gotKey', 1, 0],
             ['и встал ровно в неё', 'dq', 0, 0.001],
             ['в ограничении катаемся по ограничению', 'con', 1, 0]],
  },
  {
    /* Н7. Буква-параметр обязана менять саму функцию. Прямая раскладывается на
       коэффициенты один раз, и дальше evalCurve идёт быстрым путём; если в
       формуле есть буква, коэффициенты запоминались при её тогдашнем значении,
       и ползунок двигал только число в состоянии. Ломались ровно те формулы,
       которые ВЫГЛЯДЯТ прямыми: «100 − a·Q²» работала и раньше.
       Проверяем и кусочную запись: у неё буква живёт внутри ветви. */
    name: 'Параметры · буква меняет значение функции (Н7)',
    run: `resetSceneMemory();
          openPicker(); pickScene('sd'); closePicker();
          addCurve('100 - a*Q'); redrawAll();
          var c = STATE.curves[STATE.curves.length - 1];
          function at(v) { STATE.params.a.value = v; redrawAll(); return evalCurve(c, 10); }
          var one = at(1), five = at(5), half = at(0.5);
          var linA = c.linear ? c.linear.a : NaN;      // быстрый путь жив и едет за буквой
          addCurve('Q < 50 ? 100 - a*Q : 50'); redrawAll();
          var pw = STATE.curves[STATE.curves.length - 1];
          STATE.params.a.value = 1; redrawAll(); var pw1 = evalCurve(pw, 10);
          STATE.params.a.value = 2; redrawAll(); var pw2 = evalCurve(pw, 10);
          var pwTail = evalCurve(pw, 60);              // вторая ветвь буквы не знает
          var eqLetters = freeSymbols('x^2 + y^2 = k*25').join(',');
          resetSceneMemory();
          return { one: one, five: five, half: half, linA: linA,
                   pw1: pw1, pw2: pw2, pwTail: pwTail, eq: eqLetters === 'k' ? 1 : 0 };`,
    checks: [['a=1 → f(10)', 'one', 90, 0.001], ['a=5 → f(10)', 'five', 50, 0.001],
             ['a=0.5 → f(10)', 'half', 95, 0.001],
             ['быстрый путь пересобран', 'linA', -0.5, 0.001],
             ['кусочная при a=1', 'pw1', 90, 0.001], ['кусочная при a=2', 'pw2', 80, 0.001],
             ['вторая ветвь не тронута', 'pwTail', 50, 0.001],
             ['буквы находятся и в записи уравнением', 'eq', 1, 0]],
  },
  {
    /* П32, П33. Возврат масштаба показывает всё нарисованное и делает это
       ИДЕМПОТЕНТНО: повторное нажатие ничего не двигает. Кривые в подгонке
       намеренно не участвуют — растущая кривая раздвигала бы окно бесконечно.
       П53: шаг зума работает и туда, и обратно. */
    name: 'Масштаб · возврат показывает всё и не расползается',
    run: `openPicker(); pickScene('sd'); closePicker();
          STATE.marks = []; STATE.areaVerts = []; STATE.areaCalcList = [];
          resetZoom();
          var base = [CONFIG.Qmax, CONFIG.Pmax];
          resetZoom();
          var again = [CONFIG.Qmax, CONFIG.Pmax];
          addMarkAt(240, 180, null); resetZoom();
          var wide = [CONFIG.Qmax, CONFIG.Pmax];
          resetZoom();
          var wideAgain = [CONFIG.Qmax, CONFIG.Pmax];
          var before = CONFIG.Qmax;
          zoomStep(1 / 1.25);
          var zin = CONFIG.Qmax;
          zoomStep(1.25);
          var zout = CONFIG.Qmax;
          STATE.marks = []; resetZoom();
          return { bq: base[0], bp: base[1], aq: again[0], ap: again[1],
                   wq: wide[0], wp: wide[1], w2q: wideAgain[0], w2p: wideAgain[1],
                   grew: (zin < before) ? 1 : 0, back: (Math.abs(zout - before) < 1e-6) ? 1 : 0,
                   pad: padMax(200), padZero: padMax(0) };`,
    checks: [['базовое окно по Q', 'bq', 100, 0], ['по P', 'bp', 100, 0],
             ['повтор ничего не двигает', 'aq', 100, 0], ['и по P', 'ap', 100, 0],
             ['точка (240;180) уместилась', 'wq', 300, 0], ['и по высоте', 'wp', 250, 0],
             ['повтор с точкой тоже', 'w2q', 300, 0], ['и по высоте', 'w2p', 250, 0],
             ['«+» приближает', 'grew', 1, 0], ['«−» возвращает', 'back', 1, 0],
             ['общий запас у конца оси', 'pad', 250, 0],
             ['пустой вход — как у niceMax', 'padZero', 10, 0]],
  },
  {
    /* П31. Точка липнет и к кривым, и к ОСЯМ, а оторвать её труднее, чем
       прилепить: радиус отрыва заметно больше радиуса захвата. */
    name: 'Точки · прилипание к осям и сопротивление при отрыве',
    run: `openPicker(); pickScene('sd'); closePicker();
          var s = mainScales();
          var onX = axisSnapAt(s.mx(40), s.my(0) + 5);
          var onY = axisSnapAt(s.mx(0) - 4, s.my(60));
          var zero = axisSnapAt(s.mx(0) + 3, s.my(0) - 3);
          var far = axisSnapAt(s.mx(40), s.my(40));
          return { xName: onX && onX.name === 'ось X' ? 1 : 0,
                   xy: onX ? onX.y : -1,
                   yName: onY && onY.name === 'ось Y' ? 1 : 0,
                   yx: onY ? onY.x : -1,
                   zero: zero && zero.name === 'начало координат' ? 1 : 0,
                   far: far ? 1 : 0,
                   ratio: RELEASE_PX / SNAP_PX };`,
    checks: [['у оси X прилипает', 'xName', 1, 0], ['и садится на y = 0', 'xy', 0, 0],
             ['у оси Y прилипает', 'yName', 1, 0], ['и садится на x = 0', 'yx', 0, 0],
             ['у нуля — в начало координат', 'zero', 1, 0],
             ['вдали от осей не липнет', 'far', 0, 0],
             ['оторвать труднее, чем прилипнуть', 'ratio', 2.5, 0.01]],
  },
  {
    /* П38. Закрепка кладёт ключевую точку в список своих точек последней и
       раскрывает блок «Точки на графике», если он был закрыт.

       ⚠️ ПРОВЕРКА ПЕРЕСЧИТАНА 19.08. Прежде она требовала, чтобы после выноса
       снималось «выделение» (`STATE.hotCross`). Такого состояния больше нет:
       щелчок по точке её не закреплял никогда особенно надолго, а с решением
       владельца точка вообще ничего не помнит — наведение показывает, значок
       выносит, увёл курсор и не осталось ничего. Вместо снятого требования
       проверяется то, что теперь и есть смысл фазы: вынос НЕ гасит взведённую
       кривую (иначе точка уезжала бы в список вместе с погасшим холстом). */
    name: 'Ключевые точки · закрепка кладёт точку в список',
    run: `openPicker(); pickScene('sd'); closePicker();
          STATE.marks = []; redrawAll();
          var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
          armCurve(curveShortName(d));
          var before = STATE.marks.length;
          var p = keyTargets().filter(function (t) { return /D и S/.test(t.name); })[0];
          pinKeyPoint(p);
          var m = STATE.marks[STATE.marks.length - 1];
          var open = document.getElementById('sec-view').classList.contains('open-card') ? 1 : 0;
          return { added: STATE.marks.length - before, x: m.x, y: m.y, open: open,
                   armed: STATE.armedCurve === curveShortName(d) ? 1 : 0 };`,
    checks: [['точка добавлена', 'added', 1, 0], ['координата Q', 'x', 50, 0.1],
             ['координата P', 'y', 50, 0.1], ['блок раскрылся', 'open', 1, 0],
             ['вынос не гасит взведённую кривую', 'armed', 1, 0]],
  },
  {
    /* П26. «Деформации графика» ведёт общий механизм параметров: своего
       ползунка у сюжета больше нет, буква a приходит из sceneExtraParams. */
    name: 'Деформации · параметр a идёт из общего механизма',
    run: `openPicker(); pickScene('m-transform'); closePicker();
          STATE.params = {}; redrawAll();
          var has = STATE.params.a ? 1 : 0;
          var own = document.getElementById('math-a-field') ? 1 : 0;
          STATE.params.a.value = 4; redrawAll();
          return { has: has, own: own, a: STATE.mathRes.a };`,
    checks: [['буква a заведена', 'has', 1, 0],
             ['своего поля у сцены нет', 'own', 0, 0],
             ['ползунок доехал до расчёта', 'a', 4, 0.001]],
  },
  {
    // Фаза 6: правая граница берётся точно, а не по узлу сетки. Раньше край
    // выходил 9.97 вместо 10, и площадь получалась меньше настоящей.
    name: 'Площадь · под 10 − x в первой четверти ровно 50',
    run: `loadScene('sd'); STATE.curves = []; STATE.params = {};
          addCurve('10 - x'); redrawAll();
          var t = snapTargets()[0];
          syncAreaCalcUI();
          document.getElementById('ac-pick').value = t.name;
          STATE.areaCalcList = []; runAreaCalc();
          var r = STATE.areaCalcList[0] || {};
          return { edge: curveRightEdge(t.f), area: r.value, a: r.a, b: r.b };`,
    checks: [['правый край', 'edge', 10, 0.001], ['площадь', 'area', 50, 0.01],
             ['от', 'a', 0, 0.001], ['до', 'b', 10, 0.001]],
  },
  {
    // Фаза 11: одна строка ввода принимает все три формы записи КПВ.
    name: 'КПВ · ввод «x = 50 − 0.5y» даёт ту же кривую, что «y = 100 − 2x»',
    run: `pickScene('ppf');
          var a = parsePpfEquation('y = 100 - 2*x');
          var b = parsePpfEquation('x = 50 - 0.5*y');
          var c = parsePpfEquation('x^2 + y^2 = 10000');
          return { a20: a.f(20), b20: b.f(20), a40: a.f(40), b40: b.f(40),
                   c60: c.f(60), c0: c.f(0) };`,
    checks: [['явная в 20', 'a20', 60, 0.01], ['обратная в 20', 'b20', 60, 0.05],
             ['явная в 40', 'a40', 20, 0.01], ['обратная в 40', 'b40', 20, 0.05],
             ['дуга в 60', 'c60', 80, 0.1], ['дуга в 0', 'c0', 100, 0.1]],
  },
  {
    // Фаза 12.5: альтернативные издержки численно, в обе стороны, и для
    // нелинейной КПВ они РАЗНЫЕ в разных точках.
    name: 'КПВ · альт. издержки в обе стороны и рост у вогнутой',
    run: `pickScene('ppf');
          STATE.ppfFormula = 'y = 100 - 2*x'; redrawAll();
          var lin = ppfOppAt(evalPpf, 20);
          STATE.ppfFormula = 'y = 100 - 0.01*x^2'; redrawAll();
          var lo = ppfOppAt(evalPpf, 20), hi = ppfOppAt(evalPpf, 80);
          return { oppX: lin.oppX, oppY: lin.oppY, at20: lo.oppX, at80: hi.oppX };`,
    checks: [['издержки X у прямой', 'oppX', 2, 0.01], ['издержки Y у прямой', 'oppY', 0.5, 0.01],
             ['вогнутая при X=20', 'at20', 0.4, 0.01], ['вогнутая при X=80', 'at80', 1.6, 0.01]],
  },
  {
    // Фаза 11.4: луч комплектов 3 X на 1 Y упирается в КПВ 100 − x в (75; 25).
    name: 'КПВ · комплект 3 к 1 на границе 100 − x даёт (75; 25) и 25 комплектов',
    run: `pickScene('ppf');
          STATE.ppfFormula = 'y = 100 - x'; STATE.bundleOn = true;
          STATE.bundleX = 3; STATE.bundleY = 1; redrawAll();
          var b = bundleRay(evalPpf);
          return { x: b.x, y: b.y, whole: b.whole };`,
    checks: [['X в наборе', 'x', 75, 0.05], ['Y в наборе', 'y', 25, 0.05],
             ['целых комплектов', 'whole', 25, 0]],
  },
  {
    // Фаза 13.1: складываем ТРИ кривые. Свёртка попарно — сумма Минковского
    // ассоциативна, поэтому концы просто складываются, а изломы стоят там, где
    // очередной участник исчерпал X.
    name: 'КПВ · сумма трёх линейных 100−x, 60−3x, 40−0.5x',
    run: `setMode('ppf'); setPpfSub('sum');
          STATE.ppfSumCount = 3;
          STATE.ppf1 = 'y = 100 - x'; STATE.ppf2 = 'y = 60 - 3*x';
          STATE.ppfSumMore = ['y = 40 - 0.5*x'];
          STATE.ppfSumData = null; redrawAll();
          var d = STATE.ppfSumData;
          return { ok: d && d.ok ? 1 : 0, Xtot: d.Xtot, Ytot: d.Ytot,
                   n: d.n, kinks: (d.kinks || []).length,
                   first: d.order[0].opp, last: d.order[2].opp };`,
    // Xtot = 100 + 20 + 80 = 200; Ytot = 100 + 60 + 40 = 200.
    // Издержки X: 0.5 (третья), 1 (первая), 3 (вторая) — специализируется первой третья.
    checks: [['построилась', 'ok', 1, 0], ['X всего', 'Xtot', 200, 0.5],
             ['Y всего', 'Ytot', 200, 0.5], ['кривых', 'n', 3, 0],
             ['самые дешёвые издержки', 'first', 0.5, 0.01],
             ['самые дорогие издержки', 'last', 3, 0.01]],
  },
  {
    /* Фаза 15.6: предел торговли и излом КТВ.
       КПВ 1: y = 100 − x  (альт. цена X = 1, страна дешёвая по X, экспортирует X)
       КПВ 2: y = 120 − 4x (альт. цена X = 4, экспортирует Y, Ymax = 120)
       Возьмём Pw = 2. Страна 1 специализируется: производство (100; 0).
       Партнёр может отдать не больше 120 единиц Y, значит продать X можно
       не больше 120 / 2 = 60 при своих 100 — предел СРАБАТЫВАЕТ.
       Излом стоит в (100 − 60; 2·60) = (40; 120). */
    name: 'Торговля двух стран · предел обмена ломает КТВ в (40; 120)',
    run: `setMode('ppf'); setPpfSub('trade'); setTradeScenario('B');
          STATE.tbF1 = 'y = 100 - x'; STATE.tbF2 = 'y = 120 - 4*x';
          STATE.tbManualPrice = 2; STATE.tradeBData = null; redrawAll();
          var d = STATE.tradeBData;
          var lo = d.lowCo;
          return { ok: d.ok ? 1 : 0, Pw: d.Pw, lowIdx: d.lowIdx,
                   exportX: d.E_L, binding: lo.limit.binding ? 1 : 0,
                   kx: lo.limit.kink[0], ky: lo.limit.kink[1] };`,
    checks: [['посчиталось', 'ok', 1, 0], ['мировая цена', 'Pw', 2, 0.001],
             ['экспортёр X это страна 1', 'lowIdx', 1, 0],
             ['предел обмена X', 'exportX', 60, 0.05],
             ['предел сработал', 'binding', 1, 0],
             ['излом по X', 'kx', 40, 0.05], ['излом по Y', 'ky', 120, 0.05]],
  },
  {
    // Тот же случай, но партнёра хватает: Pw = 1.2, предел 120/1.2 = 100 = весь
    // свой X, значит излома нет и линия идёт прямой до оси.
    name: 'Торговля двух стран · партнёра хватило, излома нет',
    run: `setMode('ppf'); setPpfSub('trade'); setTradeScenario('B');
          STATE.tbF1 = 'y = 100 - x'; STATE.tbF2 = 'y = 120 - 4*x';
          STATE.tbManualPrice = 1.2; STATE.tradeBData = null; redrawAll();
          var lo = STATE.tradeBData.lowCo;
          return { exportX: STATE.tradeBData.E_L, binding: lo.limit.binding ? 1 : 0 };`,
    checks: [['обменять можно весь X', 'exportX', 100, 0.05],
             ['предел не сработал', 'binding', 0, 0]],
  },
  {
    /* А45. РАНЬШЕ здесь проверялось, что форма картинки на бумаге повторяет
       форму холста на экране. Это требование ОТМЕНЕНО, и вот почему.

       Форма холста зависит от ширины окна браузера, поэтому вместе с ней от
       ширины окна зависели и размер картинки, и кегли подписей: при узком
       окне пропорция упиралась в верхний предел и выходило 16 × 22,4 см,
       то есть 87 процентов высоты страницы, с делениями осей по 25,9 пункта
       и легендой по 41,4. Один и тот же график из разных окон давал разные
       файлы.

       Теперь размер картинки — одна договорённость на весь калькулятор
       (12 × 8 см). Так делают в вёрстке научных работ: единый размер, чтобы
       рисунки выстраивались в ряд, а кегли были предсказуемы. Диапазоны осей
       по-прежнему приходят из шкал сцены, поэтому на бумагу попадает то же
       окно, что на экране; меняется только форма поля.

       Проверяем новое требование: размер постоянный и заявленный. */
    name: 'Экспорт · размер картинки постоянный и не зависит от окна',
    run: `pickScene('tax');
          var tex = buildTex('Проверка', 'fig:t');
          var ax = /xmin=([-\\d.]+), xmax=([-\\d.]+), ymin=([-\\d.]+), ymax=([-\\d.]+)/.exec(tex);
          var sz = /width=([\\d.]+)cm, height=([\\d.]+)cm/.exec(tex);
          var s = mainScales();
          var xd = s.mx.domain(), yd = s.my.domain();
          return { w: +sz[1], h: +sz[2],
                   // окно на бумаге — то же, что на экране
                   xmin: +ax[1], xmax: +ax[2], ymin: +ax[3], ymax: +ax[4],
                   wantXmin: xd[0], wantXmax: xd[1], wantYmin: yd[0], wantYmax: yd[1],
                   only: tex.indexOf('scale only axis') >= 0 ? 1 : 0 };`,
    checks: [['ширина, см', 'w', 12, 0], ['высота, см', 'h', 8, 0],
             ['левая граница', 'xmin', 'WANTXMIN', 0.02],
             ['правая граница', 'xmax', 'WANTXMAX', 0.02],
             ['нижняя граница', 'ymin', 'WANTYMIN', 0.02],
             ['верхняя граница', 'ymax', 'WANTYMAX', 0.02],
             ['поле графика, а не картинка', 'only', 1, 0]],
  },
  {
    /* А58. Печатная версия. Правил печати не было ни одного: Ctrl+P выводил
       страницу как есть, вместе с рейкой значков, обеими панелями и тёмным
       фоном. Учителю нужен график в раздатку, поэтому на листе остаётся только
       он, название модели сверху и ключевые значения снизу.

       Само правило @media print из скрипта не проверить, поэтому проверяем то,
       что готовит к печати код: шапка и подвал наполняются. */
    name: 'Печать · название модели и значения готовятся к листу',
    run: `pickScene('tax'); redrawAll();
          fillPrintBlocks();
          var t = document.getElementById('print-title');
          var s = document.getElementById('print-stats');
          return { hasTitle: (t && t.textContent.trim().length > 3) ? 1 : 0,
                   rows: s ? s.querySelectorAll('.stat').length : 0,
                   hidden: getComputedStyle(t).display === 'none' ? 1 : 0 };`,
    checks: [['название есть', 'hasTitle', 1, 0],
             ['строк значений', 'rows', 8, 6],
             ['на экране не показывается', 'hidden', 1, 0]],
  },
  {
    /* А30 · А61 · А63. Точки на графике.

       А30: черновик открывался с «x = 0, y = 0», потому что незаполненная
       координата уходила в общий формат чисел, а тот на пустой строке считал
       ноль. Человек нажимал галочку не глядя и получал точку в начале
       координат. Теперь пусто показывается пустым.

       А61: при правке значение ВЫДЕЛЯЕТСЯ целиком, и первый набранный символ
       его заменяет. Раньше курсор ставился в конец, и набор «45» поверх нуля
       давал «045». Это отмена прежнего решения, принятая по замеру владельца.

       А63: у всех точек был один цвет (COL.ink), и на графике с тремя точками
       их было не различить. Новая точка берёт следующий свободный цвет из той
       же палитры, что предлагает пикер. */
    name: 'Точки · пустой черновик, свой цвет, замена значения при правке',
    run: `pickScene('sd');
          STATE.marks = []; markCounter = 0; renderMarkList();
          startMarkDraft();
          var row = document.querySelector('.mark-draft');
          var vals = [].map.call(row.querySelectorAll('.edval'), function (e) { return e.textContent; });
          var zeros = vals.filter(function (s) { return /=\\s*0\\b/.test(s); }).length;

          STATE.marks = []; markCounter = 0;
          for (var i = 1; i <= 5; i++) addMarkAt(i * 10, i * 10, null);
          redrawAll();
          var cols = STATE.marks.map(function (m) { return String(m.color || ''); });
          var uniq = {};
          cols.forEach(function (c) { uniq[c] = 1; });

          STATE.marks = []; markCounter = 0; addMarkAt(50, 50, null); renderMarkList();
          pickScene('sd');
          return { zeros: zeros, drafts: vals.length,
                   colors: Object.keys(uniq).length, empty: cols.filter(Boolean).length };`,
    checks: [['нулей в черновике', 'zeros', 0, 0],
             ['полей в черновике', 'drafts', 2, 1],
             ['разных цветов у пяти точек', 'colors', 5, 0],
             ['точек с заданным цветом', 'empty', 5, 0]],
  },
  {
    /* А28 · А29. Величины на холсте набраны с индексами.

       Было: в правой панели «$P_b$» набиралось формулой, а на холсте та же
       величина стояла обычным текстом «Pb=60». Даже внутри холста согласия не
       было: «Q₁» пользовалось юникодной цифрой, а «Pb» и «Ps» — обычными
       буквами. Таких «текстовых формул» по всем сценам было больше восьмидесяти.

       Решает общий разбор (qtyParts) — тот же, что у панели и у файла; на
       холсте он печатается средствами SVG, поэтому подписи остаются в снимке
       холста и попадают в выгрузку в PNG. */
    name: 'Подписи · величины на холсте с индексами, а не слипшимся текстом',
    run: `var scenes = Object.keys(SCENE_ROUTE);
          var glued = 0, withSub = 0;
          scenes.forEach(function (k) {
            pickScene(k);
            document.querySelectorAll('#chart text').forEach(function (t) {
              if (t.classList.contains('axis-num')) return;
              if (t.getBoundingClientRect().width < 0.5) return;
              var own = [].filter.call(t.childNodes, function (n) { return n.nodeType === 3; })
                          .map(function (n) { return n.nodeValue; }).join('');
              if (/[A-Za-z][0-9\\u2080-\\u2089]|[0-9\\u2080-\\u2089][A-Za-z]/.test(own)) glued++;
              if (t.querySelector('tspan[dy]')) withSub++;
            });
          });
          pickScene('tax');
          var tex = buildTex('', '');
          return { glued: glued, withSub: withSub,
                   texPb: tex.indexOf('$60_b$') >= 0 ? 1 : 0,
                   texNodes: (tex.match(/\\\\node\\[/g) || []).length };`,
    /* ⚠️ ОЖИДАНИЕ ПЕРЕСЧИТАНО 19.08. Значения координат уехали за оси и потеряли
       имя оси: вместо «P_b = 60» на оси стоит «60» с индексом «b». Требование
       осталось тем же по сути — индекс обязан доехать до бумаги, — но искать
       его надо в новой записи. Заодно эта строка держит находку фазы: индекс
       при ЧИСЛЕ разбор для бумаги раньше не понимал вовсе и терял молча. */
    /* ⚠️ ЧИСЛО ПЕРЕСЧИТАНО 25.08, И ВОТ ПОЧЕМУ. Сцена сложения стала
       подписывать свои кривые обозначениями — D₁, D₂, D₃, S₁, S₂ и D, S
       вместо «спрос первой группы» и родни (шесть подписей по 137–181 px
       читались вдоль края одной строкой). Каждое обозначение с индексом
       добавляет по подписи с tspan[dy], и потолок 58 оказался мал: замер даёт
       61. Смысл проверки не изменился — индексы обязаны быть НАБРАНЫ, а не
       слиты в текст, за это отвечает `glued`. Середина сдвинута на измеренное
       значение, допуск прежний, нижний край от этого стал строже. */
    checks: [['слипшихся величин', 'glued', 0, 0],
             ['подписей с индексом', 'withSub', 61, 28],
             ['в файле цена покупателя с индексом', 'texPb', 1, 0],
             ['подписи из файла не пропали', 'texNodes', 11, 4]],
  },
  {
    /* А60. Подписи не налезают друг на друга.

       Было замерено попарно: в сцене налога $Q_1 = 40$ налезала на деления оси
       30, 40 и 50 и читалась как «3Q₁=400 60», подпись $S$ налезала на $S + t$.
       По десяти сценам пятнадцать наложений.

       Разводит их один проход после отрисовки (spreadLabels): кто нарисован
       раньше, тот и остаётся на месте, поэтому деления осей не двигаются.
       Полного нуля не обещаем: у подписи, зажатой между кривой сверху и
       делением снизу, свободного места может не быть вовсе, а увести её от
       своего объекта хуже, чем оставить наложение. */
    name: 'Подписи · не налезают друг на друга',
    run: `var scenes = ['tax', 'sd', 'mono', 'ceil', 'elast', 'costs', 'labor', 'adas', 'ppf', 'smallopen'];
          var total = 0, labels = 0;
          scenes.forEach(function (k) {
            pickScene(k); redrawAll();
            var items = [];
            document.querySelectorAll('#chart text').forEach(function (t) {
              var r = t.getBoundingClientRect();
              if (r.width < 0.5 || r.height < 0.5) return;
              items.push(r);
            });
            labels += items.length;
            for (var i = 0; i < items.length; i++) {
              for (var j = i + 1; j < items.length; j++) {
                var a = items[i], b = items[j];
                var ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
                var oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
                if (ox > 2 && oy > 2) total++;
              }
            }
          });
          pickScene('sd');
          return { total: total, labels: labels };`,
    checks: [['наложений на десяти сценах', 'total', 0, 3],
             ['подписей всего', 'labels', 240, 80]],
  },
  {
    /* А3 · А54. Название модели переносится на две строки и не обрезается.

       Было: место под заголовок 163 px при узком окне и 199 при широком, а
       самое длинное название требовало 321 px в одну строку — многоточием
       обрезались 23 названия из 41. Решение штаба от 13.08: переносить, не
       сокращая названий и не уменьшая кегль. (Имя конкретной модели здесь не
       цитируется: оно меняется, а проверка про длину, а не про него.)

       Высота шапки постоянна: иначе содержимое ниже прыгало бы при переходе
       между сценами с коротким и длинным названием. */
    name: 'Заголовок · переносится на две строки, не обрезается, шапка не прыгает',
    run: `var cut = 0, heads = {};
          Object.keys(SCENE_ROUTE).forEach(function (k) {
            pickScene(k);
            var el = document.getElementById('scene-name');
            var cs = getComputedStyle(el);
            if (el.scrollWidth > el.clientWidth + 1) cut++;
            if (el.scrollHeight > el.clientHeight + 1) cut++;
            if (cs.textOverflow === 'ellipsis') cut++;
            heads[Math.round(document.querySelector('.side-head').getBoundingClientRect().height)] = 1;
          });
          pickScene('sd');
          return { cut: cut, headSizes: Object.keys(heads).length };`,
    checks: [['обрезанных заголовков', 'cut', 0, 0],
             ['высот шапки', 'headSizes', 1, 0]],
  },
  {
    /* А1 · А2 · А55. Порог скорости (решение штаба от 13.08): открытие сцены
       не дольше 300 мс, перерисовка не дольше 100 мс.

       Было: «Изокванта и изокоста» открывалась 7052 мс ДАЖЕ на повторном
       входе, перерисовка внутри 3348 мс. Корень оказался не в рисовании (на
       холсте 75 элементов) и не в числе делений пополам, а в том, что
       вычисление функции двух переменных каждый раз заново РАЗБИРАЛО формулу
       через math.parse: при трассировке кривой уровня это десятки тысяч
       разборов одной строки за кадр.

       Здесь меряются самые тяжёлые сцены. Числа зависят от машины, поэтому
       запас взят с расчётом на медленную: проверка стережёт возврат
       алгоритмической расточительности, а не конкретный процессор. */
    name: 'Скорость · тяжёлые сцены укладываются в порог',
    run: `var best = function (fn) {
            var m = Infinity;
            for (var i = 0; i < 3; i++) { var t = performance.now(); fn(); m = Math.min(m, performance.now() - t); }
            return m;
          };
          var worstOpen = 0, worstDraw = 0, names = ['isoquant', 'ppfsum', 'plants', 'prod', 'consumer', 'tax'];
          names.forEach(function (k) {
            pickScene(k);
            worstOpen = Math.max(worstOpen, best(function () { pickScene(k); }));
            worstDraw = Math.max(worstDraw, best(function () { redrawAll(); }));
          });
          pickScene('sd');
          return { open: worstOpen, draw: worstDraw };`,
    checks: [['самое долгое открытие, мс', 'open', 0, 900],
             ['самая долгая перерисовка, мс', 'draw', 0, 300]],
  },
  {
    /* А53. Два сюжета открывались с ПУСТЫМИ блоками «Ключевые значения» и
       «Объяснение модели»: считалось, что в построении графиков и в
       деформациях считать нечего. «Построение графиков» — первая сцена, которую
       открывает новый человек, и первое, что он про калькулятор узнавал, что
       тут ничего нет. Считать есть что: нули, вершины, пересечения. */
    name: 'Панель · в построении графиков и деформациях есть что показать',
    run: `var vis = function (el) {
            if (!el) return 0;
            var out = '';
            var walk = function (n) {
              if (n.nodeType === 3) { out += n.nodeValue; return; }
              if (n.nodeType !== 1) return;
              var cs = getComputedStyle(n);
              if (cs.display === 'none' || cs.visibility === 'hidden') return;
              if (n.classList && n.classList.contains('katex-mathml')) return;
              if (n.tagName === 'ANNOTATION') return;
              [].forEach.call(n.childNodes, walk);
            };
            walk(el);
            return out.replace(/\\s+/g, ' ').trim().length;
          };
          var take = function (key) {
            pickScene(key);
            ['sb-btn', 'ex-btn'].forEach(function (id) {
              var b = document.getElementById(id);
              if (b && b.getAttribute('aria-expanded') !== 'true') b.click();
            });
            return { s: vis(document.getElementById('sb-body')),
                     e: vis(document.getElementById('ex-body')) };
          };
          var g = take('m-graph'), t = take('m-transform');
          pickScene('sd');
          return { gs: g.s, ge: g.e, ts: t.s, te: t.e };`,
    checks: [['построение: ключевые значения', 'gs', 400, 400],
             ['построение: объяснение', 'ge', 1500, 700],
             ['деформации: ключевые значения', 'ts', 400, 400],
             ['деформации: объяснение', 'te', 1500, 700]],
  },
  {
    /* А51 · А52. У монополиста кривой предложения не существует, оптимум там
       MR = MC. Раздел «Равновесие D = S» показывался в шести монопольных
       сценах, а в трёх из них ещё и навсегда застревал в состоянии «Отметьте
       одну кривую как D»: второй кривой в модели нет.

       Заголовок стал свойством сцены. Список монопольных сюжетов берётся по
       КЛЮЧУ КАРТОЧКИ: STATE.market для этого не годится — после монополии
       флаг остаётся поднятым в сценах рынка труда. */
    name: 'Монополия · раздел равновесия не обещает D = S',
    run: `var out = { badTitle: 0, stuck: 0, monoOk: 0, compOk: 0, autarky: 0, intervBad: 0, intervOk: 0 };
          var mono = ['mono', 'mono-nat', 'mono-d1', 'mono-d3', 'mono-kink', 'monoexport'];
          /* Конкурентные сцены БЕЗ вмешательства: заголовок «D = S» верен.
             «tax» и «ceil» открываются с уже включённым вмешательством
             (замер 24.08: taxActive и pcActive подняты сразу при входе),
             и «Равновесие D = S» там было бы неправдой — заголовок обязан
             называть то, что на рынке на самом деле. */
          var comp = ['sd', 'elast', 'ext'];
          var interv = ['tax', 'ceil'];
          var title = function () {
            var s = document.getElementById('sec-eq');
            var t = s && s.querySelector('.section-title');
            return t ? t.textContent.trim() : '';
          };
          var body = function () {
            var b = document.getElementById('info-eq');
            return b ? b.textContent.trim() : '';
          };
          mono.forEach(function (k) {
            pickScene(k); redrawAll();
            if (/D\\s*=\\s*S/.test(title())) out.badTitle++;
            if (/Отметьте|Появятся/.test(body())) out.stuck++;
            if (/MR\\s*=\\s*MC/.test(title())) out.monoOk++;
          });
          comp.forEach(function (k) {
            pickScene(k); redrawAll();
            if (/D\\s*=\\s*S/.test(title())) out.compOk++;
          });
          interv.forEach(function (k) {
            resetSceneMemory(); pickScene(k); redrawAll();
            if (/D\\s*=\\s*S/.test(title())) out.intervBad++;
            if (/Рынок (после|при)/.test(title())) out.intervOk++;
          });
          pickScene('smallopen'); redrawAll();
          if (/автарки/i.test(title())) out.autarky = 1;
          pickScene('sd');
          return out;`,
    checks: [['монопольных с «D = S»', 'badTitle', 0, 0],
             ['монопольных с застрявшей подсказкой', 'stuck', 0, 0],
             ['монопольных с «MR = MC»', 'monoOk', 6, 0],
             ['конкурентных без вмешательства с «D = S»', 'compOk', 3, 0],
             ['сцен с вмешательством, где всё ещё обещают «D = S»', 'intervBad', 0, 0],
             ['сцен с вмешательством, где заголовок называет рынок', 'intervOk', 2, 0],
             ['малая открытая: автаркия', 'autarky', 1, 0]],
  },
  {
    /* А46 · А47. Подписи величин на бумаге набраны математикой и совпадают с
       тем, что видно на экране. До этого в .tex не было ни одного
       математического режима вовсе, а набор подписей расходился с экраном в
       обе стороны: уходили скрытые координаты и не уходило видимое Q₁. */
    name: 'Экспорт · подписи величин математикой и только видимые',
    run: `pickScene('tax');
          var tex = buildTex('Проверка', '');
          var nodes = tex.match(/\\\\node\\[[^\\]]*\\] at \\(axis cs:[^)]*\\) \\{([^}]*)\\}/g) || [];
          var math = nodes.filter(function (n) { return /\\{\\$/.test(n); }).length;
          return {
            nodes: nodes.length,
            mathAll: (nodes.length && math === nodes.length) ? 1 : 0,
            // Координата уехала за ось и стоит одним числом с индексом (19.08).
            hasPb: tex.indexOf('$60_b$') >= 0 ? 1 : 0,
            hasPs: tex.indexOf('$40_s$') >= 0 ? 1 : 0,
            // Своя легенда одна: вторую, от pgfplots, убрали.
            legend: (tex.match(/addlegendentry/g) || []).length,
          };`,
    checks: [['подписей на холсте', 'nodes', 10, 4],
             ['все математикой', 'mathAll', 1, 0],
             ['цена покупателя с индексом', 'hasPb', 1, 0],
             ['цена продавца с индексом', 'hasPs', 1, 0],
             ['лишней легенды нет', 'legend', 0, 0]],
  },
  {
    /* А49. Кривая, у которой есть выражение, уходит формулой, а не таблицей
       из шестидесяти точек. Сдвинутая S + t объявляет своё выражение сцене
       через markExpr — общий способ, к которому подключается любой сюжет. */
    name: 'Экспорт · сдвинутая кривая уходит формулой',
    run: `pickScene('tax');
          var tex = buildTex('Проверка', '');
          var formulas = (tex.match(/\\\\addplot\\[[^\\]]*\\] *\\{/g) || []).length;
          var tables = [].slice.call(tex.match(/\\\\addplot\\[[^\\]]*\\] *coordinates \\{[^}]*\\}/g) || []);
          var big = tables.filter(function (t) { return (t.match(/\\(/g) || []).length > 5; }).length;
          return { formulas: formulas, big: big };`,
    /* Ожидание «4 таблицы по 60 точек» ОТМЕНЕНО пунктом Б6 и заменено на ноль.
       Те четыре таблицы были не кривыми: это обведённые по контуру значки
       «закрепки» у ключевых точек. Значок живёт в группе с display:none и
       появляется только под курсором, но проверка видимости стояла лишь у
       подписей, поэтому его фигуры уезжали в файл — одна из них с
       координатами (102; −0,88), то есть за пределами осей. Теперь в сцене
       налога длинных таблиц точек нет вовсе: все кривые ушли формулами. */
    checks: [['кривых формулой', 'formulas', 3, 1],
             ['длинных таблиц точек нет', 'big', 0, 0]],
  },
  {
    // Фаза 2: ключевые точки считаются и в «Математике».
    name: 'Ключевые точки · в «Математике» пересечения находятся',
    run: `setMode('math'); setMathSub('minmax'); resetZoom();
          STATE.mathFormula = 'x'; STATE.mathG2 = '4 - x';
          STATE.mathG3 = ''; STATE.mathG4 = ''; STATE.mathMinMax = 'min';
          redrawAll();
          var pts = crossPoints();
          var mid = pts.filter(function (p) { return Math.abs(p.x - 2) < 0.1; })[0] || {};
          return { n: pts.length > 0 ? 1 : 0, x: mid.x, y: mid.y };`,
    checks: [['точки есть', 'n', 1, 0], ['x пересечения', 'x', 2, 0.05],
             ['y пересечения', 'y', 2, 0.05]],
  },
  {
    // Окно сюжета уходит в минус, и корни там настоящие. Раньше поиск шёл по
    // CONFIG (0..100) и всё, что левее нуля, терялось.
    name: 'Ключевые точки · корни в отрицательной части плана',
    run: `setMode('math'); setMathSub('optimum'); resetZoom();
          STATE.mathFormula = 'x^3 - 3*x'; setMathWindow(-3, 3, -6, 6); redrawAll();
          var xs = crossPoints().filter(function (p) { return Math.abs(p.y) < 1e-6; })
                     .map(function (p) { return p.x; }).sort(function (a, b) { return a - b; });
          return { n: xs.length, x0: xs[0], x1: xs[1], x2: xs[2] };`,
    checks: [['корней три', 'n', 3, 0], ['левый корень', 'x0', -1.7321, 0.01],
             ['средний корень', 'x1', 0, 0.01], ['правый корень', 'x2', 1.7321, 0.01]],
  },
  {
    // Z = min(f1, f2) совпадает с f1 слева и с f2 справа. Совпадение на отрезке —
    // не пересечение: раньше на его краях появлялись узлы расчётной сетки
    // (1.2501 и 1.6668) и выдавали себя за ответ.
    name: 'Ключевые точки · совпадение кривых не выдаётся за пересечение',
    run: `setMode('math'); setMathSub('minmax'); resetZoom();
          STATE.mathFormula = 'x^2'; STATE.mathG2 = '4 - x';
          STATE.mathG3 = ''; STATE.mathG4 = ''; STATE.mathMinMax = 'min';
          setMathWindow(-5, 6, -3, 12); redrawAll();
          var pts = crossPoints();
          var near = function (v) { return pts.filter(function (p) { return Math.abs(p.x - v) < 0.08; }).length; };
          var real = pts.filter(function (p) { return Math.abs(p.x - 1.5616) < 0.01; })[0] || {};
          return { grid1: near(1.2501), grid2: near(1.6668), x: real.x, y: real.y };`,
    checks: [['узел сетки 1.25 — не точка', 'grid1', 0, 0], ['узел сетки 1.667 — не точка', 'grid2', 0, 0],
             ['настоящее пересечение x', 'x', 1.5616, 0.005], ['настоящее пересечение y', 'y', 2.4384, 0.005]],
  },
  {
    // Сетка рисуется по шкалам сцены. В «Математике» её не было совсем:
    // drawGrid считала линии от CONFIG и до полного плана не доходила.
    name: 'Сетка · работает в «Математике» во всех трёх режимах',
    run: `setMode('math'); setMathSub('optimum'); redrawAll();
          var n = function () { return document.querySelectorAll('svg#chart g.grid line').length; };
          setGridMode('dense'); var d = n();
          setGridMode('plain'); var o = n();
          setGridMode('off');   var f = n();
          setGridMode('plain');
          return { dense: d > 0 ? 1 : 0, plain: o > 0 ? 1 : 0, off: f, denser: d > o ? 1 : 0 };`,
    checks: [['подробная сетка есть', 'dense', 1, 0], ['упрощённая сетка есть', 'plain', 1, 0],
             ['без сетки — ноль линий', 'off', 0, 0], ['подробная гуще упрощённой', 'denser', 1, 0]],
  },
  {
    // Правая граница обязана включаться: у 10 − x кривая садится на ось ровно
    // в 10, и площадь треугольника равна 50, а не «почти 50».
    name: 'Площадь · под 10 − x на 0…10 ровно 50',
    run: `loadScene('sd'); STATE.curves = []; curveCounter = 0; renderCurveList();
          addCurve('10 - Q'); setRole(STATE.curves[0], 'demand');
          setRanges(20, 20); redrawAll();
          setAreaCalcMode('curve');
          var sel = document.getElementById('ac-pick');
          syncAreaCalcUI();
          sel.value = sel.options[1].value;
          clearAreaCalc(); runAreaCalc();
          var r = (STATE.areaCalcList || [])[0] || {};
          var res = { a: r.a, b: r.b, s: r.value };
          clearAreaCalc(); setAreaCalcMode('curve');
          return res;`,
    checks: [['левая граница', 'a', 0, 0.001], ['правая граница', 'b', 10, 0.001],
             ['площадь', 's', 50, 0.01]],
  },
  {
    // Особые точки: у x³ − 3x в окне −3…3 три корня, максимум и минимум.
    name: 'Особые точки · корни, максимум и минимум x³ − 3x',
    run: `setMode('math'); setMathSub('optimum'); resetZoom();
          STATE.mathFormula = 'x^3 - 3*x'; setMathWindow(-3, 3, -6, 6); redrawAll();
          var k = keyTargets();
          var mx = k.filter(function (p) { return /максимум/.test(p.name); })[0] || {};
          var mn = k.filter(function (p) { return /минимум/.test(p.name); })[0] || {};
          var ax = k.filter(function (p) { return /осью/.test(p.name); });
          return { roots: ax.length, xmax: mx.x, ymax: mx.y, xmin: mn.x, ymin: mn.y };`,
    checks: [['пересечений с осями', 'roots', 3, 0],
             ['максимум x', 'xmax', -1, 0.02], ['максимум y', 'ymax', 2, 0.02],
             ['минимум x', 'xmin', 1, 0.02], ['минимум y', 'ymin', -2, 0.02]],
  },
  {
    // Автарктические цены 1 и 2: мировая обязана лежать между ними. Раньше
    // введённая девятка молча обрезалась до предела ползунка и рисовалась
    // состоявшаяся торговля.
    name: 'Торговля Б · цена вне промежутка не обрезается и торговли нет',
    run: `pickScene('trade'); setTradeScenario('B');
          STATE.tbF1 = '100 - X'; STATE.tbF2 = '100 - 2*X';
          STATE.tbManualPrice = null; redrawAll();
          var d0 = STATE.tradeBData || {};
          STATE.tbManualPrice = 9; redrawAll();
          var d1 = STATE.tradeBData || {};
          var sl = document.getElementById('tb-price-slider');
          var res = { lo: d0.priceMin, hi: d0.priceMax, eq: d0.Pw,
                      slLo: parseFloat(sl.min), slHi: parseFloat(sl.max),
                      pw: d1.Pw, noTrade: d1.noTrade ? 1 : 0,
                      msg: /между 1 и 2/.test(d1.noTradeMsg || '') ? 1 : 0 };
          STATE.tbManualPrice = null; redrawAll();
          return res;`,
    checks: [['нижняя граница', 'lo', 1, 0.001], ['верхняя граница', 'hi', 2, 0.001],
             ['равновесная', 'eq', 1.41421, 0.001],
             ['ползунок от', 'slLo', 1, 0.001], ['ползунок до', 'slHi', 2, 0.001],
             ['цена не обрезана', 'pw', 9, 0.001],
             ['торговли нет', 'noTrade', 1, 0], ['промежуток назван', 'msg', 1, 0]],
  },

  /* ===================================================================
     СТРАХОВКА БЛОКА Б. Три сцены, у которых экономика посчитана ВЕРНО и
     сверена вручную до сотых (Б1, Б2, Б3). Эти числа — не «ожидания под
     текущий код», а результат независимого пересчёта по формулам. Любой
     их сдвиг после правок этой сессии означает регресс, а не улучшение:
     искать надо ошибку в коде, а не подгонять цифру здесь.
     =================================================================== */
  {
    // Б1. TC = Q³ − 6Q² + 15Q + 18, цена 15,54.
    //   VC = Q³ − 6Q² + 15Q,  AVC = Q² − 6Q + 15 → минимум в Q = 3, AVC = 6.
    //   ATC = Q² − 6Q + 15 + 18/Q → минимум ≈ 3,67, ATC ≈ 11,35.
    //   MC = 3Q² − 12Q + 15 = 15,54 → Q ≈ 4,04 (правая ветвь).
    //   ATC(4,04) ≈ 11,54; прибыль ≈ (15,54 − 11,54)·4,04 ≈ 16,16.
    name: 'Б1 · Издержки фирмы: min AVC, min ATC, оптимум и прибыль',
    run: `pickScene('costs');
          STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 18'; STATE.lrOn = true; STATE.lrPrice = 15.54;
          redrawAll();
          var lr = STATE.lr || {};
          return { avcQ: (STATE.minAVC||{}).Q, avcV: (STATE.minAVC||{}).val,
                   atcQ: (STATE.minATC||{}).Q, atcV: (STATE.minATC||{}).val,
                   Q: lr.Q, atc: lr.atc, profit: lr.profit };`,
    checks: [['Q при min AVC', 'avcQ', 3, 0.03], ['min AVC', 'avcV', 6, 0.02],
             ['Q при min ATC', 'atcQ', 3.67, 0.03], ['min ATC', 'atcV', 11.35, 0.02],
             ['Q при P = MC', 'Q', 4.04, 0.03], ['ATC(Q)', 'atc', 11.54, 0.03],
             ['прибыль', 'profit', 16.16, 0.15]],
  },
  {
    // Б2. TP = 30L² − L³.
    //   MP = 60L − 3L² → максимум в L = 10, MP = 300 (перегиб TP).
    //   AP = 30L − L²  → максимум в L = 15, AP = 225; там же MP = 60·15 − 3·225 = 225.
    //   TP максимален там, где MP = 0: L = 20, TP = 30·400 − 8000 = 4000.
    name: 'Б2 · Производственная функция: перегиб, max AP = MP, max TP',
    run: `pickScene('production');
          STATE.prodExpr = '30*L^2 - L^3'; redrawAll();
          var p = STATE.prod || {};
          return { mpL: (p.maxMP||{}).L, mpV: (p.maxMP||{}).val,
                   apL: (p.maxAP||{}).L, apV: (p.maxAP||{}).val, mpAtAP: p.mpAtMaxAP,
                   tpL: (p.maxTP||{}).L, tpV: (p.maxTP||{}).val };`,
    checks: [['L перегиба TP', 'mpL', 10, 0.1], ['max MP', 'mpV', 300, 1],
             ['L максимума AP', 'apL', 15, 0.1], ['max AP', 'apV', 225, 1],
             ['MP в max AP', 'mpAtAP', 225, 1.5],
             ['L максимума TP', 'tpL', 20, 0.1], ['max TP', 'tpV', 4000, 8]],
  },
  {
    // Б3. TC₁ = Q², TC₂ = 2Q², предел мощности одного завода 100 (PLANT_SCAN_Q).
    //   MC₁ = 2Q₁, MC₂ = 4Q₂. Равенство предельных ⇒ Q₂ = Q₁/2, то есть Q₁ = 2Q/3.
    //   Пока оба завода внутри мощности (Q ≤ 150):
    //     TC(Q) = (2Q/3)² + 2(Q/3)² = 4Q²/9 + 2Q²/9 = 2Q²/3.
    //   При Q = 150 первый завод упирается в 100, дальше растёт только второй:
    //     TC(Q) = 100² + 2(Q − 100)² = 10000 + 2(Q − 100)².
    //   Сверка по четырём точкам: Q = 60 → 2400; Q = 150 → 15000 (излом);
    //   Q = 180 → 10000 + 2·6400 = 22800; Q = 30 → 600.
    name: 'Б3 · Сложение заводов: 2Q²/3 до излома, дальше 10000 + 2(Q−100)²',
    run: `pickScene('plants');
          STATE.pl1 = 'Q^2'; STATE.pl2 = '2*Q^2'; redrawAll();
          var at = function (q) { STATE.plQ = q; redrawAll(); var c = plantsAt(q) || {}; return c; };
          var a = at(30), b = at(60), c = at(150), d = at(180);
          return { tc30: a.tcDirect, tc60: b.tcDirect, tc150: c.tcDirect, tc180: d.tcDirect,
                   q1at60: b.q1, q2at60: b.q2, mAt60: b.m };`,
    // Допуск 0,6 % — таблица горизонтального сложения строится по сетке из 400
    // уровней предельных издержек, поэтому точка между узлами интерполируется.
    checks: [['TC(30)', 'tc30', 600, 4], ['TC(60)', 'tc60', 2400, 15],
             ['TC(150) излом', 'tc150', 15000, 90], ['TC(180)', 'tc180', 22800, 140],
             ['Q₁ при Q=60', 'q1at60', 40, 0.3], ['Q₂ при Q=60', 'q2at60', 20, 0.3],
             ['MC при Q=60', 'mAt60', 80, 0.6]],
  },

  /* --- Фаза 1: экономика издержек (Б24–Б27) --------------------------- */
  {
    /* Б24. Постоянные затраты выводятся из самой функции, а не из отдельного
       поля. Проверка ровно того случая, на котором ломался прежний код:
       свободный член меняем, поля FC не существует, и всё пересчитывается.
       TC = Q³ − 6Q² + 15Q + 40 ⇒ FC = 40, AVC = Q² − 6Q + 15 (та же, min = 6
       при Q = 3), ATC = AVC + 40/Q ⇒ минимум смещается вправо от 3,67. */
    name: 'Б24 · Постоянные затраты идут из TC(0), отдельного поля нет',
    run: `resetSceneMemory(); pickScene('costs');
          STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 40'; redrawAll();
          var fi = STATE.costsFCInfo || {};
          var vcAt5 = costVC(5), afcAt5 = costAFC(5);
          var atcQ = (STATE.minATC || {}).Q;
          return { fc: fi.val, exact: fi.kind === 'exact' ? 1 : 0,
                   vc5: vcAt5, afc5: afcAt5, avcMin: (STATE.minAVC || {}).val, atcQ: atcQ,
                   noField: document.getElementById('inp-fc') ? 1 : 0 };`,
    // VC(5) = 125 − 150 + 75 = 50; AFC(5) = 40/5 = 8; min AVC = 6 (не зависит от FC).
    checks: [['FC', 'fc', 40, 0.001], ['взято точно', 'exact', 1, 0],
             ['VC(5)', 'vc5', 50, 0.01], ['AFC(5)', 'afc5', 8, 0.01],
             ['min AVC', 'avcMin', 6, 0.02], ['Q при min ATC', 'atcQ', 4.5, 0.35],
             ['поля FC нет', 'noField', 0, 0]],
  },
  {
    /* Б25. Правило остановки МЕНЯЕТ ответ, а не только приписку. При цене 4
       (ниже min AVC = 6) выпуск ноль, а убыток равен постоянным затратам 18.
       Корень P = MC при этом остаётся отдельным числом. */
    name: 'Б25 · Ниже min AVC: выпуск 0, убыток равен FC',
    run: `resetSceneMemory(); pickScene('costs');
          STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 18'; STATE.lrOn = true;
          STATE.lrPrice = 4; redrawAll();
          var a = STATE.lr || {};
          STATE.lrPrice = 15.54; redrawAll();
          var b = STATE.lr || {};
          return { shut: a.shutdown ? 1 : 0, Q: a.Q, loss: a.profit, root: a.Qmc,
                   okShut: b.shutdown ? 1 : 0, okQ: b.Q };`,
    /* Корень при P = 4: 3Q² − 12Q + 15 = 4 ⇒ 3Q² − 12Q + 11 = 0 ⇒
       Q = (12 ± √12)/6, больший корень 2,577. Первым заходом здесь стояло 3,03
       (моя арифметическая описка при составлении случая), код давал 2,577 —
       правильно он и давал. */
    checks: [['закрытие', 'shut', 1, 0], ['выпуск', 'Q', 0, 0.001],
             ['убыток = −FC', 'loss', -18, 0.01], ['корень P = MC есть', 'root', 2.577, 0.02],
             ['при 15,54 не закрытие', 'okShut', 0, 0], ['выпуск при 15,54', 'okQ', 4.04, 0.03]],
  },
  {
    /* Б26. Край цикла сканирования больше не выдаётся за экономическую точку.
       AVC = Q растёт всюду ⇒ внутреннего минимума нет; ATC = Q + 18/Q ⇒ есть,
       в Q = √18. Постоянная кривая ⇒ минимума нет вовсе. */
    name: 'Б26 · Нет внутреннего минимума — нет и числа',
    run: `resetSceneMemory(); pickScene('costs');
          STATE.costsTC = 'Q^2 + 18'; redrawAll();
          var a = { avc: (STATE.minAVC||{}).kind, atc: (STATE.minATC||{}).kind,
                    atcQ: (STATE.minATC||{}).Q, shown: !!realMin(STATE.minAVC) };
          STATE.costsTC = '20*Q'; redrawAll();
          var b = { avc: (STATE.minAVC||{}).kind, atc: (STATE.minATC||{}).kind };
          var txt = (document.getElementById('info-costs')||{}).innerText || '';
          return { a1: a.avc === 'boundary' ? 1 : 0, a2: a.atc === 'interior' ? 1 : 0,
                   atcQ: a.atcQ, shown: a.shown ? 1 : 0,
                   b1: b.avc === 'flat' ? 1 : 0, b2: b.atc === 'flat' ? 1 : 0,
                   said: /постоянна/.test(txt) ? 1 : 0 };`,
    checks: [['AVC = Q — край', 'a1', 1, 0], ['ATC — внутренний', 'a2', 1, 0],
             ['Q при min ATC = √18', 'atcQ', 4.243, 0.02],
             ['точки закрытия не рисуем', 'shown', 0, 0],
             ['ATC постоянна', 'b1', 1, 0], ['AVC постоянна', 'b2', 1, 0],
             ['и сказано словами', 'said', 1, 0]],
  },
  {
    /* Б27. При постоянных предельных затратах блок долгого периода больше не
       исчезает молча: числа нет, зато есть объяснение — и разное для трёх
       положений цены относительно MC = 20. */
    name: 'Б27 · Постоянная MC: вместо пустоты объяснение',
    run: `resetSceneMemory(); pickScene('costs');
          STATE.costsTC = '20*Q'; STATE.lrOn = true;
          var probe = function (p) { STATE.lrPrice = p; redrawAll(); var l = STATE.lr || {};
            return { has: l.note ? 1 : 0, q: l.Q, t: l.note || '' }; };
          var hi = probe(30), lo = probe(10), eq = probe(20);
          return { hiHas: hi.has, loHas: lo.has, eqHas: eq.has,
                   hiQ: hi.q === null ? 1 : 0,
                   hiT: /наращивать без предела/.test(hi.t) ? 1 : 0,
                   loT: /не производить вовсе/.test(lo.t) ? 1 : 0,
                   eqT: /единственного оптимума нет/.test(eq.t) ? 1 : 0 };`,
    checks: [['цена выше MC — пояснение', 'hiHas', 1, 0], ['цена ниже MC', 'loHas', 1, 0],
             ['цена равна MC', 'eqHas', 1, 0], ['выпуска нет', 'hiQ', 1, 0],
             ['текст «без предела»', 'hiT', 1, 0], ['текст «не производить»', 'loT', 1, 0],
             ['текст «оптимума нет»', 'eqT', 1, 0]],
  },
  {
    /* Цена закрытия — нижняя грань AVC, а не обязательно точка на кривой.
       У TC = 0,5Q² + 10Q + 50 средние переменные 0,5Q + 10 растут всюду:
       точки закрытия на графике нет, но ниже 10 они не опускаются, поэтому
       при цене 8 производить нельзя, а при 12 можно. */
    name: 'Б25 · Цена закрытия как нижняя грань AVC без точки на кривой',
    run: `resetSceneMemory(); pickScene('costs');
          STATE.costsTC = '0.5*Q^2 + 10*Q + 50'; STATE.lrOn = true;
          STATE.lrPrice = 8; redrawAll(); var a = STATE.lr || {};
          STATE.lrPrice = 12; redrawAll(); var b = STATE.lr || {};
          return { kind: (STATE.minAVC||{}).kind === 'boundary' ? 1 : 0,
                   sp: a.shutPrice, isPt: a.shutIsPoint ? 1 : 0,
                   shut8: a.shutdown ? 1 : 0, loss8: a.profit,
                   shut12: b.shutdown ? 1 : 0, Q12: b.Q };`,
    // MC = Q + 10 = 12 ⇒ Q = 2.
    checks: [['у AVC нет внутр. минимума', 'kind', 1, 0], ['цена закрытия', 'sp', 10, 0.02],
             ['точкой не показываем', 'isPt', 0, 0],
             ['при 8 закрытие', 'shut8', 1, 0], ['убыток = −FC', 'loss8', -50, 0.01],
             ['при 12 работаем', 'shut12', 0, 0], ['выпуск при 12', 'Q12', 2, 0.03]],
  },
  {
    /* Б24, второй способ ввода: кривые задаются по отдельности и ничего не
       выводится одно из другого. MC = 3Q² − 12Q + 15, ATC = Q² − 6Q + 15 + 18/Q,
       AVC = Q² − 6Q + 15 — те же кривые, что даёт TC = Q³ − 6Q² + 15Q + 18,
       поэтому числа обязаны совпасть с Б1, а несогласованности быть не должно. */
    name: 'Б24 · Режим «задам кривые»: числа те же, несогласованности нет',
    run: `resetSceneMemory(); pickScene('costs'); setCostsInputMode('curves');
          STATE.costsMCx = '3*Q^2 - 12*Q + 15';
          STATE.costsATCx = 'Q^2 - 6*Q + 15 + 18/Q';
          STATE.costsAVCx = 'Q^2 - 6*Q + 15';
          STATE.lrOn = true; STATE.lrPrice = 15.54; redrawAll();
          var ok = { avc: (STATE.minAVC||{}).val, atc: (STATE.minATC||{}).val,
                     Q: (STATE.lr||{}).Q, fc: (STATE.costsFCInfo||{}).val, warn: STATE.costsWarn ? 1 : 0 };
          STATE.costsATCx = 'Q^2 - 2*Q + 40'; redrawAll();
          ok.warnBad = STATE.costsWarn ? 1 : 0;
          setCostsInputMode('tc');
          return ok;`,
    checks: [['min AVC', 'avc', 6, 0.02], ['min ATC', 'atc', 11.35, 0.02],
             ['выпуск', 'Q', 4.04, 0.03], ['FC из ATC − AVC', 'fc', 18, 0.2],
             ['согласованные — молчим', 'warn', 0, 0],
             ['несогласованные — говорим', 'warnBad', 1, 0]],
  },

  /* --- Фаза 2: эластичность предложения (Б28, Б29) -------------------- */
  {
    /* Б28. Правило было записано наоборот. Вывод: Q = (P − b)/a, поэтому
       Es = (dQ/dP)·(P/Q) = P/(P − b). У S: P = 10 + Q в точке Q = 10, P = 20
       выходит Es = 20/10 = 2 > 1, то есть ЭЛАСТИЧНО при ПОЛОЖИТЕЛЬНОМ
       перехвате цены. Проверяем и число, и то, что в тексте стоит нужное
       слово рядом с нужным перехватом.
       Б29. Для кривого предложения про перехват не говорим вовсе. */
    name: 'Б28 · Эластичность предложения: перехват вверх это эластично',
    run: `resetSceneMemory(); pickScene('elast');
          var setS = function (expr) {
            var s = curveByRole('supply');
            if (s) updateCurveExpr(s, expr);
            redrawAll();
          };
          STATE.showElastS = true;
          setS('10 + Q');
          STATE.elastQS = 10; redrawAll();
          var lin = STATE.elastS || {};
          var t1 = (document.getElementById('info-elast') || {}).innerText || '';
          setS('Q^2');
          STATE.elastQS = 10; redrawAll();
          var t2 = (document.getElementById('info-elast') || {}).innerText || '';
          return {
            Es: lin.absEs,
            // «эластично» стоит РЯДОМ с «положительный перехват», а не «неэластично».
            good: /положительный перехват цены., предложение эластично/.test(t1.replace(/\\s+/g, ' ')) ? 1 : 0,
            bad: /положительным перехватом цены неэластично/.test(t1) ? 1 : 0,
            noIntercept: /перехват/.test(t2) ? 1 : 0,
            varies: /от точки к точке/.test(t2) ? 1 : 0,
          };`,
    checks: [['|Es| в точке Q = 10', 'Es', 2, 0.02],
             ['сказано «эластично»', 'good', 1, 0],
             ['старой формулировки нет', 'bad', 0, 0],
             ['у кривой про перехват молчим', 'noIntercept', 0, 0],
             ['и говорим про точку', 'varies', 1, 0]],
  },

  /* --- Фаза 3: быстрые починки экспорта (Б6–Б10, Б37) ----------------- */
  {
    /* Б37. Название оси — свойство сцены, а не побочный эффект того, кто
       рисует подпись. Сцены издержек, производства и заводов рисуют вертикаль
       сами и присылали пустую строку, из-за чего в выгрузке на графике ЗАТРАТ
       стояло ylabel={P} от прошлой сцены.
       ⚠️ ПЕРЕСЧИТАН ПОД ПРАВИЛО 46 (подпись оси — символ величины, не фраза).
       Ожидание «у издержек в подписи стоит слово Издержки» отменено каноном:
       там та же величина, что и на рынке, и у неё есть буква. Защита от
       ПРОТЕЧКИ подписи прошлой сцены — та, ради чего тест и заведён, — теперь
       проверяется прямо: тот же ключ читается ДО и ПОСЛЕ чужой сцены. */
    name: 'Б37 · Подпись оси в .tex совпадает со сценой',
    run: `resetSceneMemory();
          var yl = function (k) { pickScene(k); redrawAll();
            var m = /ylabel=\\{([^}]*)\\}/.exec(buildTex('', '')); return m ? m[1] : ''; };
          var xl = function (k) { pickScene(k); redrawAll();
            var m = /xlabel=\\{([^}]*)\\}/.exec(buildTex('', '')); return m ? m[1] : ''; };
          var costs = yl('costs'), plants = yl('plants'), prodY = yl('prod'), prodX = xl('prod');
          var sd = yl('sd');
          var costsAfterProd = yl('costs'), prodAfterCosts = yl('prod');
          return { costsOk: costs === 'P' ? 1 : 0,
                   plantsOk: plants === 'P' ? 1 : 0,
                   prodOk: /TP/.test(prodY) ? 1 : 0, prodX: prodX === 'L' ? 1 : 0,
                   noLeak: (costsAfterProd === costs && prodAfterCosts === prodY) ? 1 : 0,
                   sdOk: sd === 'P' ? 1 : 0 };`,
    checks: [['издержки', 'costsOk', 1, 0], ['два завода', 'plantsOk', 1, 0],
             ['производство по вертикали', 'prodOk', 1, 0], ['производство по горизонтали', 'prodX', 1, 0],
             ['подпись не протекает между сценами', 'noLeak', 1, 0], ['на рынке по-прежнему P', 'sdOk', 1, 0]],
  },
  {
    /* Б6. В файл не уходит ничего, чего человек не видит. Проверяем на сцене
       налога: у ключевых точек есть значок «закрепки» в спрятанной группе, и
       раньше его подложка и контур уезжали в .tex.
       Б9. Точка «излом MC» на графике совокупных ЗАТРАТ — из другой кривой.
       Б10. Ось не должна уходить далеко за данные. */
    name: 'Б6 · В .tex нет спрятанного, чужого и фона',
    run: `resetSceneMemory(); pickScene('tax'); redrawAll();
          var tex = buildTex('', '');
          var canvas = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
          var hex = canvas.replace('#', '').toUpperCase();
          var outside = 0;
          var re = /\\(axis cs:(-?[\\d.]+),(-?[\\d.]+)\\)/g, m;
          while ((m = re.exec(tex))) { if (+m[1] < -1e-6 || +m[2] < -1e-6) outside++; }
          // Точка «излом MC» на графике затрат: в сцене заводов её быть не должно.
          resetSceneMemory(); pickScene('plants'); setPlantsView('tc'); redrawAll();
          var names = keyTargets().map(function (k) { return k.name; }).join('|');
          var mcOnTc = /MC/.test(names) ? 1 : 0;
          setPlantsView('mc'); redrawAll();
          var mcOnMc = /MC/.test(keyTargets().map(function (k) { return k.name; }).join('|')) ? 1 : 0;
          // Б10: верх оси не дальше трети над данными.
          var top = CONFIG.Pmax, data = STATE.plants ? STATE.plants.mMax : 0;
          return { bg: tex.indexOf('c' + hex) >= 0 ? 1 : 0, outside: outside,
                   mcOnTc: mcOnTc, mcOnMc: mcOnMc, over: data > 0 ? top / data : 1 };`,
    checks: [['цвета холста в файле нет', 'bg', 0, 0],
             ['ничего за осями', 'outside', 0, 0],
             ['на графике TC изломов MC нет', 'mcOnTc', 0, 0],
             ['на графике MC они есть', 'mcOnMc', 1, 0],
             ['запас оси не больше трети', 'over', 1.15, 0.18]],
  },
  {
    /* Б8. Голое число — математика, а не проза: узкого неразрывного пробела
       (разделителя разрядов) в шрифтах T2A нет вовсе. Плюс подпись, севшая на
       саму ось, отодвигается от неё сдвигом в пунктах.

       ⚠️ ОЖИДАНИЕ ПЕРЕСЧИТАНО 20.08, А НЕ ОТКЛЮЧЕНО. Раньше подпись цены
       разворачивалась ВНУТРЬ первой четверти (левое поле было слишком узким
       для «60_b»), приезжала на бумагу с якорем west и отодвигалась вправо,
       в поле построения. Теперь она стоит левее оси, как и требует решение
       владельца: якорь east, а сдвиг — наружу, влево. Проверяется то же самое
       по сути: подпись не сидит на самой оси, а отодвинута от неё. */
    name: 'Б8 · Числа в .tex математикой и не на самой оси',
    run: `resetSceneMemory(); pickScene('tax'); redrawAll();
          var tex = buildTex('', '');
          var thin = /\\u202F/.test(tex) ? 1 : 0;
          var shifted = /at \\(axis cs:0,60\\)/.test(tex) && /anchor=east[^;]*xshift=-3pt[^;]*at \\(axis cs:0,60\\)/.test(tex) ? 1 : 0;
          var num = quantityTex('30\\u202F000');
          var plain = quantityTex('12');
          return { thin: thin, shifted: shifted,
                   num: num === '$30\\\\,000$' ? 1 : 0, plain: plain === '$12$' ? 1 : 0 };`,
    checks: [['узкого пробела в файле нет', 'thin', 0, 0],
             ['подпись на оси отодвинута', 'shifted', 1, 0],
             ['30 000 набрано математикой', 'num', 1, 0],
             ['и просто число тоже', 'plain', 1, 0]],
  },

  /* --- Фаза 4: перетаскивание цены (Б32, Б33) ------------------------- */
  {
    /* Б32. Разбор издержек от цены не зависит, поэтому за целое перетаскивание
       он не должен считаться ни разу: раньше на каждый пиксель уходило три
       скана по 2400 вычислений формулы плюс полная пересборка холста.
       Б33. Округление и синхронизация трёх показов цены — на отпускании.
       Проверяем и то, что ОТВЕТ от этого не изменился. */
    name: 'Б32 · Перетаскивание цены не пересобирает сцену',
    run: `resetSceneMemory(); pickScene('costs');
          STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 18'; STATE.lrOn = true;
          setLrPrice(20);
          var scans = 0, during = 0, onRelease = 0;
          var realMin = window.minOf, realDraw = window.redrawCosts;
          window.minOf = function () { scans++; return realMin.apply(this, arguments); };
          window.redrawCosts = function () { during++; return realDraw.apply(this, arguments); };
          var sc = mainScales(), y0 = sc.my(20);
          ['sb-btn'].forEach(function (id) { var b = document.getElementById(id);
            if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); });
          beginLrDrag();
          var midSlider = null, midTypeset = 0;
          for (var i = 1; i <= 40; i++) {
            dragLrPrice(sc.my.invert(y0 - 200 * i / 40));
            if (i === 20) {
              midSlider = parseFloat(document.getElementById('lr-price-slider').value);
              // Панель в ПУТИ обязана быть набрана так же, как в покое.
              midTypeset = document.querySelectorAll('#sb-body .stat .katex').length > 0 ? 1 : 0;
            }
          }
          var moved = (STATE.lr || {}).Q != null ? 1 : 0;
          // Пересборка на ОТПУСКАНИИ обязана быть ровно одна: считаем отдельно.
          var mark = during;
          endLrDrag();
          onRelease = during - mark;
          window.minOf = realMin; window.redrawCosts = realDraw;
          var endPrice = STATE.lrPrice, endQ = (STATE.lr || {}).Q;
          var slider = document.getElementById('lr-price-slider');
          var endSlider = parseFloat(slider.value), step = parseFloat(slider.step) || 1;
          // Тот же ответ, полученный обычным путём.
          setLrPrice(0); setLrPrice(endPrice);
          return { scans: scans, during: mark, onRelease: onRelease, moved: moved,
                   slid: midSlider === 20 ? 1 : 0,
                   sameSlider: Math.abs(endSlider - endPrice) <= step / 2 + 1e-9 ? 1 : 0,
                   rounded: Math.abs(endPrice * 100 - Math.round(endPrice * 100)) < 1e-9 ? 1 : 0,
                   sameQ: Math.abs((STATE.lr || {}).Q - endQ) < 1e-6 ? 1 : 0,
                   typeset: midTypeset };`,
    /* Ползунок цены сделан с шагом 0,5 и точнее показать не может, поэтому
       после отпускания он совпадает с числом с точностью до половины шага;
       подпись и числовое поле показывают цену как есть. */
    checks: [['сканов за перетаскивание', 'scans', 0, 0],
             ['пересборок в пути', 'during', 0, 0],
             ['и ровно одна на отпускании', 'onRelease', 1, 0],
             ['выпуск при этом считается', 'moved', 1, 0],
             ['ползунок в пути не дёргается', 'slid', 1, 0],
             ['на отпускании ползунок догоняет', 'sameSlider', 1, 0],
             ['и цена округлена', 'rounded', 1, 0],
             ['ответ тот же, что обычным путём', 'sameQ', 1, 0],
             ['в пути панель набрана формулами', 'typeset', 1, 0]],
  },

  /* --- Фаза 5: панели (Б12–Б15, Б39–Б41) ------------------------------ */
  {
    /* Б15. Дробная часть отделяется запятой, а числовое поле продолжает
       получать машинную запись: type=number с запятой молча очищается.
       Б14. Между именем величины и числом стоит отбивка.
       Б40. Составное значение разбирается на части, но десятичная запятая
       границей списка НЕ считается. */
    name: 'Б15 · Запятая на экране, точка в числовом поле',
    run: `resetSceneMemory(); pickScene('costs');
          var pieces = statPieces('Q = 3,67, ATC = 11,35');
          var one = statPieces('(1,73; -3,46)');
          return { show: fmt(3.67) === '3,67' ? 1 : 0,
                   input: fmtInput(3.67) === '3.67' ? 1 : 0,
                   thousand: fmt(30000).indexOf(',') < 0 ? 1 : 0,
                   n: pieces.length, first: pieces[0] === 'Q = 3,67' ? 1 : 0,
                   inBrackets: one.length };`,
    checks: [['на экране запятая', 'show', 1, 0], ['в поле точка', 'input', 1, 0],
             ['разряды не путаются с дробью', 'thousand', 1, 0],
             ['составное делится надвое', 'n', 2, 0], ['и по нужному месту', 'first', 1, 0],
             ['внутри скобок не режем', 'inBrackets', 1, 0]],
  },
  {
    /* Б39, Б12. Причина наложения: у значения, набранного KaTeX, нет чем
       сжиматься, а колонке подписи разрешено ужаться до нуля. Плюс сетка
       строки держала 78 px под знак равенства даже там, где знака нет.
       Проверяем ИТОГ: ни в одной строке табло подпись и значение не
       перекрываются напечатанным текстом. */
    name: 'Б39 · Подпись и значение в табло не налезают друг на друга',
    run: `var keys = ['elast', 'costs', 'prod', 'mono-kink', 'm-optimum', 'ext', 'trade'];
          var ink = function (el) { var r = document.createRange(); r.selectNodeContents(el);
            var b = r.getBoundingClientRect();
            return (b.width > 0 && b.height > 0) ? b : el.getBoundingClientRect(); };
          var over = 0, rows = 0, stacked = 0;
          keys.forEach(function (k) {
            resetSceneMemory(); pickScene(k);
            ['sb-btn', 'ex-btn'].forEach(function (id) {
              var b = document.getElementById(id);
              if (b && b.getAttribute('aria-expanded') !== 'true') b.click();
            });
            document.querySelectorAll('.sb-body .stat').forEach(function (row) {
              var lab = row.querySelector(':scope > span'), val = row.querySelector(':scope > b');
              if (!lab || !val) return;
              var lr = ink(lab), vr = ink(val);
              if (!(lr.width > 0 && vr.width > 0)) return;
              rows++;
              if (row.classList.contains('stat-stack')) { stacked++; return; }
              var ox = Math.min(lr.right, vr.right) - Math.max(lr.left, vr.left);
              var oy = Math.min(lr.bottom, vr.bottom) - Math.max(lr.top, vr.top);
              if (ox > 1 && oy > 1) over++;
            });
          });
          return { over: over, rows: rows > 30 ? 1 : 0, stacked: stacked > 0 ? 1 : 0 };`,
    checks: [['наложений', 'over', 0, 0], ['строки нашлись', 'rows', 1, 0],
             ['стопкой разложено', 'stacked', 1, 0]],
  },

  /* --- Фаза 6: робастность (Б30, Б31) --------------------------------- */
  {
    /* Б30. Линейность определялась по трём точкам в СЕРЕДИНЕ диапазона, и
       кусочная «max(0, 80 - Q)» на них выглядела прямой P = 80 − Q: наклон
       в 20, 50 и 80 всюду единичный. Дальше evalCurve шёл быстрым путём по
       этим коэффициентам, и при Q > 80 цена уходила в минус вместо нуля. */
    name: 'Б30 · Кусочная не выдаётся за прямую',
    run: `resetSceneMemory(); pickScene('sd');
          var d = curveByRole('demand');
          updateCurveExpr(d, 'max(0, 80 - Q)'); redrawAll();
          var kink = { lin: d.linear ? 1 : 0, at90: evalCurve(d, 90), at40: evalCurve(d, 40) };
          updateCurveExpr(d, '100 - Q'); redrawAll();
          var line = { lin: d.linear ? 1 : 0, a: d.linear ? d.linear.a : null, b: d.linear ? d.linear.b : null };
          return { kinkLin: kink.lin, at90: kink.at90, at40: kink.at40,
                   lineLin: line.lin, a: line.a, b: line.b };`,
    checks: [['кусочная не прямая', 'kinkLin', 0, 0],
             ['за изломом ноль, а не минус', 'at90', 0, 0.001],
             ['до излома как надо', 'at40', 40, 0.001],
             ['настоящая прямая распознана', 'lineLin', 1, 0],
             ['наклон', 'a', -1, 0.001], ['свободный член', 'b', 100, 0.001]],
  },
  {
    /* Б31. Площадь между кривыми при НЕСКОЛЬКИХ пересечениях: модуль
       интеграла даёт разность площадей, куски с разными знаками гасят друг
       друга. Контрольный случай: g(x) = sin-подобная смена знака на [0, 2],
       где ∫ = 0, а площадь равна 2. Берём g(x) = 1 − x на [0, 2]: интеграл
       0, площадь двух треугольников по 1/2 равна 1. */
    name: 'Б31 · Площадь считается кусками, а не модулем интеграла',
    run: `var g = function (x) { return 1 - x; };
          var naive = Math.abs(integrate(g, 0, 2));
          var honest = areaBetween(g, 0, 2);
          var one = areaBetween(g, 0, 1);
          var n2 = crossingCount(function (x) { return (x - 1) * (x - 3); }, 0, 4);
          var n1 = crossingCount(g, 0, 2);
          return { naive: naive, honest: honest, one: one, n2: n2, n1: n1 };`,
    checks: [['модуль интеграла обнуляется', 'naive', 0, 0.01],
             ['площадь считается верно', 'honest', 1, 0.01],
             ['на одном знаке ответ прежний', 'one', 0.5, 0.01],
             ['два пересечения найдены', 'n2', 2, 0], ['одно — тоже', 'n1', 1, 0]],
  },
  {
    /* Б26 в производственной функции: край сетки — не экстремум.
       У TP = 10L предельный продукт постоянен (перегиба нет), у TP = L²
       он растёт всюду (максимум на краю), у TP = 100√L максимума выпуска
       нет вовсе. Числа классической 30L² − L³ при этом не двигаются. */
    name: 'Б26 · Производство: нет экстремума — нет и числа',
    run: `resetSceneMemory(); pickScene('prod');
          var kinds = function (e) { STATE.prodExpr = e; redrawAll(); var p = STATE.prod || {};
            return [(p.maxMP||{}).kind, (p.maxAP||{}).kind, (p.maxTP||{}).kind].join('/'); };
          var flat = kinds('10*L');
          var grow = kinds('L^2');
          var root = kinds('100*sqrt(L)');
          var ok = kinds('30*L^2 - L^3');
          var p = STATE.prod || {};
          return { flat: flat === 'flat/flat/boundary' ? 1 : 0,
                   grow: /boundary/.test(grow) ? 1 : 0,
                   root: /boundary/.test(root) ? 1 : 0,
                   ok: ok === 'interior/interior/interior' ? 1 : 0,
                   mp: (p.maxMP||{}).val, ap: (p.maxAP||{}).val };`,
    checks: [['MP постоянна — так и сказано', 'flat', 1, 0],
             ['MP растёт всюду — край', 'grow', 1, 0],
             ['у корня максимума нет', 'root', 1, 0],
             ['у классической всё внутри', 'ok', 1, 0],
             ['max MP не поехал', 'mp', 300, 1], ['max AP не поехал', 'ap', 225, 1]],
  },

  {
    /* Утечка параметра между моделями (ревью 19.08). Контрольный опыт
       владельца: одна и та же модель, два пути, разный результат.

       Прямой путь в «Потоварные налоги» — ползунков-параметров ноль. Через
       «Построение графиков» с буквой в формуле — ползунок «a» оставался на
       экране рядом с настоящей ставкой t, хотя в состоянии его уже не было.

       Течёт не состояние, а РАЗМЕТКА: правая панель пересобирается по смене
       подписи своего содержимого, а «заставить пересобраться» записывали
       пустой строкой — то есть тем же значением, что и законная подпись сцены
       без ползунков. Проверяем оба пути и требуем одинакового числа. */
    name: 'Утечка · параметр не переезжает из модели в модель',
    run: `resetSceneMemory();
          pickScene('tax'); redrawAll();
          var direct = document.querySelectorAll('.pchip-param').length;
          pickScene('m-graph');
          STATE.curves = []; curveCounter = 0;
          addCurve('x^2-a*x'); syncParams(); redrawAll();
          var inGraph = document.querySelectorAll('.pchip-param').length;
          var letter = STATE.params && STATE.params.a ? 1 : 0;
          pickScene('tax'); redrawAll();
          var after = document.querySelectorAll('.pchip-param').length;
          var stateAfter = Object.keys(STATE.params || {}).length;
          return { direct: direct, inGraph: inGraph, letter: letter,
                   after: after, stateAfter: stateAfter };`,
    checks: [['прямым путём ползунков нет', 'direct', 0, 0],
             ['в «Построении графиков» буква завелась', 'letter', 1, 0],
             ['и ползунок показан', 'inGraph', 1, 0],
             ['после перехода ползунков столько же, сколько прямым путём', 'after', 0, 0],
             ['и в состоянии букв не осталось', 'stateAfter', 0, 0]],
  },

  {
    /* 20.08. ЧИСЛО НА ОСИ ПРИБИТО К СВОЕМУ МЕСТУ.

       Деление шкалы и подпись координаты отвечают на вопрос «где именно»;
       сдвинутое число отвечает на него неправдой. Разведение подписей
       двигало их наравне с прочими шагом 13 px, и деление уезжало от оси на
       13, 26 или 65 пикселей — это и есть «подпись деления оторвалась от
       оси» из ревью владельца. Замером поймано в дискриминации 3-й степени и
       на внешнем рынке: последнее деление обеих панелей стояло на 26 px выше
       своего ряда.

       Проверяем прямо: снимаем координаты всех чисел на осях, зовём
       разведение ещё раз и убеждаемся, что ни одно не тронулось. Заодно —
       что класс `axis-num` есть во ВСЕХ сценах: у панельных сюжетов свои
       рисователи осей, и там его не ставили вовсе. */
    name: 'Числа на осях не двигаются разведением подписей',
    run: `var moved = 0, noScale = [], scenes = Object.keys(SCENE_ROUTE);
          scenes.forEach(function (k) {
            resetSceneMemory(); pickScene(k); redrawAll();
            var nodes = [].slice.call(document.querySelectorAll('#chart text.axis-num, #chart text.coord-num'));
            if (!nodes.length) { noScale.push(k); return; }
            var was = nodes.map(function (t) { return t.getAttribute('x') + ',' + t.getAttribute('y'); });
            spreadLabels();
            nodes.forEach(function (t, i) {
              if (t.getAttribute('x') + ',' + t.getAttribute('y') !== was[i]) moved++;
            });
          });
          return { moved: moved, noScale: noScale.length, scenes: scenes.length };`,
    checks: [['сдвинутых чисел на осях', 'moved', 0, 0],
             ['сцен без разметки шкалы', 'noScale', 0, 0],
             ['сцен всего', 'scenes', 44, 0]],   // +3: 'taxes' (объединённый сюжет налогов), 'quota' и 'sdsum' (сложение)
  },

  {
    /* 20.08, п. 4.5. ДЛИННОЕ ИМЯ КРИВОЙ ПОКАЗЫВАЕТСЯ ЦЕЛИКОМ.
       Обрез стоял на четырнадцати символах, и «Спрос жителей города»
       превращался в «Спрос жителей…» даже когда справа оставалось шестьдесят
       с лишним пикселей свободного холста: резал жёсткий лимит, а не край поля.
       Решение владельца: имя переезжает целиком, на вторую строку не рвётся. */
    name: 'Имя кривой не обрезается многоточием',
    run: `resetSceneMemory(); pickScene('sd'); redrawAll();
          STATE.curves[0].label = 'Спрос жителей города'; redrawAll();
          var own = function (n) { return [].filter.call(n.childNodes, function (c) { return c.nodeType === 3; })
                                            .map(function (c) { return c.nodeValue; }).join(''); };
          var found = null, wide = 0, box = document.getElementById('chart').getBoundingClientRect();
          document.querySelectorAll('#chart text.curve-name').forEach(function (t) {
            var s = own(t);
            if (s.indexOf('Спрос') < 0) return;
            found = s;
            var r = t.getBoundingClientRect();
            wide = (r.left >= box.left - 1 && r.right <= box.right + 1) ? 1 : 0;
          });
          return { whole: found === 'Спрос жителей города' ? 1 : 0,
                   dots: (found || '').indexOf(String.fromCharCode(8230)) >= 0 ? 1 : 0,
                   inside: wide, lines: found ? found.split(String.fromCharCode(10)).length : 0 };`,
    checks: [['имя целиком', 'whole', 1, 0], ['многоточия нет', 'dots', 0, 0],
             ['подпись внутри холста', 'inside', 1, 0], ['в одну строку', 'lines', 1, 0]],
  },
  {
    /* 20.08, пп. 4.6 и 4.7. СТРОКА ВВОДА: ОБРАЗЕЦ И НАСТРОЙКИ ПОЛЯ.
       Образец «Например: 100 − Q» уходил в MathLive целиком как формула, и
       двоеточие верстало́сь знаком отношения с отбивкой по обе стороны: на
       экране стояло «Например : 100 − Q». Проза обязана идти текстом.
       Там же — три настройки поля, переданные в конструктор, где MathLive их
       не читает: они молча не применялись и давали по предупреждению на поле. */
    name: 'Строка ввода: проза текстом, настройки поля применились',
    run: `var sample = placeholderTex('Например: 100 - Q');
          var mfs = [].slice.call(document.querySelectorAll('math-field'));
          return { fields: 1,
                   prose: sample.indexOf(String.fromCharCode(92) + 'text{Например:}') === 0 ? 1 : 0,
                   bare: /Например\s*:/.test(sample.split('}')[1] || '') ? 1 : 0,
                   smart: mfs.every(function (m) { return m.smartMode === false; }) ? 1 : 0,
                   fence: mfs.every(function (m) { return m.smartFence === true; }) ? 1 : 0,
                   paren: mfs.every(function (m) { return m.removeExtraneousParentheses === false; }) ? 1 : 0 };`,
    checks: [['образец разобран', 'fields', 1, 0],
             ['проза образца обёрнута текстом', 'prose', 1, 0],
             ['двоеточия вне текста не осталось', 'bare', 0, 0],
             ['smartMode применился', 'smart', 1, 0],
             ['smartFence применился', 'fence', 1, 0],
             ['removeExtraneousParentheses применился', 'paren', 1, 0]],
  },
  {
    /* 20.08, п. 4.8. KaTeX БОЛЬШЕ НЕ РУГАЕТСЯ.
       Два рода жалоб на каждый обход сцен: узкий неразрывный пробел U+202F
       (наш разделитель разрядов, которого в шрифтах KaTeX нет вовсе) и
       кириллица в математическом режиме. Второе не только шум: в математике
       слово набирается курсивным шрифтом переменных, то есть читается как
       произведение букв. Обе беды закрывает один общий вход katexInto. */
    name: 'KaTeX: узкий пробел и кириллица приведены к правилам',
    run: `var B = String.fromCharCode(92), NB = String.fromCharCode(8239);
          var thin = katexSafe('1' + NB + '250');
          var word = katexSafe('Безработица = 30');
          var keep = katexSafe(B + 'text{уже текст: Безработица}');
          var mix  = katexSafe('L_{' + B + 'text{спрос}} = 35');
          var errs = 0;
          Object.keys(SCENE_ROUTE).forEach(function (k) {
            resetSceneMemory(); pickScene(k); redrawAll();
            errs += document.querySelectorAll('.katex-error').length;
          });
          return { thin: thin.indexOf(NB) < 0 ? 1 : 0,
                   thinTex: thin === '1' + B + ',250' ? 1 : 0,
                   word: word.indexOf(B + 'text{Безработица}') === 0 ? 1 : 0,
                   keepOnce: keep.split(B + 'text{').length - 1,
                   mixOnce: mix.split(B + 'text{').length - 1,
                   errs: errs };`,
    checks: [['узкого пробела не осталось', 'thin', 1, 0],
             ['он стал тонким пробелом формулы', 'thinTex', 1, 0],
             ['слово обёрнуто текстом', 'word', 1, 0],
             ['готовый текст не оборачивается второй раз', 'keepOnce', 1, 0],
             ['индекс словом тоже не трогаем', 'mixOnce', 1, 0],
             ['красных формул на всех сценах', 'errs', 0, 0]],
  },

  /* --- Фаза 7: разгрузка перегруженных сюжетов (Б34) ------------------ */
  {
    /* Б34. Перетаскивание кривых мышью — главный интерактив калькулятора, и
       оно остаётся. Убираем его вместе с ползунками «Сдвиг кривых» ТОЧЕЧНО:
       в эластичности по кривым уже ездят две точки, в налогах — своя линия
       ставки. Считаем подвижные объекты на самом графике.

       ⚠️ ПРОВЕРКА ПЕРЕСЧИТАНА 19.08, А НЕ ОТКЛЮЧЕНА. Прежде она требовала,
       чтобы в «Спросе и предложении» кривые тянулись мышью. Решением владельца
       мышь там запрещена, а ползунки сдвига остались единственным способом
       двигать кривые — и это ровно то, что проверяется теперь: ползунков
       по-прежнему два (`sdShift`), а подвижных мышью объектов ноль.
       Здесь же держится урок фазы: «сцена не двигает кривые вовсе» и «кривые
       не тянутся мышью» — разные признаки. Пока они были одним, запрет мыши
       уносил с собой и ползунки.

       ⚠️ ПРОВЕРКА ПЕРЕСЧИТАНА ВТОРОЙ РАЗ, 20.08, И СНОВА НЕ ОТКЛЮЧЕНА.
       Владелец отменил «вариант Б» целиком: «на графике нельзя двигать функции
       графически мышкой». Кривые не тянутся НИГДЕ, поэтому в потолке цены и на
       рынке труда подвижных объектов стало не три, а один — сама линия
       вмешательства (потолок, МРОТ). Это и есть новое ожидание: манипулятор
       СЮЖЕТА остаётся подвижным, кривые — нет. В эластичности так и было: обе
       её подвижные точки — манипуляторы, а не кривые, и их по-прежнему две. */
    name: 'Б34 · Сдвиг кривых выключен точечно, а не везде',
    run: `var count = function (k) { resetSceneMemory(); pickScene(k); redrawAll();
            var n = 0;
            document.querySelectorAll('svg#chart *').forEach(function (el) {
              var cs = getComputedStyle(el);
              if (!/grab|move|ew-resize|ns-resize/.test(cs.cursor)) return;
              if (!el.getClientRects().length) return;
              n++;
            });
            return { grab: n, shift: pultCurveList().length }; };
          var e = count('elast'), t = count('tax'), ta = count('tax-adv');
          var sd = count('sd'), c = count('ceil'), l = count('labor');
          return { eGrab: e.grab, eShift: e.shift, tShift: t.shift, taShift: ta.shift,
                   sdShift: sd.shift, sdGrab: sd.grab, cGrab: c.grab, lGrab: l.grab };`,
    checks: [['эластичность: только две точки', 'eGrab', 2, 0],
             ['и ни одного ползунка сдвига', 'eShift', 0, 0],
             ['налог: ползунков сдвига нет', 'tShift', 0, 0],
             ['адвалорный: тоже нет', 'taShift', 0, 0],
             ['на обычном рынке сдвиг остался', 'sdShift', 2, 0],
             ['но мышью кривые не тянутся', 'sdGrab', 0, 0],
             ['в потолке подвижен только сам потолок', 'cGrab', 1, 0],
             ['на рынке труда — только МРОТ', 'lGrab', 1, 0]],
  },

  /* --- Фаза 10: экспорт от модели сцены (Б4, Б5, Б35) ----------------- */
  {
    /* Б35, Б4. Кривая, у которой есть выражение, обязана уйти в файл ФОРМУЛОЙ.
       Раньше формулами уходили только кривые из списка (STATE.curves), а
       сценовые (издержки, производство, заводы) — таблицами по шестьдесят
       точек, хотя их выражения выводятся из введённой человеком функции по
       определению: ATC = TC/Q, VC = TC − FC, MC = dTC/dQ (символьно).
       Б5. Кусок кривой уходит со своим отрезком построения. */
    name: 'Б4 · Кривые сцены уходят формулами, а не таблицами точек',
    run: `var f = function (k) {
            resetSceneMemory(); pickScene(k); redrawAll();
            var tex = buildTex('', '');
            var formulas = (tex.match(/\\\\addplot\\[[^\\]]*\\] *\\{/g) || []).length;
            var tables = (tex.match(/\\\\addplot\\[[^\\]]*\\] *coordinates \\{[^}]*\\}/g) || [])
              .filter(function (t) { return (t.match(/\\(/g) || []).length > 5; }).length;
            /* Считаем ОТРЕЗОК ПОСТРОЕНИЯ, а не ограничение по y: у каждого
               \\addplot есть и «domain=», и «restrict y to domain=», и без
               запятой перед словом в счёт попадали оба. */
            var domains = (tex.match(/, domain=[\\d.]+:[\\d.]+/g) || []).length;
            var notes = (tex.match(/выгружена точками/g) || []).length;
            return { formulas: formulas, tables: tables, domains: domains, notes: notes };
          };
          var c = f('costs'), pr = f('prod'), pl = f('plants');
          // Символьная производная должна получаться у обычной записи.
          var d = derivativeExpr('Q^3 - 6*Q^2 + 15*Q + 18', 'Q');
          var dv = d ? math.parse(d).compile().evaluate({ Q: 4 }) : NaN;
          return { cF: c.formulas, cT: c.tables, pF: pr.formulas, pT: pr.tables,
                   plF: pl.formulas, plDom: pl.domains, plNotes: pl.notes,
                   deriv: dv };`,
    // MC(4) = 3·16 − 48 + 15 = 15.
    checks: [['издержки: четыре кривые формулой', 'cF', 4, 0],
             ['и ни одной таблицей', 'cT', 0, 0],
             ['производство: TP, MP, AP формулой', 'pF', 3, 0],
             ['и ни одной таблицей', 'pT', 0, 0],
             ['заводы: TC₁ и TC₂ формулой', 'plF', 2, 0],
             ['со своими отрезками', 'plDom', 2, 0],
             ['а совокупная — с пояснением', 'plNotes', 1, 0],
             ['символьная производная верна', 'deriv', 15, 0.001]],
  },
  {
    /* Сессия 22.08. РАЗБОР ФОРМУЛЫ — ОДНА ДВЕРЬ, И ЧЕРЕЗ НЕЁ ПРОХОДИТ ВСЁ.
       Два класса дефектов разом. Первый: «100-ax» раскрывалось в «100-a*x»
       для поиска букв, но compilePpf разбирал СЫРУЮ строку и отвечал
       «Undefined symbol ax» — ползунок буквы заводился и не двигал ничего.
       Второй: запись из математического поля приходит на языке LaTeX, а
       раскрытие неявного умножения рубило её на буквы («\cdot» → «\c*d*o*t»),
       то есть разбор доламывал то, чего не понял.
       Слэш здесь собирается из кода символа: строка внутри шаблонного литерала
       .mjs разбирается ДВАЖДЫ, и посчитать слэши на глаз тут уже не удавалось. */
    name: 'Разбор · неявное умножение и LaTeX доходят до Math.js',
    run: `var B = String.fromCharCode(92);
          resetSceneMemory(); pickScene('ppf'); redrawAll();
          var ok = function (e) { return compilePpf(e).error ? 0 : 1; };
          // Сверка идёт числами (approx), поэтому отвечаем «ровно одна буква a».
          var onlyA = function (e) { return freeSymbols(e).join(',') === 'a' ? 1 : 0; };
          return {
            implicitOk:  ok('100-ax'),
            implicitLet: onlyA('100-ax'),
            cdotOk:      ok('100-a' + B + 'cdot x'),
            cdotLet:     onlyA('100-a' + B + 'cdot x'),
            fracOk:      ok(B + 'frac{100}{x}'),
            sqrtOk:      ok(B + 'sqrt{100-x}'),
            // Перевод обязан снять ВСЕ слэши: то, что дойдёт до Math.js.
            noSlash:     prepExpr('100-a' + B + 'cdot x').indexOf(B) < 0 ? 1 : 0,
            // Имя за слэшем не рубится на буквы даже без перевода.
            keepsCmd:    expandImplicitMul('1' + B + 'zzz x').indexOf('z*z*z') < 0 ? 1 : 0,
            // Значение считается верно, а не «просто разобралось».
            value:       (function () { var r = parsePpfEquation('y=100-2' + B + 'cdot x');
                                        return r.error ? NaN : r.f(10); })(),
            // Пустая строка — это не отказ разбора.
            emptyOk:     freeSymbols('').parseFailed ? 0 : 1,
            // А недописанная формула — отказ, и он теперь различим.
            brokenFlag:  freeSymbols('100-a*').parseFailed ? 1 : 0,
          };`,
    checks: [['«100-ax» разбирается', 'implicitOk', 1, 0],
             ['и найдена ровно буква a', 'implicitLet', 1, 0],
             ['«100-a\cdot x» разбирается', 'cdotOk', 1, 0],
             ['и найдена ровно буква a', 'cdotLet', 1, 0],
             ['\frac разбирается', 'fracOk', 1, 0],
             ['\sqrt разбирается', 'sqrtOk', 1, 0],
             ['до Math.js слэш не доезжает', 'noSlash', 1, 0],
             ['имя за слэшем не рубится', 'keepsCmd', 1, 0],
             ['y(10) при y=100−2·x', 'value', 80, 0.001],
             ['пустая строка — не отказ', 'emptyOk', 1, 0],
             ['недописанная — отказ виден', 'brokenFlag', 1, 0]],
  },
  {
    /* ⚠️ ВТОРОЙ ПУТЬ РАЗБОРА: СЫРАЯ СТРОКА ПРЯМО В `parsePpfEquation`.

       Эта проверка появилась потому, что её не было. Соседний случай
       («Разбор · неявное умножение и LaTeX доходят до Math.js») и живой обход
       41 сцены оба зеленели, пока `compilePpf` разбирал сырой текст в обход
       подготовки: через интерфейс сырой LaTeX до разбора не доезжает вовсе —
       математическое поле кладёт в спрятанный input уже переведённую запись.
       Дефект нашёл владелец прямым вызовом в консоли, а не прибор.

       Здесь строки подаются КАК ЕСТЬ, и проверяется вся цепочка до числа:
       разобралось · какой вид · сколько считает. Считаем в точке x = 5:
       у «y = 100 − a·x» при a = 1 это 95, при a = 10 это 50.

       ⚠️ Отдельная строка про букву БЕЗ ползунка. f(5) отдавал NaN (в JSON это
       null) при исправно разобранной формуле: пробный расчёт при разборе шёл
       через scopeFor, подставляющий единицу, а сам счёт — через paramScope,
       который знает только заведённые ползунки. Ползунок заводится ПОЗЖЕ, чем
       принимается формула, и в это окно кривая считалась в пустоту. */
    name: 'Разбор · сырая строка проходит parsePpfEquation до числа',
    run: `var B = String.fromCharCode(92);
          resetSceneMemory(); pickScene('ppf'); redrawAll();
          var was = STATE.params.a;
          var at5 = function (src, aVal) {
            if (aVal == null) delete STATE.params.a;
            else STATE.params.a = { value: aVal, min: -10, max: 10, step: 0.1 };
            var p = parsePpfEquation(src);
            if (p.error) return NaN;
            var v = p.f(5);
            return (typeof v === 'number' && isFinite(v)) ? v : NaN;
          };
          var kindOf = function (src) {
            var p = parsePpfEquation(src);
            return p.error ? 0 : (p.kind === 'explicit' ? 1 : 2);
          };
          var okc = function (src) { return compilePpf(src).error ? 0 : 1; };
          var out = {
            kImplicit: kindOf('y=100-ax'),
            kCdot:     kindOf('y=100-a' + B + 'cdot x'),
            kStar:     kindOf('y=100-a*x'),
            kFrac:     kindOf(B + 'frac{100}{x}'),
            cImplicit: okc('100-ax'),
            cCdot:     okc('100-a' + B + 'cdot x'),
            cFrac:     okc(B + 'frac{100}{x}'),
            vNoParam:  at5('y=100-ax', null),
            vA1:       at5('y=100-a' + B + 'cdot x', 1),
            vA10:      at5('y=100-ax', 10),
            vFrac:     at5(B + 'frac{100}{x}', null)
          };
          if (was) STATE.params.a = was; else delete STATE.params.a;
          return out;`,
    checks: [['«y=100-ax» — явная запись', 'kImplicit', 1, 0],
             ['«y=100-a\\cdot x» — явная запись', 'kCdot', 1, 0],
             ['«y=100-a*x» — явная запись', 'kStar', 1, 0],
             ['«\\frac{100}{x}» — явная запись', 'kFrac', 1, 0],
             ['compilePpf берёт «100-ax»', 'cImplicit', 1, 0],
             ['compilePpf берёт «100-a\\cdot x»', 'cCdot', 1, 0],
             ['compilePpf берёт «\\frac{100}{x}»', 'cFrac', 1, 0],
             ['f(5) без ползунка: буква = 1', 'vNoParam', 95, 0.001],
             ['f(5) при a=1', 'vA1', 95, 0.001],
             ['f(5) при a=10', 'vA10', 50, 0.001],
             ['f(5) у 100/x', 'vFrac', 20, 0.001]]
  },
  {
    /* Сессия 22.08. РЫЧАГ ДВИГАЕТ КРИВУЮ, А НЕ ПЛОСКОСТЬ.
       Правило 21.08 («окно идёт за формулой, а не за значением буквы») в
       «Построении КПВ» не работало: доводка подписи кривой просила следующий
       кадр обычной redrawAll, и та подгоняла оси. Окно проседало со «0…120»
       до «0…12», линия при этом занимала ТЕ ЖЕ пиксели. */
    name: 'КПВ · значение буквы не подбирает окно заново',
    /* ⚠️ ПРОВЕРКА ВЕДЁТ БУКВУ ШАЖКАМИ, КАК ВЕДЁТ РУКА, И ЖДЁТ КАДРОВ.

       Первая версия этой проверки прыгала с a = 1 сразу на 10 и читала окно
       синхронно. Она зеленела на СЛОМАННОМ коде — проверено откатом обеих
       правок, — то есть была бесполезна. Две причины разом:
         · окно ломала не сама перерисовка, а следующая за ней, которую просит
           доводка подписи кривой; синхронное чтение до неё не доживало;
         · большой скачок подпись не «ведёт», а переставляет разом («далеко»),
           и следующего кадра она тогда не просит вовсе — ломается именно
           плавное движение, то есть протяжка ручки.
       Поэтому ведём a шажками по 0,5 и отдаём между ними кадр. */
    run: `return (async function () {
            resetSceneMemory(); pickScene('ppf');
            document.getElementById('inp-ppf').value = 'y=100-a*x';
            document.getElementById('btn-ppf-apply').click();
            syncParams();
            var frame = function () { return new Promise(function (r) { requestAnimationFrame(r); }); };
            await frame(); await frame();
            var w0 = CONFIG.Qmax;
            var y0 = evalPpf(10);
            for (var v = 1.5; v <= 10.0001; v += 0.5) {
              STATE.params.a.value = Math.round(v * 100) / 100;
              redrawKeepingWindow();
              await frame();
            }
            await frame(); await frame();
            return { w0: w0, w1: CONFIG.Qmax, y0: y0, y1: evalPpf(10),
                     a: STATE.params.a.value };
          })();`,
    // a: 1 → 10. Окно остаётся, а сама кривая обязана поехать: y(10) 90 → 0.
    checks: [['окно до', 'w0', 120, 0.5],
             ['окно после протяжки — то же', 'w1', 120, 0.5],
             ['буква доехала до 10', 'a', 10, 0.001],
             ['y(10) при a=1', 'y0', 90, 0.001],
             ['y(10) при a=10', 'y1', 0, 0.001]],
  },

  /* ── Сессия 21.08: три дефекта вкладки «Графики» (три карточки Notion,
     разбор по исходникам + замер в живом браузере) ──────────────────────── */
  {
    /* «Безработица = 0» обрезалась левым краем в «Конкурентном рынке труда» при
       МРОТ выше кривой спроса: invCurve не находит корень, Qd оставался null,
       fmt(null) врал «0», sx(null) давал x="NaN". Проверяем связывающий случай
       (D(0)=100, W_min=114 — выше начала кривой спроса) и зеркальный низкий
       МРОТ — оба раза без NaN-координат и без подписей, обрезанных слева. */
    name: 'Труд · МРОТ выше кривой спроса ⇒ занятость 0, безработица честная, подписи без NaN и без обрезки',
    run: `setMode('labor');
          STATE.curves = [];
          addCurve('100 - L'); setRole(STATE.curves[0], 'demand');
          addCurve('L');       setRole(STATE.curves[1], 'supply');
          setLaborStruct('comp');
          STATE.laborMinOn = true; setLaborMin(114);
          var m = STATE.laborMin || {};
          var texts1 = Array.prototype.slice.call(document.querySelectorAll('#chart text'));
          var nanX1 = texts1.filter(function (t) { return !isFinite(parseFloat(t.getAttribute('x'))); }).length;
          var offLeft1 = texts1.filter(function (t) { return t.getBBox().x < 0; }).length;
          STATE.laborMinOn = true; setLaborMin(0.5);
          var texts2 = Array.prototype.slice.call(document.querySelectorAll('#chart text'));
          var nanX2 = texts2.filter(function (t) { return !isFinite(parseFloat(t.getAttribute('x'))); }).length;
          var offLeft2 = texts2.filter(function (t) { return t.getBBox().x < 0; }).length;
          return { emp: m.employment, unemp: m.unemployment,
                   nanX1: nanX1, offLeft1: offLeft1, nanX2: nanX2, offLeft2: offLeft2 };`,
    checks: [['занятость (МРОТ=114)', 'emp', 0, 0.5], ['безработица (МРОТ=114)', 'unemp', 114, 0.5],
             ['подписей x=NaN (МРОТ=114)', 'nanX1', 0, 0.1], ['подписей левее холста (МРОТ=114)', 'offLeft1', 0, 0.1],
             ['подписей x=NaN (МРОТ=0.5)', 'nanX2', 0, 0.1], ['подписей левее холста (МРОТ=0.5)', 'offLeft2', 0, 0.1]],
  },
  {
    /* Честный Qd=0/Qs=0 в laborMinCompetition — не единственный слой защиты:
       если где-то ещё координата дойдёт до haloText нечисловой, подпись не
       имеет права попасть на холст молча. Проверяем это НАПРЯМУЮ, минуя
       остальные слои — иначе тест выше не отличит рабочую защиту haloText
       от случайно неиспорченного пути (сцена с W_min=114 после починки Qd
       уже не производит NaN сама по себе, и порча только haloText осталась
       бы незамеченной). */
    name: 'haloText · нечисловая координата не рисуется и не возвращается',
    run: `loadScene('sd'); redrawAll();
          var g = svg.append('g');
          var before = g.node().childNodes.length;
          var ret = haloText(g, NaN, 50, 'проба', 'middle', 'hanging');
          var after = g.node().childNodes.length;
          var retNull = (ret === null) ? 1 : 0;
          var noAppend = (after === before) ? 1 : 0;
          g.remove();
          return { retNull: retNull, noAppend: noAppend };`,
    checks: [['возвращает null', 'retNull', 1, 0.1], ['ничего не рисует', 'noAppend', 1, 0.1]],
  },
  {
    /* Правка значения регулятора сцены выглядела как поле ввода на всю ширину
       панели: .param-eq-input растягивался (width:100%), рамку/фон давало
       более специфичное «#params-body .field input[type=number]:focus».
       Эталон — соседний параметр кривой (.param-eq вне .field), с ним не
       сравниваем напрямую, но проверяем те же числовые инварианты. */
    name: 'Регулятор сцены · правка значения — поле по содержимому, без рамки, без фона',
    run: `setMode('labor');
          STATE.curves = [];
          addCurve('100 - L'); setRole(STATE.curves[0], 'demand');
          addCurve('L');       setRole(STATE.curves[1], 'supply');
          setLaborStruct('comp');
          STATE.laborMinOn = true; setLaborMin(114);
          var field = document.getElementById('labmin-field');
          var eq = field.querySelector('.reg-eq');
          var eqWidth = eq.getBoundingClientRect().width;
          var panelWidth = document.getElementById('params-body').getBoundingClientRect().width;
          eq.click();
          var inp = field.querySelector('input.param-eq-input');
          var cs = getComputedStyle(inp);
          var wid = inp.getBoundingClientRect().width;
          var borderTop = parseFloat(cs.borderTopWidth);
          var bg = cs.backgroundColor;
          var bgFlag = (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') ? 1 : 0;
          var widFlag = (wid > 0 && wid <= 40) ? 1 : 0;
          var eqNarrowFlag = (eqWidth < panelWidth * 0.6) ? 1 : 0;
          inp.blur();
          return { wid: wid, widFlag: widFlag, borderTop: borderTop, bgFlag: bgFlag,
                   eqWidth: eqWidth, panelWidth: panelWidth, eqNarrowFlag: eqNarrowFlag };`,
    checks: [['ширина поля ≤ 40px (флаг)', 'widFlag', 1, 0.1], ['ширина поля, px (сырое)', 'wid', 20, 20],
             ['border-top = 0', 'borderTop', 0, 0.1], ['фон прозрачный (флаг)', 'bgFlag', 1, 0.1],
             ['строка .reg-eq заметно уже панели (флаг)', 'eqNarrowFlag', 1, 0.1],
             ['ширина .reg-eq, px (сырое)', 'eqWidth', 70, 70], ['ширина #params-body, px (сырое)', 'panelWidth', 260, 260]],
  },
  {
    /* «Равновесие𝐷 = 𝑆» без пробела: .section-title — flex-контейнер, и в нём
       текстовый узел перед span.tex теряет конечный пробел. */
    name: 'Заголовок раздела · зазор между текстом и формулой («Равновесие D = S»)',
    run: `loadScene('sd'); redrawAll();
          var t = document.getElementById('sec-eq').querySelector('.section-title');
          var textNode = Array.prototype.filter.call(t.childNodes, function (n) { return n.nodeType === 3; })[0];
          var texSpan = t.querySelector('.tex');
          var range = document.createRange();
          range.selectNodeContents(textNode);
          var tr = range.getBoundingClientRect();
          var sr = texSpan.getBoundingClientRect();
          var gap = sr.left - tr.right;
          var gapFlag = (gap > 2) ? 1 : 0;
          return { gap: gap, gapFlag: gapFlag };`,
    checks: [['зазор > 2px (флаг)', 'gapFlag', 1, 0.1], ['зазор, px (сырое)', 'gap', 4, 4]],
  },

  /* =====================================================================
     ВМЕШАТЕЛЬСТВО ГОСУДАРСТВА И ВНЕШНИЕ ЭФФЕКТЫ (ночная сессия 24.08).
     Одиннадцать проверок (а)–(л) из задания. Ручные расчёты выписаны рядом
     с каждой: тест сверяет движок с арифметикой, а не сам с собой.
     Общая модель везде одна: D = 100 − Q, S = Q, значит Q* = 50, P* = 50.
     ===================================================================== */
  {
    /* (а) Потоварный налог t = 20. S_после = Q + 20; 100 − Q = Q + 20 ⇒ Q₁ = 40.
       Pb = D(40) = 60, Ps = S(40) = 40, сбор = 20·40 = 800,
       DWL = ½·(50 − 40)·(60 − 40) = 100. */
    name: '(а) Потоварный налог t=20 ⇒ Q1=40, Pb=60, Ps=40, сбор=800, DWL=100',
    run: `pickScene('taxes'); setTaxForm('unit'); setTaxSide('seller'); setTax(20); redrawAll();
          var te = STATE.taxEq || {};
          return { Q1: te.Q, Pb: te.Pb, Ps: te.Ps, tx: STATE.tx, dwl: STATE.dwl };`,
    checks: [['Q1', 'Q1', 40, 0.3], ['Pb', 'Pb', 60, 0.3], ['Ps', 'Ps', 40, 0.3],
             ['сбор', 'tx', 800, 6], ['DWL', 'dwl', 100, 2]],
  },
  {
    /* (б) Две ПРОЦЕНТНЫЕ формы налога, обе дают ПОВОРОТ предложения, но базы
       у них разные — отсюда и разные точки.

       НДС τ = 20 % — доля от цены ПРОДАВЦА, начисляется сверх неё:
       S_после = 1,2·Q. 100 − Q = 1,2·Q ⇒ Q₁ = 100/2,2 = 45,4545.
       Pb = 54,5455, Ps = 45,4545, их отношение равно 1 + τ,
       сбор = (54,5455 − 45,4545)·45,4545 = 413,2231,
       DWL = ½·(50 − 45,4545)·9,0909 = 20,6612.

       АКЦИЗ τ = 20 % — доля от цены ПОКУПАТЕЛЯ: S_после = Q/0,8 = 1,25·Q.
       100 − Q = 1,25·Q ⇒ Q₁ = 100/2,25 = 44,4444. Pb = 55,5556, Ps = 44,4444,
       их отношение Ps/Pb равно 1 − τ = 0,8,
       сбор = τ·Pb·Q = 0,2·55,5556·44,4444 = 493,8272,
       DWL = ½·(50 − 44,4444)·11,1111 = 30,8642.

       ⚠️ Акциз ЗДЕСЬ И БЫЛ СЛОМАН: до 24.08 он проваливался в потоварную ветку
       и давал числа случая (а) — Q₁ = 40 при ставке «20 рублей». Этот случай
       ровно то и проверяет: у акциза своя точка, не совпадающая ни с (а),
       ни с НДС. */
    name: '(б) НДС τ=20% ⇒ Q1=45,4545; акциз τ=20% ⇒ Q1=44,4444 (свои точки, не потоварные)',
    run: `pickScene('taxes'); setTaxForm('vat'); setTax(20); redrawAll();
          var v = STATE.taxEq || {};
          var res = { vQ: v.Q, vPb: v.Pb, vPs: v.Ps, vRatio: v.Pb / v.Ps, vTx: STATE.tx, vDwl: STATE.dwl };
          pickScene('taxes'); setTaxForm('excise'); setTax(20); redrawAll();
          var e = STATE.taxEq || {};
          res.eQ = e.Q; res.ePb = e.Pb; res.ePs = e.Ps; res.eRatio = e.Ps / e.Pb;
          res.eTx = STATE.tx; res.eDwl = STATE.dwl;
          // Тождество: сбор по формуле таблицы обязан совпасть с (Pb − Ps)·Q.
          res.eIdent = Math.abs(0.2 * e.Pb * e.Q - STATE.tx);
          return res;`,
    checks: [['НДС Q1', 'vQ', 45.4545, 0.02], ['НДС Pb', 'vPb', 54.5455, 0.02],
             ['НДС Ps', 'vPs', 45.4545, 0.02], ['НДС Pb/Ps = 1+τ', 'vRatio', 1.2, 0.002],
             ['НДС сбор', 'vTx', 413.2231, 0.6], ['НДС DWL', 'vDwl', 20.6612, 0.3],
             ['акциз Q1', 'eQ', 44.4444, 0.02], ['акциз Pb', 'ePb', 55.5556, 0.02],
             ['акциз Ps', 'ePs', 44.4444, 0.02], ['акциз Ps/Pb = 1−τ', 'eRatio', 0.8, 0.002],
             ['акциз сбор', 'eTx', 493.8272, 0.6], ['акциз DWL', 'eDwl', 30.8642, 0.3],
             ['акциз: сбор = (Pb−Ps)·Q', 'eIdent', 0, 1e-6]],
  },
  {
    /* (в) Кто ФОРМАЛЬНО платит налог, экономику не меняет. Возвращаем сами
       разности: они обязаны быть нулями до последнего разряда, а не «примерно». */
    name: '(в) Плательщик налога не меняет ни Q1, ни цены, ни бремя, ни сбор',
    run: `pickScene('taxes'); setTaxForm('unit'); setTax(20);
          setTaxSide('seller'); redrawAll();
          var a = STATE.taxEq || {}, aB = STATE.incBuyer, aS = STATE.incSeller, aT = STATE.tx, aD = STATE.dwl;
          setTaxSide('buyer'); redrawAll();
          var b = STATE.taxEq || {};
          return { Q: a.Q, dQ: Math.abs(a.Q - b.Q), dPb: Math.abs(a.Pb - b.Pb), dPs: Math.abs(a.Ps - b.Ps),
                   dBuyer: Math.abs(aB - STATE.incBuyer), dSeller: Math.abs(aS - STATE.incSeller),
                   dTx: Math.abs(aT - STATE.tx), dDwl: Math.abs(aD - STATE.dwl) };`,
    checks: [['Q1 при продавце', 'Q', 40, 0.3], ['разница Q1', 'dQ', 0, 1e-9],
             ['разница Pb', 'dPb', 0, 1e-9], ['разница Ps', 'dPs', 0, 1e-9],
             ['разница бремени покупателя', 'dBuyer', 0, 1e-9],
             ['разница бремени продавца', 'dSeller', 0, 1e-9],
             ['разница сбора', 'dTx', 0, 1e-9], ['разница DWL', 'dDwl', 0, 1e-9]],
  },
  {
    /* (г) Потолок 30: Qd = 70, Qs = 30, дефицит 40, торгуется короткая сторона 30,
       DWL = ∫₃₀^50 (100 − 2q) dq = 2500 − 2100 = 400.
       Пол 70: Qs = 70, Qd = 30, избыток 40, та же торговля и тот же DWL.
       НЕсвязывающие случаи (потолок 70 и пол 30) рынку не мешают вовсе. */
    name: '(г) Потолок 30 и пол 70 ⇒ дефицит и избыток 40; несвязывающие не действуют',
    run: `var take = function (type, p) {
            resetSceneMemory(); pickScene('ceil'); setType(type); setPReg(p); redrawAll();
            var pc = STATE.pc || {};
            return { Qd: pc.Qd, Qs: pc.Qs, gap: pc.gap, dwl: pc.dwl, bind: pc.binding ? 1 : 0 };
          };
          var c = take('ceiling', 30), f = take('floor', 70);
          var cw = take('ceiling', 70), fl = take('floor', 30);
          return { cQd: c.Qd, cQs: c.Qs, cGap: c.gap, cDwl: c.dwl, cBind: c.bind,
                   fQs: f.Qs, fQd: f.Qd, fGap: f.gap, fDwl: f.dwl, fBind: f.bind,
                   wBind: cw.bind, lBind: fl.bind,
                   wGap: (cw.gap == null ? 0 : 1), lGap: (fl.gap == null ? 0 : 1) };`,
    checks: [['потолок Qd', 'cQd', 70, 0.3], ['потолок Qs', 'cQs', 30, 0.3],
             ['дефицит', 'cGap', 40, 0.5], ['потолок DWL', 'cDwl', 400, 4], ['потолок связывает', 'cBind', 1, 0],
             ['пол Qs', 'fQs', 70, 0.3], ['пол Qd', 'fQd', 30, 0.3],
             ['избыток', 'fGap', 40, 0.5], ['пол DWL', 'fDwl', 400, 4], ['пол связывает', 'fBind', 1, 0],
             ['потолок 70 не связывает', 'wBind', 0, 0], ['пол 30 не связывает', 'lBind', 0, 0],
             ['и дефицита не считает', 'wGap', 0, 0], ['и избытка не считает', 'lGap', 0, 0]],
  },
  {
    /* (д) Квота 40. Ниже цены S(40) = 40 продавцы этот объём не отдадут, выше
       цены D(40) = 60 покупатели его не выберут: коридор ровно [40; 60]. */
    name: '(д) Квота 40 ⇒ коридор возможных цен [40; 60]',
    run: `pickScene('quota'); redrawAll();
          var q = STATE.qt || {};
          return { Qq: q.Qq, lo: q.Plo, hi: q.Phi, bind: q.binding ? 1 : 0, active: STATE.quotaActive ? 1 : 0 };`,
    checks: [['объём квоты', 'Qq', 40, 1e-9], ['нижняя граница', 'lo', 40, 1e-6],
             ['верхняя граница', 'hi', 60, 1e-6], ['связывает', 'bind', 1, 0], ['коридор есть', 'active', 1, 0]],
  },
  {
    /* (е) ГЛАВНАЯ МЫСЛЬ СЮЖЕТА. Излишки перетекают, их сумма и потери стоят.
       CS + PS = ∫₀^40 (100 − 2q) dq = 2400 при любой цене внутри коридора,
       DWL = ∫₄₀^50 (100 − 2q) dq = 100. Цена в оба выражения не входит. */
    name: '(е) Квота 40, десять положений ползунка ⇒ CS+PS и DWL постоянны',
    run: `pickScene('quota');
          var sw = [], dwl = [], cs = [], ps = [], pr = [];
          for (var i = 0; i <= 9; i++) {
            setQuotaPos(i / 9);
            var q = STATE.qt || {};
            sw.push(q.sw); dwl.push(q.dwl); cs.push(q.cs); ps.push(q.ps); pr.push(q.P);
          }
          var spread = function (a) { var m = a[0], d = 0; a.forEach(function (v) { d = Math.max(d, Math.abs(v - m)); }); return d; };
          return { n: sw.length, swSpread: spread(sw), dwlSpread: spread(dwl),
                   sw0: sw[0], dwl0: dwl[0], pLo: pr[0], pHi: pr[9],
                   csDrop: cs[0] - cs[9], psRise: ps[9] - ps[0] };`,
    checks: [['положений ползунка', 'n', 10, 0],
             ['разброс CS+PS', 'swSpread', 0, 1e-9], ['разброс DWL', 'dwlSpread', 0, 1e-9],
             ['CS+PS', 'sw0', 2400, 1e-6], ['DWL', 'dwl0', 100, 1e-6],
             ['цена снизу', 'pLo', 40, 1e-6], ['цена сверху', 'pHi', 60, 1e-6],
             ['CS перетёк', 'csDrop', 800, 1e-6], ['PS принял', 'psRise', 800, 1e-6]],
  },
  {
    /* (ж) Квота 70 больше равновесного объёма 50 и потому не связывает:
       коридора нет, ограничение рынку не мешает. */
    name: '(ж) Квота 70 (выше равновесия) ⇒ коридора нет',
    run: `pickScene('quota'); setQuota(70); redrawAll();
          var q = STATE.qt || {};
          return { bind: q.binding ? 1 : 0, active: STATE.quotaActive ? 1 : 0,
                   hasP: (q.P == null ? 0 : 1), hasDwl: (q.dwl == null ? 0 : 1), eqQ: (STATE.eq || {}).Q };`,
    checks: [['не связывает', 'bind', 0, 0], ['коридора нет', 'active', 0, 0],
             ['цены внутри коридора нет', 'hasP', 0, 0], ['потерь не считается', 'hasDwl', 0, 0],
             ['рынок в равновесии', 'eqQ', 50, 0.3]],
  },
  {
    /* (з) Переключение между видами вмешательства не оставляет следов
       предыдущего. Снимок вида, полученного ПЕРЕХОДОМ, обязан совпасть со
       снимком того же вида, открытого с чистой сцены: закраски, подписи на
       графике, счёт фигур и видимые поля панели. Двенадцать переходов между
       четырьмя видами (налог, субсидия, фиксированная цена, квота). */
    name: '(з) Двенадцать переходов между видами вмешательства не оставляют следов',
    run: `var APPLY = {
            tax:     function(){ setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(20); },
            subsidy: function(){ setType('subsidy'); setTaxKind('unit'); setTax(20); },
            ceiling: function(){ setType('ceiling'); setPReg(30); },
            quota:   function(){ setType('quota'); setQuota(40); setQuotaPos(0.5); }
          };
          var snap = function () {
            var ch = document.getElementById('chart');
            var leg = [].map.call(ch.querySelectorAll('[data-legend]'), function (e) { return e.getAttribute('data-legend'); }).sort().join('|');
            var txt = [].map.call(ch.querySelectorAll('text'), function (e) { return (e.textContent || '').replace(/\\s+/g, ' ').trim(); })
                        .filter(Boolean).sort().join('|');
            var shp = ['line', 'circle', 'rect', 'path'].map(function (t) { return ch.querySelectorAll(t).length; }).join(',');
            var vis = ['tax-field', 'pc-field', 'quota-field', 'quota-price-field', 'taxkind-row', 'taxside-row']
                        .filter(function (id) { var e = document.getElementById(id); return e && e.offsetParent !== null; }).join(',');
            return leg + '#' + txt + '#' + shp + '#' + vis;
          };
          var kinds = ['tax', 'subsidy', 'ceiling', 'quota'], fresh = {};
          kinds.forEach(function (k) {
            resetSceneMemory(); pickScene('taxes'); APPLY[k](); redrawAll();
            fresh[k] = snap();
          });
          var pairs = 0, bad = 0;
          kinds.forEach(function (a) {
            kinds.forEach(function (b) {
              if (a === b) return;
              pairs++;
              resetSceneMemory(); pickScene('taxes'); APPLY[a](); redrawAll(); APPLY[b](); redrawAll();
              if (snap() !== fresh[b]) bad++;
            });
          });
          return { pairs: pairs, bad: bad };`,
    checks: [['переходов проверено', 'pairs', 12, 0], ['переходов со следами', 'bad', 0, 0]],
  },
  /* ═══════════════════════════════════════════════════════════════════
     ЧЕТЫРЕ ДЕФЕКТА С ПРИЁМКИ ВЛАДЕЛЬЦА 24.08 — постоянные проверки.
     Каждая проверена на зубастость: дефект временно возвращали и убеждались,
     что проверка краснеет (тексты провалов — в отчёте сессии).
     ═══════════════════════════════════════════════════════════════════ */
  {
    /* (а) Число перед буквой — это умножение. «100-2P» и «100-2*P» обязаны
       давать ПОБУКВЕННО одну и ту же кривую: ту же форму записи, тот же
       наклон, те же значения и то же равновесие. До правки первая запись
       уходила в форму P = f(Q) и рисовала горизонталь на 98 — молча. */
    name: 'Четыре дефекта (а) «100-2P» строит ту же кривую, что «100-2*P»',
    run: `var take = function (text) {
            resetSceneMemory(); pickScene('sd');
            var inp = document.getElementById('curve-expr-1');
            inp.value = text; inp.dispatchEvent(new Event('input', { bubbles: true }));
            redrawAll();
            var c = STATE.curves.filter(function (x) { return x.id === 1; })[0];
            return { form: c.srcForm, a: c.linear ? c.linear.a : NaN, b: c.linear ? c.linear.b : NaN,
                     v10: evalCurve(c, 10), v20: evalCurve(c, 20), v30: evalCurve(c, 30),
                     eqQ: STATE.eq ? STATE.eq.Q : NaN, eqP: STATE.eq ? STATE.eq.P : NaN };
          };
          var A = take('100-2P'), B = take('100-2*P');
          var diff = 0;
          Object.keys(B).forEach(function (k) { if (String(A[k]) !== String(B[k])) diff++; });
          return { diff: diff, formQP: (A.form === 'QP') ? 1 : 0,
                   a: A.a, b: A.b, v10: A.v10, v20: A.v20, v30: A.v30 };`,
    checks: [['расхождений между записями', 'diff', 0, 0],
             ['форма прочитана как Q(P)', 'formQP', 1, 0],
             ['наклон', 'a', -0.5, 0.001], ['свободный член', 'b', 50, 0.001],
             ['значение при Q=10', 'v10', 45, 0.001],
             ['значение при Q=20', 'v20', 40, 0.001],
             ['значение при Q=30', 'v30', 35, 0.001]],
  },
  {
    /* (б) Раскрытие неявного умножения не имеет права портить: имена с цифрой
       ПОСЛЕ буквы, экономические обозначения, научную запись и вызовы функций.
       Научная запись — главная ловушка: «e» это и число Эйлера, и часть
       записи числа, и первая версия правки давала «1e5» → «1*e5». */
    name: 'Четыре дефекта (б) раскрытие не портит Q_1, MC, 1e5, sqrt(4)',
    run: `var same = { 'Q_1': 'Q_1', 'x1': 'x1', 'P2': 'P2', 'MC': 'MC', 'ATC': 'ATC',
                       'DWL': 'DWL', '1e5': '1e5', '2e-3': '2e-3', '1.5e+10': '1.5e+10',
                       'sqrt(4)': 'sqrt(4)', 'log(10)': 'log(10)', 'x^2': 'x^2' };
          var broken = 0;
          Object.keys(same).forEach(function (k) { if (expandImplicitMul(k) !== same[k]) broken++; });
          // И значения: испорченная запись считается по-другому, а не «почти так же».
          var ev = function (e, sc) { try { return math.evaluate(prepExpr(e), sc || {}); } catch (x) { return NaN; } };
          return { broken: broken, n: Object.keys(same).length,
                   sci1: ev('1e5'), sci2: ev('2e-3'), root: ev('sqrt(4)'),
                   name1: ev('Q_1', { Q_1: 7 }), name2: ev('x1', { x1: 5 }),
                   // а вот эти обязаны РАСКРЫТЬСЯ
                   mul1: (expandImplicitMul('2P') === '2*P') ? 1 : 0,
                   mul2: (expandImplicitMul('0.5Q') === '0.5*Q') ? 1 : 0,
                   mul3: (expandImplicitMul('2(100-Q)') === '2*(100-Q)') ? 1 : 0,
                   mul4: (expandImplicitMul('bx') === 'b*x') ? 1 : 0 };`,
    checks: [['испорчено записей', 'broken', 0, 0], ['записей проверено', 'n', 12, 0],
             ['1e5', 'sci1', 100000, 0], ['2e-3', 'sci2', 0.002, 1e-12],
             ['sqrt(4)', 'root', 2, 0], ['Q_1 при Q_1=7', 'name1', 7, 0],
             ['x1 при x1=5', 'name2', 5, 0],
             ['2P раскрыто', 'mul1', 1, 0], ['0.5Q раскрыто', 'mul2', 1, 0],
             ['2(100-Q) раскрыто', 'mul3', 1, 0], ['bx раскрыто', 'mul4', 1, 0]],
  },
  {
    /* (в) Сдвиг — это смещение ОТ набранной формулы. Переписали формулу —
       точка отсчёта новая, значит сдвиг ноль, а ручка ровно посередине
       дорожки. До правки после набора «100-2*P» стояло «Сдвиг D = −50»
       и ручка упиралась в левый край. */
    name: 'Четыре дефекта (в) правка формулы обнуляет сдвиг и центрирует ручку',
    run: `var chip = function () {
            var ch = document.querySelector('#params-curves .pchip[data-cid="1"]');
            if (!ch) return { shift: NaN, pos: NaN };
            var sl = ch.querySelector('input[type=range]');
            var mn = parseFloat(sl.min), mx = parseFloat(sl.max), v = parseFloat(sl.value);
            var c = STATE.curves.filter(function (x) { return x.id === 1; })[0];
            return { shift: c.linear.b - (c.shiftBase == null ? c.linear.b : c.shiftBase),
                     pos: (mx > mn) ? (v - mn) / (mx - mn) * 100 : NaN, slider: v };
          };
          var edit = function (text) {
            var inp = document.getElementById('curve-expr-1');
            inp.value = text; inp.dispatchEvent(new Event('input', { bubbles: true }));
            redrawAll(); updatePult();
          };
          resetSceneMemory(); pickScene('sd'); redrawAll();
          var start = chip();
          // Сдвигаем на +20 ползунком — тем же путём, что и человек.
          var sl = document.querySelector('#params-curves .pchip[data-cid="1"] input[type=range]');
          sl.value = '20'; sl.dispatchEvent(new Event('input', { bubbles: true }));
          var shifted = chip();
          // Переписываем формулу: свободный член меняется со 120 на 50.
          edit('100-2*P');
          var after = chip();
          var c = STATE.curves.filter(function (x) { return x.id === 1; })[0];
          return { startShift: start.shift, startPos: start.pos,
                   shiftedShift: shifted.shift, shiftedPos: shifted.pos,
                   afterShift: after.shift, afterPos: after.pos, afterSlider: after.slider,
                   afterB: c.linear.b };`,
    checks: [['сдвиг на старте', 'startShift', 0, 0], ['ручка на старте, %', 'startPos', 50, 0.01],
             ['сдвиг после протяжки', 'shiftedShift', 20, 0.01],
             ['ручка после протяжки, %', 'shiftedPos', 70, 0.01],
             ['сдвиг после правки формулы', 'afterShift', 0, 0],
             ['ручка после правки, %', 'afterPos', 50, 0.01],
             ['значение ползунка после правки', 'afterSlider', 0, 0],
             ['свободный член новой формулы', 'afterB', 50, 0.01]],
  },
  {
    /* (г) Кусочная запись — СПИСОК условий, а не матрёшка. Одна фигурная
       скобка на всю функцию, по строке на кусок, и ни одной бесконечности.
       Проверяем ту запись, которую поле показывает ПОСЛЕ пересборки строки
       кривой: именно там жил дефект (сразу после «Поставить в поле» запись
       была правильной и до первой пересборки). */
    name: 'Четыре дефекта (г) кусочная — список условий, без вложенности и ∞',
    /* ⚠️ СТРОКИ СТАВИМ ПОСЛЕ ОТКРЫТИЯ ОКНА, А НЕ ДО. Конструктор больше ничего
       не помнит со страницы: при открытии он собирает строки заново из того,
       что стоит В ПОЛЕ (иначе куски текли между полями и моделями). Значит и
       здесь порядок как у человека — сперва открыть, потом набрать. */
    run: `var build = function (rows, n) {
            resetSceneMemory(); pickScene('sd'); redrawAll();
            var inp = document.getElementById('curve-expr-1');
            openPiecewise(inp, 'Q');
            PW.rows = rows.slice(); PW.n = n; renderPw();
            document.getElementById('pw-apply').click();
            // То, что поле возьмёт при пересборке строки кривой.
            return mathToLatexField(document.getElementById('curve-expr-1').value);
          };
          var count = function (t, sub) { return t.split(sub).length - 1; };
          var two = build([{ f: '100 - Q', a: '0', b: '40' }, { f: '80 - 0.5*Q', a: '40', b: '' }], 2);
          var three = build([{ f: '100 - Q', a: '0', b: '20' }, { f: '90 - 0.5*Q', a: '20', b: '50' },
                             { f: '65', a: '50', b: '' }], 3);
          var one = build([{ f: '100 - Q', a: '0', b: '40' }], 1);
          return { cases2: count(two, '\\\\begin{cases}'), rows2: count(two, '\\\\\\\\') + 1, inf2: count(two, '\\\\infty'),
                   cases3: count(three, '\\\\begin{cases}'), rows3: count(three, '\\\\\\\\') + 1, inf3: count(three, '\\\\infty'),
                   cases1: count(one, '\\\\begin{cases}'), rows1: count(one, '\\\\\\\\') + 1, inf1: count(one, '\\\\infty'),
                   otherwise: count(two, 'otherwise') + count(three, 'otherwise') + count(one, 'otherwise') };`,
    checks: [['фигурных скобок при двух кусках', 'cases2', 1, 0],
             ['строк списка при двух кусках', 'rows2', 2, 0],
             ['бесконечностей при двух кусках', 'inf2', 0, 0],
             ['фигурных скобок при трёх кусках', 'cases3', 1, 0],
             ['строк списка при трёх кусках', 'rows3', 3, 0],
             ['бесконечностей при трёх кусках', 'inf3', 0, 0],
             ['фигурных скобок при одном куске', 'cases1', 1, 0],
             ['строк списка при одном куске', 'rows1', 1, 0],
             ['бесконечностей при одном куске', 'inf1', 0, 0],
             ['английских «otherwise» во всех трёх', 'otherwise', 0, 0]],
  },
  {
    /* (д) Вне условий функция НЕ ОПРЕДЕЛЕНА, а не равна бесконечности:
       движок обязан возвращать NaN, и такая точка на графике не рисуется.
       Проверяем ограниченный последний кусок — иначе он тянется до края. */
    name: 'Четыре дефекта (д) вне условий кусочной кривой нет',
    run: `resetSceneMemory(); pickScene('sd'); redrawAll();
          var inp = document.getElementById('curve-expr-1');
          openPiecewise(inp, 'Q');
          PW.rows = [{ f: '100 - Q', a: '0', b: '40' }, { f: '80 - 0.5*Q', a: '40', b: '80' }];
          PW.n = 2; renderPw();
          document.getElementById('pw-apply').click(); redrawAll();
          var c = STATE.curves.filter(function (x) { return x.id === 1; })[0];
          var def = function (q) { var v = evalCurve(c, q); return (v == null || isNaN(v)) ? 0 : 1; };
          return { inside0: def(0), inside20: def(20), inside50: def(50), inside79: def(79),
                   out80: def(80), out90: def(90), out200: def(200), outNeg: def(-10),
                   v20: evalCurve(c, 20), v50: evalCurve(c, 50) };`,
    checks: [['определена при Q=0', 'inside0', 1, 0], ['определена при Q=20', 'inside20', 1, 0],
             ['определена при Q=50', 'inside50', 1, 0], ['определена при Q=79', 'inside79', 1, 0],
             ['определена при Q=80 (вне)', 'out80', 0, 0],
             ['определена при Q=90 (вне)', 'out90', 0, 0],
             ['определена при Q=200 (вне)', 'out200', 0, 0],
             ['определена при Q=−10 (вне)', 'outNeg', 0, 0],
             ['значение при Q=20', 'v20', 80, 0.001], ['значение при Q=50', 'v50', 55, 0.001]],
  },
  {
    /* (е) При СВЯЗЫВАЮЩЕМ потолке равновесия нет. Табло обязано показывать
       цену потолка, величину спроса, величину предложения и дефицит — а не
       пересечение D и S, которого на этом рынке уже не происходит. */
    name: 'Четыре дефекта (е) потолок 30: в табло цена 30, Qd 70, Qs 30, дефицит 40',
    run: `resetSceneMemory(); pickScene('ceil'); setType('ceiling'); setPReg(30); redrawAll();
          /* ⚠️ ЧИТАЕМ ВИДИМУЮ ЧАСТЬ, А НЕ textContent. Число в табло набрано
             формулой, и у готового KaTeX textContent это тройка «MathML +
             исходная запись + видимый текст»: «30» читалось как «303030». */
          var nums = [].map.call(document.querySelectorAll('#info-eq .stat b'), function (e) {
            var t = e.querySelector('.katex') ? katexVisibleText(e) : (e.textContent || '');
            return parseFloat(String(t).replace(/\\u00a0|\\u2009|\\s/g, '').replace(/[^0-9.,-]/g, '').replace(',', '.'));
          });
          var title = (document.querySelector('#sec-eq .section-title') || {}).textContent || '';
          return { n: nums.length, price: nums[0], qd: nums[1], qs: nums[2], gap: nums[3], dwl: nums[4],
                   promisesEq: /D\\s*=\\s*S/.test(title) ? 1 : 0,
                   namesMarket: /Рынок при потолке/.test(title) ? 1 : 0,
                   // старое мёртвое «50 и 50» не должно стоять в первых двух строках
                   dead: (Math.abs(nums[0] - 50) < 0.01 && Math.abs(nums[1] - 50) < 0.01) ? 1 : 0 };`,
    checks: [['строк в табло', 'n', 5, 0], ['цена', 'price', 30, 0.01],
             ['Qd', 'qd', 70, 0.01], ['Qs', 'qs', 30, 0.01],
             ['дефицит', 'gap', 40, 0.01], ['DWL', 'dwl', 400, 0.5],
             ['заголовок всё ещё обещает D = S', 'promisesEq', 0, 0],
             ['заголовок называет рынок', 'namesMarket', 1, 0],
             ['мёртвое «50 и 50»', 'dead', 0, 0]],
  },
  {
    /* (ж) НЕсвязывающий потолок равновесия не отменяет: он выше равновесной
       цены, рынок расчищается сам, и табло обязано остаться прежним. Эта
       проверка страхует (е) от правки «показывать регулирование всегда». */
    name: 'Четыре дефекта (ж) потолок 70: обычное равновесие 50 и 50',
    run: `resetSceneMemory(); pickScene('ceil'); setType('ceiling'); setPReg(70); redrawAll();
          /* ⚠️ ЧИТАЕМ ВИДИМУЮ ЧАСТЬ, А НЕ textContent. Число в табло набрано
             формулой, и у готового KaTeX textContent это тройка «MathML +
             исходная запись + видимый текст»: «30» читалось как «303030». */
          var nums = [].map.call(document.querySelectorAll('#info-eq .stat b'), function (e) {
            var t = e.querySelector('.katex') ? katexVisibleText(e) : (e.textContent || '');
            return parseFloat(String(t).replace(/\\u00a0|\\u2009|\\s/g, '').replace(/[^0-9.,-]/g, '').replace(',', '.'));
          });
          var title = (document.querySelector('#sec-eq .section-title') || {}).textContent || '';
          return { n: nums.length, Q: nums[0], P: nums[1],
                   promisesEq: /D\\s*=\\s*S/.test(title) ? 1 : 0,
                   binding: (STATE.pc && STATE.pc.binding) ? 1 : 0 };`,
    checks: [['строк в табло', 'n', 2, 0], ['Q*', 'Q', 50, 0.01], ['P*', 'P', 50, 0.01],
             ['заголовок обещает D = S', 'promisesEq', 1, 0],
             ['потолок связывает', 'binding', 0, 0]],
  },
  /* ═══════════════════════════════════════════════════════════════════
     ДЛИННАЯ НОЧНАЯ СЕССИЯ 24.08, БЛОКИ II-IV — постоянные проверки.
     Каждая проверена на зубастость: дефект временно возвращали и убеждались,
     что проверка краснеет (тексты провалов — в отчёте сессии).
     ═══════════════════════════════════════════════════════════════════ */
  {
    /* (а) и (б). Горизонтальное сложение: суммарные кривые ломаются там, где
       очередная группа входит в торговлю или выходит из неё. Учебный набор
       D₁ 100−Q, D₂ 60−Q, S₁ Q, S₂ Q+20 даёт излом спроса в (40; 60),
       излом предложения в (20; 20) и равновесие (70; 45). */
    name: 'Сложение (а)(б) изломы суммарных кривых и равновесие',
    run: `resetSceneMemory(); pickScene('sdsum'); redrawAll();
          var D = STATE.D, S = STATE.S;
          var pts = keyTargets();
          var near = function (x, y) {
            return pts.filter(function (p) { return Math.abs(p.x - x) < 0.6 && Math.abs(p.y - y) < 0.6; }).length;
          };
          return { Dat20: evalCurve(D, 20), Dat40: evalCurve(D, 40), Dat70: evalCurve(D, 70),
                   Dat160: evalCurve(D, 160),
                   Sat10: evalCurve(S, 10), Sat20: evalCurve(S, 20), Sat70: evalCurve(S, 70),
                   eqQ: STATE.eq.Q, eqP: STATE.eq.P,
                   kinkD: near(40, 60), kinkS: near(20, 20), eqPt: near(70, 45),
                   groups: STATE.curves.filter(function (c) { return c.sumGroup && c.kind !== 'sum'; }).length,
                   sums: STATE.curves.filter(function (c) { return c.kind === 'sum'; }).length };`,
    checks: [['спрос при Q=20', 'Dat20', 80, 1e-6], ['спрос в изломе Q=40', 'Dat40', 60, 1e-6],
             ['спрос при Q=70', 'Dat70', 45, 1e-6], ['спрос при Q=160', 'Dat160', 0, 1e-6],
             ['предложение при Q=10', 'Sat10', 10, 1e-6],
             ['предложение в изломе Q=20', 'Sat20', 20, 1e-6],
             ['предложение при Q=70', 'Sat70', 45, 1e-6],
             ['равновесие Q*', 'eqQ', 70, 1e-4], ['равновесие P*', 'eqP', 45, 1e-4],
             ['точка (40; 60) в ключевых', 'kinkD', 1, 0],
             ['точка (20; 20) в ключевых', 'kinkS', 1, 0],
             ['точка (70; 45) в ключевых', 'eqPt', 1, 0],
             ['групп в списке', 'groups', 4, 0], ['суммарных кривых', 'sums', 2, 0]],
  },
  {
    /* (в) и (г). Излишек каждой группы считается по ЕЁ кривой, а сумма обязана
       совпасть с площадью под СУММАРНОЙ кривой. Расхождение здесь означает
       ошибку сложения, а не округления, поэтому допуск жёсткий. */
    name: 'Сложение (в)(г) излишки по группам и сходимость двух путей',
    run: `resetSceneMemory(); pickScene('sdsum'); redrawAll();
          var st = sumGroupStats();
          return { d1q: st.D[0].q, d2q: st.D[1].q, qD: st.qD,
                   s1q: st.S[0].q, s2q: st.S[1].q, qS: st.qS,
                   cs1: st.D[0].surplus, cs2: st.D[1].surplus, csGroups: st.csGroups,
                   ps1: st.S[0].surplus, ps2: st.S[1].surplus, psGroups: st.psGroups,
                   csWhole: st.csWhole, psWhole: st.psWhole,
                   csGap: st.csGap, psGap: st.psGap };`,
    checks: [['D₁ берёт', 'd1q', 55, 1e-6], ['D₂ берёт', 'd2q', 15, 1e-6], ['вместе D', 'qD', 70, 1e-6],
             ['S₁ даёт', 's1q', 45, 1e-6], ['S₂ даёт', 's2q', 25, 1e-6], ['вместе S', 'qS', 70, 1e-6],
             ['излишек D₁', 'cs1', 1512.5, 1e-6], ['излишек D₂', 'cs2', 112.5, 1e-6],
             ['излишки вместе', 'csGroups', 1625, 1e-6],
             ['излишек S₁', 'ps1', 1012.5, 1e-6], ['излишек S₂', 'ps2', 312.5, 1e-6],
             ['излишки продавцов вместе', 'psGroups', 1325, 1e-6],
             ['площадь под суммарным спросом', 'csWhole', 1625, 1e-6],
             ['площадь под суммарным предложением', 'psWhole', 1325, 1e-6],
             ['расхождение двух путей CS', 'csGap', 0, 1e-6],
             ['расхождение двух путей PS', 'psGap', 0, 1e-6]],
  },
  {
    /* (д) Группа с ОТРИЦАТЕЛЬНЫМ количеством в сумму не входит: при цене выше
       своей запретительной покупатель просто не покупает. Именно это и создаёт
       излом. Проверяем прямо: при цене 70 вторая группа спроса (60 − Q) не
       торгует, и суммарный спрос равен ПЕРВОЙ группе, а не их сумме. */
    name: 'Сложение (д) группа с отрицательным количеством в сумму не входит',
    run: `resetSceneMemory(); pickScene('sdsum'); redrawAll();
          var gD = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
          var gS = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
          var q = function (c, P) { return sumGroupQty(c, P); };
          return {
            // Цена 70: вторая группа спроса вне рынка, первая берёт 30.
            d1at70: q(gD[0], 70), d2at70: q(gD[1], 70), sumD70: q(gD[0], 70) + q(gD[1], 70),
            curveAt30: invCurve(STATE.D, 70),
            // Цена 10: вторая группа предложения вне рынка, первая даёт 10.
            s1at10: q(gS[0], 10), s2at10: q(gS[1], 10),
            curveSat10: invCurve(STATE.S, 10),
            // Цена 45: торгуют все четверо.
            d1at45: q(gD[0], 45), d2at45: q(gD[1], 45), s1at45: q(gS[0], 45), s2at45: q(gS[1], 45) };`,
    checks: [['D₁ при цене 70', 'd1at70', 30, 1e-6],
             ['D₂ при цене 70 (вне рынка)', 'd2at70', 0, 0],
             ['суммарный спрос при цене 70', 'curveAt30', 30, 1e-3],
             ['S₁ при цене 10', 's1at10', 10, 1e-6],
             ['S₂ при цене 10 (вне рынка)', 's2at10', 0, 0],
             ['суммарное предложение при цене 10', 'curveSat10', 10, 1e-3],
             ['D₁ при цене 45', 'd1at45', 55, 1e-6], ['D₂ при цене 45', 'd2at45', 15, 1e-6],
             ['S₁ при цене 45', 's1at45', 45, 1e-6], ['S₂ при цене 45', 's2at45', 25, 1e-6]],
  },
  {
    /* (е) Кусочная в поле, которое общий обзор считал сломанным. Обзор мерил
       стыком за пределами самой кривой; со стыком внутри запись принимается и
       рисуется. Здесь — «Денежный рынок», формула написана по ставке i. */
    name: 'Сложение (е) кусочная в поле «Денежного рынка» принимается и рисуется',
    run: `return (async function () {
          var w = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
          resetSceneMemory(); pickScene('money'); await w(400); redrawAll();
          var shot = function () { var n = 0, len = 0, s = 0;
            document.querySelectorAll('#chart path').forEach(function (p) {
              var d = p.getAttribute('d') || ''; if (!d) return; n++; len += d.length;
              (d.match(/-?\\d+(?:\\.\\d+)?/g) || []).forEach(function (x) { s += +x; }); });
            return { n: n, len: len, s: Math.round(s * 100) / 100 }; };
          var before = shot();
          var f = document.getElementById('ma-md');
          f.value = '(i < 20) ? (200 - 4*i) : ((200 - 4*20) - 0.7*(i - 20))';
          ['input', 'change'].forEach(function (t) { f.dispatchEvent(new Event(t, { bubbles: true })); });
          f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
          await w(400); redrawAll();
          var after = shot();
          /* Мало проверить, что картинка сменилась: сцена могла отказать и
             перерисоваться прежней кривой. Спрашиваем саму модель — приняла ли
             она запись и не показывает ли отказ. */
          var err = [].slice.call(document.querySelectorAll('.error'))
            .filter(function (e) { return e.getClientRects().length; })
            .map(function (e) { return (e.textContent || '').trim(); })
            .filter(Boolean).join(' / ');
          var res = STATE.macroRes || {};
          return { accepted: (f.value || '').indexOf('?') >= 0 ? 1 : 0,
                   changed: (before.n !== after.n || before.len !== after.len
                             || Math.abs(before.s - after.s) > 1e-6) ? 1 : 0,
                   modelOk: (res.kind === 'money' && !err) ? 1 : 0,
                   paths: after.n };
          })();`,
    checks: [['запись принята полем', 'accepted', 1, 0], ['картинка изменилась', 'changed', 1, 0],
             ['модель приняла запись, отказа нет', 'modelOk', 1, 0],
             ['путей на холсте', 'paths', 3, 2]],
  },
  {
    /* ⚠️ ПЕРВАЯ ЧЕТВЕРТЬ (а). РАВНОВЕСИЕ НЕ ЗАВИСИТ ОТ ГРАНИЦ КАДРА.
       Дефект 24.08: findEquilibrium без явной границы сканировал отрезок до
       CONFIG.Qmax — правого края ВИДИМОГО окна. Один и тот же рынок на
       стартовом масштабе писал «кривые не пересекаются», а после отдаления
       показывал Q* = 128. Здесь один набор формул меряется на ТРЁХ масштабах:
       стартовом, отдалённом и приближённом. Числа обязаны совпасть. */
    name: 'Первая четверть (а) равновесие одно и то же на трёх масштабах',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 3); sumSetCount('S', 2);
          var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
          var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
          ['100-Q', '60-Q', '40-Q'].forEach(function (e, i) { updateCurveExpr(gd[i], e); });
          ['Q-100', 'Q+20'].forEach(function (e, i) { updateCurveExpr(gs[i], e); });
          redrawAll();
          var startQ = STATE.eq ? STATE.eq.Q : NaN, startP = STATE.eq ? STATE.eq.P : NaN;
          var startMax = CONFIG.Qmax;
          zoomStep(1.6); zoomStep(1.6); zoomStep(1.6); redrawAll();
          var farQ = STATE.eq ? STATE.eq.Q : NaN, farP = STATE.eq ? STATE.eq.P : NaN;
          var farMax = CONFIG.Qmax;
          zoomStep(1 / 1.6); zoomStep(1 / 1.6); zoomStep(1 / 1.6); zoomStep(1 / 1.6); redrawAll();
          var nearQ = STATE.eq ? STATE.eq.Q : NaN, nearP = STATE.eq ? STATE.eq.P : NaN;
          var nearMax = CONFIG.Qmax;
          return { startQ: startQ, startP: startP, farQ: farQ, farP: farP,
                   nearQ: nearQ, nearP: nearP,
                   grew: (farMax > startMax * 1.5) ? 1 : 0,
                   shrank: (nearMax < startMax) ? 1 : 0 };`,
    checks: [['Q* на стартовом масштабе', 'startQ', 128, 1e-3],
             ['P* на стартовом масштабе', 'startP', 24, 1e-3],
             ['Q* после отдаления', 'farQ', 128, 1e-3],
             ['P* после отдаления', 'farP', 24, 1e-3],
             ['Q* после приближения', 'nearQ', 128, 1e-3],
             ['P* после приближения', 'nearP', 24, 1e-3],
             ['окно и вправду отдалилось', 'grew', 1, 0],
             ['окно и вправду приблизилось', 'shrank', 1, 0]],
  },
  {
    /* ⚠️ ПЕРВАЯ ЧЕТВЕРТЬ (б). ИЗЛИШКИ НЕ УХОДЯТ НИЖЕ ОСИ Q.
       Дефект 24.08: у предложения Q − 100 обратная функция при Q < 100
       отрицательна, и интеграл излишка продавца уходил в отрицательные цены —
       PS первой группы выходил 7 688 вместо 2 688, ровно на треугольник под
       осью. Запись суммарной кривой при этом начиналась с Q = 100, на отрезке
       0…100 функции не было вовсе, и PS по суммарной давал NaN.
       Допуск жёсткий: расхождение здесь — ошибка правила, а не округления. */
    name: 'Первая четверть (б) излишки считаются только над осью Q',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 3); sumSetCount('S', 2);
          var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
          var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
          ['100-Q', '60-Q', '40-Q'].forEach(function (e, i) { updateCurveExpr(gd[i], e); });
          ['Q-100', 'Q+20'].forEach(function (e, i) { updateCurveExpr(gs[i], e); });
          redrawAll();
          var st = sumGroupStats();
          var box = document.getElementById('info-sum');
          return { ps1: st.S[0].surplus, ps2: st.S[1].surplus, psGroups: st.psGroups,
                   psWhole: st.psWhole, psGap: st.psGap,
                   cs1: st.D[0].surplus, cs2: st.D[1].surplus, cs3: st.D[2].surplus,
                   csGroups: st.csGroups, csWhole: st.csWhole, csGap: st.csGap,
                   sw: st.csGroups + st.psGroups,
                   warn: (box && box.querySelector('.warn')) ? 1 : 0,
                   zeroAt50: evalCurve(STATE.S, 50) };`,
    checks: [['излишек S₁', 'ps1', 2688, 1e-6], ['излишек S₂', 'ps2', 8, 1e-6],
             ['излишки продавцов вместе', 'psGroups', 2696, 1e-6],
             ['площадь под суммарным предложением', 'psWhole', 2696, 1e-6],
             ['расхождение двух путей PS', 'psGap', 0, 1e-6],
             ['излишек D₁', 'cs1', 2888, 1e-6], ['излишек D₂', 'cs2', 648, 1e-6],
             ['излишек D₃', 'cs3', 128, 1e-6],
             ['излишки покупателей вместе', 'csGroups', 3664, 1e-6],
             ['площадь под суммарным спросом', 'csWhole', 3664, 1e-6],
             ['расхождение двух путей CS', 'csGap', 0, 1e-6],
             ['общественное благосостояние', 'sw', 6360, 1e-6],
             ['предупреждения о расхождении нет', 'warn', 0, 0],
             ['суммарное предложение при Q=50 равно нулю', 'zeroAt50', 0, 1e-9]],
  },
  {
    /* ⚠️ ПЕРВАЯ ЧЕТВЕРТЬ (в). КРИВАЯ НЕ РИСУЕТСЯ НИЖЕ ОСИ Q.
       Дефект 24.08: curvePoints обрезал область по количеству, но по цене не
       обрезал вовсе, и в пути спроса 100 − Q при окне до Q = 200 лежало 200
       точек из 401 с отрицательной ценой, до P = −100. Прямоугольный clip-path
       прятал их, пока окно начиналось в нуле, но в самом пути они оставались и
       уходили в полосу попадания мыши, в ключевые точки и в выгрузку.
       Читаем НАРИСОВАННЫЙ путь и переводим пиксели обратно шкалами. */
    name: 'Первая четверть (в) в пути кривой нет точек с P < 0',
    run: `resetSceneMemory(); pickScene('sd');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
          document.getElementById('inp-qmax').value = '200';
          document.getElementById('inp-pmax').value = '200';
          applyViewBounds(); redrawAll();
           var below = 0, maxQ = -1e9, minQ = 1e9, pAtMin = NaN, n = 0;
           document.querySelectorAll('#chart path[data-curve]').forEach(function (el) {
             var id = +el.getAttribute('data-curve');
             var cur = STATE.curves.find(function (c) { return c.id === id; });
             if (!cur || cur.role !== 'demand') return;
             String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
               var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
               if (!m) return;
               n++;
               var q = sx.invert(+m[1]), p = sy.invert(+m[2]);
               if (p < -1e-6) below++;
               if (q > maxQ) maxQ = q;
               if (q < minQ) { minQ = q; pAtMin = p; }
             });
           });
           return { below: below, maxQ: maxQ, minQ: minQ, pAtMin: pAtMin, drawn: (n >= 2 ? 1 : 0) };`,
    /* ⚠️ ПРОВЕРЯЕМ ПОЛНОТУ ЛИНИИ, А НЕ ГУСТОТУ СЕТКИ.
       Здесь стояло «точек в пути 201 ± 3». Это была не проверка правила, а
       отпечаток тогдашней реализации: путь строился по сетке из 400 отрезков,
       и половина узлов приходилась на первую четверть. Прямая, проведённая
       по своим двум концам, это ТА ЖЕ линия (25.08, построение по узлам
       излома), но узлов в ней два, и проверка краснела на верной кривой.
       Правило же в том, что линия покрывает участок ЦЕЛИКОМ и не заходит под
       ось: поэтому теперь названы оба конца — начало (0; 100) и обрыв у
       Q = 100, — а от числа точек требуется только «их не меньше двух». */
    checks: [['точек с P < 0 в пути спроса', 'below', 0, 0],
             ['путь начинается у Q = 0', 'minQ', 0, 0.51],
             ['в начале пути цена 100', 'pAtMin', 100, 0.51],
             ['путь обрывается у Q = 100', 'maxQ', 100, 0.51],
             ['путь вообще нарисован', 'drawn', 1, 0]],
  },
  {
    /* ⚠️ ПЕРВАЯ ЧЕТВЕРТЬ (г). ПЕРЕСЕЧЕНИЕ ВНЕ ЧЕТВЕРТИ НАЗВАНО, НО НЕ РАВНОВЕСИЕ.
       Олимпиадная ловушка: у Qd = 100 − P и Qs = −200 + 0,5·P пересечение
       лежит в (−100; 200). Ученик видит правдоподобную цену и заканчивает
       решать. Калькулятор обязан назвать числа в разборе — и НЕ считать вокруг
       них ничего: ни излишков, ни равновесия. */
    name: 'Первая четверть (г) пересечение вне четверти названо, но не равновесие',
    run: `resetSceneMemory(); pickScene('sd');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-P');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), '-200+0.5*P');
          redrawAll();
          var ex = document.getElementById('ex-body');
          var txt = '';
          if (ex) { var cl = ex.cloneNode(true);
            cl.querySelectorAll('.katex-mathml, annotation').forEach(function (x) { x.remove(); });
            txt = cl.textContent; }
          var areas = document.getElementById('info-areas');
          return { eqNull: STATE.eq === null ? 1 : 0,
                   offQ: STATE.offEq ? STATE.offEq.Q : NaN,
                   offP: STATE.offEq ? STATE.offEq.P : NaN,
                   has200: /200/.test(txt) ? 1 : 0,
                   has100: /100/.test(txt) ? 1 : 0,
                   noStar: /Q\\s*\\*|P\\s*\\*/.test(txt) ? 0 : 1,
                   areasEmpty: (areas && areas.textContent.trim() === '') ? 1 : 0,
                   csNull: (STATE.cs == null) ? 1 : 0,
                   dashed: document.querySelectorAll('[data-offquad]').length };`,
    checks: [['равновесия нет', 'eqNull', 1, 0],
             ['пересечение Q', 'offQ', -100, 1e-3],
             ['пересечение P', 'offP', 200, 1e-3],
             ['в разборе есть число 200', 'has200', 1, 0],
             ['в разборе есть число 100', 'has100', 1, 0],
             ['обозначений Q* и P* в разборе нет', 'noStar', 1, 0],
             ['блок «Излишки» пуст', 'areasEmpty', 1, 0],
             ['излишки не посчитаны', 'csNull', 1, 0],
             ['пунктир к точке нарисован', 'dashed', 2, 0]],
  },
  {
    /* ⚠️ ПЕРВАЯ ЧЕТВЕРТЬ (д). ПРЕДЕЛЬНАЯ КРИВАЯ — ИСКЛЮЧЕНИЕ.
       MR продолжается вниз до Q-перехвата породившей её кривой: при спросе
       P = 100 − Q это Q = 100, где MR = −100. Продолжение обязано отличаться
       от основной линии видом — толщиной и прозрачностью, а не штрихом: MR
       и так штриховая. */
    name: 'Первая четверть (д) предельная кривая продолжается ниже оси',
    run: `resetSceneMemory(); pickScene('mono');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
          var mc = STATE.curves.find(function (c) { return c.role === 'mc' || c.role === 'supply'; });
          if (mc) updateCurveExpr(mc, '20');
          redrawAll();
          var tails = document.querySelectorAll('#chart [data-marginal-tail]');
          var maxQ = -1e9, minP = 1e9, w = 0, op = 1;
          tails.forEach(function (el) {
            w = parseFloat(el.getAttribute('stroke-width'));
            op = parseFloat(el.getAttribute('opacity'));
            String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
              var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
              if (!m) return;
              var q = sx.invert(+m[1]), p = sy.invert(+m[2]);
              if (q > maxQ) maxQ = q;
              if (p < minP) minP = p;
            });
          });
          var m = STATE.mono || {};
          return { n: tails.length, maxQ: maxQ, minP: minP, w: w, op: op,
                   Qm: m.Qm, Pm: m.Pm, Qc: m.Qc };`,
    checks: [['продолжений MR на холсте', 'n', 1, 0],
             ['край продолжения по Q', 'maxQ', 100, 0.6],
             ['самая нижняя точка по P', 'minP', -100, 1.5],
             ['продолжение тоньше основной линии', 'w', 1.1, 0.001],
             ['продолжение полупрозрачное', 'op', 0.45, 0.001],
             ['монопольный выпуск не сдвинулся', 'Qm', 40, 1e-3],
             ['монопольная цена не сдвинулась', 'Pm', 60, 1e-3],
             ['конкурентный выпуск не сдвинулся', 'Qc', 80, 1e-3]],
  },
  {
    /* ⚠️ ПЕРВАЯ ЧЕТВЕРТЬ (е). ЗАПИСЬ СУММАРНОЙ КРИВОЙ НЕ ЕДЕТ С МАСШТАБОМ.
       sumLinearRecord строил участки по ценам до CONFIG.Pmax, и границы
       участков в «Объяснении модели» менялись вместе с кадром: «Q <= 180» на
       стартовом окне и «Q <= 300» после отдаления. А по этой записи кривая и
       считается, поэтому вместе с ней ехала вся арифметика излишков.
       Сравниваем строки буквально, а не числа. */
    name: 'Первая четверть (е) запись суммарной кривой одна на всех масштабах',
    run: `resetSceneMemory(); pickScene('sdsum'); redrawAll();
          /* ⚠️ ЗАПИСЬ ПЕРЕСОБИРАЕМ ЗАНОВО НА КАЖДОМ МАСШТАБЕ.
             Кэш пересборки держит первую собранную запись и отдаёт её дальше
             не глядя — и это правильно ровно потому, что от кадра она не
             зависит. Но проверять надо само СВОЙСТВО, а не кэш: иначе верни
             зависимость от CONFIG.Pmax, и случай останется зелёным, потому
             что кэш подсунет прежнюю строку. Сбрасываем подпись руками. */
          var rec = function () {
            STATE._sumSig = null; sumRebuild();
            var d = STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'D'; });
            var s = STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'S'; });
            return String(d ? d.expr : '') + ' ## ' + String(s ? s.expr : '');
          };
          var a = rec();
          zoomStep(1.6); redrawAll(); var b = rec();
          zoomStep(1 / 1.6); zoomStep(1 / 1.6); redrawAll(); var c = rec();
          /* ⚠️ ОДНОГО СРАВНЕНИЯ ТРЁХ МАСШТАБОВ МАЛО. Кэш пересборки заведён
             ровно под то, что запись от кадра не зависит: верни зависимость,
             и кэш просто отдаст СТАРУЮ запись — три строки совпадут, а сама
             запись будет неверной. Поэтому рядом стоит точный текст.
             ⚠️ У СПРОСА конец 160 — настоящий: при P = 0 все группы
             исчерпаны. У ПРЕДЛОЖЕНИЯ правого края НЕТ вовсе (приёмка 31.08):
             до неё там стояло 180 из служебного потолка цены, и это было
             свойством подпорки, а не рынка. Ни то, ни другое число не берётся
             у границ окна — ровно это здесь и стережём. */
          var wantD = '(Q >= 0 and Q < 40) ? 100 - Q : ((Q >= 40 and Q <= 160) ? 80 - 0.5*Q : NaN)';
          var wantS = '(Q >= 0 and Q < 20) ? Q : ((Q >= 20) ? 0.5*Q + 10 : NaN)';
          return { sameAB: (a === b) ? 1 : 0, sameBC: (b === c) ? 1 : 0,
                   notEmpty: (a.length > 20) ? 1 : 0,
                   textD: (a.split(' ## ')[0] === wantD) ? 1 : 0,
                   textS: (a.split(' ## ')[1] === wantS) ? 1 : 0 };`,
    checks: [['запись после отдаления та же', 'sameAB', 1, 0],
             ['запись после приближения та же', 'sameBC', 1, 0],
             ['запись вообще собралась', 'notEmpty', 1, 0],
             ['текст записи спроса тот, что ждём', 'textD', 1, 0],
             ['текст записи предложения тот, что ждём', 'textS', 1, 0]],
  },
  /* =====================================================================
     ПРОЦЕНТНЫЕ НАЛОГИ И СУБСИДИИ (сессия 24.08, ветка feat/calc2-pct-tax).
     Четыре процентные формы описаны одной таблицей PCT_FORMS. Числа взяты
     из учебника Бахарева (глава «Налоги и субсидии») и посчитаны руками
     в комментарии к каждому случаю: тест сверяет движок с арифметикой.
     ===================================================================== */
  {
    /* (проц-а) ТЕОРЕМА ЭКВИВАЛЕНТНОСТИ. D = 120 − Q, S = Q, Q* = 60, P* = 60.
       Три разные формы, подобранные так, чтобы дать ОДНУ И ТУ ЖЕ точку:
         потоварный t = 40   ⇒ S+40 = Q+40;  120−Q = Q+40  ⇒ Q = 40;
         акциз     τ = 50 %  ⇒ S/(1−0,5) = 2Q; 120−Q = 2Q  ⇒ Q = 40;
         НДС       τ = 100 % ⇒ S·(1+1)   = 2Q; 120−Q = 2Q  ⇒ Q = 40.
       Всюду Pd = 80, Ps = 40, сбор 1600, DWL = ∫₄₀^₆₀(120−2q)dq = 400.

       ⚠️ ЭТОТ СЛУЧАЙ И ЛОВИТ СТАРЫЙ ДЕФЕКТ. До 24.08 акциз проваливался
       в потоварную ветку и при «50» сдвигал кривую на 50 рублей: точка
       уезжала в (35; 85/35), и три точки переставали совпадать. Сравниваем
       не только с арифметикой, но и попарно между формами — так дефект
       виден даже если ошибутся все три одинаково. */
    name: '(проц-а) Эквивалентность: потоварный 40, акциз 50 %, НДС 100 % — одна точка',
    run: `var snap = function (form, rate) {
            resetSceneMemory(); pickScene('taxes');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '120-Q');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
            setType('tax'); setTaxForm(form); setTax(rate); redrawAll();
            var te = STATE.taxEq || {};
            return { Q: te.Q, Pd: te.Pb, Ps: te.Ps, tx: STATE.tx, dwl: STATE.dwl };
          };
          var u = snap('unit', 40), e = snap('excise', 50), v = snap('vat', 100);
          var d = function (a, b) { return Math.max(Math.abs(a.Q - b.Q), Math.abs(a.Pd - b.Pd),
                                                    Math.abs(a.Ps - b.Ps), Math.abs(a.tx - b.tx)); };
          return { uQ: u.Q, uPd: u.Pd, uPs: u.Ps, uTx: u.tx, uDwl: u.dwl,
                   eQ: e.Q, ePd: e.Pd, ePs: e.Ps, eTx: e.tx, eDwl: e.dwl,
                   vQ: v.Q, vPd: v.Pd, vPs: v.Ps, vTx: v.tx, vDwl: v.dwl,
                   dUE: d(u, e), dUV: d(u, v),
                   // Тождество столбца «Деньги» таблицы PCT_FORMS.
                   identE: Math.abs(0.5 * e.Pd * e.Q - e.tx),
                   identV: Math.abs(1.0 * v.Ps * v.Q - v.tx) };`,
    checks: [['потоварный Q1', 'uQ', 40, 1e-6], ['потоварный Pd', 'uPd', 80, 1e-6],
             ['потоварный Ps', 'uPs', 40, 1e-6], ['потоварный сбор', 'uTx', 1600, 1e-4],
             ['потоварный DWL', 'uDwl', 400, 0.5],
             ['акциз Q1', 'eQ', 40, 1e-6], ['акциз Pd', 'ePd', 80, 1e-6],
             ['акциз Ps', 'ePs', 40, 1e-6], ['акциз сбор', 'eTx', 1600, 1e-4],
             ['акциз DWL', 'eDwl', 400, 0.5],
             ['НДС Q1', 'vQ', 40, 1e-6], ['НДС Pd', 'vPd', 80, 1e-6],
             ['НДС Ps', 'vPs', 40, 1e-6], ['НДС сбор', 'vTx', 1600, 1e-4],
             ['НДС DWL', 'vDwl', 400, 0.5],
             ['потоварный и акциз — одна точка', 'dUE', 0, 1e-6],
             ['потоварный и НДС — одна точка', 'dUV', 0, 1e-6],
             ['акциз: сбор = τ·Pd·Q', 'identE', 0, 1e-6],
             ['НДС: сбор = τ·Ps·Q', 'identV', 0, 1e-6]],
  },
  {
    /* (проц-б) ДВЕ ПРОЦЕНТНЫЕ СУБСИДИИ. D = 120 − Q, S = Q, ставка 50 %.
       От цены ПОКУПАТЕЛЯ: S/(1+0,5) = (2/3)Q; 120−Q = (2/3)Q ⇒ Q = 72,
         Pd = 48, Ps = 72, расход = 0,5·48·72 = 1728,
         DWL = ∫₆₀^₇₂(2q−120)dq = 144.
       От цены ПРОДАВЦА: S·(1−0,5) = 0,5Q; 120−Q = 0,5Q ⇒ Q = 80,
         Pd = 40, Ps = 80, расход = 0,5·80·80 = 3200,
         DWL = ∫₆₀^₈₀(2q−120)dq = 400.
       Расход выводится со знаком минус, как у потоварной.

       ⚠️ ДВЕ ФОРМЫ ОБЯЗАНЫ РАЗОЙТИСЬ. До 24.08 процентная субсидия была одна
       (и равнялась нынешней «от цены покупателя»), а вторая кнопка попадала
       в потоварную ветку. Проверяем не только числа, но и то, что точки
       РАЗНЫЕ: иначе правка «обе кнопки ведут в одну форму» осталась бы
       зелёной по каждому числу в отдельности. */
    name: '(проц-б) Субсидии 50 %: от цены покупателя Q=72, от цены продавца Q=80',
    run: `var snap = function (form) {
            resetSceneMemory(); pickScene('taxes');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '120-Q');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
            setType('subsidy'); setTaxForm(form); setTax(50); redrawAll();
            var te = STATE.taxEq || {};
            return { Q: te.Q, Pd: te.Pb, Ps: te.Ps, tx: STATE.tx,
                     budget: STATE.budget, dwl: STATE.dwl, kind: STATE.taxKind };
          };
          var b = snap('subbuyer'), l = snap('subseller');
          return { bQ: b.Q, bPd: b.Pd, bPs: b.Ps, bMoney: b.tx, bBudget: b.budget, bDwl: b.dwl,
                   lQ: l.Q, lPd: l.Pd, lPs: l.Ps, lMoney: l.tx, lBudget: l.budget, lDwl: l.dwl,
                   bAdv: (b.kind === 'advalorem') ? 1 : 0, lAdv: (l.kind === 'advalorem') ? 1 : 0,
                   apart: Math.abs(b.Q - l.Q),
                   identB: Math.abs(0.5 * b.Pd * b.Q - b.tx),
                   identL: Math.abs(0.5 * l.Ps * l.Q - l.tx) };`,
    checks: [['от Pd: поворот, а не сдвиг', 'bAdv', 1, 0],
             ['от Pd: Q1', 'bQ', 72, 1e-6], ['от Pd: Pd', 'bPd', 48, 1e-6],
             ['от Pd: Ps', 'bPs', 72, 1e-6], ['от Pd: расход', 'bMoney', 1728, 1e-4],
             ['от Pd: бюджет со знаком', 'bBudget', -1728, 1e-4], ['от Pd: DWL', 'bDwl', 144, 0.5],
             ['от Pd: расход = τ·Pd·Q', 'identB', 0, 1e-6],
             ['от Ps: поворот, а не сдвиг', 'lAdv', 1, 0],
             ['от Ps: Q1', 'lQ', 80, 1e-6], ['от Ps: Pd', 'lPd', 40, 1e-6],
             ['от Ps: Ps', 'lPs', 80, 1e-6], ['от Ps: расход', 'lMoney', 3200, 1e-4],
             ['от Ps: бюджет со знаком', 'lBudget', -3200, 1e-4], ['от Ps: DWL', 'lDwl', 400, 0.5],
             ['от Ps: расход = τ·Ps·Q', 'identL', 0, 1e-6],
             ['две формы дают РАЗНЫЕ точки', 'apart', 8, 1e-6]],
  },
  {
    /* (проц-в) СТАВКА ОБНУЛЯЕТСЯ ПРИ СМЕНЕ ВИДА (решение владельца), и рублёвой
       записи у процентных форм не остаётся нигде. Проходим цепочку
       потоварный 40 → акциз → НДС → потоварный и смотрим ставку после каждого
       шага, а заодно букву, единицу и предел ползунка.

       Пределы: у форм с делителем (1 − τ) верхняя граница строго меньше ста
       (99), у остальных процентных — 200, у потоварной — масштаб цены. */
    name: '(проц-в) Смена вида обнуляет ставку; у процентных форм буква τ и знак процента',
    run: `resetSceneMemory(); pickScene('taxes');
          setType('tax'); setTaxForm('unit'); setTax(40); redrawAll();
          var read = function () {
            var rl = document.getElementById('rate-letter');
            var ru = document.getElementById('rate-unit');
            var sl = document.getElementById('tax-slider');
            var inp = document.getElementById('tax-input');
            var eq = document.querySelector('#tax-field .reg-eq');
            var pult = '';
            if (eq) { var c = eq.cloneNode(true);
                      c.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
                      pult = c.textContent; }
            return { rate: STATE.tax, letter: rl ? rl.textContent.trim() : '',
                     unit: ru ? ru.textContent.trim() : '', max: parseFloat(sl ? sl.max : '0'),
                     field: parseFloat(inp ? inp.value : '-1'), pult: pult };
          };
          var a = read();
          setTaxForm('excise'); var b = read();
          setTaxForm('vat');    var c = read();
          setTaxForm('unit');   var d = read();
          return { r0: a.rate, r1: b.rate, r2: c.rate, r3: d.rate,
                   f1: b.field, f2: c.field, f3: d.field,
                   tauB: (b.letter === 'τ' && b.unit === '%') ? 1 : 0,
                   tauC: (c.letter === 'τ' && c.unit === '%') ? 1 : 0,
                   tUnit: (d.letter === 't' && d.unit === '') ? 1 : 0,
                   maxE: b.max, maxV: c.max,
                   pultPctB: /%/.test(b.pult) ? 1 : 0,
                   pultRubD: (d.pult && !/%/.test(d.pult)) ? 1 : 0 };`,
    checks: [['ставка до смены', 'r0', 40, 1e-9],
             ['после перехода на акциз', 'r1', 0, 1e-9],
             ['после перехода на НДС', 'r2', 0, 1e-9],
             ['после возврата к потоварному', 'r3', 0, 1e-9],
             ['поле ввода на акцизе', 'f1', 0, 1e-9],
             ['поле ввода на НДС', 'f2', 0, 1e-9],
             ['поле ввода на потоварном', 'f3', 0, 1e-9],
             ['акциз: буква τ и знак процента', 'tauB', 1, 0],
             ['НДС: буква τ и знак процента', 'tauC', 1, 0],
             ['потоварный: буква t без единицы', 'tUnit', 1, 0],
             ['предел акциза строго меньше ста', 'maxE', 99, 1e-9],
             ['предел НДС без верхней границы формы', 'maxV', 200, 1e-9],
             ['в ленте регуляторов у акциза есть процент', 'pultPctB', 1, 0],
             ['в ленте регуляторов у потоварного процента нет', 'pultRubD', 1, 0]],
  },
  {
    /* (проц-г) ЦЕНТР ПОВОРОТА. D = 120 − Q, S = 0,5Q + 30, акциз 25 %:
       S/(1−0,25) = (2/3)Q + 40; 120−Q = (2/3)Q+40 ⇒ Q = 48, Pd = 72,
       Ps = S(48) = 54 = 0,75·72, сбор = 0,25·72·48 = 864,
       Q₀ = 60, DWL = ∫₄₈^₆₀(90 − 1,5q)dq = 108.
       Обе кривые предложения обращаются в ноль при Q = −60 — это и есть центр.

       Контрпример в том же случае: у S = Q центр лежит в начале координат,
       и продолжения быть не должно. Без него правка «рисовать всегда»
       осталась бы зелёной. */
    name: '(проц-г) Центр поворота: два пунктира приходят в Q=−60; у S=Q продолжений нет',
    run: `var setup = function (sExpr, rate) {
            resetSceneMemory(); pickScene('taxes');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '120-Q');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), sExpr);
            setType('tax'); setTaxForm('excise'); setTax(rate); redrawAll();
          };
          var starts = function () {
            var out = [];
            document.querySelectorAll('#chart [data-pivot="1"], #chart [data-pivot="2"]').forEach(function (el) {
              var m = String(el.getAttribute('d') || '').match(/^M\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
              if (m) out.push([sx.invert(+m[1]), sy.invert(+m[2])]);
            });
            return out;
          };
          setup('0.5*Q+30', 25);
          /* ⚠️ Числа снимаем СРАЗУ: второй setup ниже перезапишет STATE.tx
             и STATE.dwl, и в отчёт уехали бы числа контрпримера. */
          var te = STATE.taxEq || {}, tx1 = STATE.tx, dwl1 = STATE.dwl;
          var piv = taxPivotPoint(), a = starts();
          setup('Q', 50);
          var noPiv = taxPivotPoint(), b = starts();
          return { Q: te.Q, Pd: te.Pb, Ps: te.Ps, tx: tx1, dwl: dwl1,
                   pivQ: piv ? piv.Q : NaN, pivP: piv ? piv.P : NaN,
                   n: a.length,
                   worstQ: a.length ? Math.max.apply(null, a.map(function (p) { return Math.abs(p[0] + 60); })) : 99,
                   worstP: a.length ? Math.max.apply(null, a.map(function (p) { return Math.abs(p[1]); })) : 99,
                   noPiv: (noPiv === null) ? 1 : 0, nNo: b.length };`,
    checks: [['Q1', 'Q', 48, 1e-6], ['Pd', 'Pd', 72, 1e-6], ['Ps', 'Ps', 54, 1e-6],
             ['сбор', 'tx', 864, 1e-4], ['DWL', 'dwl', 108, 0.5],
             ['центр поворота по Q', 'pivQ', -60, 1e-6],
             ['центр поворота по P', 'pivP', 0, 1e-9],
             ['продолжений на холсте', 'n', 2, 0],
             ['оба приходят в Q = −60', 'worstQ', 0, 0.2],
             ['оба приходят в P = 0', 'worstP', 0, 0.2],
             ['у S = Q центра не показываем', 'noPiv', 1, 0],
             ['и продолжений тоже нет', 'nNo', 0, 0]],
  },
  {
    /* (проц-д) ПРАВИЛО ПЕРВОЙ ЧЕТВЕРТИ ПРИ СНЯТОЙ ГАЛОЧКЕ (решение владельца).
       Экономическая сцена: сняли галочку — оси раздвинулись в минус, сетка на
       месте, но кривая ниже оси Q не появилась. «Математика» — не экономика:
       там парабола по-прежнему строится в отрицательных значениях.

       ⚠️ ДВЕ ПОЛОВИНЫ ОДНОГО СЛУЧАЯ, И ВТОРАЯ ВАЖНЕЕ. Правку «резать всегда и
       везде» первая половина пропустила бы: она сделала бы ровно то, чего
       здесь ждут. Ловит её вторая — число точек параболы ниже оси x. */
    name: '(проц-д) Снятая галочка: у экономики нет P < 0, у «Математики» отрицательные остаются',
    run: `resetSceneMemory(); pickScene('sd');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
          document.getElementById('inp-qmax').value = '200';
          document.getElementById('inp-pmax').value = '200';
          applyViewBounds(); redrawAll();
          var below = function () {
            var n = 0;
            document.querySelectorAll('#chart path[data-curve]').forEach(function (el) {
              String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
                var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
                if (m && sy.invert(+m[2]) < -1e-6) n++;
              });
            });
            return n;
          };
          var onQuad = below();
          setFirstQuad(false); redrawAll();
          var offQuad = below(), qmin = CONFIG.Qmin, pmin = CONFIG.Pmin;
          var grid = document.querySelectorAll('#chart .grid line, #chart [data-grid] line').length;
          var eq = STATE.eq || {}, cs = STATE.cs, ps = STATE.ps;
          /* Вторая половина: «Математика» правилу не подчиняется.
             ⚠️ Сюжет задаём ЯВНО. Соседние случаи оставляют STATE.mathSub своим
             («ограничение», «min/max»), и там общее поле f(x) не показывается
             вовсе — параболы на холсте не оказывается, а случай краснеет не по
             делу. Берём сюжет с касательной: у него f(x) есть и рисуется. */
          setMode('math'); setMathSub('tangent');
          STATE.mathFormula = 'x^2-4';
          var inp = document.getElementById('inp-mathf');
          if (inp) { inp.value = 'x^2-4'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
          setMathWindow(-6, 6, -6, 6); redrawAll();
          var ms = mainScales(), best = null;
          /* ⚠️ Без префикса «#chart»: кривую «Математики» рисует mathLine
             безымянным path, и ищется она не селектором, а по невязке
             с самой формулой — так случай не зависит от разметки. */
          Array.prototype.forEach.call(document.querySelectorAll('path'), function (el) {
            var pts = [];
            String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
              var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
              if (m) pts.push([ms.mx.invert(+m[1]), ms.my.invert(+m[2])]);
            });
            if (pts.length < 50) return;
            var err = 0;
            pts.forEach(function (p) { err += Math.abs(p[1] - (p[0] * p[0] - 4)); });
            err /= pts.length;
            if (!best || err < best.err) best = { err: err, pts: pts };
          });
          var mathBelow = best ? best.pts.filter(function (p) { return p[1] < -1e-6; }).length : -1;
          return { onQuad: onQuad, offQuad: offQuad, qmin: qmin, pmin: pmin,
                   grid: (grid > 0) ? 1 : 0, Q: eq.Q, P: eq.P, cs: cs, ps: ps,
                   mathBelow: mathBelow, mathErr: best ? best.err : 99 };`,
    checks: [['с галочкой точек с P < 0', 'onQuad', 0, 0],
             ['БЕЗ галочки точек с P < 0', 'offQuad', 0, 0],
             ['оси раздвинулись по Q', 'qmin', -50, 1e-6],
             ['оси раздвинулись по P', 'pmin', -50, 1e-6],
             ['сетка нарисована', 'grid', 1, 0],
             ['Q* не изменилось', 'Q', 50, 1e-6], ['P* не изменилось', 'P', 50, 1e-6],
             ['CS не изменился', 'cs', 1250, 1e-4], ['PS не изменился', 'ps', 1250, 1e-4],
             ['парабола найдена (невязка с x²−4)', 'mathErr', 0, 1e-3],
             ['в «Математике» точек с y < 0', 'mathBelow', 79, 0]],
  },
  {
    /* (ж) КТВ по кусочной КПВ. У ВОГНУТОЙ кусочной альтернативная стоимость
       растёт, и при мировой цене между наклонами кусков оптимум ровно в изломе.
       Куски: Y = 100 − 0,5X при X < 40 и Y = 160 − 2X при X ≥ 40, стык (40; 80).
       Ценность выпуска при цене 1: весь X — 80, весь Y — 100, излом — 120.
       Вторая половина проверки страхует от правки «всегда брать середину»:
       у ВЫПУКЛОЙ кусочной верный ответ — угол. */
    name: 'КТВ (ж) по кусочной КПВ: касание липнет к излому, у выпуклой — угол',
    run: `var build = function (formula, price) {
            resetSceneMemory(); pickScene('trade');
            var f = document.getElementById('inp-ppft');
            f.value = formula;
            ['input', 'change'].forEach(function (t) { f.dispatchEvent(new Event(t, { bubbles: true })); });
            var p = document.getElementById('inp-ppft-price');
            p.value = String(price); p.dispatchEvent(new Event('change', { bubbles: true }));
            document.getElementById('btn-ppft-apply').click();
            redrawAll();
            var d = STATE.ppfTradeData || {};
            return { xp: d.xp, yp: d.yp, xint: d.xint, yint: d.yint, regime: d.regime };
          };
          var a = build('(X >= 0 and X < 40) ? 100 - 0.5*X : (X >= 40 ? 160 - 2*X : NaN)', 1);
          var b = build('(X >= 0 and X < 40) ? 100 - X : (X >= 40 ? 80 - 0.5*X : NaN)', 0.75);
          var c = build('100 - X', 2);
          return { aXp: a.xp, aYp: a.yp, aXint: a.xint, aYint: a.yint,
                   aInner: /касание/.test(a.regime || '') ? 1 : 0,
                   bXp: b.xp, bYp: b.yp, bCorner: /специализация на X/.test(b.regime || '') ? 1 : 0,
                   cXp: c.xp, cCorner: /специализация на X/.test(c.regime || '') ? 1 : 0 };`,
    checks: [['вогнутая: производство X', 'aXp', 40, 1e-3],
             ['вогнутая: производство Y', 'aYp', 80, 1e-3],
             ['вогнутая: предел X', 'aXint', 120, 1e-3],
             ['вогнутая: предел Y', 'aYint', 120, 1e-3],
             ['вогнутая: режим «касание»', 'aInner', 1, 0],
             ['выпуклая: производство X (угол)', 'bXp', 160, 1e-3],
             ['выпуклая: производство Y', 'bYp', 0, 1e-3],
             ['выпуклая: режим «специализация»', 'bCorner', 1, 0],
             ['прямая КПВ: угол не сломан', 'cXp', 100, 1e-3],
             ['прямая КПВ: режим «специализация»', 'cCorner', 1, 0]],
  },
  {
    /* (з) Сцены с ДВУМЯ графиками: правка входа обязана менять ОБА поля.
       Полей два ровно в двух сценах — «Функция и её производная наглядно» и
       «Производственная функция». Число сцен тоже проверяем: появится третья —
       проверка про неё напомнит. */
    name: 'Два графика (з) связаны обе сцены из двух',
    run: `return (async function () {
          var w = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
          var panes = function () {
            var ys = [].map.call(document.querySelectorAll('#chart line[marker-end]'), function (l) {
              return (Math.abs(+l.getAttribute('y1') - +l.getAttribute('y2')) < 1.5) ? +l.getAttribute('y1') : null;
            }).filter(function (v) { return v != null; }).sort(function (a, b) { return a - b; });
            return ys.filter(function (v, i, arr) { return i === 0 || Math.abs(v - arr[i - 1]) > 8; });
          };
          /* ⚠️ СРАВНИВАЕМ САМУ КРИВУЮ ПОЛЯ, А НЕ ВСЁ, ЧТО В НЁМ НАРИСОВАНО.
             В нижнем поле кроме производной живут сетка, оси и бегающая точка,
             а точка следует за верхним полем всегда. Проверка на сумме всего
             оставалась зелёной, даже когда нижнюю кривую нарочно замораживали
             (замер зубастости 24.08). Берём в каждом поле САМЫЙ ДЛИННЫЙ путь —
             это и есть кривая — и сверяем именно его. */
          var sig = function (split) {
            var best = { top: null, bot: null };
            document.querySelectorAll('#chart path').forEach(function (p) {
              var d = p.getAttribute('d') || ''; if (!d) return;
              var nums = (d.match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number);
              if (nums.length < 8) return;
              var below = 0;
              for (var i = 1; i < nums.length; i += 2) if (nums[i] >= split) below++;
              var side = (below * 2 > nums.length / 2) ? 'bot' : 'top';
              if (!best[side] || d.length > best[side].length) best[side] = d;
            });
            return best;
          };
          /* ⚠️ ФОРМА КРИВОЙ, А НЕ ЕЁ ПИКСЕЛИ. Нижнее поле подбирает масштаб
             само, поэтому «связано» и «просто сменился масштаб» в пикселях
             неотличимы: замер зубастости 24.08 показал, что нарочно
             ЗАМОРОЖЕННАЯ нижняя кривая всё равно меняла путь — вместе с осями.
             Считаем перемены направления: у прямой их ноль, у параболы одна,
             и никакой масштаб этого не спрячет. */
          var turns = function (d) {
            if (!d) return -1;
            var nums = (d.match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number);
            var ys = [];
            for (var i = 1; i < nums.length; i += 2) ys.push(nums[i]);
            var t = 0, dir = 0;
            for (var j = 1; j < ys.length; j++) {
              var dy = ys[j] - ys[j - 1];
              if (Math.abs(dy) < 1e-9) continue;
              var nd = dy > 0 ? 1 : -1;
              if (dir && nd !== dir) t++;
              dir = nd;
            }
            return t;
          };
          var test = async function (key, fieldId, newValue) {
            resetSceneMemory(); pickScene(key); setToolsOpen(true); await w(450); redrawAll();
            var ys = panes();
            if (ys.length < 2) return { panes: ys.length, top: 0, bot: 0 };
            var split = (ys[0] + ys[1]) / 2;
            var before = sig(split);
            var f = document.getElementById(fieldId);
            f.value = newValue;
            ['input', 'change'].forEach(function (t) { f.dispatchEvent(new Event(t, { bubbles: true })); });
            f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
            var b = [].slice.call(document.querySelectorAll('#tools-panel button'))
              .filter(function (x) { return /Постро/i.test(x.textContent || '') && x.getClientRects().length; })[0];
            if (b) b.click();
            await w(450); redrawAll();
            var after = sig(split);
            return { panes: ys.length,
                     top: (before.top !== after.top) ? 1 : 0,
                     bot: (before.bot !== after.bot) ? 1 : 0,
                     botTurnsBefore: turns(before.bot), botTurnsAfter: turns(after.bot) };
          };
          /* ⚠️ НОВАЯ ФОРМУЛА ОБЯЗАНА МЕНЯТЬ ФОРМУ ПРОИЗВОДНОЙ, А НЕ ТОЛЬКО ЕЁ
             МАСШТАБ. Нижнее поле подбирает масштаб само, поэтому производная
             2x и производная x рисуются ПОБУКВЕННО одинаковым путём: замер
             24.08 показывал «низ не пошёл» там, где всё работает. Берём
             x^3 − 3x: производная становится параболой вместо прямой, и
             никакой масштаб этого не спрячет. */
          var t1 = await test('m-tangent', 'inp-mathf', 'x^3 - 3*x');
          var t2 = await test('prod', 'inp-prod', '25*L^2 - 0.9*L^3');
          // Сцен с двумя полями всего две — считаем по всему списку.
          var two = 0;
          var keys = Object.keys(SCENE_ROUTE);
          for (var i = 0; i < keys.length; i++) {
            resetSceneMemory(); pickScene(keys[i]); await w(320); redrawAll();
            if (panes().length >= 2) two++;
          }
          return { tangentPanes: t1.panes, tangentTop: t1.top, tangentBot: t1.bot,
                   tangentShape0: t1.botTurnsBefore, tangentShape1: t1.botTurnsAfter,
                   prodPanes: t2.panes, prodTop: t2.top, prodBot: t2.bot, scenesWithTwo: two };
          })();`,
    checks: [['полей в «Производной»', 'tangentPanes', 2, 0],
             ['«Производная»: верх пошёл', 'tangentTop', 1, 0],
             ['«Производная»: низ пошёл', 'tangentBot', 1, 0],
             ['«Производная»: у x^2 производная прямая (перемен 0)', 'tangentShape0', 0, 0],
             ['«Производная»: у x^3−3x производная парабола (перемен 1)', 'tangentShape1', 1, 0],
             ['полей в «Производственной функции»', 'prodPanes', 2, 0],
             ['«Производственная»: верх пошёл', 'prodTop', 1, 0],
             ['«Производственная»: низ пошёл', 'prodBot', 1, 0],
             ['сцен с двумя полями', 'scenesWithTwo', 2, 0]],
  },
  {
    /* (и) ХРАПОВИК ШРИФТОВ. Подпись графика, которая ЦЕЛИКОМ математическое
       обозначение, обязана быть набрана математикой (пометка data-mathset).
       Считаем ненабранные в шести сценах: число не должно расти. Потолок 3 —
       это «S» в «Налогах» и «ATC», «MC» в естественной монополии: они
       рисуются ПОСЛЕ конца перерисовки, корень не найден, карточка заведена.
       Опустить потолок можно, поднять — нельзя. */
    name: 'Шрифты (и) обозначений обычным текстом на графике не прибавилось',
    run: `var WORDS = ['MC','MR','TC','ATC','AVC','AFC','FC','VC','TR','TP','MP','AP','CS','PS','DWL',
                      'MSB','MSC','Pw','Px','Py','Qd','Qs','SW'];
          var LET = /^[A-Za-z](?:[*′']|[0-9]|[₀-₉]|_[A-Za-z0-9]+)?$/;
          var vis = function (t) {
            var out = '';
            (function walk(n) {
              for (var i = 0; i < n.childNodes.length; i++) {
                var c = n.childNodes[i];
                if (c.nodeType === 3) { out += c.nodeValue; continue; }
                if (c.nodeType !== 1) continue;
                if (String(c.nodeName).toLowerCase() === 'title') continue;
                walk(c);
              }
            })(t);
            return out.replace(/\\s+/g, ' ').trim();
          };
          var bad = 0, total = 0;
          ['sd', 'costs', 'mono', 'mono-nat', 'ppf', 'taxes'].forEach(function (k) {
            resetSceneMemory(); pickScene(k); redrawAll();
            document.querySelectorAll('#chart text').forEach(function (t) {
              var s = vis(t);
              if (!s) return;
              if (!(WORDS.indexOf(s) >= 0 || LET.test(s))) return;
              total++;
              if (!t.dataset.mathset) bad++;
            });
          });
          return { bad: bad, total: total };`,
    checks: [['обозначений обычным текстом (потолок)', 'bad', 0, 3],
             ['обозначений всего проверено', 'total', 24, 12]],
  },
  {
    /* (л) Исходное состояние сюжета внешних эффектов: MSB и MSC выключены и
       равны частным кривым, поэтому оптимум совпадает с рыночным равновесием,
       DWL равен нулю, а на графике нет ни одной общественной кривой. */
    name: '(л) Внешние эффекты: MSB и MSC выключены по умолчанию, DWL=0',
    run: `pickScene('ext'); redrawAll();
          var e = STATE.ext || {};
          var labels = [].map.call(document.querySelectorAll('#chart text'), function (t) { return t.textContent.trim(); });
          var names = [].map.call(document.querySelectorAll('#chart text.curve-name'), function (t) { return t.textContent.trim(); });
          return { msbOn: STATE.msbOn ? 1 : 0, mscOn: STATE.mscOn ? 1 : 0,
                   boxB: document.getElementById('chk-msb').checked ? 1 : 0,
                   boxC: document.getElementById('chk-msc').checked ? 1 : 0,
                   onChart: (labels.indexOf('MSB') >= 0 ? 1 : 0) + (labels.indexOf('MSC') >= 0 ? 1 : 0),
                   Qmkt: e.Qmkt, Qopt: e.Qopt, dwl: e.dwl,
                   keepD: names.indexOf('D') >= 0 ? 1 : 0, keepS: names.indexOf('S') >= 0 ? 1 : 0 };`,
    checks: [['MSB выключен', 'msbOn', 0, 0], ['MSC выключен', 'mscOn', 0, 0],
             ['галочка MSB снята', 'boxB', 0, 0], ['галочка MSC снята', 'boxC', 0, 0],
             ['общественных кривых на графике нет', 'onChart', 0, 0],
             ['рынок', 'Qmkt', 50, 0.3], ['оптимум совпал с рынком', 'Qopt', 50, 0.3],
             ['DWL', 'dwl', 0, 1e-6],
             ['кривая D не переименована', 'keepD', 1, 0], ['кривая S не переименована', 'keepS', 1, 0]],
  },

  /* =====================================================================
     СЕССИЯ «ЯДРО И КОНСТРУКТОР» (25.08). Кадр больше не участвует в
     математике, строки конструктора кусочной принадлежат полю, а запись
     помещается по ширине. Числа сняты прибором `calc2/tests/input_probe.mjs`
     (наборы К, П, Ш, В, Ф, З) и проверены на зубастость: каждый дефект
     временно возвращали, и случай краснел.
     ⚠️ Все случаи ниже меряют одно и то же ТРИЖДЫ — на стартовом окне, на
     суженном до 30 и на расширенном до 400. Одного замера мало: ровно в этом
     и был дефект — числа сходились на привычном масштабе и разъезжались на
     любом другом.
     ===================================================================== */
  {
    /* (кадр-а) Выпуск и цена монополии не зависят от того, куда смотрит
       человек. На окне до Q = 30 findRoot искал MR = MC только до края кадра,
       корень 40 лежал за ним, и всё табло монополии гасло целиком. */
    name: '(кадр-а) Монополия D 100−Q, MC 20: Qm 40, Pm 60, Qc 80 на трёх масштабах',
    run: `resetSceneMemory(); pickScene('mono');
          var prep = function () {
            var d = STATE.curves.filter(function (c) { return c.role === 'demand'; })[0];
            var mc = STATE.curves.filter(function (c) { return c.role === 'mc'; })[0];
            if (d) updateCurveExpr(d, '100 - Q');
            if (mc) updateCurveExpr(mc, '20');
          };
          var snap = function () { var m = STATE.mono || {}; return [m.Qm, m.Pm, m.Qc]; };
          prep(); redrawAll(); var a = snap();
          setRanges(30, 30); prep(); redrawAll(); var b = snap();
          setRanges(400, 400); prep(); redrawAll(); var c = snap();
          var same = function (i) {
            return (a[i] != null && b[i] != null && c[i] != null
                    && Math.abs(a[i] - b[i]) < 1e-9 && Math.abs(b[i] - c[i]) < 1e-9) ? 1 : 0;
          };
          return { Qm: b[0], Pm: b[1], Qc: b[2], sQ: same(0), sP: same(1), sC: same(2) };`,
    checks: [['Qm на суженном окне', 'Qm', 40, 0.01], ['Pm на суженном окне', 'Pm', 60, 0.01],
             ['Qc на суженном окне', 'Qc', 80, 0.01],
             ['Qm одинаков на трёх масштабах (флаг)', 'sQ', 1, 0],
             ['Pm одинакова на трёх масштабах (флаг)', 'sP', 1, 0],
             ['Qc одинаков на трёх масштабах (флаг)', 'sC', 1, 0]],
  },
  {
    /* (кадр-б) Излом предложения лежит за краем суженного окна. Пробная сетка
       определителя линейности его не видела, кривая запоминалась прямой P = Q,
       и evalCurve шёл быстрым путём по неверным коэффициентам НА ВСЁМ
       отрезке: равновесие выходило 50 вместо 46,67, а S(60) — 60 вместо 80. */
    name: '(кадр-б) Излом S за краем окна: Q* 46,67 и S(60) 80 на трёх масштабах',
    run: `resetSceneMemory(); pickScene('sd');
          var prep = function () {
            var d = STATE.curves.filter(function (c) { return c.role === 'demand'; })[0];
            var s = STATE.curves.filter(function (c) { return c.role === 'supply'; })[0];
            if (d) updateCurveExpr(d, '100 - Q');
            if (s) updateCurveExpr(s, '(Q < 40) ? Q : 2*Q - 40');
          };
          var snap = function () {
            var s = STATE.curves.filter(function (c) { return c.role === 'supply'; })[0];
            return [STATE.eq ? STATE.eq.Q : null, evalCurve(s, 60), s.linear ? 1 : 0];
          };
          prep(); redrawAll(); var a = snap();
          setRanges(30, 30); prep(); redrawAll(); var b = snap();
          setRanges(400, 400); prep(); redrawAll(); var c = snap();
          return { Q: b[0], s60: b[1], fast: a[2] + b[2] + c[2],
                   same: (Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(b[0] - c[0]) < 1e-9) ? 1 : 0 };`,
    checks: [['Q* на суженном окне', 'Q', 46.666667, 1e-4],
             ['S(60) на суженном окне', 's60', 80, 1e-6],
             ['ни на одном масштабе S не запомнена прямой', 'fast', 0, 0],
             ['Q* одинаков на трёх масштабах (флаг)', 'same', 1, 0]],
  },
  {
    /* (кадр-в) Спрос задан как Q(P) с изломом на цене 60. Определитель
       линейности по цене брал ТРИ пробы — 0,2 / 0,5 / 0,8 от края кадра, — и
       на расширенном окне все три ложились выше излома: кривая запоминалась
       прямой Q = 80 − 1,5·P, и равновесие уезжало с 50 на 32. */
    name: '(кадр-в) Q(P) с изломом: Q* 50 на трёх масштабах, прямой нигде не запомнена',
    run: `resetSceneMemory(); pickScene('sd');
          var prep = function () {
            var d = STATE.curves.filter(function (c) { return c.role === 'demand'; })[0];
            var s = STATE.curves.filter(function (c) { return c.role === 'supply'; })[0];
            if (d) updateCurveExpr(d, '(P < 60) ? 100 - P : 80 - 1.5*P');
            if (s) updateCurveExpr(s, 'Q');
          };
          var snap = function () {
            var d = STATE.curves.filter(function (c) { return c.role === 'demand'; })[0];
            return [STATE.eq ? STATE.eq.Q : null, d.srcLinear ? 1 : 0];
          };
          prep(); redrawAll(); var a = snap();
          setRanges(30, 30); prep(); redrawAll(); var b = snap();
          setRanges(400, 400); prep(); redrawAll(); var c = snap();
          return { Q: c[0], fast: a[1] + b[1] + c[1],
                   same: (Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(b[0] - c[0]) < 1e-9) ? 1 : 0 };`,
    checks: [['Q* на расширенном окне', 'Q', 50, 1e-4],
             ['ни на одном масштабе D не запомнена прямой', 'fast', 0, 0],
             ['Q* одинаков на трёх масштабах (флаг)', 'same', 1, 0]],
  },
  {
    /* (кадр-г) Нелинейное предложение Q = 0,01·P² при спросе 300 − Q.
       Равновесная цена 130,28; обращение Q(P) сканировало цены только до
       Pmax·3, и на окне до тридцати верх сетки был 90 — равновесия у сцены
       не было вовсе. */
    name: '(кадр-г) Нелинейное Q(P): Q* 169,72 и P* 130,28 на трёх масштабах',
    run: `resetSceneMemory(); pickScene('sd');
          var prep = function () {
            var d = STATE.curves.filter(function (c) { return c.role === 'demand'; })[0];
            var s = STATE.curves.filter(function (c) { return c.role === 'supply'; })[0];
            if (d) updateCurveExpr(d, '300 - Q');
            if (s) updateCurveExpr(s, '0.01*P^2');
          };
          var snap = function () { return [STATE.eq ? STATE.eq.Q : null, STATE.eq ? STATE.eq.P : null]; };
          prep(); redrawAll(); var a = snap();
          setRanges(30, 30); prep(); redrawAll(); var b = snap();
          setRanges(400, 400); prep(); redrawAll(); var c = snap();
          return { Q: b[0], P: b[1],
                   same: (a[0] != null && b[0] != null && c[0] != null
                          && Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(b[0] - c[0]) < 1e-9) ? 1 : 0 };`,
    checks: [['Q* на суженном окне', 'Q', 169.722436, 1e-4],
             ['P* на суженном окне', 'P', 130.277564, 1e-4],
             ['Q* одинаков на трёх масштабах (флаг)', 'same', 1, 0]],
  },
  {
    /* (кадр-д) Шаг центральной разности брался от края кадра, и на кривой с
       заметной кривизной одна и та же точка давала на разных масштабах разный
       наклон — а значит и разную эластичность. Меряем ядро напрямую. */
    name: '(кадр-д) Численная производная в точке не зависит от масштаба',
    run: `var mk = function (e) { var c = compileFormula(e); return { expr: e, compiled: c.compiled, linear: null, fn: null }; };
          var was = CONFIG.Qmax;
          var d = [100, 30, 400].map(function (qm) {
            CONFIG.Qmax = qm;
            return curveDeriv(mk('100 - 40*sin(Q)'), 3);
          });
          CONFIG.Qmax = was;
          return { d0: d[0],
                   same: (Math.abs(d[0] - d[1]) < 1e-9 && Math.abs(d[1] - d[2]) < 1e-9) ? 1 : 0 };`,
    checks: [['производная в Q=3 (эталон −40·cos 3)', 'd0', 39.5996998, 1e-5],
             ['одинакова на трёх масштабах (флаг)', 'same', 1, 0]],
  },
  {
    /* (кадр-е) Общественный оптимум и потери от внешнего эффекта на суженном
       окне. Оптимум ищет тот же findRoot: на окне до 30 гасло всё табло. */
    name: '(кадр-е) Внешние эффекты MSC = Q+20: оптимум 40 и DWL 100 на трёх масштабах',
    run: `resetSceneMemory(); pickScene('ext');
          var prep = function () {
            var d = STATE.curves.filter(function (c) { return c.role === 'demand'; })[0];
            var s = STATE.curves.filter(function (c) { return c.role === 'supply'; })[0];
            if (d) updateCurveExpr(d, '100 - Q');
            if (s) updateCurveExpr(s, 'Q');
            STATE.mscOn = true; STATE.mscExpr = 'Q + 20'; STATE.msbOn = false;
            recompileSocial();
          };
          var snap = function () { var e = STATE.ext || {}; return [e.Qopt, e.dwl]; };
          prep(); redrawAll(); var a = snap();
          setRanges(30, 30); prep(); redrawAll(); var b = snap();
          setRanges(400, 400); prep(); redrawAll(); var c = snap();
          return { Qopt: b[0], dwl: b[1],
                   same: (a[0] != null && b[0] != null && c[0] != null
                          && Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(b[0] - c[0]) < 1e-9) ? 1 : 0 };`,
    checks: [['оптимум на суженном окне', 'Qopt', 40, 0.01],
             ['DWL на суженном окне', 'dwl', 100, 0.01],
             ['оптимум одинаков на трёх масштабах (флаг)', 'same', 1, 0]],
  },
  {
    /* (конс-а) Строки конструктора кусочной принадлежат ПОЛЮ, а не странице.
       Открыли конструктор в «Математике» (буква x), ушли в «Спрос и
       предложение» — и в полях спроса лежали те же куски с иксом, а условия
       под ними уже писались по Q. */
    name: '(конс-а) Конструктор не течёт между полями и моделями',
    run: `var open = function (id) {
            var inp = document.getElementById(id);
            var row = inp.closest('.f-row');
            row.querySelector('.f-help').click();
            document.querySelector('.mkbd.open .mkbd-foot button').click();
            var out = { v: PW.v, all: PW.rows.map(function (r) { return r.f + ' ' + r.a + ' ' + r.b; }).join(' ') };
            closePiecewise();
            return out;
          };
          resetSceneMemory(); pickScene('m-graph');
          if (typeof addCurve === 'function' && !STATE.curves.length) addCurve();
          var rows = [].slice.call(document.querySelectorAll('#tools-panel .f-row'))
            .filter(function (r) { return r.offsetParent; });
          var mathInp = rows[0].querySelector('input');
          if (!mathInp.id) mathInp.id = 'ip-math-field';
          var m = open(mathInp.id);
          resetSceneMemory(); pickScene('sd'); redrawAll();
          var d = open('curve-expr-1');
          // Метка в спросе не должна доехать до предложения.
          var inp = document.getElementById('curve-expr-1');
          inp.closest('.f-row').querySelector('.f-help').click();
          document.querySelector('.mkbd.open .mkbd-foot button').click();
          PW.rows[0].f = 'МЕТКА'; closePiecewise();
          var s = open('curve-expr-2');
          return { mathX: /(^|[^A-Za-z0-9_])x([^A-Za-z0-9_]|$)/.test(m.all) ? 1 : 0,
                   demandQ: /(^|[^A-Za-z0-9_])Q([^A-Za-z0-9_]|$)/.test(d.all) ? 1 : 0,
                   demandX: /(^|[^A-Za-z0-9_])[xX]([^A-Za-z0-9_]|$)/.test(d.all) ? 1 : 0,
                   supplyMark: /МЕТКА/.test(s.all) ? 1 : 0 };`,
    checks: [['в «Математике» куски по x (флаг)', 'mathX', 1, 0],
             ['в «Спросе» куски по Q (флаг)', 'demandQ', 1, 0],
             ['в «Спросе» иксов нет (флаг)', 'demandX', 0, 0],
             ['метка спроса не доехала до предложения (флаг)', 'supplyMark', 0, 0]],
  },
  {
    /* (конс-б) Уже стоящая в поле кусочная разбирается обратно в те же куски.
       Между записью и проверкой ОБЯЗАТЕЛЬНО заходим в чужое поле: иначе
       случай проходил бы и на утечке — строки просто оставались бы в PW. */
    name: '(конс-б) Стоящая в поле кусочная разбирается обратно в свои куски',
    run: `var open = function (id) {
            var inp = document.getElementById(id);
            inp.closest('.f-row').querySelector('.f-help').click();
            document.querySelector('.mkbd.open .mkbd-foot button').click();
          };
          resetSceneMemory(); pickScene('sd'); redrawAll();
          open('curve-expr-1');
          PW.n = 2;
          PW.rows = [{ f: '90 - Q', a: '0', b: '30' }, { f: '60 - 0.5*Q', a: '30', b: '' }];
          renderPw();
          document.getElementById('pw-apply').click();
          open('curve-expr-2');
          var mid = PW.rows[0].f;
          closePiecewise();
          open('curve-expr-1');
          var back = PW.rows.map(function (r) { return r.f + '|' + r.a + '|' + r.b; }).join(' ; ');
          closePiecewise();
          return { midDefault: (mid === '100 - Q') ? 1 : 0,
                   back: back,
                   ok: (back === '90 - Q|0|30 ; 60 - 0.5*Q|30|') ? 1 : 0 };`,
    checks: [['чужое поле показало значения по умолчанию (флаг)', 'midDefault', 1, 0],
             ['разбор вернул те же два куска (флаг)', 'ok', 1, 0]],
  },
  {
    /* (панель-а) Вопросик появляется только рядом с тем, что он поясняет.
       Раньше подсказка без якоря получала СВОЮ пустую строку, и в «Спросе и
       предложении» висели два одиноких знака при НУЛЕ живых подсказок. */
    name: '(панель-а) Одиноких «?» в левой панели нет ни в одной проверенной сцене',
    run: `var scan = function (key) {
            resetSceneMemory(); pickScene(key); redrawAll();
            var panel = document.getElementById('tools-panel');
            var vis = function (el) { return !!(el.offsetParent || el.getClientRects().length); };
            var dots = [].slice.call(panel.querySelectorAll('.help-dot')).filter(vis);
            var lonely = dots.filter(function (d) {
              var host = d.parentElement;
              return !host || host.textContent.replace(/[?\s]/g, '').length === 0;
            });
            var hints = [].slice.call(panel.querySelectorAll('.hint')).filter(function (h) {
              return h.style.display !== 'none' && fieldActive(h.parentElement || h);
            });
            return { lonely: lonely.length, dots: dots.length, hints: hints.length,
                     anchors: panel.querySelectorAll('.help-anchor').length };
          };
          var keys = ['sd', 'mono', 'ext', 'sdsum', 'elast', 'taxes', 'ppf'];
          var lonely = 0, over = 0, anchors = 0;
          keys.forEach(function (k) {
            var r = scan(k);
            lonely += r.lonely; anchors += r.anchors;
            if (r.dots > r.hints) over++;
          });
          return { lonely: lonely, over: over, anchors: anchors };`,
    checks: [['одиноких «?» по семи сценам', 'lonely', 0, 0],
             ['сцен, где знаков больше живых подсказок', 'over', 0, 0],
             ['пустых строк .help-anchor в разметке', 'anchors', 0, 0]],
  },
  /* =====================================================================
     ВНЕШНИЙ ВИД СЛОЖЕНИЯ (сессия 25.08, ветка feat/calc2-sum-visual).
     Пять свойств, каждое из которых уже один раз было сломано и каждое
     проверено «зубастостью»: возвращаешь дефект — случай краснеет.
     Подробные замеры (контраст, расстояния между цветами, прямоугольники
     подписей) снимает calc2/tests/sum_visual_probe.mjs; здесь стоят те
     проверки, которые обязаны идти в CI на каждом прогоне.
     ===================================================================== */
  {
    /* ⚠️ ЦВЕТ ГРУППЫ НЕ ИМЕЕТ ПРАВА СОВПАСТЬ С ЦВЕТОМ СУММЫ.
       Группы брали цвета из общей палитры выбора, а её первые два цвета —
       те же канонические --curve-d и --curve-s, которыми красятся суммарные
       кривые. На экране «спрос первой группы» был одного цвета с «рыночным
       спросом», а «спрос второй группы» — с «рыночным предложением».
       Проверяем на четырёх группах в каждом семействе: там задействована
       вся палитра целиком. */
    name: 'Сложение (ж) цвет группы отличается от цвета суммы и от других групп',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 4); sumSetCount('S', 4); redrawAll();
          var norm = function (v) { return String(v || '').trim().toLowerCase(); };
          var groups = STATE.curves.filter(function (c) { return c.sumGroup && c.kind !== 'sum'; });
          var sums = STATE.curves.filter(function (c) { return c.kind === 'sum'; });
          var clash = 0, dup = 0;
          groups.forEach(function (g) {
            sums.forEach(function (s) { if (norm(g.color) === norm(s.color)) clash++; });
          });
          for (var i = 0; i < groups.length; i++) {
            for (var j = i + 1; j < groups.length; j++) {
              if (norm(groups[i].color) === norm(groups[j].color)) dup++;
            }
          }
          /* Канонические цвета обязаны остаться у сумм: на них держатся все
             сорок одна сцена, и «развести» их подменой было бы негодным. */
          var d = sums.find(function (c) { return c.sumGroup === 'D'; });
          var s = sums.find(function (c) { return c.sumGroup === 'S'; });
          var canonD = norm(d && d.color) === norm(cssVar('--curve-d')) ? 1 : 0;
          var canonS = norm(s && s.color) === norm(cssVar('--curve-s')) ? 1 : 0;
          return { clash: clash, dup: dup, canonD: canonD, canonS: canonS, n: groups.length };`,
    checks: [['групп в сцене', 'n', 8, 0],
             ['совпадений «цвет группы = цвет суммы»', 'clash', 0, 0],
             ['пар групп, делящих один цвет', 'dup', 0, 0],
             ['у суммарного спроса канонический цвет', 'canonD', 1, 0],
             ['у суммарного предложения канонический цвет', 'canonS', 1, 0]],
  },
  {
    /* ⚠️ КОНТРАСТ ЛИНИИ К ХОЛСТУ — НЕ МЕНЬШЕ 3:1 В ОБЕИХ ТЕМАХ.
       Приглушение групп прозрачностью снижает итоговый контраст, поэтому
       меряем ЦВЕТ ПОВЕРХ ХОЛСТА, а не исходный тон. Порог 3:1 — норма для
       графических объектов; ниже линию просто не видно на проекторе. */
    name: 'Сложение (з) контраст каждой линии к холсту не ниже 3:1 в обеих темах',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 4); sumSetCount('S', 4); redrawAll();
          var rgb = function (v) {
            v = String(v || '').trim();
            if (v.charAt(0) === '#') { var h = v.slice(1);
              if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
              return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)]; }
            var m = v.match(/rgba?\(([^)]+)\)/);
            return m ? m[1].split(/[,\s\/]+/).filter(Boolean).map(Number).slice(0,3) : null;
          };
          var lum = function (c) { var f = c.map(function (x) { x /= 255;
            return x <= 0.03928 ? x/12.92 : Math.pow((x+0.055)/1.055, 2.4); });
            return 0.2126*f[0] + 0.7152*f[1] + 0.0722*f[2]; };
          var ratio = function (a, b) { var l1 = lum(a), l2 = lum(b);
            if (l1 < l2) { var t = l1; l1 = l2; l2 = t; } return (l1+0.05)/(l2+0.05); };
          var worst = 99;
          ['light', 'dark'].forEach(function (th) {
            document.documentElement.setAttribute('data-theme', th);
            refreshColors(); redrawAll();
            var bg = rgb(cssVar('--canvas'));
            [].slice.call(document.querySelectorAll('#chart path[data-curve]')).forEach(function (p) {
              if (p.getAttribute('data-skip-export') === '1') return;
              var cs = getComputedStyle(p);
              var op = parseFloat(p.getAttribute('opacity') != null ? p.getAttribute('opacity') : (cs.opacity || '1'));
              var al = (isFinite(op) ? op : 1) * (parseFloat(cs.strokeOpacity || '1') || 1);
              var col = rgb(p.getAttribute('stroke') || cs.stroke);
              if (!col || !bg) return;
              var eff = [0,1,2].map(function (i) { return col[i]*al + bg[i]*(1-al); });
              var r = ratio(eff, bg);
              if (r < worst) worst = r;
            });
          });
          document.documentElement.setAttribute('data-theme', 'light');
          refreshColors(); redrawAll();
          return { worst: Math.round(worst * 100) / 100, ok: (worst >= 3) ? 1 : 0 };`,
    checks: [['худший контраст линии к холсту не ниже 3:1', 'ok', 1, 0],
             ['сам худший контраст (справочно, не ниже 3)', 'worst', 3.25, 0.9]],
  },
  {
    /* ⚠️ УЧАСТОК, ГДЕ РЫНКА НЕТ, РИСУЕТСЯ ПУНКТИРОМ ТОГО ЖЕ ВЕСА.
       При предложении Q − 100 первый продавец выходит на рынок только со ста
       единиц, и на отрезке Q от 0 до 100 рыночного предложения не существует.
       Прошлая сессия закрыла там дырку нулём — и на холсте получилась ровная
       линия по оси, неотличимая от самой оси. Решение владельца: тот же цвет,
       та же толщина, отличие только в штрихе. */
    name: 'Сложение (и) несуществующий участок суммарной кривой — пунктир того же веса',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 2); sumSetCount('S', 2);
          var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
          updateCurveExpr(gs[0], 'Q-100'); updateCurveExpr(gs[1], 'Q+20');
          redrawAll();
          var sum = STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'S'; });
          var ps = [].slice.call(document.querySelectorAll('#chart path[data-curve="' + sum.id + '"]'));
          var gh = ps.filter(function (p) { return p.getAttribute('data-sum-part') === 'ghost'; });
          var re = ps.filter(function (p) { return p.getAttribute('data-sum-part') === 'real'; });
          var num = function (p, a) { return parseFloat(p.getAttribute(a) || getComputedStyle(p)[a] || '0'); };
          var sameColor = (gh.length && re.length &&
            String(gh[0].getAttribute('stroke')) === String(re[0].getAttribute('stroke'))) ? 1 : 0;
          var sameWidth = (gh.length && re.length &&
            Math.abs(num(gh[0], 'stroke-width') - num(re[0], 'stroke-width')) < 0.01) ? 1 : 0;
          var alpha = gh.length ? parseFloat(gh[0].getAttribute('opacity') || '1') : 0;
          /* Стык считаем в пикселях: щель шириной в шаг сетки на экране
             читается как разрыв, а число «путей два» о ней молчит. */
          var gap = 0;
          if (gh.length && re.length) {
            var a = gh[0].getPointAtLength(gh[0].getTotalLength());
            var b = re[0].getPointAtLength(0);
            gap = Math.hypot(a.x - b.x, a.y - b.y);
          }
          return { ghost: gh.length, real: re.length, sameColor: sameColor,
                   sameWidth: sameWidth, alpha: alpha,
                   ghostTo: Math.round((sum.sumGhostTo || 0) * 100) / 100,
                   gap: Math.round(gap * 100) / 100 };`,
    checks: [['пунктирный участок нарисован', 'ghost', 1, 0],
             ['сплошной участок ровно один', 'real', 1, 0],
             ['докуда рынка нет, по количеству', 'ghostTo', 100, 0.01],
             ['цвет пунктира тот же, что у сплошной', 'sameColor', 1, 0],
             ['толщина пунктира та же, что у сплошной', 'sameWidth', 1, 0],
             ['пунктир не бледнее сплошной', 'alpha', 1, 0],
             ['щель на стыке, px', 'gap', 0, 0.35]],
  },
  {
    /* ⚠️ НА ХОЛСТЕ — ОБОЗНАЧЕНИЕ, В ПАНЕЛИ — ПОЛНОЕ ИМЯ.
       «спрос первой группы» занимает 137 px, «предложение второй группы» —
       181. Шесть таких подписей выстраивались вдоль края с зазором меньше
       внутреннего пробела шрифта и читались одной строкой. Связь холста с
       панелью держится тем, что то же обозначение стоит в строке списка. */
    name: 'Сложение (к) на холсте обозначение, в панели полное имя',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 3); sumSetCount('S', 2); redrawAll();
          var raw = [].slice.call(document.querySelectorAll('#chart text.curve-name'))
            .map(function (t) { return String(t.getAttribute('data-raw') || '').trim(); });
          var longOnes = raw.filter(function (s) { return s.length > 4; }).length;
          var wantD1 = raw.indexOf('D_1') >= 0 ? 1 : 0;
          var wantSum = raw.indexOf('D') >= 0 ? 1 : 0;
          /* Полное имя обязано остаться в панели: обозначение его не заменяет,
             а сопровождает. Иначе связь холста со списком теряется. */
          var names = [].slice.call(document.querySelectorAll('#curve-list .curve-row span.curve-name'))
            .map(function (e) { return e.textContent.replace(/\s+/g, ' ').trim(); });
          var full = names.filter(function (s) { return /групп/.test(s) || /рыночн/.test(s); }).length;
          var tags = document.querySelectorAll('#curve-list .crow-tag').length;
          /* Строка суммарной кривой не должна выглядеть обломком: поля формулы
             у неё нет и быть не может, но пустое место надо объяснить. */
          var autos = document.querySelectorAll('#curve-list .crow-auto').length;
          return { longOnes: longOnes, wantD1: wantD1, wantSum: wantSum,
                   full: full, tags: tags, autos: autos };`,
    checks: [['подписей длиннее четырёх знаков на холсте', 'longOnes', 0, 0],
             ['подпись первой группы спроса — D с индексом', 'wantD1', 1, 0],
             ['подпись суммарного спроса — D', 'wantSum', 1, 0],
             ['строк списка с полным именем', 'full', 7, 0],
             ['обозначений в строках списка', 'tags', 7, 0],
             ['пояснений у строк суммарных кривых', 'autos', 2, 0]],
  },
  {
    /* ⚠️ ПОДПИСЬ ПОЛЗУНКА НЕ ИМЕЕТ ПРАВА БЫТЬ ОБРЕЗАННОЙ.
       Резало дважды: код обрезал имя по шестнадцати символам, а CSS дорезал
       строку многоточием. При пяти группах на панели стояло пять одинаковых
       «Сдвиг спрос … = 0». */
    name: 'Сложение (л) подписи ползунков различимы и не обрезаны',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 3); sumSetCount('S', 2); redrawAll();
          if (typeof updatePult === 'function') updatePult();
          var chips = [].slice.call(document.querySelectorAll('#params-curves .pchip'));
          var cut = 0, seen = {}, dupText = 0, bright = 0;
          var lum = function (c) { var f = c.map(function (x) { x /= 255;
            return x <= 0.03928 ? x/12.92 : Math.pow((x+0.055)/1.055, 2.4); });
            return 0.2126*f[0] + 0.7152*f[1] + 0.0722*f[2]; };
          chips.forEach(function (ch) {
            var lab = ch.querySelector('.pchip-label');
            if (!lab) return;
            if (lab.scrollWidth > lab.clientWidth + 1) cut++;
            var cl = lab.cloneNode(true);
            cl.querySelectorAll('.katex-mathml, annotation').forEach(function (x) { x.remove(); });
            var t = cl.textContent.replace(/\s+/g, ' ').trim();
            if (/…/.test(t)) cut++;
            if (seen[t]) dupText++; else seen[t] = 1;
            /* Светлый акцент заставляет Chromium рисовать незалитую дорожку
               тёмной, и на панели оказываются рядом ползунки двух видов.
               Порог измерен перебором: 0,2487 — ещё светлая, 0,2545 — уже
               тёмная. Держим запас. */
            var sl = ch.querySelector('input[type=range]');
            var m = sl && String(getComputedStyle(sl).accentColor || '').match(/rgba?\(([^)]+)\)/);
            if (m) {
              var c = m[1].split(/[,\s\/]+/).filter(Boolean).map(Number).slice(0, 3);
              if (lum(c) > 0.245) bright++;
            }
          });
          return { chips: chips.length, cut: cut, dupText: dupText, bright: bright };`,
    checks: [['ползунков сдвига в сцене', 'chips', 5, 0],
             ['обрезанных подписей', 'cut', 0, 0],
             ['подписей-двойников', 'dupText', 0, 0],
             ['ползунков со светлым акцентом (тёмная дорожка)', 'bright', 0, 0]],
  },

  /* ═══════════════════════════════════════════════════════════════════
     ПРИЁМКА 25.08. Семь дефектов владельца плюс одна возможность.
     Полный разбор — прибор calc2/tests/priyomka_probe.mjs; здесь стоят
     ЧИСЛА, которые обязаны держаться в CI.
     ═══════════════════════════════════════════════════════════════════ */
  {
    /* ⚠️ ВМЕШАТЕЛЬСТВО РАБОТАЕТ БЕЗ РАВНОВЕСИЯ.
       Дефект: в recompute всё вмешательство было обёрнуто условием, куда
       вместе с кривыми и ставкой входило `STATE.eq`, и одно это слагаемое
       выключало сдвиг кривой целиком. На рынке D = 100 − P, S = 0,5·p − 200
       (пересечение в (−100; 200), то есть вне первой четверти) налог не
       двигал предложение вовсе — график стоял на месте.

       Три края правила, и все три здесь:
         • кривая после вмешательства строится ВСЕГДА: налог 100 поднимает
           предложение, и оно обращается в ноль при цене 500 вместо 400;
         • равновесия при этом по-прежнему нет — числа не выдумываются;
         • субсидия 450 равновесие СОЗДАЁТ: Q = 50, цена покупателя 50, цена
           продавца 500, расход бюджета 22 500. DWL при этом НЕ считается:
           сравнивать не с чем, и об этом сказано словами. */
    name: 'Приёмка · вмешательство работает без равновесия',
    run: `var setup = function (type, form, rate) {
            resetSceneMemory(); pickScene('taxes');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-P');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), '0.5*p-200');
            setType(type); setTaxForm(form); setTax(rate); redrawAll();
          };
          var textOf = function (id) {
            var e = document.getElementById(id); if (!e) return '';
            var c = e.cloneNode(true);
            c.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
            return c.textContent.replace(/\s+/g, ' ');
          };
          setup('tax', 'unit', 0);
          var zeroNoTax = evalCurve(STATE.S, 0);
          var eq0 = STATE.eq ? 1 : 0;
          setup('tax', 'unit', 100);
          var zeroTax = STATE.taxAfterS ? STATE.taxAfterS.fn(0) : NaN;
          var drawn = document.querySelectorAll('path[stroke-dasharray="6 4"]').length;
          var eqTax = STATE.eq ? 1 : 0, dwlTax = (STATE.dwl > 0) ? 1 : 0;
          setup('subsidy', 'unit', 450);
          var te = STATE.taxEq || {};
          var said = /сравнивать не с чем|рынка не было вовсе/i.test(textOf('info-tax') + ' ' + textOf('info-eq'));
          return { zeroNoTax: zeroNoTax, eq0: eq0, zeroTax: zeroTax, drawn: drawn,
                   eqTax: eqTax, dwlTax: dwlTax,
                   q: te.Q, pd: te.Pb, ps: te.Ps, spend: Math.abs(STATE.budget),
                   dwlSub: (STATE.dwl > 0) ? 1 : 0, said: said ? 1 : 0 };`,
    checks: [['без налога предложение в ноль при цене', 'zeroNoTax', 400, 1e-6],
             ['без налога равновесия нет', 'eq0', 0, 0],
             ['с налогом 100 предложение в ноль при цене', 'zeroTax', 500, 1e-6],
             ['кривая после вмешательства нарисована', 'drawn', 1, 0],
             ['с налогом равновесия по-прежнему нет', 'eqTax', 0, 0],
             ['DWL без исходного равновесия не показан', 'dwlTax', 0, 0],
             ['субсидия 450 создаёт рынок: Q', 'q', 50, 1e-6],
             ['цена покупателя', 'pd', 50, 1e-6],
             ['цена продавца', 'ps', 500, 1e-6],
             ['расход бюджета', 'spend', 22500, 1e-6],
             ['DWL по-прежнему не показан', 'dwlSub', 0, 0],
             ['сказано словами, что сравнивать не с чем', 'said', 1, 0]],
  },
  {
    /* ⚠️ ПОРЯДОК КАРТОЧКИ «ВМЕШАТЕЛЬСТВО ГОСУДАРСТВА».
       Решение владельца 25.08: ставка это не параметр формулы, а орган
       управления сценой, и в ленте регуляторов ей не место. Лента живёт
       ВЫШЕ карточки, поэтому перенос ломал порядок каскада: замер 25.08 —
       ряд «Налог платит» на y = 136, ставка на y = 199, а сам выбор вида
       вмешательства только на y = 307.

       Порядок обязан быть один и тот же у налога и у субсидии: ряд «кто
       платит / кто получает» третьим, ВСЕГДА выше ставки. */
    name: 'Приёмка · ставка вмешательства живёт в своей карточке, а не в ленте',
    run: `var y = function (sel) {
            var e = document.querySelector(sel);
            if (!e || !(e.offsetParent || e.getClientRects().length)) return null;
            return Math.round(e.getBoundingClientRect().top);
          };
          var inRibbon = function (id) {
            var e = document.getElementById(id);
            return (e && e.closest('#params-body')) ? 1 : 0;
          };
          var look = function (type, form) {
            resetSceneMemory(); pickScene('taxes');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '120-Q');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
            setType(type); if (form) setTaxForm(form); setTax(20); redrawAll();
            return { seg: y('#sec-tax > .seg'), kind: y('#taxkind-row'),
                     side: y('#taxside-row'), rate: y('#tax-field'),
                     ribbon: inRibbon('tax-field') + inRibbon('taxside-row')
                             + inRibbon('pc-field') + inRibbon('quota-field') };
          };
          var t = look('tax', 'unit'), s = look('subsidy', 'unit');
          var e = look('tax', 'excise');
          var ordered = function (o) {
            return (o.seg < o.kind && o.kind < o.side && o.side < o.rate) ? 1 : 0;
          };
          return { tax: ordered(t), sub: ordered(s),
                   pctOrdered: (e.seg < e.kind && e.kind < e.rate) ? 1 : 0,
                   ribbon: t.ribbon + s.ribbon + e.ribbon };`,
    checks: [['налог: вид → вид налога → кто платит → ставка', 'tax', 1, 0],
             ['субсидия: тот же порядок, ряд стороны третьим', 'sub', 1, 0],
             ['процентная форма: вид → вид налога → ставка', 'pctOrdered', 1, 0],
             ['органов управления вмешательством в ленте регуляторов', 'ribbon', 0, 0]],
  },
  {
    /* ⚠️ КОНСТРУКТОР КУСОЧНОЙ: КОЛОНКИ УЧАСТКА СВОЕЙ ШИРИНЫ.
       Указание владельца 25.08. Колонки «От» и «До» были жёсткие по 52 px и
       стояли последними, а поле формулы забирало остаток строки. Вдобавок
       единственная кнопка клавиатуры переезжает в ту строку, где стоит
       каретка, и отнимала свои 32 px у поля формулы: замер 25.08 — в строке
       с курсором поле 118 px, в остальных 156 px.

       Стало: сетка с постоянными колонками и зарезервированным местом под
       клавиатуру. Ширина поля формулы одна для ВСЕХ строк. */
    name: 'Приёмка · конструктор кусочной: колонки участка не ужимаются',
    run: `resetSceneMemory(); pickScene('sd'); redrawAll();
          openPiecewise(document.querySelector('.f-slot > input'), 'Q');
          PW.n = 5; renderPw();
          var card = document.querySelector('#pw-modal .modal-card');
          var slots = [], bounds = [], overflow = 0;
          document.querySelectorAll('#pw-rows .pw-row').forEach(function (row) {
            var sl = row.querySelector('.f-slot');
            if (sl) slots.push(Math.round(sl.getBoundingClientRect().width));
            row.querySelectorAll('input.pw-bound').forEach(function (b) {
              bounds.push(Math.round(b.getBoundingClientRect().width));
            });
            var last = row.querySelectorAll('input.pw-bound');
            if (last.length && card &&
                last[last.length - 1].getBoundingClientRect().right > card.getBoundingClientRect().right + 1) overflow++;
          });
          /* Ширина окна задана правилом min(720px, 92vw), поэтому в узком
             браузере она МЕНЬШЕ 720 по построению. Сравниваем с самим
             правилом, а не с числом: иначе проверка ловила бы ширину окна
             прогонщика, а не вёрстку. */
          /* Ширина окна задана правилом min(720px, 92vw), и в узком браузере
             она МЕНЬШЕ 720 по построению — плюс поля самого модального слоя.
             Поэтому сравниваем не с числом, а с двумя краями правила: окно
             заметно шире прежних 380 px и не шире 92 % браузера. */
          var cw = card ? Math.round(card.getBoundingClientRect().width) : 0;
          var res = { cardW: cw, winW: window.innerWidth,
                      widerThanOld: cw >= 600 ? 1 : 0,
                      rows: slots.length,
                      slotWidths: new Set(slots).size,
                      boundOk: (bounds.length && Math.min.apply(null, bounds) >= 90) ? 1 : 0,
                      overflow: overflow,
                      hScroll: card ? (card.scrollWidth > card.clientWidth + 1 ? 1 : 0) : 1,
                      wide: card ? (card.getBoundingClientRect().width <= window.innerWidth * 0.92 ? 1 : 0) : 0 };
          var close = document.getElementById('pw-close'); if (close) close.click();
          return res;`,
    checks: [['строк участка при пяти кусках', 'rows', 5, 0],
             ['окно конструктора шире прежних 380 px', 'widerThanOld', 1, 0],
             ['окно не шире 92 % браузера', 'wide', 1, 0],
             ['разных ширин поля формулы (курсор колонки не двигает)', 'slotWidths', 1, 0],
             ['самая узкая колонка участка не уже 90 px', 'boundOk', 1, 0],
             ['колонок за правым краем окна', 'overflow', 0, 0],
             ['горизонтальная прокрутка окна', 'hScroll', 0, 0]],
  },
  {
    /* ⚠️ СЛАГАЕМОЕ СЛОЖЕНИЯ ОФОРМЛЕНО ПО ОБРАЗЦУ СЛОЖЕНИЯ КПВ.
       Владелец 25.08: «сделай оформление так же, как при сложении нескольких
       КПВ». Оттуда толщина 1,6 и штрих «5 4»; прозрачность НЕ 0,6 из
       образца, а найденная перебором — наибольшая приглушающая, при которой
       контраст итогового цвета к холсту держит 3:1 в обеих темах. Перебор с
       шагом 0,05 от 0,5 вверх по восьми цветам палитры в двух темах дал 0,95
       (его требуют фиолетовый и маджента в тёмной теме).

       И два пунктира в одной сцене обязаны быть различимы: участок «рынка
       здесь нет» — штрих 12/6 при толщине 3,2 и полной непрозрачности,
       слагаемое — 5/4 при 1,6. Вдвое по толщине и вдвое с лишним по штриху. */
    name: 'Приёмка · слагаемые сложения: штрих 5 4, толщина 1,6, приглушение 0,95',
    run: `resetSceneMemory(); pickScene('sdsum');
          sumSetCount('D', 3); sumSetCount('S', 2);
          var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
          var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
          ['100-Q', '60-Q', '40-Q'].forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
          ['Q-100', 'Q+20'].forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
          renderCurveList(); redrawAll();
          var groups = 0, badDash = 0, badWidth = 0, badOp = 0;
          var sums = 0, sumDashed = 0, ghost = 0, ghostOk = 0, dense = 0;
          document.querySelectorAll('path[data-curve]').forEach(function (el) {
            var id = +el.getAttribute('data-curve');
            var cur = STATE.curves.find(function (c) { return c.id === id; });
            if (!cur || !cur.sumGroup) return;
            var cs = getComputedStyle(el);
            var w = parseFloat(cs.strokeWidth), op = parseFloat(cs.opacity || '1');
            var dash = (cs.strokeDasharray === 'none' ? '' : cs.strokeDasharray);
            var pts = (String(el.getAttribute('d') || '').match(/[ML]/g) || []).length;
            if (pts > 12) dense++;
            if (cur.kind === 'sum') {
              if (el.getAttribute('data-sum-part') === 'ghost') {
                ghost++;
                if (/^12(px)?[, ]/.test(dash) && Math.abs(w - 3.2) < 1e-6 && op === 1) ghostOk++;
              } else {
                sums++;
                if (dash) sumDashed++;
                if (Math.abs(w - 3.2) > 1e-6) badWidth++;
              }
              return;
            }
            groups++;
            if (!/^5(px)?[, ]/.test(dash)) badDash++;
            if (Math.abs(w - 1.6) > 1e-6) badWidth++;
            if (!(op > 0.9 && op < 1)) badOp++;
          });
          return { groups: groups, badDash: badDash, badWidth: badWidth, badOp: badOp,
                   sums: sums, sumDashed: sumDashed, ghost: ghost, ghostOk: ghostOk, dense: dense };`,
    checks: [['слагаемых в сцене', 'groups', 5, 0],
             ['слагаемых без штриха 5 4', 'badDash', 0, 0],
             ['линий не своей толщины', 'badWidth', 0, 0],
             ['слагаемых без приглушения', 'badOp', 0, 0],
             ['суммарных кривых', 'sums', 2, 0],
             ['суммарных кривых со штрихом', 'sumDashed', 0, 0],
             ['участков «рынка здесь нет»', 'ghost', 1, 0],
             ['из них со штрихом 12 6 при полной толщине', 'ghostOk', 1, 0],
             ['кривых, построенных по густой сетке', 'dense', 0, 0]],
  },
  {
    /* ⚠️ СНЯТАЯ ГАЛОЧКА САМА РАЗДВИГАЕТ ОКНО.
       Решение владельца 25.08: галочка «только первая четверть» управляет
       границами плоскости, значит раздвинуть границы — ровно её работа.
       Дважды подряд сделанное вне четверти оказывалось невидимым: центр
       поворота при процентном налоге и конец продолжения предельной кривой.

       Оба края правила: есть что показать — окно раздвигается с запасом;
       нечего — не трогается вовсе. */
    name: 'Приёмка · снятая галочка раздвигает окно до точек вне четверти',
    run: `var inView = function (Q, P) {
            var dq = CONFIG.Qmax - CONFIG.Qmin, dp = CONFIG.Pmax - CONFIG.Pmin;
            var mq = Math.min(Q - CONFIG.Qmin, CONFIG.Qmax - Q) / dq;
            var mp = Math.min(P - CONFIG.Pmin, CONFIG.Pmax - P) / dp;
            return (mq > 0.02 && mp > 0.02) ? 1 : 0;
          };
          // (1) пересечение вне четверти (−100; 200)
          resetSceneMemory(); pickScene('taxes');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-P');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), '0.5*p-200');
          setType('tax'); setTaxForm('unit'); setTax(0); redrawAll();
          setFirstQuad(false);
          var cross = inView(-100, 200);
          setFirstQuad(true);
          var backQ = (CONFIG.Qmin >= -1e-9 && CONFIG.Pmin >= -1e-9) ? 1 : 0;
          // (2) центр поворота при акцизе (−60; 0)
          resetSceneMemory(); pickScene('taxes');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '120-Q');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), '0.5*Q+30');
          setType('tax'); setTaxForm('excise'); setTax(25); redrawAll();
          setFirstQuad(false);
          var pivot = inView(-60, 0);
          setFirstQuad(true);
          // (3) конец продолжения MR (100; −100)
          resetSceneMemory(); pickScene('mono');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
          var mc = STATE.curves.find(function (c) { return c.role === 'mc'; });
          if (mc) updateCurveExpr(mc, '20');
          redrawAll(); setFirstQuad(false);
          var mr = inView(100, -100);
          setFirstQuad(true);
          // (4) показывать нечего — лишнего расширения нет
          resetSceneMemory(); pickScene('sd');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
          updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
          redrawAll();
          var wide = CONFIG.Qmax - CONFIG.Qmin;
          setFirstQuad(false);
          var quiet = (Math.abs(CONFIG.Qmin + wide * 0.25) < 1e-6
                       && Math.abs(CONFIG.Pmin + wide * 0.25) < 1e-6) ? 1 : 0;
          setFirstQuad(true);
          return { cross: cross, pivot: pivot, mr: mr, backQ: backQ, quiet: quiet };`,
    checks: [['пересечение (−100; 200) в кадре с запасом', 'cross', 1, 0],
             ['центр поворота (−60; 0) в кадре с запасом', 'pivot', 1, 0],
             ['конец продолжения MR (100; −100) в кадре с запасом', 'mr', 1, 0],
             ['обратное включение вернуло в первую четверть', 'backQ', 1, 0],
             ['показывать нечего — окно не раздвинуто', 'quiet', 1, 0]],
  },
  {
    /* ⚠️ СУММАРНАЯ КПВ — ЗАКРЫТАЯ ФОРМА ДЛЯ ЛЮБОГО ЧИСЛА ЛИНЕЙНЫХ КРИВЫХ.
       Было: закрытая форма только для ДВУХ кривых и обычным текстом; для
       трёх и больше панель писала «построена численно», хотя в сложении
       прямых ничего численного нет. Заодно численный детектор изломов давал
       (99,999; 60,001) там, где ответ ровно (100; 60).

       Числа образца владельца. Две КПВ y = 100 − x и y = 60 − 2x:
         Y = 160 − X при 0 ≤ X ≤ 100;  Y = 260 − 2X при 100 < X ≤ 130.
       Три (плюс y = 40 − 4x):
         200 − X, затем 300 − 2X, затем 560 − 4X до X = 140.
       ⚠️ 26.08 ЗДЕСЬ СТОЯЛО «дуга в наборе: ломаная НЕ выдумана», и проверка
       требовала, чтобы у набора с дугой аналитической записи не было ВОВСЕ.
       Это было ограничение движка, а не закон: с разворачиванием по равным
       альтернативным издержкам (ppfSumByEqualCost) закрытая форма у такого
       набора есть, и она честная. Правило, ради которого проверка писалась,
       осталось прежним и стало сильнее: запись набора с дугой НЕ имеет права
       состоять из одних прямых участков — в ней обязан стоять корень, и её
       значения обязаны совпасть с численной кривой. */
    name: 'Приёмка · суммарная КПВ: закрытая форма по участкам',
    run: `var take = function (exprs) {
            resetSceneMemory(); pickScene('ppfsum');
            STATE.ppfSumCount = exprs.length;
            exprs.forEach(function (e, i) { ppfSumSet(i, e); });
            STATE.ppfSumData = null;
            redrawAll(); ensurePpfSum(); redrawAll();
            var d = STATE.ppfSumData || {};
            return { tex: d.formulaTex || '', text: d.formulaText,
                     kinks: (d.kinks || []).map(function (k) { return k.join(';'); }).join(' '),
                     Xtot: d.Xtot, Ytot: d.Ytot };
          };
          var two = take(['100-x', '60-2x']);
          var three = take(['100-x', '60-2x', '40-4x']);
          var arc = take(['sqrt(10000-x^2)', '60-2x']);
          /* Значения записи против численного Минковского в трёх местах:
             начало, стык участков и конец. */
          var arcAt = null;
          if (arc.tex) {
            var cs = ['sqrt(10000-x^2)', '60-2x'].map(function (e) {
              return classifyPpf(parsePpfEquation('y = ' + e).f); });
            var g = ppfSumAnalytic(cs);
            arcAt = g ? [g.evalY(0), g.evalY(89.442719), g.evalY(130)] : null;
          }
          var has = function (tex, re) { return re.test(tex) ? 1 : 0; };
          return {
            two1: has(two.tex, /160 - X, & 0 \\\\le X \\\\le 100/),
            two2: has(two.tex, /260 - 2X, & 100 < X \\\\le 130/),
            twoKinks: two.kinks === '100;60' ? 1 : 0,
            twoX: two.Xtot, twoY: two.Ytot,
            three1: has(three.tex, /200 - X, & 0 \\\\le X \\\\le 100/),
            three2: has(three.tex, /300 - 2X, & 100 < X \\\\le 130/),
            three3: has(three.tex, /560 - 4X, & 130 < X \\\\le 140/),
            threeKinks: three.kinks === '100;100 130;40' ? 1 : 0,
            threeX: three.Xtot, threeY: three.Ytot,
            arcTex: arc.tex ? 1 : 0,
            arcSqrt: has(arc.tex, /\\\\sqrt/),
            arcStraightOnly: (arc.tex && !/\\\\sqrt/.test(arc.tex)) ? 1 : 0,
            arcY0: arcAt ? arcAt[0] : NaN,
            arcYmid: arcAt ? arcAt[1] : NaN,
            arcYend: arcAt ? arcAt[2] : NaN,
            arcX: arc.Xtot, arcYtot: arc.Ytot };`,
    checks: [['две КПВ: участок Y = 160 − X при 0 ≤ X ≤ 100', 'two1', 1, 0],
             ['две КПВ: участок Y = 260 − 2X при 100 < X ≤ 130', 'two2', 1, 0],
             ['две КПВ: излом ровно в (100; 60)', 'twoKinks', 1, 0],
             ['две КПВ: конец кривой X', 'twoX', 130, 1e-6],
             ['две КПВ: Y при нулевом X', 'twoY', 160, 1e-6],
             ['три КПВ: участок Y = 200 − X', 'three1', 1, 0],
             ['три КПВ: участок Y = 300 − 2X', 'three2', 1, 0],
             ['три КПВ: участок Y = 560 − 4X', 'three3', 1, 0],
             ['три КПВ: изломы (100; 100) и (130; 40)', 'threeKinks', 1, 0],
             ['три КПВ: конец кривой X', 'threeX', 140, 1e-6],
             ['три КПВ: Y при нулевом X', 'threeY', 200, 1e-6],
             ['дуга в наборе: закрытая форма есть', 'arcTex', 1, 0],
             ['дуга в наборе: в записи стоит корень', 'arcSqrt', 1, 0],
             ['дуга в наборе: ломаная НЕ выдумана', 'arcStraightOnly', 0, 0],
             ['дуга: Y при нулевом X', 'arcY0', 160, 1e-4],
             ['дуга: Y на стыке участков', 'arcYmid', 104.721360, 1e-3],
             ['дуга: Y на конце кривой', 'arcYend', 0, 1e-4],
             ['дуга: конец кривой X', 'arcX', 130, 1e-4]],
  },
  {
    /* ⚠️ ДВА КРАЯ У ЭТОГО ПРАВИЛА, И ОБА ЗДЕСЬ.
       Правило: путь суммарной кривой покрывает ВСЮ её область определения —
       и не обрывается на последнем изломе, и не тянется дальше записи.
       Дефект 26.08: узлами кусочной кривой были [lo, hi] плюс внутренние
       изломы, а правый конец области определения (у спроса Q = 160) в список
       не входил. Пока окно уже области, узел hi считался и линия рисовалась
       целиком; как только окно шире — hi давал NaN, точка становилась null, и
       путь кончался на изломе (40; 60) вместо (160; 0).
       Числа 160 и 180 — тот же ответ, названный для этого набора. */
    name: 'Сложение · путь суммарной кривой доходит до конца области определения',
    run: `resetSceneMemory(); pickScene('sdsum'); redrawAll();
          CONFIG.Qmin = 0; CONFIG.Qmax = 220; redrawAll();
          var last = function (side) {
            var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === side; });
            if (!c) return null;
            var el = document.querySelector('path[data-curve="' + c.id + '"][data-sum-part="real"]')
                  || document.querySelector('path[data-curve="' + c.id + '"]:not([data-sum-part])');
            if (!el) return null;
            var pts = [];
            String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
              var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
              if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
            });
            var p = pts[pts.length - 1] || null;
            return { q: p ? p[0] : NaN, v: p ? p[1] : NaN, n: pts.length,
                     domainTo: c.sumDomainTo || 0, breaks: (c.sumBreaks || []).slice() };
          };
          var D = last('D'), S = last('S');
          var offBreak = function (r) {
            if (!r) return 0;
            return r.breaks.every(function (b) { return Math.abs(r.q - b) > 1; }) ? 1 : 0;
          };
          var sCur = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === 'S'; });
          var sExpr = String(sCur && sCur.expr || '');
          return { dq: D ? D.q : NaN, dv: D ? D.v : NaN, dn: D ? D.n : NaN,
                   dDom: D ? D.domainTo : NaN, dOff: offBreak(D),
                   sq: S ? S.q : NaN, sv: S ? S.v : NaN,
                   /* Бесконечность через approx не проверить — переводим в
                      признак: 1, если верхней границы НЕТ. */
                   sOpen: (S && !isFinite(S.domainTo)) ? 1 : 0,
                   /* Служебный потолок цены давал в записи ровно 180. Его там
                      быть не должно ни в каком виде. */
                   sNo180: /(^|[^\\d.])180([^\\d.]|$)/.test(sExpr) ? 0 : 1,
                   sOff: offBreak(S),
                   winTo: CONFIG.Qmax,
                   eqQ: STATE.eq ? STATE.eq.Q : NaN, cs: STATE.cs, ps: STATE.ps };`,
    /* Допуск пиксельный: точки читаются с атрибута d и переводятся обратно в
       координаты модели, то есть через округление до пикселя. */
    checks: [['спрос: правый конец области определения', 'dDom', 160, 1e-6],
             ['спрос: путь доходит до Q = 160', 'dq', 160, 0.35],
             ['спрос: и приходит на ось цен', 'dv', 0, 0.35],
             ['спрос: путь НЕ обрывается на изломе', 'dOff', 1, 0],
             ['спрос: точек в пути единицы, а не сотни', 'dn', 3, 2],
             /* ⚠️ У ПРЕДЛОЖЕНИЯ ВЕРХНЕЙ ГРАНИЦЫ НЕТ ВОВСЕ (приёмка 31.08).
                До 31.08 здесь стояли числа 180 — и это была ОШИБКА проверки,
                а не правило: 180 получалось из служебного потолка цены
                sumPriceTop (для S₁ = Q, S₂ = Q + 20 он равен 100, а при
                P = 100 объём как раз 180). Потолок — подпорка для перебора
                участков, а не конец рынка: выше него ни одна новая группа
                войти не может, набор торгующих постоянен, и последний участок
                тянется сколь угодно далеко. Поэтому линия обязана доходить до
                КРАЯ КАДРА при любом отдалении, а числа 180 в записи быть не
                должно. У спроса всё иначе, и там 160 осталось: это настоящая
                граница, все группы исчерпаны при P = 0. */
             ['предложение: верхней границы области НЕТ', 'sOpen', 1, 0],
             ['предложение: числа 180 в записи нет', 'sNo180', 1, 0],
             ['предложение: путь доходит до края кадра', 'sq', 220, 0.5],
             ['край кадра там, где его поставили', 'winTo', 220, 1e-9],
             ['предложение: путь НЕ обрывается на изломе', 'sOff', 1, 0],
             ['равновесие не сдвинулось', 'eqQ', 70, 1e-4],
             ['CS не сдвинулся', 'cs', 1625, 1e-3],
             ['PS не сдвинулся', 'ps', 1325, 1e-3]],
  },
  {
    /* Правило: одна и та же запись выглядит ОДИНАКОВО в поле, в подсказке и в
       блоке «Итоговая функция» — потому что переводчик у них один
       (mathToLatexField). Дефект 26.08: tipExpr звал mathToTex напрямую, и
       подсказка печатала вывод Math.js — `if`/`otherwise` по-английски, связку
       `∧` вместо двойного неравенства и служебный хвост NaN как `∞`.
       ⚠️ Проверяем ОБА края: и что дурного нет, и что нужное есть. Проверка
       «нет английского if» одна покраснеть не может: пустая строка её тоже
       проходит. */
    name: 'Подсказка кривой · кусочная запись набрана общим переводчиком',
    run: `resetSceneMemory(); pickScene('sdsum'); redrawAll();
          var c = STATE.curves.find(function (x) { return x.kind === 'sum' && x.sumGroup === 'D'; });
          var t = tipExpr(c.expr);
          var f = mathToLatexField(c.expr);
          var box = document.createElement('div');
          box.style.cssText = 'position:absolute;left:-9999px;top:0';
          box.textContent = t; document.body.appendChild(box);
          renderMathIn(box);
          var cl = box.cloneNode(true);
          cl.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
          var shown = cl.textContent.replace(/\\s+/g, ' ');
          box.remove();
          return { hasIf: /\\bif\\b/.test(t) ? 1 : 0,
                   hasOther: /otherwise/.test(t) ? 1 : 0,
                   hasWedge: /wedge|∧/.test(t) ? 1 : 0,
                   hasInf: /infty|∞/.test(t) ? 1 : 0,
                   hasRu: /\\\\text\\{если \\}/.test(t) ? 1 : 0,
                   sameAsField: (t === '$' + f + '$') ? 1 : 0,
                   cases: /begin\\{cases\\}/.test(t) ? 1 : 0,
                   shownLo: /если 0\\s*≤\\s*Q\\s*<\\s*40/.test(shown) ? 1 : 0,
                   shownHi: /если 40\\s*≤\\s*Q\\s*≤\\s*160/.test(shown) ? 1 : 0 };`,
    checks: [['английского «if» в подсказке нет', 'hasIf', 0, 0],
             ['английского «otherwise» нет', 'hasOther', 0, 0],
             ['связки ∧ нет', 'hasWedge', 0, 0],
             ['служебного ∞ нет', 'hasInf', 0, 0],
             ['«если» по-русски есть', 'hasRu', 1, 0],
             ['запись набрана фигурной скобкой', 'cases', 1, 0],
             ['на экране видно «если 0 ≤ Q < 40»', 'shownLo', 1, 0],
             ['на экране видно «если 40 ≤ Q ≤ 160»', 'shownHi', 1, 0],
             ['подсказка совпала с записью поля', 'sameAsField', 1, 0]],
  },
  {
    /* Правило: сторона вмешательства меняет ТОЛЬКО нарисованную кривую, а
       числа обязаны совпасть до разряда. Дефект 26.08: у субсидии сторона не
       читалась вовсе (условие было ограничено налогом), и «Субсидию получает:
       Покупатель» не меняло на графике ничего.
       Второй край того же правила — ЗНАК: у субсидии покупателю эффективный
       спрос ПОДНИМАЕТСЯ (D + s из точки (0; 120)), а не опускается. */
    name: 'Вмешательство · субсидия покупателю двигает кривую спроса',
    run: `var snap = function (side) {
            resetSceneMemory(); pickScene('taxes');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
            updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), 'Q');
            setType('subsidy'); setTaxForm('unit'); setTaxSide(side); setTax(20);
            redrawAll();
            var el = document.querySelector('path[stroke-dasharray="6 4"]');
            var at0 = NaN;
            if (el) {
              var m = String(el.getAttribute('d') || '').match(/M\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
              if (m) at0 = sy.invert(+m[2]);
            }
            var names = [];
            document.querySelectorAll('text.curve-name').forEach(function (t) {
              var c = t.cloneNode(true);
              c.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
              names.push(c.textContent.replace(/\\s+/g, ' ').trim());
            });
            var hint = document.getElementById('tax-hint');
            var ht = hint ? hint.textContent.replace(/\\s+/g, ' ') : '';
            var te = STATE.taxEq;
            return { stroke: el ? el.getAttribute('stroke') : '', at0: at0, names: names,
                     dcol: STATE.D.color, scol: STATE.S.color,
                     Q: te ? te.Q : NaN, Pb: te ? te.Pb : NaN, Ps: te ? te.Ps : NaN,
                     budget: STATE.budget, dwl: STATE.dwl,
                     saysD: /кривая спроса/.test(ht) ? 1 : 0,
                     saysS: /кривая предложения/.test(ht) ? 1 : 0 };
          };
          var sel = snap('seller'), buy = snap('buyer');
          return { selIsS: (sel.stroke === sel.scol) ? 1 : 0,
                   buyIsD: (buy.stroke === buy.dcol) ? 1 : 0,
                   selAt0: sel.at0, buyAt0: buy.at0,
                   selName: sel.names.indexOf('S − s') >= 0 ? 1 : 0,
                   buyName: buy.names.indexOf('D + s') >= 0 ? 1 : 0,
                   selQ: sel.Q, buyQ: buy.Q, selPb: sel.Pb, buyPb: buy.Pb,
                   selPs: sel.Ps, buyPs: buy.Ps,
                   selBud: sel.budget, buyBud: buy.budget,
                   selDwl: sel.dwl, buyDwl: buy.dwl,
                   hintSel: (sel.saysS && !sel.saysD) ? 1 : 0,
                   hintBuy: (buy.saysD && !buy.saysS) ? 1 : 0 };`,
    checks: [['у продавца сдвинута кривая предложения', 'selIsS', 1, 0],
             ['у покупателя сдвинута кривая СПРОСА', 'buyIsD', 1, 0],
             ['S − s выходит из (0; −20)', 'selAt0', -20, 1e-6],
             ['D + s выходит из (0; 120)', 'buyAt0', 120, 1e-6],
             ['имя сдвинутой кривой у продавца', 'selName', 1, 0],
             ['имя сдвинутой кривой у покупателя', 'buyName', 1, 0],
             ['объём у продавца', 'selQ', 60, 1e-4],
             ['объём у покупателя тот же', 'buyQ', 60, 1e-4],
             ['цена покупателя у продавца', 'selPb', 40, 1e-4],
             ['цена покупателя у покупателя та же', 'buyPb', 40, 1e-4],
             ['цена продавца у продавца', 'selPs', 60, 1e-4],
             ['цена продавца у покупателя та же', 'buyPs', 60, 1e-4],
             ['расход у продавца', 'selBud', -1200, 1e-3],
             ['расход у покупателя тот же', 'buyBud', -1200, 1e-3],
             ['DWL у продавца', 'selDwl', 100, 1e-3],
             ['DWL у покупателя тот же', 'buyDwl', 100, 1e-3],
             ['подсказка у продавца называет S', 'hintSel', 1, 0],
             ['подсказка у покупателя называет D', 'hintBuy', 1, 0]],
  },
  {
    /* СМЕШАННАЯ ПАРА КПВ (решение владельца 31.08): у одной кривой издержки
       растут, у другой убывают. Раньше такой набор получал честный отказ.
       ⚠️ ГЛАВНОЕ ЗДЕСЬ — КАНДИДАТ (5), внутреннее решение по равным издержкам.
       «В смешанном случае оптимум всегда в углу» — неправда: вторая производная
       суммы равна f₁'' + f₂'' и при вогнутой f₁ с выпуклой f₂ бывает
       отрицательной. Проверка это стережёт числом: огибающая по одним УГЛАМ
       даёт при X = 5 ровно 99,00, а верный ответ 99,07. Разница 0,07 обязана
       ловиться, поэтому рядом с ответом считается и угловой вариант.
       ⚠️ Сверка с численным Минковским обязательна и здесь. */
    name: 'Сложение КПВ · смешанная пара и параметрическая запись',
    run: `resetSceneMemory(); pickScene('ppfsum');
          STATE.ppfSumCount = 2;
          ppfSumSet(0, 'y = 100 - x^2'); ppfSumSet(1, 'y = 20 - 10*sqrt(x)');
          if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
          recomputePpfSum(); redrawAll();
          var d = STATE.ppfSumData || {};
          var r1 = compileFormula('100 - x^2'), r2 = compileFormula('20 - 10*sqrt(x)');
          var f1 = function (x) { return ppfEvalWith(r1.compiled, x); };
          var f2 = function (x) { return ppfEvalWith(r2.compiled, x); };
          var cs = [classifyPpf(f1), classifyPpf(f2)];
          var rec = ppfSumMixedPair(cs);
          var worst = 0;
          for (var i = 0; i <= 200; i++) {
            var X = 14 * i / 200;
            var a = rec ? rec.evalY(X) : NaN, b = maxAllocY(f1, f2, X, 10, 4);
            if (isFinite(a) && isFinite(b)) worst = Math.max(worst, Math.abs(a - b));
          }
          var gap = 0;
          if (rec) (rec.kinks || []).forEach(function (k) {
            var e = 1e-7, u = rec.evalY(k.x - e), v = rec.evalY(k.x + e);
            if (isFinite(u) && isFinite(v)) gap = Math.max(gap, Math.abs(u - v));
          });
          // Ответ по одним углам — без кандидата (5).
          var F1 = ppfFam(cs[0]), F2 = ppfFam(cs[1]);
          var X1 = F1.Xmax(cs[0]), X2 = F2.Xmax(cs[1]);
          var corner = function (X) {
            var v = [];
            if (X <= X2) v.push(F1.Ymax(cs[0]) + F2.f(cs[1], X));
            if (X <= X1) v.push(F2.Ymax(cs[1]) + F1.f(cs[0], X));
            if (X >= X1) v.push(F2.f(cs[1], X - X1));
            if (X >= X2) v.push(F1.f(cs[0], X - X2));
            return Math.max.apply(null, v.filter(isFinite));
          };
          var tex = String(d.formulaTex || '');
          // Три кривые смешанного набора остаются численными (пункт 7.4).
          resetSceneMemory(); pickScene('ppfsum');
          STATE.ppfSumCount = 3;
          ppfSumSet(0, 'y = 100 - x^2'); ppfSumSet(1, 'y = 20 - 10*sqrt(x)'); ppfSumSet(2, 'y = 50 - 5*x');
          if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
          recomputePpfSum(); redrawAll();
          var d3 = STATE.ppfSumData || {};
          return {
            mixed: (ppfCostOf(cs[0]) === 'up' && ppfCostOf(cs[1]) === 'down') ? 1 : 0,
            hasRec: tex ? 1 : 0,
            hasParam: (rec && rec.pieces.some(function (p) { return p.kind === 'param'; })) ? 1 : 0,
            hasXlam: tex.indexOf('X(\\\\lambda)') >= 0 ? 1 : 0,
            hasYlam: tex.indexOf('Y(\\\\lambda)') >= 0 ? 1 : 0,
            nPieces: rec ? rec.pieces.length : 0,
            Xtot: d.Xtot, Ytot: d.Ytot,
            at5: rec ? rec.evalY(5) : NaN,
            corner5: corner(5),
            numAt5: maxAllocY(f1, f2, 5, 10, 4),
            worst: worst,
            gapRel: gap / (d.Ytot || 1),
            /* Записи для поля ввода у параметрической формы нет, и придумывать
               её нельзя: λ поле не понимает. */
            noExpr: d.formulaExpr ? 0 : 1,
            note: String(d.formulaNote || '').indexOf('альтернативные издержки единицы') >= 0 ? 1 : 0,
            threeNumeric: String(d3.formulaTex || '') ? 0 : 1,
            threeWhy: String(d3.formulaText || '').length > 30 ? 1 : 0 };`,
    checks: [['пара смешанная: растут + убывают', 'mixed', 1, 0],
             ['аналитическая запись есть (отказа нет)', 'hasRec', 1, 0],
             ['участков три', 'nPieces', 3, 0],
             ['среди участков есть параметрический', 'hasParam', 1, 0],
             ['в записи есть X(λ)', 'hasXlam', 1, 0],
             ['в записи есть Y(λ)', 'hasYlam', 1, 0],
             ['конец по X', 'Xtot', 14, 1e-4],
             ['конец по Y', 'Ytot', 120, 1e-6],
             ['ответ при X = 5 — внутреннее решение', 'at5', 99.0746, 1e-3],
             ['он же численным Минковским', 'numAt5', 99.0746, 1e-3],
             ['по одним углам вышло бы ровно 99', 'corner5', 99, 1e-6],
             ['сверка с Минковским в 200 точках', 'worst', 0, 1e-6],
             ['разрыв в узлах относительно Ymax', 'gapRel', 0, 1e-7],
             ['записи для поля ввода нет', 'noExpr', 1, 0],
             ['словами сказано, что такое λ', 'note', 1, 0],
             ['три кривые: аналитики нет', 'threeNumeric', 1, 0],
             ['три кривые: причина названа', 'threeWhy', 1, 0]],
  },
  {
    /* НОВЫЕ СЕМЕЙСТВА КРИВЫХ КПВ (приёмка 31.08): общий многочлен второй
       степени и общая степенная. Оба добавлены СТРОКОЙ в таблицу PPF_FAMILIES,
       а не ветками по файлу.
       ⚠️ ПОРЯДОК РАСПОЗНАВАТЕЛЕЙ ОХРАНЯЕТСЯ ЗДЕСЬ ЖЕ. Многочлен поглощает
       параболу (c₁ = 0), степенная — и параболу (k = 2), и выпуклую (k = 0,5).
       У парабол и выпуклых приняты СВОИ контрольные числа, поэтому они обязаны
       распознаваться первыми: проверка ловит и это.
       ⚠️ ТИП ИЗДЕРЖЕК ЧИТАЕТСЯ ПО ЗНАКУ c₂ И ПО k, а не меряется численно. */
    name: 'Сложение КПВ · общий многочлен и степенная как новые семейства',
    run: `var cls = function (e) {
            var r = compileFormula(e);
            var f = function (x) { return ppfEvalWith(r.compiled, x); };
            return classifyPpf(f);
          };
          var sum = function (a, b) {
            resetSceneMemory(); pickScene('ppfsum');
            STATE.ppfSumCount = 2; ppfSumSet(0, 'y = ' + a); ppfSumSet(1, 'y = ' + b);
            if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
            recomputePpfSum(); redrawAll();
            var d = STATE.ppfSumData || {};
            return { tex: String(d.formulaTex || ''), Xtot: d.Xtot, Ytot: d.Ytot,
                     kinks: d.kinks || [] };
          };
          var p = cls('100 - 20*x + x^2');       // многочлен, издержки УБЫВАЮТ
          var w = cls('64 - x^3');               // степенная, k = 3, издержки растут
          var par = cls('16 - x^2');             // обязана остаться параболой
          var cvx = cls('60 - 20*sqrt(x)');      // обязана остаться выпуклой
          var A = sum('100 - 20*x + x^2', '50 - 5*x');
          var B = sum('64 - x^3', '30 - 12*x');
          var kx = function (o, i) { return (o.kinks[i] || [])[0]; };
          var ky = function (o, i) { return (o.kinks[i] || [])[1]; };
          return {
            pIsPoly: (p.type === 'poly2') ? 1 : 0, pCost: (ppfCostOf(p) === 'down') ? 1 : 0,
            pXmax: p.Xmax, pYmax: p.Ymax, pC1: p.c1, pC2: p.c2,
            wIsPow: (w.type === 'power') ? 1 : 0, wCost: (ppfCostOf(w) === 'up') ? 1 : 0,
            wK: w.k, wXmax: w.Xmax, wYmax: w.Ymax,
            /* Порядок распознавателей: старые формы новые семейства не съели. */
            parStill: (par.type === 'parabola') ? 1 : 0,
            cvxStill: (cvx.type === 'convex') ? 1 : 0,
            /* Многочлен + прямая. */
            aP1: (A.tex.indexOf('150 - 5X, & 0 \\\\le X \\\\le 10') >= 0) ? 1 : 0,
            aP2: (A.tex.indexOf('X^2 - 40X + 400, & 10 < X \\\\le 15') >= 0) ? 1 : 0,
            aP3: (A.tex.indexOf('100 - 5X, & 15 < X \\\\le 20') >= 0) ? 1 : 0,
            aXtot: A.Xtot, aYtot: A.Ytot,
            aK1x: kx(A, 0), aK1y: ky(A, 0), aK2x: kx(A, 1), aK2y: ky(A, 1),
            /* Степенная + прямая. */
            bP1: (B.tex.indexOf('94 - X^{3}, & 0 \\\\le X \\\\le 2') >= 0) ? 1 : 0,
            bP2: (B.tex.indexOf('110 - 12X, & 2 < X \\\\le 4,5') >= 0) ? 1 : 0,
            bP3: (B.tex.indexOf('64 - (X - 2,5)^{3}, & 4,5 < X \\\\le 6,5') >= 0) ? 1 : 0,
            bXtot: B.Xtot, bYtot: B.Ytot,
            bK1x: kx(B, 0), bK1y: ky(B, 0), bK2x: kx(B, 1), bK2y: ky(B, 1) };`,
    checks: [['многочлен опознан', 'pIsPoly', 1, 0],
             ['у многочлена издержки УБЫВАЮТ (c₂ > 0)', 'pCost', 1, 0],
             ['многочлен: Xmax', 'pXmax', 10, 1e-6],
             ['многочлен: Ymax', 'pYmax', 100, 1e-9],
             ['многочлен: c₁', 'pC1', -20, 1e-6],
             ['многочлен: c₂', 'pC2', 1, 1e-6],
             ['степенная опознана', 'wIsPow', 1, 0],
             ['у степенной издержки растут (k > 1)', 'wCost', 1, 0],
             ['степенная: k', 'wK', 3, 1e-6],
             ['степенная: Xmax', 'wXmax', 4, 1e-6],
             ['степенная: Ymax', 'wYmax', 64, 1e-9],
             ['парабола ОСТАЛАСЬ параболой', 'parStill', 1, 0],
             ['выпуклая ОСТАЛАСЬ выпуклой', 'cvxStill', 1, 0],
             ['многочлен+прямая: участок 1', 'aP1', 1, 0],
             ['многочлен+прямая: участок 2', 'aP2', 1, 0],
             ['многочлен+прямая: участок 3', 'aP3', 1, 0],
             ['многочлен+прямая: конец по X', 'aXtot', 20, 1e-6],
             ['многочлен+прямая: конец по Y', 'aYtot', 150, 1e-6],
             ['многочлен+прямая: узел 1 X', 'aK1x', 10, 1e-6],
             ['многочлен+прямая: узел 1 Y', 'aK1y', 100, 1e-6],
             ['многочлен+прямая: узел 2 X', 'aK2x', 15, 1e-6],
             ['многочлен+прямая: узел 2 Y', 'aK2y', 25, 1e-6],
             ['степенная+прямая: участок 1', 'bP1', 1, 0],
             ['степенная+прямая: участок 2', 'bP2', 1, 0],
             ['степенная+прямая: участок 3', 'bP3', 1, 0],
             ['степенная+прямая: конец по X', 'bXtot', 6.5, 1e-6],
             ['степенная+прямая: конец по Y', 'bYtot', 94, 1e-6],
             ['степенная+прямая: узел 1 X', 'bK1x', 2, 1e-6],
             ['степенная+прямая: узел 1 Y', 'bK1y', 86, 1e-6],
             ['степенная+прямая: узел 2 X', 'bK2x', 4.5, 1e-6],
             ['степенная+прямая: узел 2 Y', 'bK2y', 56, 1e-6]],
  },
  {
    /* ⚠️ ДВА КРАЯ У ЭТОГО ПРАВИЛА, И ОБА ЗДЕСЬ.
       Квота ограничивает выпуск СВЕРХУ: связывает только ниже монопольного
       выпуска, а выше — не должна менять ничего. До 31.08 в монополии не
       работало НИ ТО, НИ ДРУГОЕ: каскад вмешательства разбирал налог, потолок
       и пол, а «квота» не совпадала ни с одним, и ветка не исполнялась вовсе.
       ⚠️ КОРИДОРА ЦЕН В МОНОПОЛИИ НЕТ. На конкурентном рынке цена при квоте
       лежит где-то между S(Qk) и D(Qk), потому что назначать её некому; у
       монополиста есть рыночная власть, и он берёт ВЕРХНИЙ край, P = D(Qk).
       Проверяем и это: ползунка цены внутри коридора здесь быть не должно. */
    name: 'Приёмка · квота в монополии связывает и коридора цен не заводит',
    run: `var look = function (qk) {
            resetSceneMemory(); pickScene('mono'); redrawAll();
            if (qk != null) { setType('quota'); setQuota(qk); redrawAll(); }
            var m = STATE.mono || {}, q = STATE.monoQuota;
            var corridor = document.getElementById('quota-price-field');
            return { Qm: m.Qm, Pm: m.Pm, psM: m.psM, csM: m.csM, dwl: m.dwl,
                     has: q ? 1 : 0, bind: (q && q.binding) ? 1 : 0,
                     Q: q ? q.Q : null, P: q ? q.price : null,
                     PS: q ? q.psM : null, CS: q ? q.csM : null, DWL: q ? q.dwl : null,
                     corr: (corridor && (corridor.offsetParent || corridor.getClientRects().length)) ? 1 : 0 };
          };
          var base = look(null), a = look(60), b = look(40), c = look(20);
          return { bQm: base.Qm, bPm: base.Pm, bPS: base.psM, bCS: base.csM, bDWL: base.dwl,
                   /* Квота ВЫШЕ выпуска и РОВНО выпуск — не связывают. */
                   a_has: a.has, a_bind: a.bind, a_Qm: a.Qm, a_Pm: a.Pm,
                   b_bind: b.bind, b_Qm: b.Qm, b_Pm: b.Pm,
                   /* Квота НИЖЕ выпуска — связывает. */
                   c_bind: c.bind, c_Q: c.Q, c_P: c.P, c_PS: c.PS, c_CS: c.CS, c_DWL: c.DWL,
                   /* Квота монополисту невыгодна: излишек падает, потери растут. */
                   psDown: (c.PS < base.psM - 1e-6) ? 1 : 0,
                   dwlUp: (c.DWL > base.dwl + 1e-6) ? 1 : 0,
                   corr: c.corr };`,
    checks: [['без квоты: Qm', 'bQm', 40, 1e-6],
             ['без квоты: Pm', 'bPm', 60, 1e-6],
             ['без квоты: PS', 'bPS', 1600, 1e-3],
             ['без квоты: DWL', 'bDWL', 800, 1e-3],
             ['квота 60: расчёт выполнен', 'a_has', 1, 0],
             ['квота 60: не связывает', 'a_bind', 0, 0],
             ['квота 60: выпуск не сдвинулся', 'a_Qm', 40, 1e-6],
             ['квота 60: цена не сдвинулась', 'a_Pm', 60, 1e-6],
             ['квота 40 (ровно выпуск): не связывает', 'b_bind', 0, 0],
             ['квота 40: выпуск не сдвинулся', 'b_Qm', 40, 1e-6],
             ['квота 20: связывает', 'c_bind', 1, 0],
             ['квота 20: выпуск', 'c_Q', 20, 1e-6],
             ['квота 20: цена = D(Qk), верхний край', 'c_P', 80, 1e-6],
             ['квота 20: PS', 'c_PS', 1200, 1e-3],
             ['квота 20: CS', 'c_CS', 200, 1e-3],
             ['квота 20: DWL', 'c_DWL', 1800, 1e-3],
             ['излишек монополиста УПАЛ', 'psDown', 1, 0],
             ['потери общества ВЫРОСЛИ', 'dwlUp', 1, 0],
             ['ползунка цены внутри коридора НЕТ', 'corr', 0, 0]],
  },
  {
    /* ⚠️ ДВА КРАЯ У ЭТОГО ПРАВИЛА, И ОБА ЗДЕСЬ.
       Владелец убрал 31.08 абзац «Почему кривые нельзя просто сложить по
       вертикали» вместе с формулой Минковского: карточка отвечает на вопрос
       «как это получилось», а не «как это НЕ получилось».
       Проверка «абзаца нет» ОДНА покраснеть не может: пустая карточка её тоже
       пройдёт, и удаление всего разбора осталось бы незамеченным. Поэтому
       рядом стоит второй край — карточка на месте и остальные абзацы в ней. */
    name: 'Приёмка · врезки про вертикальное сложение нет, а разбор не опустел',
    /* ⚠️ ПРОВЕРКА СМОТРИТ И В ИСХОДНИКИ, А НЕ ТОЛЬКО НА ЭКРАН.
       Указание владельца — убрать врезку ВЕЗДЕ, а на экране за один прогон
       видна одна сцена. Первая версия проверки читала только панель сцены
       «Сложение КПВ», и проверка зубастости это поймала: врезка, возвращённая
       в СОСЕДНЮЮ сцену (обычная КПВ), проходила мимо неё незамеченной.
       Поэтому текст ищется ещё и в самих файлах calc2: их адреса известны
       странице, и скачать их дешевле, чем обойти сорок четыре сцены. */
    run: `resetSceneMemory(); pickScene('ppfsum'); redrawAll();
          document.querySelectorAll('.fold-btn').forEach(function (b) {
            if (b.getAttribute('aria-expanded') !== 'true') b.click();
          });
          redrawAll();
          /* Врезки .sb-note переезжают в «Объяснение модели», поэтому смотрим
             и туда, и в саму панель — одним текстом. */
          var parts = ['info-ppfsum', 'ex-body', 'sb-body'].map(function (id) {
            var e = document.getElementById(id);
            return e ? e.textContent : '';
          }).join(' ').replace(/\s+/g, ' ');
          var note = document.querySelector('#ex-body .sb-note, #info-ppfsum .sb-note');
          var noteLen = note ? note.textContent.replace(/\s+/g, ' ').trim().length : 0;
          /* Исходники калькулятора: ищем текст врезки во всех файлах сразу. */
          var srcs = Array.prototype.map.call(document.querySelectorAll('script[src]'),
            function (t) { return t.src; }).filter(function (u) { return u.indexOf('/calc2/') >= 0; });
          var joined = '';
          for (var i = 0; i < srcs.length; i++) {
            try { joined += await (await fetch(srcs[i])).text(); } catch (e) { joined += ''; }
          }
          var inSrc = (joined.indexOf('сложить по вертикали') >= 0
                       || joined.indexOf('Вертикальная сумма') >= 0) ? 1 : 0;
          return {
            srcFiles: srcs.length,
            noVertSrc: inSrc ? 0 : 1,
            noVert: parts.indexOf('сложить по вертикали') < 0 ? 1 : 0,
            noVertSum: parts.indexOf('Вертикальная сумма') < 0 ? 1 : 0,
            noMink: parts.indexOf('Минковск') < 0 ? 1 : 0,
            /* Второй край: разбор существует и в нём остались нужные абзацы. */
            hasNote: note ? 1 : 0,
            /* Порог, а не размер: правило — «разбор не опустел», и привязывать
               его к точной длине текста значило бы краснеть от каждой правки
               формулировки. 400 символов это примерно два абзаца из четырёх. */
            noteLong: noteLen > 400 ? 1 : 0,
            hasEnds: parts.indexOf('Концы суммарной кривой') >= 0 ? 1 : 0,
            hasKink: (parts.indexOf('Излом появляется') >= 0
                      || parts.indexOf('Изломов нет') >= 0) ? 1 : 0,
            hasWhere: parts.indexOf('Саму запись суммарной кривой') >= 0 ? 1 : 0 };`,
    checks: [['абзаца «сложить по вертикали» нет на экране', 'noVert', 1, 0],
             /* ⚠️ ВТОРОЙ КРАЙ — ИСХОДНИКИ. Экран за один прогон показывает одну
                сцену, а убрать врезку велено ВЕЗДЕ. Проверка зубастости это и
                поймала: врезка, возвращённая в соседнюю сцену, проходила мимо
                экранной проверки незамеченной. */
             ['файлы calc2 прочитаны', 'srcFiles', 22, 8],
             ['текста нет и в исходниках calc2', 'noVertSrc', 1, 0],
             ['слов «Вертикальная сумма» нет', 'noVertSum', 1, 0],
             ['формулы Минковского нет', 'noMink', 1, 0],
             ['разбор «Как это получилось» на месте', 'hasNote', 1, 0],
             ['разбор не опустел', 'noteLong', 1, 0],
             ['абзац про концы кривой остался', 'hasEnds', 1, 0],
             ['абзац про изломы остался', 'hasKink', 1, 0],
             ['абзац «где искать запись» остался', 'hasWhere', 1, 0]],
  },
  {
    /* Правило: аналитическая запись кривой — ВЕЛИЧИНА, и живёт она первой
       карточкой «Ключевых значений», а не во врезке разбора. Держится это тем,
       что внутри блока нет ни одного узла с классом `sb-note`: общий проход
       moveExplanations уносит такие врезки в «Объяснение модели».
       ⚠️ Проверяем и второй край: запись действительно набрана (в блоке есть
       .katex), иначе пустой блок прошёл бы проверку «в разборе его нет». */
    name: 'Итоговая функция · первым блоком в «Ключевых значениях», не в разборе',
    run: `var look = function (k, setup) {
            resetSceneMemory(); pickScene(k);
            if (setup) (new Function(setup))();
            redrawAll();
            document.querySelectorAll('.fold-btn').forEach(function (b) {
              if (b.getAttribute('aria-expanded') !== 'true') b.click();
            });
            var sb = document.getElementById('sb-body');
            var ff = document.getElementById('info-final');
            var ex = document.getElementById('ex-body');
            var first = null;
            if (sb) {
              for (var i = 0; i < sb.children.length; i++) {
                var e = sb.children[i];
                if (e.textContent.replace(/\\s+/g, '').length) { first = e.id || e.className; break; }
              }
            }
            var txt = ff ? ff.textContent : '';
            return { has: ff && ff.querySelectorAll('.ff').length ? 1 : 0,
                     math: ff && ff.querySelectorAll('.ff-math .katex').length ? 1 : 0,
                     notes: ff ? ff.querySelectorAll('.sb-note, .sb-note-src').length : -1,
                     first: (first === 'info-final') ? 1 : 0,
                     /* ⚠️ ИЩЕМ САМ БЛОК, А НЕ СЛОВА. Первая версия проверки
                        искала в разборе строку «Итоговая функция» — и краснела
                        на честном тексте разбора, где сказано, где эту запись
                        искать. Правило про УЗЕЛ: блока с классом ff в
                        «Объяснении модели» быть не должно ни одного. */
                     inExplain: (ex ? ex.querySelectorAll('.ff').length : 0),
                     copy: ff && ff.querySelectorAll('.ff-copy[data-ff-expr]').length ? 1 : 0 };
          };
          var a = look('sdsum', '');
          var b = look('ppfsum', "STATE.ppfSumCount=2; ppfSumSet(0,'y = 100 - x'); ppfSumSet(1,'y = 60 - 3*x');"
                       + " if (typeof renderPpfSumRows === 'function') renderPpfSumRows(); recomputePpfSum();");
          var c = look('taxes', "setType('tax'); setTaxForm('unit'); setTax(20);");
          return { aHas: a.has, aMath: a.math, aNotes: a.notes, aFirst: a.first, aEx: a.inExplain, aCopy: a.copy,
                   bHas: b.has, bMath: b.math, bNotes: b.notes, bFirst: b.first, bEx: b.inExplain,
                   cHas: c.has, cMath: c.math, cNotes: c.notes, cFirst: c.first, cEx: c.inExplain };`,
    checks: [['сложение: блок есть', 'aHas', 1, 0],
             ['сложение: запись набрана математикой', 'aMath', 1, 0],
             ['сложение: внутри блока нет .sb-note', 'aNotes', 0, 0],
             ['сложение: блок стоит ПЕРВЫМ в табло', 'aFirst', 1, 0],
             ['сложение: блок НЕ уехал в разбор', 'aEx', 0, 0],
             ['сложение: кнопка «копировать» несёт запись', 'aCopy', 1, 0],
             ['КПВ: блок есть', 'bHas', 1, 0],
             ['КПВ: запись набрана математикой', 'bMath', 1, 0],
             ['КПВ: внутри блока нет .sb-note', 'bNotes', 0, 0],
             ['КПВ: блок стоит ПЕРВЫМ в табло', 'bFirst', 1, 0],
             ['КПВ: блок НЕ уехал в разбор', 'bEx', 0, 0],
             ['налог: блок есть', 'cHas', 1, 0],
             ['налог: запись набрана математикой', 'cMath', 1, 0],
             ['налог: внутри блока нет .sb-note', 'cNotes', 0, 0],
             ['налог: блок стоит ПЕРВЫМ в табло', 'cFirst', 1, 0],
             ['налог: блок НЕ уехал в разбор', 'cEx', 0, 0]],
  },
  {
    /* Сложение КПВ по равным альтернативным издержкам (учебник Бахарева,
       с. 181–191). Контрольные числа владельца: (а) с. 185–187, (б) две
       параболы, (в) линейные — НЕ СДВИГАТЬ, (г) с. 182–184.
       ⚠️ Проверяем ЗНАЧЕНИЯ функции, а не строку записи: одна и та же функция
       записывается по-разному (16 − (X − 5)² и −9 + 10X − X² — это одно и то
       же), и требовать буквального совпадения строки значило бы стеречь
       отпечаток реализации вместо правила. */
    name: 'Сложение КПВ · закрытая форма по равным альт. издержкам, наборы (а)–(г)',
    run: `var take = function (exprs) {
            var cs = exprs.map(function (e) { return classifyPpf(parsePpfEquation(e).f); });
            var g = ppfSumAnalytic(cs);
            return g ? function (x) { var v = g.evalY(x); return isNaN(v) ? null : Math.round(v * 1e6) / 1e6; } : null;
          };
          var A = take(['y = 20 - 4*x', 'y = 16 - x^2']);
          var B = take(['y = 16 - x^2', 'y = 36 - 4*x^2']);
          var V = take(['y = 100 - x', 'y = 60 - 2*x']);
          var V3 = take(['y = 100 - x', 'y = 60 - 2*x', 'y = 40 - 4*x']);
          var G = take(['y = 5 - 0.625*x', 'y = 8 - 2*x']);
          var D = take(['y = sqrt(100 - x^2)', 'y = sqrt(64 - x^2)']);
          var Z = take(['y = 16 - x^2', 'y = sqrt(64 - x^2)']);
          return { aOk: A ? 1 : 0, a0: A ? A(0) : NaN, a2: A ? A(2) : NaN, a5: A ? A(5) : NaN,
                   a7: A ? A(7) : NaN, a8: A ? A(8) : NaN, a9: A ? A(9) : NaN,
                   aOut: (A && A(9.5) === null) ? 1 : 0,
                   bOk: B ? 1 : 0, b0: B ? B(0) : NaN, b5: B ? B(5) : NaN, b6: B ? B(6) : NaN, b7: B ? B(7) : NaN,
                   vOk: V ? 1 : 0, v0: V ? V(0) : NaN, v100: V ? V(100) : NaN, v130: V ? V(130) : NaN,
                   v3_0: V3 ? V3(0) : NaN, v3_100: V3 ? V3(100) : NaN, v3_130: V3 ? V3(130) : NaN, v3_140: V3 ? V3(140) : NaN,
                   gOk: G ? 1 : 0, g0: G ? G(0) : NaN, g8: G ? G(8) : NaN, g12: G ? G(12) : NaN,
                   dOk: D ? 1 : 0, d0: D ? D(0) : NaN, d18: D ? D(18) : NaN, d10: D ? D(10) : NaN,
                   zNull: Z ? 0 : 1 };`,
    checks: [['(а) закрытая форма нашлась', 'aOk', 1, 0],
             ['(а) Y(0) = 36', 'a0', 36, 1e-6],
             ['(а) излом Y(2) = 32', 'a2', 32, 1e-6],
             ['(а) середина прямого участка Y(5) = 20', 'a5', 20, 1e-6],
             ['(а) второй излом Y(7) = 12', 'a7', 12, 1e-6],
             ['(а) Y(8) = 7', 'a8', 7, 1e-6],
             ['(а) конец кривой Y(9) = 0', 'a9', 0, 1e-6],
             ['(а) за концом записи нет', 'aOut', 1, 0],
             ['(б) закрытая форма нашлась', 'bOk', 1, 0],
             ['(б) Y(0) = 52', 'b0', 52, 1e-6],
             ['(б) излом Y(5) = 32', 'b5', 32, 1e-6],
             ['(б) Y(6) = 20', 'b6', 20, 1e-6],
             ['(б) конец Y(7) = 0', 'b7', 0, 1e-6],
             ['(в) линейные: Y(0) = 160', 'v0', 160, 1e-6],
             ['(в) линейные: излом Y(100) = 60', 'v100', 60, 1e-6],
             ['(в) линейные: конец Y(130) = 0', 'v130', 0, 1e-6],
             ['(в) три линейных: Y(0) = 200', 'v3_0', 200, 1e-6],
             ['(в) три линейных: Y(100) = 100', 'v3_100', 100, 1e-6],
             ['(в) три линейных: Y(130) = 40', 'v3_130', 40, 1e-6],
             ['(в) три линейных: Y(140) = 0', 'v3_140', 0, 1e-6],
             ['(г) Y(0) = 13', 'g0', 13, 1e-6],
             ['(г) излом Y(8) = 8', 'g8', 8, 1e-6],
             ['(г) конец Y(12) = 0', 'g12', 0, 1e-6],
             ['(д) две дуги: Y(0) = 18', 'd0', 18, 1e-6],
             ['(д) две дуги: Y(10) = √224', 'd10', 14.966630, 1e-4],
             ['(д) две дуги: конец Y(18) = 0', 'd18', 0, 1e-6],
             ['парабола + дуга: закрытой формы честно НЕТ', 'zNull', 1, 0]],
  },
  {
    /* СЛУЧАЙ Б — убывающие альтернативные издержки (учебник, с. 188–191).
       Метод другой: внутреннего оптимума нет, выгодна полная специализация, и
       суммарная кривая — верхняя огибающая сдвинутых копий исходных.
       Контрольное число владельца: y = 60 − 20√x (Xᵐᵃˣ 9) и y = 40 − 10x
       (Xᵐᵃˣ 4) → 100 − 10X, 100 − 20√X, 130 − 10X, узлы (4; 60) и (9; 40).
       ⚠️ Проверяем и НЕПРЕРЫВНОСТЬ в узлах: огибающая, собранная неверно,
       чаще всего даёт разрыв именно там. */
    name: 'Сложение КПВ · убывающие альт. издержки, верхняя огибающая',
    run: `var cs = ['y = 60 - 20*sqrt(x)', 'y = 40 - 10*x']
                    .map(function (e) { return classifyPpf(parsePpfEquation(e).f); });
          var g = ppfSumAnalytic(cs);
          var at = function (x) { if (!g) return NaN; var v = g.evalY(x); return isNaN(v) ? null : Math.round(v * 1e6) / 1e6; };
          var kinds = ppfCostKinds(cs).map(function (o) { return o.kind; }).join(',');
          /* ⚠️ ПРАВИЛО ЗДЕСЬ ИЗМЕНИЛОСЬ 31.08, И ЭТО НЕ ПОДГОНКА ПРОВЕРКИ.
             До приёмки смешанный набор (растущие издержки + убывающие) закрытой
             формы не получал НИКОГДА. Решением владельца пара таких кривых
             решается полностью — пять кандидатов и верхняя огибающая, с
             параметрической записью на участке равных издержек. Для трёх и
             больше перебор растёт как n·2ⁿ⁻¹, и там по-прежнему численно.
             Поэтому стережём ОБА края: пара запись получает, тройка нет. */
          var mkCs = function (list) {
            return list.map(function (e) { return classifyPpf(parsePpfEquation(e).f); });
          };
          var mixPair = ppfSumAnalytic(mkCs(['y = 60 - 20*sqrt(x)', 'y = 16 - x^2']));
          var mixThree = ppfSumAnalytic(mkCs(['y = 60 - 20*sqrt(x)', 'y = 16 - x^2', 'y = 50 - 5*x']));
          var why = ppfWhyNumeric(mkCs(['y = 60 - 20*sqrt(x)', 'y = 16 - x^2', 'y = 50 - 5*x']));
          return { ok: g ? 1 : 0, y0: at(0), y2: at(2), y4: at(4), y625: at(6.25),
                   y9: at(9), y11: at(11), y13: at(13), out: (at(13.5) === null) ? 1 : 0,
                   /* ⚠️ НЕПРЕРЫВНОСТЬ — ЭТО НЕ «СЛЕВА И СПРАВА ОДНО ЧИСЛО».
                      В узле у кривой ИЗЛОМ: наклоны слева и справа разные, и
                      при шаге ε значения законно расходятся на |Δнаклона|·2ε.
                      Первая версия проверки требовала совпадения при ε = 1e-3
                      и краснела на верной кривой. Правило другое: разрыв обязан
                      СТРЕМИТЬСЯ К НУЛЮ вместе с ε. Считаем скачок при двух
                      шагах: у непрерывной кривой он падает во столько же раз,
                      во сколько уменьшен шаг, у разорванной остаётся прежним. */
                   jump4: (function () {
                     if (at(4) == null) return NaN;
                     var big = Math.abs(at(4 - 1e-2) - at(4 + 1e-2));
                     var sml = Math.abs(at(4 - 1e-4) - at(4 + 1e-4));
                     return (big < 1e-9) ? 0 : sml / big;
                   })(),
                   jump9: (function () {
                     if (at(9) == null) return NaN;
                     var big = Math.abs(at(9 - 1e-2) - at(9 + 1e-2));
                     var sml = Math.abs(at(9 - 1e-4) - at(9 + 1e-4));
                     return (big < 1e-9) ? 0 : sml / big;
                   })(),
                   kinds: (kinds === 'down,const') ? 1 : 0,
                   mixPairOk: mixPair ? 1 : 0,
                   mixThreeNull: mixThree ? 0 : 1,
                   whyNamed: (/растущими издержками/.test(why) && /убывающими/.test(why)) ? 1 : 0 };`,
    checks: [['закрытая форма нашлась', 'ok', 1, 0],
             ['Y(0) = 100', 'y0', 100, 1e-6],
             ['Y(2) = 80 (прямой участок)', 'y2', 80, 1e-6],
             ['узел Y(4) = 60', 'y4', 60, 1e-6],
             ['Y(6,25) = 50 (корневой участок)', 'y625', 50, 1e-6],
             ['узел Y(9) = 40', 'y9', 40, 1e-6],
             ['Y(11) = 20', 'y11', 20, 1e-6],
             ['конец Y(13) = 0', 'y13', 0, 1e-6],
             ['за концом записи нет', 'out', 1, 0],
             ['в узле X = 4 кривая непрерывна (скачок падает вместе с шагом)', 'jump4', 0, 0.02],
             ['в узле X = 9 кривая непрерывна (скачок падает вместе с шагом)', 'jump9', 0, 0.02],
             ['тип издержек взят из формы кривой', 'kinds', 1, 0],
             ['смешанная ПАРА закрытую форму получает', 'mixPairOk', 1, 0],
             ['смешанная ТРОЙКА — по-прежнему нет', 'mixThreeNull', 1, 0],
             ['и причина названа словами', 'whyNamed', 1, 0]],
  },
];

function approx(got, want, tol) {
  if (typeof got !== 'number' || !isFinite(got)) return false;
  return Math.abs(got - want) <= tol;
}

const browser = await chromium.launch({ args: ['--force-color-profile=srgb'] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();

// логин
try {
  await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.fill('#id_username', USER);
  await page.fill('#id_password', PASS);
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
  await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(900);
} catch (e) {
  console.error('SKIP: не удалось открыть /calc2/ — ' + e.message);
  await browser.close();
  process.exit(3);
}

// Проверяем, что реальные функции calc2 загрузились (CDN Math.js/D3 доступны).
const ready = await page.evaluate(() => typeof loadScene === 'function' && typeof redrawAll === 'function' && typeof findEquilibrium === 'function' && typeof STATE === 'object');
if (!ready) {
  console.error('SKIP: функции calc2 не загрузились (нет CDN Math.js/D3?)');
  await browser.close();
  process.exit(3);
}

let pass = 0, fail = 0;
const failures = [];
/* Отбор случаев по куску имени: `CALC2_ONLY='(е)' node calc2/tests/calc2_math.mjs`.
   Нужен для проверки зубастости — временно вернул дефект и хочешь увидеть
   ИМЕННО тот случай, который его ловит, не дожидаясь полутора сотен других.
   В обычном прогоне (и в manage.py test) переменной нет, идут все случаи. */
const ONLY = process.env.CALC2_ONLY || '';
for (const c of CASES) {
  if (ONLY && c.name.indexOf(ONLY) < 0) continue;
  let res;
  try {
    /* П51 завёл память состояния на каждую модель: вернулся в сцену — вернулись
       и твои изменения. Контрольный прогон от этого зависеть не должен: каждый
       случай ставит свою обстановку сам, поэтому память забываем перед каждым. */
    await page.evaluate(() => { if (typeof resetSceneMemory === 'function') resetSceneMemory(); });
    /* ⚠️ ОБЁРТКА АСИНХРОННАЯ, И ЭТО НЕ УКРАШЕНИЕ. Синхронные тела случаев от
       этого не меняются (Playwright дожидается обещания), а тем, кому нужно
       что-то ДОЖДАТЬСЯ — например скачать исходники calc2 и поискать в них
       текст, — становится доступен await. Без этого проверка «врезки нет
       нигде» могла бы смотреть только на одну открытую сцену. */
    res = await page.evaluate('(async function(){ ' + c.run + ' })()');
  } catch (e) {
    fail++; failures.push(`${c.name}\n    setup упал: ${e.message}`);
    console.log(`✗ ${c.name}\n    setup упал: ${e.message}`);
    continue;
  }
  const lines = [];
  let ok = true;
  for (const [label, key, want, tol] of c.checks) {
    const got = res[key];
    /* «WANT» — ожидание, посчитанное самим случаем и лежащее в res.want.
       «WANTXMIN» и подобные — то же самое для случаев, где ожиданий
       несколько: ищем ключ res без учёта регистра. */
    let expect = want;
    if (typeof want === 'string' && want.slice(0, 4) === 'WANT') {
      const k = Object.keys(res).find(n => n.toLowerCase() === want.toLowerCase());
      expect = (k === undefined) ? res.want : res[k];
    }
    const t = (tol == null) ? 0.5 : tol;
    const good = approx(got, expect, t);
    if (!good) ok = false;
    const g = (typeof got === 'number') ? got.toFixed(3) : String(got);
    lines.push(`${good ? '·' : '✗'} ${label}=${g} (ожид ${typeof expect === 'number' ? expect : '?'} ±${t})`);
  }
  if (ok) { pass++; console.log(`✓ ${c.name}`); }
  else { fail++; failures.push(`${c.name}\n    ${lines.join('\n    ')}`); console.log(`✗ ${c.name}\n    ${lines.join('\n    ')}`); }
}

/* =====================================================================
   ФАЗА 6 (сессия «жесты, кусочная и мелкая интерактивность», 21–22.08).
   Эти случаи проверяют не математику, а ДВА ЖЕСТА и КОНСТРУКТОР КУСОЧНОЙ —
   поэтому не укладываются в CASES выше: там run() выполняется целиком ВНУТРИ
   браузера строкой, а протяжке нужен настоящий page.mouse СНАРУЖИ.
   ⚠️ Мышиные события в Playwright/Chromium идут через CDP
   Input.dispatchMouseEvent — тем же путём, что и от настоящего тачпада,
   поэтому браузер сам порождает pointerdown/pointermove/pointerup ПЕРЕД
   синтезированными mousedown/mousemove/mouseup. dispatchEvent(new
   MouseEvent(...)) из page.evaluate этот путь миновал бы и pointer-событий
   не дал бы вовсе — тремя предыдущими замерами так и не воспроизвели дефект
   протяжки (см. карточку 3c3b11c9-2bc1-81b5). */
/* ⚠️ ИТОГОВАЯ СТРОКА ОБЯЗАНА СЧИТАТЬ ВСЕ СЛУЧАИ, А НЕ ТОЛЬКО СПИСОК CASES.
   Она печатала «(всего CASES.length)», а случаи-жесты (gesture) в этот список
   не входят: они регистрируются вызовами ниже. Получалось «197 прошло (всего
   185)» — прошло БОЛЬШЕ, чем всего, и это первое, обо что спотыкается глаз
   при чтении отчёта. Считаем и жесты тоже. */
let gestureCount = 0;
async function gesture(name, fn) {
  gestureCount++;                               // считаем ЗАРЕГИСТРИРОВАННЫЕ, а не прошедшие
  if (ONLY && name.indexOf(ONLY) < 0) return;   // тот же отбор, что и у CASES
  try {
    const r = await fn();
    if (r.ok) { pass++; console.log(`✓ ${name}`); }
    else { fail++; failures.push(`${name}\n    ${r.detail}`); console.log(`✗ ${name}\n    ${r.detail}`); }
  } catch (e) {
    fail++; failures.push(`${name}\n    упал: ${e.message}`);
    console.log(`✗ ${name}\n    упал: ${e.message}`);
  }
}

// Ручка манипулятора на холсте: прозрачный rect с курсором grab (52-modes.js,
// «ОДНО НАЖАТИЕ — ОДИН СМЫСЛ»). Тот же признак, что и в самом движке.
async function grabHandle() {
  return page.evaluate(() => {
    const r = Array.from(document.querySelectorAll('svg#chart rect'))
      .find(el => getComputedStyle(el).cursor === 'grab');
    if (!r) return null;
    const b = r.getBoundingClientRect();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  });
}
async function pointerDrag(x0, y0, dx, dy, steps) {
  steps = steps || 30;
  await page.mouse.move(x0, y0);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) await page.mouse.move(x0 + dx * i / steps, y0 + dy * i / steps);
  await page.mouse.up();
}

// (а)/(б) Протяжка ручки манипулятора: значение меняется, ГРАНИЦЫ ОКНА — нет.
// По одной сцене на клин налога, потолок цены, МРОТ и мировую цену Pw (Н.
// комментарий 52-modes.js ссылается на замер владельца 21.08, ручка налога).
async function manipulatorGesture(label, sceneKey, valueExpr) {
  return gesture(label, async () => {
    await page.evaluate((sk) => { resetSceneMemory(); pickScene(sk); }, sceneKey);
    await page.waitForTimeout(250);
    const before = await page.evaluate((expr) => ({ v: eval(expr), dx0: sx.domain()[0], dx1: sx.domain()[1] }), valueExpr);
    const h = await grabHandle();
    if (!h) return { ok: false, detail: 'ручка (rect с cursor:grab) не найдена на холсте' };
    await pointerDrag(h.x, h.y, -150, -150, 30);
    await page.waitForTimeout(150);
    const after = await page.evaluate((expr) => ({ v: eval(expr), dx0: sx.domain()[0], dx1: sx.domain()[1] }), valueExpr);
    const valueChanged = Math.abs(after.v - before.v) > 1e-6;
    const domainSame = Math.abs(after.dx0 - before.dx0) < 1e-6 && Math.abs(after.dx1 - before.dx1) < 1e-6;
    const detail = `значение ${before.v}→${after.v} (изменилось: ${valueChanged}); `
      + `sx.domain()[0] ${before.dx0.toFixed(2)}→${after.dx0.toFixed(2)} (окно ${domainSame ? 'на месте' : 'СДВИНУЛОСЬ'})`;
    return { ok: valueChanged && domainSame, detail };
  });
}
await manipulatorGesture('(а) протяжка ручки налога — ставка меняется, поле стоит', 'tax', 'STATE.tax');
await manipulatorGesture('(б1) протяжка потолка цены — ставка меняется, поле стоит', 'ceil', 'STATE.pReg');
await manipulatorGesture('(б2) протяжка МРОТ — ставка меняется, поле стоит', 'labor', 'STATE.laborMinW');
await manipulatorGesture('(б3) протяжка мировой цены Pw — ставка меняется, поле стоит', 'smallopen', 'STATE.openPw');

// (в) Протяжка по ПУСТОМУ месту — сдвиг поля жив: границы окна обязаны
// сдвинуться. Контроль на то, что фаза 1 не заглушила сдвиг вообще.
await gesture('(в) протяжка по пустому месту двигает поле', async () => {
  await page.evaluate(() => { resetSceneMemory(); pickScene('sd'); });
  await page.waitForTimeout(200);
  const before = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  const rect = await page.evaluate(() => { const r = document.getElementById('chart').getBoundingClientRect(); return { left: r.left, top: r.top }; });
  // Точка выше кривой D=100−Q и правее её пересечения с осью — заведомо пустое место.
  const p0 = await page.evaluate(() => ({ x: sx(85), y: sy(97) }));
  const px0 = rect.left + p0.x, py0 = rect.top + p0.y;
  await pointerDrag(px0, py0, -80, 0, 20);
  await page.waitForTimeout(150);
  const after = await page.evaluate(() => [sx.domain()[0], sx.domain()[1]]);
  const moved = Math.abs(after[0] - before[0]) > 1e-6;
  return { ok: moved, detail: `sx.domain() ${before.map(v => v.toFixed(1))} → ${after.map(v => v.toFixed(1))}` };
});

// (г) Конструктор кусочной в «КТВ. Одна страна»: щёлкаем по НАСТОЯЩИМ кнопкам
// интерфейса («?» → «Кусочная функция» → «Поставить в поле»), запись обязана
// применяться без ручной приставки «y = » (карточка 3c3b11c9-2bc1-8182).
await gesture('(г) КТВ строится конструктором без ручной приставки "y ="', async () => {
  await page.evaluate(() => { resetSceneMemory(); pickScene('trade'); });
  await page.waitForTimeout(250);
  const reveal = async (sel) => {
    await page.evaluate((s) => {
      const el = document.querySelector(s);
      if (!el) return;
      for (let n = el; n && n !== document.body; n = n.parentElement) {
        const foldable = n.classList && n.classList.contains('fold-body');
        if (foldable && !n.classList.contains('open') && n.id) {
          const btn = document.querySelector('[aria-controls="' + n.id + '"]');
          if (btn) btn.click();
        }
      }
      el.scrollIntoView({ block: 'center' });
    }, sel);
    await page.waitForTimeout(120);
  };
  /* ⚠️ ЗДЕСЬ СТОЯЛА ПОДПОРКА `PW.rows = []`, И ЕЁ УБРАЛИ НАРОЧНО.
     Раньше строки конструктора переживали закрытие окна и чужие поля, прогон
     идёт одним долгим сеансом браузера, и более ранний случай оставлял здесь
     чужие куски в чужой букве («p» вместо «X»). Утечка починена: конструктор
     собирает строки заново при каждом открытии — из того, что стоит в ПОЛЕ.
     Без подпорки этот случай и стережёт починку: вернётся утечка — сюда
     приедет «p», и разбор КТВ покраснеет. */
  await reveal('#fh-auto-inp-ppft');
  await page.click('#fh-auto-inp-ppft');
  await page.waitForTimeout(150);
  const pwBtnSel = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('.mkbd.open .mkbd-foot button'))
      .find(b => b.textContent.trim() === 'Кусочная функция');
    if (!btn) return null;
    if (!btn.id) btn.id = '__pw_open_btn_calc2math';
    return '#' + btn.id;
  });
  if (!pwBtnSel) return { ok: false, detail: 'кнопка «Кусочная функция» не найдена в клавиатуре поля' };
  await page.click(pwBtnSel);
  await page.waitForTimeout(150);
  await page.click('#pw-apply');
  await page.waitForTimeout(250);
  const r = await page.evaluate(() => ({
    fieldValue: document.getElementById('inp-ppft').value,
    stateFormula: STATE.ppftFormula,
    parseError: (typeof parsePpfEquation === 'function') ? (parsePpfEquation(STATE.ppftFormula).error || null) : 'нет функции',
    canvasPaths: document.querySelectorAll('svg#chart path').length,
  }));
  const noPrefix = !/^\s*y\s*=/i.test(r.fieldValue);
  const ok = noPrefix && r.stateFormula === r.fieldValue && !r.parseError && r.canvasPaths > 0;
  return { ok, detail: `поле="${r.fieldValue}" ошибка=${r.parseError} путей=${r.canvasPaths}` };
});

// (д) Излом среди ключевых точек — минимум в двух разных сценах (было
// «отмечен сценой в 18 из 58 пар», см. карточку 3c3b11c9-2bc1-81cc).
await gesture('(д) излом присутствует среди ключевых точек — минимум в двух сценах', async () => {
  const scenes = [
    { key: 'sd', setup: () => { const D = STATE.curves.find(c => c.role === 'demand'); D.expr = 'Q < 40 ? 100 - Q : 80 - 0.5*Q'; D.compiled = compileFormula(D.expr).compiled; D.linear = null; } },
    { key: 'labor', setup: () => { const D = STATE.curves.find(c => c.role === 'demand'); D.expr = 'L < 40 ? 100 - L : 80 - 0.5*L'; D.compiled = compileFormula(D.expr).compiled; D.linear = null; } },
  ];
  let found = 0;
  const detail = [];
  for (const s of scenes) {
    const r = await page.evaluate(({ key, setupSrc }) => {
      resetSceneMemory(); pickScene(key);
      (new Function(setupSrc))();
      invalidateKeyTargets(); redrawAll();
      const kink = keyTargets().find(p => p.kind === 'kink');
      return !!kink;
    }, { key: s.key, setupSrc: '(' + s.setup.toString() + ')()' });
    if (r) found++;
    detail.push(`${s.key}: ${r ? 'есть' : 'НЕТ'}`);
  }
  return { ok: found >= 2, detail: detail.join(', ') + ` — сцен с изломом: ${found}/${scenes.length}` };
});

// (е) Конструктор на пустом поле не падает и не подставляет пустоту —
// возвращается к букве по виду поля (карточка «полупустое поле», хвост
// сессии 21.08).
await gesture('(е) конструктор на пустом поле не падает', async () => {
  const r = await page.evaluate(() => {
    resetSceneMemory(); pickScene('costs');
    const inp = document.getElementById('inp-tc');
    inp.value = '';
    let crashed = null, v = null;
    try {
      const fallback = (typeof FORMULA_VAR !== 'undefined' && FORMULA_VAR.TC) || 'x';
      v = pwVarForField(inp, fallback);
      openPiecewise(inp, v);
      closePiecewise();
    } catch (e) { crashed = String(e.message || e); }
    return { v, crashed };
  });
  return { ok: !r.crashed && !!r.v, detail: `буква=${r.v} crash=${r.crashed}` };
});

/* =====================================================================
   НОЧНАЯ СЕССИЯ «ЛЕВАЯ ПАНЕЛЬ» (22.08). Зубастые проверки к четырём находкам,
   которые иначе некому стеречь: память параметров между моделями, живая
   перестройка КТВ и договор «добавленная кривая в расчёты не входит».
   ===================================================================== */

// (а) Вход в модель, где в этом сеансе не были, начинается с нуля параметров.
await gesture('(а) вход в новую модель — параметров ноль', async () => {
  const r = await page.evaluate(async () => {
    const w = ms => new Promise(res => setTimeout(res, ms));
    resetSceneMemory(); pickScene('smallopen'); await w(250);
    const inp = document.querySelector('#curve-list .curve-expr-inp');
    inp.value = '100 - a*Q'; inp.dispatchEvent(new Event('input', { bubbles: true }));
    await w(250);
    const here = Object.keys(STATE.params || {});
    if (STATE.params.a) STATE.params.a.value = 3;
    redrawAll(); await w(150);
    pickScene('adas'); await w(250);
    const adas = Object.keys(STATE.params || {});
    pickScene('ceil'); await w(250);
    const ceil = Object.keys(STATE.params || {});
    return { here, adas, ceil };
  });
  return { ok: r.here.join() === 'a' && r.adas.length === 0 && r.ceil.length === 0,
           detail: `в «Малой открытой» [${r.here}], в AD–AS [${r.adas}], в «Поле и потолке» [${r.ceil}]` };
});

// (б) Возврат в модель, где параметр заводили, возвращает его с тем же числом.
// Эта проверка ВАЖНЕЕ предыдущей: сломав её, мы получим дефект хуже исходного.
await gesture('(б) возврат в модель — параметр на месте с прежним значением', async () => {
  const r = await page.evaluate(async () => {
    const w = ms => new Promise(res => setTimeout(res, ms));
    resetSceneMemory(); pickScene('smallopen'); await w(250);
    const inp = document.querySelector('#curve-list .curve-expr-inp');
    inp.value = '100 - a*Q'; inp.dispatchEvent(new Event('input', { bubbles: true }));
    await w(250);
    if (STATE.params.a) STATE.params.a.value = 3.5;
    redrawAll(); await w(150);
    pickScene('adas'); await w(250);
    const away = Object.keys(STATE.params || {});
    pickScene('smallopen'); await w(300);
    const back = Object.keys(STATE.params || {});
    const val = STATE.params.a ? STATE.params.a.value : null;
    const expr = (STATE.curves[0] || {}).expr;
    return { away, back, val, expr };
  });
  return { ok: r.away.length === 0 && r.back.join() === 'a' && Math.abs(r.val - 3.5) < 1e-9,
           detail: `уходили [${r.away}], вернулись [${r.back}] a=${r.val}, формула «${r.expr}»` };
});

// (в) КТВ перестраивается от ползунка, кнопку «Построить КТВ» не трогаем.
await gesture('(в) ползунок меняет геометрию КТВ без нажатия кнопки', async () => {
  const r = await page.evaluate(async () => {
    const w = ms => new Promise(res => setTimeout(res, ms));
    const geom = () => [...document.querySelectorAll('#chart path')].map(p => p.getAttribute('d') || '');
    resetSceneMemory(); pickScene('trade'); await w(400);
    const f = document.getElementById('inp-ppft');
    f.value = '100 - a*X';
    document.getElementById('inp-ppft-price').value = '1.5';
    document.getElementById('btn-ppft-apply').click(); await w(400);
    const before = geom();
    const d0 = STATE.ppfTradeData ? { Xmax: STATE.ppfTradeData.Xmax, yint: STATE.ppfTradeData.yint } : null;
    const sl = [...document.querySelectorAll('#params-panel input[type=range]')]
      .find(x => (x.id || '').indexOf('ppft') < 0);
    if (!sl) return { none: true };
    sl.value = String(Math.min(parseFloat(sl.max), 2));
    sl.dispatchEvent(new Event('input', { bubbles: true }));
    await w(500);
    const after = geom();
    const d1 = STATE.ppfTradeData ? { Xmax: STATE.ppfTradeData.Xmax, yint: STATE.ppfTradeData.yint } : null;
    return { changed: JSON.stringify(before) !== JSON.stringify(after), d0, d1 };
  });
  if (r.none) return { ok: false, detail: 'ползунка параметра в панели нет' };
  return { ok: r.changed && r.d0 && r.d1 && Math.abs(r.d0.Xmax - r.d1.Xmax) > 1e-6,
           detail: `до ${JSON.stringify(r.d0)}, после ${JSON.stringify(r.d1)}, путь изменился: ${r.changed}` };
});

// (е) Добавленная кривая просто рисуется поверх: контрольные P*=50, Q*=50 держатся.
await gesture('(е) добавленная кривая не меняет равновесие (P*=50, Q*=50)', async () => {
  const r = await page.evaluate(async () => {
    const w = ms => new Promise(res => setTimeout(res, ms));
    resetSceneMemory(); pickScene('sd'); await w(350);
    const eq0 = { P: STATE.eq.P, Q: STATE.eq.Q };
    addEmptyCurve();
    const el = [...document.querySelectorAll('#curve-list .curve-expr-inp')].pop();
    el.value = '30 + 0.7*Q'; el.dispatchEvent(new Event('input', { bubbles: true }));
    await w(350);
    const c = STATE.curves[STATE.curves.length - 1];
    const eq1 = { P: STATE.eq.P, Q: STATE.eq.Q };
    const drawn = document.querySelectorAll('#chart path[data-curve]').length;
    return { eq0, eq1, role: c.role, drawn, expr: c.expr };
  });
  const near = (v, t) => Math.abs(v - t) < 0.3;
  return { ok: !r.role && near(r.eq1.P, 50) && near(r.eq1.Q, 50)
               && Math.abs(r.eq1.P - r.eq0.P) < 1e-9 && Math.abs(r.eq1.Q - r.eq0.Q) < 1e-9
               && r.drawn === 3,
           detail: `до ${JSON.stringify(r.eq0)}, после ${JSON.stringify(r.eq1)}, роль ${r.role}, `
                 + `кривых на холсте ${r.drawn}, формула «${r.expr}»` };
});

await browser.close();
console.log(`\n=== calc2 регрессия: ${pass} прошло, ${fail} провалено `
  + `(всего ${CASES.length + gestureCount}: ${CASES.length} случаев + ${gestureCount} жестов)`
  + (ONLY ? ` [отбор «${ONLY}»]` : '') + ' ===');
process.exit(fail === 0 ? 0 : 1);
