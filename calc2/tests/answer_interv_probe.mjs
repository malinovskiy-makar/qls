/* «ОТВЕТ» ПРИ ВМЕШАТЕЛЬСТВЕ: ГЛАВНЫЕ ЧИСЛА — ИТОГ ВКЛЮЧЁННОГО ВМЕШАТЕЛЬСТВА
   (сессия А2 24.10, карточки Notion …81e2…, …81cc…; ADR 0158).

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/answer_interv_probe.mjs

   Стережёт ПРАВИЛА:
     А — главные строки «Ответа» берутся по СОСТОЯНИЮ: включённое и связывающее вмешательство ставит наверх свою
         группу («После тарифа», «При квоте», «С МРОТ», «После налога», «После субсидии», «При потолке цены»,
         «Рынок при поле цены»), «было» — изменением «70 − 10» под значением; без вмешательства — как прежде;
     Б — блок «Излишки» подписан состоянием («Излишки при автаркии», «… при свободной торговле», «… после тарифа»),
         излишки после вмешательства видны;
     В — «Внешние эффекты»: на рынке CS, PS, внешние издержки (выгоды) и SW С НИМИ, в оптимуме внешние издержки и SW;
     Г — квота: цена по умолчанию — цена спроса, в «Ответе» 60;
     Д — безразличие монополиста: потери общества у обоих вариантов.
   Каждая модель открывается программно (resetSceneMemory + pickScene), «Ответ» открыт (answer_open.mjs) — без
   этого прибор на закрытой колонке зеленел бы вхолостую.

   ⚠️ Расходится число — сломан движок, а не прибор. */
import { chromium } from 'playwright';
import { keepAnswerOpen, answerShown } from './answer_open.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = keepAnswerOpen(await chromium.launch());
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 }, reducedMotion: 'reduce', locale: 'ru-RU' })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0, total = 0;
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length)));
function ok(label, cond, got) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (cond ? '' : '  -> ' + JSON.stringify(got)));
}
ok('предусловие: «Ответ» открыт (#params-panel > .side-inner видна)', await answerShown(page));

const MKT = `
  var setDS = function (scene, d, s) {
    resetSceneMemory(); pickScene(scene); closePicker();
    if (d) updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), d);
    var low = STATE.curves.find(function (c) { return c.role === 'supply' || c.role === 'mc'; });
    if (low && s) updateCurveExpr(low, s);
    redrawAll();
  };`;
/* Снимок «Ответа»: группы (заголовок, строки «подпись · обозначение · значение · было»), статус, видимые блоки
   табло с заголовком (у блоков без своего заголовка — ::before). */
async function answer(code) {
  await page.evaluate((c) => { (new Function(c))(); }, MKT + code);
  await page.waitForTimeout(500);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  return page.evaluate(() => {
    const t = (el) => { if (!el) return ''; const c = el.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ' ').trim(); };
    const shown = (el) => { for (let n = el; n && n.id !== 'params-panel'; n = n.parentElement) { if (n.hidden) return false; const cs = getComputedStyle(n); if (cs.display === 'none' || cs.visibility === 'hidden') return false; } return true; };
    const groups = [...document.querySelectorAll('#ans-hero > .ans-group')].map(g => ({
      head: t(g.querySelector('.ans-ghead')),
      cells: [...g.querySelectorAll('.ans-cell')].map(c => ({ lab: t(c.querySelector('.ans-lab')), not: t(c.querySelector('.ans-not')),
        val: t(c.querySelector('.ans-val')), was: t(c.querySelector('.ans-was')) })),
    }));
    const blocks = [...document.querySelectorAll('#sb-body > [id]')].filter(shown).map(b => ({ id: b.id,
      title: t(b.querySelector(':scope > .section-title')) || getComputedStyle(b, '::before').content.replace(/^"|"$/g, '') }));
    const status = [...document.querySelectorAll('#ans-status .ans-status')].map(t);
    return { groups, blocks, status };
  });
}
const norm = (s) => String(s == null ? '' : s).replace(/[\s   ]+/g, '');
/* Значение: число — с допуском 0,011 (84,375 печатается то 84,37, то 84,38 — шум интеграла; запись чисел — сессия
   «Числа»), иначе — текст без пробелов. */
