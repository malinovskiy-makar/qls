/* Фаза 11 (б) и (в) — КТВ по кусочной КПВ и повторное построение.
     node calc2/tests/night2_phase11bc_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin'); await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const out = await page.evaluate(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const norm = t => String(t == null ? '' : t).replace(/\s+/g, ' ').trim();
  const r4 = v => (v == null || isNaN(v)) ? null : Math.round(v * 1e4) / 1e4;
  const snap = () => {
    const d = STATE.ppfTradeData;
    return {
      formula: STATE.ppftFormula,
      price: STATE.ppftPrice,
      данные: d ? { ok: d.ok, режим: d.regime, error: d.error || null,
                    Xп: r4(d.xp), Yп: r4(d.yp), Xмакс: r4(d.xint), Yмакс: r4(d.yint),
                    линияЕсть: !!d.line } : null,
      табло: norm((document.getElementById('info-ppft') || {}).innerText).slice(0, 200),
      paths: document.querySelectorAll('#chart path').length,
      ктвНаХолсте: [].map.call(document.querySelectorAll('#chart text'), e => norm(e.textContent)).filter(t => t === 'КТВ').length,
      err: [].map.call(document.querySelectorAll('.error'), e => e.getClientRects().length ? norm(e.textContent) : '').filter(Boolean).join(' / '),
    };
  };
  const setField = (v) => {
    const f = document.getElementById('inp-ppft');
    f.value = v;
    ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
    f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  };
  const build = () => {
    const b = [].slice.call(document.querySelectorAll('#tools-panel button'))
      .filter(x => /Постро/i.test(x.textContent || '') && x.getClientRects().length)[0];
    if (b) { b.click(); return b.id || norm(b.textContent); }
    return null;
  };
  const r = {};
  resetSceneMemory(); pickScene('trade'); setToolsOpen(true); await sleep(700);
  setField('100 - X'); await sleep(300);
  r['0_начало'] = snap();
  r['0_кнопка'] = build(); await sleep(600);
  r['1_КТВ_по_прямой_КПВ'] = snap();

  // (б) кусочная КПВ
  resetSceneMemory(); pickScene('trade'); setToolsOpen(true); await sleep(700);
  setField('(X >= 0 and X < 40) ? 100 - X : (X >= 40 ? 80 - 0.5*X : NaN)'); await sleep(500);
  r['2_кусочная_в_поле'] = snap();
  r['2_кнопка'] = build(); await sleep(700);
  r['3_КТВ_по_кусочной'] = snap();

  // (в) построили → поменяли формулу → построили снова
  resetSceneMemory(); pickScene('trade'); setToolsOpen(true); await sleep(700);
  setField('100 - X'); await sleep(300);
  build(); await sleep(600);
  r['4_построили_первый_раз'] = snap();
  setField('80 - 2*X'); await sleep(500);
  r['5_сменили_формулу'] = snap();
  build(); await sleep(700);
  r['6_построили_снова'] = snap();

  /* (в) ещё раз, но новой формулой с ДРУГИМ наклоном. «80 − 2·X» даёт
     внутреннюю цену ровно 2 — она равна мировой, и «нет торговли» это
     правильный ответ, а не отказ строить. */
  resetSceneMemory(); pickScene('trade'); setToolsOpen(true); await sleep(700);
  setField('100 - X'); await sleep(300); build(); await sleep(600);
  r['7_первое_построение'] = snap();
  setField('60 - 3*X'); await sleep(400);
  r['8_другая_формула'] = snap();
  build(); await sleep(700);
  r['9_построили_снова'] = snap();
  setField('100 - 0.5*X'); await sleep(400); build(); await sleep(700);
  r['10_и_ещё_раз'] = snap();

  /* (б) КАСАНИЕ В ИЗЛОМЕ. Липнуть к излому касательная обязана только у
     ВОГНУТОЙ КПВ — там альтернативная стоимость X растёт, и угол выгоднее
     обоих концов. Куски: Y = 100 − 0,5·X при X < 40 (наклон 0,5) и
     Y = 160 − 2·X при X ≥ 40 (наклон 2), стык в (40; 80), ось при X = 80.
     Мировая цена 1 лежит между наклонами, значит оптимум ровно в изломе:
       весь X   → 80 · 1 = 80
       весь Y   → 100
       излом    → 40 · 1 + 80 = 120  ← наибольшее
     Для сравнения та же проверка на ВЫПУКЛОЙ кусочной (наклоны 1 и 0,5):
     там альтернативная стоимость падает, и правильный ответ — угол, а не излом. */
  const setPrice = async (v) => {
    const pr = document.getElementById('inp-ppft-price');
    pr.value = String(v); pr.dispatchEvent(new Event('change', { bubbles: true }));
    await sleep(500);
  };
  resetSceneMemory(); pickScene('trade'); setToolsOpen(true); await sleep(700);
  setField('(X >= 0 and X < 40) ? 100 - 0.5*X : (X >= 40 ? 160 - 2*X : NaN)'); await sleep(400);
  await setPrice(1); build(); await sleep(700);
  r['11_вогнутая_касание_в_изломе'] = snap();
  resetSceneMemory(); pickScene('trade'); setToolsOpen(true); await sleep(700);
  setField('(X >= 0 and X < 40) ? 100 - X : (X >= 40 ? 80 - 0.5*X : NaN)'); await sleep(400);
  await setPrice(0.75); build(); await sleep(700);
  r['12_выпуклая_угол'] = snap();
  return r;
});
console.log(JSON.stringify(out, null, 1));
if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 6).join(' | '));
await browser.close();
