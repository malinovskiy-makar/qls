/* Прибор экрана выбора «Графиков» (решение 09.10, ADR 0141): вкладки блоков,
   сетка карточек с превью, ряд «Продолжить · <когда>» и недавних, поиск.

   Проверяет числовые инварианты задания (фаза 3):
     · вкладок 10, числа на них 6, 4, 7, 4, 5, 4, 2, 2, 6, 2;
     · карточек в сетке выбранного блока = рабочих + «скоро» этого блока;
     · встроенных превью на экране = рабочих карточек видимого блока +
       карточки ряда «Продолжить»; ни одного текстового узла в превью;
     · узлов .scard-spec 0;
     · подпись большой карточки — ровно «Продолжить · <когда>»;
     · нет истории — ряда «Продолжить» нет вовсе;
     · клавиатура вкладок (стрелки, Home, End), поиск «нал» и Enter,
       «скоро» не открывается, смена темы перекрашивает превью;
     · горизонтальной прокрутки страницы нет на 390, 760, 1440;
       цели касания на 390 не меньше 44;
     · контраст каждой кривой превью к колодцу ≥ 3 : 1 в обеих темах (тот же
       замер, что redesign/contrast_probe.mjs: путь без заливки от 1,5 px,
       цвет с учётом прозрачности).
   SHOTS=1 — снимки для владельца в reports/calc2_picker/.

   node calc2/tests/picker_probe.mjs        (CALC2_BASE_URL — сервер, по умолчанию 8099)
   Коды: 0 — всё сошлось; 1 — провал; 3 — calc2 не загрузился. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const SHOTS = !!process.env.SHOTS;
const OUT = path.join(ROOT, 'reports', 'calc2_picker');
const BLOCKS = ['Математика', 'КПВ и КТВ', 'Совершенная конкуренция', 'Теория фирмы', 'Несовершенная конкуренция',
  'Рынок труда', 'Международная торговля', 'Выбор потребителя', 'Макроэкономика', 'Избранные сюжеты'];
const COUNTS = [6, 4, 7, 4, 5, 4, 2, 2, 6, 2];
const WHEN = /^Продолжить · (только что|\d+ мин назад|\d+ ч назад|вчера|\d+ (день|дня|дней) назад)$/;

const checks = [];
const ok = (name, cond, why) => { checks.push([cond ? 'OK' : 'FAIL', name, cond ? '' : String(why == null ? '' : why)]); };
const browser = await chromium.launch();
if (SHOTS) fs.mkdirSync(OUT, { recursive: true });

async function open(theme, w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((t) => { try { localStorage.clear(); localStorage.setItem('theme', t); } catch (e) {} }, theme);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message || e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  try {
    await page.goto(BASE + '/calc2/', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForFunction(() => typeof pickScene === 'function' && document.querySelector('#scene-picker .pk-pv'), null, { timeout: 25000 });
  } catch (e) {
    console.log('calc2 не загрузился: ' + e.message.split('\n')[0]);
    await browser.close();
    process.exit(3);
  }
  return { ctx, page, errors };
}
// История: текущая модель и три недавних (3 ч, вчера, 2 дня назад), как на макете.
async function seedHistory(page, cur) {
  await page.evaluate((c) => {
    resetSceneMemory();
    const now = Date.now(), H = 3600e3;
    localStorage.setItem('calc2.v1.recent', JSON.stringify([
      { k: c, t: now - 60e3 }, { k: 'taxes', t: now - 3 * H }, { k: 'trade', t: now - 26 * H }, { k: 'mono', t: now - 50 * H }]));
    closePicker(); pickScene(c); openPicker();
  }, cur);
  await page.waitForTimeout(250);
}
async function noHistory(page) {
  await page.evaluate(() => { resetSceneMemory(); closePicker(); STATE.sceneKey = null; openPicker(); });
  await page.waitForTimeout(200);
}
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: path.join(OUT, name + '.png') }); };

// Состояние экрана одним снимком.
const stateOf = (page) => page.evaluate(() => {
  // у SVG нет offsetParent: видимость превью — по его колодцу или миниатюре
  const vis = (el) => !!el && (el instanceof SVGElement ? vis(el.parentElement) : el.offsetParent !== null && getComputedStyle(el).visibility !== 'hidden');
  const tabs = [...document.querySelectorAll('#picker-tabs .pk-tab')];
  const sel = tabs.find(t => t.getAttribute('aria-selected') === 'true');
  const block = sel ? sel.dataset.block : '';
  const g = [...document.querySelectorAll('#scene-picker .picker-group')].find(x => x.getAttribute('aria-label') === block);
  const all = g ? [...g.querySelectorAll('.scard')] : [];
  const cont = document.getElementById('picker-cont');
  const contCards = cont && vis(cont) ? [...cont.querySelectorAll('.pk-ccard')].filter(vis) : [];
  return {
    tabs: tabs.map(t => [t.querySelector('.pk-tname').textContent, t.querySelector('.pk-tcount').textContent]),
    tabsVisible: vis(document.getElementById('picker-tabs')),
    block,
    working: all.filter(c => !c.disabled).length, soon: all.filter(c => c.disabled).length,
    visibleCards: [...document.querySelectorAll('#scene-picker .scard')].filter(vis).length,
    visibleWorking: [...document.querySelectorAll('#scene-picker .scard:not([disabled])')].filter(vis).length,
    pv: [...document.querySelectorAll('#scene-picker svg.pk-pv')].filter(vis).length,
    pvText: document.querySelectorAll('#scene-picker svg.pk-pv text, #scene-picker svg.pk-pv tspan').length,
    pvEmpty: [...document.querySelectorAll('#scene-picker svg.pk-pv')].filter(s => !s.querySelector('path')).length,
    spec: document.querySelectorAll('.scard-spec').length,
    contCards: contCards.length,
    when: (document.querySelector('#picker-continue .pk-when') || {}).textContent || null,
    contName: (document.querySelector('#picker-continue .pk-cname') || {}).textContent || null,
    recents: [...document.querySelectorAll('#picker-cont .pk-recent')].map(c => c.dataset.scene),
    recentWhen: [...document.querySelectorAll('#picker-cont .pk-recent .pk-when')].map(c => c.textContent),
    sub: document.querySelectorAll('#scene-picker .picker-sub').length,
    title: (document.querySelector('#scene-picker .picker-title') || {}).textContent,
    pattern: document.getElementById('scene-picker').classList.contains('bg-pattern-host'),
    overlay: !!document.getElementById('picker-preview'),
    soonLine: [...document.querySelectorAll('#scene-picker .pk-soon')].length,
  };
});

/* ── 1. Без истории, 1440 тёмная ─────────────────────────────────────── */
let f = await open('dark', 1440, 900);
let p = f.page;
await noHistory(p);
let s = await stateOf(p);
ok('вкладок 10, имена по порядку', s.tabs.length === 10 && s.tabs.every((t, i) => t[0] === BLOCKS[i]), JSON.stringify(s.tabs.map(t => t[0])));
ok('числа на вкладках 6, 4, 7, 4, 5, 4, 2, 2, 6, 2', s.tabs.map(t => +t[1]).join() === COUNTS.join(), s.tabs.map(t => t[1]).join());
ok('без истории открыта «Математика»', s.block === 'Математика', s.block);
ok('без истории ряда «Продолжить» нет вовсе', s.contCards === 0, 'карточек ' + s.contCards);
ok('узлов .scard-spec 0', s.spec === 0, s.spec);
ok('заголовок «Графики», строки про число моделей нет', s.title.trim() === 'Графики' && !s.sub, s.title + ' / sub ' + s.sub);
ok('фона с узором нет', !s.pattern, 'bg-pattern-host на месте');
ok('всплывающей схемы и строк «скоро» на экране нет', !s.overlay && !s.soonLine, 'preview ' + s.overlay + ', строк ' + s.soonLine);
await shot(p, 'picker_1440_dark_empty');