const numOf = (s) => { const x = norm(s).replace(/−/g, '-').replace(',', '.'); return /^-?\d+(\.\d+)?$/.test(x) ? parseFloat(x) : NaN; };
const same = (a, b) => (isFinite(numOf(a)) && isFinite(numOf(b))) ? Math.abs(numOf(a) - numOf(b)) <= 0.011 : norm(a) === norm(b);
/* Ожидание группы: [заголовок, [[подпись-регэксп, значение, было?], …]] — строки по порядку, «было» — если задано. */
function checkGroup(tag, a, gi, want) {
  const g = a.groups[gi];
  ok(tag + ': группа ' + (gi + 1) + ' «' + want[0] + '»', !!g && g.head === want[0], g ? g.head : a.groups.map(x => x.head));
  if (!g) return;
  want[1].forEach(([re, v, was], i) => {
    const c = g.cells[i];
    ok(tag + ': «' + want[0] + '», строка ' + (i + 1) + ' ' + re + ' = ' + v + (was != null ? ' (' + was + ')' : ''),
      !!c && re.test(c.lab + ' ' + c.not) && same(c.val, v) && (was == null || norm(c.was) === norm(was)), c);
  });
  ok(tag + ': «' + want[0] + '» — строк ' + want[1].length, g.cells.length === want[1].length, g.cells.map(c => c.lab + ' = ' + c.val));
}
const shortOf = (a) => a.groups.map(g => '[' + g.head + '] ' + g.cells.map(c => c.lab + (c.not ? ' ' + c.not : '') + ' = ' + c.val + (c.was ? ' (' + c.was + ')' : '')).join('; ')).join(' | ');

