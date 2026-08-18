/* ФАЗА 6. Замер панелей: строки результатов, поля, кнопки, сегменты, скелет.
   Отвечает на вопросы приёмки фазы:
     1) сколько строк результата переносится и рвётся посреди слова (п. 49);
     2) сколькими способами показано число на одном экране (п. 50);
     3) какие числа повторены в двух панелях сразу (п. 56);
     4) сколько видов у поля ввода и у кнопки (п. 57, 58);
     5) какие блоки раскрыты, а какие свёрнуты при входе (п. 52);
     6) из каких блоков состоит левая панель (п. 51);
     7) отступы и высоты сегмента (п. 55).
   Запуск: node scripts/calc2_panel_probe.js <порт> <файл.json> [сцены|all]   */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8601';
const OUT  = process.argv[3] || 'reports/calc2-canon/panels.json';
const ONLY = (process.argv[4] || 'all');
const BASE = `http://127.0.0.1:${PORT}`;

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

const snap = () => {
  const out = { rows: [], wrapped: [], numStyles: {}, inputStyles: {}, btnStyles: {},
                folds: [], skeleton: [], seg: [], dupes: [] };
  const vis = (el) => {
    const c = getComputedStyle(el);
    if (c.display === 'none' || c.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0.5 && r.height > 0.5;
  };
  const key = (c, ...props) => props.map(p => c[p]).join(' | ');

  /* Строка результата: считаем ФАКТИЧЕСКОЕ число строк по высоте и ищем
     перенос ВНУТРИ слова — именно он даёт «(произво-дитель)». */
  document.querySelectorAll('.stat').forEach(el => {
    if (!vis(el)) return;
    const lab = el.querySelector('span'), val = el.querySelector('b');
    if (!lab) return;
    const c = getComputedStyle(lab);
    const lh = c.lineHeight === 'normal' ? parseFloat(c.fontSize) * 1.2 : parseFloat(c.lineHeight);
    const lines = Math.round(lab.getBoundingClientRect().height / lh);
    const txt = (lab.textContent || '').trim();
    out.rows.push({ t: txt.slice(0, 40), lines, w: +lab.getBoundingClientRect().width.toFixed(0) });
    if (lines > 1) out.wrapped.push({ t: txt.slice(0, 40), lines,
                                      hyphens: c.hyphens, wrap: c.overflowWrap,
                                      v: val ? (val.textContent || '').trim().slice(0, 24) : '' });
  });

  /* Сколько способов показать число. Ключ — кегль+вес+цвет значения. */
  document.querySelectorAll('.stat b, .sb-body b, .pchip b, .k-num, .mark-ok').forEach(el => {
    if (!vis(el)) return;
    const t = (el.textContent || '').trim();
    if (!/[0-9]/.test(t)) return;
    const c = getComputedStyle(el);
    const k = key(c, 'fontSize', 'fontWeight', 'color', 'fontVariantNumeric');
    (out.numStyles[k] = out.numStyles[k] || []).push(t.slice(0, 16));
  });

  document.querySelectorAll('input[type=text], input[type=number], input:not([type]), .f-input, math-field')
    .forEach(el => {
      if (!vis(el)) return;
      const c = getComputedStyle(el);
      const k = key(c, 'borderTopWidth', 'borderBottomWidth', 'borderStyle', 'borderRadius', 'backgroundColor');
      (out.inputStyles[k] = out.inputStyles[k] || []).push(el.id || el.className || el.tagName);
    });

  document.querySelectorAll('button').forEach(el => {
    if (!vis(el) || el.closest('nav')) return;
    const c = getComputedStyle(el);
    const k = key(c, 'backgroundColor', 'color', 'borderColor', 'borderWidth', 'fontSize', 'fontWeight');
    (out.btnStyles[k] = out.btnStyles[k] || []).push((el.textContent || '').trim().slice(0, 18) || el.className);
  });

  document.querySelectorAll('.fold-btn').forEach(el => {
    if (!vis(el)) return;
    out.folds.push({ t: (el.textContent || '').trim().slice(0, 30),
                     open: el.getAttribute('aria-expanded') === 'true' });
  });

  document.querySelectorAll('.side-left .side-part, .side-right .side-part').forEach(el => {
    if (!vis(el)) return;
    const h = el.querySelector('.fold-btn, .side-cap, h3, b');
    out.skeleton.push(((h && h.textContent) || '').trim().slice(0, 30));
  });

  document.querySelectorAll('.seg').forEach(el => {
    if (!vis(el)) return;
    Array.from(el.querySelectorAll('button')).forEach(b => {
      if (!vis(b)) return;
      const c = getComputedStyle(b), r = b.getBoundingClientRect();
      out.seg.push({ t: (b.textContent || '').trim().slice(0, 20),
                     padX: c.paddingLeft + '/' + c.paddingRight,
                     h: +r.height.toFixed(0), radius: c.borderRadius });
    });
  });

  /* Одни и те же числа в двух панелях (п. 56). Сверяем подпись+значение. */
  const bag = {};
  document.querySelectorAll('.side-left .stat, .side-right .stat').forEach(el => {
    if (!vis(el)) return;
    const lab = (el.querySelector('span') || {}).textContent || '';
    const val = (el.querySelector('b') || {}).textContent || '';
    if (!val.trim()) return;
    const side = el.closest('.side-left') ? 'left' : 'right';
    const k = lab.trim().slice(0, 24) + ' = ' + val.trim().slice(0, 16);
    (bag[k] = bag[k] || new Set()).add(side);
  });
  Object.keys(bag).forEach(k => { if (bag[k].size > 1) out.dupes.push(k); });
  return out;
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof SCENE_ROUTE === 'object', null, { timeout: 25000 });
  const keys = ONLY === 'all'
    ? await page.evaluate(() => Object.keys(SCENE_ROUTE))
    : ONLY.split(',');

  const res = {};
  for (const k of keys) {
    await page.evaluate((x) => { pickScene(x); }, k);
    await page.waitForTimeout(420);
    /* ⚠️ СОСТОЯНИЕ СКЛАДНЫХ БЛОКОВ СНИМАЕТСЯ ДО ТОГО, КАК МЫ ИХ РАСКРОЕМ.
       Первая версия читала его ПОСЛЕ раскрытия, и все сцены отвечали
       «раскрыто всё» — прибор мерил собственное действие, а не продукт. */
    const folds = await page.evaluate(() => Array.from(document.querySelectorAll('.fold-btn'))
      .filter(b => b.offsetParent !== null)
      .map(b => ({ t: (b.textContent || '').trim().slice(0, 30),
                   open: b.getAttribute('aria-expanded') === 'true' })));
    /* Раскрываем всё: часть строк результата иначе не измеряется вовсе,
       и «переносов нет» означало бы «нечего мерить». */
    await page.evaluate(() => {
      document.querySelectorAll('.fold-btn[aria-expanded="false"]').forEach(b => b.click());
    });
    await page.waitForTimeout(260);
    res[k] = await page.evaluate(snap);
    res[k].folds = folds;
  }
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(res, null, 1), 'utf-8');

  const wrapped = [], numK = new Set(), inpK = new Set(), btnK = new Set(), dup = [];
  let rows = 0, segBad = 0, segH = new Set();
  Object.entries(res).forEach(([k, r]) => {
    rows += r.rows.length;
    r.wrapped.forEach(w => wrapped.push(k + ' · ' + w.t + ' (' + w.lines + ' стр, hyphens=' + w.hyphens + ')'));
    Object.keys(r.numStyles).forEach(x => numK.add(x));
    Object.keys(r.inputStyles).forEach(x => inpK.add(x));
    Object.keys(r.btnStyles).forEach(x => btnK.add(x));
    r.dupes.forEach(d => dup.push(k + ' · ' + d));
    r.seg.forEach(s => { segH.add(s.h); if (parseFloat(s.padX) < 6) segBad++; });
  });
  const foldMix = Object.entries(res).map(([k, r]) => k + ':' + r.folds.map(f => f.open ? '1' : '0').join(''));
  console.log('сцен:', Object.keys(res).length, '· строк результата:', rows);
  console.log('переносов в строке результата:', wrapped.length);
  wrapped.slice(0, 12).forEach(w => console.log('   ', w));
  console.log('видов записи числа:', numK.size);
  Array.from(numK).slice(0, 10).forEach(x => console.log('   ', x));
  console.log('видов поля ввода:', inpK.size);
  Array.from(inpK).forEach(x => console.log('   ', x));
  console.log('видов кнопки:', btnK.size);
  Array.from(btnK).slice(0, 12).forEach(x => console.log('   ', x));
  console.log('числа в двух панелях сразу:', dup.length);
  dup.slice(0, 10).forEach(d => console.log('   ', d));
  console.log('сегмент: высот', Array.from(segH).join('/'), '· без отступов', segBad);
  console.log('состояние складных блоков по сценам (1 раскрыт):');
  foldMix.slice(0, 45).forEach(x => console.log('   ', x));
  console.log('→', OUT);
})();
