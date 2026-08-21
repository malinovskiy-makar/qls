/* Ночная сессия. ФАЗА 7 — ввод функций.
   Форма записи определяется сама, поля новой кривой сверху нет, пустая
   строка появляется только по кнопке, крестик гасит штатную и удаляет свою.
     node calc2/tests/night_phase7_input_probe.mjs */
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
  const rows = () => [...document.querySelectorAll('#curve-list .curve-row')];
  const inps = () => [...document.querySelectorAll('#curve-list .curve-expr-inp')];
  const out = {};
  resetSceneMemory(); pickScene('sd'); await wait(400);
  out.gone = ['new-role', 'cf-pq', 'cf-qp', 'inp-formula', 'curve-form-seg', 'curve-form-hint']
    .filter(id => document.getElementById(id));
  out.startRows = rows().length;
  out.startNames = STATE.curves.map(c => c.role);
  // Кнопка стоит ПОД списком
  const btn = document.getElementById('btn-add-curve'), list = document.getElementById('curve-list');
  out.btnBelow = !!(btn && list && (list.compareDocumentPosition(btn) & Node.DOCUMENT_POSITION_FOLLOWING));

  // Само поле не появляется: печатаем в готовое — новых строк быть не должно.
  const d = inps()[0]; d.value = '100 - Q'; d.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(250);
  out.rowsAfterTyping = rows().length;

  // Кнопка заводит пустую строку
  btn.click(); await wait(300);
  out.rowsAfterBtn = rows().length;
  const last = inps()[inps().length - 1];
  out.newRowEmpty = last.value === '';
  out.newCurveRole = STATE.curves[STATE.curves.length - 1].role;
  out.eqWithEmpty = STATE.eq ? { P: STATE.eq.P, Q: STATE.eq.Q } : null;

  // Добавленная кривая не меняет равновесие
  last.value = '30 + 0.2*Q'; last.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(300);
  out.eqWithExtra = STATE.eq ? { P: STATE.eq.P, Q: STATE.eq.Q } : null;
  out.extraDrawn = [...document.querySelectorAll('#chart path[data-curve]')].length;

  // Форма записи: определяется сама
  out.forms = {};
  const set = (i, v) => { const e = inps()[i]; e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); };
  set(0, '100 - Q'); await wait(200); out.forms.pq = STATE.curves[0].srcForm;
  set(0, '100 - 2*P'); await wait(250); out.forms.qp = STATE.curves[0].srcForm;
  out.qpLinear = STATE.curves[0].linear ? { a: STATE.curves[0].linear.a, b: STATE.curves[0].linear.b } : null;
  set(0, '100 - Q'); await wait(250); out.forms.back = STATE.curves[0].srcForm;
  set(2, '20'); await wait(200); out.forms.constant = STATE.curves[2].srcForm;

  // Крестик: штатная гаснет, добавленная удаляется
  const del = (i) => rows()[i].querySelector('.crow-top .btn-icon:last-of-type').click();
  const before = STATE.curves.length;
  del(0); await wait(250);
  out.staffAfterX = { count: STATE.curves.length, visible: STATE.curves[0].visible, role: STATE.curves[0].role };
  // галочка возвращает
  rows()[0].querySelector('input[type=checkbox]').click(); await wait(250);
  out.staffBack = STATE.curves[0].visible;
  del(2); await wait(250);
  out.addedAfterX = { was: before, now: STATE.curves.length };
  return out;
});
console.log(JSON.stringify(r, null, 1));
rep('переключатель формы, роль и верхнее поле убраны', r.gone.length === 0, r.gone.join(', '));
rep('кнопка «Добавить кривую» стоит под списком', r.btnBelow);
rep('модель открывается двумя готовыми полями', r.startRows === 2, 'строк ' + r.startRows);
rep('печать в готовом поле новых строк не заводит', r.rowsAfterTyping === 2, 'строк ' + r.rowsAfterTyping);
rep('кнопка добавляет ровно одну пустую строку', r.rowsAfterBtn === 3 && r.newRowEmpty,
    'строк ' + r.rowsAfterBtn + ', пустая: ' + r.newRowEmpty);
rep('у добавленной кривой роли нет', !r.newCurveRole, String(r.newCurveRole));
rep('пустая строка равновесие не трогает: P*=50, Q*=50',
    r.eqWithEmpty && Math.abs(r.eqWithEmpty.P - 50) < .3 && Math.abs(r.eqWithEmpty.Q - 50) < .3,
    JSON.stringify(r.eqWithEmpty));
rep('добавленная кривая равновесие не трогает: P*=50, Q*=50',
    r.eqWithExtra && Math.abs(r.eqWithExtra.P - 50) < .3 && Math.abs(r.eqWithExtra.Q - 50) < .3,
    JSON.stringify(r.eqWithExtra));
rep('добавленная кривая всё-таки нарисована', r.extraDrawn === 3, 'кривых на холсте ' + r.extraDrawn);
rep('«100 - Q» разобрано как P(Q)', r.forms.pq === 'PQ', r.forms.pq);
rep('«100 - 2*P» разобрано как Q(P)', r.forms.qp === 'QP', r.forms.qp);
rep('Q(P) приведено к канону: P = 50 - 0,5·Q', r.qpLinear
    && Math.abs(r.qpLinear.a + 0.5) < 1e-6 && Math.abs(r.qpLinear.b - 50) < 1e-6, JSON.stringify(r.qpLinear));
rep('правка обратно возвращает P(Q)', r.forms.back === 'PQ', r.forms.back);
rep('число «20» — это P(Q)', r.forms.constant === 'PQ', r.forms.constant);
rep('крестик у ШТАТНОЙ гасит, не удаляет',
    r.staffAfterX.count === 3 && r.staffAfterX.visible === false && r.staffAfterX.role === 'demand',
    JSON.stringify(r.staffAfterX));
rep('галочка возвращает погашенную', r.staffBack === true, String(r.staffBack));
rep('крестик у ДОБАВЛЕННОЙ удаляет', r.addedAfterX.now === r.addedAfterX.was - 1, JSON.stringify(r.addedAfterX));
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'ввод функций работает по новому договору' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
