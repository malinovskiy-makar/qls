/* ФАЗА 10. «КЛЮЧЕВЫЕ ЗНАЧЕНИЯ».

   Обход всех сцен: одна строка на значение, один формат, разделитель списка не
   спорит с десятичным знаком, панель не расширена.

   Запуск: node scripts/calc2_stats_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/stats.json';
const BASE = `http://127.0.0.1:${PORT}`;

const snap = () => {
  const vis = (el) => el.getBoundingClientRect().height > 1;
  const panel = document.querySelector('.sb-body');
  const rows = Array.from(document.querySelectorAll('.stat')).filter(vis);
  const one = 20;                      // высота одной строки с отступами, px
  return {
    panelW: panel ? +panel.getBoundingClientRect().width.toFixed(1) : null,
    rows: rows.map(r => {
      const cs = getComputedStyle(r);
      const lab = r.querySelector(':scope > span');
      const val = r.querySelector(':scope > b');
      const sign = r.querySelector(':scope > .stat-sign');
      const labCs = lab ? getComputedStyle(lab) : null;
      /* ⚠️ «ОДНА СТРОКА НА ЗНАЧЕНИЕ» — ЭТО НЕ ПРО ВЫСОТУ В ПИКСЕЛЯХ.
         Длинное значение («Наибольшее y* = 18 при x* = 3») законно
         переносится и занимает две строчки — так и задумано макетом. Жалоба
         владельца была о другом: подпись, знак и число вставали КАЖДОЕ на
         своей строке. Значит и мерить надо это: стоят ли подпись, знак и
         значение на одной линии. */
      const top = (el) => el ? Math.round(el.getBoundingClientRect().top) : null;
      const sameLine = (lab && val)
        ? Math.abs(top(lab) - top(val)) <= 4 && (!sign || Math.abs(top(lab) - top(sign)) <= 4)
        : null;
      return {
        sameLine,
        h: +r.getBoundingClientRect().height.toFixed(1),
        display: cs.display,
        justify: cs.justifyContent,
        labAlign: labCs ? labCs.textAlign : null,
        hasSign: !!sign,
        nosign: r.classList.contains('stat-nosign'),
        // значение стоит сразу за знаком, а не у правого края
        gap: (sign && val) ? +(val.getBoundingClientRect().left -
                               sign.getBoundingClientRect().right).toFixed(1) : null,
        rightGap: val ? +(r.getBoundingClientRect().right -
                          val.getBoundingClientRect().right).toFixed(1) : null,
        text: r.textContent.replace(/\s+/g, ' ').trim().slice(0, 50),
      };
    }),
    tallRows: rows.filter(r => r.getBoundingClientRect().height > one * 2.2).length,
    crossRow: rows.filter(r => /Кривые пересекаются/.test(r.textContent)).length,
    curves: (typeof snapTargets === 'function') ? snapTargets().length : null,
  };
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
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));

  const res = {};
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(900);
    if (key === 'm-graph') {
      await page.evaluate(() => {
        const box = document.getElementById('graph-rows');
        if (box) openSection(box.closest('.section').id);
        const i = document.querySelector('#graph-rows .f-slot > input');
        if (i) { i.value = 'x^2-x'; i.dispatchEvent(new Event('input', { bubbles: true })); }
      });
      await page.waitForTimeout(800);
    }
    await page.evaluate(() => {
      document.querySelectorAll('#tools-panel .section, #params-panel .section, .sb .section')
        .forEach(sec => { if (sec.id) openSection(sec.id); });
      document.querySelectorAll('.fold-btn').forEach(b => {
        if (b.getAttribute('aria-expanded') === 'false') b.click();
      });
    });
    await page.waitForTimeout(500);
    res[key] = await page.evaluate(snap);
    process.stdout.write('.');
  }
  console.log('');
  fs.writeFileSync(OUT, JSON.stringify({ scenes: res, pageErrors: errs }, null, 1), 'utf8');

  const all = [];
  Object.keys(res).forEach(k => res[k].rows.forEach(r => all.push({ scene: k, ...r })));
  /* Жалоба владельца была количественной: «пять значений дают пятнадцать
     строк», то есть подпись, знак и число вставали КАЖДОЕ на своей строке.
     Двухстрочная запись длинного значения этим дефектом не была и макетом
     прямо разрешена. Поэтому считаем строки в ТРИ текстовых строчки и выше —
     ровно то, что было до правки у всех 217 строк разом. */
  const LINE = 19;
  const tall = all.filter(r => r.h >= LINE * 3);
  const noSign = all.filter(r => !r.hasSign && !r.nosign);
  const rightAligned = all.filter(r => r.labAlign === 'right');
  const spread = all.filter(r => r.justify === 'space-between');
  const farValue = all.filter(r => r.gap != null && r.gap > 14);
  const widths = Array.from(new Set(Object.values(res).map(v => v.panelW)));
  const badCross = Object.keys(res).filter(k => res[k].crossRow > 0 && (res[k].curves || 0) < 2);
  const commaList = all.filter(r => /\d,\s\d/.test(r.text));

  const line = (name, n, ex) =>
    console.log(name.padEnd(46) + String(n).padStart(4) + (n && ex ? '   ' + ex : ''));
  console.log('\n── ФАЗА 10 ────────────────────────────────────────');
  console.log('строк «Ключевых значений» всего: ' + all.length + ' в ' + Object.keys(res).length + ' сценах');
  console.log('ширина панели: ' + JSON.stringify(widths));
  const maxH = all.reduce((m, r) => Math.max(m, r.h), 0);
  const twoLine = all.filter(r => r.h >= LINE * 2 && r.h < LINE * 3).length;
  line('строк в три строчки и выше', tall.length,
       tall[0] && (tall[0].scene + ' «' + tall[0].text + '» ' + tall[0].h));
  console.log('  (в две строчки: ' + twoLine + ', самая высокая строка: ' + maxH + ' px)');
  line('строк без знака равенства', noSign.length, noSign[0] && (noSign[0].scene + ' «' + noSign[0].text + '»'));
  line('подписей, выровненных по правому краю', rightAligned.length, rightAligned[0] && rightAligned[0].scene);
  line('строк, растянутых по краям', spread.length, spread[0] && spread[0].scene);
  line('значений, отставших от знака', farValue.length, farValue[0] && (farValue[0].scene + ' ' + farValue[0].gap));
  line('«Кривые пересекаются» при одной кривой', badCross.length, badCross.join(', '));
  line('списков с запятой-разделителем', commaList.length, commaList[0] && (commaList[0].scene + ' «' + commaList[0].text + '»'));
  console.log('ошибок страницы: ' + errs.length);
  await browser.close();
})();
