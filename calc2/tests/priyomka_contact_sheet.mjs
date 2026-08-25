/* Контактный лист приёмки 25.08: семь дефектов владельца плюс возможность.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/priyomka_contact_sheet.mjs

   По кадру на каждый починенный дефект в СВЕТЛОЙ и ТЁМНОЙ теме, плюс кадр,
   где видны оба вида пунктира сразу, и кадр подобранной прозрачности групп.
   Собирает reports/calc2_priyomka_fixes/index.html.

   ⚠️ КАРТОЧКИ РАСКРЫВАЕМ САМИ, ПРОКРУТКУ ПАНЕЛЕЙ СБРАСЫВАЕМ ПЕРЕД КАЖДЫМ
   КАДРОМ. Сцена открывается со свёрнутыми карточками, а прокрутка протекает
   из снимка в снимок: подкрутили один — следующие сняты с уехавшими панелями.
*/
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const OUT = 'reports/calc2_priyomka_fixes';
mkdirSync(OUT, { recursive: true });

// Налоговая сцена: свои кривые, свой вид вмешательства, своя ставка.
const TAX = (d, s, type, form, rate) => `
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), ${JSON.stringify(d)});
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), ${JSON.stringify(s)});
  setType(${JSON.stringify(type)});
  ${form ? `setTaxForm(${JSON.stringify(form)});` : ''}
  setTax(${rate});
  renderCurveList(); redrawAll();`;

// Сцена сложения: столько-то групп, у каждой формула.
const SUM = (d, s) => `
  sumSetCount('D', ${d.length}); sumSetCount('S', ${s.length});
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  ${JSON.stringify(d)}.forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
  ${JSON.stringify(s)}.forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
  renderCurveList(); redrawAll();`;

// Сцена сложения КПВ.
const PPF = (exprs) => `
  STATE.ppfSumCount = ${exprs.length};
  ${JSON.stringify(exprs)}.forEach(function (e, i) { ppfSumSet(i, e); });
  STATE.ppfSumData = null;
  var cnt = document.getElementById('ppfsum-count'); if (cnt) cnt.value = ${exprs.length};
  if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
  redrawAll(); ensurePpfSum(); redrawAll();`;

