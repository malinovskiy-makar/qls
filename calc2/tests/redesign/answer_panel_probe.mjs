/* «ОТВЕТ» И «РАЗБОР»: ТИХИЕ ПАНЕЛИ (14.10.2026; решение владельца 14.10, Notion
   …81de…, ADR 0150; пакет claude/mockups/calc2_panels_20261014, README 4–5).

   Разделы (--only А,А2,Б):
     А   1440 и 1280, пустая память, ?m=taxes: «Ответ» закрыт (полоска 44 px,
         .side-inner не видна, холст шире); стрелка «‹» — центр ±2 px от левого
         края колонки, верх 12 ± 2 px; щелчок → колонка 349 (1280 — 317), «›» на
         её краю; перезагрузка → открыт; стрелка → закрыт; перезагрузка → закрыт;
         щелчок по полоске открывает; «Сначала сам» при закрытом открывает;
         стрелка не пересекается с кнопками .cv-bar (открыт и закрыт); щелчки по
         стрелке и полоске — не шаг истории и не меняют ссылку «Поделиться»;
         1000 и 390 — стрелки нет; видимых .col-note нет; у стрелки и полоски
         есть aria-label, нет data-tip;
     А2  42 модели при 1280 и 1440: «собран закрытым → открыт стрелкой» =
         «открыт с загрузки» (видимый текст колонки, число видимых .ans-cell,
         .stat, таблиц, стопок .stat-stack);
     Б   «Разбор»: taxes — полоса «Разбор · 4 вопроса», свёрнут; щелчок → видны
         вступление и 4 вопроса, ответы скрыты; смена модели и назад → свёрнут;
         ppfsum «1 вопрос», ppf «5 вопросов»; 42 модели — у абзацев «Разбора» нет
         блочных потомков, кроме внутренностей .katex, p.ex-q > b, .ex-a, .tbl;
         щелчки по полосе и вопросам — не шаг истории, ссылка та же; 1000 —
         полоса есть и свёрнута; 390 — вкладка «Разбор» раскрыта, полосы нет.

   ENGINES=chromium,webkit (по умолчанию оба). Нет движка — громкий пропуск.
   CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/redesign/answer_panel_probe.mjs [--only А]
   Код 0 — всё сошлось.                                                     */
import * as pw from 'playwright';

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
/* mem: значение calc2.v1.answerHidden до загрузки (null — пустая память). */
async function openPage(w, h, key, mem) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((m) => {
    try {
      if (sessionStorage.getItem('__probeInit')) return;   // перезагрузка — память не трогаем
      sessionStorage.setItem('__probeInit', '1');
      localStorage.clear(); localStorage.setItem('theme', 'light');
      if (m != null) localStorage.setItem('calc2.v1.answerHidden', m);
    } catch (e) {}
  }, mem);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'load', timeout: 40000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined' && STATE.sceneKey, null, { timeout: 40000 });
  await settle(page, 900);
  return { ctx, page, errors };
}
async function settle(page, ms) {
  await page.waitForTimeout(ms || 400);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(150);
}
async function reload(page) {
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && STATE.sceneKey, null, { timeout: 40000 });
  await settle(page, 900);
}
async function clickSel(page, sel) {
  const shown = await page.evaluate((q) => { const e = document.querySelector(q); return !!(e && e.getClientRects().length); }, sel);
  if (shown) await page.click(sel); else await page.evaluate((q) => { const e = document.querySelector(q); if (e) e.click(); }, sel);
  await settle(page, 500);
}
const geo = (page) => page.evaluate(() => {
  const shown = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const R = (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height }; };
  const col = document.getElementById('params-panel');
  const hide = document.getElementById('ans-hide');
  const rail = document.getElementById('ans-rail');
  const inner = col.querySelector(':scope > .side-inner');
  const bar = [...document.querySelectorAll('.cv-bar button, .cv-bar a')].filter(shown).map(b => ({ id: b.id, ...R(b) }));
  return {
    hidden: document.body.classList.contains('ans-hidden'), col: R(col), card: R(document.querySelector('.cv-card')),
    hideShown: shown(hide), hide: shown(hide) ? R(hide) : null, hideParent: hide && hide.parentElement === col,
    rail: shown(rail), inner: shown(inner),
    rot: hide && hide.querySelector('svg') ? getComputedStyle(hide.querySelector('svg')).transform : 'нет шеврона',
    aria: hide ? [hide.getAttribute('aria-label'), hide.getAttribute('aria-expanded'), rail.getAttribute('aria-label')] : [],
    tips: [hide && hide.hasAttribute('data-tip'), rail && rail.hasAttribute('data-tip')],
    railText: rail ? rail.textContent.replace(/\s+/g, '') : '',
    colNotes: [...document.querySelectorAll('.col-note')].filter(shown).length,
    bar,
  };
});
const histState = (page) => page.evaluate(async () => {
  const h = (typeof histOf === 'function') ? histOf() : { undo: [], redo: [] };
  /* Ссылка — из состояния модели без того, что выбирает раскладка (место легенды,
     пересечения по сетке пикселей: calc2/CLAUDE.md, «Режимы холста»): ширина
     холста при открытии колонки законно другая. */
  const s = collectModelState();
  delete s.state.legendSpot; delete s.state.crosses;
  return { undo: h.undo.length, redo: h.redo.length, can: JSON.stringify(historyCan()), link: await shareLinkOf(s) };
});
/* Пересечение с зазором: стрелка не должна и касаться кнопок панели холста (без запаса 24 px у .cv-bar
   «Развернуть график» кончается ровно там, где начинается стрелка). */
