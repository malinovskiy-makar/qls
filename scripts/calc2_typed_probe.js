/* ФАЗА 1, добавка. ЗАМЕР «ПОСТРОЕНИЯ ГРАФИКОВ» С ВПИСАННОЙ ФУНКЦИЕЙ.

   Общая опись снимает сцены такими, какими они открываются. Три вопроса
   ревью так не снимаются вовсе, потому что относятся к состоянию ПОСЛЕ ввода:
     · появляется ли у вписанной кривой дорожка захвата (фазы 2 и 4);
     · чем нарисована строка, добавившаяся сама (фаза 7);
     · равны ли по высоте поле и кнопка клавиатуры, когда у слота уже есть
       место под сообщение об ошибке (фаза 7).

   Запуск: node scripts/calc2_typed_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/typed.json';
const BASE = `http://127.0.0.1:${PORT}`;

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
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  await page.evaluate(() => pickScene('m-graph'));
  await page.waitForTimeout(1100);
  /* Идентификатор блока не угадываем: спрашиваем у самой разметки, в какой
     секции лежит список строк. Первая версия открывала выдуманный `sec-graph-rows`,
     блок оставался закрытым, и все высоты приезжали нулями. */
  await page.evaluate(() => {
    const box = document.getElementById('graph-rows');
    const sec = box && box.closest('.section');
    if (sec && sec.id) openSection(sec.id);
  });
  await page.waitForTimeout(500);

  /* Вписываем функцию тем же путём, каким её вписывает человек: в поле строки. */
  const typed = await page.evaluate(() => {
    const inp = document.querySelector('#graph-rows .f-slot > input');
    if (!inp) return 'нет поля';
    inp.value = 'x';
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    return 'ок';
  });
  await page.waitForTimeout(1100);

  const shot = await page.evaluate(() => {
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      if (r.width < 0.5 || r.height < 0.5) return false;
      const c = getComputedStyle(el);
      return c.visibility !== 'hidden' && c.display !== 'none';
    };
    /* Строку списка рисует `.grow`, а `.f-row` появляется внутри неё только
       после того, как поле стало математическим. Спрашиваем именно `.grow`:
       иначе строка, оставшаяся обычным полем, в замер не попадёт вовсе —
       а она и есть предмет пункта ревью. */
    const rows = Array.from(document.querySelectorAll('#graph-rows .grow')).map(r => {
      const kbd = r.querySelector('.f-kbd');
      const mf  = r.querySelector('math-field');
      const inp = r.querySelector('.f-slot > input');
      const why = r.querySelector('.f-why');
      const ed  = r.querySelector('.f-slot .edval');
      const ph  = mf ? (mf.getAttribute('placeholder') || '') : (inp ? inp.placeholder : '');
      const rect = (el) => el ? +el.getBoundingClientRect().height.toFixed(1) : null;
      // Обрезан ли образец многоточием: сравниваем прокрутку с шириной.
      let clipped = null;
      const holder = ed || mf || inp;
      if (holder) clipped = holder.scrollWidth > holder.clientWidth + 1;
      return { kbd: rect(kbd), field: rect(mf || inp), slot: rect(r.querySelector('.f-slot')),
               hasWhy: !!why, hasMathField: !!mf, hasFRow: !!r.querySelector('.f-row'),
               edval: ed ? ed.className : null, filled: !!r.dataset.cid,
               html: r.innerHTML.replace(/\s+/g, ' ').slice(0, 200),
               placeholder: ph, clipped };
    });
    const bands = Array.from(document.querySelectorAll('g.curves path')).map(p => {
      const c = getComputedStyle(p);
      return { cursor: c.cursor, width: +(parseFloat(c.strokeWidth) || 0).toFixed(2),
               skip: p.getAttribute('data-skip-export') === '1',
               curveId: p.getAttribute('data-curve') || null };
    });
    const kEmpty = Array.from(document.querySelectorAll('.k-empty'))
      .filter(el => vis(el) && /Пока ни одной функции/.test(el.textContent)).length;
    return { rows, bands, kEmpty,
             curves: STATE.curves.map(c => ({ expr: c.expr, linear: !!c.linear })) };
  });

  fs.writeFileSync(OUT, JSON.stringify({ typed, shot, pageErrors: errs }, null, 1), 'utf8');
  console.log(JSON.stringify(shot, null, 1));
  console.log('ошибок страницы:', errs.length);
  await browser.close();
})();
