/* ТИШИНА И ШРИФТЫ (тихие панели, этап В, 14.10.2026; решения владельца «никаких подсказок» Notion …81eb… и
   «шрифт панелей — вариант A» …81d6…; ADR 0151; пакет claude/mockups/calc2_panels_20261014, README 3, 4, 6).

   Разделы (--only А,Ш,К):
     А  42 модели: наведение и фокус с клавиатуры на КАЖДЫЙ узел с data-tip в «Условии», шапке модели, панели
        холста, «Ответе» и окне «Вид графика» — плашка #hint-tip не видна ни разу; у каждого такого узла непустой
        aria-label; видимых .hint-btn, .hint-row, .help-dot, #btn-howto — 0; каждый абзац .hint «Условия» и
        абзац плашки с data-explain — в «Разборе» своей модели; окно клавиатуры поля в sd, ppf,
        m-graph содержит раздел «Как писать» из 9 строк;
     Ш  шрифты: в «Условии», панели «Точки и площади» и окне «Вид графика» всех 42 моделей каждый видимый текст —
        одна из ступеней 18/600, 14/600, 14/500, 14/400, 13/600, 12/500, шрифт Montserrat (KaTeX и MathLive не
        считаются); узлов с моноширинным шрифтом вне окна клавиатуры — 0; зазор подпись → поле ≥ 6 px;
     К  тёмная тема: фон полей и списков «Условия» #232019; «Сдвиг MC» в mono, mono-nat, mono-d1 без индекса
        (нет .msupsub), у smallopen «Pw» с индексом; в calc2.css нет #11151d;
     З  (сессия 5, правка А3 по приёмке 14.10) 42 модели и costs «Задам кривые»: в «Условии» нет видимого заголовка
        группы или раздела (h3.sec-head, .curve-group-title, .vsub, .section-title) без видимого органа под ним.

   ENGINES=chromium,webkit (по умолчанию оба). KEYS="sd taxes" — выборка моделей.
   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/quiet_probe.mjs [--only А,З]
   Код 0 — всё сошлось.                                                     */
import * as pw from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = (arg('only', '') || '').split(',').filter(Boolean);
const want = (s) => !ONLY.length || ONLY.includes(s);
const ENGINES = (process.env.ENGINES || 'chromium,webkit').split(',').filter(Boolean);
const ALL = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer';
const KEYS = (process.env.KEYS || ALL).split(/\s+/).filter(Boolean);

let bad = 0, total = 0, eng = '';
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' [' + eng + '] ' + label + (detail && !cond ? '  — ' + detail : ''));
}
const head = (s) => console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 60 - s.length)));
let browser = null;

