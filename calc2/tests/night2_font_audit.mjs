/* Фаза 13 — СПЛОШНОЙ аудит шрифтов.
   Правило владельца: любые СЛОВА — единым шрифтом сайта; любая МАТЕМАТИКА
   (формулы, обозначения P, Q, MC, CS, DWL и подобные) — набрана формулой.
   Точечно ловить бесполезно, поэтому обходим ВСЕ сцены и все места:
   левая панель, правая аналитика, подписи графика, меню сцен, подсказки.
     node calc2/tests/night2_font_audit.mjs [--json файл]
   Печатает ЧИСЛО найденных случаев и разбивку по местам. */
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const OUT = process.argv.includes('--json') ? process.argv[process.argv.indexOf('--json') + 1] : null;

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin'); await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const SWEEP = `(function () {
  /* Многобуквенные обозначения экономики и однобуквенные величины. Список
     намеренно узкий: ловим то, что ТОЧНО математика, чтобы число значило
     дело, а не длину списка. */
  var WORDS = ['MC','MR','TC','ATC','AVC','AFC','FC','VC','TR','TP','MP','AP','MPL','MRP',
               'Qd','Qs','Pd','Ps','Pb','Pw','Pc','Pf','CS','PS','DWL','AD','AS','SRAS','LRAS',
               'IS','LM','GDP','MSB','MSC','SW','Wmin','Qm','Pm','Qc','Px','Py'];
  var LETTERS = ['P','Q','D','S','L','K','X','Y','W','U','M','E'];
  var re = new RegExp('(?:^|[^A-Za-zА-Яа-я0-9_])(' + WORDS.join('|') + '|'
        + LETTERS.map(function (l) { return l + '(?:\\\\*|\\\\d|_\\\\w)?'; }).join('|')
        + ')(?![A-Za-zА-Яа-я0-9_])', 'g');
  var PLACES = [
    ['левая панель', '#tools-panel'],
    ['правая аналитика', '#params-panel'],
    ['подписи графика', '#chart'],
    ['меню сцен', '#scene-picker'],
  ];
  var out = [];
  PLACES.forEach(function (pl) {
    var root = document.querySelector(pl[1]);
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = walker.nextNode())) {
      var t = (n.nodeValue || '').replace(/\\s+/g, ' ').trim();
      if (!t) return void 0;
      if (!t) continue;
      // Набранное формулой пропускаем: там математика уже математика.
      var el = n.parentElement;
      // Набранное формулой пропускаем: и KaTeX в разметке, и подписи графика,
      // которым typesetChartLabels уже поставил математическое начертание.
      if (!el || el.closest('.katex') || el.closest('math-field') || el.closest('script')) continue;
      // Ищем пометку у ПРЕДКА: текстовый узел лежит внутри <tspan>, а пометку
      // ставит сам <text>, и проверка по прямому родителю её не видела.
      if (el.closest && el.closest('[data-mathset]')) continue;
      // <title> внутри SVG — всплывающая подсказка, а не подпись на холсте.
      var place = pl[0];
      if (String(el.nodeName).toLowerCase() === 'title') place = 'подсказки';
      if (el.offsetParent === null && pl[1] !== '#chart') continue;
      re.lastIndex = 0;
      var m, hits = [];
      while ((m = re.exec(t))) hits.push(m[1]);
      if (hits.length) out.push({ место: place, текст: t.slice(0, 70), обозначения: hits,
                                  узел: el.className || el.tagName });
    }
  });
  // Подсказки: их читают глазами так же, как текст на экране.
  ['[data-tip]', '[title]'].forEach(function (sel) {
    [].slice.call(document.querySelectorAll('#tools-panel ' + sel + ', #params-panel ' + sel)).forEach(function (e) {
      var t = (e.getAttribute('data-tip') || e.getAttribute('title') || '').replace(/\\s+/g, ' ').trim();
      /* ⚠️ ЧТО СТОИТ МЕЖДУ ДОЛЛАРАМИ — УЖЕ НАБРАНО ФОРМУЛОЙ, А НЕ ТЕКСТОМ.
         Плашка подсказки прогоняет свой текст через renderMathIn, и «$MC$»
         попадает на экран математическим начертанием. Считать его нарушением
         значит считать нарушением саму починку. */
      t = t.replace(/\\$[^$]*\\$/g, ' ');
      if (!t.trim()) return;
      re.lastIndex = 0; var m, hits = [];
      while ((m = re.exec(t))) hits.push(m[1]);
      if (hits.length) out.push({ место: 'подсказки', текст: t.slice(0, 70), обозначения: hits, узел: e.className || e.tagName });
    });
  });
  return out;
})()`;

const all = [];
for (const key of scenes) {
  /* Карточки раскрываем принудительно: сцена открывается со всеми свёрнутыми,
     а свёрнутое не видит ни человек, ни прибор — и число «найдено» оказалось бы
     свойством состояния экрана, а не кода (та же болезнь, что у проверки канона). */
  await page.evaluate(k => {
    resetSceneMemory(); pickScene(k); setToolsOpen(true); setParamsOpen(true);
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(function (b) {
      var body = document.getElementById(b.getAttribute('aria-controls'));
      if (!body) return;
      body.classList.add('open');
      b.setAttribute('aria-expanded', 'true');
      var card = b.closest('.section, .side-part');
      if (card) card.classList.add('open-card');
    });
  }, key);
  await page.waitForTimeout(650);
  const found = await page.evaluate(SWEEP);
  found.forEach(f => all.push({ сцена: key, ...f }));
}
// Меню сцен смотрим отдельно: оно закрыто, пока выбрана сцена.
await page.evaluate(() => { const p = document.getElementById('scene-picker'); if (p) p.classList.remove('hidden'); });
await page.waitForTimeout(400);
const picker = await page.evaluate(SWEEP);
picker.filter(f => f.место === 'меню сцен').forEach(f => all.push({ сцена: '(меню)', ...f }));

const byPlace = {};
all.forEach(f => { byPlace[f.место] = (byPlace[f.место] || 0) + f.обозначения.length; });
const uniq = {};
all.forEach(f => f.обозначения.forEach(s => { uniq[s] = (uniq[s] || 0) + 1; }));
const total = Object.values(byPlace).reduce((a, b) => a + b, 0);
console.log('=== АУДИТ ШРИФТОВ: математика, набранная обычным текстом ===');
console.log('Всего случаев: ' + total + ' в ' + all.length + ' строках, сцен обойдено: ' + scenes.length);
console.log('\nПо местам:');
Object.entries(byPlace).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => console.log('  ' + k + ': ' + v));
console.log('\nПо обозначениям (топ 20):');
Object.entries(uniq).sort((a, b) => b[1] - a[1]).slice(0, 20).forEach(([k, v]) => console.log('  ' + k + ': ' + v));
if (OUT) { writeFileSync(OUT, JSON.stringify({ total, byPlace, uniq, all }, null, 1)); console.log('\nПодробности: ' + OUT); }
if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 4).join(' | '));
await browser.close();
