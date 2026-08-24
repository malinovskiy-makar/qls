/* Контактный лист приёмки «процентные налоги и субсидии».

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/pct_tax_contact_sheet.mjs

   Снимает по два кадра (светлая и тёмная тема) на каждый случай и собирает
   reports/calc2_pct_tax/index.html. Смотреть глазами — «тесты зелёные»
   доказывают математику, а не то, что на экране красиво.

   ⚠️ ПРОКРУТКА ПАНЕЛЕЙ ПРОТЕКАЕТ ИЗ СНИМКА В СНИМОК — урок прошлой сессии.
   Сбрасывается перед КАЖДЫМ кадром, нужное подкручивается после.
*/
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const OUT = 'reports/calc2_pct_tax';
mkdirSync(OUT, { recursive: true });

/* Кривые ставим ТЕМ ЖЕ путём, что человек в поле, и обязательно перерисовываем
   список: без renderCurveList в полях панели остаётся прежний текст, и на
   снимке видно одно, а посчитано другое. */
const SD = (dExpr, sExpr) => `
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), ${JSON.stringify(dExpr)});
  updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'supply'; }), ${JSON.stringify(sExpr)});
  renderCurveList(); redrawAll();`;

// Налоговая сцена: кривые + вид вмешательства + форма + ставка.
const TAX = (dExpr, sExpr, type, form, rate) => SD(dExpr, sExpr) + `
  setType(${JSON.stringify(type)}); setTaxForm(${JSON.stringify(form)}); setTax(${rate});
  redrawAll();`;

