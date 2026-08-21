/* Ночная сессия «левая панель». ФАЗА 3 — «Вернуть исходный вид».
   Замер: заводим параметр, двигаем его, правим формулу, жмём кнопку —
   и сверяем, что модель вернулась к исходному виду ПОЛНОСТЬЮ.
     node calc2/tests/night_phase3_reset_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.log('PAGEERROR:', e.message));
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
  const geom = () => [...document.querySelectorAll('#chart path')].map(p => p.getAttribute('d') || '');
  resetSceneMemory();
  pickScene('sd'); await wait(400);
  const start = { curves: STATE.curves.map(c => c.expr), geom: geom(), params: Object.keys(STATE.params || {}) };
  // портим модель: буква в спросе, ползунок на 3, лишняя точка
  const inp = document.querySelector('#curve-list .curve-expr-inp');
  inp.value = '100 - a*Q'; inp.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(250);
  if (STATE.params.a) STATE.params.a.value = 3;
  redrawAll(); await wait(250);
  const dirty = { curves: STATE.curves.map(c => c.expr), geom: geom(),
                  params: Object.keys(STATE.params || {}), aVal: (STATE.params.a || {}).value };
  // кнопка «Вернуть исходный вид»
  document.getElementById('btn-scene-reset').click();
  await wait(500);
  const back = { curves: STATE.curves.map(c => c.expr), geom: geom(), params: Object.keys(STATE.params || {}) };
  return { start, dirty, back };
});

console.log(JSON.stringify(r, (k, v) => k === 'geom' ? ('' + v.length + ' путей, ' + v.join('').length + ' симв.') : v, 1));
rep('до правки параметров ноль', r.start.params.length === 0, JSON.stringify(r.start.params));
rep('после набора буква завелась и уехала на 3', r.dirty.params.join() === 'a' && r.dirty.aVal === 3,
    JSON.stringify(r.dirty.params) + ' a=' + r.dirty.aVal);
rep('после кнопки параметров снова ноль', r.back.params.length === 0, JSON.stringify(r.back.params));
rep('после кнопки формулы кривых как в начале', JSON.stringify(r.back.curves) === JSON.stringify(r.start.curves),
    JSON.stringify(r.back.curves) + ' vs ' + JSON.stringify(r.start.curves));
rep('после кнопки геометрия как в начале', JSON.stringify(r.back.geom) === JSON.stringify(r.start.geom),
    'путей ' + r.back.geom.length + ' vs ' + r.start.geom.length);
rep('порча вообще меняла картинку (иначе проба слепа)', JSON.stringify(r.dirty.geom) !== JSON.stringify(r.start.geom));

await browser.close();
console.log('\nИТОГ: ' + (ok ? '«Вернуть исходный вид» возвращает модель полностью' : 'ВОЗВРАТ НЕПОЛНЫЙ'));
process.exit(ok ? 0 : 1);
