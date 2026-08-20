/* Замер фазы 5 — взаимодействие с холстом (п. 24–29, 32, 33).

   Прибор отвечает ровно на то, что видит человек, и настоящими событиями
   мыши: щёлкнуть по кривой и посмотреть, изменилась ли формула, важнее, чем
   спросить у кода, есть ли у него порог.

   ⚠️ Порядок важен: сцена загружается ПОСЛЕ закрытия окна выбора, иначе поля
   MathLive не собираются (сцена под окном помечена inert), и щелчки уходят
   в никуда.

   Запуск: node scripts/calc2_canvas_probe.js [порт]                        */
const { chromium } = require('playwright');
const PORT = process.argv[2] || '8601';
const BASE = 'http://127.0.0.1:' + PORT;

let ok = 0, bad = 0;
const say = (pass, text) => { (pass ? ok++ : bad++); console.log((pass ? '✓ ' : '✗ ') + text); };

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));

  await p.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (p.url().includes('login')) {
    await p.fill('input[name="username"]', 'student1');
    await p.fill('input[name="password"]', 'student12345');
    await p.click('button[type=submit], input[type=submit]');
    await p.waitForLoadState('domcontentloaded');
  }
  await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const scene = async (key) => {
    await p.evaluate((k) => { if (typeof closePicker === 'function') closePicker(); resetSceneMemory(); pickScene(k); }, key);
    await p.waitForTimeout(600);
  };
  await scene('sd');

  /* ⚠️ Точку захвата выбираем ПРОВЕРКОЙ, а не серединой окна: над кривой
     лежат кружки ключевых точек, и первая версия прибора три раза щёлкала по
     кружку пересечения. Замер «щелчок ничего не изменил» проходил, ничего при
     этом не измерив. Берём место, где сверху действительно дорожка захвата. */
  const grabPoint = () => p.evaluate(() => {
    const c = STATE.curves.filter(c => c.visible && c.linear)[0];
    if (!c) return null;
    const { mx, my } = mainScales();
    const [q0, q1] = mx.domain();
    const r = document.getElementById('chart').getBoundingClientRect();
    for (let f = 0.2; f <= 0.85; f += 0.03) {
      const q = q0 + (q1 - q0) * f;
      const y = evalCurve(c, q);
      if (!isFinite(y)) continue;
      const x = r.left + mx(q), py = r.top + my(y);
      const top = document.elementFromPoint(x, py);
      if (top && top.tagName === 'path' && top.getAttribute('stroke') === 'transparent')
        return { x, y: py };
    }
    return null;
  });

  // ── п. 24. Щелчок по кривой её не двигает ───────────────────────────
  {
    const before = await p.evaluate(() => STATE.curves.map(c => c.expr).join(' | '));
    const at = await grabPoint();
    if (!at) { say(false, 'п. 24 · свободного места на кривой не нашлось — замерить нечем'); }
    else {
      for (let i = 0; i < 3; i++) await p.mouse.click(at.x, at.y);
      await p.waitForTimeout(200);
      const after = await p.evaluate(() => STATE.curves.map(c => c.expr).join(' | '));
      say(before === after, 'п. 24 · три щелчка по кривой не меняют формулу: ' + after);
      // …а перетаскивание по-прежнему двигает.
      await p.mouse.move(at.x, at.y);
      await p.mouse.down();
      for (let i = 1; i <= 8; i++) await p.mouse.move(at.x, at.y - i * 8);
      await p.mouse.up();
      await p.waitForTimeout(200);
      const dragged = await p.evaluate(() => STATE.curves.map(c => c.expr).join(' | '));
      say(dragged !== after, 'п. 24 · перетаскивание по-прежнему двигает кривую: ' + dragged);
    }
  }

  // ── п. 25. Взведённый режим — единственный хозяин щелчка ─────────────
  await scene('sd');
  {
    await p.evaluate(() => { setAreaCalcMode('poly'); });
    await p.waitForTimeout(200);
    const armed = await p.evaluate(() => ({ mode: canvasMode(), banner: !document.getElementById('cv-mode').hidden }));
    say(armed.mode === 'vert', 'п. 25 · режим холста называется словом: ' + armed.mode);
    say(armed.banner, 'п. 25 · полоса режима видна на холсте');
    const track = await p.evaluate(() => document.querySelectorAll('#chart path[stroke="transparent"]').length);
    say(track === 0, 'п. 25 · дорожка захвата кривой во взведённом режиме не рисуется (дорожек ' + track + ')');

    const at = await p.evaluate(() => {
      const c = STATE.curves.filter(c => c.visible && c.linear)[0];
      const { mx, my } = mainScales();
      const [q0, q1] = mx.domain();
      const q = q0 + (q1 - q0) * 0.72;
      const r = document.getElementById('chart').getBoundingClientRect();
      return { x: r.left + mx(q), y: r.top + my(evalCurve(c, q)) };
    });
    const exprBefore = await p.evaluate(() => STATE.curves.map(c => c.expr).join(' | '));
    await p.mouse.click(at.x, at.y);
    await p.waitForTimeout(200);
    const r = await p.evaluate(() => ({ verts: (STATE.areaVerts || []).length, expr: STATE.curves.map(c => c.expr).join(' | ') }));
    say(r.verts === 1, 'п. 25 · щелчок рядом с кривой ставит вершину (вершин ' + r.verts + ')');
    say(r.expr === exprBefore, 'п. 25 · и не двигает саму кривую');

    // Escape выходит из режима.
    await p.keyboard.press('Escape');
    await p.waitForTimeout(200);
    const off = await p.evaluate(() => ({ mode: canvasMode(), banner: !document.getElementById('cv-mode').hidden }));
    say(off.mode === 'look' && !off.banner, 'п. 25 · Escape выходит из режима и убирает полосу');
  }

  // ── п. 27, 28. Пустое состояние и порядок кнопок ─────────────────────
  await scene('sd');
  {
    await p.evaluate(() => { setAreaCalcMode('poly'); });
    await p.waitForTimeout(200);
    const e = await p.evaluate(() => {
      const box = document.getElementById('ac-verts-empty');
      const list = document.getElementById('ac-verts');
      const btns = document.getElementById('ac-vert-btns');
      const pos = (a, bEl) => (a.compareDocumentPosition(bEl) & Node.DOCUMENT_POSITION_FOLLOWING) ? 'после' : 'до';
      return {
        cls: box.className,
        head: (box.querySelector('b') || {}).textContent || '',
        text: (box.querySelector('p') || {}).textContent || '',
        clearAfterList: pos(list, btns),
        armHidden: (document.getElementById('ac-vert-arm') || {}).hidden,
      };
    });
    say(e.cls === 'k-empty' && e.head && e.text.length > 30,
        'п. 27 · пустое состояние по канону 3.13: «' + e.head + '»');
    say(e.clearAfterList === 'после', 'п. 28 · «Убрать все вершины» стоит ПОД списком');
    say(e.armHidden === true, 'п. 25 · пока набор идёт, второй кнопки «закончить» в панели нет');
  }

  // ── п. 29. Имя вершины устаревает вместе с картинкой ─────────────────
  await scene('sd');
  {
    const r = await p.evaluate(() => {
      setAreaCalcMode('poly');
      const k = keyTargets().filter(t => /пересечение/.test(t.name))[0];
      if (!k) return { skip: true };
      addAreaVert(k.x, k.y, k.name);
      const named = STATE.areaVerts[0].name;
      // Двигаем спрос: пересечение уезжает, координаты вершины остаются.
      const d = STATE.curves.filter(c => c.linear)[0];
      setCurveFreeTerm(d, d.linear.b - 20);
      return { named, after: STATE.areaVerts[0].name, x: STATE.areaVerts[0].x };
    });
    if (r.skip) say(false, 'п. 29 · на сцене нет пересечения — замерить нечем');
    else {
      say(!!r.named, 'п. 29 · вершина в особой точке получает имя: «' + r.named + '»');
      say(r.after === '', 'п. 29 · после сдвига кривых имя снято, координаты целы (x = ' + r.x.toFixed(2) + ')');
    }
    const num = await p.evaluate(() => {
      const g = document.querySelector('#chart g.area-verts');
      if (!g) return null;
      const t = Array.from(g.querySelectorAll('text')).filter(t => /^\d+$/.test(t.textContent.trim()))[0];
      const c = g.querySelector('circle');
      if (!t || !c) return null;
      const a = t.getBoundingClientRect(), bb = c.getBoundingClientRect();
      return Math.round(Math.hypot(a.left + a.width / 2 - (bb.left + bb.width / 2),
                                   a.top + a.height / 2 - (bb.top + bb.height / 2)));
    });
    say(num !== null && num <= 22, 'п. 29 · номер стоит вплотную к точке: ' + num + ' px');
  }

  // ── п. 26. Самопересекающийся обход называется вслух ─────────────────
  await scene('sd');
  {
    const r = await p.evaluate(() => {
      setAreaCalcMode('poly');
      // Девять вершин зигзагом: перебор невозможен, обход по кругу пересекается.
      const pts = [[10,10],[90,90],[20,80],[80,20],[15,50],[85,55],[45,95],[50,5],[70,70]];
      pts.forEach(([x, y]) => addAreaVert(x, y, ''));
      runAreaCalc();
      const res = STATE.areaCalcList[STATE.areaCalcList.length - 1];
      const note = document.querySelector('#info-areacalc .area-note');
      // Спрашиваем ИМЕННО число площади: остальные подсказки панели снимает
      // фаза 8 вместе со всей системой подсказок, и мешать их сюда нельзя.
      const val = document.querySelector('#info-areacalc .area-approx');
      return { exact: res && res.exact, crosses: res && res.crosses,
               note: note ? note.textContent.trim() : '', title: !!(val && val.getAttribute('title')) };
    });
    say(r.exact === false, 'п. 26 · девять вершин считаются приближением');
    say(r.note.length > 20, 'п. 26 · оговорка видна на экране строкой: «' + r.note.slice(0, 60) + '…»');
    say(!r.title, 'п. 26 · оговорка не спрятана в подсказку браузера');
  }

  // ── п. 32. Координата названа буквой оси; цвет точки не повторяет кривую ──
  await scene('sd');
  {
    const r = await p.evaluate(() => {
      startMarkDraft();
      const row = document.querySelector('.mark-row.mark-draft');
      const labels = Array.from(row.querySelectorAll('.edval')).map(e => e.textContent.replace(/\s+/g, ' ').trim());
      return { labels, xDef: STATE.axisXDefault, yDef: STATE.axisYDefault };
    });
    const hasAxis = r.labels.some(t => t.indexOf('Q') === 0) && r.labels.some(t => t.indexOf('P') === 0);
    say(hasAxis, 'п. 32 · координата подписана буквой оси: ' + r.labels.join(' · '));

    const c = await p.evaluate(() => {
      cancelMarkDraft();
      addMarkAt(30, 30, null);
      const mk = STATE.marks[STATE.marks.length - 1];
      const near = drawnStrokeColors().map(s => Math.round(colorDist(normHex(mk.color), s)));
      return { color: mk.color, min: Math.min.apply(null, near) };
    });
    say(c.min >= 90, 'п. 32 · цвет новой точки далёк от нарисованных кривых: ' + c.color + ', ближайшая ' + c.min);
  }

  /* ── п. 33. Возможности холста названы в интерфейсе ──────────────────
     Спрашиваем два разных вопроса. Первый: не осталось ли на холсте ВОЗМОЖНОСТИ,
     о которой знает только подсказка браузера. Второй: сказано ли о ней там,
     где ею управляют. Имя фигуры (полное название аббревиатуры легенды) под
     запрет не попадает: строка легенды ничего не делает по нажатию. */
  await scene('m-minmax');
  {
    const t = await p.evaluate(() => {
      STATE.graphTitle = 'Проба';
      redrawAll();
      return Array.from(document.querySelectorAll('#chart title'))
        .map(t => t.textContent.trim())
        .filter(s => /щелч|Потяните|список точек|перенес|переимен|Ведите/i.test(s));
    });
    say(t.length === 0, 'п. 33 · на холсте не осталось возможностей в подсказке браузера (' + t.length + ')');
    const said = await p.evaluate(() => {
      const marks = (document.getElementById('hp-marks') || {}).textContent || '';
      const note = (document.querySelector('.wrench-note') || {}).textContent || '';
      return { marks, note };
    });
    say(/двойн/i.test(said.marks) && /значок/i.test(said.marks),
        'п. 33 · переименование и закрепка названы в подсказке блока точек');
    say(/двойн/i.test(said.note) && /перенес/i.test(said.note),
        'п. 33 · перенос названия графика назван рядом с полем названия');
  }

  console.log('\n=== холст: ' + ok + ' прошло, ' + bad + ' провалено; ошибок страницы ' + errs.length + ' ===');
  errs.slice(0, 5).forEach(e => console.log('  ОШИБКА: ' + e));
  await b.close();
  process.exit(bad || errs.length ? 1 : 0);
})();