// Каждая вкладка: карточки = рабочие + «скоро»; превью = рабочие видимые + ряд «Продолжить».
const perTab = [];
for (let i = 0; i < 10; i++) {
  await p.click('#picker-tabs .pk-tab >> nth=' + i);
  await p.waitForTimeout(60);
  const t = await stateOf(p);
  perTab.push(t);
  const want = t.working + t.soon;
  ok('вкладка «' + BLOCKS[i] + '»: карточек ' + want + ' (' + t.working + ' + ' + t.soon + ' скоро)', t.block === BLOCKS[i] && t.visibleCards === want && t.working === COUNTS[i], t.block + ' видно ' + t.visibleCards);
  ok('вкладка «' + BLOCKS[i] + '»: превью ' + (t.visibleWorking + t.contCards), t.pv === t.visibleWorking + t.contCards && !t.pvText && !t.pvEmpty, 'превью ' + t.pv + ', текстовых ' + t.pvText + ', пустых ' + t.pvEmpty);
}
ok('рабочих 42 и «скоро» 14 по всем вкладкам', perTab.reduce((a, t) => a + t.working, 0) === 42 && perTab.reduce((a, t) => a + t.soon, 0) === 14,
  perTab.reduce((a, t) => a + t.working, 0) + ' / ' + perTab.reduce((a, t) => a + t.soon, 0));

