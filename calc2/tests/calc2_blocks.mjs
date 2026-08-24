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
// Стало 16: «Квоты» доведены до рабочего сюжета (ночная сессия «вмешательство»).
// Стало 15: «Сложение спросов и предложений» доведено до рабочего сюжета
// (ночная сессия 24.08, Блок II).
await t('карточек «скоро» ровно 15', async () =>
  (await page.locator('.scard.soon').count()) === 15 || 'их ' + (await page.locator('.scard.soon').count()));

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
  ['sd',          s => s.mode === 'market' && s.market === 'comp',               ['sec-tax']],
  ['taxes',       s => s.taxKind === 'unit' && s.intervType === 'tax',           ['seg-ceil', 'seg-floor']],
  ['quota',       s => s.intervType === 'quota' && s.quota === 40,               ['seg-tax', 'seg-sub']],
  ['ceil',        s => s.intervType === 'ceiling',                                     ['taxside-row']],
  ['elast',       s => s.scenario === 'elasticity',                              ['sec-tax']],
  ['ext',         s => s.scenario === 'externality',                             ['sec-tax']],
  ['costs',       s => s.mode === 'costs' && s.costsSub === 'costs',             ['costs-seg']],
  ['prod',        s => s.mode === 'costs' && s.costsSub === 'production',        ['costs-seg']],
  ['plants',      s => s.mode === 'costs' && s.costsSub === 'plants',            ['costs-seg']],
  ['isoquant',    s => s.mode === 'costs' && s.costsSub === 'isoquant',          ['costs-seg']],
  ['mono',        s => s.market === 'monopoly' && s.monoMode === 'simple',       ['mono-submode']],
  ['mono-nat',    s => s.market === 'monopoly' && s.monoMode === 'natural',      ['mono-submode']],
  ['mono-d1',     s => s.market === 'monopoly' && s.monoMode === 'discr1',       ['mono-submode']],
  ['mono-d3',     s => s.market === 'monopoly' && s.monoMode === 'discr3',       ['mono-submode']],
  ['mono-kink',   s => s.market === 'monopoly' && s.monoMode === 'kinked',       ['mono-submode']],
  ['labor',       s => s.mode === 'labor' && s.laborStruct === 'competition',    ['labor-seg']],
  ['labor-mono',  s => s.mode === 'labor' && s.laborStruct === 'monopsony',      ['labor-seg']],
  ['labor-union', s => s.mode === 'labor' && s.laborStruct === 'union',          ['labor-seg']],
  ['labor-bilat', s => s.mode === 'labor' && s.laborStruct === 'bilateral',      ['labor-seg']],
  ['smallopen',   s => s.scenario === 'openecon',                                []],
  ['monoexport',  s => s.market === 'monopoly' && s.monoMode === 'discr3',       ['mono-submode']],
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
      taxKind: STATE.taxKind, consSlutskyOn: STATE.consSlutskyOn, quota: STATE.quota,
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

/* --- 2в. Старые ключи налоговых сцен остались синонимами --------------
   Карточек «Потоварные налоги» и «Процентные налоги» на главном экране
   больше нет — их заменила одна «Налоги и субсидии». Но ключи 'tax' и
   'tax-adv' обязаны и дальше открывать ту же сцену: на них ссылаются код
   и прежние проверки. Поэтому здесь не клик по карточке, а pickScene. */
await t('ключи tax и tax-adv открывают ту же сцену', () => page.evaluate(() => {
  resetSceneMemory(); pickScene('tax');
  if (STATE.intervType !== 'tax' || STATE.taxKind !== 'unit' || STATE.tax !== 20) return 'tax: ' + JSON.stringify({ t: STATE.intervType, k: STATE.taxKind, v: STATE.tax });
  resetSceneMemory(); pickScene('tax-adv');
  if (STATE.taxKind !== 'advalorem' || STATE.taxForm !== 'vat') return 'tax-adv: ' + JSON.stringify({ k: STATE.taxKind, f: STATE.taxForm });
  return true;
}));

/* --- 5. Пульт узнаёт базовую сцену ------------------------------------ */
await t('baseScene сводит подрежим к базе', () => page.evaluate(() =>
  (baseScene('mono-nat') === 'mono' && baseScene('labor-bilat') === 'labor'
   && baseScene('tax-adv') === 'tax' && baseScene('sd') === 'sd') || 'baseScene врёт'));

