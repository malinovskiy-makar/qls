/* Ночная сессия. ФАЗА 6 — переключение излишков (с редизайна 10.2026 — галочки CS и PS в «Показать на графике»).
     node calc2/tests/night_phase6_areas_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

let ok = true;
const rep = (n, pass, d) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + n + (d ? '  -> ' + d : '')); if (!pass) ok = false; };

const r = await page.evaluate(async () => {
  const wait = ms => new Promise(res => setTimeout(res, ms));
  const fills = () => [...document.querySelectorAll('#chart [data-legend]')]
    .map(e => e.getAttribute('data-legend')).sort();
  /* ПЕРЕНАЦЕЛЕНО (редизайн 10.2026, пункт (е) закрытого списка, README макета 6.4):
     общая галочка «Показать излишки» гаечного ключа заменена двумя галочками
     CS и PS в секции «Показать на графике». Проверки по смыслу прежние: галочки
     на своём месте, старого органа нет, выключение гасит обе заливки и оба
     признака, включение возвращает как было, галочки показывают состояние
     модели, у монополии свои три галочки. */
  resetSceneMemory(); pickScene('sd'); await wait(400);
  const cs = document.getElementById('chk-cs'), ps = document.getElementById('chk-ps');
  const sec = document.getElementById('sec-show');
  const inWrench = !!(cs && ps && sec && sec.contains(cs) && sec.contains(ps));
  const oldChk = !!document.getElementById('chk-areas');
  const on = fills();
  const setBoth = (v) => [cs, ps].forEach(c => { c.checked = v; c.dispatchEvent(new Event('change', { bubbles: true })); });
  setBoth(false);
  await wait(350);
  const off = fills();
  const st = { showCS: STATE.showCS, showPS: STATE.showPS };
  setBoth(true);
  await wait(350);
  const back = fills();
  // Состояние модели → галочки: признак сняли в модели, галочка это показывает.
  STATE.showCS = false; STATE.showPS = false;
  syncViewFields();
  const afterSync = cs.checked || ps.checked;
  STATE.showCS = true; STATE.showPS = true; syncViewFields();
  // Излишки монополии — свои галочки, общие их не трогают.
  pickScene('mono'); await wait(350);
  const monoChk = ['chk-mono-cs', 'chk-mono-ps', 'chk-mono-vc'].filter(id => document.getElementById(id)).length;
  return { inWrench, oldChk, on, off, back, st, afterSync, monoChk };
});
console.log(JSON.stringify(r, null, 1));
rep('галочки CS и PS лежат в «Показать на графике»', r.inWrench);
rep('общей галочки #chk-areas больше нет', !r.oldChk);
const has = (arr, t) => arr.some(x => x.indexOf(t) >= 0);
rep('включён — заливки CS и PS на холсте', has(r.on, '(CS)') && has(r.on, '(PS)'), r.on.join(','));
rep('выключен — обеих заливок нет', !has(r.off, '(CS)') && !has(r.off, '(PS)'), '[' + r.off.join(',') + ']');
rep('выключение гасит оба признака', r.st.showCS === false && r.st.showPS === false, JSON.stringify(r.st));
rep('обратно — заливки вернулись как были', JSON.stringify(r.back) === JSON.stringify(r.on),
    r.back.join(',') + ' vs ' + r.on.join(','));
rep('галочки показывают текущее состояние модели', r.afterSync === false, 'галочка=' + r.afterSync);
rep('три галочки излишков монополии на месте', r.monoChk === 3, 'их ' + r.monoChk);
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'излишки переключаются галочками CS и PS' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
