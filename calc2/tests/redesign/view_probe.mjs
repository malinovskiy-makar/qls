/* «ВИД ГРАФИКА»: «НА ГРАФИКЕ» (тихие панели, этап Г, 14.10.2026; решение владельца «левая панель только про
   условие, всё, что меняет одну картинку, — в «Вид»», Notion …8142…; ADR 0152; README пакета 4, 7).

   Разделы (--only А,Б,В):
     А  42 модели: множество видимых галочек картинки «до» (в «Условии», опись claude/panels_night/C_after.json)
        = множество в «Виде графика» сейчас, по id (кроме мёртвых chk-cs / chk-ps рынка труда и
        дискриминации 1-й степени — D_allow); в «Условии» галочек картинки 0; условия (меняют числа) — на месте;
     Б  каждая закраска на старте каждой модели и в состояниях taxes субсидия, ceil пол, mono налог 20 и квота,
        smallopen тариф и квота: строка «Вида» есть; снял → путей с этим data-legend 0, в легенде нет, в файле
        .tex (buildTex) нет; вернул → как было; в labor снятая «Излишек фирм» прячет закраску;
     В  ссылка «Поделиться» туда и обратно для каждой переехавшей галочки и для areaHidden; старая ссылка с
        showCS: false (снята на коммите до этапа Г, claude/panels_night/old_link_taxes_showCS_false.txt) прячет
        CS; каждый щелчок — шаг истории; «Вид по умолчанию» — старт модели.

   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/view_probe.mjs [--only А] [--before путь]
   ENGINES=chromium,webkit (по умолчанию оба). Код 0 — всё сошлось.          */
import * as pw from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..', '..');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);
const ENGINES = (process.env.ENGINES || 'chromium,webkit').split(',').filter(Boolean);
const BEFORE = arg('before', path.join(ROOT, 'claude', 'panels_night', 'C_after.json'));
const OLD_LINK = path.join(ROOT, 'claude', 'panels_night', 'old_link_taxes_showCS_false.txt');
const ALL = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer';
const KEYS = (process.env.KEYS || ALL).split(/\s+/).filter(Boolean);
// Галочки картинки (переезжают) и условия (остаются в «Условии»): README 7, data/toggles_a95cae66.md.
const PICTURE = ['chk-tp', 'chk-mp', 'chk-ap', 'chk-mc', 'chk-atc', 'chk-avc', 'chk-afc', 'chk-tc', 'chk-vc', 'chk-fc',
  'chk-convex', 'chk-inflect', 'chk-iso-fan', 'chk-cons-fan', 'chk-cs', 'chk-ps', 'chk-mono-cs', 'chk-mono-ps',
  'chk-mono-vc', 'chk-nat-profit', 'chk-nat-loss', 'chk-open-money', 'chk-open-dwl', 'chk-ppf-in', 'chk-ppf-out',
  'chk-lr-area', 'chk-ghost', 'chk-lab-ghost'];
const CONDITION = ['chk-secant', 'chk-bundle-1', 'chk-bundle-2', 'chk-bundle-t', 'chk-elast-s', 'chk-msb', 'chk-msc',
  'ext-pigou', 'chk-lr', 'chk-labmin', 'ma-fx-fixed', 'ineq-redist'];
// D_allow: мёртвые галочки (сцена их не читала) — их строки заменили строки закрасок.
const DEAD = { labor: ['chk-cs', 'chk-ps'], 'labor-mono': ['chk-cs', 'chk-ps'], 'mono-d1': ['chk-cs', 'chk-ps'] };

