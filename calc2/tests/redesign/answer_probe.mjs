/* «ОТВЕТ» НОВОГО ЭКРАНА (фаза 6 редизайна calc2): главные числа — те же числа.

   Для каждого из 44 ключей: модель на свежем состоянии, затем проверки:
     1. каждая ячейка главных чисел (#ans-hero .ans-cell) показывает ровно то
        значение, что строка табло, на которую она ссылается (data-src);
     2. строка-источник в таблице группы не повторяется (класс is-hero), но
        для прибора паритета остаётся в разметке;
     3. у модели из списка главных чисел (HERO) ячеек столько, сколько строк
        нашлось, и не меньше одной, если табло не пустое;
     4. каждое предупреждение сцены (.warn) стоит строкой статуса;
     5. ошибок страницы нет.
   Печатает таблицу «модель → ячейки» для глаза.

   node calc2/tests/redesign/answer_probe.mjs [--keys a,b]
   Код 0 — всё сошлось.                                                     */
import { chromium } from 'playwright';

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('keys', '') || '').split(',').filter(Boolean);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
const keys = (await page.evaluate(() => Object.keys(SCENE_ROUTE))).filter(k => !ONLY.length || ONLY.includes(k));

let bad = 0;
const fail = (m) => { bad++; console.log('  FAIL ' + m); };
for (const key of keys) {
  const e0 = errors.length;
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
  await page.waitForTimeout(450);
  // «Ответ» пересобирается на кадр позже табло (и после отложенных расчётов
  // сцены): ждём два кадра, чтобы читать устоявшийся экран.
  await page.evaluate(() => new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res))));
  await page.waitForTimeout(150);
  const r = await page.evaluate(() => {
    const t = (el) => { if (!el) return ''; const c = el.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s  ​]+/g, ' ').trim(); };
    const cells = [...document.querySelectorAll('#ans-hero .ans-cell')].map(c => {
      const src = c.dataset.src || '';
      let srcVal = null, srcLab = '';
      const m = /^([\w-]+)#(\d+)$/.exec(src);
      if (m) {
        const blk = document.getElementById(m[1]);
        const row = blk ? [...blk.querySelectorAll('.stat')][+m[2]] : null;
        if (row) { srcVal = t(row.querySelector(':scope > b')); srcLab = t(row.querySelector(':scope > span')); }
        if (row && !row.classList.contains('is-hero')) srcVal = '(строка не помечена is-hero)';
      }
      return { src, cap: t(c.querySelector('.ans-lab')), not: t(c.querySelector('.ans-not')), val: t(c.querySelector('.ans-val')), was: t(c.querySelector('.ans-was')), srcVal, srcLab };
    });
    const warns = [...document.querySelectorAll('#sb-body .warn')].filter(w => {
      for (let n = w; n && n.nodeType === 1; n = n.parentElement) { if (n.hidden || (n.style && n.style.display === 'none') || n.classList.contains('scoped-off')) return false; }
      return t(w);
    }).map(t);
    const status = [...document.querySelectorAll('#ans-status .ans-status')].map(t);
    const sb = document.getElementById('sb-body');
    return { cells, warns, status, sbText: sb ? t(sb).length : 0, hasHero: !!(typeof HERO !== 'undefined' && HERO[STATE.sceneKey]) };
  });
  console.log(key + ': ' + (r.cells.map(c => (c.cap + ' ' + (c.not ? c.not + ' = ' : '') + c.val + (c.was ? ' (' + c.was + ')' : ''))).join(' | ') || '— главных чисел нет'));
  r.cells.forEach(c => {
    if (c.srcVal == null) return;   // ячейка из таблицы «До / После / Δ»
    if (c.srcVal !== c.val) fail(key + ': ячейка «' + c.cap + '» ' + c.val + ' ≠ строка «' + c.srcLab + '» ' + c.srcVal);
  });
  if (r.hasHero && !r.cells.length && r.sbText > 0) fail(key + ': у модели есть главные числа (HERO), а ячеек нет');
  r.warns.forEach(w => { if (!r.status.includes(w)) fail(key + ': предупреждение не стоит строкой статуса: «' + w.slice(0, 60) + '»'); });
  errors.slice(e0).forEach(e => fail(key + ': ошибка страницы ' + e));
}
await browser.close();
console.log(bad ? '\nНЕ СОШЛОСЬ: ' + bad : '\nВСЁ СОШЛОСЬ: ' + keys.length + ' моделей');
process.exit(bad ? 1 : 0);