// Клавиатура: стрелки, Home, End, Enter.
await p.click('#picker-tabs .pk-tab >> nth=0');
await p.focus('#picker-tabs .pk-tab[aria-selected="true"]');
await p.keyboard.press('ArrowRight');
let k1 = (await stateOf(p)).block;
await p.keyboard.press('End');
let k2 = (await stateOf(p)).block;
await p.keyboard.press('Home');
let k3 = (await stateOf(p)).block;
await p.keyboard.press('ArrowLeft');
let k4 = (await stateOf(p)).block;
const focusOnSel = await p.evaluate(() => document.activeElement && document.activeElement.getAttribute('aria-selected') === 'true');
ok('стрелки и Home/End переключают вкладки, фокус на выбранной', k1 === BLOCKS[1] && k2 === BLOCKS[9] && k3 === BLOCKS[0] && k4 === BLOCKS[9] && focusOnSel, [k1, k2, k3, k4, focusOnSel].join(' | '));
const roles = await p.evaluate(() => {
  const tl = document.getElementById('picker-tabs');
  const tabs = [...tl.querySelectorAll('.pk-tab')];
  return tl.getAttribute('role') === 'tablist' && tabs.every(t => t.getAttribute('role') === 'tab' && document.getElementById(t.getAttribute('aria-controls')).getAttribute('role') === 'tabpanel')
    && tabs.filter(t => t.tabIndex === 0).length === 1;
});
ok('роли tablist / tab / tabpanel, в порядке Tab одна вкладка', roles, 'роли не те');

// Вкладка помнится: перезагрузка без истории открывает последнюю выбранную.
await p.click('#picker-tabs .pk-tab >> nth=4');
await p.evaluate(() => { closePicker(); STATE.sceneKey = null; openPicker(); });
ok('последняя вкладка помнится', (await stateOf(p)).block === BLOCKS[4], (await stateOf(p)).block);

// «Скоро» не открывается.
await p.click('#picker-tabs .pk-tab >> nth=7');
await p.evaluate(() => { STATE.sceneKey = null; });
await p.locator('#scene-picker .scard.soon >> visible=true').first().click({ force: true });
await p.waitForTimeout(150);
const soonState = await p.evaluate(() => ({ open: !document.getElementById('scene-picker').classList.contains('hidden'), key: STATE.sceneKey }));
ok('карточка «скоро» не открывается', soonState.open && !soonState.key, JSON.stringify(soonState));

