/* ФАЗА 7. ПАНЕЛЬ ВВОДА ФУНКЦИЙ.

   Семь пунктов ревью, все меряются на живой странице.
   Запуск: node scripts/calc2_input_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/input.json';
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
  const open = async (key) => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(1000);
  };

  // ── 1, 2. Двух текстов больше нет ни в одной сцене ─────────────────────
  await open('sd');
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  let emptyBlocks = 0, resetWhy = 0;
  for (const key of scenes) {
    await open(key);
    await page.evaluate(() => {
      document.querySelectorAll('#tools-panel .section').forEach(s => { if (s.id) openSection(s.id); });
    });
    await page.waitForTimeout(350);
    const r = await page.evaluate(() => ({
      empty: Array.from(document.querySelectorAll('.k-empty'))
        .filter(e => /Пока ни одной функции/.test(e.textContent)).length,
      why: document.querySelectorAll('.side-reset__why').length,
      resetBtn: document.querySelectorAll('#scene-reset, .side-reset .btn').length,
    }));
    emptyBlocks += r.empty; resetWhy += r.why;
    if (key === 'sd') check(r.resetBtn > 0, 'кнопка «Вернуть исходный вид» на месте');
    process.stdout.write('.');
  }
  console.log('');
  check(emptyBlocks === 0, 'блока «Пока ни одной функции» нет ни в одной сцене (' + emptyBlocks + ')');
  check(resetWhy === 0, 'пояснения под кнопкой возврата нет ни в одной сцене (' + resetWhy + ')');

  // ── 3, 4, 5, 6. Строки ввода «Построения графиков» ────────────────────
  await open('m-graph');
  await page.evaluate(() => {
    const box = document.getElementById('graph-rows');
    if (box) openSection(box.closest('.section').id);
  });
  await page.waitForTimeout(400);
  await page.evaluate(() => {
    const inp = document.querySelector('#graph-rows .f-slot > input, #graph-rows .f-slot math-field');
    if (inp && inp.tagName === 'INPUT') { inp.value = 'x'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  await page.waitForTimeout(1200);

  const rows = await page.evaluate(() => Array.from(document.querySelectorAll('#graph-rows .grow')).map(r => {
    const kbd = r.querySelector('.f-kbd'), mf = r.querySelector('math-field');
    const h = (el) => el ? +el.getBoundingClientRect().height.toFixed(1) : null;
    const ph = mf ? (mf.getAttribute('placeholder') || '') : '';
    /* ⚠️ Обрезку меряем у ТОГО узла, который её и делает. Первая версия искала
       класс `.ML__placeholder`, которого в теневом дереве нет вовсе, получала
       null — и «нет данных» проходило за «сошлось». Настоящий носитель —
       `.ML__content`: у него и прокрутка, и видимая ширина. */
    let clipped = null, wide = null, room = null;
    if (mf && mf.shadowRoot) {
      const c = mf.shadowRoot.querySelector('.ML__content');
      if (c) { clipped = c.scrollWidth > c.clientWidth + 1; wide = c.scrollWidth; room = c.clientWidth; }
    }
    const name = r.querySelector('.edval-text');
    const nameDash = name ? getComputedStyle(name).borderBottomColor : null;
    return { kbd: h(kbd), field: h(mf), hasMathField: !!mf, placeholder: ph, clipped, wide, room, nameDash };
  }));
  check(rows.length >= 2, 'строк в списке две: заполненная и добавившаяся сама');
  check(rows.every(r => r.hasMathField), 'обе строки — настоящие поля формул: ' +
        rows.map(r => r.hasMathField ? 'да' : 'нет').join(', '));
  check(rows.every(r => r.kbd != null && r.field != null && Math.abs(r.kbd - r.field) < 1.5),
        'кнопка клавиатуры одной высоты с полем: ' +
        rows.map(r => r.kbd + '/' + r.field).join(', '));
  check(rows.every(r => r.placeholder && /Например/.test(r.placeholder)),
        'образец формулы на месте: ' + JSON.stringify(rows.map(r => r.placeholder)));
  check(rows.length > 0 && rows.every(r => r.clipped === false),
        'образец помещается целиком: ' +
        JSON.stringify(rows.map(r => (r.clipped ? 'нет ' : 'да ') + r.wide + '/' + r.room)));
  const rest = rows.map(r => r.nameDash).filter(Boolean);
  check(rest.length > 0 && rest.every(c => /rgba\(0, 0, 0, 0\)|transparent/.test(c)),
        'пунктира под «Именем на графике» в покое нет: ' + JSON.stringify(rest));

  // пунктир под координатами точек НЕ тронут
  await page.evaluate(() => { openSection('sec-view'); });
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    const b = document.querySelector('#mark-list .btn-mark-add');
    if (b) b.click();
  });
  await page.waitForTimeout(400);
  const markDash = await page.evaluate(() => {
    const e = document.querySelector('#mark-list .mark-xy .edval');
    return e ? getComputedStyle(e).borderBottomColor : null;
  });
  check(markDash && !/rgba\(0, 0, 0, 0\)/.test(markDash),
        'пунктир под координатами точек на месте: ' + markDash);

  // ── 5б. Экономическая сцена: свой образец ─────────────────────────────
  await open('sd');
  await page.evaluate(() => { openSection('sec-curves'); });
  await page.waitForTimeout(400);
  const econ = await page.evaluate(() => {
    const mf = document.querySelector('#inp-formula');
    const holder = mf && mf._mf ? mf._mf : mf;
    return holder ? (holder.getAttribute('placeholder') || holder.placeholder || '') : null;
  });
  check(econ && /100|Q/.test(econ), 'в экономической сцене свой образец: «' + econ + '»');

  // ── 7. Подсказка «Ко всем моделям» ничего не закрывает ────────────────
  await open('sd');
  const tip = await page.evaluate(async () => {
    const back = document.getElementById('scene-back');
    back.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }));
    await new Promise(r => setTimeout(r, 350));
    const t = document.getElementById('hint-tip');
    if (!t || getComputedStyle(t).display === 'none') return { shown: false };
    const tr = t.getBoundingClientRect();
    const hits = Array.from(document.querySelectorAll('button, input, select, a[href]'))
      .filter(el => el !== back && !el.contains(back) && !back.contains(el))
      .filter(el => {
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return false;
        return tr.left < r.right - 1 && tr.right > r.left + 1 &&
               tr.top < r.bottom - 1 && tr.bottom > r.top + 1;
      })
      .map(el => (el.textContent || el.id || el.className || '').trim().slice(0, 28));
    return { shown: true, text: t.textContent.trim(), hits };
  });
  check(tip.shown, 'подсказка «Ко всем моделям» показывается: «' + (tip.text || '') + '»');
  check(tip.shown && tip.hits.length === 0,
        'и не накрывает ни одной кнопки: ' + JSON.stringify(tip.hits || []));

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, rows, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 7 ─────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