/* --- 6. Ночная сессия «левая панель» (22.08) --------------------------
   Макет панели утверждён владельцем: во ВСЕХ сценах ровно три карточки в
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
    /* ⚠️ ВИДИМЫЙ ТЕКСТ СОБИРАЕМ ПО СВОИМ УЗЛАМ, А НЕ ПО «ЛИСТЬЯМ».
       Прежний фильтр брал только элементы без детей — и пропускал ровно тот
       случай, ради которого проверка написана: у подзаголовка «Структура
       рынка» внутри стоит кнопка-вопросик, значит ребёнок у него есть, и
       заголовок в замер не попадал. Проверено поломкой: снял запреты карточек,
       «Структура рынка» стала видна на экране, а проверка осталась зелёной. */
    const visText = [...document.getElementById('tools-panel').querySelectorAll('*')]
      .filter(e => e.offsetParent !== null)
      .map(e => [...e.childNodes].filter(n => n.nodeType === 3)
                                 .map(n => n.nodeValue).join('').trim())
      .filter(Boolean).join(' | ');
    rows.push({ key: k, cards, seen: FORB.filter(t => visText.indexOf(t) >= 0) });
  }
  return rows;
}, FORBIDDEN_HEADS);

// (г) Ровно три карточки в заданном порядке, первая раскрыта, две свёрнуты.
await t('(г) в каждой из 44 сцен три карточки панели в одном порядке', async () => {
  const bad = panelSweep.filter(r =>
    r.cards.map(c => c.id).join() !== WANT_CARDS.join()
    || !(r.cards[0].open === true && r.cards[1].open === false && r.cards[2].open === false)
    || r.cards[0].name !== 'Ввод функций'
    || r.cards[0].controls === 0);
  // 44 маршрута: 41 прежняя сцена, ключ 'taxes' (объединённый сюжет налогов,
  // рядом с которым 'tax' и 'tax-adv' оставлены синонимами), 'quota' и
  // 'sdsum' — сложение спросов и предложений (ночная сессия 24.08).
  if (panelSweep.length !== 44) return `сцен ${panelSweep.length}, а не 44`;
  return bad.length === 0
    || bad.map(r => r.key + ' [' + r.cards.map(c => c.id + (c.open ? '+' : '-')).join(' ') + ']').join('; ');
});

// (д) Убранные блоки не показываются НИ В ОДНОЙ сцене.
await t('(д) «Что изучаем», «Структура рынка» и «Излишки» в панели не встречаются', async () => {
  const bad = panelSweep.filter(r => r.seen.length);
  /* Удалённое обязано ОТСУТСТВОВАТЬ в разметке, а не быть спрятанным: спрятанное
     возвращается одной строчкой стиля, удалённого возвращать нечем.
     Сюда же переехали переключатель структуры рынка и панель сюжета «Сдвиги» —
     оба удалены 24.08 после замера по всем 44 сценам. */
  const gone = await page.evaluate(() => ['sec-analysis', 'sec-areas', 'scn-none', 'scn-shift',
    'market-struct-row', 'seg-comp', 'seg-mono', 'scn-pane-shift', 'info-shift',
    'shiftD-slider', 'shiftS-slider']
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

/* ═══ ПРОВЕРКИ ЗАКРЫВАЮЩЕЙ НОЧНОЙ СЕССИИ (24.08) ══════════════════════════
   По каждой временно возвращался дефект, и по каждой записан текст провала —
   иначе проверка «зелёная всегда» ничем не отличается от отсутствующей.     */

// (б) Подсказка: наведение показывает, уход прячет, клавиатура тоже
//     показывает, и формула внутри набрана математикой.
await t('(б) подсказка живёт по наведению, доступна с клавиатуры и несёт формулу', async () => {
  await page.evaluate(() => { resetSceneMemory(); pickScene('mono'); });
  await page.waitForTimeout(500);
  await page.evaluate(() => {
    setToolsOpen(true);
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(b => {
      const bd = document.getElementById(b.getAttribute('aria-controls'));
      if (bd) { bd.classList.add('open'); b.setAttribute('aria-expanded', 'true'); }
    });
  });
  await page.waitForTimeout(400);
  // Ищем видимую подсказку, в которой ЕСТЬ математика (доллары).
  const found = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('[data-tip*="$"]'))
      .find(e => e.getBoundingClientRect().width > 1);
    if (!el) return null;
    el.setAttribute('data-probe-tip', '1');
    return el.getAttribute('data-tip');
  });
  if (!found) return 'ни одной видимой подсказки с формулой не нашлось';
  const h = await page.$('[data-probe-tip]');
  await h.hover();
  await page.waitForTimeout(250);
  const shown = await page.evaluate(() => {
    const t = document.getElementById('hint-tip');
    if (!t) return { нет: true };
    return { display: getComputedStyle(t).display, формул: t.querySelectorAll('.katex').length };
  });
  if (shown.нет) return 'узла #hint-tip нет вовсе';
  if (shown.display === 'none') return 'наведение подсказку не показало';
  if (!shown.формул) return `подсказка «${found}» показана, но формула НЕ набрана (узлов KaTeX 0)`;
  // Уход мыши гасит.
  await page.mouse.move(2, 2);
  await page.waitForTimeout(250);
  const gone = await page.evaluate(() =>
    getComputedStyle(document.getElementById('hint-tip')).display);
  if (gone !== 'none') return 'мышь ушла, а подсказка осталась на экране';
  // Клавиатура: флаг «работают с клавиатуры» поднимает Tab, потом фокус.
  await page.keyboard.press('Tab');
  await page.evaluate(() => { document.querySelector('[data-probe-tip]').focus(); });
  await page.waitForTimeout(250);
  const kb = await page.evaluate(() =>
    getComputedStyle(document.getElementById('hint-tip')).display);
  if (kb === 'none') return 'фокус с клавиатуры подсказку не показал';
  return true;
});

