/* ФАЗА 11. КАРТОЧКИ БЛОКОВ И ЧЕКБОКСЫ.

   Запуск: node scripts/calc2_cards_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/cards.json';
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
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  await page.waitForTimeout(900);

  // ── А. Первый экран ───────────────────────────────────────────────────
  const cards = await page.evaluate(() => {
    const cs = Array.from(document.querySelectorAll('.bcard'));
    return cs.map(c => {
      const r = c.getBoundingClientRect();
      const nm = c.querySelector('.bcard-name'), ct = c.querySelector('.bcard-count');
      const sp = c.querySelector('.bcard-spec');
      const nmCs = nm ? getComputedStyle(nm) : null, ctCs = ct ? getComputedStyle(ct) : null;
      const spR = sp ? sp.getBoundingClientRect() : null;
      // Пустое место под текстом: низ карточки минус низ самого нижнего текста.
      const texts = [nm, ct].filter(Boolean).map(e => e.getBoundingClientRect().bottom);
      const pad = parseFloat(getComputedStyle(c).paddingBottom) || 0;
      return {
        h: +r.height.toFixed(1),
        name: nm ? nm.textContent.trim() : null,
        count: ct ? ct.textContent.trim() : null,
        nameSize: nmCs ? nmCs.fontSize : null, nameWeight: nmCs ? nmCs.fontWeight : null,
        countSize: ctCs ? ctCs.fontSize : null, countWeight: ctCs ? ctCs.fontWeight : null,
        countColor: ctCs ? ctCs.color : null,
        thumb: spR ? [+spR.width.toFixed(0), +spR.height.toFixed(0)] : null,
        thumbLeft: spR && nm ? spR.left < nm.getBoundingClientRect().left : null,
        empty: +(r.bottom - pad - Math.max(...texts)).toFixed(1),
        hasList: !!c.querySelector('.bcard-list'),
      };
    });
  });
  const heights = Array.from(new Set(cards.map(c => c.h)));
  check(cards.length === 10, 'карточек блоков десять: ' + cards.length);
  check(heights.length === 1, 'высота у всех одна: ' + JSON.stringify(heights));
  check(heights[0] >= 100 && heights[0] <= 124, 'высота около 110 px: ' + heights[0]);
  check(cards.every(c => !c.hasList), 'серого перечня моделей нет ни на одной карточке');
  check(cards.every(c => c.thumb && c.thumb[0] === 132 && c.thumb[1] === 82),
        'картинка 132×82: ' + JSON.stringify(Array.from(new Set(cards.map(c => JSON.stringify(c.thumb))))));
  check(cards.every(c => c.thumbLeft), 'компоновка горизонтальная: картинка слева от названия');
  check(cards.every(c => c.nameSize === '18px' && c.nameWeight === '600'),
        'название 18 px, вес 600: ' + cards[0].nameSize + '/' + cards[0].nameWeight);
  check(cards.every(c => c.countSize === '13px' && c.countWeight === '400'),
        'счётчик 13/400: ' + cards[0].countSize + '/' + cards[0].countWeight);
  check(cards.every(c => /модел/.test(c.count || '')),
        'надпись «N моделей» сохранена: ' + JSON.stringify(cards.slice(0, 3).map(c => c.count)));
  check(cards.some(c => /из \d/.test(c.count || '')),
        'форма «N моделей из M» тоже сохранена: ' +
        (cards.filter(c => /из \d/.test(c.count || '))'))[0] || {}).count);
  const maxEmpty = Math.max(...cards.map(c => c.empty));
  check(maxEmpty < 26, 'пустого места под названием не остаётся: не больше ' + maxEmpty.toFixed(1) + ' px');

  // ── А2. Второй экран не тронут ────────────────────────────────────────
  const second = await page.evaluate(() => {
    const c = document.querySelector('.bcard');
    c.click();
    return new Promise(res => setTimeout(() => {
      const g = document.querySelector('.scene-grid.open, .picker-grid.open') ||
                document.querySelector('.scard') && document.querySelector('.scard').parentElement;
      const cards = g ? Array.from(g.querySelectorAll('.scard')) : [];
      res({
        count: cards.length,
        withDesc: cards.filter(s => s.querySelector('.scard-desc')).length,
        sample: cards.slice(0, 2).map(s => (s.querySelector('.scard-desc') || {}).textContent || ''),
      });
    }, 500));
  });
  check(second.count > 0, 'второй экран открылся: моделей ' + second.count);
  check(second.withDesc === second.count,
        'описания моделей на втором экране на месте: ' + second.withDesc + ' из ' + second.count);

  // ── Б. Чекбоксы ───────────────────────────────────────────────────────
  const chks = [];
  for (const theme of ['light', 'dark']) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
    await page.evaluate(t => {
      document.documentElement.setAttribute('data-theme', t);
      pickScene('sd');
    }, theme);
    await page.waitForTimeout(900);
    await page.evaluate(() => {
      document.querySelectorAll('#tools-panel .section, #params-panel .section')
        .forEach(sec => { if (sec.id) openSection(sec.id); });
      document.querySelectorAll('.fold-btn').forEach(b => {
        if (b.getAttribute('aria-expanded') === 'false') b.click();
      });
    });
    await page.waitForTimeout(500);
    const r = await page.evaluate((t) => {
      const list = Array.from(document.querySelectorAll('.chk input[type=checkbox]'))
        .filter(e => e.getBoundingClientRect().width > 0);
      const one = list[0];
      if (!one) return null;
      const cs = getComputedStyle(one);
      // отмеченное состояние
      const wasChecked = one.checked;
      one.checked = true;
      const csOn = getComputedStyle(one);
      const after = getComputedStyle(one, '::after');
      const res = {
        theme: t, count: list.length,
        w: cs.width, h: cs.height,
        appearance: cs.appearance || cs.webkitAppearance,
        border: cs.borderTopWidth + ' ' + cs.borderTopStyle,
        radius: cs.borderTopLeftRadius,
        bg: cs.backgroundColor,
        onBg: csOn.backgroundColor,
        tick: after.content !== 'none' && after.width !== 'auto' ? after.width + '×' + after.height : null,
      };
      one.checked = wasChecked;
      return res;
    }, theme);
    chks.push(r);
  }
  check(chks.every(c => c && c.appearance === 'none'),
        'флажок не рисуется системой: ' + JSON.stringify(chks.map(c => c && c.appearance)));
  check(chks.every(c => c && c.w === '17px' && c.h === '17px'),
        'размер 17×17: ' + JSON.stringify(chks.map(c => c && (c.w + '/' + c.h))));
  /* ⚠️ ТОЛЩИНУ РАМКИ ВЫЧИСЛЕННЫЙ СТИЛЬ НЕ ПОКАЗЫВАЕТ. Канон просит 1,5 px, а
     браузер округляет толщину рамки до целых пикселей и отдаёт «1px» — то же
     самое он делает и с инлайновым `border-top-width: 1.5px` (проверено:
     3px отдаётся как 3px, 1,5px как 1px). Спрашивать вычисленный стиль тут
     бессмысленно, поэтому сверяем ИСХОДНИК, как уже сделано в двух проверках
     канона по той же причине. */
  const css = fs.readFileSync('calc2/static/calc2/calc2.css', 'utf8');
  const declared = /\.chk input\[type=checkbox\] \{[^}]*border: 1\.5px solid var\(--border\)/.test(css);
  check(declared, 'рамка 1,5 px сплошная объявлена в исходнике (браузер округляет её до ' +
        (chks[0] || {}).border + ')');
  check(chks.every(c => c && c.radius === '4px'), 'скругление 4 px: ' + JSON.stringify(chks.map(c => c && c.radius)));
  check(chks.every(c => c && /190, 24, 93|255, 77, 148/.test(c.onBg)),
        'отмеченный — акцентный, а не серый: ' + JSON.stringify(chks.map(c => c && c.onBg)));
  check(chks.every(c => c && c.tick), 'галочка нарисована: ' + JSON.stringify(chks.map(c => c && c.tick)));

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, cards, chks, second, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 11 ────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
