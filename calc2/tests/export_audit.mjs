// Замер содержимого выгрузки .tex (фаза 2, пункты А45–А49).
// Печатает по сцене: размер картинки, кегли, сколько кривых формулой против
// таблиц координат, сколько подписей математикой, совпадает ли набор подписей
// с тем, что видно на экране.
// Запуск: node calc2/tests/export_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SCENES = (process.env.SCENES || 'sd,tax,mono,adas,isoquant,costs').split(',');
/* Сцены, для которых генератор ОТ СОСТОЯНИЯ обязан выдать полноценный файл.
   Их и требует приёмка 26.08: сложение D и S, сложение КПВ, налог. */
const STATE_SCENES = (process.env.STATE_SCENES || 'sdsum,ppfsum,taxes').split(',');

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);
if (!await page.evaluate(() => typeof buildTex === 'function')) {
  console.error('SKIP: calc2 не загрузился'); /* ═══════════════════════════════════════════════════════════════════════
   ГЕНЕРАТОР ОТ СОСТОЯНИЯ (26.08). Правила, которых у старого сборщика не было
   и быть не могло: он снимал координаты с пикселей экрана.
   ═══════════════════════════════════════════════════════════════════════ */
let bad = 0;
const flag = (ok, label, detail) => {
  if (!ok) bad++;
  console.log('  ' + (ok ? 'OK   ' : 'FAIL ') + label + (detail != null ? '  -> ' + detail : ''));
};

const setupFor = (k) => {
  if (k === 'taxes') { setType('tax'); setTaxForm('unit'); setTax(20); }
  if (k === 'ppfsum') {
    STATE.ppfSumCount = 2;
    ppfSumSet(0, 'y = 100 - x'); ppfSumSet(1, 'y = 60 - 3*x');
    if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
    recomputePpfSum();
  }
};

const buildState = async (k, w) => {
  await page.setViewportSize({ width: w, height: 900 });
  return page.evaluate(async ([key, src]) => {
    resetSceneMemory(); pickScene(key);
    (new Function('k', src))(key);
    redrawAll();
    await new Promise(r => setTimeout(r, 450));
    return buildTexFromState('Проба', '');
  }, [k, '(' + setupFor.toString() + ')(k)']);
};

console.log('\n=== Генератор .tex от состояния ===');
for (const key of STATE_SCENES) {
  const tex = await buildState(key, 1200);
  console.log('\n  -- сцена ' + key + ', ' + tex.length + ' знаков');

  /* 1. Кривые обязаны быть ФОРМУЛАМИ. Таблица длиннее трёх точек означает, что
        кривую снова выгрузили списком координат, снятых с экрана. */
  const tables = [...tex.matchAll(/\\addplot\[[^\]]*\] *coordinates \{([^}]*)\}/g)]
    .map(m => (m[1].match(/\(/g) || []).length);
  const long = tables.filter(n => n > 3);
  flag(long.length === 0, 'кривые выгружены формулами, а не таблицами точек',
       long.length ? ('таблиц длиннее трёх точек: ' + long.length + ' (' + long.join(', ') + ')') : 'таблиц нет');

  /* 2. У каждой кривой есть толщина, у пунктирной — рисунок штриха.
        Ровно этот долг и чинился: старый файл рисовал всё одной толщиной. */
  const draws = (tex.match(/\\addplot\[[^\]]*\][^;]*\{[^;]*\};/g) || [])
    .filter(l => !/draw=none/.test(l) && !/only marks/.test(l));
  const noWidth = draws.filter(l => !/line width=/.test(l));
  flag(draws.length > 0, 'кривые в файле есть', 'кривых: ' + draws.length);
  flag(noWidth.length === 0, 'у каждой кривой указана толщина',
       noWidth.length ? noWidth[0].slice(0, 90) : '');
  const widths = [...new Set((tex.match(/line width=([\d.]+)pt/g) || []))];
  console.log('       толщины в файле: ' + widths.join(', '));
  const dashed = (tex.match(/dash pattern=/g) || []).length;
  console.log('       штриховых кривых: ' + dashed);

  /* 3. Заливки цветом холста на бумаге быть не должно (старая ловушка Б6):
        на белом листе это тёмное пятно на пустом месте. */
  const canvasHex = await page.evaluate(() =>
    texHex(getComputedStyle(document.documentElement).getPropertyValue('--canvas')));
  flag(tex.indexOf('c' + canvasHex) < 0, 'нет заливки цветом холста', 'цвет холста ' + canvasHex);

  /* 4. Итоговая функция сцены обязана быть и в файле. */
  const shows = await page.evaluate(() => {
    const ff = document.getElementById('info-final');
    return !!(ff && ff.querySelector('.ff-math'));
  });
  if (shows) flag(/\\\[/.test(tex), 'итоговая функция есть в файле');
  else console.log('       итоговой функции сцена не показывает — и в файле её нет');

  /* 5. Ни одного следа обхода холста: генератор не имеет права спрашивать
        браузер о пикселях. Проверяем по коду самой функции. */
  const src = await page.evaluate(() => String(buildTexFromState));
  ['getComputedStyle', 'getBoundingClientRect', 'querySelectorAll(\'#chart', 'getElementById(\'chart'].forEach(bad2 => {
    flag(src.indexOf(bad2) < 0, 'в генераторе нет ' + bad2);
  });

  /* 6. Файл не зависит от ширины окна: всё, кроме границ окна, побайтово то же.
        Раньше это было НЕ так — старый сборщик снимал координаты с пикселей. */
  const wide = await buildState(key, 1600);
  const strip = (t) => t.replace(/xmin=[^\]]*?ymax=[^,\]]*/, 'ОКНО');
  flag(strip(tex) === strip(wide), 'файл при окне 1200 и 1600 px одинаков (кроме границ окна)',
       tex.length + ' против ' + wide.length + ' знаков');
}
/* ═══ ОХВАТ: ГДЕ НОВЫЙ ГЕНЕРАТОР ПОКА МОЛЧИТ ═══════════════════════════
   Генератор от состояния рисует то, что в состоянии ЕСТЬ. Кривые двадцати
   двух сцен из сорока четырёх живут не в STATE.curves, а внутри самих сцен
   (издержки, макро, труд, потребитель, «Математика», КПВ и КТВ), и для них
   файл выходит пустым. Пока это так, переключать выгрузку по умолчанию
   нельзя: половина калькулятора выгружала бы чистый лист.

   ⚠️ ЧИСЛО ЗДЕСЬ — ХРАПОВИК, А НЕ ЦЕЛЬ. Оно имеет право только УМЕНЬШАТЬСЯ:
   каждая сцена, объявившая свои кривые в состоянии, снимает единицу. Выросло
   — значит сцену сломали или завели новую, которая рисует мимо состояния. */
