/* ПОРЯДОК ОТКРЫТИЯ И ПАМЯТЬ МОДЕЛИ (фаза 1 редизайна calc2).

   1. Одна страница обходит все 44 ключа ПОДРЯД, без перезагрузки и без
      resetSceneMemory: проход «вперёд» и проход «назад», где перед уходом из
      каждой модели в ней правится один вход. Старт каждой модели пишется в
      формате базового снимка (snapshot.mjs) в --out/forward и --out/reverse;
      сверка с базовым — compare.mjs --start-only. Модель обязана открываться
      одинаково при любом порядке.
   2. Память «ушёл и вернулся»: для каждого ключа один вход меняется (первый
      ползунок, числовое поле или поле формулы из базового снимка), затем уход в
      модель другой семьи, возврат — изменённое значение на месте (и в органе,
      и в STATE).

   node calc2/tests/redesign/order_probe.mjs --base calc2/tests/redesign/baseline --out reports/calc2_redesign/order
   Код возврата: 0 — память цела у всех ключей, 1 — нет (сверку стартов делает compare.mjs). */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE_URL = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BL = arg('base', path.join(HERE, 'baseline'));
const OUT = path.resolve(arg('out', 'reports/calc2_redesign/order'));
const LAYER = arg('layer', 'old');
const layer = await import(path.join(HERE, 'layer_' + LAYER + '.mjs'));
const INPAGE = fs.readFileSync(path.join(HERE, 'inpage.js'), 'utf8');
const KEYS = fs.readdirSync(BL).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5));
const BLR = Object.fromEntries(KEYS.map(k => [k, JSON.parse(fs.readFileSync(path.join(BL, k + '.json'), 'utf8'))]));
// Порядок карточек окна выбора — порядок SCENE_ROUTE.
const browser = await chromium.launch();