/* ── 2. С историей ────────────────────────────────────────────────────── */
await seedHistory(p, 'm-graph');
s = await stateOf(p);
ok('подпись большой карточки — «Продолжить · только что»', s.when === 'Продолжить · только что' && WHEN.test(s.when), s.when);
ok('в «Продолжить» модель, из которой пришли', s.contName === 'Построение графиков', s.contName);
ok('недавние: до трёх, без модели из «Продолжить», с временем', s.recents.join() === 'taxes,trade,mono' && s.recentWhen.join('|') === '3 ч назад|вчера|2 дня назад', s.recents.join() + ' / ' + s.recentWhen.join('|'));
ok('ряд «Продолжить» — 4 карточки, у каждой превью', s.contCards === 4 && s.pv === s.visibleWorking + 4, 'карточек ' + s.contCards + ', превью ' + s.pv);
ok('открыт блок модели из «Продолжить»', s.block === 'Математика', s.block);
await shot(p, 'picker_1440_dark_history');
// Возврат из модели другого блока: открыт её блок.
await seedHistory(p, 'labor-mono');
s = await stateOf(p);
ok('из «Монопсонии» экран открывается на «Рынке труда»', s.block === 'Рынок труда' && s.contName === 'Монопсония', s.block + ' / ' + s.contName);
const whenSamples = await p.evaluate(() => [0, 120e3, 5 * 3600e3, 26 * 3600e3, 3 * 86400e3].map(d => 'Продолжить · ' + whenText(Date.now() - d)));
ok('формат времени: только что, мин, ч, вчера, дни', whenSamples.every(x => /^Продолжить · (только что|\d+ мин назад|\d+ ч назад|вчера|\d+ (день|дня|дней) назад)$/.test(x)), whenSamples.join(' | '));
// Щелчок по недавней открывает её с состоянием.
await seedHistory(p, 'm-graph');
await p.click('#picker-cont .pk-recent >> nth=0');
await p.waitForTimeout(200);
ok('щелчок по недавней открывает модель', await p.evaluate(() => STATE.sceneKey === 'taxes' && document.getElementById('scene-picker').classList.contains('hidden')), await p.evaluate(() => STATE.sceneKey));

/* ── 3. Поиск «нал» ───────────────────────────────────────────────────── */
await seedHistory(p, 'm-graph');
await p.click('#picker-tabs .pk-tab >> nth=2');
await p.fill('#picker-search', 'нал');
await p.waitForTimeout(150);
const sr = await p.evaluate(() => {
  const vis = (el) => !!el && (el instanceof SVGElement ? vis(el.parentElement) : el.offsetParent !== null);
  const hits = [...document.querySelectorAll('#scene-picker .scard')].filter(vis);
  return {
    tabs: vis(document.getElementById('picker-tabs')), cont: vis(document.getElementById('picker-cont')),
    n: hits.length, blocks: hits.map(c => (c.querySelector('.pk-cblock') || {}).textContent).filter(Boolean).length,
    labelsShown: hits.every(c => vis(c.querySelector('.pk-cblock'))),
    first: (document.querySelector('#scene-picker .scard.pk-first .scard-name') || {}).textContent,
    enter: (document.querySelector('#picker-found .pk-enter') || {}).textContent,
    multiBlock: new Set(hits.map(c => c.closest('.picker-group').getAttribute('aria-label'))).size,
    pv: [...document.querySelectorAll('#scene-picker svg.pk-pv')].filter(vis).length,
    working: hits.filter(c => !c.disabled).length,
  };
});
ok('поиск «нал»: вкладки и «Продолжить» спрятаны', !sr.tabs && !sr.cont, JSON.stringify(sr));
ok('поиск «нал»: находки из разных блоков, над каждой имя блока', sr.n >= 2 && sr.multiBlock >= 2 && sr.labelsShown && sr.blocks === sr.n, JSON.stringify(sr));
ok('поиск «нал»: первая находка «Налоги и субсидии», Enter её откроет', sr.first === 'Налоги и субсидии' && /Налоги и субсидии/.test(sr.enter || ''), sr.first + ' / ' + sr.enter);
ok('поиск «нал»: превью у каждой рабочей находки', sr.pv === sr.working, sr.pv + ' / ' + sr.working);
await shot(p, 'picker_1440_dark_search_nal');
await p.fill('#picker-search', '');
await p.waitForTimeout(100);
s = await stateOf(p);
ok('очистка поиска возвращает вкладки и прежний блок', s.tabsVisible && s.block === BLOCKS[2], s.tabsVisible + ' ' + s.block);
await p.fill('#picker-search', 'нал');
await p.press('#picker-search', 'Enter');
await p.waitForTimeout(250);
ok('Enter в поиске открывает «Налоги и субсидии»', await p.evaluate(() => STATE.sceneKey === 'taxes'), await p.evaluate(() => STATE.sceneKey));
await p.evaluate(() => { const q = document.getElementById('picker-search'); q.value = ''; pickerFilter(''); });

