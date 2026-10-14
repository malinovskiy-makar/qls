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
        CS; каждый щелчок — шаг истории; «Вид по умолчанию» — старт модели; (сессия 5, А3) у каждой строки «На
        графике» во всех моделях имя словами стоит левее обозначения, имя не начинается с запятой, строка не
        начинается обозначением («MC , предельные…», «TP (общий продукт)»);
     Г  (сессия 5, правка А1 по приёмке 14.10) «Отменить» с одного нажатия: в каждой модели щелчок человека по каждой
        строке «На графике» (галочка, строка закраски, тумблер заводов, глаз рыночных D и S, цвет f′, имя суммарной
        КПВ и Z) — ровно один новый шаг истории; одно «Отменить» (кнопка в шапке) возвращает состояние модели
        (histSig), картинку (пути холста) и сам орган; «Повторить» — обратно; на свежей модели после «Отменить»
        снова undo: false. Плюс сценарий владельца на свежей загрузке taxes: CS и DWL.

   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/view_probe.mjs [--only А,Г] [--before путь]
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
  // А3 (сессия 5): строки «На графике» — имя слева, обозначение справа (как в taxes и на макете 08_view_costs).
  const order = [];
  let nNamed = 0;
  for (const key of KEYS) {
    await pick(page, key);
    await openView(page);
    await page.waitForTimeout(150);
    const r = await page.evaluate(() => {
      const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
      const txt = (e) => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation, .crow-auto, .crow-more, .fc-menu, .crow-sliders').forEach(x => x.remove()); c.querySelectorAll('.katex').forEach(x => x.replaceWith('[' + x.textContent + ']')); return c.textContent.replace(/\s+/g, ' ').trim(); };
      const out = []; let n = 0;
      [...document.querySelectorAll('#wrench-pop .vg-onchart .vg-row')].filter(vis).forEach(row => {
        const t = txt(row);
        if (/^\[?[A-Za-zА-Я′ʹ'()₀-₉]{1,6}\]?\s*[,(]/.test(t)) out.push('строка начинается обозначением «' + t.slice(0, 30) + '»');
        const nm = [...row.querySelectorAll('.show-name, .fc-name')].find(vis);
        const nt = [...row.querySelectorAll('.show-not, .fc-notation')].find(e => vis(e) && e.textContent.trim());
        if (!nm) return;
        n++;
        const nmt = txt(nm);
        if (/^\s*,/.test(nmt)) out.push('имя с запятой «' + nmt.slice(0, 30) + '»');
        if (nt && nm.getBoundingClientRect().left >= nt.getBoundingClientRect().left) out.push('обозначение левее имени «' + t.slice(0, 30) + '»');
        if (nt && (nm.compareDocumentPosition(nt) & Node.DOCUMENT_POSITION_PRECEDING) && getComputedStyle(nt).order <= getComputedStyle(nm).order) out.push('узел обозначения раньше имени «' + t.slice(0, 30) + '»');
      });
      return { out, n };
    });
    nNamed += r.n;
    r.out.forEach(x => order.push(key + ': ' + x));
    await closeView(page);
  }
  ok('строк «На графике» с именем ' + nNamed + ': имя словами левее обозначения, без запятой впереди', nNamed > 0 && !order.length, order.slice(0, 8).join(' | '));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* Г. «Отменить» с одного нажатия (сессия 5, А1). Щелчки — настоящие (page.click / mouse): только они ставят метку
   «действие человека», и только так видно, что щелчок по «Отменить» закрывает «Вид графика». */
const ROW_SEL = '#wrench-pop .vg-onchart .vg-row';
async function rowsOf(page) {
  return page.evaluate((sel) => {
    const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
    return [...document.querySelectorAll(sel)].map((r, i) => {
      if (!vis(r)) return null;
      const has = (q) => [...r.querySelectorAll(q)].some(vis);
      const kind = r.querySelector('input[type=checkbox]') && vis(r.querySelector('input[type=checkbox]').closest('label') || r) ? 'chk'
        : has('.tgl-sw') ? 'tgl' : has('.fc-eye') ? 'eye' : has('.cpick-btn') ? 'color' : has('.edval-text') ? 'name' : null;
      return kind ? { i, kind, name: r.textContent.replace(/\s+/g, ' ').trim().slice(0, 40) } : null;
    }).filter(Boolean);
  }, ROW_SEL);
}
const snapOf = (page) => page.evaluate(() => ({
  sig: histSig(collectModelState()),
  /* Картинка — набор путей холста (закраска, заливка, линия, видимость), без длины записи d: окно после перерисовки
     то же, а числа в d округляются по-разному. */
  pic: [...document.querySelectorAll('#chart path')].filter(p => !p.closest('[data-service]')).map(p => (p.getAttribute('data-legend') || '') + '|' + (p.getAttribute('fill') || p.style.fill || '') + '|' + (p.getAttribute('stroke') || p.style.stroke || '') + '|' + getComputedStyle(p).display + getComputedStyle(p).opacity).sort().join(';'),
  can: historyCan(), undo: histOf().undo.length,
}));
function sigDiff(a, b) {
  const x = JSON.parse(a), y = JSON.parse(b), out = [];
  [0, 1].forEach(i => new Set([...Object.keys(x[i]), ...Object.keys(y[i])]).forEach(k => {
    if (JSON.stringify(x[i][k]) !== JSON.stringify(y[i][k])) out.push(k + ' ' + String(JSON.stringify(x[i][k])).slice(0, 60) + ' → ' + String(JSON.stringify(y[i][k])).slice(0, 60));
  }));
  return ' (' + out.slice(0, 3).join('; ') + ')';
}
async function actOnRow(page, row) {
  const base = ROW_SEL + ':nth-child(' + 0 + ')';
  const h = await page.evaluateHandle(([sel, i]) => document.querySelectorAll(sel)[i], [ROW_SEL, row.i]);
  const el = h.asElement();
  if (row.kind === 'chk') { const inp = await el.$('input[type=checkbox]'); await inp.click({ force: true }); }
  else if (row.kind === 'tgl') { const t = await el.$('.tgl-sw'); await t.click(); }
  else if (row.kind === 'eye') { const t = await el.$('.fc-eye'); await t.click(); }
  else if (row.kind === 'color') {
    const t = await el.$('.cpick-btn'); await t.click();
    await page.waitForTimeout(150);
    const sw = await page.$('.cpick-menu .cpick-sw[aria-checked="false"]');
    if (sw) await sw.click();
  } else if (row.kind === 'name') {
    const t = await el.$('.edval-text'); await t.click();
    await page.waitForTimeout(150);
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
    await page.keyboard.type('Имя проверки');
    await page.keyboard.press('Enter');
  }
  void base;
}
async function sectionG() {
  head('Г. «Отменить» с одного нажатия: каждая строка «На графике»');
  const { ctx, page, errors } = await openPage();
  const bads = [];
  let nRows = 0;
  const kinds = {};
  for (const key of KEYS) {
    await pick(page, key);
    await page.click('#btn-view'); await page.waitForTimeout(200);
    const rows = await rowsOf(page);
    await page.click('#btn-view'); await page.waitForTimeout(150);
    for (const row of rows) {
      /* Каждая строка — на свежей загрузке модели по адресу (как у человека): после pickScene из другой модели в
         форме остаются узлы её списка кривых, и сравнение состояний «до» и «после «Отменить» шумело бы. */
      await page.evaluate(() => resetSceneMemory());
      await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'load', timeout: 40000 });
      await page.waitForFunction((k) => typeof pickScene === 'function' && typeof modelKeyOf === 'function' && modelKeyOf() === k, key, { timeout: 40000 });
      await page.waitForTimeout(700);
      await page.click('#btn-view'); await page.waitForTimeout(250);
      const s0 = await snapOf(page);
      const tag = key + ' «' + row.name + '» (' + row.kind + ')';
      if (s0.can.undo) { bads.push(tag + ': на свежей модели undo: true'); continue; }
      await actOnRow(page, row);
      await page.waitForTimeout(800);
      const s1 = await snapOf(page);
      nRows++; kinds[row.kind] = (kinds[row.kind] || 0) + 1;
      if (s1.undo !== s0.undo + 1) { bads.push(tag + ': шагов истории ' + (s1.undo - s0.undo)); continue; }
      if (s1.sig === s0.sig) { bads.push(tag + ': щелчок не изменил состояние'); continue; }
      await page.click('#btn-undo'); await page.waitForTimeout(800);
      const s2 = await snapOf(page);
      if (s2.sig !== s0.sig) bads.push(tag + ': одно «Отменить» не вернуло состояние' + sigDiff(s0.sig, s2.sig));
      if (s2.pic !== s0.pic) bads.push(tag + ': одно «Отменить» не вернуло картинку');
      if (s2.can.undo) bads.push(tag + ': после «Отменить» на свежей модели undo: true');
      if (!s2.can.redo) { bads.push(tag + ': «Повторить» выключена'); continue; }
      await page.click('#btn-redo'); await page.waitForTimeout(800);
      const s3 = await snapOf(page);
      if (s3.sig !== s1.sig) bads.push(tag + ': «Повторить» не вернула правку');
      if (s3.pic !== s1.pic) bads.push(tag + ': «Повторить» не вернула картинку');
    }
  }
  ok('строк «На графике» проверено ' + nRows + ' ' + JSON.stringify(kinds) + ': один щелчок — один шаг; одно «Отменить» возвращает состояние, картинку и орган; «Повторить» — обратно', nRows > 0 && !bads.length, bads.length + ': ' + bads.slice(0, 8).join(' | '));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
  // Сценарий владельца на свежей загрузке: taxes, «Излишек потребителя» и «Потери общества».
  for (const [label, sel, probe] of [['«Излишек потребителя» (chk-cs)', '#chk-cs', 'STATE.showCS'],
    ['«Потери общества» (areaHidden)', '#wrench-pop .vg-gen[data-key="Потери общества (DWL)"] input', "!STATE.areaHidden.includes('Потери общества (DWL)')"]]) {
    const P = await openPage(BASE + '/calc2/?m=taxes');
    await P.page.waitForTimeout(800);
    const c0 = await P.page.evaluate(() => historyCan());
    await P.page.click('#btn-view'); await P.page.waitForTimeout(300);
    await P.page.click(sel, { force: true }); await P.page.waitForTimeout(800);
    const c1 = await P.page.evaluate((x) => ({ can: historyCan(), on: eval(x), dwl: document.querySelectorAll('#chart [data-legend="Потери общества (DWL)"]').length }), probe);
    await P.page.click('#btn-undo'); await P.page.waitForTimeout(800);
    const c2 = await P.page.evaluate((x) => ({ can: historyCan(), on: eval(x), dwl: document.querySelectorAll('#chart [data-legend="Потери общества (DWL)"]').length }), probe);
    ok('свежая загрузка taxes, ' + label + ': до щелчка undo:false, после — undo:true, одно «Отменить» вернуло признак, undo:false',
      !c0.undo && c1.can.undo && !c1.on && c2.on && !c2.can.undo && c2.can.redo && c2.dwl > 0, JSON.stringify({ c0, c1, c2 }));
    await P.ctx.close();
  }
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
  if (want('Г')) await sectionG();
  await browser.close();
}
console.log('\nИТОГ view_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