const COVER_MAX = 22;
await page.setViewportSize({ width: 1280, height: 900 });
const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const empty = [];
for (const k of keys) {
  const r = await page.evaluate(async (k) => {
    resetSceneMemory(); pickScene(k);
    await new Promise(r => setTimeout(r, 260)); redrawAll();
    const cnt = (t) => (t.match(/\\addplot\[/g) || []).length + (t.match(/\\node\[/g) || []).length;
    let a = 0, l = 0;
    try { a = cnt(buildTexFromState('t', '')); } catch (e) { a = 0; }
    try { l = cnt(buildTexLegacy('t', '')); } catch (e) { l = 0; }
    return { a, l };
  }, k);
  if (r.a === 0 && r.l > 0) empty.push(k);
}
console.log('\n=== Охват генератора от состояния ===');
console.log('  сцен, где файл выходит ПУСТЫМ, а у старого сборщика нет: '
            + empty.length + ' из ' + keys.length);
console.log('  ' + empty.join(', '));
flag(empty.length <= COVER_MAX, 'охват не ухудшился (храповик ' + COVER_MAX + ')',
     'сейчас ' + empty.length);
if (empty.length > 0) {
  console.log('  ⚠️ пока это число не ноль, выгрузка по умолчанию остаётся СТАРОЙ:');
  console.log('     новый генератор включается параметром адреса ?texState=1');
}

console.log('\n' + (bad ? ('ПРОВАЛОВ: ' + bad) : 'Генератор от состояния: всё сошлось'));

await browser.close();
process.exit(bad ? 1 : 0); process.exit(3);
}

const measure = async (key) => page.evaluate(async (k) => {
  pickScene(k);
  await new Promise(r => setTimeout(r, 450));
  const tex = buildTex('Проба', '');
  const size = /width=([\d.]+)cm, height=([\d.]+)cm/.exec(tex);
  const plots = tex.match(/\\addplot\[[^\]]*\]/g) || [];
  const tableBlocks = [...tex.matchAll(/\\addplot\[[^\]]*\] *coordinates \{([^}]*)\}/g)]
    .map(m => (m[1].match(/\(/g) || []).length);
  const tables = tableBlocks.length;
  const bigTables = tableBlocks.filter(n => n > 5).length;   // настоящие кривые точками
  const segs = tableBlocks.filter(n => n <= 5).length;       // короткие отрезки-проекции
  const formulas = (tex.match(/\\addplot\[[^\]]*\] *\{/g) || []).length;
  const nodes = tex.match(/\\node\[[^\]]*\] at \(axis cs:[^)]*\) \{([^}]*(?:\{[^}]*\}[^}]*)*)\}/g) || [];
  const mathNodes = nodes.filter(n => /\{\$/.test(n)).length;
  const pts = [...tex.matchAll(/font=\\fontsize\{([\d.]+)\}/g)].map(m => +m[1]);
  // Подписи, которые видит человек на холсте.
  const vis = [];
  document.querySelectorAll('#chart text').forEach(t => {
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    const own = Array.prototype.filter.call(t.childNodes, n => n.nodeType === 3).map(n => n.nodeValue).join('').trim();
    if (own) vis.push(own);
  });
  return {
    w: size ? +size[1] : null, h: size ? +size[2] : null,
    plots: plots.length, tables, formulas, bigTables, segs,
    nodes: nodes.length, mathNodes,
    pts: [...new Set(pts)].sort((a, b) => a - b),
    visible: vis.length,
    legendEntries: (tex.match(/\\addlegendentry/g) || []).length,
    chars: tex.length,
  };
}, key);

