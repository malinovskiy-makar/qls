/* Замер фазы 7 — экран выбора моделей и экспорт (п. 62–70).

   Спрашиваем то, что видит человек: сколько моделей обещает карточка блока и
   сколько их работает, обрезан ли перечень, совпадает ли порядок на двух
   экранах, не ломает ли бейдж «СКОРО» шапку карточки, одним ли словом названа
   каждая сущность, совпадает ли имя карточки с заголовком модели, что обещает
   полоса иконок и что перечисляет опись экспорта.

   Запуск: node scripts/calc2_catalog_probe.js [порт]                        */
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
  await p.waitForTimeout(600);

  // ── п. 62, 63, 64, 67. Карточки блоков ───────────────────────────────
  const blocks = await p.evaluate(() => {
    const out = [];
    document.querySelectorAll('#scene-picker .bcard').forEach(c => {
      const grid = document.getElementById(c.getAttribute('aria-controls'));
      const cards = [...grid.querySelectorAll('.scard')];
      const list = c.querySelector('.bcard-list');
      const nameOf = (sc) => ((sc.querySelector('.scard-name') || {}).textContent || '').trim();
      out.push({
        name: c.querySelector('.bcard-name').textContent,
        count: c.querySelector('.bcard-count').textContent,
        all: cards.length,
        ready: cards.filter(s => !s.classList.contains('soon')).length,
        clipped: list.scrollHeight > list.clientHeight + 1 || list.scrollWidth > list.clientWidth + 1,
        gridOrder: cards.map(s => nameOf(s) + (s.classList.contains('soon') ? '*' : '')),
        listOrder: list.textContent.split(' · ').map(x => x.replace(' (скоро)', '*')),
        mismatch: cards.filter(s => !s.classList.contains('soon'))
          .filter(s => (typeof SCENE_NAMES !== 'undefined') && SCENE_NAMES[s.dataset.scene] &&
                       SCENE_NAMES[s.dataset.scene] !== nameOf(s))
          .map(s => nameOf(s) + ' → ' + SCENE_NAMES[s.dataset.scene]),
      });
    });
    return out;
  });
  const lying = blocks.filter(b => b.ready !== b.all && !/ из /.test(b.count));
  say(lying.length === 0, 'п. 62 · счётчик называет и готовые, и обещанные (молчащих ' + lying.length + ')');
  const totals = blocks.reduce((a, b) => ({ all: a.all + b.all, ready: a.ready + b.ready }), { all: 0, ready: 0 });
  console.log('    всего моделей ' + totals.all + ', из них работают ' + totals.ready);
  const clipped = blocks.filter(b => b.clipped);
  say(clipped.length === 0, 'п. 63 · перечень моделей не обрезан ни в одной карточке (обрезано ' + clipped.length + ')');
  const disorder = blocks.filter(b => b.gridOrder.join('|') !== b.listOrder.join('|'));
  say(disorder.length === 0, 'п. 64 · порядок моделей одинаков на обоих экранах (расходится ' + disorder.length + ')');
  const wrongName = blocks.flatMap(b => b.mismatch);
  say(wrongName.length === 0, 'п. 67 · имя карточки совпадает с заголовком модели (расхождений ' +
      wrongName.length + (wrongName.length ? ': ' + wrongName.join('; ') : '') + ')');

  // ── п. 65. Бейдж «СКОРО» не ломает шапку карточки ────────────────────
  const badge = await p.evaluate(() => {
    const bad = [];
    document.querySelectorAll('#scene-picker .scard.soon').forEach(sc => {
      const head = sc.querySelector('.scard-head');
      const nm = sc.querySelector('.scard-name');
      const bg = sc.querySelector('.scard-soon');
      if (!head || !nm || !bg) return;
      const h = head.getBoundingClientRect(), n = nm.getBoundingClientRect(), g = bg.getBoundingClientRect();
      const lines = Math.round(n.height / parseFloat(getComputedStyle(nm).lineHeight || 20));
      // Бейдж обязан стоять В ПЕРВОЙ строке имени и не вылезать из шапки.
      const topAligned = Math.abs(g.top - n.top) <= 4;
      const inside = g.right <= h.right + 0.5 && g.top >= h.top - 0.5 && g.bottom <= h.bottom + 0.5;
      if (!topAligned || !inside) bad.push(nm.textContent.trim() + ' (строк ' + lines + ')');
    });
    return bad;
  });
  say(badge.length === 0, 'п. 65 · бейдж стоит в первой строке имени и внутри шапки (не так ' +
      badge.length + (badge.length ? ': ' + badge.slice(0, 3).join('; ') : '') + ')');
  const dim = await p.evaluate(() =>
    [...document.querySelectorAll('#scene-picker .scard.soon')]
      .filter(sc => parseFloat(getComputedStyle(sc).opacity) < 1).length);
  say(dim === 0, 'п. 65 · недоступная модель показана цветом, а не прозрачностью (приглушённых ' + dim + ')');

  // ── п. 66. Одно слово на одну сущность ───────────────────────────────
  const words = await p.evaluate(() => {
    const bad = [];
    const BAN = ['раздел', 'Раздел', 'сценари', 'Сценари', 'сцен', 'Сцен'];
    const check = (where, v) => { if (v && BAN.some(w => v.includes(w))) bad.push(where + ': ' + v.slice(0, 60)); };
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walk.nextNode())) {
      const tag = n.parentElement && n.parentElement.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE') continue;
      check('текст', n.nodeValue.trim());
    }
    document.querySelectorAll('[data-tip],[aria-label],[placeholder],[title]').forEach(e => {
      ['data-tip', 'aria-label', 'placeholder', 'title'].forEach(a => check(a, e.getAttribute(a)));
    });
    return bad;
  });
  say(words.length === 0, 'п. 66 · «раздел», «сценарий» и «сцена» из интерфейса убраны (осталось ' +
      words.length + (words.length ? ': ' + words.slice(0, 3).join(' | ') : '') + ')');

  // ── п. 68, 69. Полоса иконок и окно скачивания ───────────────────────
  const dock = await p.evaluate(() => ({
    save: !!document.getElementById('dock-save'),
    exportTip: (document.getElementById('dock-export') || {}).getAttribute
      ? document.getElementById('dock-export').getAttribute('aria-label') : '',
    title: (document.getElementById('export-title') || {}).textContent || '',
  }));
  say(!dock.save, 'п. 68 · заглушки сохранения в полосе иконок нет');
  say(!/PDF|TeX|PNG/.test(dock.exportTip),
      'п. 68 · подпись кнопки не перечисляет форматов: «' + dock.exportTip + '»');
  say(dock.title !== '' && dock.title !== 'Сохранить график',
      'п. 69 · окно скачивания не тёзка кнопке сохранения: «' + dock.title + '»');

  // ── п. 69, 70. Что обещает окно и что перечисляет опись ──────────────
  await p.evaluate(() => { closePicker(); resetSceneMemory(); pickScene('tax'); });
  await p.waitForTimeout(700);
  const exp = await p.evaluate(() => {
    openExport();
    const rows = [...document.querySelectorAll('#exp-preview .exp-prow')]
      .map(r => [r.querySelector('.exp-pk').textContent, r.querySelector('.exp-pv').textContent]);
    const btns = [...document.querySelectorAll('#export-modal .modal-opts button')].map(b => b.textContent.trim());
    // Сколько всего кривых и заливок ВИДНО на холсте — с этим и сверяем опись.
    const paths = [...document.querySelectorAll('#chart path')];
    const seen = {
      curves: paths.filter(el => el.getAttribute('data-curve') || el.getAttribute('data-expr')).length,
      areas: document.querySelectorAll('#chart [data-legend]').length,
    };
    closeExport();
    return { rows, btns, seen };
  });
  const val = (k) => { const r = exp.rows.filter(x => x[0] === k)[0]; return r ? r[1] : null; };
  say(exp.rows.length > 0 && val('Кривых') !== null && val('Кривых точками') === null,
      'п. 70 · опись говорит про картинку, а не про устройство файла: ' +
      exp.rows.map(r => r[0]).join(' · '));
  const curves = +val('Кривых'), areas = +val('Закрашенных областей');
  say(curves > 0 && curves <= exp.seen.curves + 2,
      'п. 70 · кривых в описи ' + curves + ', на холсте помечено ' + exp.seen.curves);
  say(areas >= 0 && areas <= exp.seen.areas + 2,
      'п. 70 · закрашенных областей в описи ' + areas + ', на холсте ' + exp.seen.areas);
  const promised = exp.btns.join(' ');
  say(!/PDF/.test(dock.exportTip) || /PDF/.test(promised),
      'п. 69 · формат обещан только там, где кнопка есть: кнопки ' + promised);

  console.log('\n=== каталог и экспорт: ' + ok + ' прошло, ' + bad + ' провалено; ошибок страницы ' + errs.length + ' ===');
  errs.slice(0, 5).forEach(e => console.log('  ОШИБКА: ' + e));
  await b.close();
  process.exit(bad || errs.length ? 1 : 0);
})();
