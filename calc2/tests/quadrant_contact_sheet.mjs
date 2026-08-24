/* Контактный лист приёмки «правило первой четверти».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/quadrant_contact_sheet.mjs

   Снимает по два кадра (светлая и тёмная тема) на каждый случай и собирает
   reports/calc2_quadrant/index.html. Смотреть глазами — «тесты зелёные»
   доказывают математику, а не то, что на экране красиво.
*/
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const OUT = 'reports/calc2_quadrant';
mkdirSync(OUT, { recursive: true });

// Общий кусок: развернуть сцену сложения под заданные формулы групп.
const SUM = (d, s) => `
  sumSetCount('D', ${d.length}); sumSetCount('S', ${s.length});
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  ${JSON.stringify(d)}.forEach(function (e, i) { updateCurveExpr(gd[i], e); });
  ${JSON.stringify(s)}.forEach(function (e, i) { updateCurveExpr(gs[i], e); });
  renderCurveList(); redrawAll();`;

const SD = (dExpr, sExpr) => `
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), ${JSON.stringify(dExpr)});
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), ${JSON.stringify(sExpr)});
  renderCurveList(); redrawAll();`;

/* В монополии предельные издержки — своя роль (mc), кривой «предложение» там
   нет вовсе. Отдельный помощник, а не общий SD: тот молча падал на undefined. */
const MONO = (dExpr, mcExpr) => `
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), ${JSON.stringify(dExpr)});
  var mc = STATE.curves.find(function (c) { return c.role === 'mc' || c.role === 'supply'; });
  if (mc) updateCurveExpr(mc, ${JSON.stringify(mcExpr)});
  renderCurveList(); redrawAll();`;

