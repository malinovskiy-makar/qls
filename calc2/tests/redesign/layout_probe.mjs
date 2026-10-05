/* РАСКЛАДКА НОВОГО ЭКРАНА «Графиков» — числа из инвариантов задания редизайна.

   1440×760: шапка сайта 48, шапка модели 56, «Условие» 336, колонка холста 754,
   «Ответ» 348, панель холста 44, SVG 732×590. 1280×700: колонки 304 и 316,
   холст 658, SVG 636×530. 1024: «Условие» 304, «Ответ» выезжает панелью.
   390×844: SVG 372×300, зона касания каждого видимого органа ≥ 44×44.
   На 360, 390, 560, 760, 1024: ничто не едет вбок — у каждого видимого органа
   правый край не дальше окна либо есть прокручиваемый предок.
   Ключевая точка: радиус 4, ореол 9,5 при 0,2; капсула высотой 28.
   Печать: на листе холст, название и строки чисел; шапок, колонок, окон нет.

   node calc2/tests/redesign/layout_probe.mjs     Код 0 — всё в норме.        */
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
let bad = 0;
const ok = (cond, name, got) => { if (!cond) bad++; console.log((cond ? 'OK   ' : 'FAIL ') + name + (got !== undefined ? '  → ' + got : '')); };
const near = (a, b, t = 1.01) => Math.abs(a - b) <= t;

async function open(w, h, key, mobile) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: !!mobile, hasTouch: !!mobile, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  await page.goto(BASE + '/calc2/' + (key ? '?m=' + key : ''), { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
  await page.waitForTimeout(1200);
  return { ctx, page };
}
const box = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }, sel);