/* ── А, Б: малая открытая экономика ── */
head('А, Б. «Малая открытая экономика»: D = 100 − Q, S = Q, Pw = 30');
let a = await answer(`setDS('smallopen');`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('без вмешательства', a, 0, ['Свободная торговля', [[/^Величина спроса Qd$/, '70'], [/^Величина предложения Qs$/, '30'], [/^Импорт/, '40']]]);
checkGroup('без вмешательства', a, 1, ['Излишки при свободной торговле', [[/CS$/, '2 450'], [/PS$/, '450']]]);
ok('без вмешательства: блок «Излишки при автаркии»', a.blocks.some(b => b.id === 'info-areas' && b.title === 'Излишки при автаркии'), a.blocks);
a = await answer(`setDS('smallopen'); STATE.openTariff = 10; setOpenTool('tariff');`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('тариф 10', a, 0, ['После тарифа', [[/^Внутренняя цена/, '40'], [/^Величина спроса/, '60', '70 − 10'], [/^Величина предложения/, '40', '30 + 10'],
  [/^Импорт/, '20', '40 − 20'], [/^Доход бюджета/, '200'], [/^Потери общества DWL$/, '100', '50 + 50']]]);
checkGroup('тариф 10', a, 1, ['Излишки после тарифа', [[/CS$/, '1 800'], [/PS$/, '800']]]);
ok('тариф 10: блок автаркии подписан «Излишки при автаркии»', a.blocks.some(b => b.id === 'info-areas' && b.title === 'Излишки при автаркии'), a.blocks);
a = await answer(`setDS('smallopen'); STATE.openQuota = 20; setOpenTool('quota');`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('квота ввоза 20', a, 0, ['При квоте', [[/^Внутренняя цена/, '40'], [/^Величина спроса/, '60', '70 − 10'], [/^Величина предложения/, '40', '30 + 10'],
  [/^Импорт/, '20', '40 − 20'], [/^Рента от квоты/, '200'], [/^Потери общества DWL$/, '100', '50 + 50']]]);
checkGroup('квота ввоза 20', a, 1, ['Излишки при квоте', [[/CS$/, '1 800'], [/PS$/, '800']]]);

/* ── А: рынок труда с МРОТ ── */
head('А. Рынок труда, старт: D = 100 − L, S = 10 + 0,5L, МРОТ 45');
a = await answer(`resetSceneMemory(); pickScene('labor-mono'); closePicker(); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('монопсония', a, 0, ['С МРОТ', [[/^Занятость L$/, '55', '45 + 10'], [/^Зарплата W$/, '45', '32,5 + 12,5'], [/^Безработица/, '15'],
  [/^Потери общества DWL$/, '18,75', '168,75 − 150']]]);
a = await answer(`resetSceneMemory(); pickScene('labor-mono'); closePicker(); setLaborMinOn(false); redrawAll();`);
checkGroup('монопсония без МРОТ', a, 0, ['Рынок труда', [[/^Занятость/, '45'], [/^Зарплата/, '32,5'], [/DWL$/, '168,75']]]);
a = await answer(`resetSceneMemory(); pickScene('labor'); closePicker(); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('конкурентный рынок труда', a, 0, ['С МРОТ', [[/^Занятость L$/, '55', '60 − 5'], [/^Зарплата W$/, '45', '40 + 5'], [/^Безработица/, '15'],
  [/^Потери общества DWL$/, '18,75']]]);

/* ── А: монополия ── */
head('А. «Стандартная монополия»: D: Q = 120 − P, MC = 2Q + 30');
a = await answer(`setDS('mono', '120-P', '2*Q+30');`);
checkGroup('без вмешательства', a, 0, ['Монополия', [[/^Выпуск монополиста/, '22,5'], [/^Цена монополиста/, '97,5'], [/^Потери общества/, '84,37'], [/^Излишек потребителя/, '253,13']]]);
a = await answer(`setDS('mono', '120-P', '2*Q+30'); setType('tax'); setTax(45); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('налог 45', a, 0, ['После налога', [[/^Выпуск монополиста Qm$/, '11,25', '22,5 − 11,25'], [/^Цена монополиста Pm$/, '108,75', '97,5 + 11,25'],
  [/^Потери общества/, '527,34'], [/^Излишек потребителя/, '63,28']]]);
a = await answer(`setDS('mono', '120-P', '2*Q+30'); setType('subsidy'); setTax(30); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('субсидия 30', a, 0, ['После субсидии', [[/^Выпуск монополиста Qm$/, '30', '22,5 + 7,5'], [/^Цена монополиста Pm$/, '90', '97,5 − 7,5'],
  [/^Потери общества/, '0'], [/^Излишек потребителя/, '450']]]);
a = await answer(`setDS('mono', '120-P', '2*Q+30'); setType('ceiling'); setPReg(90); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('потолок 90', a, 0, ['При потолке цены', [[/^Выпуск Q$/, '30', '22,5 + 7,5'], [/^Цена P$/, '90', '97,5 − 7,5'], [/^Потери общества/, '0']]]);
a = await answer(`setDS('mono', '120-P', '2*Q+30'); setType('ceiling'); setPReg(110); redrawAll();`);
checkGroup('потолок 110 не связывает', a, 0, ['Монополия', [[/^Выпуск монополиста/, '22,5'], [/^Цена монополиста/, '97,5'], [/^Потери общества/, '84,38'], [/^Излишек потребителя/, '253,12']]]);

/* ── А: пол и потолок на конкурентном рынке ── */
head('А. «Пол и потолок цены»: D = 100 − Q, S = Q');
a = await answer(`setDS('ceil', '100-Q', 'Q'); setType('floor'); setPReg(70); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('пол 70', a, 0, ['Рынок при поле цены', [[/^Пол цены/, '70'], [/^Продаётся Q$/, '30'], [/^Избыток/, '40'], [/^Потери общества/, '400']]]);
a = await answer(`setDS('ceil', '100-Q', 'Q'); setType('ceiling'); setPReg(40); redrawAll();`);
checkGroup('потолок 40 — как прежде', a, 0, ['Рынок при потолке цены', [[/^Потолок цены/, '40'], [/^Величина предложения Qs$/, '40'], [/^Дефицит/, '20'], [/^Потери общества/, '100']]]);

/* ── В: внешние эффекты ── */
head('В. «Внешние эффекты»: D = 100 − Q, S = Q');
a = await answer(`resetSceneMemory(); pickScene('ext'); closePicker(); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('старт MSC = Q + 20', a, 0, ['Рынок', [[/^Количество/, '50'], [/^Цена/, '50'], [/^Излишек потребителя CS$/, '1 250'], [/^Излишек производителя PS$/, '1 250'],
  [/^Внешние издержки/, '1 000'], [/^Общественное благосостояние SW$/, '1 500']]]);
checkGroup('старт MSC = Q + 20', a, 1, ['Общественный оптимум', [[/^Оптимум/, 'Q = 40, P = 60'], [/^Внешние издержки/, '800'], [/^Общественное благосостояние SW$/, '1 600'],
  [/^Потери общества DWL$/, '100'], [/^Корректирующий налог/, '20']]]);
a = await answer(`resetSceneMemory(); pickScene('ext'); closePicker(); STATE.mscOn = false; STATE.mscExpr = ''; STATE.msbOn = true; STATE.msbExpr = '120 - Q';
  syncSocialFields(); recompileSocial(); redrawAll();`);
console.log('  ИНФО ' + shortOf(a));
checkGroup('MSB = 120 − Q', a, 0, ['Рынок', [[/^Количество/, '50'], [/^Цена/, '50'], [/CS$/, '1 250'], [/PS$/, '1 250'], [/^Внешние выгоды/, '1 000'], [/SW$/, '3 500']]]);
checkGroup('MSB = 120 − Q', a, 1, ['Общественный оптимум', [[/^Оптимум/, 'Q = 60, P = 60'], [/^Внешние выгоды/, '1 200'], [/SW$/, '3 600'],
  [/DWL$/, '100'], [/^Корректирующая субсидия/, '20']]]);
a = await answer(`resetSceneMemory(); pickScene('ext'); closePicker(); STATE.mscOn = false; syncSocialFields(); recompileSocial(); redrawAll();`);
ok('без внешнего эффекта: SW = CS + PS, как у всех рынков', a.groups.length && !a.groups.some(g => g.cells.some(c => /^Внешние/.test(c.lab))), shortOf(a));

/* ── Г: квота ── */
head('Г. «Квоты»: D = 100 − Q, S = Q, квота 40');
a = await answer(`resetSceneMemory(); pickScene('quota'); closePicker(); redrawAll();`);
checkGroup('старт', a, 0, ['Рынок при квоте', [[/^Объём торговли/, '40'], [/^Выбранная цена/, '60'], [/^Коридор/, '40…60']]]);

/* ── Д: безразличие монополиста ── */
head('Д. Безразличие: D: Q = 120 − P, MC = 160 − 4Q');
a = await answer(`setDS('mono', '120-P', '160-4*Q');`);
ok('статус: потери обоих вариантов', a.status.some(s => /безразлично/.test(s) && /потери общества 0 при Q\s*=\s*40 и 800 при Q\s*=\s*0/.test(s)), a.status);
checkGroup('безразличие', a, 0, ['Монополия', [[/^Выпуск монополиста/, '40'], [/^Цена монополиста/, '80'], [/^Потери общества/, '0'], [/^Излишек потребителя/, '800']]]);
a = await answer(`resetSceneMemory(); pickScene('mono-kink'); closePicker(); STATE.kinkInput = 'individual';
  STATE.kiD1 = '120 - P'; STATE.kiD2 = ''; STATE.kiD3 = ''; STATE.kinkMC = '160 - 4*Q'; redrawAll();`);
ok('составной спрос: «безразлично … или Q = 0», потери обоих', a.status.some(s => /безразлично: Q\s*=\s*40, P\s*=\s*80 или Q\s*=\s*0/.test(s) && /800 при/.test(s)), a.status);

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
ok('ошибок страницы нет', !errs.length, errs.slice(0, 3));
console.log(bad ? ('ПРОВАЛОВ: ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' ПРОВЕРОК «ОТВЕТА» ПРИ ВМЕШАТЕЛЬСТВЕ СОШЛИСЬ'));
await browser.close();
process.exit(bad ? 1 : 0);
