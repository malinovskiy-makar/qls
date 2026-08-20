/* ФАЗА 4. ПЕРЕТАСКИВАНИЕ КРИВЫХ И ОТМЕНА.

   Главное, что проверяется: запись функции не врёт. Кривую тянут НАСТОЯЩЕЙ
   мышью и сверяют три вещи разом — что нарисовано, что лежит в состоянии и
   что написано в поле панели.

   Запуск: node scripts/calc2_drag_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/drag.json';
const BASE = `http://127.0.0.1:${PORT}`;

const ok = [], bad = [];
const check = (c, w) => (c ? ok : bad).push(w);

const spotOf = (name) => {
  const svgEl = document.querySelector('#chart');
  const box = svgEl.getBoundingClientRect();
  const band = Array.from(document.querySelectorAll('path[data-hit-name]'))
    .filter(p => p.getAttribute('data-hit-name') === name)[0];
  if (!band) return null;
  const L = band.getTotalLength();
  for (let i = 20; i <= 80; i += 2) {
    const pt = band.getPointAtLength(L * i / 100);
    const m = band.getScreenCTM();
    const sx = pt.x * m.a + pt.y * m.c + m.e, sy = pt.x * m.b + pt.y * m.d + m.f;
    if (sx < box.left + 40 || sx > box.right - 40 || sy < box.top + 60 || sy > box.bottom - 60) continue;
    if (document.elementFromPoint(sx, sy) === band) return { x: sx, y: sy };
  }
  return null;
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
  const open = async (key) => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(1000);
  };

  // ── 1. Вписанная функция мышью НЕ двигается ───────────────────────────
  await open('m-graph');
  await page.evaluate(() => {
    const box = document.getElementById('graph-rows');
    if (box) openSection(box.closest('.section').id);
  });
  await page.waitForTimeout(400);
  await page.evaluate(() => {
    const inp = document.querySelector('#graph-rows .f-slot > input');
    inp.value = 'x';
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(900);
  const typedState = await page.evaluate(() => ({
    expr: STATE.curves[0] && STATE.curves[0].expr,
    hand: !!(STATE.curves[0] && STATE.curves[0].handTyped),
    cursor: (() => {
      const b = document.querySelector('path[data-hit-name]');
      return b ? getComputedStyle(b).cursor : null;
    })(),
  }));
  check(typedState.hand, 'вписанная функция помечена как «вписал человек»');
  check(typedState.cursor === 'pointer',
        'курсор над вписанной функцией не обещает перетаскивания: ' + typedState.cursor);
  /* ⚠️ Имя кривой берём У РАЗМЕТКИ. Первая версия искала полосу по имени «x»
     (по формуле), а полоса подписана коротким именем кривой, и совпасть они
     не обязаны — прибор не находил ничего и объявлял это дефектом. */
  const typedName = await page.evaluate(() => {
    const b = document.querySelector('path[data-hit-name]');
    return b ? b.getAttribute('data-hit-name') : null;
  });
  const sp = typedName ? await page.evaluate(spotOf, typedName) : null;
  check(!!sp, 'нашлось место на вписанной прямой (имя полосы «' + typedName + '»)');
  if (sp) {
    await page.mouse.move(sp.x, sp.y);
    await page.mouse.down();
    for (let i = 1; i <= 8; i++) await page.mouse.move(sp.x, sp.y + i * 11);
    await page.mouse.up();
    await page.waitForTimeout(700);
    const after = await page.evaluate(() => ({
      expr: STATE.curves[0] && STATE.curves[0].expr,
      b: STATE.curves[0] && STATE.curves[0].linear && STATE.curves[0].linear.b,
    }));
    check(after.expr === 'x' && Math.abs(after.b || 0) < 1e-9,
          'вписанная прямая не сдвинулась: формула «' + after.expr + '», свободный член ' + after.b);
  }

  // ── 2. «Спрос и предложение»: кривые не двигаются ─────────────────────
  await open('sd');
  const sdCur = await page.evaluate(() =>
    Array.from(document.querySelectorAll('path[data-hit-name]'))
      .map(b => ({ n: b.getAttribute('data-hit-name'), c: getComputedStyle(b).cursor })));
  check(sdCur.length >= 2 && sdCur.every(x => x.c === 'pointer'),
        'в «Спросе и предложении» ни одна кривая не обещает перетаскивания: ' +
        JSON.stringify(sdCur));
  const sdBefore = await page.evaluate(() => STATE.curves.map(c => c.expr).join(' | '));
  const sdSpot = await page.evaluate(spotOf, 'D');
  if (sdSpot) {
    await page.mouse.move(sdSpot.x, sdSpot.y);
    await page.mouse.down();
    for (let i = 1; i <= 8; i++) await page.mouse.move(sdSpot.x, sdSpot.y + i * 10);
    await page.mouse.up();
    await page.waitForTimeout(600);
    const sdAfter = await page.evaluate(() => STATE.curves.map(c => c.expr).join(' | '));
    check(sdBefore === sdAfter, 'формулы «Спроса и предложения» не изменились: ' + sdAfter);
  }
  const sliders = await page.evaluate(() => {
    const box = document.getElementById('params-curves');
    return { inBox: box ? box.querySelectorAll('input[type=range]').length : -1,
             fromList: typeof pultCurveList === 'function' ? pultCurveList().length : -1 };
  });
  check(sliders.inBox >= 2,
        'ползунки D и S на месте: в панели ' + sliders.inBox + ', в списке ' + sliders.fromList);

  // ── 3. Там, где сдвиг остался, формула переписывается честно ──────────
  await open('ceil');
  const dragName = await page.evaluate(() =>
    (Array.from(document.querySelectorAll('path[data-hit-name]'))
      .filter(b => getComputedStyle(b).cursor === 'ns-resize')[0] || {})
      .getAttribute && Array.from(document.querySelectorAll('path[data-hit-name]'))
      .filter(b => getComputedStyle(b).cursor === 'ns-resize')[0].getAttribute('data-hit-name'));
  check(!!dragName, 'в «Потолке цены» есть подвижная кривая: ' + dragName);
  if (dragName) {
    const s2 = await page.evaluate(spotOf, dragName);
    if (s2) {
      await page.mouse.move(s2.x, s2.y);
      await page.mouse.down();
      for (let i = 1; i <= 8; i++) await page.mouse.move(s2.x, s2.y + i * 9);
      await page.mouse.up();
      await page.waitForTimeout(700);
      const st = await page.evaluate((nm) => {
        const c = STATE.curves.filter(c => curveShortName(c) === nm)[0];
        const field = Array.from(document.querySelectorAll('.curve-expr-inp'))
          .map(i => i.value);
        // Что НАРИСОВАНО: берём y кривой в середине окна прямо у её функции.
        const t = snapTargets().filter(t => t.name === nm)[0];
        const s = mainScales(); const [lo, hi] = s.mx.domain();
        const xm = lo + (hi - lo) / 2;
        return { expr: c.expr, b: c.linear.b, drawn: t ? t.f(xm) : null,
                 fromExpr: c.compiled ? null : null, fields: field, xm: xm, a: c.linear.a };
      }, dragName);
      const dec = String(st.b).split('.')[1] || '';
      check(dec.length <= 3, 'свободный член округлён до тысячных: ' + st.b);
      check(String(st.expr).indexOf(String(st.b)) >= 0,
            'в формуле стоит ровно то число, что в расчёте: «' + st.expr + '» при b = ' + st.b);
      const want = st.a * st.xm + st.b;
      check(Math.abs(st.drawn - want) < 1e-6,
            'нарисованная кривая совпадает с записанной формулой (' +
            st.drawn.toFixed(4) + ' против ' + want.toFixed(4) + ')');
      check(st.fields.indexOf(st.expr) >= 0,
            'поле формулы в панели показывает ту же запись: ' + JSON.stringify(st.fields));

      // ── 4. Отмена возвращает на шаг назад ──────────────────────────────
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+z' : 'Control+z');
      await page.waitForTimeout(600);
      const undone = await page.evaluate((nm) => {
        const c = STATE.curves.filter(c => curveShortName(c) === nm)[0];
        return { expr: c.expr, b: c.linear.b };
      }, dragName);
      check(Math.abs(undone.b - st.b) > 1e-9,
            'отмена вернула прежнюю формулу: было «' + st.expr + '» (b=' + st.b +
            '), стало «' + undone.expr + '» (b=' + undone.b + ')');
    }
  }

  // ── 5. Значение параметра перетаскиванием не меняется ─────────────────
  await open('m-graph');
  await page.evaluate(() => {
    const box = document.getElementById('graph-rows');
    if (box) openSection(box.closest('.section').id);
  });
  await page.waitForTimeout(400);
  await page.evaluate(() => {
    const inp = document.querySelector('#graph-rows .f-slot > input');
    inp.value = '2 - a*x';
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(1000);
  const par = await page.evaluate(() => ({
    has: !!(STATE.params && STATE.params.a),
    val: STATE.params && STATE.params.a ? STATE.params.a.value : null,
    cursor: (() => {
      const b = document.querySelector('path[data-hit-name]');
      return b ? getComputedStyle(b).cursor : null;
    })(),
  }));
  check(par.has, 'буква-параметр завелась: a = ' + par.val);
  check(par.cursor === 'pointer', 'кривая с параметром не обещает перетаскивания: ' + par.cursor);

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 4 ─────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  errs.slice(0, 5).forEach(e => console.log('  ОШИБКА: ' + e));
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
