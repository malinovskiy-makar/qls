/* Рецепты состояний сайта под эталоны макета (reference/INDEX.md).
   Набор → список { file, w, h, theme, key, run(page), pending }.
   pending — рецепт появится вместе с частью нового экрана, которой он нужен. */

const KEYS = ['m-graph', 'm-transform', 'm-optimum', 'm-tangent', 'm-minmax', 'm-constraint', 'ppf', 'ppfsum', 'trade',
  'tradeprice', 'sd', 'sdsum', 'taxes', 'ceil', 'quota', 'elast', 'ext', 'prod', 'costs', 'plants', 'isoquant', 'mono',
  'mono-nat', 'mono-d1', 'mono-d3', 'mono-kink', 'labor', 'labor-mono', 'labor-union', 'labor-bilat', 'smallopen',
  'monoexport', 'consumer', 'cons-slutsky', 'adas', 'islm', 'phillips', 'money', 'loanable', 'fx', 'ineq', 'laffer'];
const DARK = ['sd', 'taxes', 'ceil', 'mono', 'costs', 'm-tangent', 'islm', 'ppf', 'labor'];
const N1280 = ['sd', 'taxes', 'ceil', 'mono', 'costs', 'm-tangent'];

export const RECIPES = {
  models: KEYS.map(k => ({ file: k + '.png', w: 1440, h: 760, key: k })),
  models_dark: DARK.map(k => ({ file: k + '.png', w: 1440, h: 760, key: k, theme: 'dark' })),
  models_1280: N1280.map(k => ({ file: k + '.png', w: 1280, h: 700, key: k })),
};

