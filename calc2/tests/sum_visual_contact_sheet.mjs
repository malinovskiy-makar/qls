/* Контактный лист приёмки «внешний вид сложения».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/sum_visual_contact_sheet.mjs

   Снимает по два кадра (светлая и тёмная тема) на каждый случай плюс узкий
   экран 380 px и собирает reports/calc2_sum_visual/index.html. Смотреть
   глазами — «тесты зелёные» доказывают математику, а не то, что на экране
   разборчиво.
*/
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const OUT = 'reports/calc2_sum_visual';
mkdirSync(OUT, { recursive: true });

// Развернуть сцену сложения под заданные формулы групп.
const SUM = (d, s) => `
  sumSetCount('D', ${d.length}); sumSetCount('S', ${s.length});
  var gd = STATE.curves.filter(function (c) { return c.sumGroup === 'D' && c.kind !== 'sum'; });
  var gs = STATE.curves.filter(function (c) { return c.sumGroup === 'S' && c.kind !== 'sum'; });
  ${JSON.stringify(d)}.forEach(function (e, i) { if (gd[i]) updateCurveExpr(gd[i], e); });
  ${JSON.stringify(s)}.forEach(function (e, i) { if (gs[i]) updateCurveExpr(gs[i], e); });
  renderCurveList(); redrawAll();`;

const SD = (dExpr, sExpr) => `
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), ${JSON.stringify(dExpr)});
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), ${JSON.stringify(sExpr)});
  renderCurveList(); redrawAll();`;

