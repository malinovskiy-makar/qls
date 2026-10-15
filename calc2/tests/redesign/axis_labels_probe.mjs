/* ПОДПИСИ ЗНАЧЕНИЙ НА ОСЯХ НЕ НАЛЕЗАЮТ (тихие панели, сессия 7, этап А2; карточка Notion …81b8…).

   Что смотрит: на холсте (#chart) подписи значений точек на осях (text.coord-num: «35_спрос», «65_min», «50_опт»)
   и числа делений шкалы (text.axis-num). Проверки:
     — первая: холст виден и на нём есть числа делений (иначе прибор зеленел бы вхолостую, README 11);
     — прямоугольники любых двух таких подписей не пересекаются (допуск 1 px по каждой оси);
     — каждая такая подпись целиком внутри области SVG (допуск 1 px): ничего не срезано краем.
   Состояния: старт каждой из 42 моделей (1 440 × 900, «Ответ» закрыт — как на первом заходе) и три состояния
   карточки — «Конкурентный рынок труда» (labor, старт, МРОТ включён), «Внешние эффекты» (ext, старт),
   «Двусторонняя монополия» (labor-bilat, старт) — при 1 440 и 1 280, с открытым «Ответом» (холст уже).

   ENGINES=chromium,webkit (по умолчанию chromium). KEYS="labor ext" — выборка моделей для стартов.
   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/axis_labels_probe.mjs
   Код 0 — всё сошлось.                                                     */
import * as pw from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ENGINES = (process.env.ENGINES || 'chromium').split(',').filter(Boolean);
const ALL = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer';
const KEYS = (process.env.KEYS || ALL).split(/\s+/).filter(Boolean);

let bad = 0, total = 0, eng = '';
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' [' + eng + '] ' + label + (detail && !cond ? '  — ' + detail : ''));
}

/* Прямоугольники подписей и холста — в странице. Подпись без размеров (спрятана) не считается. */
function measure() {
  const svg = document.getElementById('chart');
  if (!svg || !svg.getClientRects().length) return null;
  const b = svg.getBoundingClientRect();
  const out = [];
  svg.querySelectorAll('text.coord-num, text.axis-num').forEach(t => {
    if (getComputedStyle(t).display === 'none' || getComputedStyle(t).visibility === 'hidden') return;
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    out.push({ cls: t.classList.contains('coord-num') ? 'coord' : 'tick', text: t.textContent.trim(),
      l: r.left, r: r.right, t: r.top, b: r.bottom });
  });
  return { svg: { l: b.left, r: b.right, t: b.top, b: b.bottom }, labels: out };
}

function check(name, m) {
  ok(name + ': холст виден, чисел делений > 0', !!m && m.labels.some(x => x.cls === 'tick'),
    m ? 'делений ' + m.labels.filter(x => x.cls === 'tick').length : 'холста нет');
  if (!m) return;
  const L = m.labels, over = [];
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
    const a = L[i], c = L[j];
    if (a.cls === 'tick' && c.cls === 'tick') continue;   // деления между собой разводит сама шкала
    const dx = Math.min(a.r, c.r) - Math.max(a.l, c.l), dy = Math.min(a.b, c.b) - Math.max(a.t, c.t);
    if (dx > 1 && dy > 1) over.push('«' + a.text + '» × «' + c.text + '»');
  }
  ok(name + ': подписи значений и деления не пересекаются', !over.length, over.slice(0, 6).join(', '));
  const out = L.filter(x => x.l < m.svg.l - 1 || x.r > m.svg.r + 1 || x.t < m.svg.t - 1 || x.b > m.svg.b + 1)
    .map(x => '«' + x.text + '»');
  ok(name + ': все подписи внутри холста', !out.length, out.slice(0, 6).join(', '));
}

async function run(engine) {
  eng = engine;
  const browser = await pw[engine].launch();
  let opened = 0;
  const open = async (W, answerOpen) => {
    const ctx = await browser.newContext({ viewport: { width: W, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
    await ctx.addInitScript((o) => { try { localStorage.clear(); localStorage.setItem('theme', 'dark'); if (o) localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} }, answerOpen);
    opened++;
    return ctx;
  };
  const load = async (ctx, key) => {
    const page = await ctx.newPage();
    await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'load', timeout: 40000 });
    await page.waitForFunction(() => typeof redrawAll === 'function' && document.querySelector('#chart text.axis-num'), null, { timeout: 40000 }).catch(() => {});
    await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
    await page.waitForTimeout(500);
    return page;
  };
  console.log('\n=== Три состояния карточки (1 440 и 1 280, «Ответ» открыт) ===');
  for (const W of [1440, 1280]) {
    const ctx = await open(W, true);
    for (const key of ['labor', 'ext', 'labor-bilat']) {
      const page = await load(ctx, key);
      if (key === 'labor') {
        // МРОТ включён (на старте 65): если галочка выключена — включаем, как человек.
        await page.evaluate(() => { const c = document.getElementById('chk-labmin'); if (c && !c.checked) c.click(); });
        await page.waitForTimeout(400);
      }
      check(key + ' @' + W, await page.evaluate(measure));
      await page.close();
    }
    await ctx.close();
  }
  console.log('\n=== Старты 42 моделей (1 440, «Ответ» закрыт) ===');
  let ctx = await open(1440, false);
  for (const key of KEYS) {
    if (opened > 50 && engine === 'webkit') { await ctx.close(); await browser.close(); return run2(engine, KEYS.slice(KEYS.indexOf(key))); }
    const page = await load(ctx, key);
    check(key, await page.evaluate(measure));
    await page.close();
  }
  await ctx.close();
  await browser.close();
}
// WebKit держит не больше ~63 окон: перезапуск браузера на остатке списка.
async function run2(engine, keys) {
  const browser = await pw[engine].launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript(() => { try { localStorage.clear(); localStorage.setItem('theme', 'dark'); } catch (e) {} });
  for (const key of keys) {
    const page = await ctx.newPage();
    await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'load', timeout: 40000 });
    await page.waitForTimeout(900);
    check(key, await page.evaluate(measure));
    await page.close();
  }
  await browser.close();
}

for (const e of ENGINES) await run(e);
console.log('\nИТОГ: ' + (total - bad) + ' / ' + total + (bad ? ' — провалов ' + bad : ' — всё сошлось'));
process.exit(bad ? 1 : 0);
