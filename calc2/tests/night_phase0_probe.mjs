/* Ночная сессия «левая панель». ФАЗА 0 — ВОСПРОИЗВЕДЕНИЕ ДВУХ ДЕФЕКТОВ.
   Ничего не чиним: только замеряем числа ДО правок.
     node calc2/tests/night_phase0_probe.mjs
   Дефект А — буква-параметр течёт из модели в модель.
   Дефект Б — КТВ не перестраивается от ползунка мировой цены/параметра. */
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.log('PAGEERROR:', e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

console.log('══ ДЕФЕКТ А · параметр «a» между моделями ═════════════════════');
const A = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  resetSceneMemory();
  // 1. «Малая открытая экономика»
  pickScene('smallopen'); await wait(250);
  // 2. в поле спроса — «100 - a*Q» (правка прямо в строке списка кривых)
  const inp = document.querySelector('#curve-list .curve-expr-inp');
  if (!inp) return { error: 'строка спроса не найдена' };
  inp.value = '100 - a*Q';
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(250);
  const afterType = Object.keys(STATE.params || {});
  // 3. ползунок «a» на 3
  if (STATE.params && STATE.params.a) STATE.params.a.value = 3;
  redrawAll(); await wait(200);
  const inSmallopen = JSON.parse(JSON.stringify(STATE.params || {}));
  // 4. вход в модель, где в этом сеансе не были (AD–AS — другой режим, другое семейство)
  pickScene('adas'); await wait(300);
  const inAdas = Object.keys(STATE.params || {});
  const adasValues = {}; Object.keys(STATE.params || {}).forEach(k => adasValues[k] = STATE.params[k].value);
  // 5. и ещё одна нетронутая модель того же рыночного семейства
  pickScene('ceil'); await wait(300);
  const inCeil = Object.keys(STATE.params || {});
  return { afterType, inSmallopen: Object.keys(inSmallopen), aValue: (inSmallopen.a || {}).value,
           inAdas, adasValues, inCeil };
});
console.log(JSON.stringify(A, null, 1));
console.log('  ключи в «Малой открытой» после набора: [' + (A.inSmallopen || []).join(', ') + '], a = ' + A.aValue);
console.log('  ключи в «AD–AS» (не были в этом сеансе): [' + (A.inAdas || []).join(', ') + ']');
console.log('  ключи в «Пол и потолок» (не были):        [' + (A.inCeil || []).join(', ') + ']');
console.log('  ВЕРДИКТ А: ' + (((A.inAdas || []).length || (A.inCeil || []).length)
  ? 'ДЕФЕКТ ВОСПРОИЗВЁЛСЯ — буква утекла' : 'не воспроизвёлся — параметров ноль'));

console.log('\n══ ДЕФЕКТ Б · КТВ и ползунок ══════════════════════════════════');
const B = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const geom = () => {
    // Геометрия путей КТВ: все d в холсте, длиной и хешем
    const ps = [...document.querySelectorAll('#chart path')].map(p => p.getAttribute('d') || '');
    return { n: ps.length, all: ps.map(d => d.length).join('/'), ds: ps };
  };
  resetSceneMemory();
  pickScene('trade'); await wait(400);
  // КПВ с буквой + мировая цена
  const f = document.getElementById('inp-ppft'), pr = document.getElementById('inp-ppft-price');
  if (!f) return { error: 'поле КПВ не найдено' };
  f.value = '100 - a*X';
  if (pr) pr.value = '1.5';
  document.getElementById('btn-ppft-apply').click();
  await wait(400);
  const before = geom();
  const paramsBefore = Object.keys(STATE.params || {});
  const aBefore = STATE.params && STATE.params.a ? STATE.params.a.value : null;
  const dataBefore = STATE.ppfTradeData ? { Xmax: STATE.ppfTradeData.Xmax, Ymax: STATE.ppfTradeData.Ymax,
                                            xint: STATE.ppfTradeData.xint, yint: STATE.ppfTradeData.yint } : null;
  // не трогая кнопку — подвигать ползунок параметра «a»
  let moved = false;
  const sl = [...document.querySelectorAll('#params-panel input[type=range]')]
    .find(s => (s.id || '').indexOf('ppft') < 0);
  if (sl) { sl.value = String(Math.min(parseFloat(sl.max), 2)); sl.dispatchEvent(new Event('input', { bubbles: true })); moved = true; }
  await wait(500);
  const after = geom();
  const aAfter = STATE.params && STATE.params.a ? STATE.params.a.value : null;
  const dataAfter = STATE.ppfTradeData ? { Xmax: STATE.ppfTradeData.Xmax, Ymax: STATE.ppfTradeData.Ymax,
                                           xint: STATE.ppfTradeData.xint, yint: STATE.ppfTradeData.yint } : null;
  const sameCount = before.ds.filter((d, i) => d === after.ds[i]).length;
  return { paramsBefore, aBefore, aAfter, moved, sliderId: sl ? (sl.id || '(без id)') : null,
           formulaState: STATE.ppftFormula, dataBefore, dataAfter,
           pathsBefore: before.n, pathsAfter: after.n, samePaths: sameCount,
           changed: JSON.stringify(before.ds) !== JSON.stringify(after.ds) };
});
console.log(JSON.stringify(B, null, 1));
console.log('  ВЕРДИКТ Б: ' + (B.error ? ('ошибка пробы: ' + B.error)
  : (B.changed ? 'геометрия ИЗМЕНИЛАСЬ — дефект НЕ воспроизвёлся'
               : 'геометрия НЕ изменилась — ДЕФЕКТ ВОСПРОИЗВЁЛСЯ')));

