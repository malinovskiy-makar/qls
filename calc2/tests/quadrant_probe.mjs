/* Прибор «первая четверть»: математика калькулятора против границ кадра.

   Мерит четыре набора и скорость панорамирования. Числа печатаются ВСЕГДА,
   а не только при провале: этим прибором снимаются и «до», и «после», и
   сравнивать надо именно числа, а не слово OK.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/quadrant_probe.mjs                 # всё
     node calc2/tests/quadrant_probe.mjs А Б             # только эти наборы

   Наборы:
     А — регрессия: 2 группы спроса + 2 предложения, ничего не должно съехать;
     Б — главный: S₁ = Q−100 уходит ниже оси Q, равновесие за краем кадра;
     В — отрисовка: есть ли в пути кривой точки с P < 0;
     Г — пересечение вне первой четверти (P = 200, Q = −100);
     СКОРОСТЬ — среднее время кадра на 60 шагах панорамы в наборе Б.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const want = process.argv.slice(2).map(s => s.toUpperCase());
const need = (name) => !want.length || want.includes(name);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0;
const num = (v) => (typeof v === 'number' && isFinite(v)) ? (Math.round(v * 1e4) / 1e4) : String(v);
// Напечатать измеренное число рядом с ожидаемым. want === null — «просто покажи».
function show(label, got, wanted, tol) {
  if (wanted == null) { console.log('     ' + label + ' = ' + num(got)); return; }
  const good = typeof got === 'number' && isFinite(got) && Math.abs(got - wanted) <= tol;
  if (!good) bad++;
  console.log((good ? 'OK   ' : 'FAIL ') + label + ' = ' + num(got) + '   (ожид ' + wanted + ' ±' + tol + ')');
}
function flag(label, cond, detail) {
  if (!cond) bad++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (detail != null ? '  -> ' + detail : ''));
}

/* Развернуть сцену сложения: столько-то групп, у каждой своя формула.
   Формулы ставим через updateCurveExpr — тем же путём, что и человек в поле. */
const SUM_SETUP = `
function quadSetupSum(dExprs, sExprs) {
  resetSceneMemory();
  pickScene('sdsum');
  sumSetCount('D', dExprs.length);
  sumSetCount('S', sExprs.length);
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  dExprs.forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
  sExprs.forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
  redrawAll();
}
// Снимок табло: всё, ради чего заведён прибор, одним объектом.
function quadSnap() {
  var st = (typeof sumGroupStats === 'function') ? sumGroupStats() : null;
  var recD = STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'D'; });
  var recS = STATE.curves.find(function (c) { return c.kind === 'sum' && c.sumGroup === 'S'; });
  var box = document.getElementById('info-sum');
  return {
    win: { qmin: CONFIG.Qmin, qmax: CONFIG.Qmax, pmin: CONFIG.Pmin, pmax: CONFIG.Pmax },
    eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
    cs: STATE.cs, ps: STATE.ps, sw: STATE.sw,
    recordD: recD ? String(recD.expr || '') : '',
    recordS: recS ? String(recS.expr || '') : '',
    groups: st ? {
      qD: st.D.map(function (r) { return r.q; }), qS: st.S.map(function (r) { return r.q; }),
      csEach: st.D.map(function (r) { return r.surplus; }), psEach: st.S.map(function (r) { return r.surplus; }),
      csGroups: st.csGroups, psGroups: st.psGroups,
      csWhole: st.csWhole, psWhole: st.psWhole,
    } : null,
    warn: !!(box && box.querySelector('.warn')),
    warnText: (box && box.querySelector('.warn')) ? box.querySelector('.warn').textContent.trim() : '',
  };
}
`;
await page.addScriptTag({ content: SUM_SETUP });
// Скрипт живёт до первой перезагрузки; страницу мы не перезагружаем.

const run = (code) => page.evaluate(`(function(){ ${code} })()`);