/* ── 4. Смена темы на открытом экране ─────────────────────────────────── */
await seedHistory(p, 'm-graph');
const axis = () => p.evaluate(() => {
  const path = [...document.querySelectorAll('#scene-picker .pk-block.open svg.pk-pv path')].find(x => x.style.stroke === 'var(--ink)');
  return path ? getComputedStyle(path).stroke : null;
});
const a1 = await axis();
await p.evaluate(() => { document.documentElement.setAttribute('data-theme', 'light'); });
await p.waitForTimeout(120);
const a2 = await axis();
ok('смена темы перекрашивает превью (ось — чернила темы)', a1 && a2 && a1 !== a2, a1 + ' → ' + a2);
await p.evaluate(() => { document.documentElement.setAttribute('data-theme', 'dark'); });
f.errors.forEach(e => ok('ошибок на странице нет', false, e));
await f.ctx.close();

/* ── 5. Контраст кривых превью к колодцу, обе темы ────────────────────── */
let worst = { c: 99 }, lines = 0, low = [];
for (const theme of ['light', 'dark']) {
  f = await open(theme, 1440, 900);
  await noHistory(f.page);
  for (let i = 0; i < 10; i++) {
    await f.page.click('#picker-tabs .pk-tab >> nth=' + i);
    const r = await f.page.evaluate(() => {
      const rgb = (x) => { const m = String(x).match(/[\d.]+/g); return m ? m.slice(0, 4).map(Number) : null; };
      const lum = ([r, g, b]) => { const q = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * q(r) + 0.7152 * q(g) + 0.0722 * q(b); };
      const out = [];
      document.querySelectorAll('#scene-picker .pk-block.open .pk-well').forEach(w => {
        const bg = rgb(getComputedStyle(w).backgroundColor);
        w.querySelectorAll('path').forEach(pth => {
          const cs = getComputedStyle(pth);
          if (cs.fill !== 'none' || cs.stroke === 'none' || parseFloat(cs.strokeWidth) < 1.5) return;
          const c = rgb(cs.stroke); if (!c) return;
          const a = (c[3] == null ? 1 : c[3]) * (+cs.strokeOpacity || 1) * (+cs.opacity || 1);
          const mix = [0, 1, 2].map(i => c[i] * a + bg[i] * (1 - a));
          const L1 = lum(mix), L2 = lum(bg);
          out.push({ key: w.parentNode.dataset.scene, c: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), stroke: cs.stroke, a });
        });
      });
      return out;
    });
    r.forEach(x => { lines++; if (x.c < worst.c) worst = Object.assign({ theme }, x); if (x.c < 3) low.push(theme + ' ' + x.key + ' ' + x.stroke + ' ' + x.c.toFixed(2)); });
  }
  if (theme === 'light') { await seedHistory(f.page, 'm-graph'); await shot(f.page, 'picker_1440_light_history'); await noHistory(f.page); await shot(f.page, 'picker_1440_light_empty'); }
  await f.ctx.close();
}
ok('контраст кривых превью к колодцу ≥ 3 : 1 (линий ' + lines + ', худшая ' + worst.theme + ' ' + worst.key + ' ' + (worst.c || 0).toFixed(2) + ')', lines > 0 && !low.length, low.slice(0, 8).join('; '));