// (в) Подсказка не вылезает за край экрана 380 px — ни одна.
await t('(в) на экране 380 px ни одна подсказка не уходит за край', async () => {
  await page.setViewportSize({ width: 380, height: 780 });
  await page.evaluate(() => {
    resetSceneMemory(); pickScene('mono'); setToolsOpen(true);
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(b => {
      const bd = document.getElementById(b.getAttribute('aria-controls'));
      if (bd) { bd.classList.add('open'); b.setAttribute('aria-expanded', 'true'); }
    });
  });
  await page.waitForTimeout(700);
  const n = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tip]'))
    .filter(e => e.getBoundingClientRect().width > 1 && (e.getAttribute('data-tip') || '').length > 3)
    .map((e, i) => { e.setAttribute('data-probe-n', 'n' + i); return i; }).length);
  const out = [];
  for (let i = 0; i < Math.min(n, 12); i++) {
    const h = await page.$(`[data-probe-n="n${i}"]`);
    if (!h) continue;
    try { await h.hover({ timeout: 2500 }); } catch (e) { continue; }
    await page.waitForTimeout(140);
    const r = await page.evaluate(() => {
      const t = document.getElementById('hint-tip');
      if (!t || getComputedStyle(t).display === 'none') return null;
      const b = t.getBoundingClientRect();
      return { l: b.left, r: b.right, t: b.top, b: b.bottom, txt: (t.textContent || '').slice(0, 24) };
    });
    if (r && (r.l < -0.5 || r.t < -0.5 || r.r > 380.5 || r.b > 780.5)) out.push(r);
  }
  await page.setViewportSize({ width: 1400, height: 950 });
  await page.waitForTimeout(300);
  if (!n) return 'подсказок на узком экране не нашлось — проба ничего не проверила';
  return out.length === 0
    || `вылезло ${out.length}: ` + out.map(x => `«${x.txt}» ${Math.round(x.l)}…${Math.round(x.r)}`).join('; ');
});