/* ── НАБОР А. Регрессия ─────────────────────────────────────────────── */
if (need('А') || need('A')) {
  console.log('\n=== НАБОР А (регрессия): D 100-Q, 60-Q; S Q, Q+20 ===');
  const a = await run(`
    quadSetupSum(['100-Q', '60-Q'], ['Q', 'Q+20']);
    return quadSnap();
  `);
  show('Q*', a.eq && a.eq.Q, 70, 0.05);
  show('P*', a.eq && a.eq.P, 45, 0.05);
  show('спрос группы 1', a.groups && a.groups.qD[0], 55, 0.05);
  show('спрос группы 2', a.groups && a.groups.qD[1], 15, 0.05);
  show('предложение группы 1', a.groups && a.groups.qS[0], 45, 0.05);
  show('предложение группы 2', a.groups && a.groups.qS[1], 25, 0.05);
  show('CS группы 1', a.groups && a.groups.csEach[0], 1512.5, 0.05);
  show('CS группы 2', a.groups && a.groups.csEach[1], 112.5, 0.05);
  show('CS вместе', a.groups && a.groups.csGroups, 1625, 0.05);
  show('PS группы 1', a.groups && a.groups.psEach[0], 1012.5, 0.05);
  show('PS группы 2', a.groups && a.groups.psEach[1], 312.5, 0.05);
  show('PS вместе', a.groups && a.groups.psGroups, 1325, 0.05);
  show('SW (cs+ps движка)', a.sw, 2950, 0.05);
  flag('предупреждения о расхождении нет', !a.warn, a.warnText);

  /* Запись суммарной кривой при ТРЁХ масштабах. Если она едет вместе с кадром —
     строки разойдутся, и это видно без всякой интерпретации. */
  const rec = await run(`
    quadSetupSum(['100-Q', '60-Q'], ['Q', 'Q+20']);
    var out = [];
    out.push(quadSnap());
    zoomStep(1.6); out.push(quadSnap());
    zoomStep(1 / 1.6); zoomStep(1 / 1.6); out.push(quadSnap());
    return out.map(function (s) { return { qmax: s.win.qmax, pmax: s.win.pmax, D: s.recordD, S: s.recordS }; });
  `);
  rec.forEach((r, i) => console.log(`     запись при Qmax=${num(r.qmax)} Pmax=${num(r.pmax)}:\n       D: ${r.D}\n       S: ${r.S}`));
  flag('запись суммарного СПРОСА одинакова при трёх масштабах',
    rec[0].D === rec[1].D && rec[1].D === rec[2].D);
  flag('запись суммарного ПРЕДЛОЖЕНИЯ одинакова при трёх масштабах',
    rec[0].S === rec[1].S && rec[1].S === rec[2].S);
}

