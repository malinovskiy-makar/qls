// Замер содержимого выгрузки .tex (фаза 2, пункты А45–А49; с 08.10 — новая выгрузка, ADR 0139).
// Печатает по сцене: размер картинки, кегли, сколько кривых формулой против
// таблиц координат, сколько подписей математикой, совпадает ли набор подписей
// с тем, что видно на экране.
// Запуск: node calc2/tests/export_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SCENES = (process.env.SCENES || 'sd,tax,mono,adas,isoquant,costs').split(',');
/* Сцены, для которых выгрузка обязана выдать полноценный файл (приёмка 26.08):
   сложение D и S, сложение КПВ, налог. ⚠️ ПЕРЕНАЦЕЛЕНО 08.10: проверки, писанные
   для сборщика от состояния (buildTexFromState), теперь стерегут то же самое у
   настоящей двери buildTex — бумажный прогон, опись, сборка (72-export-tex.js). */
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
  /* ⚠️ ВЕТКА SKIP ВЕРНУЛА СЕБЕ СВОЙ ВЫХОД. 26.08 сюда целиком заехала копия
     блока проверок генератора от состояния: ~125 мёртвых строк внутри ветки,
     которая при нормальной загрузке не исполняется вовсе, и `process.exit(3)`
     оказался за `process.exit(bad ? 1 : 0)`. На результат это не влияло, но
     при РЕАЛЬНОМ сбое загрузки вместо понятного SKIP вышло бы невнятное
     падение на первом же обращении к несуществующим функциям страницы. */
  console.error('SKIP: calc2 не загрузился');
  await browser.close();
  process.exit(3);
}

const measure = async (key) => page.evaluate(async (k) => {
  pickScene(k);
  await new Promise(r => setTimeout(r, 450));
  const tex = buildTex('Проба', '');
  const size = /width=([\d.]+)pt, height=([\d.]+)pt/.exec(tex);
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

console.log('сцена       поле графика   форм/крив+отр  подписей(мат.)  видимых  кегли(pt)  легенд');
for (const key of SCENES) {
  const r = await measure(key);
  console.log(
    key.padEnd(11) +
    `${r.w}×${r.h}pt`.padEnd(15) +
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
   ВЫГРУЗКА ОТ НАРИСОВАННОГО С ЗАПИСЬЮ (08.10, ADR 0139). Правила те же, что
   ставились сборщику от состояния 26.08: кривые формулами, у каждой толщина,
   нет заливки цветом холста, сборка не спрашивает экран, файл не зависит от
   окна.
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
    return buildTex('Проба', '');
  }, [k, '(' + setupFor.toString() + ')(k)']);
};

console.log('\n=== Выгрузка .tex (дверь buildTex) ===');
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
  /* ⚠️ ПЕРЕНАЦЕЛЕНО 08.10: «кривые в файле есть» — это кривые холста (опись окна
     «Скачать»), а не только строки \addplot{формула}: у кривой без записи
     (сложение КПВ до записей фазы 2) в файле точная ломаная. Формулами ли они
     ушли — считает аудит выгрузки (calc2/tests/tex/summary.mjs, дефекты записи). */
  const curves = await page.evaluate(() => (buildTex._tally || {}).curves || 0);
  flag(curves > 0, 'кривые в файле есть', 'кривых холста в файле: ' + curves + ', из них формулой ' + draws.length);
  flag(noWidth.length === 0, 'у каждой кривой указана толщина',
       noWidth.length ? noWidth[0].slice(0, 90) : '');
  const widths = [...new Set((tex.match(/line width=([\d.]+)pt/g) || []))];
  console.log('       толщины в файле: ' + widths.join(', '));
  const dashed = (tex.match(/dash pattern=/g) || []).length;
  console.log('       штриховых кривых: ' + dashed);

  /* 3. Заливки цветом холста на бумаге быть не должно (старая ловушка Б6):
        на белом листе это тёмное пятно на пустом месте. */
  const canvasHex = await page.evaluate(() => {
    const m = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim();
    const t = document.createElement('i'); t.style.color = m; document.body.appendChild(t);
    const c = getComputedStyle(t).color.match(/\d+/g).slice(0, 3); t.remove();
    return c.map(v => (+v).toString(16).toUpperCase().padStart(2, '0')).join('');
  });
  flag(tex.indexOf('c' + canvasHex) < 0, 'нет заливки цветом холста', 'цвет холста ' + canvasHex);

  /* 4. ⚠️ СНЯТО 08.10: «итоговая функция есть в файле». Её дописывал под рисунком
        только сборщик от состояния, а он по умолчанию не работал, и в файлах,
        которые получали люди, её не было. Новая выгрузка повторяет холст, а
        запись итоговой функции живёт в «Ответе», не на холсте (решение 07.10). */

  /* 5. Сборка — чистая функция: опись → текст, экран она не спрашивает. Холст
        читает опись на бумажном прогоне, и это по замыслу (решение 07.10);
        проверяем по коду самой сборки. */
  const src = await page.evaluate(() => String(TexExport.emit));
  ['getComputedStyle', 'getBoundingClientRect', 'document.', 'STATE.'].forEach(bad2 => {
    flag(src.indexOf(bad2) < 0, 'в сборке нет ' + bad2);
  });

  /* 6. Файл не зависит от ширины окна: побайтово тот же, ВКЛЮЧАЯ границы
        окна (холст на листе постоянного размера). */
  const wide = await buildState(key, 1600);
  flag(tex === wide, 'файл при окне 1200 и 1600 px одинаков', tex.length + ' против ' + wide.length + ' знаков');
}
/* ═══ ОХВАТ: ПУСТОГО ЛИСТА НЕТ НИ У ОДНОЙ МОДЕЛИ ════════════════════════
   ⚠️ ПЕРЕНАЦЕЛЕНО 08.10. Здесь стоял храповик 22 пустых листов у сборщика
   от состояния. Новая выгрузка читает всё нарисованное, поэтому пустых
   листов у неё ноль из 44, и это число больше не храповик, а требование. */
const COVER_MAX = 0;
await page.setViewportSize({ width: 1280, height: 900 });
const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const empty = [];
for (const k of keys) {
  const r = await page.evaluate(async (k) => {
    resetSceneMemory(); pickScene(k);
    await new Promise(r => setTimeout(r, 260)); redrawAll();
    const cnt = (t) => (t.match(/\\addplot\[/g) || []).length + (t.match(/\\node\[/g) || []).length + (t.match(/\\fill\[/g) || []).length;
    let a = 0;
    try { a = cnt(buildTex('t', '')); } catch (e) { a = 0; }
    return { a };
  }, k);
  if (r.a === 0) empty.push(k);
}
console.log('\n=== Охват: пустой лист ===');
console.log('  моделей, где файл выходит ПУСТЫМ: ' + empty.length + ' из ' + keys.length + (empty.length ? ' — ' + empty.join(', ') : ''));
flag(empty.length <= COVER_MAX, 'пустых листов нет', 'сейчас ' + empty.length);

console.log('\n' + (bad ? ('ПРОВАЛОВ: ' + bad) : 'Выгрузка .tex: всё сошлось'));

await browser.close();
process.exit(bad ? 1 : 0);
