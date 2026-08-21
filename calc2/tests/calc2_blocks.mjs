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
// Блоки окна сценариев свёрнуты (Фаза 6) — раскрываем их перед щелчком по карточке.
// П2: на главном экране видны карточки блоков, модели живут внутри открытого
// блока. Для щелчка по карточке модели раскрываем все блоки разом.
const openGroups = async () => {
  await page.evaluate(() => {
    const b = document.getElementById('picker-blocks');
    if (b) b.classList.add('hidden');
    document.querySelectorAll('#scene-picker .picker-group').forEach(g => g.classList.add('open'));
  });
  await page.waitForTimeout(50);
};
const t = async (name, fn) => {
  try { const r = await fn(); checks.push([r === true ? 'OK' : 'FAIL', name, r === true ? '' : String(r)]); }
  catch (e) { checks.push(['ERR', name, e.message]); }
};

/* --- 1. Состав окна ------------------------------------------------- */
await t('в окне ровно десять блоков', async () =>
  (await page.locator('.picker-group').count()) === 10 || 'групп: ' + (await page.locator('.picker-group').count()));

await t('Математика идёт первой карточкой блока', async () =>
  (await page.locator('.bcard-name').first().textContent()).trim() === 'Математика' || 'первый не Математика');

/* П2: главный экран — десять больших карточек блоков с картинками, по две в
   ряд, без нумерации; ни один блок не раскрыт, кнопки возврата не видно. */
await t('главный экран — карточки блоков с картинками', () => page.evaluate(() => {
  const cards = [...document.querySelectorAll('#picker-blocks .bcard')];
  const bad = [];
  if (cards.length !== 10) bad.push('карточек ' + cards.length);
  cards.forEach(c => {
    const nm = (c.querySelector('.bcard-name') || {}).textContent || '';
    if (!c.querySelector('.bcard-spec svg')) bad.push('без картинки: ' + nm.trim());
    if (/^\s*\d+\s*·/.test(nm)) bad.push('номер в «' + nm.trim() + '»');
  });
  if (document.querySelectorAll('#scene-picker .picker-group.open').length) bad.push('блок уже раскрыт');
  if (document.getElementById('picker-back').classList.contains('shown')) bad.push('кнопка возврата видна');
  return !bad.length || bad.join('; ');
}));

await t('щелчок по блоку показывает его модели и возврат', () => page.evaluate(() => {
  const card = document.querySelectorAll('#picker-blocks .bcard')[1];
  card.click();
  const open = document.querySelectorAll('#scene-picker .picker-group.open');
  const hidden = document.getElementById('picker-blocks').classList.contains('hidden');
  const back = document.getElementById('picker-back');
  const shown = back.classList.contains('shown');
  const models = open.length ? open[0].querySelectorAll('.scard').length : 0;
  back.click();                                   // и возврат работает
  const restored = !document.getElementById('picker-blocks').classList.contains('hidden')
                && !document.querySelectorAll('#scene-picker .picker-group.open').length;
  return (open.length === 1 && hidden && shown && models > 0 && restored)
    || `открыто ${open.length}, блоки скрыты ${hidden}, возврат ${shown}, моделей ${models}, вернулись ${restored}`;
}));

await t('модель «Потребление в комплектах» вырезана', () => page.evaluate(() =>
  (!document.querySelector('.scard[data-scene="bundles"]') && typeof SCENE_ROUTE.bundles === 'undefined')
  || 'карточка ещё на месте'));

await t('модели КТВ переименованы', () => page.evaluate(() =>
  (SCENE_NAMES.trade === 'КТВ. Одна страна' && SCENE_NAMES.tradeprice === 'КТВ. Две страны-партнёра')
  || (SCENE_NAMES.trade + ' / ' + SCENE_NAMES.tradeprice)));

await t('свободного холста больше нет', () => page.evaluate(() =>
  (!document.querySelector('.scard[data-scene="free"]') && typeof SCENE_ROUTE.free === 'undefined')
  || 'холст ещё на месте'));