/* ── НАБОР Б. Главный ───────────────────────────────────────────────── */
if (need('Б') || need('B')) {
  console.log('\n=== НАБОР Б (главный): D 100-Q, 60-Q, 40-Q; S Q-100, Q+20 ===');
  const start = await run(`
    quadSetupSum(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']);
    return quadSnap();
  `);
  console.log(`     окно на старте: Q ${num(start.win.qmin)}…${num(start.win.qmax)}, P ${num(start.win.pmin)}…${num(start.win.pmax)}`);
  show('НА СТАРТЕ Q*', start.eq && start.eq.Q, 128, 0.5);
  show('НА СТАРТЕ P*', start.eq && start.eq.P, 24, 0.5);

  // «Отдалиться»: три шага колеса от себя.
  const far = await run(`
    zoomStep(1.6); zoomStep(1.6); zoomStep(1.6);
    return quadSnap();
  `);
  console.log(`     окно после отдаления: Q ${num(far.win.qmin)}…${num(far.win.qmax)}, P ${num(far.win.pmin)}…${num(far.win.pmax)}`);
  show('после отдаления Q*', far.eq && far.eq.Q, 128, 0.5);
  show('после отдаления P*', far.eq && far.eq.P, 24, 0.5);
  show('PS группы 1', far.groups && far.groups.psEach[0], 2688, 1);
  show('PS группы 2', far.groups && far.groups.psEach[1], 8, 0.5);
  show('PS вместе (по группам)', far.groups && far.groups.psGroups, 2696, 1);
  show('PS по СУММАРНОЙ кривой', far.groups && far.groups.psWhole, 2696, 1);
  show('CS группы 1', far.groups && far.groups.csEach[0], 2888, 1);
  show('CS группы 2', far.groups && far.groups.csEach[1], 648, 1);
  show('CS группы 3', far.groups && far.groups.csEach[2], 128, 1);
  show('CS вместе (по группам)', far.groups && far.groups.csGroups, 3664, 1);
  show('CS по СУММАРНОЙ кривой', far.groups && far.groups.csWhole, 3664, 1);
  show('SW = CS + PS', (far.groups && (far.groups.csGroups + far.groups.psGroups)), 6360, 2);
  console.log('     запись суммарного предложения: ' + far.recordS);
  flag('предупреждения о расхождении НЕТ', !far.warn, far.warnText);

  // Вернуться приближением: числа обязаны быть те же.
  const back = await run(`
    zoomStep(1 / 1.6); zoomStep(1 / 1.6); zoomStep(1 / 1.6); zoomStep(1 / 1.6);
    return quadSnap();
  `);
  console.log(`     окно после приближения: Q ${num(back.win.qmin)}…${num(back.win.qmax)}, P ${num(back.win.pmin)}…${num(back.win.pmax)}`);
  show('после приближения Q*', back.eq && back.eq.Q, 128, 0.5);
  show('после приближения P*', back.eq && back.eq.P, 24, 0.5);
}

/* ── НАБОР В. Отрисовка ─────────────────────────────────────────────── */
if (need('В') || need('V')) {
  console.log('\n=== НАБОР В (отрисовка): сцена «Спрос и предложение», окно до Q = 200 ===');
  const v = await run(`
    resetSceneMemory(); pickScene('sd');
    var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
    var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
    if (d) updateCurveExpr(d, '100-Q');
    if (s) updateCurveExpr(s, 'Q');
    // Границы окна — через поля меню гаечного ключа, как это делает человек.
    document.getElementById('inp-qmax').value = '200';
    document.getElementById('inp-pmax').value = '200';
    applyViewBounds();
    redrawAll();
    // Читаем НАРИСОВАННЫЙ путь и переводим пиксели обратно в данные шкалами.
    var out = [];
    document.querySelectorAll('path[data-curve]').forEach(function (el) {
      var id = +el.getAttribute('data-curve');
      var cur = STATE.curves.find(function (c) { return c.id === id; });
      var pts = [];
      String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
        var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
        if (m) pts.push([sx.invert(+m[1]), sy.invert(+m[2])]);
      });
      var below = pts.filter(function (p) { return p[1] < -1e-6; });
      var qs = pts.map(function (p) { return p[0]; });
      out.push({
        role: cur ? cur.role : null, expr: cur ? cur.expr : '',
        n: pts.length, below: below.length,
        minP: pts.length ? Math.min.apply(null, pts.map(function (p) { return p[1]; })) : null,
        maxQ: qs.length ? Math.max.apply(null, qs) : null,
        worst: below.length ? below[below.length - 1] : null,
      });
    });
    return { win: { qmax: CONFIG.Qmax, pmax: CONFIG.Pmax }, curves: out };
  `);
  console.log(`     окно: Qmax=${num(v.win.qmax)}, Pmax=${num(v.win.pmax)}`);
  v.curves.forEach(c => {
    console.log(`     ${c.role || '?'} «${c.expr}»: точек ${c.n}, из них с P<0 — ${c.below}; ` +
      `min P = ${num(c.minP)}, край пути Q = ${num(c.maxQ)}` +
      (c.worst ? `, самая нижняя (Q=${num(c.worst[0])}, P=${num(c.worst[1])})` : ''));
  });
  const dem = v.curves.find(c => c.role === 'demand');
  flag('в пути кривой СПРОСА нет точек с P < 0', dem && dem.below === 0, dem ? String(dem.below) : 'кривой нет');
  if (dem) show('край пути спроса по Q', dem.maxQ, 100, 200 / 400 + 1e-6);

  /* ⚠️ ДАННЫЕ ПУТИ И ВИДИМОЕ НА ЭКРАНЕ — РАЗНЫЕ ВЕЩИ, И ИХ НАДО РАЗЛИЧАТЬ.
     При включённой галочке «только первая четверть» прямоугольный clip-path
     режет холст по оси, и хвост ниже нуля в пути ЕСТЬ, но не виден. Стоит
     галочку снять — тот же хвост выходит на экран. Печатаем оба числа без
     вердикта: сколько точек ниже оси и сколько из них реально закрашивается. */
  const vis = await run(`
    setFirstQuad(false); redrawAll();
    var cl = document.querySelector('#plot-clip rect');
    var bottom = (+cl.getAttribute('y')) + (+cl.getAttribute('height'));
    var below = 0, seen = 0, deepest = null;
    document.querySelectorAll('path[data-curve]').forEach(function (el) {
      var id = +el.getAttribute('data-curve');
      var cur = STATE.curves.find(function (c) { return c.id === id; });
      if (!cur || cur.role !== 'demand') return;
      String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(function (tok) {
        var m = tok.match(/[ML]\\s*(-?[\\d.eE+]+)[,\\s]+(-?[\\d.eE+]+)/);
        if (!m) return;
        var py = +m[2], P = sy.invert(py);
        if (P < -1e-6) { below++; if (py <= bottom + 0.5) { seen++; deepest = P; } }
      });
    });
    return { quad: STATE.firstQuad, pmin: CONFIG.Pmin, below: below, seen: seen, deepest: deepest };
  `);
  console.log(`     галочка «только первая четверть» СНЯТА (Pmin=${num(vis.pmin)}): ` +
    `точек с P<0 в пути ${vis.below}, из них попадают в окно и закрашиваются ${vis.seen}` +
    (vis.deepest != null ? `, до P = ${num(vis.deepest)}` : ''));
}

