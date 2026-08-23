/* Фаза 10 — буква-параметр в зависимости от МЕСТА в формуле.
   Жалоба с созвона: буква то двигает график, то нет. Проверяем внутри ОДНОЙ
   модели («Малая открытая экономика»), не выходя из неё.
     node calc2/tests/night2_phase10_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin'); await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

// Три записи из жалобы плюс ещё четыре места буквы — чтобы закрытие
// «не воспроизводится» опиралось не на три случая, а на семь.
const VARIANTS = ['100 - a', '100 - Q*a', '100 - a*Q', 'a - Q', '100 - Q/a', '100*a - Q', '100 - aQ'];
const out = {};
for (const v of VARIANTS) {
  out[v] = await page.evaluate((expr) => {
    const r = x => (x == null || isNaN(x)) ? null : Math.round(x * 1e4) / 1e4;
    resetSceneMemory(); pickScene('smallopen'); redrawAll();
    // Набираем формулу в поле спроса — тем же путём, что человек.
    const inp = document.getElementById('curve-expr-1');
    if (!inp) return { error: 'поля спроса нет' };
    inp.value = expr; inp.dispatchEvent(new Event('input', { bubbles: true }));
    redrawAll(); if (typeof updatePult === 'function') updatePult();
    const c = STATE.curves.filter(x => x.id === 1)[0];
    const chipOf = (name) => {
      const box = document.getElementById('params-body');
      if (!box) return null;
      const chips = [].slice.call(box.querySelectorAll('.pchip'));
      for (const ch of chips) {
        const t = (ch.textContent || '');
        if (t.indexOf(name) >= 0 && !/Сдвиг/.test(t)) return ch;
      }
      return null;
    };
    const readNums = () => {
      const norm = e => (e ? (e.textContent || '').replace(/\s+/g, ' ').trim() : '');
      return {
        eq: STATE.eq ? { Q: r(STATE.eq.Q), P: r(STATE.eq.P) } : null,
        curveAt: [10, 30, 50].map(q => r(evalCurve(c, q))),
        open: norm(document.getElementById('info-open')).slice(0, 160),
      };
    };
    const before = readNums();
    const chip = chipOf('a');
    const sl = chip ? chip.querySelector('input[type=range]') : null;
    let after = null, moved = null;
    if (sl) {
      const v0 = parseFloat(sl.value);
      const mn = parseFloat(sl.min), mx = parseFloat(sl.max);
      const v1 = (v0 + (mx - mn) * 0.25 <= mx) ? v0 + (mx - mn) * 0.25 : v0 - (mx - mn) * 0.25;
      sl.value = String(v1); sl.dispatchEvent(new Event('input', { bubbles: true }));
      redrawAll();
      after = readNums();
      moved = { from: r(v0), to: r(v1) };
    }
    return {
      exprStored: c ? c.expr : null,
      srcForm: c ? c.srcForm : null,
      paramsInState: Object.keys(STATE.params || {}),
      paramValue: (STATE.params || {}).a,
      sliderAppeared: !!sl,
      moved,
      before, after,
      curveChanged: (after && before) ? JSON.stringify(before.curveAt) !== JSON.stringify(after.curveAt) : null,
      numbersChanged: (after && before) ? JSON.stringify(before.eq) + before.open !== JSON.stringify(after.eq) + after.open : null,
    };
  }, v);
}
console.log(JSON.stringify(out, null, 1));
if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 5).join(' | '));
await browser.close();