// 1440×760
{
  const { ctx, page } = await open(1440, 760, 'taxes');
  const nav = await box(page, '.site-nav, nav'), mh = await box(page, '#model-head');
  const cond = await box(page, '#tools-panel'), col = await box(page, '#canvas-col'), ans = await box(page, '#params-panel');
  const bar = await box(page, '#canvas-bar'), svg = await box(page, '#chart');
  console.log('1440×760:', JSON.stringify({ nav: nav && nav.h, mh: mh.h, cond: cond.w, col: col.w, ans: ans.w, bar: bar.h, svg: [svg.w, svg.h] }));
  ok(nav && near(nav.h, 48), 'шапка сайта 48', nav && nav.h);
  ok(near(mh.h, 56), 'шапка модели 56', mh.h);
  ok(near(cond.w, 337), '«Условие» 336 + граница', cond.w);
  ok(near(col.w, 754), 'колонка холста 754', col.w);
  ok(near(ans.w, 349), '«Ответ» 348 + граница', ans.w);
  ok(near(bar.h, 44), 'панель холста 44', bar.h);
  ok(near(svg.w, 732) && near(svg.h, 590), 'SVG холста 732×590', svg.w + '×' + svg.h);
  // Ключевая точка вида Б.
  await page.evaluate(() => armCurve('D'));
  await page.waitForTimeout(300);
  const kp = await page.evaluate(() => {
    const it = document.querySelector('#chart g.cross-item');
    if (!it) return null;
    const cs = [...it.querySelectorAll(':scope > circle')];
    return { halo: +cs[0].getAttribute('r'), haloOp: +cs[0].getAttribute('opacity'), dot: +cs[2].getAttribute('r') };
  });
  ok(kp && kp.dot === 4 && kp.halo === 9.5 && Math.abs(kp.haloOp - 0.2) < 1e-9, 'ключевая точка: радиус 4, ореол 9,5 при 0,2', JSON.stringify(kp));
  const pt = await page.evaluate(() => { const c = document.querySelectorAll('#chart g.cross-item circle')[2]; const r = c.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; });
  await page.mouse.move(pt[0], pt[1]);
  await page.waitForTimeout(400);
  const cap = await page.evaluate(() => { const r = document.querySelector('#chart g.cross-label rect'); return r ? +r.getAttribute('height') : null; });
  ok(cap === 28, 'капсула высотой 28', cap);
  // Допуск «Сначала сам» (README макета, 9): |a − b| ≤ max(0,011; 0,0005·|b|).
  const g = await page.evaluate(() => [checkGuess('1 245', '1\u202f250'), checkGuess('11,35', '11,35'), checkGuess('11,354', '11,35'), checkGuess('11,3', '11,35'), checkGuess('1250', '1 250')]);
  ok(g[0] === false && g[1] === true && g[2] === true && g[3] === false && g[4] === true,
    '«Сначала сам»: 1 245 к 1 250 — нет; 11,35 и 11,354 к 11,35 — да; 11,3 — нет', JSON.stringify(g));
  // Печать.
  await page.emulateMedia({ media: 'print' });
  const pr = await page.evaluate(() => {
    const vis = (s) => { const e = document.querySelector(s); if (!e) return false; const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden' && e.getBoundingClientRect().height > 0; };
    const stats = document.getElementById('print-stats');
    return { chart: vis('#chart'), head: vis('#model-head'), bar: vis('#canvas-bar'), cond: vis('#tools-panel'), ans: vis('#params-panel'),
             lines: stats ? stats.innerText.split('\n').filter(x => /\d/.test(x)).length : 0, title: stats ? (stats.querySelector('h1, h2, .print-title') || {}).textContent || '' : '' };
  });
  console.log('печать:', JSON.stringify(pr));
  ok(pr.chart && !pr.head && !pr.bar && !pr.cond && !pr.ans && pr.lines > 0, 'печать: холст и строки чисел, без шапок и колонок', JSON.stringify(pr));
  await ctx.close();
}
// 1280×700
{
  const { ctx, page } = await open(1280, 700, 'taxes');
  const cond = await box(page, '#tools-panel'), col = await box(page, '#canvas-col'), ans = await box(page, '#params-panel'), svg = await box(page, '#chart');
  console.log('1280×700:', JSON.stringify({ cond: cond.w, col: col.w, ans: ans.w, svg: [svg.w, svg.h] }));
  ok(near(cond.w, 305) && near(ans.w, 317), 'колонки 304 и 316 (+ граница)', cond.w + ' и ' + ans.w);
  ok(near(col.w, 658), 'холст 658', col.w);
  ok(near(svg.w, 636) && near(svg.h, 530), 'SVG 636×530', svg.w + '×' + svg.h);
  await ctx.close();
}
// 1024×768
{
  const { ctx, page } = await open(1024, 768, 'taxes');
  const cond = await box(page, '#tools-panel'), col = await box(page, '#canvas-col');
  const before = await page.evaluate(() => { const r = document.getElementById('params-panel').getBoundingClientRect(); return r.left >= window.innerWidth - 1; });
  await page.click('#btn-answer');
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => { const r = document.getElementById('params-panel').getBoundingClientRect(); return { left: r.left, w: r.width, in: r.right <= window.innerWidth + 1 && r.left < window.innerWidth - 100 }; });
  console.log('1024×768:', JSON.stringify({ cond: cond.w, col: col.w, ansHiddenBefore: before, after }));
  ok(near(cond.w, 305), '«Условие» 304 (+ граница)', cond.w);
  ok(near(cond.w + col.w, 1024, 2), 'холст забирает остальное', cond.w + col.w);
  ok(before && after.in, '«Ответ» выезжает панелью по кнопке', JSON.stringify(after));
  await ctx.close();
}
// 390×844
{
  const { ctx, page } = await open(390, 844, 'taxes', true);
  const svg = await box(page, '#chart');
  ok(near(svg.w, 372) && near(svg.h, 300), 'телефон: SVG 372×300', svg.w + '×' + svg.h);
  const small = [];
  for (const tab of ['cond', 'ans', 'ex']) {
    await page.click('#ph-tabs .ph-tab[data-tab="' + tab + '"]');
    await page.waitForTimeout(250);
    const s = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('button, input, select, [role=button], math-field').forEach(e => {
        if (e.closest('nav, .site-nav, #site-nav, header.site-header, #corner-stack, .tg-fab')) return;
        if (e.matches('input[type=hidden]')) return;
        const r = e.getBoundingClientRect();
        if (r.width < 1 || r.height < 1 || getComputedStyle(e).visibility === 'hidden') return;
        // Зона касания — сам орган или его подпись-обёртка (label .chk).
        const host = e.closest('label') || e;
        const hr = host.getBoundingClientRect();
        if (Math.max(r.width, hr.width) < 43.5 || Math.max(r.height, hr.height) < 43.5) out.push((e.id || e.className || e.tagName).toString().slice(0, 30) + ' ' + Math.round(r.width) + '×' + Math.round(r.height));
      });
      return out;
    });
    s.forEach(x => small.push(tab + ': ' + x));
  }
  console.log('телефон: органов меньше 44×44 — ' + small.length + (small.length ? ': ' + small.slice(0, 12).join('; ') : ''));
  ok(small.length === 0, 'телефон: зона касания каждого органа ≥ 44×44', small.length);
  await ctx.close();
}
// Ничто не едет вбок.
for (const w of [360, 390, 560, 760, 1024]) {
  const { ctx, page } = await open(w, 800, 'taxes', w < 760);
  const out = await page.evaluate(() => {
    const W = window.innerWidth;
    const scrollable = (e) => { for (let n = e.parentElement; n; n = n.parentElement) { const cs = getComputedStyle(n); if (/(auto|scroll)/.test(cs.overflowX) && n.scrollWidth > n.clientWidth) return true; } return false; };
    const badList = [];
    document.querySelectorAll('button, input, select, math-field, [role=button], a').forEach(e => {
      if (e.closest('nav, .site-nav, #site-nav, header.site-header')) return;
      const r = e.getBoundingClientRect();
      if (r.width < 1 || r.height < 1 || getComputedStyle(e).visibility === 'hidden') return;
      if (r.right > W + 1 && !scrollable(e)) badList.push((e.id || e.className || e.tagName).toString().slice(0, 30));
    });
    return { pageSpill: document.documentElement.scrollWidth - document.documentElement.clientWidth, badList };
  });
  ok(out.pageSpill <= 1 && !out.badList.length, w + ' px: страница не едет вбок, органы в окне', out.pageSpill + ' px, вне окна ' + out.badList.length + (out.badList.length ? ': ' + out.badList.slice(0, 6).join(', ') : ''));
  await ctx.close();
}
await browser.close();
console.log(bad ? '\nНЕ В НОРМЕ: ' + bad : '\nРАСКЛАДКА В НОРМЕ');
process.exit(bad ? 1 : 0);