async function openPage(W, theme) {
  const ctx = await browser.newContext({ viewport: { width: W, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((t) => { try { localStorage.clear(); localStorage.setItem('theme', t); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} }, theme || 'light');
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 40000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined', null, { timeout: 40000 });
  await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
  return { ctx, page, errors };
}
async function pick(page, key) {
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
  await page.waitForTimeout(450);
}
const tipShown = (page) => page.evaluate(() => { const t = document.getElementById('hint-tip'); return !!(t && t.getClientRects().length && getComputedStyle(t).display !== 'none' && getComputedStyle(t).visibility !== 'hidden'); });

async function sectionA() {
  head('А. Подсказок нет: плашка, «?», «Как писать формулы»');
  const { ctx, page, errors } = await openPage(1440, 'light');
  const shownAt = [], noAria = [], dots = [], lost = [];
  let hovered = 0;
  for (const key of KEYS) {
    await pick(page, key);
    // «Вид графика» открыт: его узлы тоже проверяем.
    await page.evaluate(() => { const b = document.getElementById('btn-view'); if (b) b.click(); });
    await page.waitForTimeout(200);
    const targets = await page.evaluate(() => {
      const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
      const roots = ['#tools-panel', '.mhead', '.cv-bar', '#params-panel', '#wrench-pop'].map(q => document.querySelector(q)).filter(Boolean);
      const out = [];
      roots.forEach(r => r.querySelectorAll('[data-tip]').forEach(el => {
        if (!vis(el)) return;
        if (!el.id) el.id = '__qp' + Math.random().toString(36).slice(2, 9);
        out.push({ id: el.id, aria: (el.getAttribute('aria-label') || '').trim() });
      }));
      return out;
    });
    for (const t of targets) {
      if (!t.aria) noAria.push(key + ' #' + t.id);
      const box = await page.evaluate((id) => { const e = document.getElementById(id); if (!e) return null; const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }, t.id);
      if (!box) continue;
      await page.mouse.move(box[0], box[1]);
      await page.waitForTimeout(30);
      hovered++;
      if (await tipShown(page)) shownAt.push(key + ' наведение #' + t.id);
    }
    // Фокус с клавиатуры: Tab поднимает признак «клавиатура», дальше фокус по узлам.
    await page.keyboard.press('Tab');
    for (const t of targets.slice(0, 40)) {
      await page.evaluate((id) => { const e = document.getElementById(id); if (e && e.focus) e.focus(); }, t.id);
      if (await tipShown(page)) shownAt.push(key + ' фокус #' + t.id);
    }
    await page.keyboard.press('Escape');
    // Абзацы-пояснения «Условия» (прятались под «?») и абзацы плашек с data-explain — в «Разборе».
    (await page.evaluate(() => {
      const root = document.getElementById('tools-panel');
      const hid = (w) => { for (let n = w; n && n !== root; n = n.parentElement) { if (n.hidden || (n.style && n.style.display === 'none') || n.classList.contains('scoped-off')) return true; } return false; };
      const norm = (t) => String(t || '').replace(/[\s\u00a0\u202f\u2009\u200b]+/g, '');
      const tx = (e) => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent; };
      const ex = norm(tx(document.getElementById('ex-body')));
      return [...root.querySelectorAll('.hint, .hint-pop [data-explain]')].filter(h => !h.closest('.sb-note-src') && !h.classList.contains('sb-note-src') && !hid(h) && norm(tx(h)))
        .filter(h => ex.indexOf(norm(tx(h)).slice(0, 60)) < 0).map(h => tx(h).trim().slice(0, 50));
    })).forEach(x => lost.push(key + ': «' + x + '»'));
    const d = await page.evaluate(() => [...document.querySelectorAll('.hint-btn, .hint-row, .help-dot, #btn-howto')]
      .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden').map(e => (e.id || e.className) + ' «' + e.textContent.trim().slice(0, 20) + '»'));
    d.forEach(x => dots.push(key + ': ' + x));
  }
  ok(KEYS.length + ' моделей: плашка #hint-tip не видна ни разу (наведений ' + hovered + ')', !shownAt.length, shownAt.slice(0, 6).join(' | '));
  ok('у каждого узла с data-tip есть непустой aria-label', !noAria.length, noAria.length + ': ' + noAria.slice(0, 6).join(' | '));
  ok('видимых .hint-btn, .hint-row, .help-dot, #btn-howto — 0', !dots.length, dots.slice(0, 6).join(' | '));
  ok('каждый абзац-пояснение «Условия» и абзац плашки с data-explain стоит в «Разборе» своей модели', !lost.length, lost.length + ': ' + lost.slice(0, 5).join(' | '));
  for (const key of ['sd', 'ppf', 'm-graph']) {
    await pick(page, key);
    const r = await page.evaluate(async () => {
      const b = [...document.querySelectorAll('#tools-panel .f-kbd')].find(x => x.getClientRects().length);
      if (!b) return { err: 'нет кнопки клавиатуры' };
      b.click();
      await new Promise(res => setTimeout(res, 300));
      const k = [...document.querySelectorAll('.mkbd.open')][0];
      if (!k) return { err: 'окно клавиатуры не открылось' };
      const tab = [...k.querySelectorAll('.mkbd-tab')].find(t => t.textContent.trim() === 'Как писать');
      if (!tab) return { err: 'нет раздела «Как писать»', tabs: [...k.querySelectorAll('.mkbd-tab')].map(t => t.textContent) };
      tab.click();
      await new Promise(res => setTimeout(res, 100));
      const pane = k.querySelector('.mkbd-howto');
      const rows = pane ? [...pane.querySelector('.howto-rows').querySelectorAll('.howto-row')] : [];
      return { n: rows.length, vis: !!(pane && pane.getClientRects().length), first: rows[0] ? rows[0].textContent.trim().slice(0, 30) : '' };
    });
    ok(key + ': окно клавиатуры поля — раздел «Как писать», 9 строк', r.n === 9 && r.vis, JSON.stringify(r));
    await page.keyboard.press('Escape');
  }
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

/* Видимые тексты панелей: ступень (кегль/вес), шрифт, моноширинный. */
const fontAudit = (page) => page.evaluate(() => {
  const STEPS = new Set(['18/600', '14/600', '14/500', '14/400', '13/600', '12/500']);
  const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden' && parseFloat(getComputedStyle(e).fontSize) > 0;
  const roots = ['#tools-panel', '#pts-panel', '#wrench-pop'].map(q => document.querySelector(q)).filter(Boolean);
  const off = [], mono = [];
  roots.forEach(r => {
    const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const e = n.parentElement;
      if (!e || !n.nodeValue.trim()) continue;
      if (e.closest('.katex, math-field, .mkbd, .f-pop, script, style, option, select, .ML__container')) continue;
      if (!vis(e)) continue;
      const cs = getComputedStyle(e);
      const k = Math.round(parseFloat(cs.fontSize) * 2) / 2 + '/' + (parseInt(cs.fontWeight, 10) || 400);
      const fam = cs.fontFamily.toLowerCase();
      if (/mono|courier|menlo|consolas/.test(fam)) mono.push(e.tagName + '.' + String(e.className).slice(0, 20) + ' «' + n.nodeValue.trim().slice(0, 20) + '»');
      if (!STEPS.has(k) || !/montserrat/.test(fam.split(',')[0]))
        off.push(k + ' ' + fam.split(',')[0].replace(/["']/g, '') + ' ' + e.tagName + '.' + String(e.className).slice(0, 24) + ' «' + n.nodeValue.trim().slice(0, 24) + '»');
    }
  });
  // Зазор подпись → поле.
  const gaps = [];
  roots.forEach(r => r.querySelectorAll('label').forEach(l => {
    if (!vis(l)) return;
    const f = (l.htmlFor && document.getElementById(l.htmlFor)) || null;
    if (!f || f.type === 'checkbox' || f.type === 'radio' || l.contains(f)) return;
    const fe = f.closest('.f-slot, .f-row') || f;
    if (!vis(fe)) return;
    const a = l.getBoundingClientRect(), b = fe.getBoundingClientRect();
    let gap = null;
    if (a.bottom <= b.top + 2) gap = b.top - a.bottom;
    else if (a.right <= b.left + 2) gap = b.left - a.right;
    if (gap != null && gap < 6 - 0.5) gaps.push('«' + l.textContent.trim().slice(0, 24) + '» ' + Math.round(gap * 10) / 10 + ' px');
  }));
  return { off, mono, gaps };
});

async function sectionSh() {
  head('Ш. Лесенка A: «Условие», «Точки и площади», «Вид графика»');
  for (const theme of ['light']) {
    const { ctx, page, errors } = await openPage(1440, theme);
    const off = [], mono = [], gaps = [];
    for (const key of KEYS) {
      await pick(page, key);
      let a = await fontAudit(page);
      a.off.forEach(x => off.push(key + ' Условие: ' + x)); a.mono.forEach(x => mono.push(key + ': ' + x)); a.gaps.forEach(x => gaps.push(key + ': ' + x));
      await page.evaluate(() => { const b = document.getElementById('btn-view'); if (b) b.click(); });
      await page.waitForTimeout(150);
      a = await fontAudit(page);
      a.off.filter(x => true).forEach(x => off.push(key + ' Вид: ' + x));
      await page.keyboard.press('Escape');
      await page.evaluate(() => { if (typeof setPtsMode === 'function') setPtsMode(true); });
      await page.waitForTimeout(200);
      a = await fontAudit(page);
      a.off.forEach(x => off.push(key + ' Точки: ' + x)); a.mono.forEach(x => mono.push(key + ': ' + x));
      await page.evaluate(() => { if (typeof setPtsMode === 'function') setPtsMode(false); });
    }
    const uniq = [...new Set(off.map(x => x.replace(/^\S+ /, '')))];
    ok(theme + ': ' + KEYS.length + ' моделей — каждый видимый текст на ступени лесенки A, Montserrat', !off.length, off.length + ' (разных ' + uniq.length + '): ' + uniq.slice(0, 14).join(' | '));
    ok(theme + ': моноширинного шрифта вне окна клавиатуры нет', !mono.length, mono.slice(0, 6).join(' | '));
    ok(theme + ': зазор подпись → поле ≥ 6 px', !gaps.length, gaps.slice(0, 8).join(' | '));
    ok(theme + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

async function sectionK() {
  head('К. Поля в тёмной теме, «Сдвиг MC», #11151d');
  const css = fs.readFileSync(path.join(HERE, '..', '..', 'static', 'calc2', 'calc2.css'), 'utf8');
  ok('в calc2.css нет #11151d (синий список тёмной темы)', !/#11151d/i.test(css));
  const { ctx, page, errors } = await openPage(1440, 'dark');
  const blue = [];
  for (const key of KEYS) {
    await pick(page, key);
    const r = await page.evaluate(() => [...document.querySelectorAll('#tools-panel input[type=text], #tools-panel input[type=number], #tools-panel select, #tools-panel .f-row, #tools-panel .fc-card .crow-formula')]
      .filter(e => e.getClientRects().length).map(e => getComputedStyle(e).backgroundColor).filter(c => c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent'));
    const odd = [...new Set(r)].filter(c => c !== 'rgb(35, 32, 25)');
    if (odd.length) blue.push(key + ': ' + odd.join(', '));
  }
  ok('тёмная тема: фон полей и списков «Условия» #232019', !blue.length, blue.slice(0, 6).join(' | '));
  // Подписи ползунков «Условия» (.pchip-label): исходная запись — из annotation KaTeX.
  const label = async (key, re) => { await pick(page, key); return page.evaluate((src) => {
    const re = new RegExp(src);
    return [...document.querySelectorAll('#tools-panel .pchip-label')].filter(e => e.getClientRects().length)
      .map(e => ({ tex: ((e.querySelector('annotation') || {}).textContent || '').trim(), sub: !!e.querySelector('.msupsub') }))
      .filter(x => re.test(x.tex));
  }, re); };
  for (const key of ['mono', 'mono-nat', 'mono-d1']) {
    const r = await label(key, 'Сдвиг.*M');
    ok(key + ': «Сдвиг MC» одним обозначением (без индекса)', r.length > 0 && r.every(x => !x.sub), JSON.stringify(r));
  }
  const pwR = await label('smallopen', '^P_');
  ok('smallopen: «Pw» с индексом', pwR.length > 0 && pwR.some(x => x.sub), JSON.stringify(pwR));
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

async function sectionZ() {
  head('З. Нет пустых заголовков в «Условии»');
  const { ctx, page, errors } = await openPage(1440, 'light');
  const bads = [];
  let n = 0;
  const check = async (label) => {
    const r = await page.evaluate(() => {
      const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
      const ORG = 'input:not([type=hidden]), button, select, textarea, math-field, .edval, .tgl-sw, [role=switch]';
      const hasOrg = (nodes) => nodes.some(x => (x.matches(ORG) && vis(x)) || [...x.querySelectorAll(ORG)].some(vis));
      const TIT = '.curve-group-title, .vsub, .section-title, .sc-sec';
      const tp = document.getElementById('tools-panel');
      const out = [];
      let cnt = 0;
      tp.querySelectorAll('h3.sec-head').forEach(h => {
        if (!vis(h)) return; cnt++;
        const sec = h.closest('.section') || h.parentElement;
        if (!hasOrg([...sec.children].filter(x => x !== h && !x.contains(h)))) out.push('«' + h.textContent.trim().slice(0, 40) + '»');
      });
      tp.querySelectorAll(TIT).forEach(t => {
        if (!vis(t)) return; cnt++;
        const g = [];
        for (let x = t.nextElementSibling; x && !x.matches(TIT); x = x.nextElementSibling) g.push(x);
        if (!hasOrg(g)) out.push('«' + t.textContent.trim().slice(0, 40) + '»');
      });
      return { out, cnt };
    });
    n += r.cnt;
    r.out.forEach(x => bads.push(label + ': ' + x));
  };
  for (const key of KEYS) { await pick(page, key); await check(key); }
  if (KEYS.includes('costs')) {
    await pick(page, 'costs');
    await page.evaluate(() => document.getElementById('cm-curves').click());
    await page.waitForTimeout(400);
    await check('costs «Задам кривые»');
  }
  ok('заголовков проверено ' + n + ': у каждого видимого есть видимый орган под ним', n > 0 && !bads.length, bads.slice(0, 8).join(' | '));
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
  if (want('Ш')) await sectionSh();
  if (want('К')) await sectionK();
  if (want('З')) await sectionZ();
  await browser.close();
}
console.log('\nИТОГ quiet_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
