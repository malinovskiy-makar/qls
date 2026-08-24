// Эталон вмешательства государства — снимается ДО правок и повторяется ПОСЛЕ
// КАЖДОЙ фазы ночной сессии «Вмешательство государства и внешние эффекты».
// Расхождение = откат фазы. Модель одна на все случаи: D = 100 − Q, S = Q.
//   node calc2/tests/interv_baseline_probe.mjs
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
const rows = [];
function check(label, got, want, tol) {
  const good = typeof got === 'number' && isFinite(got) && Math.abs(got - want) <= tol;
  if (!good) ok = false;
  rows.push({ label, got: (typeof got === 'number') ? +got.toFixed(4) : String(got), want, good });
}

// Общая обстановка: конкурентный рынок D = 100 − Q, S = Q.
const setup = `
  resetSceneMemory();
  setMode('market'); STATE.scenario = 'none'; STATE.curves = []; curveCounter = 0;
  addCurve('100 - Q'); setRole(STATE.curves[0], 'demand');
  addCurve('Q');       setRole(STATE.curves[1], 'supply');
  setMarket('comp'); setTaxKind('unit'); STATE.tax = 0; STATE.pReg = 0;
`;

// 1. Потоварный налог t = 20
const tax = await page.evaluate(`(function(){ ${setup}
  setType('tax'); setTax(20); redrawAll();
  var te = STATE.taxEq || {};
  return { Q1: te.Q, Pb: te.Pb, Ps: te.Ps, tx: STATE.tx, budget: STATE.budget, dwl: STATE.dwl };
})()`);
check('налог t=20 · Q1', tax.Q1, 40, 0.3);
check('налог t=20 · Pb', tax.Pb, 60, 0.3);
check('налог t=20 · Ps', tax.Ps, 40, 0.3);
check('налог t=20 · сбор', tax.tx, 800, 6);
check('налог t=20 · DWL', tax.dwl, 100, 2);

// 2. Субсидия s = 20
const sub = await page.evaluate(`(function(){ ${setup}
  setType('subsidy'); setTax(20); redrawAll();
  var te = STATE.taxEq || {};
  return { Q1: te.Q, budget: STATE.budget, dwl: STATE.dwl };
})()`);
check('субсидия s=20 · Q1', sub.Q1, 60, 0.3);
check('субсидия s=20 · расход', sub.budget, -1200, 8);
check('субсидия s=20 · DWL', sub.dwl, 100, 2);

// 3. Потолок 30
const ceil = await page.evaluate(`(function(){ ${setup}
  setType('ceiling'); setPReg(30); redrawAll();
  var pc = STATE.pc || {};
  return { Qd: pc.Qd, Qs: pc.Qs, gap: pc.gap, dwl: pc.dwl, binding: pc.binding ? 1 : 0 };
})()`);
check('потолок 30 · Qd', ceil.Qd, 70, 0.3);
check('потолок 30 · Qs', ceil.Qs, 30, 0.3);
check('потолок 30 · дефицит', ceil.gap, 40, 0.5);
check('потолок 30 · связывает', ceil.binding, 1, 0.1);

// 4. Пол 70
const floor = await page.evaluate(`(function(){ ${setup}
  setType('floor'); setPReg(70); redrawAll();
  var pc = STATE.pc || {};
  return { Qd: pc.Qd, Qs: pc.Qs, gap: pc.gap, dwl: pc.dwl, binding: pc.binding ? 1 : 0 };
})()`);
check('пол 70 · Qs', floor.Qs, 70, 0.3);
check('пол 70 · Qd', floor.Qd, 30, 0.3);
check('пол 70 · избыток', floor.gap, 40, 0.5);
check('пол 70 · связывает', floor.binding, 1, 0.1);

rows.forEach(r => console.log((r.good ? 'OK   ' : 'FAIL ') + r.label + ' = ' + r.got + ' (ожид ' + r.want + ')'));
if (errs.length) { ok = false; console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | ')); }
await browser.close();
console.log('\nЭТАЛОН: ' + (ok ? 'СОШЁЛСЯ' : 'РАЗОШЁЛСЯ'));
process.exit(ok ? 0 : 1);
