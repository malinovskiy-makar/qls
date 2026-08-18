/* ФАЗА 3. Замер раскладки холста по всем сценам при трёх ширинах окна.
   Отвечает ровно на три вопроса приёмки фазы:
     1) пересекаются ли прямоугольники текстовых элементов между собой;
     2) пересекаются ли плавающие блоки между собой и с областью подписей;
     3) выходит ли подпись за границы холста.
   Плюс два точечных класса: сырой LaTeX на холсте (п. 42) и «M с индексом C»
   вместо «MC» (п. 48).
   Запуск: node scripts/calc2_layout_probe.js <порт> <файл.json> [сцены|all] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT   = process.argv[2] || '8601';
const OUT    = process.argv[3] || 'reports/calc2-canon/layout.json';
const SCENES = (process.argv[4] || 'all').split(',');
const BASE   = `http://127.0.0.1:${PORT}`;
const WIDTHS = [1440, 1180, 960];

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
  const svgEl = document.querySelector('#chart');
  const wrap  = document.querySelector('#graph-wrap');
  if (!svgEl || !wrap) return null;
  const box = svgEl.getBoundingClientRect();
  const rel = (r) => ({ x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height });
  const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  /* Наложение считаем только заметное: соприкосновение углами на пиксель
     человек не видит, а в отчёт оно бы село шумом. */
  const overlap = (a, b) => {
    const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    return (w > 1.5 && h > 1.5) ? +(w * h).toFixed(1) : 0;
  };
  const ownText = (n) => Array.from(n.childNodes)
      .filter(c => c.nodeType === 3).map(c => c.nodeValue).join('').trim()
      || Array.from(n.querySelectorAll('tspan')).map(t => t.textContent).join('').trim();

  /* ── Тексты холста ───────────────────────────────────────────── */
  const texts = [];
  svgEl.querySelectorAll('text').forEach(t => {
    const cs = getComputedStyle(t);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < .05) return;
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    texts.push({ s: ownText(t).slice(0, 28), r: rel(r),
                 cls: t.getAttribute('class') || '' });
  });

  const textPairs = [];
  for (let i = 0; i < texts.length; i++)
    for (let j = i + 1; j < texts.length; j++) {
      const a = overlap(texts[i].r, texts[j].r);
      if (a) textPairs.push({ a: texts[i].s, b: texts[j].s, area: a });
    }

  /* ── Плавающее НАД холстом: HTML-блоки внутри обёртки ─────────── */
  const floats = [];
  wrap.querySelectorAll('.graph-tools, .quick-area, .wrench, .graph-float').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.hasAttribute('hidden')) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1) return;
    floats.push({ s: el.id || el.className, r: rel(r) });
  });
  /* Легенду рисует сам SVG — она такой же плавающий блок по смыслу. */
  const legend = svgEl.querySelector('.legend, [data-legend-box]');
  if (legend) { const r = legend.getBoundingClientRect();
                if (r.width > 1) floats.push({ s: 'легенда', r: rel(r) }); }

  const floatPairs = [];
  for (let i = 0; i < floats.length; i++)
    for (let j = i + 1; j < floats.length; j++) {
      const a = overlap(floats[i].r, floats[j].r);
      if (a) floatPairs.push({ a: floats[i].s, b: floats[j].s, area: a });
    }
  const floatOverText = [];
  floats.forEach(f => texts.forEach(t => {
    const a = overlap(f.r, t.r);
    if (a) floatOverText.push({ float: f.s, text: t.s, area: a });
  }));

  /* ── Выход за границы холста ─────────────────────────────────── */
  const outside = texts.filter(t =>
      t.r.x < -0.5 || t.r.y < -0.5 ||
      t.r.x + t.r.w > box.width + 0.5 || t.r.y + t.r.h > box.height + 0.5)
    .map(t => ({ s: t.s, x: +t.r.x.toFixed(1), y: +t.r.y.toFixed(1),
                 right: +(t.r.x + t.r.w).toFixed(1), bottom: +(t.r.y + t.r.h).toFixed(1) }));

  /* ── Сырой LaTeX на холсте (п. 42) ───────────────────────────── */
  const rawTex = texts.filter(t => /\$|\\[a-zA-Z]{2,}|\\max|\\min/.test(t.s)).map(t => t.s);

  return { size: { w: +box.width.toFixed(1), h: +box.height.toFixed(1) },
           texts: texts.length, textPairs, floats: floats.map(f => f.s),
           floatPairs, floatOverText, outside, rawTex };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: WIDTHS[0], height: 900 } });
  page.on('pageerror', e => console.log('ОШИБКА СТРАНИЦЫ:', e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  let scenes = SCENES;
  if (scenes.length === 1 && scenes[0] === 'all')
    scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  console.log('сцен:', scenes.length, '· ширины:', WIDTHS.join(', '));

  const res = {};
  for (const w of WIDTHS) {
    await page.setViewportSize({ width: w, height: 900 });
    for (const key of scenes) {
      await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
      await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
      await page.evaluate(k => pickScene(k), key);
      await page.waitForTimeout(650);
      res[w + '/' + key] = await page.evaluate(snap);
    }
  }
  fs.writeFileSync(OUT, JSON.stringify(res, null, 1), 'utf8');

  let tp = 0, fp = 0, ft = 0, out = 0, tex = 0;
  const scenesWith = { textPairs: new Set(), floatPairs: new Set(), floatOverText: new Set(), outside: new Set(), rawTex: new Set() };
  for (const k of Object.keys(res)) {
    const r = res[k]; if (!r) continue;
    const scene = k.split('/')[1];
    tp += r.textPairs.length;      if (r.textPairs.length)     scenesWith.textPairs.add(scene);
    fp += r.floatPairs.length;     if (r.floatPairs.length)    scenesWith.floatPairs.add(scene);
    ft += r.floatOverText.length;  if (r.floatOverText.length) scenesWith.floatOverText.add(scene);
    out += r.outside.length;       if (r.outside.length)       scenesWith.outside.add(scene);
    tex += r.rawTex.length;        if (r.rawTex.length)        scenesWith.rawTex.add(scene);
  }
  const line = (name, n, set) =>
    console.log(`${name.padEnd(34)} ${String(n).padStart(5)}   сцен: ${set.size}`);
  console.log('\n── ИТОГ ──────────────────────────────────────────────');
  line('подпись × подпись', tp, scenesWith.textPairs);
  line('плавающий × плавающий', fp, scenesWith.floatPairs);
  line('плавающий × подпись', ft, scenesWith.floatOverText);
  line('подпись за краем холста', out, scenesWith.outside);
  line('сырой LaTeX на холсте (п. 42)', tex, scenesWith.rawTex);
  await browser.close();
})();
