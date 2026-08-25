/* Контактный лист приёмки «ядро и конструктор».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/input_contact_sheet.mjs

   Снимает по два кадра (светлая и тёмная тема) на каждый случай и собирает
   reports/calc2_input/index.html. Смотреть глазами — «тесты зелёные»
   доказывают математику, а не то, что на экране красиво.

   ⚠️ ПРОКРУТКА ПАНЕЛЕЙ ПРОТЕКАЕТ ИЗ СНИМКА В СНИМОК — урок прошлых сессий.
   Сбрасывается перед КАЖДЫМ кадром, нужное подкручивается после.
*/
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const OUT = 'reports/calc2_input';
mkdirSync(OUT, { recursive: true });

// Кривые ставим ТЕМ ЖЕ путём, что человек в поле, и перерисовываем список:
// без renderCurveList в полях остаётся прежний текст, и на снимке видно одно,
// а посчитано другое.
const SD = (dExpr, sExpr) => `
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), ${JSON.stringify(dExpr)});
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), ${JSON.stringify(sExpr)});
  renderCurveList(); redrawAll();`;

// Кусочная собирается ТЕМ ЖЕ путём: кнопка клавиатуры, вход в конструктор,
// «Поставить в поле». Через прямую запись в поле снимок был бы про другое.
const PW = (rows) => `
  var inp = document.getElementById('curve-expr-1');
  inp.closest('.f-row').querySelector('.f-help').click();
  document.querySelector('.mkbd.open .mkbd-foot button').click();
  PW.n = ${rows.length}; PW.rows = ${JSON.stringify(rows)};
  renderPw();
  document.getElementById('pw-apply').click();`;

