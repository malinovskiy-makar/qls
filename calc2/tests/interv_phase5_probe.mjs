// Фаза 5 — внешние эффекты по-новому. Поля издержек убраны; MSB и MSC заданы
// во «Вводе функций», по умолчанию равны частным кривым и ВЫКЛЮЧЕНЫ; кривые
// D и S не переименовываются; оптимум там, где MSB = MSC.
//   node calc2/tests/interv_phase5_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let ok = true;
function check(label, got, want, tol) {
  const good = typeof got === 'number' && isFinite(got) && Math.abs(got - want) <= tol;
  if (!good) ok = false;
  console.log((good ? 'OK   ' : 'FAIL ') + label + ' = ' +
    ((typeof got === 'number') ? got.toFixed(4) : String(got)) + ' (ожид ' + want + ' ±' + tol + ')');
}
function flag(label, cond, detail) {
  if (!cond) ok = false;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (detail ? '  -> ' + detail : ''));
}

// --- 1. Исходное состояние: чекбоксы выключены, расхождения нет ---------
const start = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ext'); redrawAll();
  var e = STATE.ext || {};
  var names = [].map.call(document.querySelectorAll('#chart text.curve-name'), function (t) { return t.textContent.trim(); });
  var labels = [].map.call(document.querySelectorAll('#chart text'), function (t) { return t.textContent.trim(); });
  return { Qmkt: e.Qmkt, Pmkt: e.Pmkt, Qopt: e.Qopt, dwl: e.dwl,
           msbOn: STATE.msbOn ? 1 : 0, mscOn: STATE.mscOn ? 1 : 0,
           msbExpr: STATE.msbExpr, mscExpr: STATE.mscExpr,
           boxMsb: document.getElementById('chk-msb').checked ? 1 : 0,
           boxMsc: document.getElementById('chk-msc').checked ? 1 : 0,
           valMsb: document.getElementById('inp-msb').value,
           valMsc: document.getElementById('inp-msc').value,
           curveNames: names,
           hasMSC: labels.indexOf('MSC') >= 0 ? 1 : 0,
           hasMSB: labels.indexOf('MSB') >= 0 ? 1 : 0,
           blockShown: document.getElementById('social-curves').offsetParent !== null ? 1 : 0,
           inInputCard: !!document.getElementById('social-curves').closest('#sec-input') ? 1 : 0,
           oldField: document.getElementById('ext-input') ? 1 : 0,
           oldSign: document.getElementById('ext-neg') ? 1 : 0 };
})()`);
flag('чекбоксы MSB и MSC выключены', start.msbOn === 0 && start.mscOn === 0 && start.boxMsb === 0 && start.boxMsc === 0,
     JSON.stringify({ msb: start.msbOn, msc: start.mscOn }));
flag('по умолчанию MSB = формула спроса', start.valMsb === '100 - Q', start.valMsb);
flag('по умолчанию MSC = формула предложения', start.valMsc === 'Q', start.valMsc);
flag('на графике общественных кривых нет', start.hasMSC === 0 && start.hasMSB === 0,
     JSON.stringify({ MSC: start.hasMSC, MSB: start.hasMSB }));
check('рыночное равновесие Q', start.Qmkt, 50, 0.3);
check('рыночное равновесие P', start.Pmkt, 50, 0.3);
check('оптимум совпадает с рынком', start.Qopt, 50, 0.3);
check('DWL = 0', start.dwl, 0, 1e-6);
flag('кривые НЕ переименованы: на графике D и S',
     start.curveNames.includes('D') && start.curveNames.includes('S')
     && !start.curveNames.includes('MPB') && !start.curveNames.includes('MPC'),
     start.curveNames.join(', '));
flag('поля MSB и MSC живут во «Вводе функций»', start.blockShown === 1 && start.inInputCard === 1,
     JSON.stringify({ shown: start.blockShown, inCard: start.inInputCard }));
flag('поля издержек в сюжете больше нет', start.oldField === 0);
flag('переключателя знака эффекта больше нет', start.oldSign === 0);

// --- 2. Отрицательный внешний эффект: MSC = Q + 20 ----------------------
// Ручной расчёт: рынок D = S ⇒ 100 − Q = Q ⇒ Q = 50, P = 50.
// Оптимум MSB = MSC ⇒ 100 − Q = Q + 20 ⇒ Q = 40, P = MSC(40) = 60.
// DWL = ∫₄₀^50 (MSC − MSB) dq = ∫₄₀^50 (2q − 80) dq = (2500−4000) − (1600−3200) = 100.
// Корректирующий налог = D(40) − S(40) = 60 − 40 = 20.
const neg = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ext');
  document.getElementById('chk-msc').click();
  var inp = document.getElementById('inp-msc');
  inp.value = 'Q + 20'; inp.dispatchEvent(new Event('change'));
  redrawAll();
  var e = STATE.ext || {};
  var labels = [].map.call(document.querySelectorAll('#chart text'), function (t) { return t.textContent.trim(); });
  return { Qmkt: e.Qmkt, Pmkt: e.Pmkt, Qopt: e.Qopt, Popt: e.Popt, dwl: e.dwl,
           corr: e.corrective, sign: STATE.extSign, disabled: inp.disabled ? 1 : 0,
           hasMSC: labels.indexOf('MSC') >= 0 ? 1 : 0, hasMSB: labels.indexOf('MSB') >= 0 ? 1 : 0 };
})()`);
check('отрицательный · рынок Q', neg.Qmkt, 50, 0.3);
check('отрицательный · рынок P', neg.Pmkt, 50, 0.3);
check('отрицательный · оптимум Q', neg.Qopt, 40, 0.3);
check('отрицательный · оптимум P', neg.Popt, 60, 0.3);
check('отрицательный · DWL', neg.dwl, 100, 1.5);
check('отрицательный · налог Пигу', neg.corr, 20, 0.3);
flag('отрицательный · знак определён расчётом', neg.sign === 'neg', neg.sign);
flag('отрицательный · MSC появилась, MSB нет', neg.hasMSC === 1 && neg.hasMSB === 0, JSON.stringify(neg));
flag('включённое поле открыто для правки', neg.disabled === 0);

