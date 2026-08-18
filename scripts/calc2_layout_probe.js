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

  /* ⚠️ ПОДПИСЬ БЫВАЕТ ВНУТРИ ХОЛСТА, НО СНАРУЖИ СВОЕГО КЛИПА (Добавка А).
     Сравнения с границами `#chart` мало: в сценах с двумя панелями группа
     несёт свой `clip-path`, и обрезает именно он. Замеренный случай —
     `m-tangent`: подпись «−6» лежит с x = 23 до 36, а `#tan-clip-top`
     начинается с 29, поэтому на экране читается «6». Метрика «за краем»
     такую потерю не видела вовсе.
     Прямоугольник берётся у ближайшего предка с `clip-path` и переводится
     в координаты холста через его же `getScreenCTM` — так учитывается
     любое преобразование группы, а не только сдвиг. */
  const clipOf = (node) => {
    let el = node;
    while (el && el !== svgEl) {
      const cp = el.getAttribute && el.getAttribute('clip-path');
      const m = cp && cp.match(/url\(#([^)]+)\)/);
      if (m) {
        const def = svgEl.querySelector('#' + m[1]) || document.getElementById(m[1]);
        const rc = def && def.querySelector('rect');
        const ctm = el.getScreenCTM && el.getScreenCTM();
        if (rc && ctm) {
          const num = (a) => parseFloat(rc.getAttribute(a)) || 0;
          const at = (px, py) => {
            const p = svgEl.createSVGPoint(); p.x = px; p.y = py;
            const q = p.matrixTransform(ctm);
            return { x: q.x - box.left, y: q.y - box.top };
          };
          const a = at(num('x'), num('y'));
          const b = at(num('x') + num('width'), num('y') + num('height'));
          return { id: m[1],
                   x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
                   w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) };
        }
      }
      el = el.parentNode;
    }
    return null;
  };

  /* ── Тексты холста ───────────────────────────────────────────── */
  const texts = [];
  svgEl.querySelectorAll('text').forEach(t => {
    const cs = getComputedStyle(t);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < .05) return;
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    texts.push({ s: ownText(t).slice(0, 28), r: rel(r), node: t,
                 cls: t.getAttribute('class') || '', clip: clipOf(t) });
  });

  const textPairs = [];
  for (let i = 0; i < texts.length; i++)
    for (let j = i + 1; j < texts.length; j++) {
      const a = overlap(texts[i].r, texts[j].r);
      if (a) textPairs.push({ a: texts[i].s, b: texts[j].s, area: a });
    }

  /* ── Плавающее НАД холстом: HTML-блоки внутри обёртки ─────────── */
  /* ⚠️ У ПЛАВАЮЩЕГО БЛОКА ЕСТЬ СВОИ ПОДПИСИ, И ЭТО НЕ НАЛОЖЕНИЕ.
     Легенда — блок с текстом внутри, и первая версия замера считала её
     собственные строки («CS», «PS», «DWL») чужими подписями под ней: 96
     наложений из 127 были выдумкой самого прибора. Помним узел блока и
     пропускаем всё, что лежит ВНУТРИ него. */
  const floats = [];
  wrap.querySelectorAll('.graph-tools, .quick-area, .wrench, .graph-float').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.hasAttribute('hidden')) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1) return;
    floats.push({ s: el.id || el.className, r: rel(r), node: el });
  });
  /* Легенду рисует сам SVG — она такой же плавающий блок по смыслу. */
  const legend = svgEl.querySelector('.legend, [data-legend-box]');
  if (legend) { const r = legend.getBoundingClientRect();
                if (r.width > 1) floats.push({ s: 'легенда', r: rel(r), node: legend }); }

  const floatPairs = [];
  for (let i = 0; i < floats.length; i++)
    for (let j = i + 1; j < floats.length; j++) {
      const a = overlap(floats[i].r, floats[j].r);
      if (a) floatPairs.push({ a: floats[i].s, b: floats[j].s, area: a });
    }
  const floatOverText = [];
  floats.forEach(f => texts.forEach(t => {
    if (f.node && t.node && f.node.contains(t.node)) return;   // своя подпись — не наложение
    const a = overlap(f.r, t.r);
    if (a) floatOverText.push({ float: f.s, text: t.s, area: a });
  }));

  /* ── Обрезка подписи: холстом ИЛИ своим клипом ───────────────── */
  const cut = (t) => {
    const wide = { x: 0, y: 0, w: box.width, h: box.height };
    const boxes = [['холст', wide]];
    if (t.clip) boxes.push(['клип #' + t.clip.id, t.clip]);
    for (const [why, b] of boxes)
      if (t.r.x < b.x - 0.5 || t.r.y < b.y - 0.5 ||
          t.r.x + t.r.w > b.x + b.w + 0.5 || t.r.y + t.r.h > b.y + b.h + 0.5)
        return why;
    return '';
  };
  const outside = texts.filter(t => cut(t))
    .map(t => ({ s: t.s, why: cut(t), x: +t.r.x.toFixed(1), y: +t.r.y.toFixed(1),
                 right: +(t.r.x + t.r.w).toFixed(1), bottom: +(t.r.y + t.r.h).toFixed(1),
                 clip: t.clip ? { x: +t.clip.x.toFixed(1), y: +t.clip.y.toFixed(1),
                                  right: +(t.clip.x + t.clip.w).toFixed(1),
                                  bottom: +(t.clip.y + t.clip.h).toFixed(1) } : null }));

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
