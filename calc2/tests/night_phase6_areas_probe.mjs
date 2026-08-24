/* Ночная сессия. ФАЗА 6 — тумблер «Показать излишки» в меню гаечного ключа.
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
  resetSceneMemory(); pickScene('sd'); await wait(400);
  const chk = document.getElementById('chk-areas');
  const inWrench = !!(chk && document.getElementById('wrench-pop').contains(chk));
  const oldChk = !!document.getElementById('chk-cs') || !!document.getElementById('chk-ps');
  const on = fills();
  chk.checked = false; chk.dispatchEvent(new Event('change', { bubbles: true }));
  await wait(350);
  const off = fills();
  const st = { showCS: STATE.showCS, showPS: STATE.showPS };
  chk.checked = true; chk.dispatchEvent(new Event('change', { bubbles: true }));
  await wait(350);
  const back = fills();
  // Смена модели обнуляет состояние — меню обязано это показать.
  pickScene('mono'); await wait(350);
  STATE.showCS = false; STATE.showPS = false;
  syncViewFields();
  const afterSync = document.getElementById('chk-areas').checked;
  // Излишки монополии — свои галочки, тумблер их не трогает.
  const monoChk = ['chk-mono-cs', 'chk-mono-ps', 'chk-mono-vc'].filter(id => document.getElementById(id)).length;
  return { inWrench, oldChk, on, off, back, st, afterSync, monoChk };
});
console.log(JSON.stringify(r, null, 1));
rep('тумблер лежит в меню гаечного ключа', r.inWrench);
rep('старые галочки #chk-cs/#chk-ps убраны', !r.oldChk);
const has = (arr, t) => arr.some(x => x.indexOf(t) >= 0);
rep('включён — заливки CS и PS на холсте', has(r.on, '(CS)') && has(r.on, '(PS)'), r.on.join(','));
rep('выключен — обеих заливок нет', !has(r.off, '(CS)') && !has(r.off, '(PS)'), '[' + r.off.join(',') + ']');
rep('выключение гасит оба признака', r.st.showCS === false && r.st.showPS === false, JSON.stringify(r.st));
rep('обратно — заливки вернулись как были', JSON.stringify(r.back) === JSON.stringify(r.on),
    r.back.join(',') + ' vs ' + r.on.join(','));
rep('меню показывает текущее состояние модели', r.afterSync === false, 'галочка=' + r.afterSync);
rep('три галочки излишков монополии на месте', r.monoChk === 3, 'их ' + r.monoChk);
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'излишки переключаются одним тумблером из меню графика' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