console.log('сцена       картинка   форм/крив+отр  подписей(мат.)  видимых  кегли(pt)  легенд');
for (const key of SCENES) {
  const r = await measure(key);
  console.log(
    key.padEnd(11) +
    `${r.w}×${r.h}см`.padEnd(11) +
    `${r.formulas}/${r.bigTables}+${r.segs}`.padEnd(15) +
    `${r.nodes} (${r.mathNodes})`.padEnd(16) +
    String(r.visible).padEnd(9) +
    r.pts.join(',').padEnd(11) +
    String(r.legendEntries)
  );
}

// Независимость от ширины окна: тот же .tex при другом окне.
const same = [];
for (const key of ['sd', 'tax']) {
  await page.setViewportSize({ width: 1280, height: 900 });
  const a = await page.evaluate(async (k) => { pickScene(k); await new Promise(r => setTimeout(r, 450)); return buildTex('Проба', ''); }, key);
  await page.setViewportSize({ width: 820, height: 620 });
  const b = await page.evaluate(async (k) => { pickScene(k); await new Promise(r => setTimeout(r, 450)); return buildTex('Проба', ''); }, key);
  same.push([key, a === b, a.length, b.length]);
}
console.log('\nОдинаков ли .tex при разной ширине окна:');
same.forEach(([k, eq, la, lb]) => console.log(`  ${k.padEnd(6)} ${eq ? 'да' : 'НЕТ'}  (${la} против ${lb} знаков)`));