const GAP = 4;
const overlap = (a, b) => a && b && a.l - GAP < b.r && b.l < a.r + GAP && a.t - GAP < b.b && b.t < a.b + GAP;

/* Сводка открытой колонки: видимый текст, строки, таблицы, стопки. */
const colSummary = (page) => page.evaluate(() => {
  const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  const root = document.querySelector('#params-panel > .side-inner');
  const out = [];
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const e = n.parentElement;
    if (!e || e.closest('.katex-mathml, annotation, script, style')) continue;
    if (!vis(e)) continue;
    const t = n.nodeValue.replace(/[\s   ​]+/g, ' ').trim();
    if (t) out.push(t);
  }
  const cnt = (q) => [...root.querySelectorAll(q)].filter(vis).length;
  return { open: vis(root), text: out.join(' '), cells: cnt('.ans-cell'), stats: cnt('.stat'), tables: cnt('table'), stacks: cnt('.stat-stack') };
});

async function sectionA() {
  head('А. «Ответ» закрыт по умолчанию, стрелка, полоска');
  for (const W of [1440, 1280]) {
    const colW = W === 1440 ? 349 : 317;
    const { ctx, page, errors } = await openPage(W, 900, 'taxes', null);
    const g0 = await geo(page);
    ok(W + ': пустая память → «Ответ» закрыт: полоска 44, .side-inner не видна',
      g0.hidden && g0.rail && !g0.inner && Math.abs(g0.col.w - 44) <= 1, JSON.stringify({ h: g0.hidden, rail: g0.rail, inner: g0.inner, w: g0.col.w }));
    ok(W + ': стрелка — прямой ребёнок #params-panel вне .side-inner', g0.hideParent);
    ok(W + ': закрыт — стрелка видна, центр ±2 от левого края колонки, верх 12 ± 2',
      g0.hideShown && Math.abs((g0.hide.l + g0.hide.r) / 2 - g0.col.l) <= 2 && Math.abs(g0.hide.t - g0.col.t - 12) <= 2 && Math.abs(g0.hide.w - 40) <= 1,
      JSON.stringify({ hide: g0.hide, col: g0.col }));
    ok(W + ': закрыт — шеврон «‹» (повёрнут), aria-expanded false, подпись «Показать «Ответ»»',
      g0.rot !== 'none' && g0.aria[1] === 'false' && /Показать/.test(g0.aria[0]), JSON.stringify(g0.aria) + ' ' + g0.rot);
    ok(W + ': у стрелки и полоски нет data-tip, у полоски есть aria-label, в полоске только «Ответ»',
      !g0.tips[0] && !g0.tips[1] && !!g0.aria[2] && g0.railText === 'Ответ', JSON.stringify({ tips: g0.tips, rail: g0.railText }));
    ok(W + ': закрыт — стрелка не касается кнопок .cv-bar (зазор ≥ 4 px)', !g0.bar.some(b => overlap(b, g0.hide)),
      JSON.stringify(g0.bar.filter(b => overlap(b, g0.hide))));
    const h0 = await histState(page);
    const card0 = g0.card.w;
    await clickSel(page, '#ans-hide');
    const g1 = await geo(page);
    ok(W + ': щелчок по стрелке → открыт, колонка ' + colW + ' px', !g1.hidden && g1.inner && Math.abs(g1.col.w - colW) <= 1, JSON.stringify({ w: g1.col.w, inner: g1.inner }));
    ok(W + ': закрытый холст был шире открытого', card0 > g1.card.w + 200, card0 + ' / ' + g1.card.w);
    ok(W + ': открыт — «›» на левом краю колонки (центр ±2, верх 12 ± 2), aria-expanded true',
      g1.hideShown && Math.abs((g1.hide.l + g1.hide.r) / 2 - g1.col.l) <= 2 && Math.abs(g1.hide.t - g1.col.t - 12) <= 2 && g1.rot === 'none' && g1.aria[1] === 'true',
      JSON.stringify({ hide: g1.hide, col: g1.col, rot: g1.rot, aria: g1.aria }));
    ok(W + ': открыт — стрелка не касается кнопок .cv-bar (зазор ≥ 4 px)', !g1.bar.some(b => overlap(b, g1.hide)),
      JSON.stringify(g1.bar.filter(b => overlap(b, g1.hide))));
    ok(W + ': видимых .col-note нет', g1.colNotes === 0, String(g1.colNotes));
    const h1 = await histState(page);
    ok(W + ': щелчок по стрелке — не шаг истории, ссылка та же', h0.undo === h1.undo && h0.can === h1.can && h0.link === h1.link, JSON.stringify([h0.undo, h1.undo, h0.can, h1.can, h0.link === h1.link]));
    await reload(page);
    const g2 = await geo(page);
    ok(W + ': перезагрузка → открыт', !g2.hidden && g2.inner);
    await clickSel(page, '#ans-hide');
    const g3 = await geo(page);
    ok(W + ': стрелка → закрыт', g3.hidden && !g3.inner && g3.rail);
    await reload(page);
    const g4 = await geo(page);
    ok(W + ': перезагрузка → закрыт', g4.hidden && !g4.inner);
    const h2 = await histState(page);
    await clickSel(page, '#ans-rail');
    const g5 = await geo(page);
    ok(W + ': щелчок по полоске открывает', !g5.hidden && g5.inner);
    const h3 = await histState(page);
    ok(W + ': щелчок по полоске — не шаг истории, ссылка та же', h2.undo === h3.undo && h2.can === h3.can && h2.link === h3.link);
    await clickSel(page, '#ans-hide');
    await page.evaluate(() => { if (typeof setSelfMode === 'function') setSelfMode(true); });
    await settle(page, 600);
    const g6 = await geo(page);
    ok(W + ': «Сначала сам» при закрытом открывает «Ответ»', !g6.hidden && g6.inner);
    ok(W + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
  for (const [W, H] of [[1000, 800], [390, 844]]) {
    const { ctx, page, errors } = await openPage(W, H, 'taxes', null);
    const g = await geo(page);
    const drawer = await page.evaluate(() => {
      if (window.innerWidth >= 760) { document.getElementById('btn-answer').click(); }
      else { const t = document.querySelector('#ph-tabs .ph-tab[data-tab="ans"]'); if (t) t.click(); }
      return true;
    });
    await settle(page, 500);
    const s = await colSummary(page);
    ok(W + ': стрелки и полоски нет, «Ответ» открывается прежним способом (' + (W >= 760 ? 'выезжает' : 'вкладка') + ')',
      drawer && !g.hideShown && !g.rail && s.open && s.cells > 0, JSON.stringify({ hide: g.hideShown, rail: g.rail, open: s.open, cells: s.cells }));
    ok(W + ': ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

async function sectionA2() {
  head('А2. Собран закрытым → открыт стрелкой = открыт с загрузки (42 модели)');
  for (const W of [1440, 1280]) {
    const diffs = [];
    for (const key of KEYS) {
      const A = await openPage(W, 900, key, '0');
      const sa = await colSummary(A.page);
      await A.ctx.close();
      const B = await openPage(W, 900, key, '1');
      await clickSel(B.page, '#ans-hide');
      await settle(B.page, 500);
      const sb = await colSummary(B.page);
      await B.ctx.close();
      const same = sa.open && sb.open && sa.text === sb.text && sa.cells === sb.cells && sa.stats === sb.stats && sa.tables === sb.tables && sa.stacks === sb.stacks;
      if (!same) {
        let i = 0; while (i < sa.text.length && sa.text[i] === sb.text[i]) i++;
        diffs.push(key + ' ' + JSON.stringify({ open: [sa.open, sb.open], cells: [sa.cells, sb.cells], stats: [sa.stats, sb.stats], tables: [sa.tables, sb.tables], stacks: [sa.stacks, sb.stacks], at: '…' + sa.text.slice(Math.max(0, i - 30), i + 40) + ' ⟂ …' + sb.text.slice(Math.max(0, i - 30), i + 40) }));
      }
    }
    ok(W + ': ' + KEYS.length + ' моделей — собранный закрытым открывается тем же', !diffs.length, diffs.length + ' моделей: ' + diffs.join(' || '));
  }
}

const exInfo = (page) => page.evaluate(() => {
  const vis = (e) => !!(e && e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  const bar = document.getElementById('ex-bar');
  const ex = document.getElementById('ex-body');
  const qs = [...ex.querySelectorAll('p.ex-q')];
  return {
    // Полоса: «Разбор» и число вопросов — два узла (на экране без точки, README 4).
    bar: vis(bar), barText: bar ? [bar.querySelector('.ex-bar-name'), bar.querySelector('.ex-bar-count')].map(x => x ? x.textContent.trim() : '').filter(Boolean).join(' ') : '',
    shown: document.body.classList.contains('ex-shown'), fold: vis(document.getElementById('ex-fold')),
    qVis: qs.filter(q => vis(q.querySelector(':scope > b'))).length, q: qs.length,
    aVis: qs.filter(q => vis(q.querySelector(':scope > .ex-a'))).length,
    // Вступление — видимый текст «Разбора» вне вопросов.
    intro: (() => { const c = ex.cloneNode(true); c.querySelectorAll('p.ex-q, .katex-mathml').forEach(x => x.remove()); return vis(ex) ? c.textContent.trim().length : 0; })(),
    expanded: bar ? bar.getAttribute('aria-expanded') : '',
  };
});
/* Блочные потомки абзацев «Разбора» (кроме законных): жирное слово внутри фразы
   строкой, а не отдельным блоком. Смотрим вычисленный display (работает и в
   свёрнутом «Разборе»). */
/* Абзац — <p> или сама врезка .sb-note (вступление у налогов — текст прямо во
   врезке). Строчные узлы (жирное, курсив, ссылки, span) внутри абзаца не
   бывают блоками; законны внутренности .katex, p.ex-q > b, .ex-a, .tbl и свой
   заголовок врезки (жирное в её начале, текста перед ним нет). */
const blockKids = (page) => page.evaluate(() => {
  const ex = document.getElementById('ex-body');
  const out = [];
  const textBefore = (k) => { let t = ''; for (let n = k.previousSibling; n; n = n.previousSibling) t += n.textContent || ''; return !!t.trim(); };
  ex.querySelectorAll('.sb-note *').forEach(k => {
    if (!/^(B|STRONG|I|EM|SPAN|A|SUB|SUP|CODE)$/.test(k.tagName)) return;
    if (k.closest('.katex') || k.matches('p.ex-q > b, .ex-a') || k.closest('.tbl')) return;
    if (k.tagName === 'B' && k.parentElement.matches('.sb-note') && !textBefore(k)) return;
    const d = getComputedStyle(k).display;
    if (/^(block|flex|grid|list-item|table)$/.test(d)) out.push(k.tagName + '.' + k.className + ' «' + k.textContent.slice(0, 30) + '»');
  });
  return out;
});

async function sectionB() {
  head('Б. «Разбор» внутри «Ответа», свёрнут');
  const { ctx, page, errors } = await openPage(1440, 900, 'taxes', '0');
  const e0 = await exInfo(page);
  ok('taxes: полоса «Разбор · 4 вопроса», свёрнут', e0.bar && /^Разбор\s*4 вопроса$/.test(e0.barText) && !e0.shown && !e0.fold && e0.expanded === 'false', JSON.stringify(e0));
  const h0 = await histState(page);
  await clickSel(page, '#ex-bar');
  const e1 = await exInfo(page);
  ok('щелчок → видны вступление и 4 вопроса, ответы скрыты', e1.shown && e1.fold && e1.qVis === 4 && e1.aVis === 0 && e1.intro > 0 && e1.expanded === 'true', JSON.stringify(e1));
  /* Жирное слово внутри фразы стоит в той же строке, что текст перед ним: верх
     его первого прямоугольника = верх последнего прямоугольника предыдущего
     текста (± 4 px). Блоком оно начинало бы новую строку. */
  const sameLine = await page.evaluate(() => {
    const p = document.querySelector('#ex-body > .sb-note');
    const b = p && [...p.querySelectorAll(':scope > b')].find(x => { let t = ''; for (let n = x.previousSibling; n; n = n.previousSibling) t += n.textContent || ''; return !!t.trim(); });
    if (!b) return null;
    let prev = b.previousSibling;
    while (prev && !(prev.textContent || '').trim()) prev = prev.previousSibling;
    const r = document.createRange(); r.selectNode(prev);
    const pr = [...r.getClientRects()].pop(), br = b.getClientRects()[0];
    return pr && br ? { word: b.textContent, dy: Math.round(br.top - pr.top), disp: getComputedStyle(b).display } : null;
  });
  ok('первый абзац «Налогов» одним абзацем: жирное «' + (sameLine && sameLine.word) + '» в строке с текстом перед ним',
    !!sameLine && Math.abs(sameLine.dy) <= 4 && sameLine.disp === 'inline', JSON.stringify(sameLine));
  await page.click('#ex-body p.ex-q > b');
  await settle(page, 300);
  const e2 = await exInfo(page);
  ok('щелчок по вопросу раскрывает ровно его ответ', e2.aVis === 1, JSON.stringify(e2));
  const h1 = await histState(page);
  ok('щелчки по полосе и вопросу — не шаг истории, ссылка та же', h0.undo === h1.undo && h0.can === h1.can && h0.link === h1.link, JSON.stringify([h0.undo, h1.undo, h0.can, h1.can]));
  await page.evaluate(() => { pickScene('sd'); closePicker(); redrawAll(); });
  await settle(page, 600);
  await page.evaluate(() => { pickScene('taxes'); closePicker(); redrawAll(); });
  await settle(page, 600);
  const e3 = await exInfo(page);
  ok('смена модели и назад → снова свёрнут', !e3.shown && !e3.fold, JSON.stringify(e3));
  for (const [k, word] of [['ppfsum', '1 вопрос'], ['ppf', '5 вопросов'], ['sd', null]]) {
    await page.evaluate((x) => { pickScene(x); closePicker(); redrawAll(); }, k);
    await settle(page, 600);
    const e = await exInfo(page);
    if (word) ok(k + ': «Разбор · ' + word + '»', e.barText === 'Разбор ' + word, e.barText);
    else ok(k + ': число вопросов совпадает с числом вопросов', e.q === 0 ? e.barText === 'Разбор' : e.barText.endsWith(String(e.q) + (e.q === 1 ? ' вопрос' : e.q < 5 ? ' вопроса' : ' вопросов')), e.barText + ' / ' + e.q);
  }
  ok('ошибок страницы нет', !errors.length, errors.slice(0, 3).join(' | '));
  const bk = [];
  for (const key of KEYS) {
    await page.evaluate((x) => { pickScene(x); closePicker(); redrawAll(); }, key);
    await settle(page, 350);
    const kids = await blockKids(page);
    if (kids.length) bk.push(key + ': ' + kids.slice(0, 2).join(', '));
  }
  ok(KEYS.length + ' моделей: в абзацах «Разбора» нет блочных потомков', !bk.length, bk.join(' | '));
  await ctx.close();
  {
    const P = await openPage(1000, 800, 'taxes', null);
    await P.page.evaluate(() => document.getElementById('btn-answer').click());
    await settle(P.page, 500);
    const e = await exInfo(P.page);
    ok('1000: полоса есть и свёрнута', e.bar && !e.shown && !e.fold && /4 вопроса/.test(e.barText), JSON.stringify(e));
    await P.ctx.close();
  }
  {
    const P = await openPage(390, 844, 'taxes', null);
    await P.page.evaluate(() => document.querySelector('#ph-tabs .ph-tab[data-tab="ex"]').click());
    await settle(P.page, 500);
    const e = await exInfo(P.page);
    ok('390: вкладка «Разбор» раскрыта, полосы нет', !e.bar && e.fold && e.qVis === 4, JSON.stringify(e));
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
  if (want('А2')) await sectionA2();
  if (want('Б')) await sectionB();
  await browser.close();
}
console.log('\nИТОГ answer_panel_probe: ' + (total - bad) + ' из ' + total + (bad ? ', провалов ' + bad : ', всё сошлось'));
process.exit(bad ? 1 : 0);
