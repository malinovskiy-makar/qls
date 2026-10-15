// Опись панелей calc2 по 42 моделям: «Условие», «Ответ», «Разбор», подсказки, закраски, окно «Вид графика».
// Снимает то, что видит человек на старте каждой модели (1440 × 900, тёмная тема, пустая память).
// «Ответ» открывается ключом памяти calc2.v1.answerHidden = '0' (так выглядит страница у человека,
// который однажды открыл «Ответ»); «Разбор» читается целиком (textContent), даже если свёрнут.
//
//   node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs <out.json> [--toggles]
//
// --toggles: дополнительно щёлкает каждую видимую галочку «Условия» и «Вида», сравнивает «Ответ»
//            до и после (поле answerChanged) и возвращает галочку назад. Долго: ~6 минут.
// Окружение: сервер на 8099 (--settings=config.settings_check), BASE=… переопределяет адрес,
// KEYS="sd taxes" — только эти модели.
// Сессия 7: опись видит и панель режима «Точки и площади» (поле pts): во всех моделях — органы пустого режима;
// в PTS_FILL ещё и с двумя своими точками и площадью под кривой (строки и их «⋯», открытые по очереди).
import { chromium } from 'playwright';
import fs from 'fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const ALL = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer';
const KEYS = (process.env.KEYS || ALL).split(/\s+/).filter(Boolean);
const OUT = process.argv[2] || 'panels_inventory.json';
const TOGGLES = process.argv.includes('--toggles');
const PTS_FILL = ['taxes', 'm-graph', 'ineq'];

/* Органы панели «Точки и площади» (сессия 7). Ключ органа без id — тег, первый класс и подпись без цифр
   (имена точек и числа меняются, сам орган — нет). */
