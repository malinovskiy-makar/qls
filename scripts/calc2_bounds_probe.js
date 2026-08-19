/* ФАЗА 9. ГРАНИЦЫ ПОЛЗУНКА.

   Полный цикл ведётся настоящими щелчками и настоящим набором с клавиатуры:
   предмет фазы — поведение под рукой человека.

   Запуск: node scripts/calc2_bounds_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/bounds.json';
const BASE = `http://127.0.0.1:${PORT}`;
const ok = [], bad = [];
const check = (c, w) => (c ? ok : bad).push(w);

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
  const setup = async () => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(() => pickScene('m-graph'));
    await page.waitForTimeout(1000);
    await page.evaluate(() => {
      const box = document.getElementById('graph-rows');
      if (box) openSection(box.closest('.section').id);
      const inp = document.querySelector('#graph-rows .f-slot > input, #graph-rows .f-slot math-field');
      if (inp && inp.tagName === 'INPUT') { inp.value = 'x^2-a*x'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    });
    await page.waitForTimeout(1200);
  };
  const band = () => page.evaluate(() => {
    const p = STATE.params && STATE.params.a;
    return p ? { min: +p.min.toFixed(3), max: +p.max.toFixed(3), value: +p.value.toFixed(3) } : null;
  });
  const clickBound = async (which) => {
    const b = await page.evaluate((w) => {
      const bs = document.querySelectorAll('.pchip-param .param-bound');
      const el = bs[w === 'hi' ? 1 : 0];
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }, which);
    if (!b) return false;
    await page.mouse.click(b.x, b.y);
    await page.waitForTimeout(350);
    return true;
  };

  await setup();
  check(!!(await band()), 'ползунок параметра появился: ' + JSON.stringify(await band()));

  // ── 1–3. Щелчок по левой границе ─────────────────────────────────────
  await clickBound('lo');
  const st = await page.evaluate(() => {
    const chip = document.querySelector('.pchip-param');
    const track = chip.querySelector('.param-track');
    const ed = chip.querySelector('.param-editor');
    const fields = ed ? Array.from(ed.querySelectorAll('.edval')) : [];
    const eq = chip.querySelector('.pchip-label');
    return {
      trackHidden: track ? getComputedStyle(track).display === 'none' : null,
      editorOpen: ed ? ed.classList.contains('open') : false,
      fieldCount: fields.length,
      texts: fields.map(f => f.textContent.trim()),
      focusedIndex: fields.findIndex(f => f.classList.contains('editing') || f === document.activeElement),
      eqVisible: eq ? getComputedStyle(eq).display !== 'none' : null,
      eqText: eq ? eq.textContent.replace(/\s+/g, ' ').trim() : null,
    };
  });
  check(st.editorOpen, 'щелчок по границе раскрыл редактор');
  check(st.trackHidden === true, 'полоса ползунка и подписи границ убраны');
  check(st.fieldCount === 3, 'три поля: две границы и шаг (' + st.fieldCount + ')');
  check(st.texts.every(t => t === '' || /^[—–-]?$/.test(t)),
        'все три поля пустые: ' + JSON.stringify(st.texts));
  check(st.focusedIndex === 0, 'курсор в левом поле (щёлкнули по левой границе), индекс ' + st.focusedIndex);
  check(st.eqVisible !== false, 'значение «a = …» осталось над редактором: «' + st.eqText + '»');

  // ── 5, 6. Вписали −5 в левое, Enter ──────────────────────────────────
  await page.keyboard.type('-5');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(450);
  let b = await band();
  check(b && Math.abs(b.min + 5) < 1e-6 && Math.abs(b.max - 10) < 1e-6,
        'левая граница стала −5, правая сохранилась: ' + JSON.stringify(b));

  // ── 3б. Щелчок по правой границе ставит курсор в правое поле ─────────
  await clickBound('hi');
  const st2 = await page.evaluate(() => {
    const fields = Array.from(document.querySelectorAll('.pchip-param .param-editor .edval'));
    return fields.findIndex(f => f.classList.contains('editing') || f === document.activeElement);
  });
  check(st2 === 1, 'курсор в правом поле (щёлкнули по правой границе), индекс ' + st2);

  // щелчок мимо применяет, а не отменяет
  await page.keyboard.type('3');
  await page.mouse.click(700, 500);
  await page.waitForTimeout(500);
  b = await band();
  check(b && Math.abs(b.max - 3) < 1e-6, 'щелчок мимо применил правую границу: ' + JSON.stringify(b));

  // ── 7. Значение за полосой: границы переезжают, значение в центре ────
  await page.evaluate(() => {
    const lab = document.querySelector('.pchip-param .pchip-label');
    lab.click();
  });
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    const inp = document.querySelector('.pchip-param .param-eq-input');
    if (inp) { inp.value = '50'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  b = await band();
  check(b && Math.abs(b.min - 46) < 1e-6 && Math.abs(b.max - 54) < 1e-6 && Math.abs(b.value - 50) < 1e-6,
        'значение 50 при полосе −5…3 дало границы 46…54: ' + JSON.stringify(b));

  // ── 8. Границы без текущего значения: подтягивается значение ─────────
  await page.evaluate(() => { STATE.params.a.value = 6; STATE.params.a.min = -10; STATE.params.a.max = 10; redrawAll(); });
  await page.waitForTimeout(400);
  await clickBound('lo');
  await page.keyboard.type('-1');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(350);
  await clickBound('hi');
  await page.keyboard.type('1');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  b = await band();
  check(b && Math.abs(b.min + 1) < 1e-6 && Math.abs(b.max - 1) < 1e-6 && Math.abs(b.value - 1) < 1e-6,
        'границы −1…1 при значении 6 дали значение 1: ' + JSON.stringify(b));

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 9 ─────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  errs.slice(0, 4).forEach(e => console.log('  ОШИБКА: ' + e));
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
