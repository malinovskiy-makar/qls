// Точка переписывания эталонов старта труда (сессия «рынок труда», конец этапа Б и сверка в конце В; ADR 0156).
// Для ключей labor, labor-mono, labor-union, labor-bilat: открыть старт тем же путём, что session_probe §8 и
// parity_quick (resetSceneMemory + pickScene, settle, redrawAll), снять __RD.stateDump() и __RD.answerOld() и
// переписать в calc2/tests/redesign/baseline/<ключ>.json раздел start: в start.state — ТОЛЬКО разошедшиеся поля
// (список печатается; поле вне труда — останов без записи), start.answer — целиком (строки «Ответа» новым составом).
//   node claude/calc2_labor/rewrite_baselines.mjs [--dry] [--keys labor,labor-bilat]
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import * as L from '../../calc2/tests/redesign/lib.mjs';
import * as layerNew from '../../calc2/tests/redesign/layer_new.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BL = 'calc2/tests/redesign/baseline';
const argv = process.argv.slice(2);
const DRY = argv.includes('--dry');
const ki = argv.indexOf('--keys');
const KEYS = ki >= 0 ? argv[ki + 1].split(',') : ['labor', 'labor-mono', 'labor-union', 'labor-bilat'];
// Производное от размера холста — session_probe §8 его не сравнивает (тот же список).
const VIEW = ['crosses', 'sceneKey', 'legendSpot', 'tanTop', 'tanBot'];
// Поля, которые вправе разойтись из-за старта труда: кривые и всё, что из них считается сценой труда, окно осей.
const LABOR_OK = /^(curves|laborD|laborS|laborEq|laborMono|laborMin|laborMinW|laborMinOn|laborMinWelfare|laborWorkerCS|laborFirmCS|laborUnion|laborBilateral|D|S|eq|cs|ps|dwl|ranges|Qmax|Pmax|Qmin|Pmin|xmax|ymax|xMax|yMax|qMax|pMax|winQ|winP|view|axisMax|curveCounter)$/;

/* Запись тем же форматом, что snapshot.mjs (dump): верхний уровень и каждый шаг — своей строкой. */
function dump(rec) {
  const lines = ['{'];
  const ks = Object.keys(rec);
  ks.forEach((k, i) => {
    const v = rec[k];
    const tail = i < ks.length - 1 ? ',' : '';
    if (Array.isArray(v) && v.length && typeof v[0] === 'object') {
      lines.push(JSON.stringify(k) + ': [');
      v.forEach((x, j) => lines.push(' ' + JSON.stringify(x) + (j < v.length - 1 ? ',' : '')));
      lines.push(']' + tail);
    } else if (k === 'inventory' || k === 'start') {
      lines.push(JSON.stringify(k) + ': {');
      const kk = Object.keys(v);
      kk.forEach((x, j) => lines.push(' ' + JSON.stringify(x) + ': ' + JSON.stringify(v[x]) + (j < kk.length - 1 ? ',' : '')));
      lines.push('}' + tail);
    } else lines.push(JSON.stringify(k) + ': ' + JSON.stringify(v) + tail);
  });
  lines.push('}');
  return lines.join('\n') + '\n';
}

L.configure({ layer: layerNew, base: BASE, layerName: 'new' });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: L.viewport(), reducedMotion: 'reduce', locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
const p = await ctx.newPage();
await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
await p.waitForFunction(() => typeof pickScene === 'function');
await p.addScriptTag({ content: L.INPAGE });
await p.evaluate(async () => { const a = []; document.fonts.forEach(x => a.push(x.load().catch(() => null))); await Promise.all(a); });
let stop = false;
for (const k of KEYS) {
  const file = path.join(BL, k + '.json');
  const rec = JSON.parse(fs.readFileSync(file, 'utf8'));
  await p.evaluate((x) => { resetSceneMemory(); pickScene(x); }, k);
  await L.settle(p); await p.evaluate(() => redrawAll()); await L.settle(p);
  const st = await p.evaluate(() => window.__RD.stateDump());
  const ans = await p.evaluate(() => window.__RD.answerOld());
  const d = L.stateDiff(rec.start.state, st);
  const real = Object.keys(d).filter(x => !VIEW.includes(x) && !/Sig$/.test(x)
    && !(x === 'areaHidden' && !(x in rec.start.state) && Array.isArray(st.areaHidden) && !st.areaHidden.length));
  const foreign = real.filter(x => !LABOR_OK.test(x));
  console.log(k + ': разошлись поля start.state: ' + (real.join(', ') || 'нет') + (foreign.length ? '  ⚠️ ВНЕ ТРУДА: ' + foreign.join(', ') : ''));
  real.forEach(x => console.log('    ' + x + ': ' + JSON.stringify(rec.start.state[x]).slice(0, 160) + '  →  ' + JSON.stringify(st[x]).slice(0, 160)));
  const oldRows = ((rec.start.answer.blocks || []).find(b => b.id === 'info-labor') || {}).rows || [];
  const newRows = ((ans.blocks || []).find(b => b.id === 'info-labor') || {}).rows || [];
  console.log('    «Ответ» было: ' + oldRows.map(r => r.label + ' = ' + r.value).join(' | '));
  console.log('    «Ответ» стало: ' + newRows.map(r => r.label + ' = ' + r.value).join(' | '));
  if (foreign.length) { stop = true; continue; }
  if (DRY) continue;
  real.forEach(x => { if (st[x] === undefined) delete rec.start.state[x]; else rec.start.state[x] = st[x]; });
  rec.start.answer = ans;
  // Причина и список полей — в журнале сессии (claude/PROGRESS_CALC2_LABOR_20261015.md), не в файле: новые ключи
  // в записи снимка читали бы приборы сверки.
  fs.writeFileSync(file, dump(rec));
}
await browser.close();
if (stop) { console.log('ОСТАНОВ: разошлись поля вне труда — эталоны этих ключей не переписаны'); process.exit(1); }
console.log(DRY ? 'сухой прогон: ничего не записано' : 'эталоны переписаны');
