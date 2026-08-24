/* Фаза 0 ночной сессии «четыре дефекта»: замер ДО правок.
   Каждый дефект воспроизводится руками — набором в поле, нажатием кнопок,
   а не вызовом внутренней функции. Печатает четыре замера числами и строками.
     node calc2/tests/night2_phase0_probe.mjs */
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin');
await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

const scene = async (k) => {
  await page.evaluate(key => { resetSceneMemory(); pickScene(key); }, k);
  await page.waitForTimeout(700);
};

/* Набор в поле «как человек»: чистим математическое поле и печатаем строку.
   Поле MathLive прячет обычный input, поэтому идём через math-field. */
async function typeInCurve(idx, text) {
  const sel = `#curve-expr-${idx}`;
  await page.evaluate(s => {
    const inp = document.querySelector(s);
    if (inp && inp._mf) { inp._mf.focus(); inp._mf.executeCommand('selectAll'); inp._mf.executeCommand('deleteBackward'); }
  }, sel);
  await page.waitForTimeout(150);
  await page.keyboard.type(text, { delay: 25 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(600);
}

const readCurve = (idx) => page.evaluate(i => {
  const c = (STATE.curves || []).find(c => c.id === i) || null;
  const inp = document.querySelector('#curve-expr-' + i);
  const mf = inp && inp._mf;
  let sample = null, ok = false;
  if (c) {
    try { sample = [10, 20, 30].map(q => { const v = evalCurve(c, q); return (v == null || isNaN(v)) ? null : Math.round(v * 1e6) / 1e6; }); } catch (e) {}
    ok = sample && sample.every(v => v != null);
  }
  // Нарисована ли кривая: путь с этим data-cid в SVG.
  const path = document.querySelector('#chart path[data-cid="' + i + '"], #chart [data-cid="' + i + '"] path');
  const err = document.querySelector('#curve-expr-' + i + '') ;
  const row = err && err.closest('.crow');
  const errText = row ? (row.querySelector('.f-err, .err, .curve-err') || {}).textContent : null;
  return {
    inpValue: inp ? inp.value : null,
    mfLatex: mf ? mf.value : null,
    expr: c ? c.expr : null,
    b: c && c.linear ? c.linear.b : null,
    sampleAt_10_20_30: sample, drawable: ok,
    pathInSvg: !!path,
    errText: errText ? errText.replace(/\s+/g, ' ').trim() : null,
    bad: !!(row && row.querySelector('.bad, .is-bad')),
    rowClass: row ? row.className : null,
  };
}, idx);

const readShiftChip = () => page.evaluate(() => {
  const chips = [].map.call(document.querySelectorAll('#params-curves .pchip'), ch => {
    const sl = ch.querySelector('input[type=range]');
    const lab = ch.querySelector('.pchip-label');
    const val = ch.querySelector('.pchip-val');
    const min = sl ? parseFloat(sl.min) : null, max = sl ? parseFloat(sl.max) : null, v = sl ? parseFloat(sl.value) : null;
    return {
      cid: ch.dataset.cid,
      label: (lab ? lab.textContent : '').replace(/\s+/g, ' ').trim(),
      value: (val ? val.textContent : '').replace(/\s+/g, ' ').trim(),
      slider: { min, max, value: v,
        posPercent: (sl && max > min) ? Math.round((v - min) / (max - min) * 1000) / 10 : null },
    };
  });
  return chips;
});

const out = {};

// ── Замер 1: «100-2P» без звёздочки ────────────────────────────────────
await scene('sd');
out['1_before_baseline'] = await readCurve(1);
await typeInCurve(1, '100-2P');
out['1_after_100-2P'] = await readCurve(1);
out['1_prepExpr'] = await page.evaluate(() => {
  try { return { prep: prepExpr('100-2P'), expand: expandImplicitMul('100-2P') }; }
  catch (e) { return { error: String(e) }; }
});

// ── Замер 2: «100-2*P» и положение ползунка «Сдвиг D» ─────────────────
await scene('sd');
out['2_chip_at_start'] = await readShiftChip();
await typeInCurve(1, '100-2*P');
out['2_after_typing'] = await readCurve(1);
out['2_chip_after'] = await readShiftChip();
// И контрольный случай задания: 100-Q → сдвиг +20 → переписать на 100-2*Q
await scene('sd');
await page.evaluate(() => {
  const sl = document.querySelector('#params-curves .pchip[data-cid="1"] input[type=range]');
  if (sl) { sl.value = String(parseFloat(sl.value) + 20); sl.dispatchEvent(new Event('input', { bubbles: true })); }
});
await page.waitForTimeout(500);
out['2_chip_after_shift20'] = await readShiftChip();
await typeInCurve(1, '100-2*Q');
out['2_chip_after_rewrite'] = await readShiftChip();
out['2_curve_after_rewrite'] = await readCurve(1);

// ── Замер 3: конструктор кусочной, две строки ─────────────────────────
await scene('sd');
await page.evaluate(() => {
  const inp = document.querySelector('#curve-expr-1');
  PW.rows = []; PW.n = 2;
  openPiecewise(inp, pwVarForField(inp, 'Q'));
});
await page.waitForTimeout(500);
out['3_builder_rows'] = await page.evaluate(() => ({
  n: PW.n, rows: JSON.parse(JSON.stringify(PW.rows)),
  formula: pwFormula(), latex: pwLatex(),
  preview: (document.getElementById('pw-preview') || {}).textContent,
}));
await page.click('#pw-apply');
await page.waitForTimeout(800);
out['3_field_after_apply'] = await readCurve(1);
out['3_rendered'] = await page.evaluate(() => {
  const inp = document.querySelector('#curve-expr-1');
  const mf = inp && inp._mf;
  return {
    inpValue: inp ? inp.value : null,
    mfLatex: mf ? mf.value : null,
    // То, что человек ВИДИТ в поле: текст отрисованной записи.
    seen: mf ? (mf.shadowRoot ? (mf.shadowRoot.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 300) : null) : null,
  };
});
// Есть ли на графике уход в бесконечность вне условий
out['3_curve_outside'] = await page.evaluate(() => {
  const c = (STATE.curves || []).find(c => c.id === 1);
  if (!c) return null;
  const at = q => { try { const v = evalCurve(c, q); return (v == null || isNaN(v)) ? null : Math.round(v * 1e6) / 1e6; } catch (e) { return 'ERR'; } };
  return { at_minus10: at(-10), at_0: at(0), at_20: at(20), at_50: at(50), at_100: at(100), at_200: at(200) };
});

// ── Замер 4: потолок 30 ──────────────────────────────────────────────
await scene('ceil');
out['4_scene_start'] = await page.evaluate(() => ({
  intervType: STATE.intervType, pReg: STATE.pReg,
  eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
}));
await page.evaluate(() => { setType('ceiling'); setPReg(30); });
await page.waitForTimeout(700);
out['4_after_ceiling30'] = await page.evaluate(() => {
  const norm = t => String(t == null ? '' : t).replace(/\s+/g, ' ').trim();
  return {
    state: {
      pReg: STATE.pReg, pcActive: STATE.pcActive,
      eq: STATE.eq ? { Q: STATE.eq.Q, P: STATE.eq.P } : null,
      pc: STATE.pc ? { Preg: STATE.pc.Preg, binding: STATE.pc.binding, Qd: STATE.pc.Qd, Qs: STATE.pc.Qs,
                       Qtrade: STATE.pc.Qtrade, gap: STATE.pc.gap, dwl: STATE.pc.dwl,
                       cs: STATE.pc.cs, ps: STATE.pc.ps, sw: STATE.pc.sw } : null,
    },
    secEqTitle: norm((document.querySelector('#sec-eq .section-title') || {}).textContent),
    infoEq: norm((document.getElementById('info-eq') || {}).innerText),
    infoAreas: norm((document.getElementById('info-areas') || {}).innerText),
    infoTax: norm((document.getElementById('info-tax') || {}).innerText),
    chartTexts: [].map.call(document.querySelectorAll('#chart text'), e => norm(e.textContent)).filter(Boolean),
  };
});
// Пол 70 и несвязывающие случаи — для полноты картины
for (const [k, code] of [['4_floor70', "setType('floor'); setPReg(70);"],
                         ['4_ceiling70', "setType('ceiling'); setPReg(70);"],
                         ['4_floor30', "setType('floor'); setPReg(30);"]]) {
  await scene('ceil');
  await page.evaluate(c => { (new Function(c))(); }, code);
  await page.waitForTimeout(600);
  out[k] = await page.evaluate(() => {
    const norm = t => String(t == null ? '' : t).replace(/\s+/g, ' ').trim();
    return {
      pc: STATE.pc ? { binding: STATE.pc.binding, Qd: STATE.pc.Qd, Qs: STATE.pc.Qs, gap: STATE.pc.gap, dwl: STATE.pc.dwl } : null,
      infoEq: norm((document.getElementById('info-eq') || {}).innerText),
      infoTax: norm((document.getElementById('info-tax') || {}).innerText),
    };
  });
}
// Та же болезнь у налога / субсидии / квоты?
for (const [k, code] of [['4_tax20', "setType('tax'); setTaxForm('unit'); setTaxSide('seller'); setTax(20);"],
                         ['4_subsidy20', "setType('subsidy'); setTaxKind('unit'); setTax(20);"],
                         ['4_quota40', "setType('quota'); setQuota(40); setQuotaPos(0.5);"]]) {
  await scene('taxes');
  await page.evaluate(c => { (new Function(c))(); }, code);
  await page.waitForTimeout(600);
  out[k] = await page.evaluate(() => {
    const norm = t => String(t == null ? '' : t).replace(/\s+/g, ' ').trim();
    return {
      taxEq: STATE.taxEq ? { Q: STATE.taxEq.Q, Pb: STATE.taxEq.Pb, Ps: STATE.taxEq.Ps } : null,
      qt: STATE.qt ? { Qq: STATE.qt.Qq, binding: STATE.qt.binding, P: STATE.qt.P, Plo: STATE.qt.Plo, Phi: STATE.qt.Phi } : null,
      infoEq: norm((document.getElementById('info-eq') || {}).innerText),
      infoTax: norm((document.getElementById('info-tax') || {}).innerText),
    };
  });
}

console.log(JSON.stringify(out, null, 1));
if (errs.length) console.log('\nОШИБКИ СТРАНИЦЫ:\n' + errs.slice(0, 10).join('\n'));
await browser.close();