/* ═══════════════════════════════════════════════════════════════════════
   ГЕНЕРАТОР ОТ СОСТОЯНИЯ (26.08). Правила, которых у старого сборщика не было
   и быть не могло: он снимал координаты с пикселей экрана.
   ═══════════════════════════════════════════════════════════════════════ */
let bad = 0;
const flag = (ok, label, detail) => {
  if (!ok) bad++;
  console.log('  ' + (ok ? 'OK   ' : 'FAIL ') + label + (detail != null ? '  -> ' + detail : ''));
};

const setupFor = (k) => {
  if (k === 'taxes') { setType('tax'); setTaxForm('unit'); setTax(20); }
  if (k === 'ppfsum') {
    STATE.ppfSumCount = 2;
    ppfSumSet(0, 'y = 100 - x'); ppfSumSet(1, 'y = 60 - 3*x');
    if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
    recomputePpfSum();
  }
};

const buildState = async (k, w) => {
  await page.setViewportSize({ width: w, height: 900 });
  return page.evaluate(async ([key, src]) => {
    resetSceneMemory(); pickScene(key);
    (new Function('k', src))(key);
    redrawAll();
    await new Promise(r => setTimeout(r, 450));
    return buildTexFromState('Проба', '');
  }, [k, '(' + setupFor.toString() + ')(k)']);
};

