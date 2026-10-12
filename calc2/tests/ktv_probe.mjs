/* КТВ НЕ УХОДИТ ПОД КПВ — постоянные проверки починки 13.10.2026 (ADR 0147).

     ./venv313/bin/python manage.py runserver 8099 --noreload --settings=config.settings_check
     node calc2/tests/ktv_probe.mjs

   Что сломалось. classifyPpf подгонял форму КПВ по четырём точкам (20, 40, 60,
   80 % от Xmax). У кусочной КПВ владельца 500 − X² / 516 − 8X / 100 − (X − 50)²
   все четыре легли на прямой участок, форма вышла «прямая, b = 8», и КТВ при
   мировой цене 7,39 уходила в угол (0; 500) — НИЖЕ КПВ.

   Что стережёт прибор:
     А. Случай владельца: производство (3,695; 486,347), касание, КТВ
        Y = 513,653 − 7,39X, предел X 69,507; на холсте линия КТВ нигде не ниже КПВ.
     Б. Свойство для набора КПВ и цен (в пределах ползунка): КТВ ≥ КПВ во всех
        1 000 узлах [0; Xmax], КТВ касается КПВ в точке производства, ценность
        выпуска Y + Pw·X там равна наибольшей по сетке. Кусочная 24.08 при
        Pw = 1 — излом (40; 80).
     В. classifyPpf: КПВ владельца не «прямая»; 100 − X, 100 − X², √(100 − X²)
        опознаются как прежде.
     Г. «Внутренняя цена X» у нелинейной КПВ — диапазон «от … до …», у прямой — число.
     Д. Страховка: точка производства сверяется с общим правилом (bestByValue)
        даже при НЕВЕРНО опознанной форме. classifyPpf подменяется старой пробой
        по четырём точкам — КТВ владельца всё равно касается КПВ и не уходит под неё.

   КПВ ставится в поле тем же мостом, что и у набора MathLive (`toInput`:
   `value` + событие `input`), мировая цена — полем (`change`), как человек.
   ⚠️ Числа точки производства — свойство КПВ, а не кадра: окно здесь не проверяется.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = process.env.ONLY || '';

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/?m=trade`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
if (!(await page.evaluate(() => typeof pickScene === 'function'))) { console.log('calc2 не загрузился'); process.exit(3); }

let bad = 0, total = 0;
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}
function near(label, got, want, tol) {
  ok(label, typeof got === 'number' && Math.abs(got - want) <= tol, 'ожидалось ' + want + ' ± ' + tol + ', получилось ' + got);
}
const want = (sec) => !ONLY || ONLY.includes(sec);

const OWNER = 'X < 4 ? 500 - X^2 : (X < 54 ? 516 - 8*X : 100 - (X - 50)^2)';
const KINK24 = 'X < 40 ? 100 - 0.5*X : 160 - 2*X';
// Кусочная, у которой все четыре старые пробы (20, 40, 60, 80 при Xmax = 100) на прямом участке.
const ON_LINE = 'X < 10 ? 1000 - 0.1*X^2 : (X < 85 ? 1010 - 2*X : 840 - 2*(X - 85) - 3.6*(X - 85)^2)';

/* Поставить КПВ и цену как человек и вернуть расчёт и замер холста. */
async function setKtv(formula, price, oldProbe) {
  return page.evaluate(async ([formula, price, oldProbe]) => {
    const W = (ms) => new Promise(r => setTimeout(r, ms));
    /* Старая проба формы (до 13.10): четыре точки, без проверки на сетке и без
       сверки свободного члена прямой с f(0). Только для раздела Д. */
    const realCls = window.classifyPpf;
    if (oldProbe) window.classifyPpf = (f) => {
      const c = realCls(f);
      if (c.type !== 'unknown' || !(c.Xmax > 0)) return c;
      const xs = [0.2, 0.4, 0.6, 0.8].map(t => c.Xmax * t), lin = fitLinear(xs, xs.map(f));
      return (lin && lin.r2 > 1 - 1e-6) ? { type: 'linear', a: c.Ymax, b: -lin.slope, Xmax: c.Xmax, Ymax: c.Ymax } : c;
    };
    try {
      const inp = document.getElementById('inp-ppft');
      if (inp.value !== formula) {
        inp.value = formula;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await W(450);                                   // дребезг поля формулы 220 мс
      }
      const pr = document.getElementById('inp-ppft-price');
      pr.value = String(price);
      pr.dispatchEvent(new Event('change', { bubbles: true }));
      await W(150);
      const d = STATE.ppfTradeData;
      if (!d || !d.ok) return { error: d && d.error };
      const f = parsePpfEquation(STATE.ppftFormula).f;
      // Свойство на 1 000 узлах [0; Xmax].
      const N = 1000, tol = 1e-6 * Math.max(1, Math.abs(d.Ymax));
      let worstBelow = 0, maxVal = -Infinity;
      for (let i = 0; i <= N; i++) {
        const x = d.Xmax * i / N, y = f(x);
        if (!isFinite(y)) continue;
        maxVal = Math.max(maxVal, y + d.ratio * x);
        if (d.line) worstBelow = Math.max(worstBelow, y - (d.line.intercept - d.ratio * x));
      }
      const atP = (d.xp != null) ? d.yp + d.ratio * d.xp : NaN;
      const touch = (d.line && d.xp != null) ? Math.abs((d.line.intercept - d.ratio * d.xp) - f(d.xp)) : NaN;
      const onPpf = (d.xp != null) ? Math.abs(f(d.xp) - d.yp) : NaN;
      // Холст: пиксели пути КТВ против пикселей пути КПВ (ось y экрана вниз).
      const pathPts = (el) => (el ? (el.getAttribute('d').match(/-?\d+(\.\d+)?(e-?\d+)?/g) || []).map(Number) : []);
      const ktvEl = document.querySelector('#chart path[data-expr-name="КТВ"]');
      const ppfEl = document.querySelector('#chart path[data-expr-name="КПВ"]');
      let pxWorst = null;
      if (ktvEl && ppfEl) {
        const k = pathPts(ktvEl), p = pathPts(ppfEl);
        const [x0, y0, x1, y1] = [k[0], k[1], k[k.length - 2], k[k.length - 1]];
        pxWorst = 0;
        for (let i = 0; i + 1 < p.length; i += 2) {
          const px = p[i], py = p[i + 1];
          if (px < Math.min(x0, x1) || px > Math.max(x0, x1)) continue;
          const ky = y0 + (y1 - y0) * (px - x0) / (x1 - x0);
          pxWorst = Math.max(pxWorst, ky - py);            // > 0 — КПВ выше КТВ на экране
        }
      }
      const t = (el) => { const c = el.cloneNode(true); c.querySelectorAll('.katex-mathml,annotation').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim(); };
      const innerRow = [...document.querySelectorAll('#info-ppft .stat')].map(t).find(s => /Внутренняя цена X/.test(s)) || '';
      return { regime: d.regime, ratio: d.ratio, xp: d.xp, yp: d.yp, line: d.line, xint: d.xint, Ymax: d.Ymax, Xmax: d.Xmax,
               priceMin: d.priceMin, priceMax: d.priceMax, worstBelow, maxVal, atP, touch, onPpf, tol, pxWorst,
               cType: d.c.type, innerRow };
    } finally { window.classifyPpf = realCls; }
  }, [formula, price, !!oldProbe]);
}

