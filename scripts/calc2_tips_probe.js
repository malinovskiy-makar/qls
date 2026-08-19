/* Замер фазы 8 — подсказки, ширина окна, тексты (п. 76–82).

   Подсказки проверяются ДЕЙСТВИЯМИ: навести, увести, нажать, пройти табом.
   Разбор исходников тут бесполезен — половина прежних бед жила в том, что
   `:focus-visible` держится дольше, чем человек этого ждёт.

   Запуск: node scripts/calc2_tips_probe.js [порт]                          */
const { chromium } = require('playwright');
const PORT = process.argv[2] || '8601';
const BASE = 'http://127.0.0.1:' + PORT;
const SCENES = ['sd', 'tax', 'ceil', 'mono', 'elast', 'costs', 'labor', 'ineq', 'adas', 'islm', 'ppfsum', 'prod'];

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
    await p.evaluate((k) => { closePicker(); resetSceneMemory(); pickScene(k); }, key);
    await p.waitForTimeout(500);
  };
  await scene('tax');

  const tipState = () => p.evaluate(() => {
    const t = document.getElementById('hint-tip');
    const shown = t && getComputedStyle(t).display !== 'none';
    const r = shown ? t.getBoundingClientRect() : null;
    return { shown: !!shown, text: shown ? t.textContent.trim() : '', box: r ? [r.left, r.top, r.width, r.height] : null };
  });

  // ── п. 78. Плашка одна на весь калькулятор ───────────────────────────
  const systems = await p.evaluate(() => {
    // Считаем ВТОРЫЕ системы: правила ::after с содержимым из data-tip.
    let css = 0;
    for (const sheet of document.styleSheets) {
      let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
      for (const r of rules || []) {
        if (r.selectorText && /::after/.test(r.selectorText) && /\[data-tip\]/.test(r.selectorText)) css++;
      }
    }
    /* Плашку считаем ПОСЛЕ показа: она создаётся при первом обращении, и
       «ноль плашек» на нетронутой странице ничего не доказывает. */
    document.getElementById('btn-wrench').dispatchEvent(new PointerEvent('pointerover', { bubbles: true }));
    const plates = document.querySelectorAll('#hint-tip, .k-tip, .tip, .tooltip').length;
    hideHintTip();
    return { css, plates };
  });
  say(systems.css === 0, 'п. 78 · второй системы подсказок нет (правил ::after с data-tip: ' + systems.css + ')');
  say(systems.plates === 1, 'п. 78 · плашка на странице ровно одна (' + systems.plates + ')');

  // ── п. 79. Появляется по наведению, гаснет по уходу и по нажатию ─────
  await p.evaluate(() => hideHintTip());
  const btn = await p.evaluate(() => {
    const el = document.getElementById('btn-wrench');
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  await p.mouse.move(btn.x, btn.y);
  await p.waitForTimeout(150);
  const onHover = await tipState();
  say(onHover.shown, 'п. 79 · подсказка приходит по наведению: «' + onHover.text.slice(0, 34) + '»');
  await p.mouse.move(btn.x, btn.y + 260);
  await p.waitForTimeout(150);
  say(!(await tipState()).shown, 'п. 79 · и гаснет, когда указатель ушёл');

  await p.mouse.move(btn.x, btn.y);
  await p.waitForTimeout(120);
  await p.mouse.down(); await p.mouse.up();
  await p.waitForTimeout(150);
  say(!(await tipState()).shown, 'п. 79 · нажатие гасит подсказку, а не оставляет висеть');
  await p.evaluate(() => setWrenchOpen(false));

  // Вход в модель фокусирует кнопку возврата ПРОГРАММНО — плашки быть не должно.
  await p.mouse.move(1200, 700);
  await scene('mono');
  say(!(await tipState()).shown, 'п. 79 · вход в модель не оставляет плашку висеть');

  // Клавиатура: Tab показывает подсказку.
  await p.evaluate(() => { document.getElementById('btn-wrench').blur(); hideHintTip(); });
  await p.keyboard.press('Tab');
  await p.waitForTimeout(120);
  await p.evaluate(() => document.getElementById('scene-back').focus());
  await p.waitForTimeout(150);
  const onKey = await tipState();
  say(onKey.shown, 'п. 79 · с клавиатуры подсказка тоже приходит: «' + onKey.text.slice(0, 30) + '»');
  await p.keyboard.press('Escape');
  await p.waitForTimeout(120);
  say(!(await tipState()).shown, 'п. 79 · Escape гасит подсказку');

  // ── п. 80. Плашка стоит рядом со своим элементом ─────────────────────
  await p.mouse.move(1200, 700);
  await scene('sd');
  const far = await p.evaluate(async () => {
    const out = [];
    const els = [...document.querySelectorAll('[data-tip]')].filter(e => e.getBoundingClientRect().width > 0);
    for (const el of els) {
      el.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }));
      await new Promise(r => setTimeout(r, 20));
      const t = document.getElementById('hint-tip');
      if (!t || getComputedStyle(t).display === 'none') { out.push(['нет плашки', el.id || el.className]); continue; }
      const a = el.getBoundingClientRect(), c = t.getBoundingClientRect();
      const gap = Math.max(0, Math.max(a.left - c.right, c.left - a.right, a.top - c.bottom, c.top - a.bottom));
      if (gap > 24) out.push([Math.round(gap) + ' px', el.id || el.className]);
      hideHintTip();
    }
    return out;
  });
  say(far.length === 0, 'п. 80 · подсказка стоит вплотную к своему элементу (далеко ' +
      far.length + (far.length ? ': ' + far.slice(0, 3).map(x => x.join(' — ')).join('; ') : '') + ')');
  const floatBtn = await p.evaluate(() => document.querySelectorAll('.quick-area').length);
  say(floatBtn === 0, 'п. 80 · плавающей кнопки-двойника у холста нет');

  // ── п. 81. Подпись и текст для чтеца — одна строка ───────────────────
  const labels = await p.evaluate(() =>
    [...document.querySelectorAll('[data-tip]')]
      .filter(e => !(e.textContent || '').trim())
      .filter(e => (e.getAttribute('aria-label') || '') !== e.getAttribute('data-tip'))
      .map(e => (e.id || e.className) + ': «' + e.getAttribute('data-tip') + '» / «' + (e.getAttribute('aria-label') || '') + '»'));
  say(labels.length === 0, 'п. 81 · подпись и текст для чтеца совпадают (расходятся ' +
      labels.length + (labels.length ? ': ' + labels.slice(0, 2).join('; ') : '') + ')');

  // ── п. 76. Ноутбучные ширины: подпись не переносится ─────────────────
  let wrapTotal = 0, wrapWhere = [];
  for (const w of [1280, 1200, 1100]) {
    await p.setViewportSize({ width: w, height: 900 });
    for (const sc of SCENES) {
      await p.evaluate((s) => { closePicker(); resetSceneMemory(); pickScene(s); }, sc);
      await p.waitForTimeout(260);
      const r = await p.evaluate(() => {
        const out = [];
        document.querySelectorAll('#sb-body .stat').forEach(row => {
          const s = row.querySelector('span');
          if (!s) return;
          const lh = parseFloat(getComputedStyle(s).lineHeight) || 16;
          if (s.getBoundingClientRect().height > lh * 1.4) out.push(s.textContent.trim().slice(0, 24));
        });
        return out;
      });
      wrapTotal += r.length;
      if (r.length) wrapWhere.push(w + '/' + sc + ': ' + r[0]);
    }
  }
  say(wrapTotal === 0, 'п. 76 · на 1100–1280 подпись в аналитике не переносится (переносов ' +
      wrapTotal + (wrapTotal ? ': ' + wrapWhere.slice(0, 3).join('; ') : ', 12 моделей × 3 ширины') + ')');

  // ── п. 77. Узкое окно: панель называет себя, страница не едет вбок ───
  const narrow = [];
  for (const w of [820, 760, 720, 560, 360]) {
    await p.setViewportSize({ width: w, height: 860 });
    await p.evaluate(() => { closePicker(); resetSceneMemory(); pickScene('tax'); });
    await p.waitForTimeout(400);
    const r = await p.evaluate(() => {
      const rp = document.getElementById('params-panel');
      const sp = rp.querySelector('.side-spine');
      const seen = sp && getComputedStyle(sp).display !== 'none' && sp.getBoundingClientRect().height > 20;
      return {
        collapsed: Math.round(rp.getBoundingClientRect().width) < 60,
        named: !!seen,
        hscroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    if (r.collapsed && !r.named) narrow.push(w + ' px — свёрнута и без имени');
    if (r.hscroll > 0) narrow.push(w + ' px — страница едет вбок на ' + r.hscroll);
  }
  say(narrow.length === 0, 'п. 77 · свёрнутая панель названа, страница не едет вбок (' +
      (narrow.length ? narrow.join('; ') : 'проверено 820/760/720/560/360') + ')');

  // ── п. 82. Мелочи текста ─────────────────────────────────────────────
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.evaluate(() => { closePicker(); resetSceneMemory(); pickScene('adas'); });
  await p.waitForTimeout(600);
  /* Разрыв выпуска проверяем НА НУЛЕ, а не на том, что сцена показала сама:
     у ненулевого числа знак законен, и проверка прошла бы мимо дефекта.
     Ставим потенциальный выпуск ровно в краткосрочное равновесие. */
  await p.evaluate(() => {
    const eq = STATE.macroRes && STATE.macroRes.eq;
    const inp = document.getElementById('ma-lras');
    if (eq && inp) { inp.value = String(eq.Q); inp.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  await p.waitForTimeout(400);
  const gapRow = await p.evaluate(() => {
    const row = [...document.querySelectorAll('#sb-body .stat')]
      .filter(r => /Разрыв выпуска/.test(r.textContent))[0];
    return { gap: STATE.macroRes ? STATE.macroRes.gap : null, text: row ? row.textContent.trim() : 'строки нет' };
  });
  say(Math.abs(gapRow.gap || 0) < 1e-6 && !/\+/.test(gapRow.text),
      'п. 82 · нулевой разрыв выпуска печатается без знака: «' + gapRow.text + '»');

  const texts = await p.evaluate(() => {
    const bad = [];
    document.querySelectorAll('[placeholder]').forEach(e => {
      if (/\s[:;,]/.test(e.getAttribute('placeholder'))) bad.push('плейсхолдер: ' + e.getAttribute('placeholder'));
    });
    const body = document.body.innerText;
    if (body.includes('Вывод.')) bad.push('заголовок «Вывод» с точкой');
    if (/=\s*\+0(\D|$)/.test(body)) bad.push('знак у нуля: ' + (body.match(/.{0,22}=\s*\+0.{0,6}/) || [''])[0]);
    return bad;
  });
  say(texts.length === 0, 'п. 82 · пробел перед двоеточием, точка в «Вывод» и «+0» — ' +
      (texts.length ? texts.join(' | ') : 'ничего не найдено'));
  const eqTitle = await p.evaluate(() => {
    closePicker(); resetSceneMemory(); pickScene('sd');
    return new Promise(r => setTimeout(() => {
      const t = document.querySelector('#sec-eq .section-title');
      r({ katex: !!(t && t.querySelector('.katex')), text: t ? t.textContent.trim().slice(0, 30) : 'нет' });
    }, 600));
  });
  say(eqTitle.katex, 'п. 82 · условие равновесия набрано формулой: «' + eqTitle.text + '»');

  console.log('\n=== подсказки и ширина: ' + ok + ' прошло, ' + bad + ' провалено; ошибок страницы ' + errs.length + ' ===');
  errs.slice(0, 5).forEach(e => console.log('  ОШИБКА: ' + e));
  await b.close();
  process.exit(bad || errs.length ? 1 : 0);
})();
