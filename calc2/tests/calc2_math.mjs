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
    name: 'Экстерналии (Пигу) · D=100−Q, MPC=Q, ext=20',
    run: `loadScene('sd'); setScenario('externality'); redrawAll();
          var e = STATE.ext || {};
          return { Qmkt: e.Qmkt, Qopt: e.Qopt, dwl: e.dwl };`,
    checks: [['Qрын', 'Qmkt', 50, 0.3], ['Qопт', 'Qopt', 40, 0.4], ['DWL', 'dwl', 100, 2]],
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
    name: 'Внешний эффект ПОЛОЖИТЕЛЬНЫЙ · MPB=100−Q, ext=20, S=Q ⇒ Qрын=50, Qопт=60, DWL=100',
    // Зеркало отрицательного случая: недопроизводство, лечится СУБСИДИЕЙ.
    // В конце возвращаем знак на 'neg', чтобы не влиять на порядок прогона.
    run: `loadScene('ext'); setExtSign('pos');
          STATE.extExpr = '20'; recompileExt(); redrawAll();
          var e = STATE.ext || {};
          var res = { Qmkt: e.Qmkt, Qopt: e.Qopt, dwl: e.dwl, sub: e.corrective,
                      Popt: e.Popt, pos: e.pos ? 1 : 0 };
          setExtSign('neg');
          return res;`,
    checks: [['Qрын', 'Qmkt', 50, 0.3], ['Qопт', 'Qopt', 60, 0.4], ['DWL', 'dwl', 100, 2],
             ['субсидия', 'sub', 20, 0.2], ['Pопт = S(Qопт)', 'Popt', 60, 0.4], ['знак +', 'pos', 1, 0.1]],
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
          document.getElementById('ac-pick').value = 'D';
          document.getElementById('ac-from').value = '0';
          document.getElementById('ac-to').value = '100';
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
          document.getElementById('ac-from').value = '';
          document.getElementById('ac-to').value = '';
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
    // Фаза 9: масштаб в .tex — тот же, что на экране. Сверяем форму картинки:
    // отношение «сантиметров на единицу X» к «сантиметрам на единицу Y».
    name: 'Экспорт · масштаб .tex совпадает с экранным',
    run: `pickScene('tax');
          var tex = buildTex('Проверка', 'fig:t');
          var ax = /xmin=([-\\d.]+), xmax=([-\\d.]+), ymin=([-\\d.]+), ymax=([-\\d.]+)/.exec(tex);
          var sz = /width=([\\d.]+)cm, height=([\\d.]+)cm/.exec(tex);
          var s = mainScales();
          var xd = s.mx.domain(), yd = s.my.domain();
          var xr = s.mx.range(), yr = s.my.range();
          var scrX = Math.abs(xr[1] - xr[0]) / (xd[1] - xd[0]);
          var scrY = Math.abs(yr[1] - yr[0]) / (yd[1] - yd[0]);
          var papX = (+sz[1]) / ((+ax[2]) - (+ax[1]));
          var papY = (+sz[2]) / ((+ax[4]) - (+ax[3]));
          return { want: scrX / scrY, paper: papX / papY,
                   only: tex.indexOf('scale only axis') >= 0 ? 1 : 0 };`,
    checks: [['форма на бумаге', 'paper', 'WANT', 0.02],
             ['поле графика, а не картинка', 'only', 1, 0]],
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
          sel.value = sel.options[0].value;
          document.getElementById('ac-from').value = '';
          document.getElementById('ac-to').value = '';
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
for (const c of CASES) {
  let res;
  try {
    res = await page.evaluate('(function(){ ' + c.run + ' })()');
  } catch (e) {
    fail++; failures.push(`${c.name}\n    setup упал: ${e.message}`);
    console.log(`✗ ${c.name}\n    setup упал: ${e.message}`);
    continue;
  }
  const lines = [];
  let ok = true;
  for (const [label, key, want, tol] of c.checks) {
    const got = res[key];
    const expect = (want === 'WANT') ? res.want : want;
    const t = (tol == null) ? 0.5 : tol;
    const good = approx(got, expect, t);
    if (!good) ok = false;
    const g = (typeof got === 'number') ? got.toFixed(3) : String(got);
    lines.push(`${good ? '·' : '✗'} ${label}=${g} (ожид ${typeof expect === 'number' ? expect : '?'} ±${t})`);
  }
  if (ok) { pass++; console.log(`✓ ${c.name}`); }
  else { fail++; failures.push(`${c.name}\n    ${lines.join('\n    ')}`); console.log(`✗ ${c.name}\n    ${lines.join('\n    ')}`); }
}

await browser.close();
console.log(`\n=== calc2 регрессия: ${pass} прошло, ${fail} провалено (всего ${CASES.length}) ===`);
process.exit(fail === 0 ? 0 : 1);