const SHOTS = [
  { id: 'a-unit', scene: 'taxes', title: 'Потоварный налог t = 40 — регрессия',
    note: 'D 120−Q, S Q. Q₁ 40, Pd 80, Ps 40, сбор 1600, DWL 400. Кривая СДВИГАЕТСЯ ' +
          'параллельно, ставка в рублях, буква t без знака процента, ряд «Налог платит» на месте. ' +
          'Эталон, с которым сравниваются три следующих кадра.',
    setup: TAX('120-Q', 'Q', 'tax', 'unit', 40) },

  { id: 'b-excise', scene: 'taxes', title: 'Акциз τ = 50 % — та же точка, но ПОВОРОТ',
    note: 'Те же кривые. Числа обязаны совпасть с потоварным: Q₁ 40, Pd 80, Ps 40, сбор 1600, ' +
          'DWL 400 — это и есть теорема эквивалентности. А кривая после налога другая: ' +
          'S/(1−τ), она повёрнута, а не сдвинута. Ставка в процентах (τ = 50 %), ряда ' +
          '«Налог платит» нет: у процентной формы плательщик закреплён самой формой. ' +
          'Раньше акциз считался потоварным и давал точку (35; 85/35).',
    setup: TAX('120-Q', 'Q', 'tax', 'excise', 50) },

  { id: 'v-vat', scene: 'taxes', title: 'НДС τ = 100 % — третья форма, та же точка',
    note: 'Те же кривые, S·(1+τ). Q₁ 40, Pd 80, Ps 40, сбор 1600, DWL 400. Три формы, ' +
          'одна точка. Предел ставки у НДС 200 %, у акциза 99 %: у акциза в знаменателе ' +
          '(1 − τ), и при ста продавцу не осталось бы ничего.',
    setup: TAX('120-Q', 'Q', 'tax', 'vat', 100) },

  { id: 'g-sub-buyer', scene: 'taxes', title: 'Субсидия τ = 50 % от цены ПОКУПАТЕЛЯ',
    note: 'Зеркало акциза: S/(1+τ). Q₁ 72, Pd 48, Ps 72, расход 1728 (в табло со знаком минус), ' +
          'DWL 144. В каскаде три кнопки: «Потоварная», «% от цены продавца», ' +
          '«% от цены покупателя» — обе процентные различимы без подсказки.',
    setup: TAX('120-Q', 'Q', 'subsidy', 'subbuyer', 50) },

  { id: 'd-sub-seller', scene: 'taxes', title: 'Субсидия τ = 50 % от цены ПРОДАВЦА',
    note: 'Зеркало НДС: S·(1−τ). Q₁ 80, Pd 40, Ps 80, расход 3200, DWL 400. ' +
          'Точка ДРУГАЯ, чем у субсидии от цены покупателя, — в этом и смысл двух видов.',
    setup: TAX('120-Q', 'Q', 'subsidy', 'subseller', 50) },

  { id: 'e-pivot', scene: 'taxes', title: 'Центр поворота (набор П)',
    note: 'D 120−Q, S 0,5Q+30, акциз 25 %. Q₁ 48, Pd 72, Ps 54, сбор 864, DWL 108. ' +
          'Галочка «только первая четверть» снята, оси раздвинуты влево до Q = −80: обе ' +
          'кривые предложения продолжаются пунктиром вниз-влево к общей точке Q = −60, P = 0. ' +
          'Это и есть центр, вокруг которого идёт поворот (рис. 81 учебника Бахарева).',
    setup: TAX('120-Q', '0.5*Q+30', 'tax', 'excise', 25) + `
      setFirstQuad(false);
      document.getElementById('inp-qmin').value = '-80';
      document.getElementById('inp-pmin').value = '-20';
      document.getElementById('inp-qmax').value = '120';
      applyViewBounds(); redrawAll();` },

  { id: 'zh-explain', scene: 'taxes', scrollTo: '#ex-body .sb-note:last-child',
    title: 'Соотношение цен в «Объяснении модели»',
    note: 'Тот же акциз. В разборе появился абзац про выбранную форму: кривая после налога, ' +
          'соотношение цен Ps = (1−τ)·Pd и формула сбора T = τ·Pd·Q — набраны математикой, ' +
          'а не обычным текстом. Правая панель прокручена к нему.',
    setup: TAX('120-Q', 'Q', 'tax', 'excise', 50) },

  { id: 'z-quad-off', scene: 'sd', title: 'Снятая галочка — кривые не уходят ниже оси Q',
    note: 'D 100−Q, S Q, окно до Q = 200, галочка «только первая четверть» СНЯТА. Оси ' +
          'раздвинуты в минус, сетка нарисована, отрицательная часть плана видна — а ' +
          'экономические кривые всё равно обрываются на осях. Было 160 точек пути с P < 0 ' +
          'у спроса и 80 у предложения, стало ноль у обоих. Q* 50, P* 50, CS = PS = 1250 ' +
          'не изменились.',
    setup: SD('100-Q', 'Q') + `
      document.getElementById('inp-qmax').value = '200';
      document.getElementById('inp-pmax').value = '200';
      applyViewBounds();
      setFirstQuad(false); redrawAll();` },

  { id: 'i-math', scene: 'm-tangent', title: '«Математика» — правило не действует',
    note: 'Парабола x²−4 на полном плане. Здесь кривая это функция, а не экономика: ' +
          'отрицательные значения строятся как раньше, 79 точек пути лежат ниже оси x. ' +
          'Если этот кадр покажет обрубленную снизу параболу — правило первой четверти ' +
          'протекло туда, где его быть не должно.',
    setup: `
      STATE.mathFormula = 'x^2-4';
      var inp = document.getElementById('inp-mathf');
      if (inp) { inp.value = 'x^2-4'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
      setMathWindow(-6, 6, -6, 6); redrawAll();` },
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
<title>Процентные налоги и субсидии — контактный лист</title>
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
<h1>Процентные налоги и субсидии — контактный лист приёмки</h1>
<p class="lead">Ветка <code>feat/calc2-pct-tax</code>. Слева светлая тема, справа тёмная.
Числа проверены прибором <code>calc2/tests/pct_tax_probe.mjs</code> и случаями (проц-а)…(проц-д)
в <code>calc2/tests/calc2_math.mjs</code>; эти снимки — для глаз.</p>
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