const SHOTS = [
  { id: 'a-set', scene: 'sdsum', title: 'Набор А — две группы в каждом семействе',
    note: 'D₁ 100−Q, D₂ 60−Q; S₁ Q, S₂ Q+20. Числа те же, что были: Q* 70, P* 45, ' +
          'CS 1625, PS 1325, SW 2950. Смотреть надо на вес линий: суммарные D и S — ' +
          '3,2 px каноническими цветами, четыре группы — 1,6 px своими. ' +
          'На холсте обозначения, полные имена в левой панели.',
    setup: SUM(['100-Q', '60-Q'], ['Q', 'Q+20']) },

  { id: 'b-set', scene: 'sdsum', title: 'Набор Б — три спроса, два предложения, пунктирный участок',
    note: 'D₁ 100−Q, D₂ 60−Q, D₃ 40−Q; S₁ Q−100, S₂ Q+20. Q* 128, P* 24; PS групп 2688 и 8, ' +
          'вместе 2696; CS 3664; SW 6360. Главное на этом кадре — суммарное предложение ' +
          'вдоль оси Q от 0 до 100: рынка там нет, поэтому линия пунктирная. Цвет и толщина ' +
          'у неё те же, что у сплошной части, отличие только в штрихе.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) },

  { id: 'b-far', scene: 'sdsum', title: 'Набор Б — отдалённый масштаб',
    note: 'Тот же набор после трёх щелчков колеса от себя. Видно, где пунктир переходит в ' +
          'сплошную (Q = 100) и как суммарное предложение уходит вверх. Стык считается точно: ' +
          'щель 0,00 px.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) + `
      zoomStep(1.6); zoomStep(1.6); zoomStep(1.6); redrawAll();` },

  { id: 'g2', scene: 'sdsum', title: 'Две группы в каждом семействе',
    note: 'Палитра групп: фиолетовый, янтарный (спрос) и бирюзовый, зелёный (предложение). ' +
          'Ни один не совпадает с каноническими цветами суммарных кривых.',
    setup: SUM(['100-Q', '60-Q'], ['Q', 'Q+20']) },

  { id: 'g3', scene: 'sdsum', title: 'Три группы в каждом семействе',
    note: 'Добавились маджента и сиреневый. Шесть групп и две суммы — восемь линий, ' +
          'все различимы; контраст каждой к холсту не ниже 3,25:1 в обеих темах.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q', 'Q+20', 'Q+40']) },

  { id: 'g4', scene: 'sdsum', title: 'Четыре группы в каждом семействе — вся палитра',
    note: 'Восемь групп плюс две суммы. Задействованы все восемь цветов палитры: ' +
          'фиолетовый, бирюзовый, янтарный, зелёный, маджента, сиреневый, сланцевый, ' +
          'пыльная роза. Двух одинаковых цветов на холсте нет.',
    setup: SUM(['100-Q', '60-Q', '40-Q', '30-Q'], ['Q', 'Q+20', 'Q+40', 'Q+55']) },

  { id: 'panels', scene: 'sdsum', title: 'Обе панели: обозначение связывает холст со списком',
    note: 'Слева перед каждым именем стоит то же обозначение, что на графике, цветом своей ' +
          'линии. У строк «рыночный спрос» и «рыночное предложение» поля формулы нет и быть ' +
          'не может — на его месте стоит надпись «считается по группам — правке не подлежит», ' +
          'и высота строки сравнялась с остальными. Справа подписи ползунков — «Сдвиг D₁ = 0» ' +
          'и родня: ни одна не обрезана, все различимы, дорожки одного вида.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) },

  { id: 'dash-ghost', scene: 'sdsum', title: 'Пунктир «рынка здесь нет» вблизи',
    note: 'Тот же набор Б, окно сужено до Q = 140. Видно ритм штриха: 12 включено, 6 выключено, ' +
          'толщина 3,2 px, цвет — канонический цвет предложения. Раньше на этом месте была ' +
          'сплошная линия по оси, неотличимая от самой оси.',
    setup: SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20']) + `
      document.getElementById('inp-qmax').value = '140';
      document.getElementById('inp-pmax').value = '60';
      applyViewBounds(); redrawAll();` },

  { id: 'dash-quad', scene: 'sd', title: 'Для сравнения: пунктир первой четверти',
    note: 'Другая сцена и другой смысл: спрос 100−P, предложение −200+0,5·P пересекаются ' +
          'в (−100; 200), рынка там нет. Продолжение к этой точке — штрих 5/4, толщина 1,5, ' +
          'прозрачность 0,65. Рядом с ним пунктир «рынка здесь нет» (штрих 12/6, толщина 3,2, ' +
          'непрозрачный) не спутать. ⚠️ В ОДНОЙ СЦЕНЕ ЭТИ ДВА ПУНКТИРА НЕ ВСТРЕЧАЮТСЯ: ' +
          'участок нулевой цены от Q = 0 любой падающий спрос обязан пересечь, поэтому ' +
          'равновесие в первой четверти там находится всегда. Перебор пяти наборов это ' +
          'подтвердил, поэтому кадра «оба сразу» не существует, и сравнивать приходится парой.',
    setup: SD('100-P', '-200+0.5*P') + `
      /* Точка пересечения лежит в (−100; 200) — далеко за стартовым окном.
         Раздвигаем плоскость, иначе на кадре не видно ровно того, ради чего
         он снят: пунктирного продолжения к этой точке. */
      setFirstQuad(false);
      document.getElementById('inp-qmin').value = '-130';
      document.getElementById('inp-qmax').value = '130';
      document.getElementById('inp-pmin').value = '0';
      document.getElementById('inp-pmax').value = '230';
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

/* ⚠️ КАРТОЧКИ РАСКРЫВАЕМ САМИ, ПРОКРУТКУ СБРАСЫВАЕМ ПЕРЕД КАЖДЫМ КАДРОМ.
   Сцена открывается со свёрнутыми карточками, а прокрутка панели протекает
   из снимка в снимок: подкрутили один кадр — следующие три сняты с уехавшими
   панелями и белой полосой снизу. */
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
    await page.waitForTimeout(500);
    await prepare();
    const name = `${shot.id}-${theme}.png`;
    await page.screenshot({ path: `${OUT}/${name}` });
    files[theme] = name;
    console.log('снят ' + name);
  }
  rows.push({ ...shot, files });
}

/* Узкий экран. Отдельным проходом: смена размера окна перестраивает сцену,
   и мешать её с широкими кадрами значит снимать половину из них в переходном
   состоянии. */
await page.setViewportSize({ width: 380, height: 900 });
await page.waitForTimeout(600);
const narrow = [];
for (const [id, title, note, setup] of [
  ['w380-a', 'Узкий экран 380 px — набор А',
   'Подписей за краем холста нет и пересечений нет. До правки за краем оказывались все шесть, ' +
   'и две пары налезали друг на друга.', SUM(['100-Q', '60-Q'], ['Q', 'Q+20'])],
  ['w380-b', 'Узкий экран 380 px — набор Б',
   'То же на трёх группах спроса. Было: шесть подписей за краем, три пересекающиеся пары.',
   SUM(['100-Q', '60-Q', '40-Q'], ['Q-100', 'Q+20'])],
]) {
  const files = {};
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
    await page.evaluate(() => { resetSceneMemory(); pickScene('sdsum'); });
    await page.waitForTimeout(700);
    await page.evaluate(code => { (new Function(code))(); }, setup);
    await page.waitForTimeout(500);
    await prepare();
    const name = `${id}-${theme}.png`;
    await page.screenshot({ path: `${OUT}/${name}` });
    files[theme] = name;
    console.log('снят ' + name);
  }
  narrow.push({ id, title, note, files });
}

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
<title>Внешний вид сложения — контактный лист</title>
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
  .narrow .pair { grid-template-columns: 260px 260px; }
  @media (max-width: 900px) { .pair { grid-template-columns: 1fr; } }
  @media (prefers-color-scheme: dark) {
    body { background: #16181c; color: #e6e6e6; }
    .lead, .note, figcaption { color: #a2a6ad; }
    section { border-color: #303338; } img { border-color: #3a3d43; }
  }
</style></head><body>
<h1>Внешний вид «Сложения спросов и предложений» — контактный лист приёмки</h1>
<p class="lead">Ветка <code>feat/calc2-sum-visual</code>. Слева светлая тема, справа тёмная.
Числа сцены не менялись: <code>quadrant_probe.mjs</code> и <code>input_probe.mjs</code> сошлись,
<code>calc2_math.mjs</code> — 222 из 222. Внешний вид измерен прибором
<code>calc2/tests/sum_visual_probe.mjs</code> (расхождений было 19, стало 0); эти снимки — для глаз.</p>
${rows.map(section).join('\n')}
${narrow.map(r => `<div class="narrow">${section(r)}</div>`).join('\n')}
</body></html>
`;
writeFileSync(`${OUT}/index.html`, html);
console.log('\nконтактный лист: ' + OUT + '/index.html');