/* ── 6. Узкие окна: прокрутка вбок и цели касания ─────────────────────── */
for (const [w, h] of [[390, 844], [760, 900], [1440, 900]]) {
  f = await open('dark', w, h);
  for (const hist of [false, true]) {
    if (hist) await seedHistory(f.page, 'm-graph'); else await noHistory(f.page);
    const r = await f.page.evaluate(() => {
      const de = document.scrollingElement || document.documentElement;
      const pk = document.getElementById('scene-picker');
      const bad = [];
      const W = window.innerWidth;
      if (de.scrollWidth > W + 1) bad.push('страница ' + de.scrollWidth + ' > ' + W);
      if (pk.scrollWidth > pk.clientWidth + 1) bad.push('экран выбора ' + pk.scrollWidth + ' > ' + pk.clientWidth);
      // Ничто, кроме лент с прокруткой (вкладки, недавние), не выходит за край окна.
      pk.querySelectorAll('.pk-search, .pk-continue, .pk-panels, .scard').forEach(el => {
        if (el.offsetParent === null) return;
        const b = el.getBoundingClientRect();
        if (b.right > W + 1 || b.left < -1) bad.push((el.id || el.className) + ' ' + Math.round(b.left) + '…' + Math.round(b.right));
      });
      // Текст карточек ряда «Продолжить» не вылезает за их край.
      pk.querySelectorAll('.pk-ccard').forEach(el => {
        if (el.offsetParent === null) return;
        const b = el.getBoundingClientRect();
        el.querySelectorAll('.pk-when, .pk-cname').forEach(t => {
          const r = document.createRange(); r.selectNodeContents(t);
          const rb = r.getBoundingClientRect();
          if (rb.right > b.right - 2) bad.push('текст «' + t.textContent + '» за краем карточки на ' + Math.round(rb.right - b.right + 2) + ' px');
        });
      });
      const small = [];
      if (W < 760) {
        pk.querySelectorAll('.pk-tab, .scard:not([disabled]), .pk-ccard, .pk-go, #picker-search').forEach(el => {
          if (el.offsetParent === null) return;
          const b = el.getBoundingClientRect();
          if (b.height < 44 || b.width < 44) small.push((el.dataset.block || el.dataset.scene || el.id || el.className) + ' ' + Math.round(b.width) + '×' + Math.round(b.height));
        });
      }
      return { bad, small };
    });
    ok(w + ' px' + (hist ? ' с историей' : '') + ': страница не едет вбок', !r.bad.length, r.bad.slice(0, 5).join('; '));
    if (w < 760) ok(w + ' px' + (hist ? ' с историей' : '') + ': цели касания ≥ 44', !r.small.length, r.small.slice(0, 5).join('; '));
    if (w === 390 && hist) await shot(f.page, 'picker_390_dark_history');
    if (w === 390 && !hist) await shot(f.page, 'picker_390_dark_empty');
    if (w === 760 && hist) await shot(f.page, 'picker_760_dark_history');
  }
  f.errors.forEach(e => ok('ошибок на странице нет (' + w + ')', false, e));
  await f.ctx.close();
}
await browser.close();

let bad = 0;
for (const [st, name, why] of checks) { if (st !== 'OK') bad++; console.log(`${st.padEnd(4)} ${name}${why ? '  — ' + why : ''}`); }
console.log(`\nЭКРАН ВЫБОРА: проверок ${checks.length}, провалов ${bad}`);
process.exit(bad ? 1 : 0);
