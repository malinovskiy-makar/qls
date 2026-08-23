// Фаза 1 — два налоговых сюжета сведены в один «Налоги и субсидии».
// Проверяются: числа потоварного налога, НДС и акциза; равенство Q1 при обоих
// плательщиках; каскад уровней в правой панели; старые ключи сцен как синонимы.
//   node calc2/tests/interv_phase1_probe.mjs
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

const setup = `
  resetSceneMemory(); pickScene('taxes');
`;

// --- 1. Потоварный налог t = 20 (эталон) --------------------------------
const unit = await page.evaluate(`(function(){ ${setup}
  setTaxForm('unit'); setTaxSide('seller'); setTax(20); redrawAll();
  var te = STATE.taxEq || {};
  return { Q1: te.Q, Pb: te.Pb, Ps: te.Ps, tx: STATE.tx, dwl: STATE.dwl, kind: STATE.taxKind };
})()`);
check('потоварный t=20 · Q1', unit.Q1, 40, 0.3);
check('потоварный t=20 · Pb', unit.Pb, 60, 0.3);
check('потоварный t=20 · Ps', unit.Ps, 40, 0.3);
check('потоварный t=20 · сбор', unit.tx, 800, 6);
check('потоварный t=20 · DWL', unit.dwl, 100, 2);
flag('потоварный считается сдвигом', unit.kind === 'unit', unit.kind);

// --- 2. НДС τ = 20 % ----------------------------------------------------
// Ручной расчёт: S_после = (1+τ)·S = 1,2·Q. 100 − Q = 1,2·Q ⇒ Q1 = 100/2,2 = 45,4545.
// Pb = 100 − 45,4545 = 54,5455; Ps = 45,4545 (и Pb/Ps = 1,2 — проверка ставки).
// Сбор = (Pb − Ps)·Q1 = 9,0909 · 45,4545 = 413,2231.
// DWL = ½·(Q* − Q1)·(Pb − Ps) = ½ · 4,5455 · 9,0909 = 20,6612.
const vat = await page.evaluate(`(function(){ ${setup}
  setTaxForm('vat'); setTax(20); redrawAll();
  var te = STATE.taxEq || {};
  return { Q1: te.Q, Pb: te.Pb, Ps: te.Ps, tx: STATE.tx, dwl: STATE.dwl,
           kind: STATE.taxKind, ratio: te.Pb / te.Ps, sideShown: isShown('taxside-row') ? 1 : 0 };
  function isShown(id){ var e=document.getElementById(id); return e && e.offsetParent !== null; }
})()`);
check('НДС τ=20% · Q1', vat.Q1, 45.4545, 0.02);
check('НДС τ=20% · Pb', vat.Pb, 54.5455, 0.02);
check('НДС τ=20% · Ps', vat.Ps, 45.4545, 0.02);
check('НДС τ=20% · Pb/Ps = 1+τ', vat.ratio, 1.2, 0.002);
check('НДС τ=20% · сбор', vat.tx, 413.2231, 0.6);
check('НДС τ=20% · DWL', vat.dwl, 20.6612, 0.3);
flag('НДС считается поворотом', vat.kind === 'advalorem', vat.kind);
flag('у НДС стороны не спрашивают', vat.sideShown === 0);

// --- 3. Акциз t = 20 ----------------------------------------------------
// Ручной расчёт: акциз — потоварный налог, S_после = Q + 20. 100 − Q = Q + 20
// ⇒ Q1 = 40. Pb = 60, Ps = 40, сбор = 20·40 = 800, DWL = ½·10·20 = 100.
const exc = await page.evaluate(`(function(){ ${setup}
  setTaxForm('excise'); setTax(20); redrawAll();
  var te = STATE.taxEq || {};
  return { Q1: te.Q, Pb: te.Pb, Ps: te.Ps, tx: STATE.tx, dwl: STATE.dwl,
           kind: STATE.taxKind, side: STATE.taxSide,
           sideShown: (function(){ var e=document.getElementById('taxside-row'); return e && e.offsetParent !== null ? 1 : 0; })() };
})()`);
check('акциз t=20 · Q1', exc.Q1, 40, 0.3);
check('акциз t=20 · Pb', exc.Pb, 60, 0.3);
check('акциз t=20 · Ps', exc.Ps, 40, 0.3);
check('акциз t=20 · сбор', exc.tx, 800, 6);
check('акциз t=20 · DWL', exc.dwl, 100, 2);
flag('акциз считается сдвигом (как потоварный)', exc.kind === 'unit', exc.kind);
flag('у акциза плательщик закреплён за продавцом', exc.side === 'seller', exc.side);
flag('у акциза стороны не спрашивают', exc.sideShown === 0);

