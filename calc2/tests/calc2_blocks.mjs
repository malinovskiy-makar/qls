// Проверка СКЕЛЕТА 10 блоков: каждая рабочая карточка окна выбора должна
// открываться без ошибок JS, ставить свой подрежим и прятать переключатели
// соседних моделей. Карточки «скоро» должны быть видны, но не нажиматься.
//
// В manage.py test не подключён (поднимает браузер). Запуск руками:
//   ./venv/Scripts/python.exe manage.py runserver 8099 --noreload
//   node calc2/tests/calc2_blocks.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });

await page.setViewportSize({ width: 1400, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);

const checks = [];
const t = async (name, fn) => {
  try { const r = await fn(); checks.push([r === true ? 'OK' : 'FAIL', name, r === true ? '' : String(r)]); }
  catch (e) { checks.push(['ERR', name, e.message]); }
};

/* --- 1. Состав окна ------------------------------------------------- */
await t('десять блоков плюс свободный холст', async () =>
  (await page.locator('.picker-group').count()) === 11 || 'групп: ' + (await page.locator('.picker-group').count()));

await t('Математика идёт первым блоком', async () =>
  (await page.locator('.picker-group-label').first().textContent()).trim().startsWith('1 · Математика') || 'первый не Математика');

await t('карточек «скоро» ровно 19', async () =>
  (await page.locator('.scard.soon').count()) === 19 || 'их ' + (await page.locator('.scard.soon').count()));

await t('в потребителе есть заглушка про риск', async () =>
  (await page.locator('.scard.soon[data-scene="cons-risk"]').count()) === 1 || 'карточки риска нет');

await t('карточки «скоро» отключены', async () =>
  (await page.locator('.scard.soon:not([disabled])').count()) === 0 || 'есть нажимаемые');

await t('у каждой карточки есть data-scene', async () => {
  const bad = await page.$$eval('.scard', els => els.filter(e => !e.dataset.scene).length);
  return bad === 0 || (bad + ' без ключа');
});

/* --- 2. Каждая рабочая карточка открывается -------------------------- */
// Ожидания: [ключ карточки, что должно быть в STATE, какие id спрятаны]
const CARDS = [
  ['m-tangent',   s => s.mode === 'math'  && s.mathSub === 'tangent',            ['math-seg']],
  ['m-optimum',   s => s.mode === 'math'  && s.mathSub === 'optimum',            ['math-seg']],
  ['m-transform', s => s.mode === 'math'  && s.mathSub === 'transform',          ['math-seg']],
  ['m-minmax',    s => s.mode === 'math'  && s.mathSub === 'minmax',             ['math-seg']],
  ['m-constraint',s => s.mode === 'math'  && s.mathSub === 'constraint',         ['math-seg']],
  ['m-inverse',   s => s.mode === 'math'  && s.mathSub === 'inverse',            ['math-seg']],
  ['ppf',         s => s.mode === 'ppf'   && s.ppfSub === 'single',              ['ppf-seg']],
  ['ppfsum',      s => s.mode === 'ppf'   && s.ppfSub === 'sum',                 ['ppf-seg']],
  ['trade',       s => s.mode === 'ppf'   && s.ppfSub === 'trade',               ['ppf-seg']],
  ['tradeprice',  s => s.mode === 'ppf'   && s.ppfSub === 'trade',               ['ppf-seg']],
  ['sd',          s => s.mode === 'market' && s.market === 'comp',               ['market-struct-row', 'sec-tax']],
  ['tax',         s => s.taxKind === 'unit' && s.intervType === 'tax',                 ['market-struct-row', 'taxkind-row']],
  ['tax-adv',     s => s.taxKind === 'advalorem',                                ['market-struct-row', 'taxkind-row']],
  ['ceil',        s => s.intervType === 'ceiling',                                     ['market-struct-row', 'taxside-row']],
  ['elast',       s => s.scenario === 'elasticity',                              ['market-struct-row', 'sec-tax']],
  ['ext',         s => s.scenario === 'externality',                             ['market-struct-row', 'sec-tax']],
  ['costs',       s => s.mode === 'costs' && s.costsSub === 'costs',             ['costs-seg']],
  ['prod',        s => s.mode === 'costs' && s.costsSub === 'production',        ['costs-seg']],
  ['plants',      s => s.mode === 'costs' && s.costsSub === 'plants',            ['costs-seg']],
  ['isoquant',    s => s.mode === 'costs' && s.costsSub === 'isoquant',          ['costs-seg']],
  ['mono',        s => s.market === 'monopoly' && s.monoMode === 'simple',       ['market-struct-row', 'mono-submode']],
  ['mono-nat',    s => s.market === 'monopoly' && s.monoMode === 'natural',      ['market-struct-row', 'mono-submode']],
  ['mono-d1',     s => s.market === 'monopoly' && s.monoMode === 'discr1',       ['market-struct-row', 'mono-submode']],
  ['mono-d3',     s => s.market === 'monopoly' && s.monoMode === 'discr3',       ['market-struct-row', 'mono-submode']],
  ['mono-kink',   s => s.market === 'monopoly' && s.monoMode === 'kinked',       ['market-struct-row', 'mono-submode']],
  ['labor',       s => s.mode === 'labor' && s.laborStruct === 'competition',    ['labor-seg']],
  ['labor-mono',  s => s.mode === 'labor' && s.laborStruct === 'monopsony',      ['labor-seg']],
  ['labor-union', s => s.mode === 'labor' && s.laborStruct === 'union',          ['labor-seg']],
  ['labor-bilat', s => s.mode === 'labor' && s.laborStruct === 'bilateral',      ['labor-seg']],
  ['smallopen',   s => s.scenario === 'openecon',                                ['market-struct-row']],
  ['monoexport',  s => s.market === 'monopoly' && s.monoMode === 'discr3',       ['market-struct-row', 'mono-submode']],
  ['consumer',    s => s.mode === 'consumer' && s.consSlutskyOn === false,       ['cons-slutsky-row']],
  ['cons-slutsky',s => s.mode === 'consumer' && s.consSlutskyOn === true,        ['cons-slutsky-row']],
  ['adas',        s => s.mode === 'macro' && s.macroModel === 'adas',            ['macro-seg']],
  ['islm',        s => s.mode === 'macro' && s.macroModel === 'islm',            ['macro-seg']],
  ['phillips',    s => s.mode === 'macro' && s.macroModel === 'phillips',        ['macro-seg']],
  ['money',       s => s.mode === 'macro' && s.macroModel === 'money',           ['macro-seg']],
  ['loanable',    s => s.mode === 'macro' && s.macroModel === 'loanable',        ['macro-seg']],
  ['fx',          s => s.mode === 'macro' && s.macroModel === 'fx',              ['macro-seg']],
  ['ineq',        s => s.mode === 'inequality',                                  []],
  ['laffer',      s => s.mode === 'macro' && s.macroModel === 'laffer',          ['macro-seg']],
  ['free',        s => s.mode === 'market' && s.curves.length === 0,             []],
];

for (const [key, want, lock] of CARDS) {
  await t(`карточка ${key}`, async () => {
    await page.evaluate(() => openPicker());
    await page.waitForTimeout(60);
    await page.click(`.scard[data-scene="${key}"]`);
    await page.waitForTimeout(220);

    const st = await page.evaluate(() => ({
      mode: STATE.mode, market: STATE.market, scenario: STATE.scenario, intervType: STATE.intervType,
      monoMode: STATE.monoMode, costsSub: STATE.costsSub, ppfSub: STATE.ppfSub,
      laborStruct: STATE.laborStruct, mathSub: STATE.mathSub, macroModel: STATE.macroModel,
      taxKind: STATE.taxKind, consSlutskyOn: STATE.consSlutskyOn,
      sceneKey: STATE.sceneKey, curves: STATE.curves.map(c => c.role || '?'),
    }));
    if (st.sceneKey !== key) return `sceneKey = ${st.sceneKey}`;
    if (!want(st)) return 'состояние: ' + JSON.stringify(st);

    // Заперты именно те переключатели, что записаны в маршруте.
    const hidden = await page.evaluate(ids => ids.map(id => {
      const el = document.getElementById(id);
      return !el ? 'НЕТ ЭЛЕМЕНТА ' + id : (el.classList.contains('scoped-off') ? null : 'виден ' + id);
    }).filter(Boolean), lock);
    if (hidden.length) return hidden.join('; ');
    return true;
  });
}

/* --- 2б. Сцена собирается заново, а не наследует чужие кривые ---------- */
// Рынок труда живёт на общем списке кривых. Пресет ставился только при первом
// входе, поэтому вторая попытка открыть сцену после монополии доставалась с
// кривыми монополии: ни предложения труда, ни равновесия.
await t('труд после монополии остаётся рабочим', async () => {
  for (let pass = 0; pass < 2; pass++) {
    await page.evaluate(() => openPicker());
    await page.click('.scard[data-scene="mono"]');
    await page.waitForTimeout(300);
    await page.evaluate(() => openPicker());
    await page.click('.scard[data-scene="labor"]');
    await page.waitForTimeout(700);
    const st = await page.evaluate(() => ({
      roles: STATE.curves.map(c => c.role),
      eq: !!STATE.laborEq,
    }));
    if (!st.roles.includes('supply') || !st.eq) return `заход ${pass + 1}: ${JSON.stringify(st)}`;
  }
  return true;
});

/* --- 3. Возврат к свободному холсту снимает все запреты --------------- */
await t('свободный холст ничего не прячет', async () => {
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="free"]');
  await page.waitForTimeout(250);
  const n = await page.evaluate(() => document.querySelectorAll('.scoped-off').length);
  return n === 0 || (n + ' элементов остались спрятанными');
});