// Было 19; «Построение графиков» стало рабочей сценой, «Оси наоборот» удалены,
// «Потребление в комплектах» вырезано по П3 — функционал переехал в кривую комплектов.
await t('карточек «скоро» ровно 17', async () =>
  (await page.locator('.scard.soon').count()) === 17 || 'их ' + (await page.locator('.scard.soon').count()));

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
  ['m-graph',     s => s.mode === 'graph',                                       []],
  ['m-tangent',   s => s.mode === 'math'  && s.mathSub === 'tangent',            ['math-seg']],
  ['m-optimum',   s => s.mode === 'math'  && s.mathSub === 'optimum',            ['math-seg']],
  ['m-transform', s => s.mode === 'math'  && s.mathSub === 'transform',          ['math-seg']],
  ['m-minmax',    s => s.mode === 'math'  && s.mathSub === 'minmax',             ['math-seg']],
  ['m-constraint',s => s.mode === 'math'  && s.mathSub === 'constraint',         ['math-seg']],
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
];

for (const [key, want, lock] of CARDS) {
  await t(`карточка ${key}`, async () => {
    await page.evaluate(() => openPicker());
    await page.waitForTimeout(60);
    await openGroups();
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
    await openGroups();
    await page.click('.scard[data-scene="mono"]');
    await page.waitForTimeout(300);
    await page.evaluate(() => openPicker());
    await openGroups();
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

/* --- 3. Сцена без запретов ничего не прячет --------------------------- */
await t('сцена без запретов ничего не прячет', async () => {
  await page.evaluate(() => openPicker());
  await openGroups();
  await openGroups();
  await page.click('.scard[data-scene="ineq"]');
  await page.waitForTimeout(250);
  const n = await page.evaluate(() => document.querySelectorAll('.scoped-off').length);
  return n === 0 || (n + ' элементов остались спрятанными');
});

/* --- 4. Заголовок сцены совпадает с именем карточки ------------------- */
await t('заголовок сцены берётся из карточки', async () => {
  await page.evaluate(() => openPicker());
  await openGroups();
  await page.click('.scard[data-scene="mono-nat"]');
  await page.waitForTimeout(200);
  const txt = (await page.locator('#scene-name').textContent()).trim();
  return txt === 'Естественная монополия' || txt;
});

/* --- 5. Пульт узнаёт базовую сцену ------------------------------------ */
await t('baseScene сводит подрежим к базе', () => page.evaluate(() =>
  (baseScene('mono-nat') === 'mono' && baseScene('labor-bilat') === 'labor'
   && baseScene('tax-adv') === 'tax' && baseScene('sd') === 'sd') || 'baseScene врёт'));

/* --- 6. Ночная сессия «левая панель» (22.08) --------------------------
   Макет панели утверждён владельцем: во ВСЕХ 41 сцене ровно три карточки в
   одном порядке, убранные блоки не всплывают нигде, дорожки ползунков стоят
   вровень. Всё три — сквозные правила, поэтому проверяются перебором сцен, а
   не на одной удобной. */

const WANT_CARDS = ['sec-input', 'sec-view', 'sec-areascalc'];
const FORBIDDEN_HEADS = ['Что изучаем', 'Структура рынка', 'Излишки'];

const panelSweep = await page.evaluate(async (FORB) => {
  const w = ms => new Promise(r => setTimeout(r, ms));
  const rows = [];
  for (const k of Object.keys(SCENE_ROUTE)) {
    resetSceneMemory(); pickScene(k); await w(180);
    const cards = [...document.querySelectorAll('#tools-panel .tools-body > .section')]
      .filter(s => s.style.display !== 'none' && s.offsetParent !== null)
      .map(s => {
        const btn = s.querySelector(':scope > .fold-btn');
        const body = s.querySelector(':scope > .fold-body');
        return { id: s.id,
                 name: btn ? btn.querySelector('span > b').textContent.trim() : '',
                 open: btn ? btn.getAttribute('aria-expanded') === 'true' : null,
                 controls: body ? [...body.querySelectorAll('input,select,button,textarea')]
                                    .filter(e => e.offsetParent !== null).length : 0 };
      });
    const visText = [...document.getElementById('tools-panel').querySelectorAll('*')]
      .filter(e => e.offsetParent !== null && !e.children.length)
      .map(e => (e.textContent || '').trim()).join(' | ');
    rows.push({ key: k, cards, seen: FORB.filter(t => visText.indexOf(t) >= 0) });
  }
  return rows;
}, FORBIDDEN_HEADS);

// (г) Ровно три карточки в заданном порядке, первая раскрыта, две свёрнуты.
await t('(г) в каждой из 41 сцены три карточки панели в одном порядке', async () => {
  const bad = panelSweep.filter(r =>
    r.cards.map(c => c.id).join() !== WANT_CARDS.join()
    || !(r.cards[0].open === true && r.cards[1].open === false && r.cards[2].open === false)
    || r.cards[0].name !== 'Ввод функций'
    || r.cards[0].controls === 0);
  if (panelSweep.length !== 41) return `сцен ${panelSweep.length}, а не 41`;
  return bad.length === 0
    || bad.map(r => r.key + ' [' + r.cards.map(c => c.id + (c.open ? '+' : '-')).join(' ') + ']').join('; ');
});

// (д) Убранные блоки не показываются НИ В ОДНОЙ сцене.
await t('(д) «Что изучаем», «Структура рынка» и «Излишки» в панели не встречаются', async () => {
  const bad = panelSweep.filter(r => r.seen.length);
  const gone = await page.evaluate(() => ['sec-analysis', 'sec-areas', 'scn-none', 'scn-shift']
    .filter(id => document.getElementById(id)));
  if (gone.length) return 'в разметке остались: ' + gone.join(', ');
  return bad.length === 0 || bad.map(r => r.key + ' ' + JSON.stringify(r.seen)).join('; ');
});

// (ж) Левый край дорожек всех ползунков панели совпадает до пикселя.
await t('(ж) левый край дорожек всех ползунков панели совпадает', async () => {
  const r = await page.evaluate(async () => {
    const w = ms => new Promise(res => setTimeout(res, ms));
    /* «Пол и потолок цены» плюс буква из формулы: в панели разом стоят сдвиги
       кривых (границы «−50»), регулируемая цена («0» и «100») и буква
       («−10» и «10») — разрядность разная, ради этого случая и правилось. */
    resetSceneMemory(); pickScene('ceil'); await w(400);
    const inp = document.querySelector('#curve-list .curve-expr-inp');
    inp.value = '100 - a*Q'; inp.dispatchEvent(new Event('input', { bubbles: true }));
    await w(600); redrawAll(); await w(400);
    const tracks = [...document.querySelectorAll('#params-panel .param-track')]
      .filter(el => el.offsetParent !== null && el.getBoundingClientRect().width > 0);
    return tracks.map(el => {
      const s = el.querySelector('input[type=range]');
      return { left: Math.round(s.getBoundingClientRect().left * 100) / 100,
               bound: (el.querySelector('.param-bound') || {}).textContent };
    });
  });
  if (r.length < 3) return 'дорожек всего ' + r.length + ' — проба ничего не проверила';
  const uniq = [...new Set(r.map(x => x.left))];
  return uniq.length === 1
    || `дорожек ${r.length}, разных координат ${uniq.length}: ${uniq.join(', ')}`
       + ` | границы: ${r.map(x => x.bound).join(', ')}`;
});

/* --- Итог ------------------------------------------------------------- */
for (const [st, name, info] of checks) console.log(`${st === 'OK' ? '✓' : '✗'} ${name}${info ? ' — ' + info : ''}`);
const bad = checks.filter(c => c[0] !== 'OK').length;
if (errors.length) { console.log('\nОшибки страницы:'); errors.forEach(e => console.log('  ' + e)); }
console.log(`\n=== скелет блоков: ${checks.length - bad} прошло, ${bad} провалено; ошибок страницы ${errors.length} ===`);
await browser.close();
process.exit(bad || errors.length ? 1 : 0);