// --- 3. Положительный внешний эффект: MSB = 120 − Q ---------------------
// Оптимум MSB = MSC ⇒ 120 − Q = Q ⇒ Q = 60, P = MSC(60) = 60.
// DWL = ∫₅₀^60 (MSB − MSC) dq = ∫₅₀^60 (120 − 2q) dq = 3600 − 3500 = 100.
// Корректирующая субсидия = |D(60) − S(60)| = |40 − 60| = 20.
const pos = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ext');
  document.getElementById('chk-msb').click();
  var inp = document.getElementById('inp-msb');
  inp.value = '120 - Q'; inp.dispatchEvent(new Event('change'));
  redrawAll();
  var e = STATE.ext || {};
  var labels = [].map.call(document.querySelectorAll('#chart text'), function (t) { return t.textContent.trim(); });
  return { Qmkt: e.Qmkt, Qopt: e.Qopt, Popt: e.Popt, dwl: e.dwl, corr: e.corrective,
           sign: STATE.extSign,
           hasMSC: labels.indexOf('MSC') >= 0 ? 1 : 0, hasMSB: labels.indexOf('MSB') >= 0 ? 1 : 0 };
})()`);
check('положительный · рынок Q', pos.Qmkt, 50, 0.3);
check('положительный · оптимум Q', pos.Qopt, 60, 0.3);
check('положительный · оптимум P', pos.Popt, 60, 0.3);
check('положительный · DWL', pos.dwl, 100, 1.5);
check('положительный · субсидия (со знаком «минус» = субсидия)', pos.corr, -20, 0.3);
flag('положительный · знак определён расчётом', pos.sign === 'pos', pos.sign);
flag('положительный · MSB появилась, MSC нет', pos.hasMSB === 1 && pos.hasMSC === 0, JSON.stringify(pos));

// --- 4. Корректирующий инструмент приводит рынок ровно в оптимум --------
const pigou = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ext');
  document.getElementById('chk-msc').click();
  var inp = document.getElementById('inp-msc');
  inp.value = 'Q + 20'; inp.dispatchEvent(new Event('change'));
  document.getElementById('ext-pigou').click();
  redrawAll();
  var e = STATE.ext || {};
  return { pq: e.pigouEq ? e.pigouEq.Q : null, qopt: e.Qopt };
})()`);
check('налог Пигу приводит рынок в оптимум', pigou.pq, 40, 0.3);
check('и это ровно Qопт', Math.abs(pigou.pq - pigou.qopt), 0, 0.01);

if (errs.length) { ok = false; console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | ')); }
await browser.close();
console.log('\nФАЗА 5: ' + (ok ? 'СОШЛАСЬ' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