/* --- 4. Заголовок сцены совпадает с именем карточки ------------------- */
await t('заголовок сцены берётся из карточки', async () => {
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="mono-nat"]');
  await page.waitForTimeout(200);
  const txt = (await page.locator('#scene-name').textContent()).trim();
  return txt === 'Естественная монополия' || txt;
});

/* --- 5. Пульт узнаёт базовую сцену ------------------------------------ */
await t('baseScene сводит подрежим к базе', () => page.evaluate(() =>
  (baseScene('mono-nat') === 'mono' && baseScene('labor-bilat') === 'labor'
   && baseScene('tax-adv') === 'tax' && baseScene('sd') === 'sd') || 'baseScene врёт'));

/* --- Итог ------------------------------------------------------------- */
for (const [st, name, info] of checks) console.log(`${st === 'OK' ? '✓' : '✗'} ${name}${info ? ' — ' + info : ''}`);
const bad = checks.filter(c => c[0] !== 'OK').length;
if (errors.length) { console.log('\nОшибки страницы:'); errors.forEach(e => console.log('  ' + e)); }
console.log(`\n=== скелет блоков: ${checks.length - bad} прошло, ${bad} провалено; ошибок страницы ${errors.length} ===`);
await browser.close();
process.exit(bad || errors.length ? 1 : 0);