/* ── Рецепты состояний нового экрана (фазы 5б–10) ───────────────────────── */
const W = 1440, H = 760;
const ev = (js) => async (page) => { await page.evaluate(js); await page.waitForTimeout(400); };
const click = (sel) => async (page) => { await page.click(sel); await page.waitForTimeout(400); };
const seq = (...fs) => async (page) => { for (const f of fs) await f(page); };
const typeIn = (inputId, text) => async (page) => {
  await page.evaluate((id) => { const i = document.getElementById(id); const mf = i && i._mf; if (mf) { mf.focus(); mf.executeCommand('moveToMathfieldEnd'); } }, inputId);
  await page.waitForTimeout(150);
  await page.keyboard.type(text, { delay: 30 });
  await page.waitForTimeout(500);
};
const pie = "(function(){ var i = document.getElementById('curve-expr-2'); i.value = '(Q >= 0 and Q < 40) ? 0.5*Q + 10 : (Q >= 40 ? 2*Q - 50 : NaN)'; i.dispatchEvent(new Event('input', {bubbles:true})); i.dispatchEvent(new Event('change', {bubbles:true})); })()";
const ST = [
  { file: 'selfcheck.png', key: 'taxes', run: click('#btn-self') },
  { file: 'selfcheck_dark.png', key: 'taxes', theme: 'dark', run: click('#btn-self') },
  { file: 'iv_subsidy.png', key: 'taxes', run: ev("setType('subsidy'); setTax(20); redrawAll();") },
  { file: 'iv_vat.png', key: 'taxes', run: ev("setTaxForm('vat'); setTax(20); redrawAll();") },
  { file: 'iv_excise.png', key: 'taxes', run: ev("setTaxForm('excise'); setTax(20); redrawAll();") },
  { file: 'mono_quota.png', key: 'mono', run: ev("setType('quota'); redrawAll();") },
  { file: 'iv_buyer.png', key: 'taxes', run: ev("setTaxSide('buyer'); redrawAll();") },
  { file: 'iv_ghost.png', key: 'taxes', run: click('#chk-ghost') },
  { file: 'ceil_floor.png', key: 'ceil', run: ev("setType('floor'); redrawAll();") },
  { file: 'mono_tax.png', key: 'mono', run: seq(ev("setType('tax'); setTax(20); redrawAll();"), click('#chk-ghost')) },
  { file: 'costs_loss.png', key: 'costs', run: ev("var s = document.getElementById('lr-price-slider'); s.value = 8; s.dispatchEvent(new Event('input', {bubbles:true}));") },
  { file: 'tangent_secant.png', key: 'm-tangent', run: ev("var c = document.getElementById('chk-secant') || document.querySelector('#math-secant-row input[type=checkbox]'); if (c) c.click();") },
  { file: 'sd_qp.png', key: 'sd', run: ev("var i = document.getElementById('curve-expr-1'); i.value = '120 - 2*P'; i.dispatchEvent(new Event('input', {bubbles:true})); i.dispatchEvent(new Event('change', {bubbles:true}));") },
  { file: 'sd_letter.png', key: 'sd', run: ev("var i = document.getElementById('curve-expr-1'); i.value = '100 - a*Q'; i.dispatchEvent(new Event('input', {bubbles:true})); i.dispatchEvent(new Event('change', {bubbles:true}));") },
  { file: 'sd_hidden.png', key: 'sd', run: click('#curve-list .fc-card:nth-child(1) .fc-eye') },
  { file: 'sd_extra.png', key: 'sd', run: click('#btn-add-curve') },
  { file: 'kp_armed.png', key: 'taxes', run: ev("armCurve('D');") },
  { file: 'kp_tip.png', key: 'taxes', run: seq(ev("armCurve('D');"), async (page) => { const p = await page.evaluate(() => { const c = document.querySelectorAll('#chart g.cross-item circle')[1] || document.querySelector('#chart g.cross-item circle'); const r = c.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }); await page.mouse.move(p[0], p[1]); await page.waitForTimeout(400); }) },
  { file: 'kp_tip_dark.png', key: 'taxes', theme: 'dark', run: seq(ev("armCurve('D');"), async (page) => { const p = await page.evaluate(() => { const c = document.querySelectorAll('#chart g.cross-item circle')[1] || document.querySelector('#chart g.cross-item circle'); const r = c.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }); await page.mouse.move(p[0], p[1]); await page.waitForTimeout(400); }) },
  { file: 'tool_point.png', key: 'sd', run: click('#tool-point') },
  { file: 'tool_area.png', key: 'sd', run: click('#tool-area') },
  { file: 'pw_card.png', key: 'taxes', run: ev(pie) },
  // Окно кусочной у кусочной функции открывается щелчком по записи скобкой (README 6.6).
  { file: 'pw_modal.png', key: 'taxes', run: seq(ev(pie), ev('renderCurveList();'), click('#curve-list .fc-card:nth-child(2) .fc-pwrec')) },
  { file: 'pw_modal_dark.png', key: 'taxes', theme: 'dark', run: seq(ev(pie), ev('renderCurveList();'), click('#curve-list .fc-card:nth-child(2) .fc-pwrec')) },
  { file: 'kbd.png', key: 'sd', run: click('#curve-list .fc-card:nth-child(1) .f-kbd') },
  { file: 'pop_switcher.png', key: 'taxes', run: click('#model-switch') },
  { file: 'pop_view.png', key: 'taxes', run: click('#btn-view') },
  { file: 'pop_share.png', key: 'taxes', run: click('#btn-share') },
  { file: 'pop_export.png', key: 'taxes', run: click('#dock-export') },
  { file: 'pop_help.png', key: 'taxes', run: click('#btn-howto') },
  { file: 'pop_more.png', key: 'sd', run: click('#curve-list .fc-card:nth-child(1) .crow-gear') },
  { file: 'pop_more_extra.png', key: 'sd', run: seq(click('#btn-add-curve'), click('#curve-list .fc-card:nth-child(3) .crow-gear')) },
  { file: 'pop_color.png', key: 'sd', run: click('#curve-list .fc-card:nth-child(1) .cpick-btn') },
  { file: 'picker.png', key: null },
  { file: 'picker_dark.png', key: null, theme: 'dark' },
  { file: 'picker_search.png', key: null, run: ev("var i = document.getElementById('picker-search'); i.value = 'налог'; i.dispatchEvent(new Event('input'));") },
  { file: 'picker_search_none.png', key: null, run: ev("var i = document.getElementById('picker-search'); i.value = 'зззз'; i.dispatchEvent(new Event('input'));") },
  { file: 'palette_alt.png', key: 'taxes', pending: 'другая палитра сайта — доска-иллюстрация макета, на сайте одна палитра' },
  { file: 'sd_error.png', key: 'sd', run: typeIn('curve-expr-1', ' +') },
  { file: 'fn_focus.png', key: 'sd', run: ev("var i = document.getElementById('curve-expr-1'); if (i._mf) i._mf.focus(); else i.focus();") },
  { file: 'toast_reset.png', key: 'taxes', run: seq(ev("setTax(45); redrawAll();"), click('#btn-model-reset')) },
  { file: 'undo_enabled.png', key: 'taxes', run: typeIn('curve-expr-1', '-10') },
  { file: 'selfcheck_verdicts.png', key: 'taxes', run: seq(click('#btn-self'), ev("var a = document.querySelectorAll('.self-inp'); a[0].value = '35'; a[0].dispatchEvent(new Event('input')); a[1].value = '99'; a[1].dispatchEvent(new Event('input')); document.querySelectorAll('.self-check')[0].click(); document.querySelectorAll('.self-check')[1].click();")) },
  { file: 'picker_preview.png', key: null, run: async (page) => { await page.evaluate(() => { if (typeof selectPickerTab === 'function') selectPickerTab('Несовершенная конкуренция', false); }); const r = await page.$('#scene-picker .scard[data-scene="mono"]'); if (r) await r.hover(); await page.waitForTimeout(400); } },
  { file: 'kp_pinned.png', key: 'taxes', run: seq(ev("armCurve('D');"), async (page) => { const p = await page.evaluate(() => { const c = document.querySelectorAll('#chart g.cross-item circle')[1] || document.querySelector('#chart g.cross-item circle'); const r = c.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }); await page.mouse.move(p[0], p[1]); await page.waitForTimeout(400); await page.evaluate(() => { const pin = document.querySelector('#chart .cross-pin'); if (pin) pin.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); await page.waitForTimeout(400); }) },
  { file: 'focus_mode.png', key: 'taxes', run: click('#btn-focus') },
  { file: 'marks.png', key: 'sd', run: ev("var m = newMark(30, 70, null, 'coords'); STATE.marks.push(m); renderMarkList(); redrawAll();") },
];
RECIPES.states = ST.map(r => Object.assign({ w: W, h: H }, r));
const PH = ['taxes', 'sd', 'mono', 'costs', 'm-tangent', 'islm'];
RECIPES.phone = [];
PH.forEach(k => [['left', 'cond'], ['answer', 'ans'], ['explain', 'ex']].forEach(([n, tab]) => {
  RECIPES.phone.push({ file: k + '_' + n + '.png', w: 390, h: 844, dpr: 2, mobile: true, key: k,
    run: ev("document.querySelector('#ph-tabs .ph-tab[data-tab=\"" + tab + "\"]').click();") });
}));
RECIPES.phone.push({ file: 'taxes_dark.png', w: 390, h: 844, dpr: 2, mobile: true, key: 'taxes', theme: 'dark' });
RECIPES.models_1280 = N1280.map(k => ({ file: k + '.png', w: 1280, h: 700, key: k }));

/* Приёмка (фаза 11): все 42 модели в тёмной теме (у макета тёмных досок 9 —
   у остальных в листе «эталона нет»), ширина 1024 с закрытым и открытым
   «Ответом», лист «Действия» на телефоне. */
RECIPES.models_dark_all = KEYS.map(k => ({ file: k + '.png', w: 1440, h: 760, key: k, theme: 'dark',
  note: DARK.includes(k) ? '' : 'тёмной доски в макете нет' }));
const N1024 = ['sd', 'taxes', 'mono', 'costs', 'm-tangent', 'islm'];
RECIPES.w1024 = [];
N1024.forEach(k => {
  RECIPES.w1024.push({ file: k + '.png', w: 1024, h: 768, key: k });
  RECIPES.w1024.push({ file: k + '_answer.png', w: 1024, h: 768, key: k, run: click('#btn-answer') });
});
RECIPES.phone.push({ file: 'taxes_more.png', w: 390, h: 844, dpr: 2, mobile: true, key: 'taxes', run: click('#btn-ph-more') });