// (г) Пять подписей Фазы 2 набраны ОБЩИМ путём: у каждой подписи, чьё
//     основание — обозначение, стоит пометка правила.
await t('(г) обозначения на холсте набраны математикой во всех сценах-виновницах', async () => {
  const bad = [];
  for (const key of ['tax', 'taxes', 'tax-adv', 'mono-nat', 'plants']) {
    await page.evaluate(k => { resetSceneMemory(); pickScene(k); }, key);
    await page.waitForTimeout(650);
    /* ⚠️ ПРОВЕРКА СУДИТ САМА, А НЕ СПРАШИВАЕТ ПРОВЕРЯЕМЫЙ КОД.
       Первая версия звала chartLabelKind(chartLabelSource(el)) — то есть обе
       стороны сравнения шли из одной функции, и порча этой функции проверку не
       роняла (проверено: сломал — осталась зелёной). Теперь ожидание считается
       здесь, своим списком и своим разбором. */
    const miss = await page.evaluate(() => {
      const WORDS = ['MC','MR','TC','ATC','AVC','AFC','FC','VC','TR','TP','MP','AP','MPL','MRP',
        'Qd','Qs','Pd','Ps','Pb','Pw','Pc','Pf','CS','PS','DWL','AD','AS','SRAS','LRAS',
        'IS','LM','GDP','MSB','MSC','SW','Wmin','Qm','Pm','Qc','Px','Py'];
      const out = [];
      document.querySelectorAll('#chart text').forEach(el => {
        // Исходная запись подписи, а не склейка нарисованных tspan'ов.
        const raw = (el.dataset && el.dataset.raw) ? el.dataset.raw
          : (el.textContent || '').replace(/\u200b/g, '');
        const base = String(raw)
          .replace(/[_^](\{[^}]*\}|.)/g, '')
          .replace(/[\u2080-\u2089\u00b9\u00b2\u00b3]/g, '')
          .replace(/[*\u2217\u2032']/g, '')
          .trim();
        const isNotation = WORDS.indexOf(base) >= 0 || /^[A-Za-z]$/.test(base);
        if (!isNotation) return;
        /* ⚠️ ПОМЕТКА ТРЕБУЕТСЯ У САМОЙ ПОДПИСИ, А НЕ У ЕЁ КУСКА.
           Вторая версия проверки прощала подпись, если помечен хоть один
           tspan внутри — и «E_{ATC}» проходила за счёт помеченного индекса,
           пока само «E» стояло системным шрифтом. Проверено: с этой поблажкой
           порча chartLabelSource проверку не роняла. Основание — обозначение,
           значит начертание обязано стоять на узле подписи. */
        if (el.dataset.mathset) return;
        out.push(raw + ' (основание «' + base + '»)');
      });
      return out;
    });
    miss.forEach(m => bad.push(key + ': «' + m + '»'));
  }
  return bad.length === 0 || 'не набрано: ' + bad.join(', ');
});

// (д) После захода во «Внешние эффекты» и выхода чужие поля не видны, а свои
//     при возврате на месте.
await t('(д) блок MSB/MSC не протекает в чужие сцены и возвращается в свою', async () => {
  const vis = () => page.evaluate(() => {
    const e = document.getElementById('social-curves');
    if (!e) return 'нет узла';
    return e.offsetParent === null ? 'скрыт' : 'виден';
  });
  const go = async (k) => { await page.evaluate(x => { pickScene(x); }, k); await page.waitForTimeout(600); };
  await go('ext');
  if (await vis() !== 'виден') return 'во «Внешних эффектах» свой же блок не виден';
  await go('mono');
  const inMono = await vis();
  await go('labor');
  const inLabor = await vis();
  await go('ext');
  const back = await vis();
  if (inMono !== 'скрыт') return 'в монополии блок MSB/MSC ' + inMono + ' — протечка';
  if (inLabor !== 'скрыт') return 'на рынке труда блок MSB/MSC ' + inLabor + ' — протечка';
  if (back !== 'виден') return 'при возврате во «Внешние эффекты» свой блок пропал';
  return true;
});

// (е) Сюжет «Сдвиги» недостижим, и его кода в странице нет.
await t('(е) сюжета shift нет ни в разметке, ни в коде страницы', async () => {
  const live = await page.evaluate(() => {
    const fns = ['drawShiftScenario', 'updateShiftPanel', 'setShift', 'shiftMark']
      .filter(n => typeof window[n] === 'function' || eval('typeof ' + n) === 'function');
    const st = ['shiftD', 'shiftS', 'shiftActive', 'shiftRes'].filter(k => k in STATE);
    const ids = ['scn-shift', 'scn-pane-shift', 'info-shift', 'shiftD-slider', 'shiftS-slider']
      .filter(id => document.getElementById(id));
    return { fns, st, ids };
  });
  if (live.fns.length) return 'функции живы: ' + live.fns.join(', ');
  if (live.st.length) return 'поля состояния живы: ' + live.st.join(', ');
  if (live.ids.length) return 'узлы разметки живы: ' + live.ids.join(', ');
  return true;
});

// (ж) Математических обозначений, набранных ОБЫЧНЫМ текстом, не осталось.
//     Тот же разбор, что у прибора night2_font_audit.mjs; порог — ноль,
//     потому что ноль и достигнут. Вырастет — проверка покраснеет.
await t('(ж) обозначений обычным шрифтом на экране нет ни в одной сцене', async () => {
  const SWEEP = () => {
    const WORDS = ['MC','MR','TC','ATC','AVC','AFC','FC','VC','TR','TP','MP','AP','MPL','MRP',
      'Qd','Qs','Pd','Ps','Pb','Pw','Pc','Pf','CS','PS','DWL','AD','AS','SRAS','LRAS',
      'IS','LM','GDP','MSB','MSC','SW','Wmin','Qm','Pm','Qc','Px','Py'];
    const LETTERS = ['P','Q','D','S','L','K','X','Y','W','U','M','E'];
    const re = new RegExp('(?:^|[^A-Za-zА-Яа-я0-9_])(' + WORDS.join('|') + '|'
      + LETTERS.map(l => l + '(?:\\*|\\d|_\\w)?').join('|') + ')(?![A-Za-zА-Яа-я0-9_])', 'g');
    const hits = [];
    const scan = (text, where) => {
      const t = String(text || '').replace(/\$[^$]*\$/g, ' ').replace(/\s+/g, ' ').trim();
      if (!t) return;
      re.lastIndex = 0; let m;
      while ((m = re.exec(t))) hits.push(where + ' «' + t.slice(0, 40) + '» → ' + m[1]);
    };
    ['#tools-panel', '#params-panel', '#chart'].forEach(sel => {
      const root = document.querySelector(sel);
      if (!root) return;
      const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        const el = n.parentElement;
        if (!el) continue;
        /* `code` пропускаем намеренно: там показана ЗАПИСЬ на языке движка
           («min[Q₁+Q₂=Q]»), и набирать её математическим шрифтом значило бы
           соврать — эту строку набирают в поле руками. Список пропусков тот
           же, что у markNotationsIn: два разных списка разошлись бы. */
        if (el.closest('.katex, math-field, script, code, textarea, input, [data-mathset]')) continue;
        if (String(el.nodeName).toLowerCase() === 'title') continue;
        if (sel !== '#chart' && el.offsetParent === null) continue;
        scan(n.nodeValue, sel);
      }
      root.querySelectorAll('[data-tip], [title]').forEach(e =>
        scan(e.getAttribute('data-tip') || e.getAttribute('title'), sel + '[подсказка]'));
    });
    return hits;
  };
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  const all = [];
  for (const k of scenes) {
    await page.evaluate(x => {
      resetSceneMemory(); pickScene(x); setToolsOpen(true); setParamsOpen(true);
      document.querySelectorAll('.fold-btn[aria-controls]').forEach(b => {
        const bd = document.getElementById(b.getAttribute('aria-controls'));
        if (bd) { bd.classList.add('open'); b.setAttribute('aria-expanded', 'true'); }
      });
    }, k);
    await page.waitForTimeout(340);
    (await page.evaluate(SWEEP)).forEach(h => all.push(k + ' · ' + h));
  }
  if (scenes.length !== 44) return `сцен ${scenes.length}, а не 44 — проба обошла не всё`;
  /* ХРАПОВИК, а не голый ноль. Числа замера 24.08 (см. отчёт сессии):
     1011 → 427 (после починки самого прибора, который обрывал обход) → 1.
     Осталось одно место: «W_s» в подсказке монопсонии — обозначение написано
     через подчёркивание, и разбор его намеренно не берёт (подчёркивание может
     быть частью имени). Потолок держит долг на виду: вырос — красное, упал —
     тоже красное, потому что потолок забыли опустить. */
  const CEILING = 1;
  if (all.length > CEILING)
    return `случаев ${all.length}, потолок ${CEILING} — долг ВЫРОС на ${all.length - CEILING}: `
           + all.slice(0, 5).join(' | ');
  if (all.length < CEILING)
    return `случаев ${all.length}, потолок ${CEILING} — стало ЛУЧШЕ, опусти CEILING до ${all.length}`;
  return true;
});

/* --- Итог ------------------------------------------------------------- */
for (const [st, name, info] of checks) console.log(`${st === 'OK' ? '✓' : '✗'} ${name}${info ? ' — ' + info : ''}`);
const bad = checks.filter(c => c[0] !== 'OK').length;
if (errors.length) { console.log('\nОшибки страницы:'); errors.forEach(e => console.log('  ' + e)); }
console.log(`\n=== скелет блоков: ${checks.length - bad} прошло, ${bad} провалено; ошибок страницы ${errors.length} ===`);
await browser.close();
process.exit(bad || errors.length ? 1 : 0);
