// Фаза 4 — единый механизм вмешательства: выбор вида → свои настройки → значение.
// Проверяется, что переключение между видами НЕ оставляет следов предыдущего.
// Способ честный: снимок вида, полученного переходом, сверяется со снимком того
// же вида, открытого с чистой сцены. Любое расхождение — след.
//   node calc2/tests/interv_phase4_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

const KINDS = ['tax', 'subsidy', 'ceiling', 'floor', 'quota'];
const RU = { tax: 'налог', subsidy: 'субсидия', ceiling: 'потолок', floor: 'пол', quota: 'квота' };
// Каждому виду — своё каноническое значение (см. эталон Фазы 0).
const APPLY = {
  tax:      "setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(20);",
  subsidy:  "setType('subsidy'); setTaxKind('unit'); setTax(20);",
  ceiling:  "setType('ceiling'); setPReg(30);",
  floor:    "setType('floor'); setPReg(70);",
  quota:    "setType('quota'); setQuota(40); setQuotaPos(0.5);",
};

// Снимок всего, что видно: слои графика, подписи, поля панели, числа аналитики.
const SNAP = `(function(){
  var norm = function (t) { return String(t == null ? '' : t).replace(/\\s+/g, ' ').trim(); };
  var chart = document.getElementById('chart');
  var legends = [].map.call(chart.querySelectorAll('[data-legend]'), function (e) { return e.getAttribute('data-legend'); }).sort();
  var texts = [].map.call(chart.querySelectorAll('text'), function (e) { return norm(e.textContent); })
                 .filter(Boolean).sort();
  var shapes = {};
  ['line', 'circle', 'rect', 'path'].forEach(function (t) { shapes[t] = chart.querySelectorAll(t).length; });
  var vis = function (id) { var e = document.getElementById(id); return !!(e && e.offsetParent !== null); };
  var fields = ['tax-field', 'pc-field', 'quota-field', 'quota-price-field',
                'taxkind-row', 'taxside-row', 'tax-hint', 'pc-hint', 'quota-hint']
                 .filter(vis).sort();
  var pult = (typeof pultRegulatorIds === 'function') ? pultRegulatorIds().slice().sort() : [];
  return { legends: legends, texts: texts, shapes: shapes, fields: fields, pult: pult,
           info: norm((document.getElementById('info-tax') || {}).innerText),
           areas: norm((document.getElementById('info-areas') || {}).innerText),
           board: norm((document.getElementById('sb-body') || {}).innerText) };
})()`;

// Эталон: вид открыт с чистой сцены.
const fresh = {};
for (const k of KINDS) {
  fresh[k] = await page.evaluate(`(function(){
    resetSceneMemory(); pickScene('taxes');
    ${APPLY[k]}
    redrawAll();
    return ${SNAP};
  })()`);
}

// Что именно разошлось — по частям, чтобы в отчёт попал конкретный след.
function diff(a, b) {
  const out = [];
  const setDiff = (name, xa, xb) => {
    const only = (p, q) => p.filter(v => !q.includes(v));
    const extra = only(xb, xa), missing = only(xa, xb);
    if (extra.length) out.push(name + ': лишнее [' + extra.join(' | ') + ']');
    if (missing.length) out.push(name + ': пропало [' + missing.join(' | ') + ']');
  };
  setDiff('закраски', a.legends, b.legends);
  setDiff('подписи', a.texts, b.texts);
  setDiff('поля панели', a.fields, b.fields);
  setDiff('лента регуляторов', a.pult, b.pult);
  ['line', 'circle', 'rect', 'path'].forEach(t => {
    if (a.shapes[t] !== b.shapes[t]) out.push('фигур <' + t + '>: ' + b.shapes[t] + ' вместо ' + a.shapes[t]);
  });
  if (a.info !== b.info) out.push('аналитика: «' + b.info.slice(0, 110) + '» вместо «' + a.info.slice(0, 110) + '»');
  if (a.areas !== b.areas) out.push('излишки: «' + b.areas.slice(0, 80) + '» вместо «' + a.areas.slice(0, 80) + '»');
  if (a.board !== b.board) out.push('ключевые значения разошлись');
  return out;
}

let pairs = 0, bad = 0, traces = 0;
const report = [];
for (const from of KINDS) {
  for (const to of KINDS) {
    if (from === to) continue;
    pairs++;
    const got = await page.evaluate(`(function(){
      resetSceneMemory(); pickScene('taxes');
      ${APPLY[from]}
      redrawAll();
      ${APPLY[to]}
      redrawAll();
      return ${SNAP};
    })()`);
    const d = diff(fresh[to], got);
    if (d.length) { bad++; traces += d.length; report.push(RU[from] + ' -> ' + RU[to] + ':\n      ' + d.join('\n      ')); }
    console.log((d.length ? 'FAIL ' : 'OK   ') + RU[from] + ' → ' + RU[to] + (d.length ? '  (следов: ' + d.length + ')' : ''));
  }
}

console.log('\nПереходов проверено: ' + pairs + '; с следами: ' + bad + '; всего следов: ' + traces);
if (report.length) console.log('\n' + report.join('\n'));
if (errs.length) console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | '));
await browser.close();
const ok = (bad === 0 && errs.length === 0);
console.log('\nФАЗА 4: ' + (ok ? 'СЛЕДОВ НЕТ' : 'ЕСТЬ СЛЕДЫ'));
process.exit(ok ? 0 : 1);
