/* ФАЗА 3. ЗАМЕР ВЗВЕДЕНИЯ КРИВОЙ.

   Все проверки делаются НАСТОЯЩИМИ щелчками по живой странице, а не вызовом
   функций: предмет фазы — что происходит под рукой человека, а вызвать
   armCurve() можно и там, где по кривой физически не попасть.

   ⚠️ Место щелчка выбирается проверкой elementFromPoint: посреди окна на
   кривой обычно лежит кружок ключевой точки или чужая полоса, и щелчок ушёл бы
   не туда, а прибор отчитался бы об успехе. Эта ошибка в проекте уже была.

   Запуск: node scripts/calc2_arm_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/arm.json';
const BASE = `http://127.0.0.1:${PORT}`;

const bad = [];
const ok  = [];
const check = (cond, what) => (cond ? ok : bad).push(what);

/* Найти на холсте точку, где под курсором лежит полоса именно этой кривой. */
const spotOf = (name) => {
  const svgEl = document.querySelector('#chart');
  const box = svgEl.getBoundingClientRect();
  const band = Array.from(document.querySelectorAll('path[data-hit-name]'))
    .filter(p => p.getAttribute('data-hit-name') === name)[0];
  if (!band) return null;
  const L = band.getTotalLength();
  for (let i = 10; i <= 90; i += 2) {
    const pt = band.getPointAtLength(L * i / 100);
    const m = band.getScreenCTM();
    const sx = pt.x * m.a + pt.y * m.c + m.e, sy = pt.x * m.b + pt.y * m.d + m.f;
    if (sx < box.left + 4 || sx > box.right - 4 || sy < box.top + 4 || sy > box.bottom - 4) continue;
    const el = document.elementFromPoint(sx, sy);
    if (el === band) return { x: sx, y: sy };
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
  await page.addInitScript(() => { window.__probe = true; });

  const open = async (key) => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(1000);
  };
  const dots = () => page.evaluate(() => document.querySelectorAll('g.crosses circle[r]').length);
  const armed = () => page.evaluate(() => STATE.armedCurve);

  // ── 1. Чистый холст при открытии ──────────────────────────────────────
  const empty = {};
  const scenes = await (async () => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
    return page.evaluate(() => Object.keys(SCENE_ROUTE));
  })();
  for (const key of scenes) {
    await open(key);
    empty[key] = await page.evaluate(() => ({
      crossGroups: document.querySelectorAll('g.crosses').length,
      armed: STATE.armedCurve,
      keyPts: keyTargets().length,
    }));
    process.stdout.write('.');
  }
  console.log('');
  const dirty = Object.keys(empty).filter(k => empty[k].crossGroups > 0);
  check(dirty.length === 0,
        'холст при открытии чист во всех сценах' + (dirty.length ? ' — грязных: ' + dirty.join(', ') : ''));
  const withPts = Object.keys(empty).filter(k => empty[k].keyPts > 0).length;
  check(withPts > 20, 'ключевые точки по-прежнему считаются (сцен с точками: ' + withPts + ')');

  // ── 2. Щелчок по кривой взводит; повторный гасит ──────────────────────
  await open('sd');
  const names = await page.evaluate(() => snapTargets().map(t => t.name));
  check(names.length >= 2, 'в «Спросе и предложении» две кривые: ' + names.join(', '));
  const spot = await page.evaluate(spotOf, names[0]);
  check(!!spot, 'нашлось место, где под курсором именно полоса кривой «' + names[0] + '»');
  if (spot) {
    await page.mouse.click(spot.x, spot.y);
    await page.waitForTimeout(400);
    check((await armed()) === names[0], 'щелчок по кривой взвёл её: ' + (await armed()));
    const n1 = await dots();
    check(n1 > 0, 'у взведённой кривой загорелись ключевые точки: ' + n1);

    // координат при этом нет
    const labs = await page.evaluate(
      () => Array.from(document.querySelectorAll('g.crosses .cross-label'))
        .filter(e => getComputedStyle(e).display !== 'none').length);
    check(labs === 0, 'координаты без наведения не показываются (видимых подписей ' + labs + ')');

    // вторая кривая гасит первую
    const spot2 = await page.evaluate(spotOf, names[1]);
    if (spot2) {
      await page.mouse.click(spot2.x, spot2.y);
      await page.waitForTimeout(400);
      check((await armed()) === names[1], 'щелчок по второй кривой погасил первую и взвёл вторую');
    } else check(false, 'не нашлось места для щелчка по второй кривой');

    // повторный щелчок по той же гасит
    const spot2b = await page.evaluate(spotOf, names[1]);
    if (spot2b) {
      await page.mouse.click(spot2b.x, spot2b.y);
      await page.waitForTimeout(400);
      check((await armed()) === null, 'повторный щелчок по той же кривой погасил её');
    }

    // щелчок по пустому месту гасит
    const spot3 = await page.evaluate(spotOf, names[0]);
    await page.mouse.click(spot3.x, spot3.y);
    await page.waitForTimeout(350);
    const boxc = await page.evaluate(() => {
      const b = document.querySelector('#chart').getBoundingClientRect();
      return { x: b.left + b.width * 0.08, y: b.top + b.height * 0.08 };
    });
    await page.mouse.click(boxc.x, boxc.y);
    await page.waitForTimeout(350);
    check((await armed()) === null, 'щелчок по пустому месту холста погасил кривую');

    // Escape НЕ гасит
    await page.mouse.click(spot3.x, spot3.y);
    await page.waitForTimeout(350);
    const before = await armed();
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    check(before !== null && (await armed()) === before, 'Escape не гасит взведённую кривую');
  }

  // ── 3. Наведение показывает координаты и значок ───────────────────────
  const hov = await page.evaluate(() => {
    const c = document.querySelector('g.crosses .cross-item circle[r]');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  check(!!hov, 'на холсте есть загоревшаяся точка для наведения');
  if (hov) {
    await page.mouse.move(hov.x, hov.y);
    await page.waitForTimeout(320);
    const st = await page.evaluate(() => ({
      labels: Array.from(document.querySelectorAll('g.crosses .cross-label'))
        .filter(e => getComputedStyle(e).display !== 'none').length,
      pins: Array.from(document.querySelectorAll('g.crosses .cross-pin'))
        .filter(e => getComputedStyle(e).display !== 'none').length,
      marks: STATE.marks.length,
    }));
    check(st.labels === 1, 'наведение показало координаты ровно одной точки (' + st.labels + ')');
    check(st.pins === 1, 'рядом с координатами появился значок (' + st.pins + ')');
    check(st.marks === 0, 'наведение НИЧЕГО не вынесло в список точек');

    // увели курсор — не осталось ничего
    await page.mouse.move(hov.x + 260, hov.y + 160);
    await page.waitForTimeout(450);
    const after = await page.evaluate(() => ({
      labels: Array.from(document.querySelectorAll('g.crosses .cross-label'))
        .filter(e => getComputedStyle(e).display !== 'none').length,
      marks: STATE.marks.length,
    }));
    check(after.labels === 0 && after.marks === 0, 'увели курсор — не осталось ни плашки, ни точки');

    // значок выносит точку насовсем
    await page.mouse.move(hov.x, hov.y);
    await page.waitForTimeout(320);
    const pinBox = await page.evaluate(() => {
      const p = document.querySelector('g.crosses .cross-pin rect');
      if (!p) return null;
      const r = p.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    });
    check(!!pinBox, 'значок доступен курсору (плашка пережила переход с точки на значок)');
    if (pinBox) {
      await page.mouse.move(pinBox.x, pinBox.y);
      await page.waitForTimeout(120);
      await page.mouse.click(pinBox.x, pinBox.y);
      await page.waitForTimeout(500);
      check((await page.evaluate(() => STATE.marks.length)) === 1, 'щелчок по значку вынес точку в список');
    }
  }

  // ── 4. Промах по точке на 6–8 px берёт точку, а не кривую ─────────────
  await open('sd');
  const nm0 = (await page.evaluate(() => snapTargets().map(t => t.name)))[0];
  const sp = await page.evaluate(spotOf, nm0);
  await page.mouse.click(sp.x, sp.y);
  await page.waitForTimeout(450);
  const miss = await page.evaluate(() => {
    const c = document.querySelector('g.crosses .cross-item circle[r]');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const out = [];
    [[7, 0], [-7, 0], [0, 7], [0, -7]].forEach(([dx, dy]) => {
      const el = document.elementFromPoint(cx + dx, cy + dy);
      out.push(el && el.closest('.cross-item') ? 'точка' : (el && el.getAttribute('data-hit-name') ? 'кривая' : 'иное'));
    });
    return out;
  });
  check(!!miss && miss.every(v => v === 'точка'),
        'промах по точке на 7 px во все четыре стороны берёт точку: ' + JSON.stringify(miss));

  // ── 5. Пересечение принадлежит обеим кривым ───────────────────────────
  const both = await page.evaluate(() => {
    const t = snapTargets().map(x => x.name);
    const pts = keyTargets();
    const cross = pts.filter(p => p.owners && p.owners.length === 2);
    if (!cross.length) return null;
    const c = cross[0];
    return { owners: c.owners, isPair: t.indexOf(c.owners[0]) >= 0 && t.indexOf(c.owners[1]) >= 0 };
  });
  check(both && both.isPair, 'точка пересечения записана за обеими кривыми: ' +
        (both ? both.owners.join(' и ') : 'пересечений не найдено'));

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, empty, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 3 ─────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  errs.slice(0, 5).forEach(e => console.log('  ОШИБКА: ' + e));
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