// --- 4. Кто платит — на Q1 и бремя не влияет ----------------------------
const sides = await page.evaluate(`(function(){ ${setup}
  setTaxForm('unit'); setTax(20);
  setTaxSide('seller'); redrawAll();
  var a = STATE.taxEq || {}; var aB = STATE.incBuyer, aS = STATE.incSeller, aT = STATE.tx, aD = STATE.dwl;
  setTaxSide('buyer'); redrawAll();
  var b = STATE.taxEq || {};
  return { Qs: a.Q, Qb: b.Q, Pbs: a.Pb, Pbb: b.Pb, Pss: a.Ps, Psb: b.Ps,
           burdBs: aB, burdBb: STATE.incBuyer, burdSs: aS, burdSb: STATE.incSeller,
           txs: aT, txb: STATE.tx, dwls: aD, dwlb: STATE.dwl };
})()`);
check('платит продавец · Q1', sides.Qs, 40, 0.3);
check('платит покупатель · Q1', sides.Qb, 40, 0.3);
check('Q1 совпал (разница)', Math.abs(sides.Qs - sides.Qb), 0, 1e-9);
check('Pb совпал (разница)', Math.abs(sides.Pbs - sides.Pbb), 0, 1e-9);
check('Ps совпал (разница)', Math.abs(sides.Pss - sides.Psb), 0, 1e-9);
check('бремя покупателя совпало', Math.abs(sides.burdBs - sides.burdBb), 0, 1e-9);
check('бремя продавца совпало', Math.abs(sides.burdSs - sides.burdSb), 0, 1e-9);
check('сбор совпал', Math.abs(sides.txs - sides.txb), 0, 1e-9);
check('DWL совпал', Math.abs(sides.dwls - sides.dwlb), 0, 1e-9);

// --- 5. Каскад: все пять уровней разом не показываются -------------------
const casc = await page.evaluate(`(function(){ ${setup}
  var vis = function(id){ var e=document.getElementById(id); return !!(e && e.offsetParent !== null); };
  var snap = function(){ return { kind: vis('taxkind-row'), side: vis('taxside-row'),
                                  rate: vis('tax-field'), price: vis('pc-field'),
                                  exc: (function(){ var e=document.getElementById('tk-exc'); return !!(e && e.offsetParent !== null); })() }; };
  setTaxForm('unit'); setType('tax'); var t1 = snap();
  setTaxForm('vat');  var t2 = snap();
  setType('subsidy'); var t3 = snap();
  setType('ceiling'); var t4 = snap();
  setType('tax'); setTaxForm('unit');
  return { t1: t1, t2: t2, t3: t3, t4: t4 };
})()`);
flag('налог потоварный: вид + сторона + ставка, цены нет',
     casc.t1.kind && casc.t1.side && casc.t1.rate && !casc.t1.price, JSON.stringify(casc.t1));
flag('НДС: вид + ставка, стороны нет',
     casc.t2.kind && !casc.t2.side && casc.t2.rate, JSON.stringify(casc.t2));
flag('субсидия: вид + получатель, кнопки «Акциз» нет',
     casc.t3.kind && casc.t3.side && !casc.t3.exc, JSON.stringify(casc.t3));
flag('потолок: ни вида, ни стороны — только цена',
     !casc.t4.kind && !casc.t4.side && casc.t4.price && !casc.t4.rate, JSON.stringify(casc.t4));

// --- 6. Старые ключи сцен живы синонимами --------------------------------
const syn = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('tax');
  var a = { key: STATE.sceneKey, base: baseScene('tax'), kind: STATE.taxKind, t: STATE.tax, type: STATE.intervType };
  resetSceneMemory(); pickScene('tax-adv');
  var b = { key: STATE.sceneKey, base: baseScene('tax-adv'), kind: STATE.taxKind, t: STATE.tax, form: STATE.taxForm };
  resetSceneMemory(); pickScene('taxes');
  var c = { key: STATE.sceneKey, base: baseScene('taxes'), kind: STATE.taxKind, t: STATE.tax, type: STATE.intervType };
  return { a: a, b: b, c: c, name: (document.getElementById('scene-name')||{}).textContent };
})()`);
flag("ключ 'tax' работает: потоварный t=20",
     syn.a.key === 'tax' && syn.a.base === 'tax' && syn.a.kind === 'unit' && syn.a.t === 20 && syn.a.type === 'tax',
     JSON.stringify(syn.a));
flag("ключ 'tax-adv' работает: НДС τ=20%",
     syn.b.key === 'tax-adv' && syn.b.base === 'tax' && syn.b.kind === 'advalorem' && syn.b.form === 'vat' && syn.b.t === 20,
     JSON.stringify(syn.b));
flag("ключ 'taxes' — та же базовая сцена",
     syn.c.key === 'taxes' && syn.c.base === 'tax' && syn.c.kind === 'unit' && syn.c.t === 20,
     JSON.stringify(syn.c));
flag('заголовок сцены «Налоги и субсидии»', (syn.name || '').trim() === 'Налоги и субсидии', syn.name);

// --- 7. На главном экране осталась одна карточка вместо двух -------------
const cards = await page.evaluate(() => ({
  taxes: document.querySelectorAll('.scard[data-scene="taxes"]').length,
  old: document.querySelectorAll('.scard[data-scene="tax"], .scard[data-scene="tax-adv"]').length,
}));
flag('на главном экране одна карточка налогов', cards.taxes === 1 && cards.old === 0, JSON.stringify(cards));

if (errs.length) { ok = false; console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | ')); }
await browser.close();
console.log('\nФАЗА 1: ' + (ok ? 'СОШЛАСЬ' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