const SHOTS = [
  { id: 'a-sdsum-regress', scene: 'sdsum', title: 'Набор А — регрессия',
    note: 'D₁ 100−Q, D₂ 60−Q; S₁ Q, S₂ Q+20. Q* 70, P* 45, CS 1625, PS 1325, SW 2950. ' +
          'Ни одно число не должно было измениться.',
    setup: SUM(['100-Q', '60-Q'], ['Q', 'Q+20']) },

  { id: 'b-sdsum-start', scene: 'sdsum', title: 'Набор Б — стартовый масштаб',
    note: 'D₁ 100−Q, D₂ 60−Q, D₃ 40−Q; S₁ Q−100, S₂ Q+20. Главная проверка: равновесие ' +
          'Q* 128, P* 24 находится БЕЗ отдаления. Сама точка лежит правее кадра — это нормально, ' +
          'числа на табло от границ окна больше не зависят.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) },

  { id: 'b-sdsum-far', scene: 'sdsum', title: 'Набор Б — отдалённый масштаб',
    note: 'Тот же набор после трёх щелчков колеса от себя. Видно равновесие, заливки и табло: ' +
          'PS групп 2688 и 8, вместе 2696; PS по суммарной кривой ТОЖЕ 2696 (было NaN); ' +
          'SW 6360. Красного предупреждения о расхождении нет. Заливка PS начинается от оси Q, ' +
          'а не уходит под неё.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) + `
      zoomStep(1.6); zoomStep(1.6); zoomStep(1.6); redrawAll();` },

  { id: 'v-sd-clip', scene: 'sd', title: 'Набор В — кривая обрывается на оси',
    note: 'D 100−Q, S Q, окно расширено до Q = 200. Спрос обрывается ровно у Q = 100, ' +
          'где выходит на ось. Раньше путь тянулся до Q = 200 и уходил до P = −100 — ' +
          'невидимо на экране, но вполне ощутимо в полосе попадания мыши, ключевых точках ' +
          'и в выгрузке .tex.',
    setup: SD('100-Q', 'Q') + `
      document.getElementById('inp-qmax').value = '200';
      document.getElementById('inp-pmax').value = '200';
      applyViewBounds(); redrawAll();` },

  { id: 'g-sd-offquad', scene: 'sd', scrollTo: '#ex-body .sb-note:last-child',
    title: 'Набор Г — пересечение вне первой четверти',
    note: 'Спрос 100−P, предложение −200+0,5·P. Пересечение в (−100; 200) — рынка там нет. ' +
          'Табло молчит, излишки не считаются, а в «Объяснении модели» появился абзац с числами ' +
          'и выводом «найдя цену, проверяйте количество» — правая панель прокручена к нему.',
    setup: SD('100-P', '-200+0.5*P') },

  { id: 'd-mono', scene: 'mono', title: 'Монополия — обычный вид',
    note: 'D 100−Q, MC 20. Контрольные числа не сдвинулись: Qm 40, Pm 60, Qc 80. ' +
          'MR обрывается на оси — так и должно быть, пока показана только первая четверть.',
    setup: MONO('100-Q', '20') },

  { id: 'd-mono-plane', scene: 'mono', title: 'Монополия — продолжение MR ниже оси',
    note: 'Та же модель со снятой галочкой «только первая четверть». Видно исключение из ' +
          'правила: MR = 100 − 2Q продолжается вниз до Q = 100, где MR = −100, то есть до ' +
          'Q-перехвата ПОРОДИВШЕГО её спроса. Продолжение вдвое тоньше и полупрозрачное — ' +
          'штрихом его было бы не отличить, MR и так штриховая.',
    setup: MONO('100-Q', '20') + `
      setFirstQuad(false);
      document.getElementById('inp-pmin').value = '-120';
      document.getElementById('inp-qmax').value = '120';
      applyViewBounds(); redrawAll();` },
];

const browser = await chromium.launch();
const page = await browser.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

const rows = [];
for (const shot of SHOTS) {
  const files = {};
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
    await page.evaluate(k => { resetSceneMemory(); pickScene(k); }, shot.scene);
    await page.waitForTimeout(700);
    await page.evaluate(code => { (new Function(code))(); }, shot.setup);
    await page.waitForTimeout(500);
    /* ⚠️ КАРТОЧКИ РАСКРЫВАЕМ САМИ. Сцена открывается со свёрнутыми
       «Ключевыми значениями» и «Объяснением модели», и снимок без этого
       показывал бы две закрытые полоски вместо чисел — то есть ровно то, что
       владелец и должен принимать. Тот же приём, что в canon_checks.mjs. */
    await page.evaluate(() => {
      document.querySelectorAll('.fold-btn[aria-controls]').forEach(btn => {
        const body = document.getElementById(btn.getAttribute('aria-controls'));
        if (!body) return;
        body.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
        const card = btn.closest('.section, .side-part');
        if (card) card.classList.add('open-card');
      });
      if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
    });
    await page.waitForTimeout(600);
    /* ⚠️ ПРОКРУТКА ПАНЕЛЕЙ ПРОТЕКАЕТ ИЗ СНИМКА В СНИМОК. Один кадр
       подкрутили к нужному абзацу — и следующие три сняты с уехавшими
       панелями и белой полосой снизу. Сбрасываем всё, что прокручивается,
       перед КАЖДЫМ кадром, а нужное подкручиваем после. */
    await page.evaluate(() => {
      window.scrollTo(0, 0);
      document.querySelectorAll('*').forEach(el => {
        if (el.scrollTop) el.scrollTop = 0;
      });
    });
    await page.waitForTimeout(150);
    /* Нужный абзац бывает ниже края панели: разбор сцены идёт первым, а наш
       абзац дописывается в конец. Подкручиваем, иначе на снимке его нет. */
    if (shot.scrollTo) {
      await page.evaluate(sel => {
        const el = document.querySelector(sel);
        if (el) el.scrollIntoView({ block: 'center' });
        // scrollIntoView двигает и саму страницу — на снимке уезжала шапка
        // и оставалась белая простыня. Панель прокручена, окно возвращаем.
        window.scrollTo(0, 0);
      }, shot.scrollTo);
      await page.waitForTimeout(300);
    }
    const name = `${shot.id}-${theme}.png`;
    await page.screenshot({ path: `${OUT}/${name}` });
    files[theme] = name;
    console.log('снят ' + name);
  }
  rows.push({ ...shot, files });
}
if (errs.length) console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | '));
await browser.close();

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Правило первой четверти — контактный лист</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif;
         margin: 0 auto; max-width: 1180px; padding: 32px 20px 64px; }
  h1 { font-size: 26px; margin: 0 0 4px; }
  .lead { color: #666; margin: 0 0 28px; }
  section { margin: 0 0 40px; padding: 0 0 32px; border-bottom: 1px solid #ddd; }
  h2 { font-size: 19px; margin: 0 0 6px; }
  .note { color: #555; margin: 0 0 14px; max-width: 82ch; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  figure { margin: 0; }
  figcaption { font-size: 13px; color: #777; margin: 0 0 6px; }
  img { width: 100%; border: 1px solid #ccc; border-radius: 8px; display: block; }
  @media (max-width: 900px) { .pair { grid-template-columns: 1fr; } }
  @media (prefers-color-scheme: dark) {
    body { background: #16181c; color: #e6e6e6; }
    .lead, .note, figcaption { color: #a2a6ad; }
    section { border-color: #303338; } img { border-color: #3a3d43; }
  }
</style></head><body>
<h1>Правило первой четверти — контактный лист приёмки</h1>
<p class="lead">Ветка <code>feat/calc2-quadrant</code>. Слева светлая тема, справа тёмная.
Числа проверены прибором <code>calc2/tests/quadrant_probe.mjs</code>; эти снимки — для глаз.</p>
${rows.map(r => `<section>
  <h2>${esc(r.title)}</h2>
  <p class="note">${esc(r.note)}</p>
  <div class="pair">
    <figure><figcaption>светлая</figcaption><img src="${r.files.light}" alt="${esc(r.title)}, светлая тема"></figure>
    <figure><figcaption>тёмная</figcaption><img src="${r.files.dark}" alt="${esc(r.title)}, тёмная тема"></figure>
  </div>
</section>`).join('\n')}
</body></html>
`;
writeFileSync(`${OUT}/index.html`, html);
console.log('\nконтактный лист: ' + OUT + '/index.html');