/* ── А. Случай владельца ───────────────────────────────────────────── */
if (want('А')) {
  head('А. Кусочная КПВ владельца, мировая цена 7,39');
  const r = await setKtv(OWNER, 7.39);
  ok('режим «касание»', /касание/.test(r.regime), r.regime);
  near('Xп', r.xp, 3.695, 0.001);
  near('Yп', r.yp, 486.347, 0.001);
  near('КТВ: свободный член', r.line && r.line.intercept, 513.653, 0.001);
  near('КТВ: наклон', r.line && r.line.slope, 7.39, 1e-9);
  near('предел X', r.xint, 69.507, 0.001);
  ok('на холсте КТВ нигде не ниже КПВ (≤ 0,5 px)', r.pxWorst != null && r.pxWorst <= 0.5, 'худшее ' + r.pxWorst);
}

/* ── Б. Свойство на наборе КПВ и цен ───────────────────────────────── */
if (want('Б')) {
  head('Б. КТВ ≥ КПВ, касание, наибольшая ценность выпуска');
  const PPFS = ['100 - X', '100 - X^2', 'sqrt(100 - X^2)', '(10 - sqrt(X))^2', KINK24, OWNER, ON_LINE];
  const PRICES = [0.5, 1, 2, 7.39, 8, 12, 25];
  let pairs = 0;
  for (const p of PPFS) {
    const probe = await setKtv(p, 1);
    for (const pw of PRICES) {
      if (pw < probe.priceMin - 1e-9 || pw > probe.priceMax + 1e-9) continue;   // вне ползунка этой КПВ
      const r = await setKtv(p, pw);
      pairs++;
      const tag = p + ' @ ' + pw;
      if (r.regime === 'нет торговли') { ok(tag + ': нет торговли — КТВ совпадает с КПВ', r.line == null); continue; }
      const fails = [];
      if (!(r.worstBelow <= r.tol)) fails.push('КТВ ниже КПВ на ' + r.worstBelow);
      if (!(r.touch <= r.tol)) fails.push('КТВ не проходит через точку производства: ' + r.touch);
      if (!(r.onPpf <= r.tol)) fails.push('точка не на КПВ: ' + r.onPpf);
      if (!(r.atP >= r.maxVal - r.tol)) fails.push('ценность ' + r.atP + ' < максимума ' + r.maxVal);
      if (!(r.pxWorst != null && r.pxWorst <= 0.5)) fails.push('холст: КПВ выше КТВ на ' + r.pxWorst + ' px');
      ok(tag + ' (' + r.regime + ', ' + r.cType + ')', !fails.length, fails.join('; '));
    }
  }
  ok('проверено пар КПВ × цена: ' + pairs + ' (не меньше 30)', pairs >= 30);
  const k = await setKtv(KINK24, 1);
  near('кусочная 24.08 при Pw = 1: Xп излома', k.xp, 40, 0.01);
  near('кусочная 24.08 при Pw = 1: Yп излома', k.yp, 80, 0.01);
}