/* ── НАБОР Г. Пересечение вне первой четверти ───────────────────────── */
if (need('Г') || need('G')) {
  console.log('\n=== НАБОР Г: спрос 100-P, предложение -200+0.5*P (пересечение P=200, Q=-100) ===');
  const g = await run(`
    resetSceneMemory(); pickScene('sd');
    var d = STATE.curves.find(function (c) { return c.role === 'demand'; });
    var s = STATE.curves.find(function (c) { return c.role === 'supply'; });
    var e1 = d ? updateCurveExpr(d, '100-P') : 'нет кривой спроса';
    var e2 = s ? updateCurveExpr(s, '-200+0.5*P') : 'нет кривой предложения';
    redrawAll();
    var keys = document.getElementById('info-eq');
    var areas = document.getElementById('info-areas');
    var ex = document.getElementById('ex-body');
    /* Формулу рядом с текстом печатает KaTeX и держит её невидимую копию для
       чтецов экрана — textContent склеил бы обе. Снимаем копию с клона. */
    var txt = '';
    if (ex) {
      var clone = ex.cloneNode(true);
      clone.querySelectorAll('.katex-mathml, annotation').forEach(function (n) { n.remove(); });
      txt = clone.textContent.replace(/\\s+/g, ' ').trim();
    }
    return {
      err: [e1, e2].filter(Boolean),
      eq: STATE.eq, cs: STATE.cs, ps: STATE.ps,
      offEq: STATE.offEq || null,
      keysText: keys ? keys.textContent.trim() : '(нет блока)',
      areasText: areas ? areas.textContent.trim() : '(нет блока)',
      explainHas200: /200/.test(txt) && /−?-?100/.test(txt),
      noStarNotation: !/Q\\s*\\*|P\\s*\\*/.test(txt),
      explainLen: txt.length,
      explainTail: txt.slice(-460),
      dashed: document.querySelectorAll('[data-offquad]').length,
    };
  `);
  if (g.err.length) console.log('     ОШИБКИ ВВОДА: ' + g.err.join(' | '));
  console.log('     STATE.eq = ' + JSON.stringify(g.eq) + ', STATE.offEq = ' + JSON.stringify(g.offEq));
  console.log('     «Ключевые значения»: ' + JSON.stringify(g.keysText.slice(0, 220)));
  console.log('     «Излишки»: ' + JSON.stringify(g.areasText.slice(0, 160)));
  console.log('     пунктирных элементов пересечения: ' + g.dashed);
  console.log('     хвост «Объяснения модели»: ' + JSON.stringify(g.explainTail.slice(-320)));
  flag('равновесия нет (STATE.eq === null)', g.eq === null, JSON.stringify(g.eq));
  show('найденное пересечение · Q', g.offEq && g.offEq.Q, -100, 0.2);
  show('найденное пересечение · P', g.offEq && g.offEq.P, 200, 0.2);
  flag('в «Объяснении модели» есть числа 200 и 100', g.explainHas200);
  flag('обозначений Q* и P* рядом с этими числами НЕТ', g.noStarNotation);
  flag('блок «Излишки» пуст', g.areasText === '', JSON.stringify(g.areasText.slice(0, 80)));
  flag('в «Ключевых значениях» нет чисел равновесия', !/\d/.test(g.keysText), g.keysText.slice(0, 80));
  flag('пунктир к точке пересечения нарисован', g.dashed > 0, String(g.dashed));
}