const SHOTS = [
  { id: 'a-mono-narrow', scene: 'mono', title: 'Монополия на СУЖЕННОМ окне: Qm 40, Pm 60, Qc 80',
    note: 'D 100−Q, MC 20, окно сужено до Q = 30 — то есть оптимум монополии лежит ЗА краем ' +
          'кадра. Раньше findRoot искал MR = MC только до края окна, корень 40 туда не попадал, ' +
          'и всё табло монополии гасло: ни выпуска, ни цены, ни конкурентного объёма. ' +
          'Теперь область поиска берётся у самих кривых: числа те же, что на любом другом ' +
          'масштабе, и в «Ключевых значениях» они есть.',
    setup: `
      updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100 - Q');
      var mc = STATE.curves.find(function (c) { return c.role === 'mc'; });
      if (mc) updateCurveExpr(mc, '20');
      renderCurveList();
      setRanges(30, 30); redrawAll();` },

  { id: 'b-pw-two', scene: 'sd', title: 'Кусочная в поле: два куска, поле выросло в высоту',
    note: 'Собрана конструктором и поставлена в поле. Запись видна ЦЕЛИКОМ: и формулы, и оба ' +
          'условия. Раньше содержимое было 236 px в окне 151 и обрывалось на слове «если» — ' +
          'обрезка живёт внутри MathLive, снаружи поле выглядело исправным. Строка отдала ' +
          'полю всю ширину (кнопка клавиатуры переехала под него), кегль подобран до 12,0 px.',
    setup: PW([{ f: '100 - Q', a: '0', b: '40' }, { f: '80 - 0.5*Q', a: '40', b: '' }]) },

  { id: 'v-pw-three', scene: 'sd', title: 'Кусочная в поле: три куска, три строки',
    note: 'То же самое на трёх участках. Кегль 11,2 px — выше нижнего предела 11 px, ниже ' +
          'которого запись не сжимается. Соседняя строка предложения осталась однострочной, ' +
          'карточка «Ввод функций» не разъехалась.',
    setup: PW([{ f: '100 - Q', a: '0', b: '30' }, { f: '85 - 0.5*Q', a: '30', b: '60' },
               { f: '70 - 0.25*Q', a: '60', b: '' }]) },

  { id: 'g-panel-hints', scene: 'sd', title: 'Левая панель «Спроса и предложения»: одиноких «?» нет',
    note: 'Смотреть на вопросики. Было: два знака висели в пустых строках посреди панели ' +
          'при НУЛЕ живых подсказок у сцены — подсказка без якоря получала собственную пустую ' +
          'строку `.help-anchor`. Стало: таких строк в разметке ноль, знак появляется только ' +
          'рядом с тем, что он поясняет, и только если у него есть живая подсказка.',
    setup: SD('100-Q', 'Q'), clip: 'panel' },

  { id: 'd-picker', scene: null, title: 'Первый экран: карточка подсвечивается при наведении',
    note: 'Курсор наведён на первую карточку («Математика»). Рамка малиновая — та же, что ' +
          'у любой другой карточки. Раньше правило гашения кольца весом било `:hover`, и ' +
          'первая карточка под курсором оставалась серой, пока не нажмёшь клавишу. Светлого ' +
          'кольца клавиатурного фокуса при этом нет: мышь его не будит.',
    picker: true },

  { id: 'e-sum-record', scene: 'sdsum', scrollTo: '#ex-body .sb-note:last-child',
    title: '«Сложение спросов»: аналитическая запись помещается в панель',
    note: 'Четыре группы спроса — в записи рыночного спроса четыре участка. Правая панель ' +
          'прокручена к «Объяснению модели». Было: содержимое 239 px во врезке шириной 215, ' +
          'запись уезжала за правый край. Стало: кегль подобран вниз (12,0 и 13,2 px при ' +
          'нижнем пределе 10 px), обе записи целиком внутри панели.',
    setup: `
      sumSetCount('D', 4); sumSetCount('S', 2);
      var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
      ['100 - Q', '80 - Q', '60 - Q', '40 - Q'].forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
      var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
      ['Q', 'Q + 20'].forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
      renderCurveList(); redrawAll();` },

  { id: 'zh-narrow', scene: 'sd', width: 380, title: 'Ширина окна 380 px: узкий вид записи',
    note: 'Панель на таком экране всего 200 px, и обычная запись «формула, если условие» не ' +
          'помещается ни при каком читаемом кегле. Условие переезжает под свою формулу — ' +
          'поле растёт в высоту, как и решил владелец. Горизонтальной обрезки нет, кегль на ' +
          'нижнем пределе 11 px, запись разбирается обратно в ту же цепочку условий.',
    setup: PW([{ f: '100 - Q', a: '0', b: '40' }, { f: '80 - 0.5*Q', a: '40', b: '' }]) },
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

const rows = [];
for (const shot of SHOTS) {
  const files = {};
  for (const theme of ['light', 'dark']) {
    await page.setViewportSize({ width: shot.width || 1500, height: 950 });
    /* ⚠️ ПЕРВЫЙ ЭКРАН СНИМАЕМ ТОЛЬКО СО СВЕЖЕЙ ЗАГРУЗКИ. Кольцо гасится
       разово при открытии окна выбора, и после любой клавиши или щелчка
       класс снят — снимок показал бы не то состояние, которое принимают. */
    await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1100);
    await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
    await page.waitForTimeout(300);

    if (shot.picker) {
      const card = await page.$('#picker-blocks .bcard');
      if (card) await card.hover();
      await page.waitForTimeout(400);
    } else {
      await page.evaluate(k => { resetSceneMemory(); pickScene(k); }, shot.scene);
      await page.waitForTimeout(800);
      if (shot.setup) {
        await page.evaluate(code => { (new Function(code))(); }, shot.setup);
        await page.waitForTimeout(900);
      }
      /* ⚠️ КАРТОЧКИ РАСКРЫВАЕМ САМИ. Сцена открывается со свёрнутыми
         «Ключевыми значениями» и «Объяснением модели», и снимок без этого
         показывал бы две закрытые полоски вместо чисел. */
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
        if (typeof redrawAll === 'function') redrawAll();
      });
      await page.waitForTimeout(800);
    }
    // Прокрутка панелей: сбрасываем ПЕРЕД кадром, нужное подкручиваем после.
    await page.evaluate(() => {
      window.scrollTo(0, 0);
      document.querySelectorAll('*').forEach(el => { if (el.scrollTop) el.scrollTop = 0; });
    });
    await page.waitForTimeout(150);
    if (shot.scrollTo) {
      await page.evaluate(sel => {
        const el = document.querySelector(sel);
        if (el) el.scrollIntoView({ block: 'center' });
        window.scrollTo(0, 0);
      }, shot.scrollTo);
      await page.waitForTimeout(300);
    }
    const name = `${shot.id}-${theme}.png`;
    // Панель крупно снимаем самой панелью: на общем кадре вопросиков не разглядеть.
    const target = (shot.clip === 'panel') ? await page.$('#tools-panel') : null;
    if (target) await target.screenshot({ path: `${OUT}/${name}` });
    else await page.screenshot({ path: `${OUT}/${name}` });
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
<title>Ядро и конструктор — контактный лист</title>
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
<h1>Ядро и конструктор — контактный лист приёмки</h1>
<p class="lead">Ветка <code>feat/calc2-input</code>. Слева светлая тема, справа тёмная.
Числа проверены прибором <code>calc2/tests/input_probe.mjs</code> (наборы К, П, Ш, В, Ф, З, Я)
и случаями (кадр-а)…(кадр-е), (конс-а), (конс-б), (панель-а) в
<code>calc2/tests/calc2_math.mjs</code>; эти снимки — для глаз.</p>
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