/* ── В. Форма КПВ ──────────────────────────────────────────────────── */
if (want('В')) {
  head('В. classifyPpf: форма принимается только после проверки на сетке');
  const types = await page.evaluate(([o, l]) => {
    const cls = (e) => classifyPpf(parsePpfEquation(e).f);
    const own = cls(o);
    return { owner: own.type, ownerB: own.b, onLine: cls(l).type,
             lin: cls('100 - X'), par: cls('100 - X^2'), ell: cls('sqrt(100 - X^2)') };
  }, [OWNER, ON_LINE]);
  ok('КПВ владельца — НЕ прямая', types.owner !== 'linear', types.owner + (types.ownerB != null ? ', b = ' + types.ownerB : ''));
  ok('кусочная с пробами на прямом участке — НЕ прямая', types.onLine !== 'linear', types.onLine);
  ok('100 − X → linear, a = 100, b = 1', types.lin.type === 'linear' && Math.abs(types.lin.a - 100) < 1e-9 && Math.abs(types.lin.b - 1) < 1e-9, JSON.stringify(types.lin));
  ok('100 − X² → parabola', types.par.type === 'parabola', types.par.type);
  ok('√(100 − X²) → ellipse', types.ell.type === 'ellipse', types.ell.type);
}

/* ── Г. «Внутренняя цена X» ────────────────────────────────────────── */
if (want('Г')) {
  head('Г. «Внутренняя цена X»: у нелинейной КПВ диапазон, у прямой число');
  const o = await setKtv(OWNER, 7.39);
  ok('КПВ владельца: «от 0 до 20»', /=от 0 до 20$/.test(o.innerRow), o.innerRow);
  const k = await setKtv(KINK24, 1);
  ok('кусочная 24.08: «от 0,5 до 2»', /=от 0,5 до 2$/.test(k.innerRow), k.innerRow);
  const l = await setKtv('100 - 2*X', 1);
  ok('прямая 100 − 2X: одно число «2»', /=2$/.test(l.innerRow), l.innerRow);
}

/* ── Д. Страховка общим правилом ──────────────────────────────────── */
if (want('Д')) {
  head('Д. Неверная форма КПВ не уводит КТВ под КПВ (сверка с общим правилом)');
  await setKtv('100 - X', 1);                         // сбросить поле, чтобы пересчёт шёл с подменой
  const r = await setKtv(OWNER, 7.39, true);
  ok('подмена сработала: форма «прямая»', r.cType === 'linear', r.cType);
  near('Xп всё равно касание', r.xp, 3.695, 0.001);
  ok('КТВ ≥ КПВ на 1 000 узлах', r.worstBelow <= r.tol, 'худшее ' + r.worstBelow);
  ok('ценность выпуска в точке = наибольшая', r.atP >= r.maxVal - r.tol, r.atP + ' против ' + r.maxVal);
  await setKtv('100 - X', 1);
}

console.log('\nОшибок страницы: ' + errs.length + (errs.length ? '  ' + errs.slice(0, 3).join(' | ') : ''));
console.log(bad ? `ПРОВАЛОВ: ${bad} из ${total}` : `ВСЕ ${total} ПРОВЕРОК ПРОШЛИ`);
await browser.close();
process.exit(bad || errs.length ? 1 : 0);