console.log('\n=== Генератор .tex от состояния ===');
for (const key of STATE_SCENES) {
  const tex = await buildState(key, 1200);
  console.log('\n  -- сцена ' + key + ', ' + tex.length + ' знаков');

  /* 1. Кривые обязаны быть ФОРМУЛАМИ. Таблица длиннее трёх точек означает, что
        кривую снова выгрузили списком координат, снятых с экрана. */
  const tables = [...tex.matchAll(/\\addplot\[[^\]]*\] *coordinates \{([^}]*)\}/g)]
    .map(m => (m[1].match(/\(/g) || []).length);
  const long = tables.filter(n => n > 3);
  flag(long.length === 0, 'кривые выгружены формулами, а не таблицами точек',
       long.length ? ('таблиц длиннее трёх точек: ' + long.length + ' (' + long.join(', ') + ')') : 'таблиц нет');

  /* 2. У каждой кривой есть толщина, у пунктирной — рисунок штриха.
        Ровно этот долг и чинился: старый файл рисовал всё одной толщиной. */
  const draws = (tex.match(/\\addplot\[[^\]]*\][^;]*\{[^;]*\};/g) || [])
    .filter(l => !/draw=none/.test(l) && !/only marks/.test(l));
  const noWidth = draws.filter(l => !/line width=/.test(l));
  flag(draws.length > 0, 'кривые в файле есть', 'кривых: ' + draws.length);
  flag(noWidth.length === 0, 'у каждой кривой указана толщина',
       noWidth.length ? noWidth[0].slice(0, 90) : '');
  const widths = [...new Set((tex.match(/line width=([\d.]+)pt/g) || []))];
  console.log('       толщины в файле: ' + widths.join(', '));
  const dashed = (tex.match(/dash pattern=/g) || []).length;
  console.log('       штриховых кривых: ' + dashed);

  /* 3. Заливки цветом холста на бумаге быть не должно (старая ловушка Б6):
        на белом листе это тёмное пятно на пустом месте. */
  const canvasHex = await page.evaluate(() =>
    texHex(getComputedStyle(document.documentElement).getPropertyValue('--canvas')));
  flag(tex.indexOf('c' + canvasHex) < 0, 'нет заливки цветом холста', 'цвет холста ' + canvasHex);

  /* 4. Итоговая функция сцены обязана быть и в файле. */
  const shows = await page.evaluate(() => {
    const ff = document.getElementById('info-final');
    return !!(ff && ff.querySelector('.ff-math'));
  });
  if (shows) flag(/\\\[/.test(tex), 'итоговая функция есть в файле');
  else console.log('       итоговой функции сцена не показывает — и в файле её нет');

  /* 5. Ни одного следа обхода холста: генератор не имеет права спрашивать
        браузер о пикселях. Проверяем по коду самой функции. */
  const src = await page.evaluate(() => String(buildTexFromState));
  ['getComputedStyle', 'getBoundingClientRect', 'querySelectorAll(\'#chart', 'getElementById(\'chart'].forEach(bad2 => {
    flag(src.indexOf(bad2) < 0, 'в генераторе нет ' + bad2);
  });

  /* 6. Файл не зависит от ширины окна: всё, кроме границ окна, побайтово то же.
        Раньше это было НЕ так — старый сборщик снимал координаты с пикселей. */
  const wide = await buildState(key, 1600);
  const strip = (t) => t.replace(/xmin=[^\]]*?ymax=[^,\]]*/, 'ОКНО');
  flag(strip(tex) === strip(wide), 'файл при окне 1200 и 1600 px одинаков (кроме границ окна)',
       tex.length + ' против ' + wide.length + ' знаков');
}
/* ═══ ОХВАТ: ГДЕ НОВЫЙ ГЕНЕРАТОР ПОКА МОЛЧИТ ═══════════════════════════
   Генератор от состояния рисует то, что в состоянии ЕСТЬ. Кривые двадцати
   двух сцен из сорока четырёх живут не в STATE.curves, а внутри самих сцен
   (издержки, макро, труд, потребитель, «Математика», КПВ и КТВ), и для них
   файл выходит пустым. Пока это так, переключать выгрузку по умолчанию
   нельзя: половина калькулятора выгружала бы чистый лист.

   ⚠️ ЧИСЛО ЗДЕСЬ — ХРАПОВИК, А НЕ ЦЕЛЬ. Оно имеет право только УМЕНЬШАТЬСЯ:
   каждая сцена, объявившая свои кривые в состоянии, снимает единицу. Выросло
   — значит сцену сломали или завели новую, которая рисует мимо состояния. */
const COVER_MAX = 22;
await page.setViewportSize({ width: 1280, height: 900 });
const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const empty = [];
for (const k of keys) {
  const r = await page.evaluate(async (k) => {
    resetSceneMemory(); pickScene(k);
    await new Promise(r => setTimeout(r, 260)); redrawAll();
    const cnt = (t) => (t.match(/\\addplot\[/g) || []).length + (t.match(/\\node\[/g) || []).length;
    let a = 0, l = 0;
    try { a = cnt(buildTexFromState('t', '')); } catch (e) { a = 0; }
    try { l = cnt(buildTexLegacy('t', '')); } catch (e) { l = 0; }
    return { a, l };
  }, k);
  if (r.a === 0 && r.l > 0) empty.push(k);
}
console.log('\n=== Охват генератора от состояния ===');
console.log('  сцен, где файл выходит ПУСТЫМ, а у старого сборщика нет: '
            + empty.length + ' из ' + keys.length);
console.log('  ' + empty.join(', '));
flag(empty.length <= COVER_MAX, 'охват не ухудшился (храповик ' + COVER_MAX + ')',
     'сейчас ' + empty.length);
if (empty.length > 0) {
  console.log('  ⚠️ пока это число не ноль, выгрузка по умолчанию остаётся СТАРОЙ:');
  console.log('     новый генератор включается параметром адреса ?texState=1');
}

console.log('\n' + (bad ? ('ПРОВАЛОВ: ' + bad) : 'Генератор от состояния: всё сошлось'));

await browser.close();
process.exit(bad ? 1 : 0);
