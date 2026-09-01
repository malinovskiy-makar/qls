/* ПОЛЯ ФОРМУЛ СЛЫШАТ, ЧТО В НИХ ПЕЧАТАЮТ — обход всех сцен, 01.09.

     ./venv313/bin/python manage.py runserver 8099 --noreload
     node calc2/tests/formula_input_probe.mjs

   Поля формул — это поля MathLive, и мост между набранным полем и скрытым
   `<input>` (`toInput` в 82-input.js) шлёт ТОЛЬКО событие `input`. Поле,
   подписанное на один `change`, набранного не слышит вовсе: человек печатает
   «100 − aQ», ползунок `a` появляется (syncParams читает поля прямо из DOM),
   а состояние остаётся с прежней формулой.

   Прибор проверяет ПОВЕДЕНИЕ, а не список слушателей: ставит в поле другое
   значение, шлёт один `input` — так же, как мост, — и смотрит, изменилась ли
   картинка. Не изменилась при `input`, но изменилась при `change` — поле
   глухое.

   ⚠️ Прибор САМ раскрывает все карточки: сцена открывается со свёрнутыми, а
   поля MathLive собираются лениво — по видимому замер был бы занижен.
*/
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let bad = 0, total = 0;
function cmp(label, got, want, tol) {
  total++;
  const ok = (typeof got === 'number' && isFinite(got)) ? Math.abs(got - want) <= (tol || 0) : (got === want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'OK  ' : 'FAIL') + ' ' + label.padEnd(48)
    + 'ожидалось ' + String(want).padEnd(10) + 'получилось ' + String(got));
}
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }

async function expandAll() {
  await page.evaluate(() => {
    if (typeof setToolsOpen === 'function') setToolsOpen(true);
    if (typeof setParamsOpen === 'function') setParamsOpen(true);
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(btn => {
      const body = document.getElementById(btn.getAttribute('aria-controls'));
      if (!body) return;
      body.classList.add('open');
      btn.setAttribute('aria-expanded', 'true');
      const card = btn.closest('.section, .side-part');
      if (card) card.classList.add('open-card');
    });
    if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
  });
  await page.waitForTimeout(420);
}

/* ── Обход всех сцен: каждое видимое поле формул проверяется на слух ──── */
head('Глухие поля формул по всем сценам');
const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const deaf = [];
for (const key of scenes) {
  await page.evaluate((k) => {
    pickScene(k);
    /* Поля общественных кривых заперты, пока снят чекбокс слева: без него их
       не проверить, а глухими они были именно они. Отпираем как человек. */
    ['chk-msb', 'chk-msc'].forEach(id => {
      const b = document.getElementById(id);
      if (b && !b.checked) { b.checked = true; b.dispatchEvent(new Event('change', { bubbles: true })); }
    });
    redrawAll();
  }, key);
  await expandAll();
  const rows = await page.evaluate(async (k) => {
    /* Отпечаток картинки: длины путей кривых плюс текст ключевых значений.
       Формула изменилась — изменится и он; от густоты сетки не зависит. */
    const sig = () => {
      let s = '';
      document.querySelectorAll('#chart path').forEach(p => { s += (p.getAttribute('d') || '').length + ','; });
      const e = document.getElementById('info-eq');
      return s + '|' + (e ? e.textContent.length : 0);
    };
    /* ⚠️ ЖДЁМ ДОЛЬШЕ, ЧЕМ ЖИВЁТ АНИМАЦИЯ ОСЕЙ. Дребезг поля 220 мс, а
       переезд осей у макромоделей ещё 450: замер через 260 мс попадал в
       середину переезда и врал про «поле не слышит». */
    const wait = () => new Promise(r => setTimeout(r, 800));
    const out = [];
    const fields = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS : [])
      .filter(i => i.isConnected && typeof fieldActive === 'function' && fieldActive(i) && !i.disabled);
    for (const inp of fields) {
      const id = inp.id || '(без id)';
      const was = inp.value;
      // Значение заведомо другое: к записи добавляется слагаемое.
      const probe = (was && was.trim()) ? (was + ' + 1') : '1';
      const s0 = sig();
      inp.value = probe;
      inp.dispatchEvent(new Event('input', { bubbles: true }));   // так шлёт мост MathLive
      await wait();
      const sIn = sig();
      inp.dispatchEvent(new Event('change', { bubbles: true }));
      await wait();
      const sCh = sig();
      inp.value = was;
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
      await wait();
      out.push({ scene: k, id, слышитInput: sIn !== s0, слышитChange: sCh !== s0 });
    }
    return out;
  }, key);
  rows.forEach(r => { if (!r.слышитInput && r.слышитChange) deaf.push(r); });
}
const uniq = {};
deaf.forEach(r => { (uniq[r.id] = uniq[r.id] || []).push(r.scene); });
Object.keys(uniq).forEach(id => console.log('  ГЛУХОЕ ПОЛЕ ' + id + ' — сцены: ' + uniq[id].join(', ')));
cmp('полей, слышащих только change', Object.keys(uniq).length, 0);

/* ── Контрольное число внешних эффектов ──────────────────────────────── */
head('Внешние эффекты: MSB и MSC слышат набранное');
const r = await page.evaluate(async () => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  resetSceneMemory(); pickScene('ext');
  updateCurveExpr(STATE.curves.find(c => c.role === 'demand'), '100-Q');
  updateCurveExpr(STATE.curves.find(c => c.role === 'supply'), 'Q');
  redrawAll();
  // Включаем обе общественные кривые и печатаем в поля — ТОЛЬКО событием input.
  ['msb', 'msc'].forEach(k => { STATE[k + 'On'] = true; });
  const put = (id, txt) => {
    const inp = document.getElementById(id);
    inp.disabled = false;
    inp.value = txt;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  };
  put('inp-msb', '100 - a*Q');
  put('inp-msc', 'b*Q');
  await wait(400);
  STATE.params.a = Object.assign({ min: 0, max: 10, step: 0.1 }, STATE.params.a, { value: 3.3 });
  STATE.params.b = Object.assign({ min: 0, max: 10, step: 0.1 }, STATE.params.b, { value: 2.6 });
  redrawAll();
  await wait(200);
  const e = STATE.ext || {};
  return { msb: STATE.msbExpr, msc: STATE.mscExpr,
           Qopt: e.Qopt, Popt: e.Popt, Qmkt: e.Qmkt };
});
cmp('MSB дошла до состояния', r.msb, '100 - a*Q');
cmp('MSC дошла до состояния', r.msc, 'b*Q');
cmp('общественный оптимум Q', r.Qopt, 16.95, 0.01);
cmp('общественный оптимум P', r.Popt, 44.07, 0.01);
cmp('рыночное равновесие Q не сдвинулось', r.Qmkt, 50, 1e-4);

console.log('\nОшибок страницы: ' + errs.length);
errs.slice(0, 5).forEach(e => console.log('  ! ' + e));
console.log(bad ? ('ПРОВАЛЕНО ' + bad + ' из ' + total) : ('ВСЕ ' + total + ' ПРОВЕРОК ПОЛЕЙ СОШЛИСЬ'));
await browser.close();
process.exit(bad || errs.length ? 1 : 0);