/* ── СКОРОСТЬ. 60 шагов панорамы ────────────────────────────────────
   ⚠️ МЕРИМ ТРИ СЛУЧАЯ, А НЕ ОДИН.
   Сравнивать «до» и «после» на наборе Б в стартовом окне НЕЧЕСТНО: до починки
   равновесие там не находилось вовсе, а без равновесия движок пропускал и
   интегралы излишков, и табло по группам. Дешёвый кадр получался оттого, что
   калькулятор не считал ничего. Поэтому рядом стоят два случая, где обе
   версии делают ОДНУ И ТУ ЖЕ работу: набор Б после отдаления и набор А. */
if (need('СКОРОСТЬ') || need('S')) {
  console.log('\n=== СКОРОСТЬ: 60 шагов панорамы ===');
  const speed = async (label, setup) => {
    const sp = await run(`
      ${setup}
      // Прогрев: первая перерисовка всегда дороже (компиляция, кэш шрифтов).
      for (var w = 0; w < 5; w++) panByPixels(-3, 0);
      var reb = 0;
      var _rb = window.sumRebuildSide;
      window.sumRebuildSide = function (s) { reb++; return _rb(s); };
      var t0 = performance.now();
      for (var i = 0; i < 60; i++) panByPixels((i % 2 ? -6 : 6), 0);
      var t1 = performance.now();
      window.sumRebuildSide = _rb;
      return { per: (t1 - t0) / 60, total: t1 - t0, reb: reb, eq: !!STATE.eq };
    `);
    console.log(`     ${label}: ${num(sp.per)} мс/кадр (всего ${num(sp.total)} мс), ` +
      `пересборок суммы за 60 кадров ${sp.reb}, равновесие ${sp.eq ? 'найдено' : 'НЕ найдено'}`);
    return sp;
  };
  await speed('Б, стартовое окно', `quadSetupSum(['100-Q','60-Q','40-Q'], ['Q-100','Q+20']);`);
  await speed('Б, после отдаления', `quadSetupSum(['100-Q','60-Q','40-Q'], ['Q-100','Q+20']);
                                     zoomStep(1.6); zoomStep(1.6); zoomStep(1.6);`);
  await speed('А, стартовое окно  ', `quadSetupSum(['100-Q','60-Q'], ['Q','Q+20']);`);
}

if (errs.length) { console.log('\nОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 6).join(' | ')); bad++; }
console.log('\n' + (bad ? ('ПРОВАЛОВ: ' + bad) : 'всё сошлось'));
await browser.close();
process.exit(bad ? 1 : 0);
