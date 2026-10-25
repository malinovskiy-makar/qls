// А2 24.10 (ADR 0158): переписать эталоны СТАРТА двух моделей, чей старт сменили решения владельца, — тем же
// способом, что claude/calc2_labor/rewrite_baselines.mjs (копия с другими ключами и списком полей):
//   ext   — MSC = Q + 20 и видна (решение …81e7…): поля msbOn, mscOn, msbExpr, mscExpr, msbCompiled, mscCompiled, ext;
//   quota — цена внутри коридора по умолчанию — цена спроса (…81e0…9219…): поля quotaPos, qt.
// В start.state — ТОЛЬКО разошедшиеся поля; поле вне списка модели — останов без записи. start.answer — целиком.
//   node claude/calc2_a2/rewrite_start_baselines.mjs [--dry] [--keys ext]
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
const KEYS = ki >= 0 ? argv[ki + 1].split(',') : ['ext', 'quota'];
// Производное от размера холста — session_probe §8 его не сравнивает (тот же список).
const VIEW = ['crosses', 'sceneKey', 'legendSpot', 'tanTop', 'tanBot'];
// Поля, которые вправе разойтись: только те, что задают решения сессии у своей модели.
const OK_BY_KEY = { ext: /^(msbOn|mscOn|msbExpr|mscExpr|msbCompiled|mscCompiled|ext)$/, quota: /^(quotaPos|qt)$/ };

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
  const foreign = real.filter(x => !(OK_BY_KEY[k] || /^$/).test(x));
  console.log(k + ': разошлись поля start.state: ' + (real.join(', ') || 'нет') + (foreign.length ? '  ⚠️ ВНЕ СПИСКА: ' + foreign.join(', ') : ''));
  real.forEach(x => console.log('    ' + x + ': ' + JSON.stringify(rec.start.state[x]).slice(0, 160) + '  →  ' + JSON.stringify(st[x]).slice(0, 160)));
  const rowsOf = (a) => (a.blocks || []).map(b => b.id + ': ' + (b.rows || []).map(r => r.label + ' = ' + r.value).join(' | ')).join(' ‖ ');
  console.log('    «Ответ» было: ' + rowsOf(rec.start.answer));
  console.log('    «Ответ» стало: ' + rowsOf(ans));
  if (foreign.length) { stop = true; continue; }
  if (DRY) continue;
  real.forEach(x => { if (st[x] === undefined) delete rec.start.state[x]; else rec.start.state[x] = st[x]; });
  rec.start.answer = ans;
  // Причина и список полей — в журнале сессии (claude/calc2_a2/README.md), не в файле.
  fs.writeFileSync(file, dump(rec));
}
await browser.close();
if (stop) { console.log('ОСТАНОВ: разошлись поля вне списка — эталоны этих ключей не переписаны'); process.exit(1); }
console.log(DRY ? 'сухой прогон: ничего не записано' : 'эталоны переписаны');