console.log('\n══ А-сплошной · обход всех 41 сцены ═══════════════════════════');
const A3 = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const keys = Object.keys(SCENE_ROUTE);
  const leaks = [], touched = [];
  for (const k of keys) {
    resetSceneMemory();
    pickScene(k); await wait(160);
    const row = document.querySelector('#curve-list .curve-expr-inp');
    const live = [...document.querySelectorAll('.section')].filter(s => s.offsetParent)
      .flatMap(s => [...s.querySelectorAll('input[type=text]')])
      .filter(i => i.value && /[A-Za-z]/.test(i.value));
    const target = row || live[0];
    if (!target) continue;
    target.value = 'a*(' + target.value + ')';
    target.dispatchEvent(new Event('input', { bubbles: true }));
    await wait(160);
    if (!Object.keys(STATE.params || {}).length) continue;
    touched.push(k);
    if (STATE.params.a) STATE.params.a.value = 3;
    redrawAll(); await wait(80);
    const nxt = keys[(keys.indexOf(k) + 7) % keys.length];
    pickScene(nxt); await wait(220);
    const got = Object.keys(STATE.params || {});
    if (got.length) leaks.push({ from: k, to: nxt, got, own: (typeof sceneExtraParams === 'function' ? sceneExtraParams() : []) });
  }
  return { total: keys.length, withLetter: touched.length, leaks };
});
console.log('  сцен обойдено: ' + A3.total + ', буква завелась в ' + A3.withLetter);
const realLeaks = (A3.leaks || []).filter(l => !(l.own || []).length);
console.log('  найдено переходов с непустыми params: ' + A3.leaks.length
  + ' (из них сцена объявляет букву САМА: ' + (A3.leaks.length - realLeaks.length) + ')');
console.log('  НАСТОЯЩИХ утечек: ' + realLeaks.length + '  ' + JSON.stringify(realLeaks));

console.log('\n══ Б-варианты · какие ползунки перестраивают КТВ ══════════════');
const B2 = await page.evaluate(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const geom = () => [...document.querySelectorAll('#chart path')].map(p => p.getAttribute('d') || '');
  const out = {};
  resetSceneMemory(); pickScene('trade'); await wait(400);
  const f = document.getElementById('inp-ppft');
  f.value = '100 - a*X';
  document.getElementById('inp-ppft-price').value = '1.5';
  document.getElementById('btn-ppft-apply').click(); await wait(350);
  const g1 = geom();
  const psl = document.getElementById('ppft-price-slider');
  if (psl) { psl.value = String(Math.min(parseFloat(psl.max), parseFloat(psl.value) + 0.7)); psl.dispatchEvent(new Event('input', { bubbles: true })); }
  await wait(500);
  out.ползунокМировойЦены_меняетГеометрию = JSON.stringify(g1) !== JSON.stringify(geom());
  resetSceneMemory(); pickScene('trade'); await wait(400);
  f.value = '100 - a*X';
  document.getElementById('btn-ppft-apply').click(); await wait(350);
  const g2 = geom();
  f.value = '80 - a*X';
  f.dispatchEvent(new Event('input', { bubbles: true })); await wait(250);
  out.праваяПоляБезКнопки_меняетГеометрию = JSON.stringify(g2) !== JSON.stringify(geom());
  out.STATE_ppftFormula_послеПравкиПоля = STATE.ppftFormula;
  const sl = [...document.querySelectorAll('#params-panel input[type=range]')].find(s => (s.id || '').indexOf('ppft') < 0);
  if (sl) { sl.value = String(Math.min(parseFloat(sl.max), 2.5)); sl.dispatchEvent(new Event('input', { bubbles: true })); }
  await wait(500);
  out.ползунокПараметра_меняетГеометрию = JSON.stringify(g2) !== JSON.stringify(geom());
  return out;
});
console.log(JSON.stringify(B2, null, 1));

await browser.close();