function ptsControls() {
  const vis = (el) => !!(el && el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const clean = (el) => {
    if (!el) return '';
    const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation, script, style, select, option').forEach(n => n.remove());
    return c.textContent.replace(/[\s   ​]+/g, ' ').trim();
  };
  const keyOf = (el, label) => {
    const cls = String(el.className || '').split(/\s+/).filter(c => c && !/^(active|open|on|editing|sc-)/.test(c))[0] || '';
    return el.tagName.toLowerCase() + (el.type && el.tagName === 'INPUT' ? ':' + el.type : '') + (cls ? '.' + cls : '') +
      '|' + String(label || '').replace(/[0-9₀-₉.,;:()\[\]−\-=\s]+/g, ' ').replace(/(^|\s)(Точка|[A-Z])(?=\s|$)/g, ' ').replace(/\s+/g, ' ').trim();
  };
  const P = document.getElementById('pts-panel');
  if (!P || !vis(P)) return { open: false, controls: [] };
  const out = [];
  P.querySelectorAll('input, select, math-field, textarea, button, .edval, [role=button], [role=checkbox]').forEach(el => {
    const box = el.type === 'checkbox' ? (el.closest('label') || el.parentElement) : el;
    if (!vis(el) && !vis(box)) return;
    let label = el.getAttribute('aria-label') || el.getAttribute('data-tip') || '';
    if (el.type === 'checkbox') { const l = el.closest('label'); label = label || (l ? clean(l) : ''); }
    if (!label) label = clean(el);
    out.push({ side: 'P', tag: el.tagName.toLowerCase(), id: el.id || '', key: el.id ? '#' + el.id : keyOf(el, label),
      label: label.slice(0, 60), popup: el.getAttribute('aria-haspopup') || '' });
  });
  const rows = {
    marks: [...P.querySelectorAll('#mark-list .mark-row, #mark-list [data-mark]')].filter(vis).length,
    areas: [...P.querySelectorAll('#info-areacalc .area-row:not(.area-head), #info-areacalc [data-area-id], #info-areacalc .area-line')].filter(vis).length,
    text: clean(P).slice(0, 600),
  };
  return { open: true, controls: out, rows };
}
/* Пункты открытого всплывающего окна (меню «⋯» строки точки или площади). */
function popItems() {
  const vis = (el) => !!(el && el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const pop = [...document.querySelectorAll('.pop.open, .pop[open], [role=menu]')].filter(vis).pop();
  if (!pop) return [];
  return [...pop.querySelectorAll('button, input, [role=menuitem], [role=menuitemcheckbox], .edval')].filter(vis).map(el => {
    const t = (el.getAttribute('aria-label') || (el.closest('label') ? el.closest('label').textContent : el.textContent) || '').replace(/\s+/g, ' ').trim();
    return { side: 'PM', tag: el.tagName.toLowerCase(), id: el.id || '', key: 'menu|' + t.replace(/[0-9]+/g, '').trim(), label: t.slice(0, 60) };
  });
}

/* Всё, что считается в странице, — одной функцией: её же зовут и до, и после щелчка. */
function pageInventory() {
  const vis = (el) => !!(el && el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const clean = (el) => {
    if (!el) return '';
    const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation, script, style, select, option').forEach(n => n.remove());
    return c.textContent.replace(/[\s   ​]+/g, ' ').trim();
  };
  const visText = (root) => {
    if (!root) return '';
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
    return out.join(' ');
  };
  const L = document.getElementById('tools-panel');
  const R = document.getElementById('params-panel');
  const V = document.getElementById('wrench-pop');
  const P = document.getElementById('pts-panel');
  const secOf = (el) => { const s = el.closest('.section, .fc-card, section, .wrench-group'); return s ? (s.id || String(s.className).slice(0, 40)) : ''; };
  const labelOf = (i) => {
    const l = i.closest('label') || (i.id && document.querySelector('label[for="' + CSS.escape(i.id) + '"]'));
    if (l) return clean(l);
    const f = i.closest('.field, .pchip, .fc-card, .row');
    return f ? clean(f).slice(0, 80) : '';
  };
  const controls = (root, side) => {
    if (!root) return [];
    const out = [];
    root.querySelectorAll('input, select, math-field, textarea, button').forEach(el => {
      const box = el.type === 'checkbox' ? (el.closest('label') || el.parentElement) : el;
      if (!vis(el) && !vis(box)) return;
      const tag = el.tagName.toLowerCase();
      const type = tag === 'input' ? el.type : tag;
      const o = { side, tag, type, id: el.id || '', sec: secOf(el) };
      if (tag === 'button') o.label = (clean(el) || el.getAttribute('aria-label') || '').slice(0, 60);
      else if (type === 'checkbox') { o.label = labelOf(el).slice(0, 80); o.checked = el.checked; }
      else if (tag === 'select') { o.label = labelOf(el).slice(0, 60); o.options = [...el.options].map(x => x.text).slice(0, 8); o.value = el.value; }
      else { o.label = labelOf(el).slice(0, 80); o.value = String(el.value || '').slice(0, 40); }
      out.push(o);
    });
    return out;
  };
  const hintSel = '.hint, .hint-row, .hint-lead, .hint-btn, .f-help:not(.f-kbd), #btn-howto, .col-note, .scope-note, .burden-note, #self-note, .ans-seg-note, .muted, .side-reset__why, .wrench-note, .pts-hint, .fc-menu-note, .crow-auto';
  const hints = [];
  [['L', L], ['R', R], ['V', V], ['P', P]].forEach(([side, root]) => {
    if (!root) return;
    root.querySelectorAll(hintSel).forEach(h => {
      if (!vis(h)) return;
      if (h.parentElement && h.parentElement.closest(hintSel)) return;
      hints.push({ side, cls: String(h.className).slice(0, 40), id: h.id || '', text: clean(h).slice(0, 300) });
    });
  });
  const tips = [...document.querySelectorAll('[data-tip]')].filter(vis).length;
  const titles = [...document.querySelectorAll('.app [title]')].filter(vis).map(e => e.getAttribute('title'));
  const groups = [...document.querySelectorAll('#ans-hero .ans-group')].filter(vis).map(g => ({
    head: clean(g.querySelector('.ans-ghead')),
    cells: [...g.querySelectorAll('.ans-cell')].filter(vis).map(c => ({
      lab: clean(c.querySelector('.ans-lab')), not: clean(c.querySelector('.ans-not')),
      val: clean(c.querySelector('.ans-val')), was: clean(c.querySelector('.ans-was')), src: c.dataset.src || '' })),
  }));
  const sb = document.getElementById('sb-body');
  const blocks = sb ? [...sb.children].filter(vis).map(blk => ({
    id: blk.id || '',
    stats: [...blk.querySelectorAll('.stat')].filter(vis).map(s => ({
      lab: clean(s.querySelector(':scope > span')), val: clean(s.querySelector(':scope > b')), text: clean(s).slice(0, 120) })),
    tables: [...blk.querySelectorAll('table')].filter(vis).map(t => [...t.querySelectorAll('tr')].filter(vis).map(tr => [...tr.children].filter(vis).map(c => clean(c)))),
    notes: [...blk.querySelectorAll('.hint, .scope-note, .muted, p')].filter(vis).map(n => clean(n).slice(0, 300)),
  })) : [];
  const ex = document.getElementById('ex-body');
  const explain = ex ? {
    questions: [...ex.querySelectorAll('p.ex-q')].map(p => clean(p.querySelector(':scope > b'))),
    text: clean(ex),
  } : { questions: [], text: '' };
  const burden = document.getElementById('ans-burden');
  const legend = {};
  document.querySelectorAll('#chart [data-legend]').forEach(e => { legend[e.getAttribute('data-legend')] = 1; });
  return {
    left: controls(L, 'L'), view: controls(V, 'V'),
    /* Органы в закрытом «⋯» видимых карточек «Условия» (сессия 5: подпись на графике, «Стандартные издержки»
       переезжают в меню карточки — README 1, судьба «переехал в «⋯»»). Меню закрыто, поэтому в left их нет. */
    menus: L ? [...L.querySelectorAll('.fc-card')].filter(vis).flatMap(card => [...card.querySelectorAll('.fc-menu input, .fc-menu button, .fc-menu select, .fc-menu textarea')]
      .map(el => ({ side: 'M', tag: el.tagName.toLowerCase(), id: el.id || '', label: (clean(el) || el.getAttribute('aria-label') || '').slice(0, 60) }))) : [],
    hints, tips, titles,
    answer: {
      open: !!(R && vis(R.querySelector('.side-inner'))),
      status: visText(document.getElementById('ans-status')),
      groups, blocks,
      burden: burden && !burden.hidden ? visText(burden) : '',
      text: visText(R),
    },
    explain, legend: Object.keys(legend),
  };
}

const browser = await chromium.launch();
const result = { base: BASE, at: new Date().toISOString(), models: {} };
for (const key of KEYS) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
  await ctx.addInitScript(() => {
    try { localStorage.clear(); localStorage.setItem('theme', 'dark'); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {}
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1300);
  // «Вид графика» читаем открытым: окно, а не модель.
  await page.evaluate(() => { const b = document.getElementById('btn-wrench') || document.querySelector('[aria-controls="wrench-pop"], #btn-view'); if (b) b.click(); });
  await page.waitForTimeout(250);
  const inv = await page.evaluate(pageInventory);
  await page.keyboard.press('Escape');
  if (TOGGLES) {
    const sig = () => page.evaluate(() => {
      const r = document.getElementById('params-panel');
      return (r ? r.textContent.replace(/\s+/g, ' ') : '');
    });
    const base = await sig();
    const boxes = await page.evaluate(() => [...document.querySelectorAll('#tools-panel input[type=checkbox], #wrench-pop input[type=checkbox]')]
      .filter(el => el.id && (el.getClientRects().length || (el.closest('label') || el.parentElement).getClientRects().length)).map(el => el.id));
    inv.toggles = {};
    for (const id of boxes) {
      if (id === 'chk-legend' || id === 'chk-quad') continue;
      await page.evaluate((i) => document.getElementById(i).click(), id);
      await page.waitForTimeout(700);
      const after = await sig();
      inv.toggles[id] = after !== base ? 'answer-changed' : 'picture-only';
      await page.evaluate((i) => document.getElementById(i).click(), id);
      await page.waitForTimeout(500);
    }
  }
  /* Панель «Точки и площади» (сессия 7): вход кнопкой холста, как у человека. */
  {
    await page.evaluate(() => { const b = document.getElementById('tool-pts'); if (b) b.click(); });
    await page.waitForTimeout(500);
    const empty = await page.evaluate(ptsControls);
    inv.pts = { empty, filled: null, menus: [] };
    if (PTS_FILL.includes(key)) {
      // Две точки щелчками по первой кривой (30 % и 60 % окна по x) и площадь под первой кривой.
      const spots = await page.evaluate(() => {
        const t = (typeof snapTargets === 'function' ? snapTargets() : []).filter(t => typeof t.f === 'function')[0];
        const { mx, my } = mainScales(null);
        const [x0, x1] = mx.domain();
        const svgEl = document.getElementById('chart');
        const r = svgEl.getBoundingClientRect();
        return [0.3, 0.6].map(k => {
          const x = x0 + (x1 - x0) * k;
          const y = t ? t.f(x) : (my.domain()[0] + my.domain()[1]) / 2;
          return [r.left + mx(x), r.top + my(isFinite(y) ? y : my.domain()[1] / 2)];
        });
      });
      for (const [cx, cy] of spots) { await page.mouse.click(cx, cy); await page.waitForTimeout(1100); }
      await page.evaluate(() => { const b = document.getElementById('ac-curve'); if (b) b.click(); });
      await page.waitForTimeout(300);
      await page.evaluate(() => { const b = document.querySelector('#ac-pick-btns .ac-cbtn'); if (b) b.click(); });
      await page.waitForTimeout(300);
      await page.evaluate(() => { const b = document.getElementById('ac-calc'); if (b && !b.disabled && b.getClientRects().length) b.click(); });
      await page.waitForTimeout(800);
      inv.pts.filled = await page.evaluate(ptsControls);
      // Меню «⋯» строк — по очереди: открыть, переписать пункты, закрыть Esc (Esc при меню закрывает только меню).
      const n = await page.evaluate(() => [...document.querySelectorAll('#pts-panel [aria-haspopup]')].filter(e => e.getClientRects().length).length);
      for (let i = 0; i < n; i++) {
        await page.evaluate((i) => { const b = [...document.querySelectorAll('#pts-panel [aria-haspopup]')].filter(e => e.getClientRects().length)[i]; if (b) b.click(); }, i);
        await page.waitForTimeout(300);
        inv.pts.menus.push(...await page.evaluate(popItems));
        await page.keyboard.press('Escape');
        await page.waitForTimeout(200);
      }
    }
  }
  inv.errors = errors;
  result.models[key] = inv;
  await ctx.close();
  process.stderr.write(key + ' ');
}
await browser.close();
fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
console.log('\nопись: ' + Object.keys(result.models).length + ' моделей → ' + OUT);