const SHOTS = [
  { id: '1-interv-no-eq', scene: 'taxes',
    title: 'Дефект 1 · вмешательство работает без равновесия',
    note: 'D = 100 − P, S = 0,5·p − 200: пересечение в (−100; 200), то есть рынка в первой '
        + 'четверти нет. Потоварная субсидия 450. БЫЛО: график не двигался вовсе — всё '
        + 'вмешательство было выключено одним условием «есть равновесие». СТАЛО: кривая '
        + 'предложения опустилась и появился настоящий рынок Q = 50, цена покупателя 50, '
        + 'цена продавца 500, расход бюджета 22 500. Потери общества (DWL) при этом НЕ '
        + 'посчитаны — сравнивать не с чем, и панель говорит это словами.',
    setup: TAX('100-P', '0.5*p-200', 'subsidy', 'unit', 450) },

  { id: '1b-interv-curve', scene: 'taxes',
    title: 'Дефект 1 · тот же рынок под налогом 100 — рынок так и не появился',
    note: 'Второй край того же правила. Налог 100 поднимает предложение (оно обращается в '
        + 'ноль при цене 500 вместо 400), кривая после вмешательства нарисована пунктиром — '
        + 'а равновесия по-прежнему нет, и чисел не выдумывается ни одного.',
    setup: TAX('100-P', '0.5*p-200', 'tax', 'unit', 100) },

  { id: '2-panel-order', scene: 'taxes',
    title: 'Дефект 2 · порядок в карточке «Вмешательство государства»',
    note: 'Сверху вниз: вид вмешательства → вид субсидии → кому достаётся → ставка → '
        + 'подсказка → «было → стало». БЫЛО: ряд «Субсидию получает» стоял на y = 136, '
        + 'ставка на y = 199, а сам выбор вида вмешательства только на y = 307 — человек '
        + 'видел ставку раньше, чем то, ставка чего это. Ползунок больше не уезжает в ленту '
        + 'регуляторов наверху панели.',
    setup: TAX('120-Q', 'Q', 'subsidy', 'unit', 40) },

  { id: '4-sum-look', scene: 'sdsum',
    title: 'Дефект 4 · слагаемые оформлены по образцу сложения КПВ',
    note: 'D₁ 100−Q, D₂ 60−Q, D₃ 40−Q; S₁ Q−100, S₂ Q+20. Пять слагаемых стали тонкими и '
        + 'штриховыми (1,6 px, штрих 5/4, прозрачность 0,95), две суммарные остались '
        + 'сплошными и вдвое толще. БЫЛО: семь сплошных линий одного веса. Числа сцены не '
        + 'сдвинулись: Q* 128, P* 24, PS 2696, SW 6360.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) },

  { id: '4b-two-dashes', scene: 'sdsum',
    title: 'Дефект 4 · два вида пунктира в одном кадре',
    note: 'Главный кадр приёмки. Вдоль оси Q от 0 до 100 идёт участок «рынка здесь нет» — '
        + 'штрих 12/6 при полной толщине 3,2 и полной непрозрачности. Рядом пять слагаемых '
        + 'со штрихом 5/4 при толщине 1,6. Отличаются вдвое по толщине и вдвое с лишним по '
        + 'длине штриха: спутать нельзя даже на чёрно-белой печати. Смотреть надо на нижний '
        + 'край холста.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) + `
      CONFIG.Qmin = 0; CONFIG.Qmax = 140; CONFIG.Pmin = 0; CONFIG.Pmax = 40;
      STATE.viewDirty = true; redrawAll();` },

  { id: '4c-opacity', scene: 'sdsum',
    title: 'Дефект 4 · подобранная прозрачность групп 0,95',
    note: 'Прозрачность подобрана перебором с шагом 0,05 от 0,5 вверх по каждому из восьми '
        + 'цветов палитры и в обеих темах; для каждого взято первое значение, при котором '
        + 'контраст итогового цвета к холсту доходит до 3:1, и из шестнадцати найденных '
        + 'взято самое большое. Вышло 0,95 (его требуют фиолетовый и маджента в тёмной теме), '
        + 'худший контраст при нём 3,04:1. Честно: 0,95 от единицы глазом не отличить — весь '
        + 'эффект приглушения несут штрих и толщина, а не прозрачность. Кадр показан ровно '
        + 'для того, чтобы это было видно.',
    setup: SUM(['100-Q', '60-Q', '40-Q', '30-Q'], ['Q', 'Q+20', 'Q+40', 'Q+55']) },

  { id: '6-quad-crossing', scene: 'taxes',
    title: 'Возможность · снятая галочка раздвинула окно до пересечения вне четверти',
    note: 'D = 100 − P, S = 0,5·p − 200, галочка «только первая четверть» снята. БЫЛО: окно '
        + 'открывалось на −25…100 по обеим осям, и точка (−100; 200) в кадр не попадала — '
        + 'чтобы её увидеть, границы приходилось раздвигать руками. СТАЛО: окно '
        + '−110…100 по Q и −25…210 по P, точка внутри с запасом 4,8 % и 4,3 % от края. '
        + 'Раздвигается один раз, в момент снятия галочки; дальше колесо и панорама '
        + 'работают как обычно.',
    setup: TAX('100-P', '0.5*p-200', 'tax', 'unit', 0) + `
      setFirstQuad(false);` },

  { id: '6b-quad-pivot', scene: 'taxes',
    title: 'Возможность · центр поворота при акцизе попал в кадр',
    note: 'D = 120 − Q, S = 0,5·Q + 30, акциз 25 %. Центр поворота (−60; 0) — та самая точка, '
        + 'вокруг которой процентный налог поворачивает предложение (рис. 81 учебника '
        + 'Бахарева). Окно раздвинулось до −70…100 по Q, точка внутри с запасом 5,9 %.',
    setup: TAX('120-Q', '0.5*Q+30', 'tax', 'excise', 25) + `
      setFirstQuad(false);` },

  { id: '6c-quad-mr', scene: 'mono',
    title: 'Возможность · конец продолжения предельного дохода попал в кадр',
    note: 'D = 100 − Q, MC = 20. Продолжение MR идёт вниз до Q = 100, где MR = −100 — оно '
        + 'показывает, ОТКУДА кривая взялась. БЫЛО: конец продолжения лежал ровно на границе '
        + 'кадра и читался как обрыв. СТАЛО: окно −25…110 по Q и −110…100 по P.',
    setup: `updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), '100-Q');
      var mc = STATE.curves.find(function (c) { return c.role === 'mc'; });
      if (mc) updateCurveExpr(mc, '20');
      renderCurveList(); redrawAll(); setFirstQuad(false);` },

  { id: '7-ppf-two', scene: 'ppfsum',
    title: 'Дефект 7 · суммарная КПВ двух кривых — запись математикой',
    note: 'y = 100 − x и y = 60 − 2x. Запись по участкам: Y = 160 − X при 0 ≤ X ≤ 100, затем '
        + 'Y = 260 − 2X при 100 < X ≤ 130. Излом теперь ровно в (100; 60): численный '
        + 'детектор давал (99,999; 60,001). Смотреть в «Объяснении модели», абзац '
        + '«Форма кривой».',
    setup: PPF(['100-x', '60-2x']) },

  { id: '7b-ppf-three', scene: 'ppfsum',
    title: 'Дефект 7 · суммарная КПВ трёх кривых — раньше здесь было «построена численно»',
    note: 'Плюс y = 40 − 4x. Три участка: 200 − X, затем 300 − 2X, затем 560 − 4X до X = 140. '
        + 'Изломы (100; 100) и (130; 40). БЫЛО: для трёх и более кривых панель писала '
        + '«Построена численно», хотя в сложении прямых ничего численного нет.',
    setup: PPF(['100-x', '60-2x', '40-4x']) },
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

async function prepare() {
  await page.evaluate(() => {
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(btn => {
      const body = document.getElementById(btn.getAttribute('aria-controls'));
      if (!body) return;
      body.classList.add('open');
      btn.setAttribute('aria-expanded', 'true');
      const card = btn.closest('.section, .side-part');
      if (card) card.classList.add('open-card');
    });
    document.querySelectorAll('.crow-more').forEach(m => m.classList.add('open'));
    if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
  });
  await page.waitForTimeout(500);
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelectorAll('*').forEach(el => { if (el.scrollTop) el.scrollTop = 0; });
  });
  await page.waitForTimeout(150);
}

const rows = [];
for (const shot of SHOTS) {
  const files = {};
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
    await page.evaluate(k => { resetSceneMemory(); pickScene(k); }, shot.scene);
    await page.waitForTimeout(700);
    await page.evaluate(code => { (new Function(code))(); }, shot.setup);
    await page.waitForTimeout(600);
    await prepare();
    const name = `${shot.id}-${theme}.png`;
    await page.screenshot({ path: `${OUT}/${name}` });
    files[theme] = name;
    console.log('снят ' + name);
  }
  rows.push({ ...shot, files });
}

/* Конструктор кусочной снимается отдельно и при ДВУХ ширинах браузера: смысл
   правки в том, что колонки участка не ужимаются ни при какой из них. */
const pw = [];
for (const W of [1280, 1440]) {
  await page.setViewportSize({ width: W, height: 950 });
  await page.waitForTimeout(400);
  const files = {};
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
    await page.evaluate(() => {
      resetSceneMemory(); pickScene('sd'); redrawAll();
      openPiecewise(document.querySelector('.f-slot > input'), 'Q');
      PW.n = 5;
      PW.rows = [{ f: '100 - Q', a: '0', b: '40' },
                 { f: '(240 - 3*Q)/2 + 0.25*Q', a: '40', b: '120' },
                 { f: '80 - 0.5*Q', a: '120', b: '180' },
                 { f: '0.5*Q - 40', a: '180', b: '240' },
                 { f: '0', a: '240', b: '' }];
      renderPw();
    });
    await page.waitForTimeout(800);
    const name = `3-pw-${W}-${theme}.png`;
    await page.screenshot({ path: `${OUT}/${name}` });
    files[theme] = name;
    console.log('снят ' + name);
    await page.evaluate(() => { const b = document.getElementById('pw-close'); if (b) b.click(); });
    await page.waitForTimeout(300);
  }
  pw.push({ id: `3-pw-${W}`, files,
    title: `Дефект 3 · конструктор кусочной при ширине браузера ${W} px, пять кусков`,
    note: 'Окно 720 px вместо прежних 380. Колонки «От» и «До» получили свою ширину сетки '
        + '(96 px против прежних 52) и ужаться не могут в принципе. Место под кнопку '
        + 'клавиатуры зарезервировано в КАЖДОЙ строке: раньше она переезжала в строку с '
        + 'кареткой и отнимала у поля формулы 38 px — в строке с курсором поле было 118 px, '
        + 'в остальных 156 px, и колонки ездили от того, куда ткнули. Теперь поле формулы '
        + '370 px во всех пяти строках.' });
}
await page.setViewportSize({ width: 1500, height: 950 });

if (errs.length) console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | '));
await browser.close();

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const section = (r) => `<section>
  <h2>${esc(r.title)}</h2>
  <p class="note">${esc(r.note)}</p>
  <div class="pair">
    <figure><figcaption>светлая</figcaption><img src="${r.files.light}" alt="${esc(r.title)}, светлая тема"></figure>
    <figure><figcaption>тёмная</figcaption><img src="${r.files.dark}" alt="${esc(r.title)}, тёмная тема"></figure>
  </div>
</section>`;
const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Приёмка 25.08 — контактный лист</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif;
         margin: 0 auto; max-width: 1180px; padding: 32px 20px 64px; }
  h1 { font-size: 26px; margin: 0 0 4px; }
  .lead { color: #666; margin: 0 0 28px; max-width: 88ch; }
  section { margin: 0 0 40px; padding: 0 0 32px; border-bottom: 1px solid #ddd; }
  h2 { font-size: 19px; margin: 0 0 6px; }
  .note { color: #555; margin: 0 0 14px; max-width: 88ch; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  figure { margin: 0; }
  figcaption { font-size: 13px; color: #777; margin: 0 0 6px; }
  img { width: 100%; border: 1px solid #ccc; border-radius: 8px; display: block; }
  code { font-size: .92em; }
  @media (max-width: 900px) { .pair { grid-template-columns: 1fr; } }
  @media (prefers-color-scheme: dark) {
    body { background: #16181c; color: #e6e6e6; }
    .lead, .note, figcaption { color: #a2a6ad; }
    section { border-color: #303338; } img { border-color: #3a3d43; }
  }
</style></head><body>
<h1>Приёмка 25.08 — контактный лист</h1>
<p class="lead">Ветка <code>feat/calc2-priyomka-fixes</code>. Слева светлая тема, справа тёмная.
Семь дефектов отсмотра владельца плюс возможность «снятая галочка раздвигает окно».
Числа измерены прибором <code>calc2/tests/priyomka_probe.mjs</code> (наборы В П К О С Р);
контрольные числа стоят в <code>calc2/tests/calc2_math.mjs</code>. Эти снимки — для глаз:
«тесты зелёные» доказывают математику и разметку, а не то, что на экране разборчиво.</p>
${rows.map(section).join('\n')}
${pw.map(section).join('\n')}
</body></html>
`;
writeFileSync(`${OUT}/index.html`, html);
console.log('\nконтактный лист: ' + OUT + '/index.html');
