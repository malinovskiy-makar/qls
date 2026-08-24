// Фаза 2 — пол и потолок цены: настройки в правой панели, «было → стало»,
// связывающие и НЕсвязывающие случаи. Модель D = 100 − Q, S = Q (P* = 50).
//   node calc2/tests/interv_phase2_probe.mjs
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

const price = async (type, p) => page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ceil');
  setType('${type}'); setPReg(${p}); redrawAll();
  var pc = STATE.pc || {};
  return { Qd: pc.Qd, Qs: pc.Qs, gap: pc.gap, dwl: pc.dwl, Qtrade: pc.Qtrade,
           binding: pc.binding ? 1 : 0, active: STATE.pcActive ? 1 : 0,
           eqQ: (STATE.eq||{}).Q, eqP: (STATE.eq||{}).P,
           ghost: document.querySelectorAll('#chart g.ghost').length,
           info: ((document.getElementById('info-tax')||{}).innerText || '').replace(/\\s+/g,' ') };
})()`);

// --- 1. Потолок 30 — связывает, дефицит 40 -----------------------------
// Ручной расчёт: при P = 30 спрос Qd = 100 − 30 = 70, предложение Qs = 30.
// Торгуется короткая сторона: 30. Дефицит = 70 − 30 = 40.
// DWL = ∫ от 30 до 50 (100 − 2q) dq = 2500 − 2100 = 400.
const c30 = await price('ceiling', 30);
check('потолок 30 · Qd', c30.Qd, 70, 0.3);
check('потолок 30 · Qs', c30.Qs, 30, 0.3);
check('потолок 30 · дефицит', c30.gap, 40, 0.5);
check('потолок 30 · торговля (короткая сторона)', c30.Qtrade, 30, 0.3);
check('потолок 30 · DWL', c30.dwl, 400, 4);
flag('потолок 30 связывает', c30.binding === 1 && c30.active === 1);
flag('потолок 30 · «было → стало» по умолчанию выключено', c30.ghost === 0, 'слоёв ghost: ' + c30.ghost);

// --- 2. Пол 70 — связывает, избыток 40 ---------------------------------
// При P = 70 спрос Qd = 30, предложение Qs = 70, избыток = 40, торговля 30.
// DWL тот же: ∫ от 30 до 50 (100 − 2q) dq = 400.
const f70 = await price('floor', 70);
check('пол 70 · Qs', f70.Qs, 70, 0.3);
check('пол 70 · Qd', f70.Qd, 30, 0.3);
check('пол 70 · избыток', f70.gap, 40, 0.5);
check('пол 70 · торговля (короткая сторона)', f70.Qtrade, 30, 0.3);
check('пол 70 · DWL', f70.dwl, 400, 4);
flag('пол 70 связывает', f70.binding === 1 && f70.active === 1);
flag('пол 70 · «было → стало» по умолчанию выключено', f70.ghost === 0, 'слоёв ghost: ' + f70.ghost);

// --- 3. НЕсвязывающие случаи -------------------------------------------
// Потолок ВЫШЕ равновесной цены и пол НИЖЕ неё рынку не мешают.
const c70 = await price('ceiling', 70);
flag('потолок 70 (выше P*=50) не связывает', c70.binding === 0 && c70.active === 0,
     JSON.stringify({ binding: c70.binding, active: c70.active }));
flag('потолок 70 · дефицита не считается', c70.dwl === undefined || c70.dwl === null,
     'dwl=' + c70.dwl);
flag('потолок 70 · рынок остаётся в равновесии Q*=50', Math.abs(c70.eqQ - 50) < 0.3, 'Q*=' + c70.eqQ);
flag('потолок 70 · «было → стало» не рисуется (вмешательства нет)', c70.ghost === 0, 'ghost=' + c70.ghost);
flag('потолок 70 · панель честно говорит, что не действует',
     /не действует/.test(c70.info), c70.info.slice(0, 120));

const f30 = await price('floor', 30);
flag('пол 30 (ниже P*=50) не связывает', f30.binding === 0 && f30.active === 0,
     JSON.stringify({ binding: f30.binding, active: f30.active }));
flag('пол 30 · избытка не считается', f30.dwl === undefined || f30.dwl === null, 'dwl=' + f30.dwl);
flag('пол 30 · рынок остаётся в равновесии Q*=50', Math.abs(f30.eqQ - 50) < 0.3, 'Q*=' + f30.eqQ);
flag('пол 30 · панель честно говорит, что не действует',
     /не действует/.test(f30.info), f30.info.slice(0, 120));

// --- 4. «Было → стало» выключается повторным нажатием -------------------
const ghost = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ceil'); setType('ceiling'); setPReg(30); redrawAll();
  var box = document.getElementById('chk-ghost');
  var shown = !!(box && box.offsetParent !== null);
  var start = document.querySelectorAll('#chart g.ghost').length;   // по умолчанию выключено
  box.click();                                  // включаем
  var on1 = document.querySelectorAll('#chart g.ghost').length;
  var dashedNow = 0, ghostNow = 0;
  document.querySelectorAll('#chart g.ghost *').forEach(function (e) {
    if (e.getAttribute('stroke-dasharray')) dashedNow++;
    var s = e.getAttribute('stroke') || '';
    if (s && s === (typeof COL !== 'undefined' ? COL.ghost : '')) ghostNow++;
  });
  box.click();                                  // повторное нажатие убирает
  var off = document.querySelectorAll('#chart g.ghost').length;
  box.click();                                  // и возвращает
  var on2 = document.querySelectorAll('#chart g.ghost').length;
  return { shown: shown ? 1 : 0, start: start, on1: on1, off: off, on2: on2,
           dashed: dashedNow, ghostColor: ghostNow, checked: box.checked ? 1 : 0 };
})()`);
flag('тумблер «было → стало» виден в сцене пола и потолка', ghost.shown === 1);
flag('на входе в сцену тумблер не врёт: снят и слоя нет', ghost.start === 0, 'ghost=' + ghost.start);
flag('нажали — слой появился', ghost.on1 > 0, 'ghost=' + ghost.on1);
flag('повторное нажатие убирает', ghost.off === 0, 'ghost=' + ghost.off);
flag('и возвращает обратно', ghost.on2 > 0, 'ghost=' + ghost.on2);
flag('исходное равновесие рисуется пунктиром', ghost.dashed >= 2, 'пунктирных линий: ' + ghost.dashed);
flag('и приглушённым цветом', ghost.ghostColor >= 2, 'элементов цвета ghost: ' + ghost.ghostColor);

// --- 5. Выбор и настройки живут в ПРАВОЙ панели -------------------------
const where = await page.evaluate(`(function(){
  resetSceneMemory(); pickScene('ceil');
  var sec = document.getElementById('sec-tax');
  var inRight = !!(sec && sec.closest('.side-right'));
  var inLeft  = !!(sec && sec.closest('#tools-panel'));
  var leftLeftovers = [].slice.call(document.querySelectorAll('#tools-panel [id^="scn-pane-"]'))
                        .filter(function(e){ return e.offsetParent !== null; }).map(function(e){ return e.id; });
  return { inRight: inRight ? 1 : 0, inLeft: inLeft ? 1 : 0, leftLeftovers: leftLeftovers };
})()`);
flag('блок вмешательства — в правой панели', where.inRight === 1 && where.inLeft === 0, JSON.stringify(where));
flag('в левой панели от «Что изучаем» ничего не осталось',
     where.leftLeftovers.length === 0, where.leftLeftovers.join(', '));

if (errs.length) { ok = false; console.log('ОШИБКИ СТРАНИЦЫ: ' + errs.slice(0, 5).join(' | ')); }
await browser.close();
console.log('\nФАЗА 2: ' + (ok ? 'СОШЛАСЬ' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