let bad = 0, total = 0, eng = '';
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' [' + eng + '] ' + label + (detail && !cond ? '  — ' + detail : ''));
}
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));
let browser = null;
async function openPage(url) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript(() => { try { if (sessionStorage.getItem('__vp')) return; sessionStorage.setItem('__vp', '1'); localStorage.clear(); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(url || BASE + '/calc2/', { waitUntil: 'load', timeout: 40000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 40000 });
  await page.waitForTimeout(400);
  return { ctx, page, errors };
}
async function pick(page, key, extra) {
  await page.evaluate(([k, x]) => { resetSceneMemory(); pickScene(k); closePicker(); if (x) (new Function(x))(); redrawAll(); }, [key, extra || '']);
  await page.waitForTimeout(450);
}
const openView = (page) => page.evaluate(() => { const w = document.getElementById('wrench-pop'); if (!w.classList.contains('open')) document.getElementById('btn-view').click(); });
const closeView = (page) => page.evaluate(() => { const w = document.getElementById('wrench-pop'); if (w.classList.contains('open')) document.getElementById('btn-view').click(); });

async function sectionA() {
  head('А. Галочки картинки переехали в «Вид», условия на месте');
  const before = JSON.parse(fs.readFileSync(BEFORE, 'utf8')).models;
  const { ctx, page, errors } = await openPage();
  const diff = [], left = [], cond = [];
  for (const key of KEYS) {
    await pick(page, key);
    await openView(page);
    await page.waitForTimeout(150);
    const now = await page.evaluate(([P, C]) => {
      const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
      const shown = (id) => { const e = document.getElementById(id); if (!e) return false; const box = e.type === 'checkbox' ? (e.closest('label') || e) : e; return vis(box); };
      const view = P.filter(id => { const e = document.getElementById(id); return e && e.closest('#wrench-pop .vg-onchart') && shown(id); });
      const leftPic = P.filter(id => { const e = document.getElementById(id); return e && e.closest('#tools-panel') && shown(id); });
      const condLeft = C.filter(id => { const e = document.getElementById(id); return e && e.closest('#tools-panel') && shown(id); });
      return { view, leftPic, condLeft };
    }, [PICTURE, CONDITION]);
    await closeView(page);
    const b = before[key];
    const was = new Set(b.left.filter(c => c.type === 'checkbox' && PICTURE.includes(c.id)).map(c => c.id));
    (DEAD[key] || []).forEach(id => was.delete(id));
    const nowSet = new Set(now.view);
    const miss = [...was].filter(id => !nowSet.has(id)), extra = [...nowSet].filter(id => !was.has(id));
    if (miss.length || extra.length) diff.push(key + ': нет ' + miss.join(',') + ' / лишние ' + extra.join(','));
    if (now.leftPic.length) left.push(key + ': ' + now.leftPic.join(','));
    const condWas = b.left.filter(c => CONDITION.includes(c.id)).map(c => c.id);
    const lost = condWas.filter(id => !now.condLeft.includes(id));
    if (lost.length) cond.push(key + ': ' + lost.join(','));
  }
  ok(KEYS.length + ' моделей: галочки картинки «до» (Условие) = «после» (Вид), по id', !diff.length, diff.slice(0, 6).join(' | '));
  ok('в «Условии» галочек картинки 0', !left.length, left.slice(0, 6).join(' | '));
  ok('условия (меняют числа «Ответа») на месте, в «Условии»', !cond.length, cond.slice(0, 6).join(' | '));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* Закраски: строка у каждой, снятие прячет путь, легенду и .tex, возврат возвращает. */
async function areasCase(page, label) {
  return page.evaluate(async (label) => {
    const out = [];
    const keysDrawn = () => { const s = new Set(); document.querySelectorAll('#chart [data-legend]').forEach(e => s.add(e.getAttribute('data-legend').trim())); return s; };
    const own = new Set((STATE.areaCalcList || []).map(r => String(r.label).trim()));
    const drawn = [...keysDrawn()].filter(k => !own.has(k));
    const w = document.getElementById('wrench-pop');
    if (!w.classList.contains('open')) document.getElementById('btn-view').click();
    await new Promise(r => setTimeout(r, 120));
    const rows = [...w.querySelectorAll('.vg-onchart .vg-row.vg-area')].filter(r => !r.hidden);
    const rowFor = (k) => rows.find(r => (r.dataset.key === k) || ((typeof _vgRows !== 'undefined') && _vgRows.some(x => x.row === r && x.covers.indexOf(k) >= 0)));
    const legend = () => [...document.querySelectorAll('#chart .legend title')].map(t => t.textContent.trim());
    const tex = async () => { try { const t = await buildTex('t', 'x'); return typeof t === 'string' ? t : ''; } catch (e) { return ''; } };
    for (const k of drawn) {
      const r = rowFor(k);
      if (!r) { out.push(label + ': нет строки «' + k + '»'); continue; }
      const chk = r.querySelector('input[type=checkbox]');
      const n0 = document.querySelectorAll('#chart [data-legend="' + CSS.escape(k) + '"]').length;
      /* В .tex закраска — путь с записью и строка легенды (полное имя или обозначение): после снятия число
         упоминаний обязано упасть, а полного имени — не остаться вовсе. */
      const short = (typeof areaShort === 'function') ? areaShort(k) : k;
      const cnt = (t) => t.split(k).length - 1 + (short !== k ? t.split(short).length - 1 : 0);
      const t0 = await tex();
      chk.click();
      await new Promise(res => setTimeout(res, 350));
      const n1 = document.querySelectorAll('#chart [data-legend="' + CSS.escape(k) + '"]').length;
      const inLeg = legend().includes(k);
      const t = await tex();
      const inTex = t.indexOf(k) >= 0 || !(cnt(t) < cnt(t0) || cnt(t0) === 0) || t.length >= t0.length;
      if (n1 !== 0) out.push(label + ': снял «' + k + '» — путей ' + n1);
      if (inLeg) out.push(label + ': снял «' + k + '» — в легенде');
      if (inTex) out.push(label + ': снял «' + k + '» — в .tex');
      chk.click();
      await new Promise(res => setTimeout(res, 350));
      const n2 = document.querySelectorAll('#chart [data-legend="' + CSS.escape(k) + '"]').length;
      if (n2 !== n0) out.push(label + ': вернул «' + k + '» — путей ' + n2 + ' из ' + n0);
    }
    document.getElementById('btn-view').click();
    return { out, drawn };
  }, label);
}

async function sectionB() {
  head('Б. Строка «Вида» у каждой закраски; снять / вернуть');
  const { ctx, page, errors } = await openPage();
  const bads = [];
  let nAreas = 0;
  const run = async (key, extra, label) => {
    await pick(page, key, extra);
    const r = await areasCase(page, label || key);
    nAreas += r.drawn.length;
    r.out.forEach(x => bads.push(x));
  };
  for (const key of KEYS) await run(key);
  await run('taxes', "setType('subsidy'); setTax(20);", 'taxes субсидия');
  await run('ceil', "setType('floor'); setPReg(70);", 'ceil пол');
  await run('mono', "setType('tax'); setTax(20);", 'mono налог 20');
  await run('mono', "setType('quota'); setQuota(20);", 'mono квота');
  await run('smallopen', "setOpenPw(30); setOpenTool('tariff'); STATE.openTariff = 5;", 'smallopen тариф');
  await run('smallopen', "setOpenPw(30); setOpenTool('quota'); STATE.openQuota = 20;", 'smallopen квота');
  ok('закрасок проверено ' + nAreas + ': у каждой строка; снял — нет на холсте, в легенде и в .tex; вернул — как было', !bads.length, bads.length + ': ' + bads.slice(0, 8).join(' | '));
  // Рынок труда: «Излишек фирм» прячется (раньше галочки CS / PS там ничего не делали).
  await pick(page, 'labor');
  const lab = await page.evaluate(async () => {
    document.getElementById('btn-view').click();
    await new Promise(r => setTimeout(r, 120));
    const r = [...document.querySelectorAll('#wrench-pop .vg-gen')].find(x => x.dataset.key === 'Излишек фирм');
    if (!r) return { err: 'нет строки «Излишек фирм»' };
    r.querySelector('input').click();
    await new Promise(res => setTimeout(res, 350));
    return { paths: document.querySelectorAll('#chart [data-legend="Излишек фирм"]').length, deadCS: !!(document.getElementById('show-cs-row') && !document.getElementById('show-cs-row').closest('.vg-row').hidden) };
  });
  ok('labor: снятая «Излишек фирм» прячет закраску; мёртвой строки CS нет', lab.paths === 0 && !lab.deadCS, JSON.stringify(lab));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

async function sectionV() {
  head('В. Ссылка, история, «Вид по умолчанию», старая ссылка');
  const { ctx, page, errors } = await openPage();
  // Переехавшие галочки: в модели, где галочка видна, щелчок — шаг истории; ссылка несёт её состояние туда и обратно.
  const where = { 'chk-cs': 'taxes', 'chk-ps': 'taxes', 'chk-ghost': 'taxes', 'chk-mono-cs': 'mono', 'chk-mono-ps': 'mono', 'chk-mono-vc': 'mono',
    'chk-nat-profit': 'mono-nat', 'chk-nat-loss': 'mono-nat', 'chk-open-money': 'smallopen', 'chk-open-dwl': 'smallopen', 'chk-ppf-in': 'ppf',
    'chk-ppf-out': 'ppf', 'chk-lr-area': 'costs', 'chk-mc': 'costs', 'chk-tc': 'costs', 'chk-tp': 'prod', 'chk-ap': 'prod', 'chk-iso-fan': 'isoquant',
    'chk-cons-fan': 'consumer', 'chk-convex': 'm-optimum', 'chk-inflect': 'm-optimum', 'chk-lab-ghost': 'labor' };
  const res = [];
  for (const [id, key] of Object.entries(where)) {
    await pick(page, key);
    await openView(page);
    await page.waitForTimeout(120);
    const u0 = await page.evaluate(() => histOf().undo.length);
    const sel = '#' + id;
    const box = await page.evaluate((s) => { const e = document.querySelector(s); const l = e && (e.closest('label') || e); return !!(l && l.getClientRects().length); }, sel);
    if (!box) { res.push(id + ' (' + key + '): не видна в «Виде»'); await closeView(page); continue; }
    const was = await page.evaluate((s) => document.querySelector(s).checked, sel);
    await page.click(sel);
    await page.waitForTimeout(700);
    const st = await page.evaluate(async (s) => ({ undo: histOf().undo.length, checked: document.querySelector(s).checked, link: await shareLinkOf() }), sel);
    if (st.undo !== u0 + 1) res.push(id + ': щелчок — шагов истории ' + (st.undo - u0));
    // Ссылка туда и обратно: новая страница по ссылке, галочка в том же положении.
    const P = await openPage(st.link);
    await P.page.waitForTimeout(500);
    const back = await P.page.evaluate((s) => { const e = document.querySelector(s); return e ? e.checked : null; }, sel);
    if (back !== st.checked || back === was) res.push(id + ': по ссылке ' + back + ', ожидалось ' + st.checked);
    await P.ctx.close();
    await closeView(page);
  }
  ok('переехавшие галочки: щелчок — шаг истории, ссылка туда и обратно (' + Object.keys(where).length + ')', !res.length, res.slice(0, 6).join(' | '));
  // areaHidden: ссылка туда и обратно, шаг истории.
  await pick(page, 'taxes');
  await openView(page);
  await page.waitForTimeout(150);
  const ah = await page.evaluate(() => ({ u0: histOf().undo.length }));
  await page.click('#wrench-pop .vg-gen[data-key="Потери общества (DWL)"] input');
  await page.waitForTimeout(700);
  const ah2 = await page.evaluate(async () => ({ hidden: STATE.areaHidden.slice(), undo: histOf().undo.length, link: await shareLinkOf() }));
  const P2 = await openPage(ah2.link);
  await P2.page.waitForTimeout(600);
  const back2 = await P2.page.evaluate(() => ({ hidden: STATE.areaHidden.slice(), paths: document.querySelectorAll('#chart [data-legend="Потери общества (DWL)"]').length }));
  await P2.ctx.close();
  ok('areaHidden: ссылка туда и обратно (DWL спрятана и по ссылке)', JSON.stringify(back2.hidden) === JSON.stringify(ah2.hidden) && back2.paths === (ah2.hidden.includes('Потери общества (DWL)') ? 0 : back2.paths), JSON.stringify({ ah2: ah2.hidden, back2 }));
  ok('areaHidden: щелчок — шаг истории', ah2.undo > ah.u0, JSON.stringify({ was: ah.u0, now: ah2.undo }));
  // «Вид по умолчанию» — к старту модели: areaHidden пуст, CS и «было → стало» на старте.
  await page.evaluate(() => { const c = document.getElementById('chk-cs'); if (c.checked) c.click(); const g = document.getElementById('chk-ghost'); if (!g.checked) g.click(); });
  await page.waitForTimeout(500);
  await page.evaluate(() => document.getElementById('view-defaults').click());
  await page.waitForTimeout(700);
  const vd = await page.evaluate(() => ({ hidden: STATE.areaHidden, cs: STATE.showCS, chk: document.getElementById('chk-cs').checked, ghost: STATE.showGhost, g: document.getElementById('chk-ghost').checked, dwl: document.querySelectorAll('#chart [data-legend="Потери общества (DWL)"]').length }));
  ok('«Вид по умолчанию»: «На графике» — к старту модели', vd.hidden.length === 0 && vd.cs === true && vd.chk === true && !vd.ghost && !vd.g && vd.dwl > 0, JSON.stringify(vd));
  await closeView(page);
  // Старая ссылка (до этапа Г) с showCS: false прячет CS.
  if (fs.existsSync(OLD_LINK)) {
    const link = fs.readFileSync(OLD_LINK, 'utf8').trim().replace(/^https?:\/\/[^/]+/, BASE);
    const P3 = await openPage(link);
    await P3.page.waitForTimeout(600);
    const o = await P3.page.evaluate(() => ({ show: STATE.showCS, chk: document.getElementById('chk-cs').checked, paths: document.querySelectorAll('#chart [data-legend="Излишек потребителя (CS)"]').length }));
    await P3.ctx.close();
    ok('старая ссылка с showCS: false — CS спрятан, галочка снята', o.show === false && o.chk === false && o.paths === 0, JSON.stringify(o));
  } else ok('старая ссылка с showCS: false есть', false, 'нет файла ' + OLD_LINK);
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

for (const name of ENGINES) {
  eng = name;
  try { browser = await pw[name].launch(); } catch (e) {
    console.log('\n!!! ' + name + ': движок не запустился — НЕ ПРОВЕРЕНО (' + String(e).slice(0, 120) + ')');
    continue;
  }
  if (want('А')) await sectionA();
  if (want('Б')) await sectionB();
  if (want('В')) await sectionV();
  await browser.close();
}
console.log('\nИТОГ view_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
