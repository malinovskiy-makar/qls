/* Замер /calc2/ под канон (DESIGN.md). Два режима:
     tokens   — снимок токенов :root и вычисленных стилей выборки элементов
                (нужен, чтобы доказать «ничего не изменилось» при чистке дублей);
     contrast — контраст ВСЕХ подписей на холсте против их фона, обе темы (п. 75).
   Запуск:  node scripts/calc2_canon_probe.js <порт> <режим> <файл.json> [сцены]
   Сцена по умолчанию — набор из восьми, названных в промпте для приёмки.      */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT   = process.argv[2] || '8601';
const MODE   = process.argv[3] || 'tokens';
const OUT    = process.argv[4] || 'reports/calc2-canon/probe.json';
const SCENES = (process.argv[5] || 'sd,tax,mono,costs,monopsony,ppfsum,prod,m-graph').split(',');
const BASE   = `http://127.0.0.1:${PORT}`;

const VARS = ['--accent','--accent-deep','--accent-tint','--accent-ring','--accent-rgb',
  '--act-ink-solid','--on-accent','--text','--text2','--text3','--bg','--surface','--surface-2',
  '--border','--border-soft','--btn-bg','--btn-bg-hover','--on-btn','--focus','--focus-ring',
  '--r','--r-sm','--r-card','--r-panel','--r-pill','--line','--stripe','--t','--shadow-pop',
  '--sb','--panel','--input-bg','--canvas','--ink','--ink-soft','--grid','--halo','--pick',
  '--curve-d','--curve-s','--curve-mr','--curve-mc','--cost-mc','--cost-atc','--cost-avc','--cost-afc'];

const SEL = ['.side-left','.side-right','.dock','.btn','.f-input','.seg','.seg button','.card',
  '.side-part','.scard','.bcard','.f-pop','.mkbd','.toast','.pchip','.stat','.stat b','.chip',
  '.wrench-pop','.exp-preview','#graph-wrap','.hint-tip','.picker-group','.mark-draft','.k-num'];

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

async function openScene(page, key, theme) {
  await page.evaluate((t) => localStorage.setItem('theme', t), theme);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
  await page.evaluate((k) => { pickScene(k); }, key);
  await page.waitForTimeout(700);
}

const snapTokens = ([vars, sel]) => {
  const cs = getComputedStyle(document.documentElement);
  const out = { vars: {}, el: {} };
  vars.forEach(v => { const x = cs.getPropertyValue(v).trim(); if (x) out.vars[v] = x; });
  sel.forEach(s => {
    const e = document.querySelector(s); if (!e) return;
    const c = getComputedStyle(e);
    out.el[s] = [c.color, c.backgroundColor, c.borderColor, c.borderRadius,
                 c.fontSize, c.fontWeight, c.boxShadow, c.borderWidth].join(' | ');
  });
  return out;
};

/* Контраст по WCAG. Фон подписи на холсте — это фон САМОГО ХОЛСТА (--canvas):
   у <text> в SVG своего фона нет, а гало под подписью рисуется тем же цветом. */
const snapContrast = () => {
  /* Цвет может прийти и как rgb(), и как hex из токена — разбираем оба.
     Раньше hex не разбирался, фон холста молча становился белым, и в тёмной
     теме измерялись светлые подписи против белого: 159 «нарушений» из 312
     были выдумкой самого замера. */
  const px = (s) => { if (!s) return null; s = String(s).trim();
    const m = /rgba?\(([^)]+)\)/.exec(s);
    if (m) { const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
             return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
    const h = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
    if (!h) return null;
    let v = h[1]; if (v.length === 3) v = v.split('').map(c => c + c).join('');
    return [parseInt(v.slice(0,2),16), parseInt(v.slice(2,4),16), parseInt(v.slice(4,6),16), 1]; };
  const lum = (c) => { const f = c.map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); });
    return .2126 * f[0] + .7152 * f[1] + .0722 * f[2]; };
  const over = (fg, bg) => fg[3] >= 1 ? fg : [0,1,2].map(i => fg[i] * fg[3] + bg[i] * (1 - fg[3])).concat([1]);
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); const hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return (hi + .05) / (lo + .05); };
  const wrap = document.querySelector('#graph-wrap');
  const canvasBg = px(getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim())
                || px(getComputedStyle(wrap || document.body).backgroundColor) || [255,255,255,1];
  const rows = [];
  document.querySelectorAll('#graph-wrap svg text').forEach(t => {
    /* Подпись почти всегда собрана из <tspan> (mathTspans, qtyTspans), поэтому
       «только прямые текстовые узлы» пропускали ровно те подписи, ради которых
       замер и делается. Берём весь текст, кроме <title>: он живёт у легенды
       и на экран не попадает (CLAUDE.md, ловушка легенды). */
    const own = Array.from(t.childNodes)
      .filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName.toLowerCase() !== 'title'))
      .map(n => n.textContent).join('').trim();
    if (!own) return;
    const c = getComputedStyle(t);
    if (c.display === 'none' || c.visibility === 'hidden' || parseFloat(c.opacity) < .05) return;
    const b = t.getBoundingClientRect(); if (!b.width || !b.height) return;
    let fg = px(c.fill && c.fill.startsWith('rgb') ? c.fill : c.color); if (!fg) return;
    const op = parseFloat(c.opacity); if (isFinite(op) && op < 1) fg = [fg[0], fg[1], fg[2], fg[3] * op];
    const size = parseFloat(c.fontSize), bold = parseInt(c.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    rows.push({ text: own.slice(0, 34), fill: c.fill, size,
                r: +ratio(over(fg, canvasBg), canvasBg).toFixed(2), need: large ? 3 : 4.5 });
  });
  return { canvasBg: canvasBg.join(','), rows };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => console.log('ОШИБКА СТРАНИЦЫ:', e.message));
  await login(page);
  let scenes = SCENES;
  if (SCENES.length === 1 && SCENES[0] === 'all') {
    await openScene(page, 'sd', 'light');
    scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
    console.log('сцен в реестре:', scenes.length);
  }
  const res = {};
  for (const theme of ['light', 'dark']) {
    for (const key of scenes) {
      await openScene(page, key, theme);
      res[theme + '/' + key] = MODE === 'contrast'
        ? await page.evaluate(snapContrast)
        : await page.evaluate(snapTokens, [VARS, SEL]);
    }
  }
  fs.writeFileSync(OUT, JSON.stringify(res, null, 1), 'utf8');
  if (MODE === 'contrast') {
    let bad = 0, all = 0;
    for (const k of Object.keys(res)) for (const r of res[k].rows) { all++; if (r.r < r.need) { bad++;
      if (bad <= 40) console.log(`${k}  «${r.text}»  ${r.r} < ${r.need}   ${r.fill}`); } }
    console.log(`\nподписей ${all}, ниже нормы ${bad}`);
  } else {
    console.log('снимок токенов:', Object.keys(res).length, 'сцен×тем →', OUT);
  }
  await browser.close();
})();