async function freshPage() {
  const ctx = await browser.newContext({ viewport: { width: 1324, height: 638 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
  const page = await ctx.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 300)));
  await page.goto(BASE_URL + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
  await page.addScriptTag({ content: INPAGE });
  await page.evaluate((l) => { window.__RD_LAYER = l; }, LAYER);
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  return { ctx, page, errors };
}
async function settle(page) {
  const t0 = Date.now();
  while (Date.now() - t0 < 6000) { if (await page.evaluate(() => window.__RD.settled())) break; await page.waitForTimeout(60); }
  await page.waitForTimeout(330);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
}
async function enter(page, key) {
  await layer.enter(page, key);
  await settle(page);
  await page.evaluate(() => redrawAll());
  await settle(page);
  await layer.expand(page);
  await settle(page);
}
async function observe(page) {
  const [state, windows, geometry, controls] = await page.evaluate(() => [
    window.__RD.stateDump(), window.__RD.windows(), window.__RD.geometry(false), window.__RD.controls()]);
  const answer = await layer.answer(page);
  return { state, windows, geometry, controls, answer };
}

/* Вход, который правится в модели: первый шаг базового снимка первого
   уровня над ползунком, числом или формулой с эффектом на модель. */
function editOf(key) {
  const b = BLR[key];
  const st = (b.steps || []).find(s => s.path.length === 1 && s.effect === 'model' && /input:range|input:number|math-field/.test(s.kind)
    && !/^#(tools|params)-toggle/.test(s.path[0]));
  if (!st) return null;
  return (b.controls || []).find(c => c.key === st.path[0]) || null;
}
async function doEdit(page, c) {
  const h = (await page.evaluateHandle(k => window.__RD.findControl(k), layer.mapKey(c.key))).asElement();
  if (!h) return 'не найден';
  if (c.kind === 'input:range') { await h.focus(); for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight'); return 'ArrowRight×3'; }
  if (c.kind === 'math-field') {
    await h.evaluate(mf => mf.focus()); await page.waitForTimeout(150);
    await h.evaluate(mf => mf.executeCommand('moveToMathfieldEnd')); await page.waitForTimeout(50);
    await page.keyboard.type('+5', { delay: 30 }); await page.waitForTimeout(350);
    await layer.afterFormula(page, c.key);
    return '+5';
  }
  await h.click({ clickCount: 3 }); await page.keyboard.press('Meta+A'); await page.keyboard.type('7,5'); await page.keyboard.press('Enter');
  return '7,5';
}
const OTHER = (key) => /^(sd|sdsum|tax|taxes|tax-adv|ceil|quota|elast|ext|smallopen|monoexport|mono)/.test(key) ? 'm-graph' : 'sd';

function dump(dir, key, o) {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, key + '.json'), JSON.stringify({ key, layer: LAYER, start: { state: o.state, windows: o.windows, answer: o.answer, geometry: o.geometry }, controls: o.controls, errors: o.errors || [] }) + '\n');
}

const order = await (async () => { const f = await freshPage(); const k = await f.page.evaluate(() => Object.keys(SCENE_ROUTE)); await f.ctx.close(); return k.filter(x => KEYS.includes(x)); })();
// 1. Вперёд.
let f = await freshPage();
for (const key of order) { await enter(f.page, key); dump(path.join(OUT, 'forward'), key, { ...(await observe(f.page)), errors: f.errors.splice(0) }); }
await f.ctx.close();
// 1. Назад, с правкой перед уходом.
f = await freshPage();
for (const key of [...order].reverse()) {
  await enter(f.page, key);
  dump(path.join(OUT, 'reverse'), key, { ...(await observe(f.page)), errors: f.errors.splice(0) });
  const c = editOf(key);
  if (c) { try { await doEdit(f.page, c); await settle(f.page); } catch (e) {} }
}
await f.ctx.close();
// 2. Память.
const mem = [];
let bad = 0;
for (const key of order) {
  const c = editOf(key);
  if (!c) { mem.push([key, 'нет правимого входа в базовом снимке']); continue; }
  const p = await freshPage();
  await enter(p.page, key);
  const act = await doEdit(p.page, c);
  await settle(p.page);
  const after = await observe(p.page);
  await enter(p.page, OTHER(key));
  await enter(p.page, key);
  const back = await observe(p.page);
  /* Строки «Построения графиков» нумеруются счётчиком и при каждой пересборке
     получают новые id (graph-f-1 → graph-f-5): орган ищется по образцу ключа
     и по порядку среди таких же. */
  const pat = new RegExp('^' + c.key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\d+/g, '\\d+') + '$');
  const pick = (list) => list.find(x => x.key === c.key) || list.filter(x => pat.test(x.key))[0];
  const ca = pick(after.controls), cb = pick(back.controls);
  const sameCtl = JSON.stringify(ca && ca.props) === JSON.stringify(cb && cb.props);
  const diff = Object.keys(after.state).filter(k => JSON.stringify(after.state[k]) !== JSON.stringify(back.state[k]) && !/crosses|viewDirty|legendSpot|Sig$/.test(k));   // подписи кэшей и место легенды — не входы
  const ab = after.answer.blocks || [], bb = back.answer.blocks || [];
  // Значения сравниваются без пробелов: KaTeX набирает «(105; 0)» как «(105;0)».
  const norm = (b) => b ? JSON.stringify(b).replace(/\s|\\u200b|\u200b/g, '') : '';
  const blk = ab.map(x => x.id).filter(id => norm(ab.find(y => y.id === id)) !== norm(bb.find(y => y.id === id)));
  const ok = sameCtl && !diff.length && !blk.length;
  if (blk.length) {
    const A = ab.find(y => y.id === blk[0]), B = bb.find(y => y.id === blk[0]) || { rows: [], notes: [] };
    const rd = A.rows.filter((r, i) => JSON.stringify(r) !== JSON.stringify(B.rows[i])).map(r => r.label + ' ' + r.value + ' → ' + ((B.rows.find(x => x.i === r.i) || {}).value));
    const nd = A.notes.filter(t => !B.notes.includes(t)).map(t => 'пояснение «' + t.slice(0, 60) + '»');
    diff.push('ответ ' + blk.join(', ') + ': ' + rd.concat(nd).join('; ').slice(0, 400));
  }
  if (!ok) bad++;
  mem.push([key, (ok ? 'ok' : 'ПОТЕРЯ') + ' · ' + c.key + ' (' + act + ')' + (sameCtl ? '' : ' орган ' + JSON.stringify(ca && ca.props) + ' → ' + JSON.stringify(cb && cb.props)) + (diff.length ? ' STATE: ' + diff.slice(0, 6).join(', ') : '')]);
  await p.ctx.close();
}
await browser.close();
fs.writeFileSync(path.join(OUT, 'memory.txt'), mem.map(x => x.join(': ')).join('\n') + '\n');
mem.forEach(x => console.log((x[1].startsWith('ok') ? '✓ ' : (x[1].startsWith('ПОТЕРЯ') ? '✗ ' : '· ')) + x[0] + ': ' + x[1]));
console.log(`\nпамять: потерь ${bad} из ${mem.length}`);
process.exit(bad ? 1 : 0);
